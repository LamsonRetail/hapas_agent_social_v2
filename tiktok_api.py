"""TikTok qua API di động (`scraptik~tiktok-api`) + bảng chọn actor Apify cho từng việc.

Đo thật 16/10/2026 bằng tài khoản Apify MỚI (gói FREE), đầu vào giống nhau cho mọi ứng viên
(tìm "hapas"/"túi hapas", hồ sơ @hapas.official, bình luận 2 video HAPAS, Facebook hapasglobal).
Số liệu thô (đã bỏ token) ở `.pt/bench/` của máy đo.

TikTok — tìm theo từ khoá (USD mỗi 100 bài về):
  • scraptik (API, 0,002 USD/YÊU CẦU, 25–30 bài/yêu cầu): ~0,007. Lọc ngày PHÍA SERVER thật
    (`searchPosts_publishTime` 7/30/90/180 ngày): xin 7 ngày → 30/30 bài trong 7 ngày, 13/30
    trong 3 ngày. 24/25 bài VN, có follower, view, like, bình luận, share, ngôn ngữ, nước, cờ
    giỏ TikTok Shop (anchor "*shop*"). `searchPosts_count` > 30 trả 0 bài; sắp theo ngày
    (sortType 3) với bộ lọc 7 ngày cắt còn 18–26 bài và hết trang — lượt thường dùng sắp theo
    liên quan (0); trang "mới nhất" (17/10) dùng sortType 3 với bộ lọc 30 ngày (lật được).
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
# USD mỗi yêu cầu = giá bảng (sự kiện "request", không phí khởi động, `pricingInfos` từ
# 01/01/2026). Đo lại 18/10/2026 theo TỪNG RUN (`usageTotalUsd` đọc sau ≥ 12 giờ, hết phí ghi trễ):
# 14/14 run scraptik của tài khoản FREE mới đều 0,0020 USD, `chargedEventCounts` {"request": 1};
# Σ 97 run của chu kỳ 4,5756 so với mức tài khoản 4,5819 (lệch 0,006 = lưu trữ, không phải phí
# mỗi run). Số 0,0023–0,0034 đo 17/10 là CHÊNH MỨC TÀI KHOẢN trước/sau trong lúc agent khác chạy
# actor Threads song song (0,155 USD/run) — không phải giá một yêu cầu. Dùng 0,003 thì ước tính,
# trần đếm yêu cầu (`_Ngan`) và sổ đều lố 50%: kiểm độ phủ 0,20 USD chỉ gửi 58 thay vì 100 yêu cầu.
GIA_YEU_CAU = 0.002
TIM_MOI_TRANG = 30           # searchPosts_count tối đa thật sự trả bài (50 → 0 bài)
BAI_MOI_TRANG = 10           # userPosts trả 10 bài/yêu cầu dù xin 30


def so_yeu_cau_ho_so(n: int) -> int:
    """Số yêu cầu TỐI ĐA đọc `n` bài mới nhất của MỘT tài khoản (`_ho_so_mot`): 1 hồ sơ + ⌈n/10⌉
    trang + 1 trang bù bài ghim (bỏ `is_top`). @hapas.official 20 bài: 4 yêu cầu = 0,008 USD
    (ước tính cũ 20 bài × 0,0012 × 1,3 = 0,031 — lố 4 lần)."""
    return 2 + math.ceil(max(1, int(n)) / BAI_MOI_TRANG)
BL_MOI_TRANG = 50
TRA_LOI_MOI_TRANG = 50
_TRAN_LUOT = 0.1             # trần USD gửi Apify cho MỘT yêu cầu (sàn của `_run_actor`)
_MOC_NGAY = (7, 30, 90, 180)  # searchPosts_publishTime; 1 ("hôm qua") bỏ — chỉ ra 8 bài
#: `searchPosts_sortType` (input schema scraptik): 0 = liên quan, 1 = nhiều thích nhất, 3 = ngày.
#: Đo 17/10/2026 (21 từ khoá HAPAS, 30 ngày, 1 trang/từ, cùng 0,042 USD): "nhiều thích" bắt
#: 12/14 nhà sáng tạo top thảo luận của Kompa (90% số thảo luận), "liên quan" chỉ 9/14 (53%).
#: Mỗi câu tìm chỉ lật được ~3–4 trang (≈ 80–110 bài) dù sắp kiểu nào — không thể "lật hết".
SAP_LIEN_QUAN = 0
SAP_NHIEU_THICH = 1
#: Sắp "mới nhất" (sortType 3). Đo 17/10/2026 ("hapas", "túi hapas", bộ lọc 30 ngày): feed sắp
#: ĐÚNG theo giờ đăng giảm dần, ~97% bài nhắc brand, lật được 3–4 trang; bắt 50/497 bài brand
#: 30 ngày mà liên quan + nhiều thích + feed hashtag đều sót (độ phủ 89,7% → 99,8%). Đo lại cấu
#: hình hằng ngày (cùng ngày, 2 từ): một trang mới nhất thêm 31 bài brand ngoài lượt thường + lượt
#: nổi (hợp 191 bài: thường + nổi chỉ 83–84%). Bộ lọc 7 ngày + sortType 3 cắt còn 26 bài, hết
#: trang (và trùng trang 30 ngày chỉ 16/26) — dùng bộ lọc 30 ngày (`MOI_NHAT_MOC_NGAY`).
#: Dùng cho trang "mới nhất" hằng ngày (`tim_moi_nhat`, `theo_doi_api.tim_moi_tiktok`).
SAP_MOI_NHAT = 3
_SONG_SONG = 3              # video/tài khoản chạy song song (chừa chỗ cho việc khác)

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
    # Theo dõi trang Facebook của `/theodoi` (17/10/2026, `theo_doi_api.FB_TRANG`): thedoor rẻ nửa
    # giá, có view video; actor cũ làm dự phòng. `soi_tai_khoan` vẫn `facebook_trang` ở trên.
    "facebook_theo_doi": {"chinh": "thedoor~facebook-page-scraper",
                          "du_phong": ("apify~facebook-posts-scraper",)},
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
        self.dung: str | None = None     # mã lỗi dừng cả lượt (hết tiền / huỷ) đã gặp
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
        tran_usd: float | None = None, sap: int = SAP_LIEN_QUAN,
        trang_toi_da: int | None = None) -> list[dict]:
    """Bài TikTok theo từ khoá (item kiểu clockworks). Mỗi từ khoá xin ~`limit`/số từ bài
    TRONG `d_from`..: lật trang (30 bài/yêu cầu) tới đủ, hết trang, hoặc tối đa
    2×(trang cần)+1 trang. Trả MỌI bài đã trả tiền (kể cả ngoài `d_from` — bên gọi tự lọc:
    `/theodoi` dùng chúng để cập nhật số liệu bài đã biết). Lỗi một từ khoá không làm hỏng từ
    khác; mọi từ khoá đều lỗi thì ném lỗi cuối.

    `sap`: thứ tự của TikTok (`SAP_LIEN_QUAN` mặc định, `SAP_NHIEU_THICH` cho lượt nổi —
    `theo_doi_api.tim_noi_tiktok`); `trang_toi_da`: trần trang MỖI từ khoá (None = theo `limit`)."""
    q = A._bo_trung_tu_khoa(q)
    if not q or limit <= 0:
        return []
    per = max(1, math.ceil(limit / len(q)))
    moc = moc_ngay(d_from, d_to)
    ngan = _Ngan(tran_usd)
    loi: list[Exception] = []

    def mot(kw: str) -> list[dict]:
        try:
            return _tim_mot(kw, per, moc, (vung or "VN").upper(), d_from, ngan, sap,
                            trang_toi_da)
        except A.LoiApify as e:
            loi.append(e)
            if e.ma in _DUNG_HAN:
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


def _tim_mot(kw: str, per: int, moc: int, vung: str, d_from, ngan: _Ngan,
             sap: int = 0, trang_toi_da: int | None = None) -> list[dict]:
    ra: list[dict] = []
    thay: set[str] = set()
    trong = 0
    off = 0
    so_trang = 2 * math.ceil(per / TIM_MOI_TRANG) + 1
    if trang_toi_da is not None:
        so_trang = min(so_trang, max(0, int(trang_toi_da)))
    for _ in range(so_trang):
        try:
            it = _goi({"searchPosts_keyword": kw, "searchPosts_count": TIM_MOI_TRANG,
                       "searchPosts_offset": off, "searchPosts_region": vung,
                       "searchPosts_publishTime": moc, "searchPosts_sortType": sap}, ngan)
        except A.LoiApify as e:
            # Review 16/10: trang sau lỗi thì GIỮ các trang trước (đã trả tiền).
            if e.ma in _DUNG_HAN or not ra:
                raise
            break
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


# Lỗi làm dừng CẢ lượt (không phải lỗi riêng một tài khoản / video / từ khoá).
_DUNG_HAN = ("HET_TIEN_THANG", "DA_HUY")


def _ghi_loi(loi_ra: list | None, khoa: str, e: Exception) -> None:
    if loi_ra is not None:
        loi_ra.append((khoa, getattr(e, "ma", "LOI"), str(e)[:200]))


# ───────────────────────────── hồ sơ tài khoản ─────────────────────────────
def ho_so(ten: list[str], n: int, tran_usd: float | None = None,
          loi_ra: list | None = None) -> list[dict]:
    """Bài MỚI NHẤT của từng tài khoản (item kiểu clockworks~tiktok-profile-scraper, bỏ bài
    ghim như `excludePinnedPosts`). Không đọc được thì một item {"input", "note"} như actor
    cũ (`account_tool._doc_tiktok` ghi thành ghi chú của nguồn). Lỗi API của MỘT tài khoản
    không ném ra (review 16/10: ném là bỏ cả lô): ghi `(tên, mã, lý do)` vào `loi_ra` — bên
    gọi chỉ chạy dự phòng cho đúng các tài khoản đó. Tài khoản đọc được mà KHÔNG có video thì
    không phải lỗi (không chạy dự phòng mỗi lượt)."""
    ngan = _Ngan(tran_usd)
    return [x for ds in _song_song(lambda t: _ho_so_mot(t, n, ngan, loi_ra),
                                    [str(t).lstrip("@") for t in ten if str(t).strip()])
            for x in ds]


def _ho_so_mot(ten: str, n: int, ngan: _Ngan, loi_ra: list | None = None) -> list[dict]:
    try:
        it = _goi({"profile_username": ten, "profile_region": "VN"}, ngan)
    except A.LoiApify as e:
        if e.ma in _DUNG_HAN:
            raise
        _ghi_loi(loi_ra, ten, e)
        return [{"input": ten, "note": f"TikTok API: {e}"[:200]}]
    u = (it or {}).get("user") or {}
    if not u.get("uid"):
        # Không thấy tài khoản: actor cũ có thể vẫn đọc được → ghi lỗi để chạy dự phòng (khác
        # tài khoản ĐỌC ĐƯỢC mà 0 video — không phải lỗi).
        _ghi_loi(loi_ra, ten, A.LoiApify("NGAN_SACH", "chạm trần chi phí của lượt")
                 if it is None else A.LoiApify("KHONG_THAY", "TikTok API không thấy tài khoản"))
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
            if e.ma in _DUNG_HAN:
                raise
            if not bai:
                _ghi_loi(loi_ra, ten, e)
                return [{"input": ten, "authorMeta": am, "note": f"TikTok API: {e}"[:200]}]
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
              tran_usd: float | None = None, loi_ra: list | None = None) -> list[dict]:
    """Bình luận của từng video (item kiểu clockworks~tiktok-comments-scraper). Mỗi video tối
    đa `per` dòng (gốc + trả lời, như `maxItems` = per × số bài của actor cũ): bình luận gốc
    trước (50/yêu cầu), rồi trả lời của các luồng nhiều trả lời nhất (tối đa `tra_loi` mỗi
    luồng, 1 yêu cầu/luồng). Link không bóc được id video (link rút gọn) và video lỗi API ghi
    vào `loi_ra` (không ném — review 16/10) — bên gọi chạy dự phòng cho đúng các video đó.
    Video đọc được mà 0 bình luận KHÔNG phải lỗi."""
    ngan = _Ngan(tran_usd)
    cac = [(u, id_video(u)) for u in urls]
    for u, vid in cac:
        if not vid:
            _ghi_loi(loi_ra, u, A.LoiApify("LOI", "link không có id video (link rút gọn?)"))
    ra = _song_song(lambda x: _bl_mot(x[0], x[1], per, tra_loi, ngan, loi_ra) if x[1] else [],
                    cac)
    return [r for ds in ra for r in ds]


def _bl_mot(url: str, vid: str, per: int, tra_loi: int, ngan: _Ngan,
            loi_ra: list | None = None) -> list[dict]:
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
        if e.ma in _DUNG_HAN:
            raise
        if not goc:
            _ghi_loi(loi_ra, url, e)
            return []
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
                if e.ma in _DUNG_HAN:
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
            if e.ma in _DUNG_HAN:
                raise
            return []
        a = (it or {}).get("aweme_detail")
        return [video(a)] if isinstance(a, dict) and a.get("aweme_id") else []
    return [x for ds in _song_song(mot, list(dict.fromkeys(urls))) for x in ds]


# ───────────────── hashtag + bài mới nhất của tài khoản (kiểm độ phủ, 17/10/2026) ─────────────────
# Đo thật 17/10/2026 (tài khoản FREE, 4 yêu cầu 0,008 USD): `searchHashtags_keyword` trả
# `challenge_list[].challenge_info` {cid, cha_name, user_count, view_count}; `challengePosts_cid`
# trả `aweme_list` 20 bài/yêu cầu dù xin 30, `cursor` + `has_more` (thứ tự trộn nổi + mới: #hapas
# trang 1 có 11/20 bài trong 30 ngày, gồm video seeding chỉ có hashtag); `userPosts_userId` chạy
# được KHÔNG cần secUserId — lưu uid là lần sau khỏi gọi hồ sơ.
TAG_MOI_TRANG = 20           # challengePosts_count > 20 vẫn chỉ trả 20


def Ngan(tran_usd: float | None) -> _Ngan:  # noqa: N802 — tên công khai của `_Ngan`
    """Bộ đếm yêu cầu có trần USD (dùng chung cho nhiều lời gọi của một lượt)."""
    return _Ngan(tran_usd)


def chuan_tag(s: str) -> str:
    """Tên hashtag để so: bỏ '#', bỏ dấu, chỉ chữ thường + số ("#HAPAS🥰" → "hapas")."""
    return re.sub(r"[^0-9a-z]", "", A._norm(str(s or "").lstrip("#")))


def tim_cid(ten: str, ngan: _Ngan) -> str | None:
    """cid của hashtag `ten` (1 yêu cầu `searchHashtags`): chỉ nhận tag TRÙNG tên sau khi chuẩn
    hoá (`chuan_tag`), nhiều tag cùng tên thì lấy tag nhiều người dùng nhất. None khi không thấy
    hoặc đã chạm trần."""
    goc = chuan_tag(ten)
    if not goc:
        return None
    it = _goi({"searchHashtags_keyword": goc, "searchHashtags_count": 10,
               "searchHashtags_region": "VN", "searchHashtags_cursor": 0}, ngan)
    tot = None
    for x in (it or {}).get("challenge_list") or []:
        ci = (x or {}).get("challenge_info") if isinstance(x, dict) else None
        if not isinstance(ci, dict) or not ci.get("cid") or chuan_tag(ci.get("cha_name")) != goc:
            continue
        n = _so(ci.get("user_count")) or 0
        if tot is None or n > tot[0]:
            tot = (n, str(ci["cid"]))
    return tot[1] if tot else None


def bai_hashtag(cid: str, so_trang: int, ngan: _Ngan) -> list[dict]:
    """Bài của một hashtag (item kiểu clockworks), tối đa `so_trang` trang × 20 bài. Trang sau
    lỗi thì GIỮ các trang trước (đã trả tiền); trang đầu lỗi thì ném."""
    ra: list[dict] = []
    thay: set[str] = set()
    con_tro = 0
    for _ in range(max(0, int(so_trang))):
        try:
            it = _goi({"challengePosts_cid": str(cid), "challengePosts_count": TAG_MOI_TRANG,
                       "challengePosts_cursor": con_tro}, ngan)
        except A.LoiApify as e:
            if not ra:
                raise
            if e.ma in _DUNG_HAN:   # giữ trang đã trả tiền, nhưng khoá bộ đếm: luồng khác dừng
                ngan.dung, ngan.toi_da = e.ma, 0
            break
        if it is None:
            break
        moi = 0
        for a in it.get("aweme_list") or []:
            if isinstance(a, dict) and a.get("aweme_id") and str(a["aweme_id"]) not in thay:
                thay.add(str(a["aweme_id"]))
                ra.append(video(a))
                moi += 1
        sau = _so(it.get("cursor")) or 0
        if not it.get("has_more") or not moi or sau <= con_tro:
            break
        con_tro = sau
    return ra


def bai_tai_khoan(ten: str, so_trang: int, ngan: _Ngan, uid: str | None = None,
                  d_from: datetime.datetime | None = None) -> tuple[list[dict], str | None]:
    """Bài MỚI NHẤT của một tài khoản (bỏ bài ghim), tối đa `so_trang` trang × 10 bài; dừng sớm
    khi trang đã có bài cũ hơn `d_from`. `uid` đã biết thì bỏ yêu cầu hồ sơ. -> (bài, uid).
    Trang sau lỗi thì giữ các trang trước; trang đầu / hồ sơ lỗi thì ném."""
    if not uid:
        it = _goi({"profile_username": str(ten).lstrip("@"), "profile_region": "VN"}, ngan)
        uid = str(((it or {}).get("user") or {}).get("uid") or "") or None
        if not uid:
            return [], None
    ra: list[dict] = []
    con_tro = "0"
    for _ in range(max(0, int(so_trang))):
        try:
            it = _goi({"userPosts_userId": str(uid), "userPosts_count": BAI_MOI_TRANG,
                       "userPosts_region": "VN", "userPosts_maxCursor": con_tro}, ngan)
        except A.LoiApify as e:
            if not ra:
                raise
            if e.ma in _DUNG_HAN:   # giữ trang đã trả tiền, nhưng khoá bộ đếm: luồng khác dừng
                ngan.dung, ngan.toi_da = e.ma, 0
            break
        if it is None:
            break
        cu = False
        for a in it.get("aweme_list") or []:
            if isinstance(a, dict) and a.get("aweme_id") and not a.get("is_top"):
                v = video(a)
                ra.append(v)
                dt = A._to_vn(v["createTimeISO"])
                cu = cu or bool(d_from and dt and dt < d_from)
        con_tro = str(it.get("max_cursor") or "")
        if cu or not it.get("has_more") or not con_tro:
            break
    return ra, uid


#: Bộ lọc ngày phía server của trang "mới nhất": feed đã sắp theo giờ đăng nên bộ lọc chỉ chặn
#: đuôi; dừng lật trang theo mốc lượt trước ở phía Mark (`tim_moi_nhat`).
MOI_NHAT_MOC_NGAY = 30


def tim_moi_nhat(viec: list[tuple[str, datetime.datetime | None]], so_trang: int, ngan: _Ngan,
                 vung: str = "VN") -> dict[str, dict]:
    """Trang MỚI NHẤT (`SAP_MOI_NHAT`) của từng (từ khoá, mốc), ≤ `so_trang` trang × 30 bài mỗi
    từ. Feed sắp theo giờ đăng giảm dần: một từ XONG ("cham") khi trang chạm bài cũ hơn mốc (phần
    sau đã thấy ở lượt trước), hết trang, hoặc trang không có bài mới. Mốc None = chỉ trang đầu.

    Review 17/10 (M2): mọi từ dùng chung trần `ngan` — VÒNG 1 lấy trang đầu của MỌI từ, rồi các
    vòng sau mỗi từ chưa xong thêm một trang (xoay vòng), để từ đứng sau không bị đói vì từ bận
    đứng trước lật hết trần. -> {từ khoá: {"bai", "trang": số yêu cầu, "moi_hon_moc", "cham":
    đã lật tới mốc / hết feed (M1: chưa chạm thì bên gọi KHÔNG dời mốc), "cu_nhat": giờ đăng
    bài cũ nhất đã thấy, "loi"}}. KHÔNG ném lỗi Apify: lỗi một từ ghi vào `loi` của nó (trang đã
    trả tiền giữ nguyên); HET_TIEN_THANG / DA_HUY thì khoá bộ đếm (`ngan.dung`) — từ khác dừng."""
    kq: dict[str, dict] = {}
    trang_thai: dict[str, dict] = {}
    for kw, moc in viec:
        kq[kw] = {"bai": [], "trang": 0, "moi_hon_moc": 0, "cham": False, "cu_nhat": None,
                  "loi": ""}
        trang_thai[kw] = {"moc": moc, "off": 0, "thay": set(), "xong": False,
                          "toi_da": max(0, int(so_trang)) if moc is not None
                          else min(1, int(so_trang))}

    def mot_trang(kw: str) -> None:
        r, t = kq[kw], trang_thai[kw]
        try:
            it = _goi({"searchPosts_keyword": kw, "searchPosts_count": TIM_MOI_TRANG,
                       "searchPosts_offset": t["off"], "searchPosts_region": vung,
                       "searchPosts_publishTime": MOI_NHAT_MOC_NGAY,
                       "searchPosts_sortType": SAP_MOI_NHAT}, ngan)
        except A.LoiApify as e:
            r["loi"] = A._che_token(f"{e.ma}: {e}")[:120]
            if e.ma in _DUNG_HAN:
                ngan.dung, ngan.toi_da = e.ma, 0
            t["xong"] = True
            return
        except Exception as e:               # lỗi lạ: giữ trang đã trả tiền của mọi từ
            if type(e).__name__ == "MatQuyen":
                raise
            r["loi"] = A._che_token(f"{type(e).__name__}: {e}")[:120]
            t["xong"] = True
            return
        if it is None:                       # hết trần: dừng, CHƯA chạm mốc
            t["xong"] = True
            return
        r["trang"] += 1
        moi = 0
        for y in it.get("search_item_list") or []:
            a = (y or {}).get("aweme_info") if isinstance(y, dict) else None
            if not isinstance(a, dict) or not a.get("aweme_id"):
                continue
            try:
                v = video(a)
                dt = A._to_vn(v["createTimeISO"])
            except (KeyError, TypeError, ValueError, AttributeError):
                continue                     # một bài hỏng shape không làm mất cả trang đã trả
            if v["id"] in t["thay"]:
                continue
            t["thay"].add(v["id"])
            moi += 1
            r["bai"].append(v)
            if dt and (r["cu_nhat"] is None or dt < r["cu_nhat"]):
                r["cu_nhat"] = dt
            if t["moc"] is not None and dt and dt < t["moc"]:
                r["cham"] = True
            else:
                r["moi_hon_moc"] += 1
        if not it.get("has_more") or not moi:
            r["cham"] = True                 # hết feed: không còn gì để lật
        if r["cham"] or r["trang"] >= t["toi_da"]:
            t["xong"] = True
            return
        t["off"] = max(t["off"] + TIM_MOI_TRANG, _so(it.get("cursor")) or 0)

    while True:
        con = [kw for kw, t in trang_thai.items() if not t["xong"] and t["toi_da"] > 0]
        if not con or ngan.da >= ngan.toi_da:
            break
        _song_song(mot_trang, con)
    return kq


def so_yeu_cau_tim(so_tu: int, per: int) -> int:
    """Số yêu cầu TỐI ĐA một lượt tìm (`so_tu` từ khoá, ~`per` bài mỗi từ) — cho ước tính."""
    return so_tu * (2 * math.ceil(max(1, per) / TIM_MOI_TRANG) + 1) if so_tu and per > 0 else 0
