from __future__ import annotations

import os
import tempfile

import pytest

from nexterp_agent.erpnext import ERPNextAdapter, ERPNextClient


def local_adapter() -> ERPNextAdapter:
    required = ["NEXTERP_LOCAL_BASE_URL", "NEXTERP_LOCAL_API_KEY", "NEXTERP_LOCAL_API_SECRET"]
    if any(not os.getenv(name) for name in required):
        pytest.skip("NEXTERP_LOCAL_* credentials are not configured")
    client = ERPNextClient(
        os.environ["NEXTERP_LOCAL_BASE_URL"],
        os.environ["NEXTERP_LOCAL_API_KEY"],
        os.environ["NEXTERP_LOCAL_API_SECRET"],
    )
    return ERPNextAdapter(client)


@pytest.mark.integration
def test_todo_crud_count_comment_assignment_and_attachment() -> None:
    adapter = local_adapter()
    created_name = None
    file_name = None

    created = adapter.execute(
        {
            "tool": "erpnext.create_todo",
            "arguments": {"description": "pytest tool-layer todo", "priority": "Low"},
        }
    )
    assert created.ok, created.to_dict()
    created_name = created.data["name"]

    try:
        fetched = adapter.execute({"tool": "erpnext.get_document", "arguments": {"doctype": "ToDo", "name": created_name}})
        assert fetched.ok, fetched.to_dict()

        updated = adapter.execute(
            {
                "tool": "erpnext.update_document",
                "arguments": {
                    "doctype": "ToDo",
                    "name": created_name,
                    "data": {"description": "pytest tool-layer todo updated"},
                },
            }
        )
        assert updated.ok, updated.to_dict()

        counted = adapter.execute({"tool": "erpnext.count_documents", "arguments": {"doctype": "ToDo"}})
        assert counted.ok, counted.to_dict()

        commented = adapter.execute(
            {
                "tool": "erpnext.add_comment",
                "arguments": {
                    "reference_doctype": "ToDo",
                    "reference_name": created_name,
                    "content": "pytest comment",
                },
            }
        )
        assert commented.ok, commented.to_dict()

        comments = adapter.execute(
            {
                "tool": "erpnext.get_comments",
                "arguments": {"reference_doctype": "ToDo", "reference_name": created_name},
            }
        )
        assert comments.ok, comments.to_dict()

        assigned = adapter.execute(
            {
                "tool": "erpnext.assign_to",
                "arguments": {
                    "doctype": "ToDo",
                    "name": created_name,
                    "assign_to": ["Administrator"],
                    "description": "pytest assignment",
                },
            }
        )
        assert assigned.ok, assigned.to_dict()

        cleared = adapter.execute(
            {
                "tool": "erpnext.clear_assignment",
                "arguments": {"doctype": "ToDo", "name": created_name, "assign_to": "Administrator"},
            }
        )
        assert cleared.ok, cleared.to_dict()

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
            handle.write("pytest attachment")
            path = handle.name

        attached = adapter.execute(
            {
                "tool": "erpnext.attach_file",
                "arguments": {"doctype": "ToDo", "name": created_name, "file_path": path},
            }
        )
        assert attached.ok, attached.to_dict()
        file_name = attached.data["name"]

        attachments = adapter.execute(
            {"tool": "erpnext.list_attachments", "arguments": {"doctype": "ToDo", "name": created_name}}
        )
        assert attachments.ok, attachments.to_dict()
    finally:
        if file_name:
            adapter.execute({"tool": "erpnext.delete_attachment", "arguments": {"file_name": file_name}})
        if created_name:
            adapter.execute({"tool": "erpnext.delete_document", "arguments": {"doctype": "ToDo", "name": created_name}})


@pytest.mark.integration
def test_report_and_bridge_methods() -> None:
    adapter = local_adapter()

    report = adapter.execute(
        {
            "tool": "erpnext.run_report",
            "arguments": {"report_name": "Addresses And Contacts", "filters": {}},
        }
    )
    assert report.ok, report.to_dict()

    bridge = adapter.execute(
        {
            "tool": "erpnext.call_method",
            "arguments": {"method": "agent_bridge.api.get_manager_exceptions", "args": {"limit": 2}},
        }
    )
    assert bridge.ok, bridge.to_dict()


@pytest.mark.integration
def test_item_master_prepare_setup_and_create() -> None:
    adapter = local_adapter()

    setup = adapter.execute({"tool": "erpnext.setup_item_master"})
    assert setup.ok, setup.to_dict()

    incomplete = adapter.execute(
        {
            "tool": "erpnext.prepare_item_from_intent",
            "arguments": {
                "intent": {
                    "raw_text": "新增一个 1.5 冷板，SPCC，宽 1250，卷料，单位公斤",
                    "raw_name": "1.5 冷板",
                    "item_name": "冷轧钢卷",
                    "stock_uom": "Kg",
                    "specs": {
                        "material": "SPCC",
                        "thickness": "1.5mm",
                        "width": "1250mm",
                        "form": "卷料",
                    },
                }
            },
        }
    )
    assert incomplete.ok, incomplete.to_dict()
    assert incomplete.data["status"] == "needs_clarification"

    created_name = None
    created = adapter.execute(
        {
            "tool": "erpnext.create_item_from_intent",
            "arguments": {
                "intent": {
                    "raw_name": "pytest 1.5 冷板",
                    "item_name": "pytest 冷轧钢卷",
                    "item_group_key": "raw_metal_sheet",
                    "stock_uom": "Kg",
                    "specs": {
                        "material": "SPCC",
                        "thickness": "1.5mm",
                        "width": "1250mm",
                        "form": "卷料",
                        "standard": "GB/T 708",
                    },
                }
            },
        }
    )
    assert created.ok, created.to_dict()
    if created.data.get("status") == "created":
        created_name = created.data["item"]["name"]
    try:
        assert created.data["status"] in {"created", "needs_confirmation"}
    finally:
        if created_name:
            adapter.execute({"tool": "erpnext.delete_document", "arguments": {"doctype": "Item", "name": created_name}})
