"""Register a `social_deep_dive` tool — kéo BÌNH LUẬN của các bài cụ thể về một
Lark Sheet riêng, cấp quyền cho người hỏi, trả link.

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
  `_call(min_charge=…)` TỪ CHỐI (báo rõ) khi trần console thấp hơn mức này chứ
  không tự nâng trần — trước 01/10/2026 `_call` thiếu tham số nên mọi lượt
  YouTube/Facebook chết vì TypeError.
- Facebook (apify/facebook-comments-scraper, 4.73*): chạy được nhưng khi bài
  không có comment / bài riêng tư thì trả về OBJECT LỖI
  {"error": "no_items", "errorDescription": "..."} chứ KHÔNG phải mảng rỗng.
  Không bắt trường `error` thì sẽ map nhầm object đó thành một "bình luận".
  Tên trường khi có dữ liệu chưa kiểm chứng được (chưa tìm ra bài FB nào có
  comment) -> map phòng thủ nhiều tên ứng viên, không khớp thì BÁO RA thay vì
  ghi dòng rỗng.
- Instagram: CHƯA nối. Phải từ chối rõ, không được lặng lẽ bỏ qua.
"""

from __future__ import annotations

import datetime
import re

import memory_store
from apify_tool import (_VN_TZ, _call, _che_token, _grant, _create_sheet,
                        _first_sheet_id, _to_vn, lark)

from tools.registry import registry, tool_error, tool_result  # type: ignore

_TOOLSET = "social"
_MAX_PER_POST = 300
_MAX_POSTS = 20

_ACTORS = {
    "tiktok": "clockworks~tiktok-comments-scraper",
    "youtube": "streamers~youtube-comments-scraper",
    "facebook": "apify~facebook-comments-scraper",
}
# Actor YouTube từ chối chạy nếu trần chi phí < 0.50 (đo thật).
_MIN_CHARGE = {"youtube": 0.5, "facebook": 0.5}

_HEADER = ["Nền tảng", "Người bình luận", "Nội dung bình luận", "Likes",
           "Trả lời", "Thời gian", "Tác giả đã thích", "Link bài"]


def _platform_of(url: str) -> str | None:
    u = (url or "").lower()
    if "tiktok.com" in u:
        return "tiktok"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "facebook.com" in u or "fb.com" in u or "fb.watch" in u:
        return "facebook"
    if "instagram.com" in u:
        return "instagram"      # biết tên nhưng CHƯA nối actor
    if "threads.net" in u or "threads.com" in u:
        return "threads"        # biết tên nhưng CHƯA nối actor
    return None


# ───────────────────────── adapter từng nền tảng ─────────────────────────
def _first(d: dict, *names, default=""):
    """Lấy giá trị đầu tiên có trong dict theo danh sách tên ứng viên."""
    for n in names:
        v = d.get(n)
        if v not in (None, ""):
            return v
    return default


def _fetch_tiktok(urls: list[str], per: int) -> list[dict]:
    raw = _call(_ACTORS["tiktok"],
                {"postURLs": urls, "commentsPerPost": per}, per * len(urls))
    return [{
        "kenh": it.get("uniqueId") or "",
        "text": str(it.get("text") or "")[:1000],
        "likes": int(it.get("diggCount") or 0),
        "replies": int(it.get("replyCommentTotal") or 0),
        "thoi_gian": (lambda d: d.strftime("%Y-%m-%d %H:%M") if d else "")(
            _to_vn(it.get("createTimeISO"))),
        "tac_gia_thich": "có" if it.get("likedByAuthor") else "",
        "link": it.get("videoWebUrl") or it.get("submittedVideoUrl") or "",
    } for it in raw]


def _fetch_youtube(urls: list[str], per: int) -> list[dict]:
    raw = _call(_ACTORS["youtube"],
                {"startUrls": [{"url": u} for u in urls], "maxComments": per},
                per * len(urls), min_charge=_MIN_CHARGE["youtube"])
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
    } for it in raw]


def _fetch_facebook(urls: list[str], per: int) -> list[dict]:
    raw = _call(_ACTORS["facebook"],
                {"startUrls": [{"url": u} for u in urls], "resultsLimit": per},
                per * len(urls), min_charge=_MIN_CHARGE["facebook"])
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
            "thoi_gian": (lambda d: d.strftime("%Y-%m-%d %H:%M") if d else "")(
                _to_vn(_first(it, "date", "timestamp", "createdAt", default=None))),
            "tac_gia_thich": "",
            "link": str(_first(it, "facebookUrl", "commentUrl", "postUrl")),
        })
    if la and not out:
        raise RuntimeError(
            "Actor Facebook trả về shape KHÔNG khớp map hiện tại — không ghi bừa. "
            f"Các key nhận được: {la[0]}. Báo lại để sửa mapping.")
    return out


