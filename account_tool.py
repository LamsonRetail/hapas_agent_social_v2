"""Tool `soi_tai_khoan`: xem một TÀI KHOẢN cụ thể đăng gì — brand đối thủ hoặc KOC/KOL.

Vì sao cần — câu hỏi thật trong sổ audit mà Mark chưa làm được:
  • "khảo sát thương hiệu edoris, tactics truyền thông edoris làm từ đầu tháng 9 tới nay"
  • Team Booking KOL/KOC hỏi về creator; có lượt Mark còn trả số từ `kol_index_gia_lap`
    — tức số GIẢ LẬP.
`social_listen` tìm bài NGƯỜI KHÁC nói về một từ khoá; tool này đọc bài của CHÍNH tài
khoản đó, kèm số liệu thật (follower, view, tương tác, bài hợp tác).

Nguồn — đo thật 25/09/2026:
  • TikTok (clockworks~tiktok-profile-scraper, 0,003 USD/video): chạy. KHÔNG dùng bộ lọc
    ngày của actor: cùng tài khoản @hapas.official, có lọc ngày thì trả "Profile has no
    videos (or is behind a login wall)", không lọc thì trả đủ. Nên lấy bài MỚI NHẤT rồi
    tự lọc ngày — vừa chạy được, vừa khỏi phí lọc ngày (0,0013 USD/video).
  • Facebook (apify~facebook-posts-scraper, 0,005 USD/bài): chạy với TRANG công khai
    (vd EdorisVietNam), không đọc được trang cá nhân. Không trả số người theo dõi trang.
  • Instagram (apify~instagram-profile-scraper, 0,0026 USD/tài khoản): trả follower và
    12 bài MỚI NHẤT — không lấy sâu hơn được.

Mọi lượt chạy đi qua `apify_tool._call` nên tự chịu trần chi phí trên console, và chi phí
thật được ghi vào sổ audit (`chi_phi_tool`).
"""
from __future__ import annotations

import collections
import contextvars
import datetime
import re
import statistics
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor

import apify_tool as A
import chi_phi_tool
import memory_store

from tools.registry import registry, tool_error, tool_result  # type: ignore

_ACTOR = {
    "tiktok": "clockworks~tiktok-profile-scraper",
    "facebook": "apify~facebook-posts-scraper",
    "instagram": "apify~instagram-profile-scraper",
}
_GIA = {"tiktok": 0.003, "facebook": 0.005, "instagram": 0.0026}   # USD / bài (IG: / tài khoản)
_IG_TOI_DA = 12          # actor Instagram chỉ trả 12 bài mới nhất
_MAC_DINH_NGAY = 30
# Dấu hiệu bài hợp tác/quảng cáo trong caption. Cờ `paidPartnership`/`isAd` của nền tảng
# thường không được bật (đo 25/09: bài fansign của Edoris đều False), nên phải đọc chữ.
_HOP_TAC = re.compile(
    r"#(ad|ads|quangcao|hoptac\w*|hợptác\w*|taitro|tàitrợ|sponsored|partner\w*|collab\w*)\b"
    r"|\bhợp tác\b|\bcollab\b|\btài trợ\b", re.I)
# "EDORIS × QUANG HÙNG", "MASTERD x EDORIS": hai cụm VIẾT HOA nối bằng x/×. Phân biệt hoa
# thường, nên "x cái" trong câu thường không bị tính.
_HOP_TAC_HOA = re.compile(r"[A-ZĐÀ-Ỹ]{2,}\s*[x×]\s*[A-ZĐÀ-Ỹ]{2,}")
_NHAC = re.compile(r"@([\w.]{2,30})")


def _la_hop_tac(b: dict) -> bool:
    # NFKC đổi chữ in đậm kiểu 𝐄𝐃𝐎𝐑𝐈𝐒 (rất hay gặp trong caption) về chữ thường.
    t = unicodedata.normalize("NFKC", b.get("noi_dung") or "")
    return bool(b.get("tra_tien") or _HOP_TAC.search(t) or _HOP_TAC_HOA.search(t))


