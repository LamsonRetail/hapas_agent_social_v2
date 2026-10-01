"""Register `social_listen` — social listening trên năm nền tảng.

TikTok / Facebook / Instagram / Threads đi qua Apify. YouTube đi qua YouTube
Data API v3 chính thức, lọc ngày ngay phía server rồi batch lấy thống kê video
và subscriber của kênh. Kết quả được chuẩn hoá và ghi vào MỘT Lark Sheet.

Nền tảng
--------
Không nói gì  -> cào CẢ NĂM, chế độ QUÉT RỘNG-NÔNG.
Gọi đích danh -> chỉ nguồn đó, chế độ ĐÀO SÂU (dùng nguyên `limit`).
"fb"/"face"/"phây" -> facebook. "ig"/"insta" -> instagram. "tt" -> tiktok.
"yt"/"ytb" -> youtube. "thread" (số ít) -> threads.

Vì sao mặc định phải NÔNG: Threads đắt, còn YouTube tuy không mất tiền nhưng
`search.list` có bucket mặc định 100 lượt/ngày. Mặc định hai nguồn này chỉ quét
50/30 post; muốn sâu thì gọi tên nền tảng đó.

Nguyên tắc quan trọng nhất: KHÔNG BAO GIỜ IM LẶNG KHI THIẾU NGUỒN
------------------------------------------------------------------
Cào 3 nguồn mà 1 nguồn hỏng thì tuyệt đối không được trả về dữ liệu 2 nguồn còn
lại như thể đó là toàn bộ. Kết quả luôn kèm `per_platform` (mỗi nền tảng: lấy
được bao nhiêu / hỏng vì sao) và `platforms_failed`; mô tả tool bắt Mark phải
đọc ra. Đây đúng lớp lỗi đã xảy ra với fb_ads_library (cắt URL -> báo "0 ad" cho
mọi brand mà không hề báo lỗi).

Chất lượng từng nguồn — đo thật ngày 26/08/2026, đừng kỳ vọng bằng nhau
-----------------------------------------------------------------------
- TikTok  (apidojo/tiktok-scraper, 4.65*): tốt nhất. Có followers, views, shares,
  lọc theo quốc gia. Rẻ nhất (~$0.30/1K post).
- Instagram (apidojo/instagram-hashtag-scraper, 4.02*): KHÔNG có followers,
  KHÔNG có shares, KHÔNG lọc được quốc gia -> kết quả toàn cầu, nhiễu nặng
  (tra "hapas" ra #hapasguitars của hãng đàn guitar và post tiếng Thái).
- Facebook (scrapeforge/facebook-search-posts, 3.63*): yếu nhất. Khớp từ khoá
  lỏng (tra "hapas" ra "Happy Animals", "Happy.craft.studio"), engagement hay
  trả 0, KHÔNG có followers. GÓI FREE CHỈ CHO 20 KẾT QUẢ VÀ 1 LẦN CHẠY / 24 GIỜ.
- YouTube Data API v3 chính thức: CÓ subscribers, views, likes, comments; không
  có share. Miễn phí nhưng quota mặc định chỉ 100 lượt `search.list` mỗi ngày.
- Threads (futurizerush/meta-threads-scraper, 4.18*): dữ liệu tốt bất ngờ — có
  followers_count, view_count, repost_count, và lọc ngày server-side thật.
  BẮT BUỘC ghim RAM 1GB, xem chú thích ở _MEMORY.

Lọc ngày
--------
- TikTok: chỉ có enum thô (THIS_WEEK/THIS_MONTH...) -> thu hẹp rồi lọc lại tại chỗ.
- Instagram: không có lọc ngày -> lọc hoàn toàn tại chỗ.
- Facebook: có start_date/end_date thật -> lọc server-side, vẫn lọc lại cho chắc.
- YouTube: có publishedAfter/publishedBefore thật -> lọc server-side.
Hệ quả chung: `limit` là số post CÀO, số nằm trong khoảng luôn ÍT HƠN.

Chuẩn bị: 1 dòng trong .env
---------------------------
    APIFY_TOKEN=apify_api_xxx      # https://console.apify.com/settings/integrations
    APIFY_MAX_CHARGE_USD=1.0       # tuỳ chọn, trần chi phí MỖI NỀN TẢNG mỗi lần chạy
    YOUTUBE_DATA_API_KEY=AIza...   # Google Cloud, bật YouTube Data API v3
"""

from __future__ import annotations

import datetime
import html
import json
import os
import time
import re
import unicodedata
import urllib.parse

import requests
from concurrent.futures import ThreadPoolExecutor, TimeoutError as _FutTimeout

import chi_phi_tool
import lark_client as lark
import memory_store
from config import config

from tools.registry import registry, tool_error, tool_result  # type: ignore

_TOOLSET = "social"
_APIFY_BASE = "https://api.apify.com/v2"
_YOUTUBE_BASE = "https://www.googleapis.com/youtube/v3"
# Ngân sách thời gian. run.py có trần cứng AGENT_REPLY_TIMEOUT (mặc định 180s)
# cho CẢ lượt trả lời; tool phải xong SỚM HƠN để model còn kịp viết câu trả lời.
# Bản trước để _RUN_TIMEOUT=240 > 180 -> một lời gọi Apify chậm là chắc chắn
# timeout cả lượt (đã xảy ra thật 26/08/2026 với "tiktok + instagram, nhiều từ
# khoá, 17 ngày": Instagram gọi actor RIÊNG cho từng từ khoá, tuần tự, cộng dồn).
_REPLY_BUDGET = float(os.environ.get("AGENT_REPLY_TIMEOUT", "180"))
_TOOL_DEADLINE = max(45.0, _REPLY_BUDGET - 45.0)   # chừa 45s cho model viết trả lời
_RUN_TIMEOUT = min(120, int(_TOOL_DEADLINE))
_VN_TZ = datetime.timezone(datetime.timedelta(hours=7))
# MẶC ĐỊNH khi chủ agent chưa đặt trần trên console. Giá trị thật đọc qua `_tran()`.
_MAX_CHARGE = float(os.environ.get("APIFY_MAX_CHARGE_USD", "1.0"))
_MAX_LIMIT = 500
# Khoảng AN TOÀN cứng cho hai trần chủ agent chỉnh trên console (Năng lực → Quét mạng
# xã hội). Console gõ gì thì ở đây cũng kẹp lại: gõ nhầm 1000 USD thành 1000 không được
# biến thành một lượt quét nghìn đô. 1000 bài TikTok ≈ 3 USD, nên 5 USD đủ chỗ.
_TRAN_BAI_KHOANG = (10, 1000)
_TRAN_USD_KHOANG = (0.1, 5.0)


def _kep(v, lo: float, hi: float, mac_dinh: float) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return mac_dinh
    if v != v:                            # NaN
        return mac_dinh
    return min(hi, max(lo, v))


def _tran() -> tuple[int, float]:
    """(trần bài mỗi nền tảng, trần USD mỗi lượt chạy actor) đang có hiệu lực."""
    try:
        import lsr_policy
        c = lsr_policy.cau_hinh_tool("social_listen")
    except Exception:  # noqa: BLE001 — đọc hỏng thì dùng mặc định, không chặn quét
        c = {}
    return (int(_kep(c.get("tran_bai"), *_TRAN_BAI_KHOANG, _MAX_LIMIT)),
            round(_kep(c.get("tran_usd"), *_TRAN_USD_KHOANG, _MAX_CHARGE), 2))

_ALL = ("tiktok", "facebook", "instagram", "youtube", "threads")

# Viết tắt -> tên chuẩn. Gồm cả cách người Việt hay gõ.
_ALIAS = {
    "tiktok": "tiktok", "tt": "tiktok", "tik tok": "tiktok", "tik-tok": "tiktok",
    "douyin": "tiktok",
    "facebook": "facebook", "fb": "facebook", "face": "facebook", "phây": "facebook",
    "phay": "facebook", "facebook.com": "facebook",
    "instagram": "instagram", "ig": "instagram", "insta": "instagram",
    "in": "instagram", "instagram.com": "instagram",
    "youtube": "youtube", "yt": "youtube", "ytb": "youtube", "you tube": "youtube",
    "youtube.com": "youtube",
    "threads": "threads", "thread": "threads", "th": "threads", "threads.net": "threads",
}
# Nền tảng biết tên nhưng CHƯA nối nguồn — phải từ chối rõ, không im lặng bỏ qua.
_NOT_YET = {
    "x": "X/Twitter", "twitter": "X/Twitter", "linkedin": "LinkedIn",
    "shopee": "Shopee", "lazada": "Lazada", "zalo": "Zalo", "reddit": "Reddit",
}

# Trần cứng quan sát được của apidojo cho tìm-theo-keyword là 10 kết quả.
# Dưới ngưỡng này coi như actor chạm trần chứ KHÔNG phải thị trường hết bài.
_TIKTOK_NGUONG_LEO_THANG = 20

_ACTORS = {
    "tiktok": "apidojo~tiktok-scraper",
    "instagram": "apidojo~instagram-hashtag-scraper",
    "facebook": "scrapeforge~facebook-search-posts",
    "threads": "futurizerush~meta-threads-scraper",
    # Dự phòng cho TikTok. Đo thật 26/08/2026: apidojo chạy tốt cả buổi sáng rồi
    # đột ngột trả {"noResults": true} cho MỌI truy vấn (kể cả từ khoá phổ thông
    # và ALL_TIME), trong khi clockworks vẫn trả dữ liệu bình thường -> hỏng ở
    # actor chứ không phải tài khoản. Đắt hơn ~10 lần nên chỉ dùng khi cần.
    "tiktok_fallback": "clockworks~tiktok-hashtag-scraper",
}

# RAM ghim cho từng actor (MB). Phí "Actor Start" của Threads tính THEO GB
# ($0.02/GB) nên để mặc định 4GB là mất $0.08 trước khi trả về item nào — đo
# thật 26/08/2026: run bị abort sau 3 giây vì chạm trần chi phí, dataset rỗng.
_MEMORY = {"threads": 1024}

# Giá Apify mỗi item (USD) — YouTube Data API chính thức không tính tiền.
# TikTok để giá của actor DỰ PHÒNG (clockworks, $0.003) chứ không phải actor
# chính ($0.0003): đo 08/09/2026 thấy actor chính chạm trần 10 kết quả cho
# tìm-theo-keyword nên hầu như lượt nào cũng phải leo thang. Ước tính CAO hơn
# thực tế thì người dùng chỉ ngạc nhiên dễ chịu; ước tính THẤP hơn thì họ vỡ kế
# hoạch chi phí — cố ý chọn hướng an toàn.
_UNIT_COST = {"tiktok": 0.003, "instagram": 0.0004, "facebook": 0.00259,
              "youtube": 0.0, "threads": 0.0025}
_START_COST = {"instagram": 0.016, "threads": 0.02, "facebook": 0.00005}

# Số post quét mặc định KHI KHÔNG chỉ định nền tảng (quét rộng - nông).
# Người dùng gọi đích danh nền tảng nào thì nền tảng đó dùng nguyên `limit`
# để đào sâu — đúng cách làm việc: quét rộng trước, thấy gì hay thì khoan sâu.
_SHALLOW = {"tiktok": 100, "facebook": 100, "instagram": 100,
            "youtube": 50, "threads": 30}

_HEADER = ["Nền tảng", "Ngày đăng", "Kênh", "Followers", "Views", "Likes",
           "Comments", "Shares", "Hashtags", "Nội dung", "Link", "Từ khoá"]

_HASHTAG_RE = re.compile(r"#([A-Za-z0-9_\u00C0-\u1EF9]+)")


# ───────────────────────── nền tảng ─────────────────────────
def normalize_platforms(raw) -> tuple[list[str], list[str]]:
    """Chuẩn hoá input nền tảng -> (danh sách hợp lệ, danh sách chưa hỗ trợ).

    Rỗng / 'all' / 'tất cả' -> cả năm nguồn.
    """
    if raw is None:
        return list(_ALL), []
    items = [raw] if isinstance(raw, str) else list(raw)
    vals = []
    for x in items:
        for part in re.split(r"[,\s/+&]+|và|and", str(x).lower()):
            part = part.strip(" .#@")
            if part:
                vals.append(part)
    if not vals or any(v in ("all", "tatca", "tat", "ca", "tất", "cả", "moi", "mọi") for v in vals):
        return list(_ALL), []
    ok, bad = [], []
    for v in vals:
        n = _ALIAS.get(v)
        if n:
            if n not in ok:
                ok.append(n)
        elif v in _NOT_YET:
            if _NOT_YET[v] not in bad:
                bad.append(_NOT_YET[v])
    return ok, bad


# ───────────────────────── ngày tháng ─────────────────────────
def _parse_date(s: str, *, end: bool) -> datetime.datetime:
    """'YYYY-MM-DD' | 'DD/MM' | 'DD/MM/YYYY' -> datetime giờ VN.

    ``end=True`` lấy 23:59:59 để bao trọn ngày cuối (lấy 00:00:00 thì "tới ngày
    26" sẽ mất sạch post của chính ngày 26).
    """
    s = (s or "").strip()
    now = datetime.datetime.now(_VN_TZ)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m", "%d-%m"):
        try:
            d = datetime.datetime.strptime(s, fmt)
            if "%Y" not in fmt:
                d = d.replace(year=now.year)
            t = datetime.time(23, 59, 59) if end else datetime.time(0, 0, 0)
            return datetime.datetime.combine(d.date(), t, tzinfo=_VN_TZ)
        except ValueError:
            continue
    raise ValueError(f"Không hiểu ngày {s!r}. Dùng 'YYYY-MM-DD' hoặc 'DD/MM' (giờ VN).")


def _tiktok_enum(d_from: datetime.datetime) -> str:
    """Enum dateRange hẹp nhất của TikTok mà vẫn BAO TRỌN khoảng cần."""
    days = (datetime.datetime.now(_VN_TZ) - d_from).days
    for lim, name in ((1, "YESTERDAY"), (7, "THIS_WEEK"), (31, "THIS_MONTH"),
                      (92, "LAST_THREE_MONTHS"), (183, "LAST_SIX_MONTHS")):
        if days <= lim:
            return name
    return "ALL_TIME"


def _to_vn(raw) -> datetime.datetime | None:
    """ISO string hoặc epoch giây -> datetime giờ VN."""
    if raw in (None, ""):
        return None
    try:
        if isinstance(raw, (int, float)):
            dt = datetime.datetime.fromtimestamp(float(raw), datetime.timezone.utc)
        else:
            dt = datetime.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, OSError, OverflowError):
        return None
    return dt.astimezone(_VN_TZ)


