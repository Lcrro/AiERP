from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any
from urllib.parse import urlparse

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.master_data import MasterDataRelease  # noqa: E402
from nexterp_agent.workbench.server import AgentWorkbenchService  # noqa: E402


REPORT_PATH = ROOT / "data" / "runtime" / "test_transaction_reset_report.json"
RESET_CONFIRMATION = "RESET-CIVIL-TEST-TRANSACTIONS"
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
DELETE_ORDER = TRANSACTION_TYPES
LIST_FIELDS = ["name", "docstatus", "owner", "modified"]


def active_users() -> list[str]:
    release = MasterDataRelease()
    return sorted(
        str(row.get("user_email") or "")
        for row in release.table("user_accounts.tsv")
        if row.get("status") == "active" and row.get("user_email")
    )


def _assert_local_test_site(service: AgentWorkbenchService, users: list[str]) -> None:
    if not users:
        raise RuntimeError("没有可用的测试员工账号。")
    hosts = {
        (urlparse(service.client(user).base_url).hostname or "").lower()
        for user in users
    }
    if not hosts or any(host not in {"localhost", "127.0.0.1", "::1"} for host in hosts):
        raise RuntimeError(f"拒绝清理非本机 ERPNext：{sorted(hosts)}")


def collect(service: AgentWorkbenchService) -> dict[str, dict[str, dict[str, Any]]]:
    users = active_users()
    _assert_local_test_site(service, users)
    found: dict[str, dict[str, dict[str, Any]]] = {doctype: {} for doctype in TRANSACTION_TYPES}
    for user in users:
        client = service.client(user)
        identity = client.get_logged_user()
        if not identity.ok or identity.data != user:
            continue
        for doctype in TRANSACTION_TYPES:
            result = client.search_documents(
                doctype,
                fields=LIST_FIELDS,
                limit=500,
                order_by="modified desc",
            )
            if not result.ok or not isinstance(result.data, list):
                continue
            for row in result.data:
                name = str(row.get("name") or "")
                if not name:
                    continue
                entry = found[doctype].setdefault(name, {**row, "visible_to": []})
                if user not in entry["visible_to"]:
                    entry["visible_to"].append(user)
    return found


def summarize(found: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    counts = {doctype: len(found.get(doctype, {})) for doctype in TRANSACTION_TYPES}
    rows = [row for documents in found.values() for row in documents.values()]
    active_total = sum(1 for row in rows if int(row.get("docstatus") or 0) != 2)
    cancelled_audit_total = sum(1 for row in rows if int(row.get("docstatus") or 0) == 2)
    return {
        "total": sum(counts.values()),
        "active_total": active_total,
        "cancelled_audit_total": cancelled_audit_total,
        "counts": counts,
        "documents": {
            doctype: [dict(row) for row in found.get(doctype, {}).values()]
            for doctype in TRANSACTION_TYPES
            if found.get(doctype)
        },
    }


def _candidate_users(row: dict[str, Any], all_users: list[str]) -> list[str]:
    ordered = [str(row.get("owner") or ""), *row.get("visible_to", []), *all_users]
    result: list[str] = []
    for user in ordered:
        if user and user in all_users and user not in result:
            result.append(user)
    return result


def _purchase_receipt_priority(service: AgentWorkbenchService, row: dict[str, Any]) -> int:
    for user in row.get("visible_to", []):
        detail = service.client(user).get_document("Purchase Receipt", row["name"])
        if detail.ok and isinstance(detail.data, dict):
            return 0 if detail.data.get("is_return") else 1
    return 1


def reset(service: AgentWorkbenchService, found: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    users = active_users()
    _assert_local_test_site(service, users)
    deleted: list[dict[str, Any]] = []
    retained_cancelled: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for doctype in DELETE_ORDER:
        rows = list(found.get(doctype, {}).values())
        if doctype == "Purchase Receipt":
            rows.sort(key=lambda row: (_purchase_receipt_priority(service, row), str(row.get("modified") or "")), reverse=False)
        for row in rows:
            name = str(row["name"])
            docstatus = int(row.get("docstatus") or 0)
            candidates = _candidate_users(row, users)
            cancelled = docstatus != 1
            cancel_errors: list[str] = []
            if docstatus == 1:
                for user in candidates:
                    result = service.client(user).cancel_document(doctype, name)
                    if result.ok:
                        cancelled = True
                        break
                    cancel_errors.append(f"{user}: {result.user_message or result.error}")
            if not cancelled:
                failed.append({"doctype": doctype, "name": name, "stage": "cancel", "errors": cancel_errors})
                continue

            delete_errors: list[str] = []
            removed = False
            for user in candidates:
                result = service.client(user).delete_document(doctype, name)
                if result.ok:
                    deleted.append({"doctype": doctype, "name": name, "user": user, "was_submitted": docstatus == 1})
                    removed = True
                    break
                delete_errors.append(f"{user}: {result.user_message or result.error}")
            if not removed:
                detail_exists = False
                for user in candidates:
                    detail = service.client(user).get_document(doctype, name)
                    if detail.ok:
                        detail_exists = True
                        break
                if detail_exists and docstatus in {1, 2}:
                    retained_cancelled.append({"doctype": doctype, "name": name, "errors": delete_errors})
                elif detail_exists:
                    failed.append({"doctype": doctype, "name": name, "stage": "delete", "errors": delete_errors})

    remaining = summarize(collect(service))
    report = {
        "executed_at": datetime.now().astimezone().isoformat(),
        "deleted_count": len(deleted),
        "deleted": deleted,
        "retained_cancelled_count": len(retained_cancelled),
        "retained_cancelled": retained_cancelled,
        "failed_count": len(failed),
        "failed": failed,
        "remaining": remaining,
        "ok": not failed and remaining["total"] == len(retained_cancelled),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Inventory or reset transaction documents in the local civil ERPNext test site.")
    parser.add_argument("command", choices=["inventory", "reset"])
    parser.add_argument("--confirm", default="", help=f"Reset requires: {RESET_CONFIRMATION}")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    service = AgentWorkbenchService("civil")
    found = collect(service)
    if args.command == "inventory":
        result = {"ok": True, **summarize(found)}
    else:
        if args.confirm != RESET_CONFIRMATION:
            raise SystemExit(f"拒绝执行：请提供 --confirm {RESET_CONFIRMATION}")
        result = reset(service, found)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
