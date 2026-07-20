from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nexterp_agent.agent_runtime.deepseek_agent_runtime import (
    AGENT_ACTIONS,
    DeepSeekAgentRuntime,
    ToolDiscoveryIndex,
    _attach_runtime_confirmation,
    _bind_pending_action,
    _allowed_entity_values,
    _compact_document_snapshot,
    _compact_agent_observation,
    _document_snapshots_from_observation,
    _document_next_action_tools,
    _same_business_call,
    _pending_binding_error,
    _inject_material_request_reference_prices,
    _inject_operational_dates,
    _inject_resolved_arguments,
    _inject_source_document_references,
    _resolved_entity_values,
    _successful_execution_message,
    _source_document_tool_error,
    validate_agent_action,
)
from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime, LegacyCivilAgentRuntime
from nexterp_agent.agent_runtime.capability_registry import CapabilityRegistry
from nexterp_agent.agent_runtime.session import RuntimeSessionState, RuntimeSessionStore
from nexterp_agent.agent_runtime.tool_access import make_tool_access_policy
from nexterp_agent.master_data import MasterDataRelease
from nexterp_agent.erpnext.schemas import ToolResult


class PlannerSequence:
    def __init__(self, actions: list[dict]) -> None:
        registry = CapabilityRegistry()
        expanded = []
        loaded = set()
        for original in actions:
            action = original
            if (
                action.get("action") == "execute_tool"
                and (action.get("arguments") or {}).get("tool_call", {}).get("tool")
                == "erpnext.buying.create_material_request_draft"
            ):
                tool_arguments = action["arguments"]["tool_call"].get("arguments") or {}
                action = {
                    "action": "propose_business_action",
                    "summary": action.get("summary") or "准备材料申请",
                    "arguments": {"business_intent": {
                        "goal": "create_material_request",
                        "schedule_date": tool_arguments.get("schedule_date"),
                        "company": tool_arguments.get("company"),
                        "items": tool_arguments.get("items") or [],
                    }},
                }
            if action.get("action") == "propose_business_action":
                arguments = action.setdefault("arguments", {})
                goal = str((arguments.get("business_intent") or {}).get("goal") or "")
                capability_id = registry.for_goal(goal).capability_id
                arguments["capability_id"] = capability_id
                if capability_id not in loaded:
                    expanded.extend([
                        {"action": "discover_capabilities", "summary": "发现业务能力", "arguments": {"query": goal, "limit": 5}},
                        {"action": "get_capability_guide", "summary": "读取业务能力说明", "arguments": {"capability_ids": [capability_id]}},
                    ])
                    loaded.add(capability_id)
            expanded.append(action)
        self.actions = expanded
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
        if doctype == "Item":
            return ToolResult(ok=True, data={"name": name, "stock_uom": "个", "item_name": "测试物料", "description": "测试物料"})
        if doctype == "Material Request":
            created = self.created[-1][1] if self.created else {}
            return ToolResult(ok=True, data={
                "doctype": doctype,
                "name": name,
                "docstatus": 0,
                "items": created.get("items") or [],
            })
        raise AssertionError((doctype, name))


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
    ("discover_capabilities", {"query": "库存"}),
    ("get_tool_contracts", {"tool_names": ["erpnext.stock.get_balance"]}),
    ("get_capability_guide", {"capability_ids": ["stock.balance.query"]}),
    ("resolve_entities", {"entities": [{"id": "1", "kind": "item", "query": "手套"}]}),
    ("propose_business_action", {"capability_id": "material_request.create", "business_intent": {"goal": "create_material_request"}}),
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


