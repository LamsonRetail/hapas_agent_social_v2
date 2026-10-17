"""Đường thu thập mới 17/10/2026 (chủ dự án duyệt mở đường mới, ưu tiên ĐỘ PHỦ rồi mới tới chi phí).

Số đo thật cùng ngày (phiên đo actor Apify vòng 1 + 2): Instagram tìm theo từ khoá của kho chưa
từng chạy được (apidojo chỉ trả demo cho gói Free), độ phủ IG 11%; FB 20% (scrapeforge 5 bài/lượt);
TikTok 70% (sót #hapassuperbrandday + feed #hapas). Fixture `mau_*.json` cắt từ raw thật của các
run đó (tên trường + kiểu giá trị giữ nguyên; tên/username/link của người dùng thường đã đổi
thành mã giả, chỉ tài khoản brand giữ)."""
from __future__ import annotations

import datetime
import json
import math
import pathlib
import time

import pytest

import apify_tool as A
import kiem_do_phu as KDP
import quet_lon as Q
import theo_doi as T
import theo_doi_api as TDA
from dashboard import chi_phi as CP

_VN = datetime.timezone(datetime.timedelta(hours=7))
_GOC = pathlib.Path(__file__).resolve().parent


@pytest.fixture
def mo(monkeypatch):
    """Như `test_theo_doi.mo`: mọi nền tảng bật (trần console 5 USD/lượt), có key YouTube, AI
    không phán gì, không lấy mẫu kiểm độ phủ."""
    monkeypatch.setattr(A, "_tran_nen_tang", lambda p, nen=None, c=None: (1000, 5.0, True))
    monkeypatch.setattr(A, "_youtube_co_key", lambda: True)
    monkeypatch.setattr(A, "_phan_xu_ai", lambda *a, **k: ({}, {"_sac_thai": {}, "_chu_de": {},
                                                                 "trang_thai": "đã chạy"}))
    import viec_nen
    monkeypatch.setattr(viec_nen, "tat_ca", list)
    monkeypatch.setattr(T, "_kiem_do_phu", lambda *a, **k: {})
    return monkeypatch


def _mau(ten: str) -> dict:
    return json.loads((_GOC / ten).read_text(encoding="utf-8"))


# ───────────────────────────── 1. Instagram: apify~instagram-hashtag-scraper ─────────────────────
def test_hashtag_ig_tu_tu_khoa():
    assert A.hashtag_ig("Túi xách HAPAS") == "tuixachhapas"
    assert A.hashtag_ig("hapas.vn") == "hapasvn"
    assert A.hashtag_ig("#Quà tặng 20/10") == "quatang2010"
    assert A.hashtag_ig("Đồng hồ_nữ!") == "dongho_nu"
    assert A.hashtag_ig("🥰") == "" and A.hashtag_ig(None) == ""
    assert A.hashtag_ig_ds(["hapas", "HAPAS", "túi hapas", "tui hapas", "", "🥰"]) == [
        "hapas", "tuihapas"]
    for s in ("Túi xách HAPAS", "hapas.vn", "#Quà tặng 20/10", "Đồng hồ_nữ!", "🥰"):
        assert CP.hashtag_ig(s) == A.hashtag_ig(s), "bản sao dashboard lệch Mark"
    assert A._ACTORS["instagram"] == "apify~instagram-hashtag-scraper"


def test_chuan_instagram_theo_raw_that():
    items = _mau("mau_ig_apify_hashtag.json")["items"]
    rows = A._chuan_instagram(items)
    loi = [it for it in items if it.get("error")]
    assert loi and len(rows) == len(items) - len(loi), "item lỗi hashtag rỗng không phải bài"
    theo = {d["__goc"]["shortCode"]: (d, dt) for d, dt in rows}
    for it in items:
        if it.get("error"):
            continue
        d, dt = theo[it["shortCode"]]
        assert d["link"] == it["url"] and d["username"] == it["ownerUsername"]
        assert d["kenh"] == it["ownerFullName"]
        assert d["likes"] == max(0, it["likesCount"]), "−1 (ẩn số thích) ghi 0"
        assert d["comments"] == it["commentsCount"]
        assert d["views"] == int(it.get("videoPlayCount") or it.get("videoViewCount") or 0)
        assert d["shares"] == int(it.get("sharesCount") or 0)
        assert dt == datetime.datetime.fromisoformat(it["timestamp"].replace("Z", "+00:00"))
        assert dt.utcoffset() == datetime.timedelta(hours=7)
        # Khoá bài IG giữ ĐÚNG cách cũ (shortcode trong link) — không trùng với bài đã có.
        assert T._khoa_bai("instagram", d["link"]) == f"instagram:{it['shortCode']}"
        assert d["hashtags"].split(", ")[0] == it["hashtags"][0]
    assert any(it.get("likesCount") == -1 for it in items), "fixture phải có bài ẩn số thích"
    reel = next(d for d, _ in rows if d["__goc"].get("videoPlayCount"))
    assert reel["views"] > 0


def test_chuan_instagram_thieu_url_thi_dung_link_shortcode():
    rows = A._chuan_instagram([
        {"shortCode": "AbC-1", "timestamp": "2026-10-16T01:00:00.000Z", "caption": "hapas"},
        {"url": "https://www.instagram.com/explore/tags/hapas"},           # không phải bài
        {"demo": True}, None])
    assert [d["link"] for d, _ in rows] == ["https://www.instagram.com/p/AbC-1/"]
    assert T._khoa_bai("instagram", rows[0][0]["link"]) == "instagram:AbC-1"


def test_truong_doc_nen_du_cho_bo_chuan_hoa():
    """Việc nền đọc dataset có `fields=` (`_TRUONG_ACTOR`): thiếu một trường là mất dữ liệu IM
    LẶNG — chuẩn hoá trên bản rút trường phải ra y bản đủ trường."""
    items = _mau("mau_ig_apify_hashtag.json")["items"]
    f = A._TRUONG_ACTOR[A._ACTORS["instagram"]]
    gon = [{k: it[k] for k in f if k in it} for it in items]

    def bo_goc(rows):
        return [({k: v for k, v in d.items() if k != "__goc"}, dt) for d, dt in rows]
    assert bo_goc(A._chuan_instagram(gon)) == bo_goc(A._chuan_instagram(items))


def _goi_gia(monkeypatch, items_theo_tab: dict, hong: dict | None = None) -> list:
    goi = []

    def call(actor, payload, limit, *a, **k):
        goi.append((actor, json.loads(json.dumps(payload)), limit))
        tab = payload.get("resultsType")
        if hong and tab in hong:
            raise A.LoiApify(hong[tab], f"{tab} hỏng", {"tu_khoa": A._TU_KHOA.get()})
        return items_theo_tab.get(tab, [])
    monkeypatch.setattr(A, "_call", call)
    return goi


def test_fetch_instagram_hai_run_moi_run_moi_hashtag(monkeypatch):
    items = _mau("mau_ig_apify_hashtag.json")["items"]
    bai = [it for it in items if it.get("type") != "Video"]
    reels = [it for it in items if it.get("type") == "Video"]
    goi = _goi_gia(monkeypatch, {"posts": bai, "reels": reels})
    rows = A._fetch_instagram(["hapas", "Túi xách HAPAS", "HAPAS", "quà tặng 20/10"], 50, "VN",
                              None, None)
    assert len(goi) == 2, "ít run nhất: một run mỗi tab"
    assert {p["resultsType"] for _, p, _ in goi} == {"posts", "reels"}
    tags = ["hapas", "tuixachhapas", "quatang2010"]
    per = math.ceil(50 / (2 * 3))
    for actor, p, lim in goi:
        assert actor == "apify~instagram-hashtag-scraper"
        assert p["hashtags"] == tags and p["resultsLimit"] == per and lim == per * 3
    assert len(rows) == len(A._chuan_instagram(items))


