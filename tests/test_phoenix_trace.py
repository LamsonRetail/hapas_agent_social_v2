"""Canh trace Phoenix (phoenix_trace.py).

Ba điều không được hỏng:
  • TẮT là tắt thật — không env thì không import OpenTelemetry, không gắn hook Hermes,
    `brain.reply` chạy y như chưa bọc (kể cả ném lỗi nguyên vẹn).
  • Không một bí mật / email / SĐT / open_id / chat_id thô nào ra khỏi máy trong span.
  • Phoenix chết thì Mark vẫn trả lời, không chậm thêm, tắt máy không treo.

Span đọc bằng InMemorySpanExporter qua `phoenix_trace._dung_provider(exporter)`.
"""
from __future__ import annotations

import contextvars
import json
import os
import socket
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import phoenix_trace as PT

_GOC = Path(__file__).resolve().parent.parent

# Bí mật GIẢ — không bao giờ được thấy trong span xuất ra.
_APIFY = "apify_api_GIAgiaGIAgia1234567890"
_LARK_SECRET = "LarkSecretGia9f8e7d6c5b4a"
_SK = "sk-giaGIAgia1234567890abcd"
_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJnaWEifQ.chuKyGia123"
_BEARER = "BearerGiaTokenXYZ987654"
_EMAIL = "nguoi.dung@hapas.vn"
_SDT = "0912 345 678"
_OU = "ou_abcdef1234567890gia"
_CHAT = "lark:cli_app:oc_chatthat123456"
_TAT_CA_BI_MAT = [_APIFY, _LARK_SECRET, _SK, _JWT, _BEARER, _EMAIL, _SDT, "0912345678",
                  _OU, _CHAT, "oc_chatthat123456"]
_CAU_BAN = (f"token Apify {_APIFY}, secret {_LARK_SECRET}, khoá {_SK}, jwt {_JWT}, "
            f"Authorization: Bearer {_BEARER}, mail {_EMAIL}, gọi {_SDT}, người {_OU}")


def _otel():
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    return InMemorySpanExporter


def _don_trang_thai():
    with PT._khoa:
        cu = PT._tt.get("provider")
        PT._tt.update(tracer=None, provider=None, hook=False, dau_cuoi="",
                      mgr_da_gan=None, hook_da_gan=set())
        PT._theo_phien.clear()
        PT._tin_cho.clear()
    if cu is not None:
        try:
            cu.shutdown()
        except Exception:
            pass


@pytest.fixture
def bat_trace(monkeypatch):
    """Bật trace với exporter trong bộ nhớ. Trả exporter để đọc span."""
    InMem = _otel()
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:9")
    monkeypatch.setenv("MARK_PHOENIX_SALT", "muoi-thu-nghiem-0123456789")
    monkeypatch.setenv("APIFY_TOKEN", _APIFY)
    monkeypatch.setenv("LARK_APP_SECRET", _LARK_SECRET)
    ex = InMem()
    PT._dung_provider(ex)
    # bat() (vd lúc `import brain` trong bài) thấy cùng đầu cuối thì không dựng lại provider.
    PT._tt["dau_cuoi"] = "http://127.0.0.1:9"
    yield ex
    _don_trang_thai()


@pytest.fixture(autouse=True)
def _luon_don():
    yield
    _don_trang_thai()


def _kw_llm(**them):
    now = time.time()
    kw = dict(
        session_id="s1", turn_id="ht1", api_request_id="r1", model="gpt-5.6-terra",
        response_model="gpt-5.6-terra", provider="openai-codex", api_mode="codex_responses",
        api_call_count=1, retry_count=0, finish_reason="tool_calls",
        started_at=now - 1.5, ended_at=now - 0.5, api_duration=1.0,
        usage={"input_tokens": 100, "output_tokens": 20, "cache_read_tokens": 30,
               "cache_write_tokens": 0, "reasoning_tokens": 5, "prompt_tokens": 130,
               "total_tokens": 150},
        response={"model": "gpt-5.6-terra", "finish_reason": "tool_calls",
                  "assistant_message": {"role": "assistant", "content": "để em quét",
                                        "tool_calls": [{"id": "c1", "type": "function",
                                                        "function": {"name": "social_listen",
                                                                     "arguments": "{}"}}]}},
        telemetry_schema_version=1,
    )
    kw.update(them)
    return kw


