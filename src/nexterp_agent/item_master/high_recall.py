from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field

from .batch_intake import (
    BatchFactExtraction,
    ExtractedMaterialFacts,
    MaterialIntakeDecision,
    MaterialIntakeRow,
    MaterialIntakeTraceStep,
    _elapsed_ms,
    extract_material_facts_with_deepseek,
)
from .release_resolver import (
    DEFAULT_RELEASE_CATALOG_PATH,
    ReleaseMaterialResolver,
    normalize_spec_text,
    normalize_text,
    score_release_row,
    split_terms,
)
from .runtime_aliases import RuntimeAliasStore
from .type_classifier import MaterialTypeClassifier


class HighRecallCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_kind: Literal["type", "sku"]
    type_id: str = ""
    item_code: str = ""
    standard_name: str = ""
    item_name: str = ""
    sku_name: str = ""
    score: int = Field(ge=0, le=100)
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    matched_aliases: list[str] = Field(default_factory=list)
    matched_attributes: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    match_reasons: list[str] = Field(default_factory=list)
    required_specs: str = ""
    stock_uom: str = ""


class CandidateGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_key: str
    candidate_kind: Literal["type", "sku"]
    type_id: str = ""
    standard_name: str = ""
    count: int = Field(ge=1)
    score_min: int = Field(ge=0, le=100)
    score_max: int = Field(ge=0, le=100)
    conflict_count: int = 0
    representative_candidates: list[HighRecallCandidate] = Field(default_factory=list, max_length=3)


class MaterialBatchJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_id: str
    decision: Literal["existing_sku", "new_sku", "new_type", "needs_input"]
    selected_type_id: str = ""
    selected_item_code: str = ""
    reason: str = ""
    confirmed_attributes: dict[str, str] = Field(default_factory=dict)
    conflicts: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


class BatchMaterialJudgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: list[MaterialBatchJudgement] = Field(default_factory=list, max_length=50)


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    threshold: int = Field(ge=0, le=100)
    candidates: list[HighRecallCandidate] = Field(default_factory=list)
    candidate_groups: list[CandidateGroup] = Field(default_factory=list)
    all_candidate_count: int = 0
    reference_only: bool = False


class HighRecallBatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["completed"] = "completed"
    writes_erpnext: bool = False
    total_rows: int
    queue_counts: dict[str, int]
    decisions: list[MaterialIntakeDecision]
    processing_trace: list[MaterialIntakeTraceStep] = Field(default_factory=list)
    deepseek_judgement_error: str = ""


