from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys
from typing import Any

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextAdapter  # noqa: E402
from nexterp_agent.master_data import MasterDataRelease  # noqa: E402
from nexterp_agent.workbench.server import AgentWorkbenchService  # noqa: E402


REPORT_PATH = ROOT / "data" / "runtime" / "procurement_acceptance_report.json"
PROJECT_CODE = "PRJ-HL-13"
ERP_PROJECT = "PROJ-0010"
WAREHOUSE = "合流1.3标仓库 - SD"
ITEM_CODE = "MAT-CEM-000008"
USERS = {
    "clerk": "mao.xiaoquan@stec-up.local",
    "manager": "pan.feng@stec-up.local",
    "project_manager": "hu.yinhu@stec-up.local",
}


def _require(result, label: str) -> dict[str, Any]:
    if not result.ok:
        raise RuntimeError(result.user_message or result.error or f"{label}失败")
    if not isinstance(result.data, dict):
        raise RuntimeError(f"{label}未返回单据")
    return result.data


def _document(service: AgentWorkbenchService, user: str, doctype: str, name: str) -> dict[str, Any]:
    return service.document(user, doctype, name)["document"]


def _actual_qty(service: AgentWorkbenchService) -> float:
    result = service.client(USERS["manager"]).search_documents(
        "Bin",
        filters={"item_code": ITEM_CODE, "warehouse": WAREHOUSE},
        fields=["actual_qty"],
        limit=1,
    )
    if not result.ok or not result.data:
        return 0.0
    return float(result.data[0].get("actual_qty") or 0)


def prepare(service: AgentWorkbenchService) -> dict[str, Any]:
    release = MasterDataRelease()
    checks = {
        "project": PROJECT_CODE in release.projects,
        "warehouse": any(row.get("erpnext_warehouse_name") == WAREHOUSE for row in release.warehouses.values()),
        "item": any(row.get("item_code") == ITEM_CODE for row in release.materials),
        "suppliers": all(
            any(row.get("supplier_code") == code and row.get("status") == "active" for row in release.table("suppliers.tsv"))
            for code in ("SUP-TEST-A", "SUP-TEST-B")
        ),
    }
    for role, user in USERS.items():
        logged_in = service.client(user).get_logged_user()
        checks[f"identity:{role}"] = logged_in.ok and logged_in.data == user
    if not all(checks.values()):
        raise RuntimeError(f"验收主数据或员工身份未就绪：{checks}")
    return {"ok": True, "checks": checks, "baseline_qty": _actual_qty(service)}