def test_fetch_instagram_mot_tab_loi_van_giu_tab_kia(monkeypatch):
    items = _mau("mau_ig_apify_hashtag.json")["items"]
    _goi_gia(monkeypatch, {"posts": items}, hong={"reels": "LOI"})
    loi: list = []
    tok = A._LOI_TU_KHOA.set(loi)
    try:
        rows = A._fetch_instagram(["hapas"], 20, "VN", None, None)
    finally:
        A._LOI_TU_KHOA.reset(tok)
    assert rows and [x.get("tu_khoa") for x in loi] == ["tab reels"]
    assert A._fetch_instagram(["🥰"], 20, "VN", None, None) == []


def test_tu_cho_va_uoc_instagram_khop_dashboard():
    tu = ["hapas", "túi hapas", "Hapas", "quà tặng hapas", "hapas.vn"]
    assert T._tu_cho("instagram", tu) == ["hapas", "tuihapas", "quatanghapas", "hapasvn"]
    assert T._tu_cho("instagram", tu, 2) == ["hapas", "tuihapas"]
    # 15 bài, 1 tag: 2 tab × ⌈15/2⌉ = 16 item × 0,0026 × 1,3 — không phí khởi động.
    assert T.uoc_tu_khoa_nen_tang("instagram", 15, ["hapas"]) == pytest.approx(
        16 * 0.0026 * 1.3, abs=1e-4)
    for so in (0, 1, 15, 100, 300):
        for so_tu in (1, 2, 12):
            assert CP.uoc_tk_nen_tang("instagram", so, tu, so_tu) == \
                T.uoc_tu_khoa_nen_tang("instagram", so, tu, so_tu)
    assert CP.TK_IG_TOI_DA_TU == T.TK_IG_TOI_DA_TU and CP.TK_IG_TAB == len(A._IG_TAB)
    assert A._UNIT_COST["instagram"] == T._TK_GIA["instagram"] == 0.0026
    assert A._START_COST["instagram"] == T._TK_KHOI["instagram"] == 0.0


def test_quet_lon_instagram_hai_luot_con_moi_tag():
    ts = {"date_from": "2026-10-01", "date_to": "2026-10-17", "country": "VN"}
    kh = Q._ke_instagram(["hapas", "túi hapas"], 40, ts, {})
    assert [ph["tab"] for ph in kh["phan"]] == ["posts", "reels"]
    for ph in kh["phan"]:
        assert ph["limit"] == 20
        assert Q.dung_payload("instagram", ph, ts) == {
            "hashtags": ["hapas", "tuihapas"], "resultsType": ph["tab"], "resultsLimit": 10}
    # Kế hoạch cắt limit (thu_nho) rồi dựng lại payload: trần mỗi tag co theo.
    assert Q.dung_payload("instagram", dict(kh["phan"][0], limit=7), ts)["resultsLimit"] == 3
    assert A._ACTORS["instagram"] not in Q._RAM_NEN, "actor tính theo item: không ghim RAM"


# ───────────────────────────── 2. Facebook đường 2: mina_safwat~facebook-search-actor ──────────────
def _mina(lui_gio: float = 24) -> list[dict]:
    """Item mina thật (cắt gọn) với giờ đăng dời về `lui_gio` giờ trước — bài thử không phụ thuộc
    ngày chạy."""
    items = _mau("mau_fb_mina.json")["items"]
    goc = max(int(it["video_details"]["publish_timestamp"]) for it in items)
    moi = (datetime.datetime.now(datetime.timezone.utc).timestamp() - lui_gio * 3600) * 1000
    ra = json.loads(json.dumps(items))
    for it in ra:
        vd = it["video_details"]
        vd["publish_timestamp"] = vd["publish_date"] = int(moi - (goc - vd["publish_timestamp"]))
    return ra


def test_chuan_facebook_mina_theo_raw_that():
    items = _mau("mau_fb_mina.json")["items"]
    rows = A._chuan_facebook_mina(items, "túi hapas")
    assert len(rows) == len(items)
    for (d, dt), it in zip(rows, items):
        st, vd = it["statistics"], it["video_details"]
        ow = vd["owner"]["owner_as_page"]
        assert d["link"] == it["url"] and d["kenh"] == it["owner_name"]
        assert d["likes"] == st["reaction_count"]["count"] and d["comments"] == st["comment_count"]
        assert d["shares"] == st["shares_count"] and d["views"] == int(st["video_view_count"] or 0)
        assert d["link_chu"] == ow["profile_url"] and d["username"]
        assert dt == datetime.datetime.fromtimestamp(vd["publish_timestamp"] / 1000,
                                                     datetime.timezone.utc)
        assert d["ma_so_fb"] == it["post_id"] and d["ma_so_fb"].isdigit()
        assert d["_duong"] == "mina" and d["_cum"] == "túi hapas" and d["followers"] == 0
        assert d["text"] == it["post_title"]
    assert {it["type"] for it in items} == {"post", "video"}
    assert A._slug_fb("https://www.facebook.com/people/Ethan-Mike/61579321204843/") == \
        "61579321204843"
    assert A._slug_fb("https://www.facebook.com/profile.php?id=100012") == "100012"
    assert A._slug_fb("https://www.facebook.com/hapasglobal") == "hapasglobal"
    assert A.ma_so_fb("pfbid02J6wE8FxDkoHZX8oHmoAUJdYNZ66KYF") is None
    assert A.ma_so_fb(122180995688977373) == "122180995688977373" and A.ma_so_fb("") is None


def test_fetch_facebook_duong2_moi_cum_mot_run_ngay_tuyet_doi(monkeypatch):
    goi = []

    def call(actor, payload, limit, *a, tran_usd=None, nen_tang=None, **k):
        goi.append((actor, dict(payload), limit, tran_usd, nen_tang))
        return _mina()
    monkeypatch.setattr(A, "_call", call)
    tu = datetime.datetime(2026, 10, 14, tzinfo=_VN)
    den = datetime.datetime(2026, 10, 17, 19, 0, tzinfo=_VN)
    rows = A._fetch_facebook_duong2(["túi hapas", "Túi  HAPAS", "quà tặng hapas"], 12, tu, den,
                                    tran_usd=0.1)
    assert [g[1]["query"] for g in goi] == ["túi hapas", "quà tặng hapas"]   # bỏ trùng
    for actor, p, lim, tran, nt in goi:
        assert actor == "mina_safwat~facebook-search-actor" and lim == 12 and tran == 0.1
        assert nt == "facebook"
        assert p == {"query": p["query"], "limit": 12, "usePeriodFilter": False,
                     "startDate": "2026-10-14", "endDate": "2026-10-17"}, "period HỎNG: không gửi"
    assert {d["_cum"] for d, _ in rows} == {"túi hapas", "quà tặng hapas"}


