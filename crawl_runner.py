"""Runner cào sản phẩm — chạy TRONG .venv-scrapling, gọi bởi crawl_tool.py.

KHÔNG hardcode site. Thử thang chiến lược từ rẻ/chuẩn tới đắt/đoán mò, và LUÔN
báo lại đã dùng tầng nào để agent nói đúng sự thật.

Khảo sát thật 28/08/2026 trên 10 brand thời trang VN — vì sao thang này:
  1. catalog_json : Haravan/Shopify. hapas.vn ăn ở /collections/all/products.json
                    (112 sp, có giá thật). Chuẩn nhất, một request ra cả catalog.
                    LƯU Ý: Haravan dùng /collections/all/products.json, Shopify
                    dùng /products.json — phải thử CẢ HAI.
  2. html_data    : JSON-LD Product, Next.js/Nuxt, hoặc JSON hydration trong BẤT KỲ
                    inline <script> nào. yody.vn ăn ở đây (90 sp từ HTML thô).
  3. html_gia     : đi ngược từ giá tới thẻ <a> gần nhất ngay trong HTML thô.
                    juno.vn 40 sp, vascara.com 19 sp.
  4. browser      : render JS rồi chạy lại hai bộ bóc trên. Chỉ còn dành cho SPA
                    thật sự (vỏ HTML rỗng). Đắt nhất: ~30-70s mỗi lượt.
Tầng 3 và 4 là ĐOÁN THEO MẪU, không phải dữ liệu có cấu trúc. crawl_tool.py bắt
Mark cảnh báo người dùng đối chiếu khi `tang` là html_gia hoặc browser.
Không tầng nào ăn -> trả rỗng KÈM nhật ký từng tầng, tuyệt đối không bịa.

BỔ SUNG 06/09/2026 — vì sao có tầng `sitemap` (đọc kỹ trước khi sửa)
--------------------------------------------------------------------
Bốn tầng trên chỉ đọc ĐÚNG MỘT TRANG (URL người dùng đưa). Trang chủ chỉ bày
sản phẩm nổi bật, nên kết quả *trông như* đã cào xong mà thật ra thiếu gần hết:
vascara.com ra 19 sp trong khi sitemap có 3.521 URL, yody.vn ra 90 trong khi
sitemap sản phẩm có 2.853. Đây đúng kiểu hỏng nguy hiểm nhất của dự án — không
crash, không báo lỗi, chỉ sai số liệu. Nên khi bốn tầng trên ra ÍT HƠN số người
dùng xin, ta mở rộng phạm vi bằng sitemap (robots.txt tự khai báo, là đường đi
được chủ site cho phép, khác với việc tự đoán `?page=N` mà vascara chặn trong
robots):
  5a. sitemap_sp      : sitemap -> từng TRANG SẢN PHẨM -> JSON-LD/og có cấu trúc.
                        Chuẩn nhất và là nơi DUY NHẤT có ĐỦ ẢNH (vascara 6 ảnh/sp).
  5b. sitemap_dm      : sitemap -> nhiều TRANG DANH MỤC -> chạy lại bộ bóc ở tầng
                        2/3. Rẻ hơn nhiều lần (1 request ra vài chục sp), dành cho
                        site không nhét dữ liệu vào trang sản phẩm (yody, juno).
Site nào đi đường nào là do ĐO chứ không khai báo sẵn: ta dò thử một nhúm URL
rồi mới bung ra. Mọi thứ đều nằm dưới một NGÂN SÁCH THỜI GIAN — hết giờ thì trả
những gì đã có kèm cờ `het_ngan_sach`, không bao giờ để crawl_tool timeout trắng.
"""

from __future__ import annotations

import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

# Windows may inherit a legacy console encoding (usually cp1252).  The runner
# communicates with crawl_tool.py as JSON over stdout, so one Vietnamese error
# message must never turn a recoverable crawl failure into UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
# Giá tiền Việt: 1.290.000₫ / 1,290,000 đ / 399.000 VND
_GIA = re.compile(r"(\d{1,3}(?:[.,]\d{3}){1,3})\s*(?:₫|đ|VND|vnđ)", re.I)
_THE = re.compile(r"<[^>]+>")
_CATALOG_PATHS = ("/collections/all/products.json", "/products.json")
_LUONG = 8                  # số kết nối song song khi quét nhiều trang
_CHAN = [0]                 # đếm số lần bị chặn tốc độ (429/503) để báo lại
_NGAN_SACH_MAC_DINH = 110   # giây; phải nhỏ hơn AGENT_REPLY_TIMEOUT (180s)


def _so(v):
    """Đổi giá về số nguyên đồng.

    Cẩn thận với hai khuôn dễ nhầm nhau:
      "1.135.250" / "1,290,000" -> dấu phân nhóm nghìn, phải giữ hết chữ số
      "850000.00" / "850000,00" -> hai chữ số cuối là XU, phải bỏ
    Bản cũ `split(",")[0]` biến "1,290,000₫" thành 1 đồng — sai âm thầm, không
    báo lỗi; đó là lý do chỗ này được viết lại theo hậu tố chứ không cắt chuỗi.
    """
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = re.sub(r"[.,]\d{1,2}$", "", str(v).strip())
    s = re.sub(r"[^\d]", "", s)
    return int(s) if s else None


def _tuyet_doi(u, base: str) -> str:
    """Đưa URL về tuyệt đối. `//cdn...` và `/uploads/...` mà để nguyên thì cột
    Ảnh trong sheet bấm vào không ra gì — mất ảnh kiểu này rất khó thấy."""
    u = str(u or "").strip().replace("&amp;", "&")
    if not u or u.startswith("data:"):
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith(("http://", "https://")):
        return u
    return base.rstrip("/") + "/" + u.lstrip("/")


def _anh_chuan(v, base: str) -> list[str]:
    """Chuẩn hoá mọi kiểu khai báo ảnh về danh sách URL tuyệt đối.

    Schema.org cho phép `image` là chuỗi, mảng chuỗi, ImageObject, hay mảng
    ImageObject; các khuôn hydration thì nhét dict {url|src|thumbnail}. Bản cũ
    str() thẳng nên gặp dict là ghi nguyên chữ "{'url': ...}" vào sheet.
    """
    ra: list[str] = []
    ngan = [v]
    while ngan and len(ra) < 40:
        x = ngan.pop(0)
        if isinstance(x, str):
            ra.append(_tuyet_doi(x, base))
        elif isinstance(x, list):
            ngan = list(x) + ngan
        elif isinstance(x, dict):
            for k in ("url", "contentUrl", "src", "@id", "thumbnail", "image"):
                if x.get(k):
                    ngan.insert(0, x[k])
                    break
    return [u for u in dict.fromkeys(ra) if u.startswith("http")]


