"""Ứng dụng web dashboard lắng nghe `social.hapas.vn` (FastAPI + Jinja2, chạy sau Caddy).

Phạm vi (chủ dự án chốt 14/10/2026): chỉ số, dự án + nguồn + đề xuất nguồn, ngân sách theo dõi
tháng, người xem, trạng thái đồng bộ BigQuery. KHÔNG có kỹ năng, persona, công tắc năng lực, trần
mỗi lượt hay lịch "Giao việc" của Mark — những thứ đó ở console platform. Riêng lịch quét TỰ ĐỘNG
của `/theodoi` đặt ở đây (chủ dự án chốt 15/10/2026 "Dashboard + Mark tự chạy"; tab Lịch quét,
bảng `lich_quet`, Mark tự chạy theo mốc — `quet_tu_dong.py`).

Kiểm thử được mà không cần Postgres hay mạng: `tao_app(kho=…, cau_hinh=…, lark=…, dong_bo=…)`
nhận bản giả. Chạy thật: `uvicorn --factory dashboard.app:tao_app` (đọc env, xem README.md).

Bảo vệ, đừng bỏ khi sửa:
  • Mọi trang/API trừ /suc-khoe, /dang-nhap*, /tinh/* đòi phiên đăng nhập; quyền đọc lại từ
    `nguoi_xem` + `quyen` MỖI lượt (xoá người xem có hiệu lực ngay, không đợi phiên hết hạn).
  • Phân quyền theo BÊN (19/10/2026, `phan_quyen.py`): mỗi dự án thuộc một bên; người xem chỉ
    thấy dự án của bên mình (dự án ngoài phạm vi = "không có dự án này", không lộ dữ liệu), chỉ
    sửa được dự án của bên mình làm Quản lý. Dự án / nguồn / đề xuất / lịch của mỗi thao tác sửa
    luôn đọc lại từ KHO rồi mới kiểm bên — không tin mã dự án trong biểu mẫu.
  • Mọi POST sửa dữ liệu: phiên + mã CSRF + quyền sửa ĐÚNG dự án đó, kiểm ở PHÍA MÁY CHỦ (nút bị
    ẩn trên giao diện chỉ là tiện, không phải chốt chặn).
  • Chuyển hướng chỉ tới đường dẫn tương đối (`nhap_lieu.duong_an_toan`).
  • /noi-bo/co-du-lieu chỉ nhận từ 127.0.0.1/::1, không qua proxy, đúng khoá LANG_NGHE_BAO_KHOA.
"""
from __future__ import annotations

import asyncio
import collections
import contextlib
import copy
import datetime
import hashlib
import hmac
import inspect
import json
import logging
import os
import re
import secrets
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import jinja2
from fastapi import FastAPI, Request
from fastapi.responses import (
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders

from dashboard import chi_phi as CP
from dashboard import chi_so as CS
from dashboard import dang_nhap as DN
from dashboard import danh_ba as DB
from dashboard import kho_sheet_qc as KS
from dashboard import lich_quet as LQ
from dashboard import meta_ads as MA
from dashboard import nhap_lieu as NL
from dashboard import phan_quyen as PQ
from dashboard import quang_cao as QC
from dashboard import tiktok_ads as TA
from dashboard import trang_lich as TL
from dashboard.chuan_chu import bo_dau
from dashboard.kho import BAI_TOI_DA, BL_TOI_DA, LoiDuLieu, LoiKho

THU_MUC = Path(__file__).resolve().parent
VN = CS.VN
# ECharts 5.5.1 phục vụ TỪ CHÍNH dashboard (không CDN: CSP chỉ cho script 'self'). Tệp lấy từ
# https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js, 1.030.855 byte, sha256
# e84270bd0cd5bdf60fefc26d00c2a391cb2e81f4d26a7a9ee16185a54773a3cf — có bài thử canh hash; thay tệp
# thì sửa cả hai dòng dưới (trình duyệt từ chối chạy tệp lệch `integrity`).
ECHARTS = "/tinh/echarts.min.js"
ECHARTS_SRI = "sha256-6EJwvQzVvfYP78JtAMKjkcsugfTSanqe4WGFpUdzo88="
#: Chân trang (15/10/2026): lịch quét đặt ở tab Lịch quét — Mark tự chạy; lịch Giao việc trên
#: console vẫn chạy song song (không còn câu "lịch chỉ đặt trên console").
LICH_CHAY = ("Quét tự động: tab Lịch quét (Mark tự chạy theo giờ/ngày/tuần/chiến dịch, kết quả "
             "hiện ở đây). Lịch Giao việc “/theodoi <mã dự án>” trên console vẫn chạy song song.")
CHU_KY_KIEM = 30.0          # giây; vòng kiểm lượt quét mới khi Mark không báo được
SSE_TOI_DA_KET_NOI = 200    # trình duyệt mở cùng lúc; quá thì từ chối, khỏi cạn bộ nhớ
SSE_MOI_EMAIL = 5           # mỗi người tối đa ngần này tab nghe sự kiện
SSE_KIEM_QUYEN_GIAY = 300.0  # luồng SSE đọc lại vai trò mỗi 5 phút; bị xoá khỏi người xem -> đóng
LUOT_MOI_TRANG = 20
#: Duyệt/từ chối đề xuất hàng loạt (18/10/2026): trần số đề xuất mỗi lần gửi — trang hiện tối đa 200
#: (`kho.cac_de_xuat`), chừa dư; chặn biểu mẫu rác khiến một yêu cầu chạy hàng nghìn giao dịch.
DE_XUAT_HANG_LOAT_TOI_DA = 500
KHOANG_TOI_DA_NGAY = 400
TINH_SONG_SONG = 2          # lượt tính /api/chi-so chạy cùng lúc (MemoryMax 512M)
NHO_CHI_SO_GIAY = 60.0      # kết quả /api/chi-so giữ lại chừng này giây (khoá có mốc lượt quét)
NHO_CHI_SO_TOI_DA = 64
# Dòng thô nhớ lại (bài tới BAI_TOI_DA = 20k/bộ, bình luận tới BL_TOI_DA = 50k/bộ, bài gốc thiếu)
# giới hạn theo TỔNG SỐ DÒNG, không theo số bộ: chừng MỘT khoảng ngày (bài + bình luận) cùng lúc —
# 4 bộ bình luận 50k dòng chữ dài là vượt MemoryMax 512M. Khoảng thứ hai mở thì khoảng cũ bị bỏ.
NHO_DONG_TOI_DA_DONG = BAI_TOI_DA + BL_TOI_DA + 10_000
SUC_KHOE_GIAY = 15.0        # /suc-khoe công khai: không mở kết nối DB mỗi lần gọi
# Danh bạ Lark trên trang Người xem (danh_ba.py): bản đệm trong `nguoi_xem`, làm mới NỀN khi mở
# trang (sau khi đã trả trang) nếu cũ hơn 12 giờ; lần lỗi thì 1 giờ sau mới thử lại. Thêm email:
# đợi Lark tối đa 5 giây để báo ngay email không có/không hoạt động — quá thì lưu vẫn xong.
DANH_BA_GIAY = 12 * 3600
DANH_BA_LOI_GIAY = 3600
DANH_BA_NEN_GIAY = 30.0
DANH_BA_THEM_GIAY = 5.0
# Ô "Thêm người" tìm theo tên (21/10/2026): cả danh bạ đọc một lần, nhớ 30 phút (lỗi: 5 phút).
DANH_BA_DS_GIAY = 1800.0
DANH_BA_DS_LOI_GIAY = 300.0
DANH_BA_DS_TOI_DA_GIAY = 20.0
_CHUA_KIEM = object()
#: TikTok Ads (19/10/2026): cookie giữ lượt OAuth (nonce + PKCE verifier ĐÃ MÃ HOÁ + email quản trị
#: viên), chỉ gửi kèm đường /tiktok, sống 10 phút. Mục "Quảng cáo TikTok" trên menu đọc bên có tài
#: khoản quảng cáo, nhớ 60 giây (không mở kết nối kho mỗi trang).
COOKIE_TIKTOK = "ln_tiktok"
TIKTOK_STATE_GIAY = 600
NHO_BEN_QC_GIAY = 60.0
#: 19/10/2026 (soát): dashboard KHÔNG chạy đồng bộ TikTok trong tiến trình web — chỉ ghi cờ yêu cầu,
#: bộ hẹn giờ tiktok-ads-yeu-cau.timer / meta-ads-yeu-cau.timer (2 phút/lần, 20/10/2026) chạy lượt.
CHO_DONG_BO = "Lượt đồng bộ sẽ chạy trong ≤ 2 phút (bộ hẹn giờ trên máy chủ)."

log = logging.getLogger("lang_nghe.dashboard")

_TIEU_DE_AN_TOAN = {
    "content-security-policy": (
        "default-src 'self'; script-src 'self'; "
        # ECharts đặt style trong HTML tooltip -> cần 'unsafe-inline' cho style (không cho script).
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
        "font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; "
        "form-action 'self'"),
    "x-content-type-options": "nosniff",
    "referrer-policy": "same-origin",
    "x-frame-options": "DENY",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


class _ChuaDangNhap(Exception):
    pass


class _Cam(Exception):
    def __init__(self, thong_diep: str, ma: int = 403):
        super().__init__(thong_diep)
        self.thong_diep, self.ma = thong_diep, ma


# ───────────────────────────── sự kiện thời gian thực ─────────────────────────────
class BangTin:
    """Phát sự kiện tới các trình duyệt đang mở /su-kien. Một tiến trình uvicorn (1 worker)
    nên giữ trong bộ nhớ là đủ; hàng đợi mỗi trình duyệt có giới hạn, đầy thì bỏ sự kiện
    (trang chỉ cần biết "có dữ liệu mới", mất một sự kiện thì sự kiện sau vẫn tải lại)."""

    def __init__(self, toi_da: int = SSE_TOI_DA_KET_NOI, moi_email: int = SSE_MOI_EMAIL):
        self.toi_da, self.moi_email = toi_da, moi_email
        self._hang: dict[asyncio.Queue, str] = {}

    def dang_ky(self, email: str = "") -> asyncio.Queue | None:
        """Hàng đợi mới, hoặc None khi quá trần chung hay quá trần của MỘT người (một tài khoản
        mở hàng trăm tab không chiếm hết suất của cả team)."""
        if len(self._hang) >= self.toi_da or \
                sum(1 for e in self._hang.values() if e == email) >= self.moi_email:
            return None
        q: asyncio.Queue = asyncio.Queue(maxsize=20)
        self._hang[q] = email
        return q

    def huy(self, q: asyncio.Queue) -> None:
        self._hang.pop(q, None)

    def phat(self, ten: str, du_lieu: dict) -> None:
        for q in list(self._hang):
            with contextlib.suppress(asyncio.QueueFull):
                q.put_nowait((ten, du_lieu))

    @property
    def so_ket_noi(self) -> int:
        return len(self._hang)


class NhoDong:
    """Bộ nhớ đệm dòng thô của trang Chỉ số (bài / bình luận / bài gốc thiếu), giới hạn theo
    TỔNG SỐ DÒNG (`toi_da_dong`) chứ không theo số mục: mục ít dùng nhất bị bỏ trước (LRU — đọc
    hay ghi lại một khoá đều đưa nó về cuối hàng). Mục quá `song_giay` bị bỏ ngay khi tra hoặc
    khi ghi mục khác, không nằm chờ bị đẩy ra. Mục mới luôn được giữ (một bộ lớn hơn ngân sách
    vẫn phục vụ lượt hiện tại; lượt sau đọc lại)."""

    def __init__(self, toi_da_dong: int, song_giay: float):
        self.toi_da_dong, self.song_giay = toi_da_dong, song_giay
        self._d: collections.OrderedDict = collections.OrderedDict()

    def lay(self, khoa):
        x = self._d.get(khoa)
        if x is None:
            return None
        if time.monotonic() - x[0] >= self.song_giay:
            del self._d[khoa]
            return None
        self._d.move_to_end(khoa)
        return x[1]

    def dat(self, khoa, gia_tri, so_dong: int) -> None:
        bay_gio = time.monotonic()
        self._d.pop(khoa, None)
        for k in [k for k, x in self._d.items() if bay_gio - x[0] >= self.song_giay]:
            del self._d[k]
        self._d[khoa] = (bay_gio, gia_tri, int(so_dong))
        while len(self._d) > 1 and self.so_dong > self.toi_da_dong:
            self._d.popitem(last=False)

    @property
    def so_dong(self) -> int:
        return sum(x[2] for x in self._d.values())

    def __len__(self) -> int:
        return len(self._d)

    def __contains__(self, khoa) -> bool:
        return khoa in self._d


def _sse(ten: str, du_lieu: dict) -> str:
    return f"event: {ten}\ndata: {json.dumps(du_lieu, ensure_ascii=False)}\n\n"


def bao_cap_nhat(app: FastAPI, du_an: str, luot: int) -> None:
    """Đẩy `cap-nhat` xuống trình duyệt. Hook `sau_cap_nhat` do bên gọi chạy nền riêng."""
    app.state.luot_da_bao.append(luot)
    app.state.bang_tin.phat("cap-nhat", {"du_an": du_an, "luot": luot})


async def chay_hook(app: FastAPI, du_an: str, luot: int) -> None:
    """Gọi lần lượt các hook `app.state.sau_cap_nhat(du_an, luot)`. Hook đồng bộ (vd đồng bộ
    BigQuery, chặn I/O nhiều phút) chạy trong threadpool để không treo vòng sự kiện. Một hook
    lỗi không chặn hook sau; log chỉ tên loại lỗi (thông điệp có thể chứa đường dẫn khoá)."""
    for f in list(app.state.sau_cap_nhat):
        try:
            if inspect.iscoroutinefunction(f):
                await f(du_an, luot)
            else:
                await run_in_threadpool(f, du_an, luot)
        except Exception as e:  # noqa: BLE001
            log.warning("hook sau_cap_nhat lỗi: %s", type(e).__name__)


async def kiem_mot_lan(app: FastAPI) -> bool:
    """So lượt vừa kết thúc gần nhất với lần kiểm trước; đổi thì phát `cap-nhat` (trừ lượt Mark
    đã báo qua /noi-bo). Lần kiểm đầu chỉ ghi mốc. -> có phát hay không."""
    x = await run_in_threadpool(app.state.kho.luot_xong_moi_nhat)
    moc = (int(x["id"]), str(x.get("ket_thuc"))) if x else None
    cu, app.state.moc_luot = app.state.moc_luot, moc
    if cu is _CHUA_KIEM or moc is None or moc == cu or moc[0] in app.state.luot_da_bao:
        return False
    bao_cap_nhat(app, str(x["du_an"]), moc[0])
    viec = asyncio.create_task(chay_hook(app, str(x["du_an"]), moc[0]))
    app.state.viec_nen.add(viec)
    viec.add_done_callback(app.state.viec_nen.discard)
    return True


async def _vong_kiem(app: FastAPI, chu_ky: float) -> None:
    while True:
        try:
            await kiem_mot_lan(app)
        except Exception as e:  # noqa: BLE001 — kho tạm lỗi thì lần sau kiểm lại
            log.warning("kiểm lượt quét mới lỗi: %s", type(e).__name__)
        await asyncio.sleep(chu_ky)


# ───────────────────────────── tiêu đề bảo mật ─────────────────────────────
class _TieuDeAnToan:
    """Middleware ASGI thuần (không dùng BaseHTTPMiddleware để không chặn luồng SSE)."""

    def __init__(self, app, hsts: bool):
        self.app, self.hsts = app, hsts

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        tinh = scope.get("path", "").startswith("/tinh/")
        co_phien_ban = b"v=" in scope.get("query_string", b"")

        async def gui(msg):
            if msg["type"] == "http.response.start":
                h = MutableHeaders(scope=msg)
                for k, v in _TIEU_DE_AN_TOAN.items():
                    h.setdefault(k, v)
                if not tinh:
                    h.setdefault("cache-control", "no-store")   # trang có dữ liệu nội bộ
                else:
                    # 15/10/2026: trình duyệt giữ chi_so.js CŨ (không có cache-control → tự đoán
                    # hạn) chạy trên HTML MỚI → trang hỏng. Link có ?v=<băm nội dung> thì giữ
                    # lâu (đổi tệp là đổi link); link trần thì luôn hỏi lại máy chủ (304).
                    h.setdefault("cache-control", "public, max-age=31536000, immutable"
                                 if co_phien_ban else "no-cache")
                if self.hsts:
                    h.setdefault("strict-transport-security", "max-age=31536000")
            await send(msg)
        await self.app(scope, receive, gui)


# ───────────────────────────── định dạng kiểu Việt ─────────────────────────────
def so_vn(n) -> str:
    try:
        return f"{int(n or 0):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def pt_vn(x) -> str:
    return "—" if x is None else f"{float(x):.1f}".replace(".", ",") + "%"


def usd_vn(x, so_le: int = 2) -> str:
    s = f"{float(x or 0):,.{int(so_le)}f}"
    return s.replace(",", "\0").replace(".", ",").replace("\0", ".")


def so_gon(n) -> str:
    """Số gọn kiểu trang Chỉ số (`soThe` của chi_so.js): ≥ 1 tỷ "1,07 tỷ", ≥ 1 triệu "23,3 tr"."""
    if n is None:
        return "—"
    try:
        x = float(n)
    except (TypeError, ValueError):
        return "—"
    for nguong, don in ((1e9, " tỷ"), (1e6, " tr")):
        if abs(x) >= nguong:
            v = x / nguong
            return (f"{v:.0f}" if abs(v) >= 100 else f"{v:.1f}").replace(".", ",") + don
    return so_vn(round(x))


def so_thap(x, so_le: int = 2) -> str:
    """Số thập phân kiểu Việt (ROAS "2,35"); None → "" (template tự thay "—")."""
    if x is None:
        return ""
    return usd_vn(x, so_le)


def ngay_con(x) -> str:
    """Số ngày còn (thực) → chữ: "23 ngày", "18 giờ", "đã hết hạn"."""
    if x is None:
        return "—"
    x = float(x)
    if x <= 0:
        return "đã hết hạn"
    if x < 1:
        return f"{max(1, int(x * 24))} giờ"
    return f"{int(x)} ngày"


def gio_vn(dt) -> str:
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(VN).strftime("%d/%m/%Y %H:%M")
    if isinstance(dt, datetime.date):
        return dt.strftime("%d/%m/%Y")
    return "—" if not dt else str(dt)


def json_script(obj) -> Markup:
    """JSON nhúng trong <script type="application/json">: thoát '<', '>', '&' để chữ người dùng
    gõ (tên dự án…) không đóng được thẻ script."""
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return Markup(s.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def _phien_ban_tinh() -> dict[str, str]:
    """Băm nội dung từng tệp tĩnh lúc khởi động → `tinh("chi_so.js")` = "/tinh/chi_so.js?v=…":
    deploy đổi tệp là đổi link, trình duyệt không thể dùng lại bản cũ."""
    thu_muc = THU_MUC / "static"
    return {f.name: hashlib.sha256(f.read_bytes()).hexdigest()[:10]
            for f in thu_muc.iterdir() if f.is_file()} if thu_muc.is_dir() else {}


def _tao_mau() -> Jinja2Templates:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(THU_MUC / "templates")),
                             autoescape=True, trim_blocks=True, lstrip_blocks=True)
    pb = _phien_ban_tinh()
    env.globals["tinh"] = lambda ten: f"/tinh/{ten}?v={pb[ten]}" if ten in pb else f"/tinh/{ten}"
    env.filters.update(so_vn=so_vn, pt_vn=pt_vn, usd_vn=usd_vn, gio_vn=gio_vn,
                       so_gon=so_gon, so_thap=so_thap, ngay_con=ngay_con,
                       ten_muc_tieu=lambda x: QC.TEN_MUC_TIEU.get(str(x or ""), x),
                       json_script=json_script, link_an_toan=NL.link_an_toan,
                       # "web" (Báo & Web) không phải nguồn theo dõi được (NL) nhưng có tên hiển thị.
                       ten_nen_tang=lambda p: NL.TEN_NEN_TANG.get(p) or CS.TEN_NEN_TANG.get(p, p),
                       ten_loai=lambda x: CS.TEN_LOAI.get(x, x))
    env.globals.update(TEN_NEN_TANG=NL.TEN_NEN_TANG, LOAI_NGUON=NL.LOAI_NGUON,
                       VAI_TRO=NL.VAI_TRO, TEN_LOAI=CS.TEN_LOAI, LICH_CHAY=LICH_CHAY,
                       ECHARTS=ECHARTS, ECHARTS_SRI=ECHARTS_SRI)
    env.globals["HIEN_DOANH_THU"] = QC.HIEN_DOANH_THU   # 22/10/2026: doanh thu / ROAS tạm ẩn
    return Jinja2Templates(env=env)


# ───────────────────────────── Quảng cáo TikTok: ô KPI + chuỗi biểu đồ ─────────────────────────────
def _o_kpi(d: dict, ma: str) -> dict:
    """Một ô KPI trang Quảng cáo từ dữ liệu ĐÃ lọc tiền (`_du_lieu_qc`)."""
    nhan, goi_y, tien, mau = QC.KPI_QC[ma]
    v = d["kpi"].get(ma)
    tt = d.get("tien_te") or ["VND"]
    if ma == "roas_shop":
        so, du = (so_thap(v) or "—"), (so_thap(v, 4) or "—")
    else:
        so, du = so_gon(v), so_vn(v)
        if tien:
            don = " ₫" if tt == ["VND"] else (" " + tt[0] if len(tt) == 1 else " (nhiều tiền tệ)")
            so, du = so + don, du + don
    truoc = d["kpi_truoc"].get(ma)
    return {"ma": ma, "nhan": nhan, "goi_y": goi_y, "so": so, "day_du": du,
            "doi": d["doi"].get(ma), "mau_doi": mau, "co_truoc": bool(truoc)}


#: Chuỗi trên biểu đồ "Theo ngày" (chọn một) — chỉ chuỗi có trong dữ liệu đã lọc tiền.
_CHUOI_QC = (("chi", "Chi tiêu"), ("hien_thi", "Hiển thị"), ("view_video", "View video"),
             ("engaged_view", "Engaged view"), ("tuong_tac", "Tương tác"), ("follow", "Follow"))


def _bd_qc(d: dict) -> dict:
    ds = d.get("theo_ngay") or []
    co = set(ds[0]) if ds else set()
    return {"ngay": [x["ngay"] for x in ds], "tien_te": d.get("tien_te") or ["VND"],
            "chuoi": [{"ma": m, "ten": t, "ds": [x.get(m) or 0 for x in ds]}
                      for m, t in _CHUOI_QC if m in co]}


# ───────────────────────────── ẩn chi tiết với người chỉ xem ─────────────────────────────
LOI_CHUNG = "có lỗi — người quản lý xem chi tiết"


def an_chi_tiet(nguoi: dict, rows: list[dict], cot_an: tuple = (),
                cot_loi: tuple = ()) -> list[dict]:
    """Người chỉ xem không thấy email người sửa/thêm (`cot_an` -> None) và chữ lỗi thô (có thể
    chứa đường dẫn máy chủ, tên tài khoản dịch vụ, mã lỗi API; `cot_loi` -> dấu "có lỗi"). Lọc ở
    máy chủ trước khi dựng trang, không dựa vào template."""
    if nguoi.get("vai_tro") == "quan_ly":
        return rows
    ra = []
    for r in rows:
        r = dict(r)
        for k in cot_an:
            if k in r:
                r[k] = None
        for k in cot_loi:
            if r.get(k):
                r[k] = LOI_CHUNG
        ra.append(r)
    return ra


def nguon_tu_de_xuat(x: dict, loai, chu_ky, so_bai) -> dict:
    """Đề xuất -> nguồn đã chuẩn hoá để duyệt (dùng chung nút một dòng và duyệt hàng loạt). Định danh
    Mark đề xuất không qua được bộ chuẩn hoá thì thử link trang; vẫn hỏng -> `NL.LoiNhap`."""
    co_ban = {"nen_tang": x["nen_tang"], "ten": x.get("ten") or "", "loai": loai or "khac",
              "chu_ky_ngay": chu_ky or 1, "so_bai_moi_lan": so_bai or 5}
    try:
        return NL.nguon({**co_ban, "dinh_danh": x["dinh_danh"]})
    except NL.LoiNhap:
        if not x.get("link"):
            raise
        return NL.nguon({**co_ban, "dinh_danh": x["link"]})


def ds_id(s, toi_da: int = DE_XUAT_HANG_LOAT_TOI_DA) -> list[int]:
    """"12,15 18" -> [12, 15, 18]: id số dương, bỏ trùng, giữ thứ tự; quá `toi_da` thì báo lỗi."""
    ra = list(dict.fromkeys(int(x) for x in re.findall(r"\d{1,18}", str(s or "")) if int(x) > 0))
    if len(ra) > toi_da:
        raise NL.LoiNhap(f"Mỗi lần xử lý tối đa {toi_da} đề xuất — lọc bớt rồi làm từng đợt.")
    return ra


# ───────────────────────────── tiện ích yêu cầu ─────────────────────────────
async def _k(fn, *a, **kw):
    """Kho dùng psycopg đồng bộ: chạy trong threadpool để không chặn vòng sự kiện."""
    return await run_in_threadpool(fn, *a, **kw)


def _bay_gio() -> datetime.datetime:
    """Giờ VN hiện tại (một chỗ để bộ thử cố định thời điểm dự báo chi phí)."""
    return datetime.datetime.now(VN)


def _hom_nay() -> datetime.date:
    return datetime.datetime.now(VN).date()


def _doc_khoang(q) -> tuple[datetime.date, datetime.date]:
    """Khoảng ngày của bộ lọc. Mặc định 30 ngày TRỌN tới hết hôm qua (giờ VN): so với kỳ trước
    là so ngày trọn với ngày trọn — có hôm nay (chưa hết ngày) thì kỳ này luôn thấp giả."""
    hom_qua = _hom_nay() - datetime.timedelta(days=1)
    den = NL.ngay(q.get("den"), hom_qua)
    return NL.ngay(q.get("tu"), den - datetime.timedelta(days=29)), den


def _url(duong: str, **q) -> str:
    """Giá trị danh sách (vd nhiều `tk`, 22/10/2026) thành tham số lặp lại; rỗng / None bỏ."""
    q = {k: v for k, v in q.items() if v not in (None, "")}
    return duong + ("?" + urlencode(q, doseq=True) if q else "")


def _la_api(request: Request) -> bool:
    p = request.url.path
    return p.startswith(("/api/", "/noi-bo/")) or p == "/su-kien"


#: Câu chặn khi người dùng xem được dự án nhưng không sửa được (Chỉ xem ở bên đó).
CAM_BEN = ("Chỉ quản trị viên hoặc quản lý của bên sở hữu dự án này mới được sửa. Bạn đang có "
           "quyền chỉ xem ở bên này.")


def _dung_nguoi(email: str, q: dict, csrf: str = "", het: float = 0.0) -> dict:
    """Người đang đăng nhập. `q` = quyền theo bên (`phan_quyen`); `vai_tro` = vai trò GỘP (đầu trang,
    menu) — trang của MỘT dự án dùng `_theo_du_an` để vai_tro là quyền ở ĐÚNG dự án đó."""
    vai = PQ.vai_chung(q)
    return {"email": email, "vai_tro": vai, "csrf": csrf, "het": het, "q": q,
            "la_quan_tri": PQ.la_quan_tri(q), "co_quan_ly": vai == "quan_ly",
            "nhan_vai": PQ.nhan_vai(q)}


def _theo_du_an(nguoi: dict, du_an: dict | None) -> dict:
    """Bản `nguoi` cho trang của một dự án: vai_tro = quan_ly chỉ khi sửa được dự án này
    (template ẩn nút, `an_chi_tiet` che email + lỗi thô theo đúng quyền ở bên của dự án)."""
    return {**nguoi, "vai_tro": "quan_ly" if PQ.sua_duoc(nguoi["q"], du_an) else "xem"}


async def _nguoi(request: Request) -> dict:
    cfg = request.app.state.cau_hinh
    phien = DN.doc_phien(request.cookies.get(DN.COOKIE_PHIEN), cfg.khoa_phien)
    if not phien:
        raise _ChuaDangNhap()
    q = PQ.chuan(await _k(request.app.state.kho.quyen_cua, phien["email"]))
    if not PQ.co_quyen(q):
        raise _Cam(f"Bạn chưa có quyền xem — nhờ người quản lý thêm email {phien['email']}.")
    nguoi = _dung_nguoi(phien["email"], q, phien["csrf"], phien["het"])
    nguoi["co_qc"] = await _co_qc(request.app, q)
    return nguoi


async def _co_qc(app: FastAPI, q: dict) -> bool:
    """Mục "Quảng cáo TikTok" trên menu + trang + /api/qc: từ 20/10/2026 CHỈ quản trị viên
    (`quang_cao.thay_trang_qc`; người khác hỏi Mark, trả lời bằng chữ). Bên có tài khoản nhớ
    `NHO_BEN_QC_GIAY`; kho quảng cáo chưa dùng được (chưa chạy schema.sql) = không có."""
    if PQ.la_quan_tri(q):
        return True
    luc, ben = app.state.nho_ben_qc
    if time.monotonic() - luc >= NHO_BEN_QC_GIAY:
        try:
            ben = set(await _k(app.state.kho_qc.ben_co_tk))
        except Exception as e:  # noqa: BLE001 — chỉ là mục menu
            log.warning("đọc bên có tài khoản quảng cáo lỗi: %s", type(e).__name__)
            ben = set()
        app.state.nho_ben_qc = (time.monotonic(), ben)
    return QC.thay_trang_qc(q, ben)


class KhoQcRong:
    """Kho quảng cáo rỗng: bộ thử cũ truyền `kho` giả mà không truyền `kho_qc` — trang vẫn chạy
    như chưa kết nối TikTok, không bao giờ chạm Postgres thật."""

    def doc_ket_noi(self, ncc: str = TA.NCC):
        return None

    def cac_tk(self):
        return []

    def ben_co_tk(self):
        return set()

    def dang_dong_bo(self, *a):
        return False

    def __getattr__(self, ten: str):
        def chua_co(*a, **kw):
            raise LoiKho("chưa có kho quảng cáo")
        return chua_co


class KhoSheetRong:
    """Kho yêu cầu Sheet rỗng (bộ thử cũ truyền `kho` giả): chưa có yêu cầu nào, tạo thì báo kho
    chưa dùng được — không bao giờ chạm Postgres thật."""

    def gan_day(self, *a, **kw):
        return []

    def tao(self, *a, **kw):
        raise LoiKho("chưa có kho yêu cầu Sheet")


class _Form(dict):
    """Biểu mẫu: dict giá trị CUỐI của mỗi tên (như cũ) + `getlist` cho tên lặp lại (nhiều `tk` của
    "Xuất Lark Sheet", 22/10/2026)."""

    def __init__(self, q: dict[str, list[str]]):
        super().__init__({k: v[-1] for k, v in q.items()})
        self._ds = q

    def getlist(self, k: str) -> list[str]:
        return list(self._ds.get(k, ()))


async def _doc_form(request: Request) -> _Form:
    """Biểu mẫu urlencoded (dashboard không nhận tệp) — tự đọc để khỏi cần python-multipart.
    Tối đa 260 trường: đủ 200 tài khoản (QC.TK_TOI_DA) + các trường khác của form Sheet."""
    if not request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        raise _Cam("Biểu mẫu không hợp lệ.", 415)
    body = await request.body()
    if len(body) > 64_000:
        raise _Cam("Biểu mẫu quá lớn.", 413)
    try:
        q = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=260)
    except (UnicodeDecodeError, ValueError):
        raise _Cam("Biểu mẫu không hợp lệ.", 400) from None
    return _Form(q)


