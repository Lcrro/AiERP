from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.parse import parse_qs, quote, urlparse


ROOT = Path(__file__).resolve().parents[3]

from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime
from nexterp_agent.agent_runtime.credentials import load_user_credentials
from nexterp_agent.agent_runtime.session import RuntimeSessionStore
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.master_data import MasterDataRelease


HTML_PATH = ROOT / "tools" / "agent_workbench.html"
ASSET_DIR = ROOT / "tools" / "workbench"
ASSET_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}
DOCTYPE_ROUTES = {
    "Material Request": "material-request",
    "Request for Quotation": "request-for-quotation",
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
    "Material Request",
    "Task",
)
DOCTYPE_ROUTES.update({"Payment Entry": "payment-entry", "Task": "task"})
ALLOWED_DOCUMENT_TYPES = frozenset(DOCTYPE_ROUTES)
SUBMITTABLE_DOCUMENT_TYPES = frozenset({
    "Material Request",
    "Request for Quotation",
    "Purchase Order",
    "Purchase Receipt",
    "Purchase Invoice",
    "Stock Entry",
})
DOCUMENT_LIST_FIELDS = {
    "Material Request": ["name", "title", "status", "workflow_state", "transaction_date", "schedule_date", "owner", "modified", "docstatus"],
    "Request for Quotation": ["name", "status", "transaction_date", "owner", "modified", "docstatus"],
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


def employee_catalog() -> list[dict[str, str]]:
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
    payloads = result.get("tool_results") or ([result.get("tool_result")] if result.get("tool_result") else [])
    seen: set[tuple[str, str]] = set()
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


class AgentWorkbenchService:
    def __init__(self, profile: str = "civil") -> None:
        self.profile = profile
        prefix = f"NEXTERP_{profile.upper()}_"
        self.base_url = os.environ[prefix + "BASE_URL"]
        self.host_header = os.getenv(prefix + "HOST_HEADER")
        self.session_store = RuntimeSessionStore()
        self._project_name_cache: dict[tuple[str, str], str] = {}

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
        def matches(row: dict[str, Any]) -> bool:
            name = str(row.get("name") or "")
            if not name:
                return False
            client = self.client(user)
            detail = client.get_document(doctype, name)
            if not detail.ok or not isinstance(detail.data, dict):
                return False
            items = detail.data.get("items")
            return isinstance(items, list) and any(
                str(item.get("project") or "") == erpnext_project
                for item in items
            )

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

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
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
        context = {
            "project_code": project_code or None,
            "warehouse": str(payload.get("warehouse") or "").strip() or None,
        }
        result = self.runtime(store).run_once(text, user=user, execute=execute, request_id=request_id, context=context)
        response = result.to_dict()
        response["execute"] = execute
        response["conversation_id"] = conversation_id
        response["document_links"] = result_document_links(response, self.base_url)
        return response

    def confirm(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = dict(payload)
        request["execute"] = True
        request.setdefault("text", "确认执行当前待处理操作。")
        return self.run(request)


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
        if parsed.path == "/api/session":
            query = parse_qs(parsed.query)
            payload = self.server.service.session_history(  # type: ignore[attr-defined]
                (query.get("user") or [""])[0],
                (query.get("project") or [""])[0],
                (query.get("conversation_id") or ["default"])[0],
            )
            json_response(self, {"ok": True, **payload})
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
            if self.path == "/api/agent/confirm":
                response = self.server.service.confirm(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": response.get("status") != "failed", "result": response})
                return
            if self.path not in {"/api/agent", "/api/agent/turn"}:
                json_response(self, {"ok": False, "error": "not_found"}, 404)
                return
            response = self.server.service.run(read_json(self))  # type: ignore[attr-defined]
            json_response(self, {"ok": response.get("status") != "failed", "result": response})
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
