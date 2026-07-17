from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.agent_runtime import ToolGateway, ToolSession, make_tool_access_policy  # noqa: E402
from nexterp_agent.erpnext import ERPNextAdapter  # noqa: E402
from nexterp_agent.item_master import ReleaseMaterialResolver  # noqa: E402
from nexterp_agent.master_data import MasterDataRelease  # noqa: E402
from nexterp_agent.workbench.server import AgentWorkbenchService, employee_catalog  # noqa: E402


REPORT_PATH = ROOT / "data" / "runtime" / "employee_role_smoke_report.json"
PROJECT_CODE = "PRJ-HL-13"
WAREHOUSES = ("合流1.3标仓库 - SD", "蕰川路基地仓库 - SD")

EXPECTED_TOOLS = {
    "manager_agent": ("erpnext.accounting.accounts_payable",),
    "material_equipment_agent": (
        "erpnext.buying.create_purchase_order_draft",
        "erpnext.stock.create_transfer_draft",
    ),
    "operations_agent": ("erpnext.buying.run_purchase_analysis",),
    "project_agent": ("erpnext.projects.create_material_issue_draft",),
    "technical_agent": ("erpnext.stock.get_balance",),
    "material_clerk_agent": ("erpnext.buying.create_material_request_draft",),
    "finance_agent": ("erpnext.accounting.accounts_payable",),
}

BLOCKED_TOOLS = {
    "operations_agent": ("erpnext.buying.create_purchase_order_draft",),
    "technical_agent": ("erpnext.projects.create_material_issue_draft",),
    "material_clerk_agent": ("erpnext.buying.create_purchase_order_draft",),
    "finance_agent": ("erpnext.buying.create_purchase_order_draft",),
}


def _record(checks: dict[str, Any], name: str, ok: bool, **detail: Any) -> None:
    checks[name] = {"ok": bool(ok), **detail}


def run() -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    service = AgentWorkbenchService("civil")
    release = MasterDataRelease()
    employees = [row for row in employee_catalog() if row.get("user_email")]
    checks: dict[str, Any] = {}

    bootstrap = service.bootstrap()
    _record(
        checks,
        "workbench_bootstrap",
        len(bootstrap.get("projects") or []) >= 8 and len(bootstrap.get("employees") or []) >= 7,
        project_count=len(bootstrap.get("projects") or []),
        employee_count=len(bootstrap.get("employees") or []),
    )

    role_results = []
    for employee in employees:
        user = str(employee["user_email"])
        profile = str(employee.get("profile") or "")
        client = service.client(user)
        identity = client.get_logged_user()
        identity_ok = identity.ok and identity.data == user
        policy = make_tool_access_policy(profile)
        expected = EXPECTED_TOOLS.get(profile, ())
        blocked = BLOCKED_TOOLS.get(profile, ())
        policy_ok = all(policy.decide(tool).allowed for tool in expected)
        blocked_ok = all(not policy.decide(tool).allowed for tool in blocked)
        developer_blocked = not policy.decide("erpnext.delete_document").allowed

        inbox_error = ""
        document_errors: list[str] = []
        inbox_count = 0
        try:
            inbox_count = int(service.inbox(user, PROJECT_CODE, limit=10).get("count") or 0)
        except Exception as exc:  # noqa: BLE001 - acceptance report must retain ERP error text
            inbox_error = str(exc)
        for module in ("buying", "stock", "accounting", "projects"):
            try:
                payload = service.documents(user, PROJECT_CODE, module=module, page_size=5)
                for module_row in payload.get("modules") or []:
                    for group in module_row.get("groups") or []:
                        if group.get("error") and "权限" not in str(group["error"]):
                            document_errors.append(f"{module}/{group.get('doctype')}: {group['error']}")
            except Exception as exc:  # noqa: BLE001
                document_errors.append(f"{module}: {exc}")

        gateway = ToolGateway(
            ERPNextAdapter(client),
            ToolSession(user=user, policy=policy, verify_erpnext_identity=True),
        )
        if blocked:
            denied = gateway.execute({"tool": blocked[0], "arguments": {}})
            blocked_ok = blocked_ok and not denied.ok and denied.error_type == "permission_error"

        role_ok = identity_ok and policy_ok and blocked_ok and developer_blocked and not inbox_error and not document_errors
        role_results.append(
            {
                "employee": employee.get("employee_name"),
                "position": employee.get("position"),
                "user": user,
                "profile": profile,
                "identity_ok": identity_ok,
                "allowed_tool_count": len(policy.allowed_schema_names()),
                "expected_tools_ok": policy_ok,
                "blocked_tools_ok": blocked_ok,
                "developer_tools_blocked": developer_blocked,
                "inbox_count": inbox_count,
                "inbox_error": inbox_error,
                "document_errors": document_errors,
                "ok": role_ok,
            }
        )
    _record(checks, "employee_roles", all(row["ok"] for row in role_results), roles=role_results)

    resolver = ReleaseMaterialResolver(release.material_release_path)
    ambiguous = resolver.resolve("帆布手套", limit=10)
    exact = resolver.resolve("MAT-CEM-000008", limit=5)
    missing = resolver.resolve("不存在的验收专用物料XYZ", limit=5)
    _record(
        checks,
        "material_resolution",
        len(ambiguous.get("candidates") or []) >= 2
        and exact.get("status") == "ready"
        and not (missing.get("candidates") or []),
        ambiguous_status=ambiguous.get("status"),
        ambiguous_candidates=[row.get("item_code") for row in ambiguous.get("candidates") or []],
        exact_item=(exact.get("resolved") or {}).get("item_code"),
        missing_status=missing.get("status"),
    )

    stock_user = "pan.feng@stec-up.local"
    candidate_codes = [str(row.get("item_code") or "") for row in ambiguous.get("candidates") or [] if row.get("item_code")]
    stock = service.client(stock_user).search_documents(
        "Bin",
        filters={"item_code": ["in", candidate_codes], "warehouse": ["in", list(WAREHOUSES)]},
        fields=["item_code", "warehouse", "actual_qty", "reserved_qty", "projected_qty"],
        limit=200,
    )
    stock_rows = stock.data if stock.ok and isinstance(stock.data, list) else []
    _record(
        checks,
        "candidate_inventory_batch",
        stock.ok,
        candidate_count=len(candidate_codes),
        query_count=1,
        returned_rows=len(stock_rows),
        nonzero_rows=sum(1 for row in stock_rows if float(row.get("actual_qty") or 0) != 0),
    )

    result = {
        "executed_at": datetime.now().astimezone().isoformat(),
        "project": PROJECT_CODE,
        "ok": all(entry["ok"] for entry in checks.values()),
        "checks": checks,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    payload = run()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(0 if payload["ok"] else 1)
