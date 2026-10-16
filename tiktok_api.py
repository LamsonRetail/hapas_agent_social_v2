"""TikTok qua API di động (`scraptik~tiktok-api`) + bảng chọn actor Apify cho từng việc.

Đo thật 16/10/2026 bằng tài khoản Apify MỚI (gói FREE), đầu vào giống nhau cho mọi ứng viên
(tìm "hapas"/"túi hapas", hồ sơ @hapas.official, bình luận 2 video HAPAS, Facebook hapasglobal).
Số liệu thô (đã bỏ token) ở `.pt/bench/` của máy đo.

TikTok — tìm theo từ khoá (USD mỗi 100 bài về):
  • scraptik (API, 0,002 USD/YÊU CẦU, 25–30 bài/yêu cầu): ~0,007. Lọc ngày PHÍA SERVER thật
    (`searchPosts_publishTime` 7/30/90/180 ngày): xin 7 ngày → 30/30 bài trong 7 ngày, 13/30
    trong 3 ngày. 24/25 bài VN, có follower, view, like, bình luận, share, ngôn ngữ, nước, cờ
    giỏ TikTok Shop (anchor "*shop*"). `searchPosts_count` > 30 trả 0 bài; sắp theo ngày
    (sortType 3) cắt còn 18 bài và hết trang — dùng sắp theo liên quan (0).
  • apidojo (đang dùng, 0,0003/bài): trần cứng 10 bài cho 2 từ khoá — 0,03 nhưng thiếu bài.
  • clockworks hashtag (dự phòng, 0,003/bài): 0,30, KHÔNG lọc ngày: 10/20 bài trong 30 ngày.
    Lượt 6 thật (16/10): 252 bài về, 39 trong cửa sổ 3 ngày → ~0,0197 USD mỗi bài dùng được,
    scraptik ~0,00015 (xin 7 ngày, 13/30 trong 3 ngày) — rẻ hơn ~130 lần.
  • Loại: dltik (0,008/bài — gấp 2,7 clockworks, tìm cần cookie phiên), sandaliaapps (phí
    khởi động 0,5 USD/lượt), clockworks~tiktok-scraper (đòi trần ≥ 0,5 USD/lượt).
TikTok — hồ sơ (@hapas.official, 20 bài): scraptik 1 yêu cầu hồ sơ + 1 yêu cầu/10 bài =
  0,006; clockworks-profile 0,06 và HỎNG: "Profile has no videos (or is behind a login wall)"
  (vẫn tính 1 kết quả). scraptik đọc được (644.816 follower, 2.537 video).
TikTok — bình luận (2 video, ~100/video):
  • scraptik: 50 bình luận gốc/yêu cầu (~0,0064 USD/100 gốc); trả lời 1 yêu cầu/luồng → cả
    trả lời ~0,04 USD/100. Video 131 bình luận: 94 gốc + 20 trả lời, đủ như các actor khác.
  • clockworks (đang dùng): 0,125/100. alien_force: 0,106/100. futurizerush: 0,04/100 NHƯNG
    2/2 lượt chỉ cào video ĐẦU rồi dừng ("Collection stopped…") — không dùng được cho lô.
  • scrapesmith~free-tiktok-comments-scraper: không tồn tại (404).
Facebook (giữ actor cũ — xem `CHON`):
  • Tìm từ khoá: scrapeforge gói Free nay 5 bài/lượt ("Free tier: up to 5 results per run"),
    hai lượt cách 4 phút đều trả 5 bài. easyapi: 0 bài, vẫn mất 0,094 USD phí khởi động.
    devninja: đòi TOÀN QUYỀN tài khoản Apify — loại vì an toàn. curious_coder: tìm cần cookie.
  • Bài của trang (20 bài): apify 0,101 (có view video, hợp tác); scraper_one 0,0525;
    curious_coder 0,035 — cả ba cùng 20 bài, cùng like/bình luận/share nhưng hai actor rẻ
    KHÔNG có lượt xem video (7/20 bài là video, 6.928–336.223 view) → giữ apify.
  • Bình luận: apify 0,25/100 (60/60); danek 0,20/100 nhưng gói Free chỉ 25 bình luận/lượt
    (log actor) → giữ apify.

Cách dùng: mỗi yêu cầu API là MỘT run Apify (~2–8 giây) qua `apify_tool._call` — trần, hạn
chót, huỷ, sổ run (`_SO_RUN`, `_KHI_CO_RUN`) giữ nguyên kỷ luật cũ. Trang tiếp theo phụ thuộc
con trỏ trang trước nên trong MỘT từ khoá / tài khoản / video chạy tuần tự; khác nhau thì song
song (gói Free cho 5 run cùng lúc, `_CHO_APIFY` đã chặn). Item trả về được đổi sang ĐÚNG shape
của actor clockworks tương ứng để bộ đọc cũ (`_chuan_clockworks`, `account_tool._doc_tiktok`,
`deep_dive_tool._map_tiktok`) dùng nguyên.
"""
from __future__ import annotations

