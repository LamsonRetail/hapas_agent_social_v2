"""Kiểm + chuẩn hoá chữ người dùng gõ trên dashboard. Thuần Python, không SQL, không mạng.

Vì sao tách riêng: định danh nguồn phải ra ĐÚNG dạng Mark dùng khi quét (`theo_doi.
_chuan_dinh_danh`, `_lay_tai_khoan`, `_lay_youtube`) — sai một ký tự là nguồn "không lấy được
bài nào" mỗi ngày mà không ai hiểu vì sao. Người dùng hay dán nguyên link trang cá nhân (kèm
`?lang=vi`, `igsh=`…), nên ở đây bóc định danh từ link và báo lỗi bằng câu dễ hiểu khi họ dán
nhầm link BÀI thay vì link TRANG.

Dạng lưu (khớp chú thích bảng `nguon` trong `deploy/lang-nghe/schema.sql`):
  • TikTok / Instagram: username, chữ thường, không có '@' (Mark tự bỏ '@' rồi gửi actor).
  • YouTube: id kênh `UC…` giữ NGUYÊN hoa thường (id phân biệt hoa thường), hoặc `@handle`
    chữ thường (Mark gọi `channels?forHandle=`).
  • Facebook: URL đầy đủ `https://www.facebook.com/<trang>` chữ thường, không tham số — actor
    Facebook nhận startUrls là URL, Mark so khớp sau khi bỏ scheme/www.
  • Threads (16/10/2026): username chữ thường, không '@' (cùng handle Instagram); link hồ sơ
    threads.com/@ten hoặc threads.net/@ten đều được, link BÀI (/post/…) thì báo dán lại.
"""
from __future__ import annotations

import datetime
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit

NEN_TANG = ("tiktok", "instagram", "youtube", "facebook", "threads")
TEN_NEN_TANG = {"tiktok": "TikTok", "instagram": "Instagram", "youtube": "YouTube",
                "facebook": "Facebook", "threads": "Threads"}
# Nhãn hiển thị "Internal channel" (chủ dự án 16/10/2026); giá trị lưu vẫn là `kenh_nha`.
LOAI_NGUON = {"kol": "KOL/KOC", "page": "Trang/fanpage", "group": "Nhóm", "bao": "Báo/tin tức",
              "kenh_nha": "Internal channel", "khac": "Khác"}
VAI_TRO = {"xem": "Chỉ xem", "quan_ly": "Quản lý"}
# Chủ dự án 15/10: "không có giới hạn" — hai mức dưới chỉ chặn số rác / tràn cột (NUMERIC(8,2),
# INT), KHÔNG phải trần nghiệp vụ. Tiền vẫn chặn bằng trần tháng do người dùng đặt.
TRAN_USD_TOI_DA = Decimal("999999.99")
SO_TOI_DA = 1_000_000

_MIEN = {"tiktok": ("tiktok.com",), "instagram": ("instagram.com", "instagr.am"),
         "youtube": ("youtube.com", "youtu.be"), "facebook": ("facebook.com", "fb.com", "fb.me"),
         "threads": ("threads.com", "threads.net")}
_RE_UC = re.compile(r"UC[\w-]{22}")
_RE_TEN_TK = re.compile(r"[a-z0-9._]{2,30}")
_RE_HANDLE_YT = re.compile(r"@[\w.\-]{3,30}")
_RE_TRANG_FB = re.compile(r"[a-z0-9.\-_]{2,100}")
_RE_MA_DU_AN = re.compile(r"[a-z0-9][a-z0-9_-]{1,39}")
_RE_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
# Đoạn đường dẫn cho thấy đây là link BÀI/VIDEO chứ không phải trang — báo người dùng dán lại.
_FB_KHONG_PHAI_TRANG = {"posts", "videos", "photos", "photo", "photo.php", "permalink.php",
                        "story.php", "watch", "reel", "reels", "share", "sharer", "sharer.php",
                        "events", "marketplace", "hashtag", "search", "login", "stories"}
_IG_KHONG_PHAI_TRANG = {"p", "reel", "reels", "tv", "explore", "accounts", "direct", "about"}


class LoiNhap(ValueError):
    """Dữ liệu nhập sai. Câu thông báo hiển thị thẳng cho người dùng (tiếng Việt)."""


# ───────────────────────────── chữ chung ─────────────────────────────
def sach(s, toi_da: int = 200) -> str:
    """Bỏ ký tự điều khiển, gộp khoảng trắng, cắt độ dài — chữ tự do (tên, bối cảnh)."""
    s = unicodedata.normalize("NFC", str(s or ""))
    s = "".join(c if (c in "\n\t" or unicodedata.category(c)[0] != "C") else " " for c in s)
    return re.sub(r"[ \t]+", " ", s).strip()[:toi_da]