def test_procurement_write_is_compiled_and_confirmation_is_hash_bound(tmp_path: Path) -> None:
    planner = PlannerSequence([{
        "action": "propose_business_action",
        "summary": "准备材料申请",
        "arguments": {"business_intent": {
            "goal": "create_material_request",
            "schedule_date": "2026-07-23",
            "company": "STEC (Demo)",
            "items": [{"item_code": "SAFE-000001", "qty": 100, "uom": "双"}],
            "provenance": {"schedule_date": "user", "items": "resolver"},
        }},
    }])
    store = RuntimeSessionStore(tmp_path)
    state = RuntimeSessionState(user="mao.xiaoquan@stec-up.local", profile="project")
    state.selected_entities["gloves"] = {"kind": "item", "value": "SAFE-000001"}
    store.save(state)
    client = FakeERPNextClient()
    runtime = DeepSeekAgentRuntime(planner=planner, session_store=store, client_factory=lambda _user: client)

    result = runtime.run_once(
        "后天要100双帆布手套",
        user="mao.xiaoquan@stec-up.local",
        today=date(2026, 7, 20),
        context={
            "project_code": "PRJ-HL-13",
            "erpnext_project": "PROJ-0010",
            "warehouse": "合流1.3标仓库 - SD",
        },
    )

    assert result.status == "needs_confirmation"
    assert result.pending_tool_call["tool"] == "erpnext.buying.create_material_request_draft"
    assert result.pending_tool_call["arguments"]["items"][0]["project"] == "PROJ-0010"
    pending = store.load("mao.xiaoquan@stec-up.local", profile="project").pending_action
    assert pending["capability"] == "material_request.create"
    assert len(pending["confirmation_hash"]) == 64

    pending["tool_call"]["arguments"]["items"][0]["qty"] = 999
    state = store.load("mao.xiaoquan@stec-up.local", profile="project")
    state.pending_action = pending
    store.save(state)

    rejected = runtime.run_once(
        "确认",
        user="mao.xiaoquan@stec-up.local",
        execute=True,
        today=date(2026, 7, 20),
    )

    assert rejected.status == "failed"
    assert "发生变化" in rejected.message
    assert client.created == []


def test_stock_balance_business_action_executes_read_only_without_confirmation(tmp_path: Path) -> None:
    class StockReadClient:
        def get_logged_user(self):
            return ToolResult(ok=True, data="mao.xiaoquan@stec-up.local")

        def get_item_stock_locations(self, item_code, *, include_zero=False, limit=100):
            assert (item_code, include_zero, limit) == ("SAFE-000001", False, 200)
            return ToolResult(ok=True, data=[{
                "item_code": item_code,
                "warehouse": "合流1.3标仓库 - SD",
                "actual_qty": 12,
            }])

    planner = PlannerSequence([
        {
            "action": "propose_business_action",
            "summary": "查询手套库存",
            "arguments": {"business_intent": {
                "goal": "query_stock_balance",
                "items": [{"item_code": "SAFE-000001"}],
            }},
        },
        {"action": "finish", "summary": "回复库存", "arguments": {"message": "合流1.3标仓库现有12双。"}},
    ])
    store = RuntimeSessionStore(tmp_path)
    state = RuntimeSessionState(user="mao.xiaoquan@stec-up.local", profile="project")
    state.selected_entities["gloves"] = {"kind": "item", "value": "SAFE-000001"}
    store.save(state)
    runtime = DeepSeekAgentRuntime(
        planner=planner,
        client_factory=lambda _user: StockReadClient(),
        session_store=store,
    )

    result = runtime.run_once("查帆布手套库存", user=state.user, today=date(2026, 7, 20))

    assert result.status == "completed"
    assert result.message == "合流1.3标仓库现有12双。"
    assert result.tool_results[0]["data"][0]["actual_qty"] == 12
    assert store.load(state.user, profile="project").pending_action is None


