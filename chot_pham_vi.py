"""Cổng "chốt phạm vi" — tool cào TỐN TIỀN chỉ chạy khi người dùng đã đồng ý.

VÌ SAO CẦN CODE, KHÔNG CHỈ LỜI DẶN
Luật "hỏi 'chạy nhé?' trước khi quét" trước nay chỉ nằm trong mô tả tool và skill. Model
ChatGPT (gpt-5.6-terra) tháng 9 nghe lời: 22 lượt quét, gần như lượt nào cũng chốt phạm vi
rồi mới chạy. 01/10 Mark chuyển sang Claude (tài khoản gắn trên console) và quét THẲNG ngay
câu đầu ("hóng trend viral tuần này", "có chiến dịch hapas nào viral không") — tiền Apify
đã tiêu trước khi người hỏi kịp chỉnh phạm vi. Đổi tài khoản là đổi model, nên luật nào
cần đúng với MỌI model thì phải nằm trong code.

ĐƯỢC CHẠY KHI (một trong ba)
  1. Lượt là lệnh cứng trỏ ĐÚNG tool này (/search → social_listen, /comment →
     social_deep_dive…) — người dùng đã chọn đích danh. Lệnh khác (/kho, /bang, /nho…)
     không mở khoá gì: /kho còn cấm ra web, mà model bỏ qua lời dặn chính là lý do có cổng.
  2. Câu Mark nói NGAY TRƯỚC trong cuộc chat này là câu chốt phạm vi ("Chạy nhé?",
     "Bạn xác nhận để tôi quét nhé?", "Chốt … ?") — tin nhắn này là câu trả lời cho nó.
  3. Người dùng nói rõ không cần hỏi: "quét luôn", "chạy ngay", "khỏi hỏi"…
Còn lại tool KHÔNG chạy (không tốn đồng nào) và trả về hướng dẫn: tóm tắt phạm vi rồi hỏi
"Chạy nhé?". Lượt sau người dùng "ok" thì rơi vào trường hợp 2.

Ngoài một lượt trả lời (bộ test, script gọi thẳng handler) thì không có ngữ cảnh và cổng
không áp: mọi đường chạy thật đều đi qua `brain.reply`, nơi đặt ngữ cảnh.

Ngữ cảnh giữ bằng ContextVar, không phải threading.local: Hermes chạy tool song song trên
thread khác và chép ContextVar sang (`copy_context().run`), còn threading.local thì mất.
"""
from __future__ import annotations

import contextvars
import json
import re
import types
from typing import Callable

#: Tool gọi Apify, tính tiền theo bài/bình luận/sản phẩm. `web_crawl` không nằm đây: nó
#: chạy tầng miễn phí trước, Apify chỉ là đường lùi cuối và tự báo chi phí.
TOOL_TON_TIEN = frozenset({"social_listen", "social_deep_dive", "soi_tai_khoan", "soi_san"})

_NGU_CANH: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "mark_chot_pham_vi", default=None)

#: Câu chốt nằm cuối câu trả lời; chỉ xét đoạn cuối để chữ "xác nhận" lọt giữa một bản
#: báo cáo dài không bị hiểu là đang hỏi.
_DUOI = 700
_DONG_TU = r"(?:chạy|quét|cào|soi|bóc|lấy)"
#: Trong cùng MỘT câu: không vượt qua dấu kết câu hay xuống dòng.
_CUNG_CAU = r"[^.!?\n]{0,%d}?"
_MARK_DA_HOI = [
    re.compile(_DONG_TU + r"\s+(?:nhé|nha|nhá)\b", re.I),
    # "không/chứ" phải kèm dấu hỏi: "bài 3 lấy không được bình luận" là báo cáo, không hỏi.
    re.compile(_DONG_TU + r"\s+(?:không|ko|chứ)\s*\?", re.I),
    # Phải là lời NHỜ người đọc xác nhận ("Bạn xác nhận … chạy"), cùng một câu. "Cần xác
    # nhận lại với team trước khi chạy ngân sách" là kể việc, không phải hỏi.
    re.compile(r"\bbạn\s+(?:cứ\s+|hãy\s+)?xác\s*nhận" + _CUNG_CAU % 80 + _DONG_TU, re.I),
    re.compile(_DONG_TU + _CUNG_CAU % 80 + r"xác\s*nhận" + _CUNG_CAU % 40 + r"\?", re.I),
    # "chốt"/"phạm vi" chỉ tính khi chính câu đó là câu hỏi, hoặc câu mở đầu bằng "Chốt…"
    # (nhờ người đọc quyết). Đứng một mình thì quá rộng.
    re.compile(r"(?:\bchốt\b|phạm\s+vi)" + _CUNG_CAU % 150 + r"\?", re.I),
    re.compile(r"(?:^|[.!?\n]\s*)chốt\b", re.I),
]
_DI_LUON = re.compile(
    _DONG_TU + r"\s+(?:luôn|ngay|đi)\b|không\s+cần\s+hỏi|khỏi\s+hỏi|khỏi\s+xác\s*nhận",
    re.I)