def _kw_tool(**them):
    kw = dict(tool_name="social_listen", args={"tu_khoa": "HAPAS"}, result='{"ok": true}',
              session_id="s1", tool_call_id="c1", turn_id="ht1", duration_ms=250,
              status="ok", error_type=None, error_message=None)
    kw.update(them)
    return kw


def _theo_ten(spans):
    return {s.name: s for s in spans}


def _moi_chuoi(spans) -> str:
    """Gom MỌI chuỗi sẽ rời máy: thuộc tính, sự kiện, mô tả trạng thái, resource."""
    phan = []
    for s in spans:
        phan.append(s.name)
        for v in (s.attributes or {}).values():
            phan.append(json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v)
        for ev in s.events:
            for v in (ev.attributes or {}).values():
                phan.append(str(v))
        phan.append(s.status.description or "")
        for v in s.resource.attributes.values():
            phan.append(str(v))
    return "\n".join(phan)


# ─────────────────────────────── tắt là tắt ───────────────────────────────

def test_tat_mac_dinh_khong_import_opentelemetry():
    """Không env: import + bat() không kéo OpenTelemetry vào tiến trình (chạy riêng
    tiến trình con để chắc không bài nào khác đã import trước)."""
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("PHOENIX_", "MARK_PHOENIX_"))}
    env["PYTHONIOENCODING"] = "utf-8"
    ma = ("import sys, phoenix_trace as P; print(P.bat()); "
          "print('otel' if any(m.startswith('opentelemetry') for m in sys.modules) else 'sach')")
    ra = subprocess.run([sys.executable, "-c", ma], cwd=str(_GOC), env=env,
                        capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert ra.returncode == 0, ra.stderr
    dong = ra.stdout.strip().splitlines()
    assert dong[0].startswith("Phoenix:    TẮT"), dong
    assert dong[-1] == "sach", "tắt mà vẫn import opentelemetry"


def test_tat_thi_luot_goi_thang_va_nem_nguyen_ven(monkeypatch):
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    assert PT._tt["tracer"] is None
    goi = []

    def f(user_text, *, chat_id, sender_open_id=None, kenh=None):
        goi.append((user_text, chat_id, sender_open_id, kenh))
        return "đáp"

    assert PT.luot(f)("hỏi", chat_id="c", sender_open_id="ou_x") == "đáp"
    assert goi == [("hỏi", "c", "ou_x", None)]
    assert PT.luot(f).__wrapped__ is f

    loi = KeyError("gốc")

    def hong(*a, **k):
        raise loi

    with pytest.raises(KeyError) as e:
        PT.luot(hong)("x", chat_id="c")
    assert e.value is loi


def test_thieu_muoi_thi_tat(monkeypatch):
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006")
    monkeypatch.delenv("MARK_PHOENIX_SALT", raising=False)
    assert "TẮT" in PT.bat() and "MARK_PHOENIX_SALT" in PT.bat()
    assert PT._tt["tracer"] is None


def test_tat_thi_khong_gan_hook_hermes(monkeypatch):
    """Không env thì Hermes `has_hook` không vì Mark mà thành True."""
    plugins = _hermes_plugins()
    monkeypatch.delenv("PHOENIX_COLLECTOR_ENDPOINT", raising=False)
    PT.bat()
    hooks = plugins.get_plugin_manager()._hooks
    for ten in ("post_api_request", "api_request_error", "post_tool_call", "pre_api_request"):
        assert not any(getattr(cb, "__module__", "") == "phoenix_trace"
                       for cb in hooks.get(ten, [])), ten


def test_hook_khong_co_luot_thi_bo_qua(bat_trace):
    """Hermes gọi model ngoài lượt (việc nền, phụ trợ) → không đẻ trace mồ côi."""
    PT._on_post_api(**_kw_llm(session_id="la"))
    PT._on_post_tool(**_kw_tool(session_id="la"))
    assert bat_trace.get_finished_spans() == ()


# ─────────────────────────────── cây span ───────────────────────────────

def test_cay_span_llm_va_tool_o_luong_khac(bat_trace):
    kw_llm = _kw_llm()

    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_post_api(**kw_llm)
        with ThreadPoolExecutor(2) as ex:   # Hermes: tool song song qua copy_context
            ex.submit(contextvars.copy_context().run, PT._on_post_tool,
                      **_kw_tool(session_id="")).result()
        return "xong"

    assert reply("quét HAPAS", chat_id="oc_1", sender_open_id="ou_nguoihoi12345",
                 kenh={"chat_type": "group"}) == "xong"
    spans = bat_trace.get_finished_spans()
    assert len(spans) == 3
    s = _theo_ten(spans)
    goc, llm, tool = s["mark.turn"], s["llm gpt-5.6-terra"], s["tool social_listen"]
    assert {x.context.trace_id for x in spans} == {goc.context.trace_id}
    assert goc.parent is None
    assert llm.parent.span_id == goc.context.span_id
    assert tool.parent.span_id == goc.context.span_id
    assert goc.attributes["openinference.span.kind"] == "CHAIN"
    assert llm.attributes["openinference.span.kind"] == "LLM"
    assert tool.attributes["openinference.span.kind"] == "TOOL"
    assert tool.attributes["tool.name"] == "social_listen"
    a = llm.attributes
    assert a["llm.model_name"] == "gpt-5.6-terra" and a["llm.provider"] == "openai"
    assert (a["llm.token_count.prompt"], a["llm.token_count.completion"],
            a["llm.token_count.total"]) == (130, 20, 150)
    assert a["llm.token_count.prompt_details.cache_read"] == 30
    assert a["llm.token_count.completion_details.reasoning"] == 5
    assert a["llm.output_messages.0.message.tool_calls.0.tool_call.function.name"] \
        == "social_listen"
    assert llm.start_time == int(kw_llm["started_at"] * 1e9)
    assert llm.end_time == int(kw_llm["ended_at"] * 1e9)
    assert 240e6 <= tool.end_time - tool.start_time <= 260e6
    assert list(goc.attributes["tag.tags"]) == ["lark", "group"]
    meta = json.loads(goc.attributes["metadata"])
    assert meta["model"] == "gpt-5.6-terra" and meta["provider"] == "openai-codex"
    assert meta["so_lan_goi_model"] == 1 and meta["so_tool"] == 1
    assert goc.attributes["output.value"] == "xong"
    assert "llm.input_messages.0.message.content" not in a, "mặc định không gửi lịch sử"


def test_tool_o_luong_tran_tim_luot_theo_session(bat_trace):
    """Luồng không mang ngữ cảnh (threading.Thread trần) vẫn về đúng lượt qua session_id."""
    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_post_api(**_kw_llm(session_id="phien-A"))
        t = threading.Thread(target=PT._on_post_tool, kwargs=_kw_tool(session_id="phien-A"))
        t.start()
        t.join()
        t = threading.Thread(target=PT._on_post_tool, kwargs=_kw_tool(session_id="la"))
        t.start()
        t.join()
        return "ok"

    reply("x", chat_id="oc_2")
    spans = bat_trace.get_finished_spans()
    s = _theo_ten(spans)
    assert len(spans) == 3, "tool ở phiên lạ phải bị bỏ, không thành trace mồ côi"
    assert s["tool social_listen"].parent.span_id == s["mark.turn"].context.span_id
    assert PT._theo_phien == {}, "đóng lượt phải gỡ sổ theo phiên"


def test_luot_song_song_khong_lan_nhau(bat_trace):
    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_post_api(**_kw_llm(session_id=chat_id))
        time.sleep(0.05)
        PT._on_post_tool(**_kw_tool(session_id=chat_id, tool_name=f"t_{chat_id}"))
        return chat_id

    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda c: reply("x", chat_id=c), ["a", "b", "c", "d"]))
    spans = bat_trace.get_finished_spans()
    goc = {s.context.trace_id: s for s in spans if s.name == "mark.turn"}
    assert len(goc) == 4
    for s in spans:
        if s.name.startswith("tool t_"):
            g = goc[s.context.trace_id]
            assert s.parent.span_id == g.context.span_id
            assert g.attributes["output.value"] == s.name.split("t_")[1]


