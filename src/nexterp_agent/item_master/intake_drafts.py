from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .coding import generate_next_item_code
from .high_recall import HighRecallBatchResult
from .item_creation import ItemMasterCreationPlanner
from .type_classifier import MaterialClassificationCandidate, MaterialClassificationResult, MaterialTypeClassifier


class MaterialItemDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str
    source_rows: list[str] = Field(min_length=1)
    source_names: list[str] = Field(min_length=1)
    type_id: str
    standard_name: str
    item_code: str
    item_name: str
    item_group: str
    stock_uom: str
    required_specs: str = ""
    optional_specs: str = ""
    item_doc: dict[str, Any]
    status: str = "pending_confirmation"


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
    """Compile new-SKU decisions into server-owned, non-executable drafts."""
    started = datetime.now(timezone.utc)
    planner = ItemMasterCreationPlanner(classifier)
    used_codes = set(existing_item_codes or [])
    # Release codes make the offline preview deterministic. Live ERPNext codes
    # are added by the service before this function is called when available.
    used_codes.update(str(row.get("item_code") or "") for row in classifier.release_resolver.rows)
    drafts: list[MaterialItemDraft] = []
    skipped: list[dict[str, str]] = []
    by_key: dict[tuple[str, tuple[tuple[str, str], ...]], MaterialItemDraft] = {}

    for decision in result.decisions:
        if decision.queue == "existing_sku":
            skipped.append({"row_id": decision.row_id, "reason": "已有 SKU，无需新增物料。"})
            continue
        if decision.queue != "new_sku" or not decision.type_id:
            skipped.append({
                "row_id": decision.row_id,
                "reason": "尚未形成可安全创建的现有物料类型，需先补充或确认。",
            })
            continue

        type_row = next((item for item in classifier.types if item.type_id == decision.type_id), None)
        if type_row is None:
            skipped.append({"row_id": decision.row_id, "reason": "标准物料类型已不在当前目录版本中。"})
            continue

        attrs = {str(key): str(value) for key, value in decision.normalized_attributes.items() if value not in (None, "")}
        attrs.setdefault("uom", decision.uom)
        identity = tuple(sorted((key, value) for key, value in attrs.items() if key != "uom"))
        key = (decision.type_id, identity)
        existing_draft = by_key.get(key)
        if existing_draft is not None:
            existing_draft.source_rows.append(decision.row_id)
            existing_draft.source_names.append(decision.raw_name)
            continue

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
        except ValueError as exc:
            skipped.append({"row_id": decision.row_id, "reason": str(exc)})
            continue

        used_codes.add(draft.item_code)
        item = MaterialItemDraft(
            draft_id=f"item-draft-{uuid4().hex}",
            source_rows=[decision.row_id],
            source_names=[decision.raw_name],
            type_id=draft.type_id,
            standard_name=draft.standard_name,
            item_code=draft.item_code,
            item_name=draft.sku_name,
            item_group=draft.item_group,
            stock_uom=draft.stock_uom,
            required_specs=draft.required_specs,
            optional_specs=draft.optional_specs,
            item_doc=draft.item_doc,
        )
        drafts.append(item)
        by_key[key] = item

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
                f"跳过 {len(skipped)} 行：已有 SKU、信息不足或未找到可用标准类型。",
                "草稿尚未写入 ERPNext，确认后才会执行录入。",
            ],
        },
    )
