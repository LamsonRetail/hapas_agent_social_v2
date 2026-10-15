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


# ───────────────────────── bộ lọc chung (đợt 2f, 15/10/2026) ─────────────────────────
# Chủ dự án 15/10: "tôi muốn có thêm filter để lọc thông minh và các table sẽ liên kết với bộ lọc
# đó (gợi ý: lọc kênh nhà và listening bên ngoài…)". MỘT bộ lọc cho MỌI khối trang Chỉ số (KPI,
# biểu đồ, bảng, mây từ, chủ đề, nguồn, bài, bình luận, khung chi tiết) và cả kỳ trước. Các chiều
# AND với nhau; nhiều giá trị trong MỘT chiều là OR. Áp lên bài / bình luận như sau:
#   pham_vi    kenh_nha = nguồn loại `kenh_nha`; ben_ngoai = mọi thứ khác (kể cả bài tìm theo từ
#              khoá). Bình luận theo BÀI của nó (dòng bình luận mang sẵn nguồn của bài).
#   nen_tang, loai, nguon, anh_huong, tuong_tac, kieu_quet   cấp BÀI; bình luận theo bài của nó.
#   sac_thai   bài theo sắc thái BÀI (bài kênh nhà không mang tiếng khách → không khớp); bình luận
#              theo sắc thái của CHÍNH nó (chỉ bình luận hợp lệ có sắc thái).
#   chu_de     bài và bình luận có HAI bộ nhãn khác nhau (13 chủ đề bài, 7 chủ đề bình luận của
#              Mark). Mỗi nhãn lọc đúng loại mục mang nhãn đó: chọn toàn chủ đề bình luận thì phần
#              bài không bị lọc theo chủ đề (và ngược lại); "Khác", "chưa phân loại" lọc cả hai.
#   q          chữ tìm bỏ dấu: bài khớp khi nội dung + hashtag chứa chữ; bình luận khớp khi CHÍNH
#              nó chứa chữ HOẶC bài của nó khớp (thảo luận dưới bài nói về chữ đó).
CHIEU_LOC = ("pham_vi", "nen_tang", "loai", "nguon", "sac_thai", "chu_de", "anh_huong",
             "tuong_tac", "q", "kieu_quet")
_BIT = {k: 1 << i for i, k in enumerate(CHIEU_LOC)}
PHAM_VI = {"tat_ca": "Tất cả", "kenh_nha": "Kênh nhà", "ben_ngoai": "Bên ngoài"}
#: Mã sắc thái trên URL (gọn, không dấu) -> nhãn lưu trong kho.
MA_SAC = {"tich_cuc": TC, "tieu_cuc": TI, "trung_lap": TL, "chua_phan_loai": CHUA}
SAC_MA = {v: k for k, v in MA_SAC.items()}
#: Bậc ảnh hưởng theo followers của tài khoản đăng (mốc quen thuộc của nghề influencer).
ANH_HUONG = {"nano": "Nano · dưới 10N", "micro": "Micro · 10N–100N", "macro": "Macro · 100N–1Tr",
             "mega": "Mega · từ 1Tr", "khong_ro": "Không rõ follower"}
TUONG_TAC_MUC = (100, 1_000, 10_000)
KIEU_QUET = {"theo_doi": "Quét nguồn theo dõi", "tu_khoa": "Tìm theo từ khoá"}
# Bản sao nhãn chủ đề của Mark (`phan_loai.CHU_DE_BAI` / `phan_loai.CHU_DE`) — dashboard không
# import module của Mark; bài thử đối chiếu. Dùng để biết nhãn nào là của bài, nhãn nào của bình luận.
CHU_DE_BAI = ("Chiến dịch & quảng cáo", "Giá cả & khuyến mãi", "Chất lượng sản phẩm",
              "Hình ảnh & mẫu mã", "Trải nghiệm mua sắm", "Dịch vụ khách hàng", "Giao hàng",
              "So sánh thương hiệu", "Nguồn gốc & chính hãng", "Cửa hàng & vận hành",
              "Tuyển dụng", "Doanh nghiệp & truyền thông", "Khác")
CHU_DE_BL = ("Sản phẩm/chất lượng", "Giá/mua ở đâu/ý định mua", "KOL/nội dung",
             "Giao hàng/dịch vụ", "Đối thủ", "Tag bạn bè", "Khác")
_TOI_DA_GIA_TRI = {"nen_tang": 4, "loai": 7, "nguon": 50, "sac_thai": 4, "chu_de": 40,
                   "anh_huong": 5}
_RE_DAU_NGUON = re.compile(r"(n|t|link|\?|tiktok|facebook|instagram|youtube):")
#: Khoá nguồn dài nhất: "link:" + link bài (kho cắt 500 ký tự) — bài không có tác giả/tài khoản.
NGUON_TOI_DA_KY_TU = 520

