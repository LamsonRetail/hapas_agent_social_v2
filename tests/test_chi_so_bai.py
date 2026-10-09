"""Canh tool `chi_so_bai` (chi_so_bai_tool.py): chỉ số theo DANH SÁCH LINK BÀI.

Câu hỏi thật 05–06/10/2026: team dán 33 link TikTok/FB/IG/YT/Threads, xin "check view,
like, cmt, share, lưu từng link, đúng thứ tự, làm file". Mark không có tool nào làm được,
mò trình duyệt rồi tự cộng tổng. Dữ liệu giả dưới đây giữ ĐÚNG hình dữ liệu thật đo
06/10/2026 trên chính các link đó (xem docstring module).
"""
from __future__ import annotations

import json

import pytest

import apify_tool as A
import chi_phi_tool
import chi_so_bai_tool as C
import lsr_policy
import memory_store
from sheet_gia import LarkGia

TT1 = "https://www.tiktok.com/@rgbvn/video/7691561321686469895"
TT_NGAN = "https://vt.tiktok.com/ZSbf7vghV/"
TT_QUERY = "https://www.tiktok.com/@yum.trending/video/7692265817307761938?_r=1&_t=ZS-9AE"
FB = "https://www.facebook.com/share/v/1GS7huRtfa/"
YT = "https://www.youtube.com/watch?v=ms5PUZ2mSXw"
IG = "https://www.instagram.com/reel/Dd8Hn9qjGCp/"
TH = "https://www.threads.com/share/F4qHeBPhE/"


def _tt(sub, web, view, like, cmt, share, luu, ten="rgbvn"):
    return {"submittedVideoUrl": sub, "webVideoUrl": web, "playCount": view, "diggCount": like,
            "commentCount": cmt, "shareCount": share, "collectCount": luu,
            "createTimeISO": "2026-10-01T05:06:23.000Z", "authorMeta": {"name": ten}}


TIKTOK = [
    _tt(TT1, TT1, 525800, 31500, 384, 7849, 1714),
    _tt(TT_NGAN, "https://www.tiktok.com/@soimoishowbiz/video/7691916185029381384",
        790, 19, 0, 1, 0, "soimoishowbiz"),
    # Link dài có query: actor trả `submittedVideoUrl` đã bỏ query → khớp theo mã video.
    _tt("https://www.tiktok.com/@yum.trending/video/7692265817307761938",
        "https://www.tiktok.com/@yum.trending/video/7692265817307761938", 1000, 10, 1, 0, 2,
        "yum.trending"),
]
INSTAGRAM = [{"inputUrl": IG, "url": "https://www.instagram.com/p/Dd8Hn9qjGCp/",
              "shortCode": "Dd8Hn9qjGCp", "videoViewCount": None, "videoPlayCount": 15320,
              "likesCount": 630, "commentsCount": 0, "timestamp": "2026-10-01T05:06:51.000Z",
              "ownerUsername": "rgb.vn"}]
FACEBOOK = [{"facebookUrl": FB, "likes": 7667, "comments": 170, "pageName": "rgb.vn",
             "share_count_reduced": "1,2K", "creation_time": 1790830825}]
THREADS = [{"item_type": "original_post", "author_username": "rgb.vn",
            "post_url": "https://www.threads.com/@rgb.vn/post/Dd8AzYkiszM?xmt=x",
            "created_at": "2026-10-01T05:06:12.000Z", "like_count": 52, "reply_count": 7,
            "repost_count": 4, "share_count": 11, "view_count": 2292},
           {"item_type": "reply", "text_content": "hay", "like_count": 1}]
YOUTUBE = {"items": [{"id": "ms5PUZ2mSXw",
                      "statistics": {"viewCount": "72", "likeCount": "2", "commentCount": "0"},
                      "snippet": {"channelTitle": "RGB", "publishedAt": "2026-10-01T04:08:20Z"}}]}


