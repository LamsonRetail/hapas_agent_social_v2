"""Tool `soi_san`: giá, sản phẩm bán chạy và shop nổi bật trên Shopee theo từ khoá.

Vì sao cần — câu hỏi thật trong sổ audit mà Mark chưa làm được: "scout thị trường quà
tặng 20.10 năm nay", "đối thủ bán gì chạy". Mạng xã hội cho biết người ta NÓI gì; sàn cho
biết người ta MUA gì, với giá bao nhiêu.

Nguồn — đo thật 25/09/2026:
  • `gio21~shopee-scraper` (nhiều người dùng nhất) KHÔNG DÙNG ĐƯỢC ở gói FREE: log ghi
    "Free plan — serving up to 20 real products from the shared cache. Live scraping
    needs a paid Apify plan". "túi xách nữ" ra kết quả chỉ vì có người khác từng tìm;
    "quà tặng 20/10" ra 0. Hỏng kiểu không báo lỗi — chỉ lặng lẽ rỗng.
  • `zen-studio~shopee-product-scraper` (đang dùng): cào THẬT ở gói FREE, 20 sản phẩm
    trong 12 giây, 0,005 USD/sản phẩm. Có `sort=best_selling` — xếp hạng bán chạy của
    CHÍNH Shopee.
  • Shopee KHÔNG trả số đã bán qua nguồn này (`sold`, `historicalSold`, `soldMonthly`,
    `globalSold` đều trống). Dùng thứ hạng bán chạy của Shopee + số lượt đánh giá làm
    chỉ báo, và phải NÓI RÕ là không có số đã bán.
  • Lạc đề NẶNG và không ổn định: cùng "quà tặng 20/10" xếp theo bán chạy, lần đầu ra
    đúng set quà, lần sau ra toàn khăn tắm. Nên mặc định xếp theo LIÊN QUAN, đánh dấu từng
    sản phẩm có khớp từ khoá không (`_khop`), và chỉ tổng hợp trên hàng khớp.
"""
from __future__ import annotations

import collections
import datetime
import re
import statistics
import time
import unicodedata

import apify_tool as A
import chi_phi_tool
import memory_store

from tools.registry import registry, tool_error, tool_result  # type: ignore

ACTOR = "zen-studio~shopee-product-scraper"
_GIA = 0.005
_GIA_KHOI_DONG = 0.005
_XEP = {"ban_chay": "best_selling", "lien_quan": "relevance", "gia_thap": "price_low_to_high",
        "gia_cao": "price_high_to_low", "moi": "newest"}
# Mốc giá (VND) để chia khoảng — hợp ngành phụ kiện/quà tặng của Lamson Retail.
_MOC = [100_000, 300_000, 500_000, 1_000_000, 2_000_000]


def _so(v, kieu=int):
    try:
        return kieu(v or 0)
    except (TypeError, ValueError):
        return kieu(0)


def _nhan(v: int) -> str:
    return f"{v // 1000}k" if v < 1_000_000 else f"{v / 1_000_000:g} triệu"