# Thứ tự ưu tiên thuộc tính ảnh: site lazy-load để URL thật ở data-*, còn `src`
# chỉ là ảnh mờ 1x1 hoặc base64 -> đọc mỗi `src` là mất ảnh mà không hề báo lỗi.
_THUOC_TINH_ANH = ("data-srcset", "srcset", "data-src", "data-original",
                   "data-lazy-src", "data-lazy", "data-image", "src")
_ANH_RAC = re.compile(r"(?:^|/)(?:blank|spacer|placeholder|loading|lazy|1x1|pixel)"
                      r"[.\-_]|/tr\?id=", re.I)


def _anh_tu_the(the: str, base: str) -> str:
    """Lấy URL ảnh tốt nhất từ MỘT thẻ <img>."""
    for ten in _THUOC_TINH_ANH:
        m = re.search(ten + r'\s*=\s*["\']([^"\']+)["\']', the, re.I)
        if not m:
            continue
        v = m.group(1).strip()
        if "srcset" in ten:            # "a.jpg 1x, b.jpg 2x" -> lấy bản cuối (to nhất)
            phan = [p.strip().split()[0] for p in v.split(",") if p.strip()]
            v = phan[-1] if phan else ""
        if not v or v.startswith("data:") or _ANH_RAC.search(v):
            continue
        u = _tuyet_doi(v, base)
        if u:
            return u
    return ""


def _sp(ten, gia=None, goc=None, link="", anh="", sku="", base=""):
    g, gg = _so(gia), _so(goc)
    # compare_at_price = 0 nghĩa là KHÔNG giảm giá; để nguyên sẽ hiện "giá gốc 0đ".
    # Giá gốc thấp hơn hoặc bằng giá bán cũng vô nghĩa -> bỏ.
    if gg is not None and (gg == 0 or (g is not None and gg <= g)):
        gg = None
    ds = _anh_chuan(anh, base) if not isinstance(anh, str) else (
        [_tuyet_doi(anh, base)] if anh else [])
    ds = [u for u in ds if u]
    return {"ten": _THE.sub(" ", str(ten or "")).strip()[:250], "gia": g,
            "gia_goc": gg, "link": _tuyet_doi(link, base)[:400] if link else "",
            "anh": ds[0] if ds else "", "anh_tat_ca": ds[:20], "so_anh": len(ds),
            "sku": str(sku or "")[:60]}


def _goc(u: str) -> str:
    m = re.match(r"(https?://[^/]+)", u)
    return m.group(1) if m else u


def _khoa(p: dict) -> str:
    """Khoá khử trùng: ưu tiên link (chắc chắn), hết mới tới tên."""
    return (p.get("link") or "").split("?")[0].rstrip("/").lower() or \
        (p.get("ten") or "").strip().lower()


def _gop(dich: list[dict], them: list[dict], toi_da: int) -> int:
    """Gộp `them` vào `dich`, bản ghi cũ được BỔ SUNG chứ không bị đè mất dữ liệu.

    Vì sao không đè thẳng: trang danh mục có GIÁ còn trang sản phẩm có ĐỦ ẢNH —
    hai nguồn bổ khuyết cho nhau, đè một chiều là mất một nửa dữ liệu.
    """
    chi_muc = {_khoa(p): p for p in dich}
    dem = 0
    for p in them:
        k = _khoa(p)
        if not k or not p.get("ten"):
            continue
        cu = chi_muc.get(k)
        if cu is None:
            if len(dich) >= toi_da:
                continue
            dich.append(p)
            chi_muc[k] = p
            dem += 1
            continue
        if p.get("so_anh", 0) > cu.get("so_anh", 0):
            cu["anh"], cu["anh_tat_ca"] = p["anh"], p["anh_tat_ca"]
            cu["so_anh"] = p["so_anh"]
        for truong in ("gia", "gia_goc", "sku", "link"):
            if not cu.get(truong) and p.get(truong):
                cu[truong] = p[truong]
    return dem


# ───────────────── tầng 1: catalog JSON (Haravan / Shopify) ─────────────────
def catalog_json(base: str, toi_da: int, log: list) -> list[dict]:
    s = requests.Session()
    for path in _CATALOG_PATHS:
        out, page = [], 1
        while len(out) < toi_da and page <= 8:
            try:
                r = s.get(f"{base}{path}?limit=250&page={page}", timeout=20, headers=_UA)
            except Exception as e:
                log.append(f"catalog_json {path}: loi {type(e).__name__}")
                break
            if r.status_code != 200:
                break
            try:
                items = (r.json() or {}).get("products") or []
            except ValueError:
                break
            if not items:
                break
            for it in items:
                v = (it.get("variants") or [{}])[0]
                # LẤY CẢ ALBUM chứ không mỗi images[0]: Haravan/Shopify trả sẵn
                # toàn bộ ảnh, bỏ đi là tự tay vứt dữ liệu đã cầm trong tay.
                anh = [i.get("src") for i in (it.get("images") or [])
                       if isinstance(i, dict) and i.get("src")]
                out.append(_sp(it.get("title"), v.get("price"),
                               v.get("compare_at_price"),
                               f"{base}/products/{it.get('handle','')}", anh,
                               v.get("sku"), base))
            page += 1
        if out:
            log.append(f"catalog_json {path}: {len(out)}")
            return out[:toi_da]
        log.append(f"catalog_json {path}: 0")
    return []


# ───────────────── tầng 2: dữ liệu có cấu trúc trong HTML ─────────────────
def _duyet_ld(node, out, base=""):
    if isinstance(node, list):
        for x in node:
            _duyet_ld(x, out, base)
        return
    if not isinstance(node, dict):
        return
    t = node.get("@type")
    if any(str(x).lower() == "product" for x in ([t] if isinstance(t, str) else (t or []))):
        of = node.get("offers")
        of = (of[0] if isinstance(of, list) and of else of) or {}
        of = of if isinstance(of, dict) else {}
        out.append(_sp(node.get("name"), of.get("price") or of.get("lowPrice"),
                       node.get("highPrice") or of.get("highPrice"),
                       of.get("url") or node.get("url"),
                       node.get("image"), node.get("sku"), base))
    for k in ("@graph", "itemListElement", "item", "mainEntity"):
        if k in node:
            _duyet_ld(node[k], out, base)


