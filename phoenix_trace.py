"""Trace lượt của Mark sang Arize Phoenix tự host (OpenTelemetry, OTLP/HTTP).

VÌ SAO
------
Audit (audit.py) ghi MỘT dòng mỗi lượt: hỏi, đáp, tên tool, tổng token. Muốn biết
lượt chậm ở đâu — lần gọi model nào, tool nào, thử lại mấy lần, đổi tài khoản lúc
nào — thì cần cây span. Phoenix vẽ cây đó nếu span mang tên thuộc tính OpenInference.

CÁCH LÀM
--------
Không monkey-patch SDK. Hermes đã có hook QUAN SÁT (chỉ đọc, Hermes tự nuốt lỗi):
`post_api_request`, `api_request_error`, `post_tool_call` (+ `pre_api_request` khi
bật MARK_PHOENIX_LLM_INPUT=1). Mô-đun này đăng ký các hook đó ngay trong tiến trình
qua `PluginContext.register_hook`, và bọc `brain.reply` bằng `luot` để mở span gốc:

    mark.turn            CHAIN  (một lượt brain.reply)
    ├── llm <model>      LLM    (mỗi lần gọi nhà cung cấp, kể cả lần lỗi)
    ├── tool <tên>       TOOL   (mỗi lần gọi tool, kể cả tool chạy ở luồng khác)
    └── ...

Span con dựng LÙI theo `started_at`/`ended_at` của Hermes nên không giữ span mở nào.
KHÔNG dùng hook đổi hành vi (`pre_tool_call`, `pre_llm_call`, `transform_*`).

BA NGUYÊN TẮC
-------------
1. **Thiếu cấu hình thì tắt hẳn.** Không có `PHOENIX_COLLECTOR_ENDPOINT` (hoặc thiếu
   `MARK_PHOENIX_SALT`, hoặc chưa cài gói opentelemetry) thì không import OTel, không
   đăng ký hook — Hermes `has_hook` vẫn False, không dựng payload nào. Bot y như cũ.
2. **Không bao giờ làm hỏng câu trả lời.** Mọi đường ở đây bọc try/except; xuất span
   chạy ở luồng nền của BatchSpanProcessor, Phoenix chết thì span rơi, Mark vẫn trả lời.
3. **Không đẩy bí mật / danh tính ra ngoài.** Mọi chuỗi qua `_sach` (token Apify, giá trị
   bí mật trong env, sk-/JWT/token Lark, `lsr_platform._redact`: email, SĐT, ou_…) rồi
   cắt ngắn. chat_id/open_id thành HMAC. System prompt KHÔNG BAO GIỜ được xuất.
   `MARK_PHOENIX_CONTENT=off` bỏ hết chữ, chỉ còn tên, thời gian, token, trạng thái.

Provider RIÊNG (không đặt global) — trong venv Hermes có nhiều thứ dò OTel toàn cục.
"""
from __future__ import annotations

import functools
import hashlib
import hmac
import inspect
import json
import os
import re
import sys
import threading
import time
import urllib.parse

__all__ = ["bat", "luot"]

#: Gói cần (chỉ khi bật): `pip install -r requirements-phoenix.txt` vào venv chạy Mark.
_GOI = "opentelemetry-sdk==1.39.1 opentelemetry-exporter-otlp-proto-http==1.39.1"

# Tên thuộc tính OpenInference — chỉ là chuỗi, không cần gói semantic-conventions.
_KIND = "openinference.span.kind"
_KIND_GOC = "CHAIN"

_TOI_DA_VAO = 4000
_TOI_DA_ARG = 2000
_TOI_DA_RA = 4000
_TOI_DA_LOI = 500
_TOI_DA_TIN = 2000      # mỗi tin trong llm.input_messages
_TOI_DA_SO_TIN = 20     # chỉ giữ chừng ấy tin cuối của lịch sử

_khoa = threading.Lock()
_tt: dict = {"tracer": None, "provider": None, "hook": False, "dau_cuoi": "",
             "da_bao_thieu_goi": False, "da_hen_tat": False,
             # Sổ hook ĐÃ gắn của chính mô-đun này (không đọc `_hooks` riêng của Hermes):
             # (PluginManager đã gắn, tập tên hook). Manager khác → gắn lại từ đầu.
             "mgr_da_gan": None, "hook_da_gan": set()}

