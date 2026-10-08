"""Register a `fb_ads_library` tool on the Hermes brain — read a competitor's
ads straight from the **Meta Ad Library** using the local headless browser
(agent-browser), NO API key and NO login required.

Why the browser (not an API / not Apify)
-----------------------------------------
The Meta Ad Library (facebook.com/ads/library) is a PUBLIC transparency page:
it renders without logging in, so the browser can read it like any website —
unlike the normal FB/IG/Threads feed which is behind a login wall. One library
covers ALL Meta placements: a single ad can run on Facebook, Instagram,
Messenger, Threads and Audience Network, and each ad shows a "Platforms" field.
So there is no separate Instagram/Threads ad library — filter by platform here.

What it returns
---------------
Builds the Ad Library URL from a page_id (all ads of a page) or a keyword/
advertiser `query`, navigates, lets the SPA render, scrolls to load more, then
parses the accessibility snapshot into: total_results, a list of ads
(library_id, start date, ad copy), plus creative image URLs (via
browser_get_images). Images are resized (<=600px) and their URLs carry signed,
expiring tokens — download immediately if needed.

Requires only that agent-browser is installed (it is — the Hermes browser tool
ships it). No token, so the tool is always live.
"""

from __future__ import annotations

import datetime
import json
import re
import threading
import time
from urllib.parse import quote

from tools.registry import registry, tool_error, tool_result  # type: ignore

# agent-browser primitives (sync, return JSON strings). Importing browser_tool
# also registers the raw browser_* tools — harmless, and useful for general web.
try:
    from tools.browser_tool import (  # type: ignore
        browser_navigate,
        browser_snapshot,
        browser_get_images,
        browser_scroll,
    )
    _BROWSER_OK = True
    _IMPORT_ERR = ""
except Exception as e:  # noqa: BLE001
    _BROWSER_OK = False
    _IMPORT_ERR = f"{type(e).__name__}: {e}"


def _full_snapshot() -> str:
    """Return the COMPLETE accessibility snapshot (untruncated).

    ``browser_snapshot`` hard-caps output at ~8000 chars (fine for an LLM, but
    that only holds ~3 verbose Ad Library cards). We parse structured fields
    ourselves and never feed the raw tree to the model, so we go straight to the
    underlying agent-browser ``snapshot`` command to get every loaded card.
    """
    try:
        from tools.browser_tool import _run_browser_command, _last_session_key  # type: ignore
        key = _last_session_key(_TASK_ID)
        res = _run_browser_command(key, "snapshot", [])
        if res.get("success"):
            return (res.get("data", {}) or {}).get("snapshot", "") or ""
    except Exception:  # noqa: BLE001
        pass
    try:  # fallback: the truncated public wrapper
        s = json.loads(browser_snapshot(full=True, task_id=_TASK_ID))
        return s.get("snapshot", "") or ""
    except Exception:  # noqa: BLE001
        return ""

_TOOLSET = "fb_ads"
_TASK_ID = "fb_ads_library"  # shared browser session across navigate/snapshot/images
_MAX_ADS = 40
_MAX_IMAGES = 25

# EN + VI label variants (Ad Library UI language follows the viewer's locale).
_RE_TOTAL = re.compile(r"~?\s*([\d.,]+)\s*(?:results|kết quả)", re.I)
_RE_LIBID = re.compile(r"(?:Library ID|ID thư viện)\s*[:：]\s*(\d+)", re.I)
_RE_START = re.compile(r"(?:Started running on|Ngày bắt đầu chạy)\s*[\"']?\s*([^\"'\n]+)", re.I)
_RE_BUTTON = re.compile(r'button "((?:[^"\\]|\\.)*)"')
_NO_ADS = ("no ads match", "không có quảng cáo", "0 results", "0 kết quả")
_LOGIN_WALL = ("log in to facebook", "đăng nhập vào facebook")
# UI button labels to ignore when hunting for the ad copy (the real caption is
# the single longest button text inside an ad block).
_UI_LABELS = {
    "see ad details", "xem chi tiết quảng cáo", "see summary details",
    "xem chi tiết bản tóm tắt", "open drop-down", "filters", "bộ lọc",
    "remove", "clear filters", "xoá bộ lọc", "shop now", "mua ngay",
    "send message", "gửi tin nhắn", "learn more", "tìm hiểu thêm",
    "open navigation panel", "close",
}


