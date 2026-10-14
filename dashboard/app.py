"""Ứng dụng web dashboard lắng nghe `social.hapas.vn` (FastAPI + Jinja2, chạy sau Caddy).

Phạm vi (chủ dự án chốt 14/10/2026): chỉ số, dự án + nguồn + đề xuất nguồn, ngân sách theo dõi
tháng, người xem, trạng thái đồng bộ BigQuery. KHÔNG có kỹ năng, persona, công tắc năng lực, trần
mỗi lượt hay lịch chạy của Mark — những thứ đó ở console platform.

Kiểm thử được mà không cần Postgres hay mạng: `tao_app(kho=…, cau_hinh=…, lark=…, dong_bo=…)`
nhận bản giả. Chạy thật: `uvicorn --factory dashboard.app:tao_app` (đọc env, xem README.md).

Bảo vệ, đừng bỏ khi sửa:
  • Mọi trang/API trừ /suc-khoe, /dang-nhap*, /tinh/* đòi phiên đăng nhập; vai trò đọc lại từ
    `nguoi_xem` MỖI lượt (xoá người xem có hiệu lực ngay, không đợi phiên hết hạn).
  • Mọi POST sửa dữ liệu: phiên + mã CSRF + vai trò `quan_ly`, kiểm ở PHÍA MÁY CHỦ (nút bị ẩn
    trên giao diện chỉ là tiện, không phải chốt chặn).
  • Chuyển hướng chỉ tới đường dẫn tương đối (`nhap_lieu.duong_an_toan`).
  • /noi-bo/co-du-lieu chỉ nhận từ 127.0.0.1/::1, không qua proxy, đúng khoá LANG_NGHE_BAO_KHOA.
"""
from __future__ import annotations

import asyncio
import collections
import contextlib
import datetime
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
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders

from dashboard import chi_phi as CP
from dashboard import chi_so as CS
from dashboard import dang_nhap as DN
from dashboard import nhap_lieu as NL
from dashboard.kho import LoiDuLieu, LoiKho

THU_MUC = Path(__file__).resolve().parent
VN = CS.VN
# ECharts 5.5.1 phục vụ TỪ CHÍNH dashboard (không CDN: CSP chỉ cho script 'self'). Tệp lấy từ
# https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js, 1.030.855 byte, sha256
# e84270bd0cd5bdf60fefc26d00c2a391cb2e81f4d26a7a9ee16185a54773a3cf — có bài thử canh hash; thay tệp
# thì sửa cả hai dòng dưới (trình duyệt từ chối chạy tệp lệch `integrity`).
ECHARTS = "/tinh/echarts.min.js"
ECHARTS_SRI = "sha256-6EJwvQzVvfYP78JtAMKjkcsugfTSanqe4WGFpUdzo88="
LICH_CHAY = ("Lịch quét không đặt ở đây: đặt trên console platform — tab Lịch chạy, kiểu Giao "
             "việc, nội dung /theodoi <mã dự án>.")
CHU_KY_KIEM = 30.0          # giây; vòng kiểm lượt quét mới khi Mark không báo được
SSE_TOI_DA_KET_NOI = 200    # trình duyệt mở cùng lúc; quá thì từ chối, khỏi cạn bộ nhớ
SSE_MOI_EMAIL = 5           # mỗi người tối đa ngần này tab nghe sự kiện
SSE_KIEM_QUYEN_GIAY = 300.0  # luồng SSE đọc lại vai trò mỗi 5 phút; bị xoá khỏi người xem -> đóng
LUOT_MOI_TRANG = 20
KHOANG_TOI_DA_NGAY = 400
TINH_SONG_SONG = 2          # lượt tính /api/chi-so chạy cùng lúc (MemoryMax 512M)
NHO_CHI_SO_GIAY = 60.0      # kết quả /api/chi-so giữ lại chừng này giây (khoá có mốc lượt quét)
NHO_CHI_SO_TOI_DA = 64
NHO_DONG_TOI_DA = 4         # bộ dòng (bài/bình luận) giữ cho khung chi tiết — mỗi bộ tới 20k dòng
SUC_KHOE_GIAY = 15.0        # /suc-khoe công khai: không mở kết nối DB mỗi lần gọi
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

        async def gui(msg):
            if msg["type"] == "http.response.start":
                h = MutableHeaders(scope=msg)
                for k, v in _TIEU_DE_AN_TOAN.items():
                    h.setdefault(k, v)
                if not tinh:
                    h.setdefault("cache-control", "no-store")   # trang có dữ liệu nội bộ
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


