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

#: Lệnh → tool. Mỗi dòng ứng 1-1 với một công tắc ở khối Năng lực trên console.
BANG_LENH: dict[str, str] = {
    "/search": "social_listen",
    "/comment": "social_deep_dive",
    "/ad": "fb_ads_library",
    "/scrape": "web_crawl",
    "/read": "web_scrape",
    "/wiki": "lark_cli",
    "/profile": "soi_tai_khoan",
    "/shop": "soi_san",
    "/bang": "doc_bang",
    "/topads": "tiktok_top_ads",
    "/hapas": "binh_luan_kenh_nha",
}

#: Tool ĐI KÈM được phép gọi thêm trong cùng lệnh ép. `/bang` ép `doc_bang` (đọc), nhưng
#: câu "/bang <link> tổng hợp tỷ lệ…" cần SỐ — và số phải do `dem_bang` đếm (07/10/2026:
#: model tự đếm tab 52 dòng sai ba lượt). Không có dòng này thì lệnh ép "không đổi sang tool
#: khác" đẩy model quay lại đếm tay. Chỉ nói tới tool đi kèm khi policy đang cho nó chạy.
TOOL_DI_KEM: dict[str, str] = {"doc_bang": "dem_bang"}

#: Lệnh năng lực mà gõ TRƠN (không đối số) thì tự trả lời trạng thái, không gọi model.
#: `/hapas` (05/10/2026): `/hapas` trơn trả công tắc, kênh Meta đã nối, hạn token — đọc
#: thẳng `.env` + sổ token, không lộ giá trị nào. Có đối số thì ép tool như mọi lệnh
#: năng lực. Gõ trơn mà để model hỏi lại "cần đọc gì?" thì người ta không bao giờ biết
#: kênh nào chưa nối cho tới khi chạy thật.
LENH_TRANG_THAI_KHI_TRON = ("/hapas",)

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
#: `/viec` (02/10/2026): xem việc quét nền của cuộc chat — đọc thẳng sổ `viec_nen`, không
#: gọi model, nên tiến độ/link/chi phí là số thật, không phải model kể lại.
LENH_TIEN_ICH = ("/help", "/nangluc", "/viec", "/tiendo")

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


def _muc_tool(tool: str) -> tuple[str, dict]:
    """(mô tả, đối số thăm dò) của một tool, lấy từ `brain._TOOL_CAN_XET`.

    KHÔNG gõ lại ở đây, vì hai lý do khác nhau:

    - Đối số: `lark_cli` với args rỗng LUÔN bị từ chối vì "thiếu danh sách args hợp
      lệ", nên bảng thăm dò gõ tay sẽ báo `/wiki` bị cấm trong mọi hoàn cảnh.
    - Mô tả: `_TOOL_CAN_XET` đã là nơi mô tả từng tool cho lời dặn gửi model. Chép
      sang đây một bản nữa là tạo hai câu trả lời cho cùng câu hỏi "tool này làm gì",
      rồi một hôm sửa một bên — `/help` nói một đằng, Mark hiểu một nẻo.

    Nạp muộn để tránh vòng import với `brain`.
    """
    try:
        import brain
        mo_ta, args = brain._TOOL_CAN_XET.get(tool, ("", {}))
        return str(mo_ta or ""), dict(args or {})
    except Exception:
        return "", {}


