"""Canh phần soi sản phẩm từ link Shopee / TikTok Shop (`san_link.py` qua tool `soi_san`).

Dữ liệu giả giữ đúng hình dữ liệu thật đo 25/09/2026: đánh giá Shopee (zen-studio) có
`ratingStar`, `variations`, `isRepeatPurchase`, `shopReply`; sản phẩm TikTok Shop (pro100chok)
có `exactSoldCount`, `ratingsBreakdown`, `reviews` với `date` tính bằng mili-giây.
"""
from __future__ import annotations

import json

import pytest

import apify_tool as A
import san_link as L
import shopee_tool as S

SP_URL = "https://shopee.vn/Hop-Qua-Tang-Kep-Toc-Nu-NHA-CU-i.59009982.25022958529"
TT_URL = "https://shop.tiktok.com/vn/pdp/tui-xach-nu-deo-cheo/1731382848795347431"

DG_SHOPEE = [
    {"reviewId": "r1", "itemId": "25022958529", "ratingStar": 5, "comment": "Rất ưng, gói quà đẹp lắm luôn nha shop ơi",
     "createdAt": "2026-08-31T08:24:01+00:00", "variations": [{"name": "Hộp #224"}],
     "isRepeatPurchase": True, "shopReply": {"comment": "Cảm ơn ạ"}, "images": ["x"]},
    {"reviewId": "r2", "itemId": "25022958529", "ratingStar": 2, "comment": "Kẹp gãy sau 2 ngày",
     "createdAt": "2026-02-04T06:16:12+00:00", "variations": [{"name": "Hộp #224"}],
     "isRepeatPurchase": False, "shopReply": None, "images": []},
    {"_warning": "temporarily unavailable"},
]
TIM_SHOPEE = [{"itemId": 25022958529, "name": "Hộp Quà Tặng Kẹp Tóc Nữ NHÀ CÚ", "price": 19900,
               "priceBeforeDiscount": 27000, "discountPercent": 34, "rating": 4.9,
               "ratingCount": 5947, "likedCount": 2782, "shopName": "Nhà Cú",
               "isOfficialShop": False},
              {"itemId": 1, "name": "Sản phẩm khác", "price": 1}]
# Hình dữ liệu thật của xtracto~shopee-product-detail cho VN: có `sold`, `shop`; `price` sai.
CT_SHOPEE = [{"item_id": 25022958529, "title": "Hộp Quà", "price": 99000, "sold": 92,
              "shop": {"name": "Nhà Cú", "rating_star": 4.484663, "item_count": 17,
                       "follower_count": 7, "is_shopee_verified": False}}]
TTS = [{"productId": "1731382848795347431", "title": "Túi xách nữ đeo chéo", "currentPrice": "93911",
        "maxPrice": "112931", "originalPrice": "101044", "discountPercent": "7%",
        "exactSoldCount": "128", "salesVolume": "128", "rating": "3.7", "totalReviews": "7",
        "ratingsBreakdown": {"stars": {"1": 2, "4": 1, "5": 4}}, "sellerName": "Trần Thùy Lâmm",
        "shopTotalSold": "2470", "shopRating": "3.4", "variants": [{}, {}],
        "reviews": [{"rating": 5, "text": "Oke", "date": "1770523649365",
                     "isVerifiedPurchase": True, "variant": "163 - TRẮNG"},
                    {"rating": 1, "text": "Da bong tróc", "date": "1749796755239",
                     "isVerifiedPurchase": True, "variant": "163 - XANH"}]}]


@pytest.fixture
def gia(monkeypatch):
    goi = []

    def call(actor, payload, limit, mem=None):
        goi.append((actor, payload))
        return {L.ACTOR_DG_SHOPEE: DG_SHOPEE, L.ACTOR_TIM_SHOPEE: TIM_SHOPEE,
                L.ACTOR_CT_SHOPEE: CT_SHOPEE, L.ACTOR_TTS: TTS}[actor]

    monkeypatch.setattr(A, "_call", call)
    monkeypatch.setattr(A, "_tran", lambda: (100, 0.3))
    monkeypatch.setattr(A, "_chi_phi_thuc", lambda *a, **k: {
        "usd": 0.2, "so_run": 3, "cham_tran": 0, "dang_chay": 0})
    monkeypatch.setattr(S.chi_phi_tool, "ghi", lambda **k: {})
    monkeypatch.setattr(S.memory_store, "get_current_sender", lambda: None)
    dong = []
    monkeypatch.setattr(A, "_create_sheet", lambda title: ("tok", "https://sheet"))
    monkeypatch.setattr(A, "_first_sheet_id", lambda tok: "s1")
    monkeypatch.setattr(A, "_write_values", lambda tok, sid, rows: dong.extend(rows))
    # Sheet nhiều tab: tab 2–4 thêm bằng sheets_batch_update — giả luôn, đừng gọi Lark thật.
    import lark_client
    monkeypatch.setattr(lark_client, "call", lambda m, path, **k: {"data": {"replies": [{}] + [
        {"addSheet": {"properties": {"sheetId": f"s{i}"}}} for i in range(2, 5)]}})
    return goi, dong