def test_stock_transfer_business_action_confirms_executes_and_reads_back(tmp_path: Path) -> None:
    class StockWriteClient:
        def __init__(self):
            self.created = []

        def get_logged_user(self):
            return ToolResult(ok=True, data="pan.feng@stec-up.local")

        def get_stock_balance(self, item_code, *, warehouse=None, limit=100):
            qty = 200 if warehouse == "蕰川路基地仓库 - SD" else 0
            return ToolResult(ok=True, data=[{"item_code": item_code, "warehouse": warehouse, "actual_qty": qty}])

        def create_stock_entry_draft(self, data):
            self.created.append(data)
            return ToolResult(ok=True, data={"doctype": "Stock Entry", "name": "MAT-STE-TEST-0001", "docstatus": 0})

        def get_document(self, doctype, name):
            assert (doctype, name) == ("Stock Entry", "MAT-STE-TEST-0001")
            return ToolResult(ok=True, data={
                "doctype": doctype,
                "name": name,
                "docstatus": 0,
                "items": [{
                    "item_code": "SAFE-000001",
                    "qty": 100,
                    "s_warehouse": "蕰川路基地仓库 - SD",
                    "t_warehouse": "合流1.3标仓库 - SD",
                }],
            })

    planner = PlannerSequence([{
        "action": "propose_business_action",
        "summary": "准备库存调拨",
        "arguments": {"business_intent": {
            "goal": "create_stock_transfer",
            "company": "STEC (Demo)",
            "source_warehouse": "蕰川路基地仓库 - SD",
            "target_warehouse": "合流1.3标仓库 - SD",
            "items": [{"item_code": "SAFE-000001", "qty": 100, "uom": "双"}],
        }},
    }])
    store = RuntimeSessionStore(tmp_path)
    state = RuntimeSessionState(user="pan.feng@stec-up.local", profile="procurement")
    state.selected_entities.update({
        "item": {"kind": "item", "value": "SAFE-000001"},
        "source": {"kind": "warehouse", "value": "蕰川路基地仓库 - SD"},
        "target": {"kind": "warehouse", "value": "合流1.3标仓库 - SD"},
    })
    store.save(state)
    client = StockWriteClient()
    runtime = DeepSeekAgentRuntime(planner=planner, client_factory=lambda _user: client, session_store=store)

    preview = runtime.run_once("把100双手套从基地调到合流仓库", user=state.user, today=date(2026, 7, 20))
    assert preview.status == "needs_confirmation"
    assert preview.pending_tool_call["tool"] == "erpnext.stock.create_transfer_draft"
    assert client.created == []

    completed = runtime.run_once("确认", user=state.user, execute=True, today=date(2026, 7, 20))
    assert completed.status == "completed"
    assert len(client.created) == 1
    assert completed.tool_result["verification"]["ok"] is True
    assert "transfer_warehouses_match" in completed.tool_result["verification"]["checks"]


def test_stock_transfer_shortage_is_blocked_before_confirmation(tmp_path: Path) -> None:
    class EmptyStockClient:
        def get_logged_user(self):
            return ToolResult(ok=True, data="pan.feng@stec-up.local")

        def get_stock_balance(self, item_code, *, warehouse=None, limit=100):
            return ToolResult(ok=True, data=[{"item_code": item_code, "warehouse": warehouse, "actual_qty": 0}])

        def create_stock_entry_draft(self, _data):
            raise AssertionError("shortage must block draft creation")

    planner = PlannerSequence([
        {
            "action": "propose_business_action",
            "summary": "准备调拨",
            "arguments": {"business_intent": {
                "goal": "create_stock_transfer",
                "source_warehouse": "蕰川路基地仓库 - SD",
                "target_warehouse": "合流1.3标仓库 - SD",
                "items": [{"item_code": "SAFE-000001", "qty": 100, "uom": "双"}],
            }},
        },
        {
            "action": "ask_user",
            "summary": "说明缺料",
            "arguments": {"questions": ["基地仓库存为0，是否改为采购？"]},
        },
    ])
    store = RuntimeSessionStore(tmp_path)
    state = RuntimeSessionState(user="pan.feng@stec-up.local", profile="procurement")
    state.selected_entities.update({
        "item": {"kind": "item", "value": "SAFE-000001"},
        "source": {"kind": "warehouse", "value": "蕰川路基地仓库 - SD"},
        "target": {"kind": "warehouse", "value": "合流1.3标仓库 - SD"},
    })
    store.save(state)
    runtime = DeepSeekAgentRuntime(
        planner=planner,
        client_factory=lambda _user: EmptyStockClient(),
        session_store=store,
    )

    result = runtime.run_once("调拨100双手套", user=state.user, today=date(2026, 7, 20))

    assert result.status == "needs_clarification"
    assert result.pending_tool_call is None
    assert result.questions == ("基地仓库存为0，是否改为采购？",)
    assert any(step["label"] == "库存预检未通过" for step in result.steps)


