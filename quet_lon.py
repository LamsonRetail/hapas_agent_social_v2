"""Quét LỚN cho `social_listen`: ước tính, quyết định chạy nền, lập kế hoạch từng nền
tảng, chạy việc nền, phân xử theo tầng, ghi sheet cỡ lớn, soạn tin kết quả.

Vì sao tách khỏi apify_tool (chủ agent chốt 01–02/10/2026: một yêu cầu phải quét được
10.000 bài): lượt tại chỗ có ~135 giây; 10.000 bài TikTok ở ~2 bài/giây là ~80 phút chạy
actor. Một run khổng lồ thì hết hạn là mất cả, khởi động lại bot là POST lại (trả tiền
hai lần). Nên chia thành nhiều LƯỢT CON (từ khoá × cửa sổ ngày × hashtag), mỗi lượt con
ghi run id xuống sổ việc (viec_nen) ngay khi có, dòng chuẩn hoá tràn ra file jsonl, đọc
tiếp được sau khi khởi động lại.

Nguồn thật có giới hạn — không giấu (`chua_phu`):
- Facebook gói FREE: 1 từ khoá, 20 bài, 1 lượt/24 giờ — quét nền cũng không vượt được.
- Threads ~0,9 bài/giây: 10.000 bài không vừa hạn 45 phút; kế hoạch tự cắt cho vừa hạn
  và nói rõ phần không kịp.
- YouTube: quota 100 trang search/ngày (giờ PT); việc nền chỉ dùng tới 80 trang.
- TikTok quét theo HASHTAG (actor clockworks): từ khoá có dấu cách không phải hashtag —
  KHÔNG tự chế hashtag, chỉ còn lượt dò keyword nhỏ (apidojo ≤100 bài).
"""
from __future__ import annotations

import contextvars
import datetime
import hashlib
import json
import math
import os
import random
import re
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

import apify_tool as A
import sheet_lon

from tools.registry import tool_error, tool_result  # type: ignore

# ───────────────────────────── tốc độ actor ─────────────────────────────
# Hạt giống item/giây (đo thô 08–10/2026, chưa đủ mẫu) — tự hiệu chỉnh EWMA theo từng run
# thật, lưu `.audit/viec-nen/toc-do.json`. Ước tính sai chỉ làm sai số phút báo trước;
# hạn chót và trần tiền vẫn chặn cứng.
_TOC_HAT_GIONG = {
    A._ACTORS["tiktok"]: 2.0,
    A._ACTORS["tiktok_fallback"]: 2.0,
    A._ACTORS["instagram"]: 3.0,
    A._ACTORS["facebook"]: 1.0,
    A._ACTORS["threads"]: 0.9,
    "youtube": 1.0,                       # TRANG search/giây (mỗi trang ~3 lượt API)
    # Bình luận: CHƯA đo — để lạc quan cho ngưỡng "lượt chậm" của deep_dive không đẩy lượt
    # vài trăm bình luận sang nền; ngưỡng 1500 bình luận vẫn chặn lượt lớn. EWMA tự sửa.
    "clockworks~tiktok-comments-scraper": 15.0,
    "streamers~youtube-comments-scraper": 15.0,
    "apify~facebook-comments-scraper": 5.0,
}
_GIAY_KHOI_DONG = 20       # mỗi run Apify: xếp lịch + khởi động container
_GIAY_TAI_CHO_KHOI_DONG = 15
_EWMA = 0.3
_TOC_KHOA = threading.Lock()


def _toc_file():
    return A._thu_muc_nen() / "toc-do.json"


def _doc_toc() -> dict:
    try:
        return json.loads(_toc_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def toc(actor: str) -> float:
    v = (_doc_toc().get(actor) or {}).get("toc")
    try:
        return max(0.05, float(v)) if v else _TOC_HAT_GIONG.get(actor, 1.0)
    except (TypeError, ValueError):
        return _TOC_HAT_GIONG.get(actor, 1.0)


def cap_nhat_toc(actor: str, so_item: int, giay: float) -> None:
    """EWMA item/giây từ một run THẬT đã xong (bỏ phần khởi động)."""
    if so_item < 20 or giay <= _GIAY_KHOI_DONG:
        return
    moi = so_item / max(1.0, giay - _GIAY_KHOI_DONG)
    with _TOC_KHOA:
        d = _doc_toc()
        cu = (d.get(actor) or {}).get("toc") or _TOC_HAT_GIONG.get(actor, moi)
        d[actor] = {"toc": round(min(50.0, max(0.05, (1 - _EWMA) * cu + _EWMA * moi)), 3),
                    "n": int((d.get(actor) or {}).get("n") or 0) + 1}
        try:
            f = _toc_file()
            f.parent.mkdir(parents=True, exist_ok=True)
            tmp = f.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, f)
        except OSError:
            pass


# ───────────────────────────── khi nào chạy nền ─────────────────────────────
def _nguong() -> tuple[int, int, int]:
    return (A._so_env("SOCIAL_NEN_TONG_BAI", 1500, 100, 100000),
            A._so_env("SOCIAL_NEN_BAI_NEN_TANG", 600, 50, 100000),
            A._so_env("SOCIAL_NEN_NGUONG_GIAY", 80, 20, 3600))


def giay_tai_cho(plats: list[str], lims: dict, queries: list[str]) -> float:
    """Giây Apify ƯỚC TÍNH nếu chạy tại chỗ — các nền tảng chạy song song nên lấy nền
    tảng chậm nhất. TikTok tại chỗ = lượt dò apidojo + lượt dự phòng clockworks."""
    k = max(1, len(A._bo_trung_tu_khoa(queries)))
    ra = 0.0
    for p in plats:
        n = lims.get(p, 0)
        if p == "youtube":
            g = math.ceil(n / 50) * 3.0
        elif p == "tiktok":
            g = 2 * _GIAY_TAI_CHO_KHOI_DONG + n / toc(A._ACTORS["tiktok_fallback"])
        elif p in ("instagram", "facebook"):
            g = _GIAY_TAI_CHO_KHOI_DONG + (n / k) / toc(A._ACTORS[p])
        else:
            g = _GIAY_TAI_CHO_KHOI_DONG + n / toc(A._ACTORS[p])
        ra = max(ra, g)
    return round(ra, 1)


def can_chay_nen(lims: dict, giay: float, chay_nen=None) -> tuple[bool, str]:
    """(có chạy nền không, vì sao). `chay_nen`: True ép nền, False ép tại chỗ."""
    if chay_nen is True:
        return True, "người dùng/Mark yêu cầu chạy nền"
    if chay_nen is False:
        return False, ""
    tong, mot, ng = _nguong()
    if sum(lims.values()) > tong:
        return True, f"tổng {sum(lims.values())} bài > {tong}"
    p = max(lims, key=lims.get) if lims else ""
    if p and lims[p] > mot:
        return True, f"{p} {lims[p]} bài > {mot}/nền tảng"
    if giay > ng:
        return True, f"ước tính ~{giay:.0f} giây chạy actor > {ng} giây của một lượt trả lời"
    return False, ""


def kep_tai_cho(lims: dict) -> dict:
    """Cỡ lớn nhất chạy TẠI CHỖ được (khi tắt chạy nền SOCIAL_QUET_NEN=0)."""
    tong, mot, _ = _nguong()
    ra = {p: min(n, mot) for p, n in lims.items()}
    s = sum(ra.values())
    if s > tong:
        ra = {p: max(1, int(n * tong / s)) for p, n in ra.items()}
    return ra


# ───────────────────────────── lập kế hoạch ─────────────────────────────
_GIA_DO = 0.0003          # apidojo tiktok (lượt dò keyword)
_GIA = {"tiktok": 0.003, "instagram": A._UNIT_COST["instagram"],
        "facebook": A._UNIT_COST["facebook"], "threads": A._UNIT_COST["threads"]}
_DO_TOI_DA = 100          # lượt dò apidojo: trần cứng thực tế ~10 kết quả/keyword
_THREADS_MOI_LUOT = 500
_YT_MOI_CUA_SO = 10       # trang/cửa sổ: search.list trả tối đa ~500 kết quả mỗi truy vấn
# RAM ghim cho lượt con của việc nền (MB). Threads đã đo (phí "Actor Start" tính theo GB,
# 26/08/2026). Ba actor còn lại CHƯA đo: ghim 2 GB để phí khởi động theo GB không nhân 4
# như mặc định 4 GB — chậm hơn thì EWMA tốc độ tự thấy.
_RAM_NEN = {A._ACTORS["threads"]: 1024, A._ACTORS["instagram"]: 2048,
            A._ACTORS["tiktok_fallback"]: 2048, A._ACTORS["facebook"]: 1024}


