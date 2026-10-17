"""Đăng nhập bằng Lark (OAuth, bản quốc tế) + phiên cookie ký HMAC + CSRF. Chỉ thư viện chuẩn
và httpx — không phụ thuộc itsdangerous (venv thử không có).

Luồng: /dang-nhap/lark -> trang uỷ quyền của Lark (state đã ký, hết hạn 10 phút, buộc vào
cookie nonce của chính trình duyệt — chống "login CSRF") -> /dang-nhap/xong?code=&state= ->
đổi code lấy user_access_token -> đọc người dùng -> `tenant_key` phải là tổ chức Lark của HAPAS
(DASH_LARK_TENANT_KEY; app Lark công khai thì tài khoản tổ chức khác cũng đăng nhập được, và
`email` của họ do họ tự khai) -> email phải có trong `nguoi_xem`.

Phiên: cookie `ln_phien` = base64url(JSON).base64url(HMAC-SHA256), hết hạn 8 giờ, HttpOnly,
Secure, SameSite=Lax. Vai trò KHÔNG nằm trong cookie: mỗi lượt đọc lại `nguoi_xem`, để xoá người
xem / hạ quyền có hiệu lực ngay. Mỗi phiên một mã CSRF ngẫu nhiên, biểu mẫu POST nào cũng phải
gửi lại đúng mã đó (so bằng hmac.compare_digest).

Khoá con tách theo mục đích (phiên / state / thông báo): chữ ký của loại này không dùng được
cho loại kia dù cùng `DASH_SESSION_KEY`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

# ─── Endpoint Lark — đối chiếu tài liệu open.larksuite.com ngày 14/10/2026 ───
#  • Uỷ quyền: GET https://accounts.larksuite.com/open-apis/authen/v1/authorize
#    tham số client_id (= App ID; tài liệu mới KHÔNG dùng app_id), redirect_uri, scope, state.
#    (common-capabilities/sso/api/obtain-oauth-code)
#  • Đổi code: POST https://open.larksuite.com/open-apis/authen/v2/oauth/token, JSON
#    grant_type=authorization_code, client_id, client_secret, code, redirect_uri; trả PHẲNG
#    {code: 0, access_token, …} (authentication-management/access-token/get-user-access-token)
#  • Người dùng: GET https://open.larksuite.com/open-apis/authen/v1/user_info, Bearer
#    user_access_token; trả {code, msg, data: {email, enterprise_email, …}}. `email` cần scope
#    contact:user.email:readonly, `enterprise_email` cần contact:user.employee:readonly.
#  Lark đổi đường dẫn thì sửa ĐÚNG ở đây (hoặc qua env LARK_OPEN_BASE / LARK_ACCOUNTS_BASE).
#  Kiểm lại bằng một lần đăng nhập thật lúc triển khai (README mục "Ứng dụng Lark").
LARK_OPEN_BASE = "https://open.larksuite.com/open-apis"
LARK_ACCOUNTS_BASE = "https://accounts.larksuite.com/open-apis"
DUONG_UY_QUYEN = "/authen/v1/authorize"
DUONG_TOKEN = "/authen/v2/oauth/token"
DUONG_NGUOI_DUNG = "/authen/v1/user_info"
SCOPE_MAC_DINH = "contact:user.email:readonly"

COOKIE_PHIEN = "ln_phien"
COOKIE_NONCE = "ln_dang_nhap"
COOKIE_THONG_BAO = "ln_tb"
# 8 giờ (một ngày làm việc): cookie ký không thu hồi được từ máy chủ — "Đăng xuất" chỉ xoá cookie
# ở trình duyệt đó. Muốn chặn ai NGAY thì xoá khỏi `nguoi_xem` (vai trò đọc lại mỗi lượt) hoặc
# đổi DASH_SESSION_KEY (mọi người đăng nhập lại).
PHIEN_GIAY = 8 * 3600
STATE_GIAY = 600
_RE_KHOA = re.compile(r"[0-9a-fA-F]{32,}")


class LoiDangNhap(Exception):
    """Đăng nhập Lark hỏng. Câu thông báo KHÔNG chứa token, secret hay code."""


def kiem_khoa(khoa_phien: str, khoa_bao: str) -> None:
    """Khoá phiên bắt buộc ≥ 32 ký tự hex; khoá báo (LANG_NGHE_BAO_KHOA) để trống = tắt đường báo,
    có thì cũng ≥ 32 hex và KHÁC khoá phiên. Vì sao: khoá báo nằm cả trong .env của Mark — trùng
    khoá phiên thì ai đọc được .env của Mark cũng giả được phiên quản lý."""
    if not _RE_KHOA.fullmatch(khoa_phien or ""):
        raise RuntimeError("DASH_SESSION_KEY phải là ≥ 32 ký tự hex (openssl rand -hex 32)")
    if khoa_bao:
        if not _RE_KHOA.fullmatch(khoa_bao):
            raise RuntimeError("LANG_NGHE_BAO_KHOA phải là ≥ 32 ký tự hex (openssl rand -hex 32)")
        if hmac.compare_digest(khoa_phien.lower().encode(), khoa_bao.lower().encode()):
            raise RuntimeError("LANG_NGHE_BAO_KHOA phải KHÁC DASH_SESSION_KEY (tạo hai khoá riêng)")


@dataclass(frozen=True)
class CauHinh:
    app_id: str
    app_secret: str
    base_url: str                       # vd https://social.hapas.vn (không có '/' cuối)
    khoa_phien: bytes
    tenant_key: str                     # tổ chức Lark của HAPAS; tài khoản tổ chức khác bị chặn
    open_base: str = LARK_OPEN_BASE
    accounts_base: str = LARK_ACCOUNTS_BASE
    scope: str = SCOPE_MAC_DINH

    @property
    def redirect_uri(self) -> str:
        return self.base_url + "/dang-nhap/xong"

    @property
    def cookie_secure(self) -> bool:
        # Cookie Secure theo đúng scheme của địa chỉ công khai: production luôn https (Caddy);
        # chỉ khi chạy thử http://127.0.0.1 mới tắt, kẻo trình duyệt không gửi cookie lại.
        return self.base_url.startswith("https://")

    @classmethod
    def tu_env(cls) -> CauHinh:
        """Đọc env; thiếu thứ bắt buộc thì DỪNG khởi động (thà không chạy còn hơn chạy hở)."""
        thieu = [k for k in ("DASH_LARK_APP_ID", "DASH_LARK_APP_SECRET", "DASH_BASE_URL",
                             "DASH_SESSION_KEY", "DASH_LARK_TENANT_KEY")
                 if not (os.environ.get(k) or "").strip()]
        if thieu:
            raise RuntimeError("Dashboard thiếu biến môi trường: " + ", ".join(thieu))
        khoa = os.environ["DASH_SESSION_KEY"].strip()
        kiem_khoa(khoa, (os.environ.get("LANG_NGHE_BAO_KHOA") or "").strip())
        base = os.environ["DASH_BASE_URL"].strip().rstrip("/")
        if not base.startswith(("https://", "http://127.0.0.1", "http://localhost")):
            raise RuntimeError("DASH_BASE_URL phải là https://… (http chỉ cho 127.0.0.1)")
        return cls(app_id=os.environ["DASH_LARK_APP_ID"].strip(),
                   app_secret=os.environ["DASH_LARK_APP_SECRET"].strip(),
                   base_url=base, khoa_phien=khoa.encode(),
                   tenant_key=os.environ["DASH_LARK_TENANT_KEY"].strip(),
                   open_base=(os.environ.get("LARK_OPEN_BASE") or LARK_OPEN_BASE).rstrip("/"),
                   accounts_base=(os.environ.get("LARK_ACCOUNTS_BASE")
                                  or LARK_ACCOUNTS_BASE).rstrip("/"),
                   scope=(os.environ.get("DASH_LARK_SCOPE") or SCOPE_MAC_DINH).strip())


# ───────────────────────────── ký / mở ─────────────────────────────
def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _khoa_con(khoa: bytes, muc_dich: str) -> bytes:
    return hmac.new(khoa, b"lang-nghe-dashboard:" + muc_dich.encode(), hashlib.sha256).digest()


def ky(du_lieu: dict, khoa: bytes, muc_dich: str) -> str:
    than = _b64(json.dumps(du_lieu, separators=(",", ":"), ensure_ascii=False).encode())
    chu_ky = hmac.new(_khoa_con(khoa, muc_dich), than.encode(), hashlib.sha256).digest()
    return f"{than}.{_b64(chu_ky)}"


def mo(chuoi: str | None, khoa: bytes, muc_dich: str, bay_gio: float | None = None) -> dict | None:
    """Chuỗi đã ký -> dict, hoặc None khi sai chữ ký / hỏng / hết hạn (`het`)."""
    if not chuoi or len(chuoi) > 4096 or chuoi.count(".") != 1:
        return None
    than, chu_ky = chuoi.split(".")
    dung = hmac.new(_khoa_con(khoa, muc_dich), than.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(dung, _b64d(chu_ky)):
            return None
        d = json.loads(_b64d(than))
    except (ValueError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    het = d.get("het")
    if not isinstance(het, (int, float)) or het < (bay_gio if bay_gio is not None else time.time()):
        return None
    return d


# ───────────────────────────── phiên + CSRF ─────────────────────────────
def tao_phien(email: str, khoa: bytes, bay_gio: float | None = None) -> str:
    t = int(bay_gio if bay_gio is not None else time.time())
    return ky({"email": email, "csrf": secrets.token_urlsafe(24), "tao": t,
               "het": t + PHIEN_GIAY}, khoa, "phien")


def doc_phien(chuoi: str | None, khoa: bytes, bay_gio: float | None = None) -> dict | None:
    d = mo(chuoi, khoa, "phien", bay_gio)
    if not d or not isinstance(d.get("email"), str) or not isinstance(d.get("csrf"), str):
        return None
    return d


def csrf_dung(phien: dict | None, gui: str | None) -> bool:
    if not phien or not gui:
        return False
    return hmac.compare_digest(str(phien.get("csrf") or "").encode(), str(gui).encode())


# ───────────────────────────── state OAuth ─────────────────────────────
def tao_state(khoa: bytes, sau: str, bay_gio: float | None = None) -> tuple[str, str]:
    """-> (state gửi Lark, nonce đặt vào cookie của trình duyệt)."""
    nonce = secrets.token_urlsafe(18)
    t = int(bay_gio if bay_gio is not None else time.time())
    return ky({"n": nonce, "sau": sau, "het": t + STATE_GIAY}, khoa, "state"), nonce


def doc_state(state: str | None, nonce_cookie: str | None, khoa: bytes,
              bay_gio: float | None = None) -> dict | None:
    """State hợp lệ khi: đúng chữ ký, chưa hết hạn, nonce trùng cookie của CHÍNH trình duyệt."""
    d = mo(state, khoa, "state", bay_gio)
    if not d or not nonce_cookie or not isinstance(d.get("n"), str):
        return None
    if not hmac.compare_digest(d["n"].encode(), str(nonce_cookie).encode()):
        return None
    return d


def url_uy_quyen(cfg: CauHinh, state: str) -> str:
    q = {"client_id": cfg.app_id, "redirect_uri": cfg.redirect_uri, "state": state}
    if cfg.scope:
        q["scope"] = cfg.scope
    return f"{cfg.accounts_base}{DUONG_UY_QUYEN}?{urlencode(q)}"


# ───────────────────────────── gọi Lark ─────────────────────────────
class LarkOAuth:
    """Hai lần gọi Lark sau khi người dùng đồng ý. `transport` để bộ thử giả HTTP
    (httpx.MockTransport) — không bao giờ ra mạng thật trong bộ thử."""

    def __init__(self, cfg: CauHinh, transport=None):
        self.cfg = cfg
        self.transport = transport

    async def lay_nguoi_dung(self, code: str) -> dict:
        """code -> {"email", "open_id", "union_id", "user_id", "tenant_key"}. Mã Lark: open_id
        (riêng cho app dashboard — cũng là app đọc danh bạ), union_id (chung mọi app của nhà phát
        triển), user_id (chỉ có khi app có scope contact:user.employee_id:readonly). Email: `enterprise_email` (do tổ chức cấp)
        nếu có; CHỈ khi trống mới lấy `email` (email người dùng tự khai, kém tin hơn). Chữ
        thường; không có email thì "". Bên gọi PHẢI so `tenant_key` với tổ chức HAPAS."""
        import httpx
        async with httpx.AsyncClient(timeout=10, transport=self.transport) as kh:
            try:
                r = await kh.post(self.cfg.open_base + DUONG_TOKEN, json={
                    "grant_type": "authorization_code", "client_id": self.cfg.app_id,
                    "client_secret": self.cfg.app_secret, "code": code,
                    "redirect_uri": self.cfg.redirect_uri})
                tk = r.json() if r.content else {}
            except (httpx.HTTPError, ValueError) as e:
                raise LoiDangNhap(f"không đổi được mã đăng nhập ({type(e).__name__})") from None
            token = tk.get("access_token") if isinstance(tk, dict) else None
            if r.status_code != 200 or not isinstance(tk, dict) or tk.get("code") not in (0, None) \
                    or not token:
                ma = tk.get("code") if isinstance(tk, dict) else None
                raise LoiDangNhap(f"Lark từ chối mã đăng nhập (HTTP {r.status_code}, mã {ma})")
            try:
                u = await kh.get(self.cfg.open_base + DUONG_NGUOI_DUNG,
                                 headers={"Authorization": f"Bearer {token}"})
                ud = u.json() if u.content else {}
            except (httpx.HTTPError, ValueError) as e:
                raise LoiDangNhap(f"không đọc được thông tin người dùng ({type(e).__name__})") from None
        if u.status_code != 200 or not isinstance(ud, dict) or ud.get("code") != 0:
            ma = ud.get("code") if isinstance(ud, dict) else None
            raise LoiDangNhap(f"Lark không trả thông tin người dùng (HTTP {u.status_code}, mã {ma})")
        data = ud.get("data") if isinstance(ud.get("data"), dict) else {}
        email = (str(data.get("enterprise_email") or "").strip()
                 or str(data.get("email") or "").strip()).lower()
        return {"email": email if "@" in email else "",
                "open_id": str(data.get("open_id") or "")[:100],
                "union_id": str(data.get("union_id") or "")[:100],
                "user_id": str(data.get("user_id") or "")[:100],
                "tenant_key": str(data.get("tenant_key") or "")}


def cung_to_chuc(cfg: CauHinh, tenant_key: str) -> bool:
    """Tài khoản Lark thuộc đúng tổ chức HAPAS (so hằng thời gian; rỗng = không)."""
    return bool(tenant_key) and hmac.compare_digest(tenant_key.encode(), cfg.tenant_key.encode())
