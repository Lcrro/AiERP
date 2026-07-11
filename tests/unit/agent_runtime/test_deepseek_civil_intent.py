from __future__ import annotations

import pytest

from nexterp_agent.agent_runtime.deepseek_civil_intent import build_civil_intent_messages, validate_civil_intent


def test_prompt_forbids_model_generated_erpnext_ids() -> None:
    messages = build_civil_intent_messages("把这张材料申请转成采购订单")
    prompt = "\n".join(message["content"] for message in messages)

    assert "不填写 ERPNext 编码" in prompt
    assert "不选择工具" in prompt
    assert "create_purchase_order" in prompt


def test_validator_accepts_purchase_receipt_intent() -> None:
    payload = {
        "intent": "create_purchase_receipt",
        "document_type": "Purchase Order",
        "document_name": "PUR-ORD-2026-00001",
        "items": [],
        "questions": [],
    }

    assert validate_civil_intent(payload) is payload


def test_validator_rejects_unknown_intent_name() -> None:
    with pytest.raises(ValueError):
        validate_civil_intent({"intent": "invent_database_rows", "questions": []})


@pytest.mark.parametrize(
    "intent",
    ["create_request_for_quotation", "query_pending_material_requests", "query_overdue_purchase_orders"],
)
def test_validator_accepts_day_scenario_intents(intent: str) -> None:
    assert validate_civil_intent({"intent": intent, "items": [], "questions": []})["intent"] == intent
