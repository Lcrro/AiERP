from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
import re
from typing import Any, Callable

from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.item_master.release_resolver import ReleaseMaterialResolver
from nexterp_agent.master_data import MasterDataRelease

from .deepseek_civil_intent import extract_civil_intent_with_deepseek
from .material_request_orchestrator import compose_material_request_tool_call
from .resolvers import EntityResolverRegistry, ResolutionResult
from .session import RuntimeSessionState, RuntimeSessionStore
from .tool_access import make_tool_access_policy
from .tool_gateway import ToolGateway, ToolSession


IntentExtractor = Callable[..., dict[str, Any]]
ClientFactory = Callable[[str], ERPNextClient]


@dataclass(frozen=True)
class RuntimeTurnResult:
    status: str
    message: str
    intent: dict[str, Any]
    resolutions: dict[str, Any]
    tool_call: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None
    tool_calls: tuple[dict[str, Any], ...] = ()
    tool_results: tuple[dict[str, Any], ...] = ()
    questions: tuple[str, ...] = ()
    candidates: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class CivilAgentRuntime:
    def __init__(
        self,
        *,
        release: MasterDataRelease | None = None,
        intent_extractor: IntentExtractor = extract_civil_intent_with_deepseek,
        client_factory: ClientFactory | None = None,
        session_store: RuntimeSessionStore | None = None,
    ) -> None:
        self.release = release or MasterDataRelease()
        self.intent_extractor = intent_extractor
        self.client_factory = client_factory
        self.session_store = session_store or RuntimeSessionStore()
        self.entity_resolvers = EntityResolverRegistry(self.release)
        self.material_resolver = ReleaseMaterialResolver(self.release.material_release_path)

    def run_once(
        self,
        user_text: str,
        *,
        user: str,
        execute: bool = False,
        today: date | None = None,
        request_id: str | None = None,
    ) -> RuntimeTurnResult:
        employee = self._employee_for_user(user)
        profile = self._profile_for_employee(employee)
        session = self.session_store.load(user, profile=profile)
        if request_id and request_id in session.idempotency_results:
            cached = dict(session.idempotency_results[request_id])
            for field_name in ("tool_calls", "tool_results", "questions", "candidates"):
                cached[field_name] = tuple(cached.get(field_name) or [])
            return RuntimeTurnResult(**cached)
        today = today or date.today()
        extraction_context = {"current_date": today.isoformat(), "employee": employee["employee_name"]}
        intent = self.intent_extractor(user_text, context=extraction_context)
        if intent.get("intent") != "create_material_request":
            return self._run_workflow_intent(
                user_text,
                intent=intent,
                employee=employee,
                profile=profile,
                session=session,
                execute=execute,
                today=today,
                request_id=request_id,
            )

        project_query = intent.get("project_text") or self._session_project_query(session, employee)
        warehouse_query = intent.get("warehouse_text") or session.selected_warehouse_name or employee.get("default_warehouse_code")
        # Relative language is always resolved deterministically by Runtime;
        # model-produced ISO dates must not override words such as "明天".
        date_query = intent.get("schedule_text") or intent.get("schedule_date")
        company = self.entity_resolvers.resolve_company()
        project = self.entity_resolvers.resolve_project(project_query)
        warehouse = self.entity_resolvers.resolve_warehouse(warehouse_query)
        schedule = self.entity_resolvers.resolve_date(date_query, current_date=today)
        project = self._resolve_live_project_name(user, project)
        resolutions = {
            "company": company.to_dict(),
            "project": project.to_dict(),
            "warehouse": warehouse.to_dict(),
            "schedule_date": schedule.to_dict(),
        }

        questions = [
            resolution.question
            for resolution in (company, project, warehouse, schedule)
            if resolution.status != "resolved" and resolution.question
        ]
        if questions:
            result = RuntimeTurnResult("needs_clarification", "还需要补充一些信息。", intent, resolutions, questions=tuple(questions))
            session.pending = result.to_dict()
            self._save_turn(session, user_text, result, request_id=request_id)
            return result

        normalized_intent = dict(intent)
        normalized_intent["company"] = company.value
        normalized_intent["schedule_date"] = schedule.value
        context = {
            "company": company.value,
            "default_schedule_date": schedule.value,
            "project_candidates": [{"name": project.value, "label": project.label}],
            "warehouse_candidates": [{"name": warehouse.value, "label": warehouse.label}],
        }
        composition = compose_material_request_tool_call(
            normalized_intent,
            context=context,
            resolver=self.material_resolver,
        )
        resolutions["materials"] = {
            "resolved_items": composition.get("resolved_items", []),
            "pending_resolutions": composition.get("pending_resolutions", []),
            "item_creation_requests": composition.get("item_creation_requests", []),
        }

        if composition["status"] != "ready":
            candidates = tuple(composition.get("pending_resolutions", []))
            result = RuntimeTurnResult(
                composition["status"],
                "物料还不能唯一确定。" if candidates else "材料申请信息还不完整。",
                intent,
                resolutions,
                questions=tuple(composition.get("questions", [])),
                candidates=candidates,
            )
            session.pending = result.to_dict()
            self._save_turn(session, user_text, result, request_id=request_id)
            return result

        tool_call = composition["tool_call"]
        session.company = company.value
        session.selected_project_code = self._stable_project_code(project)
        session.selected_warehouse_name = warehouse.value
        if not execute:
            result = RuntimeTurnResult(
                "needs_confirmation",
                "材料申请草稿已经编排完成，确认后可以写入 ERPNext。",
                intent,
                resolutions,
                tool_call=tool_call,
            )
            session.pending = result.to_dict()
            self._save_turn(session, user_text, result, request_id=request_id)
            return result

        if self.client_factory is None:
            raise RuntimeError("ERPNext client factory is required for execute mode")
        client = self.client_factory(user)
        policy = make_tool_access_policy(profile, extra_allowed_tools={tool_call["tool"]})
        gateway = ToolGateway(
            ERPNextAdapter(client),
            ToolSession(user=user, policy=policy, verify_erpnext_identity=True),
        )
        execution = gateway.execute(tool_call, origin="agent")
        tool_result = execution.to_dict()
        if execution.ok:
            document_name = _extract_document_name(execution.data)
            if document_name:
                session.remember_document("Material Request", document_name)
            message = f"材料申请草稿已创建：{document_name or 'ERPNext 已返回成功结果'}。"
            status = "completed"
            session.pending = None
        else:
            message = execution.user_message or "ERPNext 执行失败。"
            status = "failed"
        result = RuntimeTurnResult(status, message, intent, resolutions, tool_call, tool_result)
        self._save_turn(session, user_text, result, request_id=request_id)
        return result

    def _run_workflow_intent(
        self,
        user_text: str,
        *,
        intent: dict[str, Any],
        employee: dict[str, str],
        profile: str,
        session: RuntimeSessionState,
        execute: bool,
        today: date,
        request_id: str | None = None,
    ) -> RuntimeTurnResult:
        intent_name = intent.get("intent")
        if intent_name in {None, "unknown"}:
            result = RuntimeTurnResult("unsupported_intent", "我还不能确定你要执行哪项 ERPNext 业务。", intent, {})
            self._save_turn(session, user_text, result, request_id=request_id)
            return result

        company = self.entity_resolvers.resolve_company()
        project_query = intent.get("project_text") or self._session_project_query(session, employee)
        warehouse_query = intent.get("warehouse_text") or session.selected_warehouse_name or employee.get("default_warehouse_code")
        project = self.entity_resolvers.resolve_project(project_query) if project_query else None
        if project:
            project = self._resolve_live_project_name(session.user, project)
        warehouse = self.entity_resolvers.resolve_warehouse(warehouse_query) if warehouse_query else None
        supplier = self.entity_resolvers.resolve_supplier(intent.get("supplier_text")) if intent.get("supplier_text") else None
        assigned_to = self.entity_resolvers.resolve_employee(intent.get("assigned_to_text")) if intent.get("assigned_to_text") else None
        resolutions: dict[str, Any] = {"company": company.to_dict()}
        if project:
            resolutions["project"] = project.to_dict()
        if warehouse:
            resolutions["warehouse"] = warehouse.to_dict()
        if supplier:
            resolutions["supplier"] = supplier.to_dict()
        if assigned_to:
            resolutions["assigned_to"] = assigned_to.to_dict()

        questions: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        confirmation = self._confirmation(user=session.user, reason=intent.get("description") or user_text)
        document_name = str(intent.get("document_name") or "").strip() or _extract_document_reference(user_text)

        def document(doctype: str) -> str | None:
            return document_name or self._latest_document(session, doctype)

        def date_value(text: Any, default: str | None = None) -> str | None:
            if not text:
                return default
            resolved = self.entity_resolvers.resolve_date(str(text), current_date=today)
            return str(resolved.value) if resolved.status == "resolved" and resolved.value else default

        if intent_name == "submit_document":
            doctype = (
                _normalize_document_type(intent.get("document_type"))
                or _infer_document_type(user_text)
                or self._latest_document_type(session)
            )
            name = document(doctype) if doctype else None
            if not doctype or not name:
                questions.append("请说明要提交的单据类型和单号。")
            else:
                tool = _submit_tool_for_doctype(doctype)
                if not tool:
                    questions.append(f"暂不支持提交 {doctype}。")
                else:
                    tool_calls.append({"tool": tool, "arguments": {"doctype": doctype, "name": name, "confirmation": confirmation}})

        elif intent_name == "create_purchase_order":
            material_request = document("Material Request")
            if not material_request:
                questions.append("请说明要转采购订单的材料申请单号。")
            if not supplier or supplier.status != "resolved":
                questions.append(supplier.question if supplier and supplier.question else "请选择供应商。")
            if material_request and supplier and supplier.status == "resolved":
                tool_calls.append(
                    {
                        "tool": "erpnext.buying.create_purchase_order_from_material_request_draft",
                        "arguments": {
                            "material_request": material_request,
                            "supplier": supplier.value,
                            "transaction_date": today.isoformat(),
                            "company": company.value,
                        },
                    }
                )

        elif intent_name == "create_request_for_quotation":
            item_result = self._resolve_workflow_items(intent.get("items") or [])
            resolutions["materials"] = item_result
            questions.extend(item_result["questions"])
            if not warehouse or warehouse.status != "resolved":
                questions.append(warehouse.question if warehouse and warehouse.question else "请选择询价物料的目标仓库。")
            if not supplier or supplier.status != "resolved":
                questions.append(supplier.question if supplier and supplier.question else "请选择至少一个询价供应商。")
            if not questions and supplier and supplier.status == "resolved" and warehouse and warehouse.status == "resolved":
                rfq_items = [dict(item, warehouse=warehouse.value) for item in item_result["items"]]
                tool_calls.append(
                    {
                        "tool": "erpnext.buying.create_request_for_quotation_draft",
                        "arguments": {
                            "transaction_date": today.isoformat(),
                            "schedule_date": date_value(intent.get("schedule_text"), today.isoformat()),
                            "company": company.value,
                            "message_for_supplier": intent.get("description") or "请按物料规格和数量报价。",
                            "suppliers": [{"supplier": supplier.value}],
                            "items": rfq_items,
                        },
                    }
                )

        elif intent_name == "create_purchase_receipt":
            purchase_order = document("Purchase Order")
            if not purchase_order:
                questions.append("请说明对应的采购订单号。")
            else:
                tool_calls.append(
                    {
                        "tool": "erpnext.buying.create_purchase_receipt_from_purchase_order_draft",
                        "arguments": {"purchase_order": purchase_order, "posting_date": today.isoformat(), "company": company.value},
                    }
                )

        elif intent_name == "record_receipt_discrepancy":
            purchase_receipt = document("Purchase Receipt")
            if not purchase_receipt:
                questions.append("请说明发生差异的采购收货单号。")
            if not intent.get("description"):
                questions.append("请说明到货与采购要求有什么差异。")
            if purchase_receipt and intent.get("description"):
                tool_calls.append(
                    {
                        "tool": "erpnext.buying.record_purchase_receipt_discrepancy",
                        "arguments": {
                            "purchase_receipt": purchase_receipt,
                            "description": intent["description"],
                            "discrepancy_type": intent.get("discrepancy_type") or "其他",
                            "reported_by": session.user,
                            "assigned_to": assigned_to.value if assigned_to and assigned_to.status == "resolved" else session.user,
                            "create_todo": True,
                            "prepare_return": bool(intent.get("full_return")),
                            "full_return": bool(intent.get("full_return")),
                        },
                    }
                )

        elif intent_name == "create_purchase_return":
            purchase_receipt = document("Purchase Receipt")
            if not purchase_receipt:
                questions.append("请说明要退货的采购收货单号。")
            else:
                tool_calls.append(
                    {
                        "tool": "erpnext.buying.create_purchase_receipt_return_draft",
                        "arguments": {
                            "purchase_receipt": purchase_receipt,
                            "posting_date": today.isoformat(),
                            "full_return": bool(intent.get("full_return", True)),
                            "reason": intent.get("description") or "用户要求采购退货",
                        },
                    }
                )

        elif intent_name == "create_purchase_invoice":
            purchase_receipt = document("Purchase Receipt")
            if not purchase_receipt:
                questions.append("请说明对应的采购收货单号。")
            else:
                tool_calls.append(
                    {
                        "tool": "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft",
                        "arguments": {
                            "purchase_receipt": purchase_receipt,
                            "posting_date": today.isoformat(),
                            "bill_date": today.isoformat(),
                            "company": company.value,
                        },
                    }
                )

        elif intent_name in {"create_material_issue", "query_stock"}:
            item_result = self._resolve_workflow_items(
                intent.get("items") or [],
                require_qty=intent_name == "create_material_issue",
            )
            resolutions["materials"] = item_result
            questions.extend(item_result["questions"])
            if warehouse is None or warehouse.status != "resolved":
                questions.append(warehouse.question if warehouse and warehouse.question else "请选择仓库。")
            if intent_name == "query_stock" and not questions:
                for item in item_result["items"]:
                    tool_calls.append(
                        {
                            "tool": "erpnext.stock.get_balance",
                            "arguments": {"item_code": item["item_code"], "warehouse": warehouse.value, "limit": 50},
                        }
                    )
            if intent_name == "create_material_issue":
                if project is None or project.status != "resolved":
                    questions.append(project.question if project and project.question else "请选择项目。")
                if not questions:
                    tool_calls.append(
                        {
                            "tool": "erpnext.projects.create_material_issue_draft",
                            "arguments": {
                                "project": project.value,
                                "source_warehouse": warehouse.value,
                                "company": company.value,
                                "posting_date": today.isoformat(),
                                "require_available_stock": True,
                                "remarks": intent.get("description") or "Agent 创建项目领料草稿",
                                "items": item_result["items"],
                            },
                        }
                    )

        elif intent_name == "query_accounts_payable":
            tool_calls.append(
                {
                    "tool": "erpnext.accounting.accounts_payable",
                    "arguments": {
                        "company": company.value,
                        "from_date": date_value(intent.get("from_date_text")),
                        "to_date": date_value(intent.get("to_date_text"), today.isoformat()),
                    },
                }
            )

        elif intent_name == "query_pending_material_requests":
            tool_calls.append(
                {
                    "tool": "erpnext.search_documents",
                    "arguments": {
                        "doctype": "Material Request",
                        "filters": {"company": company.value, "material_request_type": "Purchase", "docstatus": 1, "status": "Pending"},
                        "fields": ["name", "title", "transaction_date", "schedule_date", "status", "owner"],
                        "limit": 100,
                        "order_by": "schedule_date asc, modified asc",
                    },
                }
            )

        elif intent_name == "query_overdue_purchase_orders":
            tool_calls.append(
                {
                    "tool": "erpnext.search_documents",
                    "arguments": {
                        "doctype": "Purchase Order",
                        "filters": {
                            "company": company.value,
                            "docstatus": 1,
                            "schedule_date": ["<", today.isoformat()],
                            "status": ["not in", ["Completed", "Closed", "Cancelled"]],
                        },
                        "fields": ["name", "supplier", "schedule_date", "status", "per_received", "grand_total"],
                        "limit": 100,
                        "order_by": "schedule_date asc",
                    },
                }
            )

        elif intent_name == "query_project_cost":
            if project is None or project.status != "resolved":
                questions.append(project.question if project and project.question else "请选择项目。")
            else:
                tool_calls.append(
                    {
                        "tool": "erpnext.projects.get_project_cost_context",
                        "arguments": {
                            "project": project.value,
                            "company": company.value,
                            "from_date": date_value(intent.get("from_date_text")),
                            "to_date": date_value(intent.get("to_date_text"), today.isoformat()),
                            "include_tasks": True,
                            "include_stock_entries": True,
                            "include_purchase_receipts": True,
                            "limit": 100,
                        },
                    }
                )

        elif intent_name == "manager_summary":
            tool_calls.extend(
                [
                    {"tool": "erpnext.buying.generate_purchase_suggestions", "arguments": {"limit": 100}},
                    {
                        "tool": "erpnext.search_documents",
                        "arguments": {
                            "doctype": "Purchase Order",
                            "filters": {
                                "company": company.value,
                                "docstatus": 1,
                                "schedule_date": ["<", today.isoformat()],
                                "status": ["not in", ["Completed", "Closed", "Cancelled"]],
                            },
                            "fields": ["name", "supplier", "schedule_date", "status", "per_received", "grand_total"],
                            "limit": 100,
                            "order_by": "schedule_date asc",
                        },
                    },
                    {
                        "tool": "erpnext.accounting.accounts_payable",
                        "arguments": {"company": company.value, "to_date": today.isoformat()},
                    },
                ]
            )

        else:
            result = RuntimeTurnResult("unsupported_intent", f"暂不支持业务意图：{intent_name}", intent, resolutions)
            self._save_turn(session, user_text, result, request_id=request_id)
            return result

        questions = list(dict.fromkeys(question for question in questions if question))
        if questions:
            result = RuntimeTurnResult(
                "needs_clarification",
                "还需要补充一些信息。",
                intent,
                resolutions,
                questions=tuple(questions),
            )
            session.pending = result.to_dict()
            self._save_turn(session, user_text, result, request_id=request_id)
            return result

        read_only = intent_name in {
            "query_stock",
            "query_pending_material_requests",
            "query_overdue_purchase_orders",
            "query_accounts_payable",
            "query_project_cost",
            "manager_summary",
        }
        if not execute and not read_only:
            result = RuntimeTurnResult(
                "needs_confirmation",
                f"{len(tool_calls)} 个业务动作已经编排完成，确认后可以执行。",
                intent,
                resolutions,
                tool_call=tool_calls[0] if tool_calls else None,
                tool_calls=tuple(tool_calls),
            )
            session.pending = result.to_dict()
            self._save_turn(session, user_text, result, request_id=request_id)
            return result

        results = self._execute_tool_calls(tool_calls, user=session.user, profile=profile, session=session)
        ok = all(result.get("ok") for result in results)
        message = self._workflow_message(intent_name, results, ok=ok)
        result = RuntimeTurnResult(
            "completed" if ok else "failed",
            message,
            intent,
            resolutions,
            tool_call=tool_calls[0] if tool_calls else None,
            tool_result=results[0] if results else None,
            tool_calls=tuple(tool_calls),
            tool_results=tuple(results),
        )
        session.pending = None if ok else session.pending
        self._save_turn(session, user_text, result, request_id=request_id)
        return result

    def _execute_tool_calls(
        self,
        tool_calls: list[dict[str, Any]],
        *,
        user: str,
        profile: str,
        session: RuntimeSessionState,
    ) -> list[dict[str, Any]]:
        if self.client_factory is None:
            raise RuntimeError("ERPNext client factory is required for execution")
        client = self.client_factory(user)
        policy = make_tool_access_policy(
            profile,
            extra_allowed_tools={call["tool"] for call in tool_calls},
            allow_runtime_internal=True,
        )
        gateway = ToolGateway(ERPNextAdapter(client), ToolSession(user=user, policy=policy, verify_erpnext_identity=True))
        results: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            execution = gateway.execute(tool_call, origin="runtime")
            payload = execution.to_dict()
            results.append(payload)
            if execution.ok and isinstance(execution.data, dict):
                doctype = execution.data.get("doctype")
                name = _extract_document_name(execution.data)
                if doctype and name:
                    session.remember_document(doctype, name)
            if not execution.ok:
                break
        return results

    def _resolve_workflow_items(self, items: list[dict[str, Any]], *, require_qty: bool = True) -> dict[str, Any]:
        resolved: list[dict[str, Any]] = []
        questions: list[str] = []
        candidates: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            raw_text = str(item.get("raw_item_text") or "").strip()
            qty = item.get("qty")
            if not raw_text:
                questions.append(f"第 {index} 行缺少物料名称。")
                continue
            if require_qty and (not isinstance(qty, (int, float)) or qty <= 0):
                questions.append(f"请说明“{raw_text}”的领用或查询数量。")
                continue
            resolution = self.material_resolver.resolve(raw_text, specs=item.get("specs") or {}, limit=5)
            if resolution["status"] != "ready":
                questions.extend(resolution["questions"])
                candidates.append({"raw_item_text": raw_text, "resolution": resolution})
                continue
            material = resolution["resolved"]
            conversion_factor = material.get("conversion_factor")
            resolved.append(
                {
                    "item_code": material["item_code"],
                    "qty": qty if isinstance(qty, (int, float)) and qty > 0 else 1,
                    "uom": item.get("uom") or material.get("stock_uom"),
                    "conversion_factor": float(conversion_factor) if conversion_factor not in {None, ""} else 1.0,
                    "description": material.get("sku_name"),
                }
            )
        return {"items": resolved, "questions": questions, "candidates": candidates}

    def _latest_document(self, session: RuntimeSessionState, doctype: str) -> str | None:
        values = session.documents.get(doctype) or []
        return values[-1] if values else None

    def _latest_document_type(self, session: RuntimeSessionState) -> str | None:
        for doctype in ("Purchase Invoice", "Purchase Receipt", "Purchase Order", "Material Request", "Stock Entry"):
            if session.documents.get(doctype):
                return doctype
        return None

    def _confirmation(self, *, user: str, reason: str) -> dict[str, Any]:
        return {
            "confirmed": True,
            "confirmed_by": user,
            "confirmed_at": datetime.now().astimezone().isoformat(),
            "confirmation_text": "用户通过 CLI --execute 明确确认",
            "reason": reason,
        }

    def _workflow_message(self, intent_name: str, results: list[dict[str, Any]], *, ok: bool) -> str:
        if not ok:
            failed = next((result for result in results if not result.get("ok")), {})
            return failed.get("user_message") or failed.get("error") or "ERPNext 执行失败。"
        names = [
            _extract_document_name(result.get("data"))
            for result in results
            if isinstance(result.get("data"), dict)
        ]
        names = [name for name in names if name]
        if names:
            return f"业务动作已完成：{', '.join(names)}。"
        return f"{intent_name} 已完成，共执行 {len(results)} 个 ToolCall。"

    def _employee_for_user(self, user: str) -> dict[str, str]:
        for row in self.release.employees.values():
            if row["user_email"] == user:
                return row
        raise KeyError(f"Employee not found for user: {user}")

    def _profile_for_employee(self, employee: dict[str, str]) -> str:
        mapping = {
            "ROLE-GM": "manager",
            "ROLE-MAT-EQP-MGR": "procurement",
            "ROLE-OPS-MGR": "manager",
            "ROLE-PROJ-MGR": "project",
            "ROLE-TECH-LEAD": "project",
            "ROLE-MATERIAL-CLERK": "project",
            "ROLE-SYSADMIN": "system_admin",
        }
        return mapping.get(employee["role_code"], "project")

    def _session_project_query(self, session: RuntimeSessionState, employee: dict[str, str]) -> str | None:
        selected = session.selected_project_code
        if selected in self.release.projects:
            return selected
        return employee.get("default_project_code")

    def _stable_project_code(self, resolution: ResolutionResult) -> str | None:
        for candidate in resolution.candidates:
            row = candidate.get("row")
            if isinstance(row, dict) and row.get("project_code"):
                return row["project_code"]
        return resolution.value

    def _resolve_live_project_name(self, user: str, resolution: ResolutionResult) -> ResolutionResult:
        if resolution.status != "resolved" or not resolution.value or self.client_factory is None:
            return resolution
        project = self.release.projects.get(resolution.value)
        if not project:
            return resolution
        client = self.client_factory(user)
        result = client.search_documents(
            "Project",
            filters={"project_name": project["project_name"]},
            fields=["name", "project_name"],
            limit=2,
        )
        if not result.ok or not isinstance(result.data, list):
            return replace(
                resolution,
                status="needs_clarification",
                value=None,
                question="无法从 ERPNext 读取该项目，请检查员工项目权限。",
                reason=result.error or "ERPNext project lookup failed",
            )
        if len(result.data) != 1:
            return replace(
                resolution,
                status="needs_selection",
                value=None,
                question="ERPNext 中没有找到唯一项目，请先核对项目主数据。",
                reason=f"ERPNext project matches={len(result.data)}",
            )
        actual_name = result.data[0].get("name")
        return replace(resolution, value=actual_name, reason=f"{resolution.reason}；ERPNext项目主键已核对")

    def _save_turn(
        self,
        session: RuntimeSessionState,
        user_text: str,
        result: RuntimeTurnResult,
        *,
        request_id: str | None = None,
    ) -> None:
        if request_id:
            session.remember_request(request_id, result.to_dict())
        session.add_turn({"user_text": user_text, "result": result.to_dict()})
        self.session_store.save(session)


