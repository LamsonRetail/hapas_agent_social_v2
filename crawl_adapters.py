"""Bảng ADAPTER "site → Apify actor" cho `web_crawl` — DANH SÁCH NGOẠI LỆ.

Đọc trước khi thêm mục mới
--------------------------
Thang 6 tầng trong `crawl_runner.py` là luật CHUNG, không biết site nào cả — đó
là điểm mạnh của nó và đừng làm bẩn. File này là chỗ chứa các NGOẠI LỆ tường
minh: site mà luật chung chắc chắn không bóc được, và đã có actor Apify sẵn giải
xong bài đó.

Vì sao tách ra thành bảng riêng chứ không nhét vào thang chung: một luật riêng
lẫn giữa các luật chung sẽ bị người sau tưởng là luật chung, rồi sửa nhầm. Ở đây
mỗi mục là một dòng khai báo, đọc là biết ngay "đây là ngoại lệ cho site X".

Adapter CHỈ chạy khi thang 6 tầng miễn phí ra 0 sản phẩm. Nó tốn tiền Apify nên
không bao giờ được chạy trước tầng miễn phí.

Uniqlo — đo thật 08/09/2026
---------------------------
`web_crawl` ra **0 sp** trên `uniqlo.com/vn/vi` và `/vn/en`: SPA, storefront trả
403 cho mọi fetcher (kể cả browser stealth), sitemap 22.157 URL nhưng không nhóm
nào bóc được. Dữ liệu nằm ở API commerce riêng
(`/vn/api/commerce/v5/vi/products`) — API này trả 200 cho client thường nhưng
đòi header client-id mà Uniqlo không công bố.

Không tự hardcode endpoint + client-id đó vào runner (sẽ phá luật "không hardcode
site", và vỡ ngay khi họ đổi client-id). Dùng actor đã có người bảo trì:

    chính   rl1987~uniqlo-api-scraper     $0,50/1.000 sp   — gọi đúng API trên
    dự phòng abotapi~uniqlo-com-scraper   $2,00/1.000 sp + $0,08 khởi động

Kiểm chứng cả HAI actor (cố ý — dự án vừa học bài "cơ chế dự phòng chưa từng
chạy thì coi như không có"):
    rl1987  : 20 sp / 20s. Field: name, basePrice, promoPrice, mainImage, url,
              productId, colors, sizes, currency.
    abotapi : 12 sp / 16s, `mode` chỉ nhận "search" hoặc "url" (KHÔNG có
              "category"). Field: name, url, price, basePrice, promoPrice,
              originalPrice, discountPercent, isOnSale, currency, rating.
              Field ẢNH chưa xác minh được tên → bộ đọc ảnh dò nhiều khoá và
              GHI NHẬT KÝ khi không thấy, thay vì im lặng trả rỗng.

Rủi ro đã biết: cả hai actor đều rất ít người dùng. Dự án từng gặp apidojo chạy
tốt cả buổi rồi đột ngột trả rỗng cho mọi truy vấn. Vì thế phải leo thang theo
SẢN LƯỢNG THẤP, không đợi tới lúc lỗi hẳn.
"""

from __future__ import annotations

import datetime
import re

from apify_tool import _VN_TZ, _call
from crawl_runner import _sp   # dùng chung bộ chuẩn hoá sản phẩm, một nguồn sự thật

# Actor chính ra ít hơn ngưỡng này thì coi như nó đang hỏng -> gọi dự phòng.
# KHÔNG đợi tới lúc trả rỗng: apidojo (TikTok) đã cho thấy actor chạm trần/hỏng
# một phần thì không bao giờ rỗng, nên luật "chỉ leo thang khi rỗng" chưa từng chạy.
_NGUONG_LEO_THANG = 5


def _vung_lang(url: str) -> tuple[str, str]:
    """`uniqlo.com/vn/vi/...` -> ('vn', 'vi'). Không rõ thì mặc định VN/vi."""
    m = re.search(r"uniqlo\.com/([a-z]{2})/([a-z]{2})\b", url, re.I)
    return (m.group(1).lower(), m.group(2).lower()) if m else ("vn", "vi")