def test_tu_fb_duong2_chi_cum_nhieu_tu_co_ten_brand():
    da = {"ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas", "quatanghapas", "hapas.vn",
                                       "quà tặng hapas", "yêu từ điều nhỏ nhất", "hapas perfume",
                                       "Túi xách HAPAS", "túi hapa"]}
    assert T.tu_fb_duong2(da) == ["túi hapas", "quà tặng hapas", "hapas perfume",
                                  "Túi xách HAPAS"]
    assert CP.tu_fb_duong2(da) == T.tu_fb_duong2(da)
    mm = {"ten": "Mate Made", "tu_khoa": ["túi mate made", "túi matemade", "made in vn"]}
    assert T.tu_fb_duong2(mm) == ["túi mate made", "túi matemade"] == CP.tu_fb_duong2(mm)


@pytest.mark.parametrize("ch, bat, so", [
    ({}, True, 12),
    ({"tu_khoa": {"facebook": {"duong2": {"so_bai_moi_tu": 30}}}}, True, 30),
    ({"tu_khoa": {"facebook": {"duong2": {"so_bai_moi_tu": 0}}}}, False, 0),
    ({"tu_khoa": {"facebook": {"duong2": {"bat": "false"}}}}, False, 12),
    ({"tu_khoa": {"facebook": {"duong2": {"bat": False, "so_bai_moi_tu": "rác"}}}}, False, 12),
    ({"tu_khoa": {"facebook": {"bat": False}}}, False, 12),               # tắt Facebook = tắt cả
    # Chưa lưu `bat`: theo đường chính; đã lưu bật rõ: 0 bài chỉ tắt scrapeforge.
    ({"tu_khoa": {"facebook": {"so_bai": 0}}}, False, 12),
    ({"tu_khoa": {"facebook": {"so_bai": 0, "duong2": {"bat": True}}}}, True, 12),
])
def test_cau_hinh_duong2_va_ban_sao_dashboard(ch, bat, so):
    da = {"ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas"], "tk_bat": True, "tk_so_bai": 15,
          "cau_hinh": ch}
    c2 = T.cau_hinh(da, "tu_khoa", "facebook")["duong2"]
    assert (c2["bat"], c2["so_bai_moi_tu"]) == (bat, so)
    assert c2["gio"] == T.TK_FB2_GIO and c2["gio_chien_dich"] == T.TK_FB2_GIO_CD
    assert CP.cau_hinh(da, "tu_khoa", "facebook") == T.cau_hinh(da, "tu_khoa", "facebook")
    assert not T.cau_hinh(dict(da, tk_bat=False), "tu_khoa", "facebook")["duong2"]["bat"]
    assert T.tk_co_bat(da) is True


def test_uoc_tinh_tinh_ca_duong2_va_khop_dashboard():
    da = {"ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas", "ví hapas", "quatanghapas"],
          "tk_bat": True, "tk_so_bai": 15, "cau_hinh": {}}
    # 2 cụm × (12 × 0,002 + 0,00005) × 1,3
    assert T.uoc_fb_duong2(2, 12) == pytest.approx(2 * (12 * 0.002 + 0.00005) * 1.3, abs=1e-4)
    assert CP.uoc_fb_duong2(2, 12) == T.uoc_fb_duong2(2, 12) and T.uoc_fb_duong2(0, 12) == 0
    tat = dict(da, cau_hinh={"tu_khoa": {"facebook": {"duong2": {"bat": False}}}})
    assert T.uoc_tu_khoa_du_an(da) == pytest.approx(
        T.uoc_tu_khoa_du_an(tat) + T.uoc_fb_duong2(2, 12), abs=1e-4)
    b = CP.bang_cau_hinh(da)
    assert b["tu_khoa"]["facebook"]["duong2"]["cum"] == ["túi hapas", "ví hapas"]
    assert b["tu_khoa"]["facebook"]["duong2"]["uoc"] == T.uoc_fb_duong2(2, 12)
    assert b["uoc_tk"] == pytest.approx(CP.bang_cau_hinh(tat)["uoc_tk"] + T.uoc_fb_duong2(2, 12),
                                        abs=1e-4)
    assert (CP.TK_FB2_GIA, CP.TK_FB2_KHOI, CP.TK_FB2_MOI_TU) == (
        T.TK_FB2_GIA, T.TK_FB2_KHOI, T.TK_FB2_MOI_TU)


# ── lượt tìm /theodoi: hai đường Facebook chạy cùng lượt ──
def _sf_tim(user: str, ma: str, text: str) -> tuple:
    """Một dòng đã chuẩn hoá của scrapeforge (đường chính)."""
    return ({"kenh": user, "username": "", "followers": 0, "views": 0, "likes": 3, "comments": 1,
             "shares": 0, "hashtags": "", "text": text,
             "link": f"https://www.facebook.com/{user}/posts/{ma}", "__goc": {}},
            datetime.datetime.now(_VN) - datetime.timedelta(hours=5))


def _chay_tk_fb(mo, sf, mina, du_an=None, v=None, con=5.0):
    import contextvars

    from test_theo_doi import DU_AN, GiaKhoTk, GiaViec
    kho = GiaKhoTk(mo)
    goi = {"facebook": [], T.TK_FB2: []}

    def f_sf(q, limit, country, d_from, d_to, **k):
        goi["facebook"].append(list(q))
        if isinstance(sf, Exception):
            raise sf
        return [(dict(d), dt) for d, dt in sf]

    def f_mina(q, per, d_from, d_to, tran_usd=None):
        goi[T.TK_FB2].append((list(q), per, d_from, tran_usd))
        fn = A._KHI_CO_RUN.get()
        for i, _ in enumerate(q):
            fn({"id": f"mina-{len(goi[T.TK_FB2])}-{i}"}, {})
        if isinstance(mina, Exception):
            raise mina
        return A._chuan_facebook_mina(mina, q[0])
    mo.setattr(A, "_FETCH", {"facebook": f_sf, T.TK_FB2: f_mina,
                             **{p: (lambda *a, **k: []) for p in ("tiktok", "instagram",
                                                                 "youtube")}})
    da = du_an or dict(DU_AN, tu_khoa=["hapas", "túi hapas", "quà tặng hapas"], tk_bat=True,
                       tk_so_bai=15)
    v = v or GiaViec({}, [])
    tk = contextvars.copy_context().run(T._tim_tu_khoa, v, da, 3, con, time.monotonic() + 600)
    return tk, kho, goi, v


