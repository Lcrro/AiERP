from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
import re
from time import perf_counter
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .type_classifier import MaterialClassificationResult, MaterialTypeClassifier


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MaterialIntakeRow(_StrictModel):
    row_id: str = Field(min_length=1, max_length=80)
    raw_name: str = Field(min_length=1, max_length=300)
    raw_spec: str = Field(default="", max_length=500)
    qty: float = Field(gt=0)
    uom: str = Field(min_length=1, max_length=80)


class ExtractedMaterialFacts(_StrictModel):
    row_id: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=300)
    attributes: dict[str, str] = Field(default_factory=dict)
    top_group_hint: str = Field(default="", max_length=140)
    material_family_hint: str = Field(default="", max_length=140)
    ambiguity_note: str = Field(default="", max_length=500)


class BatchFactExtraction(_StrictModel):
    rows: list[ExtractedMaterialFacts] = Field(min_length=1, max_length=50)


class MaterialIntakeDecision(_StrictModel):
    row_id: str
    raw_name: str
    raw_spec: str = ""
    qty: float
    uom: str
    queue: Literal["existing_sku", "new_sku", "new_type", "needs_input"]
    queue_label: str
    standard_name: str = ""
    type_id: str = ""
    top_group_hint: str = ""
    material_family_hint: str = ""
    item_code: str = ""
    sku_name: str = ""
    normalized_attributes: dict[str, str] = Field(default_factory=dict)
    attribute_sources: dict[str, str] = Field(default_factory=dict)
    standard_completion_note: str = ""
    missing_attributes: list[dict[str, str]] = Field(default_factory=list)
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    reason: str
    ambiguity_note: str = ""
    retrieval_threshold: int = 0
    candidate_count: int = 0
    candidate_groups: list[dict[str, Any]] = Field(default_factory=list)
    deepseek_judgement: dict[str, Any] = Field(default_factory=dict)
    program_validation: dict[str, Any] = Field(default_factory=dict)
    alias_learning: dict[str, Any] = Field(default_factory=dict)


class MaterialIntakeTraceStep(_StrictModel):
    stage: Literal["read", "extract", "match", "retrieve", "compress", "judge", "validate", "complete", "queue"]
    title: str
    status: Literal["completed", "partial", "failed"]
    input_rows: int = 0
    output_rows: int = 0
    duration_ms: int = 0
    details: list[str] = Field(default_factory=list)


class MaterialIntakeBatchResult(_StrictModel):
    status: Literal["completed"] = "completed"
    writes_erpnext: bool = False
    total_rows: int
    queue_counts: dict[str, int]
    decisions: list[MaterialIntakeDecision]
    processing_trace: list[MaterialIntakeTraceStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_totals(self) -> "MaterialIntakeBatchResult":
        if self.total_rows != len(self.decisions):
            raise ValueError("批次总数与结果行数不一致")
        if sum(self.queue_counts.values()) != self.total_rows:
            raise ValueError("队列统计与批次总数不一致")
        return self


FactExtractor = Callable[[list[MaterialIntakeRow]], BatchFactExtraction]


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))


