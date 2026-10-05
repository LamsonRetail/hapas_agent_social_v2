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

import http.client
import json
import os
import pathlib
import re
import threading
import urllib.error
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
    "ghi_model_vua_chay",
    "lay_model_vua_chay",
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


#: Model ĐÃ CHẠY lượt gần nhất của từng chat (tai_khoan_ai.ghi_luot ghi). Trước đây usage
#: luôn báo env AGENT_MODEL, nên lượt chạy bằng Claude bị tính tiền theo giá GPT.
_MODEL_VUA_CHAY: dict[str, str] = {}
_MODEL_KHOA = threading.Lock()


def ghi_model_vua_chay(chat_id: str, model: str) -> None:
    with _MODEL_KHOA:
        _MODEL_VUA_CHAY.pop(chat_id or "", None)
        _MODEL_VUA_CHAY[chat_id or ""] = str(model)
        # Cầu nối ngắn như audit._vua_xong, không phải kho.
        while len(_MODEL_VUA_CHAY) > 500:
            _MODEL_VUA_CHAY.pop(next(iter(_MODEL_VUA_CHAY)))


def lay_model_vua_chay(chat_id: str) -> str:
    """LẤY-VÀ-XOÁ model của lượt vừa chạy; chưa có (lệnh cứng, lượt treo) → env cũ."""
    with _MODEL_KHOA:
        m = _MODEL_VUA_CHAY.pop(chat_id or "", "")
    return m or os.environ.get("AGENT_MODEL", "unknown")


def bao_luot(run_id: str, cau_hoi: str, tra_loi: str, *, ok: bool = True,
             tool: list[str] | None = None, audit_record: dict | None = None,
             model: str = "") -> None:
    """Ghi WAL rồi báo một lượt hỏi–đáp ở nền; không đưa câu hỏi thô vào trace.
    `model` = model đã chạy (`lay_model_vua_chay`); trống thì env AGENT_MODEL như cũ."""
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
            "model": model or os.environ.get("AGENT_MODEL", "unknown"),
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
    co_anh = bool(p.get("image_key") or p.get("image_keys") or anh)
    if (str(p.get("message_type") or "") == "image" or hoi.lstrip().startswith('{"image_key"')
            or (co_anh and not hoi.strip())):
        # Tin rich-text chỉ có ảnh (không chữ) cũng vậy: lượt user không được rỗng.
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
            # Lượt rỗng / chỉ khoảng trắng không ghi: nó quay lại qua `recent_turns`
            # và làm Anthropic từ chối cả lượt sau.
            if isinstance(text, str) and text.strip():
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
                 kenh: dict | None = None, job_id=None) -> tuple[str, bool, bool]:
    """Chạy `tra_loi` với trần thời gian. Trả `(đáp, ok, quá_hạn)`.

    Vì sao cần: vòng job gọi `tra_loi` đồng bộ và KHÔNG có trần. Một lượt gọi model
    treo là cả hàng đợi đứng im — không log, không lỗi, không cách nào biết ngoài việc
    nhắn thử. Đã xảy ra 18/09: job nằm im 5 phút, khởi động lại thì job sau xong trong
    8 giây.

    Luồng quá hạn KHÔNG bị giết: Python không có cách dừng một luồng an toàn, ép dừng
    giữa lúc nó đang giữ khoá hay ghi file thì hỏng nặng hơn. Để nó là daemon, chạy nốt
    rồi tự tắt, và không chặn lúc thoát tiến trình. Đổi lại: cửa hàng đợi thông ngay.

    Lượt quá hạn chạy xong thì GỬI BÙ câu trả lời vào đúng cuộc chat (sự cố 01/10/2026:
    lượt quét 617 giây đã ra kết quả + Sheet nhưng bị bỏ, người dùng chỉ thấy câu xin
    lỗi rồi hỏi lại, cào lần hai). Ai quyết trước — luồng xong hay vòng job bỏ chờ — do
    `khoa` phân xử: xong sát hạn thì trả như lượt thường, không bao giờ mất hay ra hai tin.
    Khởi động lại bot giữa chừng thì luồng daemon chết theo — tin bù mất (nói thật ở đây).
    """
    import threading
    hop: dict = {}
    khoa = threading.Lock()

    def chay():
        # Job id gắn vào CHÍNH luồng trả lời (contextvar + sổ theo phiên), gỡ trong finally
        # của luồng này — review 02/10/2026: gỡ ở `_mot_vong` khi `_chay_co_han` trả về vì
        # quá hạn thì lượt chậm (đang tạo việc nền) mất job id, kết quả web không về được.
        if job_id is not None:
            _JOB_HIEN_TAI.set(job_id)
            with _JOB_PHIEN_KHOA:
                _JOB_PHIEN[phien] = job_id
        # Một lượt mỗi phiên: lượt quá hạn còn chạy, hoặc tin cùng cuộc chat vừa tới qua
        # cửa kia (gateway ↔ listener Lark, run._do_reply), thì chờ lượt trước xong —
        # hai lượt song song đọc/ghi lịch sử xen nhau. Chờ tối đa NỬA trần rồi chạy luôn
        # (có log): một lượt treo không được khoá chết cả cuộc chat. Khoá giữ trong luồng
        # này, không phải vòng job — vòng job không bao giờ đứng chờ một phiên.
        kp = _khoa_phien(phien)
        co_khoa = kp.acquire(timeout=max(0.0, _HAN_TRA_LOI / 2))
        if not co_khoa:
            print(f"[job] phiên còn lượt trước chưa xong sau {_HAN_TRA_LOI / 2:.0f}s — "
                  "chạy luôn", flush=True)
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
        finally:
            if co_khoa:
                kp.release()
            if job_id is not None:
                with _JOB_PHIEN_KHOA:
                    if _JOB_PHIEN.get(phien) == job_id:
                        _JOB_PHIEN.pop(phien, None)
            with khoa:
                hop["xong"] = True
                bo = hop.get("bo_lai")
            if bo:
                _gui_tra_loi_muon(hop, hoi, bo)

    t = threading.Thread(target=chay, name=f"tra-loi-{phien[:16]}", daemon=True)
    t.start()
    t.join(_HAN_TRA_LOI)
    with khoa:
        xong = bool(hop.get("xong"))
        k = None
        if not xong:
            k = _kenh_tra_loi_muon(phien, job_id, kenh)
            hop["bo_lai"] = k
    if not xong:
        phut = max(1, round(_HAN_TRA_LOI / 60))
        if k:
            return (f"Câu này cần hơn {phut} phút nên Mark trả lượt trước để không chặn "
                    "những người đang chờ. Mark vẫn đang làm tiếp và sẽ nhắn kết quả vào "
                    "đây khi xong — bạn không cần hỏi lại.", False, True)
        return ("Xin lỗi, câu này Mark xử lý lâu quá mức cho phép nên tôi dừng lượt "
                "để không chặn những người đang chờ. Bạn thử hỏi lại, hoặc thu hẹp "
                "phạm vi (ít nền tảng hơn, khoảng ngày ngắn hơn).", False, True)
    if hop.get("loi"):
        print(f"[job] lượt lỗi: {_redact(hop['loi'])}", flush=True)
    return (hop.get("dap") or "", bool(hop.get("ok")), False)


