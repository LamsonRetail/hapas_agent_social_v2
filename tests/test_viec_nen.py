"""Canh quét NỀN (đợt 5, chủ agent chốt 01–02/10/2026): 10.000 bài / 30.000 bình luận.

Lỗi phải chặn:
  • lượt lớn chạy tại chỗ -> quá giờ 135s, run bị huỷ giữa chừng, tiền vẫn mất;
  • khởi động lại bot giữa việc -> POST lại run (trả tiền hai lần) thay vì đọc tiếp run id;
  • `chi_uoc_tinh` mà lỡ POST -> tốn tiền khi người dùng chưa đồng ý;
  • kết quả nhắn trùng / nhắn sai chat / lộ việc của chat khác;
  • quá ngân sách tháng giữa chừng (gói Free còn ~0,87 USD).
Không chạm mạng: Apify, Lark, model, platform đều giả; đồng hồ và giấc ngủ giả.
"""
from __future__ import annotations

import datetime
import json
import threading

import pytest

import apify_tool as A
import chi_phi_tool
import lark_client
import lsr_platform
import memory_store
import quet_lon as Q
import scheduler
import sheet_lon
import viec_nen as V
from test_apify_on_dinh import BI_MAT, R

NOW = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(hours=1)
HOM_NAY = datetime.datetime.now(A._VN_TZ)
TU = (HOM_NAY - datetime.timedelta(days=6)).strftime("%Y-%m-%d")
DEN = HOM_NAY.strftime("%Y-%m-%d")


# ───────────────────────────── giả lập ─────────────────────────────
def _item(actor: str, i: int, tag: str = "hapas") -> dict:
    url = f"https://www.tiktok.com/@u{i}/video/{abs(hash(tag)) % 10 ** 6}{i:05d}"
    txt = f"hapas túi xách đẹp quá {i}"
    if actor == A._ACTORS["tiktok_fallback"]:
        return {"createTimeISO": NOW.isoformat(), "authorMeta": {"name": f"u{i}", "fans": 9},
                "playCount": 5000 - i, "diggCount": 1, "commentCount": 0, "shareCount": 0,
                "hashtags": [{"name": tag}], "text": txt, "webVideoUrl": url}
    if actor == A._ACTORS["tiktok"]:
        return {"uploadedAtFormatted": NOW.isoformat(), "channel": {"name": f"u{i}"},
                "views": 10, "title": txt, "postPage": url}
    if actor == A._ACTORS["threads"]:
        return {"text_content": txt, "username": f"t{i}", "view_count": 3,
                "post_url": f"https://www.threads.net/@t/post/{tag}{i}",
                "created_at": NOW.isoformat()}
    if actor == A._ACTORS["instagram"]:
        return {"createdAt": NOW.isoformat(), "owner": {"username": f"i{i}"}, "caption": txt,
                "url": f"https://www.instagram.com/p/{tag}{i}/"}
    if actor == A._ACTORS["facebook"]:
        return {"timestamp": NOW.isoformat(), "author": {"name": f"f{i}"}, "message": txt,
                "url": f"https://www.facebook.com/x/posts/{i}"}
    return {"text": f"bình luận {i}", "uniqueId": f"c{i}", "diggCount": i,
            "videoWebUrl": "https://www.tiktok.com/@a/video/1234567"}


class GiaNen:
    """Fake Apify nhiều run: mỗi POST một run id + dataset riêng; GET actor-runs, dataset
    (có offset), INPUT, danh sách run của actor."""

    def __init__(self, t):
        self.t = t
        self.n = 0
        self.runs: dict = {}
        self.ds: dict = {}
        self.inputs: dict = {}
        self.actor_cua: dict = {}
        self.post_urls: list = []
        self.abort: list = []
        self.get_urls: list = []
        self.trang_thai = "SUCCEEDED"
        self.so_item = lambda actor, payload: int(
            payload.get("resultsPerPage") or payload.get("maxItems")
            or payload.get("max_posts") or payload.get("max_results")
            or payload.get("commentsPerPost") or 10)
        self.khi_get_run = None
        self.khoa = threading.Lock()

    def tao_run(self, actor, payload, items, status="RUNNING", started=None):
        with self.khoa:
            self.n += 1
            rid, ds, kv = f"run{self.n}", f"ds{self.n}", f"kv{self.n}"
        self.ds[ds] = items
        self.inputs[kv] = payload
        self.actor_cua[rid] = actor
        self.runs[rid] = {"id": rid, "status": status, "defaultDatasetId": ds,
                          "defaultKeyValueStoreId": kv, "statusMessage": "",
                          "usageTotalUsd": round(0.001 * len(items), 4),
                          "startedAt": (started or datetime.datetime.now(datetime.timezone.utc)
                                        ).isoformat()}
        return rid

    def post(self, url, json=None, **k):
        if url.endswith("/abort"):
            rid = url.split("/actor-runs/")[1].split("/")[0]
            self.abort.append(rid)
            self.runs[rid]["status"] = "ABORTED"
            return R(200, {"data": dict(self.runs[rid])})
        self.post_urls.append(url)
        actor = url.split("/acts/")[1].split("/runs")[0]
        n = self.so_item(actor, json or {})
        rid = self.tao_run(actor, json, [_item(actor, i, str((json or {}).get(
            "hashtags", ["x"])[0]) if isinstance((json or {}).get("hashtags"), list)
            else "hapas") for i in range(n)], self.trang_thai)
        return R(201, {"data": dict(self.runs[rid])})

    def get(self, url, params=None, **k):
        self.get_urls.append((url, dict(params or {})))
        if "/actor-runs/" in url:
            rid = url.split("/actor-runs/")[1].split("/")[0]
            if self.khi_get_run:
                self.khi_get_run(rid)
            self.t[0] += (params or {}).get("waitForFinish", 0)
            run = self.runs[rid]
            if run["status"] == "RUNNING" and self.trang_thai == "SUCCEEDED":
                run["status"] = "SUCCEEDED"
            return R(200, {"data": dict(run)})
        if "/datasets/" in url:
            ds = url.split("/datasets/")[1].split("/")[0]
            it = self.ds.get(ds, [])
            off = int((params or {}).get("offset") or 0)
            lim = int((params or {}).get("limit") or len(it))
            return R(200, it[off:off + lim])
        if "/key-value-stores/" in url:
            kv = url.split("/key-value-stores/")[1].split("/")[0]
            return R(200, self.inputs.get(kv))
        if "/acts/" in url and url.endswith("/runs"):
            actor = url.split("/acts/")[1].split("/runs")[0]
            return R(200, {"data": {"items": [dict(r) for rid, r in self.runs.items()
                                              if self.actor_cua.get(rid) == actor][::-1]}})
        return R(404, {})


