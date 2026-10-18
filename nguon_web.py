"""Lắng nghe WEB (báo, diễn đàn, blog) cho một dự án — bản mẫu ĐỘC LẬP, chưa nối vào /theodoi.

Vì sao làm theo cách này (đo thật 16/10/2026, chi tiết + số liệu ở `docs/lang-nghe-web.md`):
  • KHÁM PHÁ bằng máy tìm kiếm có lọc ngày, không cào rộng. Đọc RSS/sitemap của báo phải tải
    HÀNG NGHÌN bài mỗi ngày để gặp 0–1 bài nhắc brand (sitemap tin của cafef/kenh14/cafebiz:
    50 bài mới nhất, 0 bài có chữ "hapas"); tìm nội bộ của báo thì robots.txt cấm
    (tuoitre/thanhnien/znews chặn /tim-kiem). Google đã đánh chỉ mục sẵn nên ta chỉ thuê kết
    quả: actor `scraperlink~google-search-results-serp-scraper` (0,0005 USD/trang 10 link,
    nhận `tbs` lọc ngày + gl/hl). Lượt đo "hapas" trong 30 ngày: 22 link, ~11 link đúng brand
    (cafebiz bài TVC 20/10 gây tranh cãi, adsoftheworld, campaignbriefasia, vincom, cafef...).
    Actor chính chủ `apify~google-search-scraper` tốt hơn về độ ổn định nhưng ĐÒI trần tối
    thiểu 0,5 USD/lượt (`minimalMaxTotalChargeUsd`) — để làm dự phòng, xem tài liệu.
  • ĐỌC BÀI bằng HTTP thường + bóc HTML bằng thư viện chuẩn (không cần gói mới trong venv
    Hermes): 8/9 trang báo/diễn đàn đọc được, ngày đăng có sẵn ở JSON-LD/meta. Trang chặn
    (daibieunhandan 403) đọc lại qua `apify~website-content-crawler` (~0,009 USD/trang; chủ dự án
    16/10 BẬT, ≤ `BOC_MAC_DINH` trang mỗi lượt, trong phần ngân sách còn lại, robots vẫn tôn
    trọng); vẫn không được thì giữ đoạn trích của Google.
  • CHỈ GIỮ bài THỰC SỰ nhắc từ khoá trong tiêu đề/thân bài (cùng luật `_khop_tu_khoa` của
    mọi nền tảng) — Google trả cả "Hapa's Brewing", tàu "KOTA HAPAS", đàn Hapas — rồi bước AI
    phân xử sẵn có của Mark quyết giữ/loại + gán sắc thái/chủ đề.
  • KHÔNG lấy lại mạng xã hội (Facebook/TikTok/IG/YouTube/Threads đã có actor riêng — lấy lại
    qua Google thì đếm hai lần) và không lấy trang của chính brand (kênh nhà, không phải lắng
    nghe) hay trang sản phẩm sàn TMĐT (đánh giá sàn đi đường riêng, xem tài liệu).

Ghi kho: bài web vào bảng `bai` với `nen_tang = 'web'`, khoá `web:<sha1 16 ký tự của URL
chuẩn>`, `tai_khoan` = tên miền (dashboard đếm "nguồn có bài" theo miền), số xem/thích/chia sẻ
= NULL (web không có), `binh_luan` = số trả lời nếu trang công bố (diễn đàn). Mẫu "hit" trả về
đúng dạng `(d, dt)` mà `theo_doi._giu_tu_khoa` nhận, nên tích hợp chỉ là gọi hàm này.

Kỷ luật: không in/ghi token (actor chạy qua `apify_tool._run_actor`, token do module đó đọc);
mỗi lượt có trần USD; tôn trọng robots.txt, tự xưng User-Agent, nghỉ giữa hai lần tải cùng
miền; chặn URL trỏ vào mạng nội bộ (SSRF); chỉ lưu tiêu đề + đoạn quanh chỗ nhắc (≤1000 ký
tự), không lưu toàn văn bài báo.
"""
from __future__ import annotations

import datetime
import hashlib
import ipaddress
import json
import math
import re
import socket
import time
import unicodedata
import urllib.parse
import urllib.robotparser
from html.parser import HTMLParser

NEN_TANG = "web"
_VN = datetime.timezone(datetime.timedelta(hours=7))

# ───────────────────────────── giá + trần (đo 16/10/2026, gói FREE) ─────────────────────────────
#: Actor tìm Google: 1 item dataset = 1 trang kết quả (≤10 link), 0,0005 USD/item, không phí
#: khởi động. Đo: 6 trang -> 0,003 USD; 3 trang -> 0,0015 USD (đúng giá).
ACTOR_TIM = "scraperlink~google-search-results-serp-scraper"
GIA_TRANG = 0.0005
KHOI_DONG = 0.0
#: Dự phòng đọc trang bị chặn (403, lỗi mạng): đo 0,0174 USD / 2 trang (playwright, 4 GB).
ACTOR_BOC = "apify~website-content-crawler"
GIA_BOC = 0.009
HE_SO_UOC = 1.3            # như `theo_doi._HE_SO_UOC`
HE_SO_TRAN = 1.5           # như `theo_doi._HE_SO_TRAN`
TRAN_TOI_THIEU = 0.1       # `apify_tool._run_actor` kẹp trần ≥ 0,1 USD

TRANG_MAC_DINH = 2         # 2 trang = 20 link mỗi câu tìm
KQ_MOI_TRANG = 10
TU_MOI_CAU = 4             # từ khoá gộp OR trong một câu tìm
TOI_DA_TRUY_VAN = 4
BOC_MAC_DINH = 10          # trang tối đa đọc qua actor dự phòng mỗi lượt (chủ dự án 16/10: BẬT)
#: Actor dự phòng tính theo TÀI NGUYÊN (không phải theo sự kiện) nên `maxTotalChargeUsd` không
#: chặn được: chặn bằng THỜI GIAN chạy (4 GB). Đo 16/10: 69 giây = 0,0174 USD -> 0,00026 USD/s.
BOC_BO_NHO = 4096
BOC_USD_MOI_GIAY = 0.00026
BOC_GIAY_TOI_THIEU = 90
BOC_HE_SO_AN_TOAN = 1.5
#: Trang đã thử đọc qua actor dự phòng: không thử lại trong chừng này ngày (review 16/10 — trang
#: bị loại vì không ngày / quá cũ / đọc hỏng không vào sổ "đã loại", sẽ bị đọc trả tiền mỗi lượt).
BOC_NHO_NGAY = 14
TOI_DA_TU_GOOGLE = 32      # Google bỏ qua từ thứ 33 trở đi của câu tìm
TOI_DA_TAI = 60            # trang tải mỗi lượt
NGAY_GIU = 35              # như `theo_doi.NGAY_GIU`
CHU_TOI_DA = 1000          # `bai.noi_dung` của Mark cắt 1000 ký tự
_GIOI_HAN_SCRAPERLINK = (10, 20, 30, 40, 50, 100)

UA = "Mozilla/5.0 (compatible; HapasListeningBot/0.1; +https://social.hapas.vn)"
UA_ROBOTS = "HapasListeningBot"
BYTE_TOI_DA = 3_000_000
GIAY_KET_NOI, GIAY_DOC = 5, 15
GIAY_TRANG_TOI_DA = 25     # đồng hồ tối đa cho MỘT trang (cả chuyển hướng + đọc thân)
NGHI_MOI_MIEN = 1.5        # giây giữa hai lần tải cùng một miền
_CHUA_GIAY = 10.0          # còn ít hơn thì thôi tải trang, dùng đoạn trích Google

# ───────────────────────────── phân loại miền ─────────────────────────────
#: Mạng xã hội Mark đã có actor riêng — lấy lại qua Google là đếm hai lần.
MIEN_MXH = ("facebook.com", "fb.com", "tiktok.com", "instagram.com", "youtube.com",
            "youtu.be", "threads.net", "threads.com")
