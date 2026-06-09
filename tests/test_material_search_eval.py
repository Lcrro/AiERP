from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "run_material_search_eval.py"
SPEC = importlib.util.spec_from_file_location("run_material_search_eval", SCRIPT_PATH)
assert SPEC and SPEC.loader
eval_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = eval_module
SPEC.loader.exec_module(eval_module)

DEFAULT_CASES_PATH = eval_module.DEFAULT_CASES_PATH
evaluate_case = eval_module.evaluate_case
load_cases = eval_module.load_cases
summarize = eval_module.summarize


class StaticSearch:
    def search_items(self, query, *, specs=None, limit=10):
        return {
            "status": "needs_clarification" if query == "接头" else "ready",
            "top_score": 100,
            "candidates": [
                {
                    "item_code": "X-1",
                    "item_name": "不锈钢卡扣接头" if query == "接头" else "铜鼻子",
                    "item_group": "液压气动/液压管路/高压胶管"
                    if query == "接头"
                    else "电气与自动化/电线电缆与敷设/电线电缆",
                }
            ],
            "questions": ["请补充规格"] if query == "接头" else [],
            "decision_reason": "fixture",
        }


def test_eval_cases_csv_has_expected_shape_and_coverage() -> None:
    cases = load_cases(DEFAULT_CASES_PATH)

    assert 30 <= len(cases) <= 50
    assert all(case.query for case in cases)
    assert all(case.expected_statuses for case in cases)
    assert all(isinstance(case.specs, dict) for case in cases)
    assert {case.expected_review_mode for case in cases} >= {
        "exact_alias",
        "typo",
        "generic_guardrail",
        "high_risk_guardrail",
        "spec_match",
    }


def test_eval_cases_include_required_purchase_phrases() -> None:
    queries = {case.query for case in load_cases(DEFAULT_CASES_PATH)}

    for query in ["铜鼻子300A", "镀锌内丝直接2寸", "帆布手套", "割咀G01-100型2号", "接头", "吊带5T*6m"]:
        assert query in queries


def test_evaluate_case_scores_status_top_name_group_and_guardrail() -> None:
    cases = load_cases(Path("tests/fixtures/does-not-exist.csv")) if False else load_cases(DEFAULT_CASES_PATH)
    copper = next(case for case in cases if case.query == "铜鼻子300A")
    generic = next(case for case in cases if case.query == "接头")

    copper_result = evaluate_case(StaticSearch(), copper)
    generic_result = evaluate_case(StaticSearch(), generic)
    summary = summarize([copper_result, generic_result])

    assert copper_result["passed"] is True
    assert generic_result["guardrail_hit"] is True
    assert summary["total"] == 2
    assert summary["passed"] == 2
