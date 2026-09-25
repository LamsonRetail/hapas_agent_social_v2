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
      trong 30 sản phẩm bán chạy nhất của shop (mã shop luôn có trong link). Vẫn KHÔNG có
      số đã bán.
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
import datetime
import re
import statistics
import urllib.parse

import requests

import apify_tool as A

ACTOR_DG_SHOPEE = "zen-studio~shopee-product-reviews-scraper"
ACTOR_TIM_SHOPEE = "zen-studio~shopee-product-scraper"
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


_RUT_GON =("vt.tiktok.com", "vm.tiktok.com", "s.shopee.vn", "shp.ee", "shope.ee")
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
            "noi_gui": it.get("shopLocation"),
            "khong_co": ("số đã bán, giá sau voucher, phí ship, voucher shop, tồn kho — chỉ có "
                         "trên trang chi tiết, nguồn đó đang hỏng")}


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
            },
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


HEADER = ["Sàn", "Sản phẩm", "Ngày", "Sao", "Phân loại", "Nội dung", "Đã mua thật",
          "Mua lại", "Shop trả lời", "Có ảnh", "Link"]


def soi(links_vao: list[str], so_danh_gia: int) -> dict:
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
        + THAT_TTS * len(tts)

    from concurrent.futures import ThreadPoolExecutor
    loi: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=2 + len(shopee)) as ex:
        f_dg = ex.submit(_danh_gia_shopee, shopee, n_sp) if shopee else None
        f_gia = {x["item_id"]: ex.submit(_gia_shopee, x) for x in shopee}
        f_tts = ex.submit(_tiktok_shop, tts, n_tt) if tts else None
        dg_sp: dict[str, list[dict]] = {}
        if f_dg:
            try:
                dg_sp = f_dg.result(timeout=A._TOOL_DEADLINE)
            except Exception as e:  # noqa: BLE001
                loi["shopee"] = _loi_de_hieu("Shopee", e)
        gia = {}
        for k, f in f_gia.items():
            try:
                gia[k] = f.result(timeout=A._TOOL_DEADLINE)
            except Exception:  # noqa: BLE001 — giá là phụ, hỏng thì báo "chưa lấy được giá"
                gia[k] = None
        sp_tts = []
        if f_tts:
            try:
                sp_tts = f_tts.result(timeout=A._TOOL_DEADLINE)
            except Exception as e:  # noqa: BLE001
                loi["tiktok_shop"] = _loi_de_hieu("TikTok Shop", e)

    san_pham, dong = [], []
    for x in shopee:
        dg = dg_sp.get(x["item_id"], [])
        tt = gia.get(x["item_id"])
        san_pham.append({
            "san": "Shopee", "link": x["url"],
            "thong_tin": tt or {"ten": x["ten_trong_link"] or None},
            "chua_lay_duoc_gia": None if tt else (
                "Chưa lấy được giá: nguồn chi tiết sản phẩm Shopee đang hỏng, và sản phẩm này "
                f"không nằm trong {_SHOP_TOI_DA} sản phẩm bán chạy nhất của shop."),
            "khong_co_so_da_ban": True,
            "danh_gia": tong_hop_danh_gia(dg, "shopee"),
        })
        ten = (tt or {}).get("ten") or x["ten_trong_link"]
        dong += [["Shopee", ten, f"{d['ngay']:%Y-%m-%d}" if d["ngay"] else "", d["sao"],
                  d["phan_loai"], d["noi_dung"][:1000], "có", "có" if d["mua_lai"] else "",
                  "có" if d["shop_tra_loi"] else "", "có" if d["co_anh"] else "", x["url"]]
                 for d in dg]
    theo_id = {p["product_id"]: p for p in sp_tts}
    for x in tts:
        p = theo_id.get(x["product_id"])
        if not p:
            san_pham.append({"san": "TikTok Shop", "link": x["url"],
                             "khong_doc_duoc": "TikTok Shop không trả sản phẩm này (link sai, "
                                               "đã gỡ, hoặc không bán ở Việt Nam)."})
            continue
        dg = tong_hop_danh_gia(p["danh_gia"], "tiktok_shop")
        tong = p["thong_tin"].get("tong_danh_gia") or 0
        if tong > dg["so_danh_gia_da_doc"]:
            # Đo 25/09: 7 đánh giá (2 cái 1 sao) mà chỉ đọc được 3, kể cả xếp theo mới nhất —
            # TikTok Shop chỉ cho đọc vài đánh giá khi không đăng nhập (đo: 2.502 đánh giá vẫn
            # ra 3). Nói ra để khỏi tưởng mẫu là toàn bộ; `phan_bo_sao_toan_bo` vẫn đủ.
            dg["chi_doc_duoc"] = (
                f"Chỉ đọc được {dg['so_danh_gia_da_doc']}/{tong} đánh giá — TikTok Shop chỉ cho "
                "xem vài đánh giá mỗi sản phẩm, nên đây KHÔNG phải mẫu đại diện. Nhận xét về "
                "chất lượng dựa vào `phan_bo_sao_toan_bo` (đủ mọi đánh giá).")
        san_pham.append({"san": "TikTok Shop", "link": x["url"], "thong_tin": p["thong_tin"],
                         "danh_gia": dg})
        dong += [["TikTok Shop", p["thong_tin"]["ten"], f"{d['ngay']:%Y-%m-%d}" if d["ngay"] else "",
                  d["sao"], d["phan_loai"], d["noi_dung"][:1000],
                  "có" if d["da_mua_that"] else "", "", "", "có" if d["co_anh"] else "", x["url"]]
                 for d in p["danh_gia"]]

    actors = ([ACTOR_DG_SHOPEE] if shopee else []) + \
        ([ACTOR_TIM_SHOPEE] if shopee else []) + \
        ([ACTOR_TTS] if tts else [])
    return {"san_pham": san_pham, "dong_sheet": dong, "loi": loi or None,
            "khong_nhan_ra": khong_nhan or None, "actors": actors, "est": est,
            "so_danh_gia_moi_sp": {"shopee": n_sp or None, "tiktok_shop": n_tt or None},
            "bi_co_theo_tran": (f"Xin {so_danh_gia} đánh giá mỗi sản phẩm, lấy "
                                f"{n_sp or n_tt} để nằm trong trần hiện tại "
                                f"({tran_bai} bài · {tran_usd:g} USD mỗi lượt).") if co else None,
            "nen": sorted({x["san"] for x in nhan})}