class HighRecallMaterialRetriever:
    """Recall types and SKUs independently, then keep the full local result."""

    def __init__(
        self,
        classifier: MaterialTypeClassifier | None = None,
        *,
        alias_store: RuntimeAliasStore | None = None,
    ) -> None:
        self.classifier = classifier or MaterialTypeClassifier()
        self.resolver: ReleaseMaterialResolver = self.classifier.release_resolver
        self.alias_store = alias_store or RuntimeAliasStore()
        self.type_by_id = {item.type_id: item for item in self.classifier.types}

    def retrieve(
        self,
        query: str,
        *,
        attributes: dict[str, Any] | None = None,
        top_group_hint: str = "",
        material_family_hint: str = "",
    ) -> RetrievalResult:
        query = str(query or "").strip()
        attributes = {str(k): str(v) for k, v in (attributes or {}).items() if v not in (None, "")}
        threshold = self.dynamic_threshold(query, attributes)
        # Load confirmed aliases once for this row. This is request-local data,
        # not a candidate cache, and avoids one file read per catalog entry.
        runtime_aliases = self.alias_store.active()
        type_candidates = self._retrieve_types(query, attributes, top_group_hint, material_family_hint, runtime_aliases)
        sku_candidates = self._retrieve_skus(query, attributes, runtime_aliases)
        all_candidates = sorted(
            [*type_candidates, *sku_candidates],
            key=lambda candidate: (-candidate.score, candidate.candidate_kind, candidate.standard_name or candidate.sku_name),
        )
        selected = [candidate for candidate in all_candidates if candidate.score >= threshold]
        reference_only = False
        if not selected:
            selected = all_candidates[:3]
            reference_only = bool(selected)
        return RetrievalResult(
            threshold=threshold,
            candidates=selected,
            candidate_groups=self._group_candidates(selected),
            all_candidate_count=len(selected),
            reference_only=reference_only,
        )

    @staticmethod
    def dynamic_threshold(query: str, attributes: dict[str, Any]) -> int:
        normalized = normalize_text(query)
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{4,}", normalized):
            return 80
        explicit = [value for key, value in attributes.items() if key not in {"uom", "unit"} and value]
        if len(explicit) >= 2:
            return 80
        if explicit or re.search(r"\d", query):
            return 65
        return 50

    def _retrieve_types(
        self,
        query: str,
        attributes: dict[str, Any],
        top_group_hint: str,
        material_family_hint: str,
        runtime_aliases: list[dict[str, Any]],
    ) -> list[HighRecallCandidate]:
        output: list[HighRecallCandidate] = []
        for item in self.classifier.types:
            scored = self.classifier._score_type(
                item,
                query,
                top_group_hint=top_group_hint,
                material_family_hint=material_family_hint,
            )
            alias_hits = self._alias_hits(query, "type", item.type_id, runtime_aliases)
            if alias_hits:
                scored.score += 45 * len(alias_hits)
                scored.match_reasons.append("用户确认别名命中")
            normalized_score = min(100, max(0, round(scored.score / 2.2)))
            if normalized_score <= 0:
                continue
            matched_attributes = [
                key for key, value in attributes.items()
                if value and normalize_text(str(value)) in normalize_text(item.definition + item.includes)
            ]
            output.append(HighRecallCandidate(
                candidate_kind="type",
                type_id=item.type_id,
                standard_name=item.standard_name,
                score=normalized_score,
                score_breakdown=self._breakdown(scored.match_reasons, normalized_score),
                matched_aliases=alias_hits,
                matched_attributes=matched_attributes,
                match_reasons=list(scored.match_reasons),
                required_specs="；".join(
                    str(attr.get("display_name") or attr.get("attribute_key") or "")
                    for attr in item.attributes
                    if attr.get("requirement") == "required"
                ),
            ))
        return output

    def _retrieve_skus(
        self,
        query: str,
        attributes: dict[str, Any],
        runtime_aliases: list[dict[str, Any]],
    ) -> list[HighRecallCandidate]:
        output: list[HighRecallCandidate] = []
        for row in self.resolver.rows:
            scored = score_release_row(row, query, attributes)
            if scored.score <= 0:
                continue
            code = str(row.get("item_code") or "")
            type_id = self.classifier.sku_type_ids.get(code, "")
            aliases = split_terms(row.get("aliases", ""))
            alias_hits = [alias for alias in aliases if self._text_matches(query, alias)]
            alias_hits.extend(self._alias_hits(query, "sku", code, runtime_aliases))
            haystack = normalize_spec_text(
                " ".join(row.get(key, "") for key in ("sku_name", "required_specs", "optional_specs", "model", "brand"))
            )
            matched_attributes = [
                key for key, value in attributes.items()
                if key not in {"uom", "unit"} and normalize_spec_text(value) in haystack
            ]
            conflicts = [
                f"{key}={value} 未在该 SKU 规格中命中"
                for key, value in attributes.items()
                if key not in {"uom", "unit"} and normalize_spec_text(value) not in haystack
            ]
            # ReleaseMaterialCandidate is frozen; keep its source score intact
            # and derive the runtime-alias score separately.
            adjusted_score = scored.score + (45 * len(alias_hits))
            # SKU scoring has a smaller base scale than type scoring. An exact
            # item name is intentionally strong enough to clear the 50-point
            # low-recall floor, while code/exact multi-attribute matches still
            # saturate at 100.
            normalized_score = min(100, max(0, round(adjusted_score / 1.1)))
            output.append(HighRecallCandidate(
                candidate_kind="sku",
                type_id=type_id,
                item_code=code,
                standard_name=self.type_by_id.get(type_id).standard_name if type_id in self.type_by_id else row.get("item_name", ""),
                item_name=row.get("item_name", ""),
                sku_name=row.get("sku_name", ""),
                score=normalized_score,
                score_breakdown=self._breakdown(scored.match_reasons, normalized_score, alias_hits, matched_attributes),
                matched_aliases=list(dict.fromkeys(alias_hits)),
                matched_attributes=matched_attributes,
                conflicts=conflicts,
                match_reasons=list(scored.match_reasons),
                required_specs=row.get("required_specs", ""),
                stock_uom=row.get("stock_uom", ""),
            ))
        return output

    def _alias_hits(
        self,
        query: str,
        target_kind: str,
        target_id: str,
        runtime_aliases: list[dict[str, Any]],
    ) -> list[str]:
        normalized_query = normalize_text(query)
        return [
            str(row.get("alias") or "")
            for row in runtime_aliases
            if row.get("target_kind") == target_kind
            and row.get("target_id") == target_id
            and row.get("normalized_alias") == normalized_query
        ]

    @staticmethod
    def _text_matches(query: str, value: str) -> bool:
        query_norm = normalize_text(query)
        value_norm = normalize_text(value)
        return bool(query_norm and value_norm and (query_norm == value_norm or query_norm in value_norm or value_norm in query_norm))

    @staticmethod
    def _breakdown(
        reasons: list[str],
        total: int,
        aliases: list[str] | None = None,
        attributes: list[str] | None = None,
    ) -> dict[str, int]:
        aliases = aliases or []
        attributes = attributes or []
        alias_score = min(35, len(aliases) * 30)
        attribute_score = min(40, len(attributes) * 20)
        name_score = max(0, total - alias_score - attribute_score)
        if any("精确" in reason for reason in reasons):
            name_score = max(name_score, 35)
        return {"name": min(45, name_score), "alias": alias_score, "attributes": attribute_score}

    @staticmethod
    def _group_candidates(candidates: list[HighRecallCandidate]) -> list[CandidateGroup]:
        grouped: dict[tuple[str, str], list[HighRecallCandidate]] = {}
        for candidate in candidates:
            key = (candidate.candidate_kind, candidate.type_id or candidate.item_code)
            grouped.setdefault(key, []).append(candidate)
        result: list[CandidateGroup] = []
        for (kind, key), items in grouped.items():
            items = sorted(items, key=lambda item: -item.score)
            first = items[0]
            result.append(CandidateGroup(
                group_key=key,
                candidate_kind=kind,  # type: ignore[arg-type]
                type_id=first.type_id,
                standard_name=first.standard_name,
                count=len(items),
                score_min=min(item.score for item in items),
                score_max=max(item.score for item in items),
                conflict_count=sum(bool(item.conflicts) for item in items),
                representative_candidates=items[:3],
            ))
        return sorted(result, key=lambda item: (-item.score_max, item.standard_name))