def _sha(x) -> str:
    return hashlib.sha1(json.dumps(x, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _cua_so(d_from: datetime.datetime, d_to: datetime.datetime, n: int) -> list[tuple]:
    """Chia [d_from, d_to] thành ≤n cửa sổ NGÀY liền nhau -> [(ngày đầu, ngày cuối)]."""
    a, b = d_from.date(), d_to.date()
    so_ngay = (b - a).days + 1
    n = max(1, min(n, so_ngay))
    ra, dau = [], a
    for i in range(n):
        dai = so_ngay // n + (1 if i < so_ngay % n else 0)
        cuoi = dau + datetime.timedelta(days=dai - 1)
        ra.append((dau, cuoi))
        dau = cuoi + datetime.timedelta(days=1)
    return ra


def dung_payload(p: str, ph: dict, ts: dict) -> dict:
    """Payload actor của một lượt con, dựng lại từ `ph` (để cắt `limit` xong dựng lại)."""
    n = int(ph["limit"])
    if p == "tiktok" and ph.get("kieu") == "do":
        d_from = A._parse_date(ts["date_from"], end=False)
        return {"keywords": ph["tu_khoa"], "maxItems": n, "location": ts["country"],
                "sortType": "DATE_POSTED", "dateRange": A._tiktok_enum(d_from),
                "includeSearchKeywords": True}
    if p == "tiktok":
        return {"hashtags": [ph["the"]], "resultsPerPage": n}
    if p == "instagram":
        return {"keyword": ph["tu_khoa"], "getPosts": True, "getReels": True, "maxItems": n}
    if p == "facebook":
        return {"query": ph["tu_khoa"], "search_type": "posts", "max_results": n,
                "start_date": ph["tu"], "end_date": ph["den"]}
    if p == "threads":
        return {"mode": "search", "keywords": [ph["tu_khoa"]], "max_posts": max(10, n),
                "search_filter": "recent", "start_date": ph["tu"], "end_date": ph["den"]}
    return {}


def _uoc_phan(p: str, ph: dict) -> tuple[float, float]:
    """(USD, giây) ước tính của một lượt con."""
    n = int(ph["limit"])
    if p == "youtube":
        return 0.0, ph["so_trang"] * 3.0
    gia = _GIA_DO if ph.get("kieu") == "do" else _GIA[p]
    usd = A._START_COST.get(p, 0.0) + gia * n
    return round(usd, 4), _GIAY_KHOI_DONG + n / toc(ph["actor"])


def _ke_tiktok(q, lim, ts, ctx) -> dict:
    ra = {"phan": [], "chua_phu": [], "ghi_chu": []}
    ra["phan"].append({"kieu": "do", "actor": A._ACTORS["tiktok"], "tu_khoa": list(q),
                       "limit": min(_DO_TOI_DA, lim), "nhan": "dò keyword (apidojo)"})
    the = [x.lstrip("#") for x in q if x.lstrip("#") and not re.search(r"\s", x.strip())]
    bo = [x for x in q if re.search(r"\s", x.strip())]
    if bo:
        ra["chua_phu"].append(
            "TikTok chỉ quét SÂU theo hashtag; " + ", ".join(repr(x) for x in bo)
            + " có dấu cách nên không phải hashtag — KHÔNG tự chế hashtag, các từ này chỉ "
              f"có trong lượt dò keyword (≤{_DO_TOI_DA} bài).")
    if the:
        per = math.ceil(lim / len(the))
        for t in the:
            ra["phan"].append({"kieu": "the", "actor": A._ACTORS["tiktok_fallback"],
                               "the": t, "limit": per, "nhan": f"#{t}"})
    ra["ghi_chu"].append("TikTok: hashtag scraper không lọc ngày/quốc gia — cào rồi lọc "
                         "ngày tại chỗ; số bài trong khoảng thường ít hơn số cào.")
    return ra


def _ke_instagram(q, lim, ts, ctx) -> dict:
    per = math.ceil(lim / max(1, len(q)))
    return {"phan": [{"actor": A._ACTORS["instagram"], "tu_khoa": k, "limit": per,
                      "nhan": f"từ khoá '{k}'"} for k in q],
            "chua_phu": [], "ghi_chu": ["Instagram: không lọc ngày/quốc gia, không có "
                                        "followers/share."]}


def _ke_facebook(q, lim, ts, ctx) -> dict:
    ra = {"phan": [], "chua_phu": [], "ghi_chu": []}
    tu, den = ts["date_from"], ts["date_to"]
    if ctx.get("goi") in ("FREE", ""):
        luot = ctx.get("fb_luot")
        if luot:
            ra["chua_phu"].append(
                f"Facebook gói Free đã dùng lượt 24h lúc {luot[0]:%H:%M %d/%m}, mở lại lúc "
                f"{luot[1]:%H:%M %d/%m} — việc này KHÔNG quét Facebook.")
            return ra
        ra["phan"].append({"actor": A._ACTORS["facebook"], "tu_khoa": q[0],
                           "limit": min(20, lim), "tu": tu, "den": den,
                           "nhan": f"từ khoá '{q[0]}' (gói Free)"})
        ra["chua_phu"].append(
            "Facebook gói Free: chỉ 1 từ khoá, tối đa 20 bài, 1 lượt/24 giờ — chạy nền cũng "
            "không vượt được" + (f"; chưa quét: {', '.join(repr(x) for x in q[1:])}"
                                 if len(q) > 1 else "")
            + (" (không kiểm được gói Apify, coi như Free)." if not ctx.get("goi") else "."))
        return ra
    per = math.ceil(lim / max(1, len(q)))
    ra["phan"] = [{"actor": A._ACTORS["facebook"], "tu_khoa": k, "limit": per, "tu": tu,
                   "den": den, "nhan": f"từ khoá '{k}'"} for k in q]
    return ra


def _ke_threads(q, lim, ts, ctx) -> dict:
    d_from = A._parse_date(ts["date_from"], end=False)
    d_to = A._parse_date(ts["date_to"], end=True)
    per_kw = math.ceil(lim / max(1, len(q)))
    w = math.ceil(per_kw / _THREADS_MOI_LUOT)
    cua = _cua_so(d_from, d_to, w)
    ra = {"phan": [], "chua_phu": [], "ghi_chu": []}
    moi = math.ceil(per_kw / len(cua))
    if moi > _THREADS_MOI_LUOT:
        ra["chua_phu"].append(
            f"Threads: khoảng ngày chỉ có {len(cua)} ngày nên mỗi lượt phải lấy {moi} bài "
            f"(>{_THREADS_MOI_LUOT}) — lượt dài, dễ không kịp hạn.")
    for k in q:
        for a, b in cua:
            ra["phan"].append({"actor": A._ACTORS["threads"], "tu_khoa": k, "limit": moi,
                               "tu": f"{a:%Y-%m-%d}", "den": f"{b:%Y-%m-%d}",
                               "nhan": f"'{k}' {a:%d/%m}–{b:%d/%m}"})
    return ra


def _ke_youtube(q, lim, ts, ctx) -> dict:
    d_from = A._parse_date(ts["date_from"], end=False)
    d_to = A._parse_date(ts["date_to"], end=True)
    can = math.ceil(lim / 50)
    con = int(ctx.get("yt_con", 0))
    ra = {"phan": [], "chua_phu": [], "ghi_chu": []}
    trang = min(can, con)
    if trang < can:
        ra["chua_phu"].append(
            f"YouTube: quota hôm nay (giờ PT) chỉ còn {con} trang search cho việc nền (~"
            f"{con * 50} video) — cần {can} trang cho {lim} video; phần thiếu chưa quét.")
    if trang <= 0:
        return ra
    cua = _cua_so(d_from, d_to, math.ceil(trang / _YT_MOI_CUA_SO))
    moi = math.ceil(trang / len(cua))
    con_lai = trang
    for a, b in cua:
        k = min(moi, con_lai)
        if k <= 0:
            break
        con_lai -= k
        ra["phan"].append({"actor": "youtube", "tu": f"{a:%Y-%m-%d}", "den": f"{b:%Y-%m-%d}",
                           "so_trang": k, "limit": k * 50,
                           "nhan": f"{a:%d/%m}–{b:%d/%m}, {k} trang"})
    ra["ghi_chu"].append("YouTube Data API chính thức: miễn phí, lọc ngày thật; mỗi trang "
                         "50 video, tốn 1 lượt search trong quota ngày.")
    return ra


_KE = {"tiktok": _ke_tiktok, "instagram": _ke_instagram, "facebook": _ke_facebook,
       "threads": _ke_threads, "youtube": _ke_youtube}


def _chua_nen_giay(han_giay: float) -> float:
    """Giây chừa cuối việc cho lọc + AI + ghi sheet + gửi tin."""
    return min(8 * 60.0, 0.25 * han_giay)


def ke_hoach(queries: list[str], plats: list[str], lims: dict, ts: dict,
             han_phut: int, ctx: dict | None = None) -> dict:
    """Kế hoạch lượt con cho mọi nền tảng + ước tính. Chỉ GET miễn phí (qua `ctx`)."""
    ctx = dict(ctx or {})
    q = A._bo_trung_tu_khoa(queries)
    han_giay = 60.0 * han_phut
    cua_so_apify = han_giay - _chua_nen_giay(han_giay)
    nt: dict = {}
    for p in plats:
        k = _KE[p](q, lims[p], ts, ctx)
        nt[p] = {"limit": lims[p], **k}
    # Không lượt con nào được dài hơn cửa sổ chạy actor; cả việc (2 lượt song song) cũng
    # không: dài hơn là chắc chắn bị huỷ giữa chừng ở hạn chót mà vẫn mất tiền.
    for p, x in nt.items():
        for ph in x["phan"]:
            if ph["actor"] == "youtube":
                continue
            toi_da = max(10, int((cua_so_apify - _GIAY_KHOI_DONG) * toc(ph["actor"])))
            if ph["limit"] > toi_da:
                x["chua_phu"].append(f"{ph['nhan']}: một lượt chỉ kịp ~{toi_da} bài trong hạn "
                                     f"{han_phut} phút (xin {ph['limit']}).")
                ph["limit"] = toi_da
    tong_giay = sum(_uoc_phan(p, ph)[1] for p, x in nt.items() for ph in x["phan"])
    if tong_giay > 2 * cua_so_apify:
        f = 2 * cua_so_apify / tong_giay
        for p, x in nt.items():
            truoc = sum(ph["limit"] for ph in x["phan"])
            for ph in x["phan"]:
                if ph["actor"] == "youtube":
                    continue
                ph["limit"] = max(10, int(ph["limit"] * f))
            sau = sum(ph["limit"] for ph in x["phan"])
            if sau < truoc and p != "youtube":
                x["chua_phu"].append(
                    f"{A._TEN_NGUON.get(p, p)}: cả việc không kịp hạn {han_phut} phút nên chỉ "
                    f"lấy ~{sau}/{truoc} bài (tốc độ ước tính ~{toc(x['phan'][0]['actor']):g} "
                    f"bài/giây).")
    return _hoan_tat(nt, ts, han_phut)


def _hoan_tat(nt: dict, ts: dict, han_phut: int) -> dict:
    usd = giay = 0.0
    for p, x in nt.items():
        u = g = 0.0
        for i, ph in enumerate(x["phan"]):
            ph.setdefault("id", f"{p}-{i}")
            ph.setdefault("trang_thai", "cho")
            if ph["actor"] != "youtube":
                ph["payload"] = dung_payload(p, ph, ts)
                ph["payload_sha"] = _sha(ph["payload"])
                if ph["actor"] in _RAM_NEN:
                    ph["mem"] = _RAM_NEN[ph["actor"]]
            a, b = _uoc_phan(p, ph)
            ph["uoc_usd"], ph["uoc_giay"] = a, round(b, 1)
            u += a
            g += b
        x.update(uoc_usd=round(u, 3), uoc_giay=round(g, 1),
                 limit_ke_hoach=sum(int(ph["limit"]) for ph in x["phan"]))
        usd += u
        giay += g
    sau = 120 + 30 * len(nt)         # lọc + AI (≤11 lượt, 2 song song) + ghi sheet
    phut = math.ceil((giay / 2 + sau) / 60)
    return {"nen_tang": nt, "uoc_usd": round(usd, 2), "uoc_giay": round(giay / 2 + sau),
            "uoc_phut": min(phut, han_phut)}


def thu_nho(kh: dict, ts: dict, han_phut: int, ngan_sach: float,
            chi: set | None = None, nhan: str | None = None) -> dict:
    """Cắt phần TRẢ TIỀN của kế hoạch cho vừa `ngan_sach` (YouTube không tốn tiền).
    `chi`: chỉ cắt các nền tảng này (trần riêng của một nền tảng / nhóm dùng trần chung);
    `nhan`: tên trần đưa vào `chua_phu`."""
    tra = sum(x["uoc_usd"] for p, x in kh["nen_tang"].items()
              if p != "youtube" and (chi is None or p in chi))
    if tra <= ngan_sach or tra <= 0:
        return kh
    f = max(0.0, ngan_sach / tra) * 0.95
    for p, x in kh["nen_tang"].items():
        if p == "youtube" or (chi is not None and p not in chi):
            continue
        truoc = sum(int(ph["limit"]) for ph in x["phan"])
        giu = []
        for ph in x["phan"]:
            moi = int(ph["limit"] * f)
            if moi >= 10:
                ph["limit"] = moi
                giu.append(ph)
        x["phan"] = giu
        sau = sum(int(ph["limit"]) for ph in giu)
        x["chua_phu"].append(f"{A._TEN_NGUON.get(p, p)}: cắt theo {nhan or 'ngân sách'} "
                             f"{ngan_sach:.2f} USD — chỉ ~{sau}/{truoc} bài.")
        for i, ph in enumerate(giu):
            ph["id"] = f"{p}-{i}"
    return _hoan_tat(kh["nen_tang"], ts, han_phut)


_DU_TRU_THANG = 0.30


def tran_usd_nen() -> float:
    """Trần USD console cho việc NỀN (tới 50) — đọc qua `_tran()` trong ngữ cảnh nền."""
    tok = A._NEN.set(True)
    try:
        return A._tran()[1]
    finally:
        A._NEN.reset(tok)


def ngan_sach(tran_usd: float) -> tuple[float, dict | None, str]:
    """(ngân sách việc, hạn mức tháng, ghi chú) = min(trần console, còn lại tháng − 0,30 −
    phần các việc nền KHÁC đang giữ). Review 02/10/2026: hai việc tạo gần nhau cùng thấy
    nguyên phần còn lại của tháng. `viec_nen.tao_viec` kiểm lại dưới khoá chung."""
    import viec_nen
    hm = A._han_muc_thang()
    cam = viec_nen.da_cam_ket()
    if not hm:
        return round(tran_usd, 2), None, ("không kiểm được ngân sách tháng Apify (bỏ qua bước "
                                          "hỏi trước) — chỉ chặn theo trần console")
    con = max(0.0, hm["con_lai"] - _DU_TRU_THANG - cam)
    return round(min(tran_usd, con), 2), hm, (
        f"tháng này Apify đã dùng ${hm['dung']:.2f}/${hm['tran']:g}, còn ${hm['con_lai']:.2f} "
        f"(chừa {_DU_TRU_THANG:.2f} dự trữ"
        + (f", các việc nền khác đang giữ ${cam:.2f}" if cam else "") + ")")


def _ctx_nguon(plats: list[str]) -> dict:
    """Thông tin nguồn bằng GET MIỄN PHÍ: gói Apify, lượt Facebook 24h, quota YouTube."""
    ctx: dict = {}
    if "facebook" in plats:
        ctx["goi"] = A._goi_apify()
        ctx["fb_luot"] = A._fb_luot_24h() if ctx["goi"] in ("FREE", "") and \
            A._kiem_truoc_bat() else None
    if "youtube" in plats:
        ctx["yt_con"] = A._youtube_con_trang(nen=True)
    return ctx


def tom_tat_ke_hoach(kh: dict) -> dict:
    return {p: {"limit_xin": x["limit"], "limit_ke_hoach": x["limit_ke_hoach"],
                "so_luot_chay": len(x["phan"]), "uoc_usd": x["uoc_usd"],
                "uoc_phut": round(x["uoc_giay"] / 60, 1), "chua_phu": x["chua_phu"] or None,
                "gioi_han_nguon": x["ghi_chu"] or None,
                **({"tran_console_usd_rieng": x["tran_usd_rieng"]} if x.get("tran_usd_rieng")
                   else {})}
            for p, x in kh["nen_tang"].items()}


def _tran_nhom(plats: list[str], tran_nen: float) -> tuple[dict, list[str], float]:
    """Trần USD việc nền theo nền tảng TRẢ TIỀN -> ({p: trần riêng}, nền tảng dùng trần
    chung, tổng trần của việc). Không nền tảng nào có `tran_usd_<p>` thì tổng = trần chung
    như trước; có thì mỗi nền tảng có trần riêng một ngân sách riêng, các nền tảng còn lại
    CHUNG `tran_nen`, tổng = cộng các phần (vẫn kẹp theo tháng ở `ngan_sach`)."""
    c = A._cau_hinh_quet()
    tra = [p for p in plats if p != "youtube"]
    rieng = {p: A._tran_nen_tang(p, nen=True, c=c)[1] for p in tra
             if "usd" in A._khoa_rieng(p, c)}
    chung = [p for p in tra if p not in rieng]
    if not rieng:
        return {}, chung, tran_nen
    return rieng, chung, round(sum(rieng.values()) + (tran_nen if chung else 0.0), 2)


def _can_giu(x: dict) -> float:
    """Tiền một nền tảng phải giữ được trong sổ để chạy đủ kế hoạch: mỗi lượt con giữ ít
    nhất `_can` (≥ 0,1 USD) dù ước tính nhỏ hơn — so trần riêng bằng số này, không thì kế
    hoạch "vừa trần" vẫn bị sổ từ chối ngay lượt đầu."""
    return max(float(x.get("uoc_usd") or 0), sum(_can(ph) for ph in x.get("phan") or []))


def _vua_tran(kh: dict, ts: dict, hp: int, u: float, p: str) -> dict:
    """Cắt kế hoạch của nền tảng `p` cho vừa trần riêng `u` (tính cả phần giữ tối thiểu)."""
    nhan = f"trần console của {A._TEN_NGUON.get(p, p)}"
    for _ in range(6):
        x = kh["nen_tang"].get(p)
        if not x or _can_giu(x) <= u + 1e-9:
            break
        du = max(0.0, _can_giu(x) - float(x["uoc_usd"]))
        kh = thu_nho(kh, ts, hp, max(0.0, u - du - 0.01), chi={p}, nhan=nhan)
    return kh


def _vuot_nhom(kh: dict, rieng: dict, chung: list[str], tran_nen: float) -> list[str]:
    """Câu cho từng trần riêng (và trần chung của nhóm còn lại) mà kế hoạch đang vượt."""
    nt = kh["nen_tang"]
    ra = [f"trần console của {A._TEN_NGUON.get(p, p)} là {A._usd_vn(u)} USD (ước tính "
          f"{A._usd_vn(round(_can_giu(nt[p]), 2))} USD)"
          for p, u in rieng.items() if p in nt and _can_giu(nt[p]) > u + 1e-9]
    tc = sum(nt[p]["uoc_usd"] for p in chung if p in nt)
    if rieng and chung and tc > tran_nen + 1e-9:
        ra.append(f"trần chung {A._usd_vn(tran_nen)} USD cho "
                  + ", ".join(A._TEN_NGUON.get(p, p) for p in chung)
                  + f" (ước tính {A._usd_vn(round(tc, 2))} USD)")
    return ra


# ───────────────────────────── cửa vào từ social_listen ─────────────────────────────
def xu_ly_lon(args: dict, *, queries, plats, lims, explicit, country, d_from, d_to,
              boi_canh, loai_tru, khop_long, giu_nuoc_ngoai, chi_thi_truong_nay,
              not_yet, limit_xin, tran_bai, tat=None) -> tuple[str | None, dict, str]:
    """Quyết định trước khi chạy tại chỗ. -> (kết quả tool trả NGAY | None, lims dùng cho
    lượt tại chỗ, ghi chú thêm cho lượt tại chỗ). `tat`: nền tảng chủ agent đã tắt
    (`_handle` đã bỏ khỏi `plats`) — chỉ để nói ra."""
    ep = args.get("chay_nen")
    ep = None if ep is None or ep == "" else A._co(ep)
    chi_uoc = A._co(args.get("chi_uoc_tinh"))
    # Facebook gói Free chỉ cho 20 bài/24h dù xin bao nhiêu: xét cỡ theo số THẬT lấy được,
    # kẻo "facebook 700 bài" bị đẩy sang nền để rồi cũng chỉ ra 20 bài.
    goi = A._goi_apify() if "facebook" in plats else None
    lims_xet = {p: (min(n, 20) if p == "facebook" and goi in ("FREE", "") else n)
                for p, n in lims.items()}
    giay = giay_tai_cho(plats, lims_xet, queries)
    nen, vi_sao = can_chay_nen(lims_xet, giay, ep)
    import viec_nen
    ts = {"queries": A._bo_trung_tu_khoa(queries), "platforms": plats, "limit": lims,
          "date_from": f"{d_from:%Y-%m-%d}", "date_to": f"{d_to:%Y-%m-%d}",
          "country": country, "boi_canh": boi_canh, "exclude": loai_tru,
          "khop_long": khop_long, "giu_nuoc_ngoai": giu_nuoc_ngoai,
          "chi_thi_truong_nay": chi_thi_truong_nay,
          "title": str(args.get("title") or "").strip()}
    if nen and not viec_nen.bat():
        moi = kep_tai_cho(lims)
        return None, moi, (f"Chạy nền đang TẮT (SOCIAL_QUET_NEN=0) nên lượt này bị kẹp về cỡ "
                           f"chạy tại chỗ {moi} (xin {lims}; lý do cần nền: {vi_sao}). Nói rõ.")
    if not nen and not chi_uoc:
        return None, lims, ""
    tran_nen = tran_usd_nen()
    # Thử thật 02/10/2026: xin 1500 video nhưng trần console 112 → Mark nói "nguồn chỉ cho
    # tối đa 112", người dùng tưởng nguồn yếu. Đây là trần CHỦ AGENT đặt, phải nói đúng.
    # Có trần RIÊNG theo nền tảng (02/10/2026) thì nói từng nền tảng: "trần console của
    # TikTok là 200 bài" — câu trần chung sẽ sai với nền tảng có trần riêng.
    rieng_bai = A._cau_tran_rieng(plats, limit_xin)
    cau_tran = (f" Người dùng xin {limit_xin} bài/nền tảng nhưng TRẦN TRÊN CONSOLE (Năng lực "
                f"→ Quét mạng xã hội) đang trói: {rieng_bai} — nói rõ đây là trần chủ agent "
                "đặt, KHÔNG phải giới hạn của nguồn; muốn nhiều hơn thì nhờ chủ agent nâng."
                if rieng_bai else
                f" Người dùng xin {limit_xin} bài/nền tảng nhưng TRẦN TRÊN CONSOLE (Năng lực "
                f"→ Quét mạng xã hội) đang là {tran_bai} bài/nền tảng — nói rõ đây là trần chủ "
                "agent đặt, KHÔNG phải giới hạn của nguồn; muốn nhiều hơn thì nhờ chủ agent nâng."
                if limit_xin and tran_bai and limit_xin > tran_bai else "")
    tat = list(tat or [])
    cau_tat = ""
    if tat:
        cau_tat = (("NỀN TẢNG CHỦ AGENT ĐÃ TẮT — nói ĐẦU TIÊN: " if explicit else
                    "Nhắc một lần: ")
                   + "; ".join(A._ly_do_tat(p) for p in tat) + " — không quét. ")
    tran_nt = ({p: dict(zip(("tran_bai", "tran_usd_moi_luot"),
                            A._tran_nen_tang(p, nen=nen)[:2])) for p in plats}
               if any(A._khoa_rieng(p) for p in plats) else None)
    if not nen:
        so_luot = {p: (len(queries) if p in ("instagram", "facebook") else 1) for p in plats}
        est_tai_cho = sum(
            A._START_COST.get(p, 0.0) * so_luot[p]
            + A._UNIT_COST.get(p, 0.0) * lims[p] for p in plats)
        rieng_usd = A._cau_tran_rieng(plats, None, {
            p: A._START_COST.get(p, 0.0) + A._UNIT_COST.get(p, 0.0) * lims[p] / so_luot[p]
            for p in plats}, nen=False)
        return tool_result(
            success=True, chi_uoc_tinh=True, se_chay_nen=False, queries=queries,
            platforms=plats, limit=lims, uoc_tinh_usd=round(est_tai_cho, 2),
            uoc_tinh_giay=giay, tran_chi_phi_usd_moi_luot=A._tran()[1],
            tran_bai_console=tran_bai, tran_theo_nen_tang=tran_nt, nen_tang_tat=tat or None,
            note=(cau_tat
                  + "CHƯA CHẠY gì, chưa tốn tiền (chỉ ước tính). Lượt này nhỏ, sẽ chạy ngay "
                  f"trong câu trả lời (~{giay:.0f} giây, ~{est_tai_cho:.2f} USD). Báo phạm vi "
                  "+ ước tính cho người dùng rồi KẾT THÚC bằng \"Chạy nhé?\"; đồng ý thì gọi "
                  "lại KHÔNG có `chi_uoc_tinh`." + cau_tran
                  + (f" Trần riêng trói lượt này: {rieng_usd} — Apify dừng ở trần, nền tảng đó "
                     "có thể thiếu bài; nói rõ." if rieng_usd else ""))), lims, ""
    hp = viec_nen.han_phut()
    ctx = _ctx_nguon(plats)
    ma = None
    if "youtube" in plats and not chi_uoc:
        # Giữ chỗ NGUYÊN TỬ số trang search cần, theo mã việc định trước (review 02/10/2026:
        # hai việc cùng lập kế hoạch thấy chung phần quota rồi cùng dùng hết).
        ma = viec_nen.ma_moi("social_listen")
        ctx["yt_con"] = A._youtube_giu(ma, math.ceil(lims["youtube"] / 50))
    kh = ke_hoach(queries, plats, lims, ts, hp, ctx)
    # Trần USD theo nền tảng (02/10/2026): nền tảng có `tran_usd_<p>` có ngân sách riêng,
    # các nền tảng còn lại chung trần console; tổng việc vẫn ≤ phần còn lại của tháng.
    rieng, chung, tong_tran = _tran_nhom(plats, tran_nen)
    ns, hm, cau_ns = ngan_sach(tong_tran)
    tra_tien = sum(x["uoc_usd"] for p, x in kh["nen_tang"].items() if p != "youtube")
    thieu = round(max(0.0, tra_tien - ns), 2)
    vuot = _vuot_nhom(kh, rieng, chung, tran_nen)
    cat = A._co(args.get("cat_theo_ngan_sach"))
    if (thieu or vuot) and cat:
        for p, u in rieng.items():
            kh = _vua_tran(kh, ts, hp, u, p)
        if rieng and chung:
            kh = thu_nho(kh, ts, hp, tran_nen, chi=set(chung), nhan="trần chung")
        kh = thu_nho(kh, ts, hp, ns)
        thieu, vuot = 0.0, []
    for p, x in kh["nen_tang"].items():
        if p in rieng:
            x["tran_usd_rieng"] = rieng[p]
        elif p in chung and rieng:
            x["tran_usd_chung"] = round(tran_nen, 2)
    cau_vuot = ("; ".join(vuot) + " — trần chủ agent đặt trên console (Năng lực → Quét "
                "mạng xã hội)") if vuot else ""
    base = dict(queries=queries, platforms=plats, limit_xin=limit_xin, tran_bai=tran_bai,
                ly_do_chay_nen=vi_sao, uoc_tinh_usd=kh["uoc_usd"],
                uoc_tinh_phut=kh["uoc_phut"], han_phut=hp, ngan_sach_usd=ns,
                tran_console_usd=tran_nen, ngan_sach_thang=cau_ns,
                thieu_ngan_sach_usd=thieu or None, vuot_tran_nen_tang=cau_vuot or None,
                tran_theo_nen_tang=tran_nt, nen_tang_tat=tat or None,
                per_platform=tom_tat_ke_hoach(kh), platforms_not_supported=not_yet,
                goi_y_nen_tang=(None if explicit else
                                "Chưa chỉ định nền tảng nên mỗi nền tảng chỉ quét nông; "
                                "muốn nhiều bài thì hỏi người dùng quét nền tảng nào."))
    if chi_uoc:
        return tool_result(
            success=True, chi_uoc_tinh=True, se_chay_nen=True, **base,
            note=(cau_tat
                  + "CHƯA CHẠY gì, chưa tốn tiền (chỉ ước tính bằng lượt hỏi miễn phí). Lượt "
                  "này LỚN nên sẽ CHẠY NỀN. Báo người dùng: ước tính ~"
                  f"{kh['uoc_usd']:.2f} USD, ~{kh['uoc_phut']} phút, giới hạn từng nguồn "
                  "(`per_platform.*.chua_phu` / `gioi_han_nguon`)"
                  + (f", THIẾU ngân sách {thieu:.2f} USD (ngân sách {ns:.2f} USD — đề xuất "
                     "cắt theo ngân sách `cat_theo_ngan_sach`=true hoặc bớt nền tảng/bài)"
                     if thieu else "")
                  + (f", VƯỢT {cau_vuot} — đề xuất `cat_theo_ngan_sach`=true (cắt số bài "
                     "nền tảng đó cho vừa trần) hoặc nhờ chủ agent nâng" if vuot else "")
                  + ". Lần này PHẢI nói số USD ước tính (ngoại lệ của luật không tự nói chi "
                  "phí). KẾT THÚC bằng \"Chạy nhé?\"; đồng ý thì gọi lại y tham số, bỏ "
                  "`chi_uoc_tinh`." + cau_tran)), lims, ""
    if thieu or vuot:
        if ma:
            A._youtube_tra(ma)
        return tool_result(
            success=False, chua_chay=True, vuot_ngan_sach=True, **base,
            note=(cau_tat + "CHƯA CHẠY, chưa tốn tiền: "
                  + (f"ước tính phần trả tiền {tra_tien:.2f} USD vượt ngân sách {ns:.2f} USD "
                     f"({cau_ns})" if thieu else "")
                  + ("; " if thieu and vuot else "") + (f"vượt {cau_vuot}" if vuot else "")
                  + ". Nói đúng như vậy; đề xuất chạy với "
                  "`cat_theo_ngan_sach`=true (cắt số bài cho vừa), bớt nền tảng/bài, hoặc chỉ "
                  "YouTube (miễn phí).")), lims, ""
    if not any(x["phan"] for x in kh["nen_tang"].values()):
        if ma:
            A._youtube_tra(ma)
        return tool_result(success=False, chua_chay=True, **base,
                           note=cau_tat + "Không còn lượt nào chạy được (xem `chua_phu` từng "
                                          "nguồn). Nói rõ từng nguồn vì sao."), lims, ""
    tom = viec_nen.tao_viec(
        "social_listen", ts, kh["nen_tang"],
        {"usd": kh["uoc_usd"], "phut": kh["uoc_phut"], "giay": kh["uoc_giay"]}, ns,
        ghi_chu=[cau_ns] + (["không chỉ định nền tảng"] if not explicit else []),
        ma=ma, con_lai_thang=hm["con_lai"] if hm else None)
    if ma and tom.get("ma_viec") != ma:
        A._youtube_tra(ma)               # trùng việc cũ / bị từ chối: trả chỗ đã giữ
    kq = {**base, **tom, "success": not tom.get("tu_choi")}
    if cau_tat:
        kq["note"] = cau_tat + str(kq.get("note") or "")
    return tool_result(**kq), lims, ""


# ───────────────────────────── chạy việc ─────────────────────────────
_KET_PHAN = ("xong", "mot_phan", "loi", "da_huy")


def _dung_so(tran: float, cac: list):
    """Dựng một sổ tiền từ các lượt con (đúng cả sau khi khởi động lại)."""
    from deep_dive_tool import _SoNganSach
    da = giu = cho = 0.0
    for _, ph in cac:
        if ph["actor"] == "youtube":
            continue
        st = ph.get("trang_thai")
        if st in _KET_PHAN:
            # `usd_so` = đúng số đã trừ vào sổ lúc lượt con kết thúc (max(tiền Apify báo,
            # giá × item)); `usd` của run có thể None/cũ vì Apify ghi tiền chậm (review
            # 02/10/2026) -> dựng lại sổ sau khởi động thấp hơn thật, tiêu quá ngân sách.
            da += float(ph["usd_so"] if ph.get("usd_so") is not None else ph.get("usd") or 0)
        elif st in ("dang_gui", "dang_chay") and ph.get("tran_usd"):
            giu += float(ph["tran_usd"])
        else:
            cho += _can(ph)
    ns = _SoNganSach(float(tran or 0), cho)
    ns.da, ns.giu = da, giu
    return ns


class _SoTheoNenTang:
    """Sổ tiền của việc khi có trần USD RIÊNG theo nền tảng (02/10/2026): mỗi lượt con xin
    ở sổ NHÓM của nền tảng nó (trần riêng `tran_usd_<p>`, hoặc nhóm chung trần console)
    rồi ở sổ CHUNG của việc (ngân sách việc ≤ tháng). Trần gửi Apify = phần nhỏ hơn, nên
    các lượt con của một nền tảng không bao giờ tiêu quá trần của nền tảng đó. Một nhóm
    từ chối thì chỉ nhóm đó dừng; sổ chung từ chối thì cả việc dừng (như `_SoNganSach`)."""

    def __init__(self, chung, nhom: dict, cua: dict):
        self.chung, self.nhom, self.cua = chung, nhom, cua
        self._khoa = threading.Lock()

    @property
    def da(self) -> float:
        return self.chung.da

    @property
    def giu(self) -> float:
        return self.chung.giu

    def xin(self, can: float, tran_lo: float, p: str | None = None) -> float:
        n = self.nhom.get(self.cua.get(p))
        with self._khoa:
            if n is None:
                return self.chung.xin(can, tran_lo)
            cap_n = n.xin(can, tran_lo)
            if not cap_n:
                self.chung.bo(can)          # lượt này không chạy: trả phần để dành chung
                return 0.0
            cap = self.chung.xin(can, cap_n)
            if cap < cap_n:
                n.tra(cap_n - cap, 0.0)     # nhóm chỉ giữ đúng phần sổ chung cấp
            return cap

    def tra(self, giu: float, thuc: float, p: str | None = None) -> None:
        n = self.nhom.get(self.cua.get(p))
        with self._khoa:
            if n is not None:
                n.tra(giu, thuc)
            self.chung.tra(giu, thuc)


def _so_ngan_sach(v):
    chung = _dung_so(float(v.d.get("ngan_sach_usd") or 0), list(v.cac_phan()))
    nt = v.d.get("nen_tang") or {}
    if not any(x.get("tran_usd_rieng") for x in nt.values()):
        return chung
    cua = {p: (p if x.get("tran_usd_rieng") else "_chung") for p, x in nt.items()
           if x.get("tran_usd_rieng") or x.get("tran_usd_chung")}
    tran = {p: float(nt[p]["tran_usd_rieng"]) for p in cua if cua[p] == p}
    tran.update({"_chung": float(nt[p]["tran_usd_chung"]) for p in cua if cua[p] == "_chung"})
    nhom = {k: _dung_so(t, [(p, ph) for p, ph in v.cac_phan() if cua.get(p) == k])
            for k, t in tran.items()}
    return _SoTheoNenTang(chung, nhom, cua)


def _can(ph: dict) -> float:
    """Phần trần một lượt con CẦN giữ để được chạy (deep_dive đặt sẵn `can` = mức actor đòi)."""
    if ph.get("can"):
        return float(ph["can"])
    return max(A._TRAN_USD_KHOANG[0], math.floor(float(ph.get("uoc_usd") or 0) * 100) / 100)


def _tran_lo(ph: dict) -> float:
    if ph.get("tran_lo"):
        return float(ph["tran_lo"])
    return max(A._TRAN_USD_KHOANG[0], math.ceil(float(ph.get("uoc_usd") or 0) * 150) / 100)


def _chuan_hoa(p: str, ph: dict, items: list) -> list[tuple]:
    if p == "tiktok":
        if ph.get("kieu") == "do":
            return A._chuan_tiktok([it for it in items if not it.get("noResults")])
        return A._chuan_tiktok(A._chuan_clockworks(items))
    return {"instagram": A._chuan_instagram, "facebook": A._chuan_facebook,
            "threads": A._chuan_threads}[p](items)


def _ket_phan(v, ph: dict, meta: dict, n: int, loi: Exception | None = None,
              usd_so: float | None = None) -> None:
    ma = (getattr(loi, "ma", None) or "LOI") if loi else (meta.get("ma") or "OK")
    st = ("da_huy" if ma == "DA_HUY" else "loi" if loi and not n else
          "xong" if ma == "OK" else "mot_phan")
    kw = dict(trang_thai=st, so_item=n, ma=ma,
              ly_do=A._che_token(str(loi) if loi else meta.get("ly_do") or "")[:300],
              usd=meta.get("usd"), giay=meta.get("giay"),
              run_id=meta.get("run_id") or ph.get("run_id"))
    if usd_so is not None:
        kw["usd_so"] = usd_so
    v.cap_nhat_phan(ph, **kw)


def _h() -> dict:
    return {"Authorization": f"Bearer {os.environ.get('APIFY_TOKEN', '').strip()}"}


_CAU_KHONG_KIEM = ("không kiểm được run cũ trên Apify — KHÔNG chạy lại để khỏi trả tiền hai "
                   "lần; phần này coi như thiếu")


def _so_tien(p: str, ph: dict, items: list, meta: dict) -> float:
    gia = ph.get("gia") or (_GIA_DO if ph.get("kieu") == "do" else _GIA.get(p, 0.0))
    uoc = len(items or []) * float(gia) + (A._START_COST.get(p, 0.0) if items else 0.0)
    return round(max(float(meta.get("usd") or 0), uoc), 4)


def _mot_phan(v, p: str, ph: dict, ns, ts: dict, chuan=None) -> int:
    """Chạy / đọc tiếp MỘT lượt con trong luồng riêng. -> số item lấy được."""
    A._NEN.set(True)
    A._HUY.set(v.co_dung)
    if ph["actor"] == "youtube":
        A._YT_MA.set(v.ma)
        return _mot_phan_youtube(v, ph, ts)
    actor, payload = ph["actor"], ph["payload"]
    han = v.han_mono(_chua_nen_giay(60.0 * v.d.get("han_phut", 45)))
    A._KHI_CO_RUN.set(lambda run, meta: v.cap_nhat_phan(
        ph, run_id=run.get("id"), dataset_id=run.get("defaultDatasetId"),
        trang_thai="dang_chay"))
    cap = float(ph.get("tran_usd") or 0) if ph.get("trang_thai") in ("dang_gui",
                                                                      "dang_chay") else 0.0
    meta: dict = {}
    items: list = []
    loi = None
    theo_p = {"p": p} if isinstance(ns, _SoTheoNenTang) else {}
    if not cap:
        cap = ns.xin(_can(ph), _tran_lo(ph), **theo_p)
        if not cap:
            n = ns.nhom.get(p) if theo_p else None
            v.cap_nhat_phan(ph, trang_thai="loi", ma="NGAN_SACH", so_item=0, usd_so=0.0,
                            ly_do=(f"hết trần console của {A._TEN_NGUON.get(p, p)} "
                                   f"({A._usd_vn(n.tran)} USD) — lượt này chưa chạy"
                                   if n is not None and n.dung else
                                   "hết ngân sách của việc — lượt này chưa chạy"))
            return 0
    try:
        if ph.get("run_id"):
            items, meta = A._doc_tiep_run(ph["run_id"], int(ph["limit"]), han, True, actor)
        else:
            run = None
            if ph.get("trang_thai") == "dang_gui" and ph.get("moc_gui"):
                # Khởi động lại khi POST đang dở: run có thể ĐÃ được tạo. Nhận khi đọc được
                # INPUT và trùng payload. KHÔNG kiểm được (danh sách run / INPUT hỏng) thì
                # KHÔNG POST lại (review 02/10/2026) — đánh dấu lỗi, giữ phần trần đã giữ.
                run, kiem = A._tim_run_vua_tao_ex(
                    actor, payload, _h(), datetime.datetime.fromisoformat(ph["moc_gui"]),
                    nghiem=True)
                if not run and not kiem:
                    ns.tra(cap, cap, **theo_p)
                    v.cap_nhat_phan(ph, trang_thai="loi", ma="KHONG_KIEM_DUOC", so_item=0,
                                    usd_so=cap, ly_do=_CAU_KHONG_KIEM)
                    return 0
            if run:
                v.cap_nhat_phan(ph, run_id=run["id"], trang_thai="dang_chay",
                                dataset_id=run.get("defaultDatasetId"), nhan_lai=True)
                items, meta = A._doc_tiep_run(run["id"], int(ph["limit"]), han, True, actor)
            else:
                v.cap_nhat_phan(ph, trang_thai="dang_gui", tran_usd=cap,
                                moc_gui=datetime.datetime.now(A._VN_TZ).isoformat())
                items, meta = A._run_actor(actor, payload, int(ph["limit"]), ph.get("mem"),
                                           han, float(ph.get("min_charge") or 0),
                                           tran_usd=cap, mot_phan=True)
    except A.LoiApify as e:
        loi, meta = e, e.meta
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ == "MatQuyen":
            raise
        loi = A.LoiApify("LOI", A._che_token(f"{type(e).__name__}: {e}")[:250])
        meta = loi.meta
    tien = _so_tien(p, ph, items, meta)
    if loi is not None and meta.get("khong_kiem_duoc"):
        tien = cap                       # POST mơ hồ, không kiểm được: coi như đã tiêu trần
    ns.tra(cap, tien, **theo_p)
    rows = (chuan or _chuan_hoa)(p, ph, items or [])
    if rows:
        v.ghi_dong(p, rows, ph["id"])
    _ket_phan(v, ph, meta, len(items or []), loi, usd_so=tien)
    if ph["trang_thai"] == "xong" and not meta.get("doc_tiep"):
        cap_nhat_toc(actor, len(items), float(meta.get("giay") or 0))
    return len(items or [])


def _thu_don(v, p: str, ph: dict, chuan=None) -> None:
    """Đóng MỘT lượt con chưa kết thúc khi việc dừng (huỷ / tới hạn / khởi động lại muộn /
    lô treo). Review 02/10/2026: trước đây chỉ ĐÁNH DẤU QUA_GIO/da_huy, run trên Apify vẫn
    chạy và tính tiền. Nay: có run id -> huỷ-và-lấy (`_doc_tiep_run` hạn = bây giờ); đang
    gửi dở -> tìm run vừa tạo trước (không kiểm được thì báo lỗi, KHÔNG POST); chưa gửi ->
    đánh dấu chưa chạy. Giữ phần item và số tiền thật."""
    st = ph.get("trang_thai")
    if st in _KET_PHAN:
        return
    ma_dung = "DA_HUY" if v.da_huy() else "QUA_GIO"
    if ph["actor"] == "youtube":
        v.cap_nhat_phan(ph, trang_thai="da_huy" if ma_dung == "DA_HUY" else "loi",
                        ma=ma_dung, so_item=0, usd_so=0.0,
                        ly_do="việc dừng trước khi chạy lượt này")
        return
    rid = ph.get("run_id")
    if not rid and st == "dang_gui" and ph.get("moc_gui"):
        run, kiem = A._tim_run_vua_tao_ex(
            ph["actor"], ph["payload"], _h(), datetime.datetime.fromisoformat(ph["moc_gui"]),
            nghiem=True)
        if run:
            rid = run["id"]
            v.cap_nhat_phan(ph, run_id=rid, nhan_lai=True)
        elif not kiem:
            v.cap_nhat_phan(ph, trang_thai="loi", ma="KHONG_KIEM_DUOC", so_item=0,
                            usd_so=float(ph.get("tran_usd") or 0), ly_do=_CAU_KHONG_KIEM)
            return
    if not rid:
        v.cap_nhat_phan(ph, trang_thai="da_huy" if ma_dung == "DA_HUY" else "loi",
                        ma=ma_dung, so_item=0, usd_so=0.0,
                        ly_do=("huỷ trước khi chạy lượt này" if ma_dung == "DA_HUY"
                               else "không kịp hạn chót — lượt này chưa chạy"))
        return
    try:
        items, meta = A._doc_tiep_run(rid, int(ph["limit"]), A._dong_ho(), True, ph["actor"])
        loi = None
    except A.LoiApify as e:
        items, meta, loi = [], e.meta, e
    rows = (chuan or _chuan_hoa)(p, ph, items)
    if rows:
        v.ghi_dong(p, rows, ph["id"])
    _ket_phan(v, ph, meta, len(items), loi, usd_so=_so_tien(p, ph, items, meta))
    if ph["trang_thai"] == "xong" and meta.get("da_huy"):
        v.cap_nhat_phan(ph, trang_thai="mot_phan")


def _thu_don_het(v, chuan=None) -> None:
    """Đóng MỌI lượt con chưa kết thúc (ngữ cảnh riêng: `_NEN` + cờ dừng của việc)."""
    def chay():
        A._NEN.set(True)
        A._HUY.set(v.co_dung)
        for p, ph in list(v.cac_phan()):
            if ph.get("trang_thai") not in _KET_PHAN:
                _thu_don(v, p, ph, chuan)
    contextvars.copy_context().run(chay)


def _mot_phan_youtube(v, ph: dict, ts: dict) -> int:
    # Trang đã GIỮ CHỖ cho việc này lúc lập kế hoạch (`_youtube_giu`) + phần chung còn lại.
    con = A._youtube_con_trang(nen=True, ma=v.ma)
    k = min(int(ph["so_trang"]), con)
    if v.da_huy():
        v.cap_nhat_phan(ph, trang_thai="da_huy", ma="DA_HUY", so_item=0)
        return 0
    if k <= 0:
        v.cap_nhat_phan(ph, trang_thai="loi", ma="HET_QUOTA", so_item=0,
                        ly_do="hết quota YouTube dành cho việc nền hôm nay (giờ PT)")
        return 0
    tu = A._parse_date(ph["tu"], end=False)
    den = A._parse_date(ph["den"], end=True)
    try:
        rows, so_trang, bi_cat = A._youtube_tim(ts["queries"], k * 50, ts["country"], tu,
                                                den, toi_da_trang=k)
    except Exception as e:  # noqa: BLE001 — key YouTube không bao giờ nằm trong lỗi
        v.cap_nhat_phan(ph, trang_thai="loi", ma="LOI", so_item=0,
                        ly_do=A._che_token(str(e))[:250])
        return 0
    if rows:
        v.ghi_dong("youtube", rows, ph["id"])
    v.cap_nhat_phan(ph, trang_thai="mot_phan" if k < ph["so_trang"] else "xong",
                    so_item=len(rows), ma="OK", trang_dung=so_trang, usd_so=0.0,
                    ly_do=(f"chỉ được {k}/{ph['so_trang']} trang (quota)"
                           if k < ph["so_trang"] else ""))
    return len(rows)


def _thu_tu_phan(v) -> list[tuple]:
    """Lượt con CHƯA xong, xen kẽ giữa các nền tảng (một nền tảng không chiếm hết chỗ)."""
    theo: dict = {}
    for p, ph in v.cac_phan():
        if ph.get("trang_thai") not in _KET_PHAN:
            theo.setdefault(p, []).append(ph)
    ra = []
    while any(theo.values()):
        for p in list(theo):
            if theo[p]:
                ra.append((p, theo[p].pop(0)))
    # Lượt đang chạy dở (có run id / đang gửi) trước: đọc tiếp chúng là miễn phí.
    ra.sort(key=lambda x: x[1].get("trang_thai") not in ("dang_chay", "dang_gui"))
    return ra


def _xong_nen_tang(v, p: str) -> bool:
    return all(ph.get("trang_thai") in _KET_PHAN
               for ph in (v.d["nen_tang"].get(p) or {}).get("phan") or [])


def _chay_cac_phan(v, ns, ts: dict, so_bo, chuan=None) -> None:
    viec = _thu_tu_phan(v)
    du_phong = _chua_nen_giay(60.0 * v.d.get("han_phut", 45))
    # KHÔNG `with`: `with` chờ mọi luồng xong nên hạn chót vô hiệu (xem apify_tool._handle).
    ex = ThreadPoolExecutor(max_workers=2)
    dang: dict = {}
    da_ghi_so_bo: set = set()
    try:
        while viec or dang:
            while viec and len(dang) < 2:
                if v.da_huy() or v.con_giay() < du_phong + 30:
                    break
                p, ph = viec.pop(0)
                dang[ex.submit(contextvars.copy_context().run, _mot_phan, v, p, ph, ns,
                               ts, chuan)] = (p, ph)
            if not dang:
                break
            xong, _ = wait(dang, timeout=max(5.0, v.con_giay() + 60), return_when=FIRST_COMPLETED)
            if not xong:
                # Lô treo quá hạn: bật cờ dừng (vòng hỏi trạng thái của nó tự huỷ run trong
                # ~15s), chờ thêm chút rồi tự đóng những lượt còn dở (`_thu_don_het` dưới).
                v.dung.set()
                wait(dang, timeout=30)
                break
            for f in xong:
                p, ph = dang.pop(f)
                try:
                    f.result()
                except Exception as e:  # noqa: BLE001
                    v.cap_nhat_phan(ph, trang_thai="loi", ma="LOI",
                                    ly_do=A._che_token(f"{type(e).__name__}: {e}")[:250])
                if (p not in da_ghi_so_bo and _xong_nen_tang(v, p)
                        and not any(q == p for q, _ in viec)):
                    da_ghi_so_bo.add(p)
                    so_bo(p)
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    # Lượt chưa chạy / đang chạy dở (huỷ, gần hạn, lô treo): HUỶ run trên Apify và giữ phần
    # đã có — không chỉ đánh dấu (review 02/10/2026).
    _thu_don_het(v, chuan)


def _dong_phan_dang_chay(v, ts: dict, chuan=None) -> None:
    """Khởi động lại SAU hạn chót: huỷ run còn sống, giữ phần đã có, không chạy gì mới."""
    v.dung.set()
    _thu_don_het(v, chuan)


# ───────────────────────────── lọc + phân xử theo tầng ─────────────────────────────
def _chuan_link(u: str) -> str:
    s = re.sub(r"^https?://(?:www\.|m\.)?", "", str(u or "").strip().lower()).split("#")[0]
    if re.match(r"(?:[\w-]+\.)?(?:tiktok|instagram|threads)\.(?:com|net)", s):
        s = s.split("?")[0]
    return s.rstrip("/")


_RE_QUOTA = re.compile(r"(?i)quota|rate.?limit|\b429\b|insufficient|exceeded|too many "
                       r"requests|usage limit|hết hạn mức")
_MAU_KIEM = 120


def _ai_toi_da_luot() -> int:
    return A._so_env("SOCIAL_AI_NEN_TOI_DA_LUOT", 10, 0, 100)


def _cache_doc(v) -> dict:
    ra = {}
    try:
        with open(v.thu_muc() / "phan_xu.jsonl", encoding="utf-8") as fh:
            for l in fh:
                try:
                    x = json.loads(l)
                    ra[x["k"]] = tuple(x["v"])
                except (ValueError, KeyError, TypeError):
                    continue
    except OSError:
        pass
    return ra


def _cache_ghi(v, moi: dict) -> None:
    if not moi:
        return
    with open(v.thu_muc() / "phan_xu.jsonl", "a", encoding="utf-8") as fh:
        for k, val in moi.items():
            fh.write(json.dumps({"k": k, "v": list(val)}, ensure_ascii=False) + "\n")


def _khoa_link(d: dict) -> str:
    return hashlib.sha1((_chuan_link(d.get("link")) or str(d.get("text"))[:200])
                        .encode("utf-8")).hexdigest()


def _tang(d: dict, ts: dict) -> str:
    """'giu_ro' | 'loai_ro' | 'mo_ho' — tầng luật trước AI."""
    p = d["platform"]
    nhom, _ = A._ly_do_loai(d, p, ts["queries"], [], ts["country"], ts["boi_canh"],
                            ts["khop_long"], ts["giu_nuoc_ngoai"])
    if d.get("_khop") and not nhom and d.get("_thi_truong") == ts["country"]:
        return "giu_ro"
    if not d.get("_khop") and int(d.get("views") or 0) < _view_toi_thieu():
        return "loai_ro"
    return "mo_ho"


def _view_toi_thieu() -> int:
    return A._so_env("SOCIAL_AI_NEN_VIEW_TOI_THIEU", 1000, 0, 10 ** 9)


def _kenh_khoa(d: dict) -> str:
    return f"{d.get('platform')}|{A._norm(d.get('kenh') or '')}|{A._norm(d.get('username') or '')}"


def _phan_xu_tang(rows: list, ts: dict, han_mono: float, log: list, *, cache: dict | None = None,
                  ma: str = "", toi_da_luot: int | None = None,
                  song_song: int = 2) -> tuple[dict, dict]:
    """Phân xử theo TẦNG cho việc nền -> ({i: (giữ, mã, ghi chú, nguồn)}, thống kê).

    10.000 bài × 120 bài/lượt model = 84 lượt, quota model dùng chung với bot chính — không
    gánh nổi. Nên: luật giữ bài CHẮC (nhắc từ khoá + đúng thị trường + luật không nghi), luật
    loại bài CHẮC (không nhắc từ khoá, ít view); AI chỉ đọc bài MƠ HỒ, nhiều view trước,
    tối đa `SOCIAL_AI_NEN_TOI_DA_LUOT` (10) lượt, 2 lượt song song, gặp lỗi quota lần đầu là
    dừng (phần còn lại theo luật). Phán của AI lan theo KÊNH (≥2 phán cùng chiều). Thêm MỘT
    lượt kiểm mẫu 120 bài luật đã giữ để đo luật sai bao nhiêu. Cache phán theo sha1(link):
    khởi động lại không hỏi model lại bài đã hỏi."""
    cache = {} if cache is None else cache
    toi_da_luot = _ai_toi_da_luot() if toi_da_luot is None else toi_da_luot
    tang = [_tang(d, ts) for d, _ in rows]
    tt = {"tong": len(rows), "giu_ro": tang.count("giu_ro"), "loai_ro": tang.count("loai_ro"),
          "mo_ho": tang.count("mo_ho"), "luot_ai": 0, "ai_xet": 0, "theo_kenh": 0,
          "tu_cache": 0, "dung_vi_quota": False, "mau_kiem": None, "trang_thai": ""}
    ket: dict = {}
    for i, (d, _) in enumerate(rows):
        v = cache.get(_khoa_link(d))
        if v:
            ket[i] = (bool(v[0]), v[1], v[2] if len(v) > 2 else "", "AI")
            tt["tu_cache"] += 1
    ly_do = ("tắt (SOCIAL_AI_PHAN_XU=0)" if not A._ai_phan_xu_bat() else
             "thiếu boi_canh" if not ts.get("boi_canh") else
             "không có bài mơ hồ" if not tt["mo_ho"] and not tt["giu_ro"] else "")
    moi: dict = {}

    def mot_dot(chi_so: list[int], n_lo: int) -> dict:
        han = min(han_mono, time.monotonic() + 150)
        if han - time.monotonic() < A._AI_TOI_THIEU_GIAY:
            return {"trang_thai": "bỏ qua: hết thời gian", "so_lo": 0}
        r, t = A._phan_xu_ai(rows, ts["queries"], ts["boi_canh"], ts["country"], han, log,
                             toi_da=n_lo * A._AI_LO, song_song=min(song_song, n_lo),
                             thu_tu=chi_so)
        for i, val in r.items():
            ket[i] = (*val, "AI")
            moi[_khoa_link(rows[i][0])] = val
        t["_ra"] = len(r)
        return t

    if not ly_do:
        mo = sorted((i for i, t in enumerate(tang) if t == "mo_ho" and i not in ket),
                    key=lambda i: (-int(rows[i][0].get("views") or 0), i))
        con = toi_da_luot
        while mo and con > 0 and not tt["dung_vi_quota"]:
            n_lo = min(song_song, con, math.ceil(len(mo) / A._AI_LO))
            dot, mo = mo[:n_lo * A._AI_LO], mo[n_lo * A._AI_LO:]
            t = mot_dot(dot, n_lo)
            tt["luot_ai"] += t.get("so_lo", 0)
            con -= max(1, t.get("so_lo", 0))
            tt["ai_xet"] += t.get("_ra", 0)
            if _RE_QUOTA.search(str(t.get("loi_cuoi") or "")):
                tt["dung_vi_quota"] = True
                log.append("phan_xu_tang: model báo hết quota — dừng AI, phần còn lại theo luật")
            if str(t.get("trang_thai", "")).startswith("bỏ qua: hết thời gian"):
                break
        # Lượt kiểm MẪU luật: 120 bài luật đã giữ, chọn ổn định theo mã việc.
        giu = [i for i, t in enumerate(tang) if t == "giu_ro" and i not in ket]
        if giu and not tt["dung_vi_quota"] and toi_da_luot > 0:
            rd = random.Random(ma or "mau")
            mau = sorted(rd.sample(giu, min(_MAU_KIEM, len(giu))))
            t = mot_dot(mau, 1)
            tt["luot_ai"] += t.get("so_lo", 0)
            da = [i for i in mau if i in ket]
            tt["mau_kiem"] = {"xet": len(da), "ai_giu": sum(1 for i in da if ket[i][0]),
                              "ai_loai": sum(1 for i in da if not ket[i][0])}
    # Lan theo kênh: kênh có ≥2 phán AI cùng chiều -> bài MƠ HỒ chưa có phán của kênh đó
    # theo chiều ấy (giữ ổn định: lấy mã gặp nhiều nhất).
    theo_kenh: dict = {}
    for i, val in ket.items():
        if val[3] == "AI" and val[1] != "khong_ro":
            theo_kenh.setdefault(_kenh_khoa(rows[i][0]), []).append(val)
    for i, t in enumerate(tang):
        if t != "mo_ho" or i in ket:
            continue
        ds = theo_kenh.get(_kenh_khoa(rows[i][0])) or []
        if len(ds) >= 2 and len({x[0] for x in ds}) == 1:
            mas = [x[1] for x in ds]
            ket[i] = (ds[0][0], max(set(mas), key=lambda m: (mas.count(m), m)),
                      "theo kênh", "AI (theo kênh)")
            tt["theo_kenh"] += 1
    _ = moi and cache.update(moi)
    tt["_moi"] = moi
    tt["trang_thai"] = (f"bỏ qua: {ly_do}" if ly_do else
                        "dừng vì hết quota model" if tt["dung_vi_quota"] else "đã chạy")
    return ket, tt


def _loc(v, ts: dict, d_from, d_to, cho_ai: bool, log: list) -> dict:
    plats = list(v.d["nen_tang"])
    queries, country = ts["queries"], ts["country"]
    per: dict = {}
    cho_xet: list = []
    bi_loai: list = []
    for p in plats:
        raw = v.doc_dong(p)
        da, giu, trung = set(), [], 0
        for d, dt in raw:
            k = _chuan_link(d.get("link"))
            if k and k in da:
                trung += 1
                continue
            if k:
                da.add(k)
            giu.append((d, dt))
        trong = [(d, dt) for d, dt in giu if dt and d_from <= dt <= d_to]
        per[p] = {"scraped": len(raw), "trung_lap": trung, "trong_khoang": len(trong)}
        for d, dt in trong:
            d["platform"] = p
            d["_khop"] = A._khop_tu_khoa(d, queries)
            d["_thi_truong"] = A._thi_truong(d, queries)
            tu = A._tu_loai_tru_khop(d, ts.get("exclude") or [])
            if tu:
                d["_nhom"], d["_phan_xu"] = "loai_tru", "Luật"
                bi_loai.append((d, dt, f"chứa từ loại trừ '{tu}'"))
            else:
                cho_xet.append((d, dt))
    thu = {p: i for i, p in enumerate(plats)}
    cho_xet.sort(key=lambda x: (thu[x[0]["platform"]], -int(x[0].get("views") or 0),
                                str(x[0].get("link") or "")))
    # Phán đã lưu (`phan_xu.jsonl`) LUÔN được áp, kể cả khi lần này không được gọi AI
    # (huỷ / quá hạn / khởi động lại): review 02/10/2026 — bỏ cache thì danh sách kết quả
    # khác lần trước, sheet ghi tiếp thành nửa cũ nửa mới.
    cache = _cache_doc(v)
    # Hạn AI tính bằng time.monotonic (đồng hồ `_phan_xu_ai` dùng), chừa 4 phút sau hạn
    # chót của việc cho AI + ghi sheet — vượt một chút còn hơn bỏ AI cả việc.
    han_ai = time.monotonic() + max(0.0, v.con_giay()) + 240
    phan_xu, tt = _phan_xu_tang(cho_xet, ts, han_ai, log, cache=cache, ma=v.ma,
                                toi_da_luot=None if cho_ai else 0)
    _cache_ghi(v, tt.pop("_moi", {}))
    if not cho_ai:
        tt["trang_thai"] = ("chỉ dùng phán AI đã lưu (" + ("đã huỷ" if v.da_huy() else
                                                           "quá hạn chót") + ")")
    hits: list = []
    dem = {"Luật": [0, 0], "AI": [0, 0], "AI (theo kênh)": [0, 0]}
    chuyen: dict = {}
    for i, (d, dt) in enumerate(cho_xet):
        p = d["platform"]
        val = phan_xu.get(i)
        if val and val[1] == "khong_ro":
            d["_ai_khong_ro"] = True
            val = None
        if val:
            giu, ma, ghi, nguon = val
            d["_ai"], d["_ma_ai"], d["_phan_xu"] = True, ma, nguon
            if ma == "other_market" and re.fullmatch(r"[A-Za-z]{2}", ghi or ""):
                if d["_thi_truong"] in ("không rõ", country) and ghi.upper() != country:
                    d["_thi_truong"] = ghi.upper()
                ghi = ""
            d["_nhan_dinh"] = A._MA_AI.get(ma, ma) + (f" — {ghi}" if ghi else "")
            if not giu:
                d["_nhom"] = "ai"
                dem[nguon][1] += 1
                bi_loai.append((d, dt, f"{nguon}: {d['_nhan_dinh']}"))
                continue
        else:
            d["_phan_xu"] = "Luật"
            d["_nhan_dinh"] = ("AI không chắc — lọc theo luật" if d.get("_ai_khong_ro")
                               else "lọc theo luật")
            nhom, ly_do = A._ly_do_loai(d, p, queries, [], country, ts["boi_canh"],
                                        ts["khop_long"], ts["giu_nuoc_ngoai"])
            if nhom:
                d["_nhom"] = nhom
                dem["Luật"][1] += 1
                bi_loai.append((d, dt, ly_do))
                continue
        tt_ = d["_thi_truong"]
        if tt_ not in (country, "không rõ") and ts["chi_thi_truong_nay"] \
                and not ts["giu_nuoc_ngoai"]:
            d["_nhom"], d["_chuyen"] = "thi_truong", True
            chuyen[tt_] = chuyen.get(tt_, 0) + 1
            bi_loai.append((d, dt, f"thị trường {tt_} — người dùng chỉ hỏi {country}"))
            continue
        dem[d["_phan_xu"]][0] += 1
        hits.append((d, dt))
    hits.sort(key=lambda x: (thu[x[0]["platform"]], -int(x[0].get("views") or 0),
                             -int(x[0].get("likes") or 0), str(x[0].get("link") or "")))
    for p in plats:
        per[p]["giu"] = sum(1 for d, _ in hits if d["platform"] == p)
        per[p]["loai"] = sum(1 for d, _, _ in bi_loai if d["platform"] == p)
    tt["dem"] = {k: {"giu": a, "loai": b} for k, (a, b) in dem.items()}
    tt["chuyen_thi_truong"] = chuyen
    tt["loai_tru"] = sum(1 for d, _, _ in bi_loai if d.get("_nhom") == "loai_tru")
    return {"hits": hits, "bi_loai": bi_loai, "per": per, "phan_xu": tt}


# ───────────────────────────── sheet ─────────────────────────────
_TAB_TONG = "Tổng hợp"
_TAB_LOAI = "Bị loại"
_TAB_KHAC = A._TAB_THI_TRUONG_KHAC   # bài của brand ở nước khác — tab riêng (chốt 02/10/2026)
_BI_LOAI_TOI_DA = 20000


def _nuoc_khac(ts: dict):
    """Hàm xét một bài có thuộc tab `_TAB_KHAC` không: bài brand ở nước khác, trừ khi người
    dùng hỏi nhiều nước (`giu_nuoc_ngoai`) — khi đó chung tab nền tảng như cũ."""
    nuoc = ts.get("country") or "VN"
    return lambda d: (not ts.get("giu_nuoc_ngoai")
                      and (d.get("_thi_truong") or "không rõ") not in (nuoc, "không rõ"))
_COT_THEM = ["Thị trường", "Nhận định AI", "Phân xử"]


def _dong(d: dict, dt, kw: str, n_chu: int) -> list:
    return [d["platform"], dt.strftime("%Y-%m-%d %H:%M") if dt else "", d.get("kenh") or "",
            d.get("followers") or 0, d.get("views") or 0, d.get("likes") or 0,
            d.get("comments") or 0, d.get("shares") or 0, str(d.get("hashtags") or "")[:300],
            str(d.get("text") or "")[:n_chu], d.get("link") or "", kw,
            d.get("_thi_truong") or "không rõ"]


def _ten_tab(p: str) -> str:
    return A._TEN_NGUON.get(p, p)


def _title(v, ts: dict) -> str:
    return ts.get("title") or (f"Quét nền · {', '.join(ts['queries'])[:30]} · "
                               f"{ts['date_from'][8:10]}-{ts['date_from'][5:7]}→"
                               f"{ts['date_to'][8:10]}-{ts['date_to'][5:7]}")


def _ghi_so_bo(v, p: str, ts: dict, d_from, d_to) -> None:
    """Xong một nền tảng: tạo sheet + cấp quyền (lần đầu) rồi ghi bản SƠ BỘ của nền tảng
    đó (chưa qua AI) — người dùng mở link sớm được. Lỗi ở đây không làm hỏng việc."""
    try:
        s = sheet_lon.SoSheet(v)
        s.dam_bao(_title(v, ts), _TAB_TONG, v.d.get("nguoi_yeu_cau") or "")
        if s.s.get("giai_doan") == "cuoi":
            return
        if not s.s["tabs"][_TAB_TONG].get("da_ghi"):
            s.ghi_tab(_TAB_TONG, [["Mục", "Giá trị"],
                                  ["Trạng thái", f"ĐANG QUÉT NỀN ({v.ma}) — bản sơ bộ, chưa lọc AI"]])
        kw = ", ".join(ts["queries"])
        da, rows = set(), []
        for d, dt in v.doc_dong(p):
            k = _chuan_link(d.get("link"))
            if (k and k in da) or not (dt and d_from <= dt <= d_to):
                continue
            da.add(k)
            d["platform"] = p
            rows.append(_dong(d, dt, kw, 500) + ["chưa lọc", "sơ bộ"])
        rows.sort(key=lambda r: -int(r[4] or 0))
        s.ghi_tab(_ten_tab(p), [list(A._HEADER) + _COT_THEM] + rows, tu_dau=True)
    except Exception as e:  # noqa: BLE001
        if type(e).__name__ == "MatQuyen":
            raise
        with v._khoa:
            v.d.setdefault("ghi_chu", []).append(
                f"ghi sheet sơ bộ {p} lỗi: {A._che_token(e)[:150]}")
            v.luu()


def _dong_tong_hop(v, ts, ket: dict, cp: dict, trang_thai: str) -> list[list]:
    r = [["Mục", "Giá trị"], ["Mã việc", v.ma], ["Trạng thái", trang_thai],
         ["Từ khoá", ", ".join(ts["queries"])],
         ["Khoảng ngày", f"{ts['date_from']} → {ts['date_to']}"],
         ["Thị trường", ts["country"]]]
    for p, x in ket["per"].items():
        r.append([f"{_ten_tab(p)}", f"cào {x['scraped']} · trùng {x['trung_lap']} · trong "
                                    f"khoảng {x['trong_khoang']} · giữ {x['giu']} · loại "
                                    f"{x['loai']}"])
        for c in (v.d["nen_tang"][p].get("chua_phu") or []):
            r.append([f"{_ten_tab(p)} — chưa phủ", c])
        for ph in v.d["nen_tang"][p].get("phan") or []:
            if ph.get("trang_thai") in ("loi", "mot_phan", "da_huy"):
                r.append([f"{_ten_tab(p)} — {ph.get('nhan')}",
                          f"{ph.get('trang_thai')}: {ph.get('ly_do') or ph.get('ma')}"])
    cau_khac = _cau_nuoc_khac(ts, ket)
    if cau_khac:
        r.append([_TAB_KHAC, cau_khac])
    px = ket["phan_xu"]
    r.append(["Phân xử", _cau_phan_xu(px)])
    r.append(["Chi phí thật", f"{_usd(cp.get('usd'))} USD ({cp.get('so_run', 0)} lượt chạy "
                              f"Apify)"])
    return r


def _ghi_cuoi(v, ts: dict, ket: dict, cp: dict, trang_thai: str) -> str:
    """Ghi lại MỌI tab theo kết quả cuối (sau AI), tiếp được từ `da_ghi`."""
    s = sheet_lon.SoSheet(v)
    s.dam_bao(_title(v, ts), _TAB_TONG, v.d.get("nguoi_yeu_cau") or "")
    s.bat_dau_giai_doan("cuoi")
    kw = ", ".join(ts["queries"])
    khac = _nuoc_khac(ts)
    for p in v.d["nen_tang"]:
        rows = [_dong(d, dt, kw, 500) + [d.get("_nhan_dinh") or "", d.get("_phan_xu") or ""]
                for d, dt in ket["hits"] if d["platform"] == p and not khac(d)]
        s.ghi_tab(_ten_tab(p), [list(A._HEADER) + _COT_THEM] + rows)
    # Tab phụ rỗng: chưa từng có thì KHÔNG tạo tab trống; đã có từ lượt trước (việc tiếp tục
    # sau `xong_mot_phan`) thì vẫn ghi lại chỉ tiêu đề — `ghi_tab` xoá các dòng cũ thừa, kẻo
    # bài của lượt trước nằm lại như kết quả của lượt này.
    rows = [_dong(d, dt, kw, 500) + [d.get("_nhan_dinh") or "", d.get("_phan_xu") or ""]
            for d, dt in ket["hits"] if khac(d)]
    if rows or _TAB_KHAC in s.s["tabs"]:
        s.ghi_tab(_TAB_KHAC, [list(A._HEADER) + _COT_THEM] + rows)
    bl = ket["bi_loai"]
    if bl or _TAB_LOAI in s.s["tabs"]:
        rows = [_dong(d, dt, kw, 300) + [ly_do, d.get("_phan_xu") or ""]
                for d, dt, ly_do in bl[:_BI_LOAI_TOI_DA]]
        s.ghi_tab(_TAB_LOAI, [list(A._HEADER) + ["Thị trường", "Lý do loại", "Phân xử"]] + rows)
    tong = _dong_tong_hop(v, ts, ket, cp, trang_thai)
    if len(bl) > _BI_LOAI_TOI_DA:
        tong.append(["Bị loại — không ghi", f"{len(bl) - _BI_LOAI_TOI_DA} dòng (trần "
                                            f"{_BI_LOAI_TOI_DA} dòng/tab)"])
    s.ghi_tab(_TAB_TONG, tong)
    # Tab nền tảng/phụ đều thêm bằng `addSheet` (SoSheet.dam_bao_tab → A._them_tab), mà
    # Lark chèn tab mới vào vị trí 0 → link mở ra tab thêm sau cùng. Kéo "Tổng hợp" về
    # đầu — cố gắng, hỏng chỉ in cảnh báo (xem `A._dua_tab_chinh_len_dau`).
    tong_sid = (s.s["tabs"].get(_TAB_TONG) or {}).get("sheet_id")
    if tong_sid and len(s.s["tabs"]) > 1:
        A._dua_tab_chinh_len_dau(s.s.get("token") or "", tong_sid)
    return s.s.get("url") or ""


# ───────────────────────────── tin kết quả ─────────────────────────────
def _cau_nuoc_khac(ts: dict, ket: dict) -> str:
    """Câu báo bài của brand ở nước khác đã sang tab riêng; rỗng nếu không có bài nào."""
    khac = _nuoc_khac(ts)
    dem: dict[str, int] = {}
    for d, _ in ket["hits"]:
        if khac(d):
            dem[d["_thi_truong"]] = dem.get(d["_thi_truong"], 0) + 1
    if not dem:
        return ""
    nuoc = ", ".join(f"{k} {n}" for k, n in sorted(dem.items(), key=lambda x: -x[1]))
    return (f"giữ {sum(dem.values())} bài của brand ở nước khác ({nuoc}) ở tab riêng "
            f"'{_TAB_KHAC}' — các tab nền tảng chỉ có bài {ts['country']}")


def _cau_phan_xu(px: dict) -> str:
    d = px.get("dem") or {}

    def h(k):
        x = d.get(k) or {"giu": 0, "loai": 0}
        return x["giu"], x["loai"]
    ag, al = h("AI")
    kg, kl = h("AI (theo kênh)")
    lg, ll = h("Luật")
    s = (f"AI đọc {ag + al} bài (giữ {ag}, loại {al}), theo kênh {kg + kl} (giữ {kg}, loại "
         f"{kl}), luật {lg + ll} (giữ {lg}, loại {ll})")
    if px.get("luot_ai"):
        s += f"; {px['luot_ai']} lượt gọi model"
    mk = px.get("mau_kiem")
    if mk and mk.get("xet"):
        s += f"; mẫu kiểm {mk['xet']} bài luật đã giữ: AI đồng ý {mk['ai_giu']}, loại {mk['ai_loai']}"
    if px.get("loai_tru"):
        s += f", từ loại trừ {px['loai_tru']}"
    ch = sum((px.get("chuyen_thi_truong") or {}).values())
    if ch:
        s += f", chuyển sang Bị loại vì thị trường {ch}"
    st = str(px.get("trang_thai") or "")
    if st and st != "đã chạy":
        s += f" — AI {st}"
    return s


def _usd(x) -> str:
    return f"{float(x or 0):.2f}".replace(".", ",")


def _tin_nhan(v, ts, ket: dict, cp: dict, url: str, trang_thai: str, ly_do: list[str]) -> str:
    dau = {"xong": "XONG", "xong_mot_phan": "XONG MỘT PHẦN", "da_huy": "ĐÃ HUỶ"}.get(
        trang_thai, trang_thai.upper())
    d = [f"[{dau}] Quét nền {v.ma}: \"{', '.join(ts['queries'])}\" {ts['date_from']} → "
         f"{ts['date_to']}, thị trường {ts['country']}."]
    if trang_thai == "da_huy":
        d.append("Đã huỷ theo yêu cầu — các lượt đang chạy đã dừng, sheet giữ phần lấy được "
                 "tới lúc huỷ.")
    d.append(f"Link: {url}" if url else "Không tạo được sheet — xem lỗi ở dưới.")
    for p, x in ket["per"].items():
        loi = [ph for ph in v.d["nen_tang"][p].get("phan") or []
               if ph.get("trang_thai") in ("loi", "da_huy")]
        s = (f"- {_ten_tab(p)}: cào {x['scraped']}, trong khoảng {x['trong_khoang']}, giữ "
             f"{x['giu']}, loại {x['loai']}")
        if loi:
            s += f" · {len(loi)}/{len(v.d['nen_tang'][p]['phan'])} lượt hỏng/không chạy (" + \
                 "; ".join(sorted({str(ph.get('ma')) for ph in loi})) + ")"
        d.append(s)
    cau_khac = _cau_nuoc_khac(ts, ket)
    if cau_khac:
        d.append(f"Thị trường khác: {cau_khac}.")
    d.append("Phân xử: " + _cau_phan_xu(ket["phan_xu"]) + ".")
    chua = [c for x in v.d["nen_tang"].values() for c in (x.get("chua_phu") or [])]
    if chua:
        d.append("Chưa phủ: " + " | ".join(chua))
    d.append(f"Chi phí thật: {_usd(cp.get('usd'))} USD ({cp.get('so_run', 0)} lượt chạy Apify"
             + (f", {cp['chua_doc']} lượt chưa đọc được số" if cp.get("chua_doc") else "")
             + f"; ngân sách việc {_usd(v.d.get('ngan_sach_usd'))} USD).")
    if ly_do:
        d.append("Lưu ý: " + "; ".join(ly_do) + ".")
    if not (v.d.get("sheet") or {}).get("granted", True):
        d.append("Chưa cấp được quyền sheet tự động — nhờ người vận hành chia sẻ nếu không mở được.")
    return "\n".join(d)


def chay_viec(v) -> tuple[str, str]:
    """Runner của viec_nen cho `social_listen`. -> (trạng thái cuối, tin kết quả)."""
    ts = v.d["tham_so"]
    d_from = A._parse_date(ts["date_from"], end=False)
    d_to = A._parse_date(ts["date_to"], end=True)
    ly_do: list[str] = []
    log: list[str] = []
    if v.d["trang_thai"] == "dang_cao":
        if v.qua_han():
            _dong_phan_dang_chay(v, ts)
            ly_do.append("bot khởi động lại sau hạn chót — huỷ lượt đang chạy, giữ phần đã có")
        else:
            ns = _so_ngan_sach(v)
            _chay_cac_phan(v, ns, ts, lambda p: _ghi_so_bo(v, p, ts, d_from, d_to))
        v.dat("dang_loc")
    # Trước khi lọc + chốt tiền: không lượt con nào còn sống trên Apify (review 02/10/2026).
    v.dung.set()
    _thu_don_het(v)
    cho_ai = not v.da_huy() and v.con_giay() > -120
    ket = _loc(v, ts, d_from, d_to, cho_ai, log)
    with v._khoa:
        v.d["phan_xu"] = {k: val for k, val in ket["phan_xu"].items() if k != "_moi"}
        v.luu()
    v.dat("dang_ghi")
    mot_phan = any(ph.get("trang_thai") != "xong" for _, ph in v.cac_phan()) or any(
        x.get("chua_phu") for x in v.d["nen_tang"].values())
    trang_thai = "da_huy" if v.da_huy() else "xong_mot_phan" if mot_phan else "xong"
    cp = v.chot_chi_phi(ts["queries"], list(v.d["nen_tang"]),
                        f"{ts['date_from']} → {ts['date_to']}")
    url = ""
    if not ket["hits"] and not ket["bi_loai"] and not (v.d.get("sheet") or {}).get("token"):
        ly_do.append("không bài nào nằm trong khoảng ngày — không tạo sheet")
    else:
        try:
            url = _ghi_cuoi(v, ts, ket, cp, trang_thai)
        except Exception as e:  # noqa: BLE001
            if type(e).__name__ == "MatQuyen":
                raise
            ly_do.append(f"ghi sheet lỗi: {A._che_token(e)[:150]}")
            url = (v.d.get("sheet") or {}).get("url") or ""
    if log:
        with v._khoa:
            v.d.setdefault("ghi_chu", []).extend(log[-10:])
            v.luu()
    with v._khoa:
        v.d["ket_qua"] = {"per": ket["per"], "sheet_url": url,
                          "giu": len(ket["hits"]), "loai": len(ket["bi_loai"])}
        v.luu()
    return trang_thai, _tin_nhan(v, ts, ket, cp, url, trang_thai, ly_do)


__all__ = ["xu_ly_lon", "chay_viec", "ke_hoach", "can_chay_nen", "giay_tai_cho",
           "tool_error"]
