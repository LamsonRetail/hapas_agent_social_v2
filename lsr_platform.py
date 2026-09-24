"""Adapter tạm thời nối Mark vào LSR Agent Platform.

Adapter có bốn việc: poll job web, lấy context/version/RAG, ghi session và đẩy
telemetry qua WAL. Đây là đường chuyển tiếp cho Hermes theo draft EXTC; đích lâu
dài vẫn là ``lsr_hive`` theo ADR 0002.

VÌ SAO CẦN
----------
`AG-SOCIAL-LISTENING` (Mark Trần) đã nhận vai trên platform, nhưng console hiện
sức khoẻ là "never" — chưa từng nhận được tín hiệu nào. Không phải agent hỏng;
là chưa có ai nối dây. File này là sợi dây đó.

BA NGUYÊN TẮC
-------------
1. **Thiếu cấu hình thì im lặng rút lui.** Không có `LSR_TELEMETRY_API_KEY` thì
   mọi hàm ở đây trở thành no-op. Bot chạy y hệt hôm nay, không một byte khác.

2. **Không bao giờ làm hỏng một câu trả lời.** Mọi lỗi mạng, mọi lỗi phân giải
   tên miền, mọi 500 từ collector đều bị nuốt tại đây. Người dùng đang đợi bot
   trả lời — họ không cần biết telemetry có gửi được hay không.

3. **Audit không chặn nhưng không được mất.** Trace được ghi WAL cục bộ trước,
   rồi gửi ở luồng nền; platform lỗi thì lần khởi động sau flush lại.

CẦN GÌ ĐỂ BẬT
-------------
Ba biến trong `.env`. Hai cái đầu điền được ngay; cái thứ ba **chỉ quản trị viên
platform cấp được**:

    LSR_COLLECTOR         = https://collector.34-124-212-76.sslip.io
    LSR_AGENT_ID          = AG-SOCIAL-LISTENING
    LSR_TELEMETRY_API_KEY = lsr_tel_...      ← xin admin

Telemetry key chỉ hiện MỘT LẦN lúc tạo agent và platform không lưu bản rõ (chỉ
giữ sha256). Không có endpoint cấp lại. Nên phải nhờ admin chạy
`POST /v1/agents/register` trên VM — lời gọi đó cấp key mới.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import threading
import urllib.parse
import urllib.request
import uuid

__all__ = [
    "bat",
    "bao_luot",
    "chay_vong_job",
    "dong_bo_auth",
    "flush_wal",
    "ghi_luot_ngu_canh",
    "lay_ngu_canh",
]

_TIMEOUT = 5


def _cau_hinh() -> dict | None:
    """Trả cấu hình nếu đủ ba biến, ngược lại None (= tắt hẳn)."""
    url = (os.environ.get("LSR_COLLECTOR") or "").strip().rstrip("/")
    aid = (os.environ.get("LSR_AGENT_ID") or "").strip()
    key = (os.environ.get("LSR_TELEMETRY_API_KEY") or "").strip()
    if not (url and aid and key):
        return None
    platform = (os.environ.get("LSR_PLATFORM_URL") or url.replace("collector.", "platform."))
    return {"url": url, "platform": platform.rstrip("/"), "agent_id": aid, "key": key}


def bat() -> str:
    """Gọi một lần lúc khởi động. Trả về một dòng để in ra cho người vận hành."""
    c = _cau_hinh()
    if not c:
        thieu = [t for t, v in (
            ("LSR_COLLECTOR", os.environ.get("LSR_COLLECTOR")),
            ("LSR_AGENT_ID", os.environ.get("LSR_AGENT_ID")),
            ("LSR_TELEMETRY_API_KEY", os.environ.get("LSR_TELEMETRY_API_KEY")),
        ) if not (v or "").strip()]
        return f"Platform:   TẮT (thiếu {', '.join(thieu)}) — bot chạy bình thường"
    threading.Thread(target=flush_wal, name="lsr-wal-flush", daemon=True).start()
    poll = "bật" if _job_poll_duoc_phep(c) else "tắt"
    return f"Platform:   {c['agent_id']} → {c['platform']} · job poll {poll}"


_WAL_LOCK = threading.Lock()
_SECRET_RE = re.compile(
    r"(?i)\b(?:token|secret|password|api[_-]?key|authorization|bearer)\b\s*[:=]?\s*\S+"
)
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)")
_OPEN_ID_RE = re.compile(r"\bou_[A-Za-z0-9_-]{8,}\b")


def _redact(value: str) -> str:
    text = str(value or "")
    text = _SECRET_RE.sub("[đã_che_bí_mật]", text)
    text = _EMAIL_RE.sub("[đã_che_email]", text)
    text = _PHONE_RE.sub("[đã_che_sđt]", text)
    return _OPEN_ID_RE.sub("[đã_che_open_id]", text)


def _wal_dir() -> pathlib.Path:
    configured = (os.environ.get("LSR_WAL_DIR") or "").strip()
    return pathlib.Path(configured) if configured else pathlib.Path(__file__).parent / ".audit" / "platform-wal"


def _post_trace(trace: dict, c: dict) -> bool:
    req = urllib.request.Request(
        c["url"] + "/v1/traces",
        data=json.dumps(trace, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {c['key']}"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=_TIMEOUT).close()
        return True
    except Exception:
        return False


def _queue_trace(trace: dict) -> pathlib.Path | None:
    try:
        root = _wal_dir()
        root.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", str(trace.get("run_id") or "unknown"))[:80]
        target = root / f"{safe}-{uuid.uuid4().hex[:10]}.json"
        temp = target.with_suffix(".tmp")
        with _WAL_LOCK:
            temp.write_text(json.dumps(trace, ensure_ascii=False), encoding="utf-8")
            temp.replace(target)
        return target
    except Exception as exc:
        print(f"[platform] không ghi được WAL: {type(exc).__name__}: {exc}")
        return None


def _gui(wal_path: pathlib.Path, c: dict) -> None:
    try:
        trace = json.loads(wal_path.read_text(encoding="utf-8"))
        if _post_trace(trace, c):
            wal_path.unlink(missing_ok=True)
    except Exception:
        # WAL còn nguyên cho lần flush sau.
        return


def flush_wal(max_items: int = 200) -> dict:
    """Flush tối đa ``max_items`` trace; an toàn để gọi lại sau crash."""
    c = _cau_hinh()
    if not c:
        return {"sent": 0, "pending": 0, "enabled": False}
    root = _wal_dir()
    paths = sorted(root.glob("*.json"))[:max(1, max_items)] if root.exists() else []
    sent = 0
    for path in paths:
        try:
            trace = json.loads(path.read_text(encoding="utf-8"))
            if not _post_trace(trace, c):
                break
            path.unlink(missing_ok=True)
            sent += 1
        except Exception:
            break
    pending = len(list(root.glob("*.json"))) if root.exists() else 0
    return {"sent": sent, "pending": pending, "enabled": True}


def bao_luot(run_id: str, cau_hoi: str, tra_loi: str, *, ok: bool = True,
             tool: list[str] | None = None, audit_record: dict | None = None) -> None:
    """Ghi WAL rồi báo một lượt hỏi–đáp ở nền; không đưa câu hỏi thô vào trace."""
    c = _cau_hinh()
    if not c:
        return
    record = audit_record or {}
    tool_rows = record.get("tool") if isinstance(record.get("tool"), list) else []
    if not tool_rows:
        tool_rows = [{"ten": name, "co_ket_qua": True} for name in (tool or [])]
    trace = {
        "run_id": run_id or "unknown",
        "agent_id": c["agent_id"],
        "task_id": run_id or "",
        "source": os.environ.get("LSR_TRACE_SOURCE")
                  or ("test" if c["agent_id"].endswith("-TEST") else "production"),
        "llm_calls": [{
            "model": os.environ.get("AGENT_MODEL", "unknown"),
            "input_tokens": int(record.get("token_vao") or 0),
            "output_tokens": int(record.get("token_ra") or 0),
        }],
        "tool_calls": [{
            "name": row.get("ten") or "unknown",
            "ok": not bool(row.get("loi")),
            "has_result": bool(row.get("co_ket_qua")),
            "duration_ms": int(float(row.get("giay") or 0) * 1000),
            "error": _redact(row.get("loi") or "")[:300],
        } for row in tool_rows if isinstance(row, dict)],
        "duration_ms": int(float(record.get("giay") or 0) * 1000),
        "status": "ok" if ok else "error",
        "final_output": _redact(tra_loi)[:4000],
    }
    path = _queue_trace(trace)
    if path:
        threading.Thread(target=_gui, args=(path, c), daemon=True).start()


# ─────────────────────────── cầu nối tài khoản model ───────────────────────────
# Platform giữ tài khoản AI của đội và phát cho agent khi agent hỏi. Hermes thì
# KHÔNG đọc biến môi trường — nó đọc `HERMES_HOME/auth.json`, cấu trúc lồng khác.
# Hàm dưới bắc cầu giữa hai hình dạng đó. Không đụng logic: nó chỉ đặt credential
# vào đúng ô, việc gọi model vẫn nguyên của Hermes.
#
#   platform trả              →  ô trong auth.json của Hermes
#   secret.tokens.*              providers["openai-codex"].tokens.*
#   secret.auth_mode             providers["openai-codex"].auth_mode
#
# Mặc định là CHẠY THỬ: dựng bản mới ra file cạnh bên rồi báo khác nhau chỗ nào,
# KHÔNG ghi đè. Ghi thật phải gọi rõ `ghi=True`, và khi đó vẫn sao lưu trước.
#
# Không bao giờ trả về hay in ra token — chỉ trả về những gì so sánh được.

import copy
import shutil
import time

PROVIDER = "openai-codex"


def _duong_auth() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HERMES_HOME") or "") / "auth.json"


def _xin_lease() -> tuple[dict | None, str]:
    c = _cau_hinh()
    if not c:
        return None, "chưa cấu hình LSR_* — bỏ qua"
    # Lease nằm ở platform, không phải collector.
    base = c["url"].replace("collector.", "platform.")
    req = urllib.request.Request(
        base + "/v1/self/model-auth/lease", data=b"{}",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {c['key']}"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8")), "ok"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def dong_bo_auth(ghi: bool = False) -> dict:
    """Kéo tài khoản model từ platform về đúng ô của Hermes.

    ghi=False (mặc định) — dựng bản mới ra `auth.json.moi`, báo khác gì, không đụng.
    ghi=True             — sao lưu `auth.json.truoc-<ts>` rồi mới ghi đè.
    """
    bc: dict = {"ghi": ghi}

    lease, vi_sao = _xin_lease()
    if not lease:
        return {**bc, "ok": False, "ly_do": vi_sao}
    if lease.get("provider") != "openai":
        return {**bc, "ok": False,
                "ly_do": f"platform phát provider {lease.get('provider')!r} mà Hermes "
                         f"đang chạy openai-codex — không ép khớp"}
    try:
        moi = json.loads(lease.get("secret") or "{}")
    except Exception:
        return {**bc, "ok": False, "ly_do": "secret không phải JSON"}
    if not (moi.get("tokens") or {}).get("access_token"):
        return {**bc, "ok": False, "ly_do": "lease không mang access_token"}

    f = _duong_auth()
    if not f.is_file():
        return {**bc, "ok": False, "ly_do": f"không thấy {f}"}

    cu = json.loads(f.read_text(encoding="utf-8"))
    ra = copy.deepcopy(cu)
    o = ra.setdefault("providers", {}).setdefault(PROVIDER, {})
    truoc_tok = dict((cu.get("providers", {}).get(PROVIDER, {}).get("tokens") or {}))

    o["tokens"] = {**(o.get("tokens") or {}), **moi["tokens"]}
    if moi.get("auth_mode"):
        o["auth_mode"] = moi["auth_mode"]
    # Giữ ĐÚNG kiểu Hermes đang dùng: chuỗi ISO 8601 có Z, không phải số giây.
    # Ghi số vào đây là đổi kiểu dữ liệu dưới chân một thư viện không phải của
    # mình — nó có thể nổ ở chỗ chẳng liên quan gì tới credential.
    o["last_refresh"] = (
        __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z")
    # Vừa lấy credential mới thì lỗi đăng nhập cũ không còn nghĩa lý gì.
    o.pop("last_auth_error", None)
    ra["active_provider"] = ra.get("active_provider") or PROVIDER

    # So sánh mà KHÔNG lộ giá trị: chỉ nói trường nào đổi và dài bao nhiêu.
    doi = [{"truong": k, "cu_dai": len(truoc_tok.get(k) or ""),
            "moi_dai": len(o["tokens"].get(k) or "")}
           for k in ("id_token", "access_token", "refresh_token", "account_id")
           if truoc_tok.get(k) != o["tokens"].get(k)]

    bc.update({
        "ok": True,
        "tai_khoan": lease.get("label"),
        "nguon": lease.get("mode"),
        "file": str(f),
        "truong_doi": doi,
        "provider_khac_giu_nguyen": [k for k in cu.get("providers", {}) if k != PROVIDER],
        "xoa_last_auth_error": "last_auth_error" in (
            cu.get("providers", {}).get(PROVIDER, {})),
    })

    if not ghi:
        thu = f.with_name("auth.json.moi")
        thu.write_text(json.dumps(ra, ensure_ascii=False, indent=2), encoding="utf-8")
        bc["ban_thu"] = str(thu)
        return bc

    luu = f.with_name(f"auth.json.truoc-{int(time.time())}")
    shutil.copy2(f, luu)
    f.write_text(json.dumps(ra, ensure_ascii=False, indent=2), encoding="utf-8")
    bc["sao_luu"] = str(luu)
    return bc


# ──────────────────────────── cửa vào thứ hai: job ────────────────────────────
# Bot này chỉ nghe sự kiện Lark. Người quản trị nhắn thử trên console thì platform
# tạo một JOB rồi chờ agent tới lấy — không có ai lấy thì tin nằm đó mãi, và console
# không nói gì cả. Vòng dưới là chân đi lấy.
#
# Đây là CỬA VÀO, không phải logic: nó đưa câu hỏi vào đúng `brain.reply` mà
# listener Lark vẫn gọi, rồi trả kết quả về platform. Bộ não không biết câu hỏi
# đến từ Lark hay từ console — đúng như thiết kế của `/v1/self/jobs/{id}/reply`:
# "code agent KHÔNG cần biết tin đến từ Lark, Telegram, web chat hay agent khác".
#
# KHÔNG gọi `bao_luot` cho job: `/complete` đã tự ghi một trace, gọi thêm là đếm đôi
# — chính tài liệu của endpoint đó dặn vậy.

_NHIP_CHO = 25          # giây long-poll mỗi vòng; platform chặn trần ở 30


def _platform_base(c: dict) -> str:
    return c["platform"]


def _goi(c: dict, duong: str, body=None, timeout=35):
    req = urllib.request.Request(
        _platform_base(c) + duong,
        data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {c['key']}"},
        method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
        return json.loads(raw) if raw.strip() else {}


def _context_env(c: dict) -> str:
    requested = (os.environ.get("LSR_CONTEXT_ENV") or "").strip().lower()
    if c["agent_id"].endswith("-TEST"):
        return requested if requested in {"dev", "stg", "prod"} else "dev"
    # Production ID không được vô tình đọc bản dev.
    return "prod"


def _lark_sender_ref(payload: dict) -> str | None:
    """Chỉ đưa Lark user open_id thật vào ``brain.reply``.

    Web console dùng email làm ``user_ref``. Truyền email vào tham số
    ``sender_open_id`` khiến brain gọi Contact API như thể đó là ``ou_...`` và
    sinh một lỗi 400 vô ích cho mỗi web job.
    """
    # Job Lark mang người gửi ở `sender_open_id`; chỉ job console mới có `user_ref`.
    # Bản trước chỉ đọc `user_ref`, nên MỌI tin Lark tới qua gateway đều mất người gửi —
    # đếm 25/09: 54/70 lượt Lark trong sổ audit có `nguoi` trống. Hệ quả là Mark không
    # biết ai đang nói: không nhận ra sếp, không có trí nhớ theo người, ai cũng bị đối
    # xử như "chưa rõ danh tính, giữ chừng mực".
    for k in ("user_ref", "sender_open_id"):
        ref = str((payload or {}).get(k) or "").strip()
        if ref.startswith("ou_"):
            return ref
    return None


def _kenh_cua_job(j: dict) -> dict | None:
    """Nhóm hay chat riêng — Mark cần biết để trả lời đúng kiểu.

    None khi job không mang `chat_type` (job console, job thử): khi đó `tra_loi` được
    gọi y như trước, nên các bộ thử có `tra_loi` giả không phải sửa gì.
    """
    rt = j.get("reply_to") or {}
    ct = str(rt.get("chat_type") or "").strip().lower()
    if not ct:
        return None
    return {"chat_type": "p2p" if ct == "p2p" else "group"}


#: Trần mỗi ảnh tải về. Ảnh chụp màn hình quảng cáo/bài đăng hiếm khi quá vài MB; ảnh
#: lớn hơn thường là file gửi nhầm và chỉ tốn thời gian tải lẫn lượt đọc của model.
_TRAN_ANH = 10 * 1024 * 1024
_GIU_ANH_GIAY = 24 * 3600


def _tai_anh(c: dict, j: dict) -> list[str]:
    """Tải ảnh người dùng gửi kèm tin Lark về thư mục đính kèm. Trả danh sách đường dẫn.

    Gateway đẩy `image_key` (tin ảnh) hoặc `image_keys` (ảnh nhúng trong tin có chữ).
    Tải qua `/v1/lark/resource/...` bằng token của CHÍNH agent — không cầm app secret.
    Hỏng ảnh nào thì bỏ ảnh đó và in ra, không làm hỏng cả lượt trả lời.
    """
    from lsr_policy import THU_MUC_DINH_KEM
    p = j.get("payload") or {}
    mid = str(p.get("message_id") or "").strip()
    keys = ([p["image_key"]] if p.get("image_key") else []) + list(p.get("image_keys") or [])
    if not (mid and keys):
        return []
    app_id = str((j.get("reply_to") or {}).get("app_id") or "")
    THU_MUC_DINH_KEM.mkdir(exist_ok=True)
    # Dọn ảnh cũ — thư mục này chỉ để model đọc trong lượt, không phải kho lưu trữ.
    han = time.time() - _GIU_ANH_GIAY
    for cu in THU_MUC_DINH_KEM.glob("*"):
        try:
            if cu.is_file() and cu.stat().st_mtime < han:
                cu.unlink()
        except OSError:
            pass
    ra = []
    for k in keys[:4]:
        k = str(k).strip()
        if not k:
            continue
        q = urllib.parse.urlencode({"type": "image", "app_id": app_id})
        req = urllib.request.Request(
            f"{_platform_base(c)}/v1/lark/resource/{urllib.parse.quote(mid)}/"
            f"{urllib.parse.quote(k)}?{q}",
            headers={"Authorization": f"Bearer {c['key']}"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                du_lieu = r.read(_TRAN_ANH + 1)
                kieu = (r.headers.get("Content-Type") or "").lower()
        except Exception as e:
            print(f"[anh] không tải được {k[:24]}: {type(e).__name__}: {e}", flush=True)
            continue
        if len(du_lieu) > _TRAN_ANH:
            print(f"[anh] bỏ {k[:24]}: quá {_TRAN_ANH // 1024 // 1024} MB", flush=True)
            continue
        duoi = ".png" if "png" in kieu else ".webp" if "webp" in kieu else \
               ".gif" if "gif" in kieu else ".jpg"
        # Tên file chỉ gồm ký tự an toàn: message_id/file_key do Lark cấp nhưng vẫn là
        # dữ liệu từ ngoài, không ghép thẳng vào đường dẫn.
        ten = re.sub(r"[^A-Za-z0-9_-]", "_", f"{mid}_{k}")[:120] + duoi
        f = THU_MUC_DINH_KEM / ten
        f.write_bytes(du_lieu)
        ra.append(str(f))
    return ra


def _cau_hoi_kem_anh(hoi: str, j: dict, anh: list[str]) -> str:
    """Ghép câu hỏi với dòng `[Ảnh đính kèm: …]` mà prompt dặn model đọc bằng vision.

    Tin CHỈ có ảnh thì gateway đưa nguyên nội dung thô `{"image_key": "img_v3_…"}` làm
    text — model thấy một chuỗi JSON khó hiểu. Thay bằng một câu nói rõ là có ảnh.
    """
    p = j.get("payload") or {}
    if str(p.get("message_type") or "") == "image" or hoi.lstrip().startswith('{"image_key"'):
        hoi = "(Người dùng gửi một ảnh, không kèm chữ.)"
    if not anh:
        if p.get("image_key") or p.get("image_keys"):
            # Có ảnh mà không tải được: nói THẬT với model, để nó không đoán nội dung ảnh.
            hoi += "\n[Có ảnh đính kèm nhưng Mark không tải được — nói thẳng với người dùng.]"
        return hoi
    return hoi + "".join(f"\n[Ảnh đính kèm: {a}]" for a in anh)


def lay_ngu_canh(session_id: str, q: str, user_ref: str = "") -> dict:
    """Lấy instruction/version/RAG. Lỗi mạng trả ``{}`` để không chặn câu trả lời."""
    c = _cau_hinh()
    if not c:
        return {}
    query = urllib.parse.urlencode({
        "session_id": session_id or "",
        "q": q or "",
        "user_ref": user_ref or "",
        "env": _context_env(c),
        # Runtime này có tool `dung_ky_nang` (ky_nang_tool.py), nên xin bản MỤC LỤC kỹ
        # năng: tên + khi nào dùng + mã, thân nạp khi model thấy khớp. Platform chỉ trả
        # bản đó cho runtime nào tự báo — runtime không có tool vẫn nhận bản đầy đủ.
        "skills": "lazy",
    })
    try:
        result = _goi(c, f"/v1/self/context?{query}", timeout=12)
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}


def ghi_luot_ngu_canh(session_id: str, user_text: str, assistant_text: str,
                       user_ref: str = "", channel: str = "") -> bool:
    """Best-effort append hai turn vào Memory Service của Platform."""
    c = _cau_hinh()
    if not c or not session_id:
        return False
    try:
        for role, text in (("user", user_text), ("assistant", assistant_text)):
            if text:
                _goi(c, "/v1/self/session/turn", {
                    "session_id": session_id,
                    "role": role,
                    "text": text[:4000],
                    "user_ref": user_ref or None,
                    "channel": channel or None,
                }, timeout=10)
        return True
    except Exception:
        return False


#: Trần thời gian cho MỘT lượt trả lời. Rộng tay vì `social_listen` cào năm nền tảng
#: có thể chạy vài phút thật — cắt sớm là giết việc hợp lệ. Nhưng phải có trần: vòng
#: job chạy tuần tự, nên một lượt treo là đứng cả cửa console lẫn cửa Lark.
_HAN_TRA_LOI = float(os.environ.get("LSR_HAN_TRA_LOI_SECONDS", "480"))


def _chay_co_han(tra_loi, hoi: str, phien: str, sender,
                 kenh: dict | None = None) -> tuple[str, bool, bool]:
    """Chạy `tra_loi` với trần thời gian. Trả `(đáp, ok, quá_hạn)`.

    Vì sao cần: vòng job gọi `tra_loi` đồng bộ và KHÔNG có trần. Một lượt gọi model
    treo là cả hàng đợi đứng im — không log, không lỗi, không cách nào biết ngoài việc
    nhắn thử. Đã xảy ra 18/09: job nằm im 5 phút, khởi động lại thì job sau xong trong
    8 giây.

    Luồng quá hạn KHÔNG bị giết: Python không có cách dừng một luồng an toàn, ép dừng
    giữa lúc nó đang giữ khoá hay ghi file thì hỏng nặng hơn. Để nó là daemon, chạy nốt
    rồi tự tắt, và không chặn lúc thoát tiến trình. Đổi lại: cửa hàng đợi thông ngay.
    """
    import threading
    hop: dict = {}

    def chay():
        try:
            # `kenh` chỉ truyền khi có — `tra_loi` giả của các bộ thử không nhận nó.
            them = {"kenh": kenh} if kenh else {}
            hop["dap"] = tra_loi(hoi, chat_id=phien, sender_open_id=sender, **them) or ""
            hop["ok"] = True
        except Exception as e:
            hop["dap"] = ("Xin lỗi, Mark gặp lỗi khi xử lý. Mã job đã được ghi để "
                          "quản trị viên kiểm tra.")
            hop["ok"] = False
            hop["loi"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=chay, name=f"tra-loi-{phien[:16]}", daemon=True)
    t.start()
    t.join(_HAN_TRA_LOI)
    if t.is_alive():
        return ("Xin lỗi, câu này Mark xử lý lâu quá mức cho phép nên tôi dừng lượt "
                "để không chặn những người đang chờ. Bạn thử hỏi lại, hoặc thu hẹp "
                "phạm vi (ít nền tảng hơn, khoảng ngày ngắn hơn).", False, True)
    if hop.get("loi"):
        print(f"[job] lượt lỗi: {hop['loi']}", flush=True)
    return (hop.get("dap") or "", bool(hop.get("ok")), False)


def _mot_vong(c: dict, tra_loi) -> int:
    """Lấy tối đa một job, xử lý, trả lời. Trả về số job đã làm."""
    try:
        jobs = _goi(c, f"/v1/self/jobs?wait={_NHIP_CHO}&max=1")
    except Exception:
        time.sleep(5)          # platform lăn ra thì nghỉ rồi thử lại, không quay tít
        return 0
    if not isinstance(jobs, list) or not jobs:
        return 0

    j = jobs[0]
    jid = j.get("id")
    p = j.get("payload") or {}
    hoi = (p.get("text") or "").strip()
    phien = j.get("session_id") or f"job:{jid}"
    t0 = time.time()

    # In NGAY khi nhận, đừng đợi xong mới in. Trước đây chỉ có một dòng lúc hoàn tất,
    # nên một job treo trông y hệt "không có job nào" — không cách nào phân biệt bằng
    # log. Đúng chuyện đã xảy ra 18/09: job #1985 nằm im, không dòng nào báo.
    print(f"[job] #{jid} nhận · {hoi[:56]!r}", flush=True)

    anh = []
    try:
        anh = _tai_anh(c, j)
    except Exception as e:
        print(f"[anh] lỗi tải ảnh job #{jid}: {type(e).__name__}: {e}", flush=True)
    hoi = _cau_hoi_kem_anh(hoi, j, anh)

    dap, ok, treo = _chay_co_han(tra_loi, hoi, phien, _lark_sender_ref(p), _kenh_cua_job(j))
    if treo:
        print(f"[job] #{jid} QUÁ HẠN {_HAN_TRA_LOI:.0f}s — bỏ lượt, đi tiếp. "
              f"Luồng cũ vẫn chạy nền và sẽ tự tắt khi xong.", flush=True)

    # Token của lượt vừa chạy. Đường Lark lấy qua `audit.lay_luot_vua_xong` trong
    # run.py; đường job trước đây chỉ gửi model + duration, nên dashboard báo 0 token
    # dù model đã chạy thật (bàn giao 17/09 mục 5). `lay_luot_vua_xong` là LẤY-VÀ-XOÁ
    # theo chat_id, mà `tra_loi` ở trên vừa chạy dưới đúng `phien` này — nên số lấy ra
    # là của chính lượt này, không phải của lượt khác.
    dung = {"model": os.environ.get("AGENT_MODEL", "unknown"),
            "duration_ms": int((time.time() - t0) * 1000)}
    # Quá hạn thì KHÔNG đụng vào sổ token: lượt chưa kết thúc, `lay_luot_vua_xong` là
    # LẤY-VÀ-XOÁ, gọi lúc này sẽ cướp mất số của lượt đang chạy dở và ghi nhầm cho job
    # đã bỏ. Thà thiếu số còn hơn số sai.
    if not treo:
        try:
            import audit
            ghi = audit.lay_luot_vua_xong(phien) or {}
            vao, ra = int(ghi.get("token_vao") or 0), int(ghi.get("token_ra") or 0)
            if vao or ra:
                dung["input_tokens"], dung["output_tokens"] = vao, ra
        except Exception as e:
            print(f"[job] không lấy được token: {type(e).__name__}: {e}", flush=True)

    for duong, than in (
        (f"/v1/self/jobs/{jid}/reply", {"text": dap}),
        (f"/v1/self/jobs/{jid}/complete", {"ok": ok, "usage": dung}),
    ):
        try:
            _goi(c, duong, than)
        except Exception as e:
            print(f"[job] {duong} lỗi: {type(e).__name__}: {e}", flush=True)
    print(
        f"[job] #{jid} {'xong' if ok else 'LỖI'} · {hoi[:40]!r} → {dap[:60]!r}",
        flush=True,
    )
    return 1


def _job_poll_duoc_phep(c: dict) -> bool:
    if os.environ.get("LSR_JOB_POLL_ENABLED", "0").strip() != "1":
        return False
    if c["agent_id"].endswith("-TEST"):
        return True
    return os.environ.get("LSR_ALLOW_PRODUCTION_POLL", "0").strip() == "1"


def chay_vong_job(tra_loi, stop_event: threading.Event | None = None) -> bool:
    """Chạy vòng lấy job ở luồng nền. `tra_loi(text, chat_id=, sender_open_id=) -> str`.

    Trả False nếu chưa cấu hình — khi đó bot chạy y như cũ, chỉ mất cửa console.
    """
    c = _cau_hinh()
    if not c or not _job_poll_duoc_phep(c):
        return False
    stopper = stop_event or threading.Event()

    def vong():
        while not stopper.is_set():
            try:
                _mot_vong(c, tra_loi)
            except Exception as e:
                print(f"[job] vòng lặp lỗi: {type(e).__name__}: {e}", flush=True)
                time.sleep(10)

    threading.Thread(target=vong, name="lsr-job", daemon=True).start()
    return True
