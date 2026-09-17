from __future__ import annotations

from nexterp_agent.item_master.procurement_frequency_discovery import DiscoveryRow
from nexterp_agent.item_master.procurement_frequency_discovery_v0_3 import convert_rows_v3, build_clusters_v3
from nexterp_agent.item_master.procurement_frequency_discovery_v0_5 import (
    _enrich_clusters_v5,
    _fuzzy_v5,
    _queues_v5,
)


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


def _clusters(rows: list[DiscoveryRow]) -> list[dict]:
    converted = convert_rows_v3(rows)
    return _enrich_clusters_v5(build_clusters_v3(converted), converted)


def test_explicit_family_status_ignores_missing_historical_price() -> None:
    cluster = _clusters([_row(2, "高压胶管36*2层-1寸-7.5m", uom="条", price=None)])[0]
    assert cluster["family_template_status"] == "ready_for_review"
    assert cluster["source_evidence_quality"] == "ready_with_price_gap"
    assert cluster["publication_readiness"] == "ready_for_review"


def test_price_evidence_recomputes_from_v5_unit_policy() -> None:
    cluster = _clusters([_row(2, "公元PPRΦ110内丝弯头", uom="件", price=12)])[0]
    assert cluster["unit_policy_status"] == "defined"
    assert cluster["uom_quality"]["status"] == "trusted"
    assert cluster["price_evidence"] == "usable_for_comparison"


def test_attribute_parse_gap_remains_a_template_review() -> None:
    cluster = _clusters([_row(2, "灭火器2kg", uom="件")])[0]
    assert cluster["attribute_parse_flags"] == ["missing_extinguisher_agent_or_capacity"]
    assert cluster["family_template_status"] == "review_required"


def test_unknown_family_unit_policy_is_pending_not_piece() -> None:
    cluster = _clusters([_row(2, "无缝管DN50", uom="米")])[0]
    assert cluster["unit_policy_status"] == "missing"
    assert cluster["source_evidence_quality"] == "pending_unit_policy"
    assert cluster["uom_quality"]["preferred_uom"] == ""
    assert cluster["publication_readiness"] == "review_required"


def test_service_and_invalid_quantity_are_blocked() -> None:
    clusters = _clusters([
        _row(2, "顺丰快递", flags=("service_or_logistics",)),
        _row(3, "内六角螺钉M6", qty=None),
    ])
    assert {c["publication_readiness"] for c in clusters} == {"blocked"}


def test_review_queues_are_exhaustive_and_include_low_repeat_multi_spec() -> None:
    rows = [
        _row(2, "公元PPRΦ50三通", date="2023-01-01"),
        _row(3, "公元PPRΦ110三通", date="2023-01-02"),
        _row(4, "一次性临时物料", date="2023-01-03"),
    ]
    clusters = _clusters(rows)
    queues = _queues_v5(clusters)
    queued_ids = [entry["cluster_id"] for entries in queues.values() for entry in entries]
    assert len(queued_ids) == len(clusters)
    assert len(set(queued_ids)) == len(clusters)
    assert queues["low_repeat_multi_spec_review"]


def test_fuzzy_queue_marks_structural_difference_and_does_not_merge() -> None:
    clusters = _clusters([
        _row(2, "2寸高压液压内丝接头"),
        _row(3, "2寸高压液压外丝接头"),
    ])
    fuzzy = _fuzzy_v5(clusters, _queues_v5(clusters))
    assert len(fuzzy) == 1
    assert fuzzy[0]["risk_tier"] == "structure_sensitive"
    assert fuzzy[0]["review_queue"] == "archive_do_not_merge"
    assert fuzzy[0]["decision"] == "人工复核，不自动合并"