import contextvars
import datetime
import math
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import apify_tool as A

ACTOR = "scraptik~tiktok-api"
NHAN = "TikTok API (scraptik)"
GIA_YEU_CAU = 0.002          # USD mỗi yêu cầu (sự kiện "request"), không phí khởi động
TIM_MOI_TRANG = 30           # searchPosts_count tối đa thật sự trả bài (50 → 0 bài)
BAI_MOI_TRANG = 10           # userPosts trả 10 bài/yêu cầu dù xin 30
BL_MOI_TRANG = 50
TRA_LOI_MOI_TRANG = 50
_TRAN_LUOT = 0.1             # trần USD gửi Apify cho MỘT yêu cầu (sàn của `_run_actor`)
_MOC_NGAY = (7, 30, 90, 180)  # searchPosts_publishTime; 1 ("hôm qua") bỏ — chỉ ra 8 bài
_SONG_SONG = 3               # video/tài khoản chạy song song (chừa chỗ cho việc khác)

# ── Bảng chọn actor: MỘT chỗ quyết định nguồn chính + dự phòng cho từng việc ──
# "chinh" = SCRAPTIK nghĩa là đi qua bộ chuyển ở module này; "du_phong" chạy khi nguồn chính
# lỗi hoặc không trả gì (tên actor cũ giữ nguyên ở `_ACTORS` của từng module).
CHON = {
    "tiktok_tim": {"chinh": ACTOR,
                   "du_phong": ("apidojo~tiktok-scraper", "clockworks~tiktok-hashtag-scraper")},
    "tiktok_ho_so": {"chinh": ACTOR, "du_phong": ("clockworks~tiktok-profile-scraper",)},
    "tiktok_binh_luan": {"chinh": ACTOR, "du_phong": ("clockworks~tiktok-comments-scraper",)},
    "tiktok_so_bai": {"chinh": ACTOR, "du_phong": ()},
    "facebook_tim": {"chinh": "scrapeforge~facebook-search-posts", "du_phong": ()},
    "facebook_trang": {"chinh": "apify~facebook-posts-scraper", "du_phong": ()},
    "facebook_binh_luan": {"chinh": "apify~facebook-comments-scraper", "du_phong": ()},
}


def dung_api(viec: str) -> bool:
    """Việc này đang đi qua TikTok API (scraptik) không."""
    return (CHON.get(viec) or {}).get("chinh") == ACTOR


class _Ngan:
    """Đếm yêu cầu của một lượt gọi; hết trần USD thì không gửi thêm (an toàn luồng)."""

    def __init__(self, tran_usd: float | None):
        self.toi_da = (10 ** 6 if tran_usd is None
                       else max(0, math.floor(float(tran_usd) / GIA_YEU_CAU + 1e-9)))
        self.da = 0
        self._k = threading.Lock()

    def xin(self) -> bool:
        with self._k:
            if self.da >= self.toi_da:
                return False
            self.da += 1
            return True

    @property
    def usd(self) -> float:
        return round(self.da * GIA_YEU_CAU, 4)