def _nhan_dien(muc: str, mac_dinh: str) -> tuple[str, str] | None:
    """Link hoặc @tên → (nền tảng, định danh cho actor). None nếu không hiểu."""
    s = (muc or "").strip()
    if not s:
        return None
    m = re.search(r"tiktok\.com/@([\w.\-]+)", s, re.I)
    if m:
        return "tiktok", m.group(1)
    m = re.search(r"instagram\.com/([\w.\-]+)", s, re.I)
    if m:
        return "instagram", m.group(1)
    m = re.search(r"(?:facebook|fb)\.com/([^/?#\s]+)", s, re.I)
    if m:
        return "facebook", f"https://www.facebook.com/{m.group(1)}"
    ten = s.lstrip("@")
    if not re.fullmatch(r"[\w.\-]{2,60}", ten):
        return None
    if mac_dinh == "facebook":
        return "facebook", f"https://www.facebook.com/{ten}"
    return mac_dinh, ten


def _so(v) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


# ───────────────────────────── lấy dữ liệu ─────────────────────────────
def _lay_tiktok(ten: list[str], n: int) -> dict[str, dict]:
    raw = A._call(_ACTOR["tiktok"], {"profiles": ten, "resultsPerPage": n,
                                     "profileSorting": "latest", "excludePinnedPosts": True},
                  n * len(ten))
    ra: dict[str, dict] = {}
    for it in raw:
        am = it.get("authorMeta") or {}
        k = str(am.get("name") or it.get("input") or "").lower()
        tk = ra.setdefault(k, {"ho_so": {
            "ten": am.get("nickName") or am.get("name") or k, "tai_khoan": am.get("name") or k,
            "followers": _so(am.get("fans")), "tong_like": _so(am.get("heart")),
            "tong_video": _so(am.get("video")), "xac_minh": bool(am.get("verified")),
            "link": f"https://www.tiktok.com/@{am.get('name') or k}"}, "bai": [], "ghi_chu": ""})
        if it.get("note") and not it.get("webVideoUrl"):
            tk["ghi_chu"] = str(it["note"])
            continue
        tk["bai"].append({
            "ngay": A._to_vn(it.get("createTimeISO")), "loai": "video",
            "view": _so(it.get("playCount")), "like": _so(it.get("diggCount")),
            "binh_luan": _so(it.get("commentCount")), "share": _so(it.get("shareCount")),
            "noi_dung": str(it.get("text") or ""), "link": it.get("webVideoUrl") or "",
            "hashtag": [h.get("name") for h in it.get("hashtags") or [] if h.get("name")],
            "am_thanh": (it.get("musicMeta") or {}).get("musicName") or "",
            "tra_tien": bool(it.get("isAd") or it.get("isSponsored")),
        })
    return ra


def _lay_facebook(urls: list[str], n: int) -> dict[str, dict]:
    raw = A._call(_ACTOR["facebook"], {"startUrls": [{"url": u} for u in urls],
                                       "resultsLimit": n}, n * len(urls))
    ra: dict[str, dict] = {}
    for it in raw:
        if it.get("error"):
            continue
        k = str(it.get("pageName") or it.get("inputUrl") or "").lower()
        tk = ra.setdefault(k, {"ho_so": {
            "ten": it.get("pageName") or k, "tai_khoan": it.get("pageName") or k,
            "followers": None, "link": it.get("facebookUrl") or it.get("inputUrl") or ""},
            "bai": [], "ghi_chu": ""})
        media = [m.get("__typename") for m in it.get("media") or [] if isinstance(m, dict)]
        tk["bai"].append({
            "ngay": A._to_vn(it.get("time")), "loai": "video" if "Video" in media else "bài",
            "view": _so(it.get("viewsCount")) or None, "like": _so(it.get("likes")),
            "binh_luan": _so(it.get("comments")), "share": _so(it.get("shares")),
            "noi_dung": str(it.get("text") or ""), "link": it.get("url") or "",
            "hashtag": re.findall(r"#([\w]+)", str(it.get("text") or "")),
            "am_thanh": "", "tra_tien": bool(it.get("paidPartnership")),
            "dong_tac_gia": [c.get("name") for c in it.get("collaborators") or []
                             if isinstance(c, dict) and c.get("name")],
        })
    return ra


