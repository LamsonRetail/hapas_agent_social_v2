"""Tool `chi_so_bai`: đếm VIEW / like / bình luận / share / lưu của một DANH SÁCH LINK BÀI
cụ thể, giữ đúng thứ tự người dùng dán, ghi một Lark Sheet và cộng tổng sẵn.

Vì sao cần — sổ audit 05–06/10/2026: team dán 33–70 link TikTok/FB/IG/YT/Threads, xin
"check traffic (view) từng link rồi cộng tổng, làm thành sheet". Mark không có công cụ
nào làm đúng việc này:
  • `soi_tai_khoan` đọc bài MỚI NHẤT của hồ sơ, không tra đúng từng link → số lệch bài;
  • `social_deep_dive` bóc bình luận, sheet không có cột view;
  • mò bằng trình duyệt thì TikTok chặn sau ~16 video, và Mark tự cộng tổng 25 số.
Kết cục: 9 lượt hỏi liền, lượt cuối Mark xin lỗi "chưa xác minh được view".

Nguồn — đo thật 06/10/2026 trên chính các link của lượt hỏi đó:
  • TikTok (clockworks~tiktok-video-scraper, 0,003 USD/video, KHÔNG đòi trần tối thiểu):
    3/3 link, kể cả link rút gọn vt.tiktok.com (`submittedVideoUrl` = link đã gửi,
    `webVideoUrl` = link thật). Đủ view/like/bình luận/share/lưu. Không dùng
    clockworks~tiktok-scraper: actor đó đòi `maxTotalChargeUsd` ≥ 0,5 USD mà trần TikTok
    trên console đang là 0,17 → bị từ chối.
  • YouTube (Data API v3 `videos.list`, miễn phí, 1 đơn vị quota mỗi 50 video): view,
    like, bình luận. API không có share/lưu.
  • Instagram (apify~instagram-scraper `directUrls`, 0,0027 USD/bài): reel trả
    `videoPlayCount` (lượt phát; `videoViewCount` rỗng), like, bình luận. Không có
    share/lưu công khai.
  • Facebook (apify~facebook-posts-scraper, ~0,005 USD/bài): link share/v/… và link
    reel đều đọc được like + bình luận; share chỉ có khi gửi link reel/bài gốc
    (`shares` hoặc `share_count_reduced`, có thể là số làm tròn kiểu "1,2K") — cùng bài
    gửi bằng link share/v/… thì không có; reel KHÔNG có view công khai, bài video thường
    có `viewsCount`.
  • Threads (futurizerush~threads-replies-scraper): dòng `original_post` có view, like,
    trả lời, repost, share. Actor tính 0,02 USD khởi động + 0,0025/dòng và bắt tối thiểu
    10 trả lời → ~0,05 USD/link. Link share/… không chứa mã bài nên MỖI LINK MỘT LƯỢT
    (không ghép được kết quả về link nếu gửi chung).

Trần: dùng trần RIÊNG từng nền tảng của console (Năng lực → Quét mạng xã hội:
`tran_bai_<p>` link/lượt gọi, `tran_usd_<p>` USD/lượt chạy actor, `bat_<p>` = 0 là tắt),
y như social_listen. Link vượt trần KHÔNG chạy, trả về `con_lai` để gọi lượt sau.
Tổng được CỘNG BẰNG CODE (Mark không có máy tính, tự cộng 25 số từng ra sai).
"""
from __future__ import annotations

import contextvars
import datetime
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

import apify_tool as A
import chi_phi_tool
import memory_store

from tools.registry import registry, tool_error, tool_result  # type: ignore

_NGUON = {
    "tiktok": "clockworks~tiktok-video-scraper",
    "instagram": "apify~instagram-scraper",
    "facebook": "apify~facebook-posts-scraper",
    "threads": "futurizerush~threads-replies-scraper",
}
# USD mỗi link (giá gói FREE 06/10/2026). Threads = 0,02 khởi động + 11 dòng × 0,0025.
_GIA = {"tiktok": 0.003, "instagram": 0.0027, "facebook": 0.005, "threads": 0.0475,
        "youtube": 0.0}
