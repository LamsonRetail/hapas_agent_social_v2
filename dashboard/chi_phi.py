"""Dự báo chi phí theo dõi nguồn cho trang Ngân sách (chủ dự án 15/10/2026: "dashboard phải quản
trị được chi phí — tăng giảm chi phí điều chỉnh được từ platform hoặc từ chính dashboard").

Hai tầng trần (đã chốt): platform giữ trần THÁNG cấp cửa hàng (KDLA — chưa có, platform PR #101),
dashboard giữ trần tháng từng dự án (`du_an.tran_usd_thang`); Mark áp trần THẤP HƠN. Module này
chỉ TÍNH, thuần Python, không SQL, không import module nào của Mark (venv dashboard không có).

Công thức chép từ Mark — PHẢI khớp, có bài thử đối chiếu (`tests/test_dashboard_chi_phi.py`):
  • Một lượt actor (`theo_doi._uoc_phan`): (đơn vị × giá + phí khởi động actor) × hệ số 1,3; đơn
    vị = số bài mỗi lần (TikTok/Facebook; Threads tối thiểu 10) hoặc 1 tài khoản (Instagram);
    YouTube 0 (API miễn phí).
  • Giá `theo_doi._GIA`, hệ số `theo_doi._HE_SO_UOC`, phí khởi động `apify_tool._START_COST`.
Dự báo cấp tháng:
  • Mỗi nguồn ĐANG theo dõi chạy (số ngày) / chu_ky_ngay lượt; phần tiền theo bài/tài khoản tính
    riêng từng nguồn.
  • Phí khởi động actor tính GẦN ĐÚNG một lần mỗi nền tảng mỗi ngày quét (Threads: một lần mỗi lô
    20 tài khoản); nền tảng có ngày quét khi nguồn có chu kỳ ngắn nhất tới hạn -> (số ngày) / chu
    kỳ ngắn nhất của nền tảng.
  • "Còn lại của tháng" = thời gian thật từ bây giờ tới 0 giờ ngày 1 tháng sau (giờ VN), tính lẻ
    ngày: lịch chạy hằng ngày lúc nào trong ngày cũng không bị đếm hai lần hay bỏ sót có hệ thống.
"""
from __future__ import annotations

import datetime
import math
import re
import unicodedata

VN = datetime.timezone(datetime.timedelta(hours=7))

# ─── chép từ Mark (bài thử đối chiếu; đổi bên Mark thì đổi ở đây) ───
#: `theo_doi._GIA` — giá đo thật: Facebook theo bài, Instagram theo tài khoản (25/09/2026);
#: Threads (16/10/2026) theo bài, tối thiểu `TH_TOI_THIEU_BAI` bài mỗi tài khoản; TikTok qua TikTok
#: API (16/10/2026) 0,0008/bài (nguồn 5 bài = 2 yêu cầu × 0,002 USD).
GIA = {"tiktok": 0.0008, "facebook": 0.005, "instagram": 0.0026, "youtube": 0.0,
       "threads": 0.0025}
#: `theo_doi._HE_SO_UOC` — ước tính chừa hao hụt (bài ghim, phí lẻ…).
HE_SO_UOC = 1.3
#: `apify_tool._START_COST` — phí khởi động MỖI lượt actor. Threads: actor ép 4 GB RAM, gói
#: FREE 0,02 USD/GB = 0,08 USD (đo 16/10/2026).
START_COST = {"instagram": 0.016, "threads": 0.08, "facebook": 0.00005}
#: `theo_doi.TH_TOI_THIEU_BAI` / `TH_TOI_DA_MOI_LUOT` — actor Threads lấy (và tính tiền) ≥ 10 bài
#: mỗi tài khoản / từ khoá; ≤ 20 tài khoản hoặc từ khoá mỗi lượt.
TH_TOI_THIEU_BAI = 10
TH_TOI_DA_MOI_LUOT = 20