def _objects(blob: str, khoa: str, gioi_han=8000, so_luong=100_000):
    """Cắt object JSON cân bằng ngoặc chứa `khoa` (regex không làm nổi vì lồng nhau).

    `so_luong` chặn trần số vị trí khoá được quét: blob hydration có thể tới
    vài trăm KB và `"price"` xuất hiện hàng nghìn lần, quét hết sẽ ăn hết ngân
    sách thời gian của cả lượt trả lời.
    """
    for dem, m in enumerate(re.finditer(re.escape(khoa), blob)):
        if dem >= so_luong:
            return
        i = blob.rfind("{", 0, m.start())
        if i < 0:
            continue
        d = 0
        for j in range(i, min(len(blob), i + gioi_han)):
            if blob[j] == "{":
                d += 1
            elif blob[j] == "}":
                d -= 1
                if d == 0:
                    try:
                        yield json.loads(blob[i:j + 1])
                    except ValueError:
                        pass
                    break


# Khoá giá thường gặp, xếp từ RIÊNG tới CHUNG: "price" trần rất dễ dính vào
# object không phải sản phẩm (phí ship, cấu hình khuyến mãi) nên để cuối.
_KHOA_GIA = ('"originalPrice"', '"salePrice"', '"compare_at_price"',
             '"regular_price"', '"price"')
_SCRIPT = re.compile(r"<script[^>]*>(.*?)</script>", re.S | re.I)
_QUET_TOI_DA = 4000        # trần số vị trí khoá quét mỗi khoá, chống treo
# Khoá ảnh trong JSON hydration, từ RIÊNG tới CHUNG.
_KHOA_ANH = ("images", "media", "gallery", "thumbnail", "image", "image_url",
             "imageUrl", "picture", "photo", "avatar")


def _blob_inline(html: str) -> str:
    """Gom MỌI inline <script> có chứa khoá giá — không phụ thuộc framework.

    Vì sao cần tầng này: dò container THEO TÊN (__NEXT_DATA__ / __NUXT__ /
    ld+json) chỉ bắt được site dùng đúng ba khuôn đó. Đo thật 28/08/2026,
    yody.vn nhét 350KB state vào một thẻ <script> TRẦN, không thuộc tính,
    mở đầu bằng `self.categories = [...]`; cả ba khuôn trên đều trượt, mà giá
    thì nằm trong chuỗi JSON nên tầng browser bóc-theo-giá cũng ra 0 (giá
    không có thẻ <a> anh em nào bên cạnh). Quét theo NỘI DUNG thay vì theo tên
    container là luật chung, không phải luật riêng cho yody.
    """
    ra = [m.group(1) for m in _SCRIPT.finditer(html)
          if any(k in m.group(1) for k in _KHOA_GIA)]
    return chr(10).join(ra)


def html_data(html: str, toi_da: int, log: list, base: str = "", im=True) -> list[dict]:
    out = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            _duyet_ld(json.loads(m.group(1).strip()), out, base)
        except ValueError:
            continue
    out = [p for p in out if p["ten"] and (p["gia"] or p["gia_goc"])]
    if im:
        log.append(f"jsonld: {len(out)}")
    if out:
        return out[:toi_da]

    blob = ""
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if m:
        blob = m.group(1)
    else:
        ch = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', html, re.S)
        if ch:
            blob = "".join(ch).encode("utf-8", "ignore").decode("unicode_escape", "ignore")
            blob = blob.encode("latin-1", "ignore").decode("utf-8", "ignore")
    if not m and not blob:
        m2 = re.search(r'window\.__NUXT__\s*=\s*(.*?);?\s*</script>', html, re.S)
        blob = m2.group(1) if m2 else ""
    nhan = "next/nuxt"
    if not blob:                       # không khuôn nào khớp -> quét theo nội dung
        blob = _blob_inline(html)
        nhan = "inline-script"
    if blob:
        seen = []
        for khoa in _KHOA_GIA:
            for o in _objects(blob, khoa, so_luong=_QUET_TOI_DA):
                ten = o.get("name") or o.get("productName") or o.get("title")
                gia = (o.get("price") or o.get("salePrice")
                       or o.get("final_price") or o.get("sale_price"))
                if not ten or not gia or str(ten)[:60] in seen:
                    continue
                seen.append(str(ten)[:60])
                link = o.get("slug") or o.get("url") or o.get("handle") or ""
                # slug thường là tương đối -> ghép về tuyệt đối cho người dùng bấm được
                if base and link and not str(link).startswith("http"):
                    link = base.rstrip("/") + "/" + str(link).lstrip("/")
                anh = next((o[k] for k in _KHOA_ANH if o.get(k)), "")
                out.append(_sp(ten, gia,
                               o.get("originalPrice") or o.get("regular_price")
                               or o.get("compare_at_price"),
                               link, anh, o.get("sku"), base))
                if len(out) >= toi_da:
                    break
            if len(out) >= toi_da:
                break
        if im:
            log.append(f"html_data({nhan}): {len(out)}")
    return out[:toi_da]


# ───────────────── tầng 3: bóc theo mẫu giá trên HTML ─────────────────
_A = re.compile(r'<a\b[^>]*href="([^"#]{4,300})"[^>]*>(.*?)</a>', re.S | re.I)
_IMG = re.compile(r"<img\b[^>]*>", re.I)


