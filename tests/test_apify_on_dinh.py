"""Canh độ tin cậy NGUỒN của social_listen (đợt 2, rà audit 01/10/2026).

Lỗi thật đã gặp:
  • Threads: run-sync cắt ở 120s, run KHÔNG bị huỷ -> tool báo lỗi không dữ liệu mà Apify
    vẫn tính $0,08–0,165; run mồ côi giữ chỗ đồng thời -> "lỗi chạy đồng thời".
  • Facebook gói Free (20 bài/lượt, 1 lượt/24h): mỗi từ khoá một run, chỉ run đầu có
    dữ liệu; run-sync giấu `statusMessage` nên "hết lượt" trông như "0 bài".
  • `with ThreadPoolExecutor` chờ luồng chậm nhất: tool chạy 340s / 508s so với hạn 135s.
  • 403 "Monthly usage hard limit exceeded" khi hết $5 tháng — người dùng nghe "hết token".
  • Lọc từ khoá loại luôn UGC bàn về quảng cáo HAPAS mà không gọi tên brand (19:03).
Không chạm mạng: mọi HTTP là fake, đồng hồ/giấc ngủ là giả.
"""
from __future__ import annotations

import datetime
import json
import threading
import time

import pytest

import apify_tool as A

BI_MAT = "apify_api_BIMAT_W2_123456"
NOW = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(hours=1)


class R:
    def __init__(self, code=200, data=None, text=None):
        self.status_code = code
        self._d = data
        self.text = text if text is not None else json.dumps(data)

    def json(self):
        return self._d


class GiaApify:
    """Fake Apify: hàng đợi phản hồi cho POST /runs, chuỗi trạng thái cho GET actor-runs."""

    def __init__(self, t):
        self.t = t
        self.run = {"id": "run1", "status": "RUNNING", "defaultDatasetId": "ds1",
                    "statusMessage": ""}
        self.start: list = []
        self.trang_thai = ["SUCCEEDED"]
        self.items: list = [{"i": 1}, {"i": 2}]
        self.post_urls: list = []
        self.headers: list = []
        self.abort: list = []
        self.get_urls: list = []
        self.khac = lambda url, params: R(404, {})

    def post(self, url, json=None, **k):
        self.headers.append(k.get("headers") or {})
        if url.endswith("/abort"):
            self.abort.append(url)
            return R(200, {"data": {"status": "ABORTED"}})
        self.post_urls.append(url)
        x = self.start.pop(0) if self.start else R(201, {"data": dict(self.run)})
        if isinstance(x, Exception):
            raise x
        return x

    def get(self, url, params=None, **k):
        self.get_urls.append((url, params))
        if "/actor-runs/" in url:
            self.t[0] += (params or {}).get("waitForFinish", 0)
            st = self.trang_thai.pop(0) if len(self.trang_thai) > 1 else self.trang_thai[0]
            return R(200, {"data": {**self.run, "status": st}})
        if "/datasets/" in url:
            return R(200, list(self.items))
        return self.khac(url, params)


