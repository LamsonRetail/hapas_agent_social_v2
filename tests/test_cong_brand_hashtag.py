"""Cổng "phải nhắc brand" cho bài từ ĐƯỜNG HASHTAG (18/10/2026, `theo_doi.nhac_brand`).

Điều tra Kompa 18/10/2026: feed #quatang2010 kéo về 55/224 bài không gọi tên HAPAS (1.569 thảo luận)
mà AI vẫn được giữ. Bài CHỈ đến từ đường hashtag (feed challengePosts TikTok, Instagram hashtag, dự
phòng clockworks hashtag, mẫu hashtag của kiểm độ phủ) phải gọi tên brand ở nội dung / hashtag / tên
/ định danh chủ bài (hoặc tag feed), bỏ TRƯỚC AI, vào sổ "đã loại". Kho, AI giả."""
from __future__ import annotations

import contextvars
import copy
import datetime
import json
import re
import sys
import time
from pathlib import Path

import pytest
from test_loc_seeding import KhoGia, _tk
from test_theo_doi import GiaKho, _hit, mo  # noqa: F401 — `mo` là fixture

import apify_tool as A
import kiem_do_phu as KDP
import theo_doi as T
import theo_doi_api as TDA

_VN = datetime.timezone(datetime.timedelta(hours=7))
LY = T.LY_DO_HASHTAG_BRAND
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas", "quatang2010"],
         "tu_loai_tru": [], "boi_canh": "HAPAS — túi xách Việt Nam", "thi_truong": "VN",
         "cau_hinh": {}}
TEN = ["HAPAS", "hapas"]


# ───────────────────────────── luật thuần ─────────────────────────────
def test_cau_hinh_mac_dinh_bat_chi_false_la_tat_va_ten_them():
    assert T.cau_hinh_hashtag_brand(DU_AN) == {"bat": True, "ten": TEN}
    for x, bat in ((False, False), ({"bat": False}, False), ("false", True), (0, True),
                   ({"bat": "khong"}, True), (None, True), ({}, True)):
        c = T.cau_hinh_hashtag_brand({**DU_AN, "cau_hinh": {"hashtag_can_nhac_brand": x}})
        assert c["bat"] is bat, x
    c = T.cau_hinh_hashtag_brand({**DU_AN, "cau_hinh": {"hashtag_can_nhac_brand": {
        "ten": ["Mate Made", 3, "  ", "HAPAS"]}}})
    assert c == {"bat": True, "ten": ["HAPAS", "hapas", "Mate Made"]}
    assert T.cau_hinh_hashtag_brand({**DU_AN, "cau_hinh": "rác"})["bat"] is True


def test_nhac_brand_bo_dau_khong_phan_biet_hoa_thuong_va_tag_feed():
    assert T.nhac_brand({"text": "Túi HAPÁS mới về"}, TEN)
    assert T.nhac_brand({"hashtags": "quatang2010, quatanghapas"}, TEN), "hashtag dính tên brand"
    assert T.nhac_brand({"username": "hapas.official"}, TEN)
    assert T.nhac_brand({"kenh": "Hapas Việt Nam"}, TEN)
    qua = {"text": "Set quà 20/10 cho mẹ #quatang2010", "hashtags": "quatang2010",
           "username": "shop.qua", "kenh": "Shop Quà", "_tag_feed": "#quatang2010"}
    assert not T.nhac_brand(qua, TEN)
    assert T.nhac_brand({**qua, "_tag_feed": "#quatang2010 #quatanghapas"}, TEN), \
        "bài nằm trong feed #quatanghapas là bài gắn tag đó"
    assert not T.nhac_brand({"text": "lưới hapa nuôi cá"}, TEN)
    assert T.nhac_brand(qua, []), "không biết brand: không bỏ bừa"


