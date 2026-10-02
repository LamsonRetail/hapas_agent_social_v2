"""Quét NỀN: bài của brand ở nước khác sang tab riêng "Thị trường khác" (chốt 02/10/2026).

Tab nền tảng (TikTok, YouTube…) chỉ còn bài của thị trường đang quét; bài HAPAS ở Thái
không bị coi là rác (không vào "Bị loại"), mà nằm ở tab riêng, và tin kết quả + tab
Tổng hợp nói rõ số bài đó. Hỏi nhiều nước (`giu_nuoc_ngoai`) thì chung tab như cũ.
Sheet là giả — không gọi Lark thật.
"""
from __future__ import annotations

import datetime

import pytest

import apify_tool as A
import quet_lon
import sheet_lon

DT = datetime.datetime(2026, 9, 30, 10, 0, tzinfo=A._VN_TZ)


def _bai(p, kenh, tt):
    return ({"platform": p, "kenh": kenh, "followers": 0, "views": 10, "likes": 0,
             "comments": 0, "shares": 0, "hashtags": "", "text": f"HAPAS {kenh}",
             "link": f"https://x/{kenh}", "_thi_truong": tt, "_nhan_dinh": "brand",
             "_phan_xu": "AI"}, DT)


class _V:
    ma = "Q1"

    def __init__(self):
        self.d = {"nen_tang": {"tiktok": {}, "youtube": {}}, "nguoi_yeu_cau": "",
                  "ngan_sach_usd": 1.0}


@pytest.fixture
def chay(monkeypatch):
    tabs: dict[str, list] = {}

    class SoGia:
        def __init__(self, v):
            self.s = {"url": "https://sheet", "tabs": {}}

        def dam_bao(self, *a, **k):
            pass

        def bat_dau_giai_doan(self, *a):
            pass

        def ghi_tab(self, ten, bang, tu_dau=False):
            tabs[ten] = bang
            return len(bang)
    monkeypatch.setattr(sheet_lon, "SoSheet", SoGia)

    def goi(giu_nuoc_ngoai=False):
        ts = {"queries": ["hapas"], "date_from": "2026-09-18", "date_to": "2026-10-02",
              "country": "VN", "giu_nuoc_ngoai": giu_nuoc_ngoai}
        hits = [_bai("tiktok", "Ngọc Trâm", "VN"), _bai("youtube", "Shop Thái", "TH"),
                _bai("youtube", "Kênh lạ", "không rõ")]
        ket = {"hits": hits, "bi_loai": [],
               "per": {p: {"scraped": 2, "trung_lap": 0, "trong_khoang": 2, "giu": 1,
                           "loai": 0} for p in ("tiktok", "youtube")},
               "phan_xu": {}}
        v = _V()
        quet_lon._ghi_cuoi(v, ts, ket, {"usd": 0.1, "so_run": 1}, "xong")
        tin = quet_lon._tin_nhan(v, ts, ket, {"usd": 0.1, "so_run": 1}, "https://sheet",
                                 "xong", [])
        return tabs, tin
    return goi


def _kenh(bang):
    return [r[2] for r in bang[1:]]


def test_bai_nuoc_khac_sang_tab_rieng_tab_nen_tang_chi_con_vn(chay):
    tabs, tin = chay()
    assert _kenh(tabs["TikTok"]) == ["Ngọc Trâm"]
    assert _kenh(tabs["YouTube"]) == ["Kênh lạ"], "không rõ thị trường vẫn ở tab nền tảng"
    assert _kenh(tabs[A._TAB_THI_TRUONG_KHAC]) == ["Shop Thái"]
    assert tabs[A._TAB_THI_TRUONG_KHAC][0] == tabs["YouTube"][0], "cùng cột với tab nền tảng"
    assert quet_lon._TAB_LOAI not in tabs, "bài brand ở nước khác KHÔNG phải rác"
    cau = ("giữ 1 bài của brand ở nước khác (TH 1) ở tab riêng 'Thị trường khác' — các tab "
           "nền tảng chỉ có bài VN")
    assert [A._TAB_THI_TRUONG_KHAC, cau] in tabs[quet_lon._TAB_TONG]
    assert f"Thị trường khác: {cau}." in tin


def test_hoi_nhieu_nuoc_thi_chung_tab_nen_tang(chay):
    tabs, tin = chay(giu_nuoc_ngoai=True)
    assert _kenh(tabs["YouTube"]) == ["Shop Thái", "Kênh lạ"]
    assert A._TAB_THI_TRUONG_KHAC not in tabs
    assert "Thị trường khác:" not in tin
