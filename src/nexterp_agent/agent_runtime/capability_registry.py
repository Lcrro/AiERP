from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator


class _IntentBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    provenance: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_iso_date_fields(self) -> "_IntentBase":
        for field_name in self.__class__.model_fields:
            if field_name.endswith("_date") or field_name in {"from_date", "to_date", "valid_till"}:
                value = getattr(self, field_name, None)
                if value not in (None, ""):
                    _iso_date(str(value))
        return self


class DocumentReferenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    doctype: str = Field(min_length=1)
    name: str = Field(min_length=1)


class IntentItemModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_code: str | None = None
    source_row: str | None = None
    qty: float | None = Field(default=None, ge=0)
    uom: str | None = None
    rate: float | None = Field(default=None, ge=0)
    valuation_rate: float | None = Field(default=None, ge=0)
    warehouse: str | None = None
    project: str | None = None
    schedule_date: str | None = None
    reason: str | None = None
    batch_no: str | None = None
    serial_no: str | None = None
    description: str | None = None

    @field_validator("schedule_date")
    @classmethod
    def validate_schedule_date(cls, value: str | None) -> str | None:
        return _iso_date(value)


class ProcurementIntentModel(_IntentBase):
    source_documents: list[DocumentReferenceModel] = Field(default_factory=list)
    source_document: DocumentReferenceModel | None = None
    items: list[IntentItemModel] = Field(default_factory=list)
    suppliers: list[str] = Field(default_factory=list)
    supplier: str | None = None
    company: str | None = None
    project: str | None = None
    warehouse: str | None = None
    schedule_date: str | None = None
    valid_till: str | None = None
    posting_date: str | None = None
    currency: str | None = None
    message: str | None = None
    full_return: bool = False

    @field_validator("schedule_date", "valid_till", "posting_date")
    @classmethod
    def validate_dates(cls, value: str | None) -> str | None:
        return _iso_date(value)


class StockIntentModel(_IntentBase):
    items: list[IntentItemModel] = Field(default_factory=list)
    company: str | None = None
    project: str | None = None
    source_warehouse: str | None = None
    target_warehouse: str | None = None
    warehouse: str | None = None
    posting_date: str | None = None
    cost_center: str | None = None
    expense_account: str | None = None
    remarks: str | None = None
    include_zero: bool = False
    require_available_stock: bool = True

    @field_validator("posting_date")
    @classmethod
    def validate_posting_date(cls, value: str | None) -> str | None:
        return _iso_date(value)


class FinanceIntentModel(_IntentBase):
    source_documents: list[DocumentReferenceModel] = Field(default_factory=list)
    source_document: DocumentReferenceModel | None = None
    items: list[IntentItemModel] = Field(default_factory=list)
    company: str | None = None
    supplier: str | None = None
    from_date: str | None = None
    to_date: str | None = None
    posting_date: str | None = None
    bill_no: str | None = None
    bill_date: str | None = None
    paid_amount: float | None = Field(default=None, gt=0)
    reference_no: str | None = None
    reference_date: str | None = None
    reason: str | None = None
    remarks: str | None = None

    @field_validator("from_date", "to_date", "posting_date", "bill_date", "reference_date")
    @classmethod
    def validate_dates(cls, value: str | None) -> str | None:
        return _iso_date(value)


class ProjectIntentModel(_IntentBase):
    source_documents: list[DocumentReferenceModel] = Field(default_factory=list)
    source_document: DocumentReferenceModel | None = None
    project: str | None = None
    company: str | None = None
    subject: str | None = None
    description: str | None = None
    priority: Literal["Low", "Medium", "High", "Urgent"] | None = None
    status: str | None = None
    progress: float | None = Field(default=None, ge=0, le=100)
    from_date: str | None = None
    to_date: str | None = None
    exp_start_date: str | None = None
    exp_end_date: str | None = None

    @field_validator("from_date", "to_date", "exp_start_date", "exp_end_date")
    @classmethod
    def validate_dates(cls, value: str | None) -> str | None:
        return _iso_date(value)


@dataclass(frozen=True)
class CapabilityDefinition:
    capability_id: str
    goal: str
    module: str
    purpose: str
    write: bool
    tool: str
    intent_model: type[BaseModel]
    execution_model: type[BaseModel]
    resolvers: tuple[str, ...] = ()
    source_doctypes: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    verifier: str = ""

    def card(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "module": self.module,
            "purpose": self.purpose,
            "write": self.write,
        }

    def guide(self) -> dict[str, Any]:
        return {
            **self.card(),
            "intent_schema": self.intent_model.model_json_schema(),
            "resolver_requirements": list(self.resolvers),
            "source_doctypes": list(self.source_doctypes),
            "preconditions": list(self.preconditions),
            "execution": "Runtime validates and compiles the intent; do not construct the underlying ToolCall.",
        }


