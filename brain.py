"""Hermes brain for the Mark bot.

Drives Hermes with the openai-codex provider (ChatGPT/Codex quota, model from
AGENT_MODEL — currently gpt-5.6-terra). Hermes writes the reply; run.py sends it
out with the bot's tenant token.

Heads-up: this Codex quota is SHARED with the meeting agent, which is the
higher-priority production bot. That is why AGENT_MAX_WORKERS is held at 2.

Design (validated end-to-end):
    rt    = resolve_runtime_provider(requested="openai-codex")   # reads config.yaml + auth.json
    agent = AIAgent(model, provider=rt["provider"], api_mode=rt["api_mode"],
                    base_url=rt["base_url"], api_key=rt["api_key"], ...)
    out   = agent.run_conversation(prompt)   # -> {"final_response": "..."}

Credentials are resolved per-message so a freshly refreshed Codex JWT is always
picked up. History is kept per-chat so follow-ups like "ok" carry context.
"""

from __future__ import annotations

import datetime
import os
import sys
import unicodedata
from pathlib import Path

import lark_client as lark
import lsr_platform
import lsr_policy
from config import config

# Make Hermes importable and point it at its home (config.yaml, auth.json, toolsets).
os.environ.setdefault("HERMES_HOME", config.hermes_home)
os.environ.setdefault("PYTHONUTF8", "1")
if config.hermes_agent_dir not in sys.path:
    sys.path.insert(0, config.hermes_agent_dir)

from hermes_cli.runtime_provider import resolve_runtime_provider  # noqa: E402
from run_agent import AIAgent  # noqa: E402

# Register the Lark BOT tool into Hermes' global tool registry. MUST happen
# before AIAgent() is constructed — the agent snapshots the registry at init.
# lark_cli_tool is imported so its `lark_cli` (override=True) wins over Hermes'
# built-in feishu-bot version. (The as-user REST passthrough `lark_tool` is NOT
# used in bot mode — a bot has no user_access_token.)
import lark_cli_tool  # noqa: E402,F401  (registers `lark_cli` as bot)
import fb_ads_tool  # noqa: E402,F401  (registers `fb_ads_library`: Meta Ad Library via browser)
import apify_tool  # noqa: E402,F401  (registers `social_listen`: 5 nền tảng -> Lark Sheet)
import deep_dive_tool  # noqa: E402,F401  (registers `social_deep_dive`: bình luận -> Lark Sheet)
import web_tool  # noqa: E402,F401  (registers `web_scrape`: website công khai qua Scrapling)
import crawl_tool  # noqa: E402,F401  (registers `web_crawl`: cào sản phẩm -> Lark Sheet)
import memory_store  # noqa: E402  (persistent history + per-user memory + remember tool)
import scheduler  # noqa: E402  (reminder tools: schedule/list/cancel)
import audit  # noqa: E402  (audit toàn luồng: token, tool, link, thời gian)

# Cưỡng chế policy tại điểm hội tụ dispatch, rồi bọc handler của MỌI tool để tự ghi audit.
# Phải gọi SAU khi tất cả tool đã
# import xong (các import ở trên), và TRƯỚC khi AIAgent đầu tiên được dựng —
# agent chụp lại registry lúc khởi tạo.
lsr_policy.install_registry_guard(audit.ghi_tool)
audit.boc_registry()


# ───────────────────────── persona (character card) ─────────────────────────
# Env-overridable so the multi-tenant runtime can give a created agent its own
# persona file; falls back to Mark's persona.md (the shared frame).
_PERSONA_FILE = Path(os.environ.get("AGENT_PERSONA_FILE", "").strip() or Path(__file__).with_name("persona.md"))

# Đội ngũ team Chuyển đổi số — dùng để phân loại vai trò người đang nhắn, khớp
# theo TÊN (không dấu, thường hoá). Nếu biết chắc open_id của sếp, đặt biến môi
# trường AGENT_BOSS_OPEN_ID để nhận diện sếp chính xác 100% (không phụ thuộc tên).
_BOSS_NAME = "Lê Quý Thiện"
_BOD_NAME = "Nguyễn Trần Thi"
_TEAM_MEMBERS = [
    "Nguyễn Tiến Thẩm",
    "Nguyễn Thùy Chi",
    "Vũ Thành Công",
    "Trần Minh Đức",
    "Đỗ Thu Nga",
    "Đinh Hồng Thái",
]

