"""Tách video TikTok AFFILIATE (gắn giỏ hàng TikTok Shop) và VIRAL (không gắn giỏ).

Backlog marketing: "Khi tìm kiếm theo từ khoá trên TikTok dễ bị lẫn video affiliate và
video viral → cần tách riêng: video affiliate luôn gắn giỏ hàng; video viral không gắn
giỏ." Trường thật là `hasTikTokShopProduct` (bool) của actor clockworks — run thật
02/10/2026 (từ khoá "hapas", 30 item): 6 true, 24 false. apidojo không công bố trường
này nên thiếu thì "chưa rõ", không được đoán thành viral.
Dữ liệu ở đây là GIẢ (kênh, link, số liệu bịa) — không gọi Apify, Lark hay model thật.
"""
from __future__ import annotations

import datetime
import json

import pytest

import apify_tool as A
from sheet_gia import LarkGia
import quet_lon
import sheet_lon

NOW = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(hours=1)
AFF, VIR = "Affiliate (gắn giỏ)", "Viral (không giỏ)"


def _clockworks(vid: str, text: str, gio="thieu", **kw) -> dict:
    """Item đúng shape dataset clockworks/tiktok-hashtag-scraper (giá trị giả)."""
    it = {"id": vid, "text": text, "textLanguage": "vi",
          "createTimeISO": NOW.astimezone(datetime.timezone.utc).strftime(
              "%Y-%m-%dT%H:%M:%S.000Z"),
          "authorMeta": {"name": f"kenh_{vid}", "nickName": f"Kênh {vid}", "fans": 1200},
          "playCount": 5000, "diggCount": 300, "commentCount": 12, "shareCount": 4,
          "collectCount": 9, "hashtags": [{"name": "hapas"}],
          "webVideoUrl": f"https://www.tiktok.com/@kenh_{vid}/video/{vid}",
          "isAd": False, "isSponsored": False, "isSlideshow": False}
    if gio != "thieu":
        it["hasTikTokShopProduct"] = gio
    it.update(kw)
    return it


# ───────────────────────────── bộ chuẩn hoá ─────────────────────────────

def test_chuan_hoa_clockworks_doc_co_gio_hang():
    raw = [_clockworks("1", "Túi Hapas đeo đi làm", True),
           _clockworks("2", "Outfit với túi Hapas", False),
           _clockworks("3", "Hapas unbox", "thieu")]
    rows = A._chuan_tiktok(A._chuan_clockworks(raw))
    assert [d["gio_hang"] for d, _ in rows] == [True, False, None]
    assert all(dt is not None for _, dt in rows)
    assert rows[0][0]["kenh"] == "Kênh 1" and rows[0][0]["followers"] == 1200


def test_apidojo_khong_bao_gio_thi_chua_ro_khong_doan():
    """apidojo không công bố trường giỏ hàng: thiếu (hoặc sai kiểu) -> None, KHÔNG là False."""
    apidojo = {"uploadedAtFormatted": NOW.isoformat(), "channel": {"name": "a"},
               "title": "Túi hapas", "postPage": "https://www.tiktok.com/@a/video/9"}
    assert A._chuan_tiktok([apidojo])[0][0]["gio_hang"] is None
    assert A._chuan_tiktok([{**apidojo, "hasTikTokShopProduct": "true"}])[0][0][
        "gio_hang"] is None, "chỉ tin bool thật"
    assert A._chuan_tiktok([{**apidojo, "hasTikTokShopProduct": True}])[0][0]["gio_hang"]


def test_viec_nen_xin_ca_truong_gio_hang():
    """Việc nền đọc dataset với `fields=`: thiếu tên trường ở đây là mất cờ IM LẶNG."""
    assert "hasTikTokShopProduct" in A._TRUONG_ACTOR[A._ACTORS["tiktok_fallback"]]
    assert "hasTikTokShopProduct" in A._TRUONG_ACTOR[A._ACTORS["tiktok"]]


def test_nhan_cot_va_cau_dem():
    tt = lambda g: {"platform": "tiktok", "gio_hang": g}           # noqa: E731
    assert [A._loai_video_tiktok(tt(g)) for g in (True, False, None)] == [AFF, VIR, ""]
    assert A._loai_video_tiktok({"platform": "threads", "gio_hang": True}) == "", \
        "không phải TikTok thì để trống"
    ds = [tt(True), tt(False), tt(False), tt(None), {"platform": "youtube"}]
    assert A._dem_loai_video(ds) == {"affiliate": 1, "viral": 2, "chua_ro_gio": 1}
    assert A._cau_loai_video_tiktok([{"platform": "youtube"}]) == ""
    assert "CHƯA tách được" in A._cau_loai_video_tiktok([tt(None), tt(None)])


