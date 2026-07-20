from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys
import time
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.workbench.server import AgentWorkbenchService  # noqa: E402


DEFAULT_CASES = ROOT / "data" / "evals" / "finance_agent_cases.json"
DEFAULT_REPORT = ROOT / "data" / "runtime" / "finance_agent_eval_report.json"


def load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {"id", "user", "project_code", "erpnext_project", "warehouse", "text", "expected_status"}
    if not isinstance(payload, list) or not payload:
        raise ValueError("评测集必须是非空 JSON 数组。")
    for index, case in enumerate(payload, start=1):
        if not isinstance(case, dict) or not required.issubset(case):
            raise ValueError(f"第 {index} 个案例缺少必要字段。")
    return payload


def evaluate_case(service: AgentWorkbenchService, case: dict[str, Any]) -> dict[str, Any]:
    conversation_id = f"eval-{case['id']}"
    user = str(case["user"])
    project_code = str(case["project_code"])
    service.reset_session(user, project_code, conversation_id)
    runtime = service.runtime(service.scoped_session_store(user, project_code, conversation_id))
    started = time.perf_counter()
    try:
        result = runtime.run_once(
            str(case["text"]),
            user=user,
            today=date.today(),
            request_id=f"eval-{case['id']}-{date.today().isoformat()}",
            context={
                "project_code": project_code,
                "erpnext_project": case["erpnext_project"],
                "warehouse": case["warehouse"],
            },
        )
    finally:
        elapsed_ms = round((time.perf_counter() - started) * 1000)
    payload = result.to_dict()
    checks = {
        "status": payload.get("status") in case["expected_status"],
        "questions": not case.get("must_ask_question") or bool(payload.get("questions")),
        "no_write": payload.get("pending_tool_call") is None,
    }
    planner_steps = [step for step in payload.get("steps") or [] if step.get("label") == "DeepSeek规划"]
    service.reset_session(user, project_code, conversation_id)
    return {
        "id": case["id"],
        "ok": all(checks.values()),
        "checks": checks,
        "status": payload.get("status"),
        "message": payload.get("message"),
        "planner_steps": len(planner_steps),
        "planner_actions": [step.get("action") for step in planner_steps],
        "elapsed_ms": elapsed_ms,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run non-writing DeepSeek finance Agent evaluations.")
    parser.add_argument("command", choices=["validate", "run"])
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    cases = load_cases(args.cases)
    if args.case_ids:
        wanted = set(args.case_ids)
        cases = [case for case in cases if case["id"] in wanted]
        missing = wanted.difference(case["id"] for case in cases)
        if missing:
            raise ValueError(f"未知案例：{', '.join(sorted(missing))}")
    if args.command == "validate":
        print(json.dumps({"ok": True, "case_count": len(cases), "case_ids": [case["id"] for case in cases]}, ensure_ascii=False, indent=2))
        return 0
    load_dotenv(ROOT / ".env")
    service = AgentWorkbenchService("civil")
    results = [evaluate_case(service, case) for case in cases]
    report = {
        "ok": all(result["ok"] for result in results),
        "case_count": len(results),
        "passed": sum(1 for result in results if result["ok"]),
        "results": results,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