@pytest.mark.parametrize("u, san, id_", [
    (SP_URL, "shopee", "25022958529"),
    ("https://shopee.vn/product/59009982/25022958529", "shopee", "25022958529"),
    (TT_URL, "tiktok_shop", "1731382848795347431"),
    ("https://www.tiktok.com/view/product/1731382848795347431?region=VN", "tiktok_shop",
     "1731382848795347431"),
])
def test_nhan_dien_link(u, san, id_):
    x = L.nhan_dien(u)
    assert x["san"] == san and (x.get("item_id") or x.get("product_id")) == id_


def test_link_khong_phai_san_pham():
    assert L.nhan_dien("https://hapas.vn/tui-xach") is None


def test_link_chia_se_tiktok_dung_lai_dang_actor_nhan():
    x = L.nhan_dien("https://www.tiktok.com/view/product/1731382848795347431?region=VN")
    assert "/pdp/" in x["url"] and "?" not in x["url"]


def test_link_rut_gon_duoc_mo_ra(monkeypatch):
    class R:
        url = TT_URL
    monkeypatch.setattr(L.requests, "get", lambda *a, **k: R())
    assert L.nhan_dien("https://vt.tiktok.com/ZSabc123/")["product_id"] == "1731382848795347431"


def test_soi_hai_san_cung_luc(gia):
    goi, dong = gia
    kq = json.loads(S._handle({"link": [SP_URL, TT_URL]}))
    sp, tt = kq["san_pham"]
    assert sp["san"] == "Shopee" and sp["thong_tin"]["gia_tu"] == 19900, "giá lấy qua tìm theo tên"
    assert sp["chua_lay_duoc_gia"] is None
    t = sp["thong_tin"]
    assert t["da_ban"] == 92 and t["shop_follower"] == 7 and t["shop_so_san_pham"] == 17
    assert t["gia_tu"] == 19900, "giá lấy từ tìm kiếm, KHÔNG lấy price 99.000 sai của xtracto"
    assert "số đã bán" not in t["khong_co"] and "giá sau voucher" in t["khong_co"]
    d = sp["binh_luan"]
    assert d["so_danh_gia_da_doc"] == 2, "dòng _warning không được tính là đánh giá"
    assert d["ti_le_mua_lai"] == 0.5 and d["ti_le_shop_tra_loi"] == 0.5
    assert d["danh_gia_xau"] == ["2★ Kẹp gãy sau 2 ngày"]
    assert tt["thong_tin"]["da_ban"] == 128 and tt["thong_tin"]["shop_tong_da_ban"] == 2470
    assert tt["thong_tin"]["phan_bo_sao_toan_bo"] == {"1": 2, "4": 1, "5": 4}
    assert tt["binh_luan"]["den_ngay"].endswith("2026"), "date mili-giây phải đổi đúng"
    assert kq["sheet_url"] == "https://sheet"
    tieu_de = [r for r in dong if r and r[0] == "Sàn"]
    assert [r[2] for r in tieu_de] == ["Danh mục", "Phân loại", "Mô tả", "Ngày"], "đủ 4 tab"
    assert "Bình luận" in dong[dong.index(tieu_de[-1])], "cột gọi là Bình luận, không phải Nội dung"
    p = [p for a, p in goi if a == L.ACTOR_TTS][0]
    assert p["scrapeType"] == "product" and p["region"] == "vn" and p["includeReviews"] is True


def test_link_khong_ten_van_lay_duoc_gia_qua_danh_sach_shop(gia):
    """Link rút gọn không có tên → bỏ bước tìm theo tên, tìm thẳng trong shop."""
    goi, _ = gia
    kq = json.loads(S._handle({"link": ["https://shopee.vn/product/59009982/25022958529"]}))
    assert kq["san_pham"][0]["thong_tin"]["gia_tu"] == 19900
    tim = [p for a, p in goi if a == L.ACTOR_TIM_SHOPEE]
    assert len(tim) == 1 and tim[0]["shopId"] == 59009982 and tim[0]["sort"] == "best_selling"


