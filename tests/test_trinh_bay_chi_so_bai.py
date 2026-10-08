"""Sheet của `chi_so_bai` dựng bằng lớp trình bày chung (trinh_bay_sheet, 08/10/2026).

Báo cáo SỐ: Tổng quan mang ĐÚNG các tổng tool đã cộng (`tong`, `tong_view_theo_nen_tang`,
như `cau_tong`), dòng TỔNG giữ nguyên dưới bảng, ghi chú gom mọi lưu ý (ô trống ≠ 0, dòng
trùng, giới hạn nền tảng, link chưa đếm). Lark giả: tests/sheet_gia.py.
"""
from __future__ import annotations

import json

import apify_tool as A
import chi_so_bai_tool as C
import test_chi_so_bai as TC
import trinh_bay_sheet as TB
from test_chi_so_bai import gia  # noqa: F401 — fixture dùng chung
from sheet_gia import meta  # noqa: E402


LINKS = [TC.YT, TC.TT_NGAN, TC.FB, TC.TT1, TC.IG, TC.TH, TC.TT_QUERY, TC.TT1,
         "https://www.tiktok.com/@rgbvn"]


def _chay(**args) -> tuple[dict, str]:
    raw = C._handle(args)
    return json.loads(raw), raw


def _dong_tq(lark, nhan: str) -> list:
    return next(r for r in lark.o("Tổng quan") if r and r[0] == nhan)


def test_tab_dung_thu_tu_va_tong_quan_la_so_cua_tool(gia):
    kq, _ = _chay(link_bai=LINKS)
    lark = gia["lark"]
    assert lark.tab_ten() == ["Tổng quan", "Dữ liệu", "Dữ liệu gốc"]
    tq = lark.o("Tổng quan")
    assert tq[0][0] == lark.dau.title and "chi_so_bai" in meta(tq)
    # Số chính = ĐÚNG số tool đã cộng (không cộng lại ở lớp trình bày).
    assert _dong_tq(lark, "Tổng view")[1] == kq["tong"]["view"]["tong"] == 545274
    assert _dong_tq(lark, "Tổng lưu")[1] == kq["tong"]["luu"]["tong"]
    assert "3 link có số" in _dong_tq(lark, "Tổng lưu")[3]
    assert _dong_tq(lark, "Link đếm được")[1] == kq["so_link_ok"] == 7
    for p, v in kq["tong_view_theo_nen_tang"].items():
        assert _dong_tq(lark, f"View {p}")[1] == v
    chu = " ".join(str(r[0]) for r in tq)
    assert "Ô trống = nguồn không có số, không tính là 0" in chu
    assert kq["cau_tong"] in chu
    assert "Instagram: view là lượt phát" in chu and "dòng 9" in chu
    assert "THEO TRẠNG THÁI" in chu and "TOP 5 LINK THEO VIEW" in chu


def test_dong_tong_giu_nguyen_va_trang_tri_ngoai_vung_loc(gia):
    kq, _ = _chay(link_bai=LINKS)
    lark = gia["lark"]
    o = lark.o("Dữ liệu")
    assert o[0] == ["STT", "Link", "Nền tảng", "Tài khoản", "Ngày đăng", "View", "Like",
                    "Bình luận", "Share", "Lưu", "Trạng thái", "Ghi chú", "Lấy số lúc"]
    assert o[10] == [""] * 13, "một dòng trống trước dòng tổng"
    tong = o[11]
    assert tong[1] == "TỔNG (7 link OK, không cộng dòng trùng)"
    assert tong[5:10] == [kq["tong"][c]["tong"] for c in C._COT]
    assert tong[11] == "Ô trống = nguồn không có số, không tính là 0"
    st = lark.kieu_o("Dữ liệu", 6, 12)
    assert any(s.get("font", {}).get("bold") and s.get("backColor") == TB.XAM_TONG for s in st)
    sid = lark.tab("Dữ liệu")["sheet_id"]
    loc = [b for p, b in lark.loc() if f"/{sid}/" in p]
    assert loc and loc[0]["range"] == f"{sid}!A1:M10", "lọc tiêu đề + 9 dòng, không gồm dòng tổng"


