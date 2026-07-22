from __future__ import annotations

from nexterp_agent.agent_runtime.operation_catalog import (
    MaterialRequestOperationCatalog,
    SlotSource,
    SlotStatus,
)


def complete_facts() -> dict:
    return {
        "context": {
            "company": "STEC (Demo)",
            "erpnext_project": "PROJ-0010",
            "warehouse": "合流1.3标仓库 - SD",
        },
        "user": {"schedule_date": "2026-07-25"},
        "items": [{"item_code": "MAT-CEM-000008", "qty": 20, "uom": "包"}],
    }


def test_material_request_operation_is_normalized_into_relations() -> None:
    catalog = MaterialRequestOperationCatalog()

    relations = catalog.relations()

    assert len(relations["operation_templates"]) == 1
    assert len(relations["information_slots"]) == 11
    assert len(relations["operation_slots"]) == 11
    assert len(relations["operation_rules"]) == 4
    assert {row["slot_id"] for row in relations["operation_slots"]} == {
        row["slot_id"] for row in relations["information_slots"]
    }


def test_complete_material_request_facts_compile_exact_tool_call() -> None:
    evaluation = MaterialRequestOperationCatalog().evaluate(complete_facts())

    assert evaluation.status == "ready"
    assert evaluation.missing == []
    assert evaluation.invalid == []
    assert evaluation.blocked == []
    assert evaluation.tool_call == {
        "tool": "erpnext.buying.create_material_request_draft",
        "arguments": {
            "material_request_type": "Purchase",
            "schedule_date": "2026-07-25",
            "company": "STEC (Demo)",
            "items": [{
                "item_code": "MAT-CEM-000008",
                "qty": 20,
                "uom": "包",
                "project": "PROJ-0010",
                "warehouse": "合流1.3标仓库 - SD",
                "schedule_date": "2026-07-25",
            }],
        },
    }
    by_id = {slot.slot_id: slot for slot in evaluation.slots}
    assert by_id["slot.item_code"].source == SlotSource.RESOLVER
    assert by_id["slot.item_project"].source == SlotSource.DERIVED
    assert by_id["slot.material_request_type"].source == SlotSource.FIXED


def test_missing_resolver_fields_prevent_tool_call_compilation() -> None:
    facts = complete_facts()
    facts["context"]["erpnext_project"] = ""
    facts["context"]["warehouse"] = ""
    facts["items"][0]["item_code"] = ""

    evaluation = MaterialRequestOperationCatalog().evaluate(facts)

    assert evaluation.status == "needs_input"
    assert evaluation.tool_call is None
    assert {"slot.project", "slot.warehouse", "slot.item_code"}.issubset(evaluation.missing)
    assert evaluation.blocked == ["slot.item_project", "slot.item_warehouse"]


def test_invalid_quantity_and_date_are_reported_at_field_level() -> None:
    facts = complete_facts()
    facts["user"]["schedule_date"] = "25/07/2026"
    facts["items"][0]["qty"] = 0

    evaluation = MaterialRequestOperationCatalog().evaluate(facts)
    by_id = {slot.slot_id: slot for slot in evaluation.slots}

    assert evaluation.tool_call is None
    assert by_id["slot.need_by_date"].status == SlotStatus.INVALID
    assert by_id["slot.quantity"].status == SlotStatus.INVALID
    assert "slot.need_by_date" in evaluation.invalid
    assert "slot.quantity" in evaluation.invalid


def test_multiple_items_reuse_the_same_item_scope_slots() -> None:
    facts = complete_facts()
    facts["items"].append({"item_code": "SAFE-000005", "qty": 100, "uom": "双"})

    evaluation = MaterialRequestOperationCatalog().evaluate(facts)
    item_code = next(slot for slot in evaluation.slots if slot.slot_id == "slot.item_code")

    assert evaluation.status == "ready"
    assert item_code.values == ["MAT-CEM-000008", "SAFE-000005"]
    assert len(evaluation.tool_call["arguments"]["items"]) == 2
