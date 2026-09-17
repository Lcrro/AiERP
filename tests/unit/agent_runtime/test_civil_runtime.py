from __future__ import annotations

from datetime import date
from pathlib import Path

from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime
from nexterp_agent.agent_runtime.session import RuntimeSessionStore


def complete_intent(_: str, *, context=None) -> dict:
    return {
        "intent": "create_material_request",
        "project_text": "合流1.3标",
        "warehouse_text": "合流1.3标仓库",
        "schedule_text": "明天",
        "schedule_date": "",
        "items": [{"raw_item_text": "6.8级螺栓 M12*40", "qty": 100, "uom": "个", "specs": {}}],
        "questions": [],
        "confidence": 0.98,
    }


def ambiguous_intent(_: str, *, context=None) -> dict:
    intent = complete_intent(_, context=context)
    intent["items"] = [{"raw_item_text": "帆布手套", "qty": 100, "uom": "双", "specs": {}}]
    return intent


def model_with_wrong_relative_date(_: str, *, context=None) -> dict:
    intent = complete_intent(_, context=context)
    intent["schedule_date"] = "2026-07-12"
    return intent


def test_runtime_requires_material_selection_before_tool_call(tmp_path: Path) -> None:
    runtime = CivilAgentRuntime(
        intent_extractor=complete_intent,
        session_store=RuntimeSessionStore(tmp_path),
    )

    result = runtime.run_once(
        "合流1.3标明天需要100个6.8级螺栓M12*40",
        user="mao.xiaoquan@stec-up.local",
        today=date(2026, 7, 10),
    )

    assert result.status == "needs_material_selection"
    assert result.tool_call is None
    assert result.candidates


def test_runtime_returns_candidates_for_ambiguous_material(tmp_path: Path) -> None:
    runtime = CivilAgentRuntime(
        intent_extractor=ambiguous_intent,
        session_store=RuntimeSessionStore(tmp_path),
    )

    result = runtime.run_once(
        "合流项目明天需要100双帆布手套",
        user="mao.xiaoquan@stec-up.local",
        today=date(2026, 7, 10),
    )

    assert result.status == "needs_material_selection"
    assert result.candidates
    assert result.tool_call is None


def test_runtime_does_not_bypass_material_selection_for_relative_dates(tmp_path: Path) -> None:
    runtime = CivilAgentRuntime(
        intent_extractor=model_with_wrong_relative_date,
        session_store=RuntimeSessionStore(tmp_path),
    )

    result = runtime.run_once(
        "合流项目明天需要100个6.8级螺栓M12*40",
        user="mao.xiaoquan@stec-up.local",
        today=date(2026, 7, 10),
    )

    assert result.status == "needs_material_selection"
    assert result.tool_call is None
