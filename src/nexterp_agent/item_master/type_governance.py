from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
import re
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PROMPT_VERSION = "material-type-dictionary-v0.5"
DIMENSION_PATTERN = re.compile(
    r"(?:\bDN\s*\d|[MΦØ]\s*\d|\d+(?:\.\d+)?\s*(?:mm|cm|米|寸|分)|\d+\s*[×*]\s*\d+)",
    re.IGNORECASE,
)
SPEC_PART_PATTERN = re.compile(r"\s*[；;]\s*")
SPEC_KEY_PATTERN = re.compile(r"^\s*([^:：]{1,20})\s*[:：]\s*(.+?)\s*$")
TOKEN_PATTERN = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*|\d+(?:\.\d+)?|[\u4e00-\u9fff]{2,}")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class RepresentativeSku(StrictModel):
    item_code: str
    sku_name: str
    required_specs: str = ""
    optional_specs: str = ""
    aliases: str = ""
    stock_uom: str = ""


class NameEvidence(StrictModel):
    current_name: str
    sku_count: int = Field(ge=1)
    representative_skus: list[RepresentativeSku] = Field(min_length=1, max_length=5)
    observed_units: list[str] = Field(default_factory=list)
    observed_spec_keys: list[str] = Field(default_factory=list)
    distinguishing_tokens: list[str] = Field(default_factory=list)


class FamilyEvidence(StrictModel):
    top_group: str
    material_family: str
    source_hash: str
    names: list[NameEvidence] = Field(min_length=1)

    @property
    def name_count(self) -> int:
        return len(self.names)


class GovernanceBatchInput(StrictModel):
    batch_id: str
    prompt_version: str = PROMPT_VERSION
    families: list[FamilyEvidence] = Field(min_length=1)


class AttributeProposal(StrictModel):
    attribute_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    display_name: str
    requirement: Literal["required", "optional"]
    value_type: Literal["text", "number", "enum", "boolean"] = "text"
    unit: str = ""
    enum_values: list[str] = Field(default_factory=list)
    affects_sku_identity: bool = True
    description: str = ""

    @model_validator(mode="after")
    def validate_enum(self) -> "AttributeProposal":
        if self.value_type == "enum" and not self.enum_values:
            raise ValueError("enum attribute requires enum_values")
        return self


class MaterialTypeProposal(StrictModel):
    temporary_key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    standard_name: str
    definition: str
    includes: str
    excludes: str
    aliases: list[str] = Field(default_factory=list)
    attributes: list[AttributeProposal] = Field(default_factory=list)

    @field_validator("standard_name")
    @classmethod
    def reject_dimensions(cls, value: str) -> str:
        if DIMENSION_PATTERN.search(value):
            raise ValueError("standard_name must not contain SKU dimensions")
        return value


class NameDecisionProposal(StrictModel):
    current_name: str
    action: Literal["keep", "rename", "merge", "split", "needs_evidence"]
    target_keys: list[str] = Field(min_length=1)
    reason: str

    @model_validator(mode="after")
    def validate_targets(self) -> "NameDecisionProposal":
        unique = list(dict.fromkeys(self.target_keys))
        self.target_keys = unique
        if self.action == "split" and len(unique) < 2:
            raise ValueError("split decision requires at least two target_keys")
        if self.action != "split" and len(unique) != 1:
            raise ValueError("non-split decision requires exactly one target_key")
        return self


class FamilyGenerationProposal(StrictModel):
    top_group: str
    material_family: str
    source_hash: str
    types: list[MaterialTypeProposal] = Field(min_length=1)
    decisions: list[NameDecisionProposal] = Field(min_length=1)


class GovernanceGenerationResult(StrictModel):
    families: list[FamilyGenerationProposal] = Field(min_length=1)


class TypeReview(StrictModel):
    temporary_key: str
    verdict: Literal["approve", "revise", "reject"]
    issue: str = ""


class DecisionReview(StrictModel):
    current_name: str
    verdict: Literal["approve", "revise", "reject"]
    issue: str = ""


class FamilyReview(StrictModel):
    top_group: str
    material_family: str
    source_hash: str
    verdict: Literal["approve", "revise", "reject"]
    type_reviews: list[TypeReview] = Field(min_length=1)
    decision_reviews: list[DecisionReview] = Field(min_length=1)
    summary: str


