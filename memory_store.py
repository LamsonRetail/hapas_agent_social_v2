"""Persistent memory for Mark — per-chat history + per-USER long-term notes.

Two stores, both on disk under .tokens/ so they survive restarts:

  history/<chat_id>.json  — recent conversation turns per chat (context memory)
  memory/<open_id>.md     — durable facts about a specific colleague (profile
                            memory), isolated PER USER so info never leaks
                            between people (unlike Hermes' global MEMORY.md).

Also registers a `remember_about_user` tool so the brain can save a durable
fact about whoever it is currently talking to. The "current user" is set by
brain.py right before each run via set_current_sender().
"""

from __future__ import annotations

import contextvars
import datetime
import json
import re
import threading
from pathlib import Path

from config import config

from tools.registry import registry, tool_error, tool_result  # type: ignore

_BASE = config.token_file.parent
_HIST_DIR = _BASE / "history"
_MEM_DIR = _BASE / "memory"
_lock = threading.Lock()

MAX_HISTORY = 20  # turns kept per chat (10 user/assistant pairs)
_MEM_CHAR_CAP = 4000  # keep a user's memory file bounded

# Set per-message by brain.py so the remember tool knows who it's about.
# A ContextVar (NOT a module global or thread-local) is REQUIRED for concurrency:
# each message is handled in its own worker thread AND the Hermes agent runs tool
# handlers in a ThreadPoolExecutor, propagating state via contextvars.copy_context()
# (see tools/thread_context.py). A plain global would let two concurrent users
# clobber each other's "current sender"; a thread-local would not reach the
# agent's tool-executor threads. ContextVar satisfies both.
_current_sender: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "steven_current_sender", default=None
)


def set_current_sender(open_id: str | None) -> None:
    _current_sender.set(open_id)


def get_current_sender() -> str | None:
    """open_id của người đang nhắn, cho tool khác dùng (vd cấp quyền file vừa tạo)."""
    return _current_sender.get()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "unknown")[:120]


# ───────────────────────── per-chat history ─────────────────────────
def _hist_path(chat_id: str) -> Path:
    return _HIST_DIR / f"{_safe(chat_id)}.json"


def load_history(chat_id: str) -> list[dict]:
    try:
        return json.loads(_hist_path(chat_id).read_text(encoding="utf-8"))
    except Exception:
        return []


def append_turns(chat_id: str, turns: list[dict]) -> None:
    """Append turns [{role, text, sender?}] and trim to MAX_HISTORY.

    Lượt rỗng / chỉ khoảng trắng KHÔNG BAO GIỜ được ghi: Anthropic từ chối cả request
    khi lịch sử có một khối chữ rỗng, và lịch sử bẩn làm hỏng mọi lượt sau của chat.
    """
    turns = [t for t in turns or []
             if isinstance(t, dict) and isinstance(t.get("text"), str)
             and t["text"].strip()]
    if not turns:
        return
    with _lock:
        hist = load_history(chat_id) + turns
        hist = hist[-MAX_HISTORY:]
        _HIST_DIR.mkdir(parents=True, exist_ok=True)
        _hist_path(chat_id).write_text(
            json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8"
        )


# ───────────────────────── per-user long-term memory ─────────────────────────
def _mem_path(open_id: str) -> Path:
    return _MEM_DIR / f"{_safe(open_id)}.md"


def load_user_memory(open_id: str | None) -> str:
    if not open_id:
        return ""
    try:
        return _mem_path(open_id).read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def append_user_memory(open_id: str, note: str) -> None:
    note = (note or "").strip()
    if not open_id or not note:
        return
    with _lock:
        _MEM_DIR.mkdir(parents=True, exist_ok=True)
        p = _mem_path(open_id)
        today = datetime.date.today().isoformat()
        existing = ""
        try:
            existing = p.read_text(encoding="utf-8")
        except Exception:
            pass
        updated = (existing + f"- ({today}) {note}\n").strip()
        # keep only the most recent lines within the cap
        if len(updated) > _MEM_CHAR_CAP:
            lines = updated.splitlines()
            while lines and len("\n".join(lines)) > _MEM_CHAR_CAP:
                lines.pop(0)
            updated = "\n".join(lines)
        p.write_text(updated + "\n", encoding="utf-8")


# ───────────────────────── remember tool ─────────────────────────
REMEMBER_SCHEMA = {
    "name": "remember_about_user",
    "description": (
        "Lưu MỘT thông tin BỀN VỮNG về người đang nói chuyện với bạn — vd vai trò/"
        "chức vụ, phòng ban, cách xưng hô ưa thích, sở thích, việc định kỳ, ràng buộc "
        "thời gian. Dùng khi phát hiện thông tin đáng nhớ LÂU DÀI để lần sau phục vụ tốt "
        "hơn. KHÔNG lưu chuyện vặt nhất thời. Mỗi lần chỉ lưu 1 ý ngắn gọn."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "note": {
                "type": "string",
                "description": "Thông tin cần nhớ về người này, 1 câu ngắn gọn.",
            }
        },
        "required": ["note"],
    },
}


def _handle_remember(args: dict, **kwargs) -> str:
    note = (args.get("note") or "").strip()
    if not note:
        return tool_error("Thiếu `note` (nội dung cần nhớ).")
    sender = _current_sender.get()
    if not sender:
        return tool_error("Chưa xác định được người dùng hiện tại để gắn ghi nhớ.")
    append_user_memory(sender, note)
    return tool_result(success=True, remembered=note, about=sender)


def register() -> None:
    try:
        registry.register(
            name="remember_about_user",
            toolset="steven_memory",
            schema=REMEMBER_SCHEMA,
            handler=_handle_remember,
            requires_env=[],
            is_async=False,
            description="Lưu thông tin bền vững về người đang nói chuyện (per-user)",
            emoji="\U0001f9e0",
            override=True,
        )
    except Exception as e:
        print(f"[memory_store] register warning: {e}")


register()
