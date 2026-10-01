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

BÁO LỖI
`bao_loi` phân loại lỗi model: hết hạn mức → "limit" (platform cho nghỉ 5h), hỏng đăng
nhập → "auth_error" (platform VÔ HIỆU HOÁ credential). Chỉ báo cho lượt chạy bằng tài
khoản console; lượt chạy bằng máy thì không bao giờ báo.

Không bao giờ in/ghi secret: mọi thứ ra log/sổ chỉ là label, provider, credential_id.
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
    "phan_loai_loi",
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
    nguon = {"label": f"máy ({config.agent_provider})", "credential_id": None,
             "provider": config.agent_provider, "mode": "may", "tu": "may",
             "ly_do": ly_do}
    return rt, config.agent_model, nguon


def _runtime_anthropic(lease: dict) -> tuple[dict, str]:
    # Token dán từ terminal có thể dính xuống dòng giữa chuỗi.
    token = re.sub(r"\s+", "", str(lease.get("secret") or ""))
    if not token:
        raise ValueError("lease anthropic không mang token")
    rt = {"provider": "anthropic", "api_mode": "anthropic_messages",
          "base_url": ANTHROPIC_BASE_URL, "api_key": token,
          "source": "lsr-console", "requested_provider": "anthropic"}
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
          "base_url": base, "api_key": tok,
          "source": "lsr-console", "requested_provider": "openai-codex"}
    return rt, config.agent_model


_DUNG = {"anthropic": _runtime_anthropic, "openai": _runtime_openai}


def chon_runtime() -> tuple[dict, str, dict]:
    """→ (runtime cho AIAgent, model, nguon).

    nguon = {label, credential_id, provider, mode, tu: "console"|"may", ly_do}. Không
    bao giờ chứa secret.
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
    nguon = {"label": str(lease.get("label") or lease.get("credential_id") or prov),
             "credential_id": lease.get("credential_id"), "provider": prov,
             "mode": mode, "tu": "console", "ly_do": ""}
    return rt, model, nguon


def gan_vao_agent(agent, nguon: dict | None) -> None:
    """Gắn nguồn vào agent, và với tài khoản console thì khoá đường tự đọc lại thông tin
    đăng nhập của Hermes. Cờ tắt → không đụng gì (agent y như cũ)."""
    if not bat() or not nguon:
        return
    agent._tai_khoan_nguon = dict(nguon)
    if nguon.get("tu") == "console":
        # Hermes gọi hai hàm này trước MỖI request. Bản gốc đọc ~/.claude/.credentials.json
        # / auth.json của máy (thậm chí gia hạn và ghi lại file đó) rồi thay token đang
        # dùng — tức là quay về tài khoản cá nhân. Lỗi 401 phải nổi lên để `bao_loi` báo
        # platform và xin lease khác.
        agent._try_refresh_anthropic_client_credentials = lambda *a, **k: False
        agent._try_refresh_codex_client_credentials = lambda *a, **k: False


# ───────────────────────────── phân loại + báo lỗi ─────────────────────────────
_LIMIT = re.compile(
    r"\b429\b|rate[ _-]?limit|usage[ _-]?limit|quota|too many requests", re.I)
_AUTH = re.compile(
    r"\b401\b|unauthori[sz]ed|authentication[_ ]error|invalid[ _-]?(?:x-)?api[ _-]?key"
    r"|invalid[ _-]?(?:bearer[ _-]?|access[ _-]?|oauth[ _-]?)?token|token[^.\n]{0,20}"
    r"(?:expired|revoked)", re.I)


def phan_loai_loi(loi) -> str | None:
    """Lỗi (exception hoặc chuỗi) → "limit" | "auth_error" | None.

    Hạn mức xét TRƯỚC: "auth_error" làm platform vô hiệu hoá hẳn credential, nên khi
    một thông điệp lẫn cả hai thì chọn đường nhẹ tay hơn.
    """
    t = f"{type(loi).__name__}: {loi}" if isinstance(loi, BaseException) else str(loi or "")
    if _LIMIT.search(t):
        return "limit"
    if _AUTH.search(t):
        return "auth_error"
    return None


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


def bao_loi(nguon: dict | None, loi) -> str | None:
    """Phân loại lỗi; nếu lượt chạy bằng tài khoản console thì báo platform và bỏ cache
    lease để lần chọn sau xin lease mới. Trả lý do đã phân loại (hoặc None)."""
    ly_do = phan_loai_loi(loi)
    if not ly_do or not nguon or nguon.get("tu") != "console":
        return ly_do
    cid = nguon.get("credential_id")
    if cid:
        ok = _bao_platform(str(cid), ly_do)
        print(f"[tai_khoan] báo platform {ly_do} cho {nguon.get('label')} "
              f"({'đã nhận' if ok else 'không gửi được'})", flush=True)
    xoa_cache()
    return ly_do


# ───────────────────────────── sổ + /nangluc ─────────────────────────────
_GAN_NHAT: dict = {}


def ghi_luot(nguon: dict | None, model: str = "", chat_id: str = "",
             ket_qua: str = "ok", so_lan: int = 1) -> None:
    """Ghi tài khoản đã phục vụ lượt: một dòng log, một dòng JSONL, và nhớ cho /nangluc."""
    if not bat() or not nguon:
        return
    now = datetime.datetime.now(_VN)
    rec = {"thoi_diem": now.isoformat(timespec="seconds"), "chat": chat_id or "",
           "label": nguon.get("label"), "credential_id": nguon.get("credential_id"),
           "provider": nguon.get("provider"), "mode": nguon.get("mode"),
           "tu": nguon.get("tu"), "model": model, "ket_qua": ket_qua,
           "so_lan": so_lan, "ly_do": nguon.get("ly_do") or ""}
    _GAN_NHAT.clear()
    _GAN_NHAT.update(rec)
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
    g = dict(_GAN_NHAT)
    if not g:
        return "Tài khoản AI lượt gần nhất: (chưa có lượt nào từ lúc khởi động)"
    tu = "console" if g.get("tu") == "console" else "máy"
    return (f"Tài khoản AI lượt gần nhất: {g.get('label')} ({g.get('provider')}, {tu}) · "
            f"{g.get('model')} · {str(g.get('thoi_diem', ''))[11:16]}"
            + ("" if g.get("ket_qua") == "ok" else " · LỖI"))


def mo_ta_runtime(rt: dict, model: str, nguon: dict) -> dict:
    """Các trường KHÔNG bí mật để in kiểm tra (không có api_key)."""
    return {"provider": rt.get("provider"), "api_mode": rt.get("api_mode"),
            "base_url_host": urlparse(str(rt.get("base_url") or "")).hostname,
            "model": model, "label": nguon.get("label"), "tu": nguon.get("tu"),
            "mode": nguon.get("mode"), "ly_do": nguon.get("ly_do")}