_KHOA_PHIEN: dict[str, threading.Lock] = {}
_KHOA_PHIEN_GUARD = threading.Lock()


def _khoa_phien(phien: str) -> threading.Lock:
    """Khoá theo phiên hội thoại, dùng chung cho đường job và listener Lark."""
    with _KHOA_PHIEN_GUARD:
        k = _KHOA_PHIEN.get(phien)
        if k is None:
            k = _KHOA_PHIEN[phien] = threading.Lock()
        return k


def _kenh_tra_loi_muon(phien: str, job_id, kenh: dict | None) -> dict | None:
    """Kênh để gửi bù câu trả lời muộn, None nếu phiên không đẩy tin được (hồi quy, bộ
    thử…) — khi đó vẫn báo người dùng hỏi lại như trước. Không bao giờ ném."""
    try:
        import viec_nen
        k = viec_nen.kenh_tu_chat(phien, job_id, (kenh or {}).get("chat_type") or "")
        return k if viec_nen.co_the_day(k) else None
    except Exception as e:  # noqa: BLE001
        print(f"[job] không xác định được kênh gửi bù: {type(e).__name__}", flush=True)
        return None


#: Giãn cách thử gửi bù (giây), ~4,5 phút tổng: đã hứa "không cần hỏi lại" thì phải chịu
#: được một lần platform/Lark chập lâu hơn vài giây (cùng lý do `_LUI_TRA_JOB`).
_LUI_GUI_BU = (2, 6, 20, 60, 180)


