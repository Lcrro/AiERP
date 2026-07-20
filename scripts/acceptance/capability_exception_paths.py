from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys
from typing import Any, Callable
from uuid import uuid4

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.agent_runtime.business_capabilities import (  # noqa: E402
    BusinessIntentDraft,
    CapabilityCompilationError,
    FinanceBusinessIntentDraft,
    FinanceCapabilityCompiler,
    ProcurementCapabilityCompiler,
    ProjectBusinessIntentDraft,
    ProjectCapabilityCompiler,
)
from nexterp_agent.erpnext import ERPNextAdapter  # noqa: E402
from nexterp_agent.workbench.server import AgentWorkbenchService  # noqa: E402


REPORT_PATH = ROOT / "data" / "runtime" / "capability_exception_paths_report.json"
LAST_REPORT_PATH = ROOT / "data" / "runtime" / "capability_exception_paths_last_report.json"
COMPANY = "STEC (Demo)"
CURRENT_PROJECT = "PROJ-0010"
OTHER_PROJECT = "PROJ-0011"
WAREHOUSE = "合流1.3标仓库 - SD"
ITEM_CODE = "MAT-CEM-000008"
SUPPLIER = "测试建材供应商甲"
USERS = {
    "buying": "pan.feng@stec-up.local",
    "project": "hu.yinhu@stec-up.local",
    "finance": "fang.wenqian@stec-up.local",
}
COUNT_USERS = {
    "Request for Quotation": USERS["buying"],
    "Purchase Order": USERS["buying"],
    "Task": USERS["project"],
    "Journal Entry": USERS["finance"],
}


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _require(result: Any, label: str) -> dict[str, Any]:
    if not result.ok or not isinstance(result.data, dict) or not result.data.get("name"):
        raise RuntimeError(result.user_message or result.error or f"{label}失败")
    return result.data


def _loader(service: AgentWorkbenchService, user: str) -> Callable[[str, str], dict[str, Any]]:
    client = service.client(user)

    def load(doctype: str, name: str) -> dict[str, Any]:
        result = client.get_document(doctype, name)
        if not result.ok or not isinstance(result.data, dict):
            raise RuntimeError(result.user_message or result.error or f"无法读取 {doctype} {name}")
        snapshot = dict(result.data)
        snapshot.setdefault("doctype", doctype)
        snapshot.setdefault("name", name)
        return snapshot

    return load


def _count(service: AgentWorkbenchService, user: str, doctype: str) -> int:
    result = service.client(user).count_documents(doctype)
    if not result.ok:
        raise RuntimeError(result.user_message or result.error or f"无法统计 {doctype}")
    if isinstance(result.data, dict):
        return int(result.data.get("count") or 0)
    return int(result.data or 0)


def _fingerprint(document: dict[str, Any]) -> dict[str, Any]:
    return {
        key: document.get(key)
        for key in ("doctype", "name", "docstatus", "modified", "project", "status", "valid_till")
        if key in document
    }


def _expect_rejection(case: str, compile_action: Callable[[], Any], expected: str) -> dict[str, Any]:
    try:
        prepared = compile_action()
    except CapabilityCompilationError as exc:
        message = str(exc)
        return {
            "ok": expected in message,
            "case": case,
            "expected_fragment": expected,
            "message": message,
            "questions": list(exc.questions),
            "tool_call_generated": False,
        }
    return {
        "ok": False,
        "case": case,
        "expected_fragment": expected,
        "message": "Capability 未拒绝非法路径。",
        "tool_call_generated": bool(getattr(prepared, "tool_call", None)),
        "unexpected_tool_call": getattr(prepared, "tool_call", None),
    }