def _doi_so_tham_do(tool: str) -> dict:
    return _muc_tool(tool)[1]


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
    d = [
        "Các lệnh Mark nhận.",
        "",
        "Lệnh đặt ở ĐẦU câu, phần sau cứ viết tiếng Việt bình thường. Không gõ lệnh "
        "thì Mark tự chọn công cụ theo câu hỏi — gõ lệnh là bạn chỉ định thay nó.",
        "",
        "NĂNG LỰC — ép dùng đúng công cụ đó",
    ]
    co_tat = False
    for lenh, tool, cho, _ly_do in _bang_trang_thai():
        co_tat = co_tat or not cho
        d.append(f"  {lenh:<9} {'· đang bật' if cho else '· ĐANG TẮT'}")
        mo_ta = _muc_tool(tool)[0]
        if mo_ta:
            d.append(f"      {mo_ta[0].upper() + mo_ta[1:]}.")
        if lenh in LENH_TRANG_THAI_KHI_TRON:
            d.append(f"      Gõ {lenh} trơn: xem công tắc, kênh đã nối và hạn token.")
    d += [
        "",
        "NGUỒN TRẢ LỜI — quyết định Mark lấy thông tin ở đâu",
        "  /kho",
        "      Chỉ trả lời bằng kho tài liệu nội bộ. Kho không có thì nói thẳng là "
        "không có, không tự ra web.",
        "  /web",
        "      Bỏ qua kho, tra thẳng trên web. Dùng khi bạn biết tài liệu nội bộ đã cũ.",
        "      (Không gõ gì thì mặc định là kho trước, web là đường lùi.)",
        "",
        "KHÁC",
        "  /nho",
        "      Ghi nhớ dài hạn một điều về bạn, để lần sau không phải nói lại.",
        "  /nhac",
        "      Đặt một lời nhắc theo thời gian, đến giờ Mark tự nhắn vào đây.",
        "  /nangluc",
        "      Xem quyền hạn platform cấp và từng công tắc đang bật hay tắt.",
        "  /tiendo <link Base> [cot_han=\"Ngày giao\"] [tag=khong]",
        "      Tiến độ bằng code. Đặt lịch nhắc trên console → Lịch chạy → chọn nhóm → Giao việc.",
        "  /viec",
        "      Xem các việc quét nền (quét lớn chạy ngoài lượt trả lời): tiến độ, link "
        "sheet, chi phí thật. /viec <mã> để xem một việc.",
        "",
        "Ví dụ: /search áo thun nam 7 ngày tiktok",
        "Muốn biết kỹ một việc làm gì, ra kết quả gì thì hỏi bằng lời thường, không gõ "
        "lệnh ở đầu. Vd: \"soi sàn dùng thế nào?\", \"soi KOC ra những gì?\"",
    ]
    if co_tat:
        d.append("Lệnh ĐANG TẮT vẫn gõ được nhưng sẽ bị từ chối — bật lại ở khối "
                 "Năng lực trên console.")
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
    try:
        import tai_khoan_ai
        tk = tai_khoan_ai.mo_ta_luot_gan_nhat()
    except (Exception, SystemExit):   # config thiếu .env thì SystemExit — /nangluc vẫn phải chạy
        tk = ""
    if tk:
        d += ["", tk]
    return "\n".join(d)


def _ngay_vn(epoch: int) -> str:
    """dd/mm/yyyy theo giờ Việt Nam — VPS chạy UTC, nên không dùng giờ máy."""
    import datetime
    vn = datetime.timezone(datetime.timedelta(hours=7))
    return datetime.datetime.fromtimestamp(int(epoch), vn).strftime("%d/%m/%Y")


def _dong_kenh(M, kenh: str, so: dict, bay_gio: int) -> str:
    """Một dòng tình trạng kênh. Chỉ nói CÓ/KHÔNG và ngày — không bao giờ in giá trị
    `.env` hay token (kể cả một phần)."""
    import os
    thieu = M.thieu_cau_hinh(kenh)
    env = os.environ.get(M.ENV_TOKEN[kenh], "").strip()
    e = so.get(kenh) if isinstance(so.get(kenh), dict) else None
    co_luu = bool(e and e.get("token"))
    phan = ["đã nối" if not thieu else "CHƯA NỐI",
            ".env đủ" if not thieu else f".env thiếu {thieu}"]
    if not co_luu:
        phan.append("chưa có token đã lưu" + (" (nạp ở lần chạy đầu)" if not thieu else ""))
    else:
        if env and e.get("env") != M._van_tay(env):
            phan.append("token đã lưu là của bản .env cũ — lần chạy tới nạp lại")
        elif not env:
            phan.append("còn token đã lưu nhưng tool cần khoá trong .env")
        else:
            phan.append("có token đã lưu")
        het = e.get("het_han")
        if e.get("loai") == "vinh_vien":
            phan.append("không hết hạn")
        elif het:
            con = (int(het) - bay_gio) // 86400
            phan.append(f"ĐÃ HẾT HẠN {_ngay_vn(het)}" if int(het) <= bay_gio
                        else f"hết hạn {_ngay_vn(het)} (còn {con} ngày)")
        else:
            phan.append("chưa rõ hạn")
        if e.get("loi_lam_moi"):
            phan.append("lần làm mới gần nhất hỏng, sẽ tự thử lại")
    return f"  {M.TEN[kenh]:<10} · " + " · ".join(phan)


