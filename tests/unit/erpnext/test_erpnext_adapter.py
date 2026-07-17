from __future__ import annotations

from nexterp_agent.erpnext import ERPNextAdapter
from nexterp_agent.erpnext.client import classify_error, normalize_filters
from nexterp_agent.erpnext.schemas import ToolCall, ToolResult


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def get_logged_user(self) -> ToolResult:
        self.calls.append(("get_logged_user",))
        return ToolResult(ok=True, data="test@example.com")

    def search_documents(self, doctype, **kwargs) -> ToolResult:
        self.calls.append(("search_documents", doctype, kwargs))
        return ToolResult(ok=True, data=[])

    def count_documents(self, doctype, **kwargs) -> ToolResult:
        self.calls.append(("count_documents", doctype, kwargs))
        return ToolResult(ok=True, data=3)

    def get_document(self, doctype, name) -> ToolResult:
        self.calls.append(("get_document", doctype, name))
        if doctype == "Item" and name == "RM-MET-SHT-000123":
            return ToolResult(
                ok=True,
                data={
                    "name": name,
                    "item_code": name,
                    "item_name": "冷轧钢卷",
                    "item_group": "原材料",
                    "stock_uom": "Kg",
                    "specification": "SPCC 1.5mm 1250mm 卷料 GB/T 708",
                    "material": "SPCC",
                    "alias_names": "冷板, 冷轧板",
                    "disabled": 0,
                },
            )
        return ToolResult(ok=True, data={"name": name})

    def create_document(self, doctype, data) -> ToolResult:
        self.calls.append(("create_document", doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, **data})

    def update_document(self, doctype, name, data) -> ToolResult:
        self.calls.append(("update_document", doctype, name, data))
        return ToolResult(ok=True, data={"name": name, **data})

    def delete_document(self, doctype, name) -> ToolResult:
        self.calls.append(("delete_document", doctype, name))
        return ToolResult(ok=True, data={"deleted": name})

    def document_exists(self, doctype, name) -> ToolResult:
        self.calls.append(("document_exists", doctype, name))
        return ToolResult(ok=True, data={"exists": True})

    def resolve_link(self, doctype, query, **kwargs) -> ToolResult:
        self.calls.append(("resolve_link", doctype, query, kwargs))
        return ToolResult(ok=True, data=[])

    def validate_fields(self, doctype, fields) -> ToolResult:
        self.calls.append(("validate_fields", doctype, fields))
        return ToolResult(ok=True, data={"valid_fields": fields, "invalid_fields": []})

    def get_doctype_schema(self, doctype) -> ToolResult:
        self.calls.append(("get_doctype_schema", doctype))
        return ToolResult(ok=True, data={"name": doctype})

    def call_method(self, method, args=None, http_method="POST") -> ToolResult:
        self.calls.append(("call_method", method, args, http_method))
        return ToolResult(ok=True, data={"message": "ok"})

    def submit_document(self, doctype, name) -> ToolResult:
        self.calls.append(("submit_document", doctype, name))
        return ToolResult(ok=True, data={"docstatus": 1})

    def cancel_document(self, doctype, name) -> ToolResult:
        self.calls.append(("cancel_document", doctype, name))
        return ToolResult(ok=True, data={"docstatus": 2})

    def amend_document(self, doctype, name) -> ToolResult:
        self.calls.append(("amend_document", doctype, name))
        return ToolResult(ok=True, data={"docstatus": 0})

    def get_workflow_actions(self, doctype, name) -> ToolResult:
        self.calls.append(("get_workflow_actions", doctype, name))
        return ToolResult(ok=True, data=[])

    def apply_workflow(self, doctype, name, action) -> ToolResult:
        self.calls.append(("apply_workflow", doctype, name, action))
        return ToolResult(ok=True, data={"action": action})

    def run_report(self, report_name, **kwargs) -> ToolResult:
        self.calls.append(("run_report", report_name, kwargs))
        return ToolResult(ok=True, data={"columns": [], "result": []})

    def create_todo(self, description, **kwargs) -> ToolResult:
        self.calls.append(("create_todo", description, kwargs))
        return ToolResult(ok=True, data={"description": description})

    def setup_item_master(self) -> ToolResult:
        self.calls.append(("setup_item_master",))
        return ToolResult(ok=True, data={"created": []})

    def prepare_item_from_intent(self, intent) -> ToolResult:
        self.calls.append(("prepare_item_from_intent", intent))
        return ToolResult(ok=True, data={"status": "ready", "intent": intent})

    def create_item_from_intent(self, intent) -> ToolResult:
        self.calls.append(("create_item_from_intent", intent))
        return ToolResult(ok=True, data={"status": "created", "intent": intent})

    def add_comment(self, reference_doctype, reference_name, content, **kwargs) -> ToolResult:
        self.calls.append(("add_comment", reference_doctype, reference_name, content, kwargs))
        return ToolResult(ok=True, data={"content": content})

    def get_comments(self, reference_doctype, reference_name, **kwargs) -> ToolResult:
        self.calls.append(("get_comments", reference_doctype, reference_name, kwargs))
        return ToolResult(ok=True, data=[])

    def assign_to(self, doctype, name, assign_to, **kwargs) -> ToolResult:
        self.calls.append(("assign_to", doctype, name, assign_to, kwargs))
        return ToolResult(ok=True, data=True)

    def clear_assignment(self, doctype, name, assign_to) -> ToolResult:
        self.calls.append(("clear_assignment", doctype, name, assign_to))
        return ToolResult(ok=True, data=True)

    def attach_file(self, doctype, name, file_path, **kwargs) -> ToolResult:
        self.calls.append(("attach_file", doctype, name, file_path, kwargs))
        return ToolResult(ok=True, data={"file_name": file_path})

    def list_attachments(self, doctype, name) -> ToolResult:
        self.calls.append(("list_attachments", doctype, name))
        return ToolResult(ok=True, data=[])

    def delete_attachment(self, file_name) -> ToolResult:
        self.calls.append(("delete_attachment", file_name))
        return ToolResult(ok=True, data={"deleted": file_name})