class GiaLark:
    def __init__(self):
        self.goi: list = []
        self.tabs = ["s0"]
        self.khoa = threading.Lock()

    def call(self, method, path, query=None, body=None):
        with self.khoa:
            self.goi.append((method, path, body, query))
        if path == "/open-apis/sheets/v3/spreadsheets":
            return {"data": {"spreadsheet": {"spreadsheet_token": "shtA",
                                             "url": "https://lark.test/sheets/shtA"}}}
        if path.endswith("/sheets/query"):
            return {"data": {"sheets": [{"sheet_id": s, "grid_properties": {"row_count": 200}}
                                        for s in self.tabs]}}
        if path.endswith("/sheets_batch_update"):
            req = (body or {}).get("requests", [{}])[0]
            if "addSheet" in req:
                sid = f"tab{len(self.tabs)}"
                self.tabs.append(sid)
                return {"data": {"replies": [{"addSheet": {"properties": {"sheetId": sid}}}]}}
        return {"data": {}}

    def ghi(self):
        return [(b["valueRanges"][0]["range"], len(b["valueRanges"][0]["values"]))
                for m, p, b, q in self.goi if p.endswith("values_batch_update")]

    def tin(self):
        return [(q, b) for m, p, b, q in self.goi if p == "/open-apis/im/v1/messages"]


@pytest.fixture
def nen(monkeypatch, tmp_path):
    t = [1000.0]
    monkeypatch.setattr(A, "_dong_ho", lambda: t[0])
    monkeypatch.setattr(A, "_ngu", lambda s: t.__setitem__(0, t[0] + s))
    for m in (V, sheet_lon):
        monkeypatch.setattr(m, "_ngu", lambda s: None)
    monkeypatch.setenv("APIFY_TOKEN", BI_MAT)
    monkeypatch.setenv("SOCIAL_QUET_NEN", "1")
    monkeypatch.setenv("LSR_AGENT_ID", "AG-THU")
    monkeypatch.setattr(A, "_tran", lambda nen=None: (10000, 20.0))
    A._NHO_APIFY.clear()
    g = GiaNen(t)
    monkeypatch.setattr(A.requests, "post", g.post)
    monkeypatch.setattr(A.requests, "get", g.get)
    lk = GiaLark()
    monkeypatch.setattr(lark_client, "call", lk.call)
    g.lark = lk
    g.lich_su, g.ngu_canh, g.so_chi_phi, g.gw, g.su_kien = [], [], [], [], []
    monkeypatch.setattr(memory_store, "append_turns", lambda c, t_: g.lich_su.append((c, t_)))
    monkeypatch.setattr(lsr_platform, "ghi_luot_ngu_canh",
                        lambda *a, **k: g.ngu_canh.append(a) or True)
    monkeypatch.setattr(lsr_platform, "gui_lark", lambda *a: g.gw.append(a) or {})
    monkeypatch.setattr(lsr_platform, "bao_su_kien_job", lambda *a: g.su_kien.append(a) or {})
    monkeypatch.setattr(chi_phi_tool, "ghi", lambda **k: g.so_chi_phi.append(k) or k)
    scheduler.set_current_chat("oc_nhom1")
    memory_store.set_current_sender("ou_nguoi1")
    V._SU_KIEN_HUY.clear()
    with A._RUN_KHOA:
        A._RUN_CUA_MINH.clear()       # run id giả ("run1"…) lặp lại giữa các bài
    yield g
    import time as _t
    for _ in range(50):
        if A._CHO_APIFY._value == A._DONG_THOI_TOI_DA and A._CHO_NEN._value == A._NEN_SLOT:
            break
        _t.sleep(0.02)
    assert A._CHO_APIFY._value == A._DONG_THOI_TOI_DA, "lượt Apify chưa trả chỗ"
    assert A._CHO_NEN._value == A._NEN_SLOT, "việc nền chưa trả chỗ"
    A._NHO_APIFY.clear()
    scheduler.set_current_chat(None)
    memory_store.set_current_sender(None)


def _quet(**k):
    a = {"queries": ["hapas"], "platforms": ["tiktok"], "date_from": TU, "date_to": DEN,
         "limit": 3000, "boi_canh": "HAPAS túi xách"}
    a.update(k)
    return json.loads(A._handle(a))


