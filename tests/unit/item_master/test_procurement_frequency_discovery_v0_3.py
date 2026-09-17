from __future__ import annotations

from nexterp_agent.item_master.procurement_frequency_discovery import DiscoveryRow
from nexterp_agent.item_master.procurement_frequency_discovery_v0_3 import (
    build_clusters_v3,
    convert_rows_v3,
)


def _row(
    source_row: int,
    name: str,
    *,
    date: str = "2023-01-01",
    procedure: str = "14",
    uom: str = "件",
    qty: float = 1,
    price: float | None = 10,
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
        flags=(),
    )


def test_hose_parser_preserves_cut_length_and_bore() -> None:
    rows = convert_rows_v3([
        _row(2, "高压胶管36*2层-1寸-7.5m", uom="条"),
        _row(3, "高压胶管36*2层-1寸-6m", uom="条"),
    ])
    assert rows[0].attributes["长度"] == "7.5M"
    assert rows[0].attributes["结构规格"] == "36*2层"
    assert rows[0].attributes["公称尺寸"] == "1寸"
    assert rows[0].technical_variant_key != rows[1].technical_variant_key
    cluster = build_clusters_v3(rows)[0]
    assert cluster["variant_count"] == 2


def test_ppr_elbow_splits_nominal_size_and_angle() -> None:
    row = convert_rows_v3([_row(2, "公元PPRΦ110/45度弯头")])[0]
    assert row.family_candidate == "PPR弯头"
    assert row.attributes["公称尺寸"] == "110"
    assert row.attributes["角度"] == "45°"


def test_extinguisher_parser_keeps_agent_and_capacity() -> None:
    rows = convert_rows_v3([
        _row(2, "干粉灭火器2kg"),
        _row(3, "泡沫灭火器6L"),
    ])
    assert rows[0].attributes["灭火剂类型"] == "干粉"
    assert rows[0].attributes["额定容量"] == "2KG"
    assert rows[1].attributes["灭火剂类型"] == "泡沫"
    assert rows[1].attributes["额定容量"] == "6L"
    assert build_clusters_v3(rows)[0]["variant_count"] == 2


def test_flat_spring_washer_is_semantic_alias_and_grade_is_compatibility() -> None:
    rows = convert_rows_v3([
        _row(2, "8.8级M20平垫弹垫"),
        _row(3, "平弹垫M20"),
    ])
    assert {row.family_candidate for row in rows} == {"弹簧垫圈与平垫圈组合"}
    assert rows[0].attributes["适配螺纹"] == "M20"
    assert rows[0].attributes["适配螺栓性能等级"] == "8.8级"
    cluster = build_clusters_v3(rows)[0]
    assert cluster["family_confidence"] == "mixed_rule_confidence"
    assert cluster["publish_gate"] == "review_required"


def test_uom_policy_is_recommendation_and_conflict_gate() -> None:
    rows = convert_rows_v3([
        _row(2, "公元PPRΦ110管", uom="只"),
        _row(3, "公元PPRΦ50管", uom="米"),
    ])
    cluster = build_clusters_v3(rows)[0]
    assert cluster["uom_quality"]["preferred_uom"] == "米"
    assert cluster["uom_quality"]["status"] == "conflict"
    assert cluster["publish_gate"] == "review_required"
    assert cluster["uom_quality"]["invalid_source_uom_count"] == 1


def test_frequency_quadrant_separates_high_repeat_multi_spec() -> None:
    rows = convert_rows_v3([
        _row(2, "公元PPRΦ50三通", date="2023-01-01"),
        _row(3, "公元PPRΦ110三通", date="2023-01-02"),
        _row(4, "公元PPRΦ50三通", date="2023-01-03"),
        _row(5, "公元PPRΦ110三通", date="2023-01-04"),
    ])
    cluster = build_clusters_v3(rows)[0]
    assert cluster["frequency_quadrant"] == "high_repeat_multi_spec"
    assert cluster["active_purchase_date_count"] == 4
    assert cluster["purchase_session_count"] == 4


def test_price_is_observed_only_when_uom_is_not_trusted() -> None:
    rows = convert_rows_v3([_row(2, "公元PPRΦ110弯头", uom="把", price=12)])
    cluster = build_clusters_v3(rows)[0]
    assert cluster["price_evidence"] == "observed_only"
    assert cluster["market_value_sum_observed"] == 12

