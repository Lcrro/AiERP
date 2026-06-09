from __future__ import annotations

from typing import Any

from ..schemas import ToolResult
from .common import *

class UsersPermissionsToolsMixin:
    def _users_list_users(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("enabled", "user_type", "role_profile_name"))
        if args.get("query"):
            filters.append(["full_name", "like", f"%{args['query']}%"])
        result = self.client.search_documents(
            "User",
            filters=filters or None,
            fields=[
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
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="modified desc",
        )
        return _users_read_result(result, "User", "Listed ERPNext users.")

    def _users_get_user_access_summary(self, args: dict[str, Any]) -> ToolResult:
        user = args["user"]
        doc = self.client.get_document("User", user)
        if not doc.ok:
            return doc
        data = doc.data if isinstance(doc.data, dict) else {}
        roles = [
            row.get("role")
            for row in data.get("roles", [])
            if isinstance(row, dict) and row.get("role")
        ]
        permissions = None
        if args.get("include_permissions", True):
            permissions_result = self.client.search_documents(
                "User Permission",
                filters={"user": user},
                fields=["name", "user", "allow", "for_value", "applicable_for", "is_default", "hide_descendants"],
                limit=100,
                order_by="modified desc",
            )
            if not permissions_result.ok:
                return permissions_result
            permissions = permissions_result.data
        return ToolResult(
            ok=True,
            status_code=doc.status_code,
            raw_status_code=doc.raw_status_code,
            data={
                "doctype": "User",
                "name": data.get("name") or user,
                "status": "Enabled" if data.get("enabled") else "Disabled",
                "summary": f"Access summary for {data.get('name') or user}.",
                "user": {
                    "email": data.get("email"),
                    "full_name": data.get("full_name"),
                    "enabled": data.get("enabled"),
                    "user_type": data.get("user_type"),
                    "role_profile_name": data.get("role_profile_name"),
                },
                "roles": roles,
                "user_permissions": permissions,
                "next_actions": ["review_roles", "review_user_permissions"],
                "risk": {"level": "L0", "admin_write_tools_require_confirmation": True},
            },
            debug={"raw_document": data},
        )

    def _users_list_roles(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("disabled", "desk_access"))
        if args.get("query"):
            filters.append(["role_name", "like", f"%{args['query']}%"])
        result = self.client.search_documents(
            "Role",
            filters=filters or None,
            fields=["name", "role_name", "desk_access", "disabled", "is_custom", "modified"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="role_name asc",
        )
        return _users_read_result(result, "Role", "Listed ERPNext roles.")

    def _users_list_role_profiles(self, args: dict[str, Any]) -> ToolResult:
        filters = []
        if args.get("query"):
            filters.append(["role_profile", "like", f"%{args['query']}%"])
        result = self.client.search_documents(
            "Role Profile",
            filters=filters or None,
            fields=["name", "role_profile", "modified"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="modified desc",
        )
        return _users_read_result(result, "Role Profile", "Listed ERPNext role profiles.")

    def _users_preview_role_profile_roles(self, args: dict[str, Any]) -> ToolResult:
        role_profile = args["role_profile"]
        result = self.client.get_document("Role Profile", role_profile)
        if not result.ok:
            return result
        data = result.data if isinstance(result.data, dict) else {}
        role_rows = data.get("roles") or []
        roles = [
            row.get("role")
            for row in role_rows
            if isinstance(row, dict) and row.get("role")
        ]
        return ToolResult(
            ok=True,
            status_code=result.status_code,
            raw_status_code=result.raw_status_code,
            data={
                "doctype": "Role Profile",
                "name": data.get("name") or role_profile,
                "status": "Preview",
                "summary": f"Role Profile {role_profile} expands to {len(roles)} role(s).",
                "role_profile": role_profile,
                "roles": roles,
                "role_count": len(roles),
                "next_actions": ["review_roles", "use_create_user_draft_or_assign_roles"],
                "risk": {"level": "L0", "admin_write_tools_require_confirmation": True},
            },
            debug={"raw_document": data},
        )

    def _users_list_user_permissions(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("user", "allow", "for_value", "applicable_for"))
        result = self.client.search_documents(
            "User Permission",
            filters=filters or None,
            fields=["name", "user", "allow", "for_value", "applicable_for", "is_default", "hide_descendants", "modified"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="modified desc",
        )
        return _users_read_result(result, "User Permission", "Listed user permission rows.")

    def _users_list_shared_documents(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("user", "share_doctype", "share_name"))
        result = self.client.search_documents(
            "DocShare",
            filters=filters or None,
            fields=["name", "user", "share_doctype", "share_name", "read", "write", "share", "everyone", "modified"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="modified desc",
        )
        return _users_read_result(result, "DocShare", "Listed shared document rows.")

    def _users_list_access_logs(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("user",))
        result = self.client.search_documents(
            "Access Log",
            filters=filters or None,
            fields=["name", "user", "file_type", "method", "reference_document", "creation"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="creation desc",
        )
        return _users_read_result(result, "Access Log", "Listed access log rows.")

    def _users_list_activity_logs(self, args: dict[str, Any]) -> ToolResult:
        filters = _users_filters(args, ("user", "subject"))
        result = self.client.search_documents(
            "Activity Log",
            filters=filters or None,
            fields=["name", "user", "subject", "operation", "reference_doctype", "reference_name", "creation"],
            limit=args.get("limit", 50),
            offset=args.get("offset", 0),
            order_by="creation desc",
        )
        return _users_read_result(result, "Activity Log", "Listed activity log rows.")

    def _users_get_permission_metadata(self, args: dict[str, Any]) -> ToolResult:
        schema = self.client.get_doctype_schema(args["doctype"])
        if not schema.ok:
            return schema
        data = schema.data if isinstance(schema.data, dict) else {}
        permissions = data.get("permissions") or []
        docs = data.get("docs")
        if not permissions and isinstance(docs, list) and docs and isinstance(docs[0], dict):
            permissions = docs[0].get("permissions") or []
        return ToolResult(
            ok=True,
            status_code=schema.status_code,
            raw_status_code=schema.raw_status_code,
            data={
                "doctype": args["doctype"],
                "status": "Read Only",
                "summary": f"Permission metadata for {args['doctype']}.",
                "permissions": permissions or [],
                "next_actions": ["review_docperm_rows", "use_generic_schema_for_fields"],
                "risk": {"level": "L0", "changing_docperm_is_L5_ADMIN": True},
            },
            debug={"raw_schema": data},
        )

    def _users_build_metadata_permission_preview(self, user: str, doctype: str) -> ToolResult:
        user_doc = self.client.get_document("User", user)
        if not user_doc.ok:
            return user_doc
        schema = self.client.get_doctype_schema(doctype)
        if not schema.ok:
            return schema

        user_data = user_doc.data if isinstance(user_doc.data, dict) else {}
        schema_data = schema.data if isinstance(schema.data, dict) else {}
        role_names = {
            row.get("role")
            for row in user_data.get("roles", [])
            if isinstance(row, dict) and row.get("role")
        }
        role_names.discard(None)
        permission_rows = _extract_permission_rows(schema_data)
        effective, matched_rows = _metadata_effective_permissions(role_names, permission_rows)
        if not user_data.get("enabled", 1):
            effective = {key: False for key in effective}

        return ToolResult(
            ok=True,
            status_code=schema.status_code,
            raw_status_code=schema.raw_status_code,
            data={
                "doctype": doctype,
                "user": user,
                "roles": sorted(role_names),
                "enabled": user_data.get("enabled"),
                "permissions": effective,
                "matched_permission_rows": matched_rows,
            },
            debug={"raw_user": user_data, "raw_schema": schema_data},
        )

    def _users_preview_effective_permissions(self, args: dict[str, Any]) -> ToolResult:
        user = args["user"]
        doctype = args["doctype"]
        preview = self._users_build_metadata_permission_preview(user, doctype)
        if not preview.ok:
            return preview
        preview_data = preview.data
        user_permissions = None
        if args.get("include_user_permissions", True):
            permission_result = self.client.search_documents(
                "User Permission",
                filters={"user": user},
                fields=["name", "user", "allow", "for_value", "applicable_for", "is_default", "hide_descendants"],
                limit=100,
                order_by="modified desc",
            )
            if not permission_result.ok:
                return permission_result
            user_permissions = permission_result.data

        return ToolResult(
            ok=True,
            status_code=preview.status_code,
            raw_status_code=preview.raw_status_code,
            data={
                "doctype": doctype,
                "user": user,
                "status": "Preview",
                "summary": f"Previewed metadata-based effective permissions for {user} on {doctype}.",
                "roles": preview_data["roles"],
                "enabled": preview_data["enabled"],
                "permissions": preview_data["permissions"],
                "matched_permission_rows": preview_data["matched_permission_rows"],
                "user_permissions": user_permissions,
                "is_exact_runtime_evaluation": False,
                "next_actions": ["review_permissions", "use_agent_bridge_for_server_side_permission_check"],
                "risk": {"level": "L0", "admin_write_tools_require_confirmation": True},
            },
            debug=preview.debug,
        )

    def _users_check_server_permission(self, args: dict[str, Any]) -> ToolResult:
        user = args["user"]
        doctype = args["doctype"]
        action = (args["action"] or "read").strip().lower()
        if action not in USER_PERMISSION_ACTIONS:
            return ToolResult(
                ok=False,
                error=f"Unsupported permission action: {action}",
                error_type="validation_error",
                user_message="权限动作必须是 Frappe 支持的权限类型。",
                data={"supported_actions": list(USER_PERMISSION_ACTIONS)},
            )

        preview = self._users_build_metadata_permission_preview(user, doctype)
        if not preview.ok:
            return preview
        server = self.client.check_user_permission(
            user,
            doctype,
            action,
            docname=args.get("docname"),
            debug=args.get("debug", False),
        )
        if not server.ok:
            return server

        preview_data = preview.data if isinstance(preview.data, dict) else {}
        server_data = server.data if isinstance(server.data, dict) else {}
        metadata_allowed = bool((preview_data.get("permissions") or {}).get(action))
        server_allowed = bool(server_data.get("allowed"))
        difference = {
            "action": action,
            "metadata_preview_allowed": metadata_allowed,
            "server_runtime_allowed": server_allowed,
            "differs": metadata_allowed != server_allowed,
            "likely_reasons": _permission_difference_reasons(args.get("docname"), metadata_allowed, server_allowed),
        }

        return ToolResult(
            ok=True,
            status_code=server.status_code,
            raw_status_code=server.raw_status_code,
            data={
                "doctype": doctype,
                "docname": args.get("docname"),
                "user": user,
                "action": action,
                "status": "Checked",
                "summary": f"Checked server-side runtime permission for {user} to {action} {doctype}.",
                "allowed": server_allowed,
                "metadata_preview": {
                    "allowed": metadata_allowed,
                    "permissions": preview_data.get("permissions") or {},
                    "matched_permission_rows": preview_data.get("matched_permission_rows") or [],
                    "roles": preview_data.get("roles") or [],
                    "enabled": preview_data.get("enabled"),
                    "is_exact_runtime_evaluation": False,
                },
                "server_check": server_data,
                "differences": difference,
                "is_exact_runtime_evaluation": bool(server_data.get("is_exact_runtime_evaluation", True)),
                "next_actions": ["review_differences", "inspect_user_permissions_or_shares"],
                "risk": {"level": "L0", "requires_system_manager_in_agent_bridge": True},
            },
            debug={"metadata_preview": preview.debug, "raw_server_check": server_data},
        )

    def _users_preview_permission_policy_change(self, args: dict[str, Any]) -> ToolResult:
        changes = args.get("changes")
        if not isinstance(changes, list) or not changes:
            return ToolResult(
                ok=False,
                error="changes must be a non-empty list.",
                error_type="validation_error",
                user_message="权限策略预览需要至少一条 add、update 或 remove 变更。",
            )

        schema = self.client.get_doctype_schema(args["doctype"])
        if not schema.ok:
            return schema
        schema_data = schema.data if isinstance(schema.data, dict) else {}
        before_rows = [_permission_row_preview(row) for row in _extract_permission_rows(schema_data)]
        simulation = _simulate_permission_policy_changes(before_rows, changes)
        if isinstance(simulation, ToolResult):
            return simulation
        after_rows, diff, normalized_changes = simulation

        return ToolResult(
            ok=True,
            status_code=schema.status_code,
            raw_status_code=schema.raw_status_code,
            data={
                "doctype": args["doctype"],
                "status": "Permission Policy Preview",
                "summary": f"Previewed DocPerm-style policy changes for {args['doctype']} without writing ERPNext.",
                "before": before_rows,
                "after": after_rows,
                "diff": diff,
                "changes": normalized_changes,
                "requires_write_tool": "future_L5_ADMIN_docperm_change_tool",
                "next_actions": ["review_diff", "confirm_policy_owner_approval", "implement_dedicated_write_tool_if_needed"],
                "risk": {
                    "level": "L5_ADMIN",
                    "preview_only": True,
                    "writes_to_erpnext": False,
                    "changes_system_wide_permission_policy": True,
                },
            },
            debug={"raw_schema": schema_data},
        )

    def _users_create_user_draft(self, args: dict[str, Any]) -> ToolResult:
        data = {
            "email": args["email"],
            "first_name": args["first_name"],
            "last_name": args.get("last_name"),
            "enabled": 1 if args.get("enabled") is True else 0,
            "send_welcome_email": 1 if args.get("send_welcome_email") is True else 0,
            "user_type": args.get("user_type") or "System User",
            "role_profile_name": args.get("role_profile_name"),
        }
        roles = [{"role": role} for role in args.get("roles", [])]
        if roles:
            data["roles"] = roles
        data = _clean_mapping(data)
        guard = _require_admin_confirmation("create_user_draft", "User", args["email"], args.get("confirmation"), data)
        if guard:
            return guard
        result = self.client.create_document("User", data)
        return _users_write_result(result, "User", args["email"], "Created disabled user record for review.")

    def _users_set_user_enabled(self, args: dict[str, Any]) -> ToolResult:
        data = {"enabled": 1 if args["enabled"] else 0}
        action = "enable_user" if args["enabled"] else "disable_user"
        guard = _require_admin_confirmation(action, "User", args["user"], args.get("confirmation"), data)
        if guard:
            return guard
        result = self.client.update_document("User", args["user"], data)
        return _users_write_result(result, "User", args["user"], f"{'Enabled' if args['enabled'] else 'Disabled'} user.")

    def _users_assign_roles(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_admin_confirmation("assign_roles", "User", args["user"], args.get("confirmation"), {"mode": args["mode"], "roles": args["roles"]})
        if guard:
            return guard
        current = self.client.get_document("User", args["user"])
        if not current.ok:
            return current
        current_data = current.data if isinstance(current.data, dict) else {}
        existing = {
            row.get("role")
            for row in current_data.get("roles", [])
            if isinstance(row, dict) and row.get("role")
        }
        requested = set(args["roles"])
        if args["mode"] == "replace":
            next_roles = requested
        elif args["mode"] == "add":
            next_roles = existing | requested
        elif args["mode"] == "remove":
            next_roles = existing - requested
        else:
            return ToolResult(ok=False, error="Invalid role assignment mode.", error_type="validation_error", user_message="角色分配模式必须是 replace、add 或 remove。")
        result = self.client.update_document("User", args["user"], {"roles": [{"role": role} for role in sorted(next_roles)]})
        return _users_write_result(result, "User", args["user"], f"Updated roles for {args['user']}.")

    def _users_create_user_permission(self, args: dict[str, Any]) -> ToolResult:
        data = _clean_mapping(
            {
                "user": args["user"],
                "allow": args["allow"],
                "for_value": args["for_value"],
                "applicable_for": args.get("applicable_for"),
                "is_default": 1 if args.get("is_default") else 0,
                "hide_descendants": 1 if args.get("hide_descendants") else 0,
            }
        )
        guard = _require_admin_confirmation("create_user_permission", "User Permission", args["user"], args.get("confirmation"), data)
        if guard:
            return guard
        result = self.client.create_document("User Permission", data)
        return _users_write_result(result, "User Permission", data.get("for_value"), "Created user permission row.")

    def _users_delete_user_permission(self, args: dict[str, Any]) -> ToolResult:
        guard = _require_admin_confirmation("delete_user_permission", "User Permission", args["name"], args.get("confirmation"), {"name": args["name"]})
        if guard:
            return guard
        result = self.client.delete_document("User Permission", args["name"])
        return _users_write_result(result, "User Permission", args["name"], "Deleted user permission row.")
