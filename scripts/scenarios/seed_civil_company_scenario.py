from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextClient
from nexterp_agent.erpnext.config import load_erpnext_settings

COMPANY = "STEC (Demo)"
COMPANY_ABBR = "SD"
PARENT_WAREHOUSE = "All Warehouses - SD"
COST_CENTER = "Main - SD"
STOCK_ADJUSTMENT_ACCOUNT = "Stock Adjustment - SD"
SCENARIO_PREFIX = "SCEN-CIVIL"
DEFAULT_REPORT = ROOT / "data" / "scenario" / "civil_company_seed_report.json"

WAREHOUSES = [
    {"warehouse_name": f"{SCENARIO_PREFIX} 中心仓", "role": "center"},
    {"warehouse_name": f"{SCENARIO_PREFIX} 项目仓", "role": "project"},
]

PROJECTS = [
    {"project_name": f"{SCENARIO_PREFIX} 城东道路改造项目", "short_name": "城东道路改造项目"},
    {"project_name": f"{SCENARIO_PREFIX} 南区排水管网项目", "short_name": "南区排水管网项目"},
    {"project_name": f"{SCENARIO_PREFIX} 西站配套设施项目", "short_name": "西站配套设施项目"},
]

SUPPLIERS = [
    {"supplier_name": f"{SCENARIO_PREFIX} 安科劳保用品", "supplier_group": "经销商"},
    {"supplier_name": f"{SCENARIO_PREFIX} 通达管材", "supplier_group": "原材料"},
    {"supplier_name": f"{SCENARIO_PREFIX} 强盛建材", "supplier_group": "原材料"},
    {"supplier_name": f"{SCENARIO_PREFIX} 恒信电气", "supplier_group": "电气"},
]

USERS = [
    {"email": "chen.jianguo@scen-civil.local", "first_name": "建国", "last_name": "陈", "role_title": "总经理"},
    {"email": "liu.min@scen-civil.local", "first_name": "敏", "last_name": "刘", "role_title": "财务主管"},
    {"email": "zhao.qiang@scen-civil.local", "first_name": "强", "last_name": "赵", "role_title": "采购主管"},
    {"email": "sun.li@scen-civil.local", "first_name": "丽", "last_name": "孙", "role_title": "行政采购员"},
    {"email": "wang.hai@scen-civil.local", "first_name": "海", "last_name": "王", "role_title": "仓库主管"},
    {"email": "zhou.peng@scen-civil.local", "first_name": "鹏", "last_name": "周", "role_title": "项目仓管员"},
    {"email": "li.zhiyuan@scen-civil.local", "first_name": "志远", "last_name": "李", "role_title": "项目经理"},
    {"email": "ma.chao@scen-civil.local", "first_name": "超", "last_name": "马", "role_title": "施工班组长"},
    {"email": "huang.wei@scen-civil.local", "first_name": "伟", "last_name": "黄", "role_title": "项目经理"},
    {"email": "guo.liang@scen-civil.local", "first_name": "亮", "last_name": "郭", "role_title": "施工班组长"},
    {"email": "he.shan@scen-civil.local", "first_name": "珊", "last_name": "何", "role_title": "项目经理"},
    {"email": "deng.kai@scen-civil.local", "first_name": "凯", "last_name": "邓", "role_title": "机电班组长"},
    {"email": "yuan.fang@scen-civil.local", "first_name": "芳", "last_name": "袁", "role_title": "供应商联络员"},
    {"email": "cao.rui@scen-civil.local", "first_name": "瑞", "last_name": "曹", "role_title": "质检员"},
    {"email": "xu.feng@scen-civil.local", "first_name": "峰", "last_name": "许", "role_title": "系统管理员"},
]

