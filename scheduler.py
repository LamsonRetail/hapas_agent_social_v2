"""Self-contained reminder / scheduler for Mark.

Hermes' own cron is tightly coupled to its gateway (delivery, sessions, platform
adapters) — and that gateway belongs to the meeting agent — so this standalone
runner keeps a tiny, robust scheduler of its own:

  .tokens/reminders.json  — list of reminders, persisted (survive restarts)

The brain calls the `schedule_reminder` tool to create one (targeting the CURRENT
chat by default). run.py runs a background ticker that, when a reminder is due,
sends its message to the target chat as the bot, then marks it done (or
reschedules if it recurs daily).

Times are interpreted in Vietnam local time (UTC+7) and stored as epoch seconds.
"""

from __future__ import annotations

import contextvars
import datetime
import json
import re
import threading
import time
import uuid
from pathlib import Path

import lark_client as lark
from config import config

from tools.registry import registry, tool_error, tool_result  # type: ignore

VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
_FILE = config.token_file.parent / "reminders.json"
_lock = threading.Lock()

# Set per-message by brain so a reminder defaults to the current chat. Uses a
# ContextVar (not a global) so concurrent messages from different chats never
# clobber each other's target chat — see the matching note in memory_store.py.
_current_chat: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "steven_current_chat", default=None
)


def set_current_chat(chat_id: str | None) -> None:
    _current_chat.set(chat_id)


# ───────────────────────── storage ─────────────────────────
def _load() -> list[dict]:
    try:
        return json.loads(_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")


# ───────────────────────── time parsing ─────────────────────────
def _parse_when(when: str) -> float:
    """Parse `when` into an epoch (seconds). Accepts:

    - '+30m' / '+2h' / '+45s'         (relative to now)
    - 'HH:MM'                          (today in VN time; if past → tomorrow)
    - 'YYYY-MM-DD HH:MM' / ISO         (absolute, VN time)
    """
    when = (when or "").strip()
    now = datetime.datetime.now(VN_TZ)

    m = re.fullmatch(r"\+\s*(\d+)\s*([smh])", when, re.IGNORECASE)
    if m:
        n = int(m.group(1))
        unit = m.group(2).lower()
        delta = {"s": 1, "m": 60, "h": 3600}[unit] * n
        return (now + datetime.timedelta(seconds=delta)).timestamp()

    m = re.fullmatch(r"(\d{1,2}):(\d{2})", when)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        return target.timestamp()

    # absolute date-time (accept space or 'T')
    norm = when.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M", "%d/%m %H:%M"):
        try:
            dt = datetime.datetime.strptime(norm, fmt).replace(tzinfo=VN_TZ)
            if "%Y" not in fmt:  # e.g. dd/mm without year → this year
                dt = dt.replace(year=now.year)
            return dt.timestamp()
        except ValueError:
            continue
    raise ValueError(
        f"Không hiểu thời điểm {when!r}. Dùng 'HH:MM', '+30m', '+2h', "
        f"hoặc 'YYYY-MM-DD HH:MM' (giờ VN)."
    )


def _fmt(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, VN_TZ).strftime("%Y-%m-%d %H:%M")


# ───────────────────────── public API ─────────────────────────
def add_reminder(chat_id: str, message: str, when: str, recurrence: str = "none", created_by: str | None = None) -> dict:
    due = _parse_when(when)
    item = {
        "id": uuid.uuid4().hex[:10],
        "chat_id": chat_id,
        "message": message,
        "due_ts": due,
        "recurrence": (recurrence or "none").lower(),
        "created_by": created_by,
        "created_at": time.time(),
        "done": False,
    }
    with _lock:
        items = _load()
        items.append(item)
        _save(items)
    return item


def list_reminders(chat_id: str | None = None) -> list[dict]:
    items = [r for r in _load() if not r.get("done")]
    if chat_id:
        items = [r for r in items if r.get("chat_id") == chat_id]
    return sorted(items, key=lambda r: r["due_ts"])


def cancel_reminder(reminder_id: str) -> bool:
    with _lock:
        items = _load()
        found = False
        for r in items:
            if r["id"] == reminder_id and not r.get("done"):
                r["done"] = True
                found = True
        _save(items)
    return found


def _fire_due(now: float | None = None) -> int:
    """Send any due reminders as the bot. Returns how many fired."""
    now = now or time.time()
    fired = 0
    with _lock:
        items = _load()
        dirty = False
        for r in items:
            if r.get("done") or r["due_ts"] > now:
                continue
            try:
                lark.send_text("chat_id", r["chat_id"], r["message"])
                fired += 1
                print(f"[reminder] fired {r['id']} → {r['chat_id']}: {r['message'][:60]}")
            except Exception as e:
                print(f"[reminder] send error {r['id']}: {e}")
                continue  # leave for retry next tick
            if r.get("recurrence") == "daily":
                r["due_ts"] += 86400  # next day, keep active
            else:
                r["done"] = True
            dirty = True
        if dirty:
            _save(items)
    return fired


def start_ticker(interval: int = 20) -> None:
    """Start a daemon thread that fires due reminders every `interval` seconds."""

    def _loop():
        while True:
            try:
                _fire_due()
            except Exception as e:
                print(f"[reminder] ticker error: {e}")
            time.sleep(interval)

    t = threading.Thread(target=_loop, name="reminder-ticker", daemon=True)
    t.start()
    print(f"  Reminders: ticker chạy mỗi {interval}s ✅")


# ───────────────────────── tool ─────────────────────────
SCHEDULE_SCHEMA = {
    "name": "schedule_reminder",
    "description": (
        "Đặt một lời nhắc/hẹn giờ. Đến giờ, bot sẽ TỰ gửi `message` vào cuộc trò "
        "chuyện hiện tại (hoặc `chat_id` chỉ định). Dùng khi người dùng nhờ 'nhắc...', "
        "'đến 13h30 gửi nhóm...', 'mai nhắc tôi...'. `when` nhận: 'HH:MM' (hôm nay giờ VN, "
        "nếu đã qua thì mai), '+30m'/'+2h', hoặc 'YYYY-MM-DD HH:MM'. `recurrence`='daily' để "
        "lặp mỗi ngày. LƯU Ý: nội dung `message` là thứ SẼ được gửi đi nguyên văn — hãy soạn "
        "sẵn cho đúng. Trước khi đặt, nên xác nhận lại thời điểm + nội dung với người dùng."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "Nội dung sẽ gửi khi đến giờ (nguyên văn)."},
            "when": {"type": "string", "description": "Thời điểm: 'HH:MM' | '+30m' | '+2h' | 'YYYY-MM-DD HH:MM' (giờ VN)."},
            "recurrence": {"type": "string", "description": "'none' (mặc định) hoặc 'daily' để lặp hằng ngày."},
        },
        "required": ["message", "when"],
    },
}