def test_ten_trong_link_truot_thi_tim_trong_shop(gia, monkeypatch):
    goi = []

    def call(actor, payload, limit, mem=None):
        goi.append(payload)
        return TIM_SHOPEE if "shopId" in payload else [{"itemId": 999, "name": "khác"}]
    monkeypatch.setattr(A, "_call", call)
    assert L._gia_shopee(L.nhan_dien(SP_URL))["gia_tu"] == 19900
    assert "searchTerms" in goi[0] and "shopId" in goi[1], "tên trước, shop sau"


def test_chi_mot_luot_danh_gia_shopee_moi_lan_soi(gia):
    """3 lượt đánh giá song song cho cùng sản phẩm làm Shopee chặn 4 lượt liền (đo 25/09)."""
    goi, _ = gia
    S._handle({"link": [SP_URL]})
    dg = [p for a, p in goi if a == L.ACTOR_DG_SHOPEE]
    assert len(dg) == 1 and dg[0]["starFilter"] == "all"
    assert dg[0]["maxReviewsPerProduct"] == L._DG_MAC_DINH == 50
    assert dg[0]["startUrls"][0]["url"] == "https://shopee.vn/product-i.59009982.25022958529", (
        "luôn gửi dạng -i.<shop>.<item>: dạng /product/<shop>/<item> làm run FAILED")


@pytest.mark.parametrize("loi, chu", [
    (RuntimeError('HTTP 400: {"error":{"type":"run-failed"}}'), "tạm chặn"),
    (TimeoutError("Read timed out"), "không phản hồi kịp"),
])
def test_loi_nguon_thanh_cau_de_hieu(gia, monkeypatch, loi, chu):
    def hong(*a, **k):
        raise loi
    monkeypatch.setattr(L, "_danh_gia_shopee", hong)
    monkeypatch.setattr(L, "_tiktok_shop", hong)
    kq = json.loads(S._handle({"link": [SP_URL, TT_URL]}))
    assert chu in kq["loi"]["shopee"] and chu in kq["loi"]["tiktok_shop"]
    assert "HTTP" not in kq["loi"]["shopee"], "không dán lỗi kỹ thuật cho người dùng"


def test_tiktok_shop_doc_thieu_danh_gia_thi_noi_ro(gia):
    tt = json.loads(S._handle({"link": [TT_URL]}))["san_pham"][0]
    assert "2/7" in tt["binh_luan"]["chi_doc_duoc"]


def test_tiktok_shop_lay_danh_gia_moi_nhat_khong_lay_de_xuat(gia):
    """'recommended' giấu đánh giá xấu: 7 đánh giá (2 cái 1 sao) chỉ trả 3 cái 4–5 sao."""
    goi, _ = gia
    S._handle({"link": [TT_URL]})
    assert [p for a, p in goi if a == L.ACTOR_TTS][0]["reviewsSortBy"] == "recent"


def test_nhieu_phan_loai_thi_bao_khoang_gia_va_phan_bo_sao(gia, monkeypatch):
    """Tai nghe Pro4 (~20 phân loại): `price` chỉ là phân loại rẻ nhất (18.800đ) trong khi
    người dùng xem phân loại 36.000đ — phải ra KHOẢNG giá, kèm tên phân loại."""
    it = dict(TIM_SHOPEE[0], priceMin=18800, priceMax=54000, priceMinBeforeDiscount=60000,
              priceMaxBeforeDiscount=90000, isOnFlashSale=True,
              ratingBreakdown=[20, 1, 0, 2, 3, 14], isVerifiedSeller=True,
              tierVariations=[{"name": "Dòng Tai Nghe", "options": ["Pro 4", "M10", "B3"]}],
              createdAt="2025-10-06T03:46:41+00:00", shopLocation="Hà Nội")
    monkeypatch.setattr(A, "_call", lambda actor, p, n, mem=None:
                        [it] if actor == L.ACTOR_TIM_SHOPEE else DG_SHOPEE)
    t = json.loads(S._handle({"link": [SP_URL]}))["san_pham"][0]["thong_tin"]
    assert (t["gia_tu"], t["gia_den"]) == (18800, 54000) and t["dang_flash_sale"] is True
    assert t["phan_loai"] == ["Pro 4", "M10", "B3"] and t["so_phan_loai"] == 3
    assert t["phan_bo_sao_toan_bo"] == {"5 sao": 14, "4 sao": 3, "3 sao": 2, "2 sao": 0, "1 sao": 1}
    assert t["ngay_bat_dau_ban"] == "2025-10-06" and "số đã bán" in t["khong_co"]


def test_tim_theo_ten_khong_khop_itemid_thi_khong_bia_gia(gia, monkeypatch):
    monkeypatch.setattr(L, "_gia_shopee", lambda x: None)
    sp = json.loads(S._handle({"link": [SP_URL]}))["san_pham"][0]
    assert sp["chua_lay_duoc_gia"] and "gia_tu" not in sp["thong_tin"]


