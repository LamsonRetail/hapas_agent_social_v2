"""Lịch nhắc / giao việc của Mark — NAY NẰM TRÊN PLATFORM (chủ agent chốt 08/10/2026).

VÌ SAO ĐỔI
Bản cũ giữ lịch riêng trên máy (`.tokens/reminders.json` + ticker trong run.py): nhắc đặt
trong chat thì console Platform KHÔNG thấy, không sửa, không xoá được — còn lịch đặt trên
console thì Mark lại không liệt kê được. Hai nơi giữ lịch là hai sự thật. Chủ agent muốn
MỌI lịch quản lý trên console (agent → Lịch chạy).

NAY
  • `schedule_reminder` / `list_reminders` / `cancel_reminder` gọi
    `POST /v1/self/tools/call` của Platform bằng token của CHÍNH agent (`lsr_platform`),
    body {tool, args, session_id = `lark:<app_id>:<chat_id>` của cuộc chat hiện tại,
    actor = open_id người đang nói}. Platform ghi bảng `agent_schedules` — CÙNG bảng với
    console — và tới giờ thì chính Platform gửi (mode=send) hoặc đẩy job cho Mark làm
    (mode=run, payload mang `scheduled_by` = actor để Mark xét quyền theo người đặt).
  • Platform không gọi được / trả lỗi → `tool_error` nói rõ lý do. KHÔNG BAO GIỜ lặng lẽ
    lùi về file trên máy: lịch nằm chỗ console không thấy chính là lỗi cần sửa.
  • Người đặt (actor) và cuộc chat lấy từ LƯỢT (contextvar do brain đặt), không từ đối số
    model — model không đặt được lịch "thay" người khác hay vào nhóm khác.
  • Ticker trên máy CHỈ còn gửi nốt nhắc cũ chưa xong trong `.tokens/reminders.json`
    (không tạo thêm cái mới nào). Hết nhắc cũ thì ticker chạy không.

Giờ là giờ VN (UTC+7).
"""

from __future__ import annotations

import contextvars
import datetime
import json
import re
import threading
import time
import urllib.error
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


# ───────────────────────── nhắc CŨ trên máy (chỉ đọc/huỷ/gửi nốt) ─────────────────────────
# Không còn hàm tạo nhắc trên máy: lịch mới chỉ tạo trên Platform (xem đầu file).
def list_reminders(chat_id: str | None = None) -> list[dict]:
    items = [r for r in _load() if not r.get("done")]
    if chat_id:
        items = [r for r in items if r.get("chat_id") == chat_id]
    return sorted(items, key=lambda r: r["due_ts"])


def cancel_reminder(reminder_id: str, chat_id: str | None = None) -> bool:
    """Huỷ một nhắc cũ trên máy. `chat_id` khác None = chỉ huỷ được nhắc của chat đó (tool
    trong chat luôn truyền — không ai huỷ được nhắc của nhóm khác bằng cách đoán id)."""
    with _lock:
        items = _load()
        found = False
        for r in items:
            if (r["id"] == reminder_id and not r.get("done")
                    and (chat_id is None or r.get("chat_id") == chat_id)):
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
    con = len(list_reminders())
    print(f"  Reminders: lịch mới nằm trên Platform (Lịch chạy); ticker máy chỉ gửi nốt "
          f"{con} nhắc cũ, mỗi {interval}s ✅")


# ───────────────────────── tool: lịch trên Platform ─────────────────────────
#: Chỗ người dùng xem/sửa/xoá lịch — nói kèm mọi kết quả tool để Mark chỉ đúng chỗ.
HUONG_CONSOLE = "Xem, sửa, xoá lịch trên console Platform: agent Mark → Lịch chạy."
_DUONG_GOI = "/v1/self/tools/call"
_HAN_GOI = 20
_ID_CU = re.compile(r"[0-9a-f]{10}")

# Lượt đang chạy là JOB THEO LỊCH (payload `scheduled: true`)? Khi đó không có người thật
# đang chờ để xác nhận, nên lượt tự động không được đặt/huỷ lịch — một lịch "giao việc" có
# câu "đặt lịch…" sẽ tự nhân bản mỗi ngày. brain.reply đặt cờ này mỗi lượt.
_current_scheduled: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "steven_current_scheduled", default=False
)


def set_current_scheduled(scheduled: bool) -> None:
    _current_scheduled.set(bool(scheduled))


class LoiLich(Exception):
    """Gọi lịch trên Platform hỏng. `str(e)` nói thẳng được với người dùng."""


def _la_open_id(s) -> bool:
    return bool(re.fullmatch(r"ou_[A-Za-z0-9]+", str(s or "")))