_TOI_DA_LINK = 300
_THREADS_SONG_SONG = 3
_COT = ("view", "like", "binh_luan", "share", "luu")
_TEN_COT = {"view": "View", "like": "Like", "binh_luan": "Bình luận", "share": "Share",
            "luu": "Lưu"}
# Chỉ số nền tảng không công khai: ô để TRỐNG kèm ghi chú, không phải "0".
_GHI_CHU_NEN = {
    "youtube": "YouTube không công khai share/lưu.",
    "instagram": "Instagram: view là lượt phát (plays); không công khai share/lưu.",
    "facebook": ("Facebook: reel không có view công khai; link share/… thường không trả số "
                 "share (link reel/bài gốc thì có, có thể là số làm tròn của FB)."),
    "threads": "Threads: bình luận = số trả lời; không công khai lưu.",
}


# ───────────────────────────── nhận diện link ─────────────────────────────
_URL = re.compile(r"https?://[^\s<>\"']+", re.I)


def _tach_link(ds) -> list[str]:
    """Danh sách hoặc một khối chữ → các link theo đúng thứ tự xuất hiện."""
    if isinstance(ds, str):
        ds = [ds]
    ra = []
    for muc in ds or []:
        s = str(muc or "").strip()
        for u in _URL.findall(s) or ([s] if s else []):
            ra.append(u.rstrip(".,;)]}>"))
    return ra


def _nhan_dien(url: str) -> tuple[str | None, str]:
    """→ (nền tảng, khoá chống trùng) nếu là link BÀI; (None, lý do) nếu không."""
    try:
        u = urlparse(url if "://" in url else "https://" + url)
    except ValueError:
        return None, "không phải link"
    host = (u.hostname or "").lower()
    path = u.path or ""
    if host.endswith("tiktok.com"):
        m = re.search(r"/(?:video|photo)/(\d+)", path)
        if m:
            return "tiktok", "tt:" + m.group(1)
        if host.split(".")[0] in ("vt", "vm") or path.startswith("/t/"):
            return "tiktok", "tt:" + url.split("?")[0].rstrip("/")
        return None, "link hồ sơ TikTok, không phải link bài"
    if host.endswith("youtube.com") or host == "youtu.be":
        vid = ""
        if host == "youtu.be":
            vid = path.strip("/").split("/")[0]
        elif path.startswith("/watch"):
            vid = (parse_qs(u.query).get("v") or [""])[0]
        else:
            m = re.match(r"/(?:shorts|live|embed)/([\w-]{11})", path)
            vid = m.group(1) if m else ""
        if re.fullmatch(r"[\w-]{11}", vid or ""):
            return "youtube", "yt:" + vid
        return None, "link kênh YouTube, không phải link video"
    if host.endswith("instagram.com"):
        m = re.search(r"/(?:p|reel|reels|tv)/([\w-]+)", path)
        if m:
            return "instagram", "ig:" + m.group(1)
        return None, "link hồ sơ Instagram, không phải link bài"
    if host.endswith(("threads.com", "threads.net")):
        m = re.search(r"/post/([\w-]+)", path)
        if m:
            return "threads", "th:" + m.group(1)
        if path.startswith(("/share/", "/t/")):
            return "threads", "th:" + url.split("?")[0].rstrip("/")
        return None, "link hồ sơ Threads, không phải link bài"
    if host.endswith(("facebook.com", "fb.com", "fb.watch")):
        if host.endswith("fb.watch") or re.search(
                r"/(?:share|reel|videos?|posts|watch|permalink\.php|story\.php|photo)", path):
            return "facebook", "fb:" + _fb_khoa(url)
        return None, "link trang Facebook, không phải link bài"
    return None, "nền tảng chưa hỗ trợ (chỉ TikTok, YouTube, Instagram, Facebook, Threads)"


def _fb_khoa(u: str) -> str:
    """Khoá so khớp link Facebook: bỏ giao thức, www/m/web, dấu / cuối; GIỮ query của
    watch?v= / permalink.php?story_fbid= (mã bài nằm ở đó), bỏ query khác."""
    s = re.sub(r"^(?:https?://)?(?:www\.|m\.|web\.|mbasic\.)?", "", str(u or "").strip())
    goc, _, q = s.partition("?")
    giu = [x for x in q.split("&") if x.split("=")[0] in ("v", "story_fbid", "id", "fbid")]
    return goc.rstrip("/") + ("?" + "&".join(sorted(giu)) if giu else "")


