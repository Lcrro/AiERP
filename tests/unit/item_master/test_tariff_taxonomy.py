from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexterp_agent.item_master.tariff_taxonomy import (
    TariffTaxonomyIndex,
    resolve_tariff_taxonomy_source,
)


def _sample_nodes() -> list[dict[str, object]]:
    return [
        {"code": "S15", "name": "贱金属及其制品", "level": 0, "parent_code": None, "page": 894, "kind": "section"},
        {"code": "73", "name": "钢铁制品", "level": 1, "parent_code": "S15", "page": 929, "kind": "chapter"},
        {"code": "7318", "name": "钢铁制螺钉、螺栓及类似品", "level": 2, "parent_code": "73", "page": 945, "kind": "heading"},
        {"code": "731815", "name": "螺纹制品 / 其他螺钉及螺栓", "level": 3, "parent_code": "7318", "page": 945, "kind": "subheading"},
        {"code": "73181510", "name": "抗拉强度在800兆帕及以上的", "level": 4, "parent_code": "731815", "page": 945, "kind": "sku"},
    ]


def test_taxonomy_index_exposes_lazy_children_summary_and_full_search_path() -> None:
    index = TariffTaxonomyIndex(_sample_nodes())

    assert index.summary()["counts"] == {
        "section": 1,
        "chapter": 1,
        "heading": 1,
        "subheading": 1,
        "sku": 1,
    }
    assert index.children()[0]["code"] == "S15"
    assert index.children("7318")[0]["code"] == "731815"
    result = index.search("800兆帕", kind="sku")
    assert result["total"] == 1
    assert [node["code"] for node in result["rows"][0]["path"]] == [
        "S15", "73", "7318", "731815", "73181510",
    ]
    assert index.validate() == []


def test_taxonomy_index_rejects_missing_parent() -> None:
    with pytest.raises(ValueError, match="缺失父级"):
        TariffTaxonomyIndex([
            {"code": "73", "name": "钢铁制品", "level": 1, "parent_code": "S15", "kind": "chapter"},
        ])


def test_resolve_taxonomy_source_prefers_reviewed_runtime_file(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    job_dir = runtime_root / "job-1"
    job_dir.mkdir(parents=True)
    nodes_path = job_dir / "tariff-nodes.jsonl"
    nodes_path.write_text("{}\n", encoding="utf-8")
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"source_path": str(nodes_path)}), encoding="utf-8")

    assert resolve_tariff_taxonomy_source(summary_path, runtime_root) == nodes_path.resolve()


def test_resolve_taxonomy_source_rejects_review_path_outside_runtime(tmp_path: Path) -> None:
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"source_path": str(outside)}), encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="完整税则层级"):
        resolve_tariff_taxonomy_source(summary_path, runtime_root)
