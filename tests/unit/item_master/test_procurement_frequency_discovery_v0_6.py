from __future__ import annotations

from nexterp_agent.item_master.procurement_frequency_discovery import DiscoveryRow
from nexterp_agent.item_master.procurement_frequency_discovery_v0_3 import build_clusters_v3, convert_rows_v3
from nexterp_agent.item_master.procurement_frequency_discovery_v0_5 import _enrich_clusters_v5, _fuzzy_v5, _queues_v5
from nexterp_agent.item_master.procurement_frequency_discovery_v0_6 import build_v6_review


def _row(
    source_row: int,
    name: str,
    *,
    date: str = "2023-01-01",
    uom: str = "件",
    qty: float | None = 1,
    price: float | None = 10,
    flags: tuple[str, ...] = (),
) -> DiscoveryRow:
    return DiscoveryRow(
        source_row=source_row,
        purchase_date=date,
        raw_name=name,
        qty=qty,
        raw_uom=uom,
        normalized_uom=uom,
        procedure_sequence="14",
        market_unit_price=price,
        core_type=name,
        safe_core=False,
        spec_signature=name,
        flags=flags,
    )


def _v5(rows: list[DiscoveryRow]) -> dict:
    converted = convert_rows_v3(rows)
    clusters = _enrich_clusters_v5(build_clusters_v3(converted), converted)
    queues = _queues_v5(clusters)
    fuzzy = _fuzzy_v5(clusters, queues)
    return {
        "rows": converted,
        "clusters": clusters,
        "review_queues": queues,
        "fuzzy_review_candidates": fuzzy,
        "output_root": "fixture-v0.5",
        "summary": {"source_path": "fixture.xlsx", "source_sha256": "fixture", "source_sheet": "实际采购清单", "review_queue_counts": {name: len(items) for name, items in queues.items()}},
    }


def test_selector_family_has_bounded_axes_and_strong_unit_evidence() -> None:
    result = build_v6_review(_v5([_row(2, "公元PPRΦ50三通", uom="件")]))
    row = result["review_decisions"][0]
    assert row["decision"] == "selector"
    assert "公称尺寸" in row["selector_axes"]
    assert row["unit_evidence"]["reliability"] == "strong"
    assert row["unit_evidence"]["cannot_auto_convert"] is False
    assert row["publication_gate"] == "ready_for_template_review"


def test_generic_screw_family_is_split_before_template_creation() -> None:
    result = build_v6_review(_v5([_row(2, "螺丝M8×30")]))
    row = result["review_decisions"][0]
    assert row["decision"] == "split_required"
    assert "六角螺栓" in row["existing_standard_type_candidates"]
    assert row["publication_gate"] == "split_before_template"


def test_blocked_family_remains_blocked() -> None:
    result = build_v6_review(_v5([_row(2, "顺丰快递", flags=("service_or_logistics",))]))
    row = result["review_decisions"][0]
    assert row["decision"] == "blocked"
    assert row["publication_gate"] == "blocked"


def test_conflicting_historical_unit_is_weak_and_never_converted() -> None:
    result = build_v6_review(_v5([_row(2, "公元PPRΦ50三通", uom="吨")]))
    row = result["review_decisions"][0]
    assert row["unit_evidence"]["historical_uom_status"] == "conflict"
    assert row["unit_evidence"]["reliability"] == "weak"
    assert row["unit_evidence"]["cannot_auto_convert"] is True


def test_frequency_evidence_separates_same_day_duplicates_from_repeat_signal() -> None:
    result = build_v6_review(_v5([
        _row(2, "公元PPRΦ50三通", date="2023-01-01"),
        _row(3, "公元PPRΦ50三通", date="2023-01-01"),
        _row(4, "公元PPRΦ50三通", date="2023-01-02"),
        _row(5, "公元PPRΦ50三通", date="2023-01-03"),
        _row(6, "公元PPRΦ50三通", date="2023-01-04"),
    ]))
    evidence = result["review_decisions"][0]["frequency_evidence"]
    assert evidence["same_day_duplicate_excess_line_count"] == 1
    assert evidence["frequency_signal"] == "repeat_across_dates"
    assert evidence["prioritization_only"] is True


def test_structural_fuzzy_candidate_is_explicitly_do_not_merge() -> None:
    result = _v5([
        _row(2, "PPRΦ50弯头45°"),
        _row(3, "PPRΦ50内丝弯头45°"),
    ])
    reviewed = build_v6_review(result)["fuzzy_review_candidates"]
    assert reviewed
    assert any(row["reconciliation_action"] == "do_not_merge" for row in reviewed)


def test_summary_declares_read_only_and_audit_invariants() -> None:
    result = build_v6_review(_v5([_row(2, "公元PPRΦ50三通")]))
    assert result["summary"]["writes_erpnext"] is False
    assert result["quality_audit"]["all_decisions_have_no_auto_publish"] is True
    assert result["quality_audit"]["frequency_is_prioritization_only"] is True