def test_duong_hashtag_theo_nhan_input_url_va_du_phong_clockworks():
    assert TDA.duong_hashtag({"platform": "tiktok", "_tag_feed": "#quatang2010"}) == "#quatang2010"
    assert TDA.duong_hashtag({"platform": "tiktok", "_nguon": "TikTok API (scraptik)"}) == ""
    assert TDA.duong_hashtag({"platform": "tiktok", "_nguon": "clockworks (dự phòng)"}) == "#"

    def ig(u):
        return {"platform": "instagram", "__goc": {"inputUrl": u}}
    assert TDA.duong_hashtag(ig("https://www.instagram.com/explore/tags/QuaTang2010")) == \
        "#quatang2010"
    assert TDA.duong_hashtag(ig("https://www.instagram.com/explore/search/keyword/?q=hapas")) == ""
    assert TDA.tag_ig({"platform": "instagram"}) is None
    assert TDA.duong_hashtag({"platform": "facebook", "text": "#quatang2010"}) == ""
    # Hai bản của một bài: một bản từ đường từ khoá → không còn là bài chỉ-hashtag; hai bản cùng từ
    # hashtag → gộp tag.
    a = {"platform": "tiktok", "_tag_feed": "#quatang2010"}
    TDA.gop_duong(a, {"platform": "tiktok", "_nguon": "TikTok API (scraptik)"})
    b = {"platform": "tiktok", "_tag_feed": "#quatang2010"}
    TDA.gop_duong(b, {"platform": "tiktok", "_tag_feed": "#quatanghapas"})
    c = {"platform": "tiktok"}
    TDA.gop_duong(c, {"platform": "tiktok", "_tag_feed": "#x"})
    assert a["_tag_feed"] == "" and b["_tag_feed"] == "#quatang2010 #quatanghapas"
    assert "_tag_feed" not in c