def test_tim_tu_khoa_facebook_hai_duong_gop_bo_trung_pheu_rieng(mo):
    mina = _mina()
    trung = A._chuan_facebook_mina(mina[:1])[0][0]
    sf = [_sf_tim("shop.a", "1001", "túi hapas mới về"),
          ({**_sf_tim("x", "1", "x")[0], "link": trung["link"], "text": trung["text"]},
           datetime.datetime.now(_VN) - datetime.timedelta(hours=3))]
    tk, kho, goi, v = _chay_tk_fb(mo, sf, mina)
    assert goi["facebook"] and goi[T.TK_FB2][0][0] == ["túi hapas", "quà tặng hapas"]
    assert goi[T.TK_FB2][0][1] == T.TK_FB2_MOI_TU and goi[T.TK_FB2][0][3] >= 0.1
    f = tk["pheu"]["facebook"]
    assert f["ve"] == len(sf) + len(mina) and f["trung"] >= 1, "gộp rồi bỏ trùng theo khoá"
    assert f["duong"]["scrapeforge"] == {"ve": len(sf)}
    m = f["duong"]["mina"]
    assert m["ve"] == len(mina) and m["cum"] == 2 and m["moi_cum"] == T.TK_FB2_MOI_TU
    # Tiền đường 2: bài × 0,002 + run × 0,00005 (2 cụm = 2 run).
    assert m["usd"] == pytest.approx(len(mina) * 0.002 + 2 * 0.00005, abs=1e-6)
    ph = next(x for x in v.d["nen_tang"]["tu_khoa"]["phan"] if x["id"] == f"tk-{T.TK_FB2}")
    assert ph["usd_so"] == m["usd"] and ph["trang_thai"] == "xong"
    assert [x["run_id"] for x in v.d["nen_tang"]["tu_khoa"]["phan"]
            if x.get("nen_tang") == T.TK_FB2 and x.get("run_id")] == ["mina-1-0", "mina-1-1"]
    dong = next(c for c in T._cau_tk(tk) if c.startswith("phễu tìm Facebook"))
    assert f"theo đường: scrapeforge về {len(sf)}; mina về {len(mina)} (2 cụm × 12 bài" in dong
    ghi = [r for kieu, rows in kho.bai for r in rows]
    link_mina = {d["link"] for d, _ in A._chuan_facebook_mina(mina)}
    assert {r["nen_tang"] for r in ghi} == {"facebook"} and len(ghi) >= 4
    assert any(r["link"] in link_mina for r in ghi) and any(r["link"].endswith("/1001")
                                                            for r in ghi)
    assert T.TK_FB2 in T.doc_moc_tk("hapas"), "đường 2 có mốc riêng (cửa sổ + nhịp)"


def test_duong2_loi_khong_hong_duong_chinh(mo):
    tk, _, _, _ = _chay_tk_fb(mo, [_sf_tim("shop.a", "1001", "túi hapas mới về")],
                              A.LoiApify("LOI", "mina sập"))
    f = tk["pheu"]["facebook"]
    assert f["ve"] == 1 and f["duong"]["mina"]["loi"].startswith("LOI")
    assert any(c.startswith("tìm Facebook (đường 2): LOI") for c in tk["ghi_chu"])
    dong = next(c for c in T._cau_tk(tk) if c.startswith("phễu tìm Facebook"))
    assert "mina lỗi (LOI: mina sập)" in dong and f["giu"] == 1
    assert T.TK_FB2 not in T.doc_moc_tk("hapas") and "facebook" in T.doc_moc_tk("hapas")


def test_duong_chinh_loi_duong2_van_giu_bai(mo):
    tk, _, _, _ = _chay_tk_fb(mo, A.LoiApify("HET_LUOT_24H", "hết lượt"), _mina())
    f = tk["pheu"]["facebook"]
    assert "loi" not in f and f["ve"] == len(_mina()) and f["giu"] > 0
    assert f["duong"]["scrapeforge"]["loi"].startswith("HET_LUOT_24H")
    dong = next(c for c in T._cau_tk(tk) if c.startswith("phễu tìm Facebook"))
    assert "scrapeforge lỗi (HET_LUOT_24H" in dong and "mina về" in dong
    assert "facebook" not in T.doc_moc_tk("hapas") and T.TK_FB2 in T.doc_moc_tk("hapas")


def test_duong2_nhip_gio_va_tat(mo):
    _chay_tk_fb(mo, [], _mina())
    tk, _, goi, _ = _chay_tk_fb(mo, [], _mina())                  # ngay sau: < 20 giờ
    assert goi[T.TK_FB2] == [] and any("tìm Facebook (đường 2): bỏ qua (lượt trước" in c
                                       for c in tk["ghi_chu"])
    from test_theo_doi import DU_AN
    tat = dict(DU_AN, tu_khoa=["hapas", "túi hapas"], tk_bat=True, tk_so_bai=15,
               cau_hinh={"tu_khoa": {"facebook": {"duong2": {"bat": False}}}})
    _, _, goi, _ = _chay_tk_fb(mo, [], _mina(), du_an=tat)
    assert goi[T.TK_FB2] == [] and goi["facebook"]
    chi_d2 = dict(tat, cau_hinh={"tu_khoa": {"facebook": {"so_bai": 0, "duong2": {
        "gio": 0, "bat": True}}}})
    tk, _, goi, _ = _chay_tk_fb(mo, [], _mina(), du_an=chi_d2)
    assert goi["facebook"] == [] and goi[T.TK_FB2], "0 bài chỉ tắt scrapeforge, đường 2 vẫn chạy"
    assert tk["pheu"]["facebook"]["duong"]["scrapeforge"] == {"tat": True}


def test_duong2_co_con_theo_ngan_sach(mo):
    from test_theo_doi import DU_AN, GiaViec
    da = dict(DU_AN, tu_khoa=["túi hapas", "quà tặng hapas", "ví hapas"], tk_bat=True,
              tk_so_bai=0, cau_hinh={"tu_khoa": {"facebook": {"duong2": {"gio": 0, "bat": True}}}})
    v = GiaViec({}, [])
    v.d["ngan_sach_usd"] = T.uoc_fb_duong2(2, 12) + 0.001
    tk, _, goi, _ = _chay_tk_fb(mo, [], _mina(), du_an=da, v=v)
    assert goi[T.TK_FB2][0][0] == ["túi hapas", "quà tặng hapas"]
    assert any("co còn 2/3 cụm" in c for c in tk["ghi_chu"])
    v2 = GiaViec({}, [])
    v2.d["ngan_sach_usd"] = 0.01
    tk, _, goi, _ = _chay_tk_fb(mo, [], _mina(), du_an=da, v=v2)
    assert goi[T.TK_FB2] == [] and any("đường 2): bỏ qua (hết ngân sách" in c
                                       for c in tk["ghi_chu"])


def test_trang_ngan_sach_luu_duong2_facebook():
    from test_dashboard_app import QL, dang_nhap, tao, thong_bao
    _, c, kho = tao()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15,
                              tu_khoa=["hapas", "túi hapas", "quà tặng hapas"],
                              cau_hinh={"tu_khoa": {"facebook": {"duong2": {"gio": 8}}}})
    csrf = dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert 'data-nt="facebook_d2"' in t and 'name="tk_facebook_d2_so_bai"' in t
    assert 'data-o="fb2-so-cum" title="Cụm nhiều từ có tên brand">2<' in t
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "tk_facebook_bat": "1",
                                                   "tk_facebook_d2_so_bai": "20"})
    assert "Đã lưu cấu hình thu thập" in thong_bao(c, r)
    d2 = kho.du_an["hapas"]["cau_hinh"]["tu_khoa"]["facebook"]["duong2"]
    assert d2 == {"gio": 8, "bat": False, "so_bai_moi_tu": 20}, "giữ khoá biểu mẫu không sửa"
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "tk_facebook_bat": "1",
                                                   "tk_facebook_d2_bat": "1",
                                                   "tk_facebook_d2_so_bai": ""})
    d2 = kho.du_an["hapas"]["cau_hinh"]["tu_khoa"]["facebook"]["duong2"]
    assert d2 == {"gio": 8, "bat": True}
    # Biểu mẫu cũ (không có ô đường 2): khối duong2 giữ nguyên.
    c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "tk_facebook_bat": "1"})
    assert kho.du_an["hapas"]["cau_hinh"]["tu_khoa"]["facebook"]["duong2"] == d2


# ───────────────── 3. theo dõi trang Facebook: thedoor~facebook-page-scraper + dự phòng ─────────────
def _thedoor() -> list[dict]:
    return _mau("mau_fb_thedoor.json")["items"]


@pytest.mark.parametrize("dd", ["https://www.facebook.com/hapasglobal",
                                "https://www.facebook.com/HapasGlobal/",
                                "https://www.facebook.com/profile.php?id=100066634543565"])
