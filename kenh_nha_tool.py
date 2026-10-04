"""Tool `binh_luan_kenh_nha`: đọc ĐỦ bình luận trên bài của CHÍNH HAPAS (Threads,
Instagram, Trang Facebook) qua API chính thức của Meta — miễn phí, không Apify.

Ranh giới với `social_deep_dive` (chốt 04/10/2026):
  • Bài của kênh HAPAS → tool này: đủ bình luận + trả lời ở mọi cấp, 0 USD.
  • Bài của đối thủ / người khác → `social_deep_dive` (Apify, không đăng nhập, Threads/
    Instagram chỉ một phần, tốn tiền). Token chủ kênh chỉ đọc được bài của chính kênh.

Đầu ra cùng hình với `social_deep_dive`: mỗi bình luận một dòng (nền tảng, người bình
luận, nội dung, Sắc thái, Chủ đề, likes, số trả lời, thời gian, link bài) + hai cột quan
hệ cha–con (Cấp, Trả lời cho); gán nhãn bằng `phan_loai.phan_loai_binh_luan`, tab
"Thống kê" bằng `deep_dive_tool._ghi_thong_ke`, ghi sheet qua `apify_tool._write_values`
(bộ chặn công thức `_bang_an_toan`). Trả lời của CHÍNH kênh nhà nằm trong sheet nhưng
KHÔNG gán nhãn, KHÔNG vào thống kê — "cảm ơn bạn" của shop không phải tiếng nói khách.

Tiền: 0 USD (API Meta miễn phí, có hạn mức gọi). Vẫn ghi Lark Sheet nên lời dặn ở prompt
giữ nếp "ước tính miễn phí → Chạy nhé?" như các tool ghi sheet khác.
Mạng + token: `kenh_nha_meta.py`.
"""
from __future__ import annotations

import datetime
import os
import re
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, wait

import apify_tool as A
import deep_dive_tool as D
import kenh_nha_meta as M
import memory_store
import phan_loai

from tools.registry import registry, tool_error, tool_result  # type: ignore

TEN_TOOL = "binh_luan_kenh_nha"
_MAC_DINH_BAI = 5
_TOI_DA_BAI = 50
_MAC_DINH_BL = 200          # bình luận (mọi cấp) tối đa MỖI bài
_TOI_DA_BL = 2000
_QUET_TIM_BAI = 300         # số bài gần nhất được dò khi tìm bài theo link
_DANH_CHO_SAU = 45          # giây chừa cho gán nhãn + ghi sheet trong `_TOOL_DEADLINE`
_PHAN_LOAI_TOI_DA = 50

_HEADER = list(D._HEADER[:10]) + ["Cấp", "Trả lời cho"]
_HEADER_BAI = ["Nền tảng", "Link bài", "Ngày đăng", "Nội dung bài", "Bình luận đã lấy",
               "Số bình luận nền tảng báo", "Trạng thái"]
_TAB_BAI = "Bài đã đọc"
_KENH_NHA = "— (kênh nhà trả lời)"
_CHAM_TRAN = "CHẠM TRẦN max_comments — còn bình luận chưa lấy"
_HET_GIO = "CHƯA XONG — hết thời gian, chỉ có phần đã lấy"

_F_TH_BAI = "id,permalink,text,timestamp,shortcode,media_type"
_F_TH_BL = ("id,text,username,timestamp,replied_to,root_post,is_reply_owned_by_me,"
            "has_replies,hide_status,permalink")
_F_IG_BAI = "id,caption,permalink,timestamp,shortcode,comments_count,media_product_type"
_F_IG_TL = "id,text,username,timestamp,like_count"
_F_IG_BL = f"id,text,username,timestamp,like_count,replies{{{_F_IG_TL}}}"
_F_FB_BAI = "id,message,created_time,permalink_url,comments.limit(0).summary(true)"
_F_FB_BL = "id,message,from{id,name},created_time,like_count,comment_count,parent{id},permalink_url"