def test_finance_accounts_payable_executes_read_only_without_confirmation(tmp_path: Path) -> None:
    class FinanceReadClient:
        def get_logged_user(self):
            return ToolResult(ok=True, data="fang.wenqian@stec-up.local")

        def run_report(self, report_name, *, filters=None):
            assert report_name == "Accounts Payable"
            assert filters == {"company": "STEC (Demo)", "to_date": "2026-07-20"}
            return ToolResult(ok=True, data={
                "columns": [],
                "result": [{"supplier": "测试供应商", "outstanding_amount": 1200}],
            })

    planner = PlannerSequence([
        {
            "action": "propose_business_action",
            "summary": "查询当前应付",
            "arguments": {"business_intent": {"goal": "query_accounts_payable"}},
        },
        {"action": "finish", "summary": "回复应付", "arguments": {"message": "当前测试供应商应付1200元。"}},
    ])
    runtime = DeepSeekAgentRuntime(
        planner=planner,
        client_factory=lambda _user: FinanceReadClient(),
        session_store=RuntimeSessionStore(tmp_path),
    )

    result = runtime.run_once(
        "查一下今天的应付账款",
        user="fang.wenqian@stec-up.local",
        today=date(2026, 7, 20),
        context={"company": "STEC (Demo)"},
    )

    assert result.status == "completed"
    assert result.pending_tool_call is None
    assert result.tool_results[0]["ok"] is True
    assert result.message == "当前测试供应商应付1200元。"


def test_finance_invoice_from_receipt_confirms_and_verifies_lineage(tmp_path: Path) -> None:
    class FinanceWriteClient:
        def __init__(self):
            self.created = []

        def get_logged_user(self):
            return ToolResult(ok=True, data="fang.wenqian@stec-up.local")

        def get_document(self, doctype, name):
            if (doctype, name) == ("Purchase Receipt", "PRE-001"):
                return ToolResult(ok=True, data={
                    "doctype": doctype,
                    "name": name,
                    "docstatus": 1,
                    "supplier": "测试供应商",
                    "company": "STEC (Demo)",
                    "currency": "CNY",
                    "is_return": 0,
                    "items": [{
                        "name": "PRE-ITEM-001",
                        "item_code": "SAFE-000001",
                        "qty": 100,
                        "billed_qty": 0,
                        "rate": 3,
                        "amount": 300,
                        "warehouse": "合流1.3标仓库 - SD",
                    }],
                })
            if (doctype, name) == ("Purchase Invoice", "PINV-001"):
                return ToolResult(ok=True, data={
                    "doctype": doctype,
                    "name": name,
                    "docstatus": 0,
                    "items": [{"purchase_receipt": "PRE-001", "purchase_receipt_item": "PRE-ITEM-001"}],
                })
            raise AssertionError((doctype, name))

        def create_document(self, doctype, data):
            assert doctype == "Purchase Invoice"
            self.created.append(data)
            return ToolResult(ok=True, data={"doctype": doctype, "name": "PINV-001", "docstatus": 0})

    planner = PlannerSequence([{
        "action": "propose_business_action",
        "summary": "按收货单准备采购发票",
        "arguments": {"business_intent": {
            "goal": "create_purchase_invoice_from_receipt",
            "source_documents": [{"doctype": "Purchase Receipt", "name": "PRE-001"}],
            "bill_no": "SUP-INV-1001",
            "bill_date": "2026-07-19",
        }},
    }])
    store = RuntimeSessionStore(tmp_path)
    state = RuntimeSessionState(user="fang.wenqian@stec-up.local", profile="finance")
    state.selected_entities["receipt"] = {"kind": "document", "value": "PRE-001"}
    store.save(state)
    client = FinanceWriteClient()
    runtime = DeepSeekAgentRuntime(planner=planner, client_factory=lambda _user: client, session_store=store)

    preview = runtime.run_once(
        "按收货单PRE-001开票，发票号SUP-INV-1001，日期7月19日",
        user=state.user,
        today=date(2026, 7, 20),
    )
    assert preview.status == "needs_confirmation"
    assert preview.pending_tool_call["tool"] == "erpnext.accounting.create_purchase_invoice_from_purchase_receipt_draft"
    assert client.created == []

    completed = runtime.run_once("确认", user=state.user, execute=True, today=date(2026, 7, 20))
    assert completed.status == "completed"
    assert len(client.created) == 1
    assert completed.tool_result["verification"]["ok"] is True
    assert "purchase_receipt_lineage_preserved" in completed.tool_result["verification"]["checks"]