def _handle_schedule(args: dict, **kwargs) -> str:
    message = (args.get("message") or "").strip()
    when = (args.get("when") or "").strip()
    recurrence = (args.get("recurrence") or "none").strip().lower()
    if not message:
        return tool_error("Thiếu `message` (nội dung sẽ gửi).")
    if not when:
        return tool_error("Thiếu `when` (thời điểm).")
    current_chat = _current_chat.get()
    if not current_chat:
        return tool_error("Chưa xác định được cuộc trò chuyện đích để đặt nhắc.")
    try:
        item = add_reminder(current_chat, message, when, recurrence, created_by=kwargs.get("sender"))
    except ValueError as e:
        return tool_error(str(e))
    return tool_result(
        success=True,
        id=item["id"],
        due=_fmt(item["due_ts"]),
        recurrence=item["recurrence"],
        message=message,
    )


LIST_SCHEMA = {
    "name": "list_reminders",
    "description": "Liệt kê các lời nhắc đang chờ trong cuộc trò chuyện hiện tại.",
    "parameters": {"type": "object", "properties": {}},
}


def _handle_list(args: dict, **kwargs) -> str:
    rows = [
        {"id": r["id"], "due": _fmt(r["due_ts"]), "recurrence": r["recurrence"], "message": r["message"]}
        for r in list_reminders(_current_chat.get())
    ]
    return tool_result(success=True, count=len(rows), reminders=rows)


CANCEL_SCHEMA = {
    "name": "cancel_reminder",
    "description": "Hủy một lời nhắc theo id (lấy id từ list_reminders).",
    "parameters": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "id của lời nhắc cần hủy."}},
        "required": ["id"],
    },
}


def _handle_cancel(args: dict, **kwargs) -> str:
    rid = (args.get("id") or "").strip()
    if not rid:
        return tool_error("Thiếu `id`.")
    ok = cancel_reminder(rid)
    return tool_result(success=ok, cancelled=rid) if ok else tool_error(f"Không thấy lời nhắc id={rid}.")


def register() -> None:
    for name, schema, handler in (
        ("schedule_reminder", SCHEDULE_SCHEMA, _handle_schedule),
        ("list_reminders", LIST_SCHEMA, _handle_list),
        ("cancel_reminder", CANCEL_SCHEMA, _handle_cancel),
    ):
        try:
            registry.register(
                name=name,
                toolset="steven_reminders",
                schema=schema,
                handler=handler,
                requires_env=[],
                is_async=False,
                description=schema["description"][:80],
                emoji="\U0001f514",
                override=True,
            )
        except Exception as e:
            print(f"[scheduler] register warning ({name}): {e}")


register()
