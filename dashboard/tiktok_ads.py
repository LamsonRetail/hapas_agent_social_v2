"""Kết nối TikTok Ads (TikTok for Business MCP server) + đồng bộ số quảng cáo vào kho `lang_nghe`.

Chủ dự án chốt 19/10/2026. Không LLM: chỉ OAuth, JSON-RPC và upsert.

KẾT NỐI (đo thật 19/10/2026 từ máy PC, xem dashboard/README.md mục "TikTok Ads")
  • MCP server lớp "layer" của TikTok for Business — KHÔNG cần app developer: đăng ký client động
    (DCR, client công khai `token_endpoint_auth_method: none`) + OAuth PKCE S256, scope `mcp:tt4b`.
  • Access token sống ~24 giờ, refresh token 30 ngày và KHÔNG được gia hạn khi làm mới (cùng token,
    `refresh_token_expires_in` cứ đếm lùi) → cứng 30 ngày; quản trị viên đăng nhập lại để có 30
    ngày mới (thẻ "Kết nối TikTok Ads" trên trang Quản trị đếm ngược, Mark nhắc trước 7/3/1 ngày).
  • Loại `api_token` (token "API access" của app developer, không hết hạn) cũng được MCP server nhận
    làm Bearer — đổi loại chỉ là cấu hình (`ket_noi_ngoai.loai`), không làm mới, không hết hạn.

AN TOÀN
  • Danh sách công cụ CHỈ ĐỌC cứng (`CONG_CU_DOC`): tên nào khác — kể cả `tool_execute` (cửa gọi
    ~380 công cụ khác, trong đó có ghi) và mọi công cụ tạo/sửa/ngân sách — bị chặn TRƯỚC khi gửi.
  • Token mã hoá khi nằm trong DB (`ma_hoa`, khoá `TIKTOK_KHOA_MA_HOA` 32 byte base64 trong
    /opt/lang-nghe/.env). Không bao giờ in/log/hiện token; lỗi đi qua `gon_loi` (bỏ chuỗi giống
    token, URL). Mark chỉ đọc cột không bí mật của `ket_noi_ngoai` (quyền theo cột trong schema.sql).
  • Mã hoá AES-256-GCM (`cryptography`, AESGCM): base64(phiên bản 1 byte | nonce 12 byte |
    bản mã || thẻ), AAD = nhà cung cấp + tên cột — không tráo được access ↔ refresh.

ĐỒNG BỘ (`python -m dashboard.tiktok_ads dong-bo`, bộ hẹn giờ 06:30 giờ VN; nút "Đồng bộ ngay" chỉ
ghi cờ yêu cầu — bộ hẹn giờ 2 phút chạy `dong-bo --chi-khi-yeu-cau`; dashboard KHÔNG chạy đồng bộ)
  • Làm mới access token trước; không có token dùng được thì ghi trạng thái rồi thoát 0, im lặng.
  • Thấy tài khoản (auth_advertiser_get + advertiser_info_get) → `tk_quang_cao`, gán bên tự động.
  • Mỗi tài khoản đang đồng bộ: lần đầu nạp lùi 90 ngày (3 cửa sổ 30 ngày, mới trước), sau đó mỗi
    ngày đọc lại 7 ngày gần nhất (chuyển đổi TikTok ghi trễ). Cấp tài khoản theo ngày; cấp campaign
    và ad CHỈ đối tượng có hiển thị (báo cáo trả MỌI đối tượng chưa xoá kể cả không chạy — một tài
    khoản có 20.000 ad, 7.599 chạy trong 30 ngày): lấy ID xếp impressions giảm dần, dừng ở dòng 0
    đầu tiên, rồi đọc số theo lô ≤ 100 ID, ≤ 45 chỉ số mỗi lượt, trang ≤ 200 dòng (trang 1.000 dòng
    nhiều chỉ số tới 1,4 MB từng đứt giữa chừng). Khán giả (tuổi, giới tính, tỉnh, nền tảng) mỗi
    tuần một lần, cửa sổ 30 ngày.
  • Tuần tự, nghỉ ngắn giữa các lượt gọi; lỗi mạng (hết giờ, đứt giữa chừng) thử lại 3 lần.
  • Upsert theo khoá chính — chạy lại không nhân đôi. Khoá advisory Postgres: không chạy chồng.
"""
from __future__ import annotations

import argparse
import base64
import contextlib
import datetime
import hashlib
import json
import os
import re
import secrets
import sys
import time
from urllib.parse import urlencode

from dashboard import quang_cao as QC

# ─── TikTok for Business MCP (đo thật 19/10/2026) ───
NCC = "tiktok_ads"
MAY_CHU = "https://business-api.tiktok.com"
BASE = f"{MAY_CHU}/open_mcp/tt-ads-mcp-layer"
DUONG_UY_QUYEN = f"{MAY_CHU}/portal/mcp-tt4b-authorize"
DUONG_TOKEN = f"{BASE}/oauth/token"
DUONG_DANG_KY = f"{BASE}/oauth/register"
DUONG_THU_HOI = f"{BASE}/oauth/revoke"
SCOPE = "mcp:tt4b"
PHIEN_BAN_MCP = "2025-06-18"
TEN_CLIENT = "hapas-social-listening-dashboard"

#: Công cụ ĐƯỢC gọi — chỉ đọc, và CHỈ những công cụ mã này thật sự dùng (soát 19/10/2026: bỏ bc_get,
#: identity_*, tool_get/tool_list). Mọi tên khác bị chặn trước khi gửi (kể cả tool_execute).
CONG_CU_DOC = frozenset({"auth_advertiser_get", "advertiser_info_get", "report_integrated_get"})
LOAI = ("mcp_oauth", "api_token")
#: Mã lỗi TikTok coi là "token hỏng/hết hạn" (Marketing API: 40100–40105).
MA_XAC_THUC = frozenset({40100, 40101, 40102, 40104, 40105})

NAP_LUI_NGAY = 90          # lần đầu mỗi tài khoản
CUA_SO_NGAY = 30           # stat_time_day tối đa 30 ngày mỗi lượt
LUI_NGAY = 7               # hằng ngày đọc lại 7 ngày gần nhất (chuyển đổi ghi trễ)
KHAN_GIA_NGAY = 7          # khán giả: mỗi tuần một lần, cửa sổ 30 ngày
LO_ID = 100                # ≤ 100 ID mỗi bộ lọc
LO_CHI_SO = 45             # ≤ 45 chỉ số mỗi lượt gọi
TRANG = 200                # dòng mỗi trang khi nhiều chỉ số
TRANG_ID = 1000            # dòng mỗi trang khi chỉ xin impressions (lấy ID)
THU_LAI = 3
NGHI_GIAY = 0.3            # nghỉ giữa hai lượt gọi (nhẹ cho giới hạn tần suất)
CANH_BAO_NGAY, NGUY_NGAY = 7, 2   # thẻ: vàng < 7 ngày, đỏ < 2 ngày
#: Access token còn < 6 giờ thì làm mới TRƯỚC khi bắt đầu (một lượt nạp lùi chạy tới 6 giờ —
#: soát 19/10/2026); giữa lượt TikTok vẫn từ chối thì làm mới cưỡng bức một lần (`McpTuLamMoi`).
SAT_HAN_GIAY = 6 * 3600
AT_MAC_DINH, RT_MAC_DINH = 86399, 2591999   # expires_in / refresh_token_expires_in khi TikTok trả lạ
TRAN_TOKEN = 4096
VN = QC.VN
_MUI_GIO_VN = {"Asia/Ho_Chi_Minh", "Asia/Saigon", "Asia/Bangkok", "Asia/Jakarta",
               "Etc/GMT-7", "UTC+07:00"}


class LoiTikTok(RuntimeError):
    """Gọi TikTok hỏng. Câu đã qua `gon_loi` (không token, không URL) — hiện được cho quản trị."""

    def __init__(self, thong_diep: str, ma: int | None = None):
        super().__init__(gon_loi(thong_diep))
        self.ma = ma


class LoiChan(LoiTikTok):
    """Công cụ không nằm trong danh sách chỉ đọc — KHÔNG gửi đi."""


class LoiXacThuc(LoiTikTok):
    """Token bị từ chối (hết hạn / bị thu hồi)."""


class LoiHetHan(LoiXacThuc):
    """Refresh token đã hết 30 ngày — cần quản trị viên đăng nhập lại."""


class ChuaKetNoi(RuntimeError):
    """Chưa có token nào (chưa kết nối hoặc đã ngắt)."""


class LoiMaHoa(RuntimeError):
    """Khoá mã hoá thiếu/sai, hoặc bản mã bị sửa."""