def _anh_uniqlo(it: dict) -> list[str]:
    """Gom ảnh, dò nhiều tên khoá vì actor dự phòng chưa xác minh được field ảnh."""
    ra: list[str] = []
    for k in ("mainImage", "image", "imageUrl", "mainImageUrl", "thumbnail"):
        v = it.get(k)
        if isinstance(v, str) and v.startswith("http"):
            ra.append(v)
    for k in ("images", "imageUrls", "media"):
        v = it.get(k)
        if isinstance(v, list):
            ra += [x for x in v if isinstance(x, str) and x.startswith("http")]
        elif isinstance(v, dict):
            ra += [x for x in v.values() if isinstance(x, str) and x.startswith("http")]
    return list(dict.fromkeys(ra))


def _ma_mau(it: dict) -> str:
    """Khoá gộp theo MÃ MẪU (`l1Id`/`styleCode`), không phải theo tên.

    CẢNH BÁO CHO NGƯỜI SỬA SAU — đọc hết trước khi "tối ưu" chỗ này:
    Kết quả Uniqlo trông như bị lặp (10 dòng đầu có 3 dòng cùng tên "UT MAGIC
    FOR ALL ICONS Áo Thun"). Đã kiểm 08/09/2026: chúng có SKU và link KHÁC NHAU
    hoàn toàn (E489147, E489146, E484258) — là các mẫu áo KHÁC NHAU thật, chỉ
    trùng tên vì Uniqlo đặt cùng một tên cho cả bộ sưu tập UT.
    **Gộp theo TÊN là xoá mất sản phẩm thật.** Vì thế chỉ gộp theo mã mẫu.

    Trên dữ liệu thật hàm này gộp 0 dòng, và đó là ĐÚNG. Nó là chốt phòng khi
    actor bắt đầu trả nhiều màu của cùng một mẫu (cùng `l1Id`) — lúc đó gộp mới
    hợp lý, và số gộp được ghi vào nhật ký chứ không âm thầm.
    """
    return str(it.get("l1Id") or it.get("styleCode")
               or str(it.get("productId") or "").split("-")[0] or "").strip()


def _uniqlo_chuan_hoa(it: dict, base: str) -> dict:
    """Field của hai actor đủ giống nhau để dùng chung một bộ đọc.

    `promoPrice` là giá đang bán, `basePrice`/`originalPrice` là giá gốc. Không
    giảm giá thì promoPrice = null — `_sp()` tự bỏ giá gốc khi nó <= giá bán nên
    không sợ hiện "giá gốc 0đ".
    """
    goc = it.get("originalPrice") or it.get("basePrice")
    ban = it.get("promoPrice") or it.get("price") or it.get("basePrice")
    return _sp(it.get("name"), ban, goc, it.get("url") or "",
               _anh_uniqlo(it), it.get("productId") or it.get("styleCode") or "", base)


_BANG = {
    "uniqlo.com": {
        "ten": "Uniqlo — API commerce công khai (qua actor Apify)",
        "chinh": {
            "actor": "rl1987~uniqlo-api-scraper",
            "gia_moi_1000": 0.50,
            "input": lambda url, n: {**dict(zip(("region", "lang"), _vung_lang(url))),
                                     "maxItems": n},
        },
        # Dự phòng chỉ chạy được ở mode "url": nó bắt buộc phải có `queries` nếu
        # dùng mode "search", mà bịa một từ khoá tiếng Việt ("ao", "quan"…) sẽ
        # làm LỆCH catalog trả về. Thà báo thất bại trung thực còn hơn trả về một
        # mẫu bị thiên lệch mà người đọc tưởng là toàn bộ.
        "du_phong": {
            "actor": "abotapi~uniqlo-com-scraper",
            "gia_moi_1000": 2.00,
            "input": lambda url, n: {"mode": "url", "urls": [url],
                                     "country": _vung_lang(url)[0],
                                     "language": _vung_lang(url)[1], "maxItems": n},
        },
        "chuan_hoa": _uniqlo_chuan_hoa,
        # Kiểm chứng 08/09/2026: 10 dòng đầu trùng tên nhưng SKU và link KHÁC
        # NHAU hoàn toàn (E489151, E489148, E489147, E484258…) — Uniqlo đặt cùng
        # một tên cho cả bộ sưu tập UT. Suýt gộp theo tên và xoá mất sản phẩm
        # thật. Nói trước cho người đọc sheet khỏi tưởng dữ liệu bị lặp.
        "ghi_chu": ("Uniqlo đặt CÙNG MỘT TÊN cho nhiều mẫu trong cùng bộ sưu tập "
                    "(vd cả bộ UT đều tên 'UT ... Áo Thun'). Các dòng trùng tên là "
                    "SẢN PHẨM KHÁC NHAU — phân biệt bằng cột SKU và Link, đừng báo "
                    "với người dùng là dữ liệu bị trùng lặp."),
    },
}


