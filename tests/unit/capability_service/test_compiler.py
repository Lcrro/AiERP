from __future__ import annotations

from typing import Any

from nexterp_agent.capability_service.compiler import OperationCompilerRegistry
from tests.unit.capability_service.test_manual_service import material_request_slots


def bundle() -> dict[str, Any]:
    return {
        "operation": {
            "compiler_key": "material_request.create.v1",
            "tool_name": "erpnext.buying.create_material_request_draft",
        },
        "slots": material_request_slots(),
        "rules": [{"rule_id": "rule.mr.items"}],
    }


def test_database_bindings_drive_compiled_tool_call() -> None:
    catalog = bundle()
    catalog["slots"][0]["target_path"] = "arguments.company_override"
    evaluation = OperationCompilerRegistry().compile(catalog, {
        "context": {"company": "STEC", "erpnext_project": "PROJ-0010", "warehouse": "WH-1"},
        "user": {"schedule_date": "2026-08-04"},
        "items": [{"item_code": "ITEM-1", "qty": 2, "uom": "个"}],
    })

    assert evaluation.status == "ready"
    assert evaluation.tool_call is not None
    assert evaluation.tool_call["arguments"]["company_override"] == "STEC"
    assert "company" not in evaluation.tool_call["arguments"]
    assert evaluation.tool_call["arguments"]["items"][0] == {
        "item_code": "ITEM-1", "qty": 2, "uom": "个",
        "project": "PROJ-0010", "warehouse": "WH-1", "schedule_date": "2026-08-04",
    }


def test_database_binding_validation_reports_missing_slot() -> None:
    evaluation = OperationCompilerRegistry().compile(bundle(), {
        "context": {"company": "STEC", "erpnext_project": "PROJ-0010", "warehouse": "WH-1"},
        "user": {"schedule_date": "2026-08-04"},
        "items": [{"item_code": "ITEM-1", "qty": 2}],
    })

    assert evaluation.tool_call is None
    assert "slot.uom" in evaluation.missing
