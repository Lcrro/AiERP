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
    build_material_request_messages,
    plan_material_request_with_deepseek,
)

__all__ = [
    "DeepSeekSettings",
    "ToolAccessPolicy",
    "ToolContract",
    "ToolExposure",
    "ToolGateway",
    "ToolSession",
    "build_material_request_messages",
    "build_tool_contracts",
    "filter_tool_schemas_for_policy",
    "get_tool_contract",
    "make_tool_access_policy",
    "plan_material_request_with_deepseek",
]
