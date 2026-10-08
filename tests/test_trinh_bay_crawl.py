"""web_crawl (crawl_tool.py) → lớp trình bày chung (trinh_bay_sheet), Lark GIẢ (sheet_gia).

Soi: một bảng → "Tổng quan" + "Dữ liệu"; giá VND (web .vn / currency adapter) định dạng tiền ₫,
web khác thì số trơn (không gán ký hiệu tiền khi không chắc); Giảm % là số tool tính ĐÃ ×100;
SKU dạng chữ; chặn chèn công thức vẫn giữ; ghi chú CHẠM TRẦN / tầng đoán; adapter Apify →
"Dữ liệu gốc" (không lọt ra tool_result); cấp quyền sau cùng; trang trí hỏng vẫn đủ.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import apify_tool as A
import crawl_tool as C
import trinh_bay_sheet as T
from sheet_gia import LarkGia
from sheet_gia import meta  # noqa: E402

SP = [{"ten": "=cmd|' /C calc'!A0", "gia": 1000000, "gia_goc": 1300000, "link": "https://hapas.vn/a",
       "anh": "https://hapas.vn/a.jpg", "anh_tat_ca": ["https://hapas.vn/a.jpg"], "so_anh": 1,
       "sku": "00123"},
      {"ten": "Túi B", "gia": 500000, "gia_goc": None, "link": "https://hapas.vn/b", "anh": "",
       "anh_tat_ca": [], "so_anh": 0, "sku": ""}]


class _Proc:
    def __init__(self, d):
        self.stdout, self.stderr = json.dumps(d, ensure_ascii=False), ""


@pytest.fixture
def chay(monkeypatch):
    gia = LarkGia()
    monkeypatch.setattr(A.lark, "call", gia.call)
    monkeypatch.setattr(C, "_PY", Path(__file__))
    monkeypatch.setattr(C.memory_store, "get_current_sender", lambda: "ou_x")
    luc = []
    monkeypatch.setattr(C, "_grant", lambda tok, oid: luc.append(len(gia.goi)) or True)

    def run(sp=SP, url="hapas.vn", tang="catalog_json", **kw):
        d = {"san_pham": sp, "tang": tang, "so_co_anh": 1, "tong_so_anh": 1, "nhat_ky": []}
        monkeypatch.setattr(C.subprocess, "run", lambda *a, **k: _Proc(d))
        raw = C._handle({"url": url, **kw})
        return json.loads(raw), raw
    run.gia, run.luc = gia, luc
    return run


def _fmt(gia, cot, dong=2):
    return [s["formatter"] for s in gia.kieu_o("Dữ liệu", cot, dong) if "formatter" in s]


def test_web_vn_tien_dong_giam_phan_tram_sku_chu_va_chan_cong_thuc(chay):
    kq, raw = chay()
    gia = chay.gia
    assert kq["success"] is True and gia.tab_ten() == ["Tổng quan", "Dữ liệu"]
    o = gia.o("Dữ liệu")
    assert o[0] == C._COT
    assert o[1][0].startswith("'="), "tên sản phẩm '=…' vẫn bị vô hiệu hoá"
    assert o[1][1] == 1000000 and "#,##0" in _fmt(gia, 2) and "#,##0" in _fmt(gia, 3)
    assert o[1][3] == 23 and "#,##0.00" in _fmt(gia, 4), "Giảm % đã ×100: không nhân nữa"
    assert o[2][3] == "" and o[2][2] == "", "không có giá gốc → ô trống, không 0"
    assert o[1][4] == "00123" and "@" in _fmt(gia, 5)
    assert gia.tab("Dữ liệu")["frozen"] == 1
    sid = gia.tab("Dữ liệu")["sheet_id"]
    assert [b["range"] for p, b in gia.loc()] == [f"{sid}!A1:J3"]
    tq = " ".join(str(r[0]) for r in gia.o("Tổng quan"))
    assert "Nguồn: web_crawl — tầng catalog_json" in meta(gia.o("Tổng quan")) and "đồng (VND)" in tq
    assert "TOP 5 GIẢM GIÁ SÂU NHẤT" in tq
    assert kq["day_du"] is True and kq["kiem_ghi"] in kq["note"] and kq["granted"] is True
    ghi = [i for i, g in enumerate(gia.goi) if g[1].endswith("values_batch_update")]
    assert chay.luc and chay.luc[0] > max(ghi), "cấp quyền SAU khi ghi xong"
    assert T.TAB_GOC not in gia.tab_ten(), "runner trả đủ trường đã lên sheet: không cần gốc"


def test_web_ngoai_khong_chac_tien_te_thi_so_tron_va_cham_tran(chay):
    kq, _ = chay(url="example.com/shop", tang="html_gia", max_products=2)
    gia = chay.gia
    assert "#,##0" in _fmt(gia, 2) and not any("₫" in f for f in _fmt(gia, 2))
    tq = " ".join(str(r[0]) for r in gia.o("Tổng quan"))
    assert "không xác định chắc" in tq and "CHẠM TRẦN 2 sản phẩm" in tq
    assert "đoán theo mẫu giá" in tq
    assert kq["cham_tran"] is True


def test_adapter_co_du_lieu_goc_khong_lot_ra_tool_result(chay, monkeypatch):
    import crawl_adapters
    goc = {"name": "Áo thun", "promoPrice": 199000, "currency": "VND", "colors": ["Đen", "Trắng"],
           "productId": "E489147-000"}
    sp = [dict(SP[1], ten="Áo thun", sku="E489147-000", __goc=goc)]
    monkeypatch.setattr(crawl_adapters, "chay", lambda url, n, log: {
        "san_pham": sp, "adapter": "Uniqlo", "actor_da_dung": ["rl1987~uniqlo-api-scraper"],
        "uoc_tinh_chi_phi_usd": 0.0005, "ghi_chu": "Uniqlo trùng tên"})
    kq, raw = chay(sp=[], url="https://www.uniqlo.com/vn/vi/")
    gia = chay.gia
    assert gia.tab_ten() == ["Tổng quan", "Dữ liệu", T.TAB_GOC]
    g = gia.o(T.TAB_GOC)
    assert "colors" in g[0] and g[1][g[0].index("productId")] == "E489147-000"
    assert "colors" not in raw and "__goc" not in raw
    assert "#,##0" in _fmt(gia, 2), "currency VND của bản ghi adapter"
    tq = " ".join(str(r[0]) for r in gia.o("Tổng quan"))
    assert "Adapter CÓ TÍNH TIỀN" in tq and "Uniqlo trùng tên" in tq


def test_trang_tri_hong_van_co_link_va_du_lieu(chay):
    chay.gia.hong = {"styles_batch_update", "/filter", "merge_cells"}
    kq, _ = chay()
    assert kq["success"] is True and kq["sheet_url"]
    assert len(chay.gia.o("Dữ liệu")) == 3 and kq["day_du"] is True


def test_ghi_hong_thi_bao_loi_khong_link(chay):
    chay.gia.hong = {"values_batch_update"}
    kq, _ = chay()
    assert kq["success"] is False and kq["sheet_url"] is None
    assert "GHI SHEET THẤT BẠI" in kq["error"]