# Lượt đang chạy của ngữ cảnh này. ContextVar riêng (không đụng context OTel toàn cục):
# Hermes chạy tool song song qua `contextvars.copy_context()` nên tool thấy được lượt
# như audit._TURN thấy turn_id. Tạo lười để import mô-đun không có tác dụng phụ.
_ROOT = None
# Lưới dự phòng: tool chạy ở luồng không mang ngữ cảnh → tìm lượt theo session_id Hermes.
_theo_phien: dict[str, "_Luot"] = {}
# MARK_PHOENIX_LLM_INPUT=1: tin gửi model, giữ theo api_request_id tới post_api_request.
_tin_cho: dict[str, tuple[float, list]] = {}


def _ctxvar():
    global _ROOT
    if _ROOT is None:
        import contextvars
        with _khoa:
            if _ROOT is None:
                _ROOT = contextvars.ContextVar("mark_phoenix_luot", default=None)
    return _ROOT


# ───────────────────────── cấu hình ─────────────────────────
def _dau_cuoi() -> str:
    return (os.environ.get("PHOENIX_COLLECTOR_ENDPOINT") or "").strip()


def _muoi() -> str:
    return (os.environ.get("MARK_PHOENIX_SALT") or "").strip()


def _co_noi_dung() -> bool:
    return (os.environ.get("MARK_PHOENIX_CONTENT") or "scrubbed").strip().lower() not in (
        "off", "0", "tat", "tắt", "none")


def _co_tin_vao() -> bool:
    return (os.environ.get("MARK_PHOENIX_LLM_INPUT") or "0").strip() == "1"


def _du_an() -> str:
    return (os.environ.get("PHOENIX_PROJECT_NAME") or "").strip() or "mark"


def _dang_bat() -> bool:
    """Đọc lại env mỗi lượt: bộ thử xoá biến thì tắt ngay dù provider đã dựng."""
    return _tt["tracer"] is not None and bool(_dau_cuoi()) and bool(_muoi())


def _hien_dia_chi(ep: str) -> str:
    """Chỉ scheme://host:port — không in đường dẫn/user:pass nếu lỡ có."""
    try:
        u = urllib.parse.urlsplit(ep)
        return f"{u.scheme}://{u.hostname}" + (f":{u.port}" if u.port else "")
    except Exception:
        return "?"


# ───────────────────────── che & bí danh ─────────────────────────
_TOKEN_TRAN = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_.-]{20,}"
    r"|apify_api_[A-Za-z0-9]{8,}|[tu]-[A-Za-z0-9._-]{20,})")
#: "Authorization: Bearer <tok>": `_redact` khớp "Authorization: Bearer" rồi DỪNG (\S+ ăn
#: chữ "Bearer"), để lọt chính token phía sau — che token sau "Bearer" trước.
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}")
#: Tên biến env chứa bí mật — lấy GIÁ TRỊ thật để thay nguyên văn ở mọi chuỗi.
_TEN_BI_MAT = re.compile(r"(?i)(TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|_KEY$|SALT|COOKIE)")
# Bản sao của lsr_platform._redact, chỉ dùng khi không import được lsr_platform.
_SECRET_RE = re.compile(
    r"(?i)\b(?:token|secret|password|api[_-]?key|authorization|bearer)\b\s*[:=]?\s*\S+")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)")
_OPEN_ID_RE = re.compile(r"\bou_[A-Za-z0-9_-]{8,}\b")
#: MỌI loại id Lark, không chỉ ou_ như `_redact`: on_ (union), oc_ (chat), og_, od_
#: (phòng ban), om_ (tin nhắn), cli_ (app id). Kết quả tool/lỗi Lark đầy các id này,
#: và chat_id thô đặt cạnh nội dung là lần ngược được cuộc chat — HMAC trên span gốc vô ích.
_ID_LARK = re.compile(r"(?<![A-Za-z0-9])(?:ou|on|oc|og|od|om)_[A-Za-z0-9_-]{8,}"
                      r"|(?<![A-Za-z0-9])cli_[A-Za-z0-9]{8,}")


def _redact_tai_cho(s: str) -> str:
    s = _SECRET_RE.sub("[đã_che_bí_mật]", s)
    s = _EMAIL_RE.sub("[đã_che_email]", s)
    s = _PHONE_RE.sub("[đã_che_sđt]", s)
    return _OPEN_ID_RE.sub("[đã_che_open_id]", s)


