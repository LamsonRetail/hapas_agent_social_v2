"""Bot message intake via lark-cli event stream (replaces the as-user poller).

Instead of polling a user seat's inbox, we run the app BOT and let Lark push
messages to us over lark-cli's long-connection event bus:

    lark-cli event consume im.message.receive_v1 --as bot   →   NDJSON on stdout

Each stdout line is one decoded message event (flat shape, see
`lark-cli event schema im.message.receive_v1 --json`). We parse it, filter
(ignore our own/bot messages; in groups only answer when the bot is @mentioned),
and hand it to a callback.

Prereqs (Lark Developer Console, for the bot app):
  - Subscribe the event ``im.message.receive_v1`` (long-connection / "应用长连接").
  - Grant scope ``im:message.p2p_msg:readonly`` (and ``im:message`` to reply).
  - Add the bot to any group you want it to answer in.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from typing import Callable

import lark_client as lark
from config import config
from cli_support import cli_env as _cli_env
from cli_support import ensure_config, resolve_cli as _resolve_cli

_EVENT_KEY = os.environ.get("LARK_EVENT_KEY", "im.message.receive_v1")
_READY_MARKER = "[event] ready"

# Re-spawn the consumer periodically so a very long-running listener stays fresh.
# (The CLI mints & auto-refreshes its own token from file-based config, so this
# is resilience, not a token-lifetime requirement.)
_RESPAWN_SECONDS = float(os.environ.get("LARK_EVENT_RESPAWN_SECONDS", str(90 * 60)))
#: Lùi bao lâu khi bus bị nơi khác giữ. Vẫn kiểm lại — gateway có thể tắt, lúc đó
#: listener local phải giành lại được — nhưng thưa đủ để không rác log.
_LUI_KHI_BI_GIU = float(os.environ.get("LARK_EVENT_HELD_BACKOFF_SECONDS", str(10 * 60)))

# Message dict handed to the callback.
Handler = Callable[[dict], None]


def _parse_event(line: str) -> dict | None:
    """Turn one NDJSON event line into a normalized message dict, or None if it
    should be ignored."""
    try:
        ev = json.loads(line)
    except Exception:
        return None
    # A consume line may be the event itself (flat) or wrapped; handle both.
    if isinstance(ev, dict) and "message_id" not in ev and isinstance(ev.get("data"), dict):
        ev = ev["data"]

    message_id = ev.get("message_id") or ev.get("id")
    chat_id = ev.get("chat_id")
    if not message_id or not chat_id:
        return None

    sender_type = ev.get("sender_type")
    if sender_type == "bot":  # never answer another bot / our own echo
        return None

    is_group = ev.get("chat_type") == "group"
    mentions = ev.get("mentions") or []
    bot_id = lark.get_bot_open_id()
    mentioned = bool(bot_id) and any(
        (m.get("id") == bot_id) for m in mentions if isinstance(m, dict)
    )

    # In groups only jump in when the bot is @mentioned; in p2p always answer.
    if is_group and not mentioned:
        return None

    text = ev.get("content") or ""
    # strip @mention placeholders (@_user_1, @_all) from the rendered text
    import re

    text = re.sub(r"@_(?:user_\d+|all)\b", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    return {
        "message_id": message_id,
        "chat_id": chat_id,
        "chat_type": ev.get("chat_type"),
        "is_group": is_group,
        "sender_id": ev.get("sender_id"),
        "message_type": ev.get("message_type"),
        "text": text,
        "mentions": mentions,
        "thread_id": ev.get("thread_id"),
        "in_thread": bool(ev.get("thread_id")),
        "create_time": ev.get("create_time"),
    }


#: lark-cli báo chuỗi này khi MỘT bus khác đã giữ app — Lark chỉ cho một bus toàn cục.
#: Từ khi platform bật gateway Lark động, chính gateway đó giữ kết nối, nên listener
#: local KHÔNG BAO GIỜ nối được nữa. Đó là trạng thái ĐÚNG, không phải sự cố: tin Lark
#: đi qua gateway rồi thành job, agent vẫn trả lời như thường.
_BUS_BI_GIU = "another event bus is already connected"
#: Bản lark-cli mới báo cùng tình trạng bằng gợi ý này (bus ở máy khác — gateway).
_DAU_BI_GIU = (_BUS_BI_GIU, "remote event connection detected")


def _drain_stderr(proc: subprocess.Popen, ready: threading.Event,
                  bi_giu: threading.Event | None = None) -> None:
    """In stderr của lark-cli, trừ bản dump "bus bị giữ".

    Sự cố 04/10/2026: mỗi 10 phút lark-cli in ~12 dòng (consuming as…, local bus not
    found…, rồi một khối JSON lỗi) — 142 lần — dù đó là trạng thái ĐÚNG khi gateway
    platform giữ bus. Bản trước chỉ nuốt đúng dòng có câu báo, phần còn lại vẫn ra log.
    Nay giữ các dòng TRƯỚC khi sẵn sàng lại; hoá ra bus bị giữ thì bỏ cả khối
    (supervisor in một dòng duy nhất), còn sẵn sàng hoặc thoát vì lý do khác thì in đủ."""
    cho: list[str] = []

    def xa():
        for d in cho:
            print(f"[event/stderr] {d}")
        cho.clear()

    for raw in iter(proc.stderr.readline, ""):
        line = raw.rstrip("\n")
        if not line:
            continue
        if bi_giu is not None and any(d in line for d in _DAU_BI_GIU):
            bi_giu.set()
            cho.clear()
            continue
        if bi_giu is not None and bi_giu.is_set():
            continue          # phần còn lại của bản dump
        if _READY_MARKER in line and not ready.is_set():
            ready.set()
            cho.append(line)
            xa()
            continue
        if ready.is_set() or bi_giu is None:
            print(f"[event/stderr] {line}")
            continue
        cho.append(line)
        if len(cho) > 200:    # không bao giờ giữ vô hạn
            xa()
    if not (bi_giu is not None and bi_giu.is_set()):
        xa()


def _consume_once(cli: str, handler: Handler) -> bool:
    """Chạy một lượt `event consume` tới khi nó thoát.

    Trả True nếu lượt này thất bại vì MỘT BUS KHÁC đang giữ app — supervisor dùng
    tin đó để lùi lâu thay vì thử lại mỗi vài giây suốt ngày.
    """
    proc = subprocess.Popen(
        [cli, "event", "consume", _EVENT_KEY, "--as", "bot"],
        env=_cli_env(),
        stdin=subprocess.PIPE,  # keep open → unbounded run (stdin EOF = graceful stop)
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=str(config.here),
    )
    ready = threading.Event()
    bi_giu = threading.Event()
    doc_loi = threading.Thread(target=_drain_stderr, args=(proc, ready, bi_giu), daemon=True)
    doc_loi.start()

    # Chờ tối đa 30 giây, nhưng thôi chờ ngay khi biết bus bị giữ hoặc lark-cli đã thoát.
    het = time.time() + 30
    while not ready.is_set() and not bi_giu.is_set() and time.time() < het:
        if proc.poll() is not None:
            doc_loi.join(timeout=5)
            break
        ready.wait(0.5)
    if ready.is_set():
        print(f"  Intake: ✅ event bus ready — consuming {_EVENT_KEY} as bot")
    elif bi_giu.is_set():
        pass          # supervisor giải thích, chỗ này im để khỏi nói hai lần
    else:
        print(f"  Intake: ⚠ no ready marker after 30s (still trying to consume {_EVENT_KEY})")

    deadline = time.time() + _RESPAWN_SECONDS
    try:
        for raw in iter(proc.stdout.readline, ""):
            line = raw.strip()
            if line:
                msg = _parse_event(line)
                if msg:
                    try:
                        handler(msg)
                    except Exception as e:
                        print(f"[event] handler error: {e}")
            if time.time() > deadline:
                print("[event] token-refresh respawn window reached — restarting consumer")
                break
    finally:
        # graceful stop: close stdin, then terminate (never kill -9 — leaks subs)
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            pass
        # Đọc hết stderr rồi mới kết luận: không thì dòng "bus bị giữ" có thể chưa kịp
        # tới, supervisor tưởng thoát sạch và quay lại ngay.
        doc_loi.join(timeout=5)
    return bi_giu.is_set()


def start_listener(handler: Handler) -> None:
    """Blocking supervisor: (re)spawn the event consumer forever."""
    cli = _resolve_cli()
    if not cli:
        raise RuntimeError(
            "Không tìm thấy lark-cli. Cài bằng `npx @larksuite/cli@latest install` "
            "hoặc đặt LARK_CLI_PATH."
        )
    ensure_config()  # create file-based config.json once (the daemon needs it)
    backoff = 2.0
    da_bao_bi_giu = False
    while True:
        try:
            if _consume_once(cli, handler):
                # Bus bị nơi khác giữ. Từ khi platform bật gateway Lark động thì đây là
                # trạng thái ỔN ĐỊNH, không phải sự cố — và nó không tự hết. Thử lại mỗi
                # vài giây chỉ tổ đổ log, rồi người sau đọc log tưởng bot hỏng. (Đã xảy
                # ra: mất nửa tiếng đi tìm "kết nối ma" mà hoá ra là gateway.)
                if not da_bao_bi_giu:
                    print("[event] app Lark đang do MỘT BUS KHÁC giữ — gần như chắc chắn là "
                          "gateway của platform. Tin Lark vẫn tới qua job, agent vẫn trả lời "
                          "bình thường; listener local chỉ là đường CŨ. Lùi kiểm lại mỗi "
                          f"{_LUI_KHI_BI_GIU // 60} phút, không báo lại.")
                    da_bao_bi_giu = True
                time.sleep(_LUI_KHI_BI_GIU)
                continue
            da_bao_bi_giu = False
            backoff = 2.0  # clean exit → reset backoff
        except Exception as e:
            print(f"[event] consumer crashed: {e}; retry in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
