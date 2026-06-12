from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextAdapter, ERPNextClient, ToolCall
from nexterp_agent.erpnext.config import load_erpnext_settings

COMPANY = "STEC (Demo)"
PROJECT_CHENGDONG = "PROJ-0004"
CENTER_WAREHOUSE = "SCEN-CIVIL 中心仓 - SD"
PROJECT_WAREHOUSE = "SCEN-CIVIL 项目仓 - SD"
SUPPLIER_LABOR = "SCEN-CIVIL 安科劳保用品"
DEFAULT_REPORT = ROOT / "data" / "scenario" / "civil_company_day_run_report.json"


@dataclass
class ScenarioStep:
    id: str
    time: str
    actor: str
    event: str
    tool: str
    arguments: dict[str, Any]
    writes: bool = False
    expected_gap: str = ""


@dataclass
class ScenarioStepResult:
    id: str
    time: str
    actor: str
    event: str
    status: str
    writes: bool
    tool_call: dict[str, Any]
    tool_result: dict[str, Any] | None = None
    expected_gap: str = ""
    note: str = ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the civil company day scenario through ERPNext ToolCalls.")
    parser.add_argument("--profile", default="local")
    parser.add_argument("--apply", action="store_true", help="Execute write ToolCalls that create draft documents.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    settings = load_erpnext_settings(args.profile)
    client = ERPNextClient(
        settings.base_url,
        settings.api_key,
        settings.api_secret,
        host_header=settings.host_header,
        timeout=60,
    )
    adapter = ERPNextAdapter(client)

    steps = build_steps()
    results = [run_step(adapter, step, apply=args.apply) for step in steps]
    summary = summarize(results, apply=args.apply)
    write_report(args.report, summary, results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["failed"] == 0 else 1


def build_steps() -> list[ScenarioStep]:
    today = date.today()
    required_by = today + timedelta(days=1)
    return [
        ScenarioStep(
            id="08-00-auth-smoke",
            time="08:00",
            actor="陈建国，总经理",
            event="确认当前 ERPNext API 会话可用",
            tool="erpnext.get_logged_user",
            arguments={},
        ),
        ScenarioStep(
            id="08-20-search-gloves",
            time="08:20",
            actor="马超，施工班组长",
            event="城东项目提报帆布手套需求前检索物料",
            tool="erpnext.search_items",
            arguments={"query": "帆布手套", "limit": 5},
        ),
        ScenarioStep(
            id="08-20-create-material-request",
            time="08:20",
            actor="马超，施工班组长",
            event="创建城东项目劳保用品材料申请草稿",
            tool="erpnext.buying.create_material_request_draft",
            arguments={
                "material_request_type": "Purchase",
                "company": COMPANY,
                "schedule_date": required_by.isoformat(),
                "items": [
                    {
                        "item_code": "SAFE-000005",
                        "qty": 20,
                        "uom": "双",
                        "schedule_date": required_by.isoformat(),
                        "warehouse": PROJECT_WAREHOUSE,
                        "project": PROJECT_CHENGDONG,
                        "description": "城东道路改造项目劳保用品需求：帆布手套。",
                    }
                ],
            },
            writes=True,
        ),
        ScenarioStep(
            id="09-30-search-pending-mr",
            time="09:30",
            actor="赵强，采购主管",
            event="采购汇总待处理材料申请",
            tool="erpnext.search_documents",
            arguments={
                "doctype": "Material Request",
                "filters": {"material_request_type": "Purchase", "docstatus": 0},
                "fields": ["name", "title", "status", "transaction_date", "schedule_date", "company"],
                "limit": 10,
                "order_by": "modified desc",
            },
        ),
        ScenarioStep(
            id="10-00-create-po-draft",
            time="10:00",
            actor="孙丽，行政采购员",
            event="常用劳保用品创建采购订单草稿",
            tool="erpnext.buying.create_purchase_order_draft",
            arguments={
                "supplier": SUPPLIER_LABOR,
                "company": COMPANY,
                "transaction_date": today.isoformat(),
                "schedule_date": required_by.isoformat(),
                "items": [{"item_code": "SAFE-000005", "qty": 20, "uom": "双", "warehouse": CENTER_WAREHOUSE, "rate": 8}],
            },
            writes=True,
            expected_gap="MR 到 PO wrapper 已实现；runner 仍需支持读取上一步 MR、提交后再用 wrapper 生成 PO。",
        ),
        ScenarioStep(
            id="11-20-check-center-stock",
            time="11:20",
            actor="王海，仓库主管",
            event="中心仓检查帆布手套库存",
            tool="erpnext.stock.get_balance",
            arguments={"item_code": "SAFE-000005", "warehouse": CENTER_WAREHOUSE},
        ),
        ScenarioStep(
            id="13-30-create-pr-draft",
            time="13:30",
            actor="王海，仓库主管",
            event="供应商送来劳保用品，创建采购收货草稿",
            tool="erpnext.buying.create_purchase_receipt_draft",
            arguments={
                "supplier": SUPPLIER_LABOR,
                "company": COMPANY,
                "posting_date": today.isoformat(),
                "items": [{"item_code": "SAFE-000005", "qty": 20, "uom": "双", "warehouse": CENTER_WAREHOUSE, "rate": 8}],
            },
            writes=True,
            expected_gap="PR 草稿未从已提交 PO 自动生成，PO 到 PR 引用关系需要后续 wrapper 验收。",
        ),
        ScenarioStep(
            id="14-30-project-issue-context",
            time="14:30",
            actor="周鹏，项目仓管员",
            event="项目仓预览城东项目领料是否足够",
            tool="erpnext.projects.get_material_issue_context",
            arguments={
                "project": PROJECT_CHENGDONG,
                "source_warehouse": PROJECT_WAREHOUSE,
                "items": [{"item_code": "SAFE-000005", "qty": 10, "uom": "双", "description": "城东项目班组领用帆布手套。"}],
            },
        ),
        ScenarioStep(
            id="14-30-create-material-issue",
            time="14:30",
            actor="周鹏，项目仓管员",
            event="创建城东项目领料出库草稿",
            tool="erpnext.projects.create_material_issue_draft",
            arguments={
                "project": PROJECT_CHENGDONG,
                "source_warehouse": PROJECT_WAREHOUSE,
                "company": COMPANY,
                "posting_date": today.isoformat(),
                "remarks": "SCEN-CIVIL day runner: 城东项目帆布手套领料草稿",
                "items": [{"item_code": "SAFE-000005", "qty": 10, "uom": "双", "description": "城东项目班组领用帆布手套。"}],
            },
            writes=True,
        ),
        ScenarioStep(
            id="16-00-accounts-payable",
            time="16:00",
            actor="刘敏，财务主管",
            event="财务查看应付账款报表",
            tool="erpnext.accounting.accounts_payable",
            arguments={"company": COMPANY, "from_date": today.replace(day=1).isoformat(), "to_date": today.isoformat()},
            expected_gap="如果当天只创建草稿、不提交采购发票，应付报表不会体现新增业务。",
        ),
    ]


def run_step(adapter: ERPNextAdapter, step: ScenarioStep, *, apply: bool) -> ScenarioStepResult:
    call = ToolCall.from_dict(
        {
            "tool": step.tool,
            "arguments": step.arguments,
            "reason": step.event,
            "user_context": {"actor": step.actor, "scenario_step": step.id},
        }
    )
    if step.writes and not apply:
        return ScenarioStepResult(
            id=step.id,
            time=step.time,
            actor=step.actor,
            event=step.event,
            status="skipped_write",
            writes=step.writes,
            tool_call=call.to_dict(),
            expected_gap=step.expected_gap,
            note="Write ToolCall skipped. Re-run with --apply to create draft documents.",
        )
    result = adapter.execute(call)
    return ScenarioStepResult(
        id=step.id,
        time=step.time,
        actor=step.actor,
        event=step.event,
        status="ok" if result.ok else "failed",
        writes=step.writes,
        tool_call=call.to_dict(),
        tool_result=result.to_dict(),
        expected_gap=step.expected_gap,
    )


def summarize(results: list[ScenarioStepResult], *, apply: bool) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    failed = counts.get("failed", 0)
    return {
        "mode": "apply" if apply else "dry_run",
        "company": COMPANY,
        "scenario": "civil-company-day",
        "step_total": len(results),
        "executed": counts.get("ok", 0) + failed,
        "skipped_write": counts.get("skipped_write", 0),
        "failed": failed,
        "counts": counts,
        "report_note": (
            "Apply mode executed write ToolCalls that create draft documents only; no submit ToolCalls are included."
            if apply
            else "Dry-run executes read-only ToolCalls and skips draft-creating ToolCalls."
        ),
    }


def write_report(path: Path, summary: dict[str, Any], results: list[ScenarioStepResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"summary": summary, "steps": [asdict(result) for result in results]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
