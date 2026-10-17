"""Chuẩn hoá chữ bình luận/bài MXH tiếng Việt — DÙNG CHUNG dashboard và Mark (16/10/2026).

Rà kho 15/10/2026: mây từ khoá hiện "max cuo", "pii la", "ra ma" — bình luận viết bằng chữ "kiểu
cách" (𝐃𝐚́𝐧 𝐦𝐚𝐱 𝐜𝐮𝐨̂́𝐢, khối Unicode U+1D400–1D7FF) có dấu là ký tự RỜI: chuẩn hoá NFC không ghép
được nên dấu thành chỗ cắt chữ ("cuối" → "cuo"). Teen code ("mk" = mình, "bn" = bao nhiêu) và bản
không dấu ("xin gia" bên cạnh "xin giá") cũng bị đếm thành cụm riêng.

Thứ tự chuẩn hoá: NFKC (chữ kiểu cách / toàn khổ về chữ thường gặp, ghép lại dấu) → chữ thường →
teen code về chữ chuẩn, GIỮ dấu (`chuan_hoa`) → khi cần so khớp thì bỏ dấu, đ → d (`khoa`).

Chỉ thư viện chuẩn: dashboard chạy venv riêng, không import module nào của Mark; chiều ngược lại
được (như `dashboard.lich_quet`) — `loc_rac` của Mark dùng module này để bắt spam affiliate.
"""
from __future__ import annotations

import re
import unicodedata

#: Dấu tổ hợp sau NFD. Tiếng Việt chỉ dùng khối U+0300–036F; thêm các khối dấu khác cho chắc.
_RE_DAU = re.compile("[̀-ͯ᪰-᫿᷀-᷿⃐-⃿︠-︯]")
#: Khối "Mathematical Alphanumeric Symbols" — chữ đậm/nghiêng/viết tay kiểu cách.
_KIEU_TU, _KIEU_DEN = "\U0001d400", "\U0001d7ff"


def nfkc(s) -> str:
    return unicodedata.normalize("NFKC", str(s or ""))


def thuong(s) -> str:
    """NFKC rồi chữ thường (giữ dấu)."""
    return nfkc(s).lower()


def bo_dau(s) -> str:
    """NFKC → chữ thường → đ thành d → bỏ dấu. "𝐂𝐮𝐨̂́𝐢" → "cuoi"."""
    return _RE_DAU.sub("", unicodedata.normalize("NFD", thuong(s).replace("đ", "d")))


def dem_chu_kieu(s) -> tuple[int, int]:
    """(số chữ cái kiểu cách U+1D400–1D7FF, tổng số chữ cái) của chuỗi CHƯA chuẩn hoá."""
    kieu = chu = 0
    for ch in str(s or ""):
        if ch.isalpha():
            chu += 1
            if _KIEU_TU <= ch <= _KIEU_DEN:
                kieu += 1
    return kieu, chu


# ───────────────────────── teen code ─────────────────────────
# Chỉ từ ĐỨNG RIÊNG (không nằm trong chữ khác), so trên chữ thường sau NFKC. Từ nào hai nghĩa thì
# xét chữ đứng trước/sau (`_thay`); không chắc thì giữ nguyên — thà sót còn hơn đổi sai nghĩa.
_RE_TEEN = re.compile(r"(?<!\w)(mk|mik|mjk|mh|ak|ah|bn|dc|đc|ko|k|khg|khum|hok|sét|zán)(?!\w)")
_TEEN_CO_DINH = {"mk": "mình", "mik": "mình", "mjk": "mình", "mh": "mình", "dc": "được",
                 "đc": "được", "ko": "không", "khg": "không", "khum": "không", "hok": "không",
                 "zán": "dán"}