#: `theo_doi._BL_GIA` / `_BL_KHOI_DONG` — giá cào BÌNH LUẬN mỗi bình luận (gói FREE, 15/10/2026;
#: Threads 16/10/2026: actor trả lời 1 GB = 0,02 USD khởi động; TikTok qua TikTok API 16/10/2026).
BL_GIA = {"tiktok": 0.0005, "facebook": 0.0025, "instagram": 0.0026, "youtube": 0.0,
          "threads": 0.0025}
BL_KHOI_DONG = {"facebook": 0.001, "threads": 0.02}
#: `theo_doi._BL_UOC_MOI_BAI` — giữ chỗ mỗi bài khi cào hết (bl_moi_bai = 0).
BL_UOC_MOI_BAI = 60

NGAY_THANG_CAU_HINH = 30     # "theo cấu hình": tháng chuẩn 30 ngày (để so sánh tháng với tháng)


#: `theo_doi._TK_GIA` / `_TK_KHOI` / `TK_*` — tìm theo từ khoá (actor của social_listen).
TK_GIA = {"tiktok": 0.0001, "facebook": 0.00259, "instagram": 0.0004, "youtube": 0.0,
          "threads": 0.0025}
TK_KHOI = {"instagram": 0.016, "facebook": 0.00005, "threads": 0.08}
TK_IG_TOI_DA_TU = 2
TK_FB_TOI_DA = 20
#: TikTok tìm theo từ khoá tính theo YÊU CẦU (`theo_doi.TK_TT_*`, `theo_doi_api.LAM_MOI_TOI_DA`).
TK_TT_YEU_CAU = 0.002
TK_TT_MOI_TRANG = 30
TK_LAM_MOI = 10

#: Báo & Web (16/10/2026, `theo_doi.WEB_*` = `nguon_web`): Google tìm qua actor SERP tính theo TRANG
#: kết quả (10 link), đọc bài bằng HTTP thường 0 USD; trang bị chặn đọc qua website-content-crawler
#: tính theo trang, có trần `boc` trang mỗi lượt (thực tế thường 0–2 trang). Từ khoá gộp OR
#: `WEB_TU_MOI_CAU` từ một câu, tối đa `WEB_TOI_DA_CAU` câu mỗi lượt.
WEB_GIA_TRANG = 0.0005
WEB_GIA_BOC = 0.009
WEB_TU_MOI_CAU = 4
WEB_TOI_DA_CAU = 4
WEB_KQ_MOI_TRANG = 10
WEB_BOC_MAC_DINH = 10
#: `theo_doi.WEB_GIO_GIAN` — ngoài chiến dịch Mark chạy web tối đa một lượt / 20 giờ (≈ 1 lượt mỗi
#: ngày có lượt quét); trong khung chiến dịch thì MỌI lượt.
WEB_GIO_GIAN = 20


def _bo_dau_web(s: str) -> str:
    """Bản sao `nguon_web._bo_dau`: bỏ dấu + thường hoá TỪNG ký tự (đ/Đ -> d)."""
    ra = []
    for c in s or "":
        if c in "đĐ":
            ra.append("d")
            continue
        g = unicodedata.normalize("NFD", c)
        ra.append((g[0] if g and unicodedata.category(g[0]) != "Mn" else c).lower()[:1] or c)
    return "".join(ra)


def _tu_web(s: str) -> list[str]:
    """Bản sao `nguon_web._tu`: các chữ/số (bỏ dấu) của một từ khoá."""
    return re.findall(r"[^\W_]+", _bo_dau_web(s))


