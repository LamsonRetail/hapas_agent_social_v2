"""Giữ KHÔNG có phán AI phải có tín hiệu brand (soát 27/10/2026, `theo_doi.co_tin_hieu_brand`).

Kho 27/10/2026: từ khoá dự án hapas gồm khẩu hiệu "yêu từ điều nhỏ nhất"; `_khop_tu_khoa` coi từ
khoá nhiều chữ là khớp khi ĐỦ mọi chữ ở bất kỳ đâu — video của kênh "Tử Vi Vô Chính Diệu" khớp (yêu,
tự, nhỏ, nhất trong nội dung; "Diệu" ở tên kênh). AI không phán thì bản trước giữ theo luật → 109
bài không có chữ "hapas" (773 bình luận). Nay bài AI không phán chỉ được giữ khi gọi tên brand
(`ten_brand`: tên, mã, hashtag dự án / khẩu hiệu ở dạng VIẾT LIỀN) hoặc chủ bài là kênh nhà. Kho giả,
AI giả."""
from __future__ import annotations

import datetime

import pytest
from test_loc_seeding import KhoGia, _tk
from test_theo_doi import DU_AN as DU_AN_TD
from test_theo_doi import GiaKho, _hit, mo  # noqa: F401 — `mo` là fixture

import apify_tool as A
import kiem_do_phu as KDP
import lang_nghe_db as K
import theo_doi as T
import theo_doi_api as TDA

_VN = datetime.timezone(datetime.timedelta(hours=7))
LY = T.LY_DO_KHONG_NHAC_BRAND
DU_AN = {"ma": "hapas", "ten": "HAPAS", "tu_khoa": ["hapas", "túi hapas", "yêu từ điều nhỏ nhất"],
         "tu_loai_tru": [], "boi_canh": "HAPAS — túi xách Việt Nam", "thi_truong": "VN",
         "cau_hinh": {}, "hashtag": ["hapas", "yeutudieunhonhat", "lammoidieuviyeu",
                                     "quatang2010"]}
TU = DU_AN["tu_khoa"]
LUC = datetime.datetime.now(_VN) - datetime.timedelta(days=2)
TU_VI = ("Không giỏi nói lời yêu thương, nhưng chuyện lớn nhỏ trong nhà đều tự tay lo liệu… điểm "
         "cộng lớn nhất. #xuhuong #tuvi")


def _bai(i, user, text, kenh=None, hashtags=""):
    return ({"platform": "tiktok", "username": user, "kenh": kenh or user, "text": text,
             "hashtags": hashtags, "link": f"https://www.tiktok.com/@{user}/video/88{i}",
             "comments": 7, "views": 900, "likes": 1, "shares": 0, "__goc": {"id": f"88{i}"}},
            LUC)


def _tu_vi(i=1):
    return _bai(i, "tuvi.vochinhdieu", TU_VI, kenh="Tử Vi Vô Chính Diệu", hashtags="xuhuong tuvi")


def _so() -> dict:
    return {k: v[0] for k, v in TDA.doc_loai("hapas", TDA.dau_loai(DU_AN, TU),
                                             LUC - datetime.timedelta(days=5)).items()}


@pytest.fixture(autouse=True)
def khong_lich(monkeypatch):
    monkeypatch.setattr(T, "khau_hieu_chien_dich", lambda ma, bay_gio: (None, []))