JudgeFunction = Callable[[list[dict[str, Any]]], BatchMaterialJudgement]


class HighRecallBatchMaterialIntakeAnalyzer:
    """v0.6 batch path: one extraction, local high-recall retrieval, one judge."""

    def __init__(
        self,
        classifier: MaterialTypeClassifier | None = None,
        *,
        fact_extractor: Callable[[list[MaterialIntakeRow]], BatchFactExtraction] | None = None,
        judge: JudgeFunction | None = None,
        retriever: HighRecallMaterialRetriever | None = None,
    ) -> None:
        self.classifier = classifier or MaterialTypeClassifier()
        self.retriever = retriever or HighRecallMaterialRetriever(self.classifier)
        self.fact_extractor = fact_extractor or extract_material_facts_with_deepseek
        self.judge = judge or judge_material_intake_with_deepseek

    def analyze(self, rows: list[MaterialIntakeRow]) -> HighRecallBatchResult:
        if not rows:
            raise ValueError("采购清单不能为空")
        if len(rows) > 50:
            raise ValueError("首版每批最多分析 50 行")
        row_ids = [row.row_id for row in rows]
        if len(set(row_ids)) != len(row_ids):
            raise ValueError("row_id 必须唯一")
        trace: list[MaterialIntakeTraceStep] = [MaterialIntakeTraceStep(
            stage="read", title="读取采购清单", status="completed", input_rows=len(rows), output_rows=len(rows),
            details=["保留原始名称、规格、数量和单位；数量与单位不交给模型改写。"],
        )]
        chunks = [rows[index:index + 20] for index in range(0, len(rows), 20)]
        started = perf_counter()
        if len(chunks) == 1:
            extracted_chunks = [self.fact_extractor(chunks[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(3, len(chunks))) as executor:
                extracted_chunks = list(executor.map(self.fact_extractor, chunks))
        extracted = BatchFactExtraction(rows=[
            item
            for chunk in extracted_chunks
            for item in chunk.rows
        ])
        facts_by_id = {item.row_id: item for item in extracted.rows}
        if set(facts_by_id) != set(row_ids):
            missing = sorted(set(row_ids) - set(facts_by_id))
            extra = sorted(set(facts_by_id) - set(row_ids))
            raise ValueError(f"DeepSeek 返回行不完整，missing={missing}, extra={extra}")
        trace.append(MaterialIntakeTraceStep(
            stage="extract", title="DeepSeek 一次提取整批现场事实", status="completed",
            input_rows=len(rows), output_rows=len(extracted.rows), duration_ms=_elapsed_ms(started),
            details=[f"一次提取 {len(extracted.rows)} 行；数量和采购单位仍采用原始清单。"],
        ))
        started = perf_counter()

        def retrieve_chunk(chunk: list[MaterialIntakeRow]) -> dict[str, RetrievalResult]:
            with ThreadPoolExecutor(max_workers=min(3, len(chunk))) as executor:
                futures = {
                    row.row_id: executor.submit(self._retrieve_one, row, facts_by_id[row.row_id])
                    for row in chunk
                }
                return {row_id: future.result() for row_id, future in futures.items()}

        if len(chunks) == 1:
            retrieval_chunks = [retrieve_chunk(chunks[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(3, len(chunks))) as executor:
                retrieval_chunks = list(executor.map(retrieve_chunk, chunks))
        retrieval_by_id = {
            row_id: retrieval
            for chunk_result in retrieval_chunks
            for row_id, retrieval in chunk_result.items()
        }
        total_candidates = sum(item.all_candidate_count for item in retrieval_by_id.values())
        trace.append(MaterialIntakeTraceStep(
            stage="retrieve", title="并行召回标准类型和全部相关 SKU", status="completed",
            input_rows=len(rows), output_rows=total_candidates, duration_ms=_elapsed_ms(started),
            details=["每行独立检索，不先锁定单一类型；候选按本行动态门槛保留。"],
        ))
        compressed_payloads = [
            _judgement_payload(chunk, facts_by_id, retrieval_by_id)
            for chunk in chunks
        ]
        compressed_groups = sum(len(item.candidate_groups) for item in retrieval_by_id.values())
        trace.append(MaterialIntakeTraceStep(
            stage="compress", title="压缩候选上下文但保留完整服务端结果", status="completed",
            input_rows=len(rows), output_rows=compressed_groups,
            details=[f"分为 {len(chunks)} 个处理块；候选不超过 20 项时完整提供，超过 20 项时按类型和规格差异分组，每组提供 3 个代表。"],
        ))
        started = perf_counter()
        def judge_chunk(payload: list[dict[str, Any]]) -> tuple[BatchMaterialJudgement, str]:
            try:
                return self.judge(payload), ""
            except Exception as exc:  # retrieval remains useful when DeepSeek judge fails
                return BatchMaterialJudgement(rows=[]), str(exc)

        if len(compressed_payloads) == 1:
            judgement_chunks = [judge_chunk(compressed_payloads[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(3, len(compressed_payloads))) as executor:
                judgement_chunks = list(executor.map(judge_chunk, compressed_payloads))
        by_id = {
            item.row_id: item
            for judgement, _error in judgement_chunks
            for item in judgement.rows
        }
        judge_errors_by_id = {
            row.row_id: error
            for chunk, (_judgement, error) in zip(chunks, judgement_chunks)
            if error
            for row in chunk
        }
        judge_errors = list(dict.fromkeys(judge_errors_by_id.values()))
        trace.append(MaterialIntakeTraceStep(
            stage="judge", title="DeepSeek 按块比较整批候选",
            status="failed" if len(judge_errors_by_id) == len(rows) else "partial" if judge_errors_by_id else "completed",
            input_rows=len(rows), output_rows=len(by_id), duration_ms=_elapsed_ms(started),
            details=[f"调用 {len(compressed_payloads)} 次；模型只比较服务端召回的真实候选，不接收或生成 ERPNext 编码。", *judge_errors],
        ))
        started = perf_counter()
        decisions = [self._decision(
            row, facts_by_id[row.row_id], retrieval_by_id[row.row_id], by_id.get(row.row_id), judge_errors_by_id.get(row.row_id, "")
        ) for row in rows]
        trace.append(MaterialIntakeTraceStep(
            stage="validate", title="程序复核判定与真实规格", status="partial" if judge_errors_by_id else "completed",
            input_rows=len(rows), output_rows=sum(item.queue != "needs_input" for item in decisions), duration_ms=_elapsed_ms(started),
            details=["已有 SKU 必须通过输入规格复核；无效或越权编码自动降为需要选择。"],
        ))
        counts = {key: sum(item.queue == key for item in decisions) for key in ("existing_sku", "new_sku", "new_type", "needs_input")}
        trace.append(MaterialIntakeTraceStep(
            stage="queue", title="生成准入结论", status="completed", input_rows=len(rows), output_rows=len(decisions),
            details=[f"已有 SKU {counts['existing_sku']} 行；现有类型新增 SKU {counts['new_sku']} 行；新增标准类型 {counts['new_type']} 行；需要补充或选择 {counts['needs_input']} 行。", "分析阶段未写入 ERPNext。"],
        ))
        return HighRecallBatchResult(
            total_rows=len(rows), queue_counts=counts, decisions=decisions,
            processing_trace=trace, deepseek_judgement_error="; ".join(judge_errors),
        )

    def _retrieve_one(self, row: MaterialIntakeRow, facts: ExtractedMaterialFacts) -> RetrievalResult:
        attrs = dict(facts.attributes)
        attrs.setdefault("uom", row.uom)
        query = " ".join(value for value in (row.raw_name, row.raw_spec, facts.query) if value)
        return self.retriever.retrieve(query, attributes=attrs, top_group_hint=facts.top_group_hint, material_family_hint=facts.material_family_hint)

    def _decision(
        self,
        row: MaterialIntakeRow,
        facts: ExtractedMaterialFacts,
        retrieval: RetrievalResult,
        judgement: MaterialBatchJudgement | None,
        judge_error: str,
    ) -> MaterialIntakeDecision:
        candidates = [candidate.model_dump(mode="json") for candidate in retrieval.candidates]
        selected_type = next((candidate for candidate in retrieval.candidates if candidate.candidate_kind == "type" and candidate.type_id == (judgement.selected_type_id if judgement else "")), None)
        selected_sku = next((candidate for candidate in retrieval.candidates if candidate.candidate_kind == "sku" and candidate.item_code == (judgement.selected_item_code if judgement else "")), None)
        validation = self._validate(judgement, retrieval)
        queue = validation["queue"]
        reason = validation["reason"] or (judge_error or (judgement.reason if judgement else "候选已召回，等待 DeepSeek 判定。"))
        questions = list(judgement.questions if judgement else [])
        if not questions and queue == "needs_input":
            questions = ["已列出候选，请选择具体 SKU，或确认按现有物料类型新增规格。"]
        type_candidate = selected_type or next((candidate for candidate in retrieval.candidates if candidate.candidate_kind == "type"), None)
        sku_candidate = selected_sku
        attrs = dict(facts.attributes)
        attrs.setdefault("uom", row.uom)
        return MaterialIntakeDecision(
            row_id=row.row_id, raw_name=row.raw_name, raw_spec=row.raw_spec, qty=row.qty, uom=row.uom,
            queue=queue, queue_label={"existing_sku": "已有 SKU", "new_sku": "现有类型新增 SKU", "new_type": "需要新增标准类型", "needs_input": "需要补充或选择"}[queue],
            standard_name=(type_candidate.standard_name if type_candidate else ""), type_id=(type_candidate.type_id if type_candidate else ""),
            item_code=(sku_candidate.item_code if sku_candidate else ""), sku_name=(sku_candidate.sku_name if sku_candidate else ""),
            normalized_attributes={**attrs, **(judgement.confirmed_attributes if judgement else {})},
            attribute_sources={key: "现场输入" for key in attrs} | ({key: "DeepSeek判定" for key in (judgement.confirmed_attributes if judgement else {})}),
            candidates=candidates, questions=questions, reason=reason, ambiguity_note=facts.ambiguity_note,
            retrieval_threshold=retrieval.threshold, candidate_count=retrieval.all_candidate_count,
            candidate_groups=[group.model_dump(mode="json") for group in retrieval.candidate_groups],
            deepseek_judgement=(judgement.model_dump(mode="json") if judgement else {}),
            program_validation=validation,
            alias_learning={"status": "not_written", "message": "别名只有在用户明确确认候选后才会写入。"},
        )

    @staticmethod
    def _validate(judgement: MaterialBatchJudgement | None, retrieval: RetrievalResult) -> dict[str, Any]:
        if judgement is None:
            return {"valid": False, "queue": "needs_input", "reason": "没有得到 DeepSeek 判定，保留候选等待重试。", "errors": ["judge_missing"]}
        type_ids = {item.type_id for item in retrieval.candidates if item.candidate_kind == "type"}
        sku_by_code = {item.item_code: item for item in retrieval.candidates if item.candidate_kind == "sku"}
        if judgement.decision == "existing_sku":
            candidate = sku_by_code.get(judgement.selected_item_code)
            if not candidate:
                return {"valid": False, "queue": "needs_input", "reason": "模型选择的 SKU 不在本行真实候选中。", "errors": ["unknown_item_code"]}
            if candidate.conflicts:
                return {"valid": False, "queue": "needs_input", "reason": "候选 SKU 与现场关键规格冲突，不能直接复用。", "errors": candidate.conflicts}
            return {"valid": True, "queue": "existing_sku", "reason": judgement.reason, "errors": []}
        if judgement.decision == "new_sku":
            if not judgement.selected_type_id or judgement.selected_type_id not in type_ids:
                return {"valid": False, "queue": "needs_input", "reason": "新增 SKU 必须引用本行召回的真实标准类型。", "errors": ["unknown_type_id"]}
            return {"valid": True, "queue": "new_sku", "reason": judgement.reason, "errors": []}
        if judgement.decision == "new_type":
            if type_ids:
                return {"valid": False, "queue": "needs_input", "reason": "已有标准类型候选，不能直接新增类型。", "errors": ["type_candidate_exists"]}
            return {"valid": True, "queue": "new_type", "reason": judgement.reason, "errors": []}
        return {"valid": True, "queue": "needs_input", "reason": judgement.reason, "errors": []}


def _judgement_payload(
    rows: list[MaterialIntakeRow],
    facts_by_id: dict[str, ExtractedMaterialFacts],
    retrieval_by_id: dict[str, RetrievalResult],
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for row in rows:
        retrieval = retrieval_by_id[row.row_id]
        candidates = retrieval.candidates
        if len(candidates) > 20:
            evidence: Any = {"groups": [group.model_dump(mode="json") for group in retrieval.candidate_groups]}
        else:
            evidence = [candidate.model_dump(mode="json") for candidate in candidates]
        payload.append({
            "row_id": row.row_id,
            "raw_name": row.raw_name,
            "raw_spec": row.raw_spec,
            "quantity": row.qty,
            "uom": row.uom,
            "facts": facts_by_id[row.row_id].model_dump(mode="json"),
            "threshold": retrieval.threshold,
            "candidate_count": retrieval.all_candidate_count,
            "candidates": evidence,
        })
    return payload


def judge_material_intake_with_deepseek(payload: list[dict[str, Any]]) -> BatchMaterialJudgement:
    from nexterp_agent.agent_runtime.deepseek_material_request import call_deepseek_json

    messages = [
        {"role": "system", "content": (
            "你是工程采购清单的候选比较员。你只能比较下面服务端召回的真实标准类型和 SKU。"
            "不得编造 type_id、item_code，不得修改数量和单位。existing_sku 必须选择没有关键规格冲突的真实 SKU；"
            "new_sku 必须引用真实标准类型；只有没有可信类型候选时才能 new_type；证据不足必须 needs_input。"
            "候选超过20项时只能根据分组摘要追问，不得从代表项强行选择。只输出 JSON。"
        )},
        {"role": "system", "content": json.dumps({
            "output_schema": {"rows": [{
                "row_id": "原样返回", "decision": "existing_sku | new_sku | new_type | needs_input",
                "selected_type_id": "候选中的真实 type_id 或空", "selected_item_code": "候选中的真实 item_code 或空",
                "reason": "简短判断依据", "confirmed_attributes": {}, "conflicts": [], "questions": []
            }]},
            "rows": payload,
        }, ensure_ascii=False)},
    ]
    result = call_deepseek_json(messages)
    rows = result.get("rows") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise ValueError("DeepSeek 候选判定返回格式不正确")
    return BatchMaterialJudgement.model_validate({"rows": rows})
