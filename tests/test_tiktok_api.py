"""TikTok API (`tiktok_api`, scraptik) — bộ chuyển nhiều yêu cầu + đổi shape về clockworks.

Dữ liệu giả LÀM SẠCH, dựng theo đúng shape phản hồi thật đo 16/10/2026 (`search_item_list[].
aweme_info`, `aweme_list`, `comments`, `user`, `aweme_detail`) — không tên/chữ thật."""
from __future__ import annotations

import datetime
import json

import pytest

import account_tool
import apify_tool as A
import tiktok_api as TT

pytestmark = pytest.mark.tiktok_api
UTC = datetime.timezone.utc
NOW = datetime.datetime.now(UTC)


def _aweme(vid, user="kenh_a", ngay=1, shop=True, ghim=False, ngon_ngu="vi", **st):
    return {"aweme_id": str(vid), "desc": f"noi dung {vid} #tag{vid}",
            "create_time": int((NOW - datetime.timedelta(days=ngay)).timestamp()),
            "author": {"uid": "u1", "sec_uid": "s1", "unique_id": user, "nickname": "Kênh A",
                       "follower_count": 1234},
            "statistics": {"play_count": st.get("xem", 100), "digg_count": 5, "comment_count": 3,
                           "share_count": 1, "collect_count": 2},
            "text_extra": [{"hashtag_name": f"tag{vid}"}, {"user_id": "x"}],
            "anchors": [{"component_key": "anchor_complex_shop", "type": 35}] if shop else [],
            "desc_language": ngon_ngu, "region": "VN", "is_top": 1 if ghim else 0,
            "music": {"title": "am thanh goc"}}


class GiaApi:
    """Giả `apify_tool._run_actor` cho actor scraptik: trả lời theo khoá payload, mỗi lời gọi
    là một "run" (báo `_KHI_CO_RUN` như thật) — `_call` thật vẫn ghi sổ `_SO_RUN`."""

    def __init__(self, mp):
        self.goi: list[dict] = []
        self.tim: dict = {}            # (từ khoá, offset) -> (danh sách aweme, has_more)
        self.ho_so: dict = {}          # tên -> user | None
        self.bai: dict = {}            # con trỏ -> (aweme_list, has_more, max_cursor)
        self.bl: dict = {}             # (vid, cursor) -> (comments, has_more)
        self.tra_loi: dict = {}        # cid -> comments
        self.chi_tiet: dict = {}       # vid -> aweme
        self.loi: set = set()          # khoá payload làm lỗi
        mp.setattr(A, "_run_actor", self._run)

    def _run(self, actor, payload, limit, mem=None, deadline=None, min_charge=0, *,
             tran_usd=None, mot_phan=False, nen_tang=None):
        assert actor == TT.ACTOR and limit == 1 and tran_usd == TT._TRAN_LUOT
        self.goi.append(dict(payload))
        rid = f"r{len(self.goi)}"
        fn = A._KHI_CO_RUN.get()
        if fn:
            fn({"id": rid}, {})
        meta = {"actor": actor, "run_id": rid, "ma": "OK", "usd": TT.GIA_YEU_CAU}
        if set(payload) & self.loi:
            raise A.LoiApify("LOI", "giả lỗi", meta)
        return [self._tra(payload)], meta

    def _tra(self, p):
        if "searchPosts_keyword" in p:
            ds, more = self.tim.get((p["searchPosts_keyword"], p["searchPosts_offset"]), ([], 0))
            return {"status_code": 0, "search_item_list": [{"aweme_info": a} for a in ds],
                    "has_more": more, "cursor": p["searchPosts_offset"] + 30}
        if "profile_username" in p:
            u = self.ho_so.get(p["profile_username"])
            return {"status_code": 0, "user": u or {}}
        if "userPosts_userId" in p:
            ds, more, cur = self.bai.get(p["userPosts_maxCursor"], ([], 0, ""))
            return {"status_code": 0, "aweme_list": ds, "has_more": more, "max_cursor": cur}
        if "listComments_awemeId" in p:
            ds, more = self.bl.get((p["listComments_awemeId"], p["listComments_cursor"]), ([], 0))
            return {"status_code": 0, "comments": ds, "has_more": more,
                    "cursor": p["listComments_cursor"] + 50}
        if "commentReplies_commentId" in p:
            return {"status_code": 0, "comments": self.tra_loi.get(p["commentReplies_commentId"],
                                                                   [])}
        if "post_awemeId" in p:
            a = self.chi_tiet.get(p["post_awemeId"])
            return {"status_code": 0, **({"aweme_detail": a} if a else {})}
        return {"status_code": 5, "status_msg": "lạ"}


