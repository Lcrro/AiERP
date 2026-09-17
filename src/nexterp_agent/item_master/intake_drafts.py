from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .coding import generate_next_item_code
from .high_recall import HighRecallBatchResult
from .item_creation import ItemMasterCreationPlanner, _description, _render_specs, _sku_name
from .type_classifier import MaterialClassificationCandidate, MaterialClassificationResult, MaterialTypeClassifier
from .type_governance import stable_type_id


ATTRIBUTE_LABELS = {
    "spec": "规格",
    "specification": "规格",
    "material": "材质",
    "model": "型号",
    "brand": "品牌",
    "size": "尺寸",
    "diameter": "直径",
    "length": "长度",
    "width": "宽度",
    "thickness": "厚度",
    "interface": "接口",
    "strength_grade": "强度等级",
    "surface_treatment": "表面处理",
}


class MaterialTypeDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_id: str
    top_group: str
    material_family: str
    standard_name: str
    definition: str = ""
    includes: str = ""
    excludes: str = ""
    aliases: list[str] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    item_group: str
    code_prefix: str
    is_new: bool = False


class MaterialItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    source_rows: list[str] = Field(min_length=1)
    source_names: list[str] = Field(min_length=1)
    action: Literal["create_sku", "create_type_and_sku"] = "create_sku"
    type_id: str
    standard_name: str
    item_code: str
    item_name: str
    item_group: str
    stock_uom: str
    required_specs: str = ""
    optional_specs: str = ""
    normalized_attributes: dict[str, str] = Field(default_factory=dict)
    material_type: MaterialTypeDraft
    item_doc: dict[str, Any]
    revision: int = 1
    frozen_hash: str = ""
    validation_errors: list[str] = Field(default_factory=list)
    status: Literal[
        "pending_confirmation",
        "created",
        "verified_existing",
        "failed",
        "readback_failed",
    ] = "pending_confirmation"


class MaterialDraftBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_id: str
    status: str = "ready"
    created_at: str
    writes_erpnext: bool = False
    drafts: list[MaterialItemDraft] = Field(default_factory=list)
    skipped: list[dict[str, str]] = Field(default_factory=list)
    processing_step: dict[str, Any]


def build_material_drafts(
    analysis_id: str,
    result: HighRecallBatchResult,
    classifier: MaterialTypeClassifier,
    *,
    existing_item_codes: list[str] | None = None,
) -> MaterialDraftBatch:
    """Compile reviewed decisions into server-owned, non-executable drafts."""

    started = datetime.now(timezone.utc)
    planner = ItemMasterCreationPlanner(classifier)
    used_codes = set(existing_item_codes or [])
    used_codes.update(str(row.get("item_code") or "") for row in classifier.release_resolver.rows)
    drafts: list[MaterialItemDraft] = []
    skipped: list[dict[str, str]] = []
    by_key: dict[tuple[str, tuple[tuple[str, str], ...]], MaterialItemDraft] = {}

    for decision in result.decisions:
        if decision.queue == "existing_sku":
            skipped.append({"row_id": decision.row_id, "reason": "已有 SKU，无需新增物料。"})
            continue
        if decision.queue not in {"new_sku", "new_type"}:
            skipped.append({
                "row_id": decision.row_id,
                "reason": "尚未形成可安全发布的物料结论，需先补充或确认。",
            })
            continue

        attrs = {
            str(key): str(value)
            for key, value in decision.normalized_attributes.items()
            if value not in (None, "")
        }
        attrs.setdefault("uom", decision.uom)

        if decision.queue == "new_sku":
            compiled = _compile_existing_type_draft(
                decision,
                classifier,
                planner,
                attrs,
                used_codes,
            )
        else:
            compiled = _compile_new_type_draft(decision, attrs, used_codes)
        if isinstance(compiled, str):
            skipped.append({"row_id": decision.row_id, "reason": compiled})
            continue

        identity = tuple(sorted((key, value) for key, value in attrs.items() if key != "uom"))
        key = (compiled.type_id, identity)
        existing_draft = by_key.get(key)
        if existing_draft is not None:
            existing_draft.source_rows.append(decision.row_id)
            existing_draft.source_names.append(decision.raw_name)
            existing_draft.frozen_hash = _draft_hash(existing_draft)
            continue

        used_codes.add(compiled.item_code)
        drafts.append(compiled)
        by_key[key] = compiled

    return MaterialDraftBatch(
        analysis_id=analysis_id,
        created_at=started.isoformat(),
        drafts=drafts,
        skipped=skipped,
        processing_step={
            "stage": "draft",
            "title": "生成物料录入草稿",
            "status": "completed" if drafts or not result.decisions else "partial",
            "input_rows": len(result.decisions),
            "output_rows": len(drafts),
            "details": [
                f"生成 {len(drafts)} 个待确认物料草稿。",
                f"其中新标准类型及首个 SKU {sum(row.action == 'create_type_and_sku' for row in drafts)} 个。",
                f"跳过 {len(skipped)} 行：已有 SKU、信息不足或结论未确认。",
                "草稿尚未写入 ERPNext，确认后才会执行发布。",
            ],
        },
    )