# ───────────────────────────── quyết định chạy nền ─────────────────────────────
def test_nguong_quyet_dinh_chay_nen():
    assert Q.can_chay_nen({"tiktok": 100, "youtube": 50}, 40)[0] is False
    assert Q.can_chay_nen({"tiktok": 601}, 40)[0] is True
    assert Q.can_chay_nen({"tiktok": 500, "instagram": 500, "threads": 501}, 40)[0] is True
    assert Q.can_chay_nen({"tiktok": 100}, 81)[0] is True
    assert Q.can_chay_nen({"tiktok": 10}, 5, True)[0] is True
    assert Q.can_chay_nen({"tiktok": 9000}, 5000, False)[0] is False
    # Lượt TikTok thường (100 bài) vẫn chạy tại chỗ như trước.
    assert Q.can_chay_nen({"tiktok": 100}, Q.giay_tai_cho(["tiktok"], {"tiktok": 100},
                                                          ["hapas"]))[0] is False


def test_tat_chay_nen_thi_kep_ve_co_tai_cho(nen, monkeypatch):
    monkeypatch.setenv("SOCIAL_QUET_NEN", "0")
    nhan = []
    monkeypatch.setitem(A._FETCH, "tiktok", lambda q, lim, *a: nhan.append(lim) or [])
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    kq = _quet(limit=5000)
    assert nhan == [600] and "TẮT" in kq["quet_nen_ghi_chu"]
    assert not nen.post_urls and not V.tat_ca()


def test_chi_uoc_tinh_khong_post_gi(nen, monkeypatch):
    def cam(*a, **k):
        raise AssertionError("chi_uoc_tinh không được POST")
    monkeypatch.setattr(A.requests, "post", cam)
    kq = _quet(limit=5000, platforms=["tiktok", "threads", "youtube"], chi_uoc_tinh=True)
    assert kq["chi_uoc_tinh"] and kq["se_chay_nen"] and kq["uoc_tinh_usd"] > 0
    assert "Chạy nhé?" in kq["note"] and "USD" in kq["note"]
    assert set(kq["per_platform"]) == {"tiktok", "threads", "youtube"}
    assert not V.tat_ca(), "ước tính không được tạo việc"


def test_luot_lon_tra_ma_viec_truoc_moi_post(nen):
    kq = _quet()
    assert kq["dang_chay_nen"] is True and kq["trang_thai"] in ("dang_chay", "xep_hang")
    for k in ("ma_viec", "uoc_tinh_phut", "uoc_tinh_usd", "ngan_sach_usd", "han_chot",
              "se_bao_qua", "note"):
        assert kq.get(k) is not None, k
    assert nen.post_urls == [], "phải trả mã việc TRƯỚC khi POST run nào"
    f = V._duong(kq["ma_viec"])
    d = json.loads(f.read_text(encoding="utf-8"))
    for k in ("agent_id", "trang_thai", "kenh", "tham_so", "khoa_trung", "uoc_tinh",
              "ngan_sach_usd", "nen_tang", "phan_xu", "sheet", "chi_phi", "thong_bao", "huy"):
        assert k in d, k
    assert d["kenh"] == {"loai": "lark_truc_tiep", "chat_id": "oc_nhom1", "app_id": "",
                         "oc": "oc_nhom1", "job_id": None}
    ph = d["nen_tang"]["tiktok"]["phan"]
    assert ph[0]["kieu"] == "do" and ph[1]["payload"] == {"hashtags": ["hapas"],
                                                           "resultsPerPage": ph[1]["limit"]}
    assert all({"id", "actor", "payload_sha", "limit", "trang_thai"} <= set(x) for x in ph)
    assert BI_MAT not in f.read_text(encoding="utf-8")


def test_cung_tham_so_trong_6_gio_tra_lai_ma_cu(nen):
    a, b = _quet(), _quet()
    assert a["ma_viec"] == b["ma_viec"] and b["trung_viec_cu"] is True
    assert len(V.tat_ca()) == 1


def test_moi_chat_mot_viec_lon_mot_luc(nen):
    _quet()
    kq = _quet(queries=["matemade"])
    assert kq["success"] is False and "đã có một việc" in kq["note"]


def test_ngan_sach_thang_tu_choi_hoac_cat(nen, monkeypatch):
    monkeypatch.setattr(A, "_han_muc_thang",
                        lambda: {"dung": 4.13, "tran": 5.0, "con_lai": 0.87, "reset": None})
    kq = _quet(limit=5000)
    assert kq["vuot_ngan_sach"] and kq["chua_chay"] and kq["ngan_sach_usd"] == 0.57
    assert not V.tat_ca()
    kq = _quet(limit=5000, cat_theo_ngan_sach=True)
    assert kq["dang_chay_nen"]
    d = V.doc(kq["ma_viec"])
    assert sum(p["uoc_usd"] for p in d["nen_tang"]["tiktok"]["phan"]) <= 0.57
    assert any("ngân sách" in c for c in d["nen_tang"]["tiktok"]["chua_phu"])


# ───────────────────────────── kế hoạch từng nền tảng ─────────────────────────────
def _ts(**k):
    t = {"queries": ["hapas"], "date_from": "2026-09-01", "date_to": "2026-09-30",
         "country": "VN"}
    t.update(k)
    return t


def test_threads_chia_cua_so_ngay_va_noi_that_khi_khong_kip():
    kh = Q.ke_hoach(["hapas", "matemade"], ["threads"], {"threads": 10000},
                    _ts(queries=["hapas", "matemade"]), 45, {})
    ph = kh["nen_tang"]["threads"]["phan"]
    assert len(ph) >= 20 and all(x["payload"]["max_posts"] <= 500 for x in ph)
    tu = sorted({x["tu"] for x in ph})
    assert tu[0] == "2026-09-01" and len(tu) >= 10
    tong = sum(x["limit"] for x in ph)
    assert tong < 10000 and any("không kịp hạn" in c
                                for c in kh["nen_tang"]["threads"]["chua_phu"])


