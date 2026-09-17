from __future__ import annotations

import json
from pathlib import Path
import sqlite3

from nexterp_agent.item_master.reference_catalog_database import ReferenceCatalogDatabase


ROOT = Path(__file__).resolve().parents[3]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _runtime_fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    runtime_root = tmp_path / "gpc"
    version_root = runtime_root / "2026-05"
    version_root.mkdir(parents=True)
    nodes = [
        {"code": "91000000", "kind": "segment", "level": 0, "official_name": "Safety", "parent_code": None},
        {"code": "91030000", "kind": "family", "level": 1, "official_name": "Business Safety", "parent_code": "91000000"},
        {"code": "91030300", "kind": "class", "level": 2, "official_name": "Fire Extinguishers", "parent_code": "91030000"},
        {"code": "10005410", "kind": "brick", "level": 3, "official_name": "Fire Extinguisher Variety Packs", "parent_code": "91030300"},
    ]
    _write_jsonl(version_root / "nodes.jsonl", nodes)
    _write_jsonl(
        version_root / "brick-profiles.jsonl",
        [{
            "code": "10005410",
            "kind": "brick",
            "official_name": "Fire Extinguisher Variety Packs",
            "definition": "A pack of fire extinguishers.",
            "includes": "Includes more than one extinguisher.",
            "excludes": "Excludes empty cabinets.",
            "attributes": [{
                "code": "20000001",
                "name": "Pack Type",
                "definition": "Type of pack.",
                "values": [{"code": "30000001", "name": "COMBINATION", "definition": "Mixed pack."}],
            }],
        }],
    )
    _write_jsonl(
        version_root / "translations.zh-CN.jsonl",
        [
            {"code": row["code"], "working_name": f"中文-{row['code']}", "status": "machine"}
            for row in nodes
        ],
    )
    _write_jsonl(version_root / "profile-translations.zh-CN.jsonl", [])
    _write_jsonl(version_root / "profile-text-translations.zh-CN.jsonl", [])
    (version_root / "manifest.json").write_text(
        json.dumps({
            "catalog": "gpc",
            "version": "2026-05",
            "source": "GS1 GPC",
            "hierarchy_complete": True,
            "attribute_count": 1,
            "attribute_value_count": 1,
        }),
        encoding="utf-8",
    )
    extensions_path = tmp_path / "extensions.json"
    extensions_path.write_text(
        json.dumps({
            "schema_version": 1,
            "extensions": [{
                "code": "9103030001",
                "parent_code": "91030300",
                "kind": "internal_brick",
                "level": 3,
                "working_name": "灭火器附属设备",
            }, {
                "code": "910303000101",
                "parent_code": "9103030001",
                "kind": "internal_family",
                "level": 4,
                "working_name": "灭火器箱体",
            }, {
                "code": "91030300010101",
                "parent_code": "910303000101",
                "kind": "internal_type",
                "level": 5,
                "working_name": "灭火器箱",
                "definition_working": "单独采购的空箱体。",
                "includes_working": "包括壁挂式箱体。",
                "excludes_working": "不包括灭火器。",
                "attributes": [{
                    "code": "9103030001010101",
                    "name": "适配配置",
                    "working_name": "适配配置",
                    "definition": "适配数量和容量。",
                    "values": [{
                        "code": "910303000101010101",
                        "name": "2×2 kg",
                        "working_name": "2×2 kg",
                        "definition": "两具 2 kg 手提式灭火器。",
                    }],
                }],
            }],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    placements_path = tmp_path / "placements.jsonl"
    profiles_path = tmp_path / "profiles.jsonl"
    _write_jsonl(placements_path, [])
    _write_jsonl(profiles_path, [])
    return runtime_root, extensions_path, placements_path, profiles_path


def test_database_sync_readback_and_direct_sql_revision(tmp_path: Path) -> None:
    runtime_root, extensions_path, placements_path, profiles_path = _runtime_fixture(tmp_path)
    database = ReferenceCatalogDatabase(tmp_path / "catalog.sqlite3")
    result = database.sync_from_runtime(
        runtime_root,
        "2026-05",
        material_placements_path=placements_path,
        procurement_template_catalog_path=ROOT / "data/material_master/procurement_template_catalog_v0_1.json",
        procurement_type_profiles_path=profiles_path,
        internal_extensions_path=extensions_path,
    )
    assert result["revision"] == 1
    assert result["summary"]["browsable_total_nodes"] == 7
    assert result["summary"]["internal_extension_count"] == 3
    profile = database.load_gpc_index().profile("91030300010101")
    assert profile["working_name"] == "灭火器箱"
    assert profile["attributes"][0]["values"][0]["working_name"] == "2×2 kg"

    before = database.revision("gpc")["revision"]
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            """
            UPDATE catalog_nodes SET working_name = ?
            WHERE catalog = 'gpc' AND code = '9103030001'
            """,
            ("灭火器空箱",),
        )
    after = database.revision("gpc")["revision"]
    assert after == before + 1
    assert database.load_gpc_index().profile("9103030001")["working_name"] == "灭火器空箱"


def test_material_publication_replaces_rows_and_advances_once(tmp_path: Path) -> None:
    runtime_root, extensions_path, placements_path, profiles_path = _runtime_fixture(tmp_path)
    database = ReferenceCatalogDatabase(tmp_path / "catalog.sqlite3")
    database.sync_from_runtime(
        runtime_root,
        "2026-05",
        material_placements_path=placements_path,
        procurement_template_catalog_path=ROOT / "data/material_master/procurement_template_catalog_v0_1.json",
        procurement_type_profiles_path=profiles_path,
        internal_extensions_path=extensions_path,
    )
    profile = {
        "profile_id": "TEST-CABINET",
        "standard_type": "灭火器箱",
        "gpc_brick_code": "91030300010101",
        "main_template_id": "standard_component",
        "constraint_ids": [],
        "sku_identity_fields": ["procurement_attributes.适配配置"],
        "transaction_fields": [],
        "offer_fields": ["price_drivers.安装方式"],
        "status": "confirmed",
        "source_material_ids": ["TEST-MAT-001"],
    }
    material = {
        "material_id": "TEST-MAT-001",
        "procurement_profile_id": "TEST-CABINET",
        "standard_type": "灭火器箱",
        "material_name": "双具灭火器箱｜2×2 kg",
        "gpc_brick_code": "91030300010101",
        "classification_source": "nexterp_internal",
        "stock_uom": "个",
        "completeness_status": "完整",
        "questions": [],
        "procurement_attributes": {"适配配置": "2×2 kg"},
        "price_drivers": {"安装方式": "落地/壁挂通用"},
        "gpc_notes": ["内部末级，不冒充 GPC Brick"],
    }
    before = database.revision("gpc")["revision"]
    revision = database.replace_material_publication([material], [profile])
    assert revision["revision"] == before + 1
    loaded = database.load_gpc_index()
    assert loaded.summary()["actual_material_count"] == 1
    assert loaded.profile("91030300010101")["actual_materials"][0]["material_id"] == "TEST-MAT-001"
