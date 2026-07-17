from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextAdapter  # noqa: E402
from nexterp_agent.workbench.server import AgentWorkbenchService  # noqa: E402


REPORT_PATH = ROOT / "data" / "runtime" / "material_request_rejection_report.json"
PROJECT_CODE = "PRJ-HL-13"
ERP_PROJECT = "PROJ-0010"
WAREHOUSE = "合流1.3标仓库 - SD"
ITEM_CODE = "MAT-CEM-000008"
USERS = {
    "clerk": "mao.xiaoquan@stec-up.local",
    "manager": "pan.feng@stec-up.local",
    "technical": "lin.qiaohang@stec-up.local",
    "project_manager": "hu.yinhu@stec-up.local",
}


def _require(result: Any, label: str) -> dict[str, Any]:
    if not result.ok or not isinstance(result.data, dict):
        raise RuntimeError(result.user_message or result.error or f"{label}失败")
    return result.data


def _contains(inbox: dict[str, Any], name: str) -> bool:
    return any(row.get("reference_name") == name for row in inbox.get("items") or [])


def run() -> dict[str, Any]:
    load_dotenv(ROOT / ".env")
    service = AgentWorkbenchService("civil")
    clerk = USERS["clerk"]
    adapter = ERPNextAdapter(service.client(clerk))
    created = _require(
        adapter.execute(
            {
                "tool": "erpnext.buying.create_material_request_draft",
                "arguments": {
                    "company": "STEC (Demo)",
                    "material_request_type": "Purchase",
                    "transaction_date": date.today().isoformat(),
                    "schedule_date": (date.today() + timedelta(days=3)).isoformat(),
                    "items": [
                        {
                            "item_code": ITEM_CODE,
                            "qty": 2,
                            "uom": "包",
                            "warehouse": WAREHOUSE,
                            "project": ERP_PROJECT,
                            "rate": 28,
                        }
                    ],
                },
            }
        ),
        "创建驳回测试申请",
    )
    name = str(created["name"])
    checks: dict[str, bool] = {}
    try:
        service.apply_workflow_action(clerk, "Material Request", name, "提交申请", project=PROJECT_CODE)
        checks["manager_received_inbox"] = _contains(service.inbox(USERS["manager"], PROJECT_CODE), name)
        checks["technical_not_in_inbox"] = not _contains(service.inbox(USERS["technical"], PROJECT_CODE), name)

        unauthorized_rejected = False
        try:
            service.apply_workflow_action(
                USERS["technical"], "Material Request", name, "批准", project=PROJECT_CODE
            )
        except ValueError:
            unauthorized_rejected = True
        checks["non_approver_blocked"] = unauthorized_rejected

        rejection_reason = "验收测试：请补充现场用途后重新提交。"
        rejected = service.apply_workflow_action(
            USERS["manager"],
            "Material Request",
            name,
            "驳回",
            comment=rejection_reason,
            project=PROJECT_CODE,
        )
        process = rejected.get("process") or {}
        comments = process.get("comments") or []
        rejected_state = str((rejected.get("document") or {}).get("workflow_state") or "")
        checks["rejected_state"] = rejected_state in {"草稿", "已驳回", "驳回"}
        checks["rejection_reason_visible"] = any(rejection_reason in str(row.get("content") or "") for row in comments)

        actions_result = service.client(clerk).get_workflow_actions("Material Request", name)
        actions = [str(row.get("action") or "") for row in actions_result.data or []] if actions_result.ok else []
        resubmit_action = next(
            (action for action in actions if "重提" in action or "重新" in action or action == "提交申请"),
            "",
        )
        checks["resubmit_action_available"] = bool(resubmit_action)
        if resubmit_action:
            updated = service.client(clerk).update_document(
                "Material Request",
                name,
                {"schedule_date": (date.today() + timedelta(days=4)).isoformat()},
            )
            checks["rejected_document_modified"] = updated.ok
            service.apply_workflow_action(clerk, "Material Request", name, resubmit_action, project=PROJECT_CODE)
            checks["manager_received_resubmission"] = _contains(service.inbox(USERS["manager"], PROJECT_CODE), name)
        else:
            checks["rejected_document_modified"] = False
            checks["manager_received_resubmission"] = False
    finally:
        detail = service.client(clerk).get_document("Material Request", name)
        if detail.ok and int((detail.data or {}).get("docstatus") or 0) == 1:
            service.client(clerk).cancel_document("Material Request", name)
        else:
            service.client(clerk).call_method("frappe.client.delete", {"doctype": "Material Request", "name": name})

    report = {
        "executed_at": date.today().isoformat(),
        "document": name,
        "checks": checks,
        "ok": all(checks.values()),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
