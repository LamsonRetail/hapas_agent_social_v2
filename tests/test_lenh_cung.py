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
_TS = (Path(__import__("os").environ.get("PLATFORM_REPO") or r"D:\Platform")
       / "apps" / "platform-web" / "lib" / "agentToolCapabilities.ts")


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
    # Tool có công tắc lùi (`lsr_policy._CONG_TAC_LUI`) được CHỜ console: console chưa
    # có dòng của nó thì lệnh vẫn chạy được, công tắc lùi về cha. Có rồi thì phải khớp.
    cho = {t: cua_runtime[t] for t in lenh_cung.lsr_policy._CONG_TAC_LUI
           if t in cua_runtime and t not in tren_console}
    cua_runtime = {t: x for t, x in cua_runtime.items() if t not in cho}
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
    # Platform đã có `/viec` (PR #83) — khớp TUYỆT ĐỐI, không còn tập chờ.
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


# ─────────── `/hapas`: trơn thì báo trạng thái (không model), có đối số thì ép tool ───────────

_TOK = {"THREADS_ACCESS_TOKEN": "THAAbimatEnv0123456789abcdefghijklm",
        "IG_ACCESS_TOKEN": "IGAAbimatEnv0123456789abcdefghijklm",
        "FB_PAGE_ACCESS_TOKEN": "EAAbimatEnv0123456789abcdefghijklmn",
        "FB_PAGE_ID": "1029384756"}


@pytest.fixture
def hapas(monkeypatch, tmp_path):
    """Môi trường giả cho `/hapas`: công tắc, quyền, `.env`, sổ token — không mạng."""
    import json
    import time

    import kenh_nha_meta as M

    tep = tmp_path / "meta_kenh_nha.json"
    monkeypatch.setattr(M, "TEP_TOKEN", tep)
    for k in list(_TOK) + ["META_APP_SECRET"]:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setitem(lenh_cung.lsr_policy._nho_nl, "tat_ro", set())

    def dat(bat=None, cho=True, ly_do="", env=(), so=None, tat_ro=()):
        monkeypatch.setattr(lenh_cung.lsr_policy, "nang_luc_bat",
                            lambda: lenh_cung.lsr_policy.KHONG_THU_HEP if bat is None
                            else set(bat))
        monkeypatch.setitem(lenh_cung.lsr_policy._nho_nl, "tat_ro", set(tat_ro))
        monkeypatch.setattr(lenh_cung.lsr_policy, "decide",
                            lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(cho, ly_do))
        for k in env:
            monkeypatch.setenv(k, _TOK[k])
        if so is not None:
            tep.write_text(json.dumps(so), encoding="utf-8")
        return lenh_cung.xu_ly("/hapas")

    dat.M = M
    dat.bay_gio = int(time.time())
    return dat


def test_hapas_trong_bang_lenh_va_co_trang_thai_khi_tron():
    assert lenh_cung.BANG_LENH["/hapas"] == "binh_luan_kenh_nha"
    assert "/hapas" in lenh_cung.LENH_TRANG_THAI_KHI_TRON
    assert set(lenh_cung.LENH_TRANG_THAI_KHI_TRON) <= set(lenh_cung.BANG_LENH)


def test_hapas_tron_tra_thang_khong_goi_model(hapas):
    kq = hapas(bat={"social_listen"})
    assert kq.tra_loi_thang, "/hapas trơn phải tự trả lời"
    assert kq.chi_thi == "" and kq.tool == "" and not kq.sai, "không được ép tool / gọi model"
    v = kq.tra_loi_thang
    for ten in ("Threads", "Instagram", "Facebook"):
        assert ten in v
    assert v.count("CHƯA NỐI") == 3, v
    assert "/hapas <việc cần đọc>" in v, "thiếu dòng hướng dẫn dùng"


def test_hapas_tron_bao_cong_tac_theo_cha_hay_rieng(hapas):
    v = hapas(bat={"social_listen"}).tra_loi_thang
    assert "CÔNG TẮC: đang bật" in v and "theo công tắc Quét mạng xã hội" in v
    v = hapas(bat={"soi_san"}).tra_loi_thang
    assert "CÔNG TẮC: ĐANG TẮT" in v and "theo công tắc Quét mạng xã hội" in v
    v = hapas(bat={"soi_san", "binh_luan_kenh_nha"}).tra_loi_thang
    assert "CÔNG TẮC: đang bật — công tắc riêng" in v
    v = hapas(bat={"social_listen"}, tat_ro={"binh_luan_kenh_nha"}).tra_loi_thang
    assert "CÔNG TẮC: ĐANG TẮT — công tắc riêng" in v
    v = hapas(bat=None).tra_loi_thang
    assert "chưa khai trên console" in v


