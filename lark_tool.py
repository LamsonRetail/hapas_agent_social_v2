"""Register a `lark_api` tool on the Hermes brain — full Lark REST as Steven.

Why this file exists
--------------------
Hermes ships a `lark_cli` tool, but it (a) only runs when the session platform
is "feishu" and (b) reads the user token from Hermes' OWN feishu-oauth store
(lark_user_tokens.json). Our steven-hermes runs standalone with Steven's own
user_access_token (174 scopes) in .tokens/steven.json — a different identity.

So we register ONE generic passthrough tool, `lark_api`, that calls the Lark
Open API directly with Steven's user token via ``lark_client.call``. That single
tool gives the brain the whole REST surface the token is scoped for: wiki, docs/
docx, drive, im (messages/chats), calendar, task, base/bitable, sheets, contact…

Import this module (once) BEFORE constructing the AIAgent: registration mutates
the global Hermes tool registry, and AIAgent snapshots the registry at init.
"""

from __future__ import annotations

import json

import lark_client as lark

# tools.registry is importable because brain.py already put hermes_agent_dir on
# sys.path before importing this module.
from tools.registry import registry, tool_error, tool_result  # type: ignore

_TOOLSET = "lark_api"
_MAX_RESULT_CHARS = 12000  # keep tool output from blowing up the context


LARK_API_SCHEMA = {
    "name": "lark_api",
    "description": (
        "Gọi TRỰC TIẾP Lark/Feishu Open API dưới danh tính người dùng hiện tại "
        "(Steven), dùng chính quyền của Steven. Trả về JSON thô của Lark. Dùng "
        "tool này để ĐỌC/GHI mọi thứ trên Lark: wiki, tài liệu (docx/docs), "
        "drive, tin nhắn & chat (im), lịch (calendar), task, base/bitable, "
        "sheets, contact, v.v.\n"
        "Cách dùng: truyền `method` (GET/POST/PUT/DELETE/PATCH) và `api_path` "
        "(đường dẫn Open API, ví dụ '/open-apis/wiki/v2/spaces'). Tham số query "
        "cho vào `query` (object), body JSON cho vào `body` (object).\n"
        "Ví dụ đường dẫn hay dùng:\n"
        "  • Wiki: GET /open-apis/wiki/v2/spaces  (liệt kê wiki space)\n"
        "  • Wiki: GET /open-apis/wiki/v2/spaces/{space_id}/nodes  (node trong space)\n"
        "  • Wiki: GET /open-apis/wiki/v2/spaces/get_node?token={node_token}  (giải node→obj)\n"
        "  • Docx nội dung: GET /open-apis/docx/v1/documents/{document_id}/raw_content\n"
        "  • Docx blocks: GET /open-apis/docx/v1/documents/{document_id}/blocks\n"
        "  • Drive tìm file: POST /open-apis/drive/v1/files/search  body {search_key,...}\n"
        "  • IM tin nhắn: GET /open-apis/im/v1/messages?container_id_type=chat&container_id={chat_id}\n"
        "  • IM chat: GET /open-apis/im/v1/chats\n"
        "  • Calendar: GET /open-apis/calendar/v4/calendars\n"
        "  • Task: GET /open-apis/task/v2/tasks\n"
        "  • Base: GET /open-apis/bitable/v1/apps/{app_token}/tables\n"
        "  • Tìm người: GET /open-apis/search/v1/user?query={tên|email}\n"
        "Với thao tác GHI/xóa (POST/PUT/DELETE tạo/sửa task, event, doc, gửi tin) "
        "PHẢI được người dùng xác nhận trước khi gọi. Nếu Lark trả code!=0, đọc "
        "'msg' để biết lỗi (thường là thiếu tham số hoặc token/scope)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "method": {
                "type": "string",
                "description": "HTTP method: GET / POST / PUT / DELETE / PATCH.",
            },
            "api_path": {
                "type": "string",
                "description": (
                    "Đường dẫn Open API bắt đầu bằng '/open-apis/...'. Không "
                    "kèm host. Query có thể gắn thẳng vào path hoặc tách ra "
                    "trường `query`."
                ),
            },
            "query": {
                "type": "object",
                "description": "Tham số query dạng object (tùy chọn).",
            },
            "body": {
                "type": "object",
                "description": "Body JSON cho POST/PUT/PATCH (tùy chọn).",
            },
        },
        "required": ["method", "api_path"],
    },
}


def _handle_lark_api(args: dict, **kwargs) -> str:
    method = str(args.get("method") or "").strip().upper()
    api_path = str(args.get("api_path") or "").strip()
    query = args.get("query")
    body = args.get("body")

    if method not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
        return tool_error(
            "`method` phải là một trong GET/POST/PUT/DELETE/PATCH."
        )
    if not api_path:
        return tool_error("Thiếu `api_path` (ví dụ '/open-apis/wiki/v2/spaces').")

    # Tolerate a full URL or a path missing the leading slash / open-apis prefix.
    if api_path.startswith("http"):
        # strip scheme+host, keep path (+query)
        from urllib.parse import urlsplit

        parts = urlsplit(api_path)
        api_path = parts.path + (f"?{parts.query}" if parts.query else "")
    if not api_path.startswith("/"):
        api_path = "/" + api_path
    if not api_path.startswith("/open-apis/"):
        api_path = "/open-apis" + api_path if api_path.startswith("/") else api_path

    if query is not None and not isinstance(query, dict):
        return tool_error("`query` phải là object (key/value).")
    if body is not None and not isinstance(body, dict):
        return tool_error("`body` phải là object JSON.")

    try:
        data = lark.call(method, api_path, as_="user", query=query, body=body)
    except Exception as e:  # network / auth / Lark code!=0
        return tool_error(f"Gọi Lark thất bại: {type(e).__name__}: {e}")

    out = json.dumps(data, ensure_ascii=False)
    truncated = len(out) > _MAX_RESULT_CHARS
    if truncated:
        out = out[:_MAX_RESULT_CHARS]
    # NOTE: do NOT use a kwarg named `data` — tool_result treats its first
    # positional param `data` as "return this dict verbatim", which would drop
    # the other fields. Use `response` for the payload instead.
    return tool_result(
        success=True,
        method=method,
        api_path=api_path,
        truncated=truncated,
        response=out,
    )


def _check_available() -> bool:
    # Available whenever Steven has a usable user token.
    return lark.has_user_token()


def register() -> None:
    """Idempotently register the lark_api tool into the Hermes registry."""
    try:
        registry.register(
            name="lark_api",
            toolset=_TOOLSET,
            schema=LARK_API_SCHEMA,
            handler=_handle_lark_api,
            check_fn=_check_available,
            requires_env=[],
            is_async=False,
            description="Gọi Lark Open API dưới danh tính Steven (đọc/ghi mọi domain)",
            emoji="\U0001f517",
            override=True,
        )
    except Exception as e:
        print(f"[lark_tool] register warning: {e}")


register()