# Meta filters ads by placement SERVER-SIDE via this URL param (verified: counts
# change per value). We filter here rather than per-ad because the card's
# "Platforms" field renders as icons with NO accessible label — unreadable from
# the a11y snapshot — so the query-level filter is the only reliable path.
_PLATFORMS = ("facebook", "instagram", "messenger", "threads", "audience_network")


def _ads_library_url(page_id: str, query: str, country: str, active_status: str,
                     platform: str = "") -> str:
    params = [
        f"active_status={active_status}",
        "ad_type=all",
        f"country={country}",
        "is_targeted_country=false",
        "media_type=all",
    ]
    if platform:
        params.append(f"publisher_platforms[0]={platform}")
    if page_id:
        params += ["search_type=page", f"view_all_page_id={page_id}"]
    else:
        params += ["search_type=keyword_unordered", f"q={quote(query)}"]
    return "https://www.facebook.com/ads/library/?" + "&".join(params)


def _unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\n", "\n").replace("\\t", " ").strip()


def _total_results(snap: str):
    m = _RE_TOTAL.search(snap)
    if not m:
        return None
    try:
        return int(m.group(1).replace(".", "").replace(",", ""))
    except ValueError:
        return None


def _extract_caption(segment: str) -> str:
    best = ""
    for m in _RE_BUTTON.finditer(segment):
        txt = _unescape(m.group(1))
        if txt.strip().lower() in _UI_LABELS:
            continue
        if len(txt) > len(best):
            best = txt
    return best[:700]


def _parse_ads(snap: str, limit: int) -> list[dict]:
    matches = list(_RE_LIBID.finditer(snap))
    ads: list[dict] = []
    for i, m in enumerate(matches[:limit]):
        seg_start = m.start()
        seg_end = matches[i + 1].start() if i + 1 < len(matches) else len(snap)
        segment = snap[seg_start:seg_end]
        started = _RE_START.search(segment)
        ads.append({
            "library_id": m.group(1),
            "started": _unescape(started.group(1)) if started else None,
            "text": _extract_caption(segment) or None,
        })
    return ads


