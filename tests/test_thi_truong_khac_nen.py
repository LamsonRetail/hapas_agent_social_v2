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
# Bản thật — fixture `chay` thay bằng bản giả; bài kiểm "đổi thứ tự hỏng" cần bản thật.
_DUA_TAB_THAT = A._dua_tab_chinh_len_dau


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
    # Sổ sheet DÙNG CHUNG giữa các lượt `_ghi_cuoi` như sổ việc thật (v.d["sheet"]): việc
    # tiếp tục sau `xong_mot_phan` thấy lại các tab lượt trước đã tạo.
    so = {"url": "https://sheet", "token": "shtA", "tabs": {}}
    tao: list[str] = []
    dua: list[tuple] = []

    class SoGia:
        def __init__(self, v):
            self.s = so

        def dam_bao(self, title, tab_dau, nguoi=""):
            so["tabs"].setdefault(tab_dau, {"sheet_id": "s0"})

        def bat_dau_giai_doan(self, *a):
            pass

        def ghi_tab(self, ten, bang, tu_dau=False):
            if ten not in so["tabs"]:
                tao.append(ten)
                so["tabs"][ten] = {"sheet_id": f"sid-{ten}"}
            tabs[ten] = bang
            return len(bang)
    monkeypatch.setattr(sheet_lon, "SoSheet", SoGia)
    monkeypatch.setattr(A, "_dua_tab_chinh_len_dau", lambda tok, sid: dua.append((tok, sid)))

    def goi(giu_nuoc_ngoai=False, hits=None, bi_loai=()):
        ts = {"queries": ["hapas"], "date_from": "2026-09-18", "date_to": "2026-10-02",
              "country": "VN", "giu_nuoc_ngoai": giu_nuoc_ngoai}
        if hits is None:
            hits = [_bai("tiktok", "Ngọc Trâm", "VN"), _bai("youtube", "Shop Thái", "TH"),
                    _bai("youtube", "Kênh lạ", "không rõ")]
        ket = {"hits": hits, "bi_loai": list(bi_loai),
               "per": {p: {"scraped": 2, "trung_lap": 0, "trong_khoang": 2, "giu": 1,
                           "loai": 0} for p in ("tiktok", "youtube")},
               "phan_xu": {}}
        v = _V()
        quet_lon._ghi_cuoi(v, ts, ket, {"usd": 0.1, "so_run": 1}, "xong")
        tin = quet_lon._tin_nhan(v, ts, ket, {"usd": 0.1, "so_run": 1}, "https://sheet",
                                 "xong", [])
        return tabs, tin
    goi.tao, goi.dua = tao, dua
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


def test_viec_tiep_tuc_khong_con_bai_nuoc_khac_thi_xoa_tab_cu(chay):
    """Việc tiếp tục (`xong_mot_phan` → `_ghi_cuoi` chạy lại) mà lượt sau KHÔNG còn bài nước
    khác / bài bị loại: tab cũ ghi lại chỉ tiêu đề (xoá dòng cũ), không để bài lượt trước."""
    vn = _bai("tiktok", "Ngọc Trâm", "VN")
    loai = (_bai("youtube", "Ban nhạc", "không rõ")[0], DT, "AI: trùng tên")
    tabs, _ = chay(bi_loai=[loai])
    assert _kenh(tabs[A._TAB_THI_TRUONG_KHAC]) == ["Shop Thái"]
    assert _kenh(tabs[quet_lon._TAB_LOAI]) == ["Ban nhạc"]
    # Tiêu đề lúc CÓ dòng (gồm cột cuối "Loại video TikTok") — bản chỉ-tiêu-đề phải y hệt.
    hd_khac, hd_loai = tabs[A._TAB_THI_TRUONG_KHAC][0], tabs[quet_lon._TAB_LOAI][0]
    tabs, tin = chay(hits=[vn])
    assert tabs[A._TAB_THI_TRUONG_KHAC] == [hd_khac] == [
        list(A._HEADER) + quet_lon._COT_THEM + quet_lon._COT_CUOI]
    assert tabs[quet_lon._TAB_LOAI] == [hd_loai] == [
        list(A._HEADER) + ["Thị trường", "Lý do loại", "Phân xử"] + quet_lon._COT_CUOI]
    assert "Thị trường khác:" not in tin
    assert chay.tao.count(A._TAB_THI_TRUONG_KHAC) == 1, "ghi lại tab cũ, không tạo tab mới"


def test_khong_bai_nuoc_khac_khong_bi_loai_thi_khong_tao_tab_trong(chay):
    tabs, _ = chay(hits=[_bai("tiktok", "Ngọc Trâm", "VN")])
    assert A._TAB_THI_TRUONG_KHAC not in tabs and quet_lon._TAB_LOAI not in tabs
    assert A._TAB_THI_TRUONG_KHAC not in chay.tao and quet_lon._TAB_LOAI not in chay.tao


def test_tong_hop_ve_dau_sau_khi_ghi_xong(chay):
    """addSheet của Lark chèn tab mới ở vị trí 0: sau khi ghi hết, kéo "Tổng hợp" về đầu."""
    chay()
    assert chay.dua == [("shtA", "s0")]


def test_doi_thu_tu_tab_hong_khong_lam_hong_ghi_cuoi(chay, monkeypatch):
    monkeypatch.setattr(A, "_dua_tab_chinh_len_dau", _DUA_TAB_THAT)

    def lark_hong(*a, **k):
        raise RuntimeError("lark 500")
    monkeypatch.setattr(A.lark, "call", lark_hong)
    tabs, _ = chay()
    assert _kenh(tabs[A._TAB_THI_TRUONG_KHAC]) == ["Shop Thái"]
    assert quet_lon._TAB_TONG in tabs
