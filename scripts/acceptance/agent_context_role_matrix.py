from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.agent_runtime import make_tool_access_policy  # noqa: E402
from nexterp_agent.capability_service.context import AgentContextBuilder  # noqa: E402
from nexterp_agent.capability_service.catalog import ExternalIdentity  # noqa: E402
from nexterp_agent.capability_service.role_catalog import ROLE_CAPABILITY_LINKS  # noqa: E402
from nexterp_agent.workbench.openclaw_runtime import (  # noqa: E402
    workbench_external_subject,
    workbench_session_key,
)
from nexterp_agent.workbench.server import AgentWorkbenchService, employee_catalog, project_catalog  # noqa: E402


REPORT_PATH = ROOT / "data" / "runtime" / "agent_context_role_matrix_report.json"
PROJECT_CODE = "PRJ-HL-13"
DEFAULT_QUESTION = "物料表里有没有14的钻头？如果缺货，按我的岗位说明下一步该找谁配合。"
ROLE_USERS = (
    "zhang.zhenguang@stec-up.local",
    "fang.wenqian@stec-up.local",
    "hu.yinhu@stec-up.local",
    "mao.xiaoquan@stec-up.local",
)
WRITE_CAPABILITIES = {
    "cap.material_request",
    "cap.request_for_quotation",
    "cap.supplier_quotation",
    "cap.purchase_order",
    "cap.purchase_receipt",
    "cap.purchase_return",
}


def _allowed_projects(user: str) -> list[str]:
    return [
        row["project_code"]
        for row in project_catalog()
        if user in {person["user_email"] for person in row.get("employees") or []}
    ]


def _identity(employee: dict[str, Any], allowed_projects: list[str]) -> ExternalIdentity:
    return ExternalIdentity(
        external_subject=workbench_external_subject(str(employee["user_email"])),
        agent_id="main",
        employee_user=str(employee["user_email"]),
        profile_name=str(employee["profile"]),
        default_project=PROJECT_CODE,
        allowed_projects=tuple(allowed_projects),
    )


def deterministic_snapshot(service: AgentWorkbenchService, employee: dict[str, Any]) -> dict[str, Any]:
    user = str(employee["user_email"])
    allowed_projects = _allowed_projects(user)
    identity = _identity(employee, allowed_projects)
    envelope = AgentContextBuilder(ROOT).build(identity, {
        "project_code": PROJECT_CODE,
        "current_goal": DEFAULT_QUESTION,
        "intent_mode": "read",
    })
    role_context = service.capability_repository.role_context(
        envelope.identity.role_code,
        ["responsibilities", "collaboration"],
    )
    logged_user = service.client(user).get_logged_user()
    policy = make_tool_access_policy(str(employee["profile"]))
    related_capabilities = ROLE_CAPABILITY_LINKS.get(envelope.identity.role_code, ())
    checks = {
        "erpnext_identity": logged_user.ok and logged_user.data == user,
        "trusted_employee": envelope.identity.employee_user == user,
        "trusted_project": envelope.workplace.project_code == PROJECT_CODE,
        "role_profile_loaded": role_context["profile"]["role_code"] == envelope.identity.role_code,
        "responsibilities_loaded": bool(role_context["responsibilities"]),
        "role_capabilities_linked": bool(related_capabilities),
        "developer_tool_blocked": not policy.decide("erpnext.delete_document").allowed,
    }
    return {
        "employee": envelope.identity.employee_name,
        "user": user,
        "position": envelope.identity.project_position,
        "role_code": envelope.identity.role_code,
        "project": envelope.workplace.project_short_name,
        "warehouse": envelope.workplace.warehouse_name,
        "mission": role_context["profile"]["mission"],
        "boundaries": role_context["profile"]["boundaries"],
        "responsibilities": [row["label"] for row in role_context["responsibilities"]],
        "related_capabilities": list(related_capabilities),
        "allowed_tool_count": len(policy.allowed_schema_names()),
        "checks": checks,
        "ok": all(checks.values()),
    }


def live_snapshot(
    service: AgentWorkbenchService,
    employee: dict[str, Any],
    *,
    question: str,
    run_id: str,
) -> dict[str, Any]:
    user = str(employee["user_email"])
    result = service.run({
        "user": user,
        "project_code": PROJECT_CODE,
        "conversation_id": f"role-matrix-{run_id}-{employee['employee_code'].lower()}",
        "text": question,
    })
    loaded_nodes = [
        str(row.get("node_id") or "")
        for row in result.get("loaded_nodes") or []
        if isinstance(row, dict)
    ]
    tool_calls = result.get("tool_calls") or []
    checks = {
        "completed_without_write": result.get("status") == "completed",
        "no_confirmation": not result.get("pending_id") and not result.get("pending_tool_call"),
        "no_execute_tool": all(
            row.get("tool") != "nexterp_execute_prepared_operation"
            for row in tool_calls if isinstance(row, dict)
        ),
        "no_write_capability": not WRITE_CAPABILITIES.intersection(loaded_nodes),
        "has_answer": bool(str(result.get("message") or "").strip()),
    }
    return {
        "status": result.get("status"),
        "message": result.get("message"),
        "duration_ms": result.get("duration_ms"),
        "loaded_context": result.get("loaded_context") or [],
        "loaded_nodes": loaded_nodes,
        "tool_calls": [row.get("tool") for row in tool_calls if isinstance(row, dict)],
        "checks": checks,
        "ok": all(checks.values()),
    }


def run(*, live: bool = False, question: str = DEFAULT_QUESTION) -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    service = AgentWorkbenchService("civil")
    employees = {row["user_email"]: row for row in employee_catalog()}
    run_id = uuid4().hex[:10]
    rows = []
    for user in ROLE_USERS:
        employee = employees[user]
        row = deterministic_snapshot(service, employee)
        if live:
            row["live"] = live_snapshot(service, employee, question=question, run_id=run_id)
            row["ok"] = row["ok"] and row["live"]["ok"]
        rows.append(row)
    result = {
        "executed_at": datetime.now().astimezone().isoformat(),
        "mode": "live" if live else "deterministic",
        "question": question,
        "project_code": PROJECT_CODE,
        "ok": all(row["ok"] for row in rows),
        "roles": rows,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate trusted role context without writing ERPNext data")
    parser.add_argument("--live", action="store_true", help="also run the same read-only prompt through DeepSeek")
    parser.add_argument("--question", default=DEFAULT_QUESTION)
    args = parser.parse_args()
    result = run(live=args.live, question=args.question)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
