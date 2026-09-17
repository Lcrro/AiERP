"""Compile the reviewed GPC workbench into a sparse ERPNext material release.

The reference-catalog database remains the taxonomy authority.  ERPNext only
receives operational Item Groups, UOMs and approved SKU projections, with
stable links back to the catalog revision and source material record.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable, Mapping

from .reference_catalog_database import DEFAULT_REFERENCE_CATALOG_DATABASE_PATH


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ITEM_CODE_MAP_PATH = (
    ROOT / ".runtime" / "erpnext-material-test" / "material-item-code-map.json"
)
DEFAULT_RELEASE_ROOT = ROOT / ".runtime" / "erpnext-material-test" / "releases"

ERP_ROOT_ITEM_GROUP = "Nexterp经营物料"
WHOLE_NUMBER_UOMS = {"把", "支", "件", "双", "包", "块", "袋", "个", "只", "套", "具", "张", "片"}

ITEM_CUSTOM_FIELDS: tuple[dict[str, Any], ...] = (
    {
        "fieldname": "custom_nexterp_source_id",
        "label": "Nexterp源物料ID",
        "fieldtype": "Data",
        "unique": 1,
        "read_only": 1,
    },
    {
        "fieldname": "custom_nexterp_standard_type_code",
        "label": "Nexterp标准类型编码",
        "fieldtype": "Data",
        "read_only": 1,
    },
    {
        "fieldname": "custom_nexterp_gpc_brick_code",
        "label": "GPC Brick编码",
        "fieldtype": "Data",
        "read_only": 1,
    },
    {
        "fieldname": "custom_nexterp_classification_path",
        "label": "Nexterp分类路径",
        "fieldtype": "Small Text",
        "read_only": 1,
    },
    {
        "fieldname": "custom_nexterp_catalog_revision",
        "label": "Nexterp目录Revision",
        "fieldtype": "Int",
        "read_only": 1,
    },
    {
        "fieldname": "custom_nexterp_source_hash",
        "label": "Nexterp源数据哈希",
        "fieldtype": "Data",
        "read_only": 1,
    },
    {
        "fieldname": "custom_nexterp_attributes_json",
        "label": "Nexterp采购属性",
        "fieldtype": "Long Text",
        "read_only": 1,
    },
    {
        "fieldname": "custom_nexterp_classification_source",
        "label": "Nexterp分类来源",
        "fieldtype": "Data",
        "read_only": 1,
    },
)


class MaterialReleaseError(RuntimeError):
    """Raised when the reviewed catalog cannot produce a safe ERPNext release."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_code_map(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping = payload.get("material_item_codes") if isinstance(payload, dict) else None
    if not isinstance(mapping, dict):
        raise MaterialReleaseError(f"Invalid item-code map: {path}")
    return {_text(key): _text(value) for key, value in mapping.items() if _text(key) and _text(value)}


def _allocate_item_codes(
    materials: Iterable[Mapping[str, Any]],
    existing: Mapping[str, str],
) -> dict[str, str]:
    result = dict(existing)
    used_codes: dict[str, str] = {}
    for source_id, item_code in result.items():
        if item_code in used_codes and used_codes[item_code] != source_id:
            raise MaterialReleaseError(f"Duplicate mapped item code: {item_code}")
        used_codes[item_code] = source_id

    grouped: dict[str, list[str]] = {}
    for material in materials:
        source_id = _text(material["source_id"])
        type_code = _text(material["standard_type_code"])
        if source_id in result:
            continue
        grouped.setdefault(type_code, []).append(source_id)

    for type_code, source_ids in sorted(grouped.items()):
        suffix_pattern = re.compile(rf"^{re.escape(type_code)}(\d{{3}})$")
        used_suffixes = {
            int(match.group(1))
            for code in used_codes
            if (match := suffix_pattern.fullmatch(code)) is not None
        }
        next_suffix = max(used_suffixes, default=0) + 1
        for source_id in sorted(source_ids):
            while next_suffix in used_suffixes:
                next_suffix += 1
            if next_suffix > 999:
                raise MaterialReleaseError(f"Standard type {type_code} exceeds 999 active SKU codes")
            item_code = f"{type_code}{next_suffix:03d}"
            if item_code in used_codes:
                raise MaterialReleaseError(f"Generated duplicate item code: {item_code}")
            result[source_id] = item_code
            used_codes[item_code] = source_id
            used_suffixes.add(next_suffix)
            next_suffix += 1
    return result


