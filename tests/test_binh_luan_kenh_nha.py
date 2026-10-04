"""Canh tool `binh_luan_kenh_nha` (kenh_nha_tool.py + kenh_nha_meta.py): bình luận trên
kênh CỦA HAPAS qua API chính thức của Meta.

Không mạng: thay `kenh_nha_meta._http_get` bằng bộ định tuyến giả theo đúng hình trả về
trong tài liệu Meta (Threads `/conversation` phẳng có `replied_to`; Instagram `comments`
kèm `replies{…}`; Facebook `comments?filter=stream` có `parent`). Sổ token ghi vào thư
mục tạm, không đụng `.tokens/` thật.
"""
from __future__ import annotations

import json
import time

import pytest

import apify_tool as A
import kenh_nha_meta as M
import kenh_nha_tool as K
import lsr_policy

# Giá trị giả đủ dài để lộ ra là thấy ngay; KHÔNG phải token thật.
TOK_TH = "THAAfakeThreadsShortToken0123456789abcdef"
TOK_TH_DAI = "THAAfakeThreadsLongToken9876543210zyxwvu"
TOK_TH_MOI = "THAAfakeThreadsRefreshed555555555555555"
TOK_IG = "IGAAfakeInstagramLongToken0123456789abcd"
TOK_FB = "EAAfakePageToken0123456789abcdefghijklmn"
SECRET = "fakeappsecret0123456789"


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(M, "TEP_TOKEN", tmp_path / ".tokens" / "meta_kenh_nha.json")
    monkeypatch.setattr(M, "_DA_BIET", set())
    for k in ("META_APP_ID", "META_APP_SECRET", "THREADS_ACCESS_TOKEN", "IG_ACCESS_TOKEN",
              "FB_PAGE_ID", "FB_PAGE_ACCESS_TOKEN"):
        monkeypatch.delenv(k, raising=False)

    def dat(**kv):
        for k, v in kv.items():
            monkeypatch.setenv(k, v)
    return dat


class Mang:
    """Bộ định tuyến HTTP giả: (đường, con trỏ after) → (mã, JSON). Ghi lại mọi lời gọi."""

    def __init__(self):
        self.goi: list[tuple[str, dict]] = []
        self.tuyen: dict = {}

    def __call__(self, url, params, timeout):
        self.goi.append((url, dict(params)))
        duong = url.split("/", 3)[3]
        duong = duong.split("/", 1)[1] if duong.startswith(("v1.0/", "v26.0/")) else duong
        r = self.tuyen.get((duong, params.get("after")), self.tuyen.get(duong))
        if r is None:
            return 404, {"error": {"message": f"giả: không có {duong}", "code": 100}}
        return r(params) if callable(r) else r

    def duong_da_goi(self):
        return [u.split("/", 3)[3] for u, _ in self.goi]


@pytest.fixture
def mang(monkeypatch):
    m = Mang()
    monkeypatch.setattr(M, "_http_get", m)
    return m


