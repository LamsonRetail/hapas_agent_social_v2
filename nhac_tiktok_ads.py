"""Nhắc quản trị viên gia hạn kết nối TikTok Ads của dashboard (19/10/2026, chủ dự án chốt).

Vì sao: đăng nhập TikTok for Business (MCP) của dashboard dùng được đúng 30 ngày — TikTok KHÔNG gia
hạn refresh token khi làm mới (đo 19/10/2026). Hết hạn là số quảng cáo ngừng cập nhật mà không ai
thấy, nên Mark nhắn trước 7, 3 và 1 ngày (và khi đã hết hạn), kèm link trang Quản trị.

Mark chỉ ĐỌC các cột không bí mật của `ket_noi_ngoai` (nha_cung_cap, loai, trang_thai,
refresh_het_luc, goi_ok_luc, loi_cuoi — quyền theo cột trong deploy/lang-nghe/schema.sql); token
không bao giờ tới tiến trình Mark. Loại `api_token` không hết hạn → không nhắc.

Móc vào nhịp 30 giây có sẵn của lịch quét (`quet_tu_dong.mot_nhip`, chỉ tiến trình giữ quyền chủ
việc nền chạy) — tự giãn: đọc kho tối đa mỗi giờ một lần, chỉ nhắn 08:00–21:00 giờ VN, mỗi mốc
(7/3/1/hết hạn) một tin cho mỗi lần đăng nhập. Nơi nhận: `MARK_TIKTOK_NHAC` (`oc_…` nhóm quản trị
hoặc `ou_…`), trống thì dùng `MARK_LICH_QUET_BAO_LOI`; cả hai trống = không đọc kho, không nhắn.
Mark khởi động lại giữa chừng có thể nhắn lại mốc đang ở (một tin) — chấp nhận, không ghi sổ riêng.
"""
from __future__ import annotations

import datetime
import os
import re
import time

VN = datetime.timezone(datetime.timedelta(hours=7))
NGUONG = (1, 3, 7)                 # ngày còn lại: nhắc khi ≤ 7, ≤ 3, ≤ 1
GIO_DOC = 3600.0                   # đọc kho tối đa mỗi giờ
GIO_NHAN = (8, 21)                 # chỉ nhắn trong giờ làm việc (giờ VN)
#: Cột KHÔNG bí mật — đúng các cột role mark được cấp (bài thử so với schema.sql).
COT_DOC = ("nha_cung_cap", "loai", "trang_thai", "refresh_het_luc", "goi_ok_luc", "loi_cuoi")
SQL_DOC = (f"SELECT {', '.join(COT_DOC)} FROM ket_noi_ngoai WHERE nha_cung_cap = 'tiktok_ads'")

_TRANG: dict = {"doc_luc": float("-inf"), "da_gui": set()}


def dia_chi_dashboard() -> str:
    for k in ("DASH_BASE_URL", "MARK_DASHBOARD_URL"):
        v = (os.environ.get(k) or "").strip().rstrip("/")
        if v.startswith("https://"):
            return v
    return "https://social.hapas.vn"


def noi_nhan() -> str:
    """`MARK_TIKTOK_NHAC`, trống thì `MARK_LICH_QUET_BAO_LOI` (cùng dạng ou_/oc_/lark:<app>:oc_)."""
    for k in ("MARK_TIKTOK_NHAC", "MARK_LICH_QUET_BAO_LOI"):
        d = (os.environ.get(k) or "").strip()
        if re.fullmatch(r"(ou_|oc_|lark:[A-Za-z0-9_-]+:oc_)[A-Za-z0-9_-]+", d):
            return d
    return ""


def _doc() -> dict | None:
    import lang_nghe_db
    with lang_nghe_db.ket_noi() as c:
        return c.execute(SQL_DOC).fetchone()


def kiem(bay_gio: datetime.datetime, doc=None) -> dict | None:
    """Có cần nhắc không. -> {"muc": 7|3|1|0, "con_ngay", "van", "khoa"} hoặc None.
    `muc` 0 = đã hết hạn. Hàm thuần trên dòng đọc được (bài thử truyền `doc`)."""
    r = (doc or _doc)()
    if not r or r.get("loai") == "api_token" or r.get("trang_thai") in ("chua_ket_noi", "da_ngat"):
        return None
    het = r.get("refresh_het_luc")
    if not isinstance(het, datetime.datetime):
        return None
    if het.tzinfo is None:
        het = het.replace(tzinfo=datetime.timezone.utc)
    con = (het - bay_gio).total_seconds() / 86400
    if con <= 0 or r.get("trang_thai") == "het_han":
        muc = 0
    else:
        muc = next((n for n in NGUONG if con <= n), None)
        if muc is None:
            return None
    gio = het.astimezone(VN).strftime("%H:%M %d/%m/%Y")
    link = f"{dia_chi_dashboard()}/quan-tri#tiktok"
    if muc == 0:
        van = (f"TikTok Ads: kết nối của dashboard ĐÃ HẾT HẠN ({gio}) — số quảng cáo ngừng cập "
               f"nhật. Quản trị viên mở {link} và bấm “Đăng nhập lại để gia hạn 30 ngày”.")
    else:
        con_chu = f"{int(con)} ngày" if con >= 1 else f"{max(1, int(con * 24))} giờ"
        van = (f"TikTok Ads: kết nối của dashboard còn {con_chu} (hết hạn {gio}). Quản trị viên "
               f"mở {link} và bấm “Đăng nhập lại để gia hạn 30 ngày” trước khi hết hạn.")
    return {"muc": muc, "con_ngay": round(con, 2), "van": van,
            "khoa": f"tiktok-han-{muc}-{het.astimezone(VN):%Y%m%d%H%M}"}


def nhac(bay_gio: datetime.datetime | None = None, *, doc=None, gui=None) -> str | None:
    """Gọi từ nhịp lịch quét. Gửi tối đa một tin mỗi mốc; trả câu đã gửi (để log/bài thử)."""
    dich = noi_nhan()
    if not dich:
        return None
    if time.monotonic() - _TRANG["doc_luc"] < GIO_DOC:
        return None
    bay_gio = bay_gio or datetime.datetime.now(VN)
    if not GIO_NHAN[0] <= bay_gio.astimezone(VN).hour < GIO_NHAN[1]:
        return None
    _TRANG["doc_luc"] = time.monotonic()
    x = kiem(bay_gio, doc)
    if not x or x["khoa"] in _TRANG["da_gui"]:
        return None
    if gui is None:
        import quet_tu_dong
        gui = quet_tu_dong._gui
    gui(dich, x["van"], x["khoa"][:50])
    _TRANG["da_gui"].add(x["khoa"])
    print(f"[nhac_tiktok_ads] đã nhắc mốc {x['muc']} ngày", flush=True)
    return x["van"]