def revise_material_drafts(
    batch: MaterialDraftBatch,
    updates: list[dict[str, Any]],
    classifier: MaterialTypeClassifier,
    *,
    existing_item_codes: list[str] | None = None,
) -> MaterialDraftBatch:
    """Apply narrow business edits and recompile; raw ERPNext fields are rejected."""

    update_by_id: dict[str, dict[str, Any]] = {}
    for raw in updates:
        if not isinstance(raw, dict):
            raise ValueError("draft_updates 必须是对象数组")
        draft_id = str(raw.get("draft_id") or "").strip()
        if not draft_id or draft_id in update_by_id:
            raise ValueError("每条 draft_update 必须包含唯一 draft_id")
        unknown = set(raw) - {
            "draft_id",
            "stock_uom",
            "normalized_attributes",
            "top_group",
            "material_family",
            "standard_name",
            "definition",
            "includes",
            "excludes",
            "item_group",
            "code_prefix",
        }
        if unknown:
            raise ValueError(f"草稿修改包含不允许的字段：{', '.join(sorted(unknown))}")
        update_by_id[draft_id] = raw

    unknown_ids = set(update_by_id) - {row.draft_id for row in batch.drafts}
    if unknown_ids:
        raise ValueError(f"草稿不存在：{', '.join(sorted(unknown_ids))}")

    revised = batch.model_copy(deep=True)
    used_codes = set(existing_item_codes or [])
    used_codes.update(str(row.get("item_code") or "") for row in classifier.release_resolver.rows)
    planner = ItemMasterCreationPlanner(classifier)
    output: list[MaterialItemDraft] = []
    for original in revised.drafts:
        update = update_by_id.get(original.draft_id, {})
        if original.status in {"created", "verified_existing"}:
            if update:
                raise ValueError(f"已完成发布的草稿不能再修改：{original.draft_id}")
            used_codes.add(original.item_code)
            output.append(original)
            continue
        if not update:
            used_codes.add(original.item_code)
            output.append(original)
            continue
        attrs = dict(original.normalized_attributes)
        if "normalized_attributes" in update:
            raw_attrs = update["normalized_attributes"]
            if not isinstance(raw_attrs, dict):
                raise ValueError("normalized_attributes 必须是对象")
            attrs = {
                str(key).strip(): str(value).strip()
                for key, value in raw_attrs.items()
                if str(key).strip() and str(value).strip()
            }
        stock_uom = str(update.get("stock_uom") or original.stock_uom).strip()
        attrs["uom"] = stock_uom

        if original.action == "create_type_and_sku":
            type_values = original.material_type.model_dump(mode="json")
            for key in (
                "top_group",
                "material_family",
                "standard_name",
                "definition",
                "includes",
                "excludes",
                "item_group",
                "code_prefix",
            ):
                if key in update:
                    type_values[key] = str(update[key] or "").strip()
            compiled = _compile_new_type_values(
                original,
                type_values,
                attrs,
                used_codes,
            )
        else:
            compiled = _recompile_existing_type_draft(
                original,
                classifier,
                planner,
                attrs,
                used_codes,
            )
        compiled.revision = original.revision + (1 if update else 0)
        compiled.frozen_hash = _draft_hash(compiled)
        used_codes.add(compiled.item_code)
        output.append(compiled)
    revised.drafts = output
    return revised