def _goi(payload: dict, ngan: _Ngan) -> dict | None:
    """MỘT yêu cầu API = một run. None khi đã chạm trần của lượt (không gửi)."""
    if not ngan.xin():
        return None
    items = A._call(ACTOR, payload, 1, tran_usd=_TRAN_LUOT)
    it = items[0] if items else None
    if not isinstance(it, dict):
        raise A.LoiApify("LOI", "TikTok API không trả dữ liệu cho yêu cầu này.")
    if it.get("status_code") not in (0, None):
        raise A.LoiApify("LOI", f"TikTok API báo lỗi (status_code={it.get('status_code')}, "
                                f"{str(it.get('status_msg') or '')[:120]}).")
    return it


def _iso(ts) -> str | None:
    try:
        return datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _so(v):
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _tac_gia(au: dict) -> dict:
    """`author`/`user` của API → `authorMeta` kiểu clockworks."""
    return {"id": au.get("uid"), "name": au.get("unique_id") or "",
            "nickName": au.get("nickname") or "", "fans": _so(au.get("follower_count")),
            "heart": _so(au.get("total_favorited")), "video": _so(au.get("aweme_count")),
            "verified": bool(au.get("verification_type") or au.get("custom_verify")
                             or au.get("enterprise_verify_reason"))}


def _gio_hang(a: dict) -> bool | None:
    """Cờ giỏ TikTok Shop: anchor "anchor_complex_shop"/"anchor_shop" (đo 16/10: 25/30 bài tìm
    "hapas" có). Thiếu hẳn trường `anchors` thì None — không đoán thành "viral"."""
    an = a.get("anchors")
    if not isinstance(an, list):
        return None
    return any("shop" in str((x or {}).get("component_key") or "") for x in an
               if isinstance(x, dict))


def video(a: dict) -> dict:
    """`aweme_info`/`aweme_detail` của API → item kiểu clockworks (hashtag/profile scraper)."""
    au = a.get("author") or {}
    st = a.get("statistics") or {}
    ten = str(au.get("unique_id") or "")
    vid = str(a.get("aweme_id") or "")
    return {
        "id": vid, "text": str(a.get("desc") or ""), "createTimeISO": _iso(a.get("create_time")),
        "authorMeta": _tac_gia(au),
        "playCount": _so(st.get("play_count")), "diggCount": _so(st.get("digg_count")),
        "commentCount": _so(st.get("comment_count")), "shareCount": _so(st.get("share_count")),
        "collectCount": _so(st.get("collect_count")),
        "hashtags": [{"name": t["hashtag_name"]} for t in a.get("text_extra") or []
                     if isinstance(t, dict) and t.get("hashtag_name")],
        "webVideoUrl": f"https://www.tiktok.com/@{ten}/video/{vid}" if ten and vid else "",
        "textLanguage": a.get("desc_language"), "region": a.get("region"),
        "hasTikTokShopProduct": _gio_hang(a), "isAd": bool(a.get("is_ads")),
        "isPinned": bool(a.get("is_top")),
        "musicMeta": {"musicName": (a.get("music") or {}).get("title") or ""},
        "_nguon": NHAN,
    }


def binh_luan_dong(c: dict, url: str) -> dict:
    """Một bình luận của API → item kiểu clockworks~tiktok-comments-scraper."""
    u = c.get("user") or {}
    cha = str(c.get("reply_id") or "")
    return {
        "cid": str(c.get("cid") or ""), "text": str(c.get("text") or ""),
        "diggCount": _so(c.get("digg_count")) or 0,
        "replyCommentTotal": _so(c.get("reply_comment_total")) or 0,
        "createTimeISO": _iso(c.get("create_time")), "uniqueId": u.get("unique_id") or "",
        "uid": u.get("uid"), "videoWebUrl": url, "submittedVideoUrl": url,
        "repliesToId": cha if cha and cha != "0" else None,
        "likedByAuthor": bool(c.get("is_author_digged")),
        "pinnedByAuthor": bool(c.get("author_pin")), "_nguon": NHAN,
    }