def test_tool_call_defaults_are_generated() -> None:
    call = ToolCall.from_dict({"tool": "erpnext.search_documents"})

    assert call.id.startswith("toolcall_")
    assert call.created_at
    assert call.arguments == {}
    assert call.risk_level == "L0"


def test_adapter_dispatches_search_documents_and_correlates_result() -> None:
    client = FakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "id": "call_1",
            "tool": "erpnext.search_documents",
            "arguments": {
                "doctype": "Sales Order",
                "filters": {"docstatus": 1},
                "fields": ["name"],
                "limit": 5,
                "offset": 10,
            },
        }
    )

    assert result.ok
    assert result.tool_call_id == "call_1"
    assert result.duration_ms is not None
    assert client.calls == [
        (
            "search_documents",
            "Sales Order",
            {
                "filters": {"docstatus": 1},
                "fields": ["name"],
                "limit": 5,
                "offset": 10,
                "order_by": None,
            },
        )
    ]


def test_adapter_reports_unknown_tool_as_structured_error() -> None:
    adapter = ERPNextAdapter(FakeClient())  # type: ignore[arg-type]

    result = adapter.execute({"id": "bad_tool", "tool": "erpnext.nope"})

    assert not result.ok
    assert result.tool_call_id == "bad_tool"
    assert result.error_type == "unsupported_tool"
    assert "Unsupported tool" in (result.error or "")
    assert result.user_message


def test_adapter_dispatches_search_items_as_tool_result() -> None:
    client = FakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "id": "item_search_1",
            "tool": "erpnext.search_items",
            "arguments": {
                "query": "RM-MET-SHT-000123",
                "specs": {"material": "SPCC"},
                "limit": 5,
            },
        }
    )

    assert result.ok
    assert result.tool_call_id == "item_search_1"
    assert result.data["status"] == "ready"
    assert result.data["candidates"][0]["item_code"] == "RM-MET-SHT-000123"
    assert result.data["questions"] == []


def test_adapter_reports_missing_argument_as_structured_error() -> None:
    adapter = ERPNextAdapter(FakeClient())  # type: ignore[arg-type]

    result = adapter.execute({"tool": "erpnext.get_document", "arguments": {"doctype": "Customer"}})

    assert not result.ok
    assert result.error_type == "missing_argument"
    assert "name" in (result.error or "")


def test_adapter_dispatches_new_tools() -> None:
    client = FakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    calls = [
        {"tool": "erpnext.count_documents", "arguments": {"doctype": "ToDo"}},
        {"tool": "erpnext.validate_fields", "arguments": {"doctype": "ToDo", "fields": ["name"]}},
        {"tool": "erpnext.submit_document", "arguments": {"doctype": "ToDo", "name": "TODO-1"}},
        {"tool": "erpnext.run_report", "arguments": {"report_name": "General Ledger", "filters": {}}},
        {"tool": "erpnext.setup_item_master"},
        {"tool": "erpnext.prepare_item_from_intent", "arguments": {"intent": {"raw_name": "冷板"}}},
        {"tool": "erpnext.create_item_from_intent", "arguments": {"intent": {"raw_name": "冷板"}}},
        {"tool": "erpnext.create_todo", "arguments": {"description": "Follow up"}},
        {
            "tool": "erpnext.add_comment",
            "arguments": {"reference_doctype": "ToDo", "reference_name": "TODO-1", "content": "hello"},
        },
        {"tool": "erpnext.assign_to", "arguments": {"doctype": "ToDo", "name": "TODO-1", "assign_to": ["a@example.com"]}},
        {"tool": "erpnext.attach_file", "arguments": {"doctype": "ToDo", "name": "TODO-1", "file_path": "a.txt"}},
    ]

    for call in calls:
        assert adapter.execute(call).ok

    assert [call[0] for call in client.calls] == [
        "count_documents",
        "validate_fields",
        "submit_document",
        "run_report",
        "setup_item_master",
        "prepare_item_from_intent",
        "create_item_from_intent",
        "create_todo",
        "add_comment",
        "assign_to",
        "attach_file",
    ]


def test_normalize_filters_converts_compact_dict() -> None:
    assert normalize_filters(
        {
            "docstatus": 1,
            "delivery_status": ["!=", "Fully Delivered"],
        }
    ) == [
        ["docstatus", "=", 1],
        ["delivery_status", "!=", "Fully Delivered"],
    ]


def test_classify_error_maps_common_frappe_failures() -> None:
    assert classify_error(403, {}, "Not permitted") == "permission_error"
    assert classify_error(404, {}, "Not found") == "not_found"
    assert classify_error(500, {"exc_type": "ValidationError"}, "ValidationError") == "validation_error"
    assert classify_error(417, {"exc_type": "LinkExistsError"}, "Cannot delete linked document") == "link_validation_error"
    assert classify_error(
        417,
        {"exc_type": "LinkExistsError", "exception": "Missing argument while deleting linked document"},
        "Cannot delete linked document",
    ) == "link_validation_error"