# ───────────────────────── Apify ─────────────────────────
def _che_token(s, token: str | None = None) -> str:
    """Che APIFY_TOKEN khỏi MỌI chuỗi lỗi trước khi nó tới model, audit hay log.

    Chuỗi lỗi của `requests` chứa nguyên URL; bản trước để token trên query
    (`?token=…`) nên một lần mất mạng là token chui vào `per_platform.error`,
    rồi vào câu trả lời của model và sổ audit (rà 01/10/2026). Token nay đi qua
    header, hàm này là lớp chặn thứ hai.
    """
    s = str(s)
    tok = (os.environ.get("APIFY_TOKEN", "") if token is None else token).strip()
    if tok:
        s = s.replace(tok, "***").replace(urllib.parse.quote(tok), "***")
    return re.sub(r"(?i)(token=)[^&\s'\"]+", r"\1***", s)


def _call(actor: str, payload: dict, limit: int, mem: int | None = None,
          min_charge: float = 0) -> list[dict]:
    """Chạy actor đồng bộ rồi trả dataset.

    `min_charge`: mức `maxTotalChargeUsd` tối thiểu actor đòi (YouTube/Facebook
    comments đòi 0,5 USD — deep_dive_tool). Trần console THẤP HƠN mức đó thì TỪ
    CHỐI chứ không tự nâng trần: chủ agent đặt trần là để không lượt nào tiêu quá
    số đó, và giá mỗi comment của actor ta không kiểm soát nên không chứng minh
    được `maxItems × giá` luôn nằm dưới trần console. Trước 01/10/2026 deep_dive
    đã truyền tham số này mà `_call` không có -> TypeError 9/9 lượt kéo bình luận
    YouTube/Facebook.
    """
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "Thiếu APIFY_TOKEN trong .env "
            "(lấy ở https://console.apify.com/settings/integrations)."
        )
    tran_usd = _tran()[1]
    if min_charge and tran_usd < min_charge:
        def usd(x: float) -> str:
            return f"{x:g}".replace(".", ",")
        raise RuntimeError(
            f"Trần chi phí trên console ({usd(tran_usd)} USD/lượt) thấp hơn mức tối thiểu "
            f"actor {actor} yêu cầu ({usd(min_charge)} USD) — không chạy để khỏi vượt "
            f"trần. Chủ agent nâng trần ở console: Năng lực → Quét mạng xã hội.")
    # Token đi qua header Authorization, KHÔNG nằm trên URL (xem `_che_token`).
    url = (f"{_APIFY_BASE}/acts/{actor}/run-sync-get-dataset-items"
           # Đây là TRẦN cho phép, không phải phí thực — phí vẫn tính theo item.
           f"?maxItems={limit}&maxTotalChargeUsd={tran_usd}"
           + (f"&memory={mem}" if mem else ""))
    try:
        r = requests.post(url, json=payload, timeout=_RUN_TIMEOUT,
                          headers={"Authorization": f"Bearer {token}"})
    except requests.RequestException as e:
        raise RuntimeError(
            f"Không kết nối được Apify ({type(e).__name__}): {_che_token(e, token)}"[:300]
        ) from None
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {_che_token(r.text[:250], token)}")
    data = r.json()
    return data if isinstance(data, list) else []


def _chi_phi_thuc(actors: list[str], tu: datetime.datetime,
                  uoc_tinh: float = 0.0) -> dict | None:
    """Cộng `usageTotalUsd` các run của `actors` bắt đầu từ `tu` — tiền Apify THẬT tính.

    Endpoint run-sync không trả phí, nên hỏi lại lịch sử run sau khi quét. Trước
    đây chỉ có ước tính trước khi chạy: 23/09/2026 Mark báo "khoảng 0,30 USD"
    trong khi thực tế là 0,83 USD. Trả None nếu không hỏi được (không đoán số).
    """
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token or not actors:
        return None

    def _mot(actor: str) -> list[dict]:
        r = requests.get(f"{_APIFY_BASE}/acts/{actor}/runs",
                         params={"desc": 1, "limit": 20},
                         headers={"Authorization": f"Bearer {token}"}, timeout=10)
        r.raise_for_status()
        return (r.json().get("data") or {}).get("items") or []

    tran_usd = _tran()[1]

    def _mot_luot() -> dict | None:
        tong, so_run, cham_tran, dang_chay = 0.0, 0, 0, 0
        try:
            with ThreadPoolExecutor(max_workers=len(actors)) as ex:
                ds = list(ex.map(_mot, actors, timeout=15))
        except Exception:  # noqa: BLE001 — không để token lọt vào lỗi
            return None
        for items in ds:
            for it in items:
                st = _to_vn(it.get("startedAt"))
                if not st or st < tu:
                    continue
                u = float(it.get("usageTotalUsd") or 0)
                tong += u
                so_run += 1
                cham_tran += u >= 0.95 * tran_usd
                dang_chay += it.get("status") in ("READY", "RUNNING")
        return {"usd": round(tong, 3), "so_run": so_run,
                "cham_tran": cham_tran, "dang_chay": dang_chay}

    kq = _mot_luot()
    # run-sync đã trả dữ liệu nhưng Apify ghi tiền CHẬM vài giây, kể cả khi run đã báo
    # SUCCEEDED. Đo 25/09: lượt soi tài khoản vừa xong vẫn "đang chạy"; lượt Shopee báo
    # 0,01 USD trong khi thật là 0,105. Hỏi lại khi còn "đang chạy" hoặc số thật thấp hơn
    # nửa ước tính — tối đa hai lần, mỗi lần 3 giây.
    # Hỏi hỏng (None) cũng hỏi lại: đo 25/09, lượt soi TikTok Shop chạy xong trong khoảng
    # thời gian đối chiếu mà sổ vẫn ghi "chưa lấy được số thực" — một lần gọi Apify lỗi
    # thoáng qua là bỏ cuộc luôn.
    for _ in range(2):
        if kq and not (kq["dang_chay"] or (uoc_tinh and kq["usd"] < 0.5 * uoc_tinh)):
            break
        time.sleep(3)
        kq = _mot_luot() or kq
    return kq


def _dong_chi_phi(thuc: dict | None, est: float) -> str:
    """Một dòng chi phí dựng sẵn để model chép nguyên văn, khỏi tự tính."""
    def usd(x: float) -> str:
        return f"{x:.2f}".replace(".", ",")

    if thuc and not thuc["so_run"] and est <= 0:
        return "Chi phí lượt quét: 0 USD (nguồn đã quét không tính phí)."
    if not thuc or not thuc["so_run"]:
        return (f"Chi phí lượt quét: chưa lấy được số thực từ Apify, ước tính trước "
                f"khi chạy khoảng {usd(est)} USD.")
    s = f"Chi phí lượt quét: {usd(thuc['usd'])} USD (số thực từ Apify, {thuc['so_run']} lượt chạy)."
    if thuc["cham_tran"]:
        s += (f" {thuc['cham_tran']} lượt chạm trần {_tran()[1]:g} USD/lượt nên bị dừng "
              f"giữa chừng — kết quả có thể thiếu.")
    if thuc["dang_chay"]:
        s += " Một số lượt vẫn đang chạy trên Apify nên số có thể còn tăng."
    return s


# ───────────────────────── YouTube Data API v3 ─────────────────────────
def _youtube_get(resource: str, params: dict) -> dict:
    """GET một endpoint YouTube, không bao giờ để API key lọt vào lỗi/log."""
    key = os.environ.get("YOUTUBE_DATA_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "Thiếu YOUTUBE_DATA_API_KEY trong .env. Bật YouTube Data API v3 "
            "trong Google Cloud rồi tạo API key; nguồn YouTube không dùng Apify "
            "fallback để tránh phát sinh chi phí âm thầm."
        )
    try:
        r = requests.get(
            f"{_YOUTUBE_BASE}/{resource}",
            params={**params, "key": key},
            timeout=min(45, _RUN_TIMEOUT),
        )
    except requests.RequestException as e:
        # requests có thể nhét prepared URL (kèm key) vào chuỗi lỗi; chỉ nêu loại.
        raise RuntimeError(
            f"Không kết nối được YouTube Data API: {type(e).__name__}"
        ) from None
    try:
        data = r.json()
    except ValueError:
        data = {}
    if r.status_code >= 400:
        err = data.get("error") if isinstance(data, dict) else {}
        err = err if isinstance(err, dict) else {}
        reasons = err.get("errors") or []
        reason = reasons[0].get("reason") if reasons and isinstance(reasons[0], dict) else ""
        message = str(err.get("message") or "")[:180]
        if reason in ("quotaExceeded", "dailyLimitExceeded"):
            raise RuntimeError(
                "YouTube Data API đã hết quota hôm nay (search.list mặc định "
                "100 lượt/ngày; reset theo giờ Pacific)."
            )
        if reason in ("keyInvalid", "accessNotConfigured", "forbidden"):
            raise RuntimeError(
                f"YouTube Data API key chưa hợp lệ/chưa bật API ({reason}). {message}"
            )
        raise RuntimeError(
            f"YouTube Data API HTTP {r.status_code}"
            f"{f' ({reason})' if reason else ''}: {message or 'không có mô tả'}"
        )
    if not isinstance(data, dict):
        raise RuntimeError("YouTube Data API trả dữ liệu không phải JSON object.")
    return data