def moc_ngay(d_from: datetime.datetime | None, d_to: datetime.datetime | None = None) -> int:
    """Bộ lọc ngày phía server nhỏ nhất PHỦ được `d_from` (0 = mọi lúc)."""
    if d_from is None:
        return 0
    den = d_to or datetime.datetime.now(d_from.tzinfo)
    ngay = (den - d_from).total_seconds() / 86400
    for m in _MOC_NGAY:
        if ngay <= m:
            return m
    return 0


def _song_song(fn, cac: list) -> list:
    """`fn(x)` cho từng x, tối đa `_SONG_SONG` luồng, mỗi luồng một bản sao contextvars."""
    if len(cac) <= 1:
        return [fn(x) for x in cac]
    # Bản sao ngữ cảnh lấy ở LUỒNG GỌI (hạn chót, cờ huỷ, sổ run, móc ghi run id) — chép trong
    # luồng con thì chỉ được ngữ cảnh rỗng của luồng con.
    cac_ctx = [(contextvars.copy_context(), x) for x in cac]
    with ThreadPoolExecutor(max_workers=min(_SONG_SONG, len(cac))) as ex:
        return list(ex.map(lambda cx: cx[0].run(fn, cx[1]), cac_ctx))


# ───────────────────────────── tìm theo từ khoá ─────────────────────────────
def tim(q: list[str], limit: int, d_from=None, d_to=None, vung: str = "VN",
        tran_usd: float | None = None) -> list[dict]:
    """Bài TikTok theo từ khoá (item kiểu clockworks). Mỗi từ khoá xin ~`limit`/số từ bài
    TRONG `d_from`..: lật trang (30 bài/yêu cầu) tới đủ, hết trang, hoặc tối đa
    2×(trang cần)+1 trang. Trả MỌI bài đã trả tiền (kể cả ngoài `d_from` — bên gọi tự lọc:
    `/theodoi` dùng chúng để cập nhật số liệu bài đã biết). Lỗi một từ khoá không làm hỏng từ
    khác; mọi từ khoá đều lỗi thì ném lỗi cuối."""
    q = A._bo_trung_tu_khoa(q)
    if not q or limit <= 0:
        return []
    per = max(1, math.ceil(limit / len(q)))
    moc = moc_ngay(d_from, d_to)
    ngan = _Ngan(tran_usd)
    loi: list[Exception] = []

    def mot(kw: str) -> list[dict]:
        try:
            return _tim_mot(kw, per, moc, (vung or "VN").upper(), d_from, ngan)
        except A.LoiApify as e:
            loi.append(e)
            if e.ma in ("HET_TIEN_THANG", "DA_HUY"):
                raise
            return []

    ra, thay = [], set()
    for ds in _song_song(mot, q):
        for v in ds:
            if v["id"] not in thay:
                thay.add(v["id"])
                ra.append(v)
    if not ra and loi:
        raise loi[-1]
    return ra


def _tim_mot(kw: str, per: int, moc: int, vung: str, d_from, ngan: _Ngan) -> list[dict]:
    ra: list[dict] = []
    thay: set[str] = set()
    trong = 0
    off = 0
    for _ in range(2 * math.ceil(per / TIM_MOI_TRANG) + 1):
        it = _goi({"searchPosts_keyword": kw, "searchPosts_count": TIM_MOI_TRANG,
                   "searchPosts_offset": off, "searchPosts_region": vung,
                   "searchPosts_publishTime": moc, "searchPosts_sortType": 0}, ngan)
        if it is None:
            break
        moi = 0
        for x in it.get("search_item_list") or []:
            a = (x or {}).get("aweme_info") if isinstance(x, dict) else None
            if not isinstance(a, dict) or not a.get("aweme_id"):
                continue
            v = video(a)
            if v["id"] in thay:
                continue
            thay.add(v["id"])
            moi += 1
            ra.append(v)
            dt = A._to_vn(v["createTimeISO"])
            trong += bool(d_from is None or (dt and dt >= d_from))
        # Trang sau chồng trang trước ~20% (thứ tự liên quan xê dịch) — trang không có bài mới
        # là đã hết.
        if trong >= per or not it.get("has_more") or not moi:
            break
        off = max(off + TIM_MOI_TRANG, _so(it.get("cursor")) or 0)
    return ra


