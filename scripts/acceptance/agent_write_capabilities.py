from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
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

from nexterp_agent.erpnext import ERPNextAdapter  # noqa: E402
from nexterp_agent.workbench.server import AgentWorkbenchService  # noqa: E402


REPORT_PATH = ROOT / "data" / "runtime" / "agent_write_capabilities_report.json"
LAST_REPORT_PATH = ROOT / "data" / "runtime" / "agent_write_capabilities_last_report.json"
PROJECT_CODE = "PRJ-HL-13"
ERP_PROJECT = "PROJ-0010"
WAREHOUSE = "合流1.3标仓库 - SD"
COMPANY = "STEC (Demo)"
ITEM_CODE = "MAT-CEM-000008"
SUPPLIER = "测试建材供应商甲"
USERS = {
    "project_manager": "hu.yinhu@stec-up.local",
    "buying_manager": "pan.feng@stec-up.local",
    "finance": "fang.wenqian@stec-up.local",
}


def _save(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load() -> dict[str, Any]:
    if not REPORT_PATH.exists():
        raise RuntimeError("没有写入验收报告，请先运行 prepare 或 run。")
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def _require_tool(result: Any, label: str) -> dict[str, Any]:
    if not result.ok:
        raise RuntimeError(result.user_message or result.error or f"{label}失败")
    if not isinstance(result.data, dict) or not result.data.get("name"):
        raise RuntimeError(f"{label}未返回单据名称")
    return result.data


def _context() -> dict[str, str]:
    return {
        "project_code": PROJECT_CODE,
        "erpnext_project": ERP_PROJECT,
        "warehouse": WAREHOUSE,
    }


def _agent_write(
    service: AgentWorkbenchService,
    *,
    user: str,
    conversation_id: str,
    text: str,
    run_id: str,
) -> dict[str, Any]:
    service.reset_session(user, PROJECT_CODE, conversation_id)
    runtime = service.runtime(service.scoped_session_store(user, PROJECT_CODE, conversation_id))
    preview = runtime.run_once(
        text,
        user=user,
        today=date.today(),
        request_id=f"{run_id}-preview-{conversation_id}",
        context=_context(),
    ).to_dict()
    if preview.get("status") != "needs_confirmation" or not preview.get("pending_tool_call"):
        raise RuntimeError(
            f"Agent 未生成待确认写操作：status={preview.get('status')}, message={preview.get('message')}"
        )
    confirmed = runtime.run_once(
        "确认执行",
        user=user,
        execute=True,
        today=date.today(),
        request_id=f"{run_id}-confirm-{conversation_id}",
        context=_context(),
    ).to_dict()
    tool_result = confirmed.get("tool_result") or {}
    if confirmed.get("status") != "completed" or not tool_result.get("ok"):
        raise RuntimeError(
            f"Agent 写操作失败：status={confirmed.get('status')}, message={confirmed.get('message')}"
        )
    return {
        "preview": preview,
        "confirmed": confirmed,
        "tool_call": preview["pending_tool_call"],
        "tool_result": tool_result,
    }


def _append_document(
    report: dict[str, Any],
    *,
    doctype: str,
    name: str,
    user: str,
    purpose: str,
) -> None:
    report.setdefault("documents", []).append(
        {"doctype": doctype, "name": name, "user": user, "purpose": purpose}
    )
    _save(report)


def prepare(service: AgentWorkbenchService) -> dict[str, Any]:
    run_id = f"agent-e2e-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    checks: dict[str, bool] = {}
    for role, user in USERS.items():
        identity = service.client(user).get_logged_user()
        checks[f"identity:{role}"] = identity.ok and identity.data == user
    manager = service.client(USERS["buying_manager"])
    for doctype, name in (
        ("Project", ERP_PROJECT),
        ("Warehouse", WAREHOUSE),
        ("Item", ITEM_CODE),
        ("Supplier", SUPPLIER),
    ):
        exists = manager.document_exists(doctype, name)
        exists_value = exists.data.get("exists") if isinstance(exists.data, dict) else exists.data
        checks[f"{doctype}:{name}"] = exists.ok and bool(exists_value)
    if not all(checks.values()):
        raise RuntimeError(f"写入验收主数据或身份未就绪：{checks}")

    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": datetime.now().astimezone().isoformat(),
        "checks": checks,
        "documents": [],
        "cases": {},
    }
    _save(report)

    adapter = ERPNextAdapter(manager)
    schedule_date = (date.today() + timedelta(days=3)).isoformat()
    order = _require_tool(
        adapter.execute(
            {
                "tool": "erpnext.buying.create_purchase_order_draft",
                "arguments": {
                    "supplier": SUPPLIER,
                    "transaction_date": date.today().isoformat(),
                    "schedule_date": schedule_date,
                    "company": COMPANY,
                    "terms": f"{run_id} 可重复 Agent 写入验收来源单据。",
                    "items": [
                        {
                            "item_code": ITEM_CODE,
                            "qty": 1,
                            "uom": "包",
                            "rate": 28,
                            "warehouse": WAREHOUSE,
                            "schedule_date": schedule_date,
                            "project": ERP_PROJECT,
                        }
                    ],
                },
            }
        ),
        "创建采购订单夹具",
    )
    order_name = str(order["name"])
    _append_document(
        report,
        doctype="Purchase Order",
        name=order_name,
        user=USERS["buying_manager"],
        purpose="fixture",
    )
    submitted_order = manager.submit_document("Purchase Order", order_name)
    if not submitted_order.ok:
        raise RuntimeError(submitted_order.user_message or submitted_order.error or "提交采购订单夹具失败")

    receipt = _require_tool(
        adapter.execute(
            {
                "tool": "erpnext.buying.create_purchase_receipt_from_purchase_order_draft",
                "arguments": {
                    "purchase_order": order_name,
                    "posting_date": date.today().isoformat(),
                    "selected_items": [{"item_code": ITEM_CODE, "qty": 1, "warehouse": WAREHOUSE}],
                },
            }
        ),
        "创建采购收货夹具",
    )
    receipt_name = str(receipt["name"])
    _append_document(
        report,
        doctype="Purchase Receipt",
        name=receipt_name,
        user=USERS["buying_manager"],
        purpose="fixture",
    )
    submitted_receipt = manager.submit_document("Purchase Receipt", receipt_name)
    if not submitted_receipt.ok:
        raise RuntimeError(submitted_receipt.user_message or submitted_receipt.error or "提交采购收货夹具失败")

    report["fixture"] = {"purchase_order": order_name, "purchase_receipt": receipt_name}
    _save(report)
    return {"ok": True, "run_id": run_id, "checks": checks, "fixture": report["fixture"]}