def _fixed_goal_model(
    name: str,
    base: type[BaseModel],
    goal: str,
    fields: tuple[str, ...],
) -> type[BaseModel]:
    definitions: dict[str, tuple[Any, Any]] = {"goal": (Literal[goal], goal)}
    for field_name in fields:
        field = base.model_fields[field_name]
        definitions[field_name] = (field.annotation, field)
    return create_model(name, __base__=_IntentBase, **definitions)


_INTENT_FIELDS = {
    "create_material_request": ("items", "company", "project", "warehouse", "schedule_date", "message"),
    "create_rfq_from_material_request": ("source_documents", "suppliers", "valid_till", "message"),
    "create_supplier_quotation_from_rfq": ("source_documents", "supplier", "items", "valid_till", "currency"),
    "compare_supplier_quotations": ("source_documents",),
    "create_purchase_order_from_supplier_quotation": ("source_documents", "schedule_date", "items"),
    "create_purchase_order_from_material_request": ("source_documents", "supplier", "schedule_date", "items"),
    "create_purchase_receipt_from_purchase_order": ("source_documents", "posting_date", "warehouse", "items"),
    "create_purchase_return_from_receipt": ("source_documents", "posting_date", "items", "full_return", "message"),
    "query_stock_balance": ("items", "warehouse", "include_zero"),
    "create_stock_transfer": ("items", "company", "source_warehouse", "target_warehouse", "posting_date", "remarks", "require_available_stock"),
    "create_project_material_issue": ("items", "company", "project", "source_warehouse", "posting_date", "cost_center", "expense_account", "remarks", "require_available_stock"),
    "create_stock_reconciliation": ("items", "company", "warehouse", "posting_date", "remarks"),
    "query_accounts_payable": ("company", "supplier", "from_date", "to_date"),
    "create_purchase_invoice_from_receipt": ("source_documents", "posting_date", "bill_no", "bill_date", "remarks"),
    "create_supplier_payment_from_invoice": ("source_documents", "posting_date", "paid_amount", "reference_no", "reference_date", "remarks"),
    "cancel_financial_document": ("source_documents", "reason", "remarks"),
    "query_project_cost": ("project", "company", "from_date", "to_date"),
    "query_project_exceptions": ("project", "to_date"),
    "create_project_task": ("project", "company", "subject", "description", "priority", "exp_start_date", "exp_end_date"),
    "update_project_task": ("source_documents", "subject", "description", "priority", "status", "progress", "exp_start_date", "exp_end_date"),
}