class GovernanceReviewResult(StrictModel):
    families: list[FamilyReview] = Field(min_length=1)


class DetailedItemMapping(StrictModel):
    item_code: str
    target_key: str
    extracted_attributes: dict[str, str] = Field(default_factory=dict)
    reason: str
    confidence: float = Field(ge=0, le=1)


class DetailedFamilyMapping(StrictModel):
    top_group: str
    material_family: str
    source_hash: str
    mappings: list[DetailedItemMapping] = Field(min_length=1)


class DetailedMappingResult(StrictModel):
    families: list[DetailedFamilyMapping] = Field(min_length=1)


class DetailedItemReview(StrictModel):
    item_code: str
    verdict: Literal["approve", "revise", "reject"]
    issue: str = ""


class DetailedFamilyReview(StrictModel):
    top_group: str
    material_family: str
    source_hash: str
    verdict: Literal["approve", "revise", "reject"]
    item_reviews: list[DetailedItemReview] = Field(min_length=1)
    summary: str


class DetailedMappingReviewResult(StrictModel):
    families: list[DetailedFamilyReview] = Field(min_length=1)


class GovernanceIssue(StrictModel):
    issue_id: str
    batch_id: str
    top_group: str
    material_family: str
    current_name: str = ""
    item_code: str = ""
    issue_type: str
    severity: Literal["high", "medium", "low"] = "high"
    detail: str
    status: Literal["open", "resolved"] = "open"


class GovernanceSnapshot(StrictModel):
    batch: dict[str, Any]
    type_dictionary: list[dict[str, Any]] = Field(default_factory=list)
    type_aliases: list[dict[str, Any]] = Field(default_factory=list)
    attribute_templates: list[dict[str, Any]] = Field(default_factory=list)
    name_decisions: list[dict[str, Any]] = Field(default_factory=list)
    sku_mappings: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)


def normalize_name(value: str) -> str:
    return re.sub(r"[\s\-_/（）()]+", "", value or "").casefold()


def content_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_type_id(top_group: str, material_family: str, standard_name: str) -> str:
    digest = hashlib.sha256(
        f"{normalize_name(top_group)}\0{normalize_name(material_family)}\0{normalize_name(standard_name)}".encode(
            "utf-8"
        )
    ).hexdigest()[:12].upper()
    return f"MT-{digest}"


def stable_issue_id(*parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:14].upper()
    return f"MGI-{digest}"


def _spec_keys(*values: str) -> list[str]:
    keys: list[str] = []
    for value in values:
        for part in SPEC_PART_PATTERN.split(value or ""):
            match = SPEC_KEY_PATTERN.match(part)
            if match:
                keys.append(match.group(1).strip())
    return list(dict.fromkeys(keys))


def _tokens(*values: str) -> list[str]:
    excluded = {"规格", "型号", "类型", "单位", "材质", "长度", "直径", "品牌"}
    counter: Counter[str] = Counter()
    for value in values:
        for token in TOKEN_PATTERN.findall(value or ""):
            normalized = token.strip()
            if normalized and normalized not in excluded:
                counter[normalized] += 1
    return [token for token, _ in counter.most_common(12)]


def build_family_evidence(
    rows: Iterable[dict[str, str]],
    *,
    max_examples: int = 5,
) -> list[FamilyEvidence]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for raw in rows:
        row = {key: str(value or "").strip() for key, value in raw.items()}
        top_group = row.get("top_group", "")
        family = row.get("material_family", "")
        if top_group and family:
            grouped[(top_group, family)].append(row)

    families: list[FamilyEvidence] = []
    for (top_group, family), family_rows in sorted(grouped.items()):
        by_name: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in family_rows:
            by_name[row.get("item_name", "")].append(row)

        name_evidence: list[NameEvidence] = []
        for current_name, name_rows in sorted(by_name.items()):
            ordered = sorted(name_rows, key=lambda row: row.get("item_code", ""))
            examples = [
                RepresentativeSku(
                    item_code=row.get("item_code", ""),
                    sku_name=row.get("sku_name", ""),
                    required_specs=row.get("required_specs", ""),
                    optional_specs=row.get("optional_specs", ""),
                    aliases=row.get("aliases", ""),
                    stock_uom=row.get("stock_uom", ""),
                )
                for row in ordered[:max_examples]
            ]
            name_evidence.append(
                NameEvidence(
                    current_name=current_name,
                    sku_count=len(name_rows),
                    representative_skus=examples,
                    observed_units=sorted(
                        {row.get("stock_uom", "") for row in name_rows if row.get("stock_uom", "")}
                    ),
                    observed_spec_keys=_spec_keys(
                        *(row.get("required_specs", "") for row in name_rows),
                        *(row.get("optional_specs", "") for row in name_rows),
                    ),
                    distinguishing_tokens=_tokens(
                        current_name,
                        *(row.get("sku_name", "") for row in name_rows),
                        *(row.get("required_specs", "") for row in name_rows),
                    ),
                )
            )

        source_payload = [
            {
                key: row.get(key, "")
                for key in (
                    "item_code",
                    "item_name",
                    "sku_name",
                    "required_specs",
                    "optional_specs",
                    "aliases",
                    "stock_uom",
                    "top_group",
                    "material_family",
                )
            }
            for row in sorted(family_rows, key=lambda row: row.get("item_code", ""))
        ]
        families.append(
            FamilyEvidence(
                top_group=top_group,
                material_family=family,
                source_hash=content_hash(source_payload),
                names=name_evidence,
            )
        )
    return families


