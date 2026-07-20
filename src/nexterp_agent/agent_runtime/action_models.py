from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiscoverToolsArguments(_StrictModel):
    query: str = Field(min_length=1)
    modules: list[str] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=8)


class DiscoverCapabilitiesArguments(_StrictModel):
    query: str = Field(min_length=1)
    modules: list[str] = Field(default_factory=list)
    limit: int = Field(default=5, ge=1, le=5)


class GetToolContractsArguments(_StrictModel):
    tool_names: list[str] = Field(min_length=1, max_length=5)


class GetCapabilityGuideArguments(_StrictModel):
    capability_ids: list[str] = Field(min_length=1, max_length=3)


class ResolveEntitiesArguments(_StrictModel):
    entities: list[dict[str, Any]] = Field(min_length=1, max_length=20)


class ProposeBusinessActionArguments(_StrictModel):
    capability_id: str = Field(min_length=1)
    business_intent: dict[str, Any]


class ExecuteToolArguments(_StrictModel):
    tool_call: dict[str, Any]


class AskUserArguments(_StrictModel):
    message: str | None = None
    questions: list[str] = Field(min_length=1)
    candidates: list[Any] = Field(default_factory=list)


class FinishArguments(_StrictModel):
    message: str = Field(min_length=1)


class _ActionBase(_StrictModel):
    summary: str = Field(min_length=1)


class DiscoverToolsAction(_ActionBase):
    action: Literal["discover_tools"]
    arguments: DiscoverToolsArguments


class DiscoverCapabilitiesAction(_ActionBase):
    action: Literal["discover_capabilities"]
    arguments: DiscoverCapabilitiesArguments


class GetToolContractsAction(_ActionBase):
    action: Literal["get_tool_contracts"]
    arguments: GetToolContractsArguments


class GetCapabilityGuideAction(_ActionBase):
    action: Literal["get_capability_guide"]
    arguments: GetCapabilityGuideArguments


class ResolveEntitiesAction(_ActionBase):
    action: Literal["resolve_entities"]
    arguments: ResolveEntitiesArguments


class ProposeBusinessAction(_ActionBase):
    action: Literal["propose_business_action"]
    arguments: ProposeBusinessActionArguments


class ExecuteToolAction(_ActionBase):
    action: Literal["execute_tool"]
    arguments: ExecuteToolArguments


class AskUserAction(_ActionBase):
    action: Literal["ask_user"]
    arguments: AskUserArguments


class FinishAction(_ActionBase):
    action: Literal["finish"]
    arguments: FinishArguments


AgentAction = Annotated[
    Union[
        DiscoverToolsAction,
        DiscoverCapabilitiesAction,
        GetToolContractsAction,
        GetCapabilityGuideAction,
        ResolveEntitiesAction,
        ProposeBusinessAction,
        ExecuteToolAction,
        AskUserAction,
        FinishAction,
    ],
    Field(discriminator="action"),
]

AGENT_ACTION_ADAPTER = TypeAdapter(AgentAction)


def validate_action(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    action = str(normalized.get("action") or "")
    if not str(normalized.get("summary") or "").strip():
        normalized["summary"] = f"DeepSeek请求执行{action}"
    normalized.setdefault("arguments", {})
    return AGENT_ACTION_ADAPTER.validate_python(normalized).model_dump(exclude_none=True)

