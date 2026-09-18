"""Configuration for the Mark bot.

Reads a local .env (no external dependency) and exposes a single ``config``
object. One identity only: the Lark app's tenant token.

TRAP: the loader below splits on the FIRST "=" and does NOT strip trailing
comments, so an END-OF-LINE comment becomes part of the value. Writing
``AGENT_MAX_WORKERS=2  # note`` makes int() raise ValueError at import time.
Put comments on their own line.
"""

from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines; ignores # comments / blanks).

    `.env` THẮNG biến môi trường sẵn có — cố ý, và ngược với `setdefault` trước đây.

    Vì sao đổi: máy này có một biến `APIFY_TOKEN` cấp User còn sót từ lần cài cũ,
    trỏ về một tài khoản Apify đã hết hạn mức. Với `setdefault`, biến cũ đó ÂM THẦM
    che khoá mới trong `.env` — đổi khoá rồi khởi động lại mà bot vẫn chạy bằng tài
    khoản cạn tiền, không một dòng nào báo. Mất cả buổi mới tìm ra.

    `.env` nằm cạnh mã, đi theo repo, sửa là thấy. Biến cấp User thì vô hình. Nguồn
    sự thật phải là cái nhìn thấy được.

    Đè thì BÁO RA — chỉ tên khoá, không bao giờ in giá trị. Xung đột im lặng chính
    là thứ vừa cắn mình.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        cu = os.environ.get(key)
        if cu is not None and cu != val:
            print(f"[config] .env đè biến môi trường sẵn có: {key} "
                  f"(biến cũ {len(cu)} ký tự → .env {len(val)} ký tự)")
        os.environ[key] = val


_load_dotenv(HERE / ".env")


def _req(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        raise SystemExit(f"Missing required env var: {name} (copy .env.example -> .env)")
    return v


class _Config:
    here = HERE

    # --- Lark app (BOT identity: tenant_access_token from app_id+app_secret) ---
    app_id = _req("LARK_APP_ID")
    app_secret = _req("LARK_APP_SECRET")
    base_url = os.environ.get("LARK_BASE_URL", "https://open.larksuite.com").rstrip("/")
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

    # --- Hermes brain (openai-codex uses the operator's ChatGPT/Codex quota) ---
    hermes_home = os.environ.get("HERMES_HOME", str((HERE.parent / "hermes-home")))
    hermes_agent_dir = os.environ.get(
        "HERMES_AGENT_DIR", str((HERE.parent / "hermes-home" / "hermes-agent"))
    )
    agent_model = os.environ.get("AGENT_MODEL", "gpt-5.6-terra")
    agent_provider = os.environ.get("AGENT_PROVIDER", "openai-codex")
    agent_max_iterations = int(os.environ.get("AGENT_MAX_ITERATIONS", "6"))


config = _Config()