CENTER_STOCK = [
    {"item_code": "SAFE-000005", "qty": 300, "basic_rate": 8},
    {"item_code": "ELEC-000005", "qty": 60, "basic_rate": 4},
    {"item_code": "ELEC-000002", "qty": 120, "basic_rate": 3},
    {"item_code": "ELEC-000001", "qty": 4, "basic_rate": 380},
    {"item_code": "ELEC-000006", "qty": 20, "basic_rate": 35},
    {"item_code": "MAT-CEM-000004", "qty": 80, "basic_rate": 35},
    {"item_code": "PIPE-000415", "qty": 200, "basic_rate": 18},
    {"item_code": "PIPE-000021", "qty": 40, "basic_rate": 6},
    {"item_code": "PIPE-000019", "qty": 30, "basic_rate": 8},
    {"item_code": "MAT-000159", "qty": 6, "basic_rate": 180},
]

PROJECT_STOCK = [
    {"item_code": "SAFE-000005", "qty": 50, "basic_rate": 8},
    {"item_code": "ELEC-000005", "qty": 12, "basic_rate": 4},
    {"item_code": "MAT-CEM-000004", "qty": 20, "basic_rate": 35},
    {"item_code": "PIPE-000415", "qty": 60, "basic_rate": 18},
]


@dataclass
class SeedEvent:
    action: str
    doctype: str
    name: str
    ok: bool
    message: str = ""
    error_type: str = ""
    error: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed ERPNext sandbox data for the civil company day scenario.")
    parser.add_argument("--profile", default="local")
    parser.add_argument("--apply", action="store_true", help="Actually write to ERPNext. Default is dry-run.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--skip-stock", action="store_true", help="Skip initial stock receipt entries.")
    args = parser.parse_args()

    settings = load_erpnext_settings(args.profile)
    client = ERPNextClient(
        settings.base_url,
        settings.api_key,
        settings.api_secret,
        host_header=settings.host_header,
        timeout=60,
    )

    events: list[SeedEvent] = []
    context: dict[str, Any] = {"company": COMPANY, "warehouses": {}, "projects": {}, "suppliers": {}, "users": {}}

    assert_required_records(client)
    seed_warehouses(client, args.apply, context, events)
    seed_projects(client, args.apply, context, events)
    seed_suppliers(client, args.apply, context, events)
    seed_users(client, args.apply, context, events)
    if not args.skip_stock:
        seed_initial_stock(client, args.apply, context, events)

    summary = build_summary(args.apply, events, context)
    write_report(args.report, summary, events)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed_total"] == 0 else 1


def assert_required_records(client: ERPNextClient) -> None:
    required = [
        ("Company", COMPANY),
        ("Warehouse", PARENT_WAREHOUSE),
        ("Cost Center", COST_CENTER),
        ("Account", STOCK_ADJUSTMENT_ACCOUNT),
    ]
    for doctype, name in required:
        result = client.document_exists(doctype, name)
        if not result.ok or not result.data.get("exists"):
            raise RuntimeError(f"Required {doctype} is missing: {name}")

    missing_items = []
    for row in CENTER_STOCK + PROJECT_STOCK:
        result = client.document_exists("Item", row["item_code"])
        if not result.ok or not result.data.get("exists"):
            missing_items.append(row["item_code"])
    if missing_items:
        raise RuntimeError(f"Scenario stock items are missing: {', '.join(sorted(set(missing_items)))}")


def seed_warehouses(client: ERPNextClient, apply: bool, context: dict[str, Any], events: list[SeedEvent]) -> None:
    for warehouse in WAREHOUSES:
        existing = find_one(
            client,
            "Warehouse",
            {"warehouse_name": warehouse["warehouse_name"], "company": COMPANY},
            ["name", "warehouse_name", "company"],
        )
        if existing:
            context["warehouses"][warehouse["role"]] = existing["name"]
            events.append(SeedEvent("skip_existing", "Warehouse", existing["name"], True, "already exists"))
            continue

        target_name = expected_warehouse_name(warehouse["warehouse_name"])
        context["warehouses"][warehouse["role"]] = target_name
        if not apply:
            events.append(SeedEvent("dry_run_create", "Warehouse", target_name, True, "would create"))
            continue

        result = client.create_document(
            "Warehouse",
            {
                "doctype": "Warehouse",
                "warehouse_name": warehouse["warehouse_name"],
                "parent_warehouse": PARENT_WAREHOUSE,
                "company": COMPANY,
                "is_group": 0,
            },
        )
        append_result(events, "create", "Warehouse", target_name, result)
        if result.ok and isinstance(result.data, dict):
            context["warehouses"][warehouse["role"]] = result.data.get("name") or target_name


