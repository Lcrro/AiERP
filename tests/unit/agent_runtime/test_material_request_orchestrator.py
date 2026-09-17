from __future__ import annotations

from nexterp_agent.agent_runtime.material_request_orchestrator import compose_material_request_tool_call
from nexterp_agent.agent_runtime.deepseek_material_request import MATERIAL_REQUEST_TOOL
from nexterp_agent.item_master.release_resolver import ReleaseMaterialResolver


BASE_CONTEXT = {
    "company": "STEC (Demo)",
    "default_schedule_date": "2026-06-18",
    "project_candidates": [{"name": "PROJ-0010", "label": "合流1.3标"}],
    "warehouse_candidates": [{"name": "合流1.3标仓库 - SD", "label": "合流1.3标仓"}],
}


def test_ready_intent_composes_material_request_tool_call(tmp_path) -> None:
    catalog = tmp_path / "catalog.tsv"
    catalog.write_text(
        "item_code\titem_name\tsku_name\trequired_specs\tstock_uom\tstatus\tagent_use_policy\tapproved_aliases\n"
        "100031850101041\t六角螺栓\t六角螺栓 M12×40\t规格=M12×40；性能/质量等级=6.8级\t个\tactive\tauto_select_allowed\t6.8级螺栓 M12*40\n",
        encoding="utf-8",
    )
    resolver = ReleaseMaterialResolver(catalog)
    intent = {
        "intent": "create_material_request",
        "items": [{"raw_item_text": "6.8级螺栓 M12*40", "qty": 10, "uom": "个"}],
    }

    result = compose_material_request_tool_call(intent, context=BASE_CONTEXT, resolver=resolver)

    assert result["status"] == "ready"
    assert result["tool_call"]["tool"] == MATERIAL_REQUEST_TOOL
    arguments = result["tool_call"]["arguments"]
    assert arguments["company"] == "STEC (Demo)"
    assert arguments["schedule_date"] == "2026-06-18"
    assert arguments["items"] == [
        {
            "item_code": "100031850101041",
            "qty": 10,
            "uom": "个",
            "warehouse": "合流1.3标仓库 - SD",
            "schedule_date": "2026-06-18",
            "project": "PROJ-0010",
        }
    ]


def test_ambiguous_material_requires_user_selection() -> None:
    intent = {
        "intent": "create_material_request",
        "items": [{"raw_item_text": "帆布手套", "qty": 100, "uom": "双"}],
    }

    result = compose_material_request_tool_call(intent, context=BASE_CONTEXT)

    assert result["status"] == "needs_material_selection"
    assert "tool_call" not in result
    pending = result["pending_resolutions"][0]["resolution"]
    assert pending["status"] == "needs_confirmation"
    assert {candidate["item_code"] for candidate in pending["candidates"]} >= {
        "SAFE-000096",
        "SAFE-000005",
        "SAFE-000001",
    }


def test_missing_material_enters_item_creation_flow() -> None:
    intent = {
        "intent": "create_material_request",
        "items": [{"raw_item_text": "星际泡泡机", "qty": 1, "uom": "台"}],
    }

    result = compose_material_request_tool_call(intent, context=BASE_CONTEXT)

    assert result["status"] == "needs_item_creation"
    assert "tool_call" not in result
    assert result["item_creation_requests"][0]["next_action"] == "start_item_creation_flow"


def test_missing_required_runtime_context_blocks_tool_call() -> None:
    intent = {
        "intent": "create_material_request",
        "items": [{"raw_item_text": "6.8级螺栓 M12*40", "qty": 10}],
    }

    result = compose_material_request_tool_call(intent, context={"company": "STEC (Demo)"})

    assert result["status"] == "needs_clarification"
    assert "tool_call" not in result
    assert any("项目" in question for question in result["questions"])
    assert any("仓库" in question for question in result["questions"])