def _khoang(gia: float) -> str:
    duoi = 0
    for m in _MOC:
        if gia < m:
            return f"{_nhan(duoi)}–{_nhan(m)}" if duoi else f"dưới {_nhan(m)}"
        duoi = m
    return f"từ {_nhan(_MOC[-1])}"


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower().replace("đ", "d"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _khop(ten: str, kw: list[str]) -> bool:
    """Tên sản phẩm có chứa đủ các chữ của ít nhất một từ khoá không (bỏ dấu, bỏ số).

    Cần vì Shopee trả lạc đề nặng: đo thật 25/09/2026, "quà tặng 20/10" xếp theo bán chạy
    ra toàn khăn tắm (lượt thử trước đó với cùng đầu vào lại ra đúng set quà).
    """
    t = _bo_dau(ten)
    for k in kw:
        chu = [w for w in re.findall(r"\w+", _bo_dau(k)) if not any(c.isdigit() for c in w)]
        if chu and all(w in t for w in chu):
            return True
    return False


def _tong_hop(sp: list[dict]) -> dict:
    if not sp:
        return {}
    ra: dict = {}
    gia = sorted(s["gia"] for s in sp if s["gia"])
    if gia:
        q = statistics.quantiles(gia, n=4) if len(gia) >= 4 else [gia[0], gia[-1]]
        ra["gia"] = {"thap_nhat": gia[0], "pho_bien_tu": int(q[0]),
                     "trung_vi": int(statistics.median(gia)), "pho_bien_den": int(q[-1]),
                     "cao_nhat": gia[-1]}
        dem = collections.Counter(_khoang(g) for g in gia)
        thu_tu = [_khoang(m - 1) for m in _MOC] + [_khoang(_MOC[-1])]
        ra["phan_bo_gia"] = {k: dem[k] for k in thu_tu if dem.get(k)}
    giam = [s["giam_pct"] for s in sp if s["giam_pct"]]
    if giam:
        ra["dang_giam_gia"] = {"so_sp": len(giam), "giam_tb_pct": round(statistics.mean(giam))}
    diem = [s["diem"] for s in sp if s["diem"]]
    if diem:
        ra["diem_danh_gia_tb"] = round(statistics.mean(diem), 2)
    # `sp` giữ nguyên THỨ TỰ Shopee trả về; khi xếp theo bán chạy thì đó là thứ hạng bán
    # chạy của chính Shopee — thứ tốt nhất có được khi không có số đã bán.
    ra["dau_bang"] = [{k: s[k] for k in ("hang", "ten", "gia", "giam_pct", "luot_danh_gia",
                                         "diem", "shop", "chinh_hang", "link")} for s in sp[:8]]
    ra["nhieu_danh_gia_nhat"] = [
        {k: s[k] for k in ("ten", "gia", "luot_danh_gia", "shop", "link")}
        for s in sorted(sp, key=lambda s: -s["luot_danh_gia"])[:5]]
    shop = collections.defaultdict(lambda: {"so_sp": 0, "luot_danh_gia": 0, "chinh_hang": False})
    for s in sp:
        shop[s["shop"]]["so_sp"] += 1
        shop[s["shop"]]["luot_danh_gia"] += s["luot_danh_gia"]
        shop[s["shop"]]["chinh_hang"] |= s["chinh_hang"]
    ra["shop_noi_bat"] = [{"shop": k, **v} for k, v in
                          sorted(shop.items(), key=lambda x: -x[1]["luot_danh_gia"])[:6] if k]
    th = collections.Counter(s["thuong_hieu"] for s in sp if s["thuong_hieu"])
    if th:
        ra["thuong_hieu_xuat_hien"] = [f"{k} ({v})" for k, v in th.most_common(8)]
    return ra


SCHEMA = {
    "name": "soi_san",
    "description": (
        "Xem THỊ TRƯỜNG trên Shopee Việt Nam theo từ khoá sản phẩm: khoảng giá phổ biến, "
        "sản phẩm đầu bảng bán chạy, shop và thương hiệu nổi bật, mức giảm giá, điểm đánh "
        "giá. Dùng cho: 'quà 20/10 đang bán giá bao nhiêu', 'túi xách nữ trên sàn giá thế "
        "nào', 'đối thủ bán gì chạy', 'nên định giá set quà bao nhiêu'.\n"
        "KHÁC `social_listen` (người ta NÓI gì trên mạng xã hội) — tool này là người ta MUA "
        "gì, giá bao nhiêu. Chỉ có Shopee, CHƯA có Lazada/TikTok Shop: hỏi sàn khác thì nói "
        "thẳng là chưa hỗ trợ.\n"
        "`tu_khoa`: cụm từ người mua hay gõ trên Shopee, cụ thể là tốt ('túi xách nữ công "
        "sở', 'quà tặng 20/10 cho mẹ'), tối đa 3 cụm.\n"
        "KHI TRẢ LỜI: nguồn này KHÔNG có số đã bán — đừng bịa. `luot_danh_gia` là chỉ báo "
        "gián tiếp cho lượng bán; `dau_bang` chỉ là thứ hạng bán chạy khi `xep_theo`="
        "'ban_chay'. Nói rõ khi nhắc tới 'bán chạy'. `chinh_hang`=true là Shopee Mall. "
        "`tong_hop` chỉ tính sản phẩm có tên khớp từ khoá; `canh_bao_lac_de` có nội dung thì "
        "BẮT BUỘC nói ra và đề xuất từ khoá cụ thể hơn. `bi_co_theo_tran` có nội dung thì "
        "nói ra. Gửi NGUYÊN `sheet_url`."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tu_khoa": {"type": "array", "items": {"type": "string"},
                        "description": "Cụm từ tìm trên Shopee, tối đa 3."},
            "xep_theo": {"type": "string", "enum": list(_XEP),
                         "description": ("Mặc định 'lien_quan'. Chỉ đặt 'ban_chay' khi người "
                                         "dùng hỏi đúng 'bán chạy nhất' — cách xếp này lạc đề "
                                         "nhiều hơn.")},
            "so_san_pham": {"type": "integer",
                            "description": "Tổng số sản phẩm (mặc định 30; tự co theo trần chi phí)."},
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
        },
        "required": ["tu_khoa"],
    },
}

