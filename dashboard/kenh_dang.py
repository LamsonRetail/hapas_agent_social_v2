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
    còn lại Spark Ads. 23/10/2026: tên / username bắt đầu bằng HAPAS / MATE MADE → Chính chủ (mọi
    dạng danh tính TikTok).
  • Xếp theo chi tiêu (người không xem tiền: theo hiển thị); độ phủ tính cùng thước đo — người không
    xem tiền không suy ra được tỉ lệ chi.
  • Ad chưa đọc kênh / nền tảng không trả gộp một dòng "Chưa xác định" (luôn ở cuối bảng).
"""
from __future__ import annotations

import re
import unicodedata

from dashboard import quang_cao as QC

#: 23/10/2026 (chủ dự án: "thêm filter giống phần chiến dịch và quảng cáo"): đọc ĐỦ kênh của phạm vi
#: (`kho_qc.KENH_TOI_DA`) rồi lọc tên / loại, xếp theo mọi cột, chia trang 20 ở MÁY CHỦ — tìm và xếp
#: đúng trên toàn bộ kênh, không chỉ phần đã tải. Tham số: kt (tìm), kl (loại), ks (xếp), kc
#: (chiều: tang | giam), kp (trang).
KENH_MOI_TRANG = 20
#: Cột xếp được → nhãn; "chi" chỉ khi xem tiền.
SAP_KENH = {"chi": "Chi", "hien_thi": "Hiển thị", "click": "Click", "view_video": "View video",
            "tuong_tac": "Tương tác", "follow": "Follow", "so_ad": "Số quảng cáo"}
_CHINH_CHU_TIKTOK = frozenset({"TT_USER", "CUSTOMIZED_USER"})
NHAN = {"spark": "Spark Ads", "chinh_chu": "Chính chủ", "page": "Page", "instagram": "Instagram"}
#: Cột số của một dòng (không cột tiền nào khác ngoài chi — `QC.loc_tien` bỏ khi không xem tiền).
COT = ("chi", "hien_thi", "click", "view_video", "follow")


def _so(r: dict) -> dict:
    """Cột số của một dòng. 28/10/2026 (chủ dự án): Click = bấm liên kết (`click_lk` của
    `kho_qc.sql_kenh_dang` — Meta inline_link_clicks, TikTok clicks) như cả trang Quảng cáo; dòng
    không có khoá đó (kho cũ) giữ cột click."""
    return {c: (r.get("click_lk") if c == "click" and "click_lk" in r else r.get(c)) for c in COT}


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


#: 23/10/2026 (chủ dự án): kênh TikTok có tên / username BẮT ĐẦU bằng tên thương hiệu nhà là Chính
#: chủ dù chạy dạng gì (vd "HAPAS Jewelry", "HAPAS Perfume", @hapasjewelry.official, "MATE MADE Ơi").
DAU_THUONG_HIEU = ("hapas", "matemade")


def ten_nha(ten: str | None, username: str | None) -> bool:
    return any(chu_gon(x).startswith(DAU_THUONG_HIEU) for x in (ten, username))


def loai_kenh(nen_tang: str, loai: str | None, ten: str | None, username: str | None,
              ten_tk: list[str]) -> str:
    if nen_tang == "meta":
        return "instagram" if loai == "instagram" else "page"
    if loai in _CHINH_CHU_TIKTOK or ten_nha(ten, username):
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
            **_so(r), "tuong_tac": QC.tuong_tac(r)}


def loc_kenh(qp, co_tien: bool) -> dict:
    """Tham số lọc / xếp / trang của khối (kt, kl, ks, kc, kp) đã kiểm — giá trị lạ về mặc định."""
    tim = str(qp.get("kt") or "").strip()[:QC.TIM_TOI_DA]
    loai = str(qp.get("kl") or "")
    sap = str(qp.get("ks") or "")
    mac_dinh = "chi" if co_tien else "hien_thi"
    if sap not in SAP_KENH or (sap == "chi" and not co_tien):
        sap = mac_dinh
    try:
        trang = max(1, min(int(str(qp.get("kp") or 1)), QC.TRANG_TOI_DA))
    except ValueError:
        trang = 1
    return {"tim": tim, "loai": loai if loai in NHAN else "", "sap": sap,
            "chieu": "tang" if qp.get("kc") == "tang" else "giam", "trang": trang,
            "mac_dinh": mac_dinh}


def _khop(r: dict, mau: str) -> bool:
    return any(mau in QC.chu_tim(x or "") for x in (r["ten"], r["phu"], *r["tai_khoan"]))


def du_lieu(kq, ids: list[str], tu, den, qp, co_tien: bool, ten_tk: dict[str, str],
            cds: list[str] | None = None) -> dict | None:
    """Khối "Theo kênh đăng" cho trang + /api/qc. `ids` = tài khoản trong phạm vi người xem (gọi
    viên đã kiểm); tiền lọc ở `QC.loc_tien` của gọi viên. Kho chưa có hàm / bảng (schema.sql chưa
    chạy) → khối báo chưa có số, không làm hỏng trang. -> None khi không có tài khoản.
    23/10/2026 (MKT): `cds` = chiến dịch khớp tên của Bộ lọc đầu trang (`kho_qc.ma_cd_theo_ten`) —
    chỉ quảng cáo của chúng; None = không lọc (không truyền xuống kho, như cũ)."""
    if not ids:
        return None
    lk = loc_kenh(qp, co_tien)
    do = "chi" if co_tien else "hien_thi"
    ham = getattr(kq, "qc_kenh_dang", None)
    if ham is None:
        return None
    try:
        from dashboard.kho_qc import KENH_TOI_DA
        r = ham(list(ids), tu, den, sap=do, n=KENH_TOI_DA,
                **({"cds": list(cds)} if cds is not None else {}))
    except Exception:  # noqa: BLE001 — bảng chưa có (LoiKho) / lỗi đọc: khối báo chưa có số
        return {"loi": "Chưa đọc được số theo kênh (kho chưa có bảng kênh đăng).", "rows": [],
                "tong": 0, "tong_khop": 0, "trang": 1, "so_trang": 1, "loc": lk, "cac_loai": [],
                "do_phu": None, "do_phu_theo": do, "chua_ro": None}
    biet, chua = r.get("biet") or {}, r.get("chua_ro") or {}
    a, b = float(biet.get(do) or 0), float(chua.get(do) or 0)
    ds = [dong(x, ten_tk) for x in r.get("rows") or []]
    dem: dict[str, int] = {}
    for x in ds:
        dem[x["loai"]] = dem.get(x["loai"], 0) + 1
    if lk["loai"]:
        ds = [x for x in ds if x["loai"] == lk["loai"]]
    mau = QC.chu_tim(lk["tim"])
    if lk["tim"]:
        ds = [x for x in ds if _khop(x, mau)] if mau else []     # không còn chữ/số: không khớp
    tang = lk["chieu"] == "tang"
    # Thiếu số (None) luôn xuống cuối, cả hai chiều.
    ds.sort(key=lambda x: (x.get(lk["sap"]) is None,
                           (1 if tang else -1) * float(x.get(lk["sap"]) or 0), x["ten"]))
    so_trang = max(1, -(-len(ds) // KENH_MOI_TRANG))
    trang = min(lk["trang"], so_trang)
    chua_ro = None
    if chua and (chua.get("hien_thi") or chua.get("chi")):
        chua_ro = {"ten": "Chưa xác định", "so_ad": int(chua.get("so_ad") or 0),
                   **_so(chua), "tuong_tac": QC.tuong_tac(chua)}
    return {"rows": ds[(trang - 1) * KENH_MOI_TRANG: trang * KENH_MOI_TRANG],
            "tong": int(r.get("tong") or 0), "tong_khop": len(ds), "trang": trang,
            "so_trang": so_trang, "loc": {**lk, "trang": trang},
            "cac_loai": [(k, NHAN[k], dem[k]) for k in NHAN if dem.get(k)],
            "do_phu": round(a / (a + b) * 100, 1) if a + b else None, "do_phu_theo": do,
            "chua_ro": chua_ro}
