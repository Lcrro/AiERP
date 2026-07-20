from __future__ import annotations

import argparse
from collections import Counter
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
    expected_tool: str
    mode: str
    accepted_statuses: tuple[str, ...]
    allow_resolver_inventory: bool = False


CASES = (
    BenchmarkCase(
        "material_request_preview",
        "mao.xiaoquan@stec-up.local",
        "为合流1.3标创建材料申请：物料 MAT-CEM-000008，20包，送合流1.3标仓库，需求日期2026-07-25。",
        "material_request.create",
        "erpnext.buying.create_material_request_draft",
        "preview",
        ("needs_confirmation",),
    ),
    BenchmarkCase(
        "stock_balance_query",
        "mao.xiaoquan@stec-up.local",
        "查询物料 MAT-CEM-000008 在合流1.3标仓库的实时库存。",
        "stock.balance.query",
        "erpnext.stock.get_item_locations",
        "read",
        ("completed",),
        allow_resolver_inventory=True,
    ),
    BenchmarkCase(
        "project_task_preview",
        "hu.yinhu@stec-up.local",
        "为合流1.3标创建任务：检查开工材料，优先级High，计划2026-07-21开始，2026-07-23完成。",
        "project.task.create",
        "erpnext.projects.create_task",
        "preview",
        ("needs_confirmation",),
    ),
    BenchmarkCase(
        "project_cost_query",
        "hu.yinhu@stec-up.local",
        "查询合流1.3标从2026-07-01到2026-07-20的项目成本。",
        "project.cost.query",
        "erpnext.projects.get_project_cost_context",
        "read",
        ("completed",),
    ),
    BenchmarkCase(
        "accounts_payable_query",
        "fang.wenqian@stec-up.local",
        "查询 STEC (Demo) 截至2026-07-20的应付账款。",
        "finance.accounts_payable.query",
        "erpnext.accounting.accounts_payable",
        "read",
        ("completed",),
    ),
)