_HEADER = ["Hạng", "Sản phẩm", "Khớp từ khoá", "Giá (VND)", "Giá gốc", "Giảm %",
           "Lượt đánh giá", "Lượt thích", "Điểm", "Shop", "Shopee Mall", "Thương hiệu",
           "Nơi gửi", "Link"]


def _handle(args: dict, **_kwargs) -> str:
    kw = args.get("tu_khoa") or []
    kw = [kw] if isinstance(kw, str) else [str(k).strip() for k in kw if str(k).strip()][:3]
    if not kw:
        return tool_error("Thiếu `tu_khoa` (cụm từ sản phẩm cần tìm trên Shopee).")
    tran_bai, tran_usd = A._tran()
    xep = str(args.get("xep_theo") or "lien_quan")
    xep = xep if xep in _XEP else "lien_quan"
    try:
        xin = max(10, int(args.get("so_san_pham") or 30))
    except (TypeError, ValueError):
        xin = 30
    # +1e-9: (0,3 - 0,005) / 0,005 ra 58,999… trong số thực, cắt xuống là thiếu 1 sản phẩm.
    vua_tien = max(1, int((tran_usd - _GIA_KHOI_DONG) / _GIA + 1e-9))
    n = min(xin, tran_bai, vua_tien)
    bi_co = None
    if n < xin:
        bi_co = (f"Xin {xin} sản phẩm, lấy {n} để nằm trong trần hiện tại "
                 f"({tran_bai} bài · {tran_usd:g} USD mỗi lượt). Chủ agent nâng được ở console.")
    est = _GIA_KHOI_DONG + _GIA * n
    bat_dau = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=5)
    t0 = time.monotonic()
    try:
        raw = A._call(ACTOR, {"searchTerms": kw, "region": "VN", "maxItems": n,
                              "sort": _XEP[xep]}, n)
    except Exception as e:  # noqa: BLE001
        if "below-minimum" in str(e):
            return tool_error(
                f"Trần chi phí mỗi lượt trên console ({tran_usd:g} USD) thấp hơn mức tối thiểu "
                "nguồn Shopee đòi. Nhờ chủ agent nâng trần ở console rồi thử lại.")
        return tool_error(f"Không đọc được Shopee: {type(e).__name__}: {e}"[:300])

    sp = []
    for it in raw:
        if not it.get("name"):
            continue
        sp.append({
            "hang": len(sp) + 1, "ten": str(it.get("name"))[:200],
            "gia": int(_so(it.get("price"), float)),
            "gia_goc": int(_so(it.get("priceBeforeDiscount"), float)),
            "giam_pct": _so(it.get("discountPercent")),
            "diem": round(_so(it.get("rating"), float), 2),
            "luot_danh_gia": _so(it.get("ratingCount")), "luot_thich": _so(it.get("likedCount")),
            "shop": str(it.get("shopName") or ""), "chinh_hang": bool(it.get("isOfficialShop")),
            "thuong_hieu": str(it.get("brand") or ""), "noi_gui": str(it.get("shopLocation") or ""),
            "link": it.get("url") or "",
            "khop": _khop(str(it.get("name")), kw),
        })
    # Tổng hợp trên sản phẩm ĐÚNG từ khoá; Sheet vẫn giữ đủ, có cột đánh dấu.
    dung = [s for s in sp if s["khop"]]
    lac = [s["ten"][:80] for s in sp if not s["khop"]]
    canh_bao = None
    if sp and len(dung) < 5:
        canh_bao = (f"Chỉ {len(dung)}/{len(sp)} sản phẩm có tên khớp từ khoá — Shopee trả "
                    "phần lớn là hàng lạc đề. Tổng hợp dưới đây tính trên TẤT CẢ nên không "
                    "đáng tin; đề xuất đổi từ khoá cụ thể hơn.")
        dung = sp

    thuc = A._chi_phi_thuc([ACTOR], bat_dau, est)
    if thuc and thuc.get("cham_tran") and len(raw) >= n:
        thuc = {**thuc, "cham_tran": 0}
    chi_phi_tool.ghi(queries=kw, platforms=["shopee"], date_range="hiện tại", thuc=thuc, est=est)

    url, granted, loi = None, False, None
    if sp:
        title = (args.get("title") or "").strip() or \
            f"Shopee · {', '.join(kw)[:40]} · {datetime.datetime.now(A._VN_TZ):%d-%m-%Y}"
        rows = [list(_HEADER)] + [[
            s["hang"], s["ten"], "có" if s["khop"] else "lạc đề", s["gia"],
            s["gia_goc"] or "", s["giam_pct"] or "",
            s["luot_danh_gia"], s["luot_thich"], s["diem"] or "", s["shop"],
            "có" if s["chinh_hang"] else "", s["thuong_hieu"], s["noi_gui"], s["link"]]
            for s in sp]
        try:
            tok, url = A._create_sheet(title)
            A._write_values(tok, A._first_sheet_id(tok), rows)
            sender = memory_store.get_current_sender()
            granted = A._grant(tok, sender) if sender else False
        except Exception as e:  # noqa: BLE001
            loi = f"Tạo/ghi sheet thất bại: {type(e).__name__}: {e}"[:250]

    return tool_result(
        success=bool(sp) and not loi, tu_khoa=kw, xep_theo=xep, so_san_pham=len(sp),
        khong_co_so_da_ban=True, bi_co_theo_tran=bi_co, tong_hop=_tong_hop(dung),
        so_sp_khop_tu_khoa=sum(s["khop"] for s in sp), vi_du_lac_de=lac[:5] or None,
        canh_bao_lac_de=canh_bao, loi=loi,
        sheet_url=url, granted=granted,
        uoc_tinh_chi_phi_usd=round(est, 3),
        chi_phi_thuc_usd=thuc["usd"] if thuc and thuc.get("so_run") else None,
        cham_tran_chi_phi=bool(thuc and thuc.get("cham_tran")),
        chi_phi=A._dong_chi_phi(thuc, est), giay=round(time.monotonic() - t0, 1),
        note=None if sp else "Shopee không trả sản phẩm nào cho các từ khoá này.",
    )


def _available() -> bool:
    return A._available()


try:
    registry.register(
        name="soi_san", toolset="social", schema=SCHEMA, handler=_handle,
        check_fn=_available, requires_env=[], is_async=False,
        description="Giá, sản phẩm bán chạy và shop nổi bật trên Shopee theo từ khoá",
        emoji="\U0001f6d2", override=True,
    )
except Exception as e:  # noqa: BLE001
    print(f"[shopee_tool] register warning: {e}")
