from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextAdapter, ERPNextClient, ToolResult
from nexterp_agent.erpnext.config import load_erpnext_settings


DEMO_CUSTOMERS = [
    "Grant Plastics Ltd.",
    "Palmer Productions Ltd.",
    "West View Software Ltd.",
]
DEMO_SUPPLIERS = [
    "MA Inc.",
    "Summit Traders Ltd.",
    "Zuckerman Security Ltd.",
]
DEMO_ITEM_NAMES = [f"SKU{i:03d}" for i in range(1, 11)]
DEMO_ITEM_GROUPS = ["Demo Item Group"]


@dataclass(frozen=True)
class Candidate:
    doctype: str
    name: str
    docstatus: int = 0
    reason: str = ""


def build_adapter(profile: str) -> ERPNextAdapter:
    settings = load_erpnext_settings(profile)
    client = ERPNextClient(
        settings.base_url,
        settings.api_key,
        settings.api_secret,
        host_header=settings.host_header,
    )
    return ERPNextAdapter(client)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean known ERPNext demo data from the local sandbox.")
    parser.add_argument("--profile", default="local", help="ERPNext env profile, default: local")
    parser.add_argument("--execute", action="store_true", help="Actually delete records. Omit for dry-run.")
    parser.add_argument(
        "--include-agent-tests",
        action="store_true",
        help="Also delete records created by this project with AGENT-TEST-* names.",
    )
    args = parser.parse_args()

    adapter = build_adapter(args.profile)
    candidates = collect_candidates(adapter, include_agent_tests=args.include_agent_tests)
    result = cleanup(adapter, candidates, execute=args.execute)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["failed"] else 1


def collect_candidates(adapter: ERPNextAdapter, *, include_agent_tests: bool) -> list[Candidate]:
    candidates: list[Candidate] = []
    candidates.extend(find_orders(adapter, "Sales Invoice", "customer", DEMO_CUSTOMERS, "demo sales invoice"))
    candidates.extend(find_orders(adapter, "Delivery Note", "customer", DEMO_CUSTOMERS, "demo delivery note"))
    candidates.extend(find_orders(adapter, "Purchase Invoice", "supplier", DEMO_SUPPLIERS, "demo purchase invoice"))
    candidates.extend(find_orders(adapter, "Purchase Receipt", "supplier", DEMO_SUPPLIERS, "demo purchase receipt"))
    candidates.extend(find_orders(adapter, "Sales Order", "customer", DEMO_CUSTOMERS, "demo sales order"))
    candidates.extend(find_orders(adapter, "Purchase Order", "supplier", DEMO_SUPPLIERS, "demo purchase order"))
    candidates.extend(find_orders(adapter, "Quotation", "party_name", DEMO_CUSTOMERS, "demo quotation"))
    candidates.extend(find_orders(adapter, "Supplier Quotation", "supplier", DEMO_SUPPLIERS, "demo supplier quotation"))
    candidates.extend(find_orders(adapter, "Request for Quotation", "supplier", DEMO_SUPPLIERS, "demo RFQ"))
    candidates.extend(find_named_docs(adapter, "Item", DEMO_ITEM_NAMES, "demo item SKU001-SKU010"))
    candidates.extend(find_orders(adapter, "Item", "item_group", DEMO_ITEM_GROUPS, "item in Demo Item Group"))
    candidates.extend(find_named_docs(adapter, "Customer", DEMO_CUSTOMERS, "demo customer"))
    candidates.extend(find_named_docs(adapter, "Supplier", DEMO_SUPPLIERS, "demo supplier"))
    candidates.extend(find_named_docs(adapter, "Item Group", DEMO_ITEM_GROUPS, "demo item group"))

    if include_agent_tests:
        candidates.extend(find_like(adapter, "Item", "name", "AGENT-TEST-%", "agent test item"))
        candidates.extend(find_like(adapter, "ToDo", "description", "Nexterp Agent%smoke test%", "agent smoke ToDo"))

    return dedupe_candidates(candidates)


def find_named_docs(adapter: ERPNextAdapter, doctype: str, names: list[str], reason: str) -> list[Candidate]:
    candidates: list[Candidate] = []
    for name in names:
        result = adapter.execute({"tool": "erpnext.get_document", "arguments": {"doctype": doctype, "name": name}})
        if result.ok and isinstance(result.data, dict):
            candidates.append(
                Candidate(
                    doctype=doctype,
                    name=name,
                    docstatus=int(result.data.get("docstatus") or 0),
                    reason=reason,
                )
            )
    return candidates