def test_luot_ghi_audit_turn_id(bat_trace):
    import audit
    if not audit._BAT:
        pytest.skip("AUDIT_ENABLED=0")
    giu = {}

    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        tid = audit.bat_dau(chat_id, sender_open_id, user_text)
        giu["tid"] = tid
        PT._on_post_api(**_kw_llm())
        audit.ket_thuc(tid, "đáp", None)
        return "đáp"

    reply("hỏi", chat_id="oc_audit")
    goc = _theo_ten(bat_trace.get_finished_spans())["mark.turn"]
    assert json.loads(goc.attributes["metadata"])["audit_turn_id"] == giu["tid"]
    # Chỉ đọc: run.py vẫn lấy được bản ghi để gửi platform.
    assert audit.lay_luot_vua_xong("oc_audit").get("turn_id") == giu["tid"]


# ─────────────────────────────── che ───────────────────────────────

def test_khong_bi_mat_nao_lot_ra(bat_trace):
    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_post_api(**_kw_llm(response={"assistant_message": {
            "role": "assistant", "content": "tiếp " + _CAU_BAN, "tool_calls": []}}))
        PT._on_api_error(**_kw_llm(error={"type": "APIError", "message": _CAU_BAN},
                                   status_code=401, reason=_CAU_BAN))
        PT._on_post_tool(**_kw_tool(args={"q": _CAU_BAN, "url": f"https://x?token={_APIFY}"},
                                    result=_CAU_BAN))
        PT._on_post_tool(**_kw_tool(status="error", error_type="LoiApify",
                                    error_message=_CAU_BAN, result=None))
        return "trả lời: " + _CAU_BAN

    reply(_CAU_BAN, chat_id=_CHAT, sender_open_id=_OU)
    spans = bat_trace.get_finished_spans()
    assert len(spans) == 5
    tat_ca = _moi_chuoi(spans)
    for bm in _TAT_CA_BI_MAT:
        assert bm not in tat_ca, f"lọt: {bm[:12]}…"
    assert "[đã_che_email]" in tat_ca and "[đã_che_sđt]" in tat_ca
    goc = _theo_ten(spans)["mark.turn"]
    assert goc.attributes["session.id"].startswith("c_")
    assert goc.attributes["user.id"].startswith("u_")