def _van_hapas() -> str:
    """`/hapas` trơn: công tắc, kênh đã nối, hạn token — không gọi model, không gọi mạng.

    Đọc `.env` (đã nạp vào môi trường) và sổ `.tokens/meta_kenh_nha.json` qua
    `kenh_nha_meta`. Chỉ báo có/không và ngày hết hạn; giá trị nào cũng không in.
    """
    import time
    tool = BANG_LENH["/hapas"]
    d = ["Bình luận kênh Hapas — /hapas", ""]
    try:
        bat = lsr_policy.nang_luc_bat()
    except Exception:
        bat = lsr_policy.KHONG_THU_HEP
    if bat is lsr_policy.KHONG_THU_HEP:
        d.append("CÔNG TẮC: chưa khai trên console — không thu hẹp gì thêm.")
    else:
        ct = lsr_policy.cong_tac_cua(tool, bat)
        nguon = ("chưa đặt riêng, đang theo công tắc Quét mạng xã hội (/search)"
                 if ct != tool else "công tắc riêng")
        d.append(f"CÔNG TẮC: {'đang bật' if ct in bat else 'ĐANG TẮT'} — {nguon}.")
    cho, ly_do = _duoc_khong(tool)
    d.append("Quyền hạn: cho chạy (kênh nào chưa nối thì kênh đó báo chưa nối)." if cho
             else f"KHÔNG dùng được — {ly_do or 'bị chặn'}")
    d += ["", "KÊNH (token Meta của chính Hapas):"]
    try:
        import kenh_nha_meta as M
        so = M.doc_so()
        bay_gio = int(time.time())
        d += [_dong_kenh(M, k, so, bay_gio) for k in M.KENH]
    except Exception as e:  # noqa: BLE001 — trạng thái hỏng thì nói thật, không đoán
        d.append(f"  Không đọc được tình trạng kênh ({type(e).__name__}).")
    d += ["",
          "Dùng: /hapas <việc cần đọc>, vd \"/hapas bình luận 5 bài mới nhất trên "
          "Instagram\" — miễn phí, ra Lark Sheet. Bài của đối thủ thì dùng /comment."]
    if not cho:
        d.append("Bật lại ở khối Năng lực trên console, hoặc gõ /nangluc để xem toàn bộ "
                 "quyền hạn.")
    return "\n".join(d)


def _van_viec(doi_so: str) -> str:
    """`/viec` — chat/người hỏi lấy từ ngữ cảnh lượt (brain.reply đặt trước `xu_ly`)."""
    try:
        import viec_nen
        return viec_nen.van_ban_lenh(doi_so)
    except Exception as e:  # noqa: BLE001 — sổ hỏng thì nói thật, không gọi model đoán
        return f"Không đọc được sổ việc quét nền ({type(e).__name__})."


def _lam_luot_nguoi_dung(lenh: str, tool: str, doi_so: str) -> str:
    """Dựng lại lượt người dùng cho lệnh ép tool.

    VÌ SAO KHÔNG CHỈ TRẢ VỀ `doi_so`
    Bản đầu bóc lệnh ra rồi ném hết ý định vào system prompt, để lại cho model đúng
    phần đối số. Với `/ad hapas` thì lượt người dùng chỉ còn một từ `hapas` — model
    cân lượt hiện tại nặng hơn nhiều so với một ghi chú nằm ở ký tự 11.926 của
    system prompt, nên nó thấy một từ mơ hồ và hỏi lại thay vì gọi tool. Đo thật,
    không suy đoán.

    Nên mệnh lệnh phải nằm NGAY TRONG lượt người dùng, cạnh đối số. System prompt
    vẫn giữ bản của nó — hai chỗ cùng nói một điều thì model khó lách hơn một.

    Đối số rỗng thì hỏi lại là ĐÚNG, không phải lỗi: `/ad` trơ trọi không có gì để
    tra. Chỉ cấm hỏi lại khi người dùng ĐÃ đưa đối số.
    """
    if not doi_so:
        return (f"[LỆNH {lenh}] Tôi muốn dùng `{tool}` nhưng chưa nói tra gì. "
                f"Hỏi lại tôi một câu ngắn.")
    # Quét/bóc LỚN (chủ agent chốt 02/10/2026): lệnh cứng vẫn không được bỏ qua câu hỏi chi
    # phí khi ước tính > 1 USD — gọi tool ở chế độ ước tính (không tốn tiền) là đã "gọi".
    lon = (" Riêng quét/bóc LỚN (nhiều bài, có thể > 1 USD): gọi với `chi_uoc_tinh`=true "
           "trước, báo USD + phút ước tính rồi kết bằng \"Chạy nhé?\"."
           if tool in ("social_listen", "social_deep_dive") else "")
    return (
        f"{doi_so}\n\n"
        f"[LỆNH {lenh}] Dòng trên là đối số. Lượt này BẮT BUỘC gọi tool `{tool}` — "
        f"đừng hỏi lại, đừng trả lời chay. Tham số phụ nào thiếu thì lấy mặc định "
        f"hợp lý rồi chạy, và nói rõ đã lấy mặc định gì.{lon}{_cau_di_kem(tool)}"
    )


