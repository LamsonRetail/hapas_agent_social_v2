"""Canh hai tool mới: `soi_tai_khoan` (brand đối thủ / KOC) và `soi_san` (Shopee).

Câu hỏi thật trong sổ audit mà trước đây Mark không làm được: "khảo sát thương hiệu
edoris, tactics truyền thông từ đầu tháng 9", KOC cho team Booking (từng ra số GIẢ LẬP),
"scout thị trường quà tặng 20.10". Dữ liệu giả giữ đúng hình dữ liệu thật đo 25/09/2026.
"""
from __future__ import annotations

import datetime
import json

import pytest

import account_tool as T
import apify_tool as A
import lenh_cung
import lsr_policy
import shopee_tool as S

GIO = datetime.datetime.now(datetime.timezone.utc)


def _iso(ngay_truoc: float) -> str:
    return (GIO - datetime.timedelta(days=ngay_truoc)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


TIKTOK = [
    {"authorMeta": {"name": "thybui.__", "nickName": "Thy", "fans": 1000, "heart": 5, "video": 2,
                    "verified": True},
     "createTimeISO": _iso(1), "playCount": 500, "diggCount": 40, "commentCount": 5,
     "shareCount": 5, "text": "hello #xuhuong @renzo", "webVideoUrl": "https://t/v/1",
     "hashtags": [{"name": "xuhuong"}], "musicMeta": {"musicName": "nhạc A"}},
    {"authorMeta": {"name": "thybui.__", "fans": 1000},
     "createTimeISO": _iso(3), "playCount": 300, "diggCount": 20, "commentCount": 0,
     "shareCount": 0, "text": "#hoptaccung Lancôme", "webVideoUrl": "https://t/v/2",
     "hashtags": [{"name": "hoptaccung"}], "musicMeta": {"musicName": "nhạc A"}},
    {"authorMeta": {"name": "thybui.__", "fans": 1000},                       # ngoài khoảng
     "createTimeISO": _iso(90), "playCount": 99999, "diggCount": 1, "commentCount": 1,
     "shareCount": 1, "text": "cũ", "webVideoUrl": "https://t/v/3", "hashtags": []},
]
FACEBOOK = [
    {"pageName": "EdorisVietNam", "facebookUrl": "https://www.facebook.com/EdorisVietNam",
     "time": _iso(1), "likes": 3821, "comments": 346, "shares": 422, "url": "https://fb/p/1",
     "text": "🔥[𝐇𝐎𝐓] 𝐅𝐀𝐍𝐒𝐈𝐆𝐍 | 𝐄𝐃𝐎𝐑𝐈𝐒 × 𝐐𝐔𝐀𝐍𝐆 𝐇𝐔̀𝐍𝐆 𝐌𝐀𝐒𝐓𝐄𝐑𝐃", "media": [{"__typename": "Photo"}],
     "paidPartnership": False, "collaborators": []},
    {"pageName": "EdorisVietNam", "time": _iso(6), "likes": 9, "comments": None, "shares": 0,
     "url": "https://fb/reel/2", "text": "Phong cách tinh tế", "viewsCount": 6337,
     "media": [{"__typename": "Video"}]},
]
INSTAGRAM = [{"username": "edoris.vn", "fullName": "EDORIS", "followersCount": 1820,
              "postsCount": 151, "verified": False, "url": "https://www.instagram.com/edoris.vn/",
              "latestPosts": [{"timestamp": _iso(1), "type": "Image", "likesCount": 13,
                               "commentsCount": 1, "caption": "x", "url": "https://ig/p/1",
                               "hashtags": ["edoris"], "mentions": ["quanghung"]}] * 3}]
# Hình dữ liệu thật của zen-studio~shopee-product-scraper: KHÔNG có số đã bán (mọi trường
# `sold*` đều None), thứ tự trả về là thứ hạng bán chạy của Shopee khi sort=best_selling.
SHOPEE = [
    {"name": "Túi xách nữ đeo vai", "price": 169000, "priceBeforeDiscount": 250000,
     "discountPercent": 32, "sold": None, "historicalSold": None, "rating": 4.9,
     "ratingCount": 300, "likedCount": 50, "shopName": "VINICHY", "brand": "VINICHY",
     "shopLocation": "Hà Nội", "isOfficialShop": True, "url": "https://s/1"},
    {"name": "Túi tote công sở", "price": 89000, "rating": 4.8, "ratingCount": 5000,
     "shopName": "Uyên store", "url": "https://s/2"},
    {"name": "Túi da cao cấp", "price": 1_250_000, "rating": 5, "ratingCount": 40,
     "shopName": "VINICHY", "brand": "VINICHY", "url": "https://s/3"},
]


@pytest.fixture
def gia(monkeypatch):
    goi = []

    def call(actor, payload, limit, mem=None):
        goi.append((actor, payload))
        return {T._ACTOR["tiktok"]: TIKTOK, T._ACTOR["facebook"]: FACEBOOK,
                T._ACTOR["instagram"]: INSTAGRAM, S.ACTOR: SHOPEE}[actor]

    monkeypatch.setattr(A, "_call", call)
    monkeypatch.setattr(A, "_tran", lambda: (100, 0.3))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 0.1, "so_run": 1, "cham_tran": 0, "dang_chay": 0})
    for m in (T, S):
        monkeypatch.setattr(m.chi_phi_tool, "ghi", lambda **k: {})
        monkeypatch.setattr(m.memory_store, "get_current_sender", lambda: None)
    dong = []
    monkeypatch.setattr(A, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(A, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(A, "_write_values", lambda tok, sid, rows: dong.extend(rows))
    return goi, dong


# ───────────────────────────── soi_tai_khoan ─────────────────────────────

@pytest.mark.parametrize("vao, ra", [
    ("https://www.tiktok.com/@hapas.official?lang=vi-VN", ("tiktok", "hapas.official")),
    ("https://www.facebook.com/EdorisVietNam", ("facebook", "https://www.facebook.com/EdorisVietNam")),
    ("https://www.instagram.com/edoris.vn/", ("instagram", "edoris.vn")),
    ("@thybui.__", ("tiktok", "thybui.__")),
    ("câu gì đó có dấu cách", None),
])
def test_nhan_dien_link_va_ten(vao, ra):
    assert T._nhan_dien(vao, "tiktok") == ra


def test_ten_tran_theo_nen_tang_duoc_chi_dinh():
    assert T._nhan_dien("EdorisVietNam", "facebook") == (
        "facebook", "https://www.facebook.com/EdorisVietNam")


def test_tiktok_khong_dung_bo_loc_ngay_cua_actor(gia):
    """Lọc ngày của actor làm @hapas.official trả 'no videos' — phải tự lọc."""
    goi, _ = gia
    T._handle({"tai_khoan": ["@thybui.__"]})
    p = [p for a, p in goi if a == T._ACTOR["tiktok"]][0]
    assert "oldestPostDateUnified" not in p and p["profileSorting"] == "latest"


def test_so_lieu_koc_tinh_dung_va_bo_bai_ngoai_khoang(gia):
    kq = json.loads(T._handle({"tai_khoan": ["@thybui.__"]}))
    tk = kq["tai_khoan"][0]
    assert tk["so_bai_trong_khoang"] == 2 and tk["so_bai_da_doc"] == 3, "bài 90 ngày trước bị loại"
    assert tk["view_trung_vi"] == 400
    assert tk["view_trung_vi_tren_follower"] == 0.4
    assert tk["ti_le_tuong_tac_tren_view"] == round(70 / 800, 4)
    assert tk["bai_hop_tac_hoac_quang_cao"] == 1, "#hoptaccung"
    assert tk["am_thanh_hay_dung"] == ["nhạc A"] and "renzo" in tk["nhac_toi_nhieu"]


def test_chu_in_dam_kieu_unicode_van_nhan_ra_hop_tac(gia):
    """Caption Edoris dùng 𝐄𝐃𝐎𝐑𝐈𝐒 × 𝐐𝐔𝐀𝐍𝐆 — không chuẩn hoá thì không khớp."""
    kq = json.loads(T._handle({"tai_khoan": ["https://www.facebook.com/EdorisVietNam"]}))
    tk = kq["tai_khoan"][0]
    assert tk["bai_hop_tac_hoac_quang_cao"] == 1
    assert tk["ho_so"]["followers"] is None, "Facebook không trả số người theo dõi trang"
    assert tk["bai_noi_bat"][0]["tuong_tac"] == 3821 + 346 + 422


def test_chu_thuong_x_khong_bi_tinh_hop_tac():
    assert not T._la_hop_tac({"noi_dung": "mua 2 x cái túi này nha"})
    assert T._la_hop_tac({"noi_dung": "MASTERD x EDORIS"})


def test_instagram_co_follower_va_ti_le_tren_follower(gia):
    kq = json.loads(T._handle({"tai_khoan": ["https://www.instagram.com/edoris.vn/"]}))
    tk = kq["tai_khoan"][0]
    assert tk["ho_so"]["followers"] == 1820
    assert tk["ti_le_tuong_tac_tren_follower"] == round(14 / 1820, 4)


def test_tai_khoan_khong_doc_duoc_thi_bao_ro(gia, monkeypatch):
    monkeypatch.setattr(A, "_call", lambda *a, **k: [
        {"authorMeta": {"name": "hapas.official", "fans": 623500},
         "note": "Profile has no videos (or is behind a login wall)"}])
    kq = json.loads(T._handle({"tai_khoan": ["@hapas.official"]}))
    tk = kq["tai_khoan"][0]
    assert tk["so_bai_trong_khoang"] == 0 and "login wall" in tk["ghi_chu"]


def test_so_bai_bi_kep_theo_tran(gia):
    goi, _ = gia
    T._handle({"tai_khoan": ["@thybui.__"], "so_bai": 5000})
    assert [p for a, p in goi if a == T._ACTOR["tiktok"]][0]["resultsPerPage"] == 100


def test_sheet_chi_ghi_bai_trong_khoang(gia):
    _, dong = gia
    T._handle({"tai_khoan": ["@thybui.__"]})
    assert len(dong) == 1 + 2 and dong[0][0] == "Nền tảng"


# ───────────────────────────── soi_san ─────────────────────────────

def test_shopee_tong_hop_gia_va_thu_hang_ban_chay(gia):
    kq = json.loads(S._handle({"tu_khoa": ["túi xách nữ"]}))
    th = kq["tong_hop"]
    assert th["gia"]["thap_nhat"] == 89000 and th["gia"]["cao_nhat"] == 1_250_000
    assert [s["hang"] for s in th["dau_bang"]] == [1, 2, 3], "giữ đúng thứ hạng Shopee trả"
    assert th["dau_bang"][0]["chinh_hang"] is True
    assert th["nhieu_danh_gia_nhat"][0]["ten"] == "Túi tote công sở"
    assert th["phan_bo_gia"] == {"dưới 100k": 1, "100k–300k": 1, "1 triệu–2 triệu": 1}
    assert th["shop_noi_bat"][0]["shop"] == "Uyên store"
    assert kq["khong_co_so_da_ban"] is True and kq["sheet_url"] == "https://sheet"


def test_shopee_mac_dinh_xep_theo_lien_quan(gia):
    """Xếp theo bán chạy lạc đề nặng (quà 20/10 ra khăn tắm) — chỉ dùng khi được hỏi."""
    goi, _ = gia
    S._handle({"tu_khoa": ["túi"]})
    S._handle({"tu_khoa": ["túi"], "xep_theo": "ban_chay"})
    p = [p for a, p in goi if a == S.ACTOR]
    assert p[0]["sort"] == "relevance" and p[0]["region"] == "VN"
    assert p[1]["sort"] == "best_selling"


@pytest.mark.parametrize("ten, khop", [
    ("[Quà Tặng 20/10] Set Thiệp Gài Nơ", True),
    ("Set quà tặng cho nữ cốc sứ nến thơm", True),
    ("Khăn Tắm, Khăn Gội Royal Towel Sợi Cotton", False),
])
def test_khop_tu_khoa_bo_dau_bo_so(ten, khop):
    assert S._khop(ten, ["quà tặng 20/10"]) is khop


def test_tong_hop_chi_tinh_hang_khop_va_bao_lac_de(gia, monkeypatch):
    hang = [dict(SHOPEE[0], name=f"Túi xách nữ mẫu {i}", price=100_000 + i) for i in range(5)]
    hang.append(dict(SHOPEE[0], name="Khăn tắm cotton", price=5_000_000))
    monkeypatch.setattr(A, "_call", lambda *a, **k: hang)
    kq = json.loads(S._handle({"tu_khoa": ["túi xách nữ"]}))
    assert kq["so_sp_khop_tu_khoa"] == 5 and kq["vi_du_lac_de"] == ["Khăn tắm cotton"]
    assert kq["tong_hop"]["gia"]["cao_nhat"] < 5_000_000, "hàng lạc đề không được kéo giá lên"
    assert kq["canh_bao_lac_de"] is None


def test_it_hang_khop_thi_canh_bao(gia):
    kq = json.loads(S._handle({"tu_khoa": ["quà tặng 20/10"]}))
    assert kq["so_sp_khop_tu_khoa"] == 0 and "lạc đề" in kq["canh_bao_lac_de"]


def test_ghi_sheet_tu_tinh_so_cot(monkeypatch):
    """Cố định A:L (12 cột) làm Sheet 13+ cột hỏng: 'columns of value:13 > range'."""
    goi = []
    monkeypatch.setattr(A.lark, "call", lambda m, path, **k: goi.append(k["body"]))
    A._write_values("tok", "s1", [["x"] * 14, ["y"] * 3])
    assert goi[0]["valueRanges"][0]["range"] == "s1!A1:N2"
    assert [A._cot(n) for n in (1, 12, 26, 27)] == ["A", "L", "Z", "AA"]


def test_shopee_co_so_san_pham_theo_tran_chi_phi(gia):
    goi, _ = gia
    kq = json.loads(S._handle({"tu_khoa": ["túi"], "so_san_pham": 100}))
    p = [p for a, p in goi if a == S.ACTOR][0]
    assert p["maxItems"] == 59, "(0,3 - 0,005) / 0,005 = 59, không phải 58 vì lỗi làm tròn"
    assert "59" in kq["bi_co_theo_tran"] and "console" in kq["bi_co_theo_tran"]


def test_shopee_tran_duoi_toi_thieu_thi_bao_de_hieu(gia, monkeypatch):
    def tu_choi(*a, **k):
        raise RuntimeError('HTTP 400: {"error":{"type":"max-total-charge-usd-below-minimum"}}')
    monkeypatch.setattr(A, "_call", tu_choi)
    kq = S._handle({"tu_khoa": ["túi"]})
    assert "thấp hơn mức tối thiểu" in kq and "console" in kq


def test_tan_suat_chi_tinh_tren_doan_da_doc(gia, monkeypatch):
    """Đọc kín 5 bài (mức tối thiểu) mà bài cũ nhất vẫn trong khoảng → không chia cho cả
    30 ngày. Bản cũ chia cả khoảng nên mọi tài khoản ra đúng "2,8 bài/tuần"."""
    nam = [dict(TIKTOK[0], createTimeISO=_iso(d), webVideoUrl=f"https://t/v/{d}")
           for d in range(1, 6)]
    monkeypatch.setattr(A, "_call", lambda *a, **k: nam)
    kq = json.loads(T._handle({"tai_khoan": ["@thybui.__"], "so_bai": 5}))
    tk = kq["tai_khoan"][0]
    assert "chua_phu_het_khoang" in tk and "Tăng `so_bai`" in tk["chua_phu_het_khoang"]
    assert tk["bai_moi_tuan"] == round(5 / 6 * 7, 1), "5 bài trong 6 ngày đã đọc, không phải 31"


def test_doc_du_khoang_thi_khong_bao_chua_phu(gia):
    kq = json.loads(T._handle({"tai_khoan": ["@thybui.__"], "so_bai": 30}))
    assert "chua_phu_het_khoang" not in kq["tai_khoan"][0]


def test_chi_phi_hoi_lai_khi_apify_con_bao_dang_chay(monkeypatch):
    lan = []

    class R:
        def raise_for_status(self):
            pass

        def json(self):
            st = "RUNNING" if not lan[1:] else "SUCCEEDED"
            return {"data": {"items": [{"startedAt": _iso(0), "status": st,
                                        "usageTotalUsd": 0.05 if st == "RUNNING" else 0.08}]}}

    monkeypatch.setenv("APIFY_TOKEN", "tok")
    monkeypatch.setattr(A, "_tran", lambda: (100, 0.3))
    monkeypatch.setattr(A.time, "sleep", lambda s: None)
    monkeypatch.setattr(A.requests, "get", lambda *a, **k: lan.append(1) or R())
    thuc = A._chi_phi_thuc(["x~y"], A._to_vn(_iso(1)))
    assert thuc == {"usd": 0.08, "so_run": 1, "cham_tran": 0, "dang_chay": 0,
                    "on_dinh": True}


def test_shopee_thieu_tu_khoa():
    assert "Thiếu" in S._handle({})


# ───────────────────────────── quản trị ─────────────────────────────

@pytest.mark.parametrize("tool, lenh", [("soi_tai_khoan", "/profile"), ("soi_san", "/shop")])
def test_hai_tool_moi_di_dung_luong_quan_tri(tool, lenh):
    assert lsr_policy._MUTATING_EXACT[tool] == "write_data", "xuất Sheet là ghi ra ngoài"
    assert tool in lsr_policy._TOOL_CO_CONG_TAC, "phải tắt được trên console"
    assert lenh_cung.BANG_LENH[lenh] == tool
