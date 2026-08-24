"""Lark client for the Steven user-seat agent (Python port of steven-source's lark.ts + poller.ts).

Two identities:
  - tenant token (the bot app)  -> app-level calls
  - user token   (Steven seat)  -> everything "as user": send_as_user + read own DMs

The whole point: we act AS the Steven user seat. We mint a user_access_token via
OAuth v2 (once, through authorize.py), refresh it transparently, and use it to
send messages that appear as a real person and to poll Steven's own inbox
(the only way to receive a user seat's DMs without a bot).
"""

from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any, Optional

import requests

from config import config


# ───────────────────────── tenant (bot app) token ─────────────────────────
_tenant: dict | None = None  # {"token": str, "expires_at": epoch_ms}


def get_tenant_token() -> str:
    global _tenant
    if _tenant and time.time() * 1000 < _tenant["expires_at"] - 60_000:
        return _tenant["token"]
    r = requests.post(
        f"{config.base_url}/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": config.app_id, "app_secret": config.app_secret},
        timeout=30,
    )
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"tenant_access_token failed: {data}")
    _tenant = {"token": data["tenant_access_token"], "expires_at": time.time() * 1000 + data["expire"] * 1000}
    return _tenant["token"]


# ───────────────────────── user (Steven) token — OAuth v2 ─────────────────────────
def load_user_token() -> Optional[dict]:
    try:
        return json.loads(config.token_file.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_user_token(t: dict) -> None:
    config.token_file.parent.mkdir(parents=True, exist_ok=True)
    config.token_file.write_text(json.dumps(t, indent=2, ensure_ascii=False), encoding="utf-8")


def start_device_authorization() -> dict:
    """Device-code flow step 1: get a verification URL + user_code (QR/link).

    Same mechanism the official lark-cli uses — NO redirect_uri needed, so no
    20029 errors. Whoever opens the link and approves becomes the authorized
    user (i.e. sign in as Steven to bind the Steven seat).
    """
    # Different Lark builds expose this on different hosts/paths. Try each.
    candidates = [
        f"{config.auth_base_url}/oauth/v1/device_authorization",
        f"{config.base_url}/open-apis/authen/v1/device_authorization",
        f"{config.auth_base_url}/open-apis/authen/v1/device_authorization",
    ]
    body = {
        "client_id": config.app_id,
        "client_secret": config.app_secret,
        "scope": config.scope,
    }
    data = None
    errors = []
    for url in candidates:
        try:
            r = requests.post(
                url,
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            j = r.json()
        except Exception:
            errors.append(f"{url} -> {r.status_code if 'r' in dir() else '?'} non-JSON")
            continue
        if (j.get("code") in (None, 0)) and not j.get("error") and (j.get("device_code") or j.get("data")):
            data = j
            break
        errors.append(f"{url} -> {j}")
    if data is None:
        raise RuntimeError("device_authorization failed on all endpoints:\n  " + "\n  ".join(errors))
    # normalize (Lark returns data nested or flat depending on host)
    d = data.get("data", data)
    return {
        "device_code": d["device_code"],
        "user_code": d.get("user_code"),
        "verification_url": d.get("verification_url") or d.get("verification_uri"),
        "expires_in": int(d.get("expires_in") or 300),
        "interval": int(d.get("interval") or 5),
    }


def _token_request(body: dict) -> dict:
    """POST the v2 oauth/token endpoint (used for device grant AND refresh)."""
    r = requests.post(
        f"{config.base_url}/open-apis/authen/v2/oauth/token",
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    return r.json()


def _persist_from_token_response(data: dict) -> dict:
    now = time.time() * 1000
    t = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": now + (data.get("expires_in") or 7200) * 1000,
        "refresh_expires_at": now + (data.get("refresh_token_expires_in") or 30 * 24 * 3600) * 1000,
        "scope": data.get("scope"),
    }
    try:
        who = requests.get(
            f"{config.base_url}/open-apis/authen/v1/user_info",
            headers={"Authorization": f"Bearer {t['access_token']}"},
            timeout=30,
        ).json()
        if who.get("data"):
            t["open_id"] = who["data"].get("open_id")
            t["name"] = who["data"].get("name")
    except Exception:
        pass  # identity is best-effort
    save_user_token(t)
    return t


def poll_device_token(device_code: str, interval: int = 5, expires_in: int = 300) -> dict:
    """Device-code flow step 2: poll until the user approves, then save token."""
    deadline = time.time() + expires_in
    while time.time() < deadline:
        data = _token_request(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": config.app_id,
                "client_secret": config.app_secret,
            }
        )
        if data.get("access_token"):
            return _persist_from_token_response(data)
        err = str(data.get("error") or data.get("sub_code") or "")
        desc = str(data.get("error_description") or data.get("msg") or "")
        pending = (
            err in ("authorization_pending", "slow_down")
            or data.get("code") in (20037,)
            or "pending" in err
            or "pending" in desc.lower()
            or "not been authorized" in desc.lower()
        )
        if pending:
            if err == "slow_down":
                interval += 2
            time.sleep(interval)
            continue
        raise RuntimeError(f"device token exchange failed: {data}")
    raise RuntimeError("Hết thời gian chờ xác nhận (device code đã hết hạn). Chạy lại authorize.")


def get_user_token() -> str:
    """Return a valid user access token, refreshing transparently when expired."""
    t = load_user_token()
    if not t:
        raise RuntimeError("No user token yet — run authorize.py and authorize Steven first.")
    if time.time() * 1000 < t["expires_at"] - 60_000:
        return t["access_token"]
    if not t.get("refresh_token") or time.time() * 1000 > t["refresh_expires_at"]:
        raise RuntimeError("Refresh token hết hạn/không có — chạy lại authorize.py.")
    data = _token_request(
        {
            "grant_type": "refresh_token",
            "client_id": config.app_id,
            "client_secret": config.app_secret,
            "refresh_token": t["refresh_token"],
        }
    )
    if not data.get("access_token"):
        raise RuntimeError(f"refresh token failed: {data}")
    now = time.time() * 1000
    refreshed = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token") or t["refresh_token"],
        "expires_at": now + (data.get("expires_in") or 7200) * 1000,
        "refresh_expires_at": now + (data.get("refresh_token_expires_in") or 30 * 24 * 3600) * 1000,
        "scope": data.get("scope") or t.get("scope"),
        "open_id": t.get("open_id"),
        "name": t.get("name"),
    }
    save_user_token(refreshed)
    return refreshed["access_token"]


