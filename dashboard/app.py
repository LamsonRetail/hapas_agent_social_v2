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
from dashboard import lich_quet as LQ
from dashboard import nhap_lieu as NL
from dashboard import phan_quyen as PQ
from dashboard import trang_lich as TL
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
_CHUA_KIEM = object()

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
                       json_script=json_script, link_an_toan=NL.link_an_toan,
                       # "web" (Báo & Web) không phải nguồn theo dõi được (NL) nhưng có tên hiển thị.
                       ten_nen_tang=lambda p: NL.TEN_NEN_TANG.get(p) or CS.TEN_NEN_TANG.get(p, p),
                       ten_loai=lambda x: CS.TEN_LOAI.get(x, x))
    env.globals.update(TEN_NEN_TANG=NL.TEN_NEN_TANG, LOAI_NGUON=NL.LOAI_NGUON,
                       VAI_TRO=NL.VAI_TRO, TEN_LOAI=CS.TEN_LOAI, LICH_CHAY=LICH_CHAY,
                       ECHARTS=ECHARTS, ECHARTS_SRI=ECHARTS_SRI)
    return Jinja2Templates(env=env)


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
    q = {k: v for k, v in q.items() if v not in (None, "")}
    return duong + ("?" + urlencode(q) if q else "")


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
    return _dung_nguoi(phien["email"], q, phien["csrf"], phien["het"])


