"""Prepare the isolated material-test Site for the deterministic business portal.

The command is intentionally narrow: it targets only ``material-test.localhost``
on port 8003, creates missing sandbox master data and never deletes or
overwrites a conflicting ERPNext document.  Run ``plan`` first, then pass the
displayed plan hash and a UUID to ``apply``.  The journal makes a repeated UUID
return the original verified result.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping
import uuid

ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.erpnext.sync_gpc_materials_to_test_site import (  # noqa: E402
    COMPANY_ABBR,
    COMPANY_NAME,
    FrappeSessionClient,
    SyncError,
    _load_client,
)


BASE_URL = "http://localhost:8003"
SITE_HOST = "material-test.localhost"
MASTER_ROOT = ROOT / "data" / "master_data" / "release_v0_1"
DEFAULT_SECRET_PATH = ROOT / ".secrets" / "erpnext-material-test" / "site-secrets.json"
DEFAULT_JOURNAL_PATH = ROOT / ".runtime" / "erpnext-material-test" / "business-bootstrap-journal.json"


SANDBOX_USERS: tuple[dict[str, Any], ...] = (
    {
        "email": "mao.xiaoquan@stec-up.local",
        "full_name": "毛晓泉（材料员）",
        "roles": ["Purchase User", "Stock User", "Projects User"],
    },
    {
        "email": "pan.feng@stec-up.local",
        "full_name": "潘丰（材料设备主管）",
        "roles": ["Purchase Manager", "Purchase User", "Stock Manager", "Stock User", "Projects User"],
    },
    {
        "email": "hu.yinhu@stec-up.local",
        "full_name": "胡银虎（项目经理）",
        "roles": ["Projects Manager", "Projects User", "Purchase User", "Stock User"],
    },
    {
        "email": "procurement.test@stec-up.local",
        "full_name": "采购测试员",
        "roles": ["Purchase User", "Purchase Manager"],
    },
    {
        "email": "warehouse.test@stec-up.local",
        "full_name": "仓管测试员",
        "roles": ["Stock User", "Stock Manager", "Purchase User"],
    },
)


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _plan_hash(plan: Mapping[str, Any]) -> str:
    """Hash only the actionable plan, not its display timestamp.

    ``plan`` and ``apply`` are intentionally separate commands.  Including
    ``generated_at`` would make a freshly rebuilt, otherwise identical plan
    fail confirmation every time the operator copied the hash from ``plan``.
    """
    return _hash({key: value for key, value in plan.items() if key != "generated_at"})


def _rows(name: str) -> list[dict[str, str]]:
    path = MASTER_ROOT / name
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def _find(rows: Iterable[Mapping[str, str]], key: str, value: str) -> dict[str, str]:
    row = next((dict(row) for row in rows if row.get(key) == value), None)
    if row is None:
        raise SyncError(f"基础主数据缺少 {key}={value}")
    return row


def _spec() -> dict[str, list[dict[str, Any]]]:
    company = {
        "doctype": "Company",
        "name": COMPANY_NAME,
        "document": {
            "company_name": COMPANY_NAME,
            "abbr": COMPANY_ABBR,
            "default_currency": "CNY",
            "country": "China",
            "is_group": 0,
        },
    }
    fiscal_year = {
        "doctype": "Fiscal Year",
        "name": "2026",
        "document": {
            "year": "2026",
            "year_start_date": "2026-01-01",
            "year_end_date": "2026-12-31",
            "disabled": 0,
            "companies": [{"company": COMPANY_NAME}],
        },
    }
    cost_center = _find(_rows("cost_centers.tsv"), "cost_center_code", "CC-HL-13")
    project = _find(_rows("projects.tsv"), "project_code", "PRJ-HL-13")
    warehouse = _find(_rows("warehouses.tsv"), "warehouse_code", "WH-HL-13")
    suppliers = [
        _find(_rows("suppliers.tsv"), "supplier_code", code)
        for code in ("SUP-TEST-A", "SUP-TEST-B")
    ]

    # The names are explicit so a second run can address the same documents.
    root_warehouse = {
        "doctype": "Warehouse",
        "name": "盛拓仓库 - NMT",
        "document": {
            "warehouse_name": "盛拓仓库 - NMT",
            "company": COMPANY_NAME,
            "is_group": 1,
        },
    }
    project_warehouse = {
        "doctype": "Warehouse",
        "name": warehouse["erpnext_warehouse_name"].replace(" - SD", " - NMT"),
        "document": {
            "warehouse_name": warehouse["erpnext_warehouse_name"].replace(" - SD", " - NMT"),
            "parent_warehouse": root_warehouse["name"],
            "company": COMPANY_NAME,
            "is_group": 0,
        },
    }
    cc_base_name = cost_center["cost_center_name"]
    cc_name = f"{cc_base_name} - {COMPANY_ABBR}"
    cost_center_doc = {
        "doctype": "Cost Center",
        "name": cc_name,
        "document": {
            # ERPNext's Cost Center autoname appends the company abbreviation
            # to ``cost_center_name``.  Keep the base name here so the planned
            # document name remains exactly ``<name> - NMT``.
            "cost_center_name": cc_base_name,
            "company": COMPANY_NAME,
            # ERPNext creates the company-named cost center as the group root.
            # ``Main - ABBR`` is a leaf/default cost center and cannot parent
            # another node.
            "parent_cost_center": f"{COMPANY_NAME} - {COMPANY_ABBR}",
            "is_group": 0,
        },
    }
    project_doc = {
        "doctype": "Project",
        "name": project["project_code"],
        "document": {
            "project_name": project["project_code"],
            "status": "Open",
            "company": COMPANY_NAME,
            "cost_center": cc_name,
            "expected_start_date": "2026-01-01",
        },
    }
    supplier_docs = [
        {
            "doctype": "Supplier",
            "name": row["supplier_name"],
            "document": {
            "supplier_name": row["supplier_name"],
            "supplier_type": "Company",
                "country": "China",
            },
        }
        for row in suppliers
    ]
    price_list = {
        "doctype": "Price List",
        "name": "Nexterp测试采购价目表",
        "document": {
            "price_list_name": "Nexterp测试采购价目表",
            "buying": 1,
            "selling": 0,
            "enabled": 1,
            "currency": "CNY",
        },
    }
    workflow_states = [
        {
            "doctype": "Workflow State",
            "name": state,
            "document": {"workflow_state_name": state},
        }
        for state in ("Nexterp材料草稿", "Nexterp主管审批", "Nexterp项目审批", "Nexterp已批准")
    ]
    workflow_actions = [
        {
            "doctype": "Workflow Action Master",
            "name": action,
            "document": {"workflow_action_name": action},
        }
        for action in ("提交", "主管通过", "项目通过", "退回")
    ]
    users = [
        {
            "doctype": "User",
            "name": row["email"],
            "document": {
                "email": row["email"],
                "first_name": row["full_name"],
                "enabled": 1,
                "send_welcome_email": 0,
                "language": "zh",
                "time_zone": "Asia/Shanghai",
                "roles": [{"role": role} for role in row["roles"]],
            },
        }
        for row in SANDBOX_USERS
    ]
    workflow = {
        "doctype": "Workflow",
        "name": "Nexterp材料申请三级审批",
        "document": {
            "workflow_name": "Nexterp材料申请三级审批",
            "document_type": "Material Request",
            "is_active": 1,
            "override_status": 1,
            "workflow_state_field": "workflow_state",
            "states": [
                {"state": "Nexterp材料草稿", "doc_status": "0", "allow_edit": "Purchase User"},
                {"state": "Nexterp主管审批", "doc_status": "0", "allow_edit": "Purchase Manager"},
                {"state": "Nexterp项目审批", "doc_status": "0", "allow_edit": "Projects Manager"},
                {"state": "Nexterp已批准", "doc_status": "1", "allow_edit": "Purchase Manager"},
            ],
            "transitions": [
                {"state": "Nexterp材料草稿", "action": "提交", "next_state": "Nexterp主管审批", "allowed": "Purchase User"},
                {"state": "Nexterp主管审批", "action": "主管通过", "next_state": "Nexterp项目审批", "allowed": "Purchase Manager"},
                {"state": "Nexterp项目审批", "action": "项目通过", "next_state": "Nexterp已批准", "allowed": "Projects Manager"},
                {"state": "Nexterp主管审批", "action": "退回", "next_state": "Nexterp材料草稿", "allowed": "Purchase Manager"},
                {"state": "Nexterp项目审批", "action": "退回", "next_state": "Nexterp材料草稿", "allowed": "Projects Manager"},
            ],
        },
    }
    return {
        "master": [company, fiscal_year, root_warehouse, project_warehouse, cost_center_doc, project_doc, *supplier_docs, price_list, *workflow_states, *workflow_actions],
        "users": users,
        "workflow": [workflow],
    }


def _compare(existing: Mapping[str, Any] | None, expected: Mapping[str, Any]) -> str:
    if existing is None:
        return "create"
    if existing.get("doctype") == "Fiscal Year" or expected.get("year") == "2026":
        scalar_fields = ("year", "year_start_date", "year_end_date", "disabled")
        if any(str(existing.get(field) or "") != str(expected.get(field) or "") for field in scalar_fields):
            return "conflict"
        actual_companies = {str(row.get("company") or "") for row in (existing.get("companies") or []) if isinstance(row, Mapping)}
        expected_companies = {str(row.get("company") or "") for row in (expected.get("companies") or []) if isinstance(row, Mapping)}
        return "existing" if expected_companies.issubset(actual_companies) else "conflict"
    if expected.get("document_type") == "Material Request" and "states" in expected:
        scalar_fields = ("workflow_name", "document_type", "is_active", "override_status", "workflow_state_field")
        if any(str(existing.get(field) or "") != str(expected.get(field) or "") for field in scalar_fields):
            return "conflict"
        actual_states = {
            (str(row.get("state") or ""), str(row.get("doc_status") or ""), str(row.get("allow_edit") or ""))
            for row in (existing.get("states") or [])
        }
        expected_states = {
            (str(row.get("state") or ""), str(row.get("doc_status") or ""), str(row.get("allow_edit") or ""))
            for row in (expected.get("states") or [])
        }
        actual_transitions = {
            (str(row.get("state") or ""), str(row.get("action") or ""), str(row.get("next_state") or ""), str(row.get("allowed") or ""))
            for row in (existing.get("transitions") or [])
        }
        expected_transitions = {
            (str(row.get("state") or ""), str(row.get("action") or ""), str(row.get("next_state") or ""), str(row.get("allowed") or ""))
            for row in (expected.get("transitions") or [])
        }
        return "existing" if actual_states == expected_states and actual_transitions == expected_transitions else "conflict"
    mismatches = {
        key: (existing.get(key), value)
        for key, value in expected.items()
        if key != "roles" and str(existing.get(key) or "") != str(value or "")
    }
    if mismatches:
        return "conflict"
    return "existing"


def make_plan(client: FrappeSessionClient) -> dict[str, Any]:
    spec = _spec()
    operations: list[dict[str, Any]] = []
    for section, records in spec.items():
        for record in records:
            logical_name = record["name"]
            existing = client.get_doc(record["doctype"], logical_name)
            # Project uses ERPNext's PROJ-.#### autoname and ignores a supplied
            # name.  Resolve it by its stable project_name instead, so reruns
            # remain idempotent and do not create a second project.
            if record["doctype"] == "Project":
                matches = client.list_docs(
                    "Project",
                    fields=["name", "project_name"],
                    filters=[["project_name", "=", record["document"]["project_name"]]],
                    limit=5,
                )
                if matches:
                    logical_name = matches[0]["name"]
                    existing = client.get_doc("Project", logical_name)
            action = _compare(existing, record["document"])
            operations.append({
                "section": section,
                "doctype": record["doctype"],
                "name": logical_name,
                "logical_name": record["name"],
                "action": action,
                "expected": record["document"],
            })
    return {
        "site": SITE_HOST,
        "generated_at": _now(),
        "operations": operations,
        "summary": {
            "create": sum(row["action"] == "create" for row in operations),
            "existing": sum(row["action"] == "existing" for row in operations),
            "conflict": sum(row["action"] == "conflict" for row in operations),
        },
    }


def _load_journal(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema_version": 1, "requests": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload.get("requests"), dict):
        raise SyncError("业务初始化 journal 格式无效")
    return payload


def _write_journal(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def apply_plan(client: FrappeSessionClient, plan: Mapping[str, Any], *, request_id: str, journal_path: Path) -> dict[str, Any]:
    try:
        uuid.UUID(request_id)
    except ValueError as exc:
        raise SyncError("request_id 必须是 UUID") from exc
    plan_hash = _plan_hash(plan)
    journal = _load_journal(journal_path)
    previous = journal["requests"].get(request_id)
    if previous:
        if previous.get("plan_hash") != plan_hash:
            raise SyncError("request_id 已用于另一份初始化计划")
        return dict(previous["result"])
    if plan["summary"]["conflict"]:
        raise SyncError("初始化计划存在冲突，拒绝覆盖现有账套数据")
    result = {"site": SITE_HOST, "request_id": request_id, "plan_hash": plan_hash, "created": [], "existing": []}
    for operation in plan["operations"]:
        if operation["action"] == "existing":
            result["existing"].append({"doctype": operation["doctype"], "name": operation["name"]})
            continue
        document = dict(operation["expected"])
        if operation["doctype"] != "Project":
            document["name"] = operation["name"]
        created_doc = client.create_doc(operation["doctype"], document)
        readback = created_doc if operation["doctype"] == "Project" else client.get_doc(operation["doctype"], operation["name"])
        if readback is None:
            raise SyncError(f"{operation['doctype']} 回读失败：{operation['name']}")
        if operation["doctype"] == "Project" and readback.get("project_name") != operation["expected"].get("project_name"):
            raise SyncError(f"Project 回读不匹配：{operation['expected'].get('project_name')}")
        result["created"].append({"doctype": operation["doctype"], "name": readback.get("name", operation["name"])})
    result["verified_at"] = _now()
    journal["requests"][request_id] = {"plan_hash": plan_hash, "result": result}
    _write_journal(journal_path, journal)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply", "verify"))
    parser.add_argument("--secret-file", type=Path, default=DEFAULT_SECRET_PATH)
    parser.add_argument("--journal", type=Path, default=DEFAULT_JOURNAL_PATH)
    parser.add_argument("--request-id")
    parser.add_argument("--confirm-plan-hash")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        client = _load_client(Path(args.secret_file))
        plan = make_plan(client)
        plan_hash = _plan_hash(plan)
        if args.action == "plan":
            print(json.dumps({"plan_hash": plan_hash, **plan}, ensure_ascii=False, indent=2))
            return 0 if not plan["summary"]["conflict"] else 2
        if args.action == "verify":
            verified = not plan["summary"]["create"] and not plan["summary"]["conflict"]
            print(json.dumps({"verified": verified, "plan_hash": plan_hash, **plan}, ensure_ascii=False, indent=2))
            return 0 if verified else 3
        if not args.request_id or args.confirm_plan_hash != plan_hash:
            raise SyncError("apply 需要 --request-id 和匹配当前 plan 的 --confirm-plan-hash")
        print(json.dumps(apply_plan(client, plan, request_id=args.request_id, journal_path=Path(args.journal)), ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
