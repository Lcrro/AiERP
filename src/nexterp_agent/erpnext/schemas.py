from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ToolCall:
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: f"toolcall_{uuid4().hex}")
    created_at: str = field(default_factory=_now_iso)
    reason: str | None = None
    risk_level: str = "L0"
    user_context: dict[str, Any] = field(default_factory=dict)
    validation_error: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ToolCall":
        return cls(
            tool=payload["tool"],
            arguments=payload.get("arguments") or {},
            id=payload.get("id") or f"toolcall_{uuid4().hex}",
            created_at=payload.get("created_at") or _now_iso(),
            reason=payload.get("reason"),
            risk_level=payload.get("risk_level") or infer_risk_level_for_call(payload),
            user_context=payload.get("user_context") or {},
            validation_error=payload.get("validation_error"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "created_at": self.created_at,
            "tool": self.tool,
            "arguments": self.arguments,
            "risk_level": self.risk_level,
            "user_context": self.user_context,
        }
        if self.reason:
            payload["reason"] = self.reason
        if self.validation_error:
            payload["validation_error"] = self.validation_error
        return payload


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: Any = None
    status_code: int | None = None
    raw_status_code: int | None = None
    error: str | None = None
    error_type: str | None = None
    user_message: str | None = None
    tool_call_id: str | None = None
    duration_ms: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    debug: dict[str, Any] = field(default_factory=dict)

    def with_call(self, call: ToolCall, duration_ms: int | None = None) -> "ToolResult":
        return replace(
            self,
            tool_call_id=call.id,
            duration_ms=duration_ms if duration_ms is not None else self.duration_ms,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "ok": self.ok,
            "data": self.data,
        }
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.duration_ms is not None:
            payload["duration_ms"] = self.duration_ms
        if self.status_code is not None:
            payload["status_code"] = self.status_code
        if self.raw_status_code is not None:
            payload["raw_status_code"] = self.raw_status_code
        if self.error:
            payload["error"] = self.error
        if self.error_type:
            payload["error_type"] = self.error_type
        if self.user_message:
            payload["user_message"] = self.user_message
        if self.meta:
            payload["meta"] = self.meta
        if self.debug:
            payload["debug"] = self.debug
        return payload


from .risk_policy import infer_risk_level, infer_risk_level_for_call
