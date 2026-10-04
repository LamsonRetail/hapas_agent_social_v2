"""Canh bảng ngành TikTok (nganh_tiktok.py) và bộ lọc ngành của chế độ `trend`.

Mã ngành đọc từ input schema của ba actor ngày 04/10/2026: azzouzana nhận NHÃN chữ (có
ngành con), lexis nhận mã hai số, data_xplorer (`industryId`) nhận mã 11 số của ngành cha.
"""
from __future__ import annotations

import json

import pytest

import apify_tool as A
import nganh_tiktok as N
import tiktok_trend as T


@pytest.mark.parametrize("cau, khoa, nhan, nhom", [
    ("thời trang", "thoi_trang", "Apparel & Accessories", "22"),
    ("Thời Trang", "thoi_trang", "Apparel & Accessories", "22"),
    ("thoi trang", "thoi_trang", "Apparel & Accessories", "22"),
    ("quần áo", "thoi_trang", "Apparel & Accessories", "22"),
    ("Apparel & Accessories", "thoi_trang", "Apparel & Accessories", "22"),
    ("22", "thoi_trang", "Apparel & Accessories", "22"),
    ("22000000000", "thoi_trang", "Apparel & Accessories", "22"),
    ("túi xách", "tui_xach", "Bags", "22"),
    ("túi", "tui_xach", "Bags", "22"),
    ("tui xach", "tui_xach", "Bags", "22"),
    ("túi xách thời trang", "tui_xach", "Bags", "22"),
    ("balo", "tui_xach", "Bags", "22"),
    ("trang sức", "trang_suc", "Ordinary Jewellery", "22"),
    ("phụ kiện trang sức", "trang_suc", "Ordinary Jewellery", "22"),
    ("trang sức cao cấp", "trang_suc_cao_cap", "High-end Jewellery", "22"),
    ("phụ kiện", "phu_kien_thoi_trang", "Clothing Accessories", "22"),
    ("thời trang nữ", "thoi_trang_nu", "Women's Clothing", "22"),
    ("giày nữ", "giay_nu", "Women's Shoes", "22"),
    ("đồng hồ", "dong_ho", "Watches", "22"),
    ("nước hoa", "nuoc_hoa", "Fragrances & Perfumes", "14"),
    ("nuoc hoa", "nuoc_hoa", "Fragrances & Perfumes", "14"),
    ("mỹ phẩm", "lam_dep", "Beauty & Personal Care (14000000000)", "14"),
    ("son môi", "trang_diem", "Cosmetics", "14"),
    ("skincare", "cham_soc_da", "Skincare", "14"),
    ("mẹ và bé", "me_be", "Baby, Kids & Maternity", "12"),
    ("đồ ăn", "an_uong", "Food & Beverage", "27"),
])
def test_cau_tieng_viet_ra_dung_nganh(cau, khoa, nhan, nhom):
    n = N.tim(cau)
    assert n and (n["khoa"], n["nhan_actor"], n["nhom"]) == (khoa, nhan, nhom)
    assert n["id_trend"] == nhom + "000000000"


@pytest.mark.parametrize("cau", [
    "thời trang & phụ kiện", "thời trang và phụ kiện", "Thời trang & Phụ kiện",
    "thoi trang va phu kien", "thời trang", "ngành thời trang & phụ kiện"])
def test_cum_nganh_cha_thang_nganh_con_hep_hon(cau):
    """E2E 04-05/10/2026: "thời trang & phụ kiện" khớp "phụ kiện" của Clothing Accessories
    trước dòng cha Apparel & Accessories — khớp cụm đầu tiên thay vì cụm tốt nhất."""
    n = N.tim(cau)
    assert n and n["khoa"] == "thoi_trang" and n["nhan_actor"] == "Apparel & Accessories"
    assert n["la_nganh_con"] is False


