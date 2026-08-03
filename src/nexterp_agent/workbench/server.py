from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from copy import deepcopy
from typing import Any, Callable
from urllib.parse import parse_qs, quote, urlparse
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[3]

from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime
from nexterp_agent.agent_runtime.credentials import load_user_credentials
from nexterp_agent.agent_runtime.operation_catalog import MaterialRequestOperationCatalog
from nexterp_agent.agent_runtime.operation_reference_data import OperationReferenceDataCatalog
from nexterp_agent.agent_runtime.session import RuntimeSessionStore
from nexterp_agent.capability_service.catalog import CapabilityCatalogRepository
from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.master_data import MasterDataRelease
from nexterp_agent.workbench.openclaw_compare import OpenClawPreviewRunner, summarize_existing_result
from nexterp_agent.workbench.openclaw_runtime import OpenClawWorkbenchRunner, workbench_external_subject


HTML_PATH = ROOT / "tools" / "agent_workbench.html"
RUNTIME_EXPLORER_PATH = ROOT / "tools" / "agent_runtime_explorer.html"
OPERATION_MODEL_PATH = ROOT / "tools" / "operation_model_explorer.html"
RUNTIME_COMPARE_PATH = ROOT / "tools" / "agent_runtime_compare.html"
ASSET_DIR = ROOT / "tools" / "workbench"
ASSET_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
DOCTYPE_ROUTES = {
    "Material Request": "material-request",
    "Request for Quotation": "request-for-quotation",
    "Supplier Quotation": "supplier-quotation",
    "Purchase Order": "purchase-order",
    "Purchase Receipt": "purchase-receipt",
    "Purchase Invoice": "purchase-invoice",
    "Stock Entry": "stock-entry",
    "Project": "project",
    "ToDo": "todo",
}
DOCUMENT_MODULES = (
    ("buying", "采购", (
        ("Material Request", "材料申请", "Material Request Item"),
        ("Request for Quotation", "询价单", None),
        ("Supplier Quotation", "供应商报价", "Supplier Quotation Item"),
        ("Purchase Order", "采购订单", "Purchase Order Item"),
        ("Purchase Receipt", "采购收货", "Purchase Receipt Item"),
    )),
    ("stock", "库存", (
        ("Stock Entry", "库存移动", "Stock Entry Detail"),
    )),
    ("accounting", "财务", (
        ("Purchase Invoice", "采购发票", "Purchase Invoice Item"),
        ("Payment Entry", "付款单", None),
    )),
    ("projects", "项目协作", (
        ("Task", "任务", "Task"),
        ("ToDo", "待办", None),
    )),
)
DOCUMENT_RESET_ORDER = (
    "Purchase Invoice",
    "Purchase Receipt",
    "Stock Entry",
    "Purchase Order",
    "Supplier Quotation",
    "Request for Quotation",
    "Material Request",
    "Task",
)
DOCTYPE_ROUTES.update({"Payment Entry": "payment-entry", "Task": "task"})
ALLOWED_DOCUMENT_TYPES = frozenset(DOCTYPE_ROUTES)
SUBMITTABLE_DOCUMENT_TYPES = frozenset({
    "Material Request",
    "Request for Quotation",
    "Supplier Quotation",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Stock Entry",
})
DOCUMENT_LIST_FIELDS = {
    "Material Request": ["name", "title", "status", "workflow_state", "transaction_date", "schedule_date", "owner", "modified", "docstatus"],
    "Request for Quotation": ["name", "status", "transaction_date", "owner", "modified", "docstatus"],
    "Supplier Quotation": ["name", "supplier", "status", "transaction_date", "valid_till", "grand_total", "currency", "owner", "modified", "docstatus"],
    "Purchase Order": ["name", "supplier", "status", "transaction_date", "grand_total", "currency", "owner", "modified", "docstatus"],
    "Purchase Receipt": ["name", "supplier", "status", "posting_date", "grand_total", "currency", "owner", "modified", "docstatus", "is_return", "return_against"],
    "Stock Entry": ["name", "stock_entry_type", "purpose", "posting_date", "owner", "modified", "docstatus"],
    "Purchase Invoice": ["name", "supplier", "status", "posting_date", "grand_total", "currency", "owner", "modified", "docstatus"],
    "Payment Entry": ["name", "party", "payment_type", "posting_date", "paid_amount", "paid_from_account_currency", "owner", "modified", "docstatus"],
    "Task": ["name", "subject", "status", "priority", "owner", "modified", "docstatus"],
    "ToDo": ["name", "description", "status", "reference_type", "reference_name", "owner", "modified"],
}
MODULE_DOCTYPES = {
    module_code: tuple(doctype for doctype, _, _ in doctypes)
    for module_code, _, doctypes in DOCUMENT_MODULES
}
PURCHASE_DOCTYPES = frozenset({
    "Material Request",
    "Request for Quotation",
    "Purchase Order",
    "Purchase Receipt",
})


