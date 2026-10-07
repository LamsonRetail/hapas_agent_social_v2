"""Provider Promptfoo: chạy `brain.reply` của Mark trong MÔI TRƯỜNG THỬ, không đụng production.

Promptfoo nạp file này MỘT lần cho mỗi worker rồi gọi `call_api` cho từng ca. Môi trường thử
dựng ở lần gọi đầu (không lúc nạp file): Promptfoo chỉ chờ worker Python sẵn sàng khoảng
2 phút, còn import brain và đọc ngữ cảnh prod có thể lâu hơn.

Môi trường thử (giống harness staging dùng khi viết 9 kỹ năng SOW ngày 06/10):
- Nạp .env của Mark vào os.environ (KHÔNG in giá trị). Đường dẫn: biến MARK_ENV_FILE, mặc
  định `<repo>/.env`.
- Ngữ cảnh platform: đọc bản PROD thật của Mark một lần (chỉ GET), rồi THAY mục lục kỹ năng
  bằng mục lục dựng từ `<repo>/skills` — để chấm kỹ năng trên nhánh trước khi publish.
- `dung_ky_nang` trả THÂN kỹ năng từ file cục bộ.
- Chặn mọi đường GHI: báo lượt, ghi ngữ cảnh, báo lỗi tài khoản AI, đẩy audit lên Base, tạo
  Lark Sheet, cấp quyền Sheet, chạy actor Apify, tool đổi trạng thái (nhắc hẹn, ghi nhớ...).
  Tool tốn tiền chỉ được gọi ở chế độ `chi_uoc_tinh`.
- Người hỏi: MARK_EVAL_SENDER (open_id chủ agent) — chỉ để doc_bang/dem_bang kiểm quyền ĐỌC.

Trả về: `output` là câu trả lời của Mark; `metadata` có danh sách tool đã gọi, tham số, mã kỹ
năng đã nạp, lỗi tool — kiem.py dùng metadata để chấm hành vi.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[2]
CHU = os.environ.get("MARK_EVAL_SENDER", "ou_5b597bb7e77ee9e1721ff5ea8fe5be93")
_MOI_TRUONG: dict = {}


def _nap_env() -> None:
    f = pathlib.Path(os.environ.get("MARK_ENV_FILE") or REPO / ".env")
    if not f.is_file():
        raise RuntimeError(f"không thấy file env của Mark: {f} (đặt MARK_ENV_FILE)")
    for d in f.read_text(encoding="utf-8").splitlines():
        d = d.strip()
        if d and not d.startswith("#") and "=" in d:
            k, v = d.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")
    os.environ["AUDIT_TO_BASE"] = "0"
    os.environ["LSR_JOB_POLL_ENABLED"] = "0"
    # observe/off thì guard vẫn gọi handler thật dù decide() từ chối — bản vá chặn ghi bên
    # dưới mất tác dụng. .env máy dev có thể còn sót chế độ đó, nên ép enforce.
    os.environ["LSR_POLICY_MODE"] = "enforce"
    if not os.environ.get("AGENT_BOSS_OPEN_ID", "").strip():
        os.environ["AGENT_BOSS_OPEN_ID"] = CHU


def _chan(viec):
    def f(*a, **k):
        raise RuntimeError(f"môi trường nghiệm thu: chặn {viec}")
    return f


def _dung_moi_truong() -> dict:
    if _MOI_TRUONG:
        return _MOI_TRUONG
    _nap_env()
    os.chdir(REPO)
    for p in (REPO, REPO / "scripts"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    import dong_bo_tieu_su as DB
    import lsr_platform

    ky = DB.doc_ky_nang()
    than = {DB.ma_ky_nang(k["name"]): k for k in ky}
    muc_luc = ("## Kỹ năng của bạn — nạp khi cần\nMỗi dòng dưới đây là một bộ hướng dẫn CHI TIẾT "
               "đang nằm sẵn, chưa nạp. Thấy việc đang làm khớp cột “khi nào dùng” thì gọi tool "
               "`dung_ky_nang` với đúng mã để lấy hướng dẫn đầy đủ, RỒI MỚI LÀM. Không khớp thì "
               "đừng gọi — gọi thừa chỉ tốn lượt.\n"
               + "\n".join(f"- `{DB.ma_ky_nang(k['name'])}` · **{k['name']}** — khi nào dùng: "
                           f"{k['description']}" for k in ky))
    goc_ngu_canh = lsr_platform.lay_ngu_canh
    ctx_prod: dict = {}

    def lay_ngu_canh(session_id, q, user_ref=""):
        if "base" not in ctx_prod:
            ctx_prod["base"] = goc_ngu_canh("thu-nghiem-thu-ctx", "x", "")
            if not ctx_prod["base"].get("instruction_block"):
                raise RuntimeError("không đọc được ngữ cảnh prod của Mark — không chấm bằng prompt rỗng")
        ctx = json.loads(json.dumps(ctx_prod["base"]))
        ib = ctx.get("instruction_block") or ""
        m = re.search(r"## Kỹ năng của bạn — nạp khi cần.*?(?=\n## |\Z)", ib, re.S)
        ctx["instruction_block"] = (ib[:m.start()] + muc_luc + ib[m.end():]) if m else ib + "\n\n" + muc_luc
        ctx["recent_turns"], ctx["rolling_summary"], ctx["user_facts"] = [], "", []
        ctx["session_id"] = session_id
        return ctx

    lsr_platform.lay_ngu_canh = lay_ngu_canh
    lsr_platform.ghi_luot_ngu_canh = lambda *a, **k: False
    lsr_platform.bao_luot = lambda *a, **k: None

    import ky_nang_tool

    def goi_ky_nang(sid):
        k = than.get(sid)
        if not k:
            return 404, None
        return 200, {"skill_id": sid, "name": k["name"], "description": k["description"],
                     "instructions": k["instructions"]}

    ky_nang_tool._goi = goi_ky_nang
    ky_nang_tool._NHO.clear()

    import tai_khoan_ai
    tai_khoan_ai.bao_loi = lambda *a, **k: False

    import apify_tool
    # Vá TRƯỚC khi brain import các tool dùng `from apify_tool import _call, _create_sheet, ...`.
    apify_tool._call = _chan("chạy actor Apify")
    apify_tool._create_sheet = _chan("tạo Lark Sheet")
    apify_tool._write_values = _chan("ghi Lark Sheet")
    apify_tool._grant = _chan("cấp quyền Lark Sheet")

    import lsr_policy
    goc_decide = lsr_policy.decide

    def decide_thu(tool_name, args=None):
        if tool_name in lsr_policy._MUTATING_EXACT and not (args or {}).get("chi_uoc_tinh"):
            return lsr_policy.PolicyDecision(False, "môi trường nghiệm thu: chặn tool ghi/tốn "
                                                    "tiền (chỉ cho chi_uoc_tinh)")
        return goc_decide(tool_name, args)

    lsr_policy.decide = decide_thu

    import audit
    import brain  # sau các bản vá: brain gắn guard lúc import
    _MOI_TRUONG.update(brain=brain, audit=audit)
    return _MOI_TRUONG


def _ma_ky_nang_da_nap(tools: list[dict]) -> list[str]:
    ra = []
    for t in tools:
        if t.get("ten") != "dung_ky_nang":
            continue
        a = t.get("args")
        if isinstance(a, str):
            try:
                a = json.loads(a)
            except ValueError:
                a = {}
        sid = (a or {}).get("skill_id") if isinstance(a, dict) else None
        if sid:
            ra.append(sid)
    return ra


def call_api(prompt: str, options: dict, context: dict) -> dict:
    v = (context or {}).get("vars") or {}
    ma = re.sub(r"[^0-9A-Za-z_-]", "", str(v.get("ma") or "ca"))[:40]
    phien = f"thu-nghiem-thu-{ma}-{int(time.time() * 1000)}"
    luot_truoc = v.get("luot_truoc") or []
    if isinstance(luot_truoc, str):
        luot_truoc = [luot_truoc]
    try:
        mt = _dung_moi_truong()
        brain, audit = mt["brain"], mt["audit"]
        for cau in luot_truoc:
            brain.reply(cau, chat_id=phien, sender_open_id=CHU, kenh={"chat_type": "p2p"})
            audit.lay_luot_vua_xong(phien)
        t0 = time.time()
        dap = brain.reply(prompt, chat_id=phien, sender_open_id=CHU, kenh={"chat_type": "p2p"})
        giay = round(time.time() - t0, 1)
    except Exception as e:  # noqa: BLE001 — báo lỗi cho Promptfoo, không làm sập worker
        return {"error": f"{type(e).__name__}: {e}"}
    luot = audit.lay_luot_vua_xong(phien) or {}
    tools = (luot.get("tool") or []) if isinstance(luot, dict) else []
    return {
        "output": dap or "",
        "latencyMs": int(giay * 1000),
        "metadata": {
            "tool": [t.get("ten") for t in tools],
            "tool_args": [t.get("args") if isinstance(t.get("args"), (dict, list))
                          else str(t.get("args"))[:2000] for t in tools],
            "tool_loi": [t.get("loi") or "" for t in tools],
            "ky_nang": _ma_ky_nang_da_nap(tools),
            "giay": giay,
        },
    }
