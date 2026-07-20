from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from hashlib import sha256
import json
from typing import Any, Callable, Iterable


PROCUREMENT_GOALS = frozenset(
    {
        "create_material_request",
        "create_rfq_from_material_request",
        "create_supplier_quotation_from_rfq",
        "compare_supplier_quotations",
        "create_purchase_order_from_supplier_quotation",
        "create_purchase_order_from_material_request",
        "create_purchase_receipt_from_purchase_order",
        "create_purchase_return_from_receipt",
    }
)


@dataclass(frozen=True)
class DocumentReference:
    doctype: str
    name: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DocumentReference":
        doctype = str(payload.get("doctype") or "").strip()
        name = str(payload.get("name") or payload.get("value") or "").strip()
        if not doctype or not name:
            raise ValueError("source_documents require doctype and name")
        return cls(doctype=doctype, name=name)


@dataclass(frozen=True)
class IntentItem:
    item_code: str | None = None
    source_row: str | None = None
    qty: float | None = None
    uom: str | None = None
    rate: float | None = None
    warehouse: str | None = None
    project: str | None = None
    schedule_date: str | None = None
    reason: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IntentItem":
        qty = _optional_positive_number(payload.get("qty"), "items[].qty")
        rate = _optional_non_negative_number(payload.get("rate"), "items[].rate")
        return cls(
            item_code=_text(payload.get("item_code")),
            source_row=_text(
                payload.get("source_row")
                or payload.get("material_request_item")
                or payload.get("request_for_quotation_item")
                or payload.get("supplier_quotation_item")
                or payload.get("purchase_order_item")
                or payload.get("purchase_receipt_item")
            ),
            qty=qty,
            uom=_text(payload.get("uom")),
            rate=rate,
            warehouse=_text(payload.get("warehouse")),
            project=_text(payload.get("project")),
            schedule_date=_text(payload.get("schedule_date")),
            reason=_text(payload.get("reason")),
        )


