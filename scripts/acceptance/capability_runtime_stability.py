from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime
import json
from pathlib import Path
import statistics
import sys
from time import perf_counter
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.workbench.server import AgentWorkbenchService  # noqa: E402


REPORT_PATH = ROOT / "data" / "runtime" / "capability_runtime_stability_report.json"
FAILURE_CANDIDATES_PATH = ROOT / "data" / "runtime" / "capability_runtime_failure_candidates_report.json"
PROJECT_CODE = "PRJ-HL-13"
CONTEXT = {
    "project_code": PROJECT_CODE,
    "erpnext_project": "PROJ-0010",
    "warehouse": "合流1.3标仓库 - SD",
}


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    user: str
    text: str
    expected_capability: str
    accepted_statuses: tuple[str, ...]


CASES = (
    BenchmarkCase(
        "material_request_preview",
        "mao.xiaoquan@stec-up.local",
        "为合流1.3标创建材料申请：物料 MAT-CEM-000008，20包，送合流1.3标仓库，需求日期2026-07-25。",
        "material_request.create",
        ("needs_confirmation",),
    ),
    BenchmarkCase(
        "stock_balance_query",
        "mao.xiaoquan@stec-up.local",
        "查询物料 MAT-CEM-000008 在合流1.3标仓库的实时库存。",
        "stock.balance.query",
        ("completed",),
    ),
    BenchmarkCase(
        "project_task_preview",
        "hu.yinhu@stec-up.local",
        "为合流1.3标创建任务：检查开工材料，优先级High，计划2026-07-21开始，2026-07-23完成。",
        "project.task.create",
        ("needs_confirmation",),
    ),
    BenchmarkCase(
        "project_cost_query",
        "hu.yinhu@stec-up.local",
        "查询合流1.3标从2026-07-01到2026-07-20的项目成本。",
        "project.cost.query",
        ("completed",),
    ),
    BenchmarkCase(
        "accounts_payable_query",
        "fang.wenqian@stec-up.local",
        "查询 STEC (Demo) 截至2026-07-20的应付账款。",
        "finance.accounts_payable.query",
        ("completed",),
    ),
)


