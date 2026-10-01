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
NHAC = [{"rank": i + 1, "title": f"bài {i}", "author": "ca sĩ", "rank_diff": 3,
         "link": f"https://t/music/{i}"} for i in range(12)]
MAU = [
    _vid("a", "m1", hieu_ung="kikay", view=500), _vid("b", "m1", hieu_ung="kikay", view=700),
    _vid("c", "m1"),                                   # m1: 3 kênh → tín hiệu
    _vid("a", "m2"), _vid("a", "m2"),                  # m2: 1 kênh đăng 2 lần → KHÔNG
    _vid("d", "m3", ngay=40), _vid("e", "m3", ngay=60),  # cũ → bị loại
    _vid("f", "m4", lang="en"), _vid("g", "m4", lang="en"),  # nước ngoài → bị loại
    _vid("h", "m5", ad=True), _vid("i", "m5", ad=True),      # quảng cáo → bị loại
    _vid("j", "m6", lang="un"), _vid("k", "m6", lang="un"),  # caption không lời → giữ
]


class _Goi(list):
    gioi_han: list


@pytest.fixture
def gia(monkeypatch):
    goi = _Goi()

    def call(actor, payload, limit, mem=None, **kw):
        goi.append((actor, payload))
        gioi_han.append((actor, limit))
        if actor == T.ACTOR_TREND:
            return HASHTAG if payload["trendType"] == "hashtags" else VIDEO
        if actor == T.ACTOR_NHAC:
            return NHAC[:payload["maxResults"]]
        return MAU

    gioi_han = []
    goi.gioi_han = gioi_han

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
    """Mẫu xin dư 2,5 lần nhưng vẫn gọn trong trần bài (800) VÀ trần USD mỗi lượt (2,4)."""
    goi, _ = gia
    T.chay({"so_video_mau": 5000})
    mau = [p for a, p in goi if a == A._ACTORS["tiktok_fallback"]][0]
    xin = [n for a, n in goi.gioi_han if a == A._ACTORS["tiktok_fallback"]][0]
    assert xin == int(0.9 * 2.4 / 0.003) == 720, "trần USD chặn trước trần 800 bài"
    assert mau["resultsPerPage"] * 3 >= xin, "chia đều cho 3 hashtag có được"


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
    assert loai == {"Hashtag", "Video", "Nhạc dùng lại (suy từ mẫu)", "Hiệu ứng (suy từ mẫu)",
                    "Nhạc đang lên (bảng Creative Center)"}
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
    monkeypatch.setattr(T, "_bang_nhac", lambda vung, ky, n: [
        {"hang": i, "ten": "", "tac_gia": "", "thay_doi_hang": "", "moi_vao_bang": False,
         "link": ""} for i in range(n)])
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


# ───────────────────────── đợt 3 (01/10/2026) ─────────────────────────
def _goi_actor(goi, actor):
    return [p for a, p in goi if a == actor]


def test_bang_nhac_creative_center_la_nguon_thu_ba(gia):
    goi, _ = gia
    kq = json.loads(T.chay({}))
    p = _goi_actor(goi, T.ACTOR_NHAC)[0]
    assert p["country_code"] == "VN" and p["rank_type"] == "surging" and p["maxResults"] == 10
    assert [n["ten"] for n in kq["nhac"]][:2] == ["bài 0", "bài 1"] and len(kq["nhac"]) == 10
    assert kq["nhac_trong_vn"] is False


def test_vn_rong_thi_noi_thang_khong_lay_nuoc_khac(gia, monkeypatch):
    """Actor trả dòng của nước khác (hoặc rỗng) cho VN → không bao giờ trình bày là của VN."""
    monkeypatch.setitem(globals(), "NHAC", [{"title": "US hit", "country_code": "US"}])
    kq = json.loads(T.chay({}))
    assert kq["nhac"] == [] and kq["nhac_trong_vn"] is True
    assert "Creative Center không trả bảng nhạc cho VN" in kq["ghi_chu_nhac"]
    assert "Creative Center không trả bảng nhạc cho VN" in kq["note"]