@pytest.fixture
def api(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(A, "_dong_ho", lambda: t[0])
    monkeypatch.setattr(A, "_ngu", lambda s: t.__setitem__(0, t[0] + s))
    monkeypatch.setenv("APIFY_TOKEN", BI_MAT)
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    A._NHO_APIFY.clear()
    g = GiaApify(t)
    monkeypatch.setattr(A.requests, "post", g.post)
    monkeypatch.setattr(A.requests, "get", g.get)
    yield g
    A._NHO_APIFY.clear()


# ───────────────────────────── _run_actor ─────────────────────────────

def test_running_roi_succeeded_tra_item(api):
    api.trang_thai = ["RUNNING", "SUCCEEDED"]
    items, meta = A._run_actor("futurizerush~meta-threads-scraper", {"x": 1}, 30, 1024,
                               deadline=1000 + 200)
    assert items == [{"i": 1}, {"i": 2}]
    assert meta["status"] == "SUCCEEDED" and meta["run_id"] == "run1" and meta["ma"] == "OK"
    url = api.post_urls[0]
    assert "/acts/futurizerush~meta-threads-scraper/runs?" in url
    for k in ("maxItems=30", "maxTotalChargeUsd=1.0", "memory=1024", "waitForFinish=",
              "timeout="):
        assert k in url, k
    assert "run-sync" not in url and "token" not in url and BI_MAT not in url
    assert api.headers[0]["Authorization"] == f"Bearer {BI_MAT}"
    ds = [p for u, p in api.get_urls if "/datasets/ds1/items" in u]
    assert ds and ds[0]["clean"] == 1 and ds[0]["limit"] == 30
    assert api.abort == []


def test_qua_han_thi_huy_run_va_giu_item_mot_phan(api):
    api.trang_thai = ["RUNNING"]
    items, meta = A._run_actor("a~b", {}, 50, deadline=1000 + 30, mot_phan=True)
    assert items == [{"i": 1}, {"i": 2}]
    assert meta["ma"] == "QUA_GIO" and meta["da_huy"] is True
    assert api.abort == [f"{A._APIFY_BASE}/actor-runs/run1/abort"]
    assert "đã dừng run" in meta["ly_do"]


def test_qua_han_ma_ben_goi_khong_doc_meta_thi_nem_loi_nhung_van_huy(api):
    """account_tool, deep_dive… không đọc được meta: giữ hợp đồng cũ (đủ dữ liệu hoặc lỗi)."""
    api.trang_thai = ["RUNNING"]
    with pytest.raises(A.LoiApify) as e:
        A._run_actor("a~b", {}, 50, deadline=1000 + 30)
    assert e.value.ma == "QUA_GIO" and api.abort


def test_call_trong_handle_nhan_mot_phan_va_ghi_so(api):
    api.trang_thai = ["RUNNING"]
    so: list = []
    tok1, tok2 = A._SO_RUN.set(so), A._HAN_CHOT.set(1000 + 30)
    try:
        items = A._call("a~b", {}, 50)
    finally:
        A._SO_RUN.reset(tok1)
        A._HAN_CHOT.reset(tok2)
    assert len(items) == 2 and so[0]["ma"] == "QUA_GIO" and so[0]["run_id"] == "run1"
    assert A.meta_lan_cuoi()["run_id"] == "run1"
    assert A._tong_hop_nguon(items, so)["status"] == "OK_MOT_PHAN"
    assert A._tong_hop_nguon([], [dict(so[0])])["status"] == "QUA_GIO"


def test_nghen_dong_thoi_thu_lai_mot_lan_roi_bao(api):
    loi = R(402, text='{"error":{"type":"actor-memory-limit-exceeded","message":"By launching '
                      'this job you will exceed the memory limit of 8192MB"}}')
    api.start = [loi, loi, R(201, {"data": api.run})]
    with pytest.raises(A.LoiApify) as e:
        A._run_actor("a~b", {}, 10, deadline=1000 + 120)
    assert e.value.ma == "NGHEN_DONG_THOI" and len(api.post_urls) == 2
    assert api.t[0] >= 1008, "phải lùi lại trước khi thử lần hai"


def test_loi_5xx_thu_lai_thanh_cong(api):
    api.start = [R(503, text="Service Unavailable")]
    items, meta = A._run_actor("a~b", {}, 10, deadline=1000 + 120)
    assert items and len(api.post_urls) == 2


def test_read_timeout_khong_thu_lai_tranh_chay_trung(api):
    api.start = [A.requests.ReadTimeout("read timed out")]
    with pytest.raises(A.LoiApify):
        A._run_actor("a~b", {}, 10, deadline=1000 + 120)
    assert len(api.post_urls) == 1


def test_403_het_tien_thang_kem_so_tien_va_ngay_reset(api, monkeypatch):
    monkeypatch.setenv("APIFY_KIEM_TRUOC", "1")
    api.khac = lambda url, params: R(200, {"data": {
        "monthlyUsageCycle": {"startAt": "2026-09-26T00:00:00.000Z",
                              "endAt": "2026-10-25T23:59:59.999Z"},
        "limits": {"maxMonthlyUsageUsd": 5}, "current": {"monthlyUsageUsd": 4.5}}}) \
        if url.endswith("/users/me/limits") else R(404, {})
    api.start = [R(403, text='{"error":{"type":"platform-feature-disabled","message":'
                             '"Monthly usage hard limit exceeded"}}')]
    with pytest.raises(A.LoiApify) as e:
        A._run_actor("a~b", {}, 10, deadline=1000 + 120)
    assert e.value.ma == "HET_TIEN_THANG" and len(api.post_urls) == 1
    assert "Tài khoản Apify đã dùng $4.50/$5 tháng này, reset ngày 26/10" in str(e.value)


def test_het_tien_thang_kiem_truoc_thi_khong_khoi_chay(api, monkeypatch):
    monkeypatch.setenv("APIFY_KIEM_TRUOC", "1")
    api.khac = lambda url, params: R(200, {"data": {
        "monthlyUsageCycle": {"endAt": "2026-10-25T23:59:59.999Z"},
        "limits": {"maxMonthlyUsageUsd": 5}, "current": {"monthlyUsageUsd": 5.02}}})
    with pytest.raises(A.LoiApify) as e:
        A._run_actor("a~b", {}, 10, deadline=1000 + 120)
    assert e.value.ma == "HET_TIEN_THANG" and api.post_urls == []


def test_free_tier_dataset_rong_la_het_luot_24h(api):
    api.run["statusMessage"] = ("Free tier: up to 20 results per run, 1 run per 24h. Upgrade "
                                "your Apify plan to lift these limits: https://console.apify.com")
    api.items = []
    with pytest.raises(A.LoiApify) as e:
        A._run_actor("scrapeforge~facebook-search-posts", {}, 20, deadline=1000 + 120)
    assert e.value.ma == "HET_LUOT_24H" and "KHÔNG phải không có bài" in str(e.value)


def test_free_tier_co_du_lieu_van_ok_kem_gioi_han(api):
    api.run["statusMessage"] = "Free tier: up to 20 results per run, 1 run per 24h."
    items, meta = A._run_actor("scrapeforge~facebook-search-posts", {}, 20, deadline=1000 + 120)
    assert items and meta["ma"] == "OK" and "20 bài/lượt" in meta["gioi_han_goi"]


def test_token_khong_bao_gio_nam_trong_chuoi_loi(api):
    api.start = [A.requests.ConnectionError(f"Max retries with url /v2/acts?token={BI_MAT}")] * 2
    with pytest.raises(A.LoiApify) as e:
        A._run_actor("a~b", {}, 10, deadline=1000 + 120)
    assert BI_MAT not in str(e.value) and BI_MAT not in json.dumps(e.value.meta)
    api.start = [R(400, text=f"bad input, echo token={BI_MAT} {BI_MAT}")]
    with pytest.raises(A.LoiApify) as e:
        A._run_actor("a~b", {}, 10, deadline=1000 + 120)
    assert BI_MAT not in str(e.value)
    api.start = []
    api.run.update(status="FAILED", statusMessage=f"crash with {BI_MAT}")
    api.items = []
    with pytest.raises(A.LoiApify) as e:
        A._run_actor("a~b", {}, 10, deadline=1000 + 120)
    assert BI_MAT not in str(e.value) and BI_MAT not in json.dumps(e.value.meta)


def test_tran_usd_rieng_thay_tran_console(api, monkeypatch):
    monkeypatch.setattr(A, "_tran", lambda: (500, 0.37))
    A._call("streamers~youtube-comments-scraper", {}, 10, min_charge=0.5, tran_usd=0.5)
    assert "maxTotalChargeUsd=0.5" in api.post_urls[-1]
    A._call("a~b", {}, 10, tran_usd=99)
    assert "maxTotalChargeUsd=5.0" in api.post_urls[-1], "vẫn kẹp trong khoảng an toàn"
    A._call("a~b", {}, 10)
    assert "maxTotalChargeUsd=0.37" in api.post_urls[-1], "không truyền thì như cũ"
    n = len(api.post_urls)
    with pytest.raises(RuntimeError, match="thấp hơn mức tối thiểu"):
        A._call("a~b", {}, 10, min_charge=0.5, tran_usd=0.3)
    with pytest.raises(RuntimeError, match="thấp hơn mức tối thiểu"):
        A._call("a~b", {}, 10, min_charge=0.5)
    assert len(api.post_urls) == n


def test_khong_qua_bon_run_cung_luc(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", BI_MAT)
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    dang, dinh, khoa = [0], [0], threading.Lock()

    def post(url, **k):
        with khoa:
            dang[0] += 1
            dinh[0] = max(dinh[0], dang[0])
        time.sleep(0.15)
        with khoa:
            dang[0] -= 1
        return R(201, [{"i": 1}])
    monkeypatch.setattr(A.requests, "post", post)
    ts = [threading.Thread(target=A._call, args=("a~b", {}, 5)) for _ in range(8)]
    for x in ts:
        x.start()
    for x in ts:
        x.join(10)
    assert 1 <= dinh[0] <= A._DONG_THOI_TOI_DA == 4


# ───────────────────────────── Facebook gói Free ─────────────────────────────

def _fb_get(lan_chay_cach_day_gio: float | None, goi="FREE", runs_ok=True):
    bat_dau = (datetime.datetime.now(datetime.timezone.utc)
               - datetime.timedelta(hours=lan_chay_cach_day_gio or 0))

    def khac(url, params):
        if url.endswith("/users/me"):
            return R(200, {"data": {"plan": {"id": goi}}})
        if url.endswith("/users/me/limits"):
            return R(200, {"data": {"limits": {"maxMonthlyUsageUsd": 5},
                                    "current": {"monthlyUsageUsd": 1.0},
                                    "monthlyUsageCycle": {"endAt": "2026-10-25T23:59:59.999Z"}}})
        if "/acts/scrapeforge~facebook-search-posts/runs" in url:
            if not runs_ok:
                return R(500, {})
            its = [] if lan_chay_cach_day_gio is None else [
                {"id": "fb1", "status": "SUCCEEDED",
                 "startedAt": bat_dau.isoformat().replace("+00:00", "Z")}]
            return R(200, {"data": {"items": its}})
        return R(404, {})
    return khac, bat_dau


def test_fb_free_da_dung_luot_thi_khong_chay_va_noi_gio_mo_lai(api, monkeypatch):
    monkeypatch.setenv("APIFY_KIEM_TRUOC", "1")
    api.khac, bat_dau = _fb_get(3)
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A.chi_phi_tool, "ghi", lambda **k: {})
    kq = json.loads(A._handle({"queries": ["hapas", "matemade"], "platforms": ["fb"],
                               "date_from": f"{NOW:%Y-%m-%d}", "date_to": f"{NOW:%Y-%m-%d}"}))
    assert api.post_urls == [], "đã dùng lượt 24h thì KHÔNG được khởi chạy run"
    fb = kq["per_platform"]["facebook"]
    mo_lai = (bat_dau + datetime.timedelta(hours=24)).astimezone(A._VN_TZ)
    dung = bat_dau.astimezone(A._VN_TZ)
    assert fb["status"] == "HET_LUOT_24H"
    assert (f"Facebook (gói Free): đã dùng lượt 24h lúc {dung:%H:%M %d/%m}, mở lại lúc "
            f"{mo_lai:%H:%M %d/%m}, tối đa 20 bài/lượt") in fb["ly_do"]
    assert fb["goi_y"] and kq["platforms_failed"] == ["facebook"]
    assert kq["note"].startswith("NGUỒN KHÔNG LẤY ĐƯỢC DỮ LIỆU")
    assert "như thể đầy đủ" in kq["note"]


@pytest.mark.parametrize("cach_day, runs_ok", [(30, True), (None, True), (3, False)])
def test_fb_free_con_luot_chi_quet_mot_tu_khoa_va_noi_ro(api, monkeypatch, cach_day, runs_ok):
    """Còn lượt (hoặc không đọc được lịch sử run) mà gói FREE: dồn vào MỘT từ khoá."""
    monkeypatch.setenv("APIFY_KIEM_TRUOC", "1")
    api.khac, _ = _fb_get(cach_day, runs_ok=runs_ok)
    goi = []
    monkeypatch.setattr(A, "_call", lambda actor, payload, limit, **k:
                        goi.append((payload, limit)) or [])
    so: list = []
    tok = A._SO_RUN.set(so)
    try:
        A._fetch_facebook(["hapas", "#HAPAS", "matemade"], 100, "VN", NOW, NOW)
    finally:
        A._SO_RUN.reset(tok)
    assert [p["query"] for p, _ in goi] == ["hapas"]
    assert goi[0][1] == 20 and goi[0][0]["max_results"] == 20
    assert "'hapas'" in so[0]["ghi_chu"] and "'matemade'" in so[0]["ghi_chu"]
    assert "'#HAPAS'" not in so[0]["ghi_chu"], "bản trùng sau chuẩn hoá không tính là bỏ sót"


def test_fb_khong_biet_goi_thi_chay_nhu_cu(api, monkeypatch):
    monkeypatch.setenv("APIFY_KIEM_TRUOC", "1")
    api.khac = lambda url, params: R(500, {})
    goi = []
    monkeypatch.setattr(A, "_call", lambda actor, payload, limit, **k:
                        goi.append(payload["query"]) or [])
    A._fetch_facebook(["hapas", "matemade"], 100, "VN", NOW, NOW)
    assert sorted(goi) == ["hapas", "matemade"]


# ───────────────────────────── Threads ─────────────────────────────

@pytest.mark.parametrize("q, limit, tu, max_posts", [
    (["HAPAS", "#HAPAS", "hapas", "Túi xách", "tui-xach"], 100, ["HAPAS", "Túi xách"], 50),
    (["hapas"], 30, ["hapas"], 30),
    (["hapas", "matemade", "pnj"], 100, ["hapas", "matemade", "pnj"], 34),
    (["hapas", "matemade"], 5, ["hapas", "matemade"], 10),       # actor đòi ≥10
])
def test_threads_bo_trung_va_chia_max_posts_theo_tu_khoa(monkeypatch, q, limit, tu, max_posts):
    goi = []
    monkeypatch.setattr(A, "_call", lambda actor, payload, lim, mem=None, **k:
                        goi.append((payload, lim, mem)) or [])
    A._fetch_threads(q, limit, "VN", NOW, NOW)
    payload, lim, mem = goi[0]
    assert payload["keywords"] == tu and payload["max_posts"] == max_posts
    assert payload["search_filter"] == "recent" and lim == limit and mem == 1024


# ───────────────────────────── hạn chót thật ─────────────────────────────

def test_handle_tra_ve_dung_han_du_nguon_treo(monkeypatch):
    monkeypatch.setattr(A, "_TOOL_DEADLINE", 1.0)
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A.chi_phi_tool, "ghi", lambda **k: {})
    tha = threading.Event()
    monkeypatch.setitem(A._FETCH, "threads", lambda *a: tha.wait(20) and [])
    t0 = time.monotonic()
    try:
        kq = json.loads(A._handle({"queries": ["hapas"], "platforms": ["threads"],
                                   "date_from": f"{NOW:%Y-%m-%d}",
                                   "date_to": f"{NOW:%Y-%m-%d}"}))
    finally:
        tha.set()
    assert time.monotonic() - t0 < 3, "không được chờ luồng treo (bug 340s/508s)"
    assert kq["per_platform"]["threads"]["status"] == "QUA_GIO"
    assert kq["platforms_failed"] == ["threads"]