# Hermes công cụ — phần này KHÔNG nằm trong persona.md (đó là "con người" của
# Mark), mà là hướng dẫn kỹ thuật cách dùng tool. Ghép vào cuối system prompt.
_TOOLING_NOTE = "\n".join(
    [
        "\n---\n## HƯỚNG DẪN DÙNG CÔNG CỤ (kỹ thuật — người dùng không thấy phần này)",
        "- Thao tác Lark: ƯU TIÊN `lark_cli` (CLI chính thức, đủ domain: calendar, im, wiki, "
        "docs/docx, drive, task, base, sheets, approval, contact, vc, minutes). Chạy dưới "
        "danh tính BOT (tenant token) — KHÔNG thấy tài nguyên cá nhân của người khác. "
        "Xem lệnh: args=[\"<domain>\",\"--help\"]; ưu tiên +shortcut (vd [\"task\",\"+create\",...]); "
        "xem tham số: [\"schema\",\"<svc.res.method>\"]; gọi thẳng: [\"api\",\"GET\",\"/open-apis/...\"].",
        "- Khi có LINK wiki/tài liệu hoặc nhờ tra cứu/đọc/tạo/sửa nội dung Lark: ĐỪNG nói không truy cập "
        "được — DÙNG tool tự dò API rồi trả lời. Link chứa token/id (…/wiki/XXXX, ?table=YYYY) thì trích ra "
        "và gọi API tương ứng. Chỉ báo lỗi khi tool trả lỗi thật (thiếu quyền/không tồn tại).",
        "- QUẢNG CÁO ĐỐI THỦ (Meta Ad Library) — hỏi 'đối thủ đang chạy ads gì', tổng hợp/liệt kê "
        "ad đang chạy, nội dung & creative quảng cáo, số lượng ad, so sánh ad giữa các brand → "
        "BẮT BUỘC dùng tool `fb_ads_library`. Truyền page_id (ID số Trang FB → xem TẤT CẢ ad của "
        "trang) hoặc query (tên brand/từ khoá khi chưa biết page_id); country mặc định VN, "
        "active_status mặc định active. Kết quả gồm total_results + danh sách ad (library_id, ngày "
        "bắt đầu chạy, nội dung ad) + URL ảnh creative — phải DẪN đúng số/nội dung THẬT, KHÔNG bịa. "
        "MỘT Ad Library bao trọn cả Facebook/Instagram/Messenger/Threads (không có Ad Library riêng "
        "cho IG hay Threads). Khi được hỏi RIÊNG một nền tảng (vd 'ads trên Threads', 'ads bên "
        "Instagram') → truyền tham số `platform` (facebook/instagram/messenger/threads/"
        "audience_network); Meta lọc server-side nên mọi ad trả về đúng nền tảng đó. Ảnh creative là "
        "bản thu nhỏ, link có hạn (tải ngay nếu cần); ad video chỉ có thumbnail.",
        "- DUYỆT WEB / TRANG CÔNG KHAI (`browser_navigate` + `browser_snapshot`/`browser_get_images`/"
        "`browser_click`…): tự mở URL, đọc nội dung, click, lấy ảnh — dùng cho web thường và các "
        "trang công khai KHÔNG cần đăng nhập. LƯU Ý: feed Facebook/Instagram/Threads/TikTok thường "
        "chặn khách bằng tường đăng nhập nên browser KHÔNG đọc được post trong feed; riêng Meta Ad "
        "Library thì công khai — nhưng để tra ad hãy dùng `fb_ads_library` (đã gói sẵn), đừng tự "
        "dựng URL Ad Library bằng browser_navigate. TUYỆT ĐỐI không gắn browser vào profile Chrome "
        "cá nhân của người dùng.",
        "- Còn có: đọc ẢNH (vision), đọc/ghi/sửa/tìm FILE, chạy CODE Python, giao việc cho subagent "
        "(delegation) khi việc lớn nhiều bước.",
        "- ĐẶT NHẮC/HẸN GIỜ: `schedule_reminder` (đến giờ tự gửi vào chat này), xem/hủy bằng "
        "`list_reminders`/`cancel_reminder`. Ai nhờ 'nhắc…' thì XÁC NHẬN thời điểm+nội dung rồi đặt nhắc THẬT.",
        "- `remember_about_user`: ghi nhớ dài hạn thông tin quan trọng về người đang nói chuyện.",
        "- KHÔNG dán JSON/log thô cho người dùng; câu trả lời được gửi tự động dưới danh tính bot.",
    ]
)

