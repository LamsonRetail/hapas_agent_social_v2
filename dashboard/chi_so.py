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
import copy
import datetime
import functools
import itertools
import re
import unicodedata

from dashboard import chuan_chu as CC
from dashboard import tu_ghep as TG

VN =datetime.timezone(datetime.timedelta(hours=7))
TC, TI, TL = "Tích cực", "Tiêu cực", "Trung lập"
CHUA = "chưa phân loại"
SAC_THAI = (TC, TI, TL)
#: Bài không gắn nguồn theo dõi (Mark tìm theo từ khoá) — xếp như một "loại nguồn" riêng.
KHONG_NGUON = "tu_khoa"
# Chủ dự án 16/10/2026: nhãn HIỂN THỊ "Internal channel" / "External channel" thay "Kênh nhà" /
# "Bên ngoài" trên mọi trang dashboard. Giá trị lưu kho + tham số URL giữ nguyên (`kenh_nha`,
# `ben_ngoai`, `pham_vi=kenh_nha|ben_ngoai`) — link cũ vẫn mở đúng.
TEN_KENH_NHA, TEN_BEN_NGOAI = "Internal channel", "External channel"
TEN_LOAI = {"kol": "KOL/KOC", "page": "Trang/fanpage", "group": "Nhóm", "bao": "Báo/tin tức",
            "kenh_nha": TEN_KENH_NHA, "khac": "Khác", KHONG_NGUON: "Tìm theo từ khoá"}
# "web" (16/10/2026): báo, diễn đàn, blog Mark tìm qua Google theo từ khoá — `tai_khoan` = tên miền,
# xem / thích / chia sẻ luôn NULL (không có số), `binh_luan` = số trả lời diễn đàn hoặc NULL.
TEN_NEN_TANG = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube",
                "facebook": "Facebook", "threads": "Threads", "web": "Báo & Web"}
#: Loại trang của bài web (`bai.kieu_trang`, Mark gán theo danh sách miền — `nguon_web`).
KIEU_TRANG = {"bao": "Báo", "dien_dan": "Diễn đàn", "blog": "Blog", "mxh_khac": "MXH khác",
              "khac": "Web khác"}
#: Mức nhắc brand trong bài web (`bai.muc_nhac`).
MUC_NHAC = {"tieu_de": "nhắc ở tiêu đề", "chinh": "nhắc trong bài", "thoang": "nhắc lướt"}

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


# ───────────────── KOC affiliate / KOC branding (20/10/2026, task Lark t284905) ─────────────────
# Marketing: "đang bị lẫn KOC branding và KOC aff → tiêu chí: KOC branding không gắn giỏ hàng ><
# KOC aff có gắn giỏ" (chủ dự án duyệt PA1). Xếp THEO TỪNG VIDEO, không theo tài khoản: một nhà
# sáng tạo có thể đăng cả video gắn giỏ lẫn video không giỏ. Chỉ TikTok (nền tảng duy nhất có cờ
# giỏ — `bai.gio_hang`), trừ Internal channel (video của chính brand không phải KOC). KHÔNG đặt
# ngưỡng follower: tiêu chí marketing chỉ là giỏ hàng, và bài tìm theo từ khoá (phần lớn video
# TikTok) không có loại nguồn — muốn chỉ KOC lớn thì kết hợp ô "Ảnh hưởng". Độc lập với loại
# nguồn `kol` (nguồn KOL/KOC đang theo dõi): hai chiều AND với nhau. NULL = nguồn không báo giỏ
# (feed hashtag, bài cũ chưa bù) → "Chưa rõ", không bao giờ đoán thành branding.
KOC = {"affiliate": "KOC affiliate · gắn giỏ", "branding": "KOC branding · không giỏ",
       "chua_ro": "Chưa rõ giỏ hàng"}


def nhom_koc(r: dict) -> str | None:
    """affiliate | branding | chua_ro cho video TikTok ngoài Internal channel; None với bài khác."""
    if r.get("nen_tang") != "tiktok" or la_kenh_nha(r):
        return None
    g = r.get("gio_hang")
    return "affiliate" if g is True else "branding" if g is False else "chua_ro"


