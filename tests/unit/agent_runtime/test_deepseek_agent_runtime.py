from __future__ import annotations

from pathlib import Path

import pytest

from nexterp_agent.agent_runtime.deepseek_agent_runtime import (
    AGENT_ACTIONS,
    DeepSeekAgentRuntime,
    ToolDiscoveryIndex,
    validate_agent_action,
)
from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime, LegacyCivilAgentRuntime
from nexterp_agent.agent_runtime.session import RuntimeSessionStore
from nexterp_agent.agent_runtime.tool_access import make_tool_access_policy
from nexterp_agent.master_data import MasterDataRelease
from nexterp_agent.erpnext.schemas import ToolResult


class PlannerSequence:
    def __init__(self, actions: list[dict]) -> None:
        self.actions = list(actions)
        self.messages = []

    def __call__(self, messages):
        self.messages.append(messages)
        if not self.actions:
            raise AssertionError("Planner sequence exhausted")
        return self.actions.pop(0)


class FakeERPNextClient:
    def __init__(self) -> None:
        self.created = []

    def get_logged_user(self):
        return ToolResult(ok=True, data="mao.xiaoquan@stec-up.local")

    def create_document(self, doctype, data):
        self.created.append((doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": "MAT-MR-TEST-0001", "docstatus": 0})

    def search_documents(self, doctype, **_kwargs):
        assert doctype == "Project"
        return ToolResult(ok=True, data=[{"name": "PROJ-0010", "project_name": "合流1.3标"}])

    def get_document(self, doctype, name):
        assert doctype == "Item"
        return ToolResult(ok=True, data={"name": name, "stock_uom": "个", "item_name": "测试物料", "description": "测试物料"})


class RepeatingPlanner:
    def __call__(self, _messages):
        return {"action": "discover_tools", "summary": "继续查找", "arguments": {"query": "库存", "modules": ["stock"]}}


def test_public_civil_runtime_defaults_to_deepseek_runtime() -> None:
    assert isinstance(CivilAgentRuntime(planner=PlannerSequence([])), DeepSeekAgentRuntime)


def test_explicit_legacy_extractor_only_constructs_regression_runtime() -> None:
    runtime = CivilAgentRuntime(intent_extractor=lambda *_args, **_kwargs: {"intent": "unknown"})
    assert isinstance(runtime, LegacyCivilAgentRuntime)


@pytest.mark.parametrize("action,arguments", [
    ("discover_tools", {"query": "库存"}),
    ("get_tool_contracts", {"tool_names": ["erpnext.stock.get_balance"]}),
    ("resolve_entities", {"entities": [{"id": "1", "kind": "item", "query": "手套"}]}),
    ("execute_tool", {"tool_call": {}}),
    ("ask_user", {"questions": ["请选择。"]}),
    ("finish", {"message": "完成"}),
])
def test_agent_action_protocol_accepts_all_actions(action: str, arguments: dict) -> None:
    payload = {"action": action, "summary": "test", "arguments": arguments}
    assert validate_agent_action(payload) is payload


def test_agent_action_protocol_retries_invalid_shape() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        validate_agent_action({"action": "invent_sql", "summary": "bad", "arguments": {}})


def test_runtime_stops_after_configured_deepseek_decision_count(tmp_path: Path) -> None:
    runtime = DeepSeekAgentRuntime(planner=RepeatingPlanner(), session_store=RuntimeSessionStore(tmp_path), max_steps=2)
    result = runtime.run_once("查库存", user="mao.xiaoquan@stec-up.local")

    assert result.status == "failed"
    assert "2步" in result.message
    assert sum(step["label"] == "DeepSeek规划" for step in result.steps) == 2


def test_tool_discovery_only_returns_agent_visible_profile_tools() -> None:
    policy = make_tool_access_policy("project")
    cards = ToolDiscoveryIndex().discover("材料申请", policy=policy, modules=["buying"], limit=8)

    assert cards
    assert all(card["module"] == "buying" for card in cards)
    assert all(policy.decide(card["name"], origin="agent").allowed for card in cards)


def test_write_tool_is_paused_with_resolved_entities(tmp_path: Path) -> None:
    release = MasterDataRelease()
    material = release.materials[0]
    project = release.projects["PRJ-HL-13"]
    warehouse = release.warehouses[project["default_warehouse_code"]]
    tool = "erpnext.buying.create_material_request_draft"
    tool_call = {
        "tool": tool,
        "arguments": {
            "material_request_type": "Purchase",
            "schedule_date": "2026-07-14",
            "items": [{
                "item_code": material["item_code"],
                "qty": 20,
                "uom": material["stock_uom"],
                "warehouse": warehouse["erpnext_warehouse_name"],
                "schedule_date": "2026-07-14",
            }],
        },
    }
    planner = PlannerSequence([
        {"action": "get_tool_contracts", "summary": "读取材料申请契约", "arguments": {"tool_names": [tool]}},
        {"action": "resolve_entities", "summary": "核对主数据", "arguments": {"entities": [
            {"id": "company", "kind": "company", "query": "盛拓工程"},
            {"id": "project", "kind": "project", "query": "PRJ-HL-13"},
            {"id": "warehouse", "kind": "warehouse", "query": project["default_warehouse_code"]},
            {"id": "item", "kind": "item", "query": material["item_code"]},
            {"id": "date", "kind": "date", "query": "明天"},
        ]}},
        {"action": "execute_tool", "summary": "创建材料申请草稿", "arguments": {"tool_call": tool_call}},
    ])
    store = RuntimeSessionStore(tmp_path)
    runtime = DeepSeekAgentRuntime(release=release, planner=planner, session_store=store)

    result = runtime.run_once("明天需要20个物料", user="mao.xiaoquan@stec-up.local", today=__import__("datetime").date(2026, 7, 13))

    assert result.status == "needs_confirmation"
    assert result.pending_tool_call["arguments"]["company"] == release.company_name("STEC")
    assert result.pending_tool_call["arguments"]["items"][0]["project"] == project["project_code"]
    assert store.load("mao.xiaoquan@stec-up.local", profile="project").pending_action["tool_call"] == result.pending_tool_call


def test_forged_entity_is_rejected_and_returned_to_model(tmp_path: Path) -> None:
    tool = "erpnext.stock.get_balance"
    planner = PlannerSequence([
        {"action": "get_tool_contracts", "summary": "读取库存契约", "arguments": {"tool_names": [tool]}},
        {"action": "execute_tool", "summary": "查询库存", "arguments": {"tool_call": {"tool": tool, "arguments": {"item_code": "MADE-UP", "warehouse": "FAKE"}}}},
        {"action": "ask_user", "summary": "需要确认真实物料", "arguments": {"questions": ["请选择真实物料。"]}},
    ])
    runtime = DeepSeekAgentRuntime(planner=planner, session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once("查一下库存", user="mao.xiaoquan@stec-up.local")

    assert result.status == "needs_clarification"
    assert result.questions == ("请选择真实物料。",)
    assert any("不是Resolver" in message[1]["content"] for message in planner.messages if len(message) > 1)


def test_confirmation_executes_pending_call_then_returns_model_finish(tmp_path: Path) -> None:
    release = MasterDataRelease()
    material = release.materials[0]
    project = release.projects["PRJ-HL-13"]
    warehouse = release.warehouses[project["default_warehouse_code"]]
    tool = "erpnext.buying.create_material_request_draft"
    planner = PlannerSequence([
        {"action": "get_tool_contracts", "summary": "读取契约", "arguments": {"tool_names": [tool]}},
        {"action": "resolve_entities", "summary": "核对主数据", "arguments": {"entities": [
            {"id": "project", "kind": "project", "query": project["project_code"]},
            {"id": "warehouse", "kind": "warehouse", "query": project["default_warehouse_code"]},
            {"id": "item", "kind": "item", "query": material["item_code"]},
        ]}},
        {"action": "execute_tool", "summary": "创建草稿", "arguments": {"tool_call": {"tool": tool, "arguments": {"schedule_date": "2026-07-14", "items": [{"item_code": material["item_code"], "qty": 1, "warehouse": warehouse["erpnext_warehouse_name"]}]}}}},
        {"action": "finish", "summary": "完成", "arguments": {"message": "已创建测试材料申请草稿。"}},
    ])
    client = FakeERPNextClient()
    runtime = DeepSeekAgentRuntime(release=release, planner=planner, client_factory=lambda _user: client, session_store=RuntimeSessionStore(tmp_path))
    preview = runtime.run_once("创建测试材料申请", user="mao.xiaoquan@stec-up.local")

    completed = runtime.run_once("创建测试材料申请", user="mao.xiaoquan@stec-up.local", execute=True, request_id="request-1")

    assert preview.status == "needs_confirmation"
    assert completed.status == "completed"
    assert completed.message == "已创建测试材料申请草稿。"
    assert client.created[0][0] == "Material Request"
    assert runtime.session_store.load("mao.xiaoquan@stec-up.local", profile="project").documents["Material Request"] == ["MAT-MR-TEST-0001"]