def get_steven_open_id() -> Optional[str]:
    t = load_user_token()
    return t.get("open_id") if t else None


# ───────────────────────── bot identity ─────────────────────────
_bot_open_id: Optional[str] = None


def get_bot_open_id() -> Optional[str]:
    """Return the app bot's own open_id (cached), so we can ignore our own
    messages and detect @bot mentions. Uses the tenant token (bot/v3/info)."""
    global _bot_open_id
    if _bot_open_id is not None:
        return _bot_open_id or None
    try:
        r = requests.get(
            f"{config.base_url}/open-apis/bot/v3/info",
            headers={"Authorization": f"Bearer {get_tenant_token()}"},
            timeout=30,
        ).json()
        _bot_open_id = ((r.get("bot") or {}).get("open_id")) or ""
    except Exception as e:
        print(f"[bot] get open_id error: {e}")
        _bot_open_id = ""
    return _bot_open_id or None


def has_user_token() -> bool:
    return load_user_token() is not None


# ───────────────────────── generic caller ─────────────────────────
def call(method: str, api_path: str, *, as_: str = "tenant", query: dict | None = None, body: Any = None) -> dict:
    token = get_user_token() if as_ == "user" else get_tenant_token()
    url = f"{config.base_url}{'' if api_path.startswith('/') else '/'}{api_path}"
    if query:
        clean = {k: str(v) for k, v in query.items() if v is not None}
        url += "?" + urllib.parse.urlencode(clean)
    r = requests.request(
        method,
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
        data=json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None,
        timeout=60,
    )
    try:
        data = r.json()
    except Exception:
        data = {}
    if data.get("code") not in (None, 0):
        raise RuntimeError(f"Lark {method} {api_path} failed: {data}")
    return data