def test_so_nhac_bi_kep_theo_tran_usd(gia, monkeypatch):
    goi, _ = gia
    monkeypatch.setattr(A, "_tran", lambda: (800, 0.1))
    T.chay({"so_nhac": 50})
    assert _goi_actor(goi, T.ACTOR_NHAC)[0]["maxResults"] == int((0.09 - 0.02) / 0.02) == 3


def test_so_nhac_0_thi_khong_goi_va_uoc_tinh_co_tinh_nhac(gia):
    goi, _ = gia
    khong = json.loads(T.chay({"so_nhac": 0}))
    assert not _goi_actor(goi, T.ACTOR_NHAC)
    co = json.loads(T.chay({"so_nhac": 5}))
    assert co["uoc_tinh_chi_phi_usd"] - khong["uoc_tinh_chi_phi_usd"] == pytest.approx(0.12)


def test_tach_nhac_dung_lai_va_am_thanh_goc(gia, monkeypatch):
    mau = [dict(v, musicMeta=dict(v["musicMeta"])) for v in MAU]
    for v in mau:
        if v["musicMeta"]["musicId"] == "m6":
            v["musicMeta"]["musicOriginal"] = True
    # Thiếu trường musicOriginal: nhận ra âm gốc theo tên "original sound - …".
    mau += [_vid("x", "m7"), _vid("y", "m7")]
    for v in mau[-2:]:
        v["musicMeta"] = {"musicId": "m7", "musicName": "original sound - x"}
    monkeypatch.setitem(globals(), "MAU", mau)
    kq = json.loads(T.chay({}))
    assert [a["ten"] for a in kq["nhac_dung_lai"]] == ["nhạc m1"]
    assert {a["ten"] for a in kq["am_thanh_goc"]} == {"nhạc m6", "original sound - x"}
    assert {a["loai"] for a in kq["am_thanh"]} == {"Nhạc (bài hát) dùng lại", "Âm thanh gốc"}


def test_hashtag_nhay_cam_bi_gan_co_va_khong_dem_lay_mau(gia, monkeypatch):
    """01/10: Mark gợi ý móc nội dung vào #traibuonnguoi chỉ vì nó đang lên bảng."""
    goi, _ = gia
    monkeypatch.setitem(globals(), "HASHTAG", HASHTAG + [
        {"Rank": 4, "Hashtag": "#traibuonnguoi", "Trend Direction": "up", "Posts": 1,
         "Video Views": 1, "Industries": [], "TikTok URL": "https://t/tag/4"}])
    kq = json.loads(T.chay({}))
    the = [t for t in kq["hashtag"] if t["hashtag"] == "traibuonnguoi"][0]
    assert "không nên bám trend" in the["nhay_cam"] and "buôn người" in the["nhay_cam"]
    assert kq["hashtag_nhay_cam"] and "KHÔNG đề xuất" in kq["note"]
    assert "traibuonnguoi" not in _goi_actor(goi, A._ACTORS["tiktok_fallback"])[0]["hashtags"]
    assert T._nhay_cam("quàđôi") == "" and T._nhay_cam("tainangiaothong") != ""


