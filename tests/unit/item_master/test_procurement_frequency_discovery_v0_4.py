from __future__ import annotations

from nexterp_agent.item_master.procurement_frequency_discovery import DiscoveryRow
from nexterp_agent.item_master.procurement_frequency_discovery_v0_3 import convert_rows_v3
from nexterp_agent.item_master.procurement_frequency_discovery_v0_4 import (
    _build_fuzzy_candidates_v4,
    _enrich_clusters_v4,
    build_review_queues_v4,
)
from nexterp_agent.item_master.procurement_frequency_discovery_v0_3 import build_clusters_v3


def _row(
    source_row: int,
    name: str,
    *,
    date: str = "2023-01-01",
    procedure: str = "14",
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
        procedure_sequence=procedure,
        market_unit_price=price,
        core_type=name,
        safe_core=False,
        spec_signature=name,
        flags=flags,
    )


def _clusters(rows: list[DiscoveryRow]) -> list[dict]:
    return _enrich_clusters_v4(build_clusters_v3(convert_rows_v3(rows)))


def test_unknown_family_does_not_default_to_piece() -> None:
    cluster = _clusters([_row(2, "无缝管DN50", uom="米")])[0]
    assert cluster["uom_quality"]["policy_status"] == "missing"
    assert cluster["uom_quality"]["status"] == "policy_missing"
    assert cluster["uom_quality"]["preferred_uom"] == ""
    assert cluster["family_template_status"] == "candidate"
    assert cluster["publication_readiness"] == "review_required"


def test_family_template_review_is_independent_from_history_uom_conflict() -> None:
    cluster = _clusters([
        _row(2, "公元PPRΦ110管", uom="只"),
        _row(3, "公元PPRΦ50管", uom="米"),
    ])[0]
    assert cluster["family_template_status"] == "ready_for_review"
    assert cluster["source_data_quality"] == "review_required"
    assert cluster["publication_readiness"] == "review_required"


def test_explicit_family_with_missing_field_needs_template_review() -> None:
    cluster = _clusters([_row(2, "高压胶管36*2层-1寸")])[0]
    assert cluster["family_confidence"] == "explicit"
    assert cluster["family_template_status"] == "review_required"


def test_service_and_quantity_blocking_flags_are_hard_blocked() -> None:
    clusters = _clusters([
        _row(2, "顺丰快递", flags=("service_or_logistics",)),
        _row(3, "内六角螺钉M6", qty=None),
    ])
    assert all(cluster["publication_readiness"] == "blocked" for cluster in clusters)
    assert all(cluster["publish_gate"] == "blocked" for cluster in clusters)


def test_review_queues_prioritize_explicit_high_repeat_and_defer_one_offs() -> None:
    rows = [
        _row(2, "公元PPRΦ50三通", date="2023-01-01"),
        _row(3, "公元PPRΦ110三通", date="2023-01-02"),
        _row(4, "公元PPRΦ50三通", date="2023-01-03"),
        _row(5, "公元PPRΦ110三通", date="2023-01-04"),
        _row(6, "一次性临时物料", date="2023-01-05"),
    ]
    queues = build_review_queues_v4(_clusters(rows))
    assert queues["template_review_priority"]
    assert queues["deferred_low_repeat"]


def test_fuzzy_candidates_are_complete_and_mark_structural_risk() -> None:
    clusters = _clusters([
        _row(2, "2寸高压液压内丝接头"),
        _row(3, "2寸高压液压外丝接头"),
    ])
    candidates = _build_fuzzy_candidates_v4(clusters)
    assert len(candidates) == 1
    assert candidates[0]["risk_tier"] == "structure_sensitive"
    assert candidates[0]["decision"] == "人工复核，不自动合并"