@dataclass(frozen=True)
class BusinessIntentDraft:
    goal: str
    source_documents: tuple[DocumentReference, ...] = ()
    items: tuple[IntentItem, ...] = ()
    suppliers: tuple[str, ...] = ()
    company: str | None = None
    project: str | None = None
    warehouse: str | None = None
    schedule_date: str | None = None
    valid_till: str | None = None
    posting_date: str | None = None
    currency: str | None = None
    message: str | None = None
    full_return: bool = False
    provenance: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "BusinessIntentDraft":
        if not isinstance(payload, dict):
            raise ValueError("business_intent must be an object")
        goal = str(payload.get("goal") or "").strip()
        if goal not in PROCUREMENT_GOALS:
            raise ValueError(f"unsupported procurement goal: {goal}")
        raw_sources = payload.get("source_documents") or []
        if isinstance(payload.get("source_document"), dict):
            raw_sources = [payload["source_document"], *raw_sources]
        if not isinstance(raw_sources, list):
            raise ValueError("source_documents must be an array")
        raw_items = payload.get("items") or []
        if not isinstance(raw_items, list):
            raise ValueError("items must be an array")
        raw_suppliers = payload.get("suppliers") or []
        if payload.get("supplier"):
            raw_suppliers = [payload["supplier"], *raw_suppliers]
        if not isinstance(raw_suppliers, list):
            raise ValueError("suppliers must be an array")
        provenance = payload.get("provenance") or {}
        if not isinstance(provenance, dict):
            raise ValueError("provenance must be an object")
        return cls(
            goal=goal,
            source_documents=tuple(DocumentReference.from_dict(row) for row in raw_sources if isinstance(row, dict)),
            items=tuple(IntentItem.from_dict(row) for row in raw_items if isinstance(row, dict)),
            suppliers=tuple(dict.fromkeys(str(value).strip() for value in raw_suppliers if str(value).strip())),
            company=_text(payload.get("company")),
            project=_text(payload.get("project")),
            warehouse=_text(payload.get("warehouse")),
            schedule_date=_iso_date(payload.get("schedule_date"), "schedule_date"),
            valid_till=_iso_date(payload.get("valid_till"), "valid_till"),
            posting_date=_iso_date(payload.get("posting_date"), "posting_date"),
            currency=_text(payload.get("currency")),
            message=_text(payload.get("message")),
            full_return=bool(payload.get("full_return")),
            provenance={str(key): str(value) for key, value in provenance.items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CapabilitySpec:
    name: str
    goal: str
    tool: str
    source_doctypes: tuple[str, ...] = ()
    source_docstatus: int | None = None
    write: bool = True


CAPABILITY_SPECS = (
    CapabilitySpec("material_request.create", "create_material_request", "erpnext.buying.create_material_request_draft"),
    CapabilitySpec("rfq.from_material_request", "create_rfq_from_material_request", "erpnext.buying.create_request_for_quotation_draft", ("Material Request",), 1),
    CapabilitySpec("supplier_quotation.from_rfq", "create_supplier_quotation_from_rfq", "erpnext.buying.create_supplier_quotation_draft", ("Request for Quotation",), 1),
    CapabilitySpec("supplier_quotation.compare", "compare_supplier_quotations", "erpnext.buying.compare_supplier_quotations", ("Supplier Quotation",), 1, False),
    CapabilitySpec("purchase_order.from_supplier_quotation", "create_purchase_order_from_supplier_quotation", "erpnext.buying.create_purchase_order_from_supplier_quotation_draft", ("Supplier Quotation",), 1),
    CapabilitySpec("purchase_order.from_material_request", "create_purchase_order_from_material_request", "erpnext.buying.create_purchase_order_from_material_request_draft", ("Material Request",), 1),
    CapabilitySpec("purchase_receipt.from_purchase_order", "create_purchase_receipt_from_purchase_order", "erpnext.buying.create_purchase_receipt_from_purchase_order_draft", ("Purchase Order",), 1),
    CapabilitySpec("purchase_return.from_receipt", "create_purchase_return_from_receipt", "erpnext.buying.create_purchase_receipt_return_draft", ("Purchase Receipt",), 1),
)


class CapabilityCompilationError(ValueError):
    def __init__(self, message: str, *, questions: Iterable[str] = ()) -> None:
        super().__init__(message)
        self.questions = tuple(questions)


@dataclass(frozen=True)
class PreparedBusinessAction:
    capability: str
    goal: str
    tool_call: dict[str, Any]
    summary: str
    field_sources: dict[str, str]
    preflight_checks: tuple[str, ...]
    confirmation_hash: str
    write: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProcurementCapabilityGraph:
    def __init__(self, specs: tuple[CapabilitySpec, ...] = CAPABILITY_SPECS) -> None:
        self.specs = specs

    def for_goal(self, goal: str) -> CapabilitySpec:
        spec = next((item for item in self.specs if item.goal == goal), None)
        if spec is None:
            raise CapabilityCompilationError(f"没有采购业务能力可以处理目标 {goal}")
        return spec

    def legal_actions(self, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not snapshots:
            return [_capability_card(self.for_goal("create_material_request"))]
        doctypes = {str(row.get("doctype") or "") for row in snapshots}
        cards = []
        for spec in self.specs:
            if not spec.source_doctypes or not doctypes.intersection(spec.source_doctypes):
                continue
            matching = [row for row in snapshots if str(row.get("doctype") or "") in spec.source_doctypes]
            if spec.source_docstatus is not None and not all(int(row.get("docstatus") or 0) == spec.source_docstatus for row in matching):
                continue
            cards.append(_capability_card(spec))
        return cards


DocumentLoader = Callable[[str, str], dict[str, Any]]


class ProcurementCapabilityCompiler:
    def __init__(self, document_loader: DocumentLoader, *, graph: ProcurementCapabilityGraph | None = None) -> None:
        self.document_loader = document_loader
        self.graph = graph or ProcurementCapabilityGraph()

    def compile(
        self,
        intent: BusinessIntentDraft,
        *,
        runtime_context: dict[str, Any],
        today: date,
    ) -> PreparedBusinessAction:
        spec = self.graph.for_goal(intent.goal)
        snapshots = [self.document_loader(ref.doctype, ref.name) for ref in intent.source_documents]
        self._validate_source_documents(spec, intent, snapshots)
        context = _Context(intent, runtime_context, today)
        builders = {
            "create_material_request": self._material_request,
            "create_rfq_from_material_request": self._rfq_from_material_request,
            "create_supplier_quotation_from_rfq": self._supplier_quotation_from_rfq,
            "compare_supplier_quotations": self._compare_supplier_quotations,
            "create_purchase_order_from_supplier_quotation": self._purchase_order_from_supplier_quotation,
            "create_purchase_order_from_material_request": self._purchase_order_from_material_request,
            "create_purchase_receipt_from_purchase_order": self._purchase_receipt_from_purchase_order,
            "create_purchase_return_from_receipt": self._purchase_return_from_receipt,
        }
        arguments, field_sources, checks, summary = builders[intent.goal](context, snapshots)
        tool_call = {"tool": spec.tool, "arguments": _without_empty(arguments)}
        return PreparedBusinessAction(
            capability=spec.name,
            goal=spec.goal,
            tool_call=tool_call,
            summary=summary,
            field_sources=field_sources,
            preflight_checks=tuple(checks),
            confirmation_hash=canonical_tool_call_hash(tool_call),
            write=spec.write,
        )

    @staticmethod
    def _validate_source_documents(
        spec: CapabilitySpec,
        intent: BusinessIntentDraft,
        snapshots: list[dict[str, Any]],
    ) -> None:
        if spec.source_doctypes and not intent.source_documents:
            raise CapabilityCompilationError(
                f"{spec.name} 需要来源单据。",
                questions=(f"请指定要处理的{_doctype_labels(spec.source_doctypes)}单号。",),
            )
        if len(snapshots) != len(intent.source_documents):
            raise CapabilityCompilationError("部分来源单据未能读取。")
        for ref, snapshot in zip(intent.source_documents, snapshots):
            actual_type = str(snapshot.get("doctype") or ref.doctype)
            actual_name = str(snapshot.get("name") or ref.name)
            if actual_type not in spec.source_doctypes:
                raise CapabilityCompilationError(f"{spec.name} 不能使用 {actual_type} {actual_name} 作为来源。")
            if spec.source_docstatus is not None and int(snapshot.get("docstatus") or 0) != spec.source_docstatus:
                raise CapabilityCompilationError(f"{actual_type} {actual_name} 当前状态不能执行 {spec.name}。")

    def _material_request(self, ctx: "_Context", _: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str], list[str], str]:
        if not ctx.intent.items:
            raise CapabilityCompilationError("材料申请缺少物料明细。", questions=("请说明需要的物料、数量和单位。",))
        items = [_intent_item_row(row, ctx, require_item=True, require_qty=True) for row in ctx.intent.items]
        schedule_date = ctx.require_date("schedule_date", "请说明材料最迟需要在什么日期到位。")
        company = ctx.require("company", "请确认所属公司。")
        return (
            {"material_request_type": "Purchase", "schedule_date": schedule_date, "company": company, "items": items},
            ctx.sources("schedule_date", "company", item_prefix="items"),
            ["item_codes_resolved", "positive_quantities", "erpnext_project_and_warehouse_links", "purchase_request_is_draft"],
            f"创建采购类型材料申请草稿，共 {len(items)} 行，需求日期 {schedule_date}",
        )

    def _rfq_from_material_request(self, ctx: "_Context", snapshots: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str], list[str], str]:
        source = snapshots[0]
        if str(source.get("material_request_type") or "Purchase") != "Purchase":
            raise CapabilityCompilationError("只有采购类型材料申请可以生成询价单。")
        if not ctx.intent.suppliers:
            raise CapabilityCompilationError("询价单缺少候选供应商。", questions=("请选择至少一家要询价的供应商。",))
        items = _source_items(source, ctx, source_fields=("material_request", "material_request_item"))
        schedule_date = ctx.intent.schedule_date or _first_date(source, items) or ctx.today.isoformat()
        return (
            {
                "transaction_date": ctx.today.isoformat(),
                "schedule_date": schedule_date,
                "company": source.get("company") or ctx.company,
                "message_for_supplier": ctx.intent.message,
                "suppliers": list(ctx.intent.suppliers),
                "items": items,
            },
            {"transaction_date": "runtime.today", "company": "source_document", "items": "source_document", "suppliers": "resolver"},
            ["material_request_submitted", "supplier_ids_resolved", "source_rows_preserved"],
            f"从材料申请 {source.get('name')} 创建询价草稿，发送给 {len(ctx.intent.suppliers)} 家供应商",
        )

    def _supplier_quotation_from_rfq(self, ctx: "_Context", snapshots: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str], list[str], str]:
        source = snapshots[0]
        supplier = ctx.single_supplier()
        items = _source_items(source, ctx, source_fields=("request_for_quotation", "request_for_quotation_item"), require_rates=True)
        return (
            {
                "supplier": supplier,
                "transaction_date": ctx.today.isoformat(),
                "valid_till": ctx.intent.valid_till,
                "company": source.get("company") or ctx.company,
                "currency": ctx.intent.currency,
                "request_for_quotation": source.get("name"),
                "items": items,
            },
            {"supplier": "resolver", "transaction_date": "runtime.today", "valid_till": "user", "company": "source_document", "items": "source_document+user"},
            ["rfq_submitted", "supplier_resolved", "rates_non_negative", "source_rows_preserved"],
            f"为供应商 {supplier} 记录询价单 {source.get('name')} 的报价草稿",
        )

    def _compare_supplier_quotations(self, _: "_Context", snapshots: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str], list[str], str]:
        if len(snapshots) < 2:
            raise CapabilityCompilationError("比价至少需要两张供应商报价。", questions=("请选择至少两张要比较的供应商报价单。",))
        names = [str(row.get("name") or "") for row in snapshots]
        return (
            {"supplier_quotations": names, "include_drafts": False},
            {"supplier_quotations": "resolved_source_documents"},
            ["quotation_documents_exist", "submitted_quotations_only"],
            f"比较 {len(names)} 张已提交供应商报价",
        )

    def _purchase_order_from_supplier_quotation(self, ctx: "_Context", snapshots: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str], list[str], str]:
        source = snapshots[0]
        valid_till = _text(source.get("valid_till"))
        if valid_till and date.fromisoformat(valid_till[:10]) < ctx.today:
            raise CapabilityCompilationError(
                f"供应商报价 {source.get('name')} 已于 {valid_till[:10]} 失效。",
                questions=("请选择仍在有效期内的供应商报价，或先更新报价有效期。",),
            )
        selected = _selected_source_rows(ctx.intent.items, source.get("items") or [], "supplier_quotation_item")
        return (
            {
                "supplier_quotation": source.get("name"),
                "transaction_date": ctx.today.isoformat(),
                "schedule_date": ctx.intent.schedule_date,
                "selected_items": selected or None,
            },
            {"supplier_quotation": "resolved_source_document", "transaction_date": "runtime.today", "schedule_date": "user", "selected_items": "source_document+user"},
            ["quotation_submitted", "quotation_not_expired", "remaining_quantity_checked_by_adapter", "source_lineage_preserved"],
            f"从供应商报价 {source.get('name')} 创建采购订单草稿",
        )

    def _purchase_order_from_material_request(self, ctx: "_Context", snapshots: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str], list[str], str]:
        source = snapshots[0]
        supplier = ctx.single_supplier()
        selected = _selected_source_rows(ctx.intent.items, source.get("items") or [], "material_request_item")
        return (
            {
                "material_request": source.get("name"),
                "supplier": supplier,
                "transaction_date": ctx.today.isoformat(),
                "schedule_date": ctx.intent.schedule_date,
                "company": source.get("company") or ctx.company,
                "currency": ctx.intent.currency,
                "selected_items": selected or None,
            },
            {"material_request": "resolved_source_document", "supplier": "resolver", "transaction_date": "runtime.today", "company": "source_document", "selected_items": "source_document+user"},
            ["material_request_submitted", "remaining_quantity_checked_by_adapter", "source_lineage_preserved"],
            f"从材料申请 {source.get('name')} 为 {supplier} 创建采购订单草稿",
        )

    def _purchase_receipt_from_purchase_order(self, ctx: "_Context", snapshots: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str], list[str], str]:
        source = snapshots[0]
        selected = _selected_source_rows(ctx.intent.items, source.get("items") or [], "purchase_order_item")
        return (
            {
                "purchase_order": source.get("name"),
                "posting_date": ctx.intent.posting_date or ctx.today.isoformat(),
                "company": source.get("company") or ctx.company,
                "selected_items": selected or None,
            },
            {"purchase_order": "resolved_source_document", "posting_date": "runtime.today/user", "company": "source_document", "selected_items": "source_document+user"},
            ["purchase_order_submitted", "remaining_receipt_quantity_checked_by_adapter", "source_lineage_preserved"],
            f"从采购订单 {source.get('name')} 创建采购收货草稿",
        )

    def _purchase_return_from_receipt(self, ctx: "_Context", snapshots: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, str], list[str], str]:
        source = snapshots[0]
        selected = _selected_source_rows(ctx.intent.items, source.get("items") or [], "purchase_receipt_item", include_reason=True)
        if not ctx.intent.full_return and not selected:
            raise CapabilityCompilationError("退货需要指定全部退货或退货明细。", questions=("是整单退货，还是只退部分物料和数量？",))
        return (
            {
                "purchase_receipt": source.get("name"),
                "posting_date": ctx.intent.posting_date or ctx.today.isoformat(),
                "full_return": ctx.intent.full_return,
                "reason": ctx.intent.message,
                "items": selected or None,
            },
            {"purchase_receipt": "resolved_source_document", "posting_date": "runtime.today/user", "full_return": "user", "items": "source_document+user"},
            ["purchase_receipt_submitted", "returnable_quantity_checked_by_adapter", "return_source_preserved"],
            f"从采购收货 {source.get('name')} 创建{'整单' if ctx.intent.full_return else '部分'}退货草稿",
        )


