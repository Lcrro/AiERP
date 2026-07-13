from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any


BIN_FIELDS = [
    "name",
    "item_code",
    "warehouse",
    "actual_qty",
    "projected_qty",
    "reserved_qty",
    "valuation_rate",
    "stock_value",
]


def enrich_item_entity_results(
    entity_results: list[dict[str, Any]],
    *,
    client: Any,
    preferred_warehouse: str | None = None,
    related_warehouses: list[str] | None = None,
) -> dict[str, Any]:
    """Attach one live Bin query to every material candidate in this action."""
    item_codes = _candidate_item_codes(entity_results)
    if not item_codes:
        return {"status": "skipped", "item_codes": [], "row_count": 0}

    filters: list[list[Any]] = [["item_code", "in", item_codes]]
    related_warehouses = list(dict.fromkeys(related_warehouses or []))
    if related_warehouses:
        filters.append(["warehouse", "in", related_warehouses])
    response = client.search_documents(
        "Bin",
        filters=filters,
        fields=BIN_FIELDS,
        limit=max(100, len(item_codes) * 50),
        order_by="actual_qty desc",
    )
    if not response.ok or not isinstance(response.data, list):
        error = response.user_message or response.error or "库存查询失败。"
        for entity in entity_results:
            if entity.get("kind") == "item":
                entity.setdefault("resolution", {})["inventory_query"] = {
                    "status": "failed",
                    "message": error,
                }
        return {"status": "failed", "item_codes": item_codes, "row_count": 0, "message": error}

    rows_by_item: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw_row in response.data:
        row = _normalize_bin_row(raw_row)
        if row["item_code"] in item_codes:
            rows_by_item[row["item_code"]].append(row)

    for entity in entity_results:
        if entity.get("kind") != "item":
            continue
        requested_qty = _as_number(entity.get("requested_qty"))
        resolution = entity.get("resolution") or {}
        candidates = resolution.get("candidates") or []
        for candidate in candidates:
            item_code = str(candidate.get("item_code") or "")
            inventory = deepcopy(rows_by_item.get(item_code, []))
            for warehouse in related_warehouses or ([preferred_warehouse] if preferred_warehouse else []):
                if warehouse and not any(row["warehouse"] == warehouse for row in inventory):
                    inventory.append(_empty_inventory_row(item_code, warehouse))
            inventory.sort(
                key=lambda row: (
                    row["warehouse"] != preferred_warehouse,
                    -row["usable_qty"],
                    row["warehouse"],
                )
            )
            candidate["inventory"] = inventory
            candidate["inventory_summary"] = _inventory_summary(
                inventory,
                requested_qty=requested_qty,
                requested_uom=entity.get("requested_uom"),
                stock_uom=candidate.get("stock_uom"),
                preferred_warehouse=preferred_warehouse,
            )

        resolved = resolution.get("resolved")
        if isinstance(resolved, dict):
            match = next(
                (candidate for candidate in candidates if candidate.get("item_code") == resolved.get("item_code")),
                None,
            )
            if match:
                resolution["resolved"] = deepcopy(match)
        resolution["inventory_query"] = {
            "status": "completed",
            "item_codes": [candidate.get("item_code") for candidate in candidates],
            "row_count": sum(len(candidate.get("inventory") or []) for candidate in candidates),
            "preferred_warehouse": preferred_warehouse,
            "related_warehouses": related_warehouses,
        }

    return {"status": "completed", "item_codes": item_codes, "row_count": len(response.data)}


def _candidate_item_codes(entity_results: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    for entity in entity_results:
        if entity.get("kind") != "item":
            continue
        resolution = entity.get("resolution") or {}
        for candidate in resolution.get("candidates") or []:
            code = str(candidate.get("item_code") or "").strip()
            if code and code not in codes:
                codes.append(code)
    return codes


def _normalize_bin_row(row: dict[str, Any]) -> dict[str, Any]:
    actual_qty = _as_number(row.get("actual_qty")) or 0.0
    reserved_qty = _as_number(row.get("reserved_qty")) or 0.0
    available_qty = actual_qty - reserved_qty
    return {
        "item_code": str(row.get("item_code") or ""),
        "warehouse": str(row.get("warehouse") or ""),
        "actual_qty": actual_qty,
        "reserved_qty": reserved_qty,
        "available_qty": available_qty,
        "usable_qty": max(0.0, available_qty),
        "projected_qty": _as_number(row.get("projected_qty")) or 0.0,
        "valuation_rate": _as_number(row.get("valuation_rate")) or 0.0,
        "stock_value": _as_number(row.get("stock_value")) or 0.0,
    }


def _empty_inventory_row(item_code: str, warehouse: str) -> dict[str, Any]:
    return {
        "item_code": item_code,
        "warehouse": warehouse,
        "actual_qty": 0.0,
        "reserved_qty": 0.0,
        "available_qty": 0.0,
        "usable_qty": 0.0,
        "projected_qty": 0.0,
        "valuation_rate": 0.0,
        "stock_value": 0.0,
    }


def _inventory_summary(
    inventory: list[dict[str, Any]],
    *,
    requested_qty: float | None,
    requested_uom: Any,
    stock_uom: Any,
    preferred_warehouse: str | None,
) -> dict[str, Any]:
    total_actual = sum(row["actual_qty"] for row in inventory)
    total_reserved = sum(row["reserved_qty"] for row in inventory)
    total_usable = sum(row["usable_qty"] for row in inventory)
    preferred_usable = sum(
        row["usable_qty"] for row in inventory if preferred_warehouse and row["warehouse"] == preferred_warehouse
    )
    comparable_uom = not requested_uom or not stock_uom or str(requested_uom) == str(stock_uom)
    shortage_qty = None
    if requested_qty is not None and comparable_uom:
        shortage_qty = max(0.0, requested_qty - total_usable)
    return {
        "total_actual_qty": total_actual,
        "total_reserved_qty": total_reserved,
        "total_available_qty": total_usable,
        "preferred_warehouse": preferred_warehouse,
        "preferred_warehouse_available_qty": preferred_usable,
        "requested_qty": requested_qty,
        "requested_uom": requested_uom,
        "stock_uom": stock_uom,
        "shortage_qty": shortage_qty,
        "uom_comparable": comparable_uom,
    }


def _as_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
