"""Natural-language agent runtime boundaries.

This package will hold intent routing, session state, planning, tool selection,
and response generation. It must not call ERPNext/Frappe HTTP APIs directly;
all ERP execution goes through the ERPNext adapter.
"""

from .tool_access import ToolAccessPolicy, ToolExposure, filter_tool_schemas_for_policy, make_tool_access_policy
from .tool_contracts import ToolContract, build_tool_contracts, get_tool_contract
from .tool_gateway import ToolGateway, ToolSession
from .deepseek_material_request import (
    DeepSeekSettings,
    build_material_request_intent_messages,
    build_material_request_messages,
    extract_material_request_intent_with_deepseek,
    plan_material_request_with_deepseek,
)
from .deepseek_civil_intent import build_civil_intent_messages, extract_civil_intent_with_deepseek
from .material_request_orchestrator import MaterialRequestRuntimeConfig, compose_material_request_tool_call
from .civil_runtime import CivilAgentRuntime, LegacyCivilAgentRuntime, RuntimeTurnResult
from .deepseek_agent_runtime import DeepSeekAgentRuntime, DeepSeekTurnResult
from .resolvers import EntityResolverRegistry, ResolutionResult
from .session import RuntimeSessionState, RuntimeSessionStore

__all__ = [
    "DeepSeekSettings",
    "CivilAgentRuntime",
    "DeepSeekAgentRuntime",
    "DeepSeekTurnResult",
    "LegacyCivilAgentRuntime",
    "EntityResolverRegistry",
    "MaterialRequestRuntimeConfig",
    "ToolAccessPolicy",
    "ToolContract",
    "ToolExposure",
    "ToolGateway",
    "ToolSession",
    "ResolutionResult",
    "RuntimeSessionState",
    "RuntimeSessionStore",
    "RuntimeTurnResult",
    "build_material_request_intent_messages",
    "build_civil_intent_messages",
    "build_material_request_messages",
    "build_tool_contracts",
    "compose_material_request_tool_call",
    "extract_material_request_intent_with_deepseek",
    "extract_civil_intent_with_deepseek",
    "filter_tool_schemas_for_policy",
    "get_tool_contract",
    "make_tool_access_policy",
    "plan_material_request_with_deepseek",
]
