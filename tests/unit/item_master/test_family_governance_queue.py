from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "material_master" / "build_family_governance_queue.py"
SPEC = importlib.util.spec_from_file_location("build_family_governance_queue", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_queue_prioritizes_duplicates_and_inconsistent_units() -> None:
    rows = [
        {
            "top_group": "A",
            "material_family": "整洁族",
            "item_name": "甲",
            "required_specs": "规格：1",
            "stock_uom": "个",
        },
        {
            "top_group": "B",
            "material_family": "混乱族",
            "item_name": "混乱族",
            "required_specs": "规格：1",
            "stock_uom": "个",
        },
        {
            "top_group": "B",
            "material_family": "混乱族",
            "item_name": "混乱族",
            "required_specs": "规格：1",
            "stock_uom": "个",
        },
        {
            "top_group": "B",
            "material_family": "混乱族",
            "item_name": "名称 10mm",
            "required_specs": "规格：2",
            "stock_uom": "套",
        },
    ]

    queue = MODULE.build_queue(rows)

    assert queue[0]["material_family"] == "混乱族"
    assert queue[0]["generic_name_rows"] == 2
    assert queue[0]["uom_count"] == 2
    assert queue[0]["duplicate_signature_groups"] == 1
    assert queue[0]["priority_rank"] == 1
