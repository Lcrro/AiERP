from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable


@dataclass(frozen=True)
class CatalogEvaluation:
    status: str
    slots: list[dict[str, Any]]
    missing: list[str]
    invalid: list[str]
    blocked: list[str]
    rules: list[dict[str, Any]]
    tool_call: dict[str, Any] | None


Compiler = Callable[[dict[str, Any], dict[str, Any]], CatalogEvaluation]


class OperationCompilerRegistry:
    """Dispatch deterministic compilers by stable keys stored in the catalog."""

    def __init__(self) -> None:
        self._compilers: dict[str, Compiler] = {
            "material_request.create.v1": compile_material_request,
        }

    def compile(self, bundle: dict[str, Any], facts: dict[str, Any]) -> CatalogEvaluation:
        key = str(bundle.get("operation", {}).get("compiler_key") or "")
        compiler = self._compilers.get(key)
        if compiler is None:
            raise ValueError(f"Unsupported operation compiler: {key or '<missing>'}")
        return compiler(bundle, facts)


def compile_material_request(bundle: dict[str, Any], facts: dict[str, Any]) -> CatalogEvaluation:
    """Compile one material request only from catalog bindings and resolved facts."""

    operation = dict(bundle.get("operation") or {})
    tool_name = str(operation.get("tool_name") or "")
    if tool_name != "erpnext.buying.create_material_request_draft":
        raise ValueError("Material request compiler is bound to an unexpected ToolCall")

    slots = sorted((dict(row) for row in bundle.get("slots") or []), key=lambda row: int(row.get("position") or 0))
    if not slots:
        raise ValueError("Operation catalog does not define any field slots")

    items = [dict(item) for item in facts.get("items") or [] if isinstance(item, dict)]
    values: dict[str, Any] = {}
    evaluations: list[dict[str, Any]] = []
    missing: list[str] = []
    invalid: list[str] = []
    blocked: list[str] = []

    for slot in slots:
        slot_id = str(slot["slot_id"])
        scope = str(slot.get("scope") or "document")
        source = str(slot.get("source") or "")
        if source == "fixed":
            value = slot.get("fixed_value")
        elif source == "derived":
            value = values.get(str(slot.get("derived_from") or ""))
            if scope == "item" and not isinstance(value, list):
                value = [value for _ in items]
        else:
            value = _source_value(facts, str(slot.get("source_path") or ""))
        values[slot_id] = value

        status, reason = _validate_slot(slot, value, len(items))
        if status == "missing":
            missing.append(slot_id)
        elif status == "invalid":
            invalid.append(slot_id)
        elif status == "blocked":
            blocked.append(slot_id)
        evaluations.append({
            **slot,
            "status": status,
            "value": None if scope == "item" else value,
            "values": value if scope == "item" and isinstance(value, list) else [],
            "reason": reason,
        })

    tool_call = None
    if not missing and not invalid and not blocked:
        arguments: dict[str, Any] = {"items": [{} for _ in items]}
        for slot in slots:
            target = str(slot.get("target_path") or "")
            if not target.startswith("arguments."):
                continue
            value = values[str(slot["slot_id"])]
            _assign_argument(arguments, target.removeprefix("arguments."), value)
        tool_call = {"tool": tool_name, "arguments": arguments}

    return CatalogEvaluation(
        status="ready" if tool_call else "needs_input",
        slots=evaluations,
        missing=missing,
        invalid=invalid,
        blocked=blocked,
        rules=[dict(row) for row in bundle.get("rules") or []],
        tool_call=tool_call,
    )


def _source_value(facts: dict[str, Any], path: str) -> Any:
    if not path:
        return None
    if "[]" in path:
        collection_name, child_path = path.split("[]", 1)
        collection = facts.get(collection_name.rstrip(".")) or []
        child_path = child_path.lstrip(".")
        return [_nested_value(dict(row), child_path) for row in collection if isinstance(row, dict)]
    return _nested_value(facts, path)


def _nested_value(payload: dict[str, Any], path: str) -> Any:
    current: Any = payload
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _validate_slot(slot: dict[str, Any], value: Any, item_count: int) -> tuple[str, str]:
    slot_id = str(slot["slot_id"])
    scope = str(slot.get("scope") or "document")
    required = bool(slot.get("required", True))
    if scope == "item":
        sequence = value if isinstance(value, list) else []
        if item_count == 0 or len(sequence) != item_count or (required and any(item in (None, "") for item in sequence)):
            if str(slot.get("source") or "") == "derived":
                return "blocked", f"等待上游字段 {slot.get('derived_from') or ''}。"
            return "missing", "每个物料明细都必须提供该字段。"
        if slot_id == "slot.quantity" and any(not _positive_number(item) for item in sequence):
            return "invalid", "数量必须是大于 0 的数字。"
    elif required and value in (None, ""):
        return "missing", "该操作缺少必填字段。"
    if slot_id == "slot.need_by_date" and value not in (None, "") and not _iso_date(value):
        return "invalid", "日期必须使用 YYYY-MM-DD。"
    return "resolved", "字段已由目录声明的确定来源提供。"


def _assign_argument(arguments: dict[str, Any], path: str, value: Any) -> None:
    if path.startswith("items[]."):
        field = path.removeprefix("items[].")
        values = value if isinstance(value, list) else []
        if len(values) != len(arguments["items"]):
            raise ValueError(f"Item binding {path} does not match item count")
        for index, item_value in enumerate(values):
            arguments["items"][index][field] = item_value
        return
    target = arguments
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = value


def _positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _iso_date(value: Any) -> bool:
    try:
        date.fromisoformat(str(value))
        return True
    except (TypeError, ValueError):
        return False