_OC = "oc_0123456789abcdef0123456789abcdef"
_OM = "om_fedcba9876543210fedcba9876543210"
_KHAC = ["on_unionid1234567890ab", "og_group1234567890", "od_phongban123456",
         "cli_a1b2c3d4e5f60718"]


def test_moi_loai_id_lark_deu_bi_che(bat_trace):
    """`_redact` chỉ che ou_. Kết quả/lỗi của lark_cli đầy oc_ (chat), om_ (tin nhắn),
    on_/og_/od_, cli_ (app) — không cái nào được ra khỏi máy, ở BẤT KỲ chuỗi nào."""
    ket_qua = json.dumps({"chat_id": _OC, "message_id": _OM, "khac": _KHAC,
                          "url": f"https://x.larksuite.com/messenger/{_OC}"})
    loi = f"HTTP 400 khi gửi {_OM} vào {_OC} bằng app {_KHAC[-1]}"

    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_post_api(**_kw_llm(response={"assistant_message": {
            "role": "assistant", "content": f"đã gửi {_OM}", "tool_calls": []}}))
        PT._on_post_tool(**_kw_tool(tool_name="lark_cli", args={"chat": _OC},
                                    result=ket_qua))
        PT._on_post_tool(**_kw_tool(tool_name="lark_cli", status="error",
                                    error_type="LoiLark", error_message=loi, result=loi))
        PT._on_api_error(**_kw_llm(error={"type": "APIError", "message": loi}, reason=loi))
        raise RuntimeError(loi)

    with pytest.raises(RuntimeError):
        reply(f"nhắn vào {_OC} trả lời {_OM}", chat_id=f"lark:{_KHAC[-1]}:{_OC}")
    tat_ca = _moi_chuoi(bat_trace.get_finished_spans())
    for bm in [_OC, _OM, *_KHAC, _OC[3:], _OM[3:]]:
        assert bm not in tat_ca, f"lọt: {bm[:10]}…"
    assert "[đã_che_id_lark]" in tat_ca