def test_mau_thieu_thi_cao_them_duoi_hashtag_chua_soi(gia, monkeypatch):
    """01/10: xin 100 → cào 40, giữ 21. Nay xin dư, thiếu thì cào thêm một lượt."""
    goi, _ = gia
    monkeypatch.setattr(T, "_bang_hashtag", lambda vung, ky, n: [
        {"hang": i, "hashtag": f"t{i}", "huong": "lên", "so_bai": 0, "luot_xem": 0,
         "nganh": "", "link": ""} for i in range(12)])
    luot = []

    def call(actor, payload, limit, mem=None, **kw):
        goi.append((actor, payload))
        if actor != A._ACTORS["tiktok_fallback"]:
            return [] if actor == T.ACTOR_NHAC else VIDEO
        luot.append((payload["hashtags"], limit))
        if len(luot) == 1:   # 10 video, 5 cũ
            return [dict(_vid(f"k{i}", f"a{i}", ngay=1 if i < 5 else 40), id=f"v{i}")
                    for i in range(10)]
        return [dict(_vid(f"k{i}", f"a{i}"), id=f"w{i}") for i in range(20)]
    monkeypatch.setattr(A, "_call", call)
    kq = json.loads(T.chay({"so_video_mau": 100}))
    assert luot[0][1] == 250, "xin dư 2,5 lần"
    assert len(luot) == 2 and not set(luot[0][0]) & set(luot[1][0]), "lượt 2 soi hashtag mới"
    m = kq["mau_am_thanh"]
    assert m["so_luot_cao"] == 2 and m["da_cao"] == 30 and m["giu_lai_trong_ky_dung_ngon_ngu"] == 25


# ───────────────────────── rà độc lập 01/10/2026 ─────────────────────────
@pytest.mark.parametrize("tag", [
    "crochet", "crochetbag", "#CrochetBag", "tainan", "tainanhopdong", "tainan2026",
    "quàđôi", "thientai", "thiêntài", "baucua", "batmanmanga", "chếtcười", "đẹpchếtmất",
    "giếtthờigian", "machete", "ricochet", "trungthu2026", "samdealruocden"])
def test_nhay_cam_khong_bao_nham(tag):
    """Gốc ngắn trên chữ bỏ dấu từng gắn cờ #crochetbag (túi móc len — đúng ngành!) là
    'chết chóc' và #tainan (Đài Nam) là 'tai nạn'."""
    assert T._nhay_cam(tag) == "", tag


@pytest.mark.parametrize("tag, nhan", [
    ("traibuonnguoi", "buôn người"), ("tainangiaothong", "tai nạn / thiên tai"),
    ("vutainan", "tai nạn / thiên tai"), ("tainạn", "tai nạn / thiên tai"),
    ("thiêntai", "tai nạn / thiên tai"), ("chetchoc", "chết chóc"),
    ("quađời", "chết chóc"), ("gietnguoi", "chết chóc"), ("bầucử", "chính trị"),
    ("baucu2026", "chính trị"), ("khungbo", "bạo lực"), ("bocphot", "scandal")])
def test_nhay_cam_van_bat_dung(tag, nhan):
    assert T._nhay_cam(tag) == nhan


def _hai_luot(monkeypatch, goi, raw1: int, giu1: int):
    """Lượt 1 trả `raw1` video, chỉ `giu1` video trong kỳ; lượt 2 trả 20 video mới."""
    monkeypatch.setattr(T, "_bang_hashtag", lambda vung, ky, n: [
        {"hang": i, "hashtag": f"t{i}", "huong": "lên", "so_bai": 0, "luot_xem": 0,
         "nganh": "", "link": ""} for i in range(40)])
    luot = []

    def call(actor, payload, limit, mem=None, tran_usd=None, **kw):
        goi.append((actor, payload))
        if actor != A._ACTORS["tiktok_fallback"]:
            return [] if actor == T.ACTOR_NHAC else VIDEO
        luot.append({"limit": limit, "tran_usd": tran_usd})
        if len(luot) == 1:
            return [dict(_vid(f"k{i}", f"a{i}", ngay=1 if i < giu1 else 40), id=f"v{i}")
                    for i in range(raw1)]
        return [dict(_vid(f"k{i}", f"a{i}"), id=f"w{i}") for i in range(20)]
    monkeypatch.setattr(A, "_call", call)
    return luot