def _nguoi_dat() -> str:
    """open_id người đang nói (brain đặt mỗi lượt) — KHÔNG lấy từ đối số model."""
    try:
        import memory_store
        oid = memory_store.get_current_sender() or ""
    except Exception:  # noqa: BLE001
        return ""
    return oid if _la_open_id(oid) else ""


def phien_platform(chat_id: str | None = None) -> str:
    """session_id Platform `lark:<app_id>:<oc_…>` của cuộc chat hiện tại, "" nếu không phải
    chat Lark (job console web, bộ thử…).

    Tin tới qua gateway đã mang đúng khoá đó. Tin tới THẲNG listener khi Platform không đẩy
    job (run._phien_lark giữ `oc_…`) thì dựng lại bằng LARK_APP_ID của Mark — đúng khoá mà
    gateway dùng cho cùng cuộc chat."""
    loai, app_id, oc = _kenh(chat_id if chat_id is not None else (_current_chat.get() or ""))
    if loai == "lark_truc_tiep":
        app_id = str(getattr(config, "app_id", "") or "").strip()
    if loai == "khac" or not re.fullmatch(r"oc_[A-Za-z0-9]+", oc or ""):
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", app_id or ""):
        return ""
    return f"lark:{app_id}:{oc}"


def _goi_lich(tool: str, args: dict) -> dict:
    """Một lời gọi tool lịch trên Platform. Trả `data` khi ok; ném `LoiLich` (lý do đọc được)
    khi chưa cấu hình, không phải chat Lark, mạng hỏng hay Platform từ chối. Không lùi về
    file trên máy trong bất kỳ trường hợp nào."""
    import lsr_platform
    c = lsr_platform._cau_hinh()
    if not c:
        raise LoiLich("Mark chưa nối Platform (máy chạy thiếu cấu hình LSR_*), nên không "
                      "đặt/xem/huỷ được lịch. Lịch giờ chỉ quản lý trên console Platform.")
    phien = phien_platform()
    if not phien:
        raise LoiLich("Lịch chỉ đặt/xem/huỷ được khi đang nói với Mark trong một cuộc trò "
                      "chuyện Lark (nhóm hoặc chat riêng). " + HUONG_CONSOLE)
    than = {"tool": tool, "name": tool, "args": args, "session_id": phien,
            "actor": _nguoi_dat()}
    try:
        kq = lsr_platform._goi(c, _DUONG_GOI, than, timeout=_HAN_GOI)
    except urllib.error.HTTPError as e:
        chi_tiet = ""
        try:
            chi_tiet = e.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        raise LoiLich(f"Platform trả lỗi HTTP {e.code}"
                      + (f" ({lsr_platform._redact(chi_tiet)})" if chi_tiet else "")) from e
    except Exception as e:  # noqa: BLE001 — mạng/timeout/JSON hỏng
        raise LoiLich(f"Không gọi được Platform ({type(e).__name__}).") from e
    if not isinstance(kq, dict) or kq.get("ok") is not True:
        loi = (kq.get("error") if isinstance(kq, dict) else "") or "không rõ lý do"
        raise LoiLich(f"Platform từ chối: {lsr_platform._redact(str(loi))[:300]}")
    data = kq.get("data")
    return data if isinstance(data, dict) else {}


def _gon(s) -> str:
    return " ".join(str(s or "").split())


def _kiem_lenh_tiendo(message: str, mode: str) -> str:
    """Lịch có nội dung `/tiendo …`: kiểm cú pháp NGAY lúc đặt (sai thì sáng nào lịch cũng
    trả lời lỗi vào nhóm). "" = ổn."""
    phan = message.strip().split(None, 1)
    if not phan or phan[0].lower() != "/tiendo":
        return ""
    if mode != "run":
        return ("Lịch `/tiendo` phải là kiểu giao việc (mode=run): mode=send chỉ nhắn nguyên "
                "câu lệnh vào chat, không ai chạy nó.")
    try:
        import tien_do
        nguon, _opts = tien_do.tach_tuy_chon(phan[1] if len(phan) > 1 else "")
    except ValueError as e:
        return f"Câu /tiendo chưa đúng: {e}"
    if "table=tbl" not in nguon:
        return ("Lịch /tiendo cần link Base chỉ đúng một bảng (có ?table=tbl…) — mở đúng bảng "
                "trên Base rồi copy link.")
    return ""