def rut_gon_web(tu_khoa: list[str]) -> list[str]:
    """Bản sao `nguon_web.rut_gon_tu_khoa`: bỏ rỗng, bỏ trùng (không phân biệt hoa thường, giữ
    bản gặp trước), bỏ từ khoá đã được từ khoá khác phủ — có "hapas" thì "túi hapas", "hapas.vn"
    thừa (tập chữ của từ khoá kia là tập con THẬT SỰ)."""
    sach: list[str] = []
    for t in tu_khoa or []:
        t = str(t).strip()
        if t and _tu_web(t) and t.lower() not in (x.lower() for x in sach):
            sach.append(t)
    ra = []
    for t in sach:
        ti = set(_tu_web(t))
        if not any(x is not t and set(_tu_web(x)) < ti for x in sach):
            ra.append(t)
    return ra


def so_cau_web(tu: list[str]) -> int:
    """Bản sao `nguon_web.so_cau_tim`: ⌈từ khoá rút gọn / 4⌉ câu tìm, tối đa 4."""
    n = len(rut_gon_web(tu))
    return min(WEB_TOI_DA_CAU, math.ceil(n / WEB_TU_MOI_CAU)) if n else 0


def uoc_web(so_bai: int, tu: list[str], boc: int = WEB_BOC_MAC_DINH) -> float:
    """Bản sao `theo_doi.uoc_web`: USD TỐI ĐA một lượt Báo & Web = (câu × ⌈số kết quả / 10⌉ trang
    × 0,0005 + `boc` trang đọc dự phòng × 0,009) × 1,3; 0 khi không có câu tìm hoặc số bài ≤ 0."""
    cau = so_cau_web(tu)
    if so_bai <= 0 or cau <= 0:
        return 0.0
    trang = max(1, math.ceil(max(0, int(so_bai)) / WEB_KQ_MOI_TRANG))
    return round((cau * trang * WEB_GIA_TRANG + max(0, int(boc)) * WEB_GIA_BOC) * HE_SO_UOC, 4)


def uoc_tu_khoa_luot(so_bai: int, tu: list[str]) -> float:
    """Bản sao `theo_doi.uoc_tu_khoa`: USD tối đa một lượt tìm theo từ khoá của dự án (mọi nền
    tảng bật, cùng số bài)."""
    return round(sum(uoc_tk_nen_tang(p, so_bai, tu) for p in NEN_TANG), 4)


def uoc_binh_luan_luot(so_bai: int, moi_bai: int, p: str = "facebook") -> float:
    """Bản sao `theo_doi.uoc_binh_luan`: USD TỐI ĐA cào bình luận một lượt (giá Facebook khi
    chưa biết bài nào — thực tế thấp hơn: chỉ bài có bình luận mới/tăng mới được cào lại)."""
    moi_bai = moi_bai or BL_UOC_MOI_BAI
    if not so_bai or not BL_GIA.get(p):
        return 0.0
    return round((so_bai * moi_bai * BL_GIA[p] + BL_KHOI_DONG.get(p, 0.0)) * HE_SO_UOC, 4)
TOP_NGUON_TON = 3


def _so(v, mac_dinh: int) -> int:
    try:
        return max(1, int(v))
    except (TypeError, ValueError):
        return mac_dinh


def _so_bai_th(p, so_bai: int) -> int:
    """Bản sao `theo_doi._so_bai_nguon`: Threads lấy (và tính tiền) tối thiểu 10 bài/tài khoản."""
    return max(TH_TOI_THIEU_BAI, so_bai) if p == "threads" else so_bai


def don_vi(n: dict) -> int:
    """Đơn vị tính tiền mỗi lượt của một nguồn: số bài (TikTok/Facebook; Threads ≥ 10), 1 tài
    khoản (Instagram — actor trả 12 bài mới nhất bất kể số bài), 0 với YouTube."""
    p = n.get("nen_tang")
    if not GIA.get(p):
        return 0
    return 1 if p == "instagram" else _so_bai_th(p, _so(n.get("so_bai_moi_lan"), 5))