def _lay_instagram(ten: list[str], n: int) -> dict[str, dict]:
    raw = A._call(_ACTOR["instagram"], {"usernames": ten}, len(ten))
    ra: dict[str, dict] = {}
    for it in raw:
        k = str(it.get("username") or "").lower()
        if not k:
            continue
        bai = [{
            "ngay": A._to_vn(p.get("timestamp")),
            "loai": "video" if p.get("type") == "Video" else "bài",
            "view": _so(p.get("videoViewCount")) or None, "like": _so(p.get("likesCount")),
            "binh_luan": _so(p.get("commentsCount")), "share": None,
            "noi_dung": str(p.get("caption") or ""), "link": p.get("url") or "",
            "hashtag": list(p.get("hashtags") or []), "am_thanh": "",
            "tra_tien": bool(p.get("paidPartnership")),
            "nhac_ten": list(p.get("mentions") or []),
        } for p in (it.get("latestPosts") or [])[:min(n, _IG_TOI_DA)]]
        ra[k] = {"ho_so": {
            "ten": it.get("fullName") or k, "tai_khoan": k,
            "followers": _so(it.get("followersCount")), "tong_bai": _so(it.get("postsCount")),
            "xac_minh": bool(it.get("verified")), "nganh": it.get("businessCategoryName") or "",
            "link": it.get("url") or f"https://www.instagram.com/{k}/"},
            "bai": bai, "ghi_chu": "" if bai else "tài khoản riêng tư hoặc chưa có bài"}
    return ra


