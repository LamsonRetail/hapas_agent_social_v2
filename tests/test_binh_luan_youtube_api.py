"""Bình luận YouTube bằng YouTube Data API v3 trong social_deep_dive (04/10/2026).

API miễn phí là nguồn CHÍNH (0 USD, 1 đơn vị quota mỗi lượt gọi); actor
streamers~youtube-comments-scraper (đòi giữ 0,5 USD) chỉ còn là DỰ PHÒNG trong phần còn
lại của trần. Không bài nào gọi mạng thật: `requests.get` và `_call` đều là đồ giả.
"""
from __future__ import annotations

import contextvars
import json
import threading

import pytest

import apify_tool as A
import deep_dive_tool as D
import quet_lon

V1 = "https://www.youtube.com/watch?v=AAAAAAAAAA1"
V2 = "https://youtu.be/BBBBBBBBBB2"
TT = "https://www.tiktok.com/@hapas/video/7000000000000000001"


def _sn(ten, text, likes=0, t="2026-10-01T03:00:00Z"):
    return {"authorDisplayName": ten, "textOriginal": text, "textDisplay": text,
            "likeCount": likes, "publishedAt": t}


def _luong(cid, ten, text, likes, tong, kem=()):
    d = {"id": cid, "snippet": {"totalReplyCount": tong,
                                "topLevelComment": {"id": cid, "snippet": _sn(ten, text, likes)}}}
    if kem:
        d["replies"] = {"comments": [{"id": f"{cid}.{i}", "snippet": _sn(*k)}
                                     for i, k in enumerate(kem)]}
    return d


class _R:
    def __init__(self, code, data):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


def _loi(code, reason):
    return _R(code, {"error": {"code": code, "message": reason,
                               "errors": [{"reason": reason}]}})


class _YT:
    """`requests.get` giả của YouTube Data API: trang 1 có 2 luồng (luồng 1 kèm 1 trả lời
    trên tổng 3), trang 2 có 1 luồng; comments.list trả đủ 3 trả lời của luồng 1."""

    def __init__(self):
        self.goi: list[tuple[str, dict]] = []
        self.loi: dict = {}            # videoId -> (mã HTTP, reason)

    def __call__(self, url, params=None, timeout=None):
        res = url.rsplit("/", 1)[1]
        self.goi.append((res, dict(params or {})))
        vid = params.get("videoId")
        if vid in self.loi:
            return _loi(*self.loi[vid])
        if res == "commentThreads":
            if not params.get("pageToken"):
                return _R(200, {"nextPageToken": "p2", "items": [
                    _luong("c1", "An", "Túi đẹp quá &amp; xinh", 9, 3,
                           kem=[("Bình", "chuẩn luôn", 2)]),
                    _luong("c2", "Chi", "giá bao nhiêu ạ", 1, 0)]})
            return _R(200, {"items": [_luong("c3", "Dũng", "ship chậm quá", 0, 0)]})
        if res == "comments":
            return _R(200, {"items": [
                {"id": "c1.0", "snippet": _sn("Bình", "chuẩn luôn", 2)},
                {"id": "c1.x", "snippet": _sn("Em", "mua ở đâu", 0)},
                {"id": "c1.y", "snippet": _sn("Phương", "đẹp thật", 1)}]})
        return _R(404, {})


class _Apify:
    def __init__(self):
        self.goi = []
        self.hong = False

    def __call__(self, actor, payload, limit, mem=None, min_charge=0, tran_usd=None):
        self.goi.append({"actor": actor, "payload": payload, "limit": limit,
                         "min_charge": min_charge, "tran_usd": tran_usd})
        so = A._SO_RUN.get()
        if so is not None:
            so.append({"ma": "OK", "usd": 0.01, "run_id": "r1"})
        if actor == D._ACTORS["tiktok"]:
            return [{"uniqueId": "x", "text": "đẹp", "diggCount": 1, "videoWebUrl": TT}]
        return [{"author": "@z", "comment": "hay", "voteCount": 1, "replyCount": 0,
                 "publishedTimeText": "1 day ago", "pageUrl": u}
                for u in (payload.get("startUrls") and [x["url"] for x in payload["startUrls"]]
                          or [])]


