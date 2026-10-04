"""Đọc bình luận trên kênh CỦA CHÍNH HAPAS qua API chính thức của Meta — phần mạng + token.

Vì sao có (04/10/2026): `social_deep_dive` bóc Threads/Instagram KHÔNG đăng nhập qua
Apify — Instagram chỉ được một phần bình luận (đo thật 8/18), không có trả lời lồng
nhau, và tốn tiền. Với bài của CHÍNH HAPAS thì Meta cho đọc đủ bằng token của chủ kênh:
miễn phí, đủ bình luận, đủ trả lời mọi cấp. Tool `binh_luan_kenh_nha` (kenh_nha_tool.py)
dùng module này; bài của đối thủ vẫn phải đi `social_deep_dive`.

API và phiên bản ghim (đọc tài liệu chính thức 04/10/2026):
  • Threads: graph.threads.net/v1.0 — `/me`, `/me/threads`, `/{media}/conversation`
    (mọi trả lời ở mọi cấp, danh sách phẳng, có `replied_to`/`root_post`). Trả lời
    KHÔNG có trường lượt thích (like chỉ có qua insights) — cột Likes để 0, nói rõ.
  • Instagram API with Instagram Login: graph.instagram.com/v26.0 — `/me/media`,
    `/{media}/comments` (kèm `replies{…}`), `/{comment}/replies`.
  • Facebook Page: graph.facebook.com/v26.0 — `/{page}/posts`, `/{post}/comments`
    với `filter=stream` (mọi cấp, phẳng, có `parent`).
  Graph API v26.0 ra 29/07/2026; v25.0 hết hạn 29/07/2028. Đổi bằng META_GRAPH_VERSION.

Token (không bao giờ in ra; mọi chuỗi lỗi/log đi qua `che`):
  • `.env` giữ token GỐC chủ agent dán. Token đã đổi/làm mới nằm ở
    `.tokens/meta_kenh_nha.json` (thư mục trạng thái, đã gitignore, VPS giữ khi deploy) —
    KHÔNG ghi ngược vào `.env`. Dán token mới vào `.env` (khác dấu vân tay) thì nạp lại.
  • Threads: `th_exchange_token` (ngắn → 60 ngày) rồi `th_refresh_token`.
    Instagram: `ig_exchange_token` rồi `ig_refresh_token`. Làm mới khi còn < 10 ngày
    (Meta chỉ cho làm mới token ≥ 24 giờ tuổi, chưa hết hạn).
  • Facebook: token Page lấy từ token user DÀI HẠN thì không hết hạn. Dán token user
    hay token Page đều được: `debug_token` nói loại; token user thì đổi dài hạn rồi lấy
    token Page của FB_PAGE_ID.
  • Thiếu giá trị trong `.env` → kênh đó "chưa nối", không bao giờ làm sập tool.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import threading
import time
import urllib.parse
from pathlib import Path

import requests

PHIEN_BAN_GRAPH = (os.environ.get("META_GRAPH_VERSION") or "v26.0").strip()
PHIEN_BAN_THREADS = "v1.0"
GOC = {
    "threads": f"https://graph.threads.net/{PHIEN_BAN_THREADS}",
    "instagram": f"https://graph.instagram.com/{PHIEN_BAN_GRAPH}",
    "facebook": f"https://graph.facebook.com/{PHIEN_BAN_GRAPH}",
}
# Endpoint token của Threads/Instagram KHÔNG có phiên bản trong đường dẫn (theo tài liệu).
_GOC_TOKEN = {"threads": "https://graph.threads.net", "instagram": "https://graph.instagram.com"}

KENH = ("threads", "instagram", "facebook")
TEN = {"threads": "Threads", "instagram": "Instagram", "facebook": "Facebook"}
ENV_TOKEN = {"threads": "THREADS_ACCESS_TOKEN", "instagram": "IG_ACCESS_TOKEN",
             "facebook": "FB_PAGE_ACCESS_TOKEN"}
_ENV_BI_MAT = ("META_APP_SECRET", "THREADS_ACCESS_TOKEN", "IG_ACCESS_TOKEN",
               "FB_PAGE_ACCESS_TOKEN")

NGAY = 86400
_LAM_MOI_KHI_CON = 10 * NGAY     # còn ít hơn chừng này thì làm mới
_TUOI_TOI_THIEU = NGAY           # Meta: token phải ≥ 24 giờ tuổi mới làm mới được
_THU_LAI_SAU = 6 * 3600          # làm mới hỏng thì 6 giờ sau mới thử lại
_HAN_HTTP = 20

# Tệp trạng thái token: cùng thư mục `.tokens/` với bot.json, sổ chi phí, audit.
TEP_TOKEN = Path(__file__).resolve().with_name(".tokens") / "meta_kenh_nha.json"
_KHOA = threading.RLock()


class LoiKenh(RuntimeError):
    """Lỗi của MỘT kênh. `ma`: CHUA_NOI | TOKEN_HONG | HET_HAN | QUYEN | GIOI_HAN | MANG | LOI.
    Chuỗi lỗi đã qua `che` — đưa thẳng cho model được."""

    def __init__(self, kenh: str, ma: str, thong_diep: str):
        super().__init__(che(thong_diep))
        self.kenh, self.ma = kenh, ma


# ───────────────────────── che bí mật ─────────────────────────
_RE_THAM_SO = re.compile(
    r"(?i)((?:access_token|client_secret|input_token|fb_exchange_token|appsecret_proof)"
    r"(?:=|%3D|\"\s*:\s*\"|'\s*:\s*'))[^&\s'\"]+")
# Hình dạng token Meta (EAA… Facebook, IGAA…/IGQ… Instagram, THAA…/TH… Threads): lớp chặn
# cuối cho token lạ chưa nằm trong danh sách đã biết.
_RE_HINH_TOKEN = re.compile(r"\b(?:EAA|IGAA|IGQ|THAA|THQ)[A-Za-z0-9_\-]{20,}")
_DA_BIET: set[str] = set()       # token đã thấy trong phiên (đổi/làm mới) — che luôn


def _bi_mat() -> set[str]:
    s = {os.environ.get(k, "").strip() for k in _ENV_BI_MAT} | set(_DA_BIET)
    app = _app_token()
    if app:
        s.add(app)
    return {x for x in s if len(x) >= 6}


def che(s) -> str:
    """Che MỌI token/secret Meta khỏi chuỗi trước khi nó tới model, log hay audit —
    cùng vai trò `apify_tool._che_token`. Chuỗi lỗi của `requests` chứa nguyên URL."""
    s = str(s)
    for x in sorted(_bi_mat(), key=len, reverse=True):
        s = s.replace(x, "***").replace(urllib.parse.quote(x, safe=""), "***")
    s = _RE_THAM_SO.sub(r"\1***", s)
    return _RE_HINH_TOKEN.sub("***", s)


def ghi_log(thong_diep: str) -> None:
    """Log ra stdout (journal của systemd trên VPS) — luôn qua `che`."""
    print(f"[kenh_nha] {che(thong_diep)}", flush=True)


# ───────────────────────── HTTP ─────────────────────────
def _http_get(url: str, params: dict | None, timeout: float) -> tuple[int, dict]:
    """Một GET; trả (mã HTTP, JSON). Bộ thử thay hàm này."""
    r = requests.get(url, params=params or {}, timeout=timeout)
    try:
        d = r.json()
    except ValueError:
        d = {"error": {"message": (r.text or "")[:200], "code": -1}}
    return r.status_code, d if isinstance(d, dict) else {"data": d}


# Mã lỗi Graph API → mã của mình.
_MA_GIOI_HAN = {4, 17, 32, 613, 80001, 80002, 80004, 80005, 80006, 80008}


def _phan_loai_loi(kenh: str, ma_http: int, loi: dict) -> LoiKenh:
    code = loi.get("code")
    sub = loi.get("error_subcode")
    tin = str(loi.get("message") or loi.get("error_user_msg") or "")[:240]
    if code == 190:
        ma = "HET_HAN" if sub == 463 or "expired" in tin.lower() else "TOKEN_HONG"
    elif code in (10, 3) or (isinstance(code, int) and 200 <= code < 300):
        ma = "QUYEN"
    elif code in _MA_GIOI_HAN or ma_http == 429:
        ma = "GIOI_HAN"
    else:
        ma = "LOI"
    return LoiKenh(kenh, ma, f"{TEN[kenh]} API {ma_http} (mã {code}"
                             + (f"/{sub}" if sub else "") + f"): {tin}")


def goi(kenh: str, duong: str, params: dict, token: str, goc: str | None = None) -> dict:
    """GET một endpoint Graph của `kenh` bằng `token`. Lỗi → `LoiKenh` (đã che)."""
    url = duong if duong.startswith("http") else f"{goc or GOC[kenh]}/{duong.lstrip('/')}"
    p = dict(params or {})
    p["access_token"] = token
    if kenh == "facebook" and "|" not in token and os.environ.get("META_APP_SECRET", "").strip():
        # appsecret_proof: Meta khuyên dùng cho gọi từ máy chủ (bắt buộc nếu app bật
        # "Require App Secret").
        p["appsecret_proof"] = hmac.new(os.environ["META_APP_SECRET"].strip().encode(),
                                        token.encode(), hashlib.sha256).hexdigest()
    try:
        ma, d = _http_get(url, p, _HAN_HTTP)
    except requests.RequestException as e:
        raise LoiKenh(kenh, "MANG", f"{TEN[kenh]}: lỗi mạng {type(e).__name__}: {e}") from None
    if ma >= 400 or (isinstance(d.get("error"), dict)):
        raise _phan_loai_loi(kenh, ma, d.get("error") if isinstance(d.get("error"), dict)
                             else {"message": str(d)[:200]})
    return d


def phan_trang(kenh: str, duong: str, params: dict, token: str, toi_da: int,
               han: float | None = None, dung=None) -> tuple[list[dict], bool]:
    """Đọc mọi trang của một edge theo con trỏ `after` (không đi theo `paging.next` —
    URL đó chứa token). -> (các dòng, còn trang chưa đọc?). `dung(dong)` trả True thì
    dừng (vd bài đã cũ hơn khoảng ngày)."""
    ra: list[dict] = []
    p = dict(params)
    for _ in range(1000):
        if han is not None and time.monotonic() > han:
            return ra, True
        d = goi(kenh, duong, p, token)
        pg = d.get("paging") or {}
        dl = d.get("data") or []
        for i, x in enumerate(dl):
            if dung and dung(x):
                return ra, False
            ra.append(x)
            if len(ra) >= toi_da:
                return ra, i < len(dl) - 1 or bool(pg.get("next"))
        sau = (pg.get("cursors") or {}).get("after")
        if not pg.get("next") or not sau or sau == p.get("after"):
            return ra, False
        p["after"] = sau
    return ra, True


# ───────────────────────── sổ token ─────────────────────────
def _app_token() -> str:
    a, s = os.environ.get("META_APP_ID", "").strip(), os.environ.get("META_APP_SECRET", "").strip()
    return f"{a}|{s}" if a and s else ""


def _van_tay(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()[:16]


def doc_so() -> dict:
    try:
        d = json.loads(TEP_TOKEN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    for e in d.values():
        if isinstance(e, dict) and e.get("token"):
            _DA_BIET.add(str(e["token"]))
    return d


def ghi_so(d: dict) -> None:
    TEP_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    tam = TEP_TOKEN.with_suffix(".tmp")
    tam.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        os.chmod(tam, 0o600)
    except OSError:
        pass
    os.replace(tam, TEP_TOKEN)


def thieu_cau_hinh(kenh: str) -> str:
    """Tên khoá `.env` còn trống của kênh ("" = đủ để thử)."""
    thieu = [] if os.environ.get(ENV_TOKEN[kenh], "").strip() else [ENV_TOKEN[kenh]]
    if kenh == "facebook" and not os.environ.get("FB_PAGE_ID", "").strip():
        thieu.append("FB_PAGE_ID")
    return ", ".join(thieu)


def _doi_dai_han(kenh: str, ngan: str) -> dict | None:
    """Threads/IG: token ngắn → dài hạn 60 ngày. None nếu không đổi được (thiếu secret,
    hoặc token vốn đã dài hạn — Meta từ chối, đó là chuyện bình thường)."""
    secret = os.environ.get("META_APP_SECRET", "").strip()
    if not secret:
        return None
    grant = "th_exchange_token" if kenh == "threads" else "ig_exchange_token"
    try:
        return goi(kenh, "access_token", {"grant_type": grant, "client_secret": secret},
                   ngan, goc=_GOC_TOKEN[kenh])
    except LoiKenh:
        return None


def _lam_moi(kenh: str, token: str) -> dict:
    grant = "th_refresh_token" if kenh == "threads" else "ig_refresh_token"
    return goi(kenh, "refresh_access_token", {"grant_type": grant}, token,
               goc=_GOC_TOKEN[kenh])


def _muc_tu_tra_loi(kenh: str, d: dict, van_tay: str, bay_gio: int, loai: str) -> dict:
    tok = str(d.get("access_token") or "")
    if not tok:
        raise LoiKenh(kenh, "LOI", f"{TEN[kenh]}: Meta không trả access_token")
    _DA_BIET.add(tok)
    het = d.get("expires_in")
    return {"token": tok, "loai": loai, "env": van_tay, "lay_luc": bay_gio,
            "het_han": bay_gio + int(het) if isinstance(het, (int, float)) and het else None}


def _khoi_tao_th_ig(kenh: str, goc_env: str, van_tay: str, bay_gio: int) -> dict:
    d = _doi_dai_han(kenh, goc_env)
    if d:
        e = _muc_tu_tra_loi(kenh, d, van_tay, bay_gio, "dai_han")
        ghi_log(f"{TEN[kenh]}: đã đổi token ngắn hạn sang dài hạn (còn "
                f"{_con_ngay(e, bay_gio)} ngày).")
        return e
    try:
        e = _muc_tu_tra_loi(kenh, _lam_moi(kenh, goc_env), van_tay, bay_gio, "dai_han")
        ghi_log(f"{TEN[kenh]}: token trong .env là dài hạn, đã làm mới (còn "
                f"{_con_ngay(e, bay_gio)} ngày).")
        return e
    except LoiKenh as loi:
        if loi.ma in ("HET_HAN", "TOKEN_HONG"):
            raise
    # Token dài hạn vừa tạo (< 24 giờ) chưa làm mới được: dùng nguyên, 24 giờ sau thử lại.
    return {"token": goc_env, "loai": "khong_ro", "env": van_tay, "lay_luc": bay_gio,
            "het_han": None}


def _khoi_tao_fb(goc_env: str, van_tay: str, bay_gio: int) -> dict:
    page_id = os.environ.get("FB_PAGE_ID", "").strip()
    app = _app_token()
    if not app:
        return {"token": goc_env, "loai": "khong_ro", "env": van_tay, "lay_luc": bay_gio,
                "het_han": None}
    info = (goi("facebook", "debug_token", {"input_token": goc_env}, app).get("data") or {})
    if info.get("is_valid") is False:
        raise LoiKenh("facebook", "TOKEN_HONG", "Facebook: token trong .env không còn hợp lệ "
                      "(debug_token is_valid=false)")
    loai_tok = str(info.get("type") or "").upper()
    het = int(info.get("expires_at") or 0)
    if loai_tok == "USER":
        tok_user = goc_env
        if het:
            d = goi("facebook", "oauth/access_token", {
                "grant_type": "fb_exchange_token", "client_id": os.environ["META_APP_ID"].strip(),
                "client_secret": os.environ["META_APP_SECRET"].strip(),
                "fb_exchange_token": goc_env}, goc_env)
            tok_user = str(d.get("access_token") or goc_env)
            _DA_BIET.add(tok_user)
        page = goi("facebook", page_id, {"fields": "access_token"}, tok_user)
        tok = str(page.get("access_token") or "")
        if not tok:
            raise LoiKenh("facebook", "QUYEN", f"Facebook: token user không quản lý Trang "
                                               f"{page_id} (không lấy được token Trang)")
        _DA_BIET.add(tok)
        ghi_log("Facebook: đã lấy token Trang từ token user dài hạn (không hết hạn).")
        return {"token": tok, "loai": "vinh_vien", "env": van_tay, "lay_luc": bay_gio,
                "het_han": None}
    if het == 0:
        return {"token": goc_env, "loai": "vinh_vien", "env": van_tay, "lay_luc": bay_gio,
                "het_han": None}
    ghi_log(f"Facebook: token Trang trong .env CÓ HẠN (còn {max(0, het - bay_gio) // NGAY} "
            f"ngày) — nên dán token USER dài hạn để lấy token Trang không hết hạn.")
    return {"token": goc_env, "loai": "co_han", "env": van_tay, "lay_luc": bay_gio,
            "het_han": het}


def _con_ngay(e: dict, bay_gio: int) -> int | None:
    return None if not e.get("het_han") else max(0, int(e["het_han"]) - bay_gio) // NGAY


def can_lam_moi(kenh: str, e: dict, bay_gio: int) -> bool:
    """Lịch làm mới: Threads/IG, token ≥ 24 giờ tuổi, còn < 10 ngày (hoặc chưa biết hạn),
    và lần thử hỏng gần nhất đã qua 6 giờ."""
    if kenh not in _GOC_TOKEN or e.get("loai") == "vinh_vien":
        return False
    if bay_gio - int(e.get("lay_luc") or 0) < _TUOI_TOI_THIEU:
        return False
    if bay_gio - int(e.get("thu_luc") or 0) < _THU_LAI_SAU:
        return False
    het = e.get("het_han")
    return het is None or int(het) - bay_gio < _LAM_MOI_KHI_CON


def lay_token(kenh: str, bay_gio: int | None = None) -> str:
    """Token dùng được cho `kenh`, tự đổi/làm mới theo lịch. Lỗi → `LoiKenh`, không ném gì khác."""
    bay_gio = int(time.time()) if bay_gio is None else bay_gio
    thieu = thieu_cau_hinh(kenh)
    if thieu:
        raise LoiKenh(kenh, "CHUA_NOI", f"kênh {TEN[kenh]} chưa nối (.env thiếu {thieu})")
    goc_env = os.environ[ENV_TOKEN[kenh]].strip()
    vt = _van_tay(goc_env)
    with _KHOA:
        so = doc_so()
        e = so.get(kenh) if isinstance(so.get(kenh), dict) else None
        doi = False
        if not e or e.get("env") != vt or not e.get("token"):
            try:
                e = (_khoi_tao_fb(goc_env, vt, bay_gio) if kenh == "facebook"
                     else _khoi_tao_th_ig(kenh, goc_env, vt, bay_gio))
            except LoiKenh as loi:
                ghi_log(f"{TEN[kenh]}: nạp token thất bại — {loi}")
                raise
            doi = True
        if e.get("het_han") and int(e["het_han"]) <= bay_gio:
            raise LoiKenh(kenh, "HET_HAN", f"token {TEN[kenh]} đã hết hạn")
        if can_lam_moi(kenh, e, bay_gio):
            try:
                moi = _muc_tu_tra_loi(kenh, _lam_moi(kenh, e["token"]), vt, bay_gio, "dai_han")
                e = moi
                ghi_log(f"{TEN[kenh]}: đã làm mới token (còn {_con_ngay(e, bay_gio)} ngày).")
            except LoiKenh as loi:
                e = {**e, "thu_luc": bay_gio, "loi_lam_moi": str(loi)[:200]}
                ghi_log(f"{TEN[kenh]}: làm mới token thất bại — {loi}")
            doi = True
        if doi:
            so[kenh] = e
            try:
                ghi_so(so)
            except OSError as loi:
                ghi_log(f"không ghi được sổ token: {type(loi).__name__}")
        return str(e["token"])


def tinh_trang(bay_gio: int | None = None) -> dict:
    """Tình trạng từng kênh KHÔNG gọi mạng (cho `chi_uoc_tinh`)."""
    bay_gio = int(time.time()) if bay_gio is None else bay_gio
    so = doc_so()
    ra = {}
    for k in KENH:
        thieu = thieu_cau_hinh(k)
        if thieu:
            ra[k] = {"noi": False, "trang_thai": f"chưa nối kênh (.env thiếu {thieu})"}
            continue
        e = so.get(k) if isinstance(so.get(k), dict) else None
        if not e or e.get("env") != _van_tay(os.environ[ENV_TOKEN[k]].strip()):
            ra[k] = {"noi": True, "trang_thai": "đã có token, chưa dùng lần nào"}
            continue
        c = _con_ngay(e, bay_gio)
        ra[k] = {"noi": True, "con_ngay": c, "trang_thai": (
            "token không hết hạn" if e.get("loai") == "vinh_vien"
            else "token ĐÃ HẾT HẠN" if c == 0 and e.get("het_han")
            else f"token còn {c} ngày" if c is not None else "token chưa rõ hạn")}
    return ra


def lam_moi_tat_ca() -> dict:
    """Kiểm + làm mới token mọi kênh đã nối (luồng nền gọi mỗi 12 giờ)."""
    ra = {}
    for k in KENH:
        if thieu_cau_hinh(k):
            continue
        try:
            lay_token(k)
            ra[k] = "ok"
        except LoiKenh as e:
            ra[k] = f"{e.ma}: {e}"
        except Exception as e:  # noqa: BLE001 — luồng nền không được chết
            ra[k] = che(f"{type(e).__name__}: {e}")
            ghi_log(f"{TEN[k]}: lỗi khi kiểm token — {ra[k]}")
    return ra


def chay_luong_lam_moi(chu_ky: float = 12 * 3600, tre: float = 90) -> threading.Thread:
    """Luồng nền: token Threads/IG sống 60 ngày, Mark có thể không đọc kênh nhà suốt hai
    tháng — không làm mới định kỳ thì token chết im lặng."""
    def vong():
        time.sleep(tre)
        while True:
            try:
                lam_moi_tat_ca()
            except Exception as e:  # noqa: BLE001
                ghi_log(f"luồng làm mới token lỗi: {type(e).__name__}")
            time.sleep(chu_ky)
    t = threading.Thread(target=vong, name="kenh_nha_token", daemon=True)
    t.start()
    return t
