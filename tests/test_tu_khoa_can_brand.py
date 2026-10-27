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


def test_kiem_do_phu_dua_bai_ly_do_moi_qua_pheu_xet_lai(monkeypatch):
    """Bài trong sổ với lý do mới là bài "xét lại" của phần lấp lỗ (`_con_chan` quyết theo cấu
    hình hiện hành — vẫn không nhắc brand thì vẫn chặn, không tới AI)."""
    from test_kiem_do_phu import _aw

    import lang_nghe_db as K
    import tiktok_api as TT
    monkeypatch.setattr(K, "khoa_da_co", lambda ma, khoa: set())
    tu_pv = LUC - datetime.timedelta(days=10)
    TDA.ghi_loai("hapas", TDA.dau_loai(DU_AN, TU), [("tiktok:881", LY, LUC)], tu_pv)
    items = [(TT.video(_aw(881, "tuvi.vochinhdieu", TU_VI, LUC)), "@tim")]
    (x,) = KDP.danh_dau("hapas", items, DU_AN, TU, tu_pv, LUC + datetime.timedelta(hours=1),
                        lambda d: T._khoa_bai("tiktok", d["link"]))
    assert x["nhac"] and x["da_loai"] and x["xet_lai"]


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