class BatchMaterialIntakeAnalyzer:
    """Analyze a purchase list without mutating the material catalog or ERPNext."""

    def __init__(
        self,
        classifier: MaterialTypeClassifier | None = None,
        *,
        fact_extractor: FactExtractor | None = None,
    ) -> None:
        self.classifier = classifier or MaterialTypeClassifier()
        self.fact_extractor = fact_extractor or extract_material_facts_with_deepseek

    def analyze(self, rows: list[MaterialIntakeRow]) -> MaterialIntakeBatchResult:
        if not rows:
            raise ValueError("采购清单不能为空")
        if len(rows) > 50:
            raise ValueError("首版每批最多分析 50 行")
        row_ids = [row.row_id for row in rows]
        if len(set(row_ids)) != len(row_ids):
            raise ValueError("row_id 必须唯一")

        trace: list[MaterialIntakeTraceStep] = []
        started = perf_counter()
        trace.append(MaterialIntakeTraceStep(
            stage="read",
            title="读取现场原文",
            status="completed",
            input_rows=len(rows),
            output_rows=len(rows),
            duration_ms=_elapsed_ms(started),
            details=["保留原始名称、原始规格、采购数量和采购单位。", "数量和单位不交给模型改写。"],
        ))

        started = perf_counter()
        extracted = self.fact_extractor(rows)
        facts_by_id = {row.row_id: row for row in extracted.rows}
        if set(facts_by_id) != set(row_ids):
            missing = sorted(set(row_ids) - set(facts_by_id))
            extra = sorted(set(facts_by_id) - set(row_ids))
            raise ValueError(f"DeepSeek 返回行不完整，missing={missing}, extra={extra}")
        fact_rows = sum(bool(facts.attributes) for facts in extracted.rows)
        ambiguous_rows = sum(bool(facts.ambiguity_note) for facts in extracted.rows)
        trace.append(MaterialIntakeTraceStep(
            stage="extract",
            title="DeepSeek 提取现场事实",
            status="partial" if ambiguous_rows else "completed",
            input_rows=len(rows),
            output_rows=len(extracted.rows),
            duration_ms=_elapsed_ms(started),
            details=[
                f"返回 {len(extracted.rows)} 行，字段完整。",
                f"提取出明确属性 {fact_rows} 行。",
                f"标记歧义 {ambiguous_rows} 行。",
                "只使用员工原文中明确出现的属性，不负责编造标准值。",
            ],
        ))

        started = perf_counter()
        decisions = [self._decide(row, facts_by_id[row.row_id]) for row in rows]
        matched_rows = sum(bool(decision.standard_name or decision.type_id) for decision in decisions)
        existing_rows = sum(decision.queue == "existing_sku" for decision in decisions)
        new_sku_rows = sum(decision.queue == "new_sku" for decision in decisions)
        new_type_rows = sum(decision.queue == "new_type" for decision in decisions)
        needs_input_rows = sum(decision.queue == "needs_input" for decision in decisions)
        trace.append(MaterialIntakeTraceStep(
            stage="match",
            title="匹配标准目录与 SKU",
            status="partial" if needs_input_rows or new_type_rows else "completed",
            input_rows=len(decisions),
            output_rows=matched_rows,
            duration_ms=_elapsed_ms(started),
            details=[
                f"匹配到标准类型 {matched_rows} 行。",
                f"已有 SKU {existing_rows} 行；现有类型新增 SKU {new_sku_rows} 行。",
                f"没有标准类型 {new_type_rows} 行；多候选或缺信息 {needs_input_rows} 行。",
                "目录匹配由本地标准字典和 SKU 数据完成，不由模型临场编造编码。",
            ],
        ))

        started = perf_counter()
        completed_rows = sum(bool(decision.standard_completion_note and "补齐" in decision.standard_completion_note) for decision in decisions)
        completed_attributes = sum(
            sum(source == "标准物料默认" for source in decision.attribute_sources.values())
            for decision in decisions
        )
        waiting_type_rows = sum(not (decision.standard_name or decision.type_id) for decision in decisions)
        trace.append(MaterialIntakeTraceStep(
            stage="complete",
            title="采用标准物料属性补齐",
            status="partial" if waiting_type_rows else "completed",
            input_rows=len(decisions),
            output_rows=len(decisions) - waiting_type_rows,
            duration_ms=_elapsed_ms(started),
            details=[
                f"采用标准默认值补齐 {completed_rows} 行，共补齐 {completed_attributes} 个属性字段。",
                f"{waiting_type_rows} 行没有标准类型，不能套用默认属性。",
                "标准默认值只来自已批准的标准物料目录，不来自模型猜测。",
            ],
        ))
        counts = {key: 0 for key in ("existing_sku", "new_sku", "new_type", "needs_input")}
        for decision in decisions:
            counts[decision.queue] += 1
        trace.append(MaterialIntakeTraceStep(
            stage="queue",
            title="生成准入结论",
            status="completed",
            input_rows=len(decisions),
            output_rows=len(decisions),
            duration_ms=0,
            details=[
                f"已有 SKU {counts['existing_sku']} 行。",
                f"现有类型新增 SKU {counts['new_sku']} 行。",
                f"新增标准类型 {counts['new_type']} 行。",
                f"需要补充或选择 {counts['needs_input']} 行。",
                "本批只生成分析结果，未写入 ERPNext。",
            ],
        ))
        return MaterialIntakeBatchResult(
            total_rows=len(rows),
            queue_counts=counts,
            decisions=decisions,
            processing_trace=trace,
        )

    def _decide(self, row: MaterialIntakeRow, facts: ExtractedMaterialFacts) -> MaterialIntakeDecision:
        attributes = dict(facts.attributes)
        attributes.setdefault("uom", row.uom)
        # Preserve the employee's discriminating words (for example “J422”).
        # Appending the cleaned query can duplicate a generic name and reduce
        # the resolver's exact-alias score.
        classification_text = " ".join(
            value for value in (row.raw_name, row.raw_spec) if value
        ) or facts.query
        classification = self.classifier.classify(
            classification_text,
            attributes=attributes,
            top_group_hint=facts.top_group_hint,
            material_family_hint=facts.material_family_hint,
            limit=5,
        )
        input_attribute_keys = set(classification.normalized_attributes)
        classification, completion_note = _complete_from_standard_catalog(
            self.classifier,
            classification,
            classification_text,
        )
        queue = _queue_for(classification)
        selected = classification.selected_type
        existing = classification.existing_sku or {}
        candidates = (
            classification.sku_candidates
            if classification.sku_candidates
            else [candidate.model_dump(mode="json") for candidate in classification.type_candidates]
        )
        questions = list(classification.questions)
        unit_note = _unit_note(row.uom, existing) if queue == "existing_sku" else ""
        if unit_note:
            completion_note = "；".join(value for value in (completion_note, unit_note) if value)
        if facts.ambiguity_note and not questions:
            questions = [facts.ambiguity_note]
        return MaterialIntakeDecision(
            row_id=row.row_id,
            raw_name=row.raw_name,
            raw_spec=row.raw_spec,
            qty=row.qty,
            uom=row.uom,
            queue=queue,
            queue_label={
                "existing_sku": "已有 SKU",
                "new_sku": "现有类型新增 SKU",
                "new_type": "需要新增标准类型",
                "needs_input": "需要补充或选择",
            }[queue],
            standard_name=selected.standard_name if selected else "",
            type_id=selected.type_id if selected else "",
            item_code=str(existing.get("item_code") or ""),
            sku_name=str(existing.get("sku_name") or existing.get("item_name") or ""),
            normalized_attributes=classification.normalized_attributes,
            attribute_sources={
                key: "现场输入" if key in input_attribute_keys else "标准物料默认"
                for key in classification.normalized_attributes
            },
            standard_completion_note=completion_note,
            missing_attributes=classification.missing_attributes,
            candidates=candidates[:5],
            questions=questions,
            reason=classification.reason,
            ambiguity_note=facts.ambiguity_note,
        )