def pack_family_batches(
    families: Iterable[FamilyEvidence],
    *,
    max_names: int = 160,
) -> list[GovernanceBatchInput]:
    if max_names <= 0:
        raise ValueError("max_names must be positive")
    batches: list[list[FamilyEvidence]] = []
    current: list[FamilyEvidence] = []
    current_count = 0
    for family in families:
        if current and current_count + family.name_count > max_names:
            batches.append(current)
            current = []
            current_count = 0
        current.append(family)
        current_count += family.name_count
        if current_count >= max_names:
            batches.append(current)
            current = []
            current_count = 0
    if current:
        batches.append(current)
    output: list[GovernanceBatchInput] = []
    for batch in batches:
        identity = [
            {
                "top_group": family.top_group,
                "material_family": family.material_family,
                "source_hash": family.source_hash,
            }
            for family in batch
        ]
        output.append(
            GovernanceBatchInput(
                batch_id=f"MGB-{content_hash(identity)[:12].upper()}",
                families=batch,
            )
        )
    return output


def names_requiring_detailed_mapping(
    batch: GovernanceBatchInput,
    generation: GovernanceGenerationResult,
) -> dict[tuple[str, str], set[str]]:
    evidence_by_key = {(item.top_group, item.material_family): item for item in batch.families}
    output: dict[tuple[str, str], set[str]] = defaultdict(set)
    for proposal in generation.families:
        key = (proposal.top_group, proposal.material_family)
        evidence = evidence_by_key.get(key)
        if evidence is None:
            continue
        evidence_by_name = {item.current_name: item for item in evidence.names}
        for decision in proposal.decisions:
            name_evidence = evidence_by_name.get(decision.current_name)
            if decision.action in {"split", "needs_evidence"}:
                output[key].add(decision.current_name)
                continue
            if (
                name_evidence
                and name_evidence.sku_count > 1
                and normalize_name(decision.current_name) == normalize_name(evidence.material_family)
            ):
                output[key].add(decision.current_name)
    return dict(output)


def approved_detail_family_keys(
    batch: GovernanceBatchInput,
    generation: GovernanceGenerationResult,
    review: GovernanceReviewResult,
) -> set[tuple[str, str]]:
    required = names_requiring_detailed_mapping(batch, generation)
    verdicts = {
        (item.top_group, item.material_family): item.verdict for item in review.families
    }
    return {
        key
        for key, names in required.items()
        if names and verdicts.get(key) == "approve"
    }


