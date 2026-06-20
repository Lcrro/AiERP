from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any

from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.schemas import ToolCall, ToolResult

from .tool_access import ToolAccessPolicy


@dataclass(frozen=True)
class ToolSession:
    user: str | None
    policy: ToolAccessPolicy
    verify_erpnext_identity: bool = False


class ToolGateway:
    """Execute ToolCalls only after profile and identity checks.

    The adapter is deliberately lower-level and still knows how to run every
    registered tool. Employee-facing Agent Runtime code should enter here.
    """

    def __init__(self, adapter: ERPNextAdapter, session: ToolSession) -> None:
        self.adapter = adapter
        self.session = session
        self._verified_erpnext_user: str | None = None

    def execute(self, tool_call: ToolCall | dict[str, Any], *, origin: str = "agent") -> ToolResult:
        started = perf_counter()
        call = ToolCall.from_dict(tool_call) if isinstance(tool_call, dict) else tool_call

        decision = self.session.policy.decide(call.tool, origin=origin)
        if not decision.allowed:
            return self._finish(
                call,
                started,
                ToolResult(
                    ok=False,
                    error=f"Tool {call.tool} is not allowed for profile {self.session.policy.profile_name}: {decision.reason}",
                    error_type="permission_error",
                    user_message=f"当前岗位不能使用这个工具：{call.tool}",
                    meta={
                        "profile": self.session.policy.profile_name,
                        "reason": decision.reason,
                        "exposure": decision.exposure.value,
                        "origin": origin,
                    },
                ),
            )

        identity_error = self._verify_identity(call, started)
        if identity_error:
            return identity_error

        return self.adapter.execute(call)

    def _verify_identity(self, call: ToolCall, started: float) -> ToolResult | None:
        expected_user = self.session.user
        if not self.session.verify_erpnext_identity or not expected_user:
            return None
        if self._verified_erpnext_user == expected_user:
            return None

        result = self.adapter.client.get_logged_user()
        if not result.ok:
            return self._finish(
                call,
                started,
                ToolResult(
                    ok=False,
                    error=result.error or "Unable to verify ERPNext API identity",
                    error_type=result.error_type or "permission_error",
                    user_message="无法确认当前 ToolCall 使用的是员工本人的 ERPNext 身份。",
                    debug=result.debug,
                    meta={
                        "profile": self.session.policy.profile_name,
                        "expected_user": expected_user,
                    },
                ),
            )

        actual_user = _extract_logged_user(result.data)
        if actual_user != expected_user:
            return self._finish(
                call,
                started,
                ToolResult(
                    ok=False,
                    error=f"ERPNext identity mismatch: expected {expected_user}, got {actual_user}",
                    error_type="permission_error",
                    user_message="当前 ToolCall 使用的 ERPNext 身份与员工登录身份不一致，已拒绝执行。",
                    meta={
                        "profile": self.session.policy.profile_name,
                        "expected_user": expected_user,
                        "actual_user": actual_user,
                    },
                ),
            )

        self._verified_erpnext_user = actual_user
        return None

    def _finish(self, call: ToolCall, started: float, result: ToolResult) -> ToolResult:
        return result.with_call(call, duration_ms=int((perf_counter() - started) * 1000))


def _extract_logged_user(data: Any) -> str | None:
    if isinstance(data, str):
        return data
    if isinstance(data, dict):
        for key in ("message", "user", "email", "name"):
            value = data.get(key)
            if isinstance(value, str):
                return value
    return None
