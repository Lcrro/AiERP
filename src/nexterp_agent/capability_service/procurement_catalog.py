from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProcurementOperationSeed:
    capability_id: str
    capability_label: str
    capability_summary: str
    operation_id: str
    operation_label: str
    operation_summary: str
    guide: str
    usage_conditions: str
    prohibitions: str
    examples: tuple[str, ...]
    aliases: tuple[str, ...]
    goal: str
    tool_name: str
    compiler_key: str
    source_doctypes: tuple[str, ...]
    slots: tuple[dict[str, Any], ...]
    rules: tuple[tuple[str, str, str], ...]


def _slot(
    slot_id: str,
    label: str,
    position: int,
    *,
    source: str,
    control: str,
    target: str,
    required: bool = True,
    lookup_doctype: str | None = None,
    source_path: str | None = None,
    format_hint: str | None = None,
    constraint: str | None = None,
) -> dict[str, Any]:
    return {
        "slot_id": slot_id,
        "label": label,
        "description": constraint or label,
        "position": position,
        "scope": "document",
        "target_path": target,
        "source": source,
        "control": control,
        "editable": source in {"user_input", "user_choice"},
        "lookup_doctype": lookup_doctype,
        "format_hint": format_hint,
        "default_strategy": None,
        "source_path": source_path,
        "required": required,
        "resolver": lookup_doctype.casefold().replace(" ", "_") if lookup_doctype else None,
        "fixed_value": None,
        "derived_from": None,
        "constraint": constraint,
    }


