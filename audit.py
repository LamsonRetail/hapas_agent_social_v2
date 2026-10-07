"""Audit TOÀN LUỒNG mỗi câu hỏi: token, tool đã gọi, link trả về, thời gian.

Vì sao cần
----------
Suốt đợt sửa 06–08/09/2026, mọi lỗi nặng của dự án đều **không crash, không báo
lỗi, chỉ trả sai số liệu** — và cách duy nhất tìm ra là đọc log rồi chạy lại tay
từng bước. Không có bản ghi nào cho biết một câu hỏi đã đi qua những tool nào,
tốn bao nhiêu token, trả về link gì. File này tạo ra bản ghi đó.

Một dòng = MỘT câu hỏi, đọc là thấy cả luồng:
    ai hỏi gì → gọi tool nào, mỗi tool mất bao lâu, ok hay lỗi
    → trả về link nào → tốn bao nhiêu token và bao nhiêu tiền → hết bao lâu

Hai nơi lưu, cố ý
-----------------
1. **JSONL cục bộ** (`.audit/audit-YYYY-MM.jsonl`) — ghi ĐỒNG BỘ, luôn thành
   công, không phụ thuộc mạng hay Lark. Đây là nguồn sự thật.
2. **Lark Base** — đẩy ở LUỒNG NỀN, fail-open. Để xem/lọc/thống kê cho tiện.
   Lark hỏng thì chỉ mất phần xem, không mất dữ liệu và không ảnh hưởng bot.

BA nguyên tắc, đừng bỏ khi sửa
------------------------------
1. **KHÔNG BAO GIỜ làm chết lượt trả lời.** Mọi thứ trong file này bọc
   try/except. Audit là thứ phục vụ việc chính, không được thành rủi ro cho nó.
2. **KHÔNG làm chậm lượt trả lời.** Ghi JSONL vài trăm byte thì không đáng kể;
   gọi Lark API thì đẩy sang thread nền. Trần trả lời của run.py là 180s, đã
   sát, không được ăn thêm.
3. **Không ghi bí mật.** Tham số tool bị cắt ngắn và lọc qua `_che_bi_mat()`.

Token lấy ở đâu
---------------
`brain._resolve_agent()` tạo AIAgent MỚI cho từng tin nhắn, nên các bộ đếm
`agent.session_*_tokens` (khởi tạo 0 ở `agent_init.py:2632`, được cộng ở
`codex_runtime.py:134` cho provider openai-codex mà Mark dùng) chính là số của
ĐÚNG lượt đó — không cần trừ mốc trước/sau.
"""

from __future__ import annotations

import contextvars
import datetime
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

import lark_client as lark
from config import config

_HERE = Path(__file__).resolve().parent
_THU_MUC = _HERE / ".audit"
_CAU_HINH = config.token_file.parent / "audit_base.json"   # .tokens/ (đã gitignore)
_VN = datetime.timezone(datetime.timedelta(hours=7))
_BAT = os.environ.get("AUDIT_ENABLED", "1").strip() == "1"
_DAY_LEN_BASE = os.environ.get("AUDIT_TO_BASE", "1").strip() == "1"

_URL = re.compile(r"https?://[^\s\"'<>)\]}]+")
# Cắt bí mật trước khi ghi: tham số tool do người dùng điều khiển, và lark_cli
# có thể mang theo token trong lệnh.
_BI_MAT = re.compile(
    r"(?i)\b(?:token|secret|password|api[_-]?key|authorization|bearer)\b\s*[:=]?\s*\S+")
_TOI_DA_ARG = 400
_TOI_DA_TEXT = 2000


def _che_bi_mat(s: str) -> str:
    return _BI_MAT.sub("[da_che]", s or "")


def _cat(s, n: int) -> str:
    s = _che_bi_mat(str(s or ""))
    return s if len(s) <= n else s[:n] + f"…(+{len(s) - n})"


def _links(*phan) -> list[str]:
    ra: list[str] = []
    for x in phan:
        ra += _URL.findall(str(x or ""))
    # bỏ trùng, bỏ link ảnh CDN (nhiễu — một lượt cào có thể trả hàng trăm ảnh)
    sach = [u.rstrip(".,);") for u in dict.fromkeys(ra)]
    return [u for u in sach if not re.search(r"\.(?:jpg|jpeg|png|webp|gif|svg)(?:\?|$)",
                                             u, re.I)][:20]