_FETCH = {"tiktok": _fetch_tiktok, "youtube": _fetch_youtube, "facebook": _fetch_facebook}


# ───────────────────────── sheet ─────────────────────────
def _write(token: str, sheet_id: str, values: list[list]) -> None:
    col = chr(ord("A") + len(_HEADER) - 1)
    for i in range(0, len(values), 1000):
        ch = values[i:i + 1000]
        lark.call("POST", f"/open-apis/sheets/v2/spreadsheets/{token}/values_batch_update",
                  body={"valueRanges": [{"range": f"{sheet_id}!A{i+1}:{col}{i+len(ch)}",
                                         "values": ch}]})


# ───────────────────────── tool ─────────────────────────
SCHEMA = {
    "name": "social_deep_dive",
    "description": (
        "Soi SÂU một hoặc nhiều bài cụ thể: kéo BÌNH LUẬN về, ghi vào Lark Sheet riêng, "
        "cấp quyền cho người hỏi và trả LINK SHEET. Dùng khi ai nhờ 'xem người ta bình "
        "luận gì về bài này', 'soi kỹ bài đó', 'khách nói gì', 'sentiment ra sao', hoặc "
        "khi cần đánh giá sức khoẻ thương hiệu / phát hiện khủng hoảng.\n"
        "ĐẦU VÀO: `post_urls` — lấy từ cột `Link` trong sheet mà `social_listen` đã tạo, "
        "hoặc link người dùng dán vào.\n"
        "HỖ TRỢ: TikTok, YouTube, Facebook. CHƯA hỗ trợ Instagram và Threads — gặp link "
        "hai nền tảng đó phải NÓI THẲNG là chưa nối nguồn, TUYỆT ĐỐI không thay bằng "
        "nền tảng khác rồi để người dùng tưởng là của nền tảng họ hỏi.\n"
        "BẮT BUỘC KHI TRẢ LỜI:\n"
        "- Đọc `per_url`: bài nào lấy được bao nhiêu comment, bài nào lỗi/không có. Bài "
        "0 comment là BÌNH THƯỜNG (bài đó thật sự chưa ai bình luận), KHÔNG phải lỗi.\n"
        "- Tool TỐN TIỀN theo SỐ COMMENT. Xác nhận số bài + `max_comments` TRƯỚC khi gọi. "
        "Mặc định 50/bài; đừng tự ý đẩy lên cao.\n"
        "- YouTube trả thời gian dạng chữ tương đối ('2 years ago'), KHÔNG phải ngày "
        "tuyệt đối — đừng quy đổi thành ngày cụ thể.\n"
        "- Gửi NGUYÊN `sheet_url`. `granted`=false thì báo người dùng có thể mở không được.\n"
        "- Khi tóm tắt sentiment phải DẪN comment thật, không tự suy diễn cảm xúc."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "post_urls": {"type": "array", "items": {"type": "string"},
                          "description": "Link bài cần soi (tối đa 20). Lấy từ cột Link của sheet social_listen."},
            "max_comments": {"type": "integer",
                             "description": "Số bình luận tối đa MỖI bài (mặc định 50, trần 300)."},
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
        },
        "required": ["post_urls"],
    },
}


