"""22/10/2026 (chủ dự án): biểu đồ "Theo ngày" trang Quảng cáo thêm hai chuỗi xem trang sản phẩm —
"Xem trang SP TikTok Shop" (TikTok `onsite_on_web_detail`) và "Xem SP website (Meta)" (Meta Pixel
`actions__view_content`). Mỗi chuỗi một nền tảng, không gộp, định nghĩa rõ; không phải tiền."""
from __future__ import annotations

import datetime
import math
from pathlib import Path

import pytest
from test_dashboard_app import QL, dang_nhap
from test_meta_ads_dashboard import _app_hai_nen_tang
from test_tiktok_ads import Q, _co_so, _tao_app

from dashboard import kho_qc as KQ
from dashboard import quang_cao as QC
from dashboard import tiktok_ads as TA

GOC = Path(__file__).resolve().parent.parent


def test_chi_so_hop_le_co_onsite_on_web_detail_va_khong_ten_tu_choi():
    assert "onsite_on_web_detail" in QC.CHI_SO_HOP_LE
    assert len(QC.CHI_SO_HOP_LE) == len(set(QC.CHI_SO_HOP_LE)) == 101
    # = xem ÷ click (> 100%) — không xin, không hiện như tỉ lệ.
    assert "onsite_on_web_detail_rate" not in QC.CHI_SO_HOP_LE
    for ten in ("shop_page_view", "product_page_view", "total_product_detail_page_view",
                "onsite_shopping_page_view", "product_clicks", "onsite_product_view",
                "live_product_clicks_rate", "shop_visits"):
        assert ten in QC.TEN_TU_CHOI
    for ds in (QC.CHI_SO_HOP_LE, QC.CHI_SO_AD, QC.THUOC_TINH_CAMPAIGN, QC.THUOC_TINH_AD_GIU):
        assert not set(ds) & set(QC.TEN_TU_CHOI)


def test_so_lo_goi_khong_doi():
    """Cấp tài khoản + campaign vẫn 3 lô × 45; cấp ad đúng 45 tên = 1 lô (không thêm tên mới)."""
    lo = TA.LO_CHI_SO
    assert math.ceil(len(QC.CHI_SO_HOP_LE) / lo) == 3
    assert math.ceil(len(QC.THUOC_TINH_CAMPAIGN + QC.CHI_SO_HOP_LE) / lo) == 3
    assert len(QC.THUOC_TINH_AD_GIU + QC.CHI_SO_AD) == lo
    assert "onsite_on_web_detail" not in QC.CHI_SO_AD


def test_chuoi_xem_sp_dinh_nghia_va_khong_phai_tien():
    d = {c[0]: c for c in QC.CHUOI_XEM_SP}
    assert d["xem_sp_shop"][1:4] == ("onsite_on_web_detail", "tiktok", "Xem trang SP TikTok Shop")
    assert d["xem_sp_web"][1:4] == ("actions__view_content", "meta", "Xem SP website (Meta)")
    assert "không phải số người" in d["xem_sp_shop"][4] and "trang chủ shop" in d["xem_sp_shop"][4]
    assert "WEBSITE" in d["xem_sp_web"][4] and "không phải Shop" in d["xem_sp_web"][4]
    for ma in QC.TEN_CHUOI_XEM_SP:
        assert not QC.la_tien(ma)
    assert QC.loc_tien({"xem_sp_shop": 3, "xem_sp_web": 2, "chi": 9}, False) == {
        "xem_sp_shop": 3, "xem_sp_web": 2}
    # Chỉ chuỗi có số ≠ 0 trong phạm vi.
    assert QC.chuoi_xem_sp([{"xem_sp_shop": 0, "xem_sp_web": 0}]) == []
    ra = QC.chuoi_xem_sp([{"xem_sp_shop": 2, "xem_sp_web": 0}, {"xem_sp_shop": 3}])
    assert [(x["ma"], x["nen_tang"], x["tong"]) for x in ra] == [("xem_sp_shop", "tiktok", 5)]


