from __future__ import annotations

from datetime import date, timedelta
import os
from pathlib import Path
from typing import Any, Callable, Protocol

from nexterp_agent.agent_runtime.business_capabilities.procurement import (
    CapabilityCompilationError,
    PreparedBusinessAction,
    canonical_tool_call_hash,
    verify_procurement_result,
)
from nexterp_agent.agent_runtime.credentials import load_user_credentials
from nexterp_agent.agent_runtime.operation_reference_data import OperationReferenceDataCatalog
from nexterp_agent.agent_runtime.tool_access import make_tool_access_policy
from nexterp_agent.agent_runtime.tool_gateway import ToolGateway, ToolSession
from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.item_master.release_resolver import normalize_text
from nexterp_agent.item_master.type_classifier import MaterialTypeClassifier

from .catalog import CapabilityCatalogRepository, ExternalIdentity
from .compiler import CatalogEvaluation, OperationCompilerRegistry
from .context import AgentContextBuilder
from .context_models import WorkContextLoadRequest
from .models import (
    CapabilitySearchRequest,
    ExecuteOperationRequest,
    GuideLoadRequest,
    PrepareOperationRequest,
    RequestIdentity,
)
from .procurement_catalog import (
    CAPABILITY_OPERATION_IDS,
    OPERATION_BY_ID,
    PROCUREMENT_OPERATION_IDS,
    operation_capability,
    operation_goal,
)


ROOT = Path(__file__).resolve().parents[3]
MATERIAL_REQUEST_OPERATION_ID = "op.material_request.create"
ALL_OPERATION_IDS = (MATERIAL_REQUEST_OPERATION_ID, *PROCUREMENT_OPERATION_IDS)


class CatalogRepositoryLike(Protocol):
    def search_nodes(self, query: str, *, module: str | None = None, limit: int = 5) -> list[dict[str, Any]]: ...
    def load_guides(self, node_ids: list[str]) -> list[dict[str, Any]]: ...
    def operation_bundle(self, operation_id: str) -> dict[str, Any]: ...
    def current_revision(self) -> str: ...
    def resolve_identity(self, external_subject: str, agent_id: str = "") -> ExternalIdentity: ...
    def resolve_identity_for_session(self, session_key: str, agent_id: str = "") -> ExternalIdentity: ...
    def create_pending(self, **kwargs: Any) -> dict[str, Any]: ...
    def get_pending(self, pending_id: str, *, for_update: bool = False) -> dict[str, Any]: ...
    def claim_pending(self, pending_id: str, *, identity: ExternalIdentity, session_key: str) -> dict[str, Any]: ...
    def finish_pending(self, pending_id: str, *, status: str, result: dict[str, Any]) -> dict[str, Any]: ...
    def role_context(self, role_code: str, topics: list[str]) -> dict[str, Any]: ...
    def session_context(self, identity: ExternalIdentity, session_key: str) -> dict[str, Any]: ...
    def mark_context_loaded(self, identity: ExternalIdentity, session_key: str, topics: list[str]) -> None: ...
    def record_search_result(self, identity: ExternalIdentity, session_key: str, *, found: bool) -> int: ...


