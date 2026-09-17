import csv
import importlib.util
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts/material_master/rebuild_material_master_v1_1.py"
INPUT = ROOT / "data/material_master/release_v1_0/material_master_release_v1_0.tsv"


def _load_rebuilder():
    spec = importlib.util.spec_from_file_location("rebuild_material_master_v1_1", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rebuild_preserves_all_published_skus_and_is_auditable(tmp_path):
    module = _load_rebuilder()
    summary = module.rebuild(INPUT, tmp_path)
    release_path = tmp_path / "material_master_release_v1_1.tsv"
    with release_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    assert summary["row_count"] == 1979
    assert summary["unique_item_codes"] == 1979
    assert len(rows) == 1979
    assert len({row["item_code"] for row in rows}) == 1979
    assert all(row["source_item_name"] for row in rows)
    assert all(row["classification_key"] for row in rows)
    assert all(row["required_attribute_keys"] for row in rows)
    assert all(row["rule_version"] == "material-entry-rules-v1.1" for row in rows)

    # Explicit dimension/strength tokens belong in SKU attributes, not the
    # standard name.  Keep this intentionally narrow: it checks the rule's
    # deterministic transformations without pretending to judge Chinese text.
    name_token = re.compile(
        r"(?<![A-Za-z0-9])(?:M\s*\d+|DN\s*\d+|\d+(?:\.\d+)?\s*(?:mm|厘米|cm|ml|mL|L|kg|千克|V|A|W|kW)|\d+(?:\.\d+)?\s*级)"
    )
    assert not any(name_token.search(row["item_name"]) for row in rows)

    mapping_path = tmp_path / "sku_type_mapping.tsv"
    with mapping_path.open(encoding="utf-8", newline="") as handle:
        mapping = list(csv.DictReader(handle, delimiter="\t"))
    assert len(mapping) == len(rows)
    assert {row["item_code"] for row in mapping} == {row["item_code"] for row in rows}

