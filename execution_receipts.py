"""Biên nhận thực thi bền vững, tách theo cuộc hội thoại.

Lịch sử user/assistant không phải bằng chứng một tool đã chạy. Module này
bọc handler tại registry, lưu một bản ghi nhỏ đã che bí mật, rồi cung cấp
khối bằng chứng cho prompt và chốt kiểm tra mâu thuẫn hẹp.

Receipt không thay audit: audit phục vụ quan sát, receipt phục vụ trả lời
follow-up mà không chạy lại tool tốn tiền.
"""

from __future__ import annotations

import contextvars
import datetime
import hashlib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from config import config

_DIR = config.token_file.parent / "execution-receipts"
_MAX_PER_CHAT = 30
_MAX_AGE_DAYS = 30
_lock = threading.RLock()
_context: contextvars.ContextVar[tuple[str, str]] = contextvars.ContextVar(
    "execution_receipt_context", default=("", "")
)

_SECRET_KEY = re.compile(
    r"(?i)(?:token|secret|password|passwd|authorization|api[_-]?key|cookie|credential)"
)
_URL = re.compile(r"https?://[^\s\]\[<>()\"']+", re.I)
_DENIAL = re.compile(
    r"(?is)\b(?:tôi|mình)\b[^.\n]{0,140}?(?:"
    r"không\s+thực\s+sự\s+(?:đã\s+)?chạy(?:\s+công\s+cụ)?"
    r"|chưa\s+từng\s+chạy(?:\s+công\s+cụ)?"
    r"|không\s+hề\s+chạy(?:\s+công\s+cụ)?"
    r"|không\s+có\s+lần\s+chạy\s+nào)"
)
_STATUS_FOLLOWUP = re.compile(
    r"(?i)pending|required|đã\s+chạy|chạy\s+chưa|thực\s+hiện|làm\s+chưa"
    r"|sao\s+(?:bạn|mày)|trước\s+của\s+(?:tôi|mình)"
)
# Tool chỉ nạp hướng dẫn/tra trạng thái không đủ để bác bỏ phát biểu
# "chưa chạy việc". Danh sách này cố ý hẹp: guard lỡ bỏ còn an toàn hơn sửa sai.
_SUBSTANTIVE_TOOLS = {
    "tiktok_top_ads", "social_listen", "social_deep_dive", "fb_ads_library",
    "soi_tai_khoan", "soi_san", "web_crawl", "web_scrape", "doc_bang",
    "dem_bang", "chi_so_bai", "binh_luan_kenh_nha", "ghi_viec_base", "doc_tai_lieu",
}
_TOOL_TERMS = {
    "tiktok_top_ads": {"tiktok", "top ads", "creative center"},
    "social_listen": {"social listen", "quét mạng xã hội", "facebook", "instagram",
                      "youtube", "threads", "tiktok"},
    "social_deep_dive": {"deep dive", "bình luận", "comment"},
    "fb_ads_library": {"facebook", "meta", "ad library"},
    "doc_bang": {"base", "sheet", "bảng"},
    "dem_bang": {"base", "sheet", "bảng", "đếm"},
    "doc_tai_lieu": {"tài liệu", "doc", "wiki"},
    "web_crawl": {"website", "web", "crawl", "cào"},
    "web_scrape": {"website", "web", "scrape", "đọc trang"},
    "soi_tai_khoan": {"tài khoản", "brand", "koc", "kol"},
    "soi_san": {"shopee", "sàn", "sản phẩm"},
    "chi_so_bai": {"chỉ số bài", "lượt xem", "view", "like", "share"},
    "binh_luan_kenh_nha": {"kênh nhà", "bình luận", "comment"},
    "ghi_viec_base": {"ghi việc", "base", "checklist"},
}


def set_current_turn(chat_id: str, turn_id: str) -> None:
    """Gắn chat/turn cho tool executor; ContextVar được Hermes truyền sang worker."""
    _context.set((chat_id or "", turn_id or ""))


def clear_current_turn() -> None:
    _context.set(("", ""))