def khoang_truoc(tu: datetime.date, den: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Kỳ liền trước cùng độ dài: 01–30/09 -> 02/08–31/08."""
    n = (den - tu).days + 1
    return tu - datetime.timedelta(days=n), tu - datetime.timedelta(days=1)


def _bo_dau(s: str) -> str:
    return CC.bo_dau(s)


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
#   kieu_trang loại trang của bài web (báo, diễn đàn…); bài MXH không có nên chỉ khớp khi chiều này
#              trống. Bình luận theo bài của nó.
#   koc        Loại KOC của video TikTok ngoài Internal channel (`nhom_koc`: affiliate / branding /
#              chua_ro, 20/10/2026); bài khác không khớp khi chiều này có giá trị. Bình luận
#              theo bài.
#   sac_thai   bài theo sắc thái BÀI (bài kênh nhà không mang tiếng khách → không khớp); bình luận
#              theo sắc thái của CHÍNH nó (chỉ bình luận hợp lệ có sắc thái).
#   chu_de     bài và bình luận có HAI bộ nhãn khác nhau (13 chủ đề bài, 8 chủ đề bình luận của
#              Mark). Mỗi nhãn lọc đúng loại mục mang nhãn đó: chọn toàn chủ đề bình luận thì phần
#              bài không bị lọc theo chủ đề (và ngược lại); "Khác", "chưa phân loại" lọc cả hai.
#   q          chữ tìm bỏ dấu (+ teen code, chữ kiểu cách — `chuan_chu.khoa`): bài khớp khi nội
#              dung + hashtag chứa chữ; bình luận khớp khi CHÍNH nó chứa chữ HOẶC bài của nó khớp
#              (thảo luận dưới bài nói về chữ đó).
#   y_dinh     "1" = chỉ bình luận có Ý ĐỊNH MUA (`la_y_dinh_mua`, 16/10/2026); mã MÓN (`SAN_PHAM`,
#              vd "set_qua", 17/10/2026) = chỉ bình luận hỏi mua món đó (`san_pham_bl`). Như chủ đề
#              bình luận: chỉ lọc bình luận, phần bài không đổi.
#   gom_mg     "1" = mây từ khoá GỒM cả bình luận minigame (mặc định ẩn). KHÔNG lọc khối nào khác —
#              chỉ là tuỳ chọn hiển thị của mây + ngăn từ khoá, nằm đây để theo URL và khoá nhớ.
CHIEU_LOC = ("pham_vi", "nen_tang", "loai", "nguon", "sac_thai", "chu_de", "anh_huong",
             "tuong_tac", "q", "kieu_quet", "kieu_trang", "koc", "y_dinh", "gom_mg")
_BIT = {k: 1 << i for i, k in enumerate(CHIEU_LOC)}
PHAM_VI = {"tat_ca": "Tất cả", "kenh_nha": TEN_KENH_NHA, "ben_ngoai": TEN_BEN_NGOAI}
#: Mã sắc thái trên URL (gọn, không dấu) -> nhãn lưu trong kho.
MA_SAC = {"tich_cuc": TC, "tieu_cuc": TI, "trung_lap": TL, "chua_phan_loai": CHUA}
SAC_MA = {v: k for k, v in MA_SAC.items()}
#: Bậc ảnh hưởng theo followers của tài khoản đăng (mốc quen thuộc của nghề influencer).
ANH_HUONG = {"nano": "Nano · dưới 10N", "micro": "Micro · 10N–100N", "macro": "Macro · 100N–1Tr",
             "mega": "Mega · từ 1Tr", "khong_ro": "Không rõ follower"}
TUONG_TAC_MUC = (100, 1_000, 10_000)
KIEU_QUET = {"theo_doi": "Quét nguồn theo dõi", "tu_khoa": "Tìm theo từ khoá"}
#: MÓN khách hỏi mua (17/10/2026) — bản sao `phan_loai.SAN_PHAM` (mã lưu ở `binh_luan.san_pham`;
#: bài thử đối chiếu). Thứ tự = thứ tự hiện trên khối Ý định mua khi bằng số.
SAN_PHAM = {"tui": "Túi xách", "vi": "Ví", "nuoc_hoa": "Nước hoa", "trang_suc": "Trang sức",
            "set_qua": "Set quà / combo", "khac": "Món khác",
            "ngoai_brand": "Đồ không phải của brand", "chua_ro": "Chưa rõ món"}
#: Hỏi mua đồ KHÔNG phải của brand (váy KOL mặc, đồ may đo, "link nồi") không tính là ý định mua.
SP_NGOAI = "ngoai_brand"
SP_CHUA_RO = "chua_ro"
Y_DINH = {"1": "bình luận hỏi giá / muốn mua",
          **{k: f"hỏi mua: {v}" for k, v in SAN_PHAM.items() if k != SP_NGOAI}}
# Bản sao nhãn chủ đề của Mark (`phan_loai.CHU_DE_BAI` / `phan_loai.CHU_DE`) — dashboard không
# import module của Mark; bài thử đối chiếu. Dùng để biết nhãn nào là của bài, nhãn nào của bình luận.
CHU_DE_BAI = ("Chiến dịch & quảng cáo", "Giá cả & khuyến mãi", "Chất lượng sản phẩm",
              "Hình ảnh & mẫu mã", "Trải nghiệm mua sắm", "Dịch vụ khách hàng", "Giao hàng",
              "So sánh thương hiệu", "Nguồn gốc & chính hãng", "Cửa hàng & vận hành",
              "Tuyển dụng", "Doanh nghiệp & truyền thông", "Khác")
#: Chủ đề bình luận MỚI của Mark (16/10/2026, `phan_loai.CHU_DE["MG"]`): lời dự thi minigame / lời
#: chúc theo đề bài của brand. Rà kho: 29/50 cụm của mây từ là lời dự thi dưới MỘT bài minigame —
#: không phải cảm nhận về brand, nên mặc định không vào mây (`tu_khoa_thao_luan`).
CHU_DE_MINIGAME = "Minigame/bài dự thi"
CHU_DE_BL = ("Sản phẩm/chất lượng", "Giá/mua ở đâu/ý định mua", "KOL/nội dung",
             "Giao hàng/dịch vụ", "Đối thủ", "Tag bạn bè", CHU_DE_MINIGAME, "Khác")
#: Chủ đề bình luận nói về THƯƠNG HIỆU / sản phẩm (mã Mark SP, GIA, DV, DT) — tách "Tiêu cực" của
#: bình luận làm hai phần. Còn lại (ND, MG, TAG, Khác, chưa gán) = về nội dung / KOL & khác.
CHU_DE_BL_THUONG_HIEU = frozenset({"Sản phẩm/chất lượng", "Giá/mua ở đâu/ý định mua",
                                   "Giao hàng/dịch vụ", "Đối thủ"})
_TOI_DA_GIA_TRI = {"nen_tang": len(TEN_NEN_TANG), "loai": 7, "nguon": 50, "sac_thai": 4,
                   "chu_de": 40, "anh_huong": 5, "kieu_trang": len(KIEU_TRANG), "koc": len(KOC)}
_RE_DAU_NGUON = re.compile(r"(n|t|link|\?|tiktok|facebook|instagram|youtube|threads|web):")
#: Khoá nguồn dài nhất: "link:" + link bài (kho cắt 500 ký tự) — bài không có tác giả/tài khoản.
NGUON_TOI_DA_KY_TU = 520

#: Bộ lọc nhanh (chip trên trang) — DỮ LIỆU: thêm/bớt một mục ở đây là đủ, trang tự hiện. `loc`
#: dùng đúng tham số URL (bài thử kiểm từng mục đọc được bằng `doc_bo_loc`); `so_ngay` (tuỳ chọn)
#: đặt khoảng N ngày tính tới HÔM NAY. Bấm chip = thay toàn bộ bộ lọc (giữ ngày nếu không có so_ngay).
BO_LOC_NHANH = (
    {"ma": "kenh_nha", "ten": TEN_KENH_NHA,
     "mo_ta": "Chỉ bài trên kênh của chính thương hiệu và bình luận khách dưới các bài đó.",
     "loc": {"pham_vi": "kenh_nha"}},
    {"ma": "ben_ngoai", "ten": TEN_BEN_NGOAI,
     "mo_ta": "Mọi thứ ngoài Internal channel: KOL, trang, nhóm, báo và bài Mark tìm theo từ khoá.",
     "loc": {"pham_vi": "ben_ngoai"}},
    {"ma": "kol", "ten": "KOL/KOC nói về thương hiệu",
     "mo_ta": "Bài của các nguồn KOL/KOC đang theo dõi (External channel).",
     "loc": {"pham_vi": "ben_ngoai", "loai": "kol"}},
    # 20/10/2026 (task t284905): tách KOC theo giỏ hàng TikTok Shop của TỪNG video.
    {"ma": "koc_aff", "ten": "KOC affiliate (gắn giỏ)",
     "mo_ta": "Video TikTok External channel có gắn giỏ TikTok Shop — theo từng video.",
     "loc": {"koc": "affiliate"}},
    {"ma": "koc_brand", "ten": "KOC branding (không giỏ)",
     "mo_ta": "Video TikTok External channel không gắn giỏ hàng — theo từng video; chưa rõ "
              "giỏ (nguồn không báo) không tính.",
     "loc": {"koc": "branding"}},
    {"ma": "khung_hoang", "ten": "Cảnh báo khủng hoảng",
     "mo_ta": "Tiêu cực trên bài có từ 1.000 tương tác — thứ lan nhanh nhất, kể cả trên Internal channel.",
     "loc": {"sac_thai": "tieu_cuc", "tuong_tac": "1000"}},
    # 16/10/2026: cùng định nghĩa với ô "Ý định mua" (chủ đề AI hoặc câu hỏi giá/mua), không còn
    # chỉ theo chủ đề — link cũ `chu_de=Giá/mua…` vẫn lọc theo chủ đề như trước.
    {"ma": "hoi_mua", "ten": "Khách hỏi mua",
     "mo_ta": "Bình luận hỏi giá, hỏi chỗ mua, xin link, hỏi size/ship, muốn đặt — MỌI món "
              "(túi, ví, nước hoa, set quà…; khối Ý định mua tách theo món), đúng các bình luận "
              "đếm ở ô Ý định mua. Hỏi mua đồ không phải của brand không tính.",
     "loc": {"y_dinh": "1"}},
    {"ma": "can_xu_ly", "ten": "Tiêu cực cần xử lý",
     "mo_ta": "Bình luận tiêu cực trên Internal channel 7 ngày gần nhất (tính cả hôm nay) — cần trả lời.",
     "loc": {"pham_vi": "kenh_nha", "sac_thai": "tieu_cuc"}, "so_ngay": 7},
    {"ma": "lan_toa", "ten": "Lan toả mạnh", "mo_ta": "Bài có từ 10.000 tương tác.",
     "loc": {"tuong_tac": "10000"}},
    {"ma": "khen", "ten": "Khen từ External channel",
     "mo_ta": "Bài External channel tích cực — UGC để cảm ơn, xin đăng lại.",
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
    yd = str(q.get("y_dinh") or "")
    if yd and yd not in Y_DINH:
        raise LoiBoLoc("Bộ lọc không hợp lệ.")
    mg = str(q.get("gom_mg") or "")
    if mg not in ("", "1"):
        raise LoiBoLoc("Bộ lọc không hợp lệ.")
    return {"pham_vi": pv, "nen_tang": nhieu("nen_tang", TEN_NEN_TANG),
            "loai": nhieu("loai", TEN_LOAI), "nguon": nhieu("nguon"),
            "sac_thai": tuple(sorted(set(sac_ds))), "chu_de": chu_de,
            "anh_huong": nhieu("anh_huong", ANH_HUONG), "tuong_tac": int(tt) if tt else 0,
            "q": tim, "kieu_quet": kq, "kieu_trang": nhieu("kieu_trang", KIEU_TRANG),
            "koc": nhieu("koc", KOC), "y_dinh": yd, "gom_mg": mg}


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
        self.kt = set(b.get("kieu_trang") or ())
        self.koc = set(b.get("koc") or ())
        self.tt = int(b.get("tuong_tac") or 0)
        self.kq = b.get("kieu_quet") or ""
        self.q = CC.khoa_tim(b.get("q")) if b.get("q") else ""
        self.yd = str(b.get("y_dinh") or "")          # "1" | mã món | "" (không lọc)
        self.gom_mg = b.get("gom_mg") == "1"           # tuỳ chọn mây từ, không phải chiều lọc
        self._q_bai: dict[int, bool] = {}
        self.rong = self._tinh_rong()
        # Bình luận cần tra BÀI gốc khi lọc theo thứ dòng bình luận không mang.
        self.can_bai = bool(self.ah or self.tt or self.kq or self.q or self.kt or self.koc or
                            any(not k.startswith("n:") for k in self.ng))

    def _tinh_rong(self) -> bool:
        return not (self.pv != "tat_ca" or self.nt or self.lo or self.ng or self.sac or self.cd_bai
                    or self.cd_bl or self.ah or self.tt or self.kq or self.q or self.kt or self.koc
                    or self.yd)

    def bo_y_dinh(self) -> _Loc:
        """Bản sao KHÔNG có chiều y_dinh — mẫu số "% bình luận sạch" của Ý định mua: đang lọc
        y_dinh=1 mà chia cho chính các bình luận ý định mua thì luôn ra 100% (review 16/10)."""
        if not self.yd:
            return self
        ban = copy.copy(self)
        ban.yd = ""
        ban.rong = ban._tinh_rong()
        return ban

    def _chu(self, s) -> bool:
        return CC.chua(self.q, s)

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
        if self.kt and r.get("kieu_trang") not in self.kt:
            m |= _BIT["kieu_trang"]
        if self.koc and nhom_koc(r) not in self.koc:
            m |= _BIT["koc"]
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
        if self.kt and (bai is None or bai.get("kieu_trang") not in self.kt):
            m |= _BIT["kieu_trang"]
        if self.koc and (bai is None or nhom_koc(bai) not in self.koc):
            m |= _BIT["koc"]
        if self.yd and not khop_y_dinh(c, self.yd):
            m |= _BIT["y_dinh"]
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
        "web": kpi_web(rows),
    }


def kpi_web(rows: list[dict]) -> dict | None:
    """Báo & Web không có xem/thích/chia sẻ: đếm số bài, số miền, % bài PR (`la_pr`), % nhắc ở
    tiêu đề (`muc_nhac`) — % trên bài CÓ giá trị (NULL không vào mẫu số). Không có bài web -> None."""
    web = [r for r in rows if r.get("nen_tang") == "web"]
    if not web:
        return None
    pr = [r["la_pr"] for r in web if r.get("la_pr") is not None]
    mn = [r["muc_nhac"] for r in web if r.get("muc_nhac") in MUC_NHAC]
    return {"bai": len(web), "mien": len({_khoa_nguon(r) for r in web}),
            "pr": sum(1 for x in pr if x), "pr_pt": round(100.0 * sum(1 for x in pr if x) / len(pr), 1)
            if pr else None,
            "tieu_de": mn.count("tieu_de"),
            "tieu_de_pt": round(100.0 * mn.count("tieu_de") / len(mn), 1) if mn else None,
            "theo_kieu": {k: n for k in KIEU_TRANG
                          if (n := sum(1 for r in web if r.get("kieu_trang") == k))}}


def doi_pt(nay: float, truoc: float) -> float | None:
    return round(100.0 * (nay - truoc) / truoc, 1) if truoc else None


def so_sanh(nay: dict, truoc: dict) -> dict:
    """`moi` = so được và kỳ trước bằng 0 mà kỳ này có số (% không tính được — trang ghi "mới");
    chỉ máy chủ biết khi nào so sánh bị tắt (`so_sanh_lech`, dữ liệu bị cắt)."""
    return {k: {"nay": nay[k], "truoc": truoc[k], "doi_pt": doi_pt(nay[k], truoc[k]),
                "moi": not truoc[k] and bool(nay[k])}
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


def sac_thai_nen_tang(rows: list[dict], ham_sac=None) -> list[dict]:
    """Nền tảng × sắc thái (19/10/2026, marketing: "sắc thái theo kênh"). `rows` là đúng tập vòng
    sắc thái đếm — bài: bên gọi đã bỏ kênh nhà; bình luận: chỉ hợp lệ. `ham_sac`: `sac` (bài, mặc
    định) hoặc `sac_bl`. Nhiều mục trước. -> [{nen_tang, ten, so, TC, TI, TL, CHUA}]."""
    ham_sac = ham_sac or sac
    dem: dict[str, dict] = {}
    for r in rows:
        p = r.get("nen_tang") or "?"
        g = dem.setdefault(p, {"nen_tang": p, "ten": TEN_NEN_TANG.get(p, p), "so": 0,
                               TC: 0, TI: 0, TL: 0, CHUA: 0})
        g["so"] += 1
        g[ham_sac(r)] += 1
    return sorted(dem.values(), key=lambda g: (-g["so"], g["nen_tang"]))


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
#: Cách xếp bảng Nguồn nổi bật (19/10/2026, tham số `sap_nguon` của /api/chi-so): tiêu chí chính
#: rồi hai tiêu chí còn lại làm hoà. Xếp TRƯỚC khi cắt `TOP_NGUON` — top theo lượt xem là đúng
#: các nguồn nhiều xem nhất, không phải top thảo luận đem xếp lại.
SAP_NGUON = {"thao_luan": ("thao_luan", "bai", "xem"), "bai": ("bai", "thao_luan", "xem"),
             "xem": ("xem", "thao_luan", "bai")}


def top_nguon(rows: list[dict], toi_da: int = TOP_NGUON, sap: str = "thao_luan") -> list[dict]:
    """Top `toi_da` nguồn MỖI nền tảng theo `sap` (`SAP_NGUON`; mặc định thảo luận, hoà thì số
    bài, rồi lượt xem). Nền tảng xếp theo tổng thảo luận giảm dần.
    -> [{nen_tang, ten_nen_tang, so_nguon, nguon: [...]}]."""
    SAP_NGUON[sap]                          # cách xếp lạ: KeyError trước khi gom
    return top_nguon_moi_cach(rows, toi_da, (sap,))[sap]


def top_nguon_moi_cach(rows: list[dict], toi_da: int = TOP_NGUON,
                       cach: tuple = tuple(SAP_NGUON)) -> dict[str, list[dict]]:
    """Như `top_nguon` cho MỌI cách xếp trong `cach` — gom nguồn MỘT lần, xếp mỗi cách một lần.
    /api/chi-so nhớ cả ba nên đổi ô "Xếp theo" không tính lại cả trang. -> {sap: [...]}."""
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
                "xem": None, "followers": 0}
        g["bai"] += 1
        g["binh_luan"] += so(r.get("binh_luan"))
        g["thao_luan"] += thao_luan(r)
        if r.get("xem") is not None:        # nguồn chỉ có bài không có số xem (web): "—", không 0
            g["xem"] = (g["xem"] or 0) + so(r.get("xem"))
        g["followers"] = max(g["followers"], so(r.get("followers")))
    theo: dict[str, list] = collections.defaultdict(list)
    for (p, _), g in gom.items():
        theo[p].append(g)
    tong = {p: sum(g["thao_luan"] for g in ds) for p, ds in theo.items()}
    thu_tu_nt = sorted(theo, key=lambda p: (-tong[p], p))

    def xep(thu_tu: tuple) -> list[dict]:
        ra = []
        for p in thu_tu_nt:
            ds = sorted(theo[p], key=lambda g: (*(-(g[k] or 0) for k in thu_tu), g["ten"]))
            ra.append({"nen_tang": p, "ten_nen_tang": TEN_NEN_TANG.get(p, p),
                       "so_nguon": len(ds), "nguon": ds[:toi_da]})
        return ra
    return {s: xep(SAP_NGUON[s]) for s in cach}


def khoa_nguon_chu(r: dict) -> str:
    """Khoá nguồn (`_khoa_nguon`) dạng chuỗi để trình duyệt gửi lại khi bấm vào một nguồn."""
    k = _khoa_nguon(r)
    return f"{k[0]}:{k[1]}"


def so_co(v) -> int | None:
    """Số hiển thị của một chỉ số bài: NULL (nền tảng không có số — bài web không có xem / thích /
    chia sẻ) -> None để trang hiện "—", KHÔNG hiện 0."""
    return None if v is None else so(v)


def _web_bai(r: dict) -> dict:
    """Trường riêng của bài web cho thẻ bài (bài MXH: None)."""
    return {"kieu_trang": r.get("kieu_trang") if r.get("kieu_trang") in KIEU_TRANG else None,
            "muc_nhac": r.get("muc_nhac") if r.get("muc_nhac") in MUC_NHAC else None,
            "la_pr": r.get("la_pr") if isinstance(r.get("la_pr"), bool) else None}


def _the_bai(r: dict) -> dict:
    dt = r.get("dang_luc")
    return {**_web_bai(r),
        "khoa": r.get("khoa") or "", "bl_da_lay": so(r.get("bl_da_lay")),
        "link": r.get("link") or "", "nen_tang": r.get("nen_tang") or "",
        "tac_gia": r.get("tac_gia") or r.get("tai_khoan") or "",
        "dang_luc": (dt.astimezone(VN).isoformat(timespec="minutes")
                     if isinstance(dt, datetime.datetime) and dt.tzinfo else None),
        "noi_dung": " ".join(str(r.get("noi_dung") or "").split())[:500],
        "sac_thai": "kênh nhà" if la_kenh_nha(r) else sac(r),
        "chu_de": r.get("chu_de") or "", "loai": TEN_LOAI.get(loai(r), loai(r)),
        "xem": so_co(r.get("xem")), "thich": so_co(r.get("thich")),
        "binh_luan": so_co(r.get("binh_luan")), "chia_se": so_co(r.get("chia_se")),
        "thao_luan": thao_luan(r), "koc": nhom_koc(r)}


def top_bai(rows: list[dict], toi_da: int = TOP_BAI) -> list[dict]:
    ds = sorted(rows, key=lambda r: (-thao_luan(r), -so(r.get("xem")), str(r.get("link") or "")))
    ra = []
    for r in ds[:toi_da]:
        dt = r.get("dang_luc")
        ra.append({
            **_web_bai(r),
            "khoa": r.get("khoa") or "", "bl_da_lay": so(r.get("bl_da_lay")),
            "link": r.get("link") or "", "nen_tang": r.get("nen_tang") or "",
            "tac_gia": r.get("tac_gia") or r.get("tai_khoan") or "",
            "dang_luc": (dt.astimezone(VN).isoformat(timespec="minutes")
                         if isinstance(dt, datetime.datetime) and dt.tzinfo else None),
            "noi_dung": " ".join(str(r.get("noi_dung") or "").split())[:200],
            "sac_thai": "kênh nhà" if la_kenh_nha(r) else sac(r),
            "chu_de": r.get("chu_de") or "", "loai": TEN_LOAI.get(loai(r), loai(r)),
            "xem": so_co(r.get("xem")), "thich": so_co(r.get("thich")),
            "binh_luan": so_co(r.get("binh_luan")), "chia_se": so_co(r.get("chia_se")),
            "thao_luan": thao_luan(r), "koc": nhom_koc(r)})
    return ra


# ───────────────────────── từ khoá nổi bật ─────────────────────────
# Chủ dự án 16/10/2026: "phần từ khoá nổi bật đang lấy các bình luận spam và lấy key word đang lỗi".
# Rà ảnh chụp kho 16/10 (External channel, 50 cụm đầu): 6 cụm từ spam affiliate chưa gắn nhãn
# ("dán max", "max cuối", "dán cam", "sàn cam", "dán sàn", "fpg xóa" — mảnh của mã CKZ-VD88S-FPG);
# 9 cụm do MỘT người viết lặp ("hỗ trợ", "kênh bên" — tài khoản bán hàng trả lời 5 lần; "both
# pure"; "nữ aura", "xách nữ" — 3 bài cùng một tài khoản); mảnh cắt ngang ranh giới từ ("xách nữ",
# "túi màu", "hề diễn"); nhãn dán TikTok "[cười chảy nước mắt]" ra "cười chảy", "chảy nước"; mảnh câu
# hỏi giá "giá set", "set giá". Cách làm (người làm social listening lâu năm vẫn làm thế):
#   1. Tách TỪ trước khi ghép cụm (`tu_ghep`: danh sách từ ghép + so khớp dài nhất): cụm là MỘT từ
#      ghép ("túi xách", "nước mắt") hoặc HAI từ đơn liền nhau ("túi đẹp", "ví xinh"); cặp âm tiết
#      cắt ngang một từ ghép không còn là cụm.
#   2. Bỏ thứ không phải chữ: mã/số/chữ dính số ("a88ah", "20/10"), chữ nối gạch ("sộp-pii"), nhãn
#      dán TikTok "[…]", hashtag có số (thẻ mùa vụ/ngày như #quatang2010, #sale1111).
#   3. Bình luận mang dấu hiệu rác quảng cáo (mã giới thiệu, lời dặn dán mã) không vào mây dù nhãn
#      còn là hợp lệ (`la_rac_quang_cao`) — lớp phòng hờ khi luật spam của Mark sót.
#   4. Một người viết lặp không phải xu hướng: cụm cần ≥ `NGUOI_TOI_THIEU` người viết khác nhau và
#      người viết nhiều nhất góp không quá `MOT_NGUOI_TOI_DA` số thảo luận của cụm.
# Hư từ / đại từ / từ đệm hay gặp trên MXH Việt + tiếng Anh (gốc chép từ
# `tong_hop_lang_nghe._STOP` — dashboard không import module của Mark). Cặp hai từ đơn có một chữ ở
# đây thì bỏ: "rất đẹp", "của hàng" không phải từ khoá. Hư từ GHÉP ("cảm ơn", "thật sự") ở
# `tu_ghep.TU_HU`.
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
xin ak ah mk mik mjk mh bn
ông bà cô chú bác dì cậu mợ ổng bả thằng đứa ny mn mng ae ad
chiếc món quả tấm bức hề ghê xỉu thiệt thật lun lém wá qá vãi vl vkl vcl z dị zậy nhen nhe
hen nghen há hà ui ôi chắc lẻ bnh bnhiu bnhieu nhiu
both let too oh omg wow lol hi hello pls plz thanks thank thx okay
"""
_STOP = set(_STOP_CHU.split())
# Khách gõ KHÔNG DẤU ("shop oi", "dep qua"): chữ thuần ASCII trùng bản bỏ dấu của một hư từ cũng là
# hư từ — trừ các chữ hay là tên hàng/màu/chất liệu khi bỏ dấu (da, đen, ví, vàng, dây, vải…).
# "vay" (16/10) coi là "vậy": "gia sao vay shop" gặp nhiều hơn hẳn "váy" gõ không dấu.
_MO_HO = {"da", "nhung", "den", "vi", "to", "day", "dung", "dang", "vang", "de", "may",
          "len", "nam", "mau", "vai"}
_STOP_KHONG_DAU = {CC.bo_dau(x) for x in _STOP} - _MO_HO
# Mảnh câu HỎI GIÁ ("giá shop", "giá set", "set giá bao nhiêu", "báo giá") là ý định mua, không phải
# chủ đề bàn tán: đã đếm riêng ở khối Ý định mua nên không vào mây. Cặp có "giá" đứng SAU luôn bỏ;
# "giá" đứng TRƯỚC chỉ giữ khi chữ sau là lời đánh giá giá ("giá tốt", "giá rẻ", "giá cao" — đó là
# cảm nhận về giá). Chọn BỎ CỤM chứ không bỏ cả bình luận hỏi mua: "xin giá set túi trắng" vẫn góp
# "set túi", "túi trắng" — khách hỏi mua món nào cũng là tín hiệu về sản phẩm.
_GIA_DANH_GIA = {"tot", "re", "cao", "mem", "hoi", "on", "dat", "chat", "mac", "dep", "yeu", "soc"}
#: "giá" so trên MẶT CHỮ (có dấu, hoặc gõ không dấu "gia") — bản bỏ dấu thì "giả" (hàng giả) cũng
#: thành "gia" và "sp giả", "shop giả" bị bỏ nhầm (review 16/10).
_GIA = {"giá", "gia"}
#: Chữ chỉ BỔ NGHĨA cho từ đứng trước ("túi xách nữ", "áo nam"), không mở đầu một cụm: "nữ aura",
#: "nam đẹp" là mảnh cắt ngang (so bản bỏ dấu; "phụ nữ", "nam tính" là từ ghép nên không bị chặn).
_KHONG_MO_DAU = {"nu", "nam"}
#: Chữ đứng CUỐI cặp gần như luôn là lời gọi người bán ("đẹp quá shop", "bao nhiêu vậy shop").
_KHONG_KET_THUC = {"shop", "sop"}
# Hashtag "đẩy đề xuất" ai cũng gắn, không nói gì về brand.
_HASHTAG_CHUNG = {"fyp", "foryou", "foryoupage", "xuhuong", "xuhướng", "viral", "trending",
                  "trend", "tiktok", "reels", "reel", "capcut", "fypシ", "fy", "explore",
                  "viralvideo", "tiktokvietnam", "vairal", "thinhhanh", "learnontiktok",
                  "tiktokshop", "xuhuongtiktok", "trendingtiktok", "viraltiktok", "fypviral"}
_HASHTAG_CHUNG_KD = {CC.bo_dau(x) for x in _HASHTAG_CHUNG}
_RE_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
#: Tag "@tài_khoản", kèm tên hiển thị nhiều chữ ("@Trần Mai Anh xem nè"): bỏ cả các chữ VIẾT HOA
#: liền sau "@…" (tối đa 3) — tên người được tag không phải lời bình luận (`_bo_tag_ten`).
_RE_TAG_TEN = re.compile(r"@[\w.\-]+(?:[^\S\n]+[^\W\d_][\w.\-]*){0,3}")
_RE_HASHTAG = re.compile(r"#(\w+)")
_RE_DOAN = re.compile(r"[^\w\s]+|\d+|_+")
#: Nhãn dán / biểu tượng cảm xúc TikTok xuất ra thành chữ trong ngoặc vuông: "[cười chảy nước mắt]",
#: "[ấm lòng]" — không phải lời khách viết.
_RE_NHAN_DAN = re.compile(r"\[[^\[\]\n]{1,40}\]")
#: Chữ dính số hoặc nối bằng gạch/chấm/xuyệt ("a88ah", "vd88s-fpg", "sộp-pii", "20/10", "8k") là
#: mã, số, tên miền — không phải chữ: thay bằng ranh giới để mảnh của nó không ghép với chữ bên cạnh.
_RE_CHU_MA = re.compile(r"\S*(?:\d|\w[-./–—]\w)\S*")
_RE_KEO_DAI = re.compile(r"([^\W\d_])\1{2,}")              # "đẹppppp" → "đẹp"
#: Chữ dài hơn mức này mà không phải từ đã biết là chuỗi gõ bừa / cười ("hahahahaha").
_CHU_DAI_NHAT = 15
#: Dấu hiệu rác quảng cáo — bản rút gọn hai dấu hiệu MẠNH của `loc_rac.dau_hieu_affiliate` (Mark;
#: dashboard không import module của Mark, bài thử đối chiếu hai bên): mã giới thiệu ≥ 3 khúc IN
#: HOA/số nối gạch, ≥ 2 khúc có chữ cái (AHS-WCM-DQN, CKZ-VD88S-FPG); lời dặn dán mã ("dán max",
#: "zán cam", "săn cam", "xóa 88 rồi"). Ở mây từ CHỈ CẦN MỘT dấu hiệu là bỏ dòng (nhãn spam của
#: Mark cần hai): mây không phán spam, chỉ không để chữ của rác lên làm "từ khoá nổi bật" — bình
#: luận thật nhắc mã sản phẩm mất khỏi mây là cái giá nhỏ.
_RE_MA_GIOI_THIEU = re.compile(r"(?<![A-Za-z0-9\-–—])[A-Z0-9]{3,6}(?:[-–—][A-Z0-9]{2,6}){2,}"
                               r"(?![A-Za-z0-9\-–—])")
_RE_LOI_DAN_MA = re.compile(r"(?<!\w)(?:(?:dán|zán|zan) (?:mã|max|vào|cam|code)|săn cam"
                            r"|(?:xóa|xoá|xoa) \d+ (?:rồi|r|đi|là))(?!\w)")
_RE_KHUC_CO = re.compile(r"^\d{0,2}X{0,4}[SML]$|^\d{1,3}$")    # khúc là cỡ (XXL, 3XL) hoặc số
#: Cụm cần ít nhất chừng này NGƯỜI VIẾT khác nhau, và người viết nhiều nhất góp không quá tỉ lệ này
#: số thảo luận của cụm: tài khoản bán hàng trả lời cùng một câu mẫu 5 lần, một người dán cùng câu
#: tiếng Anh 2 lần, một KOC đăng 3 bài cùng chú thích — không phải xu hướng.
NGUOI_TOI_THIEU = 2
MOT_NGUOI_TOI_DA = 2 / 3


@functools.lru_cache(maxsize=65536)
def _kd(tu: str) -> str:
    """Bản bỏ dấu của MỘT chữ (nhớ đệm: mây từ đi qua cùng vài nghìn chữ hàng chục nghìn lần)."""
    return CC.bo_dau(tu)


def _hu_tu(tu: str) -> bool:
    return tu in _STOP or (tu.isascii() and tu in _STOP_KHONG_DAU)


def la_rac_quang_cao(s) -> bool:
    """Bình luận có mã giới thiệu hoặc lời dặn dán mã (xem `_RE_MA_GIOI_THIEU`) — không vào mây từ,
    kể cả khi nhãn còn là hợp lệ (luật spam của Mark sót / chưa chạy lại trên dữ liệu cũ)."""
    raw = str(s or "")
    if not raw:
        return False
    if _RE_LOI_DAN_MA.search(CC.thuong(raw)):
        return True
    for m in _RE_MA_GIOI_THIEU.finditer(CC.nfkc(_RE_URL.sub(" ", raw))):
        khuc = re.split("[-–—]", m.group())
        if (sum(any(c.isalpha() for c in k) for k in khuc) >= 2
                and not all(_RE_KHUC_CO.match(k) for k in khuc)):
            return True
    return False


#: Cách viết khác của một chữ trong danh sách từ ghép ("túi mầu đen").
_BIEN_THE = {"mầu": "màu"}


def _tu_trong_ds(chu: list[str], khoa: str) -> bool | None:
    """Các chữ liền nhau `chu` (khoá bỏ dấu `khoa`) là một từ trong `tu_ghep`? True = từ ghép có
    nghĩa, False = hư từ, None = không. So CÓ dấu (chữ gõ không dấu khớp mọi dạng): "cơ thể" ≠
    "có thể", "váy mà" ≠ "vậy mà"."""
    for mau, la_ghep in TG.DANG.get(khoa) or ():
        if all(w == x or w.isascii() or _BIEN_THE.get(w) == x for w, x in zip(chu, mau)):
            return la_ghep
    return None


def _bo_tag_ten(s: str) -> str:
    """Bỏ "@tài_khoản" và tên hiển thị viết hoa liền sau (xem `_RE_TAG_TEN`), để lại ranh giới."""
    def thay(m: re.Match) -> str:
        tu = m.group().split()
        i = 1
        while i < len(tu) and tu[i][:1].isupper():
            i += 1
        return " . " + " ".join(tu[i:]) + " "
    return _RE_TAG_TEN.sub(thay, s)


def _tach_don_vi(chu: list[str]) -> list[tuple[int, int, bool]]:
    """Tách một đoạn chữ thành TỪ: so khớp dài nhất từ trái sang với `tu_ghep` (`_tu_trong_ds`),
    không khớp thì là từ một âm tiết. -> [(đầu, cuối, là từ ghép có nghĩa)] theo chỉ số `chu`."""
    kd = [_kd(w) for w in chu]
    ra: list[tuple[int, int, bool]] = []
    i, n = 0, len(chu)
    while i < n:
        d = min(TG.DAI_NHAT, n - i) if kd[i] in TG.DAU else 1    # âm tiết không mở đầu từ nào
        la_ghep = None
        while d > 1:
            la_ghep = _tu_trong_ds(chu[i:i + d], " ".join(kd[i:i + d]))
            if la_ghep is not None:
                break
            d -= 1
        ra.append((i, i + d, bool(la_ghep)))
        i += d
    return ra


def _la_am_tiet(w: str) -> bool:
    """Chữ dùng được khi tách từ: toàn chữ cái, tối đa `_CHU_DAI_NHAT` ký tự (dài hơn là chuỗi gõ
    bừa), không có ba chữ cái liền giống nhau khi bỏ dấu ("ạaa"). Chữ MỘT ký tự vẫn tách được
    ("ý" trong "ý nghĩa") nhưng không ghép cặp (`_cap_duoc`: "e", "t", "a" là đại từ viết tắt)."""
    return (w.isalpha() and len(w) <= _CHU_DAI_NHAT
            and not _RE_KEO_DAI.search(_kd(w)))


def _cap_duoc(a: str, b: str) -> bool:
    """Hai từ ĐƠN liền nhau có thành cụm không: mỗi chữ ≥ 2 ký tự, không hư từ, không lặp, không
    mảnh câu hỏi giá, chữ đầu không phải chữ chỉ bổ nghĩa cho từ trước (`_KHONG_MO_DAU`), chữ cuối
    không phải lời gọi người bán (`_KHONG_KET_THUC`)."""
    if len(a) < 2 or len(b) < 2 or _hu_tu(a) or _hu_tu(b):
        return False
    ka, kb = _kd(a), _kd(b)
    if ka == kb or ka in _KHONG_MO_DAU or kb in _KHONG_KET_THUC or b in _GIA:
        return False
    return not (a in _GIA and kb not in _GIA_DANH_GIA)


def _tach_cum(r: dict) -> dict[str, str]:
    """{khoá bỏ dấu: mặt chữ} các cụm của MỘT bài / bình luận, mỗi khoá một lần:
      * hashtag (cột `hashtag` nối bằng dấu phẩy + "#…" trong nội dung): bỏ thẻ đẩy đề xuất
        (`_HASHTAG_CHUNG`), thẻ có số (#quatang2010, #sale1111 — thẻ mùa vụ/ngày/mã), thẻ < 3 ký
        tự; thẻ viết liền đúng một từ ghép ("#tuixach") đếm chung với từ đó ("túi xách");
      * từ ghép có nghĩa (`tu_ghep.GHEP`, sau khi tách từ bằng `_tach_don_vi`);
      * cặp hai từ ĐƠN liền nhau (`_cap_duoc`) — cặp âm tiết cắt ngang một từ ghép không tính.
    Chữ đã chuẩn hoá (`chuan_chu.chuan_hoa`: NFKC — chữ kiểu cách "𝐜𝐮𝐨̂́𝐢" không bị dấu rời cắt
    thành "cuo" —, teen code "mk" → "mình"), bỏ link, @tên, nhãn dán TikTok, chữ dính số; chữ kéo dài
    "đẹppp" về "đẹp". Khoá bỏ dấu gộp "màu đen" với "mau den"."""
    text = CC.chuan_hoa(_bo_tag_ten(_RE_URL.sub(" ", CC.nfkc(r.get("noi_dung")))))
    text = _RE_NHAN_DAN.sub(" . ", text)
    tags = set(_RE_HASHTAG.findall(text))
    # Thẻ YouTube có thể nhiều chữ ("túi xách nữ"): tách theo khoảng trắng sẽ ra hashtag giả —
    # chỉ tách theo dấu phẩy/chấm phẩy/#, bỏ thẻ có khoảng trắng.
    hs = CC.thuong(r.get("hashtag"))
    tags |= {t.strip() for t in re.split(r"[,;#]+", hs) if t.strip() and not re.search(r"\s", t.strip())}
    ra: dict[str, str] = {}
    for t in sorted(tags):
        k = _kd(t)
        if len(k) < 3 or any(ch.isdigit() for ch in k) or k in _HASHTAG_CHUNG_KD:
            continue
        lien = TG.LIEN.get(k.replace("_", ""))
        if lien is None:
            ra.setdefault("#" + k, "#" + t)
        elif lien in TG.GHEP and lien not in TG.HU:
            ra.setdefault(lien, TG.GHEP[lien])
    text = _RE_KEO_DAI.sub(r"\1", _RE_CHU_MA.sub(" . ", _RE_HASHTAG.sub(" ", text)))
    for doan in _RE_DOAN.split(text):
        # Đoạn liền nhau của những chữ dùng được; chữ không dùng được là ranh giới.
        for la, nhom in itertools.groupby(doan.split(), _la_am_tiet):
            if not la:
                continue
            chu = list(nhom)
            dv = _tach_don_vi(chu)
            for i, (a, b, la_ghep) in enumerate(dv):
                if b - a > 1:                          # một từ trong danh sách
                    if la_ghep:
                        ra.setdefault(" ".join(_kd(w) for w in chu[a:b]), " ".join(chu[a:b]))
                elif i + 1 < len(dv) and dv[i + 1][1] - dv[i + 1][0] == 1:
                    x, y = chu[a], chu[a + 1]          # hai từ đơn liền nhau
                    if _cap_duoc(x, y):
                        ra.setdefault(f"{_kd(x)} {_kd(y)}", f"{x} {y}")
    return ra


def _cum(r: dict) -> set[str]:
    """Mặt chữ các cụm của MỘT bài (xem `_tach_cum`)."""
    return set(_tach_cum(r).values())


def khoa_cum(c: str) -> str:
    """Khoá (bỏ dấu) của một cụm đang hiện — trùng khoá `_tach_cum` của mọi biến thể của nó."""
    c = " ".join(str(c or "").split())
    if c.startswith("#"):
        return "#" + _kd(c[1:].lower())
    return " ".join(_kd(w) for w in c.lower().split())


def _mat_chu(dem: collections.Counter) -> str:
    """Mặt chữ hiện cho một nhóm biến thể: bản gặp nhiều nhất; hoà thì bản có dấu."""
    return min(dem, key=lambda x: (-dem[x], -sum(not ch.isascii() for ch in x), x))


#: Màu mây từ theo NGƯỠNG (rà kho 16/10, luật "C2"): tô tích cực khi TC ≥ 25% số đã phân loại VÀ
#: TC ≥ 2 × TI; tiêu cực đối xứng; còn lại trung lập. Lấy nhãn lớn nhất tuyệt đối thì "yêu thương"
#: (TC 27%) vẫn xám dù chẳng ai chê.
NGUONG_SAC = 0.25
#: Một bài góp ≥ 60% số thảo luận của một cụm → hộp rê chuột cảnh báo "x% từ 1 bài".
TAP_TRUNG_MOT_BAI = 0.6


def sac_noi_troi(g: dict) -> str:
    """"tc" | "ti" | "tl" — sắc thái nổi trội của một cụm (xem `NGUONG_SAC`)."""
    tc, ti, tl = g.get(TC, 0), g.get(TI, 0), g.get(TL, 0)
    da = tc + ti + tl
    if tc and tc >= NGUONG_SAC * da and tc >= 2 * ti:
        return "tc"
    if ti and ti >= NGUONG_SAC * da and ti >= 2 * tc:
        return "ti"
    return "tl"


def _nguoi_viet(r: dict) -> tuple:
    """Người viết một dòng của mây từ: dòng bình luận (`tu_khoa_thao_luan` gắn `tac_gia_bl`) theo
    tên tác giả (chữ thường, bỏ @); bài theo nguồn / tài khoản đăng (`_khoa_nguon`). Không rõ thì
    coi mỗi dòng là một người — thiếu dữ liệu không được làm mất cụm."""
    if "tac_gia_bl" in r:
        t = " ".join(CC.thuong(r.get("tac_gia_bl")).split()).lstrip("@")
        return ("bl", t) if t else ("dong", id(r))
    k = _khoa_nguon(r)
    return k if k[0] != "link" or k[1] else ("dong", id(r))


def tu_khoa(rows: list[dict], tu_khoa_du_an: list[str] | tuple = (),
            toi_da: int = TOP_TU_KHOA) -> list[dict]:
    """Top cụm từ / hashtag (`_tach_cum`) theo SỐ THẢO LUẬN nhắc (bài không của kênh nhà), bỏ cụm
    chứa chính từ khoá của dự án (theo dõi "hapas" thì "túi hapas", "#hapasvn" không phải phát hiện
    gì). So trên dạng bỏ dấu + bỏ khoảng trắng; từ khoá < 3 ký tự thì không dùng để bỏ. Biến thể
    có/không dấu gộp một nhóm (đếm chung), hiện bằng mặt chữ gặp nhiều nhất. Cụm phải có ≥ 2 thảo
    luận từ ≥ `NGUOI_TOI_THIEU` người viết (`_nguoi_viet`), người nhiều nhất góp ≤ `MOT_NGUOI_TOI_DA`.
    Mỗi cụm kèm `mau` (sắc thái nổi trội, `sac_noi_troi`) và `mot_bai_pt` khi một bài góp ≥ 60%
    (dòng bình luận mang `khoa_bai`; bài tự là một bài)."""
    bo = {x for x in (re.sub(r"[\s#]+", "", _bo_dau(q)) for q in tu_khoa_du_an) if len(x) >= 3}
    dem: dict[str, dict] = {}
    mat: dict[str, collections.Counter] = {}
    theo_bai: dict[str, collections.Counter] = {}
    theo_nguoi: dict[str, collections.Counter] = {}
    for r in rows:
        if la_kenh_nha(r):
            continue
        s = sac(r)
        kb = r.get("khoa_bai") or r.get("khoa") or id(r)
        ng = _nguoi_viet(r)
        for k, c in _tach_cum(r).items():
            gon = re.sub(r"[\s#]+", "", k)
            if any(b in gon for b in bo):
                continue
            g = dem.setdefault(k, {"tu": c, "so_bai": 0, TC: 0, TI: 0, TL: 0, CHUA: 0})
            g["so_bai"] += 1
            g[s] += 1
            mat.setdefault(k, collections.Counter())[c] += 1
            theo_bai.setdefault(k, collections.Counter())[kb] += 1
            theo_nguoi.setdefault(k, collections.Counter())[ng] += 1
    ds = []
    for k, g in dem.items():
        ng = theo_nguoi[k]
        if (g["so_bai"] < TU_KHOA_TOI_THIEU_BAI or len(ng) < NGUOI_TOI_THIEU
                or max(ng.values()) > MOT_NGUOI_TOI_DA * g["so_bai"]):
            continue
        g["tu"] = _mat_chu(mat[k])
        g["mau"] = sac_noi_troi(g)
        nhieu_nhat = max(theo_bai[k].values())
        if nhieu_nhat >= TAP_TRUNG_MOT_BAI * g["so_bai"]:
            g["mot_bai_pt"] = round(100 * nhieu_nhat / g["so_bai"])
        ds.append(g)
    ds.sort(key=lambda g: (-g["so_bai"], g["tu"]))
    return ds[:toi_da]


# ───────────────────────── gộp ─────────────────────────
def _top_nguon_tong_hop(rows: list[dict], sap: str, moi_cach: bool) -> dict:
    SAP_NGUON[sap]
    if not moi_cach:
        return {"top_nguon": top_nguon(rows, sap=sap), "sap_nguon": sap}
    theo = top_nguon_moi_cach(rows)
    return {"top_nguon": theo[sap], "sap_nguon": sap, "top_nguon_theo": theo}


def tong_hop(rows: list[dict], tu: datetime.date, den: datetime.date, *,
             tu_khoa_du_an: list[str] | tuple = (), nen_tang: str | None = None,
             loai_nguon: str | None = None, hom_nay: datetime.date | None = None,
             bo_loc=None, sap_nguon: str = "thao_luan", moi_cach_xep: bool = False) -> dict:
    """Mọi khối của trang Chỉ số. `rows` gồm bài của CẢ kỳ này lẫn kỳ trước (kho đọc một lần
    từ đầu kỳ trước); hàm tự chia. `bo_loc` (bộ lọc chung) áp cho CẢ hai kỳ — so sánh cùng một
    tập. `sap_nguon`: cách xếp bảng Nguồn nổi bật (`SAP_NGUON`); `moi_cach_xep`: thêm
    `top_nguon_theo` = {sap: bảng} cho mọi cách (bộ nhớ đệm của /api/chi-so). -> dict thuần JSON."""
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
            v["doi_pt"], v["moi"] = None, False
    return {
        "khoang": {"tu": tu.isoformat(), "den": den.isoformat(),
                   "so_ngay": (den - tu).days + 1,
                   "ky_truoc": {"tu": tu_truoc.isoformat(), "den": den_truoc.isoformat()}},
        "kpi": k_nay, "kpi_truoc": k_truoc, "so_sanh": ss, "so_sanh_lech": lech,
        "xu_huong": xu_huong(nay, tu, den, hom_nay),
        "sac_thai": sac_thai(nay), "sac_thai_chu_de": sac_thai_chu_de(nay),
        "sac_thai_nen_tang": sac_thai_nen_tang([r for r in nay if not la_kenh_nha(r)]),
        "nen_tang": phan_bo_nen_tang(nay), "loai_nguon": phan_bo_loai(nay),
        **_top_nguon_tong_hop(nay, sap_nguon, moi_cach_xep),
        "tu_khoa": tu_khoa(nay, tu_khoa_du_an),
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
          cum=None, ngoai_nha=False) -> bool:
    # ngoai_nha (19/10/2026): bỏ bài kênh nhà — "Chi tiết" của hàng Sắc thái theo nền tảng đếm
    # đúng tập vòng sắc thái (không kênh nhà) nên danh sách phải khớp con số của hàng.
    if ngoai_nha and kenh_nha:
        return False
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
    # Cụm từ khoá: so theo KHOÁ bỏ dấu — mây từ gộp "xin gia"/"xin giá" thành một nhóm.
    return not (cum and (kenh_nha or khoa_cum(cum) not in _tach_cum(r)))


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
            "ly_do_loc": c.get("ly_do_loc") or "",
            # Món khách hỏi mua (17/10/2026) — chỉ bình luận HỎI MUA (kể cả hỏi đồ ngoài brand,
            # để thấy vì sao không tính); "" với bình luận khác dù kho có món.
            "san_pham": SAN_PHAM[san_pham_bl(c)] if lb == "hop_le" and _hoi_mua(c) else ""}


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

    # Tiêu cực chia đôi theo chủ đề (19/10/2026): chê sản phẩm / giá / dịch vụ / so đối thủ là
    # tiếng về THƯƠNG HIỆU; chê KOL, nội dung clip, minigame, tag bạn… thì không.
    ti_th = sum(1 for c in khach if sac_bl(c) == TI
                and str(c.get("chu_de") or "").strip() in CHU_DE_BL_THUONG_HIEU)

    def pt(x: str) -> float | None:
        return round(100.0 * dem[x] / da, 1) if da else None
    return {
        "loai": [{"loai": k, "ten": TEN_LOAI_BL[k], "so": theo_loai[k]} for k in LOAI_BL
                 if theo_loai[k]],
        "sac_thai_nen_tang": sac_thai_nen_tang(khach, sac_bl),
        "kpi": {"so": len(rows), "khach": len(khach), "sach": len(khach),
                "da_loc": len(rows) - len(khach) - theo_loai["thuong_hieu"],
                "thuong_hieu": theo_loai["thuong_hieu"],
                "so_bai": len({c.get("khoa_bai") for c in rows}), "da_phan_loai": da,
                "tich_cuc": dem[TC], "tieu_cuc": dem[TI], "trung_lap": dem[TL],
                "chua_phan_loai": dem[CHUA], "tich_cuc_pt": pt(TC), "tieu_cuc_pt": pt(TI),
                "trung_lap_pt": pt(TL),
                "tieu_cuc_thuong_hieu": ti_th, "tieu_cuc_khac": dem[TI] - ti_th},
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
                nen_tang=None, loai_nguon=None, loai=None, nguon=None, q=None, cum=None,
                y_dinh: bool | str = False, khoa_bai: str | None = None,
                sap_xep: str = "thich", moi_trang: int = MOI_TRANG, bo_loc=None,
                bai_theo_khoa: dict | None = None) -> dict:
    """Luồng bình luận lọc theo các trường (kiểu Kompa): nền tảng, nguồn, sắc thái, chủ đề,
    nhãn lọc, chữ tìm (`chuan_chu.khoa`: bỏ dấu, teen code, chữ kiểu cách — nội dung + tác giả),
    khoảng ngày; sắp xếp nhiều thích / mới / cũ — AND với bộ lọc chung `bo_loc` (xem phần "bộ
    lọc chung"). Ngăn từ khoá gửi `cum`: khớp đúng như mây từ đếm (`_tach_cum` trên nội dung, KHÔNG
    xét tên tác giả) để số trong ngăn bằng số trên mây. `y_dinh`: chỉ bình luận ý định mua
    (True / "1") hoặc chỉ bình luận hỏi mua MỘT món (mã `SAN_PHAM`); `khoa_bai`: chỉ bình luận
    của một bài (khối Ý định mua).
    -> {tong, trang, so_trang, binh_luan, facets}. `facets` = {trường: [{gia_tri, ten, so}]}
    đếm trên các dòng khớp MỌI điều kiện TRỪ chính trường đó (chọn tiếp được giá trị khác)."""
    chu = CC.khoa_tim(q) if q else ""
    kc = khoa_cum(cum) if cum else ""
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
        if khoa_bai and c.get("khoa_bai") != khoa_bai:
            continue
        if chu and not CC.chua(chu, f"{c.get('noi_dung') or ''} {c.get('tac_gia') or ''}"):
            continue
        if kc and (kc not in _tach_cum({"noi_dung": c.get("noi_dung")}) or
                   (not f.gom_mg and _chu_de(c) == CHU_DE_MINIGAME) or
                   la_rac_quang_cao(c.get("noi_dung"))):
            continue                       # như mây: minigame ẩn trừ khi gom_mg=1; rác quảng cáo bỏ
        if y_dinh and not khop_y_dinh(c, "1" if y_dinh is True else str(y_dinh)):
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
    hợp lệ (không spam, không của thương hiệu) trong kỳ, cùng bộ lọc chung. Bình luận chủ đề
    minigame (`CHU_DE_MINIGAME`) mặc định KHÔNG vào mây — lời chúc dự thi không phải cảm nhận về
    brand; bộ lọc `gom_mg=1` gồm lại. Bình luận mang dấu hiệu rác quảng cáo (`la_rac_quang_cao`)
    không vào mây và không vào `tong`. -> {"tu_khoa": [{tu, so_bai (= số thảo luận nhắc),
    sắc thái…, mau, mot_bai_pt?}], "tong", "an_minigame"}."""
    f = bien_dich(_gop(bo_loc, nen_tang, loai_nguon))
    b = loc_bai(trong_khoang(bai, tu, den), f)
    c = loc_bl([x for x in bl if loai_bl(x) == "hop_le"
                and (n := _ngay_bl(x)) is not None and tu <= n <= den], f, bai_theo_khoa)
    an_mg = 0
    if not f.gom_mg:
        con = [x for x in c if _chu_de(x) != CHU_DE_MINIGAME]
        an_mg, c = len(c) - len(con), con
    c = [x for x in c if not la_rac_quang_cao(x.get("noi_dung"))]
    # Bình luận: chữ + sắc thái + bài của nó (cảnh báo tập trung) + người viết (cụm một người viết
    # lặp không lên mây) — không gắn nguồn: bình luận dưới bài kênh nhà là tiếng khách.
    dong = b + [{"noi_dung": x.get("noi_dung") or "", "sac_thai": x.get("sac_thai"),
                 "khoa_bai": x.get("khoa_bai"), "tac_gia_bl": x.get("tac_gia") or ""} for x in c]
    return {"tu_khoa": tu_khoa(dong, tu_khoa_du_an),
            "tong": sum(not la_kenh_nha(r) for r in b) + len(c), "an_minigame": an_mg}


# ───────────────────────── ý định mua (16/10/2026) ─────────────────────────
# Rà kho 15/10: 451/994 bình luận sạch (45%) có chủ đề "Giá/mua ở đâu/ý định mua", 323 (32,5%)
# khớp câu hỏi giá — tất cả nằm lẫn trong "Trung lập", trang không có chỉ số nào cho nó. Ý ĐỊNH MUA
# = bình luận HỢP LỆ mà AI gán chủ đề đó HOẶC là câu hỏi giá/mua (`_RE_Y_DINH_MUA`, so trên khoá
# `chuan_chu.khoa`: bỏ dấu, teen code "bn" = bao nhiêu, "mk" = mình). Spam affiliate ("dán mã vào
# sộp-pii là ra giá") đã bị `loc_rac` loại khỏi hop_le nên không vào đây.
CHU_DE_MUA = "Giá/mua ở đâu/ý định mua"
TOP_BAI_Y_DINH = 20
_RE_Y_DINH_MUA = re.compile(
    r"\b(?:"
    r"(?:hoi|xin|bao|check|cho (?:minh|em|chi|toi|xin))(?: xin)? gia"
    r"|gia (?:sao|bao nhieu|nhieu|nhiu|may|the nao|ntn|ra sao|shop|sp|a|ah|ak|nhe|oi)"
    r"|bao nhieu(?! (?:tuoi|nguoi|lan|ngay|nam|thang|gio|phut|km|cm|kg|follow))"
    r"|ib|ibx|inb|inbox"
    r"|(?:mua|ban|order|dat) (?:o|tai) (?:dau|nao)|o dau (?:ban|mua|co ban)"
    r"|mua (?:the nao|ntn|sao|nhu nao|kieu gi|o shop nao)"
    r"|xin link|link mua|link (?:sp|san pham|dat hang|shopee)|cho (?:minh|em|xin) link|co link"
    r"|con hang|het hang chua|con (?:size|sz|mau)"
    r"|con khong(?= (?:a|shop|ban|em|chi|vay|nhi)\b|\W*$)"
    r"|(?:co|con|lay|chon|tu van|het) size|size (?:nao|gi|bao nhieu|may|s|m|l|xl|xxl|\d{2})"
    r"|(?:co|duoc|nhan) ship|phi ship|ship (?:cod|ve|toi|den|ra|tinh|bao nhieu|khong|may ngay)"
    # "đặt hàng 5 ngày chưa nhận", "order rồi mà…" là phàn nàn sau khi mua, không phải ý định mua.
    r"|(?:dat hang|order)(?! (?:roi|r|xong|\d|ma|tu|lau|hom|bi|chua nhan))"
    r"|dat mua|dat (?:set|do|don)|chot don|len don|muon (?:mua|dat)|can mua"
    r")\b")
#: "ib"/"inbox" đứng riêng: lời người bán ("Nàng ib e nha", "Bạn inbox cho kênh hỗ trợ") cũng có —
#: không tính khi AI gán Giao hàng/dịch vụ (`_hoi_mua`).
_RE_IB = re.compile(r"\b(?:ib|ibx|inb|inbox)\b")
#: Chủ đề AI nói rõ bình luận nói chuyện khác (nội dung/KOL, minigame, tag bạn, đối thủ): câu chữ
#: kiểu "bao nhiêu", "ib" không đủ để lật lại thành ý định mua.
_CD_KHONG_MUA = frozenset({"KOL/nội dung", CHU_DE_MINIGAME, "Tag bạn bè", "Đối thủ"})
_CD_DICH_VU = "Giao hàng/dịch vụ"
_RE_CHI_GIA = re.compile(r"\W*gia\W*")                 # cả bình luận chỉ là "Giá?"


def _hoi_mua(c: dict) -> bool:
    """Bình luận hợp lệ mang dấu hiệu hỏi mua (chủ đề AI hoặc câu hỏi giá/mua) — CHƯA xét món.

    Chủ đề AI "Giá/mua…" (không Tiêu cực) là nguồn chính; câu chữ chỉ là lưới HẸP bắt phần AI
    chưa gán / gán chủ đề khác. Rà kho 17/10/2026: 103 bình luận chỉ khớp câu chữ, đọc tay 76 sai
    (≈ 74%) — lời người bán trả lời khách ("Nàng ib e nha", "Bạn inbox cho kênh hỗ trợ" — fanpage
    phụ chưa nhận ra là thương hiệu), "bn" = bạn ("Siêu bn thân"), câu về người trong video. Nên:
      • TRẢ LỜI (la_tra_loi) mà AI không gán "Giá/mua…": không tính (gần như toàn lời người bán /
        người khác chỉ cách nhắn shop);
      • AI gán nội dung/KOL, minigame, tag bạn, đối thủ: không tính;
      • "ib"/"inbox" đứng riêng không tính khi AI gán Giao hàng/dịch vụ (lời mời nhắn của shop);
      • "bn" = bạn theo ngữ cảnh (`chuan_chu`)."""
    if loai_bl(c) != "hop_le":
        return False
    cd = _chu_de(c)
    # Chủ đề "Giá/mua…" gộp cả lời CHÊ giá ("hợp kim mà giá cỡ đấy :)))", "nhìn giá và lặng lẽ
    # rời đi" — tập đánh giá 17/10/2026): bình luận Tiêu cực chỉ tính khi có câu hỏi giá/mua.
    if cd == CHU_DE_MUA and sac_bl(c) != TI:
        return True
    if cd in _CD_KHONG_MUA or (c.get("la_tra_loi") and cd != CHU_DE_MUA):
        return False
    k = CC.khoa(c.get("noi_dung"))
    if _RE_CHI_GIA.fullmatch(k):
        return True
    if cd == _CD_DICH_VU:
        k = _RE_IB.sub(" ", k)
    return bool(_RE_Y_DINH_MUA.search(k))


def la_y_dinh_mua(c: dict) -> bool:
    """Bình luận có Ý ĐỊNH MUA: hợp lệ VÀ (chủ đề AI "Giá/mua ở đâu/ý định mua" mà không Tiêu cực,
    HOẶC câu hỏi giá/mua: hỏi/xin giá, giá bao nhiêu/bn, ib/inbox, mua ở đâu, xin link, còn
    hàng/size, ship, đặt hàng…) VÀ AI không nói món là đồ KHÔNG phải của brand (`SP_NGOAI`,
    17/10/2026: "xin link chân váy chị mặc" dưới bài KOL không phải khách hỏi mua hàng của
    brand). Thuần, không gọi mạng."""
    return c.get("san_pham") != SP_NGOAI and _hoi_mua(c)


# ── MÓN khách hỏi mua (17/10/2026) ──
# Chủ dự án: "đôi khi người dùng hỏi mua những cái khác nhưng đang bị đánh vào hỏi mua túi". Kho
# 16/10: 1.798 bình luận ý định mua, 1.456 không nói tên món — món nằm ở BÀI (hộp quà 20/10 gồm túi
# + ví + nước hoa, gắn #tuixachhapas); 244 hỏi set/combo, ~55 nói "túi". AI gán món khi gán nhãn
# (`binh_luan.san_pham`, đọc cả bài). Dòng chưa có món (gán trước 17/10, hoặc lượt cào gán ngay) lùi
# về CHỮ trong chính bình luận — luật an toàn: chỉ khi bình luận nói tên món; không đoán theo bài
# (hashtag túi xách gắn cả bài set quà, bài KOL — đoán theo bài là lặp lại đúng lỗi), không bao giờ
# ra `ngoai_brand` (cần biết brand bán gì). So trên chữ CÓ DẤU: "túi" khác "tui" (= tôi).
_RE_SP_SET = re.compile(
    r"(?<!\w)(?:(?<!sấm )s[eé]t(?! (?:đồ|đánh))|combo|box|gift ?box|h[ộo]p qu[àa]|b[ộo] qu[àa])"
    r"(?!\w)")
_RE_SP = (
    ("tui", re.compile(r"(?<!\w)(?:túi|balo|ba lô|clutch|tote|tui xach)(?!\w)")),
    ("vi", re.compile(r"(?<!\w)(?:ví(?! dụ)|bóp)(?!\w)")),
    ("nuoc_hoa", re.compile(r"(?<!\w)(?:nước hoa|nuoc hoa|perfume)(?!\w)")),
    ("trang_suc", re.compile(
        r"(?<!\w)(?:dây chuyền|day chuyen|vòng cổ|vòng tay|lắc tay|lắc chân|nhẫn|bông tai|"
        r"khuyên tai|trang sức|trang suc|charm)(?!\w)")),
    ("khac", re.compile(
        r"(?<!\w)(?:váy|đầm|áo|quần|giày|dép|thắt lưng|dây lưng|khăn|mũ|nón|kính|băng đô|"
        r"móc khoá|móc khóa|son|đồng hồ|set đồ)(?!\w)")),
)


def san_pham_tu_chu(text) -> str | None:
    """Món nói THẲNG trong bình luận (luật lùi khi AI chưa gán món), None khi không nói tên. Có
    set/combo/hộp quà → set quà ("xin giá set túi trắng" hỏi cả set); còn lại món nhắc trước."""
    t = unicodedata.normalize("NFC", " ".join(str(text or "").split())).lower()
    if _RE_SP_SET.search(t):
        return "set_qua"
    gap = [(m.start(), ma) for ma, r in _RE_SP if (m := r.search(t))]
    return min(gap)[1] if gap else None


def san_pham_bl(c: dict) -> str:
    """Mã MÓN của một bình luận hỏi mua: AI gán (`san_pham`) → chữ trong bình luận → chưa rõ."""
    sp = c.get("san_pham")
    if sp in SAN_PHAM:
        return sp
    return san_pham_tu_chu(c.get("noi_dung")) or SP_CHUA_RO


def khop_y_dinh(c: dict, gt: str) -> bool:
    """Giá trị lọc `y_dinh`: "1" = mọi ý định mua; mã món = ý định mua của món đó."""
    return la_y_dinh_mua(c) and (gt == "1" or san_pham_bl(c) == gt)


def y_dinh_mua(rows: list[dict], tu: datetime.date, den: datetime.date, *,
               rows_truoc: list[dict] | None = None, truoc_bi_cat: bool = False,
               nay_bi_cat: bool = False, hom_nay: datetime.date | None = None, bo_loc=None,
               bai_theo_khoa: dict | None = None, toi_da: int = TOP_BAI_Y_DINH) -> dict:
    """Khối "Ý định mua" của trang Chỉ số, theo bộ lọc chung `bo_loc` (cả kỳ trước).

    `rows` = bình luận của [tu, den]; `rows_truoc` = bình luận của kỳ liền trước cùng độ dài
    (None: không so). % so với kỳ trước không hiện khi kỳ trước 0, khi kỳ này / kỳ trước bị cắt
    bớt dòng (`nay_bi_cat`, `truoc_bi_cat`) hoặc khi lọc theo mức tương tác (tương tác cộng dồn
    theo tuổi bài). Mẫu số "bình luận sạch" bỏ chiều y_dinh của bộ lọc (không thì luôn 100%).
    Đang lọc MỘT món (y_dinh = mã món) thì số / cột / top bài chỉ đếm món đó; `theo_san_pham`
    luôn chia MỌI ý định mua theo món (17/10/2026) để thấy khách hỏi món gì.
    -> {so, sach, pt, truoc, doi_pt, theo_chu_de, theo_cau, xu_huong, top_bai, theo_san_pham,
    san_pham_loc, sp_ai, ngoai_brand}."""
    hom_nay = hom_nay or datetime.datetime.now(VN).date()
    goc = bien_dich(bo_loc)
    gt = goc.yd or "1"
    f = goc.bo_y_dinh()

    def sach(ds: list[dict], a: datetime.date, b: datetime.date) -> list[dict]:
        return loc_bl([c for c in ds if loai_bl(c) == "hop_le"
                       and (n := _ngay_bl(c)) is not None and a <= n <= b], f, bai_theo_khoa)
    nay = sach(rows, tu, den)
    tat = [c for c in nay if la_y_dinh_mua(c)]
    yd = tat if gt == "1" else [c for c in tat if san_pham_bl(c) == gt]
    truoc = None
    if rows_truoc is not None:
        a, b = khoang_truoc(tu, den)
        truoc = sum(1 for c in sach(rows_truoc, a, b) if khop_y_dinh(c, gt))
    so_sanh_duoc = truoc is not None and not (truoc_bi_cat or nay_bi_cat or f.tt)
    theo_tuan = (den - tu).days + 1 > NGAY_TOI_DA_THEO_NGAY
    cuoi = max(tu, min(den, hom_nay))
    moc = _cac_moc(tu, cuoi, theo_tuan)
    chi = {m: i for i, m in enumerate(moc)}
    cot = {"so": [0] * len(moc), "sach": [0] * len(moc)}
    for c in nay:
        n = _ngay_bl(c)
        if n > cuoi:
            continue
        i = chi[max(tu, n - datetime.timedelta(days=n.weekday())) if theo_tuan else n]
        cot["sach"][i] += 1
    for c in yd:
        n = _ngay_bl(c)
        if n <= cuoi:
            cot["so"][chi[max(tu, n - datetime.timedelta(days=n.weekday())) if theo_tuan else n]] += 1
    sach_bai = collections.Counter(c.get("khoa_bai") for c in nay)
    dem_bai = collections.Counter(c.get("khoa_bai") for c in yd)
    mau: dict = {}
    sp_bai: dict = {}
    for c in yd:
        mau.setdefault(c.get("khoa_bai"), c)
        sp_bai.setdefault(c.get("khoa_bai"), collections.Counter())[san_pham_bl(c)] += 1
    top = []
    for k, n in sorted(dem_bai.items(), key=lambda x: (-x[1], str(x[0])))[:toi_da]:
        c = mau[k]
        # Món khách dưới bài này hỏi NHIỀU nhất (bỏ "chưa rõ" nếu có món rõ) — đọc nhanh "bài
        # này khách hỏi set quà", không phải đoán theo hashtag của bài.
        ro = [(-v, ma) for ma, v in sp_bai[k].items() if ma != SP_CHUA_RO]
        sp = min(ro)[1] if ro else SP_CHUA_RO
        top.append({"khoa_bai": k or "", "so": n, "sach": sach_bai[k],
                    "nen_tang": c.get("nen_tang") or "", "tac_gia": c.get("bai_tac_gia") or "",
                    "nguon": khoa_nguon_bl(c)[1], "link": "", "noi_dung": "", "dang_luc": None,
                    "san_pham": sp, "ten_san_pham": SAN_PHAM[sp], "so_san_pham": sp_bai[k][sp]})
    theo_cd = sum(1 for c in yd if _chu_de(c) == CHU_DE_MUA)
    dem_sp = collections.Counter(san_pham_bl(c) for c in tat)
    thu_tu = list(SAN_PHAM)
    theo_sp = [{"ma": ma, "ten": SAN_PHAM[ma], "so": v}
               for ma, v in sorted(dem_sp.items(), key=lambda x: (
                   x[0] == SP_CHUA_RO, -x[1], thu_tu.index(x[0])))]
    return {"so": len(yd), "sach": len(nay),
            "pt": round(100.0 * len(yd) / len(nay), 1) if nay else None,
            "truoc": truoc, "doi_pt": doi_pt(len(yd), truoc) if so_sanh_duoc else None,
            "moi": bool(so_sanh_duoc and not truoc and yd),
            "theo_chu_de": theo_cd, "theo_cau": len(yd) - theo_cd,
            "xu_huong": {"don_vi": "tuần" if theo_tuan else "ngày",
                         "moc": [m.isoformat() for m in moc], **cot},
            "top_bai": top,
            "theo_san_pham": theo_sp, "san_pham_loc": "" if gt == "1" else gt,
            "sp_ai": sum(1 for c in tat if c.get("san_pham") in SAN_PHAM),
            "ngoai_brand": sum(1 for c in nay if c.get("san_pham") == SP_NGOAI and _hoi_mua(c))}


def gan_ngu_canh_y_dinh(top: list[dict], ngu_canh: dict[str, dict]) -> None:
    """Link + đoạn nội dung + giờ đăng của các bài top ý định mua (`kho.ngu_canh_bai`)."""
    for x in top:
        b = ngu_canh.get(x.get("khoa_bai"))
        if b:
            x.update(link=b.get("bai_link") or "", dang_luc=_iso_vn(b.get("bai_dang_luc")),
                     noi_dung=" ".join(str(b.get("bai_noi_dung") or "").split())[:200])


# ───────────────────────── đếm cho ô lọc + kênh nhà vs bên ngoài ─────────────────────────
NGUON_TOI_DA_DEM = 80


def _phia() -> dict:
    return {"bai": 0, "thao_luan": 0, "bl": 0, "bl_hop_le": 0,
            "sac_bai": dict.fromkeys(MA_SAC, 0), "sac_bl": dict.fromkeys(MA_SAC, 0)}


def _nhom_koc() -> dict:
    return {"bai": 0, "thao_luan": 0, "xem": 0, "tuong_tac": 0, "quang_cao": 0,
            "sac_bai": dict.fromkeys(MA_SAC, 0), "nguoi": set()}


def _loai_koc_json(koc: dict[str, dict]) -> dict:
    """Khối "KOC affiliate vs branding" (20/10/2026): mỗi nhóm số video, nhà sáng tạo, thảo luận,
    lượt xem, tương tác, video quảng cáo (is_ads), sắc thái bài + % trên tổng ba nhóm. `tong` =
    tổng của video TikTok External channel khớp mọi bộ lọc TRỪ chính chiều "Loại KOC"."""
    tong = {k: sum(g[k] for g in koc.values()) for k in ("bai", "thao_luan", "xem", "tuong_tac")}

    def pt(a, b):
        return round(100.0 * a / b, 1) if b else None
    return {"tong": tong, "nhom": [
        {"ma": k, "ten": KOC[k], **{x: g[x] for x in ("bai", "thao_luan", "xem", "tuong_tac",
                                                        "quang_cao", "sac_bai")},
         "nguoi": len(g["nguoi"]), **{f"{x}_pt": pt(g[x], tong[x]) for x in tong}}
        for k, g in koc.items()]}


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
    koc = {k: _nhom_koc() for k in KOC}
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
        if m in (0, _BIT["kieu_trang"]) and r.get("kieu_trang") in KIEU_TRANG:
            dem["kieu_trang"][r["kieu_trang"]] += 1
        if m in (0, _BIT["koc"]) and (nk := nhom_koc(r)) is not None:
            dem["koc"][nk] += 1
            g = koc[nk]
            g["bai"] += 1
            g["thao_luan"] += thao_luan(r)
            g["xem"] += so(r.get("xem"))
            g["tuong_tac"] += tuong_tac_bai(r)
            g["sac_bai"][SAC_MA[sac(r)]] += 1
            g["quang_cao"] += 1 if r.get("la_quang_cao") is True else 0
            g["nguoi"].add(_khoa_nguon(r))
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
                                    "kieu_quet", "kieu_trang", "koc")}
    return {"bo_loc_dem": {**don, "sac_thai": {k: {"bai": dem["sac_thai"][k],
                                                   "bl": sac_bl_dem[k]} for k in MA_SAC},
                           "chu_de": chu_de, "nguon": nguon},
            "nha_ngoai": nha, "loai_koc": _loai_koc_json(koc)}


#: Nhãn + giá trị của thanh lọc cho trình duyệt (một nguồn sự thật với phần kiểm ở máy chủ).
NHAN_BO_LOC = {
    "pham_vi": PHAM_VI, "nen_tang": TEN_NEN_TANG, "loai": TEN_LOAI,
    "sac_thai": {k: v[0].upper() + v[1:] for k, v in MA_SAC.items()},
    "anh_huong": ANH_HUONG, "kieu_quet": KIEU_QUET, "kieu_trang": KIEU_TRANG, "y_dinh": Y_DINH,
    "koc": KOC,
    "tuong_tac": [{"gia_tri": str(m), "ten": f"Từ {m:,}".replace(",", ".") + " tương tác"}
                  for m in TUONG_TAC_MUC],
}


# ───────────────────────── độ phủ (kiểm 2 lần/tuần của Mark, 17/10/2026) ─────────────────────────
#: Độ phủ theo thảo luận dưới ngưỡng này thì thẻ "Độ phủ" chuyển màu cảnh báo.
NGUONG_DO_PHU = 80.0
#: Lần kiểm gần nhất cũ hơn chừng này ngày (Mark kiểm hai lần mỗi tuần) — thẻ nói "đã cũ".
DO_PHU_CU_NGAY = 7
SOT_HIEN = 10


def _url_an_toan(u) -> str:
    u = str(u or "")
    return u if re.match(r"https?://", u, re.I) else ""


def _so_hay_none(v):
    try:
        return None if v is None else round(float(v), 2)
    except (TypeError, ValueError):
        return None


def do_phu_json(rows: list[dict], bay_gio: datetime.datetime) -> dict | None:
    """Thẻ "Độ phủ" từ `kho.do_phu_gan_nhat` (mới nhất trước). Không có lượt kiểm → None.

    Số chính = độ phủ theo thảo luận (`do_phu_tl`); ▲/▼ = chênh ĐIỂM % với lần kiểm trước (không
    phải % thay đổi); `canh_bao` khi dưới `NGUONG_DO_PHU`. Danh sách bài sót chỉ giữ trường cần
    hiện, link không phải http(s) bỏ trống."""
    if not rows:
        return None
    r, truoc = rows[0], (rows[1] if len(rows) > 1 else None)
    tl = _so_hay_none(r.get("do_phu_tl"))
    tl_truoc = _so_hay_none((truoc or {}).get("do_phu_tl"))
    luc = r.get("luc")
    mau = r.get("mau") if isinstance(r.get("mau"), dict) else {}
    sot = []
    for x in (r.get("bai_sot") if isinstance(r.get("bai_sot"), list) else [])[:SOT_HIEN]:
        if not isinstance(x, dict):
            continue
        sot.append({"link": _url_an_toan(x.get("link")),
                    "tai_khoan": str(x.get("tai_khoan") or "")[:100],
                    "ten": str(x.get("ten") or "")[:120], "thao_luan": so(x.get("thao_luan")),
                    "binh_luan": so(x.get("binh_luan")), "thich": so(x.get("thich")),
                    "xem": so(x.get("xem")), "dang_luc": str(x.get("dang_luc") or "")[:25],
                    "noi_dung": str(x.get("noi_dung") or "")[:200],
                    "ly_do": [str(y)[:120] for y in (x.get("ly_do") or [])[:3]],
                    "duong": [str(y)[:60] for y in (x.get("duong") or [])[:3]],
                    "hanh_dong": [str(y)[:120] for y in (x.get("hanh_dong") or [])[:5]],
                    "bo_sung": bool(x.get("bo_sung"))})

    def ten(ds) -> list[str]:
        return [str(x.get("ten") or "")[:60] for x in ds if isinstance(x, dict)][:10]
    cu = bool(isinstance(luc, datetime.datetime)
              and bay_gio - luc > datetime.timedelta(days=DO_PHU_CU_NGAY))
    return {"luc": luc.isoformat(timespec="minutes") if isinstance(luc, datetime.datetime)
            else (str(luc) if luc else None),
            "nen_tang": r.get("nen_tang") or "tiktok", "do_phu_tl": tl,
            "do_phu": _so_hay_none(r.get("do_phu")),
            **{k: so(r.get(k)) for k in ("so_mau", "so_nhac", "so_da_co", "so_sot",
                                         "so_da_loai", "bo_sung", "so_yeu_cau")},
            "chi_phi_usd": _so_hay_none(r.get("chi_phi_usd")) or 0.0,
            "truoc": None if truoc is None else {
                "do_phu_tl": tl_truoc,
                "luc": truoc["luc"].isoformat(timespec="minutes")
                if isinstance(truoc.get("luc"), datetime.datetime) else None},
            "doi_diem": None if tl is None or tl_truoc is None else round(tl - tl_truoc, 1),
            "canh_bao": tl is not None and tl < NGUONG_DO_PHU, "nguong": NGUONG_DO_PHU,
            "cu": cu, "cu_ngay": DO_PHU_CU_NGAY, "tag": ten(mau.get("tag") or []),
            "tac_gia": ten(mau.get("tac_gia") or []),
            "ngay_mau": so(mau.get("ngay")) or 30, "bai_sot": sot,
            "tran_usd": _so_hay_none(mau.get("tran_usd")),
            "ly_do": ly_do_tong(r.get("bai_sot")),
            "hanh_dong": hanh_dong_json(r.get("hanh_dong"))}


#: Nhãn ngắn của mã lý do sót (`kiem_do_phu.LY_DO`) cho dòng tóm tắt thẻ.
LY_DO_NGAN = {"chi_hashtag": "chỉ có hashtag", "ngoai_cua_so": "ngoài cửa sổ tuần",
              "it_thich": "ít thích", "tac_gia_moi": "nhà sáng tạo mới", "khac": "khác"}


def ly_do_tong(sot) -> list[dict]:
    """Đếm mã lý do trên các bài sót đã lưu (nhiều nhất trước)."""
    dem: collections.Counter = collections.Counter()
    for x in sot if isinstance(sot, list) else []:
        for m in (x.get("ma_ly_do") or []) if isinstance(x, dict) else []:
            dem[str(m)] += 1
    return [{"ma": m, "ten": LY_DO_NGAN.get(m, m), "so": n}
            for m, n in sorted(dem.items(), key=lambda kv: (-kv[1], kv[0]))]


def hanh_dong_json(hd) -> dict:
    """Việc Mark đã tự làm (`kiem_do_phu.hanh_dong` tóm tắt) — chỉ trường hiển thị."""
    hd = hd if isinstance(hd, dict) else {}
    noi = hd.get("noi") if isinstance(hd.get("noi"), dict) else {}
    return {"de_xuat": [{"dinh_danh": str(g.get("dinh_danh") or "")[:100],
                         "so_bai": so(g.get("so_bai")), "thao_luan": so(g.get("thao_luan")),
                         "uu_tien": bool(g.get("uu_tien"))}
                        for g in (hd.get("de_xuat") or [])[:20] if isinstance(g, dict)],
            "tag_them": [str(t)[:60] for t in (hd.get("tag_them") or [])[:10]],
            "tag_noi": [str(t)[:60] for t in (hd.get("tag_noi") or [])[:10]],
            "noi_ly_do": str(noi.get("ly_do") or "")[:200]}


def noi_tu_hanh_dong(hd) -> dict:
    """Cấu hình lượt nổi + trần trang "mới nhất" TikTok mà Mark đang dùng sau lần kiểm cuối
    (trang Ngân sách)."""
    hd = hd if isinstance(hd, dict) else {}
    noi = hd.get("noi") if isinstance(hd.get("noi"), dict) else {}

    def sau(k):
        x = noi.get(k)
        return so(x[-1]) if isinstance(x, list) and x else None
    return {"tag": [str(t)[:60] for t in (hd.get("tag_noi") or [])[:10]],
            "trang": sau("trang"), "gio": sau("gio"), "moi_trang": sau("moi_trang")}