def test_fanout_tra_loi_tung_tu_khoa_thanh_du_lieu_va_khong_cho_qua_han():
    tha = threading.Event()

    def fn(k):
        if k == "cham":
            tha.wait(20)
            return []
        if k == "hong":
            raise ValueError(f"vỡ ?token={BI_MAT}")
        return [{"k": k}]
    so, loi = [], []
    t1 = A._SO_RUN.set(so)
    t2 = A._HAN_CHOT.set(time.monotonic() - A._DU_PHONG_HUY + 1.5)
    t0 = time.monotonic()
    try:
        out = A._fanout(fn, ["nhanh", "cham", "hong"], loi_ra=loi)
    finally:
        A._SO_RUN.reset(t1)
        A._HAN_CHOT.reset(t2)
        tha.set()
    assert time.monotonic() - t0 < 3
    assert out == [{"k": "nhanh"}]
    ma = {x["tu_khoa"]: x["ma"] for x in so}
    assert ma == {"cham": "QUA_GIO", "hong": "LOI"} and loi == so
    assert BI_MAT not in json.dumps(so)
    tt = A._tong_hop_nguon(out, so)
    assert tt["status"] == "OK_MOT_PHAN" and "từ khoá 'hong'" in tt["ly_do"]


def test_het_ngan_sach_thang_thi_bo_nguon_tra_tien_giu_youtube(api, monkeypatch):
    monkeypatch.setenv("APIFY_KIEM_TRUOC", "1")
    api.khac = lambda url, params: R(200, {"data": {
        "monthlyUsageCycle": {"endAt": "2026-10-25T23:59:59.999Z"},
        "limits": {"maxMonthlyUsageUsd": 5}, "current": {"monthlyUsageUsd": 4.9}}})
    goi = []
    monkeypatch.setitem(A._FETCH, "tiktok", lambda *a: goi.append("tiktok") or [])
    monkeypatch.setitem(A._FETCH, "youtube", lambda *a: goi.append("youtube") or [])
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A.chi_phi_tool, "ghi", lambda **k: {})
    kq = json.loads(A._handle({"queries": ["hapas"], "platforms": ["tiktok", "youtube"],
                               "date_from": f"{NOW:%Y-%m-%d}", "date_to": f"{NOW:%Y-%m-%d}"}))
    assert goi == ["youtube"]
    tt = kq["per_platform"]["tiktok"]
    assert tt["status"] == "HET_TIEN_THANG"
    assert "Tài khoản Apify đã dùng $4.90/$5 tháng này, reset ngày 26/10" in tt["ly_do"]
    assert kq["per_platform"]["youtube"]["status"] == "OK"
    assert kq["nguon_loi"][0]["nen_tang"] == "tiktok"