def validate_generation_and_review(
    batch: GovernanceBatchInput,
    generation: GovernanceGenerationResult,
    review: GovernanceReviewResult,
    detailed_mapping: DetailedMappingResult | None = None,
    detailed_review: DetailedMappingReviewResult | None = None,
) -> list[GovernanceIssue]:
    issues: list[GovernanceIssue] = []
    evidence_by_key = {(item.top_group, item.material_family): item for item in batch.families}
    generated_by_key = {(item.top_group, item.material_family): item for item in generation.families}
    review_by_key = {(item.top_group, item.material_family): item for item in review.families}
    detail_required = names_requiring_detailed_mapping(batch, generation)
    detailed_by_key = {
        (item.top_group, item.material_family): item
        for item in (detailed_mapping.families if detailed_mapping else [])
    }
    detailed_review_by_key = {
        (item.top_group, item.material_family): item
        for item in (detailed_review.families if detailed_review else [])
    }

    def add_issue(
        family: FamilyEvidence,
        issue_type: str,
        detail: str,
        *,
        current_name: str = "",
        severity: Literal["high", "medium", "low"] = "high",
    ) -> None:
        issues.append(
            GovernanceIssue(
                issue_id=stable_issue_id(
                    batch.batch_id,
                    family.top_group,
                    family.material_family,
                    current_name,
                    issue_type,
                    detail,
                ),
                batch_id=batch.batch_id,
                top_group=family.top_group,
                material_family=family.material_family,
                current_name=current_name,
                issue_type=issue_type,
                severity=severity,
                detail=detail,
            )
        )

    for key, evidence in evidence_by_key.items():
        proposal = generated_by_key.get(key)
        family_review = review_by_key.get(key)
        if proposal is None:
            add_issue(evidence, "missing_generation", "生成结果缺少该物料族。")
            continue
        if proposal.source_hash != evidence.source_hash:
            add_issue(evidence, "source_hash_mismatch", "生成结果引用的来源版本与当前输入不一致。")
        if family_review is None:
            add_issue(evidence, "missing_review", "独立复核结果缺少该物料族。")
            continue
        if family_review.source_hash != evidence.source_hash:
            add_issue(evidence, "review_source_hash_mismatch", "复核结果引用的来源版本与当前输入不一致。")

        expected_names = {item.current_name for item in evidence.names}
        decision_names = {item.current_name for item in proposal.decisions}
        for missing in sorted(expected_names - decision_names):
            add_issue(evidence, "missing_name_decision", "现有名称没有治理决定。", current_name=missing)
        for extra in sorted(decision_names - expected_names):
            add_issue(evidence, "unknown_name_decision", "治理决定包含输入中不存在的名称。", current_name=extra)

        type_keys = {item.temporary_key for item in proposal.types}
        normalized_names: dict[str, str] = {}
        for item in proposal.types:
            normalized = normalize_name(item.standard_name)
            if normalized in normalized_names:
                add_issue(
                    evidence,
                    "duplicate_standard_name",
                    f"标准名称与 {normalized_names[normalized]} 归一化后重复。",
                    current_name=item.standard_name,
                )
            normalized_names[normalized] = item.standard_name
            attribute_keys = [attribute.attribute_key for attribute in item.attributes]
            if len(attribute_keys) != len(set(attribute_keys)):
                add_issue(
                    evidence,
                    "duplicate_attribute_key",
                    "同一标准名称包含重复属性键。",
                    current_name=item.standard_name,
                )
        for decision in proposal.decisions:
            unknown_targets = sorted(set(decision.target_keys) - type_keys)
            if unknown_targets:
                add_issue(
                    evidence,
                    "unknown_target_type",
                    f"治理决定引用了不存在的类型键：{', '.join(unknown_targets)}。",
                    current_name=decision.current_name,
                )
            if decision.current_name in detail_required.get(key, set()) and key not in detailed_by_key:
                add_issue(
                    evidence,
                    "detailed_mapping_required",
                    "该名称需要查看完整 SKU 证据后再映射。",
                    current_name=decision.current_name,
                    severity="medium",
                )

        required_names = detail_required.get(key, set())
        if required_names and key in detailed_by_key:
            detailed_family = detailed_by_key[key]
            detailed_family_review = detailed_review_by_key.get(key)
            required_codes = {
                row.item_code
                for name in evidence.names
                if name.current_name in required_names
                for row in name.representative_skus
            }
            actual_codes = {item.item_code for item in detailed_family.mappings}
            # Representative evidence alone is not enough to prove complete SKU coverage.
            # The orchestrator sends full rows; the exact-code check is completed in build_snapshot.
            if not required_codes.issubset(actual_codes):
                add_issue(evidence, "missing_detailed_examples", "详细映射没有覆盖全部代表性SKU。")
            if detailed_family_review is None or detailed_family_review.verdict != "approve":
                add_issue(
                    evidence,
                    "detailed_review_not_approved",
                    detailed_family_review.summary if detailed_family_review else "缺少详细映射复核。",
                )
            else:
                item_reviews = {item.item_code: item for item in detailed_family_review.item_reviews}
                for item in detailed_family.mappings:
                    item_review = item_reviews.get(item.item_code)
                    if item_review is None or item_review.verdict != "approve":
                        add_issue(
                            evidence,
                            "detailed_item_not_approved",
                            item_review.issue if item_review else "复核缺少该SKU。",
                            current_name=next(iter(required_names), ""),
                        )

        if family_review.verdict != "approve":
            add_issue(evidence, "family_review_not_approved", family_review.summary)
        type_review_by_key = {item.temporary_key: item for item in family_review.type_reviews}
        for item in proposal.types:
            item_review = type_review_by_key.get(item.temporary_key)
            if item_review is None or item_review.verdict != "approve":
                add_issue(
                    evidence,
                    "type_review_not_approved",
                    item_review.issue if item_review else "复核缺少该标准类型。",
                    current_name=item.standard_name,
                )
        decision_review_by_name = {item.current_name: item for item in family_review.decision_reviews}
        for decision in proposal.decisions:
            item_review = decision_review_by_name.get(decision.current_name)
            if item_review is None or item_review.verdict != "approve":
                add_issue(
                    evidence,
                    "decision_review_not_approved",
                    item_review.issue if item_review else "复核缺少该名称决定。",
                    current_name=decision.current_name,
                )

    for key in sorted(set(generated_by_key) - set(evidence_by_key)):
        top_group, family = key
        ghost = FamilyEvidence(
            top_group=top_group,
            material_family=family,
            source_hash="unknown",
            names=[
                NameEvidence(
                    current_name="unknown",
                    sku_count=1,
                    representative_skus=[RepresentativeSku(item_code="unknown", sku_name="unknown")],
                )
            ],
        )
        add_issue(ghost, "unexpected_family", "生成结果包含输入批次之外的物料族。")
    return issues