def test_project_task_business_action_confirms_and_verifies_project(tmp_path: Path) -> None:
    class ProjectTaskClient:
        def __init__(self):
            self.created = []

        def get_logged_user(self):
            return ToolResult(ok=True, data="hu.yinhu@stec-up.local")

        def get_document(self, doctype, name):
            if (doctype, name) == ("Project", "PROJ-0010"):
                return ToolResult(ok=True, data={"doctype": doctype, "name": name, "project_name": "合流1.3标", "status": "Open"})
            if (doctype, name) == ("Task", "TASK-NEW-001"):
                return ToolResult(ok=True, data={
                    "doctype": doctype, "name": name, "project": "PROJ-0010", "subject": "完成井壁验收",
                    "status": "Open", "priority": "High", "exp_end_date": "2026-07-22",
                })
            raise AssertionError((doctype, name))

        def create_document(self, doctype, data):
            assert doctype == "Task"
            self.created.append(data)
            return ToolResult(ok=True, data={"doctype": doctype, "name": "TASK-NEW-001"})

    planner = PlannerSequence([{
        "action": "propose_business_action",
        "summary": "准备项目任务",
        "arguments": {"business_intent": {
            "goal": "create_project_task", "project": "PRJ-HL-13", "subject": "完成井壁验收", "priority": "High",
            "exp_end_date": "2026-07-22",
        }},
    }])
    store = RuntimeSessionStore(tmp_path)
    client = ProjectTaskClient()
    runtime = DeepSeekAgentRuntime(planner=planner, client_factory=lambda _user: client, session_store=store)

    preview = runtime.run_once(
        "创建任务：7月22日前完成井壁验收，高优先级",
        user="hu.yinhu@stec-up.local",
        today=date(2026, 7, 20),
        context={"project_code": "PRJ-HL-13", "erpnext_project": "PROJ-0010", "warehouse": "合流1.3标仓库 - SD"},
    )
    assert preview.status == "needs_confirmation"
    assert preview.pending_tool_call["tool"] == "erpnext.projects.create_task"
    assert preview.pending_tool_call["arguments"]["project"] == "PROJ-0010"
    assert client.created == []

    completed = runtime.run_once("确认", user="hu.yinhu@stec-up.local", execute=True, today=date(2026, 7, 20))
    assert completed.status == "completed"
    assert len(client.created) == 1
    assert completed.tool_result["verification"]["ok"] is True
    assert "task_fields_verified" in completed.tool_result["verification"]["checks"]


