from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SlotScope(StrEnum):
    DOCUMENT = "document"
    ITEM = "item"


class SlotSource(StrEnum):
    USER_INPUT = "user_input"
    USER_CHOICE = "user_choice"
    RUNTIME_CONTEXT = "runtime_context"
    RESOLVER = "resolver"
    SOURCE_DOCUMENT = "source_document"
    ERP_DEFAULT = "erp_default"
    SYSTEM_GENERATED = "system_generated"
    DERIVED = "derived"
    FIXED = "fixed"


class SlotStatus(StrEnum):
    RESOLVED = "resolved"
    MISSING = "missing"
    INVALID = "invalid"
    BLOCKED = "blocked"
    NOT_APPLICABLE = "not_applicable"


class SlotControl(StrEnum):
    READ_ONLY = "read_only"
    SELECT = "select"
    SEARCH_SELECT = "search_select"
    DATE = "date"
    NUMBER = "number"
    DERIVED = "derived"
    FIXED = "fixed"


class InformationSlot(BaseModel):
    """A reusable business fact, independent from any one ERPNext operation."""

    model_config = ConfigDict(extra="forbid")

    slot_id: str = Field(pattern=r"^slot\.[a-z0-9_.]+$")
    serial: int = Field(gt=0)
    label: str = Field(min_length=1)
    data_type: str = Field(min_length=1)
    entity_type: str | None = None
    description: str = Field(min_length=1)


class OperationTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(pattern=r"^op\.[a-z0-9_.]+$")
    capability_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    module: str = Field(min_length=1)
    tool: str = Field(min_length=1)
    write: bool = True