#: Bộ lọc nhanh (chip trên trang) — DỮ LIỆU: thêm/bớt một mục ở đây là đủ, trang tự hiện. `loc`
#: dùng đúng tham số URL (bài thử kiểm từng mục đọc được bằng `doc_bo_loc`); `so_ngay` (tuỳ chọn)
#: đặt khoảng N ngày tính tới HÔM NAY. Bấm chip = thay toàn bộ bộ lọc (giữ ngày nếu không có so_ngay).
BO_LOC_NHANH = (
    {"ma": "kenh_nha", "ten": "Kênh nhà",
     "mo_ta": "Chỉ bài trên kênh của chính thương hiệu và bình luận khách dưới các bài đó.",
     "loc": {"pham_vi": "kenh_nha"}},
    {"ma": "ben_ngoai", "ten": "Listening bên ngoài",
     "mo_ta": "Mọi thứ ngoài kênh nhà: KOL, trang, nhóm, báo và bài Mark tìm theo từ khoá.",
     "loc": {"pham_vi": "ben_ngoai"}},
    {"ma": "kol", "ten": "KOL/KOC nói về thương hiệu",
     "mo_ta": "Bài của các nguồn KOL/KOC đang theo dõi (bên ngoài).",
     "loc": {"pham_vi": "ben_ngoai", "loai": "kol"}},
    {"ma": "khung_hoang", "ten": "Cảnh báo khủng hoảng",
     "mo_ta": "Tiêu cực trên bài có từ 1.000 tương tác — thứ lan nhanh nhất, kể cả trên kênh nhà.",
     "loc": {"sac_thai": "tieu_cuc", "tuong_tac": "1000"}},
    {"ma": "hoi_mua", "ten": "Khách hỏi mua",
     "mo_ta": "Bình luận hỏi giá / hỏi chỗ mua / muốn mua (chủ đề bình luận của Mark).",
     "loc": {"chu_de": "Giá/mua ở đâu/ý định mua"}},
    {"ma": "can_xu_ly", "ten": "Tiêu cực cần xử lý",
     "mo_ta": "Bình luận tiêu cực trên kênh nhà 7 ngày gần nhất (tính cả hôm nay) — cần trả lời.",
     "loc": {"pham_vi": "kenh_nha", "sac_thai": "tieu_cuc"}, "so_ngay": 7},
    {"ma": "lan_toa", "ten": "Lan toả mạnh", "mo_ta": "Bài có từ 10.000 tương tác.",
     "loc": {"tuong_tac": "10000"}},
    {"ma": "khen", "ten": "Khen từ bên ngoài",
     "mo_ta": "Bài bên ngoài tích cực — UGC để cảm ơn, xin đăng lại.",
     "loc": {"pham_vi": "ben_ngoai", "sac_thai": "tich_cuc"}},
    # Cả hai điều kiện: bài không gắn nguồn VÀ vào kho qua lượt tìm từ khoá — loại bài của nguồn
    # đã xoá (nguon_id NULL nhưng kieu_quet vẫn theo_doi), vốn là nguồn cũ chứ không phải mới.
    {"ma": "ngoai_theo_doi", "ten": "Ngoài danh sách theo dõi",
     "mo_ta": "Bài Mark tìm theo từ khoá từ tài khoản chưa theo dõi — nguồn mới nên xem.",
     "loc": {"loai": KHONG_NGUON, "kieu_quet": "tu_khoa"}},
)


class LoiBoLoc(ValueError):
    """Giá trị bộ lọc sai. Câu thông báo trả thẳng cho người dùng (API 400)."""


def muc_anh_huong(r: dict) -> str:
    """Bậc ảnh hưởng của tài khoản đăng bài. followers NULL hoặc 0 = không rõ: nhiều actor
    (Instagram, Facebook tìm từ khoá) ghi 0 khi KHÔNG trả follower, nên 0 không phải "nano"."""
    f = so(r.get("followers"))
    if f <= 0:
        return "khong_ro"
    return "mega" if f >= 1_000_000 else "macro" if f >= 100_000 else \
        "micro" if f >= 10_000 else "nano"


def tuong_tac_bai(r: dict) -> int:
    return so(r.get("thich")) + so(r.get("binh_luan")) + so(r.get("chia_se"))


def kieu_quet_bai(r: dict) -> str:
    """theo_doi | tu_khoa. Dòng không có cột (dữ liệu cũ) thì suy từ nguồn."""
    x = r.get("kieu_quet")
    if x in KIEU_QUET:
        return x
    return KHONG_NGUON if r.get("nguon_id") is None else "theo_doi"


def nhom_chu_de(cd: str) -> str:
    """Nhãn chủ đề thuộc bài ("bai"), bình luận ("bl") hay cả hai ("chung"). Nhãn lạ (nhãn bài
    cũ — bộ nhãn bình luận của Mark cố định) coi là của bài."""
    if cd == CHUA or (cd in CHU_DE_BAI and cd in CHU_DE_BL):
        return "chung"
    return "bl" if cd in CHU_DE_BL else "bai"


def _chu_de(r: dict) -> str:
    return str(r.get("chu_de") or "").strip() or CHUA