def _compile_existing_type_draft(
    decision: Any,
    classifier: MaterialTypeClassifier,
    planner: ItemMasterCreationPlanner,
    attrs: dict[str, str],
    used_codes: set[str],
) -> MaterialItemDraft | str:
    type_row = next((item for item in classifier.types if item.type_id == decision.type_id), None)
    if type_row is None:
        return "标准物料类型已不在当前目录版本中。"
    candidate = MaterialClassificationCandidate(
        type_id=type_row.type_id,
        top_group=type_row.top_group,
        material_family=type_row.material_family,
        standard_name=type_row.standard_name,
        definition=type_row.definition,
        includes=type_row.includes,
        excludes=type_row.excludes,
        score=100,
        confidence="high",
        match_reasons=["来自本次程序复核通过的真实标准类型"],
        attributes=list(type_row.attributes),
    )
    classification = MaterialClassificationResult(
        status="new_sku",
        raw_text=decision.raw_name,
        normalized_attributes=attrs,
        selected_type=candidate,
        type_candidates=[candidate],
        reason="由高召回检索结果编译物料录入草稿。",
        ready_to_create=True,
    )
    try:
        draft = planner.build_draft(classification, existing_item_codes=sorted(used_codes))
        prefix = planner.code_prefix(classification)
    except ValueError as exc:
        return str(exc)
    material_type = MaterialTypeDraft(
        type_id=candidate.type_id,
        top_group=candidate.top_group,
        material_family=candidate.material_family,
        standard_name=candidate.standard_name,
        definition=candidate.definition,
        includes=candidate.includes,
        excludes=candidate.excludes,
        aliases=list(type_row.aliases),
        attributes=candidate.attributes,
        item_group=draft.item_group,
        code_prefix=prefix,
        is_new=False,
    )
    output = MaterialItemDraft(
        draft_id=f"item-draft-{uuid4().hex}",
        source_rows=[decision.row_id],
        source_names=[decision.raw_name],
        action="create_sku",
        type_id=draft.type_id,
        standard_name=draft.standard_name,
        item_code=draft.item_code,
        item_name=draft.sku_name,
        item_group=draft.item_group,
        stock_uom=draft.stock_uom,
        required_specs=draft.required_specs,
        optional_specs=draft.optional_specs,
        normalized_attributes=attrs,
        material_type=material_type,
        item_doc=draft.item_doc,
    )
    output.validation_errors = _validate_draft(output)
    output.frozen_hash = _draft_hash(output)
    return output


def _recompile_existing_type_draft(
    original: MaterialItemDraft,
    classifier: MaterialTypeClassifier,
    planner: ItemMasterCreationPlanner,
    attrs: dict[str, str],
    used_codes: set[str],
) -> MaterialItemDraft:
    decision = type("Decision", (), {
        "type_id": original.type_id,
        "raw_name": original.source_names[0],
        "row_id": original.source_rows[0],
    })()
    compiled = _compile_existing_type_draft(decision, classifier, planner, attrs, used_codes)
    if isinstance(compiled, str):
        raise ValueError(compiled)
    compiled.draft_id = original.draft_id
    compiled.source_rows = list(original.source_rows)
    compiled.source_names = list(original.source_names)
    return compiled


def _compile_new_type_draft(
    decision: Any,
    attrs: dict[str, str],
    used_codes: set[str],
) -> MaterialItemDraft:
    standard_name = str(decision.standard_name or decision.raw_name).strip()
    top_group = str(decision.top_group_hint or "").strip()
    material_family = str(decision.material_family_hint or standard_name).strip()
    item_group = top_group
    type_values = {
        "top_group": top_group,
        "material_family": material_family,
        "standard_name": standard_name,
        "definition": f"经员工确认发布的标准物料类型：{standard_name}",
        "includes": str(decision.raw_name or "").strip(),
        "excludes": "",
        "aliases": list(dict.fromkeys([str(decision.raw_name or "").strip()])),
        "attributes": _attribute_templates(attrs, fallback_spec=str(decision.raw_spec or "").strip()),
        "item_group": item_group,
        "code_prefix": _runtime_code_prefix(top_group, material_family, standard_name),
        "is_new": True,
    }
    if not any(key != "uom" for key in attrs) and str(decision.raw_spec or "").strip():
        attrs = {**attrs, "spec": str(decision.raw_spec).strip()}
    original = MaterialItemDraft.model_construct(
        draft_id=f"item-draft-{uuid4().hex}",
        source_rows=[decision.row_id],
        source_names=[decision.raw_name],
        action="create_type_and_sku",
        revision=1,
    )
    return _compile_new_type_values(original, type_values, attrs, used_codes)