def _capabilities(steps: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for step in steps:
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        arguments = step.get("arguments") if isinstance(step.get("arguments"), dict) else {}
        for card in result.get("capabilities") or []:
            if isinstance(card, dict):
                capability_id = str(card.get("capability_id") or "").strip()
                if capability_id and capability_id not in values:
                    values.append(capability_id)
        candidates = (
            result.get("capability"),
            arguments.get("capability_id"),
            (arguments.get("intent") or {}).get("capability_id")
            if isinstance(arguments.get("intent"), dict)
            else None,
        )
        for value in candidates:
            text = str(value or "").strip()
            if text and text not in values:
                values.append(text)
    return values


def _count_observation(steps: list[dict[str, Any]], observation_type: str) -> int:
    return sum(
        1
        for step in steps
        if isinstance(step.get("result"), dict)
        and step["result"].get("type") == observation_type
    )


def run_case(
    service: AgentWorkbenchService,
    case: BenchmarkCase,
    *,
    round_number: int,
) -> dict[str, Any]:
    conversation_id = f"capability-stability-{case.case_id}-{round_number}"
    service.reset_session(case.user, PROJECT_CODE, conversation_id)
    runtime = service.runtime(service.scoped_session_store(case.user, PROJECT_CODE, conversation_id))
    started = perf_counter()
    result = runtime.run_once(
        case.text,
        user=case.user,
        today=date.today(),
        request_id=conversation_id,
        context=CONTEXT,
    ).to_dict()
    elapsed_ms = round((perf_counter() - started) * 1000, 2)
    raw_steps = result.get("steps")
    steps = list(raw_steps) if isinstance(raw_steps, (list, tuple)) else []
    capabilities = _capabilities(steps)
    bypass_attempts = _count_observation(steps, "capability_required")
    repairs = (
        _count_observation(steps, "business_action_error")
        + _count_observation(steps, "tool_validation_error")
    )
    repeats = sum(1 for step in steps if step.get("action") == "no_progress")
    success = (
        result.get("status") in case.accepted_statuses
        and case.expected_capability in capabilities
        and bypass_attempts == 0
        and result.get("status") != "failed"
    )
    service.reset_session(case.user, PROJECT_CODE, conversation_id)
    return {
        "case_id": case.case_id,
        "round": round_number,
        "success": success,
        "status": result.get("status"),
        "message": result.get("message"),
        "expected_capability": case.expected_capability,
        "observed_capabilities": capabilities,
        "step_count": len(steps),
        "repair_count": repairs,
        "repeat_count": repeats,
        "bypass_attempts": bypass_attempts,
        "elapsed_ms": elapsed_ms,
        "action_trace": [
            {
                "action": step.get("action"),
                "tool": (
                    (step.get("payload") or {}).get("tool")
                    or ((step.get("payload") or {}).get("tool_call") or {}).get("tool")
                ) if isinstance(step.get("payload"), dict) else None,
                "result_type": (step.get("result") or {}).get("type")
                if isinstance(step.get("result"), dict)
                else None,
                "capability": (step.get("result") or {}).get("capability")
                if isinstance(step.get("result"), dict)
                else None,
            }
            for step in steps
        ],
        "error_path": [
            {
                "action": step.get("action"),
                "result": step.get("result"),
            }
            for step in steps
            if step.get("action") == "no_progress"
            or (
                isinstance(step.get("result"), dict)
                and step["result"].get("type") in {"business_action_error", "tool_validation_error"}
            )
        ],
    }


def run(rounds: int, case_id: str | None = None) -> dict[str, Any]:
    service = AgentWorkbenchService("civil")
    selected_cases = tuple(case for case in CASES if not case_id or case.case_id == case_id)
    if not selected_cases:
        raise ValueError(f"Unknown benchmark case: {case_id}")
    results = [
        run_case(service, case, round_number=round_number)
        for round_number in range(1, rounds + 1)
        for case in selected_cases
    ]
    successes = sum(1 for result in results if result["success"])
    total = len(results)
    report = {
        "ok": successes >= max(1, total - 1),
        "target": "at least 19/20 for the default four rounds",
        "total": total,
        "successes": successes,
        "success_rate": round(successes / total, 4) if total else 0,
        "average_steps": round(statistics.fmean(result["step_count"] for result in results), 2),
        "average_elapsed_ms": round(statistics.fmean(result["elapsed_ms"] for result in results), 2),
        "total_repairs": sum(result["repair_count"] for result in results),
        "total_repeats": sum(result["repeat_count"] for result in results),
        "total_bypass_attempts": sum(result["bypass_attempts"] for result in results),
        "results": results,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = [result for result in results if not result["success"]]
    if failures:
        candidates = {
            "generated_at": datetime.now().astimezone().isoformat(),
            "source_report": str(REPORT_PATH),
            "review_required": True,
            "instructions": "Confirm the expected behavior and root cause before promoting a case into tests/fixtures/agent_runtime_failure_cases.json.",
            "cases": failures,
        }
        FAILURE_CANDIDATES_PATH.write_text(
            json.dumps(candidates, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        FAILURE_CANDIDATES_PATH.unlink(missing_ok=True)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the real-DeepSeek Capability Runtime stability benchmark.")
    parser.add_argument("--rounds", type=int, default=4, help="Run all five scenarios this many times.")
    parser.add_argument("--case", choices=[case.case_id for case in CASES], help="Run one scenario only.")
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be at least 1")
    load_dotenv(ROOT / ".env")
    report = run(args.rounds, args.case)
    print(json.dumps({key: value for key, value in report.items() if key != "results"}, ensure_ascii=False, indent=2))
    print(f"report: {REPORT_PATH}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