def run(service: AgentWorkbenchService) -> dict[str, Any]:
    prepared = prepare(service)
    schedule_date = (date.today() + timedelta(days=4)).isoformat()
    valid_till = (date.today() + timedelta(days=7)).isoformat()
    report: dict[str, Any] = {
        "created_at": date.today().isoformat(),
        "project_code": PROJECT_CODE,
        "baseline_qty": prepared["baseline_qty"],
        "documents": [],
    }

    clerk_adapter = ERPNextAdapter(service.client(USERS["clerk"]))
    mr_data = _require(clerk_adapter.execute({
        "tool": "erpnext.buying.create_material_request_draft",
        "arguments": {
            "company": "STEC (Demo)",
            "material_request_type": "Purchase",
            "transaction_date": date.today().isoformat(),
            "schedule_date": schedule_date,
            "items": [{
                "item_code": ITEM_CODE,
                "qty": 1,
                "uom": "包",
                "warehouse": WAREHOUSE,
                "project": ERP_PROJECT,
                "rate": 28,
            }],
        },
    }), "创建材料申请")
    mr = str(mr_data["name"])
    report["documents"].append({"doctype": "Material Request", "name": mr, "user": USERS["clerk"]})

    service.apply_workflow_action(USERS["clerk"], "Material Request", mr, "提交申请", project=PROJECT_CODE)
    service.apply_workflow_action(USERS["manager"], "Material Request", mr, "批准", project=PROJECT_CODE)
    service.apply_workflow_action(USERS["project_manager"], "Material Request", mr, "批准", project=PROJECT_CODE)
    mr_doc = _document(service, USERS["manager"], "Material Request", mr)
    mr_item = str(mr_doc["items"][0]["name"])

    rfq_payload = service.create_request_for_quotation(
        USERS["manager"], PROJECT_CODE, [f"{mr}:{mr_item}"], ["SUP-TEST-A", "SUP-TEST-B"],
        schedule_date=schedule_date,
        message_for_supplier="采购闭环自动验收，请按测试价格报价。",
    )
    rfq = str(rfq_payload["name"])
    report["documents"].append({"doctype": "Request for Quotation", "name": rfq, "user": USERS["manager"]})
    service.submit_document(USERS["manager"], "Request for Quotation", rfq, project=PROJECT_CODE)
    rfq_doc = _document(service, USERS["manager"], "Request for Quotation", rfq)
    rfq_item = str(rfq_doc["items"][0]["name"])

    sq_payload = service.create_supplier_quotation(
        USERS["manager"], PROJECT_CODE, rfq, "SUP-TEST-B",
        [{"request_for_quotation_item": rfq_item, "rate": 26.8, "schedule_date": schedule_date}],
        valid_till=valid_till,
        terms="货到付款；采购闭环自动验收。",
    )
    sq = str(sq_payload["name"])
    report["documents"].append({"doctype": "Supplier Quotation", "name": sq, "user": USERS["manager"]})
    service.submit_document(USERS["manager"], "Supplier Quotation", sq, project=PROJECT_CODE)

    po_payload = service.create_purchase_order_from_supplier_quotation(USERS["manager"], PROJECT_CODE, sq)
    po = str(po_payload["name"])
    report["documents"].append({"doctype": "Purchase Order", "name": po, "user": USERS["manager"]})
    service.submit_document(USERS["manager"], "Purchase Order", po, project=PROJECT_CODE)

    receipt_payload = service.create_purchase_receipt_from_purchase_order(USERS["manager"], PROJECT_CODE, po)
    receipt = str(receipt_payload["name"])
    report["documents"].append({"doctype": "Purchase Receipt", "name": receipt, "user": USERS["manager"]})
    service.submit_document(USERS["manager"], "Purchase Receipt", receipt, project=PROJECT_CODE)

    return_payload = service.create_purchase_return_from_receipt(
        USERS["manager"], PROJECT_CODE, receipt, "采购闭环自动验收：规格与订单不一致。",
    )
    purchase_return = str(return_payload["name"])
    report["documents"].append({"doctype": "Purchase Receipt", "name": purchase_return, "user": USERS["manager"]})
    service.submit_document(USERS["manager"], "Purchase Receipt", purchase_return, project=PROJECT_CODE)

    report["names"] = {
        "material_request": mr,
        "request_for_quotation": rfq,
        "supplier_quotation": sq,
        "purchase_order": po,
        "purchase_receipt": receipt,
        "purchase_return": purchase_return,
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return verify(service, report)


def verify(service: AgentWorkbenchService, report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = report or json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    names = report["names"]
    documents = {
        key: _document(service, USERS["manager"], "Purchase Receipt" if key in {"purchase_receipt", "purchase_return"} else {
            "material_request": "Material Request",
            "request_for_quotation": "Request for Quotation",
            "supplier_quotation": "Supplier Quotation",
            "purchase_order": "Purchase Order",
        }[key], name)
        for key, name in names.items()
    }
    checks = {
        "all_submitted": all(int(document.get("docstatus") or 0) == 1 for document in documents.values()),
        "material_request_approved": documents["material_request"].get("workflow_state") == "已批准",
        "rfq_source": documents["request_for_quotation"]["items"][0].get("material_request") == names["material_request"],
        "quotation_source": documents["supplier_quotation"]["items"][0].get("request_for_quotation") == names["request_for_quotation"],
        "order_source": documents["purchase_order"]["items"][0].get("supplier_quotation") == names["supplier_quotation"],
        "receipt_source": documents["purchase_receipt"]["items"][0].get("purchase_order") == names["purchase_order"],
        "return_source": documents["purchase_return"].get("return_against") == names["purchase_receipt"],
        "return_negative_qty": float(documents["purchase_return"]["items"][0].get("qty") or 0) == -1,
        "inventory_restored": _actual_qty(service) == float(report.get("baseline_qty") or 0),
    }
    result = {"ok": all(checks.values()), "checks": checks, "names": names, "actual_qty": _actual_qty(service)}
    if not result["ok"]:
        raise RuntimeError(f"采购闭环验收失败：{result}")
    return result


def cleanup(service: AgentWorkbenchService) -> dict[str, Any]:
    if not REPORT_PATH.exists():
        return {"ok": True, "deleted": [], "message": "没有验收清单，无需清理。"}
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    deleted = []
    retained_cancelled = []
    failed = []
    for entry in reversed(report.get("documents") or []):
        doctype, name, user = entry["doctype"], entry["name"], entry["user"]
        client = service.client(user)
        detail = client.get_document(doctype, name)
        if not detail.ok:
            continue
        if int(detail.data.get("docstatus") or 0) == 1:
            cancelled = client.cancel_document(doctype, name)
            if not cancelled.ok:
                failed.append({"doctype": doctype, "name": name, "stage": "cancel", "error": cancelled.user_message or cancelled.error})
                continue
        removed = client.call_method("frappe.client.delete", {"doctype": doctype, "name": name})
        if removed.ok:
            deleted.append({"doctype": doctype, "name": name})
        elif "LinkExistsError" in str(removed.error or "") and int(detail.data.get("docstatus") or 0) in {1, 2}:
            retained_cancelled.append({"doctype": doctype, "name": name, "reason": "保留ERPNext取消审计及总账/库存追溯"})
        else:
            failed.append({"doctype": doctype, "name": name, "stage": "delete", "error": removed.user_message or removed.error})
    if not failed:
        REPORT_PATH.unlink(missing_ok=True)
    return {"ok": not failed, "deleted": deleted, "retained_cancelled": retained_cancelled, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the repeatable ERPNext procurement closed-loop acceptance.")
    parser.add_argument("command", choices=["prepare", "run", "verify", "cleanup", "all"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    service = AgentWorkbenchService("civil")
    if args.command == "prepare":
        result = prepare(service)
    elif args.command == "run":
        result = run(service)
    elif args.command == "verify":
        result = verify(service)
    elif args.command == "cleanup":
        result = cleanup(service)
    else:
        cleanup(service)
        result = run(service)
        result["cleanup"] = cleanup(service)
        result["ok"] = bool(result.get("ok")) and bool(result["cleanup"].get("ok"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
