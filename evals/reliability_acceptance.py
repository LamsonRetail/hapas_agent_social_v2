"""Root-authored acceptance: same assertions run against before and after trees.

This tests deterministic contracts with a replayed model response, not live LLM accuracy.
Network is forbidden; paid actor and Sheet writes use the existing offline fixture.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(os.environ.get("MARK_ACCEPTANCE_REPO") or Path(__file__).resolve().parents[1])
sys.path.insert(0, str(ROOT))
os.environ.update(LARK_APP_ID="acceptance", LARK_APP_SECRET="acceptance",
                  MARK_THEO_TAI_KHOAN_CONSOLE="0", AUDIT_TO_BASE="0",
                  APIFY_KIEM_TRUOC="0", SOCIAL_AI_PHAN_XU="0", SOCIAL_NEN_TU_CHAY="0")
import brain
import audit
import lsr_policy
import tiktok_ads_tool as T
from tools.registry import registry

spec = importlib.util.spec_from_file_location("offline_top_ads_fixture", ROOT / "tests/test_tiktok_top_ads.py")
fixture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture_module)


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    import requests
    import urllib.request
    def forbidden(*args, **kwargs):
        raise AssertionError("Acceptance attempted a real network request")
    monkeypatch.setattr(requests.sessions.Session, "request", forbidden)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(audit, "_THU_MUC", tmp_path / "audit")
    monkeypatch.setattr(audit, "_DAY_LEN_BASE", False)
    monkeypatch.setattr(brain.lsr_platform, "lay_ngu_canh", lambda *a, **k: {})
    monkeypatch.setattr(brain.lsr_platform, "ghi_luot_ngu_canh", lambda *a, **k: None)
    monkeypatch.setattr(brain.memory_store, "load_history", lambda *a: [])
    monkeypatch.setattr(brain.memory_store, "append_turns", lambda *a: None)
    monkeypatch.setattr(brain.tai_khoan_ai, "ghi_luot", lambda *a, **k: None)
    try:
        import execution_receipts as R
        monkeypatch.setattr(R, "_DIR", tmp_path / "receipts")
    except ImportError:
        pass


@pytest.fixture
def actor(monkeypatch):
    return fixture_module.gia.__wrapped__(monkeypatch)


def test_permission_error_cannot_be_audit_ok():
    tid = audit.bat_dau("acceptance", None, "read task")
    audit.ghi_tool("tra_tien_do", {}, json.dumps({"error": "missing_identity"}), 0.1)
    rec = audit.ket_thuc(tid, "Cannot identify account")
    assert rec["trang_thai"] == "blocked"
    assert rec["tool"][0]["co_ket_qua"] is False


def test_paid_quota_not_free_plan(actor):
    actor["ket"]["msg"] = "Quota exceeded for a paid account. Upgrade quota in billing."
    out = json.loads(T._handle({"so_ads": 20}))
    warning = " ".join(out.get("canh_bao") or [])
    assert "gói Free" not in warning
    assert out.get("limit_reason", {}).get("code") == "quota_exceeded"


def test_unknown_short_result_does_not_invent_reason(actor):
    out = json.loads(T._handle({"so_ads": 20}))
    assert out.get("limit_reason", {}).get("verified") is False
    assert "chưa xác định nguyên nhân" in " ".join(out.get("canh_bao") or [])


def test_broader_fallback_not_complete_even_with_requested_count(actor):
    actor["ket"]["chinh"] = RuntimeError("upstream unavailable")
    actor["ket"]["du_phong"] = [dict(fixture_module.LEXIS[0], id=str(i)) for i in range(20)]
    out = json.loads(T._handle({"nganh": "trang sức", "so_ads": 20}))
    assert out["tom_tat"]["so_ads"] == 20
    assert out.get("scope_match") is False
    assert out.get("status") == "partial"


def test_docs_fetch_readonly_available():
    assert lsr_policy.decide("lark_cli", {"args": ["docs", "+fetch", "--doc-token", "doc_x",
                                                  "--doc-format", "markdown"]}).allowed


def test_unknown_action_not_allowed_by_option_value():
    assert not lsr_policy.decide("lark_cli", {"args": ["docs", "+mystery", "--title", "fetch"]}).allowed


def test_write_still_blocked():
    for args in (["docs", "+update"], ["api", "POST", "/open-apis/docx/v1/documents"]):
        assert not lsr_policy.decide("lark_cli", {"args": args}).allowed


def test_reply_pipeline_corrects_recorded_false_confession_without_rerun(monkeypatch, actor):
    class ModelReplay:
        model = "offline-replay"
        calls = 0
        def run_conversation(self, text, **kwargs):
            if text == "ok chạy":
                ModelReplay.calls += 1
                registry._tools["tiktok_top_ads"].handler({"so_ads": 20, "ky_ngay": "7"})
                return {"final_response": "Đã chạy, có Sheet."}
            return {"final_response": "Tôi xử lý sai: không thực sự chạy công cụ nên số 3 chưa xác minh."}
    monkeypatch.setattr(brain, "_resolve_agent", lambda *a, **k: ModelReplay())
    brain.reply("ok chạy", chat_id="acceptance:same")
    reply = brain.reply("sao bạn pending required trước của tôi", chat_id="acceptance:same")
    assert "không thực sự chạy công cụ" not in reply
    assert "3/20" in reply
    assert ModelReplay.calls == 1 and len(actor["goi"]) == 1


def test_unrelated_tool_cannot_rewrite_legitimate_denial(monkeypatch, tmp_path):
    try:
        import execution_receipts as R
    except ImportError:
        return  # Legacy has no guard; negative control already holds.
    R.record("acceptance", "wiki-turn", "lark_cli", {"args": ["wiki", "+node-get"]}, {"success": True})
    answer = "Tôi không hề chạy TikTok cho yêu cầu này."
    actual, changed = R.ground_final_answer("acceptance", "TikTok chạy chưa?", answer)
    assert (actual, changed) == (answer, False)


def test_quote_cannot_prove_paid_execution():
    try:
        import execution_receipts as R
    except ImportError:
        return
    R.record("acceptance", "estimate", "tiktok_top_ads", {}, {
        "success": True, "chi_uoc_tinh": True, "da_chay": False, "so_ads": 20})
    answer = "Tôi không hề chạy công cụ TikTok."
    assert R.ground_final_answer("acceptance", "đã chạy chưa?", answer) == (answer, False)


def test_actual_logged_confession_after_intermediate_skill_read():
    try:
        import execution_receipts as R
    except ImportError:
        pytest.fail("Legacy has no persistent execution evidence")
    R.record("actual-chat", "10845caa1562", "tiktok_top_ads", {"so_ads": 20}, {
        "success": True, "so_ads_xin": 20, "tom_tat": {"so_ads": 5},
        "chi_phi_thuc_usd": 0.02, "sheet_url": "https://example.test/sheet"})
    R.record("actual-chat", "b20a8d5042dd", "dung_ky_nang", {}, {"success": True})
    original = ('Tôi xử lý sai luồng ở yêu cầu trước. Bạn đã xác nhận “ok chạy”, '
                'nhưng tôi trả kết quả như thể đã quét mà không thực sự chạy công cụ '
                '— nên cả con số “5 quảng cáo” lẫn lời giải thích về giới hạn nguồn chưa được xác minh.')
    actual, changed = R.ground_final_answer("actual-chat", "sao bạn pending required trước của tôi", original)
    assert changed and "5/20" in actual and "0.02 USD" in actual


def test_new_failure_not_hidden_by_old_success():
    try:
        import execution_receipts as R
    except ImportError:
        return
    R.record("chat", "old", "tiktok_top_ads", {}, {"success": True, "actual_count": 5})
    R.record("chat", "new", "tiktok_top_ads", {}, {"error": "budget_exceeded"})
    answer = "Tôi không hề chạy công cụ thành công."
    assert R.ground_final_answer("chat", "đã chạy chưa?", answer) == (answer, False)


def test_read_policy_does_not_enable_unknown_fetch_resource():
    assert not lsr_policy.decide("lark_cli", {"args": ["other", "+fetch"]}).allowed


def test_web_body_open_id_cannot_impersonate_user():
    import inspect
    from lsr_platform import _lark_sender_ref
    payload = {"user_ref": "ou_victim"}
    args = {"channel": "web"} if "channel" in inspect.signature(_lark_sender_ref).parameters else {}
    assert _lark_sender_ref(payload, **args) is None


def test_verified_web_sender_and_legacy_lark_sender_work():
    import inspect
    from lsr_platform import _lark_sender_ref
    args = {"channel": "web"} if "channel" in inspect.signature(_lark_sender_ref).parameters else {}
    assert _lark_sender_ref({"user_ref": "tester@example.test", "sender_open_id": "ou_verified",
                             "sender_identity_verified": True}, **args) == "ou_verified"
    assert _lark_sender_ref({"sender_open_id": "ou_lark"}) == "ou_lark"


def test_policy_denial_is_captured_before_handler_and_blocks_old_success(monkeypatch):
    try:
        import execution_receipts as R
    except ImportError:
        pytest.fail("Legacy has no execution evidence")
    import dong_ho_luot
    monkeypatch.setattr(dong_ho_luot, "xet", lambda: ("", 0))
    monkeypatch.setattr(lsr_policy, "decide", lambda *a, **k: lsr_policy.PolicyDecision(False, "test blocked"))
    R.record("policy-chat", "old", "tiktok_top_ads", {}, {"success": True, "actual_count": 5})
    tid = audit.bat_dau("policy-chat", None, "new request")
    R.set_current_turn("policy-chat", tid)
    try:
        out = registry.dispatch("tiktok_top_ads", {"so_ads": 20})
        assert "policy_denied" in out
        assert R.load("policy-chat")[-1]["status"] == "blocked"
        answer = "Tôi không hề chạy công cụ TikTok."
        assert R.ground_final_answer("policy-chat", "đã chạy chưa?", answer) == (answer, False)
    finally:
        R.clear_current_turn()
        audit.ket_thuc(tid, "blocked")
