"""Đồng hồ của MỘT lượt trả lời: nhắc model gói lại, rồi chặn tool mới trước trần cứng.

Vì sao: từng tool đã có hạn chót riêng (cào ~135 giây), nhưng một lượt có thể gọi NHIỀU
tool nối nhau. 02/10/2026 một lượt gọi 24 tool (soi tài khoản, thư viện QC, đọc web…)
mất 417 giây — sát trần 480 giây của vòng job (`lsr_platform._HAN_TRA_LOI`), quá trần là
người dùng nhận câu xin lỗi thay vì câu trả lời.

Hai mốc, tính từ lúc `brain.reply` bắt đầu lượt:
- NHẮC (mặc định 300 giây): tool vẫn chạy, kết quả kèm một dòng nhắc model tổng kết bằng
  dữ liệu đã có. Model tự quyết — đây là gợi ý, không phải luật hành vi.
- CHẶN (mặc định 400 giây): tool mới không chạy, trả lỗi "hết thời gian của lượt" để
  model buộc phải viết trả lời trước trần. Đây là giới hạn THỜI GIAN bảo vệ vòng job,
  không phải luật nghiệp vụ.

Mốc chỉnh qua env (`LSR_LUOT_NHAC_GIAY`, `LSR_LUOT_CHAN_GIAY`); mốc chặn luôn chừa ít nhất
60 giây trước trần để model kịp viết. Ngoài lượt trả lời (việc nền, nhắc việc, bộ thử)
đồng hồ không chạy → không đụng gì.
"""
from __future__ import annotations

import contextvars
import json
import os
import time

_BAT_DAU: contextvars.ContextVar = contextvars.ContextVar("lsr_luot_bat_dau", default=None)
_dong_ho = time.monotonic     # tách tên để bộ thử giả đồng hồ

#: Phải chừa sau mốc chặn để model viết câu trả lời cuối (một lượt gọi model ~10–40 giây).
_CHUA_VIET = 60.0


def bat_dau() -> None:
    """Gọi đầu mỗi lượt trả lời (brain.reply). Contextvar → theo đúng luồng của lượt đó;
    Hermes chép context sang luồng chạy tool song song (propagate_context_to_thread)."""
    _BAT_DAU.set(_dong_ho())


def da_chay() -> float | None:
    t0 = _BAT_DAU.get()
    return None if t0 is None else _dong_ho() - t0


def _so(ten: str, md: float) -> float:
    try:
        v = float(os.environ.get(ten, "") or md)
    except ValueError:
        return md
    return v if v > 0 else md


def nguong() -> tuple[float, float, float]:
    """(nhắc, chặn, trần) theo giây."""
    tran = _so("LSR_HAN_TRA_LOI_SECONDS", 480.0)
    chan = min(_so("LSR_LUOT_CHAN_GIAY", 400.0), max(1.0, tran - _CHUA_VIET))
    nhac = min(_so("LSR_LUOT_NHAC_GIAY", 300.0), chan)
    return nhac, chan, tran


def xet() -> tuple[str, float]:
    """("", giây) | ("nhac", giây) | ("chan", giây) cho lần gọi tool hiện tại."""
    g = da_chay()
    if g is None:
        return "", 0.0
    nhac, chan, _ = nguong()
    if g >= chan:
        return "chan", g
    if g >= nhac:
        return "nhac", g
    return "", g


def _phut(g: float) -> str:
    return f"{g / 60:.1f}".replace(".", ",")


def loi_chan(ten_tool: str, g: float) -> str:
    _, _, tran = nguong()
    return json.dumps({
        "error": "het_gio_luot",
        "tool": ten_tool,
        "reason": (f"Lượt này đã chạy {_phut(g)} phút, sát trần {_phut(tran)} phút nên "
                   "KHÔNG chạy thêm công cụ. Viết câu trả lời NGAY bằng dữ liệu đã có; "
                   "phần chưa làm thì nói rõ và đề nghị người dùng hỏi tiếp ở lượt sau."),
    }, ensure_ascii=False)


def gan_nhac(ket_qua, g: float):
    """Gắn lời nhắc vào kết quả tool. JSON object thì thêm khoá riêng (không phá cấu
    trúc tool trả về); chuỗi khác thì nối thêm một dòng; kiểu khác giữ nguyên."""
    if not isinstance(ket_qua, str):
        return ket_qua
    _, _, tran = nguong()
    cau = (f"Lượt đã chạy {_phut(g)}/{_phut(tran)} phút. Hãy tổng kết bằng dữ liệu đã có, "
           "hạn chế gọi thêm công cụ; phần chưa kịp làm thì nói rõ và đề nghị người dùng "
           "hỏi tiếp.")
    try:
        d = json.loads(ket_qua)
    except ValueError:
        d = None
    if isinstance(d, dict):
        d["_dong_ho_luot"] = cau
        return json.dumps(d, ensure_ascii=False)
    return f"{ket_qua}\n\n[đồng hồ lượt] {cau}"