#: "bn" là "bạn" khi đứng trước lời gọi / sau lời cảm ơn, chào; còn lại (giá bn, bn ạ) là "bao nhiêu".
#: 17/10/2026 (rà kho: "Siêu bn thân", "bn ấy", "bn pk hiểu", "bảo bn mà", "nó bock a bn" bị đếm là
#: hỏi giá): thêm "bạn thân/bạn ấy/bạn phải/bạn hiểu/bạn bè" và "bảo/anh/a/với/vs/của/cùng + bn".
_BAN_SAU = {"ơi", "oi", "ê", "à", "thân", "than", "ấy", "pk", "phải", "phai", "hiểu", "hieu",
            "bè"}
_BAN_TRUOC = {"ơn", "on", "chào", "chao", "các", "cac", "giúp", "giup", "bảo", "a", "anh",
              "với", "vs", "của", "cùng"}
#: "sét" là "set" (bộ sản phẩm) khi đứng cạnh từ chỉ hàng — tránh đổi "sét đánh".
_SET_SAU = {"túi", "tui", "ví", "quà", "hộp", "hop", "đồ", "combo", "mini", "áo", "váy", "son",
            "nước", "này", "nay", "kia", "đó", "đấy", "gồm", "full"}
_SET_TRUOC = {"giá", "gia", "mua", "lấy", "lay", "bộ", "cả", "đặt", "dat", "cái", "một", "mot",
              "hai", "ba", "combo", "chiếc"}
_RE_TU_TRUOC = re.compile(r"(\w+)\W*$")
_RE_TU_SAU = re.compile(r"\W*(\w+)")
_RE_HET_CAU = re.compile(r"\s*(?:[^\w\s]|$)")
#: Ngữ cảnh chữ trước/sau chỉ xét trong khung ngắn quanh từ: tra từ đầu chuỗi mỗi lần khớp là
#: O(n²) (review 16/10: chuỗi 50.000 ký tự mất ~8 giây).
_KHUNG = 40


def _thay(m: re.Match) -> str:
    t, s = m.group(1), m.string
    if t in _TEEN_CO_DINH:
        return _TEEN_CO_DINH[t]
    a, b = m.start(), m.end()
    truoc = _RE_TU_TRUOC.search(s, max(0, a - _KHUNG), a)
    truoc = truoc.group(1) if truoc else ""
    sau = _RE_TU_SAU.match(s, b, b + _KHUNG)
    sau = sau.group(1) if sau else ""
    if t in ("ak", "ah"):                      # tiểu từ cuối câu ("giá ak", "zán cam ah") = "ạ"
        return "ạ" if _RE_HET_CAU.match(s, b) else t
    if t == "bn":
        return "bạn" if sau in _BAN_SAU or truoc in _BAN_TRUOC else "bao nhiêu"
    if t == "k":                               # "299 k" là nghìn đồng, không phải "không"
        return t if s[max(0, a - _KHUNG):a].rstrip()[-1:].isdigit() else "không"
    if t == "sét":
        return "set" if (sau in _SET_SAU or sau.isdigit() or truoc in _SET_TRUOC) else t
    return t


def chuan_hoa(s) -> str:
    """NFKC → chữ thường → teen code về chữ chuẩn, GIỮ dấu: "Giá bn ak" → "giá bao nhiêu ạ"."""
    return _RE_TEEN.sub(_thay, thuong(s))


def khoa(s) -> str:
    """Khoá so khớp: `chuan_hoa` → bỏ dấu → gộp khoảng trắng. "Xin giá sét túi" và "xin gia set
    tui" cùng khoá; "mk xin" = "mình xin"."""
    return " ".join(bo_dau(chuan_hoa(s)).split())


def khoa_tim(q) -> str:
    """Khoá của CHỮ TÌM (ô tìm bình luận/bài): như `khoa`; riêng chữ tìm còn dưới 2 ký tự sau teen
    code (vd "ak" → "a") thì giữ bản bỏ dấu gốc — không để một chữ cái khớp mọi bình luận."""
    k = khoa(q)
    return k if len(k) >= 2 else " ".join(bo_dau(q).split())


def chua(q_khoa: str, s) -> bool:
    """`s` có chứa chữ tìm (đã qua `khoa_tim`) không — bỏ dấu, teen code, chữ kiểu cách."""
    return not q_khoa or q_khoa in khoa(s)
