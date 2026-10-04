"""Register a `social_deep_dive` tool — kéo BÌNH LUẬN của các bài cụ thể về một
Lark Sheet riêng, GÁN NHÃN sắc thái + chủ đề từng bình luận, thống kê, cấp quyền cho
người hỏi, trả link.

Vì sao cần
----------
`social_listen` chỉ trả về caption + số liệu tương tác. Nhưng sentiment thật —
khen/chê, hỏi giá, so sánh đối thủ, phàn nàn chất lượng — nằm ở BÌNH LUẬN.
Persona của Mark có nhiệm vụ "đánh giá sức khoẻ thương hiệu (sentiment, share of
voice, cảnh báo khủng hoảng)", mà không đọc được comment thì không làm nổi.

Cách dùng: lấy `Link` từ sheet của `social_listen` rồi truyền vào đây.

Nền tảng — đo thật 27/08/2026
------------------------------
- TikTok  (clockworks/tiktok-comments-scraper, 4.59*): CHẠY. Trả text, diggCount,
  uniqueId, createTimeISO, likedByAuthor, replyCommentTotal.
- YouTube (streamers/youtube-comments-scraper, 4.89*): CHẠY. Trả comment, author,
  voteCount, replyCount, publishedTimeText. LƯU Ý: thời gian là chữ tương đối
  ("2 years ago"), KHÔNG phải mốc tuyệt đối.
  Actor này bắt maxTotalChargeUsd >= 0.50 (trần cho phép, không phải phí thực).
- Facebook (apify/facebook-comments-scraper, 4.73*): chạy được nhưng khi bài
  không có comment / bài riêng tư thì trả về OBJECT LỖI
  {"error": "no_items", "errorDescription": "..."} chứ KHÔNG phải mảng rỗng.
  Không bắt trường `error` thì sẽ map nhầm object đó thành một "bình luận".
  Tên trường khi có dữ liệu chưa kiểm chứng được (chưa tìm ra bài FB nào có
  comment) -> map phòng thủ nhiều tên ứng viên, không khớp thì BÁO RA thay vì
  ghi dòng rỗng.

Threads và Instagram — đo thật 04/10/2026, KHÔNG đăng nhập
-----------------------------------------------------------
- Threads (futurizerush/threads-replies-scraper): bài hapas.vn DeBjCyXDzaz trả 19/21 trả
  lời, không có trả lời lồng nhau. Mỗi lượt tối đa 20 bài, `max_replies` 10–300. Phí 0,02
  USD khởi động (ghim RAM 1 GB) + 0,0025/dòng, và actor TÍNH TIỀN cả dòng bài gốc
  (`item_type`="original_post") — bỏ khỏi bảng nhưng tính vào ước tính. Dự phòng:
  fetch_cat/threads-replies-scraper (0,005 + 0,0002/trả lời, lấy 14/21).
- Instagram (apify/instagram-comment-scraper, 0,0026/bình luận): bài /p/DHn78JLv9-U/ trả
  8/18 bình luận thấy được khi chưa đăng nhập. Dự phòng:
  apidojo/instagram-comments-scraper-api (0,0075/bài + 0,0005/bình luận, chậm hơn).
- Chưa đăng nhập thì cả hai KHÔNG trả trả-lời-lồng-nhau, Instagram chỉ trả một PHẦN bình
  luận — Mark phải nói ra (`gioi_han_nen_tang`), không trình bày như đủ.
- Công tắc `bat_<p>` và trần USD riêng `tran_usd_<p>` của console (Quét mạng xã hội) áp
  cho MỌI nền tảng (04/10/2026 — trước chỉ Threads/Instagram, chủ agent đặt `bat_tiktok=0`
  mà bóc bình luận TikTok vẫn chạy); trần cả lượt vẫn là `tran_usd_goi`, lấy mức chặt hơn.
- Nguồn chính HỎNG thì chạy nguồn dự phòng trong PHẦN CÒN LẠI của trần lô (cùng cách
  `tiktok_ads_tool._tran_du_phong`): tiền nguồn chính + trần dự phòng ≤ trần lô.

Trần chi phí — đo thật 01/10/2026
---------------------------------
Thứ cắt dữ liệu thật là TRẦN USD MỖI LƯỢT CHẠY actor, không phải số bài: 25 bài TikTok
gửi chung MỘT lượt (maxItems = 50 × 25) thì lượt đó chạm trần 0,37 USD sau ~300 bình
luận, 12 bài có bình luận, 13 bài sau hiện 0 — mà mô tả tool lại dặn "0 comment là BÌNH
THƯỜNG", nên Mark báo 13 bài "chưa ai bình luận". Nay: chia lô sao cho MỖI lượt nằm gọn
trong trần riêng của tool này (`tran_usd_goi` trên console, mặc định 0,5 USD — đủ mức
0,5 USD actor YouTube đòi; mượn trần của social_listen 0,37 thì YouTube bị từ chối),
chạy tối đa 3 lô song song, và bài rỗng trong lô chạm trần được báo "CÓ THỂ BỊ CẮT".
Giá gói FREE: TikTok 0,00125 USD/bình luận, YouTube 0,002, Facebook 0,0025 + 0,001/lượt.

YouTube — YouTube Data API v3 làm nguồn CHÍNH (04/10/2026)
-----------------------------------------------------------
- `commentThreads.list` (part=snippet,replies, 100/trang, order=relevance, lật pageToken) +
  `comments.list` cho luồng có nhiều trả lời hơn số kèm sẵn (API kèm tối đa 5). Mỗi lượt gọi
  1 đơn vị quota trên 10.000 đơn vị miễn phí/ngày (sổ ngày dùng chung với search của
  social_listen: `apify_tool._youtube_dem_dv`). 0 USD — không giữ trần, không ghi sổ chi
  phí Apify; thời gian là mốc tuyệt đối; dòng trả lời có cột "Trả lời bình luận" (link gốc).
- Actor streamers~youtube-comments-scraper (đòi giữ 0,5 USD mỗi lượt) chỉ còn là DỰ PHÒNG khi:
  không có `YOUTUBE_DATA_API_KEY`, hết quota (403 quotaExceeded — ghi sổ ngày, lượt sau đi
  thẳng dự phòng), lỗi HTTP/kết nối. Dự phòng chạy trong PHẦN CÒN LẠI của trần lượt gọi
  (`_SoNganSach.xin(..., ngoai_ke_hoach=True)` + `_tran_du_phong`), không ăn chỗ các lô khác.
- Video TẮT bình luận (403 commentsDisabled) hoặc không tồn tại (404 videoNotFound): báo
  từng video, KHÔNG chạy dự phòng — actor cũng không lấy được gì mà vẫn giữ 0,5 USD.

Trần của chủ agent là trần CỨNG (chốt 01/10/2026): console đặt `tran_binh_luan` và
`tran_usd_goi` cho MỖI lần gọi; trong trần người dùng xin bao nhiêu cũng được (tới
`_MAX_PER_POST` bình luận/bài), vượt trần thì KHÔNG chạy — trả `vuot_tran` kèm mức vừa trần.
Không còn cờ `xac_nhan_chi_phi` để chạy vượt; hỏi "Chạy nhé?" là việc của lời dặn prompt.
"""

from __future__ import annotations

import contextvars
import datetime
import html
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait

import apify_tool as A
import chi_phi_tool
import memory_store
import phan_loai
from apify_tool import (_VN_TZ, _call, _che_token, _grant, _create_sheet,
                        _first_sheet_id, _to_vn, lark)

from tools.registry import registry, tool_error, tool_result  # type: ignore

_TOOLSET = "social"
# Đọc input schema 3 actor ngày 02/10/2026 (commentsPerPost / maxComments / resultsLimit):
# đều là integer KHÔNG có maximum. 1000/bài là trần của tool; tổng vẫn bị `tran_binh_luan`
# chặn. TikTok tự ghi chú bài nghìn bình luận có thể trả ít hơn số xin.
_MAX_PER_POST = 1000
_MAX_POSTS = 50

_ACTORS = {
    "tiktok": "clockworks~tiktok-comments-scraper",
    "youtube": "streamers~youtube-comments-scraper",
    "facebook": "apify~facebook-comments-scraper",
    "threads": "futurizerush~threads-replies-scraper",
    "instagram": "apify~instagram-comment-scraper",
}
# Nguồn DỰ PHÒNG khi nguồn chính hỏng (đo thật 04/10/2026, xem docstring).
_ACTORS_DU_PHONG = {
    "threads": "fetch_cat~threads-replies-scraper",
    "instagram": "apidojo~instagram-comments-scraper-api",
}
# Actor YouTube từ chối chạy nếu trần chi phí < 0.50 (đo thật).
_MIN_CHARGE = {"youtube": 0.5, "facebook": 0.5}
# Giá gói FREE (Apify, 01/10/2026). Ước tính dùng giá này nên CAO hơn gói trả tiền.
_GIA = {"tiktok": 0.00125, "youtube": 0.002, "facebook": 0.0025,
        "threads": 0.0025, "instagram": 0.0026}
_GIA_KHOI_DONG = {"facebook": 0.001, "threads": 0.02}
# Tiền tính thêm cho MỖI BÀI của lượt: Threads tính cả dòng bài gốc (`original_post`).
_GIA_MOI_BAI = {"threads": 0.0025}
# (dưới, trên) số bình luận/bài actor nhận: Threads `max_replies` chỉ nhận 10–300.
_PER_KHOANG = {"threads": (10, 300)}
_BAI_MOI_LO = {"threads": 20}           # Threads: tối đa 20 link mỗi lượt
_RAM = {"threads": 1024}                # phí khởi động Threads tính theo GB RAM
# Dự phòng: (phí khởi động, mỗi bình luận, mỗi bài). apidojo IG cho 15 bình luận đầu
# mỗi bài miễn phí — bỏ qua cho ước tính cao hơn thực tế. YouTube: nguồn chính là API
# miễn phí, dự phòng là chính actor streamers (giá `_GIA["youtube"]`).
_GIA_DU_PHONG = {"threads": (0.005, 0.00021, 0.0), "instagram": (0.0, 0.0005, 0.0075),
                 "youtube": (0.0, 0.002, 0.0)}
# Lỗi mà nguồn dự phòng cũng gặp y hệt — không chạy dự phòng (như tiktok_ads_tool).
_KHONG_DU_PHONG = {"HET_TIEN_THANG", "NGHEN_DONG_THOI", "DA_HUY", "QUA_GIO"}
# Nền tảng theo công tắc + trần riêng của console "Quét mạng xã hội" (`bat_<p>`,
# `tran_usd_<p>` — xem apify_tool._tran_nen_tang).
# MỌI nền tảng (04/10/2026). YouTube: `tran_usd_youtube` không có (apify_tool._khoa_rieng
# bỏ qua — API miễn phí), nhưng `bat_youtube`=0 vẫn tắt cả đường API lẫn dự phòng.
_THEO_CONSOLE_QUET = ("tiktok", "youtube", "facebook", "threads", "instagram")
# Giới hạn khi chưa đăng nhập — Mark phải nói ra khi báo kết quả nền tảng đó.
_GIOI_HAN = {
    "threads": ("Threads (không đăng nhập): chỉ lấy trả lời cấp 1 công khai, KHÔNG có trả "
                "lời lồng nhau; có thể thiếu vài trả lời so với số trên bài."),
    "instagram": ("Instagram (không đăng nhập): chỉ lấy được MỘT PHẦN bình luận thấy được "
                  "công khai (đo thật 8/18), KHÔNG có trả lời lồng nhau — không phải toàn "
                  "bộ bình luận của bài."),
}
# ── YouTube Data API v3 (nguồn chính, miễn phí; xem docstring) ──
_YT_API_NGUON = "YouTube Data API v3 (miễn phí)"
_YT_TRANG = 100               # maxResults tối đa của commentThreads.list / comments.list
_YT_BAI_MOI_LO = 10           # video mỗi lô API (một lô = một luồng gọi tuần tự)
_YT_THU_TU = "relevance"      # bình luận được quan tâm nhất trước (hoặc "time")
_YT_QUOTA_NGAY = 10000        # đơn vị quota miễn phí mỗi ngày (giờ Pacific)
_YT_TOC = 50.0                # bình luận/giây ước tính (một lượt ~100 dòng ~1–2 giây)
_YT_HET_QUOTA = ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded")
_TAT_BL = "VIDEO TẮT BÌNH LUẬN"
# None = tự đọc (có key và hôm nay chưa hết quota); `_handle` chốt MỘT lần cho cả lượt gọi
# (lô chạy trong bản sao context) để kế hoạch, sổ tiền và lúc chạy không lệch nhau.
_YT_API: contextvars.ContextVar = contextvars.ContextVar("dd_yt_api", default=None)


def _yt_api_san_sang() -> bool:
    return A._youtube_co_key() and not A._youtube_het_quota()


def _mien_phi(p: str) -> bool:
    """Nền tảng `p` có kéo bằng nguồn MIỄN PHÍ trong lượt này không (YouTube Data API)."""
    if p != "youtube":
        return False
    v = _YT_API.get()
    return _yt_api_san_sang() if v is None else bool(v)


_BIEN = 0.9            # mỗi lô chỉ tiêu tối đa 90% trần: giá thật lệch chút vẫn không chạm
_SONG_SONG = 3
# Chừa cho gán nhãn + ghi sheet sau khi kéo xong (trong `_TOOL_DEADLINE` 135s).
_DANH_CHO_SAU = 40
_PHAN_LOAI_TOI_DA = 50

# Ô cấu hình của chủ agent trên console (Năng lực → social_deep_dive). Giá trị thô bị kẹp.
# Chủ agent chốt 01–02/10/2026: console cho tới 30.000 bình luận / 50 USD mỗi lần gọi; lượt
# lớn chạy NỀN (viec_nen), lượt tại chỗ vẫn kẹp `apify_tool._TRAN_USD_TUONG_TAC` (5 USD).
_TRAN_BL = (300, 50, 30000)      # (mặc định, thấp nhất, cao nhất) TỔNG bình luận mỗi lần gọi
_TRAN_USD = (0.5, 0.1, 50.0)     # USD mỗi lần gọi (cả lượt), cũng là trần MỖI lượt chạy actor

_HEADER = ["Nền tảng", "Người bình luận", "Nội dung bình luận", "Sắc thái", "Chủ đề",
           "Likes", "Trả lời", "Thời gian", "Tác giả đã thích", "Link bài",
           "Trả lời bình luận"]          # link bình luận GỐC của dòng trả lời (YouTube API)
_TAB_THONG_KE = "Thống kê"
_CAT = "CÓ THỂ BỊ CẮT DO TRẦN CHI PHÍ"
_CHUA_CHAY_GIO = "CHƯA CHẠY — hết thời gian"
_CHUA_CHAY_NS = "CHƯA CHẠY — chạm ngân sách lượt"
_CHUA_XONG_GIU = "CHƯA XONG — giữ phần đã lấy"