def dat(tool_cua_lenh: str, hoi: str, cau_mark_truoc: str) -> contextvars.Token:
    """Mở ngữ cảnh cho một lượt. `tool_cua_lenh` = tool mà lệnh cứng của lượt trỏ tới
    (`lenh_cung.BANG_LENH`), "" nếu không phải lệnh cứng. Trả token để `bo()`."""
    return _NGU_CANH.set({"tool_cua_lenh": tool_cua_lenh or "", "hoi": hoi or "",
                          "cau_mark_truoc": cau_mark_truoc or ""})


def bo(token: contextvars.Token) -> None:
    try:
        _NGU_CANH.reset(token)
    except (ValueError, RuntimeError):
        _NGU_CANH.set(None)


def mark_da_hoi_chot(cau: str) -> bool:
    duoi = (cau or "")[-_DUOI:]
    return any(p.search(duoi) for p in _MARK_DA_HOI)


def xet(ten_tool: str) -> str | None:
    """None = cho chạy. Chuỗi = lý do chặn (đưa nguyên cho model)."""
    if ten_tool not in TOOL_TON_TIEN:
        return None
    nc = _NGU_CANH.get()
    if nc is None:
        return None
    if nc["tool_cua_lenh"] == ten_tool:
        return None
    if _DI_LUON.search(nc["hoi"]):
        return None
    if mark_da_hoi_chot(nc["cau_mark_truoc"]):
        return None
    return (
        f"CHƯA CHẠY `{ten_tool}` — tool này tốn tiền và người dùng CHƯA đồng ý phạm vi. "
        "KHÔNG gọi lại tool nào tốn tiền trong lượt này. Trả lời người dùng: tóm tắt ngắn "
        "phạm vi sẽ quét (từ khoá hoặc link, nền tảng, khoảng ngày, số bài mỗi nền tảng; "
        "ghi chú điều chưa rõ nếu có), rồi KẾT THÚC bằng đúng câu \"Chạy nhé?\". Người dùng "
        "đồng ý ở lượt sau thì tool sẽ chạy."
    )


def cai_vao_registry(ghi_audit: Callable[..., None] | None = None, registry=None) -> bool:
    """Bọc `registry.dispatch` một lần. Cài TRƯỚC `lsr_policy.install_registry_guard` để
    cổng quyền/công tắc nằm ngoài và xét trước: tool đang TẮT thì người dùng nghe "đang
    tắt", không bị hỏi "Chạy nhé?" cho một thứ không chạy được.

    `registry` chỉ để bộ thử đưa registry giả; mặc định là registry của Hermes."""
    if registry is None:
        try:
            from tools.registry import registry  # type: ignore
        except Exception:
            return False
    if getattr(registry, "_mark_chot_pham_vi", False):
        return True
    goc = registry.dispatch

    def boc(self, name: str, args: dict, **kwargs):
        ly_do = xet(name)
        if ly_do is None:
            return goc(name, args, **kwargs)
        kq = json.dumps({"error": "can_chot_pham_vi", "tool": name, "huong_dan": ly_do},
                        ensure_ascii=False)
        if ghi_audit:
            try:
                ghi_audit(name, args, kq, 0.0, loi="chờ chốt phạm vi")
            except Exception:
                pass
        return kq

    registry.dispatch = types.MethodType(boc, registry)
    registry._mark_chot_pham_vi = True
    return True
