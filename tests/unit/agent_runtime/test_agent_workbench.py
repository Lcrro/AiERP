from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "agent_workbench.py"
SPEC = importlib.util.spec_from_file_location("agent_workbench", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_employee_catalog_does_not_expose_credentials() -> None:
    employees = MODULE.employee_catalog()

    assert len(employees) == 7
    assert all("api_key" not in employee and "api_secret" not in employee for employee in employees)
    assert {employee["employee_name"] for employee in employees} >= {"张振光", "潘丰", "毛晓泉", "胡银虎"}


def test_result_document_links_build_internal_workbench_route() -> None:
    result = {
        "tool_result": {"data": {"doctype": "Material Request", "name": "MAT-MR-2026-00001"}},
        "tool_results": [],
    }

    assert MODULE.result_document_links(result, "http://localhost:8002") == [
        {
            "doctype": "Material Request",
            "name": "MAT-MR-2026-00001",
            "url": "#document/Material%20Request/MAT-MR-2026-00001",
        }
    ]


def test_pending_confirmation_history_is_explicitly_not_created() -> None:
    result = MODULE.compact_chat_result(
        {
            "status": "needs_confirmation",
            "message": "创建材料申请草稿",
            "pending_tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}},
        },
        "http://localhost:8002",
    )

    assert result["message"] == "我已准备好创建材料申请草稿，但尚未写入 ERPNext。请确认后再执行。"


def test_successful_document_is_not_shown_failed_when_final_reply_failed() -> None:
    tool_result = {
        "ok": True,
        "data": {"doctype": "Material Request", "name": "MAT-MR-2026-00015"},
    }

    result = MODULE.compact_chat_result(
        {
            "status": "failed",
            "message": "DeepSeek规划失败：finish.arguments.message is required",
            "tool_result": tool_result,
            "tool_results": [tool_result],
        },
        "http://localhost:8002",
    )

    assert result["status"] == "completed"
    assert "MAT-MR-2026-00015 已在 ERPNext 中执行成功" in result["message"]


def test_document_process_without_workflow_explains_direct_submission() -> None:
    process = MODULE.document_process_summary(
        "Material Request",
        {"docstatus": 0, "status": "Draft", "_assign": "[]"},
    )

    assert process["state"] == "草稿"
    assert process["workflow_configured"] is False
    assert process["can_submit"] is True
    assert "直接成为已提交状态" in process["description"]
    assert process["notification"] == "当前没有审批待办接收人"


def test_document_process_shows_workflow_state_and_assignees() -> None:
    process = MODULE.document_process_summary(
        "Material Request",
        {"docstatus": 0, "workflow_state": "等待项目经理审批", "_assign": '["manager@example.com"]'},
    )

    assert process["state"] == "等待项目经理审批"
    assert process["workflow_configured"] is True
    assert process["assignees"] == ["manager@example.com"]
    assert process["notification"] == "已生成审批分配"


def test_document_process_exposes_only_current_users_workflow_actions() -> None:
    process = MODULE.document_process_summary(
        "Material Request",
        {"docstatus": 0, "workflow_state": "待材料设备主管审批", "_assign": "[]"},
        ["批准", "驳回"],
    )

    assert process["available_actions"] == ["批准", "驳回"]
    assert process["can_submit"] is False
    assert process["notification"] == "当前账号可执行：批准、驳回"


def test_workbench_workflow_button_executes_erpnext_directly_without_agent() -> None:
    calls = []

    class FakeClient:
        def get_workflow_actions(self, doctype, name):
            calls.append(("get_workflow_actions", doctype, name))
            return SimpleNamespace(ok=True, data=[{"action": "提交申请"}], user_message=None, error=None)

        def apply_workflow(self, doctype, name, action):
            calls.append(("apply_workflow", doctype, name, action))
            return SimpleNamespace(ok=True, data={"name": name}, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.document = lambda user, doctype, name: {"doctype": doctype, "name": name, "user": user}

    result = service.apply_workflow_action(
        "clerk@example.com",
        "Material Request",
        "MAT-MR-0001",
        "提交申请",
    )

    assert result["name"] == "MAT-MR-0001"
    assert calls == [
        ("get_workflow_actions", "Material Request", "MAT-MR-0001"),
        ("apply_workflow", "Material Request", "MAT-MR-0001", "提交申请"),
    ]


def test_reset_documents_cancels_submitted_documents_before_deleting() -> None:
    calls = []

    class FakeClient:
        def cancel_document(self, doctype, name):
            calls.append(("cancel", doctype, name))
            return SimpleNamespace(ok=True, user_message=None, error=None)

        def delete_document(self, doctype, name):
            calls.append(("delete", doctype, name))
            return SimpleNamespace(ok=True, user_message=None, error=None)

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.documents = lambda user, project, **kwargs: {
        "erpnext_project": "PROJ-0010",
        "modules": [{"groups": [
            {"doctype": "Material Request", "documents": [{"name": "MR-1", "docstatus": 1}]},
            {"doctype": "Purchase Invoice", "documents": [{"name": "PI-1", "docstatus": 0}]},
            {"doctype": "Request for Quotation", "documents": [{"name": "RFQ-KEEP", "docstatus": 0}]},
        ]}],
    }
    service.client = lambda user: FakeClient()

    result = service.reset_documents("buyer@example.com", "PRJ-HL-13")

    assert calls == [
        ("delete", "Purchase Invoice", "PI-1"),
        ("cancel", "Material Request", "MR-1"),
        ("delete", "Material Request", "MR-1"),
    ]
    assert result["deleted_count"] == 2
    assert result["failed_count"] == 0


def test_project_catalog_contains_project_specific_and_organization_employees() -> None:
    projects = {row["project_code"]: row for row in MODULE.project_catalog()}
    names = {row["employee_name"] for row in projects["PRJ-HL-13"]["employees"]}

    assert projects["PRJ-HL-13"]["project_short_name"] == "合流1.3标"
    assert {"张振光", "林乔航", "毛晓泉", "徐溥祺"} <= names
    assert "梁志华" not in names


def test_session_history_restores_visible_chat_and_reset_clears_context(tmp_path: Path) -> None:
    user = "mao.xiaoquan@stec-up.local"
    store = MODULE.RuntimeSessionStore(tmp_path)
    session = store.load(user, profile="project")
    session.pending_action = {"tool_call": {"tool": "erpnext.buying.create_material_request_draft", "arguments": {}}}
    session.add_turn({
        "user_text": "帮我采购点水泥",
        "result": {
            "status": "needs_clarification",
            "message": "请选择具体水泥。",
            "questions": ["请选择具体水泥。"],
            "candidates": [{
                "item_code": "MAT-CEM-000011",
                "sku_name": "水泥 PC425 袋装 50kg",
                "stock_uom": "包",
                "required_specs": "强度等级：42.5",
                "search_keywords": "不应传给网页",
            }],
        },
    })
    store.save(session)
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.session_store = store
    service.base_url = "http://localhost:8002"

    history = service.session_history(user)

    assert history["latest_user_text"] == "帮我采购点水泥"
    assert history["turns"][0]["result"]["message"] == "请选择具体水泥。"
    assert history["turns"][0]["result"]["candidates"] == [{
        "item_code": "MAT-CEM-000011",
        "sku_name": "水泥 PC425 袋装 50kg",
        "required_specs": "强度等级：42.5",
        "stock_uom": "包",
    }]
    assert service.reset_session(user) == {"reset": True, "had_history": True}
    assert service.session_history(user)["turns"] == []


def test_conversations_are_isolated_by_employee_project_and_conversation(tmp_path: Path) -> None:
    user = "mao.xiaoquan@stec-up.local"
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.session_store = MODULE.RuntimeSessionStore(tmp_path)
    service.base_url = "http://localhost:8002"

    first = service.scoped_session_store(user, "PRJ-HL-13", "conversation-a")
    session = first.load(user, profile="project")
    session.add_turn({"user_text": "合流项目要水泥", "result": {"message": "收到"}})
    first.save(session)

    assert service.session_history(user, "PRJ-HL-13", "conversation-a")["turns"]
    assert service.session_history(user, "PRJ-HL-13", "conversation-b")["turns"] == []
    assert service.session_history(user, "PRJ-NJ-01", "conversation-a")["turns"] == []


def test_documents_are_loaded_by_module_with_page_offset() -> None:
    calls = []
    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service._project_name_cache = {}
    service.client = lambda _user: object()
    service.erpnext_project_name = lambda _client, _project: "ERP-PROJECT"

    def load_group(user, doctype, label, project_child, project, limit, offset, status, owner):
        calls.append((doctype, limit, offset, status, owner))
        return {"doctype": doctype, "label": label, "documents": []}

    service._load_document_group = load_group
    result = service.documents(
        "buyer@example.com",
        "PRJ-HL-13",
        module="buying",
        status="Draft",
        page=3,
        page_size=10,
        mine_only=True,
    )

    assert result["module"] == "buying"
    assert {call[0] for call in calls} == set(MODULE.MODULE_DOCTYPES["buying"])
    assert all(call[1:] == (10, 20, "Draft", "buyer@example.com") for call in calls)


def test_inbox_uses_open_erpnext_workflow_actions_and_real_transitions() -> None:
    class FakeClient:
        def search_documents(self, doctype, **kwargs):
            assert doctype == "Workflow Action"
            assert kwargs["filters"] == {"status": "Open"}
            return SimpleNamespace(ok=True, data=[{
                "name": "WA-1",
                "reference_doctype": "Material Request",
                "reference_name": "MR-1",
                "workflow_state": "待材料设备主管审批",
                "modified": "2026-07-15 12:00:00",
            }], user_message=None, error=None)

        def call_method(self, method, arguments):
            assert method == "agent_bridge.api.get_document_with_workflow_actions"
            assert arguments == {"doctype": "Material Request", "name": "MR-1"}
            return SimpleNamespace(ok=True, data={
                "document": {"name": "MR-1", "title": "手套申请", "owner": "clerk@example.com"},
                "actions": [{"action": "批准"}, {"action": "驳回"}],
            })

    service = MODULE.AgentWorkbenchService.__new__(MODULE.AgentWorkbenchService)
    service.client = lambda _user: FakeClient()
    service.erpnext_project_name = lambda _client, _project: ""

    result = service.inbox("supervisor@example.com")

    assert result["count"] == 1
    assert result["items"][0]["actions"] == ["批准", "驳回"]
    assert result["items"][0]["title"] == "手套申请"