def _handle(args: dict, **kwargs) -> str:
    urls = [str(u).strip() for u in (args.get("post_urls") or []) if str(u).strip()]
    if not urls:
        return tool_error("Thiếu `post_urls` (link bài cần soi).")
    if len(urls) > _MAX_POSTS:
        return tool_error(f"Tối đa {_MAX_POSTS} bài mỗi lần, bạn đưa {len(urls)}.")
    try:
        per = int(args.get("max_comments") or 50)
    except (TypeError, ValueError):
        per = 50
    per = max(1, min(per, _MAX_PER_POST))

    nhom: dict[str, list[str]] = {}
    chua_ho_tro: dict[str, list[str]] = {}
    for u in urls:
        p = _platform_of(u)
        if p in _FETCH:
            nhom.setdefault(p, []).append(u)
        else:
            chua_ho_tro.setdefault(p or "không nhận ra", []).append(u)

    if not nhom:
        return tool_error(
            f"Không link nào thuộc nền tảng đã nối. Chưa hỗ trợ: "
            f"{', '.join(chua_ho_tro)}. Hãy NÓI THẲNG là chưa nối nguồn cho các nền "
            f"tảng đó, đừng thay bằng nguồn khác.")

    per_url, rows, failed = {}, [], []
    for p, us in nhom.items():
        try:
            got = _FETCH[p](us, per)
        except Exception as e:  # noqa: BLE001
            # Che token: chuỗi lỗi đi thẳng vào câu trả lời của model và sổ audit.
            for u in us:
                per_url[u] = {"platform": p, "status": "LỖI",
                              "error": _che_token(f"{type(e).__name__}: {e}")[:220]}
            failed.append(p)
            continue
        for c in got:
            c["platform"] = p
            rows.append(c)
        # đếm theo từng link để biết bài nào rỗng
        for u in us:
            n = sum(1 for c in got if u.split("?")[0].rstrip("/") in (c.get("link") or ""))
            per_url[u] = {"platform": p, "status": "OK", "comments": n}
        tong = len(got)
        if tong and sum(v.get("comments", 0) for v in per_url.values()) == 0:
            # link trả về không khớp link gửi đi -> vẫn có dữ liệu, chỉ là không quy được về bài
            per_url[us[0]]["comments"] = tong
            per_url[us[0]]["ghi_chu"] = "không khớp được comment về từng link, gộp chung"

    for p, us in chua_ho_tro.items():
        for u in us:
            per_url[u] = {"platform": p, "status": "CHƯA HỖ TRỢ",
                          "error": f"Chưa nối nguồn bình luận cho {p}. Phải nói thẳng."}

    base = dict(so_bai=len(urls), max_comments=per, per_url=per_url,
                platforms_failed=failed, chua_ho_tro=list(chua_ho_tro),
                tong_comment=len(rows))

    if not rows:
        return tool_result(
            success=not failed, sheet_url=None, **base,
            note="Không lấy được bình luận nào. Nếu các bài đều 0 comment thì đó là SỰ "
                 "THẬT (chưa ai bình luận), không phải lỗi — nói đúng như vậy. Không tạo sheet.")

    title = (args.get("title") or "").strip() or \
        f"Bình luận · {len(urls)} bài · {datetime.datetime.now(_VN_TZ):%d-%m %H%M}"
    values = [list(_HEADER)] + [[
        c["platform"], c["kenh"], c["text"], c["likes"], c["replies"],
        c["thoi_gian"], c["tac_gia_thich"], c["link"],
    ] for c in rows]

    try:
        tok, url = _create_sheet(title)
        _write(tok, _first_sheet_id(tok), values)
    except Exception as e:  # noqa: BLE001
        return tool_result(
            success=False, sheet_url=None, **base,
            error=_che_token(f"Lấy được {len(rows)} comment nhưng TẠO/GHI SHEET THẤT "
                             f"BẠI: {type(e).__name__}: {e}"),
            mau=[{"kenh": c["kenh"], "text": c["text"][:120]} for c in rows[:5]])

    sender = memory_store.get_current_sender()
    granted = _grant(tok, sender) if sender else False

    return tool_result(
        success=True, title=title, sheet_url=url, granted=granted, **base,
        mau=[{"nen_tang": c["platform"], "kenh": c["kenh"], "likes": c["likes"],
              "text": c["text"][:160]} for c in rows[:10]],
        note=(f"Đã ghi ĐỦ {len(rows)} bình luận vào sheet '{title}'. GỬI `sheet_url`. "
              f"Khi tóm tắt sentiment phải DẪN comment thật, đừng suy diễn."
              + (f" CẢNH BÁO: nguồn HỎNG: {', '.join(failed)}." if failed else "")
              + (f" CHƯA HỖ TRỢ: {', '.join(chua_ho_tro)} — phải nói rõ."
                 if chua_ho_tro else "")
              + ("" if granted else " CẢNH BÁO: chưa cấp được quyền tự động.")),
    )


def _available() -> bool:
    import os
    return bool(os.environ.get("APIFY_TOKEN", "").strip())


def register() -> None:
    try:
        registry.register(
            name="social_deep_dive", toolset=_TOOLSET, schema=SCHEMA, handler=_handle,
            check_fn=_available, requires_env=[], is_async=False,
            description="Kéo bình luận của bài cụ thể (TikTok/YouTube/Facebook) vào Lark Sheet",
            emoji="\U0001f4ac", override=True,
        )
    except Exception as e:
        print(f"[deep_dive_tool] register warning: {e}")


register()
