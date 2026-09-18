import json
from pathlib import Path

import lsr_platform


def _set_platform_env(monkeypatch, agent_id="AG-SOCIAL-LISTENING-TEST"):
    monkeypatch.setenv("LSR_COLLECTOR", "https://collector.example.test")
    monkeypatch.setenv("LSR_PLATFORM_URL", "https://platform.example.test")
    monkeypatch.setenv("LSR_AGENT_ID", agent_id)
    monkeypatch.setenv("LSR_TELEMETRY_API_KEY", "test-key")


def test_redact_before_wal():
    text = "email a@example.com, phone 0912 345 678, token=secret-value, ou_abcdefghijk"
    clean = lsr_platform._redact(text)
    assert "a@example.com" not in clean
    assert "0912" not in clean
    assert "secret-value" not in clean
    assert "ou_abcdefghijk" not in clean


def test_job_poll_requires_explicit_test_flag(monkeypatch):
    _set_platform_env(monkeypatch)
    monkeypatch.delenv("LSR_JOB_POLL_ENABLED", raising=False)
    assert not lsr_platform._job_poll_duoc_phep(lsr_platform._cau_hinh())
    monkeypatch.setenv("LSR_JOB_POLL_ENABLED", "1")
    assert lsr_platform._job_poll_duoc_phep(lsr_platform._cau_hinh())


def test_production_poll_requires_second_override(monkeypatch):
    _set_platform_env(monkeypatch, "AG-SOCIAL-LISTENING")
    monkeypatch.setenv("LSR_JOB_POLL_ENABLED", "1")
    monkeypatch.delenv("LSR_ALLOW_PRODUCTION_POLL", raising=False)
    assert not lsr_platform._job_poll_duoc_phep(lsr_platform._cau_hinh())
    monkeypatch.setenv("LSR_ALLOW_PRODUCTION_POLL", "1")
    assert lsr_platform._job_poll_duoc_phep(lsr_platform._cau_hinh())


def test_context_env_is_dev_only_for_test_agent(monkeypatch):
    _set_platform_env(monkeypatch)
    assert lsr_platform._context_env(lsr_platform._cau_hinh()) == "dev"
    _set_platform_env(monkeypatch, "AG-SOCIAL-LISTENING")
    monkeypatch.setenv("LSR_CONTEXT_ENV", "dev")
    assert lsr_platform._context_env(lsr_platform._cau_hinh()) == "prod"


def test_web_user_ref_is_not_sent_to_lark_contact_api():
    assert lsr_platform._lark_sender_ref({"user_ref": "thamnt@hapas.vn"}) is None
    assert lsr_platform._lark_sender_ref({"user_ref": "console"}) is None
    assert lsr_platform._lark_sender_ref({"user_ref": "ou_12345678"}) == "ou_12345678"


def test_wal_retries_with_same_run_id(monkeypatch, tmp_path: Path):
    _set_platform_env(monkeypatch)
    monkeypatch.setenv("LSR_WAL_DIR", str(tmp_path))
    trace = {"run_id": "r-123", "agent_id": "AG-SOCIAL-LISTENING-TEST"}
    path = lsr_platform._queue_trace(trace)
    assert path and path.exists()

    monkeypatch.setattr(lsr_platform, "_post_trace", lambda _trace, _c: False)
    first = lsr_platform.flush_wal()
    assert first == {"sent": 0, "pending": 1, "enabled": True}
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "r-123"

    seen = []
    monkeypatch.setattr(
        lsr_platform,
        "_post_trace",
        lambda sent_trace, _c: seen.append(sent_trace["run_id"]) is None or True,
    )
    second = lsr_platform.flush_wal()
    assert second["sent"] == 1
    assert second["pending"] == 0
    assert seen == ["r-123"]
