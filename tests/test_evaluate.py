from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("evaluate", ROOT / "tests" / "evaluate.py")
assert SPEC and SPEC.loader
evaluate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluate)


def test_normalize_is_case_and_accent_insensitive() -> None:
    assert evaluate.normalize("  KHÔNG  thể ") == "khong the"


def test_manifest_hash_matches_platform_algorithm() -> None:
    assert evaluate.manifest_hash({"b": 2, "a": "Trần"}) == "6f5b3493bc534824"


def test_declared_behavior_cases_are_loadable() -> None:
    cases = evaluate.load_cases()
    assert len(cases) == 5
    assert all(case["expect"] for case in cases)


def test_expectation_groups_accept_synonyms_without_dropping_concepts() -> None:
    expected = ["mẫu", ["không thể", "chưa thể", "không đủ"]]
    assert evaluate.missing_expectations("Mẫu này quá nhỏ nên chưa thể kết luận.", expected) == []
    assert evaluate.missing_expectations("Mẫu này đủ để kết luận.", expected) == [
        ["không thể", "chưa thể", "không đủ"]
    ]
