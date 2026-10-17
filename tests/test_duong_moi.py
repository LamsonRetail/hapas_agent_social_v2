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
import quet_lon as Q
import theo_doi as T
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
