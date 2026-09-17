from __future__ import annotations

from nexterp_agent.item_master.procurement_frequency_discovery import DiscoveryRow
from nexterp_agent.item_master.procurement_frequency_discovery_v0_2 import (
    build_clusters_v2,
    convert_rows,
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


def test_rebar_is_not_merged_with_tools_or_protective_sleeves() -> None:
    rows = convert_rows([
        _row(2, "世达数显式钢筋套筒力矩扳手"),
        _row(3, "钢筋保护套M20"),
        _row(4, "抗震热轧带肋钢筋HRB400E Φ10", uom="吨"),
    ])
    clusters = build_clusters_v2(rows)
    by_type = {row["standard_type_candidate"]: row for row in clusters}
    assert by_type["钢筋扭矩扳手"]["family_confidence"] == "blocked"
    assert by_type["钢筋保护套"]["family_confidence"] == "blocked"
    assert by_type["螺纹钢"]["family_confidence"] == "explicit"
    assert len(clusters) == 3


def test_ppr_inner_thread_elbow_is_a_separate_family() -> None:
    rows = convert_rows([
        _row(2, "公元PPRΦ110/45度弯头"),
        _row(3, "公元PPR110/45度弯头"),
        _row(4, "公元PPRΦ110内丝弯头"),
    ])
    clusters = build_clusters_v2(rows)
    plain = next(row for row in clusters if row["standard_type_candidate"] == "PPR弯头")
    inner = next(row for row in clusters if row["standard_type_candidate"] == "PPR内丝弯头")
    assert plain["line_count"] == 2
    assert plain["variant_count"] == 1
    assert inner["line_count"] == 1


def test_alias_and_packaging_are_separated_from_variant() -> None:
    rows = convert_rows([
        _row(2, "公元PPRΦ110管300只/包"),
        _row(3, "PPR110管300只/包"),
    ])
    cluster = next(row for row in build_clusters_v2(rows) if row["standard_type_candidate"] == "PPR管")
    assert cluster["raw_name_count"] == 2
    assert cluster["variant_count"] == 1
    assert cluster["alias_candidate_group_count"] == 1
    assert "包装" in cluster["attributes_observed"]


def test_same_session_aliases_count_once_but_variants_count_separately() -> None:
    rows = convert_rows([
        _row(2, "公元PPRΦ110管", date="2023-01-01", procedure="14"),
        _row(3, "PPR110管", date="2023-01-01", procedure="14"),
        _row(4, "PPRΦ50管", date="2023-01-01", procedure="14"),
    ])
    cluster = next(row for row in build_clusters_v2(rows) if row["standard_type_candidate"] == "PPR管")
    assert cluster["line_count"] == 3
    assert cluster["distinct_event_count_approx"] == 2
    assert cluster["repeat_line_count"] == 1
    assert cluster["active_purchase_date_count"] == 1
    assert cluster["purchase_session_count"] == 1
    assert cluster["variant_count"] == 2


def test_units_flag_a_family_but_do_not_hide_the_multi_spec_candidate() -> None:
    rows = convert_rows([
        _row(2, "公元PPRΦ110管", uom="件"),
        _row(3, "公元PPRΦ50管", uom="米"),
    ])
    cluster = next(row for row in build_clusters_v2(rows) if row["standard_type_candidate"] == "PPR管")
    assert cluster["queue"] == "多规格族候选"
    assert cluster["review_status"] == "单位字段待复核"
    assert cluster["auto_ready_multi_attribute"] is False


def test_generic_screw_variants_become_review_only_family_candidate() -> None:
    rows = convert_rows([
        _row(2, "8.8级M20*170螺丝"),
        _row(3, "8.8级M20*70螺丝"),
    ])
    cluster = next(row for row in build_clusters_v2(rows) if row["standard_type_candidate"] == "螺丝")
    assert cluster["family_confidence"] == "lexical_candidate"
    assert cluster["variant_count"] == 2
    assert cluster["queue"] == "词法族候选/待复核"
