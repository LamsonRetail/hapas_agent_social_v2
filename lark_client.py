"""Lark REST client for the Mark bot.

ONE identity: the tenant (app) token, minted from LARK_APP_ID/LARK_APP_SECRET and
refreshed transparently. Every call in this module goes out as the bot.

There is no OAuth-as-user path any more. An earlier revision ran as a real user
seat (user_access_token + send_as_user + inbox polling); that architecture was
dropped, and its helpers were removed on 28/08/2026 together with authorize.py.
Practical consequence: the bot cannot see anyone else's personal resources, and
in group chats it only receives messages that @mention it.

Provides: tenant token, bot open_id, generic `call`, message-resource download,
reactions (the "Typing" badge), open_id -> display-name resolution, send/reply.
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


# ───────────────────────── generic caller ─────────────────────────
def call(method: str, api_path: str, *, query: dict | None = None, body: Any = None) -> dict:
    token = get_tenant_token()
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
    # A failed HTTP response is not a successful Lark call.  In particular,
    # treating an HTML/proxy error as an empty JSON object made callers log a
    # successful send even though the user only saw the temporary Typing badge.
    if not r.ok:
        detail = r.text[:500]
        raise RuntimeError(
            f"Lark {method} {api_path} failed: HTTP {r.status_code}: {detail}"
        )
    try:
        data = r.json()
    except ValueError as e:
        raise RuntimeError(
            f"Lark {method} {api_path} returned non-JSON success response: {r.text[:500]}"
        ) from e
    if data.get("code") not in (None, 0):
        raise RuntimeError(f"Lark {method} {api_path} failed: {data}")
    return data


# ───────────────────────── binary download ─────────────────────────
def download_message_resource(message_id: str, file_key: str, type_: str = "image") -> bytes:
    """Download an image/file attached to a received message (as the bot).

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
# done (adding "CrossMark" on failure). We mirror that with the bot token — it
# renders as the little keyboard/typing badge on the message, not a chat line.
def add_reaction(message_id: str, emoji_type: str = "Typing") -> Optional[str]:
    """Add an emoji reaction to a message (as bot). Returns reaction_id or None."""
    try:
        data = call(
            "POST",
            f"/open-apis/im/v1/messages/{urllib.parse.quote(message_id)}/reactions",
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
            query={"user_id_type": "open_id"},  # id -> name needs the tenant token
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
def send_text(receive_id_type: str, receive_id: str, text: str) -> dict:
    return call(
        "POST",
        "/open-apis/im/v1/messages",
        query={"receive_id_type": receive_id_type},
        body={
            "receive_id": receive_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
    )


def reply_text(message_id: str, text: str, in_thread: bool = True) -> dict:
    """Reply TO a specific message. With ``in_thread=True`` the reply lands INSIDE
    the message's thread (so an @mention inside a thread gets answered in that
    thread, not the main chat). Used for group thread replies."""
    return call(
        "POST",
        f"/open-apis/im/v1/messages/{message_id}/reply",
        body={
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
            "reply_in_thread": bool(in_thread),
        },
    )