# Trần USD MỖI LÔ = ước tính lô × 1,5 (kẹp [mức actor đòi hoặc 0,1; trần tool]). Rà
# 01/10/2026: lô nào cũng được cả `tran_usd_goi` nên N lô có thể tiêu tới N × ngân sách
# đã duyệt nếu giá actor lệch. Cả lượt gọi tool thì giữ sổ (`_SoNganSach`): trần Apify
# gửi cho mỗi lô CHÍNH LÀ phần nó giữ chỗ, cắt cho vừa phần còn lại sau khi để dành phần
# cần của các lô chưa chạy — tổng tiền có thể bị tính luôn ≤ `tran_usd_goi`.
_HE_SO_TRAN_LO = 1.5
# Còn ít hơn chừng này giây tới hạn run thì không khởi chạy lô (vẫn mất phí start mà
# run bị huỷ ngay).
_GIAY_TOI_THIEU_LO = 20


def _kep(v, md: float, lo: float, hi: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return md
    return md if v != v else min(hi, max(lo, v))


def _cau_hinh(nen: bool | None = None) -> tuple[int, float]:
    """(trần bình luận, trần USD) mỗi lần gọi tool — trần CỨNG do chủ agent đặt. Trần USD
    kẹp thêm 5 USD trừ khi lập kế hoạch/chạy cho việc NỀN (`nen=True` hoặc `A._NEN`)."""
    try:
        import lsr_policy
        c = lsr_policy.cau_hinh_tool("social_deep_dive")
    except Exception:  # noqa: BLE001 — đọc hỏng thì dùng mặc định
        c = {}
    nen = A._NEN.get() if nen is None else nen
    usd = _kep(c.get("tran_usd_goi"), *_TRAN_USD)
    return (int(_kep(c.get("tran_binh_luan"), *_TRAN_BL)),
            round(usd if nen else min(usd, A._TRAN_USD_TUONG_TAC), 2))


def _platform_of(url: str) -> str | None:
    u = (url or "").lower()
    if "tiktok.com" in u:
        return "tiktok"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "facebook.com" in u or "fb.com" in u or "fb.watch" in u:
        return "facebook"
    if "instagram.com" in u:
        return "instagram"
    if "threads.net" in u or "threads.com" in u:
        return "threads"
    return None


def _tran_p(p: str, tran_usd: float) -> float:
    """Trần USD MỖI LƯỢT của nền tảng `p`: trần của tool, hạ thêm theo `tran_usd_<p>` trên
    console Quét mạng xã hội nếu chủ agent đặt riêng — lấy mức CHẶT hơn trong hai."""
    if p not in _THEO_CONSOLE_QUET:
        return tran_usd
    c = A._cau_hinh_quet()
    if "usd" not in A._khoa_rieng(p, c):
        return tran_usd
    return round(min(tran_usd, A._kep(c.get(f"tran_usd_{p}"), *A._TRAN_USD_KHOANG,
                                      tran_usd)), 2)


# ───────────────────────── quy bình luận về bài ─────────────────────────
# Bản cũ đếm bằng "link gửi đi là CHUỖI CON của link bình luận": …/video/1 khớp luôn
# …/video/11, còn link rút gọn vt.tiktok.com thì không bao giờ khớp. Nay so theo ID bài.
_ID_RE = {
    "tiktok": [r"/(?:video|photo)/(\d{6,})", r"[?&]item_id=(\d+)"],
    "youtube": [r"[?&]v=([\w-]{11})", r"youtu\.be/([\w-]{11})",
                r"/(?:shorts|live|embed)/([\w-]{11})"],
    "facebook": [r"story_fbid=(\w+)", r"[?&]fbid=(\d+)", r"/posts/(\w+)",
                 r"/(?:videos|reel|reels|permalink)/(?:[^/?#]+/)?(\d+)", r"[?&]v=(\d+)"],
    # threads.net và threads.com cùng một mã bài: …/@kenh/post/<mã>, link cũ …/t/<mã>.
    "threads": [r"/post/([\w-]+)", r"threads\.(?:net|com)/t/([\w-]+)"],
    "instagram": [r"/(?:p|reels?|tv)/([\w-]+)"],
}


def _id_bai(url: str) -> str | None:
    p = _platform_of(url)
    for rx in _ID_RE.get(p or "", []):
        m = re.search(rx, url or "")
        if m:
            return f"{p}:{m.group(1)}"
    return None


def _chuan(url: str) -> str:
    u = re.sub(r"^https?://(?:www\.|m\.)?", "", str(url or "").strip().lower()).split("#")[0]
    # Query của TikTok chỉ là mã theo dõi (?is_from_webapp=…); của YouTube/Facebook thì
    # chứa chính ID bài (watch?v=…, story_fbid=…) — bỏ đi là mọi link YouTube "bằng nhau".
    if "tiktok.com" in u:
        u = u.split("?")[0]
    return u.rstrip("/")


def _quy_ve_bai(nguon: list[str], us: list[str]) -> str:
    """Link bài (trong `us`) mà bình luận thuộc về, "" nếu không quy được."""
    ids = {_id_bai(x) for x in nguon if x} - {None}
    chuan = {_chuan(x) for x in nguon if x}
    for u in us:
        i = _id_bai(u)
        if (i and i in ids) or _chuan(u) in chuan:
            return u
    # Lô một bài: mọi bình luận của lượt đó là của bài ấy (cứu link rút gọn không mở được).
    return us[0] if len(us) == 1 else ""


# ───────────────────────── adapter từng nền tảng ─────────────────────────
def _first(d: dict, *names, default=""):
    """Lấy giá trị đầu tiên có trong dict theo danh sách tên ứng viên."""
    for n in names:
        v = d.get(n)
        if v not in (None, ""):
            return v
    return default


def _gio(raw) -> str:
    d = _to_vn(raw)
    return d.strftime("%Y-%m-%d %H:%M") if d else ""


def _fetch_tiktok(urls: list[str], per: int, tran_usd: float) -> tuple[list[dict], int]:
    raw = _call(_ACTORS["tiktok"], _payload("tiktok", urls, per),
                per * len(urls), tran_usd=tran_usd)
    return _map_tiktok(raw)


def _payload(p: str, urls: list[str], per: int) -> dict:
    if p == "tiktok":
        return {"postURLs": urls, "commentsPerPost": per}
    if p == "youtube":
        return {"startUrls": [{"url": u} for u in urls], "maxComments": per}
    if p == "threads":
        lo, hi = _PER_KHOANG["threads"]
        return {"post_urls": [{"url": u} for u in urls],
                "max_replies": max(lo, min(hi, per)), "include_nested_replies": False}
    if p == "instagram":
        return {"directUrls": list(urls), "resultsLimit": per}
    return {"startUrls": [{"url": u} for u in urls], "resultsLimit": per}


def _payload_du_phong(p: str, urls: list[str], per: int) -> dict:
    if p == "threads":
        return {"postUrls": [{"url": u} for u in urls], "maxRepliesPerThread": per,
                "maxDepth": 1}
    return {"startUrls": list(urls), "maxItems": per * len(urls), "fetchReplies": False}


def _limit(p: str, urls: list[str], per: int) -> int:
    """Số item đọc về của một lượt: Threads trả thêm một dòng bài gốc mỗi bài."""
    return per * len(urls) + (len(urls) if p in _GIA_MOI_BAI else 0)


def _map_tiktok(raw: list) -> tuple[list[dict], int]:
    return [{
        "kenh": it.get("uniqueId") or "",
        "text": str(it.get("text") or "")[:1000],
        "likes": int(it.get("diggCount") or 0),
        "replies": int(it.get("replyCommentTotal") or 0),
        "thoi_gian": _gio(it.get("createTimeISO")),
        "tac_gia_thich": "có" if it.get("likedByAuthor") else "",
        "link": it.get("videoWebUrl") or it.get("submittedVideoUrl") or "",
        "_nguon": [str(it.get(k) or "") for k in
                   ("videoWebUrl", "submittedVideoUrl", "inputUrl", "url")],
    } for it in raw], len(raw)


def _fetch_youtube(urls: list[str], per: int, tran_usd: float) -> tuple[list[dict], int]:
    raw = _call(_ACTORS["youtube"], _payload("youtube", urls, per),
                per * len(urls), min_charge=_MIN_CHARGE["youtube"], tran_usd=tran_usd)
    return _map_youtube(raw)


def _map_youtube(raw: list) -> tuple[list[dict], int]:
    return [{
        "kenh": it.get("author") or "",
        "text": str(it.get("comment") or "")[:1000],
        "likes": int(it.get("voteCount") or 0),
        "replies": int(it.get("replyCount") or 0),
        # publishedTimeText là chữ tương đối ("2 years ago") — giữ nguyên văn,
        # KHÔNG bịa thành ngày tuyệt đối.
        "thoi_gian": str(it.get("publishedTimeText") or ""),
        "tac_gia_thich": "có" if it.get("hasCreatorHeart") else "",
        "link": it.get("pageUrl") or "",
        "_nguon": [str(it.get(k) or "") for k in ("pageUrl", "videoUrl", "inputUrl", "url")]
                  + ([f"https://www.youtube.com/watch?v={it['videoId']}"]
                     if it.get("videoId") else []),
    } for it in raw], len(raw)


def _fetch_facebook(urls: list[str], per: int, tran_usd: float) -> tuple[list[dict], int]:
    raw = _call(_ACTORS["facebook"], _payload("facebook", urls, per),
                per * len(urls), min_charge=_MIN_CHARGE["facebook"], tran_usd=tran_usd)
    return _map_facebook(raw)


def _map_facebook(raw: list) -> tuple[list[dict], int]:
    out, la = [], []
    for it in raw:
        if it.get("error"):          # {"error":"no_items", ...} chứ không phải comment
            continue
        txt = _first(it, "text", "message", "commentText", "comment")
        if not txt:                  # shape lạ -> nhớ lại để BÁO RA, đừng ghi dòng rỗng
            la.append(sorted(it.keys())[:12])
            continue
        out.append({
            "kenh": str(_first(it, "profileName", "authorName", "name", "author")),
            "text": str(txt)[:1000],
            "likes": int(_first(it, "likesCount", "likeCount", "reactionsCount", default=0) or 0),
            "replies": int(_first(it, "replyCount", "commentsCount", default=0) or 0),
            "thoi_gian": _gio(_first(it, "date", "timestamp", "createdAt", default=None)),
            "tac_gia_thich": "",
            "link": str(_first(it, "facebookUrl", "commentUrl", "postUrl")),
            "_nguon": [str(it.get(k) or "") for k in
                       ("facebookUrl", "postUrl", "inputUrl", "url", "commentUrl")],
        })
    if la and not out:
        raise RuntimeError(
            "Actor Facebook trả về shape KHÔNG khớp map hiện tại — không ghi bừa. "
            f"Các key nhận được: {la[0]}. Báo lại để sửa mapping.")
    return out, len(raw)


def _so(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _bao_shape(p: str, la: list, out: list) -> None:
    if la and not out:
        raise RuntimeError(
            f"Actor {p} trả về shape KHÔNG khớp map hiện tại — không ghi bừa. "
            f"Các key nhận được: {la[0]}. Báo lại để sửa mapping.")


def _fetch_threads(urls: list[str], per: int, tran_usd: float) -> tuple[list[dict], int]:
    pl = _payload("threads", urls, per)
    raw = _call(_ACTORS["threads"], pl, _limit("threads", urls, pl["max_replies"]),
                mem=_RAM["threads"], tran_usd=tran_usd)
    return _map_threads(raw)


def _map_threads(raw: list) -> tuple[list[dict], int]:
    """futurizerush: một dòng/trả lời + MỘT dòng bài gốc (`item_type`="original_post") —
    dòng gốc bị tính tiền nên vẫn đếm vào số item thô, nhưng không phải bình luận."""
    out, la = [], []
    for it in raw:
        if it.get("error") or it.get("item_type") == "original_post":
            continue
        if "text_content" not in it and "author_username" not in it:
            la.append(sorted(it.keys())[:12])
            continue
        goc = str(it.get("source_post_url") or "")
        out.append({
            "kenh": str(it.get("author_username") or ""),
            "text": str(it.get("text_content") or "")[:1000],
            "likes": _so(it.get("like_count")),
            "replies": _so(it.get("reply_count")),
            "thoi_gian": _gio(it.get("created_at")),
            "tac_gia_thich": "có" if it.get("is_liked_by_author") else "",
            "link": goc,
            # KHÔNG đưa reply_url vào: …/post/<mã TRẢ LỜI> không phải mã bài.
            "_nguon": [goc] + [str(it.get(k) or "") for k in ("inputUrl", "url")],
        })
    _bao_shape("Threads", la, out)
    return out, len(raw)


def _map_threads_du_phong(raw: list) -> tuple[list[dict], int]:
    """fetch_cat: trả lời cấp 1 (`depth`=1); `createdAt` thường rỗng khi chưa đăng nhập."""
    out, la = [], []
    for it in raw:
        if it.get("error") or it.get("depth") == 0:
            continue
        if "text" not in it and "authorUsername" not in it:
            la.append(sorted(it.keys())[:12])
            continue
        goc = str(it.get("rootPostUrl") or it.get("sourceUrl") or "")
        out.append({
            "kenh": str(it.get("authorUsername") or ""),
            "text": str(it.get("text") or "")[:1000],
            "likes": _so(it.get("likeCount")),
            "replies": _so(it.get("replyCount")),
            "thoi_gian": _gio(it.get("createdAt")),
            "tac_gia_thich": "có" if it.get("isLikedByRootAuthor") else "",
            "link": goc,
            "_nguon": [str(it.get(k) or "") for k in ("sourceUrl", "rootPostUrl")],
        })
    _bao_shape("Threads (dự phòng)", la, out)
    return out, len(raw)


def _fetch_instagram(urls: list[str], per: int, tran_usd: float) -> tuple[list[dict], int]:
    raw = _call(_ACTORS["instagram"], _payload("instagram", urls, per),
                _limit("instagram", urls, per), tran_usd=tran_usd)
    return _map_instagram(raw)


def _map_instagram(raw: list) -> tuple[list[dict], int]:
    out, la = [], []
    for it in raw:
        if it.get("error"):
            continue
        if "text" not in it and "ownerUsername" not in it:
            la.append(sorted(it.keys())[:12])
            continue
        chu = it.get("owner") if isinstance(it.get("owner"), dict) else {}
        out.append({
            "kenh": str(it.get("ownerUsername") or chu.get("username") or ""),
            "text": str(it.get("text") or "")[:1000],
            "likes": _so(it.get("likesCount")),
            "replies": _so(it.get("repliesCount")),
            "thoi_gian": _gio(it.get("timestamp")),
            "tac_gia_thich": "",
            "link": str(it.get("postUrl") or ""),
            "_nguon": [str(it.get(k) or "") for k in
                       ("postUrl", "inputUrl", "url", "commentUrl")],
        })
    _bao_shape("Instagram", la, out)
    return out, len(raw)


def _map_instagram_du_phong(raw: list) -> tuple[list[dict], int]:
    out, la = [], []
    for it in raw:
        if it.get("error") or it.get("type") not in (None, "comment"):
            continue
        if "message" not in it and "user" not in it:
            la.append(sorted(it.keys())[:12])
            continue
        nd = it.get("user") if isinstance(it.get("user"), dict) else {}
        goc = str(it.get("inputSource") or "")
        out.append({
            "kenh": str(nd.get("username") or ""),
            "text": str(it.get("message") or "")[:1000],
            "likes": _so(it.get("likeCount")),
            "replies": _so(it.get("replyCount")),
            "thoi_gian": _gio(it.get("createdAt")),
            "tac_gia_thich": "",
            "link": goc,
            "_nguon": [goc] + ([f"https://www.instagram.com/p/{it['postId']}/"]
                               if it.get("postId") else []),
        })
    _bao_shape("Instagram (dự phòng)", la, out)
    return out, len(raw)


# ───────────────────────── YouTube Data API v3 (nguồn chính) ─────────────────────────
def _yt_link(vid: str) -> str:
    return f"https://www.youtube.com/watch?v={vid}"


def _yt_dong(sn: dict, vid: str, tra_loi: int = 0, cha: str = "") -> dict:
    """Một comment (snippet của commentThreads/comments) -> dòng chung của tool. `cha` =
    link bình luận gốc khi dòng này là TRẢ LỜI (rỗng với bình luận gốc)."""
    link = _yt_link(vid)
    return {
        "kenh": str(sn.get("authorDisplayName") or ""),
        "text": html.unescape(str(sn.get("textOriginal") or sn.get("textDisplay") or ""))[:1000],
        "likes": _so(sn.get("likeCount")),
        "replies": tra_loi,
        "thoi_gian": _gio(sn.get("publishedAt")),      # API cho mốc tuyệt đối (ISO 8601)
        "tac_gia_thich": "",                          # API không trả "tim của tác giả"
        "link": link,
        "cha": cha,
        "_nguon": [link],
    }


def _yt_mot_video(vid: str, per: int, han: float, dv: list) -> tuple[list[dict], bool]:
    """≤ `per` dòng (bình luận gốc + trả lời) của MỘT video -> (dòng, hết giờ giữa chừng).

    Lượt 1: lật `commentThreads.list` (kèm tối đa 5 trả lời mỗi luồng) tới khi đủ `per`
    hoặc hết trang. Lượt 2: còn chỗ thì `comments.list` (parentId) lấy nốt trả lời của các
    luồng có nhiều trả lời hơn số kèm sẵn. Ném `A.LoiYouTube` khi API báo lỗi."""
    rows: list[dict] = []
    thieu: list[tuple[str, str, set]] = []      # (id gốc, link gốc, id trả lời đã có)

    def goi(res: str, params: dict):
        con = han - time.monotonic()
        if con < 3:
            return None
        d = A._youtube_get(res, params, timeout=min(30.0, con))
        dv[0] += 1
        return d

    tok = None
    while len(rows) < per:
        d = goi("commentThreads", {"part": "snippet,replies", "videoId": vid,
                                   "maxResults": min(_YT_TRANG, max(1, per - len(rows))),
                                   "order": _YT_THU_TU, "textFormat": "plainText",
                                   **({"pageToken": tok} if tok else {})})
        if d is None:
            return rows, True
        for th in d.get("items") or []:
            if len(rows) >= per:
                break
            sn = th.get("snippet") or {}
            goc = sn.get("topLevelComment") or {}
            tong = _so(sn.get("totalReplyCount"))
            rows.append(_yt_dong(goc.get("snippet") or {}, vid, tong))
            cha = f"{_yt_link(vid)}&lc={goc.get('id') or ''}"
            kem = (th.get("replies") or {}).get("comments") or []
            da = set()
            for r in kem:
                if len(rows) >= per:
                    break
                rows.append(_yt_dong(r.get("snippet") or {}, vid, 0, cha))
                da.add(r.get("id"))
            if tong > len(kem) and goc.get("id"):
                thieu.append((goc["id"], cha, da))
        tok = d.get("nextPageToken")
        if not tok:
            break
    for goc_id, cha, da in thieu:
        tok = None
        while len(rows) < per:
            d = goi("comments", {"part": "snippet", "parentId": goc_id,
                                 "maxResults": _YT_TRANG, "textFormat": "plainText",
                                 **({"pageToken": tok} if tok else {})})
            if d is None:
                return rows, True
            for r in d.get("items") or []:
                if len(rows) >= per:
                    break
                if r.get("id") in da:
                    continue
                da.add(r.get("id"))
                rows.append(_yt_dong(r.get("snippet") or {}, vid, 0, cha))
            tok = d.get("nextPageToken")
            if not tok:
                break
        if len(rows) >= per:
            break
    return rows, False


def _yt_api_lo(lo: list[str], per: int, han: float) -> dict:
    """Kéo bình luận các video của một lô bằng YouTube Data API.

    -> {"binh_luan", "dv" (đơn vị quota), "loi_bai" {link: (trạng thái, lý do)} (tắt bình
    luận / không có video — KHÔNG dự phòng), "con_lai" [link cần nguồn dự phòng], "loi"
    (vì sao dự phòng), "mot_phan" [link hết giờ giữa chừng], "chua_chay" [link chưa tới
    lượt khi hết giờ]}."""
    ra = {"binh_luan": [], "dv": 0, "loi_bai": {}, "con_lai": [], "loi": "",
          "mot_phan": [], "chua_chay": []}
    dv = [0]
    het_gio = False
    for u in lo:
        if het_gio:
            ra["chua_chay"].append(u)
            continue
        if ra["loi"]:                     # lỗi chung (hết quota, key, mạng): khỏi gọi tiếp
            ra["con_lai"].append(u)
            continue
        vid = (_id_bai(u) or ":").split(":", 1)[1]
        if not vid:                       # không đọc được mã: actor dự phòng tự mở link
            ra["con_lai"].append(u)
            continue
        try:
            rows, het_gio = _yt_mot_video(vid, per, han, dv)
        except A.LoiYouTube as e:
            ly_do = getattr(e, "ly_do", "")
            if ly_do == "commentsDisabled":
                ra["loi_bai"][u] = (_TAT_BL, "Video đã TẮT bình luận (YouTube commentsDisabled) "
                                             "— không có gì để bóc, không chạy dự phòng.")
            elif ly_do == "videoNotFound":
                ra["loi_bai"][u] = ("LỖI", "YouTube không tìm thấy video (riêng tư/đã xoá/sai "
                                           "link — videoNotFound); không chạy dự phòng.")
            else:
                if ly_do in ("quotaExceeded", "dailyLimitExceeded"):
                    A._youtube_het_quota(True)
                ra["loi"] = _che_token(str(e))[:200]
                ra["con_lai"].append(u)
            continue
        except Exception as e:  # noqa: BLE001 — lỗi lạ: như lỗi HTTP, đi dự phòng
            ra["loi"] = _che_token(f"{type(e).__name__}: {e}")[:200]
            ra["con_lai"].append(u)
            continue
        ra["binh_luan"] += rows
        if het_gio:
            ra["mot_phan"].append(u)
    ra["dv"] = dv[0]
    if ra["con_lai"] and not ra["loi"]:
        ra["loi"] = "không đọc được mã video từ link"
    return ra


def _yt_du_phong(kq: dict, urls: list[str], per: int, so_ns: "_SoNganSach", han_run: float,
                 tran_usd: float, ly_do: str) -> None:
    """YouTube Data API không lấy được `urls` (không key/hết quota/lỗi HTTP): chạy actor
    streamers trong PHẦN CÒN LẠI của trần lượt gọi (lô API không giữ chỗ gì từ đầu nên
    `ngoai_ke_hoach`), cắt số bình luận/bài theo `_tran_du_phong`. Ghi vào `kq`."""
    actor = _ACTORS["youtube"]
    dp = {"urls": list(urls), "loi": "", "n_raw": 0, "per": 0, "ma": "OK", "actor": actor,
          "ly_do": ly_do}
    kq["du_phong_kq"] = dp
    dau = f"YouTube Data API: {ly_do} | dự phòng {actor}"
    if han_run - time.monotonic() < _GIAY_TOI_THIEU_LO:
        dp["loi"] = f"{dau} không chạy: hết thời gian của lượt"
        return
    tok = _YT_API.set(False)                      # tính như lô Apify thường
    try:
        can = _san("youtube")
        tran_lo = _tran_lo("youtube", _uoc_lo("youtube", urls, per), tran_usd)
    finally:
        _YT_API.reset(tok)
    cap = so_ns.xin(can, tran_lo, ngoai_ke_hoach=True)
    if not cap:
        dp["loi"] = (f"{dau} không chạy: phần còn lại của trần lượt gọi không đủ mức "
                     f"{_usd(can)} USD actor đòi giữ")
        return
    tran_dp, per_dp = _tran_du_phong("youtube", cap, 0.0, len(urls), per)
    if not per_dp or tran_dp + 1e-9 < can:
        so_ns.tra(cap, 0.0)
        dp["loi"] = f"{dau} không chạy: phần trần còn lại ({_usd(cap)} USD) không đủ"
        return
    kq.setdefault("actors", []).append(actor)
    so: list = []
    A._SO_RUN.set(so)
    A._HAN_CHOT.set(han_run)
    tien = 0.0
    try:
        raw = _call(actor, _payload("youtube", urls, per_dp), per_dp * len(urls),
                    min_charge=_MIN_CHARGE["youtube"], tran_usd=tran_dp)
        bl, n = _map_youtube(raw)
        tien = n * _GIA["youtube"]
        kq["binh_luan"] += bl
        dp.update(n_raw=n, per=per_dp)
    except Exception as e:  # noqa: BLE001
        tien = _da_tieu(so, tran_dp)
        dp["loi"] = (f"{dau}: " + _che_token(f"{type(e).__name__}: {e}"))[:400]
    finally:
        tien = max(tien, sum(float(m.get("usd") or 0) for m in so if isinstance(m, dict)))
        so_ns.tra(cap, tien)
        kq["tien"] = float(kq.get("tien") or 0) + tien
    if {m.get("ma") for m in so if isinstance(m, dict)} & {"OK_MOT_PHAN", "QUA_GIO"}:
        dp["ma"] = "OK_MOT_PHAN"


def _keo_lo_yt_api(kq: dict, lo: list[str], per: int, so_ns: "_SoNganSach",
                   han_run: float, tran_usd: float) -> dict:
    """Lô YouTube bằng API miễn phí: không xin sổ tiền; phần API không lấy được mới xin
    phần còn lại của trần cho actor dự phòng."""
    r = _yt_api_lo(lo, per, han_run)
    kq.update(yt_api=True, actors=[], binh_luan=r["binh_luan"], n_raw=len(r["binh_luan"]),
              dv=r["dv"], loi_bai=r["loi_bai"], mot_phan=r["mot_phan"],
              chua_chay=r["chua_chay"], tien=0.0)
    if r["con_lai"]:
        _yt_du_phong(kq, r["con_lai"], per, so_ns, han_run, tran_usd, r["loi"])
    return kq


def _trang_thai_yt(kq: dict, per_url: dict, failed: list) -> None:
    """Trạng thái TỪNG video của một lô API (lỗi riêng từng video, phần dự phòng)."""
    p = "youtube"
    dp = kq.get("du_phong_kq") or {}
    dp_cat = bool(dp.get("n_raw")) and (dp["n_raw"] >= 0.95 * dp["per"] * len(dp["urls"])
                                        or dp.get("ma") == "OK_MOT_PHAN")
    for u in kq["lo"]:
        n = sum(1 for c in kq["binh_luan"] if c["bai"] == u)
        if u in kq.get("loi_bai", {}):
            st, ly_do = kq["loi_bai"][u]
            per_url[u] = {"platform": p, "status": st, "error": ly_do, "comments": 0}
        elif u in kq.get("chua_chay", []):
            per_url[u] = {"platform": p, "status": _CHUA_CHAY_GIO, "comments": 0}
        elif u in kq.get("mot_phan", []):
            per_url[u] = {"platform": p, "status": _CHUA_XONG_GIU, "ma": "OK_MOT_PHAN",
                          "comments": n, "nguon": _YT_API_NGUON,
                          "ghi_chu": "hết thời gian — chỉ là phần lấy được tới lúc đó"}
        elif u in dp.get("urls", []):
            if dp.get("loi"):
                per_url[u] = {"platform": p, "status": "LỖI", "error": dp["loi"]}
                if p not in failed:
                    failed.append(p)
                continue
            per_url[u] = {"platform": p, "status": _CAT if (n == 0 and dp_cat) else "OK",
                          "comments": n,
                          "nguon": (f"DỰ PHÒNG {dp['actor']} — YouTube Data API không dùng "
                                    f"được: {dp.get('ly_do', '')}")[:300]}
        else:
            per_url[u] = {"platform": p, "status": "OK", "comments": n, "nguon": _YT_API_NGUON}


_FETCH = {"tiktok": _fetch_tiktok, "youtube": _fetch_youtube, "facebook": _fetch_facebook,
          "threads": _fetch_threads, "instagram": _fetch_instagram}
_MAP = {"tiktok": _map_tiktok, "youtube": _map_youtube, "facebook": _map_facebook,
        "threads": _map_threads, "instagram": _map_instagram}
_MAP_DU_PHONG = {"threads": _map_threads_du_phong, "instagram": _map_instagram_du_phong}


# ───────────────────────── chia lô theo trần ─────────────────────────
def _suc_chua(p: str, tran_usd: float) -> int:
    """Số bình luận tối đa MỘT lượt chạy (một bài) mà vẫn nằm dưới `_BIEN` × trần."""
    if _mien_phi(p):
        return _MAX_PER_POST * _YT_BAI_MOI_LO
    return max(1, int((_BIEN * _tran_p(p, tran_usd) - _GIA_KHOI_DONG.get(p, 0.0)
                       - _GIA_MOI_BAI.get(p, 0.0)) / _GIA[p]))


def _chia_lo(p: str, us: list[str], per: int,
             tran_usd: float) -> tuple[int, list[list[str]]]:
    """(số bình luận/bài thực dùng, các lô link) sao cho mỗi lượt nằm gọn trong trần.

    Chia ĐỀU số bài giữa các lô (8 bài -> 4 + 4, không 7 + 1): mỗi lô phải giữ ít nhất
    mức trần tối thiểu `_san` (0,1 USD; YouTube/Facebook 0,5), lô vụn cuối cũng tốn
    nguyên mức đó trong trần cứng của lượt. Threads: số bình luận/bài trong 10–300 (actor
    chỉ nhận vậy), tối đa 20 bài mỗi lượt, mỗi bài tốn thêm dòng bài gốc."""
    suc = _suc_chua(p, tran_usd)
    duoi, tren = _PER_KHOANG.get(p, (1, _MAX_PER_POST))
    per_thuc = max(duoi, min(per, suc, tren))
    moi_bai = _GIA_MOI_BAI.get(p, 0.0)
    if moi_bai:
        ngan = _BIEN * _tran_p(p, tran_usd) - _GIA_KHOI_DONG.get(p, 0.0)
        co = max(1, int(ngan / (per_thuc * _GIA[p] + moi_bai)))
    else:
        co = max(1, suc // per_thuc)
    co = min(co, _YT_BAI_MOI_LO if _mien_phi(p) else _BAI_MOI_LO.get(p, co))
    so_lo = max(1, math.ceil(len(us) / co))
    co = max(1, math.ceil(len(us) / so_lo))
    return per_thuc, [us[i:i + co] for i in range(0, len(us), co)]


def _uoc_tinh(ke_hoach: dict) -> tuple[int, float]:
    """(tổng bình luận tối đa, USD) của kế hoạch {p: (per, lô)}."""
    bl = usd = 0.0
    for p, (per, cac_lo) in ke_hoach.items():
        bl += sum(len(lo) for lo in cac_lo) * per
        usd += sum(_uoc_lo(p, lo, per) for lo in cac_lo)
    return int(bl), round(usd, 4)


def _uoc_lo(p: str, lo: list[str], per: int) -> float:
    if _mien_phi(p):
        return 0.0
    return (len(lo) * (per * _GIA[p] + _GIA_MOI_BAI.get(p, 0.0))
            + _GIA_KHOI_DONG.get(p, 0.0))


def _san(p: str) -> float:
    """maxTotalChargeUsd thấp nhất một lô được gửi: mức actor đòi, và 0,1 của `_call`.
    Lô YouTube Data API không gửi Apify gì: 0."""
    if _mien_phi(p):
        return 0.0
    return max(_MIN_CHARGE.get(p, 0.0), _TRAN_USD[1])


def _can_lo(p: str, uoc: float) -> float:
    """Phần trần một lô CẦN giữ để được khởi chạy: max(sàn, ước tính làm tròn xuống cent)."""
    return max(_san(p), math.floor(uoc * 100 + 1e-9) / 100)


def _can_giu(ke_hoach: dict) -> float:
    """Tổng phần trần các lô cần giữ — phải ≤ `tran_usd_goi` thì mọi lô mới chạy được."""
    return round(sum(_can_lo(p, _uoc_lo(p, lo, per))
                     for p, (per, cac_lo) in ke_hoach.items() for lo in cac_lo), 4)


def _tran_lo(p: str, uoc: float, tran_usd: float) -> float:
    """maxTotalChargeUsd TỐI ĐA của MỘT lô: ước tính × 1,5, làm tròn LÊN tới cent (kẻo
    `_call` làm tròn xuống dưới ước tính), không thấp hơn mức actor đòi, không quá trần
    tool. Trần thật gửi đi còn bị `_SoNganSach.xin` cắt theo phần trần còn lại."""
    if _mien_phi(p):
        return 0.0
    return min(_tran_p(p, tran_usd),
               max(_san(p), math.ceil(uoc * _HE_SO_TRAN_LO * 100 - 1e-9) / 100))


class _SoNganSach:
    """Sổ tiền của MỘT lượt gọi tool, dùng chung giữa các lô chạy song song.

    Bất biến (review 02/10/2026): tiền đã tiêu + trần Apify của các lô đang chạy + phần
    cần giữ của các lô chưa khởi chạy ≤ `tran`. Bản trước chỉ giữ chỗ theo ước tính trong
    khi mỗi lô được gửi maxTotalChargeUsd tới ước tính × 1,5 — ba lô song song có thể tiêu
    tới ~1,5 × trần nếu giá actor lệch. Nay trần gửi Apify CHÍNH LÀ phần giữ chỗ, nên tổng
    tiền có thể bị tính không bao giờ vượt `tran`."""

    def __init__(self, tran: float, can_cho: float = 0.0):
        self.tran, self.da, self.giu = tran, 0.0, 0.0
        self.cho = can_cho            # phần cần giữ của các lô CHƯA khởi chạy
        self.dung = False
        self._khoa = threading.Lock()

    def bo(self, can: float) -> None:
        """Lô không khởi chạy (vd hết giờ): trả phần nó đang được để dành."""
        with self._khoa:
            self.cho = max(0.0, self.cho - can)

    def xin(self, can: float, tran_lo: float, *, ngoai_ke_hoach: bool = False) -> float:
        """Trần Apify (USD, làm tròn xuống cent) cấp cho một lô, 0 nếu không được chạy.
        = min(`tran_lo`, phần còn lại sau khi để dành cho các lô chưa chạy); dưới `can`
        thì không chạy. Từ chối một lần là dừng hẳn: giá đang lệch, lô nhỏ phía sau có lọt
        qua cũng chỉ làm kết quả lỗ chỗ.

        `ngoai_ke_hoach`: lượt KHÔNG được để dành từ đầu (dự phòng của lô YouTube Data API
        miễn phí) — không trừ phần để dành của lô khác, bị từ chối cũng không dừng sổ."""
        with self._khoa:
            if not ngoai_ke_hoach:
                self.cho = max(0.0, self.cho - can)
            if self.dung:
                return 0.0
            con = self.tran - self.da - self.giu - self.cho
            cap = math.floor(min(tran_lo, con) * 100 + 1e-9) / 100
            if cap + 1e-9 < can or cap <= 0:
                if not ngoai_ke_hoach:
                    self.dung = True
                return 0.0
            self.giu += cap
            return cap

    def tra(self, giu: float, thuc: float) -> None:
        with self._khoa:
            self.giu -= giu
            self.da += thuc


def _da_tieu(metas: list, mac_dinh: float) -> float:
    """Tiền các run trong `metas` đã tiêu (như `tiktok_ads_tool._da_tieu`): run chưa hề
    được tạo = 0; số Apify báo nếu có; không thì hỏi lại theo run id; vẫn không đọc được
    thì coi như đã tiêu `mac_dinh` (ước tính) — thà để dự phòng ít trần hơn là vượt trần."""
    tong = 0.0
    for m in metas:
        if not isinstance(m, dict) or not m.get("run_id"):
            continue
        u = m.get("usd")
        if u is None:
            cp = A._chi_phi_cac_run([m["run_id"]]) or {}
            u = cp.get("usd") if cp.get("so_run") else None
        try:
            tong += max(0.0, float(u)) if u is not None else mac_dinh
        except (TypeError, ValueError):
            tong += mac_dinh
    return tong


def _tran_du_phong(p: str, tran_lo: float, da_tieu: float, n_bai: int,
                   per: int) -> tuple[float, int]:
    """(trần USD, bình luận/bài) cho lượt dự phòng = PHẦN CÒN LẠI của trần lô sau nguồn
    chính — cùng cách `tiktok_ads_tool._tran_du_phong` (review PR #6): tiền nguồn chính +
    trần dự phòng ≤ trần lô, nên cả lượt gọi tool vẫn ≤ `tran_usd_goi`. Làm tròn XUỐNG tới
    cent; dưới sàn 0,1 USD của `_call` (dưới đó nó tự nâng) hoặc không đủ khởi động + một
    bình luận mỗi bài thì (0, 0) = không chạy."""
    con = math.floor(max(0.0, tran_lo - da_tieu) * 100) / 100
    kd, moi_bl, moi_bai = _GIA_DU_PHONG[p]
    if con < max(A._TRAN_USD_KHOANG[0], kd + n_bai * (moi_bai + moi_bl)):
        return 0.0, 0
    per_dp = min(per, int((_BIEN * con - kd - n_bai * moi_bai) / (moi_bl * n_bai)))
    return (con, per_dp) if per_dp >= 1 else (0.0, 0)


def _chay_du_phong(kq: dict, p: str, lo: list[str], per: int, cap: float, so: list,
                   han_run: float, tien: list, uoc: float) -> None:
    """Nguồn chính của lô hỏng (không phải hết giờ/hết tiền tháng): chạy nguồn dự phòng
    trong phần trần lô còn lại. Ghi đè `kq` khi dự phòng lấy được bình luận."""
    loi_chinh = kq["loi"]
    actor = _ACTORS_DU_PHONG[p]
    da_tieu = _da_tieu(so, uoc)
    tien[0] = max(tien[0], da_tieu)
    tran_dp, per_dp = _tran_du_phong(p, cap, da_tieu, len(lo), per)
    if han_run - time.monotonic() < _GIAY_TOI_THIEU_LO:
        kq["loi"] = f"{loi_chinh} | dự phòng {actor} không chạy: hết thời gian của lượt"
        return
    if not per_dp:
        kq["loi"] = (f"{loi_chinh} | dự phòng {actor} không chạy: nguồn chính đã tiêu "
                     f"~{_usd(da_tieu)} USD, phần còn lại của trần lượt ({_usd(cap)} USD) "
                     f"không đủ")
        return
    kq["actors"].append(actor)
    truoc = len(so)
    try:
        raw = _call(actor, _payload_du_phong(p, lo, per_dp), per_dp * len(lo),
                    tran_usd=tran_dp)
        bl, n = _MAP_DU_PHONG[p](raw)
    except Exception as e:  # noqa: BLE001
        # Không biết dự phòng tiêu bao nhiêu thì tính nguyên trần của nó vào sổ.
        tien[0] = da_tieu + _da_tieu(so[truoc:], tran_dp)
        if getattr(e, "ma", "") == "QUA_GIO":
            kq["loi"], kq["loi_nguon_chinh"] = "", loi_chinh
            kq["trang_thai"] = ("CHƯA XONG — nguồn chính hỏng, nguồn dự phòng hết thời "
                                "gian, chưa lấy được bình luận")
        else:
            kq["loi"] = (f"{loi_chinh} | dự phòng {actor}: "
                         + _che_token(f"{type(e).__name__}: {e}"))[:400]
        return
    kd, moi_bl, moi_bai = _GIA_DU_PHONG[p]
    tien[0] = da_tieu + kd + len(lo) * moi_bai + n * moi_bl
    kq.update(binh_luan=bl, n_raw=n, loi="", per=per_dp, nguon="dự phòng",
              du_phong=actor, loi_nguon_chinh=loi_chinh)


def _keo_lo(p: str, lo: list[str], per: int, can: float, tran_lo: float,
            so_ns: _SoNganSach, han_run: float) -> dict:
    """Kéo MỘT lô — chạy trong `contextvars.copy_context()` của riêng nó.

    Đặt `_SO_RUN`/`_HAN_CHOT` của apify_tool (đợt 2) cho lô: tới hạn thì `_run_actor` HUỶ
    run trên Apify và trả phần đã lấy (`mot_phan`), thay vì ném QUA_GIO làm mất trắng
    cả lô như khi submit thẳng `_FETCH[p]` (rà 01/10/2026: không luồng nào đặt hai biến
    này, nên lô quá giờ không bao giờ được giữ phần dở). Trần Apify của lô do sổ cấp
    ngay lúc khởi chạy (`_SoNganSach.xin`)."""
    kq = {"p": p, "lo": lo, "per": per, "binh_luan": [], "n_raw": 0, "loi": "",
          "trang_thai": "OK", "ma": "OK", "tran_lo": 0.0}
    if han_run - time.monotonic() < _GIAY_TOI_THIEU_LO:
        so_ns.bo(can)
        kq["trang_thai"] = _CHUA_CHAY_GIO
        return kq
    if _mien_phi(p):
        return _keo_lo_yt_api(kq, lo, per, so_ns, han_run, so_ns.tran)
    cap = so_ns.xin(can, tran_lo)
    if not cap:
        kq["trang_thai"] = _CHUA_CHAY_NS
        return kq
    kq["tran_lo"] = cap
    kq["actors"] = [_ACTORS[p]]
    so: list = []
    A._SO_RUN.set(so)
    A._HAN_CHOT.set(han_run)
    loi_chinh = None
    tien = [0.0]                  # tiền đã chắc chắn tiêu (giá × item, hoặc đo thật)
    try:
        try:
            kq["binh_luan"], kq["n_raw"] = _FETCH[p](lo, per, cap)
            if kq["n_raw"]:
                # Apify ghi tiền chậm vài giây: lấy số lớn hơn giữa tiền run báo và giá × item.
                tien[0] = kq["n_raw"] * _GIA[p] + _GIA_KHOI_DONG.get(p, 0.0)
        except A.LoiApify as e:
            loi_chinh = e
            if e.ma == "QUA_GIO":
                kq["trang_thai"] = ("CHƯA XONG — hết thời gian, đã dừng run, chưa lấy được "
                                    "bình luận")
            else:
                kq["loi"] = _che_token(f"{type(e).__name__}: {e}")[:220]
        except Exception as e:  # noqa: BLE001
            loi_chinh = e
            # Che token: chuỗi lỗi đi thẳng vào câu trả lời của model và sổ audit.
            kq["loi"] = _che_token(f"{type(e).__name__}: {e}")[:220]
        if kq["loi"] and p in _ACTORS_DU_PHONG \
                and getattr(loi_chinh, "ma", "LOI") not in _KHONG_DU_PHONG:
            _chay_du_phong(kq, p, lo, per, cap, so, han_run, tien, _uoc_lo(p, lo, per))
    finally:
        usd = sum(float(m.get("usd") or 0) for m in so if isinstance(m, dict))
        kq["tien"] = max(usd, tien[0])
        so_ns.tra(cap, kq["tien"])
    ma = {m.get("ma") for m in so if isinstance(m, dict)}
    if "QUA_GIO" in ma and kq["binh_luan"]:
        kq["ma"], kq["trang_thai"] = "OK_MOT_PHAN", _CHUA_XONG_GIU
    elif "OK_MOT_PHAN" in ma:        # run FAILED/ABORTED giữa chừng (vd chạm trần lô)
        kq["ma"] = "OK_MOT_PHAN"
    return kq


def _ly_do_vuot(ke_hoach: dict, tran_bl: int, tran_usd: float) -> list[str]:
    """Trần nào kế hoạch vượt ([] = trong trần): số bình luận, chi phí ước tính, và phần
    trần các lô cần giữ (mỗi lượt YouTube/Facebook đòi giữ tối thiểu 0,5 USD)."""
    bl, usd = _uoc_tinh(ke_hoach)
    can = _can_giu(ke_hoach)
    # Trần RIÊNG mỗi lượt của nền tảng (console) mà một lô vẫn vượt — vd Threads
    # buộc ≥10 trả lời/bài + 0,02 USD khởi động dưới trần riêng quá thấp.
    rieng = sorted({p for p, (per, cac_lo) in ke_hoach.items() for lo in cac_lo
                    if _can_lo(p, _uoc_lo(p, lo, per)) > _tran_lo(p, _uoc_lo(p, lo, per),
                                                                 tran_usd) + 1e-9})
    return (([f"bình luận {bl} > {tran_bl}"] if bl > tran_bl else [])
            + [f"một lượt {A._TEN_NGUON.get(p, p)} cần hơn trần {_usd(_tran_p(p, tran_usd))} "
               f"USD/lượt" + (" (trần riêng trên console Quét mạng xã hội)"
                              if _tran_p(p, tran_usd) < tran_usd else "") for p in rieng]
            + ([f"chi phí {_usd(usd)} > {_usd(tran_usd)} USD"] if usd > tran_usd + 1e-9 else [])
            + ([f"phần trần cần giữ cho {sum(len(c) for _, c in ke_hoach.values())} lượt "
                f"chạy {_usd(can)} > {_usd(tran_usd)} USD"]
               if usd <= tran_usd + 1e-9 and can > tran_usd + 1e-9 else []))


def _trong_tran(bai: list[tuple[str, str]], per: int, tran_bl: int, tran_usd: float) -> bool:
    """Kế hoạch (chia lô thật, kể cả phí khởi động và sàn trần mỗi lô) cho `bai` =
    [(nền tảng, link)] với `per` bình luận/bài có nằm trong trần không."""
    nhom: dict[str, list[str]] = {}
    for p, u in bai:
        nhom.setdefault(p, []).append(u)
    return not _ly_do_vuot({p: _chia_lo(p, us, per, tran_usd) for p, us in nhom.items()},
                           tran_bl, tran_usd)


def _lon_nhat(hi: int, duoc) -> int:
    """Số lớn nhất trong 1..hi mà `duoc(k)` đúng (đơn điệu), 0 nếu không có."""
    lo, kq = 1, 0
    while lo <= hi:
        giua = (lo + hi) // 2
        if duoc(giua):
            kq, lo = giua, giua + 1
        else:
            hi = giua - 1
    return kq


def _vua_tran(bai: list[tuple[str, str]], per: int, tran_bl: int, tran_usd: float) -> dict:
    """Mức VỪA trần, tính bằng đúng phép chia lô sẽ chạy: số bình luận/bài tối đa cho đủ
    mọi bài, và số bài đầu tiên chạy được nếu giữ nguyên `per`."""
    return {"max_comments_cho_du_bai": _lon_nhat(
                per, lambda k: _trong_tran(bai, k, tran_bl, tran_usd)),
            "so_bai_voi_max_comments_hien_tai": _lon_nhat(
                len(bai), lambda m: _trong_tran(bai[:m], per, tran_bl, tran_usd))}


# ───────────────────────── sheet ─────────────────────────
def _write(token: str, sheet_id: str, values: list[list]) -> None:
    values = A._bang_an_toan(values)          # bình luận người lạ viết: chặn chèn công thức
    col = chr(ord("A") + len(_HEADER) - 1)
    for i in range(0, len(values), 1000):
        ch = values[i:i + 1000]
        lark.call("POST", f"/open-apis/sheets/v2/spreadsheets/{token}/values_batch_update",
                  body={"valueRanges": [{"range": f"{sheet_id}!A{i+1}:{col}{i+len(ch)}",
                                         "values": ch}]})


def _dong_thong_ke(tk: dict) -> list[list]:
    """Bảng thống kê: tổng, theo nền tảng, theo bài, chủ đề. Mọi dòng đủ 5 cột."""
    def khoi(pham_vi: str, g: dict) -> list[list]:
        r = [[pham_vi, lab, v["so"], v["ti_le"] if v["ti_le"] is not None else "",
              v["ti_le_theo_like"] if v["ti_le_theo_like"] is not None else ""]
             for lab, v in g["sac_thai"].items()]
        if g["chua_phan_loai"]:
            r.append([pham_vi, "Chưa phân loại", g["chua_phan_loai"], "", ""])
        return r

    rows = [["Phạm vi", "Sắc thái / Chủ đề", "Số bình luận",
             "Tỉ lệ % (trên số đã phân loại)", "Tỉ lệ % theo lượt thích"],
            [f"TỔNG: đã phân loại {tk['da_phan_loai']}/{tk['tong']}", "", "", "", ""]]
    rows += khoi("Tổng", tk)
    for p, g in tk["theo_nen_tang"].items():
        rows += khoi(f"Nền tảng: {p}", g)
    for b, g in tk["theo_bai"].items():
        rows += khoi(f"Bài: {b}", g)
    rows += [["Chủ đề (tổng)", lab, v["so"], v["ti_le"], ""] for lab, v in tk["chu_de"].items()]
    return rows


def _ghi_thong_ke(tok: str, sid_chinh: str, so_dong_chinh: int, tk: dict) -> str:
    """Tab 'Thống kê' riêng; thêm tab hỏng thì ghi nối dưới sheet chính (không bỏ số)."""
    rows = _dong_thong_ke(tk)
    them_tab = getattr(A, "_them_tab", None)
    if them_tab:
        try:
            A._write_values(tok, them_tab(tok, _TAB_THONG_KE), rows)
            return f"tab '{_TAB_THONG_KE}'"
        except Exception as e:  # noqa: BLE001
            print(f"[social_deep_dive] thêm tab Thống kê hỏng, ghi dưới sheet chính: "
                  f"{_che_token(e)}")
    A._write_values(tok, sid_chinh, [[""] * 5, ["THỐNG KÊ", "", "", "", ""]] + rows,
                    dong_dau=so_dong_chinh + 1)
    return "cuối sheet chính (dưới dòng 'THỐNG KÊ')"


# ───────────────────────── tool ─────────────────────────
SCHEMA = {
    "name": "social_deep_dive",
    "description": (
        "Soi SÂU một hoặc nhiều bài cụ thể: kéo BÌNH LUẬN về, TỰ GÁN NHÃN từng bình luận "
        "(Sắc thái: Tích cực/Tiêu cực/Trung lập; Chủ đề: sản phẩm, giá/mua ở đâu, KOL/nội "
        "dung, giao hàng/dịch vụ, đối thủ, tag bạn bè, khác), thống kê, ghi vào Lark Sheet "
        "riêng (kèm tab 'Thống kê'), cấp quyền cho người hỏi và trả LINK SHEET. Dùng khi ai "
        "nhờ 'xem người ta bình luận gì về bài này', 'khách nói gì', 'sentiment ra sao', "
        "'gán nhãn từng bình luận và thống kê', hoặc cần đánh giá sức khoẻ thương hiệu / "
        "phát hiện khủng hoảng. Việc gán nhãn + thống kê là tool LÀM ĐƯỢC — đừng nói không.\n"
        "ĐẦU VÀO: `post_urls` — lấy từ cột `Link` trong sheet mà `social_listen` đã tạo, "
        "hoặc link người dùng dán vào.\n"
        "HỖ TRỢ: TikTok, YouTube, Facebook, Threads (threads.net/threads.com), Instagram. "
        "Link nền tảng khác (`chua_ho_tro`) phải NÓI THẲNG là chưa nối nguồn, TUYỆT ĐỐI không "
        "thay bằng nền tảng khác rồi để người dùng tưởng là của nền tảng họ hỏi.\n"
        "- Threads/Instagram bóc KHÔNG đăng nhập: không có trả lời lồng nhau, Instagram chỉ "
        "lấy được MỘT PHẦN bình luận công khai — luôn nói rõ theo `gioi_han_nen_tang`, không "
        "gọi là toàn bộ bình luận. `per_url[...].nguon` có 'DỰ PHÒNG' = nguồn chính hỏng, "
        "đã lấy bằng nguồn dự phòng (vẫn trong trần) — nói ra. 'ĐÃ TẮT' = chủ agent tắt nền "
        "tảng đó trên console.\n"
        "- YouTube lấy bằng YouTube Data API MIỄN PHÍ (0 USD, xem `youtube_api`: số đơn vị "
        "quota, số trả lời); cột 'Trả lời bình luận' = link bình luận gốc của dòng trả lời. "
        "API hỏng/hết quota thì tự chạy actor DỰ PHÒNG trong trần (`per_url[...].nguon`). '"
        + _TAT_BL + "' = chủ video tắt bình luận — nói đúng vậy, không phải lỗi nguồn.\n"
        "BẮT BUỘC KHI TRẢ LỜI:\n"
        "- TRẦN CỨNG: chủ agent đặt trần bình luận + trần USD cho MỖI lần gọi (`tran`); "
        "tổng tiền Apify có thể tính của cả lần gọi không bao giờ vượt trần USD (mỗi lượt "
        "Facebook và YouTube-dự-phòng phải giữ tối thiểu 0,5 USD trong trần đó). Trong trần "
        "người dùng "
        "xin bao nhiêu bình luận/bài cũng được (tới 1000). `vuot_tran`=true: tool CHƯA CHẠY, "
        "chưa tốn tiền — nói rõ trần nào bị vượt (`vuot`), chép câu `goi_y` (mức vừa trần), đề xuất giảm "
        "số bình luận/bài hoặc bớt bài, hoặc nhờ chủ agent nâng 'Trần bình luận' / 'Trần chi "
        "phí bóc bình luận' ở Console → Năng lực. Không có cách nào chạy vượt trần.\n"
        "- Đọc `per_url`. `status`='" + _CAT + "' nghĩa là lượt chạy chạm trần nên bài đó "
        "CHƯA lấy hết — nói rõ như vậy, TUYỆT ĐỐI không nói bài đó không có bình luận. Chỉ "
        "bài `status`='OK' với 0 comment mới là bài thật sự chưa có bình luận. 'CHƯA CHẠY'/"
        "'CHƯA XONG' = hết thời gian, nói rõ và đề xuất soi lại ít bài hơn. '"
        + _CHUA_XONG_GIU + "' = chỉ có PHẦN bình luận lấy được trước khi hết giờ, chưa đủ. '"
        + _CHUA_CHAY_NS + "' = dừng vì các lô trước đã tiêu gần hết ngân sách đã duyệt.\n"
        "- SỐ SENTIMENT CHỈ LẤY TỪ `thong_ke` / chép `dong_thong_ke`. Luôn nói đã phân loại "
        "`da_phan_loai`/`tong`. TUYỆT ĐỐI không tự ước lượng tỉ lệ, không làm tròn khác đi. "
        "Dẫn bình luận thật từ `trich_dan`. `phan_loai.trang_thai` khác 'đã chạy' thì nói "
        "rõ phần chưa phân loại.\n"
        "- Mặc định 50 comment/bài; đừng tự ý đẩy lên cao — người dùng xin số nào thì đặt "
        "đúng số đó vào `max_comments`.\n"
        "- YouTube lấy bằng nguồn DỰ PHÒNG trả thời gian dạng chữ tương đối ('2 years ago'), "
        "KHÔNG phải ngày "
        "tuyệt đối — đừng quy đổi thành ngày cụ thể.\n"
        "- Gửi NGUYÊN `sheet_url`. `granted`=false thì báo người dùng có thể mở không được.\n"
        "- Chi phí: chỉ nói khi được hỏi, đọc NGUYÊN VĂN `chi_phi`. NGOẠI LỆ: bóc LỚN thì "
        "PHẢI nói USD ước tính trước khi chạy.\n"
        "- BÓC LỚN (>1500 bình luận tổng, hoặc lượt chậm/đắt hơn một lượt trả lời): tool tự "
        "CHẠY NỀN rồi Mark tự nhắn kết quả. Gọi trước với `chi_uoc_tinh`=true (không chạy, "
        "không tốn tiền), báo USD + phút ước tính, KẾT THÚC bằng \"Chạy nhé?\". Kết quả "
        "`dang_chay_nen`=true: chưa có số liệu — chỉ nói mã việc, ước tính, sẽ báo qua đâu. "
        "Hỏi 'xong chưa' → `tra_viec_nen`; 'huỷ' → `huy_viec_nen`."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "post_urls": {"type": "array", "items": {"type": "string"},
                          "description": "Link bài cần soi (tối đa 50). Lấy từ cột Link của sheet social_listen."},
            "max_comments": {"type": "integer",
                             "description": ("Số bình luận tối đa MỖI bài (mặc định 50, tối "
                                             "đa 1000; tổng vẫn trong trần chủ agent đặt).")},
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
            "chi_uoc_tinh": {"type": "boolean", "description": (
                "true = CHỈ ước tính số bình luận/USD/phút, không chạy, không tốn tiền.")},
            "chay_nen": {"type": "boolean", "description": (
                "true = ép chạy nền (xong Mark tự nhắn). Bỏ trống = tool tự quyết theo cỡ.")},
        },
        "required": ["post_urls"],
    },
}


def _usd(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _handle(args: dict, **kwargs) -> str:
    # Chốt MỘT lần: YouTube đi API miễn phí hay actor (kế hoạch, sổ tiền, lô cùng thấy).
    tok = _YT_API.set(_yt_api_san_sang())
    try:
        return _xu_ly(args)
    finally:
        _YT_API.reset(tok)


def _xu_ly(args: dict) -> str:
    t0 = time.monotonic()
    urls = [str(u).strip() for u in (args.get("post_urls") or []) if str(u).strip()]
    if not urls:
        return tool_error("Thiếu `post_urls` (link bài cần soi).")
    if len(urls) > _MAX_POSTS:
        return tool_error(f"Tối đa {_MAX_POSTS} bài mỗi lần, bạn đưa {len(urls)}.")
    try:
        per_xin = int(args.get("max_comments") or 50)
    except (TypeError, ValueError):
        per_xin = 50
    per = max(1, min(per_xin, _MAX_PER_POST))
    tran_bl, tran_usd = _cau_hinh()

    nhom: dict[str, list[str]] = {}
    chua_ho_tro: dict[str, list[str]] = {}
    for u in urls:
        p = _platform_of(u)
        if p in _FETCH:
            nhom.setdefault(p, []).append(u)
        else:
            chua_ho_tro.setdefault(p or "không nhận ra", []).append(u)
    # Chủ agent TẮT nền tảng trên console (`bat_<p>`=0) thì cũng không bóc bình luận.
    tat = {p: nhom.pop(p) for p in [p for p in nhom if p in _THEO_CONSOLE_QUET]
           if not A._tran_nen_tang(p)[2]}
    cau_tat = "; ".join(A._ly_do_tat(p) for p in tat)

    if not nhom:
        if tat and not chua_ho_tro:
            return tool_error(
                f"Không chạy: {cau_tat} — bóc bình luận nền tảng đó cũng tắt. Nói rõ như "
                f"vậy; muốn bóc thì chủ agent bật lại ở Console → {A._NOI_CONSOLE}.")
        return tool_error(
            f"Không link nào thuộc nền tảng đã nối (TikTok, YouTube, Facebook, Threads, "
            f"Instagram). Chưa hỗ trợ: {', '.join(chua_ho_tro)}"
            + (f"; {cau_tat}" if tat else "")
            + ". Hãy NÓI THẲNG là chưa nối nguồn cho các link đó, đừng thay bằng nguồn khác.")

    per_url: dict[str, dict] = {}
    for p, us in tat.items():
        for u in us:
            per_url[u] = {"platform": p, "status": "ĐÃ TẮT",
                          "error": A._ly_do_tat(p) + " — không bóc bình luận."}
    failed: list[str] = []
    # Trần (của tool, hoặc trần riêng nền tảng trên console nếu chặt hơn) thấp hơn mức
    # actor đòi → từ chối rõ, không gọi Apify, không tự nâng.
    for p in list(nhom):
        tp = _tran_p(p, tran_usd)
        if not _mien_phi(p) and _MIN_CHARGE.get(p, 0) > tp:
            rieng = tp < tran_usd
            for u in nhom.pop(p):
                per_url[u] = {"platform": p, "status": "LỖI", "error": (
                    (f"Trần riêng {A._TEN_NGUON.get(p, p)} trên console Quét mạng xã hội "
                     if rieng else "Trần chi phí của social_deep_dive ")
                    + f"({_usd(tp)} USD/lượt) thấp hơn mức tối thiểu actor {p} yêu cầu "
                    f"({_usd(_MIN_CHARGE[p])} USD) — không chạy. Chủ agent nâng ô "
                    + (f"`tran_usd_{p}` ở Console → {A._NOI_CONSOLE}." if rieng else
                       "`tran_usd_goi` của social_deep_dive trên console."))}
            failed.append(p)

    ke_hoach = {p: _chia_lo(p, us, per, tran_usd) for p, us in nhom.items()}
    uoc_bl, est = _uoc_tinh(ke_hoach)
    cat_per = (f"Người dùng xin {per_xin} bình luận/bài, tối đa {_MAX_PER_POST} mỗi lần — "
               f"đã dùng {_MAX_PER_POST}. Nói rõ." if per_xin > _MAX_PER_POST else None)
    if "threads" in nhom and per != ke_hoach["threads"][0] \
            and ke_hoach["threads"][0] in _PER_KHOANG["threads"]:
        cat_per = ((cat_per + " ") if cat_per else "") + (
            f"Threads chỉ nhận {_PER_KHOANG['threads'][0]}–{_PER_KHOANG['threads'][1]} "
            f"trả lời/bài nên dùng {ke_hoach['threads'][0]}. Nói rõ.")
    # Bóc LỚN (chủ agent chốt 01–02/10/2026: tới 30.000 bình luận) thành việc NỀN — xét
    # TRƯỚC trần của lượt tại chỗ (5 USD), kẻo lượt lớn hợp lệ bị báo "vượt trần".
    tra_ngay, ghi_chu_nen = _thu_chay_nen(args, urls, nhom, per, cat_per, ke_hoach, per_url)
    if tra_ngay is not None:
        return tra_ngay
    # Trần chủ agent là trần CỨNG (chốt 01/10/2026): vượt thì không chạy, không có cờ bỏ
    # qua. Trước đây `xac_nhan_chi_phi`=true cho chạy vượt trần sau một câu "ok".
    vuot = _ly_do_vuot(ke_hoach, tran_bl, tran_usd) if nhom else []
    if vuot:
        return _tra_vuot(urls, nhom, per, cat_per, ke_hoach, tran_bl, tran_usd, vuot)

    # ── kéo bình luận: các lô chạy song song, không chờ quá hạn ──
    bat_dau = datetime.datetime.now(_VN_TZ) - datetime.timedelta(seconds=5)
    viec = [(p, lo, ke_hoach[p][0]) for p in ke_hoach for lo in ke_hoach[p][1]]
    lo_kq: list[dict] = []
    if viec:
        han = max(10.0, A._TOOL_DEADLINE - _DANH_CHO_SAU - (time.monotonic() - t0))
        han_keo = time.monotonic() + han
        # Run dừng TRƯỚC hạn chờ `_DU_PHONG_HUY` giây: đủ để huỷ run + lấy item dở dang.
        han_run = han_keo - A._DU_PHONG_HUY
        # Sổ để dành ngay từ đầu phần trần mọi lô cần (`_can_giu` ≤ trần, đã kiểm ở trên):
        # lô khởi chạy trước không được ăn mất chỗ của lô sau.
        so_ns = _SoNganSach(tran_usd, _can_giu(ke_hoach))
        ex = ThreadPoolExecutor(max_workers=min(_SONG_SONG, len(viec)))
        futs = {}
        for p, lo, pc in viec:
            uoc = _uoc_lo(p, lo, pc)
            futs[ex.submit(contextvars.copy_context().run, _keo_lo, p, lo, pc,
                           _can_lo(p, uoc), _tran_lo(p, uoc, tran_usd),
                           so_ns, han_run)] = (p, lo, pc)
        xong, chua = wait(futs, timeout=max(0.05, han_keo - time.monotonic()))
        dang_chay = {f for f in chua if f.running()}
        ex.shutdown(wait=False, cancel_futures=True)
        for f, (p, lo, pc) in futs.items():
            kq = {"p": p, "lo": lo, "per": pc, "binh_luan": [], "n_raw": 0, "loi": "",
                  "trang_thai": "OK", "ma": "OK",
                  **({"actors": []} if _mien_phi(p) else {})}
            if f in xong:
                try:
                    kq = f.result()
                except Exception as e:  # noqa: BLE001 — `_keo_lo` tự bắt; phòng hờ
                    kq["loi"] = _che_token(f"{type(e).__name__}: {e}")[:220]
            else:
                kq["trang_thai"] = ("CHƯA XONG — hết thời gian chờ (run tự bị huỷ khi tới "
                                    "hạn)" if f in dang_chay else _CHUA_CHAY_GIO)
            lo_kq.append(kq)

    rows: list[dict] = []
    khong_quy = 0
    for kq in lo_kq:
        for c in kq["binh_luan"]:
            c["platform"] = kq["p"]
            c["bai"] = _quy_ve_bai(c.pop("_nguon", []) + [c.get("link") or ""], kq["lo"])
            khong_quy += not c["bai"]
            rows.append(c)

    # ── chi phí thật (hỏi song song với gán nhãn: Apify ghi tiền chậm vài giây) ──
    da_chay = [kq for kq in lo_kq if not kq["trang_thai"].startswith("CHƯA CHẠY")]
    # Lô YouTube Data API (`actors`=[]) KHÔNG phải lượt Apify: không hỏi/ghi chi phí Apify.
    actors = sorted({a for kq in da_chay for a in kq.get("actors", [_ACTORS[kq["p"]]])})
    dv_yt = sum(int(kq.get("dv") or 0) for kq in lo_kq)
    lo_yt = [kq for kq in lo_kq if kq.get("yt_api")]
    ex_cp = ThreadPoolExecutor(max_workers=1)
    f_cp = ex_cp.submit(A._chi_phi_thuc, actors, bat_dau, est) if actors else None

    tt_pl: dict = {}
    if rows:
        han_pl = min(_PHAN_LOAI_TOI_DA, A._TOOL_DEADLINE - (time.monotonic() - t0) - 12)
        nhan = phan_loai.phan_loai_binh_luan(rows, han_pl, tt_pl)
        for c, (s, cd) in zip(rows, nhan):
            c["sac_thai"], c["chu_de"] = s, cd

    thuc = None
    if f_cp:
        try:
            thuc = f_cp.result(timeout=max(3.0, A._TOOL_DEADLINE - (time.monotonic() - t0) - 8))
        except Exception:  # noqa: BLE001 — không có số thật thì nói là ước tính
            thuc = None
    ex_cp.shutdown(wait=False)
    if thuc and thuc.get("cham_tran") and tran_usd > A._tran()[1]:
        # `_chi_phi_thuc` so mỗi lượt với trần của social_listen (vd 0,37), mà lô ở đây được
        # phép tới 90% trần RIÊNG (vd 0,45 của 0,5) — cờ đó báo nhầm. Dựa vào đếm từng lô.
        thuc = {**thuc, "cham_tran": 0}
    # Apify ghi tiền CHẬM: đo 04/10 lượt Threads xong vẫn chỉ báo 0,02 USD (phí khởi động)
    # sau hai lần hỏi lại, thật là 0,07 (khởi động + 20 dòng × 0,0025). Số dòng actor đã
    # tính phí là sàn chắc chắn — số Apify báo thấp hơn sàn thì dùng sàn, và nói rõ.
    san = round(sum(float(kq.get("tien") or 0) for kq in lo_kq), 3)
    theo_dem = bool(thuc and thuc.get("so_run") and thuc.get("usd", 0) < san - 1e-9)
    if theo_dem:
        thuc = {**thuc, "usd": san}
    if actors:
        chi_phi_tool.ghi(queries=[f"bình luận {len(urls)} bài"], platforms=list(ke_hoach),
                         date_range="", thuc=thuc, est=est)
    cham_tran_thuc = bool(thuc and thuc.get("cham_tran"))

    # ── trạng thái từng bài ──
    for kq in lo_kq:
        p, lo = kq["p"], kq["lo"]
        if kq.get("yt_api"):
            _trang_thai_yt(kq, per_url, failed)
            continue
        # Lượt trả gần đủ maxItems = các bài đầu đã ăn hết hạn mức, bài rỗng phía sau có
        # thể chỉ là bị cắt (đúng ca 01/10: 13/25 bài hiện 0).
        # Run dừng giữa chừng phía Apify (FAILED/ABORTED, vd chạm trần lô) cũng là bị cắt.
        cat = bool(kq["n_raw"]) and (kq["n_raw"] >= 0.95 * kq["per"] * len(lo)
                                     or cham_tran_thuc or kq.get("ma") == "OK_MOT_PHAN")
        for u in lo:
            if kq["loi"]:
                per_url[u] = {"platform": p, "status": "LỖI", "error": kq["loi"]}
                continue
            n = sum(1 for c in kq["binh_luan"] if c["bai"] == u)
            if kq["trang_thai"] == _CHUA_XONG_GIU:
                per_url[u] = {"platform": p, "status": _CHUA_XONG_GIU, "ma": "OK_MOT_PHAN",
                              "comments": n,
                              "ghi_chu": "hết thời gian, run đã dừng — chỉ là phần lấy được "
                                         "tới lúc đó, CHƯA đủ bình luận của bài"}
                continue
            if kq["trang_thai"] != "OK":
                per_url[u] = {"platform": p, "status": kq["trang_thai"], "comments": 0}
                continue
            if n == 0 and cat:
                per_url[u] = {"platform": p, "status": _CAT, "comments": 0,
                              "ghi_chu": "lượt chạy chạm trần nên bài này chưa được lấy — "
                                         "KHÔNG phải bài không có bình luận"}
            else:
                per_url[u] = {"platform": p, "status": "OK", "comments": n}
        if kq["loi"] and p not in failed:
            failed.append(p)
        if kq.get("du_phong"):
            for u in lo:
                per_url[u]["nguon"] = (f"DỰ PHÒNG {kq['du_phong']} — nguồn chính hỏng: "
                                       f"{kq.get('loi_nguon_chinh', '')}")[:300]
    du_phong = sorted({kq["p"] for kq in lo_kq if kq.get("du_phong")
                       or (kq.get("du_phong_kq") and not kq["du_phong_kq"].get("loi"))})
    yt_api = None
    if lo_yt:
        yt_api = {"nguon": _YT_API_NGUON, "chi_phi_usd": 0,
                  "don_vi_quota": dv_yt, "quota_mien_phi_ngay": _YT_QUOTA_NGAY,
                  # dòng lấy bằng API (gốc + trả lời); dòng của actor dự phòng không có "cha"
                  "so_dong": sum(1 for kq in lo_yt for c in kq["binh_luan"] if "cha" in c),
                  "tra_loi": sum(1 for kq in lo_yt for c in kq["binh_luan"] if c.get("cha")),
                  "video_tat_binh_luan": [u for kq in lo_yt
                                          for u, (st, _) in kq.get("loi_bai", {}).items()
                                          if st == _TAT_BL] or None}
    gioi_han = {p: _GIOI_HAN[p] for p in ke_hoach if p in _GIOI_HAN}
    for p, us in chua_ho_tro.items():
        for u in us:
            per_url[u] = {"platform": p, "status": "CHƯA HỖ TRỢ",
                          "error": f"Chưa nối nguồn bình luận cho {p}. Phải nói thẳng."}
    so_tat_bl = sum(1 for v in per_url.values() if v["status"] == _TAT_BL)
    so_cat = sum(1 for v in per_url.values() if v["status"] == _CAT)
    so_ns_cham = sum(1 for v in per_url.values() if v["status"] == _CHUA_CHAY_NS)
    so_chua = sum(1 for v in per_url.values() if v["status"].startswith("CHƯA X")
                  or v["status"] == _CHUA_CHAY_GIO)

    base = dict(so_bai=len(urls), max_comments=per, max_comments_bi_cat=cat_per,
                quet_nen_ghi_chu=ghi_chu_nen or None,
                tran={"tran_binh_luan": tran_bl, "tran_usd_goi": tran_usd},
                max_comments_thuc={p: k[0] for p, k in ke_hoach.items()},
                per_url={u: per_url[u] for u in urls if u in per_url},
                platforms_failed=failed, chua_ho_tro=list(chua_ho_tro),
                nen_tang_da_tat=list(tat) or None, gioi_han_nen_tang=gioi_han or None,
                dung_nguon_du_phong=du_phong or None, youtube_api=yt_api,
                tong_comment=len(rows), khong_quy_ve_bai=khong_quy,
                so_luot_chay=len(da_chay), so_bai_co_the_bi_cat=so_cat,
                so_bai_cham_ngan_sach=so_ns_cham,
                uoc_tinh_chi_phi_usd=est,
                chi_phi_thuc_usd=thuc["usd"] if thuc and thuc.get("so_run") else None,
                cham_tran_chi_phi=cham_tran_thuc or bool(so_cat),
                chi_phi=(f"Chi phí lượt quét: {_usd(thuc['usd'])} USD ({thuc['so_run']} lượt "
                         f"chạy; Apify chưa ghi xong tiền nên tính theo số dòng actor đã tính "
                         f"phí)." if theo_dem else A._dong_chi_phi(thuc, est)
                         if actors else "Chi phí lượt quét: 0 USD (không chạy lượt Apify nào)."
                         ) + (f" YouTube lấy bằng {_YT_API_NGUON}: 0 USD, dùng {dv_yt} đơn vị "
                              f"quota (miễn phí {_YT_QUOTA_NGAY}/ngày)." if lo_yt else ""))
    canh_bao = ((f" {so_cat} bài {_CAT} — nói rõ, đừng gọi là 0 bình luận." if so_cat else "")
                + (f" {so_chua} bài chưa kéo xong vì hết thời gian." if so_chua else "")
                + (f" {so_ns_cham} bài {_CHUA_CHAY_NS}: các lô trước đã tiêu gần hết ngân "
                   f"sách đã duyệt — nói rõ, đề xuất soi riêng các bài đó." if so_ns_cham else "")
                + (f" CẢNH BÁO: nguồn HỎNG: {', '.join(failed)}." if failed else "")
                + (f" CHƯA HỖ TRỢ: {', '.join(chua_ho_tro)} — phải nói rõ."
                   if chua_ho_tro else "")
                + (f" ĐÃ TẮT: {cau_tat} — nói rõ các bài đó không được bóc." if tat else "")
                + (f" {so_tat_bl} video {_TAT_BL} — nói rõ là video tắt bình luận, không "
                   f"phải lỗi nguồn." if so_tat_bl else "")
                + (f" {', '.join(A._TEN_NGUON.get(p, p) for p in du_phong)}: nguồn chính hỏng, "
                   f"đã lấy bằng nguồn DỰ PHÒNG (xem `per_url[...].nguon`) — nói rõ."
                   if du_phong else "")
                + (" GIỚI HẠN PHẢI NÓI RA: " + " ".join(gioi_han.values()) if gioi_han else ""))

    if not rows:
        return tool_result(
            success=not failed and not so_cat and not so_chua and not so_ns_cham,
            sheet_url=None, **base,
            note=("Không lấy được bình luận nào. Chỉ bài `status`='OK' với 0 comment mới là "
                  "bài chưa có bình luận — nói đúng từng bài theo `per_url`. Không tạo sheet."
                  + canh_bao))

    tk = phan_loai.dem(rows, "bai")
    dong_tk = phan_loai.dong_thong_ke(tk)
    title = (args.get("title") or "").strip() or \
        f"Bình luận · {len(urls)} bài · {datetime.datetime.now(_VN_TZ):%d-%m %H%M}"
    values = [list(_HEADER)] + [[
        c["platform"], c["kenh"], c["text"], c.get("sac_thai", phan_loai.CHUA),
        c.get("chu_de", phan_loai.CHUA), c["likes"], c["replies"], c["thoi_gian"],
        c["tac_gia_thich"], c["bai"] or c["link"], c.get("cha") or "",
    ] for c in rows]
    pl = {"trang_thai": tt_pl.get("trang_thai", ""), "da_phan_loai": tk["da_phan_loai"],
          "tong": tk["tong"], "ghi_chu": tt_pl.get("ghi_chu", "")}

    try:
        tok, url = _create_sheet(title)
        sid = _first_sheet_id(tok)
        _write(tok, sid, values)
    except Exception as e:  # noqa: BLE001
        return tool_result(
            success=False, sheet_url=None, **base, thong_ke=tk, dong_thong_ke=dong_tk,
            phan_loai=pl, trich_dan=phan_loai.trich_dan(rows),
            error=_che_token(f"Lấy được {len(rows)} comment nhưng TẠO/GHI SHEET THẤT "
                             f"BẠI: {type(e).__name__}: {e}"))
    try:
        thong_ke_o = _ghi_thong_ke(tok, sid, len(values), tk)
    except Exception as e:  # noqa: BLE001 — sheet chính đã ghi xong, chỉ thiếu bảng đếm
        thong_ke_o = f"KHÔNG ghi được ({_che_token(type(e).__name__)})"

    sender = memory_store.get_current_sender()
    granted = _grant(tok, sender) if sender else False

    return tool_result(
        success=True, title=title, sheet_url=url, granted=granted, **base,
        thong_ke=tk, dong_thong_ke=dong_tk, phan_loai=pl, thong_ke_ghi_o=thong_ke_o,
        trich_dan=phan_loai.trich_dan(rows),
        note=(f"Đã ghi ĐỦ {len(rows)} bình luận (kèm cột Sắc thái, Chủ đề) vào sheet "
              f"'{title}'; thống kê ở {thong_ke_o}. GỬI `sheet_url`. Số sentiment CHỈ lấy "
              f"từ `thong_ke`/`dong_thong_ke`, nói rõ đã phân loại {tk['da_phan_loai']}/"
              f"{tk['tong']}; dẫn lời thật từ `trich_dan`."
              + canh_bao
              + ("" if granted else " CẢNH BÁO: chưa cấp được quyền tự động.")),
    )


def _tra_vuot(urls, nhom, per, cat_per, ke_hoach, tran_bl, tran_usd, vuot) -> str:
    uoc_bl, est = _uoc_tinh(ke_hoach)
    bai = [(_platform_of(u), u) for u in urls if _platform_of(u) in nhom]
    vua = _vua_tran(bai, per, tran_bl, tran_usd)
    n, k, m = len(bai), vua["max_comments_cho_du_bai"], vua["so_bai_voi_max_comments_hien_tai"]
    goi_y = ((f"Trong trần này bóc được tối đa {k} bình luận/bài cho {n} bài" if k else
              f"Trần này không đủ cho {n} bài, kể cả 1 bình luận/bài")
             + (f", hoặc {m} bài nếu giữ {per} bình luận/bài" if 0 < m < n else "") + ".")
    return tool_result(
        success=False, vuot_tran=True, chua_chay=True, so_bai=len(urls),
        max_comments=per, max_comments_bi_cat=cat_per,
        uoc_tinh_binh_luan=uoc_bl, uoc_tinh_chi_phi_usd=est,
        tran={"tran_binh_luan": tran_bl, "tran_usd_goi": tran_usd}, vuot=vuot,
        vua_tran=vua, goi_y=goi_y,
        note=(f"CHƯA CHẠY, chưa tốn tiền: yêu cầu vượt trần chủ agent đặt cho mỗi lần "
              f"bóc bình luận ({'; '.join(vuot)}). {goi_y} Nói đúng như vậy, đề xuất "
              f"giảm số bình luận/bài hoặc bớt bài; muốn chạy đủ thì nhờ chủ agent nâng "
              f"'Trần bình luận' / 'Trần chi phí bóc bình luận' ở Console → Năng lực. "
              f"Không có cách nào chạy vượt trần từ phía bạn."))


# ───────────────────────── chạy NỀN (viec_nen) ─────────────────────────
def _giay_lo(p: str, lo: list[str], pc: int) -> float:
    import quet_lon
    if _mien_phi(p):
        return 1.0 + pc * len(lo) / _YT_TOC
    return quet_lon._GIAY_KHOI_DONG + pc * len(lo) / quet_lon.toc(_ACTORS[p])


def _giay_ke(ke: dict, song_song: int = _SONG_SONG) -> float:
    """Giây ước tính chạy hết các lô của kế hoạch (`song_song` lô một lúc)."""
    import quet_lon
    tong = dai = 0.0
    for p, (pc, cac_lo) in ke.items():
        for lo in cac_lo:
            g = _giay_lo(p, lo, pc)
            tong += g
            dai = max(dai, g)
    return round(max(dai, tong / max(1, song_song)), 1)


def _ke_hoach_nen(ke: dict, tran_usd: float) -> dict:
    """Kế hoạch lô -> `nen_tang` của sổ việc (mỗi lô là một lượt con)."""
    import quet_lon
    nt: dict = {}
    for p, (pc, cac_lo) in ke.items():
        ds = []
        for i, lo in enumerate(cac_lo):
            if _mien_phi(p):
                # Lượt con YouTube Data API: quet_lon._mot_phan chuyển cho `mot_phan_yt_api`;
                # không giữ tiền trong sổ việc (API hỏng mới xin phần còn lại cho dự phòng).
                pl = {"video": list(lo), "per": pc}
                ds.append({"id": f"{p}-{i}", "actor": _ACTORS[p], "kieu": KIEU_YT_API,
                           "lo": list(lo), "per": pc, "payload": pl,
                           "payload_sha": quet_lon._sha(pl), "limit": pc * len(lo),
                           "uoc_usd": 0.0, "uoc_giay": round(_giay_lo(p, lo, pc), 1),
                           "can": 0.0, "tran_lo": 0.0, "min_charge": 0.0, "gia": 0.0,
                           "tran_usd_goi": round(min(float(tran_usd), A._TRAN_USD_TUONG_TAC), 2),
                           "trang_thai": "cho", "nhan": f"lô {i + 1}: {len(lo)} video (API)"})
                continue
            uoc = _uoc_lo(p, lo, pc)
            pl = _payload(p, lo, pc)
            ds.append({"id": f"{p}-{i}", "actor": _ACTORS[p], "lo": list(lo), "per": pc,
                       "payload": pl, "payload_sha": quet_lon._sha(pl),
                       "limit": _limit(p, lo, pc), "uoc_usd": round(uoc, 4),
                       "uoc_giay": round(_giay_lo(p, lo, pc), 1),
                       "can": _can_lo(p, uoc), "tran_lo": _tran_lo(p, uoc, tran_usd),
                       "min_charge": _MIN_CHARGE.get(p, 0.0), "gia": _GIA[p],
                       **({"mem": _RAM[p]} if p in _RAM else {}),
                       "trang_thai": "cho", "nhan": f"lô {i + 1}: {len(lo)} bài"})
        nt[p] = {"limit": sum(x["limit"] for x in ds), "phan": ds, "chua_phu": [],
                 "ghi_chu": []}
    return nt


def _thu_chay_nen(args, urls, nhom, per, cat_per, ke_tai_cho, per_url):
    """-> (kết quả trả NGAY | None, ghi chú cho lượt tại chỗ)."""
    import quet_lon
    import viec_nen
    if not nhom:
        return None, ""
    ep = args.get("chay_nen")
    ep = None if ep is None or ep == "" else A._co(ep)
    chi_uoc = A._co(args.get("chi_uoc_tinh"))
    tran_bl, tran_usd = _cau_hinh()
    tok = A._NEN.set(True)
    try:
        tran_bl_n, tran_usd_n = _cau_hinh()
    finally:
        A._NEN.reset(tok)
    # Lô của việc nền vẫn ≤5 USD/lô: một lô hỏng giữa chừng không đốt cả ngân sách, và
    # khởi động lại thì chỉ lô dở phải đọc tiếp.
    ke_n = {p: _chia_lo(p, us, per, min(tran_usd_n, A._TRAN_USD_TUONG_TAC))
            for p, us in nhom.items()}
    bl_n, est_n = _uoc_tinh(ke_n)
    _, est_tc = _uoc_tinh(ke_tai_cho)
    giay = _giay_ke(ke_tai_cho)
    han_tc = A._TOOL_DEADLINE - _DANH_CHO_SAU
    nguong = A._so_env("SOCIAL_NEN_BINH_LUAN", 1500, 50, 10 ** 6)
    vi_sao = ""
    if ep is True:
        vi_sao = "yêu cầu chạy nền"
    elif ep is None and bl_n > nguong:
        vi_sao = f"{bl_n} bình luận > {nguong}"
    elif ep is None and giay > han_tc:
        vi_sao = f"ước tính ~{giay:.0f} giây > {han_tc:.0f} giây của một lượt trả lời"
    elif ep is None and est_tc > tran_usd + 1e-9 and tran_usd_n > tran_usd + 1e-9:
        vi_sao = (f"ước tính {_usd(est_tc)} USD > trần {_usd(tran_usd)} USD của lượt chạy "
                  f"tại chỗ")
    if vi_sao and not viec_nen.bat():
        return None, (f"Chạy nền đang TẮT (SOCIAL_QUET_NEN=0) nên chạy tại chỗ trong trần "
                      f"lượt thường (lý do cần nền: {vi_sao}). Nói rõ.")
    if not vi_sao:
        if not chi_uoc:
            return None, ""
        uoc_bl, est = _uoc_tinh(ke_tai_cho)
        return tool_result(
            success=True, chi_uoc_tinh=True, se_chay_nen=False, so_bai=len(urls),
            max_comments=per, uoc_tinh_binh_luan=uoc_bl, uoc_tinh_chi_phi_usd=est,
            uoc_tinh_giay=giay, tran={"tran_binh_luan": tran_bl, "tran_usd_goi": tran_usd},
            note=("CHƯA CHẠY gì (chỉ ước tính). Lượt nhỏ, sẽ chạy ngay trong câu trả lời. "
                  "Báo phạm vi + ước tính rồi KẾT THÚC bằng \"Chạy nhé?\"; đồng ý thì gọi "
                  "lại không có `chi_uoc_tinh`.")), ""
    vuot = _ly_do_vuot(ke_n, tran_bl_n, tran_usd_n)
    if vuot:
        return _tra_vuot(urls, nhom, per, cat_per, ke_n, tran_bl_n, tran_usd_n, vuot), ""
    ns, hm, cau_ns = quet_lon.ngan_sach(tran_usd_n)
    phut = min(viec_nen.han_phut(), math.ceil((_giay_ke(ke_n, 2) + 180) / 60))
    base = dict(so_bai=len(urls), max_comments=per, max_comments_bi_cat=cat_per,
                ly_do_chay_nen=vi_sao, uoc_tinh_binh_luan=bl_n, uoc_tinh_usd=est_n,
                uoc_tinh_phut=phut, ngan_sach_usd=ns, ngan_sach_thang=cau_ns,
                tran={"tran_binh_luan": tran_bl_n, "tran_usd_goi": tran_usd_n},
                so_luot_chay=sum(len(c) for _, c in ke_n.values()),
                per_url_loi={u: v for u, v in per_url.items()} or None)
    if est_n > ns + 1e-9:
        return tool_result(
            success=False, chua_chay=True, vuot_ngan_sach=True, **base,
            thieu_ngan_sach_usd=round(est_n - ns, 2),
            note=(f"CHƯA CHẠY, chưa tốn tiền: ước tính {_usd(est_n)} USD vượt ngân sách "
                  f"{_usd(ns)} USD ({cau_ns}). Đề xuất bớt bài hoặc bớt bình luận/bài.")), ""
    if chi_uoc:
        return tool_result(
            success=True, chi_uoc_tinh=True, se_chay_nen=True, **base,
            note=(f"CHƯA CHẠY gì (chỉ ước tính). Lượt LỚN sẽ CHẠY NỀN: ~{bl_n} bình luận, "
                  f"~{_usd(est_n)} USD, ~{phut} phút. Lần này PHẢI nói số USD ước tính. KẾT "
                  f"THÚC bằng \"Chạy nhé?\"; đồng ý thì gọi lại bỏ `chi_uoc_tinh`.")), ""
    ts = {"post_urls": urls, "max_comments": per, "so_bai": len(urls),
          "title": str(args.get("title") or "").strip()}
    tom = viec_nen.tao_viec("social_deep_dive", ts, _ke_hoach_nen(ke_n, tran_usd_n),
                            {"usd": est_n, "phut": phut, "binh_luan": bl_n}, ns,
                            ghi_chu=[cau_ns], con_lai_thang=hm["con_lai"] if hm else None)
    return tool_result(**{**base, **tom, "success": not tom.get("tu_choi")}), ""


KIEU_YT_API = "yt_api_binh_luan"   # `kieu` của lượt con việc nền đi YouTube Data API


def mot_phan_yt_api(v, p: str, ph: dict, ns, ts: dict, chuan=None) -> int:
    """Lượt con việc nền đi YouTube Data API (miễn phí). Phần API không lấy được (không
    key/hết quota/lỗi HTTP) thì CHUYỂN lượt con thành lượt Apify actor streamers cho đúng
    các video còn lại, trần = phần còn lại của sổ việc (`ngoai_ke_hoach`) cắt theo
    `_tran_du_phong`, rồi để `quet_lon._mot_phan` chạy như lượt Apify thường (khởi động lại
    giữa chừng thì đọc tiếp run cũ như mọi lượt khác). -> số dòng lấy được."""
    import quet_lon
    if v.da_huy():
        v.cap_nhat_phan(ph, trang_thai="da_huy", ma="DA_HUY", so_item=0, usd_so=0.0)
        return 0
    han = v.han_mono(quet_lon._chua_nen_giay(60.0 * v.d.get("han_phut", 45)))
    r = _yt_api_lo(ph["lo"], int(ph["per"]), han)
    rows = []
    for c in r["binh_luan"]:
        c["platform"] = p
        c["bai"] = _quy_ve_bai(c.pop("_nguon", []) + [c.get("link") or ""], ph["lo"])
        rows.append((c, None))
    if rows:
        v.ghi_dong(p, rows, ph["id"])
    chung = dict(don_vi_quota=int(ph.get("don_vi_quota") or 0) + r["dv"],
                 loi_bai={u: list(x) for u, x in r["loi_bai"].items()}, so_item_api=len(rows))
    if not r["con_lai"]:
        v.cap_nhat_phan(ph, trang_thai="mot_phan" if r["mot_phan"] or r["chua_chay"] else "xong",
                        so_item=len(rows), ma="OK", usd_so=0.0, ly_do="", **chung)
        return len(rows)
    con = r["con_lai"]
    tok = _YT_API.set(False)
    try:
        can = _san(p)
        tran_lo = _tran_lo(p, _uoc_lo(p, con, int(ph["per"])),
                           float(ph.get("tran_usd_goi") or _TRAN_USD[0]))
    finally:
        _YT_API.reset(tok)
    try:
        cap = ns.xin(can, tran_lo, ngoai_ke_hoach=True)
    except TypeError:                     # sổ theo nền tảng: không có lượt ngoài kế hoạch
        cap = 0.0
    tran_dp, per_dp = _tran_du_phong(p, cap, 0.0, len(con), int(ph["per"])) if cap else (0, 0)
    if not per_dp or tran_dp + 1e-9 < can:
        if cap:
            ns.tra(cap, 0.0)
        v.cap_nhat_phan(ph, trang_thai="mot_phan" if rows else "loi", ma="NGAN_SACH",
                        so_item=len(rows), usd_so=0.0, video_loi=con,
                        ly_do=(f"YouTube Data API: {r['loi']} | dự phòng {_ACTORS[p]} không "
                               f"chạy: phần còn lại của ngân sách việc không đủ mức "
                               f"{_usd(can)} USD actor đòi giữ")[:300], **chung)
        return len(rows)
    pl = _payload(p, con, per_dp)
    v.cap_nhat_phan(ph, kieu="", payload=pl, payload_sha=quet_lon._sha(pl),
                    limit=per_dp * len(con), can=can, tran_lo=tran_dp,
                    min_charge=_MIN_CHARGE[p], gia=_GIA[p], du_phong_lo=con,
                    du_phong_ly_do=r["loi"][:200], **chung)
    return len(rows) + quet_lon._mot_phan(v, p, ph, ns, ts, chuan, cap_san=tran_dp)


def _chuan_nen(p: str, ph: dict, items: list) -> list[tuple]:
    bl, _ = _MAP[p](items)
    for c in bl:
        c["platform"] = p
        c["bai"] = _quy_ve_bai(c.pop("_nguon", []) + [c.get("link") or ""], ph["lo"])
    return [(c, None) for c in bl]


_AI_NEN_BINH_LUAN = 1000      # bình luận tối đa gửi model trong một việc nền (10 lượt × 100)


def _nhan_nen(v, rows: list[dict]) -> dict:
    """Gán nhãn sắc thái/chủ đề cho việc nền, có cache theo sha1(bài|nội dung): khởi động
    lại không hỏi model lại. Luật trước; model chỉ cho `SOCIAL_AI_NEN_BINH_LUAN` bình luận
    nhiều like nhất còn lại; phần sau "Chưa phân loại" — nói rõ, không đoán."""
    import hashlib
    import json as _json
    f = v.thu_muc() / "phan_loai.jsonl"
    cache: dict = {}
    try:
        for l in f.read_text(encoding="utf-8").splitlines():
            try:
                x = _json.loads(l)
                cache[x["k"]] = tuple(x["v"])
            except (ValueError, KeyError, TypeError):
                continue
    except OSError:
        pass

    def khoa(c):
        return hashlib.sha1(f"{c.get('bai')}|{c.get('text')}".encode("utf-8")).hexdigest()
    tt: dict = {}
    can = []
    for i, c in enumerate(rows):
        k = cache.get(khoa(c))
        if k:
            c["sac_thai"], c["chu_de"] = k
            continue
        lu = phan_loai._luat(c.get("text") or "")
        if lu and lu[0] != phan_loai.CHUA:
            c["sac_thai"], c["chu_de"] = lu
        else:
            can.append(i)
    toi_da = A._so_env("SOCIAL_AI_NEN_BINH_LUAN", _AI_NEN_BINH_LUAN, 0, 100000)
    can.sort(key=lambda i: -int(rows[i].get("likes") or 0))
    gui = can[:toi_da] if not v.da_huy() else []
    moi = {}
    if gui:
        han = max(30.0, min(420.0, v.con_giay() + 240))
        nhan = phan_loai.phan_loai_binh_luan([rows[i] for i in gui], han, tt)
        for i, nh in zip(gui, nhan):
            rows[i]["sac_thai"], rows[i]["chu_de"] = nh
            if nh[0] != phan_loai.CHUA:
                moi[khoa(rows[i])] = list(nh)
    if moi:
        with open(f, "a", encoding="utf-8") as fh:
            for k, val in moi.items():
                fh.write(_json.dumps({"k": k, "v": val}, ensure_ascii=False) + "\n")
    tt["khong_gui_model"] = len(can) - len(gui)
    return tt


def _bo_nen_tang_da_tat(v, ly_do: list) -> None:
    """Chủ agent tắt nền tảng (`bat_<p>`=0) SAU khi việc nền đã tạo: lượt con CHƯA chạy của
    nền tảng đó không chạy nữa (lượt đang chạy dở thì để `quet_lon` đọc tiếp như thường)."""
    c = A._cau_hinh_quet()
    tat = set()
    for p, ph in list(v.cac_phan()):
        if p in _THEO_CONSOLE_QUET and ph.get("trang_thai") in (None, "cho") \
                and not A._tran_nen_tang(p, nen=True, c=c)[2]:
            v.cap_nhat_phan(ph, trang_thai="loi", ma="DA_TAT", so_item=0, usd_so=0.0,
                            ly_do=A._ly_do_tat(p) + " — lượt này không chạy")
            tat.add(p)
    if tat:
        ly_do.append("; ".join(A._ly_do_tat(p) for p in sorted(tat))
                     + " sau khi tạo việc — phần chưa chạy của nền tảng đó bỏ qua")


def chay_viec_nen(v) -> tuple[str, str]:
    """Runner của viec_nen cho `social_deep_dive`. -> (trạng thái cuối, tin kết quả)."""
    import quet_lon
    import sheet_lon
    ts = v.d["tham_so"]
    ly_do: list[str] = []
    if v.d["trang_thai"] == "dang_cao":
        _bo_nen_tang_da_tat(v, ly_do)
        if v.qua_han():
            quet_lon._dong_phan_dang_chay(v, ts, chuan=_chuan_nen)
            ly_do.append("bot khởi động lại sau hạn chót — huỷ lô đang chạy, giữ phần đã có")
        else:
            quet_lon._chay_cac_phan(v, quet_lon._so_ngan_sach(v), ts, lambda p: None,
                                    chuan=_chuan_nen)
        v.dat("dang_loc")
    # Không lô nào còn sống trên Apify trước khi chốt tiền (review 02/10/2026).
    v.dung.set()
    quet_lon._thu_don_het(v, chuan=_chuan_nen)
    rows: list[dict] = []
    da = set()
    for p in v.d["nen_tang"]:
        for c, _ in v.doc_dong(p):
            k = (c.get("bai"), c.get("kenh"), c.get("text"), c.get("thoi_gian"))
            if k in da:
                continue
            da.add(k)
            rows.append(c)
    tt_pl = _nhan_nen(v, rows) if rows else {}
    v.dat("dang_ghi")
    per_url: dict = {}
    for p, nt in v.d["nen_tang"].items():
        for ph in nt["phan"]:
            st, lo = ph.get("trang_thai"), ph["lo"]
            cat = int(ph.get("so_item") or 0) >= 0.95 * ph["per"] * len(lo)
            loi_bai = ph.get("loi_bai") or {}
            dp_lo = set(ph.get("du_phong_lo") or [])
            loi_dp = set(ph.get("video_loi") or [])
            for u in lo:
                n = sum(1 for c in rows if c.get("bai") == u)
                if u in loi_bai:              # video tắt bình luận / không tồn tại (API)
                    per_url[u] = {"platform": p, "comments": 0, "status": loi_bai[u][0],
                                  "error": loi_bai[u][1]}
                    continue
                if ph.get("ma") == "DA_TAT":  # chủ agent tắt nền tảng sau khi tạo việc
                    per_url[u] = {"platform": p, "comments": n, "status": "ĐÃ TẮT",
                                  "error": ph.get("ly_do") or ""}
                    continue
                if u in loi_dp:               # API hỏng, dự phòng không đủ ngân sách
                    per_url[u] = {"platform": p, "comments": n, "status": "LỖI",
                                  "error": ph.get("ly_do") or ph.get("ma")}
                    continue
                if ph.get("so_item_api") is not None and u not in dp_lo:
                    # Đã lấy bằng API: trạng thái lượt dự phòng không áp cho video này.
                    per_url[u] = {"platform": p, "comments": n,
                                  "status": "ĐÃ HUỶ" if st == "da_huy" and not n else "OK"}
                    continue
                per_url[u] = {"platform": p, "comments": n, "status": (
                    "LỖI" if st == "loi" else "ĐÃ HUỶ" if st == "da_huy" else
                    _CHUA_XONG_GIU if st == "mot_phan" else
                    _CAT if (n == 0 and cat) else "OK")}
                if st == "loi":
                    per_url[u]["error"] = ph.get("ly_do") or ph.get("ma")
    mot_phan = any(x["status"] != "OK" for x in per_url.values())
    trang_thai = "da_huy" if v.da_huy() else "xong_mot_phan" if mot_phan else "xong"
    cp = v.chot_chi_phi([f"bình luận {len(ts['post_urls'])} bài"], list(v.d["nen_tang"]), "")
    tk = phan_loai.dem(rows, "bai") if rows else None
    url = ""
    if rows:
        try:
            s = sheet_lon.SoSheet(v)
            title = ts.get("title") or f"Bình luận nền · {len(ts['post_urls'])} bài · {v.ma}"
            s.dam_bao(title, "Bình luận", v.d.get("nguoi_yeu_cau") or "")
            s.bat_dau_giai_doan("cuoi")
            s.ghi_tab("Bình luận", [list(_HEADER)] + [[
                c["platform"], c.get("kenh") or "", str(c.get("text") or "")[:500],
                c.get("sac_thai", phan_loai.CHUA), c.get("chu_de", phan_loai.CHUA),
                c.get("likes") or 0, c.get("replies") or 0, c.get("thoi_gian") or "",
                c.get("tac_gia_thich") or "", c.get("bai") or c.get("link") or "",
                c.get("cha") or ""]
                for c in rows])
            s.ghi_tab(_TAB_THONG_KE, _dong_thong_ke(tk))
            url = s.s.get("url") or ""
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ == "MatQuyen":
                raise
            ly_do.append(f"ghi sheet lỗi: {_che_token(e)[:150]}")
    dau = {"xong": "XONG", "xong_mot_phan": "XONG MỘT PHẦN", "da_huy": "ĐÃ HUỶ"}[trang_thai]
    d = [f"[{dau}] Bóc bình luận nền {v.ma}: {len(ts['post_urls'])} bài, lấy được "
         f"{len(rows)} bình luận."]
    if trang_thai == "da_huy":
        d.append("Đã huỷ theo yêu cầu — sheet giữ phần lấy được tới lúc huỷ.")
    d.append(f"Link: {url}" if url else "Chưa có sheet (không có bình luận nào hoặc ghi lỗi).")
    for p in v.d["nen_tang"]:
        cua = [x for x in per_url.values() if x["platform"] == p]
        xau: dict = {}
        for x in cua:
            if x["status"] != "OK":
                xau[x["status"]] = xau.get(x["status"], 0) + 1
        d.append(f"- {p}: {sum(x['comments'] for x in cua)} bình luận từ {len(cua)} bài"
                 + (" · " + ", ".join(f"{n} bài {k}" for k, n in xau.items()) if xau else ""))
    if tk:
        d.append(f"Sắc thái (đã phân loại {tk['da_phan_loai']}/{tk['tong']}): "
                 + phan_loai.dong_thong_ke(tk).replace("\n", " "))
        if tt_pl.get("khong_gui_model"):
            d.append(f"{tt_pl['khong_gui_model']} bình luận ít like không gửi AI (trần "
                     f"{A._so_env('SOCIAL_AI_NEN_BINH_LUAN', _AI_NEN_BINH_LUAN, 0, 100000)}) — "
                     f"để 'Chưa phân loại'.")
    if any(ph.get("so_item_api") is not None for _, ph in v.cac_phan()):
        dv = sum(int(ph.get("don_vi_quota") or 0) for _, ph in v.cac_phan())
        d.append(f"YouTube lấy bằng {_YT_API_NGUON}: 0 USD, {dv} đơn vị quota.")
    if any(x["status"] == _TAT_BL for x in per_url.values()):
        d.append(f"Video '{_TAT_BL}': chủ video tắt bình luận, không phải lỗi nguồn.")
    if any(x["status"] == _CAT for x in per_url.values()):
        d.append(f"Bài '{_CAT}' là CHƯA lấy hết, không phải không có bình luận.")
    d.append(f"Chi phí thật: {_usd(cp.get('usd'))} USD ({cp.get('so_run', 0)} lượt chạy Apify; "
             f"ngân sách việc {_usd(v.d.get('ngan_sach_usd'))} USD).")
    if ly_do:
        d.append("Lưu ý: " + "; ".join(ly_do) + ".")
    with v._khoa:
        v.d["ket_qua"] = {"per_url": per_url, "tong_comment": len(rows), "sheet_url": url,
                          "phan_loai": {k: tt_pl.get(k) for k in ("trang_thai", "theo_ai",
                                                                   "theo_luat")}}
        v.luu()
    return trang_thai, "\n".join(d)


def _available() -> bool:
    import os
    return bool(os.environ.get("APIFY_TOKEN", "").strip())


def register() -> None:
    try:
        registry.register(
            name="social_deep_dive", toolset=_TOOLSET, schema=SCHEMA, handler=_handle,
            check_fn=_available, requires_env=[], is_async=False,
            description="Kéo bình luận của bài cụ thể (TikTok/YouTube/Facebook/Threads/"
                        "Instagram), gán nhãn "
                        "sắc thái/chủ đề, thống kê, ghi vào Lark Sheet",
            emoji="\U0001f4ac", override=True,
        )
    except Exception as e:
        print(f"[deep_dive_tool] register warning: {e}")


register()