#: Sàn TMĐT — đánh giá sản phẩm đi đường riêng (API người bán), không coi là bài web.
MIEN_TMDT = ("shopee.vn", "lazada.vn", "tiki.vn", "sendo.vn", "shopee.com", "lazada.com")
MIEN_BAO = (
    "vnexpress.net", "tuoitre.vn", "thanhnien.vn", "dantri.com.vn", "znews.vn", "zingnews.vn",
    "kenh14.vn", "cafef.vn", "cafebiz.vn", "vietnamnet.vn", "vtv.vn", "vov.vn", "laodong.vn",
    "nld.com.vn", "tienphong.vn", "baomoi.com", "soha.vn", "afamily.vn", "eva.vn", "24h.com.vn",
    "ngoisao.vn", "daibieunhandan.vn", "vneconomy.vn", "theleader.vn", "nhipcaudautu.vn",
    "vietnamplus.vn", "plo.vn", "doanhnhansaigon.vn", "elle.vn", "harpersbazaar.com.vn",
    "brandsvietnam.com", "advertisingvietnam.com", "marketingai.vn", "campaignbriefasia.com",
    "marketech-apac.com", "adsoftheworld.com", "musebyclios.com", "campaignasia.com")
MIEN_DIEN_DAN = ("voz.vn", "tinhte.vn", "otofun.net", "webtretho.com", "lamchame.com",
                 "reddit.com", "quora.com")
MIEN_MXH_KHAC = ("linkedin.com", "x.com", "twitter.com", "lemon8-app.com", "pinterest.com")
#: Trang TUYỂN DỤNG / hồ sơ cá nhân — không phải tiếng nói về brand (16/10/2026: hồ sơ LinkedIn
#: "Talent Acquisition Intern HAPAS" và tin tuyển dụng lọt vào Báo & Web). Luật URL thuần, chắc
#: chắn: sàn việc làm theo miền; LinkedIn theo đường dẫn (hồ sơ /in/, việc /jobs/, trang việc của
#: công ty). Bài đăng LinkedIn (/posts/, /pulse/) vẫn giữ — đó là bài viết công khai.
MIEN_VIEC_LAM = ("topcv.vn", "vietnamworks.com", "careerviet.vn", "careerlink.vn", "itviec.com",
                 "joboko.com", "timviec365.vn", "vieclam24h.vn", "jobstreet.vn", "jobstreet.com",
                 "glints.com", "indeed.com", "glassdoor.com", "1900.com.vn", "jobsgo.vn",
                 "mywork.com.vn", "jobokovn.com", "careerbuilder.vn", "tuyendung.vn")
_DUONG_VIEC_LINKEDIN = re.compile(r"^/(in|jobs|talent|school)(/|$)|^/company/[^/]+/(jobs|life|people)(/|$)",
                                  re.IGNORECASE)
_DUOI_TEP = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".zip")
_THAM_SO_BO = re.compile(r"^(utm_\w+|srsltid|fbclid|gclid|gad_source|gbraid|wbraid|_gl|mc_cid|"
                         r"mc_eid|igshid|zarsrc|ref|refer|source|si)$", re.IGNORECASE)
_DUONG_DIEN_DAN = re.compile(r"/(threads?|t|topic|f|forums?|dien-dan|showthread)[/.]", re.IGNORECASE)


# ───────────────────────────── URL ─────────────────────────────
def _tach(url) -> urllib.parse.SplitResult | None:
    """`urlsplit` không ném: URL hỏng ("http://[x", ký tự lạ) -> None (review 16/10: một link
    hỏng từ Google không được làm vỡ cả lượt)."""
    try:
        p = urllib.parse.urlsplit(str(url or "").strip())
        p.hostname  # noqa: B018 — ép kiểm phần máy chủ (IPv6 hỏng ném ở đây)
        return p
    except ValueError:
        return None


def mien(url: str) -> str:
    """Tên miền chuẩn: chữ thường, bỏ www./m./amp. ở đầu. URL hỏng -> ""."""
    p = _tach(url)
    h = ((p.hostname if p else "") or "").lower().rstrip(".")
    return re.sub(r"^(www\d?|m|amp|mobile)\.", "", h)


def _thuoc(m: str, ds) -> bool:
    return any(m == d or m.endswith("." + d) for d in ds)


def url_chuan(url: str) -> str:
    """URL chuẩn để chống trùng: https, miền chuẩn, bỏ tham số theo dõi/fragment, bỏ '/' cuối.
    m.cafef.vn/x?utm_source=a và https://cafef.vn/x/ là MỘT bài."""
    p = _tach(url)
    if p is None or p.scheme not in ("http", "https") or not p.hostname:
        return ""
    q = sorted((k, v) for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
               if not _THAM_SO_BO.match(k))
    duong = re.sub(r"/amp/?$", "", p.path or "/") or "/"
    if len(duong) > 1:
        duong = duong.rstrip("/")
    return urllib.parse.urlunsplit(("https", mien(url), duong, urllib.parse.urlencode(q), ""))


def ma_web(url: str) -> str:
    return hashlib.sha1(url_chuan(url).encode("utf-8")).hexdigest()[:16]


def khoa_web(url: str) -> str:
    """Khoá bài trong kho: "web:<16 hex>" — cùng dạng "<nền tảng>:<id>" của Mark."""
    return f"{NEN_TANG}:{ma_web(url)}"


def kieu_trang(url: str, kieu_ld: str = "") -> str:
    """'bao' | 'dien_dan' | 'blog' | 'mxh_khac' | 'khac' — để dashboard tách Báo / Diễn đàn."""
    m = mien(url)
    if _thuoc(m, MIEN_BAO):
        return "bao"
    p = _tach(url)
    if _thuoc(m, MIEN_DIEN_DAN) or kieu_ld == "DiscussionForumPosting" \
            or _DUONG_DIEN_DAN.search((p.path if p else "") + "/"):
        return "dien_dan"
    if _thuoc(m, MIEN_MXH_KHAC):
        return "mxh_khac"
    if kieu_ld in ("NewsArticle", "ReportageNewsArticle", "AnalysisNewsArticle"):
        return "bao"
    if kieu_ld == "BlogPosting":
        return "blog"
    return "khac"


def mien_nha(du_an: dict) -> list[str]:
    """Miền của chính brand (bỏ qua — là kênh nhà): `cau_hinh.web.mien_nha` + từ khoá có dạng
    tên miền ("hapas.vn")."""
    cfg = ((du_an.get("cau_hinh") or {}).get("web") or {}).get("mien_nha") or []
    tu = [str(t).strip().lower() for t in du_an.get("tu_khoa") or []]
    ra = [mien("https://" + x.split("://")[-1]) for x in [*cfg, *tu]
          if re.fullmatch(r"(https?://)?[a-z0-9-]+(\.[a-z0-9-]+)+/?", str(x).strip().lower())]
    return sorted({x for x in ra if x})


def _ly_do_bo_url(url: str, nha: list[str]) -> str:
    m = mien(url)
    if not m:
        return "url_hong"
    if _thuoc(m, MIEN_MXH):
        return "mxh"
    if _thuoc(m, MIEN_TMDT):
        return "tmdt"
    if _thuoc(m, nha):
        return "nha"
    if _thuoc(m, MIEN_VIEC_LAM) or (_thuoc(m, ("linkedin.com",))
                                    and _DUONG_VIEC_LINKEDIN.search(_tach(url).path or "/")):
        return "tuyen_dung"
    if not url_chuan(url):
        return "url_hong"
    if (_tach(url).path or "").lower().endswith(_DUOI_TEP):
        return "tep"
    return ""


# ───────────────────────────── câu tìm ─────────────────────────────
def _bo_dau(s: str) -> str:
    """Bỏ dấu + thường hoá, GIỮ NGUYÊN độ dài (mỗi ký tự -> một ký tự) để vị trí khớp trên bản
    bỏ dấu dùng được để cắt đoạn trên bản gốc."""
    ra = []
    for c in s or "":
        if c in "đĐ":
            ra.append("d")
            continue
        g = unicodedata.normalize("NFD", c)
        ra.append((g[0] if g and unicodedata.category(g[0]) != "Mn" else c).lower()[:1] or c)
    return "".join(ra)


def _tu(s: str) -> list[str]:
    return re.findall(r"[^\W_]+", _bo_dau(s))