_SPECS = (
    ("material_request.create", "create_material_request", "buying", "创建采购类型材料申请草稿", True, "erpnext.buying.create_material_request_draft", ProcurementIntentModel, ("item", "project", "warehouse", "company", "date", "uom"), (), ("物料、数量和需求日期明确",), "verify_procurement_result"),
    ("rfq.from_material_request", "create_rfq_from_material_request", "buying", "从已提交材料申请创建询价草稿", True, "erpnext.buying.create_request_for_quotation_draft", ProcurementIntentModel, ("document", "supplier", "date"), ("Material Request",), ("来源材料申请已提交",), "verify_procurement_result"),
    ("supplier_quotation.from_rfq", "create_supplier_quotation_from_rfq", "buying", "从已提交询价录入供应商报价草稿", True, "erpnext.buying.create_supplier_quotation_draft", ProcurementIntentModel, ("document", "supplier", "date"), ("Request for Quotation",), ("来源询价已提交",), "verify_procurement_result"),
    ("supplier_quotation.compare", "compare_supplier_quotations", "buying", "比较已提交的供应商报价", False, "erpnext.buying.compare_supplier_quotations", ProcurementIntentModel, ("document",), ("Supplier Quotation",), ("报价已提交",), "verify_procurement_result"),
    ("purchase_order.from_supplier_quotation", "create_purchase_order_from_supplier_quotation", "buying", "从已提交供应商报价创建采购订单草稿", True, "erpnext.buying.create_purchase_order_from_supplier_quotation_draft", ProcurementIntentModel, ("document", "date"), ("Supplier Quotation",), ("报价已提交且仍可转订单",), "verify_procurement_result"),
    ("purchase_order.from_material_request", "create_purchase_order_from_material_request", "buying", "从已提交材料申请创建采购订单草稿", True, "erpnext.buying.create_purchase_order_from_material_request_draft", ProcurementIntentModel, ("document", "supplier", "date"), ("Material Request",), ("材料申请已提交",), "verify_procurement_result"),
    ("purchase_receipt.from_purchase_order", "create_purchase_receipt_from_purchase_order", "buying", "从已提交采购订单创建采购收货草稿", True, "erpnext.buying.create_purchase_receipt_from_purchase_order_draft", ProcurementIntentModel, ("document", "warehouse", "date"), ("Purchase Order",), ("采购订单已提交且存在未收数量",), "verify_procurement_result"),
    ("purchase_return.from_receipt", "create_purchase_return_from_receipt", "buying", "从已提交采购收货创建退货草稿", True, "erpnext.buying.create_purchase_receipt_return_draft", ProcurementIntentModel, ("document",), ("Purchase Receipt",), ("采购收货已提交",), "verify_procurement_result"),
    ("stock.balance.query", "query_stock_balance", "stock", "查询物料在相关仓库的实时库存", False, "erpnext.stock.get_item_locations", StockIntentModel, ("item", "warehouse"), (), ("物料已解析",), "verify_stock_result"),
    ("stock.transfer.create", "create_stock_transfer", "stock", "创建仓库间库存调拨草稿", True, "erpnext.stock.create_transfer_draft", StockIntentModel, ("item", "warehouse", "company"), (), ("源仓库存充足且源目标仓不同",), "verify_stock_result"),
    ("stock.project_issue.create", "create_project_material_issue", "stock", "创建项目材料领用草稿", True, "erpnext.projects.create_material_issue_draft", StockIntentModel, ("item", "warehouse", "project", "company"), (), ("来源仓库存充足",), "verify_stock_result"),
    ("stock.reconciliation.create", "create_stock_reconciliation", "stock", "创建库存盘点调整草稿", True, "erpnext.stock.create_reconciliation_draft", StockIntentModel, ("item", "warehouse", "company"), (), ("实盘数量非负",), "verify_stock_result"),
    ("finance.accounts_payable.query", "query_accounts_payable", "accounting", "查询实时应付账款", False, "erpnext.accounting.accounts_payable", FinanceIntentModel, ("company", "supplier", "date"), (), ("公司已确认",), "verify_finance_result"),
    ("finance.purchase_invoice.from_receipt", "create_purchase_invoice_from_receipt", "accounting", "从采购收货创建采购发票草稿", True, "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft", FinanceIntentModel, ("document", "date"), ("Purchase Receipt",), ("采购收货已提交且存在未开票数量",), "verify_finance_result"),
    ("finance.supplier_payment.from_invoice", "create_supplier_payment_from_invoice", "accounting", "从已提交采购发票创建供应商付款草稿", True, "erpnext.accounting.create_supplier_payment_from_purchase_invoice_draft", FinanceIntentModel, ("document", "date"), ("Purchase Invoice",), ("采购发票已提交且存在未付金额",), "verify_finance_result"),
    ("finance.document.cancel", "cancel_financial_document", "accounting", "取消并冲销允许的已提交财务单据", True, "erpnext.accounting.cancel_financial_document", FinanceIntentModel, ("document",), tuple(), ("单据已提交且取消原因明确",), "verify_finance_result"),
    ("project.cost.query", "query_project_cost", "projects", "查询项目成本上下文", False, "erpnext.projects.get_project_cost_context", ProjectIntentModel, ("project", "company", "date"), (), ("项目已确认",), "verify_project_result"),
    ("project.exceptions.query", "query_project_exceptions", "projects", "查询项目任务和业务异常", False, "erpnext.projects.get_project_exceptions", ProjectIntentModel, ("project", "date"), (), ("项目已确认",), "verify_project_result"),
    ("project.task.create", "create_project_task", "projects", "创建项目任务", True, "erpnext.projects.create_task", ProjectIntentModel, ("project",), (), ("项目和任务名称明确",), "verify_project_result"),
    ("project.task.update", "update_project_task", "projects", "更新项目任务状态、进度或计划", True, "erpnext.projects.update_task", ProjectIntentModel, ("document",), ("Task",), ("任务已实时读取",), "verify_project_result"),
)


_TOOL_CAPABILITY_ALIASES = {
    "erpnext.stock.get_balance": "stock.balance.query",
}


