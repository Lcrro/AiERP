from __future__ import annotations

from datetime import date, timedelta
import os
from pathlib import Path
from typing import Any, Callable, Protocol

from nexterp_agent.agent_runtime.credentials import load_user_credentials
from nexterp_agent.agent_runtime.operation_reference_data import OperationReferenceDataCatalog
from nexterp_agent.agent_runtime.tool_access import make_tool_access_policy
from nexterp_agent.agent_runtime.tool_gateway import ToolGateway, ToolSession
from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.item_master.release_resolver import normalize_text

from .catalog import CapabilityCatalogRepository, ExternalIdentity
from .compiler import CatalogEvaluation, OperationCompilerRegistry
from .models import (
    CapabilitySearchRequest,
    ExecuteOperationRequest,
    GuideLoadRequest,
    PrepareOperationRequest,
    RequestIdentity,
)


ROOT = Path(__file__).resolve().parents[3]
MATERIAL_REQUEST_OPERATION_ID = "op.material_request.create"


class CatalogRepositoryLike(Protocol):
    def search_nodes(self, query: str, *, module: str | None = None, limit: int = 5) -> list[dict[str, Any]]: ...
    def load_guides(self, node_ids: list[str]) -> list[dict[str, Any]]: ...
    def operation_bundle(self, operation_id: str) -> dict[str, Any]: ...
    def current_revision(self) -> str: ...
    def resolve_identity(self, external_subject: str, agent_id: str = "") -> ExternalIdentity: ...
    def create_pending(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_pending(self, pending_id: str, *, for_update: bool = False) -> dict[str, Any]: ...
    def claim_pending(self, pending_id: str, *, identity: ExternalIdentity, session_key: str) -> dict[str, Any]: ...
    def finish_pending(self, pending_id: str, *, status: str, result: dict[str, Any]) -> dict[str, Any]: ...


class CapabilityManualService:
    """Safe boundary between an external conversational agent and ERPNext."""

    def __init__(
        self,
        repository: CatalogRepositoryLike,
        *,
        reference_data: OperationReferenceDataCatalog | None = None,
        client_factory: Callable[[str], ERPNextClient] | None = None,
        compiler_registry: OperationCompilerRegistry | None = None,
    ) -> None:
        self.repository = repository
        self.reference_data = reference_data or OperationReferenceDataCatalog(ROOT)
        self.client_factory = client_factory or self._default_client_factory
        self.compiler_registry = compiler_registry or OperationCompilerRegistry()

    def search(self, request: CapabilitySearchRequest, identity_request: RequestIdentity) -> dict[str, Any]:
        identity = self._identity(identity_request)
        cards = self.repository.search_nodes(request.query, module=request.module, limit=request.limit)
        allowed = [card for card in cards if self._node_allowed(card, identity)]
        return {
            "status": "found" if allowed else "not_found",
            "catalog_revision": self.repository.current_revision(),
            "cards": allowed[: request.limit],
        }

    def load_guides(self, request: GuideLoadRequest, identity_request: RequestIdentity) -> dict[str, Any]:
        identity = self._identity(identity_request)
        guides = self.repository.load_guides(request.node_ids)
        for guide in guides:
            if not self._node_allowed(guide, identity):
                raise PermissionError(f"当前岗位不能加载该业务能力：{guide['node_id']}")
        return {
            "status": "loaded",
            "catalog_revision": self.repository.current_revision(),
            "guides": guides,
        }

    def prepare(self, request: PrepareOperationRequest, identity_request: RequestIdentity) -> dict[str, Any]:
        identity = self._identity(identity_request)
        bundle = self.repository.operation_bundle(request.operation_id)
        if not self._operation_allowed(bundle, identity):
            raise PermissionError("当前岗位不能准备这个业务操作")
        if request.operation_id != MATERIAL_REQUEST_OPERATION_ID:
            raise ValueError("当前试验只支持创建材料申请草稿")

        resolution = self._resolve_material_request(request, identity)
        if resolution["status"] != "resolved":
            return {
                **resolution,
                "operation_id": request.operation_id,
                "catalog_revision": self.repository.current_revision(),
            }

        facts = resolution["facts"]
        evaluation = self.compiler_registry.compile(bundle, facts)
        if not evaluation.tool_call:
            return {
                "status": "needs_input",
                "operation_id": request.operation_id,
                "catalog_revision": self.repository.current_revision(),
                "missing": evaluation.missing,
                "invalid": evaluation.invalid,
                "blocked": evaluation.blocked,
                "fields": evaluation.slots,
                "questions": self._questions_for_evaluation(evaluation),
            }

        project_code = str(resolution["project_code"])
        summary = self._confirmation_summary(facts, bundle)
        pending = self.repository.create_pending(
            operation_id=request.operation_id,
            identity=identity,
            project_code=project_code,
            session_key=identity_request.session_key,
            request_id=request.request_id,
            tool_call=evaluation.tool_call,
            summary=summary,
        )
        return {
            "status": "needs_confirmation",
            "operation_id": request.operation_id,
            "catalog_revision": pending["catalog_revision"],
            "pending_id": pending["pending_id"],
            "expires_at": pending["expires_at"].isoformat(),
            "summary": summary,
            "resolved": resolution["resolved"],
        }

    def execute(self, request: ExecuteOperationRequest, identity_request: RequestIdentity) -> dict[str, Any]:
        identity = self._identity(identity_request)
        pending = self.repository.claim_pending(
            request.pending_id,
            identity=identity,
            session_key=identity_request.session_key,
        )
        if pending["status"] == "completed":
            return self._public_pending(pending)
        try:
            bundle = self.repository.operation_bundle(pending["operation_id"])
            if not self._operation_allowed(bundle, identity):
                raise PermissionError("当前岗位已无权执行该操作。")

            gateway = self._gateway(identity)
            tool_result = gateway.execute(pending["tool_call"], origin="agent")
            result_payload = tool_result.to_dict()
            if not tool_result.ok:
                completed = self.repository.finish_pending(request.pending_id, status="failed", result=result_payload)
                return self._public_pending(completed)

            readback = self._readback(gateway, tool_result.data)
            if not readback.get("ok"):
                failure = {
                    "ok": False,
                    "error_type": "readback_error",
                    "user_message": "ERPNext 已返回写入结果，但回读校验失败，请人工核查。",
                    "write_result": result_payload,
                    "readback": readback,
                }
                completed = self.repository.finish_pending(request.pending_id, status="failed", result=failure)
                return self._public_pending(completed)

            verified = {
                "ok": True,
                "write_result": result_payload,
                "readback": readback,
                "document": readback.get("data"),
            }
            completed = self.repository.finish_pending(request.pending_id, status="completed", result=verified)
            return self._public_pending(completed)
        except PermissionError as exc:
            failure = {"ok": False, "error_type": "permission_error", "user_message": str(exc)}
            self.repository.finish_pending(request.pending_id, status="failed", result=failure)
            raise
        except Exception as exc:
            failure = {
                "ok": False,
                "error_type": "execution_error",
                "user_message": "执行过程中发生异常，未继续重试。请检查服务状态后重新准备操作。",
                "debug": {"exception_type": type(exc).__name__, "detail": str(exc)},
            }
            completed = self.repository.finish_pending(request.pending_id, status="failed", result=failure)
            return self._public_pending(completed)

    def operation(self, pending_id: str, identity_request: RequestIdentity) -> dict[str, Any]:
        identity = self._identity(identity_request)
        pending = self.repository.get_pending(pending_id)
        if pending["employee_user"] != identity.employee_user or pending["external_subject"] != identity.external_subject:
            raise PermissionError("无权读取这个待确认动作")
        if pending["agent_id"] != identity.agent_id or pending["session_key"] != identity_request.session_key:
            raise PermissionError("待确认动作不属于当前 OpenClaw 会话")
        return self._public_pending(pending)

    def _resolve_material_request(self, request: PrepareOperationRequest, identity: ExternalIdentity) -> dict[str, Any]:
        project_text = str(request.project or identity.default_project or "").strip()
        if not project_text:
            return {"status": "needs_input", "questions": ["这批材料属于哪个项目？"], "missing": ["project"]}
        project_options = self.reference_data.options("project", query=project_text)
        project_option = exact_or_unique_option(project_options, project_text)
        if not project_option:
            return {
                "status": "needs_choice" if project_options else "blocked",
                "entity": "project",
                "questions": ["请选择材料归属项目。"] if project_options else ["没有找到可用项目，请联系管理员检查项目主数据。"],
                "candidates": project_options[:5],
            }
        project_code = str(project_option.get("source_code") or project_text)
        if identity.allowed_projects and project_code not in identity.allowed_projects:
            raise PermissionError("当前员工无权操作该项目")

        warehouse_options = self.reference_data.options(
            "warehouse", query=str(request.warehouse or ""), project=project_code,
        )
        warehouse_option = exact_or_unique_option(warehouse_options, str(request.warehouse or ""))
        if not warehouse_option and not request.warehouse:
            project_warehouses = [
                option for option in warehouse_options
                if str(option.get("project") or "") == project_code
            ]
            if len(project_warehouses) == 1:
                warehouse_option = project_warehouses[0]
        if not warehouse_option:
            return {
                "status": "needs_choice" if warehouse_options else "blocked",
                "entity": "warehouse",
                "questions": ["请选择材料要送到的项目仓库。"] if warehouse_options else ["项目没有可用仓库，请先维护仓库主数据。"],
                "candidates": warehouse_options[:5],
            }

        schedule_date = parse_schedule_date(request.schedule_date or request.schedule_text)
        if not schedule_date:
            return {"status": "needs_input", "questions": ["这些材料最迟哪天需要到位？"], "missing": ["schedule_date"]}

        resolved_items = []
        choices = []
        for index, item in enumerate(request.items):
            query = item.item_code or item.raw_item_text or ""
            candidates = self.reference_data.options("item", query=query)
            selected = exact_or_unique_option(candidates, query, value_key="value")
            if not selected:
                choices.append({
                    "item_index": index,
                    "raw_item_text": item.raw_item_text,
                    "candidates": candidates[:5],
                })
                continue
            uom_options = self.reference_data.options("uom", item_code=str(selected["value"]))
            requested_uom = str(item.uom or "").strip()
            allowed_uoms = {
                normalize_text(option.get("value")): option.get("value")
                for option in uom_options if option.get("value")
            }
            if requested_uom and normalize_text(requested_uom) not in allowed_uoms:
                choices.append({
                    "item_index": index,
                    "raw_item_text": item.raw_item_text,
                    "item_code": selected["value"],
                    "entity": "uom",
                    "requested_uom": requested_uom,
                    "candidates": uom_options,
                })
                continue
            uom = (
                allowed_uoms.get(normalize_text(requested_uom))
                or selected.get("purchase_uom")
                or selected.get("stock_uom")
            )
            if not uom and len(uom_options) == 1:
                uom = uom_options[0]["value"]
            if not uom:
                choices.append({
                    "item_index": index,
                    "raw_item_text": item.raw_item_text,
                    "item_code": selected["value"],
                    "entity": "uom",
                    "candidates": uom_options,
                })
                continue
            resolved_items.append({"item_code": selected["value"], "qty": item.qty, "uom": uom})
        if choices:
            return {
                "status": "needs_choice",
                "entity": "item",
                "questions": ["有物料无法唯一确定，请选择对应的标准物料。"],
                "choices": choices,
            }

        company_options = self.reference_data.options("company")
        if not company_options:
            return {"status": "blocked", "questions": ["没有可用公司账套，请联系管理员。"]}
        facts = {
            "context": {
                "company": company_options[0]["value"],
                "erpnext_project": project_option["value"],
                "warehouse": warehouse_option["value"],
            },
            "user": {"schedule_date": schedule_date},
            "items": resolved_items,
        }
        return {
            "status": "resolved",
            "facts": facts,
            "project_code": project_code,
            "resolved": {
                "company": company_options[0], "project": project_option,
                "warehouse": warehouse_option, "items": resolved_items,
            },
        }

    def _node_allowed(self, node: dict[str, Any], identity: ExternalIdentity) -> bool:
        node_id = str(node.get("node_id") or "")
        if node_id in {"module.buying", "cap.material_request"}:
            bundle = self.repository.operation_bundle(MATERIAL_REQUEST_OPERATION_ID)
            return self._operation_allowed(bundle, identity)
        if node.get("node_type") == "slot":
            return self._operation_allowed(self.repository.operation_bundle(MATERIAL_REQUEST_OPERATION_ID), identity)
        if node_id == MATERIAL_REQUEST_OPERATION_ID:
            return self._operation_allowed(self.repository.operation_bundle(node_id), identity)
        return False

    @staticmethod
    def _operation_allowed(bundle: dict[str, Any], identity: ExternalIdentity) -> bool:
        policy = make_tool_access_policy(identity.profile_name)
        return policy.decide(str(bundle["operation"]["tool_name"]), origin="agent").allowed

    def _identity(self, request: RequestIdentity) -> ExternalIdentity:
        return self.repository.resolve_identity(request.external_subject, request.agent_id)

    def _gateway(self, identity: ExternalIdentity) -> ToolGateway:
        client = self.client_factory(identity.employee_user)
        policy = make_tool_access_policy(identity.profile_name)
        return ToolGateway(
            ERPNextAdapter(client),
            ToolSession(user=identity.employee_user, policy=policy, verify_erpnext_identity=True),
        )

    def _default_client_factory(self, user: str) -> ERPNextClient:
        profile = os.getenv("NEXTERP_CAPABILITY_ERP_PROFILE", "CIVIL").upper()
        credentials = load_user_credentials(user)
        return ERPNextClient(
            os.environ[f"NEXTERP_{profile}_BASE_URL"],
            credentials["api_key"], credentials["api_secret"],
            host_header=os.getenv(f"NEXTERP_{profile}_HOST_HEADER"), timeout=90,
        )

    @staticmethod
    def _confirmation_summary(facts: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
        return {
            "title": bundle["operation"]["label"],
            "project": facts["context"]["erpnext_project"],
            "warehouse": facts["context"]["warehouse"],
            "company": facts["context"]["company"],
            "schedule_date": facts["user"]["schedule_date"],
            "items": facts["items"],
            "effect": "将在 ERPNext 中创建一张采购类型材料申请草稿。",
        }

    @staticmethod
    def _questions_for_evaluation(evaluation: CatalogEvaluation) -> list[str]:
        by_id = {row["slot_id"]: row for row in evaluation.slots}
        return [
            f"请补充或修正：{by_id[slot_id]['label']}。{by_id[slot_id]['reason']}"
            for slot_id in [*evaluation.missing, *evaluation.invalid, *evaluation.blocked]
            if slot_id in by_id
        ]

    def _readback(self, gateway: ToolGateway, data: Any) -> dict[str, Any]:
        name = data.get("name") if isinstance(data, dict) else None
        doctype = data.get("doctype") if isinstance(data, dict) else None
        if not name or not doctype:
            return {"ok": False, "error": "write result did not contain document identity"}
        result = gateway.adapter.client.get_document(str(doctype), str(name))
        return result.to_dict()

    @staticmethod
    def _public_pending(pending: dict[str, Any]) -> dict[str, Any]:
        return {
            "pending_id": pending["pending_id"], "operation_id": pending["operation_id"],
            "status": pending["status"], "summary": pending["summary"],
            "catalog_revision": pending["catalog_revision"],
            "expires_at": pending["expires_at"].isoformat(), "result": pending.get("result"),
        }


def parse_schedule_date(value: str | None, *, today: date | None = None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    base = today or date.today()
    relative = {"今天": 0, "明天": 1, "后天": 2, "大后天": 3}
    if text in relative:
        return (base + timedelta(days=relative[text])).isoformat()
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def exact_or_unique_option(
    options: list[dict[str, Any]],
    query: str,
    *,
    value_key: str = "value",
) -> dict[str, Any] | None:
    needle = normalize_text(query)
    exact = [
        row for row in options
        if needle and needle in {
            normalize_text(row.get(value_key)),
            normalize_text(row.get("label")),
            normalize_text(row.get("source_code")),
        }
    ]
    if len(exact) == 1:
        return exact[0]
    return options[0] if len(options) == 1 else None