def _extract_document_name(data: Any) -> str | None:
    if isinstance(data, dict):
        if isinstance(data.get("name"), str):
            return data["name"]
        document = data.get("document")
        if isinstance(document, dict) and isinstance(document.get("name"), str):
            return document["name"]
    return None


def _submit_tool_for_doctype(doctype: str) -> str | None:
    if doctype in {"Material Request", "Request for Quotation", "Supplier Quotation", "Purchase Order", "Purchase Receipt"}:
        return "erpnext.buying.submit_document"
    if doctype in {"Stock Entry", "Stock Reconciliation", "Delivery Note", "Pick List"}:
        return "erpnext.stock.submit_document"
    if doctype in {"Purchase Invoice", "Sales Invoice", "Payment Entry", "Journal Entry"}:
        return "erpnext.accounting.submit_financial_document"
    return None


def _extract_document_reference(text: str) -> str:
    patterns = (
        r"MAT-MR-\d{4}-\d+",
        r"PUR-ORD-\d{4}-\d+",
        r"MAT-PRE-\d{4}-\d+",
        r"MAT-PR-RET-\d{4}-\d+",
        r"ACC-PINV-\d{4}-\d+",
        r"MAT-STE-\d{4}-\d+",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0).upper()
    return ""


def _normalize_document_type(value: Any) -> str | None:
    text = str(value or "").strip()
    aliases = {
        "Purchase Return": "Purchase Receipt",
        "Purchase Receipt Return": "Purchase Receipt",
        "采购退货": "Purchase Receipt",
        "采购收货": "Purchase Receipt",
        "采购订单": "Purchase Order",
        "材料申请": "Material Request",
        "采购发票": "Purchase Invoice",
        "项目领料": "Stock Entry",
    }
    return aliases.get(text, text or None)


def _infer_document_type(text: str) -> str | None:
    for phrase, doctype in (
        ("采购退货", "Purchase Receipt"),
        ("采购收货", "Purchase Receipt"),
        ("采购订单", "Purchase Order"),
        ("材料申请", "Material Request"),
        ("采购发票", "Purchase Invoice"),
        ("项目领料", "Stock Entry"),
    ):
        if phrase in text:
            return doctype
    return None


# Kept only as an explicit regression fixture. Production entry points use the
# DeepSeek planning loop below and never fall back to this implementation.
LegacyCivilAgentRuntime = CivilAgentRuntime

from .deepseek_agent_runtime import DeepSeekAgentRuntime  # noqa: E402


class CivilAgentRuntime(DeepSeekAgentRuntime):
    """Backward-compatible public name for the DeepSeek autonomous Runtime."""

    def __new__(cls, *args: Any, **kwargs: Any):
        intent_extractor = kwargs.pop("intent_extractor", None)
        if intent_extractor is not None:
            return LegacyCivilAgentRuntime(*args, intent_extractor=intent_extractor, **kwargs)
        return super().__new__(cls)
