from __future__ import annotations

import argparse
from datetime import date, datetime
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


REPORT_PATH = ROOT / "data" / "runtime" / "stock_movement_acceptance_report.json"
PROJECT_CODE = "PRJ-HL-13"
ERP_PROJECT = "PROJ-0010"
SOURCE_WAREHOUSE = "蕰川路基地仓库 - SD"
TARGET_WAREHOUSE = "合流1.3标仓库 - SD"
ITEM_CODE = "MAT-CEM-000008"
COMPANY = "STEC (Demo)"
USERS = {
    "stock_manager": "pan.feng@stec-up.local",
    "project_clerk": "mao.xiaoquan@stec-up.local",
}


def _save_report(report: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _require(result: Any, label: str) -> dict[str, Any]:
    if not result.ok:
        raise RuntimeError(result.user_message or result.error or f"{label}失败")
    if not isinstance(result.data, dict):
        raise RuntimeError(f"{label}未返回结构化结果")
    return result.data


def _balance(service: AgentWorkbenchService, user: str, warehouse: str) -> float:
    result = service.client(user).get_stock_balance(ITEM_CODE, warehouse=warehouse, limit=10)
    if not result.ok:
        raise RuntimeError(result.user_message or result.error or "读取库存失败")
    rows = result.data if isinstance(result.data, list) else []
    for row in rows:
        if isinstance(row, dict) and row.get("warehouse") == warehouse:
            return float(row.get("actual_qty") or 0)
    return 0.0


def _confirmation(user: str, reason: str) -> dict[str, Any]:
    return {
        "confirmed": True,
        "confirmed_by": user,
        "confirmed_at": datetime.now().astimezone().isoformat(),
        "confirmation_text": "已确认提交库存测试单据",
        "reason": reason,
        "approval_reference": "stock-movement-acceptance",
    }


def _submit(adapter: ERPNextAdapter, user: str, name: str, reason: str) -> dict[str, Any]:
    return _require(
        adapter.execute(
            {
                "tool": "erpnext.stock.submit_document",
                "arguments": {
                    "doctype": "Stock Entry",
                    "name": name,
                    "confirmation": _confirmation(user, reason),
                },
            }
        ),
        f"提交 {name}",
    )


def prepare(service: AgentWorkbenchService) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    for key, user in USERS.items():
        logged_in = service.client(user).get_logged_user()
        checks[f"identity:{key}"] = logged_in.ok and logged_in.data == user
    for warehouse in (SOURCE_WAREHOUSE, TARGET_WAREHOUSE):
        exists = service.client(USERS["stock_manager"]).document_exists("Warehouse", warehouse)
        checks[f"warehouse:{warehouse}"] = exists.ok and bool(exists.data)
    item_exists = service.client(USERS["stock_manager"]).document_exists("Item", ITEM_CODE)
    checks[f"item:{ITEM_CODE}"] = item_exists.ok and bool(item_exists.data)
    if not all(checks.values()):
        raise RuntimeError(f"库存闭环验收准备失败：{checks}")
    return {
        "ok": True,
        "checks": checks,
        "baseline": {
            "source": _balance(service, USERS["stock_manager"], SOURCE_WAREHOUSE),
            "target": _balance(service, USERS["stock_manager"], TARGET_WAREHOUSE),
        },
    }


def run(service: AgentWorkbenchService) -> dict[str, Any]:
    prepared = prepare(service)
    stock_user = USERS["stock_manager"]
    project_user = USERS["project_clerk"]
    stock_adapter = ERPNextAdapter(service.client(stock_user))
    project_adapter = ERPNextAdapter(service.client(project_user))
    report: dict[str, Any] = {
        "created_at": datetime.now().astimezone().isoformat(),
        "baseline": prepared["baseline"],
        "documents": [],
    }
    _save_report(report)

    seed = _require(
        stock_adapter.execute(
            {
                "tool": "erpnext.stock.create_entry_draft",
                "arguments": {
                    "stock_entry_type": "Material Receipt",
                    "purpose": "Material Receipt",
                    "company": COMPANY,
                    "posting_date": date.today().isoformat(),
                    "remarks": "库存调拨与项目领料闭环自动验收：建立来源仓测试库存。",
                    "items": [
                        {
                            "item_code": ITEM_CODE,
                            "qty": 3,
                            "uom": "包",
                            "t_warehouse": SOURCE_WAREHOUSE,
                            "basic_rate": 28,
                        }
                    ],
                },
            }
        ),
        "创建测试入库草稿",
    )
    seed_name = str(seed["name"])
    report["documents"].append({"doctype": "Stock Entry", "name": seed_name, "user": stock_user, "kind": "seed"})
    _save_report(report)
    _submit(stock_adapter, stock_user, seed_name, "建立库存闭环验收基线")

    transfer_context = _require(
        stock_adapter.execute(
            {
                "tool": "erpnext.stock.get_transfer_context",
                "arguments": {
                    "source_warehouse": SOURCE_WAREHOUSE,
                    "target_warehouse": TARGET_WAREHOUSE,
                    "items": [{"item_code": ITEM_CODE, "qty": 2, "uom": "包"}],
                },
            }
        ),
        "检查调拨条件",
    )
    if transfer_context.get("shortages"):
        raise RuntimeError(f"建立测试库存后仍存在调拨缺料：{transfer_context['shortages']}")

    transfer = _require(
        stock_adapter.execute(
            {
                "tool": "erpnext.stock.create_transfer_draft",
                "arguments": {
                    "source_warehouse": SOURCE_WAREHOUSE,
                    "target_warehouse": TARGET_WAREHOUSE,
                    "company": COMPANY,
                    "posting_date": date.today().isoformat(),
                    "project": ERP_PROJECT,
                    "remarks": "库存调拨与项目领料闭环自动验收：基地调拨至合流项目仓。",
                    "items": [{"item_code": ITEM_CODE, "qty": 2, "uom": "包"}],
                },
            }
        ),
        "创建库存调拨草稿",
    )
    transfer_name = str(transfer["name"])
    report["documents"].append({"doctype": "Stock Entry", "name": transfer_name, "user": stock_user, "kind": "transfer"})
    _save_report(report)
    _submit(stock_adapter, stock_user, transfer_name, "确认基地仓调拨到项目仓")
    transfer_impact = _require(
        stock_adapter.execute(
            {"tool": "erpnext.stock.verify_transfer_impact", "arguments": {"stock_entry": transfer_name}}
        ),
        "核验库存调拨影响",
    )

    issue = _require(
        project_adapter.execute(
            {
                "tool": "erpnext.projects.create_material_issue_draft",
                "arguments": {
                    "project": ERP_PROJECT,
                    "source_warehouse": TARGET_WAREHOUSE,
                    "company": COMPANY,
                    "posting_date": date.today().isoformat(),
                    "remarks": "库存调拨与项目领料闭环自动验收：项目班组领用。",
                    "items": [{"item_code": ITEM_CODE, "qty": 1, "uom": "包"}],
                },
            }
        ),
        "创建项目领料草稿",
    )
    issue_name = str(issue["name"])
    report["documents"].append({"doctype": "Stock Entry", "name": issue_name, "user": project_user, "kind": "issue"})
    _save_report(report)
    _submit(project_adapter, project_user, issue_name, "确认合流项目材料领用")
    issue_impact = _require(
        project_adapter.execute(
            {
                "tool": "erpnext.projects.verify_material_issue_cost_impact",
                "arguments": {"stock_entry": issue_name, "project": ERP_PROJECT},
            }
        ),
        "核验项目领料成本",
    )

    report["names"] = {"seed": seed_name, "transfer": transfer_name, "issue": issue_name}
    report["verification"] = {"transfer": transfer_impact, "issue": issue_impact}
    _save_report(report)
    return verify(service, report)


def verify(service: AgentWorkbenchService, report: dict[str, Any] | None = None) -> dict[str, Any]:
    report = report or json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    source = _balance(service, USERS["stock_manager"], SOURCE_WAREHOUSE)
    target = _balance(service, USERS["stock_manager"], TARGET_WAREHOUSE)
    baseline_source = float(report["baseline"]["source"])
    baseline_target = float(report["baseline"]["target"])
    transfer = report.get("verification", {}).get("transfer", {})
    issue = report.get("verification", {}).get("issue", {})
    checks = {
        "source_balance": source == baseline_source + 1,
        "target_balance": target == baseline_target + 1,
        "transfer_verified": transfer.get("status") == "Verified",
        "transfer_ledger_matched": all(row.get("matched") for row in transfer.get("comparisons") or []),
        "issue_submitted": issue.get("docstatus") == 1,
        "issue_has_project_row": bool(issue.get("items")),
        "issue_has_ledger": bool(issue.get("ledger_entries")),
    }
    result = {"ok": all(checks.values()), "checks": checks, "balances": {"source": source, "target": target}, "names": report["names"]}
    if not result["ok"]:
        raise RuntimeError(f"库存调拨与项目领料闭环验收失败：{result}")
    return result


def cleanup(service: AgentWorkbenchService) -> dict[str, Any]:
    if not REPORT_PATH.exists():
        return {"ok": True, "cancelled": [], "message": "没有库存闭环验收清单，无需清理。"}
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    cancelled: list[str] = []
    failed: list[dict[str, Any]] = []
    for entry in reversed(report.get("documents") or []):
        client = service.client(entry["user"])
        result = client.cancel_document(entry["doctype"], entry["name"])
        if result.ok:
            cancelled.append(entry["name"])
        else:
            failed.append({"name": entry["name"], "error": result.user_message or result.error})
    restored = {
        "source": _balance(service, USERS["stock_manager"], SOURCE_WAREHOUSE),
        "target": _balance(service, USERS["stock_manager"], TARGET_WAREHOUSE),
    }
    baseline = report.get("baseline") or {}
    inventory_restored = restored == {"source": float(baseline.get("source") or 0), "target": float(baseline.get("target") or 0)}
    if not failed and inventory_restored:
        REPORT_PATH.unlink(missing_ok=True)
    return {"ok": not failed and inventory_restored, "cancelled": cancelled, "failed": failed, "restored": restored, "inventory_restored": inventory_restored}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the repeatable stock transfer and project issue acceptance.")
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
