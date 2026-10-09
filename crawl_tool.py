"""Register a `web_crawl` tool — cào TOÀN BỘ SẢN PHẨM của một web bán hàng vào
Lark Sheet, cấp quyền cho người hỏi, trả link.

Khác `web_scrape` (trong web_tool.py): `web_scrape` chỉ đọc CHỮ của một trang;
`web_crawl` bóc ra BẢNG SẢN PHẨM có cấu trúc (tên/giá/giá gốc/%giảm/link/ảnh).

KHÔNG hardcode site — xem thang chiến lược trong crawl_runner.py. Runner chạy ở
.venv-scrapling (venv riêng, không đụng venv Hermes mà meeting dùng chung).

Đo lại 06/09/2026 sau khi thêm tầng sitemap + sửa lỗi ảnh (xin 120 sp mỗi site).
Cột "trước" là bản 28/08, khi bốn tầng cũ chỉ đọc ĐÚNG MỘT trang:

    site         tầng                          sp   ảnh    (trước: sp / ảnh)
    hapas.vn     catalog_json                 112  1410     112 / 112
    yody.vn      html_data+sitemap_dm+bu_anh  120   404      90 /  90
    juno.vn      html_gia+sitemap_sp+bu_anh   120  1075      40 /  40
    vascara.com  html_gia+sitemap_sp+bu_anh   120   709      19 /  12
    dior.com     --                             0    --     Akamai chặn cả 4 tầng

Ba lỗi ÂM THẦM đã sửa cùng đợt (không cái nào từng crash hay báo lỗi):
  1. Ảnh GÁN NHẦM sản phẩm liền trước (lấy thẻ <img> đầu cửa sổ thay vì gần giá
     nhất) — "Kính mát Cassie" của vascara mang ảnh giày sandals.
  2. Link sản phẩm 404 hàng loạt trên yody: hydration khai slug không kèm tiền
     tố /product/, code ghép thẳng base+slug. Nay đối chiếu sitemap để chữa.
  3. `_so("1,290,000")` trả 1 đồng do cắt chuỗi ở dấu phẩy đầu tiên.
Kiểm chứng 06/09: 18/18 sản phẩm mẫu có MỌI URL ảnh nằm đúng trong trang sản
phẩm của chính nó; 24/24 link mẫu trả HTTP 200.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
from pathlib import Path

import lark_client as lark  # noqa: F401 — giữ tên cũ (bộ thử/patch cũ gọi crawl_tool.lark)
import memory_store
import trinh_bay_sheet as T
from apify_tool import _bang_an_toan, _create_sheet, _first_sheet_id, _grant  # noqa: F401
from cli_support import env_tien_trinh_con
from config import config
from web_tool import _DA_BIET_CHAN, _PY

from tools.registry import registry, tool_error, tool_result  # type: ignore

_TOOLSET = "browser"
_HERE = Path(__file__).resolve().parent
_RUNNER = _HERE / "crawl_runner.py"
# Ngân sách của RUNNER phải nằm gọn trong timeout 1 lượt trả lời của run.py
# (AGENT_REPLY_TIMEOUT, mặc định 180s). Bản cũ để _TIMEOUT=280 > 180: lượt cào
# lâu bị run.py cắt trước, người dùng chỉ thấy bot im lặng chứ không thấy kết
# quả một phần. Nay runner tự dừng ở `_NGAN_SACH` rồi trả những gì đã có.
_NGAN_SACH = 110
_TIMEOUT = _NGAN_SACH + 40
_COT = ["Tên sản phẩm", "Giá bán", "Giá gốc", "Giảm %", "SKU", "Link",
        "Ảnh", "Số ảnh", "Tất cả ảnh", "Nguồn"]
# Tầng ĐOÁN THEO MẪU GIÁ (khác tầng dữ liệu có cấu trúc). `sitemap_dm` cũng
# dùng chính bộ bóc đó, chỉ khác là chạy trên nhiều trang danh mục.
_TANG_DOAN = ("html_gia", "browser", "sitemap_dm")
# Khoá của một sản phẩm runner trả (`crawl_runner._sp`) — đều đã lên sheet. Khoá khác (hoặc
# `__goc` của adapter Apify) thì thêm tab "Dữ liệu gốc" để không mất trường nào.
_KHOA_SP = {"ten", "gia", "gia_goc", "link", "anh", "anh_tat_ca", "so_anh", "sku"}


def _tien_te(dom: str, url: str, sp: list) -> str | None:
    """Đơn vị giá: `currency` của bản ghi adapter nếu có và thống nhất; web .vn (hoặc đường
    dẫn /vn/) là VND (bộ bóc theo mẫu giá chỉ nhận ₫/đ/VND); còn lại None = không chắc."""
    cur = {str((p.get("__goc") or {}).get("currency") or "").strip().upper() for p in sp
           if isinstance(p.get("__goc"), dict)} - {""}
    if cur:
        return cur.pop() if len(cur) == 1 else None
    if dom.lower().endswith(".vn") or re.search(r"/vn(?:/|$)", url.lower()):
        return "VND"
    return None


def _cot(tien_te: str | None) -> list:
    """Cột sheet sản phẩm. Giá VND → tiền ₫; đơn vị khác/không chắc → số nguyên (bộ bóc giá
    `_so` trả số nguyên, bỏ phần lẻ) — không gán ký hiệu tiền khi không chắc."""
    gia = ("tien", "VND") if tien_te == "VND" else ("so_nguyen", None)
    return [T.Cot("Tên sản phẩm"), T.Cot("Giá bán", gia[0], gia[1]),
            T.Cot("Giá gốc", gia[0], gia[1]), T.Cot("Giảm %", "phan_tram_100"),
            T.Cot("SKU", "ma"), T.Cot("Link", "link"), T.Cot("Ảnh", "link"),
            T.Cot("Số ảnh", "so_nguyen"), T.Cot("Tất cả ảnh", "chu_dai"), T.Cot("Nguồn")]


SCHEMA = {
    "name": "web_crawl",
    "description": (
        "CÀO TOÀN BỘ SẢN PHẨM của một website bán hàng (tên, giá bán, giá gốc, % giảm, "
        "link, ảnh), ghi vào Lark Sheet, cấp quyền cho người hỏi và trả LINK SHEET. "
        "Dùng khi ai nhờ 'cào toàn bộ sản phẩm của web X', 'lấy bảng giá đối thủ', "
        "'so sánh giá với brand Y', 'xem bộ sưu tập mới của họ'.\n"
        "KHÁC `web_scrape`: `web_scrape` chỉ ĐỌC CHỮ một trang; `web_crawl` bóc ra BẢNG "
        "SẢN PHẨM có cấu trúc rồi ghi sheet.\n"
        "TỰ NHẬN DIỆN nền tảng — KHÔNG cần khai báo trước site nào, đưa domain bất kỳ "
        "là chạy (thử catalog JSON Haravan/Shopify -> JSON-LD/Next.js/Nuxt/inline-script "
        "-> bóc theo mẫu giá trên HTML thô -> mở rộng qua sitemap sang trang sản phẩm và "
        "trang danh mục -> render JS rồi bóc theo mẫu giá).\n"
        "BẮT BUỘC KHI TRẢ LỜI:\n"
        "- Đọc `tang` (có thể ghép nhiều tầng, vd 'html_gia+sitemap_sp+bu_anh'). "
        "`catalog_json`, `html_data`, `sitemap_sp` là dữ liệu CÓ CẤU TRÚC, tin được. "
        "Còn `html_gia`, `sitemap_dm`, `browser` là tầng ĐOÁN THEO MẪU GIÁ — số liệu có "
        "thể lệch (hay gặp nhất: giá gốc/giá bán bắt nhầm sang sản phẩm kề bên), phải "
        "nhắc người dùng đối chiếu vài sản phẩm với web.\n"
        "- `het_ngan_sach`=true nghĩa là hết giờ giữa chừng: kết quả MỚI LÀ MỘT PHẦN, "
        "phải nói rõ và gợi ý chạy lại cho phần còn lại.\n"
        "- `bi_chan_toc_do`>0 nghĩa là site chặn bớt request: sản phẩm thiếu ảnh có thể "
        "do BỊ CHẶN chứ không phải sản phẩm đó không có ảnh — đừng kết luận nhầm.\n"
        "- `so_co_anh`/`tong_so_anh`: sheet có cột 'Ảnh' (ảnh chính), 'Số ảnh' và "
        "'Tất cả ảnh' (cả album, mỗi ảnh một dòng trong ô).\n"
        "- `success`=false nghĩa là CHƯA bóc được, KHÔNG phải site không có sản phẩm. "
        "Đọc `nhat_ky` để nói rõ đã thử những cách nào. TUYỆT ĐỐI không bịa sản phẩm.\n"
        "- `cham_tran`=true nghĩa là mới lấy tới giới hạn, chưa phải toàn bộ catalog — "
        "nói rõ đây là MẪU và gợi ý tăng `max_products`.\n"
        "- Gửi NGUYÊN `sheet_url`. `granted`=false thì báo họ có thể mở không được.\n"
        "- `qua_adapter` có giá trị nghĩa là 6 tầng miễn phí đều ra 0, phải dùng ADAPTER "
        "CÓ TÍNH TIỀN (actor Apify chuyên cho site đó). Khi đó PHẢI nói cho người dùng "
        "biết đã tốn `chi_phi_apify_usd`, và nếu có `adapter_ghi_chu` thì đọc rồi truyền "
        "đạt lại — nó giải thích các đặc thù dữ liệu của site đó.\n"
        "- Site hạng sang dùng Akamai (dior.com…) KHÔNG cào được — báo thẳng, đừng thử."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string",
                    "description": "Domain hoặc URL trang danh mục, vd 'vascara.com' hoặc 'https://juno.vn/tui-xach'."},
            "max_products": {"type": "integer", "description": "Số sản phẩm tối đa (mặc định 100, trần 1000)."},
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
        },
        "required": ["url"],
    },
}


def _handle(args: dict, **kwargs) -> str:
    url = str(args.get("url") or "").strip()
    if not url:
        return tool_error("Thiếu `url`.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    low = url.lower()
    for dom, ly_do in _DA_BIET_CHAN.items():
        if dom in low:
            return tool_error(
                f"{dom} KHÔNG cào được: {ly_do}. Nói thẳng với người dùng, "
                f"TUYỆT ĐỐI đừng bịa danh sách sản phẩm.")
    if any(k in low for k in ("tiktok.com", "instagram.com", "facebook.com", "threads.net")):
        return tool_error("Đây là mạng xã hội, không phải web bán hàng. Dùng `social_listen`.")
    if not _PY.exists():
        return tool_error("Chưa cài Scrapling — xem hướng dẫn trong mô tả `web_scrape`.")

    try:
        n = int(args.get("max_products") or 100)
    except (TypeError, ValueError):
        n = 100
    n = max(1, min(n, 1000))

    env = env_tien_trinh_con()  # không mang token Meta vào Scrapling
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [str(_PY), str(_RUNNER)],
            input=json.dumps({"url": url, "max_products": n,
                              "budget_s": _NGAN_SACH}, ensure_ascii=False),
            env=env, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=_TIMEOUT, cwd=str(config.here))
    except subprocess.TimeoutExpired:
        return tool_error(
            f"Quá {_TIMEOUT}s. Giảm `max_products`, hoặc đưa thẳng URL trang danh mục "
            f"thay vì trang chủ.")
    except OSError as e:
        return tool_error(f"Không chạy được runner: {type(e).__name__}: {e}")

    out = (proc.stdout or "").strip()
    if not out:
        return tool_error(f"Runner không trả gì. stderr: {(proc.stderr or '')[:400]}")
    try:
        d = json.loads(out.splitlines()[-1])
    except json.JSONDecodeError:
        return tool_error(f"Runner trả dữ liệu không phải JSON: {out[:300]}")

    sp = d.get("san_pham") or []
    nhat_ky = list(d.get("nhat_ky") or [])
    adapter = None

    # TẦNG ADAPTER — chỉ chạy khi thang 6 tầng MIỄN PHÍ ra 0 (hoặc ra rác bị cờ
    # `nghi_ngo` chặn). Nó tốn tiền Apify nên tuyệt đối không được chạy trước.
    # Xem `crawl_adapters.py` để biết vì sao đây là bảng NGOẠI LỆ tường minh.
    if not sp or d.get("nghi_ngo"):
        try:
            import crawl_adapters
            kq = crawl_adapters.chay(url, n, nhat_ky)
            if kq.get("san_pham"):
                sp = kq["san_pham"]
                adapter = kq
                d["tang"] = "apify_adapter"
                d["nghi_ngo"] = False
        except Exception as e:  # noqa: BLE001
            # FAIL-OPEN: adapter hỏng thì giữ nguyên kết luận thất bại trung thực
            # của thang miễn phí. KHÔNG được biến lỗi adapter thành "site không
            # có sản phẩm" — đó là kết luận sai về thị trường.
            nhat_ky.append(f"adapter: khong nap duoc ({type(e).__name__}: {str(e)[:90]})")
    d["nhat_ky"] = nhat_ky

    # `nghi_ngo` = có ra kết quả nhưng quá ít và toàn từ tầng đoán -> KHÔNG ghi
    # sheet. Ghi ra sheet là hợp thức hoá dữ liệu rác: người dùng thấy có link
    # sheet sẽ tin là cào được thật.
    if not sp or d.get("nghi_ngo"):
        return tool_result(
            success=False, url=url, tang=d.get("tang") or "",
            so_san_pham=len(sp), nghi_ngo=bool(d.get("nghi_ngo")),
            nhat_ky=d.get("nhat_ky") or [], sheet_url=None,
            tim_thay=[{"ten": p.get("ten"), "gia": p.get("gia")} for p in sp[:3]],
            error=d.get("error") or "Chưa bóc được sản phẩm nào.",
            note="CHƯA bóc được KHÔNG có nghĩa là site không có sản phẩm. Nói rõ đã thử "
                 "những cách nào (xem `nhat_ky`) và đề nghị người dùng đưa thẳng URL "
                 "trang danh mục. TUYỆT ĐỐI không bịa danh sách."
                 + (" Vài kết quả trong `tim_thay` nhiều khả năng là RÁC (tiêu đề bài "
                    "viết/banner) — đừng trình bày chúng như sản phẩm."
                    if d.get("nghi_ngo") else ""))

    dom = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    rows = []
    for p in sp:
        gia, goc = p.get("gia"), p.get("gia_goc")
        # Giảm % do tool tính (số ĐÃ nhân 100, làm tròn) → định dạng "23.00%".
        giam = round((goc - gia) / goc * 100) if (gia and goc and goc > gia) else ""
        ds = p.get("anh_tat_ca") or ([p["anh"]] if p.get("anh") else [])
        rows.append([p.get("ten", ""), gia or "", goc or "", giam,
                     p.get("sku", ""), p.get("link", ""), p.get("anh", ""),
                     len(ds), "\n".join(ds), dom])
    rows = _bang_an_toan(rows)            # tên/mô tả sản phẩm từ web: chặn chèn công thức

    title = (args.get("title") or "").strip() or \
        f"Sản phẩm · {dom} · {datetime.datetime.now():%d-%m %H%M}"
    cham_tran = len(sp) >= n
    tang = d.get("tang") or ""
    doan = [t for t in _TANG_DOAN if t in tang]
    het_ns, chan = bool(d.get("het_ngan_sach")), int(d.get("bi_chan_toc_do") or 0)
    # Sản phẩm từ adapter không đi qua bộ đếm ảnh của runner -> đếm lại tại đây,
    # không thì báo cáo sẽ nói "0 ảnh" trong khi sheet có ảnh đầy đủ.
    if adapter:
        d["so_co_anh"] = sum(1 for p in sp if p.get("anh"))
        d["tong_so_anh"] = sum(p.get("so_anh", 0) for p in sp)
    thieu_anh = len(sp) - int(d.get("so_co_anh") or 0)

    tien_te = _tien_te(dom, url, sp)
    bang = T.Bang("Sản phẩm", _cot(tien_te), rows,
                  mo_ta=f"Mỗi sản phẩm một dòng (cào từ {dom}, tầng {tang})")
    goc_ds = [p.get("__goc") if isinstance(p.get("__goc"), dict)
              else {k: v for k, v in p.items() if k != "__goc"} for p in sp]
    can_goc = any(isinstance(p.get("__goc"), dict) or set(p) - _KHOA_SP - {"__goc"}
                  for p in sp)
    tq = T.TongQuan(
        tieu_de=title, nguon="web_crawl — tầng " + (tang or "?")
        + (f" · adapter {adapter.get('adapter')} (Apify)" if adapter else ""),
        pham_vi=f"{url} · tối đa {n} sản phẩm",
        top=T.top_theo(bang, "Giảm %", 5, ["Tên sản phẩm", "Giá bán", "Giá gốc", "Giảm %",
                                            "Link"], "Top 5 giảm giá sâu nhất"),
        ghi_chu=[g for g in [
            "Giá: " + ("đồng (VND)." if tien_te == "VND" else
                       f"đơn vị {tien_te} theo nguồn." if tien_te else
                       "đơn vị tiền theo web (không xác định chắc nên để số trơn).")
            + " Bộ bóc giá trả số nguyên (bỏ phần lẻ); ô trống = web không ghi giá đó.",
            "Giảm % = (giá gốc − giá bán) / giá gốc, làm tròn số nguyên, do tool tính.",
            (f"LƯU Ý: một phần lấy bằng tầng {'/'.join(doan)} (đoán theo mẫu giá) nên số liệu "
             "có thể lệch — đối chiếu vài sản phẩm với web.") if doan else "",
            (f"CHẠM TRẦN {n} sản phẩm: đây mới là MẪU, chưa phải toàn bộ catalog (chưa biết "
             f"còn bao nhiêu sản phẩm) — muốn đủ thì cào lại với max_products cao hơn "
             f"(tối đa 1000).") if cham_tran else "",
            (f"HẾT NGÂN SÁCH {d.get('ngan_sach_s')}s trước khi quét xong: kết quả MỘT PHẦN, "
             "chưa phải toàn bộ catalog.") if het_ns else "",
            (f"Site chặn tốc độ {chan} lần — sản phẩm thiếu ảnh có thể do BỊ CHẶN, không phải "
             "không có ảnh.") if chan else "",
            f"{thieu_anh} sản phẩm không lấy được ảnh." if thieu_anh else "",
            "'Tất cả ảnh': tối đa 20 ảnh mỗi sản phẩm (giới hạn bộ cào), mỗi ảnh một dòng "
            "trong ô; tên sản phẩm cắt ở 250 ký tự.",
            (f"Adapter CÓ TÍNH TIỀN: {adapter.get('adapter')}, ước tính "
             f"{adapter.get('uoc_tinh_chi_phi_usd')} USD.") if adapter else "",
            (adapter or {}).get("ghi_chu") or "",
        ] if g])
    sender = memory_store.get_current_sender()
    cap: dict = {}

    def _cap_quyen(tok: str) -> None:
        T.gop_quyen(cap, _grant(tok, sender) if sender else False)

    try:
        kq = T.xuat(title, [bang], tq, goc=T.bang_goc(goc_ds) if can_goc else None,
                    cap_quyen=_cap_quyen)
    except Exception as e:  # noqa: BLE001
        return tool_result(
            success=False, url=url, tang=d.get("tang"), so_san_pham=len(sp),
            sheet_url=None, nhat_ky=d.get("nhat_ky") or [],
            error=f"Cào được {len(sp)} sản phẩm nhưng GHI SHEET THẤT BẠI: "
                  f"{type(e).__name__}: {e}",
            mau=[{"ten": p["ten"], "gia": p["gia"]} for p in sp[:5]])
    sheet_url = kq.url
    granted = bool(cap.get("granted"))

    return tool_result(
        success=True, url=url, tang=tang, so_san_pham=len(sp),
        so_co_anh=d.get("so_co_anh"), tong_so_anh=d.get("tong_so_anh"),
        het_ngan_sach=het_ns, bi_chan_toc_do=chan,
        cham_tran=cham_tran, title=title, sheet_url=sheet_url, granted=granted,
        nhat_ky=d.get("nhat_ky") or [], **kq.cho_tool(),
        # Adapter là tầng CÓ TÍNH TIỀN -> phải báo ra, không được im lặng.
        qua_adapter=(adapter or {}).get("adapter"),
        actor_da_dung=(adapter or {}).get("actor_da_dung"),
        chi_phi_apify_usd=(adapter or {}).get("uoc_tinh_chi_phi_usd"),
        adapter_ghi_chu=(adapter or {}).get("ghi_chu"),
        mau=[{"ten": p["ten"], "gia": p["gia"], "gia_goc": p["gia_goc"],
              "so_anh": p.get("so_anh", 0)} for p in sp[:8]],
        note=(f"Đã ghi {'ĐỦ ' if kq.day_du else ''}{len(sp)} sản phẩm vào sheet '{title}' "
              f"({d.get('tong_so_anh')} ảnh): tab '{T.TAB_TONG_QUAN}' rồi tab "
              f"'{kq.tabs[0].ten if kq.tabs else T.TAB_DU_LIEU}'. Kiểm ghi: {kq.cau_kiem} "
              + ("" if kq.day_du is not False else
                 "CẢNH BÁO GHI THIẾU: sheet CHƯA đủ dòng như `kiem_ghi` nói — báo rõ, đừng nói "
                 "là đủ. ")
              + "GỬI `sheet_url` kèm NGUYÊN câu `kiem_ghi`."
              + (f" CHẠM TRẦN {n} — đây mới là MẪU, chưa phải toàn bộ catalog; muốn đủ "
                 f"thì tăng `max_products`." if cham_tran else "")
              # html_gia và sitemap_dm dùng CHÍNH bộ đoán-theo-mẫu của tầng browser,
              # chỉ khác là chạy trên HTML thô -> phải cảnh báo y hệt.
              + (f" LƯU Ý: một phần lấy bằng tầng {'/'.join(doan)} (đoán theo mẫu giá) "
                 "nên số liệu có thể lệch — nhắc người dùng đối chiếu vài sản phẩm với web."
                 if doan else "")
              + (f" HẾT NGÂN SÁCH {d.get('ngan_sach_s')}s trước khi quét xong: đây là kết "
                 "quả MỘT PHẦN, chưa phải toàn bộ catalog." if het_ns else "")
              + (f" Site chặn tốc độ {chan} lần — một số sản phẩm có thể thiếu ảnh vì bị "
                 "chặn chứ KHÔNG phải sản phẩm đó không có ảnh." if chan else "")
              + (f" {thieu_anh} sản phẩm không lấy được ảnh." if thieu_anh else "")
              + ("" if granted else " CẢNH BÁO: chưa cấp được quyền tự động.")),
    )


def _available() -> bool:
    return _PY.exists() and _RUNNER.exists()


def register() -> None:
    try:
        registry.register(
            name="web_crawl", toolset=_TOOLSET, schema=SCHEMA, handler=_handle,
            check_fn=_available, requires_env=[], is_async=False,
            description="Cào toàn bộ sản phẩm của web bán hàng vào Lark Sheet (tự nhận diện nền tảng)",
            emoji="\U0001f6cd", override=True,
        )
    except Exception as e:
        print(f"[crawl_tool] register warning: {e}")


register()