def record_current(tool: str, args: Any, result: Any, *, error: str = "") -> dict | None:
    """Ghi receipt cho chặn ở dispatch, nơi handler wrapper chưa được gọi.

    API công khai này giữ ContextVar bên trong module; caller không cần và không được
    đọc chat/turn ID trực tiếp. Thiếu context thì `record` fail-closed bằng None.
    """
    chat_id, turn_id = _context.get()
    return record(chat_id, turn_id, tool, args, result, error=error)


def _path(chat_id: str) -> Path:
    # Không đưa chat ID/email thô vào tên file.
    digest = hashlib.sha256((chat_id or "").encode("utf-8")).hexdigest()[:32]
    return _DIR / f"{digest}.json"


def _cut(value: Any, limit: int = 300) -> str:
    text = str(value or "")
    text = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~-]+", "Bearer [đã_che]", text)
    text = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_.-]{20,})\b",
                  "[đã_che]", text)
    text = re.sub(
        r"(?i)(\b(?:access[_-]?token|token|secret|password|passwd|api[_-]?key|"
        r"authorization|credential|signature)\b\s*[:=]\s*)(?:Bearer\s+)?[^\s,;}\]]+",
        r"\1[đã_che]", text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _safe_url(value: Any) -> str:
    """Giữ URL đầu ra công khai, che signed query/credential nếu có."""
    raw = _cut(value, 1000)
    try:
        parts = urlsplit(raw)
        if parts.scheme not in ("http", "https"):
            return _cut(raw, 500)
        safe_query = []
        for key, val in parse_qsl(parts.query, keep_blank_values=True):
            sensitive = bool(re.search(
                r"(?i)(?:token|secret|password|passwd|api[_-]?key|authorization|"
                r"credential|signature|(?:^|[-_])sig(?:$|[-_])|policy)", key))
            safe_query.append((key, "[đã_che]" if sensitive else _cut(val, 200)))
        fragment = _cut(parts.fragment, 200)
        if re.search(r"(?i)(token|secret|signature|credential|authorization)", fragment):
            fragment = "[đã_che]"
        return _cut(urlunsplit((parts.scheme, parts.netloc, parts.path,
                                urlencode(safe_query), fragment)), 500)
    except Exception:
        return _cut(raw, 500)


def _sanitize(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "[đã_lược_bớt]"
    if isinstance(value, dict):
        out = {}
        for key, item in list(value.items())[:40]:
            name = _cut(key, 80)
            out[name] = "[đã_che]" if _SECRET_KEY.search(name) else _sanitize(item, depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [_sanitize(item, depth + 1) for item in list(value)[:30]]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return _cut(value)


def _as_object(result: Any) -> Any:
    if isinstance(result, (dict, list)):
        return result
    if isinstance(result, str):
        try:
            return json.loads(result)
        except (TypeError, ValueError):
            return result
    return result


def _classify(result: Any, error: str = "") -> dict:
    """Dùng chung phân loại audit khi có; fallback phải fail-closed."""
    try:
        import audit
        fn = getattr(audit, "phan_loai_ket_qua_tool", None)
        if callable(fn):
            data = fn(result, error)
            if isinstance(data, dict) and data.get("trang_thai"):
                return data
    except Exception:
        pass
    obj = _as_object(result)
    if error:
        return {"trang_thai": "failed", "co_ket_qua": False, "loi": _cut(error, 200)}
    if isinstance(obj, dict):
        code = str(obj.get("error") or obj.get("error_code") or "")
        success = obj.get("success")
        if code or success is False:
            blocked = bool(re.search(r"(?i)permission|policy|forbidden|identity|budget|limit", code))
            return {"trang_thai": "blocked" if blocked else "failed",
                    "co_ket_qua": False, "loi": _cut(code, 200)}
        requested = obj.get("requested_count", obj.get("so_ads_xin"))
        actual = obj.get("actual_count")
        if actual is None:
            for key in ("so_ads", "total_results", "count", "total"):
                if isinstance(obj.get(key), (int, float)):
                    actual = obj[key]
                    break
        if actual is None and isinstance(obj.get("items"), list):
            actual = len(obj["items"])
        partial = (isinstance(requested, (int, float)) and isinstance(actual, (int, float))
                   and actual < requested)
        return {"trang_thai": "partial" if partial else "completed",
                "co_ket_qua": bool(result), "so_ket_qua": actual}
    return {"trang_thai": "completed" if result else "failed", "co_ket_qua": bool(result)}


def _facts(result: Any, classified: dict) -> dict:
    obj = _as_object(result)
    facts: dict[str, Any] = {
        "status": classified.get("trang_thai") or "failed",
        "has_result": bool(classified.get("co_ket_qua")),
    }
    if classified.get("so_ket_qua") is not None:
        facts["actual_count"] = classified["so_ket_qua"]
    if classified.get("ma_loi"):
        facts["error_code"] = _cut(classified["ma_loi"], 100)
    if classified.get("loi"):
        facts["error"] = _cut(classified["loi"], 200)
    if isinstance(obj, dict):
        if (obj.get("da_chay") is False or obj.get("chi_uoc_tinh") is True
                or obj.get("execution_state") == "estimated"):
            facts["executed"] = False
            facts["execution_state"] = "estimated"
        else:
            facts["executed"] = True
        aliases = {
            "so_ads_xin": "requested_count", "requested_count": "requested_count",
            "actual_count": "actual_count", "so_ads": "actual_count",
            "total_results": "actual_count", "count": "actual_count",
            "pham_vi": "scope", "nguon": "source", "source": "source",
            "chi_phi_thuc_usd": "actual_cost_usd", "actual_cost_usd": "actual_cost_usd",
            "sheet_url": "output_url", "output_url": "output_url", "url": "output_url",
            "source_url": "source_url",
        }
        for source, target in aliases.items():
            if source in obj and obj[source] not in (None, ""):
                facts[target] = (_safe_url(obj[source]) if target.endswith("_url")
                                 else _sanitize(obj[source]))
        summary = obj.get("tom_tat")
        if (facts.get("actual_count") is None and isinstance(summary, dict)
                and isinstance(summary.get("so_ads"), (int, float))):
            facts["actual_count"] = summary["so_ads"]
        # Không quét mọi URL trong raw items: creative/signed media có thể mang
        # credential và không cần cho follow-up. Chỉ giữ URL đầu ra/nguồn đã biết.
        links = [facts[key] for key in ("output_url", "source_url") if facts.get(key)]
        if links:
            facts["links"] = links[:5]
    return facts


def load(chat_id: str, limit: int = 10) -> list[dict]:
    if not chat_id:
        return []
    try:
        data = json.loads(_path(chat_id).read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else []
        return [row for row in rows if isinstance(row, dict)][-max(0, limit):]
    except Exception:
        return []


def record(chat_id: str, turn_id: str, tool: str, args: Any, result: Any,
           *, elapsed_seconds: float = 0.0, error: str = "") -> dict | None:
    if not chat_id or not tool:
        return None
    classified = _classify(result, error)
    facts = _facts(result, classified)
    # Preflight/ước tính không phải biên nhận THỰC THI. Không lưu nó vì
    # nó sẽ thành receipt mới nhất và che khuất lần chạy thật ngay trước đó.
    if facts.get("executed") is False:
        return None
    status = classified.get("trang_thai") or "failed"
    if (status == "completed" and isinstance(facts.get("requested_count"), (int, float))
            and isinstance(facts.get("actual_count"), (int, float))
            and facts["actual_count"] < facts["requested_count"]):
        status = "partial"
        facts["status"] = "partial"
    row = {
        "version": 1,
        "receipt_id": f"{turn_id or 'outside'}:{int(time.time() * 1000)}",
        "turn_id": turn_id or "",
        "executed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "tool": _cut(tool, 100),
        "status": status,
        "elapsed_seconds": round(float(elapsed_seconds or 0.0), 3),
        "args": _sanitize(args if isinstance(args, dict) else {}),
        "facts": facts,
    }
    with _lock:
        rows = load(chat_id, _MAX_PER_CHAT)
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=_MAX_AGE_DAYS)
        kept = []
        for old in rows:
            try:
                if datetime.datetime.fromisoformat(old["executed_at"]) >= cutoff:
                    kept.append(old)
            except Exception:
                continue
        kept = (kept + [row])[-_MAX_PER_CHAT:]
        _DIR.mkdir(parents=True, exist_ok=True)
        path = _path(chat_id)
        tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(kept, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(path)
    return row


def prompt_block(chat_id: str, limit: int = 5) -> str:
    rows = load(chat_id, limit)
    if not rows:
        return ""
    lines = ["\n---\n## BIÊN NHẬN THỰC THI (bằng chứng hệ thống, ưu tiên hơn lời kể trong lịch sử)"]
    for row in rows:
        facts = row.get("facts") if isinstance(row.get("facts"), dict) else {}
        bits = [f"tool={row.get('tool')}", f"trạng_thái={row.get('status')}",
                f"turn_id={row.get('turn_id')}", f"lúc={row.get('executed_at')}"]
        for key in ("requested_count", "actual_count", "scope", "source",
                    "actual_cost_usd", "output_url", "error_code", "execution_state"):
            if facts.get(key) not in (None, ""):
                bits.append(f"{key}={_cut(facts[key], 180)}")
        lines.append("- " + "; ".join(bits))
    lines += [
        "- Khi người dùng hỏi đã chạy hay chưa, đối chiếu biên nhận. Không phủ nhận "
        "lần completed/partial chỉ vì lời trả lời cũ mâu thuẫn. Không tự chạy lại tool để kiểm tra.",
    ]
    return "\n".join(lines)


def _denial_is_quoted(text: str, start: int, end: int) -> bool:
    """Chỉ coi denial là trích dẫn khi CHÍNH mệnh đề nằm trong cặp nháy.

    Nháy quanh một cụm khác gần đó (ca thật có “ok chạy” và
    “5 quảng cáo”) không được che lời phủ nhận nằm ở giữa.
    """
    for opening, closing in (("“", "”"), ("‘", "’")):
        opened = text.rfind(opening, 0, start)
        closed = text.rfind(closing, 0, start)
        if opened > closed and text.find(closing, end) >= 0:
            return True
    for quote in ('"', "'"):
        if text[:start].count(quote) % 2 == 1 and text.find(quote, end) >= 0:
            return True
    return False


def ground_final_answer(chat_id: str, user_text: str, answer: str) -> tuple[str, bool]:
    """Sửa duy nhất phủ nhận tuyệt đối trái receipt, không duyệt nội dung chung."""
    denial = _DENIAL.search(answer or "")
    if not denial or not _STATUS_FOLLOWUP.search(user_text or ""):
        return answer, False
    # Đừng biến câu trích dẫn/bác bỏ thành lời tự nhận, hoặc dùng receipt cũ
    # để tuyên bố một yêu cầu mới đã chạy.
    answer_text = answer or ""
    around = answer_text[max(0, denial.start() - 30):denial.end() + 50]
    if _denial_is_quoted(answer_text, denial.start(), denial.end()):
        return answer, False
    if re.search(r"(?i)(?:là|hoàn\s+toàn)\s+sai|không\s+đúng", around[denial.end() - max(0, denial.start() - 30):]):
        return answer, False
    if re.search(r"(?i)(?:cho|với)\s+(?:yêu\s+cầu|việc|lần)\s+này", denial.group(0) + around):
        return answer, False
    # Bỏ qua tool phụ (nạp skill, ghi nhớ, tra chi phí). Ca production có
    # tiktok_top_ads thành công, sau đó dung_ky_nang, rồi mới bị phủ nhận;
    # tool phụ không được che receipt nghiệp vụ. Ngược lại failed/blocked
    # của chính tool nghiệp vụ vẫn là receipt mới nhất và phải chặn success cũ.
    rows = [row for row in load(chat_id, 10)
            if row.get("tool") in _SUBSTANTIVE_TOOLS]
    if not rows:
        return answer, False
    # Receipt mới nhất là blocked/failed thì không được lấy một success cũ
    # ra che nó. Chỉ chốt câu trong cửa sổ follow-up ngắn của cùng chat.
    receipt = rows[-1]
    if receipt.get("status") not in ("completed", "partial"):
        return answer, False
    facts = receipt.get("facts") if isinstance(receipt.get("facts"), dict) else {}
    if facts.get("executed") is False:
        return answer, False
    combined = f"{user_text} {answer}".casefold()
    mentioned = {tool for tool, terms in _TOOL_TERMS.items()
                 if any(term in combined for term in terms)}
    if mentioned and receipt.get("tool") not in mentioned:
        return answer, False
    if not mentioned:
        # Câu chung chung "sao pending" chỉ gắn với receipt gần nhất khi chính
        # câu trả lời nhắc một mốc trong receipt. Ca thật nhắc "con số 5";
        # không có anchor thì chọn bỏ sót thay vì sửa nhầm việc khác.
        anchors = [facts.get("actual_count"), facts.get("actual_cost_usd"),
                   facts.get("output_url"), receipt.get("turn_id")]
        if not any(str(anchor) in combined for anchor in anchors if anchor not in (None, "")):
            return answer, False
    try:
        executed = datetime.datetime.fromisoformat(receipt["executed_at"])
        if datetime.datetime.now(datetime.timezone.utc) - executed > datetime.timedelta(hours=2):
            return answer, False
    except Exception:
        return answer, False
    details = [f"công cụ {receipt.get('tool')}", f"trạng thái {receipt.get('status')}"]
    if facts.get("actual_count") is not None:
        if facts.get("requested_count") is not None:
            details.append(f"kết quả {facts['actual_count']}/{facts['requested_count']}")
        else:
            details.append(f"kết quả {facts['actual_count']}")
    if facts.get("actual_cost_usd") is not None:
        details.append(f"chi phí thực {facts['actual_cost_usd']} USD")
    if facts.get("output_url"):
        details.append(f"đầu ra {facts['output_url']}")
    correction = ("Tôi kiểm tra lại biên nhận thực thi: đã có một lần chạy được ghi nhận "
                  + ", ".join(details) + f" (turn {receipt.get('turn_id')}). "
                  "Vì vậy tôi không thể kết luận là công cụ chưa từng chạy. "
                  "Phần nguyên nhân hoặc mức độ đủ của kết quả cần đánh giá riêng.")
    try:
        import audit
        audit.ghi_chat_luong("corrected", "execution_receipt_contradiction",
                             evidence_turn_id=str(receipt.get("turn_id") or ""))
    except Exception:
        pass
    print(f"[execution_receipts] grounded_correction turn={receipt.get('turn_id')} "
          f"tool={receipt.get('tool')}", flush=True)
    return correction, True


_installed = False


def install_registry_capture() -> int:
    """Bọc registry sau audit; receipt hỏng tuyệt đối không làm hỏng tool."""
    global _installed
    if _installed:
        return 0
    try:
        from tools.registry import registry  # type: ignore
    except Exception:
        return 0

    def wrap(name: str, original, is_async: bool):
        if is_async:
            async def captured(args, **kwargs):
                started = time.monotonic()
                try:
                    result = await original(args, **kwargs)
                except Exception as exc:
                    chat, turn = _context.get()
                    try:
                        record(chat, turn, name, args, None,
                               elapsed_seconds=time.monotonic() - started,
                               error=f"{type(exc).__name__}: {exc}")
                    except Exception:
                        pass
                    raise
                chat, turn = _context.get()
                try:
                    record(chat, turn, name, args, result,
                           elapsed_seconds=time.monotonic() - started)
                except Exception:
                    pass
                return result
        else:
            def captured(args, **kwargs):
                started = time.monotonic()
                try:
                    result = original(args, **kwargs)
                except Exception as exc:
                    chat, turn = _context.get()
                    try:
                        record(chat, turn, name, args, None,
                               elapsed_seconds=time.monotonic() - started,
                               error=f"{type(exc).__name__}: {exc}")
                    except Exception:
                        pass
                    raise
                chat, turn = _context.get()
                try:
                    record(chat, turn, name, args, result,
                           elapsed_seconds=time.monotonic() - started)
                except Exception:
                    pass
                return result
        captured.__name__ = getattr(original, "__name__", name)
        captured.__doc__ = getattr(original, "__doc__", None)
        captured._execution_receipt = True
        return captured

    count = 0
    try:
        for name, entry in list(getattr(registry, "_tools", {}).items()):
            handler = getattr(entry, "handler", None)
            if handler is None or getattr(handler, "_execution_receipt", False):
                continue
            entry.handler = wrap(name, handler, bool(getattr(entry, "is_async", False)))
            count += 1
    except Exception:
        return count
    _installed = True
    return count
