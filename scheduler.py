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


def get_current_chat() -> str | None:
    """Chat của lượt đang chạy — việc nền (viec_nen) ghi lại để biết gửi kết quả về đâu."""
    return _current_chat.get()


# "p2p" | "group" | None (không biết — vd tin Lark trực tiếp qua run.py). Việc nền dùng để
# chỉ cho "người yêu cầu" xem/huỷ việc của mình khi đang ở chat RIÊNG (review 02/10/2026).
_current_chat_type: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "steven_current_chat_type", default=None
)


def set_current_chat_type(chat_type: str | None) -> None:
    _current_chat_type.set(chat_type)


def get_current_chat_type() -> str | None:
    return _current_chat_type.get()


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


# ───────────────────────── gửi ─────────────────────────
# Sự cố 04/10/2026: nhắc đặt từ chat Lark đi qua gateway platform mang chat key
# `lark:<app_id>:<oc_…>`. Bản cũ đưa nguyên chuỗi đó cho `lark.send_text` → Lark trả
# 230001 "invalid receive_id", và vì MỌI lỗi đều "để lần sau thử lại" nên nhắc
# 6cbd4598d1 của người dùng thật thử 4.271 lần (mỗi 20 giây), không bao giờ tới.
# Nay: tách chat key giống `viec_nen.kenh_hien_tai`, gửi đúng đường việc nền dùng; lỗi
# vĩnh viễn thì dừng hẳn, lỗi tạm thì lùi dần và có trần.

#: Trễ quá chừng này thì không gửi nữa mà đánh dấu thất bại. Nhắc trễ 1–2 ngày vẫn có
#: ích (người dùng biết việc mình hẹn đã qua, tự xử lý); trễ cả tuần thì gần như chắc
#: chắn vô nghĩa, lại dễ làm người nhận hoang mang.
_TRE_TOI_DA = 7 * 86400
#: Trễ hơn chừng này mới ghi chú "nhắc trễ" (nhịp 20 giây + khởi động lại là bình thường).
_TRE_GHI_CHU = 10 * 60
#: Lỗi tạm thời: thử tối đa bấy nhiêu lần, lùi 30s, 60s, 120s… trần 1 giờ (≈3 giờ tổng).
_THU_TOI_DA = 10
_LUI_DAU = 30
_LUI_TRAN = 3600

#: Dấu hiệu Lark từ chối VĨNH VIỄN (thử lại cũng vô ích): sai receive_id, chat không
#: còn, bot không ở trong chat. Qua gateway thì platform chỉ chuyển `msg` (không có mã),
#: nên dò cả chữ lẫn mã.
_DAU_VINH_VIEN = (
    "230001", "230002", "232009", "232011",
    "invalid receive_id", "not in the chat", "not in chat", "bot is not in",
    "chat not found", "chat not exist", "chat does not exist", "chat_id not exist",
    "dissolved", "disbanded",
)


class LoiGui(Exception):
    """Gửi nhắc hỏng. `vinh_vien` = thử lại cũng không khá hơn."""

    def __init__(self, chi_tiet: str, vinh_vien: bool):
        super().__init__(chi_tiet)
        self.vinh_vien = vinh_vien


def _kenh(chat_id: str) -> tuple[str, str, str]:
    """Tách chat key như `viec_nen.kenh_hien_tai` -> (loại, app_id, oc)."""
    chat_id = chat_id or ""
    if chat_id.startswith("lark:"):
        phan = chat_id.split(":", 2)
        if len(phan) == 3 and phan[2]:
            return "lark_gateway", phan[1], phan[2]
    elif chat_id.startswith("oc_"):
        return "lark_truc_tiep", "", chat_id
    return "khac", "", ""


def _la_vinh_vien(chi_tiet: str) -> bool:
    t = (chi_tiet or "").lower()
    return any(d in t for d in _DAU_VINH_VIEN)


def _gui(chat_id: str, text: str, uid: str) -> None:
    """Gửi `text` vào chat của nhắc, qua đúng đường việc nền dùng. Ném `LoiGui`."""
    loai, app_id, oc = _kenh(chat_id)
    if loai == "khac":
        raise LoiGui(f"chat {chat_id[:24]!r} không có kênh Lark để tự nhắn", True)
    try:
        if loai == "lark_gateway":
            import lsr_platform
            lsr_platform.gui_lark(oc, text, app_id, uuid=uid)
        else:
            lark.send_text("chat_id", oc, text, uuid=uid)
    except Exception as e:  # noqa: BLE001
        chi_tiet = f"{type(e).__name__}: {e}"
        ma = getattr(e, "code", None)            # urllib HTTPError từ platform
        if isinstance(ma, int):
            try:
                chi_tiet += " " + e.read().decode("utf-8", "replace")[:300]  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        # Platform trả 4xx (trừ 401 khoá/408/429 quá tải) = yêu cầu sai, không tự khỏi.
        # 502 "Lark từ chối: …" thì phải nhìn nội dung mới biết.
        vinh_vien = _la_vinh_vien(chi_tiet) or (
            isinstance(ma, int) and 400 <= ma < 500 and ma not in (401, 408, 429))
        raise LoiGui(chi_tiet[:400], vinh_vien) from e