class CapabilityRegistry:
    def __init__(self) -> None:
        definitions = []
        for index, spec in enumerate(_SPECS):
            capability_id, goal, module, purpose, write, tool, base, resolvers, sources, preconditions, verifier = spec
            model_name = "".join(part.title() for part in goal.split("_")) + "Intent"
            definitions.append(CapabilityDefinition(
                capability_id=capability_id,
                goal=goal,
                module=module,
                purpose=purpose,
                write=write,
                tool=tool,
                intent_model=_fixed_goal_model(f"{model_name}{index}", base, goal, _INTENT_FIELDS[goal]),
                execution_model=base,
                resolvers=resolvers,
                source_doctypes=sources,
                preconditions=preconditions,
                verifier=verifier,
            ))
        self._definitions = tuple(definitions)
        self._by_id = {item.capability_id: item for item in definitions}
        self._by_goal = {item.goal: item for item in definitions}
        self._by_tool = {item.tool: item for item in definitions}

    @property
    def definitions(self) -> tuple[CapabilityDefinition, ...]:
        return self._definitions

    @property
    def protected_write_tools(self) -> frozenset[str]:
        return frozenset(item.tool for item in self._definitions if item.write)

    @property
    def capability_tools(self) -> frozenset[str]:
        return frozenset(item.tool for item in self._definitions) | frozenset(_TOOL_CAPABILITY_ALIASES)

    def get(self, capability_id: str) -> CapabilityDefinition:
        try:
            return self._by_id[capability_id]
        except KeyError as exc:
            raise ValueError(f"unknown capability_id: {capability_id}") from exc

    def for_goal(self, goal: str) -> CapabilityDefinition:
        try:
            return self._by_goal[goal]
        except KeyError as exc:
            raise ValueError(f"unsupported business goal: {goal}") from exc

    def for_tool(self, tool: str) -> CapabilityDefinition | None:
        direct = self._by_tool.get(tool)
        if direct:
            return direct
        capability_id = _TOOL_CAPABILITY_ALIASES.get(tool)
        return self._by_id.get(capability_id) if capability_id else None

    def discover(self, query: str, *, policy: Any, modules: list[str] | None = None, limit: int = 5) -> list[dict[str, Any]]:
        allowed_modules = {value for value in modules or [] if value}
        query_tokens = _search_tokens(query)
        ranked: list[tuple[int, CapabilityDefinition]] = []
        for definition in self._definitions:
            if allowed_modules and definition.module not in allowed_modules:
                continue
            if not policy.decide(definition.tool, origin="agent").allowed:
                continue
            text = f"{definition.capability_id} {definition.goal} {definition.module} {definition.purpose}".lower()
            score = sum(4 if token in definition.capability_id else 1 for token in query_tokens if token in text)
            ranked.append((score, definition))
        ranked.sort(key=lambda row: (-row[0], row[1].capability_id))
        return [definition.card() for _, definition in ranked[: max(1, min(int(limit), 5))]]

    def guides(self, capability_ids: list[str], *, policy: Any) -> list[dict[str, Any]]:
        guides = []
        for capability_id in capability_ids[:3]:
            definition = self._by_id.get(str(capability_id))
            if definition and policy.decide(definition.tool, origin="agent").allowed:
                guides.append(definition.guide())
        return guides

    def validate_intent(self, capability_id: str, payload: dict[str, Any]) -> tuple[CapabilityDefinition, dict[str, Any]]:
        definition = self.get(capability_id)
        normalized = dict(payload)
        normalized["goal"] = definition.goal
        model = definition.intent_model.model_validate(normalized)
        return definition, model.model_dump(exclude_none=True)

    def parse_intent(self, capability_id: str, payload: dict[str, Any]) -> tuple[CapabilityDefinition, BaseModel]:
        """Return the canonical validated intent model for compiler execution."""
        definition = self.get(capability_id)
        normalized = dict(payload)
        normalized["goal"] = definition.goal
        focused = definition.intent_model.model_validate(normalized)
        model = definition.execution_model.model_validate(focused.model_dump(exclude_none=True))
        return definition, model


def _iso_date(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError("date must use YYYY-MM-DD") from exc


def _search_tokens(value: str) -> set[str]:
    text = str(value or "").lower()
    ascii_tokens = set(re.findall(r"[a-z0-9_.-]+", text))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    chinese_tokens = {chinese[index:index + 2] for index in range(max(0, len(chinese) - 1))}
    if chinese:
        chinese_tokens.add(chinese)
    return ascii_tokens | chinese_tokens