def _selected_capabilities(steps: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for step in steps:
        result = step.get("result") if isinstance(step.get("result"), dict) else {}
        prepared = result.get("prepared_action") if isinstance(result.get("prepared_action"), dict) else {}
        candidates = (result.get("capability"), prepared.get("capability"))
        for value in candidates:
            text = str(value or "").strip()
            if text and text not in values:
                values.append(text)
    return values


def _executed_tools(steps: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for step in steps:
        if step.get("action") != "execute_tool" or not isinstance(step.get("payload"), dict):
            continue
        payload = step["payload"]
        value = str(payload.get("tool") or (payload.get("tool_call") or {}).get("tool") or "").strip()
        if value and value not in values:
            values.append(value)
    return values


def _has_resolver_inventory_evidence(steps: list[dict[str, Any]]) -> bool:
    return any(
        step.get("action") == "resolve_entities"
        and isinstance(step.get("result"), dict)
        and step["result"].get("type") == "resolve_entities"
        and isinstance(step["result"].get("inventory_query"), dict)
        and step["result"]["inventory_query"].get("status") == "completed"
        for step in steps
    )


def _repair_category(step: dict[str, Any]) -> str | None:
    result = step.get("result") if isinstance(step.get("result"), dict) else {}
    result_type = str(result.get("type") or "")
    if result_type == "tool_validation_error":
        return "tool_schema"
    if result_type != "business_action_error":
        return None
    error = str(result.get("error") or "")
    if "Resolver" in error or "resolve_entities" in error or "真实值" in error:
        return "resolver_required"
    if result.get("questions") or any(token in error for token in ("缺少", "不能为空", "required")):
        return "missing_field"
    if any(token in error for token in ("状态不能", "不一致", "失效", "不能超过", "尚未提交")):
        return "business_precondition"
    return "business_validation"


def _failure_category(
    *,
    result: dict[str, Any],
    case: BenchmarkCase,
    selected_capabilities: list[str],
    executed_tools: list[str],
    resolver_inventory_evidence: bool,
    bypass_attempts: int,
) -> str:
    if bypass_attempts:
        return "capability_bypass"
    status = str(result.get("status") or "")
    message = str(result.get("message") or "")
    if status == "failed":
        lowered = message.lower()
        if any(token in lowered for token in ("network", "timeout", "deepseek", "连接", "服务不可用")):
            return "external_service"
        if any(token in message for token in ("步数", "上限", "无进展", "重复")):
            return "planner_non_convergence"
        return "runtime_failed"
    if status not in case.accepted_statuses:
        return "unexpected_status"
    if case.allow_resolver_inventory and resolver_inventory_evidence:
        return "none"
    if case.expected_capability not in selected_capabilities:
        return "capability_not_selected"
    if case.mode == "read" and case.expected_tool not in executed_tools:
        return "tool_not_executed"
    pending = result.get("pending_tool_call") if isinstance(result.get("pending_tool_call"), dict) else {}
    if case.mode == "preview" and pending.get("tool") != case.expected_tool:
        return "wrong_pending_tool"
    return "none"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * percentile + 0.999999)))
    return round(float(ordered[index]), 2)


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    successes = sum(1 for result in results if result["success"])
    per_case: dict[str, Any] = {}
    for case_id in sorted({str(result["case_id"]) for result in results}):
        rows = [result for result in results if result["case_id"] == case_id]
        case_successes = sum(1 for row in rows if row["success"])
        per_case[case_id] = {
            "total": len(rows),
            "successes": case_successes,
            "success_rate": round(case_successes / len(rows), 4),
            "clean_successes": sum(1 for row in rows if row["outcome"] == "clean_success"),
            "recovered_successes": sum(1 for row in rows if row["outcome"] == "recovered_success"),
            "failure_categories": dict(Counter(row["failure_category"] for row in rows if not row["success"])),
            "average_steps": round(statistics.fmean(row["step_count"] for row in rows), 2),
            "p50_elapsed_ms": _percentile([row["elapsed_ms"] for row in rows], 0.50),
            "p95_elapsed_ms": _percentile([row["elapsed_ms"] for row in rows], 0.95),
            "total_repairs": sum(row["repair_count"] for row in rows),
            "total_repeats": sum(row["repeat_count"] for row in rows),
        }
    return {
        "total": total,
        "successes": successes,
        "success_rate": round(successes / total, 4) if total else 0,
        "clean_successes": sum(1 for result in results if result["outcome"] == "clean_success"),
        "recovered_successes": sum(1 for result in results if result["outcome"] == "recovered_success"),
        "failure_categories": dict(Counter(result["failure_category"] for result in results if not result["success"])),
        "status_counts": dict(Counter(str(result.get("status") or "unknown") for result in results)),
        "average_steps": round(statistics.fmean(result["step_count"] for result in results), 2) if total else 0,
        "p50_steps": _percentile([result["step_count"] for result in results], 0.50),
        "p95_steps": _percentile([result["step_count"] for result in results], 0.95),
        "average_elapsed_ms": round(statistics.fmean(result["elapsed_ms"] for result in results), 2) if total else 0,
        "p50_elapsed_ms": _percentile([result["elapsed_ms"] for result in results], 0.50),
        "p95_elapsed_ms": _percentile([result["elapsed_ms"] for result in results], 0.95),
        "total_repairs": sum(result["repair_count"] for result in results),
        "repair_categories": dict(
            Counter(category for result in results for category in result.get("repair_categories") or [])
        ),
        "total_repeats": sum(result["repeat_count"] for result in results),
        "total_bypass_attempts": sum(result["bypass_attempts"] for result in results),
        "per_case": per_case,
    }


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
    capabilities = _selected_capabilities(steps)
    executed_tools = _executed_tools(steps)
    resolver_inventory_evidence = _has_resolver_inventory_evidence(steps)
    bypass_attempts = _count_observation(steps, "capability_required")
    repair_categories = [category for step in steps if (category := _repair_category(step))]
    repairs = len(repair_categories)
    repeats = sum(1 for step in steps if step.get("action") == "no_progress")
    failure_category = _failure_category(
        result=result,
        case=case,
        selected_capabilities=capabilities,
        executed_tools=executed_tools,
        resolver_inventory_evidence=resolver_inventory_evidence,
        bypass_attempts=bypass_attempts,
    )
    success = failure_category == "none"
    outcome = "recovered_success" if success and (repairs or repeats) else "clean_success" if success else "failed"
    service.reset_session(case.user, PROJECT_CODE, conversation_id)
    return {
        "case_id": case.case_id,
        "round": round_number,
        "success": success,
        "status": result.get("status"),
        "message": result.get("message"),
        "expected_capability": case.expected_capability,
        "expected_tool": case.expected_tool,
        "mode": case.mode,
        "selected_capabilities": capabilities,
        "executed_tools": executed_tools,
        "resolver_inventory_evidence": resolver_inventory_evidence,
        "execution_evidence": (
            "resolver_inventory"
            if resolver_inventory_evidence and case.allow_resolver_inventory
            else "pending_tool_call"
            if case.mode == "preview" and isinstance(result.get("pending_tool_call"), dict)
            else "execute_tool"
            if case.expected_tool in executed_tools
            else "none"
        ),
        "pending_tool": (result.get("pending_tool_call") or {}).get("tool")
        if isinstance(result.get("pending_tool_call"), dict)
        else None,
        "outcome": outcome,
        "failure_category": failure_category,
        "step_count": len(steps),
        "repair_count": repairs,
        "repair_categories": repair_categories,
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
    summary = summarize_results(results)
    total = summary["total"]
    minimum_successes = max(1, total - 1)
    report = {
        "ok": summary["successes"] >= minimum_successes and summary["total_bypass_attempts"] == 0,
        "benchmark_version": "2",
        "generated_at": datetime.now().astimezone().isoformat(),
        "target": f"at least {minimum_successes}/{total}, with no capability bypass",
        **summary,
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