def danh_sach(s, toi_da: int = 50, dai_toi_da: int = 100) -> list[str]:
    """"a, b\\nc" -> ["a", "b", "c"]: tách theo dấu phẩy/xuống dòng, bỏ trùng (không phân biệt
    hoa thường), giữ thứ tự gõ."""
    ra: list[str] = []
    thay: set[str] = set()
    for x in re.split(r"[,\n;]+", str(s or "")):
        x = sach(x, dai_toi_da)
        if x and x.lower() not in thay:
            thay.add(x.lower())
            ra.append(x)
    if len(ra) > toi_da:
        raise LoiNhap(f"Tối đa {toi_da} mục mỗi danh sách.")
    return ra


def so_nguyen(s, ten: str, nho: int, lon: int = SO_TOI_DA) -> int:
    """Số nguyên trong [nho, lon]. `lon` = SO_TOI_DA nghĩa là không trần trên nghiệp vụ."""
    khoang = f"từ {nho} trở lên" if lon >= SO_TOI_DA else f"từ {nho} đến {lon}"
    try:
        n = int(str(s or "").strip())
    except ValueError:
        raise LoiNhap(f"{ten} phải là số nguyên {khoang}.") from None
    if n < nho:
        raise LoiNhap(f"{ten} phải {khoang}.")
    if n > lon:
        raise LoiNhap(f"{ten} quá lớn (tối đa {lon:,})." if lon >= SO_TOI_DA
                      else f"{ten} phải {khoang}.")
    return n


def tran_usd(s) -> Decimal:
    """Trần USD tháng: ≥ 0 (không trần trên), nhận cả "5,5" kiểu Việt. Decimal để khỏi lệch
    0.1+0.2."""
    t = str(s or "").strip().replace(" ", "").replace(",", ".")
    try:
        x = Decimal(t)
    except InvalidOperation:
        raise LoiNhap("Trần tháng phải là số USD từ 0 trở lên.") from None
    if not x.is_finite() or x < 0 or x > TRAN_USD_TOI_DA:
        raise LoiNhap("Trần tháng phải là số USD từ 0 trở lên (dưới 1.000.000).")
    return x.quantize(Decimal("0.01"))


def email(s) -> str:
    e = str(s or "").strip().lower()
    if len(e) > 254 or not _RE_EMAIL.fullmatch(e):
        raise LoiNhap("Email không hợp lệ.")
    return e


def vai_tro(s) -> str:
    v = str(s or "").strip()
    if v not in VAI_TRO:
        raise LoiNhap("Vai trò phải là Chỉ xem hoặc Quản lý.")
    return v


def ma_du_an(s) -> str:
    m = str(s or "").strip().lower()
    if not _RE_MA_DU_AN.fullmatch(m):
        raise LoiNhap("Mã dự án: 2–40 ký tự a-z, 0-9, '-' hoặc '_', bắt đầu bằng chữ/số "
                      "(đây là chữ gõ sau /theodoi).")
    return m


def thi_truong(s) -> str:
    t = str(s or "VN").strip().upper() or "VN"
    if not re.fullmatch(r"[A-Z]{2}", t):
        raise LoiNhap("Thị trường là mã quốc gia 2 chữ cái, vd VN.")
    return t


def ngay(s, mac_dinh: datetime.date) -> datetime.date:
    t = str(s or "").strip()
    if not t:
        return mac_dinh
    try:
        d = datetime.date.fromisoformat(t)
    except ValueError:
        raise LoiNhap("Ngày phải có dạng YYYY-MM-DD.") from None
    # Chặn năm cực trị: 9999-12-31 + 1 ngày là lỗi tràn (trang 500) khi dựng mốc truy vấn.
    if not 2000 <= d.year <= 2100:
        raise LoiNhap("Ngày phải trong khoảng năm 2000–2100.")
    return d


def duong_an_toan(s, mac_dinh: str = "/") -> str:
    """Chỉ cho chuyển hướng tới đường dẫn TƯƠNG ĐỐI trong chính trang (chống open redirect):
    '/nguon?du_an=x' được; '//evil.com', '/\\evil.com', 'https://…', ký tự điều khiển thì không."""
    s = str(s or "")
    if (not s.startswith("/") or s.startswith("//") or "\\" in s or "://" in s
            or any(ord(c) < 0x20 or ord(c) == 0x7F for c in s) or len(s) > 500):
        return mac_dinh
    return s


def link_an_toan(s) -> str:
    """Link hiển thị cho người xem: chỉ http(s), không `javascript:`."""
    s = str(s or "").strip()
    return s if re.match(r"https?://", s, re.IGNORECASE) else ""


# ───────────────────────────── định danh nguồn ─────────────────────────────
def _la_link(s: str) -> bool:
    return bool(re.match(r"(https?://)?([\w-]+\.)*[\w-]+\.[a-z]{2,}(/|$)", s,
                         re.IGNORECASE)) and "/" in s