@pytest.fixture
def gia(monkeypatch):
    s = {"goi": [], "tran": {}, "loi": {}, "grant": [], "yt": [], "lark": LarkGia()}

    def call(actor, payload, limit, mem=None, min_charge=0, tran_usd=None, *, nen_tang=None):
        s["goi"].append((actor, payload, limit, nen_tang))
        if actor in s["loi"]:
            raise RuntimeError(s["loi"][actor])
        return {C._NGUON["tiktok"]: TIKTOK, C._NGUON["instagram"]: INSTAGRAM,
                C._NGUON["facebook"]: FACEBOOK, C._NGUON["threads"]: THREADS}[actor]

    def yt(resource, params, timeout=None):
        s["yt"].append((resource, params))
        return YOUTUBE

    monkeypatch.setattr(A, "_call", call)
    monkeypatch.setattr(A, "_youtube_get", yt)
    monkeypatch.setattr(A, "_tran_nen_tang",
                        lambda p, nen=None, c=None: s["tran"].get(p, (100, 0.5, True)))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 0.02, "so_run": 4, "cham_tran": 0, "dang_chay": 0})
    monkeypatch.setattr(chi_phi_tool, "ghi", lambda **k: {})
    # Lark giả (tests/sheet_gia.py): Sheet dựng bằng trinh_bay_sheet, soi được từng tab.
    monkeypatch.setattr(A.lark, "call", s["lark"].call)
    monkeypatch.setattr(A, "_grant", lambda tok, oid: s["grant"].append(oid) or True)
    monkeypatch.setattr(memory_store, "get_current_sender", lambda: "ou_x")
    return s


def _chay(**args) -> dict:
    return json.loads(C._handle(args))


# ───────────────────────────── nhận diện link ─────────────────────────────
@pytest.mark.parametrize("u,nen", [
    (TT1, "tiktok"), (TT_NGAN, "tiktok"), (TT_QUERY, "tiktok"),
    ("https://vm.tiktok.com/ZMabc/", "tiktok"),
    ("https://www.tiktok.com/@a/photo/7691561321686469895", "tiktok"),
    (FB, "facebook"), ("https://www.facebook.com/reel/1562933819188284", "facebook"),
    ("https://fb.watch/abc123/", "facebook"),
    ("https://www.facebook.com/rgb.vn/posts/pfbid0abc", "facebook"),
    (YT, "youtube"), ("https://youtu.be/ms5PUZ2mSXw", "youtube"),
    ("https://www.youtube.com/shorts/ms5PUZ2mSXw", "youtube"),
    (IG, "instagram"), ("https://www.instagram.com/p/DHn78JLv9-U/", "instagram"),
    (TH, "threads"), ("https://www.threads.net/@rgb.vn/post/Dd8AzYkiszM", "threads"),
])
def test_nhan_dien_link_bai(u, nen):
    assert C._nhan_dien(u)[0] == nen


@pytest.mark.parametrize("u", [
    "https://www.tiktok.com/@rgbvn", "https://www.instagram.com/rgb.vn/",
    "https://www.facebook.com/rgb.vn", "https://www.youtube.com/@rgb",
    "https://www.threads.com/@rgb.vn", "https://shopee.vn/abc", "không phải link",
])
def test_link_ho_so_hoac_la_thi_khong_dem(u):
    p, ly_do = C._nhan_dien(u)
    assert p is None and ly_do


def test_tach_link_tu_khoi_chu_giu_thu_tu():
    khoi = f"{TT1}\n{TT_NGAN}, {FB}\nxem thêm: {YT}."
    assert C._tach_link([khoi]) == [TT1, TT_NGAN, FB, YT]
    assert C._tach_link(khoi) == [TT1, TT_NGAN, FB, YT]


@pytest.mark.parametrize("v,ra", [(None, None), ("", None), (0, 0), ("244", 244),
                                  ("1,2K", 1200), ("3.4M", 3400000), ("1.234", 1234),
                                  ("abc", None), (True, None)])
def test_doc_so(v, ra):
    assert C._so(v) == ra


# ───────────────────────────── ước tính ─────────────────────────────
def test_uoc_tinh_khong_chay_va_chia_dung_nen_tang(gia):
    kq = _chay(link_bai=[TT1, TT_NGAN, FB, YT, IG, TH, "https://www.tiktok.com/@rgbvn"],
               chi_uoc_tinh=True)
    assert gia["goi"] == [] and gia["yt"] == [] and not gia["lark"].bt
    assert kq["chi_uoc_tinh"] and kq["theo_nen_tang"] == {
        "tiktok": 2, "facebook": 1, "youtube": 1, "instagram": 1, "threads": 1}
    assert kq["uoc_tinh_chi_phi_usd"] == round(2 * 0.003 + 0.005 + 0.0027 + 0.0475, 3)
    assert "Chạy nhé" in kq["huong_dan"] and "USD" in kq["cau_uoc_tinh"]
    assert any("hồ sơ TikTok" in x for x in kq["khong_dem"])


