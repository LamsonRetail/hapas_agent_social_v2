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


def _drain_stderr(proc: subprocess.Popen, ready: threading.Event) -> None:
    for raw in iter(proc.stderr.readline, ""):
        line = raw.rstrip("\n")
        if not line:
            continue
        if _READY_MARKER in line and not ready.is_set():
            ready.set()
        # surface diagnostics but don't spam
        print(f"[event/stderr] {line}")


def _consume_once(cli: str, handler: Handler) -> None:
    """Run one `event consume` process until it exits (respawn/token refresh)."""
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
    threading.Thread(target=_drain_stderr, args=(proc, ready), daemon=True).start()

    if ready.wait(timeout=30):
        print(f"  Intake: ✅ event bus ready — consuming {_EVENT_KEY} as bot")
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
    while True:
        try:
            _consume_once(cli, handler)
            backoff = 2.0  # clean exit → reset backoff
        except Exception as e:
            print(f"[event] consumer crashed: {e}; retry in {backoff:.0f}s")
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)