def canonical_tool_call_hash(tool_call: dict[str, Any]) -> str:
    canonical = {
        "tool": str(tool_call.get("tool") or ""),
        "arguments": _strip_confirmation(tool_call.get("arguments") or {}),
    }
    encoded = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(encoded.encode("utf-8")).hexdigest()


def verify_procurement_result(
    prepared: PreparedBusinessAction,
    tool_result: dict[str, Any],
    document_loader: DocumentLoader,
) -> dict[str, Any]:
    if not tool_result.get("ok"):
        return {"ok": False, "reason": "tool_result_failed", "checks": []}
    data = tool_result.get("data") if isinstance(tool_result.get("data"), dict) else {}
    doctype = str(data.get("doctype") or "")
    name = str(data.get("name") or "")
    expected = {
        "create_material_request": "Material Request",
        "create_rfq_from_material_request": "Request for Quotation",
        "create_supplier_quotation_from_rfq": "Supplier Quotation",
        "create_purchase_order_from_supplier_quotation": "Purchase Order",
        "create_purchase_order_from_material_request": "Purchase Order",
        "create_purchase_receipt_from_purchase_order": "Purchase Receipt",
        "create_purchase_return_from_receipt": "Purchase Receipt",
    }.get(prepared.goal)
    if not prepared.write:
        return {"ok": True, "reason": "read_only_action", "checks": ["tool_result_ok"]}
    if not doctype or not name:
        return {"ok": False, "reason": "missing_created_document_identity", "checks": ["tool_result_ok"]}
    snapshot = document_loader(doctype, name)
    checks = ["tool_result_ok", "document_read_back"]
    if expected and doctype != expected:
        return {"ok": False, "reason": f"expected {expected}, got {doctype}", "checks": checks, "document": snapshot}
    if str(snapshot.get("name") or "") != name:
        return {"ok": False, "reason": "read_back_name_mismatch", "checks": checks, "document": snapshot}
    checks.append("document_identity_matches")
    if prepared.goal == "create_purchase_order_from_supplier_quotation":
        source = prepared.tool_call["arguments"]["supplier_quotation"]
        if not any(str(row.get("supplier_quotation") or "") == source for row in snapshot.get("items") or []):
            return {"ok": False, "reason": "supplier_quotation_lineage_missing", "checks": checks, "document": snapshot}
        checks.append("supplier_quotation_lineage_preserved")
    if prepared.goal == "create_purchase_receipt_from_purchase_order":
        source = prepared.tool_call["arguments"]["purchase_order"]
        if not any(str(row.get("purchase_order") or "") == source for row in snapshot.get("items") or []):
            return {"ok": False, "reason": "purchase_order_lineage_missing", "checks": checks, "document": snapshot}
        checks.append("purchase_order_lineage_preserved")
    return {"ok": True, "reason": "verified", "checks": checks, "document": snapshot}


