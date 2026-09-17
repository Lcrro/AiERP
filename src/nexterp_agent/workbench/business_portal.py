"""Deterministic business-portal primitives.

The business portal deliberately does not know about DeepSeek, OpenClaw, or
low-level ToolCall arguments.  It only stores short-lived, server-owned
preview commands before an explicit confirmation is executed by the existing
WorkbenchService methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any
from uuid import uuid4


BUSINESS_ACTIONS = frozenset(
    {
        "material_request.create_draft",
        "material_request.update_draft",
        "document.submit",
        "workflow.action",
        "rfq.create",
        "quotation.create",
        "purchase_order.create",
        "purchase_receipt.create",
        "purchase_discrepancy.create",
        "purchase_return.create",
        "stock.project_issue.create",
        "stock.project_return.create",
        "stock.transfer.create",
        "stock.reconciliation.create",
    }
)


@dataclass
class BusinessCommand:
    command_id: str
    action: str
    user: str
    project: str
    payload: dict[str, Any]
    summary: dict[str, Any]
    account_code: str = ""
    created_at: float = field(default_factory=time.time)
    expires_at: float = field(default_factory=lambda: time.time() + 600)
    status: str = "pending"
    result: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "action": self.action,
            "project": self.project,
            "account_code": self.account_code,
            "summary": self.summary,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status,
            "result": self.result,
        }


class BusinessCommandStore:
    """Thread-safe in-memory preview store for one workbench process."""

    def __init__(self, *, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = max(60, int(ttl_seconds))
        self._lock = threading.Lock()
        self._commands: dict[str, BusinessCommand] = {}
        self._request_results: dict[tuple[str, str], dict[str, Any]] = {}

    def _purge(self) -> None:
        now = time.time()
        for command_id, command in list(self._commands.items()):
            if command.expires_at < now and command.status == "pending":
                command.status = "expired"
            if command.expires_at + self.ttl_seconds < now:
                self._commands.pop(command_id, None)

    def create(
        self,
        *,
        action: str,
        user: str,
        project: str,
        payload: dict[str, Any],
        summary: dict[str, Any],
        account_code: str = "",
    ) -> BusinessCommand:
        if action not in BUSINESS_ACTIONS:
            raise ValueError(f"unsupported business action: {action}")
        if not user:
            raise ValueError("business identity is required")
        with self._lock:
            self._purge()
            command = BusinessCommand(
                command_id=f"cmd_{uuid4().hex}",
                action=action,
                user=user,
                project=project,
                account_code=account_code,
                payload=dict(payload),
                summary=dict(summary),
                expires_at=time.time() + self.ttl_seconds,
            )
            self._commands[command.command_id] = command
            return command

    def get(self, command_id: str, *, user: str, account_code: str = "") -> BusinessCommand:
        with self._lock:
            self._purge()
            command = self._commands.get(command_id)
            if command is None or command.user != user or (account_code and command.account_code != account_code):
                raise ValueError("business command not found")
            return command

    def remember_request(self, request_id: str, result: dict[str, Any], *, account_code: str = "") -> None:
        if not request_id:
            return
        with self._lock:
            self._purge()
            self._request_results[(account_code, request_id)] = dict(result)

    def request_result(self, request_id: str, *, account_code: str = "") -> dict[str, Any] | None:
        if not request_id:
            return None
        with self._lock:
            self._purge()
            result = self._request_results.get((account_code, request_id))
            return dict(result) if result else None
