"""Công tắc + trần USD riêng của console (Quét mạng xã hội) cho MỌI nền tảng bóc bình luận.

04/10/2026: chỉ Threads/Instagram theo `bat_<p>`/`tran_usd_<p>`; chủ agent đặt
`bat_tiktok=0` mà social_deep_dive vẫn bóc bình luận TikTok. Nay cả TikTok, YouTube
(API lẫn dự phòng) và Facebook, ở lượt tại chỗ lẫn việc nền; trần của tool và trần riêng
console lấy mức CHẶT hơn. Không bài nào gọi Apify/YouTube/Lark/model thật.
"""
from __future__ import annotations

import json

import pytest

import apify_tool as A
import deep_dive_tool as D

TT = "https://www.tiktok.com/@hapas/video/7000000000000000001"
TT2 = "https://www.tiktok.com/@hapas/video/7000000000000000002"
YT = "https://www.youtube.com/watch?v=AAAAAAAAAA1"
FB = "https://www.facebook.com/hapas/posts/1"


class _Apify:
    def __init__(self):
        self.goi = []

    def __call__(self, actor, payload, limit, mem=None, min_charge=0, tran_usd=None):
        self.goi.append({"actor": actor, "payload": payload, "tran_usd": tran_usd})
        if actor == D._ACTORS["tiktok"]:
            return [{"uniqueId": "a", "text": "đẹp", "diggCount": 1, "videoWebUrl": u}
                    for u in payload["postURLs"]]
        if actor == D._ACTORS["youtube"]:
            return [{"author": "@b", "comment": "hay", "pageUrl": x["url"]}
                    for x in payload["startUrls"]]
        return [{"profileName": "c", "text": "ok", "facebookUrl": x["url"]}
                for x in payload["startUrls"]]


@pytest.fixture
def mt(monkeypatch):
    ap = _Apify()
    cfg: dict = {}
    monkeypatch.setattr(D, "_call", ap)
    monkeypatch.setattr(D, "_cau_hinh", lambda: (3000, 2.0))
    monkeypatch.setattr(A, "_cau_hinh_quet", lambda: cfg)
    monkeypatch.setattr(A, "_tran", lambda nen=None: (500, 0.37))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {})
    monkeypatch.setattr(D.chi_phi_tool, "ghi", lambda **k: {})
    monkeypatch.setattr(D.phan_loai, "_goi_model", lambda nhac: "{}")
    monkeypatch.setattr(D, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(D, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(D, "_write", lambda *a: None)
    monkeypatch.setattr(A, "_them_tab", lambda tok, ten: "s2")
    monkeypatch.setattr(A, "_write_values", lambda *a, **k: None)
    monkeypatch.setattr(D, "_grant", lambda tok, oid: True)
    monkeypatch.setattr(D.memory_store, "get_current_sender", lambda: "ou_test")
    return ap, cfg


@pytest.mark.parametrize("p,url", [("tiktok", TT), ("facebook", FB), ("youtube", YT)])
def test_tat_tren_console_thi_khong_boc_moi_nen_tang(mt, p, url):
    ap, cfg = mt
    cfg[f"bat_{p}"] = 0
    kq = json.loads(D._handle({"post_urls": [url]}))
    assert ap.goi == [] and f"đã tắt {A._TEN_NGUON[p]}" in kq["error"]
    other = TT2 if p != "tiktok" else YT
    kq = json.loads(D._handle({"post_urls": [url, other]}))
    assert kq["per_url"][url]["status"] == "ĐÃ TẮT" and kq["nen_tang_da_tat"] == [p]
    assert all(g["actor"] != D._ACTORS[p] for g in ap.goi)


def test_tat_youtube_chan_ca_duong_api_mien_phi(mt, monkeypatch):
    ap, cfg = mt
    goi_api = []
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "AIzaGIA")
    monkeypatch.setattr(A.requests, "get", lambda *a, **k: goi_api.append(a) or None)
    cfg["bat_youtube"] = 0
    kq = json.loads(D._handle({"post_urls": [YT]}))
    assert goi_api == [] and ap.goi == [] and "YouTube" in kq["error"]


def test_tran_usd_rieng_tiktok_chat_hon_tran_tool(mt):
    ap, cfg = mt
    cfg["tran_usd_tiktok"] = 0.2
    kq = json.loads(D._handle({"post_urls": [TT, TT2], "max_comments": 200}))
    # 0,9 × 0,2 / 0,00125 = 144 bình luận mỗi lượt → 144/bài, mỗi lượt một bài.
    assert kq["max_comments_thuc"] == {"tiktok": 144}
    assert len(ap.goi) == 2 and all(g["tran_usd"] <= 0.2 for g in ap.goi)


def test_tran_tool_chat_hon_tran_console_thi_lay_tran_tool(mt, monkeypatch):
    ap, cfg = mt
    cfg["tran_usd_tiktok"] = 3.0
    monkeypatch.setattr(D, "_cau_hinh", lambda: (3000, 0.15))
    json.loads(D._handle({"post_urls": [TT], "max_comments": 50}))
    assert ap.goi[0]["tran_usd"] <= 0.15


def test_tran_rieng_facebook_duoi_muc_actor_doi_thi_tu_choi_ro(mt):
    ap, cfg = mt
    cfg["tran_usd_facebook"] = 0.3
    kq = json.loads(D._handle({"post_urls": [FB, TT]}))
    e = kq["per_url"][FB]
    assert e["status"] == "LỖI" and "tran_usd_facebook" in e["error"] and "0,30" in e["error"]
    assert [g["actor"] for g in ap.goi] == [D._ACTORS["tiktok"]]


def test_youtube_du_phong_khong_co_tran_usd_rieng(mt):
    """`tran_usd_youtube` không tồn tại (YouTube là API miễn phí) — dự phòng theo trần tool."""
    ap, cfg = mt
    cfg["tran_usd_youtube"] = 0.1
    json.loads(D._handle({"post_urls": [YT], "max_comments": 20}))
    assert ap.goi[0]["actor"] == D._ACTORS["youtube"] and ap.goi[0]["tran_usd"] >= 0.5


def test_tran_usd_thap_khong_chan_youtube_api(mt, monkeypatch):
    ap, cfg = mt
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "AIzaGIA")

    class R:
        status_code = 200

        def json(self):
            return {"items": [{"id": "c1", "snippet": {"totalReplyCount": 0, "topLevelComment": {
                "id": "c1", "snippet": {"authorDisplayName": "a", "textOriginal": "xinh"}}}}]}
    monkeypatch.setattr(A.requests, "get", lambda *a, **k: R())
    monkeypatch.setattr(D, "_cau_hinh", lambda: (300, 0.1))
    cfg["tran_usd_tiktok"] = 0.1
    kq = json.loads(D._handle({"post_urls": [YT]}))
    assert ap.goi == [] and kq["per_url"][YT]["status"] == "OK" and kq["tong_comment"] == 1


