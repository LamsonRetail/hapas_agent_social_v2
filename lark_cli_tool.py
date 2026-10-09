"""Register a `lark_cli` tool on the Hermes brain — the FULL Lark/Feishu CLI as the BOT.

The official ``@larksuite/cli`` binary is built to be *driven by an agent*: it
exposes every Lark domain (calendar, im, wiki, docs, drive, task, base, sheets,
mail, okr, approval, contact, vc, minutes …) with:

  • ``<domain> +<shortcut>``  — high-level tasks (preferred), e.g. ``im +messages-send``
  • ``schema <svc.res.method>`` — discover a method's params/types/scopes/examples
  • ``api <METHOD> <path>``     — raw escape hatch for ANY endpoint
  • ``<domain> --help`` / ``skills`` — self-discovery

So the LLM can "just call lark_cli" and figure out the right API itself.

Auth (bot identity)
-------------------
Uses lark-cli's **file-based** config (``config.json`` in ``config.cli_config_dir``,
created once by ``cli_support.ensure_config()`` from app_id/app_secret). The CLI
mints & auto-refreshes its own bot ``tenant_access_token``. This is the SAME
config the event listener uses — one config dir, one auth mode. (An injected env
token works for stateless calls but the long-connection event daemon rejects it,
so file-based config is the single source of truth.) Identity = the app bot;
user-personal resources (someone's calendar/mailbox/drive) are NOT accessible.
"""

from __future__ import annotations

import subprocess

from config import config
from cli_support import cli_env, ensure_config, resolve_cli

from tools.registry import registry, tool_error, tool_result  # type: ignore

_TOOLSET = "lark_api"  # same toolset as lark_api so one enable flag turns on both
_CLI_TIMEOUT = 90
_MAX_OUT = 12000


LARK_CLI_SCHEMA = {
    "name": "lark_cli",
    "description": (
        "Chạy official Lark CLI (lark-cli) dưới danh tính BOT (tenant token) để làm "
        "việc trên Lark bằng quyền của app bot: im (gửi/đọc tin nhắn, chat), base/"
        "bitable, wiki, drive, task, sheets, approval, contact, vc, "
        "minutes... Đây là công cụ MẠNH NHẤT, ưu tiên dùng. Lưu ý: bot KHÔNG thấy "
        "tài nguyên cá nhân của người khác (lịch/mail/drive riêng).\n"
        "KHÔNG đọc NỘI DUNG tài liệu, Base/Sheet, slide/minutes hoặc tải/xuất file bằng "
        "lệnh này. Docs/Wiki dùng `doc_tai_lieu`; Base/Sheet dùng `doc_bang`/`dem_bang` "
        "để kiểm quyền người hỏi. Slide/minutes/tệp khác chưa có đường đọc an toàn.\n"
        "Cách agent tự dò & gọi API (làm theo thứ tự):\n"
        "  1) Xem lệnh của 1 domain:  args=[\"<domain>\",\"--help\"]  (domain: calendar, im, wiki, docs, drive, task, base, sheets, mail, okr, approval, contact, vc, minutes)\n"
        "  2) Ưu tiên +shortcut (việc mức cao):  args=[\"calendar\",\"+agenda\"]  hay  args=[\"task\",\"+create\",\"--summary\",\"Gọi khách\"]\n"
        "  3) Xem tham số 1 method:  args=[\"schema\",\"mail.user_mailbox.messages.list\"]\n"
        "  4) Escape hatch gọi thẳng endpoint bất kỳ:  args=[\"api\",\"GET\",\"/open-apis/calendar/v4/calendars\"]  (thêm --params '{json}' cho query, --data '{json}' cho body)\n"
        "Mẹo: thêm \"--jq\",\"<biểu thức>\" để lọc JSON; \"--dry-run\" để xem trước request mà KHÔNG chạy.\n"
        "AN TOÀN: lệnh ghi rủi ro cao (high-risk-write) cần cờ \"--yes\" — CHỈ thêm --yes SAU KHI người dùng đã xác nhận. Xem mức rủi ro trong <domain> --help (read | write | high-risk-write)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "args": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Danh sách tham số truyền NGUYÊN VĂN cho lark-cli (KHÔNG kèm "
                    "tên chương trình). Ví dụ: [\"wiki\",\"--help\"] hoặc "
                    "[\"api\",\"GET\",\"/open-apis/wiki/v2/spaces\"]."
                ),
            }
        },
        "required": ["args"],
    },
}


def _handle_lark_cli(args: dict, **kwargs) -> str:
    cli_args = args.get("args")
    if not isinstance(cli_args, list) or not cli_args or not all(isinstance(a, str) for a in cli_args):
        return tool_error("`args` phải là list chuỗi không rỗng, vd [\"wiki\",\"--help\"].")

    cli = resolve_cli()
    if not cli:
        return tool_error(
            "Không tìm thấy lark-cli. Cài bằng `npx @larksuite/cli@latest install` "
            "hoặc đặt biến môi trường LARK_CLI_PATH."
        )

    try:
        ensure_config()  # file-based config.json (shared with the event listener)
    except Exception as e:
        return tool_error(f"Không khởi tạo được config lark-cli của bot: {e}. Kiểm tra LARK_APP_ID/LARK_APP_SECRET.")

    try:
        proc = subprocess.run(
            [cli, *cli_args],
            env=cli_env(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_CLI_TIMEOUT,
            cwd=str(config.here),
        )
    except subprocess.TimeoutExpired:
        return tool_error(f"lark-cli quá thời gian {_CLI_TIMEOUT}s khi chạy {' '.join(cli_args)!r}.")
    except OSError as e:
        return tool_error(f"Không chạy được lark-cli: {type(e).__name__}: {e}")

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()
    if proc.returncode != 0:
        detail = stderr or stdout or "(no output)"
        return tool_error(f"lark-cli exit code {proc.returncode}: {detail[:1500]}")

    return tool_result(
        success=True,
        command=cli_args,
        stdout=stdout[:_MAX_OUT],
        stderr=stderr[:1000] if stderr else "",
        truncated=len(stdout) > _MAX_OUT,
    )


def _check_available() -> bool:
    return resolve_cli() is not None and bool(config.app_id and config.app_secret)


def register() -> None:
    try:
        registry.register(
            name="lark_cli",
            toolset=_TOOLSET,
            schema=LARK_CLI_SCHEMA,
            handler=_handle_lark_cli,
            check_fn=_check_available,
            requires_env=[],
            is_async=False,
            description="Chạy Lark CLI dưới danh tính bot (đủ mọi domain + shortcut + raw api)",
            emoji="\U0001f4bc",
            override=True,
        )
    except Exception as e:
        print(f"[lark_cli_tool] register warning: {e}")


register()
