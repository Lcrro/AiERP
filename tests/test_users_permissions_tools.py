from __future__ import annotations

from nexterp_agent.erpnext import ERPNextAdapter
from nexterp_agent.erpnext.schemas import ToolCall, ToolResult


class UsersFakeClient:
    def __init__(self) -> None:
        self.calls = []
        self.enabled = 1

    def search_documents(self, doctype, **kwargs) -> ToolResult:
        self.calls.append(("search_documents", doctype, kwargs))
        return ToolResult(ok=True, data=[{"name": "alice@example.com"}])

    def get_document(self, doctype, name) -> ToolResult:
        self.calls.append(("get_document", doctype, name))
        if doctype == "Role Profile":
            return ToolResult(
                ok=True,
                data={
                    "doctype": "Role Profile",
                    "name": name,
                    "role_profile": name,
                    "roles": [{"role": "Sales User"}, {"role": "Accounts User"}],
                },
            )
        return ToolResult(
            ok=True,
            data={
                "name": name,
                "email": name,
                "full_name": "Alice Admin",
                "enabled": self.enabled,
                "user_type": "System User",
                "role_profile_name": None,
                "roles": [{"role": "Sales User"}, {"role": "Stock User"}],
            },
        )

    def get_doctype_schema(self, doctype) -> ToolResult:
        self.calls.append(("get_doctype_schema", doctype))
        return ToolResult(
            ok=True,
            data={
                "permissions": [
                    {"role": "Sales User", "read": 1, "write": 1, "create": 1, "email": 1},
                    {"role": "Stock User", "read": 1, "report": 1, "export": 1},
                    {"role": "Accounts User", "read": 1, "submit": 1},
                    {"role": "All", "print": 1},
                ]
            },
        )

    def create_document(self, doctype, data) -> ToolResult:
        self.calls.append(("create_document", doctype, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": data.get("email") or "UP-1", **data})

    def update_document(self, doctype, name, data) -> ToolResult:
        self.calls.append(("update_document", doctype, name, data))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name, **data})

    def delete_document(self, doctype, name) -> ToolResult:
        self.calls.append(("delete_document", doctype, name))
        return ToolResult(ok=True, data={"doctype": doctype, "name": name})

    def check_user_permission(self, user, doctype, action, *, docname=None, debug=False) -> ToolResult:
        self.calls.append(("check_user_permission", user, doctype, action, docname, debug))
        return ToolResult(
            ok=True,
            data={
                "user": user,
                "doctype": doctype,
                "docname": docname,
                "action": action,
                "allowed": False,
                "is_exact_runtime_evaluation": True,
                "evaluation": "frappe.permissions.has_permission",
            },
        )


def _confirmation() -> dict[str, str | bool]:
    return {
        "confirmed": True,
        "confirmed_by": "admin@example.com",
        "confirmed_at": "2026-06-09T10:00:00Z",
        "confirmation_text": "Confirm Users & Permissions admin change.",
        "reason": "Approved by module owner.",
    }


def test_users_read_tool_returns_module_result_shape() -> None:
    client = UsersFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute({"tool": "erpnext.users.list_users", "arguments": {"enabled": True}})

    assert result.ok
    assert result.data["doctype"] == "User"
    assert result.data["status"] == "Read Only"
    assert result.data["risk"]["level"] == "L0"
    assert result.data["records"] == [{"name": "alice@example.com"}]
    assert client.calls == [
        (
            "search_documents",
            "User",
            {
                "filters": [["enabled", "=", 1]],
                "fields": [
                    "name",
                    "email",
                    "first_name",
                    "last_name",
                    "full_name",
                    "enabled",
                    "user_type",
                    "role_profile_name",
                    "last_login",
                    "last_active",
                    "modified",
                ],
                "limit": 50,
                "offset": 0,
                "order_by": "modified desc",
            },
        )
    ]