# ───────────────────────── việc nền ─────────────────────────
def test_viec_nen_lo_theo_tran_rieng(mt):
    ap, cfg = mt
    cfg["tran_usd_facebook"] = 0.6
    nt = D._ke_hoach_nen({"facebook": D._chia_lo("facebook", [FB], 400, 5.0)}, 5.0)
    ph = nt["facebook"]["phan"][0]
    assert ph["tran_lo"] <= 0.6 and ph["per"] < 400


class _Viec:
    def __init__(self, nt):
        self.d = {"nen_tang": nt}

    def cac_phan(self):
        for p, x in self.d["nen_tang"].items():
            for ph in x["phan"]:
                yield p, ph

    def cap_nhat_phan(self, ph, **kw):
        ph.update(kw)


def test_viec_nen_tat_sau_khi_tao_thi_bo_luot_chua_chay(mt):
    ap, cfg = mt
    v = _Viec({"tiktok": {"phan": [{"id": "t0", "trang_thai": "cho"},
                                   {"id": "t1", "trang_thai": "dang_chay"}]},
               "facebook": {"phan": [{"id": "f0", "trang_thai": "cho"}]}})
    cfg["bat_tiktok"] = 0
    ly_do: list = []
    D._bo_nen_tang_da_tat(v, ly_do)
    t0, t1 = v.d["nen_tang"]["tiktok"]["phan"]
    assert t0["trang_thai"] == "loi" and t0["ma"] == "DA_TAT" and t0["usd_so"] == 0.0
    assert t1["trang_thai"] == "dang_chay", "lượt đang chạy dở để quet_lon đọc tiếp"
    assert v.d["nen_tang"]["facebook"]["phan"][0]["trang_thai"] == "cho"
    assert ly_do and "TikTok" in ly_do[0]