@pytest.fixture
def sheet(monkeypatch):
    """Giả Lark Sheet ở tầng `lark.call` — bộ chặn công thức thật vẫn chạy."""
    ghi: list = []
    monkeypatch.setattr(A, "_create_sheet", lambda title: ("tok", "https://sheet/x"))
    monkeypatch.setattr(A, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(A, "_them_tab", lambda tok, ten: "tab-" + ten)
    monkeypatch.setattr(A.lark, "call", lambda *a, **k: ghi.append(k.get("body")) or {})
    monkeypatch.setattr(K.memory_store, "get_current_sender", lambda: None)

    def nhan(rows, han, tt):
        tt.update(trang_thai="đã chạy")
        return [("Tiêu cực", "Sản phẩm/chất lượng") if "xấu" in (r["text"] or "")
                else ("Tích cực", "Sản phẩm/chất lượng") for r in rows]
    monkeypatch.setattr(K.phan_loai, "phan_loai_binh_luan", nhan)
    return ghi


def _bang(ghi, tab: str) -> list[list]:
    ra = []
    for b in ghi:
        for vr in (b or {}).get("valueRanges", []):
            if vr["range"].startswith(tab + "!"):
                ra += vr["values"]
    return ra


def chay(**args) -> dict:
    return json.loads(K._handle(args))


# ───────────────────────── dữ liệu giả ─────────────────────────
def _threads(m: Mang):
    m.tuyen["me"] = (200, {"id": "u1", "username": "hapas.vn"})
    m.tuyen["me/threads"] = (200, {"data": [
        {"id": "P1", "permalink": "https://www.threads.com/@hapas.vn/post/AAA",
         "text": "Túi mới", "timestamp": "2026-10-03T03:00:00+0000", "shortcode": "AAA"},
        {"id": "RP", "media_type": "REPOST_FACADE", "timestamp": "2026-10-02T03:00:00+0000"},
    ]})
    m.tuyen["P1/conversation"] = (200, {"data": [
        {"id": "C1", "text": "Đẹp quá", "username": "khach1", "timestamp": "2026-10-03T04:00:00+0000",
         "replied_to": {"id": "P1"}, "root_post": {"id": "P1"}},
        {"id": "C2", "text": "Giá bao nhiêu?", "username": "khach2",
         "timestamp": "2026-10-03T05:00:00+0000", "replied_to": {"id": "C1"},
         "root_post": {"id": "P1"}},
        {"id": "C3", "text": "Inbox bạn nhé", "username": "hapas.vn",
         "timestamp": "2026-10-03T06:00:00+0000", "replied_to": {"id": "C2"},
         "root_post": {"id": "P1"}, "is_reply_owned_by_me": True},
        {"id": "C4", "text": "=HYPERLINK(\"http://x\",\"xấu\")", "username": "khach3",
         "timestamp": "2026-10-03T07:00:00+0000", "replied_to": {"id": "P1"},
         "root_post": {"id": "P1"}},
    ], "paging": {"cursors": {"after": "z"}}})


def _instagram(m: Mang):
    m.tuyen["me"] = (200, {"id": "ig1", "username": "hapas.official"})
    m.tuyen["me/media"] = (200, {"data": [
        {"id": "M1", "permalink": "https://www.instagram.com/p/XYZ/", "caption": "BST mới",
         "timestamp": "2026-10-02T03:00:00+0000", "shortcode": "XYZ", "comments_count": 4}]})
    m.tuyen[("M1/comments", None)] = (200, {
        "data": [{"id": "I1", "text": "Xinh", "username": "a", "timestamp": "2026-10-02T04:00:00+0000",
                  "like_count": 3,
                  "replies": {"data": [{"id": "I1r1", "text": "đồng ý", "username": "b",
                                        "timestamp": "2026-10-02T05:00:00+0000", "like_count": 1}],
                              "paging": {"cursors": {"after": "r1"},
                                         "next": "https://graph.instagram.com/x?access_token="
                                                 + TOK_IG}}}],
        "paging": {"cursors": {"after": "c2"},
                   "next": "https://graph.instagram.com/v26.0/M1/comments?access_token=" + TOK_IG}})
    m.tuyen[("M1/comments", "c2")] = (200, {"data": [
        {"id": "I2", "text": "Chất da xấu", "username": "c", "timestamp": "2026-10-02T06:00:00+0000",
         "like_count": 0}], "paging": {"cursors": {"after": "c3"}}})
    m.tuyen[("I1/replies", None)] = (200, {"data": [
        {"id": "I1r1", "text": "đồng ý", "username": "b", "timestamp": "2026-10-02T05:00:00+0000",
         "like_count": 1},
        {"id": "I1r2", "text": "Cảm ơn bạn", "username": "hapas.official",
         "timestamp": "2026-10-02T05:30:00+0000", "like_count": 0}]})


def _facebook(m: Mang):
    m.tuyen["111"] = (200, {"id": "111", "name": "HAPAS"})
    m.tuyen["111/posts"] = (200, {"data": [
        {"id": "111_9", "message": "Sale", "created_time": "2026-10-01T03:00:00+0000",
         "permalink_url": "https://www.facebook.com/hapas/posts/9",
         "comments": {"summary": {"total_count": 3}}}]})
    m.tuyen[("111_9/comments", None)] = (200, {"data": [
        {"id": "9_1", "message": "Còn size M không", "from": {"id": "u7", "name": "Lan"},
         "created_time": "2026-10-01T04:00:00+0000", "like_count": 2}],
        "paging": {"cursors": {"after": "p2"}, "next": "https://graph.facebook.com/x"}})
    m.tuyen[("111_9/comments", "p2")] = (200, {"data": [
        {"id": "9_2", "message": "Dạ còn ạ", "from": {"id": "111", "name": "HAPAS"},
         "created_time": "2026-10-01T05:00:00+0000", "parent": {"id": "9_1"}},
        {"id": "9_3", "message": "Ship chậm, xấu", "from": {"id": "u8", "name": "Minh"},
         "created_time": "2026-10-01T06:00:00+0000", "parent": {"id": "9_2"}, "like_count": 0}]})


def _so_dai_han(kenh: str, token: str, env_tok: str, het_sau: float, tuoi: float):
    bay = int(time.time())
    M.ghi_so({kenh: {"token": token, "loai": "dai_han", "env": M._van_tay(env_tok),
                     "lay_luc": bay - int(tuoi), "het_han": bay + int(het_sau)}})


# ───────────────────────── Threads: trả lời mọi cấp ─────────────────────────
def test_threads_conversation_tra_loi_long_nhau_va_tra_loi_cua_kenh(env, mang, sheet):
    env(THREADS_ACCESS_TOKEN=TOK_TH_DAI)
    _so_dai_han("threads", TOK_TH_DAI, TOK_TH_DAI, 50 * M.NGAY, 2 * M.NGAY)
    _threads(mang)
    kq = chay(kenh=["threads"], so_bai=3)
    assert kq["success"] and kq["sheet_url"] == "https://sheet/x"
    url, p = next(g for g in mang.goi if "conversation" in g[0])
    assert url.startswith("https://graph.threads.net/v1.0/P1/conversation")
    assert {"text", "username", "timestamp", "replied_to", "root_post"} <= set(p["fields"].split(","))
    assert kq["tong_comment"] == 4 and kq["tra_loi_cua_kenh_nha"] == 1
    # bài đăng lại của người khác không phải bài kênh
    assert len(kq["per_bai"]) == 1
    rows = _bang(sheet, "s1")
    assert rows[0] == K._HEADER and "Sắc thái" in rows[0] and "Chủ đề" in rows[0]
    by_text = {r[2].lstrip("'"): r for r in rows[1:]}
    assert by_text["Đẹp quá"][10] == "bình luận" and by_text["Đẹp quá"][6] == 1
    assert by_text["Giá bao nhiêu?"][10] == "trả lời cấp 2"
    assert by_text["Giá bao nhiêu?"][11] == "khach1"
    assert by_text["Inbox bạn nhé"][10] == "trả lời cấp 3"
    assert by_text["Inbox bạn nhé"][3] == K._KENH_NHA, "trả lời của shop không được gán nhãn"
    # Thống kê chỉ đếm bình luận của khách
    assert kq["thong_ke"]["tong"] == 3
    # cây: trả lời nằm ngay dưới cha
    thu_tu = [r[2].lstrip("'") for r in rows[1:]]
    assert thu_tu.index("Giá bao nhiêu?") == thu_tu.index("Đẹp quá") + 1
    # Threads không có like từng trả lời → ô trống, không bịa số 0
    assert by_text["Đẹp quá"][5] == ""


def test_bo_chan_cong_thuc_va_tab_thong_ke(env, mang, sheet):
    env(THREADS_ACCESS_TOKEN=TOK_TH_DAI)
    _so_dai_han("threads", TOK_TH_DAI, TOK_TH_DAI, 50 * M.NGAY, 2 * M.NGAY)
    _threads(mang)
    chay(kenh="threads")
    o = [r[2] for r in _bang(sheet, "s1")[1:]]
    assert any(x.startswith("'=HYPERLINK") for x in o), "ô '=' phải bị vô hiệu hoá"
    tk = _bang(sheet, "tab-Thống kê")
    assert tk and tk[0][3].startswith("Tỉ lệ %")
    bai = _bang(sheet, "tab-" + K._TAB_BAI)
    assert bai[0] == K._HEADER_BAI and bai[1][4] == 4


# ───────────────────────── Instagram: phân trang + replies ─────────────────────────
def test_instagram_phan_trang_va_doc_them_tra_loi(env, mang, sheet):
    env(IG_ACCESS_TOKEN=TOK_IG)
    _so_dai_han("instagram", TOK_IG, TOK_IG, 50 * M.NGAY, 2 * M.NGAY)
    _instagram(mang)
    kq = chay(kenh=["instagram"])
    assert kq["success"], kq
    goi = mang.duong_da_goi()
    assert goi.count("v26.0/M1/comments") == 2, "phải đọc trang 2 theo con trỏ after"
    assert "v26.0/I1/replies" in goi, "replies{} còn trang sau thì đọc cạnh /replies"
    # không bao giờ đi theo paging.next (URL đó chứa token)
    assert all("access_token=" not in u for u, _ in mang.goi)
    p = next(p for u, p in mang.goi if u.endswith("M1/comments"))
    assert "replies{" in p["fields"] and "like_count" in p["fields"]
    rows = {r[2]: r for r in _bang(sheet, "s1")[1:]}
    assert set(rows) == {"Xinh", "đồng ý", "Cảm ơn bạn", "Chất da xấu"}
    assert rows["đồng ý"][11] == "a" and rows["Xinh"][5] == 3
    assert rows["Cảm ơn bạn"][3] == K._KENH_NHA
    assert kq["thong_ke"]["sac_thai"]["Tiêu cực"]["so"] == 1


# ───────────────────────── Facebook: stream + parent ─────────────────────────
def test_facebook_stream_phan_trang_va_parent(env, mang, sheet):
    env(FB_PAGE_ID="111", FB_PAGE_ACCESS_TOKEN=TOK_FB)
    _facebook(mang)
    kq = chay(kenh=["facebook"])
    assert kq["success"], kq
    p = next(p for u, p in mang.goi if u.endswith("111_9/comments"))
    assert p["filter"] == "stream" and "parent" in p["fields"]
    assert mang.goi[0][0].startswith("https://graph.facebook.com/v26.0/")
    rows = {r[2]: r for r in _bang(sheet, "s1")[1:]}
    assert rows["Dạ còn ạ"][3] == K._KENH_NHA and rows["Dạ còn ạ"][11] == "Lan"
    assert rows["Ship chậm, xấu"][10] == "trả lời cấp 3"
    assert kq["per_bai"][0]["nen_tang_bao"] == 3 and kq["per_bai"][0]["binh_luan"] == 3


def test_cham_tran_max_comments_thi_bao_chua_lay_het(env, mang, sheet):
    env(FB_PAGE_ID="111", FB_PAGE_ACCESS_TOKEN=TOK_FB)
    _facebook(mang)
    kq = chay(kenh="facebook", max_comments=1)
    assert kq["per_bai"][0]["trang_thai"] == K._CHAM_TRAN
    assert "chưa lấy hết" in kq["note"]


def test_link_bai_cua_kenh_nha_va_link_la(env, mang, sheet):
    env(IG_ACCESS_TOKEN=TOK_IG)
    _so_dai_han("instagram", TOK_IG, TOK_IG, 50 * M.NGAY, 2 * M.NGAY)
    _instagram(mang)
    kq = chay(bai=["https://www.instagram.com/p/XYZ/?igsh=1",
                   "https://www.instagram.com/p/DOITHU/"])
    kh = kq["per_kenh"]["instagram"]["khong_tim_thay"]
    assert list(kh) == ["https://www.instagram.com/p/DOITHU/"]
    assert "social_deep_dive" in kh["https://www.instagram.com/p/DOITHU/"]
    assert kq["per_bai"][0]["link"] == "https://www.instagram.com/p/XYZ/"
    loi = json.loads(K._handle({"bai": ["https://www.tiktok.com/@x/video/1"]}))
    assert "social_deep_dive" in json.dumps(loi, ensure_ascii=False)


# ───────────────────────── thiếu cấu hình từng kênh ─────────────────────────
def test_thieu_env_thi_chua_noi_khong_sap(env, mang, sheet):
    env(IG_ACCESS_TOKEN=TOK_IG)
    _so_dai_han("instagram", TOK_IG, TOK_IG, 50 * M.NGAY, 2 * M.NGAY)
    _instagram(mang)
    kq = chay()
    assert kq["per_kenh"]["threads"]["trang_thai"] == "CHƯA NỐI"
    assert "THREADS_ACCESS_TOKEN" in kq["per_kenh"]["threads"]["loi"]
    assert "FB_PAGE_ID" in kq["per_kenh"]["facebook"]["loi"]
    assert kq["per_kenh"]["instagram"]["trang_thai"] == "OK"
    assert "chủ agent cần cấp" in kq["note"]
    assert not any("threads.net" in u or "facebook.com" in u for u, _ in mang.goi)


def test_khong_kenh_nao_noi(env, mang):
    kq = json.loads(K._handle({}))
    assert "error" in kq and "chưa nối" in kq["error"]
    assert mang.goi == []
    uoc = chay(chi_uoc_tinh=True)
    assert uoc["chi_uoc_tinh"] and uoc["chi_phi_usd"] == 0 and "Chạy nhé?" in uoc["note"]
    assert all("chưa nối" in v for v in uoc["kenh"].values())
    assert mang.goi == [], "ước tính không được gọi mạng"


# ───────────────────────── token: đổi, làm mới, lịch ─────────────────────────
def test_threads_doi_token_ngan_sang_dai_han_luu_so_khong_ghi_env(env, mang, monkeypatch):
    env(THREADS_ACCESS_TOKEN=TOK_TH, META_APP_ID="1", META_APP_SECRET=SECRET)
    mang.tuyen["access_token"] = (200, {"access_token": TOK_TH_DAI, "token_type": "bearer",
                                        "expires_in": 5184000})
    assert M.lay_token("threads") == TOK_TH_DAI
    url, p = mang.goi[0]
    assert url == "https://graph.threads.net/access_token"
    assert p["grant_type"] == "th_exchange_token" and p["client_secret"] == SECRET
    so = json.loads(M.TEP_TOKEN.read_text(encoding="utf-8"))
    assert so["threads"]["token"] == TOK_TH_DAI and so["threads"]["env"] != TOK_TH
    assert TOK_TH not in M.TEP_TOKEN.read_text(encoding="utf-8")
    # Lần sau dùng sổ, không đổi lại
    mang.goi.clear()
    assert M.lay_token("threads") == TOK_TH_DAI and mang.goi == []
    # Dán token mới vào .env → nạp lại
    monkeypatch.setenv("THREADS_ACCESS_TOKEN", TOK_TH + "x")
    M.lay_token("threads")
    assert mang.goi and mang.goi[0][1]["grant_type"] == "th_exchange_token"


def test_instagram_doi_bang_ig_exchange_token(env, mang):
    env(IG_ACCESS_TOKEN=TOK_IG, META_APP_ID="1", META_APP_SECRET=SECRET)
    mang.tuyen["access_token"] = (200, {"access_token": TOK_IG + "L", "expires_in": 5184000})
    assert M.lay_token("instagram") == TOK_IG + "L"
    assert mang.goi[0][0] == "https://graph.instagram.com/access_token"
    assert mang.goi[0][1]["grant_type"] == "ig_exchange_token"


def test_token_da_dai_han_thi_lam_moi_thay_vi_doi(env, mang):
    env(IG_ACCESS_TOKEN=TOK_IG, META_APP_ID="1", META_APP_SECRET=SECRET)
    mang.tuyen["access_token"] = (400, {"error": {"message": "Invalid", "code": 100}})
    mang.tuyen["refresh_access_token"] = (200, {"access_token": TOK_IG + "R",
                                                "expires_in": 5184000})
    assert M.lay_token("instagram") == TOK_IG + "R"
    assert mang.goi[-1][1]["grant_type"] == "ig_refresh_token"


@pytest.mark.parametrize("con_ngay,tuoi_ngay,lam_moi", [
    (5, 30, True),      # còn < 10 ngày, đủ 24 giờ tuổi → làm mới
    (20, 30, False),    # còn nhiều
    (5, 0.5, False),    # < 24 giờ tuổi: Meta không cho làm mới
])
def test_lich_lam_moi(env, mang, con_ngay, tuoi_ngay, lam_moi):
    env(THREADS_ACCESS_TOKEN=TOK_TH)
    _so_dai_han("threads", TOK_TH_DAI, TOK_TH, con_ngay * M.NGAY, tuoi_ngay * M.NGAY)
    mang.tuyen["refresh_access_token"] = (200, {"access_token": TOK_TH_MOI,
                                                "expires_in": 5184000})
    tok = M.lay_token("threads")
    assert (tok == TOK_TH_MOI) is lam_moi
    if lam_moi:
        assert mang.goi[0][0] == "https://graph.threads.net/refresh_access_token"
        assert mang.goi[0][1]["grant_type"] == "th_refresh_token"
        e = json.loads(M.TEP_TOKEN.read_text(encoding="utf-8"))["threads"]
        assert e["het_han"] - time.time() > 59 * M.NGAY
    else:
        assert mang.goi == []


def test_lam_moi_hong_thi_dung_token_cu_va_6_gio_sau_moi_thu(env, mang, capsys):
    env(THREADS_ACCESS_TOKEN=TOK_TH)
    _so_dai_han("threads", TOK_TH_DAI, TOK_TH, 5 * M.NGAY, 30 * M.NGAY)
    mang.tuyen["refresh_access_token"] = (500, {"error": {
        "message": f"loi tam thoi access_token={TOK_TH_DAI}", "code": 2}})
    assert M.lay_token("threads") == TOK_TH_DAI
    n = len(mang.goi)
    M.lay_token("threads")
    assert len(mang.goi) == n, "vừa hỏng thì chưa thử lại"
    bay = int(time.time()) + 7 * 3600
    M.lay_token("threads", bay_gio=bay)
    assert len(mang.goi) == n + 1
    assert TOK_TH_DAI not in capsys.readouterr().out


def test_facebook_token_page_khong_lam_moi(env):
    assert not M.can_lam_moi("facebook", {"loai": "vinh_vien", "lay_luc": 0}, int(time.time()))


def test_facebook_token_user_doi_lay_token_trang(env, mang):
    env(FB_PAGE_ID="111", FB_PAGE_ACCESS_TOKEN=TOK_FB, META_APP_ID="1", META_APP_SECRET=SECRET)
    mang.tuyen["debug_token"] = (200, {"data": {"is_valid": True, "type": "USER",
                                                "expires_at": int(time.time()) + 3600}})
    mang.tuyen["oauth/access_token"] = (200, {"access_token": TOK_FB + "LL"})
    mang.tuyen["111"] = (200, {"id": "111", "access_token": TOK_FB + "PAGE"})
    assert M.lay_token("facebook") == TOK_FB + "PAGE"
    assert json.loads(M.TEP_TOKEN.read_text(encoding="utf-8"))["facebook"]["loai"] == "vinh_vien"
    assert mang.goi[1][1]["grant_type"] == "fb_exchange_token"
    assert "appsecret_proof" in mang.goi[-1][1]


def test_tinh_trang_khong_goi_mang(env, mang):
    env(THREADS_ACCESS_TOKEN=TOK_TH)
    _so_dai_han("threads", TOK_TH_DAI, TOK_TH, 12 * M.NGAY, 30 * M.NGAY)
    tt = M.tinh_trang()
    assert tt["threads"]["con_ngay"] in (11, 12) and tt["instagram"]["noi"] is False
    assert mang.goi == []


# ───────────────────────── token không bao giờ lộ ─────────────────────────
def test_token_het_han_noi_thang_va_khong_lo_token(env, mang, sheet, capsys):
    env(THREADS_ACCESS_TOKEN=TOK_TH_DAI, IG_ACCESS_TOKEN=TOK_IG, META_APP_SECRET=SECRET)
    _so_dai_han("threads", TOK_TH_DAI, TOK_TH_DAI, 50 * M.NGAY, 2 * M.NGAY)
    M.ghi_so({**M.doc_so(), "instagram": {"token": TOK_IG, "loai": "dai_han",
                                          "env": M._van_tay(TOK_IG), "lay_luc": int(time.time()),
                                          "het_han": int(time.time()) + 50 * M.NGAY}})
    _threads(mang)
    mang.tuyen["me"] = lambda p: ((200, {"id": "u1", "username": "hapas.vn"})
                                  if p["access_token"] == TOK_TH_DAI else
                                  (400, {"error": {"code": 190, "error_subcode": 463,
                                                   "message": "Session has expired; token "
                                                              + TOK_IG + " client_secret="
                                                              + SECRET}}))
    kq = K._handle({"kenh": ["threads", "instagram"]})
    d = json.loads(kq)
    assert d["per_kenh"]["instagram"]["trang_thai"] == "LỖI"
    assert "token hết hạn" in d["per_kenh"]["instagram"]["loi"]
    assert "chủ agent cần cấp lại" in d["per_kenh"]["instagram"]["loi"]
    assert d["per_kenh"]["threads"]["trang_thai"] == "OK", "kênh hỏng không kéo kênh khác"
    out = capsys.readouterr().out
    assert "[kenh_nha]" in out, "lỗi token phải được ghi log"
    for bi_mat in (TOK_IG, TOK_TH_DAI, SECRET):
        assert bi_mat not in kq and bi_mat not in out


def test_loi_mang_chua_url_co_token_bi_che(env, monkeypatch):
    import requests
    env(IG_ACCESS_TOKEN=TOK_IG)

    def hong(url, params, timeout):
        raise requests.ConnectionError(
            f"HTTPSConnectionPool: {url}?access_token={params['access_token']}")
    monkeypatch.setattr(M, "_http_get", hong)
    with pytest.raises(M.LoiKenh) as e:
        M.goi("instagram", "me", {}, TOK_IG)
    assert e.value.ma == "MANG" and TOK_IG not in str(e.value)


def test_che_token_la_theo_hinh_dang(env):
    la = "EAAunknownTokenNotInEnv0123456789abcdefg"
    s = M.che(f"x {la} y access_token=abc&client_secret=def input_token%3Dghi")
    assert la not in s and "abc" not in s and "def" not in s and "ghi" not in s


# ───────────────────────── policy + đăng ký ─────────────────────────
def test_policy_ghi_sheet_va_cong_tac_muon_quet_mxh(monkeypatch):
    gio = time.time()
    lsr_policy._nho.update(quyen={"reply", "write_data"}, luc=gio, nguon="test")
    assert lsr_policy._MUTATING_EXACT[K.TEN_TOOL] == "write_data"
    assert lsr_policy._CONG_TAC_LUI[K.TEN_TOOL] == "social_listen"
    lsr_policy._nho_nl.update(bat={"social_listen"}, luc=gio)
    assert lsr_policy.decide(K.TEN_TOOL, {}).allowed
    lsr_policy._nho_nl.update(bat={"soi_san"}, luc=gio)
    d = lsr_policy.decide(K.TEN_TOOL, {})
    assert not d.allowed and "theo công tắc 'social_listen'" in d.reason
    lsr_policy._nho.update(quyen={"reply"}, luc=gio)
    lsr_policy._nho_nl.update(bat={"social_listen", K.TEN_TOOL}, luc=gio)
    assert "write_data" in lsr_policy.decide(K.TEN_TOOL, {}).reason


def test_loi_dan_prompt_va_ky_nang():
    import pathlib
    goc = pathlib.Path(K.__file__).resolve().parent
    brain = (goc / "brain.py").read_text(encoding="utf-8")
    assert "import kenh_nha_tool" in brain and "`binh_luan_kenh_nha`" in brain
    assert '"binh_luan_kenh_nha":' in brain       # _TOOL_CAN_XET
    sk = (goc / "skills" / "comment-deep-dive.md").read_text(encoding="utf-8")
    assert "binh_luan_kenh_nha" in sk and "social_deep_dive" in sk
    assert "Chạy nhé?" in K.SCHEMA["description"] and "0 USD" in K.SCHEMA["description"]