def _cau_di_kem(tool: str) -> str:
    """Câu cho phép gọi thêm tool đi kèm (`TOOL_DI_KEM`), rỗng nếu không có/đang bị chặn."""
    kem = TOOL_DI_KEM.get(tool)
    cau = ""
    if kem and _duoc_khong(kem)[0]:
        cau = (f" Phần cần SỐ (đếm, %, so nhóm, cộng tổng) thì gọi thêm `{kem}` — số do code "
               "đếm, chép nguyên; không tự đếm trên bảng đã đọc.")
    # `tinh` (07/10/2026) đi kèm lệnh ép đọc bảng: lệnh cứng nói "không đổi sang tool khác",
    # mà rà ngân sách sau /bang vẫn cần 13/90 — thiếu câu này là model quay về tính tay.
    if cau and _duoc_khong("tinh")[0]:
        cau += (" Phép tính (tỷ lệ, chênh lệch, %) thì gọi thêm `tinh`, chép nguyên "
                "`cau_tinh`.")
    return cau


def xu_ly(text: str, *, kenh: dict | None = None, chat_id: str = "",
          sender_open_id: str | None = None) -> KetQua:
    """Bóc lệnh khỏi câu hỏi. Không có lệnh thì trả nguyên văn, không đụng gì."""
    lenh, con_lai = tach(text)
    if not lenh:
        return KetQua(van_ban=text or "")

    if lenh == "/tiendo":
        cho, ly_do = _duoc_khong("tra_tien_do")
        if not cho:
            return KetQua(van_ban=con_lai, lenh=lenh, sai=True,
                          tra_loi_thang=f"Không đọc tiến độ: {ly_do or 'năng lực đang tắt'}")
        import tien_do
        return KetQua(van_ban=con_lai, lenh=lenh, tra_loi_thang=tien_do.lenh_tiendo(
            con_lai, kenh=kenh, chat_id=chat_id, sender_open_id=sender_open_id))
    if lenh == "/help":
        return KetQua(van_ban=con_lai, lenh=lenh, tra_loi_thang=_van_help())
    if lenh == "/nangluc":
        return KetQua(van_ban=con_lai, lenh=lenh, tra_loi_thang=_van_nangluc())
    if lenh == "/viec":
        return KetQua(van_ban=con_lai, lenh=lenh, tra_loi_thang=_van_viec(con_lai))

    if lenh in LENH_NGUON:
        return KetQua(van_ban=con_lai or text, lenh=lenh, chi_thi=LENH_NGUON[lenh])

    if lenh in LENH_TOOL_TU_DO:
        tool = LENH_TOOL_TU_DO[lenh]
        return KetQua(
            van_ban=con_lai or text, lenh=lenh, tool=tool,
            chi_thi=f"LỆNH CỨNG {lenh} — lượt này PHẢI dùng tool `{tool}`.",
        )

    if lenh in LENH_TRANG_THAI_KHI_TRON and not con_lai:
        # Trạng thái thì luôn trả, KỂ CẢ khi tool đang tắt — đó là lúc cần nó nhất.
        return KetQua(van_ban="", lenh=lenh, tra_loi_thang=_van_hapas())

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
            van_ban=_lam_luot_nguoi_dung(lenh, tool, con_lai),
            lenh=lenh, tool=tool,
            chi_thi=(
                f"LỆNH CỨNG {lenh} — người dùng đã chỉ định công cụ. Lượt này gọi "
                f"`{tool}`, không đổi sang tool khác và không trả lời chay."
                + _cau_di_kem(tool)
                + ("" if con_lai else
                   " Họ chưa đưa đối số: hỏi lại ngắn gọn cần tra gì, rồi dừng.")
            ),
        )

    return KetQua(
        van_ban=con_lai, lenh=lenh, sai=True,
        tra_loi_thang=f"Không có lệnh {lenh}. Gõ /help để xem danh sách.",
    )