def test_luot_hai_chi_dung_phan_con_lai_cua_tran(gia, monkeypatch):
    """Rà 01/10: lượt hai từng được xin lại CẢ trần mỗi lượt → tiêu gần gấp đôi."""
    goi, _ = gia
    luot = _hai_luot(monkeypatch, goi, raw1=500, giu1=10)
    json.loads(T.chay({"so_video_mau": 200}))
    suc = int(0.9 * 2.4 / 0.003)                   # 720 video mỗi lượt
    assert luot[0]["limit"] == 500 and luot[0]["tran_usd"] is None
    assert len(luot) == 2 and luot[1]["limit"] == suc - 500, "chỉ phần còn lại của trần"
    assert luot[1]["tran_usd"] == pytest.approx(2.4 - 500 * 0.003)
    tong = (500 + luot[1]["limit"]) * 0.003
    assert tong <= 0.9 * 2.4 + 1e-9, "hai lượt cộng lại vẫn trong một trần"


def test_luot_dau_an_gan_het_tran_thi_khong_cao_them(gia, monkeypatch):
    goi, _ = gia
    luot = _hai_luot(monkeypatch, goi, raw1=710, giu1=10)
    kq = json.loads(T.chay({"so_video_mau": 300}))
    assert len(luot) == 1, "còn 10 video trong trần — không đáng một lượt"
    assert kq["mau_am_thanh"]["so_luot_cao"] == 1


def test_uoc_tinh_truoc_tinh_ca_luot_hai_te_nhat(gia):
    kq = json.loads(T.chay({"so_nhac": 0, "so_video": 5, "so_hashtag": 5}))
    # so_video_mau mặc định 100: lượt 1 xin 250, lượt 2 tệ nhất tới hết trần 720 video.
    assert T._so_mau_toi_da(100, 800, 2.4) == 720
    mau = 720 * 0.003
    assert kq["uoc_tinh_chi_phi_usd"] >= round(mau, 3)
    assert T._so_mau_toi_da(20, 800, 10.0) == 50 + 121, "mẫu nhỏ: 2,5×20 + 6×20+1"


def test_thientai_khong_dau_chi_tinh_khi_kem_ngu_canh_tham_hoa():
    assert T._nhay_cam("thientai") == "" and T._nhay_cam("thientaiamnhac") == ""
    for h in ("thientaimientrung", "thientaicuutro", "cuutromientrung", "baolumientrung"):
        assert T._nhay_cam(h), h


def test_trend_tra_dung_han_va_moi_actor_nhan_han_chot(gia, monkeypatch):
    """Rà 01/10/2026: mỗi bảng chờ nguyên _TOOL_DEADLINE riêng và lượt lấy mẫu đầu không
    kiểm giờ — cộng dồn 300–400s. Nay một hạn chót chung, truyền xuống từng lời gọi actor."""
    import time as _t
    monkeypatch.setattr(A, "_TOOL_DEADLINE", 1.5)
    thay = []

    def bang_treo(vung, ky, n):
        thay.append(A._HAN_CHOT.get())
        _t.sleep(4)
        return []
    monkeypatch.setattr(T, "_bang_hashtag", bang_treo)
    monkeypatch.setattr(T, "_bang_video", lambda *a: (thay.append(A._HAN_CHOT.get()), [])[1])
    t0 = _t.monotonic()
    T.chay({"so_nhac": 0})
    assert _t.monotonic() - t0 < 3.5, "trend phải trả trong hạn, không chờ bảng treo"
    assert thay and all(h is not None for h in thay), "actor phải nhận hạn chót của lượt"


def test_het_gio_thi_bo_lay_mau_va_noi_ro(gia, monkeypatch):
    monkeypatch.setattr(T, "_TOI_THIEU_GIAY_MAU", 10 ** 6)
    goi = []
    monkeypatch.setattr(T, "_mau_am_thanh", lambda *a: goi.append(1))
    kq = json.loads(T.chay({}))
    assert not goi and "hết thời gian" in json.dumps(kq, ensure_ascii=False)