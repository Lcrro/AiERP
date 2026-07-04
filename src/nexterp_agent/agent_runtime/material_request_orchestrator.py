from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexterp_agent.item_master.release_resolver import ReleaseMaterialResolver

from .deepseek_material_request import MATERIAL_REQUEST_TOOL


@dataclass(frozen=True)
class MaterialRequestRuntimeConfig:
    company: str | None = None
    default_schedule_date: str | None = None
    project_candidates: tuple[dict[str, Any], ...] = ()
    warehouse_candidates: tuple[dict[str, Any], ...] = ()

    @classmethod
    def from_context(cls, context: dict[str, Any] | None) -> "MaterialRequestRuntimeConfig":
        context = context or {}
        return cls(
            company=context.get("company"),
            default_schedule_date=context.get("default_schedule_date"),
            project_candidates=tuple(_dict_candidates(context.get("project_candidates"))),
            warehouse_candidates=tuple(_dict_candidates(context.get("warehouse_candidates"))),
        )


def compose_material_request_tool_call(
    intent: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
    resolver: ReleaseMaterialResolver | None = None,
) -> dict[str, Any]:
    """Resolve a structured material request intent into a ToolCall candidate.

    The LLM is expected to produce the intent draft. This function owns all
    deterministic runtime work: resolving master data, copying ERPNext ids,
    enforcing positive quantities, and deciding whether the request is ready,
    needs candidate selection, or should enter item creation.
    """

    resolved_config = MaterialRequestRuntimeConfig.from_context(context)
    resolved_resolver = resolver or ReleaseMaterialResolver()
    issues: list[str] = []

    company = _first_non_empty(intent.get("company"), resolved_config.company)
    schedule_date = _first_non_empty(intent.get("schedule_date"), resolved_config.default_schedule_date)
    project = _single_candidate_value(resolved_config.project_candidates, ("name", "project"))
    warehouse = _single_candidate_value(resolved_config.warehouse_candidates, ("name", "warehouse"))

    if not company:
        issues.append("缺少公司。")
    if not schedule_date:
        issues.append("缺少需求日期。")
    if not project:
        issues.append("项目未解析到唯一候选。")
    if not warehouse:
        issues.append("仓库未解析到唯一候选。")

    raw_items = intent.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        issues.append("缺少物料明细。")
        raw_items = []

    resolved_items: list[dict[str, Any]] = []
    pending_resolutions: list[dict[str, Any]] = []
    item_creation_requests: list[dict[str, Any]] = []

    for index, raw_item in enumerate(raw_items, start=1):
        item_issue_prefix = f"第 {index} 行"
        if not isinstance(raw_item, dict):
            issues.append(f"{item_issue_prefix}物料明细不是对象。")
            continue

        qty = raw_item.get("qty")
        if not isinstance(qty, (int, float)) or qty <= 0:
            issues.append(f"{item_issue_prefix}数量必须是正数。")
            continue

        raw_item_text = str(raw_item.get("raw_item_text") or raw_item.get("item_text") or "").strip()
        if not raw_item_text:
            issues.append(f"{item_issue_prefix}缺少物料名称。")
            continue

        material_resolution = resolved_resolver.resolve(
            raw_item_text,
            specs=raw_item.get("specs") if isinstance(raw_item.get("specs"), dict) else None,
            limit=5,
        )

        if material_resolution["status"] == "ready":
            resolved = material_resolution["resolved"]
            resolved_items.append(
                {
                    "item_code": resolved["item_code"],
                    "qty": qty,
                    "uom": raw_item.get("uom") or resolved.get("stock_uom"),
                    "warehouse": warehouse,
                    "schedule_date": schedule_date,
                    "project": project,
                    "runtime_resolution": {
                        "raw_item_text": raw_item_text,
                        "sku_name": resolved.get("sku_name"),
                        "required_specs": resolved.get("required_specs"),
                        "decision_reason": material_resolution["decision_reason"],
                    },
                }
            )
        elif material_resolution["status"] == "not_found":
            item_creation_requests.append(
                {
                    "raw_item_text": raw_item_text,
                    "qty": qty,
                    "uom": raw_item.get("uom"),
                    "resolution": material_resolution,
                    "next_action": "start_item_creation_flow",
                }
            )
        else:
            pending_resolutions.append(
                {
                    "raw_item_text": raw_item_text,
                    "qty": qty,
                    "uom": raw_item.get("uom"),
                    "resolution": material_resolution,
                    "next_action": "present_candidates",
                }
            )

    if issues:
        return {
            "status": "needs_clarification",
            "questions": issues,
            "intent": intent,
            "resolved_items": resolved_items,
            "pending_resolutions": pending_resolutions,
            "item_creation_requests": item_creation_requests,
        }

    if item_creation_requests:
        return {
            "status": "needs_item_creation",
            "questions": ["有物料未在发布版物料表中找到，请先确认是否新建物料。"],
            "intent": intent,
            "resolved_items": resolved_items,
            "pending_resolutions": pending_resolutions,
            "item_creation_requests": item_creation_requests,
        }

    if pending_resolutions:
        return {
            "status": "needs_material_selection",
            "questions": ["有物料存在多个候选，请先选择标准物料。"],
            "intent": intent,
            "resolved_items": resolved_items,
            "pending_resolutions": pending_resolutions,
            "item_creation_requests": item_creation_requests,
        }

    tool_call = {
        "tool": MATERIAL_REQUEST_TOOL,
        "arguments": {
            "material_request_type": "Purchase",
            "company": company,
            "schedule_date": schedule_date,
            "items": [
                {
                    "item_code": item["item_code"],
                    "qty": item["qty"],
                    "uom": item["uom"],
                    "warehouse": item["warehouse"],
                    "schedule_date": item["schedule_date"],
                    "project": item["project"],
                }
                for item in resolved_items
            ],
        },
    }
    return {
        "status": "ready",
        "questions": [],
        "intent": intent,
        "tool_call": tool_call,
        "resolved_items": resolved_items,
        "pending_resolutions": [],
        "item_creation_requests": [],
    }


def _dict_candidates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [candidate for candidate in value if isinstance(candidate, dict)]


def _single_candidate_value(candidates: tuple[dict[str, Any], ...], keys: tuple[str, ...]) -> Any:
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    for key in keys:
        value = candidate.get(key)
        if value not in (None, ""):
            return value
    return None


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None