def tim(url: str) -> tuple[str, dict] | tuple[None, None]:
    low = url.lower()
    for mien, cfg in _BANG.items():
        if mien in low:
            return mien, cfg
    return None, None


def _ghi_so(url: str, actors: list[str], bat_dau, est: float, log: list) -> None:
    """Ghi tiền Apify của adapter vào sổ chi phí quét — như mọi tool quét khác.

    Trước 02/10/2026 adapter tốn tiền thật mà không có dòng nào trong "Chi phí quét"
    (UAT-WEB-04). Ghi cả khi actor lỗi/ra 0 dòng: Apify vẫn tính tiền lượt chạy.
    Fail-open: sổ hỏng không được làm hỏng kết quả cào."""
    if not actors:
        return
    try:
        import apify_tool
        import chi_phi_tool
        thuc = apify_tool._chi_phi_thuc(list(dict.fromkeys(actors)), bat_dau, est)
        chi_phi_tool.ghi(queries=[url], platforms=["web"], date_range="hiện tại",
                         thuc=thuc, est=est)
    except Exception as e:  # noqa: BLE001
        log.append(f"adapter: ghi so chi phi loi {type(e).__name__}: {str(e)[:80]}")


def chay(url: str, toi_da: int, log: list) -> dict:
    """Chạy adapter cho `url`. Trả dict luôn có khoá `san_pham` (có thể rỗng).

    FAIL-OPEN: mọi lỗi đều được ghi vào `log` rồi trả rỗng — hàm gọi giữ nguyên
    kết luận thất bại trung thực của thang miễn phí, không được biến lỗi adapter
    thành "site không có sản phẩm".
    """
    mien, cfg = tim(url)
    if not cfg:
        return {"san_pham": [], "adapter": None}

    goc = (re.match(r"(https?://[^/]+)", url) or [None, url])[1] if "://" in url else url
    sp: list[dict] = []
    da_dung: list[str] = []
    da_goi: list[str] = []
    chi_phi = 0.0
    bat_dau = datetime.datetime.now(_VN_TZ) - datetime.timedelta(seconds=5)

    for nhan in ("chinh", "du_phong"):
        buoc = cfg.get(nhan)
        if not buoc:
            continue
        if sp and len(sp) >= _NGUONG_LEO_THANG:
            break
        da_goi.append(buoc["actor"])
        try:
            raw = _call(buoc["actor"], buoc["input"](url, toi_da), toi_da)
        except Exception as e:  # noqa: BLE001
            log.append(f"adapter {buoc['actor']}: loi {type(e).__name__}: {str(e)[:110]}")
            continue
        got, da_co_mau, gop = [], set(), 0
        for it in raw:
            if not isinstance(it, dict):
                continue
            p = cfg["chuan_hoa"](it, goc)
            if not p.get("ten"):
                continue
            k = _ma_mau(it)
            if k and k in da_co_mau:
                gop += 1
                continue
            if k:
                da_co_mau.add(k)
            got.append(p)
        thieu_anh = sum(1 for p in got if not p.get("anh"))
        log.append(f"adapter {buoc['actor']}: {len(raw)} dong -> {len(got)} mau"
                   + (f" (gop {gop} bien the mau)" if gop else "")
                   + (f", {thieu_anh} khong co anh" if thieu_anh else ""))
        if got:
            co = {p["link"] for p in sp if p.get("link")}
            sp += [p for p in got if p.get("link") not in co or not p.get("link")]
            da_dung.append(buoc["actor"])
            chi_phi += len(got) / 1000.0 * float(buoc.get("gia_moi_1000") or 0)
        if len(sp) >= _NGUONG_LEO_THANG:
            break
        if nhan == "chinh":
            log.append(f"adapter: actor chinh ra {len(sp)} sp (< nguong "
                       f"{_NGUONG_LEO_THANG}) -> thu actor du phong")

    _ghi_so(url, da_goi, bat_dau, chi_phi, log)
    return {"san_pham": sp[:toi_da], "adapter": cfg["ten"] if sp else None,
            "actor_da_dung": da_dung, "uoc_tinh_chi_phi_usd": round(chi_phi, 4),
            "ghi_chu": cfg.get("ghi_chu") if sp else None}