# ───────────────────────────── AI cứu bài không nhắc tên ─────────────────────────────

def _bai(text, kenh, views=0, **kw):
    d = {"kenh": kenh, "followers": 0, "views": views, "likes": 0, "comments": 0,
         "shares": 0, "hashtags": "", "text": text, "link": f"https://x/{kenh}"}
    d.update(kw)
    return d


BIEU_CAM = _bai("Đây chính là biểu cảm của t khi xem 30 giây đầu của cái quảng cáo này =)))",
                "Linh Đan", views=954000)
DINH_KIEN = _bai("T biết brand lên ý tưởng cho campaign 20/10 nhưng cái quảng cáo này đâu đó "
                 "vẫn có định kiến về giới…", "Minh Thư", views=12000)
MASON = _bai("vote Tinh Hà ở đâu", "Mason Nguyễn", views=500)
CO_TEN = _bai("Mới mua túi Hapas xinh xỉu luôn mọi người ơi", "Ngọc Trâm")


@pytest.fixture
def quet(monkeypatch):
    ghi, hoi = [], []
    monkeypatch.setenv("SOCIAL_AI_CUU", "1")
    monkeypatch.setitem(A._FETCH, "threads", lambda *a: [(dict(d), NOW) for d in
                                                         (BIEU_CAM, DINH_KIEN, MASON, CO_TEN)])
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    monkeypatch.setattr(A, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(A, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(A, "_write_values", lambda tok, sid, rows, **k: ghi.append((sid, rows)))
    monkeypatch.setattr(A, "_them_tab", lambda tok, ten: "s2")
    monkeypatch.setattr(A, "_grant", lambda tok, oid: True)
    monkeypatch.setattr(A.memory_store, "get_current_sender", lambda: "ou_test")
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A.chi_phi_tool, "ghi", lambda **k: {})
    monkeypatch.setattr(A, "_loc_bang_ai", lambda rows, *a, trang_thai=None, **k: (
        trang_thai.update(trang_thai="bỏ qua vì quá ít bài", da_xet=0) or set()))

    def model(nhac, ngan_sach):
        """AI giả: chỉ giữ dòng nào bàn về 'quảng cáo' — như model thật nên làm."""
        hoi.append(nhac)
        dong = [x for x in nhac.splitlines() if x[:1].isdigit() and ". (" in x]
        return json.dumps({"giu": [int(x.split(".")[0]) for x in dong if "quảng cáo" in x]})
    monkeypatch.setattr(A, "_hoi_model", model)

    def chay(**them):
        args = {"queries": ["hapas"], "platforms": ["threads"],
                "date_from": f"{NOW - datetime.timedelta(days=2):%Y-%m-%d}",
                "date_to": f"{NOW + datetime.timedelta(hours=1):%Y-%m-%d}",
                "boi_canh": "HAPAS: túi xách, trang sức, nước hoa; đang chạy iTVC 20/10",
                **them}
        return json.loads(A._handle(args))
    return chay, ghi, hoi


def test_ai_cuu_ugc_ban_ve_quang_cao_va_khong_cuu_mason(quet):
    chay, ghi, hoi = quet
    kq = chay()
    assert kq["cuu_lai_boi_ai"] == 2 and kq["cuu_ai_trang_thai"] == "đã chạy"
    chinh, loai = ghi[0][1], ghi[1][1]
    assert chinh[0][-1] == "Ghi chú lọc"
    giu = {r[2]: r[-1] for r in chinh[1:]}
    assert giu["Linh Đan"] == giu["Minh Thư"] == A._GHI_CHU_CUU
    assert giu["Ngọc Trâm"] == "", "bài có tên brand không bị gắn nhãn cứu"
    assert [r[2] for r in loai[1:]] == ["Mason Nguyễn"]
    pp = kq["per_platform"]["threads"]
    assert pp["cuu_lai_boi_ai"] == 2 and pp["loai_vi_khong_chua_tu_khoa"] == 1
    assert pp["in_range"] == 3 and kq["in_range"] == 3 and kq["tong_bi_loai"] == 1
    assert "AI giữ lại 2 bài bàn về brand dù không nhắc tên" in kq["tom_tat_loai"]
    assert kq["tom_tat_loai"].startswith("Đã loại 1/4 bài không nhắc từ khoá")
    assert "KHÔNG CHẮC THÌ KHÔNG CHỌN" in hoi[0] and "iTVC 20/10" in hoi[0]
    assert "Ngọc Trâm" not in hoi[0], "chỉ gửi bài bị loại vì không nhắc từ khoá"


def test_nguon_mot_phan_khong_tinh_la_hong_nhung_note_noi_truoc(quet, monkeypatch):
    chay, ghi, _ = quet

    def threads(*a):
        A._SO_RUN.get().append({"tu_khoa": "matemade", "ma": "QUA_GIO", "run_id": "r9",
                                "ly_do": "Quá giờ sau 127s — đã dừng run trên Apify."})
        return [(dict(CO_TEN), NOW)]
    monkeypatch.setitem(A._FETCH, "threads", threads)
    kq = chay()
    tt = kq["per_platform"]["threads"]
    assert tt["status"] == "OK_MOT_PHAN" and tt["run_id"] == "r9" and tt["goi_y"]
    assert kq["platforms_failed"] == [] and kq["nguon_mot_phan"] == ["threads"]
    assert kq["note"].startswith("NGUỒN CHỈ CÓ MỘT PHẦN: Threads: từ khoá 'matemade'")
    assert kq["success"] is True and kq["sheet_url"]


def test_ai_cuu_can_boi_canh(quet):
    chay, ghi, hoi = quet
    kq = chay(boi_canh="")
    assert kq["cuu_lai_boi_ai"] == 0 and kq["cuu_ai_trang_thai"] == "bỏ qua vì thiếu boi_canh"
    assert hoi == []


def test_ai_cuu_hong_thi_bai_o_lai_tab_bi_loai(quet, monkeypatch):
    chay, ghi, _ = quet

    def hong(nhac, ngan_sach):
        raise RuntimeError("quota")
    monkeypatch.setattr(A, "_hoi_model", hong)
    kq = chay()
    assert kq["cuu_lai_boi_ai"] == 0 and kq["cuu_ai_trang_thai"] == "lỗi"
    assert len(ghi[1][1]) == 1 + 3 and ghi[0][1][0][-1] == "Từ khoá"


def test_ai_cuu_khong_xet_bai_ngoai_thi_truong(quet, monkeypatch):
    chay, ghi, hoi = quet
    thai = _bai("โฆษณานี้สวยมาก กระเป๋าใบนี้", "ร้านไทย", views=10**6)
    monkeypatch.setitem(A._FETCH, "threads", lambda *a: [(dict(d), NOW) for d in
                                                         (thai, BIEU_CAM, CO_TEN)])
    chay()
    assert "ร้านไทย" not in hoi[0] and "Linh Đan" in hoi[0]


def test_ai_cuu_gioi_han_60_bai_nhieu_view_nhat_va_ton_trong_han(monkeypatch):
    monkeypatch.setenv("SOCIAL_AI_CUU", "1")
    hoi = []
    monkeypatch.setattr(A, "_hoi_model", lambda nhac, ns: hoi.append(nhac) or '{"giu": [0]}')
    rows = [(dict(_bai(f"bài số {i}", f"k{i}", views=i), platform="threads"), NOW)
            for i in range(70)]
    tt: dict = {}
    giu = A._cuu_bang_ai(rows, ["hapas"], "túi", [], con_lai=50, trang_thai=tt)
    dong = [x for x in hoi[0].splitlines() if ". (threads)" in x]
    assert len(dong) == A._CUU_TOI_DA == 60
    assert "[k69]" in dong[0] and "[k10]" in hoi[0] and "[k9]" not in hoi[0]
    assert giu == {69} and tt == {"trang_thai": "đã chạy", "da_xet": 60}
    tt = {}
    assert A._cuu_bang_ai(rows, ["hapas"], "túi", [], con_lai=5, trang_thai=tt) == set()
    assert tt["trang_thai"] == "bỏ qua vì hết thời gian" and len(hoi) == 1
