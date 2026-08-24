"""Configuration for the Steven-Hermes user-seat agent.

Reads a local .env (no external dependency) and exposes a single ``config``
object. The Lark app is the SAME bot app you already have; we only use it to
mint the tenant token and to run the user OAuth that lets us act AS the Steven
user seat (user_access_token + im:message.send_as_user).
"""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines; ignores # comments / blanks)."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv(HERE / ".env")


def _req(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise SystemExit(f"Missing required env var: {name} (copy .env.example -> .env)")
    return v


# Scopes needed to act as the Steven user seat. The key one is
# im:message.send_as_user (post as a real person) + the *_as_user read scopes
# (the only way to see a user seat's own DMs without a bot).
DEFAULT_SCOPE = " ".join([
    "offline_access",
    "im:message",
    "im:message:readonly",
    "im:message:send_as_user",
    "im:message.p2p_msg:get_as_user",
    "im:message.group_msg:get_as_user",
    "im:chat:read",
    "im:chat:readonly",
    "im:resource",
    "contact:user:search",
    "contact:user.base:readonly",
    "contact:user.basic_profile:readonly",
    "calendar:calendar:read",
    "calendar:calendar.event:read",
    "calendar:calendar.free_busy:read",
    "task:task:read",
    "task:task:write",
])


class _Config:
    here = HERE

    # --- Lark app (BOT identity: tenant_access_token from app_id+app_secret) ---
    app_id = _req("LARK_APP_ID")
    app_secret = _req("LARK_APP_SECRET")
    base_url = os.environ.get("LARK_BASE_URL", "https://open.larksuite.com").rstrip("/")
    auth_base_url = os.environ.get("LARK_AUTH_BASE_URL", "https://accounts.larksuite.com").rstrip("/")
    # lark-cli brand + isolated CLI config dir (never touch the operator's ~/.lark-cli).
    # cli_config_dir is env-overridable so the multi-tenant runtime can give each
    # created bot app its OWN config dir (one lark-cli auth per app).
    brand = "Feishu" if os.environ.get("FEISHU_DOMAIN", "").lower() == "feishu" else "Lark"
    cli_config_dir = Path(
        os.environ.get("LARKSUITE_CLI_CONFIG_DIR", "").strip() or str(HERE / ".lark-cli-bot")
    )

    # Display name / persona for THIS agent instance. Empty = the default Mark
    # persona (persona.md). The runtime sets AGENT_NAME per created bot so a
    # shared frame still answers with the right identity.
    agent_name = os.environ.get("AGENT_NAME", "").strip()

    # --- local state dir (media downloads, name cache, chat history) ---
    token_file = HERE / os.environ.get("LARK_STATE_FILE", ".tokens/bot.json")

    # --- event intake ---
    event_key = os.environ.get("LARK_EVENT_KEY", "im.message.receive_v1")

    # --- OAuth-as-user (legacy; unused in bot mode, kept only for authorize.py) ---
    redirect_uri = os.environ.get("LARK_REDIRECT_URI", "http://localhost:3001/oauth/callback")
    scope = os.environ.get("LARK_SCOPE", DEFAULT_SCOPE)
    chats_file = HERE / os.environ.get("LARK_POLL_CHATS_FILE", ".tokens/poll-chats.json")
    poll_seconds = float(os.environ.get("LARK_POLL_SECONDS", "3"))
    oauth_port = int(os.environ.get("OAUTH_PORT", "3001"))

    # --- Hermes brain (openai-codex, "as user" quota) ---
    hermes_home = os.environ.get("HERMES_HOME", str((HERE.parent / "hermes-home")))
    hermes_agent_dir = os.environ.get(
        "HERMES_AGENT_DIR", str((HERE.parent / "hermes-home" / "hermes-agent"))
    )
    agent_model = os.environ.get("AGENT_MODEL", "gpt-5.4")
    agent_provider = os.environ.get("AGENT_PROVIDER", "openai-codex")
    agent_max_iterations = int(os.environ.get("AGENT_MAX_ITERATIONS", "6"))


config = _Config()