@pytest.fixture
def mt(monkeypatch):
    yt, ap = _YT(), _Apify()
    sheet, so_cp = [], []
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "AIzaGIA_KHONG_THAT")
    monkeypatch.setattr(A.requests, "get", yt)
    monkeypatch.setattr(D, "_call", ap)
    monkeypatch.setattr(D, "_cau_hinh", lambda: (300, 0.5))
    monkeypatch.setattr(A, "_cau_hinh_quet", lambda: {})
    monkeypatch.setattr(A, "_tran", lambda nen=None: (500, 0.37))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda actors, *a, **k: {
        "usd": 0.01, "so_run": len(ap.goi), "cham_tran": 0, "dang_chay": 0})
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {})
    monkeypatch.setattr(D.chi_phi_tool, "ghi", lambda **k: so_cp.append(k) or {})
    monkeypatch.setattr(D.phan_loai, "_goi_model", lambda nhac: "{}")
    monkeypatch.setattr(D, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(D, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(D, "_write", lambda tok, sid, values: sheet.extend(values))
    monkeypatch.setattr(A, "_them_tab", lambda tok, ten: "s2")
    monkeypatch.setattr(A, "_write_values", lambda *a, **k: None)
    monkeypatch.setattr(D, "_grant", lambda tok, oid: True)
    monkeypatch.setattr(D.memory_store, "get_current_sender", lambda: "ou_test")
    return yt, ap, sheet, so_cp


def test_api_lay_binh_luan_va_tra_loi_0_usd_khong_goi_apify(mt):
    yt, ap, sheet, so_cp = mt
    kq = json.loads(D._handle({"post_urls": [V1], "max_comments": 100}))
    assert ap.goi == [] and so_cp == [], "API 0 USD: không chạy Apify, không ghi sổ chi phí"
    assert kq["per_url"][V1]["status"] == "OK" and kq["per_url"][V1]["comments"] == 6
    assert "Data API" in kq["per_url"][V1]["nguon"]
    # 2 trang commentThreads + 1 comments.list cho luồng có 3 trả lời mà chỉ kèm 1.
    assert [g[0] for g in yt.goi] == ["commentThreads", "commentThreads", "comments"]
    p1 = yt.goi[0][1]
    assert p1["part"] == "snippet,replies" and p1["maxResults"] == 100
    assert p1["order"] in ("relevance", "time") and p1["videoId"] == "AAAAAAAAAA1"
    assert yt.goi[2][1]["parentId"] == "c1"
    ya = kq["youtube_api"]
    assert ya["don_vi_quota"] == 3 and ya["chi_phi_usd"] == 0
    assert ya["so_dong"] == 6 and ya["tra_loi"] == 3
    assert kq["uoc_tinh_chi_phi_usd"] == 0 and "0 USD" in kq["chi_phi"]
    assert "3 đơn vị quota" in kq["chi_phi"]
    hd, dong = sheet[0], {r[2]: r for r in sheet[1:]}
    assert hd[-2] == "Trả lời bình luận" and hd[-1] == "Nguồn" and len(hd) == len(D._HEADER)
    goc = dong["Túi đẹp quá & xinh"]
    assert goc[6] == 3 and goc[-2] == "" and goc[7] == "2026-10-01 10:00", "mốc tuyệt đối, giờ VN"
    assert dong["mua ở đâu"][-2].endswith("&lc=c1") and dong["chuẩn luôn"][-2].endswith("&lc=c1")
    assert sum(1 for r in sheet[1:] if r[2] == "chuẩn luôn") == 1, "trả lời kèm sẵn không lặp"
    assert all(r[-3] == V1 for r in sheet[1:]), "quy về đúng link bài"
    assert A._youtube_doc()["dv"] == 3, "đơn vị quota vào sổ ngày dùng chung"


def test_max_comments_tinh_ca_tra_loi(mt):
    yt = mt[0]
    kq = json.loads(D._handle({"post_urls": [V1], "max_comments": 3}))
    assert kq["tong_comment"] == 3 and yt.goi[0][1]["maxResults"] == 3
    assert [g[0] for g in yt.goi] == ["commentThreads"]


def test_video_tat_binh_luan_bao_ra_khong_du_phong(mt):
    yt, ap = mt[0], mt[1]
    yt.loi["BBBBBBBBBB2"] = (403, "commentsDisabled")
    kq = json.loads(D._handle({"post_urls": [V1, V2]}))
    assert ap.goi == [], "tắt bình luận thì actor cũng không lấy được — không tốn 0,5 USD"
    assert kq["per_url"][V2]["status"] == D._TAT_BL
    assert kq["per_url"][V1]["status"] == "OK" and kq["platforms_failed"] == []
    assert D._TAT_BL in kq["note"] and kq["youtube_api"]["video_tat_binh_luan"] == [V2]


def test_het_quota_thi_du_phong_trong_phan_con_lai_va_lan_sau_di_thang_actor(mt):
    yt, ap = mt[0], mt[1]
    yt.loi["AAAAAAAAAA1"] = (403, "quotaExceeded")
    kq = json.loads(D._handle({"post_urls": [V1, V2], "max_comments": 50}))
    assert len(yt.goi) == 1, "lỗi chung: không gọi tiếp video sau"
    assert len(ap.goi) == 1 and ap.goi[0]["actor"] == D._ACTORS["youtube"]
    g = ap.goi[0]
    assert g["min_charge"] == 0.5 and 0.5 <= g["tran_usd"] <= 0.5 + 1e-9
    assert sorted(x["url"] for x in g["payload"]["startUrls"]) == sorted([V1, V2])
    # (0,9 × 0,5) / (0,002 × 2 bài) = 112 > 50 → giữ 50/bài.
    assert g["payload"]["maxComments"] == 50
    v = kq["per_url"][V1]
    assert v["status"] == "OK" and "DỰ PHÒNG" in v["nguon"] and "quota" in v["nguon"]
    assert kq["dung_nguon_du_phong"] == ["youtube"]
    assert A._youtube_het_quota() is True
    yt.goi.clear()
    ap.goi.clear()
    kq = json.loads(D._handle({"post_urls": [V1]}))
    assert yt.goi == [] and ap.goi[0]["actor"] == D._ACTORS["youtube"]
    assert "youtube_api" not in kq or kq["youtube_api"] is None


def test_du_phong_khong_an_phan_de_danh_cua_lo_khac(mt, monkeypatch):
    yt, ap = mt[0], mt[1]
    yt.loi["AAAAAAAAAA1"] = (500, "backendError")
    monkeypatch.setattr(D, "_cau_hinh", lambda: (300, 0.55))
    kq = json.loads(D._handle({"post_urls": [V1, TT]}))
    # TikTok giữ 0,1 → còn 0,45 < 0,5 actor YouTube đòi: KHÔNG chạy dự phòng.
    assert [g["actor"] for g in ap.goi] == [D._ACTORS["tiktok"]]
    assert kq["per_url"][V1]["status"] == "LỖI" and "không đủ" in kq["per_url"][V1]["error"]
    assert kq["platforms_failed"] == ["youtube"]


def test_tran_usd_thap_khong_chan_api_mien_phi(mt, monkeypatch):
    monkeypatch.setattr(D, "_cau_hinh", lambda: (300, 0.1))
    kq = json.loads(D._handle({"post_urls": [V1, V2]}))
    assert kq["per_url"][V1]["status"] == "OK" and kq["tong_comment"] == 12


def test_uoc_tinh_mien_phi_khi_co_api(mt):
    kq = json.loads(D._handle({"post_urls": [V1, V2], "chi_uoc_tinh": True}))
    assert kq["uoc_tinh_chi_phi_usd"] == 0 and mt[0].goi == []


def test_khong_key_thi_van_la_actor(mt, monkeypatch):
    monkeypatch.delenv("YOUTUBE_DATA_API_KEY")
    ap = mt[1]
    kq = json.loads(D._handle({"post_urls": [V1]}))
    assert mt[0].goi == [] and ap.goi[0]["actor"] == D._ACTORS["youtube"]
    assert kq["uoc_tinh_chi_phi_usd"] > 0


def test_loi_youtube_khong_lo_key(monkeypatch):
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "AIzaBIMAT")
    monkeypatch.setattr(A.requests, "get", lambda *a, **k: _loi(403, "quotaExceeded"))
    with pytest.raises(A.LoiYouTube) as e:
        A._youtube_get("commentThreads", {"videoId": "x"})
    assert e.value.ly_do == "quotaExceeded" and e.value.http == 403
    assert "AIzaBIMAT" not in str(e.value)


def test_quota_binh_luan_tru_vao_trang_search():
    assert A._youtube_con_trang(nen=False) == 100
    A._youtube_dem_dv(250)
    assert A._youtube_con_trang(nen=False) == 98, "250 đơn vị = 2 trang search (100 đv/trang)"


# ───────────────────────── việc nền ─────────────────────────
class _Viec:
    def __init__(self, ph):
        self.d = {"han_phut": 45, "nen_tang": {"youtube": {"phan": [ph]}}}
        self.ma, self.dong = "v1", []
        self.co_dung = threading.Event()

    def da_huy(self):
        return False

    def han_mono(self, chua=0.0):
        import time
        return time.monotonic() + 600

    def ghi_dong(self, p, rows, pid):
        self.dong += rows

    def cap_nhat_phan(self, ph, **kw):
        ph.update(kw)

    def cac_phan(self):
        for p, nt in self.d["nen_tang"].items():
            for ph in nt["phan"]:
                yield p, ph


def test_viec_nen_luot_con_api_0_usd(mt):
    tok = D._YT_API.set(True)
    try:
        nt = D._ke_hoach_nen({"youtube": (100, [[V1, V2]])}, 5.0)
    finally:
        D._YT_API.reset(tok)
    ph = nt["youtube"]["phan"][0]
    assert ph["kieu"] == D.KIEU_YT_API == quet_lon._KIEU_YT_API
    assert ph["uoc_usd"] == 0 and ph["can"] == 0
    v = _Viec(ph)
    ns = quet_lon._dung_so(1.0, list(v.cac_phan()))
    assert ns.cho == 0, "lượt API không giữ tiền trong sổ việc"
    # Ngữ cảnh riêng: `_mot_phan` đặt `_NEN`/`_HUY` — không được rò sang bài sau.
    n = contextvars.copy_context().run(quet_lon._mot_phan, v, "youtube", ph, ns, {})
    assert n == 12 and ph["trang_thai"] == "xong" and ph["usd_so"] == 0.0
    assert ph["don_vi_quota"] == 6 and mt[1].goi == []
    assert all(c["platform"] == "youtube" and c["bai"] in (V1, V2) for c, _ in v.dong)


def test_viec_nen_api_het_quota_chuyen_thanh_luot_actor(mt, monkeypatch):
    yt, ap = mt[0], mt[1]
    yt.loi["BBBBBBBBBB2"] = (403, "quotaExceeded")
    tok = D._YT_API.set(True)
    try:
        nt = D._ke_hoach_nen({"youtube": (50, [[V1, V2]])}, 5.0)
    finally:
        D._YT_API.reset(tok)
    ph = nt["youtube"]["phan"][0]
    v = _Viec(ph)
    ns = quet_lon._dung_so(1.0, list(v.cac_phan()))
    goi_run = []

    def run_actor(actor, payload, limit, mem, han, min_charge, tran_usd=None, mot_phan=True):
        goi_run.append((actor, payload, tran_usd, min_charge))
        return [{"author": "@z", "comment": "hay", "pageUrl": V2}], {"ma": "OK", "usd": 0.002}
    monkeypatch.setattr(A, "_run_actor", run_actor)
    contextvars.copy_context().run(quet_lon._mot_phan, v, "youtube", ph, ns, {},
                                   D._chuan_nen)
    actor, payload, tran, mc = goi_run[0]
    assert actor == D._ACTORS["youtube"] and payload["startUrls"] == [{"url": V2}]
    assert mc == 0.5 and 0.5 <= tran <= 1.0 and ph.get("kieu") == ""
    assert ns.da + ns.giu <= 1.0 + 1e-9
    assert ph["du_phong_lo"] == [V2] and ph["so_item_api"] == 6