def _che_token_tai_cho(s: str) -> str:
    """Như apify_tool._che_token khi chưa nạp apify_tool (bộ thử, run.py trước brain)."""
    tok = (os.environ.get("APIFY_TOKEN") or "").strip()
    if tok:
        s = s.replace(tok, "***").replace(urllib.parse.quote(tok), "***")
    return re.sub(r"(?i)(token=)[^&\s'\"]+", r"\1***", s)


def _gia_tri_bi_mat() -> list[str]:
    """Giá trị ≥12 ký tự của mọi biến env tên như bí mật, dài trước (thay chuỗi dài trước)."""
    vals = set()
    for k, v in os.environ.items():
        v = (v or "").strip()
        if len(v) >= 12 and _TEN_BI_MAT.search(k):
            vals.add(v)
    return sorted(vals, key=len, reverse=True)


def _sach(gia_tri, toi_da: int = _TOI_DA_RA) -> str:
    """Che mọi thứ nhạy cảm trong một chuỗi rồi cắt ngắn. Không bao giờ ném."""
    try:
        s = gia_tri if isinstance(gia_tri, str) else str(gia_tri)
        # Cắt thô RẤT rộng rồi mới che: cắt sát rồi che thì mảnh token nằm vắt qua mép
        # cắt lọt ra. Kết quả tool có thể cỡ MB; 200k ký tự regex vẫn chỉ vài ms.
        s = s[:200_000]
        apify = sys.modules.get("apify_tool")
        s = apify._che_token(s) if apify is not None and hasattr(apify, "_che_token") \
            else _che_token_tai_cho(s)
        for v in _gia_tri_bi_mat():
            if v in s:
                s = s.replace(v, "[đã_che_bí_mật]")
            q = urllib.parse.quote(v)
            if q != v and q in s:
                s = s.replace(q, "[đã_che_bí_mật]")
        s = _BEARER.sub("Bearer [đã_che_bí_mật]", s)
        s = _TOKEN_TRAN.sub("[đã_che_bí_mật]", s)
        lp = sys.modules.get("lsr_platform")
        s = lp._redact(s) if lp is not None and hasattr(lp, "_redact") else _redact_tai_cho(s)
        s = _ID_LARK.sub("[đã_che_id_lark]", s)
        if len(s) > toi_da:
            s = s[:toi_da] + "…[cắt]"
        return s
    except Exception:
        return "[không che được — bỏ nội dung]"


