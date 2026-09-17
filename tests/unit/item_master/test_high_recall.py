from __future__ import annotations

from pathlib import Path

from nexterp_agent.item_master.batch_intake import (
    BatchFactExtraction,
    ExtractedMaterialFacts,
    MaterialIntakeRow,
)
from nexterp_agent.item_master.high_recall import (
    BatchMaterialJudgement,
    HighRecallBatchMaterialIntakeAnalyzer,
    HighRecallCandidate,
    HighRecallMaterialRetriever,
    MaterialBatchJudgement,
    RetrievalResult,
)
from nexterp_agent.item_master.runtime_aliases import RuntimeAliasStore


def test_dynamic_threshold_is_more_permissive_for_vague_queries() -> None:
    assert HighRecallMaterialRetriever.dynamic_threshold("二保焊枪", {}) == 50
    assert HighRecallMaterialRetriever.dynamic_threshold("二保焊枪", {"model": "500A"}) == 65
    assert HighRecallMaterialRetriever.dynamic_threshold("二保焊枪", {"model": "500A", "length": "6m"}) == 80


def test_retriever_keeps_all_candidates_above_threshold() -> None:
    retriever = HighRecallMaterialRetriever()
    result = retriever.retrieve("钻头", attributes={})

    assert result.candidates
    assert result.all_candidate_count == len(result.candidates)
    assert all(candidate.score >= result.threshold for candidate in result.candidates) or result.reference_only
    assert result.candidate_groups
    assert all(len(group.representative_candidates) <= 3 for group in result.candidate_groups)


def test_exact_sku_name_clears_low_recall_threshold() -> None:
    retriever = HighRecallMaterialRetriever()
    result = retriever.retrieve("垃圾袋 120*140cm")

    assert result.threshold == 65
    assert result.candidates
    assert any(candidate.candidate_kind == "sku" for candidate in result.candidates)
    assert max(candidate.score for candidate in result.candidates) >= 65


def test_batch_analyzer_extracts_and_judges_once() -> None:
    fact_calls: list[int] = []
    judge_calls: list[int] = []

    def facts(rows: list[MaterialIntakeRow]) -> BatchFactExtraction:
        fact_calls.append(len(rows))
        return BatchFactExtraction(rows=[
            ExtractedMaterialFacts(row_id=row.row_id, query=row.raw_name, attributes={})
            for row in rows
        ])

    def judge(payload: list[dict[str, object]]) -> BatchMaterialJudgement:
        judge_calls.append(len(payload))
        return BatchMaterialJudgement(rows=[
            MaterialBatchJudgement(row_id=str(item["row_id"]), decision="needs_input", reason="等待选择")
            for item in payload
        ])

    rows = [
        MaterialIntakeRow(row_id="1", raw_name="帆布手套", qty=10, uom="双"),
        MaterialIntakeRow(row_id="2", raw_name="活动扳手", raw_spec="12寸", qty=1, uom="把"),
    ]
    result = HighRecallBatchMaterialIntakeAnalyzer(fact_extractor=facts, judge=judge).analyze(rows)

    assert fact_calls == [2]
    assert judge_calls == [2]
    assert result.writes_erpnext is False
    assert [step.stage for step in result.processing_trace] == [
        "read", "extract", "retrieve", "compress", "judge", "validate", "queue"
    ]
    assert all(item.candidate_count >= 0 for item in result.decisions)


def test_batch_analyzer_uses_twenty_row_blocks() -> None:
    fact_calls: list[int] = []
    judge_calls: list[int] = []

    def facts(rows: list[MaterialIntakeRow]) -> BatchFactExtraction:
        fact_calls.append(len(rows))
        return BatchFactExtraction(rows=[
            ExtractedMaterialFacts(row_id=row.row_id, query=row.raw_name, attributes={})
            for row in rows
        ])

    def judge(payload: list[dict[str, object]]) -> BatchMaterialJudgement:
        judge_calls.append(len(payload))
        return BatchMaterialJudgement(rows=[
            MaterialBatchJudgement(row_id=str(item["row_id"]), decision="needs_input", reason="等待选择")
            for item in payload
        ])

    rows = [MaterialIntakeRow(row_id=str(index), raw_name="帆布手套", qty=1, uom="双") for index in range(21)]
    result = HighRecallBatchMaterialIntakeAnalyzer(fact_extractor=facts, judge=judge).analyze(rows)

    assert sorted(fact_calls) == [1, 20]
    assert sorted(judge_calls) == [1, 20]
    assert result.total_rows == 21
    assert "分为 2 个处理块" in result.processing_trace[3].details[0]


def test_confirmed_alias_is_persisted_separately_from_analysis(tmp_path: Path) -> None:
    store = RuntimeAliasStore(tmp_path / "aliases.jsonl")
    row = store.confirm(
        alias="二保焊枪",
        target_kind="type",
        target_id="MT-TEST",
        user="tester@example.com",
        source_row="7",
    )

    assert row["enabled"] is True
    assert row["target_kind"] == "type"
    assert row["target_id"] == "MT-TEST"
    assert store.active()[0]["alias"] == "二保焊枪"


def test_strict_current_candidate_cannot_be_selected_by_batch_judge() -> None:
    candidate = HighRecallCandidate(
        candidate_kind="sku",
        item_code="1001",
        standard_name="六角螺栓",
        sku_name="六角螺栓 M12×40",
        score=95,
        strict_matching=True,
        exact_code_match=False,
        approved_alias_match=False,
        required_specs_match=False,
        auto_selectable=False,
    )
    retrieval = RetrievalResult(threshold=50, candidates=[candidate], all_candidate_count=1)
    judgement = MaterialBatchJudgement(
        row_id="1",
        decision="existing_sku",
        selected_item_code="1001",
        reason="模型选择",
    )
    validation = HighRecallBatchMaterialIntakeAnalyzer._validate(judgement, retrieval)
    assert validation["queue"] == "needs_input"
    assert validation["errors"] == ["strict_auto_select_gate"]
