from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from nexterp_agent.item_master.tariff_attribute_review import (
    build_attribute_decision_template,
    build_attribute_review,
    compile_standard_type_sku_candidates,
    extract_tariff_attributes,
    freeze_attribute_review_package,
)


def test_fastener_attribute_candidates_keep_source_evidence() -> None:
    row = extract_tariff_attributes(
        {
            "code": "73181510",
            "source_name": "其他螺钉及螺栓：抗拉强度在800兆帕及以上的",
            "parent_name": "钢铁制的螺钉、螺栓、螺母",
            "suggested_top_group": "紧固件与连接件",
            "suggested_material_family": "螺丝/螺栓",
            "review_status": "candidate",
        }
    )
    assert row.attributes["tensile_strength"]["value"] == ">=800 MPa"
    assert row.attributes["fastener_kind"]["value"] == "螺钉 | 螺栓"
    assert row.attributes["material"]["value"].startswith("钢铁制")
    assert row.attribute_status == "review_required"


def test_mixed_fastener_name_is_not_collapsed_to_one_kind() -> None:
    row = extract_tariff_attributes(
        {"code": "76161000", "source_name": "螺钉、螺栓、螺母、垫圈及类似品", "parent_name": "其他铝制品"}
    )
    assert "螺钉" in row.attributes["fastener_kind"]["value"]
    assert "螺母" in row.attributes["fastener_kind"]["value"]
    assert row.attributes["fastener_kind"]["confidence"] == "0.40"


def test_build_attribute_review_writes_auditable_json_attributes(tmp_path: Path) -> None:
    source = tmp_path / "candidates.tsv"
    source.write_text(
        "code\tsource_name\tparent_name\tsuggested_top_group\tsuggested_material_family\treview_status\n"
        "73181510\t抗拉强度在800兆帕及以上的螺栓\t钢铁制的螺钉\t紧固件与连接件\t螺丝/螺栓\tcandidate\n",
        encoding="utf-8",
    )
    summary = build_attribute_review(source, tmp_path / "out")
    assert summary["row_count"] == 1
    with (tmp_path / "out/tariff_attribute_candidates.tsv").open(encoding="utf-8-sig", newline="") as handle:
        row = next(csv.DictReader(handle, delimiter="\t"))
    assert json.loads(row["attributes"])["tensile_strength"]["value"] == ">=800 MPa"
    assert summary["erpnext_written"] is False


def _write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    columns = list(rows[0])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def test_attribute_decision_template_is_hash_bound_and_freezes_only_explicit_approvals(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.tsv"
    _write_tsv(candidates, [
        {
            "code": "A1",
            "source_name": "高强度螺钉",
            "parent_name": "钢铁制",
            "attribute_status": "review_required",
            "attributes": json.dumps({"tensile_strength": {"value": ">=800 MPa"}}, ensure_ascii=False),
        },
        {"code": "B1", "source_name": "混合紧固件", "parent_name": "", "attribute_status": "review_required", "attributes": "{}"},
    ])
    decisions = tmp_path / "decisions.tsv"
    metadata = build_attribute_decision_template(candidates, decisions)
    assert metadata["candidate_sha256"]
    assert json.loads(decisions.with_suffix(".tsv.meta.json").read_text(encoding="utf-8"))["candidate_sha256"] == metadata["candidate_sha256"]
    _write_tsv(decisions, [
        {
            "code": "A1", "attribute_decision": "approve", "reviewer": "reviewer-1", "override_attributes": "", "comment": "确认来源强度",
            "source_name": "高强度螺钉", "parent_name": "钢铁制", "attribute_status": "review_required",
            "attributes": json.dumps({"tensile_strength": {"value": ">=800 MPa"}}, ensure_ascii=False),
        },
        {
            "code": "B1", "attribute_decision": "reject", "reviewer": "reviewer-1", "override_attributes": "", "comment": "混合税目不确认",
            "source_name": "混合紧固件", "parent_name": "", "attribute_status": "review_required", "attributes": "{}",
        },
    ])
    # Recreate the metadata after the decision file is written; the binding is to candidates, not decisions.
    decisions.with_suffix(".tsv.meta.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    summary = freeze_attribute_review_package(candidates, decisions, tmp_path / "release")
    assert summary["release_row_count"] == 1
    assert summary["decision_counts"] == {"approve": 1, "reject": 1}
    assert summary["erpnext_written"] is False
    release_row = next(csv.DictReader((tmp_path / "release/tariff_attribute_release.tsv").open(encoding="utf-8-sig"), delimiter="\t"))
    assert json.loads(release_row["effective_attributes"])["tensile_strength"]["value"] == ">=800 MPa"


def test_attribute_freeze_rejects_stale_candidate_hash(tmp_path: Path) -> None:
    candidates = tmp_path / "candidates.tsv"
    _write_tsv(candidates, [{"code": "A1", "source_name": "螺钉", "parent_name": "", "attribute_status": "candidate", "attributes": "{}"}])
    decisions = tmp_path / "decisions.tsv"
    build_attribute_decision_template(candidates, decisions)
    candidates.write_text(candidates.read_text(encoding="utf-8-sig") + "\n", encoding="utf-8-sig")
    with pytest.raises(ValueError, match="哈希"):
        freeze_attribute_review_package(candidates, decisions, tmp_path / "release")


def test_compile_standard_type_sku_candidates_requires_both_review_releases(tmp_path: Path) -> None:
    family = tmp_path / "family.tsv"
    _write_tsv(family, [
        {"code": "A1", "tariff_name": "高强度螺钉", "top_group": "紧固件与连接件", "material_family": "螺丝/螺栓"},
        {"code": "B1", "tariff_name": "未有属性", "top_group": "紧固件与连接件", "material_family": "螺丝/螺栓"},
    ])
    attributes = tmp_path / "attributes.tsv"
    _write_tsv(attributes, [{"code": "A1", "effective_attributes": json.dumps({"tensile_strength": {"value": ">=800 MPa"}}, ensure_ascii=False)}])
    summary = compile_standard_type_sku_candidates(family, attributes, tmp_path / "compiled")
    assert summary["candidate_row_count"] == 1
    assert summary["audit_status_counts"] == {"ready_for_manual_confirmation": 1, "missing_attributes": 1}
    assert summary["explicit_confirmation_required"] is True