def test_facebook_free_chi_mot_tu_khoa_20_bai():
    kh = Q.ke_hoach(["hapas", "matemade"], ["facebook"], {"facebook": 5000}, _ts(), 45,
                    {"goi": "FREE"})
    x = kh["nen_tang"]["facebook"]
    assert len(x["phan"]) == 1 and x["phan"][0]["limit"] == 20
    assert x["phan"][0]["payload"]["query"] == "hapas"
    assert any("20 bài" in c and "matemade" in c for c in x["chua_phu"])
    luot = (NOW, NOW + datetime.timedelta(hours=24))
    kh = Q.ke_hoach(["hapas"], ["facebook"], {"facebook": 5000}, _ts(), 45,
                    {"goi": "FREE", "fb_luot": luot})
    assert not kh["nen_tang"]["facebook"]["phan"]
    assert "KHÔNG quét Facebook" in kh["nen_tang"]["facebook"]["chua_phu"][0]


def test_youtube_cua_so_trong_quota_ngay(monkeypatch, tmp_path):
    A._youtube_dem(70)
    assert A._youtube_con_trang(nen=True) == 10 and A._youtube_con_trang(nen=False) == 30
    kh = Q.ke_hoach(["hapas"], ["youtube"], {"youtube": 1500}, _ts(), 45,
                    {"yt_con": A._youtube_con_trang(nen=True)})
    ph = kh["nen_tang"]["youtube"]["phan"]
    assert sum(x["so_trang"] for x in ph) == 10
    assert any("quota" in c for c in kh["nen_tang"]["youtube"]["chua_phu"])
    kh = Q.ke_hoach(["hapas"], ["youtube"], {"youtube": 1500}, _ts(), 45, {"yt_con": 80})
    ph = kh["nen_tang"]["youtube"]["phan"]
    assert sum(x["so_trang"] for x in ph) == 30 and len(ph) == 3
    assert ph[0]["tu"] == "2026-09-01" and ph[-1]["den"] == "2026-09-30"


def test_youtube_dem_trang_dung_chung(monkeypatch):
    monkeypatch.setenv("YOUTUBE_DATA_API_KEY", "AIzaTHU")

    class Y:
        status_code = 200

        def json(self):
            return {"items": [{"id": {"videoId": f"v{i}"}, "snippet": {}} for i in range(50)],
                    "nextPageToken": "n"}
    monkeypatch.setattr(A.requests, "get", lambda *a, **k: Y())
    rows, so, cat = A._youtube_tim(["hapas"], 500, "VN", NOW - datetime.timedelta(days=3),
                                   NOW, toi_da_trang=3)
    assert so == 3 and cat is True
    assert A._youtube_da_dung() == 3, "trang search phải vào bộ đếm ngày dùng chung"


def test_tiktok_moi_hashtag_mot_luot_khong_che_hashtag():
    kh = Q.ke_hoach(["hapas", "matemade", "túi xách"], ["tiktok"], {"tiktok": 3000}, _ts(),
                    45, {})
    ph = kh["nen_tang"]["tiktok"]["phan"]
    assert ph[0]["kieu"] == "do" and ph[0]["limit"] <= 100
    the = [x["payload"]["hashtags"] for x in ph[1:]]
    assert the == [["hapas"], ["matemade"]], "không tự chế hashtag từ 'túi xách'"
    assert any("túi xách" in c for c in kh["nen_tang"]["tiktok"]["chua_phu"])


def test_khu_trung_theo_link_chuan():
    assert Q._chuan_link("https://www.tiktok.com/@a/video/1?is_from_webapp=1") == \
        Q._chuan_link("http://m.tiktok.com/@a/video/1/")
    assert Q._chuan_link("https://youtube.com/watch?v=abc") != \
        Q._chuan_link("https://youtube.com/watch?v=xyz")


# ───────────────────────────── chạy việc ─────────────────────────────
def _tao_va_chay(**k):
    kq = _quet(**k)
    return V.chay_ngay(kq["ma_viec"]), kq


def test_chay_het_viec_ghi_sheet_nhan_mot_lan_va_ghi_so_chi_phi(nen):
    d, kq = _tao_va_chay(limit=2500)
    assert d["trang_thai"] in ("xong", "xong_mot_phan"), d.get("ly_do_ket_thuc")
    assert len(nen.post_urls) == 2, "1 lượt dò + 1 hashtag"
    tab = {b["requests"][0]["addSheet"]["properties"]["title"]
           for m, p, b, q in nen.lark.goi
           if p.endswith("sheets_batch_update") and "addSheet" in b["requests"][0]}
    assert "TikTok" in tab
    assert all(n <= 1000 for _, n in nen.lark.ghi()), "mỗi lượt ghi ≤1000 dòng"
    assert any(p.endswith("dimension_range") for m, p, b, q in nen.lark.goi), \
        "lưới 200 dòng phải được nới trước khi ghi 2500 dòng"
    tin = nen.lark.tin()
    assert len(tin) == 1 and tin[0][1]["receive_id"] == "oc_nhom1"
    assert tin[0][1]["uuid"] == f"{kq['ma_viec']}-kq"
    van = json.loads(tin[0][1]["content"])["text"]
    assert "https://lark.test/sheets/shtA" in van and "Chi phí thật" in van
    assert nen.lich_su and nen.lich_su[-1][0] == "oc_nhom1"
    assert nen.so_chi_phi[-1]["ma_viec"] == kq["ma_viec"]
    ids = [ph["run_id"] for ph in d["nen_tang"]["tiktok"]["phan"]]
    assert nen.so_chi_phi[-1]["thuc"]["usd"] == round(sum(
        nen.runs[r]["usageTotalUsd"] for r in ids), 4)
    assert BI_MAT not in V._duong(kq["ma_viec"]).read_text(encoding="utf-8")
    # Khởi động lại sau khi đã nhắn: KHÔNG nhắn lại.
    V.chay_ngay(kq["ma_viec"])
    assert len(nen.lark.tin()) == 1
    # Cùng yêu cầu trong 6 giờ sau khi xong: trả kết quả cũ, không quét lại.
    lai = _quet(limit=2500)
    assert lai["da_xong_truoc"] and lai["ma_viec"] == kq["ma_viec"] and lai["ket_qua"]
    assert len(nen.post_urls) == 2


