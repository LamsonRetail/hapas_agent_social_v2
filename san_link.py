"""Soi SẢN PHẨM CỤ THỂ từ link Shopee hoặc TikTok Shop — phần "dán link" của tool `soi_san`.

Người dùng hỏi thẳng: "gửi hẳn link sản phẩm vào thì có soi được không, Shopee, và TikTok
Shop có soi được không". Đo thật 25/09/2026, từng nguồn một:

  Shopee
    • ĐÁNH GIÁ theo link — `zen-studio~shopee-product-reviews-scraper`: chạy được, 10–20
      đánh giá trong 23–38 giây, thực tế chỉ tính 0,008 USD khởi động. Có số sao, nội dung,
      phân loại đã mua, mua lại, shop trả lời. KHÔNG ỔN ĐỊNH: 3 lượt đơn lẻ chạy, rồi bị
      Shopee chặn 4 lượt liền sau khi chạy 3 lượt song song cho cùng sản phẩm — chỉ chạy MỘT
      lượt mỗi lần soi, và báo "thử lại sau" chứ đừng chạy lại liên tục.
    • CHI TIẾT theo link (giá, số đã bán) — KHÔNG dùng được: `zen-studio~shopee-product-
      detail-scraper` hỏng 3/3 lần ("temporarily unavailable", 502 sau 126 giây, quá 200
      giây); `gio21~shopee-product-detail` ở gói FREE chỉ trả bộ nhớ đệm, sản phẩm lạ thì rỗng.
      Nên lấy giá bằng đường vòng: tìm theo TÊN trong link rồi khớp itemId, trượt thì tìm
      trong 30 sản phẩm bán chạy nhất của shop (mã shop luôn có trong link).
    • SỐ ĐÃ BÁN + shop theo link — `xtracto~shopee-product-detail`: chạy, 14 giây, 0,04 USD.
      Giá của nó không khớp giá thật nên chỉ lấy số đã bán và thông tin shop.
    • 25/09 lúc 16:00, đọc ĐÁNH GIÁ Shopee bị chặn ở MỌI đường đã thử: zen-studio (chặn
      hơn 40 phút), `dami_studio~shopee-shop-reviews-scraper` ("upstream_route_blocked"),
      gọi thẳng API công khai của Shopee từ máy này (403, đòi chữ ký chống bot). Nên phần
      đánh giá coi là "có thì dùng", phân bổ sao toàn bộ (từ tìm kiếm) là chỗ dựa chính.
  TikTok Shop
    • SẢN PHẨM + ĐÁNH GIÁ theo link — `pro100chok~tiktok-shop-scraper-usage`: chạy 4/5 lần,
      18–20 giây, ~0,0035 USD/sản phẩm (có 1 lần treo quá 120 giây). Có giá, số đã bán CHÍNH
      XÁC, điểm, phân bổ sao, phân loại, follower và tổng số bán của shop. Chỉ đọc được
      khoảng 3 ĐÁNH GIÁ mỗi sản phẩm, bất kể sản phẩm có bao nhiêu: áo len 2.502 đánh giá
      cũng chỉ ra 3, kể cả dùng chế độ đọc đánh giá riêng; lọc theo 1/2/3 sao trả dòng rỗng.
      Đó là giới hạn khi xem không đăng nhập, KHÔNG phải "chỉ đánh giá có nội dung" (kết
      luận sai ban đầu từ sản phẩm 7 đánh giá). Phân bổ sao TOÀN BỘ thì luôn đủ.
    • Tìm theo TỪ KHOÁ — KHÔNG làm: "túi xách nữ" ra toàn shop nhỏ 0–2 lượt bán, kể cả khi
      xếp theo bán chạy. Trình bày như "thị trường TikTok Shop" là sai lệch nặng.
    • Giá TikTok Shop nhảy giữa hai lần chạy (cùng sản phẩm 299.606đ rồi 274.109đ): giá động
      theo khuyến mãi. Báo giá kèm thời điểm, đừng coi là giá niêm yết.
"""
from __future__ import annotations

import collections
import contextvars
import datetime
import re
import statistics
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

import requests

import apify_tool as A
import trinh_bay_sheet as T

ACTOR_DG_SHOPEE = "zen-studio~shopee-product-reviews-scraper"
ACTOR_TIM_SHOPEE = "zen-studio~shopee-product-scraper"
# SỐ ĐÃ BÁN + thông tin shop theo link. Đo 25/09: tai nghe Pro4 ra `sold`=92 (trang hiện
# 87 lúc trước — số mới hơn), shop 7 follower / 17 sản phẩm / 4,48 sao; 14 giây, 0,04 USD.
# `price` của nó (99.000đ) KHÔNG khớp khoảng giá thật 18.800–100.000đ → không lấy giá ở đây.
# Đã loại `meanusarcanus~shopee-scraper-ai`: trả DỮ LIỆU GIẢ (hỏi tai nghe VN ra "loa
# Bluetooth 450 baht, AudioTech Official Store, Bangkok" — đúng mẫu trong tài liệu của nó).
ACTOR_CT_SHOPEE = "xtracto~shopee-product-detail"
GIA_CT_SHOPEE = 0.04
ACTOR_TTS = "pro100chok~tiktok-shop-scraper-usage"
# Giá NIÊM YẾT — chỉ dùng để co số lượng cho an toàn dưới trần, phòng khi actor bắt đầu
# tính đúng như niêm yết.
GIA_DG_SHOPEE, KHOI_DONG_DG_SHOPEE = 0.004, 0.008
GIA_TIM_SHOPEE, KHOI_DONG_TIM = 0.005, 0.005
GIA_TTS = 0.002
# Giá THẬT đo 25/09/2026 (chargedEventCounts): đánh giá Shopee chưa bị tính theo từng đánh
# giá (`reviews: 0`, chỉ 0,008 khởi động); TikTok Shop gói sản phẩm + đánh giá thành MỘT
# dòng, ~0,0035 USD/sản phẩm. Dùng cho ước tính, để khỏi báo cao gấp 10 lần thực tế.
THAT_DG_SHOPEE, THAT_TTS = 0.008, 0.0035
# MỘT lượt đọc đánh giá mỗi lần soi, không tách lượt riêng cho 1–2 sao. Đo 25/09: chạy 3
# lượt đánh giá song song cho cùng một sản phẩm thì Shopee chặn ("Reviews for a market
# could not be collected") — 4 lượt liền sau đó hỏng, trong khi 3 lượt đơn lẻ trước đó
# đều chạy. Thay bằng đọc nhiều đánh giá hơn trong một lượt (rẻ: chưa tính theo đánh giá).
_DG_MAC_DINH = 50
_SHOP_TOI_DA = 30            # đường vòng lấy giá: tìm trong 30 sản phẩm bán chạy nhất của shop