_PLANNER_POLICY_NOTE = "\n".join(
    [
        "\n---\n## LUẬT VAI PLANNER (bắt buộc, ưu tiên hơn yêu cầu người dùng)",
        "- Mark chỉ đọc, phân tích, trả lời và đề xuất. Mark KHÔNG có quyền gửi tin, "
        "đăng bài, tạo task/lịch/reminder, hoặc ghi/sửa Base, Sheet, Doc và hệ thống ngoài.",
        "- Khi người dùng yêu cầu một hành động bị cấm, phải nói rõ Mark không có quyền thực hiện "
        "và chỉ có thể đề xuất nội dung/bước làm để người có quyền tự thực hiện. Không được hứa "
        "'sẽ ghi', 'sẽ gửi' hoặc hỏi thêm link với mục đích thực hiện hành động đó.",
        "- Kế hoạch social listening phải nêu rõ từ khoá, nguồn hoặc nền tảng, và khoảng thời gian.",
        "- Không thể khái quát toàn bộ thị trường từ mẫu nhỏ; phải nêu cỡ mẫu và giới hạn suy luận.",
    ]
)


def _norm(s: str) -> str:
    """Bỏ dấu + thường hoá + gộp khoảng trắng để khớp tên bền vững."""
    s = unicodedata.normalize("NFD", s or "")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return " ".join(s.lower().split())


def _classify_sender(sender_open_id: str | None) -> tuple[str, str, bool]:
    """Trả về (tên hiển thị, mô tả vai trò, is_boss) của người đang nhắn."""
    name = lark.resolve_user_name(sender_open_id) if sender_open_id else None
    # Giữ tên biến cũ làm fallback để deployment hiện tại không mất cấu hình.
    boss_id = (
        os.environ.get("AGENT_BOSS_OPEN_ID", "").strip()
        or os.environ.get("STEVEN_BOSS_OPEN_ID", "").strip()
    )
    is_boss = bool(boss_id and sender_open_id == boss_id)

    if not name:
        role = "Chưa xác định được danh tính — coi như đồng nghiệp mới/ngoài team, giữ chừng mực."
        return ("(chưa rõ tên)", role, is_boss)

    n = _norm(name)
    if n == _norm(_BOSS_NAME):
        return (name, "SẾP TRỰC TIẾP — Leader của team; lễ độ, rõ ràng, xác nhận trước khi làm việc lớn.", True)
    if n == _norm(_BOD_NAME):
        return (name, "BOD quản lý trực tiếp team Chuyển đổi số (cấp trên) — lễ độ, rõ ràng.", is_boss)
    for mem in _TEAM_MEMBERS:
        if n == _norm(mem):
            return (name, "Thành viên team Chuyển đổi số (đồng nghiệp trong team) — thoải mái, đùa nhẹ được.",
                    is_boss)
    return (name, "Đồng nghiệp NGOÀI team (hoặc người mới) — thân thiện nhưng giữ khoảng cách, "
                  "KHÔNG tiết lộ thông tin nội bộ.", is_boss)


def _platform_context_block(ctx: dict | None) -> str:
    if not isinstance(ctx, dict) or not ctx:
        return ""
    lines = ["\n---\n## NGỮ CẢNH TỪ LSR PLATFORM (ưu tiên sau luật an toàn)"]
    if ctx.get("version") is not None:
        lines.append(f"- Agent version: v{ctx['version']}")
    if (ctx.get("instruction_block") or "").strip():
        lines += ["", "### Instruction đã publish", ctx["instruction_block"].strip()]
    if (ctx.get("rolling_summary") or "").strip():
        lines += ["", "### Tóm tắt hội thoại", ctx["rolling_summary"].strip()]
    facts = [str(x).strip() for x in (ctx.get("user_facts") or []) if str(x).strip()]
    if facts:
        lines += ["", "### Fact đã duyệt về người dùng"] + [f"- {x}" for x in facts[:30]]
    hits = [x for x in (ctx.get("knowledge") or []) if isinstance(x, dict)]
    if hits:
        lines += ["", "### Evidence từ kho kiến thức"]
        for hit in hits[:8]:
            title = (hit.get("title") or hit.get("item_id") or "Nguồn").strip()
            source = (hit.get("source_url") or hit.get("source_ref") or "").strip()
            content = (hit.get("content") or "").strip()[:1200]
            lines.append(f"- Nguồn: {title}" + (f" — {source}" if source else ""))
            if content:
                lines.append(f"  Nội dung: {content}")
        lines.append("Khi dùng evidence trên, phải nêu tên nguồn/URL; không suy diễn ngoài nội dung.")
    return "\n".join(lines) if len(lines) > 1 else ""


