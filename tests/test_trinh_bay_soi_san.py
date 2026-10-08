"""Sheet của `soi_san` (Shopee theo từ khoá) dựng bằng lớp trình bày chung (08/10/2026).

Danh sách sản phẩm: giá VND định dạng tiền ₫, Giảm % là số ĐÃ nhân 100 (32 = 32%), điểm
hai chữ số thập phân; Tổng quan = đúng `tong_hop` tool đã tính + đếm theo nhóm + ghi chú
"không có số đã bán". Lark giả: tests/sheet_gia.py. (Chế độ `link` thuộc san_link.py.)
"""
from __future__ import annotations

import json

import apify_tool as A
import shopee_tool as S
import test_soi_tai_khoan_va_san as TS
from test_soi_tai_khoan_va_san import gia  # noqa: F401 — fixture dùng chung


def _chay(**args) -> tuple[dict, str]:
    raw = S._handle(args)
    return json.loads(raw), raw


def _fmt(lark, tab, cot, dong=2):
    return [s["formatter"] for s in lark.kieu_o(tab, cot, dong) if "formatter" in s]


def _tq(lark, nhan):
    return next(r for r in lark.o("Tổng quan") if r and r[0] == nhan)


def test_tab_va_dinh_dang_tien_phan_tram_diem(gia):
    _, lark = gia
    kq, _ = _chay(tu_khoa=["túi xách nữ"])
    assert lark.tab_ten() == ["Tổng quan", "Dữ liệu", "Dữ liệu gốc"]
    o = lark.o("Dữ liệu")
    assert o[0] == S._HEADER and o[1][3] == 169000 and o[1][5] == 32
    assert '#,##0 "₫"' in _fmt(lark, "Dữ liệu", 4) and '#,##0 "₫"' in _fmt(lark, "Dữ liệu", 5)
    assert '0.00"%"' in _fmt(lark, "Dữ liệu", 6), "32 đã là phần trăm: không nhân 100 nữa"
    assert "#,##0.00" in _fmt(lark, "Dữ liệu", 9) and "#,##0" in _fmt(lark, "Dữ liệu", 7)
    assert lark.tab("Dữ liệu")["frozen"] == 1
    sid = lark.tab("Dữ liệu")["sheet_id"]
    assert [b["range"] for p, b in lark.loc() if f"/{sid}/" in p] == [f"{sid}!A1:N4"]
    assert kq["day_du"] is True and kq["kiem_ghi"].startswith("Đã ghi đủ")


def test_tong_quan_la_tong_hop_cua_tool(gia):
    _, lark = gia
    kq, _ = _chay(tu_khoa=["túi xách nữ"])
    g = kq["tong_hop"]["gia"]
    assert _tq(lark, "Giá trung vị")[1] == g["trung_vi"]
    assert _tq(lark, "Giá thấp nhất")[1] == g["thap_nhat"]
    assert _tq(lark, "Mức giảm trung bình")[1] == kq["tong_hop"]["dang_giam_gia"]["giam_tb_pct"]
    assert _tq(lark, "Khớp từ khoá")[1] == kq["so_sp_khop_tu_khoa"]
    chu = " ".join(str(r[0]) for r in lark.o("Tổng quan"))
    assert "Nguồn KHÔNG có số đã bán" in chu and kq["canh_bao_lac_de"] in chu
    assert "THEO SHOP (MỌI SẢN PHẨM)" in chu and "PHÂN BỐ GIÁ (MỌI SẢN PHẨM)" in chu
    assert "NHIỀU ĐÁNH GIÁ NHẤT (MỌI SẢN PHẨM)" in chu


def test_du_lieu_goc_giu_truong_tool_bo(gia):
    _, lark = gia
    _, raw = _chay(tu_khoa=["túi"])
    g = lark.o("Dữ liệu gốc")
    assert g[0][0] == "Hạng" and "historicalSold" in g[0] and "isOfficialShop" in g[0]
    assert [r[0] for r in g[1:]] == [1, 2, 3]
    assert "historicalSold" not in raw


def test_khong_san_pham_thi_khong_tao_sheet(gia, monkeypatch):
    _, lark = gia
    monkeypatch.setattr(A, "_call", lambda *a, **k: [])
    kq, _ = _chay(tu_khoa=["túi"])
    assert kq["sheet_url"] is None and not lark.bt and kq["day_du"] is None


def test_trang_tri_hong_van_giu_link(gia):
    _, lark = gia
    lark.hong = {"styles_batch_update"}
    kq, _ = _chay(tu_khoa=["túi"])
    assert kq["sheet_url"] and kq["loi"] is None and lark.o("Dữ liệu")[3][3] == 1_250_000


def test_ghi_hong_thi_loi_nhu_cu(gia):
    _, lark = gia
    lark.hong = {"values_batch_update"}
    kq, _ = _chay(tu_khoa=["túi"])
    assert kq["loi"].startswith("Tạo/ghi sheet thất bại") and kq["success"] is False
    assert kq["sheet_url"] is None and kq["tong_hop"]["gia"]["cao_nhat"] == 1_250_000


def test_xep_ban_chay_thi_noi_hang_la_thu_hang_ban_chay(gia):
    _, lark = gia
    _chay(tu_khoa=["túi"], xep_theo="ban_chay")
    chu = " ".join(str(r[0]) for r in lark.o("Tổng quan"))
    assert "thứ hạng bán chạy của Shopee" in chu and TS.SHOPEE
