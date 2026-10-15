"""Lọc spam / rác / trùng cho dữ liệu lắng nghe (đợt 2d, chủ dự án 15/10/2026: "tìm hiểu kĩ cơ
chế lọc spam, chống trùng... và 1 bài thì phải cào hết tất cả thảo luận sau khi đã áp dụng cơ chế").

Cách các nền tảng chuyên nghiệp làm (Talkwalker `noise_category`, Sprinklr spam classifier,
Meltwater gom bản trùng, Kompa/YouNet "loại spam, clone, seeding"): GIỮ dữ liệu thô, GẮN NHÃN
lý do, và báo cáo SỐ SẠCH bên cạnh số thô — người xem bật lại được phần đã lọc. Không hãng nào
công bố ngưỡng; ngưỡng dưới đây chốt theo dữ liệu thật của HAPAS (14/10/2026, 184 bình luận):
26 bình luận chỉ ".", "Hapas tặng" 11 lần từ 5 người (tham gia minigame lặp), 1 bình luận shop
giả "🔥Hot mua hàng chính hãng giảm 50% tại đây https://facebook.com/…", ~45 "Ib"/"Xin giá".

QUAN TRỌNG — "ib", "xin giá", "bn ạ" dưới bài của brand là KHÁCH HỎI MUA (ý định mua), không
phải spam: giữ là hợp lệ. Spam là bình luận kéo khách đi nơi khác (link lạ + lời chào hàng,
zalo/telegram của người bán khác, vay tiền, cờ bạc, việc nhẹ lương cao).

Nhãn bình luận (`binh_luan.loai`):
  hop_le       — tính vào thảo luận sạch, được gán sắc thái/chủ đề.
  it_noi_dung  — chỉ ".", "…", emoji, tag bạn bè, "chấm", "hóng": vẫn là tương tác (đếm vào
                 thảo luận thô) nhưng không gán sắc thái.
  spam         — quảng cáo/lừa đảo/kéo khách (`ly_do_loc` nói rõ loại).
  trung        — cùng người, cùng nội dung, cùng bài: giữ bản đầu, các bản sau là trùng.
  seeding      — cùng nội dung (≥ `SEEDING_TOI_THIEU_CHU` ký tự) từ ≥ `SEEDING_TAC_GIA` tài khoản
                 khác nhau trong `SEEDING_NGAY` ngày: dấu hiệu chiến dịch đăng hộ / bot.
  thuong_hieu  — chính thương hiệu trả lời.
Thuần Python, không gọi mạng — kiểm được bằng bài thử.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

LOAI = ("hop_le", "it_noi_dung", "spam", "trung", "seeding", "thuong_hieu")
#: Nhãn được gán sắc thái + tính vào "thảo luận sạch".
SACH = ("hop_le",)
TEN_LOAI = {"hop_le": "Hợp lệ", "it_noi_dung": "Ít nội dung", "spam": "Spam",
            "trung": "Trùng lặp", "seeding": "Seeding", "thuong_hieu": "Thương hiệu"}

SEEDING_TAC_GIA = 3
SEEDING_NGAY = 7
# Review 15/10: câu hỏi mua ngắn ("shop ơi cho mình xin giá ạ") nhiều khách cùng viết là
# chuyện thường — seeding phải đủ dài VÀ xuất hiện ở ≥ 2 bài (xem lang_nghe_db).
SEEDING_TOI_THIEU_CHU = 40
BAI_TRUNG_TOI_THIEU_CHU = 30

_RE_URL = re.compile(r"(https?://|www\.)\S+|\b[\w-]+\.(?:com|vn|net|xyz|top|site|shop|me|ly|link|io)"
                     r"(?:/\S*)?\b", re.IGNORECASE)
_RE_TAG = re.compile(r"@[\w.\-À-ỹ]+")
_RE_SDT = re.compile(r"(?<!\d)(?:\+?84|0)[\s.\-]?[35789](?:[\s.\-]?\d){8}(?!\d)")
_RE_EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")

# Từ vựng spam phổ biến ở mục bình luận VN, so trên bản BỎ DẤU, chữ thường.
_SPAM = {
    "vay_tien": r"\b(vay (tien|von) (nhanh|online|khong the chap)|vay nhanh|giai ngan|"
                r"no xau van vay|app vay)\b",
    "co_bac": r"\b(nha cai|no hu|tai xiu|ca cuoc|ca do|game bai|xoc dia|lo de|soi keo|"
              r"casino|thuong nap|khuyen mai nap)\b",
    "viec_lam_mmo": r"\b(viec nhe luong cao|kiem tien (online|tai nha|de dang)|tuyen ctv|"
                    r"tuyen cong tac vien|viec lam tai nha|thu nhap \d|chot don tai nha|"
                    r"go chu tai nha|xac nhan don hang tai nha)\b",
    "keo_khach": r"\b(ket ban zalo|add zalo|lien he zalo|zalo:? ?0\d|"
                 r"(add|ket ban|lien he|vao nhom) (tele|telegram)|t\.me/|"
                 r"xem trang ca nhan (minh|em)|vao trang (minh|em) (xem|mua))\b",
    # Review 15/10: "shop mình có size L không", "có giảm 10% không shop" là KHÁCH hỏi — chỉ
    # bắt câu mời mua đi nơi khác.
    "ban_hang_khac": r"\b(mua (ngay|hang) tai day|xem (them )?(mau )?tai day|"
                     r"link (o|tai|duoi) (day|bio)|inbox (shop|minh) (de|nhan) (gia|uu dai))\b",
}
# Ranh giới từ cuối mẫu không khớp sau "%" ("giảm 50% tại đây") — thay bằng "không có chữ
# liền sau".
_SPAM_RE = {k: re.compile(v[:-2] + r"(?!\w)" if v.endswith(r"\b") else v)
            for k, v in _SPAM.items()}
_KHUYEN_MAI = re.compile(r"\b(giam|sale|khuyen mai|chinh hang|mua hang|freeship|hot|uu dai)\b")
_IT_CHU = re.compile(r"^(cham|cham cham|hong|up|upp|ok|oke|e|a|o|in)$")


def bo_dau(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def chuan(s: str) -> str:
    """Chuẩn hoá để so trùng: bỏ dấu, chữ thường, bỏ @tag/link/emoji/dấu câu, gộp ký tự lặp
    ("đẹppppp" = "depp"), số thành 0, gộp khoảng trắng."""
    t = _RE_EMOJI.sub(" ", _RE_URL.sub(" ", _RE_TAG.sub(" ", str(s or ""))))
    t = bo_dau(unicodedata.normalize("NFC", t))
    t = re.sub(r"\d", "0", t)
    t = re.sub(r"[^\w\s]", " ", t)
    t = re.sub(r"(\w)\1{2,}", r"\1\1", t)
    return " ".join(t.split())


def ma_noi_dung(s: str, toi_thieu: int = 1) -> str | None:
    """Băm 16 ký tự của nội dung đã chuẩn hoá — None khi nội dung (bỏ khoảng trắng) ngắn hơn
    `toi_thieu` ký tự (quá ngắn để kết luận là trùng)."""
    c = chuan(s)
    if not c or len(c.replace(" ", "")) < toi_thieu:
        return None
    return hashlib.sha1(c.encode("utf-8")).hexdigest()[:16]


def ly_do_spam(s: str, thuong_hieu: list[str] | tuple = ()) -> str:
    """Loại spam đầu tiên khớp ("" nếu không phải spam). `thuong_hieu`: tên/từ khoá của dự án —
    link kèm tên brand không phải shop giả."""
    raw = str(s or "")
    t = bo_dau(raw)
    for k, rx in _SPAM_RE.items():
        if rx.search(t):
            return k
    co_link = bool(_RE_URL.search(raw))
    brand = [bo_dau(x).strip() for x in thuong_hieu if len(str(x).strip()) >= 3]
    if co_link and _KHUYEN_MAI.search(t) and not any(b in t for b in brand):
        return "lien_ket_quang_cao"       # link lạ + lời chào hàng (shop giả mạo)
    if _RE_SDT.search(raw) and co_link:
        return "so_dien_thoai_quang_cao"  # SĐT + link; SĐT đơn thuần = khách để lại số
    return ""


def it_noi_dung(s: str) -> bool:
    """Chỉ ".", "…", emoji, tag bạn bè, "chấm", "hóng" — không có ý để gán sắc thái."""
    c = chuan(s)
    return not c or bool(_IT_CHU.match(c))


def phan_loai(rows: list[dict], thuong_hieu: list[str] | tuple = ()) -> None:
    """Gắn `loai`, `ly_do_loc`, `ma_noi_dung` cho từng bình luận (dict có `khoa_bai`,
    `tac_gia`, `noi_dung`, `cua_thuong_hieu`), tại chỗ. Trùng = cùng bài + cùng người + cùng
    nội dung (giữ bản đầu). Seeding xét ở kho (cần lịch sử) — `lang_nghe_db.ghi_binh_luan`."""
    thay: set[tuple] = set()
    for r in rows:
        text = r.get("noi_dung") or ""
        r["ma_noi_dung"] = ma_noi_dung(text, SEEDING_TOI_THIEU_CHU)
        if r.get("cua_thuong_hieu"):
            r["loai"], r["ly_do_loc"] = "thuong_hieu", None
            continue
        sp = ly_do_spam(text, thuong_hieu)
        if sp:
            r["loai"], r["ly_do_loc"] = "spam", sp
            continue
        khoa = (r.get("khoa_bai"), chuan(r.get("tac_gia") or ""), chuan(text))
        if khoa[1] and khoa in thay:
            r["loai"], r["ly_do_loc"] = "trung", "cung_nguoi_cung_noi_dung"
            continue
        thay.add(khoa)
        if it_noi_dung(text):
            r["loai"], r["ly_do_loc"] = "it_noi_dung", None
            continue
        r["loai"], r["ly_do_loc"] = "hop_le", None


def bai_spam(text: str) -> str:
    """Bài (tìm theo từ khoá, không phải kênh nhà) mang dấu hiệu spam rõ — bỏ trước bước AI."""
    t = bo_dau(text)
    for k in ("vay_tien", "co_bac", "viec_lam_mmo"):
        if _SPAM_RE[k].search(t):
            return k
    return ""
