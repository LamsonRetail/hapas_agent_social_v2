"""Dự báo chi phí theo dõi nguồn cho trang Ngân sách (chủ dự án 15/10/2026: "dashboard phải quản
trị được chi phí — tăng giảm chi phí điều chỉnh được từ platform hoặc từ chính dashboard").

Hai tầng trần (đã chốt): platform giữ trần THÁNG cấp cửa hàng (KDLA — chưa có, platform PR #101),
dashboard giữ trần tháng từng dự án (`du_an.tran_usd_thang`); Mark áp trần THẤP HƠN. Module này
chỉ TÍNH, thuần Python, không SQL, không import module nào của Mark (venv dashboard không có).

Công thức chép từ Mark — PHẢI khớp, có bài thử đối chiếu (`tests/test_dashboard_chi_phi.py`):
  • Một lượt actor (`theo_doi._uoc_phan`): (đơn vị × giá + phí khởi động actor) × hệ số 1,3; đơn
    vị = số bài mỗi lần (TikTok/Facebook) hoặc 1 tài khoản (Instagram); YouTube 0 (API miễn phí).
  • Giá `theo_doi._GIA`, hệ số `theo_doi._HE_SO_UOC`, phí khởi động `apify_tool._START_COST`.
Dự báo cấp tháng:
  • Mỗi nguồn ĐANG theo dõi chạy (số ngày) / chu_ky_ngay lượt; phần tiền theo bài/tài khoản tính
    riêng từng nguồn.
  • Phí khởi động actor tính GẦN ĐÚNG một lần mỗi nền tảng mỗi ngày quét; nền tảng có ngày quét
    khi nguồn có chu kỳ ngắn nhất tới hạn -> (số ngày) / chu kỳ ngắn nhất của nền tảng.
  • "Còn lại của tháng" = thời gian thật từ bây giờ tới 0 giờ ngày 1 tháng sau (giờ VN), tính lẻ
    ngày: lịch chạy hằng ngày lúc nào trong ngày cũng không bị đếm hai lần hay bỏ sót có hệ thống.
"""
from __future__ import annotations

import datetime

VN = datetime.timezone(datetime.timedelta(hours=7))

# ─── chép từ Mark (bài thử đối chiếu; đổi bên Mark thì đổi ở đây) ───
#: `theo_doi._GIA` — giá đo thật 25/09/2026: TikTok/Facebook theo bài, Instagram theo tài khoản.
GIA = {"tiktok": 0.003, "facebook": 0.005, "instagram": 0.0026, "youtube": 0.0}
#: `theo_doi._HE_SO_UOC` — ước tính chừa hao hụt (bài ghim, phí lẻ…).
HE_SO_UOC = 1.3
#: `apify_tool._START_COST` — phí khởi động MỖI lượt actor.
START_COST = {"instagram": 0.016, "threads": 0.02, "facebook": 0.00005}

#: `theo_doi._BL_GIA` / `_BL_KHOI_DONG` — giá cào BÌNH LUẬN mỗi bình luận (gói FREE, 15/10/2026).
BL_GIA = {"tiktok": 0.00125, "facebook": 0.0025, "instagram": 0.0026, "youtube": 0.0}
BL_KHOI_DONG = {"facebook": 0.001}

NGAY_THANG_CAU_HINH = 30     # "theo cấu hình": tháng chuẩn 30 ngày (để so sánh tháng với tháng)


def uoc_binh_luan_luot(so_bai: int, moi_bai: int, p: str = "facebook") -> float:
    """Bản sao `theo_doi.uoc_binh_luan`: USD TỐI ĐA cào bình luận một lượt (giá Facebook khi
    chưa biết bài nào — thực tế thấp hơn: chỉ bài có bình luận mới/tăng mới được cào lại)."""
    if not so_bai or not BL_GIA.get(p):
        return 0.0
    return round((so_bai * moi_bai * BL_GIA[p] + BL_KHOI_DONG.get(p, 0.0)) * HE_SO_UOC, 4)
TOP_NGUON_TON = 3