# ───────────────────────────── pipeline lượt tìm ─────────────────────────────
@pytest.fixture
def ai(monkeypatch):
    goi: list[list[str]] = []

    def phan_xu(rows, *a, **k):
        goi.append([d["username"] for d, _ in rows])
        return {}, {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"}
    monkeypatch.setattr(A, "_phan_xu_ai", phan_xu)
    return goi


LUC = datetime.datetime.now(_VN) - datetime.timedelta(days=2)


def _bai(i, user, text, tag_feed=None, kenh=None):
    d = {"platform": "tiktok", "username": user, "kenh": kenh or user, "text": text,
         "hashtags": "quatang2010", "link": f"https://www.tiktok.com/@{user}/video/77{i}",
         "comments": 5, "views": 900, "likes": 1, "shares": 0, "__goc": {"id": f"77{i}"}}
    if tag_feed is not None:
        d["_tag_feed"] = tag_feed
    return d, LUC


def _so() -> dict:
    return TDA.doc_loai("hapas", TDA.dau_loai(DU_AN, DU_AN["tu_khoa"]),
                        LUC - datetime.timedelta(days=5))


def test_bai_chi_hashtag_khong_nhac_brand_bo_truoc_ai_vao_so_va_pheu(monkeypatch, ai):
    kho = KhoGia([{"id": 1, "nen_tang": "tiktok", "dinh_danh": "nha_mau", "loai": "kenh_nha"}])
    kho.cai(monkeypatch)
    hits = [_bai(1, "shop_qua", "Set quà 20/10 cho mẹ #quatang2010", "#quatang2010"),
            _bai(2, "khach_a", "Mua túi HAPAS tặng mẹ nhân 20/10", "#quatang2010"),
            _bai(3, "hapas.daily", "Quà 20/10 xinh xắn", "#quatang2010"),
            _bai(4, "shop_b", "Quà 20/10 cho mẹ #quatang2010"),             # đường từ khoá
            _bai(5, "nha_mau", "BST thu đông về rồi #quatang2010", "#quatang2010")]  # kênh nhà
    tk = _tk()
    T._tach_va_giu(DU_AN, 7, hits, DU_AN["tu_khoa"], 1e12, tk)
    f = tk["pheu"]["tiktok"]
    assert f["khong_brand"] == 1 and tk["khong_brand"] == 1
    assert ai == [["khach_a", "hapas.daily", "shop_b", "nha_mau"]], "bài bị cổng không tới AI"
    assert {k: v[0] for k, v in _so().items()} == {"tiktok:771": LY}
    assert "hashtag không nhắc brand 1" in T._cau_pheu("tiktok", f)
    assert "bỏ 1 bài đường hashtag không nhắc brand" in T._cau_tk({**tk, "tu": ["hapas"]})[0]
    # Gặp lại qua feed: "đã loại trước", không tới AI. Về qua đường TỪ KHOÁ: sổ không chặn (lý do
    # gắn với đường) — tới AI, kết quả không tuỳ đường nào thấy bài trước.
    tk2 = _tk()
    T._tach_va_giu(DU_AN, 8, [_bai(1, "shop_qua", "Set quà 20/10 cho mẹ #quatang2010",
                                   "#quatang2010")], DU_AN["tu_khoa"], 1e12, tk2)
    assert tk2["pheu"]["tiktok"]["da_loai_truoc"] == 1 and len(ai) == 1
    tk3 = _tk()
    T._tach_va_giu(DU_AN, 9, [_bai(1, "shop_qua", "Set quà 20/10 cho mẹ #quatang2010")],
                   DU_AN["tu_khoa"], 1e12, tk3)
    assert not tk3["pheu"]["tiktok"]["da_loai_truoc"] and ai[-1] == ["shop_qua"]


def test_tat_cong_thi_bai_hashtag_toi_ai_ke_ca_bai_da_loai_truoc(monkeypatch, ai):
    KhoGia().cai(monkeypatch)
    hits = [_bai(1, "shop_qua", "Set quà 20/10 cho mẹ #quatang2010", "#quatang2010")]
    T._tach_va_giu(DU_AN, 7, hits, DU_AN["tu_khoa"], 1e12, _tk())
    assert ai == [] and _so()
    tat = {**DU_AN, "cau_hinh": {"hashtag_can_nhac_brand": False}}
    tk = _tk()
    T._tach_va_giu(tat, 8, [_bai(1, "shop_qua", "Set quà 20/10 cho mẹ #quatang2010",
                                 "#quatang2010")], DU_AN["tu_khoa"], 1e12, tk)
    assert ai == [["shop_qua"]] and not tk["pheu"]["tiktok"]["khong_brand"]


def test_ban_trung_tu_duong_tu_khoa_khong_bi_cong(monkeypatch, ai):
    """Cùng một video về qua feed hashtag VÀ tìm theo từ khoá trong một lượt: không phải bài
    chỉ-hashtag — tới AI như bài tìm thấy (`tach_da_biet` gộp nhãn)."""
    KhoGia().cai(monkeypatch)
    tk = _tk()
    T._tach_va_giu(DU_AN, 7, [_bai(1, "shop_qua", "Quà 20/10 #quatang2010", "#quatang2010"),
                              _bai(1, "shop_qua", "Quà 20/10 #quatang2010")],
                   DU_AN["tu_khoa"], 1e12, tk)
    assert ai == [["shop_qua"]] and tk["pheu"]["tiktok"]["trung"] == 1


def _ig(sc, user, cap, tag="quatang2010"):
    luc = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1)
    it = {"id": f"ig{sc}", "shortCode": sc, "url": f"https://www.instagram.com/p/{sc}/",
          "timestamp": luc.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "caption": cap,
          "hashtags": re.findall(r"#(\w+)", cap), "ownerUsername": user, "ownerFullName": user,
          "likesCount": 3, "commentsCount": 2}
    if tag is not None:
        it["inputUrl"] = f"https://www.instagram.com/explore/tags/{tag}"
    return it


