from __future__ import annotations

import argparse
import csv
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
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
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4
from http.cookies import SimpleCookie


ROOT = Path(__file__).resolve().parents[3]

from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime
from nexterp_agent.agent_runtime.credentials import DEFAULT_CREDENTIALS_PATH, load_user_credentials
from nexterp_agent.agent_runtime.operation_catalog import MaterialRequestOperationCatalog
from nexterp_agent.agent_runtime.operation_reference_data import OperationReferenceDataCatalog
from nexterp_agent.agent_runtime.session import RuntimeSessionStore
from nexterp_agent.capability_service.catalog import CapabilityCatalogRepository
from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.agent_runtime.tool_access import make_tool_access_policy
from nexterp_agent.agent_runtime.tool_gateway import ToolGateway, ToolSession
from nexterp_agent.master_data import MasterDataRelease
from nexterp_agent.item_master import (
    HighRecallBatchMaterialIntakeAnalyzer,
    MaterialDraftBatch,
    MaterialIntakeRow,
    MaterialTypeClassifier,
    ProcurementBatchPilotJobManager,
    ProcurementBatchReviewStore,
    RuntimeMaterialPublicationStore,
    build_material_drafts,
    revise_material_drafts,
    TARIFF_EXPECTED_PAGES,
    TARIFF_EXPECTED_BYTES,
    TARIFF_SOURCE_URL,
    TARIFF_SOURCE_VERSION,
    TariffExtractionJobManager,
    DECLARATION_EXPECTED_PAGES,
    DECLARATION_SOURCE_URL,
    DECLARATION_SOURCE_VERSION,
    TariffDeclarationJobManager,
    load_declaration_profiles,
)
from nexterp_agent.item_master.tariff_taxonomy import (
    TariffTaxonomyIndex,
    resolve_tariff_taxonomy_source,
)
from nexterp_agent.item_master.reference_catalog import ChatgptClassificationIndex, GpcReferenceIndex
from nexterp_agent.item_master.reference_catalog_database import (
    DEFAULT_REFERENCE_CATALOG_DATABASE_PATH,
    ReferenceCatalogDatabase,
)
from nexterp_agent.workbench.business_portal import BUSINESS_ACTIONS, BusinessCommandStore
from nexterp_agent.workbench.openclaw_compare import OpenClawPreviewRunner, summarize_existing_result
from nexterp_agent.workbench.openclaw_runtime import (
    OpenClawWorkbenchRunner,
    workbench_external_subject,
    workbench_session_key,
)


HTML_PATH = ROOT / "tools" / "agent_workbench.html"
BUSINESS_PORTAL_PATH = ROOT / "tools" / "business_portal.html"
RUNTIME_EXPLORER_PATH = ROOT / "tools" / "agent_runtime_explorer.html"
OPERATION_MODEL_PATH = ROOT / "tools" / "operation_model_explorer.html"
RUNTIME_COMPARE_PATH = ROOT / "tools" / "agent_runtime_compare.html"
MATERIAL_ITEM_LAB_PATH = ROOT / "tools" / "material_item_lab.html"
MATERIAL_INTAKE_LAB_PATH = ROOT / "tools" / "material_intake_lab.html"
MATERIAL_MARKETPLACE_PATH = ROOT / "tools" / "material_marketplace.html"
MATERIAL_MASTER_BROWSER_PATH = ROOT / "tools" / "material_master_browser.html"
CHATGPT_CLASSIFICATION_DATA_PATH = ROOT / "data" / "material_master" / "chatgpt_classification_v4" / "material_master_chatgpt_browser_data.json"
PROCUREMENT_BATCH_PILOT_PATH = ROOT / "tools" / "procurement_batch_pilot.html"
TARIFF_EXTRACTION_LAB_PATH = ROOT / "tools" / "tariff_extraction_lab.html"
TARIFF_DECLARATION_LAB_PATH = ROOT / "tools" / "tariff_declaration_lab.html"
TARIFF_FAMILY_REVIEW_BROWSER_PATH = ROOT / "tools" / "tariff_family_review_browser.html"
TARIFF_TAXONOMY_BROWSER_PATH = ROOT / "tools" / "tariff_taxonomy_browser.html"
TARIFF_FAMILY_REVIEW_DIR = ROOT / "data" / "material_master" / "tariff_family_review_v0_1"
TARIFF_TAXONOMY_RUNTIME_ROOT = ROOT / ".runtime" / "tariff-extraction"
TARIFF_DECLARATION_RUNTIME_ROOT = ROOT / ".runtime" / "tariff-declaration"
GPC_REFERENCE_RUNTIME_ROOT = ROOT / ".runtime" / "gpc-reference"
GPC_REFERENCE_VERSION = "2026-05"
GPC_MATERIAL_PLACEMENTS_PATH = ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl"
GPC_PROCUREMENT_TEMPLATE_CATALOG_PATH = ROOT / "data" / "material_master" / "procurement_template_catalog_v0_1.json"
GPC_PROCUREMENT_TYPE_PROFILES_PATH = ROOT / ".runtime" / "material-master" / "gpc-procurement-type-profiles.jsonl"
GPC_INTERNAL_EXTENSIONS_PATH = ROOT / "data" / "material_master" / "gpc_internal_extensions_v0_1.json"
GPC_REFERENCE_DATABASE_PATH = DEFAULT_REFERENCE_CATALOG_DATABASE_PATH
MATERIAL_ITEM_CODE_MAP_PATH = ROOT / ".runtime" / "erpnext-material-test" / "material-item-code-map.json"
MATERIAL_TEST_CREDENTIALS_PATH = ROOT / ".secrets" / "erpnext-material-test" / "user-api-credentials.json"
MATERIAL_CLASSIFICATION_V4_CREDENTIALS_PATH = ROOT / ".secrets" / "erpnext-material-classification-v4" / "user-api-credentials.json"
PROCUREMENT_BATCH_PILOT_RUNTIME_ROOT = ROOT / ".runtime" / "material-master" / "batch-pilot"
TARIFF_ATTRIBUTE_REVIEW_PATH = TARIFF_FAMILY_REVIEW_DIR / "fastener_review_v0_2" / "tariff_attribute_candidates.tsv"
TARIFF_ATTRIBUTE_SUMMARY_PATH = TARIFF_FAMILY_REVIEW_DIR / "fastener_review_v0_2" / "tariff_attribute_summary.json"
ASSET_DIR = ROOT / "tools" / "workbench"
ASSET_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}

CLASSIFICATION_SOURCES: tuple[dict[str, str], ...] = (
    {"code": "original", "label": "原分类（GPC）", "kind": "operational"},
    {"code": "chatgpt_v4", "label": "ChatGPT 分类（龙华 V4）", "kind": "classification_preview"},
)

# Business portal account routing is deliberately allow-listed.  The browser
# may request a classification source, but it can never provide an ERPNext
# URL, site name, credentials path, or ToolCall arguments.  The selected
# account is kept in a request context so all nested reads/writes in one
# portal request use the same isolated ERPNext site.
_BUSINESS_ACCOUNT_CONTEXT: ContextVar[str] = ContextVar("nexterp_business_account", default="")
BUSINESS_ACCOUNTS: tuple[dict[str, str], ...] = (
    {
        "code": "material_test",
        "label": "原 GPC 测试账套",
        "classification_source": "original",
        "site": "material-test.localhost",
        "base_url_env": "NEXTERP_MATERIAL_TEST_BASE_URL",
        "base_url_default": "http://127.0.0.1:8003",
        "host_header_env": "NEXTERP_MATERIAL_TEST_HOST_HEADER",
        "host_header_default": "material-test.localhost",
        "credentials_path_env": "NEXTERP_MATERIAL_TEST_CREDENTIALS_PATH",
        "credentials_path_default": str(MATERIAL_TEST_CREDENTIALS_PATH),
        "company_env": "NEXTERP_MATERIAL_TEST_COMPANY",
        "company_default": "Nexterp物料测试有限公司",
        "project_name_env": "NEXTERP_MATERIAL_TEST_PROJECT_NAME",
        "project_name_default": "PROJ-0001",
        "warehouse_suffix": " - NMT",
    },
    {
        "code": "classification_v4",
        "label": "ChatGPT 分类 V4 测试账套",
        "classification_source": "chatgpt_v4",
        "site": "material-classification-v4.localhost",
        "base_url_env": "NEXTERP_CLASSIFICATION_V4_BASE_URL",
        "base_url_default": "http://127.0.0.1:8004",
        "host_header_env": "NEXTERP_CLASSIFICATION_V4_HOST_HEADER",
        "host_header_default": "material-classification-v4.localhost",
        "credentials_path_env": "NEXTERP_CLASSIFICATION_V4_CREDENTIALS_PATH",
        "credentials_path_default": str(MATERIAL_CLASSIFICATION_V4_CREDENTIALS_PATH),
        "company_env": "NEXTERP_CLASSIFICATION_V4_COMPANY",
        "company_default": "Nexterp分类示范有限公司",
        "project_name_env": "NEXTERP_CLASSIFICATION_V4_PROJECT_NAME",
        "project_name_default": "PROJ-0001",
        "warehouse_suffix": " - NCV",
    },
)

MATERIAL_BROWSER_DATA_PATHS: dict[str, Path] = {
    "release_v1_1": ROOT / "data/material_master/release_v1_1/material_master_release_v1_1_browser_data.json",
    "type_dictionary_v0_5": ROOT / "data/material_master/governance_v0_5/material_master_type_governed_browser_data.json",
    "price_ready_v0_1": ROOT / "data/material_master/price_ready_release_v0_1/material_master_price_ready_browser_data.json",
    "release_v0_3": ROOT / "data/material_master/release_v0_3/material_master_release_v0_3_browser_data.json",
    "family_cohort_001": ROOT / "data/material_master/governance_v0_4/cohort_001_browser_data.json",
    "drill_family_governed": ROOT / "data/material_master/governance_v0_4/工具耗材_钻头/material_master_family_governed_browser_data.json",
    "original": ROOT / "data/material_master/material_master_browser_data.json",
    "reclassified": ROOT / "data/material_master/reclassification/material_master_browser_data_reclassified.json",
    "screw_governed": ROOT / "data/material_master/governance_v0_2/screw/material_master_screw_governed_preview.json",
    "manual_family": ROOT / "data/material_master/governance_v0_2/manual_family_mapping/material_master_manual_family_preview.json",
    "third_layer": ROOT / "data/material_master/governance_v0_2/manual_third_layer_mapping/material_master_third_layer_preview.json",
    "screw_bolt_third": ROOT / "data/material_master/governance_v0_2/manual_third_layer_mapping/material_master_screw_bolt_third_layer_preview.json",
    "chatgpt_v4": CHATGPT_CLASSIFICATION_DATA_PATH,
}


class BusinessInputError(ValueError):
    """A deterministic, user-facing validation failure before any write."""

    def __init__(self, message: str, *, error_code: str = "invalid_business_input", field_path: str = "") -> None:
        super().__init__(message)
        self.error_code = error_code
        self.field_path = field_path