def _boc_theo_gia(html: str, base: str, toi_da: int) -> list[dict]:
    """Từ MỖI GIÁ, lùi lại tìm thẻ <a> có chữ gần nhất — đó là tên + link sản phẩm.

    Vì sao đi ngược từ giá chứ không quét thẻ <a>: đo thật trên vascara.com,
    giá KHÔNG nằm trong <a> mà là thẻ anh em kề bên:
        <h2><a href="...">Túi mini twin buckle</a></h2>
        <div class="price"><div class="ins">1.135.250đ</div></div>
    Quét <a> rồi tìm giá bên trong sẽ ra 0. Đi ngược từ giá thì đúng 19/19.
    Không phụ thuộc class/id nên site đổi giao diện vẫn chạy.

    ẢNH — sửa 06/09/2026, lỗi cũ GÁN NHẦM chứ không phải thiếu: bản cũ dùng
    `re.search('<img...')` nên lấy thẻ <img> ĐẦU cửa sổ 1800 ký tự, mà thẻ đầu
    cửa sổ thường thuộc SẢN PHẨM LIỀN TRƯỚC. Đo trên vascara: "Kính mát" bị gán
    ảnh "Giày sandals" — sheet vẫn đủ cột, nhìn không ra là sai. Ảnh đúng là thẻ
    <img> GẦN GIÁ NHẤT, tức thẻ CUỐI cửa sổ.
    """
    out, seen = [], set()
    for m in _GIA.finditer(html):
        cua_so = html[max(0, m.start() - 1800):m.start()]
        ten = link = ""
        for am in _A.finditer(cua_so):          # thẻ <a> CUỐI CÙNG có chữ
            t = re.sub(r"\s+", " ", _THE.sub(" ", am.group(2))).strip()
            if t and not _GIA.search(t) and len(t) > 3:
                ten, link = t[:200], am.group(1)
        if not ten or ten.lower() in seen:
            continue
        seen.add(ten.lower())
        # gom các giá quanh đó -> thấp nhất là giá bán, cao nhất là giá gốc
        gan = sorted({_so(g) for g in _GIA.findall(html[max(0, m.start() - 200):m.start() + 260])
                      if _so(g)})
        anh = ""
        for the in _IMG.findall(cua_so):        # thẻ <img> CUỐI = gần giá nhất
            u = _anh_tu_the(the, base)
            if u:
                anh = u
        out.append(_sp(ten, gan[0] if gan else None,
                       gan[-1] if len(gan) > 1 else None, link, anh, "", base))
        if len(out) >= toi_da:
            break
    return out


_THE_MO = re.compile(r"<[a-z][a-z0-9]*\b[^>]*\bdata-price\s*=\s*\"([^\"]+)\"[^>]*>", re.I)
_ALT = re.compile(r'\balt\s*=\s*"([^"]{3,200})"', re.I)
_TITLE = re.compile(r'\btitle\s*=\s*"([^"]{3,200})"', re.I)


def _thuoc_tinh(the: str, ten: str) -> str:
    m = re.search(ten + r'\s*=\s*"([^"]*)"', the, re.I)
    return m.group(1).strip() if m else ""


def _boc_theo_data_attr(html: str, base: str, toi_da: int) -> list[dict]:
    """Bóc từ THUỘC TÍNH `data-price` / `data-pid` trên thẻ sản phẩm.

    Vì sao cần tầng này — đo thật 08/09/2026 trên charleskeith.vn/vn: HTML đã
    render của họ **không có một chữ giá nào**, 0 khớp cho mọi định dạng tiền
    (`1.799.000₫`, `₫1.799.000`, `… VND`). Nên `_boc_theo_gia` ra 0 và site bị
    kết luận "không cào được", trong khi trang có 24 thẻ sản phẩm đầy đủ.

    Giá nằm trong thuộc tính:
        <div class="product-tile" data-pid="CK2-90151648-1_STO.GR_M-VN"
             data-price="2650000.0" data-currency="VND" data-availability="in_stock">

    Đây là khuôn Salesforce Commerce Cloud (SFRA) — `data-pid` + `data-price`
    dùng ở rất nhiều web doanh nghiệp, nên là luật CHUNG theo cấu trúc, KHÔNG
    phải luật riêng cho charleskeith. Và nó ĐÁNG TIN HƠN `_boc_theo_gia`: giá
    đọc từ thuộc tính khai báo sẵn, không phải đoán theo khoảng cách văn bản.

    Tên lấy từ `alt` của ảnh — thẻ `<a>` ở đây bọc ảnh nên không có chữ nào.
    """
    out: list[dict] = []
    for m in _THE_MO.finditer(html):
        the, gia = m.group(0), m.group(1)
        sau = html[m.end():m.end() + 3000]
        am = re.search(r'<a\b[^>]*href="([^"#]{4,400})"', sau, re.I)
        the_img = re.search(r"<img[^>]*>", sau)
        anh = _anh_tu_the(the_img.group(0), base) if the_img else ""
        ten = ""
        for nguon in (the_img.group(0) if the_img else "", sau[:1500], the):
            t = _ALT.search(nguon) or _TITLE.search(nguon)
            if t and not _GIA.search(t.group(1)):
                ten = re.sub(r"\s+", " ", t.group(1)).strip()
                # alt ảnh hay có đuôi kỹ thuật ", hi-res" / ", lo-res" — đó là
                # tên FILE ẢNH, không phải tên sản phẩm.
                ten = re.sub(r",\s*(?:hi|lo|low|high)-res\s*$", "", ten, flags=re.I)
                break
        if not ten:
            continue
        out.append(_sp(ten, gia, _thuoc_tinh(the, "data-markdown-price") or None,
                       am.group(1) if am else "", anh,
                       _thuoc_tinh(the, "data-pid"), base))
        if len(out) >= toi_da:
            break
    return out


_CUON_LAN = 6          # số lần cuộn xuống để kích lazy-load
_CUON_NGHI = 700       # ms nghỉ giữa mỗi lần cuộn


def _cuon_trang(page):
    """Cuộn xuống nhiều lần để trang tự nạp thêm sản phẩm.

    Vì sao cần: `network_idle` chỉ chờ mạng lặng SAU khi tải xong khung trang.
    Web bán hàng ngày nay nạp sản phẩm theo kiểu lazy-load/infinite-scroll —
    không cuộn thì DOM chỉ có vài sản phẩm đầu, hoặc rỗng hẳn. Đo thật
    08/09/2026: pedro.com render ra vỏn vẹn 12.349 ký tự, tức vỏ SPA chưa có
    hàng nào.

    Luật CHUNG cho mọi SPA, không phụ thuộc selector hay site nào. Lỗi thì bỏ
    qua: cuộn là để lấy THÊM, hỏng bước này không được làm chết cả lượt fetch.
    """
    try:
        for _ in range(_CUON_LAN):
            page.mouse.wheel(0, 20000)
            page.wait_for_timeout(_CUON_NGHI)
    except Exception:  # noqa: BLE001
        pass
    return page