# ───────────────────────────── tính số liệu ─────────────────────────────
def _tong_hop(nen: str, tk: dict, tu: datetime.datetime, den: datetime.datetime,
             n_doc: int) -> dict:
    ho_so, tat_ca = tk["ho_so"], tk["bai"]
    bai = [b for b in tat_ca if b["ngay"] and tu <= b["ngay"] <= den]
    ra = {"nen_tang": nen, "ho_so": ho_so, "so_bai_trong_khoang": len(bai),
          "so_bai_da_doc": len(tat_ca), "ghi_chu": tk.get("ghi_chu") or ""}
    if not bai:
        return ra
    # Đọc KÍN số bài giới hạn mà bài cũ nhất vẫn nằm trong khoảng → phần đầu khoảng chưa
    # đọc tới. Chia cho cả khoảng là ra tần suất SAI: đo thật 25/09, đọc 10 bài từ 01/09
    # thì cả Edoris, HAPAS lẫn IG Edoris đều ra đúng "2,8 bài/tuần" — con số do giới hạn
    # đọc sinh ra, không phải của tài khoản. Khi đó chỉ tính trên đoạn đã đọc được.
    cu_nhat = min(b["ngay"] for b in bai)
    chua_phu = len(tat_ca) >= min(n_doc, _IG_TOI_DA if nen == "instagram" else n_doc) \
        and cu_nhat > tu
    goc = cu_nhat if chua_phu else tu
    so_ngay = max(1, (den - goc).days + 1)
    if chua_phu:
        ra["chua_phu_het_khoang"] = (
            f"Chỉ đọc {len(tat_ca)} bài mới nhất, phủ từ {cu_nhat:%d/%m}; trước đó chưa đọc "
            f"tới. Tần suất tính trên {so_ngay} ngày đã đọc được."
            + ("" if nen == "instagram" else " Tăng `so_bai` để phủ trọn khoảng."))
    tuong_tac = [b["like"] + b["binh_luan"] + (b["share"] or 0) for b in bai]
    view = [b["view"] for b in bai if b["view"]]
    fol = ho_so.get("followers") or 0
    ra.update({
        "bai_moi_tuan": round(len(bai) / so_ngay * 7, 1),
        "tuong_tac_tb_moi_bai": round(statistics.mean(tuong_tac)),
        "like_tb": round(statistics.mean(b["like"] for b in bai)),
        "binh_luan_tb": round(statistics.mean(b["binh_luan"] for b in bai)),
    })
    if view:
        ra["view_trung_vi"] = int(statistics.median(view))
        ra["ti_le_tuong_tac_tren_view"] = round(
            sum(t for b, t in zip(bai, tuong_tac) if b["view"]) / max(1, sum(view)), 4)
        if fol:
            # View thường đạt bao nhiêu % follower: thước đo KOC có "sống" không.
            ra["view_trung_vi_tren_follower"] = round(ra["view_trung_vi"] / fol, 3)
    elif fol:
        ra["ti_le_tuong_tac_tren_follower"] = round(statistics.mean(tuong_tac) / fol, 4)

    hop_tac = [b for b in bai if _la_hop_tac(b)]
    ra["bai_hop_tac_hoac_quang_cao"] = len(hop_tac)
    tag = collections.Counter(h.lower() for b in bai for h in b["hashtag"])
    ra["hashtag_hay_dung"] = [f"#{h}" for h, _ in tag.most_common(8)]
    nhac = collections.Counter(
        n.lower() for b in bai for n in (b.get("nhac_ten") or []) + _NHAC.findall(b["noi_dung"])
        + (b.get("dong_tac_gia") or []))
    if nhac:
        ra["nhac_toi_nhieu"] = [n for n, _ in nhac.most_common(6)]
    am = collections.Counter(b["am_thanh"] for b in bai if b["am_thanh"])
    if am:
        ra["am_thanh_hay_dung"] = [a for a, _ in am.most_common(5)]
    # Không trộn đơn vị: Facebook chỉ reel mới có view, bài ảnh thì không. Xếp theo "view,
    # không có thì tương tác" từng đẩy reel 6.337 view / 9 like lên trên bài 4.589 tương
    # tác. Chỉ xếp theo view khi MỌI bài đều có view (TikTok).
    theo_view = all(b["view"] for b in bai)
    top = sorted(zip(bai, tuong_tac),
                 key=lambda x: -(x[0]["view"] if theo_view else x[1]))[:3]
    ra["bai_noi_bat"] = [{
        "ngay": f"{b['ngay']:%d/%m}", "view": b["view"], "tuong_tac": t,
        "noi_dung": " ".join(b["noi_dung"].split())[:160], "link": b["link"]} for b, t in top]
    return ra