def test_provider_khong_tu_gan_atexit(bat_trace):
    """shutdown_on_exit=False: provider không tự gắn atexit; Mark tắt qua `_tat`."""
    p = PT._tt["provider"]
    assert getattr(p, "_atexit_handler", None) is None
    PT._tat()
    assert PT._tt["tracer"] is None
    PT._tat()   # gọi lại không ném


def test_bi_danh_on_dinh_va_theo_muoi(monkeypatch, bat_trace):
    a = PT._bi_danh(_CHAT, "c")
    assert a == PT._bi_danh(_CHAT, "c") and a != PT._bi_danh(_CHAT + "x", "c")
    monkeypatch.setenv("MARK_PHOENIX_SALT", "muoi-khac-hoan-toan-000000")
    assert PT._bi_danh(_CHAT, "c") != a


def test_khong_xuat_system_prompt_ke_ca_khi_bat_tin_vao(monkeypatch, bat_trace):
    monkeypatch.setenv("MARK_PHOENIX_LLM_INPUT", "1")
    he_thong = "PERSONA BÍ MẬT: đội ngũ Lê Quý Thiện, ngữ cảnh platform"

    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_pre_api(api_request_id="r1", session_id="s1", request={"body": {
            "instructions": he_thong,
            "messages": [{"role": "system", "content": he_thong},
                         {"role": "developer", "content": he_thong},
                         {"role": "user", "content": [{"type": "text",
                                                       "text": "hỏi " + _EMAIL}]}]}})
        PT._on_post_api(**_kw_llm())
        return "ok"

    reply("hỏi", chat_id="oc_3")
    llm = _theo_ten(bat_trace.get_finished_spans())["llm gpt-5.6-terra"]
    assert llm.attributes["llm.input_messages.0.message.role"] == "user"
    assert "[đã_che_email]" in llm.attributes["llm.input_messages.0.message.content"]
    assert "llm.input_messages.1.message.role" not in llm.attributes
    assert "PERSONA" not in _moi_chuoi(bat_trace.get_finished_spans())


def test_tin_vao_mac_dinh_tat(bat_trace):
    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_pre_api(api_request_id="r1", session_id="s1", request={"body": {
            "messages": [{"role": "user", "content": "lịch sử"}]}})
        PT._on_post_api(**_kw_llm())
        return "ok"

    reply("hỏi", chat_id="oc_4")
    for s in bat_trace.get_finished_spans():
        assert not any(k.startswith("llm.input_messages") for k in s.attributes)


def test_che_noi_dung_off_khong_con_chu_nao(monkeypatch, bat_trace):
    monkeypatch.setenv("MARK_PHOENIX_CONTENT", "off")
    monkeypatch.setenv("MARK_PHOENIX_LLM_INPUT", "1")

    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_pre_api(api_request_id="r1", session_id="s1", request={"body": {
            "messages": [{"role": "user", "content": "lịch sử"}]}})
        PT._on_post_api(**_kw_llm())
        PT._on_api_error(**_kw_llm(error={"type": "APIError", "message": "chi tiết lỗi"}))
        PT._on_post_tool(**_kw_tool(status="error", error_type="X",
                                    error_message="chi tiết tool"))
        raise RuntimeError("chi tiết exception")

    with pytest.raises(RuntimeError):
        reply("câu hỏi riêng tư", chat_id="oc_5")
    spans = bat_trace.get_finished_spans()
    assert len(spans) == 4
    for s in spans:
        for k in s.attributes:
            assert k not in ("input.value", "output.value", "tool.parameters"), (s.name, k)
            assert not k.startswith("llm.input_messages"), k
            assert not k.endswith("message.content"), k
    tat_ca = _moi_chuoi(spans)
    for chu in ("câu hỏi riêng tư", "chi tiết", "để em quét", "HAPAS", "lịch sử"):
        assert chu not in tat_ca, chu
    # Vẫn còn khung để đọc: tên, token, trạng thái.
    s = _theo_ten(spans)
    assert s["mark.turn"].status.status_code.name == "ERROR"
    assert any(x.attributes.get("llm.token_count.total") == 150 for x in spans)