def build_snapshot(
    batch: GovernanceBatchInput,
    generation: GovernanceGenerationResult,
    review: GovernanceReviewResult,
    source_rows: Iterable[dict[str, str]],
    *,
    model: str,
    review_model: str,
    detailed_mapping: DetailedMappingResult | None = None,
    detailed_review: DetailedMappingReviewResult | None = None,
    minimum_detailed_confidence: float = 0.75,
) -> GovernanceSnapshot:
    rows = [{key: str(value or "").strip() for key, value in row.items()} for row in source_rows]
    issues = validate_generation_and_review(
        batch,
        generation,
        review,
        detailed_mapping=detailed_mapping,
        detailed_review=detailed_review,
    )
    blocked_families = {(item.top_group, item.material_family) for item in issues if item.severity == "high"}
    issues_by_name = {(item.top_group, item.material_family, item.current_name) for item in issues}
    detail_required = names_requiring_detailed_mapping(batch, generation)
    detailed_by_key = {
        (item.top_group, item.material_family): item
        for item in (detailed_mapping.families if detailed_mapping else [])
    }
    detailed_review_by_key = {
        (item.top_group, item.material_family): item
        for item in (detailed_review.families if detailed_review else [])
    }
    generation_by_key = {(item.top_group, item.material_family): item for item in generation.families}
    review_by_key = {(item.top_group, item.material_family): item for item in review.families}

    type_dictionary: list[dict[str, Any]] = []
    type_aliases: list[dict[str, Any]] = []
    attribute_templates: list[dict[str, Any]] = []
    name_decisions: list[dict[str, Any]] = []
    sku_mappings: list[dict[str, Any]] = []
    type_ids: dict[tuple[str, str, str], str] = {}

    for family in batch.families:
        key = (family.top_group, family.material_family)
        proposal = generation_by_key.get(key)
        if proposal is None:
            continue
        family_review = review_by_key.get(key)
        family_status = "frozen" if key not in blocked_families else "review_required"
        for item in proposal.types:
            type_id = stable_type_id(family.top_group, family.material_family, item.standard_name)
            type_ids[(family.top_group, family.material_family, item.temporary_key)] = type_id
            type_dictionary.append(
                {
                    "type_id": type_id,
                    "top_group": family.top_group,
                    "material_family": family.material_family,
                    "standard_name": item.standard_name,
                    "definition": item.definition,
                    "includes": item.includes,
                    "excludes": item.excludes,
                    "governance_status": family_status,
                    "revision": 1,
                    "source_hash": family.source_hash,
                    "prompt_version": batch.prompt_version,
                    "generator_model": model,
                    "reviewer_model": review_model,
                }
            )
            for alias in list(dict.fromkeys(item.aliases)):
                if alias and normalize_name(alias) != normalize_name(item.standard_name):
                    type_aliases.append(
                        {
                            "type_id": type_id,
                            "alias": alias,
                            "normalized_alias": normalize_name(alias),
                            "alias_kind": "governance",
                        }
                    )
            for order, attribute in enumerate(item.attributes, start=1):
                attribute_templates.append(
                    {
                        "type_id": type_id,
                        "attribute_key": attribute.attribute_key,
                        "display_name": attribute.display_name,
                        "requirement": attribute.requirement,
                        "value_type": attribute.value_type,
                        "unit": attribute.unit,
                        "enum_values": "；".join(attribute.enum_values),
                        "affects_sku_identity": attribute.affects_sku_identity,
                        "display_order": order,
                        "description": attribute.description,
                    }
                )

        for decision in proposal.decisions:
            target_ids = [
                type_ids.get((family.top_group, family.material_family, target), "")
                for target in decision.target_keys
            ]
            decision_status = (
                "frozen"
                if family_status == "frozen"
                and (family.top_group, family.material_family, decision.current_name) not in issues_by_name
                else "review_required"
            )
            name_decisions.append(
                {
                    "top_group": family.top_group,
                    "material_family": family.material_family,
                    "current_name": decision.current_name,
                    "action": decision.action,
                    "target_type_ids": "；".join(value for value in target_ids if value),
                    "reason": decision.reason,
                    "decision_status": decision_status,
                    "source_hash": family.source_hash,
                    "review_summary": family_review.summary if family_review else "",
                }
            )
            if (
                decision_status != "frozen"
                or len(target_ids) != 1
                or decision.current_name in detail_required.get(key, set())
            ):
                continue
            type_id = target_ids[0]
            target_type = next(
                (item for item in type_dictionary if item["type_id"] == type_id),
                None,
            )
            for row in rows:
                if (
                    row.get("top_group") == family.top_group
                    and row.get("material_family") == family.material_family
                    and row.get("item_name") == decision.current_name
                ):
                    mapping_payload = {
                        "item_code": row.get("item_code", ""),
                        "type_id": type_id,
                        "source_hash": family.source_hash,
                    }
                    sku_mappings.append(
                        {
                            "item_code": row.get("item_code", ""),
                            "type_id": type_id,
                            "standard_name": target_type["standard_name"] if target_type else "",
                            "mapping_method": "exact_current_name",
                            "mapping_evidence": decision.reason,
                            "mapping_status": "frozen",
                            "source_hash": content_hash(mapping_payload),
                        }
                    )

        detailed_family = detailed_by_key.get(key)
        detailed_family_review = detailed_review_by_key.get(key)
        if detailed_family and detailed_family_review and detailed_family_review.verdict == "approve":
            allowed_names = detail_required.get(key, set())
            expected_codes = {
                row.get("item_code", "")
                for row in rows
                if row.get("top_group") == family.top_group
                and row.get("material_family") == family.material_family
                and row.get("item_name") in allowed_names
            }
            detailed_codes = {item.item_code for item in detailed_family.mappings}
            if detailed_codes != expected_codes:
                issue = GovernanceIssue(
                    issue_id=stable_issue_id(
                        batch.batch_id,
                        family.top_group,
                        family.material_family,
                        "detailed_mapping_coverage",
                    ),
                    batch_id=batch.batch_id,
                    top_group=family.top_group,
                    material_family=family.material_family,
                    issue_type="detailed_mapping_coverage",
                    severity="high",
                    detail="详细映射编码集合与需要下钻的SKU集合不一致。",
                )
                issues.append(issue)
                blocked_families.add(key)
            else:
                item_reviews = {item.item_code: item for item in detailed_family_review.item_reviews}
                proposal_type_keys = {item.temporary_key for item in proposal.types}
                for item in detailed_family.mappings:
                    item_review = item_reviews.get(item.item_code)
                    if (
                        item.target_key not in proposal_type_keys
                        or item.confidence < minimum_detailed_confidence
                        or item_review is None
                        or item_review.verdict != "approve"
                    ):
                        issues.append(
                            GovernanceIssue(
                                issue_id=stable_issue_id(
                                    batch.batch_id,
                                    family.top_group,
                                    family.material_family,
                                    item.item_code,
                                    "detailed_mapping_not_approved",
                                ),
                                batch_id=batch.batch_id,
                                top_group=family.top_group,
                                material_family=family.material_family,
                                item_code=item.item_code,
                                issue_type="detailed_mapping_not_approved",
                                severity="high",
                                detail=(
                                    "详细映射未达到自动放行条件："
                                    f"target={item.target_key}, confidence={item.confidence:.2f}, "
                                    f"review={item_review.verdict if item_review else 'missing'}。"
                                ),
                            )
                        )
                        blocked_families.add(key)
                        continue
                    type_id = type_ids[(family.top_group, family.material_family, item.target_key)]
                    target_type = next(
                        value for value in type_dictionary if value["type_id"] == type_id
                    )
                    mapping_payload = {
                        "item_code": item.item_code,
                        "type_id": type_id,
                        "attributes": item.extracted_attributes,
                        "source_hash": family.source_hash,
                    }
                    sku_mappings.append(
                        {
                            "item_code": item.item_code,
                            "type_id": type_id,
                            "standard_name": target_type["standard_name"],
                            "mapping_method": "detailed_evidence",
                            "mapping_evidence": json.dumps(
                                {
                                    "reason": item.reason,
                                    "attributes": item.extracted_attributes,
                                    "confidence": item.confidence,
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                            "mapping_status": "frozen",
                            "source_hash": content_hash(mapping_payload),
                        }
                    )

        if key in blocked_families:
            for item in type_dictionary:
                if item["top_group"] == family.top_group and item["material_family"] == family.material_family:
                    item["governance_status"] = "review_required"
            for item in name_decisions:
                if item["top_group"] == family.top_group and item["material_family"] == family.material_family:
                    item["decision_status"] = "review_required"
            sku_mappings = [
                item
                for item in sku_mappings
                if not any(
                    row.get("item_code") == item["item_code"]
                    and row.get("top_group") == family.top_group
                    and row.get("material_family") == family.material_family
                    for row in rows
                )
            ]

    mapped_codes = {item["item_code"] for item in sku_mappings}
    batch_family_keys = {
        (family.top_group, family.material_family) for family in batch.families
    }
    unresolved_family_keys: set[tuple[str, str]] = set()
    existing_item_issues = {item.item_code for item in issues if item.item_code}
    for row in rows:
        key = (row.get("top_group", ""), row.get("material_family", ""))
        item_code = row.get("item_code", "")
        if key not in batch_family_keys or not item_code or item_code in mapped_codes:
            continue
        unresolved_family_keys.add(key)
        if item_code in existing_item_issues:
            continue
        issues.append(
            GovernanceIssue(
                issue_id=stable_issue_id(
                    batch.batch_id,
                    key[0],
                    key[1],
                    item_code,
                    "sku_mapping_unresolved",
                ),
                batch_id=batch.batch_id,
                top_group=key[0],
                material_family=key[1],
                current_name=row.get("item_name", ""),
                item_code=item_code,
                issue_type="sku_mapping_unresolved",
                severity="high",
                detail="该 SKU 尚未获得经生成、独立复核和程序校验共同确认的标准类型映射。",
            )
        )

    if unresolved_family_keys:
        for item in type_dictionary:
            if (item["top_group"], item["material_family"]) in unresolved_family_keys:
                item["governance_status"] = "review_required"
        for item in name_decisions:
            if (item["top_group"], item["material_family"]) in unresolved_family_keys:
                item["decision_status"] = "review_required"

    batch_row = {
        "batch_id": batch.batch_id,
        "prompt_version": batch.prompt_version,
        "generator_model": model,
        "reviewer_model": review_model,
        "input_hash": content_hash(batch.model_dump(mode="json")),
        "family_count": len(batch.families),
        "name_count": sum(item.name_count for item in batch.families),
        "status": "frozen" if not any(item.severity == "high" for item in issues) else "review_required",
    }
    return GovernanceSnapshot(
        batch=batch_row,
        type_dictionary=type_dictionary,
        type_aliases=type_aliases,
        attribute_templates=attribute_templates,
        name_decisions=name_decisions,
        sku_mappings=sku_mappings,
        issues=[item.model_dump(mode="json") for item in issues],
    )
