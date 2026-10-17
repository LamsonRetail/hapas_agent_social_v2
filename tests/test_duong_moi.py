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

import pytest

import apify_tool as A
import quet_lon as Q
import theo_doi as T
from dashboard import chi_phi as CP

_VN = datetime.timezone(datetime.timedelta(hours=7))
_GOC = pathlib.Path(__file__).resolve().parent


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