# ───────────────────────────── ghi JSONL ─────────────────────────────
_khoa_ghi = threading.Lock()


def _ghi(rec: dict) -> None:
    try:
        _THU_MUC.mkdir(exist_ok=True)
        f = _THU_MUC / f"audit-{datetime.datetime.now(_VN):%Y-%m}.jsonl"
        with _khoa_ghi:
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"[audit] ghi JSONL loi: {type(e).__name__}: {e}")


# ───────────────────────────── Lark Base ─────────────────────────────
# Một bảng, một dòng = một câu hỏi. Kiểu field theo API bitable:
# 1=text, 2=number, 5=datetime.
_COT = [
    ("Thời điểm", 5), ("Người hỏi", 1), ("Chat", 1),
    ("Câu hỏi", 1), ("Trả lời", 1),
    ("Tool đã gọi", 1), ("Số tool", 2), ("Link trả về", 1),
    ("Token vào", 2), ("Token ra", 2), ("Token tổng", 2),
    ("Lượt gọi API", 2), ("Chi phí USD", 2),
    ("Thời gian (giây)", 2), ("Trạng thái", 1), ("Lỗi", 1), ("Turn ID", 1),
]

_COT_V2 = [
    ("Thời gian", 5), ("Người hỏi", 1), ("Chat", 1),
    ("Câu hỏi của User", 1), ("Kết quả / Trả lời", 1),
    ("Tool gọi", 1), ("Số tool", 2), ("Link trả về", 1),
    ("Token vào", 2), ("Token ra", 2), ("Token tổng", 2),
    ("Lượt gọi API", 2), ("Chi phí USD", 2),
    ("Thời gian (giây)", 2), ("Trạng thái", 1), ("Lỗi", 1), ("Turn ID", 1),
]