def test_tran_console_cat_link_va_tra_con_lai(gia):
    # Trần TikTok thật trên console 06/10: 50 bài, 0,17 USD/lượt.
    gia["tran"]["tiktok"] = (50, 0.17, True)
    links = [f"https://www.tiktok.com/@a/video/{7000000000000000000 + i}" for i in range(70)]
    kq = _chay(link_bai=links, chi_uoc_tinh=True)
    assert kq["theo_nen_tang"] == {"tiktok": 50}
    assert kq["vuot_tran_console"] == links[50:]
    # Trần USD chặt hơn trần bài: 0,1 USD / (0,003 × 1,1) = 30 link.
    gia["tran"]["tiktok"] = (50, 0.1, True)
    assert _chay(link_bai=links, chi_uoc_tinh=True)["theo_nen_tang"] == {"tiktok": 30}


def test_cong_tac_tat_nen_tang_thi_khong_chay(gia):
    gia["tran"]["tiktok"] = (100, 0.5, False)
    kq = _chay(link_bai=[TT1, YT])
    assert all(g[0] != C._NGUON["tiktok"] for g in gia["goi"])
    assert any("tắt TikTok" in x for x in kq["khong_lay_duoc"])
    assert kq["so_link_ok"] == 1


def test_tran_threads_thap_hon_gia_mot_link(gia):
    gia["tran"]["threads"] = (100, 0.03, True)
    kq = _chay(link_bai=[TH, YT])
    assert all(g[0] != C._NGUON["threads"] for g in gia["goi"])
    assert any("thấp hơn giá một link" in x for x in kq["khong_lay_duoc"])


def test_tran_usd_threads_tinh_ca_lo_khong_tinh_tung_run(gia):
    # Review PR #20: trần mỗi run ≥ 0,1 USD luôn > giá một link Threads, nên phải tính cả lô.
    links = [f"https://www.threads.com/@a/post/Ma{i}" for i in range(30)]
    kq = _chay(link_bai=links, chi_uoc_tinh=True)
    assert kq["theo_nen_tang"] == {"threads": 9}                    # 0,5 / (0,0475 × 1,1)
    assert kq["vuot_tran_console"] == links[9:]


def test_moi_luot_actor_co_han_chot_chung(gia, monkeypatch):
    thay = []
    goc = A._call

    def call(*a, **k):
        thay.append((A._HAN_CHOT.get(), A._SO_RUN.get() is not None))
        return goc(*a, **k)

    monkeypatch.setattr(A, "_call", call)
    _chay(link_bai=[TH, TT1])
    assert len(thay) == 2 and all(h is not None and co_so for h, co_so in thay)


# ───────────────────────────── chạy thật (giả nguồn) ─────────────────────────────
def test_chay_du_5_nen_tang_dung_thu_tu_va_tong_do_code_cong(gia):
    links = [YT, TT_NGAN, FB, TT1, IG, TH, TT_QUERY, TT1, "https://www.tiktok.com/@rgbvn"]
    kq = _chay(link_bai=links)
    rows = gia["lark"].o("Dữ liệu")
    assert rows[0][:3] == ["STT", "Link", "Nền tảng"]
    assert [r[1] for r in rows[1:10]] == links                     # đúng thứ tự dán
    by = {r[1]: r for r in rows[1:7]}
    # View/Like/BL/Share/Lưu ở cột 5..9.
    assert by[TT_NGAN][5:10] == [790, 19, 0, 1, 0] and by[TT_NGAN][3] == "soimoishowbiz"
    assert rows[7][5] == 1000                                       # link có query khớp theo mã
    assert by[YT][5:10] == [72, 2, 0, "", ""]                       # YT: không có share/lưu
    assert by[IG][5:10] == [15320, 630, 0, "", ""]                  # IG: lượt phát
    assert by[FB][5:10] == ["", 7667, 170, 1200, ""]                # FB reel: không view
    assert by[TH][5:10] == [2292, 52, 7, 11, ""]
    assert "Trùng link dòng 4" in rows[8][10] and rows[8][5] == 525800
    assert rows[9][10].startswith("Không đếm")
    # Tổng: 7 link OK, link trùng KHÔNG cộng hai lần, ô trống không tính.
    assert kq["so_link_ok"] == 7
    assert kq["tong"]["view"] == {"tong": 72 + 790 + 525800 + 15320 + 2292 + 1000,
                                  "so_link_co_so": 6}
    assert kq["tong"]["luu"] == {"tong": 0 + 1714 + 2, "so_link_co_so": 3}
    tong_row = rows[-1]
    assert tong_row[1].startswith("TỔNG") and tong_row[5] == kq["tong"]["view"]["tong"]
    assert "545.274" in kq["cau_tong"] and "6 link" in kq["cau_tong"]
    assert kq["sheet_url"] == "https://x.larksuite.com/sheets/sht1" and gia["grant"] == ["ou_x"]
    assert kq["trung_lap"] == ["8 trùng 4"]
    assert any("Instagram" in g for g in kq["gioi_han_nen_tang"])