def _tach_link(nen_tang: str, s: str):
    """-> (host, [đoạn đường dẫn], query). Link của nền tảng KHÁC thì báo lỗi rõ."""
    if not re.match(r"https?://", s, re.IGNORECASE):
        s = "https://" + s
    u = urlsplit(s)
    host = (u.hostname or "").lower()
    if not any(host == m or host.endswith("." + m) for m in _MIEN[nen_tang]):
        khac = next((TEN_NEN_TANG[p] for p, ms in _MIEN.items()
                     if any(host == m or host.endswith("." + m) for m in ms)), None)
        raise LoiNhap(f"Link này là của {khac}, không phải {TEN_NEN_TANG[nen_tang]}." if khac
                      else f"Link không phải của {TEN_NEN_TANG[nen_tang]}.")
    doan = [d for d in u.path.split("/") if d]
    return host, doan, u.query


def chuan_dinh_danh(nen_tang: str, chuoi: str) -> tuple[str, str]:
    """Username / link trang người dùng dán -> (định danh lưu kho, link trang chuẩn)."""
    if nen_tang not in NEN_TANG:
        raise LoiNhap("Nền tảng phải là TikTok, Instagram, YouTube, Facebook hoặc Threads.")
    s = str(chuoi or "").strip()
    if not s:
        raise LoiNhap("Chưa nhập tài khoản / link trang.")
    if len(s) > 500:
        raise LoiNhap("Link quá dài.")
    return {"tiktok": _tiktok, "instagram": _instagram, "youtube": _youtube,
            "facebook": _facebook, "threads": _threads}[nen_tang](s)


def _tiktok(s: str) -> tuple[str, str]:
    if _la_link(s):
        host, doan, _ = _tach_link("tiktok", s)
        if host.startswith(("vm.", "vt.")) or (doan and doan[0] == "t"):
            raise LoiNhap("Đây là link TikTok rút gọn — mở link rồi dán link trang cá nhân "
                          "(dạng tiktok.com/@ten).")
        ten = next((d for d in doan if d.startswith("@")), "")
        if not ten:
            raise LoiNhap("Không thấy tên tài khoản trong link TikTok — dán link dạng "
                          "tiktok.com/@ten.")
        s = ten
    ten = s.strip().lstrip("@").lower()
    if not _RE_TEN_TK.fullmatch(ten):
        raise LoiNhap("Tên tài khoản TikTok chỉ gồm chữ, số, '.' và '_' (2–30 ký tự).")
    return ten, f"https://www.tiktok.com/@{ten}"


def _instagram(s: str) -> tuple[str, str]:
    if _la_link(s):
        _, doan, _ = _tach_link("instagram", s)
        if doan and doan[0].lower() == "stories" and len(doan) > 1:
            doan = doan[1:]
        if not doan or doan[0].lower() in _IG_KHONG_PHAI_TRANG:
            raise LoiNhap("Đây là link bài/reel Instagram — dán link trang cá nhân "
                          "(dạng instagram.com/ten).")
        s = doan[0]
    ten = s.strip().lstrip("@").lower()
    if not _RE_TEN_TK.fullmatch(ten):
        raise LoiNhap("Tên tài khoản Instagram chỉ gồm chữ, số, '.' và '_' (2–30 ký tự).")
    return ten, f"https://www.instagram.com/{ten}/"


def _threads(s: str) -> tuple[str, str]:
    if _la_link(s):
        _, doan, _ = _tach_link("threads", s)
        if not doan or not doan[0].startswith("@") or len(doan) > 1:
            raise LoiNhap("Đây không phải link trang cá nhân Threads — dán link dạng "
                          "threads.com/@ten (không phải link bài /post/…).")
        s = doan[0]
    ten = s.strip().lstrip("@").lower()
    if not _RE_TEN_TK.fullmatch(ten):
        raise LoiNhap("Tên tài khoản Threads chỉ gồm chữ, số, '.' và '_' (2–30 ký tự).")
    return ten, f"https://www.threads.com/@{ten}"