@dataclass(frozen=True)
class _Context:
    intent: BusinessIntentDraft
    runtime: dict[str, Any]
    today: date

    @property
    def company(self) -> str | None:
        return self.intent.company or _text(self.runtime.get("company"))

    @property
    def project(self) -> str | None:
        return self.intent.project or _text(self.runtime.get("project"))

    @property
    def warehouse(self) -> str | None:
        return self.intent.warehouse or _text(self.runtime.get("warehouse"))

    def require(self, field_name: str, question: str) -> str:
        value = getattr(self.intent, field_name, None) or self.runtime.get(field_name)
        if not value:
            raise CapabilityCompilationError(f"缺少 {field_name}", questions=(question,))
        return str(value)

    def require_date(self, field_name: str, question: str) -> str:
        return self.require(field_name, question)

    def single_supplier(self) -> str:
        if len(self.intent.suppliers) != 1:
            raise CapabilityCompilationError("该操作需要唯一供应商。", questions=("请选择一家确定的供应商。",))
        return self.intent.suppliers[0]

    def sources(self, *fields: str, item_prefix: str | None = None) -> dict[str, str]:
        result = {field: self.intent.provenance.get(field, "user_or_runtime") for field in fields}
        if item_prefix:
            result[item_prefix] = "resolver+user+runtime_context"
        return result