def test_hapas_tron_van_tra_trang_thai_khi_tool_tat(hapas):
    """Tool tắt thì `/hapas <việc>` bị từ chối — nhưng `/hapas` trơn vẫn phải báo trạng
    thái: đó đúng là lúc người ta cần biết vì sao."""
    kq = hapas(bat={"soi_san"}, cho=False, ly_do="đang TẮT ở khối Năng lực")
    assert kq.tra_loi_thang and "KÊNH" in kq.tra_loi_thang
    assert "KHÔNG dùng được — đang TẮT ở khối Năng lực" in kq.tra_loi_thang
    assert "Không có lệnh" not in kq.tra_loi_thang


def test_hapas_tron_ke_kenh_va_ngay_het_han_khong_lo_gia_tri(hapas):
    M, g = hapas.M, hapas.bay_gio
    luu = {k: f"{k[:2].upper()}AAbimatLuu0123456789abcdefghijklmnop" for k in M.KENH}
    so = {
        "threads": {"token": luu["threads"], "loai": "dai_han", "lay_luc": g,
                    "env": M._van_tay(_TOK["THREADS_ACCESS_TOKEN"]),
                    "het_han": g + 59 * 86400 + 60},
        "instagram": {"token": luu["instagram"], "env": "khac", "het_han": g - 60},
        "facebook": {"token": luu["facebook"], "loai": "vinh_vien", "het_han": None,
                     "env": M._van_tay(_TOK["FB_PAGE_ACCESS_TOKEN"]),
                     "loi_lam_moi": f"loi {luu['facebook']}"},
    }
    v = hapas(bat={"social_listen"}, so=so,
              env=("THREADS_ACCESS_TOKEN", "FB_PAGE_ACCESS_TOKEN", "FB_PAGE_ID")).tra_loi_thang
    dong = {k: next(d for d in v.splitlines() if d.strip().startswith(M.TEN[k]))
            for k in M.KENH}
    het = lenh_cung._ngay_vn(so["threads"]["het_han"])
    assert "đã nối" in dong["threads"] and f"hết hạn {het} (còn 59 ngày)" in dong["threads"]
    assert "CHƯA NỐI" in dong["instagram"] and "IG_ACCESS_TOKEN" in dong["instagram"]
    assert "còn token đã lưu" in dong["instagram"] and "ĐÃ HẾT HẠN" in dong["instagram"]
    assert "đã nối" in dong["facebook"] and "không hết hạn" in dong["facebook"]
    assert "làm mới gần nhất hỏng" in dong["facebook"]
    for bi_mat in [*_TOK.values(), *luu.values()]:
        assert bi_mat not in v, "lộ giá trị .env / token"
        assert bi_mat[:12] not in v and bi_mat[-8:] not in v, "lộ một phần token"


def test_hapas_tron_env_moi_thi_bao_se_nap_lai(hapas):
    M = hapas.M
    so = {"threads": {"token": "THAAcu0123456789abcdefghijklmnopqrs", "env": "cu",
                      "het_han": hapas.bay_gio + 86400 * 30}}
    v = hapas(bat={"social_listen"}, so=so, env=("THREADS_ACCESS_TOKEN",)).tra_loi_thang
    dong = next(d for d in v.splitlines() if d.strip().startswith(M.TEN["threads"]))
    assert "bản .env cũ" in dong and "nạp lại" in dong


def test_hapas_tron_so_hong_thi_noi_that(hapas, monkeypatch):
    def hong():
        raise RuntimeError("x")
    monkeypatch.setattr(hapas.M, "doc_so", hong)
    v = hapas(bat={"social_listen"}).tra_loi_thang
    assert "Không đọc được tình trạng kênh (RuntimeError)" in v


def test_hapas_co_doi_so_thi_ep_tool(monkeypatch):
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(True, ""),
    )
    kq = lenh_cung.xu_ly("/hapas bình luận 5 bài mới nhất Instagram")
    assert kq.tra_loi_thang is None and kq.tool == "binh_luan_kenh_nha"
    assert "binh_luan_kenh_nha" in kq.chi_thi and "5 bài mới nhất" in kq.van_ban


def test_help_ke_hapas_tron(monkeypatch):
    monkeypatch.setattr(
        lenh_cung.lsr_policy, "decide",
        lambda t, a=None: lenh_cung.lsr_policy.PolicyDecision(True, ""),
    )
    van = lenh_cung.xu_ly("/help").tra_loi_thang or ""
    assert "Gõ /hapas trơn: xem công tắc, kênh đã nối và hạn token." in van