@pytest.fixture
def api(monkeypatch):
    return GiaApi(monkeypatch)


def test_doi_shape_video_ve_clockworks():
    v = TT.video(_aweme(7, ghim=True))
    assert v["id"] == "7" and v["webVideoUrl"] == "https://www.tiktok.com/@kenh_a/video/7"
    assert v["authorMeta"]["name"] == "kenh_a" and v["authorMeta"]["fans"] == 1234
    assert (v["playCount"], v["diggCount"], v["commentCount"], v["shareCount"]) == (100, 5, 3, 1)
    assert v["hashtags"] == [{"name": "tag7"}] and v["textLanguage"] == "vi"
    assert v["hasTikTokShopProduct"] is True and v["isPinned"] is True
    assert v["createTimeISO"].endswith(".000Z") and v["_nguon"] == TT.NHAN
    assert TT.video(_aweme(8, shop=False))["hasTikTokShopProduct"] is False
    a = _aweme(9)
    a.pop("anchors")
    assert TT.video(a)["hasTikTokShopProduct"] is None, "thiếu trường thì không đoán 'viral'"
    # Qua bộ chuẩn hoá cũ của social_listen: đủ cột, nguồn ghi rõ là TikTok API.
    d, dt = A._chuan_tiktok(A._chuan_clockworks([TT.video(_aweme(7))]))[0]
    assert d["followers"] == 1234 and d["views"] == 100 and d["gio_hang"] is True
    assert d["_nguon"] == TT.NHAN and dt is not None


@pytest.mark.parametrize("ngay, moc", [(3, 7), (7, 7), (8, 30), (30, 30), (60, 90),
                                       (120, 180), (400, 0)])
def test_moc_ngay_phu_cua_so(ngay, moc):
    assert TT.moc_ngay(NOW - datetime.timedelta(days=ngay), NOW) == moc


def test_tim_lat_trang_toi_du_trong_cua_so_va_bo_trung(api):
    api.tim[("hapas", 0)] = ([_aweme(i, ngay=1 if i % 2 else 5) for i in range(30)], 1)
    api.tim[("hapas", 30)] = ([_aweme(i, ngay=1) for i in range(25, 55)], 1)   # chồng 5 bài
    api.tim[("túi hapas", 0)] = ([_aweme(3), _aweme(100)], 0)
    ra = TT.tim(["hapas", "Hapas", "túi hapas"], 60, NOW - datetime.timedelta(days=3), NOW)
    goi = [g for g in api.goi if g["searchPosts_keyword"] == "hapas"]
    assert [g["searchPosts_offset"] for g in goi] == [0, 30], "15 trong cửa sổ < 30 → lật trang"
    assert all(g["searchPosts_count"] == 30 and g["searchPosts_publishTime"] == 7
               and g["searchPosts_sortType"] == 0 and g["searchPosts_region"] == "VN"
               for g in api.goi)
    assert len({v["id"] for v in ra}) == len(ra) == 56     # 55 "hapas" + 1 mới của "túi hapas"
    assert len(api.goi) == 3


def test_tim_dung_khi_het_trang_va_theo_tran_yeu_cau(api):
    api.tim[("a", 0)] = ([_aweme(1)], 0)
    assert len(TT.tim(["a"], 100, NOW - datetime.timedelta(days=30), NOW)) == 1
    assert len(api.goi) == 1, "has_more=0 thì không hỏi thêm"
    api.goi.clear()
    api.tim.update({(k, 0): ([_aweme(k)], 1) for k in ("b", "c", "d")})
    TT.tim(["b", "c", "d"], 30, None, None, tran_usd=2 * TT.GIA_YEU_CAU)   # trần = 2 yêu cầu
    assert len(api.goi) == 2


def test_tim_moi_tu_deu_loi_thi_nem_loi(api):
    api.loi = {"searchPosts_keyword"}
    with pytest.raises(A.LoiApify):
        TT.tim(["a", "b"], 30, None, None)