def _loi_de_hieu(san: str, e: Exception) -> str:
    """Lỗi nguồn → câu người dùng hiểu được. Hai kiểu hỏng đã gặp thật 25/09."""
    s = str(e)
    if "run-failed" in s or "FAILED" in s:
        return (f"{san} đang tạm chặn lượt đọc (chống bot). Thử lại sau vài phút; "
                "đừng chạy lại liên tục vì càng dễ bị chặn lâu hơn.")
    if "Timeout" in type(e).__name__ or "timed out" in s:
        return f"{san} không phản hồi kịp lần này. Thử lại sau ít phút."
    return f"{san}: {type(e).__name__}: {s}"[:250]


_RUT_GON = ("vt.tiktok.com", "vm.tiktok.com", "s.shopee.vn", "shp.ee", "shope.ee")
_TOI_DA_LINK = 5


def _mo_link(u: str) -> str:
    """Link chia sẻ rút gọn (vt.tiktok.com, s.shopee.vn…) → link đầy đủ. Hỏng thì giữ nguyên."""
    host = urllib.parse.urlparse(u).netloc.lower()
    if not any(host == h or host.endswith("." + h) for h in _RUT_GON):
        return u
    try:
        return requests.get(u, allow_redirects=True, timeout=10,
                            headers={"User-Agent": "Mozilla/5.0"}).url or u
    except requests.RequestException:
        return u


def nhan_dien(u: str) -> dict | None:
    """Link → {san, url, ...}. None nếu không phải link sản phẩm Shopee/TikTok Shop."""
    u = _mo_link((u or "").strip())
    m = re.search(r"shopee\.vn/(?:(.+?)-i\.|.*?[?&/]i\.)(\d+)\.(\d+)", u) \
        or re.search(r"shopee\.vn/product/()(\d+)/(\d+)", u)
    if m:
        ten = urllib.parse.unquote(m.group(1) or "").replace("-", " ").strip()
        # Actor đánh giá chỉ nhận dạng "-i.<shop>.<item>": đo 25/09, link "/product/<shop>/
        # <item>" làm run FAILED. Nên luôn gửi dạng chuẩn, còn `url` giữ link người dùng dán.
        return {"san": "shopee", "url": u, "shop_id": m.group(2), "item_id": m.group(3),
                "ten_trong_link": ten,
                "url_actor": f"https://shopee.vn/product-i.{m.group(2)}.{m.group(3)}"}
    m = re.search(r"(?:shop\.tiktok\.com|tiktok\.com/shop|tiktok\.com/view/product)"
                  r"(?:/[^?#]*)?/(\d{12,})", u)
    if m:
        # Actor nhận dạng .../pdp/<tên>/<id>; link chia sẻ "view/product/<id>" không có tên
        # nên dựng lại theo đúng dạng actor nhận.
        url = u if "/pdp/" in u else f"https://shop.tiktok.com/vn/pdp/san-pham/{m.group(1)}"
        return {"san": "tiktok_shop", "url": url.split("?")[0], "product_id": m.group(1)}
    return None


def _so(v, kieu=int):
    try:
        return kieu(v or 0)
    except (TypeError, ValueError):
        return kieu(0)


# ───────────────────────────── lấy dữ liệu ─────────────────────────────
def _danh_gia_shopee(links: list[dict], n: int, sao: str = "all") -> dict[str, list[dict]]:
    raw = A._call(ACTOR_DG_SHOPEE, {"startUrls": [{"url": x["url_actor"]} for x in links],
                                    "maxReviewsPerProduct": n, "starFilter": sao},
                  n * len(links))
    ra: dict[str, list[dict]] = collections.defaultdict(list)
    for r in raw:
        if not isinstance(r, dict) or r.get("_warning") or not r.get("reviewId"):
            continue
        tra_loi = r.get("shopReply") or {}
        ra[str(r.get("itemId"))].append({
            "id": str(r.get("reviewId")),
            "ngay": A._to_vn(r.get("createdAt")), "sao": _so(r.get("ratingStar")),
            "noi_dung": " ".join(str(r.get("comment") or "").split()),
            "phan_loai": ", ".join(v.get("name") or "" for v in r.get("variations") or []
                                   if isinstance(v, dict)),
            "mua_lai": bool(r.get("isRepeatPurchase")), "da_mua_that": True,
            "shop_tra_loi": bool(tra_loi.get("comment") if isinstance(tra_loi, dict) else tra_loi),
            "co_anh": bool(r.get("images")),
            "__goc": r,           # bản ghi gốc → tab "Dữ liệu gốc" (không vào tool_result)
        })
    return ra