def seed_projects(client: ERPNextClient, apply: bool, context: dict[str, Any], events: list[SeedEvent]) -> None:
    for project in PROJECTS:
        existing = find_one(client, "Project", {"project_name": project["project_name"], "company": COMPANY}, ["name", "project_name"])
        if existing:
            context["projects"][project["short_name"]] = existing["name"]
            events.append(SeedEvent("skip_existing", "Project", existing["name"], True, "already exists"))
            continue

        if not apply:
            context["projects"][project["short_name"]] = project["project_name"]
            events.append(SeedEvent("dry_run_create", "Project", project["project_name"], True, "would create"))
            continue

        result = client.create_document(
            "Project",
            {
                "doctype": "Project",
                "project_name": project["project_name"],
                "company": COMPANY,
                "status": "Open",
            },
        )
        append_result(events, "create", "Project", project["project_name"], result)
        if result.ok and isinstance(result.data, dict):
            context["projects"][project["short_name"]] = result.data.get("name") or project["project_name"]


def seed_suppliers(client: ERPNextClient, apply: bool, context: dict[str, Any], events: list[SeedEvent]) -> None:
    for supplier in SUPPLIERS:
        existing = find_one(client, "Supplier", {"supplier_name": supplier["supplier_name"]}, ["name", "supplier_name"])
        if existing:
            context["suppliers"][supplier["supplier_name"]] = existing["name"]
            events.append(SeedEvent("skip_existing", "Supplier", existing["name"], True, "already exists"))
            continue

        if not apply:
            context["suppliers"][supplier["supplier_name"]] = supplier["supplier_name"]
            events.append(SeedEvent("dry_run_create", "Supplier", supplier["supplier_name"], True, "would create"))
            continue

        result = client.create_document(
            "Supplier",
            {
                "doctype": "Supplier",
                "supplier_name": supplier["supplier_name"],
                "supplier_group": supplier["supplier_group"],
                "supplier_type": "Company",
            },
        )
        append_result(events, "create", "Supplier", supplier["supplier_name"], result)
        if result.ok and isinstance(result.data, dict):
            context["suppliers"][supplier["supplier_name"]] = result.data.get("name") or supplier["supplier_name"]


def seed_users(client: ERPNextClient, apply: bool, context: dict[str, Any], events: list[SeedEvent]) -> None:
    for user in USERS:
        user_label = f"{user['last_name']}{user['first_name']}（{user['role_title']}）"
        result = client.document_exists("User", user["email"])
        if result.ok and result.data.get("exists"):
            context["users"][user_label] = user["email"]
            events.append(SeedEvent("skip_existing", "User", user["email"], True, "already exists"))
            continue

        if not apply:
            context["users"][user_label] = user["email"]
            events.append(SeedEvent("dry_run_create", "User", user["email"], True, "would create disabled user"))
            continue

        result = client.create_document(
            "User",
            {
                "doctype": "User",
                "email": user["email"],
                "first_name": user["first_name"],
                "last_name": user["last_name"],
                "enabled": 0,
                "send_welcome_email": 0,
                "user_type": "System User",
                "bio": f"{SCENARIO_PREFIX} scenario user: {user['role_title']}",
            },
        )
        append_result(events, "create", "User", user["email"], result)
        if result.ok:
            context["users"][user_label] = user["email"]


def seed_initial_stock(client: ERPNextClient, apply: bool, context: dict[str, Any], events: list[SeedEvent]) -> None:
    center_warehouse = context["warehouses"].get("center")
    project_warehouse = context["warehouses"].get("project")
    if not center_warehouse or not project_warehouse:
        events.append(SeedEvent("skip", "Stock Entry", "initial stock", False, error="Warehouses are not available"))
        return

    create_stock_receipt(client, apply, "CENTER", center_warehouse, CENTER_STOCK, events)
    create_stock_receipt(client, apply, "PROJECT", project_warehouse, PROJECT_STOCK, events)


