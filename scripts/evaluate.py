"""Run Mark's declared behavioral cases and emit an enroll evaluation report.

This runner calls the real local ``brain.reply`` with the configured model. It
disables Platform context/telemetry and external audit sinks so pre-enroll
results cannot depend on the production agent or write to Lark/Base.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import register_test_agent  # noqa: E402


REPORT_PATH = register_test_agent.evaluation_path()


def normalize(value: str) -> str:
    text = unicodedata.normalize("NFD", value or "")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return " ".join(text.casefold().split())


def manifest_hash(manifest: dict) -> str:
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()[:16]


def load_cases() -> list[dict]:
    rows = []
    path = ROOT / "tests" / "tests.jsonl"
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        row = json.loads(raw)
        if not row.get("q") or not isinstance(row.get("expect"), list):
            raise SystemExit(f"Case dòng {line_no} không hợp lệ.")
        rows.append(row)
    if len(rows) < 2:
        raise SystemExit("Cần ít nhất 2 behavioral test case.")
    return rows


def missing_expectations(response: str, expectations: list) -> list:
    """Return unmet concepts; nested lists mean any synonym may satisfy the concept."""
    normalized = normalize(response)
    missing = []
    for expected in expectations:
        alternatives = expected if isinstance(expected, list) else [expected]
        if not alternatives or not any(normalize(term) in normalized for term in alternatives):
            missing.append(expected)
    return missing


def prepare_environment() -> None:
    for key in (
        "LSR_COLLECTOR",
        "LSR_PLATFORM_URL",
        "LSR_AGENT_ID",
        "LSR_TELEMETRY_API_KEY",
    ):
        os.environ[key] = ""
    os.environ["LSR_POLICY_MODE"] = "enforce"
    os.environ["AUDIT_TO_BASE"] = "0"
    os.environ["AUDIT_ENABLED"] = "0"


def run() -> dict:
    prepare_environment()
    import brain  # imported only after external effects have been disabled

    cases = load_cases()
    failures = []
    results = []
    for index, case in enumerate(cases, 1):
        response = brain.reply(
            case["q"],
            chat_id=f"eval:mark-test:{index}:{os.getpid()}",
            sender_open_id=None,
        )
        missing = missing_expectations(response, case["expect"])
        passed = not missing
        results.append({"case": index, "passed": passed, "expected": case["expect"]})
        if missing:
            failures.append({"case": index, "missing": missing})
        print(f"MARK-EVAL-{index:02d}: {'PASS' if passed else 'FAIL'}")

    manifest = register_test_agent.build_payload()["manifest"]
    report = {
        "manifest_hash": manifest_hash(manifest),
        "tests_total": len(cases),
        "tests_pass": len(cases) - len(failures),
        "failures": failures,
        "results": results,
        "runner": "scripts/evaluate.py",
        "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Kết quả: {report['tests_pass']}/{report['tests_total']}")
    print(f"Báo cáo: {REPORT_PATH}")
    return report


if __name__ == "__main__":
    outcome = run()
    raise SystemExit(0 if outcome["tests_pass"] == outcome["tests_total"] else 1)
