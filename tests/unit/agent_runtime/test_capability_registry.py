from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from nexterp_agent.agent_runtime.capability_registry import CapabilityRegistry, ProcurementIntentModel
from nexterp_agent.agent_runtime.deepseek_agent_runtime import (
    DeepSeekAgentRuntime,
    _capability_draft,
    _clear_capability_draft,
    _merge_capability_intent,
)
from nexterp_agent.agent_runtime.session import RuntimeSessionState, RuntimeSessionStore
from nexterp_agent.agent_runtime.tool_access import make_tool_access_policy
from nexterp_agent.erpnext.schemas import ToolResult


class PlannerSequence:
    def __init__(self, actions: list[dict]) -> None:
        self.actions = list(actions)
        self.messages: list[list[dict[str, str]]] = []

    def __call__(self, messages):
        self.messages.append(messages)
        return self.actions.pop(0)


class ProjectDocumentClient:
    def get_document(self, doctype: str, name: str) -> ToolResult:
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, "project_name": name})


def test_registry_contains_twenty_focused_capabilities() -> None:
    registry = CapabilityRegistry()

    assert len(registry.definitions) == 20
    assert len(registry.protected_write_tools) == 15
    assert len(registry.capability_tools) == 21
    assert "erpnext.stock.get_balance" in registry.capability_tools
    material_request = registry.get("material_request.create")
    properties = material_request.guide()["intent_schema"]["properties"]
    assert "items" in properties
    assert "schedule_date" in properties
    assert "bill_no" not in properties
    assert "supplier" not in properties


def test_each_capability_has_a_distinct_pydantic_intent_model() -> None:
    registry = CapabilityRegistry()

    assert len({definition.intent_model for definition in registry.definitions}) == 20
    for definition in registry.definitions:
        parsed_definition, payload = registry.validate_intent(definition.capability_id, {})
        assert parsed_definition is definition
        assert payload["goal"] == definition.goal


def test_parse_intent_returns_module_execution_model_without_expanding_guide() -> None:
    registry = CapabilityRegistry()

    definition, intent = registry.parse_intent(
        "material_request.create",
        {
            "items": [{"item_code": "MAT-CEM-000008", "qty": 20, "uom": "包"}],
            "schedule_date": "2026-07-25",
        },
    )

    assert isinstance(intent, ProcurementIntentModel)
    assert intent.goal == "create_material_request"
    assert intent.source_documents == []
    assert intent.items[0].item_code == "MAT-CEM-000008"
    guide_fields = definition.guide()["intent_schema"]["properties"]
    assert "source_documents" not in guide_fields
    assert "supplier" not in guide_fields


def test_capability_intent_rejects_unknown_fields_and_invalid_values() -> None:
    registry = CapabilityRegistry()

    with pytest.raises(ValidationError):
        registry.validate_intent("material_request.create", {"bill_no": "not-allowed"})
    with pytest.raises(ValidationError):
        registry.validate_intent("material_request.create", {"schedule_date": "20/07/2026"})
    with pytest.raises(ValidationError):
        registry.validate_intent("finance.supplier_payment.from_invoice", {"paid_amount": -1})
    with pytest.raises(ValidationError):
        registry.validate_intent("project.task.create", {"priority": "马上"})


def test_capability_discovery_is_permission_filtered_and_limited() -> None:
    registry = CapabilityRegistry()
    policy = make_tool_access_policy("project")

    cards = registry.discover("查询项目成本和异常", policy=policy, modules=["projects"], limit=99)

    assert 1 <= len(cards) <= 5
    assert all(card["module"] == "projects" for card in cards)
    assert all(card["match_score"] > 0 for card in cards)
    assert all(policy.decide(registry.get(card["capability_id"]).tool, origin="agent").allowed for card in cards)


def test_capability_discovery_does_not_pad_with_zero_score_results() -> None:
    registry = CapabilityRegistry()
    policy = make_tool_access_policy("project")

    assert registry.discover("完全无关的火星业务", policy=policy, modules=["stock"], limit=5) == []


