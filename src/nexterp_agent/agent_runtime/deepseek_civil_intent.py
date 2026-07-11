from __future__ import annotations

import json
from typing import Any

from .deepseek_material_request import DeepSeekSettings, call_deepseek_json


CIVIL_INTENTS = {
    "create_material_request",
    "submit_document",
    "create_purchase_order",
    "create_purchase_receipt",
    "record_receipt_discrepancy",
    "create_purchase_return",
    "create_material_issue",
    "create_purchase_invoice",
    "query_stock",
    "query_accounts_payable",
    "query_project_cost",
    "manager_summary",
    "unknown",
}


def build_civil_intent_messages(user_text: str, *, context: dict[str, Any] | None = None) -> list[dict[str, str]]:
    schema = {
        "intent": " | ".join(sorted(CIVIL_INTENTS)),
        "document_type": "Material Request | Purchase Order | Purchase Receipt | Purchase Invoice | Stock Entry | 空",
        "document_name": "用户明确说出的单号或空，禁止编造",
        "project_text": "口头项目名或空",
        "warehouse_text": "口头仓库名或空",
        "supplier_text": "供应商口头名称或空",
        "schedule_text": "今天、明天或用户原话日期或空",
        "posting_date_text": "过账日期原话或空",
        "items": [
            {
                "raw_item_text": "物料原话，不要改成编码",
                "qty": "数字或 null",
                "uom": "单位或空",
                "specs": {"用户明确说出的规格字段": "规格值"},
            }
        ],
        "description": "差异、退货、领料或操作原因",
        "discrepancy_type": "规格不符 | 数量不符 | 质量问题 | 其他 | 空",
        "full_return": "boolean",
        "assigned_to_text": "负责人姓名或邮箱或空",
        "from_date_text": "开始日期原话或空",
        "to_date_text": "结束日期原话或空",
        "questions": ["模型认为缺失的业务信息"],
        "confidence": 0.0,
    }
    return [
        {
            "role": "system",
            "content": (
                "你是土木工程 ERPNext 业务意图抽取器。你只抽取业务意图和用户原话槽位，不选择工具，"
                "不填写 ERPNext 编码，不编造单号、项目主键、仓库全称、供应商主键或物料编码。"
                "“提交这张单”归 submit_document；材料申请转采购订单归 create_purchase_order；"
                "采购订单到货归 create_purchase_receipt；到货不符归 record_receipt_discrepancy；"
                "退给供应商归 create_purchase_return；项目领料归 create_material_issue；"
                "收货后开票归 create_purchase_invoice。只输出 JSON object。"
            ),
        },
        {
            "role": "system",
            "content": json.dumps({"output_schema": schema, "runtime_context": context or {}}, ensure_ascii=False),
        },
        {"role": "user", "content": user_text},
    ]


def extract_civil_intent_with_deepseek(
    user_text: str,
    *,
    context: dict[str, Any] | None = None,
    settings: DeepSeekSettings | None = None,
) -> dict[str, Any]:
    payload = call_deepseek_json(build_civil_intent_messages(user_text, context=context), settings=settings)
    return validate_civil_intent(payload)


def validate_civil_intent(intent: dict[str, Any]) -> dict[str, Any]:
    name = intent.get("intent")
    if name not in CIVIL_INTENTS:
        raise ValueError(f"Unsupported civil intent: {name}")
    items = intent.get("items")
    if items is not None and not isinstance(items, list):
        raise ValueError("civil intent items must be an array")
    for index, item in enumerate(items or [], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"items[{index}] must be an object")
        qty = item.get("qty")
        if qty is not None and (not isinstance(qty, (int, float)) or qty <= 0):
            raise ValueError(f"items[{index}].qty must be a positive number")
        if item.get("specs") is not None and not isinstance(item["specs"], dict):
            raise ValueError(f"items[{index}].specs must be an object")
    if not isinstance(intent.get("questions") or [], list):
        raise ValueError("civil intent questions must be an array")
    return intent