# ───────────────────────── binary download ─────────────────────────
def download_message_resource(message_id: str, file_key: str, type_: str = "image") -> bytes:
    """Download an image/file attached to a received message (as user).

    Uses GET /open-apis/im/v1/messages/{message_id}/resources/{file_key}?type=...
    which returns the raw bytes (not JSON). ``type_`` is "image" or "file".
    A bot can download resources from messages it received (im:message:readonly).
    """
    token = get_tenant_token()
    url = (
        f"{config.base_url}/open-apis/im/v1/messages/"
        f"{urllib.parse.quote(message_id)}/resources/{urllib.parse.quote(file_key)}"
        f"?type={urllib.parse.quote(type_)}"
    )
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
    ctype = r.headers.get("Content-Type", "")
    if r.status_code != 200 or ctype.startswith("application/json"):
        # error responses come back as JSON
        try:
            raise RuntimeError(f"download resource failed: {r.json()}")
        except ValueError:
            raise RuntimeError(f"download resource failed: HTTP {r.status_code}")
    return r.content


# ───────────────────────── reactions (typing indicator) ─────────────────────────
# Hermes' feishu bot has no native "typing" API, so it marks work-in-progress by
# adding an emoji REACTION ("Typing") to the user's message and removing it when
# done (adding "CrossMark" on failure). We mirror that AS the Steven user seat —
# it renders as the little keyboard/typing badge on the message, not a chat line.
def add_reaction(message_id: str, emoji_type: str = "Typing") -> Optional[str]:
    """Add an emoji reaction to a message (as bot). Returns reaction_id or None."""
    try:
        data = call(
            "POST",
            f"/open-apis/im/v1/messages/{urllib.parse.quote(message_id)}/reactions",
            as_="tenant",
            body={"reaction_type": {"emoji_type": emoji_type}},
        )
        return (data.get("data", {}) or {}).get("reaction_id")
    except Exception as e:
        print(f"[reaction] add {emoji_type} error: {e}")
        return None


def remove_reaction(message_id: str, reaction_id: str) -> bool:
    """Remove a previously-added reaction (as bot)."""
    if not message_id or not reaction_id:
        return False
    try:
        call(
            "DELETE",
            f"/open-apis/im/v1/messages/{urllib.parse.quote(message_id)}"
            f"/reactions/{urllib.parse.quote(reaction_id)}",
            as_="tenant",
        )
        return True
    except Exception as e:
        print(f"[reaction] remove error: {e}")
        return False


# ───────────────────────── identity resolution ─────────────────────────
# open_id -> display name, cached on disk so we don't re-hit the API. NOTE: the
# id→name lookup requires the TENANT token (the user token gets 99991679); the
# bot app has tenant-level contact read.
_name_cache: dict[str, str] | None = None
_name_cache_file = config.token_file.parent / "users.json"


def _load_name_cache() -> dict[str, str]:
    global _name_cache
    if _name_cache is None:
        try:
            _name_cache = json.loads(_name_cache_file.read_text(encoding="utf-8"))
        except Exception:
            _name_cache = {}
    return _name_cache


def resolve_user_name(open_id: str | None) -> Optional[str]:
    """Return a user's display name from their open_id (cached). None on failure."""
    if not open_id:
        return None
    cache = _load_name_cache()
    if open_id in cache:
        return cache[open_id] or None
    try:
        r = call(
            "GET",
            f"/open-apis/contact/v3/users/{urllib.parse.quote(open_id)}",
            as_="tenant",  # id→name needs tenant token
            query={"user_id_type": "open_id"},
        )
        name = ((r.get("data", {}) or {}).get("user", {}) or {}).get("name")
    except Exception as e:
        print(f"[contact] resolve {open_id[:12]} error: {e}")
        name = None
    if name:
        cache[open_id] = name
        try:
            _name_cache_file.parent.mkdir(parents=True, exist_ok=True)
            _name_cache_file.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
    return name


# ───────────────────────── send helpers ─────────────────────────
def send_text(receive_id_type: str, receive_id: str, text: str, as_user: bool = False) -> dict:
    return call(
        "POST",
        "/open-apis/im/v1/messages",
        as_="user" if as_user else "tenant",
        query={"receive_id_type": receive_id_type},
        body={
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
    )


def reply_text(message_id: str, text: str, as_user: bool = False, in_thread: bool = True) -> dict:
    """Reply TO a specific message. With ``in_thread=True`` the reply lands INSIDE
    the message's thread (so a @Steven tag in a thread gets answered in that
    thread, not the main chat). Used for group thread replies."""
    return call(
        "POST",
        f"/open-apis/im/v1/messages/{message_id}/reply",
        as_="user" if as_user else "tenant",
        body={
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
            "reply_in_thread": bool(in_thread),
        },
    )