def _intent_item_row(item: IntentItem, ctx: _Context, *, require_item: bool, require_qty: bool) -> dict[str, Any]:
    if require_item and not item.item_code:
        raise CapabilityCompilationError("物料明细中存在未解析物料。", questions=("请选择明确的标准物料。",))
    if require_qty and item.qty is None:
        raise CapabilityCompilationError("物料明细中缺少数量。", questions=(f"请说明 {item.item_code or '该物料'} 的数量。",))
    return _without_empty(
        {
            "item_code": item.item_code,
            "qty": item.qty,
            "uom": item.uom,
            "rate": item.rate,
            "warehouse": item.warehouse or ctx.warehouse,
            "project": item.project or ctx.project,
            "schedule_date": item.schedule_date or ctx.intent.schedule_date,
        }
    )


def _source_items(
    source: dict[str, Any],
    ctx: _Context,
    *,
    source_fields: tuple[str, str],
    require_rates: bool = False,
) -> list[dict[str, Any]]:
    overrides = _intent_items_by_source(ctx.intent.items)
    rows = []
    for source_row in source.get("items") or []:
        if not isinstance(source_row, dict):
            continue
        row_name = str(source_row.get("name") or "")
        override = overrides.get(row_name)
        if ctx.intent.items and override is None:
            continue
        qty = override.qty if override and override.qty is not None else source_row.get("qty")
        rate = override.rate if override and override.rate is not None else source_row.get("rate")
        if require_rates and rate is None:
            raise CapabilityCompilationError(
                f"来源行 {row_name or source_row.get('item_code')} 缺少报价。",
                questions=(f"请提供 {source_row.get('item_code')} 的供应商报价。",),
            )
        payload = {
            "item_code": source_row.get("item_code"),
            "qty": qty,
            "uom": source_row.get("uom") or source_row.get("stock_uom"),
            "rate": rate,
            "schedule_date": (override.schedule_date if override else None) or ctx.intent.schedule_date or source_row.get("schedule_date"),
            "warehouse": (override.warehouse if override else None) or source_row.get("warehouse") or ctx.warehouse,
            "project": source_row.get("project") or ctx.project,
            source_fields[0]: source.get("name"),
            source_fields[1]: row_name,
        }
        if source_fields[0] != "material_request":
            payload["material_request"] = source_row.get("material_request")
            payload["material_request_item"] = source_row.get("material_request_item")
        rows.append(_without_empty(payload))
    if not rows:
        raise CapabilityCompilationError("来源单据没有可处理的物料行。")
    return rows


