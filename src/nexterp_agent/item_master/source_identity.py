"""Stable provenance keys for material discovery and publication data.

Source row numbers are only meaningful inside a particular dataset/document/
sheet.  This module keeps that boundary explicit and adds a deterministic hash
of the source row contents when the producer has the original row available.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import hashlib
import json
from collections.abc import Mapping
from typing import Any


DEFAULT_SOURCE_DATASET = "material_purchase_2024"
DEFAULT_SOURCE_DOCUMENT = "actual_material_purchase_list"
DEFAULT_SOURCE_SHEET = "实际采购清单"


def _value(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return ""


def _as_mapping(row: Any) -> Mapping[str, Any]:
    if isinstance(row, Mapping):
        return row
    if is_dataclass(row):
        return asdict(row)
    return {"value": str(row or "")}


def source_row_payload(row: Any) -> dict[str, Any]:
    """Return the stable business fields used to fingerprint a source row."""

    values = _as_mapping(row)
    return {
        "purchase_date": str(_value(values, "purchase_date", "日期")),
        "raw_name": str(_value(values, "raw_name", "材料")),
        "qty": _value(values, "qty", "quantity", "数量"),
        "raw_uom": str(_value(values, "raw_uom", "uom", "单位")),
        "procedure_sequence": str(_value(values, "procedure_sequence", "工序序号")),
        "market_unit_price": _value(values, "market_unit_price", "unit_price", "市场单价"),
    }


def source_row_hash(row: Any) -> str:
    payload = json.dumps(
        source_row_payload(row), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_source_record(
    source_row: int,
    *,
    row: Any | None = None,
    dataset: str = DEFAULT_SOURCE_DATASET,
    document: str = DEFAULT_SOURCE_DOCUMENT,
    sheet: str = DEFAULT_SOURCE_SHEET,
    row_hash: str = "",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source_dataset": str(dataset or "").strip(),
        "source_document": str(document or "").strip(),
        "source_sheet": str(sheet or "").strip(),
        "source_row": int(source_row),
    }
    fingerprint = str(row_hash or "").strip() or (source_row_hash(row) if row is not None else "")
    if fingerprint:
        record["source_row_hash"] = fingerprint
    return record


def source_record_key(record: Mapping[str, Any]) -> tuple[str, str, str, int]:
    """Return the identity key; hashes are checked separately when present."""

    return (
        str(record.get("source_dataset") or "").strip(),
        str(record.get("source_document") or "").strip(),
        str(record.get("source_sheet") or "").strip(),
        int(record.get("source_row") or 0),
    )


def source_record_matches(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Match complete identities and reject conflicting row fingerprints."""

    try:
        left_key = source_record_key(left)
        right_key = source_record_key(right)
    except (TypeError, ValueError):
        return False
    if not all(key[:3] and key[3] > 0 for key in (left_key, right_key)):
        return False
    if left_key != right_key:
        return False
    left_hash = str(left.get("source_row_hash") or "").strip()
    right_hash = str(right.get("source_row_hash") or "").strip()
    return not left_hash or not right_hash or left_hash == right_hash


def normalize_source_records(value: Any) -> list[dict[str, Any]]:
    """Keep only complete, well-formed source records from a JSON payload."""

    if not isinstance(value, list):
        return []
    records: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        try:
            record = make_source_record(
                int(raw.get("source_row") or 0),
                dataset=str(raw.get("source_dataset") or ""),
                document=str(raw.get("source_document") or ""),
                sheet=str(raw.get("source_sheet") or ""),
                row_hash=str(raw.get("source_row_hash") or ""),
            )
        except (TypeError, ValueError):
            continue
        if record["source_row"] <= 0 or not all(record[key] for key in ("source_dataset", "source_document", "source_sheet")):
            continue
        records.append(record)
    return records