def qua_browser(url: str, toi_da: int, log: list) -> list[dict]:
    from scrapling.fetchers import DynamicFetcher, StealthyFetcher
    base = _goc(url)
    for ten_tang, fn in (("browser", DynamicFetcher), ("browser_stealth", StealthyFetcher)):
        try:
            p = fn.fetch(url, headless=True, network_idle=True, timeout=70000,
                         page_action=_cuon_trang, wait=1500)
            h = str(p.html_content)
            if int(getattr(p, "status", 0) or 0) >= 400:
                log.append(f"{ten_tang}: HTTP {p.status}")
                continue
            sp = (html_data(h, toi_da, log, base)
                  or _boc_theo_data_attr(h, base, toi_da)
                  or _boc_theo_gia(h, base, toi_da))
            log.append(f"{ten_tang}: {len(sp)} (html {len(h)})")
            if sp:
                return sp
        except Exception as e:  # noqa: BLE001
            log.append(f"{ten_tang}: loi {type(e).__name__}")
    return []


# ───────────────── tầng 5: mở rộng phạm vi bằng sitemap ─────────────────
# Khớp "sitemap_products_1.xml", "/sitemap/product", "/san-pham/" — nhưng KHÔNG
# khớp chữ "item" nằm giữa "sitemap" (s-item-ap). Bẫy này đã làm bản nháp nhận
# nhầm toàn bộ sitemap phẳng của vascara là sitemap sản phẩm.
_NHAN_SP = re.compile(r"(?:^|[/_.\-])(products?|san-pham|item)s?(?:[/_.\-]|$)", re.I)
_LA_SITEMAP = re.compile(r"sitemap|\.xml(?:\.gz)?$", re.I)


def _duong_dan(u: str) -> list[str]:
    return [x for x in u.split("//", 1)[-1].split("/")[1:] if x and "?" not in x]