def test_admin_write_requires_confirmation_and_returns_preview() -> None:
    client = UsersFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.users.set_user_enabled",
            "arguments": {"user": "alice@example.com", "enabled": False},
        }
    )

    assert not result.ok
    assert result.error_type == "admin_confirmation_required"
    assert result.data["risk"]["level"] == "L5_ADMIN"
    assert result.data["preview"] == {"enabled": 0}
    assert client.calls == []


def test_assign_roles_with_confirmation_updates_roles() -> None:
    client = UsersFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.users.assign_roles",
            "arguments": {
                "user": "alice@example.com",
                "mode": "add",
                "roles": ["Accounts User"],
                "confirmation": _confirmation(),
            },
        }
    )

    assert result.ok
    assert result.data["risk"]["level"] == "L5_ADMIN"
    assert client.calls == [
        ("get_document", "User", "alice@example.com"),
        (
            "update_document",
            "User",
            "alice@example.com",
            {"roles": [{"role": "Accounts User"}, {"role": "Sales User"}, {"role": "Stock User"}]},
        ),
    ]


def test_user_access_summary_includes_roles_and_permissions() -> None:
    client = UsersFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.users.get_user_access_summary",
            "arguments": {"user": "alice@example.com"},
        }
    )

    assert result.ok
    assert result.data["roles"] == ["Sales User", "Stock User"]
    assert result.data["risk"]["level"] == "L0"
    assert [call[0] for call in client.calls] == ["get_document", "search_documents"]


def test_preview_role_profile_roles_is_read_only() -> None:
    client = UsersFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.users.preview_role_profile_roles",
            "arguments": {"role_profile": "Sales And Accounts"},
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Role Profile"
    assert result.data["status"] == "Preview"
    assert result.data["roles"] == ["Sales User", "Accounts User"]
    assert result.data["role_count"] == 2
    assert result.data["risk"]["level"] == "L0"
    assert client.calls == [("get_document", "Role Profile", "Sales And Accounts")]


def test_preview_effective_permissions_uses_metadata_and_user_permissions() -> None:
    client = UsersFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.users.preview_effective_permissions",
            "arguments": {"user": "alice@example.com", "doctype": "Sales Order"},
        }
    )

    assert result.ok
    assert result.data["doctype"] == "Sales Order"
    assert result.data["user"] == "alice@example.com"
    assert result.data["status"] == "Preview"
    assert result.data["risk"]["level"] == "L0"
    assert result.data["roles"] == ["Sales User", "Stock User"]
    assert result.data["permissions"]["read"] is True
    assert result.data["permissions"]["write"] is True
    assert result.data["permissions"]["create"] is True
    assert result.data["permissions"]["report"] is True
    assert result.data["permissions"]["export"] is True
    assert result.data["permissions"]["print"] is True
    assert result.data["permissions"]["submit"] is False
    assert result.data["is_exact_runtime_evaluation"] is False
    assert [row["role"] for row in result.data["matched_permission_rows"]] == ["Sales User", "Stock User", "All"]
    assert result.data["user_permissions"] == [{"name": "alice@example.com"}]
    assert client.calls == [
        ("get_document", "User", "alice@example.com"),
        ("get_doctype_schema", "Sales Order"),
        (
            "search_documents",
            "User Permission",
            {
                "filters": {"user": "alice@example.com"},
                "fields": ["name", "user", "allow", "for_value", "applicable_for", "is_default", "hide_descendants"],
                "limit": 100,
                "order_by": "modified desc",
            },
        ),
    ]


def test_preview_effective_permissions_disabled_user_has_no_effective_actions() -> None:
    client = UsersFakeClient()
    client.enabled = 0
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.users.preview_effective_permissions",
            "arguments": {
                "user": "alice@example.com",
                "doctype": "Sales Order",
                "include_user_permissions": False,
            },
        }
    )

    assert result.ok
    assert result.data["enabled"] == 0
    assert all(value is False for value in result.data["permissions"].values())
    assert result.data["user_permissions"] is None
    assert [call[0] for call in client.calls] == ["get_document", "get_doctype_schema"]


