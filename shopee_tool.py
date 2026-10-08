"""Tool `soi_san`: thị trường Shopee theo từ khoá, hoặc soi sản phẩm cụ thể từ link Shopee/TikTok Shop.

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

Soi SẢN PHẨM CỤ THỂ từ link (Shopee, TikTok Shop): xem `san_link.py` — nguồn nào dùng được,
nguồn nào hỏng, và vì sao TikTok Shop chỉ soi theo link chứ không tìm theo từ khoá.
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
import san_link
import trinh_bay_sheet as TB

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
        "gì, giá bao nhiêu. Tìm theo từ khoá chỉ có Shopee; TikTok Shop chỉ soi theo link; "
        "CHƯA có Lazada: hỏi sàn khác thì nói thẳng là chưa hỗ trợ.\n"
        "`tu_khoa`: cụm từ người mua hay gõ trên Shopee, cụ thể là tốt ('túi xách nữ công "
        "sở', 'quà tặng 20/10 cho mẹ'), tối đa 3 cụm.\n"
        "CÓ LINK SẢN PHẨM (Shopee hoặc TikTok Shop, kể cả link rút gọn) → truyền vào `link` "
        "để soi ĐÚNG sản phẩm đó: khách khen/chê gì, số sao, phân loại hay mua, số đã bán. "
        "CHỈ ĐÁNH GIÁ SẢN PHẨM — đừng nhận xét về shop (follower, tổng đã bán, điểm shop) trừ "
        "khi người dùng hỏi về shop; khi đó đặt `gom_shop`=true. Shopee theo link có số đã "
        "bán (`da_ban`) khi nguồn trả; giá "
        "chỉ lấy được khi tìm ra sản phẩm theo tên hoặc trong các sản phẩm bán chạy của shop "
        "— `chua_lay_duoc_gia` có nội dung thì nói ra. Đọc NỘI DUNG đánh giá Shopee hay bị "
        "chặn: khi đó nhận xét chất lượng dựa vào `phan_bo_sao_toan_bo`. "
        "Giá Shopee theo link là KHOẢNG theo phân loại (`gia_tu`–`gia_den`), KHÔNG phải giá "
        "sau voucher/flash sale — nói rõ, đừng báo một con số như thể là giá đang bán. "
        "`phan_bo_sao_toan_bo` là số sao của MỌI đánh giá, vẫn có khi không đọc được nội "
        "dung. `khong_co` liệt kê thứ nguồn không trả — người dùng hỏi thì nói thẳng. "
        "Kết quả soi theo link PHỦ MỌI KHÍA CẠNH CỦA SẢN PHẨM: `thong_tin` (giá, đã bán, sao, "
        "giao hàng, tên shop bán), `phan_loai` (giá + tồn kho từng phân loại), `mo_ta` (mô tả "
        "sản phẩm — chỉ TikTok Shop có), `binh_luan` (đã lọc trùng/rỗng; `loc` cho biết đọc được bao nhiêu, "
        "giữ lại bao nhiêu). Sheet có 4 tab: Tổng quan, Phân loại, Mô tả, Bình luận. Trả lời "
        "đủ các mặt đó chứ đừng chỉ nói số sao. "
        "`chi_doc_duoc` có nội dung thì nói rõ mẫu bình luận không phải toàn bộ. Hai nguồn "
        "này đôi khi tạm chặn: `loi` có nội dung thì nói NGUYÊN câu đó và KHÔNG tự chạy lại "
        "liên tục. TikTok Shop CHỈ soi được theo link, "
        "KHÔNG tìm theo từ khoá (nguồn trả toàn shop nhỏ, sai lệch). Giá TikTok Shop là giá "
        "động theo khuyến mãi: nói kèm 'tại thời điểm soi'.\n"
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
            "link": {"type": "array", "items": {"type": "string"},
                     "description": ("Link SẢN PHẨM Shopee hoặc TikTok Shop (kể cả link chia sẻ "
                                     "rút gọn), tối đa 5. Có link thì soi đúng sản phẩm đó.")},
            "gom_shop": {"type": "boolean",
                         "description": ("Chỉ khi có `link` VÀ người dùng hỏi về SHOP: thêm "
                                         "follower, tổng đã bán, điểm, số sản phẩm của shop. "
                                         "Mặc định false — chỉ đánh giá sản phẩm.")},
            "so_danh_gia": {"type": "integer",
                            "description": "Chỉ khi có `link`: số đánh giá đọc mỗi sản phẩm (mặc định 50)."},
            "tu_khoa": {"type": "array", "items": {"type": "string"},
                        "description": "Cụm từ tìm trên Shopee, tối đa 3 (khi không có link)."},
            "xep_theo": {"type": "string", "enum": list(_XEP),
                         "description": ("Mặc định 'lien_quan'. Chỉ đặt 'ban_chay' khi người "
                                         "dùng hỏi đúng 'bán chạy nhất' — cách xếp này lạc đề "
                                         "nhiều hơn.")},
            "so_san_pham": {"type": "integer",
                            "description": "Tổng số sản phẩm (mặc định 30; tự co theo trần chi phí)."},
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
        },
        # Rỗng vì hai đường vào: `link` (soi sản phẩm) hoặc `tu_khoa` (xem thị trường).
        # `_handle` tự báo lỗi rõ khi thiếu cả hai.
        "required": [],
    },
}


def _handle_link(args: dict) -> str:
    links = args.get("link") or []
    links = [links] if isinstance(links, str) else [str(x) for x in links if str(x).strip()]
    try:
        n = max(5, int(args.get("so_danh_gia") or san_link._DG_MAC_DINH))
    except (TypeError, ValueError):
        n = san_link._DG_MAC_DINH
    bat_dau = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=5)
    t0 = time.monotonic()
    kq = san_link.soi(links, n, gom_shop=bool(args.get("gom_shop")))
    if not kq["san_pham"]:
        return tool_error("Không nhận ra link sản phẩm nào. Dán link sản phẩm Shopee "
                          "(shopee.vn/…-i.<shop>.<item>) hoặc TikTok Shop (shop.tiktok.com/…/pdp/…).")
    thuc = A._chi_phi_thuc(kq["actors"], bat_dau, kq["est"]) if kq["actors"] else None
    chi_phi_tool.ghi(queries=links[:5], platforms=kq["nen"], date_range="hiện tại",
                     thuc=thuc, est=kq["est"])
    url, granted, loi = None, False, kq["loi"]
    # Tạo Sheet khi có ÍT NHẤT một sản phẩm đọc được — kể cả khi không có bình luận nào (bản
    # cũ chỉ tạo khi có bình luận, nên Shopee bị chặn đọc bình luận là mất luôn cả Sheet).
    if len(kq["tabs"][0][1]) > 1:
        title = (args.get("title") or "").strip() or \
            f"Soi sản phẩm · {datetime.datetime.now(A._VN_TZ):%d-%m-%Y %H:%M}"
        try:
            tok, url = san_link.ghi_nhieu_tab(title, kq["tabs"])
            sender = memory_store.get_current_sender()
            granted = A._grant(tok, sender) if sender else False
        except Exception as e:  # noqa: BLE001
            loi = {**(loi or {}), "sheet": f"{type(e).__name__}: {e}"[:250]}
    # Kiểm ghi của lớp trình bày chung (san_link gắn `ket_qua` vào danh sách tab sau khi ghi).
    kq_sheet = getattr(kq["tabs"], "ket_qua", None) if url else None
    if kq_sheet is not None and kq_sheet.day_du is False:
        loi = {**(loi or {}), "kiem_ghi": kq_sheet.cau_kiem}
    return tool_result(
        **(kq_sheet.cho_tool() if kq_sheet is not None
           else {"day_du": None, "kiem_ghi": None, "bang_tinh_tiep": None}),
        success=not loi, che_do="soi_theo_link", san_pham=kq["san_pham"],
        so_danh_gia_moi_sp=kq["so_danh_gia_moi_sp"], bi_co_theo_tran=kq["bi_co_theo_tran"],
        khong_nhan_ra=kq["khong_nhan_ra"], loi=loi, sheet_url=url, granted=granted,
        thoi_diem_soi=f"{datetime.datetime.now(A._VN_TZ):%H:%M %d/%m/%Y}",
        uoc_tinh_chi_phi_usd=round(kq["est"], 3),
        chi_phi_thuc_usd=thuc["usd"] if thuc and thuc.get("so_run") else None,
        chi_phi=A._dong_chi_phi(thuc, kq["est"]), giay=round(time.monotonic() - t0, 1),
    )


def _handle(args: dict, **_kwargs) -> str:
    if args.get("link"):
        return _handle_link(args)
    kw = args.get("tu_khoa") or []
    kw = [kw] if isinstance(kw, str) else [str(k).strip() for k in kw if str(k).strip()][:3]
    if not kw:
        return tool_error("Thiếu `tu_khoa` (cụm từ cần tìm trên Shopee) hoặc `link` sản phẩm.")
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

    sp, goc = [], []
    for it in raw:
        if not it.get("name"):
            continue
        # Bản ghi nguồn nguyên vẹn (cùng thứ tự tab dữ liệu) cho tab "Dữ liệu gốc": tool chỉ
        # chọn vài trường. Chỉ đi vào Sheet, không vào tool_result.
        goc.append({"Hạng": len(sp) + 1, **it})
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

    tong_hop = _tong_hop(dung)
    thuc = A._chi_phi_thuc([ACTOR], bat_dau, est)
    if thuc and thuc.get("cham_tran") and len(raw) >= n:
        thuc = {**thuc, "cham_tran": 0}
    chi_phi_tool.ghi(queries=kw, platforms=["shopee"], date_range="hiện tại", thuc=thuc, est=est)

    url, granted, loi, kq_sheet = None, False, None, None
    if sp:
        title = (args.get("title") or "").strip() or \
            f"Shopee · {', '.join(kw)[:40]} · {datetime.datetime.now(A._VN_TZ):%d-%m-%Y}"
        cap = {"granted": False}

        def _cap_quyen(tok: str) -> None:
            sender = memory_store.get_current_sender()
            cap["granted"] = A._grant(tok, sender) if sender else False

        try:
            bang = _bang_sheet(sp)
            kq_sheet = TB.xuat(title, [bang],
                               _tong_quan_sheet(title, bang, kw, xep, sp, dung, tong_hop,
                                                canh_bao, bi_co),
                               goc=TB.bang_goc(goc) if goc else None, cap_quyen=_cap_quyen)
            url, granted = kq_sheet.url, cap["granted"]
        except Exception as e:  # noqa: BLE001
            loi = f"Tạo/ghi sheet thất bại: {type(e).__name__}: {e}"[:250]
    canh_bao_ghi = (kq_sheet.cau_kiem if kq_sheet is not None and kq_sheet.day_du is False
                    else None)

    return tool_result(
        success=bool(sp) and not loi, tu_khoa=kw, xep_theo=xep, so_san_pham=len(sp),
        khong_co_so_da_ban=True, bi_co_theo_tran=bi_co, tong_hop=tong_hop,
        so_sp_khop_tu_khoa=sum(s["khop"] for s in sp), vi_du_lac_de=lac[:5] or None,
        canh_bao_lac_de=canh_bao, loi=loi,
        sheet_url=url, granted=granted,
        uoc_tinh_chi_phi_usd=round(est, 3),
        chi_phi_thuc_usd=thuc["usd"] if thuc and thuc.get("so_run") else None,
        cham_tran_chi_phi=bool(thuc and thuc.get("cham_tran")),
        chi_phi=A._dong_chi_phi(thuc, est), giay=round(time.monotonic() - t0, 1),
        note=(canh_bao_ghi if sp else "Shopee không trả sản phẩm nào cho các từ khoá này."),
        **(kq_sheet.cho_tool() if kq_sheet is not None
           else {"day_du": None, "kiem_ghi": None, "bang_tinh_tiep": None}),
    )


# ───────────────────────────── Sheet (trinh_bay_sheet) ─────────────────────────────
# Giá: số VND nguyên (zen-studio trả `price` theo đồng). Giảm %: `discountPercent` là số
# ĐÃ nhân 100 (32 = giảm 32%) → phan_tram_100. Điểm: 0–5, hai chữ số thập phân.
_COT_SHEET = [
    TB.Cot("Hạng", "so_nguyen"), TB.Cot("Sản phẩm", "chu_dai"), TB.Cot("Khớp từ khoá"),
    TB.Cot("Giá (VND)", "tien", tien_te="VND"), TB.Cot("Giá gốc", "tien", tien_te="VND"),
    TB.Cot("Giảm %", "phan_tram_100"), TB.Cot("Lượt đánh giá", "so_nguyen"),
    TB.Cot("Lượt thích", "so_nguyen"), TB.Cot("Điểm", "thap_phan"), TB.Cot("Shop"),
    TB.Cot("Shopee Mall"), TB.Cot("Thương hiệu"), TB.Cot("Nơi gửi"), TB.Cot("Link", "link"),
]
_HEADER = [c.ten for c in _COT_SHEET]


def _bang_sheet(sp: list) -> "TB.Bang":
    rows = [[
        s["hang"], s["ten"], "có" if s["khop"] else "lạc đề", s["gia"],
        s["gia_goc"] or "", s["giam_pct"] or "",
        s["luot_danh_gia"], s["luot_thich"], s["diem"] or "", s["shop"],
        "có" if s["chinh_hang"] else "", s["thuong_hieu"], s["noi_gui"], s["link"]]
        for s in sp]
    return TB.Bang("Sản phẩm", list(_COT_SHEET), rows,
                   mo_ta="Sản phẩm Shopee theo đúng thứ tự Shopee trả, có cột khớp từ khoá")


def _tong_quan_sheet(title, bang, kw, xep, sp, dung, th, canh_bao, bi_co) -> "TB.TongQuan":
    """Số liệu chính = ĐÚNG `tong_hop` tool đã tính (trên sản phẩm khớp từ khoá)."""
    tren = (f"trên {len(dung)} sản phẩm khớp từ khoá" if not canh_bao
            else f"trên TẤT CẢ {len(dung)} sản phẩm (ít hàng khớp — không đáng tin)")
    so_lieu = [TB.SoLieu("Sản phẩm lấy được", len(sp), "so_nguyen"),
               TB.SoLieu("Khớp từ khoá", sum(s["khop"] for s in sp), "so_nguyen",
                         ghi_chu="tên chứa đủ chữ của một từ khoá (bỏ dấu, bỏ số)")]
    g = th.get("gia") or {}
    for k, nhan in (("thap_nhat", "Giá thấp nhất"), ("pho_bien_tu", "Giá phổ biến từ (Q1)"),
                    ("trung_vi", "Giá trung vị"), ("pho_bien_den", "Giá phổ biến đến (Q3)"),
                    ("cao_nhat", "Giá cao nhất")):
        if k in g:
            so_lieu.append(TB.SoLieu(nhan, g[k], "tien", tien_te="VND", ghi_chu=tren))
    if th.get("dang_giam_gia"):
        so_lieu += [TB.SoLieu("Sản phẩm đang giảm giá", th["dang_giam_gia"]["so_sp"],
                              "so_nguyen", ghi_chu=tren),
                    TB.SoLieu("Mức giảm trung bình", th["dang_giam_gia"]["giam_tb_pct"],
                              "phan_tram_100", ghi_chu="trung bình trên sản phẩm đang giảm")]
    if th.get("diem_danh_gia_tb"):
        so_lieu.append(TB.SoLieu("Điểm đánh giá trung bình", th["diem_danh_gia_tb"],
                                 "thap_phan", ghi_chu=tren))
    nhom = []
    if th.get("phan_bo_gia"):
        nhom.append(TB.Nhom("Phân bố giá (" + ("mọi sản phẩm" if canh_bao else
                                               "sản phẩm khớp từ khoá") + ")",
                            list(th["phan_bo_gia"].items()),
                            sum(th["phan_bo_gia"].values())))
    nhom += [TB.dem_theo(bang, "Khớp từ khoá", "Theo khớp từ khoá (mọi sản phẩm)"),
             TB.dem_theo(bang, "Shop", "Theo shop (mọi sản phẩm)", toi_da=10)]
    top = None
    if th.get("nhieu_danh_gia_nhat"):
        top = TB.Bang(
            "Nhiều đánh giá nhất (" + ("mọi sản phẩm" if canh_bao else
                                       "sản phẩm khớp từ khoá") + ")",
            [TB.Cot("Sản phẩm", "chu_dai"), TB.Cot("Giá (VND)", "tien", tien_te="VND"),
             TB.Cot("Lượt đánh giá", "so_nguyen"), TB.Cot("Shop"), TB.Cot("Link", "link")],
            [[x["ten"], x["gia"], x["luot_danh_gia"], x["shop"], x["link"]]
             for x in th["nhieu_danh_gia_nhat"]])
    ghi_chu = [
        "Nguồn KHÔNG có số đã bán. Lượt đánh giá chỉ là chỉ báo gián tiếp cho lượng bán.",
        "Hạng = thứ tự Shopee trả về"
        + (" — là thứ hạng bán chạy của Shopee (xếp theo bán chạy)." if xep == "ban_chay"
           else f" khi xếp theo '{xep}' — KHÔNG phải thứ hạng bán chạy."),
        "Số liệu tổng hợp chỉ tính sản phẩm có tên khớp từ khoá; tab dữ liệu giữ đủ mọi "
        "sản phẩm, cột 'Khớp từ khoá' = 'lạc đề' là hàng Shopee trả lệch từ khoá.",
        "Shopee Mall = shop chính hãng (isOfficialShop). Ô Giá gốc / Giảm % / Điểm trống = "
        "nguồn không trả.",
        "Tên sản phẩm cắt ở 200 ký tự — bản đầy đủ ở tab Dữ liệu gốc.",
    ]
    if canh_bao:
        ghi_chu.append(canh_bao)
    if bi_co:
        ghi_chu.append(bi_co)
    return TB.TongQuan(
        tieu_de=title, nguon=f"Tool soi_san · Shopee ({ACTOR})",
        thoi_gian=f"giá tại thời điểm lấy, {datetime.datetime.now(A._VN_TZ):%H:%M %d/%m/%Y}",
        pham_vi=f"Shopee Việt Nam · từ khoá: {', '.join(kw)} · xếp theo: {xep}",
        so_lieu=so_lieu, nhom=nhom, top=top, ghi_chu=ghi_chu)


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
