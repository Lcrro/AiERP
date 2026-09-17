from __future__ import annotations

import json

from scripts.material_master.evaluate_vector_shadow import load_current_linked_cases, review_gate_status
from scripts.material_master.build_retrieval_review_set import build_review_set
from scripts.material_master.promote_reviewed_aliases import promote_reviewed_aliases
from scripts.material_master.model_pre_review_retrieval_queue import model_pre_review
from scripts.material_master.resolve_assisted_retrieval_review import resolve_assisted_review

from nexterp_agent.item_master.release_resolver import (
    ReleaseMaterialResolver,
    load_current_published_catalog,
)
from nexterp_agent.item_master.reference_catalog import GpcReferenceIndex
from nexterp_agent.item_master.vector_retrieval import HashingTextVectorizer, TextVectorIndex
from nexterp_agent.item_master.source_identity import make_source_record, source_row_hash, source_record_matches


def test_hashing_vectorizer_is_stable_and_normalized() -> None:
    vectorizer = HashingTextVectorizer(dimension=128)
    first = vectorizer.embed_one("六角螺栓 M12×40")
    second = vectorizer.embed_one("六角螺栓 M12×40")

    assert first == second
    assert len(first) == 128
    assert abs(sum(value * value for value in first) - 1.0) < 1e-9


def test_vector_index_orders_related_text_before_unrelated_text() -> None:
    index = TextVectorIndex(HashingTextVectorizer(dimension=128))
    index.build([
        ("bolt", "六角螺栓 M12×40 碳钢"),
        ("hose", "透明钢丝增强吸水软管 DN50"),
        ("glove", "帆布手套 加厚 L码"),
    ])

    matches = index.query("螺栓 M12*40", limit=3)

    assert matches[0].document_id == "bolt"
    assert matches[0].score > matches[-1].score


def test_release_resolver_exposes_vector_signal_without_auto_selecting() -> None:
    resolver = ReleaseMaterialResolver()
    result = resolver.resolve("六角螺栓 M12*40")

    assert result["candidates"]
    top = result["candidates"][0]
    assert "vector_score" in top
    assert "retrieval_sources" in top
    assert result["status"] in {"ready", "needs_confirmation"}


def test_unknown_query_is_not_promoted_by_vector_recall() -> None:
    resolver = ReleaseMaterialResolver()

    result = resolver.resolve("星际泡泡机")

    assert result["status"] == "not_found"
    assert result["resolved"] is None


def test_vector_signal_is_shadow_only_and_cannot_reorder_lexical_candidates(tmp_path) -> None:
    catalog = tmp_path / "catalog.tsv"
    catalog.write_text(
        "item_code\titem_name\tsku_name\tstandard_name\tstock_uom\tstatus\tagent_use_policy\n"
        "A\t六角螺栓\t六角螺栓 M12×40\t六角螺栓\t件\tactive\tauto_select_allowed\n"
        "B\t六角螺栓\t六角螺栓 M12×50\t六角螺栓\t件\tactive\tauto_select_allowed\n"
        "C\t随机物料\t随机物料\t随机物料\t件\tactive\tauto_select_allowed\n",
        encoding="utf-8",
    )
    resolver = ReleaseMaterialResolver(catalog)
    resolver.vector_scores = lambda _query, _specs: {"A": 0.45, "B": 0.99, "C": 0.99}  # type: ignore[method-assign]

    result = resolver.resolve("六角螺栓 M12*40", limit=3)

    # B has the stronger vector score, but A remains first because lexical
    # ranking is the governed production order in shadow mode. C is not
    # surfaced until a labelled review set authorises vector-only recall.
    assert [candidate["item_code"] for candidate in result["candidates"]] == ["A", "B"]
    assert result["candidates"][0]["score"] > result["candidates"][1]["score"]


def test_vector_mode_is_off_by_default_and_shadow_is_explicit(tmp_path) -> None:
    catalog = tmp_path / "catalog.tsv"
    catalog.write_text(
        "item_code\titem_name\tsku_name\tstandard_name\tstock_uom\tstatus\tagent_use_policy\n"
        "A\t六角螺栓\t六角螺栓 M12×40\t六角螺栓\t件\tactive\tauto_select_allowed\n",
        encoding="utf-8",
    )

    production = ReleaseMaterialResolver(catalog)
    shadow = ReleaseMaterialResolver(catalog, vector_mode="shadow")

    assert production.vector_mode == "off"
    assert production.vector_scores("六角螺栓 M12×40") == {}
    assert shadow.vector_mode == "shadow"
    assert shadow.vector_scores("六角螺栓 M12×40")["A"] > 0