def _viec_dang_chay(nen, phan_sua):
    kq = _quet(limit=1500)
    d = V.doc(kq["ma_viec"])
    d["trang_thai"] = "dang_cao"
    d["bat_dau_ts"] = V._bay_gio()
    d["han_chot_ts"] = V._bay_gio() + 1800
    ph = d["nen_tang"]["tiktok"]["phan"]
    ph[0]["trang_thai"] = "xong"
    ph[0]["so_item"] = 0
    phan_sua(d, ph[1])
    V.luu(d)
    return kq["ma_viec"]


def test_khoi_dong_lai_doc_tiep_run_dang_chay_chi_get(nen):
    actor = A._ACTORS["tiktok_fallback"]
    rid = nen.tao_run(actor, {}, [_item(actor, i) for i in range(1500)], "RUNNING")

    def sua(d, ph):
        ph.update(trang_thai="dang_chay", run_id=rid, tran_usd=4.5, moc_gui=NOW.isoformat())
    ma = _viec_dang_chay(nen, sua)
    V.khoi_dong(chay_luong=False)
    d = V.chay_ngay(ma)
    assert nen.post_urls == [], "đọc tiếp run cũ — KHÔNG POST lại"
    ds = [p for u, p in nen.get_urls if "/datasets/" in u]
    assert [p.get("offset") for p in ds] == [None, 1000], "đọc dataset theo trang 1000"
    assert all("fields" in p and "webVideoUrl" in p["fields"] for p in ds)
    assert d["nen_tang"]["tiktok"]["phan"][1]["so_item"] == 1500


def test_khoi_dong_lai_khi_dang_gui_nhan_run_vua_tao_khong_chay_trung(nen):
    actor = A._ACTORS["tiktok_fallback"]
    holder = {}

    def sua(d, ph):
        rid = nen.tao_run(actor, ph["payload"], [_item(actor, i) for i in range(30)],
                          "SUCCEEDED")
        holder["rid"] = rid
        ph.update(trang_thai="dang_gui", tran_usd=4.5,
                  moc_gui=(datetime.datetime.now(A._VN_TZ)
                           - datetime.timedelta(seconds=5)).isoformat())
    ma = _viec_dang_chay(nen, sua)
    d = V.chay_ngay(ma)
    ph = d["nen_tang"]["tiktok"]["phan"][1]
    assert nen.post_urls == [] and ph["run_id"] == holder["rid"] and ph.get("nhan_lai")


def test_khoi_dong_lai_sau_han_huy_run_giu_phan_do(nen):
    actor = A._ACTORS["tiktok_fallback"]
    rid = nen.tao_run(actor, {}, [_item(actor, i) for i in range(40)], "RUNNING")
    nen.trang_thai = "RUNNING"

    def sua(d, ph):
        ph.update(trang_thai="dang_chay", run_id=rid, tran_usd=4.5)
    ma = _viec_dang_chay(nen, sua)
    d = V.doc(ma)
    d["han_chot_ts"] = V._bay_gio() - 60
    V.luu(d)
    d = V.chay_ngay(ma)
    assert rid in nen.abort and nen.post_urls == []
    assert d["trang_thai"] == "xong_mot_phan"
    assert d["nen_tang"]["tiktok"]["phan"][1]["so_item"] == 40
    assert "sau hạn chót" in d["thong_bao"]["ket_qua"]


def test_huy_giua_chung_dung_run_giu_phan_do_va_bao_da_huy(nen):
    nen.trang_thai = "RUNNING"
    kq = _quet(limit=1500)
    ma = kq["ma_viec"]
    da = []

    def khi_get(rid):
        if not da:
            da.append(rid)
            assert V.huy(ma)["ok"]
    nen.khi_get_run = khi_get
    d = V.chay_ngay(ma)
    assert d["trang_thai"] == "da_huy"
    assert nen.abort, "run đang chạy phải bị HUỶ trên Apify"
    assert any(ph["trang_thai"] == "da_huy" for ph in d["nen_tang"]["tiktok"]["phan"])
    van = d["thong_bao"]["ket_qua"]
    assert "ĐÃ HUỶ" in van and "https://lark.test/sheets/shtA" in van
    assert d["huy"]["yeu_cau"] is True


def test_huy_khi_con_xep_hang_khong_chay_gi(nen):
    kq = _quet()
    r = V.huy(kq["ma_viec"])
    assert r["ok"] and r["trang_thai"] == "da_huy"
    d = V.chay_ngay(kq["ma_viec"])
    assert d["trang_thai"] == "da_huy" and nen.post_urls == []


def test_nen_chi_giu_toi_da_2_cho_apify_tuong_tac_van_chay(nen):
    giu = [A._CHO_NEN.acquire(timeout=0) for _ in range(A._NEN_SLOT)]
    try:
        tok = A._NEN.set(True)
        try:
            with pytest.raises(A.LoiApify) as e:
                A._run_actor("a~b", {}, 5, deadline=A._dong_ho() + 10)
            assert e.value.ma == "NGHEN_DONG_THOI" and "nền" in str(e.value)
        finally:
            A._NEN.reset(tok)
        items, meta = A._run_actor("a~b", {}, 5, deadline=A._dong_ho() + 200)
        assert meta["ma"] == "OK", "lượt tại chỗ không phải chờ chỗ của việc nền"
    finally:
        for x in giu:
            if x:
                A._CHO_NEN.release()
    assert A._NEN_SLOT == 2 and A._DONG_THOI_TOI_DA == 4


