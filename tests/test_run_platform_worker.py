from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_platform_worker.py"
SPEC = importlib.util.spec_from_file_location("run_platform_worker", MODULE_PATH)
assert SPEC and SPEC.loader
worker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker)


def test_worker_refuses_production_agent(monkeypatch):
    monkeypatch.setenv("LSR_AGENT_ID", "AG-SOCIAL-LISTENING")
    monkeypatch.setenv("LSR_JOB_POLL_ENABLED", "1")

    with pytest.raises(SystemExit, match="-TEST"):
        worker._require_test_config()


def test_worker_requires_explicit_poll_opt_in(monkeypatch):
    monkeypatch.setenv("LSR_AGENT_ID", "AG-SOCIAL-LISTENING-TEST")
    monkeypatch.delenv("LSR_JOB_POLL_ENABLED", raising=False)

    with pytest.raises(SystemExit, match="LSR_JOB_POLL_ENABLED=1"):
        worker._require_test_config()


def test_worker_accepts_test_agent(monkeypatch):
    monkeypatch.setenv("LSR_AGENT_ID", "AG-SOCIAL-LISTENING-TEST")
    monkeypatch.setenv("LSR_JOB_POLL_ENABLED", "1")

    worker._require_test_config()