def test_ho_so_bo_bai_ghim_lat_trang_va_ghi_chu(api):
    api.ho_so["kenh_a"] = {"uid": "u1", "sec_uid": "s1", "unique_id": "kenh_a",
                           "nickname": "Kênh A", "follower_count": 99, "aweme_count": 40,
                           "total_favorited": 500}
    api.bai["0"] = ([_aweme(1, ghim=True)] + [_aweme(i) for i in range(2, 10)], 1, "c1")
    api.bai["c1"] = ([_aweme(i) for i in range(10, 20)], 1, "c2")
    ra = TT.ho_so(["@kenh_a", "khong_co"], 12)
    cua_a = [x for x in ra if x.get("input") == "kenh_a"]
    # 2 trang đã trả tiền (8 + 10 bài): giữ HẾT 18 bài, không cắt về 12 (soát 18/10/2026).
    assert len(cua_a) == 18 and "1" not in {x["id"] for x in cua_a}, "bỏ bài ghim"
    assert cua_a[0]["authorMeta"]["fans"] == 99 and cua_a[0]["authorMeta"]["video"] == 40
    assert [g["userPosts_maxCursor"] for g in api.goi if "userPosts_userId" in g] == ["0", "c1"]
    ghi = [x for x in ra if x.get("input") == "khong_co"]
    assert ghi and "không thấy" in ghi[0]["note"]
    # Đọc bằng bộ đọc cũ của soi_tai_khoan: hồ sơ + bài, tài khoản không thấy thành ghi chú.
    doc = account_tool._doc_tiktok(ra)
    assert doc["kenh_a"]["ho_so"]["followers"] == 99 and len(doc["kenh_a"]["bai"]) == 18
    assert doc["khong_co"]["ghi_chu"]


def test_binh_luan_goc_roi_tra_loi_trong_tran_moi_bai(api):
    u = "https://www.tiktok.com/@kenh_a/video/70000555"

    def c(i, rep=0):
        return {"cid": f"c{i}", "text": f"bl {i}", "create_time": int(NOW.timestamp()),
                "digg_count": i, "reply_comment_total": rep, "reply_id": "0",
                "user": {"unique_id": f"khach{i}", "uid": f"k{i}"}, "is_author_digged": i == 1}
    api.bl[("70000555", 0)] = ([c(i, rep=2 if i == 3 else 0) for i in range(50)], 1)
    api.bl[("70000555", 50)] = ([c(i) for i in range(45, 60)], 0)                 # chồng 5
    api.tra_loi["c3"] = [{**c(900), "reply_id": "c3"}, {**c(901), "reply_id": "c3"}]
    ra = TT.binh_luan([u, "https://vt.tiktok.com/rutgon/"], 70, tra_loi=20)
    goc = [r for r in ra if not r["repliesToId"]]
    tl = [r for r in ra if r["repliesToId"]]
    assert len(goc) == 60 and len(tl) == 2 and tl[0]["repliesToId"] == "c3"
    assert all(r["videoWebUrl"] == u for r in ra), "link rút gọn: bỏ qua, bên gọi chạy dự phòng"
    assert goc[1]["likedByAuthor"] is True and goc[1]["uniqueId"] == "khach1"
    import deep_dive_tool as D
    rows, n = D._map_tiktok(ra)
    assert n == 62 and rows[0]["kenh"] == "khach0" and any(r["cha"] for r in rows)


def test_so_lieu_bai_theo_link(api):
    api.chi_tiet["70000777"] = _aweme(70000777, xem=999)
    ra = TT.so_lieu_bai(["https://www.tiktok.com/@kenh_a/video/70000777",
                         "https://www.tiktok.com/@kenh_a/video/70000888"])
    assert [(x["id"], x["playCount"]) for x in ra] == [("70000777", 999)]


def test_fetch_tiktok_di_api_truoc_roi_moi_du_phong(api, monkeypatch):
    api.tim[("hapas", 0)] = ([_aweme(1), _aweme(2)], 0)
    ra = A._fetch_tiktok(["hapas"], 30, "VN", NOW - datetime.timedelta(days=3), NOW)
    assert [d["link"].rsplit("/", 1)[1] for d, _ in ra] == ["1", "2"]
    # API lỗi → chuỗi cũ (apidojo) chạy như trước.
    api.loi = {"searchPosts_keyword"}
    cu = []
    monkeypatch.setattr(A, "_call", lambda actor, payload, limit, **k: (
        cu.append(actor), [] if actor != A._ACTORS["tiktok"] else [
            {"postPage": "https://www.tiktok.com/@x/video/9", "channel": {"username": "x"},
             "uploadedAtFormatted": NOW.isoformat()}])[1])
    monkeypatch.setattr(TT.A, "_call", A._call)
    ra = A._fetch_tiktok(["hapas"], 30, "VN", NOW - datetime.timedelta(days=3), NOW)
    assert cu[0] == "scraptik~tiktok-api" and A._ACTORS["tiktok"] in cu


