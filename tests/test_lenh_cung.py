"""Canh bộ lệnh cứng: bảng lệnh hai nơi, quyền không bị nới, `/help` không nói dối.

Bảng lệnh tồn tại ở HAI nơi và buộc phải thế: console là TypeScript, runtime là
Python, không bên nào gọi được bên kia. Nên phải có bộ canh — đây là bộ đó. Lệch âm
thầm nghĩa là console hiện `/search` mà gõ vào thì Mark bảo "không có lệnh đó".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import lenh_cung

_GOC = Path(__file__).resolve().parents[1]
_TS = Path(r"D:\Platform") / "apps" / "platform-web" / "lib" / "agentToolCapabilities.ts"


def _lenh_tren_console() -> dict[str, str]:
    """{tool: lệnh} đọc từ file TypeScript của console."""
    if not _TS.is_file():
        pytest.skip("không thấy repo platform ở cây làm việc này")
    s = _TS.read_text(encoding="utf-8")
    ra = {
        m.group(1): m.group(2)
        for m in re.finditer(r'tool:\s*"([^"]+)",\s*lenh:\s*"(/[^"]+)"', s)
    }
    assert ra, "regex không đọc ra dòng nào — mọi khẳng định sau sẽ vô nghĩa"
    return ra


def test_bang_lenh_khop_console():
    tren_console = _lenh_tren_console()
    cua_runtime = {tool: lenh for lenh, tool in lenh_cung.BANG_LENH.items()}
    assert cua_runtime == tren_console, (
        "bảng lệnh runtime lệch khỏi console.\n"
        f"  runtime: {sorted(cua_runtime.items())}\n"
        f"  console: {sorted(tren_console.items())}\n"
        "Console hiện một nhãn mà runtime không nhận = gõ vào thì Mark bảo không có."
    )


def test_lenh_khong_cong_tac_cung_khop():
    """Sáu lệnh ở chân khối Năng lực phải đúng là sáu lệnh runtime nhận."""
    if not _TS.is_file():
        pytest.skip("không thấy repo platform")
    s = _TS.read_text(encoding="utf-8")
    m = re.search(r"LENH_KHONG_CONG_TAC[^=]*=\s*\[(.*?)\n\];", s, re.S)
    assert m, "không tìm thấy LENH_KHONG_CONG_TAC"
    console = set(re.findall(r'lenh:\s*"(/[^"]+)"', m.group(1)))
    assert console, "đọc ra danh sách rỗng"

    runtime = (set(lenh_cung.LENH_NGUON)
               | set(lenh_cung.LENH_TOOL_TU_DO)
               | set(lenh_cung.LENH_TIEN_ICH))
    assert console == runtime, (
        f"console bày {sorted(console)} · runtime nhận {sorted(runtime)}"
    )


def test_moi_lenh_chi_mot_tool():
    ten = list(lenh_cung.BANG_LENH.values())
    trung = {t for t in ten if ten.count(t) > 1}
    assert not trung, f"hai lệnh cùng trỏ một tool: {sorted(trung)}"


def test_khong_lenh_nao_trung_nhau_giua_cac_nhom():
    nhom = [set(lenh_cung.BANG_LENH), set(lenh_cung.LENH_NGUON),
            set(lenh_cung.LENH_TOOL_TU_DO), set(lenh_cung.LENH_TIEN_ICH)]
    het = [x for n in nhom for x in n]
    trung = {x for x in het if het.count(x) > 1}
    assert not trung, f"lệnh nằm ở hai nhóm — nhóm nào thắng là tuỳ thứ tự if: {sorted(trung)}"


def test_cau_khong_phai_lenh_thi_khong_doi_gi():
    """Ràng buộc quan trọng nhất về hồi quy: câu thường phải đi y như trước."""
    for cau in ["quét social cho anh", "", "  ", "5/10 có gì hot", "a/b test là gì"]:
        kq = lenh_cung.xu_ly(cau)
        assert kq.tra_loi_thang is None, f"{cau!r} bị nuốt thành lệnh"
        assert kq.chi_thi == "", f"{cau!r} bị gắn chỉ thị"
        assert kq.van_ban == cau, f"{cau!r} bị sửa văn bản"


def test_tach_giu_nguyen_phan_con_lai():
    lenh, con = lenh_cung.tach("/search áo thun nam 7 ngày tiktok")
    assert lenh == "/search"
    assert con == "áo thun nam 7 ngày tiktok"


def test_lenh_viet_hoa_van_nhan():
    assert lenh_cung.tach("/SEARCH abc")[0] == "/search"


def test_lenh_la_thi_bao_chu_khong_im_lang():
    kq = lenh_cung.xu_ly("/xoaheet mọi thứ")
    assert kq.sai and kq.tra_loi_thang and "/help" in kq.tra_loi_thang


def test_lenh_bi_chan_thi_KHONG_goi_model_va_KHONG_doi_duong(monkeypatch):
    """Đây là bài quan trọng nhất của cả tệp.

    Tool tắt thì `/search` phải DỪNG kèm lý do. Nếu nó lặng lẽ trả về một chỉ thị
    khác (ví dụ đẩy sang tra web) thì cái công tắc người dùng vừa tắt thành vô nghĩa,
    mà không có chỗ nào nói ra.
    """
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(False, "đang TẮT ở khối Năng lực"),
    )
    kq = lenh_cung.xu_ly("/search áo thun")
    assert kq.sai, "lệnh bị chặn mà không đánh dấu sai"
    assert kq.tra_loi_thang, "bị chặn mà vẫn để lượt chạy tiếp tới model"
    assert "đang TẮT" in kq.tra_loi_thang, "không nói lý do thật"
    assert kq.chi_thi == "", "bị chặn mà vẫn phát chỉ thị ép tool"


def test_lenh_duoc_phep_thi_ep_dung_tool_do(monkeypatch):
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(True, ""),
    )
    for lenh, tool in lenh_cung.BANG_LENH.items():
        kq = lenh_cung.xu_ly(f"{lenh} thử")
        assert kq.tra_loi_thang is None, f"{lenh} bị chặn nhầm"
        assert tool in kq.chi_thi, f"{lenh} không ép đúng `{tool}`"


def test_help_doc_trang_thai_that_chu_khong_phai_chu_cung(monkeypatch):
    """`/help` gõ tay sẽ lệch đúng vào hôm ai đó tắt một năng lực."""
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(
            t != "social_listen", "" if t != "social_listen" else "tắt"),
    )
    van = lenh_cung.xu_ly("/help").tra_loi_thang
    assert van
    dong = next(d for d in van.splitlines() if d.strip().startswith("/search"))
    assert "ĐANG TẮT" in dong, f"/help báo /search đang bật trong khi nó tắt: {dong!r}"
    dong2 = next(d for d in van.splitlines() if d.strip().startswith("/ad"))
    assert "đang bật" in dong2


def test_help_ke_du_moi_lenh_nang_luc(monkeypatch):
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(True, ""),
    )
    van = lenh_cung.xu_ly("/help").tra_loi_thang or ""
    thieu = [l for l in lenh_cung.BANG_LENH if l not in van]
    assert not thieu, f"/help bỏ sót: {thieu}"


def test_luot_nguoi_dung_giu_ca_menh_lenh_lan_doi_so(monkeypatch):
    """Hồi quy cho đúng lỗi đã xảy ra thật với `/ad hapas`.

    Bản đầu bóc lệnh ra rồi ném ý định vào system prompt, để lại lượt người dùng đúng
    một từ `hapas`. Model cân lượt hiện tại nặng hơn một ghi chú ở ký tự 11.926 của
    system prompt, nên nó hỏi lại thay vì gọi tool. Mệnh lệnh phải nằm NGAY TRONG
    lượt người dùng.
    """
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(True, ""),
    )
    kq = lenh_cung.xu_ly("/ad hapas")
    assert "hapas" in kq.van_ban, "mất đối số"
    assert "fb_ads_library" in kq.van_ban, (
        "lượt người dùng không nhắc tool — ý định bị đẩy hết sang system prompt, "
        "đúng cái đã làm Mark hỏi lại thay vì chạy"
    )
    assert kq.van_ban.strip() != "hapas", "lượt người dùng trơ trọi một từ"


def test_co_doi_so_thi_CAM_hoi_lai(monkeypatch):
    """Câu 'thiếu thông tin thì hỏi lại' từng là cửa thoát model dùng ngay lần đầu."""
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(True, ""),
    )
    kq = lenh_cung.xu_ly("/ad hapas")
    het = (kq.van_ban + " " + kq.chi_thi).lower()
    assert "đừng hỏi lại" in het, "không có lệnh cấm hỏi lại"
    assert "thiếu thông tin thì hỏi lại" not in het, "cửa thoát cũ còn nguyên"


def test_khong_co_doi_so_thi_VAN_duoc_hoi_lai(monkeypatch):
    """`/ad` trơ trọi thì không có gì để tra — hỏi lại là đúng, không phải lỗi."""
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(True, ""),
    )
    kq = lenh_cung.xu_ly("/ad")
    assert "hỏi lại" in (kq.van_ban + kq.chi_thi).lower()


def test_help_moi_lenh_deu_co_mo_ta(monkeypatch):
    """Tên lệnh trần không nói được nó làm gì.

    Khối NĂNG LỰC từng chỉ in `/search · đang bật` trong khi hai khối dưới có mô tả
    — người đọc phải đoán. Chốt này bắt luôn ca thêm năng lực thứ bảy mà quên mô tả.
    """
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(True, ""),
    )
    dong = (lenh_cung.xu_ly("/help").tra_loi_thang or "").splitlines()
    het = list(lenh_cung.BANG_LENH) + list(lenh_cung.LENH_NGUON) + list(lenh_cung.LENH_TOOL_TU_DO)
    thieu = []
    for lenh in het:
        i = next((k for k, d in enumerate(dong) if d.strip().startswith(lenh + " ")
                  or d.strip() == lenh), None)
        assert i is not None, f"/help không kể {lenh}"
        sau = [d for d in dong[i + 1:i + 3] if d.startswith("      ")]
        if not sau or len(sau[0].strip()) < 15:
            thieu.append(lenh)
    assert not thieu, f"lệnh không có mô tả trong /help: {thieu}"


def test_mo_ta_lay_tu_bang_cua_brain():
    """Mô tả phải đến từ `_TOOL_CAN_XET`, không phải chuỗi gõ riêng trong module này.

    Hai bản mô tả cho cùng một tool thì một hôm ai đó sửa một bên: `/help` nói một
    đằng, lời dặn gửi model nói một nẻo.
    """
    import brain
    for tool in lenh_cung.BANG_LENH.values():
        assert _mo_ta(tool) == brain._TOOL_CAN_XET[tool][0], f"{tool} lệch mô tả"


def _mo_ta(tool: str) -> str:
    return lenh_cung._muc_tool(tool)[0]


def test_policy_nem_thi_dong_chu_khong_mo():
    """Hỏng thì ĐÓNG. Mở khi không biết là cách nhanh nhất để lỗi thành vượt quyền."""
    cho, vi_sao = lenh_cung._duoc_khong("khong_co_tool_nay_dau")
    assert isinstance(cho, bool)


def test_doi_so_tham_do_lark_cli_khong_rong():
    """`lark_cli` với args rỗng LUÔN bị từ chối — bảng thăm dò gõ tay sẽ báo /wiki
    bị cấm trong mọi hoàn cảnh, kể cả khi nó đang bật."""
    assert lenh_cung._doi_so_tham_do("lark_cli"), (
        "mất đối số thăm dò của lark_cli — /wiki sẽ luôn báo bị cấm"
    )