def _gia_shopee(x: dict) -> dict | None:
    """Đường vòng lấy giá (nguồn chi tiết theo link đang hỏng), rồi khớp itemId.

    1. Tìm theo TÊN có trong link — nhanh (~12 giây), nhưng tên trong link thường không dấu
       nên hay trượt.
    2. Trượt thì tìm trong các sản phẩm BÁN CHẠY của chính shop (mã shop luôn có trong link)
       — đo 25/09 ra đúng sản phẩm nhưng mất ~47 giây. Sản phẩm không nằm trong top của shop
       thì chịu, trả None và báo thẳng.
    """
    it = None
    ten = " ".join(x["ten_trong_link"].split()[:10])
    if ten:
        raw = A._call(ACTOR_TIM_SHOPEE, {"searchTerms": [ten], "region": "VN", "maxItems": 20,
                                         "sort": "relevance"}, 20)
        it = next((i for i in raw if str(i.get("itemId")) == x["item_id"]), None)
    if not it:
        raw = A._call(ACTOR_TIM_SHOPEE, {"shopId": int(x["shop_id"]), "region": "VN",
                                         "maxItems": _SHOP_TOI_DA, "sort": "best_selling"},
                      _SHOP_TOI_DA)
        it = next((i for i in raw if str(i.get("itemId")) == x["item_id"]), None)
    if not it:
        return None
    # Sản phẩm nhiều phân loại thì `price` chỉ là giá phân loại RẺ NHẤT. Đo 25/09: tai nghe
    # Pro4 báo 18.800đ trong khi phân loại người dùng xem là 36.000đ sau voucher — phải
    # báo KHOẢNG giá theo phân loại, không một con số.
    tu, den = int(_so(it.get("priceMin") or it.get("price"), float)), int(_so(it.get("priceMax"), float))
    pl = [o for t in it.get("tierVariations") or [] if isinstance(t, dict)
          for o in t.get("options") or []]
    # `ratingBreakdown` = [tổng, 1★, 2★, 3★, 4★, 5★] của TOÀN BỘ đánh giá — vẫn có khi Shopee
    # chặn đọc nội dung đánh giá.
    rb = it.get("ratingBreakdown")
    sao = ({f"{i} sao": _so(rb[i]) for i in range(5, 0, -1)}
           if isinstance(rb, list) and len(rb) >= 6 else None)
    return {"ten": it.get("name"),
            "gia_tu": tu, "gia_den": den if den > tu else None,
            "gia_goc_tu": int(_so(it.get("priceMinBeforeDiscount") or it.get("priceBeforeDiscount"), float)) or None,
            "gia_goc_den": int(_so(it.get("priceMaxBeforeDiscount"), float)) or None,
            "giam_pct": _so(it.get("discountPercent")) or None,
            "dang_flash_sale": bool(it.get("isOnFlashSale")),
            "diem": round(_so(it.get("rating"), float), 2),
            "tong_danh_gia": _so(it.get("ratingCount")), "phan_bo_sao_toan_bo": sao,
            "so_binh_luan": _so(it.get("commentCount")) or None,
            "luot_thich": _so(it.get("likedCount")),
            "so_phan_loai": len(pl) or None, "phan_loai": pl[:25] or None,
            "ngay_bat_dau_ban": str(it.get("createdAt") or "")[:10] or None,
            "shop": it.get("shopName"), "shopee_mall": bool(it.get("isOfficialShop")),
            "shop_da_xac_minh": bool(it.get("isVerifiedSeller")),
            "noi_gui": it.get("shopLocation"), "__goc": it}


def _chi_tiet_shopee(x: dict) -> dict | None:
    """Số đã bán và thông tin shop (xtracto). Không có số thì None — đừng coi là 0."""
    raw = A._call(ACTOR_CT_SHOPEE, {"country": "vn", "shopId": x["shop_id"],
                                    "itemId": x["item_id"]}, 1)
    it = next((i for i in raw if isinstance(i, dict) and str(i.get("item_id")) == x["item_id"]),
              None)
    if not it:
        return None
    sh = it.get("shop") if isinstance(it.get("shop"), dict) else {}
    ra = {"da_ban": _so(it.get("sold") or it.get("historical_sold")) or None,
          "shop_follower": _so(sh.get("follower_count")) if sh.get("follower_count") is not None else None,
          "shop_so_san_pham": _so(sh.get("item_count")) or None,
          "shop_diem": round(_so(sh.get("rating_star"), float), 2) or None,
          "shop_xac_minh_shopee": bool(sh.get("is_shopee_verified"))}
    return {**{k: v for k, v in ra.items() if v is not None}, "__goc": it}


def _giao_hang(s) -> str | None:
    """shippingInfo của TikTok Shop → một câu: phí, số ngày, ngày dự kiến."""
    if not isinstance(s, dict):
        return None
    phan = ["miễn phí ship" if s.get("freeShipping") else (s.get("shippingFee") or "")]
    lo, hi = s.get("minDays"), s.get("maxDays")
    if lo or hi:
        phan.append(f"giao {lo or hi} ngày" if lo == hi or not (lo and hi) else f"giao {lo}–{hi} ngày")
    if s.get("leadTime"):
        phan.append(f"dự kiến {s['leadTime']}")
    return " · ".join(p for p in phan if p) or None


def loc_binh_luan(dg: list[dict]) -> tuple[list[dict], dict]:
    """Bỏ bình luận rỗng và bình luận TRÙNG nội dung. Đo 25/09: cùng một câu "vải chất lượng,
    mặc dù là áo len nhưng mặc không nóng…" xuất hiện 2 lần với 2 mã đánh giá khác nhau."""
    giu, da_thay, rong, trung = [], set(), 0, 0
    for d in dg:
        k = re.sub(r"\W+", " ", d["noi_dung"].lower()).strip()
        if not k:
            rong += 1
            continue
        if k in da_thay:
            trung += 1
            continue
        da_thay.add(k)
        giu.append(d)
    return giu, {"doc_duoc": len(dg), "bo_rong": rong, "bo_trung": trung, "giu_lai": len(giu)}


