"""Shared lark-cli plumbing for the BOT: resolve the binary, ensure a file-based
config exists, and build a clean env.

Why file-based config (config.json) instead of an injected tenant token?
The long-connection **event bus daemon** (`event consume`) refuses the env
credential source ("credentials are provided externally") and only starts with a
real ``config.json``. A bot config is just app_id + app_secret + brand, and
``config init`` for a bot is headless (no browser). Once config.json exists the
CLI mints & auto-refreshes its own tenant token, so both the daemon (listener)
and the API tool (lark_cli_tool) share ONE config dir and one auth mode.

Note: HERMES_HOME/HERMES_AGENT_DIR are stripped from the CLI env — otherwise the
CLI detects a "hermes agent context" it isn't bound to and refuses to init.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path

from config import config

_DEFAULT_CLI = (
    Path(os.environ.get("APPDATA", r"C:\Users\PC\AppData\Roaming"))
    / "npm" / "node_modules" / "@larksuite" / "cli" / "bin" / "lark-cli.exe"
)

# Serialize the one-time `config init` so concurrent callers don't race.
_config_lock = threading.Lock()
_config_ready = False


def resolve_cli() -> str | None:
    override = os.environ.get("LARK_CLI_PATH", "").strip()
    if override and Path(override).exists():
        return override
    if _DEFAULT_CLI.exists():
        return str(_DEFAULT_CLI)
    for name in ("lark-cli", "lark-cli.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def cli_env() -> dict:
    """Clean env for file-based bot auth: point at the shared config dir, and
    strip the injected credential vars + hermes-context markers."""
    env = dict(os.environ)
    for k in list(env):
        if k.startswith("LARKSUITE_CLI_") or k in ("HERMES_HOME", "HERMES_AGENT_DIR"):
            env.pop(k, None)
    env["LARKSUITE_CLI_CONFIG_DIR"] = str(config.cli_config_dir)
    env["LARKSUITE_CLI_BRAND"] = config.brand
    env["LARKSUITE_CLI_NO_UPDATE_NOTIFIER"] = "1"
    env["LARKSUITE_CLI_NO_SKILLS_NOTIFIER"] = "1"
    env["NO_COLOR"] = "1"
    env["CI"] = "1"
    return env


def ensure_config() -> None:
    """Create the bot's file-based config.json once (idempotent, headless)."""
    global _config_ready
    if _config_ready:
        return
    with _config_lock:
        if _config_ready:
            return
        config.cli_config_dir.mkdir(parents=True, exist_ok=True)
        if (config.cli_config_dir / "config.json").exists():
            _config_ready = True
            return
        cli = resolve_cli()
        if not cli:
            raise RuntimeError(
                "Không tìm thấy lark-cli. Cài `npx @larksuite/cli@latest install` "
                "hoặc đặt LARK_CLI_PATH."
            )
        proc = subprocess.run(
            [cli, "config", "init", "--new", "--app-id", config.app_id,
             "--app-secret-stdin", "--brand", config.brand.lower()],
            env=cli_env(),
            input=config.app_secret + "\n",
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=90, cwd=str(config.here),
        )
        if proc.returncode != 0 and not (config.cli_config_dir / "config.json").exists():
            raise RuntimeError(
                f"lark-cli config init thất bại (rc={proc.returncode}): "
                f"{(proc.stderr or proc.stdout or '').strip()[:500]}"
            )
        _config_ready = True