def _ngay_ke_tiep(due: float, now: float) -> float:
    while due <= now:
        due += 86400
    return due


def _xu_ly(r: dict, now: float) -> tuple[dict, bool]:
    """Xử lý MỘT nhắc đến hạn. -> (các trường cần ghi đè, đã gửi?). In log chỉ khi trạng
    thái đổi (gửi được / bắt đầu thử lại / thất bại), không in mỗi nhịp."""
    rid, due = r["id"], float(r["due_ts"])
    hang_ngay = r.get("recurrence") == "daily"
    tre = now - due
    xoa_thu = {"so_lan_thu": 0, "thu_lai_ts": None, "loi": None}
    if tre > _TRE_TOI_DA:
        if hang_ngay:
            ke = _ngay_ke_tiep(due, now)
            print(f"[reminder] {rid}: lỡ quá 7 ngày, bỏ các lần lỡ, hẹn lần kế "
                  f"{_fmt(ke)}", flush=True)
            return {"due_ts": ke, **xoa_thu}, False
        print(f"[reminder] {rid}: THẤT BẠI — trễ {tre / 86400:.1f} ngày (quá 7), "
              "không gửi muộn nữa", flush=True)
        return {"done": True, "trang_thai": "that_bai", "that_bai_luc": now,
                "loi": ((r.get("loi") or "") + " | quá hạn 7 ngày").strip(" |")}, False
    text = r["message"]
    if tre > _TRE_GHI_CHU:
        text = f"(nhắc trễ do lỗi gửi — hẹn lúc {_fmt(due)}) {text}"
    try:
        _gui(r["chat_id"], text, f"nhac-{rid}-{int(due)}")
    except LoiGui as e:
        lan = int(r.get("so_lan_thu") or 0) + 1
        if e.vinh_vien or lan >= _THU_TOI_DA:
            ly_do = "lỗi vĩnh viễn" if e.vinh_vien else f"hết {_THU_TOI_DA} lần thử"
            print(f"[reminder] {rid}: THẤT BẠI ({ly_do}), dừng thử: {e}", flush=True)
            return {"done": True, "trang_thai": "that_bai", "that_bai_luc": now,
                    "so_lan_thu": lan, "loi": str(e)}, False
        if lan == 1:
            print(f"[reminder] {rid}: gửi lỗi tạm, sẽ thử lại tối đa {_THU_TOI_DA} lần "
                  f"(lùi dần): {e}", flush=True)
        lui = min(_LUI_DAU * 2 ** (lan - 1), _LUI_TRAN)
        return {"so_lan_thu": lan, "thu_lai_ts": now + lui, "loi": str(e)}, False
    ghi_tre = f" (trễ {tre / 60:.0f} phút)" if tre > _TRE_GHI_CHU else ""
    print(f"[reminder] fired {rid} → {r['chat_id'][:40]}{ghi_tre}: "
          f"{r['message'][:60]}", flush=True)
    if hang_ngay:
        return {"due_ts": _ngay_ke_tiep(due, now), **xoa_thu}, True
    return {"done": True, "trang_thai": "da_gui", "gui_luc": now, **xoa_thu}, True


def _fire_due(now: float | None = None) -> int:
    """Send any due reminders as the bot. Returns how many fired.

    Gọi mạng NGOÀI khoá (gateway có thể mất tới 20 giây) để đặt/huỷ nhắc không bị
    chặn; ghi kết quả theo id dưới khoá, bỏ qua nhắc bị huỷ trong lúc đang gửi."""
    now = now or time.time()
    with _lock:
        den = [dict(r) for r in _load()
               if not r.get("done") and r["due_ts"] <= now
               and float(r.get("thu_lai_ts") or 0) <= now]
    fired = 0
    for r in den:
        sua, da_gui = _xu_ly(r, now)
        fired += int(da_gui)
        with _lock:
            items = _load()
            for x in items:
                if x.get("id") == r["id"] and not x.get("done"):
                    x.update(sua)
                    _save(items)
                    break
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