def _sitemap(base: str, s: requests.Session, log: list, han_chot: float) -> tuple[list, list]:
    """Trả (url_co_nhan_san_pham, tất_cả_url). Đệ quy sitemap index tối đa 3 tầng.

    Lấy khai báo từ robots.txt trước — đó là nơi chủ site CHỦ ĐỘNG chỉ đường
    (vascara khai `www.` còn người dùng gõ không `www.`; juno khai
    `//sitemap` không đuôi .xml). Đoán mỗi `/sitemap.xml` là trượt cả hai.
    """
    khai: list[str] = []
    try:
        rb = s.get(base + "/robots.txt", timeout=12, headers=_UA).text
        khai = list(dict.fromkeys(re.findall(r"(?im)^\s*sitemap:\s*(\S+)", rb)))
    except Exception:  # noqa: BLE001
        pass
    hang = [(u, 0) for u in (khai or [base + "/sitemap.xml"])]
    da, sp, tat_ca = set(), [], []
    while hang and len(da) < 20 and time.time() < han_chot:
        u, sau = hang.pop(0)
        if u in da or sau > 2:
            continue
        da.add(u)
        try:
            r = s.get(u, timeout=20, headers=_UA)
            if r.status_code != 200 or "<loc" not in r.text[:5000]:
                continue
            locs = re.findall(r"<loc>\s*([^<]+?)\s*</loc>", r.text)
        except Exception as e:  # noqa: BLE001
            log.append(f"sitemap {u.rsplit('/', 1)[-1]}: loi {type(e).__name__}")
            continue
        con = [x for x in locs if _LA_SITEMAP.search(x) and x not in da]
        if con and len(con) >= max(1, len(locs) // 2):   # đây là sitemap index
            hang += [(c, sau + 1) for c in con[:12]]
            continue
        tat_ca += locs
        if _NHAN_SP.search(u):
            sp += locs
    sp = list(dict.fromkeys(sp))
    tat_ca = list(dict.fromkeys(tat_ca))
    # Sitemap PHẲNG (vascara: 1 file, 3.521 URL, không nhãn) -> vớt theo đường dẫn.
    # Nhưng phải ĐỦ NHIỀU mới tin: đo thật trên vascara, luật này chỉ vớt được 8
    # URL và cả 8 đều là landing page cũ ("/san-pham-moi-thang-10-2017"). Nhận
    # nhầm 8 URL đó là "danh sách sản phẩm" thì bước dò sau đó trượt sạch, rồi
    # cả site bị kết luận là không bóc được — trong khi nó có 3.521 URL.
    if not sp:
        vot = [u for u in tat_ca if _NHAN_SP.search("/" + "/".join(_duong_dan(u)[:1]))]
        sp = vot if len(vot) >= max(20, len(tat_ca) // 50) else []
    log.append(f"sitemap: {len(tat_ca)} url, {len(sp)} co nhan san pham")
    return sp, tat_ca


def _tron_bucket(urls: list[str], sau=1) -> list[str]:
    """Xếp xen kẽ theo nhóm đường dẫn đầu — để mẫu dò trải đều mọi ngành hàng
    chứ không dồn hết vào /khuyen-mai (bucket to nhất của vascara: 591 URL)."""
    nhom: dict[str, list[str]] = {}
    for u in urls:
        dd = _duong_dan(u)
        nhom.setdefault("/".join(dd[:sau]) if dd else "/", []).append(u)
    ra, i = [], 0
    while any(nhom.values()):
        for k in list(nhom):
            if i < len(nhom[k]):
                ra.append(nhom[k][i])
        i += 1
        if i > 4000:
            break
    return ra


def _tai_song_song(urls: list[str], s: requests.Session, han_chot: float):
    """Tải nhiều trang song song, dừng ngay khi hết ngân sách thời gian.

    Chia lô đúng bằng số luồng thay vì đẩy cả nghìn URL vào `map` một lần: hàm
    gọi hay `break` giữa chừng (đủ số sản phẩm rồi), mà `ThreadPoolExecutor` đã
    nhận việc thì lúc thoát `with` vẫn phải chờ cho xong — chia lô nên bỏ dở chỉ
    tốn tối đa một lô.
    """
    def lay(u):
        for lan in range(2):
            if time.time() >= han_chot:
                return u, ""
            try:
                r = s.get(u, timeout=20, headers=_UA)
                if r.status_code == 200:
                    return u, r.text
                # 429/503 = bị CHẶN TỐC ĐỘ, không phải trang không có. Đo thật
                # trên yody.vn: chạy 10 luồng thì ~70% trả 429, mà bản đầu coi
                # mọi mã khác 200 là rỗng -> mất ảnh của 89/120 sản phẩm và
                # KHÔNG có gì báo lỗi. Nghỉ một nhịp rồi thử lại là qua.
                if r.status_code in (429, 503) and lan == 0:
                    _CHAN[0] += 1
                    time.sleep(1.2)
                    continue
                return u, ""
            except Exception:  # noqa: BLE001
                return u, ""
        return u, ""

    i = 0
    while i < len(urls):
        if time.time() >= han_chot:
            return
        # TỰ GIẢM TỐC: site nào chặn (yody trả 429 hàng loạt ở 8 luồng) thì hạ
        # xuống 3 luồng và nghỉ giữa các lô. Cứ giữ nguyên tốc độ thì phần lớn
        # request trả 429, kết quả là thiếu ảnh mà nhìn vào không biết vì sao.
        luong = 3 if _CHAN[0] >= 5 else _LUONG
        with ThreadPoolExecutor(max_workers=luong) as ex:
            for u, h in ex.map(lay, urls[i:i + luong]):
                yield u, h
        i += luong
        if _CHAN[0] >= 5:
            time.sleep(0.4)


def _boc_trang_sp(html: str, url: str, base: str) -> dict | None:
    """Bóc MỘT trang sản phẩm — chỉ nhận dữ liệu CÓ CẤU TRÚC.

    Cố tình KHÔNG đoán giá bằng regex ở đây: trang sản phẩm nào cũng đầy giá
    (sản phẩm gợi ý, "mua kèm"), đoán bừa sẽ gán giá hàng xóm cho sản phẩm
    chính — sai âm thầm. Không có dấu hiệu sản phẩm thì trả None để hàm gọi
    biết đường chuyển sang tầng danh mục.
    """
    ra: list[dict] = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I):
        try:
            _duyet_ld(json.loads(m.group(1).strip()), ra, base)
        except ValueError:
            continue
    ra = [p for p in ra if p["ten"] and (p["gia"] or p["so_anh"])]
    if ra:
        p = max(ra, key=lambda x: (bool(x["gia"]), x["so_anh"]))
        p["link"] = p["link"] or url
        return p

    og = re.findall(r'<meta[^>]+(?:property|name)="((?:og|product):[^"]+)"[^>]*'
                    r'content="([^"]*)"', html)
    kv: dict[str, str] = {}
    anh: list[str] = []
    for k, v in og:
        if k.startswith("og:image") and not k.endswith(("alt", "width", "height", "type")):
            anh.append(v)
        kv.setdefault(k, v)
    gia = _so(kv.get("product:price:amount") or kv.get("og:price:amount"))
    la_sp = kv.get("og:type", "").lower() in ("product", "og:product") or bool(gia)
    ten = kv.get("og:title") or ""
    if ten and la_sp:
        return _sp(ten, gia, None, kv.get("og:url") or url,
                   _anh_tu_trang(html, base, ten) or anh, "", base)
    return None


def _chuan_ten(s) -> str:
    return re.sub(r"\W+", " ", str(s or "").lower(), flags=re.U).strip()


def _anh_tu_trang(html: str, base: str, ten: str = "") -> list[str]:
    """Gom album ảnh của một trang sản phẩm — chỉ từ khai báo CÓ CHỦ ĐÍCH.

    Ba nguồn, đều là khai báo chứ không phải đoán:
      1. og:image — site khai nhiều thẻ cho nhiều ảnh (juno 4 thẻ).
      2. ảnh trong JSON-LD Product (vascara 6 ảnh).
      3. thẻ <img> có `alt` TRÙNG TÊN SẢN PHẨM. Đo thật trên yody.vn: cả ba ảnh
         gallery đều là alt="Quần short nam đổi màu - Vàng - M", trong khi og
         chỉ khai đúng 1 ảnh. Đối chiếu theo alt là luật CHUNG (không phụ thuộc
         class/id/CDN) nên site đổi giao diện vẫn chạy.
    KHÔNG quét bừa mọi thẻ <img>: trang sản phẩm nào cũng đầy logo, banner,
    "sản phẩm gợi ý" — gom hết vào cột Ảnh thì còn tệ hơn thiếu ảnh.
    """
    ra: list[str] = []
    for k, v in re.findall(r'<meta[^>]+(?:property|name)="(og:image[^"]*)"[^>]*'
                           r'content="([^"]*)"', html):
        if not k.endswith(("alt", "width", "height", "type")):
            ra.append(v)
    nut: list[dict] = []
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>',
                         html, re.S | re.I):
        try:
            _duyet_ld(json.loads(m.group(1).strip()), nut, base)
        except ValueError:
            continue
    for p in nut:
        ra += p.get("anh_tat_ca") or []

    tn = _chuan_ten(ten)
    if len(tn) >= 8:
        for the in _IMG.findall(html):
            m = re.search(r'alt\s*=\s*"([^"]{4,200})"', the, re.I)
            if not m:
                continue
            an = _chuan_ten(m.group(1))
            if an and (an[:36].startswith(tn[:36]) or tn[:36].startswith(an[:36])):
                ra.append(_anh_tu_the(the, base))

    # Khử trùng BỎ QUA query: cùng một ảnh hay xuất hiện hai lần, một lần ở
    # og:image trần và một lần ở <img> kèm "?width=987" — đếm thành 2 là báo
    # cáo số ảnh sai.
    ra, thay = [_tuyet_doi(x, base) for x in ra], {}
    for u in ra:
        if u:
            thay.setdefault(u.split("?")[0], u)
    return list(thay.values())