async def _doc_form(request: Request) -> dict[str, str]:
    """Biểu mẫu urlencoded (dashboard không nhận tệp) — tự đọc để khỏi cần python-multipart."""
    if not request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        raise _Cam("Biểu mẫu không hợp lệ.", 415)
    body = await request.body()
    if len(body) > 64_000:
        raise _Cam("Biểu mẫu quá lớn.", 413)
    try:
        q = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=200)
    except (UnicodeDecodeError, ValueError):
        raise _Cam("Biểu mẫu không hợp lệ.", 400) from None
    return {k: v[-1] for k, v in q.items()}


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
            danh_ba=None,
            chu_ky_kiem: float | None = CHU_KY_KIEM,
            sse_toi_da_su_kien: int | None = None,
            sse_kiem_quyen_giay: float = SSE_KIEM_QUYEN_GIAY) -> FastAPI:
    """Dựng ứng dụng. Mặc định (uvicorn --factory): kho Postgres thật, cấu hình từ env, Lark
    thật, đồng bộ BigQuery thật (`dong_bo_bq`, tự tắt khi thiếu BQ_DATASET), vòng kiểm 30 giây.

    Bộ thử truyền `kho` giả, `cau_hinh`, `lark` (LarkOAuth với httpx.MockTransport), `dong_bo`
    giả (trang_thai/chay/cai_vao không mở luồng), `chu_ky_kiem=None` (không vòng kiểm),
    `sse_toi_da_su_kien` (luồng SSE tự đóng sau N sự kiện) và `sse_kiem_quyen_giay`;
    `danh_ba` = DanhBaLark với httpx.MockTransport (mặc định: danh bạ Lark thật, cùng app)."""
    if kho is None:
        from dashboard import kho as kho_pg
        kho = kho_pg
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
        data["do_phu"] = await _do_phu(du_an["ma"])
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

    def _dong_nguoi_xem(nguoi: dict, x: dict, ben_thay: list[str], ten_ben: dict,
                        so_quan_tri: int, dang_doc: bool) -> dict:
        """Một dòng trang Người xem: quyền ở các bên NGƯỜI XEM TRANG được thấy, và các nút họ
        bấm được (cùng luật `phan_quyen` mà kho kiểm lại trong giao dịch)."""
        dich = {"la_quan_tri": bool(x.get("la_quan_tri")), "ben": dict(x.get("quyen") or {})}
        quyen_hien = []
        for b in sorted(dich["ben"]):
            if b not in ben_thay:
                continue
            try:
                PQ.kiem_xoa_quyen(nguoi["q"], nguoi["email"], dich, x["email"], b)
                xoa_duoc = True
            except PQ.LoiQuyen:
                xoa_duoc = False
            quyen_hien.append({"ma": b, "ten": ten_ben.get(b, b.upper()), "vai": dich["ben"][b],
                               "xoa_duoc": xoa_duoc})
        cuoi = dich["la_quan_tri"] and so_quan_tri <= 1
        return {**x, "o": _o_danh_ba(x, dang_doc), "quyen_hien": quyen_hien,
                "la_quan_tri": dich["la_quan_tri"], "qt_cuoi": cuoi,
                "xoa_het": nguoi["la_quan_tri"] and not cuoi}

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
        r = _trang(request, "nguoi_xem.html", nguoi, "nguoi_xem", so_quan_tri=so_qt,
                   ds=[_dong_nguoi_xem(nguoi, x, ben_thay, ten_ben, so_qt, dang_doc) for x in ds],
                   ben_ql=[{"ma": m, "ten": ten_ben.get(m, m.upper())} for m in ben_ql],
                   loc_ben=loc,
                   cac_ben=([{**b, "du_an": [d for d in du_an if d.get("don_vi") == b["ma"]]}
                             for b in cac_ben] if qt else []),
                   nhat_ky=[{**x, "chi_tiet_chu": json.dumps(x.get("chi_tiet") or {},
                                                             ensure_ascii=False,
                                                             default=str)[:400]}
                            for x in nk])
        r.background = nen
        return r

    @app.post("/nguoi-xem/them")
    async def nguoi_xem_them(request: Request):
        """Thêm / đổi quyền một người ở MỘT bên; quản trị viên tích thêm "Quản trị viên". Luật
        (quản lý chỉ thêm người Chỉ xem của bên mình…) do kho kiểm trong giao dịch — câu lỗi của
        kho hiện thẳng cho người dùng."""
        nguoi, form = await _sua(request)
        kho = app.state.kho
        try:
            e = NL.email(form.get("email"))
            ben = str(form.get("don_vi") or "").strip().lower()
            lam_qt = form.get("quan_tri") == "1"
            if lam_qt and not nguoi["la_quan_tri"]:
                raise NL.LoiNhap("Chỉ quản trị viên mới cấp quyền quản trị viên.")
            if not ben and not lam_qt:
                duoc = PQ.ben_quan_ly(nguoi["q"], [b["ma"] for b in await _cac_don_vi()])
                if len(duoc) != 1:
                    raise NL.LoiNhap("Chọn bên cho người này.")
                ben = duoc[0]
            phan = []
            if ben:
                v = NL.vai_tro(form.get("vai_tro"))
                await _k(kho.luu_quyen, nguoi["email"], e, ben, v)
                phan.append(f"{ben.upper()}: {NL.VAI_TRO[v]}")
            if lam_qt:
                await _k(kho.dat_quan_tri, nguoi["email"], e, True)
                phan.append("Quản trị viên")
        except (NL.LoiNhap, LoiDuLieu) as ex:
            return _chuyen(request, "/quan-tri", "loi", str(ex))
        # Kiểm email với danh bạ Lark: CHỈ cảnh báo, không chặn (danh bạ có thể chậm/thiếu quyền).
        tin = f"Đã lưu {e} ({' · '.join(phan)})"
        # Nhanh: chỉ tra theo email (không dò cả danh bạ). Lark không khớp enterprise_email nên
        # "khong_co" ở đây CHƯA chắc: không ghi, lượt đọc nền khi mở trang sẽ dò kỹ.
        kq = (await doc_danh_ba(app, [e], DANH_BA_THEM_GIAY, quet=False) or {}).get(e)
        if not kq:
            return _chuyen(request, "/quan-tri", "ok",
                           tin + ". Chưa kiểm được với danh bạ Lark — xem cột Trạng thái sau.")
        if kq["trang_thai"] == "khong_co":
            return _chuyen(request, "/quan-tri", "canh",
                           f"{tin}, nhưng Lark chưa khớp email này. Email công ty: dashboard "
                           "đang dò cả danh bạ — xem cột Trạng thái sau ít giây; người này "
                           "đăng nhập một lần là nhận diện chắc chắn.")
        if kq["trang_thai"] != "hoat_dong":
            return _chuyen(request, "/quan-tri", "canh",
                           f"{tin}, nhưng trên Lark: {DB.TRANG_THAI[kq['trang_thai']]} — "
                           "kiểm lại email, người này chưa đăng nhập được.")
        # 18/10/2026: trang Người xem bỏ chức danh (chủ dự án) — câu báo chỉ còn tên Lark.
        ai = kq.get("ten") or ""
        return _chuyen(request, "/quan-tri", "ok",
                       tin + (f" — {ai}" if ai else "") + ", tài khoản Lark đang hoạt động.")

    @app.post("/nguoi-xem/quan-tri")
    async def nguoi_xem_quan_tri(request: Request):
        """Bật / bỏ cờ quản trị viên (chỉ quản trị viên; không bỏ người cuối — kho kiểm)."""
        nguoi, form = await _sua(request)
        try:
            e = NL.email(form.get("email"))
            bat = form.get("bat") == "1"
            het = await _k(app.state.kho.dat_quan_tri, nguoi["email"], e, bat)
        except (NL.LoiNhap, LoiDuLieu) as ex:
            return _chuyen(request, "/quan-tri", "loi", str(ex))
        if bat:
            return _chuyen(request, "/quan-tri", "ok", f"Đã cấp quyền quản trị viên cho {e}.")
        return _chuyen(request, "/quan-tri", "ok",
                       f"Đã bỏ quyền quản trị viên của {e}"
                       + (" — không còn quyền ở bên nào nên đã xoá khỏi danh sách." if het
                          else "."))

    @app.post("/nguoi-xem/xoa")
    async def nguoi_xem_xoa(request: Request):
        """Có `don_vi`: bỏ quyền ở MỘT bên (bên khác giữ). Không có: xoá hẳn người đó (chỉ quản trị
        viên). Luật + "còn ≥ 1 quản trị viên" kho kiểm trong giao dịch có khoá bảng."""
        nguoi, form = await _sua(request)
        try:
            e = NL.email(form.get("email"))
            ben = str(form.get("don_vi") or "").strip().lower()
            if ben:
                het = await _k(app.state.kho.xoa_quyen, nguoi["email"], e, ben)
                tin = (f"Đã bỏ quyền của {e} ở bên {ben.upper()}"
                       + (" — không còn quyền ở bên nào nên đã xoá khỏi danh sách." if het
                          else "."))
            else:
                await _k(app.state.kho.xoa_nguoi_xem, nguoi["email"], e)
                tin = f"Đã xoá {e} khỏi danh sách người xem."
        except (NL.LoiNhap, LoiDuLieu) as ex:
            return _chuyen(request, "/quan-tri", "loi", str(ex))
        return _chuyen(request, "/quan-tri", "ok", tin)

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
