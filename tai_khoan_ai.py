"""Mark chạy bằng tài khoản AI được gán trên console platform.

VÌ SAO CÓ
Trước đây Mark luôn gọi model bằng tài khoản Codex cá nhân đăng nhập trên máy này
(`HERMES_HOME/auth.json`) — đổi tài khoản trên console không có tác dụng gì. Module này
xin "lease" từ platform (`POST /v1/self/model-auth/lease`) và dựng runtime Hermes từ đó.

ĐƯỜNG ĐI
  lease subscription · provider "anthropic" → runtime anthropic_messages, token OAuth
                                              chỉ nằm trong RAM
  lease subscription · provider "openai"    → runtime codex_responses từ access_token
                                              (KHÔNG ghi auth.json — xem dưới)
  mode "api" / provider lạ / lỗi lease / lỗi dựng runtime
                                            → đường CŨ y nguyên: resolve_runtime_provider
                                              (requested=config.agent_provider)
  MARK_THEO_TAI_KHOAN_CONSOLE=0             → luôn đường cũ, không lease, không ghi sổ

VÌ SAO KHÔNG GHI auth.json
Platform tự gia hạn token OpenAI lúc phát lease. Nếu Hermes ở máy này cũng cầm cùng
refresh_token và tự gia hạn, hai bên sẽ lần lượt vô hiệu hoá token của nhau. Nên token
console chỉ sống trong bộ nhớ, và agent dựng từ nó bị tắt đường tự gia hạn của Hermes
(`gan_vao_agent`) — Hermes mà tự đọc lại thông tin đăng nhập thì nó lấy ĐÚNG tài khoản
cá nhân của máy (~/.claude/.credentials.json hoặc auth.json), âm thầm đổi tài khoản giữa
lượt.

BÁO LỖI — CHỈ TỪ DỮ LIỆU CÓ CẤU TRÚC
`phan_loai_that_bai` quyết định từ: exception thật (status_code / tên lớp của SDK),
`failure_reason` của Hermes, và (status_code, reason) mà bộ phân loại lỗi của Hermes đưa
vào `_invoke_api_request_error_hook` — KHÔNG BAO GIỜ từ chữ trong câu trả lời. Chữ thì
người dùng bảo model viết gì cũng được ("API call failed … 401 …"), mà "auth_error" làm
platform VÔ HIỆU HOÁ hẳn credential dùng chung. Hết hạn mức → "limit" (nghỉ 5h); 401 →
"auth_error"; 403 → không báo, chỉ chạy lượt đó bằng máy. Lượt chạy bằng máy không bao
giờ báo.

Không bao giờ in/ghi secret. Label của lease có thể là email chủ tài khoản → không giữ,
không hiện. Người dùng chỉ thấy tên chung (`ten_hien_thi`); log/sổ dùng provider +
credential_id.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import threading
import time
import urllib.request
from urllib.parse import urlparse

import lsr_platform
from config import config

__all__ = [
    "bao_loi",
    "bat",
    "chon_runtime",
    "chon_runtime_may",
    "gan_vao_agent",
    "ghi_luot",
    "mo_ta_luot_gan_nhat",
    "phan_loai_that_bai",
    "ten_hien_thi",
    "xoa_cache",
]

_HERE = pathlib.Path(__file__).resolve().parent
# Thư mục CON: bộ chạy hồi quy đọc file .audit/*.jsonl mới nhất ở cấp trên cùng.
_SO_DIR = _HERE / ".audit" / "tai-khoan"
_VN = datetime.timezone(datetime.timedelta(hours=7))

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
CODEX_BASE_URL_MAC_DINH = "https://chatgpt.com/backend-api/codex"


def bat() -> bool:
    """Cờ MARK_THEO_TAI_KHOAN_CONSOLE: mặc định bật; "0" = đường cũ y nguyên."""
    return (os.environ.get("MARK_THEO_TAI_KHOAN_CONSOLE", "1") or "1").strip() != "0"


def _ttl() -> float:
    try:
        return max(0.0, float(os.environ.get("MARK_LEASE_TTL", "60")))
    except ValueError:
        return 60.0


def _model_anthropic() -> str:
    return (os.environ.get("MARK_MODEL_ANTHROPIC") or "claude-sonnet-4-6").strip()


# ───────────────────────────── lease + cache ─────────────────────────────
_KHOA = threading.Lock()
_CACHE: dict = {}      # {"luc": monotonic, "lease": dict | None, "vi_sao": str}


def xoa_cache() -> None:
    with _KHOA:
        _CACHE.clear()


def _lay_lease() -> tuple[dict | None, str]:
    """Lease từ cache nếu còn hạn, không thì xin mới. Lỗi cũng được nhớ trong TTL —
    platform sập thì không bắt từng lượt chờ 15 giây timeout."""
    with _KHOA:
        if _CACHE and time.monotonic() - _CACHE["luc"] < _ttl():
            return _CACHE["lease"], _CACHE["vi_sao"]
        try:
            lease, vi_sao = lsr_platform._xin_lease()
        except Exception as e:  # _xin_lease đã tự nuốt lỗi; đây chỉ là chốt chặn
            lease, vi_sao = None, type(e).__name__
        if lease is not None and not isinstance(lease, dict):
            lease, vi_sao = None, "lease không phải object"
        _CACHE.update({"luc": time.monotonic(), "lease": lease, "vi_sao": vi_sao})
        return lease, vi_sao


# ───────────────────────────── dựng runtime ─────────────────────────────

def chon_runtime_may(ly_do: str = "") -> tuple[dict, str, dict]:
    """Đường CŨ, đúng từng chữ: tài khoản Hermes đăng nhập trên máy này."""
    from hermes_cli.runtime_provider import resolve_runtime_provider

    rt = resolve_runtime_provider(requested=config.agent_provider)
    nguon = {"credential_id": None, "provider": config.agent_provider, "mode": "may",
             "tu": "may", "ly_do": ly_do}
    return rt, config.agent_model, nguon


def _runtime_anthropic(lease: dict) -> tuple[dict, str]:
    # Token dán từ terminal có thể dính xuống dòng giữa chuỗi.
    token = re.sub(r"\s+", "", str(lease.get("secret") or ""))
    if not token:
        raise ValueError("lease anthropic không mang token")
    rt = {"provider": "anthropic", "api_mode": "anthropic_messages",
          "base_url": ANTHROPIC_BASE_URL, "api_key": token}
    return rt, _model_anthropic()


def _runtime_openai(lease: dict) -> tuple[dict, str]:
    try:
        blob = json.loads(lease.get("secret") or "")
    except Exception:
        # Không kèm thông điệp gốc: nó có thể trích một đoạn của secret.
        raise ValueError("secret openai không phải JSON") from None
    tok = str(((blob or {}).get("tokens") or {}).get("access_token") or "").strip()
    if not tok:
        raise ValueError("lease openai không mang access_token")
    base = (os.environ.get("HERMES_CODEX_BASE_URL", "").strip().rstrip("/")
            or CODEX_BASE_URL_MAC_DINH)
    rt = {"provider": "openai-codex", "api_mode": "codex_responses",
          "base_url": base, "api_key": tok}
    return rt, config.agent_model


_DUNG = {"anthropic": _runtime_anthropic, "openai": _runtime_openai}


def chon_runtime() -> tuple[dict, str, dict]:
    """→ (runtime cho AIAgent, model, nguon).

    nguon = {credential_id, provider, mode, tu: "console"|"may", ly_do}. Không chứa
    secret, và cố ý không giữ `label` của lease (có thể là email chủ tài khoản).
    """
    if not bat():
        return chon_runtime_may("cờ MARK_THEO_TAI_KHOAN_CONSOLE=0")
    lease, vi_sao = _lay_lease()
    if not lease:
        return chon_runtime_may(f"không xin được lease: {lsr_platform._redact(vi_sao)[:160]}")
    mode = str(lease.get("mode") or "")
    prov = str(lease.get("provider") or "")
    if mode != "subscription" or prov not in _DUNG:
        return chon_runtime_may(f"lease mode={mode or '?'} provider={prov or '?'} chưa hỗ trợ")
    if not lease.get("secret"):
        return chon_runtime_may("lease không mang secret (credential kiểu file trên VM)")
    try:
        rt, model = _DUNG[prov](lease)
    except Exception as e:
        return chon_runtime_may(f"dựng runtime {prov} lỗi: {type(e).__name__}")
    nguon = {"credential_id": lease.get("credential_id"), "provider": prov,
             "mode": mode, "tu": "console", "ly_do": ""}
    return rt, model, nguon


def gan_vao_agent(agent, nguon: dict | None) -> None:
    """Gắn nguồn vào agent, và với tài khoản console thì khoá đường tự đọc lại thông tin
    đăng nhập của Hermes + ghi lại lỗi API có cấu trúc. Cờ tắt → không đụng gì."""
    if not bat() or not nguon:
        return
    agent._tai_khoan_nguon = dict(nguon)
    if nguon.get("tu") == "console":
        # Hermes gọi hai hàm này trước MỖI request. Bản gốc đọc ~/.claude/.credentials.json
        # / auth.json của máy (thậm chí gia hạn và ghi lại file đó) rồi thay token đang
        # dùng — tức là quay về tài khoản cá nhân. Lỗi 401 phải nổi lên để báo platform
        # và xin lease khác.
        agent._try_refresh_anthropic_client_credentials = lambda *a, **k: False
        agent._try_refresh_codex_client_credentials = lambda *a, **k: False
        _ghi_loi_api_vao(agent)


def _ghi_loi_api_vao(agent) -> None:
    """Bọc hook lỗi API của Hermes trên RIÊNG agent này để nhớ (status_code, reason,
    error_type) — đúng kết quả `classify_api_error` của Hermes. Không giữ error_message.

    Cần vì lỗi 401 đi đường "non-retryable" của Hermes, kết quả trả về không có
    `failure_reason`; hook này là chỗ duy nhất status_code đi ra có cấu trúc."""
    goc = getattr(agent, "_invoke_api_request_error_hook", None)
    agent._tai_khoan_loi_api = None
    if goc is None:
        return

    def boc(*a, **k):
        st = k.get("status_code")
        agent._tai_khoan_loi_api = {
            "status_code": st if isinstance(st, int) and not isinstance(st, bool) else None,
            "reason": str(k.get("reason") or ""),
            "error_type": str(k.get("error_type") or ""),
        }
        return goc(*a, **k)
    agent._invoke_api_request_error_hook = boc


# ───────────────────────────── phân loại + báo lỗi ─────────────────────────────
_LY_DO_BAO = ("limit", "auth_error")


def _quyet(status, reason: str = "", ten_lop: str = "") -> tuple[str | None, bool]:
    """(lý do báo platform | None, có nên đổi tài khoản cho lượt này không)."""
    reason = (reason or "").lower()
    status = status if isinstance(status, int) and not isinstance(status, bool) else None
    if (reason in ("rate_limit", "billing") or status in (429, 402)
            or ten_lop == "RateLimitError"):
        return "limit", True
    if reason == "auth_permanent" or status == 401 or ten_lop == "AuthenticationError":
        return "auth_error", True
    # 403 có thể là lỗi của chính mình (header/beta OAuth) chứ chưa chắc credential hỏng:
    # không báo, chỉ chạy lượt này bằng máy.
    if reason == "auth" or status == 403 or ten_lop == "PermissionDeniedError":
        return None, True
    return None, False


def phan_loai_that_bai(agent, out, exc: BaseException | None) -> tuple[str | None, bool]:
    """Lượt hỏng → (lý do báo | None, có đổi tài khoản không).

    Chỉ đọc dữ liệu có cấu trúc: exception thật, `failed`/`failure_reason` của Hermes, và
    lỗi API mà `_ghi_loi_api_vao` đã nhớ. `final_response` — chữ do model viết — KHÔNG
    BAO GIỜ được đọc."""
    if exc is not None:
        ly_do, doi = _quyet(getattr(exc, "status_code", None), "", type(exc).__name__)
        if ly_do or doi:
            return ly_do, doi
    elif not (isinstance(out, dict) and out.get("failed") is True):
        return None, False
    if isinstance(out, dict):
        ly_do, doi = _quyet(None, str(out.get("failure_reason") or ""))
        if ly_do or doi:
            return ly_do, doi
    ghi = getattr(agent, "_tai_khoan_loi_api", None)
    if isinstance(ghi, dict):
        return _quyet(ghi.get("status_code"), ghi.get("reason", ""), ghi.get("error_type", ""))
    return None, False


def _bao_platform(credential_id: str, ly_do: str) -> bool:
    c = lsr_platform._cau_hinh()
    if not c:
        return False
    # Cùng gốc với _xin_lease: lease/report nằm ở platform, không phải collector.
    base = c["url"].replace("collector.", "platform.")
    req = urllib.request.Request(
        base + "/v1/self/model-auth/report",
        data=json.dumps({"credential_id": credential_id, "reason": ly_do}).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {c['key']}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        return True
    except Exception as e:
        print(f"[tai_khoan] báo platform thất bại: {type(e).__name__}", flush=True)
        return False


def bao_loi(nguon: dict | None, ly_do: str | None) -> bool:
    """Báo platform một lý do ĐÃ phân loại từ dữ liệu có cấu trúc, rồi bỏ cache lease để
    lần chọn sau xin lease mới. Chỉ cho lượt chạy bằng tài khoản console."""
    if ly_do not in _LY_DO_BAO or not nguon or nguon.get("tu") != "console":
        return False
    cid = nguon.get("credential_id")
    ok = bool(cid) and _bao_platform(str(cid), ly_do)
    print(f"[tai_khoan] báo platform {ly_do} cho {nguon.get('provider')}/{cid} "
          f"({'đã nhận' if ok else 'không gửi được'})", flush=True)
    xoa_cache()
    return ok


def ten_hien_thi(nguon: dict | None) -> str:
    """Tên chung cho người dùng — không bao giờ là label/email/credential_id."""
    if not nguon or nguon.get("tu") != "console":
        return "tài khoản dự phòng trên máy"
    return {"anthropic": "tài khoản trên console (Claude)",
            "openai": "tài khoản trên console (ChatGPT)"}.get(
        str(nguon.get("provider")), "tài khoản trên console")


# ───────────────────────────── sổ + /nangluc ─────────────────────────────
#: Lượt gần nhất. Mỗi lần ghi là GÁN LẠI cả object (nguyên tử), không sửa tại chỗ.
_GAN_NHAT: dict = {}


def ghi_luot(nguon: dict | None, model: str = "", chat_id: str = "",
             ket_qua: str = "ok", so_lan: int = 1) -> None:
    """Ghi tài khoản đã phục vụ lượt: một dòng JSONL, và nhớ cho /nangluc."""
    global _GAN_NHAT
    if not bat() or not nguon:
        return
    now = datetime.datetime.now(_VN)
    rec = {"thoi_diem": now.isoformat(timespec="seconds"), "chat": chat_id or "",
           "credential_id": nguon.get("credential_id"),
           "provider": nguon.get("provider"), "mode": nguon.get("mode"),
           "tu": nguon.get("tu"), "model": model, "ket_qua": ket_qua,
           "so_lan": so_lan, "ly_do": nguon.get("ly_do") or ""}
    _GAN_NHAT = rec
    try:
        _SO_DIR.mkdir(parents=True, exist_ok=True)
        with (_SO_DIR / f"{now:%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # sổ hỏng không được làm hỏng câu trả lời
        print(f"[tai_khoan] không ghi được sổ: {type(e).__name__}", flush=True)


def mo_ta_luot_gan_nhat() -> str:
    """Dòng cho /nangluc. Cờ tắt → chuỗi rỗng (không thêm dòng nào)."""
    if not bat():
        return ""
    g = _GAN_NHAT
    if not g:
        return "Tài khoản AI lượt gần nhất: (chưa có lượt nào từ lúc khởi động)"
    return (f"Tài khoản AI lượt gần nhất: {ten_hien_thi(g)} · {g.get('model')} · "
            f"{str(g.get('thoi_diem', ''))[11:16]}"
            + ("" if g.get("ket_qua") == "ok" else " · LỖI"))


def mo_ta_runtime(rt: dict, model: str, nguon: dict) -> dict:
    """Các trường KHÔNG bí mật để in kiểm tra (không api_key, không label/email)."""
    return {"provider": rt.get("provider"), "api_mode": rt.get("api_mode"),
            "base_url_host": urlparse(str(rt.get("base_url") or "")).hostname,
            "model": model, "ten": ten_hien_thi(nguon), "tu": nguon.get("tu"),
            "mode": nguon.get("mode"), "credential_id": nguon.get("credential_id"),
            "ly_do": nguon.get("ly_do")}