def _sua_link(da_co: list[dict], locs: list[str], log: list) -> None:
    """Sửa link sai bằng cách đối chiếu slug với sitemap — KHÔNG tốn request nào.

    Vì sao cần: JSON hydration hay khai `slug` KHÔNG kèm tiền tố đường dẫn, mà
    tầng html_data thì ghép thẳng `base + slug`. Đo thật trên yody.vn 06/09/2026:
    slug "ao-polo-nam-co-v-..." ghép ra https://yody.vn/ao-polo-nam-co-v-... —
    HTTP 404, trong khi link thật là /product/ao-polo-nam-co-v-... Cả 90 sản
    phẩm vào sheet với link chết mà không có gì báo lỗi; người dùng bấm mới biết.
    Sitemap đã có sẵn URL thật nên chỉ cần khớp theo đoạn cuối đường dẫn.
    """
    chi_muc: dict[str, str] = {}
    dem_tien_to: dict[str, int] = {}
    for u in locs:
        dd = _duong_dan(u.split("?")[0])
        if not dd:
            continue
        chi_muc.setdefault(dd[-1].lower(), u)
        if len(dd) >= 2:
            dem_tien_to["/".join(dd[:-1])] = dem_tien_to.get("/".join(dd[:-1]), 0) + 1
    # Tiền tố áp đảo (yody: "product" chiếm 2.853/2.853) dùng để chữa cả những
    # sản phẩm KHÔNG có trong sitemap — sitemap không bao giờ liệt kê đủ 100%.
    tien_to, n = max(dem_tien_to.items(), key=lambda kv: kv[1], default=("", 0))
    ap_dao = tien_to if n >= max(10, len(locs) * 0.8) else ""
    sua = doan = 0
    for p in da_co:
        cu = (p.get("link") or "").split("?")[0].rstrip("/")
        dd = _duong_dan(cu)
        if not cu or not dd:
            continue
        moi = chi_muc.get(dd[-1].lower())
        if moi is None and ap_dao and len(dd) == 1:
            moi = f"{_goc(cu)}/{ap_dao}/{dd[-1]}"
            doan += 1
        if moi and moi.split("?")[0].rstrip("/") != cu:
            p["link"] = moi
            sua += 1
    if sua:
        log.append(f"sua_link theo sitemap: {sua} link"
                   + (f" (trong do {doan} suy ra tu tien to '/{ap_dao}/')" if doan else ""))