def uoc_mot_luot(p: str, so_nguon: int, so_bai: int) -> float:
    """Bản sao `theo_doi._uoc_phan`: USD một lượt actor gồm `so_nguon` nguồn, mỗi nguồn `so_bai`
    bài (Instagram tính theo tài khoản; Threads ≥ 10 bài), cộng phí khởi động, nhân hệ số."""
    gia = GIA.get(p, 0.0)
    if not gia or not so_nguon:
        return 0.0
    dv = so_nguon if p == "instagram" else so_nguon * _so_bai_th(p, so_bai)
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
        if p == "threads":                 # ≤ 20 tài khoản mỗi lượt actor: mỗi lô một phí khởi động
            kd_ngay *= -(-len(ds) // TH_TOI_DA_MOI_LUOT)
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


# ───── cấu hình theo nền tảng (bản sao `theo_doi.cau_hinh` — đợt 2e, bài thử đối chiếu) ─────
#: "web" (Báo & Web, 16/10/2026): chỉ tìm theo từ khoá — không cào bình luận (giá bình luận 0).
NEN_TANG = ("tiktok", "facebook", "instagram", "youtube", "threads", "web")
#: `theo_doi.MAC_DINH_TAT` — nền tảng TẮT khi `du_an.cau_hinh` chưa ghi `bat` (Threads, 16/10/2026:
#: deploy không tự tiêu tiền; chủ dự án bật trên trang này).
MAC_DINH_TAT = ("threads", "web")   # web: chỉ HAPAS bật (16/10)
SO_TOI_DA = 1_000_000        # chỉ chặn số rác — chủ dự án 15/10: "không có giới hạn"
GIOI_HAN = {"tk_so_bai": (0, SO_TOI_DA), "tk_so_tu": (1, 50), "bl_so_bai": (0, SO_TOI_DA),
            "bl_moi_bai": (0, SO_TOI_DA)}


def _kep(v, lo: int, hi: int, md: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return md


def _so_rieng(v, lo: int, hi: int, md: int) -> int:
    if isinstance(v, bool):
        return md
    try:
        n = int(v)
    except (TypeError, ValueError):
        return md
    return md if n < lo else min(hi, n)


def cau_hinh(du_an: dict, nhom: str, p: str) -> dict:
    """Cấu hình HIỆU LỰC của một nền tảng — y hệt `theo_doi.cau_hinh` của Mark (cột tk_bat /
    bl_bat là công tắc tổng; thiếu `bat` thì bật trừ `MAC_DINH_TAT`; số bỏ trống/rác lấy cột
    chung, áp cho TỪNG nền tảng)."""
    goc = du_an.get("cau_hinh") if isinstance(du_an.get("cau_hinh"), dict) else {}
    nh = goc.get(nhom) if isinstance(goc.get(nhom), dict) else {}
    rieng = nh.get(p) if isinstance(nh.get(p), dict) else {}
    bat_rieng = rieng.get("bat", p not in MAC_DINH_TAT) is True
    if nhom == "tu_khoa":
        chung = _kep(du_an.get("tk_so_bai") or 0, *GIOI_HAN["tk_so_bai"], 0)
        so = _so_rieng(rieng.get("so_bai"), *GIOI_HAN["tk_so_bai"], chung)
        ra = {"bat": bool(du_an.get("tk_bat", True)) and bat_rieng and so > 0,
              "so_bai": so,
              "so_tu": _so_rieng(rieng.get("so_tu"), *GIOI_HAN["tk_so_tu"], TK_IG_TOI_DA_TU)}
        if p == "web":
            # Trần trang đọc dự phòng mỗi lượt: 0 = tắt (hợp lệ, không rơi về mặc định).
            b = rieng.get("boc")
            ra["boc"] = (WEB_BOC_MAC_DINH if isinstance(b, bool) or b is None
                         else _kep(b, 0, SO_TOI_DA, WEB_BOC_MAC_DINH))
        return ra
    chung = _kep(du_an.get("bl_so_bai") or 0, *GIOI_HAN["bl_so_bai"], 0)
    so = _so_rieng(rieng.get("so_bai"), *GIOI_HAN["bl_so_bai"], chung)
    moi_chung = _kep(du_an.get("bl_moi_bai") or 0, *GIOI_HAN["bl_moi_bai"], 0)
    moi = _so_rieng(rieng.get("moi_bai"), *GIOI_HAN["bl_moi_bai"], moi_chung)
    return {"bat": bool(du_an.get("bl_bat", True)) and bat_rieng and so > 0,
            "so_bai": so, "moi_bai": 5 if 0 < moi < 5 else moi}


def cau_hinh_hien_thi(goc) -> dict:
    """`du_an.cau_hinh` cho biểu mẫu trang Ngân sách: nền tảng `MAC_DINH_TAT` chưa ghi `bat` thì
    điền `bat: False` — ô bật hiện ĐÚNG trạng thái hiệu lực (tắt), không theo cột tk_bat/bl_bat
    (bấm Lưu mà không để ý thì Threads không tự bật). Không sửa dict gốc."""
    goc = goc if isinstance(goc, dict) else {}
    ra = dict(goc)
    for nhom in ("tu_khoa", "binh_luan"):
        nh = dict(goc.get(nhom)) if isinstance(goc.get(nhom), dict) else {}
        for p in MAC_DINH_TAT:
            rieng = dict(nh.get(p)) if isinstance(nh.get(p), dict) else {}
            rieng.setdefault("bat", False)
            nh[p] = rieng
        ra[nhom] = nh
    return ra


def _norm(s: str) -> str:
    """Bản sao `apify_tool._norm`: bỏ dấu (kể cả đ) + thường hoá."""
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def tu_tim(du_an: dict) -> list[str]:
    """Bản sao `theo_doi.tu_tim`: từ khoá tìm (bỏ trùng, giữ thứ tự, tối đa 12)."""
    ra: list[str] = []
    for x in du_an.get("tu_khoa") or [du_an.get("ten") or ""]:
        x = " ".join(str(x).split())
        if x and _norm(x) not in {_norm(y) for y in ra}:
            ra.append(x)
    return ra[:GIOI_HAN["tk_so_tu"][1]]


def _tu_ig(tu: list[str], so_tu: int) -> list[str]:
    return [t for t in tu if " " not in t][:so_tu]


def tu_gui(p: str, tu: list[str], so_tu: int = TK_IG_TOI_DA_TU, so_bai: int = 0) -> list[str]:
    """Bản sao `theo_doi._tu_cho`: từ khoá thật sự gửi actor. Instagram: `so_tu` từ không dấu
    cách; Threads: `so_bai // 10` từ đầu (≥ 1, ≤ 20 — actor lấy ≥ 10 bài mỗi từ)."""
    if p == "instagram":
        return _tu_ig(tu, so_tu)
    if p == "threads":
        return tu[:max(1, min(TH_TOI_DA_MOI_LUOT, so_bai // TH_TOI_THIEU_BAI))]
    return tu


def uoc_tk_nen_tang(p: str, so_bai: int, tu: list[str], so_tu: int = TK_IG_TOI_DA_TU,
                    fb_toi_da: int = TK_FB_TOI_DA, boc: int = WEB_BOC_MAC_DINH) -> float:
    """Bản sao `theo_doi.uoc_tu_khoa_nen_tang` (web: `uoc_web` với trần đọc dự phòng `boc`)."""
    if p == "web":
        return uoc_web(so_bai, tu, boc)
    q = tu_gui(p, tu, so_tu, so_bai)
    gia = TK_GIA.get(p, 0.0)
    if not q or not gia or so_bai <= 0:
        return 0.0
    if p == "instagram":
        return round(len(q) * (TK_KHOI["instagram"] + so_bai * gia) * HE_SO_UOC, 4)
    if p == "tiktok":
        trang = 2 * math.ceil(math.ceil(so_bai / len(q)) / TK_TT_MOI_TRANG) + 1
        return round((len(q) * trang + TK_LAM_MOI) * TK_TT_YEU_CAU * HE_SO_UOC, 4)
    n = (min(so_bai, fb_toi_da) if p == "facebook"
         else max(so_bai, TH_TOI_THIEU_BAI) if p == "threads" else so_bai)
    return round((n * gia + TK_KHOI.get(p, 0.0)) * HE_SO_UOC, 4)


def bang_cau_hinh(du_an: dict) -> dict:
    """Cấu hình hiệu lực + ước tính USD/lượt từng nền tảng cho trang Ngân sách. Dashboard không
    biết gói Apify nên Facebook tính theo đúng số bài cấu hình (mức TRẦN; gói Free thực tế chỉ
    lấy tối đa `TK_FB_TOI_DA` bài) — báo cao hơn còn hơn báo thiếu. `tu_khoa[p]["so_tu_gui"]`:
    số từ khoá THẬT SỰ tìm của nền tảng (Threads ít hơn khi số bài < 10 × số từ; web: số từ khoá
    sau rút gọn, kèm `so_cau` câu tìm). `uoc_web` = phần Báo & Web của `uoc_tk` (ngoài chiến dịch
    chạy ≤ 1 lượt/ngày — `luot_web_thuong`), `uoc_tk_mxh` = phần còn lại (chạy mọi lượt)."""
    tu = tu_tim(du_an)
    tk = {p: {**cau_hinh(du_an, "tu_khoa", p)} for p in NEN_TANG}
    bl = {p: {**cau_hinh(du_an, "binh_luan", p)} for p in NEN_TANG}
    for p in NEN_TANG:
        tk[p]["uoc"] = (uoc_tk_nen_tang(p, tk[p]["so_bai"], tu, tk[p]["so_tu"],
                                        fb_toi_da=GIOI_HAN["tk_so_bai"][1],
                                        boc=tk[p].get("boc", WEB_BOC_MAC_DINH))
                        if tk[p]["bat"] else 0.0)
        tk[p]["so_tu_gui"] = (len(rut_gon_web(tu)) if p == "web"
                              else len(tu_gui(p, tu, tk[p]["so_tu"], tk[p]["so_bai"])))
        bl[p]["uoc"] = (uoc_binh_luan_luot(bl[p]["so_bai"], bl[p]["moi_bai"], p)
                        if bl[p]["bat"] else 0.0)
    tk["web"]["so_cau"] = so_cau_web(tu)
    uoc_tk = round(sum(x["uoc"] for x in tk.values()), 4)
    return {"tu_khoa": tk, "binh_luan": bl, "so_tu_khoa": len(tu),
            "uoc_tk": uoc_tk, "uoc_web": tk["web"]["uoc"],
            "uoc_tk_mxh": round(uoc_tk - tk["web"]["uoc"], 4),
            "uoc_bl": round(sum(x["uoc"] for x in bl.values()), 4)}


# ───── lịch quét tự động (15/10/2026): chi phí theo TẦN SUẤT lịch, không còn giả định 1 lượt/ngày ─────
def nguon_moi_luot(nguon: list[dict]) -> float:
    """USD TỐI ĐA phần NGUỒN của MỘT lượt quét mọi nguồn (lịch `quet_moi_nguon`): chia lượt actor
    đúng như `theo_doi.chia_phan` — mỗi (nền tảng, số bài mỗi lần) một lượt (Threads: số bài
    ≥ 10, ≤ 20 tài khoản mỗi lượt), mỗi lượt = (đơn vị × giá + phí khởi động) × 1,3
    (`uoc_mot_luot`). Nguồn tạm dừng, YouTube: 0."""
    nhom: dict[tuple[str, int], int] = {}
    for n in nguon:
        p = n.get("nen_tang")
        if (n.get("trang_thai") or "dang_theo_doi") != "dang_theo_doi" or not GIA.get(p):
            continue
        k = (p, 0 if p == "instagram" else _so_bai_th(p, _so(n.get("so_bai_moi_lan"), 5)))
        nhom[k] = nhom.get(k, 0) + 1
    tong = 0.0
    for (p, bai), so in nhom.items():
        lo = TH_TOI_DA_MOI_LUOT if p == "threads" else so
        tong += sum(uoc_mot_luot(p, min(lo, so - i), bai) for i in range(0, so, lo))
    return round(tong, 4)


def uoc_lich(lich: dict, bang: dict, nguon: list[dict]) -> dict:
    """USD TỐI ĐA một lượt của một lịch: tìm theo từ khoá + cào bình luận (`bang_cau_hinh` — chạy
    mỗi lượt) + phần nguồn khi lịch quét mọi nguồn. Lịch thường: nguồn tốn theo CHU KỲ của nguồn
    (đã nằm trong `du_bao`), không nhân theo số lượt.
    Báo & Web (`web` = USD một lượt web): lịch chiến dịch chạy web MỌI lượt nên nằm trong
    `tk_bl` / `moi_luot`; lịch thường chỉ ≤ 1 lượt web mỗi ngày (`WEB_GIO_GIAN`) nên KHÔNG nằm
    trong `moi_luot` — tính riêng theo `luot_web_thuong` (`du_bao_lich`)."""
    web = round(float(bang.get("uoc_web") or 0), 4)
    cd = lich.get("kieu") == "chien_dich"
    tk = float(bang.get("uoc_tk") or 0) - (0.0 if cd else web)
    tk_bl = round(max(0.0, tk) + float(bang.get("uoc_bl") or 0), 4)
    ng = nguon_moi_luot(nguon) if lich.get("quet_moi_nguon") else 0.0
    return {"tk_bl": tk_bl, "nguon": ng, "moi_luot": round(tk_bl + ng, 4), "web": web,
            "web_moi_luot": cd}


def luot_web_thuong(cac_lich: list[dict], tu: datetime.datetime, den: datetime.datetime) -> int:
    """Số lượt Báo & Web của các LỊCH THƯỜNG đang bật trong (tu, den]: ngoài chiến dịch Mark chạy
    web tối đa một lượt / `WEB_GIO_GIAN` giờ -> đếm số NGÀY (giờ VN) có ít nhất một mốc lịch
    thường ngoài khung chiến dịch (≤ min(số lượt, số ngày)). Lượt chiến dịch đã tính web trong
    `uoc_lich` nên không đếm ở đây."""
    from dashboard import lich_quet as LQ
    khung = [k for x in cac_lich if x.get("bat") and (k := LQ.khung_chien_dich(x))]
    ngay: set = set()
    for x in cac_lich:
        if not x.get("bat") or x.get("kieu") == "chien_dich":
            continue
        for m in LQ.lap_moc(x.get("kieu") or "", x.get("cau_hinh") or {}, tu):
            if m > den:
                break
            d = m.astimezone(VN).date()
            if d not in ngay and not any(a <= m <= b for a, b in khung):
                ngay.add(d)
    return len(ngay)


def du_bao_lich(cac_lich: list[dict], bang: dict, nguon: list[dict],
                bay_gio: datetime.datetime) -> dict:
    """Ngân sách theo LỊCH QUÉT TỰ ĐỘNG đang bật của một dự án: số lượt còn lại tháng này (giờ
    VN) và trong 30 ngày tới (mốc lịch thường trong khung chiến dịch không tính — nhường), cùng
    phần nguồn thêm của lịch quét mọi nguồn. Không có lịch đang bật -> {"co_lich": False}
    (trang Ngân sách giữ giả định cũ: 1 lượt/ngày từ lịch console).
    Báo & Web: `luot_web_con_lai` / `luot_web_30` = số lượt web (≤ 1/ngày theo lịch thường —
    `luot_web_thuong` — + mọi lượt chiến dịch); `web_them` / `web_them_30` = USD web của lịch
    thường (phần chiến dịch đã nằm trong `moi_luot` của lịch đó).
    -> {co_lich, luot_con_lai, luot_30, nguon_them, nguon_them_30, theo_lich: {id: lượt tháng},
        luot_web_con_lai, luot_web_30, web_them, web_them_30}."""
    from dashboard import lich_quet as LQ
    if not any(x.get("bat") for x in cac_lich):
        return {"co_lich": False}
    bay_gio = bay_gio if bay_gio.tzinfo else bay_gio.replace(tzinfo=datetime.timezone.utc)
    het = _dau_thang_sau(bay_gio) - datetime.timedelta(microseconds=1)
    thang = LQ.dem_luot_du_an(cac_lich, bay_gio, het)
    ba_muoi = LQ.dem_luot_du_an(cac_lich, bay_gio, bay_gio + datetime.timedelta(days=30))
    ng = nguon_moi_luot(nguon)
    moi = {x.get("id") for x in cac_lich if x.get("bat") and x.get("quet_moi_nguon")}
    cd = {x.get("id") for x in cac_lich if x.get("bat") and x.get("kieu") == "chien_dich"}
    w_thang = luot_web_thuong(cac_lich, bay_gio, het)
    w_30 = luot_web_thuong(cac_lich, bay_gio, bay_gio + datetime.timedelta(days=30))
    web = float(bang.get("uoc_web") or 0)
    return {"co_lich": True, "luot_con_lai": sum(thang.values()),
            "luot_web_con_lai": w_thang + sum(n for i, n in thang.items() if i in cd),
            "luot_web_30": w_30 + sum(n for i, n in ba_muoi.items() if i in cd),
            "web_them": round(w_thang * web, 4), "web_them_30": round(w_30 * web, 4),
            "luot_30": sum(ba_muoi.values()),
            "nguon_them": round(sum(n * ng for i, n in thang.items() if i in moi), 4),
            "nguon_them_30": round(sum(n * ng for i, n in ba_muoi.items() if i in moi), 4),
            "theo_lich": thang}


def hang_so_cho_trinh_duyet() -> dict:
    """Hằng số cho phép tính lại ngay trên trình duyệt khi sửa số bài / chu kỳ / cấu hình."""
    return {"gia": GIA, "he_so": HE_SO_UOC, "start": START_COST, "ngay": NGAY_THANG_CAU_HINH,
            "tk_gia": TK_GIA, "tk_khoi": TK_KHOI, "tk_fb_toi_da": TK_FB_TOI_DA,
            "tk_ig_so_tu": TK_IG_TOI_DA_TU, "bl_gia": BL_GIA, "bl_khoi": BL_KHOI_DONG,
            "bl_uoc_moi_bai": BL_UOC_MOI_BAI, "gioi_han": GIOI_HAN, "nen_tang": NEN_TANG,
            # Threads (16/10/2026): ≥ 10 bài mỗi tài khoản / từ khoá, ≤ 20 mỗi lượt; mặc định tắt.
            "th_toi_thieu_bai": TH_TOI_THIEU_BAI, "th_toi_da_moi_luot": TH_TOI_DA_MOI_LUOT,
            "mac_dinh_tat": MAC_DINH_TAT,
            # TikTok tìm theo từ khoá tính theo yêu cầu (16/10/2026) — `uoc_tk_nen_tang`.
            "tk_tt_yeu_cau": TK_TT_YEU_CAU, "tk_tt_moi_trang": TK_TT_MOI_TRANG,
            "tk_lam_moi": TK_LAM_MOI,
            # Báo & Web (16/10/2026) — `uoc_web`, `rut_gon_web`.
            "web": {"gia_trang": WEB_GIA_TRANG, "gia_boc": WEB_GIA_BOC,
                    "tu_moi_cau": WEB_TU_MOI_CAU, "toi_da_cau": WEB_TOI_DA_CAU,
                    "kq_moi_trang": WEB_KQ_MOI_TRANG, "boc_mac_dinh": WEB_BOC_MAC_DINH}}