def _selected_source_rows(
    items: tuple[IntentItem, ...],
    source_rows: list[dict[str, Any]],
    source_key: str,
    *,
    include_reason: bool = False,
) -> list[dict[str, Any]]:
    if not items:
        return []
    by_name = {str(row.get("name") or ""): row for row in source_rows if isinstance(row, dict)}
    result = []
    for item in items:
        candidates = []
        if item.source_row and item.source_row in by_name:
            candidates = [by_name[item.source_row]]
        elif item.item_code:
            candidates = [row for row in by_name.values() if str(row.get("item_code") or "") == item.item_code]
        if len(candidates) != 1:
            raise CapabilityCompilationError(
                f"无法把 {item.item_code or item.source_row or '物料'} 唯一对应到来源单据行。",
                questions=("请选择具体的来源单据明细行。",),
            )
        source_row = candidates[0]
        payload = {
            source_key: source_row.get("name"),
            "item_code": source_row.get("item_code"),
            "qty": item.qty,
            "warehouse": item.warehouse,
            "schedule_date": item.schedule_date,
        }
        if include_reason:
            payload["reason"] = item.reason
        result.append(_without_empty(payload))
    return result


def _intent_items_by_source(items: tuple[IntentItem, ...]) -> dict[str, IntentItem]:
    return {item.source_row: item for item in items if item.source_row}


def _first_date(source: dict[str, Any], items: list[dict[str, Any]]) -> str | None:
    return _text(source.get("schedule_date")) or next((_text(row.get("schedule_date")) for row in items if row.get("schedule_date")), None)


def _capability_card(spec: CapabilitySpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "goal": spec.goal,
        "write": spec.write,
        "source_doctypes": list(spec.source_doctypes),
    }


def _doctype_labels(doctypes: tuple[str, ...]) -> str:
    return "、".join(doctypes)


def _strip_confirmation(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _strip_confirmation(item) for key, item in value.items() if key != "confirmation"}
    if isinstance(value, list):
        return [_strip_confirmation(item) for item in value]
    return value


def _without_empty(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None and value != ""}


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _iso_date(value: Any, field_name: str) -> str | None:
    text = _text(value)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field_name} must be ISO YYYY-MM-DD") from exc


def _optional_positive_number(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if number <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return number


def _optional_non_negative_number(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    number = float(value)
    if number < 0:
        raise ValueError(f"{field_name} must be at least 0")
    return number