def rut_gon_tu_khoa(tu_khoa: list[str]) -> list[str]:
    """Bỏ từ khoá đã được từ khoá khác phủ: có "hapas" thì "túi hapas", "ví hapas",
    "hapas.vn" thừa (Google tìm "hapas" đã ra các trang đó) — đỡ tiền một câu tìm mỗi lượt."""
    sach = []
    for t in tu_khoa or []:
        t = str(t).strip()
        if t and _tu(t) and t.lower() not in (x.lower() for x in sach):
            sach.append(t)
    ra = []
    for t in sach:
        ti = set(_tu(t))
        if not any(x is not t and set(_tu(x)) < ti for x in sach):
            ra.append(t)
    return ra


def _vi_cau(t: str) -> str:
    t = re.sub(r"\s+", " ", t.replace('"', " ")).strip()
    if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", t.lower()):
        return t                              # tên miền: Google hiểu nguyên khối
    return f'"{t}"' if " " in t else t


def so_cau_tim(tu_khoa: list[str]) -> int:
    """Số câu tìm của một lượt: ⌈từ khoá đã rút gọn / `TU_MOI_CAU`⌉, tối đa `TOI_DA_TRUY_VAN`.
    Công thức ƯỚC TÍNH (dashboard chép y hệt — `dashboard/chi_phi.py`, `ngan_sach.js`); câu
    tìm thật (`cau_truy_van`) không bao giờ nhiều hơn (chỉ có thể bớt từ là miền nhà)."""
    n = len(rut_gon_tu_khoa(tu_khoa))
    return min(TOI_DA_TRUY_VAN, math.ceil(n / TU_MOI_CAU)) if n else 0


def cau_truy_van(du_an: dict, them_tu: list[str] | None = None,
                 toi_da: int = TOI_DA_TRUY_VAN) -> list[str]:
    """Từ khoá dự án (+ `them_tu`: khẩu hiệu của chiến dịch đang chạy) -> ≤ `toi_da` câu tìm
    Google, mỗi câu gộp OR ≤ `TU_MOI_CAU` từ; loại MXH/sàn/miền nhà bằng -site:, thêm
    -"từ loại trừ" khi còn chỗ trong trần 32 từ (luật cứng vẫn kiểm lại sau khi đọc bài)."""
    goc = [str(x) for x in du_an.get("tu_khoa") or []] or [du_an.get("ten", "")]
    tu = rut_gon_tu_khoa([*goc, *(them_tu or [])])
    nha = mien_nha(du_an)
    tu = [t for t in tu if mien("https://" + t.lower()) not in nha] or tu
    loai = [f"-site:{d}" for d in (*MIEN_MXH, *MIEN_TMDT[:3], *nha)]
    # Từ loại trừ ngắn / nằm trong từ khoá ("hapa" ⊂ "hapas") KHÔNG đưa lên Google: toán tử "-"
    # của Google khớp cả biến thể từ, có thể loại luôn trang nhắc brand. Luật cứng (khớp nguyên
    # từ, `apify_tool._tu_loai_tru_khop`) vẫn chạy sau khi đọc bài.
    nk = [_bo_dau(t) for t in tu]
    tru = [f"-{_vi_cau(x)}" for x in du_an.get("tu_loai_tru") or [] if _tu(str(x))
           and len(_bo_dau(str(x)).strip()) > 4
           and not any(_bo_dau(str(x)).strip() in k for k in nk)]

    def so_tu(xs: list[str]) -> int:
        return sum(len(x.split()) for x in xs)
    ra = []
    for i in range(0, min(len(tu), toi_da * TU_MOI_CAU), TU_MOI_CAU):
        nhom = [_vi_cau(t) for t in tu[i:i + TU_MOI_CAU]]
        dau = nhom[0] if len(nhom) == 1 else "(" + " OR ".join(nhom) + ")"
        q = [dau]
        for x in [*loai, *tru]:              # từ khoá trước; Google bỏ phần quá 32 từ
            if so_tu(q) + len(x.split()) > TOI_DA_TU_GOOGLE:
                break
            q.append(x)
        ra.append(" ".join(q))
    return ra


def tbs_cua_so(tu: datetime.date, den: datetime.date) -> str:
    """Khoảng ngày tuỳ ý của Google (`tbs=cdr:1,...`, tháng/ngày/năm)."""
    def f(d: datetime.date) -> str:
        return f"{d.month}/{d.day}/{d.year}"
    return f"cdr:1,cd_min:{f(tu)},cd_max:{f(den)}"


def payload_tim(truy_van: list[str], tu: datetime.date, den: datetime.date,
                so_trang: int = TRANG_MAC_DINH, thi_truong: str = "VN") -> dict:
    """Input của `ACTOR_TIM`. Không đặt `lr` (ngôn ngữ): báo quảng cáo quốc tế viết tiếng Anh về
    chiến dịch của brand (campaignbriefasia, adsoftheworld) — đo 16/10 là nhóm có giá trị."""
    can = max(1, so_trang) * 10
    gioi_han = next((x for x in _GIOI_HAN_SCRAPERLINK if x >= can), 100)
    return {"keyword": "\n".join(truy_van), "limit": str(gioi_han),
            "country": (thi_truong or "VN").upper(),
            "hl": "vi" if (thi_truong or "VN").upper() == "VN" else "en",
            "tbs": tbs_cua_so(tu, den), "include_merged": False}


def uoc_luot(so_truy_van: int, so_trang: int = TRANG_MAC_DINH, so_boc: int = 0) -> float:
    """USD ước tính một lượt web (cùng kiểu `theo_doi._uoc_phan`): trang kết quả × giá + phí
    khởi động, cộng trần trang đọc qua actor dự phòng, nhân hệ số hao hụt. HTTP thường: 0."""
    if so_truy_van <= 0:
        return 0.0
    tim = so_truy_van * max(1, so_trang) * GIA_TRANG + KHOI_DONG
    return round((tim + max(0, so_boc) * GIA_BOC) * HE_SO_UOC, 4)


def so_trang_cua(so_bai: int) -> int:
    """Số trang kết quả mỗi câu tìm cho `so_bai` kết quả (10 link/trang)."""
    return max(1, math.ceil(max(0, int(so_bai or 0)) / KQ_MOI_TRANG))


def uoc_tu_khoa(tu_khoa: list[str], so_bai: int, boc: int = BOC_MAC_DINH) -> float:
    """USD TỐI ĐA một lượt web theo cấu hình (số kết quả mỗi câu, trần trang dự phòng)."""
    if so_bai <= 0:
        return 0.0
    return uoc_luot(so_cau_tim(tu_khoa), so_trang_cua(so_bai), boc)


def tran_luot(uoc: float, con_usd: float | None = None) -> float:
    """Trần USD gửi kèm lượt actor: ước tính × 1,5, không thấp hơn mức kẹp 0,1, không quá phần
    tháng còn lại. Tháng còn < 0,1 thì 0 (bên gọi không chạy)."""
    t = max(TRAN_TOI_THIEU, round(uoc * HE_SO_TRAN, 4))
    if con_usd is not None:
        if con_usd < TRAN_TOI_THIEU:
            return 0.0
        t = min(t, con_usd)
    return round(t, 4)


# ───────────────────────────── ngày ─────────────────────────────
_DON_VI = {"phut": 60, "phút": 60, "minute": 60, "minutes": 60, "min": 60, "mins": 60,
           "gio": 3600, "giờ": 3600, "hour": 3600, "hours": 3600,
           "ngay": 86400, "ngày": 86400, "day": 86400, "days": 86400,
           "tuan": 604800, "tuần": 604800, "week": 604800, "weeks": 604800,
           "thang": 2592000, "tháng": 2592000, "month": 2592000, "months": 2592000}
_THANG_EN = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def ngay_iso(s) -> datetime.datetime | None:
    """ISO 8601 của JSON-LD/meta ("2026-07-02T09:12:45+0700", "...Z", không múi giờ = giờ VN)."""
    s = str(s or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(?:\.\d+)?)?"
                 r"\s*(Z|[+-]\d{2}:?\d{2})?", s)
    if not m:
        return None
    y, mo, d, hh, mi, ss, tz = m.groups()
    if tz in (None, ""):
        z = _VN
    elif tz == "Z":
        z = datetime.timezone.utc
    else:
        h, p = int(tz[1:3]), int(tz[-2:])
        z = datetime.timezone((1 if tz[0] == "+" else -1) * datetime.timedelta(hours=h, minutes=p))
    try:
        return datetime.datetime(int(y), int(mo), int(d), int(hh or 0), int(mi or 0),
                                 int(ss or 0), tzinfo=z)
    except ValueError:
        return None


