"""Chỉ số kiểu Kompa từ các dòng `bai` (kèm loại nguồn) mà `kho.bai_trong_khoang` trả về.

THUẦN Python, không SQL: mọi phép đếm kiểm được bằng bài thử với số tính tay; kho chỉ lọc dự
án + khoảng ngày. Cùng nguyên tắc với `tong_hop_lang_nghe.py` của Mark (13/10/2026) để số trên
dashboard và số trong sheet `social_listen` đọc giống nhau:
  1. CHỈ ĐẾM, KHÔNG ƯỚC LƯỢNG. "Thảo luận" = số bài + số bình luận NỀN TẢNG BÁO trên các bài đó
     (như Kompa); không phải toàn bộ thảo luận về brand.
  2. Bài của kênh nhà (nguồn loại `kenh_nha`) vẫn tính vào số bài / thảo luận / nguồn, nhưng
     KHÔNG vào sắc thái, chủ đề, từ khoá: tiếng của brand không phải tiếng khách.
  3. Ngày luôn là ngày GIỜ VN của `dang_luc`; bài không có ngày đăng thì không xếp vào khoảng.
  4. So sánh với kỳ liền trước CÙNG ĐỘ DÀI; kỳ trước 0 bài thì không bịa % (None).

Sắc thái lưu đúng ba nhãn "Tích cực", "Tiêu cực", "Trung lập" (AI gán lúc Mark quét); None hay
nhãn lạ = "chưa phân loại". Chủ đề (`chu_de`) giữ nguyên chữ đã lưu.
"""
from __future__ import annotations

import collections
import datetime
import itertools
import re
import unicodedata

VN = datetime.timezone(datetime.timedelta(hours=7))
TC, TI, TL = "Tích cực", "Tiêu cực", "Trung lập"
CHUA = "chưa phân loại"
SAC_THAI = (TC, TI, TL)
#: Bài không gắn nguồn theo dõi (Mark tìm theo từ khoá) — xếp như một "loại nguồn" riêng.
KHONG_NGUON = "tu_khoa"
TEN_LOAI = {"kol": "KOL/KOC", "page": "Trang/fanpage", "group": "Nhóm", "bao": "Báo/tin tức",
            "kenh_nha": "Kênh nhà", "khac": "Khác", KHONG_NGUON: "Tìm theo từ khoá"}
TEN_NEN_TANG = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube",
                "facebook": "Facebook"}

NGAY_TOI_DA_THEO_NGAY = 92      # khoảng dài hơn thì gom theo tuần (biểu đồ khỏi vài trăm cột)
TOP_NGUON = 10                  # mỗi nền tảng
TOP_TU_KHOA = 50
TU_KHOA_TOI_THIEU_BAI = 2       # cụm chỉ một bài nhắc là nhiễu, không phải "nổi bật"
TOP_BAI = 20


# ───────────────────────── tiện ích ─────────────────────────
def so(v) -> int:
    try:
        return max(0, int(float(v or 0)))
    except (TypeError, ValueError):
        return 0


def ngay_vn(dt) -> datetime.date | None:
    """datetime có múi giờ -> ngày giờ VN. datetime KHÔNG múi giờ coi là UTC (psycopg luôn trả
    timestamptz có múi giờ; nhánh này chỉ để dữ liệu lạ không làm lệch ngày âm thầm)."""
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(VN).date()
    if isinstance(dt, datetime.date):
        return dt
    return None


def thao_luan(r: dict) -> int:
    return 1 + so(r.get("binh_luan"))


def sac(r: dict) -> str:
    s = r.get("sac_thai")
    return s if s in SAC_THAI else CHUA


def loai(r: dict) -> str:
    if r.get("nguon_id") is None:
        return KHONG_NGUON
    return r.get("nguon_loai") or "khac"


def la_kenh_nha(r: dict) -> bool:
    return loai(r) == "kenh_nha"