# ───────────────────────────── hồ sơ tài khoản ─────────────────────────────
def ho_so(ten: list[str], n: int, tran_usd: float | None = None) -> list[dict]:
    """Bài MỚI NHẤT của từng tài khoản (item kiểu clockworks~tiktok-profile-scraper, bỏ bài
    ghim như `excludePinnedPosts`). Không đọc được thì một item {"input", "note"} như actor
    cũ (`account_tool._doc_tiktok` ghi thành ghi chú của nguồn)."""
    ngan = _Ngan(tran_usd)
    return [x for ds in _song_song(lambda t: _ho_so_mot(t, n, ngan),
                                    [str(t).lstrip("@") for t in ten if str(t).strip()])
            for x in ds]


def _ho_so_mot(ten: str, n: int, ngan: _Ngan) -> list[dict]:
    try:
        it = _goi({"profile_username": ten, "profile_region": "VN"}, ngan)
    except A.LoiApify as e:
        if e.ma in ("HET_TIEN_THANG", "DA_HUY"):
            raise
        return [{"input": ten, "note": f"TikTok API: {e}"[:200]}]
    u = (it or {}).get("user") or {}
    if not u.get("uid"):
        return [{"input": ten, "note": "TikTok API không thấy tài khoản này"
                 if it is not None else "chạm trần chi phí của lượt"}]
    am = _tac_gia(u)
    bai: list[dict] = []
    con_tro = "0"
    for _ in range(math.ceil(max(1, n) / BAI_MOI_TRANG) + 1):
        try:
            it = _goi({"userPosts_userId": str(u["uid"]),
                       "userPosts_secUserId": str(u.get("sec_uid") or ""),
                       "userPosts_count": BAI_MOI_TRANG, "userPosts_region": "VN",
                       "userPosts_maxCursor": con_tro}, ngan)
        except A.LoiApify as e:
            if e.ma in ("HET_TIEN_THANG", "DA_HUY") or not bai:
                raise
            break
        if it is None:
            break
        for a in it.get("aweme_list") or []:
            if isinstance(a, dict) and a.get("aweme_id") and not a.get("is_top"):
                v = video(a)
                v.update(authorMeta=am, input=ten)
                bai.append(v)
        con_tro = str(it.get("max_cursor") or "")
        if len(bai) >= n or not it.get("has_more") or not con_tro:
            break
    if not bai:
        return [{"input": ten, "authorMeta": am,
                 "note": "Tài khoản chưa có video công khai (TikTok API)"}]
    return bai[:n]


# ───────────────────────────── bình luận ─────────────────────────────
_ID_VIDEO = re.compile(r"/(?:video|photo)/(\d{8,})")


def id_video(url: str) -> str | None:
    m = _ID_VIDEO.search(url or "")
    return m.group(1) if m else None