def ngay_serp(s, bay_gio: datetime.datetime | None = None) -> datetime.datetime | None:
    """Ngày Google hiện cạnh kết quả: "4 thg 5, 2026", "5 ngày trước", "14 giờ trước",
    "Oct 5, 2026", "3 days ago", hoặc ISO."""
    s = str(s or "").strip()
    if not s:
        return None
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    m = re.match(r"(\d+)\s+(\S+)\s+(trước|ago)", s.lower())
    if m and m.group(2) in _DON_VI:
        return bay_gio - datetime.timedelta(seconds=int(m.group(1)) * _DON_VI[m.group(2)])
    m = re.match(r"(\d{1,2})\s+thg\s+(\d{1,2}),?\s+(\d{4})", s.lower())
    if m:
        d, mo, y = map(int, m.groups())
    else:
        m = re.match(r"([a-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})", s.lower())
        if not m or m.group(1) not in _THANG_EN:
            return ngay_iso(s)
        mo, d, y = _THANG_EN[m.group(1)], int(m.group(2)), int(m.group(3))
    try:
        return datetime.datetime(y, mo, d, 12, 0, tzinfo=_VN)   # giữa ngày: lệch múi giờ không đổi ngày
    except ValueError:
        return None


# ───────────────────────────── đọc kết quả tìm ─────────────────────────────
def doc_serp(items: list, bay_gio: datetime.datetime | None = None) -> list[dict]:
    """Dataset actor tìm -> [{link, tieu_de, trich, ngay, truy_van, vi_tri}]. Nhận ba dạng đã
    gặp: scraperlink (`results`), cheapapi (`newsResults`/`organicResults`, dòng `newsResult`),
    actor chính chủ (`organicResults`)."""
    ra = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        q = str(it.get("search_term") or it.get("searchTerm") or "")
        con = [it] if it.get("rowType") in ("newsResult", "organicResult") else (
            it.get("results") or it.get("organicResults") or it.get("newsResults") or [])
        for r in con if isinstance(con, list) else []:
            if not isinstance(r, dict):
                continue
            link = str(r.get("link") or r.get("url") or "")
            if not link.startswith(("http://", "https://")):
                continue
            try:                         # dòng hỏng (ngày lạ, kiểu lạ) bỏ riêng dòng đó
                ra.append({"link": link, "tieu_de": str(r.get("title") or "")[:300],
                           "trich": str(r.get("snippet") or r.get("description") or "")[:500],
                           "ngay": ngay_serp(r.get("date") or r.get("published"), bay_gio),
                           "truy_van": q[:200], "vi_tri": r.get("position")})
            except (ValueError, TypeError, OverflowError):
                continue
    return ra


# ───────────────────────────── bóc HTML ─────────────────────────────
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
         "source", "track", "wbr"}
_THE_BO = {"script", "style", "noscript", "nav", "header", "footer", "aside", "form", "button",
           "select", "svg", "iframe", "template", "option", "textarea"}
_THE_KHOI = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "figcaption",
             "td", "th", "section", "article", "tr", "dd", "dt", "pre", "ul", "ol", "table"}
_LOP_BO = re.compile(r"(?:^|[-_])(?:related|relate|lienquan|lien-?quan|sidebar|comments?|"
                     r"footer|menu|breadcrumbs?|share|social|tags?|banner|ads|advert|"
                     r"quang-?cao|newsletter|popup|modal|recommend|goi-?y|most-?read|"
                     r"xem-?them|tin-?khac|readmore|navigation)(?:$|[-_])", re.IGNORECASE)
_LOP_CHINH = re.compile(r"(?:^|[-_])(?:article|content|detail|post|entry|bbwrapper|"
                        r"message-?body|maincontent|singular|story)(?:$|[-_])", re.IGNORECASE)
_KIEU_BAI = ("NewsArticle", "Article", "BlogPosting", "DiscussionForumPosting",
             "ReportageNewsArticle", "AnalysisNewsArticle", "OpinionNewsArticle",
             "SocialMediaPosting", "Report")