def _node_path(nodes: Mapping[str, Mapping[str, Any]], code: str) -> list[Mapping[str, Any]]:
    path: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    current = code
    while current:
        if current in seen:
            raise MaterialReleaseError(f"Cycle detected in catalog path at {current}")
        seen.add(current)
        node = nodes.get(current)
        if node is None:
            raise MaterialReleaseError(f"Missing catalog node {current}")
        path.append(node)
        current = _text(node.get("parent_code"))
    path.reverse()
    return path


def _description(payload: Mapping[str, Any]) -> str:
    parts = [f"标准类型：{_text(payload.get('standard_type'))}"]
    attributes = payload.get("procurement_attributes") or {}
    price_drivers = payload.get("price_drivers") or {}
    if attributes:
        parts.append("采购属性：" + "；".join(f"{key}={value}" for key, value in attributes.items()))
    if price_drivers:
        parts.append("价格/质量要点：" + "；".join(f"{key}={value}" for key, value in price_drivers.items()))
    return "\n".join(parts)


def build_material_release(
    database_path: Path = DEFAULT_REFERENCE_CATALOG_DATABASE_PATH,
    *,
    code_map_path: Path = DEFAULT_ITEM_CODE_MAP_PATH,
) -> dict[str, Any]:
    """Build and validate one immutable release from the active GPC catalog."""

    database_path = Path(database_path).resolve()
    if not database_path.is_file():
        raise MaterialReleaseError(f"Reference-catalog database does not exist: {database_path}")

    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        state = connection.execute(
            "SELECT source_version, revision, schema_version FROM catalog_state WHERE catalog = 'gpc'"
        ).fetchone()
        if state is None:
            raise MaterialReleaseError("GPC catalog state is missing")
        node_rows = connection.execute(
            "SELECT code, parent_code, kind, level, working_name, official_name, is_gpc "
            "FROM catalog_nodes WHERE catalog = 'gpc'"
        ).fetchall()
        placement_rows = connection.execute(
            "SELECT material_id, node_code, payload_json FROM material_placements "
            "WHERE catalog = 'gpc' ORDER BY material_id"
        ).fetchall()
    finally:
        connection.close()

    nodes = {row["code"]: dict(row) for row in node_rows}
    raw_materials: list[dict[str, Any]] = []
    errors: list[str] = []
    for row in placement_rows:
        payload = json.loads(row["payload_json"])
        source_id = _text(payload.get("material_id") or row["material_id"])
        material_name = _text(payload.get("material_name"))
        stock_uom = _text(payload.get("stock_uom"))
        standard_type = _text(payload.get("standard_type"))
        node_code = _text(row["node_code"])
        completeness = _text(payload.get("completeness_status"))
        missing = [
            name
            for name, value in {
                "source_id": source_id,
                "material_name": material_name,
                "stock_uom": stock_uom,
                "standard_type": standard_type,
                "node_code": node_code,
            }.items()
            if not value
        ]
        if missing:
            errors.append(f"{source_id or row['material_id']}: missing {', '.join(missing)}")
            continue
        if completeness != "完整":
            errors.append(f"{source_id}: completeness_status is {completeness or '<blank>'}")
            continue
        path = _node_path(nodes, node_code)
        type_node = path[-1]
        if type_node["kind"] != "internal_type":
            errors.append(f"{source_id}: target node {node_code} is not a standard type")
            continue
        segment = next((node for node in path if node["kind"] == "segment"), None)
        brick = next((node for node in path if node["kind"] == "brick"), None)
        if segment is None:
            errors.append(f"{source_id}: path lacks a GPC segment")
            continue
        classification_path = " / ".join(
            f"{node['code']} {_text(node['working_name'])}" for node in path
        )
        raw_materials.append(
            {
                "source_id": source_id,
                "item_name": material_name,
                "stock_uom": stock_uom,
                "standard_type": standard_type,
                "standard_type_code": node_code,
                "gpc_brick_code": _text(brick["code"]) if brick else "",
                "classification_source": "gpc" if brick else "nexterp_internal",
                "segment_code": _text(segment["code"]),
                "segment_name": _text(segment["working_name"]),
                "classification_path": classification_path,
                "procurement_attributes": payload.get("procurement_attributes") or {},
                "price_drivers": payload.get("price_drivers") or {},
                "description": _description(payload),
            }
        )

    if errors:
        preview = "; ".join(errors[:10])
        raise MaterialReleaseError(f"Catalog release validation failed ({len(errors)}): {preview}")
    if not raw_materials:
        raise MaterialReleaseError("Catalog contains no approved actual materials")

    source_ids = [item["source_id"] for item in raw_materials]
    if len(source_ids) != len(set(source_ids)):
        raise MaterialReleaseError("Duplicate source material IDs found")

    existing_map = _read_code_map(Path(code_map_path))
    item_code_map = _allocate_item_codes(raw_materials, existing_map)
    revision = int(state["revision"])

    items: list[dict[str, Any]] = []
    for raw in raw_materials:
        attributes_json = _canonical_json(
            {
                "procurement_attributes": raw["procurement_attributes"],
                "price_drivers": raw["price_drivers"],
            }
        )
        item = {
            "source_id": raw["source_id"],
            "item_code": item_code_map[raw["source_id"]],
            "item_name": raw["item_name"],
            "item_group": f"{raw['segment_code']} {raw['segment_name']}",
            "stock_uom": raw["stock_uom"],
            "description": raw["description"],
            "standard_type": raw["standard_type"],
            "standard_type_code": raw["standard_type_code"],
            "gpc_brick_code": raw["gpc_brick_code"],
            "classification_source": raw["classification_source"],
            "classification_path": raw["classification_path"],
            "catalog_revision": revision,
            "attributes_json": attributes_json,
        }
        item["source_hash"] = _hash(item)
        items.append(item)

    item_codes = [item["item_code"] for item in items]
    if len(item_codes) != len(set(item_codes)):
        raise MaterialReleaseError("Duplicate ERPNext item codes found")

    segments = sorted({(item["segment_code"], item["segment_name"]) for item in raw_materials})
    item_groups = [
        {
            "item_group_name": ERP_ROOT_ITEM_GROUP,
            "parent_item_group": "All Item Groups",
            "is_group": 1,
        }
    ] + [
        {
            "item_group_name": f"{code} {name}",
            "parent_item_group": ERP_ROOT_ITEM_GROUP,
            "is_group": 0,
        }
        for code, name in segments
    ]
    uoms = [
        {"uom_name": name, "must_be_whole_number": int(name in WHOLE_NUMBER_UOMS)}
        for name in sorted({item["stock_uom"] for item in items})
    ]

    release_body = {
        "catalog": "gpc",
        "catalog_source_version": _text(state["source_version"]),
        "catalog_schema_version": int(state["schema_version"]),
        "catalog_revision": revision,
        "item_groups": item_groups,
        "uoms": uoms,
        "items": sorted(items, key=lambda item: item["item_code"]),
    }
    release_hash = _hash(release_body)
    return {
        **release_body,
        "release_hash": release_hash,
        "generated_at": _now(),
        "counts": {
            "item_groups": len(item_groups),
            "uoms": len(uoms),
            "items": len(items),
            "standard_types": len({item["standard_type_code"] for item in items}),
        },
        "item_code_map": item_code_map,
    }