def _filter_images(images) -> list[str]:
    out, seen = [], set()
    if not isinstance(images, list):
        return out
    for im in images:
        src = im.get("src") if isinstance(im, dict) else (im if isinstance(im, str) else None)
        if not src or "fbcdn" not in src:
            continue
        if "s60x60" in src or "s148x148" in src:  # tiny avatars/thumbs — skip
            continue
        key = src.split("?", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        out.append(src)
        if len(out) >= _MAX_IMAGES:
            break
    return out


#: Cột Lark Sheet theo dõi (chủ agent chốt 05/10/2026: tra ads cũng phải ra Sheet như
#: Top Ads TikTok, để team lưu và so theo thời gian thay vì chỉ đọc trong chat).
#: (tên, kiểu cột của trinh_bay_sheet). "Ngày bắt đầu chạy" giữ nguyên chữ Ad Library hiện
#: (vd "1 Oct 2026" / "1 thg 10, 2026" theo ngôn ngữ giao diện) — không đoán ngày.
_COT_SHEET = [("STT", "so_nguyen"), ("Library ID", "ma"), ("Ngày bắt đầu chạy", "chu"),
              ("Nội dung quảng cáo", "chu_dai"), ("Link trên Ad Library", "link"),
              ("Trang / từ khoá", "chu"), ("Nền tảng lọc", "chu"), ("Quốc gia", "chu"),
              ("Trạng thái lọc", "chu"), ("Ngày quét", "ngay")]
_HEADER_SHEET = [t for t, _ in _COT_SHEET]
_TRANG_THAI = {"active": "đang chạy", "inactive": "đã dừng", "all": "tất cả"}
_VN_TZ = datetime.timezone(datetime.timedelta(hours=7))


def _duoc_ghi_sheet() -> bool:
    """Tra ads là việc ĐỌC (agent không có `write_data` vẫn tra được); Sheet là ghi dữ
    liệu ra ngoài nên chỉ ghi khi hợp đồng agent có `write_data`."""
    try:
        import lsr_policy
        return "write_data" in lsr_policy.quyen_phat()
    except Exception:  # noqa: BLE001
        return False


def _dong_sheet(ads: list[dict], nhan: str, platform: str, country: str,
                active_status: str, ngay, stt_dau: int = 1) -> list[list]:
    return [[stt_dau + i, a["library_id"], a.get("started") or "", a.get("text") or "",
             f"https://www.facebook.com/ads/library/?id={a['library_id']}", nhan,
             platform or "tất cả", country, _TRANG_THAI.get(active_status, active_status), ngay]
            for i, a in enumerate(ads)]


def _cot_sheet():
    import trinh_bay_sheet as TB
    return [TB.Cot(t, k) for t, k in _COT_SHEET]


def _ghi_chu_brand(nhan: str, platform: str, country: str, active_status: str,
                   so_ad: int, total, limit) -> str:
    """Một dòng ghi chú cho mỗi trang/từ khoá: Ad Library báo bao nhiêu, sheet có bao nhiêu,
    thiếu bao nhiêu và lấy thêm bằng cách nào (không bao giờ cắt âm thầm)."""
    bo_loc = (f"{country}, {platform or 'mọi nền tảng'}, "
              f"{_TRANG_THAI.get(active_status, active_status)}")
    if total is None:
        cau = (f"{nhan} ({bo_loc}): sheet có {so_ad} ad; Ad Library không hiện tổng số kết "
               "quả nên không biết còn bao nhiêu ad chưa đưa vào.")
    else:
        cau = f"{nhan} ({bo_loc}): Ad Library báo khoảng {total} kết quả; sheet có {so_ad} ad"
        cau += (f" — còn khoảng {total - so_ad} ad chưa đưa vào sheet" if total > so_ad else "")
        cau += "."
    if limit and (total is None or total > so_ad):
        cau += (f" Lượt này bóc tối đa {limit} ad (trần {_MAX_ADS}); muốn thêm thì tra lại với "
                f"limit lớn hơn (tối đa {_MAX_ADS}) hoặc lọc hẹp hơn (platform, active_status).")
    return cau


_GHI_CHU_CHUNG = [
    "Mỗi dòng một ad bóc từ trang Meta Ad Library công khai (trình duyệt, không API). "
    "Nhiều trang/từ khoá tra trong cùng một lượt được ghi nối vào cùng sheet này.",
    "Nền tảng lọc / Quốc gia / Trạng thái lọc là BỘ LỌC gửi cho Meta (lọc phía Meta), không "
    "phải nền tảng của từng ad — thẻ ad không đọc được trường nền tảng.",
    "Ngày bắt đầu chạy giữ nguyên chữ Ad Library hiển thị. Nội dung quảng cáo là chữ dài "
    "nhất trong thẻ ad, cắt ở 700 ký tự; ô trống = thẻ ad không có chữ đọc được.",
    "Ảnh creative không đưa vào sheet (link ảnh có chữ ký, hết hạn) — xem bằng Link trên "
    "Ad Library.",
]


def _tong_quan_sheet(title: str, rows: list[list], brand_notes: list[str], ngay):
    import trinh_bay_sheet as TB
    bang = TB.Bang("Quảng cáo", _cot_sheet(), rows,
                   mo_ta="Mỗi ad một dòng (Meta Ad Library), kèm link Ad Library")
    nhan = list(dict.fromkeys(str(r[5]) for r in rows))
    tq = TB.TongQuan(
        tieu_de=title, nguon="Meta Ad Library (fb_ads_library — trang công khai, trình duyệt)",
        thoi_gian=f"quét ngày {ngay:%d/%m/%Y}",
        pham_vi="Trang / từ khoá: " + ", ".join(nhan[:10]) + ("…" if len(nhan) > 10 else ""),
        so_lieu=[TB.SoLieu("Số ad trong sheet (mẫu đã bóc)", len(rows), "so_nguyen"),
                 TB.SoLieu("Số trang / từ khoá đã tra", len(nhan), "so_nguyen")],
        nhom=[TB.dem_theo(bang, "Trang / từ khoá"), TB.dem_theo(bang, "Nền tảng lọc"),
              TB.dem_theo(bang, "Quốc gia"), TB.dem_theo(bang, "Trạng thái lọc")],
        ghi_chu=list(brand_notes) + _GHI_CHU_CHUNG)
    return bang, tq


#: Sheet của LƯỢT trả lời đang chạy: (chat, mã lượt) -> {tok, sid, url, granted, dong}.
#: 02/10/2026 một lượt gọi tool này 8 lần (8 brand) — mỗi lần một file là 8 link rác.
#: Cùng lượt thì ghi NỐI vào sheet đầu; lượt sau (mã khác) là sheet mới.
_SHEET_LUOT: dict[tuple, dict] = {}
_SHEET_GUARD = threading.Lock()
_KHOA_SHEET_LUOT: dict[tuple, threading.Lock] = {}


def _khoa_cho(khoa: tuple | None) -> threading.Lock:
    """Khoá RIÊNG từng lượt: hai lời gọi song song cùng lượt không cùng tạo sheet hay
    ghi đè cùng dòng; lượt/người khác không phải chờ nhau. Ngoài lượt: khoá mới (không
    chia sẻ gì để mà tranh)."""
    if khoa is None:
        return threading.Lock()
    with _SHEET_GUARD:
        k = _KHOA_SHEET_LUOT.get(khoa)
        if k is None:
            if len(_KHOA_SHEET_LUOT) >= 200:
                for cu in [x for x, kk in _KHOA_SHEET_LUOT.items() if not kk.locked()][:50]:
                    _KHOA_SHEET_LUOT.pop(cu, None)
            k = _KHOA_SHEET_LUOT[khoa] = threading.Lock()
        return k


def _khoa_luot() -> tuple | None:
    """Khoá của lượt hiện tại; None ngoài lượt trả lời (khi đó luôn tạo sheet mới)."""
    try:
        import dong_ho_luot
        import scheduler
        ma = dong_ho_luot.ma_luot()
        return None if ma is None else (scheduler.get_current_chat() or "", ma)
    except Exception:  # noqa: BLE001
        return None


def _ghi_sheet(title: str, ads: list[dict], nhan: str, platform: str, country: str,
               active_status: str, total=None, limit=None
               ) -> tuple[str | None, bool, str | None, bool, dict]:
    """Ghi các ad đã bóc vào Lark Sheet (lớp trình bày chung `trinh_bay_sheet`). -> (sheet_url,
    đã cấp quyền cho người hỏi, lỗi, ghi nối vào sheet có sẵn của lượt, kiểm ghi
    {day_du, kiem_ghi, bang_tinh_tiep}). Lỗi ghi sheet KHÔNG làm hỏng kết quả tra — trả kèm
    để Mark nói ra."""
    import apify_tool as A
    import trinh_bay_sheet as TB
    try:
        import memory_store
        sender = memory_store.get_current_sender()
    except Exception:  # noqa: BLE001
        sender = None
    ngay = datetime.datetime.now(_VN_TZ).date()
    note = _ghi_chu_brand(nhan, platform, country, active_status, len(ads), total, limit)
    khoa = _khoa_luot()
    # Giữ khoá của LƯỢT suốt lời gọi Lark (vài giây).
    with _khoa_cho(khoa):
        co = _SHEET_LUOT.get(khoa) if khoa else None
        if co:
            dong = _dong_sheet(ads, nhan, platform, country, active_status, ngay,
                               stt_dau=co["dong"])
            cot = _cot_sheet()
            try:
                # Ngày ghi dạng chữ dd/MM/yyyy: định dạng đặt SAU khi ghi (trang_tri_bang).
                with TB.ngan_sach_cho():          # chờ 429 có trần, như `xuat`
                    TB._noi_luoi(co["tok"], co["sid"],
                                 TB._luoi(co["tok"]).get(co["sid"], (0, 0)),
                                 co["dong"] + len(dong), len(cot))
                    TB._ghi(co["tok"], co["sid"],
                            [[TB._o(v, c.kieu, False) for v, c in zip(r, cot)] for r in dong],
                            dong_dau=co["dong"] + 1)
            except Exception as e:  # noqa: BLE001
                # Sheet của lượt VẪN CÒN (đã có brand trước, đã cấp quyền) — trả đúng link,
                # lỗi chỉ là brand này chưa nối vào được.
                return (co["url"], co["granted"],
                        A._che_token(f"{type(e).__name__}: {e}")[:250], True, {})
            co["dong"] += len(dong)
            co["rows"] += dong
            co["notes"].append(note)
            with TB.ngan_sach_cho():              # trang trí + ghi lại Tổng quan
                kiem = _sau_khi_noi(co, title, ngay)
            return co["url"], co["granted"], None, True, kiem
        try:
            rows = _dong_sheet(ads, nhan, platform, country, active_status, ngay)
            bang, tq = _tong_quan_sheet(title, rows, [note], ngay)
            cap: dict = {"granted": False}

            def cap_quyen(tok):
                TB.gop_quyen(cap, A._grant(tok, sender) if sender else False)
            kq = TB.xuat(title, [bang], tq, cap_quyen=cap_quyen)
            granted = cap["granted"]
            if khoa and kq.tabs:
                tq_dong = len(TB.dung_tong_quan(kq.tong_quan or tq, kq.tabs, [], kq.kiem,
                                                kq.url)[0]) if kq.tong_quan_sid else 0
                with _SHEET_GUARD:
                    if len(_SHEET_LUOT) >= 200:
                        _SHEET_LUOT.pop(next(iter(_SHEET_LUOT)))
                    _SHEET_LUOT[khoa] = {"tok": kq.token, "sid": kq.tabs[0].sheet_id,
                                         "url": kq.url, "granted": granted,
                                         "dong": len(ads) + 1, "rows": list(rows),
                                         "notes": [note], "tabs": kq.tabs, "title": title,
                                         "tq_sid": kq.tong_quan_sid, "tq_dong": tq_dong}
            return kq.url, granted, None, False, kq.cho_tool()
        except Exception as e:  # noqa: BLE001
            return None, False, A._che_token(f"{type(e).__name__}: {e}")[:250], False, {}


def _sau_khi_noi(co: dict, title: str, ngay) -> dict:
    """Sau khi nối dòng của brand mới: trang trí lại tab dữ liệu cho đủ dòng mới (định dạng,
    bộ lọc), đọc lại kiểm, ghi đè Tổng quan theo toàn bộ dòng. Trang trí/Tổng quan hỏng chỉ
    cảnh báo (dữ liệu đã ghi). -> {day_du, kiem_ghi, bang_tinh_tiep}."""
    import trinh_bay_sheet as TB
    cb: list = []
    tab = co["tabs"][0]
    tab.so_dong = len(co["rows"])
    # Đọc lại dòng CUỐI vừa nối (không phải dòng cuối của lần ghi trước — review 09/10).
    cuoi = max((i for i, r in enumerate(co["rows"]) if any(v not in ("", None) for v in r)),
               default=None)
    tab.r_kiem = tab.dong_dau if cuoi is None else tab.dong_dau + 1 + cuoi
    TB.trang_tri_bang(co["tok"], co["sid"], tab.cot, tab.so_dong, mau=co["rows"],
                      dinh_dang_xong=False, canh_bao=cb)
    kiem = TB.kiem_ghi(co["tok"], co["tabs"])
    if co.get("tq_sid"):
        _, tq = _tong_quan_sheet(co.get("title") or title, co["rows"], co["notes"], ngay)
        ket = TB.ghi_lai_tong_quan(co["tok"], co["tq_sid"], co["url"], tq, co["tabs"],
                                   kiem=kiem, canh_bao=cb, so_dong_cu=co["tq_dong"])
        co["tq_dong"] = ket["so_dong"]
        kiem = TB.gop_kiem_tong_quan(kiem, ket)
    ra = {"day_du": kiem.get("day_du"), "kiem_ghi": kiem.get("cau") or "",
          "bang_tinh_tiep": None}
    if cb:
        ra["canh_bao_trinh_bay"] = "; ".join(c[:140] for c in cb[:4])[:600]
    return ra


FB_ADS_LIBRARY_SCHEMA = {
    "name": "fb_ads_library",
    "description": (
        "Tra QUẢNG CÁO đối thủ trên Meta Ad Library (facebook.com/ads/library) — "
        "trang CÔNG KHAI, KHÔNG cần login/API. Dùng khi được hỏi 'đối thủ đang chạy "
        "ads gì', tổng hợp ad đang chạy, nội dung/creative quảng cáo, số lượng ad. "
        "MỘT Ad Library bao trọn cả Facebook, Instagram, Messenger, Threads (không có "
        "Ad Library riêng cho IG/Threads). Muốn nghiên cứu RIÊNG một nền tảng (vd 'ads "
        "trên Threads') thì truyền `platform` — Meta lọc server-side.\n"
        "Cách dùng: truyền `page_id` (ID số của Trang FB → xem TẤT CẢ ad của trang) "
        "HOẶC `query` (tên brand/từ khoá khi chưa biết page_id). country mặc định VN, "
        "active_status mặc định active.\n"
        "Trả về: total_results, danh sách ad (library_id, ngày bắt đầu chạy, nội dung "
        "ad), và URL ảnh creative. LƯU Ý: ảnh là bản thu nhỏ (<=600px), link có hạn — "
        "tải ngay nếu cần; ad video chỉ lấy được thumbnail.\n"
        "Có ad thì tự ghi một Lark Sheet theo dõi (mỗi ad một dòng, kèm link Ad Library); "
        "tra nhiều brand trong CÙNG một lượt thì ghi nối vào cùng một sheet (`sheet_ghi_noi`) — "
        "gửi NGUYÊN `sheet_url`. Có `loi_sheet` mà KHÔNG có `sheet_url` thì nói rõ chưa ghi "
        "được sheet; có cả hai thì sheet vẫn có nhưng brand này chưa nối vào được."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "page_id": {
                "type": "string",
                "description": "ID số của Trang Facebook (view_all_page_id). Cho ra TẤT CẢ ad của trang đó.",
            },
            "query": {
                "type": "string",
                "description": "Tên brand/advertiser hoặc từ khoá — dùng khi chưa biết page_id.",
            },
            "country": {
                "type": "string",
                "description": "Mã quốc gia 2 ký tự (mặc định VN). VD: VN, US, TH.",
            },
            "active_status": {
                "type": "string",
                "enum": ["active", "inactive", "all"],
                "description": "active = đang chạy (mặc định); all = cả đã dừng; inactive = đã dừng.",
            },
            "platform": {
                "type": "string",
                "enum": ["facebook", "instagram", "messenger", "threads", "audience_network"],
                "description": (
                    "Lọc theo NỀN TẢNG hiển thị. Bỏ trống = tất cả. Dùng khi được hỏi "
                    "riêng 'ads trên Threads/Instagram/Facebook' — Meta lọc server-side "
                    "nên mọi ad trả về đúng nền tảng này."
                ),
            },
            "limit": {
                "type": "integer",
                "description": "Số ad tối đa cần bóc (mặc định 12, tối đa 40).",
                "minimum": 1,
                "maximum": 40,
            },
            "with_images": {
                "type": "boolean",
                "description": "Có lấy URL ảnh creative không (mặc định true).",
            },
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
        },
        "required": [],
    },
}