def _chunks(xs: list[str], n: int = 50):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def _rfc3339_utc(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _join(items) -> str:
    """Nối list thành chuỗi, BỎ QUA phần tử None/không phải chuỗi.

    Actor TikTok thỉnh thoảng trả None lẫn trong mảng hashtags -> `", ".join()`
    ném TypeError và làm hỏng NGUYÊN nguồn đó. Lỗi chập chờn nên rất dễ lọt.
    """
    return ", ".join(str(x) for x in (items or []) if x)[:500]


def _tags_from(text: str) -> str:
    return ", ".join(_HASHTAG_RE.findall(text or ""))[:500]


def _norm(s: str) -> str:
    """Bỏ dấu + thường hoá, để so khớp từ khoá bền vững.

    'đ' KHÔNG tách dấu được qua NFD (là chữ riêng U+0111) nên phải đổi tay, không
    thì "Đồng hồ" không bao giờ khớp từ khoá gõ không dấu "dong ho".
    """
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


# Nguồn khớp từ khoá LỎNG, phải lọc lại phía mình. Đo thật 26/08/2026: tra
# "hapas" trên Facebook trả về "Happy Animals", "Happy With Raveen",
# "Happy Syrian" — khớp chữ "Happy". Instagram thì ra #hapasguitars (hãng đàn)
# và post tiếng Thái vì actor không lọc được quốc gia.
# Từ 01/10/2026 MỌI nền tảng đi qua `_khop_tu_khoa`; danh sách này chỉ còn dùng
# khi `khop_long`=true (truy vấn khám phá kiểu "viral"): khi đó giữ đúng hành vi
# cũ — ba nguồn khớp lỏng này vẫn phải chứa chuỗi con từ khoá (`_relevant`).
_NEEDS_RELEVANCE_FILTER = ("facebook", "instagram", "youtube")

# Nguồn KHÔNG lọc được khoảng ngày ở phía server: chỉ lấy được N item MỚI NHẤT
# rồi mình lọc lại. Với khoảng ngày rộng, N item đó có thể nằm gọn trong vài
# ngày gần nhất -> phần cũ của khoảng KHÔNG hề được quét, mà kết quả nhìn vẫn
# "đầy". Facebook và Threads có start_date/end_date thật nên không dính.
_NO_SERVER_DATE = ("tiktok", "instagram")


def _relevant(d: dict, queries: list[str]) -> bool:
    """Từ khoá có THỰC SỰ xuất hiện trong nội dung/hashtag không.

    Cố ý so khớp CHUỖI CON chứ không theo ranh giới từ: người Việt hay gõ liền
    một mạch nhiều hashtag ("...tiktokdichHAPASNUOCHOAHAPASLEAVEANOTE"), khớp
    theo ranh giới từ sẽ loại đúng những bài của chính brand.
    """
    hay = _norm(f"{d.get('text','')} {d.get('hashtags','')} {d.get('kenh','')}")
    return any(_norm(q) in hay for q in queries)


def _tokens(s: str) -> list[str]:
    """Chuẩn hoá (bỏ dấu, đ→d, thường) rồi tách theo ký tự KHÔNG phải chữ/số.

    '#' '.' '_' '@' đều là dấu tách: "hapas.official" -> ["hapas", "official"].
    Dùng lớp chữ Unicode chứ không chỉ a-z để từ khoá tiếng Thái/Hindi vẫn so được.
    """
    return re.findall(r"[^\W_]+", _norm(s))


def _ghep_lien(tokens: list[str], kim: str) -> bool:
    """`kim` bằng đúng phần GHÉP của vài token LIỀN NHAU — khớp ranh giới cả hai đầu.

    Để "matemade" khớp "Mate Made" mà "hapas" KHÔNG khớp "hapa systems" (ghép
    "hapasystems" chứa "hapas" nhưng cắt giữa chữ "systems").
    """
    for i in range(len(tokens)):
        s = ""
        for t in tokens[i:]:
            s += t
            if len(s) >= len(kim):
                break
        if s == kim:
            return True
    return False


def _khop_mot_tu(tokens: list[str], tu: str, the: tuple = ()) -> bool:
    if len(tu) <= 3:
        # Kim ngắn ("ai", "k", "20") khớp chuỗi con là khớp bừa ("ai" nằm trong
        # "hai", "mai", "thailand") — bắt buộc trùng nguyên một từ. Riêng HASHTAG
        # thì cho khớp ĐẦU token: brand ngắn hay gõ dính ("#PNJ30Nam",
        # "PNJSpring2026") — chỉ hashtag, không áp cho chữ thường trong nội dung.
        return tu in tokens or any(t.startswith(tu) for t in the)
    # Kim dài: được nằm GIỮA một token, vì người Việt gõ dính hashtag
    # ("#HAPASNUOCHOAHAPAS"). Nhưng không bắc qua ranh giới từ, xem `_ghep_lien`.
    return any(tu in t for t in tokens) or _ghep_lien(tokens, tu)


def _khop_tu_khoa(d: dict, queries: list[str]) -> bool:
    """Bài có THỰC SỰ nhắc từ khoá không — áp cho MỌI nền tảng.

    Vì sao: trước 01/10/2026 chỉ Facebook/Instagram/YouTube được kiểm, TikTok và
    Threads lọt thẳng vào sheet. Sheet ngày 01/10 có bài Threads của "Mason
    Nguyễn" ("vote Tinh Hà ở đâu"), "Bùi Trường Linh" ("Đt gập thì a k có…"),
    "Tu Anh Vu" (Thơm Da LAB x Folio's Men x Narciso) — không bài nào có chữ
    "hapas". Actor search của Threads/TikTok khớp cả hồ sơ, bình luận, gợi ý.

    Haystack = nội dung (tiêu đề/caption) + hashtag + tên kênh + username.
    TUYỆT ĐỐI không đưa trường actor VỌNG LẠI từ khoá vào (`searchKeyword`,
    `input` — apidojo `includeSearchKeywords`): dòng nào cũng có, lọc thành vô hiệu.

    Luật: bỏ dấu (đ→d) + thường hoá; từ khoá nhiều chữ khớp khi ĐỦ mọi chữ hoặc
    khi dạng viết liền của nó xuất hiện; chữ ≤3 ký tự phải trùng nguyên từ.
    "hapa" (lưới nuôi cá — "Taj Nets – aquaculture hapa", YouTube 01/10) KHÔNG
    khớp "hapas". "Hapas Ashen" (ban nhạc metal "SHINAI – Hapas Ashen") thì CÓ
    chữ "Hapas" nên vẫn khớp — bài đó do cổng thị trường VN hoặc AI loại.
    """
    hay = " ".join(str(d.get(k) or "") for k in ("text", "hashtags", "kenh", "username"))
    tokens = _tokens(hay)
    # Token HASHTAG: trường `hashtags` (tên đã bỏ '#') + các '#…' trong nội dung.
    the = tuple(_tokens(" ".join([str(d.get("hashtags") or "")]
                                 + re.findall(r"#(\S+)", str(d.get("text") or "")))))
    hay_norm = _norm(hay)
    co_kiem = False
    for q in queries:
        tu = _tokens(q)
        if not tu:
            continue
        co_kiem = True
        if len(tu) > 1 and all(t.isdigit() for t in tu):
            # Từ khoá NGÀY/SỐ ("20/10", "11/11", "8/3"): các số phải ĐỨNG LIỀN theo
            # đúng thứ tự, nối bằng / - . hoặc chữ "tháng". Luật "đủ mọi chữ" thì
            # "Sale có 20 mẫu giảm giá tới 10%" thành khớp "20/10". Cố ý KHÔNG nhận
            # dạng dính "2010": trùng năm 2010.
            mau = r"\s*(?:[/.\-]|\s+thang\s+)\s*".join(re.escape(t) for t in tu)
            if re.search(rf"(?<!\d){mau}(?!\d)", hay_norm):
                return True
            continue
        gon = "".join(tu)
        if len(tu) > 1 and len(gon) > 3 and (any(gon in t for t in tokens)
                                             or _ghep_lien(tokens, gon)):
            return True
        # Nhiều chữ ("túi xách nữ"): đủ MỌI chữ, không cần đúng thứ tự/liền nhau.
        if all(_khop_mot_tu(tokens, w, the) for w in tu):
            return True
    # Từ khoá không có chữ/số nào (emoji…) thì không kiểm được -> giữ, đừng loại bừa.
    return not co_kiem


# Thị trường dùng chữ Latin — chỉ ở những nước này mới lọc theo hệ chữ.
_THI_TRUONG_LATIN = {"VN", "US", "GB", "AU", "CA", "FR", "DE", "ES", "IT", "NL",
                     "PT", "BR", "PL", "SE", "NO", "DK", "FI", "ID", "MY", "PH",
                     "TR", "CZ", "RO", "HU"}
_NGUONG_PHI_LATIN = 0.3
# Ngôn ngữ chính theo nước, dùng cho `relevanceLanguage` của YouTube.
_NGON_NGU_THEO_NUOC = {"VN": "vi", "TH": "th", "ID": "id", "MY": "ms", "PH": "en",
                       "JP": "ja", "KR": "ko", "CN": "zh", "TW": "zh", "IN": "hi",
                       "US": "en", "GB": "en", "AU": "en", "FR": "fr", "DE": "de",
                       "ES": "es", "BR": "pt", "IT": "it"}


def _ti_le_phi_latin(s: str) -> float:
    chu = [c for c in s if c.isalpha()]
    if not chu:
        return 0.0
    ngoai = 0
    for c in chu:
        try:
            if "LATIN" not in unicodedata.name(c):
                ngoai += 1
        except ValueError:          # ký tự không có tên -> coi như không phải Latin
            ngoai += 1
    return ngoai / len(chu)


_AI_LO = 120           # số bài mỗi LÔ gửi cho model
_AI_TOI_DA = 600       # trần tuyệt đối cho cả lượt
_AI_TIMEOUT = 50       # giây; phải gọn trong trần trả lời 180s của run.py
_AI_TOI_THIEU = 5      # ít hơn thế thì không bõ một lượt gọi model


def _loc_bang_ai(rows: list, queries: list[str], boi_canh: str, log: list,
                 con_lai: float = _AI_TIMEOUT, trang_thai: dict | None = None,
                 da_khop_tu_khoa: bool = True) -> set:
    """Chia lô rồi lọc — KHÔNG BAO GIỜ bỏ qua chỉ vì nhiều bài.

    Bản đầu đặt trần 150 bài, quá thì bỏ lọc. Sai nặng, và đã hỏng thật
    08/09/2026: một lượt quét ra **154 bài** — vượt trần đúng 4 bài — nên bộ lọc
    KHÔNG chạy dòng nào, sheet đầy tin thời sự Ấn Độ. Trần đó vô hiệu hoá bộ lọc
    đúng vào lượt cần nó nhất: quét càng rộng thì nhiễu càng nhiều.

    Nay chia lô `_AI_LO` bài mỗi lượt gọi, chạy tiếp tới khi hết ngân sách thời
    gian. Hết giờ giữa chừng thì **giữ phần chưa xét** (không loại bừa) và ghi
    rõ đã xét được bao nhiêu — người dùng phải biết bộ lọc mới chạy một phần.

    `trang_thai` (nếu truyền) được điền CHUYỆN THỰC SỰ XẢY RA: {"trang_thai":
    "đã chạy" | "chạy một phần" | "bỏ qua vì hết thời gian" | "bỏ qua vì quá ít
    bài" | "lỗi", "da_xet": n}. Bản trước trả `loc_bang_ai=True` cứng kể cả khi
    bộ lọc không chạy dòng nào vì hết giờ — Mark báo "đã lọc bằng AI" sai sự thật.
    """
    tt = trang_thai if trang_thai is not None else {}
    tt.update(trang_thai="bỏ qua vì quá ít bài", da_xet=0)
    if len(rows) < _AI_TOI_THIEU:
        return set()
    # Thiếu `boi_canh` thì VẪN lọc, chỉ đổi cách hỏi: bảo model tự nhìn ra chủ
    # đề chiếm đa số rồi loại những bài lạc hẳn ra. Không để bộ lọc tắt ngúm chỉ
    # vì Mark quên điền một tham số — người dùng lại nhận sheet đầy nhiễu mà
    # không hiểu vì sao lúc được lúc không.
    if not boi_canh:
        log.append("loc_ai: thieu `boi_canh` -> dung che do 'tim bai lac dan'")
    xet = rows[:_AI_TOI_DA]
    if len(rows) > _AI_TOI_DA:
        log.append(f"loc_ai: chi xet {_AI_TOI_DA}/{len(rows)} bai dau (tran tuyet doi)")

    bo: set = set()
    t0 = time.monotonic()
    da_xet = 0
    ket: list[str] = []          # kết cục từng lô: "ok" | "het_gio" | "loi"
    for i0 in range(0, len(xet), _AI_LO):
        con = con_lai - (time.monotonic() - t0)
        if con < 15:
            ket.append("het_gio")
            break
        lo = xet[i0:i0 + _AI_LO]
        n_ket = len(ket)
        bo |= {i0 + j for j in _loc_mot_lo(lo, queries, boi_canh, log, con, ket,
                                           da_khop_tu_khoa)}
        if ket[n_ket:] == ["ok"]:
            da_xet += len(lo)
    if da_xet < len(rows):
        log.append(f"loc_ai: moi xet {da_xet}/{len(rows)} bai thi het ngan sach — "
                   f"phan con lai GIU NGUYEN, chua duoc loc")
    if da_xet and da_xet >= len(rows):
        tt["trang_thai"] = "đã chạy"
    elif da_xet:
        tt["trang_thai"] = "chạy một phần"
    elif "loi" in ket:
        tt["trang_thai"] = "lỗi"
    else:
        tt["trang_thai"] = "bỏ qua vì hết thời gian"
    tt["da_xet"] = da_xet
    return bo


def _loc_mot_lo(rows: list, queries: list[str], boi_canh: str, log: list,
                con_lai: float, ket: list | None = None,
                da_khop_tu_khoa: bool = True) -> set:
    """Nhờ CHÍNH model của Mark đọc bối cảnh ngành hàng rồi loại bài lạc đề.

    Vì sao cần, dù đã có lọc hệ chữ và `exclude`: nhiễu đồng âm có thể viết
    bằng đúng chữ Latin và người dùng không đoán trước được phải loại từ gì.
    Đo thật 08/09/2026 — brand "hapas" (túi xách, trang sức, nước hoa) dính tin
    thời sự về địa danh Hapas ở Rajasthan, hãng đàn HapasGuitars, một cửa hàng
    xi măng ở Ấn Độ và một bản remix Indonesia. Không luật chuỗi nào tách nổi;
    đọc hiểu ngành hàng thì tách được ngay.

    BA nguyên tắc, đừng bỏ khi sửa:
      1. MỘT lượt gọi model cho CẢ lượt quét, không phải mỗi nền tảng một lượt —
         quota Codex dùng chung với meeting agent (bot production ưu tiên hơn).
      2. FAIL-OPEN: model lỗi/hết giờ/trả rác thì GIỮ NGUYÊN mọi bài và ghi vào
         nhật ký. Bộ lọc hỏng mà im lặng vứt dữ liệu là kiểu hỏng tệ nhất ở đây.
      3. KHÔNG CHẮC THÌ GIỮ. Với việc theo dõi brand, bỏ sót một bài nhắc thật
         tai hại hơn là để lọt một bài lạc đề — người dùng nhìn sheet là thấy
         bài thừa, còn bài thiếu thì không bao giờ biết.
    """
    # Ngân sách còn lại phải ĐỦ. `_TOOL_DEADLINE` là 135s và đã chừa 45s cho
    # model viết câu trả lời; cộng thêm 50s gọi model ở đây là vượt trần 180s
    # của run.py và bị cắt CẢ lượt trả lời — người dùng mất trắng cả lượt quét
    # vừa tốn tiền Apify. Không đủ giờ thì thà bỏ lọc, giữ nguyên dữ liệu.
    ket = ket if ket is not None else []
    ngan_sach = min(_AI_TIMEOUT, con_lai)
    if ngan_sach < 15:
        log.append(f"loc_ai: chi con {con_lai:.0f}s -> bo qua de khong lam vo tran "
                   f"tra loi (giu nguyen tat ca)")
        ket.append("het_gio")
        return set()

    dong = []
    for i, (d, _) in enumerate(rows):
        tieu_de = " ".join(str(d.get("text") or "").split())[:110]
        # Kèm nền tảng + hashtag: nhiều bài TikTok/Instagram chỉ nói bằng hashtag
        # ("#HAPAS #túixách"), cắt mất hashtag thì model thấy bài "trống", đoán bừa.
        the = str(d.get("hashtags") or "")[:60]
        dong.append(f"{i}. ({d.get('platform') or '?'}) [{str(d.get('kenh') or '')[:28]}] "
                    f"{tieu_de}" + (f" | hashtag: {the}" if the else ""))
    # Tiền đề phải ĐÚNG: từ 01/10/2026 mọi bài đã qua `_khop_tu_khoa` nên thật sự
    # có nhắc từ khoá; với `khop_long` thì không — nói khác đi cho model khỏi hiểu sai.
    tien_de = ("đã được kiểm là CÓ nhắc từ khoá (trong nội dung, hashtag hoặc tên kênh)"
               if da_khop_tu_khoa else
               "vừa cào về theo từ khoá (có thể KHÔNG chứa nguyên văn từ khoá)")
    nhac = (
        f"Brand đang theo dõi: {', '.join(queries)}\n"
        + (f"Ngành hàng / bối cảnh: {boi_canh}\n\n" if boi_canh else
           "KHÔNG biết trước ngành hàng. Hãy tự nhìn ra chủ đề mà ĐA SỐ bài đang "
           "nói tới — đó chính là ngành hàng của brand — rồi loại những bài lạc "
           "hẳn khỏi chủ đề đó.\n\n")
        + f"Dưới đây là {len(rows)} bài {tien_de}. Nhưng tên "
        f"brand có thể TRÙNG với thứ khác (địa danh, hãng khác, ban nhạc, từ thông "
        f"dụng ở nước khác). Hãy chỉ ra những bài KHÔNG liên quan gì tới brand và ngành "
        f"hàng trên.\n"
        f"QUY TẮC:\n"
        f"- Không chắc thì GIỮ LẠI. Chỉ loại khi rõ ràng là chuyện khác hẳn.\n"
        f"- Brand có thể bán ở NHIỀU NƯỚC. Bài tiếng nước ngoài mà nói ĐÚNG ngành "
        f"hàng trên thì vẫn GIỮ — đừng loại chỉ vì khác ngôn ngữ.\n"
        f"- Chỉ loại khi nội dung thuộc lĩnh vực khác hẳn: thời sự, chính trị, tôn "
        f"giáo, địa danh trùng tên, hãng khác ngành.\n"
        f"CHỈ trả về JSON đúng dạng {{\"loai\": [số, số, ...]}} — không giải thích.\n\n"
        + "\n".join(dong)
    )

    def _chay():
        from hermes_cli.runtime_provider import resolve_runtime_provider
        from run_agent import AIAgent
        rt = resolve_runtime_provider(requested=config.agent_provider)
        ag = AIAgent(model=config.agent_model, provider=rt.get("provider"),
                     api_mode=rt.get("api_mode"), base_url=rt.get("base_url"),
                     api_key=rt.get("api_key"), max_iterations=1, quiet_mode=True,
                     enabled_toolsets=[], disabled_toolsets=["terminal"])
        return (ag.run_conversation(nhac) or {}).get("final_response") or ""

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            tra_loi = ex.submit(_chay).result(timeout=ngan_sach)
    except _FutTimeout:
        log.append(f"loc_ai: model qua {ngan_sach:.0f}s chua tra loi -> giu nguyen tat ca")
        ket.append("het_gio")
        return set()
    except Exception as e:  # noqa: BLE001
        log.append(f"loc_ai: KHONG chay duoc ({type(e).__name__}) -> giu nguyen tat ca")
        ket.append("loi")
        return set()

    m = re.search(r'\{[^{}]*"loai"\s*:\s*\[[^\]]*\][^{}]*\}', tra_loi or "", re.S)
    if not m:
        log.append("loc_ai: model tra ve khong dung dang JSON -> giu nguyen tat ca")
        ket.append("loi")
        return set()
    try:
        chi_so = json.loads(m.group(0)).get("loai") or []
    except ValueError:
        log.append("loc_ai: JSON hong -> giu nguyen tat ca")
        ket.append("loi")
        return set()

    bo = {int(x) for x in chi_so if isinstance(x, (int, float, str))
          and str(x).strip().lstrip("-").isdigit() and 0 <= int(x) < len(rows)}
    # Chốt an toàn: model đòi loại gần hết thì gần như chắc chắn nó hiểu sai đề
    # (hoặc bối cảnh người dùng đưa quá hẹp). Thà giữ thừa còn hơn xoá sạch.
    if len(bo) > len(rows) * 0.9:
        log.append(f"loc_ai: model doi loai {len(bo)}/{len(rows)} bai — NGHI SAI, "
                   f"giu nguyen tat ca")
        ket.append("loi")
        return set()
    ket.append("ok")
    return bo


def _bi_loai_tru(d: dict, loai_tru: list[str]) -> bool:
    """Bài có chứa từ người dùng yêu cầu LOẠI TRỪ.

    Vì sao cần, dù đã có lọc hệ chữ: nhiễu đồng âm có thể viết bằng ĐÚNG hệ chữ
    Latin. Đo thật 08/09/2026 với brand "hapas" — Hapas còn là tên một địa danh
    ở Rajasthan (Ấn Độ) đang có vụ việc nóng, nên lọt cả tin phiên âm Latin
    ("Salim Hapas and Sania in Dubai") lẫn hãng đàn HapasGuitars. Không luật tự
    động nào đoán nổi cái nào liên quan tới brand; người dùng biết, nên đưa cần
    gạt cho họ.
    """
    return bool(_tu_loai_tru_khop(d, loai_tru))


def _tu_loai_tru_khop(d: dict, loai_tru: list[str]) -> str:
    """Từ loại trừ đầu tiên bài chứa (để ghi LÝ DO vào tab Bị loại), "" nếu không."""
    if not loai_tru:
        return ""
    hay = _norm(f"{d.get('text','')} {d.get('hashtags','')} {d.get('kenh','')} "
                f"{d.get('username') or ''}")
    return next((x for x in loai_tru if x and _norm(x) in hay), "")


def _ngoai_thi_truong(d: dict, country: str) -> bool:
    """Bài KHỚP từ khoá nhưng thuộc hệ chữ khác hẳn thị trường đang quét.

    Vì sao cần, đo thật 08/09/2026: quét brand "hapas" trên YouTube trả về 23/25
    video "hợp lệ" — vì Hapas còn là TÊN MỘT ĐỊA DANH ở Rajasthan (Ấn Độ), nên
    kết quả đầy tin thời sự tiếng Hindi về vụ Sania–Salim, cộng hashtag thương
    hiệu tiếng Thái và hãng đàn HapasGuitars. `_relevant()` giữ hết vì chúng
    THẬT SỰ chứa chữ "hapas" — lọc đúng như thiết kế, nhưng thiết kế chưa đủ.

    `regionCode=VN` không cứu được: YouTube chỉ dùng nó để xếp hạng chứ không
    lọc địa lý. Nên phải lọc phía mình, và lọc theo HỆ CHỮ chứ không theo danh
    sách nước — luật chung, không phải luật riêng cho tiếng Hindi.

    KHÔNG dùng cho nước không viết chữ Latin (TH, IN, JP…) — ở đó chính nội dung
    cần tìm mới là phi-Latin.
    """
    if country.upper() not in _THI_TRUONG_LATIN:
        return False
    # CHỈ đo phần đầu nội dung + tên kênh, không đo cả mô tả. Mô tả YouTube dài
    # và thường lẫn nhiều chữ Latin (link, hashtag, tên phiên âm) nên pha loãng
    # tỉ lệ: đo cả mô tả thì tin tiếng Hindi tụt xuống dưới ngưỡng và lọt lưới,
    # đúng như lần đo đầu 08/09/2026.
    # `text` của YouTube là "tiêu đề — mô tả"; chỉ lấy phần TIÊU ĐỀ. Mô tả lẫn
    # link/hashtag Latin, để lọt vào phép đo là tin Devanagari tụt dưới ngưỡng.
    dau = str(d.get("text", "")).split(" — ", 1)[0][:120]
    return _ti_le_phi_latin(f"{dau} {d.get('kenh','')}") >= _NGUONG_PHI_LATIN


# ── Cổng thị trường VN ──
# Vì sao, rà sheet 01/10/2026: lọc hệ chữ chỉ bắt chữ phi-Latin, nên bài TIẾNG ANH
# lọt hết — YouTube ra "SHINAI – Hapas Ashen // Humanity's Last Breath" (ban nhạc
# metal), Threads ra tote của HAPAS THAILAND. Và lọc cũ chỉ chạy khi KHÔNG có
# `boi_canh`, trong khi Mark gần như luôn điền `boi_canh` -> cổng gần như chưa mở.
# Nay quét VN thì luôn kiểm; bài bị loại không mất mà sang tab "Bị loại".
_NEN_TANG_CONG_VN = ("youtube", "threads")   # + TikTok từ actor dự phòng (không lọc nước)
_DAU_CHI_TIENG_VIET = {"̆", "̛", "̣", "̉"}  # ă · ơ ư · ạ · ả
# Âm tiết tiếng Việt viết KHÔNG dấu, ít trùng tiếng Anh/Pháp. Người Việt hay gõ không
# dấu; thiếu danh sách này thì "tui xach dep qua" thành "tiêu đề tiếng nước ngoài".
_TU_VIET_KHONG_DAU = {
    "khong", "duoc", "nhung", "nhieu", "minh", "voi", "nguoi", "xinh", "xach", "nhe",
    "nha", "roi", "dep", "tui", "nhat", "thich", "chung", "cua", "mua", "vay", "dang",
    "ngay", "thoi", "biet", "muon", "nhin", "dien", "thoai", "trang", "suc", "nuoc",
    "hoa", "sieu", "cuc", "xiu", "luon", "gium", "nhau", "chiec", "dau",
}


def _chu_chi_tieng_viet(c: str) -> bool:
    """ă â đ ơ ư, nguyên âm có dấu nặng/hỏi, nguyên âm ghép dấu (ấ ề ổ…), ẽ ĩ ũ ỹ.

    Không tính à á è é ê ô ã: tiếng Pháp/Tây Ban Nha/Bồ Đào Nha cũng có.
    """
    if c in "đĐ":
        return True
    n = unicodedata.normalize("NFD", c)
    dau = n[1:]
    if not dau:
        return False
    if any(m in _DAU_CHI_TIENG_VIET for m in dau) or len(dau) >= 2:
        return True
    goc = n[0].lower()
    return (goc == "a" and dau == "̂") or (goc in "eiuy" and dau == "̃")


def _la_noi_dung_vn(d: dict) -> bool:
    """Bài có dấu hiệu Việt Nam không: chữ tiếng Việt, ngôn ngữ 'vi', kênh ở VN."""
    if str(d.get("_quoc_gia") or "").upper() == "VN":
        return True
    if str(d.get("_ngon_ngu") or "").lower().startswith("vi"):
        return True
    s = unicodedata.normalize("NFC", f"{d.get('text') or ''} {d.get('kenh') or ''}")
    if sum(_chu_chi_tieng_viet(c) for c in s) >= 2:
        return True
    return len(set(_tokens(s)) & _TU_VIET_KHONG_DAU) >= 2


def _so_tu_latin(s: str) -> int:
    """Số từ chữ Latin (≥2 ký tự) trong tiêu đề, BỎ hashtag/@mention/link —
    "#hapas #tuixach #fyp #xuhuong #tiktokvn" không phải câu tiếng Anh."""
    s = re.sub(r"(https?://\S+|[#@]\S+)", " ", unicodedata.normalize("NFC", s or ""))
    return sum(1 for w in re.findall(r"[^\W\d_]+", s)
               if len(w) >= 2 and all("LATIN" in unicodedata.name(c, "") for c in w))


# "299k" chỉ là giá khi KHÔNG đi kèm chữ đếm tương tác: "100k views", "50k followers"
# là cách viết chung toàn cầu — khớp nó thì video metal nước ngoài ghi "100k views
# milestone" lọt lại (review 01/10/2026). Số điện thoại 10 số chỉ tính khi có chữ gọi
# đi kèm (sđt/hotline/zalo…), không thì mã đơn hàng ngẫu nhiên cũng thành "VN".
_DAU_HIEU_VN_RE = re.compile(
    r"(\.vn\b|₫|\bvnd\b"
    r"|\b\d{2,4}\s?k\b(?!\s*(?:views?|likes?|followers?|follows?|fl|subs?|subscribers?"
    r"|plays?|shares?|comments?|cmts?|luot|lượt|tim|mat|mắt)\b)"
    r"|\b\d{1,3}(?:[.,]\d{3})+\s?(?:d|đ|vnd)\b"
    r"|\+84|(?:sdt|sđt|hotline|zalo|lien he|liên hệ|\blh)\W{0,3}0[35789]\d{8}\b"
    r"|\bviet\s?nam\b|\bsai\s?gon\b|\bha\s?noi\b|\bda\s?nang\b|\b(?:tp)?hcm\b)")
_TU_VN = ("vietnam", "saigon", "hanoi")
# Tên nước khác nằm TRONG tên kênh/username = tài khoản của thị trường đó ("HAPAS
# THAILAND", Threads 01/10/2026). Không xét trong nội dung: kênh VN viết "ship đi
# Thailand" vẫn là bài VN. Không có "thai" trơn: "Thái" bỏ dấu cũng thành "thai".
_NUOC_KHAC_TRONG_KENH = ("thailand", "philippines", "malaysia", "indonesia", "singapore",
                         "cambodia", "myanmar", "india", "japan", "korea", "usa")


def _co_dau_hieu_vn(d: dict) -> bool:
    """Dấu hiệu VN ngoài chữ có dấu: '#tiktokvn', 'hapas.vn', giá '299k'/'₫', +84…

    Rà 01/10/2026: caption tiếng Anh của chính kênh brand VN ("HAPAS Flash Sale
    Today Only…") bị cổng loại nhầm vì không có chữ tiếng Việt nào.
    """
    hay = " ".join(str(d.get(k) or "") for k in ("text", "hashtags", "kenh", "username"))
    if _DAU_HIEU_VN_RE.search(hay.lower()) or _DAU_HIEU_VN_RE.search(_norm(hay)):
        return True
    return any(t == "vn" or (len(t) > 2 and t.endswith("vn")) or any(x in t for x in _TU_VN)
               for t in _tokens(hay))


def _ly_do_ngoai_vn(d: dict, p: str = "youtube", queries: list[str] | None = None) -> str:
    """Lý do bài nằm NGOÀI thị trường VN, "" nếu giữ.

    Chỉ loại khi CHẮC, theo thứ tự:
      1. kênh khai nước khác VN -> loại;
      2. có dấu hiệu Việt (chữ có dấu, ngôn ngữ 'vi', kênh ở VN, '#tiktokvn',
         '.vn', giá '299k'/'₫', +84…) -> giữ;
      3. tên kênh/username chứa tên nước khác ("HAPAS THAILAND") -> loại;
      4. từ khoá khớp ngay ở TÊN KÊNH/USERNAME (kênh của brand hoặc fan) -> giữ;
      5. chỉ YouTube: tiêu đề là câu ≥5 từ Latin -> loại.
    Vì sao (5) chỉ còn YouTube: nhiễu tiếng Anh thật nằm ở YouTube (ban metal
    "SHINAI – Hapas Ashen // Humanity's Last Breath", 01/10/2026); trên TikTok/
    Threads luật này loại nhầm caption tiếng Anh của chính brand. Ngưỡng giữ 5 vì
    tiêu đề SHINAI chỉ có 6 từ Latin — nâng lên 7 là lọt đúng bài cần loại.
    """
    qg = str(d.get("_quoc_gia") or "").upper()
    if qg and qg != "VN":
        return f"ngoài thị trường VN: kênh đăng ký ở nước {qg}"
    if _la_noi_dung_vn(d) or _co_dau_hieu_vn(d):
        return ""
    kenh_khop = bool(queries) and _khop_tu_khoa(
        {"kenh": d.get("kenh"), "username": d.get("username")}, queries)
    # Tên nước chỉ tính khi đi CÙNG từ khoá trong tên kênh: "HAPAS THAILAND" là tài khoản
    # brand ở thị trường khác; còn "Korea Cosmetics Shop", "Thailand Closet" là shop VN
    # đặt tên theo nguồn hàng nhập — không được loại vì tên nước (review 01/10/2026).
    if kenh_khop:
        kenh = _tokens(f"{d.get('kenh') or ''} {d.get('username') or ''}")
        nuoc = next((n for n in _NUOC_KHAC_TRONG_KENH if any(n in t for t in kenh)), "")
        if nuoc:
            return f"ngoài thị trường VN: tài khoản của thị trường '{nuoc}'"
        return ""
    tieu_de = str(d.get("text") or "").split(" — ", 1)[0][:200]
    if p == "youtube" and _so_tu_latin(tieu_de) >= 5:
        return "ngoài thị trường VN: không có dấu hiệu tiếng Việt, tiêu đề tiếng nước ngoài"
    return ""


# Mỗi adapter: chạy actor rồi trả list[(dict đã chuẩn hoá, datetime giờ VN)]
def _fanout(fn, keys: list[str]) -> list[dict]:
    """Chạy `fn(kw)` cho từng từ khoá SONG SONG rồi gộp kết quả.

    Instagram và Facebook chỉ nhận MỘT từ khoá mỗi lần gọi actor. Chạy tuần tự
    thì 6 từ khoá = 6 lần gọi nối đuôi, cộng với các nền tảng khác là vượt trần
    trả lời 180s của run.py (đã xảy ra thật 26/08/2026). Từ khoá nào lỗi thì bỏ
    qua từ khoá đó, không làm hỏng cả nguồn.
    """
    if len(keys) <= 1:
        return fn(keys[0]) if keys else []
    out = []
    with ThreadPoolExecutor(max_workers=min(len(keys), 5)) as ex:
        for f in [ex.submit(fn, k) for k in keys]:
            try:
                out.extend(f.result())
            except Exception as e:  # noqa: BLE001
                print(f"[social_listen] fanout lỗi 1 từ khoá: {_che_token(e)}")
    return out


def _fetch_tiktok_fallback(q: list[str], limit: int) -> list[dict]:
    """clockworks/tiktok-hashtag-scraper -> đổi về đúng shape của apidojo.

    Chỉ nhận HASHTAG (không keyword search, không lọc ngày/quốc gia) nhưng bù
    lại có `authorMeta.fans` (followers) và chạy ổn định. Đắt hơn ~10 lần
    ($0.003 vs $0.0003 mỗi video) nên chỉ gọi khi actor chính trả rỗng.
    """
    # `resultsPerPage` tính cho TỪNG hashtag, và actor bỏ qua `maxItems` trên URL.
    # Đo thật 25/09/2026: 5 hashtag × 100 = đòi 500 video, cào 333 thì chạm trần
    # $1 và bị cắt ngang. Chia `limit` cho số hashtag như Instagram/Facebook để
    # `limit` đúng nghĩa "tối đa MỖI nền tảng".
    tags = [x.lstrip("#") for x in q]
    per = max(1, limit // max(1, len(tags)))
    try:
        raw = _call(_ACTORS["tiktok_fallback"],
                    {"hashtags": tags, "resultsPerPage": per}, limit)
    except Exception as e:  # noqa: BLE001
        print(f"[social_listen] tiktok fallback lỗi: {_che_token(e)}")
        return []
    out = []
    for it in raw:
        am = it.get("authorMeta") or {}
        out.append({
            "uploadedAtFormatted": it.get("createTimeISO"),
            "channel": {"name": am.get("nickName") or am.get("name"),
                        "username": am.get("name"),
                        "followers": am.get("fans")},
            "views": it.get("playCount"), "likes": it.get("diggCount"),
            "comments": it.get("commentCount"), "shares": it.get("shareCount"),
            "hashtags": [h.get("name") for h in (it.get("hashtags") or []) if isinstance(h, dict)],
            "title": it.get("text"), "postPage": it.get("webVideoUrl"),
            # Actor dự phòng KHÔNG lọc quốc gia -> cần tín hiệu cho cổng thị trường
            # VN. `textLanguage` chưa kiểm chứng có mặt ở mọi bản actor: đọc phòng
            # thủ, thiếu thì cổng chỉ dựa vào chữ tiếng Việt trong nội dung/kênh.
            "textLanguage": it.get("textLanguage"),
            "_nguon": "clockworks (dự phòng)",
        })
    return out


def _fetch_tiktok(q: list[str], limit: int, country: str, d_from, d_to) -> list[tuple]:
    raw = _call(_ACTORS["tiktok"], {
        "keywords": q, "maxItems": limit, "location": country,
        "sortType": "DATE_POSTED", "dateRange": _tiktok_enum(d_from),
        "includeSearchKeywords": True,
    }, limit)
    # Actor trả sentinel {"noResults": true} khi TikTok search không ra gì. Nếu
    # đếm chúng như dữ liệu thì báo cáo thành "cào 10 -> giữ 0", người đọc tưởng
    # bộ lọc ngày loại hết, trong khi thực tế nguồn KHÔNG trả gì. Phải loại sớm
    # để rơi vào nhánh cảnh báo "cào 0 item" cho đúng bản chất.
    raw = [it for it in raw if not it.get("noResults")]
    # LEO THANG KHI SẢN LƯỢNG QUÁ THẤP, không phải chỉ khi rỗng.
    #
    # Đo thật 08/09/2026, brand "hapas" + "matemade", 01/08→08/09, limit=100:
    #   apidojo    : 10 bài (7 trong khoảng) — và ĐÚNG 10 ở MỌI biến thể tham số
    #                (1 hay 2 từ khoá, có hay không `location`, maxItems 50 hay
    #                100). Đây là TRẦN CỨNG của actor cho tìm-theo-keyword, không
    #                phải "thị trường chỉ có bấy nhiêu".
    #   clockworks : 120 bài, 60 bài trong khoảng, 99 kênh — gấp 12 lần.
    # `startUrls` với URL tag/search đều trả 0 nên không cứu được.
    #
    # Luật cũ "chỉ gọi dự phòng khi apidojo RỖNG" nên không bao giờ chạy: apidojo
    # trả 10 chứ không rỗng. Người dùng nhận 7 bài và tin đó là tất cả, trong khi
    # brand đang chạy chiến dịch rầm rộ — đúng kiểu hỏng không crash, không báo
    # lỗi, chỉ sai số liệu.
    #
    # Đánh đổi: clockworks đắt hơn ~10 lần ($0.003 vs $0.0003 mỗi video). Chấp
    # nhận, vì báo cáo sai về thị trường đắt hơn nhiều so với tiền một lần chạy.
    # Chi phí vẫn bị chặn bởi `limit` của người dùng, và được báo ra ở `nguon`.
    thieu = len(raw) < min(limit, _TIKTOK_NGUONG_LEO_THANG)
    if thieu:
        them = _fetch_tiktok_fallback(q, limit)
        if them:
            co = {str(x.get("postPage") or "") for x in raw}
            raw = raw + [x for x in them if str(x.get("postPage") or "") not in co]
    out = []
    for it in raw:
        dt = _to_vn(it.get("uploadedAtFormatted"))
        ch = it.get("channel") or {}
        # KHÔNG mang `searchKeyword` (includeSearchKeywords vọng lại từ khoá) vào
        # dòng: `_khop_tu_khoa` mà đọc trường đó thì bài nào cũng "khớp".
        out.append(({
            "kenh": ch.get("name") or ch.get("username") or "",
            "username": ch.get("username") or "",
            "_ngon_ngu": str(it.get("textLanguage") or ""),
            "followers": int(ch.get("followers") or 0),
            "views": int(it.get("views") or 0),
            "likes": int(it.get("likes") or 0),
            "comments": int(it.get("comments") or 0),
            "shares": int(it.get("shares") or 0),
            "hashtags": _join(it.get("hashtags")),
            "text": str(it.get("title") or "")[:1000],
            "link": it.get("postPage") or "",
            "_nguon": it.get("_nguon") or "apidojo",
        }, dt))
    return out


def _fetch_instagram(q: list[str], limit: int, country: str, d_from, d_to) -> list[tuple]:
    # Actor chỉ nhận MỘT keyword (string) -> chạy lần lượt từng từ khoá.
    per = max(1, limit // max(1, len(q)))
    raw = _fanout(lambda kw: _call(_ACTORS["instagram"], {
        "keyword": kw, "getPosts": True, "getReels": True, "maxItems": per,
    }, per), q)
    out = []
    if True:
        for it in raw:
            dt = _to_vn(it.get("createdAt"))
            ow = it.get("owner") or {}
            vid = it.get("video") or {}
            cap = str(it.get("caption") or "")
            out.append(({
                "kenh": ow.get("username") or ow.get("fullName") or "",
                "followers": 0,           # actor KHÔNG trả follower
                "views": int(vid.get("playCount") or 0),
                "likes": int(it.get("likeCount") or 0),
                "comments": int(it.get("commentCount") or 0),
                "shares": 0,              # actor KHÔNG trả share
                "hashtags": _tags_from(cap),
                "text": cap[:1000],
                "link": it.get("url") or "",
            }, dt))
    return out


def _fetch_facebook(q: list[str], limit: int, country: str, d_from, d_to) -> list[tuple]:
    # Actor chỉ nhận MỘT query (string); có lọc ngày server-side thật.
    per = max(1, limit // max(1, len(q)))
    raw = _fanout(lambda kw: _call(_ACTORS["facebook"], {
        "query": kw, "search_type": "posts", "max_results": per,
        "start_date": d_from.strftime("%Y-%m-%d"),
        "end_date": d_to.strftime("%Y-%m-%d"),
    }, per), q)
    out = []
    if True:
        for it in raw:
            dt = _to_vn(it.get("timestamp"))
            au = it.get("author") or {}
            msg = str(it.get("message") or "")
            out.append(({
                "kenh": au.get("name") or "",
                "followers": 0,           # actor KHÔNG trả follower
                "views": int(it.get("video_view_count") or 0),
                "likes": int(it.get("reactions_count") or 0),
                "comments": int(it.get("comments_count") or 0),
                "shares": int(it.get("reshare_count") or 0),
                "hashtags": _tags_from(msg),
                "text": msg[:1000],
                "link": it.get("url") or "",
            }, dt))
    return out


def _fetch_youtube(q: list[str], limit: int, country: str, d_from, d_to) -> list[tuple]:
    """YouTube Data API v3: search -> batch video stats -> batch channel stats.

    `publishedAfter`/`publishedBefore` lọc ngày server-side thật. Các keyword
    được nối bằng toán tử OR (`|`) để một trang kết quả chỉ tốn MỘT lượt trong
    bucket `search.list` 100 lượt/ngày, thay vì một lượt cho từng keyword.
    """
    search_items: list[dict] = []
    seen_ids: set[str] = set()
    page_token = ""
    query = "|".join(x for x in q if x)
    while len(search_items) < limit:
        take = min(50, limit - len(search_items))
        params = {
            "part": "snippet",
            "type": "video",
            "q": query,
            "order": "date",
            "maxResults": take,
            "publishedAfter": _rfc3339_utc(d_from),
            "publishedBefore": _rfc3339_utc(d_to),
        }
        if len(country) == 2 and country.isalpha():
            params["regionCode"] = country.upper()
            # `regionCode` CHỈ đổi thứ tự xếp hạng, KHÔNG lọc địa lý — đo thật
            # 08/09/2026: đặt VN vẫn trả về tin tiếng Hindi về địa danh Hapas ở
            # Rajasthan. `relevanceLanguage` kéo thêm kết quả đúng ngôn ngữ lên,
            # nhưng cũng không phải bộ lọc cứng, nên vẫn phải lọc lại phía mình
            # bằng `_ngoai_thi_truong()`.
            ngon_ngu = _NGON_NGU_THEO_NUOC.get(country.upper())
            if ngon_ngu:
                params["relevanceLanguage"] = ngon_ngu
        if page_token:
            params["pageToken"] = page_token
        data = _youtube_get("search", params)
        items = data.get("items") or []
        if not isinstance(items, list):
            items = []
        for item in items:
            if not isinstance(item, dict):
                continue
            ident = item.get("id") or {}
            vid = ident.get("videoId") if isinstance(ident, dict) else ""
            if not vid or vid in seen_ids:
                continue
            seen_ids.add(vid)
            search_items.append(item)
            if len(search_items) >= limit:
                break
        page_token = str(data.get("nextPageToken") or "")
        if not items or not page_token:
            break

    video_ids = [str((x.get("id") or {}).get("videoId") or "") for x in search_items]
    video_ids = [x for x in video_ids if x]
    videos: dict[str, dict] = {}
    for batch in _chunks(video_ids):
        data = _youtube_get("videos", {
            "part": "snippet,statistics", "id": ",".join(batch), "maxResults": 50,
        })
        for item in data.get("items") or []:
            if isinstance(item, dict) and item.get("id"):
                videos[str(item["id"])] = item

    channel_ids = []
    for item in search_items:
        snippet = item.get("snippet") or {}
        cid = str(snippet.get("channelId") or "")
        if cid and cid not in channel_ids:
            channel_ids.append(cid)
    subscribers: dict[str, int] = {}
    quoc_gia: dict[str, str] = {}
    for batch in _chunks(channel_ids):
        # Thêm `snippet` để lấy `snippet.country` cho cổng thị trường VN. Quota
        # channels.list là 1 đơn vị mỗi lượt gọi BẤT KỂ số part — không tốn thêm.
        data = _youtube_get("channels", {
            "part": "snippet,statistics", "id": ",".join(batch), "maxResults": 50,
        })
        for item in data.get("items") or []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            stats = item.get("statistics") or {}
            subscribers[str(item["id"])] = int(stats.get("subscriberCount") or 0)
            quoc_gia[str(item["id"])] = str((item.get("snippet") or {}).get("country") or "")

    out = []
    for found in search_items:
        vid = str((found.get("id") or {}).get("videoId") or "")
        detail = videos.get(vid) or {}
        snippet = detail.get("snippet") or found.get("snippet") or {}
        stats = detail.get("statistics") or {}
        title = html.unescape(str(snippet.get("title") or ""))
        desc = html.unescape(str(snippet.get("description") or ""))
        tags = _join(snippet.get("tags"))
        hashtags = _tags_from(f"{title} {desc}")
        if tags:
            hashtags = _join([hashtags, tags])
        channel_id = str(snippet.get("channelId") or "")
        out.append(({
            "kenh": html.unescape(str(snippet.get("channelTitle") or "")),
            # Tín hiệu cho cổng thị trường VN (`_ly_do_ngoai_vn`): nước kênh tự khai
            # và ngôn ngữ video tự khai — videos.list part=snippet đã trả sẵn.
            "_quoc_gia": quoc_gia.get(channel_id, ""),
            "_ngon_ngu": str(snippet.get("defaultAudioLanguage")
                             or snippet.get("defaultLanguage") or ""),
            "followers": subscribers.get(channel_id, 0),
            "views": int(stats.get("viewCount") or 0),
            "likes": int(stats.get("likeCount") or 0),
            "comments": int(stats.get("commentCount") or 0),
            "shares": 0,                       # YouTube không công khai share
            "hashtags": hashtags,
            "text": f"{title} — {desc}"[:1000],
            "link": f"https://www.youtube.com/watch?v={vid}",
        }, _to_vn(snippet.get("publishedAt"))))
    return out


def _fetch_threads(q: list[str], limit: int, country: str, d_from, d_to) -> list[tuple]:
    raw = _call(_ACTORS["threads"], {
        "mode": "search", "keywords": q,
        "max_posts": max(10, limit),           # actor từ chối max_posts < 10
        "start_date": d_from.strftime("%Y-%m-%d"),
        "end_date": d_to.strftime("%Y-%m-%d"),
    }, limit, mem=_MEMORY.get("threads"))
    out = []
    for it in raw:
        txt = str(it.get("text_content") or "")
        out.append(({
            "kenh": it.get("display_name") or it.get("username") or "",
            "username": it.get("username") or "",
            "followers": int(it.get("followers_count") or 0),
            "views": int(it.get("view_count") or 0),
            "likes": int(it.get("like_count") or 0),
            "comments": int(it.get("reply_count") or 0),
            "shares": int(it.get("repost_count") or it.get("share_count") or 0),
            "hashtags": _tags_from(txt) or str(it.get("topic_tag") or ""),
            "text": txt[:1000],
            "link": it.get("post_url") or "",
        }, _to_vn(it.get("created_at_timestamp") or it.get("created_at"))))
    return out


_FETCH = {"tiktok": _fetch_tiktok, "instagram": _fetch_instagram,
          "facebook": _fetch_facebook, "youtube": _fetch_youtube,
          "threads": _fetch_threads}


# ───────────────────────── Lark Sheet ─────────────────────────
def _create_sheet(title: str) -> tuple[str, str]:
    r = lark.call("POST", "/open-apis/sheets/v3/spreadsheets", body={"title": title})
    sp = (r.get("data") or {}).get("spreadsheet") or {}
    tok = sp.get("spreadsheet_token") or ""
    if not tok:
        raise RuntimeError(f"Không tạo được sheet: {r}")
    return tok, sp.get("url") or ""


def _first_sheet_id(token: str) -> str:
    r = lark.call("GET", f"/open-apis/sheets/v3/spreadsheets/{token}/sheets/query")
    sheets = (r.get("data") or {}).get("sheets") or []
    if not sheets:
        raise RuntimeError("Sheet vừa tạo không có sub-sheet nào.")
    return sheets[0].get("sheet_id") or ""


def _cot(n: int) -> str:
    """Số cột (1-based) → chữ cột Excel: 1→A, 12→L, 27→AA."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _write_values(token: str, sheet_id: str, values: list[list], dong_dau: int = 1) -> None:
    # Vùng ghi theo đúng số cột của dữ liệu. Cố định "A:L" (12 cột của social_listen) làm
    # tool Shopee 13 cột hỏng: "columns of value:13 > range" (đo thật 25/09/2026).
    # `dong_dau`: dòng bắt đầu (1-based) — để ghi NỐI dưới dữ liệu sẵn có mà không đè.
    rong = _cot(max((len(r) for r in values), default=1))
    for i in range(0, len(values), 1000):
        chunk = values[i:i + 1000]
        a = dong_dau + i
        lark.call("POST", f"/open-apis/sheets/v2/spreadsheets/{token}/values_batch_update",
                  body={"valueRanges": [{
                      "range": f"{sheet_id}!A{a}:{rong}{a + len(chunk) - 1}",
                      "values": chunk}]})


_TAB_BI_LOAI = "Bị loại"


def _them_tab(token: str, ten: str) -> str:
    """Thêm một tab vào sheet, trả sheet_id. Cùng request `addSheet` mà
    san_link.ghi_nhieu_tab đang chạy thật; không lấy được id thì ném lỗi để bên
    gọi chuyển sang phương án dự phòng (ghi dưới sheet chính)."""
    d = lark.call("POST", f"/open-apis/sheets/v2/spreadsheets/{token}/sheets_batch_update",
                  body={"requests": [{"addSheet": {"properties": {"title": ten}}}]})
    replies = (d.get("data") or {}).get("replies") or []
    sid = ((replies[0].get("addSheet") or {}).get("properties") or {}).get("sheetId") \
        if replies and isinstance(replies[0], dict) else ""
    if not sid:
        raise RuntimeError("Lark không trả sheetId cho tab mới.")
    return sid


def _ghi_bi_loai(token: str, sheet_id: str, so_dong_chinh: int,
                 bi_loai_rows: list[list]) -> str:
    """Ghi bài BỊ LOẠI (kèm lý do) — trả nơi đã ghi để báo cho model.

    Vì sao: bài bị lọc mà biến mất thì bộ lọc sai cũng không ai phát hiện được.
    Ưu tiên tab riêng "Bị loại" để sheet chính sạch (người dùng lọc/đếm/sắp xếp
    trên đó). Thêm tab hỏng thì KHÔNG bỏ dữ liệu: ghi nối dưới sheet chính, cách
    một dòng trống và một dòng phân cách "BỊ LOẠI — lý do". Sheet chính đã ghi
    xong TRƯỚC bước này nên lỗi ở đây không làm hỏng dữ liệu chính.
    """
    try:
        _write_values(token, _them_tab(token, _TAB_BI_LOAI), bi_loai_rows)
        return f"tab '{_TAB_BI_LOAI}'"
    except Exception as e:  # noqa: BLE001
        print(f"[social_listen] thêm tab Bị loại hỏng, ghi dưới sheet chính: {_che_token(e)}")
    # Đệm dòng phân cách cho ĐỦ số cột: một vùng ghi mà dòng 1 cột lẫn dòng 13 cột
    # thì Lark có thể từ chối cả khối (cùng loại lỗi "columns of value > range").
    rong = max((len(r) for r in bi_loai_rows), default=1)
    phan_cach = [[""] * rong,
                 ["BỊ LOẠI — lý do ở cột cuối (bài khớp sai/ngoài thị trường)"]
                 + [""] * (rong - 1)]
    _write_values(token, sheet_id, phan_cach + bi_loai_rows, dong_dau=so_dong_chinh + 1)
    return "cuối sheet chính (dưới dòng 'BỊ LOẠI')"


def _grant(token: str, open_id: str) -> bool:
    """File do bot tạo nên bot là chủ; KHÔNG cấp quyền thì người dùng mở không được."""
    try:
        lark.call("POST", f"/open-apis/drive/v1/permissions/{token}/members", query={"type": "sheet"},
                  body={"member_type": "openid", "member_id": open_id, "perm": "edit"})
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[social_listen] cấp quyền thất bại: {_che_token(e)}")
        return False


def _top_per_platform(hits: list[tuple], n: int) -> list[dict]:
    """Top N của TỪNG nền tảng, không phải top N toàn cục.

    Sắp toàn cục theo views sẽ vùi Facebook/Instagram xuống đáy vĩnh viễn (hai
    nguồn đó thường trả views = 0), khiến bản xem nhanh trông như chỉ có TikTok.
    """
    out, seen = [], {}
    for d, dt in hits:
        p = d["platform"]
        if seen.get(p, 0) >= n:
            continue
        seen[p] = seen.get(p, 0) + 1
        out.append({"nen_tang": p, "kenh": d["kenh"], "followers": d["followers"],
                    "views": d["views"], "likes": d["likes"],
                    "ngay": dt.strftime("%Y-%m-%d"), "link": d["link"]})
    return out


# ───────────────────────── tool ─────────────────────────
SCHEMA = {
    "name": "social_listen",
    "description": (
        "Social listening đa nền tảng: cào post theo TỪ KHOÁ/HASHTAG trong MỘT KHOẢNG "
        "NGÀY trên TikTok + Facebook + Instagram + YouTube + Threads, gộp vào MỘT Lark Sheet, cấp quyền cho "
        "người hỏi và trả LINK SHEET. Dùng khi ai nhờ 'soi hashtag X từ ngày… tới ngày…', "
        "'quét từ khoá Y trên fb', 'tìm KOC đang nói về brand Z'.\n"
        "TREND CHUNG (không có brand/từ khoá cụ thể — 'trend TikTok đang nổi', 'âm thanh "
        "đang hot', 'format nào đang viral'): gọi với `che_do`='trend', KHÔNG cần "
        "`queries` hay ngày. Đừng cào hashtag chung chung kiểu #trend/#viral/#xuhuong: đo "
        "thật chỉ ra mẫu ngẫu nhiên, lẫn video cũ và nước ngoài. Kết quả trend: `hashtag` "
        "là bảng CHÍNH THỨC của TikTok (ưu tiên nêu hashtag `huong`='lên'); `video` là top "
        "video của vùng; `am_thanh`/`hieu_ung` SUY từ mẫu nên phải nói rõ cỡ mẫu "
        "(`mau_am_thanh`) và chỉ gọi là tín hiệu. `am_thanh` rỗng thì nói thẳng là mẫu "
        "chưa thấy âm thanh nào nhiều kênh dùng lại, đừng bịa tên. Hashtag hoặc hiệu ứng "
        "gắn tên brand (vd #larocheposaysuperbrandday, #hoptaccung…, xem `di_kem_hashtag`) "
        "là CHIẾN DỊCH TRẢ TIỀN của brand, nói rõ như vậy, đừng gọi là trend tự nhiên.\n"
        "NỀN TẢNG: không nói gì thì cào CẢ NĂM (tiktok, facebook, instagram, youtube, "
        "threads) ở chế độ QUÉT RỘNG-NÔNG — YouTube 50 post (quota 100 search/ngày), "
        "Threads 30 post (chi phí cao). Gọi đích danh nền tảng nào thì nền tảng đó "
        "ĐÀO SÂU theo đúng `limit`. "
        "Viết tắt: 'fb'/'face'/'phây' = facebook, 'ig'/'insta' = instagram, 'tt' = "
        "tiktok, 'yt'/'ytb' = youtube, 'thread' = threads — cứ truyền NGUYÊN VĂN chữ "
        "người dùng dùng vào `platforms`, tool tự hiểu.\n"
        "BẮT BUỘC KHI TRẢ LỜI:\n"
        "- Đọc `per_platform` và `platforms_failed`. Nguồn nào hỏng phải NÓI RÕ nguồn đó "
        "hỏng, TUYỆT ĐỐI KHÔNG trình bày dữ liệu các nguồn còn lại như thể là toàn bộ.\n"
        "- Nói cả hai con số: `scraped` (số post CÀO) và `in_range` (số nằm trong khoảng).\n"
        "- `in_range` NHỎ HƠN `scraped` là BÌNH THƯỜNG — do lọc ngày, KHÔNG phải ghi "
        "sheet thiếu. Sheet luôn chứa ĐỦ toàn bộ post trong khoảng đã qua bộ lọc liên quan "
        "(`ghi_du_khong`=true); bài bị lọc nằm riêng ở `bi_loai_ghi_o`. "
        "TUYỆT ĐỐI không chạy lại tool để 'ghi cho đủ' — chỉ tốn tiền, kết quả y hệt.\n"
        "- Người dùng muốn NHIỀU POST HƠN trong sheet: đọc `goi_y_limit` rồi gọi lại với "
        "`limit` lớn hơn (tối đa `tran_bai`), hoặc nới khoảng ngày. Đừng hứa số post mà nguồn "
        "không có.\n"
        "- Nguồn nào có `chua_phu_het` thì BẮT BUỘC nói ra: khoảng ngày rộng mà chạm trần "
        "`limit` nghĩa là phần CŨ của khoảng CHƯA hề được quét. Đừng để người dùng tưởng "
        "đã phủ trọn khoảng — đề xuất tăng limit hoặc chia nhỏ khoảng ngày.\n"
        "- Chi phí: KHÔNG tự nói ra trong câu trả lời — hệ thống đã tự ghi vào sổ "
        "audit. Chỉ khi người dùng HỎI thì đọc NGUYÊN VĂN `chi_phi` (số Apify THỰC "
        "tính); lượt sau mới hỏi thì gọi `tra_chi_phi_quet`. Không tự tính, không lấy "
        "`uoc_tinh_chi_phi_usd` thay cho số thực.\n"
        "- `limit_bi_cat` có nội dung thì BẮT BUỘC nói ra: người dùng xin nhiều hơn trần.\n"
        "- BÀI BỊ LOẠI: BẮT BUỘC nói con số theo `tom_tat_loai` (không nhắc từ khoá / "
        "chứa từ loại trừ / ngoài thị trường VN / AI loại) và chỉ chỗ xem (`bi_loai_ghi_o`, "
        "thường là tab 'Bị loại' kèm lý do). Đừng để người dùng tưởng brand ít được nhắc "
        "trong khi ta vừa lọc bớt; ai thấy lọc nhầm thì gợi ý `khop_long`/`giu_nuoc_ngoai`.\n"
        "- LỌC AI: CHỈ được nói 'đã lọc bằng AI' khi `loc_bang_ai`=true. "
        "`loc_ai_trang_thai` khác 'đã chạy' (bỏ qua vì hết thời gian / lỗi / chạy một "
        "phần / quá ít bài) thì phải nói rõ AI CHƯA lọc (hoặc mới lọc `loc_ai_da_xet` bài) "
        "nên sheet có thể còn nhiễu.\n"
        "- `cham_tran_chi_phi`=true: có lượt chạy bị dừng giữa chừng, nên nói rõ kết "
        "quả có thể THIẾU và đề xuất giảm số từ khoá hoặc giảm `limit` (không cần nêu "
        "số tiền).\n"
        "- Chất lượng nguồn KHÔNG bằng nhau, phải nhắc khi liên quan: Instagram và "
        "Facebook KHÔNG có followers; Instagram không lọc được quốc gia nên nhiễu quốc "
        "tế; Facebook khớp từ khoá lỏng và gói free chỉ 20 kết quả + 1 lần chạy/24h.\n"
        "- Tool TỐN TIỀN. Xác nhận từ khoá + khoảng ngày + nền tảng TRƯỚC khi gọi.\n"
        "- Gửi NGUYÊN `sheet_url` cho người dùng. `granted`=false thì phải báo họ có thể "
        "mở không được."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "queries": {"type": "array", "items": {"type": "string"},
                        "description": "Từ khoá/hashtag (không cần dấu #). VD [\"hapas\"]."},
            "date_from": {"type": "string", "description": "Ngày bắt đầu 'YYYY-MM-DD' (giờ VN)."},
            "date_to": {"type": "string", "description": "Ngày kết thúc 'YYYY-MM-DD' (giờ VN), bao trọn cả ngày."},
            "platforms": {
                "type": "array", "items": {"type": "string"},
                "description": ("Nền tảng. BỎ TRỐNG = cào cả ba. Nhận viết tắt: fb, face, "
                                "ig, insta, tt. Truyền nguyên văn chữ người dùng dùng."),
            },
            "limit": {"type": "integer", "description": "Số post CÀO tối đa MỖI nền tảng (mặc định 100, tối đa theo trần chủ agent đặt — mặc định 500)."},
            "country": {"type": "string", "description": "Mã ISO, mặc định VN. TikTok và YouTube dùng được."},
            "boi_canh": {
                "type": "string",
                "description": (
                    "NGÀNH HÀNG / bối cảnh của brand, vd 'HAPAS: túi xách, trang sức, "
                    "nước hoa'. LUÔN ĐIỀN nếu bạn biết brand làm gì — kể cả người dùng "
                    "không nói ra, hãy suy từ ngữ cảnh cuộc trò chuyện. Có trường này "
                    "thì hệ thống sẽ nhờ chính model đọc từng bài rồi TỰ loại bài lạc đề "
                    "(tên brand trùng địa danh, trùng hãng khác…), người dùng không phải "
                    "tự nghĩ ra từ khoá loại trừ. Bỏ trống thì AI VẪN lọc nhưng phải tự "
                    "đoán ngành hàng từ chủ đề đa số — kém chính xác hơn, nên điền. AI có "
                    "thể bị bỏ qua khi hết thời gian: xem `loc_ai_trang_thai`. Điền hay "
                    "không thì cổng thị trường VN vẫn chạy (tắt bằng `giu_nuoc_ngoai`)."),
            },
            "khop_long": {
                "type": "boolean",
                "description": (
                    "Mặc định false: bài phải THỰC SỰ nhắc từ khoá (nội dung/hashtag/tên "
                    "kênh/username) mới vào sheet, áp cho MỌI nền tảng. Đặt true CHỈ cho truy "
                    "vấn khám phá chung mà bài không nhất thiết chứa nguyên chữ (vd 'viral', "
                    "'xu hướng', 'outfit đi làm') — khi đó TikTok/Threads không bị kiểm từ "
                    "khoá. Theo dõi brand thì ĐỪNG bật."),
            },
            "giu_nuoc_ngoai": {
                "type": "boolean",
                "description": (
                    "Mặc định false: quét `country`=VN thì loại bài ngoài thị trường VN "
                    "(hệ chữ khác; kênh khai nước khác; hoặc tiêu đề tiếng nước ngoài mà "
                    "không có dấu hiệu tiếng Việt) — vd 'HAPAS THAILAND', ban nhạc metal "
                    "'Hapas Ashen'. Đặt true khi người dùng muốn xem CẢ thị trường nước "
                    "ngoài (brand bán nhiều nước)."),
            },
            "exclude": {
                "type": "array", "items": {"type": "string"},
                "description": (
                    "Từ khoá LOẠI TRỪ — bài nào chứa các từ này thì bỏ. Dùng khi tên brand "
                    "bị TRÙNG NGHĨA với thứ khác (địa danh, hãng khác, từ thông dụng). "
                    "Ví dụ: brand 'hapas' trùng tên một địa danh ở Ấn Độ đang có tin nóng "
                    "và một hãng đàn guitar, nên exclude=['sania','salim','guitars'] sẽ "
                    "cắt sạch. Áp cho MỌI nền tảng. Nếu kết quả trả về có "
                    "`bi_loai_vi_khac_he_chu` cao hoặc "
                    "người dùng kêu nhiễu, HÃY GỢI Ý họ dùng tham số này."),
            },
            "title": {"type": "string", "description": "Tên file sheet. Bỏ trống sẽ tự đặt."},
            "che_do": {
                "type": "string", "enum": ["trend"],
                "description": ("'trend' = trend TikTok đang nổi theo vùng (bảng chính thức "
                                "Creative Center), không cần từ khoá. Bỏ trống = quét "
                                "theo từ khoá như thường (khi đó BẮT BUỘC có `queries`, "
                                "`date_from`, `date_to`)."),
            },
            "ky_ngay": {"type": "string", "enum": ["7", "30"],
                        "description": "Chỉ cho che_do='trend': kỳ xếp hạng, mặc định 7 ngày."},
            "so_hashtag": {"type": "integer",
                           "description": "Chỉ cho che_do='trend': số hashtag (mặc định 20, tối đa 100)."},
            "so_video": {"type": "integer",
                         "description": "Chỉ cho che_do='trend': số top video (mặc định 20, tối đa 100)."},
            "so_video_mau": {"type": "integer",
                             "description": ("Chỉ cho che_do='trend': số video lấy mẫu để "
                                             "tìm âm thanh/hiệu ứng (mặc định 100, tối đa "
                                             "theo trần bài). Người dùng xin 'đủ N bài' thì "
                                             "đặt N ở đây.")},
            "chi_tu_nhien": {"type": "boolean",
                             "description": "Chỉ cho che_do='trend': bỏ video quảng cáo trả tiền (mặc định true)."},
        },
        # Rỗng vì chế độ trend không cần từ khoá/ngày. Chế độ thường vẫn tự kiểm và báo
        # lỗi rõ ràng trong `_handle` khi thiếu.
        "required": [],
    },
}


def _co(v) -> bool:
    """Cờ boolean từ model: chấp nhận true/"true"/"có"/1; mặc định False."""
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "co", "có")
    return bool(v)


def _vi_du(d: dict) -> str:
    return f"{str(d.get('kenh') or '')[:30]}: {' '.join(str(d.get('text') or '').split())[:60]}"


def _ly_do_loai(d: dict, p: str, queries: list[str], loai_tru: list[str], country: str,
                boi_canh: str, khop_long: bool, giu_nuoc_ngoai: bool) -> tuple[str, str]:
    """(nhóm, lý do) nếu bài bị loại, ("", "") nếu giữ. Nhóm dùng để đếm/báo cáo.

    Thứ tự cố định: từ khoá -> loại trừ -> thị trường; bài trúng nhiều luật chỉ
    tính vào luật đầu, để các con số cộng lại đúng bằng số bài bị loại.
    """
    if khop_long:
        # Giữ đúng hành vi cũ cho truy vấn khám phá: chỉ ba nguồn khớp lỏng bị kiểm.
        if p in _NEEDS_RELEVANCE_FILTER and not _relevant(d, queries):
            return "tu_khoa", "không nhắc từ khoá"
    elif not _khop_tu_khoa(d, queries):
        return "tu_khoa", "không nhắc từ khoá"
    tu = _tu_loai_tru_khop(d, loai_tru)
    if tu:
        return "loai_tru", f"chứa từ loại trừ '{tu}'"
    if giu_nuoc_ngoai:
        return "", ""
    if country == "VN":
        # Quét VN: cổng thị trường chạy BẤT KỂ có `boi_canh` (rà 01/10/2026: Mark
        # gần như luôn điền `boi_canh` nên lọc hệ chữ cũ gần như không bao giờ chạy).
        # Bài Thái đúng ngành (#HAPAS #กระเป๋า, 08/09) không mất: nằm ở tab Bị loại,
        # và người dùng muốn thì bật `giu_nuoc_ngoai`.
        if _ngoai_thi_truong(d, country):
            return "he_chu", "ngoài thị trường VN: hệ chữ khác (Thái/Hindi/…)"
        if p in _NEN_TANG_CONG_VN or (
                p == "tiktok" and str(d.get("_nguon") or "").startswith("clockworks")):
            ly_do = _ly_do_ngoai_vn(d, p, queries)
            if ly_do:
                return "thi_truong", ly_do
    elif not boi_canh and p in _NEEDS_RELEVANCE_FILTER and _ngoai_thi_truong(d, country):
        # Nước khác VN: giữ nguyên luật cũ.
        return "he_chu", "hệ chữ khác thị trường đang quét"
    return "", ""


def _handle(args: dict, **kwargs) -> str:
    if str(args.get("che_do") or "").strip().lower() == "trend":
        import tiktok_trend
        return tiktok_trend.chay(args)
    queries = [str(q).strip().lstrip("#") for q in (args.get("queries") or []) if str(q).strip()]
    if not queries:
        return tool_error("Thiếu `queries` (từ khoá/hashtag).")
    try:
        d_from = _parse_date(args.get("date_from", ""), end=False)
        d_to = _parse_date(args.get("date_to", ""), end=True)
    except ValueError as e:
        return tool_error(str(e))
    if d_to < d_from:
        return tool_error("`date_to` phải sau `date_from`.")

    plats, not_yet = normalize_platforms(args.get("platforms"))
    if not plats:
        return tool_error(
            f"Chưa nối nguồn: {', '.join(not_yet) or 'nền tảng bạn nêu'}. "
            f"Hiện chỉ có: TikTok, Facebook, Instagram. Hãy nói THẲNG là chưa hỗ trợ, "
            f"ĐỪNG thay bằng nguồn khác rồi để người dùng tưởng là nguồn họ hỏi."
        )

    try:
        limit = int(args.get("limit") or 100)
    except (TypeError, ValueError):
        limit = 100
    tran_bai, tran_usd = _tran()
    limit_xin = limit
    limit = max(1, min(limit, tran_bai))
    country = (str(args.get("country") or "VN").strip() or "VN").upper()
    ex = args.get("exclude") or []
    loai_tru = [str(x).strip() for x in (ex if isinstance(ex, list) else [ex]) if str(x).strip()]
    boi_canh = str(args.get("boi_canh") or "").strip()[:400]
    khop_long = _co(args.get("khop_long"))
    giu_nuoc_ngoai = _co(args.get("giu_nuoc_ngoai"))
    rng =f"{d_from:%Y-%m-%d} → {d_to:%Y-%m-%d}"

    # Không chỉ định nền tảng = quét RỘNG-NÔNG (giới hạn theo giá từng nguồn).
    # Gọi đích danh = ĐÀO SÂU, dùng nguyên `limit` người dùng đặt.
    explicit = bool(args.get("platforms"))
    per_platform, hits, failed = {}, [], []
    trong_khoang = 0          # số bài nằm trong khoảng ngày, TRƯỚC lọc liên quan
    bi_loai: list[tuple] = []  # (dòng, ngày, lý do) — ghi tab "Bị loại", không vứt
    # Chạy các nền tảng SONG SONG: tuần tự thì tổng thời gian là tổng của tất cả,
    # rất dễ vượt trần trả lời. Nền tảng nào không kịp hạn thì báo LỖI rõ ràng
    # chứ không âm thầm biến mất khỏi kết quả.
    lims = {p: (limit if explicit else min(limit, _SHALLOW.get(p, limit))) for p in plats}
    # Instagram/Facebook chạy MỖI từ khoá một run nên phí khởi động nhân theo số từ khoá.
    so_run = {p: (len(queries) if p in ("instagram", "facebook") else 1) for p in plats}
    est = sum(_START_COST.get(p, 0.0) * so_run[p] + _UNIT_COST.get(p, 0.0) * lims[p]
              for p in plats)
    # Lùi vài giây để đồng hồ máy lệch với Apify không làm sót run đầu tiên.
    _bat_dau = datetime.datetime.now(_VN_TZ) - datetime.timedelta(seconds=5)
    _t0 = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(plats)) as ex:
        futs = {p: ex.submit(_FETCH[p], queries, lims[p], country, d_from, d_to)
                for p in plats}
        results = {}
        for p, f in futs.items():
            con_lai = _TOOL_DEADLINE - (time.monotonic() - _t0)
            try:
                results[p] = f.result(timeout=max(1.0, con_lai))
            except _FutTimeout:
                results[p] = RuntimeError(
                    f"Quá {_TOOL_DEADLINE:.0f}s — nguồn này chưa kịp trả. Thử giảm số từ "
                    f"khoá, giảm `limit`, hoặc quét từng nền tảng một.")
            except Exception as e:  # noqa: BLE001
                results[p] = e

    for p in plats:
        lim_p = lims[p]
        got = results.get(p)
        if isinstance(got, Exception):
            # Che token: chuỗi lỗi đi thẳng vào câu trả lời của model và sổ audit.
            per_platform[p] = {"status": "LỖI",
                               "error": _che_token(f"{type(got).__name__}: {got}")[:250]}
            failed.append(p)
            continue
        keep = [(d, dt) for d, dt in got if dt and d_from <= dt <= d_to]
        trong_khoang += len(keep)
        # Lọc liên quan cho MỌI nền tảng (từ khoá -> loại trừ -> thị trường). Bài
        # bị loại KHÔNG vứt: gom vào `bi_loai` kèm lý do để ghi tab "Bị loại", và
        # đếm + ví dụ để Mark nói ra — loại âm thầm thì người dùng tưởng brand mình
        # không ai nhắc, mà thật ra là ta vừa vứt đi hoặc vừa giữ nhầm.
        nhom: dict[str, list] = {}
        giu = []
        for d, dt in keep:
            d["platform"] = p
            k, ly_do = _ly_do_loai(d, p, queries, loai_tru, country, boi_canh,
                                   khop_long, giu_nuoc_ngoai)
            if k:
                nhom.setdefault(k, []).append(d)
                bi_loai.append((d, dt, ly_do))
            else:
                giu.append((d, dt))
        keep = giu
        hits.extend(keep)
        per_platform[p] = {"status": "OK", "limit": lim_p,
                           "scraped": len(got), "in_range": len(keep)}
        tk = nhom.get("tu_khoa") or []
        if tk:
            per_platform[p].update({
                "loai_vi_khong_chua_tu_khoa": len(tk),
                "vi_du_khong_chua_tu_khoa": [_vi_du(d) for d in tk[:3]]})
        lt = nhom.get("loai_tru") or []
        if lt:
            per_platform[p].update({
                "bi_loai_vi_tu_loai_tru": len(lt),
                "vi_du_tu_loai_tru": [_vi_du(d) for d in lt[:3]]})
        hc = nhom.get("he_chu") or []
        tt_ = hc + (nhom.get("thi_truong") or [])
        if tt_:
            per_platform[p].update({
                "bi_loai_vi_ngoai_thi_truong": len(tt_),
                "vi_du_ngoai_thi_truong": [_vi_du(d) for d in tt_[:3]]})
        if hc:
            per_platform[p].update({
                "bi_loai_vi_khac_he_chu": len(hc),
                "vi_du_bi_loai": [_vi_du(d) for d in hc[:3]],
                "ghi_chu_nhieu": (
                    f"{len(hc)} bài KHỚP từ khoá nhưng viết bằng hệ chữ khác "
                    f"(Hindi/Thái/…) nên đã loại khỏi sheet — từ khoá này bị "
                    f"TRÙNG NGHĨA ở thị trường khác. Nói cho người dùng biết và "
                    f"gợi ý thu hẹp từ khoá (thêm tên ngành, hoặc dùng hashtag "
                    f"riêng của brand)."),
            })
        if p == "tiktok":
            # Nói rõ bài nào đến từ actor dự phòng: nó đắt hơn ~10 lần, và nếu
            # nó phải gánh phần lớn kết quả thì actor chính đang chạm trần —
            # người vận hành cần biết để còn tính chi phí.
            du_phong = sum(1 for d, _ in keep if d.get("_nguon", "").startswith("clockworks"))
            if du_phong:
                per_platform[p].update({
                    "tu_actor_du_phong": du_phong,
                    "ghi_chu_nguon": (
                        f"{du_phong}/{len(keep)} bài lấy từ actor DỰ PHÒNG (clockworks) vì "
                        f"actor chính chạm trần 10 kết quả cho tìm-theo-keyword. Dự phòng "
                        f"đắt hơn ~10 lần ($0,003 vs $0,0003 mỗi video) — chi phí lượt này "
                        f"cao hơn ước tính ban đầu."),
                })
        if p == "youtube":
            per_platform[p].update({
                "nguon": "YouTube Data API v3 chính thức",
                "chi_phi_usd": 0,
                "search_calls_toi_da": (lim_p + 49) // 50,
            })

        # Cảnh báo VÙNG CHƯA PHỦ: nguồn không lọc ngày server-side, đã cào kịch
        # `limit`, mà item CŨ NHẤT vẫn mới hơn `date_from` -> chạm trần trước
        # khi chạm mốc đầu khoảng. Không nói ra thì người dùng tưởng đã quét trọn.
        moc = [dt for _, dt in got if dt]
        so_ngay = (d_to - d_from).days + 1
        if p in _NO_SERVER_DATE and len(got) >= lim_p and so_ngay > 14:
            # Chạm trần `limit` trên khoảng ngày rộng => kết quả chắc chắn chỉ là
            # MẪU. Hai kiểu thiếu, phải phân biệt:
            #  - nguồn sắp theo ngày (apidojo): cắt cụt ở đầu CŨ -> có
            #    thể chỉ ra đoạn ngày nào chưa đụng tới.
            #  - nguồn không sắp theo ngày (clockworks hashtag): item rải rác cả
            #    khoảng nên không cắt cụt, nhưng THƯA — cũng không phải toàn bộ.
            cu_nhat = min(moc) if moc else None
            if cu_nhat and cu_nhat > d_from + datetime.timedelta(days=1):
                per_platform[p]["chua_phu_het"] = (
                    f"CHẠM TRẦN {lim_p} post trên khoảng {so_ngay} ngày. CHỈ phủ được "
                    f"{cu_nhat:%Y-%m-%d} → {d_to:%Y-%m-%d}; đoạn {d_from:%Y-%m-%d} → "
                    f"{cu_nhat:%Y-%m-%d} CHƯA hề được quét. PHẢI nói rõ. Muốn đủ thì "
                    f"tăng `limit` hoặc chia nhỏ khoảng ngày."
                )
            else:
                per_platform[p]["chua_phu_het"] = (
                    f"CHẠM TRẦN {lim_p} post trên khoảng {so_ngay} ngày, nên đây là MẪU "
                    f"chứ KHÔNG phải toàn bộ bài trong khoảng. PHẢI nói rõ là mẫu; "
                    f"đừng đưa ra kết luận kiểu 'chỉ có N bài trong {so_ngay} ngày'. "
                    f"Muốn đầy đủ hơn thì tăng `limit` hoặc chia nhỏ khoảng ngày."
                )
        if not got:
            # Cào 0 item KHÔNG đồng nghĩa "không có bài nào". Actor Facebook gói
            # free chỉ cho 1 lần chạy / 24h và khi hết hạn mức nó vẫn trả về
            # SUCCEEDED với dataset rỗng — nhìn y hệt "không có kết quả".
            # Không nêu rõ chỗ này thì người dùng sẽ kết luận sai về thị trường.
            if p == "youtube":
                per_platform[p]["canh_bao"] = (
                    "YouTube Data API trả 0 video. KHÔNG chắc thị trường không có bài — "
                    "có thể truy vấn/khoảng ngày/quốc gia quá hẹp. Nói rõ sự mơ hồ này."
                )
            else:
                per_platform[p]["canh_bao"] = (
                    "Cào được 0 item. KHÔNG chắc là không có bài — có thể đã hết hạn mức "
                    "(Facebook gói free: 20 kết quả và 1 LẦN CHẠY / 24 GIỜ) hoặc actor bị "
                    "chặn. PHẢI nói rõ sự mơ hồ này, đừng kết luận là nguồn này không có gì."
                )

    scraped = sum(v.get("scraped", 0) for v in per_platform.values())

    # LỌC BẰNG AI — chạy MỘT LẦN trên toàn bộ kết quả đã gộp, sau mọi bộ lọc rẻ
    # tiền (ngày, từ khoá, hệ chữ, exclude). Đặt ở đây chứ không trong vòng lặp
    # từng nền tảng: một lượt gọi model cho cả lượt quét, vì quota Codex dùng
    # chung với meeting agent.
    ai_log: list[str] = []
    ai_tt: dict = {"trang_thai": "bỏ qua vì quá ít bài", "da_xet": 0}
    bo_ai = _loc_bang_ai(hits, queries, boi_canh, ai_log,
                         con_lai=_TOOL_DEADLINE - (time.monotonic() - _t0),
                         trang_thai=ai_tt, da_khop_tu_khoa=not khop_long)
    vi_du_ai: list[str] = []
    if bo_ai:
        vi_du_ai = [f"[{hits[i][0].get('platform')}] "
                    f"{str(hits[i][0].get('text') or '')[:70]}" for i in sorted(bo_ai)[:4]]
        bi_loai.extend((d, dt, "AI: lạc đề so với brand/ngành hàng")
                       for i, (d, dt) in enumerate(hits) if i in bo_ai)
        hits = [x for i, x in enumerate(hits) if i not in bo_ai]
    loc_bang_ai = ai_tt.get("trang_thai") in ("đã chạy", "chạy một phần")

    hits.sort(key=lambda x: (x[0]["views"], x[0]["likes"]), reverse=True)

    # Gợi ý limit: tỉ lệ post lọt khoảng thường thấp (lọc ngày), nên muốn N post
    # trong sheet thì phải cào N/tỉ_lệ. Tính sẵn để model khỏi đoán mò.
    ty_le = (len(hits) / scraped) if scraped else 0.0
    goi_y = None
    if 0 < ty_le < 0.9:
        goi_y = (f"Chỉ {ty_le:.0%} post cào được nằm trong khoảng ngày và qua bộ lọc liên "
                 f"quan. Muốn khoảng N "
                 f"post trong sheet thì đặt limit ≈ N/{ty_le:.2f} (vd muốn 50 post → "
                 f"limit ≈ {min(tran_bai, max(1, int(50 / ty_le)))}). Trần limit là {tran_bai}.")

    actors = [_ACTORS[p] for p in plats if p in _ACTORS]
    if "tiktok" in plats:
        actors.append(_ACTORS["tiktok_fallback"])
    thuc = _chi_phi_thuc(actors, _bat_dau, est) if actors else {
        "usd": 0.0, "so_run": 0, "cham_tran": 0, "dang_chay": 0}
    # "Tiêu ≥95% trần" chỉ là dấu hiệu, không phải bằng chứng bị cắt: đặt trần 2,4 USD
    # cho 800 bài TikTok (800 × 0,003) thì lấy ĐỦ 800 bài cũng tiêu đúng 2,4 USD. Đo thật
    # 25/09/2026: Mark báo "chạm trần, có thể thiếu" cho một lượt đã lấy đủ 800/800.
    # Nguồn Apify nào cũng đã cào đủ `limit` thì không có gì bị cắt.
    if thuc and thuc.get("cham_tran") and all(
            (per_platform.get(p) or {}).get("scraped", 0) >= lims[p]
            for p in plats if p in _ACTORS):
        thuc = {**thuc, "cham_tran": 0}
    chi_phi_tool.ghi(queries=queries, platforms=plats, date_range=rng, thuc=thuc, est=est)

    # Tổng kết bài bị loại thành MỘT câu cho model chép — trường rải rác trong
    # `per_platform` thì model hay bỏ sót (rà 01/10/2026: sheet đầy nhiễu mà Mark
    # không nói đã/không lọc gì).
    dem_loai = {"tu_khoa": 0, "loai_tru": 0, "thi_truong": 0, "ai": len(bo_ai)}
    for v in per_platform.values():
        dem_loai["tu_khoa"] += v.get("loai_vi_khong_chua_tu_khoa", 0)
        dem_loai["loai_tru"] += v.get("bi_loai_vi_tu_loai_tru", 0)
        dem_loai["thi_truong"] += v.get("bi_loai_vi_ngoai_thi_truong", 0)

    def _tom_tat(noi: str) -> str:
        if not bi_loai:
            return (f"Không bài nào bị bộ lọc liên quan loại ({trong_khoang} bài trong "
                    f"khoảng ngày đều giữ).")
        phan = [f"Đã loại {dem_loai['tu_khoa']}/{trong_khoang} bài không nhắc từ khoá"]
        if dem_loai["loai_tru"]:
            phan.append(f"{dem_loai['loai_tru']} bài chứa từ loại trừ")
        if dem_loai["thi_truong"]:
            phan.append(f"{dem_loai['thi_truong']} bài ngoài thị trường {country}")
        if dem_loai["ai"]:
            phan.append(f"{dem_loai['ai']} bài AI đánh giá lạc đề")
        return "; ".join(phan) + (f" (xem {noi})." if noi else ".")

    base = dict(queries=queries, date_range=rng, platforms=plats,
                ty_le_trong_khoang=round(ty_le, 3), goi_y_limit=goi_y,
                che_do="đào sâu (gọi đích danh)" if explicit else "quét rộng-nông (mặc định)",
                uoc_tinh_chi_phi_usd=round(est, 3),
                tran_bai=tran_bai, tran_chi_phi_usd_moi_luot=tran_usd,
                limit_bi_cat=(f"Người dùng xin {limit_xin} bài, trần hiện tại là {tran_bai} "
                              f"bài mỗi nền tảng. Chủ agent nâng được ở console: Năng lực → "
                              f"Quét mạng xã hội.") if limit_xin > tran_bai else None,
                chi_phi_thuc_usd=thuc["usd"] if thuc else None,
                cham_tran_chi_phi=bool(thuc and thuc["cham_tran"]),
                chi_phi=_dong_chi_phi(thuc, est),
                per_platform=per_platform, platforms_failed=failed,
                platforms_not_supported=not_yet, scraped=scraped, in_range=len(hits),
                trong_khoang_ngay=trong_khoang, tong_bi_loai=len(bi_loai),
                khop_long=khop_long, giu_nuoc_ngoai=giu_nuoc_ngoai,
                # Lọc bằng AI: báo ĐÚNG chuyện đã xảy ra. Trước 01/10/2026 trường này
                # là True cứng kể cả khi bộ lọc chưa chạy dòng nào vì hết giờ.
                loc_bang_ai=loc_bang_ai,
                loc_ai_trang_thai=ai_tt.get("trang_thai"),
                loc_ai_da_xet=ai_tt.get("da_xet", 0))

    if not hits and not bi_loai:
        return tool_result(
            success=not failed, sheet_url=None, **base,
            tom_tat_loai=_tom_tat(""),
            note=(f"Cào {scraped} post, KHÔNG post nào nằm trong {rng}. Không tạo sheet."
                  + (f" LƯU Ý: nguồn hỏng: {', '.join(failed)} — phải báo người dùng."
                     if failed else "")),
        )

    title = (args.get("title") or "").strip() or \
        f"Social · {', '.join(queries)[:30]} · {d_from:%d-%m}→{d_to:%d-%m}"
    kw = ", ".join(queries)

    def _dong(d: dict, dt) -> list:
        return [d["platform"], dt.strftime("%Y-%m-%d %H:%M"), d["kenh"], d["followers"],
                d["views"], d["likes"], d["comments"], d["shares"], d["hashtags"],
                d["text"], d["link"], kw]

    rows = [list(_HEADER)] + [_dong(d, dt) for d, dt in hits]
    # Bài bị loại vẫn có sheet để kiểm (kể cả khi KHÔNG bài nào được giữ): bộ lọc
    # loại nhầm mà không ai thấy được thì không bao giờ sửa được.
    rows_loai = [list(_HEADER) + ["Lý do loại"]] + [
        _dong(d, dt) + [ly_do] for d, dt, ly_do in bi_loai]

    try:
        tok, url = _create_sheet(title)
        sid = _first_sheet_id(tok)
        _write_values(tok, sid, rows)
    except Exception as e:  # noqa: BLE001
        return tool_result(
            success=False, sheet_url=None, **base,
            tom_tat_loai=_tom_tat(""),
            error=_che_token(f"Cào OK ({len(hits)} post trong khoảng) nhưng TẠO/GHI SHEET "
                             f"THẤT BẠI: {type(e).__name__}: {e}"),
            top=[{"nen_tang": d["platform"], "kenh": d["kenh"], "views": d["views"],
                  "link": d["link"]} for d, _ in hits[:5]],
        )
    bi_loai_ghi_o = None
    if bi_loai:
        try:
            bi_loai_ghi_o = _ghi_bi_loai(tok, sid, len(rows), rows_loai)
        except Exception as e:  # noqa: BLE001
            bi_loai_ghi_o = (f"KHÔNG ghi được ({type(e).__name__}) — chỉ còn ví dụ trong "
                             f"per_platform")

    sender = memory_store.get_current_sender()
    granted = _grant(tok, sender) if sender else False

    return tool_result(
        success=True, title=title, sheet_url=url, granted=granted, **base,
        top=_top_per_platform(hits, 3),
        tom_tat_loai=_tom_tat(bi_loai_ghi_o or ""),
        bi_loai_ghi_o=bi_loai_ghi_o,
        # Các trường DƯỚI ĐÂY cố tình tách bạch và đặt tên dài, vì bản trước ghi
        # gọn "Đã ghi 7/100 post vào sheet" và model đọc thành "sheet mới ghi
        # được 7 trong 100" — tưởng GHI HỎNG, rồi chạy lại 3 lần + xuất CSV để
        # chữa một lỗi không hề tồn tại. Con số tụt là do LỌC NGÀY, không phải
        # ghi thiếu; phải nói thẳng ra chứ đừng để suy diễn.
        da_ghi_vao_sheet=len(hits),
        bi_loai_vi_ngoai_khoang_ngay=scraped - trong_khoang,
        ghi_du_khong=True,
        bi_loai_boi_ai=len(bo_ai),
        vi_du_ai_da_loai=vi_du_ai,
        ai_ghi_chu=("; ".join(ai_log) if ai_log else
                    (f"AI đã đọc bối cảnh '{boi_canh or 'tự đoán chủ đề đa số'}' và loại "
                     f"{len(bo_ai)} bài lạc đề. Nói cho người dùng biết con số này."
                     if bo_ai else
                     "AI đã kiểm nhưng không thấy bài nào lạc đề." if loc_bang_ai else
                     f"AI CHƯA lọc ({ai_tt.get('trang_thai')}).")),
        note=(f"GHI ĐỦ, KHÔNG thiếu dòng nào: sheet '{title}' có đúng {len(hits)} post "
              f"— là TẤT CẢ post nằm trong {rng} đã qua bộ lọc liên quan. "
              f"Đã cào {scraped} post, {scraped - trong_khoang} post nằm NGOÀI khoảng ngày "
              f"nên bị lọc bỏ (đây là hành vi ĐÚNG của bộ lọc ngày, KHÔNG phải lỗi ghi "
              f"sheet — đừng chạy lại)"
              + (f"; {len(bi_loai)} post trong khoảng bị bộ lọc liên quan loại, ghi ở "
                 f"{bi_loai_ghi_o} kèm lý do" if bi_loai else "")
              + ". Muốn nhiều post trong khoảng hơn thì tăng "
              f"`limit` hoặc nới khoảng ngày. GỬI `sheet_url`."
              + (f" CẢNH BÁO: nguồn HỎNG: {', '.join(failed)} — dữ liệu KHÔNG đầy đủ, "
                 f"phải nói rõ với người dùng." if failed else "")
              + ("" if granted else " CẢNH BÁO: chưa cấp được quyền tự động.")),
    )


def _available() -> bool:
    return bool(
        os.environ.get("APIFY_TOKEN", "").strip()
        or os.environ.get("YOUTUBE_DATA_API_KEY", "").strip()
    )


def register() -> None:
    try:
        registry.register(
            name="social_listen", toolset=_TOOLSET, schema=SCHEMA, handler=_handle,
            check_fn=_available, requires_env=[], is_async=False,
            description=("Cào TikTok/Facebook/Instagram/YouTube/Threads theo keyword "
                         "+ khoảng ngày, gộp vào Lark Sheet"),
            emoji="\U0001f4e1", override=True,
        )
    except Exception as e:
        print(f"[apify_tool] register warning: {e}")


register()