#: Chuỗi ≥ 24 ký tự có cả chữ và số (token, khoá, mã) — tên công cụ toàn chữ thì giữ nguyên.
_RE_GIONG_TOKEN = re.compile(r"(?=[A-Za-z0-9_\-.+/=]*[0-9])(?=[A-Za-z0-9_\-.+/=]*[A-Za-z])"
                             r"[A-Za-z0-9_\-.+/=]{24,}")
_RE_URL = re.compile(r"https?://\S+")


#: Token đang dùng trong tiến trình (giải mã / vừa nhận) — `gon_loi` xoá ĐÚNG các chuỗi này ngoài
#: luật regex (token ngắn hoặc lạ dạng vẫn không lọt vào lỗi). Chỉ trong bộ nhớ, không ghi đâu cả.
_BI_MAT: set[str] = set()


def nho_bi_mat(*ds) -> None:
    for x in ds:
        if isinstance(x, str) and len(x) >= 8:
            _BI_MAT.add(x)


def gon_loi(s, bi_mat=()) -> str:
    """Chữ lỗi an toàn để lưu/hiện: bỏ đúng các token đã biết (`bi_mat` + token tiến trình đang
    dùng), URL, chuỗi dài giống token/khoá, cắt 300 ký tự."""
    s = str(s or "")
    biet = {b for b in bi_mat if isinstance(b, str) and b} | _BI_MAT
    for x in sorted(biet, key=len, reverse=True):
        s = s.replace(x, "<…>")
    s = _RE_URL.sub("<url>", s)
    s = re.sub(r"(?i)bearer\s+\S+", "Bearer <…>", s)
    return _RE_GIONG_TOKEN.sub("<…>", s)[:300]


# ───────────────────────────── mã hoá token ─────────────────────────────
def khoa_tu_env(env=None) -> bytes | None:
    """`TIKTOK_KHOA_MA_HOA` (32 byte, base64 — `openssl rand -base64 32`). Trống → None (tính
    năng tắt). Sai dạng → LoiMaHoa (không đoán, không cắt/độn khoá)."""
    s = ((env if env is not None else os.environ).get("TIKTOK_KHOA_MA_HOA") or "").strip()
    if not s:
        return None
    try:
        k = base64.b64decode(s + "=" * (-len(s) % 4), altchars=b"-_" if ("-" in s or "_" in s)
                             else None, validate=True)
    except (ValueError, TypeError):
        raise LoiMaHoa("TIKTOK_KHOA_MA_HOA không phải base64 (tạo: openssl rand -base64 32)") \
            from None
    if len(k) != 32:
        raise LoiMaHoa("TIKTOK_KHOA_MA_HOA phải đúng 32 byte (tạo: openssl rand -base64 32)")
    return k


PHIEN_BAN_MA = b"\x01"           # byte đầu bản mã: định dạng AES-256-GCM v1


def _aad(ngu_canh: str, ncc: str = NCC) -> bytes:
    """AAD = nhà cung cấp + tên cột: bản mã cột access không giải được ở cột refresh (và ngược
    lại), bản mã của nhà cung cấp này không dùng được cho nhà cung cấp khác (Meta Ads dùng
    chung khoá, `ncc` = "meta_ads" — 20/10/2026)."""
    return f"lang-nghe|{ncc}|{ngu_canh}".encode()


def _aesgcm(khoa: bytes):
    if not isinstance(khoa, (bytes, bytearray)) or len(khoa) != 32:
        raise LoiMaHoa("khoá mã hoá phải đúng 32 byte (TIKTOK_KHOA_MA_HOA)")
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        raise LoiMaHoa("máy chủ chưa cài thư viện cryptography") from None
    return AESGCM(bytes(khoa))


def ma_hoa(chu: str, khoa: bytes, ngu_canh: str, ncc: str = NCC) -> str:
    """Chuỗi → base64(phiên bản 1 byte | nonce 12 byte | bản mã || thẻ 16 byte), AES-256-GCM,
    AAD = `_aad(ngu_canh, ncc)` (vd "access", "refresh", "pkce")."""
    a = _aesgcm(khoa)
    nonce = secrets.token_bytes(12)
    ma = a.encrypt(nonce, str(chu).encode("utf-8"), _aad(ngu_canh, ncc))
    return base64.urlsafe_b64encode(PHIEN_BAN_MA + nonce + ma).decode()


def giai_ma(chuoi: str, khoa: bytes, ngu_canh: str, ncc: str = NCC) -> str:
    """Ngược `ma_hoa`. Sai khoá / bị sửa / sai cột (AAD) → LoiMaHoa, không bao giờ trả rác."""
    a = _aesgcm(khoa)
    try:
        b = base64.urlsafe_b64decode(str(chuoi or "").encode())
    except (ValueError, TypeError):
        raise LoiMaHoa("bản mã hỏng") from None
    if len(b) < 1 + 12 + 16 or b[:1] != PHIEN_BAN_MA:
        raise LoiMaHoa("bản mã không đúng định dạng")
    from cryptography.exceptions import InvalidTag
    try:
        return a.decrypt(b[1:13], b[13:], _aad(ngu_canh, ncc)).decode("utf-8")
    except InvalidTag:
        raise LoiMaHoa("bản mã không khớp khoá (khoá đổi hoặc dữ liệu bị sửa)") from None


# ───────────────────────────── HTTP ─────────────────────────────
class Http:
    """POST tới TikTok bằng httpx (venv dashboard có sẵn). Lỗi mạng (hết giờ, đứt giữa chừng —
    IncompleteRead/RemoteProtocolError) và 502/503/504 thử lại `THU_LAI` lần, nghỉ 3/6/9 giây.
    Bộ thử truyền `transport=httpx.MockTransport(...)` — không bao giờ ra mạng thật."""

    def __init__(self, transport=None, ngu=time.sleep, timeout: float = 90.0):
        self.transport, self.ngu, self.timeout = transport, ngu, timeout

    def post(self, url: str, *, json_body=None, form=None, headers=None
             ) -> tuple[int, dict, str]:
        import httpx
        h = dict(headers or {})
        loi = None
        for lan in range(THU_LAI):
            try:
                with httpx.Client(timeout=self.timeout, transport=self.transport) as kh:
                    if form is not None:
                        r = kh.post(url, data=form, headers=h)
                    else:
                        r = kh.post(url, json=json_body, headers=h)
                    van = r.text
                if r.status_code in (502, 503, 504) and lan < THU_LAI - 1:
                    loi = f"HTTP {r.status_code}"
                    self.ngu(3 * (lan + 1))
                    continue
                return r.status_code, {k.lower(): v for k, v in r.headers.items()}, van
            except httpx.TransportError as e:   # gồm ReadTimeout, RemoteProtocolError (đứt giữa)
                loi = type(e).__name__
                if lan < THU_LAI - 1:
                    self.ngu(3 * (lan + 1))
        raise LoiTikTok(f"không gọi được TikTok sau {THU_LAI} lần ({loi})")


def _json_hoac_loi(status: int, van: str, viec: str) -> dict:
    try:
        d = json.loads(van) if van else {}
    except ValueError:
        d = {}
    if status >= 300 or not isinstance(d, dict):
        ma = d.get("error") if isinstance(d, dict) else None
        cls = LoiXacThuc if status in (400, 401) and ma in ("invalid_grant", "invalid_token",
                                                            "unauthorized_client") else LoiTikTok
        raise cls(f"{viec}: HTTP {status}" + (f" ({ma})" if ma else ""))
    return d


def _giay(v, mac_dinh: int, ten: str, log=print) -> int:
    """Số giây TikTok trả (expires_in…) → int; lạ / thiếu / âm thì dùng mặc định + cảnh báo gọn
    (không để callback 500)."""
    try:
        n = int(v)
        if n > 0:
            return n
    except (TypeError, ValueError, OverflowError):
        pass
    if v is not None:
        log(f"[tiktok_ads] {ten} lạ ({gon_loi(str(v))[:40]}) — dùng mặc định {mac_dinh} giây")
    return mac_dinh


# ───────────────────────────── OAuth ─────────────────────────────
def pkce() -> tuple[str, str]:
    """-> (code_verifier, code_challenge S256)."""
    ver = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    chal = base64.urlsafe_b64encode(hashlib.sha256(ver.encode()).digest()).rstrip(b"=").decode()
    return ver, chal


def url_uy_quyen(client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    return DUONG_UY_QUYEN + "?" + urlencode({
        "response_type": "code", "resource": BASE, "client_id": client_id,
        "redirect_uri": redirect_uri, "scope": SCOPE, "code_challenge": challenge,
        "code_challenge_method": "S256", "state": state})


def dang_ky_client(http: Http, redirect_uri: str) -> str:
    s, _, van = http.post(DUONG_DANG_KY, json_body={
        "client_name": TEN_CLIENT, "redirect_uris": [redirect_uri],
        "token_endpoint_auth_method": "none", "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"]})
    d = _json_hoac_loi(s, van, "đăng ký client")
    cid = str(d.get("client_id") or "")
    if not cid or len(cid) > 300:
        raise LoiTikTok("đăng ký client: TikTok không trả client_id")
    return cid