@pytest.mark.parametrize("cau, khoa", [
    ("túi xách", "tui_xach"), ("túi xách thời trang", "tui_xach"),
    ("phụ kiện", "phu_kien_thoi_trang"), ("phụ kiện thời trang", "phu_kien_thoi_trang"),
    ("phụ kiện trang sức", "trang_suc"), ("trang sức cao cấp", "trang_suc_cao_cap"),
    ("thời trang nữ", "thoi_trang_nu"), ("giày nữ", "giay_nu")])
def test_cum_dai_nhat_thang_va_nganh_con_giu_nhu_cu(cau, khoa):
    assert N.tim(cau)["khoa"] == khoa


@pytest.mark.parametrize("cau", ["", "vũ trụ", "tui", "vay", "vi", "123"])
def test_khong_doan_bua(cau):
    """Bỏ dấu chỉ cho cụm dài: "tui" (= tôi), "vay" (vay tiền), "vi" (ví/vì)."""
    assert N.tim(cau) is None


def test_nganh_con_duoc_danh_dau_de_bao_loc_rong_hon():
    assert N.tim("túi")["la_nganh_con"] is True
    assert N.tim("túi")["ten_nhom"] == "Apparel & Accessories"
    assert N.tim("thời trang")["la_nganh_con"] is False
    assert N.tim("mỹ phẩm")["la_nganh_con"] is False


def test_moi_nhom_trend_deu_nam_trong_enum_cua_actor():
    enum = {"10000000000", "11000000000", "12000000000", "14000000000", "15000000000",
            "17000000000", "18000000000", "19000000000", "21000000000", "22000000000",
            "23000000000", "25000000000", "27000000000", "28000000000", "29000000000"}
    for d in N._BANG:
        assert N._ra(d)["id_trend"] in enum, d[0]


def test_ten_nhom_tu_industry_key():
    assert N.ten_nhom_tu_key("label_22104000000") == "Apparel & Accessories"
    assert N.ten_nhom_tu_key("label_14000000000") == "Beauty & Personal Care"
    assert N.ten_nhom_tu_key(None) == ""


# ───────────────────────────── chế độ trend ─────────────────────────────
@pytest.fixture
def trend(monkeypatch):
    goi: list = []

    def call(actor, payload, limit, mem=None, **kw):
        goi.append((actor, payload))
        if actor == T.ACTOR_TREND and payload["trendType"] == "hashtags":
            return [{"Rank": 1, "Hashtag": "#outfit", "Trend Direction": "up", "Posts": 10,
                     "Video Views": 100, "Industries": ["Apparel & Accessories"],
                     "TikTok URL": "https://t/1"}]
        return []

    monkeypatch.setattr(A, "_call", call)
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, *a, **k: (800, 2.4, True))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(T.chi_phi_tool, "ghi", lambda **k: {})
    monkeypatch.setattr(A, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(A, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(A, "_write_values", lambda *a, **k: None)
    monkeypatch.setattr(T.memory_store, "get_current_sender", lambda: None)
    return goi


def _tag(goi):
    return [p for a, p in goi if a == T.ACTOR_TREND and p["trendType"] == "hashtags"]


def test_trend_theo_nganh_gui_industry_id(trend):
    kq = json.loads(A._handle({"che_do": "trend", "nganh": "túi xách", "so_video_mau": 0,
                               "so_nhac": 0}))
    assert _tag(trend)[0]["industryId"] == "22000000000"
    assert kq["nganh"] == {"ten": "Túi xách", "loc_theo": "Apparel & Accessories",
                           "industry_id": "22000000000"}
    assert "top video KHÔNG lọc" in kq["note"] and "ngành cha" in kq["note"]


def test_trend_khong_nganh_thi_payload_y_cu(trend):
    kq = json.loads(A._handle({"che_do": "trend", "so_video_mau": 0, "so_nhac": 0}))
    assert "industryId" not in _tag(trend)[0] and kq["nganh"] is None


def test_trend_nganh_la_thi_bao_khong_chay(trend):
    kq = json.loads(A._handle({"che_do": "trend", "nganh": "vũ trụ"}))
    assert "error" in kq and not trend


def test_schema_social_listen_co_tham_so_nganh():
    assert "nganh" in A.SCHEMA["parameters"]["properties"]