def write_material_release(
    release: Mapping[str, Any],
    *,
    release_root: Path = DEFAULT_RELEASE_ROOT,
    code_map_path: Path = DEFAULT_ITEM_CODE_MAP_PATH,
) -> Path:
    """Persist runtime-only release artifacts and the stable source-to-SKU map."""

    release_dir = Path(release_root) / f"gpc-r{release['catalog_revision']}-{release['release_hash'][:12]}"
    release_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        key: release[key]
        for key in (
            "catalog",
            "catalog_source_version",
            "catalog_schema_version",
            "catalog_revision",
            "release_hash",
            "generated_at",
            "counts",
        )
    }
    (release_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for filename, key in (
        ("item-groups.jsonl", "item_groups"),
        ("uoms.jsonl", "uoms"),
        ("items.jsonl", "items"),
    ):
        lines = "".join(_canonical_json(row) + "\n" for row in release[key])
        (release_dir / filename).write_text(lines, encoding="utf-8")

    code_map_path = Path(code_map_path)
    code_map_path.parent.mkdir(parents=True, exist_ok=True)
    code_map_payload = {
        "schema_version": 1,
        "updated_at": _now(),
        "material_item_codes": dict(sorted(release["item_code_map"].items())),
    }
    code_map_path.write_text(
        json.dumps(code_map_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return release_dir