def _so(v, md: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return md


def _gio(raw) -> str:
    d = A._to_vn(raw)
    return d.strftime("%Y-%m-%d %H:%M") if d else ""


def _co(v) -> bool:
    return A._co(v) if v not in (None, "") else False


# ───────────────────────── đầu vào ─────────────────────────
def _kenh_xin(v) -> tuple[list[str], list[str]]:
    """-> (kênh hợp lệ, chữ không nhận ra). Bỏ trống / 'all' / 'tat_ca' = cả ba."""
    if v in (None, "", []):
        return list(M.KENH), []
    xs = v if isinstance(v, list) else re.split(r"[,\s;]+", str(v))
    ra, la = [], []
    for x in xs:
        k = str(x).strip().lower()
        if not k:
            continue
        if k in ("all", "tat_ca", "tất cả", "tat ca", "*"):
            return list(M.KENH), []
        k = {"ig": "instagram", "insta": "instagram", "fb": "facebook",
             "page": "facebook", "th": "threads"}.get(k, k)
        (ra if k in M.KENH else la).append(k)
    return list(dict.fromkeys(ra)), la


def _kenh_cua_link(u: str) -> str | None:
    p = D._platform_of(u)
    return p if p in M.KENH else None


_RE_MA = {
    "threads": [r"/post/([\w-]+)", r"threads\.(?:net|com)/t/([\w-]+)"],
    "instagram": [r"/(?:p|reels?|tv)/([\w-]+)"],
    "facebook": [r"story_fbid=(\w+)", r"[?&]fbid=(\d+)", r"/posts/([\w]+)",
                 r"/(?:videos|reel|reels|permalink)/(?:[^/?#]+/)?(\d+)", r"[?&]v=(\d+)"],
}


def _ma_trong_link(kenh: str, u: str) -> str:
    for rx in _RE_MA[kenh]:
        m = re.search(rx, u)
        if m:
            return m.group(1)
    return ""


# ID bài trần được nhận (review bảo mật PR #10): ID đi thẳng vào đường dẫn Graph, nên chỉ
# nhận đúng hình ID Meta công bố — media Threads/Instagram là dãy số; bài Trang Facebook là
# "<id Trang>_<id bài>" hoặc chỉ id bài (số). Có `?`, `&`, `#`, `/`… là từ chối.
_RE_ID = {"threads": re.compile(r"[0-9]{1,30}"), "instagram": re.compile(r"[0-9]{1,30}"),
          "facebook": re.compile(r"[0-9]{1,30}(?:_[0-9]{1,30})?")}


def id_hop_le(kenh: str, u: str) -> bool:
    return bool(_RE_ID[kenh].fullmatch(u))


def _doan(x: str) -> str:
    """Một đoạn đường dẫn Graph đã quote (phòng thủ thêm sau allow-list)."""
    return urllib.parse.quote(str(x), safe="_")


def _chuan_link(u: str) -> str:
    return re.sub(r"^https?://(?:www\.|m\.)?", "", str(u or "").strip().lower()
                  ).split("?")[0].split("#")[0].rstrip("/")


# ───────────────────────── bài của kênh ─────────────────────────
def _bai_th(x: dict) -> dict:
    return {"id": str(x.get("id") or ""), "link": str(x.get("permalink") or ""),
            "ngay": _gio(x.get("timestamp")), "_ts": x.get("timestamp"),
            "noi_dung": str(x.get("text") or "")[:300], "ma": str(x.get("shortcode") or ""),
            "bao": None}


def _bai_ig(x: dict) -> dict:
    return {"id": str(x.get("id") or ""), "link": str(x.get("permalink") or ""),
            "ngay": _gio(x.get("timestamp")), "_ts": x.get("timestamp"),
            "noi_dung": str(x.get("caption") or "")[:300], "ma": str(x.get("shortcode") or ""),
            "bao": x.get("comments_count")}


def _bai_fb(x: dict) -> dict:
    tong = ((x.get("comments") or {}).get("summary") or {}).get("total_count")
    return {"id": str(x.get("id") or ""), "link": str(x.get("permalink_url") or ""),
            "ngay": _gio(x.get("created_time")), "_ts": x.get("created_time"),
            "noi_dung": str(x.get("message") or "")[:300], "ma": "", "bao": tong}


_BAI = {"threads": ("me/threads", _F_TH_BAI, _bai_th),
        "instagram": ("me/media", _F_IG_BAI, _bai_ig),
        "facebook": (None, _F_FB_BAI, _bai_fb)}


def _ds_bai(kenh: str, tok: str, n: int, tu, den, han: float) -> list[dict]:
    """`n` bài mới nhất của kênh trong khoảng [tu, den] (datetime VN hoặc None)."""
    duong, f, chuan = _BAI[kenh]
    duong = duong or f"{os.environ['FB_PAGE_ID'].strip()}/posts"
    p: dict = {"fields": f, "limit": min(100, max(n, 10))}
    if tu:
        p["since"] = int(tu.timestamp())
    if den:
        p["until"] = int(den.timestamp())

    def cu_qua(x):   # danh sách mới → cũ: gặp bài cũ hơn `tu` thì dừng
        d = A._to_vn(x.get("timestamp") or x.get("created_time"))
        return bool(tu and d and d < tu)

    raw, _ = M.phan_trang(kenh, duong, p, tok, n * 3 if den else n, han, dung=cu_qua)
    ra = []
    for x in raw:
        if kenh == "threads" and str(x.get("media_type") or "") == "REPOST_FACADE":
            continue          # bài đăng lại của người khác, không phải bài của kênh
        d = A._to_vn(x.get("timestamp") or x.get("created_time"))
        if den and d and d > den:
            continue
        ra.append(chuan(x))
        if len(ra) >= n:
            break
    return ra


def _tim_bai(kenh: str, tok: str, yeu_cau: list[str], han: float) -> tuple[list[dict], dict]:
    """Link/ID người dùng đưa → bài của kênh. -> (bài, {đầu vào: lý do không tìm thấy})."""
    page_id = os.environ.get("FB_PAGE_ID", "").strip()
    bai, khong = [], {}
    can_quet = []
    for u in yeu_cau:
        la_link = "/" in u or "." in u
        ma = _ma_trong_link(kenh, u) if la_link else ""
        if not la_link:
            # ID trần: FB "<page>_<post>" hoặc số bài; Threads/IG là media id (số).
            if not id_hop_le(kenh, u):
                khong[u] = f"không phải ID bài {M.TEN[kenh]} hợp lệ (chỉ nhận chữ số)"
                continue
            mid = u if (kenh != "facebook" or "_" in u) else f"{page_id}_{u}"
            if kenh == "facebook" and not mid.startswith(page_id + "_"):
                khong[u] = "ID không thuộc Trang của kênh nhà (FB_PAGE_ID)"
                continue
            try:
                x = M.goi(kenh, _doan(mid), {"fields": _BAI[kenh][1]}, tok)
                bai.append({**_BAI[kenh][2](x), "dau_vao": u})
            except M.LoiKenh as e:
                khong[u] = f"không đọc được bài bằng token kênh nhà ({e.ma})"
            continue
        if kenh == "facebook" and ma.isdigit() and page_id:
            try:
                x = M.goi(kenh, _doan(f"{page_id}_{ma}"), {"fields": _F_FB_BAI}, tok)
                bai.append({**_bai_fb(x), "dau_vao": u})
                continue
            except M.LoiKenh:
                pass
        can_quet.append((u, ma))
    if can_quet:
        gan_day = _ds_bai(kenh, tok, _QUET_TIM_BAI, None, None, han)
        for u, ma in can_quet:
            k = next((b for b in gan_day
                      if (ma and (b["ma"] == ma or b["id"].endswith("_" + ma)
                                  or f"/{ma}" in b["link"]))
                      or _chuan_link(b["link"]) == _chuan_link(u)), None)
            if k:
                bai.append({**k, "dau_vao": u})
            else:
                khong[u] = (f"không thấy trong {len(gan_day)} bài gần nhất của kênh nhà — nếu "
                            f"là bài của người khác/đối thủ thì dùng social_deep_dive")
    return bai, khong


# ───────────────────────── bình luận ─────────────────────────
def _dong(kenh: str, bai: dict, id_: str, ten: str, text: str, likes, ts, cha: str,
          cua_kenh: bool, link: str = "") -> dict:
    return {"platform": kenh, "kenh": ten, "text": str(text or "")[:1000],
            "likes": likes, "replies": 0, "thoi_gian": _gio(ts), "tac_gia_thich": "",
            "link": link or bai["link"], "bai": bai["link"] or bai["id"], "id": id_,
            "cha": cha, "cua_kenh": cua_kenh}


def _bl_threads(tok: str, bai: dict, toi_da: int, han: float, toi: dict) -> tuple[list, bool]:
    raw, con = M.phan_trang("threads", f"{bai['id']}/conversation",
                            {"fields": _F_TH_BL, "reverse": "false"}, tok, toi_da, han)
    ra = []
    for x in raw:
        cha = str((x.get("replied_to") or {}).get("id") or "")
        ten = str(x.get("username") or "")
        ra.append(_dong("threads", bai, str(x.get("id") or ""), ten, x.get("text"), None,
                        x.get("timestamp"), "" if cha == bai["id"] else cha,
                        bool(x.get("is_reply_owned_by_me") or (ten and ten == toi.get("ten"))),
                        str(x.get("permalink") or "")))
    return ra, con


def _bl_instagram(tok: str, bai: dict, toi_da: int, han: float, toi: dict) -> tuple[list, bool]:
    raw, con = M.phan_trang("instagram", f"{bai['id']}/comments",
                            {"fields": _F_IG_BL, "limit": 50}, tok, toi_da, han)
    ra: list = []
    for x in raw:
        ten = str(x.get("username") or "")
        cid = str(x.get("id") or "")
        ra.append(_dong("instagram", bai, cid, ten, x.get("text"), x.get("like_count"),
                        x.get("timestamp"), "", bool(ten and ten == toi.get("ten"))))
        tl = x.get("replies") or {}
        ds = tl.get("data") or []
        # Trường lồng `replies{…}` chỉ trả trang đầu; còn trang sau thì đọc cả cạnh replies.
        if (tl.get("paging") or {}).get("next"):
            try:
                ds, _ = M.phan_trang("instagram", f"{cid}/replies",
                                     {"fields": _F_IG_TL, "limit": 50}, tok, toi_da, han)
            except M.LoiKenh as e:
                M.ghi_log(f"Instagram: đọc thêm trả lời của một bình luận hỏng — {e}")
        for r in ds:
            t2 = str(r.get("username") or "")
            ra.append(_dong("instagram", bai, str(r.get("id") or ""), t2, r.get("text"),
                            r.get("like_count"), r.get("timestamp"), cid,
                            bool(t2 and t2 == toi.get("ten"))))
        if len(ra) >= toi_da:
            return ra[:toi_da], True
    return ra, con


def _bl_facebook(tok: str, bai: dict, toi_da: int, han: float, toi: dict) -> tuple[list, bool]:
    raw, con = M.phan_trang("facebook", f"{bai['id']}/comments",
                            {"fields": _F_FB_BL, "filter": "stream", "order": "chronological",
                             "limit": 100}, tok, toi_da, han)
    ra = []
    for x in raw:
        tu = x.get("from") or {}
        ra.append(_dong("facebook", bai, str(x.get("id") or ""), str(tu.get("name") or ""),
                        x.get("message"), x.get("like_count"), x.get("created_time"),
                        str((x.get("parent") or {}).get("id") or ""),
                        bool(tu.get("id")) and str(tu.get("id")) == toi.get("id"),
                        str(x.get("permalink_url") or "")))
    return ra, con


_BL = {"threads": _bl_threads, "instagram": _bl_instagram, "facebook": _bl_facebook}


def _xep_cay(rows: list[dict]) -> list[dict]:
    """Gắn Cấp / Trả lời cho / số trả lời, rồi xếp mỗi trả lời ngay dưới bình luận cha."""
    theo_id = {r["id"]: r for r in rows if r["id"]}
    con: dict[str, list] = {}
    for r in rows:
        if r["cha"] and r["cha"] in theo_id:
            con.setdefault(r["cha"], []).append(r)
    for r in rows:
        r["replies"] = len(con.get(r["id"], []))
        cap, c, da = 1, r["cha"], set()
        while c and c not in da:
            da.add(c)
            cap += 1
            c = theo_id[c]["cha"] if c in theo_id else ""
        r["cap"] = cap
        cha = theo_id.get(r["cha"])
        r["tra_loi_cho"] = (cha["kenh"] if cha and cha["kenh"] else r["cha"]) \
            if r["cha"] else ""
    ra: list[dict] = []
    da_xep: set[int] = set()

    def xep(r):
        if id(r) in da_xep:
            return
        da_xep.add(id(r))
        ra.append(r)
        for c in con.get(r["id"], []):
            xep(c)
    for r in rows:
        if not r["cha"] or r["cha"] not in theo_id:
            xep(r)
    for r in rows:          # vòng lặp cha–con bất thường: không bỏ dòng nào
        xep(r)
    return ra


def _toi(kenh: str, tok: str) -> dict:
    """Danh tính kênh nhà: để nhận ra trả lời của chính shop."""
    if kenh == "facebook":
        pid = os.environ["FB_PAGE_ID"].strip()
        d = M.goi("facebook", pid, {"fields": "id,name"}, tok)
        return {"id": str(d.get("id") or pid), "ten": str(d.get("name") or "")}
    d = M.goi(kenh, "me", {"fields": "id,username"}, tok)
    return {"id": str(d.get("id") or ""), "ten": str(d.get("username") or "")}


def _cau_loi(kenh: str, e: M.LoiKenh) -> str:
    """Câu nói thẳng với người dùng cho lỗi kênh."""
    ten = M.TEN[kenh]
    if e.ma == "CHUA_NOI":
        return f"kênh {ten} chưa nối — chủ agent cần cấp token ({e})"
    if e.ma in ("HET_HAN", "TOKEN_HONG"):
        return f"kênh {ten}: token hết hạn hoặc không hợp lệ — chủ agent cần cấp lại ({e})"
    if e.ma == "QUYEN":
        return f"kênh {ten}: token thiếu quyền đọc bình luận — chủ agent cấp lại đủ quyền ({e})"
    if e.ma == "GIOI_HAN":
        return f"kênh {ten}: Meta đang giới hạn số lần gọi — thử lại sau ít phút ({e})"
    return f"kênh {ten}: lỗi khi đọc ({e})"


def _doc_kenh(kenh: str, bo: dict, han: float) -> dict:
    """Đọc MỘT kênh. Không bao giờ ném: lỗi nằm trong kết quả."""
    kq: dict = {"kenh": kenh, "bai": [], "rows": [], "khong_thay": {}, "loi": "", "ma": ""}
    try:
        tok = M.lay_token(kenh)
        toi = _toi(kenh, tok)
        kq["tai_khoan"] = toi.get("ten") or toi.get("id")
        if bo["bai"].get(kenh):
            bai, kq["khong_thay"] = _tim_bai(kenh, tok, bo["bai"][kenh], han)
        else:
            bai = _ds_bai(kenh, tok, bo["so_bai"], bo["tu"], bo["den"], han)
        for b in bai:
            b["bl"] = 0
            if time.monotonic() > han:
                b["trang_thai"] = "CHƯA ĐỌC — hết thời gian"
                kq["bai"].append(b)
                continue
            try:
                rows, con = _BL[kenh](tok, b, bo["max_bl"], han, toi)
            except M.LoiKenh as e:
                b["trang_thai"] = "LỖI: " + _cau_loi(kenh, e)
                kq["bai"].append(b)
                if e.ma in ("HET_HAN", "TOKEN_HONG", "GIOI_HAN"):
                    kq["loi"], kq["ma"] = _cau_loi(kenh, e), e.ma
                    break
                continue
            rows = _xep_cay(rows)
            b["bl"] = len(rows)
            b["trang_thai"] = (_HET_GIO if con and time.monotonic() > han
                               else _CHAM_TRAN if con else "OK")
            kq["bai"].append(b)
            kq["rows"] += rows
    except M.LoiKenh as e:
        kq["loi"], kq["ma"] = _cau_loi(kenh, e), e.ma
        if e.ma != "CHUA_NOI":
            M.ghi_log(f"{M.TEN[kenh]}: {kq['loi']}")
    except Exception as e:  # noqa: BLE001 — một kênh hỏng không kéo sập kênh khác
        kq["loi"] = M.che(f"kênh {M.TEN[kenh]}: lỗi {type(e).__name__}: {e}")[:300]
        kq["ma"] = "LOI"
        M.ghi_log(kq["loi"])
    return kq


# ───────────────────────── sheet ─────────────────────────
def _cap_chu(r: dict) -> str:
    return "bình luận" if r.get("cap", 1) <= 1 else f"trả lời cấp {r['cap']}"


def _o(r: dict) -> list:
    return [r["platform"], r["kenh"], r["text"],
            _KENH_NHA if r["cua_kenh"] else r.get("sac_thai", phan_loai.CHUA),
            "" if r["cua_kenh"] else r.get("chu_de", phan_loai.CHUA),
            "" if r["likes"] is None else r["likes"], r["replies"], r["thoi_gian"],
            r["tac_gia_thich"], r["bai"], _cap_chu(r), r.get("tra_loi_cho") or ""]


def _o_bai(kenh: str, b: dict) -> list:
    return [kenh, b["link"] or b["id"], b["ngay"], b["noi_dung"], b.get("bl", 0),
            "" if b.get("bao") is None else b["bao"], b.get("trang_thai", "")]


# ───────────────────────── tool ─────────────────────────
SCHEMA = {
    "name": TEN_TOOL,
    "description": (
        "ĐỌC ĐỦ BÌNH LUẬN TRÊN KÊNH CỦA CHÍNH HAPAS (Threads, Instagram, Trang Facebook) "
        "bằng API chính thức của Meta — MIỄN PHÍ, đủ mọi bình luận và trả lời lồng nhau. "
        "Lấy bài gần nhất của kênh (hoặc theo khoảng ngày, hoặc link/ID bài của HAPAS), kéo "
        "toàn bộ bình luận, TỰ GÁN NHÃN Sắc thái + Chủ đề, thống kê %, ghi Lark Sheet (tab "
        "'Thống kê', tab 'Bài đã đọc') và trả LINK. Dùng khi hỏi 'khách bình luận gì dưới bài "
        "của HAPAS', 'sentiment bài mới trên Threads/IG/Fanpage của mình'. Bài của ĐỐI THỦ/"
        "người khác thì KHÔNG dùng tool này — dùng `social_deep_dive`.\n"
        "GHI SHEET: gọi TRƯỚC với `chi_uoc_tinh`=true (miễn phí, không đọc gì), nêu phạm vi "
        "(kênh, số bài/khoảng ngày, số bình luận/bài) và kênh nào chưa nối, kết bằng "
        "\"Chạy nhé?\"; đồng ý mới gọi lại bỏ `chi_uoc_tinh`. Chi phí luôn 0 USD.\n"
        "KHI TRẢ LỜI: kênh có `loi` (chưa nối / token hết hạn) thì NÓI THẲNG câu đó — chủ "
        "agent cần cấp lại token; không lấy kênh khác hay `social_deep_dive` thay vào mà "
        "không nói. Số sentiment CHỈ lấy từ `thong_ke`/`dong_thong_ke`, nói đã phân loại "
        "`da_phan_loai`/`tong`; trả lời của chính kênh nhà KHÔNG tính vào thống kê. Bài có "
        "trạng thái 'CHẠM TRẦN' / 'CHƯA XONG' là chưa lấy hết — nói rõ. Threads không có số "
        "like của từng trả lời (cột Likes để trống). Gửi NGUYÊN `sheet_url`."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "kenh": {"type": "array", "items": {"type": "string",
                                                "enum": ["threads", "instagram", "facebook",
                                                         "all"]},
                     "description": "Kênh cần đọc. Bỏ trống hoặc 'all' = cả ba."},
            "so_bai": {"type": "integer", "description": (
                f"Số bài gần nhất MỖI kênh (mặc định {_MAC_DINH_BAI}, tối đa {_TOI_DA_BAI}).")},
            "tu_ngay": {"type": "string", "description": "Lọc bài đăng từ ngày (YYYY-MM-DD hoặc DD/MM)."},
            "den_ngay": {"type": "string", "description": "Lọc bài đăng tới ngày (YYYY-MM-DD hoặc DD/MM)."},
            "bai": {"type": "array", "items": {"type": "string"}, "description": (
                "Link (hoặc ID) bài CỦA HAPAS cần đọc. ID trần thì `kenh` phải là đúng một kênh.")},
            "max_comments": {"type": "integer", "description": (
                f"Bình luận tối đa MỖI bài, kể cả trả lời (mặc định {_MAC_DINH_BL}, tối đa "
                f"{_TOI_DA_BL}).")},
            "chi_uoc_tinh": {"type": "boolean", "description": (
                "true = CHỈ nêu phạm vi + kênh đã nối, không đọc gì. Gọi thế này trước.")},
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
        },
        "required": [],
    },
}