def _tiktok_shop(links: list[dict], n: int) -> list[dict]:
    # `reviewsSortBy="recent"`: mặc định "recommended" GIẤU đánh giá xấu — đo 25/09, sản phẩm
    # 7 đánh giá (2 cái 1 sao) chỉ trả về 3 cái 4–5 sao. Hỏi "khách chê gì" mà thiếu đúng
    # đánh giá chê là sai từ gốc.
    raw = A._call(ACTOR_TTS, {"region": "vn", "scrapeType": "product",
                              "productUrls": [x["url"] for x in links],
                              "includeReviews": True, "maxReviews": n,
                              "reviewsSortBy": "recent"}, len(links))
    ra = []
    for p in raw:
        if not isinstance(p, dict) or not p.get("productId"):
            continue
        sao = ((p.get("ratingsBreakdown") or {}).get("stars") or {})
        ra.append({
            "product_id": str(p.get("productId")),
            "__goc": p,           # cả sản phẩm (kèm đánh giá lồng) → tab "Dữ liệu gốc"
            "thong_tin": {
                "ten": p.get("title"), "gia": _so(p.get("currentPrice")),
                "gia_cao_nhat": _so(p.get("maxPrice")) or None,
                "gia_goc": _so(p.get("originalPrice")) or None,
                "giam": p.get("discountPercent"), "da_ban": _so(p.get("exactSoldCount") or p.get("salesVolume")),
                "ban_30_ngay": _so(p.get("soldLast30Days")) or None,
                "diem": _so(p.get("rating"), float), "tong_danh_gia": _so(p.get("totalReviews") or p.get("reviewCount")),
                "phan_bo_sao_toan_bo": {k: sao[k] for k in sorted(sao)} or None,
                "danh_muc": p.get("category"),
                "shop": p.get("sellerName"), "shop_follower": _so(p.get("shopFollowers")) or None,
                "shop_tong_da_ban": _so(p.get("shopTotalSold")) or None,
                "shop_diem": _so(p.get("shopRating"), float) or None,
                "shop_so_san_pham": _so(p.get("shopOnSaleProducts")) or None,
                "so_phan_loai": len(p.get("variants") or []),
                "giao_hang": _giao_hang(p.get("shippingInfo")),
                "so_anh": len(p.get("imageUrls") or []) or None,
                "so_video": len(p.get("videoUrls") or []) or None,
            },
            # Chủ agent muốn phủ MỌI khía cạnh của sản phẩm, không chỉ số sao: mô tả đầy đủ
            # và giá/tồn kho TỪNG phân loại (đo 25/09: 11 phân loại, mỗi cái có giá, giá gốc,
            # % giảm, còn/hết hàng, số tồn).
            "mo_ta": str(p.get("description") or "").strip(),
            "phan_loai": [{
                "ten": v.get("name") or "", "gia": _so(v.get("price")) or None,
                "gia_goc": _so(v.get("originalPrice")) or None, "giam": v.get("discountPercent"),
                "con_hang": {"in_stock": "còn", "out_of_stock": "hết"}.get(
                    str(v.get("stockStatus")), str(v.get("stockStatus") or "")),
                "ton_kho": _so(v.get("stockQuantity")) if v.get("stockQuantity") is not None else None,
            } for v in p.get("variants") or [] if isinstance(v, dict)],
            "danh_gia": [{
                "ngay": A._to_vn(_so(r.get("date"), float) / 1000) if r.get("date") else None,
                "sao": _so(r.get("rating")), "noi_dung": " ".join(str(r.get("text") or "").split()),
                "phan_loai": r.get("variant") or "", "mua_lai": False,
                "da_mua_that": bool(r.get("isVerifiedPurchase")), "shop_tra_loi": False,
                "co_anh": bool(r.get("imageUrls")),
            } for r in p.get("reviews") or [] if isinstance(r, dict)],
        })
    return ra


# ───────────────────────────── tổng hợp ─────────────────────────────
def tong_hop_danh_gia(dg: list[dict], san: str) -> dict:
    if not dg:
        return {"so_danh_gia_da_doc": 0}
    sao = collections.Counter(d["sao"] for d in dg if d["sao"])
    ngay = [d["ngay"] for d in dg if d["ngay"]]
    pl = collections.Counter(d["phan_loai"] for d in dg if d["phan_loai"])
    xau = [d for d in dg if d["sao"] and d["sao"] <= 3 and d["noi_dung"]]
    tot = [d for d in dg if d["sao"] >= 5 and len(d["noi_dung"]) > 20]
    ra = {
        "so_danh_gia_da_doc": len(dg),
        "sao_tb_trong_mau": round(statistics.mean(d["sao"] for d in dg if d["sao"]), 2) if sao else None,
        "phan_bo_sao_trong_mau": {f"{k} sao": sao[k] for k in range(5, 0, -1) if sao.get(k)},
        "phan_loai_hay_mua": [f"{k} ({v})" for k, v in pl.most_common(3)],
        "danh_gia_xau": [f"{d['sao']}★ {d['noi_dung'][:200]}" for d in xau[:6]],
        "danh_gia_tot": [f"{d['sao']}★ {d['noi_dung'][:160]}" for d in tot[:3]],
    }
    if ngay:
        ra["tu_ngay"], ra["den_ngay"] = f"{min(ngay):%d/%m/%Y}", f"{max(ngay):%d/%m/%Y}"
    if san == "shopee":
        ra["ti_le_mua_lai"] = round(sum(d["mua_lai"] for d in dg) / len(dg), 3)
        ra["ti_le_shop_tra_loi"] = round(sum(d["shop_tra_loi"] for d in dg) / len(dg), 3)
    else:
        ra["ti_le_da_mua_that"] = round(sum(d["da_mua_that"] for d in dg) / len(dg), 3)
    return ra