def _gui_tra_loi_muon(hop: dict, hoi: str, k: dict) -> None:
    """Gửi bù câu trả lời của lượt đã quá hạn (đã được ghi vào lịch sử chat bởi
    `brain.reply` như mọi lượt). Thử lại giãn dần; khử trùng theo job/phiên. Gửi hỏng hẳn
    thì ghi chú vào lịch sử để lượt sau Mark biết người dùng CHƯA nhận câu trả lời đó.
    Chạy trong `finally` của luồng trả lời — không bao giờ ném."""
    try:
        cau = " ".join((hoi or "").split())
        cau = cau if len(cau) <= 80 else cau[:79] + "…"
        dap = (hop.get("dap") or "").strip()
        if hop.get("ok") and dap:
            van = f"Trả lời muộn cho câu “{cau}”:\n\n{dap}"
        else:
            van = (f"Câu “{cau}” chạy quá lâu rồi gặp lỗi nên Mark chưa trả lời được. "
                   "Bạn hỏi lại giúp Mark, hoặc thu hẹp phạm vi nhé.")
        if hop.get("loi"):
            print(f"[job] lượt quá hạn lỗi: {_redact(hop['loi'])}", flush=True)
        kid = (f"j{k['job_id']}-muon" if k.get("job_id")
               else f"muon-{uuid.uuid4().hex[:16]}")[:50]
        import viec_nen
        for lan in range(len(_LUI_GUI_BU) + 1):
            try:
                viec_nen.day_theo_kenh(k, van, kid)
                print(f"[job] đã gửi bù trả lời muộn ({k.get('loai')})", flush=True)
                return
            except Exception as e:  # noqa: BLE001
                print(f"[job] gửi bù trả lời muộn lỗi lần {lan + 1}: "
                      f"{_redact(f'{type(e).__name__}: {e}')}", flush=True)
                if lan < len(_LUI_GUI_BU):
                    _ngu(_LUI_GUI_BU[lan])
        print(f"[job] BỎ gửi bù trả lời muộn sau {len(_LUI_GUI_BU) + 1} lần "
              f"({k.get('loai')})", flush=True)
        _ghi_chu_chua_gui(k, cau)
    except Exception as e:  # noqa: BLE001
        print(f"[job] gửi bù trả lời muộn hỏng: {type(e).__name__}", flush=True)


def _ghi_chu_chua_gui(k: dict, cau: str) -> None:
    """Lịch sử đã có câu trả lời (brain.reply ghi) mà người dùng chưa từng thấy — thêm
    ghi chú để lượt sau model không nói "như tôi đã trả lời ở trên"."""
    chat = k.get("chat_id") or ""
    if not chat:
        return
    chu = (f"(Ghi chú hệ thống: câu trả lời muộn cho câu “{cau}” KHÔNG gửi được tới "
           "người dùng — họ chưa thấy nó. Nếu họ hỏi lại, trả lời đầy đủ.)")
    try:
        import memory_store
        memory_store.append_turns(chat, [{"role": "assistant", "text": chu}])
    except Exception as e:  # noqa: BLE001
        print(f"[job] ghi chú chưa gửi lỗi: {type(e).__name__}", flush=True)
    ghi_luot_ngu_canh(chat, "", chu, "",
                      channel="lark" if str(k.get("loai", "")).startswith("lark") else "web")


# Job platform đang được trả lời theo từng phiên — việc NỀN ghi lại job id lúc tool được
# gọi để sau này đẩy kết quả về đúng job gốc (web console).
_JOB_PHIEN: dict[str, object] = {}
_JOB_PHIEN_KHOA = threading.Lock()
import contextvars as _cv  # noqa: E402
_JOB_HIEN_TAI: _cv.ContextVar = _cv.ContextVar("lsr_job_hien_tai", default=None)


def job_cua_phien(phien: str):
    """Job id platform đang xử lý cho `phien`, None nếu không có (tin Lark trực tiếp).
    Ưu tiên job của CHÍNH luồng đang chạy (phiên có job mới chen vào thì không lẫn)."""
    j = _JOB_HIEN_TAI.get()
    if j is not None:
        return j
    with _JOB_PHIEN_KHOA:
        return _JOB_PHIEN.get(phien or "")


def gui_lark(chat_id: str, text: str, app_id: str = "", uuid: str | None = None) -> dict:
    """Gửi tin vào chat Lark qua platform (`/v1/lark/send`) bằng token của CHÍNH agent —
    đường cho chat tới qua gateway (`lark:<app>:<oc>`), runtime không cầm secret app đó.
    `uuid` gửi kèm để khử trùng, NHƯNG platform (02/10/2026) chưa chuyển trường này xuống
    Lark — xem viec_nen.gui."""
    c = _cau_hinh()
    if not c:
        raise RuntimeError("chưa cấu hình LSR_* nên không gửi được qua platform")
    than = {"to": chat_id, "to_type": "chat_id", "app_id": app_id or None,
            "text": text[:15000]}
    if uuid:
        than["uuid"] = str(uuid)[:50]
    return _goi(c, "/v1/lark/send", than, timeout=20)


def bao_su_kien_job(job_id, text: str, ma_su_kien: str | None = None) -> dict:
    """Gắn một sự kiện "message" vào job gốc trên console (đường TẠM cho web, 02/10/2026:
    console chưa có kênh đẩy tin chủ động cho agent). `ma_su_kien` nằm trong `data.id` để
    console bỏ trùng khi agent gửi lại sau khởi động."""
    c = _cau_hinh()
    if not c or not job_id:
        raise RuntimeError("không có job gốc / chưa cấu hình LSR_*")
    data = {"text": text[:15000]}
    if ma_su_kien:
        data["id"] = ma_su_kien
    return _goi(c, f"/v1/self/jobs/{job_id}/event", {"kind": "message", "data": data},
                timeout=20)