def doi_ma(http: Http, client_id: str, code: str, verifier: str, redirect_uri: str) -> dict:
    s, _, van = http.post(DUONG_TOKEN, form={
        "grant_type": "authorization_code", "code": code, "code_verifier": verifier,
        "redirect_uri": redirect_uri, "client_id": client_id})
    d = _json_hoac_loi(s, van, "đổi mã")
    if not d.get("access_token"):
        raise LoiTikTok("đổi mã: TikTok không trả access_token")
    return d


def lam_moi(http: Http, client_id: str, refresh_token: str) -> dict:
    s, _, van = http.post(DUONG_TOKEN, form={"grant_type": "refresh_token",
                                             "refresh_token": refresh_token,
                                             "client_id": client_id})
    d = _json_hoac_loi(s, van, "làm mới token")
    if not d.get("access_token"):
        raise LoiXacThuc("làm mới token: TikTok không trả access_token")
    return d


def thu_hoi(http: Http, token: str, goi_y: str = "access_token") -> bool:
    """Thu hồi phía TikTok (cố gắng; lỗi không chặn việc xoá token ở kho)."""
    try:
        s, _, _ = http.post(DUONG_THU_HOI, form={"token": token, "token_type_hint": goi_y})
    except LoiTikTok:
        return False
    return s < 300


# ───────────────────────────── MCP (JSON-RPC) ─────────────────────────────
def kiem_cong_cu(ten: str, args: dict | None = None) -> None:
    """Chặn mọi công cụ ngoài danh sách chỉ đọc (gồm tool_execute). Gọi TRƯỚC khi gửi."""
    if ten not in CONG_CU_DOC:
        raise LoiChan(f"chặn công cụ '{str(ten)[:60]}': không nằm trong danh sách chỉ đọc")


class Mcp:
    """Một phiên MCP: initialize một lần, gửi lại Mcp-Session-Id, đọc SSE (dòng "data:" cuối)."""

    def __init__(self, token: str, http: Http, ngu=time.sleep, nghi: float = NGHI_GIAY):
        self._token, self.http, self.ngu, self.nghi = token, http, ngu, nghi
        nho_bi_mat(token)
        self._phien: str | None = None
        self._da_mo = False
        self.so_luot = 0

    def _rpc(self, method: str, params=None, thong_bao: bool = False):
        h = {"Authorization": "Bearer " + self._token,
             "Accept": "application/json, text/event-stream"}
        if self._phien:
            h["Mcp-Session-Id"] = self._phien
        msg: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not thong_bao:
            msg["id"] = secrets.randbelow(10 ** 9)
        s, hd, van = self.http.post(BASE, json_body=msg, headers=h)
        if hd.get("mcp-session-id"):
            self._phien = hd["mcp-session-id"][:200]
        if thong_bao:
            return None
        if s == 401:
            raise LoiXacThuc("TikTok từ chối token (HTTP 401)")
        if s >= 300:
            raise LoiTikTok(f"{method}: HTTP {s}")
        if "text/event-stream" in (hd.get("content-type") or ""):
            ds = [ln[5:].strip() for ln in van.splitlines() if ln.startswith("data:")]
            van = ds[-1] if ds else "{}"
        try:
            return json.loads(van)
        except ValueError:
            raise LoiTikTok(f"{method}: trả về không phải JSON") from None

    def mo(self) -> None:
        if self._da_mo:
            return
        r = self._rpc("initialize", {"protocolVersion": PHIEN_BAN_MCP, "capabilities": {},
                                     "clientInfo": {"name": TEN_CLIENT, "version": "1.0"}})
        if isinstance(r, dict) and r.get("error"):
            raise LoiTikTok(f"initialize: {json.dumps(r['error'], ensure_ascii=False)[:200]}")
        self._rpc("notifications/initialized", thong_bao=True)
        self._da_mo = True

    def goi(self, ten: str, args: dict | None = None):
        """Gọi một công cụ đọc → `data` (code 0). Ném LoiChan / LoiXacThuc / LoiTikTok."""
        kiem_cong_cu(ten, args)
        self.mo()
        if self.so_luot and self.nghi:
            self.ngu(self.nghi)
        self.so_luot += 1
        r = self._rpc("tools/call", {"name": ten, "arguments": args or {}})
        if not isinstance(r, dict):
            raise LoiTikTok(f"{ten}: trả về lạ")
        if r.get("error"):
            raise LoiTikTok(f"{ten}: {json.dumps(r['error'], ensure_ascii=False)[:200]}")
        res = r.get("result") or {}
        van = "".join(c.get("text", "") for c in res.get("content") or []
                      if isinstance(c, dict) and c.get("type") == "text")
        try:
            d = json.loads(van)
        except ValueError:
            raise LoiTikTok(f"{ten}: {van[:200]}") from None
        if isinstance(d, dict) and d.get("code") not in (None, 0):
            ma = d.get("code")
            cls = LoiXacThuc if ma in MA_XAC_THUC else LoiTikTok
            raise cls(f"{ten}: code {ma}: {str(d.get('message') or '')[:160]}", ma)
        if res.get("isError"):
            raise LoiTikTok(f"{ten}: {van[:200]}")
        return d.get("data") if isinstance(d, dict) and "data" in d else d


class McpTuLamMoi:
    """Phiên MCP của một lượt đồng bộ: TikTok từ chối token giữa chừng (LoiXacThuc) thì làm mới
    CƯỠNG BỨC một lần, dựng lại phiên, gọi lại đúng lượt đó; làm mới cũng hỏng mới chịu lỗi."""

    def __init__(self, dv):
        self.dv = dv
        self._mcp = Mcp(dv.token(), dv.http, dv.ngu)

    @property
    def so_luot(self) -> int:
        return self._mcp.so_luot

    def goi(self, ten: str, args: dict | None = None):
        kiem_cong_cu(ten, args)
        try:
            return self._mcp.goi(ten, args)
        except LoiChan:
            raise
        except LoiXacThuc as e:
            self.dv.log(f"[tiktok_ads] TikTok từ chối token giữa lượt ({e}) — làm mới rồi thử lại")
            self._mcp = Mcp(self.dv.token(ep=True), self.dv.http, self.dv.ngu)
            return self._mcp.goi(ten, args)


# ───────────────────────────── báo cáo ─────────────────────────────
LOC_ID = {"campaign_id": "campaign_ids", "adgroup_id": "adgroup_ids", "ad_id": "ad_ids"}


def bao_cao(mcp: Mcp, adv: str, cap: str, chieu: list[str], chi_so: list[str] | tuple,
            tu: datetime.date, den: datetime.date, *, loai: str = "BASIC",
            loc: list | None = None) -> list[dict]:
    """report_integrated_get: tách chỉ số thành lô ≤ LO_CHI_SO, phân trang ≤ TRANG dòng, ghép
    các lô theo bộ chiều. -> [{<chiều>…, <chỉ số>…}] (giá trị gốc, chưa đổi số)."""
    gop: dict[str, dict] = {}
    chi_so = list(chi_so)
    for i in range(0, len(chi_so), LO_CHI_SO):
        trang = 1
        while True:
            a = {"advertiser_id": adv, "report_type": loai, "data_level": cap,
                 "dimensions": list(chieu), "metrics": chi_so[i:i + LO_CHI_SO],
                 "start_date": tu.isoformat(), "end_date": den.isoformat(),
                 "page": trang, "page_size": TRANG}
            if loc:
                a["filtering"] = loc
            d = mcp.goi("report_integrated_get", a) or {}
            for r in d.get("list") or []:
                dims = r.get("dimensions") or {}
                k = json.dumps(dims, sort_keys=True)
                gop.setdefault(k, dict(dims)).update(r.get("metrics") or {})
            tong = int((d.get("page_info") or {}).get("total_page") or 1)
            if trang >= tong:
                break
            trang += 1
    return list(gop.values())


def ids_co_chay(mcp: Mcp, adv: str, cap: str, dim: str, tu: datetime.date,
                den: datetime.date) -> list[str]:
    """ID có hiển thị > 0 trong kỳ: xếp impressions giảm dần, dừng ở dòng 0 ĐẦU TIÊN (không đọc
    hết hàng chục nghìn đối tượng không chạy)."""
    ra, trang = [], 1
    while True:
        d = mcp.goi("report_integrated_get", {
            "advertiser_id": adv, "report_type": "BASIC", "data_level": cap, "dimensions": [dim],
            "metrics": ["impressions"], "start_date": tu.isoformat(), "end_date": den.isoformat(),
            "order_field": "impressions", "order_type": "DESC", "page": trang,
            "page_size": TRANG_ID}) or {}
        for r in d.get("list") or []:
            if (QC.so((r.get("metrics") or {}).get("impressions")) or 0) <= 0:
                return ra
            ra.append(str((r.get("dimensions") or {}).get(dim)))
        if trang >= int((d.get("page_info") or {}).get("total_page") or 1):
            return ra
        trang += 1