# ───────────────────────────── tool ─────────────────────────────
SCHEMA = {
    "name": "soi_tai_khoan",
    "description": (
        "Soi MỘT hoặc vài TÀI KHOẢN cụ thể trên TikTok, Facebook (trang công khai) hoặc "
        "Instagram: họ đăng gì, bao nhiêu bài mỗi tuần, view và tương tác thật, bài nào "
        "nổi nhất, hay dùng hashtag/âm thanh nào, nhắc tới ai, bao nhiêu bài hợp tác/quảng "
        "cáo. Dùng cho: (1) ĐỐI THỦ — 'Edoris đăng gì từ đầu tháng 9', 'tactics truyền "
        "thông của brand X'; (2) KOC/KOL — 'KOC này có đáng book không', 'so sánh 3 KOC'.\n"
        "KHÁC `social_listen`: tool kia tìm bài NGƯỜI KHÁC nói về một từ khoá; tool này đọc "
        "bài của CHÍNH tài khoản đó. Hỏi 'mọi người nói gì về HAPAS' thì dùng social_listen.\n"
        "Muốn biết đối thủ đang CHẠY QUẢNG CÁO gì thì gọi thêm `fb_ads_library`.\n"
        "`tai_khoan`: dán link hồ sơ (tiktok.com/@…, facebook.com/…, instagram.com/…) hoặc "
        "@tên. Chưa biết link thì tra trang web chính thức của brand bằng `web_scrape` — "
        "thường có link mạng xã hội ở chân trang — đừng đoán tên tài khoản.\n"
        "KHI TRẢ LỜI: nói số liệu THẬT từ kết quả, đừng tự ước lượng follower hay view. "
        "`view_trung_vi_tren_follower` là tỉ lệ view thường đạt so với follower (KOC 'sống' "
        "hay không). Instagram chỉ có 12 bài mới nhất; Facebook không có số người theo "
        "dõi trang — nói rõ khi liên quan. Tài khoản có `ghi_chu` (không đọc được) thì nói "
        "thẳng, đừng bỏ qua. Gửi NGUYÊN `sheet_url`."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tai_khoan": {"type": "array", "items": {"type": "string"},
                          "description": "Link hồ sơ hoặc @tên, tối đa 5 tài khoản."},
            "nen_tang": {"type": "string", "enum": ["tiktok", "facebook", "instagram"],
                         "description": "Nền tảng cho những mục chỉ ghi @tên (mặc định tiktok)."},
            "date_from": {"type": "string",
                          "description": "Ngày bắt đầu 'YYYY-MM-DD' (mặc định 30 ngày trước)."},
            "date_to": {"type": "string", "description": "Ngày kết thúc (mặc định hôm nay)."},
            "so_bai": {"type": "integer",
                       "description": "Số bài mới nhất đọc MỖI tài khoản (mặc định 30, tối đa theo trần)."},
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
        },
        "required": ["tai_khoan"],
    },
}

_LAY = {"tiktok": _lay_tiktok, "facebook": _lay_facebook, "instagram": _lay_instagram}
_HEADER = ["Nền tảng", "Tài khoản", "Ngày đăng", "Loại", "View", "Like", "Bình luận",
           "Share", "Hợp tác / QC", "Hashtag", "Nội dung", "Link"]