# ───────────────────────────── phân xử theo tầng ─────────────────────────────
def _hang(n, khop=True, views=5000):
    ra = []
    for i in range(n):
        d = {"platform": "tiktok", "kenh": f"k{i % 7}", "username": "", "views": views - i,
             "text": ("hapas túi xách" if khop else "túi đẹp quá") + f" {i}",
             "hashtags": "", "link": f"https://www.tiktok.com/@a/video/{i}",
             "_khop": khop, "_thi_truong": "không rõ"}
        ra.append((d, NOW))
    return ra


_TS_AI = {"queries": ["hapas"], "country": "VN", "boi_canh": "HAPAS túi xách",
          "khop_long": False, "giu_nuoc_ngoai": False}


def test_phan_xu_tang_tran_luot_va_lan_theo_kenh(monkeypatch):
    import time
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "1")
    goi = []

    def model(nhac, han):
        n = nhac.count('<p i="') - 1          # trừ ví dụ thẻ trong lời dặn
        goi.append(n)
        return json.dumps({str(i): ["l", "trung_ten"] for i in range(n)})
    monkeypatch.setattr(A, "_hoi_model", model)
    rows = _hang(3000, khop=False, views=99999)       # mơ hồ: không khớp từ khoá, nhiều view
    ket, tt = Q._phan_xu_tang(rows, _TS_AI, time.monotonic() + 600, [], ma="viec1")
    assert len(goi) == 10 and max(goi) <= A._AI_LO, "tối đa 10 lượt model, ≤120 bài/lượt"
    assert tt["luot_ai"] == 10 and tt["ai_xet"] == 1200
    assert tt["theo_kenh"] == 1800, "bài còn lại của các kênh đã bị AI loại lan theo kênh"
    assert {v[3] for v in ket.values()} == {"AI", "AI (theo kênh)"}


def test_phan_xu_tang_dung_khi_het_quota_va_mau_kiem(monkeypatch):
    import time
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "1")
    goi = []

    def model(nhac, han):
        goi.append(1)
        raise RuntimeError("429 quota exceeded")
    monkeypatch.setattr(A, "_hoi_model", model)
    ket, tt = Q._phan_xu_tang(_hang(1000, khop=False, views=99999), _TS_AI,
                              time.monotonic() + 600, [], ma="v")
    assert tt["dung_vi_quota"] and len(goi) == 2 and not ket
    # Bài luật giữ chắc -> chỉ MỘT lượt kiểm mẫu 120 bài.
    monkeypatch.setattr(A, "_hoi_model", lambda nhac, han: json.dumps(
        {str(i): ["k", "brand"] for i in range(nhac.count('<p i="'))}))
    rows = _hang(500)
    for d, _ in rows:
        d["_thi_truong"] = "VN"
    ket, tt = Q._phan_xu_tang(rows, _TS_AI, time.monotonic() + 600, [], ma="v")
    assert tt["giu_ro"] == 500 and tt["luot_ai"] == 1
    assert tt["mau_kiem"] == {"xet": 120, "ai_giu": 120, "ai_loai": 0}


def test_loc_dem_cong_lai_dung_tong(nen, monkeypatch):
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "1")
    monkeypatch.setattr(A, "_hoi_model", lambda nhac, han: json.dumps(
        {str(i): (["l", "spam"] if i % 2 else ["k", "ugc"])
         for i in range(nhac.count('<p i="'))}))
    kq = _quet(limit=1500, exclude=["cấm"])
    v = V.Viec(V.doc(kq["ma_viec"]))
    rows = [({"kenh": f"k{i}", "text": ("hapas túi xách " if i % 3 else "túi xinh ")
              + ("cấm" if i == 5 else "") + str(i), "views": 5000 + i,
              "link": f"https://www.tiktok.com/@a/video/{i}"}, NOW) for i in range(300)]
    rows.append(rows[0])                                       # trùng link
    v.ghi_dong("tiktok", rows, "tiktok-1")
    ts = dict(v.d["tham_so"])
    ket = Q._loc(v, ts, A._parse_date(TU, end=False), A._parse_date(DEN, end=True), True, [])
    per = ket["per"]["tiktok"]
    assert per["scraped"] == 301 and per["trung_lap"] == 1
    dem = ket["phan_xu"]["dem"]
    tong = sum(x["giu"] + x["loai"] for x in dem.values()) + ket["phan_xu"]["loai_tru"] \
        + sum(ket["phan_xu"]["chuyen_thi_truong"].values())
    assert tong == per["trong_khoang"] == 300
    assert per["giu"] + per["loai"] == 300
    assert {d.get("_phan_xu") for d, _ in ket["hits"]} <= {"AI", "AI (theo kênh)", "Luật"}
    # Cache phán xử: lần lọc thứ hai KHÔNG gọi model lại.
    Q._cache_ghi(v, {Q._khoa_link(d): (True, "ugc", "") for d, _ in rows})
    monkeypatch.setattr(A, "_hoi_model", lambda *a: (_ for _ in ()).throw(AssertionError()))
    Q._loc(v, ts, A._parse_date(TU, end=False), A._parse_date(DEN, end=True), True, [])


# ───────────────────────────── sheet cỡ lớn ─────────────────────────────
class _VGia:
    def __init__(self):
        self.d = {"ma": "x1", "sheet": {}}
        self._khoa = threading.RLock()

    def luu(self):
        pass