def _tach_nguon(s: str) -> list[str]:
    """Khoá nguồn cách nhau bằng dấu phẩy; tên tác giả có dấu phẩy thì mảnh sau không bắt đầu
    bằng tiền tố khoá (n:, tiktok:, link:…) — ghép lại vào khoá trước."""
    ra: list[str] = []
    for p in str(s or "").split(","):
        if ra and not _RE_DAU_NGUON.match(p.strip()):
            ra[-1] += "," + p
        elif p.strip():
            ra.append(p.strip())
    return ra


def doc_bo_loc(q) -> dict:
    """Tham số URL (`q.get(tên)` -> chuỗi) -> bộ lọc chuẩn: chiều nhiều giá trị là tuple đã sắp
    (dùng thẳng làm khoá bộ nhớ đệm). Nhiều giá trị cách nhau bằng dấu phẩy; `nen_tang` / `loai`
    một giá trị kiểu cũ vẫn đọc được. Sai -> LoiBoLoc."""
    def nhieu(k: str, hop_le=None) -> tuple:
        ds = _tach_nguon(q.get(k)) if k == "nguon" else \
            [x.strip() for x in str(q.get(k) or "").split(",") if x.strip()]
        ds = list(dict.fromkeys(ds))
        if len(ds) > _TOI_DA_GIA_TRI[k]:
            raise LoiBoLoc(f"Bộ lọc “{k}”: chọn tối đa {_TOI_DA_GIA_TRI[k]} giá trị.")
        dai = NGUON_TOI_DA_KY_TU if k == "nguon" else 300
        for x in ds:
            if (hop_le is not None and x not in hop_le) or len(x) > dai:
                raise LoiBoLoc("Bộ lọc không hợp lệ.")
        return tuple(sorted(ds))

    pv = str(q.get("pham_vi") or "tat_ca")
    if pv not in PHAM_VI:
        raise LoiBoLoc("Bộ lọc không hợp lệ.")
    sac_ds = []
    for x in nhieu("sac_thai", (*MA_SAC, *MA_SAC.values())):
        sac_ds.append(MA_SAC.get(x, x))
    chu_de = nhieu("chu_de")
    if any(len(x) > 100 for x in chu_de):
        raise LoiBoLoc("Chủ đề quá dài.")
    tt = str(q.get("tuong_tac") or "").replace(".", "").strip()
    if tt and tt not in {str(m) for m in TUONG_TAC_MUC}:
        raise LoiBoLoc("Mức tương tác không hợp lệ.")
    tim = " ".join(str(q.get("q") or "").split())
    if len(tim) > 100:
        raise LoiBoLoc("Chữ tìm tối đa 100 ký tự.")
    kq = str(q.get("kieu_quet") or "")
    if kq and kq not in KIEU_QUET:
        raise LoiBoLoc("Bộ lọc không hợp lệ.")
    return {"pham_vi": pv, "nen_tang": nhieu("nen_tang", TEN_NEN_TANG),
            "loai": nhieu("loai", TEN_LOAI), "nguon": nhieu("nguon"),
            "sac_thai": tuple(sorted(set(sac_ds))), "chu_de": chu_de,
            "anh_huong": nhieu("anh_huong", ANH_HUONG), "tuong_tac": int(tt) if tt else 0,
            "q": tim, "kieu_quet": kq}


def khoa_bo_loc(bo_loc: dict | None) -> tuple:
    """Khoá băm được (bộ nhớ đệm /api/chi-so)."""
    b = bo_loc or {}
    return tuple((k, b.get(k)) for k in CHIEU_LOC)


def bo_loc_json(bo_loc: dict | None) -> dict:
    """Bộ lọc cho trình duyệt: danh sách thay tuple, sắc thái dạng mã URL."""
    b = doc_bo_loc({}) | dict(bo_loc or {})
    ra = {k: ([SAC_MA.get(x, x) for x in b[k]] if k == "sac_thai" else
              list(b[k]) if isinstance(b[k], tuple) else b[k]) for k in CHIEU_LOC}
    ra["tuong_tac"] = str(b["tuong_tac"]) if b["tuong_tac"] else ""     # giống tham số URL
    return ra


def _gop(bo_loc, nen_tang: str | None = None, loai_nguon: str | None = None):
    """Bộ lọc + hai tham số một giá trị kiểu cũ (`nen_tang`, `loai_nguon`) của các hàm tổng hợp.
    Không có tham số cũ thì trả nguyên `bo_loc` (có thể là `_Loc` đã dịch)."""
    if not (nen_tang or loai_nguon):
        return bo_loc
    b = dict(bo_loc or {})
    if nen_tang:
        b["nen_tang"] = (nen_tang,)
    if loai_nguon:
        b["loai"] = (loai_nguon,)
    return b