def run_project(service: AgentWorkbenchService, report: dict[str, Any]) -> dict[str, Any]:
    run_id = str(report["run_id"])
    subject = f"AGENT-E2E 项目任务 {run_id}"
    result = _agent_write(
        service,
        user=USERS["project_manager"],
        conversation_id=f"{run_id}-project-task",
        text=(
            f"请在当前合流项目创建任务，任务名称是“{subject}”，"
            f"开始日期为{(date.today() + timedelta(days=1)).isoformat()}，"
            f"结束日期为{(date.today() + timedelta(days=2)).isoformat()}，优先级高。"
        ),
        run_id=run_id,
    )
    data = result["tool_result"].get("data") or {}
    task_name = str(data.get("name") or "")
    if not task_name:
        raise RuntimeError("项目任务验收未返回 Task 名称")
    task = service.client(USERS["project_manager"]).get_document("Task", task_name)
    checks = {
        "tool": result["tool_call"].get("tool") == "erpnext.projects.create_task",
        "task_exists": task.ok,
        "subject_marker": task.ok and str(task.data.get("subject") or "") == subject,
        "project": task.ok and task.data.get("project") == ERP_PROJECT,
        "readback_verification": bool(
            (result["confirmed"].get("tool_result") or {}).get("verification", {}).get("ok")
        ),
    }
    report["cases"]["project_task"] = {
        "ok": all(checks.values()),
        "checks": checks,
        "document": task_name,
        "tool": result["tool_call"].get("tool"),
    }
    _append_document(
        report,
        doctype="Task",
        name=task_name,
        user=USERS["project_manager"],
        purpose="agent_project_task",
    )
    return report["cases"]["project_task"]