def _youtube(s: str) -> tuple[str, str]:
    if _RE_UC.fullmatch(s):
        return s, f"https://www.youtube.com/channel/{s}"
    if _la_link(s):
        host, doan, _ = _tach_link("youtube", s)
        if host == "youtu.be" or (doan and doan[0] in ("watch", "shorts", "live", "embed",
                                                        "playlist")):
            raise LoiNhap("Đây là link video YouTube — dán link kênh (dạng youtube.com/@ten "
                          "hoặc youtube.com/channel/UC…).")
        if len(doan) >= 2 and doan[0] == "channel" and _RE_UC.fullmatch(doan[1]):
            return doan[1], f"https://www.youtube.com/channel/{doan[1]}"
        if doan and doan[0].startswith("@"):
            s = doan[0]
        else:
            raise LoiNhap("Link kênh kiểu /c/ hoặc /user/ không dùng được — mở kênh, dán link "
                          "dạng youtube.com/@ten hoặc youtube.com/channel/UC….")
    handle = "@" + s.strip().lstrip("@").lower()
    if not _RE_HANDLE_YT.fullmatch(handle):
        raise LoiNhap("Handle YouTube gồm 3–30 chữ, số, '.', '-' hoặc '_' (vd @hapas), hoặc "
                      "id kênh UC… (24 ký tự).")
    return handle, f"https://www.youtube.com/{handle}"


def _facebook(s: str) -> tuple[str, str]:
    if _la_link(s):
        host, doan, query = _tach_link("facebook", s)
        if host == "fb.me":
            raise LoiNhap("Đây là link Facebook rút gọn — mở link rồi dán link trang.")
        thap = [d.lower() for d in doan]
        if thap and thap[0] == "profile.php":
            # profile.php?id=… : id nằm trong tham số — đổi sang facebook.com/<id> (Facebook tự
            # chuyển) để vẫn lưu được dạng không tham số như các trang khác.
            so = (parse_qs(query).get("id") or [""])[0]
            if not so.isdigit():
                raise LoiNhap("Link profile.php thiếu id — dán link có dạng "
                              "facebook.com/profile.php?id=123….")
            duong = so
        elif thap and thap[0] == "pages" and len(thap) >= 3 and thap[2].isdigit():
            duong = thap[2]
        elif thap and thap[0] == "groups" and len(thap) >= 2:
            if not _RE_TRANG_FB.fullmatch(thap[1]):
                raise LoiNhap("Tên nhóm Facebook không hợp lệ.")
            if len(thap) > 2:
                raise LoiNhap("Đây là link bài trong nhóm — dán link nhóm (facebook.com/groups/ten).")
            duong = f"groups/{thap[1]}"
        elif not thap or thap[0] in _FB_KHONG_PHAI_TRANG or any(
                d in _FB_KHONG_PHAI_TRANG for d in thap[1:]):
            raise LoiNhap("Đây không phải link trang Facebook — dán link trang "
                          "(dạng facebook.com/ten-trang).")
        else:
            duong = thap[0]
    else:
        duong = s.strip().lstrip("@").lower()
    if not duong.startswith("groups/") and not _RE_TRANG_FB.fullmatch(duong):
        raise LoiNhap("Tên trang Facebook chỉ gồm chữ, số, '.', '-' và '_'.")
    url = f"https://www.facebook.com/{duong}"
    return url, url


# ───────────────────────────── biểu mẫu ─────────────────────────────
def du_an(form: dict, *, moi: bool) -> dict:
    """Biểu mẫu dự án -> dict cột `du_an` (trừ trần tháng: sửa ở trang Ngân sách)."""
    d = {
        "ten": sach(form.get("ten"), 200),
        "tu_khoa": danh_sach(form.get("tu_khoa")),
        "tu_loai_tru": danh_sach(form.get("tu_loai_tru")),
        "boi_canh": sach(form.get("boi_canh"), 2000),
        "thi_truong": thi_truong(form.get("thi_truong")),
        "dang_bat": str(form.get("dang_bat") or "").strip() in ("1", "on", "true"),
    }
    if moi:
        d["ma"] = ma_du_an(form.get("ma"))
    if not d["ten"]:
        raise LoiNhap("Chưa nhập tên dự án.")
    if not d["tu_khoa"]:
        raise LoiNhap("Cần ít nhất một từ khoá (bài từ nguồn ngoài phải nhắc từ khoá mới được giữ).")
    return d


def nguon(form: dict) -> dict:
    """Biểu mẫu nguồn -> dict cột `nguon` (định danh đã chuẩn hoá)."""
    p = str(form.get("nen_tang") or "").strip()
    dinh_danh, link = chuan_dinh_danh(p, form.get("dinh_danh"))
    loai = str(form.get("loai") or "khac").strip()
    if loai not in LOAI_NGUON:
        raise LoiNhap("Loại nguồn không hợp lệ.")
    return {
        "nen_tang": p, "dinh_danh": dinh_danh, "link": link,
        "ten": sach(form.get("ten"), 200) or dinh_danh.rsplit("/", 1)[-1],
        "loai": loai, "nhan": danh_sach(form.get("nhan"), 20, 50),
        "chu_ky_ngay": so_nguyen(form.get("chu_ky_ngay") or 1, "Chu kỳ quét (ngày)", 1, 30),
        "so_bai_moi_lan": so_nguyen(form.get("so_bai_moi_lan") or 5, "Số bài mỗi lần", 1),
    }