def extract_material_facts_with_deepseek(rows: list[MaterialIntakeRow]) -> BatchFactExtraction:
    # A larger chunk reduces API round trips while keeping the extraction
    # prompt small enough for stable JSON output. Quantity and UOM stay local.
    chunks = [rows[index:index + 20] for index in range(0, len(rows), 20)]
    if len(chunks) == 1:
        return _extract_material_fact_chunk(chunks[0])
    with ThreadPoolExecutor(max_workers=min(3, len(chunks))) as executor:
        extracted_chunks = list(executor.map(_extract_material_fact_chunk, chunks))
    by_id = {
        row.row_id: row
        for extracted in extracted_chunks
        for row in extracted.rows
    }
    return BatchFactExtraction(rows=[by_id[row.row_id] for row in rows if row.row_id in by_id])


def _extract_material_fact_chunk(rows: list[MaterialIntakeRow]) -> BatchFactExtraction:
    # Import lazily: agent_runtime imports ERPNext modules that also import item_master.
    from nexterp_agent.agent_runtime.deepseek_material_request import call_deepseek_json

    payload = [
        {
            "row_id": row.row_id,
            "raw_name": row.raw_name,
            "raw_spec": row.raw_spec,
        }
        for row in rows
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "你是工程采购清单的物料事实抽取员。逐行把脏名称和规格整理成供企业物料字典分类的事实。"
                "不得删除行、合并行或改变数量和原单位；不得编造品牌、型号、材质、尺寸或性能。"
                "query 应保留能决定物料类型的名称，去掉品牌和纯尺寸；attributes 只记录输入中明确出现的采购属性。"
                "允许规范单位符号和常见写法，例如 φ14→14mm、12寸保留为12寸。"
                "可推断一级类目和物料族，但不确定时留空。名称或规格有歧义时写入 ambiguity_note。"
                "只输出 JSON object，不要 Markdown。"
            ),
        },
        {
            "role": "system",
            "content": json.dumps(
                {
                    "output_schema": {
                        "rows": [
                            {
                                "row_id": "必须原样返回",
                                "query": "用于标准名称字典匹配的物料名称",
                                "attributes": {
                                    "material|size|diameter|length|interface|brand|model|voltage|power|capacity|nominal_diameter|connection_type|strength_grade|surface_treatment|spec|uom": "仅输入中明确出现的值"
                                },
                                "top_group_hint": "可可靠判断时填写",
                                "material_family_hint": "可可靠判断时填写",
                                "ambiguity_note": "无歧义则为空",
                            }
                        ]
                    },
                    "rows": payload,
                },
                ensure_ascii=False,
            ),
        },
    ]
    return BatchFactExtraction.model_validate(_normalize_extraction_payload(call_deepseek_json(messages)))


