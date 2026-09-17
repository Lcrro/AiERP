from __future__ import annotations

import json
from pathlib import Path
import zipfile

from nexterp_agent.item_master.procurement_batch_pilot import (
    ClusterFact,
    ClusterJudgement,
    LlmJsonResult,
    ProcurementBatchPilot,
    ProcurementSourceRow,
    _normalise_fact_row,
    build_clusters,
    load_purchase_workbook,
)
from nexterp_agent.item_master.procurement_templates import ProcurementTemplateRegistry
from nexterp_agent.item_master.reference_catalog import GpcReferenceIndex


def _write_xlsx(path: Path, business_rows: list[list[object]]) -> None:
    rows = [["日期", "材料", "数量", "单位", "工序序号", "市场单价"], *business_rows]
    row_xml = []
    for row_number, values in enumerate(rows, start=1):
        cells = []
        for column_number, value in enumerate(values, start=1):
            column = chr(ord("A") + column_number - 1)
            reference = f"{column}{row_number}"
            if isinstance(value, (int, float)):
                cells.append(f'<c r="{reference}"><v>{value}</v></c>')
            elif value not in (None, ""):
                cells.append(f'<c r="{reference}" t="inlineStr"><is><t>{value}</t></is></c>')
        row_xml.append(f'<row r="{row_number}">{"".join(cells)}</row>')
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", """
            <workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets><sheet name="实际采购清单" sheetId="1" r:id="rId1"/></sheets>
            </workbook>
        """)
        archive.writestr("xl/_rels/workbook.xml.rels", """
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>
            </Relationships>
        """)
        archive.writestr("xl/worksheets/sheet1.xml", f"""
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>{''.join(row_xml)}</sheetData>
            </worksheet>
        """)


def _gpc_index() -> GpcReferenceIndex:
    nodes = [
        {"code": "83000000", "kind": "segment", "level": 0, "name": "建筑产品", "parent_code": ""},
        {"code": "83010000", "kind": "family", "level": 1, "name": "紧固件", "parent_code": "83000000"},
        {"code": "83010100", "kind": "class", "level": 2, "name": "螺纹紧固件", "parent_code": "83010000"},
        {"code": "10003181", "kind": "brick", "level": 3, "name": "Screws", "parent_code": "83010100"},
    ]
    profiles = [{
        "code": "10003181",
        "definition": "Includes products described as a screw.",
        "includes": "Threaded fasteners.",
        "excludes": "Bolts.",
        "attributes": [],
    }]
    translations = [{"code": "10003181", "working_name": "螺丝", "status": "machine"}]
    return GpcReferenceIndex(nodes, profiles, translations)


def _gpc_index_with_cable_ties() -> GpcReferenceIndex:
    nodes = [
        {"code": "78000000", "kind": "segment", "level": 0, "name": "Electrical Supplies", "parent_code": ""},
        {"code": "78040000", "kind": "family", "level": 1, "name": "Cable Management", "parent_code": "78000000"},
        {"code": "78040100", "kind": "class", "level": 2, "name": "Cable Accessories", "parent_code": "78040000"},
        {"code": "10005651", "kind": "brick", "level": 3, "name": "Cable Clips/Grommets/Ties", "parent_code": "78040100"},
        {"code": "10003181", "kind": "brick", "level": 3, "name": "Screws", "parent_code": "78040100"},
    ]
    profiles = [
        {"code": "10005651", "definition": "Cable clips, grommets and ties.", "attributes": []},
        {"code": "10003181", "definition": "Screws.", "attributes": []},
    ]
    translations = [
        {"code": "10005651", "working_name": "电缆夹/护圈/扎带", "status": "machine"},
        {"code": "10003181", "working_name": "螺丝", "status": "machine"},
    ]
    return GpcReferenceIndex(nodes, profiles, translations)


def test_purchase_workbook_reader_preserves_rows_and_flags(tmp_path: Path) -> None:
    source = tmp_path / "采购.xlsx"
    _write_xlsx(source, [
        [44853, "M12x40螺丝", 10, "只", 4, 1.2],
        [44854, "修理电焊机", None, "项", 20, None],
    ])

    snapshot = load_purchase_workbook(source, limit=2)

    assert snapshot.selected_row_count == 2
    assert snapshot.selected_start_row == 2
    assert snapshot.selected_end_row == 3
    assert snapshot.rows[0].purchase_date == "2022-10-19"
    assert snapshot.rows[0].raw_name == "M12x40螺丝"
    assert snapshot.rows[1].flags == [
        "missing_or_invalid_quantity",
        "missing_market_price",
        "service_line",
    ]


def test_clusters_analyse_variants_once_and_merge_golden_rows() -> None:
    rows = [
        ProcurementSourceRow(source_row=2, raw_name="M12x40螺丝", qty=10, raw_uom="只", exact_key="m12x40螺丝", cluster_key="螺丝"),
        ProcurementSourceRow(source_row=3, raw_name="M12x60螺丝", qty=5, raw_uom="只", exact_key="m12x60螺丝", cluster_key="螺丝"),
        ProcurementSourceRow(source_row=4, raw_name="底座叫法A", qty=1, raw_uom="只", exact_key="底座叫法a", cluster_key="底座a"),
        ProcurementSourceRow(source_row=10, raw_name="底座叫法B", qty=1, raw_uom="只", exact_key="底座叫法b", cluster_key="底座b"),
        ProcurementSourceRow(source_row=12, raw_name="底座叫法A", qty=1, raw_uom="只", exact_key="底座叫法a", cluster_key="底座a"),
    ]
    placements = [{"material_id": "MAT-1", "source_rows": [4, 10]}]

    clusters = build_clusters(rows, golden_placements=placements)

    assert len(clusters) == 2
    assert clusters[0].source_rows == [2, 3]
    assert clusters[0].unique_variant_count == 2
    assert clusters[1].source_rows == [4, 10, 12]
    assert clusters[1].golden_material_id == "MAT-1"


def test_gpc_candidate_retrieval_returns_only_real_bricks() -> None:
    rows = _gpc_index().candidate_bricks(["自攻螺丝", "螺丝"], limit=8)

    assert [row["code"] for row in rows] == ["10003181"]
    assert rows[0]["working_name"] == "螺丝"
    assert rows[0]["full_path"][-1]["code"] == "10003181"


def test_procurement_alias_adds_exact_official_gpc_candidate(tmp_path: Path) -> None:
    pilot = ProcurementBatchPilot(
        source_path=tmp_path / "unused.xlsx",
        runtime_root=tmp_path / "runtime",
        gpc_index=_gpc_index_with_cable_ties(),
        registry=ProcurementTemplateRegistry.from_files(),
        placements=[],
    )
    cluster = build_clusters([
        ProcurementSourceRow(
            source_row=2,
            raw_name="尼龙扎带4×200",
            qty=1,
            raw_uom="包",
            exact_key="尼龙扎带4x200",
            cluster_key="尼龙扎带",
        )
    ])[0]

    candidates = pilot._candidates(
        cluster,
        pilot._facts([cluster], use_deepseek=False)[0][cluster.cluster_id],
    )

    assert candidates[0]["code"] == "10005651"


def test_frozen_review_rules_pin_positive_code_and_remove_forbidden_code(tmp_path: Path) -> None:
    nodes = [
        {"code": "83000000", "kind": "segment", "level": 0, "name": "建筑", "parent_code": ""},
        {"code": "83010000", "kind": "family", "level": 1, "name": "管路", "parent_code": "83000000"},
        {"code": "83010100", "kind": "class", "level": 2, "name": "管路件", "parent_code": "83010000"},
        {"code": "10008009", "kind": "brick", "level": 3, "name": "Connectors", "parent_code": "83010100"},
        {"code": "10004024", "kind": "brick", "level": 3, "name": "Valves/Fittings", "parent_code": "83010100"},
        {"code": "10004055", "kind": "brick", "level": 3, "name": "Pumps", "parent_code": "83010100"},
    ]
    index = GpcReferenceIndex(nodes, [
        {"code": "10008009", "definition": "Pipeline connectors."},
        {"code": "10004024", "definition": "Valves regulate flow."},
        {"code": "10004055", "definition": "Water and gas pumps; excludes oil pumps."},
    ], [
        {"code": "10008009", "working_name": "管路连接器"},
        {"code": "10004024", "working_name": "水气阀门"},
        {"code": "10004055", "working_name": "水气泵"},
    ])
    pilot = ProcurementBatchPilot(
        source_path=tmp_path / "unused.xlsx",
        runtime_root=tmp_path / "runtime",
        gpc_index=index,
        registry=ProcurementTemplateRegistry.from_files(),
        placements=[],
    )

    def candidates(name: str, standard_type: str) -> list[str]:
        cluster = build_clusters([
            ProcurementSourceRow(
                source_row=2, raw_name=name, qty=1, raw_uom="件",
                exact_key=name, cluster_key=name,
            )
        ])[0]
        fact = ClusterFact(
            cluster_id=cluster.cluster_id,
            standard_query=standard_type,
            standard_type=standard_type,
        )
        return [row["code"] for row in pilot._candidates(cluster, fact)]

    assert candidates("PPRΦ110弯头", "PPR弯头")[0] == "10008009"
    assert "10004055" not in candidates("抽油机", "抽油泵")


def test_model_cannot_turn_fabricated_stock_into_service_and_values_are_normalised() -> None:
    cluster = build_clusters([
        ProcurementSourceRow(
            source_row=2,
            raw_name="加工40x40角铁1.5米",
            qty=1,
            raw_uom="根",
            exact_key="加工40x40角铁1.5米",
            cluster_key="加工角铁",
        )
    ])[0]

    fact = _normalise_fact_row({
        "cluster_id": cluster.cluster_id,
        "standard_query": "角铁",
        "standard_type": "加工角铁",
        "explicit_facts": {"是否加工": True, "规格": ["40x40", "1.5米"]},
        "search_synonyms": [],
        "is_service": True,
        "is_bundled_line": False,
    }, cluster)

    assert fact is not None
    assert fact.is_service is False
    assert fact.explicit_facts == {"是否加工": "是", "规格": "40x40/1.5米"}


def test_low_rank_medium_confidence_candidate_requires_review(tmp_path: Path) -> None:
    pilot = ProcurementBatchPilot(
        source_path=tmp_path / "unused.xlsx",
        runtime_root=tmp_path / "runtime",
        gpc_index=_gpc_index(),
        registry=ProcurementTemplateRegistry.from_files(),
        placements=[],
    )
    cluster = build_clusters([
        ProcurementSourceRow(
            source_row=2, raw_name="智能变频调速器", qty=1, raw_uom="台",
            exact_key="智能变频调速器", cluster_key="智能变频调速器",
        )
    ])[0]
    fact = ClusterFact(cluster_id=cluster.cluster_id, standard_query="变频器", standard_type="变频器")
    candidates = [
        {"code": str(index), "working_name": f"候选{index}", "official_name": ""}
        for index in range(1, 9)
    ]
    judgement = ClusterJudgement(
        cluster_id=cluster.cluster_id,
        selected_gpc_code="8",
        standard_type="变频器",
        main_template_id="equipment_tool",
        confidence="medium",
        reason="低排名候选",
    )

    decision = pilot._decision(cluster, fact, candidates, judgement)

    assert decision["queue"] == "needs_review"
    assert decision["selected_candidate_rank"] == 8


def test_batch_pilot_constrains_model_and_writes_local_review_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "采购.xlsx"
    _write_xlsx(source, [
        [44853, "M12x40螺丝", 10, "只", 4, 1.2],
        [44854, "M12x60螺丝", 5, "只", 4, 1.5],
        [44855, "修理电焊机", 1, "项", 20, None],
    ])
    registry = ProcurementTemplateRegistry.from_files()
    calls = []

    def fake_deepseek(messages: list[dict[str, str]], max_tokens: int) -> LlmJsonResult:
        payload = json.loads(messages[1]["content"])
        calls.append((messages[0]["content"], max_tokens, payload))
        if "事实整理员" in messages[0]["content"]:
            rows = []
            for cluster in payload["clusters"]:
                is_service = "修理" in cluster["representative_name"]
                rows.append({
                    "cluster_id": cluster["cluster_id"],
                    "standard_query": "电焊机维修" if is_service else "螺丝",
                    "standard_type": "电焊机维修服务" if is_service else "螺丝",
                    "explicit_facts": {} if is_service else {"规格": "M12"},
                    "search_synonyms": [],
                    "is_service": is_service,
                    "is_bundled_line": False,
                    "ambiguity_note": "",
                })
        else:
            rows = [{
                "cluster_id": cluster["cluster_id"],
                "selected_gpc_code": "10003181",
                "standard_type": "螺丝",
                "main_template_id": "standard_component",
                "constraint_ids": [],
                "sku_identity_fact_keys": ["规格"],
                "transaction_fact_keys": [],
                "offer_fact_keys": [],
                "stock_uom": "件",
                "confidence": "high",
                "reason": "候选定义与原文一致",
                "questions": [],
            } for cluster in payload["clusters"]]
        return LlmJsonResult(
            data={"rows": rows},
            model="deepseek-test",
            usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
            request_id=f"req-{len(calls)}",
        )

    pilot = ProcurementBatchPilot(
        source_path=source,
        runtime_root=tmp_path / "runtime",
        gpc_index=_gpc_index(),
        registry=registry,
        placements=[],
        deepseek_client=fake_deepseek,
        llm_chunk_size=50,
    )

    result = pilot.run(limit=3, job_id="pilot-test")

    assert result["audit"]["row_count"] == 3
    assert result["audit"]["cluster_count"] == 2
    assert result["audit"]["deepseek"]["call_count"] == 2
    assert result["audit"]["deepseek"]["usage"]["total_tokens"] == 240
    assert result["audit"]["writes_erpnext"] is False
    assert {row["queue"] for row in result["decisions"]} == {"ready_new_type", "excluded_non_material"}
    material = next(row["material_candidate"] for row in result["decisions"] if row["queue"] == "ready_new_type")
    assert material["gpc_brick_code"] == "10003181"
    assert material["material_name"] == "螺丝｜M12"
    job_dir = tmp_path / "runtime" / "jobs" / "pilot-test"
    assert (job_dir / "source-rows.jsonl").is_file()
    assert (job_dir / "deepseek-calls.jsonl").is_file()
    assert (job_dir / "prompt-manifest.json").is_file()
    assert len(calls) == 2


def test_batch_pilot_rejects_model_invented_gpc_code(tmp_path: Path) -> None:
    source = tmp_path / "采购.xlsx"
    _write_xlsx(source, [[44853, "M12x40螺丝", 10, "只", 4, 1.2]])

    def fake_deepseek(messages: list[dict[str, str]], _max_tokens: int) -> LlmJsonResult:
        payload = json.loads(messages[1]["content"])
        if "事实整理员" in messages[0]["content"]:
            row = payload["clusters"][0]
            data = {"rows": [{
                "cluster_id": row["cluster_id"], "standard_query": "螺丝", "standard_type": "螺丝",
                "explicit_facts": {"规格": "M12"}, "search_synonyms": [], "is_service": False,
                "is_bundled_line": False, "ambiguity_note": "",
            }]}
        else:
            row = payload["clusters"][0]
            data = {"rows": [{
                "cluster_id": row["cluster_id"], "selected_gpc_code": "99999999", "standard_type": "螺丝",
                "main_template_id": "standard_component", "constraint_ids": [],
                "sku_identity_fact_keys": ["规格"], "transaction_fact_keys": [], "offer_fact_keys": [],
                "stock_uom": "件", "confidence": "high", "reason": "bad", "questions": [],
            }]}
        return LlmJsonResult(data=data, model="test", usage={})

    pilot = ProcurementBatchPilot(
        source_path=source,
        runtime_root=tmp_path / "runtime",
        gpc_index=_gpc_index(),
        registry=ProcurementTemplateRegistry.from_files(),
        placements=[],
        deepseek_client=fake_deepseek,
    )

    result = pilot.run(limit=1, job_id="bad-code")

    assert result["decisions"][0]["queue"] == "needs_review"
    assert result["decisions"][0]["gpc_brick_code"] == ""
    assert result["audit"]["model_error_count"] == 1
    assert "候选集合外" in result["audit"]["model_errors"][0]["error"]


def test_batch_pilot_retries_only_rows_missing_from_model_response(tmp_path: Path) -> None:
    source = tmp_path / "采购.xlsx"
    _write_xlsx(source, [
        [44853, "M12螺丝", 10, "只", 4, 1.2],
        [44854, "自攻螺丝", 5, "只", 4, 1.5],
    ])
    fact_call_sizes: list[int] = []
    judgement_call_sizes: list[int] = []

    def fake_deepseek(messages: list[dict[str, str]], _max_tokens: int) -> LlmJsonResult:
        payload = json.loads(messages[1]["content"])
        clusters = payload["clusters"]
        if "事实整理员" in messages[0]["content"]:
            fact_call_sizes.append(len(clusters))
            returned = clusters[:1] if len(clusters) > 1 else clusters
            rows = [{
                "cluster_id": row["cluster_id"], "standard_query": "螺丝", "standard_type": "螺丝",
                "explicit_facts": {"规格": "M12"}, "search_synonyms": [], "is_service": False,
                "is_bundled_line": False, "ambiguity_note": "",
            } for row in returned]
        else:
            judgement_call_sizes.append(len(clusters))
            rows = [{
                "cluster_id": row["cluster_id"], "selected_gpc_code": "10003181", "standard_type": "螺丝",
                "main_template_id": "standard_component", "constraint_ids": [],
                "sku_identity_fact_keys": ["规格"], "transaction_fact_keys": [], "offer_fact_keys": [],
                "stock_uom": "件", "confidence": "high", "reason": "匹配", "questions": [],
            } for row in clusters]
            if len(rows) > 1:
                rows[1]["selected_gpc_code"] = "99999999"
        return LlmJsonResult(data={"rows": rows}, model="test", usage={})

    result = ProcurementBatchPilot(
        source_path=source,
        runtime_root=tmp_path / "runtime",
        gpc_index=_gpc_index(),
        registry=ProcurementTemplateRegistry.from_files(),
        placements=[],
        deepseek_client=fake_deepseek,
        llm_chunk_size=50,
    ).run(limit=2, job_id="partial-retry")

    assert fact_call_sizes == [2, 1]
    assert judgement_call_sizes == [2, 1]
    assert result["audit"]["model_error_count"] == 0