def _handle_fb_ads_library(args: dict, **kwargs) -> str:
    if not _BROWSER_OK:
        return tool_error(
            "Trình duyệt (agent-browser) chưa dùng được nên không mở được Ad Library. "
            f"Chi tiết: {_IMPORT_ERR}"
        )
    page_id = str(args.get("page_id") or "").strip()
    query = str(args.get("query") or "").strip()
    if not page_id and not query:
        return tool_error("Cần `page_id` (ID số Trang FB) hoặc `query` (tên brand/từ khoá).")
    country = (str(args.get("country") or "VN").strip() or "VN").upper()
    active_status = (str(args.get("active_status") or "active").strip().lower())
    if active_status not in ("active", "inactive", "all"):
        active_status = "active"
    platform = (str(args.get("platform") or "").strip().lower())
    if platform not in _PLATFORMS:
        platform = ""
    try:
        limit = int(args.get("limit") or 12)
    except (TypeError, ValueError):
        limit = 12
    limit = max(1, min(limit, _MAX_ADS))
    with_images = args.get("with_images", True)

    url = _ads_library_url(page_id, query, country, active_status, platform)

    # 1) Navigate (shared session so snapshot/images see the same page).
    try:
        nav = json.loads(browser_navigate(url=url, task_id=_TASK_ID))
    except Exception as e:  # noqa: BLE001
        return tool_error(f"Lỗi mở Ad Library: {type(e).__name__}: {e}")
    if not nav.get("success"):
        return tool_error(f"Không mở được Ad Library: {nav.get('error')}")
    title = nav.get("title", "")

    # 2) Let the SPA render; scroll to lazy-load more ad cards. A single
    #    accessibility snapshot only holds a few cards, so we ACCUMULATE across
    #    scroll steps (dedupe by library_id, keep the richest caption) until we
    #    have `limit` ads, hit the empty-state, or stop growing.
    collected: dict[str, dict] = {}
    total = None
    snap = ""
    stagnant = 0
    for i in range(12):
        time.sleep(5 if i == 0 else 2.5)
        snap = _full_snapshot()  # untruncated snapshot (public wrapper caps at ~8000 chars)
        if not snap:
            continue
        low = snap.lower()
        if total is None:
            total = _total_results(snap)
        before = len(collected)
        for ad in _parse_ads(snap, _MAX_ADS):
            lid = ad["library_id"]
            prev = collected.get(lid)
            if prev is None or len(ad.get("text") or "") > len(prev.get("text") or ""):
                collected[lid] = ad
        if not collected and any(k in low for k in _NO_ADS):
            break
        if len(collected) >= limit:
            break
        stagnant = stagnant + 1 if len(collected) == before else 0
        if stagnant >= 3:
            break
        try:
            browser_scroll(direction="down", task_id=_TASK_ID)
        except Exception:  # noqa: BLE001
            pass

    low = snap.lower()
    if not snap:
        return tool_error("Ad Library không trả nội dung (trang có thể chưa render kịp). Thử lại.")
    if any(k in low for k in _LOGIN_WALL) and "ad library" not in low and "thư viện quảng cáo" not in low:
        return tool_error("Trang đòi đăng nhập bất thường — thử lại hoặc kiểm tra URL/page_id.")

    ads = list(collected.values())[:limit]
    if not ads and (total == 0 or any(k in low for k in _NO_ADS)):
        return tool_result(
            success=True, source="facebook_ads_library", url=url,
            page_id=page_id or None, query=query or None, country=country,
            active_status=active_status, platform=platform or None,
            total_results=0, ads_returned=0,
            ads=[], image_count=0, image_urls=[], page_title=title,
            note="Không có ad nào khớp (trang này hiện không chạy ad theo bộ lọc). "
                 "Thử active_status=all để xem ad đã dừng.",
        )

    images: list[str] = []
    if with_images:
        try:
            im = json.loads(browser_get_images(task_id=_TASK_ID))
            images = _filter_images(im.get("images") or im.get("data") or [])
        except Exception:  # noqa: BLE001
            images = []

    sheet_url, granted, loi_sheet, ten_sheet, ghi_noi = None, False, None, None, False
    kiem: dict = {}
    if ads and _duoc_ghi_sheet():
        nhan = f"page_id {page_id}" if page_id else query
        ten_sheet = (str(args.get("title") or "").strip()
                     or f"Ads Meta · {nhan} · {country}"[:77]
                     + f" · {datetime.datetime.now(_VN_TZ):%d-%m-%Y}")
        sheet_url, granted, loi_sheet, ghi_noi, kiem = _ghi_sheet(
            ten_sheet, ads, nhan, platform, country, active_status, total=total, limit=limit)
    if kiem.get("day_du") is False:
        kiem["canh_bao_sheet"] = "Sheet có thể thiếu dữ liệu: " + str(kiem.get("kiem_ghi") or "")

    return tool_result(
        success=True,
        source="facebook_ads_library",
        sheet_url=sheet_url,
        granted=granted,
        title=ten_sheet,
        loi_sheet=loi_sheet,
        sheet_ghi_noi=ghi_noi or None,
        url=url,
        page_id=page_id or None,
        query=query or None,
        country=country,
        active_status=active_status,
        platform=platform or None,
        total_results=total,
        ads_returned=len(ads),
        ads=ads,
        image_count=len(images),
        image_urls=images,
        page_title=title,
        **kiem,
        note=(
            "Ảnh creative là bản thu nhỏ (<=600px) và URL có token hết hạn — tải ngay "
            "nếu cần dùng. Ad video chỉ lấy được thumbnail. total_results là tổng ad "
            "trên Ad Library; danh sách `ads` chỉ gồm số ad đã bóc theo limit."
        ),
    )


def _check_available() -> bool:
    return _BROWSER_OK


def register() -> None:
    try:
        registry.register(
            name="fb_ads_library",
            toolset=_TOOLSET,
            schema=FB_ADS_LIBRARY_SCHEMA,
            handler=_handle_fb_ads_library,
            check_fn=_check_available,
            requires_env=[],
            is_async=False,
            description="Tra ads đối thủ trên Meta Ad Library qua trình duyệt (không cần login/API)",
            emoji="\U0001f4e2",
            override=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[fb_ads_tool] register warning: {e}")


register()