def _lich_trung(message: str, when: str) -> dict | None:
    """Lịch đang bật trong chat này có CÙNG nội dung và CÙNG lần chạy kế (ngày giờ)? — để
    model gọi lại (thử lại, người dùng nhắc lại) không đẻ hai lịch giống hệt. Không parse
    được `when` thì không so (Platform tự kiểm)."""
    try:
        moc = datetime.datetime.fromtimestamp(_parse_when(when), VN_TZ).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return None
    for r in _goi_lich("list_reminders", {}).get("reminders") or []:
        if (isinstance(r, dict) and _gon(r.get("message")) == _gon(message)
                and str(r.get("due_at_vn") or "").strip() == moc):
            return r
    return None


SCHEDULE_SCHEMA = {
    "name": "schedule_reminder",
    "description": (
        "Đặt LỊCH trên Platform (console thấy, sửa, xoá được ở agent → Lịch chạy) cho CUỘC "
        "CHAT HIỆN TẠI; người đặt = người đang nói (code tự lấy, không truyền).\n"
        "Hai kiểu `mode`:\n"
        "• send (mặc định): tới giờ gửi NGUYÊN VĂN `message` vào chat này — nhắc đơn giản "
        "('14h nhắc họp').\n"
        "• run: tới giờ Mark TỰ LÀM việc trong `message` như người đặt vừa nhắn, rồi gửi kết "
        "quả; quyền đọc dữ liệu xét theo người đặt. `message` phải là yêu cầu tự đủ nghĩa.\n"
        "NHẮC TIẾN ĐỘ / VIỆC QUÁ HẠN MỖI SÁNG: mode=run, recurrence=daily, message="
        "`/tiendo <link Base có ?table=tbl…>` (thêm ` cua_toi=co` khi họ nói 'việc của tôi'; "
        "thêm ` tag=khong` nếu không muốn tag PIC).\n"
        "BẮT BUỘC TRƯỚC KHI GỌI: nói lại giờ + ngày lặp, nội dung (nhắn câu gì / làm việc gì), "
        "cuộc chat nhận, rồi chờ người dùng đồng ý. Xong thì báo id + giờ chạy kế và nói họ xem/"
        "sửa/xoá được trên console (Lịch chạy). Lỗi thì báo nguyên lý do, KHÔNG nói đã đặt."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "message": {"type": "string",
                        "description": "mode=send: câu sẽ gửi nguyên văn. mode=run: việc Mark sẽ "
                                       "làm (vd `/tiendo <link Base?table=tbl…>`)."},
            "when": {"type": "string",
                     "description": "Lần chạy đầu, giờ VN: 'HH:MM' (qua giờ thì mai), "
                                    "'+30m'/'+2h'/'+1d', 'YYYY-MM-DD HH:MM' hoặc 'dd/mm HH:MM'."},
            "recurrence": {"type": "string",
                           "description": "none (một lần, mặc định) | daily | weekly | monthly. "
                                          "Nhiều ngày mỗi tuần = daily + `days`."},
            "days": {"type": "string",
                     "description": "Chỉ chạy các ngày này (dùng với daily): weekdays (T2–T6) | "
                                    "weekends | '2,3,4' (1=T2…7=CN). Bỏ trống = mọi ngày."},
            "mode": {"type": "string", "enum": ["send", "run"],
                     "description": "send = nhắn đúng câu; run = tới giờ Mark tự làm việc."},
        },
        "required": ["message", "when"],
    },
}