# ─────────────────────────────── lượt lỗi ───────────────────────────────

def test_luot_loi_ghi_error_va_nem_nguyen_ven(bat_trace):
    loi = ValueError(f"hỏng khi gọi với {_SK}")

    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_api_error(**_kw_llm(error={"type": "RateLimitError", "message": "HTTP 429"},
                                   status_code=429, retryable=True))
        raise loi

    with pytest.raises(ValueError) as e:
        reply("x", chat_id="oc_6")
    assert e.value is loi
    s = _theo_ten(bat_trace.get_finished_spans())
    goc, llm = s["mark.turn"], s["llm gpt-5.6-terra"]
    assert goc.status.status_code.name == "ERROR"
    assert "ValueError" in goc.status.description and _SK not in goc.status.description
    assert llm.status.status_code.name == "ERROR" and "429" in llm.status.description
    assert json.loads(llm.attributes["metadata"])["status_code"] == 429
    assert PT._ctxvar().get() is None, "lượt lỗi phải gỡ ngữ cảnh"


def test_luot_model_hong_qua_brain_la_error(monkeypatch, bat_trace):
    """Đi qua brain.reply THẬT: Hermes trả 429 dạng chữ → người dùng nhận câu dễ hiểu,
    span gốc vẫn ERROR (theo trạng thái audit), có span LLM và tool con."""
    # Nạp brain lần đầu ngay trong bài thì brain gọi bat() → gắn hook vào Hermes TOÀN CỤC;
    # bài này gọi hook thẳng nên chặn bước gắn, không để dính sang bài khác.
    monkeypatch.setattr(PT, "_dang_ky_hook", lambda: False)
    import brain
    import audit
    if not audit._BAT:
        pytest.skip("AUDIT_ENABLED=0")

    class AgentGia:
        model = "gpt-5.6-terra"

        def run_conversation(self, *a, **k):
            PT._on_post_api(**_kw_llm(session_id="sb"))
            with ThreadPoolExecutor(1) as ex:
                ex.submit(contextvars.copy_context().run, PT._on_post_tool,
                          **_kw_tool(session_id="")).result()
            return {"final_response": "API call failed after 3 retries: HTTP 429: The "
                                      "usage limit has been reached", "failed": True}

    monkeypatch.setattr(brain, "_resolve_agent", lambda *a, **k: AgentGia())
    monkeypatch.setattr(brain.lsr_platform, "lay_ngu_canh", lambda *a, **k: {})
    monkeypatch.setattr(brain.lsr_platform, "ghi_luot_ngu_canh", lambda *a, **k: None)
    monkeypatch.setattr(brain.memory_store, "load_history", lambda cid: [])
    monkeypatch.setattr(brain.memory_store, "append_turns", lambda *a, **k: None)
    dap = brain.reply("quét HAPAS", chat_id="lark:a:oc_b", sender_open_id=None)
    assert "HTTP 429" not in dap
    s = _theo_ten(bat_trace.get_finished_spans())
    assert set(s) == {"mark.turn", "llm gpt-5.6-terra", "tool social_listen"}
    assert s["mark.turn"].status.status_code.name == "ERROR"
    assert json.loads(s["mark.turn"].attributes["metadata"])["audit_turn_id"]


# ─────────────────────────────── fail-open ───────────────────────────────

def _cong_dong() -> int:
    so = socket.socket()
    so.bind(("127.0.0.1", 0))
    port = so.getsockname()[1]
    so.close()
    return port