def test_check_server_permission_compares_metadata_preview_with_runtime_bridge() -> None:
    client = UsersFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.users.check_server_permission",
            "arguments": {
                "user": "alice@example.com",
                "doctype": "Sales Order",
                "docname": "SO-1",
                "action": "write",
                "debug": True,
            },
        }
    )

    assert result.ok
    assert result.data["status"] == "Checked"
    assert result.data["allowed"] is False
    assert result.data["metadata_preview"]["allowed"] is True
    assert result.data["differences"] == {
        "action": "write",
        "metadata_preview_allowed": True,
        "server_runtime_allowed": False,
        "differs": True,
        "likely_reasons": ["owner_rule", "docshare", "user_permission", "controller_hook", "workflow_state"],
    }
    assert result.data["risk"]["level"] == "L0"
    assert client.calls == [
        ("get_document", "User", "alice@example.com"),
        ("get_doctype_schema", "Sales Order"),
        ("check_user_permission", "alice@example.com", "Sales Order", "write", "SO-1", True),
    ]


def test_preview_permission_policy_change_returns_diff_without_writing() -> None:
    client = UsersFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.users.preview_permission_policy_change",
            "arguments": {
                "doctype": "Sales Order",
                "changes": [
                    {
                        "operation": "add",
                        "role": "Purchase User",
                        "permlevel": 0,
                        "permissions": {"read": True, "write": True, "apply_user_permissions": True},
                    },
                    {
                        "operation": "update",
                        "match": {"role": "Sales User", "permlevel": 0},
                        "permissions": {"write": False, "submit": True},
                    },
                    {"operation": "remove", "match": {"role": "All", "permlevel": 0}},
                ],
            },
        }
    )

    assert result.ok
    assert result.data["status"] == "Permission Policy Preview"
    assert result.data["risk"] == {
        "level": "L5_ADMIN",
        "preview_only": True,
        "writes_to_erpnext": False,
        "changes_system_wide_permission_policy": True,
    }
    assert len(result.data["before"]) == 4
    assert len(result.data["after"]) == 4
    assert result.data["diff"]["added"][0]["role"] == "Purchase User"
    assert result.data["diff"]["added"][0]["read"] is True
    assert result.data["diff"]["added"][0]["apply_user_permissions"] is True
    assert result.data["diff"]["updated"][0]["match"] == {"role": "Sales User", "permlevel": 0}
    assert result.data["diff"]["updated"][0]["changed_fields"] == {
        "write": {"before": True, "after": False},
        "submit": {"before": False, "after": True},
    }
    assert result.data["diff"]["removed"][0]["role"] == "All"
    assert client.calls == [("get_doctype_schema", "Sales Order")]


def test_preview_permission_policy_change_rejects_invalid_fields_without_writing() -> None:
    client = UsersFakeClient()
    adapter = ERPNextAdapter(client)  # type: ignore[arg-type]

    result = adapter.execute(
        {
            "tool": "erpnext.users.preview_permission_policy_change",
            "arguments": {
                "doctype": "Sales Order",
                "changes": [
                    {
                        "operation": "update",
                        "match": {"role": "Sales User", "permlevel": 0},
                        "permissions": {"drop_database": True},
                    }
                ],
            },
        }
    )

    assert not result.ok
    assert result.error_type == "validation_error"
    assert result.data["unsupported_fields"] == ["drop_database"]
    assert client.calls == [("get_doctype_schema", "Sales Order")]


def test_users_tools_infer_expected_risk_levels() -> None:
    assert ToolCall.from_dict({"tool": "erpnext.users.list_roles"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.users.preview_role_profile_roles"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.users.preview_effective_permissions"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.users.check_server_permission"}).risk_level == "L0"
    assert ToolCall.from_dict({"tool": "erpnext.users.preview_permission_policy_change"}).risk_level == "L5_ADMIN"
    assert ToolCall.from_dict({"tool": "erpnext.users.assign_roles"}).risk_level == "L5_ADMIN"
    assert ToolCall.from_dict({"tool": "erpnext.users.create_user_permission"}).risk_level == "L5_ADMIN"
