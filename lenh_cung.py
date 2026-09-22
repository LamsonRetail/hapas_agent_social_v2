"""Lệnh cứng trong chat: `/search`, `/comment`, `/ad`…

VÌ SAO CÓ
Mặc định model tự chọn tool theo câu hỏi. Đoán đúng phần lớn thời gian, nhưng người
dùng biết rõ mình muốn gì thì không có cách nào nói thẳng. Lệnh cứng là cách nói
thẳng đó: `/search áo thun nam` là ÉP dùng `social_listen`, không thương lượng.

LỆNH KHÔNG NỚI QUYỀN — đây là ràng buộc quan trọng nhất của cả module.
Lệnh chỉ ép CHỌN CÁI GÌ. Quyết định ĐƯỢC HAY KHÔNG vẫn thuộc `lsr_policy.decide()`,
y như khi model tự gọi. Tool đang tắt ở khối Năng lực thì `/search` bị từ chối kèm
lý do thật, KHÔNG lặng lẽ đổi sang tra web cho có kết quả. Đổi đường âm thầm là kiểu
hỏng tệ nhất: người dùng tưởng năng lực còn chạy, và cái công tắc họ vừa tắt trở
thành vô nghĩa mà không ai biết.

Nói theo tầng: lệnh là tầng thứ tư, nằm DƯỚI ba tầng cũ (hợp đồng → công tắc → lời
dặn), không chen ngang.

BẢNG LỆNH NẰM HAI NƠI, VÀ CÓ BỘ CANH
`BANG_LENH` dưới đây phải khớp với `lenh:` trong
`apps/platform-web/lib/agentToolCapabilities.ts` của repo platform — console hiện
nhãn nào thì runtime phải nhận đúng nhãn đó. TS không gọi được từ Python nên buộc
phải có hai bản; `tests/test_lenh_cung.py` đối chiếu chúng để hai bên không lệch âm
thầm. Đây đúng là thứ đã cắn một lần: prompt nói một đằng, policy một nẻo.

ĐỐI SỐ THÌ ĐỂ MODEL BÓC
Lệnh cố định TOOL, phần còn lại của dòng vẫn là tiếng người và model tự dịch thành
đối số. Ép luôn cú pháp kiểu `--ngay 7 --nen tiktok` sẽ biến Mark thành CLI, và
người trong Lark gõ sai một lần là bỏ luôn.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import lsr_policy

#: Lệnh → tool. Sáu dòng này ứng 1-1 với sáu công tắc ở khối Năng lực trên console.
BANG_LENH: dict[str, str] = {
    "/search": "social_listen",
    "/comment": "social_deep_dive",
    "/ad": "fb_ads_library",
    "/scrape": "web_crawl",
    "/read": "web_scrape",
    "/wiki": "lark_cli",
}

#: Lệnh ghi đè THỨ TỰ DÙNG NGUỒN (mặc định: kho trước, web là đường lùi).
#: Không gọi tool nào nên không có gì để bật/tắt, và cũng không qua `decide()`.
LENH_NGUON: dict[str, str] = {
    "/kho": (
        "LỆNH CỨNG /kho — CHỈ trả lời bằng kho tài liệu đã cắm trong ngữ cảnh. "
        "Kho không có thì nói thẳng là kho không có, rồi hỏi người dùng có muốn "
        "tra web không. TUYỆT ĐỐI không tự ra web trong lượt này."
    ),
    "/web": (
        "LỆNH CỨNG /web — bỏ qua kho tài liệu, tra web. Người dùng đã chủ động nói "
        "rằng tài liệu nội bộ có thể đã cũ. Nói rõ đây là thông tin ngoài."
    ),
}

#: Lệnh gọi tool nhưng tool đó KHÔNG có công tắc (nằm ngoài `_TOOL_CO_CONG_TAC`).
#: Tắt trí nhớ và lịch theo năng lực thì agent quên cả hai, không ai muốn thế.
LENH_TOOL_TU_DO: dict[str, str] = {
    "/nho": "remember_about_user",
    "/nhac": "schedule_reminder",
}

#: Lệnh tự trả lời, không gọi model. Rẻ, nhanh, và quan trọng hơn: không bịa được.
LENH_TIEN_ICH = ("/help", "/nangluc")

_CU_PHAP = re.compile(r"^\s*(/[a-zA-Z][a-zA-Z0-9_-]*)\s*(.*)$", re.S)


@dataclass
class KetQua:
    """Kết quả bóc lệnh.

    `tra_loi_thang` khác None nghĩa là xong ngay, đừng gọi model. Dùng cho `/help`,
    `/nangluc`, và cho ca bị từ chối — từ chối mà vẫn nấu một lượt model là đốt tiền
    để nói một câu đã biết trước.
    """
    van_ban: str                      # text đưa cho model (đã gỡ lệnh)
    chi_thi: str = ""                 # khối chỉ thị ghép vào system prompt
    tra_loi_thang: str | None = None
    lenh: str = ""                    # lệnh đã nhận, "" nếu không có
    tool: str = ""                    # tool bị ép, "" nếu lệnh không ép tool
    sai: bool = field(default=False)  # lệnh lạ hoặc bị từ chối


def tach(text: str) -> tuple[str, str]:
    """Tách `/lenh` đầu dòng. Trả `("", text)` nếu không phải lệnh."""
    m = _CU_PHAP.match(text or "")
    if not m:
        return "", (text or "")
    return m.group(1).lower(), m.group(2).strip()


def _doi_so_tham_do(tool: str) -> dict:
    """Đối số tối thiểu để `decide()` trả lời đúng về tool này.

    Lấy từ `brain._TOOL_CAN_XET` chứ không gõ lại: `lark_cli` với args rỗng LUÔN bị
    từ chối vì "thiếu danh sách args hợp lệ", nên bảng thăm dò gõ tay sẽ báo `/wiki`
    bị cấm trong mọi hoàn cảnh. Nạp muộn để tránh vòng import với `brain`.
    """
    try:
        import brain
        return dict(brain._TOOL_CAN_XET.get(tool, ("", {}))[1] or {})
    except Exception:
        return {}


def _duoc_khong(tool: str) -> tuple[bool, str]:
    try:
        d = lsr_policy.decide(tool, _doi_so_tham_do(tool))
        return bool(d.allowed), str(d.reason or "")
    except Exception as e:
        # Hỏng thì ĐÓNG, và nói ra. Mở khi không biết là cách nhanh nhất để một lỗi
        # tạm thời thành một lần vượt quyền.
        return False, f"không hỏi được bộ thực thi quyền ({type(e).__name__})"


def _bang_trang_thai() -> list[tuple[str, str, bool, str]]:
    """[(lệnh, tool, đang dùng được, lý do nếu không)] cho cả sáu lệnh năng lực."""
    ra = []
    for lenh, tool in BANG_LENH.items():
        cho, vi_sao = _duoc_khong(tool)
        ra.append((lenh, tool, cho, vi_sao))
    return ra


def _van_help() -> str:
    """Bản `/help` SINH RA từ trạng thái thật, không phải chữ cứng.

    Gõ tay danh sách này là tạo nguồn sự thật thứ tư, và nó sẽ lệch đúng vào hôm ai
    đó tắt một năng lực — lúc người dùng cần nó đúng nhất.
    """
    d = ["Các lệnh Mark nhận:", "", "NĂNG LỰC (ép dùng đúng công cụ đó)"]
    for lenh, _tool, cho, _ly_do in _bang_trang_thai():
        d.append(f"  {lenh:<9} {'· đang bật' if cho else '· ĐANG TẮT'}")
    d += [
        "",
        "NGUỒN TRẢ LỜI",
        "  /kho      chỉ dùng kho tài liệu, không ra web",
        "  /web      bỏ qua kho, tra web",
        "",
        "KHÁC",
        "  /nho      ghi nhớ dài hạn một điều về bạn",
        "  /nhac     đặt một lời nhắc",
        "  /nangluc  xem quyền hạn và công tắc chi tiết",
        "",
        "Gõ lệnh rồi viết tiếp bằng tiếng Việt bình thường, "
        "ví dụ: /search áo thun nam 7 ngày tiktok",
    ]
    return "\n".join(d)


def _van_nangluc() -> str:
    try:
        phat = sorted(lsr_policy.quyen_phat())
    except Exception:
        phat = []
    try:
        bat = lsr_policy.nang_luc_bat()
    except Exception:
        bat = lsr_policy.KHONG_THU_HEP

    d = ["Quyền hạn của Mark lúc này:", "",
         f"HỢP ĐỒNG (platform cấp): {', '.join(phat) or '(trống)'}"]
    if bat is lsr_policy.KHONG_THU_HEP:
        d.append("CÔNG TẮC: chưa khai trên console — không thu hẹp gì thêm.")
    else:
        d.append(f"CÔNG TẮC đang bật: {', '.join(sorted(bat)) or '(không cái nào)'}")
    d += ["", "Từng lệnh:"]
    for lenh, tool, cho, ly_do in _bang_trang_thai():
        d.append(f"  {lenh:<9} {tool:<18} {'dùng được' if cho else 'KHÔNG — ' + (ly_do or 'bị chặn')}")
    d += ["", "Hợp đồng đổi trên platform · công tắc đổi ở khối Năng lực trên console. "
          "Không sửa được từ chat."]
    return "\n".join(d)


def xu_ly(text: str) -> KetQua:
    """Bóc lệnh khỏi câu hỏi. Không có lệnh thì trả nguyên văn, không đụng gì."""
    lenh, con_lai = tach(text)
    if not lenh:
        return KetQua(van_ban=text or "")

    if lenh == "/help":
        return KetQua(van_ban=con_lai, lenh=lenh, tra_loi_thang=_van_help())
    if lenh == "/nangluc":
        return KetQua(van_ban=con_lai, lenh=lenh, tra_loi_thang=_van_nangluc())

    if lenh in LENH_NGUON:
        return KetQua(van_ban=con_lai or text, lenh=lenh, chi_thi=LENH_NGUON[lenh])

    if lenh in LENH_TOOL_TU_DO:
        tool = LENH_TOOL_TU_DO[lenh]
        return KetQua(
            van_ban=con_lai or text, lenh=lenh, tool=tool,
            chi_thi=f"LỆNH CỨNG {lenh} — lượt này PHẢI dùng tool `{tool}`.",
        )

    if lenh in BANG_LENH:
        tool = BANG_LENH[lenh]
        cho, ly_do = _duoc_khong(tool)
        if not cho:
            return KetQua(
                van_ban=con_lai, lenh=lenh, tool=tool, sai=True,
                tra_loi_thang=(
                    f"Lệnh {lenh} cần năng lực `{tool}`, mà nó đang không dùng được.\n"
                    f"Lý do: {ly_do or 'bị chặn'}\n\n"
                    "Bật lại ở khối Năng lực trên console, hoặc gõ /nangluc để xem "
                    "toàn bộ quyền hạn hiện tại."
                ),
            )
        return KetQua(
            van_ban=con_lai or text, lenh=lenh, tool=tool,
            chi_thi=(
                f"LỆNH CỨNG {lenh} — người dùng đã chỉ định công cụ, KHÔNG tự chọn "
                f"cái khác. Lượt này PHẢI gọi tool `{tool}`. Phần còn lại của câu là "
                f"đối số, tự bóc ra. Thiếu thông tin thì HỎI LẠI, đừng đoán bừa rồi "
                f"chạy — công cụ này tốn tiền và thời gian thật."
            ),
        )

    return KetQua(
        van_ban=con_lai, lenh=lenh, sai=True,
        tra_loi_thang=f"Không có lệnh {lenh}. Gõ /help để xem danh sách.",
    )