class OperationSlotBinding(BaseModel):
    """The operation-specific use of a reusable slot."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str
    slot_id: str
    position: int = Field(gt=0)
    scope: SlotScope
    target_path: str = Field(min_length=1)
    source: SlotSource
    control: SlotControl
    editable: bool = False
    lookup_doctype: str | None = None
    format_hint: str | None = None
    default_strategy: str | None = None
    source_path: str | None = None
    required: bool = True
    resolver: str | None = None
    fixed_value: Any = None
    derived_from: str | None = None
    constraint: str | None = None


class OperationRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    operation_id: str
    label: str
    expression: str
    message: str


class SlotEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot_id: str
    serial: int
    label: str
    scope: SlotScope
    target_path: str
    source: SlotSource
    control: SlotControl
    editable: bool
    lookup_doctype: str | None = None
    format_hint: str | None = None
    default_strategy: str | None = None
    required: bool
    status: SlotStatus
    value: Any = None
    values: list[Any] = Field(default_factory=list)
    reason: str = ""


class OperationEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: OperationTemplate
    status: str
    slots: list[SlotEvaluation]
    missing: list[str]
    invalid: list[str]
    blocked: list[str]
    rules: list[OperationRule]
    tool_call: dict[str, Any] | None = None


MATERIAL_REQUEST_OPERATION = OperationTemplate(
    operation_id="op.material_request.create",
    capability_id="material_request.create",
    label="新建采购类型材料申请草稿",
    module="buying",
    tool="erpnext.buying.create_material_request_draft",
)


INFORMATION_SLOTS = (
    InformationSlot(slot_id="slot.company", serial=1, label="公司", data_type="Link", entity_type="Company", description="当前员工正在操作的公司账套。"),
    InformationSlot(slot_id="slot.project", serial=2, label="项目", data_type="Link", entity_type="Project", description="材料实际归属的 ERPNext 项目。"),
    InformationSlot(slot_id="slot.warehouse", serial=3, label="目标仓库", data_type="Link", entity_type="Warehouse", description="材料到货或领用归属的标准仓库全称。"),
    InformationSlot(slot_id="slot.need_by_date", serial=4, label="需求日期", data_type="Date", description="材料最迟需要到位的日期。"),
    InformationSlot(slot_id="slot.item_code", serial=5, label="物料编码", data_type="Link", entity_type="Item", description="由物料 Resolver 返回的真实 Item 主键。"),
    InformationSlot(slot_id="slot.quantity", serial=6, label="数量", data_type="Decimal", description="本行申请数量，必须大于 0。"),
    InformationSlot(slot_id="slot.uom", serial=7, label="计量单位", data_type="Link", entity_type="UOM", description="物料主数据单位或用户明确选择的单位。"),
    InformationSlot(slot_id="slot.item_project", serial=8, label="明细项目", data_type="Link", entity_type="Project", description="每个明细行继承已确认的项目。"),
    InformationSlot(slot_id="slot.item_warehouse", serial=9, label="明细仓库", data_type="Link", entity_type="Warehouse", description="每个明细行继承已确认的目标仓库。"),
    InformationSlot(slot_id="slot.item_need_by_date", serial=10, label="明细需求日期", data_type="Date", description="每个明细行继承单据需求日期。"),
    InformationSlot(slot_id="slot.material_request_type", serial=11, label="申请类型", data_type="Enum", description="本操作固定为采购申请 Purchase。"),
)


MATERIAL_REQUEST_BINDINGS = (
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.company", position=1, scope=SlotScope.DOCUMENT, target_path="arguments.company", source=SlotSource.RUNTIME_CONTEXT, control=SlotControl.READ_ONLY, lookup_doctype="Company", source_path="context.company", default_strategy="当前登录身份所属公司", constraint="必须是当前员工可访问的 Company"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.project", position=2, scope=SlotScope.DOCUMENT, target_path="context.erpnext_project", source=SlotSource.RUNTIME_CONTEXT, control=SlotControl.SELECT, editable=True, lookup_doctype="Project", source_path="context.erpnext_project", resolver="project", default_strategy="当前工作台项目", constraint="只能从当前员工可访问的 Project 中选择"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.warehouse", position=3, scope=SlotScope.DOCUMENT, target_path="context.warehouse", source=SlotSource.RUNTIME_CONTEXT, control=SlotControl.SELECT, editable=True, lookup_doctype="Warehouse", source_path="context.warehouse", resolver="warehouse", default_strategy="所选项目的默认仓库", constraint="只能选择所选项目可用的 Warehouse"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.need_by_date", position=4, scope=SlotScope.DOCUMENT, target_path="arguments.schedule_date", source=SlotSource.USER_INPUT, control=SlotControl.DATE, editable=True, source_path="user.schedule_date", resolver="date", format_hint="YYYY-MM-DD", constraint="ISO 日期 YYYY-MM-DD"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.item_code", position=5, scope=SlotScope.ITEM, target_path="arguments.items[].item_code", source=SlotSource.RESOLVER, control=SlotControl.SEARCH_SELECT, editable=True, lookup_doctype="Item", source_path="items[].item_code", resolver="item", default_strategy="物料检索唯一命中时自动选择", constraint="禁止模型编造，必须存在于 Item"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.quantity", position=6, scope=SlotScope.ITEM, target_path="arguments.items[].qty", source=SlotSource.USER_INPUT, control=SlotControl.NUMBER, editable=True, source_path="items[].qty", format_hint="大于 0，最多 3 位小数", constraint="number > 0"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.uom", position=7, scope=SlotScope.ITEM, target_path="arguments.items[].uom", source=SlotSource.USER_CHOICE, control=SlotControl.SELECT, editable=True, lookup_doctype="UOM", source_path="items[].uom", resolver="uom", default_strategy="所选物料的库存单位", constraint="必须是物料允许的 UOM"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.item_project", position=8, scope=SlotScope.ITEM, target_path="arguments.items[].project", source=SlotSource.DERIVED, control=SlotControl.DERIVED, derived_from="slot.project", default_strategy="继承单据项目"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.item_warehouse", position=9, scope=SlotScope.ITEM, target_path="arguments.items[].warehouse", source=SlotSource.DERIVED, control=SlotControl.DERIVED, derived_from="slot.warehouse", default_strategy="继承单据仓库"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.item_need_by_date", position=10, scope=SlotScope.ITEM, target_path="arguments.items[].schedule_date", source=SlotSource.DERIVED, control=SlotControl.DERIVED, derived_from="slot.need_by_date", default_strategy="继承单据需求日期"),
    OperationSlotBinding(operation_id=MATERIAL_REQUEST_OPERATION.operation_id, slot_id="slot.material_request_type", position=11, scope=SlotScope.DOCUMENT, target_path="arguments.material_request_type", source=SlotSource.FIXED, control=SlotControl.FIXED, fixed_value="Purchase", default_strategy="操作模板固定值", constraint="enum: Purchase"),
)


MATERIAL_REQUEST_RULES = (
    OperationRule(rule_id="rule.mr.items", operation_id=MATERIAL_REQUEST_OPERATION.operation_id, label="至少一个明细", expression="len(items) >= 1", message="请至少选择一种物料。"),
    OperationRule(rule_id="rule.mr.qty", operation_id=MATERIAL_REQUEST_OPERATION.operation_id, label="数量为正数", expression="all(item.qty > 0)", message="每个物料的数量必须大于 0。"),
    OperationRule(rule_id="rule.mr.links", operation_id=MATERIAL_REQUEST_OPERATION.operation_id, label="业务主键已解析", expression="company/project/warehouse/item_code are resolved", message="公司、项目、仓库和物料必须来自真实数据。"),
    OperationRule(rule_id="rule.mr.date", operation_id=MATERIAL_REQUEST_OPERATION.operation_id, label="需求日期有效", expression="schedule_date is ISO date", message="需求日期必须使用 YYYY-MM-DD。"),
)


class MaterialRequestOperationCatalog:
    """Relational-style operation catalog for the first v0.4 vertical slice."""

    def __init__(self) -> None:
        self.operation = MATERIAL_REQUEST_OPERATION
        self.slots = {slot.slot_id: slot for slot in INFORMATION_SLOTS}
        self.bindings = MATERIAL_REQUEST_BINDINGS
        self.rules = MATERIAL_REQUEST_RULES

    def relations(self) -> dict[str, Any]:
        return {
            "operation_templates": [self.operation.model_dump(mode="json")],
            "information_slots": [slot.model_dump(mode="json") for slot in INFORMATION_SLOTS],
            "operation_slots": [binding.model_dump(mode="json") for binding in self.bindings],
            "operation_rules": [rule.model_dump(mode="json") for rule in self.rules],
        }

    def evaluate(self, facts: dict[str, Any]) -> OperationEvaluation:
        context = dict(facts.get("context") or {})
        user = dict(facts.get("user") or {})
        items = [dict(item) for item in facts.get("items") or [] if isinstance(item, dict)]
        slot_values: dict[str, Any] = {
            "slot.company": context.get("company"),
            "slot.project": context.get("erpnext_project") or context.get("project"),
            "slot.warehouse": context.get("warehouse"),
            "slot.need_by_date": user.get("schedule_date"),
            "slot.item_code": [item.get("item_code") for item in items],
            "slot.quantity": [item.get("qty") for item in items],
            "slot.uom": [item.get("uom") for item in items],
            "slot.item_project": [context.get("erpnext_project") or context.get("project") for _ in items],
            "slot.item_warehouse": [context.get("warehouse") for _ in items],
            "slot.item_need_by_date": [user.get("schedule_date") for _ in items],
            "slot.material_request_type": "Purchase",
        }
        evaluations = [self._evaluate_binding(binding, slot_values, len(items)) for binding in self.bindings]
        missing = [row.slot_id for row in evaluations if row.status == SlotStatus.MISSING]
        invalid = [row.slot_id for row in evaluations if row.status == SlotStatus.INVALID]
        blocked = [row.slot_id for row in evaluations if row.status == SlotStatus.BLOCKED]
        tool_call = None if missing or invalid or blocked else self._compile(context, user, items)
        return OperationEvaluation(
            operation=self.operation,
            status="ready" if tool_call else "needs_input",
            slots=evaluations,
            missing=missing,
            invalid=invalid,
            blocked=blocked,
            rules=list(self.rules),
            tool_call=tool_call,
        )

    def demo(self) -> dict[str, Any]:
        facts = {
            "context": {
                "company": "STEC (Demo)",
                "erpnext_project": "PROJ-0010",
                "warehouse": "合流1.3标仓库 - SD",
            },
            "user": {"schedule_date": date.today().isoformat()},
            "items": [{"item_code": "MAT-CEM-000008", "qty": 20, "uom": "包"}],
        }
        return {"relations": self.relations(), "facts": facts, "evaluation": self.evaluate(facts).model_dump(mode="json")}

    def _evaluate_binding(self, binding: OperationSlotBinding, values: dict[str, Any], item_count: int) -> SlotEvaluation:
        slot = self.slots[binding.slot_id]
        raw = values.get(binding.slot_id)
        sequence = raw if binding.scope == SlotScope.ITEM else []
        status = SlotStatus.RESOLVED
        reason = "字段已由确定来源提供。"
        if binding.scope == SlotScope.ITEM:
            if item_count == 0 or len(sequence) != item_count or any(value in (None, "") for value in sequence):
                if binding.source == SlotSource.DERIVED:
                    status = SlotStatus.BLOCKED
                    reason = f"等待上游字段 {binding.derived_from}。"
                else:
                    status = SlotStatus.MISSING
                    reason = "每个物料明细都必须提供该字段。"
            elif binding.slot_id == "slot.quantity" and any(not _positive_number(value) for value in sequence):
                status = SlotStatus.INVALID
                reason = "数量必须是大于 0 的数字。"
        elif raw in (None, "") and binding.required:
            status = SlotStatus.MISSING
            reason = "该操作缺少必填字段。"
        elif binding.slot_id == "slot.need_by_date" and raw not in (None, "") and not _iso_date(raw):
            status = SlotStatus.INVALID
            reason = "日期必须使用 YYYY-MM-DD。"
        return SlotEvaluation(
            slot_id=slot.slot_id,
            serial=slot.serial,
            label=slot.label,
            scope=binding.scope,
            target_path=binding.target_path,
            source=binding.source,
            control=binding.control,
            editable=binding.editable,
            lookup_doctype=binding.lookup_doctype,
            format_hint=binding.format_hint,
            default_strategy=binding.default_strategy,
            required=binding.required,
            status=status,
            value=None if binding.scope == SlotScope.ITEM else raw,
            values=sequence if binding.scope == SlotScope.ITEM else [],
            reason=reason,
        )

    def _compile(self, context: dict[str, Any], user: dict[str, Any], items: list[dict[str, Any]]) -> dict[str, Any]:
        project = context.get("erpnext_project") or context.get("project")
        warehouse = context.get("warehouse")
        schedule_date = user.get("schedule_date")
        return {
            "tool": self.operation.tool,
            "arguments": {
                "material_request_type": "Purchase",
                "schedule_date": schedule_date,
                "company": context.get("company"),
                "items": [
                    {
                        "item_code": item.get("item_code"),
                        "qty": item.get("qty"),
                        "uom": item.get("uom"),
                        "project": project,
                        "warehouse": warehouse,
                        "schedule_date": schedule_date,
                    }
                    for item in items
                ],
            },
        }


def _positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _iso_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value))
        return True
    except (TypeError, ValueError):
        return False
