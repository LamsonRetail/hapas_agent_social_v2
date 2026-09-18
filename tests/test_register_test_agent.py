from __future__ import annotations

import importlib.util
from pathlib import Path
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "register_test_agent", ROOT / "scripts" / "register_test_agent.py"
)
assert SPEC and SPEC.loader
register_test_agent = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(register_test_agent)


def test_payload_is_isolated_from_production() -> None:
    payload = register_test_agent.build_payload()
    manifest = payload["manifest"]

    assert payload["agent_id"] == "AG-SOCIAL-LISTENING-TEST"
    assert payload["deployment"] == "external"
    assert manifest["agent"]["id"] == payload["agent_id"]
    assert all(item["channel"] == "web" for item in manifest["connections"])


def test_payload_is_owner_only_and_uses_test_index() -> None:
    payload = register_test_agent.build_payload()
    manifest = payload["manifest"]
    audience = manifest["permissions"]["data"]["audiences"][0]
    index = next(item for item in manifest["data_sources"] if item["kind"] == "index")

    assert audience["viewers"] == ["thamnt@hapas.vn"]
    assert index["scope"] == "agent:AG-SOCIAL-LISTENING-TEST:approved"
    assert "lark_app" not in {item["channel"] for item in manifest["connections"]}


def test_exists_probe_sends_admin_authorization(monkeypatch) -> None:
    seen = {}

    def fake_urlopen(request, timeout):
        seen["authorization"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        raise urllib.error.HTTPError(request.full_url, 404, "not found", {}, None)

    monkeypatch.setattr(register_test_agent.urllib.request, "urlopen", fake_urlopen)

    assert register_test_agent.agent_exists("https://platform.example", "secret") is False
    assert seen == {"authorization": "Bearer secret", "timeout": 15}