def lo_id(ids: list[str], n: int = LO_ID) -> list[list[str]]:
    return [ids[i:i + n] for i in range(0, len(ids), n)]


def bo_loc_id(dim: str, ids: list[str]) -> list[dict]:
    if len(ids) > LO_ID:
        raise ValueError("tối đa 100 ID mỗi bộ lọc")
    return [{"field_name": LOC_ID[dim], "filter_type": "IN", "filter_value": json.dumps(ids)}]


# ───────────────────────────── dòng TikTok → dòng kho ─────────────────────────────
def _ngay(v) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None


_KHONG_PHAI_SO = frozenset({"campaign_name", "adgroup_name", "ad_name", "ad_text",
                            "objective_type", "promotion_type", "placement_type", "billing_event",
                            "bid_strategy", "tt_app_name", "call_to_action", "image_mode",
                            "dpa_target_audience_type", "campaign_dedicate_type", "opt_status",
                            "smart_target", "currency", "timezone"})


def _chi_so_json(r: dict, bo: tuple = ()) -> dict:
    """Mọi chỉ số còn lại → JSON (số đã đổi; chữ giữ nguyên, cắt 300)."""
    ra = {}
    for k, v in r.items():
        if k in bo or k in ("stat_time_day", "advertiser_id", "campaign_id", "adgroup_id",
                            "ad_id"):
            continue
        ra[k] = str(v)[:300] if k in _KHONG_PHAI_SO else QC.so(v)
    return ra


def co_phan_phoi(r: dict) -> bool:
    return bool((r.get("hien_thi") or 0) > 0 or (r.get("chi") or 0) > 0)


def dong_tk(r: dict, adv: str) -> dict:
    return {"advertiser_id": adv, "ngay": _ngay(r.get("stat_time_day")), **QC.dong_so(r),
            "chi_so": _chi_so_json(r)}


def dong_campaign(r: dict, adv: str) -> dict:
    return {"advertiser_id": adv, "campaign_id": str(r.get("campaign_id")),
            "ngay": _ngay(r.get("stat_time_day")), "ten": str(r.get("campaign_name") or "")[:300],
            "muc_tieu": str(r.get("objective_type") or "")[:60] or None, **QC.dong_so(r),
            "chi_so": _chi_so_json(r, ("campaign_name", "objective_type"))}


def dong_ad(r: dict, adv: str) -> dict:
    return {"advertiser_id": adv, "campaign_id": str(r.get("campaign_id") or "") or None,
            "adgroup_id": str(r.get("adgroup_id") or "") or None, "ad_id": str(r.get("ad_id")),
            "ngay": _ngay(r.get("stat_time_day")), "ten_ad": str(r.get("ad_name") or "")[:300],
            "noi_dung": str(r.get("ad_text") or "")[:2000],
            "ten_campaign": str(r.get("campaign_name") or "")[:300],
            "ten_nhom": str(r.get("adgroup_name") or "")[:300], **QC.dong_so(r),
            "chi_so": _chi_so_json(r, ("ad_name", "ad_text", "campaign_name", "adgroup_name"))}


def dong_khan_gia(r: dict, adv: str, tu: datetime.date, den: datetime.date, chieu: str) -> dict:
    g = r.get(chieu)
    return {"advertiser_id": adv, "tu": tu, "den": den, "chieu": chieu,
            "gia_tri": "" if g is None else str(g)[:100], **QC.dong_so(r),
            "chi_so": _chi_so_json(r, (chieu,))}


def cua_so(tu: datetime.date, den: datetime.date, n: int = CUA_SO_NGAY
           ) -> list[tuple[datetime.date, datetime.date]]:
    """[tu, den] → các cửa sổ ≤ n ngày, MỚI TRƯỚC (số gần nhất có sớm nhất)."""
    ra, b = [], den
    while b >= tu:
        a = max(tu, b - datetime.timedelta(days=n - 1))
        ra.append((a, b))
        b = a - datetime.timedelta(days=1)
    return ra


def hom_qua(mui_gio: str | None, bay_gio: datetime.datetime) -> datetime.date:
    """Hôm qua theo múi giờ tài khoản (TikTok tính ngày theo múi giờ tài khoản)."""
    tz = VN
    if mui_gio and mui_gio not in _MUI_GIO_VN:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(mui_gio)
        except Exception:  # noqa: BLE001 — máy thiếu tzdata: lùi về giờ VN
            tz = VN
    return bay_gio.astimezone(tz).date() - datetime.timedelta(days=1)


#: Lượt "nhanh" (người dùng bấm "Đồng bộ ngay", chủ dự án 20/10/2026): hôm nay + 2 ngày trước.
NHANH_NGAY = 3


def cua_so_nhanh(hq: datetime.date) -> tuple[datetime.date, datetime.date]:
    """Cửa sổ lượt nhanh theo múi giờ tài khoản: [hôm nay − 2, hôm nay] (`hq` = hôm qua). Số hôm
    nay chưa trọn — lượt 06:30 sáng mai đọc lại 7 ngày nên tự đúng."""
    homnay = hq + datetime.timedelta(days=1)
    return homnay - datetime.timedelta(days=NHANH_NGAY - 1), homnay


#: Lượt "tức thì" theo phạm vi (Mark hỏi số mới, chủ dự án 20/10/2026): tối đa 7 ngày GỒM hôm nay.
TUC_THI_NGAY = 7


def cua_so_tuc_thi(hq: datetime.date, tu: datetime.date | None, den: datetime.date | None
                   ) -> tuple[datetime.date, datetime.date] | None:
    """Cửa sổ của lượt tức thì cho MỘT tài khoản (`hq` = hôm qua theo múi giờ tài khoản): [tu, den]
    kẹp vào [hôm nay − 6, hôm nay]. Kỳ hỏi nằm hẳn trước 7 ngày gần nhất → None (số cũ đã chốt
    ở lượt hằng ngày, không cần đọc lại)."""
    homnay = hq + datetime.timedelta(days=1)
    a = max(tu or homnay, homnay - datetime.timedelta(days=TUC_THI_NGAY - 1))
    b = min(den or homnay, homnay)
    return (a, b) if a <= b else None


def co_chay_gan(kho, t: dict, bay: datetime.datetime) -> bool:
    """Tài khoản có hiển thị trong 30 ngày gần nhất (lượt nhanh bỏ tài khoản không chạy)."""
    hq = hom_qua(t.get("mui_gio"), bay)
    try:
        return bool((kho.qc_tong([str(t["advertiser_id"])], hq - datetime.timedelta(days=29), hq)
                     or {}).get("hien_thi"))
    except Exception:  # noqa: BLE001 — đọc kho hỏng: cứ đọc (an toàn hơn bỏ sót)
        return True


# ───────────────────────────── dịch vụ ─────────────────────────────
TEN_TRANG_THAI = {"chua_ket_noi": "Chưa kết nối", "hoat_dong": "Đang hoạt động",
                  "het_han": "Hết hạn", "loi": "Lỗi", "da_ngat": "Đã ngắt"}