def _doc_cau_hinh() -> dict:
    try:
        return json.loads(_CAU_HINH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


_khoa_moc = threading.Lock()


def _ghi_moc(turn_id: str, ts: float | None = None) -> None:
    """Ghi mốc "đã đẩy tới đâu" để `dong_bo_lai()` biết chỗ tiếp tục.

    Mốc chỉ TIẾN, không lùi: hai thread `_day()` xong lệch thứ tự (lượt cũ đẩy chậm
    hơn lượt mới) thì lượt cũ không được kéo mốc về trước lượt mới. Ghi lỗi thì IN
    ra — bản đầu nuốt im lặng, mốc kẹt lại mà không ai biết (xem `dong_bo_lai`).
    """
    if not turn_id:
        return
    try:
        with _khoa_moc:
            cfg = _doc_cau_hinh()
            if not cfg.get("table_id"):
                return   # đọc hỏng giữa chừng: đừng ghi đè mất app_token/table_id
            if ts is not None and float(cfg.get("da_day_den_ts") or 0) > ts:
                return
            cfg["da_day_den"] = turn_id
            if ts is not None:
                cfg["da_day_den_ts"] = ts
            _CAU_HINH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        print(f"[audit] ghi moc loi: {type(e).__name__}: {e}")


def _doc_jsonl_gan_day() -> list[dict]:
    """Dòng JSONL của tháng trước + tháng này, đúng thứ tự ghi.

    Đọc cả tháng trước: khởi động đầu tháng thì mốc nằm ở file tháng trước, chỉ đọc
    file tháng này là không tìm thấy mốc và lượt cuối tháng trước bị bỏ sót.
    """
    nay = datetime.datetime.now(_VN)
    truoc = nay.replace(day=1) - datetime.timedelta(days=1)
    dong: list[dict] = []
    for thang in (truoc, nay):
        f = _THU_MUC / f"audit-{thang:%Y-%m}.jsonl"
        if not f.exists():
            continue
        for x in f.read_text(encoding="utf-8").splitlines():
            if x.strip():
                try:
                    dong.append(json.loads(x))
                except ValueError:
                    continue
    return dong


def _turn_id_tren_base(cfg: dict, toi_da_trang: int = 40) -> set[str]:
    """Mọi Turn ID đang có trong bảng audit trên Base. Lỗi thì NÉM, không trả rỗng:
    trả rỗng tức là "chưa có gì" và đẩy bù sẽ nhân đôi cả bảng."""
    co: set[str] = set()
    trang = None
    for _ in range(toi_da_trang):
        q = {"page_size": 500, "field_names": json.dumps(["Turn ID"])}
        if trang:
            q["page_token"] = trang
        d = (lark.call("GET", f"/open-apis/bitable/v1/apps/{cfg['app_token']}"
                              f"/tables/{cfg['table_id']}/records", query=q)
             .get("data") or {})
        for it in d.get("items") or []:
            v = (it.get("fields") or {}).get("Turn ID")
            if isinstance(v, list):   # text field trả [{"text": ..., "type": "text"}]
                v = "".join(str(p.get("text") or "") for p in v if isinstance(p, dict))
            if v:
                co.add(str(v))
        trang = d.get("page_token")
        if not d.get("has_more") or not trang:
            return co
    raise RuntimeError(f"bang audit qua {toi_da_trang} trang, dung kiem de khoi doc nham")


def dong_bo_lai(toi_da: int = 200) -> int:
    """Đẩy bù những dòng JSONL chưa lên Base. Trả số dòng đã đẩy.

    Vì sao cần: `_day()` chạy trong thread `daemon=True` nên nếu tiến trình
    thoát ngay sau một lượt (bot restart, kill), dòng đó KHÔNG lên Base — JSONL
    vẫn có, Base thì thiếu. Bản ghi mà thiếu lỗ thì mất hết giá trị đối chiếu.

    Mốc `da_day_den` chỉ để thu hẹp chỗ cần xét; quyết định đẩy hay không là theo
    Turn ID ĐÃ CÓ TRÊN BASE. Bản đầu tin hẳn vào mốc, mà mốc có thể lệch (POST
    hết giờ chờ dù Base đã tạo dòng, ghi mốc lỗi bị nuốt) → lúc khởi động đẩy lại
    dòng đã có: 4 lượt bị nhân đôi trong bảng Audit, 25/09 và 30/09/2026. Không
    đọc được Base thì KHÔNG đẩy — lần khởi động sau thử lại, mốc vẫn giữ nguyên.
    """
    if not _DAY_LEN_BASE:
        return 0
    try:
        dong = _doc_jsonl_gan_day()
    except Exception as e:  # noqa: BLE001
        print(f"[audit] dong_bo_lai doc JSONL loi: {type(e).__name__}: {e}")
        return 0
    if not dong:
        return 0
    cfg = _doc_cau_hinh() or {}
    moc = cfg.get("da_day_den") or ""
    vt = next((i for i, r in enumerate(dong) if r.get("turn_id") == moc), -1)
    ung_vien = [r for r in dong[vt + 1:] if r.get("turn_id")]
    if not ung_vien:
        return 0
    if not cfg.get("table_id"):
        return 0   # Base chưa tạo — lượt đầu tiên sẽ tạo rồi tự đẩy
    try:
        co = _turn_id_tren_base(cfg)
    except Exception as e:  # noqa: BLE001
        print(f"[audit] dong_bo_lai: khong doc duoc Turn ID tren Base, bo qua lan nay: "
              f"{type(e).__name__}: {e}")
        return 0
    con = [r for r in ung_vien if r["turn_id"] not in co][:toi_da]
    for r in con:
        _day(r)
    cuoi = ung_vien[-1]
    if not con or cuoi["turn_id"] in co:
        _ghi_moc(cuoi["turn_id"], cuoi.get("ts"))
    if con:
        print(f"[audit] dong_bo_lai: da day bu {len(con)} dong "
              f"(bo qua {len(ung_vien) - len(con)} dong da co tren Base)")
    return len(con)


def _ten_nguoi(open_id: str) -> str:
    """Đổi open_id thành tên hiển thị. Bảng audit đầy `ou_xxx` thì không ai đọc.

    `lark_client` cache tên trên đĩa nên gọi nhiều lần không tốn thêm request.
    """
    if not open_id:
        return ""
    if not open_id.startswith("ou_"):
        return open_id
    try:
        return lark.resolve_user_name(open_id) or open_id
    except Exception:  # noqa: BLE001
        return open_id


def _tao_base(cap_quyen_cho: str = "") -> dict:
    """Tạo Base + bảng audit MỘT LẦN, ghi lại token để lần sau dùng luôn."""
    d = lark.call("POST", "/open-apis/bitable/v1/apps",
                  body={"name": "Audit Mark Trần"})
    app = ((d.get("data") or {}).get("app") or {})
    tok = app.get("app_token")
    if not tok:
        raise RuntimeError(f"khong tao duoc base: {str(d)[:200]}")
    t = lark.call("POST", f"/open-apis/bitable/v1/apps/{tok}/tables",
                  body={"table": {"name": "Audit_Logs",
                                  "fields": [{"field_name": n, "type": ty}
                                             for n, ty in _COT_V2]}})
    tid = ((t.get("data") or {}).get("table_id"))
    cfg = {"app_token": tok, "table_id": tid, "url": app.get("url") or "",
           "schema_version": 2}
    try:
        _CAU_HINH.parent.mkdir(parents=True, exist_ok=True)
        _CAU_HINH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    if cap_quyen_cho:
        # Bot tạo nên bot là chủ; KHÔNG cấp quyền thì người dùng mở không được.
        try:
            lark.call("POST", f"/open-apis/drive/v1/permissions/{tok}/members",
                      query={"type": "bitable"},
                      body={"member_type": "openid", "member_id": cap_quyen_cho,
                            "perm": "edit"})
        except Exception as e:  # noqa: BLE001
            print(f"[audit] cap quyen Base that bai: {type(e).__name__}: {e}")
    print(f"[audit] da tao Lark Base: {cfg.get('url') or tok}")
    return cfg


_da_kiem_cot = False
_khoa_cot = threading.Lock()


def _dam_bao_cot(cfg: dict) -> None:
    """Bổ sung cột còn thiếu vào bảng đã tồn tại.

    Vì sao cần: bảng được tạo MỘT LẦN ở lượt đầu. Sau này thêm cột vào `_COT`
    thì bảng cũ vẫn thiếu cột đó, và đẩy dữ liệu vào field không tồn tại là LỖI
    — cả dòng audit mất. Chạy một lần mỗi tiến trình, so tên cột rồi thêm cái
    nào chưa có.
    """
    global _da_kiem_cot
    # KHOÁ, và chỉ đánh dấu "đã kiểm" khi THÊM XONG. Bản đầu đặt cờ ngay lúc vào
    # hàm nên hai luồng `_day()` chạy song song (một từ thread nền của lượt vừa
    # xong, một từ `dong_bo_lai()`) thì luồng thứ hai bỏ qua kiểm cột rồi POST
    # trước khi cột kịp tạo -> `FieldNameNotFound`, MẤT NGUYÊN dòng audit. Đã
    # gặp thật 08/09/2026 lúc thêm cột mới vào bảng đã có.
    with _khoa_cot:
        if _da_kiem_cot:
            return
        try:
            d = lark.call("GET", f"/open-apis/bitable/v1/apps/{cfg['app_token']}"
                                 f"/tables/{cfg['table_id']}/fields",
                          query={"page_size": 100})
            co = {f.get("field_name") for f in ((d.get("data") or {}).get("items") or [])}
            for ten, ty in (_COT_V2 if cfg.get("schema_version") == 2 else _COT):
                if ten in co:
                    continue
                lark.call("POST", f"/open-apis/bitable/v1/apps/{cfg['app_token']}"
                                  f"/tables/{cfg['table_id']}/fields",
                          body={"field_name": ten, "type": ty})
                print(f"[audit] da them cot Base: {ten}")
            _da_kiem_cot = True
        except Exception as e:  # noqa: BLE001
            print(f"[audit] kiem cot Base loi (bo qua): {type(e).__name__}: {e}")


def _base_fields(rec: dict, schema_version: int = 1) -> dict:
    """Ánh xạ một lượt audit sang schema Base đang dùng."""
    fields = {
            "Thời điểm": int(rec["ts"] * 1000),
            "Người hỏi": _ten_nguoi(rec.get("nguoi") or ""),
            "Chat": rec.get("chat") or "",
            "Câu hỏi": rec.get("hoi") or "",
            "Trả lời": rec.get("tra_loi") or "",
            "Tool đã gọi": rec.get("tool_tom_tat") or "",
            "Số tool": rec.get("so_tool") or 0,
            "Link trả về": "\n".join(rec.get("link") or []),
            "Token vào": rec.get("token_vao") or 0,
            "Token ra": rec.get("token_ra") or 0,
            "Token tổng": rec.get("token_tong") or 0,
            "Lượt gọi API": rec.get("api_calls") or 0,
            "Chi phí USD": rec.get("chi_phi_usd") or 0,
            "Thời gian (giây)": rec.get("giay") or 0,
            "Trạng thái": rec.get("trang_thai") or "",
            "Lỗi": rec.get("loi") or "",
            "Turn ID": rec.get("turn_id") or "",
    }
    if schema_version >= 2:
        for old, new in (("Thời điểm", "Thời gian"),
                         ("Câu hỏi", "Câu hỏi của User"),
                         ("Trả lời", "Kết quả / Trả lời"),
                         ("Tool đã gọi", "Tool gọi")):
            fields[new] = fields.pop(old)
    return fields


def _day(rec: dict) -> None:
    """Đẩy một dòng lên Base. Chạy trong thread nền, fail-open."""
    try:
        cfg = _doc_cau_hinh() or _tao_base(rec.get("nguoi") or "")
        if not cfg.get("table_id"):
            return
        _dam_bao_cot(cfg)
        f = _base_fields(rec, cfg.get("schema_version") or 1)
        lark.call("POST", f"/open-apis/bitable/v1/apps/{cfg['app_token']}"
                          f"/tables/{cfg['table_id']}/records", body={"fields": f})
        _ghi_moc(rec.get("turn_id") or "", rec.get("ts"))
    except Exception as e:  # noqa: BLE001
        print(f"[audit] day len Base loi (bo qua): {type(e).__name__}: {e}")


def link_base() -> str:
    return (_doc_cau_hinh() or {}).get("url") or ""


# ───────────────────────── vòng đời một lượt ─────────────────────────
_dang_chay: dict[str, dict] = {}
_vua_xong: dict[str, dict] = {}
_khoa_luot = threading.Lock()
# Mark chạy nhiều chat song song (AGENT_MAX_WORKERS). Mỗi lượt giữ turn_id riêng để
# `ghi_tool()` và sổ chi phí biết mình thuộc lượt nào — không truyền tay qua 10 tool.
# ContextVar, KHÔNG threading.local: Hermes chạy tool trong ThreadPoolExecutor qua
# `contextvars.copy_context()` (xem memory_store.py), và các tool quét lại tách luồng
# con bằng `copy_context().run`. threading.local không sang được các luồng đó nên
# tool chạy ở đó mất turn_id — ghi_tool rơi mất, sổ chi phí để trống Turn ID.
_TURN: contextvars.ContextVar[str] = contextvars.ContextVar("audit_turn_id", default="")


def turn_id_hien_tai() -> str:
    """Turn ID của lượt đang chạy trong ngữ cảnh này ("" nếu ngoài lượt)."""
    return _TURN.get()


def bat_dau(chat_id: str, sender: str | None, hoi: str) -> str:
    if not _BAT:
        return ""
    tid = uuid.uuid4().hex[:12]
    with _khoa_luot:
        _dang_chay[tid] = {"turn_id": tid, "ts": time.time(), "t0": time.monotonic(),
                           "chat": chat_id or "", "nguoi": sender or "",
                           "hoi": _cat(hoi, _TOI_DA_TEXT), "tool": []}
    _TURN.set(tid)
    return tid


def ghi_tool(ten: str, args, ket_qua, giay: float, loi: str = "") -> None:
    """Ghi một lượt gọi tool vào lượt đang chạy của thread này."""
    if not _BAT:
        return
    tid = _TURN.get()
    with _khoa_luot:
        luot = _dang_chay.get(tid)
        if luot is None:
            return
        luot["tool"].append({
            "ten": ten, "giay": round(giay, 2), "loi": _cat(loi, 200),
            "args": _cat(json.dumps(args, ensure_ascii=False, default=str)
                         if not isinstance(args, str) else args, _TOI_DA_ARG),
            "link": _links(ket_qua),
            "co_ket_qua": bool(ket_qua),
        })


def ket_thuc(turn_id: str, tra_loi: str, agent=None, loi: str = "",
             trang_thai: str = "ok") -> dict:
    if not _BAT or not turn_id:
        return {}
    with _khoa_luot:
        luot = _dang_chay.pop(turn_id, None)
    if _TURN.get() == turn_id:
        # Worker thread được dùng lại cho tin sau: đừng để việc chạy ngoài lượt trên
        # thread này (việc nền, nhắc lịch) mang nhầm turn_id của lượt đã đóng.
        _TURN.set("")
    if luot is None:
        return {}

    def g(ten, mac_dinh=0):
        return getattr(agent, ten, mac_dinh) if agent is not None else mac_dinh

    tools = luot["tool"]
    link: list[str] = []
    for t in tools:
        link += t.get("link") or []
    link += _links(tra_loi)

    rec = {
        "loai": "turn", "turn_id": luot["turn_id"], "ts": luot["ts"],
        "thoi_diem": datetime.datetime.fromtimestamp(luot["ts"], _VN).isoformat(),
        "chat": luot["chat"], "nguoi": luot["nguoi"], "hoi": luot["hoi"],
        "tra_loi": _cat(tra_loi, _TOI_DA_TEXT),
        "so_tool": len(tools), "tool": tools,
        "tool_tom_tat": "; ".join(
            f"{t['ten']}({t['giay']}s{'' if not t['loi'] else ' LỖI'})" for t in tools),
        "link": list(dict.fromkeys(link))[:20],
        "token_vao": g("session_prompt_tokens"),
        "token_ra": g("session_completion_tokens"),
        "token_tong": g("session_total_tokens"),
        "api_calls": g("session_api_calls"),
        "chi_phi_usd": round(float(g("session_estimated_cost_usd", 0.0) or 0.0), 6),
        "giay": round(time.monotonic() - luot["t0"], 2),
        "trang_thai": trang_thai, "loi": _cat(loi, 500),
    }
    with _khoa_luot:
        _vua_xong[luot["chat"]] = rec
        # Chỉ là cầu nối ngắn giữa brain worker và run worker; không phải kho audit.
        while len(_vua_xong) > 500:
            _vua_xong.pop(next(iter(_vua_xong)))
    _ghi(rec)
    if _DAY_LEN_BASE:
        threading.Thread(target=_day, args=(rec,), daemon=True).start()
    return rec


def lay_luot_vua_xong(chat_id: str) -> dict:
    """Lấy-và-xoá telemetry lượt cuối của chat để gửi sang Platform đúng một lần."""
    with _khoa_luot:
        return _vua_xong.pop(chat_id or "", {})


# ───────────────────── bọc toàn bộ tool trong registry ─────────────────────
_da_boc = False


def boc_registry() -> int:
    """Bọc handler của MỌI tool đã đăng ký để tự ghi audit.

    Bọc ở registry là chỗ duy nhất bắt được cả 10 tool bằng một lần sửa — không
    phải đi thêm code vào từng file tool (và nhớ thêm cho tool mới sau này).
    Gọi SAU khi tất cả tool đã import xong, xem cuối brain.py.
    """
    global _da_boc
    if _da_boc or not _BAT:
        return 0
    try:
        from tools.registry import registry  # type: ignore
    except Exception as e:  # noqa: BLE001
        print(f"[audit] khong nap duoc registry: {type(e).__name__}")
        return 0

    def boc(ten: str, goc):
        # Chữ ký CỐ ĐỊNH `handler(args, **kwargs)` — xem tools/registry.py:753.
        # Đoán sai chữ ký ở đây là vỡ cả 10 tool, nên bám đúng chỗ registry gọi.
        def da_boc(args, **kw):
            t0 = time.monotonic()
            try:
                kq = goc(args, **kw)
                ghi_tool(ten, args, kq, time.monotonic() - t0)
                return kq
            except Exception as e:
                ghi_tool(ten, args, None, time.monotonic() - t0,
                         loi=f"{type(e).__name__}: {e}")
                raise
        da_boc.__name__ = getattr(goc, "__name__", ten)
        da_boc.__doc__ = getattr(goc, "__doc__", None)
        return da_boc

    def boc_async(ten: str, goc):
        async def da_boc(args, **kw):
            t0 = time.monotonic()
            try:
                kq = await goc(args, **kw)
                ghi_tool(ten, args, kq, time.monotonic() - t0)
                return kq
            except Exception as e:
                ghi_tool(ten, args, None, time.monotonic() - t0,
                         loi=f"{type(e).__name__}: {e}")
                raise
        da_boc.__name__ = getattr(goc, "__name__", ten)
        da_boc.__doc__ = getattr(goc, "__doc__", None)
        return da_boc

    dem = bo_qua = 0
    try:
        for ten, entry in list(getattr(registry, "_tools", {}).items()):
            h = getattr(entry, "handler", None)
            if h is None or getattr(h, "_audit", False):
                continue
            if getattr(entry, "is_async", False):
                moi = boc_async(ten, h)
            else:
                moi = boc(ten, h)
            moi._audit = True
            entry.handler = moi
            dem += 1
    except Exception as e:  # noqa: BLE001
        print(f"[audit] boc registry loi: {type(e).__name__}: {e}")
    _da_boc = True
    print(f"[audit] da boc {dem} tool"
          + (f" (bo qua {bo_qua} tool async)" if bo_qua else ""))
    return dem