class _Boc(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ngan: list[tuple[str, bool, bool]] = []   # (thẻ, bỏ, chính)
        self.bo = self.chinh = 0
        self.khoi: list[tuple[str, bool]] = []
        self.buf: list[str] = []
        self.buf_chinh = False
        self.meta: dict[str, str] = {}
        self.ld: list[str] = []
        self._ld: list[str] | None = None
        self._title: list[str] | None = None
        self.title = ""
        self.canonical = ""
        self.lien_ket: list[tuple[str, bool]] = []
        self.time_dau = ""

    def _xa(self):
        t = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if t:
            self.khoi.append((t, self.buf_chinh))
        self.buf, self.buf_chinh = [], False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "meta":
            k = (a.get("property") or a.get("name") or a.get("itemprop") or "").lower()
            if k and a.get("content") and k not in self.meta:
                self.meta[k] = a["content"].strip()
            return
        if tag == "link":
            if "canonical" in a.get("rel", "").lower() and a.get("href"):
                self.canonical = a["href"].strip()
            return
        if tag in _VOID:
            if tag == "br":
                self.buf.append("\n")
            return
        lop = f"{a.get('class', '')} {a.get('id', '')}".split()
        bo = (tag in _THE_BO or a.get("aria-hidden") == "true"
              or any(_LOP_BO.search(x) for x in lop))
        chinh = tag in ("article", "main") or any(_LOP_CHINH.search(x) for x in lop)
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self._ld = []
        if tag == "title" and not self.title:
            self._title = []
        if tag in _THE_KHOI:
            self._xa()
        if tag == "a" and a.get("href") and not self.bo:
            self.lien_ket.append((a["href"], self.chinh > 0 or chinh))
        if tag == "time" and a.get("datetime") and not self.time_dau and not self.bo:
            self.time_dau = a["datetime"]
        self.ngan.append((tag, bo, chinh))
        self.bo += bo
        self.chinh += chinh

    def handle_endtag(self, tag):
        if tag in _VOID or not any(t == tag for t, _, _ in self.ngan):
            return
        if tag in _THE_KHOI:
            self._xa()
        while self.ngan:
            t, bo, chinh = self.ngan.pop()
            self.bo -= bo
            self.chinh -= chinh
            if t == tag:
                break
        if tag == "script" and self._ld is not None:
            self.ld.append("".join(self._ld))
            self._ld = None
        if tag == "title" and self._title is not None:
            self.title = re.sub(r"\s+", " ", "".join(self._title)).strip()
            self._title = None

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
            return
        if self._title is not None:
            self._title.append(data)
            return
        if self.bo <= 0:
            self.buf.append(data)
            self.buf_chinh = self.buf_chinh or self.chinh > 0


def _duyet_ld(x, ra: list):
    if isinstance(x, list):
        for y in x:
            _duyet_ld(y, ra)
    elif isinstance(x, dict):
        if "@graph" in x:
            _duyet_ld(x["@graph"], ra)
        kieu = x.get("@type")
        kieu = kieu if isinstance(kieu, list) else [kieu]
        if any(k in _KIEU_BAI for k in kieu):
            ra.append(x)


def _ten(x) -> str:
    if isinstance(x, list):
        return ", ".join(t for t in (_ten(y) for y in x[:3]) if t)
    if isinstance(x, dict):
        return str(x.get("name") or "")
    return "" if str(x or "").startswith("http") else str(x or "")


def _so_bl(o: dict) -> int | None:
    if str(o.get("commentCount") or "").isdigit():
        return int(o["commentCount"])
    st = o.get("interactionStatistic")
    for s in st if isinstance(st, list) else [st]:
        if isinstance(s, dict) and re.search(r"Comment|Reply", str(s.get("interactionType"))):
            try:
                return int(s.get("userInteractionCount"))
            except (TypeError, ValueError):
                pass
    return None


def boc_trang(html_text: str, url: str = "") -> dict:
    """HTML -> {tieu_de, noi_dung, dang_luc, sua_luc, tac_gia, ten_trang, kieu_ld,
    so_binh_luan, canonical, lien_ket_chinh}. Thân bài: khối trong vùng chính (article/main/
    lớp *content*/*detail*/bbWrapper) nếu đủ dài, không thì mọi khối ngoài nav/footer/tin liên
    quan — tránh bắt chữ brand ở cột "tin liên quan"."""
    p = _Boc()
    try:
        p.feed(html_text or "")
        p.close()
    except Exception:  # noqa: BLE001 — HTML hỏng: dùng phần đã đọc được
        p.khoi.append(("", False))
    p._xa()
    ld: list[dict] = []
    for raw in p.ld:
        try:
            _duyet_ld(json.loads(raw.strip(), strict=False), ld)
        except (ValueError, RecursionError):     # JSON-LD hỏng / lồng quá sâu
            continue
    o = ld[0] if ld else {}
    kieu = o.get("@type")
    kieu = next((k for k in (kieu if isinstance(kieu, list) else [kieu]) if k in _KIEU_BAI), "")
    chinh = [t for t, c in p.khoi if c]
    khoi = chinh if sum(len(t) for t in chinh) >= 200 else [t for t, _ in p.khoi]
    gon: list[str] = []
    for t in khoi:
        if not gon or gon[-1] != t:
            gon.append(t)
    than = "\n".join(gon)
    body = str(o.get("articleBody") or "")
    if len(body) > len(than):
        than = body
    m = p.meta
    dang = ngay_iso(o.get("datePublished") or m.get("article:published_time")
                    or m.get("datepublished") or m.get("pubdate") or m.get("publishdate")
                    or m.get("og:published_time") or m.get("dc.date") or p.time_dau)
    sua = ngay_iso(o.get("dateModified") or m.get("article:modified_time")
                   or m.get("datemodified"))
    tieu_de = str(o.get("headline") or m.get("og:title") or p.title or "").strip()
    # Canonical khác miền (giả mạo) hoặc trỏ về TRANG CHỦ (nhiều CMS đặt sai) thì bỏ.
    pc = _tach(p.canonical)
    can = (p.canonical if pc and mien(p.canonical) == mien(url)
           and (pc.path or "/").strip("/") else "")
    return {"tieu_de": re.sub(r"\s+", " ", tieu_de)[:300], "noi_dung": than,
            "dang_luc": dang, "sua_luc": sua,
            "tac_gia": (_ten(o.get("author")) or _ten(m.get("author"))
                        or _ten(m.get("article:author")))[:200],
            "ten_trang": (m.get("og:site_name") or _ten(o.get("publisher")) or mien(url))[:200],
            "kieu_ld": kieu, "so_binh_luan": _so_bl(o) if o else None, "canonical": can,
            "lien_ket_chinh": [x for x in (_noi(url, h) for h, c in p.lien_ket if c) if x]}


def _noi(goc: str, h: str) -> str:
    try:
        return urllib.parse.urljoin(goc, h)
    except ValueError:
        return ""


# ───────────────────────────── nhắc brand ─────────────────────────────
def vi_tri_nhac(text: str, tu_khoa: list[str]) -> list[tuple[int, int]]:
    """Vị trí (đầu, cuối) mỗi lần nhắc từ khoá trên text gốc (khớp trên bản bỏ dấu cùng độ dài).
    Kim ≤3 ký tự phải trùng nguyên từ; cụm nhiều chữ cho phép dấu câu/khoảng trắng ở giữa."""
    n = _bo_dau(text)
    ra: set[tuple[int, int]] = set()
    for q in tu_khoa:
        t = _tu(q)
        if not t:
            continue
        if len(t) == 1 and len(t[0]) > 3:
            mau = re.escape(t[0])
        else:
            mau = r"(?<![^\W_])" + r"[\W_]+".join(re.escape(x) for x in t) + r"(?![^\W_])"
        ra.update((m.start(), m.end()) for m in re.finditer(mau, n))
    return sorted(ra)


def doan_trich(text: str, vt: list[tuple[int, int]], truoc: int = 60, sau: int = 200,
               toi_da: int = 3) -> list[str]:
    """Tối đa `toi_da` đoạn quanh các lần nhắc, không chồng nhau."""
    ra, het = [], -1
    for a, b in vt:
        if a < het:
            continue
        x, y = max(0, a - truoc), min(len(text), b + sau)
        ra.append(("…" if x else "") + re.sub(r"\s+", " ", text[x:y]).strip()
                  + ("…" if y < len(text) else ""))
        het = y
        if len(ra) >= toi_da:
            break
    return ra


def danh_gia_nhac(trang: dict, tu_khoa: list[str], nha: list[str]) -> dict:
    """Mức nhắc + dấu hiệu bài PR. 'tieu_de' (brand ở tiêu đề) > 'chinh' (≥3 lần) > 'thoang'
    (nhắc lướt, vd bài "top 10 túi"). `la_pr`: thân bài dẫn link về miền nhà hoặc ghi
    "Ảnh/Nguồn: <brand>" — bài đặt (owned/paid), tách khỏi báo tự viết (earned)."""
    than = trang.get("noi_dung") or ""
    vt = vi_tri_nhac(than, tu_khoa)
    o_tieu_de = bool(vi_tri_nhac(trang.get("tieu_de") or "", tu_khoa))
    muc = "tieu_de" if o_tieu_de else ("chinh" if len(vt) >= 3 else ("thoang" if vt else ""))
    link_nha = sum(1 for h in trang.get("lien_ket_chinh") or [] if _thuoc(mien(h), nha))
    nb = _bo_dau(than)
    ghi_nguon = any(re.search(rf"\b(anh|nguon|photo|source)\s*:\s*{re.escape(_bo_dau(k))}\b", nb)
                    for k in tu_khoa if len(_tu(k)) == 1)
    return {"so_lan_nhac": len(vt) + (1 if o_tieu_de else 0), "muc_nhac": muc,
            "la_pr": bool(link_nha or ghi_nguon), "link_nha": link_nha, "vi_tri": vt}


# ───────────────────────────── tải trang (HTTP thường, an toàn) ─────────────────────────────
def _ip_noi_bo(ip: str) -> bool:
    try:
        x = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return not x.is_global or x.is_multicast


def url_an_toan(url: str, phan_giai=None) -> bool:
    """Chỉ http/https, cổng mặc định, miền phân giải ra IP công khai — URL do Google trả về
    không được dẫn bot vào mạng nội bộ của VPS."""
    p = _tach(url)
    if p is None or p.scheme not in ("http", "https") or not p.hostname or p.username \
            or p.password:
        return False
    try:
        cong = p.port                    # ":99999" ném ValueError
    except ValueError:
        return False
    if cong not in (None, 80, 443):
        return False
    h = p.hostname
    try:
        ipaddress.ip_address(h)
        return not _ip_noi_bo(h)
    except ValueError:
        pass
    try:
        ips = (phan_giai or (lambda x: [a[4][0] for a in socket.getaddrinfo(x, None)]))(h)
    except (OSError, UnicodeError):
        return False
    return bool(ips) and not any(_ip_noi_bo(i) for i in ips)


def tai_http(url: str, han: float | None = None) -> tuple[int, str, str]:
    """GET một trang -> (mã HTTP | 0 khi lỗi mạng | -1 khi URL không an toàn, html, url cuối).
    Tự theo ≤4 lần chuyển hướng, kiểm an toàn từng bước; chỉ đọc text/html, ≤3 MB."""
    import requests
    het = time.monotonic() + GIAY_TRANG_TOI_DA
    if han is not None:
        het = min(het, han)
    cur = url
    for _ in range(5):
        if not url_an_toan(cur):
            return -1, "", cur
        doc = GIAY_DOC if han is None else max(2.0, min(GIAY_DOC, han - time.monotonic()))
        try:
            r = requests.get(cur, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.5",
                                           "Accept-Language": "vi,en;q=0.5"},
                             timeout=(GIAY_KET_NOI, doc), allow_redirects=False, stream=True)
        except requests.RequestException:
            return 0, "", cur
        with r:
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                cur = _noi(cur, r.headers["location"])
                if not cur:
                    return -1, "", url
                continue
            loai = r.headers.get("content-type", "").lower()
            if r.status_code != 200 or ("html" not in loai and "text/plain" not in loai):
                return r.status_code if r.status_code != 200 else 415, "", cur
            buf, n = [], 0
            try:
                for ch in r.iter_content(65536):
                    buf.append(ch)
                    n += len(ch)
                    if n >= BYTE_TOI_DA:
                        break
                    if time.monotonic() > het:
                        # Máy chủ nhỏ giọt (mỗi khối kịp trước timeout đọc): hạn đồng hồ của
                        # trang và của lượt, không đợi tới 3 MB.
                        return 0, "", cur
            except requests.RequestException:
                return 0, "", cur
            m = re.search(r"charset=([\w-]+)", loai)
            try:
                return 200, b"".join(buf).decode(m.group(1) if m else "utf-8", "replace"), cur
            except LookupError:
                return 200, b"".join(buf).decode("utf-8", "replace"), cur
    return 0, "", cur