def _tao_mau() -> Jinja2Templates:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(THU_MUC / "templates")),
                             autoescape=True, trim_blocks=True, lstrip_blocks=True)
    env.filters.update(so_vn=so_vn, pt_vn=pt_vn, usd_vn=usd_vn, gio_vn=gio_vn,
                       json_script=json_script, link_an_toan=NL.link_an_toan,
                       ten_nen_tang=lambda p: NL.TEN_NEN_TANG.get(p, p),
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


async def _nguoi(request: Request) -> dict:
    cfg = request.app.state.cau_hinh
    phien = DN.doc_phien(request.cookies.get(DN.COOKIE_PHIEN), cfg.khoa_phien)
    if not phien:
        raise _ChuaDangNhap()
    vai = await _k(request.app.state.kho.vai_tro, phien["email"])
    if vai not in NL.VAI_TRO:
        raise _Cam(f"Bạn chưa có quyền xem — nhờ người quản lý thêm email {phien['email']}.")
    return {"email": phien["email"], "vai_tro": vai, "csrf": phien["csrf"], "het": phien["het"]}


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
    """Chốt chặn của MỌI POST: phiên -> nguồn gốc -> CSRF -> vai trò. -> (người, biểu mẫu)."""
    nguoi = await _nguoi(request)
    if not _cung_nguon_goc(request):
        raise _Cam("Yêu cầu không đến từ trang dashboard.")
    form = await _doc_form(request)
    if not DN.csrf_dung(nguoi, form.get("csrf")):
        raise _Cam("Biểu mẫu đã hết hạn hoặc không hợp lệ — tải lại trang rồi thử lại.")
    if can_quan_ly and nguoi["vai_tro"] != "quan_ly":
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


# ───────────────────────────── nhà máy ứng dụng ─────────────────────────────
def tao_app(kho=None, *, cau_hinh: DN.CauHinh | None = None, lark=None, dong_bo=None,
            chu_ky_kiem: float | None = CHU_KY_KIEM,
            sse_toi_da_su_kien: int | None = None,
            sse_kiem_quyen_giay: float = SSE_KIEM_QUYEN_GIAY) -> FastAPI:
    """Dựng ứng dụng. Mặc định (uvicorn --factory): kho Postgres thật, cấu hình từ env, Lark
    thật, đồng bộ BigQuery thật (`dong_bo_bq`, tự tắt khi thiếu BQ_DATASET), vòng kiểm 30 giây.

    Bộ thử truyền `kho` giả, `cau_hinh`, `lark` (LarkOAuth với httpx.MockTransport), `dong_bo`
    giả (trang_thai/chay/cai_vao không mở luồng), `chu_ky_kiem=None` (không vòng kiểm),
    `sse_toi_da_su_kien` (luồng SSE tự đóng sau N sự kiện) và `sse_kiem_quyen_giay`."""
    if kho is None:
        from dashboard import kho as kho_pg
        kho = kho_pg
    cau_hinh = cau_hinh or DN.CauHinh.tu_env()
    lark = lark or DN.LarkOAuth(cau_hinh)
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

    app = FastAPI(title="Lắng nghe MXH — HAPAS", docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=vong_doi)
    app.state.kho = kho
    app.state.cau_hinh = cau_hinh
    app.state.lark = lark
    app.state.dong_bo = dong_bo
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
    app.state.nho_dong = collections.OrderedDict()
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
        if await _k(app.state.kho.vai_tro, email) not in NL.VAI_TRO:
            return loi(f"Bạn chưa có quyền xem — nhờ người quản lý thêm email {email}.", 403)
        try:
            await _k(app.state.kho.ghi_dang_nhap_lan_dau, email, nd.get("open_id") or "")
        except (LoiKho, LoiDuLieu) as e:   # chỉ là nhật ký — không chặn đăng nhập
            log.warning("không ghi được lần đăng nhập đầu: %s", type(e).__name__)
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

    # ─── chỉ số ───
    @app.get("/")
    async def trang_chi_so(request: Request):
        nguoi = await _nguoi(request)
        ds = await _k(app.state.kho.cac_du_an)
        q = request.query_params
        du_an = _chon_du_an(ds, q.get("du_an"))
        loi = ""
        try:
            tu, den = _doc_khoang(q)
        except NL.LoiNhap as e:
            loi = str(e)
            tu, den = _doc_khoang({})
        nen_tang = q.get("nen_tang") if q.get("nen_tang") in NL.NEN_TANG else ""
        loai = q.get("loai") if q.get("loai") in CS.TEN_LOAI else ""
        loc = {"du_an": du_an["ma"] if du_an else "", "tu": tu.isoformat(),
               "den": den.isoformat(), "nen_tang": nen_tang, "loai": loai}
        return _trang(request, "chi_so.html", nguoi, "chi_so", du_an_ds=ds, du_an=du_an,
                      loc=loc, loi_loc=loi, chua_tron=den >= _hom_nay())

    async def _loc_api(request: Request):
        """Bộ lọc chung của các API số liệu. -> (dự án, từ, đến, nền tảng, loại) hoặc
        JSONResponse lỗi."""
        await _nguoi(request)
        q = request.query_params
        du_an = await _k(app.state.kho.doc_du_an, q.get("du_an") or "")
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
        nen_tang = q.get("nen_tang") or None
        loai = q.get("loai") or None
        if (nen_tang and nen_tang not in NL.NEN_TANG) or (loai and loai not in CS.TEN_LOAI):
            return JSONResponse({"loi": "Bộ lọc không hợp lệ."}, status_code=400)
        return du_an, tu, den, nen_tang, loai

    def _moc_ngay(tu: datetime.date, den: datetime.date) -> tuple:
        return (datetime.datetime.combine(tu, datetime.time(0), VN),
                datetime.datetime.combine(den + datetime.timedelta(days=1), datetime.time(0), VN))

    async def _dong_nho(loai_dong: str, du_an: str, tu, den):
        """Dòng bài / bình luận của [tu, den] cho khung chi tiết, nhớ `NHO_CHI_SO_GIAY` giây
        theo mốc lượt quét mới nhất (bấm liên tiếp nhiều cột không đọc lại kho mỗi lần).
        -> None khi máy chủ đang bận."""
        moc = await _k(app.state.kho.luot_xong_moi_nhat) or {}
        khoa = (loai_dong, du_an, tu, den, moc.get("id"), str(moc.get("ket_thuc")))
        nho = app.state.nho_dong
        x = nho.get(khoa)
        if x and time.monotonic() - x[0] < NHO_CHI_SO_GIAY:
            return x[1]
        if not app.state.ban.acquire(blocking=False):
            return None
        try:
            bd, kt = _moc_ngay(tu, den)
            fn = (app.state.kho.bai_trong_khoang if loai_dong == "bai"
                  else app.state.kho.binh_luan_trong_khoang)
            rows = (await _k(fn, du_an, bd, kt))["rows"]
        finally:
            app.state.ban.release()
        nho[khoa] = (time.monotonic(), rows)
        while len(nho) > NHO_DONG_TOI_DA:
            nho.popitem(last=False)
        return rows

    def _dk_chi_tiet(q) -> dict:
        """Điều kiện của khung chi tiết (cột/điểm vừa bấm). Ném NL.LoiNhap khi rác."""
        dk: dict = {}
        for k in ("ngay_tu", "ngay_den"):
            if q.get(k):
                dk[k] = NL.ngay(q.get(k), _hom_nay())
        s = q.get("sac_thai") or ""
        if s:
            if s not in (*CS.SAC_THAI, CS.CHUA, "kênh nhà"):
                raise NL.LoiNhap("Sắc thái không hợp lệ.")
            dk["sac_thai"] = s
        for k, dai in (("chu_de", 100), ("nguon", 300), ("cum", 100)):
            v = (q.get(k) or "").strip()
            if v:
                if len(v) > dai:
                    raise NL.LoiNhap("Điều kiện quá dài.")
                dk[k] = v
        return dk

    def _ban():
        return JSONResponse({"loi": "Máy chủ đang bận — thử lại sau ít giây."},
                            status_code=503, headers={"Retry-After": "5"})

    @app.get("/api/bai")
    async def api_bai(request: Request):
        x = await _loc_api(request)
        if isinstance(x, JSONResponse):
            return x
        du_an, tu, den, nen_tang, loai = x
        q = request.query_params
        try:
            dk = _dk_chi_tiet(q)
        except NL.LoiNhap as e:
            return JSONResponse({"loi": str(e)}, status_code=400)
        rows = await _dong_nho("bai", du_an["ma"], tu, den)
        if rows is None:
            return _ban()
        kq = await _k(CS.chi_tiet_bai, rows, tu, den, trang=_so_trang(q.get("trang")),
                      **{"nen_tang": nen_tang, "loai_nguon": loai, **dk})
        return JSONResponse(kq)

    @app.get("/api/binh-luan")
    async def api_binh_luan(request: Request):
        x = await _loc_api(request)
        if isinstance(x, JSONResponse):
            return x
        du_an, tu, den, nen_tang, loai = x
        q = request.query_params
        khoa = (q.get("khoa") or "").strip()
        if khoa:
            if len(khoa) > 200:
                return JSONResponse({"loi": "Khoá bài không hợp lệ."}, status_code=400)
            ds = await _k(app.state.kho.binh_luan_cua_bai, du_an["ma"], khoa)
            return JSONResponse({"tong": len(ds), "trang": 1, "so_trang": 1,
                                 "binh_luan": [CS.the_bl(c) for c in ds]})
        try:
            dk = _dk_chi_tiet(q)
        except NL.LoiNhap as e:
            return JSONResponse({"loi": str(e)}, status_code=400)
        if dk.get("sac_thai") == "kênh nhà" or dk.get("nguon") or dk.get("cum"):
            return JSONResponse({"loi": "Điều kiện không hợp lệ cho bình luận."}, status_code=400)
        rows = await _dong_nho("bl", du_an["ma"], tu, den)
        if rows is None:
            return _ban()
        kq = await _k(CS.chi_tiet_bl, rows, tu, den, trang=_so_trang(q.get("trang")),
                      **{"nen_tang": nen_tang, "loai_nguon": loai, **dk})
        return JSONResponse(kq)

    @app.get("/api/chi-so")
    async def api_chi_so(request: Request):
        x = await _loc_api(request)
        if isinstance(x, JSONResponse):
            return x
        du_an, tu, den, nen_tang, loai = x
        hom_nay = _hom_nay()
        # Bộ nhớ đệm: khoá gồm mốc lượt quét vừa xong — có lượt mới là tính lại ngay, không có
        # thì nhiều người mở cùng bộ lọc trong NHO_CHI_SO_GIAY giây chỉ tốn một lần đọc kho.
        moc = await _k(app.state.kho.luot_xong_moi_nhat) or {}
        khoa = (du_an["ma"], tu, den, nen_tang, loai, hom_nay, tuple(du_an["tu_khoa"] or []),
                moc.get("id"), str(moc.get("ket_thuc")))
        nho = app.state.nho_chi_so
        x = nho.get(khoa)
        if x and time.monotonic() - x[0] < NHO_CHI_SO_GIAY:
            data = dict(x[1])
        else:
            if not app.state.ban.acquire(blocking=False):
                return JSONResponse({"loi": "Máy chủ đang bận tính số liệu — thử lại sau ít giây."},
                                    status_code=503, headers={"Retry-After": "5"})
            try:
                tu_truoc, _ = CS.khoang_truoc(tu, den)
                bat_dau = datetime.datetime.combine(tu_truoc, datetime.time(0), VN)
                ket_thuc = datetime.datetime.combine(den + datetime.timedelta(days=1),
                                                     datetime.time(0), VN)
                kq = await _k(app.state.kho.bai_trong_khoang, du_an["ma"], bat_dau, ket_thuc)
                data = await _k(CS.tong_hop, kq["rows"], tu, den,
                                tu_khoa_du_an=du_an["tu_khoa"] or [], nen_tang=nen_tang,
                                loai_nguon=loai, hom_nay=hom_nay)
                data["bi_cat"] = bool(kq["bi_cat"])
                del kq
                bd, kt = _moc_ngay(tu, den)
                kb = await _k(app.state.kho.binh_luan_trong_khoang, du_an["ma"], bd, kt)
                data["binh_luan_da_cao"] = await _k(CS.tong_hop_bl, kb["rows"], tu, den,
                                                    nen_tang=nen_tang, loai_nguon=loai,
                                                    hom_nay=hom_nay)
                data["bl_bi_cat"] = bool(kb["bi_cat"])
                del kb
            finally:
                app.state.ban.release()
            nho[khoa] = (time.monotonic(), data)
            while len(nho) > NHO_CHI_SO_TOI_DA:
                nho.popitem(last=False)
            data = dict(data)
        luot, _ = await _k(app.state.kho.cac_luot, du_an["ma"], 1, 1)
        data.update(du_an={"ma": du_an["ma"], "ten": du_an["ten"]},
                    ngay_cuoi_chua_tron=den >= hom_nay,
                    luot_gan_nhat=_luot_json(luot[0] if luot else None),
                    cap_nhat_luc=datetime.datetime.now(VN).isoformat(timespec="seconds"))
        return JSONResponse(data)

    # ─── dự án + nguồn + đề xuất ───
    @app.get("/nguon")
    async def trang_nguon(request: Request):
        nguoi = await _nguoi(request)
        ds = await _k(app.state.kho.cac_du_an)
        du_an = _chon_du_an(ds, request.query_params.get("du_an"))
        nguon = await _k(app.state.kho.cac_nguon, du_an["ma"]) if du_an else []
        de_xuat = await _k(app.state.kho.cac_de_xuat, du_an["ma"]) if du_an else []
        du_an = an_chi_tiet(nguoi, [du_an], ("sua_boi",))[0] if du_an else None
        # Ước tính tiền/tháng mỗi nguồn theo cấu hình (cùng công thức trang Ngân sách); trình
        # duyệt tính lại ngay khi sửa số bài/chu kỳ bằng chính các hằng số này (`chi_phi_js`).
        nguon = [{**n, "usd_thang": CP.chi_phi_thang_nguon(n)} for n in nguon]
        return _trang(request, "nguon.html", nguoi, "nguon", du_an_ds=ds, du_an=du_an,
                      nguon=an_chi_tiet(nguoi, nguon, ("them_boi",), ("loi_cuoi",)),
                      de_xuat=an_chi_tiet(nguoi, de_xuat, ("xu_ly_boi",)),
                      chi_phi_js=CP.hang_so_cho_trinh_duyet(),
                      phi_khoi_dong={p: CP.phi_khoi_dong_ngay(p) for p in NL.NEN_TANG})

    @app.post("/du-an/them")
    async def du_an_them(request: Request):
        nguoi, form = await _sua(request)
        try:
            d = NL.du_an(form, moi=True)
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
            d = NL.du_an(form, moi=False)
            await _k(app.state.kho.sua_du_an, nguoi["email"], ma, d)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", "Đã lưu dự án.")

    async def _du_an_phai_co(ma: str) -> dict:
        d = await _k(app.state.kho.doc_du_an, ma)
        if not d:
            raise NL.LoiNhap("Không có dự án này.")
        return d

    @app.post("/nguon/them")
    async def nguon_them(request: Request):
        nguoi, form = await _sua(request)
        ma = str(form.get("du_an") or "")
        ve = _url("/nguon", du_an=ma)
        try:
            await _du_an_phai_co(ma)
            d = NL.nguon(form)
            await _k(app.state.kho.them_nguon, nguoi["email"], ma, d)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok",
                       f"Đã thêm nguồn {NL.TEN_NEN_TANG[d['nen_tang']]} {d['dinh_danh']}.")

    async def _nguon_phai_co(nid: int) -> dict:
        n = await _k(app.state.kho.doc_nguon, nid)
        if not n:
            raise _Cam("Không còn nguồn này.", 404)
        return n

    @app.post("/nguon/{nid}/sua")
    async def nguon_sua(request: Request, nid: int):
        nguoi, form = await _sua(request)
        n = await _nguon_phai_co(nid)
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
        n = await _nguon_phai_co(nid)
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
        n = await _nguon_phai_co(nid)
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
        ve = _url("/nguon", du_an=x["du_an"])
        if x["trang_thai"] != "cho":
            return _chuyen(request, ve, "loi", "Đề xuất này đã được xử lý.")
        try:
            co_ban = {"nen_tang": x["nen_tang"], "ten": x.get("ten") or "",
                      "loai": form.get("loai") or "khac",
                      "chu_ky_ngay": form.get("chu_ky_ngay") or 1,
                      "so_bai_moi_lan": form.get("so_bai_moi_lan") or 5}
            try:
                d = NL.nguon({**co_ban, "dinh_danh": x["dinh_danh"]})
            except NL.LoiNhap:
                if not x.get("link"):
                    raise
                d = NL.nguon({**co_ban, "dinh_danh": x["link"]})
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
        ve = _url("/nguon", du_an=x["du_an"])
        try:
            await _k(app.state.kho.tu_choi_de_xuat, nguoi["email"], did)
        except LoiDuLieu as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", f"Đã từ chối đề xuất {x['dinh_danh']}.")

    # ─── ngân sách ───
    @app.get("/ngan-sach")
    async def trang_ngan_sach(request: Request):
        nguoi = await _nguoi(request)
        ds = await _k(app.state.kho.cac_du_an)
        da_tieu = await _k(app.state.kho.da_tieu_thang)
        du_an = _chon_du_an(ds, request.query_params.get("du_an"))
        trang = _so_trang(request.query_params.get("trang"))
        luot, tong = (await _k(app.state.kho.cac_luot, du_an["ma"], trang, LUOT_MOI_TRANG)
                      if du_an else ([], 0))
        so_trang = max(1, -(-tong // LUOT_MOI_TRANG))
        bay_gio = _bay_gio()
        dong = []
        for d in ds:
            tran_du_an = float(d.get("tran_usd_thang") or 0)
            tieu = float(da_tieu.get(d["ma"], 0.0))
            tran_pf = await _k(app.state.kho.tran_platform, d["ma"])
            nguon = await _k(app.state.kho.cac_nguon, d["ma"])
            db = CP.du_bao(nguon, tieu, tran_du_an, tran_pf, bay_gio)
            tran = db["tran"]
            bl_uoc = (CP.uoc_binh_luan_luot(int(d.get("bl_so_bai") or 0), int(d.get("bl_moi_bai") or 20))
                      if d.get("bl_bat", True) else 0.0)
            dong.append({**d, "da_tieu": tieu, "con_lai": max(0.0, tran - tieu), "du_bao": db,
                         "bl_uoc": bl_uoc,
                         "pt": min(100.0, 100.0 * tieu / tran) if tran else (100.0 if tieu else 0),
                         "pt_du_bao": (min(100.0, 100.0 * db["du_bao_thang"] / tran) if tran
                                       else (100.0 if db["du_bao_thang"] else 0))})
        return _trang(request, "ngan_sach.html", nguoi, "ngan_sach",
                      dong=an_chi_tiet(nguoi, dong, ("sua_boi",)), du_an=du_an,
                      luot=an_chi_tiet(nguoi, luot, ("ghi_chu",), ("loi",)), tong=tong,
                      trang=trang, so_trang=so_trang, thang=bay_gio.strftime("%m/%Y"),
                      so_ngay_thang=CP.so_ngay_thang(bay_gio))

    @app.post("/ngan-sach/{ma}")
    async def ngan_sach_luu(request: Request, ma: str):
        nguoi, form = await _sua(request)
        ve = _url("/ngan-sach", du_an=ma)
        try:
            await _du_an_phai_co(ma)
            usd = NL.tran_usd(form.get("tran_usd_thang"))
            await _k(app.state.kho.dat_tran_thang, nguoi["email"], ma, usd)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok", f"Đã đặt trần tháng {usd_vn(usd)} USD cho dự án {ma}.")

    @app.post("/ngan-sach/{ma}/binh-luan")
    async def ngan_sach_binh_luan(request: Request, ma: str):
        nguoi, form = await _sua(request)
        ve = _url("/ngan-sach", du_an=ma)
        try:
            await _du_an_phai_co(ma)
            bat = form.get("bl_bat") == "1"
            so_bai = NL.so_nguyen(form.get("bl_so_bai"), "Số bài cào bình luận mỗi lượt", 0, 100)
            moi_bai = NL.so_nguyen(form.get("bl_moi_bai"), "Số bình luận mỗi bài", 5, 200)
            await _k(app.state.kho.dat_binh_luan, nguoi["email"], ma, bat, so_bai, moi_bai)
        except (NL.LoiNhap, LoiDuLieu) as e:
            return _chuyen(request, ve, "loi", str(e))
        return _chuyen(request, ve, "ok",
                       (f"Đã lưu: cào bình luận tối đa {so_bai} bài × {moi_bai} bình luận mỗi "
                        f"lượt (tối đa ≈ {usd_vn(CP.uoc_binh_luan_luot(so_bai, moi_bai))} USD/lượt)."
                        if bat else "Đã tắt cào bình luận."))

    # ─── người xem ───
    async def _chi_quan_ly(request: Request) -> dict:
        nguoi = await _nguoi(request)
        if nguoi["vai_tro"] != "quan_ly":
            raise _Cam("Trang này chỉ dành cho người quản lý.")
        return nguoi

    @app.get("/nguoi-xem")
    async def trang_nguoi_xem(request: Request):
        nguoi = await _chi_quan_ly(request)
        ds = await _k(app.state.kho.cac_nguoi_xem)
        nk = await _k(app.state.kho.nhat_ky, 100)
        so_ql = sum(1 for x in ds if x["vai_tro"] == "quan_ly")
        return _trang(request, "nguoi_xem.html", nguoi, "nguoi_xem", ds=ds, so_quan_ly=so_ql,
                      nhat_ky=[{**x, "chi_tiet_chu": json.dumps(x.get("chi_tiet") or {},
                                                                ensure_ascii=False,
                                                                default=str)[:400]}
                               for x in nk])

    async def _la_quan_ly_cuoi(email: str) -> bool:
        """Kiểm ở tầng app cho câu báo dễ hiểu; kho kiểm lại trong giao dịch có khoá bảng."""
        ds = await _k(app.state.kho.cac_nguoi_xem)
        ql = [x["email"] for x in ds if x["vai_tro"] == "quan_ly"]
        return ql == [email]

    @app.post("/nguoi-xem/them")
    async def nguoi_xem_them(request: Request):
        nguoi, form = await _sua(request)
        try:
            e = NL.email(form.get("email"))
            v = NL.vai_tro(form.get("vai_tro"))
            if v != "quan_ly" and await _la_quan_ly_cuoi(e):
                raise NL.LoiNhap("Không hạ quyền người quản lý cuối cùng — thêm quản lý khác trước.")
            await _k(app.state.kho.luu_nguoi_xem, nguoi["email"], e, v)
        except (NL.LoiNhap, LoiDuLieu) as ex:
            return _chuyen(request, "/nguoi-xem", "loi", str(ex))
        return _chuyen(request, "/nguoi-xem", "ok", f"Đã lưu {e} ({NL.VAI_TRO[v]}).")

    @app.post("/nguoi-xem/xoa")
    async def nguoi_xem_xoa(request: Request):
        nguoi, form = await _sua(request)
        try:
            e = NL.email(form.get("email"))
            if await _la_quan_ly_cuoi(e):
                raise NL.LoiNhap("Không xoá được người quản lý cuối cùng — thêm quản lý khác trước.")
            await _k(app.state.kho.xoa_nguoi_xem, nguoi["email"], e)
        except (NL.LoiNhap, LoiDuLieu) as ex:
            return _chuyen(request, "/nguoi-xem", "loi", str(ex))
        return _chuyen(request, "/nguoi-xem", "ok", f"Đã xoá {e} khỏi danh sách người xem.")

    # ─── BigQuery ───
    @app.get("/bigquery")
    async def trang_bigquery(request: Request):
        nguoi = await _nguoi(request)
        loi = ""
        try:
            tt = await _k(app.state.dong_bo.trang_thai)
        except Exception as e:  # noqa: BLE001 — trang vẫn hiện, chỉ báo chưa đọc được
            loi = f"Chưa đọc được trạng thái đồng bộ ({type(e).__name__})."
            tt = {"dataset": "", "da_bat": False, "bang": []}
        tt = {**tt, "bang": an_chi_tiet(nguoi, list(tt.get("bang") or []), (), ("loi",))}
        return _trang(request, "bigquery.html", nguoi, "bigquery", tt=tt, loi_tt=loi)

    @app.post("/bigquery/dong-bo")
    async def bigquery_dong_bo(request: Request):
        nguoi, _ = await _sua(request)
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
                        if await _k(app.state.kho.vai_tro, nguoi["email"]) not in NL.VAI_TRO:
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