def test_reference_catalog_does_not_build_vector_lane_by_default() -> None:
    index = GpcReferenceIndex([
        {"code": "10000000", "name": "段", "kind": "segment", "level": 0, "parent_code": ""},
        {"code": "10000001", "name": "族", "kind": "family", "level": 1, "parent_code": "10000000"},
        {"code": "10000002", "name": "类", "kind": "class", "level": 2, "parent_code": "10000001"},
        {"code": "10000003", "name": "螺栓", "kind": "brick", "level": 3, "parent_code": "10000002"},
    ])

    assert index.vector_mode == "off"
    rows = index.candidate_bricks(["螺栓"])
    assert rows and rows[0]["vector_score"] == 0.0
    assert rows[0]["vector_shadow_hit"] is False


def test_current_published_catalog_uses_numeric_erpnext_codes(tmp_path) -> None:
    placements = tmp_path / "placements.jsonl"
    placements.write_text(
        json.dumps({
            "material_id": "LH-GPC-1",
            "material_name": "六角螺栓｜M12×40",
            "standard_type": "六角螺栓",
            "gpc_brick_code": "100031850101",
            "procurement_attributes": {"规格": "M12×40"},
            "price_drivers": {"材质": "碳钢"},
            "stock_uom": "件",
        }, ensure_ascii=False) + "\n"
        + json.dumps({
            "material_id": "LEGACY",
            "material_name": "旧物料",
            "standard_type": "旧物料",
            "gpc_brick_code": "10000000",
            "procurement_attributes": {"规格": "未知"},
            "price_drivers": {"材质": "未知"},
            "stock_uom": "件",
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    code_map = tmp_path / "map.json"
    code_map.write_text(
        json.dumps({"material_item_codes": {"LH-GPC-1": "100031850101001", "LEGACY": "FAST-0001"}}),
        encoding="utf-8",
    )

    rows = load_current_published_catalog(placements, code_map)

    assert [row["item_code"] for row in rows] == ["100031850101001"]
    assert rows[0]["source_material_id"] == "LH-GPC-1"


def test_current_published_catalog_does_not_ingest_unreviewed_frequency_aliases(tmp_path) -> None:
    placements = tmp_path / "placements.jsonl"
    placements.write_text(
        json.dumps({
            "material_id": "LH-GPC-1",
            "material_name": "六角螺栓｜M12×40",
            "standard_type": "六角螺栓",
            "gpc_brick_code": "100031850101",
            "procurement_attributes": {"规格": "M12×40"},
            "source_rows": [12],
            "stock_uom": "件",
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    code_map = tmp_path / "map.json"
    code_map.write_text(json.dumps({"material_item_codes": {"LH-GPC-1": "100031850101001"}}), encoding="utf-8")
    clusters = tmp_path / "clusters.jsonl"
    clusters.write_text(
        json.dumps({
            "grouping_confidence": "high",
            "standard_type_candidate": "六角螺栓",
            "raw_names": ["M12螺栓"],
            "source_rows": [12],
        }, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with clusters.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "grouping_confidence": "high",
            "standard_type_candidate": "六角螺栓",
            "raw_names": ["M99螺栓"],
            "source_rows": [12],
        }, ensure_ascii=False) + "\n")

    rows = load_current_published_catalog(placements, code_map, clusters)
    assert "M12螺栓" not in rows[0]["aliases"]
    assert rows[0]["approved_aliases"] == ""


def test_current_published_catalog_accepts_only_explicitly_approved_aliases(tmp_path) -> None:
    placements = tmp_path / "placements.jsonl"
    placements.write_text(json.dumps({
        "material_id": "LH-GPC-1",
        "material_name": "六角螺栓｜M12×40",
        "standard_type": "六角螺栓",
        "gpc_brick_code": "100031850101",
        "procurement_attributes": {"规格": "M12×40"},
        "source_rows": [12],
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    code_map = tmp_path / "map.json"
    code_map.write_text(json.dumps({"material_item_codes": {"LH-GPC-1": "100031850101001"}}), encoding="utf-8")
    aliases = tmp_path / "approved.jsonl"
    aliases.write_text(json.dumps({
        "alias": "M12螺栓",
        "source_material_id": "LH-GPC-1",
        "status": "approved",
        "reviewer": "tester",
        "reviewed_at": "2026-08-31T10:00:00+08:00",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    rows = load_current_published_catalog(placements, code_map, approved_aliases_path=aliases)
    assert rows[0]["approved_aliases"] == "M12螺栓"


def test_current_published_catalog_rejects_approval_without_audit_fields(tmp_path) -> None:
    placements = tmp_path / "placements.jsonl"
    placements.write_text(json.dumps({
        "material_id": "LH-GPC-1", "material_name": "六角螺栓", "standard_type": "六角螺栓",
        "gpc_brick_code": "100031850101", "source_rows": [12],
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    code_map = tmp_path / "map.json"
    code_map.write_text(json.dumps({"material_item_codes": {"LH-GPC-1": "100031850101001"}}), encoding="utf-8")
    aliases = tmp_path / "approved.jsonl"
    aliases.write_text(json.dumps({
        "alias": "M12螺栓", "source_material_id": "LH-GPC-1", "status": "approved",
    }, ensure_ascii=False) + "\n", encoding="utf-8")

    rows = load_current_published_catalog(placements, code_map, approved_aliases_path=aliases)

    assert rows[0]["approved_aliases"] == ""


def test_current_published_catalog_requires_erpnext_enablement_for_auto_policy(tmp_path) -> None:
    placements = tmp_path / "placements.jsonl"
    placements.write_text(json.dumps({
        "material_id": "LH-GPC-1", "material_name": "六角螺栓", "standard_type": "六角螺栓",
        "gpc_brick_code": "100031850101", "source_rows": [12], "stock_uom": "件",
    }, ensure_ascii=False) + "\n", encoding="utf-8")
    code_map = tmp_path / "map.json"
    code_map.write_text(json.dumps({"material_item_codes": {"LH-GPC-1": "100031850101001"}}), encoding="utf-8")

    unverified = load_current_published_catalog(placements, code_map)
    assert unverified[0]["erpnext_status"] == "unverified"
    assert unverified[0]["agent_use_policy"] == "review_required"
    enabled = load_current_published_catalog(placements, code_map, enabled_item_codes={"100031850101001"})
    assert enabled[0]["erpnext_status"] == "enabled"
    assert enabled[0]["agent_use_policy"] == "auto_select_allowed"


def test_source_identity_does_not_join_same_row_across_datasets() -> None:
    purchase = make_source_record(47, dataset="material_purchase_2024", document="actual_material_purchase_list")
    historical = make_source_record(47, dataset="civil_reference_materials", document="civil_reference_table")
    assert source_record_matches(purchase, purchase)
    assert not source_record_matches(purchase, historical)


def test_source_row_hash_rejects_same_identity_with_changed_source_content() -> None:
    left = make_source_record(47, row={"raw_name": "世达扭力扳手", "qty": 1})
    right = make_source_record(47, row={"raw_name": "热轧带肋钢筋", "qty": 1})
    assert left["source_row_hash"] != right["source_row_hash"]
    assert not source_record_matches(left, right)


def test_linked_review_cases_keep_same_row_separate_across_sources(tmp_path) -> None:
    purchase_record = make_source_record(
        47,
        row={"raw_name": "世达扭力扳手", "qty": 1},
        dataset="material_purchase_2024",
        document="actual_material_purchase_list",
        sheet="实际采购清单",
    )
    historical_record = make_source_record(
        47,
        row={"raw_name": "热轧带肋钢筋", "qty": 1},
        dataset="civil_reference_materials",
        document="civil_reference_table",
        sheet="材料表",
    )
    placements = tmp_path / "placements.jsonl"
    placements.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in (
                {
                    "material_id": "PURCHASE-47",
                    "material_name": "世达扭力扳手",
                    "standard_type": "扭力扳手",
                    "source_records": [purchase_record],
                },
                {
                    "material_id": "HISTORICAL-47",
                    "material_name": "热轧带肋钢筋",
                    "standard_type": "钢筋",
                    "source_records": [historical_record],
                },
            )
        ),
        encoding="utf-8",
    )
    item_map = tmp_path / "item-map.json"
    item_map.write_text(
        json.dumps(
            {
                "material_item_codes": {
                    "PURCHASE-47": "1000000000001",
                    "HISTORICAL-47": "1000000000002",
                }
            }
        ),
        encoding="utf-8",
    )
    clusters = tmp_path / "clusters.jsonl"
    clusters.write_text(
        "".join(
            json.dumps(cluster, ensure_ascii=False) + "\n"
            for cluster in (
                {
                    "cluster_id": "PURCHASE-CLUSTER",
                    "standard_type_candidate": "扭力扳手",
                    "raw_names": ["世达扭力扳手"],
                    "source_rows": [47],
                    "source_records": [purchase_record],
                },
                {
                    "cluster_id": "HISTORICAL-CLUSTER",
                    "standard_type_candidate": "钢筋",
                    "raw_names": ["热轧带肋钢筋"],
                    "source_rows": [47],
                    "source_records": [historical_record],
                },
            )
        ),
        encoding="utf-8",
    )

    cases = load_current_linked_cases(clusters, placements, item_map)

    assert len(cases) == 2
    assert {case["expected_top_item_code"] for case in cases} == {"1000000000001", "1000000000002"}
    assert {case["source_identity"]["source_dataset"] for case in cases} == {
        "material_purchase_2024",
        "civil_reference_materials",
    }


def test_vector_maintenance_gate_stays_blocked_until_review_labels_exist(tmp_path) -> None:
    review = tmp_path / "review.jsonl"
    review.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in (
                {"sample_role": "positive_candidate", "review_decision": "approved"},
                {"sample_role": "hard_negative_candidate", "review_decision": "rejected"},
                {"sample_role": "positive_candidate", "review_decision": ""},
            )
        ),
        encoding="utf-8",
    )

    gate = review_gate_status(review)

    assert gate["status"] == "blocked"
    assert gate["counts"] == {"positive": 1, "negative": 1, "pending": 1, "invalid": 0}
    assert gate["gates"]["minimum_confirmed_positive"] == 300


def test_review_set_has_required_pending_coverage(tmp_path) -> None:
    result = build_review_set(tmp_path / "review.jsonl", tmp_path / "summary.json")

    summary = result["summary"]
    assert summary["positive_candidate_count"] == 300
    assert summary["negative_candidate_count"] == 100
    assert summary["confirmed_positive_count"] == 0
    assert summary["confirmed_negative_count"] == 0
    tags = summary["coverage_tag_counts"]
    assert tags["alias"] > 0
    assert tags["spec_variant"] > 0
    assert tags["brand"] > 0
    assert tags["typo"] > 0
    assert tags["nonexistent"] == 50


def test_model_pre_review_is_separate_and_never_fills_human_labels(tmp_path) -> None:
    review = tmp_path / "review.jsonl"
    review.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False) + "\n"
            for row in (
                {
                    "review_id": "POS-0001",
                    "sample_role": "positive_candidate",
                    "query": "六角螺栓｜M12×40",
                    "expected_item_code": "1001",
                    "expected_item_name": "六角螺栓｜M12×40",
                    "coverage_tags": ["canonical"],
                    "review_decision": "",
                },
                {
                    "review_id": "POS-0002",
                    "sample_role": "positive_candidate",
                    "query": "灭火器2kg",
                    "expected_item_code": "1002",
                    "expected_item_name": "手提式干粉灭火器｜2 kg",
                    "coverage_tags": ["alias"],
                    "review_decision": "",
                },
                {
                    "review_id": "NEG-0001",
                    "sample_role": "nonexistent_candidate",
                    "query": "不存在物料测试-001",
                    "expected_item_code": "",
                    "coverage_tags": ["nonexistent"],
                    "review_decision": "",
                },
            )
        ),
        encoding="utf-8",
    )
    output = tmp_path / "model.jsonl"
    summary = tmp_path / "model.summary.json"

    result = model_pre_review(review, output, summary, reviewed_at="2026-08-31T12:00:00+08:00")

    assert result["summary"]["row_count"] == 3
    assert result["summary"]["production_effect"]["fills_human_review_decision"] is False
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert rows[0]["model_pre_review"]["verdict"] == "likely_match"
    assert rows[0]["review_decision"] == ""
    assert rows[1]["model_pre_review"]["verdict"] == "needs_human"
    assert rows[2]["model_pre_review"]["verdict"] == "likely_non_match"
    assert all(row["model_pre_review"]["production_effect"] == "none" for row in rows)
    # The authoritative gate reads the original queue, not this projection;
    # model recommendations cannot satisfy the 300/100 human-label gate.
    assert review_gate_status(review)["counts"]["pending"] == 3


def test_assisted_high_risk_resolution_keeps_human_and_production_boundaries(tmp_path) -> None:
    source = tmp_path / "model.jsonl"
    rows = []
    for index in range(260, 270):
        rows.append({
            "review_id": f"POS-{index:04d}",
            "query": "错别字挑战",
            "expected_item_code": "1001",
            "expected_item_name": "标准物料",
            "model_pre_review": {"verdict": "needs_human"},
            "source_audit_status": "not_provided",
        })
    for index in (276, 280, 286, 287, 289, 290, 291, 295, 299):
        rows.append({
            "review_id": f"POS-{index:04d}",
            "query": "采购简称",
            "expected_item_code": "1002",
            "expected_item_name": "标准物料",
            "source_identity": {
                "source_dataset": "d",
                "source_document": "f",
                "source_sheet": "s",
                "source_row": index,
                "source_row_hash": "abc",
            },
            "model_pre_review": {"verdict": "needs_human"},
            "source_audit_status": "complete",
        })
    source.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    output = tmp_path / "assisted.jsonl"
    summary = tmp_path / "summary.json"

    result = resolve_assisted_review(
        source,
        output,
        summary,
        reviewed_at="2026-09-01T09:00:00+08:00",
    )

    assert result["summary"]["row_count"] == 19
    assert result["summary"]["synthetic_typo_count"] == 10
    assert result["summary"]["complete_source_identity_count"] == 9
    assert result["summary"]["production_effect"]["promotes_aliases"] is False
    resolved = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert all(row["review_decision"] == "" for row in resolved)
    assert all(row["reviewer"] == "" for row in resolved)
    assert all(row["assisted_resolution"]["production_effect"] == "none" for row in resolved)
    assert {
        row["assisted_resolution"]["production_alias_action"] for row in resolved[:10]
    } == {"do_not_promote_synthetic_typo"}


def test_only_numeric_code_or_approved_alias_can_auto_select(tmp_path) -> None:
    catalog = tmp_path / "catalog.tsv"
    catalog.write_text(
        "item_code\titem_name\tsku_name\tstandard_name\trequired_specs\tstock_uom\tstatus\tagent_use_policy\tapproved_aliases\n"
        "1001\t六角螺栓\t六角螺栓 M12×40\t六角螺栓\t规格=M12×40\t件\tactive\tauto_select_allowed\tM12×40螺栓\n",
        encoding="utf-8",
    )
    resolver = ReleaseMaterialResolver(catalog)
    assert resolver.resolve("1001")["status"] == "ready"
    alias_result = resolver.resolve("M12×40螺栓")
    assert alias_result["status"] == "ready"
    assert resolver.resolve("六角螺栓 M12×40")["status"] == "needs_confirmation"
    assert resolver.resolve("M12螺栓", specs={"规格": "M10×20"})["status"] != "ready"


def test_strict_projection_rejects_legacy_non_numeric_exact_code(tmp_path) -> None:
    catalog = tmp_path / "catalog.tsv"
    catalog.write_text(
        "item_code\titem_name\tsku_name\trequired_specs\tstock_uom\tstatus\tagent_use_policy\tapproved_aliases\n"
        "SAFE-0001\t测试物料\t测试物料 M1\t规格=M1\t件\tactive\tauto_select_allowed\t\n",
        encoding="utf-8",
    )
    resolver = ReleaseMaterialResolver(catalog)
    result = resolver.resolve("SAFE-0001")
    assert result["status"] == "needs_confirmation"
    assert result["resolved"] is None


def test_only_audited_positive_review_rows_are_promoted_to_aliases(tmp_path) -> None:
    review = tmp_path / "review.jsonl"
    rows = [
        {
            "review_id": "POS-0001",
            "sample_role": "positive_candidate",
            "query": "M12×40螺栓",
            "expected_item_code": "1001",
            "review_decision": "approved",
            "reviewer": "reviewer@example.com",
            "reviewed_at": "2026-08-31T12:00:00+08:00",
            "source_identity": {"source_dataset": "d", "source_document": "f", "source_sheet": "s", "source_row": 1},
        },
        {
            "review_id": "POS-0002",
            "sample_role": "positive_candidate",
            "query": "未审核别名",
            "expected_item_code": "1002",
            "review_decision": "approved",
            "reviewer": "",
            "reviewed_at": "",
        },
        {
            "review_id": "NEG-0001",
            "sample_role": "hard_negative_candidate",
            "query": "M12×40螺栓",
            "expected_item_code": "1002",
            "review_decision": "approved",
            "reviewer": "reviewer@example.com",
            "reviewed_at": "2026-08-31T12:00:00+08:00",
        },
    ]
    review.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    output = tmp_path / "approved.jsonl"
    report = promote_reviewed_aliases(review, output)
    assert report["approved_alias_count"] == 1
    assert report["writes_erpnext"] is False
    promoted = json.loads(output.read_text(encoding="utf-8").strip())
    assert promoted["alias"] == "M12×40螺栓"
    assert promoted["target_id"] == "1001"
    assert report["skipped"]["missing_audit"] == 1
    assert report["skipped"]["negative"] == 1