# ───────────────────────────── _handle đầu-cuối ─────────────────────────────

RAW = [_clockworks("11", "Review túi Hapas mới mua, link giỏ hàng bên dưới", True),
       _clockworks("12", "Túi Hapas đi cafe cuối tuần xinh xỉu", False),
       _clockworks("13", "Hapas phối đồ đi làm", False),
       _clockworks("14", "Mở hộp túi Hapas", "thieu"),
       _clockworks("15", "Hapas guitars custom build", True)]       # dính `exclude`
THREADS = {"kenh": "Ngọc Trâm", "followers": 0, "views": 9, "likes": 0, "comments": 0,
           "shares": 0, "hashtags": "", "text": "Mới mua túi Hapas xinh xỉu luôn",
           "link": "https://www.threads.net/@x/post/1"}


@pytest.fixture
def quet(monkeypatch):
    monkeypatch.setenv("SOCIAL_AI_PHAN_XU", "0")
    du_lieu = {"raw": RAW}
    monkeypatch.setitem(A._FETCH, "tiktok",
                        lambda *a: A._chuan_tiktok(A._chuan_clockworks(du_lieu["raw"])))
    monkeypatch.setitem(A._FETCH, "threads", lambda *a: [(dict(THREADS), NOW)])
    monkeypatch.setattr(A, "_tran", lambda: (500, 1.0))
    gia = LarkGia(url="https://sheet")           # Lark giả (tests/sheet_gia.py)
    monkeypatch.setattr(A.lark, "call", gia.call)
    ghi = gia.ghi_cu({A.TAB_BAI_DANG: "s1", "Dữ liệu": "s1", A._TAB_BI_LOAI: "s2",
                      A._TAB_THI_TRUONG_KHAC: "s3"})
    monkeypatch.setattr(A, "_grant", lambda tok, oid: True)
    monkeypatch.setattr(A.memory_store, "get_current_sender", lambda: "ou_test")
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: None)
    monkeypatch.setattr(A.chi_phi_tool, "ghi", lambda **k: {})
    monkeypatch.setattr(A, "_hoi_model", lambda *a: pytest.fail("AI tắt, không gọi model"))

    def chay(raw=None, **them):
        if raw is not None:
            du_lieu["raw"] = raw
        args = {"queries": ["hapas"], "platforms": ["tiktok", "threads"],
                "date_from": f"{NOW - datetime.timedelta(days=2):%Y-%m-%d}",
                "date_to": f"{NOW + datetime.timedelta(hours=1):%Y-%m-%d}",
                "exclude": ["guitars"], **them}
        return json.loads(A._handle(args))
    return chay, ghi


def _bang(ghi, sid):
    return next(rows for s, rows in ghi if s == sid)


def test_cot_cuoi_va_dem_theo_gio_hang(quet):
    chay, ghi = quet
    kq = chay()
    chinh, loai = _bang(ghi, "s1"), _bang(ghi, "s2")
    for bang in (chinh, loai):
        assert bang[0][:12] == A._HEADER, "12 cột đầu giữ nguyên"
        assert bang[0][-1] == A._COT_LOAI_VIDEO
        assert {len(r) for r in bang} == {len(bang[0])}, "tiêu đề và dòng cùng số cột"
    assert chinh[0][-5:] == ["Thị trường", "Nhận định AI", "Sắc thái", "Nguồn",
                             A._COT_LOAI_VIDEO], "cột loại video sau cột Sắc thái/Nguồn"
    assert loai[0][-2:] == ["Lý do loại", A._COT_LOAI_VIDEO]
    theo_kenh = {r[2]: r[-1] for r in chinh[1:]}
    assert theo_kenh == {"Kênh 11": AFF, "Kênh 12": VIR, "Kênh 13": VIR, "Kênh 14": "",
                         "Ngọc Trâm": ""}, "chưa rõ và bài Threads để trống"
    assert [(r[2], r[-1]) for r in loai[1:]] == [("Kênh 15", AFF)], \
        "bài bị loại vẫn ghi loại video để kiểm"
    tt = kq["per_platform"]["tiktok"]
    assert (tt["affiliate"], tt["viral"], tt["chua_ro_gio"]) == (1, 2, 1), \
        "chỉ đếm bài GIỮ, không đếm bài bị loại"
    assert "affiliate" not in kq["per_platform"]["threads"]
    cau = kq["cau_loai_video_tiktok"]
    assert cau == ("TikTok: 4 bài trong sheet — 1 video affiliate (có gắn giỏ hàng TikTok "
                   "Shop), 2 video viral (không gắn giỏ), 1 bài chưa rõ (nguồn không báo giỏ "
                   "hàng); lọc theo cột 'Loại video TikTok'.")
    assert cau in kq["note"], "câu nằm cả trong note để model không bỏ sót"