def test_tiktok_shop_khong_tra_san_pham_thi_bao_ro(gia, monkeypatch):
    monkeypatch.setattr(L, "_tiktok_shop", lambda links, n: [])
    tt = json.loads(S._handle({"link": [TT_URL]}))["san_pham"][0]
    assert "không trả sản phẩm này" in tt["khong_doc_duoc"]


def test_so_danh_gia_co_theo_tran(gia):
    goi, _ = gia
    kq = json.loads(S._handle({"link": [SP_URL], "so_danh_gia": 500}))
    p = [p for a, p in goi if a == L.ACTOR_DG_SHOPEE and p["starFilter"] == "all"][0]
    assert p["maxReviewsPerProduct"] == 73, "(0,3 - 0,008) / 0,004 = 73"
    assert kq["bi_co_theo_tran"]


def test_link_la_thi_bao_ro(gia):
    assert "Không nhận ra link" in S._handle({"link": ["https://hapas.vn"]})


def test_khong_co_link_thi_van_tim_tu_khoa_nhu_cu(gia, monkeypatch):
    monkeypatch.setattr(A, "_call", lambda *a, **k: [])
    kq = json.loads(S._handle({"tu_khoa": ["túi"]}))
    assert kq.get("che_do") != "soi_theo_link" and kq["so_san_pham"] == 0


def test_khong_lay_duoc_so_da_ban_thi_noi_ro_chu_khong_ghi_0(gia, monkeypatch):
    monkeypatch.setattr(L, "_chi_tiet_shopee", lambda x: None)
    t = json.loads(S._handle({"link": [SP_URL]}))["san_pham"][0]["thong_tin"]
    assert "da_ban" not in t and t["khong_co"].startswith("số đã bán")


def test_chi_tiet_shopee_khong_khop_item_thi_bo_qua(monkeypatch):
    monkeypatch.setattr(A, "_call", lambda *a, **k: [dict(CT_SHOPEE[0], item_id=1)])
    assert L._chi_tiet_shopee(L.nhan_dien(SP_URL)) is None


def test_tiktok_shop_co_mo_ta_phan_loai_va_giao_hang(gia, monkeypatch):
    """Chủ agent 28/09: phủ MỌI khía cạnh — mô tả, giá/tồn kho từng phân loại, giao hàng."""
    sp = dict(TTS[0], description="THÔNG TIN CHI TIẾT:\nChất liệu: Da tổng hợp",
              variants=[{"name": "163 - XANH BƠ", "price": "112931", "originalPrice": "142650",
                         "discountPercent": "21%", "stockStatus": "in_stock", "stockQuantity": 979}],
              shippingInfo={"freeShipping": False, "shippingFee": "From 30.200₫", "minDays": 2,
                            "maxDays": 6, "leadTime": "Sep 27 - Oct 1"})
    monkeypatch.setattr(A, "_call", lambda *a, **k: [sp])
    tt = json.loads(S._handle({"link": [TT_URL]}))["san_pham"][0]
    assert tt["mo_ta"].startswith("THÔNG TIN CHI TIẾT")
    assert tt["phan_loai"] == [{"ten": "163 - XANH BƠ", "gia": 112931, "gia_goc": 142650,
                                "giam": "21%", "con_hang": "còn", "ton_kho": 979}]
    assert tt["thong_tin"]["giao_hang"] == "From 30.200₫ · giao 2–6 ngày · dự kiến Sep 27 - Oct 1"


def test_loc_binh_luan_bo_trung_va_rong():
    dg = [{"noi_dung": "Vải chất lượng, nên mua!"}, {"noi_dung": "vải chất lượng nên mua"},
          {"noi_dung": ""}, {"noi_dung": "Áo đẹp"}]
    giu, loc = L.loc_binh_luan(dg)
    assert [d["noi_dung"] for d in giu] == ["Vải chất lượng, nên mua!", "Áo đẹp"]
    assert loc == {"doc_duoc": 4, "bo_rong": 1, "bo_trung": 1, "giu_lai": 2}


def test_shopee_bi_chan_binh_luan_van_tao_sheet(gia, monkeypatch):
    """Bản cũ chỉ tạo Sheet khi có bình luận: Shopee chặn đọc bình luận là mất cả Sheet."""
    monkeypatch.setattr(L, "_danh_gia_shopee", lambda *a, **k: {})
    kq = json.loads(S._handle({"link": [SP_URL]}))
    assert kq["sheet_url"] == "https://sheet"
    assert "mô tả" in kq["san_pham"][0]["thong_tin"]["khong_co"]