def run_finance(service: AgentWorkbenchService, report: dict[str, Any]) -> dict[str, Any]:
    run_id = str(report["run_id"])
    receipt = str(report.get("fixture", {}).get("purchase_receipt") or "")
    if not receipt:
        raise RuntimeError("采购收货夹具不存在")
    bill_no = f"E2E-{run_id[-13:]}"
    invoice_result = _agent_write(
        service,
        user=USERS["finance"],
        conversation_id=f"{run_id}-purchase-invoice",
        text=(
            f"请从已提交的采购收货单 {receipt} 创建采购发票草稿，"
            f"供应商发票号 {bill_no}，发票日期和入账日期都是 {date.today().isoformat()}。"
        ),
        run_id=run_id,
    )
    invoice_data = invoice_result["tool_result"].get("data") or {}
    invoice_name = str(invoice_data.get("name") or "")
    if not invoice_name:
        raise RuntimeError("采购发票验收未返回 Purchase Invoice 名称")
    _append_document(
        report,
        doctype="Purchase Invoice",
        name=invoice_name,
        user=USERS["finance"],
        purpose="agent_purchase_invoice",
    )
    finance_client = service.client(USERS["finance"])
    invoice = finance_client.get_document("Purchase Invoice", invoice_name)
    invoice_checks = {
        "tool": invoice_result["tool_call"].get("tool")
        == "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft",
        "invoice_exists": invoice.ok,
        "bill_no": invoice.ok and invoice.data.get("bill_no") == bill_no,
        "receipt_lineage": invoice.ok
        and any(row.get("purchase_receipt") == receipt for row in invoice.data.get("items") or []),
        "readback_verification": bool(
            (invoice_result["confirmed"].get("tool_result") or {}).get("verification", {}).get("ok")
        ),
    }
    if not all(invoice_checks.values()):
        raise RuntimeError(f"采购发票 Agent 验收失败：{invoice_checks}")

    submitted_invoice = finance_client.submit_document("Purchase Invoice", invoice_name)
    if not submitted_invoice.ok:
        raise RuntimeError(submitted_invoice.user_message or submitted_invoice.error or "提交采购发票夹具失败")

    payment_result = _agent_write(
        service,
        user=USERS["finance"],
        conversation_id=f"{run_id}-supplier-payment",
        text=(
            f"请从已提交的采购发票 {invoice_name} 创建全额供应商付款草稿，"
            f"付款日期 {date.today().isoformat()}，备注“{run_id} 付款验收”。"
        ),
        run_id=run_id,
    )
    payment_data = payment_result["tool_result"].get("data") or {}
    payment_name = str(payment_data.get("name") or "")
    if not payment_name:
        raise RuntimeError("付款验收未返回 Payment Entry 名称")
    _append_document(
        report,
        doctype="Payment Entry",
        name=payment_name,
        user=USERS["finance"],
        purpose="agent_supplier_payment",
    )
    payment = finance_client.get_document("Payment Entry", payment_name)
    payment_checks = {
        "tool": payment_result["tool_call"].get("tool")
        == "erpnext.accounting.create_supplier_payment_from_purchase_invoice_draft",
        "payment_exists": payment.ok,
        "invoice_reference": payment.ok
        and any(row.get("reference_name") == invoice_name for row in payment.data.get("references") or []),
        "draft_only": payment.ok and int(payment.data.get("docstatus") or 0) == 0,
        "readback_verification": bool(
            (payment_result["confirmed"].get("tool_result") or {}).get("verification", {}).get("ok")
        ),
    }
    report["cases"]["finance"] = {
        "ok": all(invoice_checks.values()) and all(payment_checks.values()),
        "invoice_checks": invoice_checks,
        "payment_checks": payment_checks,
        "purchase_invoice": invoice_name,
        "payment_entry": payment_name,
    }
    _save(report)
    return report["cases"]["finance"]