def _utc(dt):
    if isinstance(dt, datetime.datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


#: Lượt hằng ngày chờ khoá: thử lại mỗi 30 giây (soát 20/10/2026 H2).
NHIP_CHO_KHOA = 30


def chay_voi_khoa(mo_khoa, chay, cho_giay: float, ngu, log, ten: str,
                  bo_qua: str = "đang có lượt đồng bộ khác") -> dict:
    """Giữ khoá advisory (`mo_khoa()` → context manager → True/False) rồi `chay()`. Lượt khác đang
    giữ: chờ, thử lại mỗi `NHIP_CHO_KHOA` giây tới `cho_giay` giây; vẫn không có khoá →
    {"ban": True, "bo_qua"} (dòng lệnh thoát khác 0). `cho_giay` 0 (nút, bộ hẹn giờ 2 phút, bộ
    nghe) → {"bo_qua"} ngay như trước."""
    da = 0.0
    while True:
        with mo_khoa() as giu:
            if giu:
                return chay()
        if cho_giay <= 0:
            return {"bo_qua": bo_qua}
        if da >= cho_giay:
            return {"ban": True, "bo_qua": bo_qua}
        log(f"[{ten}] lượt khác đang giữ khoá đồng bộ — chờ ({int(da)}/{int(cho_giay)} giây)")
        ngu(NHIP_CHO_KHOA)
        da += NHIP_CHO_KHOA


class DichVu:
    """Mọi việc TikTok Ads của dashboard + bộ hẹn giờ. `kho` = module `kho_qc` (hoặc bản giả),
    `http` = `Http` (bộ thử truyền MockTransport), `khoa` = khoá mã hoá (None → đọc env)."""

    def __init__(self, kho=None, *, http: Http | None = None, khoa: bytes | None = None,
                 ngu=time.sleep, bay_gio=None, log=print):
        if kho is None:
            from dashboard import kho_qc as kho
        self.kho = kho
        self.http = http or Http(ngu=ngu)
        self._khoa = khoa
        self.ngu = ngu
        self._bay_gio = bay_gio or (lambda: datetime.datetime.now(datetime.timezone.utc))
        self.log = log

    # ── khoá ──
    def khoa(self) -> bytes:
        k = self._khoa if self._khoa is not None else khoa_tu_env()
        if not k:
            raise LoiMaHoa("máy chủ chưa đặt TIKTOK_KHOA_MA_HOA")
        return k

    def co_khoa(self) -> bool:
        return self.loi_khoa() is None

    def loi_khoa(self) -> str | None:
        """None khi khoá dùng được; không thì câu nói rõ vì sao (thiếu / sai dạng / sai độ dài /
        thiếu thư viện) — thẻ và bộ đồng bộ hiện câu này, dashboard không sập."""
        try:
            _aesgcm(self.khoa())
            return None
        except LoiMaHoa as e:
            return str(e)

    def ma_hoa_tam(self, chu: str) -> str:
        return ma_hoa(chu, self.khoa(), "pkce")

    def giai_ma_tam(self, chuoi: str) -> str:
        return giai_ma(chuoi, self.khoa(), "pkce")

    # ── thẻ trạng thái (KHÔNG token) ──
    def the(self) -> dict:
        """Thẻ "Kết nối TikTok Ads": chỉ cột không bí mật + số đã tính sẵn."""
        r = self.kho.doc_ket_noi() or {}
        bay = self._bay_gio()
        loai = r.get("loai") or "mcp_oauth"
        co_token = bool(r.get("access_token_enc"))
        het = _utc(r.get("refresh_het_luc"))
        con = (het - bay).total_seconds() / 86400 if het and loai == "mcp_oauth" else None
        tt = r.get("trang_thai") or "chua_ket_noi"
        if co_token and loai == "mcp_oauth" and con is not None and con <= 0:
            tt = "het_han"
        muc = "tot"
        if tt in ("het_han", "loi"):
            muc = "loi"
        elif tt in ("chua_ket_noi", "da_ngat"):
            muc = ""
        elif con is not None:
            muc = "loi" if con < NGUY_NGAY else ("canh" if con < CANH_BAO_NGAY else "tot")
        thay, truoc = r.get("so_tk_thay"), r.get("so_tk_truoc")
        try:
            dang = bool(self.kho.dang_dong_bo())
        except Exception:  # noqa: BLE001
            dang = False
        return {
            "trang_thai": tt, "nhan": TEN_TRANG_THAI.get(tt, tt), "muc": muc, "loai": loai,
            "co_token": co_token, "khong_het_han": loai == "api_token" and co_token,
            "refresh_het_luc": het, "con_ngay": None if con is None else round(con, 1),
            "nguoi_cap": r.get("nguoi_cap"), "cap_luc": r.get("cap_luc"),
            "so_tk_thay": thay, "so_tk_truoc": truoc,
            "it_hon": thay is not None and truoc is not None and thay < truoc,
            "lam_moi_luc": r.get("lam_moi_luc"), "goi_ok_luc": r.get("goi_ok_luc"),
            "dong_bo_bat_dau": r.get("dong_bo_bat_dau"), "dong_bo_xong": r.get("dong_bo_xong"),
            "dong_bo_ok_luc": r.get("dong_bo_ok_luc"), "dong_bo_so_dong": r.get("dong_bo_so_dong"),
            "dong_bo_loi": r.get("dong_bo_loi"), "loi_cuoi": r.get("loi_cuoi"),
            "loi_luc": r.get("loi_luc"), "so_den_ngay": r.get("so_den_ngay"),
            "dang_dong_bo": dang, "loi_khoa": self.loi_khoa(), "co_khoa": self.loi_khoa() is None,
            "co_client": bool(r.get("client_id")),
            "yeu_cau_dong_bo_luc": r.get("yeu_cau_dong_bo_luc"), "yeu_cau_boi": r.get("yeu_cau_boi"),
            "yeu_cau_kieu": r.get("yeu_cau_kieu"), "nhanh_xong_luc": r.get("nhanh_xong_luc"),
            "dong_bo_kieu": r.get("dong_bo_kieu"),
        }

    # ── OAuth ──
    def bat_dau(self, redirect_uri: str, state: str) -> tuple[str, str]:
        """Đăng ký client (DCR) nếu chưa có hoặc redirect_uri đổi → (link uỷ quyền, verifier)."""
        self.khoa()
        r = self.kho.doc_ket_noi() or {}
        cid = r.get("client_id")
        if not cid or r.get("redirect_uri") != redirect_uri:
            cid = dang_ky_client(self.http, redirect_uri)
            self.kho.luu_dang_ky(cid, redirect_uri)
        ver, chal = pkce()
        return url_uy_quyen(cid, redirect_uri, chal, state), ver

    def ket_thuc(self, ai: str, code: str, verifier: str, redirect_uri: str) -> dict:
        """Đổi mã → lưu token (mã hoá) → thấy tài khoản. -> {"so_tk_thay", "so_tk_truoc", …}."""
        k = self.khoa()
        r = self.kho.doc_ket_noi() or {}
        cid = r.get("client_id")
        if not cid:
            raise LoiTikTok("chưa đăng ký client — bấm Đăng nhập lại")
        t = doi_ma(self.http, cid, code, verifier, redirect_uri)
        bay = self._bay_gio()
        at, rt = str(t["access_token"]), str(t.get("refresh_token") or "")
        nho_bi_mat(at, rt)
        self.kho.luu_token(
            ai, "mcp_oauth", ma_hoa(at, k, "access"), ma_hoa(rt, k, "refresh") if rt else None,
            bay + datetime.timedelta(seconds=_giay(t.get("expires_in"), AT_MAC_DINH, "expires_in",
                                                   self.log)),
            bay + datetime.timedelta(seconds=_giay(t.get("refresh_token_expires_in"), RT_MAC_DINH,
                                                   "refresh_token_expires_in", self.log))
            if rt else None)
        return self._kham_pha_an_toan(Mcp(at, self.http, self.ngu))

    def luu_api_token(self, ai: str, token: str) -> dict:
        """Token API (không hết hạn): thử MỘT lượt đọc trước, đúng mới lưu."""
        k = self.khoa()
        token = str(token or "").strip()
        if not re.fullmatch(rf"[A-Za-z0-9._\-]{{16,{TRAN_TOKEN}}}", token):
            raise LoiTikTok("token không đúng dạng")
        mcp = Mcp(token, self.http, self.ngu)
        ds = mcp.goi("auth_advertiser_get", {})          # sai token → LoiXacThuc, không lưu
        self.kho.luu_token(ai, "api_token", ma_hoa(token, k, "access"), None, None, None)
        return self._ghi_tk(mcp, ds)

    def ngat(self, ai: str) -> bool:
        """Thu hồi phía TikTok (cố gắng) rồi xoá token trong kho. -> đã thu hồi được không."""
        r = self.kho.doc_ket_noi() or {}
        da = False
        if r.get("access_token_enc") and r.get("loai") != "api_token":
            try:
                k = self.khoa()
                da = thu_hoi(self.http, giai_ma(r["access_token_enc"], k, "access"))
                if r.get("refresh_token_enc"):
                    thu_hoi(self.http, giai_ma(r["refresh_token_enc"], k, "refresh"),
                            "refresh_token")
            except LoiMaHoa:
                da = False
        self.kho.ngat(ai)
        return da

    # ── token ──
    def token(self, ep: bool = False) -> str:
        """Access token dùng được. Làm mới khi còn < `SAT_HAN_GIAY` (6 giờ) hoặc khi `ep` (TikTok
        vừa từ chối giữa lượt). Ném ChuaKetNoi / LoiHetHan / LoiTikTok. Ghi kho CÓ ĐIỀU KIỆN
        (đúng token + cap_luc đã đọc): ngắt / đăng nhập lại giữa lượt không bị ghi đè."""
        r = self.kho.doc_ket_noi() or {}
        if not r.get("access_token_enc"):
            raise ChuaKetNoi("chưa kết nối TikTok Ads")
        neu = (r.get("access_token_enc"), r.get("cap_luc"))
        k = self.khoa()
        if r.get("loai") == "api_token":
            at = giai_ma(r["access_token_enc"], k, "access")
            nho_bi_mat(at)
            if ep:
                raise LoiXacThuc("TikTok từ chối token API (không làm mới được — kiểm token)")
            return at
        bay = self._bay_gio()
        het_at = _utc(r.get("access_het_luc"))
        if not ep and het_at and (het_at - bay).total_seconds() > SAT_HAN_GIAY:
            at = giai_ma(r["access_token_enc"], k, "access")
            nho_bi_mat(at)
            return at
        het_rt = _utc(r.get("refresh_het_luc"))
        if not r.get("refresh_token_enc") or (het_rt and het_rt <= bay):
            self.kho.ghi_trang_thai("het_han", "Hết 30 ngày của lần đăng nhập — quản trị viên "
                                    "bấm “Đăng nhập lại để gia hạn 30 ngày”.", neu=neu)
            raise LoiHetHan("refresh token đã hết hạn")
        rt = giai_ma(r["refresh_token_enc"], k, "refresh")
        nho_bi_mat(rt)
        try:
            t = lam_moi(self.http, r.get("client_id") or "", rt)
        except LoiXacThuc as e:
            self.kho.ghi_trang_thai("het_han", f"TikTok không làm mới được token: {e}", neu=neu)
            raise LoiHetHan(str(e)) from None
        at = str(t["access_token"])
        rt_moi = str(t.get("refresh_token") or "")
        nho_bi_mat(at, rt_moi)
        con = t.get("refresh_token_expires_in")
        het_moi = (bay + datetime.timedelta(seconds=_giay(con, RT_MAC_DINH,
                                                          "refresh_token_expires_in", self.log))
                   if con is not None else None)
        if rt_moi and rt_moi != rt:
            # Token mới thật sự (TikTok đổi cách) → hạn mới.
            rt_enc, het_rt = ma_hoa(rt_moi, k, "refresh"), het_moi or het_rt
        else:
            # Đo 19/10/2026: CÙNG refresh token, hạn tiếp tục đếm lùi — không bao giờ kéo dài hạn.
            rt_enc = None
            het_rt = min(x for x in (het_rt, het_moi) if x) if (het_rt or het_moi) else None
        het_at = bay + datetime.timedelta(seconds=_giay(t.get("expires_in"), AT_MAC_DINH,
                                                        "expires_in", self.log))
        if not self.kho.cap_nhat_token(ma_hoa(at, k, "access"), het_at, rt_enc, het_rt, neu=neu):
            # Quản trị viên ngắt / đăng nhập lại trong lúc làm mới: không ghi đè, dừng lượt.
            raise ChuaKetNoi("kết nối vừa bị ngắt hoặc đăng nhập lại — lượt này dừng")
        return at

    def mcp(self) -> McpTuLamMoi:
        return McpTuLamMoi(self)

    # ── tài khoản ──
    def _ghi_tk(self, mcp: Mcp, ds) -> dict:
        tk = []
        for x in (ds or {}).get("list") or []:
            adv = str(x.get("advertiser_id") or "")
            if re.fullmatch(r"[0-9]{1,30}", adv):
                tk.append({"advertiser_id": adv, "ten": str(x.get("advertiser_name") or "").strip()})
        theo = {t["advertiser_id"]: t for t in tk}
        ids = list(theo)
        for i in range(0, len(ids), 50):
            try:
                info = mcp.goi("advertiser_info_get", {"advertiser_ids": ids[i:i + 50]}) or {}
            except LoiXacThuc:
                raise
            except LoiTikTok as e:          # thiếu tiền tệ/múi giờ không chặn thấy tài khoản
                self.log(f"[tiktok_ads] advertiser_info_get lỗi: {e}")
                continue
            for x in info.get("list") or []:
                t = theo.get(str(x.get("advertiser_id")))
                if t:
                    t["tien_te"] = x.get("currency") or "VND"
                    t["mui_gio"] = x.get("display_timezone") or x.get("timezone") or ""
                    t["ten"] = t["ten"] or str(x.get("name") or "").strip()
        kq = self.kho.ghi_tk(tk)
        self.kho.ghi_goi_ok()
        return kq

    def kham_pha(self, mcp: Mcp) -> dict:
        return self._ghi_tk(mcp, mcp.goi("auth_advertiser_get", {}))

    def _kham_pha_an_toan(self, mcp: Mcp) -> dict:
        try:
            return {"ok": True, **self.kham_pha(mcp)}
        except LoiTikTok as e:
            self.kho.ghi_trang_thai("loi", f"Kết nối xong nhưng chưa đọc được tài khoản: {e}")
            return {"ok": False, "loi": str(e)}

    # ── đồng bộ ──
    def dong_bo(self, *, bu: int | None = None, tu: datetime.date | None = None,
                den: datetime.date | None = None, theo_yeu_cau: bool = False,
                chi_nhanh: bool = False, cho_khoa_giay: float = 0) -> dict:
        """Một lượt đồng bộ (bộ hẹn giờ / nút). Không bao giờ chạy chồng (khoá advisory).
        `theo_yeu_cau` (bộ hẹn giờ 2 phút): yêu cầu đang chờ là loại "nhanh" (người dùng bấm
        "Đồng bộ ngay", 20/10/2026) thì chỉ đọc hôm nay + 2 ngày trước của tài khoản có hiển thị.
        `chi_nhanh` (bộ nghe): chỉ chạy khi cờ đang chờ là nhanh — không bao giờ mở lượt đầy đủ.
        `cho_khoa_giay` (lượt hằng ngày, soát 20/10/2026 H2): lượt khác đang giữ khoá thì CHỜ (thử lại
        mỗi `NHIP_CHO_KHOA` giây) tới chừng ấy giây; hết giờ vẫn không có khoá → {"ban": True}
        (dòng lệnh thoát khác 0, systemd chạy lại) — lượt hằng ngày không bao giờ lặng lẽ mất."""
        r = self.kho.doc_ket_noi() or {}
        loi = self.loi_khoa()
        if loi:
            if r.get("access_token_enc"):
                # Có token mà khoá hỏng/thiếu: không đọc được token — báo rõ trên thẻ.
                self.kho.ghi_trang_thai("loi", f"Không giải mã được token: {loi}")
            return {"bo_qua": loi}
        if not r.get("access_token_enc"):
            self.kho.ghi_trang_thai(r.get("trang_thai") or "chua_ket_noi")
            return {"bo_qua": "chưa kết nối TikTok Ads"}
        return chay_voi_khoa(
            lambda: self.kho.khoa_dong_bo(),
            lambda: self._dong_bo(bu=bu, tu=tu, den=den, theo_yeu_cau=theo_yeu_cau,
                                  chi_nhanh=chi_nhanh),
            cho_khoa_giay, self.ngu, self.log, "tiktok_ads")

    def co_yeu_cau(self) -> bool:
        """Có yêu cầu "Đồng bộ ngay" đang chờ (bộ hẹn giờ 2 phút chỉ chạy khi có)."""
        return bool((self.kho.doc_ket_noi() or {}).get("yeu_cau_dong_bo_luc"))

    def yeu_cau(self, ai: str, kieu: str = "day_du") -> None:
        """Nút "Đồng bộ ngay" / sau khi kết nối: CHỈ ghi cờ yêu cầu. Dashboard không bao giờ tự
        chạy đồng bộ (MemoryMax 512M, khởi động lại giữa chừng) — bộ hẹn giờ
        tiktok-ads-yeu-cau.timer (2 phút/lần) chạy `dong-bo --chi-khi-yeu-cau`. `kieu`: "day_du"
        (quản trị viên: lượt thường, nạp lùi nếu cần) hoặc "nhanh" (mọi người: 3 ngày gần nhất);
        yêu cầu day_du đang chờ không bao giờ bị hạ thành nhanh (`kho_qc.yeu_cau_dong_bo`)."""
        self.kho.yeu_cau_dong_bo(ai, kieu=kieu)

    def dong_bo_tai_khoan(self, ids, tu: datetime.date | None, den: datetime.date | None
                          ) -> dict:
        """Lượt TỨC THÌ theo phạm vi (Mark hỏi số mới, 20/10/2026; bộ nghe `nghe_qc` gọi): CHỈ các
        tài khoản `ids` đang đồng bộ, cửa sổ [tu, den] kẹp vào 7 ngày gồm hôm nay (`cua_so_tuc_thi`).
        Chỉ đọc (report_integrated_get — `Mcp` chặn mọi công cụ ngoài CONG_CU_DOC); không khám phá
        lại tài khoản, không khán giả, KHÔNG đụng cờ yêu cầu / mốc lượt của thẻ kết nối. Cùng khoá
        advisory với lượt thường (không bao giờ chạy chồng).
        -> {"so_dong", "so_tk" (tài khoản đọc được), "so_tk_yeu_cau", "den_ngay", "loi"} |
        {"ban": True, "bo_qua"} | {"bo_qua"}."""
        r = self.kho.doc_ket_noi() or {}
        loi = self.loi_khoa()
        if loi:
            return {"bo_qua": loi}
        if not r.get("access_token_enc"):
            return {"bo_qua": "chưa kết nối TikTok Ads"}
        with self.kho.khoa_dong_bo() as giu:
            if not giu:
                return {"ban": True, "bo_qua": "đang có lượt đồng bộ khác"}
            return self._dong_bo_pham_vi({str(x) for x in ids or ()}, tu, den)

    def _dong_bo_pham_vi(self, ids: set[str], tu, den) -> dict:
        dem = {"so_dong": 0, "so_tk": 0, "so_tk_yeu_cau": len(ids), "den_ngay": None}
        loi = []
        try:
            mcp = self.mcp()
            bay = self._bay_gio()
            for t in self.kho.cac_tk():
                adv = str(t["advertiser_id"])
                if (adv not in ids or (t.get("nen_tang") or "tiktok") != "tiktok"
                        or not t.get("dang_dong_bo") or not t.get("con_quyen", True)):
                    continue
                cs = cua_so_tuc_thi(hom_qua(t.get("mui_gio"), bay), tu, den)
                if cs is None:
                    continue
                try:
                    dem["so_dong"] += self._mot_cua_so(mcp, adv, *cs)
                    dem["so_tk"] += 1
                    dn = dem["den_ngay"]
                    dem["den_ngay"] = max(dn, cs[1]) if dn else cs[1]
                except LoiXacThuc:
                    raise
                except LoiTikTok as e:
                    loi.append(f"{t.get('ten') or adv}: {e}")
                    self.log(f"[tiktok_ads] tức thì {adv} lỗi: {e}")
        except (ChuaKetNoi, LoiHetHan) as e:
            return {**dem, "loi": str(e)}
        except LoiXacThuc as e:
            self.kho.ghi_trang_thai("loi", f"TikTok từ chối token: {e}", con_token=True)
            return {**dem, "loi": f"token bị từ chối: {e}"}
        except (LoiTikTok, LoiMaHoa) as e:
            return {**dem, "loi": str(e)}
        return {**dem, "loi": "; ".join(loi)[:500] or None}

    def _dong_bo(self, *, bu, tu, den, theo_yeu_cau: bool = False, chi_nhanh: bool = False
                 ) -> dict:
        """Bắt đầu lượt (xoá cờ yêu cầu + quyết định loại lượt NGUYÊN TỬ — `kho_qc.bat_dau_dong_bo`)
        rồi chạy; LUÔN kết thúc lượt: khoá/bản mã hỏng → trạng thái loi; ngoại lệ lạ → ghi "dừng
        bất thường" rồi ném tiếp (thẻ không bao giờ kẹt "ổn", dong_bo_xong không bao giờ NULL)."""
        if chi_nhanh:
            kieu = self.kho.bat_dau_dong_bo(cho_nhanh=True, chi_nhanh=True)
            if kieu is None:
                return {"bo_qua": "không có yêu cầu nhanh đang chờ"}
        else:
            kieu = self.kho.bat_dau_dong_bo(cho_nhanh=bool(theo_yeu_cau and not (bu or tu or den)))
        dem = {"tong": 0, "den_ngay": None}
        ket = None
        try:
            ket = self._chay(dem, bu=bu, tu=tu, den=den, nhanh=kieu == "nhanh")
        except LoiMaHoa as e:
            self.kho.ghi_trang_thai("loi", f"Không giải mã được token: {e}", con_token=True)
            ket = (f"không giải mã được token: {e}", {"loi": str(e), "so_dong": dem["tong"]})
        finally:
            if ket is None:
                ten = "lượt dừng bất thường — xem journalctl tiktok-ads-*"
                with contextlib.suppress(Exception):
                    self.kho.ghi_trang_thai("loi", ten, con_token=True)
                with contextlib.suppress(Exception):
                    self.kho.ket_thuc_dong_bo(dem["tong"], ten, dem["den_ngay"])
        self.kho.ket_thuc_dong_bo(dem["tong"], ket[0], dem["den_ngay"])
        return ket[1]

    def _chay(self, dem: dict, *, bu, tu, den, nhanh: bool) -> tuple[str | None, dict]:
        """Thân lượt. -> (chữ lỗi cho ket_thuc_dong_bo | None, kết quả trả). `dem` cập nhật dần."""
        loi = []
        try:
            mcp = self.mcp()
            self.kham_pha(mcp)
            bay = self._bay_gio()
            cap_luc = (self.kho.doc_ket_noi() or {}).get("cap_luc")
            for t in self.kho.cac_tk():
                # 20/10/2026: tk_quang_cao có cả tài khoản Meta (`meta_ads.py` đồng bộ riêng).
                if (t.get("nen_tang") or "tiktok") != "tiktok":
                    continue
                if not t.get("dang_dong_bo") or not t.get("con_quyen", True):
                    continue
                # Quản trị viên ngắt / đăng nhập lại giữa lượt: dừng, không ghi gì thêm.
                r = self.kho.doc_ket_noi() or {}
                if not r.get("access_token_enc") or r.get("cap_luc") != cap_luc:
                    raise ChuaKetNoi("kết nối vừa bị ngắt hoặc đăng nhập lại — lượt này dừng")
                if nhanh and not co_chay_gan(self.kho, t, bay):
                    continue                  # lượt nhanh: chỉ tài khoản có hiển thị 30 ngày
                try:
                    n, d = self._dong_bo_tk(mcp, t, bay, bu=bu, tu=tu, den=den, nhanh=nhanh)
                    dem["tong"] += n
                    dn = dem["den_ngay"]
                    dem["den_ngay"] = max(dn, d) if dn and d else (d or dn)
                except LoiXacThuc:
                    raise
                except LoiTikTok as e:
                    loi.append(f"{t.get('ten') or t['advertiser_id']}: {e}")
                    self.log(f"[tiktok_ads] {t['advertiser_id']} lỗi: {e}")
            self.kho.ghi_trang_thai("hoat_dong", con_token=True)
        except ChuaKetNoi as e:
            return str(e), {"bo_qua": str(e)}
        except LoiHetHan as e:
            return f"hết hạn: {e}", {"bo_qua": "token hết hạn — cần đăng nhập lại",
                                      "so_dong": dem["tong"]}
        except LoiXacThuc as e:
            self.kho.ghi_trang_thai("loi", f"TikTok từ chối token: {e}", con_token=True)
            return f"token bị từ chối: {e}", {"loi": str(e), "so_dong": dem["tong"]}
        except LoiTikTok as e:
            self.kho.ghi_trang_thai("loi", str(e), con_token=True)
            return str(e), {"loi": str(e), "so_dong": dem["tong"]}
        chu_loi = "; ".join(loi)[:500] or None
        return chu_loi, {"so_dong": dem["tong"], "den_ngay": dem["den_ngay"], "loi": chu_loi}

    def _dong_bo_tk(self, mcp: Mcp, t: dict, bay: datetime.datetime, *, bu, tu, den,
                    nhanh: bool = False) -> tuple[int, datetime.date]:
        adv = str(t["advertiser_id"])
        hq = hom_qua(t.get("mui_gio"), bay)
        if nhanh:
            a, b = cua_so_nhanh(hq)
            n = self._mot_cua_so(mcp, adv, a, b)
            self.log(f"[tiktok_ads] {adv} nhanh {a}→{b}: {n} dòng")
            return n, hq
        tuan = hq - datetime.timedelta(days=LUI_NGAY - 1)
        nap_lui = None                         # ngày đầu của đợt nạp lùi (None = không nạp lùi)
        if tu or den:
            a, b = tu or (den or hq) - datetime.timedelta(days=LUI_NGAY - 1), min(den or hq, hq)
            cac = cua_so(a, b)
        elif bu:
            a, b = hq - datetime.timedelta(days=int(bu) - 1), hq
            cac = cua_so(a, b)
        elif not t.get("nap_lui_xong_luc"):
            # Nạp lùi 90 ngày, MỚI TRƯỚC. Mỗi cửa sổ xong thì ghi mốc `nap_lui_tu`: lượt bị ngắt
            # (hết giờ, mất mạng) thì lượt sau chỉ đọc 7 ngày gần nhất + phần còn thiếu.
            a, b = hq - datetime.timedelta(days=NAP_LUI_NGAY - 1), hq
            nap_lui = a
            da = t.get("nap_lui_tu")
            cac = ([(tuan, hq)] + cua_so(a, da - datetime.timedelta(days=1))
                   if isinstance(da, datetime.date) and a < da <= hq else cua_so(a, b))
        else:
            a, b = tuan, hq
            cac = cua_so(a, b)
        n = 0
        for x, y in cac:
            n += self._mot_cua_so(mcp, adv, x, y)
            if nap_lui is not None and (x, y) != (tuan, hq):
                self.kho.dat_nap_lui(adv, x, xong=x <= nap_lui)
        n += self._khan_gia(mcp, t, hq, bay)
        self.log(f"[tiktok_ads] {adv} {a}→{b}: {n} dòng")
        return n, b

    def _mot_cua_so(self, mcp: Mcp, adv: str, a: datetime.date, b: datetime.date) -> int:
        rows = bao_cao(mcp, adv, "AUCTION_ADVERTISER", ["advertiser_id", "stat_time_day"],
                       QC.CHI_SO_HOP_LE, a, b)
        ngay = [x for x in (dong_tk(r, adv) for r in rows) if x["ngay"] and co_phan_phoi(x)]
        n = self.kho.ghi_tk_ngay(ngay)
        if not ngay:
            return n                          # không phân phối trong cửa sổ: bỏ campaign/ad
        for cap, dim, chi_so, dong, ghi in (
                ("AUCTION_CAMPAIGN", "campaign_id",
                 QC.THUOC_TINH_CAMPAIGN + QC.CHI_SO_HOP_LE, dong_campaign,
                 self.kho.ghi_campaign_ngay),
                ("AUCTION_AD", "ad_id", QC.THUOC_TINH_AD_GIU + QC.CHI_SO_AD, dong_ad,
                 self.kho.ghi_ad_ngay)):
            for ids in lo_id(ids_co_chay(mcp, adv, cap, dim, a, b)):
                rows = bao_cao(mcp, adv, cap, [dim, "stat_time_day"], chi_so, a, b,
                               loc=bo_loc_id(dim, ids))
                n += ghi([x for x in (dong(r, adv) for r in rows)
                          if x["ngay"] and co_phan_phoi(x)])
        return n

    def _khan_gia(self, mcp: Mcp, t: dict, hq: datetime.date, bay: datetime.datetime) -> int:
        luc = _utc(t.get("khan_gia_luc"))
        if luc and (bay - luc).days < KHAN_GIA_NGAY:
            return 0
        adv = str(t["advertiser_id"])
        a = hq - datetime.timedelta(days=CUA_SO_NGAY - 1)
        if not ((self.kho.qc_tong([adv], a, hq) or {}).get("hien_thi") or 0):
            return 0                          # không chạy 30 ngày: không có khán giả để đọc
        n = 0
        for chieu in QC.CHIEU_KHAN_GIA:
            rows = bao_cao(mcp, adv, "AUCTION_ADVERTISER", ["advertiser_id", chieu],
                           QC.CHI_SO_KHAN_GIA, a, hq, loai="AUDIENCE")
            n += self.kho.ghi_khan_gia([dong_khan_gia(r, adv, a, hq, chieu) for r in rows])
        self.kho.dat_khan_gia(adv)
        return n


# ───────────────────────────── dòng lệnh (bộ hẹn giờ) ─────────────────────────────
def _ngay_tham_so(s: str) -> datetime.date:
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError("ngày dạng YYYY-MM-DD") from None


def nhanh_trong_gio_dong_bo(dv, ncc: str, bay: datetime.datetime | None = None) -> bool:
    """Cờ đang chờ là lượt NHANH và đang trong khung đồng bộ hằng ngày (06:25–07:30) → để sau."""
    r = dv.kho.doc_ket_noi(ncc) or {}
    if bay is None and callable(getattr(dv, "_bay_gio", None)):
        bay = dv._bay_gio()
    return r.get("yeu_cau_kieu") == "nhanh" and QC.trong_gio_dong_bo(bay)


def tuc_thi_du_phong(ncc: str, dv, bat: bool) -> None:
    """Bộ hẹn giờ 2 phút cũng xử lý hàng chờ số tức thì của Mark (`nghe_qc.xu_ly_cho`) — dự phòng
    khi bộ nghe `*-ads-nghe` chết / chưa cài. `bat` False (bộ thử truyền dịch vụ giả) → bỏ qua.
    Lỗi (bảng chưa tạo…) chỉ in một dòng stderr, không làm đỏ lượt."""
    if not bat:
        return
    try:
        from dashboard import nghe_qc
        kq = nghe_qc.xu_ly_cho(ncc, dv, log=lambda *_: None)
        if not kq.get("khong_co"):
            print(f"[{ncc}] tức thì: {json.dumps(kq, ensure_ascii=False, default=str)[:300]}")
    except Exception as e:  # noqa: BLE001
        print(f"[{ncc}] tức thì lỗi: {type(e).__name__}: {gon_loi(e)}", file=sys.stderr)


def main(argv: list[str] | None = None, dich_vu: DichVu | None = None, dong_bo_bq=None) -> int:
    p = argparse.ArgumentParser(prog="python -m dashboard.tiktok_ads",
                                description="Đồng bộ TikTok Ads vào kho lang_nghe.")
    sub = p.add_subparsers(dest="lenh", required=True)
    d = sub.add_parser("dong-bo", help="một lượt đồng bộ (bộ hẹn giờ gọi lệnh này)")
    d.add_argument("--bu", type=int, help="nạp lại N ngày gần nhất (≤ 400)")
    d.add_argument("--tu", type=_ngay_tham_so)
    d.add_argument("--den", type=_ngay_tham_so)
    d.add_argument("--khong-bq", action="store_true", help="không đẩy BigQuery sau khi xong")
    d.add_argument("--chi-khi-yeu-cau", action="store_true",
                   help="chỉ chạy khi có yêu cầu \"Đồng bộ ngay\" đang chờ (bộ hẹn giờ 2 phút)")
    d.add_argument("--cho-khoa-phut", type=int, default=30,
                   help="lượt hằng ngày: lượt khác đang giữ khoá thì chờ tối đa N phút (mặc định "
                        "30), quá thì thoát 3 để systemd chạy lại")
    sub.add_parser("trang-thai", help="in trạng thái kết nối (không in token)")
    a = p.parse_args(argv)
    try:
        dv = dich_vu or DichVu()
        if a.lenh == "trang-thai":
            print(json.dumps(dv.the(), ensure_ascii=False, default=str, indent=1))
            return 0
        if a.bu is not None and not 1 <= a.bu <= 400:
            p.error("--bu trong 1..400")
        if a.chi_khi_yeu_cau:
            tuc_thi_du_phong(NCC, dv, dich_vu is None)
            if dv.co_yeu_cau() and nhanh_trong_gio_dong_bo(dv, NCC):
                return 0                      # khung đồng bộ hằng ngày: lượt nhanh đợi sau 07:30
        if a.chi_khi_yeu_cau and not dv.co_yeu_cau():
            return 0                          # không có yêu cầu: thoát ngay, không in gì
        kq = dv.dong_bo(bu=a.bu, tu=a.tu, den=a.den, theo_yeu_cau=a.chi_khi_yeu_cau,
                        cho_khoa_giay=0 if a.chi_khi_yeu_cau else max(0, a.cho_khoa_phut) * 60)
    except LoiMaHoa as e:
        print(f"[tiktok_ads] {e}", file=sys.stderr)
        return 0                              # chưa cấu hình: im lặng, không làm đỏ systemd
    except Exception as e:  # noqa: BLE001 — kho chưa dùng được…: báo lỗi, mã thoát 1
        print(f"[tiktok_ads] lỗi: {type(e).__name__}: {gon_loi(e)}", file=sys.stderr)
        return 1
    print(f"[tiktok_ads] {json.dumps(kq, ensure_ascii=False, default=str)}")
    if kq.get("ban") and not a.chi_khi_yeu_cau:
        # Soát 20/10/2026 H2: lượt hằng ngày KHÔNG được lặng lẽ mất vì lượt nhỏ đang giữ khoá.
        print(f"[tiktok_ads] chờ {a.cho_khoa_phut} phút vẫn chưa giữ được khoá đồng bộ — thoát 3 "
              "(systemd Restart=on-failure chạy lại)", file=sys.stderr)
        return 3
    if kq.get("so_dong") and not a.khong_bq:
        if dong_bo_bq is None:
            from dashboard import dong_bo_bq
        if dong_bo_bq.da_bat():
            try:
                bq = dong_bo_bq.chay()
                print(f"[tiktok_ads] BigQuery: {json.dumps(bq, ensure_ascii=False, default=str)[:500]}")
            except Exception as e:  # noqa: BLE001 — BigQuery còn nhịp 6 giờ của dashboard
                print(f"[tiktok_ads] BigQuery lỗi: {type(e).__name__}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
