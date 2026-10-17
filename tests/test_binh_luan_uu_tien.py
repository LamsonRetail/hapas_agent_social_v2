"""Bình luận: ưu tiên bài chưa cào thiếu nhiều nhất, đọc tiếp video TikTok cào dở (18/10/2026).

Chủ dự án 18/10: "các luồng cào để tối ưu output nhất có thể" — bình luận là đầu vào sắc thái /
chủ đề. Đo kho production 17/10: TikTok chỉ có ~30% số bình luận nền tảng báo; 2 video 5.181 và
4.752 bình luận chưa cào dòng nào. Lý do: lô "cào hết" xếp theo cỡ TĂNG dần → bài to luôn chạy
cuối, hết tiền thì bị bỏ (`bl_lay_luc` NULL) và lượt sau chọn lại đúng nó rồi lại bỏ (lượt 5–6:
5 lô TikTok "bỏ qua (trần còn 0,00 USD)"). Mỗi lần cào lại một video dở cũng đọc lại từ trang đầu."""
from __future__ import annotations

import datetime
import inspect

import pytest

import apify_tool as A
import lang_nghe_db as K
import theo_doi as T
import tiktok_api as TT

VN = datetime.timezone(datetime.timedelta(hours=7))
LUC = datetime.datetime(2026, 10, 17, 9, 0, tzinfo=VN)


def _bai(khoa, co, *, lay=None, da=None, khi_co=None, goc=0, p="tiktok"):
    return {"khoa": khoa, "nen_tang": p, "link": f"https://www.tiktok.com/@k/video/{abs(hash(khoa))}",
            "tai_khoan": "k", "tac_gia": "k", "binh_luan": co, "bl_lay_luc": lay, "bl_da_lay": da,
            "bl_lay_khi_co": khi_co, "nguon_loai": None, "bl_goc": goc}


#: Hai video THẬT chưa cào dòng nào (kho 17/10) + một video nhỏ + một video cào dở (40 gốc).
DS = [_bai("nho", 30), _bai("v5181", 5181), _bai("do", 150, lay=LUC, da=50, khi_co=150, goc=40),
      _bai("v4752", 4752)]


def test_lo_uu_tien_bai_chua_cao_thieu_nhieu_nhat(monkeypatch):
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 2.0, True))
    lo = T._chia_lo_bl("tiktok", list(DS), 0)
    # Trần console 2 USD → lô ≤ 0,9 × 2 / (0,0004 × 1,3) = 3.461 bình luận; video to một mình.
    assert [[b["khoa"] for b in x] for x, _ in lo] == [["v5181"], ["v4752"], ["nho", "do"]]
    # Trước 18/10 (cỡ tăng dần): [nho, do], [v4752], [v5181] — video to luôn đứng cuối.
    assert min(DS, key=T._uu_tien_bl)["khoa"] == "v5181"
    lo_co_dinh = T._chia_lo_bl("tiktok", list(DS), 20)              # bl_moi_bai > 0
    assert [b["khoa"] for b in lo_co_dinh[0][0]][:2] == ["v5181", "v4752"]


def test_doc_tiep_video_tiktok_cao_do():
    assert T._doc_tiep_tiktok(DS[2]) == 40                       # cào dở: 50 / 150 < 80%
    assert T._doc_tiep_tiktok(DS[1]) == 0                        # chưa cào: đọc từ đầu
    du = dict(DS[2], bl_da_lay=130)                              # 130 / 150 ≥ 80%: đã đủ
    assert T._doc_tiep_tiktok(du) == 0
    assert T._doc_tiep_tiktok(dict(DS[2], nen_tang="facebook")) == 0
    # Chỉ xin phần CÒN THIẾU: int((150 − 50) × 1,15) + 10 = 124 thay vì int(150 × 1,15) + 10 = 182.
    assert T._can_bl(DS[2], 0) == 124 and T._can_bl(DS[1], 0) == 5968


@pytest.mark.tiktok_api
def test_phan_tiktok_mang_vi_tri_doc_tiep(monkeypatch):
    from test_theo_doi import GiaViec
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 2.0, True))
    v = GiaViec({}, [])
    T._tao_cac_phan_bl(v, list(DS), {"tiktok": 0})
    cac = T._phan_bl(v)
    assert [len(ph["bai"]) for ph in cac] == [1, 1, 2]
    assert all(ph["bo_chuyen"] == "tiktok_binh_luan" for ph in cac)
    assert "bat_dau" not in cac[0] and cac[2]["bat_dau"] == {DS[2]["link"]: 40}
    # Ước tính theo giá thật 0,0004/bình luận: video 5.181 = 5.968 × 0,0004 × 1,3 = 3,10 USD
    # (giá cũ 0,00075 → 5,82 USD, lô luôn bị bỏ vì vượt phần còn).
    assert cac[0]["uoc_usd"] == pytest.approx(5968 * 0.0004 * 1.3, abs=1e-4)


def test_tiktok_api_doc_tiep_tu_vi_tri_goc(monkeypatch):
    from test_tiktok_api import NOW, GiaApi
    api = GiaApi(monkeypatch)
    u = "https://www.tiktok.com/@kenh_a/video/70000555"

    def c(i):
        return {"cid": f"c{i}", "text": f"bl {i}", "create_time": int(NOW.timestamp()),
                "digg_count": 0, "reply_comment_total": 0, "reply_id": "0",
                "user": {"unique_id": f"khach{i}", "uid": f"k{i}"}}
    api.bl[("70000555", 100)] = ([c(i) for i in range(100, 150)], 1)
    api.bl[("70000555", 150)] = ([c(i) for i in range(150, 160)], 0)
    ra = TT.binh_luan([u], 200, tra_loi=0, bat_dau={u: 100})
    assert [g["listComments_cursor"] for g in api.goi] == [100, 150]   # không đọc lại trang 0, 50
    assert len(ra) == 60
    api.goi.clear()
    TT.binh_luan([u], 200, tra_loi=0)                                  # không có vị trí: từ đầu
    assert api.goi[0]["listComments_cursor"] == 0


def test_tran_lo_giu_cho_cac_lo_sau():
    # Phần còn của việc 1 USD, lô to ước 4 USD: các lô sau ước 0,8 → giữ tối đa 0,5 cho chúng.
    assert T._tran_lo_bl(2.0, 5.0, 1.0, 0.8, 4.0) == 0.5
    assert T._tran_lo_bl(2.0, 5.0, 1.0, 0.2, 4.0) == 0.8
    assert T._tran_lo_bl(2.0, 5.0, 1.0, 0.0, 4.0) == 1.0              # lô cuối: dùng hết
    assert T._tran_lo_bl(2.0, 5.0, 1.0, 0.0, 0.01) == 0.1             # sàn 0,1 của Apify
    assert T._tran_lo_bl(0.66, 5.0, 1.0, 0.0, 4.0) == 0.66            # trần console nền tảng


def test_cau_pheu_uu_tien_va_doc_tiep():
    c = T._cau_uu_tien_bl(list(DS))
    assert c[0] == "bình luận: ưu tiên 3 bài chưa cào thiếu nhiều nhất (TikTok 5.181, TikTok " \
                   "4.752, TikTok 30)"
    assert c[1] == "bình luận TikTok: đọc tiếp 1 video cào dở, bỏ 40 bình luận gốc đã có"
    assert T._cau_uu_tien_bl([]) == []


def test_sql_chon_bai_dem_binh_luan_goc_da_co():
    sql = inspect.getsource(K.bai_can_lay_binh_luan)
    assert "AS bl_goc" in sql and "NOT c.la_tra_loi" in sql