class _Loc:
    """Bộ lọc đã "dịch" sẵn cho vòng lặp: mỗi dòng -> mặt nạ bit các chiều TRƯỢT (0 = khớp)."""

    def __init__(self, bo_loc: dict | None):
        b = bo_loc or {}
        self.pv = b.get("pham_vi") or "tat_ca"
        self.nt, self.lo, self.ng = (set(b.get(k) or ()) for k in ("nen_tang", "loai", "nguon"))
        self.sac = set(b.get("sac_thai") or ())
        cd = set(b.get("chu_de") or ())
        self.cd_bai = {x for x in cd if nhom_chu_de(x) != "bl"}
        self.cd_bl = {x for x in cd if nhom_chu_de(x) != "bai"}
        self.ah = set(b.get("anh_huong") or ())
        self.tt = int(b.get("tuong_tac") or 0)
        self.kq = b.get("kieu_quet") or ""
        self.q = " ".join(_bo_dau(b.get("q") or "").split())
        self._q_bai: dict[int, bool] = {}
        self.rong = not (self.pv != "tat_ca" or self.nt or self.lo or self.ng or self.sac or cd
                         or self.ah or self.tt or self.kq or self.q)
        # Bình luận cần tra BÀI gốc khi lọc theo thứ dòng bình luận không mang.
        self.can_bai = bool(self.ah or self.tt or self.kq or self.q or
                            any(not k.startswith("n:") for k in self.ng))

    def _chu(self, s) -> bool:
        return self.q in " ".join(_bo_dau(s).split())

    def khop_q_bai(self, r: dict) -> bool:
        k = id(r)                          # dòng sống suốt lượt tính: nhớ để khỏi bỏ dấu lại
        x = self._q_bai.get(k)
        if x is None:
            x = self._q_bai[k] = self._chu(f"{r.get('noi_dung') or ''} {r.get('hashtag') or ''}")
        return x

    def _pham_vi(self, kn: bool) -> bool:
        return self.pv == "tat_ca" or (self.pv == "kenh_nha") == kn

    def hong_bai(self, r: dict) -> int:
        if self.rong:
            return 0
        m, kn = 0, la_kenh_nha(r)
        if not self._pham_vi(kn):
            m |= _BIT["pham_vi"]
        if self.nt and r.get("nen_tang") not in self.nt:
            m |= _BIT["nen_tang"]
        if self.lo and loai(r) not in self.lo:
            m |= _BIT["loai"]
        if self.ng and khoa_nguon_chu(r) not in self.ng:
            m |= _BIT["nguon"]
        if self.sac and (kn or sac(r) not in self.sac):
            m |= _BIT["sac_thai"]
        if self.cd_bai and (kn or _chu_de(r) not in self.cd_bai):
            m |= _BIT["chu_de"]
        if self.ah and muc_anh_huong(r) not in self.ah:
            m |= _BIT["anh_huong"]
        if self.tt and tuong_tac_bai(r) < self.tt:
            m |= _BIT["tuong_tac"]
        if self.q and not self.khop_q_bai(r):
            m |= _BIT["q"]
        if self.kq and kieu_quet_bai(r) != self.kq:
            m |= _BIT["kieu_quet"]
        return m

    def hong_bl(self, c: dict, bai: dict | None = None) -> int:
        """Như `hong_bai` cho MỘT bình luận; `bai` = dòng bài gốc (cần khi `can_bai`; thiếu bài
        thì các chiều cấp bài coi như trượt — không đoán)."""
        if self.rong:
            return 0
        m, kn = 0, la_kenh_nha(c)
        if not self._pham_vi(kn):
            m |= _BIT["pham_vi"]
        if self.nt and c.get("nen_tang") not in self.nt:
            m |= _BIT["nen_tang"]
        if self.lo and loai(c) not in self.lo:
            m |= _BIT["loai"]
        if self.ng:
            k = f"n:{c['nguon_id']}" if c.get("nguon_id") is not None else \
                (khoa_nguon_chu(bai) if bai else None)
            if k not in self.ng:
                m |= _BIT["nguon"]
        hop_le = loai_bl(c) == "hop_le"
        if self.sac and not (hop_le and sac_bl(c) in self.sac):
            m |= _BIT["sac_thai"]
        if self.cd_bl and not (hop_le and _chu_de(c) in self.cd_bl):
            m |= _BIT["chu_de"]
        if self.ah and (bai is None or muc_anh_huong(bai) not in self.ah):
            m |= _BIT["anh_huong"]
        if self.tt and (bai is None or tuong_tac_bai(bai) < self.tt):
            m |= _BIT["tuong_tac"]
        if self.q and not (self._chu(c.get("noi_dung")) or (bai is not None and self.khop_q_bai(bai))):
            m |= _BIT["q"]
        if self.kq and (bai is None or kieu_quet_bai(bai) != self.kq):
            m |= _BIT["kieu_quet"]
        return m


def bien_dich(bo_loc) -> _Loc:
    return bo_loc if isinstance(bo_loc, _Loc) else _Loc(bo_loc)


def can_tra_bai(bo_loc) -> bool:
    """Lọc bình luận theo bộ lọc này có cần dòng bài gốc không (app đọc bài thiếu theo khoá)."""
    return bien_dich(bo_loc).can_bai


def chi_muc_bai(rows: list[dict]) -> dict[str, dict]:
    return {r["khoa"]: r for r in rows if r.get("khoa")}


def khoa_bai_thieu(bl: list[dict], chi_muc: dict) -> list[str]:
    """Khoá bài của các bình luận mà `chi_muc` chưa có (bài đăng trước khoảng đã đọc)."""
    return list(dict.fromkeys(k for c in bl if (k := c.get("khoa_bai")) and k not in chi_muc))


