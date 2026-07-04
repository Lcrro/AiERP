from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv

from .tool_contracts import get_tool_contract


MATERIAL_REQUEST_TOOL = "erpnext.buying.create_material_request_draft"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"


@dataclass(frozen=True)
class DeepSeekSettings:
    api_key: str
    base_url: str = DEFAULT_DEEPSEEK_BASE_URL
    model: str = DEFAULT_DEEPSEEK_MODEL
    timeout_seconds: int = 60


def load_deepseek_settings() -> DeepSeekSettings:
    load_dotenv()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key or api_key == "replace-me":
        raise RuntimeError("Missing DeepSeek configuration: DEEPSEEK_API_KEY")

    return DeepSeekSettings(
        api_key=api_key,
        base_url=os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL,
        model=os.getenv("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL,
        timeout_seconds=int(os.getenv("DEEPSEEK_TIMEOUT_SECONDS") or "60"),
    )


def build_material_request_messages(user_text: str, *, context: dict[str, Any] | None = None) -> list[dict[str, str]]:
    contract = get_tool_contract(MATERIAL_REQUEST_TOOL)
    params = {
        param.name: {
            "type": param.json_type,
            "required": param.required,
            "source": param.source,
            "resolver": param.resolver,
            "enum_values": list(param.enum_values),
            "constraints": list(param.constraints),
            "repair": list(param.repair),
            "description": param.description,
        }
        for param in contract.parameters
    }
    runtime_context = context or {}

    system_prompt = {
        "role": "system",
        "content": (
            "你是 ERPNext 材料申请 ToolCall 编排器，只负责把用户自然语言整理成候选 ToolCall。"
            "你不能执行工具，不能假装已经创建单据，不能编造 ERPNext 主键。"
            "如果物料、仓库、项目、日期或数量缺失或不确定，返回 needs_clarification 并提出最少必要问题。"
            "如果信息足够，返回 needs_confirmation，并生成 erpnext.buying.create_material_request_draft 的候选参数。"
            "数量必须是数字；日期必须是 YYYY-MM-DD；items 必须是数组。"
            "如果 runtime_context.default_schedule_date 已提供，必须用它作为需求日期，不要再追问今天日期。"
            "item_code、warehouse、project 只能使用上下文中已经解析出的标准值；没有标准值时不要凭空造。"
            "只输出一个 JSON object，不要 Markdown，不要解释性正文。"
        ),
    }
    developer_prompt = {
        "role": "system",
        "content": json.dumps(
            {
                "output_schema": {
                    "status": "needs_clarification | needs_confirmation",
                    "questions": ["string"],
                    "tool_call": {
                        "tool": MATERIAL_REQUEST_TOOL,
                        "arguments": {
                            "material_request_type": "Purchase",
                            "company": "ERPNext company name",
                            "schedule_date": "YYYY-MM-DD",
                            "items": [
                                {
                                    "item_code": "resolved Item.name",
                                    "qty": 1,
                                    "uom": "resolved UOM",
                                    "warehouse": "resolved Warehouse.name",
                                    "schedule_date": "YYYY-MM-DD",
                                    "project": "resolved Project.name",
                                }
                            ],
                        },
                    },
                    "candidate_summary": "string",
                    "assumptions": ["string"],
                    "confidence": 0.0,
                },
                "tool_contract": {
                    "name": contract.name,
                    "confirm": contract.confirm,
                    "allowed_roles": list(contract.allowed_roles),
                    "business_contract": list(contract.business_contract),
                    "parameters": params,
                },
                "runtime_context": runtime_context,
            },
            ensure_ascii=False,
        ),
    }
    user_prompt = {"role": "user", "content": user_text}
    return [system_prompt, developer_prompt, user_prompt]


def build_material_request_intent_messages(
    user_text: str,
    *,
    context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    runtime_context = context or {}
    system_prompt = {
        "role": "system",
        "content": (
            "你是 ERPNext 材料申请的业务意图抽取器，只负责把员工自然语言抽成结构化草稿。"
            "你不能选择 item_code，不能编造仓库、项目、物料编码或 ERPNext 单号。"
            "物料只填写 raw_item_text、数量、单位和用户明确说出的规格。"
            "如果日期可以根据 runtime_context.current_date 或 default_schedule_date 明确推断，输出 YYYY-MM-DD；否则保留 schedule_text 并提出问题。"
            "只输出 JSON object，不要 Markdown，不要解释正文。"
        ),
    }
    developer_prompt = {
        "role": "system",
        "content": json.dumps(
            {
                "output_schema": {
                    "intent": "create_material_request | unknown",
                    "project_text": "用户口头项目名或空",
                    "warehouse_text": "用户口头仓库名或空",
                    "schedule_text": "用户口头需求日期或空",
                    "schedule_date": "YYYY-MM-DD 或空",
                    "items": [
                        {
                            "raw_item_text": "用户说的物料名称，不要改成编码",
                            "qty": 1,
                            "uom": "用户说的单位或空",
                            "specs": {"规格字段": "用户明确说出的规格值"},
                        }
                    ],
                    "questions": ["缺失关键业务信息时要问的问题"],
                    "confidence": 0.0,
                },
                "runtime_context": runtime_context,
            },
            ensure_ascii=False,
        ),
    }
    return [system_prompt, developer_prompt, {"role": "user", "content": user_text}]


def call_deepseek_json(
    messages: list[dict[str, str]],
    *,
    settings: DeepSeekSettings | None = None,
) -> dict[str, Any]:
    resolved_settings = settings or load_deepseek_settings()
    endpoint = resolved_settings.base_url.rstrip("/") + "/chat/completions"
    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {resolved_settings.api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": resolved_settings.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "stream": False,
        },
        timeout=resolved_settings.timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    return parse_json_object(content)


def plan_material_request_with_deepseek(
    user_text: str,
    *,
    context: dict[str, Any] | None = None,
    settings: DeepSeekSettings | None = None,
) -> dict[str, Any]:
    messages = build_material_request_messages(user_text, context=context)
    plan = call_deepseek_json(messages, settings=settings)
    plan = normalize_material_request_plan(plan, context=context)
    return validate_material_request_plan(plan)


def extract_material_request_intent_with_deepseek(
    user_text: str,
    *,
    context: dict[str, Any] | None = None,
    settings: DeepSeekSettings | None = None,
) -> dict[str, Any]:
    messages = build_material_request_intent_messages(user_text, context=context)
    intent = call_deepseek_json(messages, settings=settings)
    return validate_material_request_intent(intent)


def parse_json_object(content: str) -> dict[str, Any]:
    cleaned = content.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("DeepSeek response must be a JSON object")
    return data


def normalize_material_request_plan(
    plan: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply deterministic Runtime context after the model proposes a ToolCall.

    DeepSeek is allowed to interpret intent, but resolved ERPNext identifiers and
    relative dates must come from the Runtime. When the context contains a single
    resolved candidate, it is treated as authoritative and copied into the
    proposed ToolCall.
    """

    if plan.get("status") != "needs_confirmation" or not context:
        return plan

    normalized = deepcopy(plan)
    tool_call = normalized.get("tool_call")
    if not isinstance(tool_call, dict):
        return normalized
    arguments = tool_call.get("arguments")
    if not isinstance(arguments, dict):
        return normalized
    items = arguments.get("items")
    if not isinstance(items, list):
        return normalized

    corrections = normalized.setdefault("runtime_corrections", [])

    def set_field(container: dict[str, Any], field: str, value: Any, reason: str) -> None:
        if value in (None, ""):
            return
        old_value = container.get(field)
        if old_value == value:
            return
        container[field] = value
        corrections.append({"field": field, "from": old_value, "to": value, "reason": reason})

    set_field(arguments, "company", context.get("company"), "company resolved by Runtime context")

    schedule_date = context.get("default_schedule_date")
    set_field(arguments, "schedule_date", schedule_date, "schedule_date resolved by Runtime date policy")

    project = _single_candidate_value(context.get("project_candidates"), ("name", "project"))
    warehouse = _single_candidate_value(context.get("warehouse_candidates"), ("name", "warehouse"))
    item_candidate = _single_candidate(context.get("item_candidates"))
    item_code = _candidate_value(item_candidate, ("item_code", "name")) if item_candidate else None
    item_uom = _candidate_value(item_candidate, ("stock_uom", "uom")) if item_candidate else None

    for item in items:
        if not isinstance(item, dict):
            continue
        set_field(item, "item_code", item_code, "item_code resolved by Item resolver")
        set_field(item, "uom", item_uom, "uom resolved from Item stock_uom")
        set_field(item, "warehouse", warehouse, "warehouse resolved by Warehouse resolver")
        set_field(item, "project", project, "project resolved by Project resolver")
        set_field(item, "schedule_date", schedule_date, "item schedule_date resolved by Runtime date policy")

    if corrections:
        assumptions = normalized.setdefault("assumptions", [])
        if isinstance(assumptions, list):
            assumptions.append("Runtime 已用解析上下文覆盖模型输出中的主数据和日期字段。")

    return normalized


def validate_material_request_plan(plan: dict[str, Any]) -> dict[str, Any]:
    status = plan.get("status")
    if status not in {"needs_clarification", "needs_confirmation"}:
        raise ValueError("DeepSeek plan status must be needs_clarification or needs_confirmation")

    if status == "needs_clarification":
        questions = plan.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ValueError("needs_clarification response must include non-empty questions")
        return plan

    tool_call = plan.get("tool_call")
    if not isinstance(tool_call, dict):
        raise ValueError("needs_confirmation response must include tool_call")
    if tool_call.get("tool") != MATERIAL_REQUEST_TOOL:
        raise ValueError(f"DeepSeek may only propose {MATERIAL_REQUEST_TOOL}")

    arguments = tool_call.get("arguments")
    if not isinstance(arguments, dict):
        raise ValueError("tool_call.arguments must be an object")
    if not arguments.get("company"):
        raise ValueError("material request arguments must include company")
    if not arguments.get("schedule_date"):
        raise ValueError("material request arguments must include schedule_date")
    items = arguments.get("items")
    if not isinstance(items, list) or not items:
        raise ValueError("material request arguments must include non-empty items")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"items[{index}] must be an object")
        qty = item.get("qty")
        if not isinstance(qty, (int, float)) or qty <= 0:
            raise ValueError(f"items[{index}].qty must be a positive number")
        if not item.get("item_code"):
            raise ValueError(f"items[{index}].item_code is required")
        if not item.get("warehouse"):
            raise ValueError(f"items[{index}].warehouse is required")
        if not item.get("schedule_date"):
            raise ValueError(f"items[{index}].schedule_date is required")

    return plan


def validate_material_request_intent(intent: dict[str, Any]) -> dict[str, Any]:
    status = intent.get("intent")
    if status not in {"create_material_request", "unknown"}:
        raise ValueError("material request intent must be create_material_request or unknown")
    items = intent.get("items")
    if status == "create_material_request":
        if not isinstance(items, list) or not items:
            raise ValueError("create_material_request intent must include non-empty items")
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise ValueError(f"items[{index}] must be an object")
            if not item.get("raw_item_text"):
                raise ValueError(f"items[{index}].raw_item_text is required")
            qty = item.get("qty")
            if qty is not None and (not isinstance(qty, (int, float)) or qty <= 0):
                raise ValueError(f"items[{index}].qty must be a positive number when provided")
            specs = item.get("specs")
            if specs is not None and not isinstance(specs, dict):
                raise ValueError(f"items[{index}].specs must be an object when provided")
    return intent


def _single_candidate(candidates: Any) -> dict[str, Any] | None:
    if not isinstance(candidates, list) or len(candidates) != 1:
        return None
    candidate = candidates[0]
    return candidate if isinstance(candidate, dict) else None


def _single_candidate_value(candidates: Any, keys: tuple[str, ...]) -> Any:
    candidate = _single_candidate(candidates)
    if not candidate:
        return None
    return _candidate_value(candidate, keys)


def _candidate_value(candidate: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = candidate.get(key)
        if value not in (None, ""):
            return value
    return None
