from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from nexterp_agent.item_master.postgres_catalog import PostgresCatalogSearchClient
from nexterp_agent.item_master.search import MaterialSearch


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_PATH = REPO_ROOT / "data" / "material_purchase_2024" / "material_search_eval_cases.csv"
GUARDRAIL_MODES = {"generic_guardrail", "high_risk_guardrail"}


@dataclass(frozen=True)
class EvalCase:
    query: str
    specs: dict[str, Any]
    expected_statuses: set[str]
    expected_top_item_name: str
    expected_canonical_group: str
    expected_review_mode: str
    notes: str


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[EvalCase]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = csv.DictReader(handle)
        return [case_from_row(row) for row in rows]


def case_from_row(row: dict[str, str]) -> EvalCase:
    specs_text = row.get("specs_json") or "{}"
    specs = json.loads(specs_text)
    if not isinstance(specs, dict):
        raise ValueError(f"specs_json must be an object for query={row.get('query')!r}")
    statuses = {status.strip() for status in (row.get("expected_status") or "").split("|") if status.strip()}
    if not statuses:
        raise ValueError(f"expected_status is required for query={row.get('query')!r}")
    return EvalCase(
        query=row.get("query") or "",
        specs=specs,
        expected_statuses=statuses,
        expected_top_item_name=row.get("expected_top_item_name") or "",
        expected_canonical_group=row.get("expected_canonical_group") or "",
        expected_review_mode=row.get("expected_review_mode") or "",
        notes=row.get("notes") or "",
    )


def evaluate_case(search: MaterialSearch, case: EvalCase) -> dict[str, Any]:
    result = search.search_items(case.query, specs=case.specs, limit=10)
    candidates = result.get("candidates") or []
    top = candidates[0] if candidates else {}
    top_name = top.get("item_name") or ""
    top_group = top.get("item_group") or ""
    status = result.get("status") or ""
    top1_name_hit = bool(case.expected_top_item_name) and top_name == case.expected_top_item_name
    canonical_group_hit = bool(case.expected_canonical_group) and top_group == case.expected_canonical_group
    status_hit = status in case.expected_statuses
    guardrail_hit = True
    if case.expected_review_mode in GUARDRAIL_MODES:
        guardrail_hit = status != "ready"
    passed = status_hit and guardrail_hit
    require_top_identity = case.expected_review_mode != "generic_guardrail"
    if case.expected_top_item_name:
        passed = passed and (top1_name_hit or not require_top_identity)
    if case.expected_canonical_group:
        passed = passed and (canonical_group_hit or not require_top_identity)

    return {
        "query": case.query,
        "expected_status": "|".join(sorted(case.expected_statuses)),
        "status": status,
        "expected_top_item_name": case.expected_top_item_name,
        "top_item_name": top_name,
        "top_item_code": top.get("item_code") or "",
        "expected_canonical_group": case.expected_canonical_group,
        "top_canonical_group": top_group,
        "top_score": result.get("top_score") or 0,
        "review_mode": case.expected_review_mode,
        "top1_name_hit": top1_name_hit,
        "canonical_group_hit": canonical_group_hit,
        "status_hit": status_hit,
        "guardrail_hit": guardrail_hit,
        "passed": passed,
        "decision_reason": result.get("decision_reason") or "",
        "questions": result.get("questions") or [],
    }


def run_eval(dsn: str, cases: list[EvalCase]) -> list[dict[str, Any]]:
    search = MaterialSearch(PostgresCatalogSearchClient(dsn))
    return [evaluate_case(search, case) for case in cases]


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    expected_top_count = sum(1 for result in results if result["expected_top_item_name"])
    expected_group_count = sum(1 for result in results if result["expected_canonical_group"])
    return {
        "total": len(results),
        "passed": sum(1 for result in results if result["passed"]),
        "top1_name_hits": sum(1 for result in results if result["top1_name_hit"]),
        "top1_name_total": expected_top_count,
        "canonical_group_hits": sum(1 for result in results if result["canonical_group_hit"]),
        "canonical_group_total": expected_group_count,
        "status_distribution": dict(Counter(result["status"] for result in results)),
        "review_mode_distribution": dict(Counter(result["review_mode"] for result in results)),
        "failures": [result for result in results if not result["passed"]],
    }


def print_summary(summary: dict[str, Any], *, max_failures: int) -> None:
    print(f"Total cases: {summary['total']}")
    print(f"Passed cases: {summary['passed']}/{summary['total']}")
    print(f"Top1 item-name hits: {summary['top1_name_hits']}/{summary['top1_name_total']}")
    print(f"Canonical group hits: {summary['canonical_group_hits']}/{summary['canonical_group_total']}")
    print(f"Status distribution: {json.dumps(summary['status_distribution'], ensure_ascii=False, sort_keys=True)}")
    print(f"Review mode distribution: {json.dumps(summary['review_mode_distribution'], ensure_ascii=False, sort_keys=True)}")

    failures = summary["failures"]
    if not failures:
        print("Failures: none")
        return

    print(f"Failures: {len(failures)}")
    for failure in failures[:max_failures]:
        questions = "；".join(failure["questions"])
        print(
            "- "
            f"{failure['query']} | status {failure['status']} expected {failure['expected_status']} | "
            f"top {failure['top_item_name']} ({failure['top_item_code']}) expected {failure['expected_top_item_name']} | "
            f"group {failure['top_canonical_group']} expected {failure['expected_canonical_group']} | "
            f"score {failure['top_score']} | {failure['decision_reason']} {questions}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run material catalog search quality evaluation cases.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH, help="CSV file with eval cases.")
    parser.add_argument("--dsn", default="", help="PostgreSQL DSN. Defaults to MATERIAL_CATALOG_DATABASE_URL from .env.")
    parser.add_argument("--limit", type=int, default=0, help="Run only the first N cases.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary JSON.")
    parser.add_argument("--max-failures", type=int, default=20, help="Maximum failure rows to print.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any case fails.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")
    dsn = args.dsn or os.environ.get("MATERIAL_CATALOG_DATABASE_URL") or ""
    if not dsn:
        raise SystemExit("MATERIAL_CATALOG_DATABASE_URL is not set. Add it to .env or pass --dsn.")

    cases = load_cases(args.cases)
    if args.limit:
        cases = cases[: args.limit]
    results = run_eval(dsn, cases)
    summary = summarize(results)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print_summary(summary, max_failures=args.max_failures)
    return 1 if args.strict and summary["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