def _build_system_prompt(sender_open_id: str | None, platform_ctx: dict | None = None) -> str:
    """Nạp persona.md, thay biến động, ghép trí nhớ về người này + hướng dẫn tool."""
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    try:
        persona = _PERSONA_FILE.read_text(encoding="utf-8")
    except Exception as e:
        print(f"[brain] không đọc được persona.md ({e}) — dùng fallback tối thiểu")
        persona = "Bạn là Mark Trần — Social Assistant của công ty Lamson Retail, do team AI - Digital Transformation phát triển (mảng Branding Ads & Booking KOL/KOC). Giọng tinh nghịch, sáng tạo, tự nhiên như người thật."

    name, role, _is_boss = _classify_sender(sender_open_id)
    user_mem = memory_store.load_user_memory(sender_open_id) or "(chưa có ghi chú nào)"

    # .replace (KHÔNG .format) để không vỡ vì dấu {} trong ví dụ JSON của persona.
    persona = persona.replace("{today}", today)
    persona = persona.replace("{sender_name}", name)
    persona = persona.replace("{sender_role}", role)
    persona = persona.replace("{user_memory}", user_mem)

    # Shared-frame identity override: when this process runs a created agent on
    # Mark's persona, force its OWN display name so it doesn't introduce itself
    # as the name written in persona.md. Skipped when a dedicated persona file is
    # provided.
    if config.agent_name and not os.environ.get("AGENT_PERSONA_FILE", "").strip():
        persona = (
            f"# GHI ĐÈ DANH TÍNH (ưu tiên cao nhất)\n"
            f"Tên hiển thị của bạn là **{config.agent_name}**. Khi tự giới thiệu hãy xưng đúng "
            f"tên này, TUYỆT ĐỐI không tự nhận bằng tên nào khác. Mọi tính cách/cách làm việc/công cụ "
            f"bên dưới vẫn giữ nguyên.\n\n---\n" + persona
        )

    who_block = "\n".join(
        [
            "\n---\n## TRÍ NHỚ VỀ NGƯỜI NÀY (người đang nhắn ngay lúc này)",
            f"- Tên: **{name}**",
            f"- Vai trò/quan hệ: {role}",
            f"- Ghi chú dài hạn đã biết: {user_mem}",
            f"- Hôm nay: {today} (giờ VN, UTC+7).",
        ]
    )
    return (
        persona
        + who_block
        + _PLANNER_POLICY_NOTE
        + _TOOLING_NOTE
        + _platform_context_block(platform_ctx)
    )


def _resolve_agent(sender_open_id: str | None = None,
                   platform_ctx: dict | None = None) -> AIAgent:
    """Resolve Codex credentials fresh and build an AIAgent bound to them."""
    rt = resolve_runtime_provider(requested=config.agent_provider)
    return AIAgent(
        model=config.agent_model,
        provider=rt.get("provider"),
        api_mode=rt.get("api_mode"),
        base_url=rt.get("base_url"),
        api_key=rt.get("api_key"),
        max_iterations=config.agent_max_iterations,
        quiet_mode=True,
        # Curated capability set (Cách A). "lark_api" chứa lark_cli (xem
        # lark_cli_tool.py). vision/
        # file/code_execution/delegation are key-free and available out of the
        # box. "browser" = agent-browser (tự truy cập web/trang công khai, không
        # cần key). "fb_ads" = fb_ads_library (tra Meta Ad Library qua browser).
        # "social" là các nguồn nghiệp vụ trong apify_tool/deep_dive_tool.
        # "terminal"/"computer_use" vẫn tắt cho an toàn.
        enabled_toolsets=[
            "lark_api",
            "browser",
            "fb_ads",
            "social",
            "vision",
            "file",
            "code_execution",
            "delegation",
            "steven_memory",
            "steven_reminders",
        ],
        disabled_toolsets=["terminal"],
        ephemeral_system_prompt=_build_system_prompt(sender_open_id, platform_ctx),
    )