def verify(service: AgentWorkbenchService, report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = report or _load()
    document_checks: list[dict[str, Any]] = []
    for entry in report.get("documents") or []:
        detail = service.client(entry["user"]).get_document(entry["doctype"], entry["name"])
        document_checks.append(
            {
                "doctype": entry["doctype"],
                "name": entry["name"],
                "exists": detail.ok,
                "docstatus": detail.data.get("docstatus") if detail.ok and isinstance(detail.data, dict) else None,
            }
        )
    cases = report.get("cases") or {}
    expected_cases = {"project_task", "finance"}
    result = {
        "ok": expected_cases.issubset(cases) and all(bool(cases[name].get("ok")) for name in expected_cases)
        and all(row["exists"] for row in document_checks),
        "run_id": report.get("run_id"),
        "cases": cases,
        "documents": document_checks,
    }
    report["verification"] = result
    _save(report)
    return result


def cleanup(service: AgentWorkbenchService, report: dict[str, Any] | None = None) -> dict[str, Any]:
    if report is None and not REPORT_PATH.exists():
        return {"ok": True, "message": "没有写入验收 manifest，无需清理。", "removed": []}
    report = report or _load()
    removed: list[dict[str, Any]] = []
    retained_cancelled: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    users = list(dict.fromkeys([entry.get("user") for entry in report.get("documents") or []] + list(USERS.values())))

    for entry in reversed(report.get("documents") or []):
        doctype = str(entry["doctype"])
        name = str(entry["name"])
        owner = str(entry.get("user") or "")
        candidates = [user for user in [owner, *users] if user]
        detail = next(
            (result for user in candidates if (result := service.client(user).get_document(doctype, name)).ok),
            None,
        )
        if detail is None:
            continue
        docstatus = int((detail.data or {}).get("docstatus") or 0)
        if docstatus == 1:
            cancelled = False
            cancel_errors = []
            for user in candidates:
                result = service.client(user).cancel_document(doctype, name)
                if result.ok:
                    cancelled = True
                    break
                cancel_errors.append(result.user_message or result.error)
            if not cancelled:
                failed.append({"doctype": doctype, "name": name, "stage": "cancel", "errors": cancel_errors})
                continue

        deleted = False
        delete_errors = []
        for user in candidates:
            result = service.client(user).delete_document(doctype, name)
            if result.ok:
                removed.append({"doctype": doctype, "name": name})
                deleted = True
                break
            delete_errors.append(result.user_message or result.error)
        if not deleted:
            exists = any(service.client(user).get_document(doctype, name).ok for user in candidates)
            if exists and docstatus == 1:
                retained_cancelled.append({"doctype": doctype, "name": name, "errors": delete_errors})
            elif exists:
                failed.append({"doctype": doctype, "name": name, "stage": "delete", "errors": delete_errors})

    for user in USERS.values():
        for suffix in ("project-task", "purchase-invoice", "supplier-payment"):
            service.reset_session(user, PROJECT_CODE, f"{report.get('run_id')}-{suffix}")
    result = {
        "ok": not failed,
        "run_id": report.get("run_id"),
        "removed": removed,
        "retained_cancelled": retained_cancelled,
        "failed": failed,
    }
    if result["ok"]:
        REPORT_PATH.unlink(missing_ok=True)
    return result


def run_all(service: AgentWorkbenchService) -> dict[str, Any]:
    if REPORT_PATH.exists():
        previous_cleanup = cleanup(service)
        if not previous_cleanup.get("ok"):
            raise RuntimeError(f"上一次写入验收数据未能清理：{previous_cleanup}")
    prepared = prepare(service)
    report = _load()
    project = run_project(service, report)
    finance = run_finance(service, report)
    verification = verify(service, report)
    cleanup_result = cleanup(service, report)
    result = {
        "ok": bool(project.get("ok")) and bool(finance.get("ok")) and bool(verification.get("ok"))
        and bool(cleanup_result.get("ok")),
        "prepared": prepared,
        "project": project,
        "finance": finance,
        "verification": verification,
        "cleanup": cleanup_result,
    }
    LAST_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_REPORT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repeatable real-DeepSeek Agent write acceptance tests.")
    parser.add_argument("command", choices=["prepare", "project", "finance", "verify", "cleanup", "all"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    service = AgentWorkbenchService("civil")
    if args.command == "prepare":
        result = prepare(service)
    elif args.command == "project":
        report = _load()
        result = run_project(service, report)
    elif args.command == "finance":
        report = _load()
        result = run_finance(service, report)
    elif args.command == "verify":
        result = verify(service)
    elif args.command == "cleanup":
        result = cleanup(service)
    else:
        result = run_all(service)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