def prepare(service: AgentWorkbenchService) -> dict[str, Any]:
    buying = service.client(USERS["buying"])
    if buying.base_url not in {"http://localhost:8002", "http://127.0.0.1:8002"}:
        raise RuntimeError(f"异常写入验收只允许本地 civil 站点，当前地址：{buying.base_url}")

    checks: dict[str, bool] = {}
    for role, user in USERS.items():
        identity = service.client(user).get_logged_user()
        checks[f"identity:{role}"] = identity.ok and identity.data == user
    for doctype, name in (
        ("Project", CURRENT_PROJECT),
        ("Project", OTHER_PROJECT),
        ("Warehouse", WAREHOUSE),
        ("Item", ITEM_CODE),
        ("Supplier", SUPPLIER),
    ):
        exists = buying.document_exists(doctype, name)
        checks[f"{doctype}:{name}"] = exists.ok and bool((exists.data or {}).get("exists"))
    if not all(checks.values()):
        raise RuntimeError(f"异常验收主数据或身份未就绪：{checks}")

    run_id = f"cap-ex-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}"
    report: dict[str, Any] = {
        "run_id": run_id,
        "started_at": datetime.now().astimezone().isoformat(),
        "checks": checks,
        "documents": [],
        "cases": {},
    }
    _save(REPORT_PATH, report)

    buying_adapter = ERPNextAdapter(buying)
    schedule_date = (date.today() + timedelta(days=3)).isoformat()
    material_request = _require(
        buying_adapter.execute(
            {
                "tool": "erpnext.buying.create_material_request_draft",
                "arguments": {
                    "material_request_type": "Purchase",
                    "schedule_date": schedule_date,
                    "company": COMPANY,
                    "items": [
                        {
                            "item_code": ITEM_CODE,
                            "qty": 1,
                            "uom": "包",
                            "warehouse": WAREHOUSE,
                            "schedule_date": schedule_date,
                            "project": CURRENT_PROJECT,
                        }
                    ],
                },
            }
        ),
        "创建草稿材料申请夹具",
    )
    report["documents"].append(
        {"doctype": "Material Request", "name": material_request["name"], "user": USERS["buying"]}
    )
    _save(REPORT_PATH, report)

    quotation = _require(
        buying_adapter.execute(
            {
                "tool": "erpnext.buying.create_supplier_quotation_draft",
                "arguments": {
                    "supplier": SUPPLIER,
                    "transaction_date": (date.today() - timedelta(days=2)).isoformat(),
                    "valid_till": (date.today() - timedelta(days=1)).isoformat(),
                    "company": COMPANY,
                    "terms": f"{run_id} 过期报价异常路径夹具。",
                    "items": [{"item_code": ITEM_CODE, "qty": 1, "uom": "包", "rate": 28}],
                },
            }
        ),
        "创建过期供应商报价夹具",
    )
    report["documents"].append(
        {"doctype": "Supplier Quotation", "name": quotation["name"], "user": USERS["buying"]}
    )
    _save(REPORT_PATH, report)
    submitted = buying.submit_document("Supplier Quotation", str(quotation["name"]))
    if not submitted.ok:
        raise RuntimeError(submitted.user_message or submitted.error or "提交过期供应商报价夹具失败")

    project_adapter = ERPNextAdapter(service.client(USERS["project"]))
    task = _require(
        project_adapter.execute(
            {
                "tool": "erpnext.projects.create_task",
                "arguments": {
                    "project": CURRENT_PROJECT,
                    "subject": f"{run_id} 跨项目更新拦截夹具",
                    "priority": "Medium",
                    "exp_start_date": date.today().isoformat(),
                    "exp_end_date": schedule_date,
                },
            }
        ),
        "创建项目任务夹具",
    )
    report["documents"].append({"doctype": "Task", "name": task["name"], "user": USERS["project"]})
    _save(REPORT_PATH, report)

    journal = _require(
        service.client(USERS["finance"]).create_document(
            "Journal Entry",
            {
                "doctype": "Journal Entry",
                "voucher_type": "Journal Entry",
                "posting_date": date.today().isoformat(),
                "company": COMPANY,
                "user_remark": f"{run_id} 草稿财务冲销拦截夹具",
                "accounts": [
                    {"account": "Cash - SD", "debit_in_account_currency": 1, "credit_in_account_currency": 0},
                    {
                        "account": "Administrative Expenses - SD",
                        "debit_in_account_currency": 0,
                        "credit_in_account_currency": 1,
                    },
                ],
            },
        ),
        "创建草稿日记账夹具",
    )
    report["documents"].append(
        {"doctype": "Journal Entry", "name": journal["name"], "user": USERS["finance"]}
    )
    report["fixture"] = {
        "draft_material_request": material_request["name"],
        "expired_supplier_quotation": quotation["name"],
        "project_task": task["name"],
        "draft_journal_entry": journal["name"],
    }
    _save(REPORT_PATH, report)
    return report