def create_stock_receipt(
    client: ERPNextClient,
    apply: bool,
    marker_suffix: str,
    warehouse: str,
    items: list[dict[str, Any]],
    events: list[SeedEvent],
) -> None:
    marker = f"{SCENARIO_PREFIX}-SEED-STOCK-{marker_suffix}"
    existing = client.search_documents(
        "Stock Entry",
        filters={"remarks": ["like", f"%{marker}%"], "docstatus": ["!=", 2]},
        fields=["name", "docstatus", "remarks"],
        limit=1,
    )
    if existing.ok and existing.data:
        name = existing.data[0]["name"]
        events.append(SeedEvent("skip_existing", "Stock Entry", name, True, f"stock seed already exists: {marker}"))
        return

    if not apply:
        events.append(SeedEvent("dry_run_create_submit", "Stock Entry", marker, True, f"would create and submit stock receipt into {warehouse}"))
        return

    stock_items = []
    for row in items:
        item = client.get_document("Item", row["item_code"])
        if not item.ok:
            append_result(events, "read", "Item", row["item_code"], item)
            continue
        item_data = item.data or {}
        stock_uom = item_data.get("stock_uom")
        stock_items.append(
            {
                "item_code": row["item_code"],
                "qty": row["qty"],
                "t_warehouse": warehouse,
                "uom": stock_uom,
                "stock_uom": stock_uom,
                "conversion_factor": 1,
                "basic_rate": row["basic_rate"],
                "allow_zero_valuation_rate": 0,
                "expense_account": STOCK_ADJUSTMENT_ACCOUNT,
                "cost_center": COST_CENTER,
            }
        )

    create_result = client.create_stock_entry_draft(
        {
            "stock_entry_type": "Material Receipt",
            "purpose": "Material Receipt",
            "company": COMPANY,
            "posting_date": date.today().isoformat(),
            "remarks": marker,
            "items": stock_items,
        }
    )
    if not create_result.ok:
        append_result(events, "create", "Stock Entry", marker, create_result)
        return

    stock_entry_name = create_result.data.get("name") if isinstance(create_result.data, dict) else marker
    events.append(SeedEvent("create", "Stock Entry", stock_entry_name, True, "created draft"))
    submit_result = client.submit_document("Stock Entry", stock_entry_name)
    append_result(events, "submit", "Stock Entry", stock_entry_name, submit_result)


def find_one(client: ERPNextClient, doctype: str, filters: dict[str, Any], fields: list[str]) -> dict[str, Any] | None:
    result = client.search_documents(doctype, filters=filters, fields=fields, limit=1)
    if not result.ok:
        raise RuntimeError(result.error or result.user_message or f"Cannot search {doctype}")
    rows = result.data if isinstance(result.data, list) else []
    return rows[0] if rows else None


def expected_warehouse_name(warehouse_name: str) -> str:
    return f"{warehouse_name} - {COMPANY_ABBR}"


def append_result(events: list[SeedEvent], action: str, doctype: str, name: str, result: Any) -> None:
    if result.ok:
        events.append(SeedEvent(action, doctype, name, True, "ok"))
    else:
        events.append(
            SeedEvent(
                action,
                doctype,
                name,
                False,
                result.user_message or "",
                result.error_type or "",
                result.error or "",
            )
        )


def build_summary(apply: bool, events: list[SeedEvent], context: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    failed_total = 0
    for event in events:
        key = f"{event.action}_{event.doctype}".replace(" ", "_").lower()
        counts[key] = counts.get(key, 0) + 1
        if not event.ok:
            failed_total += 1
    return {
        "mode": "apply" if apply else "dry_run",
        "scenario_prefix": SCENARIO_PREFIX,
        "company": COMPANY,
        "failed_total": failed_total,
        "counts": counts,
        "context": context,
    }


def write_report(path: Path, summary: dict[str, Any], events: list[SeedEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"summary": summary, "events": [asdict(event) for event in events]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
