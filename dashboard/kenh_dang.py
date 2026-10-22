"""Khối "Theo kênh đăng" của trang Quảng cáo (22/10/2026, chủ dự án chốt).

Kênh đăng = danh tính một quảng cáo chạy dưới tên: TikTok identity (tài khoản chính chủ, KOC — Spark
Ads), Meta Trang Facebook (Instagram đi kèm hiện là thông tin phụ). Bộ đồng bộ ghi `qc_ad_kenh` /
`qc_kenh` (tiktok_ads.py, meta_ads.py); module này chỉ biến tổng SQL (`kho_qc.qc_kenh_dang`) thành
dòng hiển thị — không SQL, không gọi mạng.

Quyết định (22/10/2026):
  • Meta gộp theo TRANG (actor) — một ad luôn có Trang; Instagram của ad (nếu có) là thông tin phụ
    của dòng (Instagram của ad tiêu nhiều hiển thị nhất). Ad chỉ có Instagram → kênh là Instagram.
  • Nhãn TikTok: AUTH_CODE → Spark Ads (bài KOC uỷ quyền bằng mã); TT_USER / CUSTOMIZED_USER → Chính
    chủ; BC_AUTH_TT (tài khoản gắn Business Center — đo 22/10/2026: phần lớn là KOC, cả MATE MADE) →
    Chính chủ khi tên / username trùng tên tài khoản quảng cáo (vd "MATE MADE" ↔ "MATEMADE MKT"),
    còn lại Spark Ads.
  • Xếp theo chi tiêu (người không xem tiền: theo hiển thị); độ phủ tính cùng thước đo — người không
    xem tiền không suy ra được tỉ lệ chi.
  • Ad chưa đọc kênh / nền tảng không trả gộp một dòng "Chưa xác định" (luôn ở cuối bảng).
"""
from __future__ import annotations

import re
import unicodedata

from dashboard import quang_cao as QC

#: Số kênh hiện: mặc định 20, "xem thêm" lên 100 rồi 500 (`kho_qc.KENH_TOI_DA`).
SO_KENH = (20, 100, 500)
_CHINH_CHU_TIKTOK = frozenset({"TT_USER", "CUSTOMIZED_USER"})
NHAN = {"spark": "Spark Ads", "chinh_chu": "Chính chủ", "page": "Page", "instagram": "Instagram"}
#: Cột số của một dòng (không cột tiền nào khác ngoài chi — `QC.loc_tien` bỏ khi không xem tiền).
COT = ("chi", "hien_thi", "click", "view_video", "follow")


def chu_gon(s) -> str:
    """Bỏ dấu, chữ thường, chỉ a-z 0-9 ("MATE MADE" → "matemade")."""
    s = unicodedata.normalize("NFKD", str(s or "")).replace("đ", "d").replace("Đ", "d")
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


def chinh_chu(ten: str | None, username: str | None, ten_tk: list[str]) -> bool:
    """Tên / username kênh (≥ 5 ký tự gọn) nằm trong tên tài khoản quảng cáo, hoặc ngược lại."""
    tk = [chu_gon(t) for t in ten_tk if chu_gon(t)]
    for x in (chu_gon(ten), chu_gon(username)):
        if len(x) >= 5 and any(x in t or (len(t) >= 5 and t in x) for t in tk):
            return True
    return False


def loai_kenh(nen_tang: str, loai: str | None, ten: str | None, username: str | None,
              ten_tk: list[str]) -> str:
    if nen_tang == "meta":
        return "instagram" if loai == "instagram" else "page"
    if loai in _CHINH_CHU_TIKTOK:
        return "chinh_chu"
    if loai == "BC_AUTH_TT" and chinh_chu(ten, username, ten_tk):
        return "chinh_chu"
    return "spark"


def _at(u) -> str | None:
    u = str(u or "").strip().lstrip("@")
    return f"@{u}" if u else None


def dong(r: dict, ten_tk: dict[str, str]) -> dict:
    """Tổng SQL của một kênh → dòng hiển thị (tên, nhãn, tài khoản, số)."""
    nen = r.get("nen_tang") or "tiktok"
    kid = str(r.get("kenh_id") or "")
    tks = [ten_tk[i] for i in (r.get("tk_ids") or []) if i in ten_tk]
    lk = loai_kenh(nen, r.get("loai"), r.get("ten"), r.get("username"), tks)
    if nen == "meta" and lk == "instagram":
        ten, phu = _at(r.get("username")) or f"IG {kid}", None
    elif nen == "meta":
        ig = r.get("kenh_phu_id")
        ten = r.get("ten") or f"Page {kid}"
        phu = (_at(r.get("phu_username")) or f"IG {ig}") if ig else None
    else:
        ten = r.get("ten") or _at(r.get("username")) or f"TikTok {kid[:12]}"
        phu = _at(r.get("username")) if r.get("ten") else None
    return {"nen_tang": nen, "ten": ten, "phu": phu, "loai": lk, "nhan_loai": NHAN[lk],
            "tai_khoan": tks, "so_ad": int(r.get("so_ad") or 0),
            **{c: r.get(c) for c in COT}, "tuong_tac": QC.tuong_tac(r)}


def so_kenh(qp) -> int:
    try:
        n = int(str(qp.get("kenh_so") or SO_KENH[0]))
    except ValueError:
        return SO_KENH[0]
    return n if n in SO_KENH else SO_KENH[0]


def du_lieu(kq, ids: list[str], tu, den, qp, co_tien: bool, ten_tk: dict[str, str]) -> dict | None:
    """Khối "Theo kênh đăng" cho trang + /api/qc. `ids` = tài khoản trong phạm vi người xem (gọi
    viên đã kiểm); tiền lọc ở `QC.loc_tien` của gọi viên. Kho chưa có hàm / bảng (schema.sql chưa
    chạy) → khối báo chưa có số, không làm hỏng trang. -> None khi không có tài khoản."""
    if not ids:
        return None
    so = so_kenh(qp)
    do = "chi" if co_tien else "hien_thi"
    ham = getattr(kq, "qc_kenh_dang", None)
    if ham is None:
        return None
    try:
        r = ham(list(ids), tu, den, sap=do, n=so)
    except Exception:  # noqa: BLE001 — bảng chưa có (LoiKho) / lỗi đọc: khối báo chưa có số
        return {"loi": "Chưa đọc được số theo kênh (kho chưa có bảng kênh đăng).", "rows": [],
                "tong": 0, "so": so, "so_tiep": None, "do_phu": None, "do_phu_theo": do,
                "chua_ro": None}
    biet, chua = r.get("biet") or {}, r.get("chua_ro") or {}
    a, b = float(biet.get(do) or 0), float(chua.get(do) or 0)
    tong = int(r.get("tong") or 0)
    tiep = next((n for n in SO_KENH if n > so), None)
    chua_ro = None
    if chua and (chua.get("hien_thi") or chua.get("chi")):
        chua_ro = {"ten": "Chưa xác định", "so_ad": int(chua.get("so_ad") or 0),
                   **{c: chua.get(c) for c in COT}, "tuong_tac": QC.tuong_tac(chua)}
    return {"rows": [dong(x, ten_tk) for x in r.get("rows") or []], "tong": tong, "so": so,
            "so_tiep": tiep if tiep and tong > so else None,
            "do_phu": round(a / (a + b) * 100, 1) if a + b else None, "do_phu_theo": do,
            "chua_ro": chua_ro}