def run(service: AgentWorkbenchService, report: dict[str, Any]) -> dict[str, Any]:
    fixture = report["fixture"]
    loaders = {role: _loader(service, user) for role, user in USERS.items()}
    sources = {
        "draft_material_request": loaders["buying"]("Material Request", fixture["draft_material_request"]),
        "expired_supplier_quotation": loaders["buying"](
            "Supplier Quotation", fixture["expired_supplier_quotation"]
        ),
        "project_task": loaders["project"]("Task", fixture["project_task"]),
        "draft_journal_entry": loaders["finance"]("Journal Entry", fixture["draft_journal_entry"]),
    }
    before_fingerprints = {key: _fingerprint(value) for key, value in sources.items()}
    before_counts = {
        doctype: _count(service, user, doctype) for doctype, user in COUNT_USERS.items()
    }

    procurement = ProcurementCapabilityCompiler(loaders["buying"])
    project = ProjectCapabilityCompiler(loaders["project"])
    finance = FinanceCapabilityCompiler(loaders["finance"])
    cases = {
        "draft_material_request_to_rfq": _expect_rejection(
            "draft_material_request_to_rfq",
            lambda: procurement.compile(
                BusinessIntentDraft.from_dict(
                    {
                        "goal": "create_rfq_from_material_request",
                        "source_document": {
                            "doctype": "Material Request",
                            "name": fixture["draft_material_request"],
                        },
                        "suppliers": [SUPPLIER],
                    }
                ),
                runtime_context={"company": COMPANY, "project": CURRENT_PROJECT, "warehouse": WAREHOUSE},
                today=date.today(),
            ),
            "当前状态不能执行",
        ),
        "expired_quotation_to_purchase_order": _expect_rejection(
            "expired_quotation_to_purchase_order",
            lambda: procurement.compile(
                BusinessIntentDraft.from_dict(
                    {
                        "goal": "create_purchase_order_from_supplier_quotation",
                        "source_document": {
                            "doctype": "Supplier Quotation",
                            "name": fixture["expired_supplier_quotation"],
                        },
                        "schedule_date": (date.today() + timedelta(days=3)).isoformat(),
                    }
                ),
                runtime_context={"company": COMPANY, "project": CURRENT_PROJECT, "warehouse": WAREHOUSE},
                today=date.today(),
            ),
            "失效",
        ),
        "cross_project_task_update": _expect_rejection(
            "cross_project_task_update",
            lambda: project.compile(
                ProjectBusinessIntentDraft.from_dict(
                    {
                        "goal": "update_project_task",
                        "source_document": {"doctype": "Task", "name": fixture["project_task"]},
                        "project": OTHER_PROJECT,
                        "progress": 50,
                    }
                ),
                runtime_context={"company": COMPANY, "project": OTHER_PROJECT},
                today=date.today(),
            ),
            "与当前项目",
        ),
        "cancel_draft_financial_document": _expect_rejection(
            "cancel_draft_financial_document",
            lambda: finance.compile(
                FinanceBusinessIntentDraft.from_dict(
                    {
                        "goal": "cancel_financial_document",
                        "source_document": {
                            "doctype": "Journal Entry",
                            "name": fixture["draft_journal_entry"],
                        },
                        "reason": "异常路径验收，不应真正取消。",
                    }
                ),
                runtime_context={"company": COMPANY},
                today=date.today(),
            ),
            "只有已提交",
        ),
    }

    after_sources = {
        "draft_material_request": loaders["buying"]("Material Request", fixture["draft_material_request"]),
        "expired_supplier_quotation": loaders["buying"](
            "Supplier Quotation", fixture["expired_supplier_quotation"]
        ),
        "project_task": loaders["project"]("Task", fixture["project_task"]),
        "draft_journal_entry": loaders["finance"]("Journal Entry", fixture["draft_journal_entry"]),
    }
    after_fingerprints = {key: _fingerprint(value) for key, value in after_sources.items()}
    after_counts = {
        doctype: _count(service, user, doctype) for doctype, user in COUNT_USERS.items()
    }
    integrity = {
        "source_documents_unchanged": before_fingerprints == after_fingerprints,
        "document_counts_unchanged": before_counts == after_counts,
        "before_counts": before_counts,
        "after_counts": after_counts,
        "before_sources": before_fingerprints,
        "after_sources": after_fingerprints,
    }
    result = {
        "ok": all(case["ok"] and not case["tool_call_generated"] for case in cases.values())
        and integrity["source_documents_unchanged"]
        and integrity["document_counts_unchanged"],
        "run_id": report["run_id"],
        "cases": cases,
        "integrity": integrity,
    }
    report["cases"] = cases
    report["integrity"] = integrity
    report["run_result"] = result
    _save(REPORT_PATH, report)
    return result


