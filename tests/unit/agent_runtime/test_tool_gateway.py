from __future__ import annotations

from nexterp_agent.agent_runtime import (
    ToolGateway,
    ToolSession,
    filter_tool_schemas_for_policy,
    make_tool_access_policy,
)
from nexterp_agent.erpnext.schemas import ToolCall, ToolResult


class FakeClient:
    def __init__(self, logged_user: str = "buyer@example.com") -> None:
        self.logged_user = logged_user
        self.calls: list[tuple[str]] = []

    def get_logged_user(self) -> ToolResult:
        self.calls.append(("get_logged_user",))
        return ToolResult(ok=True, data=self.logged_user)


class FakeAdapter:
    def __init__(self, logged_user: str = "buyer@example.com") -> None:
        self.client = FakeClient(logged_user)
        self.calls: list[ToolCall] = []

    def execute(self, tool_call: ToolCall) -> ToolResult:
        self.calls.append(tool_call)
        return ToolResult(ok=True, data={"tool": tool_call.tool}).with_call(tool_call, duration_ms=1)


def test_procurement_gateway_allows_profile_tool() -> None:
    adapter = FakeAdapter()
    gateway = ToolGateway(adapter, ToolSession(user=None, policy=make_tool_access_policy("采购员")))

    result = gateway.execute(
        {
            "id": "mr_1",
            "tool": "erpnext.buying.create_material_request_draft",
            "arguments": {"items": [{"item_code": "SAFE-000001", "qty": 1}]},
        }
    )

    assert result.ok
    assert result.tool_call_id == "mr_1"
    assert [call.tool for call in adapter.calls] == ["erpnext.buying.create_material_request_draft"]


def test_procurement_schema_filter_excludes_hidden_tools() -> None:
    policy = make_tool_access_policy("采购员")

    schema_names = {schema["name"] for schema in filter_tool_schemas_for_policy(policy)}

    assert "erpnext.buying.create_material_request_draft" in schema_names
    assert "erpnext.create_document" not in schema_names
    assert "erpnext.stock.create_reconciliation_draft" not in schema_names
    assert "erpnext.search_documents" not in schema_names


def test_procurement_gateway_blocks_stock_write_tool_before_adapter() -> None:
    adapter = FakeAdapter()
    gateway = ToolGateway(adapter, ToolSession(user=None, policy=make_tool_access_policy("采购员")))

    result = gateway.execute(
        {
            "id": "stock_write",
            "tool": "erpnext.stock.create_reconciliation_draft",
            "arguments": {"data": {"items": []}},
        }
    )

    assert not result.ok
    assert result.tool_call_id == "stock_write"
    assert result.error_type == "permission_error"
    assert result.meta["reason"] == "not_in_profile_allowlist"
    assert adapter.calls == []


def test_employee_gateway_blocks_developer_only_generic_tool() -> None:
    adapter = FakeAdapter()
    gateway = ToolGateway(adapter, ToolSession(user=None, policy=make_tool_access_policy("采购员")))

    result = gateway.execute(
        {
            "id": "raw_create",
            "tool": "erpnext.create_document",
            "arguments": {"doctype": "Stock Reconciliation", "data": {}},
        }
    )

    assert not result.ok
    assert result.error_type == "permission_error"
    assert result.meta["reason"] == "developer_only_tool"
    assert adapter.calls == []


def test_runtime_internal_tool_is_not_available_to_model_origin() -> None:
    adapter = FakeAdapter()
    policy = make_tool_access_policy(
        "采购员",
        extra_allowed_tools={"erpnext.search_documents"},
        allow_runtime_internal=True,
    )
    gateway = ToolGateway(adapter, ToolSession(user=None, policy=policy))

    result = gateway.execute(
        {
            "id": "search_1",
            "tool": "erpnext.search_documents",
            "arguments": {"doctype": "Material Request"},
        }
    )

    assert not result.ok
    assert result.meta["reason"] == "runtime_internal_tool"
    assert adapter.calls == []


def test_runtime_internal_tool_can_be_used_by_runtime_origin_when_allowlisted() -> None:
    adapter = FakeAdapter()
    policy = make_tool_access_policy(
        "采购员",
        extra_allowed_tools={"erpnext.search_documents"},
        allow_runtime_internal=True,
    )
    gateway = ToolGateway(adapter, ToolSession(user=None, policy=policy))

    result = gateway.execute(
        {
            "id": "search_1",
            "tool": "erpnext.search_documents",
            "arguments": {"doctype": "Material Request"},
        },
        origin="runtime",
    )

    assert result.ok
    assert [call.tool for call in adapter.calls] == ["erpnext.search_documents"]


def test_gateway_rejects_identity_mismatch_before_adapter() -> None:
    adapter = FakeAdapter(logged_user="administrator@example.com")
    gateway = ToolGateway(
        adapter,
        ToolSession(
            user="buyer@example.com",
            policy=make_tool_access_policy("采购员"),
            verify_erpnext_identity=True,
        ),
    )

    result = gateway.execute(
        {
            "id": "mr_1",
            "tool": "erpnext.buying.create_material_request_draft",
            "arguments": {"items": [{"item_code": "SAFE-000001", "qty": 1}]},
        }
    )

    assert not result.ok
    assert result.error_type == "permission_error"
    assert result.meta["expected_user"] == "buyer@example.com"
    assert result.meta["actual_user"] == "administrator@example.com"
    assert adapter.calls == []
    assert adapter.client.calls == [("get_logged_user",)]


def test_developer_profile_can_execute_developer_only_tool() -> None:
    adapter = FakeAdapter()
    gateway = ToolGateway(adapter, ToolSession(user=None, policy=make_tool_access_policy("developer")))

    result = gateway.execute(
        {
            "id": "raw_create",
            "tool": "erpnext.create_document",
            "arguments": {"doctype": "ToDo", "data": {"description": "dev"}},
        }
    )

    assert result.ok
    assert [call.tool for call in adapter.calls] == ["erpnext.create_document"]