def _cung_nguon_goc(request: Request) -> bool:
    """Lớp chặn CSRF thứ hai: trình duyệt gửi Origin với POST; có thì phải là chính trang."""
    o = request.headers.get("origin")
    if not o or o == "null":
        return o is None
    base = urlsplit(request.app.state.cau_hinh.base_url)
    u = urlsplit(o)
    return (u.scheme, u.netloc) == (base.scheme, base.netloc)


async def _sua(request: Request, *, can_quan_ly: bool = True) -> tuple[dict, dict]:
    """Chốt chặn của MỌI POST: phiên -> nguồn gốc -> CSRF -> có quyền quản lý ở ÍT NHẤT một bên.
    -> (người, biểu mẫu). Quyền ở ĐÚNG dự án / bên của thao tác: mỗi đường tự kiểm tiếp
    (`_du_an_sua`, `_thuoc_du_an_sua`, trang Người xem theo `phan_quyen`)."""
    nguoi = await _nguoi(request)
    if not _cung_nguon_goc(request):
        raise _Cam("Yêu cầu không đến từ trang dashboard.")
    form = await _doc_form(request)
    if not DN.csrf_dung(nguoi, form.get("csrf")):
        raise _Cam("Biểu mẫu đã hết hạn hoặc không hợp lệ — tải lại trang rồi thử lại.")
    if can_quan_ly and not nguoi["co_quan_ly"]:
        raise _Cam("Chỉ người quản lý mới được sửa. Bạn đang có quyền chỉ xem.")
    return nguoi, form


def _dat_cookie(request: Request, resp, ten: str, gia_tri: str, tuoi: int, duong: str = "/"):
    resp.set_cookie(ten, gia_tri, max_age=tuoi, path=duong, httponly=True, samesite="lax",
                    secure=request.app.state.cau_hinh.cookie_secure)


def _chuyen(request: Request, duong: str, loai: str, noi_dung: str) -> RedirectResponse:
    """Chuyển về trang (303) kèm thông báo một lần, ký HMAC — không đọc chữ thông báo từ URL
    (khỏi bị dựng link hiện thông báo giả)."""
    r = RedirectResponse(NL.duong_an_toan(duong), status_code=303)
    tb = DN.ky({"loai": loai, "nd": str(noi_dung)[:300], "het": time.time() + 120},
               request.app.state.cau_hinh.khoa_phien, "thong_bao")
    _dat_cookie(request, r, DN.COOKIE_THONG_BAO, tb, 120)
    return r


def _trang(request: Request, ten: str, nguoi: dict | None, trang_hien: str = "",
           ma: int = 200, **ctx):
    cfg = request.app.state.cau_hinh
    tb = DN.mo(request.cookies.get(DN.COOKIE_THONG_BAO), cfg.khoa_phien, "thong_bao")
    r = request.app.state.mau.TemplateResponse(
        request, ten, {"nguoi": nguoi, "tb": tb, "trang_hien": trang_hien, **ctx},
        status_code=ma)
    if request.cookies.get(DN.COOKIE_THONG_BAO):
        r.delete_cookie(DN.COOKIE_THONG_BAO, path="/", secure=cfg.cookie_secure, httponly=True,
                        samesite="lax")
    return r


def _chon_du_an(ds: list[dict], ma: str | None) -> dict | None:
    if ma:
        return next((d for d in ds if d["ma"] == ma), None)
    return next((d for d in ds if d.get("dang_bat")), ds[0] if ds else None)


def _so_trang(s, mac_dinh: int = 1) -> int:
    try:
        return min(max(1, int(str(s or mac_dinh))), 10_000)
    except ValueError:
        return mac_dinh


def _luot_json(r: dict | None) -> dict | None:
    if not r:
        return None
    return {"id": r.get("id"), "trang_thai": r.get("trang_thai"),
            "bat_dau": gio_vn(r.get("bat_dau")), "ket_thuc": gio_vn(r.get("ket_thuc"))}


def _chay_dong_bo_nen(chay) -> threading.Thread:
    def chay_an_toan():
        try:
            chay()
        except Exception as e:  # noqa: BLE001
            log.warning("đồng bộ BigQuery lỗi: %s", type(e).__name__)
    t = threading.Thread(target=chay_an_toan, name="dong_bo_bq_tay", daemon=True)
    t.start()
    return t


# ───────────────────────────── danh bạ Lark (trang Người xem) ─────────────────────────────
_MAU_TRANG_THAI = {"hoat_dong": "tot", "chua_kich_hoat": "canh", "tam_khoa": "canh",
                   "nghi_viec": "loi", "khong_co": "loi"}
_GOI_Y_TRANG_THAI = {
    "hoat_dong": "Tài khoản Lark của công ty đang hoạt động.",
    "chua_kich_hoat": "Tài khoản Lark đã tạo nhưng chưa kích hoạt — người này chưa đăng nhập "
                      "được dashboard.",
    "tam_khoa": "Tài khoản Lark đang bị tạm khoá — người này không đăng nhập được.",
    "nghi_viec": "Tài khoản đã rời tổ chức Lark — nên xoá khỏi danh sách người xem.",
    "khong_co": "Không tìm thấy email này trong danh bạ Lark công ty (sai chính tả, email cá "
                "nhân, hoặc ngoài phạm vi danh bạ app được xem) — người này không đăng nhập được.",
}
GOI_Y_CHUA_DANG_NHAP = (
    " Người này chưa đăng nhập dashboard lần nào: nếu email đúng là email công ty, nhờ họ đăng "
    "nhập một lần — dashboard lưu mã tài khoản Lark và tự nhận diện lại.")
GOI_Y_THIEU_QUYEN = (
    "App Lark của dashboard chưa được cấp quyền đọc danh bạ. Cần bật trong Lark Developer → "
    "Permissions & Scopes (quyền ứng dụng): contact:user.id:readonly, contact:user.base:readonly, "
    "contact:user.employee:readonly (chức danh), contact:user.department:readonly, "
    "contact:department.base:readonly; phạm vi danh bạ = toàn công ty; phát hành phiên bản mới. "
    "Dashboard tự thử lại mỗi giờ.")
GOI_Y_LOI_DANH_BA = "Lark lỗi hoặc quá thời gian khi đọc danh bạ — dashboard tự thử lại sau 1 giờ."


def _can_doc_danh_ba(ds: list[dict], bay_gio: datetime.datetime) -> list[str]:
    """Email cần đọc lại danh bạ: chưa đọc, đọc được đã cũ hơn 12 giờ, lỗi đã quá 1 giờ."""
    ra = []
    for x in ds:
        luc = x.get("danh_ba_luc")
        if not isinstance(luc, datetime.datetime):
            ra.append(x["email"])
            continue
        if luc.tzinfo is None:
            luc = luc.replace(tzinfo=datetime.UTC)
        song = DANH_BA_LOI_GIAY if x.get("danh_ba_loi") else DANH_BA_GIAY
        if (bay_gio - luc).total_seconds() >= song:
            ra.append(x["email"])
    return ra


def _o_danh_ba(x: dict, dang_doc: bool) -> dict:
    """Một dòng `nguoi_xem` -> ô Trạng thái: chữ, màu nhãn, câu ⓘ, ⓘ cảnh báo hay không."""
    tt, loi = x.get("trang_thai_lark"), x.get("danh_ba_loi")
    if tt in DB.TRANG_THAI:
        goi_y = _GOI_Y_TRANG_THAI[tt]
        if tt == "khong_co" and not x.get("lark_open_id"):
            goi_y += GOI_Y_CHUA_DANG_NHAP
        if loi:
            goi_y += " Lần đọc danh bạ gần nhất lỗi — đây là dữ liệu của lần đọc được trước đó."
        return {"chu": DB.TRANG_THAI[tt], "mau": _MAU_TRANG_THAI[tt], "goi_y": goi_y,
                "canh": bool(loi) or tt != "hoat_dong"}
    if loi:
        return {"chu": "Chưa đọc được danh bạ", "mau": "", "canh": True,
                "goi_y": GOI_Y_THIEU_QUYEN if loi == "thieu_quyen" else GOI_Y_LOI_DANH_BA}
    return {"chu": "Đang đọc danh bạ…" if dang_doc else "Chưa đọc danh bạ", "mau": "",
            "canh": False, "goi_y": "Dashboard đang đọc danh bạ Lark — tải lại trang sau vài giây."}


async def doc_danh_ba(app: FastAPI, emails: list[str], giay: float,
                      open_id_cua: dict[str, str] | None = None,
                      quet: bool = True) -> dict[str, dict] | None:
    """Đọc danh bạ cho `emails` (đợi tối đa `giay`) rồi ghi bản đệm. Hỏng thì ghi dấu lỗi vào
    từng dòng (để 1 giờ sau mới thử lại) và trả None — KHÔNG ném lỗi ra ngoài.
    `open_id_cua`: open_id đã lưu lúc đăng nhập (tra thẳng). `quet=False` (đường thêm email, cần
    nhanh): không dò cả danh bạ, và KHÔNG ghi "khong_co" — để lượt đọc nền (có dò) quyết định."""
    loai = "loi"
    try:
        kq = await asyncio.wait_for(
            app.state.danh_ba.tra_cuu(emails, open_id_cua=open_id_cua, quet=quet), giay)
    except DB.LoiDanhBa as e:
        log.warning("đọc danh bạ Lark lỗi: %s", e)
        loai = e.loai
    except TimeoutError:
        log.warning("đọc danh bạ Lark quá %ss", giay)
    except Exception as e:  # noqa: BLE001 — danh bạ chỉ là thông tin thêm
        log.warning("đọc danh bạ Lark lỗi: %s", type(e).__name__)
    else:
        ghi = kq if quet else {e: d for e, d in kq.items() if d.get("trang_thai") != "khong_co"}
        try:
            await run_in_threadpool(app.state.kho.ghi_danh_ba, ghi)
        except (LoiKho, LoiDuLieu) as e:
            log.warning("không ghi được danh bạ: %s", type(e).__name__)
        return kq
    try:
        await run_in_threadpool(app.state.kho.ghi_loi_danh_ba, emails, loai)
    except (LoiKho, LoiDuLieu) as e:
        log.warning("không ghi được lỗi danh bạ: %s", type(e).__name__)
    return None


async def doc_danh_ba_nen(app: FastAPI, emails: list[str],
                          open_id_cua: dict[str, str] | None = None) -> None:
    """Chạy SAU khi trang đã trả (BackgroundTask). Mốc `danh_ba_doc_tu` đặt lúc lên lịch; việc
    nền không chạy được (trình duyệt ngắt trước) thì mốc tự hết hạn, không kẹt mãi."""
    try:
        await doc_danh_ba(app, emails, DANH_BA_NEN_GIAY, open_id_cua)
    finally:
        app.state.danh_ba_doc_tu = float("-inf")


def _dang_doc_danh_ba(app: FastAPI) -> bool:
    return time.monotonic() - app.state.danh_ba_doc_tu < DANH_BA_NEN_GIAY + 10