@pytest.mark.tiktok_api
@pytest.mark.usefixtures("mo")
def test_luot_tim_feed_tiktok_va_instagram_qua_cong_brand(monkeypatch):
    """Lượt /theodoi thật (`_tim_tu_khoa`): bài feed #quatang2010 TikTok và bài Instagram hashtag
    không gọi tên HAPAS bị bỏ trước AI; bài gọi tên giữ; Instagram thiếu `inputUrl` vẫn là đường
    hashtag."""
    import test_duong_moi as DM
    from test_theo_doi import DU_AN as DA0
    from test_theo_doi import GiaKhoTk, GiaViec, _tt_tim
    kho = GiaKhoTk(monkeypatch)
    feed = [DM._tt_clockworks("7000000000000000005", "shop.qua", "Set quà 20/10 cho mẹ"),
            DM._tt_clockworks("7000000000000000006", "kol.d", "Túi HAPAS làm quà 20/10")]
    for it in feed:
        it["hashtags"] = [{"name": "quatang2010"}]

    def lay_mau(trang_tag, trang_tg, cid, uid, ngan, d_from):
        fn = A._KHI_CO_RUN.get()
        for i in range(sum(trang_tag.values()) + sum(1 for t in trang_tag if not cid.get(t))):
            fn({"id": f"tag-{i}"}, {"actor": T.TT_ACTOR})
        return ([(it, "#quatang2010") for it in feed],
                {"tag": {t: {"cid": f"cid-{t}", "bai": len(feed), "loi": ""} for t in trang_tag}})
    monkeypatch.setattr(KDP, "lay_mau", lay_mau)

    def tim_tt(q, limit, country, d_from, d_to, **k):
        A._KHI_CO_RUN.get()({"id": "run-tt"}, {"actor": T.TT_ACTOR})
        return [_tt_tim("kol.a", "7000000000000000001", "túi hapas đẹp")]

    def tim_ig(q, limit, country, d_from, d_to, **k):
        return A._chuan_instagram([_ig("A1", "shop.qua.ig", "Quà 20/10 cho nàng #quatang2010"),
                                   _ig("A2", "kol.e", "Túi Hapas xinh #quatang2010"),
                                   _ig("A3", "shop.f", "Quà tặng 20/10 #quatang2010", tag=None)])
    monkeypatch.setattr(T, "_them_luot_moi", lambda v, ma, luot, q, got, *a, **k: (got, {}))
    monkeypatch.setattr(T, "_them_luot_noi", lambda v, ma, luot, q, got, *a, **k: (got, {}))
    monkeypatch.setattr(A, "_FETCH", {"tiktok": tim_tt, "instagram": tim_ig,
                             **{p: (lambda *a, **k: []) for p in ("facebook", "youtube")}})
    gui: list[str] = []
    monkeypatch.setattr(A, "_phan_xu_ai", lambda rows, *a, **k: (
        gui.extend(d["username"] for d, _ in rows),
        ({}, {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"}))[1])
    da = dict(DA0, tu_khoa=["hapas", "túi hapas", "quatang2010"], tk_bat=True, tk_so_bai=15)
    tk = contextvars.copy_context().run(T._tim_tu_khoa, GiaViec({}, []), da, 3, 5.0,
                                        time.monotonic() + 600)
    assert tk["pheu"]["tiktok"]["khong_brand"] == 1 and tk["pheu"]["instagram"]["khong_brand"] == 2
    assert sorted(gui) == ["kol.a", "kol.d", "kol.e"]
    assert {r["tai_khoan"] for _, rows in kho.bai for r in rows} == {"kol.a", "kol.d", "kol.e"}
    so = TDA.doc_loai("hapas", TDA.dau_loai(da, T.tu_tim(da)),
                      datetime.datetime.now(_VN) - datetime.timedelta(days=30))
    assert sorted(v[0] for v in so.values()) == [LY] * 3
    cau = T._cau_tk(tk)
    assert "bỏ 3 bài đường hashtag không nhắc brand" in cau[0]
    assert "hashtag không nhắc brand 2" in next(c for c in cau if c.startswith("phễu tìm Instagram"))


def test_luot_noi_tag_kiem_do_phu_mang_nhan_duong_hashtag(monkeypatch):
    """Lượt nổi đọc feed của tag kiểm độ phủ: bài feed mang `_tag_feed`, bài tìm từ khoá thì không."""
    from test_duong_moi import _tt_clockworks

    import tiktok_api as TT
    monkeypatch.setattr(TT, "dung_api", lambda ten: True)
    monkeypatch.setattr(TT, "tim", lambda *a, **k: [_tt_clockworks("1", "kol.a", "hapas")])
    monkeypatch.setattr(TT, "tim_cid", lambda t, ngan: f"cid-{t}")
    monkeypatch.setattr(TT, "bai_hashtag", lambda c, trang, ngan: [
        _tt_clockworks("2", "shop.qua", "quà 20/10")])
    ra = TDA.tim_noi_tiktok(["hapas"], datetime.datetime.now(_VN), 1.0, tag=["lammoidieuviyeu"])
    assert [(d["username"], d.get("_tag_feed"), d["_noi"]) for d, _ in ra] == [
        ("kol.a", None, True), ("shop.qua", "#lammoidieuviyeu", True)]


@pytest.mark.usefixtures("mo")
def test_luu_tu_khoa_social_listen_cung_qua_cong(monkeypatch):
    kho = GiaKho().cai(monkeypatch)
    ig = {"platform": "instagram", "kenh": "Shop Quà", "username": "shop.qua", "followers": 0,
          "views": 0, "likes": 1, "comments": 0, "shares": 0, "hashtags": "quatang2010",
          "text": "Quà 20/10 #quatang2010", "link": "https://www.instagram.com/p/Q1/",
          "_khop": True, "_sac_thai": None, "_chu_de": None,
          "__goc": {"id": "q1", "inputUrl": "https://www.instagram.com/explore/tags/quatang2010"}}
    ban = T._ban_sao_tu_khoa([(ig, datetime.datetime.now(_VN) - datetime.timedelta(days=1)),
                              _hit("tiktok", "me4con", 2)])
    assert ban[0][0]["_tag_feed"] == "#quatang2010" and ban[1][0]["_tag_feed"] == ""
    kq = T.luu_tu_khoa(["hapas"], ban)
    (_, luot, _, rows), = kho.bai
    assert kq["hapas"][0] == 1 and [r["tai_khoan"] for r in rows] == ["me4con"]
    assert "bỏ 1 bài đường hashtag không nhắc brand" in kho.luot[luot]["ghi_chu"]


# ───────────────────────────── script nạp raw ─────────────────────────────
def test_nap_raw_feed_hashtag_va_ig_hashtag_qua_cong_brand(monkeypatch, tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    import lang_nghe_nap_raw as N
    import test_lang_nghe_nap_raw as R
    monkeypatch.setattr(A, "_phan_xu_ai", lambda *a, **k: ({}, {"_sac_thai": {}, "_chu_de": {},
                                                                 "trang_thai": "đã chạy"}))
    R.KhoGia().cai(monkeypatch)
    goc = R._tao_raw(tmp_path / "raw")
    qua = copy.deepcopy(R._aw("review")[0])
    qua.update(aweme_id="7690000000000077777", desc="Set quà 20/10 cho mẹ #quatang2010",
               text_extra=[{"hashtag_name": "quatang2010"}])
    qua["author"] = {**qua["author"], "unique_id": "shop_qua_mau", "nickname": "Shop Quà"}
    live0 = R._aw("livestream")[0]               # cùng có ở tìm theo từ khoá: không bị cổng
    R._jsonl(goc / "kompa" / "raw_tt_tag_quatang2010.jsonl", [
        {"loai": "challengePosts", "tag": "quatang2010", "item": {"aweme_list": [qua, live0]}}])
    luc = (R.BAY_GIO - datetime.timedelta(days=2)).astimezone(datetime.timezone.utc)

    def ig(sc, user, cap, url):
        return {"id": sc, "shortCode": sc, "url": f"https://www.instagram.com/p/{sc}/",
                "timestamp": luc.strftime("%Y-%m-%dT%H:%M:%S.000Z"), "caption": cap,
                "hashtags": ["quatang2010"], "ownerUsername": user, "ownerFullName": user,
                "likesCount": 1, "commentsCount": 4, "inputUrl": url}
    for ten, inp, it in (
            ("raw_ig_tag.json", {"hashtags": ["quatang2010"]},
             ig("T1", "shop.ig", "Quà 20/10 #quatang2010",
                "https://www.instagram.com/explore/tags/quatang2010")),
            ("raw_ig_kw.json", {"hashtags": ["quà 20/10"], "keywordSearch": True},
             ig("K1", "shop.kw", "Quà 20/10 #quatang2010",
                "https://www.instagram.com/explore/search/keyword/?q=qua"))):
        (goc / "kompa" / ten).write_text(json.dumps(
            {"actor": "apify/instagram-hashtag-scraper", "input": inp, "items": [it]}),
            encoding="utf-8")
    tu = R.BAY_GIO - datetime.timedelta(days=40)
    raw = N.doc_raw([str(goc)], tu, R.BAY_GIO)
    nhan: dict = {}
    for d, _ in raw["tim"]:                      # nhãn của bản đọc ĐẦU mỗi tài khoản
        nhan.setdefault(d["username"], d.get("_tag_feed"))
    assert nhan["shop_qua_mau"] == "#quatang2010" and nhan["shop.ig"] == "#quatang2010"
    assert nhan["shop.kw"] == "" and nhan["review_mau"] == "#hapas"
    giu, _ = N.loc_khung(raw["tim"], tu, R.BAY_GIO)
    assert next(d for d, _ in giu if d["username"] == "live_mau" and d["link"].endswith(
        live0["aweme_id"]))["_tag_feed"] == "", "bản trùng có đường từ khoá"
    out: list[str] = []
    assert N.chay(N.tao_parser().parse_args(["hapas", str(goc), "--tu", tu.date().isoformat()]),
                  in_ra=out.append, bay_gio=R.BAY_GIO, nghi=lambda s: None) == 0
    s = "\n".join(out)
    tl = (1 + qua["statistics"]["comment_count"]) + (1 + 4)
    assert f"loại vì đường hashtag không nhắc brand 2 bài ({tl} thảo luận; tiktok 1; instagram 1)" \
        in s, s
    assert "bỏ 2 bài đường hashtag không nhắc brand" in s
    assert "hashtag không nhắc brand 1" in next(x for x in out if "phễu tìm Instagram" in x)


def test_mo_ta_schema_noi_cong_brand():
    """COMMENT `du_an.cau_hinh` + mô tả bảng bai (quy chuẩn BI: mô tả đúng dữ liệu) nói cổng brand."""
    sql = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "schema.sql").read_text(
        encoding="utf-8")
    m = re.search(r"COMMENT ON COLUMN du_an\.cau_hinh IS '([^']*)';", sql).group(1)
    assert '"hashtag_can_nhac_brand"' in m and LY in m
    assert "bài chỉ đến từ đường hashtag (feed hashtag TikTok, Instagram hashtag)" in sql
    bq = (Path(__file__).resolve().parents[1] / "deploy" / "lang-nghe" / "bigquery.sql").read_text(
        encoding="utf-8")
    assert bq.count("bài chỉ đến từ đường hashtag (feed hashtag TikTok, Instagram hashtag)") == 2