def test_repeated_read_only_business_action_is_executed_once(tmp_path: Path) -> None:
    class ProjectReadClient:
        def __init__(self):
            self.project_reads = 0

        def get_logged_user(self):
            return ToolResult(ok=True, data="hu.yinhu@stec-up.local")

        def get_document(self, doctype, name):
            assert (doctype, name) == ("Project", "PROJ-0010")
            self.project_reads += 1
            return ToolResult(ok=True, data={"doctype": doctype, "name": name, "status": "Open"})

        def search_documents(self, doctype, **_kwargs):
            assert doctype in {"Task", "Stock Entry", "Purchase Receipt"}
            return ToolResult(ok=True, data=[])

    action = {
        "action": "propose_business_action",
        "summary": "查询项目成本",
        "arguments": {"business_intent": {"goal": "query_project_cost"}},
    }
    client = ProjectReadClient()
    varied_action = {
        "action": "propose_business_action",
        "summary": "换日期再次查询项目成本",
        "arguments": {"business_intent": {"goal": "query_project_cost", "from_date": "2026-07-01"}},
    }
    runtime = DeepSeekAgentRuntime(
        planner=PlannerSequence([
            action,
            varied_action,
            {
                "action": "finish",
                "summary": "回复项目成本",
                "arguments": {"message": "当前项目暂无已记录的领料、收货或任务成本。"},
            },
        ]),
        client_factory=lambda _user: client,
        session_store=RuntimeSessionStore(tmp_path),
    )
    result = runtime.run_once(
        "查看当前项目成本",
        user="hu.yinhu@stec-up.local",
        today=date(2026, 7, 20),
        context={"project_code": "PRJ-HL-13", "erpnext_project": "PROJ-0010"},
    )
    assert result.status == "completed"
    assert len(result.tool_results) == 1
    assert result.message == "当前项目暂无已记录的领料、收货或任务成本。"
    assert any(step["label"] == "要求生成最终回复" for step in result.steps)


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


def test_procurement_profile_can_discover_specialized_transfer_tools() -> None:
    policy = make_tool_access_policy("procurement")
    cards = ToolDiscoveryIndex().discover(
        "从基地仓调拨物料到项目仓并检查库存",
        policy=policy,
        modules=["stock"],
        limit=8,
    )

    names = {card["name"] for card in cards}
    assert "erpnext.stock.get_transfer_context" in names
    assert "erpnext.stock.create_transfer_draft" in names


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
    disclosure = next(step for step in result.steps if step["action"] == "capability_required")
    assert disclosure["result"]["capability"]["capability_id"] == "stock.balance.query"
    assert "stock.balance.query" in planner.messages[1][1]["content"]


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
    runtime = DeepSeekAgentRuntime(release=release, planner=planner, session_store=store, client_factory=lambda _user: FakeERPNextClient())

    result = runtime.run_once("明天需要20个物料", user="mao.xiaoquan@stec-up.local", today=__import__("datetime").date(2026, 7, 13))

    assert result.status == "needs_confirmation"
    assert "材料申请草稿" in result.message
    assert result.pending_tool_call["arguments"]["company"] == release.company_name("STEC")
    assert result.pending_tool_call["arguments"]["items"][0]["project"] == "PROJ-0010"
    assert store.load("mao.xiaoquan@stec-up.local", profile="project").pending_action["tool_call"] == result.pending_tool_call


def test_runtime_context_replaces_stable_codes_with_erpnext_link_names(tmp_path: Path) -> None:
    release = MasterDataRelease()
    material = release.materials[0]
    tool = "erpnext.buying.create_material_request_draft"
    planner = PlannerSequence([
        {"action": "get_tool_contracts", "summary": "读取契约", "arguments": {"tool_names": [tool]}},
        {
            "action": "resolve_entities",
            "summary": "解析物料",
            "arguments": {"entities": [{"id": "item", "kind": "item", "query": material["item_code"]}]},
        },
        {
            "action": "execute_tool",
            "summary": "创建材料申请",
            "arguments": {
                "tool_call": {
                    "tool": tool,
                    "arguments": {
                        "material_request_type": "Purchase",
                        "schedule_date": "2026-07-18",
                        "items": [{
                            "item_code": material["item_code"],
                            "qty": 100,
                            "uom": material["stock_uom"],
                                "project": "PROJ-0010",
                                "warehouse": "合流1.3标仓库 - SD",
                        }],
                    },
                },
            },
        },
    ])
    runtime = DeepSeekAgentRuntime(
        release=release,
        planner=planner,
        session_store=RuntimeSessionStore(tmp_path),
        client_factory=lambda _user: FakeERPNextClient(),
    )

    result = runtime.run_once(
        "创建手套材料申请",
        user="mao.xiaoquan@stec-up.local",
        context={
            "project_code": "PRJ-HL-13",
            "erpnext_project": "PROJ-0010",
            "warehouse": "合流1.3标仓库 - SD",
        },
    )

    assert result.status == "needs_confirmation"
    item = result.pending_tool_call["arguments"]["items"][0]
    assert item["project"] == "PROJ-0010"
    assert item["warehouse"] == "合流1.3标仓库 - SD"
    assert not any(step["action"] == "inject_context" for step in result.steps)


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
    assert any("stock.balance.query" in message[1]["content"] for message in planner.messages if len(message) > 1)


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