def _bi_danh(x, tien_to: str) -> str:
    """HMAC-SHA256(MARK_PHOENIX_SALT, x)[:16] — cùng id ra cùng bí danh, không lần ngược."""
    x = str(x or "")
    if not x:
        return ""
    h = hmac.new(_muoi().encode("utf-8"), x.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{tien_to}_{h[:16]}"


def _json(o, toi_da: int) -> str:
    try:
        s = o if isinstance(o, str) else json.dumps(o, ensure_ascii=False, default=str)
    except Exception:
        s = str(o)
    return _sach(s, toi_da)


# ───────────────────────── provider / exporter ─────────────────────────
class _XuatAnToan:
    """Bọc exporter: nuốt mọi lỗi xuất, log MỘT dòng gọn mỗi 5 phút (không traceback).

    OTLPSpanExporter ném ConnectionError khi Phoenix tắt; BatchSpanProcessor sẽ log
    nguyên traceback mỗi lô — journal của Mark ngập. Lô hỏng thì bỏ, không thử lại.
    """

    def __init__(self, ben_trong):
        self._trong = ben_trong
        self._lan_bao = 0.0

    def export(self, spans):
        from opentelemetry.sdk.trace.export import SpanExportResult
        try:
            return self._trong.export(spans)
        except Exception as e:  # noqa: BLE001
            now = time.monotonic()
            if now - self._lan_bao > 300:
                self._lan_bao = now
                print(f"[phoenix] không gửi được trace ({type(e).__name__}) — bỏ lô, "
                      f"Mark vẫn chạy", flush=True)
            return SpanExportResult.FAILURE

    def shutdown(self):
        try:
            self._trong.shutdown()
        except Exception:
            pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        try:
            return bool(self._trong.force_flush(timeout_millis))
        except Exception:
            return False


def _dung_provider(exporter=None, dong_bo: bool | None = None):
    """Dựng TracerProvider riêng. Mặc định: OTLP/HTTP tới PHOENIX_COLLECTOR_ENDPOINT +
    BatchSpanProcessor. Bộ thử truyền `exporter` (InMemorySpanExporter) — khi đó
    `dong_bo` mặc định True (SimpleSpanProcessor) để đọc span ngay."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

    if exporter is None:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        ep = _dau_cuoi().rstrip("/")
        if not ep.endswith("/v1/traces"):
            ep += "/v1/traces"
        key = (os.environ.get("PHOENIX_API_KEY") or "").strip()
        exporter = OTLPSpanExporter(
            endpoint=ep, headers={"authorization": f"Bearer {key}"} if key else None,
            timeout=3)
        if dong_bo is None:
            dong_bo = False
    elif dong_bo is None:
        dong_bo = True
    # shutdown_on_exit=False: SDK không tự gắn atexit cho MỖI provider (bộ thử dựng hàng
    # chục cái); Mark tự tắt đúng một provider đang dùng qua `_tat` (atexit hẹn ở bat()).
    provider = TracerProvider(resource=Resource.create({
        "service.name": "mark", "openinference.project.name": _du_an()}),
        shutdown_on_exit=False)
    if dong_bo:
        provider.add_span_processor(SimpleSpanProcessor(_XuatAnToan(exporter)))
    else:
        # on_end chỉ xếp hàng; xuất ở luồng nền. Hàng đầy thì span rơi, không chặn.
        provider.add_span_processor(BatchSpanProcessor(
            _XuatAnToan(exporter), max_queue_size=2048, schedule_delay_millis=2000,
            max_export_batch_size=256, export_timeout_millis=5000))
    cu = _tt.get("provider")
    _tt["provider"] = provider
    _tt["tracer"] = provider.get_tracer("mark.phoenix")
    if cu is not None and cu is not provider:
        try:
            cu.shutdown()
        except Exception:
            pass
    return provider


def _tat() -> None:
    """Lúc thoát tiến trình: xả span còn trong hàng (BatchSpanProcessor chờ tối đa
    export_timeout_millis=5s, exporter timeout 3s) rồi tắt. Không bao giờ ném."""
    try:
        p = _tt.get("provider")
        _tt["tracer"] = None
        if p is not None:
            p.shutdown()
    except Exception:
        pass


def _dang_ky_hook() -> bool:
    """Gắn hook quan sát vào PluginManager của Hermes. Idempotent. False = chưa gắn
    được (Hermes chưa import được — run.py gọi trước brain; brain gọi lại sau)."""
    try:
        from hermes_cli.plugins import PluginContext, PluginManifest, get_plugin_manager
    except Exception:
        return False
    try:
        mgr = get_plugin_manager()
        can = [("post_api_request", _on_post_api), ("api_request_error", _on_api_error),
               ("post_tool_call", _on_post_tool)]
        if _co_tin_vao():
            can.append(("pre_api_request", _on_pre_api))
        with _khoa:
            if _tt["mgr_da_gan"] is not mgr:
                _tt["mgr_da_gan"], _tt["hook_da_gan"] = mgr, set()
            da_gan = _tt["hook_da_gan"]
            ctx = PluginContext(PluginManifest(name="mark_phoenix", source="user"), mgr)
            for ten, cb in can:
                if ten not in da_gan:
                    ctx.register_hook(ten, cb)
                    da_gan.add(ten)
        _tt["hook"] = bool(mgr.has_hook("post_api_request"))
        return _tt["hook"]
    except Exception as e:  # noqa: BLE001
        print(f"[phoenix] không gắn được hook Hermes: {type(e).__name__}", flush=True)
        return False


def bat() -> str:
    """Gọi lúc khởi động (brain lúc import, run.py lúc in trạng thái). Idempotent.
    Trả một dòng trạng thái cho người vận hành."""
    try:
        ep = _dau_cuoi()
        if not ep:
            return "Phoenix:    TẮT (chưa đặt PHOENIX_COLLECTOR_ENDPOINT)"
        if not _muoi():
            return "Phoenix:    TẮT (thiếu MARK_PHOENIX_SALT — cần để băm chat/người dùng)"
        with _khoa:
            if _tt["tracer"] is None or _tt["dau_cuoi"] != ep:
                try:
                    _dung_provider()
                except ImportError:
                    if not _tt["da_bao_thieu_goi"]:
                        _tt["da_bao_thieu_goi"] = True
                        print(f"[phoenix] chưa cài gói OpenTelemetry → tắt trace "
                              f"(cài: {_GOI})", flush=True)
                    return "Phoenix:    TẮT (chưa cài gói opentelemetry)"
                _tt["dau_cuoi"] = ep
                if not _tt["da_hen_tat"]:
                    import atexit
                    atexit.register(_tat)
                    _tt["da_hen_tat"] = True
        hook = _dang_ky_hook()
        nd = "nội dung đã che" if _co_noi_dung() else "không nội dung"
        if _co_noi_dung() and _co_tin_vao():
            nd += " + tin vào model"
        return (f"Phoenix:    BẬT → {_hien_dia_chi(ep)} · project {_du_an()} · {nd} · "
                + ("hook ✅" if hook else "hook chờ nạp brain"))
    except Exception as e:  # noqa: BLE001
        return f"Phoenix:    TẮT (lỗi khởi động {type(e).__name__}) — bot chạy bình thường"


# ───────────────────────── một lượt ─────────────────────────
class _Luot:
    __slots__ = ("span", "ctx", "t0", "chat", "phien", "mo_hinh", "nha_cc", "lenh",
                 "so_llm", "so_tool", "audit_tid", "dong", "khoa")

    def __init__(self, span, ctx, chat: str):
        self.span, self.ctx, self.chat = span, ctx, chat
        self.t0 = time.time()
        self.phien: set[str] = set()
        self.mo_hinh = self.nha_cc = self.lenh = self.audit_tid = ""
        self.so_llm = self.so_tool = 0
        self.dong = False
        self.khoa = threading.Lock()


def _set(span, k: str, v) -> None:
    try:
        if v is None or v == "":
            return
        span.set_attribute(k, v)
    except Exception:
        pass


def _kenh_cua(chat: str, sender: str) -> str:
    if sender == "console" or chat.startswith("web:"):
        return "web"
    if chat.startswith("job:"):
        return "job"
    return "lark"


def _mo_luot(fn, args, kwargs):
    if not _dang_bat():
        return None
    try:
        from opentelemetry import trace
        from opentelemetry.context import Context
        try:
            b = inspect.signature(fn).bind_partial(*args, **kwargs).arguments
        except Exception:
            b = dict(kwargs)
        hoi = b.get("user_text", args[0] if args else "")
        chat = str(b.get("chat_id") or "")
        sender = str(b.get("sender_open_id") or "")
        kenh = b.get("kenh") if isinstance(b.get("kenh"), dict) else {}
        chat_type = str(kenh.get("chat_type") or "")
        span = _tt["tracer"].start_span("mark.turn", context=Context())
        l = _Luot(span, trace.set_span_in_context(span, Context()), chat)
        _set(span, _KIND, _KIND_GOC)
        _set(span, "session.id", _bi_danh(chat, "c"))
        if sender:
            _set(span, "user.id", _bi_danh(sender, "u"))
        _set(span, "tag.tags", [t for t in (_kenh_cua(chat, sender), chat_type) if t])
        if _co_noi_dung():
            _set(span, "input.value", _sach(hoi, _TOI_DA_VAO))
            _set(span, "input.mime_type", "text/plain")
        m = re.match(r"\s*/([A-Za-z_]+)", str(hoi or ""))
        l.lenh = m.group(1).lower() if m else ""
        return l
    except Exception:
        return None


def _ban_ghi_audit(l: _Luot) -> dict:
    """Bản ghi audit lượt vừa đóng của chat này (CHỈ ĐỌC, không lấy-và-xoá như
    `lay_luot_vua_xong` — run.py còn cần nó cho platform)."""
    try:
        a = sys.modules.get("audit")
        if a is None:
            return {}
        with a._khoa_luot:
            rec = dict(a._vua_xong.get(l.chat) or {})
        if float(rec.get("ts") or 0) >= l.t0 - 1:
            return rec
    except Exception:
        pass
    return {}


def _dong_luot(l: _Luot, kq=None, loi: BaseException | None = None) -> None:
    try:
        from opentelemetry.trace import Status, StatusCode
        with l.khoa:
            if l.dong:
                return
            l.dong = True
        with _khoa:
            for p in l.phien:
                if _theo_phien.get(p) is l:
                    _theo_phien.pop(p, None)
        span = l.span
        rec = _ban_ghi_audit(l)
        # model/provider CUỐI của lượt (sau đổi tài khoản) lấy từ hook LLM cuối cùng.
        meta = {"audit_turn_id": rec.get("turn_id") or l.audit_tid or "",
                "lenh": l.lenh, "model": l.mo_hinh, "provider": l.nha_cc,
                "so_lan_goi_model": l.so_llm, "so_tool": l.so_tool}
        meta = {k: v for k, v in meta.items() if v not in ("", None)}
        _set(span, "metadata", json.dumps(meta, ensure_ascii=False))
        if loi is not None:
            mo_ta = type(loi).__name__
            if _co_noi_dung():
                mo_ta = _sach(f"{type(loi).__name__}: {loi}", _TOI_DA_LOI)
            span.add_event("exception", {"exception.type": type(loi).__name__,
                                         **({"exception.message": mo_ta}
                                            if _co_noi_dung() else {})})
            span.set_status(Status(StatusCode.ERROR, mo_ta))
        else:
            if _co_noi_dung() and kq is not None:
                _set(span, "output.value", _sach(kq, _TOI_DA_RA))
                _set(span, "output.mime_type", "text/plain")
            if rec.get("trang_thai") == "lỗi":
                span.set_status(Status(StatusCode.ERROR, "lượt lỗi (xem audit)"))
            else:
                span.set_status(Status(StatusCode.OK))
        span.end()
    except Exception:
        try:
            l.span.end()
        except Exception:
            pass


def luot(fn):
    """Bọc `brain.reply`: một span gốc mỗi lượt. Tắt thì gọi thẳng `fn`, không thêm gì.
    Lỗi của `fn` ném ra NGUYÊN VẸN; lỗi của trace không bao giờ tới `fn`."""

    @functools.wraps(fn)
    def boc(*args, **kwargs):
        l = _mo_luot(fn, args, kwargs)
        if l is None:
            return fn(*args, **kwargs)
        try:
            token = _ctxvar().set(l)
        except Exception:
            token = None
        try:
            kq = fn(*args, **kwargs)
        except BaseException as e:
            _dong_luot(l, loi=e)
            raise
        finally:
            if token is not None:
                try:
                    _ctxvar().reset(token)
                except Exception:
                    pass
        _dong_luot(l, kq=kq)
        return kq

    return boc


# ───────────────────────── hook Hermes ─────────────────────────
def _luot_cua(kw: dict) -> _Luot | None:
    """Lượt chứa sự kiện hook: ngữ cảnh hiện tại, không có thì theo session_id."""
    if not _dang_bat():
        return None
    sid = str(kw.get("session_id") or "")
    l = _ctxvar().get()
    if l is not None and not l.dong:
        if sid and sid not in l.phien:
            with _khoa:
                l.phien.add(sid)
                _theo_phien[sid] = l
                while len(_theo_phien) > 500:
                    _theo_phien.pop(next(iter(_theo_phien)))
        return l
    if sid:
        with _khoa:
            l = _theo_phien.get(sid)
        if l is not None and not l.dong:
            return l
    return None


def _ns(giay, mac_dinh: int) -> int:
    try:
        g = float(giay)
        if g > 1e9:          # epoch giây hợp lệ
            return int(g * 1e9)
    except Exception:
        pass
    return mac_dinh


def _nha_cung_cap(p: str) -> str:
    p = (p or "").lower()
    if "anthropic" in p or "claude" in p:
        return "anthropic"
    if "openai" in p or "codex" in p:
        return "openai"
    return p


def _ghi_audit_tid(l: _Luot) -> None:
    if l.audit_tid:
        return
    try:
        a = sys.modules.get("audit")
        if a is not None:
            l.audit_tid = a.turn_id_hien_tai() or ""
    except Exception:
        pass


def _chu_cua(noi_dung) -> str:
    """Nội dung tin (chuỗi hoặc list part) → chữ thuần."""
    if isinstance(noi_dung, str):
        return noi_dung
    if isinstance(noi_dung, list):
        phan = []
        for p in noi_dung:
            if isinstance(p, str):
                phan.append(p)
            elif isinstance(p, dict) and isinstance(p.get("text"), str):
                phan.append(p["text"])
        return "\n".join(phan)
    return "" if noi_dung is None else str(noi_dung)


def _on_pre_api(**kw) -> None:
    """Chỉ khi MARK_PHOENIX_LLM_INPUT=1: giữ tin gửi model (BỎ system/developer)."""
    try:
        if not (_co_noi_dung() and _co_tin_vao()) or _luot_cua(kw) is None:
            return
        rid = str(kw.get("api_request_id") or "")
        body = ((kw.get("request") or {}).get("body") or {}) if isinstance(
            kw.get("request"), dict) else {}
        msgs = body.get("messages")
        if not isinstance(msgs, list):
            msgs = body.get("input")
        if not rid or not isinstance(msgs, list):
            return
        giu = []
        for m in msgs[-_TOI_DA_SO_TIN:]:
            if not isinstance(m, dict):
                continue
            vai = str(m.get("role") or "")
            if vai in ("system", "developer"):
                continue
            giu.append((vai, _sach(_chu_cua(m.get("content")), _TOI_DA_TIN)))
        now = time.time()
        with _khoa:
            for k in [k for k, (t, _) in _tin_cho.items() if now - t > 600]:
                _tin_cho.pop(k, None)
            _tin_cho[rid] = (now, giu)
            while len(_tin_cho) > 200:
                _tin_cho.pop(next(iter(_tin_cho)))
    except Exception:
        pass


def _ten_tool_goi(tool_calls) -> list[str]:
    ten = []
    for tc in tool_calls or []:
        try:
            if isinstance(tc, dict):
                f = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                n = f.get("name") or tc.get("name")
            else:
                n = getattr(getattr(tc, "function", None), "name", None) or getattr(
                    tc, "name", None)
            if n:
                ten.append(str(n)[:100])
        except Exception:
            pass
    return ten


def _thuoc_tinh_llm(l: _Luot, kw: dict) -> dict:
    model = str(kw.get("response_model") or kw.get("model") or "")
    ncc = _nha_cung_cap(str(kw.get("provider") or ""))
    l.mo_hinh = model or l.mo_hinh
    l.nha_cc = str(kw.get("provider") or "") or l.nha_cc
    a = {_KIND: "LLM", "llm.model_name": model, "llm.provider": ncc, "llm.system": ncc}
    meta = {"api_mode": kw.get("api_mode"), "api_call_count": kw.get("api_call_count"),
            "retry_count": kw.get("retry_count"), "finish_reason": kw.get("finish_reason"),
            "hermes_turn_id": kw.get("turn_id"), "provider_goc": kw.get("provider")}
    a["metadata"] = json.dumps({k: v for k, v in meta.items() if v not in (None, "")},
                               ensure_ascii=False, default=str)
    return a


def _on_post_api(**kw) -> None:
    try:
        l = _luot_cua(kw)
        if l is None:
            return
        _ghi_audit_tid(l)
        with l.khoa:
            l.so_llm += 1
        a = _thuoc_tinh_llm(l, kw)
        u = kw.get("usage") if isinstance(kw.get("usage"), dict) else {}
        try:
            vao = int(u.get("prompt_tokens") or u.get("input_tokens") or 0)
            ra = int(u.get("output_tokens") or 0)
            a["llm.token_count.prompt"] = vao
            a["llm.token_count.completion"] = ra
            a["llm.token_count.total"] = int(u.get("total_tokens") or vao + ra)
            for k_ra, k_vao in (("llm.token_count.prompt_details.cache_read", "cache_read_tokens"),
                                ("llm.token_count.prompt_details.cache_write", "cache_write_tokens"),
                                ("llm.token_count.completion_details.reasoning",
                                 "reasoning_tokens")):
                if u.get(k_vao):
                    a[k_ra] = int(u[k_vao])
        except Exception:
            pass
        mt = kw.get("max_tokens")
        if mt:
            a["llm.invocation_parameters"] = json.dumps({"max_tokens": mt}, default=str)
        resp = kw.get("response") if isinstance(kw.get("response"), dict) else {}
        am = resp.get("assistant_message") if isinstance(resp.get("assistant_message"),
                                                         dict) else {}
        tools = _ten_tool_goi(am.get("tool_calls"))
        for i, n in enumerate(tools):
            a[f"llm.output_messages.0.message.tool_calls.{i}.tool_call.function.name"] = n
        if _co_noi_dung():
            chu = _sach(_chu_cua(am.get("content")), _TOI_DA_RA)
            ra_v = chu + (f"\n[tool_calls: {', '.join(tools)}]" if tools else "")
            if ra_v.strip():
                a["output.value"] = ra_v
            a["llm.output_messages.0.message.role"] = "assistant"
            if chu:
                a["llm.output_messages.0.message.content"] = chu
            rid = str(kw.get("api_request_id") or "")
            with _khoa:
                tin = _tin_cho.pop(rid, None) if rid else None
            if tin:
                for i, (vai, noi) in enumerate(tin[1]):
                    a[f"llm.input_messages.{i}.message.role"] = vai
                    a[f"llm.input_messages.{i}.message.content"] = noi
        _span_lui(l, f"llm {a.get('llm.model_name') or 'model'}", a,
                  kw.get("started_at"), kw.get("ended_at"), loi=None)
    except Exception:
        pass


def _on_api_error(**kw) -> None:
    try:
        l = _luot_cua(kw)
        if l is None:
            return
        _ghi_audit_tid(l)
        with l.khoa:
            l.so_llm += 1
        a = _thuoc_tinh_llm(l, kw)
        err = kw.get("error") if isinstance(kw.get("error"), dict) else {}
        try:
            meta = json.loads(a["metadata"])
        except Exception:
            meta = {}
        meta.update({k: kw.get(k) for k in ("status_code", "retryable", "reason")
                     if kw.get(k) not in (None, "")})
        a["metadata"] = _json(meta, 1000)
        loai = str(err.get("type") or "Loi")[:100]
        mo_ta = loai + (": " + _sach(err.get("message") or "", _TOI_DA_LOI)
                        if _co_noi_dung() else "")
        _span_lui(l, f"llm {a.get('llm.model_name') or 'model'}", a,
                  kw.get("started_at"), kw.get("ended_at"), loi=mo_ta)
    except Exception:
        pass


def _on_post_tool(**kw) -> None:
    try:
        l = _luot_cua(kw)
        if l is None:
            return
        _ghi_audit_tid(l)
        with l.khoa:
            l.so_tool += 1
        ten = str(kw.get("tool_name") or "tool")[:100]
        trang_thai = str(kw.get("status") or "ok")
        a = {_KIND: "TOOL", "tool.name": ten,
             "metadata": json.dumps({k: v for k, v in {
                 "tool_call_id": kw.get("tool_call_id"), "status": trang_thai,
                 "error_type": kw.get("error_type")}.items() if v}, ensure_ascii=False,
                 default=str)}
        if _co_noi_dung():
            args = _json(kw.get("args"), _TOI_DA_ARG)
            a["tool.parameters"] = args
            a["input.value"] = args
            a["input.mime_type"] = "application/json"
            if kw.get("result") is not None:
                a["output.value"] = _json(kw.get("result"), _TOI_DA_RA)
        loi = None
        if trang_thai != "ok":
            loi = f"{trang_thai}: {kw.get('error_type') or ''}"
            if _co_noi_dung() and kw.get("error_message"):
                loi += " " + _sach(kw.get("error_message"), _TOI_DA_LOI)
        cuoi = time.time()
        try:
            dau = cuoi - max(0.0, float(kw.get("duration_ms") or 0)) / 1000.0
        except Exception:
            dau = cuoi
        _span_lui(l, f"tool {ten}", a, dau, cuoi, loi=loi)
    except Exception:
        pass


def _span_lui(l: _Luot, ten: str, thuoc_tinh: dict, bat_dau, ket_thuc,
              loi: str | None) -> None:
    """Dựng một span con ĐÃ XONG dưới span gốc của lượt, theo mốc thời gian có sẵn."""
    from opentelemetry.trace import Status, StatusCode
    now = time.time_ns()
    t1 = _ns(ket_thuc, now)
    t0 = min(_ns(bat_dau, t1), t1)
    span = _tt["tracer"].start_span(ten, context=l.ctx, start_time=t0)
    for k, v in thuoc_tinh.items():
        _set(span, k, v)
    if loi:
        span.set_status(Status(StatusCode.ERROR, loi[:_TOI_DA_LOI + 100]))
    span.end(end_time=t1)