def test_doc_thedoor_theo_raw_that_va_ghep_nguon(dd):
    items = _thedoor()
    ket = TDA.doc_thedoor(items, ["https://www.facebook.com/khac", dd])
    (tk,) = ket.values()
    assert tk["ho_so"]["ten"] == "HAPAS" and len(tk["bai"]) == len(items)
    for b, it in zip(tk["bai"], items):
        eg = it["engagement"]
        assert b["link"] == it["post"]["url"] and "/posts/" in b["link"]
        assert b["ngay"] == datetime.datetime.fromtimestamp(it["created"]["timestamp"],
                                                            datetime.timezone.utc)
        assert (b["like"], b["binh_luan"], b["share"]) == (eg["reactions"], eg["comments"],
                                                           eg["shares"])
        assert b["view"] == (eg["views"] or None)
        assert b["loai"] == ("video" if it["video"]["is_video"] else "bài")
        assert b["_goc"]["postId"] == it["post"]["id"] and b["_goc"]["inputUrl"] == dd
    assert any(b["view"] for b in tk["bai"]), "thedoor có view video (actor rẻ khác không có)"
    nguon = [{"id": 6, "nen_tang": "facebook", "dinh_danh": dd, "so_bai_moi_lan": 20},
             {"id": 7, "nen_tang": "facebook", "dinh_danh": "https://www.facebook.com/khac",
              "so_bai_moi_lan": 20}]
    kq, loi = T.ghep_nguon("facebook", ket, nguon)
    assert len(kq[6]) == len(items) and kq[7] == [] and 7 in loi
    for d, _ in kq[6]:
        assert d["ma_so_fb"] and d["ma_so_fb"].isdigit() and d["_goc_id"] == d["ma_so_fb"]
        assert T._khoa_bai("facebook", d["link"], {"id": d["_goc_id"]}) == \
            f"facebook:{d['ma_so_fb']}"


def test_gia_nguon_facebook_thedoor_khop_dashboard():
    assert T._GIA["facebook"] == TDA.FB_TRANG_GIA == 0.0025
    assert T._KHOI_NGUON["facebook"] == TDA.FB_TRANG_KHOI == 0.01
    for so_nguon, n in ((1, 5), (6, 20), (3, 1)):
        assert CP.uoc_mot_luot("facebook", so_nguon, n) == T._uoc_phan("facebook", so_nguon, n)
    assert T._uoc_phan("facebook", 6, 20) == pytest.approx((6 * 20 * 0.0025 + 0.01) * 1.3,
                                                           abs=1e-4)
    assert CP.phi_khoi_dong_ngay("facebook") == pytest.approx(0.01 * 1.3)
    assert CP.hang_so_cho_trinh_duyet()["khoi_nguon"]["facebook"] == 0.01
    import tiktok_api as TT
    assert TT.CHON["facebook_theo_doi"] == {"chinh": TDA.FB_TRANG,
                                            "du_phong": ("apify~facebook-posts-scraper",)}


def _fb_cu(trang: str, i: int) -> dict:
    """Item thật dạng apify~facebook-posts-scraper (actor dự phòng)."""
    return {"pageName": trang, "inputUrl": f"https://www.facebook.com/{trang}",
            "facebookUrl": f"https://www.facebook.com/{trang}", "postId": f"77{i:010d}",
            "url": f"https://www.facebook.com/{trang}/posts/pfbid0Mau{i}",
            "time": (datetime.datetime.now(datetime.timezone.utc)
                     - datetime.timedelta(hours=i + 1)).isoformat(),
            "likes": 5, "comments": 2, "shares": 0, "text": f"bài {i} của {trang}"}


class _GiaChay:
    """`A._run_actor` / `A._doc_tiep_run` giả theo actor; ghi mọi lượt gửi."""

    def __init__(self, mp, tra: dict):
        self.tra, self.gui, self.doc = tra, [], []
        mp.setattr(A, "_run_actor", self.run)
        mp.setattr(A, "_doc_tiep_run", self.doc_tiep)

    def run(self, actor, payload, limit, mem=None, deadline=None, min_charge=0, *, tran_usd=None,
            mot_phan=False, nen_tang=None):
        self.gui.append({"actor": actor, "payload": payload, "limit": limit, "tran": tran_usd})
        rid = f"r{len(self.gui)}"
        fn = A._KHI_CO_RUN.get()
        if fn:
            fn({"id": rid}, {})
        x = self.tra.get(actor)
        if isinstance(x, Exception):
            raise x
        return list(x or []), {"run_id": rid, "ma": "OK", "usd": 0.0}

    def doc_tiep(self, run_id, limit, deadline=None, mot_phan=True, actor=""):
        self.doc.append(run_id)
        return list(self.tra.get(actor) or []), {"run_id": run_id, "ma": "OK", "usd": 0.0}


def _chay_phan(v, ph, ds, cap: float = 1.0):
    """`theo_doi._chay_phan_apify` trong BẢN SAO ngữ cảnh như runner thật (`chay_viec`): cờ Apify
    (`_NEN_TANG`, `_KHI_CO_RUN`…) không rò sang bài thử khác."""
    import contextvars
    return contextvars.copy_context().run(T._chay_phan_apify, v, "facebook", ph, ds, cap,
                                          time.monotonic() + 300)


def _phan_fb(urls: list[str], n: int = 5):
    from test_theo_doi import GiaViec
    ds = [{"id": i + 1, "nen_tang": "facebook", "dinh_danh": u, "ten": u, "link": "",
           "loai": "kenh_nha", "so_bai_moi_lan": n, "chu_ky_ngay": 1, "quet_cuoi": None}
          for i, u in enumerate(urls)]
    (ph,) = T.chia_phan(ds)["facebook"]
    v = GiaViec({"facebook": {"phan": [ph]}}, [x["id"] for x in ds])
    return v, ph, ds


def test_trang_thedoor_thieu_thi_chay_actor_cu_cho_dung_trang_do(monkeypatch):
    urls = ["https://www.facebook.com/hapasglobal", "https://www.facebook.com/trang.khac"]
    v, ph, ds = _phan_fb(urls)
    ap = _GiaChay(monkeypatch, {TDA.FB_TRANG: _thedoor(),
                                ph["du_phong"]["actor"]: [_fb_cu("trang.khac", i)
                                                          for i in range(3)]})
    tien = _chay_phan(v, ph, ds)
    assert [g["actor"] for g in ap.gui] == [TDA.FB_TRANG, "apify~facebook-posts-scraper"]
    assert ap.gui[0]["payload"] == {"pageUrls": urls, "postsToScrape": 5}
    assert ap.gui[1]["payload"]["startUrls"] == [{"url": urls[1]}], "chỉ trang thedoor thiếu"
    assert ap.gui[1]["tran"] <= 1.0 - (len(_thedoor()) * 0.0025 + 0.01) + 1e-9
    assert ph["run_id"] == "r1" and ph["run_phu"] == ["r2"] and ph["du_phong_run"] == "r2"
    dong = {}
    for d, _ in v.doc_dong("facebook"):
        dong.setdefault(d["_nguon_id"], []).append(d)
    assert len(dong[1]) == len(_thedoor()) and len(dong[2]) == 3
    assert all(d["ma_so_fb"] for x in dong.values() for d in x)
    assert tien == pytest.approx(len(_thedoor()) * 0.0025 + 0.01 + 3 * 0.005 + 0.001, abs=1e-6)
    assert ph["trang_thai"] == "xong" and not ph.get("loi_nguon")