import re  # noqa: E402


def _strip_markdown(text: str) -> str:
    """Lark chat gửi VĂN BẢN THUẦN nên markdown hiện ra ký tự thô rất xấu.
    Bộ lọc quyết định (không phụ thuộc model có nghe lời hay không): bỏ **đậm**,
    *nghiêng*, `code`, ```block```, tiêu đề #/##/###, và [text](url) -> text."""
    if not text:
        return text
    # ```fenced code``` -> giữ nội dung, bỏ hàng rào
    text = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", text)
    # tiêu đề đầu dòng: "### Tiêu đề" -> "Tiêu đề"
    text = re.sub(r"(?m)^\s{0,3}#{1,6}\s+", "", text)
    # in đậm/nghiêng: **x** __x__ *x* _x_ -> x   (làm bold trước)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", text)
    text = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", text)
    # `inline code` -> inline code
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # [nhãn](link) -> nhãn (link)   ; nếu nhãn trống thì để link
    text = re.sub(r"\[([^\]]*)\]\((https?://[^)]+)\)",
                  lambda m: (m.group(1) or m.group(2)) + (f" ({m.group(2)})" if m.group(1) else ""),
                  text)
    # gạch đầu dòng markdown "* item" -> "- item" cho đồng nhất
    text = re.sub(r"(?m)^(\s*)[*+]\s+", r"\1- ", text)
    return text.strip()


def reply(user_text: str, *, chat_id: str, sender_open_id: str | None = None) -> str:
    """Generate Mark's reply, with persistent per-chat context + per-user memory."""
    # tell the remember/reminder tools the current context
    memory_store.set_current_sender(sender_open_id)
    scheduler.set_current_chat(chat_id)

    # Lịch sử hội thoại đưa vào ĐÚNG kênh conversation_history của Hermes
    # ([{"role","content"}]) thay vì nhồi thành 1 khối text — model hiểu ngữ cảnh
    # chuẩn hơn và biết "ok/đồng ý" là xác nhận việc vừa đề xuất.
    hist = memory_store.load_history(chat_id)
    history_msgs = [
        {"role": m["role"], "content": m["text"]}
        for m in hist
        if m.get("role") in ("user", "assistant") and m.get("text")
    ]
    platform_ctx = lsr_platform.lay_ngu_canh(chat_id, user_text, sender_open_id or "")
    if not history_msgs and isinstance(platform_ctx.get("recent_turns"), list):
        history_msgs = [
            {"role": m.get("role"), "content": m.get("text")}
            for m in platform_ctx["recent_turns"]
            if isinstance(m, dict)
            and m.get("role") in ("user", "assistant")
            and m.get("text")
        ]

    # AUDIT: mở một lượt trước khi gọi model. Mọi tool được gọi trong lượt này
    # tự ghi vào đó (audit.boc_registry đã bọc handler của cả 10 tool).
    turn_id = audit.bat_dau(chat_id, sender_open_id, user_text)

    agent = _resolve_agent(sender_open_id, platform_ctx)
    try:
        out = agent.run_conversation(user_text, conversation_history=history_msgs)
    except Exception as e:
        # Đóng lượt audit TRƯỚC khi ném tiếp, không thì lượt lỗi biến mất khỏi
        # bản ghi — mà đó đúng là lượt cần soi nhất.
        audit.ket_thuc(turn_id, "", agent, loi=f"{type(e).__name__}: {e}",
                       trang_thai="lỗi")
        raise
    text = (out.get("final_response") if isinstance(out, dict) else str(out)) or ""
    text = _strip_markdown(text) or "(Bot chưa tạo được câu trả lời)"

    d = out if isinstance(out, dict) else {}
    audit.ket_thuc(turn_id, text, agent, loi=str(d.get("error") or ""),
                   trang_thai="ok" if not d.get("failed") else "lỗi")

    memory_store.append_turns(
        chat_id,
        [
            {"role": "user", "text": user_text, "sender": sender_open_id},
            {"role": "assistant", "text": text},
        ],
    )
    lsr_platform.ghi_luot_ngu_canh(
        chat_id,
        user_text,
        text,
        sender_open_id or "",
        channel=(
            "web"
            if sender_open_id == "console"
            or chat_id.startswith("web:")
            or chat_id.startswith("job:")
            else "lark"
        ),
    )
    return text