def cleanup(service: AgentWorkbenchService, report: dict[str, Any]) -> dict[str, Any]:
    removed: list[dict[str, str]] = []
    failed: list[dict[str, Any]] = []
    for entry in reversed(report.get("documents") or []):
        doctype = str(entry["doctype"])
        name = str(entry["name"])
        user = str(entry["user"])
        client = service.client(user)
        detail = client.get_document(doctype, name)
        if not detail.ok:
            continue
        docstatus = int((detail.data or {}).get("docstatus") or 0)
        if docstatus == 1:
            cancelled = client.cancel_document(doctype, name)
            if not cancelled.ok:
                failed.append(
                    {"doctype": doctype, "name": name, "stage": "cancel", "error": cancelled.user_message or cancelled.error}
                )
                continue
        deleted = client.delete_document(doctype, name)
        if deleted.ok:
            removed.append({"doctype": doctype, "name": name})
        else:
            failed.append(
                {"doctype": doctype, "name": name, "stage": "delete", "error": deleted.user_message or deleted.error}
            )
    return {"ok": not failed, "removed": removed, "failed": failed}


def run_all(service: AgentWorkbenchService) -> dict[str, Any]:
    if REPORT_PATH.exists():
        previous = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        previous_cleanup = cleanup(service, previous)
        if not previous_cleanup["ok"]:
            raise RuntimeError(f"上一次异常验收夹具未能清理：{previous_cleanup}")
        REPORT_PATH.unlink(missing_ok=True)
    report = prepare(service)
    result: dict[str, Any]
    try:
        result = run(service, report)
    except Exception as exc:
        result = {"ok": False, "run_id": report["run_id"], "error": f"{type(exc).__name__}: {exc}"}
    finally:
        cleanup_result = cleanup(service, report)
    final = {
        **result,
        "ok": bool(result.get("ok")) and bool(cleanup_result.get("ok")),
        "cleanup": cleanup_result,
        "finished_at": datetime.now().astimezone().isoformat(),
    }
    _save(LAST_REPORT_PATH, final)
    if final["ok"]:
        REPORT_PATH.unlink(missing_ok=True)
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Capability rejection paths against the local civil ERPNext site.")
    parser.add_argument("command", nargs="?", choices=["all"], default="all")
    parser.parse_args()
    load_dotenv(ROOT / ".env")
    result = run_all(AgentWorkbenchService("civil"))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