def test_sheet_ghi_khoi_1000_va_ghi_tiep_khong_nhan_doi(monkeypatch):
    lk = GiaLark()
    monkeypatch.setattr(lark_client, "call", lk.call)
    monkeypatch.setattr(sheet_lon, "_ngu", lambda s: None)
    monkeypatch.setattr(A, "_grant", lambda *a: True)
    v = _VGia()
    s = sheet_lon.SoSheet(v)
    s.dam_bao("T", "Tổng hợp", "ou_x")
    bang = [["h1", "h2"]] + [[i, i] for i in range(2500)]
    s.ghi_tab("TikTok", bang)
    ghi = lk.ghi()
    assert [n for _, n in ghi] == [1000, 1000, 501]
    assert ghi[2][0].endswith("A2001:B2501")
    # Khởi động lại giữa chừng: đã ghi 1000 dòng -> chỉ ghi phần còn lại.
    lk.goi.clear()
    s.s["tabs"]["TikTok"]["da_ghi"] = 1000
    s.ghi_tab("TikTok", bang)
    assert [n for _, n in lk.ghi()] == [1000, 501]
    # Bản cuối ít dòng hơn bản sơ bộ -> xoá phần thừa.
    lk.goi.clear()
    s.ghi_tab("TikTok", bang[:11], tu_dau=True)
    r = lk.ghi()
    assert r[0][1] == 11 and sum(n for _, n in r[1:]) == 2490


def test_sheet_lui_dan_khi_lark_bao_tan_suat(monkeypatch):
    n = []

    def call(method, path, **k):
        n.append(path)
        if len(n) < 3:
            raise RuntimeError("Lark POST x failed: HTTP 429: frequency limit")
        return {"data": {}}
    ngu = []
    monkeypatch.setattr(A.lark, "call", call)
    monkeypatch.setattr(sheet_lon, "_ngu", ngu.append)
    sheet_lon._goi("POST", "/x", body={})
    assert len(n) == 3 and ngu == [1.5, 3.0]


def test_bi_loai_bi_chan_tran_dong(nen, monkeypatch):
    monkeypatch.setattr(Q, "_BI_LOAI_TOI_DA", 5)
    kq = _quet(limit=1500, exclude=["hapas"])           # mọi bài chứa từ loại trừ
    d = V.chay_ngay(kq["ma_viec"])
    loai = [r for r in nen.lark.ghi()]
    assert d["ket_qua"]["loai"] > 5
    tong = [b for m, p, b, q in nen.lark.goi if p.endswith("values_batch_update")
            and any("không ghi" in str(c) for row in b["valueRanges"][0]["values"]
                    for c in row)]
    assert tong, "phần vượt trần Bị loại phải được đếm ở tab Tổng hợp"
    assert loai


# ───────────────────────────── gửi kết quả ─────────────────────────────
def _viec_xong(kenh: dict, chat="oc_nhom1"):
    d = {"ma": "qthu-abcde", "agent_id": "AG-THU", "trang_thai": "xong",
         "kenh": {**kenh, "chat_id": chat}, "nguoi_yeu_cau": "ou_nguoi1",
         "thong_bao": {"ket_qua": "xong rồi", "lan_thu": 0, "da_gui": False},
         "huy": {}, "nen_tang": {}, "tao_ts": V._bay_gio()}
    V.luu(d)
    return V.Viec(d)


def test_gui_qua_gateway_web_va_hoi_quy(nen):
    v = _viec_xong({"loai": "lark_gateway", "app_id": "cli_a", "oc": "oc_9"},
                   "lark:cli_a:oc_9")
    assert V.gui(v) and nen.gw == [("oc_9", "xong rồi", "cli_a")]
    assert nen.ngu_canh[-1][0] == "lark:cli_a:oc_9"
    v = _viec_xong({"loai": "web", "job_id": 77}, "web:abc")
    assert V.gui(v) and nen.su_kien == [(77, "xong rồi")]
    v = _viec_xong({"loai": "khac"}, "hoiquy-1")
    V.gui(v)
    assert v.d["thong_bao"]["khong_day"] and not nen.lark.tin()


def test_gui_thu_lai_roi_khong_gui_lai(nen, monkeypatch):
    lan = []

    def gw(*a):
        lan.append(a)
        if len(lan) == 1:
            raise RuntimeError("502")
        return {}
    monkeypatch.setattr(lsr_platform, "gui_lark", gw)
    v = _viec_xong({"loai": "lark_gateway", "app_id": "a", "oc": "oc_1"}, "lark:a:oc_1")
    assert V.gui(v) and len(lan) == 2 and v.d["thong_bao"]["lan_thu"] == 1
    V.gui(v)
    assert len(lan) == 2 and len(nen.lich_su) == 1, "không nhắn/ghi lịch sử lần hai"


def test_kenh_ghi_lai_job_platform(nen):
    scheduler.set_current_chat("web:abc")
    with lsr_platform._JOB_PHIEN_KHOA:
        lsr_platform._JOB_PHIEN["web:abc"] = 4242
    try:
        k, nguoi = V.kenh_hien_tai()
    finally:
        lsr_platform._JOB_PHIEN.pop("web:abc", None)
    assert k["loai"] == "web" and k["job_id"] == 4242 and nguoi == "ou_nguoi1"
    scheduler.set_current_chat("lark:cli_x:oc_7")
    k, _ = V.kenh_hien_tai()
    assert (k["loai"], k["app_id"], k["oc"]) == ("lark_gateway", "cli_x", "oc_7")