def _doc_tham_so(args: dict) -> tuple[dict | None, str]:
    kenh, la = _kenh_xin(args.get("kenh"))
    if la:
        return None, (f"Không nhận ra kênh {', '.join(la)}. Tool này chỉ đọc kênh HAPAS trên "
                      f"Threads, Instagram, Facebook. TikTok/YouTube/bài người khác → "
                      f"social_deep_dive.")
    tu = den = None
    try:
        if str(args.get("tu_ngay") or "").strip():
            tu = A._parse_date(str(args["tu_ngay"]), end=False)
        if str(args.get("den_ngay") or "").strip():
            den = A._parse_date(str(args["den_ngay"]), end=True)
    except ValueError as e:
        return None, str(e)
    bai: dict[str, list[str]] = {}
    for u in [str(x).strip() for x in (args.get("bai") or []) if str(x).strip()]:
        k = _kenh_cua_link(u)
        if k is None and ("/" in u or "." in u):
            return None, (f"Link {u} không phải Threads/Instagram/Facebook. Bài nền tảng khác "
                          f"→ social_deep_dive.")
        if k is None:
            if len(kenh) != 1:
                return None, f"ID bài trần '{u}' cần `kenh` là đúng MỘT kênh."
            k = kenh[0]
            if not id_hop_le(k, u):
                return None, (f"'{u}' không phải ID bài {M.TEN[k]} hợp lệ: ID bài chỉ gồm chữ "
                              f"số (Facebook có thể là <id Trang>_<id bài>). Gửi link bài "
                              f"hoặc đúng ID.")
        bai.setdefault(k, []).append(u)
    if bai:
        kenh = [k for k in M.KENH if k in bai]
    so_bai = _so(args.get("so_bai"), _MAC_DINH_BAI, 1, _TOI_DA_BAI)
    if (tu or den) and args.get("so_bai") in (None, ""):
        so_bai = _TOI_DA_BAI          # có khoảng ngày mà không nói số bài: lấy hết trong khoảng
    if sum(len(v) for v in bai.values()) > _TOI_DA_BAI:
        return None, f"Tối đa {_TOI_DA_BAI} bài mỗi lần."
    return {"kenh": kenh, "tu": tu, "den": den, "bai": bai, "so_bai": so_bai,
            "max_bl": _so(args.get("max_comments"), _MAC_DINH_BL, 1, _TOI_DA_BL)}, ""


