"""Social Agent: run the Lark BOT agent.

Receives messages pushed to the app bot over lark-cli's event bus
(`im.message.receive_v1`), sends each new message to the Hermes brain
(model from AGENT_MODEL via openai-codex), and replies AS the bot.

    python run.py

Prereqs (Lark Developer Console, for the bot app):
  - Subscribe the event `im.message.receive_v1` (long-connection mode).
  - Grant scopes: `im:message.p2p_msg:readonly` (receive) + `im:message` (send)
    (+ `im:message.reactions:write_only` for the typing badge).
  - Add the bot to any group you want it to answer in.
"""

from __future__ import annotations

import os
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import lark_client as lark
import lsr_platform            # nối platform — chỉ báo cáo, không đổi hành vi
import phoenix_trace           # trace sang Phoenix — tắt nếu thiếu env, không đổi hành vi
from config import config
from listener import start_listener

# ───────────────────────── network safety ─────────────────────────
# A global default socket timeout caps ANY blocking socket read/connect that
# doesn't set its own, so a stuck request RAISES instead of hanging forever.
_NET_TIMEOUT = float(os.environ.get("AGENT_NET_TIMEOUT", "90"))
socket.setdefaulttimeout(_NET_TIMEOUT)

# Hard cap on a single reply (whole brain turn, possibly many tool iterations).
_REPLY_TIMEOUT = float(os.environ.get("AGENT_REPLY_TIMEOUT", "180"))

# ───────────────────────── concurrency ─────────────────────────
# The listener callback must stay snappy, so it does NOT run the (slow) brain
# inline. Each new message is dispatched to a small thread pool. Different chats
# are answered concurrently; within a single chat a per-chat lock keeps messages
# strictly in order.
_MAX_WORKERS = int(os.environ.get("AGENT_MAX_WORKERS", "4"))
_pool = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="social-worker")
_brain_pool = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="social-brain")

_chat_locks: dict[str, threading.Lock] = {}
_chat_locks_guard = threading.Lock()

# de-dupe: Lark can redeliver an event; message_id is the idempotency key.
_seen_messages: set[str] = set()
_seen_guard = threading.Lock()


def _lock_for(chat_id: str) -> threading.Lock:
    with _chat_locks_guard:
        lk = _chat_locks.get(chat_id)
        if lk is None:
            lk = threading.Lock()
            _chat_locks[chat_id] = lk
        return lk


def handle_incoming(msg: dict) -> None:
    """Called by the listener (fast). Dispatch to the pool and return immediately."""
    message_id = msg.get("message_id")
    with _seen_guard:
        if message_id in _seen_messages:
            return
        _seen_messages.add(message_id)
        if len(_seen_messages) > 5000:  # bound the set
            _seen_messages.clear()
            _seen_messages.add(message_id)

    text = msg.get("text") or ""
    print(f"[in] chat={msg.get('chat_id')} ({msg.get('chat_type')}): {text!r}")
    _pool.submit(_process_message, msg)


def _process_message(msg: dict) -> None:
    chat_id = msg["chat_id"]
    with _lock_for(chat_id):
        try:
            _do_reply(msg)
        except Exception as e:
            print(f"[worker] error chat={chat_id}: {e}")