def find_orders(
    adapter: ERPNextAdapter,
    doctype: str,
    field: str,
    values: list[str],
    reason: str,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    for value in values:
        result = adapter.execute(
            {
                "tool": "erpnext.search_documents",
                "arguments": {
                    "doctype": doctype,
                    "filters": {field: value},
                    "fields": ["name", "docstatus"],
                    "limit": 500,
                },
            }
        )
        if not result.ok or not isinstance(result.data, list):
            continue
        for row in result.data:
            candidates.append(
                Candidate(
                    doctype=doctype,
                    name=row["name"],
                    docstatus=int(row.get("docstatus") or 0),
                    reason=f"{reason}: {field}={value}",
                )
            )
    return candidates


def find_like(adapter: ERPNextAdapter, doctype: str, field: str, pattern: str, reason: str) -> list[Candidate]:
    result = adapter.execute(
        {
            "tool": "erpnext.search_documents",
            "arguments": {
                "doctype": doctype,
                "filters": {field: ["like", pattern]},
                "fields": ["name", "docstatus"],
                "limit": 500,
            },
        }
    )
    if not result.ok or not isinstance(result.data, list):
        return []
    return [
        Candidate(
            doctype=doctype,
            name=row["name"],
            docstatus=int(row.get("docstatus") or 0),
            reason=reason,
        )
        for row in result.data
    ]


def dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    seen: set[tuple[str, str]] = set()
    unique: list[Candidate] = []
    for candidate in candidates:
        key = (candidate.doctype, candidate.name)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def cleanup(adapter: ERPNextAdapter, candidates: list[Candidate], *, execute: bool) -> dict[str, Any]:
    deleted: list[dict[str, Any]] = []
    disabled: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    planned = [candidate.__dict__ for candidate in candidates]

    if not execute:
        return {
            "mode": "dry-run",
            "planned_count": len(planned),
            "planned": planned,
            "deleted": deleted,
            "disabled": disabled,
            "failed": failed,
        }

    for candidate in candidates:
        cancel_result: ToolResult | None = None
        if candidate.docstatus == 1:
            cancel_result = adapter.execute(
                {
                    "tool": "erpnext.cancel_document",
                    "arguments": {"doctype": candidate.doctype, "name": candidate.name},
                    "reason": f"Cancel before deleting {candidate.reason}",
                }
            )
            if not cancel_result.ok:
                failed.append(format_failure(candidate, "cancel", cancel_result))
                continue

        delete_result = adapter.execute(
            {
                "tool": "erpnext.delete_document",
                "arguments": {"doctype": candidate.doctype, "name": candidate.name},
                "reason": f"Delete {candidate.reason}",
            }
        )
        if delete_result.ok:
            deleted.append({**candidate.__dict__, "cancelled": bool(cancel_result and cancel_result.ok)})
        else:
            disable_result = disable_instead(adapter, candidate)
            if disable_result and disable_result.ok:
                disabled.append(
                    {
                        **candidate.__dict__,
                        "cancelled": bool(cancel_result and cancel_result.ok),
                        "delete_error": delete_result.error,
                    }
                )
            else:
                failure = format_failure(candidate, "delete", delete_result)
                if cancel_result and cancel_result.ok:
                    failure["cancelled"] = True
                if disable_result and not disable_result.ok:
                    failure["disable_error"] = disable_result.error
                failed.append(failure)

    return {
        "mode": "execute",
        "planned_count": len(planned),
        "planned": planned,
        "deleted_count": len(deleted),
        "deleted": deleted,
        "disabled_count": len(disabled),
        "disabled": disabled,
        "failed_count": len(failed),
        "failed": failed,
    }


def disable_instead(adapter: ERPNextAdapter, candidate: Candidate) -> ToolResult | None:
    disable_fields = {
        "Customer": {"disabled": 1},
        "Item": {"disabled": 1},
        "Supplier": {"disabled": 1},
    }
    data = disable_fields.get(candidate.doctype)
    if not data:
        return None
    return adapter.execute(
        {
            "tool": "erpnext.update_document",
            "arguments": {"doctype": candidate.doctype, "name": candidate.name, "data": data},
            "reason": f"Disable linked demo master record instead of deleting {candidate.reason}",
        }
    )


def format_failure(candidate: Candidate, action: str, result: ToolResult) -> dict[str, Any]:
    return {
        **candidate.__dict__,
        "action": action,
        "error_type": result.error_type,
        "error": result.error,
        "user_message": result.user_message,
    }


if __name__ == "__main__":
    raise SystemExit(main())