@pytest.fixture
def ai(monkeypatch):
    """AI giả: `phan[username]` = phán của bài (thiếu = không phán — hết giờ / bỏ qua)."""
    goi: list[list[str]] = []
    phan: dict[str, tuple] = {}

    def phan_xu(rows, *a, **k):
        goi.append([d["username"] for d, _ in rows])
        return ({i: phan[d["username"]] for i, (d, _) in enumerate(rows) if d["username"] in phan},
                {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"})
    monkeypatch.setattr(A, "_phan_xu_ai", phan_xu)
    return goi, phan


# ───────────────────────────── luật thuần ─────────────────────────────
def test_khop_tho_rai_rac_nhung_khong_co_tin_hieu_brand():
    cong = T.cau_hinh_hashtag_brand(DU_AN)
    ten = T.ten_brand(DU_AN, cong=cong)
    assert "yeutudieunhonhat" in ten and "quatang2010" not in ten
    d = _tu_vi()[0]
    assert A._khop_tu_khoa(d, TU), "nguyên nhân: đủ chữ ở bất kỳ đâu (cả tên kênh)"
    assert not T.co_tin_hieu_brand(d, cong, ten)
    # Dạng viết liền chỉ khớp đúng cụm LIỀN NHAU (`_ghep_lien`).
    for text, co in (("Yêu từ điều nhỏ nhất ❤️ quà 20/10", True),
                     ("Quà 20/10 #yeutudieunhonhat", True),
                     ("Yêu bản thân từ những điều nhỏ nhất", False),
                     ("Nhất định phải yêu từ nhỏ, điều đó", False),
                     ("Túi HAPAS xinh quá", True),
                     # Tag dự án do NGƯỜI đặt (`du_an.hashtag`) là tên brand — câu đúng cụm "Làm
                     # mọi điều vì YÊU" được giữ; muốn bỏ thì gỡ tag khỏi danh sách.
                     ("Làm mọi điều vì YÊU 💕", True)):
        assert T.co_tin_hieu_brand(_bai(2, "x", text)[0], cong, ten) is co, text
    # Kênh nhà; cổng brand tắt (dự án không có "tên brand" để đòi) → giữ như cũ.
    assert T.co_tin_hieu_brand(d, cong, ten, la_nha=lambda x: True)
    tat = T.cau_hinh_hashtag_brand({**DU_AN, "cau_hinh": {"hashtag_can_nhac_brand": False}})
    assert T.co_tin_hieu_brand(d, tat, ten)
    # `ten` dạng hàm (lười) — chỉ gọi khi tên + mã không đủ.
    goi = []
    assert T.co_tin_hieu_brand(_bai(3, "x", "hapas")[0], cong, lambda: goi.append(1) or ten)
    assert goi == []


# ───────────────────────────── lượt tìm theo từ khoá ─────────────────────────────
def test_ai_khong_phan_chi_giu_bai_co_tin_hieu_brand_khong_vao_so(monkeypatch, ai):
    goi, _ = ai
    kho = KhoGia([{"id": 1, "nen_tang": "tiktok", "dinh_danh": "hapas.official",
                   "loai": "kenh_nha"}])
    kho.cai(monkeypatch)
    hits = [_tu_vi(1),
            _bai(2, "kol_a", "Quà 20/10 #yeutudieunhonhat"),
            _bai(3, "khach_b", "Túi HAPAS yêu từ điều nhỏ nhất"),
            _bai(4, "hapas.official", "Yêu bản thân từ những điều nhỏ nhất"),
            _bai(5, "me_c", "Yêu bản thân từ những điều nhỏ nhất")]
    tk = _tk()
    T._tach_va_giu(DU_AN, 7, hits, TU, 1e12, tk)
    assert goi == [["tuvi.vochinhdieu", "kol_a", "khach_b", "hapas.official", "me_c"]]
    giu = {r["tai_khoan"]: r for rows in kho.ghi for r in rows}
    assert set(giu) == {"kol_a", "khach_b", "hapas.official"}
    assert {r["ly_do_giu"] for r in giu.values()} == {"khop_tu_khoa"}
    f = tk["pheu"]["tiktok"]
    assert f["khong_nhac_brand"] == 2 and f["giu"] == 3
    assert _so() == {}, "AI chưa xét (hết giờ / bỏ qua): không vào sổ — lượt sau AI xét lại"
    assert "AI không phán mà không nhắc brand 2" in T._cau_pheu("tiktok", f)
    # Lượt sau: bài cũ không bị sổ chặn, tới AI lại.
    T._tach_va_giu(DU_AN, 8, [_tu_vi(1)], TU, 1e12, _tk())
    assert goi[-1] == ["tuvi.vochinhdieu"]


def test_ai_khong_ro_vao_so_ly_do_moi_va_cau_hinh_moi_go_duoc(monkeypatch, ai):
    goi, phan = ai
    kho = KhoGia()
    kho.cai(monkeypatch)
    phan["tuvi.vochinhdieu"] = (True, "khong_ro", "")
    phan["kol_a"] = (True, "khong_ro", "")
    T._tach_va_giu(DU_AN, 7, [_tu_vi(1), _bai(2, "kol_a", "Túi HAPAS 20/10")], TU, 1e12, _tk())
    assert [r["tai_khoan"] for rows in kho.ghi for r in rows] == ["kol_a"]
    assert _so() == {"tiktok:881": LY}
    assert LY not in T.LY_DO_XET_LAI, "không xét lại vô điều kiện (gửi AI lại mỗi lượt)"
    # Gặp lại: sổ chặn, không tới AI.
    tk = _tk()
    T._tach_va_giu(DU_AN, 8, [_tu_vi(1)], TU, 1e12, tk)
    assert tk["pheu"]["tiktok"]["da_loai_truoc"] == 1 and len(goi) == 1
    # Chủ bài thành kênh nhà (hoặc thêm tên / tag) → sổ không chặn nữa: tới AI, AI không rõ → giữ.
    kho.nguon = [{"id": 2, "nen_tang": "tiktok", "dinh_danh": "tuvi.vochinhdieu",
                  "loai": "kenh_nha"}]
    tk = _tk()
    T._tach_va_giu(DU_AN, 9, [_tu_vi(1)], TU, 1e12, tk)
    assert goi[-1] == ["tuvi.vochinhdieu"] and tk["pheu"]["tiktok"]["xet_lai"] == 1
    assert kho.ghi[-1][0]["tai_khoan"] == "tuvi.vochinhdieu"


def test_bai_ai_giu_khong_doi(monkeypatch, ai):
    """Bài AI giữ (mã brand / ad / ugc…) không cần tín hiệu brand — vd Threads bàn "brand H"."""
    _, phan = ai
    kho = KhoGia()
    kho.cai(monkeypatch)
    phan["tuvi.vochinhdieu"] = (True, "ad", "")
    T._tach_va_giu(DU_AN, 7, [_tu_vi(1)], TU, 1e12, _tk())
    ((r,),) = kho.ghi
    assert r["ly_do_giu"] == "ad" and r["khop_tu_khoa"] is True, "cờ khớp thô giữ nguyên"


def test_con_chan_go_khi_them_ten_tag_hoac_tat_cong(monkeypatch, ai):
    """Lý do `khong_nhac_brand` không chặn mãi: thêm tên brand ("Mate Made") → bài tới AI lại, AI
    vẫn không rõ → giữ (giờ có tín hiệu brand). Thêm tag dự án / tắt cổng cũng gỡ."""
    goi, phan = ai
    kho = KhoGia()
    kho.cai(monkeypatch)
    mm = _bai(1, "shop_mm", "Mate Made — yêu bản thân từ những điều nhỏ nhất")
    phan["shop_mm"] = (True, "khong_ro", "")
    T._tach_va_giu(DU_AN, 7, [mm], TU, 1e12, _tk())
    assert _so() == {"tiktok:881": LY} and kho.ghi == []
    v = [LY, "x"]
    cong = T.cau_hinh_hashtag_brand(DU_AN)
    assert T._con_chan(v, mm[0], cong, T.ten_brand(DU_AN))
    tag = {**DU_AN, "hashtag": [*DU_AN["hashtag"], "matemade"]}
    assert not T._con_chan(v, mm[0], cong, T.ten_brand(tag))
    tat = T.cau_hinh_hashtag_brand({**DU_AN, "cau_hinh": {"hashtag_can_nhac_brand": False}})
    assert not T._con_chan(v, mm[0], tat, T.ten_brand(DU_AN))
    them = {**DU_AN, "cau_hinh": {"hashtag_can_nhac_brand": {"ten": ["Mate Made"]}}}
    tk = _tk()
    T._tach_va_giu(them, 8, [mm], TU, 1e12, tk)
    assert goi[-1] == ["shop_mm"] and tk["pheu"]["tiktok"]["xet_lai"] == 1
    assert kho.ghi[-1][0]["tai_khoan"] == "shop_mm"


def test_other_market_ghi_chu_vn_thi_giu_khac_vn_thi_loai(monkeypatch, ai):
    """Luật M2 như cũ: AI giữ mã other_market với ghi chú "VN" → giữ (mã other_market); ghi chú
    nước khác → loại, sổ `ai:other_market`."""
    _, phan = ai
    kho = KhoGia()
    kho.cai(monkeypatch)
    phan["hapas.vn2"] = (True, "other_market", "VN")
    phan["hapas.th"] = (True, "other_market", "TH")
    T._tach_va_giu(DU_AN, 7, [_bai(1, "hapas.vn2", "HAPAS chi nhánh"),
                              _bai(2, "hapas.th", "HAPAS Thailand")], TU, 1e12, _tk())
    assert [(r["tai_khoan"], r["ly_do_giu"]) for rows in kho.ghi for r in rows] == [
        ("hapas.vn2", "other_market")]
    assert _so() == {"tiktok:882": "ai:other_market"}
    assert T.other_market_ngoai_vn("other_market", " vn ") is False
    assert T.other_market_ngoai_vn("other_market", "") is True
    assert T.other_market_ngoai_vn("brand", "TH") is False


# ───────────────────────────── kiểm độ phủ ─────────────────────────────
def test_kiem_do_phu_bai_khop_rai_rac_khong_la_bai_nhac_brand(monkeypatch):
    """Soát M3: bài mẫu khớp khẩu hiệu rải rác mà không có tín hiệu brand không phải "bài nhắc
    brand" — không vào mẫu số, không thành bài sót, không đi lấp lỗ. Bài trong sổ với lý do mới mà
    nay có tín hiệu brand (thêm tên) là bài "xét lại" của phần lấp lỗ."""
    from test_kiem_do_phu import _aw

    import tiktok_api as TT
    monkeypatch.setattr(K, "khoa_da_co", lambda ma, khoa: set())
    monkeypatch.setattr(K, "nguon_cua_du_an", lambda ma: [])
    tu_pv = LUC - datetime.timedelta(days=10)
    TDA.ghi_loai("hapas", TDA.dau_loai(DU_AN, TU), [("tiktok:882", LY, LUC)], tu_pv)
    items = [(TT.video(_aw(881, "tuvi.vochinhdieu", TU_VI, LUC)), "@tim"),
             (TT.video(_aw(882, "shop_mm", "Mate Made — yêu từ điều nhỏ nhất", LUC)), "@tim")]
    them = {**DU_AN, "cau_hinh": {"hashtag_can_nhac_brand": {"ten": ["Mate Made"]}}}
    mau = KDP.danh_dau("hapas", items, them, TU, tu_pv, LUC + datetime.timedelta(hours=1),
                       lambda d: T._khoa_bai("tiktok", d["link"]))
    x = {m["khoa"]: (m["nhac"], m["da_loai"], m["xet_lai"]) for m in mau}
    assert x == {"tiktok:881": (False, False, False), "tiktok:882": (True, True, True)}
    so = KDP.tinh_do_phu(mau)
    assert (so["so_nhac"], so["so_sot"]) == (0, 0)
    assert KDP.bai_sot(mau, TU, set(), LUC) == []


def test_kiem_do_phu_lap_lo_khong_dua_bai_khop_rai_rac_vao_pheu(mo):  # noqa: F811
    """Cả lượt kiểm độ phủ (TikTok giả): video "Tử Vi" trong danh sách bài của một nhà sáng tạo khớp
    khẩu hiệu — không tính là bài nhắc brand, không thành bài sót, không đi lấp lỗ (không tới
    AI, không vào kho), không đẩy tác giả thành đề xuất."""
    import test_kiem_do_phu as TK

    import tiktok_api as TT
    mo.setattr(T, "_kiem_do_phu", TK._KIEM_THAT)
    mo.setattr(TT, "dung_api", lambda viec: True)
    mo.setattr(T, "khau_hieu_chien_dich", lambda ma, bay_gio: (None, []))
    kho = TK.KhoDp(mo)
    kho.da_co = {"tiktok:70000002"}

    mo.setattr(K, "khoa_da_co", lambda ma, khoa: {k for k in khoa if k in kho.da_co | {
        r["khoa"] for _, rows in kho.bai for r in rows}})
    goi_ai: list = []
    mo.setattr(A, "_phan_xu_ai", lambda rows, *a, **k: (
        goi_ai.append([d["username"] for d, _ in rows]),
        ({}, {"_sac_thai": {}, "_chu_de": {}, "trang_thai": "đã chạy"}))[1])
    goc = TK._tra_mau(datetime.datetime.now(_VN) - datetime.timedelta(days=15))

    def tra(p):
        r = goc(p)
        if not any(k in p for k in ("searchHashtags_keyword", "challengePosts_cid",
                                    "profile_username")):
            r = {**r, "aweme_list": [*r["aweme_list"], TK._aw(
                70000009, "tuvi.vochinhdieu", TU_VI, TK.BAY - datetime.timedelta(days=1), bl=900)]}
        return r
    TK.GiaApi(mo, tra)
    du_an = {**TK.DU_AN, "tu_khoa": ["hapas", "yêu từ điều nhỏ nhất"]}
    kq = TK._chay_dp(TK.GiaViec({}, []), du_an)
    (dong,) = kho.dong
    assert [s["khoa"] for s in dong["bai_sot"]] == ["tiktok:70000001"]
    assert (kq["so"]["so_nhac"], kq["so"]["so_sot"]) == (2, 1)
    assert [r["khoa"] for _, rows in kho.bai for r in rows] == ["tiktok:70000001"]
    assert all("tuvi.vochinhdieu" not in g for g in goi_ai), "không gửi AI"
    assert all(x["dinh_danh"] != "tuvi.vochinhdieu" for x in dong["hanh_dong"]["de_xuat"])


# ───────────────────────────── social_listen → kho ─────────────────────────────
@pytest.mark.usefixtures("mo")
def test_luu_tu_khoa_bai_giu_theo_luat_cung_can_brand_va_vn_bo_other_market(monkeypatch):
    kho = GiaKho(du_an={"hapas": {**DU_AN_TD, **DU_AN}}).cai(monkeypatch)
    ngay = datetime.datetime.now(_VN) - datetime.timedelta(days=1)
    tu_vi = {**_tu_vi(1)[0], "_khop": True, "_sac_thai": None, "_chu_de": None}
    ad = {**_tu_vi(2)[0], "username": "brand.h", "_khop": True, "_ma_ai": "ad",
          "_sac_thai": None, "_chu_de": None}
    thai = {**_bai(3, "hapas.th", "HAPAS Thailand ของขวัญ")[0], "_khop": True,
            "_ma_ai": "other_market", "_sac_thai": None, "_chu_de": None}
    ban = T._ban_sao_tu_khoa([(tu_vi, ngay), (ad, ngay), (thai, ngay),
                              _hit("tiktok", "me4con", 9)])
    kq = T.luu_tu_khoa(["hapas"], ban)
    (_, luot, _, rows), = kho.bai
    assert kq["hapas"][0] == 2
    assert sorted(r["tai_khoan"] for r in rows) == ["brand.h", "me4con"]
    ghi_chu = kho.luot[luot]["ghi_chu"]
    assert "bỏ 1 bài AI không phán mà không nhắc brand" in ghi_chu
    assert "bỏ 1 bài AI xếp thị trường khác" in ghi_chu


@pytest.mark.usefixtures("mo")
def test_luu_tu_khoa_kenh_nha_tag_feed_va_other_market_vn(monkeypatch):
    """Bài giữ theo luật của kênh nhà, bài chỉ có tín hiệu brand ở TAG FEED (Instagram từ feed
    #yeutudieunhonhat — tag dự án) được ghi; other_market mà ghi chú AI là "VN" được ghi như
    `_giu_tu_khoa`, ghi chú nước khác thì bỏ."""
    from test_theo_doi import _nguon
    kho = GiaKho(du_an={"hapas": {**DU_AN_TD, **DU_AN}},
                 nguon=[_nguon(1, "tiktok", "nha_mau", "kenh_nha")]).cai(monkeypatch)
    # Kho giả của test_theo_doi không trả `loai` — kho thật có (`nguon_cua_du_an`).
    monkeypatch.setattr(K, "nguon_cua_du_an", lambda ma: kho.nguon)
    ngay = datetime.datetime.now(_VN) - datetime.timedelta(days=1)
    chung = {"_khop": True, "_sac_thai": None, "_chu_de": None}
    nha = {**_bai(1, "nha_mau", "Yêu bản thân từ những điều nhỏ nhất")[0], **chung}
    ig = {"platform": "instagram", "kenh": "Shop Quà", "username": "shop.qua", "followers": 0,
          "views": 0, "likes": 1, "comments": 0, "shares": 0, "hashtags": "", **chung,
          "text": "Quà 20/10 cho mẹ", "link": "https://www.instagram.com/p/Q9/",
          "__goc": {"id": "q9",
                    "inputUrl": "https://www.instagram.com/explore/tags/yeutudieunhonhat"}}
    vn = {**_bai(3, "hapas.vn2", "HAPAS chi nhánh")[0], **chung, "_ma_ai": "other_market",
          "_ghi_ai": "VN"}
    th = {**_bai(4, "hapas.th", "HAPAS Thailand")[0], **chung, "_ma_ai": "other_market",
          "_ghi_ai": "TH"}
    ban = T._ban_sao_tu_khoa([(nha, ngay), (ig, ngay), (vn, ngay), (th, ngay)])
    assert ban[1][0]["_tag_feed"] == "#yeutudieunhonhat" and ban[2][0]["_ghi_ai"] == "VN"
    T.luu_tu_khoa(["hapas"], ban)
    (_, luot, _, rows), = kho.bai
    assert sorted(r["tai_khoan"] for r in rows) == ["hapas.vn2", "nha_mau", "shop.qua"]
    assert "bỏ 1 bài AI xếp thị trường khác" in kho.luot[luot]["ghi_chu"]
    assert "không nhắc brand" not in kho.luot[luot]["ghi_chu"]
