from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.erpnext import ERPNextAdapter, ERPNextClient
from nexterp_agent.erpnext.config import load_erpnext_settings


def build_adapter(profile: str) -> ERPNextAdapter:
    settings = load_erpnext_settings(profile)
    client = ERPNextClient(
        settings.base_url,
        settings.api_key,
        settings.api_secret,
        host_header=settings.host_header,
    )
    return ERPNextAdapter(client)


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test ERPNext API access.")
    parser.add_argument("--profile", default="remote", help="remote, local, or custom env profile")
    parser.add_argument(
        "--check",
        choices=[
            "auth",
            "customer",
            "doctype",
            "bridge",
            "count",
            "todo-write",
            "attachment",
            "report",
            "remote-readonly",
        ],
        default="auth",
    )
    parser.add_argument("--report-name", default="Addresses And Contacts")
    args = parser.parse_args()

    try:
        adapter = build_adapter(args.profile)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.check == "auth":
        result = adapter.execute({"tool": "erpnext.get_logged_user"})
    elif args.check == "customer":
        result = adapter.execute(
            {
                "tool": "erpnext.search_documents",
                "arguments": {
                    "doctype": "Customer",
                    "fields": ["name", "customer_name"],
                    "limit": 1,
                },
            }
        )
    elif args.check == "doctype":
        result = adapter.execute(
            {
                "tool": "erpnext.get_doctype_schema",
                "arguments": {"doctype": "Customer"},
            }
        )
    elif args.check == "bridge":
        result = adapter.execute(
            {
                "tool": "erpnext.call_method",
                "arguments": {"method": "agent_bridge.api.ping"},
            }
        )
    elif args.check == "count":
        result = adapter.execute({"tool": "erpnext.count_documents", "arguments": {"doctype": "Customer"}})
    elif args.check == "todo-write":
        result = smoke_todo_write(adapter)
    elif args.check == "attachment":
        result = smoke_attachment(adapter)
    elif args.check == "report":
        result = adapter.execute(
            {
                "tool": "erpnext.run_report",
                "arguments": {"report_name": args.report_name, "filters": {}},
            }
        )
    else:
        result = smoke_remote_readonly(adapter)

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def smoke_todo_write(adapter: ERPNextAdapter):
    created = adapter.execute(
        {
            "tool": "erpnext.create_todo",
            "arguments": {
                "description": "Nexterp Agent smoke test ToDo",
                "priority": "Low",
            },
        }
    )
    if not created.ok:
        return created

    name = created.data.get("name") if isinstance(created.data, dict) else None
    if not name:
        return created

    updated = adapter.execute(
        {
            "tool": "erpnext.update_document",
            "arguments": {
                "doctype": "ToDo",
                "name": name,
                "data": {"description": "Nexterp Agent smoke test ToDo updated"},
            },
        }
    )
    fetched = adapter.execute({"tool": "erpnext.get_document", "arguments": {"doctype": "ToDo", "name": name}})
    counted = adapter.execute({"tool": "erpnext.count_documents", "arguments": {"doctype": "ToDo"}})
    deleted = adapter.execute({"tool": "erpnext.delete_document", "arguments": {"doctype": "ToDo", "name": name}})

    ok = all(result.ok for result in [updated, fetched, counted, deleted])
    return created.__class__(
        ok=ok,
        data={
            "created": created.to_dict(),
            "updated": updated.to_dict(),
            "fetched": fetched.to_dict(),
            "counted": counted.to_dict(),
            "deleted": deleted.to_dict(),
        },
        error=None if ok else "ToDo write smoke failed",
        error_type=None if ok else "validation_error",
        user_message=None if ok else "ToDo 写入冒烟测试失败。",
    )


def smoke_attachment(adapter: ERPNextAdapter):
    todo = adapter.execute(
        {
            "tool": "erpnext.create_todo",
            "arguments": {
                "description": "Nexterp Agent attachment smoke test",
                "priority": "Low",
            },
        }
    )
    if not todo.ok:
        return todo
    name = todo.data.get("name") if isinstance(todo.data, dict) else None
    if not name:
        return todo

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as handle:
        handle.write("Nexterp Agent attachment smoke test")
        path = handle.name

    attached = adapter.execute(
        {
            "tool": "erpnext.attach_file",
            "arguments": {"doctype": "ToDo", "name": name, "file_path": path},
        }
    )
    listed = adapter.execute({"tool": "erpnext.list_attachments", "arguments": {"doctype": "ToDo", "name": name}})
    file_name = None
    if attached.ok and isinstance(attached.data, dict):
        file_name = attached.data.get("name")
    deleted_file = (
        adapter.execute({"tool": "erpnext.delete_attachment", "arguments": {"file_name": file_name}})
        if file_name
        else attached
    )
    deleted_todo = adapter.execute({"tool": "erpnext.delete_document", "arguments": {"doctype": "ToDo", "name": name}})
    ok = all(result.ok for result in [attached, listed, deleted_file, deleted_todo])
    return todo.__class__(
        ok=ok,
        data={
            "todo": todo.to_dict(),
            "attached": attached.to_dict(),
            "listed": listed.to_dict(),
            "deleted_file": deleted_file.to_dict(),
            "deleted_todo": deleted_todo.to_dict(),
        },
        error=None if ok else "Attachment smoke failed",
        error_type=None if ok else "validation_error",
        user_message=None if ok else "附件冒烟测试失败。",
    )


def smoke_remote_readonly(adapter: ERPNextAdapter):
    checks = {
        "auth": adapter.execute({"tool": "erpnext.get_logged_user"}),
        "customer": adapter.execute(
            {
                "tool": "erpnext.search_documents",
                "arguments": {"doctype": "Customer", "fields": ["name", "customer_name"], "limit": 1},
            }
        ),
        "doctype": adapter.execute(
            {"tool": "erpnext.get_doctype_schema", "arguments": {"doctype": "Customer"}}
        ),
    }
    ok = all(result.ok for result in checks.values())
    return next(iter(checks.values())).__class__(
        ok=ok,
        data={name: result.to_dict() for name, result in checks.items()},
        error=None if ok else "Remote readonly smoke failed",
        error_type=None if ok else "validation_error",
        user_message=None if ok else "远程只读冒烟测试失败。",
    )


if __name__ == "__main__":
    raise SystemExit(main())