def binh_luan(urls: list[str], per: int, tra_loi: int = 20,
              tran_usd: float | None = None) -> list[dict]:
    """Bình luận của từng video (item kiểu clockworks~tiktok-comments-scraper). Mỗi video tối
    đa `per` dòng (gốc + trả lời, như `maxItems` = per × số bài của actor cũ): bình luận gốc
    trước (50/yêu cầu), rồi trả lời của các luồng nhiều trả lời nhất (tối đa `tra_loi` mỗi
    luồng, 1 yêu cầu/luồng). Link không bóc được id video (link rút gọn) thì bỏ qua — bên gọi
    chạy dự phòng cho bài thiếu."""
    ngan = _Ngan(tran_usd)
    cac = [(u, id_video(u)) for u in urls]
    ra = _song_song(lambda x: _bl_mot(x[0], x[1], per, tra_loi, ngan) if x[1] else [], cac)
    return [r for ds in ra for r in ds]


def _bl_mot(url: str, vid: str, per: int, tra_loi: int, ngan: _Ngan) -> list[dict]:
    goc: list[dict] = []
    thay: set[str] = set()
    con_tro = 0
    try:
        for _ in range(math.ceil(max(1, per) / BL_MOI_TRANG) + 2):
            it = _goi({"listComments_awemeId": vid, "listComments_count": BL_MOI_TRANG,
                       "listComments_cursor": con_tro}, ngan)
            if it is None:
                break
            moi = 0
            for c in it.get("comments") or []:
                if isinstance(c, dict) and c.get("cid") and str(c["cid"]) not in thay:
                    thay.add(str(c["cid"]))
                    goc.append(binh_luan_dong(c, url))
                    moi += 1
            if len(goc) >= per or not it.get("has_more") or not moi:
                break
            con_tro = max(con_tro + BL_MOI_TRANG, _so(it.get("cursor")) or 0)
    except A.LoiApify as e:
        if e.ma in ("HET_TIEN_THANG", "DA_HUY") or not goc:
            raise
    goc = goc[:per]
    ra = list(goc)
    if tra_loi > 0:
        for c in sorted((c for c in goc if c["replyCommentTotal"] > 0),
                        key=lambda c: -c["replyCommentTotal"]):
            if len(ra) >= per:
                break
            try:
                it = _goi({"commentReplies_commentId": c["cid"], "commentReplies_awemeId": vid,
                           "commentReplies_count": min(TRA_LOI_MOI_TRANG, tra_loi)}, ngan)
            except A.LoiApify as e:
                if e.ma in ("HET_TIEN_THANG", "DA_HUY"):
                    raise
                break
            if it is None:
                break
            for r in (it.get("comments") or [])[:tra_loi]:
                if isinstance(r, dict) and r.get("cid") and str(r["cid"]) not in thay \
                        and len(ra) < per:
                    thay.add(str(r["cid"]))
                    d = binh_luan_dong(r, url)
                    d["repliesToId"] = d["repliesToId"] or c["cid"]
                    ra.append(d)
    return ra


# ───────────────────────────── số liệu theo link bài ─────────────────────────────
def so_lieu_bai(urls: list[str], tran_usd: float | None = None) -> list[dict]:
    """Số liệu MỚI của từng video theo link (1 yêu cầu/video, 0,002 USD — rẻ hơn
    clockworks~tiktok-video-scraper 0,003). Video lỗi/xoá thì bỏ qua."""
    ngan = _Ngan(tran_usd)

    def mot(u: str) -> list[dict]:
        vid = id_video(u)
        if not vid:
            return []
        try:
            it = _goi({"post_awemeId": vid, "post_region": "VN"}, ngan)
        except A.LoiApify as e:
            if e.ma in ("HET_TIEN_THANG", "DA_HUY"):
                raise
            return []
        a = (it or {}).get("aweme_detail")
        return [video(a)] if isinstance(a, dict) and a.get("aweme_id") else []
    return [x for ds in _song_song(mot, list(dict.fromkeys(urls))) for x in ds]


def so_yeu_cau_tim(so_tu: int, per: int) -> int:
    """Số yêu cầu TỐI ĐA một lượt tìm (`so_tu` từ khoá, ~`per` bài mỗi từ) — cho ước tính."""
    return so_tu * (2 * math.ceil(max(1, per) / TIM_MOI_TRANG) + 1) if so_tu and per > 0 else 0