def _load_material_item_code_map() -> dict[str, str]:
    """Load the runtime bridge from local publication ids to ERPNext Item codes."""

    try:
        payload = json.loads(MATERIAL_ITEM_CODE_MAP_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    mapping = payload.get("material_item_codes") if isinstance(payload, dict) else {}
    if not isinstance(mapping, dict):
        return {}
    return {
        str(source_id).strip(): str(item_code).strip()
        for source_id, item_code in mapping.items()
        if str(source_id).strip() and str(item_code).strip()
    }
DOCTYPE_ROUTES = {
    "Item": "item",
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
    "Purchase Order": ["name", "supplier", "status", "transaction_date", "grand_total", "currency", "owner", "modified", "docstatus", "per_received", "per_billed"],
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


def json_response(
    handler: BaseHTTPRequestHandler,
    payload: dict[str, Any],
    status: int = 200,
    *,
    headers: dict[str, str] | None = None,
    set_cookies: list[str] | None = None,
) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    for name, value in (headers or {}).items():
        handler.send_header(name, value)
    for cookie in set_cookies or []:
        handler.send_header("Set-Cookie", cookie)
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


def json_file_response(handler: BaseHTTPRequestHandler, path: Path) -> None:
    """Serve one explicitly allow-listed browser snapshot without exposing the data tree."""

    if not path.is_file() or path.suffix.lower() != ".json":
        json_response(handler, {"ok": False, "error": "分类数据不存在"}, HTTPStatus.NOT_FOUND)
        return
    try:
        data = path.read_bytes()
        json.loads(data.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        json_response(handler, {"ok": False, "error": "分类数据不可读取"}, HTTPStatus.BAD_GATEWAY)
        return
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    return json.loads(handler.rfile.read(length).decode("utf-8")) if length else {}


def _group_rows(rows: list[dict[str, Any]], *, key: Callable[[dict[str, Any]], str]) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for row in rows:
        value = key(row)
        if value not in grouped:
            grouped[value] = []
            order.append(value)
        grouped[value].append(row)
    return [(value, grouped[value]) for value in order]


def _count_rows(rows: list[dict[str, Any]], value_key: str, label_key: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    labels: dict[str, str] = {}
    for row in rows:
        value = str(row.get(value_key) or "")
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
        labels[value] = str(row.get(label_key) or value)
    return [{"code": value, "name": labels[value], "count": counts[value]} for value in sorted(counts)]


def _build_chatgpt_category_tree(rows: list[dict[str, Any]], query_terms: list[str]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in rows:
        haystack = str(row.get("search_text") or "").lower()
        if query_terms and not all(term in haystack for term in query_terms):
            continue
        top = str(row.get("top_group") or "未分类")
        second = str(row.get("sub_group") or "未细分")
        grouped.setdefault(top, {}).setdefault(second, []).append(row)
    result: list[dict[str, Any]] = []
    for top in sorted(grouped):
        children = []
        for second in sorted(grouped[top]):
            child_rows = grouped[top][second]
            children.append({
                "code": f"CHATGPT-L2-{top}|{second}",
                "name": second,
                "count": len(child_rows),
                "path": f"{top} / {second}",
                "children": [],
            })
        top_rows = [row for child in grouped[top].values() for row in child]
        result.append({
            "code": f"CHATGPT-L1-{top}",
            "name": top,
            "count": len(top_rows),
            "path": top,
            "children": children,
        })
    return result


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
            "role_code": row["role_code"],
            "department_code": row.get("department_code", ""),
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


BUSINESS_SANDBOX_EMPLOYEES: tuple[dict[str, Any], ...] = (
    {
        "employee_code": "EMP-PROCUREMENT-TEST",
        "employee_name": "采购测试员",
        "position": "采购",
        "role_code": "ROLE-PROCUREMENT-TEST",
        "department_code": "DEPT-UP",
        "user_email": "procurement.test@stec-up.local",
        "profile": "procurement_agent",
        "default_project_code": "PRJ-HL-13",
        "default_warehouse_code": "WH-HL-13",
        "workbench_view": WORKBENCH_ROLE_VIEWS["采购员"],
    },
    {
        "employee_code": "EMP-WAREHOUSE-TEST",
        "employee_name": "仓管测试员",
        "position": "仓管",
        "role_code": "ROLE-WAREHOUSE-TEST",
        "department_code": "DEPT-UP",
        "user_email": "warehouse.test@stec-up.local",
        "profile": "warehouse_agent",
        "default_project_code": "PRJ-HL-13",
        "default_warehouse_code": "WH-HL-13",
        "workbench_view": WORKBENCH_ROLE_VIEWS["仓管员"],
    },
)


def business_employee_catalog() -> list[dict[str, Any]]:
    """Return local catalog identities plus the two sandbox-only operators."""

    rows = employee_catalog()
    known = {row["user_email"] for row in rows}
    rows.extend(row for row in BUSINESS_SANDBOX_EMPLOYEES if row["user_email"] not in known)
    return rows


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
        "confirmation": result.get("confirmation")
        or ((result.get("pending_tool_call") or {}).get("summary")
            if isinstance(result.get("pending_tool_call"), dict) else None),
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


def document_approval_stages(doctype: str, document: dict[str, Any]) -> list[dict[str, Any]]:
    """Describe the visible approval path without creating a second business state.

    The active position always comes from the ERPNext ``workflow_state`` and
    ``docstatus`` fields returned with the document.  Stage labels are only a
    presentation aid for the material-request workflow provisioned in the
    isolated business portal sandbox.
    """

    workflow_state = str(document.get("workflow_state") or "").strip()
    if doctype != "Material Request" or not workflow_state:
        return []
    configured = (
        ("Nexterp材料草稿", "申请提交", "材料员"),
        ("Nexterp主管审批", "材料设备主管审批", "材料设备主管"),
        ("Nexterp项目审批", "项目经理审批", "项目经理"),
        ("Nexterp已批准", "审批完成", "系统"),
    )
    state_names = [row[0] for row in configured]
    try:
        current_index = state_names.index(workflow_state)
    except ValueError:
        return [{
            "state": workflow_state,
            "label": workflow_state,
            "role": "ERPNext 工作流",
            "status": "current",
            "status_label": "当前节点",
            "is_current": True,
        }]
    docstatus = int(document.get("docstatus") or 0)
    completed = docstatus == 1 or workflow_state == "Nexterp已批准"
    cancelled = docstatus == 2
    stages: list[dict[str, Any]] = []
    for index, (state, label, role) in enumerate(configured):
        if cancelled:
            status = "cancelled" if index == current_index else "pending"
            status_label = "已取消" if index == current_index else "未执行"
        elif completed or index < current_index:
            status = "completed"
            status_label = "已完成"
        elif index == current_index:
            status = "current"
            status_label = "当前节点"
        else:
            status = "pending"
            status_label = "待处理"
        stages.append({
            "state": state,
            "label": label,
            "role": role,
            "status": status,
            "status_label": status_label,
            "is_current": index == current_index and not completed and not cancelled,
        })
    return stages


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


def _material_publish_fingerprint(
    analysis_id: str,
    draft_ids: list[str],
    draft_hashes: dict[str, str],
) -> str:
    payload = {
        "analysis_id": analysis_id,
        "draft_ids": sorted(draft_ids),
        "draft_hashes": {key: draft_hashes[key] for key in sorted(draft_hashes)},
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validate_material_dependencies(client: Any, item_group: str, stock_uom: str) -> str:
    for doctype, name, label in (
        ("Item Group", item_group, "物料组"),
        ("UOM", stock_uom, "库存单位"),
    ):
        result = client.document_exists(doctype, name)
        if not result.ok:
            return result.user_message or f"无法验证 ERPNext {label} {name}"
        data = result.data or {}
        exists = data.get("exists") if isinstance(data, dict) else bool(data)
        if not exists:
            return f"ERPNext 中不存在{label}“{name}”，本条未写入。"
    return ""


def _verify_item_readback(expected: dict[str, Any], result: Any) -> dict[str, Any]:
    if not result.ok or not isinstance(result.data, dict):
        return {
            "verified": False,
            "document": result.data if isinstance(result.data, dict) else {},
            "mismatches": {},
            "error_type": result.error_type or "readback_failed",
            "user_message": result.user_message or result.error or "无法从 ERPNext 回读 Item",
        }
    document = dict(result.data)
    fields = (
        "item_code",
        "item_name",
        "item_group",
        "stock_uom",
        "disabled",
        "is_stock_item",
        "is_purchase_item",
        "is_sales_item",
        "include_item_in_manufacturing",
    )
    flag_fields = {
        "disabled",
        "is_stock_item",
        "is_purchase_item",
        "is_sales_item",
        "include_item_in_manufacturing",
    }
    mismatches: dict[str, dict[str, Any]] = {}
    for field in fields:
        expected_value = expected.get(field)
        actual_value = document.get(field)
        if field in flag_fields:
            try:
                expected_value = int(expected_value or 0)
                actual_value = int(actual_value or 0)
            except (TypeError, ValueError):
                pass
        else:
            expected_value = str(expected_value or "").strip()
            actual_value = str(actual_value or "").strip()
        if expected_value != actual_value:
            mismatches[field] = {"expected": expected_value, "actual": actual_value}
    return {
        "verified": not mismatches,
        "document": document,
        "mismatches": mismatches,
        "error_type": "" if not mismatches else "readback_mismatch",
        "user_message": "ERPNext 回读字段与冻结草稿一致。" if not mismatches else "ERPNext 回读字段与冻结草稿不一致。",
    }


SOURCE_LINK_FIELDS: dict[str, tuple[str, str]] = {
    "material_request": ("Material Request", "材料申请"),
    "request_for_quotation": ("Request for Quotation", "询价单"),
    "supplier_quotation": ("Supplier Quotation", "供应商报价"),
    "purchase_order": ("Purchase Order", "采购订单"),
    "purchase_receipt": ("Purchase Receipt", "采购收货"),
    "stock_entry": ("Stock Entry", "库存移动"),
}


def document_quantity_summary(document: dict[str, Any]) -> dict[str, Any]:
    """Return a small, read-only quantity summary for detail drawers."""

    items = [row for row in document.get("items") or [] if isinstance(row, dict)]
    ordered = sum(_number(row.get("qty")) for row in items)
    received = sum(_number(row.get("received_qty")) for row in items)
    returned = sum(_number(row.get("returned_qty")) for row in items)
    remaining = max(0.0, ordered - received + returned)
    return {
        "line_count": len(items),
        "ordered_qty": ordered,
        "received_qty": received,
        "returned_qty": returned,
        "remaining_qty": remaining,
        "uoms": sorted({str(row.get("uom") or row.get("stock_uom") or "") for row in items if row.get("uom") or row.get("stock_uom")}),
    }


def document_source_links(document: dict[str, Any]) -> list[dict[str, str]]:
    """Extract explicit ERPNext predecessor references without inventing links."""

    links: dict[tuple[str, str], dict[str, str]] = {}
    rows = [document, *(row for row in document.get("items") or [] if isinstance(row, dict))]
    for row in rows:
        for fieldname, (doctype, label) in SOURCE_LINK_FIELDS.items():
            name = str(row.get(fieldname) or "").strip()
            if not name:
                continue
            links[(doctype, name)] = {"doctype": doctype, "name": name, "label": label, "field": fieldname}
        # ERPNext versions sometimes expose the predecessor through prevdoc_docname.
        prev_name = str(row.get("prevdoc_docname") or "").strip()
        prev_type = str(row.get("prevdoc_doctype") or "").strip()
        if prev_name and prev_type in ALLOWED_DOCUMENT_TYPES:
            links[(prev_type, prev_name)] = {
                "doctype": prev_type,
                "name": prev_name,
                "label": prev_type,
                "field": "prevdoc_docname",
            }
    return sorted(links.values(), key=lambda link: (link["doctype"], link["name"]))


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


def infer_intent_mode(text: str) -> str:
    """Conservatively classify effect level; capability selection remains model-driven."""
    normalized = str(text or "").strip()
    write_markers = (
        "创建", "新建", "新增", "申请", "帮我买", "帮我采购", "采购一批", "下单", "提交", "批准", "驳回",
        "收货", "退货", "调拨", "领料", "付款", "修改", "删除", "录入", "生成", "转成",
    )
    analyze_markers = ("分析", "比较", "汇总", "异常", "建议", "风险", "趋势", "延期")
    if any(marker in normalized for marker in write_markers):
        return "write"
    if any(marker in normalized for marker in analyze_markers):
        return "analyze"
    return "read"


class AgentWorkbenchService:
    def __init__(self, profile: str = "civil") -> None:
        self.profile = profile
        prefix = f"NEXTERP_{profile.upper()}_"
        if profile == "material_test":
            self.base_url = os.getenv(prefix + "BASE_URL", "http://127.0.0.1:8003")
            self.host_header = os.getenv(prefix + "HOST_HEADER", "material-test.localhost")
        else:
            self.base_url = os.environ[prefix + "BASE_URL"]
            self.host_header = os.getenv(prefix + "HOST_HEADER")
        self.session_store = RuntimeSessionStore()
        self._project_name_cache: dict[tuple[str, str], str] = {}
        self._material_catalog_sync_cache: dict[str, dict[str, Any]] = {}
        self.openclaw_preview = OpenClawPreviewRunner(ROOT)
        self.openclaw_runtime = OpenClawWorkbenchRunner(ROOT)
        self.capability_repository = CapabilityCatalogRepository(os.environ["MATERIAL_CATALOG_DATABASE_URL"])
        # Analysis merges the immutable release with ERPNext-verified runtime
        # publications. It still never writes ERPNext by itself.
        self.material_publications = RuntimeMaterialPublicationStore()
        classifier = MaterialTypeClassifier(runtime_publications=self.material_publications.active())
        self.material_intake = HighRecallBatchMaterialIntakeAnalyzer(classifier)
        self._run_lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._material_intake_runs: dict[str, dict[str, Any]] = {}
        self._material_draft_batches: dict[str, MaterialDraftBatch] = {}
        self.tariff_extraction = TariffExtractionJobManager(ROOT / ".runtime" / "tariff-extraction")
        self.tariff_declaration = TariffDeclarationJobManager(TARIFF_DECLARATION_RUNTIME_ROOT)
        self.procurement_batch_pilot = ProcurementBatchPilotJobManager(PROCUREMENT_BATCH_PILOT_RUNTIME_ROOT)
        self.business_commands = BusinessCommandStore()

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
            if self.profile == "material_test":
                account = self._business_account_for_code("material_test")
                credentials_path = Path(self._business_account_value(account, "credentials_path"))
                base_url = self._business_account_value(account, "base_url")
                host_header = self._business_account_value(account, "host_header")
            else:
                credentials_path = Path(os.getenv(f"NEXTERP_{self.profile.upper()}_CREDENTIALS_PATH", str(DEFAULT_CREDENTIALS_PATH)))
                base_url = self.base_url
                host_header = self.host_header
            credentials = load_user_credentials(user, credentials_path)
            return ERPNextClient(
                base_url,
                credentials["api_key"],
                credentials["api_secret"],
                host_header=host_header,
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

    def analyze_material_intake(self, payload: dict[str, Any]) -> dict[str, Any]:
        source_rows = payload.get("rows")
        if not isinstance(source_rows, list):
            raise ValueError("rows 必须是采购清单数组")
        rows = [MaterialIntakeRow.model_validate(row) for row in source_rows]
        result = self.material_intake.analyze(rows)
        analysis_id = uuid4().hex
        with self._run_lock:
            self._material_intake_runs[analysis_id] = {
                "result": result,
                "created_at": time.time(),
            }
        return {"analysis_id": analysis_id, **result.model_dump(mode="json")}

    def procurement_batch_pilot_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Start a local GPC candidate run; this boundary never writes ERPNext."""

        return self.procurement_batch_pilot.start(
            limit=int(payload.get("limit") or 100),
            use_deepseek=bool(payload.get("use_deepseek", True)),
        )

    def procurement_batch_pilot_status(self, job_id: str) -> dict[str, Any]:
        return self.procurement_batch_pilot.status(job_id)

    def procurement_batch_pilot_result(self, job_id: str) -> dict[str, Any]:
        return self.procurement_batch_pilot.result(job_id)

    def procurement_batch_pilot_latest(self) -> dict[str, Any]:
        return self.procurement_batch_pilot.latest()

    def procurement_batch_pilot_cancel(self, job_id: str) -> dict[str, Any]:
        return self.procurement_batch_pilot.cancel(job_id)

    def _procurement_batch_review_store(self) -> ProcurementBatchReviewStore:
        index = self._gpc_reference_index()
        cached = getattr(self, "_procurement_review_cache", None)
        signature = tuple(index.codes(kind="brick"))
        if cached is None or cached[0] != signature:
            cached = (
                signature,
                ProcurementBatchReviewStore(
                    PROCUREMENT_BATCH_PILOT_RUNTIME_ROOT,
                    allowed_gpc_codes=signature,
                    max_source_row=101,
                ),
            )
            self._procurement_review_cache = cached
        return cached[1]

    def procurement_batch_review_status(self, job_id: str) -> dict[str, Any]:
        return self._procurement_batch_review_store().status(job_id)

    def procurement_batch_review_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "").strip()
        return self._procurement_batch_review_store().save(job_id, payload)

    def procurement_batch_review_freeze(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = str(payload.get("job_id") or "").strip()
        return self._procurement_batch_review_store().freeze(job_id)

    def prepare_material_intake_drafts(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Compile the latest analysis into server-owned, non-executable drafts."""
        analysis_id = str(payload.get("analysis_id") or "").strip()
        if not analysis_id:
            raise ValueError("analysis_id 必填，请先完成采购清单分析")
        with self._run_lock:
            run = self._material_intake_runs.get(analysis_id)
        if not run:
            raise ValueError("分析结果已过期，请重新分析采购清单")

        existing_codes: list[str] = []
        lookup_status = "release_catalog_only"
        user = str(payload.get("user") or "").strip()
        if user:
            try:
                existing = self.client(user).search_documents(
                    "Item",
                    fields=["item_code"],
                    limit=5000,
                    order_by="item_code asc",
                )
                if existing.ok and isinstance(existing.data, list):
                    existing_codes = [
                        str(row.get("item_code") or "")
                        for row in existing.data
                        if isinstance(row, dict) and row.get("item_code")
                    ]
                    lookup_status = "erpnext_checked"
                else:
                    lookup_status = "erpnext_unavailable"
            except Exception:
                lookup_status = "erpnext_unavailable"

        batch = build_material_drafts(
            analysis_id,
            run["result"],
            self.material_intake.retriever.classifier,
            existing_item_codes=existing_codes,
        )
        batch.processing_step["details"].append(f"编码检查：{lookup_status}。")
        with self._run_lock:
            self._material_draft_batches[analysis_id] = batch
        return batch.model_dump(mode="json")

    def revise_material_intake_drafts(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Recompile narrow user edits without writing ERPNext."""

        analysis_id = str(payload.get("analysis_id") or "").strip()
        user = str(payload.get("user") or "").strip()
        updates = payload.get("draft_updates") or []
        if not analysis_id or not user:
            raise ValueError("analysis_id 和 user 必填")
        if not isinstance(updates, list) or not updates:
            raise ValueError("draft_updates 必须是非空数组")
        with self._run_lock:
            batch = self._material_draft_batches.get(analysis_id)
        if batch is None:
            raise ValueError("物料录入草稿不存在或已过期，请重新生成")

        client = self.client(user)
        existing = client.search_documents(
            "Item",
            fields=["item_code"],
            limit=5000,
            order_by="item_code asc",
        )
        if not existing.ok:
            raise ValueError(existing.user_message or "无法读取 ERPNext 现有物料编码，不能重新冻结草稿")
        live_codes = [
            str(row.get("item_code") or "")
            for row in (existing.data or [])
            if isinstance(row, dict) and row.get("item_code")
        ]
        reserved_codes = {draft.item_code for draft in batch.drafts}
        revised = revise_material_drafts(
            batch,
            updates,
            self.material_intake.retriever.classifier,
            existing_item_codes=[code for code in live_codes if code not in reserved_codes],
        )
        with self._run_lock:
            self._material_draft_batches[analysis_id] = revised
        return revised.model_dump(mode="json")

    def confirm_material_intake_drafts(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Publish confirmed drafts with identity, idempotency and readback."""
        analysis_id = str(payload.get("analysis_id") or "").strip()
        user = str(payload.get("user") or "").strip()
        request_id = str(payload.get("request_id") or "").strip()
        conversation_id = str(payload.get("conversation_id") or "material-intake").strip()
        if not analysis_id or not user or not request_id:
            raise ValueError("analysis_id、user 和 request_id 必填")
        requested_ids = sorted({
            str(value).strip()
            for value in (payload.get("draft_ids") or [])
            if str(value).strip()
        })
        if not requested_ids:
            raise ValueError("draft_ids 必须包含至少一个待确认草稿")
        if payload.get("draft_updates"):
            raise ValueError("发布请求不能同时修改草稿；请先调用草稿修订接口并确认重新冻结后的内容")
        raw_hashes = payload.get("draft_hashes") or []
        if not isinstance(raw_hashes, list):
            raise ValueError("draft_hashes 必须是数组")
        draft_hashes = {
            str(row.get("draft_id") or "").strip(): str(row.get("frozen_hash") or "").strip()
            for row in raw_hashes
            if isinstance(row, dict) and row.get("draft_id")
        }

        if set(requested_ids) != set(draft_hashes):
            raise ValueError("每个确认草稿都必须提交对应的 frozen_hash")
        fingerprint = _material_publish_fingerprint(analysis_id, requested_ids, draft_hashes)
        cached, request_context = self._idempotency_context(user, "", conversation_id, request_id)
        if cached is not None:
            if cached.get("request_fingerprint") != fingerprint:
                raise ValueError("request_id 已用于另一份物料草稿，不能改写后重复使用")
            return {**cached, "idempotent_replay": True}

        with self._run_lock:
            batch = self._material_draft_batches.get(analysis_id)
        if batch is None:
            raise ValueError("物料录入草稿不存在或已过期，请重新生成")

        known_ids = {draft.draft_id for draft in batch.drafts}
        if set(requested_ids) - known_ids:
            raise ValueError("确认请求包含不存在的物料草稿")
        revised = batch.model_copy(deep=True)
        drafts = [draft for draft in revised.drafts if not requested_ids or draft.draft_id in requested_ids]
        stale = [draft.draft_id for draft in drafts if draft_hashes.get(draft.draft_id) != draft.frozen_hash]
        if stale:
            raise ValueError("草稿已变化或冻结摘要不一致，请重新查看后确认：" + "、".join(stale))
        if not drafts:
            result = {
                "status": "completed",
                "analysis_id": analysis_id,
                "request_id": request_id,
                "request_fingerprint": fingerprint,
                "created": [],
                "verified_existing": [],
                "skipped": [],
                "failed": [],
                "writes_erpnext": False,
                "readback_verified": True,
            }
            self._remember_idempotent_result(request_context, request_id, result)
            return result
        invalid = [
            {"draft_id": draft.draft_id, "errors": draft.validation_errors}
            for draft in drafts
            if draft.validation_errors
        ]
        if invalid:
            raise ValueError("草稿仍需修改后才能发布：" + json.dumps(invalid, ensure_ascii=False))

        client = self.client(user)
        logged_user = client.get_logged_user()
        if not logged_user.ok:
            raise PermissionError(logged_user.user_message or "无法核对 ERPNext 登录身份")
        actual_user = logged_user.data
        if isinstance(actual_user, dict):
            actual_user = actual_user.get("message") or actual_user.get("user") or actual_user.get("name")
        if str(actual_user or "").strip() != user:
            raise PermissionError("ERPNext 登录身份与确认员工不一致")

        gateway = ToolGateway(
            ERPNextAdapter(client),
            ToolSession(
                user=user,
                policy=make_tool_access_policy(str(payload.get("profile") or "procurement")),
                verify_erpnext_identity=True,
            ),
        )
        created: list[dict[str, Any]] = []
        verified_existing: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []
        wrote_item = False
        for draft in drafts:
            exists = client.document_exists("Item", draft.item_code)
            if not exists.ok:
                draft.status = "failed"
                failed.append({
                    "draft_id": draft.draft_id,
                    "item_code": draft.item_code,
                    "error_type": exists.error_type,
                    "error": exists.error,
                    "user_message": exists.user_message or "无法确认物料编码是否已存在，为避免重复录入，本条未执行。",
                })
                continue
            if bool((exists.data or {}).get("exists")):
                readback = client.get_document("Item", draft.item_code)
                verification = _verify_item_readback(draft.item_doc, readback)
                if not verification["verified"]:
                    draft.status = "readback_failed"
                    failed.append({
                        "draft_id": draft.draft_id,
                        "item_code": draft.item_code,
                        "error_type": "item_code_conflict",
                        "user_message": "ERPNext 已存在同编码物料，但字段与确认草稿不一致。",
                        "readback": verification,
                        "write_succeeded": False,
                    })
                    continue
                publication_error = self._record_material_publication(
                    draft,
                    request_id=request_id,
                    analysis_id=analysis_id,
                    user=user,
                    readback=verification["document"],
                )
                if publication_error:
                    failed.append(publication_error)
                    continue
                draft.status = "verified_existing"
                verified_existing.append({
                    "draft_id": draft.draft_id,
                    "item_code": draft.item_code,
                    "item_name": draft.item_name,
                    "type_id": draft.type_id,
                    "readback": verification,
                    "reason": "ERPNext 已存在且回读字段与确认草稿一致，未重复创建。",
                })
                continue
            dependency_error = _validate_material_dependencies(client, draft.item_group, draft.stock_uom)
            if dependency_error:
                draft.status = "failed"
                failed.append({
                    "draft_id": draft.draft_id,
                    "item_code": draft.item_code,
                    "error_type": "missing_master_data",
                    "user_message": dependency_error,
                    "write_succeeded": False,
                })
                continue
            call = {
                "tool": "erpnext.stock.create_item",
                "reason": "用户确认物料录入草稿",
                "risk_level": "L3",
                "user_context": {
                    "confirmed_by": user,
                    "source": "material_intake_lab",
                    "analysis_id": analysis_id,
                    "request_id": request_id,
                    "draft_id": draft.draft_id,
                    "frozen_hash": draft.frozen_hash,
                },
                "arguments": dict(draft.item_doc),
            }
            result = gateway.execute(call, origin="agent")
            if result.ok:
                wrote_item = True
                readback = client.get_document("Item", draft.item_code)
                verification = _verify_item_readback(draft.item_doc, readback)
                if not verification["verified"]:
                    draft.status = "readback_failed"
                    failed.append({
                        "draft_id": draft.draft_id,
                        "item_code": draft.item_code,
                        "error_type": "readback_mismatch",
                        "user_message": "Item 已写入 ERPNext，但独立回读验证未通过。",
                        "readback": verification,
                        "write_succeeded": True,
                    })
                    continue
                publication_error = self._record_material_publication(
                    draft,
                    request_id=request_id,
                    analysis_id=analysis_id,
                    user=user,
                    readback=verification["document"],
                    write_succeeded=True,
                )
                if publication_error:
                    failed.append(publication_error)
                    continue
                draft.status = "created"
                created.append({
                    "draft_id": draft.draft_id,
                    "item_code": draft.item_code,
                    "item_name": draft.item_name,
                    "type_id": draft.type_id,
                    "action": draft.action,
                    "readback": verification,
                    "result": result.to_dict(),
                })
            else:
                draft.status = "failed"
                failed.append({
                    "draft_id": draft.draft_id,
                    "item_code": draft.item_code,
                    "error_type": result.error_type,
                    "error": result.error,
                    "user_message": result.user_message,
                    "write_succeeded": False,
                })

        response = {
            "status": "partial" if failed else "completed",
            "analysis_id": analysis_id,
            "request_id": request_id,
            "request_fingerprint": fingerprint,
            "created": created,
            "verified_existing": verified_existing,
            "skipped": skipped,
            "failed": failed,
            "writes_erpnext": wrote_item,
            "readback_verified": not failed and all(
                row.get("readback", {}).get("verified")
                for row in [*created, *verified_existing]
            ),
            "idempotent_replay": False,
        }
        with self._run_lock:
            self._material_draft_batches[analysis_id] = revised
        self._remember_idempotent_result(request_context, request_id, response)
        return response

    @staticmethod
    def _classification_source(value: str = "") -> str:
        normalized = str(value or "").strip().lower()
        allowed = {row["code"] for row in CLASSIFICATION_SOURCES}
        return normalized if normalized in allowed else "original"

    @staticmethod
    def _business_account_catalog() -> tuple[dict[str, str], ...]:
        return BUSINESS_ACCOUNTS

    @classmethod
    def _business_account_for_code(cls, value: str = "") -> dict[str, str]:
        normalized = str(value or "").strip().lower()
        for account in cls._business_account_catalog():
            if account["code"] == normalized:
                return account
        # The service is still used by the civil/developer workbench.  Its
        # legacy profile remains the safe fallback when no portal account was
        # selected in the current request.
        return next(account for account in cls._business_account_catalog() if account["code"] == "material_test")

    @classmethod
    def _business_account_for_source(cls, source: str = "original") -> dict[str, str]:
        selected = cls._classification_source(source)
        return next(
            account for account in cls._business_account_catalog()
            if account["classification_source"] == selected
        )

    @classmethod
    def _business_account_value(cls, account: Mapping[str, str], key: str) -> str:
        env_name = str(account.get(f"{key}_env") or "")
        default = str(account.get(f"{key}_default") or "")
        return str(os.getenv(env_name, default) or default).strip()

    @classmethod
    def _business_account_summary(cls, account: Mapping[str, str]) -> dict[str, Any]:
        credentials_path = Path(cls._business_account_value(account, "credentials_path"))
        return {
            "code": account["code"],
            "label": account["label"],
            "site": account["site"],
            "classification_source": account["classification_source"],
            "available": credentials_path.is_file(),
            "write_enabled": credentials_path.is_file(),
        }

    def _resolve_business_account(self, cookie_header: str = "", *, source: str = "") -> dict[str, str]:
        cookie = SimpleCookie()
        if cookie_header:
            cookie.load(cookie_header)
        requested_account = unquote(cookie.get("nexterp_business_account").value) if cookie.get("nexterp_business_account") else ""
        if requested_account:
            normalized = requested_account.strip().lower()
            if normalized not in {row["code"] for row in self._business_account_catalog()}:
                requested_account = ""
        selected_source = self._classification_source(source or (
            unquote(cookie.get("nexterp_classification_source").value)
            if cookie.get("nexterp_classification_source") else "original"
        ))
        account = self._business_account_for_code(requested_account) if requested_account else self._business_account_for_source(selected_source)
        # A source and account are a single invariant.  Never let a stale
        # source cookie route a write to the other Site.
        if source and account["classification_source"] != selected_source:
            account = self._business_account_for_source(selected_source)
        _BUSINESS_ACCOUNT_CONTEXT.set(account["code"])
        return account

    @staticmethod
    def _classification_source_info(source: str) -> dict[str, str]:
        selected = AgentWorkbenchService._classification_source(source)
        return next(row for row in CLASSIFICATION_SOURCES if row["code"] == selected)

    def _chatgpt_classification_snapshot(self) -> dict[str, Any]:
        path = CHATGPT_CLASSIFICATION_DATA_PATH
        if not path.is_file():
            raise FileNotFoundError("ChatGPT 分类数据尚未生成")
        signature = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        # Keep the raw snapshot cache separate from the hierarchy-index cache.
        # Both are keyed by the same file signature, but their values have
        # different contracts: callers here need a mapping and the index
        # loader returns a ChatgptClassificationIndex object.
        cached = getattr(self, "_chatgpt_snapshot_cache", None)
        if cached is not None and cached[0] == signature:
            return cached[1]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("rows"), list):
            raise ValueError("ChatGPT 分类数据格式无效")
        self._chatgpt_snapshot_cache = (signature, payload)
        return payload

    def classification_source_summary(self, source: str = "original") -> dict[str, Any]:
        selected = self._classification_source(source)
        info = self._classification_source_info(selected)
        if selected == "chatgpt_v4":
            try:
                payload = self._chatgpt_classification_snapshot()
            except (FileNotFoundError, ValueError):
                return {
                    **info,
                    "available": False,
                    "sku_count": 0,
                    "family_count": 0,
                    "top_group_count": 0,
                    "source_version": "chatgpt-v4",
                    "read_only": True,
                    "business_test_enabled": False,
                    "note": "ChatGPT 分类数据包尚未生成，当前不可用。",
                }
            summary = dict(payload.get("summary") or {})
            return {
                **info,
                "available": True,
                "sku_count": int(summary.get("sku_count") or 0),
                "family_count": int(summary.get("material_family_count") or summary.get("item_name_count") or 0),
                "top_group_count": int(summary.get("top_group_count") or 0),
                "source_version": str(payload.get("release_hash") or "chatgpt-v4"),
                "read_only": True,
                "business_test_enabled": True,
                "note": "ChatGPT 分类使用独立 V4 测试账套，可用于业务流程测试。",
            }
        return {
            **info,
            "available": True,
            "sku_count": 259,
            "family_count": 138,
            "top_group_count": 14,
            "source_version": GPC_REFERENCE_VERSION,
            "read_only": False,
            "note": "原分类（GPC）为当前物料采购目录，可用于申请。",
        }

    def business_context(self, cookie_header: str = "") -> dict[str, Any]:
        """Resolve the local business portal identity without trusting form data.

        Production deployments should provide an authenticated session.  The
        local sandbox has an explicitly scoped developer switcher so the five
        workflow roles can be exercised without putting identity fields in
        business write requests.
        """
        cookie = SimpleCookie()
        if cookie_header:
            cookie.load(cookie_header)
        default_user = os.getenv("NEXTERP_BUSINESS_DEFAULT_USER", "mao.xiaoquan@stec-up.local")
        default_project = os.getenv("NEXTERP_BUSINESS_DEFAULT_PROJECT", "PRJ-HL-13")
        user = unquote(cookie.get("nexterp_business_user").value) if cookie.get("nexterp_business_user") else default_user
        project_code = unquote(cookie.get("nexterp_business_project").value) if cookie.get("nexterp_business_project") else default_project
        account = self._resolve_business_account(cookie_header)
        classification_source = account["classification_source"]
        employees = business_employee_catalog()
        projects = project_catalog()
        employee = next((row for row in employees if row.get("user_email") == user), None)
        project = next((row for row in projects if row.get("project_code") == project_code), None)
        if employee is None:
            employee = next((row for row in employees if row.get("user_email") == default_user), None) or (employees[0] if employees else {})
            user = str(employee.get("user_email") or "")
        if project is None:
            project = next((row for row in projects if row.get("project_code") == default_project), None) or (projects[0] if projects else {})
            project_code = str(project.get("project_code") or "")
        project_people = {row.get("user_email") for row in project.get("employees") or []}
        if user not in project_people and project_people:
            # Organization-level supervisors can act on the project; a local
            # dev context may still select them explicitly.
            if employee.get("position") not in {"材料设备主管", "总经理", "经营主管", "财务人员", "采购", "仓管"}:
                employee = next((row for row in project.get("employees") or [] if row.get("user_email") in project_people), employee)
                user = str(employee.get("user_email") or user)
        dev_switcher = os.getenv("NEXTERP_BUSINESS_DEV_CONTEXT", "1").lower() not in {"0", "false", "no"}
        return {
            "user": user,
            "employee": {key: employee.get(key) for key in ("employee_code", "employee_name", "position", "role_code", "user_email", "profile")},
            "project": project,
            "project_code": project_code,
            "classification_source": classification_source,
            "classification": self.classification_source_summary(classification_source),
            "account": self._business_account_summary(account),
            "developer_identity_switcher": dev_switcher,
        }

    def business_classification_update(self, payload: dict[str, Any]) -> dict[str, str]:
        """Switch the classification view and its paired isolated ERPNext Site."""

        source = self._classification_source(str(payload.get("classification_source") or ""))
        if str(payload.get("classification_source") or "").strip().lower() not in {row["code"] for row in CLASSIFICATION_SOURCES}:
            raise ValueError("未知分类版本")
        # Force-load the selected snapshot before changing the browser context so
        # a missing or malformed ChatGPT release cannot leave a half-switched UI.
        summary = self.classification_source_summary(source)
        if summary.get("available") is False:
            raise ValueError(str(summary.get("note") or "分类版本不可用"))
        account = self._business_account_for_source(source)
        if source == "chatgpt_v4" and not Path(self._business_account_value(account, "credentials_path")).is_file():
            raise ValueError("ChatGPT 分类测试账套尚未配置测试身份，请先初始化该账套")
        return {"classification_source": source, "account_code": account["code"]}

    def business_context_update(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Set a local-only sandbox context; production identity stays session-owned."""

        if os.getenv("NEXTERP_BUSINESS_DEV_CONTEXT", "1").lower() in {"0", "false", "no"}:
            raise PermissionError("开发身份切换器已关闭")
        user = str(payload.get("user") or "").strip()
        project = str(payload.get("project_code") or "").strip()
        if not any(row.get("user_email") == user for row in business_employee_catalog()):
            raise ValueError("未知员工账号")
        projects = project_catalog()
        if not any(row.get("project_code") == project for row in self._authorized_business_projects(user, projects)):
            raise ValueError("未知项目")
        return {"user": user, "project_code": project}

    @staticmethod
    def _authorized_business_projects(
        user: str,
        projects: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """Return projects the selected sandbox identity may actually use.

        The developer switcher is only a test convenience; it must not turn the
        project selector into an unrestricted cross-project picker.  Organization
        supervisors retain their organization-wide scope, while test operators
        without a release assignment are limited to their declared default.
        """

        rows = list(projects or project_catalog())
        employee = next((row for row in business_employee_catalog() if row.get("user_email") == user), {})
        position = str(employee.get("position") or "")
        if position in {"材料设备主管", "总经理", "经营主管", "财务人员"}:
            return rows
        assigned = [
            project for project in rows
            if any(person.get("user_email") == user for person in project.get("employees") or [])
        ]
        if assigned:
            return assigned
        default_code = str(employee.get("default_project_code") or "")
        return [project for project in rows if project.get("project_code") == default_code]

    def business_bootstrap(self, cookie_header: str = "") -> dict[str, Any]:
        context = self.business_context(cookie_header)
        visible_projects = self._authorized_business_projects(str(context.get("user") or ""))
        return {
            "profile": self.profile,
            "context": context,
            "business_accounts": [self._business_account_summary(row) for row in self._business_account_catalog()],
            "classification_sources": [self.classification_source_summary(row["code"]) for row in CLASSIFICATION_SOURCES],
            "projects": visible_projects,
            "employees": business_employee_catalog(),
            "modules": [
                {"code": "catalog", "label": "物料目录", "href": "/material-marketplace", "roles": ["all"]},
                {"code": "requests", "label": "我的申请", "doctype": "Material Request", "roles": ["all"]},
                {"code": "approvals", "label": "审批中心", "roles": ["材料设备主管", "项目经理", "总经理"]},
                {"code": "buying", "label": "采购中心", "roles": ["材料设备主管", "采购"]},
                {"code": "receiving", "label": "收货中心", "roles": ["仓管", "材料设备主管", "采购"]},
                {"code": "inventory", "label": "库存中心", "roles": ["仓管", "材料设备主管", "项目经理"]},
                {"code": "project", "label": "项目用料", "roles": ["项目经理", "材料员", "材料设备主管"]},
                {"code": "documents", "label": "单据中心", "roles": ["all"]},
            ],
            "features": {"ai": False, "erpnext_authority": True, "developer_identity_switcher": context["developer_identity_switcher"]},
        }

    def business_dashboard(self, cookie_header: str = "") -> dict[str, Any]:
        context = self.business_context(cookie_header)
        user = str(context["user"])
        project = str(context["project_code"])
        result: dict[str, Any] = {"context": context, "sections": {}, "metrics": {}}
        loaders = {
            "approvals": lambda: self.inbox(user, project),
            "pending_procurement": lambda: self.pending_procurement(user, project, scope="project", limit=50),
            "receiving": lambda: self.pending_receiving(user, project, limit=50),
            "documents": lambda: self.documents(user, project, module="buying", page=1, page_size=10, status_scope="active"),
        }
        for key, loader in loaders.items():
            try:
                result["sections"][key] = loader()
            except Exception as exc:  # a dashboard card must not hide the rest of the portal
                result["sections"][key] = {"error": str(exc), "items": [], "rows": [], "modules": []}
        approvals = result["sections"].get("approvals") or {}
        pending = result["sections"].get("pending_procurement") or {}
        receiving = result["sections"].get("receiving") or {}
        result["metrics"] = {
            "approvals": int(approvals.get("count") or 0),
            "pending_procurement": len(pending.get("rows") or []),
            "receiving": len(receiving.get("rows") or []),
            # The selected classification owns this count; business documents still
            # come from ERPNext and are never mixed into the classification metric.
            "catalog": int((context.get("classification") or {}).get("sku_count") or 0),
            "catalog_source": context.get("classification_source") or "original",
            "catalog_label": (context.get("classification") or {}).get("label") or "原分类（GPC）",
            "catalog_note": (context.get("classification") or {}).get("note") or "",
        }
        return result

    def business_documents(self, cookie_header: str = "", **filters: Any) -> dict[str, Any]:
        context = self.business_context(cookie_header)
        return self.documents(
            str(context["user"]),
            str(filters.get("project") or context["project_code"]),
            module=str(filters.get("module") or "buying"),
            status=str(filters.get("status") or ""),
            page=int(filters.get("page") or 1),
            page_size=int(filters.get("page_size") or 20),
            mine_only=bool(filters.get("mine_only")),
            query=str(filters.get("query") or ""),
            doctype=str(filters.get("doctype") or ""),
            status_scope=str(filters.get("status_scope") or "active"),
            date_from=str(filters.get("date_from") or ""),
            date_to=str(filters.get("date_to") or ""),
        )

    def business_document(self, cookie_header: str, doctype: str, name: str) -> dict[str, Any]:
        context = self.business_context(cookie_header)
        return self.document(str(context["user"]), doctype, name)

    def business_inventory(self, cookie_header: str = "", *, item_code: str = "", warehouse: str = "", project: str = "", limit: int = 100) -> dict[str, Any]:
        context = self.business_context(cookie_header)
        selected_project = str(project or context.get("project_code") or "").strip()
        if selected_project and selected_project != str(context.get("project_code") or ""):
            raise PermissionError("库存项目必须使用当前已授权项目上下文")
        client = self.client(str(context["user"]))
        balance = client.get_stock_balance(item_code or None, warehouse=warehouse or None, limit=min(200, max(1, int(limit))))
        ledger = client.get_stock_ledger_entries(item_code=item_code or None, warehouse=warehouse or None, limit=30)
        balances = []
        for row in balance.data if balance.ok and isinstance(balance.data, list) else []:
            if not isinstance(row, dict):
                continue
            enriched = dict(row)
            enriched["available_qty"] = _number(row.get("actual_qty")) - _number(row.get("reserved_qty"))
            balances.append(enriched)
        return {
            "context": context,
            "item_code": item_code,
            "warehouse": warehouse,
            "project": selected_project,
            "balances": balances,
            "ledger": ledger.data if ledger.ok and isinstance(ledger.data, list) else [],
            "errors": [value for value in (balance.error if not balance.ok else "", ledger.error if not ledger.ok else "") if value],
        }

    def business_project_materials(self, cookie_header: str = "") -> dict[str, Any]:
        context = self.business_context(cookie_header)
        project = str(context["project_code"])
        pending = self.pending_procurement(str(context["user"]), project, scope="project", limit=500)
        documents = self.documents(str(context["user"]), project, module="stock", page=1, page_size=50)
        buying = self.documents(str(context["user"]), project, module="buying", page=1, page_size=50, status_scope="active")
        receiving = self.pending_receiving(str(context["user"]), project, limit=50)
        return {"context": context, "pending": pending, "stock_documents": documents, "buying_documents": buying, "receiving": receiving}

    def _prepare_material_request_payload(
        self,
        context: dict[str, Any],
        business_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve and freeze every ERPNext link before confirmation."""

        # Tests and non-HTTP callers may supply a compact context mapping
        # without going through ``business_context``.  Activate its paired
        # account explicitly so a previous request cannot leak a Site into
        # this preview.
        context_account = (context.get("account") or {}).get("code") if isinstance(context.get("account"), dict) else ""
        source_account = self._business_account_for_source(str(context.get("classification_source") or "original"))
        _BUSINESS_ACCOUNT_CONTEXT.set(str(context_account or source_account["code"]))

        items = business_payload.get("items")
        if not isinstance(items, list) or not items:
            raise BusinessInputError("至少选择一项物料", field_path="items")
        schedule_date = str(business_payload.get("schedule_date") or "").strip()
        if not schedule_date:
            raise BusinessInputError("要求到货日期不能为空", field_path="schedule_date")
        try:
            date.fromisoformat(schedule_date)
        except ValueError as exc:
            raise BusinessInputError("要求到货日期必须是 YYYY-MM-DD", field_path="schedule_date") from exc

        user = str(context["user"])
        project_code = str(context["project_code"])
        client = self.client(user)
        company = self.erpnext_company_name("STEC")
        company_exists = client.document_exists("Company", company)
        if not company_exists.ok or not bool((company_exists.data or {}).get("exists")):
            raise BusinessInputError(
                f"ERPNext 测试账套缺少公司主数据：{company}",
                error_code="company_not_found",
                field_path="company",
            )

        erp_project = self.erpnext_project_name(client, project_code)
        project_result = client.get_document("Project", erp_project)
        if not project_result.ok or not isinstance(project_result.data, dict):
            raise BusinessInputError(
                f"ERPNext 测试账套缺少项目主数据：{project_code}",
                error_code="project_not_found",
                field_path="project",
            )
        project_document = project_result.data
        project_company = str(project_document.get("company") or "").strip()
        if project_company and project_company != company:
            raise BusinessInputError(
                "项目所属公司与申请公司不一致",
                error_code="project_company_mismatch",
                field_path="project",
            )

        project_config = context.get("project") if isinstance(context.get("project"), dict) else {}
        warehouse_code = str(project_config.get("warehouse_code") or "").strip()
        warehouse = self.erpnext_warehouse_name(warehouse_code)
        warehouse_exists = client.document_exists("Warehouse", warehouse)
        if not warehouse_exists.ok or not bool((warehouse_exists.data or {}).get("exists")):
            raise BusinessInputError(
                f"ERPNext 测试账套缺少项目仓库：{warehouse}",
                error_code="warehouse_not_found",
                field_path="warehouse",
            )

        normalized: list[dict[str, Any]] = []
        item_checks: list[dict[str, Any]] = []
        code_map = _load_material_item_code_map()
        for index, raw in enumerate(items):
            field_prefix = f"items[{index}]"
            if not isinstance(raw, dict):
                raise BusinessInputError("物料行格式无效", field_path=field_prefix)
            supplied_code = str(raw.get("item_code") or raw.get("material_id") or "").strip()
            item_code = code_map.get(supplied_code, supplied_code)
            if not item_code:
                raise BusinessInputError("缺少物料编码", field_path=f"{field_prefix}.item_code")
            try:
                qty = float(raw.get("qty") or 0)
            except (TypeError, ValueError) as exc:
                raise BusinessInputError("数量必须是数字", field_path=f"{field_prefix}.qty") from exc
            if qty <= 0:
                raise BusinessInputError("数量必须大于 0", field_path=f"{field_prefix}.qty")
            uom = str(raw.get("uom") or "").strip()
            if not uom:
                raise BusinessInputError("缺少库存单位", field_path=f"{field_prefix}.uom")
            item_result = client.get_document("Item", item_code)
            item_document = item_result.data if item_result.ok and isinstance(item_result.data, dict) else {}
            if not item_document:
                raise BusinessInputError(
                    f"ERPNext 中不存在物料：{item_code}",
                    error_code="item_not_found",
                    field_path=f"{field_prefix}.item_code",
                )
            if int(item_document.get("disabled") or 0):
                raise BusinessInputError(
                    f"物料已停用：{item_code}",
                    error_code="item_disabled",
                    field_path=f"{field_prefix}.item_code",
                )
            if not int(item_document.get("is_purchase_item") if item_document.get("is_purchase_item") is not None else 1):
                raise BusinessInputError(
                    f"物料不可采购：{item_code}",
                    error_code="item_not_purchasable",
                    field_path=f"{field_prefix}.item_code",
                )
            stock_uom = str(item_document.get("stock_uom") or "").strip()
            if stock_uom and uom != stock_uom:
                raise BusinessInputError(
                    f"库存单位不匹配，ERPNext 要求 {stock_uom}",
                    error_code="uom_mismatch",
                    field_path=f"{field_prefix}.uom",
                )
            normalized.append({
                "item_code": item_code,
                "qty": qty,
                "uom": uom,
                "warehouse": warehouse,
                "project": erp_project,
                "description": str(raw.get("description") or "").strip(),
            })
            item_checks.append({
                "item_code": item_code,
                "item_name": item_document.get("item_name"),
                "stock_uom": stock_uom,
                "is_stock_item": int(item_document.get("is_stock_item") or 0),
                "is_purchase_item": int(item_document.get("is_purchase_item") or 0),
            })

        return {
            "_prepared_material_request": True,
            "material_request_type": "Purchase",
            "schedule_date": schedule_date,
            "company": company,
            "project_code": project_code,
            "erpnext_project": erp_project,
            "warehouse": warehouse,
            "items": normalized,
            "purpose": str(business_payload.get("purpose") or "现场施工使用").strip(),
            "preflight": {
                "company": company,
                "project": erp_project,
                "warehouse": warehouse,
                "items": item_checks,
            },
        }

    def create_material_request_direct(self, cookie_header: str, payload: dict[str, Any], *, request_id: str = "") -> dict[str, Any]:
        context = self.business_context(cookie_header)
        user = str(context["user"])
        account_code = str(_BUSINESS_ACCOUNT_CONTEXT.get() or (context.get("account") or {}).get("code") or "")
        requested_project = str(payload.get("project_code") or "").strip()
        if requested_project and requested_project != str(context["project_code"]):
            raise PermissionError("项目上下文与当前登录会话不一致")
        project_code = str(context["project_code"])
        request_context = self._idempotency_context(user, project_code, "business-portal", request_id)[1]
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("至少选择一项物料")
        if payload.get("_prepared_material_request"):
            normalized = [dict(row) for row in payload.get("items") or []]
            company = str(payload.get("company") or "").strip()
        else:
            normalized = []
            for raw in items:
                if not isinstance(raw, dict):
                    raise ValueError("物料行格式无效")
                item_code = str(raw.get("item_code") or "").strip()
                item_code = _load_material_item_code_map().get(item_code, item_code)
                qty = float(raw.get("qty") or 0)
                if not item_code or qty <= 0:
                    raise ValueError("物料编码和数量必须有效")
                row = {"item_code": item_code, "qty": qty}
                for field in ("uom", "warehouse", "description"):
                    if raw.get(field):
                        row[field] = str(raw[field]).strip()
                row["project"] = self.erpnext_project_name(self.client(user), project_code)
                normalized.append(row)
            company = self.erpnext_company_name("STEC")
        command_payload = {
            "material_request_type": "Purchase",
            "schedule_date": str(payload.get("schedule_date") or "").strip() or date.today().isoformat(),
            "company": company,
            "items": normalized,
            "title": str(payload.get("purpose") or "").strip(),
        }
        cached = self.business_commands.request_result(request_id, account_code=account_code)
        if cached is None and request_context is not None:
            cached = request_context[1].idempotency_results.get(request_id)
        if cached is not None:
            return cached
        adapter = ERPNextAdapter(self.client(user))
        result = adapter.execute({"tool": "erpnext.buying.create_material_request_draft", "arguments": command_payload})
        if not result.ok or not isinstance(result.data, dict):
            raise ValueError(result.user_message or result.error or "创建材料申请草稿失败")
        name = str(result.data.get("name") or "")
        readback = self.document(user, "Material Request", name) if name else result.data
        response = {"request_id": request_id, "doctype": "Material Request", "name": name, "document": readback, "readback": True}
        self.business_commands.remember_request(request_id, response, account_code=account_code)
        self._remember_idempotent_result(request_context, request_id, response)
        return response

    def business_preview(self, cookie_header: str, payload: dict[str, Any]) -> dict[str, Any]:
        context = self.business_context(cookie_header)
        context_account = (context.get("account") or {}).get("code") if isinstance(context.get("account"), dict) else ""
        source_account = self._business_account_for_source(str(context.get("classification_source") or "original"))
        _BUSINESS_ACCOUNT_CONTEXT.set(str(context_account or source_account["code"]))
        action = str(payload.get("action") or "").strip()
        if action not in BUSINESS_ACTIONS:
            raise ValueError("业务动作不在门户白名单中")
        business_payload = dict(payload.get("payload") or {})
        if any(key in business_payload for key in ("user", "employee", "api_key", "api_secret", "tool", "arguments", "request_id")):
            raise ValueError("业务预览不能携带身份、凭据或底层 ToolCall 参数")
        summary: dict[str, Any] = {"action": action, "project": context["project_code"], "requires_confirmation": True}
        if action == "material_request.create_draft":
            rows = business_payload.get("items") if isinstance(business_payload.get("items"), list) else []
            business_payload = self._prepare_material_request_payload(context, business_payload)
            summary.update({"title": "创建材料申请草稿", "line_count": len(rows), "quantity": sum(float(row.get("qty") or 0) for row in rows if isinstance(row, dict))})
            summary["resolved"] = {
                "company": business_payload["company"],
                "project": business_payload["erpnext_project"],
                "warehouse": business_payload["warehouse"],
                "items": business_payload["preflight"]["items"],
            }
        elif action == "material_request.update_draft":
            name = str(business_payload.get("name") or "").strip()
            if not name:
                raise BusinessInputError("缺少材料申请单号", error_code="missing_document", field_path="name")
            schedule_date = str(business_payload.get("schedule_date") or "").strip()
            if schedule_date:
                try:
                    date.fromisoformat(schedule_date)
                except ValueError as exc:
                    raise BusinessInputError("日期必须是 YYYY-MM-DD", error_code="invalid_date", field_path="schedule_date") from exc
            business_payload = {
                "name": name,
                "schedule_date": schedule_date,
                "purpose": str(business_payload.get("purpose") or "").strip(),
            }
            summary.update({"title": "修改材料申请草稿", "name": name})
        elif action == "document.submit":
            summary.update({"title": "提交 ERPNext 单据", "doctype": business_payload.get("doctype"), "name": business_payload.get("name")})
        elif action == "workflow.action":
            summary.update({"title": "执行审批动作", "doctype": business_payload.get("doctype"), "name": business_payload.get("name"), "action": business_payload.get("action")})
        elif action == "rfq.create":
            summary.update({"title": "创建询价单草稿", "line_count": len(business_payload.get("selected_rows") or []), "supplier_count": len(business_payload.get("supplier_codes") or [])})
        elif action == "quotation.create":
            summary.update({"title": "录入供应商报价", "supplier_code": business_payload.get("supplier_code"), "request_for_quotation": business_payload.get("request_for_quotation")})
        elif action == "purchase_order.create":
            summary.update({"title": "创建采购订单草稿", "supplier_quotation": business_payload.get("supplier_quotation")})
        elif action == "purchase_receipt.create":
            summary.update({"title": "创建采购收货草稿", "purchase_order": business_payload.get("purchase_order")})
        elif action == "purchase_discrepancy.create":
            summary.update({"title": "记录收货差异", "purchase_receipt": business_payload.get("purchase_receipt")})
        elif action == "purchase_return.create":
            summary.update({"title": "创建采购退货草稿", "purchase_receipt": business_payload.get("purchase_receipt")})
        elif action == "stock.project_issue.create":
            summary.update({"title": "创建项目领料草稿", "line_count": len(business_payload.get("items") or []), "source_warehouse": business_payload.get("source_warehouse")})
        elif action == "stock.project_return.create":
            summary.update({"title": "创建项目退料草稿", "line_count": len(business_payload.get("items") or []), "target_warehouse": business_payload.get("target_warehouse")})
        elif action == "stock.transfer.create":
            summary.update({"title": "创建库存调拨草稿", "line_count": len(business_payload.get("items") or []), "source_warehouse": business_payload.get("source_warehouse"), "target_warehouse": business_payload.get("target_warehouse")})
        elif action == "stock.reconciliation.create":
            summary.update({"title": "创建库存盘点草稿", "line_count": len(business_payload.get("items") or []), "warehouse": business_payload.get("warehouse")})
        command = self.business_commands.create(
            action=action,
            user=str(context["user"]),
            project=str(context["project_code"]),
            payload=business_payload,
            summary=summary,
            account_code=str(_BUSINESS_ACCOUNT_CONTEXT.get() or ""),
        )
        return command.as_dict()

    def create_stock_business_draft(
        self,
        user: str,
        project: str,
        action: str,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        """Execute a typed stock draft and immediately read it back.

        The browser supplies only business fields.  Tool names, company and
        project links are selected here, on the server, before the adapter is
        called.  This keeps stock issue/return/transfer/count in the same
        preview-confirm boundary as buying actions.
        """
        client = self.client(user)
        company = self.erpnext_company_name("STEC")
        if action == "stock.project_issue.create":
            tool = "erpnext.projects.create_material_issue_draft"
            arguments = dict(payload)
            arguments["project"] = self.erpnext_project_name(client, project)
            arguments["company"] = company
        elif action == "stock.transfer.create":
            tool = "erpnext.stock.create_transfer_draft"
            arguments = dict(payload)
            arguments["company"] = company
            arguments.setdefault("project", self.erpnext_project_name(client, project))
        elif action == "stock.reconciliation.create":
            tool = "erpnext.stock.create_reconciliation_draft"
            arguments = dict(payload)
            arguments["company"] = company
        else:
            tool = "erpnext.stock.create_entry_draft"
            arguments = dict(payload)
            arguments["company"] = company
            arguments.setdefault("stock_entry_type", "Material Receipt")
            arguments.setdefault("purpose", "Material Receipt")
            arguments.setdefault("remarks", f"Project material return for {project}")
        result = ERPNextAdapter(client).execute({"tool": tool, "arguments": arguments})
        if not result.ok or not isinstance(result.data, dict):
            raise ValueError(result.user_message or result.error or "库存草稿创建失败")
        name = str(result.data.get("name") or "")
        doctype = str(result.data.get("doctype") or ("Stock Reconciliation" if action == "stock.reconciliation.create" else "Stock Entry"))
        readback = self.document(user, doctype, name) if name else result.data
        response = {
            "request_id": request_id,
            "doctype": doctype,
            "name": name,
            "document": readback,
            "result": result.data,
            "readback": True,
        }
        return response

    def update_material_request_draft(
        self,
        user: str,
        name: str,
        *,
        schedule_date: str = "",
        purpose: str = "",
    ) -> dict[str, Any]:
        if not user or not name:
            raise ValueError("user 和材料申请单号必填")
        client = self.client(user)
        current = client.get_document("Material Request", name)
        if not current.ok or not isinstance(current.data, dict):
            raise ValueError(current.user_message or current.error or f"无法读取材料申请 {name}")
        document = current.data
        if int(document.get("docstatus") or 0) != 0:
            raise ValueError("只有草稿状态的材料申请才能修改")
        changes: dict[str, Any] = {}
        if schedule_date:
            changes["schedule_date"] = schedule_date
            for row in document.get("items") or []:
                if isinstance(row, dict):
                    row["schedule_date"] = schedule_date
            changes["items"] = document.get("items") or []
        if purpose:
            changes["title"] = purpose
        if not changes:
            raise ValueError("至少提供新的到货日期或用途说明")
        result = client.update_document("Material Request", name, changes)
        if not result.ok:
            raise ValueError(result.user_message or result.error or "材料申请草稿修改失败")
        return self.document(user, "Material Request", name)

    def business_confirm(self, cookie_header: str, command_id: str, request_id: str) -> dict[str, Any]:
        context = self.business_context(cookie_header)
        user = str(context["user"])
        account_code = str(_BUSINESS_ACCOUNT_CONTEXT.get() or (context.get("account") or {}).get("code") or "")
        request_context = self._idempotency_context(user, str(context["project_code"]), "business-portal", request_id)[1]
        cached = self.business_commands.request_result(request_id, account_code=account_code)
        if cached is None and request_context is not None:
            cached = request_context[1].idempotency_results.get(request_id)
        if cached is not None:
            return cached
        command = self.business_commands.get(command_id, user=user, account_code=account_code)
        if command.status != "pending" or command.expires_at < time.time():
            raise ValueError("业务确认已过期或已处理")
        payload = command.payload
        if command.action == "material_request.create_draft":
            result = self.create_material_request_direct(cookie_header, payload, request_id=request_id)
        elif command.action == "material_request.update_draft":
            result = self.update_material_request_draft(
                user,
                str(payload.get("name") or ""),
                schedule_date=str(payload.get("schedule_date") or ""),
                purpose=str(payload.get("purpose") or ""),
            )
        elif command.action == "document.submit":
            result = self.submit_document(user, str(payload.get("doctype") or ""), str(payload.get("name") or ""), request_id=request_id, project=command.project)
        elif command.action == "workflow.action":
            result = self.apply_workflow_action(user, str(payload.get("doctype") or ""), str(payload.get("name") or ""), str(payload.get("action") or ""), comment=str(payload.get("comment") or ""), request_id=request_id, project=command.project)
        elif command.action == "rfq.create":
            result = self.create_request_for_quotation(
                user,
                command.project,
                [str(value) for value in payload.get("selected_rows") or []],
                [str(value) for value in payload.get("supplier_codes") or []],
                schedule_date=str(payload.get("schedule_date") or ""),
                message_for_supplier=str(payload.get("message_for_supplier") or ""),
                request_id=request_id,
                conversation_id="business-portal",
            )
        elif command.action == "quotation.create":
            result = self.create_supplier_quotation(
                user,
                command.project,
                str(payload.get("request_for_quotation") or ""),
                str(payload.get("supplier_code") or ""),
                list(payload.get("offers") or []),
                valid_till=str(payload.get("valid_till") or ""),
                terms=str(payload.get("terms") or ""),
                request_id=request_id,
                conversation_id="business-portal",
            )
        elif command.action == "purchase_order.create":
            result = self.create_purchase_order_from_supplier_quotation(
                user, command.project, str(payload.get("supplier_quotation") or ""),
                selected_items=list(payload.get("selected_items") or []), request_id=request_id, conversation_id="business-portal",
            )
        elif command.action == "purchase_receipt.create":
            result = self.create_purchase_receipt_from_purchase_order(
                user, command.project, str(payload.get("purchase_order") or ""),
                selected_items=list(payload.get("selected_items") or []), request_id=request_id, conversation_id="business-portal",
            )
        elif command.action == "purchase_discrepancy.create":
            result = self.record_purchase_receipt_discrepancy(
                user, command.project, str(payload.get("purchase_receipt") or ""), str(payload.get("description") or ""),
                items=list(payload.get("items") or []), discrepancy_type=str(payload.get("discrepancy_type") or "spec_mismatch"),
                severity=str(payload.get("severity") or "Medium"), assigned_to=str(payload.get("assigned_to") or ""),
                create_todo=bool(payload.get("create_todo", False)),
                request_id=request_id, conversation_id="business-portal",
            )
        elif command.action in {
            "stock.project_issue.create",
            "stock.project_return.create",
            "stock.transfer.create",
            "stock.reconciliation.create",
        }:
            result = self.create_stock_business_draft(
                user,
                command.project,
                command.action,
                payload,
                request_id=request_id,
            )
        else:
            result = self.create_purchase_return_from_receipt(
                user, command.project, str(payload.get("purchase_receipt") or ""), str(payload.get("reason") or ""),
                items=list(payload.get("items") or []), request_id=request_id, conversation_id="business-portal",
            )
        command.status = "completed"
        command.result = result
        self.business_commands.remember_request(request_id, result, account_code=account_code)
        self._remember_idempotent_result(request_context, request_id, result)
        return result

    def tariff_extraction_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        manager = getattr(self, "tariff_extraction", None)
        if manager is None:
            manager = TariffExtractionJobManager(ROOT / ".runtime" / "tariff-extraction")
            self.tariff_extraction = manager
        return manager.start(payload)

    def tariff_extraction_status(self, job_id: str) -> dict[str, Any]:
        manager = getattr(self, "tariff_extraction", None)
        if manager is None:
            raise ValueError("任务不存在或服务尚未初始化")
        return manager.snapshot(job_id)

    def tariff_family_review_summary(self) -> dict[str, Any]:
        path = TARIFF_FAMILY_REVIEW_DIR / "tariff_family_summary.json"
        if not path.exists():
            raise ValueError("税则物料族审阅包尚未生成")
        summary = json.loads(path.read_text(encoding="utf-8"))
        if TARIFF_ATTRIBUTE_SUMMARY_PATH.exists():
            summary["attribute_summary"] = json.loads(TARIFF_ATTRIBUTE_SUMMARY_PATH.read_text(encoding="utf-8"))
        return summary

    def _tariff_taxonomy_index(self) -> TariffTaxonomyIndex:
        source_path = resolve_tariff_taxonomy_source(
            TARIFF_FAMILY_REVIEW_DIR / "tariff_family_summary.json",
            TARIFF_TAXONOMY_RUNTIME_ROOT,
        )
        signature = (str(source_path), source_path.stat().st_mtime_ns, source_path.stat().st_size)
        cached = getattr(self, "_tariff_taxonomy_cache", None)
        if cached is None or cached[0] != signature:
            cached = (signature, TariffTaxonomyIndex.from_jsonl(source_path))
            self._tariff_taxonomy_cache = cached
        return cached[1]

    def tariff_taxonomy_summary(self) -> dict[str, Any]:
        return self._tariff_taxonomy_index().summary()

    def tariff_taxonomy_children(self, parent_code: str = "") -> list[dict[str, Any]]:
        return self._tariff_taxonomy_index().children(parent_code or None)

    def tariff_taxonomy_search(self, query: str, *, kind: str = "", limit: int = 100) -> dict[str, Any]:
        return self._tariff_taxonomy_index().search(query, kind=kind, limit=limit)

    def _gpc_reference_index(self) -> GpcReferenceIndex:
        """Load the allow-listed, generated GPC package for the browser."""

        database = ReferenceCatalogDatabase(GPC_REFERENCE_DATABASE_PATH)
        use_database = (
            GPC_REFERENCE_RUNTIME_ROOT.resolve() == (ROOT / ".runtime" / "gpc-reference").resolve()
            and GPC_MATERIAL_PLACEMENTS_PATH.resolve()
            == (ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl").resolve()
            and GPC_PROCUREMENT_TYPE_PROFILES_PATH.resolve()
            == (ROOT / ".runtime" / "material-master" / "gpc-procurement-type-profiles.jsonl").resolve()
            and GPC_INTERNAL_EXTENSIONS_PATH.resolve()
            == (ROOT / "data" / "material_master" / "gpc_internal_extensions_v0_1.json").resolve()
        )
        if use_database and database.is_ready("gpc"):
            revision = database.revision("gpc")
            signature = (
                "sqlite",
                str(GPC_REFERENCE_DATABASE_PATH.resolve()),
                int(revision.get("revision") or 0),
            )
            cached = getattr(self, "_gpc_reference_cache", None)
            if cached is None or cached[0] != signature:
                cached = (
                    signature,
                    database.load_gpc_index(GPC_PROCUREMENT_TEMPLATE_CATALOG_PATH),
                )
                self._gpc_reference_cache = cached
            return cached[1]

        root = GPC_REFERENCE_RUNTIME_ROOT.resolve()
        version_root = (root / GPC_REFERENCE_VERSION).resolve()
        try:
            version_root.relative_to(root)
        except ValueError as exc:  # pragma: no cover - defensive path boundary
            raise ValueError("GPC 运行期路径越界") from exc
        signature_parts = []
        for name in ("manifest.json", "nodes.jsonl", "brick-profiles.jsonl", "translations.zh-CN.jsonl"):
            path = version_root / name
            signature_parts.append((str(path), path.stat().st_mtime_ns, path.stat().st_size) if path.is_file() else (str(path), 0, 0))
        placements_path = GPC_MATERIAL_PLACEMENTS_PATH.resolve()
        for extra_path in (
            placements_path,
            GPC_PROCUREMENT_TEMPLATE_CATALOG_PATH.resolve(),
            GPC_PROCUREMENT_TYPE_PROFILES_PATH.resolve(),
            GPC_INTERNAL_EXTENSIONS_PATH.resolve(),
        ):
            signature_parts.append(
                (str(extra_path), extra_path.stat().st_mtime_ns, extra_path.stat().st_size)
                if extra_path.is_file()
                else (str(extra_path), 0, 0)
            )
        signature = tuple(signature_parts)
        cached = getattr(self, "_gpc_reference_cache", None)
        if cached is None or cached[0] != signature:
            cached = (
                signature,
                GpcReferenceIndex.from_runtime(
                    root,
                    GPC_REFERENCE_VERSION,
                    material_placements_path=placements_path,
                    procurement_template_catalog_path=GPC_PROCUREMENT_TEMPLATE_CATALOG_PATH,
                    procurement_type_profiles_path=GPC_PROCUREMENT_TYPE_PROFILES_PATH,
                    internal_extensions_path=GPC_INTERNAL_EXTENSIONS_PATH,
                ),
            )
            self._gpc_reference_cache = cached
        return cached[1]

    def reference_catalog_revision(self, catalog: str = "hs", classification_source: str = "original") -> dict[str, Any]:
        """Return a cheap change token used by the page for live refresh."""

        catalog = str(catalog or "").strip().lower()
        classification_source = str(classification_source or "original").strip().lower()
        if catalog == "gpc" and classification_source == "chatgpt_v4":
            path = CHATGPT_CLASSIFICATION_DATA_PATH
            signature = f"{path.resolve()}:{path.stat().st_mtime_ns}:{path.stat().st_size}" if path.is_file() else f"{path.resolve()}:0:0"
            return {
                "catalog": catalog,
                "classification_source": classification_source,
                "available": path.is_file(),
                "storage": "files",
                "source_version": "chatgpt-classification-v4",
                "revision": hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16],
                "updated_at": path.stat().st_mtime if path.is_file() else 0,
            }
        if catalog == "gpc":
            database = ReferenceCatalogDatabase(GPC_REFERENCE_DATABASE_PATH)
            use_database = (
                GPC_REFERENCE_RUNTIME_ROOT.resolve() == (ROOT / ".runtime" / "gpc-reference").resolve()
                and GPC_MATERIAL_PLACEMENTS_PATH.resolve()
                == (ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl").resolve()
                and GPC_PROCUREMENT_TYPE_PROFILES_PATH.resolve()
                == (ROOT / ".runtime" / "material-master" / "gpc-procurement-type-profiles.jsonl").resolve()
                and GPC_INTERNAL_EXTENSIONS_PATH.resolve()
                == (ROOT / "data" / "material_master" / "gpc_internal_extensions_v0_1.json").resolve()
            )
            if use_database and database.is_ready("gpc"):
                return database.revision("gpc")
            root = GPC_REFERENCE_RUNTIME_ROOT.resolve() / GPC_REFERENCE_VERSION
            paths = [
                root / "manifest.json",
                root / "nodes.jsonl",
                GPC_MATERIAL_PLACEMENTS_PATH,
                GPC_PROCUREMENT_TYPE_PROFILES_PATH,
                GPC_INTERNAL_EXTENSIONS_PATH,
            ]
        elif catalog == "hs":
            paths = [
                resolve_tariff_taxonomy_source(
                    TARIFF_FAMILY_REVIEW_DIR / "tariff_family_summary.json",
                    TARIFF_TAXONOMY_RUNTIME_ROOT,
                )
            ]
        else:
            raise ValueError("未知参考目录：catalog 必须是 hs 或 gpc")
        signature = "|".join(
            f"{path.resolve()}:{path.stat().st_mtime_ns}:{path.stat().st_size}"
            if path.is_file()
            else f"{path.resolve()}:0:0"
            for path in paths
        )
        return {
            "catalog": catalog,
            "available": all(path.is_file() for path in paths[:1]),
            "storage": "files",
            "source_version": GPC_REFERENCE_VERSION if catalog == "gpc" else TARIFF_SOURCE_VERSION,
            "revision": hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16],
            "updated_at": max(
                (path.stat().st_mtime for path in paths if path.is_file()),
                default=0,
            ),
        }

    def _chatgpt_classification_index(self) -> ChatgptClassificationIndex:
        path = CHATGPT_CLASSIFICATION_DATA_PATH.resolve()
        if not path.is_file():
            raise FileNotFoundError("ChatGPT 分类 V4 数据包尚未生成")
        signature = (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        cached = getattr(self, "_chatgpt_classification_cache", None)
        if cached is None or cached[0] != signature:
            cached = (signature, ChatgptClassificationIndex(json.loads(path.read_text(encoding="utf-8")), source_path=path))
            self._chatgpt_classification_cache = cached
        return cached[1]

    @staticmethod
    def _reference_hs_payload(node: dict[str, Any], index: TariffTaxonomyIndex) -> dict[str, Any]:
        payload = dict(node)
        payload["official_name"] = payload.get("name", "")
        payload["working_name"] = payload.get("name", "")
        payload["translation_status"] = "official"
        payload["full_path"] = index.path(str(payload["code"]))
        return payload

    def reference_catalog_summary(self, catalog: str = "hs", classification_source: str = "original") -> dict[str, Any]:
        catalog = str(catalog or "").strip().lower()
        if catalog == "hs":
            index = self._tariff_taxonomy_index()
            summary = index.summary()
            kind_labels = summary.get("kind_labels") or {}
            levels = [
                {"kind": kind, "label": label, "label_zh": label, "level": level, "count": summary["counts"].get(kind, 0)}
                for level, (kind, label) in enumerate(kind_labels.items())
            ]
            return {
                **summary,
                "catalog": "hs",
                "available": True,
                "source": "中华人民共和国进出口税则",
                "source_url": TARIFF_SOURCE_URL,
                "levels": levels,
                "kind_labels_zh": kind_labels,
            }
        if catalog == "gpc":
            if str(classification_source or "original").strip().lower() == "chatgpt_v4":
                return self._chatgpt_classification_index().summary()
            try:
                return self._gpc_reference_index().summary()
            except (FileNotFoundError, ValueError) as exc:
                return {
                    "catalog": "gpc",
                    "available": False,
                    "source": "GS1 GPC",
                    "source_version": GPC_REFERENCE_VERSION,
                    "levels": [],
                    "counts": {},
                    "message": str(exc),
                }
        raise ValueError("未知参考目录：catalog 必须是 hs 或 gpc")

    def reference_catalog_children(
        self,
        catalog: str,
        parent_code: str = "",
        *,
        materialized_only: bool = False,
        classification_source: str = "original",
    ) -> list[dict[str, Any]]:
        catalog = str(catalog or "").strip().lower()
        if catalog == "hs":
            index = self._tariff_taxonomy_index()
            return [self._reference_hs_payload(row, index) for row in index.children(parent_code or None)]
        if catalog == "gpc":
            if str(classification_source or "original").strip().lower() == "chatgpt_v4":
                return self._chatgpt_classification_index().children(parent_code or None, materialized_only=materialized_only)
            return self._gpc_reference_index().children(parent_code or None, materialized_only=materialized_only)
        raise ValueError("未知参考目录：catalog 必须是 hs 或 gpc")

    def reference_catalog_search(
        self,
        catalog: str,
        query: str,
        *,
        kind: str = "",
        limit: int = 100,
        materialized_only: bool = False,
        classification_source: str = "original",
    ) -> dict[str, Any]:
        catalog = str(catalog or "").strip().lower()
        bounded_limit = min(200, max(1, int(limit)))
        if catalog == "hs":
            index = self._tariff_taxonomy_index()
            payload = index.search(query, kind=kind, limit=bounded_limit)
            payload["rows"] = [self._reference_hs_payload(row, index) for row in payload.get("rows", [])]
            return payload
        if catalog == "gpc":
            if str(classification_source or "original").strip().lower() == "chatgpt_v4":
                return self._chatgpt_classification_index().search(
                    query, kind=kind, limit=bounded_limit, materialized_only=materialized_only,
                )
            return self._gpc_reference_index().search(
                query,
                kind=kind,
                limit=bounded_limit,
                materialized_only=materialized_only,
            )
        raise ValueError("未知参考目录：catalog 必须是 hs 或 gpc")

    def reference_catalog_profile(self, catalog: str, code: str, classification_source: str = "original") -> dict[str, Any]:
        catalog = str(catalog or "").strip().lower()
        normalized = str(code or "").strip()
        if catalog == "gpc":
            if str(classification_source or "original").strip().lower() == "chatgpt_v4":
                return self._chatgpt_classification_index().profile(code)
            profile = self._gpc_reference_index().profile(normalized)
            item_code_map = _load_material_item_code_map()
            for material in profile.get("actual_materials") or []:
                source_id = str(material.get("material_id") or "")
                if source_id in item_code_map:
                    material["item_code"] = item_code_map[source_id]
            return profile
        if catalog == "hs":
            index = self._tariff_taxonomy_index()
            node = next((row for row in index.children(None) if row.get("code") == normalized), None)
            # Look up a node through a bounded search so non-root codes are
            # supported without exposing the index internals.
            if node is None:
                matches = index.search(normalized, limit=1).get("rows") or []
                node = matches[0] if matches and matches[0].get("code") == normalized else None
            if node is None:
                raise ValueError(f"税则节点不存在：{normalized}")
            if len(normalized) == 8 and normalized.isdigit():
                profile = self.tariff_declaration_profile(normalized)
                profile["path"] = index.path(normalized)
                profile["node"] = self._reference_hs_payload(node, index)
                return profile
            return {"code": normalized, "status": "available", "profile": None, "node": self._reference_hs_payload(node, index), "path": index.path(normalized)}
        raise ValueError("未知参考目录：catalog 必须是 hs 或 gpc")

    def _chatgpt_material_catalog(
        self,
        *,
        allowed_item_codes: set[str] | None = None,
        query: str = "",
        segment_code: str = "",
        category_code: str = "",
        standard_type: str = "",
        stock_uom: str = "",
        sort: str = "name",
        offset: int = 0,
        limit: int = 24,
        group_variants: bool = False,
    ) -> dict[str, Any]:
        """Read the imported V4 classification snapshot without using the old GPC index."""

        payload = self._chatgpt_classification_snapshot()
        source_rows = [dict(row) for row in payload.get("rows") or [] if isinstance(row, dict)]
        query_terms = [term.lower() for term in str(query or "").split() if term.strip()]
        rows = []
        for row in source_rows:
            row["classification_source"] = "chatgpt_v4"
            if allowed_item_codes is not None and str(row.get("item_code") or "") not in allowed_item_codes:
                continue
            haystack = str(row.get("search_text") or "").lower()
            if query_terms and not all(term in haystack for term in query_terms):
                continue
            if segment_code and str(row.get("segment_code") or "") != str(segment_code):
                continue
            if category_code and str(row.get("category_code") or "") != str(category_code):
                continue
            if standard_type and str(row.get("standard_type") or "") != str(standard_type):
                continue
            if stock_uom and str(row.get("stock_uom") or "") != str(stock_uom):
                continue
            row.setdefault("gpc_brick_code", row.get("family_code"))
            rows.append(row)
        if sort == "code":
            rows.sort(key=lambda row: str(row.get("item_code") or ""))
        elif sort == "type":
            rows.sort(key=lambda row: (str(row.get("standard_type") or ""), str(row.get("item_code") or "")))
        else:
            rows.sort(key=lambda row: (str(row.get("material_name") or row.get("item_name") or ""), str(row.get("item_code") or "")))

        sku_total = len(rows)
        if group_variants:
            groups: list[dict[str, Any]] = []
            for family_code, family_rows in _group_rows(rows, key=lambda row: str(row.get("family_code") or "")):
                if len(family_rows) <= 1:
                    groups.extend(family_rows)
                    continue
                first = family_rows[0]
                attributes = {
                    "一级分类": str(first.get("top_group") or ""),
                    "二级分类": str(first.get("sub_group") or ""),
                    "物料族": str(first.get("material_family") or ""),
                }
                groups.append({
                    **first,
                    "record_kind": "standard_type_group",
                    "material_id": f"chatgpt-family-{family_code}",
                    "variant_type_code": family_code,
                    "variant_count": len(family_rows),
                    "variant_attributes": {key: value for key, value in attributes.items() if value},
                    "standard_type": str(first.get("material_family") or ""),
                    "material_name": str(first.get("material_family") or first.get("material_name") or ""),
                    "item_code": "",
                    "gpc_brick_code": family_code,
                })
            rows = groups
        total = len(rows)
        segments = _count_rows(rows if not group_variants else [row for row in source_rows if (not query_terms or all(term in str(row.get("search_text") or "").lower() for term in query_terms))], "segment_code", "segment_name")
        types = _count_rows(rows if not group_variants else source_rows, "standard_type", "standard_type")
        uoms = _count_rows(rows if not group_variants else source_rows, "stock_uom", "stock_uom")
        category_tree = _build_chatgpt_category_tree(source_rows, query_terms)
        return {
            "rows": rows[offset : offset + limit],
            "total": total,
            "sku_total": sku_total,
            "offset": offset,
            "limit": limit,
            "segments": segments,
            "standard_types": types,
            "stock_uoms": uoms,
            "category_tree": category_tree,
        }

    def material_marketplace_catalog(
        self,
        *,
        cookie_header: str = "",
        verify_erpnext: bool = False,
        classification_source: str = "",
        query: str = "",
        segment_code: str = "",
        category_code: str = "",
        standard_type: str = "",
        stock_uom: str = "",
        sort: str = "name",
        page: int = 1,
        page_size: int = 24,
        group_variants: bool = False,
    ) -> dict[str, Any]:
        """Expose approved GPC materials as a read-only request catalogue."""

        bounded_page = max(1, int(page))
        bounded_page_size = min(60, max(1, int(page_size)))
        selected_source = self._classification_source(classification_source)
        if not classification_source and verify_erpnext:
            selected_source = self._classification_source(str(self.business_context(cookie_header).get("classification_source") or "original"))
        if selected_source == "chatgpt_v4":
            account = self._business_account_for_source(selected_source)
            context = self.business_context(cookie_header) if verify_erpnext else None
            allowed_item_codes: set[str] | None = None
            sync_status = "classification_only"
            sync_message = "ChatGPT 分类为分类账套预览；切换到对应测试账套后才能创建申请。"
            if verify_erpnext:
                user = str((context or {}).get("user") or "")
                try:
                    client = self.client(user, account_code=account["code"])
                    client.timeout = min(float(client.timeout), 3.0)
                    erp_rows = client.search_documents(
                        "Item",
                        filters={"disabled": 0},
                        fields=["item_code"],
                        limit=5000,
                        order_by="item_code asc",
                    )
                    if not erp_rows.ok:
                        raise ValueError(erp_rows.user_message or erp_rows.error or "ERPNext 物料目录不可用")
                    allowed_item_codes = {
                        str(row.get("item_code") or "")
                        for row in (erp_rows.data or [])
                        if isinstance(row, dict) and row.get("item_code")
                    }
                    sync_status = "erpnext_verified"
                    sync_message = "仅展示 ChatGPT 分类包中已在对应 V4 测试账套启用的物料。"
                except Exception:
                    sync_status = "erpnext_unavailable"
                    sync_message = "ChatGPT 分类测试账套暂时不可用，恢复连接后才能加入申请。"
            catalog = self._chatgpt_material_catalog(
                allowed_item_codes=allowed_item_codes,
                query=query,
                segment_code=segment_code,
                category_code=category_code,
                standard_type=standard_type,
                stock_uom=stock_uom,
                sort=sort,
                offset=(bounded_page - 1) * bounded_page_size,
                limit=bounded_page_size,
                group_variants=group_variants,
            )
            return {
                **catalog,
                "page": bounded_page,
                "page_size": bounded_page_size,
                "source": "ChatGPT 分类（龙华 V4）",
                "source_version": self._chatgpt_classification_snapshot().get("release_hash") or "chatgpt-v4",
                "classification_source": selected_source,
                "account_code": account["code"],
                "account_label": account["label"],
                "erpnext_site": account["site"],
                "price_status": "not_bound" if sync_status == "classification_only" else "not_maintained",
                "stock_status": "not_bound" if sync_status == "classification_only" else "query_on_request",
                "erpnext_sync_status": sync_status,
                "erpnext_sync_message": sync_message,
            }
        allowed_material_ids: set[str] | None = None
        code_map: dict[str, str] = {}
        sync_status = "local_catalog_only"
        sync_message = "目录数据来自本地 GPC 发布包。"
        selected_account = self._business_account_for_source(selected_source)
        if verify_erpnext:
            context = self.business_context(cookie_header)
            # The query's classification source is authoritative for a catalog
            # read.  A stale browser cookie must not make an explicit original
            # request read the V4 Site (or vice versa) during a switch.
            _BUSINESS_ACCOUNT_CONTEXT.set(selected_account["code"])
            cache_key = str(context.get("user") or "")
            cached_scope = getattr(self, "_material_catalog_sync_cache", {}).get(cache_key)
            if cached_scope and float(cached_scope.get("expires_at") or 0) > time.monotonic():
                allowed_material_ids = set(cached_scope.get("allowed_material_ids") or set())
                code_map = dict(cached_scope.get("code_map") or {})
                sync_status = str(cached_scope.get("sync_status") or "erpnext_unavailable")
                sync_message = str(cached_scope.get("sync_message") or "ERPNext 物料状态暂时无法读取。")
            else:
                try:
                    code_map_payload = json.loads(MATERIAL_ITEM_CODE_MAP_PATH.read_text(encoding="utf-8"))
                    code_map = code_map_payload.get("material_item_codes") if isinstance(code_map_payload, dict) else {}
                    if not isinstance(code_map, dict):
                        raise ValueError("ERPNext 物料编码映射文件格式无效")
                except Exception:
                    code_map = {}
            try:
                if not cached_scope or float(cached_scope.get("expires_at") or 0) <= time.monotonic():
                    # ``_BUSINESS_ACCOUNT_CONTEXT`` was set immediately above;
                    # keep the one-argument client contract used by older
                    # adapters and test doubles while still routing to the
                    # selected allowlisted Site.
                    client = self.client(str(context["user"]))
                    client.timeout = min(float(client.timeout), 2.0)
                    erp_rows = client.search_documents(
                        "Item",
                        filters={"disabled": 0},
                        fields=["item_code"],
                        limit=5000,
                        order_by="item_code asc",
                    )
                    if not erp_rows.ok:
                        raise ValueError(erp_rows.user_message or erp_rows.error or "ERPNext 物料目录不可用")
                    enabled_codes = {
                        str(row.get("item_code") or "")
                        for row in (erp_rows.data or [])
                        if isinstance(row, dict) and row.get("item_code")
                    }
                    allowed_material_ids = {
                        str(source_id)
                        for source_id, item_code in code_map.items()
                        if str(item_code) in enabled_codes
                    }
                    sync_status = "erpnext_verified"
                    sync_message = "仅展示本地已发布且 ERPNext 已启用的物料。"
                    self._material_catalog_sync_cache[cache_key] = {
                        "allowed_material_ids": set(allowed_material_ids),
                        "code_map": dict(code_map),
                        "sync_status": sync_status,
                        "sync_message": sync_message,
                        "expires_at": time.monotonic() + 30.0,
                    }
            except Exception as exc:
                sync_status = "erpnext_unavailable"
                sync_message = "ERPNext 暂时离线；当前展示最近同步目录，恢复连接后才能加入申请。"
                allowed_material_ids = set(str(source_id) for source_id in code_map)
                self._material_catalog_sync_cache[cache_key] = {
                    "allowed_material_ids": set(allowed_material_ids),
                    "code_map": dict(code_map),
                    "sync_status": sync_status,
                    "sync_message": sync_message,
                    "error": str(exc),
                    "expires_at": time.monotonic() + 10.0,
                }

        catalog_kwargs: dict[str, Any] = {
            "query": query,
            "segment_code": segment_code,
            "category_code": category_code,
            "standard_type": standard_type,
            "stock_uom": stock_uom,
            "sort": sort,
            "offset": (bounded_page - 1) * bounded_page_size,
            "limit": bounded_page_size,
        }
        if allowed_material_ids is not None:
            catalog_kwargs["allowed_material_ids"] = allowed_material_ids
        if group_variants:
            catalog_kwargs["group_all_multi_sku_types"] = True
        catalog = self._gpc_reference_index().material_catalog(**catalog_kwargs)
        if code_map:
            for row in catalog.get("rows") or []:
                source_id = str(row.get("material_id") or "")
                if source_id in code_map:
                    row["item_code"] = str(code_map[source_id])
        return {
            **catalog,
            "page": bounded_page,
            "page_size": bounded_page_size,
            "source": "Nexterp 已审核物料目录",
            "source_version": GPC_REFERENCE_VERSION,
            "price_status": "not_maintained",
            "stock_status": "query_on_request",
            "classification_source": selected_source,
            "account_code": selected_account["code"],
            "account_label": selected_account["label"],
            "erpnext_site": selected_account["site"],
            "erpnext_sync_status": sync_status,
            "erpnext_sync_message": sync_message,
        }

    @staticmethod
    def _tariff_attribute_map() -> dict[str, dict[str, Any]]:
        if not TARIFF_ATTRIBUTE_REVIEW_PATH.exists():
            return {}
        result: dict[str, dict[str, Any]] = {}
        with TARIFF_ATTRIBUTE_REVIEW_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                code = str(row.get("code") or "").strip()
                if not code:
                    continue
                try:
                    attributes = json.loads(row.get("attributes") or "{}")
                except json.JSONDecodeError:
                    attributes = {}
                result[code] = {
                    "attribute_status": str(row.get("attribute_status") or ""),
                    "attributes": attributes if isinstance(attributes, dict) else {},
                }
        return result

    def tariff_family_review_rows(
        self, *, status: str = "", attribute_status: str = "", query: str = "", offset: int = 0, limit: int = 100
    ) -> dict[str, Any]:
        path = TARIFF_FAMILY_REVIEW_DIR / "tariff_family_candidates.tsv"
        if not path.exists():
            raise ValueError("税则物料族审阅包尚未生成")
        status = str(status or "").strip().lower()
        attribute_status = str(attribute_status or "").strip().lower()
        query = str(query or "").strip().lower()
        query_terms = [term.strip() for term in query.split("|") if term.strip()]
        offset = max(0, int(offset))
        limit = min(500, max(1, int(limit)))
        rows: list[dict[str, Any]] = []
        attribute_map = self._tariff_attribute_map()
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if status and row.get("review_status", "").lower() != status:
                    continue
                evidence = attribute_map.get(str(row.get("code") or ""), {"attribute_status": "", "attributes": {}})
                row["attribute_status"] = evidence["attribute_status"]
                row["attributes"] = evidence["attributes"]
                if attribute_status and row["attribute_status"].lower() != attribute_status:
                    continue
                if query_terms:
                    haystack = " ".join(row.get(key, "") for key in (
                        "code", "normalized_name", "parent_name", "chapter_context",
                        "suggested_top_group", "suggested_material_family",
                    )).lower() + " " + json.dumps(row["attributes"], ensure_ascii=False).lower()
                    if not any(term in haystack for term in query_terms):
                        continue
                rows.append(row)
        return {"rows": rows[offset : offset + limit], "total": len(rows), "offset": offset, "limit": limit}

    def tariff_extraction_cancel(self, job_id: str) -> dict[str, Any]:
        manager = getattr(self, "tariff_extraction", None)
        if manager is None:
            raise ValueError("任务不存在或服务尚未初始化")
        return manager.cancel(job_id)

    def tariff_declaration_start(self, payload: dict[str, Any]) -> dict[str, Any]:
        manager = getattr(self, "tariff_declaration", None)
        if manager is None:
            manager = TariffDeclarationJobManager(TARIFF_DECLARATION_RUNTIME_ROOT)
            self.tariff_declaration = manager
        return manager.start(payload)

    def tariff_declaration_status(self, job_id: str) -> dict[str, Any]:
        manager = getattr(self, "tariff_declaration", None)
        if manager is None:
            raise ValueError("任务不存在或服务尚未初始化")
        return manager.snapshot(job_id)

    def tariff_declaration_cancel(self, job_id: str) -> dict[str, Any]:
        manager = getattr(self, "tariff_declaration", None)
        if manager is None:
            raise ValueError("任务不存在或服务尚未初始化")
        return manager.cancel(job_id)

    def _tariff_declaration_profile_source(self) -> Path | None:
        candidates: list[tuple[tuple[int, int, int], Path]] = []
        for profile_path in TARIFF_DECLARATION_RUNTIME_ROOT.glob("*/tariff-declaration-profiles.jsonl"):
            if not profile_path.is_file():
                continue
            manifest_path = profile_path.with_name("manifest.json")
            mode = ""
            profile_count = 0
            if manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    mode = str(manifest.get("mode") or "")
                    profile_count = int(manifest.get("profiles") or 0)
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
            candidates.append(((1 if mode == "full" else 0, profile_count, profile_path.stat().st_mtime_ns), profile_path))
        if not candidates:
            return None
        return max(candidates, key=lambda item: item[0])[1]

    def tariff_declaration_profile(self, code: str) -> dict[str, Any]:
        normalized = str(code or "").strip()
        if len(normalized) != 8 or not normalized.isdigit():
            raise ValueError("属性查询需要八位数字税号")
        source_path = self._tariff_declaration_profile_source()
        if source_path is None:
            return {
                "code": normalized,
                "status": "source_unavailable",
                "message": "申报目录证据包尚未生成",
                "profile": None,
            }
        signature = (str(source_path), source_path.stat().st_mtime_ns, source_path.stat().st_size)
        cached = getattr(self, "_tariff_declaration_profiles_cache", None)
        if cached is None or cached[0] != signature:
            profiles = load_declaration_profiles(source_path)
            cached = (signature, {profile.code: profile.as_dict() for profile in profiles})
            self._tariff_declaration_profiles_cache = cached
        profile = cached[1].get(normalized)
        if profile is None:
            return {
                "code": normalized,
                "status": "not_available",
                "message": "2026 涉税规范申报目录未提供此税号的属性记录",
                "profile": None,
                "source_file": str(source_path),
            }
        return {
            "code": normalized,
            "status": "available" if profile.get("declaration_attributes") else "no_attributes",
            "message": "已从涉税规范申报目录读取" if profile.get("declaration_attributes") else "目录有税号记录，但未列出申报属性",
            "profile": profile,
            "source_file": str(source_path),
        }

    def _record_material_publication(
        self,
        draft: Any,
        *,
        request_id: str,
        analysis_id: str,
        user: str,
        readback: dict[str, Any],
        write_succeeded: bool = False,
    ) -> dict[str, Any] | None:
        try:
            publication = self.material_publications.record_verified(
                request_id=request_id,
                draft_id=draft.draft_id,
                analysis_id=analysis_id,
                confirmed_by=user,
                material_type=draft.material_type.model_dump(mode="json"),
                sku={
                    "item_code": draft.item_code,
                    "type_id": draft.type_id,
                    "standard_name": draft.standard_name,
                    "item_name": draft.item_name,
                    "sku_name": draft.item_name,
                    "item_group": draft.item_group,
                    "stock_uom": draft.stock_uom,
                    "required_specs": draft.required_specs,
                    "optional_specs": draft.optional_specs,
                    "item_doc": dict(draft.item_doc),
                    "erpnext_readback": readback,
                },
            )
            self.material_intake.retriever.classifier.register_publication(publication)
            return None
        except Exception as exc:
            draft.status = "failed"
            return {
                "draft_id": draft.draft_id,
                "item_code": draft.item_code,
                "error_type": "runtime_catalog_sync_failed",
                "user_message": f"ERPNext 回读已通过，但 Nexterp 运行期目录同步失败：{exc}",
                "write_succeeded": write_succeeded,
            }

    def confirm_material_alias(self, payload: dict[str, Any]) -> dict[str, Any]:
        alias = str(payload.get("alias") or "").strip()
        target_kind = str(payload.get("target_kind") or "").strip()
        target_id = str(payload.get("target_id") or "").strip()
        user = str(payload.get("user") or "").strip()
        if not user:
            raise ValueError("user 必填")
        retriever = self.material_intake.retriever
        valid_ids = (
            {item.type_id for item in retriever.classifier.types}
            if target_kind == "type"
            else {str(row.get("item_code") or "") for row in retriever.resolver.rows}
        )
        if target_kind not in {"type", "sku"} or target_id not in valid_ids:
            raise ValueError("别名目标不是当前标准目录中的真实类型或 SKU")
        return retriever.alias_store.confirm(
            alias=alias,
            target_kind=target_kind,
            target_id=target_id,
            user=user,
            source_row=str(payload.get("source_row") or ""),
        )

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
            "task_context": {
                "current_goal": session.current_goal,
                "intent_mode": session.intent_mode,
                "confirmed_entities": session.confirmed_entities,
                "unresolved_fields": session.unresolved_fields,
                "active_capability": session.active_capability,
                "loaded_context": session.loaded_context,
                "recent_documents": session.recent_documents,
                "pending_operation": session.pending_operation,
                "last_successful_progress": session.last_successful_progress,
            },
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

    def client(self, user: str, account_code: str = "") -> ERPNextClient:
        selected_code = str(account_code or _BUSINESS_ACCOUNT_CONTEXT.get() or "").strip().lower()
        if selected_code in {row["code"] for row in self._business_account_catalog()}:
            account = self._business_account_for_code(selected_code)
            credentials_path = Path(self._business_account_value(account, "credentials_path"))
            base_url = self._business_account_value(account, "base_url")
            host_header = self._business_account_value(account, "host_header")
        else:
            default_credentials_path = MATERIAL_TEST_CREDENTIALS_PATH if self.profile == "material_test" else DEFAULT_CREDENTIALS_PATH
            credentials_path = Path(os.getenv(f"NEXTERP_{self.profile.upper()}_CREDENTIALS_PATH", str(default_credentials_path)))
            base_url = self.base_url
            host_header = self.host_header
        credentials = load_user_credentials(user, credentials_path)
        return ERPNextClient(base_url, credentials["api_key"], credentials["api_secret"], host_header=host_header, timeout=90)

    def erpnext_company_name(self, code: str = "STEC") -> str:
        profile = str(getattr(self, "profile", "civil"))
        active_account = _BUSINESS_ACCOUNT_CONTEXT.get()
        if active_account in {row["code"] for row in self._business_account_catalog()}:
            account = self._business_account_for_code(active_account)
            return self._business_account_value(account, "company")
        prefix = f"NEXTERP_{profile.upper()}_"
        # The isolated material-test Site has its own Company master.  Accept
        # both historical env names so a stale .env cannot make business
        # documents point at the civil sandbox company.
        override = os.getenv(prefix + "COMPANY_NAME") or os.getenv(prefix + "COMPANY")
        if override:
            return override
        if profile == "material_test":
            return "Nexterp物料测试有限公司"
        return MasterDataRelease().company_name(code)

    def erpnext_project_name(self, client: ERPNextClient, project_code: str) -> str:
        project = MasterDataRelease().projects.get(project_code)
        if not project:
            return project_code
        active_account = _BUSINESS_ACCOUNT_CONTEXT.get()
        if active_account == "classification_v4" and project_code == "PRJ-HL-13":
            account = self._business_account_for_code(active_account)
            return self._business_account_value(account, "project_name")
        if getattr(self, "profile", "civil") == "material_test" and project_code == "PRJ-HL-13":
            # The isolated bootstrap deliberately keeps the business code
            # stable while ERPNext's autoname may be PROJ-0001.  The override
            # is configurable for a rebuilt Site and avoids requiring every
            # role (notably procurement) to have Project read permission.
            override = os.getenv("NEXTERP_MATERIAL_TEST_PROJECT_NAME")
            if override:
                return override
            return "PROJ-0001"
        # ERPNext may autoname Project documents (for example PROJ-0001),
        # while the business portal keeps the stable project_code as the
        # project_name.  Try the stable code first, then the long master-data
        # label for older sites.
        candidates = [project_code, str(project.get("project_name") or "").strip()]
        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            result = client.search_documents(
                "Project",
                filters={"project_name": candidate},
                fields=["name", "project_name"],
                limit=20,
            )
            if not result.ok or not isinstance(result.data, list):
                continue
            matches = [
                row for row in result.data
                if isinstance(row, dict) and str(row.get("project_name") or "").strip() == candidate
            ]
            if len(matches) == 1:
                return str(matches[0]["name"])
        return project_code

    def erpnext_warehouse_name(self, warehouse_value: str) -> str:
        value = str(warehouse_value or "").strip()
        for warehouse in MasterDataRelease().warehouses.values():
            if value in {
                warehouse.get("warehouse_code"),
                warehouse.get("warehouse_name"),
                warehouse.get("erpnext_warehouse_name"),
            }:
                name = str(warehouse.get("erpnext_warehouse_name") or value)
                active_account = _BUSINESS_ACCOUNT_CONTEXT.get()
                if active_account == "classification_v4" and name.endswith(" - SD"):
                    name = name[:-5] + " - NCV"
                elif getattr(self, "profile", "civil") == "material_test" and name.endswith(" - SD"):
                    name = name[:-5] + " - NMT"
                return name
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
            if not hasattr(client, "get_document"):
                detail = client.call_method(
                    "agent_bridge.api.get_document_with_workflow_actions",
                    {"doctype": doctype, "name": name},
                )
                if not detail.ok or not isinstance(detail.data, dict) or not isinstance(detail.data.get("document"), dict):
                    return None
                document = detail.data["document"]
                transitions = detail.data.get("actions")
                actions = [str(item.get("action")) for item in transitions or [] if isinstance(item, dict) and item.get("action")]
            else:
                document_result = client.get_document(doctype, name)
                if not document_result.ok or not isinstance(document_result.data, dict):
                    return None
                document = document_result.data
                transitions = client.get_workflow_actions(doctype, name)
                actions = [str(item.get("action")) for item in (transitions.data or []) if isinstance(item, dict) and item.get("action")] if transitions.ok and isinstance(transitions.data, list) else []
            if erpnext_project and not document_matches_project(document, erpnext_project):
                return None
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
        if (not result.ok or not isinstance(result.data, dict)) and "agent_bridge" in ((result.error or "") + (result.user_message or "")):
            # material-test.localhost deliberately has no optional
            # agent_bridge app. Reconstruct the same permission-scoped view
            # from standard Material Request, child rows and Bin APIs.
            result = self._pending_procurement_from_standard_api(
                client,
                erpnext_project=erpnext_project,
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
                "stock_uom": row.get("stock_uom") or row.get("uom"),
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

    def _pending_procurement_from_standard_api(
        self,
        client: Any,
        *,
        erpnext_project: str,
        warehouses: list[str],
        limit: int,
    ) -> Any:
        """Return the bridge-shaped pending procurement payload using Frappe APIs."""
        from nexterp_agent.erpnext.schemas import ToolResult

        parents = client.search_documents(
            "Material Request",
            filters={"docstatus": 1},
            fields=["name", "schedule_date"],
            limit=min(500, max(limit, 50)),
            order_by="modified desc",
        )
        if not parents.ok:
            return parents
        rows: list[dict[str, Any]] = []
        item_codes: set[str] = set()
        for parent in parents.data or []:
            if not isinstance(parent, dict) or not parent.get("name"):
                continue
            detail = client.get_document("Material Request", str(parent["name"]))
            if not detail.ok or not isinstance(detail.data, dict):
                continue
            for item in detail.data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if erpnext_project and str(item.get("project") or "") != erpnext_project:
                    continue
                ordered = _number(item.get("ordered_qty"))
                qty = _number(item.get("qty"))
                remaining = max(qty - ordered, 0.0)
                if not item.get("item_code") or remaining <= 0:
                    continue
                item_code = str(item["item_code"])
                item_codes.add(item_code)
                rows.append({
                    "item_code": item_code,
                    "item_name": item.get("item_name"),
                    "qty": qty,
                    "remaining_qty": remaining,
                    "ordered_qty": ordered,
                    "uom": item.get("uom") or item.get("stock_uom"),
                    "stock_uom": item.get("stock_uom") or item.get("uom"),
                    "schedule_date": item.get("schedule_date") or detail.data.get("schedule_date"),
                    "warehouse": item.get("warehouse"),
                    "project": item.get("project"),
                    "material_request": detail.data.get("name"),
                    "material_request_item": item.get("name"),
                    "rate": item.get("rate") or 0,
                })
                if len(rows) >= limit:
                    break
            if len(rows) >= limit:
                break
        bins = client.search_documents(
            "Bin",
            filters={"warehouse": ["in", warehouses]} if warehouses else {},
            fields=["item_code", "warehouse", "actual_qty", "reserved_qty", "projected_qty"],
            limit=1000,
        )
        if not bins.ok:
            return ToolResult(ok=True, data={"rows": rows, "inventory": [], "inventory_error": bins.user_message or bins.error})
        inventory = [
            dict(row) for row in (bins.data or [])
            if isinstance(row, dict) and (not item_codes or str(row.get("item_code") or "") in item_codes)
        ]
        return ToolResult(ok=True, data={"rows": rows, "inventory": inventory})

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
                "company": self.erpnext_company_name("STEC"),
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
                "company": self.erpnext_company_name("STEC"),
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
        create_todo: bool = False,
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
            "create_todo": bool(create_todo),
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
        # Business idempotency is account-scoped as well as identity/project
        # scoped.  A request_id reused after switching Sites must not replay a
        # result that was written to the other ERPNext account.
        account_code = _BUSINESS_ACCOUNT_CONTEXT.get()
        session_project = f"{account_code}::{project}" if account_code else project
        store = self.scoped_session_store(user, session_project, conversation_id)
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
            name = self.erpnext_warehouse_name(row.get("erpnext_warehouse_name") or code)
            if name and name not in names:
                names.append(name)
        return names

    @staticmethod
    def _document_row_matches_scope(
        row: dict[str, Any],
        *,
        doctype: str,
        status_scope: str,
        query: str = "",
        date_from: str = "",
        date_to: str = "",
    ) -> bool:
        """Apply portal visibility rules consistently after either API path."""

        if int(row.get("docstatus") or 0) == 2:
            return status_scope == "cancelled"
        status = str(row.get("status") or "").strip().lower()
        if status_scope == "cancelled":
            return False
        if status_scope == "active" and status in {"cancelled", "已取消"}:
            return False
        if status_scope == "pending_receipt" and doctype == "Purchase Order":
            if status in {"cancelled", "已取消", "completed", "已完成", "closed", "已关闭"}:
                return False
            try:
                if float(row.get("per_received")) >= 100:
                    return False
            except (TypeError, ValueError):
                # Older ERPNext versions do not expose per_received in list rows.
                # Their terminal status still safely excludes completed orders.
                pass
        if query:
            needle = query.casefold()
            haystack = " ".join(str(row.get(key) or "") for key in ("name", "title", "supplier", "status", "workflow_state"))
            if needle not in haystack.casefold():
                return False
        if date_from or date_to:
            value = str(row.get("transaction_date") or row.get("posting_date") or "")[:10]
            if date_from and value and value < date_from:
                return False
            if date_to and value and value > date_to:
                return False
        return True

    def pending_receiving(self, user: str, project: str = "", *, limit: int = 50) -> dict[str, Any]:
        """Return only submitted, non-cancelled POs that still have receipt quantity."""

        if not user:
            raise ValueError("user 必填")
        client = self.client(user)
        project_key = (user, project)
        erpnext_project = self._project_name_cache.get(project_key, "") if project else ""
        if project and not erpnext_project:
            erpnext_project = self.erpnext_project_name(client, project)
            self._project_name_cache[project_key] = erpnext_project
        result = client.search_documents(
            "Purchase Order",
            filters={"docstatus": 1},
            fields=DOCUMENT_LIST_FIELDS["Purchase Order"],
            limit=min(200, max(1, int(limit))),
            offset=0,
            order_by="modified desc",
        )
        rows = result.data if result.ok and isinstance(result.data, list) else []
        if erpnext_project:
            rows = self.filter_parent_documents_by_project(
                user,
                "Purchase Order",
                rows,
                erpnext_project,
                account_code=_BUSINESS_ACCOUNT_CONTEXT.get(),
            )
        rows = [
            dict(row)
            for row in rows
            if self._document_row_matches_scope(row, doctype="Purchase Order", status_scope="pending_receipt")
        ]
        for row in rows:
            try:
                row["remaining_receipt_percent"] = max(0.0, 100.0 - float(row.get("per_received") or 0.0))
            except (TypeError, ValueError):
                row["remaining_receipt_percent"] = None
        return {
            "project": project,
            "erpnext_project": erpnext_project,
            "count": len(rows),
            "rows": rows,
            "error": None if result.ok else result.user_message or result.error,
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
        query: str = "",
        doctype: str = "",
        status_scope: str = "active",
        date_from: str = "",
        date_to: str = "",
    ) -> dict[str, Any]:
        if not user:
            raise ValueError("user 必填")
        if module not in MODULE_DOCTYPES:
            raise ValueError(f"未知业务模块：{module}")
        page = max(1, int(page))
        page_size = min(50, max(1, int(page_size)))
        requested_doctype = doctype
        client = self.client(user)
        account_code = _BUSINESS_ACCOUNT_CONTEXT.get()
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
        # The comprehension above intentionally keeps the module ordering; apply
        # the optional doctype filter separately to preserve readable error paths.
        if doctype:
            document_specs = [row for row in document_specs if row[0] == doctype]
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
                    "documents": [
                        dict(row) for row in batch_groups.get(doctype, [])
                        if isinstance(row, dict)
                        and self._document_row_matches_scope(
                            row,
                            doctype=doctype,
                            status_scope=status_scope,
                            query=query,
                            date_from=date_from,
                            date_to=date_to,
                        )
                    ],
                }
        else:
            def load_group_in_account(
                user_value: str,
                doctype_value: str,
                label_value: str,
                project_child_value: str | None,
                project_value: str,
                limit_value: int,
                offset_value: int,
                status_value: str,
                owner_value: str,
            ) -> dict[str, Any]:
                # ContextVar values are thread-local.  Install the selected
                # allowlisted account in each worker, then call the original
                # method signature so legacy test doubles remain compatible.
                token = _BUSINESS_ACCOUNT_CONTEXT.set(account_code)
                try:
                    return self._load_document_group(
                        user_value,
                        doctype_value,
                        label_value,
                        project_child_value,
                        project_value,
                        limit_value,
                        offset_value,
                        status_value,
                        owner_value,
                    )
                finally:
                    _BUSINESS_ACCOUNT_CONTEXT.reset(token)

            with ThreadPoolExecutor(max_workers=min(8, len(document_specs))) as executor:
                futures = {
                    doctype: executor.submit(
                        load_group_in_account,
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
        for group in loaded.values():
            group["documents"] = [
                row for row in group.get("documents", [])
                if self._document_row_matches_scope(
                    row,
                    doctype=str(group.get("doctype") or ""),
                    status_scope=status_scope,
                    query=query,
                    date_from=date_from,
                    date_to=date_to,
                )
            ]
        modules: list[dict[str, Any]] = []
        for module_code, module_label, doctypes in DOCUMENT_MODULES:
            if module_code != module:
                continue
            groups = [loaded[doctype] for doctype, _, _ in doctypes if doctype in loaded]
            modules.append({"code": module_code, "label": module_label, "groups": groups})
        return {
            "project": project,
            "erpnext_project": erpnext_project,
            "module": module,
            "status": status,
            "status_scope": status_scope,
            "query": query,
            "doctype": requested_doctype,
            "date_from": date_from,
            "date_to": date_to,
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
        account_code: str = "",
    ) -> dict[str, Any]:
        # ThreadPoolExecutor workers do not inherit ContextVar state.  Carry
        # the allowlisted account explicitly so a V4 list can never fall back
        # to the original material-test Site while filtering child rows.
        if account_code:
            _BUSINESS_ACCOUNT_CONTEXT.set(account_code)
        client = self.client(user, account_code=account_code) if account_code else self.client(user)
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
            rows = self.filter_parent_documents_by_project(
                user,
                doctype,
                rows,
                erpnext_project,
                account_code=account_code,
            )
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
        account_code: str = "",
    ) -> list[dict[str, Any]]:
        if account_code:
            _BUSINESS_ACCOUNT_CONTEXT.set(account_code)
        client = self.client(user, account_code=account_code) if account_code else self.client(user)
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

    @staticmethod
    def _document_has_relation(document: dict[str, Any], relation_fields: tuple[str, ...], name: str) -> bool:
        if any(str(document.get(field) or "") == name for field in relation_fields):
            return True
        for item in document.get("items") or []:
            if isinstance(item, dict) and any(str(item.get(field) or "") == name for field in relation_fields):
                return True
        return False

    @staticmethod
    def _document_has_any_relation(document: dict[str, Any], relation_fields: tuple[str, ...], names: set[str]) -> bool:
        return any(AgentWorkbenchService._document_has_relation(document, relation_fields, candidate) for candidate in names)

    def related_document_source_links(
        self,
        client: Any,
        doctype: str,
        name: str,
        document: dict[str, Any],
    ) -> list[dict[str, str]]:
        """Add reverse child links so a request can be followed downstream.

        ERPNext stores most procurement ancestry on child rows.  The detail
        drawer therefore needs a small, read-only reverse lookup for the
        current document; it never invents a business state or writes data.
        """

        links = document_source_links(document)
        seen = {(row["doctype"], row["name"]) for row in links}
        relation_specs: dict[str, tuple[tuple[str, tuple[str, ...]], ...]] = {
            "Material Request": (
                ("Request for Quotation", ("material_request",)),
                ("Supplier Quotation", ("material_request", "request_for_quotation")),
                ("Purchase Order", ("material_request", "request_for_quotation", "supplier_quotation")),
            ),
            "Request for Quotation": (
                ("Supplier Quotation", ("request_for_quotation",)),
                ("Purchase Order", ("request_for_quotation",)),
            ),
            "Supplier Quotation": (("Purchase Order", ("supplier_quotation",)),),
            "Purchase Order": (
                ("Purchase Receipt", ("purchase_order",)),
                ("Stock Entry", ("purchase_order", "purchase_receipt")),
            ),
            "Purchase Receipt": (("Stock Entry", ("purchase_receipt", "purchase_order")),),
        }
        labels = {
            "Request for Quotation": "询价",
            "Supplier Quotation": "供应商报价",
            "Purchase Order": "采购订单",
            "Purchase Receipt": "收货/退货",
            "Stock Entry": "库存流水",
        }
        for child_doctype, relation_fields in relation_specs.get(doctype, ()):
            target_names = {name}
            if child_doctype == "Supplier Quotation":
                target_names.update(row["name"] for row in links if row.get("doctype") == "Request for Quotation")
            elif child_doctype == "Purchase Order":
                target_names.update(row["name"] for row in links if row.get("doctype") in {"Request for Quotation", "Supplier Quotation"})
            try:
                listing = client.search_documents(
                    child_doctype,
                    filters={},
                    fields=["name", "docstatus", "modified"],
                    limit=100,
                    offset=0,
                    order_by="modified desc",
                )
                candidates = listing.data if listing.ok and isinstance(listing.data, list) else []
                for row in candidates:
                    child_name = str(row.get("name") or "")
                    if not child_name:
                        continue
                    child_result = client.get_document(child_doctype, child_name)
                    child_document = child_result.data if child_result.ok and isinstance(child_result.data, dict) else None
                    if not child_document or not self._document_has_any_relation(child_document, relation_fields, target_names):
                        continue
                    key = (child_doctype, child_name)
                    if key not in seen:
                        links.append({"doctype": child_doctype, "name": child_name, "label": labels.get(child_doctype, child_doctype)})
                        seen.add(key)
            except Exception:
                # A missing optional child DocType must not make the main detail
                # drawer unavailable; explicit ERPNext links remain visible.
                continue
        return links

    def document(self, user: str, doctype: str, name: str) -> dict[str, Any]:
        if not user or not doctype or not name:
            raise ValueError("user、doctype 和 name 必填")
        if doctype not in ALLOWED_DOCUMENT_TYPES:
            raise ValueError(f"测试台暂不支持查看 {doctype}")
        client = self.client(user)
        if doctype == "Item":
            result = client.get_document(doctype, name)
            if not result.ok or not isinstance(result.data, dict):
                raise ValueError(result.user_message or result.error or f"无法读取 {doctype} {name}")
            document = dict(result.data)
            enabled = not bool(document.get("disabled"))
            ledger_result = client.get_stock_ledger_entries(item_code=name, limit=30) if hasattr(client, "get_stock_ledger_entries") else None
            return {
                "doctype": doctype,
                "name": name,
                "label": "标准物料",
                "document": document,
                "summary": {"item_code": document.get("item_code"), "item_name": document.get("item_name"), "stock_uom": document.get("stock_uom")},
                "source_links": [],
                "inventory": {
                    "ledger": ledger_result.data if ledger_result and ledger_result.ok and isinstance(ledger_result.data, list) else [],
                    "ledger_error": None if not ledger_result or ledger_result.ok else ledger_result.user_message or ledger_result.error,
                },
                "readback": {"verified": True, "source": "ERPNext", "docstatus": document.get("docstatus")},
                "process": {
                    "state": "已启用" if enabled else "已停用",
                    "description": "这是 ERPNext 中的物料主数据，不参与单据审批流程。",
                    "workflow_configured": False,
                    "assignees": [],
                    "notification": "后续采购、库存和领料单据可引用该物料编码。" if enabled else "该物料当前不可用于新的业务单据。",
                    "available_actions": [],
                    "can_submit": False,
                    "history": [],
                    "comments": [],
                },
            }
        if hasattr(client, "get_document"):
            document_result = client.get_document(doctype, name)
            if not document_result.ok or not isinstance(document_result.data, dict):
                raise ValueError(document_result.user_message or document_result.error or f"无法读取 {doctype} {name}")
            document = document_result.data
            transitions = client.get_workflow_actions(doctype, name)
            actions = [str(row.get("action")) for row in transitions.data if isinstance(row, dict) and row.get("action")] if transitions.ok and isinstance(transitions.data, list) else []
            comments_result = client.search_documents(
                "Comment",
                filters={"reference_doctype": doctype, "reference_name": name},
                fields=["name", "content", "comment_by", "creation"],
                limit=100,
                order_by="creation asc",
            )
            comments = comments_result.data if comments_result.ok and isinstance(comments_result.data, list) else []
            history = []
        else:
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
            actions = [str(row.get("action")) for row in transitions if isinstance(row, dict) and row.get("action")] if isinstance(transitions, list) else []
            history = result.data.get("workflow_history") if isinstance(result.data.get("workflow_history"), list) else []
            comments = result.data.get("workflow_comments") if isinstance(result.data.get("workflow_comments"), list) else []
        process = document_process_summary(doctype, document, actions)
        process["approval_stages"] = document_approval_stages(doctype, document)
        process["history"] = history
        process["comments"] = comments
        return {
            "doctype": doctype,
            "name": name,
            "label": next(
                (label for _, _, doctypes in DOCUMENT_MODULES for candidate, label, _ in doctypes if candidate == doctype),
                doctype,
            ),
            "document": document,
            "process": process,
            "summary": document_quantity_summary(document),
            "source_links": self.related_document_source_links(client, doctype, name, document),
            "readback": {
                "verified": True,
                "source": "ERPNext",
                "docstatus": document.get("docstatus"),
                "workflow_state": document.get("workflow_state") or "",
                "modified": document.get("modified") or "",
            },
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
        if hasattr(client, "apply_workflow"):
            result = client.apply_workflow(doctype, name, action)
        else:
            result = client.call_method(
                "agent_bridge.api.apply_workflow_action_with_comment",
                {"doctype": doctype, "name": name, "action": action, "comment": comment.strip()},
            )
        if result.ok and comment.strip() and hasattr(client, "add_comment"):
            comment_result = client.add_comment(
                doctype,
                name,
                comment.strip(),
                comment_email=user,
                comment_by=user,
            )
            if not comment_result.ok:
                raise ValueError(comment_result.user_message or comment_result.error or "审批意见写入失败")
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
        session_key = workbench_session_key(user, project_code, conversation_id)
        intent_mode = infer_intent_mode(text)
        existing_store = self.scoped_session_store(user, project_code, conversation_id)
        existing_session = existing_store.load(user, profile=str(employee["profile"]))
        upsert_context = getattr(self.capability_repository, "upsert_session_context", None)
        if upsert_context:
            upsert_context(
                external_subject=workbench_external_subject(user),
                agent_id="main",
                session_key=session_key,
                employee_user=user,
                project_code=project_code,
                current_goal=text,
                intent_mode=intent_mode,
                confirmed_entities=existing_session.confirmed_entities,
                unresolved_fields=existing_session.unresolved_fields,
                active_capability=existing_session.active_capability,
                loaded_context=existing_session.loaded_context,
                recent_documents=existing_session.recent_documents,
                pending_operation=existing_session.pending_operation,
                last_successful_progress=existing_session.last_successful_progress,
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
            "trusted_context": {
                "role_code": employee.get("role_code", ""),
                "department_code": employee.get("department_code", ""),
                "intent_mode": intent_mode,
            },
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
        session.current_goal = text
        session.intent_mode = intent_mode
        session.loaded_context = list(response.get("loaded_context") or session.loaded_context)
        session.active_capability = next(
            (str(row.get("node_id")) for row in reversed(response.get("loaded_nodes") or [])
             if isinstance(row, dict) and str(row.get("node_id") or "").startswith("cap.")),
            session.active_capability,
        )
        session.pending_operation = pending_id or None
        session.last_successful_progress = str(response.get("status") or "")
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

    def _business_json(self, callback: Callable[[], dict[str, Any]]) -> None:
        """Keep ERPNext outages and validation failures inside the JSON API."""

        try:
            json_response(self, {"ok": True, **callback()})
        except PermissionError as exc:
            json_response(self, {"ok": False, "error": str(exc)}, HTTPStatus.FORBIDDEN)
        except (ValueError, json.JSONDecodeError) as exc:
            json_response(self, {"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover - live ERPNext boundary
            json_response(self, {"ok": False, "error": str(exc)}, HTTPStatus.BAD_GATEWAY)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/workbench-assets/"):
            asset_response(self, ASSET_DIR / Path(parsed.path).name)
            return
        if parsed.path == "/":
            html_response(self, BUSINESS_PORTAL_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/material-master-browser", "/material-master-browser/"}:
            html_response(self, MATERIAL_MASTER_BROWSER_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/developer/agent-workbench", "/developer/agent-workbench/"}:
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
        if parsed.path in {"/material-item-lab", "/material-item-lab/"}:
            html_response(self, MATERIAL_ITEM_LAB_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/material-intake-lab", "/material-intake-lab/"}:
            html_response(self, MATERIAL_INTAKE_LAB_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/material-marketplace", "/material-marketplace/"}:
            html_response(self, MATERIAL_MARKETPLACE_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/procurement-batch-pilot", "/procurement-batch-pilot/"}:
            html_response(self, PROCUREMENT_BATCH_PILOT_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/tariff-extraction-lab", "/tariff-extraction-lab/"}:
            html_response(self, TARIFF_EXTRACTION_LAB_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/tariff-declaration-lab", "/tariff-declaration-lab/"}:
            html_response(self, TARIFF_DECLARATION_LAB_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/tariff-family-review", "/tariff-family-review/"}:
            html_response(self, TARIFF_FAMILY_REVIEW_BROWSER_PATH.read_text(encoding="utf-8"))
            return
        if parsed.path in {"/tariff-taxonomy-browser", "/tariff-taxonomy-browser/"}:
            html_response(self, TARIFF_TAXONOMY_BROWSER_PATH.read_text(encoding="utf-8"))
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
        if parsed.path == "/api/business/bootstrap":
            self._business_json(lambda: self.server.service.business_bootstrap(self.headers.get("Cookie", "")))  # type: ignore[attr-defined]
            return
        if parsed.path == "/api/business/dashboard":
            self._business_json(lambda: self.server.service.business_dashboard(self.headers.get("Cookie", "")))  # type: ignore[attr-defined]
            return
        if parsed.path == "/api/business/documents":
            query = parse_qs(parsed.query)
            self._business_json(lambda: self.server.service.business_documents(  # type: ignore[attr-defined]
                self.headers.get("Cookie", ""),
                project=(query.get("project") or [""])[0],
                module=(query.get("module") or ["buying"])[0],
                status=(query.get("status") or [""])[0],
                query=(query.get("q") or query.get("query") or [""])[0],
                doctype=(query.get("doctype") or [""])[0],
                status_scope=(query.get("status_scope") or ["active"])[0],
                date_from=(query.get("date_from") or [""])[0],
                date_to=(query.get("date_to") or [""])[0],
                page=int((query.get("page") or [1])[0]),
                page_size=int((query.get("page_size") or [20])[0]),
                mine_only=(query.get("mine_only") or ["0"])[0] in {"1", "true", "True"},
            ))
            return
        if parsed.path == "/api/business/document":
            query = parse_qs(parsed.query)
            self._business_json(lambda: self.server.service.business_document(  # type: ignore[attr-defined]
                self.headers.get("Cookie", ""),
                (query.get("doctype") or [""])[0],
                (query.get("name") or [""])[0],
            ))
            return
        if parsed.path == "/api/business/inventory":
            query = parse_qs(parsed.query)
            self._business_json(lambda: self.server.service.business_inventory(  # type: ignore[attr-defined]
                self.headers.get("Cookie", ""),
                item_code=(query.get("item_code") or [""])[0],
                warehouse=(query.get("warehouse") or [""])[0],
                project=(query.get("project") or [""])[0],
                limit=int((query.get("limit") or [100])[0]),
            ))
            return
        if parsed.path == "/api/business/project-materials":
            self._business_json(lambda: self.server.service.business_project_materials(self.headers.get("Cookie", "")))  # type: ignore[attr-defined]
            return
        if parsed.path == "/api/material-classification/browser-data":
            query = parse_qs(parsed.query)
            source = str((query.get("source") or ["release_v1_1"])[0] or "release_v1_1")
            path = MATERIAL_BROWSER_DATA_PATHS.get(source)
            if path is None:
                json_response(self, {"ok": False, "error": "未知分类数据源"}, HTTPStatus.BAD_REQUEST)
                return
            json_file_response(self, path)
            return
        if parsed.path == "/api/material-marketplace/catalog":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.material_marketplace_catalog(  # type: ignore[attr-defined]
                    cookie_header=self.headers.get("Cookie", ""),
                    verify_erpnext=True,
                    classification_source=(query.get("classification_source") or [""])[0],
                    query=(query.get("q") or [""])[0],
                    segment_code=(query.get("segment") or [""])[0],
                    category_code=(query.get("category") or [""])[0],
                    standard_type=(query.get("standard_type") or [""])[0],
                    stock_uom=(query.get("stock_uom") or [""])[0],
                    sort=(query.get("sort") or ["name"])[0],
                    page=int((query.get("page") or [1])[0]),
                    page_size=int((query.get("page_size") or [24])[0]),
                    group_variants=(query.get("group_variants") or ["0"])[0] in {"1", "true", "yes"},
                )
            except (FileNotFoundError, TypeError, ValueError) as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 400)
                return
            json_response(self, {"ok": True, **payload})
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
        if parsed.path == "/api/tariff-extraction/job":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.tariff_extraction_status(  # type: ignore[attr-defined]
                    (query.get("job_id") or [""])[0]
                )
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, "job": payload})
            return
        if parsed.path == "/api/procurement-batch-pilot/latest":
            payload = self.server.service.procurement_batch_pilot_latest()  # type: ignore[attr-defined]
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/procurement-batch-pilot/job":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.procurement_batch_pilot_status(  # type: ignore[attr-defined]
                    (query.get("job_id") or [""])[0]
                )
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, "job": payload})
            return
        if parsed.path == "/api/procurement-batch-pilot/result":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.procurement_batch_pilot_result(  # type: ignore[attr-defined]
                    (query.get("job_id") or [""])[0]
                )
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/procurement-batch-pilot/review":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.procurement_batch_review_status(  # type: ignore[attr-defined]
                    (query.get("job_id") or [""])[0]
                )
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/tariff-declaration/job":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.tariff_declaration_status(  # type: ignore[attr-defined]
                    (query.get("job_id") or [""])[0]
                )
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, "job": payload})
            return
        if parsed.path == "/api/tariff-declaration/profile":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.tariff_declaration_profile(  # type: ignore[attr-defined]
                    (query.get("code") or [""])[0]
                )
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 400)
                return
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/reference-catalog/revision":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.reference_catalog_revision(  # type: ignore[attr-defined]
                    (query.get("catalog") or ["hs"])[0],
                    (query.get("classification_source") or ["original"])[0],
                )
            except (FileNotFoundError, ValueError) as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/reference-catalog/summary":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.reference_catalog_summary(  # type: ignore[attr-defined]
                    (query.get("catalog") or ["hs"])[0],
                    (query.get("classification_source") or ["original"])[0],
                )
            except (FileNotFoundError, ValueError) as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            # A missing GPC package is a normal, recoverable state: the HS
            # catalog stays usable and the UI can show the import command.
            json_response(self, {"ok": True, "summary": payload})
            return
        if parsed.path == "/api/reference-catalog/children":
            query = parse_qs(parsed.query)
            try:
                rows = self.server.service.reference_catalog_children(  # type: ignore[attr-defined]
                    (query.get("catalog") or ["hs"])[0],
                    (query.get("parent_code") or [""])[0],
                    materialized_only=(query.get("materialized_only") or [""])[0].strip().lower()
                    in {"1", "true", "yes", "on"},
                    classification_source=(query.get("classification_source") or ["original"])[0],
                )
            except (FileNotFoundError, ValueError) as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, "rows": rows})
            return
        if parsed.path == "/api/reference-catalog/search":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.reference_catalog_search(  # type: ignore[attr-defined]
                    (query.get("catalog") or ["hs"])[0],
                    (query.get("q") or [""])[0],
                    kind=(query.get("kind") or [""])[0],
                    limit=int((query.get("limit") or [100])[0]),
                    materialized_only=(query.get("materialized_only") or [""])[0].strip().lower()
                    in {"1", "true", "yes", "on"},
                    classification_source=(query.get("classification_source") or ["original"])[0],
                )
            except (FileNotFoundError, TypeError, ValueError) as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 400)
                return
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/reference-catalog/profile":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.reference_catalog_profile(  # type: ignore[attr-defined]
                    (query.get("catalog") or ["hs"])[0],
                    (query.get("code") or [""])[0],
                    (query.get("classification_source") or ["original"])[0],
                )
            except (FileNotFoundError, ValueError) as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/tariff-family-review/summary":
            try:
                payload = self.server.service.tariff_family_review_summary()  # type: ignore[attr-defined]
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, "summary": payload})
            return
        if parsed.path == "/api/tariff-family-review/rows":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.tariff_family_review_rows(  # type: ignore[attr-defined]
                    status=(query.get("status") or [""])[0],
                    attribute_status=(query.get("attribute_status") or [""])[0],
                    query=(query.get("q") or [""])[0],
                    offset=int((query.get("offset") or [0])[0]),
                    limit=int((query.get("limit") or [100])[0]),
                )
            except (ValueError, TypeError) as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 400)
                return
            json_response(self, {"ok": True, **payload})
            return
        if parsed.path == "/api/tariff-taxonomy/summary":
            try:
                payload = self.server.service.tariff_taxonomy_summary()  # type: ignore[attr-defined]
            except (FileNotFoundError, ValueError) as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, "summary": payload})
            return
        if parsed.path == "/api/tariff-taxonomy/children":
            query = parse_qs(parsed.query)
            try:
                rows = self.server.service.tariff_taxonomy_children(  # type: ignore[attr-defined]
                    (query.get("parent_code") or [""])[0]
                )
            except ValueError as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 404)
                return
            json_response(self, {"ok": True, "rows": rows})
            return
        if parsed.path == "/api/tariff-taxonomy/search":
            query = parse_qs(parsed.query)
            try:
                payload = self.server.service.tariff_taxonomy_search(  # type: ignore[attr-defined]
                    (query.get("q") or [""])[0],
                    kind=(query.get("kind") or [""])[0],
                    limit=int((query.get("limit") or [100])[0]),
                )
            except (TypeError, ValueError) as exc:
                json_response(self, {"ok": False, "error": str(exc)}, 400)
                return
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
            if self.path == "/api/business/context":
                request = read_json(self)
                context = self.server.service.business_context_update(request)  # type: ignore[attr-defined]
                existing_cookie = self.headers.get("Cookie", "").strip("; ")
                account_context_cookie = "; ".join(
                    part for part in existing_cookie.split("; ")
                    if part.startswith("nexterp_business_account=") or part.startswith("nexterp_classification_source=")
                )
                selected_context_cookie = "; ".join(part for part in (
                    account_context_cookie,
                    f"nexterp_business_user={quote(context['user'], safe='')}",
                    f"nexterp_business_project={quote(context['project_code'], safe='')}",
                ) if part)
                json_response(self, {"ok": True, "context": self.server.service.business_context(  # type: ignore[attr-defined]
                    selected_context_cookie
                )}, set_cookies=[
                    f"nexterp_business_user={quote(context['user'], safe='')}; Path=/; SameSite=Lax",
                    f"nexterp_business_project={quote(context['project_code'], safe='')}; Path=/; SameSite=Lax",
                ])
                return
            if self.path == "/api/business/classification":
                request = read_json(self)
                context = self.server.service.business_classification_update(request)  # type: ignore[attr-defined]
                existing_cookie = self.headers.get("Cookie", "").strip("; ")
                selected_cookie = f"nexterp_classification_source={quote(context['classification_source'], safe='')}"
                account_cookie = f"nexterp_business_account={quote(context['account_code'], safe='')}"
                cookie_header = "; ".join(part for part in (existing_cookie, selected_cookie, account_cookie) if part)
                json_response(self, {"ok": True, "context": self.server.service.business_context(cookie_header)}, set_cookies=[
                    f"nexterp_classification_source={quote(context['classification_source'], safe='')}; Path=/; SameSite=Lax",
                    f"nexterp_business_account={quote(context['account_code'], safe='')}; Path=/; SameSite=Lax",
                ])
                return
            if self.path == "/api/business/commands/preview":
                payload = self.server.service.business_preview(self.headers.get("Cookie", ""), read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "command": payload})
                return
            if self.path.startswith("/api/business/commands/") and self.path.endswith("/confirm"):
                command_id = self.path[len("/api/business/commands/") : -len("/confirm")].strip("/")
                request = read_json(self)
                request_id = str(request.get("request_id") or "").strip()
                if not request_id:
                    raise ValueError("request_id 必填")
                payload = self.server.service.business_confirm(self.headers.get("Cookie", ""), command_id, request_id)  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "result": payload})
                return
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
            if self.path == "/api/material-intake/analyze":
                payload = self.server.service.analyze_material_intake(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "result": payload})
                return
            if self.path == "/api/procurement-batch-pilot/jobs":
                payload = self.server.service.procurement_batch_pilot_start(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "job": payload}, 202)
                return
            if self.path == "/api/procurement-batch-pilot/jobs/cancel":
                request = read_json(self)
                payload = self.server.service.procurement_batch_pilot_cancel(  # type: ignore[attr-defined]
                    str(request.get("job_id") or "").strip()
                )
                json_response(self, {"ok": True, "job": payload})
                return
            if self.path == "/api/procurement-batch-pilot/review":
                payload = self.server.service.procurement_batch_review_save(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, **payload})
                return
            if self.path == "/api/procurement-batch-pilot/review/freeze":
                payload = self.server.service.procurement_batch_review_freeze(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "release": payload})
                return
            if self.path == "/api/tariff-extraction/jobs":
                payload = self.server.service.tariff_extraction_start(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "job": payload}, 202)
                return
            if self.path == "/api/tariff-extraction/jobs/cancel":
                request = read_json(self)
                payload = self.server.service.tariff_extraction_cancel(  # type: ignore[attr-defined]
                    str(request.get("job_id") or "").strip()
                )
                json_response(self, {"ok": True, "job": payload})
                return
            if self.path == "/api/tariff-declaration/jobs":
                payload = self.server.service.tariff_declaration_start(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "job": payload}, 202)
                return
            if self.path == "/api/tariff-declaration/jobs/cancel":
                request = read_json(self)
                payload = self.server.service.tariff_declaration_cancel(  # type: ignore[attr-defined]
                    str(request.get("job_id") or "").strip()
                )
                json_response(self, {"ok": True, "job": payload})
                return
            if self.path == "/api/material-intake/drafts":
                payload = self.server.service.prepare_material_intake_drafts(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "drafts": payload})
                return
            if self.path == "/api/material-intake/drafts/revise":
                payload = self.server.service.revise_material_intake_drafts(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "drafts": payload})
                return
            if self.path == "/api/material-intake/drafts/confirm":
                payload = self.server.service.confirm_material_intake_drafts(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": not payload.get("failed"), "execution": payload})
                return
            if self.path == "/api/material-intake/confirm-alias":
                payload = self.server.service.confirm_material_alias(read_json(self))  # type: ignore[attr-defined]
                json_response(self, {"ok": True, "alias": payload})
                return
            if self.path not in {"/api/agent", "/api/agent/turn"}:
                json_response(self, {"ok": False, "error": "not_found"}, 404)
                return
            response = self.server.service.run(read_json(self))  # type: ignore[attr-defined]
            json_response(self, {"ok": response.get("status") != "failed", "result": response})
        except PermissionError as exc:
            json_response(self, {"ok": False, "error": str(exc)}, 403)
        except BusinessInputError as exc:
            json_response(
                self,
                {
                    "ok": False,
                    "error": str(exc),
                    "error_code": exc.error_code,
                    "field_path": exc.field_path,
                },
                422,
            )
        except (ValueError, json.JSONDecodeError) as exc:
            json_response(self, {"ok": False, "error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover - local service boundary
            json_response(self, {"ok": False, "error": str(exc)}, 500)

    def log_message(self, format: str, *args: Any) -> None:
        stream = sys.stderr
        if stream is None:
            return
        try:
            stream.write("[agent-workbench] " + format % args + "\n")
        except (OSError, ValueError):
            # Detached/hidden Windows launches can inherit a closed stderr.
            # Request logging must never prevent the HTTP response itself.
            return


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
    if not MATERIAL_ITEM_LAB_PATH.exists():
        raise FileNotFoundError(MATERIAL_ITEM_LAB_PATH)
    if not MATERIAL_INTAKE_LAB_PATH.exists():
        raise FileNotFoundError(MATERIAL_INTAKE_LAB_PATH)
    if not MATERIAL_MARKETPLACE_PATH.exists():
        raise FileNotFoundError(MATERIAL_MARKETPLACE_PATH)
    if not PROCUREMENT_BATCH_PILOT_PATH.exists():
        raise FileNotFoundError(PROCUREMENT_BATCH_PILOT_PATH)
    if not TARIFF_EXTRACTION_LAB_PATH.exists():
        raise FileNotFoundError(TARIFF_EXTRACTION_LAB_PATH)
    if not TARIFF_DECLARATION_LAB_PATH.exists():
        raise FileNotFoundError(TARIFF_DECLARATION_LAB_PATH)
    if not TARIFF_TAXONOMY_BROWSER_PATH.exists():
        raise FileNotFoundError(TARIFF_TAXONOMY_BROWSER_PATH)
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