def _pham_vi(bo: dict) -> str:
    phan = [", ".join(M.TEN[k] for k in bo["kenh"])]
    if bo["bai"]:
        phan.append(f"{sum(len(v) for v in bo['bai'].values())} bài chỉ định")
    else:
        phan.append(f"tối đa {bo['so_bai']} bài mới nhất mỗi kênh")
        if bo["tu"] or bo["den"]:
            phan.append(f"đăng {bo['tu']:%d/%m/%Y}" if bo["tu"] else "đăng")
            if bo["den"]:
                phan[-1] += f" tới {bo['den']:%d/%m/%Y}"
    phan.append(f"tối đa {bo['max_bl']} bình luận/bài (kể cả trả lời)")
    return " · ".join(phan)


def _handle(args: dict, **_kw) -> str:
    t0 = time.monotonic()
    bo, loi = _doc_tham_so(args)
    if bo is None:
        return tool_error(loi)
    tt = M.tinh_trang()
    chua_noi = {k: tt[k]["trang_thai"] for k in bo["kenh"] if not tt[k]["noi"]}
    pham_vi = _pham_vi(bo)
    if _co(args.get("chi_uoc_tinh")):
        return tool_result(
            success=True, chi_uoc_tinh=True, da_chay=False, pham_vi=pham_vi,
            kenh={k: tt[k]["trang_thai"] for k in bo["kenh"]}, chi_phi_usd=0,
            note=("CHƯA đọc gì. Nêu phạm vi, nói chi phí 0 USD (API chính thức của Meta), "
                  "kênh nào chưa nối thì nói thẳng (chủ agent cần cấp token), rồi kết bằng "
                  "\"Chạy nhé?\" và DỪNG. Đồng ý mới gọi lại bỏ `chi_uoc_tinh`."))
    if len(chua_noi) == len(bo["kenh"]):
        return tool_error(
            "Chưa đọc được: " + "; ".join(f"kênh {M.TEN[k]} chưa nối" for k in chua_noi)
            + ". Nói thẳng với người dùng: chủ agent cần cấp token Meta cho kênh đó (hướng "
              "dẫn docs/noi-kenh-nha-meta.md). Không thay bằng social_deep_dive mà không nói.")

    han = t0 + max(20.0, A._TOOL_DEADLINE - _DANH_CHO_SAU)
    chay = [k for k in bo["kenh"] if k not in chua_noi]
    with ThreadPoolExecutor(max_workers=len(chay)) as ex:
        futs = {ex.submit(_doc_kenh, k, bo, han): k for k in chay}
        wait(futs)
    kq = {futs[f]: f.result() for f in futs}

    per_kenh: dict[str, dict] = {}
    for k in bo["kenh"]:
        if k in chua_noi:
            per_kenh[k] = {"trang_thai": "CHƯA NỐI", "loi": f"kênh {M.TEN[k]} chưa nối — chủ "
                           f"agent cần cấp token ({chua_noi[k]})"}
            continue
        r = kq[k]
        per_kenh[k] = {"trang_thai": "LỖI" if r["loi"] else "OK", "loi": r["loi"] or None,
                       "tai_khoan": r.get("tai_khoan"), "so_bai": len(r["bai"]),
                       "so_binh_luan": len(r["rows"]),
                       "khong_tim_thay": r["khong_thay"] or None}
    rows = [x for k in chay for x in kq[k]["rows"]]
    bai = [(k, b) for k in chay for b in kq[k]["bai"]]
    per_bai = [{"kenh": k, "link": b["link"] or b["id"], "ngay": b["ngay"],
                "binh_luan": b.get("bl", 0), "nen_tang_bao": b.get("bao"),
                "trang_thai": b.get("trang_thai", "")} for k, b in bai]
    khach = [r for r in rows if not r["cua_kenh"]]
    so_loi = [k for k, v in per_kenh.items() if v["loi"]]
    chua_du = [p for p in per_bai if p["trang_thai"] != "OK"]
    base = dict(pham_vi=pham_vi, per_kenh=per_kenh, per_bai=per_bai, tong_comment=len(rows),
                binh_luan_cua_khach=len(khach), tra_loi_cua_kenh_nha=len(rows) - len(khach),
                chi_phi="0 USD — API chính thức của Meta, không dùng Apify.",
                kenh_loi=so_loi or None)
    canh_bao = ((" Kênh lỗi/chưa nối: " + "; ".join(per_kenh[k]["loi"] for k in so_loi)
                 + " — NÓI THẲNG, chủ agent cần cấp lại.") if so_loi else "") + (
        f" {len(chua_du)} bài chưa lấy hết (xem `per_bai[].trang_thai`) — nói rõ."
        if chua_du else "")
    if not rows:
        return tool_result(
            success=not so_loi, sheet_url=None, **base,
            note=("Không có bình luận nào trong phạm vi này (bài `trang_thai`='OK' với 0 "
                  "bình luận là bài thật sự chưa có bình luận). Không tạo sheet." + canh_bao))

    tt_pl: dict = {}
    if khach:
        han_pl = min(_PHAN_LOAI_TOI_DA, A._TOOL_DEADLINE - (time.monotonic() - t0) - 12)
        for r, (s, cd) in zip(khach, phan_loai.phan_loai_binh_luan(khach, han_pl, tt_pl)):
            r["sac_thai"], r["chu_de"] = s, cd
    tk = phan_loai.dem(khach, "bai")
    dong_tk = phan_loai.dong_thong_ke(tk)
    pl = {"trang_thai": tt_pl.get("trang_thai", ""), "da_phan_loai": tk["da_phan_loai"],
          "tong": tk["tong"], "ghi_chu": tt_pl.get("ghi_chu", "")}
    title = (str(args.get("title") or "").strip()
             or f"Bình luận kênh nhà · {'+'.join(M.TEN[k] for k in chay)} · "
                f"{datetime.datetime.now(A._VN_TZ):%d-%m %H%M}")
    values = [list(_HEADER)] + [_o(r) for r in rows]
    try:
        tok, url = A._create_sheet(title)
        sid = A._first_sheet_id(tok)
        A._write_values(tok, sid, values)
    except Exception as e:  # noqa: BLE001
        M.ghi_log(f"ghi sheet hỏng: {type(e).__name__}")
        return tool_result(
            success=False, sheet_url=None, **base, thong_ke=tk, dong_thong_ke=dong_tk,
            phan_loai=pl, trich_dan=phan_loai.trich_dan(khach),
            error=A._che_token(M.che(f"Lấy được {len(rows)} bình luận nhưng TẠO/GHI SHEET "
                                     f"THẤT BẠI: {type(e).__name__}: {e}")))
    try:
        thong_ke_o = D._ghi_thong_ke(tok, sid, len(values), tk)
    except Exception as e:  # noqa: BLE001
        thong_ke_o = f"KHÔNG ghi được ({type(e).__name__})"
    try:
        A._write_values(tok, A._them_tab(tok, _TAB_BAI),
                        [list(_HEADER_BAI)] + [_o_bai(k, b) for k, b in bai])
    except Exception as e:  # noqa: BLE001 — chỉ thiếu tab phụ
        M.ghi_log(f"không thêm được tab '{_TAB_BAI}': {type(e).__name__}")
    sender = memory_store.get_current_sender()
    granted = A._grant(tok, sender) if sender else False
    return tool_result(
        success=True, title=title, sheet_url=url, granted=granted, **base,
        thong_ke=tk, dong_thong_ke=dong_tk, phan_loai=pl, thong_ke_ghi_o=thong_ke_o,
        trich_dan=phan_loai.trich_dan(khach), giay=round(time.monotonic() - t0, 1),
        note=(f"Đã ghi {len(rows)} bình luận (đủ trả lời lồng nhau; {len(rows) - len(khach)} "
              f"trả lời của chính kênh nhà không gán nhãn, không tính thống kê) vào sheet "
              f"'{title}'; thống kê ở {thong_ke_o}. GỬI `sheet_url`. Số sentiment CHỈ lấy từ "
              f"`thong_ke`/`dong_thong_ke`, nói rõ đã phân loại {tk['da_phan_loai']}/"
              f"{tk['tong']}; dẫn lời thật từ `trich_dan`. Chi phí 0 USD." + canh_bao
              + ("" if granted else " CẢNH BÁO: chưa cấp được quyền tự động.")))


def _available() -> bool:
    """Luôn hiện tool: kênh chưa nối thì tool tự nói 'chưa nối', Mark không phải đoán."""
    return True


def register() -> None:
    try:
        registry.register(
            name=TEN_TOOL, toolset="social", schema=SCHEMA, handler=_handle,
            check_fn=_available, requires_env=[], is_async=False,
            description=("Đọc đủ bình luận trên kênh HAPAS (Threads/Instagram/Facebook) qua "
                         "API Meta, gán nhãn sắc thái, ghi Lark Sheet"),
            emoji="\U0001f3e0", override=True,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[kenh_nha_tool] register warning: {e}")


register()
# Không chạy luồng làm mới token trong bộ thử.
if "pytest" not in sys.modules:
    M.chay_luong_lam_moi()