def test_tieu_de_co_dinh_va_dinh_dang_theo_kieu_cot(gia):
    _chay(link_bai=LINKS)
    lark = gia["lark"]
    assert lark.tab("Dữ liệu")["frozen"] == 1
    assert any(s.get("backColor") == TB.NAVY for s in lark.kieu_o("Dữ liệu", 1, 1))

    def fmt(cot, dong=2):
        return [s["formatter"] for s in lark.kieu_o("Dữ liệu", cot, dong) if "formatter" in s]

    assert "#,##0" in fmt(1) and "#,##0" in fmt(6) and "#,##0" in fmt(10)
    assert "yyyy/MM/dd" in fmt(5) and "yyyy/MM/dd HH:mm:ss" in fmt(13)
    assert "@" in fmt(4), "tài khoản là mã: giữ dạng chữ"
    o = lark.o("Dữ liệu")
    assert isinstance(o[1][4], int) and isinstance(o[1][12], float), "ngày ghi thành ngày thật"
    assert isinstance(o[2][3], str) and o[2][3] == "soimoishowbiz"


def test_ten_tai_khoan_toan_so_van_la_chu(gia, monkeypatch):
    monkeypatch.setattr(TC, "TIKTOK", [TC._tt(TC.TT1, TC.TT1, 5, 1, 0, 0, 0, ten="1234567")])
    _chay(link_bai=[TC.TT1])
    assert gia["lark"].o("Dữ liệu")[1][3] == "1234567"


def test_du_lieu_goc_cung_thu_tu_va_khong_lot_vao_tool_result(gia):
    _, raw = _chay(link_bai=LINKS)
    g = gia["lark"].o("Dữ liệu gốc")
    assert g[0][:2] == ["STT (tab dữ liệu)", "Link đã dán"]
    assert [r[0] for r in g[1:]] == [1, 2, 3, 4, 5, 6, 7], "dòng trùng (8) không lặp lại"
    assert "collectCount" in g[0] and "statistics.viewCount" in g[0]
    assert '"_goc"' not in raw


def test_kiem_ghi_vao_tool_result(gia):
    kq, _ = _chay(link_bai=LINKS)
    assert kq["day_du"] is True and kq["bang_tinh_tiep"] is None
    assert kq["kiem_ghi"].startswith("Đã ghi đủ 16/16 dòng")


def test_trang_tri_hong_van_giu_link_va_du_lieu(gia):
    gia["lark"].hong = {"styles_batch_update"}
    kq, _ = _chay(link_bai=LINKS)
    assert kq["sheet_url"] and kq["day_du"] is True and kq["loi"] is None
    assert gia["lark"].o("Dữ liệu")[4][5] == 525800


def test_cap_quyen_sau_khi_ghi_xong(gia, monkeypatch):
    goi_grant = []
    monkeypatch.setattr(A, "_grant", lambda tok, oid: goi_grant.append(
        len(gia["lark"].goi)) or True)
    kq, _ = _chay(link_bai=LINKS)
    ghi = [i for i, g in enumerate(gia["lark"].goi) if g[1].endswith("/values_batch_update")]
    assert kq["granted"] is True and goi_grant and goi_grant[0] > max(ghi)


def test_tao_sheet_hong_thi_loi_sheet_nhu_cu(gia):
    gia["lark"].hong = {"/open-apis/sheets/v3/spreadsheets"}
    kq, _ = _chay(link_bai=LINKS)
    assert kq["sheet_url"] is None and "sheet" in kq["loi"] and kq["success"] is False
    assert kq["so_link_ok"] == 7 and kq["day_du"] is None


def test_link_vuot_tran_noi_ro_trong_tong_quan(gia):
    gia["tran"]["tiktok"] = (1, 0.5, True)
    kq, _ = _chay(link_bai=[TC.TT1, TC.TT_NGAN, TC.YT])
    chu = " ".join(str(r[0]) for r in gia["lark"].o("Tổng quan"))
    assert kq["con_lai"] == [TC.TT_NGAN]
    assert "1 link CHƯA đếm vì vượt trần console" in chu