# ───────────────────────────── tra cứu / lệnh ─────────────────────────────
def test_tra_viec_nen_chi_thay_viec_cua_chat_hoac_nguoi_hoi(nen):
    kq = _quet()
    assert V.tra(chat="oc_nhom1", nguoi="ou_khac")["tim_thay"]
    assert V.tra(chat="oc_khac", nguoi="ou_nguoi1")["tim_thay"]
    r = V.tra(chat="oc_khac", nguoi="ou_khac")
    assert not r["tim_thay"]
    assert not V.tra(kq["ma_viec"], chat="oc_khac", nguoi="ou_khac")["tim_thay"]
    assert not V.huy(kq["ma_viec"], chat="oc_khac", nguoi="ou_khac")["ok"]
    x = V.tra(chat="oc_nhom1", nguoi="")["viec"][0]
    assert x["ma_viec"] == kq["ma_viec"] and x["trang_thai"] == "xep_hang"


def test_khoa_chu_cua_tien_trinh_khac_thi_khong_nhan_viec(nen):
    f = V._khoa_chu()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"pid": -1, "agent_id": "AG-THU", "heartbeat": V._bay_gio()}),
                 encoding="utf-8")
    assert "tiến trình khác" in V.khoi_dong(chay_luong=False)
    f.write_text(json.dumps({"pid": -1, "agent_id": "AG-THU",
                             "heartbeat": V._bay_gio() - 500}), encoding="utf-8")
    assert "✅" in V.khoi_dong(chay_luong=False)


def test_chi_phi_cong_dung_run_cua_viec(nen):
    a = nen.tao_run("x~y", {}, [1] * 100, "SUCCEEDED")
    b = nen.tao_run("x~y", {}, [1] * 50, "SUCCEEDED")
    nen.tao_run("x~y", {}, [1] * 999, "SUCCEEDED")         # run của người khác cùng actor
    kq = A._chi_phi_cac_run([a, b, a])
    assert kq == {"usd": 0.15, "so_run": 2, "chua_doc": 0}


# ───────────────────────────── deep dive ─────────────────────────────
def test_deep_dive_kep_30000_va_5_usd_tai_cho(monkeypatch):
    import deep_dive_tool as D
    import lsr_policy
    monkeypatch.setattr(lsr_policy, "cau_hinh_tool",
                        lambda t: {"tran_binh_luan": 99999, "tran_usd_goi": 99})
    assert D._cau_hinh() == (30000, 5.0)
    assert D._cau_hinh(nen=True) == (30000, 50.0)


def test_deep_dive_lon_chay_nen_roi_ghi_sheet(nen, monkeypatch):
    import deep_dive_tool as D
    import phan_loai
    monkeypatch.setattr(D, "_cau_hinh", lambda nen=None: (30000, 50.0 if nen else 5.0))
    tok = A._NEN.set(False)
    A._NEN.reset(tok)
    monkeypatch.setattr(phan_loai, "phan_loai_binh_luan",
                        lambda rows, han, tt=None: [("Tích cực", "sản phẩm")] * len(rows))
    urls = [f"https://www.tiktok.com/@a/video/{1000000 + i}" for i in range(40)]
    kq = json.loads(D._handle({"post_urls": urls, "max_comments": 100}))
    assert kq["dang_chay_nen"] and "1500" in kq["ly_do_chay_nen"]
    assert nen.post_urls == []
    nen.so_item = lambda actor, p: 3
    d = V.chay_ngay(kq["ma_viec"])
    assert d["trang_thai"] in ("xong", "xong_mot_phan")
    assert len(nen.post_urls) == len(d["nen_tang"]["tiktok"]["phan"]) >= 2
    van = d["thong_bao"]["ket_qua"]
    assert "Bóc bình luận nền" in van and "https://lark.test/sheets/shtA" in van
    assert nen.so_chi_phi[-1]["ma_viec"] == kq["ma_viec"]


def test_deep_dive_nho_van_chay_tai_cho(nen, monkeypatch):
    import deep_dive_tool as D
    monkeypatch.setattr(D, "_cau_hinh", lambda nen=None: (300, 0.5))
    kq = json.loads(D._handle({"post_urls": ["https://www.tiktok.com/@a/video/1234567"],
                               "max_comments": 50, "chi_uoc_tinh": True}))
    assert kq["chi_uoc_tinh"] and kq["se_chay_nen"] is False and not V.tat_ca()



def test_nam_nen_tang_mot_viec_chuan_hoa_dung(nen, monkeypatch):
    """Mỗi nền tảng một tab; Facebook gói Free chỉ 20 bài; YouTube không tốn tiền Apify."""
    def yt(q, lim, country, tu, den, toi_da_trang=None):
        return ([({"kenh": f"y{i}", "text": f"hapas review túi {i}", "views": 9,
                   "link": f"https://www.youtube.com/watch?v=v{tu:%d}{i:05d}"}, NOW)
                 for i in range(toi_da_trang * 50)], toi_da_trang, False)
    monkeypatch.setattr(A, "_youtube_tim", yt)
    kq = _quet(platforms=["tiktok", "instagram", "facebook", "threads", "youtube"],
               limit=700, chay_nen=True)
    assert kq["dang_chay_nen"], kq
    d = V.chay_ngay(kq["ma_viec"])
    per = d["ket_qua"]["per"]
    assert set(per) == {"tiktok", "instagram", "facebook", "threads", "youtube"}
    assert per["facebook"]["scraped"] == 20 and per["youtube"]["scraped"] == 700
    assert per["instagram"]["giu"] > 0 and per["threads"]["giu"] > 0
    tab = {b["requests"][0]["addSheet"]["properties"]["title"]
           for m, p, b, q in nen.lark.goi
           if p.endswith("sheets_batch_update") and "addSheet" in b["requests"][0]}
    assert {"TikTok", "Instagram", "Facebook", "Threads", "YouTube"} <= tab
    assert not any("/acts/youtube" in u for u in nen.post_urls)
    assert "Facebook" in d["thong_bao"]["ket_qua"] and "Chưa phủ" in d["thong_bao"]["ket_qua"]