def _handle_schedule(args: dict, **_kw) -> str:
    a = args or {}
    message = str(a.get("message") or "").strip()
    when = str(a.get("when") or "").strip()
    if not message:
        return tool_error("Thiếu `message` (câu sẽ gửi hoặc việc sẽ làm).")
    if not when:
        return tool_error("Thiếu `when` (thời điểm chạy đầu).")
    if _current_scheduled.get():
        return tool_error("Lượt này đang chạy THEO LỊCH (không có người đang chờ xác nhận) "
                          "nên không đặt thêm lịch. " + HUONG_CONSOLE)
    mode = str(a.get("mode") or "send").strip().lower()
    if mode not in ("send", "run"):
        return tool_error("`mode` chỉ nhận send (nhắn đúng câu) hoặc run (tới giờ Mark tự "
                          "làm việc).")
    loi = _kiem_lenh_tiendo(message, mode)
    if loi:
        return tool_error(loi)
    if mode == "run" and not _nguoi_dat():
        # Lịch run không có người đặt thì tới giờ Mark phải từ chối mọi việc cần quyền.
        return tool_error("Lịch giao việc (mode=run) cần biết ai đặt để tới giờ xét quyền "
                          "theo người đó, mà lượt này chưa có danh tính Lark của bạn. Nhắn "
                          "Mark trong Lark, hoặc đặt trên console → Lịch chạy.")
    gui: dict = {"message": message, "when": when, "mode": mode}
    rc = str(a.get("recurrence") or "").strip()
    if rc:
        gui["recurrence"] = rc
    if a.get("days") not in (None, "", []):
        gui["days"] = a.get("days")
    try:
        trung = _lich_trung(message, when)
    except LoiLich:
        trung = None            # xem danh sách hỏng thì lời gọi tạo bên dưới tự báo lỗi
    if trung:
        return tool_result(
            success=True, da_co_san=True, id=trung.get("id"), message=trung.get("message"),
            recurrence=trung.get("recurrence"), due_at_vn=trung.get("due_at_vn"),
            note="Cuộc chat này ĐÃ có lịch giống hệt (cùng nội dung, cùng giờ chạy kế) — "
                 "không tạo thêm. Báo người dùng lịch sẵn có này.",
            xem_sua_xoa=HUONG_CONSOLE)
    try:
        d = _goi_lich("schedule_reminder", gui)
    except LoiLich as e:
        return tool_error(f"CHƯA đặt được lịch: {e} Nếu lỗi là mạng/timeout thì gọi "
                          "list_reminders xem lịch đã có chưa trước khi đặt lại.")
    return tool_result(
        success=True, id=d.get("id"), message=d.get("message", message),
        mode=d.get("mode", mode), recurrence=d.get("recurrence"), days=d.get("days"),
        due_at_vn=d.get("due_at_vn"), note=d.get("note"), xem_sua_xoa=HUONG_CONSOLE)


LIST_SCHEMA = {
    "name": "list_reminders",
    "description": ("Liệt kê lịch đang bật của Mark trong CUỘC CHAT HIỆN TẠI (lấy từ Platform — "
                    "cùng danh sách console thấy ở Lịch chạy). Dùng trước khi huỷ để lấy id."),
    "parameters": {"type": "object", "properties": {}},
}


def _handle_list(args: dict, **_kw) -> str:
    try:
        d = _goi_lich("list_reminders", {})
    except LoiLich as e:
        return tool_error(f"Không xem được lịch: {e}")
    rows = [r for r in (d.get("reminders") or []) if isinstance(r, dict)]
    cu = [{"id": r["id"], "due": _fmt(r["due_ts"]), "recurrence": r.get("recurrence"),
           "message": r.get("message")}
          for r in list_reminders(_current_chat.get() or "")] if _current_chat.get() else []
    them = ({"nhac_cu_tren_may": cu,
             "ghi_chu_nhac_cu": "Nhắc đặt trước 08/10/2026, còn nằm trên máy Mark (console "
                                "không thấy); huỷ bằng cancel_reminder với id chữ."}
            if cu else {})
    return tool_result(success=True, count=len(rows), reminders=rows, **them,
                       xem_sua_xoa=HUONG_CONSOLE)


CANCEL_SCHEMA = {
    "name": "cancel_reminder",
    "description": ("Huỷ một lịch của CUỘC CHAT HIỆN TẠI theo id lấy từ list_reminders. Nói lại "
                    "lịch sẽ huỷ và chờ người dùng đồng ý trước khi gọi."),
    "parameters": {
        "type": "object",
        "properties": {"id": {"type": "string",
                              "description": "id lịch (số) từ list_reminders; nhắc cũ trên máy "
                                             "có id chữ 10 ký tự."}},
        "required": ["id"],
    },
}


def _handle_cancel(args: dict, **_kw) -> str:
    rid = str((args or {}).get("id") if (args or {}).get("id") is not None else "").strip()
    if not rid:
        return tool_error("Thiếu `id` — gọi list_reminders để lấy.")
    if _current_scheduled.get():
        return tool_error("Lượt này đang chạy THEO LỊCH nên không huỷ lịch. " + HUONG_CONSOLE)
    if rid.isdigit():
        try:
            d = _goi_lich("cancel_reminder", {"id": int(rid)})
        except LoiLich as e:
            return tool_error(f"CHƯA huỷ được lịch #{rid}: {e}")
        return tool_result(success=True, cancelled=d.get("cancelled", int(rid)),
                           xem_sua_xoa=HUONG_CONSOLE)
    chat = _current_chat.get()
    if _ID_CU.fullmatch(rid) and chat and cancel_reminder(rid, chat_id=chat):
        return tool_result(success=True, cancelled=rid, nhac_cu_tren_may=True)
    return tool_error(f"Không thấy lịch id={rid[:40]} trong cuộc này — gọi list_reminders để "
                      "lấy đúng id.")


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
