from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestIdentity(StrictModel):
    external_subject: str = Field(min_length=1, max_length=240)
    agent_id: str = Field(default="", max_length=180)
    session_key: str = Field(min_length=1, max_length=240)


class CapabilitySearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=500)
    module: str | None = Field(default=None, max_length=60)
    intent_mode: Literal["read", "analyze", "write"] | None = None
    limit: int = Field(default=5, ge=1, le=5)


class GuideLoadRequest(StrictModel):
    node_ids: list[str] = Field(min_length=1, max_length=3)


class PrepareItem(StrictModel):
    raw_item_text: str | None = Field(default=None, max_length=300)
    item_code: str | None = Field(default=None, max_length=180)
    source_row: str | None = Field(default=None, max_length=180)
    qty: float | None = Field(default=None, gt=0)
    uom: str | None = Field(default=None, max_length=80)
    rate: float | None = Field(default=None, ge=0)
    warehouse: str | None = Field(default=None, max_length=240)
    project: str | None = Field(default=None, max_length=240)
    schedule_date: str | None = Field(default=None, max_length=40)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("raw_item_text", "item_code", "source_row", "uom", "warehouse", "project", "schedule_date", "reason")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        value = str(value or "").strip()
        return value or None


class PrepareDocumentReference(StrictModel):
    doctype: str = Field(min_length=1, max_length=140)
    name: str = Field(min_length=1, max_length=180)


class PrepareOperationRequest(StrictModel):
    operation_id: str = Field(pattern=r"^op\.[a-z0-9_.]+$")
    request_id: str = Field(min_length=1, max_length=180)
    project: str | None = Field(default=None, max_length=240)
    warehouse: str | None = Field(default=None, max_length=240)
    schedule_date: str | None = Field(default=None, max_length=40)
    schedule_text: str | None = Field(default=None, max_length=120)
    posting_date: str | None = Field(default=None, max_length=40)
    valid_till: str | None = Field(default=None, max_length=40)
    currency: str | None = Field(default=None, max_length=20)
    message: str | None = Field(default=None, max_length=4000)
    supplier: str | None = Field(default=None, max_length=240)
    suppliers: list[str] = Field(default_factory=list, max_length=50)
    source_documents: list[PrepareDocumentReference] = Field(default_factory=list, max_length=20)
    items: list[PrepareItem] = Field(default_factory=list, max_length=100)
    full_return: bool = False
    query: str | None = Field(default=None, max_length=500)
    item_codes: list[str] = Field(default_factory=list, max_length=50)
    document_type: str | None = Field(default=None, max_length=140)
    document_name: str | None = Field(default=None, max_length=180)
    limit: int = Field(default=10, ge=1, le=50)
class ExecuteOperationRequest(StrictModel):
    pending_id: str = Field(min_length=1, max_length=80)


class CapabilityNodeCard(StrictModel):
    node_id: str
    node_type: str
    module: str
    label: str
    summary: str
    is_write: bool
    score: int = 0


class PreparedOperationState(StrictModel):
    pending_id: str
    operation_id: str
    status: str
    summary: dict[str, Any]
    expires_at: datetime
    result: dict[str, Any] | None = None


PrepareStatus = Literal["needs_input", "needs_choice", "blocked", "needs_confirmation"]