def _so(v, mac_dinh: int) -> int:
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return mac_dinh


def don_vi(n: dict) -> int:
    """Đơn vị tính tiền mỗi lượt của một nguồn: số bài (TikTok/Facebook), 1 tài khoản
    (Instagram — actor trả 12 bài mới nhất bất kể số bài), 0 với YouTube."""
    p = n.get("nen_tang")
    if not GIA.get(p):
        return 0
    return 1 if p == "instagram" else _so(n.get("so_bai_moi_lan"), 5)


def uoc_mot_luot(p: str, so_nguon: int, so_bai: int) -> float:
    """Bản sao `theo_doi._uoc_phan`: USD một lượt actor gồm `so_nguon` nguồn, mỗi nguồn `so_bai`
    bài (Instagram tính theo tài khoản), cộng phí khởi động, nhân hệ số. Dùng cho bài đối chiếu."""
    gia = GIA.get(p, 0.0)
    if not gia or not so_nguon:
        return 0.0
    dv = so_nguon if p == "instagram" else so_nguon * so_bai
    return round((dv * gia + START_COST.get(p, 0.0)) * HE_SO_UOC, 4)


def chi_phi_luot_nguon(n: dict) -> float:
    """Phần tiền theo bài/tài khoản của MỘT nguồn trong một lượt (chưa gồm phí khởi động —
    phí đó chung cho cả nền tảng, xem `phi_khoi_dong_ngay`)."""
    return don_vi(n) * GIA.get(n.get("nen_tang"), 0.0) * HE_SO_UOC


def phi_khoi_dong_ngay(p: str) -> float:
    """Phí khởi động actor một ngày quét của nền tảng (đã nhân hệ số)."""
    return START_COST.get(p, 0.0) * HE_SO_UOC if GIA.get(p) else 0.0


def chi_phi_thang_nguon(n: dict, so_ngay: float = NGAY_THANG_CAU_HINH) -> float:
    """Tiền theo bài/tài khoản của nguồn trong `so_ngay` ngày theo cấu hình hiện tại."""
    return so_ngay / _so(n.get("chu_ky_ngay"), 1) * chi_phi_luot_nguon(n)


# ───────────────────────────── tháng giờ VN ─────────────────────────────
def _dau_thang_sau(bay_gio: datetime.datetime) -> datetime.datetime:
    v = bay_gio.astimezone(VN)
    nam, thang = (v.year + 1, 1) if v.month == 12 else (v.year, v.month + 1)
    return datetime.datetime(nam, thang, 1, tzinfo=VN)


def ngay_con_lai(bay_gio: datetime.datetime) -> float:
    """Số ngày (lẻ) từ `bay_gio` tới 0 giờ ngày 1 tháng sau, giờ VN."""
    if bay_gio.tzinfo is None:
        bay_gio = bay_gio.replace(tzinfo=datetime.timezone.utc)
    return max(0.0, (_dau_thang_sau(bay_gio) - bay_gio).total_seconds() / 86400.0)


def so_ngay_thang(bay_gio: datetime.datetime) -> int:
    v = bay_gio.astimezone(VN) if bay_gio.tzinfo else bay_gio.replace(
        tzinfo=datetime.timezone.utc).astimezone(VN)
    return (_dau_thang_sau(v) - datetime.datetime(v.year, v.month, 1, tzinfo=VN)).days


# ───────────────────────────── dự báo một dự án ─────────────────────────────
def tran_hieu_luc(tran_du_an: float, tran_platform: float | None) -> float:
    """Mark áp trần THẤP HƠN giữa trần platform (cấp cửa hàng) và trần của dự án."""
    tran = float(tran_du_an or 0)
    return tran if tran_platform is None else min(tran, float(tran_platform))


