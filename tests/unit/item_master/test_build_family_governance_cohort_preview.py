from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "material_master" / "build_family_governance_cohort_preview.py"
SPEC = importlib.util.spec_from_file_location("build_family_governance_cohort_preview", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_build_preview_merges_family_results_and_keeps_review_queue(tmp_path: Path) -> None:
    family_dir = tmp_path / "管材管件阀门_弯头"
    family_dir.mkdir()
    MODULE.write_tsv(
        family_dir / "family_governed.tsv",
        [
            {
                "item_code": "PIPE-1",
                "proposed_item_name": "内丝弯头",
                "proposed_sku_name": "PPR内丝弯头 25mm×4分",
                "proposed_required_specs": "材质：PPR；规格/口径：25mm；内丝端口径：4分",
                "proposed_optional_specs": "",
                "proposed_stock_uom": "个",
                "proposed_aliases": "PPR25*4内牙弯头",
                "proposed_brand": "",
                "proposed_model": "",
                "duplicate_with_item_code": "",
                "change_reason": "保留内丝端口径。",
            }
        ],
        MODULE.MODEL_FIELDS,
    )
    (family_dir / "independent_review.json").write_text(
        '{"verdict":"needs_revision","issues":[{"item_code":"PIPE-1","severity":"medium","issue_type":"duplicate","issue":"疑似重复","suggestion":"人工确认"}]}',
        encoding="utf-8",
    )
    (family_dir / "summary.json").write_text(
        '{"source_rows":1}',
        encoding="utf-8",
    )
    source_rows = [
        {
            "item_code": "PIPE-1",
            "item_name": "弯头",
            "sku_name": "PPR弯头",
            "required_specs": "规格：25",
            "optional_specs": "",
            "stock_uom": "个",
            "purchase_uom": "个",
            "aliases": "",
            "brand": "",
            "model": "",
            "search_keywords": "",
            "governance_note": "",
            "top_group": "管材管件阀门",
            "material_family": "弯头",
        }
    ]

    preview, queue, summary = MODULE.build_preview(
        source_rows=source_rows,
        cohort_rows=[{"top_group": "管材管件阀门", "material_family": "弯头"}],
        output_root=tmp_path,
    )

    assert preview[0]["sku_name"] == "PPR内丝弯头 25mm×4分"
    assert "独立复核[medium]" in preview[0]["governance_note"]
    assert queue[0]["review_status"] == "待人工确认"
    assert summary["governed_rows"] == 1
    assert summary["review_pending_family_count"] == 1