def test_thedoor_du_thi_khong_chay_du_phong_va_loi_dung_ca_luot_cung_khong(monkeypatch):
    v, ph, ds = _phan_fb(["https://www.facebook.com/hapasglobal"])
    ap = _GiaChay(monkeypatch, {TDA.FB_TRANG: _thedoor()})
    _chay_phan(v, ph, ds)
    assert [g["actor"] for g in ap.gui] == [TDA.FB_TRANG]
    v, ph, ds = _phan_fb(["https://www.facebook.com/hapasglobal"])
    ap = _GiaChay(monkeypatch, {TDA.FB_TRANG: A.LoiApify("HET_TIEN_THANG", "hết tiền")})
    _chay_phan(v, ph, ds)
    assert [g["actor"] for g in ap.gui] == [TDA.FB_TRANG] and ph["trang_thai"] == "loi"
    # thedoor lỗi thường (actor hỏng) → dự phòng cứu cả trang.
    v, ph, ds = _phan_fb(["https://www.facebook.com/hapasglobal"])
    ap = _GiaChay(monkeypatch, {TDA.FB_TRANG: A.LoiApify("LOI", "actor hỏng"),
                                "apify~facebook-posts-scraper": [_fb_cu("hapasglobal", 1)]})
    _chay_phan(v, ph, ds)
    assert [g["actor"] for g in ap.gui] == [TDA.FB_TRANG, "apify~facebook-posts-scraper"]
    assert len(v.doc_dong("facebook")) == 1 and ph["trang_thai"] == "mot_phan"


def test_khoi_dong_lai_doc_tiep_run_du_phong_khong_post_lai(monkeypatch):
    urls = ["https://www.facebook.com/hapasglobal", "https://www.facebook.com/trang.khac"]
    v, ph, ds = _phan_fb(urls)
    ph.update(run_id="r-cu", trang_thai="dang_chay", du_phong_run="r-dp", run_phu=["r-dp"])
    ap = _GiaChay(monkeypatch, {TDA.FB_TRANG: _thedoor(),
                                "apify~facebook-posts-scraper": [_fb_cu("trang.khac", 1)]})
    _chay_phan(v, ph, ds)
    assert ap.gui == [] and ap.doc == ["r-cu", "r-dp"]
    assert len(v.doc_dong("facebook")) == len(_thedoor()) + 1


# ───────────────── 4. TikTok: feed hashtag của từ khoá một chữ trong lượt tìm hằng ngày ─────────────
def test_tag_tiktok_tu_tu_khoa_mot_chu_va_ban_sao_dashboard():
    tu = ["hapas", "túi hapas", "#HAPAS", "hapas.vn", "HapasSuperBrandDay", "ab", "Quà"]
    assert T.tag_tiktok(tu) == ["hapas", "hapasvn", "hapassuperbrandday", "qua"]
    assert CP.tag_tiktok(tu) == T.tag_tiktok(tu)
    import tiktok_api as TT
    assert all(TT.chuan_tag(x) == x for x in T.tag_tiktok(tu))


@pytest.mark.parametrize("ch, bat, so", [
    ({}, True, 5),
    ({"tu_khoa": {"tiktok": {"hashtag": {"so_yeu_cau": 3}}}}, True, 3),
    ({"tu_khoa": {"tiktok": {"hashtag": {"so_yeu_cau": 0}}}}, False, 0),
    ({"tu_khoa": {"tiktok": {"hashtag": {"bat": "true"}}}}, False, 5),
    ({"tu_khoa": {"tiktok": {"bat": False}}}, False, 5),
    ({"tu_khoa": {"tiktok": {"so_bai": 0}}}, False, 5),
    ({"tu_khoa": {"tiktok": {"so_bai": 0, "hashtag": {"bat": True}}}}, True, 5),
])
def test_cau_hinh_feed_hashtag_va_uoc_tinh(ch, bat, so):
    da = {"ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas", "hapassuperbrandday"],
          "tk_bat": True, "tk_so_bai": 15, "cau_hinh": ch}
    c = T.cau_hinh(da, "tu_khoa", "tiktok")
    assert (c["hashtag"]["bat"], c["hashtag"]["so_yeu_cau"]) == (bat, so)
    assert c["hashtag"]["gio"] == T.TK_TAG_GIO
    assert CP.cau_hinh(da, "tu_khoa", "tiktok") == c
    b = CP.bang_cau_hinh(da)
    assert b["tu_khoa"]["tiktok"]["hashtag"]["tag"] == ["hapas", "hapassuperbrandday"]
    u = T.uoc_tag_tiktok(so, 2) if bat else 0.0
    assert b["tu_khoa"]["tiktok"]["hashtag"]["uoc"] == u
    assert u == (round(so * 0.003 * 1.3, 4) if bat else 0.0)
    tat = dict(da, cau_hinh={**ch, "tu_khoa": {**ch.get("tu_khoa", {}), "tiktok": {
        **(ch.get("tu_khoa", {}).get("tiktok") or {}), "hashtag": {"bat": False}}}})
    assert T.uoc_tu_khoa_du_an(da) == pytest.approx(T.uoc_tu_khoa_du_an(tat) + u, abs=1e-4)


def _tt_clockworks(vid: str, user: str, text: str, gio: float = 30) -> dict:
    """Item feed hashtag đã đổi sang shape clockworks (`tiktok_api.video`)."""
    luc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=gio)
    return {"id": vid, "text": text, "createTimeISO": luc.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "authorMeta": {"name": user, "nickName": user, "fans": 10}, "playCount": 50,
            "diggCount": 3, "commentCount": 1, "shareCount": 0,
            "hashtags": [{"name": "hapassuperbrandday"}],
            "webVideoUrl": f"https://www.tiktok.com/@{user}/video/{vid}",
            "_nguon": "TikTok API (scraptik)"}


def _gia_lay_mau(mo, feed=None) -> dict:
    goi: dict = {"mau": []}

    def lay_mau(trang_tag, trang_tg, cid, uid, ngan, d_from):
        goi["mau"].append((dict(trang_tag), dict(cid)))
        fn = A._KHI_CO_RUN.get()
        for i in range(sum(trang_tag.values()) + sum(1 for t in trang_tag if not cid.get(t))):
            fn({"id": f"tag-{len(goi['mau'])}-{i}"}, {"actor": T.TT_ACTOR})
        return ([(it, "#hapassuperbrandday") for it in (feed or [])],
                {"tag": {t: {"cid": cid.get(t) or f"cid-{t}", "bai": len(feed or []), "loi": ""}
                         for t in trang_tag}})
    mo.setattr(KDP, "lay_mau", lay_mau)
    return goi


def _chay_tk_tt(mo, du_an=None, feed=None, v=None, con=5.0):
    import contextvars

    from test_theo_doi import DU_AN, GiaKhoTk, GiaViec, _tt_tim
    GiaKhoTk(mo)
    goi = _gia_lay_mau(mo, feed)

    def tim_tt(q, limit, country, d_from, d_to, **k):
        A._KHI_CO_RUN.get()({"id": "run-tt"}, {"actor": T.TT_ACTOR})
        return [_tt_tim("kol.a", "7000000000000000001", "túi hapas đẹp")]
    mo.setattr(T, "_them_luot_moi", lambda v, ma, luot, q, got, *a, **k: (got, {}))
    mo.setattr(T, "_them_luot_noi", lambda v, ma, luot, q, got, *a, **k: (got, {}))
    mo.setattr(A, "_FETCH", {"tiktok": tim_tt, **{p: (lambda *a, **k: [])
                                                  for p in ("facebook", "instagram", "youtube")}})
    da = du_an or dict(DU_AN, tu_khoa=["hapas", "túi hapas", "hapassuperbrandday"], tk_bat=True,
                       tk_so_bai=15)
    v = v or GiaViec({}, [])
    tk = contextvars.copy_context().run(T._tim_tu_khoa, v, da, 3, con, time.monotonic() + 600)
    return tk, goi, v