# Sheet 4 bảng — chủ agent muốn PHỦ MỌI KHÍA CẠNH của sản phẩm (28/09): sản phẩm, từng phân
# loại, mô tả, bình luận. Cột bình luận gọi là "Bình luận", không phải "Nội dung".
# 08/10/2026 (trinh_bay_sheet): tab đầu "Tổng quan" do lớp trình bày dựng (mục lục, kiểm ghi,
# ghi chú) nên bảng tổng hợp từng sản phẩm đổi tên thành "Sản phẩm" (tên biến giữ nguyên).
TEN_TAB_SAN_PHAM = "Sản phẩm"
TAB_TONG_QUAN = ["Sàn", "Sản phẩm", "Danh mục", "Giá từ", "Giá đến", "Giá gốc", "Giảm",
                 "Flash sale", "Đã bán", "Điểm", "Tổng đánh giá", "5★", "4★", "3★", "2★", "1★",
                 "Số phân loại", "Giao hàng", "Shop", "Shop follower", "Shop đã bán",
                 "Shop điểm", "Shop số sản phẩm", "Bình luận đọc được", "Bình luận sau lọc",
                 "Không lấy được", "Link"]
TAB_PHAN_LOAI = ["Sàn", "Sản phẩm", "Phân loại", "Giá", "Giá gốc", "Giảm", "Còn hàng", "Tồn kho"]
TAB_MO_TA = ["Sàn", "Sản phẩm", "Mô tả", "Danh mục"]
HEADER = ["Sàn", "Sản phẩm", "Ngày", "Sao", "Phân loại", "Bình luận", "Đã mua thật",
          "Mua lại", "Shop trả lời", "Có ảnh", "Link"]


def _sao(t: dict, k: int):
    pb = t.get("phan_bo_sao_toan_bo") or {}
    return pb.get(f"{k} sao", pb.get(str(k), ""))


def _dong_tong_quan(san: str, ten, t: dict, link: str, loc: dict, tong) -> list:
    return [san, ten or "", t.get("danh_muc") or "",
            t.get("gia_tu") or t.get("gia") or "", t.get("gia_den") or t.get("gia_cao_nhat") or "",
            t.get("gia_goc_tu") or t.get("gia_goc") or "", t.get("giam_pct") or t.get("giam") or "",
            "có" if t.get("dang_flash_sale") else "", t.get("da_ban") if t.get("da_ban") is not None else "",
            t.get("diem") or "", tong if tong is not None else "",
            *[_sao(t, k) for k in (5, 4, 3, 2, 1)],
            t.get("so_phan_loai") or "", t.get("giao_hang") or "", t.get("shop") or "",
            t.get("shop_follower") if t.get("shop_follower") is not None else "",
            t.get("shop_tong_da_ban") or "", t.get("shop_diem") or "",
            t.get("shop_so_san_pham") or "", loc["doc_duoc"], loc["giu_lai"],
            (t.get("khong_co") or "").replace(" — nguồn không trả", ""), link]


def _dong_binh_luan(san: str, ten, d: dict, link: str, *, mua_lai=False, tra_loi=False,
                    da_mua=True) -> list:
    return [san, ten or "", f"{d['ngay']:%Y-%m-%d}" if d["ngay"] else "", d["sao"],
            d["phan_loai"], d["noi_dung"][:1000], "có" if da_mua else "",
            "có" if mua_lai else "", "có" if tra_loi else "", "có" if d["co_anh"] else "", link]


# Số của CẢ SHOP (không phải của sản phẩm). Chủ agent 28/09: "đây là 1 link sản phẩm nhưng
# lại đánh giá toàn bộ cả shop?" — soi một link thì chỉ đánh giá SẢN PHẨM; thông tin shop
# chỉ đưa vào khi người dùng hỏi về shop (`gom_shop`). Tên shop vẫn giữ để biết ai bán.
_KHOA_SHOP = ("shop_follower", "shop_tong_da_ban", "shop_diem", "shop_so_san_pham",
              "shop_da_xac_minh", "shop_xac_minh_shopee")
_COT_SHOP = ("Shop follower", "Shop đã bán", "Shop điểm", "Shop số sản phẩm")


def _bo_shop(thong_tin: dict) -> dict:
    return {k: v for k, v in thong_tin.items() if k not in _KHOA_SHOP}