PROCUREMENT_CHAIN: tuple[ProcurementOperationSeed, ...] = (
    ProcurementOperationSeed(
        capability_id="cap.request_for_quotation",
        capability_label="询价",
        capability_summary="从已提交材料申请向一家或多家真实供应商发起询价。",
        operation_id="op.request_for_quotation.from_material_request",
        operation_label="从材料申请创建询价草稿",
        operation_summary="读取已提交材料申请并保留来源行，解析供应商后创建询价草稿。",
        guide=(
            "先提供已提交材料申请单号和候选供应商。Nexterp 会实时读取材料申请，"
            "自动带出公司、物料、数量、单位、项目、仓库和需求日期。"
            "若供应商名称不唯一，应让员工从候选中选择。"
        ),
        usage_conditions="材料申请必须已提交、属于当前员工可访问公司且存在可询价明细。",
        prohibitions="不得复制用户口述明细覆盖来源单据；不得编造供应商主键；不得跳过确认。",
        examples=("把 MAT-MR-2026-00015 发给测试供应商询价",),
        aliases=("询价", "发起询价", "从材料申请询价", "创建询价单", "RFQ"),
        goal="create_rfq_from_material_request",
        tool_name="erpnext.buying.create_request_for_quotation_draft",
        compiler_key="procurement.create_rfq_from_material_request.v1",
        source_doctypes=("Material Request",),
        slots=(
            _slot("slot.source_material_request", "来源材料申请", 1, source="source_document", control="search_select", target="source.material_request", lookup_doctype="Material Request", constraint="必须是已提交的采购类型材料申请"),
            _slot("slot.suppliers", "询价供应商", 2, source="user_choice", control="search_select", target="arguments.suppliers", lookup_doctype="Supplier", constraint="至少一家真实且可用的供应商"),
            _slot("slot.transaction_date", "询价日期", 3, source="system_generated", control="read_only", target="arguments.transaction_date", format_hint="YYYY-MM-DD"),
            _slot("slot.need_by_date", "需求日期", 4, source="source_document", control="read_only", target="arguments.schedule_date", format_hint="YYYY-MM-DD"),
            _slot("slot.source_items", "询价明细", 5, source="source_document", control="read_only", target="arguments.items", constraint="保留材料申请父行与子行引用"),
            _slot("slot.supplier_message", "给供应商的说明", 6, source="user_input", control="select", target="arguments.message_for_supplier", required=False),
        ),
        rules=(
            ("rule.rfq.source_submitted", "来源材料申请已提交", "只有已提交的采购材料申请可以转询价。"),
            ("rule.rfq.suppliers", "供应商已解析", "至少选择一家真实供应商。"),
            ("rule.rfq.lineage", "来源关系保留", "每个询价明细必须保留材料申请来源行。"),
        ),
    ),
    ProcurementOperationSeed(
        capability_id="cap.supplier_quotation",
        capability_label="供应商报价",
        capability_summary="依据已提交询价记录某一家供应商的报价。",
        operation_id="op.supplier_quotation.from_request_for_quotation",
        operation_label="从询价创建供应商报价草稿",
        operation_summary="读取已提交询价及其来源行，为唯一供应商记录逐项报价。",
        guide=(
            "提供已提交询价单号、唯一供应商和报价。报价可以按来源明细行填写；"
            "若只给物料编码，Nexterp 仅在该编码对应唯一来源行时自动绑定。"
        ),
        usage_conditions="询价必须已提交；供应商唯一；每个选中明细的单价为非负数。",
        prohibitions="不得把报价有效期当成交货日期；不得猜测来源明细行；不得跳过确认。",
        examples=("记录测试供应商对 PUR-RFQ-2026-00001 的报价，每包 32 元",),
        aliases=("供应商报价", "录入报价", "报价单", "从询价报价", "Supplier Quotation"),
        goal="create_supplier_quotation_from_rfq",
        tool_name="erpnext.buying.create_supplier_quotation_draft",
        compiler_key="procurement.create_supplier_quotation_from_rfq.v1",
        source_doctypes=("Request for Quotation",),
        slots=(
            _slot("slot.source_rfq", "来源询价单", 1, source="source_document", control="search_select", target="source.request_for_quotation", lookup_doctype="Request for Quotation", constraint="必须是已提交询价单"),
            _slot("slot.supplier", "报价供应商", 2, source="user_choice", control="search_select", target="arguments.supplier", lookup_doctype="Supplier", constraint="必须唯一确定"),
            _slot("slot.quote_items", "报价明细", 3, source="user_input", control="number", target="arguments.items", constraint="来源行与非负单价逐项对应"),
            _slot("slot.valid_till", "报价有效期", 4, source="user_input", control="date", target="arguments.valid_till", required=False, format_hint="YYYY-MM-DD"),
            _slot("slot.currency", "币种", 5, source="user_choice", control="select", target="arguments.currency", required=False, lookup_doctype="Currency"),
            _slot("slot.transaction_date", "报价日期", 6, source="system_generated", control="read_only", target="arguments.transaction_date", format_hint="YYYY-MM-DD"),
        ),
        rules=(
            ("rule.sq.source_submitted", "来源询价已提交", "只有已提交询价可以生成供应商报价。"),
            ("rule.sq.one_supplier", "供应商唯一", "一张供应商报价只能对应一家供应商。"),
            ("rule.sq.rates", "报价非负", "报价单价不能小于 0。"),
        ),
    ),
    ProcurementOperationSeed(
        capability_id="cap.purchase_order",
        capability_label="采购订单",
        capability_summary="从有效的已提交供应商报价生成采购订单。",
        operation_id="op.purchase_order.from_supplier_quotation",
        operation_label="从供应商报价创建采购订单草稿",
        operation_summary="校验报价状态、有效期和可转数量后，保留报价来源创建采购订单草稿。",
        guide=(
            "提供已提交供应商报价单号。默认转换全部仍可下单的报价行；"
            "部分下单时提供来源行或可唯一对应的物料及数量。交货日期可由员工补充。"
        ),
        usage_conditions="供应商报价已提交、未过有效期并且仍有可转数量。",
        prohibitions="不得改用通用采购订单工具丢失报价来源；不得超过剩余可转数量。",
        examples=("把 PUR-SQTN-2026-00001 转成采购订单，下周三到货",),
        aliases=("采购订单", "从报价下单", "供应商报价转采购订单", "PO"),
        goal="create_purchase_order_from_supplier_quotation",
        tool_name="erpnext.buying.create_purchase_order_from_supplier_quotation_draft",
        compiler_key="procurement.create_purchase_order_from_supplier_quotation.v1",
        source_doctypes=("Supplier Quotation",),
        slots=(
            _slot("slot.source_supplier_quotation", "来源供应商报价", 1, source="source_document", control="search_select", target="arguments.supplier_quotation", lookup_doctype="Supplier Quotation", constraint="必须已提交且有效"),
            _slot("slot.selected_items", "下单明细", 2, source="user_choice", control="select", target="arguments.selected_items", required=False, constraint="留空表示全部可转行；部分选择必须绑定来源行"),
            _slot("slot.need_by_date", "交货日期", 3, source="user_input", control="date", target="arguments.schedule_date", required=False, format_hint="YYYY-MM-DD"),
            _slot("slot.transaction_date", "下单日期", 4, source="system_generated", control="read_only", target="arguments.transaction_date", format_hint="YYYY-MM-DD"),
        ),
        rules=(
            ("rule.po.quotation_submitted", "供应商报价已提交", "采购订单只能从已提交报价生成。"),
            ("rule.po.quotation_valid", "报价仍有效", "已过有效期的报价不能直接下单。"),
            ("rule.po.remaining_qty", "可转数量足够", "下单数量不得超过报价剩余可转数量。"),
            ("rule.po.lineage", "报价来源保留", "采购订单明细必须保留供应商报价来源行。"),
        ),
    ),
    ProcurementOperationSeed(
        capability_id="cap.purchase_receipt",
        capability_label="采购收货",
        capability_summary="从已提交采购订单记录实际到货。",
        operation_id="op.purchase_receipt.from_purchase_order",
        operation_label="从采购订单创建收货草稿",
        operation_summary="读取采购订单未收数量，按实际到货行创建采购收货草稿。",
        guide=(
            "提供已提交采购订单单号。整单到货可以不提供明细；"
            "分批到货时提供来源行或唯一物料及本次实收数量、仓库。"
        ),
        usage_conditions="采购订单已提交且至少一行仍有未收数量。",
        prohibitions="不得超过未收数量；不得丢失采购订单来源；不得把计划数量当作实收数量。",
        examples=("PUR-ORD-2026-00004 今天全部到货，帮我建收货草稿",),
        aliases=("采购收货", "到货", "收货入库", "采购订单转收货", "Purchase Receipt"),
        goal="create_purchase_receipt_from_purchase_order",
        tool_name="erpnext.buying.create_purchase_receipt_from_purchase_order_draft",
        compiler_key="procurement.create_purchase_receipt_from_purchase_order.v1",
        source_doctypes=("Purchase Order",),
        slots=(
            _slot("slot.source_purchase_order", "来源采购订单", 1, source="source_document", control="search_select", target="arguments.purchase_order", lookup_doctype="Purchase Order", constraint="必须是已提交采购订单"),
            _slot("slot.receipt_items", "本次收货明细", 2, source="user_choice", control="select", target="arguments.selected_items", required=False, constraint="留空表示全部未收数量；部分收货必须绑定来源行"),
            _slot("slot.posting_date", "收货日期", 3, source="user_input", control="date", target="arguments.posting_date", required=False, format_hint="YYYY-MM-DD"),
            _slot("slot.warehouse", "收货仓库", 4, source="user_choice", control="search_select", target="arguments.selected_items[].warehouse", required=False, lookup_doctype="Warehouse", constraint="默认沿用采购订单行仓库"),
        ),
        rules=(
            ("rule.pr.po_submitted", "采购订单已提交", "只有已提交采购订单可以收货。"),
            ("rule.pr.remaining_qty", "未收数量足够", "本次收货数量不得超过订单未收数量。"),
            ("rule.pr.lineage", "订单来源保留", "收货明细必须保留采购订单来源行。"),
        ),
    ),
    ProcurementOperationSeed(
        capability_id="cap.purchase_return",
        capability_label="采购退货",
        capability_summary="从已提交采购收货生成整单或部分退货。",
        operation_id="op.purchase_return.from_purchase_receipt",
        operation_label="从采购收货创建退货草稿",
        operation_summary="读取可退数量，按整单或指定明细创建反向采购收货草稿。",
        guide=(
            "提供已提交采购收货单号，并明确整单退货或部分退货。"
            "部分退货必须给出来源行或可唯一对应的物料、退货数量和原因。"
        ),
        usage_conditions="采购收货已提交、不是退货单且存在可退数量。",
        prohibitions="不得超过可退数量；不得对退货单再次退货；不得省略部分退货范围。",
        examples=("MAT-PRE-2026-00004 规格不符，全部退货",),
        aliases=("采购退货", "退供应商", "整单退货", "收货退回", "Purchase Return"),
        goal="create_purchase_return_from_receipt",
        tool_name="erpnext.buying.create_purchase_receipt_return_draft",
        compiler_key="procurement.create_purchase_return_from_receipt.v1",
        source_doctypes=("Purchase Receipt",),
        slots=(
            _slot("slot.source_purchase_receipt", "来源采购收货", 1, source="source_document", control="search_select", target="arguments.purchase_receipt", lookup_doctype="Purchase Receipt", constraint="必须是已提交且可退的非退货单"),
            _slot("slot.full_return", "是否整单退货", 2, source="user_input", control="select", target="arguments.full_return", constraint="整单或部分必须明确"),
            _slot("slot.return_items", "退货明细", 3, source="user_choice", control="select", target="arguments.items", required=False, constraint="部分退货时必填并绑定来源行"),
            _slot("slot.posting_date", "退货日期", 4, source="user_input", control="date", target="arguments.posting_date", required=False, format_hint="YYYY-MM-DD"),
            _slot("slot.return_reason", "退货原因", 5, source="user_input", control="select", target="arguments.reason", required=False),
        ),
        rules=(
            ("rule.return.receipt_submitted", "采购收货已提交", "只有已提交采购收货可以退货。"),
            ("rule.return.scope", "退货范围明确", "必须明确整单退货或部分退货明细。"),
            ("rule.return.quantity", "可退数量足够", "退货数量不得超过当前可退数量。"),
            ("rule.return.lineage", "退货来源保留", "退货单必须保留 return_against 和来源明细。"),
        ),
    ),
)


OPERATION_BY_ID = {seed.operation_id: seed for seed in PROCUREMENT_CHAIN}
CAPABILITY_OPERATION_IDS = {seed.capability_id: seed.operation_id for seed in PROCUREMENT_CHAIN}
PROCUREMENT_OPERATION_IDS = tuple(OPERATION_BY_ID)


def operation_goal(operation_id: str) -> str:
    if operation_id == "op.material_request.create":
        return "create_material_request"
    return OPERATION_BY_ID[operation_id].goal


def operation_capability(operation_id: str) -> str:
    if operation_id == "op.material_request.create":
        return "material_request.create"
    return OPERATION_BY_ID[operation_id].capability_id.removeprefix("cap.")