class Robots:
    """robots.txt theo miền (nhớ trong lượt). 200 -> theo luật; 4xx -> cho phép; lỗi mạng /
    5xx -> KHÔNG tải (RFC 9309: không đọc được thì coi như cấm hết)."""

    def __init__(self, tai):
        self.tai, self.nho = tai, {}

    def cho_phep(self, url: str) -> bool:
        p = _tach(url)
        if p is None or not p.netloc:
            return False
        goc = f"{p.scheme}://{p.netloc}"
        if goc not in self.nho:
            ma, txt, _ = self.tai(goc + "/robots.txt")
            if ma == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(txt.splitlines())
                self.nho[goc] = rp
            else:
                self.nho[goc] = 400 <= ma < 500
        x = self.nho[goc]
        return x if isinstance(x, bool) else x.can_fetch(UA_ROBOTS, url)


# ───────────────────────────── một lượt ─────────────────────────────
def _chay_actor_mac_dinh(payload: dict, limit: int, han: float, tran: float):
    import apify_tool as A
    return A._run_actor(ACTOR_TIM, payload, limit, deadline=han, tran_usd=tran,
                        mot_phan=True, nen_tang=NEN_TANG)


def payload_boc(urls: list[str]) -> dict:
    """Input của `ACTOR_BOC`: đúng các trang này (độ sâu 0), trả HTML để bóc bằng `boc_trang`
    như trang đọc thường (cùng luật thân bài / ngày / tác giả)."""
    return {"startUrls": [{"url": u} for u in urls], "crawlerType": "playwright:adaptive",
            "maxCrawlDepth": 0, "maxCrawlPages": len(urls), "maxResults": len(urls),
            "saveHtml": True, "saveMarkdown": False, "removeCookieWarnings": True,
            "proxyConfiguration": {"useApifyProxy": True}}


def giay_boc(tran: float) -> float:
    """Thời gian chạy tối đa của actor dự phòng để tiền (theo tài nguyên) không vượt `tran`:
    chia thêm hệ số an toàn `BOC_HE_SO_AN_TOAN` (giá giây đo một lần, proxy/khởi động dao động)."""
    return tran / (BOC_USD_MOI_GIAY * BOC_HE_SO_AN_TOAN)


def _boc_mac_dinh(urls: list[str], han: float, tran: float):
    import apify_tool as A
    het = min(han, time.monotonic() + giay_boc(tran))
    return A._run_actor(ACTOR_BOC, payload_boc(urls), len(urls), mem=BOC_BO_NHO, deadline=het,
                        tran_usd=tran, mot_phan=True, nen_tang=NEN_TANG)


def trang_tu_boc(it: dict) -> tuple[str, dict | None]:
    """Một item của actor dự phòng -> (URL chuẩn, trang đã bóc | None khi trang vẫn hỏng)."""
    try:
        return _trang_tu_boc(it)
    except Exception:  # noqa: BLE001 — một item hỏng không làm mất cả lô đã trả tiền
        return url_chuan(str(it.get("url") or "")), None


def _trang_tu_boc(it: dict) -> tuple[str, dict | None]:
    url = str(it.get("url") or (it.get("crawl") or {}).get("loadedUrl") or "")
    ma = (it.get("crawl") or {}).get("httpStatusCode")
    if not url or (ma is not None and ma != 200):
        return url_chuan(url), None
    if it.get("html"):
        t = boc_trang(str(it["html"]), url)
    else:
        m = it.get("metadata") or {}
        t = {"tieu_de": str(m.get("title") or ""), "noi_dung": str(it.get("text") or ""),
             "dang_luc": None, "sua_luc": None, "tac_gia": _ten(m.get("author")),
             "ten_trang": mien(url), "kieu_ld": "", "so_binh_luan": None, "canonical": "",
             "lien_ket_chinh": []}
    return url_chuan(url), (t if (t.get("noi_dung") or "").strip() else None)


def _che(s) -> str:
    """Thông điệp lỗi an toàn để ghi: che chuỗi giống token, cắt ngắn."""
    return re.sub(r"(apify_api_|token=)[\w-]+", r"\1***", str(s))[:200]


def thanh_hit(goc: dict, trang: dict | None, nhac: dict, tu_khoa: list[str],
              dt: datetime.datetime) -> tuple[dict, datetime.datetime]:
    """Một bài web -> `(d, dt)` đúng dạng hit của Mark (`theo_doi._giu_tu_khoa`). `text` đặt
    tiêu đề + đoạn quanh lần nhắc ĐẦU lên trước: bước AI chỉ xem 200 ký tự đầu (`_boc_bai`)."""
    trang = trang or {}
    link = goc["link"]
    tieu_de = trang.get("tieu_de") or goc.get("tieu_de") or ""
    than = trang.get("noi_dung") or ""
    doan = doan_trich(than, nhac.get("vi_tri") or []) if than else []
    if not doan and goc.get("trich"):
        doan = [goc["trich"]]
    text = (tieu_de[:110] + " | " + " … ".join(doan)).strip(" |")[:CHU_TOI_DA]
    m = mien(link)
    d = {"platform": NEN_TANG, "link": link, "text": text, "hashtags": "",
         "kenh": trang.get("ten_trang") or m, "username": m, "followers": None,
         "views": None, "likes": None, "shares": None,
         "comments": trang.get("so_binh_luan"), "__goc": {"id": ma_web(link)},
         "_web": {"kieu_trang": kieu_trang(link, trang.get("kieu_ld") or ""),
                  "muc_nhac": nhac.get("muc_nhac") or "", "so_lan_nhac": nhac.get("so_lan_nhac", 0),
                  "la_pr": bool(nhac.get("la_pr")), "tieu_de": tieu_de[:300],
                  "tac_gia_bai": trang.get("tac_gia") or "", "chi_trich": not than,
                  "truy_van": goc.get("truy_van") or ""}}
    return d, dt


def thanh_dong(d: dict, dt: datetime.datetime, sac_thai: str | None = None,
               chu_de: str | None = None, ly_do: str = "khop_tu_khoa") -> dict:
    """Hit -> dòng bảng `bai` (cùng khoá với `theo_doi._giu_tu_khoa`), kèm cột đề xuất thêm
    (`kieu_trang`, `muc_nhac`, `la_pr`) — `lang_nghe_db.ghi_bai` chỉ lấy cột nó biết nên
    cột thừa vô hại cho tới khi schema có."""
    w = d.get("_web") or {}
    return {"khoa": f"{NEN_TANG}:{d['__goc']['id']}", "nen_tang": NEN_TANG, "nguon_id": None,
            "link": d["link"], "tac_gia": str(d.get("kenh") or "")[:200],
            "tai_khoan": str(d.get("username") or "")[:200], "followers": None, "dang_luc": dt,
            "noi_dung": str(d.get("text") or "")[:CHU_TOI_DA], "hashtag": "",
            "khop_tu_khoa": True, "sac_thai": sac_thai, "chu_de": chu_de,
            "ly_do_giu": str(ly_do)[:60], "xem": None, "thich": None,
            "binh_luan": d.get("comments"), "chia_se": None,
            "kieu_trang": w.get("kieu_trang"), "muc_nhac": w.get("muc_nhac"),
            "la_pr": w.get("la_pr")}


def _pheu_moi() -> dict:
    return {k: 0 for k in ("serp", "trung", "mxh", "tmdt", "nha", "tuyen_dung", "tep", "url_hong",
                           "da_co",
                           "da_loai_truoc", "robots_chan", "tai_loi", "boc_du_phong",
                           "boc_duoc", "da_boc_truoc", "chi_trich", "khong_ngay", "qua_cu",
                           "khong_nhac", "loai_tru", "spam", "trang_hong", "giu")}


