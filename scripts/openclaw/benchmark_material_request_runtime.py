from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from time import perf_counter
from typing import Any, Literal


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from nexterp_agent.workbench.openclaw_compare import OpenClawPreviewRunner  # noqa: E402


Expectation = Literal["confirmation", "clarification"]


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    text: str
    expectation: Expectation


SCENARIOS = (
    Scenario("exact-code-iso-date", "申请物料 MAT-CEM-000008 20包，2026-08-04需要。", "confirmation"),
    Scenario("exact-code-relative-date", "给合流1.3标申请 MAT-CEM-000008 20包，后天要用。", "confirmation"),
    Scenario("exact-name", "申请水泥42.5袋装50kg 20包，后天要用。", "confirmation"),
    Scenario("multiple-items", "申请 MAT-CEM-000008 20包和 MAT-CEM-000011 10包，2026-08-04需要。", "confirmation"),
    Scenario("explicit-project", "合流1.3标需要 MAT-CEM-000008 5包，明天使用。", "confirmation"),
    Scenario("ambiguous-item", "申请20包水泥，后天要用。", "clarification"),
    Scenario("missing-quantity", "申请 MAT-CEM-000008，后天要用。", "clarification"),
    Scenario("invalid-quantity", "申请 MAT-CEM-000008 负5包，后天要用。", "clarification"),
    Scenario("unknown-item", "申请物料 NOT-A-REAL-ITEM 20包，后天要用。", "clarification"),
    Scenario("wrong-uom", "申请 MAT-CEM-000008 20吨，后天要用。", "clarification"),
)


def evaluate(result: dict[str, Any], expectation: Expectation) -> tuple[bool, str]:
    pending = bool(result.get("pending_id") and result.get("confirmation"))
    questions = result.get("questions") if isinstance(result.get("questions"), list) else []
    message = str(result.get("message") or "")
    asks_user = bool(questions) or bool(re.search(r"请|确认|选择|补充|说明|数量|无法|不匹配|不存在", message))
    no_execute = "nexterp_execute_prepared_operation" not in (result.get("tool_summary") or {}).get("tools", [])
    if expectation == "confirmation":
        return pending and no_execute, "生成冻结确认且未执行" if pending and no_execute else "未生成正确的冻结确认"
    return (not pending) and asks_user and no_execute, "正确追问或阻断且未执行" if (not pending) and asks_user and no_execute else "未正确追问或发生了不应有的确认"


def run_case(index: int, scenario: Scenario) -> dict[str, Any]:
    started = perf_counter()
    try:
        result = OpenClawPreviewRunner(ROOT).run(
            text=scenario.text,
            project_label="合流1.3标",
            employee_name="毛晓泉",
        )
        passed, reason = evaluate(result, scenario.expectation)
        return {
            "run": index,
            "scenario_id": scenario.scenario_id,
            "expectation": scenario.expectation,
            "passed": passed,
            "reason": reason,
            "status": result.get("status"),
            "duration_ms": result.get("duration_ms"),
            "tools": (result.get("tool_summary") or {}).get("tools") or [],
            "tool_failures": (result.get("tool_summary") or {}).get("failures", 0),
            "loaded_nodes": [row.get("node_id") for row in result.get("loaded_nodes") or []],
            "pending": bool(result.get("pending_id")),
            "question_count": result.get("question_count", 0),
            "message": result.get("message") or "",
        }
    except Exception as exc:
        return {
            "run": index,
            "scenario_id": scenario.scenario_id,
            "expectation": scenario.expectation,
            "passed": False,
            "reason": str(exc),
            "status": "failed",
            "duration_ms": round((perf_counter() - started) * 1000),
            "tools": [],
            "tool_failures": 1,
            "loaded_nodes": [],
            "pending": False,
            "question_count": 0,
            "message": "",
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the v0.5 OpenClaw material-request stability benchmark.")
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "runtime" / "openclaw_material_request_benchmark.json",
    )
    args = parser.parse_args()
    if args.runs < 1 or args.workers < 1:
        parser.error("--runs and --workers must be positive")

    cases = [(index + 1, SCENARIOS[index % len(SCENARIOS)]) for index in range(args.runs)]
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(args.workers, args.runs)) as executor:
        futures = {executor.submit(run_case, index, scenario): index for index, scenario in cases}
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"[{result['run']:02d}/{args.runs}] {result['scenario_id']}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)

    results.sort(key=lambda row: row["run"])
    passed = sum(1 for row in results if row["passed"])
    durations = sorted(int(row.get("duration_ms") or 0) for row in results)
    report = {
        "version": "openclaw-manual-runtime-v0.5",
        "mode": "preview_only",
        "runs": args.runs,
        "passed": passed,
        "failed": args.runs - passed,
        "pass_rate": round(passed / args.runs, 4),
        "zero_execute_calls": all("nexterp_execute_prepared_operation" not in row["tools"] for row in results),
        "median_duration_ms": durations[len(durations) // 2],
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False, indent=2))
    return 0 if passed >= max(1, args.runs - 1) and report["zero_execute_calls"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