class CapabilityManualService:
    """Safe boundary between an external conversational agent and ERPNext."""

    def __init__(
        self,
        repository: CatalogRepositoryLike,
        *,
        reference_data: OperationReferenceDataCatalog | None = None,
        client_factory: Callable[[str], ERPNextClient] | None = None,
        compiler_registry: OperationCompilerRegistry | None = None,
        material_classifier: MaterialTypeClassifier | None = None,
    ) -> None:
        self.repository = repository
        self.reference_data = reference_data or OperationReferenceDataCatalog(ROOT)
        self.client_factory = client_factory or self._default_client_factory
        self.compiler_registry = compiler_registry or OperationCompilerRegistry()
        self.material_classifier = material_classifier or MaterialTypeClassifier()
        self.context_builder = AgentContextBuilder(ROOT)

    def search(self, request: CapabilitySearchRequest, identity_request: RequestIdentity) -> dict[str, Any]:
        identity = self._identity(identity_request)
        session = self._session_context(identity, identity_request.session_key)
        # Legacy callers without a registered trusted session keep the old discovery behavior.
        intent_mode = str(session.get("intent_mode") or request.intent_mode or "write")
        cards = self.repository.search_nodes(request.query, module=request.module, limit=request.limit)
        allowed = [
            card for card in cards
            if self._mode_allowed(card, intent_mode) and self._node_allowed(card, identity)
        ]
        record_search = getattr(self.repository, "record_search_result", None)
        misses = record_search(identity, identity_request.session_key, found=bool(allowed)) if record_search else 0
        if not allowed and misses >= 2:
            return {
                "status": "unsupported",
                "catalog_revision": self.repository.current_revision(),
                "intent_mode": intent_mode,
                "message": "当前说明书中没有与该请求匹配的合法能力，我不会改用语义相近的其他操作。",
                "cards": [],
            }
        return {
            "status": "found" if allowed else "not_found",
            "catalog_revision": self.repository.current_revision(),
            "intent_mode": intent_mode,
            "cards": allowed[: request.limit],
        }

    def load_context(self, request: WorkContextLoadRequest, identity_request: RequestIdentity) -> dict[str, Any]:
        identity = self._identity(identity_request)
        session = self._session_context(identity, identity_request.session_key)
        envelope = self.context_builder.build(identity, session)
        role_context = self.repository.role_context(envelope.identity.role_code, request.topics)
        dynamic: dict[str, Any] = {}
        if "project" in request.topics:
            dynamic["project"] = envelope.workplace.model_dump(mode="json")
        if "recent_documents" in request.topics:
            dynamic["recent_documents"] = self._recent_documents(identity, request.query)
        if "inbox" in request.topics:
            dynamic["inbox"] = self._workflow_inbox(identity)
        self.repository.mark_context_loaded(identity, identity_request.session_key, request.topics)
        return {
            "status": "loaded",
            "catalog_revision": self.repository.current_revision(),
            "agent_context": envelope.model_dump(mode="json"),
            "role_context": role_context,
            "dynamic_context": dynamic,
            "loaded_topics": request.topics,
        }

    def load_guides(self, request: GuideLoadRequest, identity_request: RequestIdentity) -> dict[str, Any]:
        identity = self._identity(identity_request)
        guides = self.repository.load_guides(request.node_ids)
        for guide in guides:
            if not self._node_allowed(guide, identity):
                raise PermissionError(f"当前岗位不能加载该业务能力：{guide['node_id']}")
            guide["relations"] = [
                relation for relation in guide.get("relations") or []
                if self._node_allowed(relation, identity)
            ]
        return {
            "status": "loaded",
            "catalog_revision": self.repository.current_revision(),
            "guides": guides,
        }

    def prepare(self, request: PrepareOperationRequest, identity_request: RequestIdentity) -> dict[str, Any]:
        identity = self._identity(identity_request)
        if request.operation_id == "op.material.search":
            return self._search_materials(request, identity, identity_request)
        if request.operation_id == "op.material.classify":
            return self._classify_material(request)
        if request.operation_id == "op.document.search":
            return self._search_visible_documents(request, identity, identity_request)
        bundle = self.repository.operation_bundle(request.operation_id)
        if not self._operation_allowed(bundle, identity):
            raise PermissionError("当前岗位不能准备这个业务操作")
        if request.operation_id == MATERIAL_REQUEST_OPERATION_ID:
            resolution = self._resolve_material_request(request, identity)
        elif request.operation_id in OPERATION_BY_ID:
            resolution = self._resolve_procurement_operation(request, identity)
        else:
            raise ValueError(f"当前说明书服务尚不支持操作 {request.operation_id}")
        if resolution["status"] != "resolved":
            return {
                **resolution,
                "operation_id": request.operation_id,
                "catalog_revision": self.repository.current_revision(),
            }

        facts = resolution["facts"]
        try:
            evaluation = self.compiler_registry.compile(bundle, facts)
        except CapabilityCompilationError as exc:
            return {
                "status": "needs_input",
                "operation_id": request.operation_id,
                "catalog_revision": self.repository.current_revision(),
                "questions": list(exc.questions) or [str(exc)],
                "error": str(exc),
            }
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
        summary = self._confirmation_summary(facts, bundle, evaluation.tool_call)
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

            readback = self._verify_readback(gateway, pending, result_payload)
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
                "document": readback.get("document"),
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
        if not request.items:
            return {
                "status": "needs_input",
                "questions": ["请说明需要的物料、数量和单位。"],
                "missing": ["items"],
            }
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

    def _resolve_procurement_operation(
        self,
        request: PrepareOperationRequest,
        identity: ExternalIdentity,
    ) -> dict[str, Any]:
        seed = OPERATION_BY_ID[request.operation_id]
        if len(request.source_documents) != 1:
            expected = "、".join(seed.source_doctypes)
            return {
                "status": "needs_input",
                "questions": [f"请指定一张要处理的{expected}单号。"],
                "missing": ["source_documents"],
            }
        reference = request.source_documents[0]
        if reference.doctype not in seed.source_doctypes:
            return {
                "status": "blocked",
                "questions": [
                    f"{seed.operation_label} 需要 {seed.source_doctypes[0]}，不能使用 {reference.doctype}。"
                ],
            }

        client = self._verified_client(identity)
        source_result = client.get_document(reference.doctype, reference.name)
        if not source_result.ok or not isinstance(source_result.data, dict):
            if source_result.error_type in {"permission_error", "auth_error"}:
                raise PermissionError(source_result.user_message or "当前员工无权读取来源单据")
            return {
                "status": "blocked",
                "questions": [source_result.user_message or f"无法读取 {reference.doctype} {reference.name}。"],
                "source_document": reference.model_dump(),
            }
        snapshot = dict(source_result.data)
        snapshot.setdefault("doctype", reference.doctype)
        snapshot.setdefault("name", reference.name)

        supplier_queries = list(request.suppliers)
        if request.supplier:
            supplier_queries.insert(0, request.supplier)
        needs_suppliers = seed.goal in {
            "create_rfq_from_material_request",
            "create_supplier_quotation_from_rfq",
        }
        if needs_suppliers and not supplier_queries:
            wording = "至少一家供应商" if seed.goal == "create_rfq_from_material_request" else "报价供应商"
            return {
                "status": "needs_input",
                "questions": [f"请选择{wording}。"],
                "missing": ["suppliers"],
            }
        resolved_suppliers: list[str] = []
        supplier_choices: list[dict[str, Any]] = []
        for query in dict.fromkeys(supplier_queries):
            options = self.reference_data.options("supplier", query=query)
            selected = exact_or_unique_option(options, query)
            if selected:
                resolved_suppliers.append(str(selected["value"]))
            else:
                supplier_choices.append({"query": query, "candidates": options[:5]})
        if supplier_choices:
            return {
                "status": "needs_choice" if any(row["candidates"] for row in supplier_choices) else "blocked",
                "entity": "supplier",
                "questions": ["有供应商无法唯一确定，请从真实供应商中选择。"],
                "choices": supplier_choices,
            }
        if seed.goal == "create_supplier_quotation_from_rfq" and len(resolved_suppliers) != 1:
            return {
                "status": "needs_choice",
                "entity": "supplier",
                "questions": ["一张供应商报价只能对应一家供应商，请选择其中一家。"],
                "candidates": [{"value": value, "label": value} for value in resolved_suppliers],
            }

        schedule_date = parse_schedule_date(request.schedule_date or request.schedule_text)
        if (request.schedule_date or request.schedule_text) and not schedule_date:
            return {
                "status": "needs_input",
                "questions": ["日期无法确定，请使用明确日期，例如 2026-08-06。"],
                "missing": ["schedule_date"],
            }
        for field_name, value in (("posting_date", request.posting_date), ("valid_till", request.valid_till)):
            if value and not _is_iso_date(value):
                return {
                    "status": "needs_input",
                    "questions": [f"{field_name} 请使用 YYYY-MM-DD。"],
                    "invalid": [field_name],
                }

        project_scope = self._resolve_project_scope(request.project, snapshot, identity)
        if project_scope["status"] != "resolved":
            return project_scope
        project_code = str(project_scope["project_code"])

        warehouse_value = str(request.warehouse or "").strip()
        if warehouse_value:
            options = self.reference_data.options("warehouse", query=warehouse_value, project=project_code)
            selected = exact_or_unique_option(options, warehouse_value)
            if not selected:
                return {
                    "status": "needs_choice" if options else "blocked",
                    "entity": "warehouse",
                    "questions": ["请选择真实收货仓库。"],
                    "candidates": options[:5],
                }
            warehouse_value = str(selected["value"])

        normalized_items, item_choices = self._source_operation_items(
            request.items,
            snapshot,
            project_code=project_code,
        )
        if item_choices:
            return {
                "status": "needs_choice",
                "entity": "source_item",
                "questions": ["部分物料无法唯一对应到来源单据明细，请选择具体行。"],
                "choices": item_choices,
            }

        company = str(snapshot.get("company") or "")
        if not company:
            companies = self.reference_data.options("company")
            company = str(companies[0]["value"]) if len(companies) == 1 else ""
        source_project = str(project_scope.get("erpnext_project") or "")
        intent = {
            "source_documents": [{"doctype": reference.doctype, "name": reference.name}],
            "items": normalized_items,
            "suppliers": resolved_suppliers,
            "company": company or None,
            "project": source_project or None,
            "warehouse": warehouse_value or None,
            "schedule_date": schedule_date,
            "valid_till": request.valid_till,
            "posting_date": request.posting_date,
            "currency": request.currency,
            "message": request.message,
            "full_return": request.full_return,
        }
        facts = {
            "today": date.today(),
            "runtime_context": {
                "company": company or None,
                "project": source_project or None,
                "warehouse": warehouse_value or None,
            },
            "source_documents": [snapshot],
            "intent": intent,
        }
        return {
            "status": "resolved",
            "facts": facts,
            "project_code": project_code,
            "resolved": {
                "source_documents": [{
                    "doctype": snapshot.get("doctype"),
                    "name": snapshot.get("name"),
                    "docstatus": snapshot.get("docstatus"),
                    "status": snapshot.get("status"),
                }],
                "suppliers": resolved_suppliers,
                "project": project_scope,
                "warehouse": warehouse_value or None,
                "items": normalized_items,
            },
        }

    def _resolve_project_scope(
        self,
        requested_project: str | None,
        snapshot: dict[str, Any],
        identity: ExternalIdentity,
    ) -> dict[str, Any]:
        source_projects = list(dict.fromkeys(
            str(value).strip()
            for value in [
                snapshot.get("project"),
                *[row.get("project") for row in snapshot.get("items") or [] if isinstance(row, dict)],
            ]
            if str(value or "").strip()
        ))
        resolved_sources: list[dict[str, Any]] = []
        for source_project in source_projects:
            options = self.reference_data.options("project", query=source_project)
            selected_source = exact_or_unique_option(options, source_project)
            if not selected_source:
                return {
                    "status": "blocked",
                    "entity": "project",
                    "questions": [f"来源单据中的项目 {source_project} 无法映射到受管项目主数据。"],
                }
            source_code = str(selected_source.get("source_code") or source_project)
            if identity.allowed_projects and source_code not in identity.allowed_projects:
                raise PermissionError("当前员工无权操作来源单据所属项目")
            resolved_sources.append(selected_source)

        selected: dict[str, Any] | None = None
        project_text = str(requested_project or "").strip()
        if project_text:
            options = self.reference_data.options("project", query=project_text)
            selected = exact_or_unique_option(options, project_text)
        elif len(resolved_sources) == 1:
            selected = resolved_sources[0]
            project_text = str(selected.get("value") or selected.get("label") or "")
        elif len(resolved_sources) > 1:
            return {
                "status": "blocked",
                "entity": "project",
                "questions": ["来源单据包含多个项目，请先按项目拆分后再继续。"],
                "candidates": resolved_sources[:5],
            }

        if project_text and not selected:
            return {
                "status": "needs_choice" if options else "blocked",
                "entity": "project",
                "questions": ["请选择当前业务所属的真实项目。"],
                "candidates": options[:5],
            }
        if selected and resolved_sources:
            selected_code = str(selected.get("source_code") or "")
            source_codes = {str(row.get("source_code") or "") for row in resolved_sources}
            if selected_code not in source_codes:
                return {
                    "status": "blocked",
                    "entity": "project",
                    "questions": ["指定项目与来源单据项目不一致，不能转换。"],
                }

        project_code = str((selected or {}).get("source_code") or identity.default_project)
        if not project_code:
            return {
                "status": "needs_input",
                "entity": "project",
                "questions": ["请指定当前业务所属项目。"],
            }
        if identity.allowed_projects and project_code not in identity.allowed_projects:
            raise PermissionError("当前员工无权操作来源单据所属项目")
        return {
            "status": "resolved",
            "project_code": project_code,
            "erpnext_project": (selected or {}).get("value"),
            "label": (selected or {}).get("label") or project_text,
        }

    def _source_operation_items(
        self,
        items: list[Any],
        snapshot: dict[str, Any],
        *,
        project_code: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        source_rows = [dict(row) for row in snapshot.get("items") or [] if isinstance(row, dict)]
        by_name = {str(row.get("name") or ""): row for row in source_rows if row.get("name")}
        normalized: list[dict[str, Any]] = []
        choices: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            payload = item.model_dump(exclude_none=True)
            source_row = str(payload.get("source_row") or "")
            matches: list[dict[str, Any]] = []
            if source_row and source_row in by_name:
                matches = [by_name[source_row]]
            elif payload.get("item_code"):
                matches = [row for row in source_rows if str(row.get("item_code") or "") == payload["item_code"]]
            elif payload.get("raw_item_text"):
                needle = normalize_text(payload["raw_item_text"])
                matches = [
                    row for row in source_rows
                    if needle in {
                        normalize_text(row.get("item_code")),
                        normalize_text(row.get("item_name")),
                        normalize_text(row.get("description")),
                    }
                ]
            if len(matches) == 1:
                payload["source_row"] = matches[0].get("name")
                payload["item_code"] = matches[0].get("item_code")
            elif items:
                choices.append({
                    "item_index": index,
                    "query": payload.get("item_code") or payload.get("raw_item_text") or source_row,
                    "candidates": [
                        {
                            "value": row.get("name"),
                            "label": row.get("item_name") or row.get("item_code"),
                            "item_code": row.get("item_code"),
                            "qty": row.get("qty"),
                            "uom": row.get("uom") or row.get("stock_uom"),
                        }
                        for row in source_rows[:20]
                    ],
                })
                continue

            warehouse = str(payload.get("warehouse") or "").strip()
            if warehouse:
                warehouse_options = self.reference_data.options("warehouse", query=warehouse, project=project_code)
                selected = exact_or_unique_option(warehouse_options, warehouse)
                if not selected:
                    choices.append({
                        "item_index": index,
                        "entity": "warehouse",
                        "query": warehouse,
                        "candidates": warehouse_options[:5],
                    })
                    continue
                payload["warehouse"] = selected["value"]
            payload.pop("raw_item_text", None)
            normalized.append(payload)
        return normalized, choices

    def _node_allowed(self, node: dict[str, Any], identity: ExternalIdentity) -> bool:
        node_id = str(node.get("node_id") or "")
        if str(node.get("operation_mode") or "") in {"read", "analyze"}:
            return True
        if node_id == "module.buying":
            return any(
                self._operation_allowed(self.repository.operation_bundle(operation_id), identity)
                for operation_id in ALL_OPERATION_IDS
            )
        capability_operation = {
            "cap.material_request": MATERIAL_REQUEST_OPERATION_ID,
            **CAPABILITY_OPERATION_IDS,
        }.get(node_id)
        if capability_operation:
            return self._operation_allowed(self.repository.operation_bundle(capability_operation), identity)
        if node.get("node_type") == "slot":
            return any(
                self._operation_allowed(self.repository.operation_bundle(operation_id), identity)
                for operation_id in ALL_OPERATION_IDS
            )
        if node_id in ALL_OPERATION_IDS:
            return self._operation_allowed(self.repository.operation_bundle(node_id), identity)
        return False

    @staticmethod
    def _mode_allowed(node: dict[str, Any], intent_mode: str) -> bool:
        node_mode = str(node.get("operation_mode") or ("write" if node.get("is_write") else "read"))
        if intent_mode == "read":
            return node_mode == "read"
        if intent_mode == "analyze":
            return node_mode in {"read", "analyze"}
        return True

    def _search_materials(
        self,
        request: PrepareOperationRequest,
        identity: ExternalIdentity,
        identity_request: RequestIdentity,
    ) -> dict[str, Any]:
        session = self._session_context(identity, identity_request.session_key)
        query = str(request.query or "").strip()
        if not query:
            return {"status": "needs_input", "operation_id": request.operation_id,
                    "questions": ["请告诉我要查询的物料名称或规格。"]}
        candidates = self.reference_data.options("item", query=query)[: request.limit]
        item_codes = [str(row.get("value") or "") for row in candidates if row.get("value")]
        project_code = str(session.get("project_code") or identity.default_project or "")
        warehouses: list[dict[str, Any]] = []
        for accessible_project in dict.fromkeys([project_code, *identity.allowed_projects]):
            for warehouse in self.reference_data.options("warehouse", project=accessible_project):
                if warehouse.get("value") and not any(row.get("value") == warehouse.get("value") for row in warehouses):
                    warehouses.append(warehouse)
        warehouse_names = [str(row.get("value") or "") for row in warehouses if row.get("value")]
        inventory_by_item: dict[str, list[dict[str, Any]]] = {code: [] for code in item_codes}
        inventory_status = "available"
        if item_codes and warehouse_names:
            client = self._verified_client(identity)
            result = client.search_documents(
                "Bin",
                filters=[["item_code", "in", item_codes], ["warehouse", "in", warehouse_names]],
                fields=["item_code", "warehouse", "actual_qty", "reserved_qty", "projected_qty"],
                limit=min(500, len(item_codes) * max(1, len(warehouse_names))),
                order_by="item_code asc, warehouse asc",
            )
            if result.ok:
                rows = result.data if isinstance(result.data, list) else []
                for row in rows:
                    if isinstance(row, dict) and str(row.get("item_code") or "") in inventory_by_item:
                        inventory_by_item[str(row["item_code"])].append(row)
            else:
                inventory_status = "unavailable"
        enriched = []
        for row in candidates:
            code = str(row.get("value") or "")
            stocks = inventory_by_item.get(code, [])
            enriched.append({
                "item_code": code,
                "sku_name": row.get("label"),
                "required_specs": row.get("meta"),
                "stock_uom": row.get("stock_uom"),
                "purchase_uom": row.get("purchase_uom"),
                "score": row.get("score"),
                "match_reason": row.get("match_reason"),
                "inventory": stocks,
                "total_actual_qty": sum(float(stock.get("actual_qty") or 0) for stock in stocks),
            })
        return {
            "status": "completed",
            "operation_id": request.operation_id,
            "operation_mode": "read",
            "query": query,
            "project_code": project_code,
            "inventory_status": inventory_status,
            "candidates": enriched,
            "catalog_revision": self.repository.current_revision(),
        }

    def _classify_material(self, request: PrepareOperationRequest) -> dict[str, Any]:
        query = str(request.query or "").strip()
        result = self.material_classifier.classify(
            query,
            attributes=request.attributes,
            top_group_hint=str(request.top_group_hint or ""),
            material_family_hint=str(request.material_family_hint or ""),
            limit=request.limit,
        )
        return {
            **result.model_dump(mode="json"),
            "operation_id": request.operation_id,
            "operation_mode": "analyze",
            "catalog_revision": self.repository.current_revision(),
            "writes_erpnext": False,
        }

    def _search_visible_documents(
        self,
        request: PrepareOperationRequest,
        identity: ExternalIdentity,
        identity_request: RequestIdentity,
    ) -> dict[str, Any]:
        allowed = {
            "Material Request": ["name", "status", "workflow_state", "transaction_date", "schedule_date", "modified", "owner"],
            "Request for Quotation": ["name", "status", "transaction_date", "modified", "owner"],
            "Supplier Quotation": ["name", "status", "transaction_date", "valid_till", "modified", "owner"],
            "Purchase Order": ["name", "status", "transaction_date", "schedule_date", "modified", "owner"],
            "Purchase Receipt": ["name", "status", "posting_date", "modified", "owner"],
        }
        doctype = str(request.document_type or "Material Request")
        if doctype not in allowed:
            return {"status": "blocked", "operation_id": request.operation_id,
                    "message": "当前只读说明书尚未开放该单据类型。"}
        client = self._verified_client(identity)
        if request.document_name:
            result = client.get_document(doctype, request.document_name)
            rows = [result.data] if result.ok and isinstance(result.data, dict) else []
        else:
            filters: dict[str, Any] = {}
            if request.query:
                filters["name"] = ["like", f"%{request.query}%"]
            result = client.search_documents(
                doctype, filters=filters or None, fields=allowed[doctype],
                limit=request.limit, order_by="modified desc",
            )
            rows = result.data if result.ok and isinstance(result.data, list) else []
        if not result.ok:
            return {"status": "blocked", "operation_id": request.operation_id,
                    "message": result.user_message or "读取单据失败。"}
        return {"status": "completed", "operation_id": request.operation_id,
                "operation_mode": "read", "doctype": doctype, "documents": rows,
                "catalog_revision": self.repository.current_revision()}

    def _recent_documents(self, identity: ExternalIdentity, query: str | None) -> dict[str, Any]:
        client = self._verified_client(identity)
        rows: list[dict[str, Any]] = []
        for doctype in ("Material Request", "Purchase Order", "Purchase Receipt"):
            result = client.search_documents(doctype, fields=["name", "status", "modified", "owner"],
                                             limit=5, order_by="modified desc")
            if result.ok and isinstance(result.data, list):
                rows.extend({"doctype": doctype, **row} for row in result.data if isinstance(row, dict))
        rows.sort(key=lambda row: str(row.get("modified") or ""), reverse=True)
        return {"source": "ERPNext live", "documents": rows[:10]}

    def _workflow_inbox(self, identity: ExternalIdentity) -> dict[str, Any]:
        client = self._verified_client(identity)
        result = client.search_documents(
            "Workflow Action",
            filters={"user": identity.employee_user, "status": "Open"},
            fields=["name", "reference_doctype", "reference_name", "status", "creation"],
            limit=20, order_by="creation desc",
        )
        return {
            "source": "ERPNext live",
            "available": result.ok,
            "actions": result.data if result.ok and isinstance(result.data, list) else [],
            "message": None if result.ok else (result.user_message or "待办读取失败"),
        }

    @staticmethod
    def _operation_allowed(bundle: dict[str, Any], identity: ExternalIdentity) -> bool:
        policy = make_tool_access_policy(identity.profile_name)
        return policy.decide(str(bundle["operation"]["tool_name"]), origin="agent").allowed

    def _identity(self, request: RequestIdentity) -> ExternalIdentity:
        if ":workbench:" in request.session_key:
            resolver = getattr(self.repository, "resolve_identity_for_session", None)
            if resolver:
                return resolver(request.session_key, request.agent_id)
        return self.repository.resolve_identity(request.external_subject, request.agent_id)

    def _session_context(self, identity: ExternalIdentity, session_key: str) -> dict[str, Any]:
        loader = getattr(self.repository, "session_context", None)
        return loader(identity, session_key) if loader else {}

    def _gateway(self, identity: ExternalIdentity) -> ToolGateway:
        client = self._verified_client(identity)
        policy = make_tool_access_policy(identity.profile_name)
        return ToolGateway(
            ERPNextAdapter(client),
            ToolSession(user=identity.employee_user, policy=policy, verify_erpnext_identity=True),
        )

    def _verified_client(self, identity: ExternalIdentity) -> ERPNextClient:
        client = self.client_factory(identity.employee_user)
        logged_user = client.get_logged_user()
        if not logged_user.ok:
            raise PermissionError(logged_user.user_message or "无法核对 ERPNext 登录身份")
        actual = logged_user.data
        if isinstance(actual, dict):
            actual = actual.get("message") or actual.get("user") or actual.get("name")
        if str(actual or "").strip() != identity.employee_user:
            raise PermissionError("ERPNext 登录身份与当前员工不一致")
        return client

    def _default_client_factory(self, user: str) -> ERPNextClient:
        profile = os.getenv("NEXTERP_CAPABILITY_ERP_PROFILE", "CIVIL").upper()
        credentials = load_user_credentials(user)
        return ERPNextClient(
            os.environ[f"NEXTERP_{profile}_BASE_URL"],
            credentials["api_key"], credentials["api_secret"],
            host_header=os.getenv(f"NEXTERP_{profile}_HOST_HEADER"), timeout=90,
        )

    @staticmethod
    def _confirmation_summary(
        facts: dict[str, Any],
        bundle: dict[str, Any],
        tool_call: dict[str, Any],
    ) -> dict[str, Any]:
        operation_id = str(bundle["operation"]["operation_id"])
        arguments = dict(tool_call.get("arguments") or {})
        if operation_id == MATERIAL_REQUEST_OPERATION_ID:
            return {
                "title": bundle["operation"]["label"],
                "project": facts["context"]["erpnext_project"],
                "warehouse": facts["context"]["warehouse"],
                "company": facts["context"]["company"],
                "schedule_date": facts["user"]["schedule_date"],
                "items": facts["items"],
                "effect": "将在 ERPNext 中创建一张采购类型材料申请草稿。",
            }
        seed = OPERATION_BY_ID[operation_id]
        intent = dict(facts.get("intent") or {})
        return {
            "title": seed.operation_label,
            "source_documents": intent.get("source_documents") or [],
            "company": arguments.get("company") or facts.get("runtime_context", {}).get("company"),
            "project": facts.get("runtime_context", {}).get("project"),
            "warehouse": facts.get("runtime_context", {}).get("warehouse"),
            "suppliers": arguments.get("suppliers") or ([arguments["supplier"]] if arguments.get("supplier") else []),
            "schedule_date": arguments.get("schedule_date"),
            "posting_date": arguments.get("posting_date"),
            "valid_till": arguments.get("valid_till"),
            "items": arguments.get("items") or arguments.get("selected_items") or [],
            "effect": f"将在 ERPNext 中{seed.operation_summary}",
        }

    @staticmethod
    def _questions_for_evaluation(evaluation: CatalogEvaluation) -> list[str]:
        by_id = {row["slot_id"]: row for row in evaluation.slots}
        return [
            f"请补充或修正：{by_id[slot_id]['label']}。{by_id[slot_id]['reason']}"
            for slot_id in [*evaluation.missing, *evaluation.invalid, *evaluation.blocked]
            if slot_id in by_id
        ]

    def _verify_readback(
        self,
        gateway: ToolGateway,
        pending: dict[str, Any],
        tool_result: dict[str, Any],
    ) -> dict[str, Any]:
        operation_id = str(pending["operation_id"])
        goal = operation_goal(operation_id)
        prepared = PreparedBusinessAction(
            capability=operation_capability(operation_id),
            goal=goal,
            tool_call=dict(pending["tool_call"]),
            summary=str(pending.get("summary", {}).get("title") or goal),
            field_sources={},
            preflight_checks=(),
            confirmation_hash=canonical_tool_call_hash(dict(pending["tool_call"])),
            write=True,
        )

        def load_document(doctype: str, name: str) -> dict[str, Any]:
            result = gateway.adapter.client.get_document(doctype, name)
            if not result.ok or not isinstance(result.data, dict):
                raise RuntimeError(result.user_message or f"无法回读 {doctype} {name}")
            return dict(result.data)

        return verify_procurement_result(prepared, tool_result, load_document)

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


def _is_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(str(value)[:10])
        return True
    except ValueError:
        return False