def _normalize_extraction_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop harmless copied source columns while keeping the contract strict.

    Models often echo qty/uom to demonstrate row preservation. Those values are
    intentionally ignored: the original purchase row remains authoritative.
    """
    allowed = {
        "row_id", "query", "attributes", "top_group_hint",
        "material_family_hint", "ambiguity_note",
    }
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return payload
    return {
        "rows": [
            {key: value for key, value in row.items() if key in allowed}
            if isinstance(row, dict) else row
            for row in rows
        ]
    }


def _queue_for(result: MaterialClassificationResult) -> str:
    return {
        "existing_sku": "existing_sku",
        "new_sku": "new_sku",
        "new_type_review": "new_type",
        "needs_choice": "needs_input",
        "needs_input": "needs_input",
    }[result.status]


def _complete_from_standard_catalog(
    classifier: MaterialTypeClassifier,
    classification: MaterialClassificationResult,
    raw_text: str,
) -> tuple[MaterialClassificationResult, str]:
    """Fill system attributes from approved catalog rows, never from guesswork."""

    if classification.status != "needs_input" or not classification.selected_type:
        return classification, ""

    matching = [
        item for item in classification.sku_candidates
        if item.get("all_supplied_attributes_match") and item.get("confidence") == "high"
    ]
    if matching:
        top_score = int(matching[0].get("score") or 0)
        second_score = int(matching[1].get("score") or 0) if len(matching) > 1 else 0
        if len(matching) == 1 or top_score - second_score >= 25:
            row = classifier.release_rows.get(str(matching[0].get("item_code") or ""), {})
            completed = _attributes_from_release_row(
                classification.selected_type.attributes,
                row,
            )
            retried = classifier.classify(
                raw_text,
                attributes={**completed, **classification.normalized_attributes},
                limit=5,
            )
            if retried.status == "existing_sku":
                return retried, "缺少的系统属性已采用企业标准 SKU 补齐。"

    release_rows = classifier.release_rows_for_type(classification.selected_type.type_id)
    defaults = _common_standard_attributes(classification.selected_type.attributes, release_rows)
    missing_keys = {item["attribute_key"] for item in classification.missing_attributes}
    applicable = {key: value for key, value in defaults.items() if key in missing_keys}
    if not applicable:
        return classification, ""
    retried = classifier.classify(
        raw_text,
        attributes={**applicable, **classification.normalized_attributes},
        limit=5,
    )
    if retried.status in {"existing_sku", "new_sku"}:
        labels = "、".join(applicable.values())
        return retried, f"缺少的系统属性已继承该标准类型的企业默认值：{labels}。"
    return classification, ""


def _common_standard_attributes(
    templates: list[dict[str, Any]],
    rows: list[dict[str, str]],
) -> dict[str, str]:
    if not rows:
        return {}
    parsed = [_attributes_from_release_row(templates, row) for row in rows]
    output: dict[str, str] = {}
    for template in templates:
        key = str(template.get("attribute_key") or "")
        values = {item.get(key, "") for item in parsed if item.get(key)}
        if len(values) == 1:
            output[key] = values.pop()
    return output


def _attributes_from_release_row(
    templates: list[dict[str, Any]],
    row: dict[str, Any],
) -> dict[str, str]:
    spec_text = "；".join(
        str(row.get(key) or "") for key in ("required_specs", "optional_specs")
    )
    pairs = {
        label.strip(): value.strip()
        for label, value in re.findall(r"([^；:：]+)[：:]([^；]+)", spec_text)
    }
    label_aliases = {
        "outer_diameter": ("外径", "直径"),
        "diameter_mm": ("直径（mm）", "直径"),
        "grade": ("等级", "牌号"),
        "gauge": ("规格/号数", "号数", "规格"),
        "abrasive_material": ("磨料材质", "材质"),
    }
    output: dict[str, str] = {}
    for template in templates:
        key = str(template.get("attribute_key") or "")
        labels = (str(template.get("display_name") or ""), *label_aliases.get(key, ()))
        value = next((pairs[label] for label in labels if label in pairs), "")
        if value:
            output[key] = value
    return output


def _unit_note(source_uom: str, existing: dict[str, Any]) -> str:
    stock_uom = str(existing.get("stock_uom") or "").strip()
    purchase_uom = str(existing.get("purchase_uom") or "").strip()
    allowed = {value for value in (stock_uom, purchase_uom) if value}
    if not allowed or source_uom in allowed:
        return ""
    return (
        f"现场采购单位保留为“{source_uom}”；标准库存单位为“{purchase_uom or stock_uom}”，"
        "换算关系在报价或收货阶段按实际包装确认。"
    )