def loc_bai(rows: list[dict], bo_loc=None) -> list[dict]:
    f = bien_dich(bo_loc)
    return rows if f.rong else [r for r in rows if not f.hong_bai(r)]


def loc_bl(rows: list[dict], bo_loc=None, bai_theo_khoa: dict | None = None) -> list[dict]:
    f = bien_dich(bo_loc)
    if f.rong:
        return rows
    tra = (bai_theo_khoa or {}).get
    return [c for c in rows if not f.hong_bl(c, tra(c.get("khoa_bai")))]


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
             loai_nguon: str | None = None, hom_nay: datetime.date | None = None,
             bo_loc=None) -> dict:
    """Mọi khối của trang Chỉ số. `rows` gồm bài của CẢ kỳ này lẫn kỳ trước (kho đọc một lần
    từ đầu kỳ trước); hàm tự chia. `bo_loc` (bộ lọc chung) áp cho CẢ hai kỳ — so sánh cùng một
    tập. -> dict thuần JSON (ngày dạng ISO)."""
    hom_nay = hom_nay or datetime.datetime.now(VN).date()
    f = bien_dich(_gop(bo_loc, nen_tang, loai_nguon))
    rows = loc_bai(rows, f)
    tu_truoc, den_truoc = khoang_truoc(tu, den)
    nay = trong_khoang(rows, tu, den)
    truoc = trong_khoang(rows, tu_truoc, den_truoc)
    k_nay, k_truoc = kpi(nay), kpi(truoc)
    ss = so_sanh(k_nay, k_truoc)
    # Tương tác là số CỘNG DỒN trọn đời bài: bài kỳ trước có thêm thời gian tích tương tác nên
    # lọc "từ N tương tác" ưu ái kỳ trước — % so sánh lệch, không hiện (`so_sanh_lech` nói lý do).
    lech = "tuong_tac" if f.tt else None
    if lech:
        for v in ss.values():
            v["doi_pt"] = None
    return {
        "khoang": {"tu": tu.isoformat(), "den": den.isoformat(),
                   "so_ngay": (den - tu).days + 1,
                   "ky_truoc": {"tu": tu_truoc.isoformat(), "den": den_truoc.isoformat()}},
        "kpi": k_nay, "kpi_truoc": k_truoc, "so_sanh": ss, "so_sanh_lech": lech,
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
                 trang: int = 1, bo_loc=None, **dk) -> dict:
    """Bài trong [tu, den] khớp bộ lọc chung `bo_loc` VÀ điều kiện `dk` của điểm/cột vừa bấm
    (ngay_tu, ngay_den, sac_thai, chu_de, nen_tang, loai_nguon, nguon, cum), nhiều thảo luận
    trước. -> {tong, thao_luan, trang, so_trang, bai}."""
    ds = [r for r in loc_bai(trong_khoang(rows, tu, den), bo_loc)
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


def _iso_vn(dt) -> str | None:
    return (dt.astimezone(VN).isoformat(timespec="minutes")
            if isinstance(dt, datetime.datetime) and dt.tzinfo else None)


def khoa_nguon_bl(c: dict) -> tuple[str, str]:
    """(khoá, tên) nguồn của bình luận: nguồn theo dõi của bài, không thì tác giả bài."""
    if c.get("nguon_id") is not None:
        return f"n:{c['nguon_id']}", c.get("nguon_ten") or c.get("bai_tac_gia") or "?"
    t = str(c.get("bai_tac_gia") or "").strip()
    return (f"t:{t.lower()}", t) if t else ("t:?", "Không rõ nguồn")


def the_bl(c: dict) -> dict:
    dt = c.get("dang_luc")
    lb = loai_bl(c)
    kn, tn = khoa_nguon_bl(c)
    return {"ma": c.get("ma") or "", "ma_cha": c.get("ma_cha") or "",
            "link": c.get("link") or "",
            "bai": {"link": c.get("bai_link") or "", "tac_gia": c.get("bai_tac_gia") or "",
                    "noi_dung": " ".join(str(c.get("bai_noi_dung") or "").split())[:200],
                    "dang_luc": _iso_vn(c.get("bai_dang_luc"))},
            "nguon": {"khoa": kn, "ten": tn,
                      "loai": TEN_LOAI.get(loai(c), loai(c)) if "nguon_loai" in c else ""},
            "tac_gia": c.get("tac_gia") or "", "noi_dung": str(c.get("noi_dung") or "")[:1000],
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
                hom_nay: datetime.date | None = None, bo_loc=None,
                bai_theo_khoa: dict | None = None) -> dict:
    """Bình luận đã cào trong kỳ: số, sắc thái (chỉ của khách), xu hướng, chủ đề × sắc thái.
    Đây là MẪU bình luận Mark đọc được, không phải toàn bộ bình luận nền tảng báo. `bo_loc` +
    `bai_theo_khoa` (bài gốc theo khoá, khi `can_tra_bai`): xem phần "bộ lọc chung"."""
    hom_nay = hom_nay or datetime.datetime.now(VN).date()
    rows = loc_bl([c for c in rows if (n := _ngay_bl(c)) is not None and tu <= n <= den],
                  _gop(bo_loc, nen_tang, loai_nguon), bai_theo_khoa)
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


def xep_theo_luong(rows: list[dict]) -> list[dict]:
    """Bình luận của MỘT bài theo luồng như trên nền tảng: bình luận gốc nhiều thích trước, ngay
    sau mỗi gốc là các trả lời của nó (cũ trước). Trả lời mất cha (cha chưa cào) thành gốc."""
    ma = {c.get("ma") for c in rows if c.get("ma")}
    con: dict[str, list] = collections.defaultdict(list)
    goc: list[dict] = []
    for c in rows:
        cha = c.get("ma_cha")
        (con[cha] if cha and cha in ma and cha != c.get("ma") else goc).append(c)
    luc_min = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
    goc.sort(key=lambda c: (-so(c.get("thich")), c.get("dang_luc") or luc_min))
    ra: list[dict] = []
    da: set = set()

    def them(c: dict) -> None:
        ngan = [c]
        while ngan:                       # duyệt sâu không đệ quy (luồng dài không tràn ngăn xếp)
            x = ngan.pop()
            if id(x) in da:
                continue
            da.add(id(x))
            ra.append(x)
            ngan.extend(sorted(con.get(x.get("ma"), []),
                               key=lambda y: y.get("dang_luc") or luc_min, reverse=True))
    for g in goc:
        them(g)
    ra.extend(c for c in rows if id(c) not in da)      # vòng cha-con lỗi: vẫn không mất dòng
    return ra


def gan_ngu_canh_bai(ds: list[dict], ngu_canh: dict[str, dict]) -> None:
    """Điền link / đoạn nội dung / giờ đăng của bài vào các thẻ bình luận (`the_bl`) đã chọn."""
    for x in ds:
        b = ngu_canh.get(x.get("khoa_bai"))
        if b:
            x["bai"].update(link=b.get("bai_link") or "",
                            noi_dung=" ".join(str(b.get("bai_noi_dung") or "").split())[:200],
                            dang_luc=_iso_vn(b.get("bai_dang_luc")))


SAP_XEP_BL = ("thich", "moi", "cu")
#: Trường lọc của luồng bình luận (kiểu Kompa) — mỗi trường có đếm số theo giá trị (facets).
TRUONG_LOC_BL = ("nen_tang", "nguon", "sac_thai", "chu_de", "loai")


def _gia_tri_bl(c: dict, truong: str) -> str:
    if truong == "nen_tang":
        return c.get("nen_tang") or ""
    if truong == "nguon":
        return khoa_nguon_bl(c)[0]
    lb = loai_bl(c)
    if truong == "loai":
        return lb
    if lb != "hop_le":                    # sắc thái/chủ đề chỉ có nghĩa với bình luận hợp lệ
        return ""
    if truong == "sac_thai":
        return sac_bl(c)
    return str(c.get("chu_de") or "").strip() or CHUA


def chi_tiet_bl(rows: list[dict], tu: datetime.date, den: datetime.date, *,
                trang: int = 1, ngay_tu=None, ngay_den=None, sac_thai=None, chu_de=None,
                nen_tang=None, loai_nguon=None, loai=None, nguon=None, q=None,
                sap_xep: str = "thich", moi_trang: int = MOI_TRANG, bo_loc=None,
                bai_theo_khoa: dict | None = None) -> dict:
    """Luồng bình luận lọc theo các trường (kiểu Kompa): nền tảng, nguồn, sắc thái, chủ đề,
    nhãn lọc, chữ tìm (bỏ dấu, nội dung + tác giả), khoảng ngày; sắp xếp nhiều thích / mới / cũ
    — AND với bộ lọc chung `bo_loc` (xem phần "bộ lọc chung").
    -> {tong, trang, so_trang, binh_luan, facets}. `facets` = {trường: [{gia_tri, ten, so}]}
    đếm trên các dòng khớp MỌI điều kiện TRỪ chính trường đó (chọn tiếp được giá trị khác)."""
    chu = _bo_dau(q).strip() if q else ""
    dk = {"nen_tang": nen_tang, "nguon": nguon, "sac_thai": sac_thai, "chu_de": chu_de,
          "loai": loai}
    f = bien_dich(_gop(bo_loc, None, loai_nguon))
    tra = (bai_theo_khoa or {}).get
    co_so: list[dict] = []
    for c in rows:
        n = _ngay_bl(c)
        if n is None or not tu <= n <= den:
            continue
        if (ngay_tu and n < ngay_tu) or (ngay_den and n > ngay_den):
            continue
        if chu and chu not in _bo_dau(f"{c.get('noi_dung') or ''} {c.get('tac_gia') or ''}"):
            continue
        if not f.rong and f.hong_bl(c, tra(c.get("khoa_bai"))):
            continue
        co_so.append(c)

    def khop(c: dict, bo: str | None = None) -> bool:
        return all(not v or k == bo or _gia_tri_bl(c, k) == v for k, v in dk.items())
    ds = [c for c in co_so if khop(c)]
    if sap_xep == "moi":
        ds.sort(key=lambda c: c.get("luc") or c.get("dang_luc") or datetime.datetime.min.replace(
            tzinfo=datetime.timezone.utc), reverse=True)
    elif sap_xep == "cu":
        ds.sort(key=lambda c: c.get("luc") or c.get("dang_luc") or datetime.datetime.max.replace(
            tzinfo=datetime.timezone.utc))
    else:
        ds.sort(key=lambda c: (-so(c.get("thich")), str(c.get("khoa_bai") or "")))
    facets: dict[str, list] = {}
    for t in TRUONG_LOC_BL:
        dem: collections.Counter = collections.Counter()
        ten: dict[str, str] = {}
        for c in co_so:
            if not khop(c, bo=t):
                continue
            g = _gia_tri_bl(c, t)
            if not g:
                continue
            dem[g] += 1
            if t == "nguon":
                ten[g] = khoa_nguon_bl(c)[1]
        ten_mac_dinh = {"nen_tang": TEN_NEN_TANG, "loai": TEN_LOAI_BL}.get(t, {})
        facets[t] = [{"gia_tri": g, "ten": ten.get(g) or ten_mac_dinh.get(g, g), "so": n}
                     for g, n in dem.most_common(30 if t == "nguon" else None)]
    mot, trang, so_trang = _trang(ds, trang, moi_trang)
    return {"tong": len(ds), "trang": trang, "so_trang": so_trang,
            "binh_luan": [the_bl(c) for c in mot], "facets": facets}


def tu_khoa_thao_luan(bai: list[dict], bl: list[dict], tu: datetime.date, den: datetime.date, *,
                      nen_tang: str | None = None, loai_nguon: str | None = None,
                      tu_khoa_du_an: list[str] | tuple = (), bo_loc=None,
                      bai_theo_khoa: dict | None = None) -> dict:
    """Từ khoá nổi bật kiểu Kompa: đếm trên THẢO LUẬN = bài (không phải kênh nhà) + bình luận
    hợp lệ trong kỳ, cùng bộ lọc chung. -> {"tu_khoa": [{tu, so_bai (= số thảo luận nhắc),
    sắc thái…}], "tong"}."""
    f = bien_dich(_gop(bo_loc, nen_tang, loai_nguon))
    b = loc_bai(trong_khoang(bai, tu, den), f)
    c = loc_bl([x for x in bl if loai_bl(x) == "hop_le"
                and (n := _ngay_bl(x)) is not None and tu <= n <= den], f, bai_theo_khoa)
    # Bình luận: chỉ chữ + sắc thái (không gắn nguồn — bình luận dưới bài kênh nhà là tiếng khách).
    dong = b + [{"noi_dung": x.get("noi_dung") or "", "sac_thai": x.get("sac_thai")} for x in c]
    return {"tu_khoa": tu_khoa(dong, tu_khoa_du_an),
            "tong": sum(not la_kenh_nha(r) for r in b) + len(c)}


# ───────────────────────── đếm cho ô lọc + kênh nhà vs bên ngoài ─────────────────────────
NGUON_TOI_DA_DEM = 80


def _phia() -> dict:
    return {"bai": 0, "thao_luan": 0, "bl": 0, "bl_hop_le": 0,
            "sac_bai": dict.fromkeys(MA_SAC, 0), "sac_bl": dict.fromkeys(MA_SAC, 0)}


def tong_quan_loc(bai: list[dict], bl: list[dict], tu: datetime.date, den: datetime.date,
                  bo_loc=None, bai_theo_khoa: dict | None = None) -> dict:
    """Trên kỳ [tu, den]: số đếm cho từng ô của thanh lọc (`bo_loc_dem`) + khối "Kênh nhà vs Bên
    ngoài" (`nha_ngoai`).

    Đếm kiểu ô chọn nhiều giá trị: số của MỘT chiều tính trên các mục khớp mọi chiều KHÁC (bỏ qua
    chính chiều đó) — đang chọn TikTok vẫn thấy số của Facebook để chọn thêm. Một lượt duyệt: mỗi
    mục có mặt nạ các chiều trượt; trượt 0 chiều thì vào mọi ô, trượt đúng 1 chiều thì chỉ vào ô
    của chiều đó. Đơn vị: BÀI cho các chiều cấp bài; sắc thái / chủ đề đếm cả bài lẫn bình luận
    hợp lệ. `nha_ngoai` = mục khớp mọi chiều TRỪ phạm vi, chia kênh nhà / bên ngoài: bài, thảo
    luận, bình luận đã cào, sắc thái bài (chỉ bên ngoài có) và sắc thái bình luận hợp lệ."""
    f = bien_dich(bo_loc)
    dem: dict[str, collections.Counter] = {k: collections.Counter() for k in CHIEU_LOC}
    cd_bl: collections.Counter = collections.Counter()
    sac_bl_dem: collections.Counter = collections.Counter()
    ten_nguon: dict[str, dict] = {}
    nha = {"kenh_nha": _phia(), "ben_ngoai": _phia()}
    pv = _BIT["pham_vi"]
    for r in trong_khoang(bai, tu, den):
        m = f.hong_bai(r)
        if m & (m - 1):                       # trượt từ 2 chiều: không vào ô nào
            continue
        kn = la_kenh_nha(r)
        if m in (0, pv):
            o = nha["kenh_nha" if kn else "ben_ngoai"]
            o["bai"] += 1
            o["thao_luan"] += thao_luan(r)
            if not kn:
                o["sac_bai"][SAC_MA[sac(r)]] += 1
        if m in (0, pv):
            dem["pham_vi"]["kenh_nha" if kn else "ben_ngoai"] += 1
        if m in (0, _BIT["nen_tang"]):
            dem["nen_tang"][r.get("nen_tang") or "?"] += 1
        if m in (0, _BIT["loai"]):
            dem["loai"][loai(r)] += 1
        if m in (0, _BIT["nguon"]):
            k = khoa_nguon_chu(r)
            dem["nguon"][k] += 1
            if k not in ten_nguon:
                ten_nguon[k] = {"ten": r.get("nguon_ten") or r.get("tac_gia") or r.get("tai_khoan")
                                or "?", "nen_tang": r.get("nen_tang") or "", "loai": loai(r)}
        if m in (0, _BIT["sac_thai"]) and not kn:
            dem["sac_thai"][SAC_MA[sac(r)]] += 1
        if m in (0, _BIT["chu_de"]) and not kn:
            dem["chu_de"][_chu_de(r)] += 1
        if m in (0, _BIT["anh_huong"]):
            dem["anh_huong"][muc_anh_huong(r)] += 1
        if m in (0, _BIT["tuong_tac"]):
            t = tuong_tac_bai(r)
            for muc in TUONG_TAC_MUC:
                if t >= muc:
                    dem["tuong_tac"][str(muc)] += 1
        if m in (0, _BIT["kieu_quet"]):
            dem["kieu_quet"][kieu_quet_bai(r)] += 1
    tra = (bai_theo_khoa or {}).get
    for c in bl:
        n = _ngay_bl(c)
        if n is None or not tu <= n <= den:
            continue
        m = f.hong_bl(c, tra(c.get("khoa_bai")))
        if m & (m - 1):
            continue
        hop_le = loai_bl(c) == "hop_le"
        if m in (0, pv):
            o = nha["kenh_nha" if la_kenh_nha(c) else "ben_ngoai"]
            o["bl"] += 1
            if hop_le:
                o["bl_hop_le"] += 1
                o["sac_bl"][SAC_MA[sac_bl(c)]] += 1
        if hop_le and m in (0, _BIT["sac_thai"]):
            sac_bl_dem[SAC_MA[sac_bl(c)]] += 1
        if hop_le and m in (0, _BIT["chu_de"]):
            cd_bl[_chu_de(c)] += 1
    # Nguồn: nhiều bài trước; nguồn đang chọn luôn có mặt (kể cả 0 bài) để hiện tên trên chip.
    chon = set(f.ng)
    nguon = [{"gia_tri": k, **ten_nguon[k], "so": n}
             for k, n in sorted(dem["nguon"].items(), key=lambda x: (-x[1], x[0]))
             [:NGUON_TOI_DA_DEM]]
    co = {x["gia_tri"] for x in nguon}
    nguon += [{"gia_tri": k, **ten_nguon.get(k, {"ten": k, "nen_tang": "", "loai": ""}),
               "so": dem["nguon"][k]} for k in sorted(chon - co)]
    cac_cd = set(dem["chu_de"]) | set(cd_bl) | set(f.cd_bai) | set(f.cd_bl)
    chu_de = sorted(({"gia_tri": x, "nhom": nhom_chu_de(x), "so_bai": dem["chu_de"][x],
                      "so_bl": cd_bl[x]} for x in cac_cd),
                    key=lambda g: (g["gia_tri"] == CHUA, -(g["so_bai"] + g["so_bl"]),
                                   g["gia_tri"]))
    don = {k: dict(dem[k]) for k in ("pham_vi", "nen_tang", "loai", "anh_huong", "tuong_tac",
                                    "kieu_quet")}
    return {"bo_loc_dem": {**don, "sac_thai": {k: {"bai": dem["sac_thai"][k],
                                                   "bl": sac_bl_dem[k]} for k in MA_SAC},
                           "chu_de": chu_de, "nguon": nguon},
            "nha_ngoai": nha}


#: Nhãn + giá trị của thanh lọc cho trình duyệt (một nguồn sự thật với phần kiểm ở máy chủ).
NHAN_BO_LOC = {
    "pham_vi": PHAM_VI, "nen_tang": TEN_NEN_TANG, "loai": TEN_LOAI,
    "sac_thai": {k: v[0].upper() + v[1:] for k, v in MA_SAC.items()},
    "anh_huong": ANH_HUONG, "kieu_quet": KIEU_QUET,
    "tuong_tac": [{"gia_tri": str(m), "ten": f"Từ {m:,}".replace(",", ".") + " tương tác"}
                  for m in TUONG_TAC_MUC],
}