# ───────────────────────────── nhà máy ứng dụng ─────────────────────────────
def tao_app(kho=None, *, cau_hinh: DN.CauHinh | None = None, lark=None, dong_bo=None,
            danh_ba=None, kho_qc=None, tiktok=None, meta=None, kho_sheet=None,
            chu_ky_kiem: float | None = CHU_KY_KIEM,
            sse_toi_da_su_kien: int | None = None,
            sse_kiem_quyen_giay: float = SSE_KIEM_QUYEN_GIAY) -> FastAPI:
    """Dựng ứng dụng. Mặc định (uvicorn --factory): kho Postgres thật, cấu hình từ env, Lark
    thật, đồng bộ BigQuery thật (`dong_bo_bq`, tự tắt khi thiếu BQ_DATASET), vòng kiểm 30 giây.

    Bộ thử truyền `kho` giả, `cau_hinh`, `lark` (LarkOAuth với httpx.MockTransport), `dong_bo`
    giả (trang_thai/chay/cai_vao không mở luồng), `chu_ky_kiem=None` (không vòng kiểm),
    `sse_toi_da_su_kien` (luồng SSE tự đóng sau N sự kiện) và `sse_kiem_quyen_giay`;
    `danh_ba` = DanhBaLark với httpx.MockTransport (mặc định: danh bạ Lark thật, cùng app).
    TikTok Ads (19/10/2026): `kho_qc` (mặc định `dashboard.kho_qc` khi kho thật, `KhoQcRong` khi bộ
    thử truyền kho giả) và `tiktok` (`tiktok_ads.DichVu` — bộ thử truyền bản có HTTP giả). Meta Ads
    (20/10/2026): `meta` (`meta_ads.DichVu`, cùng `kho_qc`). Xuất Lark Sheet (20/10/2026): `kho_sheet`
    (mặc định `dashboard.kho_sheet_qc` khi kho thật, `KhoSheetRong` khi bộ thử truyền kho giả)."""
    if kho_sheet is None:
        if kho is None:
            from dashboard import kho_sheet_qc as kho_sheet
        else:
            kho_sheet = KhoSheetRong()
    if kho_qc is None:
        if kho is None:
            from dashboard import kho_qc as kho_qc_pg
            kho_qc = kho_qc_pg
        else:
            kho_qc = KhoQcRong()
    if kho is None:
        from dashboard import kho as kho_pg
        kho = kho_pg
    tiktok = tiktok or TA.DichVu(kho_qc)
    meta = meta or MA.DichVu(kho_qc)
    cau_hinh = cau_hinh or DN.CauHinh.tu_env()
    lark = lark or DN.LarkOAuth(cau_hinh)
    danh_ba = danh_ba or DB.DanhBaLark(cau_hinh)
    if dong_bo is None:
        from dashboard import dong_bo_bq
        dong_bo = dong_bo_bq

    @contextlib.asynccontextmanager
    async def vong_doi(app: FastAPI):
        viec = asyncio.create_task(_vong_kiem(app, chu_ky_kiem)) if chu_ky_kiem else None
        try:
            yield
        finally:
            if viec:
                viec.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await viec

    app = FastAPI(title="Social Listening — HAPAS", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=vong_doi)
    app.state.kho = kho
    app.state.cau_hinh = cau_hinh
    app.state.lark = lark
    app.state.dong_bo = dong_bo
    app.state.danh_ba = danh_ba
    app.state.danh_ba_doc_tu = float("-inf")
    app.state.danh_ba_ds = (float("-inf"), [], "")
    app.state.khoa_danh_ba_ds = asyncio.Lock()
    app.state.kho_qc = kho_qc
    app.state.tiktok = tiktok
    app.state.meta = meta
    app.state.kho_sheet = kho_sheet
    app.state.nho_ben_qc = (float("-inf"), set())
    app.state.mau = _tao_mau()
    app.state.bang_tin = BangTin()
    app.state.moc_luot = _CHUA_KIEM
    app.state.luot_da_bao = collections.deque(maxlen=200)
    app.state.viec_nen = set()
    app.state.sse_toi_da_su_kien = sse_toi_da_su_kien
    app.state.sse_kiem_quyen_giay = sse_kiem_quyen_giay
    # /api/chi-so: tối đa TINH_SONG_SONG lượt đọc + tính cùng lúc (quá thì 503, không xếp hàng
    # — người xem bấm liên tục khoảng 400 ngày không làm cạn bộ nhớ dịch vụ) + bộ nhớ đệm ngắn.
    app.state.ban = threading.Semaphore(TINH_SONG_SONG)
    # Dòng thô (bài, bình luận) + bài gốc thiếu: MỘT ngân sách dòng chung (xem `NhoDong`).
    app.state.nho_dong = NhoDong(NHO_DONG_TOI_DA_DONG, NHO_CHI_SO_GIAY)
    app.state.nho_chi_so = collections.OrderedDict()
    app.state.nho_suc_khoe = (0.0, False)
    # Hook sau mỗi `cap-nhat`: danh sách hàm (du_an, luot), chạy NỀN sau khi đã đẩy sự kiện
    # xuống trình duyệt (xem `chay_hook`). Đồng bộ BigQuery tự đăng ký vào đây qua
    # `dong_bo_bq.cai_vao(app)` ngay dưới; muốn thêm việc sau mỗi lượt quét thì append vào.
    app.state.sau_cap_nhat = []
    cai_vao = getattr(dong_bo, "cai_vao", None)
    if callable(cai_vao):
        cai_vao(app)          # không làm gì khi thiếu BQ_DATASET; bộ thử truyền bản giả
    app.add_middleware(_TieuDeAnToan, hsts=cau_hinh.cookie_secure)
    app.mount("/tinh", StaticFiles(directory=str(THU_MUC / "static")), name="tinh")

    # ─── xử lý lỗi chung ───
    @app.exception_handler(_ChuaDangNhap)
    async def _xl_chua_dang_nhap(request: Request, exc: _ChuaDangNhap):
        if request.method == "GET" and not _la_api(request):
            sau = request.url.path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(_url("/dang-nhap", sau=sau), status_code=303)
        return JSONResponse({"loi": "Chưa đăng nhập hoặc phiên đã hết hạn."}, status_code=401)

    @app.exception_handler(_Cam)
    async def _xl_cam(request: Request, exc: _Cam):
        if _la_api(request):
            return JSONResponse({"loi": exc.thong_diep}, status_code=exc.ma)
        return _trang(request, "loi.html", None, ma=exc.ma, tieu_de="Không thực hiện được",
                      thong_diep=exc.thong_diep)

    @app.exception_handler(LoiKho)
    async def _xl_kho(request: Request, exc: LoiKho):
        log.warning("kho lỗi: %s", exc)       # LoiKho không bao giờ chứa DSN
        tin = "Kho dữ liệu tạm thời chưa dùng được — thử lại sau ít phút."
        if _la_api(request):
            return JSONResponse({"loi": tin}, status_code=503)
        return _trang(request, "loi.html", None, ma=503, tieu_de="Kho dữ liệu", thong_diep=tin)

    # ─── công khai ───
    @app.get("/suc-khoe")
    async def suc_khoe():
        # Công khai nên KHÔNG mở kết nối DB mỗi lần gọi: kết quả kiểm giữ SUC_KHOE_GIAY giây.
        luc, db = app.state.nho_suc_khoe
        if time.monotonic() - luc >= SUC_KHOE_GIAY:
            try:
                db = bool(await _k(app.state.kho.kiem_tra))
            except Exception:  # noqa: BLE001 — chỉ báo có/không, không lộ chi tiết
                db = False
            app.state.nho_suc_khoe = (time.monotonic(), db)
        return {"ok": True, "db": db}

    @app.get("/dang-nhap")
    async def dang_nhap(request: Request):
        sau = NL.duong_an_toan(request.query_params.get("sau"))
        return _trang(request, "dang_nhap.html", None, sau=sau)

    @app.get("/dang-nhap/lark")
    async def dang_nhap_lark(request: Request):
        sau = NL.duong_an_toan(request.query_params.get("sau"))
        state, nonce = DN.tao_state(cau_hinh.khoa_phien, sau)
        r = RedirectResponse(DN.url_uy_quyen(cau_hinh, state), status_code=302)
        _dat_cookie(request, r, DN.COOKIE_NONCE, nonce, DN.STATE_GIAY, "/dang-nhap")
        return r

    @app.get("/dang-nhap/xong")
    async def dang_nhap_xong(request: Request):
        q = request.query_params

        def loi(tin: str, ma: int):
            r = _trang(request, "loi.html", None, ma=ma, tieu_de="Đăng nhập", thong_diep=tin,
                       dang_nhap_lai=True)
            r.delete_cookie(DN.COOKIE_NONCE, path="/dang-nhap")
            return r
        if q.get("error"):
            return loi("Bạn chưa đồng ý cho dashboard đọc thông tin tài khoản Lark.", 400)
        st = DN.doc_state(q.get("state"), request.cookies.get(DN.COOKIE_NONCE),
                          cau_hinh.khoa_phien)
        if not st:
            return loi("Lượt đăng nhập không hợp lệ hoặc đã quá 10 phút — bấm đăng nhập lại.", 400)
        code = q.get("code") or ""
        if not code or len(code) > 2000:
            return loi("Lark không trả mã đăng nhập — bấm đăng nhập lại.", 400)
        try:
            nd = await app.state.lark.lay_nguoi_dung(code)
        except DN.LoiDangNhap as e:
            log.warning("đăng nhập Lark lỗi: %s", e)
            return loi("Không đăng nhập được bằng Lark lúc này — thử lại sau ít phút.", 502)
        # Tổ chức trước, email sau: tài khoản Lark của tổ chức khác tự khai email bất kỳ được.
        if not DN.cung_to_chuc(cau_hinh, nd.get("tenant_key") or ""):
            # tenant_key không phải bí mật: ghi log để người cài tra được khoá đúng của HAPAS.
            log.warning("đăng nhập bị chặn: tenant_key %r không phải DASH_LARK_TENANT_KEY",
                        str(nd.get("tenant_key") or "")[:64])
            return loi("Tài khoản Lark này không thuộc tổ chức HAPAS — đăng nhập bằng tài khoản "
                       "Lark công ty.", 403)
        email = nd.get("email") or ""
        if not email:
            return loi("Tài khoản Lark này không cho đọc email — nhờ người quản lý kiểm quyền "
                       "đọc email của ứng dụng dashboard.", 403)
        if not PQ.co_quyen(PQ.chuan(await _k(app.state.kho.quyen_cua, email))):
            return loi(f"Bạn chưa có quyền xem — nhờ người quản lý thêm email {email}.", 403)
        try:
            await _k(app.state.kho.ghi_dang_nhap, email, nd.get("open_id") or "",
                     nd.get("union_id") or "", nd.get("user_id") or "")
        except (LoiKho, LoiDuLieu) as e:   # chỉ là nhật ký — không chặn đăng nhập
            log.warning("không ghi được lượt đăng nhập: %s", type(e).__name__)
        r = RedirectResponse(NL.duong_an_toan(st.get("sau")), status_code=303)
        _dat_cookie(request, r, DN.COOKIE_PHIEN, DN.tao_phien(email, cau_hinh.khoa_phien),
                    DN.PHIEN_GIAY)
        r.delete_cookie(DN.COOKIE_NONCE, path="/dang-nhap")
        return r

    @app.post("/dang-xuat")
    async def dang_xuat(request: Request):
        await _sua(request, can_quan_ly=False)
        r = RedirectResponse("/dang-nhap", status_code=303)
        r.delete_cookie(DN.COOKIE_PHIEN, path="/", secure=cau_hinh.cookie_secure, httponly=True,
                        samesite="lax")
        return r

    # ─── phạm vi theo bên (19/10/2026) ───
    async def _ds_doc(nguoi: dict) -> list[dict]:
        """Dự án người này ĐỌC được (quản trị viên: tất cả) — mọi trang chọn dự án từ đây."""
        return PQ.loc_du_an(nguoi["q"], await _k(app.state.kho.cac_du_an))

    async def _du_an_doc(nguoi: dict, ma: str) -> dict | None:
        """Dự án `ma` nếu có VÀ người này đọc được; ngoài phạm vi trả None như không có (không lộ
        dự án của bên khác có tồn tại hay không)."""
        d = await _k(app.state.kho.doc_du_an, ma) if ma else None
        return d if PQ.doc_duoc(nguoi["q"], d) else None

    async def _du_an_sua(nguoi: dict, ma: str) -> dict:
        """Dự án `ma` để SỬA: không có / ngoài phạm vi -> NL.LoiNhap "Không có dự án này." (chuyển
        về trang kèm lỗi như trước); xem được mà không sửa được -> 403."""
        d = await _du_an_doc(nguoi, ma)
        if not d:
            raise NL.LoiNhap("Không có dự án này.")
        if not PQ.sua_duoc(nguoi["q"], d):
            raise _Cam(CAM_BEN)
        return d

    async def _thuoc_du_an_sua(nguoi: dict, ma: str, khong_co: str) -> dict:
        """Nguồn / đề xuất / lịch: dự án của nó (đọc từ KHO) phải sửa được. Ngoài phạm vi = 404
        như không có."""
        d = await _du_an_doc(nguoi, ma)
        if not d:
            raise _Cam(khong_co, 404)
        if not PQ.sua_duoc(nguoi["q"], d):
            raise _Cam(CAM_BEN)
        return d

    async def _cac_don_vi() -> list[dict]:
        ham = getattr(app.state.kho, "cac_don_vi", None)
        return list(await _k(ham)) if ham else []

    # ─── chỉ số ───
    @app.get("/")
    async def trang_chi_so(request: Request):
        nguoi = await _nguoi(request)
        ds = await _ds_doc(nguoi)
        q = request.query_params
        du_an = _chon_du_an(ds, q.get("du_an"))
        loi = ""
        try:
            tu, den = _doc_khoang(q)
        except NL.LoiNhap as e:
            loi = str(e) + " Đang hiện 30 ngày trọn gần nhất."
            tu, den = _doc_khoang({})
        try:
            bo_loc = CS.doc_bo_loc(q)
        except CS.LoiBoLoc as e:
            loi = (loi + " " if loi else "") + str(e) + " Đã bỏ bộ lọc."
            bo_loc = CS.doc_bo_loc({})
        mac_dinh = _doc_khoang({})
        hom_nay = _hom_nay()
        # Thanh lọc chung (đợt 2f): trạng thái đầu + nhãn + bộ lọc nhanh — JS đọc qua JSON nhúng.
        loc = {"du_an": du_an["ma"] if du_an else "", "tu": tu.isoformat(),
               "den": den.isoformat(), "bo_loc": CS.bo_loc_json(bo_loc),
               "mac_dinh": {"tu": mac_dinh[0].isoformat(), "den": mac_dinh[1].isoformat()},
               "hom_nay": hom_nay.isoformat(), "toi_da_ngay": KHOANG_TOI_DA_NGAY,
               "nhan": CS.NHAN_BO_LOC, "nhanh": list(CS.BO_LOC_NHANH)}
        return _trang(request, "chi_so.html", nguoi, "chi_so", du_an_ds=ds, du_an=du_an,
                      loc=loc, loi_loc=loi, chua_tron=den >= hom_nay)

    # ─── đồng bộ quảng cáo: dải trạng thái + "Đồng bộ ngay" cho mọi người có quyền (20/10/2026) ───
    def _dv_qc() -> dict:
        return {"tiktok": app.state.tiktok, "meta": app.state.meta}

    async def _the_qc(nen: str) -> dict | None:
        try:
            return await _k(_dv_qc()[nen].the)
        except Exception as e:  # noqa: BLE001 — kho quảng cáo chưa dùng được: không có dải
            log.warning("đọc trạng thái đồng bộ %s lỗi: %s", nen, type(e).__name__)
            return None

    def _bay_dv(nen: str) -> datetime.datetime:
        """Đồng hồ của dịch vụ đồng bộ (khung 06:25–07:30; 00:00–07:30 của lượt 90 ngày) — bộ thử
        đặt giờ giả."""
        f = getattr(_dv_qc()[nen], "_bay_gio", None)
        return f() if callable(f) else datetime.datetime.now(datetime.timezone.utc)

    async def _dai_qc(la_quan_tri: bool = False) -> list[dict]:
        """Điều khiển đồng bộ (trang Quảng cáo, thiết kế lại 20/10/2026): mỗi nền tảng một dòng —
        tên đầy đủ, một câu trạng thái, lý do khoá từng nút; chi tiết phụ để gập. KHÔNG tiền, không
        số liệu. Nền tảng chưa kết nối vẫn có dòng ("Chưa kết nối") để biết vì sao không bấm được."""
        bay = datetime.datetime.now(datetime.timezone.utc)
        ra = []
        for nen in QC.NEN_TANG_QC:
            t = await _the_qc(nen)
            if t is not None:
                ra.append(QC.dong_dieu_khien(t, nen, bay, hien_ai=la_quan_tri,
                                             la_quan_tri=la_quan_tri, bay_dv=_bay_dv(nen)))
        return ra if any(x["co_token"] for x in ra) else []

    #: `ncc` của biểu mẫu → nền tảng (ca_hai = cả hai). `nen_tang` (bản trước) vẫn nhận.
    _NCC_FORM = {"tiktok_ads": ("tiktok",), "meta_ads": ("meta",), "ca_hai": QC.NEN_TANG_QC,
                 "tiktok": ("tiktok",), "meta": ("meta",), "tat_ca": QC.NEN_TANG_QC}

    @app.post("/quang-cao/dong-bo")
    async def quang_cao_dong_bo(request: Request):
        """Đồng bộ bấm tay — CHỈ ghi cờ yêu cầu, bộ hẹn giờ 2 phút / bộ nghe chạy lượt; dashboard
        không bao giờ chạy đồng bộ. `ncc` = tiktok_ads | meta_ads | ca_hai; `kieu`:
          • nhanh (mặc định) — hôm nay + 2 ngày trước; mọi người có quyền ở ≥ 1 bên (như nút BigQuery),
            giãn 15 phút sau lượt nhanh trước;
          • day_du — "Đồng bộ lại 90 ngày": xoá mốc nạp lùi (`kho_qc.nap_lai`) rồi ghi cờ đầy đủ —
            CHỈ quản trị viên (kiểm ở máy chủ).
        Cả hai: không khi đang chạy / đang có yêu cầu / chưa kết nối / trong khung 06:25–07:30."""
        nguoi, form = await _sua(request, can_quan_ly=False)
        if not PQ.co_quyen(nguoi["q"]):
            raise _Cam("Bạn chưa có quyền ở bên nào.")
        ve = NL.duong_an_toan(str(form.get("ve") or "/"))
        ma = str(form.get("ncc") or form.get("nen_tang") or "ca_hai")
        kieu = str(form.get("kieu") or "nhanh")
        if ma not in _NCC_FORM or kieu not in QC.KIEU_DONG_BO:
            return _chuyen(request, ve, "loi", "Nền tảng hoặc kiểu đồng bộ không hợp lệ.")
        if kieu == "day_du" and not nguoi["la_quan_tri"]:
            raise _Cam("Chỉ quản trị viên được đồng bộ lại 90 ngày.")
        ca = len(_NCC_FORM[ma]) > 1
        bay = datetime.datetime.now(datetime.timezone.utc)
        ok, tu_choi = [], []
        for n in _NCC_FORM[ma]:
            ten = QC.TEN_DAY_DU[n]
            t = await _the_qc(n)
            if t is None:
                tu_choi.append(f"{ten}: chưa đọc được trạng thái")
                continue
            # Email người đã yêu cầu chỉ quản trị viên thấy; người khác chỉ thấy giờ.
            ly_do = QC.ly_do_khong_dong_bo(t, bay, kieu, hien_ai=nguoi["la_quan_tri"],
                                           la_quan_tri=nguoi["la_quan_tri"], bay_dv=_bay_dv(n))
            if ly_do:
                if ca and ly_do == "chưa kết nối":
                    continue
                tu_choi.append(f"{ten}: {ly_do}")
                continue
            try:
                if kieu == "day_du":
                    # MỘT giao dịch: xoá mốc nạp lùi + ghi cờ day_du + NOTIFY + một dòng nhật ký —
                    # hỏng thì không đổi gì (không có cảnh mốc đã xoá mà chưa có yêu cầu).
                    await _k(app.state.kho_qc.nap_lai, nguoi["email"], QC.NEN_NCC[n])
                else:
                    await _k(_dv_qc()[n].yeu_cau, nguoi["email"], kieu)
                    await _k(app.state.kho.ghi_nhat_ky, nguoi["email"], "dong_bo_qc",
                             f"quang_cao:{n}", {"kieu": "bam_tay", "cua_so": kieu})
                ok.append(ten)
            except (LoiKho, LoiDuLieu) as e:
                log.warning("ghi yêu cầu đồng bộ %s lỗi: %s", n, type(e).__name__)
                tu_choi.append(f"{ten}: chưa ghi được yêu cầu")
        if ok:
            pham_vi = ("nạp lại 90 ngày, chạy nền — có thể mất vài giờ (Meta tới ~6 giờ)"
                       if kieu == "day_du" else "hôm nay + 2 ngày trước")
            tin = (f"Đã yêu cầu đồng bộ {', '.join(ok)} ({pham_vi}). {CHO_DONG_BO}"
                   + (f" Bỏ qua — {'; '.join(tu_choi)}." if tu_choi else ""))
            return _chuyen(request, ve, "ok", tin)
        return _chuyen(request, ve, "canh", "Chưa tạo yêu cầu mới — "
                       + ("; ".join(tu_choi) or "chưa kết nối nền tảng nào") + ".")

    async def _loc_api(request: Request):
        """Bộ lọc chung của các API số liệu. -> (dự án, từ, đến, bộ lọc `CS.doc_bo_loc`) hoặc
        JSONResponse lỗi (400 khi giá trị lọc sai; 404 khi không có dự án HOẶC dự án của bên người
        này không được xem — như nhau, không trả số)."""
        nguoi = await _nguoi(request)
        q = request.query_params
        du_an = await _du_an_doc(nguoi, q.get("du_an") or "")
        if not du_an:
            return JSONResponse({"loi": "Không có dự án này."}, status_code=404)
        try:
            tu, den = _doc_khoang(q)
        except NL.LoiNhap as e:
            return JSONResponse({"loi": str(e)}, status_code=400)
        if tu > den:
            return JSONResponse({"loi": "Ngày bắt đầu phải trước ngày kết thúc."}, status_code=400)
        if (den - tu).days + 1 > KHOANG_TOI_DA_NGAY:
            return JSONResponse({"loi": f"Khoảng tối đa {KHOANG_TOI_DA_NGAY} ngày."},
                                status_code=400)
        try:
            bo_loc = CS.doc_bo_loc(q)
        except CS.LoiBoLoc as e:
            return JSONResponse({"loi": str(e)}, status_code=400)
        return du_an, tu, den, bo_loc

    def _moc_ngay(tu: datetime.date, den: datetime.date) -> tuple:
        return (datetime.datetime.combine(tu, datetime.time(0), VN),
                datetime.datetime.combine(den + datetime.timedelta(days=1), datetime.time(0), VN))

    async def _moc_luot() -> tuple:
        """Mốc lượt quét vừa xong — đọc MỘT lần mỗi yêu cầu, mọi khoá nhớ của yêu cầu dùng chung
        (dòng thô, bài gốc thiếu, kết quả /api/chi-so cùng một mốc)."""
        x = await _k(app.state.kho.luot_xong_moi_nhat) or {}
        return x.get("id"), str(x.get("ket_thuc"))

    async def _kq_nho(loai_dong: str, du_an: str, tu, den, moc: tuple, *,
                      da_giu: bool = False):
        """{rows, bi_cat} bài / bình luận của [tu, den] (CHƯA lọc), nhớ `NHO_CHI_SO_GIAY` giây
        theo mốc lượt quét `moc`: đổi bộ lọc, bấm liên tiếp nhiều cột, lật trang bình luận không
        đọc lại kho. Bài luôn đọc từ đầu KỲ TRƯỚC (`/api/chi-so` cần so sánh; khung chi tiết tự
        cắt về kỳ này) nên mọi API dùng chung một bộ dòng mỗi khoảng. `da_giu`: bên gọi đã giữ
        suất tính (`app.state.ban`). -> None khi máy chủ đang bận."""
        if loai_dong == "bai":
            tu = CS.khoang_truoc(tu, den)[0]
        khoa = (loai_dong, du_an, tu, den, *moc)
        nho = app.state.nho_dong
        x = nho.lay(khoa)
        if x is not None:
            return x
        if not da_giu and not app.state.ban.acquire(blocking=False):
            return None
        try:
            bd, kt = _moc_ngay(tu, den)
            fn = (app.state.kho.bai_trong_khoang if loai_dong == "bai"
                  else app.state.kho.binh_luan_trong_khoang)
            kq = await _k(fn, du_an, bd, kt)
            kq = {"rows": kq["rows"], "bi_cat": bool(kq["bi_cat"])}
        finally:
            if not da_giu:
                app.state.ban.release()
        nho.dat(khoa, kq, len(kq["rows"]))
        return kq

    async def _dong_nho(loai_dong: str, du_an: str, tu, den, moc: tuple):
        kq = await _kq_nho(loai_dong, du_an, tu, den, moc)
        return None if kq is None else kq["rows"]

    async def _bai_cho_bl(du_an: str, bai: list, bl: list, moc: tuple, co_chu: bool, *,
                          da_giu: bool = False):
        """Bài gốc theo khoá cho các bình luận, khi bộ lọc có điều kiện cấp bài mà dòng bình luận
        không mang (ảnh hưởng, tương tác, kiểu quét, nguồn tìm theo từ khoá, chữ tìm). Bài đã đọc
        của khoảng dùng lại; bài đăng TRƯỚC khoảng (bình luận mới dưới bài cũ) đọc thêm theo khoá
        — cột hẹp (nội dung + hashtag chỉ khi `co_chu`, tức đang lọc chữ). Nhớ theo CÙNG mốc
        `moc` với dòng đã đọc, gộp dần: lượt sau chỉ đọc khoá chưa từng đọc. -> None khi bận."""
        ds = CS.chi_muc_bai(bai)
        thieu = CS.khoa_bai_thieu(bl, ds)
        if not thieu:
            return ds
        nho = app.state.nho_dong
        khoa_nho = ("bai_thieu", du_an, *moc, co_chu)
        x = nho.lay(khoa_nho) or {"bai": {}, "khong_co": frozenset()}
        can = [k for k in thieu if k not in x["bai"] and k not in x["khong_co"]]
        if can:
            if not da_giu and not app.state.ban.acquire(blocking=False):
                return None
            try:
                them = await _k(app.state.kho.bai_theo_khoa, du_an, can, co_chu)
            finally:
                if not da_giu:
                    app.state.ban.release()
            moi = {**x["bai"], **CS.chi_muc_bai(them)}
            x = {"bai": moi, "khong_co": x["khong_co"] | (set(can) - set(moi))}
            nho.dat(khoa_nho, x, len(moi))
        ds.update((k, x["bai"][k]) for k in thieu if k in x["bai"])
        return ds

    def _dk_chi_tiet(q) -> dict:
        """Điều kiện RIÊNG của khung chi tiết bài (cột/điểm vừa bấm), AND với bộ lọc chung. Tên
        có tiền tố `ct_` để không trùng tham số của bộ lọc chung. Ném NL.LoiNhap khi rác."""
        dk: dict = {}
        for k in ("ngay_tu", "ngay_den"):
            if q.get(k):
                dk[k] = NL.ngay(q.get(k), _hom_nay())
        s = q.get("ct_sac_thai") or ""
        if s:
            if s not in (*CS.SAC_THAI, CS.CHUA, "kênh nhà"):
                raise NL.LoiNhap("Sắc thái không hợp lệ.")
            dk["sac_thai"] = s
        if q.get("ct_nen_tang"):
            # CS (mọi nền tảng có bài, gồm "web"), không phải NL (nền tảng theo dõi nguồn được)
            if q.get("ct_nen_tang") not in CS.TEN_NEN_TANG:
                raise NL.LoiNhap("Nền tảng không hợp lệ.")
            dk["nen_tang"] = q.get("ct_nen_tang")
        if q.get("ct_loai"):
            if q.get("ct_loai") not in CS.TEN_LOAI:
                raise NL.LoiNhap("Loại nguồn không hợp lệ.")
            dk["loai_nguon"] = q.get("ct_loai")
        for k, ra, dai in (("ct_chu_de", "chu_de", 100),
                           ("ct_nguon", "nguon", CS.NGUON_TOI_DA_KY_TU), ("cum", "cum", 100)):
            v = (q.get(k) or "").strip()
            if v:
                if len(v) > dai:
                    raise NL.LoiNhap("Điều kiện quá dài.")
                dk[ra] = v
        # ct_ngoai_nha=1: chỉ bài ngoài Internal channel (hàng "Sắc thái theo nền tảng").
        if q.get("ct_ngoai_nha"):
            if q.get("ct_ngoai_nha") != "1":
                raise NL.LoiNhap("Điều kiện ngoài Internal channel không hợp lệ.")
            dk["ngoai_nha"] = True
        return dk

    def _ban():
        return JSONResponse({"loi": "Máy chủ đang bận — thử lại sau ít giây."},
                            status_code=503, headers={"Retry-After": "5"})

    @app.get("/api/bai")
    async def api_bai(request: Request):
        x = await _loc_api(request)
        if isinstance(x, JSONResponse):
            return x
        du_an, tu, den, bo_loc = x
        q = request.query_params
        try:
            dk = _dk_chi_tiet(q)
        except NL.LoiNhap as e:
            return JSONResponse({"loi": str(e)}, status_code=400)
        rows = await _dong_nho("bai", du_an["ma"], tu, den, await _moc_luot())
        if rows is None:
            return _ban()
        kq = await _k(CS.chi_tiet_bai, rows, tu, den, trang=_so_trang(q.get("trang")),
                      bo_loc=bo_loc, **dk)
        return JSONResponse(kq)

    def _dk_bl(q) -> dict:
        """Điều kiện RIÊNG của luồng bình luận / khung chi tiết bình luận (hậu tố `_bl`), AND với
        bộ lọc chung. Ném NL.LoiNhap khi rác."""
        dk: dict = {}
        for k in ("ngay_tu", "ngay_den"):
            if q.get(k):
                dk[k] = NL.ngay(q.get(k), _hom_nay())
        s = q.get("sac_thai_bl") or ""
        if s:
            if s not in (*CS.SAC_BL, CS.CHUA):
                raise NL.LoiNhap("Sắc thái không hợp lệ.")
            dk["sac_thai"] = s
        if q.get("loai_bl"):
            if q.get("loai_bl") not in CS.LOAI_BL:
                raise NL.LoiNhap("Nhãn lọc không hợp lệ.")
            dk["loai"] = q.get("loai_bl")
        # cum_bl: cụm của ngăn Từ khoá (đếm như mây từ); bai_bl: một bài (khối Ý định mua).
        for k, ra, dai in (("q_bl", "q", 100), ("nguon_bl", "nguon", 300),
                           ("chu_de_bl", "chu_de", 100), ("cum_bl", "cum", 100),
                           ("bai_bl", "khoa_bai", 200)):
            v = (q.get(k) or "").strip()
            if len(v) > dai:
                raise NL.LoiNhap("Điều kiện quá dài.")
            if v:
                dk[ra] = v
        # "1" = mọi ý định mua; mã món (17/10/2026, `CS.SAN_PHAM`) = chỉ bình luận hỏi mua món đó.
        yd = q.get("y_dinh_bl") or ""
        if yd and yd not in CS.Y_DINH:
            raise NL.LoiNhap("Điều kiện ý định mua không hợp lệ.")
        if yd:
            dk["y_dinh"] = True if yd == "1" else yd
        sx = q.get("sap_xep") or "thich"
        if sx not in CS.SAP_XEP_BL:
            raise NL.LoiNhap("Cách sắp xếp không hợp lệ.")
        dk["sap_xep"] = sx
        if q.get("nen_tang_bl"):
            if q.get("nen_tang_bl") not in NL.NEN_TANG:
                raise NL.LoiNhap("Nền tảng không hợp lệ.")
            dk["nen_tang"] = q.get("nen_tang_bl")
        return dk

    @app.get("/api/binh-luan")
    async def api_binh_luan(request: Request):
        x = await _loc_api(request)
        if isinstance(x, JSONResponse):
            return x
        du_an, tu, den, bo_loc = x
        q = request.query_params
        khoa = (q.get("khoa") or "").strip()
        if khoa:
            # Chuỗi bình luận của MỘT bài (bài đã khớp bộ lọc mới được bấm): giữ đủ cả chuỗi —
            # lọc theo sắc thái/chữ ở đây làm đứt mạch trả lời.
            if len(khoa) > 200:
                return JSONResponse({"loi": "Khoá bài không hợp lệ."}, status_code=400)
            ds = await _k(app.state.kho.binh_luan_cua_bai, du_an["ma"], khoa)
            if q.get("loai_bl") in CS.LOAI_BL:
                ds = [c for c in ds if CS.loai_bl(c) == q.get("loai_bl")]
            ds = CS.xep_theo_luong(ds)            # trả lời nằm ngay dưới bình luận cha
            mot, trang, so_trang = CS._trang(ds, _so_trang(q.get("trang")), 50)
            return JSONResponse({"tong": len(ds), "trang": trang, "so_trang": so_trang,
                                 "binh_luan": [CS.the_bl(c) for c in mot]})
        try:
            dk = _dk_bl(q)
        except NL.LoiNhap as e:
            return JSONResponse({"loi": str(e)}, status_code=400)
        moc = await _moc_luot()
        rows = await _dong_nho("bl", du_an["ma"], tu, den, moc)
        if rows is None:
            return _ban()
        bai_khoa = None
        if CS.can_tra_bai(bo_loc):
            bai = await _dong_nho("bai", du_an["ma"], tu, den, moc)
            if bai is None:
                return _ban()
            bai_khoa = await _bai_cho_bl(du_an["ma"], bai, rows, moc, bool(bo_loc["q"]))
            if bai_khoa is None:
                return _ban()
        kq = await _k(CS.chi_tiet_bl, rows, tu, den, trang=_so_trang(q.get("trang")),
                      bo_loc=bo_loc, bai_theo_khoa=bai_khoa, **dk)
        # Link + đoạn nội dung bài chỉ đọc cho bình luận của trang này (không cho cả khoảng).
        nc = await _k(app.state.kho.ngu_canh_bai, du_an["ma"],
                      [x["khoa_bai"] for x in kq["binh_luan"]])
        CS.gan_ngu_canh_bai(kq["binh_luan"], nc)
        return JSONResponse(kq)

    async def _tien_do_gan_nhan(ma: str) -> dict | None:
        """Tiến độ gán nhãn nền của Mark — đọc thẳng kho mỗi lần (không nhớ đệm: số đổi theo
        phút). Kho cũ / lỗi: None, trang chỉ không hiện dòng tiến độ."""
        ham = getattr(app.state.kho, "tien_do_gan_nhan", None)
        if ham is None:
            return None
        try:
            return await _k(ham, ma)
        except Exception as e:  # noqa: BLE001 — chỉ là dòng phụ, không làm hỏng trang
            print(f"[chi_so] không đọc được tiến độ gán nhãn: {type(e).__name__}", flush=True)
            return None

    async def _do_phu(ma: str) -> dict | None:
        """Thẻ "Độ phủ" (kiểm 2 lần/tuần của Mark, 17/10/2026) — không theo bộ lọc/khoảng ngày:
        luôn là lần kiểm gần nhất. Bảng chưa tạo / lỗi: None, trang chỉ không hiện thẻ."""
        ham = getattr(app.state.kho, "do_phu_gan_nhat", None)
        if ham is None:
            return None
        try:
            return CS.do_phu_json(await _k(ham, ma), _bay_gio())
        except Exception as e:  # noqa: BLE001 — chỉ là thẻ phụ, không làm hỏng trang
            print(f"[chi_so] không đọc được độ phủ: {type(e).__name__}", flush=True)
            return None

    @app.get("/api/chi-so")
    async def api_chi_so(request: Request):
        x = await _loc_api(request)
        if isinstance(x, JSONResponse):
            return x
        du_an, tu, den, bo_loc = x
        # Cách xếp bảng Nguồn nổi bật (19/10/2026): xếp ở máy chủ, trước khi cắt top mỗi nền tảng.
        # Bộ nhớ đệm giữ bảng của CẢ ba cách xếp (`top_nguon_theo`) — đổi cách xếp không tính lại
        # cả trang, nên `sap_nguon` không nằm trong khoá nhớ.
        sap_nguon = request.query_params.get("sap_nguon") or "thao_luan"
        if sap_nguon not in CS.SAP_NGUON:
            return JSONResponse({"loi": "Cách xếp nguồn không hợp lệ."}, status_code=400)
        hom_nay = _hom_nay()
        # Bộ nhớ đệm: khoá gồm BỘ LỌC + mốc lượt quét vừa xong — có lượt mới là tính lại ngay,
        # không có thì nhiều người mở cùng bộ lọc trong NHO_CHI_SO_GIAY giây chỉ tính một lần.
        # Dòng thô (chưa lọc) nhớ riêng theo khoảng (`_kq_nho`): đổi bộ lọc không đọc lại kho.
        moc = await _moc_luot()
        khoa = (du_an["ma"], tu, den, CS.khoa_bo_loc(bo_loc), hom_nay,
                tuple(du_an["tu_khoa"] or []), *moc)
        nho = app.state.nho_chi_so
        x = nho.get(khoa)
        if x and time.monotonic() - x[0] < NHO_CHI_SO_GIAY:
            data = dict(x[1])
        else:
            if not app.state.ban.acquire(blocking=False):
                return JSONResponse({"loi": "Máy chủ đang bận tính số liệu — thử lại sau ít giây."},
                                    status_code=503, headers={"Retry-After": "5"})
            try:
                kq = await _kq_nho("bai", du_an["ma"], tu, den, moc, da_giu=True)
                kb = await _kq_nho("bl", du_an["ma"], tu, den, moc, da_giu=True)
                # Bình luận kỳ TRƯỚC: chỉ để so "Ý định mua" với kỳ liền trước — chỉ hop_le, cột
                # hẹp, KHÔNG vào bộ nhớ dòng (review 16/10: gấp đôi bộ nhớ khi khoảng chạm trần).
                kbt = await _k(app.state.kho.binh_luan_hop_le_gon, du_an["ma"],
                               *_moc_ngay(*CS.khoang_truoc(tu, den)))
                bai_khoa = None
                if CS.can_tra_bai(bo_loc):
                    bai_khoa = await _bai_cho_bl(du_an["ma"], kq["rows"],
                                                 kb["rows"] + kbt["rows"], moc,
                                                 bool(bo_loc["q"]), da_giu=True)
                tu_khoa_da = du_an["tu_khoa"] or []

                def tinh() -> dict:
                    # MỘT bộ lọc đã dịch cho mọi khối: chữ tìm chỉ bỏ dấu mỗi dòng một lần.
                    f = CS.bien_dich(bo_loc)
                    d = CS.tong_hop(kq["rows"], tu, den, tu_khoa_du_an=tu_khoa_da,
                                    hom_nay=hom_nay, bo_loc=f, moi_cach_xep=True)
                    tk = CS.tu_khoa_thao_luan(kq["rows"], kb["rows"], tu, den,
                                              tu_khoa_du_an=tu_khoa_da, bo_loc=f,
                                              bai_theo_khoa=bai_khoa)
                    d["tu_khoa"], d["tu_khoa_tong"] = tk["tu_khoa"], tk["tong"]
                    d["tu_khoa_an_mg"] = tk["an_minigame"]
                    d["binh_luan_da_cao"] = CS.tong_hop_bl(kb["rows"], tu, den, hom_nay=hom_nay,
                                                           bo_loc=f, bai_theo_khoa=bai_khoa)
                    d["y_dinh_mua"] = CS.y_dinh_mua(kb["rows"], tu, den, rows_truoc=kbt["rows"],
                                                    truoc_bi_cat=bool(kbt["bi_cat"]),
                                                    nay_bi_cat=bool(kb["bi_cat"]),
                                                    hom_nay=hom_nay, bo_loc=f,
                                                    bai_theo_khoa=bai_khoa)
                    d.update(CS.tong_quan_loc(kq["rows"], kb["rows"], tu, den, f, bai_khoa))
                    d["bo_loc"] = CS.bo_loc_json(bo_loc)
                    d["bi_cat"], d["bl_bi_cat"] = kq["bi_cat"], kb["bi_cat"]
                    return d
                data = await _k(tinh)
                del kq, kb, kbt, bai_khoa
                # Link + đoạn nội dung chỉ cho các bài top ý định mua (≤ 20 khoá), không cả khoảng.
                top = data["y_dinh_mua"]["top_bai"]
                if top:
                    CS.gan_ngu_canh_y_dinh(top, await _k(app.state.kho.ngu_canh_bai, du_an["ma"],
                                                         [x["khoa_bai"] for x in top]))
            finally:
                app.state.ban.release()
            nho[khoa] = (time.monotonic(), data)
            while len(nho) > NHO_CHI_SO_TOI_DA:
                nho.popitem(last=False)
            data = dict(data)
        theo = data.pop("top_nguon_theo", None)     # `data` là bản sao nông: bộ nhớ đệm giữ nguyên
        if theo:
            data["top_nguon"] = theo[sap_nguon]
        data["sap_nguon"] = sap_nguon
        # Chỉ cần trạng thái lượt gần nhất (`_luot_json`): không kéo ghi chú (tới 20.000 ký tự).
        luot, _ = await _k(app.state.kho.cac_luot, du_an["ma"], 1, 1, ghi_chu=False)
        data["gan_nhan"] = await _tien_do_gan_nhan(du_an["ma"])
        # 20/10/2026 (chủ dự án): "Độ thu đủ" chỉ giúp người vận hành — không còn trên trang Chỉ số
        # (thẻ vận hành ở trang Quản trị, chỉ quản trị viên); API không trả nữa.
        data.update(du_an={"ma": du_an["ma"], "ten": du_an["ten"]},
                    ngay_cuoi_chua_tron=den >= hom_nay,
                    luot_gan_nhat=_luot_json(luot[0] if luot else None),
                    cap_nhat_luc=datetime.datetime.now(VN).isoformat(timespec="seconds"))
        return JSONResponse(data)

    async def _nhip_dang(ma: str) -> dict:
        """Nhịp đăng từng nguồn (`kho.nhip_dang`); kho giả cũ / bảng lỗi → {} (không co)."""
        ham = getattr(app.state.kho, "nhip_dang", None)
        if ham is None:
            return {}
        try:
            return await _k(ham, ma)
        except LoiKho:
            return {}

    # ─── dự án + nguồn + đề xuất ───
    @app.get("/nguon")
    async def trang_nguon(request: Request):
        nguoi = await _nguoi(request)
        ds = await _ds_doc(nguoi)
        du_an = _chon_du_an(ds, request.query_params.get("du_an"))
        # Bên người này được tạo dự án (quản trị viên: mọi bên) — ô chọn bên của "Thêm dự án";
        # `don_vi_ds` (mọi bên) chỉ cho quản trị viên chuyển dự án sang bên khác.
        cac_ben = await _cac_don_vi()
        ten_ben = {b["ma"]: b["ten"] for b in cac_ben}
        ben_tao = [{"ma": m, "ten": ten_ben.get(m, m)}
                   for m in PQ.ben_quan_ly(nguoi["q"], list(ten_ben)) if m in ten_ben]
        tong = nguoi
        nguoi = _theo_du_an(nguoi, du_an)
        nguon = await _k(app.state.kho.cac_nguon, du_an["ma"]) if du_an else []
        de_xuat = await _k(app.state.kho.cac_de_xuat, du_an["ma"]) if du_an else []
        du_an = an_chi_tiet(nguoi, [du_an], ("sua_boi",))[0] if du_an else None
        # Ước tính tiền/tháng mỗi nguồn theo cấu hình (cùng công thức trang Ngân sách); trình
        # duyệt tính lại ngay khi sửa số bài/chu kỳ bằng chính các hằng số này (`chi_phi_js`).
        # Co số bài theo nhịp đăng (18/10/2026): số bài Mark thật sự lấy, không phải số cấu hình.
        if du_an:
            nguon = CP.gan_co_gian(nguon, await _nhip_dang(du_an["ma"]), du_an)
        nguon = [{**n, "usd_thang": CP.chi_phi_thang_nguon(n)} for n in nguon]
        return _trang(request, "nguon.html", nguoi, "nguon", du_an_ds=ds, du_an=du_an,
                      ben_tao=ben_tao, ten_ben=ten_ben,
                      don_vi_ds=cac_ben if tong["la_quan_tri"] else [],
                      nguon=an_chi_tiet(nguoi, nguon, ("them_boi",), ("loi_cuoi",)),
                      de_xuat=an_chi_tiet(nguoi, de_xuat, ("xu_ly_boi",)),
                      chi_phi_js=CP.hang_so_cho_trinh_duyet(),
                      # Ô "thêm nguồn" (mặc định TikTok 5 bài, mỗi ngày) khi trình duyệt tắt JS.
                      uoc_nguon_moi=CP.chi_phi_thang_nguon({"nen_tang": "tiktok",
                                                            "so_bai_moi_lan": 5}),
                      phi_khoi_dong={p: CP.phi_khoi_dong_ngay(p) for p in NL.NEN_TANG})

    @app.post("/du-an/them")
    async def du_an_them(request: Request):
        nguoi, form = await _sua(request)
        try:
            d = NL.du_an(form, moi=True)
            # Bên của dự án mới: quản trị viên chọn bất kỳ bên nào; quản lý chỉ bên mình quản lý
            # (một bên thì không cần chọn). Bên ngoài danh sách = từ chối, không tạo.
            cac = [b["ma"] for b in await _cac_don_vi()]
            duoc = [m for m in PQ.ben_quan_ly(nguoi["q"], cac) if m in cac]
            ben = str(form.get("don_vi") or "").strip().lower()
            if not ben and len(duoc) == 1:
                ben = duoc[0]
            if not ben:
                raise NL.LoiNhap("Chọn bên sở hữu dự án.")
            if ben not in duoc:
                raise NL.LoiNhap("Bạn không tạo được dự án ở bên này — chọn bên bạn quản lý.")
            d["don_vi"] = ben
            await _k(app.state.kho.them_du_an, nguoi["email"], d)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, "/nguon", "loi", str(e))
        return _chuyen(request, _url("/nguon", du_an=d["ma"]), "ok",
                       f"Đã thêm dự án {d['ten']} (mã {d['ma']}).")

    @app.post("/du-an/{ma}/sua")
    async def du_an_sua(request: Request, ma: str):
        nguoi, form = await _sua(request)
        ve = _url("/nguon", du_an=ma)
        try:
            cu = await _du_an_sua(nguoi, ma)
            d = NL.du_an(form, moi=False)
            # Chuyển dự án sang bên khác: chỉ quản trị viên (đổi bên = đổi ai thấy cả dữ liệu).
            ben = str(form.get("don_vi") or "").strip().lower()
            if ben and ben != cu.get("don_vi"):
                if not nguoi["la_quan_tri"]:
                    raise _Cam("Chỉ quản trị viên mới chuyển được dự án sang bên khác.")
                if ben not in {b["ma"] for b in await _cac_don_vi()}:
                    raise NL.LoiNhap("Không có bên này.")
                d["don_vi"] = ben
            await _k(app.state.kho.sua_du_an, nguoi["email"], ma, d)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", "Đã lưu dự án.")

    @app.post("/nguon/them")
    async def nguon_them(request: Request):
        nguoi, form = await _sua(request)
        ma = str(form.get("du_an") or "")
        ve = _url("/nguon", du_an=ma)
        try:
            await _du_an_sua(nguoi, ma)
            d = NL.nguon(form)
            await _k(app.state.kho.them_nguon, nguoi["email"], ma, d)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok",
                       f"Đã thêm nguồn {NL.TEN_NEN_TANG[d['nen_tang']]} {d['dinh_danh']}.")

    async def _nguon_phai_co(nguoi: dict, nid: int) -> dict:
        """Nguồn để sửa: dự án của nguồn đọc từ kho (không tin biểu mẫu) phải sửa được."""
        n = await _k(app.state.kho.doc_nguon, nid)
        if not n:
            raise _Cam("Không còn nguồn này.", 404)
        await _thuoc_du_an_sua(nguoi, n["du_an"], "Không còn nguồn này.")
        return n

    @app.post("/nguon/{nid}/sua")
    async def nguon_sua(request: Request, nid: int):
        nguoi, form = await _sua(request)
        n = await _nguon_phai_co(nguoi, nid)
        ve = _url("/nguon", du_an=n["du_an"])
        try:
            d = NL.nguon(form)
            await _k(app.state.kho.sua_nguon, nguoi["email"], nid, d)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", f"Đã lưu nguồn {d['dinh_danh']}.")

    @app.post("/nguon/{nid}/trang-thai")
    async def nguon_trang_thai(request: Request, nid: int):
        nguoi, form = await _sua(request)
        n = await _nguon_phai_co(nguoi, nid)
        ve = _url("/nguon", du_an=n["du_an"])
        tt = str(form.get("trang_thai") or "")
        if tt not in ("dang_theo_doi", "tam_dung"):
            return _chuyen(request, ve, "loi", "Trạng thái không hợp lệ.")
        try:
            await _k(app.state.kho.doi_trang_thai_nguon, nguoi["email"], nid, tt)
        except LoiDuLieu as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", ("Đã tạm dừng" if tt == "tam_dung" else "Đã tiếp tục")
                       + f" nguồn {n['dinh_danh']}.")

    @app.post("/nguon/{nid}/xoa")
    async def nguon_xoa(request: Request, nid: int):
        nguoi, _ = await _sua(request)
        n = await _nguon_phai_co(nguoi, nid)
        ve = _url("/nguon", du_an=n["du_an"])
        try:
            await _k(app.state.kho.xoa_nguon, nguoi["email"], nid)
        except LoiDuLieu as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", f"Đã xoá nguồn {n['dinh_danh']} (bài đã quét vẫn giữ).")

    @app.post("/de-xuat/{did}/duyet")
    async def de_xuat_duyet(request: Request, did: int):
        nguoi, form = await _sua(request)
        x = await _k(app.state.kho.doc_de_xuat, did)
        if not x:
            raise _Cam("Không còn đề xuất này.", 404)
        await _thuoc_du_an_sua(nguoi, x["du_an"], "Không còn đề xuất này.")
        ve = _url("/nguon", du_an=x["du_an"])
        if x["trang_thai"] != "cho":
            return _chuyen(request, ve, "loi", "Đề xuất này đã được xử lý.")
        try:
            d = nguon_tu_de_xuat(x, form.get("loai"), form.get("chu_ky_ngay"),
                                 form.get("so_bai_moi_lan"))
            nid = await _k(app.state.kho.duyet_de_xuat, nguoi["email"], did, d)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", f"Đã duyệt — thêm nguồn {d['dinh_danh']}." if nid
                       else f"Đã duyệt — nguồn {d['dinh_danh']} đã có sẵn trong dự án.")

    @app.post("/de-xuat/{did}/tu-choi")
    async def de_xuat_tu_choi(request: Request, did: int):
        nguoi, _ = await _sua(request)
        x = await _k(app.state.kho.doc_de_xuat, did)
        if not x:
            raise _Cam("Không còn đề xuất này.", 404)
        await _thuoc_du_an_sua(nguoi, x["du_an"], "Không còn đề xuất này.")
        ve = _url("/nguon", du_an=x["du_an"])
        try:
            await _k(app.state.kho.tu_choi_de_xuat, nguoi["email"], did)
        except LoiDuLieu as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", f"Đã từ chối đề xuất {x['dinh_danh']}.")

    @app.post("/de-xuat/hang-loat")
    async def de_xuat_hang_loat(request: Request):
        """Duyệt / từ chối NHIỀU đề xuất một lần (chủ dự án 18/10/2026: "chờ duyệt thì có thể là
        chọn nhiều người 1 lúc hoặc chọn tất cả chứ ko chọn từng người 1 mất thời gian").

        Cùng chốt chặn như mọi POST (phiên, nguồn gốc, CSRF, quản lý). Mỗi đề xuất xử lý ĐÚNG như
        nút một dòng — `kho.duyet_de_xuat` / `tu_choi_de_xuat`, mỗi cái một giao dịch + một dòng
        nhật ký — để một đề xuất hỏng không kéo cả lô. Đề xuất không còn chờ (đã xử lý, người khác
        vừa bấm, khác dự án, không còn) thì bỏ qua và đếm. Thông số chung (loại, chu kỳ, số bài)
        kiểm MỘT lần trước khi chạy: sai thì không đụng đề xuất nào."""
        nguoi, form = await _sua(request)
        ma = str(form.get("du_an") or "")
        ve = _url("/nguon", du_an=ma) + "#de-xuat"
        hd = str(form.get("hanh_dong") or "")
        try:
            await _du_an_sua(nguoi, ma)
            if hd not in ("duyet", "tu_choi"):
                raise NL.LoiNhap("Chọn Duyệt hoặc Từ chối.")
            ids = ds_id(form.get("ids"))
            if not ids:
                raise NL.LoiNhap("Chưa chọn đề xuất nào — tích ô đầu dòng rồi bấm lại.")
            loai = str(form.get("loai") or "kol")
            chu_ky = so_bai = 0
            if hd == "duyet":
                if loai not in NL.LOAI_NGUON:
                    raise NL.LoiNhap("Loại nguồn không hợp lệ.")
                chu_ky = NL.so_nguyen(form.get("chu_ky_ngay") or 1, "Chu kỳ quét (ngày)", 1, 30)
                so_bai = NL.so_nguyen(form.get("so_bai_moi_lan") or 5, "Số bài mỗi lần", 1)
        except NL.LoiNhap as e:
            return _chuyen(request, ve, "loi", str(e))
        kho = app.state.kho

        def xu_ly() -> dict:
            dem = {"duyet": 0, "tu_choi": 0, "bo_qua": 0, "da_co": 0, "loi": 0, "loi_dau": "",
                   "dung": ""}
            # Một lần đọc cả danh sách chờ của dự án; id không có trong đó mới đọc lẻ.
            theo = {int(x["id"]): x for x in kho.cac_de_xuat(ma)}
            for i, did in enumerate(ids):
                try:
                    x = theo.get(did) or kho.doc_de_xuat(did)
                    if not x or x.get("du_an") != ma or x.get("trang_thai") != "cho":
                        dem["bo_qua"] += 1
                        continue
                    if hd == "tu_choi":
                        kho.tu_choi_de_xuat(nguoi["email"], did)
                        dem["tu_choi"] += 1
                        continue
                    nid = kho.duyet_de_xuat(nguoi["email"], did,
                                            nguon_tu_de_xuat(x, loai, chu_ky, so_bai))
                    dem["duyet"] += 1
                    dem["da_co"] += int(nid is None)
                except NL.LoiNhap as e:              # định danh Mark đề xuất không dùng được
                    dem["loi"] += 1
                    dem["loi_dau"] = dem["loi_dau"] or f"{x.get('dinh_danh')}: {e}"
                except LoiDuLieu as e:
                    if "không còn chờ" in str(e):    # người khác vừa xử lý cùng lúc
                        dem["bo_qua"] += 1
                    else:
                        dem["loi"] += 1
                        dem["loi_dau"] = dem["loi_dau"] or f"{x.get('dinh_danh')}: {e}"
                except LoiKho as e:                  # kho hỏng giữa chừng: dừng, báo phần đã làm
                    dem["dung"] = f"kho lỗi ({e}) — còn {len(ids) - i} đề xuất chưa xử lý"
                    break
            return dem

        dem = await _k(xu_ly)
        tin = f"Đã duyệt {dem['duyet']}, từ chối {dem['tu_choi']}, bỏ qua {dem['bo_qua']}."
        if dem["da_co"]:
            tin += f" {dem['da_co']} nguồn đã có sẵn trong dự án (chỉ đánh dấu đã duyệt)."
        if dem["loi"]:
            tin += f" Không duyệt được {dem['loi']}: {dem['loi_dau']}"
        if dem["dung"]:
            tin += f" Dừng giữa chừng: {dem['dung']}."
        return _chuyen(request, ve, "canh" if dem["loi"] or dem["dung"] else "ok", tin)

    # ─── ngân sách ───
    @app.get("/ngan-sach")
    async def trang_ngan_sach(request: Request):
        nguoi = await _nguoi(request)
        # Chỉ dự án của bên người này xem được (19/10/2026). Khối "Gói Apify": số đã dùng / trần /
        # ngày đặt lại là của CẢ tài khoản Apify dùng chung (chi phí của token chung, chỉ đọc —
        # chủ dự án chấp nhận cho mọi người xem thấy), còn trần nội bộ + dự báo tới lúc đặt lại chỉ
        # cộng các dự án trong phạm vi — không lộ ngân sách / chi tiêu từng dự án của bên khác.
        ds = await _ds_doc(nguoi)
        da_tieu = await _k(app.state.kho.da_tieu_thang)
        du_an = _chon_du_an(ds, request.query_params.get("du_an"))
        tong_nguoi = nguoi
        nguoi = _theo_du_an(nguoi, du_an)
        trang = _so_trang(request.query_params.get("trang"))
        luot, tong = (await _k(app.state.kho.cac_luot, du_an["ma"], trang, LUOT_MOI_TRANG)
                      if du_an else ([], 0))
        so_trang = max(1, -(-tong // LUOT_MOI_TRANG))
        bay_gio = _bay_gio()
        # Gói Apify (18/10/2026): trần THẬT của cả tài khoản — ảnh chụp Mark ghi (`han_muc_apify`;
        # dashboard không giữ token). Bảng chưa tạo / kho giả cũ: không có khối.
        snap = None
        ham_goi = getattr(app.state.kho, "han_muc_apify", None)
        if ham_goi is not None:
            try:
                snap = await _k(ham_goi)
            except LoiKho:
                snap = None
        dat_lai = CP._vn((snap or {}).get("chu_ky_den"))
        khoi = []
        dong = []
        for d in ds:
            tieu = float(da_tieu.get(d["ma"], 0.0))
            tran_pf = await _k(app.state.kho.tran_platform, d["ma"])
            nguon = await _k(app.state.kho.cac_nguon, d["ma"])
            # Chi THẬT mỗi lượt (18/10/2026): trung vị ≤ 7 lượt gần nhất — dự báo cả tháng và tới
            # lúc gói đặt lại theo số này, không theo riêng nguồn (hụt) hay mức tối đa (lố).
            luot_gan, _ = await _k(app.state.kho.cac_luot, d["ma"], 1, 20, ghi_chu=False)
            # Lịch quét tự động (15/10/2026): số lượt còn lại tháng này theo lịch đang bật thay cho
            # giả định 1 lượt/ngày. Bảng lich_quet chưa có (schema chưa áp) thì giữ giả định cũ.
            try:
                cac_lich = await _k(app.state.kho.cac_lich, d["ma"])
            except LoiKho:
                cac_lich = []
            # Kiểm độ phủ (17/10/2026, 2 lần/tuần): lần kiểm cuối quyết định lần tới. Bảng chưa tạo
            # (schema chưa áp) thì coi như chưa kiểm lần nào.
            lan_cuoi, hd_dp = None, {}
            ham_dp = getattr(app.state.kho, "do_phu_gan_nhat", None)
            if ham_dp is not None:
                try:
                    r_dp = await _k(ham_dp, d["ma"], 1)
                    lan_cuoi = r_dp[0]["luc"] if r_dp else None
                    hd_dp = (r_dp[0].get("hanh_dong") if r_dp else None) or {}
                except LoiKho:
                    lan_cuoi = None
            # Mọi số của dự án — Mark (`hoi_dashboard_tool._chi_phi`) gọi đúng hàm này. Nguồn theo
            # số bài Mark thật sự lấy sau khi co theo nhịp đăng (18/10/2026).
            k = CP.khoi_ngan_sach(d, tieu, tran_pf, nguon, await _nhip_dang(d["ma"]), luot_gan,
                                  cac_lich, lan_cuoi, dat_lai, bay_gio)
            khoi.append((d, k))
            db, bang, dl, dp = k["du_bao"], k["bang"], k["lich"], k["do_phu"]
            tran = db["tran"]
            # Công tắc "Tìm rộng hơn" của Threads (Nâng cao, 18/10/2026): USD nếu bật — để trình
            # duyệt cộng ngay khi người dùng bật lại phần đang tắt (cùng hàm `chi_phi.uoc_th2`).
            th2 = bang["tu_khoa"]["threads"].get("duong2")
            if isinstance(th2, dict):
                th2["uoc_neu_bat"] = CP.uoc_th2({**th2, "bat": True},
                                                CP.tu_nen_tang(d, "threads", CP.tu_tim(d)))
            # `cau_hinh` hiển thị: Threads (MAC_DINH_TAT) chưa đặt thì ô bật hiện TẮT như hiệu lực.
            dong.append({**d, "cau_hinh": CP.cau_hinh_hien_thi(d.get("cau_hinh")),
                         # Hashtag riêng của dự án đã chuẩn hoá (18/10/2026); [] = suy từ từ khoá.
                         "hashtag_rieng": CP.nguon_tag(d, []),
                         # "Không tìm trên…" đã lưu từng nền tảng (18/10/2026) cho trình duyệt.
                         "bo_tu": {p: CP.bo_tu(d, p) for p in CP.NEN_TANG},
                         # Hashtag Instagram thật sự gửi mỗi lượt (khối Nâng cao hiện danh sách).
                         "tag_ig": CP.tu_gui("instagram", CP.tag_cua(d, "instagram", CP.tu_tim(d)),
                                             bang["tu_khoa"]["instagram"]["so_tu"]),
                         "da_tieu": tieu, "con_lai": max(0.0, tran - tieu), "du_bao": db,
                         "bang": bang, "lich": dl,
                         "do_phu": {**dp, "noi": CS.noi_tu_hanh_dong(hd_dp)},
                         "pt": min(100.0, 100.0 * tieu / tran) if tran else (100.0 if tieu else 0),
                         "pt_du_bao": (min(100.0, 100.0 * db["du_bao_thang"] / tran) if tran
                                       else (100.0 if db["du_bao_thang"] else 0))})
        goi = CP.goi_ngan_sach(snap, khoi, bay_gio)
        return _trang(request, "ngan_sach.html", nguoi, "ngan_sach", goi=goi,
                      goi_mot_phan=not tong_nguoi["la_quan_tri"],
                      dong=[an_chi_tiet(_theo_du_an(tong_nguoi, x), [x], ("sua_boi",))[0]
                            for x in dong], du_an=du_an,
                      luot=an_chi_tiet(nguoi, luot, ("ghi_chu", "ghi_chu_dai"), ("loi",)),
                      tong=tong,
                      trang=trang, so_trang=so_trang, thang=bay_gio.strftime("%m/%Y"),
                      so_ngay_thang=CP.so_ngay_thang(bay_gio),
                      hang_so=CP.hang_so_cho_trinh_duyet())

    @app.get("/ngan-sach/luot/{luot_id}/ghi-chu")
    async def ghi_chu_luot(request: Request, luot_id: int):
        """Ghi chú ĐỦ của một lượt (soát 17/10/2026, L5): trang Ngân sách chỉ in phần đầu, bản đủ
        (tới 20.000 ký tự) mở ở đây. Chữ thuần (`text/plain`, nosniff) — không qua HTML nên không
        cần thoát ký tự. Chỉ người SỬA được dự án đó: người chỉ xem không thấy ghi chú
        (`an_chi_tiet`); dự án ngoài phạm vi = 404 như không có."""
        nguoi = await _nguoi(request)
        ma = str(request.query_params.get("du_an") or "")
        d = await _du_an_doc(nguoi, ma)
        if d and not PQ.sua_duoc(nguoi["q"], d):
            raise _Cam("Trang này chỉ dành cho người quản lý.")
        gc = await _k(app.state.kho.ghi_chu_luot, ma, luot_id) if d else None
        if gc is None:
            raise _Cam("Không có ghi chú của lượt này.", 404)
        return PlainTextResponse(gc)

    @app.post("/ngan-sach/{ma}")
    async def ngan_sach_luu(request: Request, ma: str):
        nguoi, form = await _sua(request)
        ve = _url("/ngan-sach", du_an=ma)
        try:
            await _du_an_sua(nguoi, ma)
            usd = NL.tran_usd(form.get("tran_usd_thang"))
            await _k(app.state.kho.dat_tran_thang, nguoi["email"], ma, usd)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", f"Đã đặt trần tháng {usd_vn(usd)} USD cho dự án {ma}.")

    @app.post("/ngan-sach/{ma}/cau-hinh")
    async def ngan_sach_cau_hinh(request: Request, ma: str):
        """Đợt 2e: cấu hình thu thập TỪNG nền tảng (tìm từ khoá + cào bình luận) và trần tháng
        trong MỘT biểu mẫu. Ô bỏ trống = theo mặc định chung của dự án."""
        nguoi, form = await _sua(request)
        ve = _url("/ngan-sach", du_an=ma)
        try:
            await _du_an_sua(nguoi, ma)
            cu_du_an = await _k(app.state.kho.doc_du_an, ma) or {}
            # Soát 18/10/2026: bấm Lưu từng XOÁ khối `gian` (giãn nhịp) của mọi nền tảng — biểu
            # mẫu dựng lại cả nhóm tu_khoa / binh_luan / do_phu từ ô của nó, nên khoá con biểu mẫu
            # không quản (`gian`, `so_tu` ngoài Instagram, khoá thêm về sau…) mất theo. Nay mỗi khối
            # bắt đầu từ bản ĐANG LƯU, chỉ đặt lại khoá biểu mẫu quản (ô trống vẫn = bỏ khoá, theo
            # mặc định chung); nhóm ngoài biểu mẫu (`seeding`, `hashtag_can_nhac_brand`, `web`,
            # `theo_doi`…) giữ nhờ `kho.dat_cau_hinh` chỉ thay nhóm được gửi.
            cu_ch = cu_du_an.get("cau_hinh") if isinstance(cu_du_an.get("cau_hinh"), dict) else {}

            def khoi_cu(*duong: str) -> dict:
                x = cu_ch
                for k in duong:
                    x = x.get(k) if isinstance(x, dict) else None
                return copy.deepcopy(x) if isinstance(x, dict) else {}
            ch: dict = {"tu_khoa": khoi_cu("tu_khoa"), "binh_luan": khoi_cu("binh_luan")}
            for p in CP.NEN_TANG:
                tk = khoi_cu("tu_khoa", p)
                tk["bat"] = form.get(f"tk_{p}_bat") == "1"
                for k in ("so_bai", *(("so_tu",) if p == "instagram" else ()),
                          *(("boc",) if p == "web" else ())):
                    tk.pop(k, None)
                if (form.get(f"tk_{p}_so_bai") or "").strip():
                    tk["so_bai"] = NL.so_nguyen(form.get(f"tk_{p}_so_bai"),
                                                f"Tìm từ khoá {CS.TEN_NEN_TANG.get(p, p)}: số bài",
                                                *CP.GIOI_HAN["tk_so_bai"])
                if p == "instagram" and (form.get("tk_instagram_so_tu") or "").strip():
                    tk["so_tu"] = NL.so_nguyen(form.get("tk_instagram_so_tu"),
                                               "Instagram: số từ khoá", *CP.GIOI_HAN["tk_so_tu"])
                if p == "web" and (form.get("tk_web_boc") or "").strip():
                    tk["boc"] = NL.so_nguyen(form.get("tk_web_boc"),
                                             "Báo & Web: số trang đọc dự phòng", 0,
                                             CP.SO_TOI_DA)
                # Dòng phụ (17/10/2026): Facebook đường 2 (`duong2`), TikTok feed hashtag
                # (`hashtag`). Khối thay CẢ nhóm tu_khoa khi lưu — biểu mẫu không có ô (trang cũ)
                # thì giữ nguyên khối đang có; khoá biểu mẫu không sửa (gio…) luôn giữ.
                for p_phu, khoi, o_bat, o_so, k_so, nhan in (
                        ("facebook", "duong2", "tk_facebook_d2_bat", "tk_facebook_d2_so_bai",
                         "so_bai_moi_tu", "Facebook đường 2: số bài mỗi cụm"),
                        ("tiktok", "hashtag", "tk_tiktok_tag_bat", "tk_tiktok_tag_so_yc",
                         "so_yeu_cau", "TikTok feed hashtag: số yêu cầu mỗi lượt")):
                    if p != p_phu:
                        continue
                    cu = cu_du_an.get("cau_hinh")
                    for k in ("tu_khoa", p, khoi):
                        cu = cu.get(k) if isinstance(cu, dict) else None
                    x = dict(cu) if isinstance(cu, dict) else {}
                    if o_so in form:
                        x["bat"] = form.get(o_bat) == "1"
                        x.pop(k_so, None)
                        if (form.get(o_so) or "").strip():
                            x[k_so] = NL.so_nguyen(form.get(o_so), nhan, 0, CP.SO_TOI_DA)
                    if x:
                        tk[khoi] = x
                    else:
                        tk.pop(khoi, None)
                # "Không tìm trên…" (18/10/2026, `tu_khoa.<p>.bo_tu`): từ khoá không đem đi tìm trên
                # nền tảng này. Biểu mẫu không có ô (trang cũ) thì giữ danh sách đang lưu; ô trống
                # = bỏ khoá (tìm mọi từ khoá như trước).
                o_bo = f"tk_{p}_bo_tu"
                if o_bo in form:
                    bo = NL.danh_sach(form.get(o_bo))
                else:
                    bo = CP.bo_tu(cu_du_an, p)
                tk.pop("bo_tu", None)
                if bo:
                    tk["bo_tu"] = bo
                ch["tu_khoa"][p] = tk
                if p == "web":             # web không cào bình luận (giai đoạn 1)
                    continue
                bl = khoi_cu("binh_luan", p)
                bl["bat"] = form.get(f"bl_{p}_bat") == "1"
                bl.pop("so_bai", None)
                bl.pop("moi_bai", None)
                if (form.get(f"bl_{p}_so_bai") or "").strip():
                    bl["so_bai"] = NL.so_nguyen(form.get(f"bl_{p}_so_bai"),
                                                f"Bình luận {CS.TEN_NEN_TANG.get(p, p)}: số bài",
                                                *CP.GIOI_HAN["bl_so_bai"])
                if (form.get(f"bl_{p}_moi_bai") or "").strip():
                    mb = NL.so_nguyen(form.get(f"bl_{p}_moi_bai"),
                                      f"Bình luận {CS.TEN_NEN_TANG.get(p, p)}: số mỗi bài",
                                      *CP.GIOI_HAN["bl_moi_bai"])
                    if 0 < mb < 5:
                        raise NL.LoiNhap("Số bình luận mỗi bài: 0 (cào hết) hoặc từ 5 trở lên.")
                    bl["moi_bai"] = mb
                ch["binh_luan"][p] = bl
            if "dp_tran" in form:
                # Kiểm độ phủ (17/10/2026, 2 lần/tuần): công tắc + trần mỗi lần; ô trống = 0,20.
                dp = khoi_cu("do_phu")
                dp["bat"] = form.get("dp_bat") == "1"
                dp.pop("tran_usd", None)
                if (form.get("dp_tran") or "").strip():
                    t = NL.tran_usd(form.get("dp_tran"))
                    if t > CP.DP_TRAN_TOI_DA:
                        raise NL.LoiNhap("Kiểm độ phủ: trần tối đa "
                                         f"{usd_vn(CP.DP_TRAN_TOI_DA)} USD mỗi lần.")
                    dp["tran_usd"] = float(t)
                ch["do_phu"] = dp
            tran = (NL.tran_usd(form.get("tran_usd_thang"))
                    if (form.get("tran_usd_thang") or "").strip() else None)
            # Đường 2 Threads (17/10/2026, `tu_khoa.threads.duong2`): biểu mẫu chưa có ô riêng —
            # GIỮ nguyên khối đang lưu, không thì bấm Lưu là mất cấu hình (vd người vận hành đã
            # tắt đường 2 sau cảnh báo "về 0 bài 2 lượt liền" → lưu lại thành bật). Đọc chung bản
            # dự án đã đọc cho các dòng phụ Facebook / TikTok ở trên.
            th_cu = cu_du_an
            for k in ("cau_hinh", "tu_khoa", "threads", "duong2"):
                th_cu = th_cu.get(k) if isinstance(th_cu, dict) else None
            if isinstance(th_cu, dict) and "threads" in ch["tu_khoa"]:
                ch["tu_khoa"]["threads"]["duong2"] = dict(th_cu)
            # 18/10/2026: khối "Nâng cao" có công tắc "Tìm rộng hơn" của Threads (ô ẩn
            # `tk_threads_d2` báo biểu mẫu có công tắc): chỉ đổi `bat`, giữ mọi khoá khác đang lưu
            # (so_bai, so_bai_moi_tu, so_luot). Biểu mẫu cũ không có ô ẩn thì giữ nguyên như trên.
            if "tk_threads_d2" in form and "threads" in ch["tu_khoa"]:
                th2 = dict(ch["tu_khoa"]["threads"].get("duong2") or {})
                th2["bat"] = form.get("tk_threads_d2_bat") == "1"
                ch["tu_khoa"]["threads"]["duong2"] = th2
            await _k(app.state.kho.dat_cau_hinh, nguoi["email"], ma, ch)
            if tran is not None:
                await _k(app.state.kho.dat_tran_thang, nguoi["email"], ma, tran)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        d = await _k(app.state.kho.doc_du_an, ma)
        b = CP.bang_cau_hinh(d or {})
        return _chuyen(request, ve, "ok",
                       f"Đã lưu cấu hình thu thập — ước tối đa {usd_vn(b['uoc_tk'] + b['uoc_bl'])} "
                       "USD/lượt cho tìm từ khoá + bình luận.")

    @app.post("/ngan-sach/{ma}/tu-khoa")
    async def ngan_sach_tu_khoa(request: Request, ma: str):
        nguoi, form = await _sua(request)
        ve = _url("/ngan-sach", du_an=ma)
        try:
            d = await _du_an_sua(nguoi, ma)
            bat = form.get("tk_bat") == "1"
            so_bai = NL.so_nguyen(form.get("tk_so_bai"), "Số bài mỗi nền tảng", 0)
            await _k(app.state.kho.dat_tim_tu_khoa, nguoi["email"], ma, bat, so_bai)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        b = CP.bang_cau_hinh(await _k(app.state.kho.doc_du_an, ma) or {})
        return _chuyen(request, ve, "ok",
                       (f"Đã lưu: tìm {len(d.get('tu_khoa') or [])} từ khoá, tối đa {so_bai} bài mỗi "
                        f"nền tảng mỗi lượt (tối đa ≈ {usd_vn(b['uoc_tk'])} USD/lượt)."
                        if bat else "Đã tắt tìm theo từ khoá."))

    @app.post("/ngan-sach/{ma}/binh-luan")
    async def ngan_sach_binh_luan(request: Request, ma: str):
        nguoi, form = await _sua(request)
        ve = _url("/ngan-sach", du_an=ma)
        try:
            await _du_an_sua(nguoi, ma)
            bat = form.get("bl_bat") == "1"
            so_bai = NL.so_nguyen(form.get("bl_so_bai"), "Số bài cào bình luận mỗi lượt", 0)
            moi_bai = NL.so_nguyen(form.get("bl_moi_bai"), "Số bình luận mỗi bài", 0)
            if 0 < moi_bai < 5:
                raise NL.LoiNhap("Số bình luận mỗi bài: 0 (cào hết) hoặc từ 5 trở lên.")
            await _k(app.state.kho.dat_binh_luan, nguoi["email"], ma, bat, so_bai, moi_bai)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        b = CP.bang_cau_hinh(await _k(app.state.kho.doc_du_an, ma) or {})
        return _chuyen(request, ve, "ok",
                       (f"Đã lưu: cào bình luận tối đa {so_bai} bài mỗi lượt, "
                        + ("mỗi bài cào HẾT bình luận" if not moi_bai else f"mỗi bài {moi_bai} bình luận")
                        + f" (ước tối đa ≈ {usd_vn(b['uoc_bl'])} USD/lượt)."
                        if bat else "Đã tắt cào bình luận."))

    # ─── lịch quét tự động (chủ dự án chốt 15/10/2026: "Dashboard + Mark tự chạy") ───
    async def _du_lieu_lich(du_an: dict):
        """(lịch, nguồn, đã tiêu tháng, trần platform) của một dự án — đủ cho trang + xem trước.
        Nguồn theo số bài Mark thật sự lấy sau khi co theo nhịp đăng (soát 18/10/2026: như trang
        Ngân sách — `tong_quan` cộng phần nguồn theo chu kỳ)."""
        kho, ma = app.state.kho, du_an["ma"]
        cac, nguon = await _k(kho.cac_lich, ma), await _k(kho.cac_nguon, ma)
        return (cac, CP.gan_co_gian(nguon, await _nhip_dang(ma), du_an),
                float((await _k(kho.da_tieu_thang)).get(ma, 0.0)), await _k(kho.tran_platform, ma))

    async def _chi_lich(ma: str) -> dict:
        """Chi thật + trần console mỗi lượt cho trang Lịch quét (18/10/2026, `trang_lich._kep_luot`)
        — `chi_phi.chi_lich`, Mark gọi đúng hàm đó."""
        kho = app.state.kho
        luot_gan, _ = await _k(kho.cac_luot, ma, 1, 20, ghi_chu=False)
        snap = None
        ham_goi = getattr(kho, "han_muc_apify", None)
        if ham_goi is not None:
            try:
                snap = await _k(ham_goi)
            except LoiKho:
                snap = None
        return CP.chi_lich(luot_gan, snap, _bay_gio())

    async def _trang_lich(request: Request, nguoi: dict, ma: str | None, sua_id: str = "",
                          bm: dict | None = None, loi: str = "", ma_http: int = 200):
        """Trang Lịch quét. `bm` + `loi`: vẽ lại biểu mẫu vừa gửi bị từ chối (không mất chữ)."""
        ds = await _ds_doc(nguoi)
        du_an = _chon_du_an(ds, ma)
        bay_gio = _bay_gio()
        nguoi = _theo_du_an(nguoi, du_an)        # quản lý của ĐÚNG bên dự án đang xem
        ql = nguoi["vai_tro"] == "quan_ly"
        ctx: dict = {"du_an_ds": ds, "du_an": du_an, "lich": [], "tong": None, "bm": None,
                     "xt": None, "sua": None, "loi_bm": loi}
        if du_an:
            cac, nguon, da_tieu, tran_pf = await _du_lieu_lich(du_an)
            chi = await _chi_lich(du_an["ma"])
            sua = (next((x for x in cac if str(x["id"]) == str(sua_id)), None)
                   if ql and sua_id else None)
            if ql:
                bm = bm or (LQ.tu_form(sua, bay_gio) if sua else LQ.tu_form_mac_dinh(bay_gio))

            def dung() -> dict:
                """Đếm mốc + chi phí (thuần, có thể vài chục nghìn vòng): chạy trong threadpool,
                không chặn vòng sự kiện (review 15/10, M2)."""
                ra = {"lich": TL.dong_lich(cac, du_an, nguon, bay_gio, ql, LOI_CHUNG, chi),
                      "tong": TL.tong_quan(cac, du_an, nguon, da_tieu, tran_pf, bay_gio, chi)}
                if ql:
                    try:
                        d = LQ.chuan_hoa(LQ.bieu_mau(bm), bay_gio)
                        ra["xt"] = TL.xem_truoc(d, cac, du_an, nguon, da_tieu, tran_pf, bay_gio,
                                                sua["id"] if sua else None, chi)
                    except LQ.LoiLich as e:
                        ra["xt"] = {"loi": str(e)}
                    ra.update(sua=sua, bm=bm)
                return ra
            ctx.update(await _k(dung))
        return _trang(request, "lich_quet.html", nguoi, "lich_quet", ma=ma_http, KIEU_LICH=LQ.KIEU,
                      THU=LQ.THU, MOI_GIO=LQ.MOI_GIO, PHUT_TOI_THIEU=LQ.PHUT_TOI_THIEU,
                      TU_KHOA_THEM_TOI_DA=LQ.TU_KHOA_THEM_TOI_DA,
                      TU_KHOA_THEM_DAI=LQ.TU_KHOA_THEM_DAI, **ctx)

    @app.get("/lich-quet")
    async def trang_lich_quet(request: Request):
        nguoi = await _nguoi(request)
        q = request.query_params
        return await _trang_lich(request, nguoi, q.get("du_an"), q.get("sua") or "")

    @app.get("/api/lich-quet/xem-truoc")
    async def api_lich_xem_truoc(request: Request):
        """10 lần chạy tới + chi phí của biểu mẫu đang gõ (chưa lưu). Chỉ đọc, ai đăng nhập cũng
        gọi được (dự án của bên mình); tính ở máy chủ bằng đúng hàm Mark dùng
        (`dashboard/lich_quet.py`)."""
        nguoi = await _nguoi(request)
        q = request.query_params
        if len(str(request.url.query)) > 4000:
            return JSONResponse({"loi": "Yêu cầu quá dài."}, status_code=400)
        du_an = await _du_an_doc(nguoi, q.get("du_an") or "")
        if not du_an:
            return JSONResponse({"loi": "Không có dự án này."}, status_code=404)
        lid = q.get("lid") or ""
        bay_gio = _bay_gio()
        try:
            d = await _k(LQ.chuan_hoa, dict(q), bay_gio)
        except LQ.LoiLich as e:
            return JSONResponse({"loi": str(e)}, status_code=400)
        cac, nguon, da_tieu, tran_pf = await _du_lieu_lich(du_an)
        chi = await _chi_lich(du_an["ma"])
        # Đếm mốc trong threadpool (review 15/10, M2): không chặn vòng sự kiện của cả dashboard.
        return JSONResponse(await _k(TL.xem_truoc, d, cac, du_an, nguon, da_tieu, tran_pf,
                                     bay_gio, int(lid) if lid.isdigit() and len(lid) < 19
                                     else None, chi))

    async def _lich_phai_co(nguoi: dict, lid: int) -> dict:
        """Lịch để sửa: dự án của lịch đọc từ kho phải sửa được (ngoài phạm vi = 404)."""
        x = await _k(app.state.kho.doc_lich, lid)
        if not x:
            raise _Cam("Không còn lịch này.", 404)
        await _thuoc_du_an_sua(nguoi, x["du_an"], "Không còn lịch này.")
        return x

    def _cau_lan_dau(d: dict, bay_gio) -> str:
        ke = d.get("lan_chay_ke")
        if not d.get("bat"):
            return "Lịch đang tắt — bật khi cần."
        return f"Lần chạy đầu: {LQ.chu_moc(ke, bay_gio)} ({LQ.chu_con(ke, bay_gio)})." if ke else ""

    @app.post("/lich-quet/them")
    async def lich_them(request: Request):
        nguoi, form = await _sua(request)
        ma = str(form.get("du_an") or "")
        bay_gio = _bay_gio()
        try:
            await _du_an_sua(nguoi, ma)
            d = LQ.chuan_hoa(form, bay_gio)
            d["lan_chay_ke"] = LQ.moc_ke(d["kieu"], d["cau_hinh"], bay_gio) if d["bat"] else None
            lid = await _k(app.state.kho.them_lich, nguoi["email"], ma, d)
        except (NL.LoiNhap, LQ.LoiLich, LoiDuLieu) as e:
            return await _trang_lich(request, nguoi, ma, "", LQ.gia_tri_tu_form(form, bay_gio),
                                     str(e), 400)
        return _chuyen(request, _url("/lich-quet", du_an=ma), "ok",
                       f"Đã tạo lịch #{lid} “{d['ten']}”. {_cau_lan_dau(d, bay_gio)}")

    @app.post("/lich-quet/{lid}/sua")
    async def lich_sua(request: Request, lid: int):
        nguoi, form = await _sua(request)
        x = await _lich_phai_co(nguoi, lid)
        bay_gio = _bay_gio()
        try:
            d = LQ.chuan_hoa(form, bay_gio)
            d["lan_chay_ke"] = LQ.moc_ke(d["kieu"], d["cau_hinh"], bay_gio) if d["bat"] else None
            await _k(app.state.kho.sua_lich, nguoi["email"], lid, d)
        except (LQ.LoiLich, LoiDuLieu) as e:
            return await _trang_lich(request, nguoi, x["du_an"], str(lid),
                                     LQ.gia_tri_tu_form(form, bay_gio), str(e), 400)
        return _chuyen(request, _url("/lich-quet", du_an=x["du_an"]), "ok",
                       f"Đã lưu lịch #{lid} “{d['ten']}”. {_cau_lan_dau(d, bay_gio)}")

    @app.post("/lich-quet/{lid}/bat-tat")
    async def lich_bat_tat(request: Request, lid: int):
        nguoi, form = await _sua(request)
        x = await _lich_phai_co(nguoi, lid)
        ve = _url("/lich-quet", du_an=x["du_an"])
        bat = form.get("bat") == "1"
        bay_gio = _bay_gio()
        ke = LQ.moc_ke(x["kieu"], x.get("cau_hinh") or {}, bay_gio) if bat else None
        if bat and ke is None:
            return _chuyen(request, ve, "loi", f"Lịch #{lid} không còn mốc chạy nào (chiến dịch đã "
                           "kết thúc) — sửa thời gian rồi bật lại.")
        try:
            await _k(app.state.kho.bat_tat_lich, nguoi["email"], lid, bat, ke)
        except LoiDuLieu as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", (f"Đã bật lịch #{lid}. "
                                           + _cau_lan_dau({"bat": True, "lan_chay_ke": ke}, bay_gio))
                       if bat else f"Đã tắt lịch #{lid} — Mark không chạy lịch này nữa.")

    @app.post("/lich-quet/{lid}/xoa")
    async def lich_xoa(request: Request, lid: int):
        nguoi, _ = await _sua(request)
        x = await _lich_phai_co(nguoi, lid)
        ve = _url("/lich-quet", du_an=x["du_an"])
        try:
            await _k(app.state.kho.xoa_lich, nguoi["email"], lid)
        except LoiDuLieu as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", f"Đã xoá lịch #{lid} (lượt đã chạy vẫn giữ trong lịch sử).")

    # ─── người xem (19/10/2026: quyền theo bên) ───
    async def _chi_quan_ly(request: Request) -> dict:
        """Quản trị viên hoặc quản lý của ít nhất một bên; người chỉ xem: 403 như trước."""
        nguoi = await _nguoi(request)
        if not nguoi["co_quan_ly"]:
            raise _Cam("Trang này chỉ dành cho người quản lý.")
        return nguoi

    def _neo_nguoi(email: str) -> str:
        """Mã neo của một dòng (#nx-…) — trang quay về đúng người vừa lưu."""
        return "nx-" + hashlib.sha256(email.encode()).hexdigest()[:10]

    def _dong_nguoi_xem(nguoi: dict, x: dict, ben_ql: list[str], ben_thay: list[str],
                        ten_ben: dict, so_quan_tri: int, dang_doc: bool) -> dict:
        """Một dòng trang Quản trị (21/10/2026): tóm tắt quyền bằng chữ (chỉ các bên người xem
        trang quản lý) + ngăn "Sửa quyền": mỗi bên người sửa quản lý một ô chọn (lựa chọn khoá
        theo CHÍNH luật `phan_quyen` mà kho kiểm lại trong giao dịch) + công tắc Quản trị viên."""
        dich = {"la_quan_tri": bool(x.get("la_quan_tri")), "ben": dict(x.get("quyen") or {})}
        lam, e_lam = nguoi["q"], nguoi["email"]
        o_ben = []
        for b in ben_ql:
            duoc, ly_do = PQ.lua_chon_ben(lam, e_lam, dich, x["email"], b)
            o_ben.append({"ma": b, "ten": ten_ben.get(b, b.upper()), "vai": dich["ben"].get(b, ""),
                          "duoc": duoc, "khoa": len(duoc) < 2, "ly_do": ly_do})
        cuoi = dich["la_quan_tri"] and so_quan_tri <= 1
        qt_doi = nguoi["la_quan_tri"] and not cuoi
        sua_duoc = qt_doi or any(not o["khoa"] for o in o_ben)
        ten = x.get("ten_lark") or ""
        return {**x, "o": _o_danh_ba(x, dang_doc), "neo": _neo_nguoi(x["email"]), "ten": ten,
                "tom_tat": PQ.tom_tat(dich, ten_ben, None if nguoi["la_quan_tri"] else ben_thay),
                "o_ben": o_ben, "la_quan_tri": dich["la_quan_tri"], "qt_cuoi": cuoi,
                "qt_doi": qt_doi, "sua_duoc": sua_duoc,
                "xoa_het": nguoi["la_quan_tri"] and not cuoi,
                "tim": bo_dau(" ".join(filter(None, (ten, x["email"], x.get("phong_ban")))))}

    @app.get("/nguoi-xem")
    async def trang_nguoi_xem_cu(request: Request):
        """Đường cũ của trang Quản trị (đổi tên 19/10/2026, chủ dự án): link cũ vẫn mở được —
        308 sang /quan-tri giữ nguyên query. Đòi đăng nhập trước như mọi trang."""
        await _nguoi(request)
        q = request.url.query
        return RedirectResponse("/quan-tri" + (f"?{q}" if q else ""), status_code=308)

    @app.get("/quan-tri")
    async def trang_nguoi_xem(request: Request):
        nguoi = await _chi_quan_ly(request)
        cac_ben = await _cac_don_vi()
        ten_ben = {b["ma"]: b["ten"] for b in cac_ben}
        qt = nguoi["la_quan_tri"]
        # Bên người này quản lý (quản trị viên: mọi bên) — chỉ thấy người + nhật ký của các bên đó;
        # quyền của họ ở bên KHÁC không hiện (không lộ ai làm gì ở bên khác).
        ben_ql = PQ.ben_quan_ly(nguoi["q"], list(ten_ben))
        loc = str(request.query_params.get("ben") or "")
        loc = loc if loc in ben_ql else ""
        ben_thay = [loc] if loc else ben_ql
        ds = await _k(app.state.kho.cac_nguoi_xem)
        so_qt = sum(1 for x in ds if x.get("la_quan_tri"))
        ds = [x for x in ds if set(x.get("quyen") or {}) & set(ben_thay)
              or (qt and not loc and x.get("la_quan_tri"))]
        # 21/10/2026: xếp theo TÊN (tên Lark, chưa có thì email) — chọn người qua tên cho dễ.
        ds.sort(key=lambda x: bo_dau(x.get("ten_lark") or x["email"]))
        du_an = await _k(app.state.kho.cac_du_an)
        if qt:
            nk = await _k(app.state.kho.nhat_ky, 100)
        else:
            nk = await _k(app.state.kho.nhat_ky, 100,
                          [d["ma"] for d in du_an if d.get("don_vi") in ben_ql], ben_ql)
        # Danh bạ Lark: trả trang NGAY bằng bản đệm; dòng cũ thì đọc lại NỀN sau khi đã trả
        # (một lượt đọc một lúc cho cả app — mở trang liên tục không bắn Lark liên tục).
        can = _can_doc_danh_ba(ds, datetime.datetime.now(datetime.UTC))
        nen = None
        if can and not _dang_doc_danh_ba(app):
            app.state.danh_ba_doc_tu = time.monotonic()
            nen = BackgroundTask(doc_danh_ba_nen, app, can,
                                 {x["email"]: x["lark_open_id"] for x in ds
                                  if x.get("lark_open_id")})
        dang_doc = _dang_doc_danh_ba(app)
        # TikTok Ads (19/10/2026): thẻ kết nối + bảng gán bên — CHỈ quản trị viên (chủ dự án chốt).
        tt_the, mt_the, tk_qc, loi_qc = None, None, [], ""
        if qt:
            try:
                tt_the = await _k(app.state.tiktok.the)
                mt_the = await _k(app.state.meta.the)
                tk_qc = [{**t, "nen_tang": QC.nen_tang_tk(t), "duyet": t.get("duyet", True)}
                         for t in await _k(app.state.kho_qc.cac_tk)]
            except (LoiKho, LoiDuLieu) as e:
                log.warning("thẻ quảng cáo lỗi: %s", type(e).__name__)
                loi_qc = ("Chưa đọc được bảng quảng cáo (TikTok / Meta Ads) — chạy "
                          "deploy/lang-nghe/schema.sql bản mới trên VPS rồi tải lại trang.")
        # Độ thu đủ (20/10/2026): thẻ VẬN HÀNH, chỉ quản trị viên — mỗi dự án lần kiểm gần nhất,
        # đúng hàm của trang Chỉ số trước đây (`_do_phu` → `CS.do_phu_json`), không SQL mới.
        do_phu = []
        if qt:
            for d in du_an:
                x = CS.the_do_phu(await _do_phu(d["ma"]))
                if x:
                    do_phu.append({**x, "du_an": d["ma"], "ten_du_an": d.get("ten") or d["ma"],
                                   "dang_bat": d.get("dang_bat", True)})
        r = _trang(request, "nguoi_xem.html", nguoi, "nguoi_xem", so_quan_tri=so_qt,
                   tt=tt_the, mt=mt_the, tk_qc=tk_qc, loi_qc=loi_qc, do_phu=do_phu,
                   co_kiem_do_phu=qt and bool(du_an),
                   TEN_NEN_TANG_QC=QC.TEN_NEN_TANG_QC,
                   ten_ben=[{"ma": m, "ten": t} for m, t in ten_ben.items()],
                   ds=[_dong_nguoi_xem(nguoi, x, ben_ql, ben_thay, ten_ben, so_qt, dang_doc)
                       for x in ds],
                   ben_ql=[{"ma": m, "ten": ten_ben.get(m, m.upper())} for m in ben_ql],
                   LUA_CHON_BEN=PQ.LUA_CHON_BEN,
                   o_moi=[{"ma": m, "ten": ten_ben.get(m, m.upper()),
                           "vai": "xem" if m == loc or len(ben_ql) == 1 else "",
                           "duoc": PQ.lua_chon_ben(nguoi["q"], nguoi["email"], None, "",
                                                    m)[0]} for m in ben_ql],
                   loc_ben=loc,
                   cac_ben=([{**b, "du_an": [d for d in du_an if d.get("don_vi") == b["ma"]]}
                             for b in cac_ben] if qt else []),
                   nhat_ky=[{**x, "chi_tiet_chu": json.dumps(x.get("chi_tiet") or {},
                                                             ensure_ascii=False,
                                                             default=str)[:400]}
                            for x in nk])
        r.background = nen
        if qt:
            # Nút kết nối là form POST → 303 sang trang uỷ quyền TikTok: CSP form-action áp cả lượt
            # chuyển hướng sau khi gửi form, nên CHỈ trang này của quản trị viên thêm đúng một gốc.
            r.headers["content-security-policy"] = _TIEU_DE_AN_TOAN[
                "content-security-policy"].replace("form-action 'self'",
                                                   f"form-action 'self' {TA.MAY_CHU}")
        return r

    def _ve_nguoi(form, email: str = "") -> str:
        """Trang Quản trị sau khi lưu: giữ bộ lọc bên (mã hợp lệ mới giữ) + neo về đúng người."""
        loc = str(form.get("loc_ben") or "").strip().lower()
        duong = "/quan-tri" + (f"?ben={loc}" if re.fullmatch(r"[a-z0-9][a-z0-9_\-]{1,39}", loc)
                               else "")
        return duong + (f"#{_neo_nguoi(email)}" if email else "")

    @app.post("/nguoi-xem/quyen")
    async def nguoi_xem_quyen(request: Request):
        """Lưu TRỌN quyền của một người (21/10/2026 — thay /nguoi-xem/them, /nguoi-xem/quan-tri và
        nút × bỏ từng bên): `email`, `vai__<mã bên>` = "" | xem | quan_ly cho mỗi bên biểu mẫu gửi
        (ô bị khoá không gửi = giữ nguyên), `co_quan_tri=1` khi biểu mẫu có công tắc + `quan_tri=1`
        khi bật. Kho kiểm từng thay đổi bằng luật cũ trong MỘT giao dịch; câu lỗi hiện thẳng."""
        nguoi, form = await _sua(request)
        try:
            e = NL.email(form.get("email"))
            ben: dict[str, str | None] = {}
            for k in form:
                if not str(k).startswith("vai__"):
                    continue
                if len(ben) >= 50:
                    raise NL.LoiNhap("Quá nhiều bên trong một lần lưu.")
                v = str(form.get(k) or "").strip()
                ben[NL.ma_don_vi(str(k)[5:])] = NL.vai_tro(v) if v else None
            quan_tri = (form.get("quan_tri") == "1") if form.get("co_quan_tri") == "1" else None
            # Giá trị trang đã tải (soát 21/10/2026): kho từ chối khi đã có người sửa sau đó.
            da_tai = {"quan_tri": (form.get("qt_cu") == "1") if form.get("qt_cu") in ("0", "1")
                      else None,
                      "ben": {b: (str(form.get(f"cu__{b}") or "").strip() or None)
                              for b in ben if f"cu__{b}" in form}}
            kq = await _k(app.state.kho.dat_quyen, nguoi["email"], e, quan_tri, ben,
                          da_tai=da_tai)
        except (NL.LoiNhap, LoiDuLieu) as ex:
            return _chuyen(request, _ve_nguoi(form, ""), "loi", str(ex))
        ve = _ve_nguoi(form, "" if kq["xoa_nguoi_xem"] else e)
        if kq["xoa_nguoi_xem"]:
            return _chuyen(request, ve, "ok", f"Đã lưu — {e} không còn quyền nào nên đã xoá "
                           "khỏi danh sách.")
        cac_ben = {b["ma"]: b["ten"] for b in await _cac_don_vi()}
        thay = None if nguoi["la_quan_tri"] else PQ.ben_quan_ly(nguoi["q"], list(cac_ben))
        # Tên Lark chỉ khi người này (sau khi lưu) nằm trong phạm vi người sửa thấy trên trang.
        ai = e
        if thay is None or set(kq["sau"]["ben"]) & set(thay):
            cu = next((x for x in await _k(app.state.kho.cac_nguoi_xem) if x["email"] == e), {})
            ai = cu.get("ten_lark") or e
        tt = PQ.tom_tat(kq["sau"], cac_ben, thay)
        tin = (f"Đã lưu quyền cho {ai}: {tt}" if tt
               else f"Đã lưu — {ai} không còn quyền ở bên bạn quản lý")
        if kq["sau"]["la_quan_tri"] and any((v or None) != kq["sau"]["ben"].get(b)
                                             for b, v in ben.items()):
            tin += " (đã là quản trị viên — quyền theo bên giữ nguyên)"
        if not kq["nguoi_moi"]:
            return _chuyen(request, ve, "ok", tin + ".")
        # Người mới: kiểm email với danh bạ Lark — CHỈ cảnh báo, không chặn. Nhanh: chỉ tra theo
        # email (không dò cả danh bạ); Lark không khớp enterprise_email nên "khong_co" ở đây CHƯA
        # chắc: không ghi, lượt đọc nền khi mở trang sẽ dò kỹ.
        kq_db = (await doc_danh_ba(app, [e], DANH_BA_THEM_GIAY, quet=False) or {}).get(e)
        if not kq_db:
            return _chuyen(request, ve, "ok",
                           tin + ". Chưa kiểm được với danh bạ Lark — xem cột Trạng thái sau.")
        if kq_db["trang_thai"] == "khong_co":
            return _chuyen(request, ve, "canh",
                           f"{tin}, nhưng Lark chưa khớp email này. Email công ty: dashboard "
                           "đang dò cả danh bạ — xem cột Trạng thái sau ít giây; người này "
                           "đăng nhập một lần là nhận diện chắc chắn.")
        if kq_db["trang_thai"] != "hoat_dong":
            return _chuyen(request, ve, "canh",
                           f"{tin}, nhưng trên Lark: {DB.TRANG_THAI[kq_db['trang_thai']]} — "
                           "kiểm lại email, người này chưa đăng nhập được.")
        ten = kq_db.get("ten") or ""
        return _chuyen(request, ve, "ok",
                       tin + (f" — {ten}" if ten else "") + ", tài khoản Lark đang hoạt động.")

    @app.post("/nguoi-xem/xoa")
    async def nguoi_xem_xoa(request: Request):
        """Xoá hẳn một người (mọi bên) — chỉ quản trị viên, không xoá quản trị viên cuối (kho kiểm
        trong giao dịch có khoá bảng). Bỏ quyền ở MỘT bên: chọn "Không có quyền" rồi Lưu."""
        nguoi, form = await _sua(request)
        if "don_vi" in form:
            # Tab cũ (nút × bỏ quyền MỘT bên, trước 21/10/2026): không được thành xoá hẳn người.
            return _chuyen(request, "/quan-tri", "loi",
                           "Trang đã cũ — tải lại trang rồi sửa quyền bằng nút Sửa quyền.")
        try:
            e = NL.email(form.get("email"))
            await _k(app.state.kho.xoa_nguoi_xem, nguoi["email"], e)
        except (NL.LoiNhap, LoiDuLieu) as ex:
            return _chuyen(request, _ve_nguoi(form), "loi", str(ex))
        return _chuyen(request, _ve_nguoi(form), "ok", f"Đã xoá {e} khỏi danh sách người xem.")

    async def _danh_ba_ds() -> tuple[list[dict], str]:
        """Cả danh bạ Lark cho ô Thêm người, nhớ DANH_BA_DS_GIAY (lỗi: DANH_BA_DS_LOI_GIAY) — gõ
        tên không bắn Lark mỗi phím; một lượt đọc một lúc cho cả app. -> (người, loại lỗi)."""
        luc, ds, loi = app.state.danh_ba_ds
        if time.monotonic() - luc < (DANH_BA_DS_LOI_GIAY if loi else DANH_BA_DS_GIAY):
            return ds, loi
        async with app.state.khoa_danh_ba_ds:
            luc, ds, loi = app.state.danh_ba_ds
            if time.monotonic() - luc < (DANH_BA_DS_LOI_GIAY if loi else DANH_BA_DS_GIAY):
                return ds, loi
            loi = ""
            try:
                ds = await asyncio.wait_for(app.state.danh_ba.cac_nguoi(), DANH_BA_DS_TOI_DA_GIAY)
            except DB.LoiDanhBa as ex:
                log.warning("đọc cả danh bạ Lark lỗi: %s", ex)
                ds, loi = [], ex.loai
            except Exception as ex:  # noqa: BLE001 — chỉ là gợi ý, nhập email vẫn được
                log.warning("đọc cả danh bạ Lark lỗi: %s", type(ex).__name__)
                ds, loi = [], "loi"
            app.state.danh_ba_ds = (time.monotonic(), ds, loi)
            return ds, loi

    @app.get("/api/danh-ba/tim")
    async def api_danh_ba_tim(request: Request):
        """Gợi ý người theo TÊN hoặc email cho ô "Thêm người". Tìm
        không dấu trong bản nhớ của cả danh bạ Lark; tối đa 8 người. Danh bạ chưa đọc được thì
        trả `loi` — trang vẫn cho nhập email. CHỈ quản trị viên (soát 21/10/2026: quản lý bên không
        liệt kê được cả danh bạ công ty — họ nhập email)."""
        nguoi = await _chi_quan_ly(request)
        if not nguoi["la_quan_tri"]:
            raise _Cam("Chỉ quản trị viên mới tìm được trong danh bạ Lark — nhập email Lark.")
        q = bo_dau(" ".join(str(request.query_params.get("q") or "").split()))[:80]
        if len(q) < 2:
            return JSONResponse({"ket_qua": [], "loi": ""})
        ds, loi = await _danh_ba_ds()
        tu = q.split()
        kq = [x for x in ds if all(t in bo_dau(f"{x['ten']} {x['email']}") for t in tu)][:8]
        return JSONResponse({"ket_qua": kq, "loi": loi})

    @app.post("/don-vi/them")
    async def don_vi_them(request: Request):
        """Tạo bên mới (chỉ quản trị viên — kho kiểm lại trong giao dịch)."""
        nguoi, form = await _sua(request)
        try:
            if not nguoi["la_quan_tri"]:
                raise NL.LoiNhap("Chỉ quản trị viên mới tạo được bên.")
            ma = NL.ma_don_vi(form.get("ma"))
            ten = NL.sach(form.get("ten"), 200)
            if not ten:
                raise NL.LoiNhap("Chưa nhập tên bên.")
            await _k(app.state.kho.them_don_vi, nguoi["email"], ma, ten)
        except (NL.LoiNhap, LoiDuLieu) as ex:
            return _chuyen(request, "/quan-tri", "loi", str(ex))
        return _chuyen(request, "/quan-tri", "ok", f"Đã tạo bên {ten} (mã {ma}).")

    # ─── BigQuery (19/10/2026: chỉ quản trị viên — trạng thái gồm mọi bảng của mọi bên) ───
    async def _chi_quan_tri(request: Request) -> dict:
        nguoi = await _nguoi(request)
        if not nguoi["la_quan_tri"]:
            raise _Cam("Trang này chỉ dành cho quản trị viên.")
        return nguoi

    @app.get("/bigquery")
    async def trang_bigquery(request: Request):
        nguoi = await _chi_quan_tri(request)
        loi = ""
        try:
            tt = await _k(app.state.dong_bo.trang_thai)
        except Exception as e:  # noqa: BLE001 — trang vẫn hiện, chỉ báo chưa đọc được
            loi = f"Chưa đọc được trạng thái đồng bộ ({type(e).__name__})."
            tt = {"dataset": "", "da_bat": False, "bang": []}
        # `canh_bao` (soát 18/10/2026, `dong_bo_bq.tach_canh_bao`) không che: câu do dong_bo_bq tự
        # soạn (tên cột, tên lỗi), không có chữ lỗi thô của Google như `loi`.
        tt = {**tt, "bang": an_chi_tiet(nguoi, list(tt.get("bang") or []), (), ("loi",))}
        return _trang(request, "bigquery.html", nguoi, "bigquery", tt=tt, loi_tt=loi)

    @app.post("/bigquery/dong-bo")
    async def bigquery_dong_bo(request: Request):
        nguoi, _ = await _sua(request)
        if not nguoi["la_quan_tri"]:
            raise _Cam("Chỉ quản trị viên mới đồng bộ BigQuery.")
        if not app.state.dong_bo.da_bat():
            return _chuyen(request, "/bigquery", "loi",
                           "Đồng bộ chưa bật (thiếu BQ_DATASET trên máy chủ dashboard).")
        try:
            await _k(app.state.kho.ghi_nhat_ky, nguoi["email"], "dong_bo_bq", "bigquery",
                     {"dataset": app.state.dong_bo.dataset(), "kieu": "bam_tay"})
        except LoiDuLieu as e:
            return _chuyen(request, "/bigquery", "loi", str(e))
        _chay_dong_bo_nen(app.state.dong_bo.chay)
        return _chuyen(request, "/bigquery", "ok", "Đã bắt đầu đồng bộ — tải lại trang sau ít "
                       "phút để xem kết quả (đang có lượt khác thì lượt này tự bỏ qua).")

    # ─── TikTok Ads (19/10/2026): kết nối — CHỈ quản trị viên ───
    def _ve_quan_tri(request: Request, loai: str, tin: str, *, xoa_cookie: bool = False,
                     neo: str = "tiktok"):
        r = _chuyen(request, f"/quan-tri#{neo}", loai, tin)
        if xoa_cookie:
            r.delete_cookie(COOKIE_TIKTOK, path="/tiktok", secure=cau_hinh.cookie_secure,
                            httponly=True, samesite="lax")
        return r

    def _redirect_tiktok() -> str:
        return cau_hinh.base_url + "/tiktok/xong"

    def _bam_csrf(csrf: str) -> str:
        """Dấu của mã CSRF phiên (state OAuth mang dấu này, không mang chính mã CSRF)."""
        return hashlib.sha256(b"tiktok-state|" + str(csrf).encode()).hexdigest()[:32]

    @app.get("/tiktok/ket-noi")
    async def tiktok_ket_noi_cu(request: Request):
        """Link cũ / gõ tay: GET không có tác dụng phụ — chỉ đưa về thẻ trên trang Quản trị (nút
        kết nối là biểu mẫu POST có CSRF)."""
        await _nguoi(request)
        return RedirectResponse("/quan-tri#tiktok", status_code=303)

    @app.post("/tiktok/ket-noi")
    async def tiktok_ket_noi(request: Request):
        """Bắt đầu OAuth TikTok (nút "Đăng nhập lại để gia hạn 30 ngày", POST + CSRF + Origin).
        State ký HMAC, buộc vào PHIÊN quản trị viên (dấu CSRF của phiên) + cookie nonce của chính
        trình duyệt; PKCE verifier nằm trong cookie đã MÃ HOÁ, chỉ gửi kèm đường /tiktok."""
        nguoi, _ = await _sua_qt(request)
        tt = app.state.tiktok
        loi = tt.loi_khoa()
        if loi:
            return _ve_quan_tri(request, "loi", f"Chưa kết nối được: {loi} — xem dashboard/README.md "
                                "mục TikTok Ads.")
        nonce = secrets.token_urlsafe(18)
        het = time.time() + TIKTOK_STATE_GIAY
        state = DN.ky({"n": nonce, "c": _bam_csrf(nguoi["csrf"]), "het": het},
                      cau_hinh.khoa_phien, "tiktok_state")
        try:
            url, ver = await _k(tt.bat_dau, _redirect_tiktok(), state)
            mo = await _k(tt.ma_hoa_tam, ver)
        except (TA.LoiTikTok, TA.LoiMaHoa, LoiKho) as e:
            log.warning("bắt đầu OAuth TikTok lỗi: %s", e)
            return _ve_quan_tri(request, "loi", f"Chưa mở được trang đăng nhập TikTok ({e}).")
        r = RedirectResponse(url, status_code=303)
        _dat_cookie(request, r, COOKIE_TIKTOK,
                    DN.ky({"n": nonce, "v": mo, "e": nguoi["email"], "het": het},
                          cau_hinh.khoa_phien, "tiktok_oauth"), TIKTOK_STATE_GIAY, "/tiktok")
        return r

    @app.get("/tiktok/xong")
    async def tiktok_xong(request: Request):
        """TikTok trả về sau khi quản trị viên bấm Authorize. Kiểm: phiên quản trị viên, state đúng
        chữ ký + chưa quá 10 phút + nonce trùng cookie của chính trình duyệt + đúng phiên (dấu
        CSRF) + đúng người (email). Rồi đổi mã (PKCE), lưu token MÃ HOÁ, đọc tài khoản."""
        nguoi = await _chi_quan_tri(request)
        q = request.query_params
        tt = app.state.tiktok
        if q.get("error"):
            return _ve_quan_tri(request, "loi", "TikTok báo chưa cấp quyền (bạn đã bấm từ chối hoặc "
                                "đóng trang) — bấm Đăng nhập lại để thử.", xoa_cookie=True)
        st = DN.mo(q.get("state"), cau_hinh.khoa_phien, "tiktok_state")
        ck = DN.mo(request.cookies.get(COOKIE_TIKTOK), cau_hinh.khoa_phien, "tiktok_oauth")
        hop_le = bool(st and ck and isinstance(st.get("n"), str) and isinstance(ck.get("n"), str)
                      and hmac.compare_digest(st["n"].encode(), ck["n"].encode())
                      and hmac.compare_digest(str(st.get("c") or "").encode(),
                                              _bam_csrf(nguoi["csrf"]).encode())
                      and ck.get("e") == nguoi["email"])
        if not hop_le:
            return _ve_quan_tri(request, "loi", "Lượt kết nối TikTok không hợp lệ hoặc đã quá 10 "
                                "phút — bấm “Đăng nhập lại để gia hạn 30 ngày” để làm lại.",
                                xoa_cookie=True)
        code = q.get("code") or ""
        if not code or len(code) > 2000:
            return _ve_quan_tri(request, "loi", "TikTok không trả mã cấp quyền — bấm Đăng nhập lại.",
                                xoa_cookie=True)
        try:
            ver = await _k(tt.giai_ma_tam, str(ck.get("v") or ""))
            kq = await _k(tt.ket_thuc, nguoi["email"], code, ver, _redirect_tiktok())
        except (TA.LoiTikTok, TA.LoiMaHoa, LoiKho) as e:
            log.warning("kết thúc OAuth TikTok lỗi: %s", e)
            return _ve_quan_tri(request, "loi", f"Chưa kết nối được TikTok ({e}).",
                                xoa_cookie=True)
        if not kq.get("ok"):
            return _ve_quan_tri(request, "canh", "Đã lưu kết nối nhưng chưa đọc được tài khoản "
                                f"quảng cáo ({kq.get('loi')}) — xem thẻ Kết nối TikTok Ads.",
                                xoa_cookie=True)
        await _yeu_cau_dong_bo(nguoi["email"])
        app.state.nho_ben_qc = (float("-inf"), set())
        thay, truoc = kq.get("so_tk_thay"), kq.get("so_tk_truoc")
        tin = f"Đã kết nối TikTok Ads — thấy {thay} tài khoản quảng cáo"
        if truoc is not None and thay is not None and thay < truoc:
            return _ve_quan_tri(request, "canh", f"{tin}, ÍT HƠN lần trước ({truoc}). Kiểm lại "
                                "quyền của tài khoản TikTok vừa đăng nhập. " + CHO_DONG_BO,
                                xoa_cookie=True)
        return _ve_quan_tri(request, "ok", f"{tin}. {CHO_DONG_BO} Lần đầu nạp 90 ngày, có thể mất "
                            "vài chục phút tới vài giờ.", xoa_cookie=True)

    async def _yeu_cau_dong_bo(ai: str) -> bool:
        """Ghi cờ yêu cầu đồng bộ (bộ hẹn giờ 2 phút chạy). Dashboard KHÔNG tự chạy đồng bộ."""
        try:
            await _k(app.state.tiktok.yeu_cau, ai)
            return True
        except (LoiKho, LoiDuLieu) as e:
            log.warning("ghi yêu cầu đồng bộ TikTok lỗi: %s", type(e).__name__)
            return False

    async def _sua_qt(request: Request) -> tuple[dict, dict]:
        nguoi, form = await _sua(request)
        if not nguoi["la_quan_tri"]:
            raise _Cam("Chỉ quản trị viên mới quản lý kết nối TikTok Ads.")
        return nguoi, form

    @app.post("/tiktok/ngat")
    async def tiktok_ngat(request: Request):
        nguoi, _ = await _sua_qt(request)
        try:
            loai = ((await _k(app.state.kho_qc.doc_ket_noi)) or {}).get("loai")
            da = await _k(app.state.tiktok.ngat, nguoi["email"])
        except (LoiKho, LoiDuLieu) as e:
            return _ve_quan_tri(request, "loi", f"Chưa ngắt được ({e}).")
        if loai == "api_token":
            # Token API KHÔNG hết hạn và dashboard không thu hồi được nó: nhắc thu hồi tận gốc.
            return _ve_quan_tri(request, "canh", "Đã xoá token API khỏi máy chủ. Token này KHÔNG tự "
                                "hết hạn — vào TikTok for Business Developer (trang app) thu hồi "
                                "hoặc tạo lại token để nó không còn dùng được ở đâu khác.")
        return _ve_quan_tri(request, "ok", "Đã ngắt kết nối TikTok Ads và xoá token khỏi máy chủ"
                            + ("." if da else " (TikTok chưa xác nhận thu hồi — token tự hết hạn)."))

    @app.post("/tiktok/token")
    async def tiktok_token(request: Request):
        """Dán token API (app developer, không hết hạn): thử một lượt đọc rồi mới lưu (mã hoá)."""
        nguoi, form = await _sua_qt(request)
        tt = app.state.tiktok
        loi = tt.loi_khoa()
        if loi:
            return _ve_quan_tri(request, "loi", f"Chưa lưu được token: {loi}.")
        try:
            kq = await _k(tt.luu_api_token, nguoi["email"], form.get("token") or "")
        except TA.LoiXacThuc:
            return _ve_quan_tri(request, "loi", "TikTok không nhận token này — kiểm lại token "
                                "API access của app (chưa lưu gì).")
        except (TA.LoiTikTok, TA.LoiMaHoa, LoiKho) as e:
            return _ve_quan_tri(request, "loi", f"Chưa lưu được token ({e}).")
        await _yeu_cau_dong_bo(nguoi["email"])
        app.state.nho_ben_qc = (float("-inf"), set())
        return _ve_quan_tri(request, "ok", "Đã lưu token API (không hết hạn) — thấy "
                            f"{kq.get('so_tk_thay')} tài khoản quảng cáo. " + CHO_DONG_BO)

    @app.post("/tiktok/gan-ben")
    @app.post("/qc/gan-ben")
    async def tiktok_gan_ben(request: Request):
        """Bảng "Tài khoản quảng cáo → bên" (TikTok + Meta): bên, bật đồng bộ, (Meta) duyệt."""
        nguoi, form = await _sua_qt(request)
        adv = str(form.get("advertiser_id") or "")
        ben = str(form.get("don_vi") or "").strip().lower()
        bat = form.get("dang_dong_bo") == "1"
        meta = adv.startswith("act_")
        if not re.fullmatch(r"(act_)?[0-9]{1,30}", adv):
            return _ve_quan_tri(request, "loi", "Mã tài khoản quảng cáo không hợp lệ.", neo="tk-qc")
        duyet = (form.get("duyet") == "1") if meta else None
        try:
            if meta:
                await _k(app.state.kho_qc.gan_ben, nguoi["email"], adv, ben or None, bat, duyet)
            else:
                await _k(app.state.kho_qc.gan_ben, nguoi["email"], adv, ben or None, bat)
        except (LoiDuLieu, LoiKho) as e:
            return _ve_quan_tri(request, "loi", str(e), neo="tk-qc")
        app.state.nho_ben_qc = (float("-inf"), set())
        return _ve_quan_tri(request, "ok", f"Đã lưu tài khoản {adv}: "
                            + (f"bên {ben.upper()}" if ben else "chưa gán bên")
                            + (", đang đồng bộ" if bat else ", tắt đồng bộ")
                            + ("" if duyet is None else (", đã duyệt." if duyet else
                                                         ", chưa duyệt (không đọc số).")),
                            neo="tk-qc")

    # ─── Meta Ads (20/10/2026): kết nối — CHỈ quản trị viên. "Đồng bộ ngay" của thẻ bỏ (20/10/2026,
    # chủ dự án): đồng bộ bấm tay chỉ còn ở dải "Số quảng cáo" trang Quảng cáo (/quang-cao/dong-bo). ───
    @app.post("/meta/ngat")
    async def meta_ngat(request: Request):
        nguoi, _ = await _sua_qt(request)
        try:
            await _k(app.state.meta.ngat, nguoi["email"])
        except (LoiKho, LoiDuLieu) as e:
            return _ve_quan_tri(request, "loi", f"Chưa ngắt được ({e}).", neo="meta")
        return _ve_quan_tri(request, "canh", "Đã xoá token Meta khỏi máy chủ (số đã đồng bộ giữ "
                            "nguyên). Token người dùng hệ thống KHÔNG tự hết hạn và dashboard không "
                            "thu hồi được bằng quyền đọc — vào Meta Business Settings → Người dùng "
                            "hệ thống → thu hồi / tạo lại token.", neo="meta")

    @app.post("/meta/token")
    async def meta_token(request: Request):
        """Dán token người dùng hệ thống: GET me + me/permissions (CHỈ ĐỌC mới nhận) +
        me/adaccounts rồi mới lưu (mã hoá). Duyệt tài khoản giữ như cũ; tài khoản mới chờ duyệt."""
        nguoi, form = await _sua_qt(request)
        mt = app.state.meta
        loi = mt.loi_khoa()
        if loi:
            return _ve_quan_tri(request, "loi", f"Chưa lưu được token: {loi}.", neo="meta")
        try:
            kq = await _k(mt.luu_token, nguoi["email"], form.get("token") or "")
        except MA.LoiTokenKhongChiDoc as e:
            return _ve_quan_tri(request, "loi", f"Không lưu: {e}.", neo="meta")
        except MA.LoiXacThuc:
            return _ve_quan_tri(request, "loi", "Meta không nhận token này (chưa lưu gì).",
                                neo="meta")
        except (MA.LoiMeta, TA.LoiMaHoa, LoiKho) as e:
            return _ve_quan_tri(request, "loi", f"Chưa lưu được token ({e}).", neo="meta")
        app.state.nho_ben_qc = (float("-inf"), set())
        return _ve_quan_tri(request, "ok", f"Đã lưu token Meta ({kq.get('chu') or 'không tên'}; "
                            f"quyền {', '.join(kq.get('quyen') or [])}) — thấy "
                            f"{kq.get('so_tk_thay')} tài khoản. Tài khoản mới cần được duyệt ở bảng "
                            "bên dưới. " + CHO_DONG_BO, neo="meta")

    # ─── Quảng cáo TikTok (trang + API; chỉ bên đọc được, tiền chỉ quản trị/quản lý) ───
    def _du_lieu_qc(nguoi: dict, qp, cac_tk: list[dict], ten_ben: dict, *, nghiem: bool) -> dict:
        """Số cho trang /quang-cao và /api/qc (cùng một hàm, chạy trong threadpool). `nghiem`: API —
        bên / tài khoản ngoài phạm vi là 404 (như không có); trang — lùi về mặc định."""
        q = nguoi["q"]
        # 20/10/2026: lọc nền tảng (tat_ca | tiktok | meta) + chỉ tài khoản đã duyệt (Meta).
        nen = str(qp.get("nen_tang") or "tat_ca")
        if nen not in (*QC.NEN_TANG_QC, "tat_ca"):
            if nghiem:
                raise NL.LoiNhap("Nền tảng phải là tat_ca, tiktok hoặc meta.")
            nen = "tat_ca"
        cac_nen = [n for n in QC.NEN_TANG_QC if any(QC.nen_tang_tk(t) == n
                                                    for t in QC.tk_dung(cac_tk))]
        cac_tk = QC.tk_dung(cac_tk, nen)
        cac_ben = QC.ben_doc_qc(q, cac_tk)
        if nguoi["la_quan_tri"]:
            if any(not t.get("don_vi") for t in cac_tk):
                cac_ben.append(QC.CHUA_GAN)
            cac_ben.insert(0, QC.TAT_CA)
        ben = str(qp.get("ben") or "")
        if ben not in cac_ben:
            if ben and nghiem:
                raise _Cam("Không có bên này.", 404)
            ben = cac_ben[0] if cac_ben else ""
        tk_ben = QC.tk_trong_pham_vi(q, cac_tk, ben) if ben else []
        # 22/10/2026 (chủ dự án): chọn NHIỀU tài khoản — `tk=` lặp lại (một `tk=` cũ vẫn dùng được);
        # mọi mã kiểm theo phạm vi người xem: trang bỏ lặng mã lạ, API 404 như trước.
        tk_ds, tk_ngoai = QC.tk_chon(qp.getlist("tk") if hasattr(qp, "getlist") else qp.get("tk"),
                                     tk_ben)
        if tk_ngoai and nghiem:
            raise _Cam("Không có tài khoản quảng cáo này.", 404)
        tk = tk_ds[0] if len(tk_ds) == 1 else ""
        ids = list(tk_ds) or [t["advertiser_id"] for t in tk_ben]
        tu, den = _doc_khoang(qp)
        if tu > den or (den - tu).days >= KHOANG_TOI_DA_NGAY:
            raise NL.LoiNhap(f"Khoảng ngày phải từ 1 tới {KHOANG_TOI_DA_NGAY} ngày.")
        co_tien = QC.xem_tien(q, ben if ben not in (QC.TAT_CA, QC.CHUA_GAN) else None)
        kq = app.state.kho_qc
        t0, t1 = QC.khoang_truoc(tu, den)
        kpi = QC.kpi(kq.qc_tong(ids, tu, den) if ids else {})
        kpi_truoc = QC.kpi(kq.qc_tong(ids, t0, t1) if ids else {})
        theo = {r["ngay"]: r for r in (kq.qc_theo_ngay(ids, tu, den) if ids else [])}
        ngay, d = [], tu
        while d <= den:
            r = theo.get(d) or {}
            ngay.append({"ngay": d.isoformat(), **{c: r.get(c) or 0 for c in QC.TEN_COT_SO},
                         "tuong_tac": QC.tuong_tac(r)})
            d += datetime.timedelta(days=1)
        # 22/10/2026 (MKT): bảng chiến dịch / quảng cáo lọc theo tên + chiến dịch, xếp theo mọi cột;
        # (chủ dự án) 20 dòng một trang, trang `tc` / `ta` kẹp về trang cuối ở `kho_qc.qc_bang`.
        lb = QC.loc_bang(qp, co_tien)
        sap = lb["sap"]
        ten_tk = {t["advertiser_id"]: t.get("ten") or t["advertiser_id"] for t in cac_tk}
        nen_tk = {t["advertiser_id"]: QC.nen_tang_tk(t) for t in cac_tk}
        dem, trang = {}, {}
        moi_trang = QC.DONG_MOI_TRANG

        def top(cap):
            # Chữ tìm không còn chữ/số Latin nào (vd "…", chữ Thái) → không khớp gì, không lờ đi.
            tr = lb["tc"] if cap == "campaign" else lb["ta"]
            b = (kq.qc_bang(cap, ids, tu, den, sap=sap, tang=lb["chieu"] == "tang", mau=lb["mau"],
                            cd=lb["cd"], n=moi_trang, bo_qua=(tr - 1) * moi_trang)
                 if ids and not (lb["tim"] and not lb["mau"]) else {"rows": [], "tong": 0})
            dem[cap] = b["tong"]
            trang[cap] = int(b.get("bo_qua") or 0) // moi_trang + 1
            return [{**QC.dong_top(r), "ten_tk": ten_tk.get(r.get("advertiser_id"), ""),
                     "nen_tang": nen_tk.get(r.get("advertiser_id"), "tiktok")} for r in b["rows"]]
        # Tách theo nền tảng (KPI tổng + chuỗi ngày của từng nền tảng trong phạm vi đang lọc).
        theo_nen, ngay_nen = [], []
        for n in QC.NEN_TANG_QC:
            ids_n = [i for i in ids if nen_tk.get(i) == n]
            if ids_n:
                theo_nen.append({"nen_tang": n, "ten": QC.TEN_NEN_TANG_QC[n],
                                 "so_tai_khoan": len(ids_n),
                                 "kpi": QC.kpi(kq.qc_tong(ids_n, tu, den))})
                ngay_nen.extend({"ngay": r["ngay"].isoformat() if hasattr(r["ngay"], "isoformat")
                                 else str(r["ngay"]), "nen_tang": n,
                                 **{c: r.get(c) or 0 for c in QC.TEN_COT_SO},
                                 "tuong_tac": QC.tuong_tac(r)}
                                for r in kq.qc_theo_ngay(ids_n, tu, den))
        kg = kq.qc_khan_gia(ids) if ids else {"rows": [], "tu": None, "den": None}
        moi = (kq.qc_moi(ids) if ids else None) or {}
        ten = {**ten_ben, QC.TAT_CA: "Tất cả bên", QC.CHUA_GAN: "Chưa gán bên"}
        ra = {
            "ben": ben, "cac_ben": [{"ma": b, "ten": ten.get(b, b.upper())} for b in cac_ben],
            "nen_tang": nen,
            "cac_nen_tang": [{"ma": "tat_ca", "ten": "Tất cả"}]
            + [{"ma": n, "ten": QC.TEN_NEN_TANG_QC[n]} for n in cac_nen],
            "tk": tk, "tk_ds": tk_ds,
            "tai_khoan": [{"advertiser_id": t["advertiser_id"],
                           "ten": t.get("ten") or t["advertiser_id"],
                           "nen_tang": QC.nen_tang_tk(t),
                           "tien_te": t.get("tien_te") or "VND"} for t in tk_ben],
            "theo_nen_tang": theo_nen, "theo_ngay_nen_tang": ngay_nen,
            "tu": tu.isoformat(), "den": den.isoformat(),
            "ky_truoc": {"tu": t0.isoformat(), "den": t1.isoformat()},
            "xem_tien": co_tien, "sap": sap,
            "tien_te": sorted({t.get("tien_te") or "VND" for t in tk_ben
                               if t["advertiser_id"] in ids}) or ["VND"],
            "kpi": kpi, "kpi_truoc": kpi_truoc,
            "doi": {k: QC.doi_pt(kpi.get(k), kpi_truoc.get(k)) for k in kpi},
            "theo_ngay": ngay, "campaign": top("campaign"), "ad": top("ad"),
            "bang": {"tim": lb["tim"], "cd": lb["cd"], "chieu": lb["chieu"], "moi_trang": moi_trang,
                     "tong_campaign": dem.get("campaign", 0), "tong_ad": dem.get("ad", 0),
                     "trang_campaign": trang.get("campaign", 1), "trang_ad": trang.get("ad", 1),
                     "so_trang_campaign": max(1, -(-dem.get("campaign", 0) // moi_trang)),
                     "so_trang_ad": max(1, -(-dem.get("ad", 0) // moi_trang))},
            "khan_gia": QC.khan_gia(kg.get("rows") or []),
            "khan_gia_khoang": {"tu": kg.get("tu"), "den": kg.get("den")},
            "moi": {"ngay_cuoi": moi.get("ngay_cuoi"), "ghi_luc": moi.get("ghi_luc")},
        }
        # Chốt chặn tiền ở MÁY CHỦ: người Chỉ xem không bao giờ nhận khoá tiền (kể cả khối con).
        # 22/10/2026 (chủ dự án): doanh thu Shop / ROAS tạm ẩn với MỌI người (`QC.HIEN_DOANH_THU`).
        return QC.loc_doanh_thu(QC.loc_tien(ra, co_tien))

    async def _qc_cho(nguoi: dict, qp, *, nghiem: bool) -> dict:
        """Cùng ngân sách tính với /api/chi-so (`app.state.ban`, tối đa TINH_SONG_SONG lượt cùng
        lúc, quá thì 503 — không xếp hàng). Khoảng ngày ≤ KHOANG_TOI_DA_NGAY (`_du_lieu_qc`)."""
        if not app.state.ban.acquire(blocking=False):
            raise _Cam("Máy chủ đang bận tính số liệu — thử lại sau ít giây.", 503)
        try:
            cac_tk = list(await _k(app.state.kho_qc.cac_tk))
            ten_ben = {b["ma"]: b["ten"] for b in await _cac_don_vi()}
            return await _k(_du_lieu_qc, nguoi, qp, cac_tk, ten_ben, nghiem=nghiem)
        finally:
            app.state.ban.release()

    @app.get("/api/qc")
    async def api_qc(request: Request):
        nguoi = await _nguoi(request)
        if not nguoi.get("co_qc"):
            return JSONResponse({"loi": "Không có quyền xem trang quảng cáo."}, status_code=404)
        try:
            d = await _qc_cho(nguoi, request.query_params, nghiem=True)
        except NL.LoiNhap as e:
            return JSONResponse({"loi": str(e)}, status_code=400)
        if not d["cac_ben"]:
            return JSONResponse({"loi": "Bên của bạn chưa có tài khoản quảng cáo TikTok nào."},
                                status_code=404)
        return JSONResponse(json.loads(json.dumps(d, ensure_ascii=False, default=str)))

    @app.get("/quang-cao")
    async def trang_quang_cao(request: Request):
        nguoi = await _nguoi(request)
        if not nguoi.get("co_qc"):
            raise _Cam("Bên của bạn chưa có tài khoản quảng cáo TikTok nào.", 404)
        loi, d = "", None
        try:
            d = await _qc_cho(nguoi, request.query_params, nghiem=False)
        except NL.LoiNhap as e:
            loi = str(e)
        except LoiKho:
            loi = "Chưa đọc được số quảng cáo (kho chưa có bảng TikTok Ads)."
        dai = await _dai_qc(la_quan_tri=nguoi["la_quan_tri"])
        dong_bo = max((x["dong_bo_luc"] for x in dai if x.get("dong_bo_luc")), default=None)
        ctx: dict = {"dai_qc": dai, "duong_ve": "/quang-cao"}
        if d:
            b = d["bang"]
            # Liên kết giữ mọi bộ lọc; KHÔNG giữ trang (tc / ta) — đổi lọc / xếp là về trang 1. Thanh
            # trang tự thêm trang của mình + giữ trang của bảng kia.
            loc = {"ben": d["ben"], "nen_tang": d["nen_tang"], "tk": d["tk_ds"], "tu": d["tu"],
                   "den": d["den"], "sap": d["sap"], "tim": b["tim"], "cd": b["cd"],
                   "chieu": "tang" if b["chieu"] == "tang" else ""}
            hq = _hom_nay() - datetime.timedelta(days=1)
            chinh, phu = QC.chon_kpi(d["xem_tien"])

            def url_trang(cap: str, so: int, loc=loc, b=b) -> str:
                tc = so if cap == "campaign" else b["trang_campaign"]
                ta = so if cap == "ad" else b["trang_ad"]
                return _url("/quang-cao", **{**loc, "tc": tc if tc > 1 else "",
                                             "ta": ta if ta > 1 else ""}) + "#top"
            ctx |= {"kpi_chinh": [_o_kpi(d, k) for k in chinh], "kpi_phu": [_o_kpi(d, k) for k in phu],
                   "du_lieu_bd": _bd_qc(d), "url_cho": lambda **kw: _url("/quang-cao",
                                                                       **{**loc, **kw}),
                   "hom_qua": hq.isoformat(),
                   "nhanh": {n: (hq - datetime.timedelta(days=n - 1)).isoformat()
                             for n in (7, 30, 90)},
                   "sap_xep": [(k, t) for k, t in QC.SAP_BANG.items()
                               if d["xem_tien"] or k not in QC.SAP_BANG_TIEN],
                   "o_trang": QC.o_trang, "url_trang": url_trang}
        ctx["sheet_ds"] = await _ds_sheet(nguoi["email"])
        if d:
            ctx["sheet_so_ngay"] = (datetime.date.fromisoformat(d["den"])
                                    - datetime.date.fromisoformat(d["tu"])).days + 1
        return _trang(request, "quang_cao.html", nguoi, "quang_cao", d=d, loi_qc=loi,
                      dong_bo_luc=dong_bo, TEN_CHIEU=QC.TEN_CHIEU, CHIEU=QC.CHIEU_TAT_CA,
                      TEN_NEN_TANG_QC=QC.TEN_NEN_TANG_QC, SHEET_TRAN_DONG=KS.TRAN_DONG,
                      SHEET_TRAN_GIO=KS.TRAN_GIO, SAP_BANG=QC.SAP_BANG, TIM_TOI_DA=QC.TIM_TOI_DA,
                      NGUONG_TI_LE=QC.NGUONG_TI_LE, **ctx)

    # ─── xuất Lark Sheet (20/10/2026, chủ dự án): CHỈ quản trị viên. Dashboard chỉ GHI yêu cầu
    # (`kho_sheet_qc.tao`, RLS theo email phiên); bộ nghe qc-sheet-nghe của Mark (app Lark của Mark)
    # dựng Sheet, chia sẻ quyền xem, nhắn link. Tiến trình web không gọi Lark, không cầm token nào. ───
    _NHAN_SHEET = {"cho": "Đang chờ", "dang_tao": "Đang tạo", "xong": "Xong", "loi": "Lỗi",
                   "qua_han": "Quá hạn"}

    def _o_sheet(r: dict) -> dict:
        tt = KS.hien_trang(r)
        tu, den = r.get("tu"), r.get("den")
        ds = list(r.get("tk_ds") or [])
        pv = (f"{QC.TEN_NEN_TANG_QC.get(r.get('nen_tang'), 'TikTok + Meta')} · "
              f"{'Tất cả bên' if r.get('ben') == QC.TAT_CA else ('Chưa gán bên' if r.get('ben') == QC.CHUA_GAN else str(r.get('ben') or '').upper())}"
              + (f" · {len(ds)} tài khoản" if len(ds) > 1 else
                 (f" · {ds[0] if ds else r['tk']}" if ds or r.get("tk") else ""))
              + (f" · tìm “{r['tim']}”" if r.get("tim") else "")
              + (f" · chiến dịch {r['cd']}" if r.get("cd") else "")
              + (f" · {tu:%d/%m}–{den:%d/%m/%Y}" if isinstance(tu, datetime.date)
                 and isinstance(den, datetime.date) else ""))
        sd = r.get("so_dong") or {}
        cat = (int(sd.get("tong_quang_cao") or 0) > int(sd.get("quang_cao") or 0)
               or int(sd.get("tong_chien_dich") or 0) > int(sd.get("chien_dich") or 0))
        return {"id": r.get("id"), "trang_thai": tt, "nhan": _NHAN_SHEET.get(tt, tt),
                "ten": r.get("tieu_de") or pv, "pham_vi": pv,
                "url": KS.link_lark(r.get("sheet_url")) if tt == "xong" else "",
                "loi": (r.get("loi") or ("Dịch vụ tạo Sheet chưa nhận yêu cầu — bấm tạo lại sau ít "
                                         "phút." if tt == "qua_han" else "")),
                "luc": gio_vn(r.get("tao_luc")),
                "so_dong": (f"{so_vn(sd.get('ngay', 0))} dòng theo ngày · "
                            f"{so_vn(sd.get('chien_dich', 0))} chiến dịch · "
                            f"{so_vn(sd.get('quang_cao', 0))} quảng cáo" + (" (đã cắt)" if cat else ""))
                if tt == "xong" and sd else "",
                "dang": tt in ("cho", "dang_tao")}

    async def _ds_sheet(email: str) -> list[dict]:
        try:
            return [_o_sheet(r) for r in await _k(app.state.kho_sheet.gan_day, email, 5)]
        except (LoiKho, LoiDuLieu) as e:
            log.warning("đọc yêu cầu Sheet lỗi: %s", type(e).__name__)
            return []

    @app.get("/api/qc/sheet")
    async def api_qc_sheet(request: Request):
        nguoi = await _nguoi(request)
        if not nguoi["la_quan_tri"]:
            return JSONResponse({"loi": "Không có quyền."}, status_code=404)
        ds = await _ds_sheet(nguoi["email"])
        return JSONResponse({"ds": ds, "dang": any(x["dang"] for x in ds)})

    @app.post("/quang-cao/tao-sheet")
    async def quang_cao_tao_sheet(request: Request):
        """"Xuất Lark Sheet theo bộ lọc này" (22/10/2026: một chỗ, trong mục "Chiến dịch và quảng
        cáo"). Phạm vi kiểm lại ở máy chủ bằng đúng luật trang (`quang_cao.tk_xuat`, mọi mã tài khoản
        đã chọn phải trong phạm vi) + bộ lọc bảng qua `quang_cao.loc_bang` — bộ nghe của Mark kiểm
        lại lần nữa trước khi đọc số."""
        nguoi, form = await _sua(request, can_quan_ly=False)
        if not nguoi["la_quan_tri"]:
            raise _Cam("Chỉ quản trị viên tạo được Sheet quảng cáo.")
        ben = str(form.get("ben") or "")
        nen = str(form.get("nen_tang") or QC.TAT_CA)
        tk_vao = [str(x).strip() for x in form.getlist("tk") if str(x).strip()]
        tk_vao = list(dict.fromkeys(tk_vao))
        lb = QC.loc_bang(form, True)
        ve_q = {"ben": ben, "nen_tang": nen, "tk": tk_vao[:QC.TK_TOI_DA], "tu": form.get("tu"),
                "den": form.get("den"), "tim": lb["tim"], "cd": lb["cd"], "sap": lb["sap"],
                "chieu": "tang" if lb["chieu"] == "tang" else ""}
        ve = _url("/quang-cao", **ve_q) + "#sheet"
        if (not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", ben)
                or nen not in (*QC.NEN_TANG_QC, QC.TAT_CA) or len(tk_vao) > QC.TK_TOI_DA
                or any(not re.fullmatch(r"(act_)?[0-9]{1,30}", x) for x in tk_vao)):
            return _chuyen(request, ve, "loi", "Bộ lọc không hợp lệ — tải lại trang rồi thử lại.")
        try:
            tu, den = _doc_khoang(form)
        except NL.LoiNhap as e:
            return _chuyen(request, ve, "loi", str(e))
        if tu > den or (den - tu).days >= QC.XUAT_TOI_DA_NGAY:
            return _chuyen(request, ve, "loi",
                           f"Khoảng ngày phải từ 1 tới {QC.XUAT_TOI_DA_NGAY} ngày.")
        cac = list(await _k(app.state.kho_qc.cac_tk))
        ds = QC.tk_xuat(nguoi["q"], cac, ben, nen, tk_vao or None)
        if not ds:
            return _chuyen(request, ve, "loi", "Phạm vi này chưa có tài khoản quảng cáo nào.")
        if tk_vao and len(ds) != len(tk_vao):
            return _chuyen(request, ve, "loi", "Có tài khoản đã chọn không còn trong phạm vi — tải "
                           "lại trang rồi thử lại.")
        # Chọn đủ mọi tài khoản của phạm vi = không chọn (NULL: mọi tài khoản lúc dựng Sheet).
        tk_ds = [str(t["advertiser_id"]) for t in ds]
        if len(tk_ds) == len(QC.tk_xuat(nguoi["q"], cac, ben, nen)):
            tk_ds = []
        loc = {"tk_ds": tk_ds or None, "tim": lb["tim"] or None, "cd": lb["cd"] or None,
               "sap": lb["sap"], "chieu": lb["chieu"]}
        try:
            r = await _k(app.state.kho_sheet.tao, nguoi["email"], ben, nen, None, tu, den, **loc)
        except LoiDuLieu as e:
            return _chuyen(request, ve, "canh", str(e))
        except LoiKho as e:
            log.warning("ghi yêu cầu Sheet lỗi: %s", e)
            return _chuyen(request, ve, "loi", "Chưa ghi được yêu cầu — kho dữ liệu chưa sẵn sàng, "
                           "thử lại sau ít phút.")
        with contextlib.suppress(LoiKho, LoiDuLieu):
            await _k(app.state.kho.ghi_nhat_ky, nguoi["email"], KS.HANH_DONG,
                     f"sheet_qc:{r.get('id')}", {"ben": ben, "nen_tang": nen, **loc,
                                                 "tu": tu.isoformat(), "den": den.isoformat(),
                                                 "so_tai_khoan": len(ds)})
        return _chuyen(request, ve, "ok", "Đang tạo Sheet — thường xong sau 1–2 phút. Link hiện ở "
                       "mục Xuất Lark Sheet; Mark cũng nhắn bạn trên Lark.")

    # ─── thời gian thực ───
    @app.get("/su-kien")
    async def su_kien(request: Request):
        nguoi = await _nguoi(request)
        bt: BangTin = app.state.bang_tin
        q = bt.dang_ky(nguoi["email"])
        if q is None:
            return JSONResponse({"loi": "Quá nhiều kết nối — đóng bớt tab rồi tải lại trang."},
                                status_code=429)
        toi_da = app.state.sse_toi_da_su_kien
        kiem_quyen = float(app.state.sse_kiem_quyen_giay)
        het = float(nguoi["het"])
        quyen = [nguoi["q"]]          # đọc lại mỗi `kiem_quyen` giây (bị bỏ bên thì thôi nhận)

        async def duoc_nhan(du_lieu) -> bool:
            """Chỉ đẩy sự kiện của dự án người này đọc được (19/10/2026): bên của dự án đọc lại từ
            kho mỗi sự kiện (dự án vừa chuyển bên thì người bên cũ thôi nhận ngay)."""
            ma = du_lieu.get("du_an") if isinstance(du_lieu, dict) else None
            if not ma:
                return True
            try:
                d = await _k(app.state.kho.doc_du_an, str(ma))
            except LoiKho:
                return False
            return PQ.doc_duoc(quyen[0], d)

        async def dong():
            try:
                yield "retry: 5000\n\n"
                yield _sse("xin-chao", {"luc": datetime.datetime.now(VN).isoformat(
                    timespec="seconds")})
                n = 0
                lan_kiem = time.monotonic()
                while toi_da is None or n < toi_da:
                    if time.time() >= het:
                        # Phiên hết hạn: đóng luồng; trình duyệt nối lại sẽ nhận 401.
                        yield _sse("het-phien", {})
                        break
                    if time.monotonic() - lan_kiem >= kiem_quyen:
                        # Luồng mở hàng giờ: bị xoá khỏi người xem thì đóng, không đợi hết phiên.
                        lan_kiem = time.monotonic()
                        quyen[0] = PQ.chuan(await _k(app.state.kho.quyen_cua, nguoi["email"]))
                        if not PQ.co_quyen(quyen[0]):
                            yield _sse("het-quyen", {})
                            break
                    cho = max(0.05, min(15.0, kiem_quyen - (time.monotonic() - lan_kiem)))
                    try:
                        ten, du_lieu = await asyncio.wait_for(q.get(), timeout=cho)
                    except TimeoutError:
                        if await request.is_disconnected():
                            break
                        yield ": giu-ket-noi\n\n"
                        continue
                    if not await duoc_nhan(du_lieu):
                        continue
                    yield _sse(ten, du_lieu)
                    n += 1
            finally:
                bt.huy(q)
        return StreamingResponse(dong(), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no"})

    @app.post("/noi-bo/co-du-lieu")
    async def co_du_lieu(request: Request):
        """Mark (cùng VPS) báo vừa ghi xong một lượt. Chỉ nhận khi: gọi thẳng từ loopback (không
        qua Caddy — có X-Forwarded-For/Forwarded là bị đẩy qua proxy), env LANG_NGHE_BAO_KHOA
        khác rỗng và header X-Lang-Nghe-Khoa trùng (so hằng thời gian)."""
        host = request.client.host if request.client else ""
        khoa = (os.environ.get("LANG_NGHE_BAO_KHOA") or "").strip()
        gui = request.headers.get("x-lang-nghe-khoa") or ""
        qua_proxy = any(h in request.headers for h in ("x-forwarded-for", "forwarded",
                                                         "x-real-ip"))
        # Khoá báo trùng khoá phiên = ai đọc .env của Mark cũng ký được phiên: từ chối hẳn
        # (CauHinh.tu_env đã chặn lúc khởi động; đây là lớp thứ hai).
        trung_phien = hmac.compare_digest(khoa.encode(), cau_hinh.khoa_phien)
        if (host not in ("127.0.0.1", "::1") or qua_proxy or not khoa or trung_phien
                or not hmac.compare_digest(gui.encode(), khoa.encode())):
            return JSONResponse({"loi": "Từ chối."}, status_code=403)
        body = await request.body()
        if len(body) > 4096:
            return JSONResponse({"loi": "Quá lớn."}, status_code=413)
        try:
            d = json.loads(body)
            du_an, luot = str(d["du_an"]), int(d["luot"])
        except (ValueError, TypeError, KeyError):
            return JSONResponse({"loi": "Cần JSON {du_an, luot}."}, status_code=400)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,39}", du_an) or luot <= 0:
            return JSONResponse({"loi": "du_an/luot không hợp lệ."}, status_code=400)
        bao_cap_nhat(app, du_an, luot)
        return JSONResponse({"ok": True},
                            background=BackgroundTask(chay_hook, app, du_an, luot))

    return app