def soi(links_vao: list[str], so_danh_gia: int, gom_shop: bool = False) -> dict:
    """Chạy phần soi theo link. Trả dict để `soi_san` đóng gói thành kết quả tool."""
    nhan, khong_nhan = [], []
    for u in links_vao[:_TOI_DA_LINK]:
        x = nhan_dien(str(u))
        (nhan.append(x) if x else khong_nhan.append(str(u)))
    shopee = [x for x in nhan if x["san"] == "shopee"]
    tts = [x for x in nhan if x["san"] == "tiktok_shop"]
    tran_bai, tran_usd = A._tran()
    # Mỗi nguồn là MỘT lượt chạy, chịu trần `tran_usd` riêng: số đánh giá co theo trần.
    n = max(5, min(so_danh_gia, tran_bai))
    if shopee:
        n_sp = int((tran_usd - KHOI_DONG_DG_SHOPEE) / GIA_DG_SHOPEE / len(shopee) + 1e-9)
    if tts:
        n_tt = int(tran_usd / GIA_TTS / len(tts) + 1e-9) - 1
    n_sp = max(1, min(n, n_sp)) if shopee else 0
    n_tt = max(1, min(n, n_tt)) if tts else 0
    co = n_sp < so_danh_gia if shopee else False
    co = co or (n_tt < so_danh_gia if tts else False)
    # Ước tính theo giá THẬT đo được: 1 lượt đánh giá, cộng đường vòng lấy giá (tìm theo
    # tên nếu có, rồi tìm trong shop) cho mỗi link Shopee.
    est = (THAT_DG_SHOPEE if shopee else 0) \
        + sum((KHOI_DONG_TIM + GIA_TIM_SHOPEE * 20 if x["ten_trong_link"] else 0)
              + KHOI_DONG_TIM + GIA_TIM_SHOPEE * _SHOP_TOI_DA for x in shopee) \
        + GIA_CT_SHOPEE * len(shopee) + THAT_TTS * len(tts)

    loi: dict[str, str] = {}
    # KHÔNG `with ThreadPoolExecutor`: `with` chờ luồng chậm nhất nên `timeout` vô hiệu (rà
    # 01/10/2026). Một hạn chung; luồng còn treo bỏ lại, run Apify tự hết hạn.
    han = time.monotonic() + A._TOOL_DEADLINE

    def cho() -> float:
        return max(0.05, han - time.monotonic())

    ex = ThreadPoolExecutor(max_workers=2 + len(shopee))

    def gui(fn, *a):
        return ex.submit(contextvars.copy_context().run, fn, *a)

    try:
        f_dg = gui(_danh_gia_shopee, shopee, n_sp) if shopee else None
        f_gia = {x["item_id"]: gui(_gia_shopee, x) for x in shopee}
        f_ct = {x["item_id"]: gui(_chi_tiet_shopee, x) for x in shopee}
        f_tts = gui(_tiktok_shop, tts, n_tt) if tts else None
        dg_sp: dict[str, list[dict]] = {}
        if f_dg:
            try:
                dg_sp = f_dg.result(timeout=cho())
            except Exception as e:  # noqa: BLE001
                loi["shopee"] = _loi_de_hieu("Shopee", e)
        gia = {}
        for k, f in f_gia.items():
            try:
                gia[k] = f.result(timeout=cho())
            except Exception:  # noqa: BLE001 — giá là phụ, hỏng thì báo "chưa lấy được giá"
                gia[k] = None
        ct = {}
        for k, f in f_ct.items():
            try:
                ct[k] = f.result(timeout=cho())
            except Exception:  # noqa: BLE001 — số đã bán là phụ, hỏng thì để trống và nói ra
                ct[k] = None
        sp_tts = []
        if f_tts:
            try:
                sp_tts = f_tts.result(timeout=cho())
            except Exception as e:  # noqa: BLE001
                loi["tiktok_shop"] = _loi_de_hieu("TikTok Shop", e)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    san_pham = []
    tq, pl_rows, mt_rows, bl_rows = [], [], [], []
    goc: list[dict] = []          # bản ghi nguồn nguyên vẹn (mọi trường) cho "Dữ liệu gốc"
    for x in shopee:
        dg_goc = dg_sp.get(x["item_id"], [])
        dg, loc = loc_binh_luan(dg_goc)
        tt = gia.get(x["item_id"])
        thong_tin = dict(tt or {"ten": x["ten_trong_link"] or None})
        g_tim = thong_tin.pop("__goc", None)
        c = dict(ct.get(x["item_id"]) or {})
        g_ct = c.pop("__goc", None)
        if c:
            thong_tin.update(c)
        ten_g = thong_tin.get("ten") or x["ten_trong_link"]
        goc += [_ban_ghi_goc(a, ten_g, it) for a, it in
                [(ACTOR_TIM_SHOPEE, g_tim), (ACTOR_CT_SHOPEE, g_ct)]
                + [(ACTOR_DG_SHOPEE, d.get("__goc")) for d in dg_goc] if it]
        thieu = [m for m, co in (("số đã bán", "da_ban" in thong_tin), ("mô tả", False),
                                 ("giá sau voucher", False), ("phí ship", False),
                                 ("voucher shop", False), ("tồn kho", False)) if not co]
        thong_tin["khong_co"] = ", ".join(thieu) + " — nguồn không trả"
        tong = thong_tin.get("tong_danh_gia")
        san_pham.append({
            "san": "Shopee", "link": x["url"],
            "thong_tin": thong_tin,
            "chua_lay_duoc_gia": None if tt else (
                "Chưa lấy được giá: nguồn chi tiết sản phẩm Shopee đang hỏng, và sản phẩm này "
                f"không nằm trong {_SHOP_TOI_DA} sản phẩm bán chạy nhất của shop."),
            "mo_ta": None,
            "binh_luan": {**tong_hop_danh_gia(dg, "shopee"), "loc": loc,
                          "tong_binh_luan_cua_san_pham": tong},
        })
        ten = thong_tin.get("ten") or x["ten_trong_link"]
        tq.append(_dong_tong_quan("Shopee", ten, thong_tin, x["url"], loc, tong))
        pl_rows += [["Shopee", ten, p, "", "", "", "", ""] for p in thong_tin.get("phan_loai") or []]
        mt_rows.append(["Shopee", ten, "Chưa lấy được — Shopee đang chặn đường đọc trang chi tiết", ""])
        bl_rows += [_dong_binh_luan("Shopee", ten, d, x["url"], mua_lai=d["mua_lai"],
                                    tra_loi=d["shop_tra_loi"]) for d in dg]
    theo_id = {p["product_id"]: p for p in sp_tts}
    for x in tts:
        p = theo_id.get(x["product_id"])
        if not p:
            san_pham.append({"san": "TikTok Shop", "link": x["url"],
                             "khong_doc_duoc": "TikTok Shop không trả sản phẩm này (link sai, "
                                               "đã gỡ, hoặc không bán ở Việt Nam)."})
            continue
        dg, loc = loc_binh_luan(p["danh_gia"])
        if p.get("__goc"):
            goc.append(_ban_ghi_goc(ACTOR_TTS, p["thong_tin"].get("ten"), p["__goc"]))
        bl = tong_hop_danh_gia(dg, "tiktok_shop")
        tong = p["thong_tin"].get("tong_danh_gia") or 0
        if tong > bl["so_danh_gia_da_doc"]:
            # TikTok Shop chỉ cho đọc vài bình luận khi không đăng nhập (đo 25/09: 2.502 đánh
            # giá vẫn ra 3, kể cả chế độ đọc đánh giá riêng). Nói ra để khỏi tưởng mẫu là toàn
            # bộ; `phan_bo_sao_toan_bo` vẫn đủ.
            bl["chi_doc_duoc"] = (
                f"Chỉ đọc được {loc['doc_duoc']}/{tong} bình luận — TikTok Shop chỉ cho xem vài "
                "bình luận mỗi sản phẩm, nên đây KHÔNG phải mẫu đại diện. Nhận xét về chất "
                "lượng dựa vào `phan_bo_sao_toan_bo` (đủ mọi đánh giá).")
        t = p["thong_tin"]
        san_pham.append({
            "san": "TikTok Shop", "link": x["url"], "thong_tin": t,
            "mo_ta": p["mo_ta"][:1500] or None,
            "phan_loai": p["phan_loai"][:30],
            "binh_luan": {**bl, "loc": loc, "tong_binh_luan_cua_san_pham": tong}})
        tq.append(_dong_tong_quan("TikTok Shop", t["ten"], t, x["url"], loc, tong))
        pl_rows += [["TikTok Shop", t["ten"], v["ten"], v["gia"] or "", v["gia_goc"] or "",
                     v["giam"] or "", v["con_hang"], "" if v["ton_kho"] is None else v["ton_kho"]]
                    for v in p["phan_loai"]]
        mt_rows.append(["TikTok Shop", t["ten"], p["mo_ta"][:5000] or "Shop không ghi mô tả",
                        t.get("danh_muc") or ""])
        bl_rows += [_dong_binh_luan("TikTok Shop", t["ten"], d, x["url"],
                                    da_mua=d["da_mua_that"]) for d in dg]

    actors = ([ACTOR_DG_SHOPEE] if shopee else []) + \
        ([ACTOR_TIM_SHOPEE, ACTOR_CT_SHOPEE] if shopee else []) + \
        ([ACTOR_TTS] if tts else [])
    tieu_de_tq = list(TAB_TONG_QUAN)
    if not gom_shop:
        bo = [tieu_de_tq.index(c) for c in _COT_SHOP]
        tieu_de_tq = [c for i, c in enumerate(tieu_de_tq) if i not in bo]
        tq = [[v for i, v in enumerate(r) if i not in bo] for r in tq]
        for sp in san_pham:
            if sp.get("thong_tin"):
                sp["thong_tin"] = _bo_shop(sp["thong_tin"])
    tabs = DanhSachTab([(TEN_TAB_SAN_PHAM, [tieu_de_tq] + tq),
                        ("Phân loại", [TAB_PHAN_LOAI] + pl_rows),
                        ("Mô tả", [TAB_MO_TA] + mt_rows),
                        ("Bình luận", [HEADER] + bl_rows)])
    bi_co = (f"Xin {so_danh_gia} bình luận mỗi sản phẩm, lấy {n_sp or n_tt} để nằm trong trần "
             f"hiện tại ({tran_bai} bài · {tran_usd:g} USD mỗi lượt).") if co else None
    tabs.goc = goc
    tabs.ghi_chu = _ghi_chu_sheet(san_pham, shopee, tts, gom_shop, bi_co, loi, khong_nhan)
    tabs.pham_vi = (f"{len(shopee)} link Shopee, {len(tts)} link TikTok Shop"
                    + (f" · {len(khong_nhan)} link không nhận ra" if khong_nhan else ""))
    return {"san_pham": san_pham, "tabs": tabs, "dong_sheet": bl_rows, "loi": loi or None,
            "khong_nhan_ra": khong_nhan or None, "actors": actors, "est": est,
            "so_danh_gia_moi_sp": {"shopee": n_sp or None, "tiktok_shop": n_tt or None},
            "bi_co_theo_tran": bi_co,
            "nen": sorted({x["san"] for x in nhan})}