def _do_reply(msg: dict) -> None:
    chat_id = msg["chat_id"]
    message_id = msg.get("message_id")
    sender_open_id = msg.get("sender_id")
    text = msg.get("text") or ""
    message_type = msg.get("message_type")

    if message_type not in ("text", "post") and not text:
        # image/file/etc without rendered text — acknowledge instead of guessing
        text = (
            f"(Đồng nghiệp vừa gửi một tin nhắn dạng '{message_type}'. "
            "Hãy hỏi lại xem anh/chị cần em hỗ trợ gì.)"
        )
    if not text:
        text = "(Đồng nghiệp vừa tag bot nhưng chưa nói gì. Hãy chào và hỏi cần hỗ trợ gì.)"

    # 1) Badge "đang xử lý": thả reaction Typing lên tin nhắn của người dùng, gỡ
    # ra khi đã trả lời xong. Đây đúng là cơ chế meeting agent dùng (xem
    # `_FEISHU_REACTION_IN_PROGRESS` trong plugins/platforms/feishu/adapter.py) —
    # Lark render reaction của bot thành một badge nhỏ ngay dưới tin nhắn.
    #
    # Mặc định TẮT vì lý do vẫn còn giá trị: nếu quyền gửi tin hỏng, người dùng
    # chỉ thấy mỗi badge mà không thấy trả lời nào, tưởng bot đang nghĩ mãi. Bật
    # bằng AGENT_TYPING_BADGE=1 (đã bật trong .env ngày 07/09/2026) SAU KHI xác
    # minh đủ hai điều kiện: app có `im:message.reactions:write_only`, và bot đã
    # gửi tin thành công thật.
    show_typing_badge = _typing_badge_on()
    reaction_id = (
        lark.add_reaction(message_id, "Typing")
        if show_typing_badge and message_id
        else None
    )

    # 2) brain, under a hard timeout so one bad message can't freeze the chat.
    failed = False
    treo = False
    phien = _phien_lark(chat_id)
    try:
        import brain

        if phien != chat_id:
            # Chạy cùng gateway platform: Lark chia sự kiện ngẫu nhiên giữa các kết nối
            # của cùng app, nên thỉnh thoảng một tin rơi vào listener này (05/10/2026:
            # "ok chốt" tới đây, Mark tìm lịch sử theo `oc_…` thay vì `lark:<app>:oc_…`,
            # không thấy đề xuất vừa đưa, chạy theo lịch sử cũ). Dùng ĐÚNG phiên, kiểu
            # chat, trần thời gian và gửi bù như đường job — hai cửa, một cuộc hội thoại.
            ct = str(msg.get("chat_type") or "").strip().lower()
            kenh = {"chat_type": "p2p" if ct == "p2p" else "group"} if ct else None
            reply, ok, treo = lsr_platform._chay_co_han(
                brain.reply, text, phien, sender_open_id, kenh)
            failed = not ok and not treo
        else:
            fut = _brain_pool.submit(
                brain.reply, text, chat_id=chat_id, sender_open_id=sender_open_id
            )
            reply = fut.result(timeout=_REPLY_TIMEOUT)
    except FutureTimeout:
        print(f"[brain] TIMEOUT after {_REPLY_TIMEOUT:.0f}s chat={chat_id}")
        reply = "Xin lỗi, em xử lý hơi lâu và bị quá thời gian. Anh/chị nhắn lại giúp em nhé 🙏"
        failed = True
    except Exception as e:
        print(f"[brain] error: {e}")
        reply = "Xin lỗi, Mark gặp lỗi khi xử lý. Anh/chị thử lại giúp em nhé."
        failed = True

    # 3) Reply as the bot. If the message came from inside a thread, answer
    #    INSIDE that thread; otherwise a normal message to the chat.
    in_thread = bool(msg.get("in_thread"))
    delivered = False
    try:
        if in_thread and message_id:
            lark.reply_text(message_id, reply, in_thread=True)
            print(f"[out] chat={chat_id} (thread): {reply[:100]}")
        else:
            lark.send_text("chat_id", chat_id, reply)
            print(f"[out] chat={chat_id}: {reply[:120]}")
        delivered = True
    except Exception as e:
        print(f"[out] error ({e}); fallback to chat send")
        try:
            lark.send_text("chat_id", chat_id, reply)
            delivered = True
            print(f"[out] chat={chat_id} (fallback): {reply[:120]}")
        except Exception as e2:
            print(f"[out] fallback error: {e2}")

    # 4) Remove the progress indicator only after the outbound message has
    # actually been accepted by Lark.  On a delivery error retain a visible
    # failure marker for operators without showing an empty "typing" state.
    if reaction_id:
        lark.remove_reaction(message_id, reaction_id)
    if (failed or not delivered) and message_id:
        lark.add_reaction(message_id, "CrossMark")

    # 5) Báo lượt cho platform. Đặt CUỐI CÙNG, sau khi tin đã ra và badge đã gỡ:
    # hàm này không ném, không đợi, và tự tắt nếu chưa cấu hình — nên không có
    # đường nào nó làm hỏng một câu trả lời.
    # Quá hạn thì lượt chưa xong: `lay_luot_vua_xong` / `lay_model_vua_chay` là LẤY-VÀ-XOÁ,
    # gọi lúc này sẽ cướp số của lượt đang chạy (cùng lý do như `_mot_vong`).
    audit_record = {}
    if not treo:
        try:
            import audit
            audit_record = audit.lay_luot_vua_xong(phien)
        except Exception:
            audit_record = {}
    lsr_platform.bao_luot(
        message_id or chat_id,
        text,
        reply,
        ok=(delivered and not failed and not treo),
        audit_record=audit_record,
        model=("" if treo else lsr_platform.lay_model_vua_chay(phien)),
    )


def _phien_lark(chat_id: str) -> str:
    """Phiên hội thoại của tin Lark đến THẲNG listener này. Đang chạy cùng gateway
    platform (job poll bật) thì phải trùng phiên gateway `lark:<app_id>:<chat_id>` —
    lịch sử, ngữ cảnh platform, nhắc việc đều theo khoá đó. Không có platform (máy PC cũ)
    thì giữ `chat_id` như trước."""
    if not str(chat_id or "").startswith("oc_"):
        return chat_id
    c = lsr_platform._cau_hinh()
    if not c or not lsr_platform._job_poll_duoc_phep(c):
        return chat_id
    return f"lark:{config.app_id}:{chat_id}"