@pytest.mark.tiktok_api
def test_feed_hashtag_trong_luot_tim_qua_cung_pheu(mo):
    feed = [_tt_clockworks("7000000000000000001", "kol.a", "túi hapas đẹp"),     # trùng lượt thường
            _tt_clockworks("7000000000000000002", "kol.b", "#hapassuperbrandday xinh"),
            _tt_clockworks("7000000000000000003", "kol.c", "hapas cũ", gio=24 * 60)]
    tk, goi, _ = _chay_tk_tt(mo, feed=feed)
    # 5 yêu cầu, chưa nhớ cid: #hapas cid + 2 trang, #hapassuperbrandday cid + 1 trang.
    assert goi["mau"] == [({"hapas": 2, "hapassuperbrandday": 1}, {})]
    f = tk["pheu"]["tiktok"]
    tf = f["tag_feed"]
    assert (tf["ve"], tf["moi"], tf["yeu_cau"]) == (3, 2, 5) and tf["chua_toi"] == []
    assert tf["usd"] == pytest.approx(5 * 0.003, abs=1e-9)
    assert f["ve"] == 3 and f["ngoai_pham_vi"] == 1, "bài feed qua cùng cửa sổ phạm vi ngày"
    assert tk["usd"] == pytest.approx(6 * 0.003, abs=1e-9), "1 yêu cầu thường + 5 feed"
    dong = next(c for c in T._cau_tk(tk) if c.startswith("phễu tìm TikTok"))
    assert "feed hashtag (chưa có lượt feed hashtag; #hapas 2 trang, #hapassuperbrandday 1 " \
           "trang; 5 yêu cầu): về 3, thêm 2 bài" in dong
    moc = T.doc_moc_tk("hapas")
    assert moc[T.TK_TAG]["usd"] == pytest.approx(0.015) and moc[T.TK_TAG]["tag"] == [
        "hapas", "hapassuperbrandday"]
    assert moc[KDP.KHOA_MOC]["cid"] == {"hapas": "cid-hapas",
                                        "hapassuperbrandday": "cid-hapassuperbrandday"}
    # Lượt sau trong 20 giờ: không đọc feed lại.
    _, goi2, _ = _chay_tk_tt(mo, feed=feed)
    assert goi2["mau"] == []


@pytest.mark.tiktok_api
def test_feed_hashtag_tran_ngan_sach_tag_luot_noi_va_tat(mo):
    import contextvars

    from test_theo_doi import DU_AN, GiaViec
    # Phần còn của tháng/việc chỉ đủ 1 yêu cầu thường (đã tiêu) + 2 feed → #hapas: cid + 1 trang.
    goi = _gia_lay_mau(mo)
    v = GiaViec({}, [])
    ctx = contextvars.copy_context()
    ctx.run(A._KHI_CO_RUN.set, lambda run, meta: T._them_phan_tk(v, {
        "id": run["id"], "nen_tang": "tiktok", "run_id": run["id"], "actor": T.TT_ACTOR}))
    _, tf = ctx.run(T._them_feed_tag, v, "hapas", 3, ["hapas", "hapassuperbrandday"], [], {},
                    datetime.datetime.now(_VN), {"bat": True, "so_yeu_cau": 5, "gio": 20},
                    3 * 0.003 + 0.0005, [{"run_id": "r0", "actor": T.TT_ACTOR}])
    assert goi["mau"] == [({"hapas": 1}, {})]
    assert tf["yeu_cau"] == 2 and tf["chua_toi"] == ["hapassuperbrandday"]
    assert "chưa tới #hapassuperbrandday (tăng số yêu cầu)" in T._cau_tag(tf)
    _, tf = ctx.run(T._them_feed_tag, v, "hapas", 3, ["hapas"], [], {},
                    datetime.datetime.now(_VN), {"bat": True, "so_yeu_cau": 5, "gio": 20},
                    0.004, [{"run_id": "r0", "actor": T.TT_ACTOR}])
    assert "không còn ngân sách" in tf["ly_do"] and len(goi["mau"]) == 1
    # Tag lượt nổi (kiểm độ phủ đã thêm) không đọc lại ở feed; cid đã nhớ thì không tìm lại.
    T.ghi_moc_tk("hapas", {KDP.KHOA_NOI_CFG: {"tag": ["hapas"]}, T.TK_TAG: {},
                           KDP.KHOA_MOC: {"cid": {"hapassuperbrandday": "c1"}}})
    _, goi, _ = _chay_tk_tt(mo)
    assert goi["mau"] == [({"hapassuperbrandday": 5}, {"hapassuperbrandday": "c1"})]
    tat = dict(DU_AN, tu_khoa=["hapas", "hapassuperbrandday"], tk_bat=True, tk_so_bai=15,
               cau_hinh={"tu_khoa": {"tiktok": {"hashtag": {"bat": False}}}})
    T.ghi_moc_tk("hapas", {T.TK_TAG: {}})
    _, goi, _ = _chay_tk_tt(mo, du_an=tat)
    assert goi["mau"] == []


def test_trang_ngan_sach_luu_feed_hashtag_tiktok():
    from test_dashboard_app import QL, dang_nhap, tao, thong_bao
    _, c, kho = tao()
    kho.du_an["hapas"].update(tk_bat=True, tk_so_bai=15,
                              tu_khoa=["hapas", "túi hapas", "hapassuperbrandday"])
    csrf = dang_nhap(c, QL)
    t = c.get("/ngan-sach").text
    assert 'data-nt="tiktok_tag"' in t and 'name="tk_tiktok_tag_so_yc"' in t
    assert 'data-o="tt-tag-so" title="Từ khoá một chữ thành hashtag">2<' in t
    r = c.post("/ngan-sach/hapas/cau-hinh", data={"csrf": csrf, "tk_tiktok_bat": "1",
                                                   "tk_tiktok_tag_bat": "1",
                                                   "tk_tiktok_tag_so_yc": "3"})
    assert "Đã lưu cấu hình thu thập" in thong_bao(c, r)
    assert kho.du_an["hapas"]["cau_hinh"]["tu_khoa"]["tiktok"]["hashtag"] == {
        "bat": True, "so_yeu_cau": 3}
    assert CP.bang_cau_hinh(kho.du_an["hapas"])["tu_khoa"]["tiktok"]["hashtag"]["uoc"] == \
        T.uoc_tag_tiktok(3, 2)


# ───────────────── 5. scripts/lang_nghe_bu_ig.py: bù lịch sử Instagram kênh nhà (một lần) ─────────────
def _bu_ig():
    import importlib.util
    spec = importlib.util.spec_from_file_location("lang_nghe_bu_ig",
                                                  _GOC.parent / "scripts" / "lang_nghe_bu_ig.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _fz(lui_ngay: float = 10) -> list[dict]:
    """Item futurizerush thật (cắt gọn) với giờ đăng dời về `lui_ngay` ngày trước."""
    items = json.loads(json.dumps(_mau("mau_ig_futurizerush_profile.json")["items"]))
    for i, it in enumerate(items):
        luc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=lui_ngay + i)
        it["timestamp"] = luc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return items