def du_bao(nguon: list[dict], da_tieu: float, tran_du_an: float, tran_platform: float | None,
           bay_gio: datetime.datetime) -> dict:
    """Dự báo tiền theo dõi cả tháng của MỘT dự án. Nguồn tạm dừng không tính.

    -> {ngay_con_lai, da_tieu, con_lai (USD phần còn lại), du_bao_thang (đã tiêu + còn lại),
        thang_cau_hinh (USD một tháng 30 ngày theo cấu hình), tran_du_an, tran_platform,
        tran (hiệu lực), vuot (bool), vuot_usd, nen_tang: [{nen_tang, so_nguon, nguon_con_lai,
        khoi_dong_con_lai, con_lai, thang_cau_hinh}], nguon: [{id, nen_tang, dinh_danh, ten,
        chu_ky_ngay, so_bai_moi_lan, luot_usd, thang_usd, con_lai_usd}] (tốn nhất trước),
        top_ton: 3 nguồn tốn nhất (> 0)}."""
    con = ngay_con_lai(bay_gio)
    dang = [n for n in nguon if (n.get("trang_thai") or "dang_theo_doi") == "dang_theo_doi"]
    theo_nguon = []
    for n in dang:
        theo_nguon.append({
            "id": n.get("id"), "nen_tang": n.get("nen_tang"), "dinh_danh": n.get("dinh_danh"),
            "ten": n.get("ten") or n.get("dinh_danh"),
            "chu_ky_ngay": _so(n.get("chu_ky_ngay"), 1),
            "so_bai_moi_lan": _so(n.get("so_bai_moi_lan"), 5),
            "luot_usd": round(chi_phi_luot_nguon(n), 6),
            "thang_usd": round(chi_phi_thang_nguon(n), 6),
            "con_lai_usd": round(chi_phi_thang_nguon(n, con), 6)})
    theo_nguon.sort(key=lambda x: (-x["thang_usd"], str(x["dinh_danh"])))
    nen_tang = []
    for p in sorted({x["nen_tang"] for x in theo_nguon}):
        ds = [x for x in theo_nguon if x["nen_tang"] == p]
        ky_ngan = min(x["chu_ky_ngay"] for x in ds)
        kd_ngay = phi_khoi_dong_ngay(p)
        nguon_con = sum(x["con_lai_usd"] for x in ds)
        kd_con = con / ky_ngan * kd_ngay
        nen_tang.append({
            "nen_tang": p, "so_nguon": len(ds),
            "nguon_con_lai": round(nguon_con, 6), "khoi_dong_con_lai": round(kd_con, 6),
            "con_lai": round(nguon_con + kd_con, 6),
            "thang_cau_hinh": round(sum(x["thang_usd"] for x in ds)
                                    + NGAY_THANG_CAU_HINH / ky_ngan * kd_ngay, 6)})
    nen_tang.sort(key=lambda x: (-x["con_lai"], x["nen_tang"]))
    con_lai = sum(x["con_lai"] for x in nen_tang)
    da_tieu = float(da_tieu or 0)
    tran = tran_hieu_luc(tran_du_an, tran_platform)
    du_bao_thang = da_tieu + con_lai
    return {
        "ngay_con_lai": round(con, 4), "da_tieu": round(da_tieu, 4),
        "con_lai": round(con_lai, 4), "du_bao_thang": round(du_bao_thang, 4),
        "thang_cau_hinh": round(sum(x["thang_cau_hinh"] for x in nen_tang), 4),
        "tran_du_an": float(tran_du_an or 0),
        "tran_platform": None if tran_platform is None else float(tran_platform),
        "tran": tran, "vuot": du_bao_thang > tran + 1e-9,
        "vuot_usd": round(max(0.0, du_bao_thang - tran), 4),
        "nen_tang": nen_tang, "nguon": theo_nguon,
        "top_ton": [x for x in theo_nguon if x["thang_usd"] > 0][:TOP_NGUON_TON],
    }


def hang_so_cho_trinh_duyet() -> dict:
    """Hằng số cho phép tính lại ngay trên trình duyệt khi sửa số bài / chu kỳ (trang Nguồn)."""
    return {"gia": GIA, "he_so": HE_SO_UOC, "start": START_COST, "ngay": NGAY_THANG_CAU_HINH}
