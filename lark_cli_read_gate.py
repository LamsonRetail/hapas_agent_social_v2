"""Keep bot-only CLI reads on metadata; content uses asker-checked tools."""
from __future__ import annotations

import posixpath
import re
from urllib.parse import unquote, urlsplit

DOC = "lark_cli không đọc nội dung tài liệu — gọi `doc_tai_lieu` với nguyên link."
TABLE = "lark_cli không đọc nội dung Base/Sheet — gọi `doc_bang` hoặc `dem_bang`."
FILE = "lark_cli không tải/xuất nội dung tệp; chưa có tool kiểm quyền người hỏi cho tệp này."
UNSUPPORTED = "lark_cli không đọc nội dung slide/minutes; gửi link Docs cho `doc_tai_lieu` hoặc dán nội dung."

BASE_META = {
    "base-get", "table-list", "table-get", "field-list", "field-get",
    "field-search-options", "view-list", "view-get", "title-resolve",
    "url-resolve", "dashboard-list", "dashboard-get", "dashboard-block-list",
    "dashboard-block-get", "role-list", "role-get", "workflow-list",
    "workflow-get", "template-categories", "template-list", "template-search",
}
DOMAINS = {
    "doc": (DOC, set()), "docx": (DOC, set()), "docs": (DOC, {"search"}),
    "docs_ai": (DOC, set()), "markdown": (DOC, set()),
    "base": (TABLE, BASE_META), "bitable": (TABLE, BASE_META),
    "sheets": (TABLE, {"sheet-info", "workbook-info", "filter-list", "filter-view-list"}),
    "sheet_ai": (TABLE, set()), "sheets_ai": (TABLE, set()),
    "slides": (UNSUPPORTED, set()), "minutes": (UNSUPPORTED, {"search"}),
    "wiki": (DOC, {"node-get", "node-list", "space-list", "member-list", "search"}),
    "drive": (FILE, {"search", "member-list", "permission-get-setting", "secure-label-list"}),
}
VALUE_FLAGS = {
    "--as", "--data", "-d", "--format", "--params", "-p", "--file",
    "-o", "--output", "--jq", "-q", "--page-size", "--page-token",
    "--page-limit", "--header", "--identity", "--profile", "--timeout",
    "--query", "--body",
}
BOOL_FLAGS = {"--page-all", "--paginate", "--verbose", "-v", "--raw",
              "--pretty", "--no-color", "--dry-run", "--yes", "--help", "-h"}
WRITE_WORDS = {
    "create", "update", "delete", "remove", "send", "write", "edit",
    "patch", "post", "put", "upload", "move", "copy", "grant", "revoke",
    "approve", "reject", "schedule", "cancel", "invite", "add", "set",
    "clear", "merge", "unmerge", "replace", "fill", "sort", "overwrite",
    "submit", "import", "restore", "revert", "resolve", "react", "hide",
    "unhide", "freeze", "insert", "resize", "rename", "bind", "unbind",
    "enable", "disable", "apply", "upsert",
}


def is_content_read(argv: list[str]) -> bool:
    """SOW distinguishes a denied read from a denied write."""
    try:
        argv = command_args([x.strip().lower() for x in argv])
        if "--yes" in argv:
            return False
        if argv[0] == "api":
            return api_args(argv)[0] in {"get", "head"}
        words = {word for x in argv if x.startswith("+")
                 for word in x[1:].replace("_", "-").split("-")}
        return bool(words) and not words & WRITE_WORDS
    except (ValueError, TypeError, AttributeError):
        return False


def command_args(argv: list[str]) -> list[str]:
    """Resolve global flags before the command as the CLI does."""
    i = 0
    while i < len(argv) and argv[i].startswith("-") and argv[i] not in {"--help", "-h"}:
        flag = argv[i].split("=", 1)[0]
        if flag in VALUE_FLAGS:
            if "=" not in argv[i]:
                if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                    raise ValueError("cờ toàn cục thiếu giá trị")
                i += 1
        elif flag not in BOOL_FLAGS:
            raise ValueError("cờ toàn cục không nhận ra")
        i += 1
    if i == len(argv):
        raise ValueError("thiếu lệnh")
    return argv[i:]


def normal_path(value: str) -> str:
    value = value.strip().lower()
    for _ in range(8):
        decoded = unquote(value).lower()
        if decoded == value:
            break
        value = decoded
    if "%" in value:
        raise ValueError("đường dẫn mã hoá chưa rõ")
    value = value.replace("\\", "/")
    if "://" in value:
        parsed = urlsplit(value)
        if parsed.hostname not in {"open.larksuite.com", "open.feishu.cn", "open.larkenterprise.com"}:
            raise ValueError("API host không thuộc Lark")
        value = parsed.path
    value = re.split(r"[?#]", value, 1)[0]
    value = posixpath.normpath("/" + re.sub(r"/+", "/", value)).lstrip("/")
    while value.startswith("open-apis/"):
        value = value[len("open-apis/"):]
    return value


def api_args(argv: list[str]) -> tuple[str, str]:
    positional = []
    i = 1
    while i < len(argv):
        token = argv[i]
        if token.startswith("-"):
            flag = token.split("=", 1)[0]
            if flag in VALUE_FLAGS:
                if "=" not in token:
                    if i + 1 >= len(argv) or argv[i + 1].startswith("-"):
                        raise ValueError("cờ thiếu giá trị")
                    i += 1
            elif flag not in BOOL_FLAGS or "=" in token:
                raise ValueError("cờ API không nhận ra")
        else:
            positional.append(token)
        i += 1
    if len(positional) != 2:
        raise ValueError("cần đúng method và một đường dẫn")
    return positional[0], normal_path(positional[1])


def discovery(argv: list[str]) -> bool:
    if argv[0] in {"schema", "skills", "help", "--help", "-h"}:
        return True
    return (len(argv) <= 4 and argv[-1] in {"--help", "-h"}
            and all(not x.startswith("-") for x in argv[:-1]))


def deny_reason(argv: list[str]) -> str:
    import bang_tool
    try:
        internal = bang_tool.base_noi_bo()
        decoded = list(argv)
        for _ in range(8):
            decoded = [unquote(x).lower() for x in decoded]
        if any(t.lower() in x for t in internal if t for x in decoded):
            return "Base nội bộ của Mark — chỉ đọc qua `doc_bang` có kiểm quyền."
    except Exception:
        return "Không kiểm được Base nội bộ — fail-closed."
    if discovery(argv):
        return ""
    if argv[0] == "api":
        try:
            _, path = api_args(argv)
        except ValueError:
            return "lark_cli api không chắc đường dẫn — fail-closed."
        domain = path.split("/", 1)[0]
        if domain in DOMAINS and domain not in {"wiki", "drive"}:
            return DOMAINS[domain][0]
        if domain in {"drive", "im"} and re.search(
                r"(^|/)(medias|resources|comments?|export_tasks)(/|$)|download|export", path):
            return FILE
        return ""
    domain = DOMAINS.get(argv[0])
    if domain:
        reason, allowed = domain
        shortcuts = [x[1:] for x in argv[1:] if x.startswith("+")]
        if not shortcuts or any(x not in allowed for x in shortcuts):
            return reason
    return ""
