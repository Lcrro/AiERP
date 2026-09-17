from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexterp_agent.item_master.procurement_templates import (
    DEFAULT_TEMPLATE_CATALOG_PATH,
    ProcurementTemplateCatalog,
    ProcurementTemplateRegistry,
)


ROOT = Path(__file__).resolve().parents[3]
PROFILE_PATH = ROOT / ".runtime" / "material-master" / "gpc-procurement-type-profiles.jsonl"
MATERIAL_PATH = ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl"


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_procurement_catalog_has_exactly_ten_main_templates_and_five_constraints() -> None:
    catalog = ProcurementTemplateCatalog.model_validate(
        json.loads(DEFAULT_TEMPLATE_CATALOG_PATH.read_text(encoding="utf-8"))
    )

    assert len(catalog.main_templates) == 10
    assert len(catalog.constraints) == 5
    assert catalog.sku_generation_policy == "actual_combinations_only"
    assert {item.template_id for item in catalog.main_templates} >= {
        "standard_component", "linear_cut_material", "custom_fabricated", "kit_assembly",
    }
    force_review = {item.constraint_id for item in catalog.constraints if item.force_review}
    assert force_review == {"pressure_fluid", "safety_regulatory", "chemical_shelf_life"}


def test_current_workbench_materials_are_profiled_without_cartesian_generation() -> None:
    registry = ProcurementTemplateRegistry.from_files(DEFAULT_TEMPLATE_CATALOG_PATH, PROFILE_PATH)
    materials = _load_jsonl(MATERIAL_PATH)
    enriched = [registry.enrich_material(item) for item in materials]
    golden = [item for item in enriched if str(item["material_id"]).startswith("LH-GPC-C")]

    summary = registry.summary()
    assert summary["catalog_version"] == "v0.1"
    assert summary["main_template_count"] == 10
    assert summary["constraint_count"] == 5
    assert summary["type_profile_count"] == len(_load_jsonl(PROFILE_PATH))
    assert summary["sku_generation_policy"] == "actual_combinations_only"
    assert len(enriched) >= 8
    assert len(golden) == 8
    assert sum(item["record_kind"] == "sku_candidate" for item in golden) == 7
    assert sum(item["record_kind"] == "project_configuration" for item in golden) == 1
    fingerprints = [item["sku_identity_fingerprint"] for item in enriched if item["sku_identity_fingerprint"]]
    assert len(fingerprints) == len(set(fingerprints))

    roller = next(item for item in enriched if item["material_id"] == "LH-GPC-C007")
    assert roller["procurement_profile"]["main_template_id"] == "custom_fabricated"
    assert roller["procurement_profile"]["constraint_ids"] == ["project_custom_nonstock"]
    assert roller["sku_identity_fingerprint"] == ""
    assert roller["record_kind"] == "project_configuration"


def test_offer_fields_do_not_duplicate_sku_but_identity_fields_do() -> None:
    registry = ProcurementTemplateRegistry.from_files(DEFAULT_TEMPLATE_CATALOG_PATH, PROFILE_PATH)
    source = next(item for item in _load_jsonl(MATERIAL_PATH) if item["material_id"] == "LH-GPC-C005")
    baseline = registry.enrich_material(source)

    offer_changed = json.loads(json.dumps(source, ensure_ascii=False))
    offer_changed["procurement_attributes"]["包装"] = "500只/包"
    same_identity = registry.enrich_material(offer_changed)
    assert same_identity["sku_identity_fingerprint"] == baseline["sku_identity_fingerprint"]
    assert same_identity["configuration_fingerprint"] == baseline["configuration_fingerprint"]

    identity_changed = json.loads(json.dumps(source, ensure_ascii=False))
    identity_changed["procurement_attributes"]["规格"] = "Φ8×40 mm"
    different_identity = registry.enrich_material(identity_changed)
    assert different_identity["sku_identity_fingerprint"] != baseline["sku_identity_fingerprint"]


def test_template_registry_rejects_unassigned_or_missing_attribute_roles() -> None:
    registry = ProcurementTemplateRegistry.from_files(DEFAULT_TEMPLATE_CATALOG_PATH, PROFILE_PATH)
    source = next(item for item in _load_jsonl(MATERIAL_PATH) if item["material_id"] == "LH-GPC-C001")

    unassigned = json.loads(json.dumps(source, ensure_ascii=False))
    unassigned["procurement_attributes"]["颜色"] = "白色"
    with pytest.raises(ValueError, match="未分配属性角色"):
        registry.enrich_material(unassigned)

    missing = json.loads(json.dumps(source, ensure_ascii=False))
    del missing["procurement_attributes"]["规格"]
    with pytest.raises(ValueError, match="属性缺失"):
        registry.enrich_material(missing)
