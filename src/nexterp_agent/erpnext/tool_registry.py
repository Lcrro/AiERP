from __future__ import annotations

from .tool_schemas.accounting import ACCOUNTING_TOOL_SCHEMAS
from .tool_schemas.assets import ASSETS_TOOL_SCHEMAS
from .tool_schemas.buying import BUYING_TOOL_SCHEMAS
from .tool_schemas.common import (
    BUYING_ITEM_LINE_SCHEMA,
    CONFIRMATION_SCHEMA,
    PICK_LIST_LOCATION_SCHEMA,
    STOCK_ENTRY_ITEM_SCHEMA,
    STOCK_PREVIEW_ITEM_SCHEMA,
    STOCK_RECONCILIATION_ITEM_SCHEMA,
    _object_schema,
)
from .tool_schemas.generic import GENERIC_AGENT_TOOL_SCHEMAS, GENERIC_CORE_TOOL_SCHEMAS, GENERIC_TOOL_SCHEMAS
from .tool_schemas.projects import PROJECTS_TOOL_SCHEMAS
from .tool_schemas.stock import STOCK_TOOL_SCHEMAS
from .tool_schemas.users import USERS_TOOL_SCHEMAS

ERPNext_TOOL_SCHEMAS = (
    GENERIC_CORE_TOOL_SCHEMAS
    + USERS_TOOL_SCHEMAS
    + ACCOUNTING_TOOL_SCHEMAS
    + ASSETS_TOOL_SCHEMAS
    + STOCK_TOOL_SCHEMAS
    + PROJECTS_TOOL_SCHEMAS
    + GENERIC_AGENT_TOOL_SCHEMAS
    + BUYING_TOOL_SCHEMAS
)