def test_nguon_khong_bao_gio_thi_noi_chua_tach_duoc(quet):
    chay, ghi = quet
    kq = chay(raw=[_clockworks("21", "Túi Hapas mới", "thieu"),
                   _clockworks("22", "Hapas đi chơi", "thieu")])
    assert [r[-1] for r in _bang(ghi, "s1")[1:]] == ["", "", ""]
    tt = kq["per_platform"]["tiktok"]
    assert (tt["affiliate"], tt["viral"], tt["chua_ro_gio"]) == (0, 0, 2)
    assert "CHƯA tách được" in kq["cau_loai_video_tiktok"]
    assert "viral (không gắn giỏ)" not in kq["cau_loai_video_tiktok"], "không đoán là viral"


def test_khong_quet_tiktok_thi_khong_co_cau(quet):
    chay, ghi = quet
    kq = chay(platforms=["threads"])
    assert kq["cau_loai_video_tiktok"] is None
    assert _bang(ghi, "s1")[0][-1] == A._COT_LOAI_VIDEO, "cột vẫn có, cùng bố cục mọi sheet"


def test_schema_giai_thich_affiliate_la_gan_gio():
    mo_ta = A.SCHEMA["description"]
    assert "cau_loai_video_tiktok" in mo_ta and "GẮN GIỎ HÀNG TikTok Shop" in mo_ta
    assert "chua_ro_gio" in mo_ta


# ───────────────────────────── quét nền ─────────────────────────────

def test_quet_nen_cung_cot_va_cau(monkeypatch):
    tabs: dict[str, list] = {}

    class SoGia:
        def __init__(self, v):
            self.s = {"url": "https://sheet", "tabs": {}}

        def dam_bao(self, *a, **k):
            pass

        def bat_dau_giai_doan(self, *a):
            pass

        def ghi_tab(self, ten, bang, tu_dau=False, cot=None, mo_ta=""):
            tabs[ten] = bang
            return len(bang)

        def kiem_ghi(self, bo_qua=()):
            return {"day_du": None, "cau": "chưa kiểm (giả)", "tabs": []}

        def ghi_tong_quan(self, ten, tq, kiem=None, bo_qua=()):
            import trinh_bay_sheet as T
            tabs[ten] = T.dung_tong_quan(tq, [], [], kiem)[0]

        def sap_tab(self, thu_tu):
            pass
    monkeypatch.setattr(sheet_lon, "SoSheet", SoGia)

    class V:
        ma = "Q9"
        d = {"nen_tang": {"tiktok": {}}, "nguoi_yeu_cau": "", "ngan_sach_usd": 1.0}

    def bai(kenh, gio):
        return ({"platform": "tiktok", "kenh": kenh, "views": 1, "text": "hapas",
                 "link": f"https://x/{kenh}", "_thi_truong": "VN", "gio_hang": gio,
                 "_nhan_dinh": "brand", "_phan_xu": "AI"}, NOW)
    ts = {"queries": ["hapas"], "date_from": "2026-09-18", "date_to": "2026-10-02",
          "country": "VN"}
    ket = {"hits": [bai("a", True), bai("b", False), bai("c", None)],
           "bi_loai": [(bai("d", True)[0], NOW, "chứa từ loại trừ 'x'")],
           "per": {"tiktok": {"scraped": 4, "trung_lap": 0, "trong_khoang": 4, "giu": 3,
                              "loai": 1}},
           "phan_xu": {}}
    quet_lon._ghi_cuoi(V(), ts, ket, {"usd": 0.1, "so_run": 1}, "xong")
    for ten in ("TikTok", quet_lon._TAB_LOAI):
        bang = tabs[ten]
        assert bang[0][-1] == A._COT_LOAI_VIDEO and {len(r) for r in bang} == {len(bang[0])}
    assert [r[-1] for r in tabs["TikTok"][1:]] == [AFF, VIR, ""]
    assert tabs[quet_lon._TAB_LOAI][1][-2:] == ["AI", AFF]
    cau = ("TikTok: 3 bài trong các tab — 1 video affiliate (có gắn giỏ hàng TikTok Shop), "
           "1 video viral (không gắn giỏ), 1 bài chưa rõ (nguồn không báo giỏ hàng); lọc "
           "theo cột 'Loại video TikTok'.")
    assert [A._COT_LOAI_VIDEO, cau] in [r[:2] for r in tabs[quet_lon._TAB_TONG]]
    tin = quet_lon._tin_nhan(V(), ts, ket, {"usd": 0.1, "so_run": 1}, "https://sheet",
                             "xong", [])
    assert cau in tin