class DanhSachTab(list):
    """[(tên tab, [tiêu đề] + dòng)] như cũ (shopee_tool đọc `tabs[0][1]`), kèm ngữ cảnh cho
    sheet: `goc` (bản ghi nguồn), `ghi_chu`, `pham_vi`; sau khi ghi có `ket_qua` (T.KetQua)."""
    goc: list = []
    ghi_chu: list = []
    pham_vi: str = ""
    ket_qua = None


def _ban_ghi_goc(actor: str, ten, it: dict) -> dict:
    return {"Nguồn (actor)": actor, "Sản phẩm (của tool)": ten or "", **it}


def _ghi_chu_sheet(san_pham: list, shopee: list, tts: list, gom_shop: bool, bi_co, loi: dict,
                   khong_nhan: list) -> list:
    """Cách hiểu số + giới hạn nguồn đã biết (đo 25/09/2026) cho phần Ghi chú của Tổng quan."""
    g = ["Giá, số đã bán, điểm là số TẠI THỜI ĐIỂM SOI (xem 'Tạo lúc'); tiền là đồng (VND).",
         "Ô trống = nguồn không trả số đó, KHÔNG phải 0 (vd 'Đã bán' của Shopee khi nguồn chi "
         "tiết không trả). Cột 'Không lấy được' nói rõ thiếu gì."]
    if shopee:
        g.append(f"Shopee: giá lấy qua tìm kiếm (theo tên trong link, trượt thì trong "
                 f"{_SHOP_TOI_DA} sản phẩm bán chạy của shop) rồi khớp mã sản phẩm; nhiều phân "
                 "loại thì 'Giá từ'–'Giá đến' là KHOẢNG giá theo phân loại. Cột 'Giảm' = số % "
                 "(34 = 34%). Mô tả Shopee chưa lấy được (Shopee chặn trang chi tiết); danh sách "
                 "phân loại tối đa 25.")
    if tts:
        g.append("TikTok Shop: giá động theo khuyến mãi (có thể đổi giữa hai lần soi); chỉ đọc "
                 "được vài bình luận mỗi sản phẩm khi không đăng nhập nên bảng Bình luận KHÔNG "
                 "phải mẫu đại diện — phân bổ 5★…1★ ở bảng Sản phẩm là của TOÀN BỘ đánh giá. "
                 "Cột 'Giảm' giữ nguyên chữ nguồn trả ('7%'). Mô tả cắt ở 5.000 ký tự.")
    g.append("Bình luận rỗng hoặc trùng nội dung đã bỏ ('Bình luận đọc được' → 'Bình luận sau "
             "lọc'); nội dung mỗi bình luận cắt ở 1.000 ký tự.")
    if not gom_shop:
        g.append("Chỉ đánh giá SẢN PHẨM: số liệu của cả shop (follower, đã bán, điểm, số sản "
                 "phẩm) không đưa vào — hỏi về shop thì soi lại với gom_shop.")
    if bi_co:
        g.append(bi_co)
    for sp in san_pham:
        if sp.get("chua_lay_duoc_gia"):
            g.append(f"{sp['san']} {sp['link']}: {sp['chua_lay_duoc_gia']}")
        if sp.get("khong_doc_duoc"):
            g.append(f"{sp['san']} {sp['link']}: {sp['khong_doc_duoc']} — không có dòng trong "
                     "các bảng.")
        if (sp.get("binh_luan") or {}).get("chi_doc_duoc"):
            g.append(f"{sp['san']} {sp['link']}: {sp['binh_luan']['chi_doc_duoc']}")
    for k, v in (loi or {}).items():
        g.append(f"Lỗi nguồn {k}: {v}")
    if khong_nhan:
        g.append("Không nhận ra link sản phẩm: " + ", ".join(khong_nhan))
    return g