class _KhoBuIg:
    def __init__(self, mp, dang_chay=None, da_tieu=0.0):
        import lang_nghe_db as K
        self.bai, self.dong, self.mo = [], [], []
        da = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas"], "tu_loai_tru": [],
              "boi_canh": "HAPAS", "thi_truong": "VN", "tran_usd_thang": 5.0}
        nguon = [{"id": 11, "nen_tang": "instagram", "dinh_danh": "hapas.vn", "loai": "kenh_nha",
                  "ten": "HAPAS", "so_bai_moi_lan": 5, "chu_ky_ngay": 1},
                 {"id": 12, "nen_tang": "instagram", "dinh_danh": "kol.x", "loai": "kol"},
                 {"id": 13, "nen_tang": "tiktok", "dinh_danh": "hapas.official",
                  "loai": "kenh_nha"}]
        mp.setattr(K, "doc_du_an", lambda ma: dict(da) if ma == "hapas" else None)
        mp.setattr(K, "nguon_dang_theo_doi", lambda ma: [dict(n) for n in nguon])
        mp.setattr(K, "da_tieu_thang", lambda ma: da_tieu)
        mp.setattr(K, "luot_dang_chay", lambda ma: dang_chay)
        mp.setattr(K, "mo_luot", lambda ma, kieu, **kw: (self.mo.append((kieu, kw)), 99)[1])
        mp.setattr(K, "ghi_bai", lambda ma, luot, kieu, rows: (
            self.bai.append((luot, kieu, [dict(r) for r in rows])), (len(rows), 0))[1])
        mp.setattr(K, "dong_luot", lambda luot, **kw: self.dong.append((luot, kw)))


def _ns(**kw):
    import argparse
    m = _bu_ig()
    return argparse.Namespace(**{"du_an": "hapas", "tai_khoan": None, "ngay": m.NGAY_MAC_DINH,
                                 "so_bai": m.BAI_MAC_DINH, "tran": m.TRAN_TOI_DA,
                                 "ap_dung": False, **kw})


def test_bu_ig_doc_futurizerush_theo_raw_that():
    m = _bu_ig()
    items = _mau("mau_ig_futurizerush_profile.json")["items"]
    (tk,) = m.doc_futurizerush(items).values()
    assert tk["ho_so"]["tai_khoan"] == "hapas.vn" and len(tk["bai"]) == len(items)
    for b, it in zip(tk["bai"], items):
        assert b["link"] == it["postUrl"] and (b["like"], b["binh_luan"]) == (it["likes"],
                                                                             it["comments"])
        assert b["ngay"] == datetime.datetime.fromisoformat(it["timestamp"].replace("Z", "+00:00"))
        assert b["hashtag"] == it["hashtags"]
    (d, _), *_ = T._dong_tu_tai_khoan("instagram", tk)
    assert T._khoa_bai("instagram", d["link"], {"id": d["_goc_id"]}) == \
        f"instagram:{items[0]['shortcode']}"
    assert m.ACTOR == "futurizerush~instagram-profile-posts-scraper"


def test_bu_ig_chay_thu_khong_goi_actor_khong_ghi(monkeypatch):
    m = _bu_ig()
    kho = _KhoBuIg(monkeypatch)
    monkeypatch.setattr(A, "_run_actor", lambda *a, **k: pytest.fail("chạy thử không gọi actor"))
    ra = []
    bay = datetime.datetime(2026, 10, 17, 20, 0, tzinfo=_VN)
    assert m.chay(_ns(), ra.append, bay) == 0
    van = "\n".join(ra)
    assert "CHẠY THỬ" in van and "@hapas.vn (#11)" in van and "kol.x" not in van
    assert "'usernames': ['hapas.vn'], 'maxPosts': 40, 'postsNewerThan': '2026-09-17'" in van
    assert "Trần maxTotalChargeUsd 0.10 USD; ước tính tối đa 0.0700 USD" in van
    assert kho.mo == [] and kho.bai == [] and kho.dong == []
    # Trần không vượt 0,10 dù gõ lớn hơn.
    ra.clear()
    m.chay(_ns(tran=5), ra.append, bay)
    assert "Trần maxTotalChargeUsd 0.10 USD" in "\n".join(ra)


def test_bu_ig_ap_dung_ghi_dung_duong_nguon_kenh_nha(monkeypatch, mo):
    m = _bu_ig()
    kho = _KhoBuIg(monkeypatch)
    monkeypatch.setenv("APIFY_TOKEN", "apify_api_gia")
    monkeypatch.setattr(m, "_NGHI_GIAY", 0)
    gui = []

    def run(actor, payload, limit, mem=None, deadline=None, min_charge=0, *, tran_usd=None,
            mot_phan=False, nen_tang=None):
        gui.append((actor, payload, limit, tran_usd, nen_tang))
        return _fz(), {"run_id": "rbu1", "status": "SUCCEEDED", "ma": "OK", "usd": 0.0}
    monkeypatch.setattr(A, "_run_actor", run)
    monkeypatch.setattr(A, "_chi_phi_cac_run", lambda ids: {"usd": 0.0385, "so_run": len(ids),
                                                            "chua_doc": 0, "con_song": []})
    ra = []
    assert m.chay(_ns(ap_dung=True), ra.append) == 0
    assert gui == [(m.ACTOR, gui[0][1], 40, 0.1, "instagram")]
    assert gui[0][1]["usernames"] == ["hapas.vn"] and gui[0][1]["maxPosts"] == 40
    (luot, kieu, rows), = kho.bai
    assert luot == 99 and kieu == "theo_doi" and kho.mo[0][0] == "theo_doi"
    assert kho.mo[0][1]["ma_viec"].startswith("bu-ig-")
    items = _fz()
    assert sorted(r["khoa"] for r in rows) == sorted(f"instagram:{x['shortcode']}" for x in items)
    assert all(r["nguon_id"] == 11 and r["ly_do_giu"] == "kenh_nha" for r in rows)
    assert {r["binh_luan"] for r in rows} == {x["comments"] for x in items}
    (luot_d, kw), = kho.dong
    assert luot_d == 99 and kw["chi_phi_usd"] == 0.0385 and kw["trang_thai"] == "xong"
    assert kw["bai_moi"] == len(items) and "bình luận" in kw["ghi_chu"]
    assert "Chi phí thật: 0.0385 USD" in "\n".join(ra)


@pytest.mark.parametrize("dang, da_tieu, cau", [
    ({"id": 7, "ma_viec": "t1"}, 0.0, "đang có lượt theo dõi t1"),
    (None, 4.95, "phần còn của tháng (0.05 USD) thấp hơn trần"),
])
def test_bu_ig_ap_dung_dung_khi_dang_chay_hoac_het_thang(monkeypatch, dang, da_tieu, cau):
    m = _bu_ig()
    kho = _KhoBuIg(monkeypatch, dang_chay=dang, da_tieu=da_tieu)
    monkeypatch.setenv("APIFY_TOKEN", "apify_api_gia")
    monkeypatch.setattr(A, "_run_actor", lambda *a, **k: pytest.fail("không được gọi actor"))
    ra = []
    assert m.chay(_ns(ap_dung=True), ra.append) == 2
    assert cau in "\n".join(ra) and kho.mo == []