def test_moi_link_threads_mot_luot_va_tiktok_mot_luot(gia):
    _chay(link_bai=[TH, "https://www.threads.com/share/AbCdEf/", TT1, TT_NGAN])
    th = [g for g in gia["goi"] if g[0] == C._NGUON["threads"]]
    tt = [g for g in gia["goi"] if g[0] == C._NGUON["tiktok"]]
    assert len(th) == 2 and all(len(g[1]["post_urls"]) == 1 for g in th)
    assert len(tt) == 1 and tt[0][1]["postURLs"] == [TT1, TT_NGAN]
    assert all(g[3] in ("tiktok", "threads") for g in gia["goi"])  # trần riêng nền tảng
    assert tt[0][1]["shouldDownloadVideos"] is False


def test_nguon_loi_khong_lam_hong_nen_tang_khac(gia):
    gia["loi"][C._NGUON["tiktok"]] = "HTTP 402"
    kq = _chay(link_bai=[TT1, YT])
    assert kq["success"] is False and "tiktok" in kq["loi"]
    assert kq["so_link_ok"] == 1 and any("Lỗi nguồn TikTok" in x for x in kq["khong_lay_duoc"])


def test_bai_khong_tra_ve_thi_bao_khong_lay_duoc(gia):
    kq = _chay(link_bai=["https://www.tiktok.com/@x/video/7000000000000000001", TT1])
    assert kq["so_link_ok"] == 1
    assert any("Không lấy được" in x for x in kq["khong_lay_duoc"])


def test_khong_link_nao_dem_duoc_thi_khong_tao_sheet(gia):
    kq = _chay(link_bai=["https://www.tiktok.com/@rgbvn"])
    assert not gia["lark"].bt and kq["sheet_url"] is None and kq["so_link_ok"] == 0


def test_thieu_link_bao_loi(gia):
    assert "error" in _chay(link_bai=[])


def test_qua_toi_da_link_bao_so_bi_bo(gia):
    links = [f"https://youtu.be/{i:011d}" for i in range(C._TOI_DA_LINK + 5)]
    kq = _chay(link_bai=links, chi_uoc_tinh=True)
    assert kq["link_bi_bo_vi_qua_dai"] == 5


# ───────────────────────────── nối vào hệ thống ─────────────────────────────
def test_policy_doi_write_data_va_theo_cong_tac_quet_mxh():
    assert lsr_policy._MUTATING_EXACT["chi_so_bai"] == "write_data"
    assert "chi_so_bai" in lsr_policy._TOOL_CO_CONG_TAC
    assert lsr_policy._CONG_TAC_LUI["chi_so_bai"] == "social_listen"


def test_brain_va_ky_nang_tro_toi_tool():
    import pathlib
    goc = pathlib.Path(__file__).resolve().parent.parent
    brain = (goc / "brain.py").read_text(encoding="utf-8")
    assert "import chi_so_bai_tool" in brain and "`chi_so_bai`" in brain
    assert '"chi_so_bai":' in brain                                  # _TOOL_CAN_XET
    sk = (goc / "skills" / "social-query-planning.md").read_text(encoding="utf-8")
    assert "`chi_so_bai`" in sk
    assert "`chi_so_bai`" in (goc / "account_tool.py").read_text(encoding="utf-8")