def khoang_truoc(tu: datetime.date, den: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Kỳ liền trước cùng độ dài: 01–30/09 -> 02/08–31/08."""
    n = (den - tu).days + 1
    return tu - datetime.timedelta(days=n), tu - datetime.timedelta(days=1)


def _bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _khoa_nguon(r: dict) -> tuple:
    """Nguồn của bài: nguồn theo dõi (id) nếu có; bài tìm theo từ khoá thì theo tài khoản
    đăng (handle, rồi tên), để "nguồn có bài" đếm đúng số tác giả như Kompa."""
    if r.get("nguon_id") is not None:
        return ("n", r["nguon_id"])
    for k in ("tai_khoan", "tac_gia"):
        x = re.sub(r"\s+", " ", _bo_dau(r.get(k) or "")).strip().lstrip("@")
        if x:
            return (r.get("nen_tang") or "?", x)
    return ("link", r.get("link") or "")


# ───────────────────────── lọc + chia kỳ ─────────────────────────
def loc(rows: list[dict], nen_tang: str | None = None, loai_nguon: str | None = None) -> list[dict]:
    return [r for r in rows
            if (not nen_tang or r.get("nen_tang") == nen_tang)
            and (not loai_nguon or loai(r) == loai_nguon)]


def trong_khoang(rows: list[dict], tu: datetime.date, den: datetime.date) -> list[dict]:
    ra = []
    for r in rows:
        n = ngay_vn(r.get("dang_luc"))
        if n is not None and tu <= n <= den:
            ra.append(r)
    return ra


# ───────────────────────── KPI + so sánh ─────────────────────────
def kpi(rows: list[dict]) -> dict:
    khach = [r for r in rows if not la_kenh_nha(r)]
    dem = collections.Counter(sac(r) for r in khach)
    da = sum(dem[s] for s in SAC_THAI)
    bl = sum(so(r.get("binh_luan")) for r in rows)

    def pt(s: str) -> float | None:
        return round(100.0 * dem[s] / da, 1) if da else None
    return {
        "bai": len(rows), "binh_luan": bl, "thao_luan": len(rows) + bl,
        "xem": sum(so(r.get("xem")) for r in rows),
        "tuong_tac": sum(so(r.get("thich")) + so(r.get("binh_luan")) + so(r.get("chia_se"))
                         for r in rows),
        "nguon_co_bai": len({_khoa_nguon(r) for r in rows}),
        # Đợt 2d: bài cùng nội dung (đăng lại nhiều trang/seeding) đếm một lần.
        "bai_khu_trung": len({r.get("ma_noi_dung") or ("k", r.get("khoa") or id(r)) for r in rows}),
        "bl_da_cao": sum(so(r.get("bl_da_lay")) for r in rows),
        "bl_nen_tang_bao_bai_da_cao": sum(so(r.get("binh_luan")) for r in rows
                                          if r.get("bl_da_lay") is not None),
        "bai_kenh_nha": len(rows) - len(khach),
        "da_phan_loai": da, "chua_phan_loai": len(khach) - da,
        "tich_cuc": dem[TC], "tieu_cuc": dem[TI], "trung_lap": dem[TL],
        "tich_cuc_pt": pt(TC), "tieu_cuc_pt": pt(TI), "trung_lap_pt": pt(TL),
    }


def doi_pt(nay: float, truoc: float) -> float | None:
    return round(100.0 * (nay - truoc) / truoc, 1) if truoc else None


def so_sanh(nay: dict, truoc: dict) -> dict:
    return {k: {"nay": nay[k], "truoc": truoc[k], "doi_pt": doi_pt(nay[k], truoc[k])}
            for k in ("bai", "thao_luan", "binh_luan", "nguon_co_bai", "xem", "tuong_tac")}


# ───────────────────────── xu hướng ─────────────────────────
def _cac_moc(tu: datetime.date, cuoi: datetime.date, theo_tuan: bool) -> list[datetime.date]:
    moc, n = [], tu
    while n <= cuoi:
        m = max(tu, n - datetime.timedelta(days=n.weekday())) if theo_tuan else n
        if not moc or moc[-1] != m:
            moc.append(m)
        n += datetime.timedelta(days=1)
    return moc


def xu_huong(rows: list[dict], tu: datetime.date, den: datetime.date,
             hom_nay: datetime.date) -> dict:
    """Đếm theo NGÀY đăng (giờ VN), đủ mọi ngày kể cả ngày 0 bài. Khoảng dài hơn
    `NGAY_TOI_DA_THEO_NGAY` ngày thì theo TUẦN (mốc = thứ Hai, mốc đầu kẹp vào `tu`). Ngày cuối
    kẹp về hôm nay: chọn "tới cuối tháng" giữa tháng thì không vẽ nửa tháng 0 bài giả."""
    theo_tuan = (den - tu).days + 1 > NGAY_TOI_DA_THEO_NGAY
    cuoi = max(tu, min(den, hom_nay))
    moc = _cac_moc(tu, cuoi, theo_tuan)
    chi_so = {m: i for i, m in enumerate(moc)}
    ten = ("bai", "binh_luan", "thao_luan", "tich_cuc", "tieu_cuc", "trung_lap",
           "chua_phan_loai", "kenh_nha")
    cot = {k: [0] * len(moc) for k in ten}
    khoa_sac = {TC: "tich_cuc", TI: "tieu_cuc", TL: "trung_lap", CHUA: "chua_phan_loai"}
    for r in rows:
        n = ngay_vn(r.get("dang_luc"))
        if n is None or not tu <= n <= cuoi:
            continue
        m = max(tu, n - datetime.timedelta(days=n.weekday())) if theo_tuan else n
        i = chi_so[m]
        cot["bai"][i] += 1
        cot["binh_luan"][i] += so(r.get("binh_luan"))
        cot["thao_luan"][i] += thao_luan(r)
        cot["kenh_nha" if la_kenh_nha(r) else khoa_sac[sac(r)]][i] += 1
    dinh = None
    if moc and max(cot["thao_luan"]) > 0:
        i = max(range(len(moc)), key=lambda j: (cot["thao_luan"][j], -j))
        dinh = {"moc": moc[i].isoformat(), "thao_luan": cot["thao_luan"][i], "bai": cot["bai"][i]}
    return {"don_vi": "tuần" if theo_tuan else "ngày", "moc": [m.isoformat() for m in moc],
            **cot, "dinh": dinh}


# ───────────────────────── sắc thái, chủ đề, phân bố ─────────────────────────
def sac_thai(rows: list[dict]) -> list[dict]:
    dem = collections.Counter(sac(r) for r in rows if not la_kenh_nha(r))
    return [{"sac_thai": s, "so": dem[s]} for s in (*SAC_THAI, CHUA)]


def sac_thai_chu_de(rows: list[dict]) -> list[dict]:
    """Chủ đề × sắc thái trên bài KHÔNG của kênh nhà. Nhiều bài trước, "chưa phân loại" cuối."""
    dem: dict[str, dict] = {}
    for r in rows:
        if la_kenh_nha(r):
            continue
        c = str(r.get("chu_de") or "").strip() or CHUA
        g = dem.setdefault(c, {"chu_de": c, "so": 0, TC: 0, TI: 0, TL: 0, CHUA: 0})
        g["so"] += 1
        g[sac(r)] += 1
    return sorted(dem.values(), key=lambda g: (g["chu_de"] == CHUA, -g["so"], g["chu_de"]))


def _phan_bo(rows: list[dict], khoa) -> dict[str, dict]:
    gom: dict[str, dict] = {}
    for r in rows:
        k = khoa(r)
        g = gom.setdefault(k, {"bai": 0, "binh_luan": 0, "thao_luan": 0, "xem": 0})
        g["bai"] += 1
        g["binh_luan"] += so(r.get("binh_luan"))
        g["thao_luan"] += thao_luan(r)
        g["xem"] += so(r.get("xem"))
    return gom


def phan_bo_nen_tang(rows: list[dict]) -> list[dict]:
    gom = _phan_bo(rows, lambda r: r.get("nen_tang") or "?")
    return [{"nen_tang": p, "ten": TEN_NEN_TANG.get(p, p), **g}
            for p, g in sorted(gom.items(), key=lambda x: (-x[1]["thao_luan"], x[0]))]


def phan_bo_loai(rows: list[dict]) -> list[dict]:
    gom = _phan_bo(rows, loai)
    return [{"loai": k, "ten": TEN_LOAI.get(k, k), **g}
            for k, g in sorted(gom.items(), key=lambda x: (-x[1]["thao_luan"], x[0]))]


# ───────────────────────── nguồn + bài nổi bật ─────────────────────────
def top_nguon(rows: list[dict], toi_da: int = TOP_NGUON) -> list[dict]:
    """Top `toi_da` nguồn MỖI nền tảng theo thảo luận (hoà thì số bài, rồi lượt xem). Nền tảng
    xếp theo tổng thảo luận giảm dần. -> [{nen_tang, ten_nen_tang, so_nguon, nguon: [...]}]."""
    gom: dict[tuple, dict] = {}
    for r in rows:
        k = (r.get("nen_tang") or "?", _khoa_nguon(r))
        g = gom.get(k)
        if g is None:
            g = gom[k] = {
                "ten": r.get("nguon_ten") or r.get("tac_gia") or r.get("tai_khoan") or "?",
                "dinh_danh": r.get("nguon_dinh_danh") or r.get("tai_khoan") or "",
                "loai": loai(r), "ten_loai": TEN_LOAI.get(loai(r), loai(r)),
                "khoa_nguon": khoa_nguon_chu(r),
                "link": r.get("nguon_link") or "", "bai": 0, "binh_luan": 0, "thao_luan": 0,
                "xem": 0, "followers": 0}
        g["bai"] += 1
        g["binh_luan"] += so(r.get("binh_luan"))
        g["thao_luan"] += thao_luan(r)
        g["xem"] += so(r.get("xem"))
        g["followers"] = max(g["followers"], so(r.get("followers")))
    theo: dict[str, list] = collections.defaultdict(list)
    for (p, _), g in gom.items():
        theo[p].append(g)
    tong = {p: sum(g["thao_luan"] for g in ds) for p, ds in theo.items()}
    ra = []
    for p in sorted(theo, key=lambda p: (-tong[p], p)):
        ds = sorted(theo[p], key=lambda g: (-g["thao_luan"], -g["bai"], -g["xem"], g["ten"]))
        ra.append({"nen_tang": p, "ten_nen_tang": TEN_NEN_TANG.get(p, p),
                   "so_nguon": len(ds), "nguon": ds[:toi_da]})
    return ra


def khoa_nguon_chu(r: dict) -> str:
    """Khoá nguồn (`_khoa_nguon`) dạng chuỗi để trình duyệt gửi lại khi bấm vào một nguồn."""
    k = _khoa_nguon(r)
    return f"{k[0]}:{k[1]}"


def _the_bai(r: dict) -> dict:
    dt = r.get("dang_luc")
    return {
        "khoa": r.get("khoa") or "", "bl_da_lay": so(r.get("bl_da_lay")),
        "link": r.get("link") or "", "nen_tang": r.get("nen_tang") or "",
        "tac_gia": r.get("tac_gia") or r.get("tai_khoan") or "",
        "dang_luc": (dt.astimezone(VN).isoformat(timespec="minutes")
                     if isinstance(dt, datetime.datetime) and dt.tzinfo else None),
        "noi_dung": " ".join(str(r.get("noi_dung") or "").split())[:500],
        "sac_thai": "kênh nhà" if la_kenh_nha(r) else sac(r),
        "chu_de": r.get("chu_de") or "", "loai": TEN_LOAI.get(loai(r), loai(r)),
        "xem": so(r.get("xem")), "thich": so(r.get("thich")),
        "binh_luan": so(r.get("binh_luan")), "chia_se": so(r.get("chia_se")),
        "thao_luan": thao_luan(r)}


def top_bai(rows: list[dict], toi_da: int = TOP_BAI) -> list[dict]:
    ds = sorted(rows, key=lambda r: (-thao_luan(r), -so(r.get("xem")), str(r.get("link") or "")))
    ra = []
    for r in ds[:toi_da]:
        dt = r.get("dang_luc")
        ra.append({
            "khoa": r.get("khoa") or "", "bl_da_lay": so(r.get("bl_da_lay")),
            "link": r.get("link") or "", "nen_tang": r.get("nen_tang") or "",
            "tac_gia": r.get("tac_gia") or r.get("tai_khoan") or "",
            "dang_luc": (dt.astimezone(VN).isoformat(timespec="minutes")
                         if isinstance(dt, datetime.datetime) and dt.tzinfo else None),
            "noi_dung": " ".join(str(r.get("noi_dung") or "").split())[:200],
            "sac_thai": "kênh nhà" if la_kenh_nha(r) else sac(r),
            "chu_de": r.get("chu_de") or "", "loai": TEN_LOAI.get(loai(r), loai(r)),
            "xem": so(r.get("xem")), "thich": so(r.get("thich")),
            "binh_luan": so(r.get("binh_luan")), "chia_se": so(r.get("chia_se")),
            "thao_luan": thao_luan(r)})
    return ra


# ───────────────────────── từ khoá nổi bật ─────────────────────────
# Hư từ / đại từ / từ đệm hay gặp trên MXH Việt + tiếng Anh (chép từ `tong_hop_lang_nghe._STOP`
# — dashboard không import module của Mark). Cụm hai chữ có một chữ ở đây thì bỏ: "rất đẹp",
# "của hàng" không phải từ khoá. Cố ý ngắn; thiếu vài từ chỉ làm lọt cụm vô nghĩa ở cuối bảng.
_STOP_CHU = """
và của là có cho với các những một này đó thì mà được đã đang sẽ không chưa cũng rất quá
lắm nhé nha ạ à ơi nhỉ vậy thế như để khi từ trong ngoài trên dưới ra vào lên xuống đi
đến tới về theo bị vì nên nếu hay hoặc còn nữa rồi mình bạn tôi tui tớ em anh chị ai gì
nào đâu sao bao nhiêu thôi luôn ngay lại đây kia ấy nhiều ít hơn nhất mỗi mọi cả tất chỉ
vẫn đều chứ nhưng tại bởi do qua giữa sau trước cùng hết ở nó họ chúng ta mấy cái con
người thấy làm biết muốn cần phải đều vừa mới xong đúng đó đấy nè nhá hả ha hihi haha
hehe kk ok oke uh ừ vâng dạ ko k hok hông khum dc đc dk j r vs ib inbox link bio rep cmt
check xem nhé nhaa luôn thì là lúc giờ hôm nay mai qua năm tháng ngày tuần
the a an and or of to in on for with is are was were be been my your our their i you
he she it we they this that these those at by from as so if not no yes me us them its
just very really all any can will would should do does did have has had get got more
"""
_STOP = set(_STOP_CHU.split())
# Hashtag "đẩy đề xuất" ai cũng gắn, không nói gì về brand.
_HASHTAG_CHUNG = {"fyp", "foryou", "foryoupage", "xuhuong", "xuhướng", "viral", "trending",
                  "trend", "tiktok", "reels", "reel", "capcut", "fypシ", "fy", "explore",
                  "viralvideo", "tiktokvietnam", "vairal", "thinhhanh", "learnontiktok"}
_RE_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_RE_TAG_NGUOI = re.compile(r"@[\w.\-]+")
_RE_HASHTAG = re.compile(r"#(\w+)")
_RE_DOAN = re.compile(r"[^\w\s]+|\d+|_+")


def _cum(r: dict) -> set[str]:
    """Các cụm của MỘT bài: hashtag ('#tên', từ cột `hashtag` nối bằng dấu phẩy và từ nội
    dung) + cặp chữ liền nhau không vượt dấu câu/số, không chứa hư từ. Mỗi cụm một lần/bài."""
    text = unicodedata.normalize("NFC", str(r.get("noi_dung") or "")).lower()
    text = _RE_TAG_NGUOI.sub(" ", _RE_URL.sub(" ", text))
    tags = set(_RE_HASHTAG.findall(text))
    # Thẻ YouTube có thể nhiều chữ ("túi xách nữ"): tách theo khoảng trắng sẽ ra hashtag giả —
    # chỉ tách theo dấu phẩy/chấm phẩy/#, bỏ thẻ có khoảng trắng.
    hs = unicodedata.normalize("NFC", str(r.get("hashtag") or "")).lower()
    tags |= {t.strip() for t in re.split(r"[,;#]+", hs) if t.strip() and not re.search(r"\s", t.strip())}
    ra = {"#" + t for t in tags if len(t) >= 3 and not t.isdigit() and t not in _HASHTAG_CHUNG}
    text = _RE_HASHTAG.sub(" ", text)
    for doan in _RE_DOAN.split(text):
        chu = doan.split()
        for a, b in itertools.pairwise(chu):          # cặp chữ liền nhau
            if (a != b and len(a) >= 2 and len(b) >= 2 and a.isalpha() and b.isalpha()
                    and a not in _STOP and b not in _STOP):
                ra.add(f"{a} {b}")
    return ra


def tu_khoa(rows: list[dict], tu_khoa_du_an: list[str] | tuple = (),
            toi_da: int = TOP_TU_KHOA) -> list[dict]:
    """Top cụm từ / hashtag theo SỐ BÀI nhắc (bài không của kênh nhà), bỏ cụm chứa chính từ
    khoá của dự án (theo dõi "hapas" thì "túi hapas", "#hapasvn" không phải phát hiện gì). So
    trên dạng bỏ dấu + bỏ khoảng trắng; từ khoá < 3 ký tự thì không dùng để bỏ."""
    bo = {x for x in (re.sub(r"[\s#]+", "", _bo_dau(q)) for q in tu_khoa_du_an) if len(x) >= 3}
    dem: dict[str, dict] = {}
    for r in rows:
        if la_kenh_nha(r):
            continue
        s = sac(r)
        for c in _cum(r):
            gon = re.sub(r"[\s#]+", "", _bo_dau(c))
            if any(b in gon for b in bo):
                continue
            g = dem.setdefault(c, {"tu": c, "so_bai": 0, TC: 0, TI: 0, TL: 0, CHUA: 0})
            g["so_bai"] += 1
            g[s] += 1
    ds = [g for g in dem.values() if g["so_bai"] >= TU_KHOA_TOI_THIEU_BAI]
    ds.sort(key=lambda g: (-g["so_bai"], g["tu"]))
    return ds[:toi_da]


# ───────────────────────── gộp ─────────────────────────
def tong_hop(rows: list[dict], tu: datetime.date, den: datetime.date, *,
             tu_khoa_du_an: list[str] | tuple = (), nen_tang: str | None = None,
             loai_nguon: str | None = None, hom_nay: datetime.date | None = None) -> dict:
    """Mọi khối của trang Chỉ số. `rows` gồm bài của CẢ kỳ này lẫn kỳ trước (kho đọc một lần
    từ đầu kỳ trước); hàm tự chia. -> dict thuần JSON (ngày dạng ISO)."""
    hom_nay = hom_nay or datetime.datetime.now(VN).date()
    rows = loc(rows, nen_tang, loai_nguon)
    tu_truoc, den_truoc = khoang_truoc(tu, den)
    nay = trong_khoang(rows, tu, den)
    truoc = trong_khoang(rows, tu_truoc, den_truoc)
    k_nay, k_truoc = kpi(nay), kpi(truoc)
    return {
        "khoang": {"tu": tu.isoformat(), "den": den.isoformat(),
                   "so_ngay": (den - tu).days + 1,
                   "ky_truoc": {"tu": tu_truoc.isoformat(), "den": den_truoc.isoformat()}},
        "kpi": k_nay, "kpi_truoc": k_truoc, "so_sanh": so_sanh(k_nay, k_truoc),
        "xu_huong": xu_huong(nay, tu, den, hom_nay),
        "sac_thai": sac_thai(nay), "sac_thai_chu_de": sac_thai_chu_de(nay),
        "nen_tang": phan_bo_nen_tang(nay), "loai_nguon": phan_bo_loai(nay),
        "top_nguon": top_nguon(nay), "tu_khoa": tu_khoa(nay, tu_khoa_du_an),
        "top_bai": top_bai(nay),
    }


# ───────────────────────── chi tiết: bấm vào biểu đồ (đợt 2b, 15/10/2026) ─────────────────────────
# Chủ dự án 15/10: bấm vào một điểm/cột phải ra đúng các bài (và bình luận) làm nên con số đó,
# như khung "5.768 thảo luận trong ngày …" của Kompa. Lọc trên CÙNG các dòng trang Chỉ số đã
# đếm (cùng bộ lọc dự án/khoảng/nền tảng/loại nguồn) nên tổng khung chi tiết khớp con số đã bấm.
MOI_TRANG = 20
SAC_BL = (TC, TI, TL)


def _khop(r: dict, ngay: datetime.date | None, *, kenh_nha: bool, ngay_tu=None, ngay_den=None,
          sac_thai=None, chu_de=None, nen_tang=None, loai_nguon=None, nguon=None,
          cum=None) -> bool:
    if ngay_tu and (ngay is None or ngay < ngay_tu):
        return False
    if ngay_den and (ngay is None or ngay > ngay_den):
        return False
    if nen_tang and r.get("nen_tang") != nen_tang:
        return False
    if loai_nguon and loai(r) != loai_nguon:
        return False
    if nguon and khoa_nguon_chu(r) != nguon:
        return False
    if sac_thai:
        if sac_thai == "kênh nhà":
            if not kenh_nha:
                return False
        elif kenh_nha or sac(r) != sac_thai:
            return False
    if chu_de and (kenh_nha or (str(r.get("chu_de") or "").strip() or CHUA) != chu_de):
        return False
    return not (cum and (kenh_nha or cum not in _cum(r)))


def _trang(ds: list, trang: int, moi_trang: int = MOI_TRANG) -> tuple[list, int, int]:
    so_trang = max(1, -(-len(ds) // moi_trang))
    trang = max(1, min(int(trang or 1), so_trang))
    return ds[(trang - 1) * moi_trang: trang * moi_trang], trang, so_trang


def chi_tiet_bai(rows: list[dict], tu: datetime.date, den: datetime.date, *,
                 trang: int = 1, **dk) -> dict:
    """Bài trong [tu, den] khớp điều kiện `dk` (ngay_tu, ngay_den, sac_thai, chu_de, nen_tang,
    loai_nguon, nguon, cum), nhiều thảo luận trước. -> {tong, thao_luan, trang, so_trang, bai}."""
    ds = [r for r in trong_khoang(rows, tu, den)
          if _khop(r, ngay_vn(r.get("dang_luc")), kenh_nha=la_kenh_nha(r), **dk)]
    ds.sort(key=lambda r: (-thao_luan(r), -so(r.get("xem")), str(r.get("link") or "")))
    tl = sum(thao_luan(r) for r in ds)
    mot, trang, so_trang = _trang(ds, trang)
    return {"tong": len(ds), "thao_luan": tl, "trang": trang, "so_trang": so_trang,
            "bai": [_the_bai(r) for r in mot]}


# ───────────────────────── bình luận đã cào ─────────────────────────
def sac_bl(c: dict) -> str:
    s = c.get("sac_thai")
    return s if s in SAC_BL else CHUA


def _ngay_bl(c: dict) -> datetime.date | None:
    return ngay_vn(c.get("luc") or c.get("dang_luc"))


# Bản sao `loc_rac.LOAI` / `TEN_LOAI` của Mark (dashboard cài riêng, không import module Mark —
# bài thử đối chiếu). Chỉ `hop_le` vào thảo luận sạch + sắc thái.
LOAI_BL = ("hop_le", "it_noi_dung", "spam", "trung", "seeding", "thuong_hieu")
TEN_LOAI_BL = {"hop_le": "Hợp lệ", "it_noi_dung": "Ít nội dung", "spam": "Spam",
               "trung": "Trùng lặp", "seeding": "Seeding", "thuong_hieu": "Thương hiệu"}


def loai_bl(c: dict) -> str:
    x = c.get("loai")
    if x in LOAI_BL:
        return x
    return "thuong_hieu" if c.get("cua_thuong_hieu") else "hop_le"


def the_bl(c: dict) -> dict:
    dt = c.get("dang_luc")
    lb = loai_bl(c)
    return {"tac_gia": c.get("tac_gia") or "", "noi_dung": str(c.get("noi_dung") or "")[:1000],
            "thich": so(c.get("thich")), "tra_loi": so(c.get("tra_loi")),
            "la_tra_loi": bool(c.get("la_tra_loi")),
            "cua_thuong_hieu": bool(c.get("cua_thuong_hieu")),
            "dang_luc": (dt.astimezone(VN).isoformat(timespec="minutes")
                         if isinstance(dt, datetime.datetime) and dt.tzinfo else None),
            "sac_thai": sac_bl(c) if lb == "hop_le" else TEN_LOAI_BL[lb].lower(),
            "chu_de": c.get("chu_de") or "", "khoa_bai": c.get("khoa_bai") or "",
            "nen_tang": c.get("nen_tang") or "", "loai": lb, "ten_loai": TEN_LOAI_BL[lb],
            "ly_do_loc": c.get("ly_do_loc") or ""}


def tong_hop_bl(rows: list[dict], tu: datetime.date, den: datetime.date, *,
                nen_tang: str | None = None, loai_nguon: str | None = None,
                hom_nay: datetime.date | None = None) -> dict:
    """Bình luận đã cào trong kỳ: số, sắc thái (chỉ của khách), xu hướng, chủ đề × sắc thái.
    Đây là MẪU bình luận Mark đọc được, không phải toàn bộ bình luận nền tảng báo."""
    hom_nay = hom_nay or datetime.datetime.now(VN).date()
    rows = [c for c in loc(rows, nen_tang, loai_nguon)
            if (n := _ngay_bl(c)) is not None and tu <= n <= den]
    theo_loai = collections.Counter(loai_bl(c) for c in rows)
    # Chỉ bình luận HỢP LỆ (đã lọc spam/rác/trùng/seeding/thương hiệu) vào sắc thái, chủ đề.
    khach = [c for c in rows if loai_bl(c) == "hop_le"]
    dem = collections.Counter(sac_bl(c) for c in khach)
    da = sum(dem[s] for s in SAC_BL)
    theo_tuan = (den - tu).days + 1 > NGAY_TOI_DA_THEO_NGAY
    cuoi = max(tu, min(den, hom_nay))
    moc = _cac_moc(tu, cuoi, theo_tuan)
    chi = {m: i for i, m in enumerate(moc)}
    cot = {k: [0] * len(moc) for k in ("tich_cuc", "tieu_cuc", "trung_lap", "chua_phan_loai")}
    khoa = {TC: "tich_cuc", TI: "tieu_cuc", TL: "trung_lap", CHUA: "chua_phan_loai"}
    cd: dict[str, dict] = {}
    for c in khach:
        n = _ngay_bl(c)
        if n <= cuoi:
            m = max(tu, n - datetime.timedelta(days=n.weekday())) if theo_tuan else n
            cot[khoa[sac_bl(c)]][chi[m]] += 1
        t = str(c.get("chu_de") or "").strip() or CHUA
        g = cd.setdefault(t, {"chu_de": t, "so": 0, TC: 0, TI: 0, TL: 0, CHUA: 0})
        g["so"] += 1
        g[sac_bl(c)] += 1

    def pt(x: str) -> float | None:
        return round(100.0 * dem[x] / da, 1) if da else None
    return {
        "loai": [{"loai": k, "ten": TEN_LOAI_BL[k], "so": theo_loai[k]} for k in LOAI_BL
                 if theo_loai[k]],
        "kpi": {"so": len(rows), "khach": len(khach), "sach": len(khach),
                "da_loc": len(rows) - len(khach) - theo_loai["thuong_hieu"],
                "thuong_hieu": theo_loai["thuong_hieu"],
                "so_bai": len({c.get("khoa_bai") for c in rows}), "da_phan_loai": da,
                "tich_cuc": dem[TC], "tieu_cuc": dem[TI], "trung_lap": dem[TL],
                "chua_phan_loai": dem[CHUA], "tich_cuc_pt": pt(TC), "tieu_cuc_pt": pt(TI),
                "trung_lap_pt": pt(TL)},
        "xu_huong": {"don_vi": "tuần" if theo_tuan else "ngày",
                     "moc": [m.isoformat() for m in moc], **cot},
        "chu_de": sorted(cd.values(), key=lambda g: (g["chu_de"] == CHUA, -g["so"], g["chu_de"])),
    }


def chi_tiet_bl(rows: list[dict], tu: datetime.date, den: datetime.date, *,
                trang: int = 1, ngay_tu=None, ngay_den=None, sac_thai=None, chu_de=None,
                nen_tang=None, loai_nguon=None, loai=None) -> dict:
    """Bình luận khớp điều kiện (sắc thái/chủ đề chỉ xét bình luận của khách), nhiều thích
    trước. -> {tong, trang, so_trang, binh_luan}."""
    ds = []
    for c in loc(rows, nen_tang, loai_nguon):
        n = _ngay_bl(c)
        if n is None or not tu <= n <= den:
            continue
        if (ngay_tu and n < ngay_tu) or (ngay_den and n > ngay_den):
            continue
        lb = loai_bl(c)
        if loai and lb != loai:
            continue
        sach = lb == "hop_le"
        if sac_thai and (not sach or sac_bl(c) != sac_thai):
            continue
        if chu_de and (not sach or (str(c.get("chu_de") or "").strip() or CHUA) != chu_de):
            continue
        ds.append(c)
    ds.sort(key=lambda c: (-so(c.get("thich")), str(c.get("khoa_bai") or "")))
    mot, trang, so_trang = _trang(ds, trang)
    return {"tong": len(ds), "trang": trang, "so_trang": so_trang,
            "binh_luan": [the_bl(c) for c in mot]}