def test_confirmation_executes_pending_call_and_immediately_returns_tool_result(tmp_path: Path) -> None:
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
    assert completed.message == "Material Request MAT-MR-TEST-0001 已执行成功，当前状态：Draft。"
    assert client.created[0][0] == "Material Request"
    assert len(planner.messages) == 5
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
    assert not any(step["label"] == "生成回复降级" for step in completed.steps)


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
        max_steps=6,
    )

    preview = runtime.run_once("创建草稿", user="mao.xiaoquan@stec-up.local")
    completed = runtime.run_once("确认创建", user="mao.xiaoquan@stec-up.local", execute=True)

    assert preview.status == "needs_confirmation"
    assert completed.status == "completed"
    assert "MAT-MR-TEST-0001" in completed.message
    assert not any(step["label"] == "生成回复降级" for step in completed.steps)


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
    assert not any(step["label"] == "跳过重复动作" for step in completed.steps)


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


def test_operational_date_does_not_reuse_quotation_validity_date() -> None:
    call = {
        "tool": "erpnext.buying.create_supplier_quotation_draft",
        "arguments": {
            "transaction_date": "2026-07-31",
            "valid_till": "2026-07-31",
        },
    }

    corrections = _inject_operational_dates(call, date(2026, 7, 17))

    assert call["arguments"]["transaction_date"] == "2026-07-17"
    assert call["arguments"]["valid_till"] == "2026-07-31"
    assert corrections == [{"field": "transaction_date", "value": "2026-07-17", "source": "runtime.today"}]


def test_resolver_does_not_replace_selected_items_array_with_item_code(tmp_path: Path) -> None:
    runtime = DeepSeekAgentRuntime(session_store=RuntimeSessionStore(tmp_path))
    contract = next(
        item
        for item in runtime.discovery.contracts
        if item.name == "erpnext.buying.create_purchase_order_from_material_request_draft"
    )
    session = RuntimeSessionState(user="pan.feng@stec-up.local", profile="procurement")
    session.selected_entities["item"] = {"kind": "item", "value": "SAFE-000001"}
    arguments = {
        "material_request": "MAT-MR-2026-00001",
        "supplier": "测试建材供应商甲",
        "selected_items": [{"item_code": "SAFE-000001", "qty": 100}],
    }

    _inject_resolved_arguments(arguments, contract, session, [])

    assert arguments["selected_items"] == [{"item_code": "SAFE-000001", "qty": 100}]


def test_generic_purchase_order_is_rejected_when_supplier_quotation_is_resolved() -> None:
    session = RuntimeSessionState(user="pan.feng@stec-up.local", profile="procurement")
    session.selected_entities["quote"] = {
        "kind": "document",
        "value": "PUR-SQTN-2026-00001",
        "row": {"doctype": "Supplier Quotation", "name": "PUR-SQTN-2026-00001"},
    }

    error = _source_document_tool_error(
        "erpnext.buying.create_purchase_order_draft",
        session,
        [],
    )

    assert error == (
        "已解析到Supplier Quotation来源单据，必须使用"
        "erpnext.buying.create_purchase_order_from_supplier_quotation_draft保留来源引用。"
    )


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


