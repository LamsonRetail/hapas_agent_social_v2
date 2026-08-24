"""Message intake for the Steven user seat (Python port of steven-source's poller.ts).

There is NO bot receiving these messages — we poll Steven's own inbox with the
user token (im:message.*_msg:get_as_user). That's the only way a user seat can
"receive" DMs. Groups: only react when @Steven. P2P: always react.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Callable

import lark_client as lark
from config import config

# where downloaded images are cached for the vision tool to read
_MEDIA_DIR = config.token_file.parent / "media"

# chat_id -> newest create_time (ms) already processed
_watermark: dict[str, int] = {}

# epoch-ms when the poller started. First time we see a chat, we baseline to
# THIS instead of the chat's newest message: anything sent before we started is
# real backlog (ignore), but anything sent after we started is a genuine new
# message we must answer — INCLUDING the very first DM from someone who never
# messaged Steven before (their p2p chat only appears once they message, so the
# old "baseline to newest & skip" logic swallowed their opening message).
_start_ts_ms: int = 0

Handler = Callable[[str, str, dict], None]


# ---- persisted p2p chat ids (groups auto-discovered; 1-1 chats are not listed) ----
def _load_extra_chats() -> list[str]:
    try:
        return json.loads(config.chats_file.read_text(encoding="utf-8")).get("p2p", [])
    except Exception:
        return []


def _save_extra_chats(ids: list[str]) -> None:
    config.chats_file.parent.mkdir(parents=True, exist_ok=True)
    config.chats_file.write_text(json.dumps({"p2p": sorted(set(ids))}, indent=2), encoding="utf-8")


_extra_chats = _load_extra_chats()


def register_chat(chat_id: str) -> None:
    """Remember a chat (e.g. a p2p we just replied in) so we keep polling it."""
    if chat_id not in _extra_chats:
        _extra_chats.append(chat_id)
        _save_extra_chats(_extra_chats)


# Cache the chat LIST so we don't re-list every tick. This only affects how fast
# a BRAND-NEW chat is discovered (bounded by the TTL); already-known chats are
# still polled for new messages every single tick, so it doesn't slow replies to
# existing conversations. Lower LARK_CHATS_CACHE_SECONDS if you want new DMers
# picked up faster (at the cost of more list-API calls).
_CHATS_CACHE_TTL = float(os.environ.get("LARK_CHATS_CACHE_SECONDS", "15"))
_chats_cache: list[tuple[str, bool]] | None = None
_chats_cache_ts: float = 0.0


def _discover_chats() -> list[tuple[str, bool]]:
    """Return [(chat_id, is_group)] — ALL p2p DMs + groups the user belongs to,
    cached for ``_CHATS_CACHE_TTL`` seconds to cut API load."""
    global _chats_cache, _chats_cache_ts
    now = time.time()
    if _chats_cache is not None and (now - _chats_cache_ts) < _CHATS_CACHE_TTL:
        return _chats_cache
    result = _fetch_chats()
    _chats_cache = result
    _chats_cache_ts = now
    return result


def _fetch_chats() -> list[tuple[str, bool]]:
    """Actually hit the API. Passing ``types=p2p,group`` makes the user-token
    list endpoint return 1-1 chats too, so ANY colleague who DMs Steven is
    auto-discovered — no manual seeding needed. (Seeded ``_extra_chats`` are
    still honoured as a fallback.)"""
    refs: dict[str, bool] = {cid: False for cid in _extra_chats}
    try:
        page_token = ""
        for _ in range(10):  # paginate defensively (up to ~1000 chats)
            query = {"types": "p2p,group", "page_size": 100}
            if page_token:
                query["page_token"] = page_token
            r = lark.call("GET", "/open-apis/im/v1/chats", as_="user", query=query)
            data = r.get("data", {}) or {}
            for c in (data.get("items") or []):
                refs[c["chat_id"]] = c.get("chat_mode") == "group"
            page_token = data.get("page_token") or ""
            if not data.get("has_more") or not page_token:
                break
    except Exception as e:
        print(f"[poll] list chats error: {e}")
    return list(refs.items())


_IMG_EXT = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}


def _extract_content(m: dict) -> tuple[str, list[str]]:
    """Return (text, image_keys) from a text/post/image message."""
    msg_type = m.get("msg_type")
    try:
        content = json.loads(m["body"]["content"])
    except Exception:
        return "", []

    if msg_type == "text":
        return content.get("text", ""), []

    if msg_type == "image":
        key = content.get("image_key")
        return "", [key] if key else []

    if msg_type == "post":  # rich text: title + nested segments
        parts: list[str] = []
        keys: list[str] = []
        if content.get("title"):
            parts.append(str(content["title"]))
        blocks = content.get("content") or []
        for line in blocks:
            for seg in line or []:
                tag = seg.get("tag")
                if tag in ("text", "a") and seg.get("text"):
                    parts.append(seg["text"])
                elif tag == "img" and seg.get("image_key"):
                    keys.append(seg["image_key"])
        return " ".join(parts), keys

    return "", []


def _download_images(message_id: str, image_keys: list[str]) -> list[str]:
    """Download image_keys to local files; return existing local paths."""
    paths: list[str] = []
    _MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    for key in image_keys:
        try:
            data = lark.download_message_resource(message_id, key, "image")
        except Exception as e:
            print(f"[poll] image download error ({key}): {e}")
            continue
        # sniff a sensible extension from magic bytes
        ext = ".png"
        if data[:3] == b"\xff\xd8\xff":
            ext = ".jpg"
        elif data[:4] == b"GIF8":
            ext = ".gif"
        elif data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            ext = ".webp"
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", key)[:80]
        p = _MEDIA_DIR / f"{safe}{ext}"
        try:
            p.write_bytes(data)
            paths.append(str(p.resolve()))
        except Exception as e:
            print(f"[poll] image save error ({key}): {e}")
    return paths


def _mentions_steven(m: dict, steven: str | None) -> bool:
    if not steven or not isinstance(m.get("mentions"), list):
        return False
    for x in m["mentions"]:
        xid = x.get("id")
        if xid == steven or (isinstance(xid, dict) and xid.get("open_id") == steven):
            return True
    return False


# chat_id -> set of thread_ids seen in that chat. Thread REPLIES are invisible
# to the chat-level messages list (they only show up when listing with
# container_id_type=thread), so a @Steven tag INSIDE a thread would never be
# answered unless we poll each thread separately. We learn thread ids from the
# root messages (which DO appear at chat level) and from the threads themselves.
_known_threads: dict[str, set[str]] = {}


def _dispatch_fresh(chat_id: str, fresh: list[dict], handler: Handler) -> None:
    """Clean text, download images, and hand each fresh message to the handler."""
    fresh.sort(key=lambda m: int(m["create_time"]))
    for m in fresh:
        text, image_keys = _extract_content(m)
        text = re.sub(r"@_user_\d+", "", text)
        text = re.sub(r"\s+", " ", text).strip()  # strip @mention placeholders
        # download any attached images so the vision tool can read them
        m["_image_paths"] = _download_images(m["message_id"], image_keys) if image_keys else []
        try:
            handler(chat_id, text, m)
        except Exception as e:
            print(f"[poll] handler error: {e}")


def _poll_chat(chat_id: str, is_group: bool, handler: Handler) -> None:
    r = lark.call(
        "GET",
        "/open-apis/im/v1/messages",
        as_="user",
        query={
            "container_id_type": "chat",
            "container_id": chat_id,
            "sort_type": "ByCreateTimeDesc",
            "page_size": 20,
        },
    )
    items = r.get("data", {}).get("items") or []

    # Learn any threads visible here so we can poll their (hidden) replies below.
    if is_group:
        seen = _known_threads.setdefault(chat_id, set())
        for m in items:
            if m.get("thread_id"):
                seen.add(m["thread_id"])

    if not items:
        # still poll known threads even if no top-level messages this tick
        if is_group:
            for tid in list(_known_threads.get(chat_id, ())):
                _poll_thread(chat_id, tid, handler)
        return

    newest = max(int(m["create_time"]) for m in items)
    if chat_id not in _watermark:
        # First sight: ignore anything sent before the poller started (backlog),
        # but fall through so messages that arrived AFTER startup still get
        # answered this same tick (a first-time DMer's opening message).
        _watermark[chat_id] = _start_ts_ms

    last = _watermark[chat_id]
    steven = lark.get_steven_open_id()
    fresh = [
        m
        for m in items
        if int(m["create_time"]) > last
        and not m.get("deleted")
        and m.get("msg_type") in ("text", "image", "post")
        and m.get("sender", {}).get("id") != steven  # ignore our own messages
        and (not is_group or _mentions_steven(m, steven))  # group: only @Steven
    ]
    _dispatch_fresh(chat_id, fresh, handler)
    _watermark[chat_id] = newest

    # Now poll each known thread for @Steven mentions in its (hidden) replies.
    if is_group:
        for tid in list(_known_threads.get(chat_id, ())):
            _poll_thread(chat_id, tid, handler)


def _poll_thread(chat_id: str, thread_id: str, handler: Handler) -> None:
    """Poll ONE thread for fresh @Steven mentions. Replies inside a thread do not
    appear in the chat-level list, so this is the only way to see (and answer)
    them. Answers are sent back INTO the thread (run.py uses `_thread_reply`)."""
    wm_key = f"thread:{thread_id}"
    try:
        r = lark.call(
            "GET",
            "/open-apis/im/v1/messages",
            as_="user",
            query={
                "container_id_type": "thread",
                "container_id": thread_id,
                "sort_type": "ByCreateTimeDesc",
                "page_size": 20,
            },
        )
    except Exception as e:
        print(f"[poll] thread list error ({thread_id}): {e}")
        return
    items = r.get("data", {}).get("items") or []
    if not items:
        return

    newest = max(int(m["create_time"]) for m in items)
    if wm_key not in _watermark:
        _watermark[wm_key] = _start_ts_ms

    last = _watermark[wm_key]
    steven = lark.get_steven_open_id()
    fresh = [
        m
        for m in items
        if int(m["create_time"]) > last
        and not m.get("deleted")
        and m.get("msg_type") in ("text", "image", "post")
        and m.get("sender", {}).get("id") != steven
        and _mentions_steven(m, steven)  # in a thread, only jump in when @Steven
    ]
    for m in fresh:
        m["_thread_reply"] = True  # tell run.py to answer INSIDE the thread
    _dispatch_fresh(chat_id, fresh, handler)
    _watermark[wm_key] = newest


def start_poller(handler: Handler) -> None:
    """Blocking poll loop. Every poll_seconds: discover chats, poll each for new text."""
    print(
        f"  Intake: polling get_as_user every {config.poll_seconds}s "
        f"(group: chỉ trả lời khi @Steven) ✅"
    )
    global _start_ts_ms
    _start_ts_ms = int(time.time() * 1000)

    while True:
        try:
            for chat_id, is_group in _discover_chats():
                _poll_chat(chat_id, is_group, handler)
        except Exception as e:
            print(f"[poll] tick error: {e}")
        time.sleep(config.poll_seconds)
