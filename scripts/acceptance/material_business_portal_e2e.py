"""Full material portal acceptance against the isolated material-test Site.

The driver deliberately uses the same server-owned preview/confirm boundary as
the browser.  It never accepts ERPNext credentials or tool names from a
business payload, and every confirmed write carries a unique request_id.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
import time
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
load_dotenv(ROOT / ".env")

from nexterp_agent.master_data import MasterDataRelease  # noqa: E402
from nexterp_agent.workbench.server import AgentWorkbenchService, BusinessInputError  # noqa: E402


REPORT_ROOT = ROOT / ".runtime" / "acceptance" / "material-business-portal"
PROJECT_CODE = "PRJ-HL-13"
USERS = {
    "clerk": "mao.xiaoquan@stec-up.local",
    "supervisor": "pan.feng@stec-up.local",
    "project_manager": "hu.yinhu@stec-up.local",
    "procurement": "procurement.test@stec-up.local",
    "warehouse": "warehouse.test@stec-up.local",
}
SUPPLIERS = ["SUP-TEST-A", "SUP-TEST-B"]
ITEMS = [
    {"item_code": "1000557301001", "qty": 4, "uom": "件"},
    {"item_code": "100031850101041", "qty": 4, "uom": "套"},
    {"item_code": "100031790102001", "qty": 20, "uom": "只"},
]


def _now_run_id() -> str:
    return f"E2E验收-{datetime.now().astimezone().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"


def _report_path(run_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in run_id)
    return REPORT_ROOT / f"{safe}.json"


def _cookie(user: str) -> str:
    return f"nexterp_business_user={user}; nexterp_business_project={PROJECT_CODE}"


def _document(service: AgentWorkbenchService, user: str, doctype: str, name: str) -> dict[str, Any]:
    payload = service.document(user, doctype, name)
    document = payload.get("document") if isinstance(payload, dict) else None
    if not isinstance(document, dict):
        raise RuntimeError(f"{doctype} {name} 回读没有文档内容")
    return document


def _actual_qty(service: AgentWorkbenchService, user: str, item_code: str, warehouse: str) -> float:
    result = service.client(user).get_stock_balance(item_code, warehouse=warehouse, limit=20)
    if not result.ok:
        raise RuntimeError(result.user_message or result.error or "读取库存失败")
    for row in result.data or []:
        if isinstance(row, dict) and str(row.get("warehouse") or "") == warehouse:
            return float(row.get("actual_qty") or 0)
    return 0.0


def _save(report: dict[str, Any]) -> None:
    path = _report_path(str(report["run_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _load(run_id: str) -> dict[str, Any]:
    path = _report_path(run_id)
    if not path.exists():
        raise FileNotFoundError(f"找不到验收 run_id：{run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _command(
    service: AgentWorkbenchService,
    report: dict[str, Any],
    user: str,
    action: str,
    payload: dict[str, Any],
    label: str,
) -> dict[str, Any]:
    preview = service.business_preview(_cookie(user), {"action": action, "payload": payload})
    command_id = str(preview["command_id"])
    request_id = f"{report['run_id']}:{label}:{uuid4().hex}"
    result = service.business_confirm(_cookie(user), command_id, request_id)
    duplicate = service.business_confirm(_cookie(user), command_id, request_id)
    if result.get("name") and duplicate.get("name") != result.get("name"):
        raise RuntimeError(f"{label} 幂等重放返回了不同单号")
    entry = {
        "label": label,
        "action": action,
        "user": user,
        "command_id": command_id,
        "request_id": request_id,
        "preview": preview,
        "result": result,
        "duplicate_same_result": duplicate.get("name") == result.get("name"),
    }
    report.setdefault("commands", []).append(entry)
    _save(report)
    return result


def _record_document(report: dict[str, Any], doctype: str, name: str, user: str, *, role: str = "") -> None:
    report.setdefault("documents", []).append({"doctype": doctype, "name": name, "user": user, "role": role})
    _save(report)


def prepare(service: AgentWorkbenchService, run_id: str | None = None) -> dict[str, Any]:
    release = MasterDataRelease()
    company = service.erpnext_company_name("STEC")
    client = service.client(USERS["clerk"])
    erp_project = service.erpnext_project_name(client, PROJECT_CODE)
    warehouse = service.erpnext_warehouse_name("WH-HL-13")
    checks: dict[str, bool] = {
        "company": bool(client.document_exists("Company", company).ok),
        "project": bool(client.document_exists("Project", erp_project).ok),
        "warehouse": bool(client.document_exists("Warehouse", warehouse).ok),
        "suppliers": True,
    }
    for code in SUPPLIERS:
        supplier = next((row for row in release.table("suppliers.tsv", include_candidates=False) if row.get("supplier_code") == code), None)
        checks[f"supplier:{code}"] = bool(supplier and client.document_exists("Supplier", str(supplier.get("supplier_name"))).ok)
    for row in ITEMS:
        item = client.get_document("Item", row["item_code"])
        checks[f"item:{row['item_code']}"] = bool(
            item.ok and isinstance(item.data, dict)
            and not item.data.get("disabled")
            and int(item.data.get("is_stock_item") or 0) == 1
            and int(item.data.get("is_purchase_item") or 0) == 1
            and str(item.data.get("stock_uom") or "") == row["uom"]
        )
    for role, user in USERS.items():
        identity = service.client(user).get_logged_user()
        checks[f"identity:{role}"] = identity.ok and identity.data == user
    if not all(checks.values()):
        raise RuntimeError(f"沙盘主数据验收失败：{checks}")
    run_id = run_id or _now_run_id()
    baseline = {
        row["item_code"]: _actual_qty(service, USERS["warehouse"], row["item_code"], warehouse)
        for row in ITEMS
    }
    report = {
        "run_id": run_id,
        "marker": run_id,
        "created_at": datetime.now().astimezone().isoformat(),
        "project_code": PROJECT_CODE,
        "erpnext_project": erp_project,
        "company": company,
        "warehouse": warehouse,
        "items": ITEMS,
        "checks": checks,
        "baseline_inventory": baseline,
        "documents": [],
        "commands": [],
        "negative_cases": {},
    }
    _save(report)
    return report


def _workflow(service: AgentWorkbenchService, report: dict[str, Any], user: str, name: str, action: str, label: str, comment: str = "") -> dict[str, Any]:
    return _command(service, report, user, "workflow.action", {
        "doctype": "Material Request",
        "name": name,
        "action": action,
        "comment": comment,
    }, label)


def run(service: AgentWorkbenchService, report: dict[str, Any]) -> dict[str, Any]:
    schedule_date = (date.today() + timedelta(days=7)).isoformat()
    marker = report["marker"]
    clerk = USERS["clerk"]
    supervisor = USERS["supervisor"]
    project_manager = USERS["project_manager"]
    procurement = USERS["procurement"]
    warehouse_user = USERS["warehouse"]
    mr_result = _command(service, report, clerk, "material_request.create_draft", {
        "items": ITEMS,
        "schedule_date": schedule_date,
        "purpose": f"{marker}｜龙华项目三行物料采购申请",
    }, "material-request-create")
    mr = str(mr_result["name"])
    _record_document(report, "Material Request", mr, clerk, role="clerk")

    _workflow(service, report, clerk, mr, "提交", "material-request-submit")
    _workflow(service, report, supervisor, mr, "退回", "material-request-reject", comment=f"{marker}：请补充现场用途后重提")
    _command(service, report, clerk, "material_request.update_draft", {
        "name": mr,
        "schedule_date": (date.today() + timedelta(days=8)).isoformat(),
        "purpose": f"{marker}｜已补充现场用途：合流项目施工材料采购",
    }, "material-request-resubmit-edit")
    _workflow(service, report, clerk, mr, "提交", "material-request-resubmit")
    _workflow(service, report, supervisor, mr, "主管通过", "material-request-supervisor-approve", comment=f"{marker}：主管审核通过")
    _workflow(service, report, project_manager, mr, "项目通过", "material-request-project-approve", comment=f"{marker}：项目经理审核通过")
    mr_doc = _document(service, project_manager, "Material Request", mr)
    if int(mr_doc.get("docstatus") or 0) != 1:
        raise RuntimeError("材料申请审批完成但 docstatus 不是 1")
    report["names"] = {"material_request": mr}
    mr_items = [row for row in mr_doc.get("items") or [] if isinstance(row, dict)]
    selected_rows = [f"{mr}:{row['name']}" for row in mr_items]

    rfq_result = _command(service, report, procurement, "rfq.create", {
        "selected_rows": selected_rows,
        "supplier_codes": SUPPLIERS,
        "schedule_date": schedule_date,
        "message_for_supplier": f"{marker}：请按三行物料分别报价",
    }, "rfq-create")
    rfq = str(rfq_result["name"])
    _record_document(report, "Request for Quotation", rfq, procurement, role="procurement")
    _command(service, report, procurement, "document.submit", {"doctype": "Request for Quotation", "name": rfq}, "rfq-submit")
    rfq_doc = _document(service, procurement, "Request for Quotation", rfq)
    rfq_items = [row for row in rfq_doc.get("items") or [] if isinstance(row, dict)]

    quotation_names: list[str] = []
    rates = [31.5, 27.8]
    valid_till = (date.today() + timedelta(days=14)).isoformat()
    for index, supplier in enumerate(SUPPLIERS):
        offers = [{"request_for_quotation_item": row["name"], "rate": rates[index] + n, "schedule_date": schedule_date} for n, row in enumerate(rfq_items)]
        quotation_result = _command(service, report, procurement, "quotation.create", {
            "request_for_quotation": rfq,
            "supplier_code": supplier,
            "offers": offers,
            "valid_till": valid_till,
            "terms": f"{marker}：测试报价，交期有效",
        }, f"quotation-{index + 1}-create")
        quotation = str(quotation_result["name"])
        quotation_names.append(quotation)
        _record_document(report, "Supplier Quotation", quotation, procurement, role="procurement")
        _command(service, report, procurement, "document.submit", {"doctype": "Supplier Quotation", "name": quotation}, f"quotation-{index + 1}-submit")
    comparison = service.compare_supplier_quotations(procurement, quotation_names)
    report["quotation_comparison"] = comparison
    recommendation = str((comparison.get("recommendation") or {}).get("supplier_quotation") or "")
    if recommendation not in quotation_names:
        totals = {str(row.get("name")): float(row.get("grand_total") or 0) for row in comparison.get("quotations") or [] if isinstance(row, dict)}
        recommendation = min(totals, key=totals.get) if totals else quotation_names[1]
    report["names"]["recommended_quotation"] = recommendation
    po_result = _command(service, report, procurement, "purchase_order.create", {"supplier_quotation": recommendation}, "purchase-order-create")
    po = str(po_result["name"])
    _record_document(report, "Purchase Order", po, procurement, role="procurement")
    _command(service, report, procurement, "document.submit", {"doctype": "Purchase Order", "name": po}, "purchase-order-submit")
    po_doc = _document(service, procurement, "Purchase Order", po)
    po_items = [row for row in po_doc.get("items") or [] if isinstance(row, dict)]

    first_quantities = {ITEMS[0]["item_code"]: 2, ITEMS[1]["item_code"]: 2, ITEMS[2]["item_code"]: 10}
    first_selection = [{"purchase_order_item": row["name"], "qty": first_quantities.get(str(row.get("item_code")), 0)} for row in po_items if first_quantities.get(str(row.get("item_code")), 0)]
    receipt_result = _command(service, report, warehouse_user, "purchase_receipt.create", {"purchase_order": po, "selected_items": first_selection}, "receipt-partial-create")
    receipt = str(receipt_result["name"])
    _record_document(report, "Purchase Receipt", receipt, warehouse_user, role="warehouse")
    _command(service, report, warehouse_user, "document.submit", {"doctype": "Purchase Receipt", "name": receipt}, "receipt-partial-submit")
    receipt_doc = _document(service, warehouse_user, "Purchase Receipt", receipt)
    bolt_receipt_item = next(row for row in receipt_doc.get("items") or [] if row.get("item_code") == ITEMS[1]["item_code"])
    discrepancy_result = _command(service, report, warehouse_user, "purchase_discrepancy.create", {
        "purchase_receipt": receipt,
        "description": f"{marker}：螺栓到货规格差异，退回1套",
        "items": [{"purchase_receipt_item": bolt_receipt_item["name"], "item_code": ITEMS[1]["item_code"], "qty": 1, "reason": "规格差异"}],
        "discrepancy_type": "spec_mismatch",
        "severity": "High",
        "assigned_to": supervisor,
    }, "receipt-discrepancy")
    report["discrepancy"] = discrepancy_result.get("discrepancy") or discrepancy_result.get("result", {}).get("discrepancy")
    return_result = _command(service, report, warehouse_user, "purchase_return.create", {
        "purchase_receipt": receipt,
        "reason": f"{marker}：规格差异采购退货",
        "items": [{"purchase_receipt_item": bolt_receipt_item["name"], "item_code": ITEMS[1]["item_code"], "qty": 1, "reason": "规格差异"}],
    }, "receipt-return-create")
    purchase_return = str(return_result["name"])
    _record_document(report, "Purchase Receipt", purchase_return, warehouse_user, role="warehouse")
    _command(service, report, warehouse_user, "document.submit", {"doctype": "Purchase Receipt", "name": purchase_return}, "receipt-return-submit")

    po_after_return = _document(service, warehouse_user, "Purchase Order", po)
    second_selection = []
    for row in po_after_return.get("items") or []:
        remaining = max(float(row.get("qty") or 0) - float(row.get("received_qty") or 0), 0)
        if remaining > 0:
            second_selection.append({"purchase_order_item": row["name"], "qty": remaining})
    if not second_selection:
        raise RuntimeError("部分收货/退货后采购订单没有可收剩余量")
    second_result = _command(service, report, warehouse_user, "purchase_receipt.create", {"purchase_order": po, "selected_items": second_selection}, "receipt-remaining-create")
    second_receipt = str(second_result["name"])
    _record_document(report, "Purchase Receipt", second_receipt, warehouse_user, role="warehouse")
    _command(service, report, warehouse_user, "document.submit", {"doctype": "Purchase Receipt", "name": second_receipt}, "receipt-remaining-submit")

    bolt_code = ITEMS[1]["item_code"]
    warehouse = report["warehouse"]
    issue_result = _command(service, report, project_manager, "stock.project_issue.create", {
        "source_warehouse": warehouse,
        "items": [{"item_code": bolt_code, "qty": 1, "uom": ITEMS[1]["uom"]}],
        "remarks": f"{marker}：项目领用1套螺栓",
    }, "project-issue-create")
    issue = str(issue_result["name"])
    _record_document(report, "Stock Entry", issue, project_manager, role="project_manager")
    _command(service, report, project_manager, "document.submit", {"doctype": "Stock Entry", "name": issue}, "project-issue-submit")
    return_result = _command(service, report, project_manager, "stock.project_return.create", {
        "target_warehouse": warehouse,
        "items": [{"item_code": bolt_code, "qty": 1, "uom": ITEMS[1]["uom"], "t_warehouse": warehouse, "project": report["erpnext_project"]}],
        "remarks": f"{marker}：项目退回1套螺栓",
    }, "project-return-create")
    project_return = str(return_result["name"])
    _record_document(report, "Stock Entry", project_return, project_manager, role="project_manager")
    _command(service, report, project_manager, "document.submit", {"doctype": "Stock Entry", "name": project_return}, "project-return-submit")
    report["names"].update({
        "request_for_quotation": rfq,
        "supplier_quotations": quotation_names,
        "purchase_order": po,
        "purchase_receipt_partial": receipt,
        "purchase_return": purchase_return,
        "purchase_receipt_remaining": second_receipt,
        "stock_issue": issue,
        "stock_return": project_return,
    })
    report["final_inventory"] = {row["item_code"]: _actual_qty(service, warehouse_user, row["item_code"], warehouse) for row in ITEMS}
    _save(report)
    return verify(service, report)


def verify(service: AgentWorkbenchService, report: dict[str, Any]) -> dict[str, Any]:
    names = report.get("names") or {}
    checks: dict[str, bool] = {}
    mr = _document(service, USERS["project_manager"], "Material Request", str(names["material_request"]))
    checks["material_request_approved"] = int(mr.get("docstatus") or 0) == 1 and "批准" in str(mr.get("workflow_state") or "")
    checks["three_item_rows"] = len(mr.get("items") or []) == 3
    rfq = _document(service, USERS["procurement"], "Request for Quotation", str(names["request_for_quotation"]))
    checks["rfq_submitted"] = int(rfq.get("docstatus") or 0) == 1 and len(rfq.get("suppliers") or []) == 2
    po = _document(service, USERS["procurement"], "Purchase Order", str(names["purchase_order"]))
    checks["purchase_order_submitted"] = int(po.get("docstatus") or 0) == 1
    checks["purchase_order_fully_received"] = float(po.get("per_received") or 0) >= 99.99
    expected_received = {
        row["item_code"]: float(report["baseline_inventory"].get(row["item_code"], 0.0)) + float(row["qty"])
        for row in report.get("items") or []
    }
    checks["purchase_order_received_quantities"] = all(
        abs(float(row.get("received_qty") or 0.0) - float(row.get("qty") or 0.0)) < 0.0001
        for row in (po.get("items") or [])
        if isinstance(row, dict)
    )
    partial = _document(service, USERS["warehouse"], "Purchase Receipt", str(names["purchase_receipt_partial"]))
    returned = _document(service, USERS["warehouse"], "Purchase Receipt", str(names["purchase_return"]))
    remaining = _document(service, USERS["warehouse"], "Purchase Receipt", str(names["purchase_receipt_remaining"]))
    checks["partial_receipt_submitted"] = int(partial.get("docstatus") or 0) == 1 and not bool(partial.get("is_return"))
    checks["purchase_return_submitted"] = int(returned.get("docstatus") or 0) == 1 and bool(returned.get("is_return"))
    checks["remaining_receipt_submitted"] = int(remaining.get("docstatus") or 0) == 1
    issue = _document(service, USERS["project_manager"], "Stock Entry", str(names["stock_issue"]))
    stock_return = _document(service, USERS["project_manager"], "Stock Entry", str(names["stock_return"]))
    checks["project_issue_submitted"] = int(issue.get("docstatus") or 0) == 1 and str(issue.get("stock_entry_type")) == "Material Issue"
    checks["project_return_submitted"] = int(stock_return.get("docstatus") or 0) == 1
    final_inventory = report.get("final_inventory") or {
        row["item_code"]: _actual_qty(service, USERS["warehouse"], row["item_code"], report["warehouse"])
        for row in report.get("items") or []
    }
    checks["inventory_reconciled_after_issue_return"] = all(
        abs(float(final_inventory.get(code, 0.0)) - expected) < 0.0001
        for code, expected in expected_received.items()
    )
    ledger_docs = (
        names.get("purchase_receipt_partial"),
        names.get("purchase_return"),
        names.get("purchase_receipt_remaining"),
        names.get("stock_issue"),
        names.get("stock_return"),
    )
    ledger_counts: dict[str, int] = {}
    for voucher in ledger_docs:
        if not voucher:
            continue
        ledger = service.client(USERS["warehouse"]).search_documents(
            "Stock Ledger Entry",
            filters={"voucher_no": voucher},
            fields=["name", "item_code", "actual_qty", "qty_after_transaction", "warehouse", "voucher_no", "voucher_type", "project"],
            limit=50,
        )
        ledger_counts[str(voucher)] = len(ledger.data or []) if ledger.ok and isinstance(ledger.data, list) else 0
    report["stock_ledger_counts"] = ledger_counts
    checks["stock_ledger_readback"] = all(count > 0 for count in ledger_counts.values()) and len(ledger_counts) == len(ledger_docs)
    checks["all_commands_idempotent"] = all(bool(row.get("duplicate_same_result")) for row in report.get("commands") or [])
    checks["source_links_present"] = all(
        any(row.get("material_request") == names["material_request"] for row in (po.get("items") or []) if isinstance(row, dict))
        and any(row.get("supplier_quotation") == names["recommended_quotation"] for row in (po.get("items") or []) if isinstance(row, dict))
        for _ in [0]
    )
    negative = report.setdefault("negative_cases", {})
    try:
        service.business_preview(_cookie(USERS["clerk"]), {"action": "material_request.create_draft", "payload": {"items": [{"item_code": "999999999999999", "qty": 1, "uom": "件"}], "schedule_date": date.today().isoformat()}})
    except BusinessInputError as exc:
        negative["invalid_item_no_write"] = {"error_code": exc.error_code, "field_path": exc.field_path}
    try:
        expired = service.business_preview(_cookie(USERS["clerk"]), {"action": "material_request.update_draft", "payload": {"name": names["material_request"], "purpose": "expired"}})
        service.business_commands.get(expired["command_id"], user=USERS["clerk"]).expires_at = time.time() - 1
        service.business_confirm(_cookie(USERS["clerk"]), expired["command_id"], f"{report['run_id']}:expired")
    except ValueError:
        negative["expired_preview_no_write"] = True
    checks["negative_cases_no_write"] = bool(negative.get("invalid_item_no_write")) and bool(negative.get("expired_preview_no_write"))
    report["verification"] = {"checks": checks, "ok": all(checks.values()), "verified_at": datetime.now().astimezone().isoformat()}
    _save(report)
    if not report["verification"]["ok"]:
        raise RuntimeError(f"验收核验失败：{checks}")
    return report["verification"]


def cleanup(service: AgentWorkbenchService, report: dict[str, Any]) -> dict[str, Any]:
    results = []
    marker = str(report.get("marker") or report.get("run_id") or "")
    for row in reversed(report.get("documents") or []):
        doctype, name, user = row.get("doctype"), row.get("name"), row.get("user")
        if not doctype or not name or not marker:
            continue
        document = service.client(user).get_document(doctype, name)
        if not document.ok or not isinstance(document.data, dict):
            results.append({"doctype": doctype, "name": name, "status": "not_found"})
            continue
        marker_present = marker in json.dumps(document.data, ensure_ascii=False)
        if int(document.data.get("docstatus") or 0) != 1:
            results.append({"doctype": doctype, "name": name, "status": "draft_retained", "marker_present": marker_present})
            continue
        cancelled = service.client(user).cancel_document(doctype, name)
        results.append({
            "doctype": doctype,
            "name": name,
            "status": "cancelled" if cancelled.ok else "cancel_failed",
            "error": cancelled.error,
            "marker_present": marker_present,
        })
    report["cleanup"] = {"run_id": report["run_id"], "results": results, "completed_at": datetime.now().astimezone().isoformat()}
    _save(report)
    return report["cleanup"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "run", "verify", "cleanup", "all"])
    parser.add_argument("--run-id", default="")
    args = parser.parse_args()
    service = AgentWorkbenchService("material_test")
    if args.command == "prepare":
        report = prepare(service, args.run_id or None)
        print(json.dumps({"ok": True, "run_id": report["run_id"], "report": str(_report_path(report["run_id"]))}, ensure_ascii=False))
        return 0
    if args.command == "all":
        report = prepare(service, args.run_id or None)
        print(json.dumps(run(service, report), ensure_ascii=False))
        return 0
    if not args.run_id:
        raise SystemExit("该命令需要 --run-id")
    report = _load(args.run_id)
    if args.command == "run":
        print(json.dumps(run(service, report), ensure_ascii=False))
    elif args.command == "verify":
        print(json.dumps(verify(service, report), ensure_ascii=False))
    elif args.command == "cleanup":
        print(json.dumps(cleanup(service, report), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