def test_phoenix_chet_mark_van_tra_loi_nhanh(monkeypatch):
    _otel()
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    port = _cong_dong()
    monkeypatch.setenv("PHOENIX_COLLECTOR_ENDPOINT", f"http://127.0.0.1:{port}")
    monkeypatch.setenv("MARK_PHOENIX_SALT", "muoi-thu-nghiem-0123456789")
    provider = PT._dung_provider(
        OTLPSpanExporter(endpoint=f"http://127.0.0.1:{port}/v1/traces", timeout=1),
        dong_bo=False)

    def goc(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_post_api(**_kw_llm())
        PT._on_post_tool(**_kw_tool())
        return "đáp"

    boc = PT.luot(goc)
    t = time.perf_counter()
    for _ in range(20):
        assert boc("x", chat_id="oc_7") == "đáp"
    moi_luot = (time.perf_counter() - t) / 20
    assert moi_luot < 0.05, f"trace làm chậm lượt {moi_luot * 1000:.1f} ms"
    # Hook nhận rác (Hermes đổi payload) không bao giờ ném.
    rac = {k: None for k in _kw_llm()}
    PT._on_post_api(**rac)
    PT._on_api_error(**rac, error="không phải dict")
    PT._on_post_tool(**{k: None for k in _kw_tool()})
    PT._on_pre_api(request="rác")
    PT._on_post_api()
    t = time.perf_counter()
    provider.shutdown()
    assert time.perf_counter() - t < 10, "tắt máy bị treo vì Phoenix chết"


def test_loi_trong_trace_khong_toi_reply(monkeypatch, bat_trace):
    """Tracer hỏng giữa chừng (vd OTel đổi API) → reply vẫn trả đúng."""
    class Hong:
        def start_span(self, *a, **k):
            raise RuntimeError("tracer hỏng")

    monkeypatch.setitem(PT._tt, "tracer", Hong())

    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        PT._on_post_api(**_kw_llm())
        return "vẫn trả lời"

    assert reply("x", chat_id="oc_8") == "vẫn trả lời"


# ─────────────────────────────── gắn vào Hermes ───────────────────────────────

def _hermes_plugins():
    try:
        from config import config
        if config.hermes_agent_dir not in sys.path:
            sys.path.insert(0, config.hermes_agent_dir)
    except Exception:
        pass
    return pytest.importorskip("hermes_cli.plugins")


def test_hook_gan_dung_hermes_va_khong_trung(monkeypatch, bat_trace):
    """Gắn qua PluginContext.register_hook vào một PluginManager MỚI (không đụng bản
    toàn cục), gắn hai lần không nhân đôi, và Hermes invoke_hook thật đẻ đúng span."""
    plugins = _hermes_plugins()
    mgr = plugins.PluginManager()
    monkeypatch.setattr(plugins, "get_plugin_manager", lambda: mgr)
    assert PT._dang_ky_hook() and PT._dang_ky_hook()
    assert len(mgr._hooks["post_api_request"]) == 1
    assert len(mgr._hooks["post_tool_call"]) == 1
    assert "pre_api_request" not in mgr._hooks, "mặc định không gắn pre_api_request"
    for ten in ("pre_tool_call", "pre_llm_call", "transform_tool_result",
                "transform_llm_output"):
        assert ten not in mgr._hooks, f"không được gắn hook đổi hành vi {ten}"

    @PT.luot
    def reply(user_text, *, chat_id, sender_open_id=None, kenh=None):
        mgr.invoke_hook("post_api_request", **_kw_llm())
        mgr.invoke_hook("post_tool_call", **_kw_tool())
        return "ok"

    reply("x", chat_id="oc_9")
    assert set(_theo_ten(bat_trace.get_finished_spans())) == {
        "mark.turn", "llm gpt-5.6-terra", "tool social_listen"}


def test_bat_in_trang_thai(monkeypatch, bat_trace):
    monkeypatch.setattr(PT, "_dang_ky_hook", lambda: True)
    monkeypatch.setitem(PT._tt, "dau_cuoi", "http://127.0.0.1:9")
    dong = PT.bat()
    assert dong.startswith("Phoenix:    BẬT → http://127.0.0.1:9") and "hook ✅" in dong
    assert "project mark" in dong