def thu_thap(du_an: dict, *, tu: datetime.date | None = None, den: datetime.date | None = None,
             so_trang: int = TRANG_MAC_DINH, con_usd: float | None = None,
             han: float | None = None, chay_actor=None, tai=None, tai_robots=None,
             ngu=time.sleep, bay_gio: datetime.datetime | None = None,
             tu_dong_ho=time.monotonic, them_tu: list[str] | None = None,
             tu_giu: datetime.datetime | None = None, da_biet=None,
             boc=None, boc_toi_da: int = 0, da_boc: set[str] | None = None,
             so: dict | None = None, tu_tim: list[str] | None = None) -> tuple[list, dict]:
    """MỘT lượt web của dự án -> (hits `(d, dt)` đã qua lọc luật, thống kê phễu). `tu_tim` (18/10/2026,
    `theo_doi.tu_nen_tang`): từ khoá đem đi TÌM khi khác từ khoá dự án (bỏ `bo_tu` của web) — chỉ
    đổi câu tìm Google, bài vẫn lọc theo đủ từ khoá dự án.

    Bước: câu tìm (từ khoá + `them_tu`) -> actor Google (trần USD) -> chống trùng URL chuẩn ->
    bỏ MXH/sàn/miền nhà -> `da_biet(khoá)` (bài đã có trong kho / đã bị loại: không tải lại) ->
    robots.txt -> tải + bóc trang (nghỉ giữa hai lần cùng miền; chuyển hướng sang miền khác thì
    kiểm robots của miền mới) -> trang không đọc được (403, lỗi mạng) mà robots CHO PHÉP và chưa
    thử đọc dự phòng trong `BOC_NHO_NGAY` ngày (`da_boc`): đọc lại qua actor dự phòng (≤
    `boc_toi_da` trang, trần trong phần ngân sách còn lại) -> vẫn không được thì đoạn trích
    Google -> ngày (trang > Google) từ `tu_giu` (mặc định `NGAY_GIU` ngày) -> nhắc từ khoá + từ
    loại trừ xét trên TIÊU ĐỀ + ĐOẠN quanh chỗ nhắc (không xét cả thân bài) -> spam. Bước AI +
    ghi kho để `theo_doi._giu_tu_khoa` làm (như mọi nền tảng).

    Một trang hỏng (URL lạ, HTML/JSON-LD hỏng) chỉ mất trang đó (`pheu.trang_hong`), không làm
    vỡ lượt. `so`: dict của bên gọi để nhận thống kê NGAY KHI có (tiền, run id) — kể cả khi hàm
    vẫn ném lỗi bất ngờ, bên gọi vẫn chốt được tiền đã tiêu.

    `tk["usd_tim"]`, `tk["usd_boc"]`: tiền theo sổ (giá thật × trang Google về; actor dự phòng
    tính nguyên trần tới khi chốt theo run id); `tk["run_ids"]`; `tk["da_boc_moi"]`: khoá trang
    vừa gửi actor dự phòng (bên gọi ghi sổ `BOC_NHO_NGAY` ngày); `tk["bi_loai"]`: (khoá, lý do,
    ngày) bị loại theo luật — gồm cả khoá URL Google lẫn khoá canonical khi khác nhau."""
    import apify_tool as A
    import loc_rac
    bay_gio = bay_gio or datetime.datetime.now(_VN)
    den = den or bay_gio.astimezone(_VN).date()
    tu = tu or den - datetime.timedelta(days=7)
    han = han if han is not None else tu_dong_ho() + 600
    tai = tai or (lambda u: tai_http(u, han))
    robots = Robots(tai_robots or tai)
    tk: dict = so if so is not None else {}
    tk.update({"truy_van": [], "uoc_usd": 0.0, "tran_usd": 0.0, "run_id": None, "run_ids": [],
               "usd_tim": 0.0, "usd_boc": 0.0, "trang_thai": "", "loi": "", "ghi_chu": [],
               "bi_loai": [], "da_boc_moi": [], "pheu": _pheu_moi()})
    ph = tk["pheu"]
    da_boc = set(da_boc or ())
    goc_tu = [str(x) for x in du_an.get("tu_khoa") or [] if str(x).strip()] or [du_an["ten"]]
    tu_khoa = rut_gon_tu_khoa([*goc_tu, *(them_tu or [])]) or goc_tu
    loai_tru = [str(x) for x in du_an.get("tu_loai_tru") or [] if str(x).strip()]
    nha = mien_nha(du_an)
    q = cau_truy_van({**du_an, "tu_khoa": tu_tim} if tu_tim is not None else du_an, them_tu)
    tk["truy_van"] = q
    tk["uoc_usd"] = uoc_luot(len(q), so_trang)
    tran = tran_luot(tk["uoc_usd"], con_usd)
    tk["tran_usd"] = tran
    if not q or not tran:
        # Không chạy gì: trạng thái "bo_qua" — bên gọi KHÔNG dời mốc web (review 16/10, L4).
        tk["trang_thai"] = "bo_qua: " + ("không có từ khoá" if not q else "hết ngân sách tháng")
        return [], tk
    try:
        items, meta = (chay_actor or _chay_actor_mac_dinh)(
            payload_tim(q, tu, den, so_trang, du_an.get("thi_truong") or "VN"),
            len(q) * max(1, so_trang) + 2, han, tran)
        tk["run_id"] = (meta or {}).get("run_id")
    except Exception as e:  # noqa: BLE001 — lỗi actor: báo trong phễu, không làm hỏng lượt lớn
        tk["trang_thai"], tk["loi"] = "loi", _che(f"{getattr(e, 'ma', type(e).__name__)}: {e}")
        em = getattr(e, "meta", None) or {}
        if em.get("run_id"):             # run đã tạo rồi mới hỏng: tiền chưa biết -> nguyên trần
            tk["run_ids"].append(em["run_id"])
            tk["usd_tim"] = tran
        return [], tk
    if tk["run_id"]:
        tk["run_ids"].append(tk["run_id"])
    # Sổ theo GIÁ THẬT: actor tính 0,0005 USD mỗi item (= một trang kết quả) đã về.
    items = items if isinstance(items, list) else []
    tk["usd_tim"] = round(sum(1 for it in items if isinstance(it, dict)) * GIA_TRANG, 4)
    serp = doc_serp(items, bay_gio)
    ph["serp"] = len(serp)
    moc = tu_giu or max(datetime.datetime.combine(tu, datetime.time(), _VN),
                        bay_gio - datetime.timedelta(days=NGAY_GIU))
    het = datetime.datetime.combine(den + datetime.timedelta(days=1), datetime.time(), _VN)

    def hong(g, e) -> None:
        ph["trang_hong"] += 1
        if len(tk["ghi_chu"]) < 5:
            tk["ghi_chu"].append(_che(f"trang hỏng ({mien(g.get('link')) or '?'}): "
                                      f"{type(e).__name__}"))

    def hoi_biet(khoa: list[str]) -> dict:
        if not da_biet or not khoa:
            return {}
        try:
            return da_biet(khoa) or {}
        except Exception as e:  # noqa: BLE001 — không hỏi được: coi như chưa biết
            tk["ghi_chu"].append(_che(f"không đọc được sổ bài đã biết: {type(e).__name__}"))
            return {}

    # 1) lọc URL + chống trùng (trước mọi lần tải)
    cho: list[dict] = []
    thay: set[str] = set()
    for g in serp:
        try:
            ly = _ly_do_bo_url(g["link"], nha)
            if ly:
                ph[ly] += 1
                continue
            k = ma_web(g["link"])
        except Exception as e:  # noqa: BLE001
            hong(g, e)
            continue
        if k in thay:
            ph["trung"] += 1
            continue
        thay.add(k)
        cho.append(g)
    biet = hoi_biet([khoa_web(g["link"]) for g in cho])
    con_lai = []
    for g in cho:
        ly = biet.get(khoa_web(g["link"]))
        if ly in ("da_co", "da_loai_truoc"):
            ph[ly] += 1                  # đã có / đã loại: không tải lại, không trả tiền đọc
        else:
            con_lai.append(g)

    # 2) tải HTTP thường — mỗi trang trong try riêng
    lan_cuoi: dict[str, float] = {}
    da_tai = 0
    doc: list[list] = []             # [kết quả Google, trang | None, ứng viên đọc dự phòng?]
    for g in con_lai:
        trang, ung_vien = None, False
        try:
            if tu_dong_ho() < han - _CHUA_GIAY and da_tai < TOI_DA_TAI:
                if not robots.cho_phep(g["link"]):
                    ph["robots_chan"] += 1
                else:
                    m = mien(g["link"])
                    nghi = NGHI_MOI_MIEN - (tu_dong_ho() - lan_cuoi.get(m, -1e9))
                    if nghi > 0:
                        ngu(nghi)
                    ma, h, cuoi = tai(g["link"])
                    lan_cuoi[m] = tu_dong_ho()
                    da_tai += 1
                    if ma == 200 and h and mien(cuoi) != m and not robots.cho_phep(cuoi):
                        ph["robots_chan"] += 1   # chuyển hướng sang miền khác cấm bot (L2)
                    elif ma == 200 and h:
                        trang = boc_trang(h, cuoi)
                    elif ma != -1:       # -1: URL không an toàn — không đọc bằng đường nào
                        ph["tai_loi"] += 1
                        ung_vien = True  # robots cho phép, chỉ bị chặn/lỗi
        except Exception as e:  # noqa: BLE001 — trang hỏng: giữ đoạn trích Google
            hong(g, e)
            trang, ung_vien = None, False
        doc.append([g, trang, ung_vien])

    # 3) actor dự phòng cho trang bị chặn — ưu tiên trang mà Google đã thấy nhắc brand; bỏ trang
    #    đã thử đọc dự phòng trong `BOC_NHO_NGAY` ngày (đọc lại cũng chặn/hỏng như cũ, tốn tiền).
    ung = []
    for x in doc:
        if x[2]:
            if khoa_web(x[0]["link"]) in da_boc:
                ph["da_boc_truoc"] += 1
            else:
                ung.append(x)
    ung.sort(key=lambda x: not A._khop_tu_khoa(
        {"text": f"{x[0]['tieu_de']} {x[0]['trich']}"}, tu_khoa))
    ung = ung[:max(0, boc_toi_da)]
    con_boc = (con_usd if con_usd is not None else float("inf")) - tk["usd_tim"]
    tran_boc = round(min(max(TRAN_TOI_THIEU, len(ung) * GIA_BOC * HE_SO_TRAN), con_boc), 4)
    if ung and tran_boc < TRAN_TOI_THIEU:
        tk["ghi_chu"].append(f"đọc dự phòng: bỏ qua {len(ung)} trang (hết ngân sách)")
        ung = []
    if ung and han - tu_dong_ho() < BOC_GIAY_TOI_THIEU + _CHUA_GIAY:
        tk["ghi_chu"].append(f"đọc dự phòng: bỏ qua {len(ung)} trang (hết giờ)")
        ung = []
    if ung:
        ph["boc_du_phong"] = len(ung)
        tk["da_boc_moi"] = [khoa_web(x[0]["link"]) for x in ung]
        theo: dict = {}
        try:
            # Actor tính theo tài nguyên: sổ giữ NGUYÊN TRẦN tới khi chốt theo run id (M5).
            tk["usd_boc"] = tran_boc
            items_b, meta_b = (boc or _boc_mac_dinh)([x[0]["link"] for x in ung], han, tran_boc)
            rid = (meta_b or {}).get("run_id")
            if rid:
                tk["run_ids"].append(rid)
            for it in items_b or []:
                if isinstance(it, dict):
                    k_b, t_b = trang_tu_boc(it)
                    if k_b:
                        theo[k_b] = t_b
        except Exception as e:  # noqa: BLE001 — dự phòng hỏng: về đoạn trích Google
            tk["ghi_chu"].append(_che(f"đọc dự phòng lỗi: {getattr(e, 'ma', type(e).__name__)}"
                                      f": {e}"))
            em = getattr(e, "meta", None) or {}
            if em.get("run_id"):
                tk["run_ids"].append(em["run_id"])
        for x in ung:
            x[1] = theo.get(url_chuan(x[0]["link"]))
        ph["boc_duoc"] = sum(1 for x in ung if x[1] is not None)

    # 4) xét từng bài — khoá canonical cũng hỏi sổ "đã biết"
    can_moi = {}
    for g, trang, _u in doc:
        try:
            if trang is not None and trang.get("canonical"):
                k2 = khoa_web(trang["canonical"])
                if k2 != khoa_web(g["link"]):
                    can_moi[k2] = None
        except Exception:  # noqa: BLE001, S112 — canonical hỏng: bỏ qua canonical
            continue
    biet2 = hoi_biet(list(can_moi))
    hits: list = []
    for g, trang, _u in doc:
        try:
            x = _xet_bai(g, trang, tk, thay, biet2, moc, het, tu_khoa, loai_tru, nha, A, loc_rac)
        except Exception as e:  # noqa: BLE001 — một bài hỏng không làm mất cả lượt
            hong(g, e)
            continue
        if x is not None:
            hits.append(x)
    ph["giu"] = len(hits)
    tk["trang_thai"] = "xong"
    return hits, tk