#: Giãn cách các lần thử lại `/reply` và `/complete` (giây). Sự cố 04/10/2026 21:46:
#: job 5632 dính 502 Bad Gateway một lần là mất câu trả lời — người dùng không nhận gì.
_LUI_TRA_JOB = (1, 3, 9)
_ngu = time.sleep


def _loi_tam(e: Exception) -> bool:
    """5xx hoặc lỗi mạng = đáng thử lại. 4xx = yêu cầu sai / trạng thái sai, thử lại
    cũng thế (vd 409 job không còn running)."""
    if isinstance(e, urllib.error.HTTPError):
        return e.code >= 500
    return isinstance(e, (urllib.error.URLError, OSError, http.client.HTTPException))


def _goi_job(c: dict, duong: str, than: dict):
    """`_goi` cho `/reply` và `/complete`, thử lại tối đa 3 lần (1s, 3s, 9s) khi lỗi tạm.

    Thử lại AN TOÀN, không ra hai tin Lark — platform (`self_job_reply`) khoá theo job
    (`pg_advisory_xact_lock`) rồi kiểm job đã có sự kiện `message` chưa; có rồi thì trả
    `duplicate: true` và KHÔNG gửi ra kênh nữa. Nên 502 do proxy (handler vẫn chạy xong
    và commit) thì lần thử lại thấy bản trùng; handler còn đang chạy thì lần thử lại chờ
    khoá rồi cũng thấy bản trùng. Chỗ hở duy nhất: tiến trình platform chết ĐÚNG giữa
    lúc đã gửi Lark và lúc commit — giao dịch rollback, lần thử lại gửi thêm một tin.
    `/complete` gửi hai lần thì lần sau nhận 409 (job đã `done`) — vô hại."""
    for lan in range(len(_LUI_TRA_JOB) + 1):
        try:
            return _goi(c, duong, than)
        except Exception as e:  # noqa: BLE001
            if lan >= len(_LUI_TRA_JOB) or not _loi_tam(e):
                e.so_lan_thu = lan  # type: ignore[attr-defined]
                raise
            print(f"[job] {duong} lỗi tạm ({type(e).__name__}: {e}) — thử lại sau "
                  f"{_LUI_TRA_JOB[lan]}s", flush=True)
            _ngu(_LUI_TRA_JOB[lan])


_APP_DA_CANH_BAO: set[str] = set()


def _canh_bao_app_lech(phien: str) -> None:
    """Phiên gateway `lark:<app>:<oc>` mà <app> khác LARK_APP_ID của Mark thì cảnh báo
    MỘT lần: tin rơi vào listener (run._phien_lark) sẽ dựng phiên bằng LARK_APP_ID, lệch
    là hai cửa lại thành hai cuộc hội thoại — lỗi im lặng, chỉ log mới thấy."""
    if not str(phien).startswith("lark:"):
        return
    app = str(phien).split(":", 2)[1]
    cua_minh = (os.environ.get("LARK_APP_ID") or "").strip()
    if cua_minh and app and app != cua_minh and app not in _APP_DA_CANH_BAO:
        _APP_DA_CANH_BAO.add(app)
        print(f"[job] CẢNH BÁO: phiên gateway mang app {app} khác LARK_APP_ID "
              f"{cua_minh} — tin Lark vào thẳng listener sẽ lệch phiên", flush=True)


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
    _canh_bao_app_lech(phien)
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

    dap, ok, treo = _chay_co_han(tra_loi, hoi, phien, _lark_sender_ref(p),
                                 _kenh_cua_job(j), job_id=jid)
    if treo:
        print(f"[job] #{jid} QUÁ HẠN {_HAN_TRA_LOI:.0f}s — bỏ lượt, đi tiếp. "
              f"Luồng cũ chạy tiếp, xong thì gửi bù trả lời (nếu kênh đẩy được).",
              flush=True)

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
        # Model ĐÃ CHẠY, cùng lý do lấy-và-xoá như token: quá hạn thì giữ env cũ.
        dung["model"] = lay_model_vua_chay(phien)
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
            _goi_job(c, duong, than)
        except Exception as e:
            if (duong.endswith("/complete") and getattr(e, "code", None) == 409
                    and getattr(e, "so_lan_thu", 0)):
                # Lần trước đã tới platform, chỉ mất phản hồi — job đã done.
                print(f"[job] {duong}: đã xong từ lần gửi trước (409)", flush=True)
                continue
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