def test_soi_tai_khoan_api_khong_ra_bai_thi_chay_clockworks(api, monkeypatch):
    api.ho_so["kenh_a"] = {"uid": "u1", "unique_id": "kenh_a", "follower_count": 5}
    api.bai["0"] = ([_aweme(1)], 0, "")
    goc = A._call
    du_phong = []

    def call(actor, payload, limit, **k):
        if actor == TT.ACTOR:
            return goc(actor, payload, limit, **k)
        du_phong.append((actor, payload["profiles"]))
        return [{"authorMeta": {"name": "kenh_b", "fans": 7}, "webVideoUrl":
                 "https://www.tiktok.com/@kenh_b/video/2", "createTimeISO": NOW.isoformat()}]
    monkeypatch.setattr(A, "_call", call)
    ra = account_tool._lay_tiktok(["kenh_a", "kenh_b"], 5)
    assert du_phong == [(account_tool._ACTOR["tiktok"], ["kenh_b"])]
    assert len(ra["kenh_a"]["bai"]) == 1 and len(ra["kenh_b"]["bai"]) == 1


@pytest.mark.parametrize("ma, giu", [("CHI_DEMO", True), ("LOI", True),
                                     ("HET_TIEN_THANG", False)])
def test_soi_tai_khoan_du_phong_hong_van_giu_bai_api(api, monkeypatch, ma, giu):
    """Soát 17/10/2026: clockworks (mắt xích cuối) ném CHI_DEMO thì bài TikTok API đã đọc được
    của tài khoản khác không được mất theo; tài khoản thiếu mang ghi chú lý do."""
    api.ho_so["kenh_a"] = {"uid": "u1", "unique_id": "kenh_a", "follower_count": 5}
    api.bai["0"] = ([_aweme(1)], 0, "")
    goc = A._call

    def call(actor, payload, limit, **k):
        if actor == TT.ACTOR:
            return goc(actor, payload, limit, **k)
        raise A.LoiApify(ma, "giả lỗi dự phòng")
    monkeypatch.setattr(A, "_call", call)
    if giu:
        ra = account_tool._lay_tiktok(["kenh_a", "kenh_b"], 5)
        assert len(ra["kenh_a"]["bai"]) == 1 and not ra["kenh_b"]["bai"]
        assert f"dự phòng lỗi {ma}: {A.nhan_ma(ma)}" in ra["kenh_b"]["ghi_chu"]
    else:
        with pytest.raises(A.LoiApify):
            account_tool._lay_tiktok(["kenh_a", "kenh_b"], 5)
    # API không ra bài nào để giữ: lỗi dự phòng ném ra như cũ.
    with pytest.raises(A.LoiApify):
        account_tool._lay_tiktok(["kenh_b"], 5)


def test_bang_chon_actor_khop_ten_actor_cu():
    import deep_dive_tool as D
    assert TT.CHON["tiktok_tim"]["du_phong"] == (A._ACTORS["tiktok"],
                                                A._ACTORS["tiktok_fallback"])
    assert TT.CHON["tiktok_ho_so"]["du_phong"] == (account_tool._ACTOR["tiktok"],)
    assert TT.CHON["tiktok_binh_luan"]["du_phong"] == (D._ACTORS["tiktok"],)
    assert TT.CHON["facebook_tim"]["chinh"] == A._ACTORS["facebook"]
    assert TT.CHON["facebook_trang"]["chinh"] == account_tool._ACTOR["facebook"]
    assert TT.CHON["facebook_binh_luan"]["chinh"] == D._ACTORS["facebook"]
    assert json.dumps(TT.CHON)


def test_goi_apify_dat_tay_qua_env(monkeypatch):
    """Token phạm vi hẹp không đọc được /users/me: `APIFY_GOI` quyết định gói."""
    monkeypatch.setenv("APIFY_GOI", "starter")
    assert A._goi_apify() == "STARTER"
    monkeypatch.delenv("APIFY_GOI")
    assert A._goi_apify() == ""          # bộ thử tắt hỏi trước (APIFY_KIEM_TRUOC=0)