def test_sql_theo_ngay_cong_json_co_dinh(monkeypatch):
    s = KQ._TONG_XEM_SP
    assert "jsonb_typeof(chi_so->'onsite_on_web_detail') = 'number'" in s
    assert "(chi_so->>'actions__view_content')::numeric" in s
    assert "AS xem_sp_shop" in s and "AS xem_sp_web" in s and "%" not in s
    with pytest.raises(ValueError):
        KQ._tong_json("x'; DROP TABLE qc_tk_ngay; --", "xem")

    class Ket:
        def __init__(self):
            self.sql = []

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, tham):
            self.sql.append((sql, tham))
            return self

        def fetchall(self):
            return []
    k = Ket()
    monkeypatch.setattr(KQ, "ket_noi", lambda: k)
    KQ.qc_theo_ngay(["1"], datetime.date(2026, 10, 1), datetime.date(2026, 10, 2))
    sql, tham = k.sql[0]
    assert KQ._TONG_XEM_SP in sql and sql.count("%s") == 3 and len(tham) == 3


def test_api_qc_tiktok_co_xem_sp_shop_khong_co_web():
    _app, c, _kho, _kq, _tt, _dv = _co_so(_tao_app())
    dang_nhap(c, QL)
    d = c.get(f"/api/qc?{Q}").json()
    assert all("xem_sp_shop" in r and "xem_sp_web" in r for r in d["theo_ngay"])
    assert sum(r["xem_sp_shop"] for r in d["theo_ngay"]) > 0
    assert sum(r["xem_sp_web"] for r in d["theo_ngay"]) == 0
    assert [x["ma"] for x in d["chuoi_xem_sp"]] == ["xem_sp_shop"]
    assert all("xem_sp_shop" in r for r in d["theo_ngay_nen_tang"])
    t = c.get(f"/quang-cao?{Q}").text
    assert "Giải thích chỉ số xem trang sản phẩm" in t and "Xem trang SP TikTok Shop" in t
    assert "Xem SP website (Meta)" not in t.split('id="qc-api"')[0]


def test_api_qc_hai_nen_tang_moi_chuoi_mot_nen_tang():
    h = _app_hai_nen_tang()
    c, kq = h.c, h.kho_qc
    web = 0
    for r in kq.bang["qc_tk_ngay"].values():
        if r["advertiser_id"].startswith("act_"):
            r["chi_so"] = {**(r.get("chi_so") or {}), "actions__view_content": 7}
            web += 7 if QC.tk_dung([kq.tk[r["advertiser_id"]]]) else 0
    dang_nhap(c, QL)
    d = c.get(f"/api/qc?{Q}").json()
    assert [x["ma"] for x in d["chuoi_xem_sp"]] == ["xem_sp_shop", "xem_sp_web"]
    assert [x["nen_tang"] for x in d["chuoi_xem_sp"]] == ["tiktok", "meta"]
    assert sum(r["xem_sp_web"] for r in d["theo_ngay"]) == web > 0
    # Không lẫn: dòng Meta không có xem trang SP Shop, dòng TikTok không có xem SP website.
    for r in d["theo_ngay_nen_tang"]:
        assert r["xem_sp_shop" if r["nen_tang"] == "meta" else "xem_sp_web"] == 0
    m = c.get(f"/api/qc?{Q}&nen_tang=meta").json()
    assert [x["ma"] for x in m["chuoi_xem_sp"]] == ["xem_sp_web"]
    tk = c.get(f"/api/qc?{Q}&nen_tang=tiktok").json()
    assert [x["ma"] for x in tk["chuoi_xem_sp"]] == ["xem_sp_shop"]
    t = c.get(f"/quang-cao?{Q}").text
    assert "không cộng với nhau" in t and "Meta Pixel ViewContent" in t


def test_bieu_do_chuoi_rieng_khong_chong():
    js = (GOC / "dashboard" / "static" / "qc.js").read_text(encoding="utf-8")
    assert "p.chuoi_xem_sp" in js and "var xep = chong && !nenRieng" in js
    assert "if (xep)" in js and "if (chong) {" not in js