def test_unique_capability_discovery_auto_loads_guide(tmp_path: Path) -> None:
    planner = PlannerSequence([
        {
            "action": "discover_capabilities",
            "summary": "查找材料申请能力",
            "arguments": {"query": "创建采购类型材料申请草稿", "modules": ["buying"]},
        },
        {"action": "ask_user", "summary": "询问物料", "arguments": {"questions": ["需要什么物料？"]}},
    ])
    runtime = DeepSeekAgentRuntime(planner=planner, session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once("帮我创建材料申请", user="mao.xiaoquan@stec-up.local")

    assert result.status == "needs_clarification"
    discovery = next(step["result"] for step in result.steps if step["label"] == "发现业务能力")
    assert discovery["auto_loaded_guide"]["capability_id"] == "material_request.create"
    assert "material_request.create" in planner.messages[1][1]["content"]
    assert not any(step["action"] == "get_capability_guide" for step in result.steps)


def test_runtime_initial_prompt_uses_progressive_capability_disclosure(tmp_path: Path) -> None:
    planner = PlannerSequence([
        {"action": "discover_capabilities", "summary": "查找能力", "arguments": {"query": "项目任务", "modules": ["projects"]}},
        {"action": "get_capability_guide", "summary": "读取说明", "arguments": {"capability_ids": ["project.task.create"]}},
        {"action": "ask_user", "summary": "询问名称", "arguments": {"questions": ["任务名称是什么？"]}},
    ])
    runtime = DeepSeekAgentRuntime(planner=planner, session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once("帮我建一个项目任务", user="hu.yinhu@stec-up.local")

    initial_protocol = planner.messages[0][1]["content"]
    loaded_protocol = planner.messages[2][1]["content"]
    assert result.status == "needs_clarification"
    assert "create_material_request" not in initial_protocol
    assert "erpnext.projects.create_task" not in initial_protocol
    assert "project.task.create" in loaded_protocol
    assert "intent_schema" in loaded_protocol


def test_business_action_requires_loaded_guide(tmp_path: Path) -> None:
    planner = PlannerSequence([
        {
            "action": "propose_business_action",
            "summary": "直接创建任务",
            "arguments": {
                "capability_id": "project.task.create",
                "business_intent": {"goal": "create_project_task", "subject": "测试任务"},
            },
        },
        {"action": "ask_user", "summary": "说明缺少步骤", "arguments": {"questions": ["需要先加载业务能力说明。"]}},
    ])
    runtime = DeepSeekAgentRuntime(planner=planner, session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once("建任务", user="hu.yinhu@stec-up.local")

    assert result.status == "needs_clarification"
    assert any(step["result"].get("type") == "business_action_error" for step in result.steps if isinstance(step.get("result"), dict))


def test_protected_write_tool_cannot_use_generic_execute_tool(tmp_path: Path) -> None:
    planner = PlannerSequence([
        {
            "action": "execute_tool",
            "summary": "绕过能力直接写入",
            "arguments": {"tool_call": {
                "tool": "erpnext.buying.create_material_request_draft",
                "arguments": {"schedule_date": "2026-07-21", "items": []},
            }},
        },
        {"action": "finish", "summary": "停止", "arguments": {"message": "需要通过材料申请业务能力准备。"}},
    ])
    runtime = DeepSeekAgentRuntime(planner=planner, session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once("创建材料申请", user="mao.xiaoquan@stec-up.local")

    assert result.status == "completed"
    assert result.pending_tool_call is None
    assert any(step["action"] == "capability_required" for step in result.steps)


def test_capability_read_tool_cannot_bypass_registry(tmp_path: Path) -> None:
    planner = PlannerSequence([
        {
            "action": "execute_tool",
            "summary": "绕过库存能力直接查询",
            "arguments": {"tool_call": {
                "tool": "erpnext.stock.get_item_locations",
                "arguments": {"item_code": "MAT-CEM-000008"},
            }},
        },
        {"action": "finish", "summary": "停止", "arguments": {"message": "需要通过库存查询能力执行。"}},
    ])
    runtime = DeepSeekAgentRuntime(planner=planner, session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once("查库存", user="mao.xiaoquan@stec-up.local")

    assert result.status == "completed"
    assert result.tool_results == ()
    assert any(step["action"] == "capability_required" for step in result.steps)


def test_repeated_meta_action_stops_for_no_progress(tmp_path: Path) -> None:
    action = {"action": "discover_capabilities", "summary": "重复发现", "arguments": {"query": "库存"}}
    planner = PlannerSequence([action.copy(), action.copy(), action.copy()])
    runtime = DeepSeekAgentRuntime(planner=planner, session_store=RuntimeSessionStore(tmp_path), max_steps=5)

    result = runtime.run_once("查库存", user="mao.xiaoquan@stec-up.local")

    assert result.status == "failed"
    assert "没有取得新进展" in result.message
    assert any(step["action"] == "no_progress" for step in result.steps)


def test_capability_draft_merges_partial_item_fields() -> None:
    previous = {
        "goal": "create_material_request",
        "schedule_date": "2026-07-25",
        "items": [{"item_code": "MAT-CEM-000008", "uom": "包"}],
    }

    merged = _merge_capability_intent(previous, {"items": [{"qty": 20}]})

    assert merged["schedule_date"] == "2026-07-25"
    assert merged["items"] == [{"item_code": "MAT-CEM-000008", "uom": "包", "qty": 20}]


def test_capability_draft_survives_clarification_and_compiles_next_turn(tmp_path: Path) -> None:
    context = {
        "project_code": "PRJ-HL-13",
        "erpnext_project": "PROJ-0010",
        "warehouse": "合流1.3标仓库 - SD",
    }
    store = RuntimeSessionStore(tmp_path)
    first_planner = PlannerSequence([
        {
            "action": "discover_capabilities",
            "summary": "发现项目任务能力",
            "arguments": {"query": "创建项目任务", "modules": ["projects"]},
        },
        {
            "action": "get_capability_guide",
            "summary": "读取项目任务说明",
            "arguments": {"capability_ids": ["project.task.create"]},
        },
        {
            "action": "propose_business_action",
            "summary": "准备项目任务",
            "arguments": {
                "capability_id": "project.task.create",
                "business_intent": {
                    "goal": "create_project_task",
                    "description": "检查开工材料和人员准备",
                    "priority": "High",
                },
            },
        },
        {"action": "ask_user", "summary": "询问任务名", "arguments": {"questions": ["任务叫什么？"]}},
    ])
    first_runtime = DeepSeekAgentRuntime(
        planner=first_planner,
        session_store=store,
        client_factory=lambda _user: ProjectDocumentClient(),
    )

    first = first_runtime.run_once("帮我建立开工检查任务", user="hu.yinhu@stec-up.local", context=context)

    assert first.status == "needs_clarification"
    saved = store.load("hu.yinhu@stec-up.local", profile="project")
    assert _capability_draft(saved, "project.task.create")["description"] == "检查开工材料和人员准备"

    second_planner = PlannerSequence([
        {
            "action": "propose_business_action",
            "summary": "补充任务名",
            "arguments": {
                "capability_id": "project.task.create",
                "business_intent": {"goal": "create_project_task", "subject": "开工准备检查"},
            },
        },
    ])
    second_runtime = DeepSeekAgentRuntime(
        planner=second_planner,
        session_store=store,
        client_factory=lambda _user: ProjectDocumentClient(),
    )

    second = second_runtime.run_once("任务叫开工准备检查", user="hu.yinhu@stec-up.local", context=context)

    assert second.status == "needs_confirmation"
    assert second.pending_tool_call["arguments"]["subject"] == "开工准备检查"
    assert second.pending_tool_call["arguments"]["description"] == "检查开工材料和人员准备"
    assert second.pending_tool_call["arguments"]["priority"] == "High"


def test_clear_capability_draft_respects_capability_identity() -> None:
    session = RuntimeSessionState(user="user@example.com", profile="project")
    session.business_state = {
        "active_capability_id": "project.task.create",
        "capability_draft": {"capability_id": "project.task.create", "intent": {"subject": "测试"}},
    }

    _clear_capability_draft(session, "material_request.create")
    assert session.business_state["active_capability_id"] == "project.task.create"

    _clear_capability_draft(session, "project.task.create")
    assert "active_capability_id" not in session.business_state
    assert "capability_draft" not in session.business_state