# ───────────── review 16/10: dự phòng, lỗi từng mục, ước tính theo yêu cầu ─────────────
def test_tim_thanh_cong_ma_rong_thi_khong_chay_du_phong(api):
    """HIGH 1: API tìm THÀNH CÔNG mà 0 bài (từ khoá hẹp + lọc 7 ngày) không được đẩy sang
    clockworks (tính theo video) — giả `_run_actor` chỉ nhận actor TikTok API, gọi actor cũ là
    bài thử đỏ."""
    assert A._fetch_tiktok(["tu_hiem"], 30, "VN", NOW - datetime.timedelta(days=3), NOW) == []
    assert [g.get("searchPosts_keyword") for g in api.goi] == ["tu_hiem"]


def test_du_phong_chi_tieu_phan_ngan_sach_con_lai(monkeypatch):
    def hong(*a, **k):
        raise A.LoiApify("LOI", "API hỏng")
    monkeypatch.setattr(TT, "tim", hong)
    goi = []
    monkeypatch.setattr(A, "_call", lambda actor, payload, limit, **k: (
        goi.append((actor, limit, k.get("tran_usd"))), [])[1])
    d3 = NOW - datetime.timedelta(days=3)
    assert A._fetch_tiktok(["a"], 100, "VN", d3, NOW, tran_du_phong=0.05) == []
    assert goi == [], "dưới sàn 0,1 USD: không chạy dự phòng"
    A._fetch_tiktok(["a"], 100, "VN", d3, NOW, tran_du_phong=0.15)
    assert goi[0] == (A._ACTORS["tiktok"], 100, 0.15)
    # clockworks: 0,15 USD / 0,003 = 50 video tối đa, trần đúng phần còn.
    assert goi[1] == (A._ACTORS["tiktok_fallback"], 50, 0.15)


def test_loi_mot_tai_khoan_mot_video_khong_bo_ca_lo(api):
    """MEDIUM 2: lỗi API của MỘT tài khoản / video ghi vào `loi_ra`, phần còn lại giữ."""
    api.ho_so["kenh_a"] = {"uid": "u1", "unique_id": "kenh_a"}
    api.bai["0"] = ([_aweme(1)], 0, "")
    goc = api._tra

    def tra(p):
        if p.get("profile_username") == "kenh_loi" or p.get("listComments_awemeId") == "70000002":
            raise A.LoiApify("LOI", "giả lỗi")
        return goc(p)
    api._tra = tra
    loi: list = []
    ra = TT.ho_so(["kenh_a", "kenh_loi", "khong_co"], 5, loi_ra=loi)
    assert any(x.get("webVideoUrl") for x in ra if x.get("input") == "kenh_a")
    assert sorted((k, ma) for k, ma, _ in loi) == [("kenh_loi", "LOI"), ("khong_co", "KHONG_THAY")]
    api.bl[("70000001", 0)] = ([{"cid": "c1", "text": "x", "reply_comment_total": 0,
                                 "reply_id": "0", "user": {"unique_id": "k"}}], 0)
    loi = []
    u1, u2 = (f"https://www.tiktok.com/@a/video/7000000{i}" for i in (1, 2))
    ra = TT.binh_luan([u1, u2, "https://vt.tiktok.com/x/"], 20, loi_ra=loi)
    assert [r["videoWebUrl"] for r in ra] == [u1]
    assert sorted(k for k, _, _ in loi) == sorted([u2, "https://vt.tiktok.com/x/"])


def test_tim_trang_sau_loi_giu_trang_truoc(api):
    api.tim[("a", 0)] = ([_aweme(i) for i in range(30)], 1)
    goc = api._tra
    api._tra = lambda p: (_ for _ in ()).throw(A.LoiApify("LOI", "trang 2 hỏng")) \
        if p.get("searchPosts_offset") else goc(p)
    assert len(TT.tim(["a"], 60, None, None)) == 30


def test_uoc_tai_cho_tiktok_theo_yeu_cau():
    """MEDIUM 4: ≥ 1 yêu cầu mỗi từ khoá, tối đa 2×(trang cần)+1 — như /theodoi."""
    est, luot = A._uoc_tai_cho(["tiktok"], {"tiktok": 100}, ["a", "b", "A"])
    assert est == pytest.approx(TT.so_yeu_cau_tim(2, 50) * TT.GIA_YEU_CAU)    # 10 × 0,003
    assert luot["tiktok"] == TT.GIA_YEU_CAU
    assert A._uoc_tai_cho(["tiktok"], {"tiktok": 5}, ["k" + str(i) for i in range(21)])[0] == \
        pytest.approx(21 * 3 * TT.GIA_YEU_CAU)