class ScopedRuntimeSessionStore(RuntimeSessionStore):
    """Keep conversations isolated by employee, project and browser conversation."""

    def __init__(self, directory: Path, *, user: str, project: str, conversation_id: str) -> None:
        super().__init__(directory)
        self.storage_key = "__".join((user, project or "no-project", conversation_id or "default"))

    def path_for(self, user: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", self.storage_key)
        return self.directory / f"{safe}.json"


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def json_response(handler: BaseHTTPRequestHandler, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def html_response(handler: BaseHTTPRequestHandler, body: str) -> None:
    data = body.encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def asset_response(handler: BaseHTTPRequestHandler, path: Path) -> None:
    content_type = ASSET_TYPES.get(path.suffix)
    if not content_type or not path.is_file() or path.parent != ASSET_DIR:
        json_response(handler, {"ok": False, "error": "资源不存在"}, HTTPStatus.NOT_FOUND)
        return
    data = path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    return json.loads(handler.rfile.read(length).decode("utf-8")) if length else {}


WORKBENCH_ROLE_VIEWS: dict[str, dict[str, Any]] = {
    "材料员": {
        "default_panel": "mine",
        "recommended_panels": ["mine", "progress", "recent"],
        "focus": "提出材料需求、跟踪申请与补充被退回的信息",
    },
    "材料设备主管": {
        "default_panel": "inbox",
        "recommended_panels": ["inbox", "pending", "progress", "exceptions"],
        "focus": "审批材料需求、组织询价下单、跟进收货与异常退货",
    },
    "项目经理": {
        "default_panel": "inbox",
        "recommended_panels": ["inbox", "progress", "exceptions"],
        "focus": "审批项目采购需求、关注紧急缺料和采购执行风险",
    },
    "采购员": {
        "default_panel": "pending",
        "recommended_panels": ["pending", "progress", "exceptions", "recent"],
        "focus": "处理待采购需求、组织询价下单并跟进供应商交付",
    },
    "仓库主管": {
        "default_panel": "progress",
        "recommended_panels": ["progress", "exceptions", "recent"],
        "focus": "办理采购收货、检查到货差异并跟进退货处理",
    },
    "仓管员": {
        "default_panel": "progress",
        "recommended_panels": ["progress", "exceptions", "recent"],
        "focus": "办理本人仓库权限范围内的收货、入库和退货",
    },
    "总经理": {
        "default_panel": "progress",
        "recommended_panels": ["progress", "exceptions", "recent"],
        "focus": "查看采购进度、异常升级和项目风险",
    },
    "经营主管": {
        "default_panel": "progress",
        "recommended_panels": ["progress", "recent", "exceptions"],
        "focus": "关注项目采购履约、合同与经营风险",
    },
    "技术负责人": {
        "default_panel": "recent",
        "recommended_panels": ["recent", "exceptions"],
        "focus": "协助确认技术规格和处理到货技术差异",
    },
    "财务人员": {
        "default_panel": "recent",
        "recommended_panels": ["recent", "progress", "exceptions"],
        "focus": "核对采购收货与发票，处理应付和付款业务",
    },
}


def employee_catalog() -> list[dict[str, Any]]:
    release = MasterDataRelease()
    roles = release.roles
    return [
        {
            "employee_code": row["employee_code"],
            "employee_name": row["employee_name"],
            "position": row["position"],
            "user_email": row["user_email"],
            "profile": roles[row["role_code"]]["default_agent_profile"],
            "default_project_code": row.get("default_project_code", ""),
            "default_warehouse_code": row.get("default_warehouse_code", ""),
            "workbench_view": WORKBENCH_ROLE_VIEWS.get(
                row["position"],
                {"default_panel": "recent", "recommended_panels": ["recent"], "focus": "处理本人 ERPNext 权限范围内的工作"},
            ),
        }
        for row in release.table("employees.tsv", include_candidates=False)
        if row.get("user_email")
    ]


def project_catalog() -> list[dict[str, Any]]:
    release = MasterDataRelease()
    employees = {row["employee_code"]: row for row in employee_catalog()}
    assignments = release.table("employee_assignments.tsv", include_candidates=False)
    organization_people = {
        row["employee_code"] for row in assignments
        if row.get("scope_type") == "organization" and row.get("scope_code") == "DEPT-UP" and row.get("is_active") == "1"
    }
    project_roles: dict[str, list[dict[str, str]]] = {}
    for project_code, project in release.projects.items():
        people: dict[str, dict[str, str]] = {}
        for row in assignments:
            employee_code = row.get("employee_code", "")
            if employee_code not in employees or row.get("is_active") != "1":
                continue
            if employee_code in organization_people or row.get("scope_code") == project_code:
                person = dict(employees[employee_code])
                person["project_position"] = row.get("position", person["position"]) if row.get("scope_code") == project_code else person["position"]
                people[employee_code] = person
        project_roles[project_code] = sorted(people.values(), key=lambda row: (row["position"] != "项目经理", row["employee_name"]))
    return [
        {
            "project_code": code,
            "project_name": row["project_name"],
            "project_short_name": row["project_short_name"],
            "operating_status": row.get("project_operating_status", ""),
            "warehouse_code": row.get("default_warehouse_code", ""),
            "employees": project_roles[code],
        }
        for code, row in release.projects.items()
    ]


def result_document_links(result: dict[str, Any], erpnext_base_url: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for supplied in result.get("document_links") or []:
        if not isinstance(supplied, dict):
            continue
        doctype = str(supplied.get("doctype") or "")
        name = str(supplied.get("name") or "")
        if doctype in DOCTYPE_ROUTES and name:
            links.append({
                "doctype": doctype,
                "name": name,
                "url": f"#document/{quote(doctype, safe='')}/{quote(name, safe='')}",
            })
    payloads = result.get("tool_results") or ([result.get("tool_result")] if result.get("tool_result") else [])
    seen: set[tuple[str, str]] = {(row["doctype"], row["name"]) for row in links}
    for payload in payloads:
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict):
            continue
        doctype = str(data.get("doctype") or "")
        name = str(data.get("name") or "")
        route = DOCTYPE_ROUTES.get(doctype)
        if not route or not name or (doctype, name) in seen:
            continue
        seen.add((doctype, name))
        links.append(
            {
                "doctype": doctype,
                "name": name,
                "url": f"#document/{quote(doctype, safe='')}/{quote(name, safe='')}",
            }
        )
    return links


def compact_chat_candidates(groups: list[Any] | tuple[Any, ...]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        rows = group.get("candidates") if isinstance(group.get("candidates"), list) else [group]
        candidates = [
            {
                key: row[key]
                for key in ("item_code", "item_name", "sku_name", "required_specs", "stock_uom", "estimated_rate", "currency", "price_basis", "inventory", "inventory_summary")
                if key in row
            }
            for row in rows
            if isinstance(row, dict) and row.get("item_code")
        ][:5]
        if not candidates:
            continue
        if isinstance(group.get("candidates"), list):
            compact.append({"id": group.get("id"), "kind": group.get("kind"), "query": group.get("query"), "candidates": candidates})
        else:
            compact.extend(candidates)
    return compact


def business_error_cards(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert unresolved Runtime failures into employee-facing recovery guidance."""
    if result.get("status") not in {"failed", "needs_clarification"}:
        return []
    cards: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for step in reversed(result.get("steps") or []):
        if not isinstance(step, dict):
            continue
        observation = step.get("result") if isinstance(step.get("result"), dict) else {}
        observation_type = str(observation.get("type") or "")
        if observation_type not in {"business_action_error", "tool_validation_error"} and observation.get("ok") is not False:
            continue
        detail = str(
            observation.get("user_message")
            or observation.get("error")
            or result.get("message")
            or "当前操作未能完成。"
        ).strip()
        questions = [str(value).strip() for value in observation.get("questions") or [] if str(value).strip()]
        error_type = str(observation.get("error_type") or observation_type)
        category, title, fallback = _business_error_category(detail, error_type, bool(questions))
        key = (category, detail)
        if key in seen:
            continue
        seen.add(key)
        cards.append({
            "category": category,
            "title": title,
            "summary": detail,
            "next_actions": questions or [fallback],
            "retryable": category not in {"permission", "identity"},
        })
        if len(cards) == 3:
            break
    if cards:
        return list(reversed(cards))
    if result.get("status") == "failed":
        return [{
            "category": "runtime",
            "title": "助理未能完成这次操作",
            "summary": str(result.get("message") or "执行过程没有正常完成。"),
            "next_actions": ["请稍后重试；若问题仍存在，可在开发者模式查看执行记录。"],
            "retryable": True,
        }]
    return []


def _business_error_category(detail: str, error_type: str, has_questions: bool) -> tuple[str, str, str]:
    text = f"{detail} {error_type}".lower()
    if any(token in text for token in ("identity", "身份不一致", "登录身份")):
        return "identity", "当前登录身份不匹配", "请切换到正确员工账号后重新操作。"
    if any(token in text for token in ("permission", "not permitted", "权限", "无权")):
        return "permission", "当前岗位没有此操作权限", "请交由有权限的岗位处理，或联系管理员核对角色权限。"
    if has_questions or any(token in text for token in ("缺少", "不能为空", "required", "请选择", "请说明", "请确认")):
        return "missing_information", "还缺少必要业务信息", "请补充缺少的信息后继续。"
    if any(token in text for token in ("状态不能", "尚未提交", "已失效", "过期", "不能超过", "不一致", "跨项目", "跨公司")):
        return "business_precondition", "当前业务状态不允许这样操作", "请先处理来源单据状态或选择符合条件的单据。"
    if any(token in text for token in ("not found", "不存在", "未找到")):
        return "not_found", "没有找到对应业务数据", "请核对单号或重新选择系统中的真实记录。"
    if any(token in text for token in ("network", "timeout", "连接", "服务不可用")):
        return "service", "外部服务暂时不可用", "请稍后重试，本次不会重复写入单据。"
    return "validation", "业务校验未通过", "请按提示修改业务信息后重新提交。"


def compact_chat_result(result: dict[str, Any], erpnext_base_url: str, *, include_trace: bool = False) -> dict[str, Any]:
    document_links = result_document_links(result, erpnext_base_url)
    status = result.get("status")
    message = result.get("message")
    successful_results = [
        item
        for item in [result.get("tool_result"), *(result.get("tool_results") or [])]
        if isinstance(item, dict) and item.get("ok")
    ]
    if status == "failed" and document_links and successful_results:
        status = "completed"
        created = document_links[-1]
        message = f"{created['doctype']} {created['name']} 已在 ERPNext 中执行成功。Agent 生成最终回复时格式异常，但不影响单据。"
    if status == "needs_confirmation" and "尚未" not in str(message or ""):
        action = str(message or "执行这项操作").strip().rstrip("。")
        message = f"我已准备好{action}，但尚未写入 ERPNext。请确认后再执行。"
    payload = {
        "status": status,
        "message": message,
        "questions": result.get("questions") or [],
        "candidates": compact_chat_candidates(result.get("candidates") or []),
        "business_errors": business_error_cards(result),
        "document_links": document_links,
        "pending_tool_call": result.get("pending_tool_call"),
        "tool_call": result.get("tool_call"),
    }
    if include_trace:
        payload.update({
            "steps": result.get("steps") or [],
            "tool_calls": result.get("tool_calls") or [],
            "tool_results": result.get("tool_results") or [],
            "tool_result": result.get("tool_result"),
        })
    return payload


def document_process_summary(
    doctype: str,
    document: dict[str, Any],
    available_actions: list[str] | None = None,
) -> dict[str, Any]:
    raw_assignments = document.get("_assign") or []
    if isinstance(raw_assignments, str):
        try:
            raw_assignments = json.loads(raw_assignments)
        except json.JSONDecodeError:
            raw_assignments = []
    assignees = [str(value) for value in raw_assignments if str(value).strip()] if isinstance(raw_assignments, list) else []
    docstatus = int(document.get("docstatus") or 0)
    workflow_state = str(document.get("workflow_state") or "").strip()
    if workflow_state:
        state_label = workflow_state
        description = "该单据已进入 ERPNext 审批工作流。"
    elif docstatus == 0:
        state_label = "草稿"
        description = "当前账套未给这张单据配置审批工作流；提交后将直接成为已提交状态。"
    elif docstatus == 1:
        state_label = "已提交"
        description = "单据已经提交生效，当前没有后续审批节点。"
    else:
        state_label = "已取消"
        description = "单据已取消，不再继续流转。"
    actions = [str(action) for action in (available_actions or []) if str(action).strip()]
    if actions:
        notification = f"当前账号可执行：{'、'.join(actions)}"
    elif assignees:
        notification = "已生成审批分配"
    elif workflow_state and docstatus == 0:
        notification = "当前账号不是本节点审批人，正在等待对应岗位处理"
    else:
        notification = "当前没有审批待办接收人"
    return {
        "state": state_label,
        "description": description,
        "workflow_configured": bool(workflow_state),
        "assignees": assignees,
        "notification": notification,
        "available_actions": actions,
        "can_submit": docstatus == 0 and doctype in SUBMITTABLE_DOCUMENT_TYPES and not workflow_state,
    }


def document_matches_project(document: dict[str, Any], erpnext_project: str) -> bool:
    if not erpnext_project:
        return True
    if str(document.get("project") or "") == erpnext_project:
        return True
    for fieldname in ("items", "suppliers"):
        rows = document.get(fieldname)
        if isinstance(rows, list) and any(str(row.get("project") or "") == erpnext_project for row in rows):
            return True
    # Some buying documents inherit project context indirectly and have no project field.
    return not document.get("items") and not document.get("project")


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _procurement_urgency(days_remaining: int | None) -> dict[str, str]:
    if days_remaining is None:
        return {"code": "unknown", "label": "日期待确认"}
    if days_remaining < 0:
        return {"code": "overdue", "label": "已逾期"}
    if days_remaining <= 2:
        return {"code": "urgent", "label": "紧急"}
    if days_remaining <= 7:
        return {"code": "soon", "label": "近期"}
    return {"code": "normal", "label": "正常"}


class AgentWorkbenchService:
    def __init__(self, profile: str = "civil") -> None:
        self.profile = profile
        prefix = f"NEXTERP_{profile.upper()}_"
        self.base_url = os.environ[prefix + "BASE_URL"]
        self.host_header = os.getenv(prefix + "HOST_HEADER")
        self.session_store = RuntimeSessionStore()
        self._project_name_cache: dict[tuple[str, str], str] = {}
        self.openclaw_preview = OpenClawPreviewRunner(ROOT)
        self.openclaw_runtime = OpenClawWorkbenchRunner(ROOT)
        self.capability_repository = CapabilityCatalogRepository(os.environ["MATERIAL_CATALOG_DATABASE_URL"])
        self._run_lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}

    def scoped_session_store(self, user: str, project: str = "", conversation_id: str = "default") -> RuntimeSessionStore:
        if not project and conversation_id == "default":
            return self.session_store
        return ScopedRuntimeSessionStore(
            self.session_store.directory,
            user=user,
            project=project,
            conversation_id=conversation_id,
        )

    def runtime(self, session_store: RuntimeSessionStore | None = None) -> CivilAgentRuntime:
        def client_factory(user: str) -> ERPNextClient:
            credentials = load_user_credentials(user)
            return ERPNextClient(
                self.base_url,
                credentials["api_key"],
                credentials["api_secret"],
                host_header=self.host_header,
                timeout=90,
            )

        return CivilAgentRuntime(client_factory=client_factory, session_store=session_store or self.session_store)

    def bootstrap(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "projects": project_catalog(),
            "employees": employee_catalog(),
            "features": {
                "developer_mode": True,
                "purchase_modules": list(MODULE_DOCTYPES["buying"]),
                "conversation_scope": "employee_project_conversation",
                "agent_runtime": "openclaw_progressive_manual",
            },
        }

    def session_history(
        self,
        user: str,
        project: str = "",
        conversation_id: str = "default",
    ) -> dict[str, Any]:
        if not user:
            raise ValueError("user 必填")
        employee = next((row for row in employee_catalog() if row["user_email"] == user), None)
        if not employee:
            raise ValueError("未知员工账号")
        store = self.scoped_session_store(user, project, conversation_id)
        session = store.load(user, profile=employee["profile"])
        source_turns = session.turns[-20:]
        turns = [
            {
                "user_text": str(turn.get("user_text") or ""),
                "result": compact_chat_result(turn.get("result") or {}, self.base_url),
            }
            for turn in source_turns
            if turn.get("user_text") or (turn.get("result") or {}).get("message")
        ]
        latest_source = source_turns[-1] if source_turns else {}
        latest_result = compact_chat_result(latest_source.get("result") or {}, self.base_url, include_trace=True) if latest_source else None
        return {
            "turns": turns,
            "latest_user_text": str(latest_source.get("user_text") or ""),
            "latest_result": latest_result,
            "updated_at": session.updated_at,
            "conversation_id": conversation_id,
            "project": project,
        }

    def reset_session(self, user: str, project: str = "", conversation_id: str = "default") -> dict[str, Any]:
        if not user:
            raise ValueError("user 必填")
        if not any(row["user_email"] == user for row in employee_catalog()):
            raise ValueError("未知员工账号")
        path = self.scoped_session_store(user, project, conversation_id).path_for(user)
        existed = path.exists()
        path.unlink(missing_ok=True)
        return {"reset": True, "had_history": existed}

    def client(self, user: str) -> ERPNextClient:
        credentials = load_user_credentials(user)
        return ERPNextClient(self.base_url, credentials["api_key"], credentials["api_secret"], host_header=self.host_header, timeout=90)

    def erpnext_project_name(self, client: ERPNextClient, project_code: str) -> str:
        project = MasterDataRelease().projects.get(project_code)
        if not project:
            return project_code
        result = client.search_documents(
            "Project",
            filters={"project_name": project["project_name"]},
            fields=["name", "project_name"],
            limit=2,
        )
        if result.ok and isinstance(result.data, list) and len(result.data) == 1:
            return str(result.data[0]["name"])
        return project_code

    @staticmethod
    def erpnext_warehouse_name(warehouse_value: str) -> str:
        value = str(warehouse_value or "").strip()
        for warehouse in MasterDataRelease().warehouses.values():
            if value in {
                warehouse.get("warehouse_code"),
                warehouse.get("warehouse_name"),
                warehouse.get("erpnext_warehouse_name"),
            }:
                return str(warehouse.get("erpnext_warehouse_name") or value)
        return value

    def inbox(self, user: str, project: str = "", *, limit: int = 30) -> dict[str, Any]:
        if not user:
            raise ValueError("user 必填")
        client = self.client(user)
        erpnext_project = self.erpnext_project_name(client, project) if project else ""
        result = client.search_documents(
            "Workflow Action",
            filters={"status": "Open"},
            fields=["name", "reference_doctype", "reference_name", "workflow_state", "modified"],
            limit=min(50, max(1, int(limit))),
            order_by="modified desc",
        )
        if not result.ok:
            raise ValueError(result.user_message or result.error or "无法读取 ERPNext 审批待办")
        rows = result.data if isinstance(result.data, list) else []

        def enrich(row: dict[str, Any]) -> dict[str, Any] | None:
            doctype = str(row.get("reference_doctype") or "")
            name = str(row.get("reference_name") or "")
            if not doctype or not name or doctype not in ALLOWED_DOCUMENT_TYPES:
                return None
            detail = client.call_method(
                "agent_bridge.api.get_document_with_workflow_actions",
                {"doctype": doctype, "name": name},
            )
            if not detail.ok or not isinstance(detail.data, dict):
                return None
            document = detail.data.get("document")
            transitions = detail.data.get("actions")
            if not isinstance(document, dict):
                return None
            if erpnext_project and not document_matches_project(document, erpnext_project):
                return None
            actions = [str(item.get("action")) for item in transitions or [] if item.get("action")]
            return {
                "workflow_action": row.get("name"),
                "reference_doctype": doctype,
                "reference_name": name,
                "label": next(
                    (label for _, _, doctypes in DOCUMENT_MODULES for candidate, label, _ in doctypes if candidate == doctype),
                    doctype,
                ),
                "title": document.get("title") or document.get("supplier") or document.get("subject") or name,
                "workflow_state": document.get("workflow_state") or row.get("workflow_state") or document.get("status"),
                "actions": actions,
                "owner": document.get("owner"),
                "modified": document.get("modified") or row.get("modified"),
            }

        with ThreadPoolExecutor(max_workers=min(6, max(1, len(rows)))) as executor:
            items = [item for item in executor.map(enrich, rows) if item]
        return {
            "project": project,
            "erpnext_project": erpnext_project,
            "items": items,
            "count": len(items),
        }

    def pending_procurement(
        self,
        user: str,
        project: str = "",
        *,
        scope: str = "project",
        limit: int = 500,
    ) -> dict[str, Any]:
        if not user:
            raise ValueError("user 必填")
        if scope not in {"project", "all"}:
            raise ValueError("scope 只能是 project 或 all")
        release = MasterDataRelease()
        client = self.client(user)
        erpnext_project = self.erpnext_project_name(client, project) if project and scope == "project" else ""
        warehouse_names = self.procurement_inventory_warehouses(project, include_all=scope == "all")
        result = client.get_pending_procurement_items(
            project=erpnext_project or None,
            warehouses=warehouse_names,
            limit=max(1, min(limit, 1000)),
        )
        if not result.ok or not isinstance(result.data, dict):
            raise ValueError(result.user_message or result.error or "无法读取待采购需求")

        materials = {row["item_code"]: row for row in release.materials if row.get("item_code")}
        suppliers = {row["supplier_code"]: row for row in release.table("suppliers.tsv")}
        policies_by_item: dict[str, list[dict[str, str]]] = {}
        for policy in release.table("supplier_item_policies.tsv"):
            policies_by_item.setdefault(policy.get("item_code", ""), []).append(policy)
        inventory_by_item: dict[str, list[dict[str, Any]]] = {}
        for source in result.data.get("inventory") or []:
            stock = dict(source)
            stock["available_qty"] = _number(stock.get("actual_qty")) - _number(stock.get("reserved_qty"))
            inventory_by_item.setdefault(str(stock.get("item_code") or ""), []).append(stock)

        today_value = date.today()
        rows = []
        for source in result.data.get("rows") or []:
            row = dict(source)
            item_code = str(row.get("item_code") or "")
            material = materials.get(item_code) or {}
            inventory = inventory_by_item.get(item_code, [])
            for warehouse in warehouse_names:
                if not any(str(stock.get("warehouse") or "") == warehouse for stock in inventory):
                    inventory.append({
                        "item_code": item_code,
                        "warehouse": warehouse,
                        "actual_qty": 0.0,
                        "reserved_qty": 0.0,
                        "available_qty": 0.0,
                        "projected_qty": 0.0,
                    })
            inventory.sort(key=lambda stock: (-_number(stock.get("available_qty")), str(stock.get("warehouse") or "")))
            schedule_date = str(row.get("schedule_date") or "")[:10]
            days_remaining = None
            try:
                days_remaining = (date.fromisoformat(schedule_date) - today_value).days
            except ValueError:
                pass
            urgency = _procurement_urgency(days_remaining)
            policies = sorted(
                policies_by_item.get(item_code, []),
                key=lambda policy: int(policy.get("preferred_rank") or 999),
            )
            supplier_suggestions = [
                {
                    "supplier_code": policy.get("supplier_code"),
                    "supplier_name": (suppliers.get(policy.get("supplier_code", "")) or {}).get("supplier_name") or policy.get("supplier_code"),
                    "preferred_rank": policy.get("preferred_rank"),
                    "lead_time_days": policy.get("lead_time_days"),
                    "default_rate": policy.get("default_rate"),
                }
                for policy in policies[:3]
            ]
            remaining_qty = _number(row.get("remaining_qty"))
            total_available = sum(max(0.0, _number(stock.get("available_qty"))) for stock in inventory)
            row.update({
                "sku_name": material.get("sku_name") or row.get("item_name") or item_code,
                "required_specs": material.get("required_specs") or "",
                "top_group": material.get("top_group") or "未分类",
                "material_family": material.get("material_family") or "未分类",
                "purchase_uom": material.get("purchase_uom") or row.get("uom"),
                "urgency": urgency["code"],
                "urgency_label": urgency["label"],
                "days_remaining": days_remaining,
                "inventory": inventory,
                "total_available_qty": total_available,
                "inventory_coverage": "enough" if total_available >= remaining_qty else "shortage",
                "supplier_suggestions": supplier_suggestions,
                "estimated_amount": remaining_qty * _number(row.get("rate")),
            })
            rows.append(row)

        aggregate: dict[str, dict[str, Any]] = {}
        for row in rows:
            item_code = row["item_code"]
            group = aggregate.setdefault(item_code, {
                "item_code": item_code,
                "sku_name": row["sku_name"],
                "uom": row.get("uom"),
                "material_family": row["material_family"],
                "total_remaining_qty": 0.0,
                "request_count": 0,
                "projects": set(),
                "earliest_schedule_date": row.get("schedule_date"),
                "supplier_suggestions": row["supplier_suggestions"],
            })
            group["total_remaining_qty"] += _number(row.get("remaining_qty"))
            group["request_count"] += 1
            if row.get("project"):
                group["projects"].add(row["project"])
            if row.get("schedule_date") and (not group["earliest_schedule_date"] or row["schedule_date"] < group["earliest_schedule_date"]):
                group["earliest_schedule_date"] = row["schedule_date"]
        aggregate_rows = []
        for group in aggregate.values():
            group["projects"] = sorted(group["projects"])
            aggregate_rows.append(group)
        aggregate_rows.sort(key=lambda row: (str(row.get("earliest_schedule_date") or "9999-12-31"), row["sku_name"]))
        rows.sort(key=lambda row: (str(row.get("schedule_date") or "9999-12-31"), row["sku_name"]))

        payment_templates = {
            row.get("payment_term_code"): row.get("erpnext_payment_terms_template")
            for row in release.table("payment_terms.tsv", include_candidates=False)
        }
        active_suppliers = [
            {
                "supplier_code": supplier.get("supplier_code"),
                "supplier_name": supplier.get("supplier_name"),
                "supplier_group": supplier.get("supplier_group"),
                "primary_category": supplier.get("primary_category"),
                "currency": supplier.get("default_currency") or "CNY",
                "payment_term": payment_templates.get(supplier.get("default_payment_term")) or supplier.get("default_payment_term"),
            }
            for supplier in release.table("suppliers.tsv", include_candidates=False)
            if supplier.get("supplier_code") and supplier.get("supplier_name")
        ]
        return {
            "scope": scope,
            "project": project,
            "erpnext_project": erpnext_project,
            "warehouses": warehouse_names,
            "rows": rows,
            "aggregate": aggregate_rows,
            "summary": {
                **dict(result.data.get("summary") or {}),
                "shortage_rows": sum(1 for row in rows if row["inventory_coverage"] == "shortage"),
                "urgent_rows": sum(1 for row in rows if row["urgency"] in {"overdue", "urgent"}),
                "estimated_amount": sum(_number(row.get("estimated_amount")) for row in rows),
            },
            "filters": {
                "families": sorted({row["material_family"] for row in rows}),
                "suppliers": sorted({
                    supplier["supplier_name"]
                    for row in rows
                    for supplier in row["supplier_suggestions"]
                    if supplier.get("supplier_name")
                }),
            },
            "available_suppliers": active_suppliers,
            "inventory_error": result.data.get("inventory_error"),
        }

    def create_request_for_quotation(
        self,
        user: str,
        project: str,
        selected_rows: list[str],
        supplier_codes: list[str],
        *,
        schedule_date: str = "",
        message_for_supplier: str = "",
        request_id: str = "",
        conversation_id: str = "default",
    ) -> dict[str, Any]:
        if not user or not project:
            raise ValueError("user 和 project 必填")
        selected = {str(value).strip() for value in selected_rows if str(value).strip()}
        if not selected:
            raise ValueError("请至少选择一条待采购需求")
        if not supplier_codes:
            raise ValueError("请至少选择一家供应商")
        cached, request_context = self._idempotency_context(user, project, conversation_id, request_id)
        if cached is not None:
            return cached

        release = MasterDataRelease()
        supplier_by_code = {
            row["supplier_code"]: row
            for row in release.table("suppliers.tsv", include_candidates=False)
            if row.get("supplier_code")
        }
        unknown_suppliers = [code for code in supplier_codes if code not in supplier_by_code]
        if unknown_suppliers:
            raise ValueError(f"未知或未启用的供应商：{'、'.join(unknown_suppliers)}")

        current = self.pending_procurement(user, project, scope="project")
        current_rows = {
            f"{row.get('material_request') or ''}:{row.get('material_request_item') or row.get('item_code') or ''}": row
            for row in current["rows"]
        }
        stale = sorted(selected - set(current_rows))
        if stale:
            raise ValueError(f"有 {len(stale)} 条需求已不在待采购队列，请刷新后重新选择")
        rows = [current_rows[key] for key in selected]
        effective_schedule_date = schedule_date or min(
            (str(row.get("schedule_date") or "")[:10] for row in rows if row.get("schedule_date")),
            default="",
        )
        items = [
            {
                "item_code": row["item_code"],
                "qty": _number(row.get("remaining_qty")),
                "uom": row.get("uom"),
                "schedule_date": str(row.get("schedule_date") or effective_schedule_date)[:10],
                "warehouse": row.get("warehouse"),
                "project": row.get("project"),
                "material_request": row.get("material_request"),
                "material_request_item": row.get("material_request_item"),
            }
            for row in rows
        ]
        adapter = ERPNextAdapter(self.client(user))
        result = adapter.execute({
            "tool": "erpnext.buying.create_request_for_quotation_draft",
            "arguments": {
                "company": release.company_name("STEC"),
                "transaction_date": date.today().isoformat(),
                "schedule_date": effective_schedule_date,
                "message_for_supplier": message_for_supplier.strip(),
                "suppliers": [
                    {"supplier": supplier_by_code[code]["supplier_name"]}
                    for code in supplier_codes
                ],
                "items": items,
            },
        })
        if not result.ok or not isinstance(result.data, dict) or not result.data.get("name"):
            raise ValueError(result.user_message or result.error or "创建询价单草稿失败")
        payload = self.document(user, "Request for Quotation", str(result.data["name"]))
        payload["source_rows"] = rows
        payload["selected_suppliers"] = [supplier_by_code[code]["supplier_name"] for code in supplier_codes]
        self._remember_idempotent_result(request_context, request_id, payload)
        return payload

    def create_supplier_quotation(
        self,
        user: str,
        project: str,
        request_for_quotation: str,
        supplier_code: str,
        offers: list[dict[str, Any]],
        *,
        valid_till: str = "",
        terms: str = "",
        request_id: str = "",
        conversation_id: str = "default",
    ) -> dict[str, Any]:
        if not user or not request_for_quotation or not supplier_code:
            raise ValueError("user、request_for_quotation 和 supplier_code 必填")
        cached, request_context = self._idempotency_context(user, project, conversation_id, request_id)
        if cached is not None:
            return cached
        release = MasterDataRelease()
        supplier = next(
            (
                row for row in release.table("suppliers.tsv", include_candidates=False)
                if supplier_code in {row.get("supplier_code"), row.get("supplier_name")}
            ),
            None,
        )
        if not supplier:
            raise ValueError("供应商不存在或未启用")
        client = self.client(user)
        rfq_result = client.get_document("Request for Quotation", request_for_quotation)
        if not rfq_result.ok or not isinstance(rfq_result.data, dict):
            raise ValueError(rfq_result.user_message or rfq_result.error or "无法读取询价单")
        rfq = rfq_result.data
        if int(rfq.get("docstatus") or 0) != 1:
            raise ValueError("请先提交询价单，再录入供应商报价")
        supplier_name = supplier["supplier_name"]
        rfq_suppliers = {
            str(row.get("supplier") or row.get("supplier_name") or "")
            for row in rfq.get("suppliers") or []
            if isinstance(row, dict)
        }
        if supplier_name not in rfq_suppliers:
            raise ValueError("该供应商不在这张询价单的供应商范围内")
        offer_by_row = {
            str(row.get("request_for_quotation_item") or row.get("item_code") or ""): row
            for row in offers
            if isinstance(row, dict)
        }
        items = []
        for row in rfq.get("items") or []:
            if not isinstance(row, dict):
                continue
            offer = offer_by_row.get(str(row.get("name") or "")) or offer_by_row.get(str(row.get("item_code") or ""))
            rate = _number((offer or {}).get("rate"))
            if rate <= 0:
                raise ValueError(f"{row.get('item_code') or '报价明细'} 的单价必须大于 0")
            items.append({
                "item_code": row.get("item_code"),
                "qty": row.get("qty"),
                "uom": row.get("uom"),
                "schedule_date": (offer or {}).get("schedule_date") or row.get("schedule_date"),
                "rate": rate,
                "warehouse": row.get("warehouse"),
                "project": row.get("project"),
                "request_for_quotation": request_for_quotation,
                "request_for_quotation_item": row.get("name"),
            })
        if not items:
            raise ValueError("询价单没有可报价的物料明细")
        result = ERPNextAdapter(client).execute({
            "tool": "erpnext.buying.create_supplier_quotation_draft",
            "arguments": {
                "supplier": supplier_name,
                "company": release.company_name("STEC"),
                "currency": supplier.get("default_currency") or "CNY",
                "transaction_date": date.today().isoformat(),
                "valid_till": valid_till,
                "request_for_quotation": request_for_quotation,
                "payment_terms_template": next(
                    (
                        row.get("erpnext_payment_terms_template")
                        for row in release.table("payment_terms.tsv", include_candidates=False)
                        if row.get("payment_term_code") == supplier.get("default_payment_term")
                    ),
                    supplier.get("default_payment_term"),
                ),
                "terms": terms.strip(),
                "items": items,
            },
        })
        if not result.ok or not isinstance(result.data, dict) or not result.data.get("name"):
            raise ValueError(result.user_message or result.error or "创建供应商报价草稿失败")
        payload = self.document(user, "Supplier Quotation", str(result.data["name"]))
        payload["request_for_quotation"] = request_for_quotation
        self._remember_idempotent_result(request_context, request_id, payload)
        return payload

    def supplier_quotations(self, user: str, request_for_quotation: str) -> dict[str, Any]:
        if not user or not request_for_quotation:
            raise ValueError("user 和 request_for_quotation 必填")
        client = self.client(user)
        parents = client.search_documents(
            "Supplier Quotation",
            fields=["name", "supplier", "status", "transaction_date", "valid_till", "grand_total", "currency", "docstatus", "modified"],
            limit=200,
            order_by="modified desc",
        )
        if not parents.ok:
            raise ValueError(parents.user_message or parents.error or "无法读取关联供应商报价")
        quotations = []
        for row in parents.data or []:
            name = str(row.get("name") or "")
            if not name:
                continue
            result = client.get_document("Supplier Quotation", name)
            if result.ok and isinstance(result.data, dict) and any(
                str(item.get("request_for_quotation") or "") == request_for_quotation
                for item in result.data.get("items") or []
                if isinstance(item, dict)
            ):
                quotations.append(result.data)
        purchase_orders = client.search_documents(
            "Purchase Order",
            filters={"docstatus": ["!=", 2]},
            fields=["name", "supplier", "status", "docstatus"],
            limit=500,
            order_by="modified desc",
        )
        ordered_by_quotation: dict[str, dict[str, Any]] = {}
        if purchase_orders.ok:
            quotation_names = {str(row.get("name") or "") for row in quotations}
            for parent in purchase_orders.data or []:
                parent_name = str(parent.get("name") or "")
                if not parent_name:
                    continue
                detail = client.get_document("Purchase Order", parent_name)
                if not detail.ok or not isinstance(detail.data, dict):
                    continue
                for item in detail.data.get("items") or []:
                    quotation_name = str(item.get("supplier_quotation") or "")
                    if quotation_name not in quotation_names:
                        continue
                    summary = ordered_by_quotation.setdefault(quotation_name, {"purchase_orders": set(), "ordered_qty": 0.0})
                    summary["purchase_orders"].add(parent_name)
                    summary["ordered_qty"] += _number(item.get("qty"))
        for quotation in quotations:
            summary = ordered_by_quotation.get(str(quotation.get("name") or ""), {})
            quoted_qty = sum(_number(item.get("qty")) for item in quotation.get("items") or [] if isinstance(item, dict))
            quotation["purchase_orders"] = sorted(summary.get("purchase_orders") or [])
            quotation["ordered_qty"] = _number(summary.get("ordered_qty"))
            quotation["remaining_qty"] = max(quoted_qty - quotation["ordered_qty"], 0.0)
        return {"request_for_quotation": request_for_quotation, "quotations": quotations, "count": len(quotations)}

    def compare_supplier_quotations(self, user: str, names: list[str], *, include_drafts: bool = False) -> dict[str, Any]:
        if not user:
            raise ValueError("user 必填")
        result = ERPNextAdapter(self.client(user)).execute({
            "tool": "erpnext.buying.compare_supplier_quotations",
            "arguments": {"supplier_quotations": names, "include_drafts": include_drafts},
        })
        if not result.ok or not isinstance(result.data, dict):
            raise ValueError(result.user_message or result.error or "供应商报价比较失败")
        return result.data

    def create_purchase_order_from_supplier_quotation(
        self,
        user: str,
        project: str,
        supplier_quotation: str,
        *,
        selected_items: list[dict[str, Any]] | None = None,
        request_id: str = "",
        conversation_id: str = "default",
    ) -> dict[str, Any]:
        if not user or not project or not supplier_quotation:
            raise ValueError("user、project 和 supplier_quotation 必填")
        cached, request_context = self._idempotency_context(user, project, conversation_id, request_id)
        if cached is not None:
            return cached
        result = ERPNextAdapter(self.client(user)).execute({
            "tool": "erpnext.buying.create_purchase_order_from_supplier_quotation_draft",
            "arguments": {
                "supplier_quotation": supplier_quotation,
                "transaction_date": date.today().isoformat(),
                "selected_items": selected_items or [],
            },
        })
        if not result.ok or not isinstance(result.data, dict) or not result.data.get("name"):
            raise ValueError(result.user_message or result.error or "创建采购订单草稿失败")
        payload = self.document(user, "Purchase Order", str(result.data["name"]))
        payload["source_supplier_quotation"] = supplier_quotation
        self._remember_idempotent_result(request_context, request_id, payload)
        return payload

    def create_purchase_receipt_from_purchase_order(
        self,
        user: str,
        project: str,
        purchase_order: str,
        *,
        selected_items: list[dict[str, Any]] | None = None,
        request_id: str = "",
        conversation_id: str = "default",
    ) -> dict[str, Any]:
        if not user or not project or not purchase_order:
            raise ValueError("user、project 和 purchase_order 必填")
        cached, request_context = self._idempotency_context(user, project, conversation_id, request_id)
        if cached is not None:
            return cached
        result = ERPNextAdapter(self.client(user)).execute({
            "tool": "erpnext.buying.create_purchase_receipt_from_purchase_order_draft",
            "arguments": {
                "purchase_order": purchase_order,
                "posting_date": date.today().isoformat(),
                "selected_items": selected_items or [],
            },
        })
        if not result.ok or not isinstance(result.data, dict) or not result.data.get("name"):
            raise ValueError(result.user_message or result.error or "创建采购收货草稿失败")
        payload = self.document(user, "Purchase Receipt", str(result.data["name"]))
        payload["source_purchase_order"] = purchase_order
        self._remember_idempotent_result(request_context, request_id, payload)
        return payload

    def record_purchase_receipt_discrepancy(
        self,
        user: str,
        project: str,
        purchase_receipt: str,
        description: str,
        *,
        items: list[dict[str, Any]] | None = None,
        discrepancy_type: str = "spec_mismatch",
        severity: str = "Medium",
        assigned_to: str = "",
        request_id: str = "",
        conversation_id: str = "default",
    ) -> dict[str, Any]:
        if not user or not project or not purchase_receipt or not description.strip():
            raise ValueError("user、project、purchase_receipt 和 description 必填")
        cached, request_context = self._idempotency_context(user, project, conversation_id, request_id)
        if cached is not None:
            return cached
        arguments = {
            "purchase_receipt": purchase_receipt,
            "description": description.strip(),
            "discrepancy_type": discrepancy_type or "spec_mismatch",
            "severity": severity or "Medium",
            "reported_by": user,
            "comment_email": user,
            "comment_by": user,
            "create_todo": True,
            "prepare_return": True,
            "items": items or [],
        }
        if assigned_to:
            arguments["assigned_to"] = assigned_to
        result = ERPNextAdapter(self.client(user)).execute({
            "tool": "erpnext.buying.record_purchase_receipt_discrepancy",
            "arguments": arguments,
        })
        if not result.ok or not isinstance(result.data, dict):
            raise ValueError(result.user_message or result.error or "记录到货差异失败")
        payload = self.document(user, "Purchase Receipt", purchase_receipt)
        payload["discrepancy"] = result.data
        self._remember_idempotent_result(request_context, request_id, payload)
        return payload

    def create_purchase_return_from_receipt(
        self,
        user: str,
        project: str,
        purchase_receipt: str,
        reason: str,
        *,
        items: list[dict[str, Any]] | None = None,
        request_id: str = "",
        conversation_id: str = "default",
    ) -> dict[str, Any]:
        if not user or not project or not purchase_receipt or not reason.strip():
            raise ValueError("user、project、purchase_receipt 和 reason 必填")
        cached, request_context = self._idempotency_context(user, project, conversation_id, request_id)
        if cached is not None:
            return cached
        result = ERPNextAdapter(self.client(user)).execute({
            "tool": "erpnext.buying.create_purchase_receipt_return_draft",
            "arguments": {
                "purchase_receipt": purchase_receipt,
                "posting_date": date.today().isoformat(),
                "reason": reason.strip(),
                "items": items or [],
            },
        })
        if not result.ok or not isinstance(result.data, dict) or not result.data.get("name"):
            raise ValueError(result.user_message or result.error or "创建采购退货草稿失败")
        payload = self.document(user, "Purchase Receipt", str(result.data["name"]))
        payload["return_against"] = purchase_receipt
        self._remember_idempotent_result(request_context, request_id, payload)
        return payload

    def _idempotency_context(
        self,
        user: str,
        project: str,
        conversation_id: str,
        request_id: str,
    ) -> tuple[dict[str, Any] | None, tuple[RuntimeSessionStore, Any] | None]:
        if not request_id:
            return None, None
        store = self.scoped_session_store(user, project, conversation_id)
        employee = next((row for row in employee_catalog() if row["user_email"] == user), None)
        session = store.load(user, profile=employee["profile"] if employee else "general")
        return session.idempotency_results.get(request_id), (store, session)

    @staticmethod
    def _remember_idempotent_result(
        context: tuple[RuntimeSessionStore, Any] | None,
        request_id: str,
        payload: dict[str, Any],
    ) -> None:
        if not request_id or context is None:
            return
        store, session = context
        session.remember_request(request_id, payload)
        store.save(session)

    def procurement_inventory_warehouses(self, project: str, *, include_all: bool = False) -> list[str]:
        release = MasterDataRelease()
        codes = ["WH-CENTER", "WH-WCL-BASE"]
        if include_all:
            codes.extend(code for code, row in release.warehouses.items() if row.get("is_group") != "1")
        else:
            project_row = release.projects.get(project) or {}
            if project_row.get("default_warehouse_code"):
                codes.insert(0, project_row["default_warehouse_code"])
        names = []
        for code in codes:
            row = release.warehouses.get(code) or {}
            name = row.get("erpnext_warehouse_name")
            if name and name not in names:
                names.append(name)
        return names

    def documents(
        self,
        user: str,
        project: str = "",
        *,
        module: str = "buying",
        status: str = "",
        page: int = 1,
        page_size: int = 20,
        mine_only: bool = False,
    ) -> dict[str, Any]:
        if not user:
            raise ValueError("user 必填")
        if module not in MODULE_DOCTYPES:
            raise ValueError(f"未知业务模块：{module}")
        page = max(1, int(page))
        page_size = min(50, max(1, int(page_size)))
        client = self.client(user)
        project_key = (user, project)
        erpnext_project = self._project_name_cache.get(project_key, "") if project else ""
        if project and not erpnext_project:
            erpnext_project = self.erpnext_project_name(client, project)
            self._project_name_cache[project_key] = erpnext_project
        document_specs = [
            (doctype, label, project_child)
            for module_code, _, doctypes in DOCUMENT_MODULES
            if module_code == module
            for doctype, label, project_child in doctypes
        ]
        loaded: dict[str, dict[str, Any]] = {}
        try:
            batch = client.call_method(
                "agent_bridge.api.list_workbench_documents",
                {
                    "doctypes": [doctype for doctype, _, _ in document_specs],
                    "project": erpnext_project,
                    "status": status,
                    "owner": user if mine_only else "",
                    "limit": page_size,
                    "offset": (page - 1) * page_size,
                },
            )
        except (AttributeError, TypeError):
            batch = None
        if batch and batch.ok and isinstance(batch.data, dict):
            batch_groups = batch.data.get("groups") if isinstance(batch.data.get("groups"), dict) else {}
            batch_errors = batch.data.get("errors") if isinstance(batch.data.get("errors"), dict) else {}
            for doctype, label, _ in document_specs:
                loaded[doctype] = {
                    "doctype": doctype,
                    "label": label,
                    "error": batch_errors.get(doctype),
                    "documents": [dict(row) for row in batch_groups.get(doctype, []) if isinstance(row, dict)],
                }
        else:
            with ThreadPoolExecutor(max_workers=min(8, len(document_specs))) as executor:
                futures = {
                    doctype: executor.submit(
                        self._load_document_group,
                        user,
                        doctype,
                        label,
                        project_child,
                        erpnext_project,
                        page_size,
                        (page - 1) * page_size,
                        status,
                        user if mine_only else "",
                    )
                    for doctype, label, project_child in document_specs
                }
                for doctype, future in futures.items():
                    try:
                        loaded[doctype] = future.result()
                    except Exception as exc:
                        loaded[doctype] = {
                            "doctype": doctype,
                            "label": next(label for candidate, label, _ in document_specs if candidate == doctype),
                            "error": str(exc),
                            "documents": [],
                        }
        modules: list[dict[str, Any]] = []
        for module_code, module_label, doctypes in DOCUMENT_MODULES:
            if module_code != module:
                continue
            groups = [loaded[doctype] for doctype, _, _ in doctypes]
            modules.append({"code": module_code, "label": module_label, "groups": groups})
        return {
            "project": project,
            "erpnext_project": erpnext_project,
            "module": module,
            "status": status,
            "page": page,
            "page_size": page_size,
            "modules": modules,
        }

    def _load_document_group(
        self,
        user: str,
        doctype: str,
        label: str,
        project_child: str | None,
        erpnext_project: str,
        limit: int,
        offset: int = 0,
        status: str = "",
        owner: str = "",
    ) -> dict[str, Any]:
        client = self.client(user)
        filters: dict[str, Any] = {}
        if owner:
            filters["owner"] = owner
        if status and status not in {"all", "open"}:
            field = "workflow_state" if doctype == "Material Request" and status.startswith("待") else "status"
            filters[field] = status
        if erpnext_project and project_child == "Task":
            filters["project"] = erpnext_project
        result = client.search_documents(
            doctype,
            filters=filters,
            fields=DOCUMENT_LIST_FIELDS[doctype],
            limit=limit,
            offset=offset,
            order_by="modified desc",
        )
        rows = result.data if result.ok and isinstance(result.data, list) else []
        if erpnext_project and project_child and project_child != "Task":
            rows = self.filter_parent_documents_by_project(user, doctype, rows, erpnext_project)
        return {
            "doctype": doctype,
            "label": label,
            "error": None if result.ok else result.user_message or result.error,
            "documents": [dict(row) for row in rows],
        }

    def filter_parent_documents_by_project(
        self,
        user: str,
        doctype: str,
        rows: list[dict[str, Any]],
        erpnext_project: str,
    ) -> list[dict[str, Any]]:
        client = self.client(user)
        names = [str(row.get("name") or "") for row in rows if row.get("name")]
        try:
            result = client.call_method(
                "agent_bridge.api.filter_documents_by_project",
                {"doctype": doctype, "names": names, "project": erpnext_project},
            )
        except (AttributeError, TypeError):
            result = None
        if result and result.ok and isinstance(result.data, dict):
            matched_names = {str(value) for value in result.data.get("names", [])}
            return [row for row in rows if str(row.get("name") or "") in matched_names]

        # Compatibility path for older sandboxes that have not synced agent_bridge yet.
        detail_cache: dict[tuple[str, str], dict[str, Any] | None] = {}

        def detail(document_type: str, name: str) -> dict[str, Any] | None:
            key = (document_type, name)
            if key not in detail_cache:
                result = client.get_document(document_type, name)
                detail_cache[key] = result.data if result.ok and isinstance(result.data, dict) else None
            return detail_cache[key]

        def material_request_matches(name: str, item_name: str = "") -> bool:
            document = detail("Material Request", name)
            if not document:
                return False
            if str(document.get("project") or "") == erpnext_project:
                return True
            items = document.get("items") or []
            return any(
                (not item_name or str(item.get("name") or "") == item_name)
                and str(item.get("project") or "") == erpnext_project
                for item in items
                if isinstance(item, dict)
            )

        def rfq_matches(name: str, item_name: str = "") -> bool:
            document = detail("Request for Quotation", name)
            if not document:
                return False
            for item in document.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if item_name and str(item.get("name") or "") != item_name:
                    continue
                if str(item.get("project") or "") == erpnext_project:
                    return True
                material_request = str(item.get("material_request") or "")
                if material_request and material_request_matches(
                    material_request,
                    str(item.get("material_request_item") or ""),
                ):
                    return True
            return False

        def matches(row: dict[str, Any]) -> bool:
            name = str(row.get("name") or "")
            if not name:
                return False
            document = detail(doctype, name)
            if not document:
                return False
            if str(document.get("project") or "") == erpnext_project:
                return True
            for item in document.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if str(item.get("project") or "") == erpnext_project:
                    return True
                material_request = str(item.get("material_request") or "")
                if material_request and material_request_matches(
                    material_request,
                    str(item.get("material_request_item") or ""),
                ):
                    return True
                request_for_quotation = str(item.get("request_for_quotation") or "")
                if request_for_quotation and rfq_matches(
                    request_for_quotation,
                    str(item.get("request_for_quotation_item") or ""),
                ):
                    return True
            return False

        with ThreadPoolExecutor(max_workers=min(6, max(1, len(rows)))) as executor:
            decisions = list(executor.map(matches, rows))
        return [row for row, matched in zip(rows, decisions, strict=True) if matched]

    def document(self, user: str, doctype: str, name: str) -> dict[str, Any]:
        if not user or not doctype or not name:
            raise ValueError("user、doctype 和 name 必填")
        if doctype not in ALLOWED_DOCUMENT_TYPES:
            raise ValueError(f"测试台暂不支持查看 {doctype}")
        client = self.client(user)
        result = client.call_method(
            "agent_bridge.api.get_document_with_workflow_actions",
            {"doctype": doctype, "name": name},
        )
        if not result.ok or not isinstance(result.data, dict):
            raise ValueError(result.user_message or result.error or f"无法读取 {doctype} {name}")
        document = result.data.get("document")
        if not isinstance(document, dict):
            raise ValueError(f"无法读取 {doctype} {name}")
        transitions = result.data.get("actions")
        actions = [str(row.get("action")) for row in transitions if row.get("action")] if isinstance(transitions, list) else []
        process = document_process_summary(doctype, document, actions)
        history = result.data.get("workflow_history")
        process["history"] = history if isinstance(history, list) else []
        comments = result.data.get("workflow_comments")
        process["comments"] = comments if isinstance(comments, list) else []
        return {
            "doctype": doctype,
            "name": name,
            "label": next(
                (label for _, _, doctypes in DOCUMENT_MODULES for candidate, label, _ in doctypes if candidate == doctype),
                doctype,
            ),
            "document": document,
            "process": process,
        }

    def apply_workflow_action(
        self,
        user: str,
        doctype: str,
        name: str,
        action: str,
        *,
        comment: str = "",
        request_id: str = "",
        project: str = "",
        conversation_id: str = "default",
    ) -> dict[str, Any]:
        if not user or not doctype or not name or not action:
            raise ValueError("user、doctype、name 和 action 必填")
        if doctype not in ALLOWED_DOCUMENT_TYPES:
            raise ValueError(f"测试台暂不支持处理 {doctype}")
        if "驳回" in action and not comment.strip():
            raise ValueError("驳回时必须填写原因")
        store = None
        session = None
        if request_id:
            store = self.scoped_session_store(user, project, conversation_id)
            employee = next((row for row in employee_catalog() if row["user_email"] == user), None)
            session = store.load(user, profile=employee["profile"] if employee else "general")
            if request_id in session.idempotency_results:
                return session.idempotency_results[request_id]
        client = self.client(user)
        available = client.get_workflow_actions(doctype, name)
        if not available.ok or not isinstance(available.data, list):
            raise ValueError(available.user_message or available.error or "无法读取当前工作流动作")
        allowed_actions = {str(row.get("action")) for row in available.data if row.get("action")}
        if action not in allowed_actions:
            raise ValueError(f"当前账号不能对该单据执行“{action}”")
        result = client.call_method(
            "agent_bridge.api.apply_workflow_action_with_comment",
            {
                "doctype": doctype,
                "name": name,
                "action": action,
                "comment": comment.strip(),
            },
        )
        if not result.ok:
            raise ValueError(result.user_message or result.error or f"工作流动作“{action}”执行失败")
        payload = self.document(user, doctype, name)
        if request_id and store and session:
            session.remember_request(request_id, payload)
            store.save(session)
        return payload

    def submit_document(
        self,
        user: str,
        doctype: str,
        name: str,
        *,
        request_id: str = "",
        project: str = "",
        conversation_id: str = "default",
    ) -> dict[str, Any]:
        if not user or not doctype or not name:
            raise ValueError("user、doctype 和 name 必填")
        if doctype not in ALLOWED_DOCUMENT_TYPES:
            raise ValueError(f"测试台暂不支持提交 {doctype}")
        store = None
        session = None
        if request_id:
            store = self.scoped_session_store(user, project, conversation_id)
            employee = next((row for row in employee_catalog() if row["user_email"] == user), None)
            session = store.load(user, profile=employee["profile"] if employee else "general")
            if request_id in session.idempotency_results:
                return session.idempotency_results[request_id]
        client = self.client(user)
        detail = client.get_document(doctype, name)
        if not detail.ok or not isinstance(detail.data, dict):
            raise ValueError(detail.user_message or detail.error or f"无法读取 {doctype} {name}")
        if str(detail.data.get("workflow_state") or "").strip():
            raise ValueError("该单据已启用审批工作流，请执行当前工作流动作，不能直接提交。")
        result = client.submit_document(doctype, name)
        if not result.ok:
            raise ValueError(result.user_message or result.error or f"提交 {doctype} {name} 失败")
        payload = self.document(user, doctype, name)
        if request_id and store and session:
            session.remember_request(request_id, payload)
            store.save(session)
        return payload

    def reset_documents(self, user: str, project: str) -> dict[str, Any]:
        if not user or not project:
            raise ValueError("user 和 project 必填")
        snapshots = [
            self.documents(user, project, module=module, page_size=50)
            for module in MODULE_DOCTYPES
        ]
        groups = {
            group["doctype"]: group
            for snapshot in snapshots
            for module_row in snapshot["modules"]
            for group in module_row["groups"]
        }
        client = self.client(user)
        deleted: list[dict[str, str]] = []
        failed: list[dict[str, str]] = []
        for doctype in DOCUMENT_RESET_ORDER:
            for row in groups.get(doctype, {}).get("documents", []):
                name = str(row.get("name") or "")
                if not name:
                    continue
                if int(row.get("docstatus") or 0) == 1:
                    cancelled = client.cancel_document(doctype, name)
                    if not cancelled.ok:
                        failed.append({
                            "doctype": doctype,
                            "name": name,
                            "stage": "cancel",
                            "error": cancelled.user_message or cancelled.error or "取消失败",
                        })
                        continue
                removed = client.delete_document(doctype, name)
                if removed.ok:
                    deleted.append({"doctype": doctype, "name": name})
                else:
                    failed.append({
                        "doctype": doctype,
                        "name": name,
                        "stage": "delete",
                        "error": removed.user_message or removed.error or "删除失败",
                    })
        return {
            "project": project,
            "erpnext_project": snapshots[0]["erpnext_project"] if snapshots else project,
            "deleted": deleted,
            "failed": failed,
            "deleted_count": len(deleted),
            "failed_count": len(failed),
        }

    def _validate_agent_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate the cheap request scope before a background run is created."""
        user = str(payload.get("user") or "").strip()
        project_code = str(payload.get("project_code") or "").strip()
        conversation_id = str(payload.get("conversation_id") or "default").strip() or "default"
        text = str(payload.get("text") or "").strip()
        event = payload.get("event") if isinstance(payload.get("event"), dict) else None
        if not user:
            raise ValueError("user 必填")
        if not project_code:
            raise ValueError("project_code 必填")
        employee = next((row for row in employee_catalog() if row["user_email"] == user), None)
        project = next((row for row in project_catalog() if row["project_code"] == project_code), None)
        if not employee or not project:
            raise ValueError("未知员工或项目")
        if user not in {row["user_email"] for row in project.get("employees") or []}:
            raise PermissionError("当前员工不属于所选项目")
        candidate = event.get("candidate") if event and event.get("type") == "select_candidate" else None
        if candidate is not None and (not isinstance(candidate, dict) or not candidate.get("item_code")):
            raise ValueError("候选物料事件缺少 item_code")
        if not text and not isinstance(candidate, dict):
            raise ValueError("text 必填")
        return {
            "user": user,
            "project_code": project_code,
            "conversation_id": conversation_id,
            "text": text,
            "event": event,
            "employee": employee,
            "project": project,
        }

    def _ensure_run_registry(self) -> None:
        # Some focused unit tests construct the service with __new__ to avoid external setup.
        if not hasattr(self, "_run_lock"):
            self._run_lock = threading.Lock()
        if not hasattr(self, "_runs"):
            self._runs = {}

    def _set_run_progress(self, run_id: str, stage: str, label: str) -> None:
        self._ensure_run_registry()
        now = time.time()
        with self._run_lock:
            run = self._runs.get(run_id)
            if not run or run.get("status") != "running":
                return
            run.update({"stage": stage, "stage_label": label, "updated_at": now})

    def _run_status(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_run_registry()
        user = str(payload.get("user") or "").strip()
        project_code = str(payload.get("project_code") or "").strip()
        conversation_id = str(payload.get("conversation_id") or "default").strip() or "default"
        with self._run_lock:
            run = self._runs.get(run_id)
            if not run:
                raise ValueError("找不到该助理运行记录，可能已过期")
            if run["user"] != user or run["project_code"] != project_code or run["conversation_id"] != conversation_id:
                raise PermissionError("不能读取其他员工或项目的助理运行记录")
            return deepcopy(run)

    def run_status(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._run_status(str(run_id or "").strip(), payload)

    def start_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Start an OpenClaw turn without blocking the HTTP request."""
        context = self._validate_agent_request(payload)
        self._ensure_run_registry()
        run_id = uuid4().hex
        now = time.time()
        record = {
            "run_id": run_id,
            "user": context["user"],
            "project_code": context["project_code"],
            "conversation_id": context["conversation_id"],
            "status": "running",
            "stage": "starting",
            "stage_label": "小助理正在准备请求...",
            "started_at": now,
            "updated_at": now,
        }
        with self._run_lock:
            self._runs[run_id] = record
            # Keep a bounded in-memory status cache. The session file remains the durable chat record.
            if len(self._runs) > 100:
                finished = [key for key, value in self._runs.items() if value.get("status") != "running"]
                for key in finished[: max(1, len(self._runs) - 100)]:
                    self._runs.pop(key, None)
        thread = threading.Thread(target=self._run_in_background, args=(run_id, dict(payload)), daemon=True)
        thread.start()
        return {key: record[key] for key in ("run_id", "status", "stage", "stage_label", "started_at", "updated_at")}

    def _run_in_background(self, run_id: str, payload: dict[str, Any]) -> None:
        stop = threading.Event()
        phases = (
            ("connecting", "小助理正在连接业务服务...", 0.8),
            ("planning", "小助理正在理解你的需求...", 1.7),
            ("discovering", "小助理正在查找相关业务能力...", 2.8),
            ("guides", "小助理正在读取业务说明书...", 4.0),
            ("resolving", "小助理正在查询物料、项目和仓库...", 6.0),
            ("preparing", "小助理正在准备可执行的业务操作...", 8.0),
        )

        def advance() -> None:
            for stage, label, delay in phases:
                if stop.wait(delay):
                    return
                self._set_run_progress(run_id, stage, label)

        progress_thread = threading.Thread(target=advance, daemon=True)
        progress_thread.start()
        try:
            result = self.run(
                payload,
                progress=lambda stage, label: self._set_run_progress(run_id, stage, label),
            )
            status = str(result.get("status") or "failed")
            terminal = {
                "completed": ("completed", "小助理已完成处理。"),
                "needs_confirmation": ("needs_confirmation", "小助理已准备好，请确认后执行。"),
                "needs_clarification": ("needs_clarification", "小助理需要你补充一点信息。"),
                "failed": ("failed", "小助理处理失败。"),
            }.get(status, (status, "小助理已返回结果。"))
            now = time.time()
            with self._run_lock:
                run = self._runs.get(run_id)
                if run:
                    run.update({"status": terminal[0], "stage": terminal[0], "stage_label": terminal[1], "updated_at": now, "result": result})
        except Exception as exc:  # pragma: no cover - exercised through the HTTP boundary
            now = time.time()
            with self._run_lock:
                run = self._runs.get(run_id)
                if run:
                    run.update({"status": "failed", "stage": "failed", "stage_label": "小助理处理失败。", "updated_at": now, "error": str(exc)})
        finally:
            stop.set()
            progress_thread.join(timeout=0.2)

    def run(self, payload: dict[str, Any], *, progress: Callable[[str, str], None] | None = None) -> dict[str, Any]:
        user = str(payload.get("user") or "").strip()
        project_code = str(payload.get("project_code") or "").strip()
        conversation_id = str(payload.get("conversation_id") or "default").strip() or "default"
        text = str(payload.get("text") or "").strip()
        event = payload.get("event") if isinstance(payload.get("event"), dict) else None
        if not user:
            raise ValueError("user 必填")
        if not project_code:
            raise ValueError("project_code 必填")
        employee = next((row for row in employee_catalog() if row["user_email"] == user), None)
        project = next((row for row in project_catalog() if row["project_code"] == project_code), None)
        if not employee or not project:
            raise ValueError("未知员工或项目")
        if user not in {row["user_email"] for row in project.get("employees") or []}:
            raise PermissionError("当前员工不属于所选项目")

        candidate = event.get("candidate") if event and event.get("type") == "select_candidate" else None
        if candidate is not None and (not isinstance(candidate, dict) or not candidate.get("item_code")):
            raise ValueError("候选物料事件缺少 item_code")
        if not text and isinstance(candidate, dict):
            label = candidate.get("sku_name") or candidate.get("item_name") or candidate["item_code"]
            text = f"选择 {label}（{candidate['item_code']}）并继续。"
        if not text:
            raise ValueError("text 必填")

        allowed_projects = [
            row["project_code"]
            for row in project_catalog()
            if user in {person["user_email"] for person in row.get("employees") or []}
        ]
        self.capability_repository.upsert_identity(
            external_subject=workbench_external_subject(user),
            employee_user=user,
            profile_name=str(employee["profile"]),
            agent_id="main",
            default_project=project_code,
            allowed_projects=allowed_projects,
        )
        if progress:
            progress("openclaw", "小助理正在处理业务请求...")
        runtime_kwargs = {
            "text": text,
            "user": user,
            "employee_name": str(employee.get("employee_name") or user),
            "position": str(employee.get("project_position") or employee.get("position") or ""),
            "project_code": project_code,
            "project_label": str(project.get("project_short_name") or project_code),
            "warehouse": str(payload.get("warehouse") or project.get("warehouse_code") or ""),
            "conversation_id": conversation_id,
            "event": event,
        }
        if progress is not None:
            runtime_kwargs["progress"] = progress
        result = self.openclaw_runtime.run(**runtime_kwargs)
        response = dict(result)
        response["execute"] = False
        response["conversation_id"] = conversation_id
        response["document_links"] = result_document_links(response, self.base_url)
        response["business_errors"] = response.get("business_errors") or business_error_cards(response)

        store = self.scoped_session_store(user, project_code, conversation_id)
        session = store.load(user, profile=str(employee["profile"]))
        pending_id = str(response.get("pending_id") or "")
        session.pending_action = (
            {"runtime": "openclaw_manual", "pending_id": pending_id}
            if response.get("status") == "needs_confirmation" and pending_id
            else None
        )
        session.add_turn({"user_text": text, "result": response})
        store.save(session)
        return response

    def run_existing(self, payload: dict[str, Any]) -> dict[str, Any]:
        user = str(payload.get("user") or "").strip()
        text = str(payload.get("text") or "").strip()
        project_code = str(payload.get("project_code") or "").strip()
        conversation_id = str(payload.get("conversation_id") or "default").strip() or "default"
        event = payload.get("event")
        if not user:
            raise ValueError("user 必填")
        store = self.scoped_session_store(user, project_code, conversation_id)
        if isinstance(event, dict) and event.get("type") == "select_candidate":
            candidate = event.get("candidate")
            if not isinstance(candidate, dict) or not candidate.get("item_code"):
                raise ValueError("候选物料事件缺少 item_code")
            employee = next((row for row in employee_catalog() if row["user_email"] == user), None)
            if not employee:
                raise ValueError("未知员工账号")
            session = store.load(user, profile=employee["profile"])
            entity_id = str(event.get("entity_id") or "selected_item")
            session.selected_entities[entity_id] = {
                "kind": "item",
                "value": candidate["item_code"],
                "label": candidate.get("item_name") or candidate.get("sku_name") or candidate["item_code"],
                "row": candidate,
            }
            store.save(session)
            text = text or "使用我刚刚确认的标准物料继续当前任务。"
        if not text:
            raise ValueError("text 必填")
        execute = bool(payload.get("execute"))
        request_id = str(payload.get("request_id") or "").strip() or None
        erpnext_project = ""
        if project_code:
            project_key = (user, project_code)
            erpnext_project = self._project_name_cache.get(project_key, "")
            if not erpnext_project:
                erpnext_project = self.erpnext_project_name(self.client(user), project_code)
                self._project_name_cache[project_key] = erpnext_project
        context = {
            "project_code": project_code or None,
            "erpnext_project": erpnext_project or None,
            "warehouse": self.erpnext_warehouse_name(str(payload.get("warehouse") or "")) or None,
            "conversation_id": conversation_id,
        }
        result = self.runtime(store).run_once(text, user=user, execute=execute, request_id=request_id, context=context)
        response = result.to_dict()
        response["execute"] = execute
        response["conversation_id"] = conversation_id
        response["business_errors"] = business_error_cards(response)
        response["document_links"] = result_document_links(response, self.base_url)
        return response

    def confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        user = str(payload.get("user") or "").strip()
        project_code = str(payload.get("project_code") or "").strip()
        conversation_id = str(payload.get("conversation_id") or "default").strip() or "default"
        if not user or not project_code:
            raise ValueError("user 和 project_code 必填")
        employee = next((row for row in employee_catalog() if row["user_email"] == user), None)
        if not employee:
            raise ValueError("未知员工账号")
        store = self.scoped_session_store(user, project_code, conversation_id)
        session = store.load(user, profile=str(employee["profile"]))
        pending = session.pending_action if isinstance(session.pending_action, dict) else {}
        pending_id = str(pending.get("pending_id") or "")
        if pending.get("runtime") != "openclaw_manual" or not pending_id:
            raise ValueError("当前会话没有等待确认的新 Agent 操作")
        response = self.openclaw_runtime.confirm(
            pending_id=pending_id,
            user=user,
            project_code=project_code,
            conversation_id=conversation_id,
        )
        response["execute"] = True
        response["conversation_id"] = conversation_id
        response["document_links"] = result_document_links(response, self.base_url)
        session.pending_action = None
        session.add_turn({"user_text": "", "result": response})
        store.save(session)
        return response

    def compare_runtimes(self, payload: dict[str, Any]) -> dict[str, Any]:
        user = str(payload.get("user") or "").strip()
        project_code = str(payload.get("project_code") or "").strip()
        text = str(payload.get("text") or "").strip()
        include_existing = payload.get("include_existing") is True
        if not user or not project_code or not text:
            raise ValueError("user、project_code 和 text 必填")
        employee = next((row for row in employee_catalog() if row["user_email"] == user), None)
        project = next((row for row in project_catalog() if row["project_code"] == project_code), None)
        if not employee or not project:
            raise ValueError("未知员工或项目")
        if user not in {row["user_email"] for row in project.get("employees") or []}:
            raise PermissionError("当前员工不属于所选项目")

        comparison_id = uuid4().hex

        def existing_preview() -> dict[str, Any]:
            started = time.perf_counter()
            result = self.run_existing({
                "user": user,
                "project_code": project_code,
                "text": text,
                "execute": False,
                "conversation_id": f"compare-existing-{comparison_id}",
            })
            return summarize_existing_result(result, duration_ms=round((time.perf_counter() - started) * 1000))

        def openclaw_preview() -> dict[str, Any]:
            return self.openclaw_preview.run(
                text=text,
                project_label=str(project.get("project_short_name") or project_code),
                employee_name=str(employee.get("employee_name") or user),
            )

        def safe(call: Any, runtime_name: str) -> dict[str, Any]:
            try:
                return call()
            except Exception as exc:
                return {
                    "runtime": runtime_name,
                    "status": "failed",
                    "message": str(exc),
                    "duration_ms": 0,
                    "steps": [],
                    "questions": [],
                    "question_count": 0,
                    "tool_summary": {"calls": 0, "tools": [], "failures": 1},
                }

        if include_existing:
            with ThreadPoolExecutor(max_workers=2) as executor:
                old_future = executor.submit(safe, existing_preview, "existing")
                new_future = executor.submit(safe, openclaw_preview, "openclaw_manual")
                existing = old_future.result()
                openclaw = new_future.result()
        else:
            existing = {
                "runtime": "existing",
                "status": "disabled",
                "message": "旧版 Runtime 已暂停，本次没有调用模型，也没有消耗 Token。",
                "duration_ms": 0,
                "steps": [],
                "questions": [],
                "question_count": 0,
                "tool_summary": {"calls": 0, "tools": [], "failures": 0},
            }
            openclaw = safe(openclaw_preview, "openclaw_manual")
        return {
            "comparison_id": comparison_id,
            "mode": "ab_preview" if include_existing else "openclaw_only",
            "notice": (
                "两侧均只做预览；OpenClaw 对比会话在插件层禁止写入 ERPNext。"
                if include_existing
                else "本次只运行 OpenClaw 新版；旧版 Runtime 未调用，不消耗额外 Token。"
            ),
            "request": {
                "text": text,
                "project_code": project_code,
                "project_label": project.get("project_short_name"),
                "user": user,
                "employee_name": employee.get("employee_name"),
            },
            "existing": existing,
            "openclaw": openclaw,
        }


class AgentWorkbenchHandler(BaseHTTPRequestHandler):
    server_version = "NexterpAgentWorkbench/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/workbench-assets/"):
            asset_response(self, ASSET_DIR / Path(parsed.path).name)
            return
        if parsed.path == "/":
            html_response(self, HTML_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/agent-runtime", "/agent-runtime/"}:
            html_response(self, RUNTIME_EXPLORER_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/operation-model", "/operation-model/"}:
            html_response(self, OPERATION_MODEL_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/agent-runtime-compare", "/agent-runtime-compare/"}:
            html_response(self, RUNTIME_COMPARE_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path == "/favicon.ico":
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
            return
        if parsed.path == "/api/employees":
            json_response(self, {"ok": True, "employees": employee_catalog()})
            return
        if parsed.path == "/api/catalog":
            json_response(self, {"ok": True, "projects": project_catalog(), "employees": employee_catalog()})
            return
        if parsed.path == "/api/workbench/bootstrap":
            json_response(self, {"ok": True, **self.server.service.bootstrap()})  # type: ignore[attr-defined]
            return
        if parsed.path == "/api/operation-model/material-request":
            json_response(self, {"ok": True, **MaterialRequestOperationCatalog().demo()})
            return
        if parsed.path == "/api/operation-model/options":
            query = parse_qs(parsed.query)
            options = OperationReferenceDataCatalog(ROOT).options(
                (query.get("entity") or [""])[0],
                query=(query.get("q") or [""])[0],
                project=(query.get("project") or [""])[0],
                item_code=(query.get("item_code") or [""])[0],
            )
            json_response(self, {"ok": True, "options": options})
            return
        if parsed.path == "/api/session":
            query = parse_qs(parsed.query)
            payload = self.server.service.session_history(  # type: ignore[attr-defined]
                (query.get("user") or [""])[0],
                (query.get("project") or [""])[0],
                (query.get("conversation_id") or ["default"])[0],
            )
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/agent/run":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.run_status(  # type: ignore[attr-defined]
                    (query.get("run_id") or [""])[0],
                    {
                        "user": (query.get("user") or [""])[0],
                        "project_code": (query.get("project_code") or [""])[0],
                        "conversation_id": (query.get("conversation_id") or ["default"])[0],
                    },
                )
            except PermissionError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 403)
                return
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, "run": payload})
            return
        if parsed.path == "/api/inbox":
            query = parse_qs(parsed.query)
            payload = self.server.service.inbox(  # type: ignore[attr-defined]
                (query.get("user") or [""])[0],
                (query.get("project") or [""])[0],
                limit=int((query.get("limit") or [30])[0]),
            )
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/procurement/pending":
            query = parse_qs(parsed.query)
            payload = self.server.service.pending_procurement(  # type: ignore[attr-defined]
                (query.get("user") or [""])[0],
                (query.get("project") or [""])[0],
                scope=(query.get("scope") or ["project"])[0],
                limit=int((query.get("limit") or [500])[0]),
            )
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/procurement/quotations":
            query = parse_qs(parsed.query)
            payload = self.server.service.supplier_quotations(  # type: ignore[attr-defined]
                (query.get("user") or [""])[0],
                (query.get("request_for_quotation") or [""])[0],
            )
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/documents":
            query = parse_qs(parsed.query)
            payload = self.server.service.documents(  # type: ignore[attr-defined]
                (query.get("user") or [""])[0],
                (query.get("project") or [""])[0],
                module=(query.get("module") or ["buying"])[0],
                status=(query.get("status") or [""])[0],
                page=int((query.get("page") or [1])[0]),
                page_size=int((query.get("page_size") or [20])[0]),
                mine_only=(query.get("mine_only") or ["0"])[0] in {"1", "true", "True"},
            )
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/document":
            query = parse_qs(parsed.query)
            payload = self.server.service.document(  # type: ignore[attr-defined]
                (query.get("user") or [""])[0],
                (query.get("doctype") or [""])[0],
                (query.get("name") or [""])[0],
            )
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/health":
            json_response(self, {"ok": True, "service": "agent-workbench", "profile": self.server.service.profile})  # type: ignore[attr-defined]
            return
        json_response(self, {"ok": False, "error": "not_found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        try:
            if self.path == "/api/operation-model/compile":
                request = read_json(self)
                evaluation = MaterialRequestOperationCatalog().evaluate(request)
                json_response(self, {"ok": True, "evaluation": evaluation.model_dump(mode="json")})
                return
            if self.path == "/api/agent-runtime/compare":
                payload = self.server.service.compare_runtimes(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/session/reset":
                request = read_json(self)
                payload = self.server.service.reset_session(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("project_code") or "").strip(),
                    str(request.get("conversation_id") or "default").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/documents/reset":
                request = read_json(self)
                payload = self.server.service.reset_documents(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("project") or "").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/workflow/action":
                request = read_json(self)
                payload = self.server.service.apply_workflow_action(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("doctype") or "").strip(),
                    str(request.get("name") or "").strip(),
                    str(request.get("action") or "").strip(),
                    comment=str(request.get("comment") or "").strip(),
                    request_id=str(request.get("request_id") or "").strip(),
                    project=str(request.get("project_code") or "").strip(),
                    conversation_id=str(request.get("conversation_id") or "default").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/document/submit":
                request = read_json(self)
                payload = self.server.service.submit_document(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("doctype") or "").strip(),
                    str(request.get("name") or "").strip(),
                    request_id=str(request.get("request_id") or "").strip(),
                    project=str(request.get("project_code") or "").strip(),
                    conversation_id=str(request.get("conversation_id") or "default").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/procurement/rfq":
                request = read_json(self)
                payload = self.server.service.create_request_for_quotation(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("project_code") or "").strip(),
                    list(request.get("selected_rows") or []),
                    list(request.get("supplier_codes") or []),
                    schedule_date=str(request.get("schedule_date") or "").strip(),
                    message_for_supplier=str(request.get("message_for_supplier") or "").strip(),
                    request_id=str(request.get("request_id") or "").strip(),
                    conversation_id=str(request.get("conversation_id") or "default").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/procurement/quotation":
                request = read_json(self)
                payload = self.server.service.create_supplier_quotation(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("project_code") or "").strip(),
                    str(request.get("request_for_quotation") or "").strip(),
                    str(request.get("supplier_code") or "").strip(),
                    list(request.get("offers") or []),
                    valid_till=str(request.get("valid_till") or "").strip(),
                    terms=str(request.get("terms") or "").strip(),
                    request_id=str(request.get("request_id") or "").strip(),
                    conversation_id=str(request.get("conversation_id") or "default").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/procurement/compare":
                request = read_json(self)
                payload = self.server.service.compare_supplier_quotations(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    list(request.get("supplier_quotations") or []),
                    include_drafts=bool(request.get("include_drafts")),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/procurement/purchase-order":
                request = read_json(self)
                payload = self.server.service.create_purchase_order_from_supplier_quotation(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("project_code") or "").strip(),
                    str(request.get("supplier_quotation") or "").strip(),
                    selected_items=list(request.get("selected_items") or []),
                    request_id=str(request.get("request_id") or "").strip(),
                    conversation_id=str(request.get("conversation_id") or "default").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/procurement/purchase-receipt":
                request = read_json(self)
                payload = self.server.service.create_purchase_receipt_from_purchase_order(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("project_code") or "").strip(),
                    str(request.get("purchase_order") or "").strip(),
                    selected_items=list(request.get("selected_items") or []),
                    request_id=str(request.get("request_id") or "").strip(),
                    conversation_id=str(request.get("conversation_id") or "default").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/procurement/discrepancy":
                request = read_json(self)
                payload = self.server.service.record_purchase_receipt_discrepancy(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("project_code") or "").strip(),
                    str(request.get("purchase_receipt") or "").strip(),
                    str(request.get("description") or "").strip(),
                    items=list(request.get("items") or []),
                    discrepancy_type=str(request.get("discrepancy_type") or "spec_mismatch").strip(),
                    severity=str(request.get("severity") or "Medium").strip(),
                    assigned_to=str(request.get("assigned_to") or "").strip(),
                    request_id=str(request.get("request_id") or "").strip(),
                    conversation_id=str(request.get("conversation_id") or "default").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/procurement/purchase-return":
                request = read_json(self)
                payload = self.server.service.create_purchase_return_from_receipt(  # type: ignore[attr-defined]
                    str(request.get("user") or "").strip(),
                    str(request.get("project_code") or "").strip(),
                    str(request.get("purchase_receipt") or "").strip(),
                    str(request.get("reason") or "").strip(),
                    items=list(request.get("items") or []),
                    request_id=str(request.get("request_id") or "").strip(),
                    conversation_id=str(request.get("conversation_id") or "default").strip(),
                )
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/agent/confirm":
                response = self.server.service.confirm(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": response.get("status") != "failed", "result": response})
                return
            if self.path == "/api/agent/turn/start":
                run = self.server.service.start_run(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "run": run})
                return
            if self.path not in {"/api/agent", "/api/agent/turn"}:
                json_response(self, {"ok": False, "error": "not_found"}, 404)
                return
            response = self.server.service.run(read_json(self))  # type: ignore[attr-defined]
            json_response(self, {"ok": response.get("status") != "failed", "result": response})
        except PermissionError as exc:
            json_response(self, {"ok": False, "error": str(exc)}, 403)
        except (ValueError, json.JSONDecodeError) as exc:
            json_response(self, {"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover - local service boundary
            json_response(self, {"ok": False, "error": str(exc)}, 500)

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write("[agent-workbench] " + format % args + "\n")


def build_server(host: str, port: int, profile: str) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), AgentWorkbenchHandler)
    server.service = AgentWorkbenchService(profile)  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the employee natural-language Agent workbench.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    parser.add_argument("--profile", default="civil")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    load_dotenv(args.env_file)
    if not HTML_PATH.exists():
        raise FileNotFoundError(HTML_PATH)
    if not RUNTIME_EXPLORER_PATH.exists():
        raise FileNotFoundError(RUNTIME_EXPLORER_PATH)
    if not RUNTIME_COMPARE_PATH.exists():
        raise FileNotFoundError(RUNTIME_COMPARE_PATH)
    server = build_server(args.host, args.port, args.profile)
    print(f"Employee Agent workbench: http://{args.host}:{args.port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