def _so(v) -> int | None:
    """Số nguyên từ dữ liệu nguồn; None nếu nguồn không có. Hiểu "1,2K", "3.4M"."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(" ", "")
    m = re.fullmatch(r"([\d.,]+)([KkMmBb]?)", s)
    if not m:
        return None
    so, don_vi = m.group(1), m.group(2).upper()
    if don_vi:
        try:
            return int(round(float(so.replace(",", ".")) * {"K": 1e3, "M": 1e6, "B": 1e9}[don_vi]))
        except ValueError:
            return None
    try:
        return int(so.replace(",", "").replace(".", ""))
    except ValueError:
        return None


# ───────────────────────────── lấy dữ liệu ─────────────────────────────
def _ket(tai_khoan=None, ngay=None, link=None, **so) -> dict:
    return {"tai_khoan": str(tai_khoan or ""), "ngay": ngay, "link_that": str(link or ""),
            **{c: so.get(c) for c in _COT}}


def _id_tiktok(u: str) -> str:
    m = re.search(r"/(?:video|photo)/(\d+)", str(u or ""))
    return m.group(1) if m else ""


def _lay_tiktok(urls: list[str]) -> dict[str, dict]:
    raw = A._call(_NGUON["tiktok"], {
        "postURLs": urls, "shouldDownloadVideos": False, "shouldDownloadCovers": False,
        "shouldDownloadSlideshowImages": False}, len(urls), nen_tang="tiktok")
    ra, theo_id = {}, {}
    for it in raw:
        if not it.get("webVideoUrl"):
            continue
        am = it.get("authorMeta") or {}
        k = _ket(am.get("name"), A._to_vn(it.get("createTimeISO")), it.get("webVideoUrl"),
                 view=_so(it.get("playCount")), like=_so(it.get("diggCount")),
                 binh_luan=_so(it.get("commentCount")), share=_so(it.get("shareCount")),
                 luu=_so(it.get("collectCount")))
        if it.get("submittedVideoUrl"):
            ra[str(it["submittedVideoUrl"])] = k
        if _id_tiktok(it["webVideoUrl"]):
            theo_id[_id_tiktok(it["webVideoUrl"])] = k
    # Link dài có query (?_r=1&_t=…) mà actor trả `submittedVideoUrl` khác chữ: khớp theo mã.
    return {u: ra.get(u) or theo_id.get(_id_tiktok(u)) for u in urls
            if ra.get(u) or theo_id.get(_id_tiktok(u))}


def _lay_youtube(urls: list[str]) -> dict[str, dict]:
    id_cua = {u: _nhan_dien(u)[1][3:] for u in urls}
    ids = list(dict.fromkeys(id_cua.values()))
    theo_id = {}
    for i in range(0, len(ids), 50):
        d = A._youtube_get("videos", {"part": "statistics,snippet",
                                      "id": ",".join(ids[i:i + 50]), "maxResults": 50})
        for it in d.get("items") or []:
            st, sn = it.get("statistics") or {}, it.get("snippet") or {}
            theo_id[it.get("id")] = _ket(
                sn.get("channelTitle"), A._to_vn(sn.get("publishedAt")),
                f"https://www.youtube.com/watch?v={it.get('id')}",
                view=_so(st.get("viewCount")), like=_so(st.get("likeCount")),
                binh_luan=_so(st.get("commentCount")))
    return {u: theo_id[v] for u, v in id_cua.items() if v in theo_id}


def _lay_instagram(urls: list[str]) -> dict[str, dict]:
    raw = A._call(_NGUON["instagram"], {"directUrls": urls, "resultsType": "posts",
                                         "resultsLimit": 1}, len(urls), nen_tang="instagram")
    theo_ma = {}
    for it in raw:
        if it.get("error") or not it.get("shortCode"):
            continue
        view = _so(it.get("videoPlayCount"))
        theo_ma[str(it["shortCode"])] = _ket(
            it.get("ownerUsername"), A._to_vn(it.get("timestamp")), it.get("url"),
            view=view if view is not None else _so(it.get("videoViewCount")),
            like=_so(it.get("likesCount")), binh_luan=_so(it.get("commentsCount")))
    return {u: theo_ma[_nhan_dien(u)[1][3:]] for u in urls
            if _nhan_dien(u)[1][3:] in theo_ma}


def _lay_facebook(urls: list[str]) -> dict[str, dict]:
    raw = A._call(_NGUON["facebook"], {"startUrls": [{"url": u} for u in urls],
                                        "resultsLimit": 1}, len(urls), nen_tang="facebook")
    theo = {}
    for it in raw:
        if it.get("error"):
            continue
        share = _so(it.get("shares"))
        if share is None:
            share = _so(it.get("share_count_reduced"))
        view = next((_so(it.get(k)) for k in ("viewsCount", "videoViewCount", "playCount")
                     if _so(it.get(k)) is not None), None)
        like = _so(it.get("likes"))
        if like is None:
            like = _so((it.get("unified_reactors") or {}).get("count"))
        bl = None if isinstance(it.get("comments"), list) else _so(it.get("comments"))
        if bl is None:
            bl = _so(it.get("total_comment_count"))
        k = _ket(it.get("pageName"), A._to_vn(it.get("time") or it.get("creation_time")),
                 it.get("url") or it.get("facebookUrl"),
                 view=view, like=like, binh_luan=bl, share=share)
        for khoa in (it.get("inputUrl"), it.get("facebookUrl")):
            if khoa:
                theo[_fb_khoa(khoa)] = k
    return {u: theo[_fb_khoa(u)] for u in urls if _fb_khoa(u) in theo}


def _lay_threads_mot(url: str) -> dict | None:
    raw = A._call(_NGUON["threads"], {"post_urls": [{"url": url}], "max_replies": 10,
                                       "include_nested_replies": False}, 12,
                  nen_tang="threads")
    for it in raw:
        if it.get("item_type") == "original_post" and not it.get("error"):
            return _ket(it.get("author_username"), A._to_vn(it.get("created_at")),
                        str(it.get("post_url") or "").split("?")[0],
                        view=_so(it.get("view_count")), like=_so(it.get("like_count")),
                        binh_luan=_so(it.get("reply_count")),
                        share=_so(it.get("share_count")))
    return None


def _lay_threads(urls: list[str]) -> dict[str, dict]:
    ra, loi = {}, []
    ex = ThreadPoolExecutor(max_workers=_THREADS_SONG_SONG)
    try:
        futs = {u: ex.submit(contextvars.copy_context().run, _lay_threads_mot, u) for u in urls}
        for u, f in futs.items():
            try:
                k = f.result()
            except Exception as e:  # noqa: BLE001
                loi.append(e)
                continue
            if k:
                ra[u] = k
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    if loi and not ra:
        raise loi[0]
    return ra


_LAY = {"tiktok": _lay_tiktok, "youtube": _lay_youtube, "instagram": _lay_instagram,
        "facebook": _lay_facebook, "threads": _lay_threads}


# ───────────────────────────── tool ─────────────────────────────
SCHEMA = {
    "name": "chi_so_bai",
    "description": (
        "Đếm chỉ số CÔNG KHAI (view, like, bình luận, share, lưu) của MỘT DANH SÁCH LINK BÀI "
        "cụ thể trên TikTok, YouTube, Instagram, Facebook, Threads — giữ ĐÚNG THỨ TỰ link "
        "người dùng dán, ghi MỘT Lark Sheet (mỗi link một dòng + dòng TỔNG) và cộng tổng "
        "sẵn. Dùng khi: 'check view/traffic các link này', 'đếm view, tym, lưu, share từng "
        "link rồi lập sheet', 'tổng traffic của các bài này', đo bài KOL/KOC/seeding đã lên. "
        "Nhận cả link rút gọn (vt.tiktok.com, fb share/…, threads share/…).\n"
        "KHÁC `soi_tai_khoan` (đọc bài MỚI NHẤT của một HỒ SƠ — không tra đúng từng link) và "
        "`social_deep_dive` (đọc NỘI DUNG bình luận). Có link bài cụ thể và cần SỐ LƯỢNG → "
        "dùng tool này, KHÔNG mò từng link bằng trình duyệt.\n"
        "Tốn tiền: gọi TRƯỚC với `chi_uoc_tinh`=true (miễn phí, không chạy), chép "
        "`cau_uoc_tinh` rồi hỏi \"Chạy nhé?\"; đồng ý thì gọi lại bỏ `chi_uoc_tinh`.\n"
        "KHI TRẢ LỜI: chép NGUYÊN `cau_tong` (tổng do code cộng — KHÔNG tự cộng lại), gửi "
        "NGUYÊN `sheet_url`, nói rõ link nào không lấy được (`khong_lay_duoc`) và chỉ số nền "
        "tảng không công khai (`gioi_han_nen_tang`) — ô trống KHÔNG phải số 0. Có `con_lai` "
        "(vượt trần console mỗi lượt) thì gọi tiếp với đúng các link đó (cùng phạm vi người "
        "dùng đã đồng ý), rồi báo cả hai sheet."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "link_bai": {"type": "array", "items": {"type": "string"},
                         "description": f"Link bài, đúng thứ tự người dùng dán (tối đa "
                                        f"{_TOI_DA_LINK}). Dán nguyên khối chữ có link cũng được."},
            "chi_uoc_tinh": {"type": "boolean",
                             "description": "true = chỉ ước tính chi phí, không chạy."},
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
        },
        "required": ["link_bai"],
    },
}


def _usd(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")


def _so_vn(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def _ten(p: str | None) -> str:
    return A._TEN_NGUON.get(p or "", p or "")


def _ke_hoach(dong: list[dict]) -> tuple[dict, list, set, dict]:
    """Gom link CẦN CHẠY theo nền tảng, áp công tắc + trần console từng nền tảng.
    → (chạy {nền: [link]}, còn lại [link], nền bị tắt, {nền: trần USD quá thấp})."""
    can: dict[str, list[str]] = {}
    for d in dong:
        if d["nen"] and d["trung_voi"] is None:
            can.setdefault(d["nen"], []).append(d["link"])
    chay, con_lai, tat, tran_thap = {}, [], set(), {}
    for p, us in can.items():
        tran_bai, tran_usd, bat = A._tran_nen_tang(p)
        if not bat:
            tat.add(p)
            continue
        n = tran_bai
        if p == "threads":
            n = tran_bai if tran_usd >= _GIA[p] else 0       # mỗi link một lượt actor
        elif _GIA[p] > 0:
            # Một lượt actor phải gọn trong trần USD (chừa 10% cho phí lệch giá).
            n = min(tran_bai, int(tran_usd / (_GIA[p] * 1.1)))
        if n < 1:
            tran_thap[p] = tran_usd
            continue
        chay[p] = us[:n]
        con_lai += us[n:]
    return chay, con_lai, tat, tran_thap


def _handle(args: dict, **_kwargs) -> str:
    links = _tach_link(args.get("link_bai"))
    if not links:
        return tool_error("Thiếu `link_bai` — dán các link bài cần đếm chỉ số.")
    du = links[_TOI_DA_LINK:]
    links = links[:_TOI_DA_LINK]

    dong, lan_dau = [], {}
    for i, u in enumerate(links):
        p, k = _nhan_dien(u)
        d = {"stt": i + 1, "link": u, "nen": p, "trang_thai": "", "ket": None,
             "trung_voi": None}
        if not p:
            d["trang_thai"] = f"Không đếm: {k}"
        elif k in lan_dau:
            d["trung_voi"] = lan_dau[k]
        else:
            lan_dau[k] = i + 1
        dong.append(d)

    chay, con_lai, tat, tran_thap = _ke_hoach(dong)
    est = sum(_GIA[p] * len(v) for p, v in chay.items())
    if A._co(args.get("chi_uoc_tinh")):
        theo_nen = {p: len(v) for p, v in chay.items()}
        cau = (f"Sẽ đếm chỉ số {sum(theo_nen.values())} link ("
               + ", ".join(f"{_ten(p)} {n}" for p, n in theo_nen.items())
               + f"), ước tính khoảng {_usd(est)} USD"
               + (" (YouTube miễn phí)" if "youtube" in theo_nen else "")
               + ", xuất MỘT Lark Sheet đúng thứ tự link kèm dòng tổng.")
        return tool_result(
            success=True, chi_uoc_tinh=True, so_link=len(links), theo_nen_tang=theo_nen,
            uoc_tinh_chi_phi_usd=round(est, 3), cau_uoc_tinh=cau,
            khong_dem=[f"{d['stt']}. {d['link']} — {d['trang_thai']}"
                       for d in dong if d["trang_thai"]] or None,
            trung_lap=[f"{d['stt']} trùng {d['trung_voi']}" for d in dong
                       if d["trung_voi"] is not None] or None,
            vuot_tran_console=con_lai or None,
            nen_tang_bi_tat=[A._ly_do_tat(p) for p in sorted(tat)] or None,
            tran_qua_thap={_ten(p): v for p, v in tran_thap.items()} or None,
            link_bi_bo_vi_qua_dai=len(du) or None,
            huong_dan=("Nêu phạm vi + chép `cau_uoc_tinh`, nói link nào không đếm được và vì "
                       "sao, rồi KẾT THÚC bằng \"Chạy nhé?\"."))

    bat_dau = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=5)
    t0 = time.monotonic()
    ket_qua: dict[str, dict] = {}
    loi: dict[str, str] = {}
    # KHÔNG `with ThreadPoolExecutor` (cùng lý do account_tool): một hạn chung cho mọi nguồn.
    han = t0 + A._TOOL_DEADLINE
    ex = ThreadPoolExecutor(max_workers=max(1, len(chay)))
    try:
        futs = {p: ex.submit(contextvars.copy_context().run, _LAY[p], v)
                for p, v in chay.items()}
        for p, f in futs.items():
            try:
                ket_qua.update(f.result(timeout=max(0.05, han - time.monotonic())))
            except Exception as e:  # noqa: BLE001
                loi[p] = A._che_token(f"{type(e).__name__}: {e}")[:250]
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    luc = datetime.datetime.now(A._VN_TZ)

    actors = [_NGUON[p] for p in chay if p in _NGUON]
    thuc = A._chi_phi_thuc(actors, bat_dau, est) if actors else None
    chi_phi_tool.ghi(queries=[f"chỉ số {len(links)} link bài"], platforms=sorted(chay),
                     date_range=f"lấy số lúc {luc:%Y-%m-%d %H:%M}", thuc=thuc, est=est)

    da_chay = {u for v in chay.values() for u in v}
    for d in dong:
        if d["trang_thai"] or d["trung_voi"] is not None:
            continue
        p = d["nen"]
        if p in tat:
            d["trang_thai"] = f"Không đếm: {A._ly_do_tat(p)}"
        elif p in tran_thap:
            d["trang_thai"] = (f"Không đếm: trần console {_ten(p)} ({_usd(tran_thap[p])} "
                               f"USD/lượt) thấp hơn giá một link")
        elif d["link"] not in da_chay:
            d["trang_thai"] = "Chưa đếm: vượt trần console mỗi lượt, gọi lượt sau"
        elif d["link"] in ket_qua:
            d["ket"], d["trang_thai"] = ket_qua[d["link"]], "OK"
        elif p in loi:
            d["trang_thai"] = f"Lỗi nguồn {_ten(p)}"
        else:
            d["trang_thai"] = "Không lấy được (bài đã xoá, riêng tư hoặc nguồn chặn)"
    for d in dong:          # dòng trùng: hiện số của dòng gốc, KHÔNG cộng vào tổng
        if d["trung_voi"] is not None:
            goc = dong[d["trung_voi"] - 1]
            d["ket"] = goc["ket"]
            d["trang_thai"] = f"Trùng link dòng {d['trung_voi']}, không cộng lại vào tổng"

    # Tổng: chỉ dòng OK (dòng trùng không phải "OK"); ô trống không tính là 0.
    ok = [d for d in dong if d["trang_thai"] == "OK"]
    tong = {c: {"tong": sum(d["ket"][c] for d in ok if d["ket"][c] is not None),
                "so_link_co_so": sum(1 for d in ok if d["ket"][c] is not None)} for c in _COT}
    view_nen: dict[str, int] = {}
    for d in ok:
        if d["ket"]["view"] is not None:
            view_nen[_ten(d["nen"])] = view_nen.get(_ten(d["nen"]), 0) + d["ket"]["view"]
    cau_tong = (f"Đếm được {len(ok)}/{len(links)} link. Tổng view: "
                f"{_so_vn(tong['view']['tong'])} (cộng trên {tong['view']['so_link_co_so']} "
                f"link có số view"
                + (": " + ", ".join(f"{p} {_so_vn(v)}" for p, v in view_nen.items())
                   if len(view_nen) > 1 else "")
                + "). " + "; ".join(f"{_TEN_COT[c]} {_so_vn(tong[c]['tong'])} "
                                    f"({tong[c]['so_link_co_so']} link)"
                                    for c in _COT[1:] if tong[c]["so_link_co_so"]) + ".")

    url, granted = None, False
    header = ["STT", "Link", "Nền tảng", "Tài khoản", "Ngày đăng", "View", "Like",
              "Bình luận", "Share", "Lưu", "Trạng thái", "Ghi chú", "Lấy số lúc"]
    rows = [header]
    for d in dong:
        k = d["ket"] or {}
        rows.append([
            d["stt"], d["link"], _ten(d["nen"]), k.get("tai_khoan", ""),
            f"{k['ngay']:%Y-%m-%d}" if k.get("ngay") else "",
            *[k.get(c) if k.get(c) is not None else "" for c in _COT],
            d["trang_thai"], _GHI_CHU_NEN.get(d["nen"] or "", "") if k else "",
            f"{luc:%Y-%m-%d %H:%M}" if k else ""])
    rows.append([""] * len(header))
    rows.append(["", f"TỔNG ({len(ok)} link OK, không cộng dòng trùng)", "", "", "",
                 *[tong[c]["tong"] if tong[c]["so_link_co_so"] else "" for c in _COT],
                 "", "Ô trống = nguồn không có số, không tính là 0", ""])
    if ok:
        title = (args.get("title") or "").strip() or \
            f"Chỉ số {len(links)} link bài · {luc:%d-%m-%Y %H:%M}"
        try:
            tok, url = A._create_sheet(title)
            A._write_values(tok, A._first_sheet_id(tok), rows)
            sender = memory_store.get_current_sender()
            granted = A._grant(tok, sender) if sender else False
        except Exception as e:  # noqa: BLE001
            loi["sheet"] = f"{type(e).__name__}: {e}"[:250]

    if not ok and loi:
        return tool_error("Không đếm được link nào: " + "; ".join(
            f"{k}: {v}" for k, v in loi.items()))
    return tool_result(
        success=not loi, so_link=len(links), so_link_ok=len(ok), tong=tong,
        tong_view_theo_nen_tang=view_nen or None, cau_tong=cau_tong,
        khong_lay_duoc=[f"{d['stt']}. {d['link']} — {d['trang_thai']}" for d in dong
                        if d["trang_thai"] != "OK" and d["trung_voi"] is None] or None,
        trung_lap=[f"{d['stt']} trùng {d['trung_voi']}" for d in dong
                   if d["trung_voi"] is not None] or None,
        con_lai=con_lai or None, link_bi_bo_vi_qua_dai=len(du) or None,
        gioi_han_nen_tang=[_GHI_CHU_NEN[p] for p in sorted({d["nen"] for d in ok})
                           if p in _GHI_CHU_NEN] or None,
        loi=loi or None, sheet_url=url, granted=granted,
        lay_so_luc=f"{luc:%H:%M %d/%m/%Y}", uoc_tinh_chi_phi_usd=round(est, 3),
        chi_phi_thuc_usd=thuc["usd"] if thuc and thuc.get("so_run") else None,
        chi_phi=A._dong_chi_phi(thuc, est), giay=round(time.monotonic() - t0, 1),
    )


def _available() -> bool:
    return A._available()


try:
    registry.register(
        name="chi_so_bai", toolset="social", schema=SCHEMA, handler=_handle,
        check_fn=_available, requires_env=[], is_async=False,
        description="Đếm view/like/bình luận/share/lưu của danh sách link bài, ra Lark Sheet",
        emoji="\U0001f4ca", override=True,
    )
except Exception as e:  # noqa: BLE001
    print(f"[chi_so_bai_tool] register warning: {e}")
