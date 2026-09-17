from __future__ import annotations

import json
from pathlib import Path
import sqlite3

import pytest

from nexterp_agent.item_master.erpnext_material_release import (
    MaterialReleaseError,
    build_material_release,
    write_material_release,
)


def _database(path: Path, *, completeness: str = "完整") -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE catalog_state (
            catalog TEXT PRIMARY KEY,
            schema_version INTEGER NOT NULL,
            source_version TEXT NOT NULL,
            revision INTEGER NOT NULL
        );
        CREATE TABLE catalog_nodes (
            catalog TEXT NOT NULL,
            code TEXT NOT NULL,
            parent_code TEXT,
            kind TEXT NOT NULL,
            level INTEGER NOT NULL,
            working_name TEXT NOT NULL,
            official_name TEXT NOT NULL,
            is_gpc INTEGER NOT NULL
        );
        CREATE TABLE material_placements (
            material_id TEXT NOT NULL,
            catalog TEXT NOT NULL,
            node_code TEXT NOT NULL,
            payload_json TEXT NOT NULL
        );
        """
    )
    connection.execute("INSERT INTO catalog_state VALUES ('gpc', 1, '2026-05', 7)")
    nodes = [
        ("11000000", None, "segment", 0, "工业用品", "Industrial Supplies", 1),
        ("11010000", "11000000", "family", 1, "紧固件族", "Fasteners", 1),
        ("11010100", "11010000", "class", 2, "紧固件类", "Fasteners", 1),
        ("10000001", "11010100", "brick", 3, "螺栓/螺纹杆", "Bolts/Threaded Rods", 1),
        ("1000000101", "10000001", "internal_type", 4, "六角螺栓", "", 0),
    ]
    connection.executemany(
        "INSERT INTO catalog_nodes VALUES ('gpc', ?, ?, ?, ?, ?, ?, ?)", nodes
    )
    payload = {
        "material_id": "SRC-B",
        "material_name": "六角螺栓｜M10×50 mm｜碳钢｜4.8级",
        "stock_uom": "套",
        "standard_type": "六角螺栓",
        "completeness_status": completeness,
        "procurement_attributes": {"规格": "M10×50 mm"},
        "price_drivers": {"性能等级": "4.8级"},
    }
    connection.execute(
        "INSERT INTO material_placements VALUES (?, 'gpc', ?, ?)",
        ("SRC-B", "1000000101", json.dumps(payload, ensure_ascii=False)),
    )
    connection.commit()
    connection.close()


def test_build_release_uses_sparse_segment_groups_and_stable_numeric_sku(tmp_path: Path) -> None:
    database = tmp_path / "catalog.sqlite3"
    code_map = tmp_path / "item-code-map.json"
    _database(database)

    release = build_material_release(database, code_map_path=code_map)
    assert release["counts"] == {
        "item_groups": 2,
        "uoms": 1,
        "items": 1,
        "standard_types": 1,
    }
    assert release["item_groups"][1]["item_group_name"] == "11000000 工业用品"
    item = release["items"][0]
    assert item["item_code"] == "1000000101001"
    assert item["gpc_brick_code"] == "10000001"
    assert item["classification_source"] == "gpc"
    assert item["standard_type_code"] == "1000000101"
    assert item["stock_uom"] == "套"
    assert item["source_hash"]

    release_dir = write_material_release(
        release,
        release_root=tmp_path / "releases",
        code_map_path=code_map,
    )
    assert (release_dir / "manifest.json").is_file()
    assert (release_dir / "items.jsonl").is_file()

    connection = sqlite3.connect(database)
    payload = {
        "material_id": "SRC-A",
        "material_name": "六角螺栓｜M8×30 mm｜碳钢｜4.8级",
        "stock_uom": "套",
        "standard_type": "六角螺栓",
        "completeness_status": "完整",
        "procurement_attributes": {"规格": "M8×30 mm"},
        "price_drivers": {"性能等级": "4.8级"},
    }
    connection.execute(
        "INSERT INTO material_placements VALUES (?, 'gpc', ?, ?)",
        ("SRC-A", "1000000101", json.dumps(payload, ensure_ascii=False)),
    )
    connection.commit()
    connection.close()

    second = build_material_release(database, code_map_path=code_map)
    by_source = {item["source_id"]: item["item_code"] for item in second["items"]}
    assert by_source == {"SRC-B": "1000000101001", "SRC-A": "1000000101002"}


def test_build_release_rejects_incomplete_material(tmp_path: Path) -> None:
    database = tmp_path / "catalog.sqlite3"
    _database(database, completeness="待确认")
    with pytest.raises(MaterialReleaseError, match="completeness_status"):
        build_material_release(database, code_map_path=tmp_path / "codes.json")