def sitemap_bo_sung(base: str, da_co: list[dict], toi_da: int, log: list,
                    han_chot: float) -> str:
    """Mở rộng phạm vi: sitemap -> trang sản phẩm -> trang danh mục -> bù ảnh.

    Trả tên tầng đã đóng góp thêm, và ghi thẳng vào `da_co`.
    """
    s = requests.Session()
    tang = ""
    sp_url, tat_ca = _sitemap(base, s, log, han_chot)
    if not tat_ca:
        return tang
    _sua_link(da_co, sp_url or tat_ca, log)
    da_lay = {(p.get("link") or "").rstrip("/") for p in da_co if p.get("link")}

    # ── 5a. TRANG SẢN PHẨM: chuẩn nhất, và là nơi DUY NHẤT có đủ ảnh ──
    # Dò rồi mới bung, và quyết định theo TỪNG NHÓM đường dẫn chứ không theo tỉ
    # lệ chung: sitemap phẳng của vascara trộn lẫn 235 URL giày với 591 URL bài
    # khuyến mãi, lấy tỉ lệ chung sẽ kết luận "site này không bóc được" trong
    # khi thật ra chỉ là dò trúng nhóm bài viết.
    goc_sp = sp_url or [u for u in tat_ca if len(_duong_dan(u)) >= 2]
    goc_sp = [u for u in goc_sp if u.rstrip("/") not in da_lay]
    nhom: dict[str, list[str]] = {}
    for u in goc_sp:
        dd = _duong_dan(u)
        nhom.setdefault(dd[0] if dd else "/", []).append(u)
    xep = sorted(nhom.items(), key=lambda kv: -len(kv[1]))[:14]
    # Ít nhóm thì phải dò SÂU hơn mỗi nhóm: yody gom cả 2.853 URL sản phẩm vào
    # đúng một nhóm /product, dò 2 trang rồi kết luận là quá mỏng.
    moi_nhom = max(2, 12 // max(1, len(xep)))
    mau = [u for k, v in xep for u in v[:moi_nhom]]
    if mau and time.time() < han_chot:
        trung, thuoc = [], {}
        for u, h in _tai_song_song(mau, s, han_chot):
            p = _boc_trang_sp(h, u, base) if h else None
            if p:
                trung.append(p)
                dd = _duong_dan(u)
                thuoc[dd[0] if dd else "/"] = True
        log.append(f"sitemap_sp do {len(mau)} trang: {len(trung)} trung, "
                   f"{len(thuoc)}/{len(xep)} nhom co san pham")
        if trung:
            _gop(da_co, trung, toi_da)
            tang = "sitemap_sp"
            con = [u for u in _tron_bucket([u for k in thuoc for u in nhom[k]])
                   if u not in set(mau)]
            them = []
            for u, h in _tai_song_song(con, s, han_chot):
                p = _boc_trang_sp(h, u, base) if h else None
                if p:
                    them.append(p)
                if len(da_co) + len(them) >= toi_da:
                    break
            _gop(da_co, them, toi_da)
            log.append(f"sitemap_sp: tong {len(da_co)} sp")

    # ── 5b. TRANG DANH MỤC: 1 request ra vài chục sp, rẻ hơn nhiều lần ──
    if len(da_co) < toi_da and time.time() < han_chot:
        bo = set(sp_url)
        dm = _tron_bucket([u for u in tat_ca
                           if u not in bo and 1 <= len(_duong_dan(u)) <= 2])[:80]
        truoc, thu = len(da_co), 0
        for u, h in _tai_song_song(dm, s, han_chot):
            if not h:
                continue
            thu += 1
            got = html_data(h, toi_da, log, base, im=False) or _boc_theo_gia(h, base, toi_da)
            _gop(da_co, got, toi_da)
            if len(da_co) >= toi_da:
                break
        if len(da_co) > truoc:
            log.append(f"sitemap_dm quet {thu} trang danh muc: +{len(da_co) - truoc} sp")
            tang = f"{tang}+sitemap_dm" if tang else "sitemap_dm"

    # Chữa link LẦN NỮA: tầng 5b vừa thêm sản phẩm mới, mà chúng cũng lấy từ
    # JSON hydration nên dính đúng lỗi slug thiếu tiền tố. Bỏ bước này thì
    # những sản phẩm thêm sau vừa vào sheet với link chết, vừa không bù được ảnh.
    _sua_link(da_co, sp_url or tat_ca, log)

    # ── 5c. BÙ ẢNH: sp lấy từ trang danh mục chỉ có 1 ảnh thumbnail ──
    # yody/juno không để giá ở trang sản phẩm nên phải lấy giá từ trang danh mục,
    # nhưng album ảnh thì chỉ trang sản phẩm mới có. Còn ngân sách thì đi bù.
    thieu_anh = [p for p in da_co if p.get("link") and p.get("so_anh", 0) <= 1]
    if thieu_anh and time.time() < han_chot:
        chi_muc = {p["link"]: p for p in thieu_anh}
        bu = 0
        for u, h in _tai_song_song([p["link"] for p in thieu_anh], s, han_chot):
            p = chi_muc.get(u)
            ds = _anh_tu_trang(h, base, p.get("ten") if p else "") if h else []
            if p is not None and len(ds) > p.get("so_anh", 0):
                p["anh"], p["anh_tat_ca"], p["so_anh"] = ds[0], ds[:20], len(ds)
                bu += 1
        if bu:
            log.append(f"bu_anh: {bu}/{len(thieu_anh)} sp lay them duoc album")
            tang = f"{tang}+bu_anh" if tang else "bu_anh"
    return tang


def main() -> int:
    try:
        a = json.loads(sys.stdin.read() or "{}")
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": f"input khong phai JSON: {e}"}))
        return 1
    url = (a.get("url") or "").strip()
    if not url:
        print(json.dumps({"ok": False, "error": "thieu url"}))
        return 1
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    toi_da = max(1, min(int(a.get("max_products") or 100), 1000))
    ngan_sach = max(20, min(float(a.get("budget_s") or _NGAN_SACH_MAC_DINH), 600))
    han_chot = time.time() + ngan_sach
    base = _goc(url)
    log: list[str] = []

    sp = catalog_json(base, toi_da, log)
    tang = "catalog_json" if sp else ""
    if not sp:
        try:
            h = requests.get(url, timeout=25, headers=_UA).text
            sp = html_data(h, toi_da, log, base)
            tang = "html_data" if sp else ""
            if not sp:
                # Bóc-theo-giá vốn chỉ chạy sau khi đã render browser. Nhưng site
                # render sẵn phía server thì HTML vừa tải VỀ ĐÃ có giá — thử ngay
                # ở đây tiết kiệm hẳn một lượt bật trình duyệt (~30-70s).
                sp = _boc_theo_data_attr(h, base, toi_da)
                if sp:
                    log.append(f"boc_theo_data_attr(html tho): {len(sp)}")
                    tang = "html_data_attr"
                else:
                    sp = _boc_theo_gia(h, base, toi_da)
                    log.append(f"boc_theo_gia(html tho): {len(sp)}")
                    tang = "html_gia" if sp else ""
        except Exception as e:  # noqa: BLE001
            log.append(f"html_data: fetch loi {type(e).__name__}")

    # Bốn tầng trên chỉ đọc MỘT trang. Ra ít hơn số người dùng xin nghĩa là còn
    # thiếu chứ KHÔNG phải site chỉ có bấy nhiêu — mở rộng bằng sitemap.
    thieu = len(sp) < toi_da
    if thieu and time.time() < han_chot:
        them = sitemap_bo_sung(base, sp, toi_da, log, han_chot)
        if them:
            tang = f"{tang}+{them}" if tang else them

    # LEO THANG SANG BROWSER KHI KẾT QUẢ ĐÁNG NGỜ, không phải chỉ khi rỗng.
    #
    # Đo thật 08/09/2026 trên charleskeith.vn/vn: tầng `html_gia` bắt được đúng
    # MỘT thứ — cái banner "Nhận ngay túi tote canvas độc quyền* 1.799.000đ".
    # `sp` không rỗng nên luật cũ ("chỉ bật browser khi sp rỗng") bỏ qua tầng
    # browser, trong khi browser render ra 992.205 ký tự đầy sản phẩm thật.
    #
    # Cùng họ với lỗi actor TikTok cùng ngày: cơ chế leo thang chờ tới lúc RỖNG
    # thì không bao giờ chạy, vì hỏng-một-phần không bao giờ rỗng. Ngưỡng phải
    # đặt theo SẢN LƯỢNG ĐÁNG NGỜ.
    co_cau_truc = any(t in tang for t in ("catalog_json", "html_data",
                                          "html_data_attr", "sitemap_sp"))
    if not sp or (len(sp) <= 2 and not co_cau_truc):
        got = qua_browser(url, toi_da, log)
        # Chỉ nhận nếu browser ra NHIỀU HƠN — không được để tầng đắt hơn làm
        # nghèo kết quả đi.
        if len(got) > len(sp):
            sp, tang = got, "browser"
        elif not sp:
            tang = ""

    het = time.time() >= han_chot
    # CHỐT CHẶN DƯƠNG TÍNH GIẢ. Tầng bóc-theo-giá chỉ cần thấy "1.799.000đ"
    # cạnh một thẻ <a> là dựng ra "sản phẩm". Đo thật 06/09/2026: vnexpress.net
    # ra 1 "sản phẩm" là tiêu đề bài báo, charleskeith.vn ra 1 banner khuyến mãi
    # ("Nhận ngay túi tote canvas độc quyền*"). Cả hai đều `ok=true`, và Mark sẽ
    # hồn nhiên báo "cào được 1 sản phẩm" — sai mà không ai thấy. Vài kết quả lẻ
    # KHÔNG có tầng cấu trúc nào chống lưng thì phải coi là CHƯA cào được.
    co_cau_truc = any(t in tang for t in ("catalog_json", "html_data",
                                          "html_data_attr", "sitemap_sp"))
    nghi_ngo = bool(sp) and not co_cau_truc and len(sp) <= 2
    print(json.dumps({
        "ok": bool(sp) and not nghi_ngo, "url": url, "tang": tang,
        "nghi_ngo": nghi_ngo, "so_san_pham": len(sp),
        "so_co_anh": sum(1 for p in sp if p.get("anh")),
        "tong_so_anh": sum(p.get("so_anh", 0) for p in sp),
        "het_ngan_sach": het, "ngan_sach_s": ngan_sach, "bi_chan_toc_do": _CHAN[0],
        "san_pham": sp, "nhat_ky": log,
        "error": "" if (sp and not nghi_ngo) else (
            f"Chỉ ra {len(sp)} kết quả và đều từ tầng ĐOÁN THEO MẪU GIÁ, không tầng dữ "
            "liệu có cấu trúc nào chống lưng — nhiều khả năng đây KHÔNG phải trang danh "
            "mục sản phẩm (bắt nhầm tiêu đề bài viết hoặc banner khuyến mãi). Xem "
            "`san_pham` để tự đánh giá. Cũng có thể là shop rất nhỏ thật — nói rõ sự mơ "
            "hồ này, đừng khẳng định chiều nào." if nghi_ngo else
            "Không tầng nào bóc được sản phẩm. Xem `nhat_ky` để biết đã thử gì. ĐỪNG kết "
            "luận site không có sản phẩm — rất có thể chỉ là chưa bóc được."),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
