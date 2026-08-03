from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TrustLevel = Literal["authoritative", "trusted_master_data", "session", "advisory"]
IntentMode = Literal["read", "analyze", "write"]
ContextTopic = Literal[
    "responsibilities",
    "collaboration",
    "project",
    "recent_documents",
    "inbox",
    "process_position",
]


class ContextModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContextFact(ContextModel):
    value: Any
    source: str
    trust: TrustLevel


class AgentIdentityContext(ContextModel):
    employee_code: str
    employee_name: str
    employee_user: str
    role_code: str
    position: str
    project_position: str
    department_code: str
    department_name: str
    profile_name: str


class AgentWorkplaceContext(ContextModel):
    project_code: str
    project_name: str
    project_short_name: str
    project_status: str
    warehouse_code: str
    warehouse_name: str
    allowed_projects: list[str]


class AgentTaskContext(ContextModel):
    current_goal: str = ""
    intent_mode: IntentMode = "read"
    confirmed_entities: dict[str, Any] = Field(default_factory=dict)
    unresolved_fields: list[str] = Field(default_factory=list)
    active_capability: str | None = None
    loaded_context: list[str] = Field(default_factory=list)
    recent_documents: list[dict[str, Any]] = Field(default_factory=list)
    pending_operation: str | None = None
    last_successful_progress: str | None = None


class AgentContextEnvelope(ContextModel):
    identity: AgentIdentityContext
    workplace: AgentWorkplaceContext
    task: AgentTaskContext
    current_date: date
    available_context_topics: list[ContextTopic]
    provenance: dict[str, ContextFact]


class WorkContextLoadRequest(ContextModel):
    topics: list[ContextTopic] = Field(min_length=1, max_length=3)
    query: str | None = Field(default=None, max_length=300)