def _compile_new_type_values(
    original: MaterialItemDraft,
    type_values: dict[str, Any],
    attrs: dict[str, str],
    used_codes: set[str],
) -> MaterialItemDraft:
    top_group = str(type_values.get("top_group") or "").strip()
    family = str(type_values.get("material_family") or "").strip()
    standard_name = str(type_values.get("standard_name") or "").strip()
    prefix = str(type_values.get("code_prefix") or "").strip().upper()
    material_type = MaterialTypeDraft(
        type_id=stable_type_id(top_group, family, standard_name),
        top_group=top_group,
        material_family=family,
        standard_name=standard_name,
        definition=str(type_values.get("definition") or "").strip(),
        includes=str(type_values.get("includes") or "").strip(),
        excludes=str(type_values.get("excludes") or "").strip(),
        aliases=[str(value).strip() for value in type_values.get("aliases") or original.source_names if str(value).strip()],
        attributes=_attribute_templates(attrs),
        item_group=str(type_values.get("item_group") or "").strip(),
        code_prefix=prefix,
        is_new=True,
    )
    item_code = generate_next_item_code(prefix, sorted(used_codes)) if _valid_prefix(prefix) else f"{prefix or 'INVALID'}-000001"
    required_specs, optional_specs, identity_values = _render_specs(material_type.attributes, attrs)
    item_name = _sku_name(standard_name, identity_values)
    item_doc = {
        "item_code": item_code,
        "item_name": item_name,
        "item_group": material_type.item_group,
        "stock_uom": str(attrs.get("uom") or "").strip(),
        "description": _description(
            sku_name=item_name,
            type_id=material_type.type_id,
            standard_name=standard_name,
            required_specs=required_specs,
            optional_specs=optional_specs,
        ),
        "disabled": 0,
        "is_stock_item": 1,
        "is_purchase_item": 1,
        "is_sales_item": 0,
        "include_item_in_manufacturing": 0,
    }
    output = MaterialItemDraft(
        draft_id=original.draft_id,
        source_rows=list(original.source_rows),
        source_names=list(original.source_names),
        action="create_type_and_sku",
        type_id=material_type.type_id,
        standard_name=standard_name,
        item_code=item_code,
        item_name=item_name,
        item_group=material_type.item_group,
        stock_uom=item_doc["stock_uom"],
        required_specs=required_specs,
        optional_specs=optional_specs,
        normalized_attributes=attrs,
        material_type=material_type,
        item_doc=item_doc,
        revision=getattr(original, "revision", 1),
    )
    output.validation_errors = _validate_draft(output)
    output.frozen_hash = _draft_hash(output)
    return output


def _attribute_templates(attrs: dict[str, str], *, fallback_spec: str = "") -> list[dict[str, Any]]:
    values = dict(attrs)
    if not any(key != "uom" for key in values) and fallback_spec:
        values["spec"] = fallback_spec
    output: list[dict[str, Any]] = []
    for key in values:
        if key == "uom":
            continue
        if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", key):
            continue
        output.append({
            "attribute_key": key,
            "display_name": ATTRIBUTE_LABELS.get(key, key),
            "requirement": "required",
            "value_type": "text",
            "unit": "",
            "enum_values": [],
            "affects_sku_identity": True,
            "description": "由本次员工确认的首个 SKU 规格建立。",
        })
    return output


def _runtime_code_prefix(top_group: str, material_family: str, standard_name: str) -> str:
    digest = hashlib.sha256(f"{top_group}\0{material_family}\0{standard_name}".encode("utf-8")).hexdigest()[:6].upper()
    return f"MAT-{digest}"


def _valid_prefix(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9-]{2,29}", value))


def _validate_draft(draft: MaterialItemDraft) -> list[str]:
    errors: list[str] = []
    if not draft.stock_uom:
        errors.append("库存单位不能为空。")
    if not draft.item_group:
        errors.append("必须选择 ERPNext 中已存在的物料组。")
    if draft.action == "create_type_and_sku":
        if not draft.material_type.top_group:
            errors.append("新增标准类型必须确认一级分类。")
        if not draft.material_type.material_family:
            errors.append("新增标准类型必须确认物料族。")
        if not draft.material_type.standard_name:
            errors.append("新增标准类型必须确认标准名称。")
        if not _valid_prefix(draft.material_type.code_prefix):
            errors.append("编码前缀必须为 3-30 位大写字母、数字或连字符。")
        if not draft.material_type.attributes:
            errors.append("新增标准类型至少需要一个可识别首个 SKU 的规格属性。")
    return errors


def _draft_hash(draft: MaterialItemDraft) -> str:
    payload = draft.model_dump(mode="json", exclude={"frozen_hash", "status"})
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