def _xet_bai(g, trang, tk, thay, biet2, moc, het, tu_khoa, loai_tru, nha, A, loc_rac):
    """Một bài -> hit `(d, dt)` hoặc None (đã đếm vào phễu)."""
    ph = tk["pheu"]
    khoa_g = khoa_web(g["link"])
    if trang is not None and trang.get("canonical"):
        k2 = khoa_web(trang["canonical"])
        if k2 != khoa_g:
            if biet2.get(k2) in ("da_co", "da_loai_truoc"):
                ph[biet2[k2]] += 1
                return None
            if ma_web(trang["canonical"]) in thay:
                ph["trung"] += 1
                return None
            thay.add(ma_web(trang["canonical"]))
            g = {**g, "link": url_chuan(trang["canonical"])}
    khoa = khoa_web(g["link"])
    cac_khoa = [khoa] + ([khoa_g] if khoa_g != khoa else [])
    if trang is None:
        ph["chi_trich"] += 1
        trang_xet = {"tieu_de": g["tieu_de"], "noi_dung": g["trich"]}
    else:
        trang_xet = trang
    dt = trang_xet.get("dang_luc") if trang else None
    if trang and kieu_trang(g["link"], trang.get("kieu_ld") or "") == "dien_dan":
        dt = max([x for x in (dt, trang.get("sua_luc")) if x], default=None)
    dt = dt or g.get("ngay")
    if not dt:
        ph["khong_ngay"] += 1
        return None
    if not (moc <= dt < het):
        ph["qua_cu"] += 1
        return None
    # Nhắc từ khoá + từ loại trừ xét trên TIÊU ĐỀ + ĐOẠN quanh chỗ nhắc (review 16/10, M3): cả
    # thân bài thì từ khoá nhiều chữ "đủ mọi chữ" khớp bừa qua các đoạn xa nhau, và một chữ
    # "guitar" ở cuối bài dài loại oan bài nhắc brand đàng hoàng.
    than = trang_xet.get("noi_dung") or ""
    doan = doan_trich(than, vi_tri_nhac(than, tu_khoa), truoc=120, sau=200, toi_da=5)
    hay = {"text": f"{trang_xet.get('tieu_de') or ''}\n" + "\n".join(doan)}
    if not A._khop_tu_khoa(hay, tu_khoa):
        ph["khong_nhac"] += 1
        tk["bi_loai"].extend((k, "khong_nhac", dt) for k in cac_khoa)
        return None
    if A._tu_loai_tru_khop(hay, loai_tru):
        ph["loai_tru"] += 1
        tk["bi_loai"].extend((k, "loai_tru", dt) for k in cac_khoa)
        return None
    nhac = danh_gia_nhac(trang_xet, tu_khoa, nha)
    d, dt = thanh_hit(g, trang, nhac, tu_khoa, dt)
    if loc_rac.bai_spam(d["text"]):
        ph["spam"] += 1
        tk["bi_loai"].extend((k, "spam", dt) for k in cac_khoa)
        return None
    return d, dt
