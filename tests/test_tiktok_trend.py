"""Canh chế độ `trend` của social_listen (tiktok_trend.py).

Lỗi thật 25/09/2026: "quét trend TikTok, đủ 800 bài" bằng hashtag chung chung ra một mẫu
ngẫu nhiên — chỉ 95/800 video vừa mới vừa tiếng Việt, không âm thanh nào được dùng quá
một lần, video top đầu là kênh nước ngoài. Dữ liệu giả dưới đây giữ đúng hình dữ liệu
thật của hai actor.
"""
from __future__ import annotations

import datetime
import json

import pytest

import apify_tool as A
import tiktok_trend as T

GIO = datetime.datetime.now(datetime.timezone.utc)


def _iso(ngay_truoc: float) -> str:
    return (GIO - datetime.timedelta(days=ngay_truoc)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _vid(kenh, am, ngay=1, lang="vi", ad=False, tag="samdealruocden", hieu_ung=None, view=1000):
    return {"authorMeta": {"name": kenh}, "createTimeISO": _iso(ngay), "textLanguage": lang,
            "isAd": ad, "input": tag, "playCount": view,
            "musicMeta": {"musicId": am, "musicName": f"nhạc {am}", "musicAuthor": "tg"},
            "effectStickers": [{"name": hieu_ung}] if hieu_ung else []}


HASHTAG = [
    {"Rank": 1, "Hashtag": "#samdealruocden", "Trend Direction": "up", "Posts": 21209,
     "Video Views": 13703711, "Industries": [], "TikTok URL": "https://t/tag/1"},
    {"Rank": 2, "Hashtag": "#ob55", "Trend Direction": "down", "Posts": 4131,
     "Video Views": 75781065, "Industries": [], "TikTok URL": "https://t/tag/2"},
    {"Rank": 3, "Hashtag": "#2425luongve", "Trend Direction": "up", "Posts": 33174,
     "Video Views": 26940666, "Industries": ["News & Entertainment"], "TikTok URL": "https://t/tag/3"},
]
VIDEO = [{"Video Rank": 1, "Views": 20223601, "Author Handle": "@kenh", "Title": "tiêu đề",
          "Content Tags": ["Food & Beverage"], "Video TikTok URL": "https://t/v/1",
          "Metrics": [{"metric": "Views", "value": 20223601},
                      {"metric": "Organic Views", "value": 338825}]}]
MAU = [
    _vid("a", "m1", hieu_ung="kikay", view=500), _vid("b", "m1", hieu_ung="kikay", view=700),
    _vid("c", "m1"),                                   # m1: 3 kênh → tín hiệu
    _vid("a", "m2"), _vid("a", "m2"),                  # m2: 1 kênh đăng 2 lần → KHÔNG
    _vid("d", "m3", ngay=40), _vid("e", "m3", ngay=60),  # cũ → bị loại
    _vid("f", "m4", lang="en"), _vid("g", "m4", lang="en"),  # nước ngoài → bị loại
    _vid("h", "m5", ad=True), _vid("i", "m5", ad=True),      # quảng cáo → bị loại
    _vid("j", "m6", lang="un"), _vid("k", "m6", lang="un"),  # caption không lời → giữ
]


@pytest.fixture
def gia(monkeypatch):
    goi = []

    def call(actor, payload, limit, mem=None):
        goi.append((actor, payload))
        if actor == T.ACTOR_TREND:
            return HASHTAG if payload["trendType"] == "hashtags" else VIDEO
        return MAU

    monkeypatch.setattr(A, "_call", call)
    monkeypatch.setattr(A, "_tran", lambda: (800, 2.4))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 0.41, "so_run": 3, "cham_tran": 0, "dang_chay": 0})
    monkeypatch.setattr(T.chi_phi_tool, "ghi", lambda **k: {})
    dong = []
    monkeypatch.setattr(A, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(A, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(A, "_write_values", lambda tok, sid, rows: dong.extend(rows))
    monkeypatch.setattr(T.memory_store, "get_current_sender", lambda: None)
    return goi, dong


def test_handle_chuyen_sang_che_do_trend_khong_can_tu_khoa(gia):
    kq = json.loads(A._handle({"che_do": "trend"}))
    assert kq["che_do"] == "trend" and kq["vung"] == "VN" and kq["success"] is True


def test_chi_dem_am_thanh_nhieu_kenh_dung_lai(gia):
    kq = json.loads(T.chay({}))
    ten = [a["ten"] for a in kq["am_thanh"]]
    assert ten == ["nhạc m1", "nhạc m6"], "m2 chỉ một kênh; m3 cũ; m4 nước ngoài; m5 quảng cáo"
    m1 = kq["am_thanh"][0]
    assert m1["so_kenh"] == 3 and m1["so_video"] == 3 and m1["tong_view"] == 2200
    assert kq["hieu_ung"] == [{"ten": "kikay", "so_kenh": 2, "so_video": 2,
                              "di_kem_hashtag": "samdealruocden"}]
    assert kq["mau_am_thanh"]["da_cao"] == len(MAU)
    assert kq["mau_am_thanh"]["giu_lai_trong_ky_dung_ngon_ngu"] == 7, "13 - 2 cũ - 2 nước ngoài - 2 quảng cáo"


def test_lay_mau_duoi_hashtag_dang_len(gia):
    goi, _ = gia
    T.chay({})
    mau = [p for a, p in goi if a == A._ACTORS["tiktok_fallback"]]
    assert mau and mau[0]["hashtags"] == ["samdealruocden", "2425luongve", "ob55"], (
        "hashtag đang LÊN đứng trước; #ob55 đang xuống chỉ để bù cho đủ mẫu")


def test_so_video_mau_bi_kep_theo_tran_bai(gia):
    goi, _ = gia
    T.chay({"so_video_mau": 5000})
    mau = [p for a, p in goi if a == A._ACTORS["tiktok_fallback"]][0]
    assert mau["resultsPerPage"] == 800 // 3, "trần 800 bài chia cho 3 hashtag có được"


def _tag(ten, huong="lên"):
    return {"hang": 0, "hashtag": ten, "huong": huong, "so_bai": 0, "luot_xem": 0,
            "nganh": "", "link": ""}


def test_mau_lon_thi_soi_nhieu_hashtag():
    """TikTok chỉ trả ~40 video/hashtag: 800 bài mà soi 5 hashtag thì chỉ được ~200."""
    tags = [_tag(f"t{i}") for i in range(30)]
    assert len(T._chon_hashtag_soi(tags, 800)) == 20
    assert len(T._chon_hashtag_soi(tags, 100)) == 5, "mẫu nhỏ vẫn soi tối thiểu 5"
    assert len(T._chon_hashtag_soi(tags, 5000)) == 25, "không soi quá 25 hashtag"


def test_bo_hashtag_chien_dich_brand_khoi_mau():
    tags = [_tag("larocheposaysuperbrandday"), _tag("hợptáccùnglarocheposay"),
            _tag("hoptaccungabc"), _tag("trungthu2026"), _tag("ob55", "xuống")]
    assert T._chon_hashtag_soi(tags, 100) == ["trungthu2026", "ob55"]


def test_mau_lon_thi_lay_bang_hashtag_dai_hon(gia):
    goi, _ = gia
    kq = json.loads(T.chay({"so_hashtag": 20, "so_video_mau": 800}))
    tag = [p for a, p in goi if a == T.ACTOR_TREND and p["trendType"] == "hashtags"][0]
    assert tag["maxItems"] == 50, "800 bài cần 20 hashtag để soi → lấy 2×20+10 dòng"
    assert len(kq["hashtag"]) <= 20, "vẫn chỉ báo đúng số hashtag người dùng xin"


def test_mac_dinh_bo_video_quang_cao(gia):
    goi, _ = gia
    T.chay({})
    vid = [p for a, p in goi if a == T.ACTOR_TREND and p["trendType"] == "videos"][0]
    assert vid["videoOrganicOnly"] is True and vid["videoCountry"] == "VN"


def test_vung_khong_co_top_video_thi_chi_lay_hashtag(gia):
    goi, _ = gia
    kq = json.loads(T.chay({"country": "FR"}))
    assert kq["video"] == []
    assert not [p for a, p in goi if a == T.ACTOR_TREND and p["trendType"] == "videos"]


def test_vung_la_thi_bao_ro(gia):
    assert "chưa có trend" in T.chay({"country": "ZZ"})


def test_sheet_co_du_bon_loai_dong(gia):
    _, dong = gia
    kq = json.loads(T.chay({}))
    loai = {r[0] for r in dong[1:]}
    assert loai == {"Hashtag", "Video", "Âm thanh (suy từ mẫu)", "Hiệu ứng (suy từ mẫu)"}
    assert kq["sheet_url"] == "https://sheet"


def test_lay_du_thi_khong_bao_cham_tran(gia, monkeypatch):
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 2.4, "so_run": 3, "cham_tran": 1, "dang_chay": 0})
    # Bảng trả ĐỦ số hỏi (5 hashtag, 5 video) và mẫu cào đủ 20 → không gì bị cắt, dù
    # tiền tiêu sát trần.
    monkeypatch.setattr(T, "_bang_hashtag", lambda vung, ky, n: [
        {"hang": i, "hashtag": f"t{i}", "huong": "lên", "so_bai": 0, "luot_xem": 0,
         "nganh": "", "link": ""} for i in range(n)])
    monkeypatch.setattr(T, "_bang_video", lambda *a: [
        {"hang": i, "luot_xem": 0, "luot_xem_tu_nhien": 0, "kenh": "", "followers": 0,
         "tieu_de": "", "chu_de": "", "link": ""} for i in range(5)])
    monkeypatch.setattr(T, "_mau_am_thanh", lambda *a: {
        "cao": 20, "giu": 20, "am_thanh": [], "hieu_ung": [], "cao_du": True})
    kq = json.loads(T.chay({"so_hashtag": 5, "so_video": 5, "so_video_mau": 20}))
    assert kq["cham_tran_chi_phi"] is False


def test_thieu_mau_va_tieu_sat_tran_thi_van_bao(gia, monkeypatch):
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 2.4, "so_run": 3, "cham_tran": 1, "dang_chay": 0})
    kq = json.loads(T.chay({"so_video_mau": 800}))     # mẫu giả chỉ có 13 video
    assert kq["cham_tran_chi_phi"] is True


def test_bang_trend_hong_thi_bao_loi_ro(monkeypatch, gia):
    def hong(*a, **k):
        raise RuntimeError("HTTP 500")
    monkeypatch.setattr(A, "_call", hong)
    assert "Không lấy được bảng trend" in T.chay({})
