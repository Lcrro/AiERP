from __future__ import annotations

import re

import frappe


CIVIL_TEST_SITE = "fac.localhost"
PURGE_CONFIRMATION = "PURGE-CIVIL-TEST-TRANSACTIONS"
TRANSACTION_TYPES = (
    "Payment Entry",
    "Purchase Invoice",
    "Purchase Receipt",
    "Stock Entry",
    "Purchase Order",
    "Supplier Quotation",
    "Request for Quotation",
    "Material Request",
    "Task",
    "ToDo",
)
MASTER_DATA_TYPES = (
    "Company",
    "Project",
    "Warehouse",
    "Employee",
    "User",
    "Item",
    "Supplier",
    "Item Price",
)


def inventory() -> dict:
    counts: dict[str, int] = {}
    active = 0
    cancelled = 0
    for doctype in TRANSACTION_TYPES:
        rows = frappe.get_all(doctype, fields=["name", "docstatus"], limit_page_length=0)
        counts[doctype] = len(rows)
        active += sum(int(row.get("docstatus") or 0) != 2 for row in rows)
        cancelled += sum(int(row.get("docstatus") or 0) == 2 for row in rows)
    return {
        "site": frappe.local.site,
        "total": sum(counts.values()),
        "active_total": active,
        "cancelled_total": cancelled,
        "counts": counts,
    }


def master_data_inventory() -> dict:
    return {
        "site": frappe.local.site,
        "counts": {
            doctype: frappe.db.count(doctype)
            for doctype in MASTER_DATA_TYPES
        },
    }


def purge_cancelled_transactions(confirmation: str) -> dict:
    if frappe.local.site != CIVIL_TEST_SITE:
        frappe.throw(f"Refusing to purge non-test site: {frappe.local.site}")
    if confirmation != PURGE_CONFIRMATION:
        frappe.throw("Invalid civil test purge confirmation")
    before = inventory()
    if before["active_total"]:
        frappe.throw(f"Refusing to purge while {before['active_total']} active documents remain")

    deleted: list[dict[str, str]] = []
    series: set[str] = set()
    for doctype in TRANSACTION_TYPES:
        rows = frappe.get_all(
            doctype,
            filters={"docstatus": 2},
            fields=["name"],
            order_by="modified desc",
            limit_page_length=0,
        )
        for row in rows:
            name = str(row["name"])
            prefix = re.sub(r"\d+$", "", name)
            if prefix != name:
                series.add(prefix)
            frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
            deleted.append({"doctype": doctype, "name": name})

    workflow_actions = frappe.get_all(
        "Workflow Action",
        filters={"reference_doctype": ["in", list(TRANSACTION_TYPES)]},
        pluck="name",
        limit_page_length=0,
    )
    for name in workflow_actions:
        frappe.delete_doc("Workflow Action", name, force=True, ignore_permissions=True)

    if series:
        frappe.db.sql("delete from `tabSeries` where name in %(series)s", {"series": tuple(series)})
    frappe.db.commit()
    return {
        "before": before,
        "deleted_count": len(deleted),
        "workflow_actions_deleted": len(workflow_actions),
        "reset_series": sorted(series),
        "after": inventory(),
    }