def _typing_badge_on() -> bool:
    return os.environ.get("AGENT_TYPING_BADGE", "0").strip() == "1"


def main() -> None:
    print("\n▶ Social Agent — Lark BOT (Hermes + lark-cli)")
    print(f"  Base URL:   {config.base_url}")
    print(f"  Model:      {config.agent_model} (provider={config.agent_provider})")
    print(f"  App ID:     {config.app_id}")
    print(f"  {lsr_platform.bat()}")
    print(f"  {phoenix_trace.bat()}")

    # Cửa vào thứ hai: người quản trị nhắn thử trên console thì platform tạo job.
    # Vòng này đi lấy và đưa vào ĐÚNG brain.reply mà listener Lark vẫn gọi — không
    # có bộ não thứ hai, không có nhánh xử lý riêng.
    def _tra_loi_job(text, chat_id=None, sender_open_id=None, kenh=None):
        import brain
        return brain.reply(text, chat_id=chat_id, sender_open_id=sender_open_id, kenh=kenh)

    if lsr_platform.chay_vong_job(_tra_loi_job):
        print("  Job console: đang lắng nghe (/v1/self/jobs)")

    try:
        lark.get_tenant_token()
        bot_id = lark.get_bot_open_id()
        print(f"  Bot creds:  ✅ tenant_access_token OK  (bot open_id={bot_id or '?'})")
    except Exception as e:
        print(f"  Bot creds:  ❌ {e}")
        return

    # Trạng thái badge phải HIỆN RA lúc khởi động: nó là thứ người dùng nhìn vào
    # để biết bot còn sống, mà lại bật/tắt bằng một biến .env — không in ra thì
    # lúc badge biến mất không ai biết là do tắt cờ hay do bot chết.
    if _typing_badge_on():
        print("  Badge:      ✅ reaction 'Typing' lên tin người dùng khi đang xử lý")
    else:
        print("  Badge:      ⛔ tắt (đặt AGENT_TYPING_BADGE=1 trong .env để bật)")

    # Audit: in link Base + đẩy bù những dòng mất khi lần trước tắt giữa lượt.
    # Đẩy bù ở đây (lúc khởi động) chứ không ở luồng trả lời — không được để
    # việc dọn dẹp làm chậm câu trả lời cho người dùng.
    try:
        import audit

        bu = audit.dong_bo_lai()
        link = audit.link_base()
        print(f"  Audit:      ✅ .audit/*.jsonl"
              + (f" · Base: {link}" if link else " · Base sẽ tạo ở lượt đầu")
              + (f" · đã đẩy bù {bu} dòng" if bu else ""))
    except Exception as e:  # noqa: BLE001
        print(f"  Audit:      ⚠ {type(e).__name__}: {e}")

    # background reminder ticker (fires scheduled reminders as the bot)
    try:
        import scheduler

        scheduler.start_ticker()
    except Exception as e:
        print(f"  Reminders:  ❌ {e}")

    # Việc quét nền (viec_nen.py): nhận lại việc dở của lần chạy trước — đọc tiếp đúng run
    # Apify đã ghi, không POST lại — và gửi nốt kết quả chưa nhắn được.
    try:
        import viec_nen

        print(f"  {viec_nen.khoi_dong()}")
    except Exception as e:  # noqa: BLE001
        print(f"  Việc nền:   ❌ {type(e).__name__}: {e}")

    # Nhịp nền theo dõi nguồn Wiki: quét định kỳ và BÁO, chỉ nhập khi chủ agent bấm
    # "Nhập ngay" trên console. Trước đây giao diện hứa "agent sẽ quét ở lượt kiểm
    # nguồn kế tiếp" mà không có lượt nào — dán link xong ngồi đợi mãi.
    try:
        import wiki_tu_dong

        if wiki_tu_dong.start_ticker():
            print(f"  Wiki:       ✅ quét mỗi {wiki_tu_dong.NHIP_QUET / 60:.0f}′ · "
                  f"kiểm lệnh nhập mỗi {wiki_tu_dong.NHIP_NHAP:.0f}s")
        else:
            print("  Wiki:       ⛔ tắt (thiếu khoá agent hoặc ~/.lsr/token)")
    except Exception as e:
        print(f"  Wiki:       ❌ {type(e).__name__}: {e}")

    start_listener(handle_incoming)  # blocking


if __name__ == "__main__":
    main()
