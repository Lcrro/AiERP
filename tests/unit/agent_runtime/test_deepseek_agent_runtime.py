from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nexterp_agent.agent_runtime.deepseek_agent_runtime import (
    AGENT_ACTIONS,
    DeepSeekAgentRuntime,
    ToolDiscoveryIndex,
    _attach_runtime_confirmation,
    _allowed_entity_values,
    _compact_document_snapshot,
    _document_next_action_tools,
    _same_business_call,
    _inject_material_request_reference_prices,
    _inject_source_document_references,
    _resolved_entity_values,
    _successful_execution_message,
    validate_agent_action,
)
from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime, LegacyCivilAgentRuntime
from nexterp_agent.agent_runtime.session import RuntimeSessionState, RuntimeSessionStore
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
        self.searches = []

    def get_logged_user(self):
        return ToolResult(ok=True, data="mao.xiaoquan@stec-up.local")

    def create_document(self, doctype, data):
        self.created.append((doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": "MAT-MR-TEST-0001", "docstatus": 0})

    def search_documents(self, doctype, **kwargs):
        self.searches.append((doctype, kwargs))
        if doctype == "Project":
            return ToolResult(ok=True, data=[{"name": "PROJ-0010", "project_name": "合流1.3标"}])
        if doctype == "Bin":
            item_codes = kwargs["filters"][0][2]
            return ToolResult(ok=True, data=[
                {
                    "name": f"BIN-{item_code}",
                    "item_code": item_code,
                    "warehouse": "蕰川路基地仓库 - SD",
                    "actual_qty": 5,
                    "reserved_qty": 1,
                    "projected_qty": 7,
                }
                for item_code in item_codes
            ])
        raise AssertionError(f"Unexpected doctype: {doctype}")

    def get_document(self, doctype, name):
        assert doctype == "Item"
        return ToolResult(ok=True, data={"name": name, "stock_uom": "个", "item_name": "测试物料", "description": "测试物料"})


class RepeatingPlanner:
    def __call__(self, _messages):
        return {"action": "discover_tools", "summary": "继续查找", "arguments": {"query": "库存", "modules": ["stock"]}}


def test_material_request_rate_comes_from_governed_master_data() -> None:
    call = {
        "tool": "erpnext.buying.create_material_request_draft",
        "arguments": {"items": [{"item_code": "MAT-CEM-000008", "qty": 20, "rate": 9999}]},
    }

    corrections = _inject_material_request_reference_prices(
        call,
        {"MAT-CEM-000008": {"estimated_rate": "28.00", "price_basis": "测试参考价"}},
    )

    assert call["arguments"]["items"][0]["rate"] == 28.0
    assert corrections == [{
        "field": "items[0].rate",
        "value": 28.0,
        "source": "material_master.estimated_rate",
        "price_basis": "测试参考价",
    }]


def test_unverified_model_rate_is_removed_when_material_has_no_reference_price() -> None:
    call = {
        "tool": "erpnext.buying.create_material_request_draft",
        "arguments": {"items": [{"item_code": "ITEM-NO-PRICE", "qty": 1, "rate": 88}]},
    }

    _inject_material_request_reference_prices(call, {})

    assert "rate" not in call["arguments"]["items"][0]


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


def test_project_profile_can_discover_material_request_submit_tool() -> None:
    policy = make_tool_access_policy("project")
    cards = ToolDiscoveryIndex().discover("提交材料申请单据", policy=policy, modules=["buying"], limit=8)

    assert "erpnext.buying.submit_document" in {card["name"] for card in cards}


def test_workflow_document_direct_submit_is_rejected_before_confirmation() -> None:
    class WorkflowClient:
        def get_document(self, doctype, name):
            return ToolResult(ok=True, data={"doctype": doctype, "name": name, "workflow_state": "草稿"})

    runtime = DeepSeekAgentRuntime(client_factory=lambda _user: WorkflowClient())
    call = {
        "tool": "erpnext.buying.submit_document",
        "arguments": {
            "doctype": "Material Request",
            "name": "MAT-MR-TEST-0001",
            "confirmation": {
                "confirmed": True,
                "confirmed_by": "EMP-MAOXIAOQUAN",
                "confirmed_at": "2026-07-15T10:00:00",
                "confirmation_text": "提交申请",
                "reason": "测试工作流保护",
            },
        },
    }
    session = RuntimeSessionState(
        user="mao.xiaoquan@stec-up.local",
        profile="project",
        documents={"Material Request": ["MAT-MR-TEST-0001"]},
    )
    observations = [{
        "type": "get_tool_contracts",
        "contracts": [{"name": "erpnext.buying.submit_document"}],
    }]

    error = runtime._validate_proposed_call(
        call,
        user=session.user,
        policy=make_tool_access_policy("project"),
        session=session,
        observations=observations,
    )

    assert "已启用ERPNext工作流" in str(error)
    assert "erpnext.get_workflow_actions" in str(error)


def test_success_message_prefers_workflow_state_over_generic_document_status() -> None:
    message = _successful_execution_message({
        "data": {
            "doctype": "Material Request",
            "name": "MAT-MR-0001",
            "status": "Draft",
            "workflow_state": "待材料设备主管审批",
        }
    })

    assert message == "Material Request MAT-MR-0001 已执行成功，当前状态：待材料设备主管审批。"


def test_document_resolution_returns_live_compact_snapshot() -> None:
    class DocumentClient:
        def get_document(self, doctype, name):
            return ToolResult(ok=True, data={
                "doctype": doctype,
                "name": name,
                "status": "Pending",
                "workflow_state": "已批准",
                "docstatus": 1,
                "items": [{
                    "name": "MRI-1",
                    "item_code": "MAT-CEM-000008",
                    "qty": 1,
                    "uom": "包",
                    "project": "PROJ-0010",
                    "private_field": "discard",
                }],
                "private_field": "discard",
            })

    runtime = DeepSeekAgentRuntime(client_factory=lambda _user: DocumentClient())
    session = RuntimeSessionState(user="pan.feng@stec-up.local", profile="procurement")

    result = runtime._resolve_entities(
        {"entities": [{"id": "request", "kind": "document", "doctype": "Material Request", "query": "MAT-MR-0001"}]},
        user=session.user,
        today=date(2026, 7, 15),
        session=session,
    )

    snapshot = result["entities"][0]["resolution"]["row"]
    assert snapshot["workflow_state"] == "已批准"
    assert snapshot["items"] == [{
        "name": "MRI-1",
        "item_code": "MAT-CEM-000008",
        "qty": 1,
        "uom": "包",
        "project": "PROJ-0010",
    }]
    assert "private_field" not in snapshot

    session.selected_entities.update(_resolved_entity_values(result))
    allowed = _allowed_entity_values(session, [])
    assert "MAT-CEM-000008" in allowed["item"]
    assert "PROJ-0010" in allowed["project"]


def test_execute_tool_progressively_discloses_missing_contract(tmp_path: Path) -> None:
    tool = "erpnext.stock.get_balance"
    planner = PlannerSequence([
        {
            "action": "execute_tool",
            "summary": "尝试查询库存",
            "arguments": {"tool_call": {"tool": tool, "arguments": {"item_code": "ITEM-1", "warehouse": "WH-1"}}},
        },
        {
            "action": "ask_user",
            "summary": "等待真实实体",
            "arguments": {"questions": ["请选择真实物料和仓库。"]},
        },
    ])
    runtime = DeepSeekAgentRuntime(planner=planner, session_store=RuntimeSessionStore(tmp_path))

    result = runtime.run_once("查询库存", user="mao.xiaoquan@stec-up.local")

    assert result.status == "needs_clarification"
    disclosure = next(step for step in result.steps if step["label"] == "自动读取契约")
    assert disclosure["payload"]["tool_names"] == [tool]
    assert tool in planner.messages[1][1]["content"]


def test_rfq_arguments_inherit_material_request_source_rows() -> None:
    session = RuntimeSessionState(
        user="pan.feng@stec-up.local",
        profile="procurement",
        selected_entities={
            "request": {
                "kind": "document",
                "value": "MAT-MR-0001",
                "row": {
                    "doctype": "Material Request",
                    "name": "MAT-MR-0001",
                    "items": [{
                        "name": "MRI-1",
                        "item_code": "MAT-CEM-000008",
                        "qty": 1,
                        "project": "PROJ-0010",
                        "warehouse": "合流1.3标仓库 - SD",
                    }],
                },
            }
        },
    )
    call = {
        "tool": "erpnext.buying.create_request_for_quotation_draft",
        "arguments": {"items": [{"item_code": "MAT-CEM-000008", "qty": 1}]},
    }

    corrections = _inject_source_document_references(call, session, [])

    assert call["arguments"]["items"][0] == {
        "item_code": "MAT-CEM-000008",
        "qty": 1,
        "material_request": "MAT-MR-0001",
        "material_request_item": "MRI-1",
        "project": "PROJ-0010",
        "warehouse": "合流1.3标仓库 - SD",
    }
    assert {row["field"] for row in corrections} == {
        "items[0].material_request",
        "items[0].material_request_item",
        "items[0].project",
        "items[0].warehouse",
    }


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
    assert "尚未写入 ERPNext" in result.message
    assert "确认" in result.message
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
    assert result.message == "请选择真实物料。"
    assert any("不是Resolver" in message[1]["content"] for message in planner.messages if len(message) > 1)


def test_item_resolution_batches_candidate_inventory_once(tmp_path: Path) -> None:
    release = MasterDataRelease()
    materials = release.materials[:2]
    project = release.projects["PRJ-HL-13"]
    planner = PlannerSequence([
        {"action": "resolve_entities", "summary": "解析候选并查询库存", "arguments": {"entities": [
            {
                "id": str(index),
                "kind": "item",
                "query": material["item_code"],
                "qty": 10,
                "uom": material["stock_uom"],
            }
            for index, material in enumerate(materials, start=1)
        ]}},
        {"action": "ask_user", "summary": "请确认候选", "arguments": {"questions": ["请选择物料。"]}},
    ])
    client = FakeERPNextClient()
    runtime = DeepSeekAgentRuntime(
        release=release,
        planner=planner,
        client_factory=lambda _user: client,
        session_store=RuntimeSessionStore(tmp_path),
    )

    result = runtime.run_once(
        "查两个候选物料库存",
        user="mao.xiaoquan@stec-up.local",
        context={"project_code": project["project_code"], "warehouse": project["default_warehouse_code"]},
    )

    bin_searches = [search for search in client.searches if search[0] == "Bin"]
    assert len(bin_searches) == 1
    assert bin_searches[0][1]["filters"] == [
        ["item_code", "in", [material["item_code"] for material in materials]],
        ["warehouse", "in", ["合流1.3标仓库 - SD", "蕰川路基地仓库 - SD"]],
    ]
    observation = next(step["result"] for step in result.steps if step["label"] == "解析实体")
    assert observation["inventory_query"]["status"] == "completed"
    for entity in observation["entities"]:
        candidate = entity["resolution"]["candidates"][0]
        assert candidate["inventory"]
        assert candidate["inventory_summary"]["total_available_qty"] == 4
        assert candidate["inventory_summary"]["shortage_qty"] == 6


def test_shared_item_name_requires_user_selection_and_excludes_partial_name_matches(tmp_path: Path) -> None:
    planner = PlannerSequence([
        {"action": "resolve_entities", "summary": "解析水泥", "arguments": {"entities": [
            {"id": "cement", "kind": "item", "query": "水泥"},
        ]}},
        {
            "action": "ask_user",
            "summary": "询问水泥需求",
            "arguments": {
                "questions": ["请选择具体水泥，并告诉我需要多少。"],
                "candidates": [{"item_code": "MAT-CEM-000011", "sku_name": "水泥 PC425 袋装 50kg"}],
            },
        },
    ])
    store = RuntimeSessionStore(tmp_path)
    session = store.load("mao.xiaoquan@stec-up.local", profile="project")
    session.selected_entities["old_item"] = {"kind": "item", "value": "STALE-CEMENT"}
    store.save(session)
    runtime = DeepSeekAgentRuntime(
        planner=planner,
        client_factory=lambda _user: FakeERPNextClient(),
        session_store=store,
    )

    result = runtime.run_once("帮我采购点水泥，后天要用", user="mao.xiaoquan@stec-up.local")

    assert result.status == "needs_clarification"
    assert result.message == "请选择具体水泥，并告诉我需要多少。"
    candidates = result.candidates[0]["candidates"]
    assert len(candidates) == 1
    assert {candidate["item_name"] for candidate in candidates} == {"水泥"}
    assert all("水泥砖" not in candidate["sku_name"] for candidate in candidates)
    assert candidates[0]["inventory"]
    resolve_step = next(step for step in result.steps if step["label"] == "解析实体")
    assert resolve_step["result"]["entities"][0]["resolution"]["selection_required"] is True
    selected = store.load("mao.xiaoquan@stec-up.local", profile="project").selected_entities
    assert not any(entity.get("kind") == "item" for entity in selected.values())


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


def test_successful_write_is_not_reported_failed_when_finish_json_is_invalid(tmp_path: Path) -> None:
    release = MasterDataRelease()
    material = release.materials[0]
    tool = "erpnext.buying.create_material_request_draft"
    call = {
        "tool": tool,
        "arguments": {
            "schedule_date": "2026-07-14",
            "items": [{"item_code": material["item_code"], "qty": 1}],
        },
    }
    planner = PlannerSequence([
        {"action": "get_tool_contracts", "summary": "读取契约", "arguments": {"tool_names": [tool]}},
        {"action": "resolve_entities", "summary": "解析物料", "arguments": {"entities": [
            {"id": "item", "kind": "item", "query": material["item_code"]},
        ]}},
        {"action": "execute_tool", "summary": "创建草稿", "arguments": {"tool_call": call}},
        {"action": "finish", "summary": "完成", "arguments": {}},
        {"action": "finish", "summary": "完成", "arguments": {}},
    ])
    client = FakeERPNextClient()
    runtime = DeepSeekAgentRuntime(
        release=release,
        planner=planner,
        client_factory=lambda _user: client,
        session_store=RuntimeSessionStore(tmp_path),
    )

    preview = runtime.run_once("创建草稿", user="mao.xiaoquan@stec-up.local")
    completed = runtime.run_once("确认创建", user="mao.xiaoquan@stec-up.local", execute=True)

    assert preview.status == "needs_confirmation"
    assert completed.status == "completed"
    assert "MAT-MR-TEST-0001" in completed.message
    assert len(client.created) == 1
    assert any(step["label"] == "生成回复降级" for step in completed.steps)


def test_successful_write_falls_back_to_tool_result_at_planner_step_limit(tmp_path: Path) -> None:
    release = MasterDataRelease()
    material = release.materials[0]
    tool = "erpnext.buying.create_material_request_draft"
    call = {
        "tool": tool,
        "arguments": {"schedule_date": "2026-07-14", "items": [{"item_code": material["item_code"], "qty": 1}]},
    }
    planner = PlannerSequence([
        {"action": "get_tool_contracts", "summary": "读取契约", "arguments": {"tool_names": [tool]}},
        {"action": "resolve_entities", "summary": "解析物料", "arguments": {"entities": [
            {"id": "item", "kind": "item", "query": material["item_code"]},
        ]}},
        {"action": "execute_tool", "summary": "创建草稿", "arguments": {"tool_call": call}},
        {"action": "discover_tools", "summary": "继续规划", "arguments": {"query": "后续操作", "modules": ["buying"]}},
    ])
    runtime = DeepSeekAgentRuntime(
        release=release,
        planner=planner,
        client_factory=lambda _user: FakeERPNextClient(),
        session_store=RuntimeSessionStore(tmp_path),
        max_steps=4,
    )

    preview = runtime.run_once("创建草稿", user="mao.xiaoquan@stec-up.local")
    completed = runtime.run_once("确认创建", user="mao.xiaoquan@stec-up.local", execute=True)

    assert preview.status == "needs_confirmation"
    assert completed.status == "completed"
    assert "MAT-MR-TEST-0001" in completed.message
    assert any(step["result"].get("source") == "successful_tool_result" for step in completed.steps if step["label"] == "生成回复降级")


def test_confirmation_does_not_reconfirm_identical_successful_tool_call(tmp_path: Path) -> None:
    release = MasterDataRelease()
    material = release.materials[0]
    tool = "erpnext.buying.create_material_request_draft"
    call = {
        "tool": tool,
        "arguments": {
            "schedule_date": "2026-07-14",
            "items": [{"item_code": material["item_code"], "qty": 1}],
        },
    }
    planner = PlannerSequence([
        {"action": "get_tool_contracts", "summary": "读取契约", "arguments": {"tool_names": [tool]}},
        {"action": "resolve_entities", "summary": "解析物料", "arguments": {"entities": [
            {"id": "item", "kind": "item", "query": material["item_code"]},
        ]}},
        {"action": "execute_tool", "summary": "创建草稿", "arguments": {"tool_call": call}},
        {"action": "execute_tool", "summary": "重复创建草稿", "arguments": {"tool_call": call}},
    ])
    runtime = DeepSeekAgentRuntime(
        release=release,
        planner=planner,
        client_factory=lambda _user: FakeERPNextClient(),
        session_store=RuntimeSessionStore(tmp_path),
    )

    preview = runtime.run_once("创建草稿", user="mao.xiaoquan@stec-up.local")
    completed = runtime.run_once("确认创建", user="mao.xiaoquan@stec-up.local", execute=True)

    assert preview.status == "needs_confirmation"
    assert completed.status == "completed"
    assert completed.tool_result["ok"] is True
    assert any(step["label"] == "跳过重复动作" for step in completed.steps)


def test_system_prompt_distinguishes_workflow_from_plain_submit(tmp_path):
    runtime = DeepSeekAgentRuntime(planner=lambda _messages: {}, session_store=RuntimeSessionStore(tmp_path))
    session = RuntimeSessionState(user="pan.feng@stec-up.local", profile="procurement")

    messages = runtime._messages(
        "提交询价单",
        {"user_email": session.user, "position": "材料设备主管"},
        session,
        date(2026, 7, 16),
        [],
        [],
    )

    assert "没有workflow_state且docstatus=0" in messages[0]["content"]
    assert "禁止调用get_workflow_actions或apply_workflow" in messages[0]["content"]
    assert "submit_document工具" in messages[0]["content"]


def test_confirmation_gated_call_is_validated_before_runtime_adds_audit_metadata(tmp_path):
    runtime = DeepSeekAgentRuntime(planner=lambda _messages: {}, session_store=RuntimeSessionStore(tmp_path))
    session = RuntimeSessionState(user="pan.feng@stec-up.local", profile="procurement")
    session.documents["Request for Quotation"] = ["PUR-RFQ-2026-00003"]
    call = {
        "tool": "erpnext.buying.submit_document",
        "arguments": {"doctype": "Request for Quotation", "name": "PUR-RFQ-2026-00003"},
    }
    observations = [{
        "type": "get_tool_contracts",
        "contracts": [{"name": "erpnext.buying.submit_document"}],
    }]

    error = runtime._validate_proposed_call(
        call,
        user=session.user,
        policy=make_tool_access_policy("procurement"),
        session=session,
        observations=observations,
    )

    assert error is None
    assert "confirmation" not in call["arguments"]
    _attach_runtime_confirmation(call, user=session.user, reason="提交询价单")
    assert call["arguments"]["confirmation"]["confirmed"] is True
    assert call["arguments"]["confirmation"]["confirmed_by"] == session.user
    assert call["arguments"]["confirmation"]["reason"] == "提交询价单"


def test_missing_action_summary_is_repaired_for_audit() -> None:
    action = validate_agent_action({"action": "finish", "arguments": {"message": "完成"}})

    assert action["summary"] == "DeepSeek请求执行finish"


def test_business_call_comparison_ignores_runtime_confirmation_metadata() -> None:
    left = {"tool": "erpnext.buying.submit_document", "arguments": {
        "doctype": "Purchase Order", "name": "PUR-ORD-2026-00006",
        "confirmation": {"confirmed_at": "old"},
    }}
    right = {"tool": "erpnext.buying.submit_document", "arguments": {
        "doctype": "Purchase Order", "name": "PUR-ORD-2026-00006",
        "confirmation": {"confirmed_at": "new"},
    }}

    assert _same_business_call(left, right) is True


def test_document_snapshot_discloses_only_state_valid_submit_path() -> None:
    plain = _compact_document_snapshot({
        "doctype": "Purchase Order",
        "name": "PUR-ORD-2026-00006",
        "docstatus": 0,
        "status": "Draft",
    })
    workflow = _compact_document_snapshot({
        "doctype": "Material Request",
        "name": "MAT-MR-2026-00021",
        "docstatus": 0,
        "workflow_state": "待材料设备主管审批",
    })

    assert plain["allowed_next_actions"] == ["erpnext.buying.submit_document"]
    assert workflow["allowed_next_actions"] == ["erpnext.get_workflow_actions", "erpnext.apply_workflow"]

    observation = {"entities": [{
        "kind": "document",
        "resolution": {"status": "resolved", "row": plain},
    }]}
    assert _document_next_action_tools(observation) == ["erpnext.buying.submit_document"]