def test_pending_confirmation_is_bound_to_session_and_project() -> None:
    session = RuntimeSessionState(user="mao.xiaoquan@stec-up.local", profile="project")
    session.selected_project_code = "PRJ-HL-13"
    session.business_state["conversation_id"] = "conversation-a"
    session.selected_entities["runtime_project"] = {"value": "PROJ-0010"}
    pending = _bind_pending_action(
        {"tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}}},
        session=session,
        user=session.user,
        profile=session.profile,
    )

    assert _pending_binding_error(pending, session=session, user=session.user, profile=session.profile) is None
    session.selected_project_code = "PRJ-NJ-01"
    error = _pending_binding_error(pending, session=session, user=session.user, profile=session.profile)
    assert error and "项目或会话已经变化" in error


def test_pending_confirmation_cannot_move_to_a_new_session() -> None:
    original = RuntimeSessionState(user="mao.xiaoquan@stec-up.local", profile="project")
    pending = _bind_pending_action(
        {"tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}}},
        session=original,
        user=original.user,
        profile=original.profile,
    )
    replacement = RuntimeSessionState(user=original.user, profile=original.profile)

    error = _pending_binding_error(pending, session=replacement, user=replacement.user, profile=replacement.profile)

    assert error and "项目或会话已经变化" in error


def test_pending_confirmation_expires() -> None:
    session = RuntimeSessionState(user="mao.xiaoquan@stec-up.local", profile="project")
    pending = _bind_pending_action(
        {"tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}}},
        session=session,
        user=session.user,
        profile=session.profile,
    )
    pending["binding"]["expires_at"] = "2000-01-01T00:00:00+08:00"

    error = _pending_binding_error(pending, session=session, user=session.user, profile=session.profile)

    assert error and "超过30分钟有效期" in error


def test_expired_pending_confirmation_is_not_executed(tmp_path: Path) -> None:
    user = "mao.xiaoquan@stec-up.local"
    store = RuntimeSessionStore(tmp_path)
    session = RuntimeSessionState(user=user, profile="project")
    session.pending_action = _bind_pending_action(
        {"tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}}},
        session=session,
        user=user,
        profile="project",
    )
    session.pending_action["binding"]["expires_at"] = "2000-01-01T00:00:00+08:00"
    store.save(session)
    client = FakeERPNextClient()
    runtime = DeepSeekAgentRuntime(
        planner=PlannerSequence([]),
        client_factory=lambda _user: client,
        session_store=store,
    )

    result = runtime.run_once("确认执行", user=user, execute=True)

    assert result.status == "failed"
    assert "超过30分钟有效期" in result.message
    assert client.created == []
    assert store.load(user, profile="project").pending_action is None


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
    assert _document_snapshots_from_observation(observation) == [plain]


def test_resolver_observation_sent_to_model_omits_large_internal_material_payload() -> None:
    compact = _compact_agent_observation({
        "type": "resolve_entities",
        "entities": [{
            "id": "item-1",
            "kind": "item",
            "query": "水泥",
            "resolution": {
                "status": "ready",
                "resolved": {
                    "item_code": "MAT-CEM-000008",
                    "sku_name": "水泥 42.5 袋装 50kg",
                    "required_specs": "强度等级：42.5",
                    "stock_uom": "包",
                    "inventory_summary": {"total_available_qty": 0},
                    "data": {"search_keywords": "very large internal payload"},
                },
                "candidates": [{
                    "item_code": "MAT-CEM-000008",
                    "sku_name": "水泥 42.5 袋装 50kg",
                    "data": {"search_keywords": "do not disclose"},
                }],
            },
        }],
        "inventory_query": {"status": "completed", "row_count": 1},
    })

    encoded = str(compact)
    assert "MAT-CEM-000008" in encoded
    assert "inventory_summary" in encoded
    assert "search_keywords" not in encoded
    assert "very large internal payload" not in encoded