def _handle(args: dict, **_kwargs) -> str:
    ds = args.get("tai_khoan") or []
    ds = [ds] if isinstance(ds, str) else list(ds)
    mac_dinh = str(args.get("nen_tang") or "tiktok").lower()
    nhom: dict[str, list[str]] = collections.defaultdict(list)
    khong_hieu = []
    for m in ds[:5]:
        r = _nhan_dien(str(m), mac_dinh if mac_dinh in _ACTOR else "tiktok")
        if r:
            nhom[r[0]].append(r[1])
        else:
            khong_hieu.append(str(m))
    if not nhom:
        return tool_error("Không nhận ra tài khoản nào. Dán link hồ sơ (tiktok.com/@…, "
                          "facebook.com/…, instagram.com/…) hoặc @tên.")
    try:
        den = A._parse_date(args.get("date_to") or "", end=True) if args.get("date_to") \
            else datetime.datetime.now(A._VN_TZ)
        tu = A._parse_date(args.get("date_from") or "", end=False) if args.get("date_from") \
            else (den - datetime.timedelta(days=_MAC_DINH_NGAY)).replace(hour=0, minute=0, second=0)
    except ValueError as e:
        return tool_error(str(e))

    tran_bai, _ = A._tran()
    try:
        n = max(5, min(int(args.get("so_bai") or 30), tran_bai))
    except (TypeError, ValueError):
        n = min(30, tran_bai)
    est = sum(_GIA[p] * (len(v) if p == "instagram" else len(v) * n) for p, v in nhom.items())
    bat_dau = datetime.datetime.now(A._VN_TZ) - datetime.timedelta(seconds=5)
    t0 = time.monotonic()

    ket_qua, loi = [], {}
    # KHÔNG `with ThreadPoolExecutor`: `with` gọi shutdown(wait=True), ngồi chờ luồng chậm
    # nhất nên `timeout` vô hiệu (rà 01/10/2026, cùng lỗi audit 340s/508s của social_listen).
    # Một hạn chung cho mọi nguồn; luồng còn treo bỏ lại, run Apify tự hết hạn.
    han = t0 + A._TOOL_DEADLINE
    ex = ThreadPoolExecutor(max_workers=len(nhom))
    try:
        futs = {p: ex.submit(contextvars.copy_context().run, _LAY[p], v, n)
                for p, v in nhom.items()}
        for p, f in futs.items():
            try:
                for tk in f.result(timeout=max(0.05, han - time.monotonic())).values():
                    ket_qua.append((p, tk))
            except Exception as e:  # noqa: BLE001
                loi[p] = f"{type(e).__name__}: {e}"[:250]
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    thuc = A._chi_phi_thuc([_ACTOR[p] for p in nhom], bat_dau, est)
    rng = f"{tu:%Y-%m-%d} → {den:%Y-%m-%d}"
    chi_phi_tool.ghi(queries=ds[:5], platforms=sorted(nhom), date_range=rng, thuc=thuc, est=est)

    tong = [_tong_hop(p, tk, tu, den, n) for p, tk in ket_qua]
    da_thay = {t["ho_so"]["tai_khoan"].lower() for t in tong}
    khong_thay = [v for p, vs in nhom.items() if p not in loi for v in vs
                  if v.rstrip("/").split("/")[-1].lower() not in da_thay]

    url, granted = None, False
    rows = [list(_HEADER)] + [[
        p, tk["ho_so"]["tai_khoan"], f"{b['ngay']:%Y-%m-%d %H:%M}" if b["ngay"] else "",
        b["loai"], b["view"] or "", b["like"], b["binh_luan"], b["share"] or "",
        "có" if _la_hop_tac(b) else "",
        " ".join(f"#{h}" for h in b["hashtag"][:8]), b["noi_dung"][:1000], b["link"],
    ] for p, tk in ket_qua for b in tk["bai"] if b["ngay"] and tu <= b["ngay"] <= den]
    if len(rows) > 1:
        title = (args.get("title") or "").strip() or \
            f"Soi tài khoản · {', '.join(t['ho_so']['tai_khoan'] for t in tong)[:40]} · {tu:%d-%m}→{den:%d-%m}"
        try:
            tok, url = A._create_sheet(title)
            A._write_values(tok, A._first_sheet_id(tok), rows)
            sender = memory_store.get_current_sender()
            granted = A._grant(tok, sender) if sender else False
        except Exception as e:  # noqa: BLE001
            loi["sheet"] = f"{type(e).__name__}: {e}"[:250]

    if not tong and loi:
        return tool_error("Không đọc được tài khoản nào: " + "; ".join(
            f"{k}: {v}" for k, v in loi.items()))
    return tool_result(
        success=not loi, khoang_ngay=rng, tai_khoan=tong,
        khong_tim_thay=khong_thay or None, khong_nhan_ra=khong_hieu or None,
        loi=loi or None, sheet_url=url, granted=granted, so_bai_doc_moi_tai_khoan=n,
        uoc_tinh_chi_phi_usd=round(est, 3),
        chi_phi_thuc_usd=thuc["usd"] if thuc and thuc.get("so_run") else None,
        chi_phi=A._dong_chi_phi(thuc, est), giay=round(time.monotonic() - t0, 1),
    )


def _available() -> bool:
    return A._available()


try:
    registry.register(
        name="soi_tai_khoan", toolset="social", schema=SCHEMA, handler=_handle,
        check_fn=_available, requires_env=[], is_async=False,
        description="Soi tài khoản brand đối thủ hoặc KOC trên TikTok/Facebook/Instagram",
        emoji="\U0001f50d", override=True,
    )
except Exception as e:  # noqa: BLE001
    print(f"[account_tool] register warning: {e}")