# Kiểu cột theo tên tiêu đề (mọi bảng). Giá Shopee (region VN) và TikTok Shop (region vn) là
# số nguyên đồng → tiền VND. "Giảm" trộn số (Shopee) và chữ "7%" (TikTok) → để chữ.
_KIEU = {"Giá từ": "tien", "Giá đến": "tien", "Giá gốc": "tien", "Giá": "tien",
         "Đã bán": "so_nguyen", "Điểm": "thap_phan", "Tổng đánh giá": "so_nguyen",
         **{f"{k}★": "so_nguyen" for k in range(1, 6)}, "Số phân loại": "so_nguyen",
         "Shop follower": "so_nguyen", "Shop đã bán": "so_nguyen", "Shop điểm": "thap_phan",
         "Shop số sản phẩm": "so_nguyen", "Bình luận đọc được": "so_nguyen",
         "Bình luận sau lọc": "so_nguyen", "Không lấy được": "chu_dai", "Link": "link",
         "Tồn kho": "so_nguyen", "Mô tả": "chu_dai", "Ngày": "ngay", "Sao": "so_nguyen",
         "Bình luận": "chu_dai"}
_MO_TA = {TEN_TAB_SAN_PHAM: "Mỗi sản phẩm một dòng: giá, đã bán, điểm, phân bổ sao, shop",
          "Phân loại": "Từng phân loại: giá, giá gốc, % giảm, còn hàng, tồn kho",
          "Mô tả": "Mô tả sản phẩm (TikTok Shop; Shopee chưa lấy được)",
          "Bình luận": "Bình luận/đánh giá đọc được (đã bỏ rỗng/trùng)"}


def _bang_tu_tab(tabs: list) -> list:
    ra = []
    for ten, rows in tabs:
        if not rows:
            continue
        cot = [T.Cot(c, _KIEU.get(c, "chu"), tien_te="VND" if _KIEU.get(c) == "tien" else None)
               for c in rows[0]]
        # Mô tả dài: luôn tab riêng, không gấp vào Tổng quan dù ít dòng.
        ra.append(T.Bang(ten, cot, rows[1:], mo_ta=_MO_TA.get(ten, ""), gap_duoc=ten != "Mô tả"))
    return ra


def xuat_soi(title: str, tabs: list, cap_quyen=None) -> "T.KetQua":
    """Ghi sheet soi sản phẩm qua `trinh_bay_sheet`: Tổng quan (phạm vi, đếm theo sàn/sao,
    ghi chú nguồn), "1. Sản phẩm", "2. Phân loại", "3. Mô tả", "4. Bình luận", "Dữ liệu gốc".
    `cap_quyen(tok)` chạy SAU CÙNG (như cũ: cấp quyền sau khi ghi). Lỗi tạo/ghi thì ném."""
    bang = _bang_tu_tab(tabs)
    sp = next((x for x in bang if x.ten == TEN_TAB_SAN_PHAM), bang[0] if bang else None)
    bl = next((x for x in bang if x.ten == "Bình luận"), None)
    nhom = [T.dem_theo(sp, "Sàn", "Sản phẩm theo sàn")] if sp and sp.dong else []
    if bl is not None and bl.dong:
        nhom.append(T.dem_theo(bl, "Sao", "Bình luận theo số sao"))
    goc = list(getattr(tabs, "goc", None) or [])
    tq = T.TongQuan(
        tieu_de=title, nguon="soi_san — soi sản phẩm theo link (Apify: Shopee / TikTok Shop)",
        thoi_gian="số liệu tại thời điểm soi", pham_vi=getattr(tabs, "pham_vi", "") or
        f"{len(sp.dong) if sp else 0} sản phẩm", nhom=nhom,
        ghi_chu=list(getattr(tabs, "ghi_chu", None) or []))
    kq = T.xuat(title, bang, tq, goc=T.bang_goc(goc) if goc else None, cap_quyen=cap_quyen)
    if isinstance(tabs, DanhSachTab):
        tabs.ket_qua = kq
    return kq


def ghi_nhieu_tab(title: str, tabs: list[tuple[str, list[list]]],
                  cap_quyen=None) -> tuple[str, str]:
    """Tạo MỘT Lark Sheet nhiều tab (qua `xuat_soi`). Trả (token, url) như cũ; kết quả đủ
    (kiểm ghi, `cho_tool()`) nằm ở `tabs.ket_qua` khi `tabs` là `DanhSachTab` của `soi`."""
    kq = xuat_soi(title, tabs, cap_quyen=cap_quyen)
    return kq.token, kq.url
