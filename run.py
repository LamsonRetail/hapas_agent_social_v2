"""Social Agent: run the Lark BOT agent.

Receives messages pushed to the app bot over lark-cli's event bus
(`im.message.receive_v1`), sends each new message to the Hermes brain
(gpt-5.4 via openai-codex), and replies AS the bot.

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

    # 1) ack with a "Typing" reaction on the user's message (removed on success;
    #    a "CrossMark" is added on failure).
    reaction_id = lark.add_reaction(message_id, "Typing") if message_id else None

    # 2) brain, under a hard timeout so one bad message can't freeze the chat.
    failed = False
    try:
        import brain

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
        reply = f"Xin lỗi, em gặp lỗi khi xử lý: {e}"
        failed = True

    # 3) clear the typing badge (mark failure if the brain errored)
    if reaction_id:
        lark.remove_reaction(message_id, reaction_id)
    if failed and message_id:
        lark.add_reaction(message_id, "CrossMark")

    # 4) reply, as the bot. If the message came from inside a thread, answer
    #    INSIDE that thread; otherwise a normal message to the chat.
    in_thread = bool(msg.get("in_thread"))
    try:
        if in_thread and message_id:
            lark.reply_text(message_id, reply, as_user=False, in_thread=True)
            print(f"[out] chat={chat_id} (thread): {reply[:100]}")
        else:
            lark.send_text("chat_id", chat_id, reply, as_user=False)
            print(f"[out] chat={chat_id}: {reply[:120]}")
    except Exception as e:
        print(f"[out] error ({e}); fallback to chat send")
        try:
            lark.send_text("chat_id", chat_id, reply, as_user=False)
        except Exception as e2:
            print(f"[out] fallback error: {e2}")


def main() -> None:
    print("\n▶ Social Agent — Lark BOT (Hermes + lark-cli)")
    print(f"  Base URL:   {config.base_url}")
    print(f"  Model:      {config.agent_model} (provider={config.agent_provider})")
    print(f"  App ID:     {config.app_id}")

    try:
        lark.get_tenant_token()
        bot_id = lark.get_bot_open_id()
        print(f"  Bot creds:  ✅ tenant_access_token OK  (bot open_id={bot_id or '?'})")
    except Exception as e:
        print(f"  Bot creds:  ❌ {e}")
        return

    # background reminder ticker (fires scheduled reminders as the bot)
    try:
        import scheduler

        scheduler.start_ticker()
    except Exception as e:
        print(f"  Reminders:  ❌ {e}")

    start_listener(handle_incoming)  # blocking


if __name__ == "__main__":
    main()
