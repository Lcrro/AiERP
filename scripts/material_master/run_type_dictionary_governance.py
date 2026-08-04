from __future__ import annotations

import argparse
import csv
from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from nexterp_agent.agent_runtime.deepseek_material_request import (  # noqa: E402
    call_deepseek_json,
    load_deepseek_settings,
)
from nexterp_agent.item_master.type_governance import (  # noqa: E402
    DetailedMappingResult,
    DetailedMappingReviewResult,
    GovernanceBatchInput,
    GovernanceGenerationResult,
    GovernanceReviewResult,
    GovernanceSnapshot,
    PROMPT_VERSION,
    approved_detail_family_keys,
    build_family_evidence,
    build_snapshot,
    names_requiring_detailed_mapping,
    pack_family_batches,
)
from nexterp_agent.item_master.type_governance_postgres import (  # noqa: E402
    PostgresTypeGovernanceCatalog,
)

from deepseek_family_governance import build_browser_payload  # noqa: E402


DEFAULT_INPUT = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "release_v1_0"
    / "material_master_release_v1_0.tsv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "material_master" / "governance_v0_5"
T = TypeVar("T", bound=BaseModel)

SNAPSHOT_FILES = {
    "material_type_dictionary": "material_type_dictionary.tsv",
    "material_type_aliases": "material_type_aliases.tsv",
    "material_attribute_templates": "material_attribute_templates.tsv",
    "material_name_decisions": "material_name_decisions.tsv",
    "sku_type_mapping": "sku_type_mapping.tsv",
    "material_governance_issues": "material_governance_issues.tsv",
}


def log_stage(batch_id: str, stage: str) -> None:
    print(f"{datetime.now().isoformat(timespec='seconds')} {batch_id}: {stage}", flush=True)


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), [
            {key: str(value or "").strip() for key, value in row.items()}
            for row in reader
        ]


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved_fields = fields or list(rows[0].keys() if rows else [])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=resolved_fields,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: (
                        "true"
                        if value is True
                        else "false"
                        if value is False
                        else ""
                        if value is None
                        else value
                    )
                    for key, value in row.items()
                }
            )


def build_generation_messages(batch: GovernanceBatchInput) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是土木工程企业的资深物料主数据架构师。你的任务是为输入的物料族建立稳定的"
                "三级标准物料名称字典，而不是逐条改写SKU。必须区分商品结构、连接接口、加工对象、"
                "材质、品牌、尺寸和包装等不同维度。只有长期稳定、采购员一望即知且确实改变商品类型"
                "的词才进入标准名称；直径、长度、规格、品牌和包装必须留在SKU属性。"
                "兼容性接口只有在它会决定设备能否使用时才允许进入标准名称。"
                "不得跨物料族移动，不得补造输入没有支持的商品类型。每个现有名称必须且只能有一个决定。"
                "只输出符合给定JSON Schema的JSON object。"
            ),
        },
        {
            "role": "system",
            "content": json.dumps(
                {
                    "prompt_version": PROMPT_VERSION,
                    "governance_rules": [
                        "为每个物料族单独建立类型，temporary_key只需在该族内唯一。",
                        "standard_name不得包含SKU尺寸、型号、品牌或包装数量。",
                        "definition、includes、excludes必须能解释类型边界。",
                        "属性键使用简短英文snake_case，显示名使用中文。",
                        "required只用于缺失会明显导致买错的属性，其余设为optional。",
                        "affects_sku_identity表示该属性不同是否应形成不同SKU。",
                        "keep表示现有名称已经合格；rename和merge只能指向一个类型。",
                        "无法仅凭压缩证据可靠拆分时使用needs_evidence，不要猜。",
                        "source_hash、top_group、material_family必须原样返回。",
                    ],
                    "output_schema": GovernanceGenerationResult.model_json_schema(),
                    "batch": batch.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
        },
    ]


def build_review_messages(
    batch: GovernanceBatchInput,
    generation: GovernanceGenerationResult,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是独立的物料主数据审计员。你没有参与生成阶段。请只根据原始压缩证据审查提案，"
                "检查标准名称是否混合了结构、材质、接口、用途、品牌或尺寸，类型边界是否重叠，"
                "旧名称是否全部覆盖，是否存在无依据推断，以及属性模板是否足以区分采购SKU。"
                "有任何实质问题必须判为revise或reject，不得为了通过而放宽标准。"
                "每个提议类型和每个名称决定都必须有一条复核记录。只输出JSON object。"
            ),
        },
        {
            "role": "system",
            "content": json.dumps(
                {
                    "prompt_version": PROMPT_VERSION,
                    "review_rules": [
                        "top_group、material_family、source_hash必须与输入原样一致。",
                        "family verdict只有在全部类型和名称决定都approve时才可approve。",
                        "尺寸、品牌和包装出现在standard_name时必须reject。",
                        "仅由材质或用途构成、不能表达商品结构的名称通常应revise。",
                        "SDS-Plus和SDS-Max等设备兼容接口可与冲击钻头结构共同构成稳定商品名。",
                        "不要提出新的完整治理方案，只审查给定提案。",
                    ],
                    "output_schema": GovernanceReviewResult.model_json_schema(),
                    "source_evidence": batch.model_dump(mode="json"),
                    "proposal": generation.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
        },
    ]


def _detailed_source_payload(
    batch: GovernanceBatchInput,
    generation: GovernanceGenerationResult,
    source_rows: list[dict[str, str]],
    *,
    family_keys: set[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    required = names_requiring_detailed_mapping(batch, generation)
    generation_by_key = {
        (item.top_group, item.material_family): item for item in generation.families
    }
    payload: list[dict[str, Any]] = []
    for family in batch.families:
        key = (family.top_group, family.material_family)
        if family_keys is not None and key not in family_keys:
            continue
        required_names = required.get(key, set())
        if not required_names:
            continue
        proposal = generation_by_key[key]
        rows = [
            {
                "item_code": row.get("item_code", ""),
                "current_name": row.get("item_name", ""),
                "sku_name": row.get("sku_name", ""),
                "required_specs": row.get("required_specs", ""),
                "optional_specs": row.get("optional_specs", ""),
                "aliases": row.get("aliases", ""),
                "stock_uom": row.get("stock_uom", ""),
            }
            for row in source_rows
            if row.get("top_group") == family.top_group
            and row.get("material_family") == family.material_family
            and row.get("item_name") in required_names
        ]
        payload.append(
            {
                "top_group": family.top_group,
                "material_family": family.material_family,
                "source_hash": family.source_hash,
                "names_requiring_detail": sorted(required_names),
                "allowed_types": [
                    {
                        "temporary_key": item.temporary_key,
                        "standard_name": item.standard_name,
                        "definition": item.definition,
                        "includes": item.includes,
                        "excludes": item.excludes,
                        "attribute_keys": [attribute.attribute_key for attribute in item.attributes],
                    }
                    for item in proposal.types
                ],
                "sku_rows": rows,
            }
        )
    return payload


def build_detailed_mapping_messages(
    batch: GovernanceBatchInput,
    generation: GovernanceGenerationResult,
    source_rows: list[dict[str, str]],
    *,
    family_keys: set[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是物料主数据的SKU证据映射员。上一步发现某些旧名称过于笼统或需要拆分。"
                "请逐个读取完整SKU证据，只能映射到给定allowed_types中的temporary_key。"
                "不得新建类型、不得修改SKU字段、不得根据品牌猜测结构。"
                "证据不足时选择定义最宽但仍真实的已有类型，并降低confidence；confidence低于0.75"
                "的项目将进入问题队列。每个输入item_code必须且只能输出一次。只输出JSON object。"
            ),
        },
        {
            "role": "system",
            "content": json.dumps(
                {
                    "output_schema": DetailedMappingResult.model_json_schema(),
                    "families": _detailed_source_payload(
                        batch,
                        generation,
                        source_rows,
                        family_keys=family_keys,
                    ),
                },
                ensure_ascii=False,
            ),
        },
    ]


def build_detailed_review_messages(
    batch: GovernanceBatchInput,
    generation: GovernanceGenerationResult,
    source_rows: list[dict[str, str]],
    mapping: DetailedMappingResult,
    *,
    family_keys: set[tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是独立的SKU类型映射审计员。请核对每个item_code是否根据现有名称、SKU名称、"
                "规格和别名映射到了正确的allowed type。不得因为材质或品牌相同就假定结构相同。"
                "每个映射都必须有复核记录；有歧义就判revise。只输出JSON object。"
            ),
        },
        {
            "role": "system",
            "content": json.dumps(
                {
                    "output_schema": DetailedMappingReviewResult.model_json_schema(),
                    "source_evidence": _detailed_source_payload(
                        batch,
                        generation,
                        source_rows,
                        family_keys=family_keys,
                    ),
                    "mapping_proposal": mapping.model_dump(mode="json"),
                },
                ensure_ascii=False,
            ),
        },
    ]


def call_typed_json(
    messages: list[dict[str, str]],
    model_type: type[T],
    *,
    settings: Any,
    attempts: int = 2,
) -> tuple[T, dict[str, Any]]:
    current_messages = list(messages)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            raw = call_deepseek_json(current_messages, settings=settings)
            return model_type.model_validate(raw), raw
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            current_messages.extend(
                [
                    {
                        "role": "system",
                        "content": (
                            "上一份JSON未通过结构校验。请修正后重新输出完整JSON。"
                            f"校验错误：{str(exc)[:2500]}"
                        ),
                    }
                ]
            )
            time.sleep(0.5)
    raise RuntimeError("typed DeepSeek call failed") from last_error


def run_batch(
    batch: GovernanceBatchInput,
    *,
    source_rows: list[dict[str, str]],
    output_dir: Path,
    settings: Any,
    reuse_responses: bool,
    defer_detailed: bool = False,
) -> GovernanceSnapshot:
    log_stage(batch.batch_id, "generation_started")
    batch_dir = output_dir / "batches" / batch.batch_id
    request_dir = batch_dir / "requests"
    response_dir = batch_dir / "responses"
    request_dir.mkdir(parents=True, exist_ok=True)
    response_dir.mkdir(parents=True, exist_ok=True)

    generation_messages = build_generation_messages(batch)
    generation_request = request_dir / "generation.json"
    generation_response = response_dir / "generation.json"
    generation_request.write_text(
        json.dumps({"messages": generation_messages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if reuse_responses and generation_response.exists():
        generation_raw = json.loads(generation_response.read_text(encoding="utf-8"))
        generation = GovernanceGenerationResult.model_validate(generation_raw)
        log_stage(batch.batch_id, "generation_reused")
    else:
        generation, generation_raw = call_typed_json(
            generation_messages,
            GovernanceGenerationResult,
            settings=settings,
        )
        generation_response.write_text(
            json.dumps(generation_raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        log_stage(batch.batch_id, "generation_completed")

    log_stage(batch.batch_id, "review_started")
    review_messages = build_review_messages(batch, generation)
    review_request = request_dir / "review.json"
    review_response = response_dir / "review.json"
    review_request.write_text(
        json.dumps({"messages": review_messages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if reuse_responses and review_response.exists():
        review_raw = json.loads(review_response.read_text(encoding="utf-8"))
        review = GovernanceReviewResult.model_validate(review_raw)
        log_stage(batch.batch_id, "review_reused")
    else:
        review, review_raw = call_typed_json(
            review_messages,
            GovernanceReviewResult,
            settings=settings,
        )
        review_response.write_text(
            json.dumps(review_raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        log_stage(batch.batch_id, "review_completed")

    detailed_mapping: DetailedMappingResult | None = None
    detailed_review: DetailedMappingReviewResult | None = None
    approved_detail_families = approved_detail_family_keys(batch, generation, review)
    if approved_detail_families and defer_detailed:
        log_stage(
            batch.batch_id,
            f"detailed_mapping_deferred_{len(approved_detail_families)}_families",
        )
    elif approved_detail_families:
        log_stage(batch.batch_id, "detailed_mapping_started")
        detailed_messages = build_detailed_mapping_messages(
            batch,
            generation,
            source_rows,
            family_keys=approved_detail_families,
        )
        detailed_request = request_dir / "detailed_mapping.json"
        detailed_response = response_dir / "detailed_mapping.json"
        detailed_request.write_text(
            json.dumps({"messages": detailed_messages}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if reuse_responses and detailed_response.exists():
            detailed_raw = json.loads(detailed_response.read_text(encoding="utf-8"))
            detailed_mapping = DetailedMappingResult.model_validate(detailed_raw)
            log_stage(batch.batch_id, "detailed_mapping_reused")
        else:
            detailed_mapping, detailed_raw = call_typed_json(
                detailed_messages,
                DetailedMappingResult,
                settings=settings,
            )
            detailed_response.write_text(
                json.dumps(detailed_raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            log_stage(batch.batch_id, "detailed_mapping_completed")

        log_stage(batch.batch_id, "detailed_review_started")
        detailed_review_messages = build_detailed_review_messages(
            batch,
            generation,
            source_rows,
            detailed_mapping,
            family_keys=approved_detail_families,
        )
        detailed_review_request = request_dir / "detailed_review.json"
        detailed_review_response = response_dir / "detailed_review.json"
        detailed_review_request.write_text(
            json.dumps({"messages": detailed_review_messages}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if reuse_responses and detailed_review_response.exists():
            detailed_review_raw = json.loads(detailed_review_response.read_text(encoding="utf-8"))
            detailed_review = DetailedMappingReviewResult.model_validate(detailed_review_raw)
            log_stage(batch.batch_id, "detailed_review_reused")
        else:
            detailed_review, detailed_review_raw = call_typed_json(
                detailed_review_messages,
                DetailedMappingReviewResult,
                settings=settings,
            )
            detailed_review_response.write_text(
                json.dumps(detailed_review_raw, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            log_stage(batch.batch_id, "detailed_review_completed")

    snapshot = build_snapshot(
        batch,
        generation,
        review,
        source_rows,
        model=settings.model,
        review_model=settings.model,
        detailed_mapping=detailed_mapping,
        detailed_review=detailed_review,
    )
    (batch_dir / "snapshot.json").write_text(
        snapshot.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    log_stage(batch.batch_id, f"snapshot_{snapshot.batch['status']}")
    return snapshot


def export_database_snapshots(
    catalog: PostgresTypeGovernanceCatalog,
    output_dir: Path,
) -> dict[str, list[dict[str, Any]]]:
    exports = catalog.export_rows()
    for key, filename in SNAPSHOT_FILES.items():
        write_tsv(output_dir / filename, exports.get(key, []))
    return exports


def build_preview(
    source_fields: list[str],
    source_rows: list[dict[str, str]],
    exports: dict[str, list[dict[str, Any]]],
    output_dir: Path,
) -> dict[str, Any]:
    mappings = {str(row["item_code"]): row for row in exports.get("sku_type_mapping", [])}
    decisions = {
        (str(row["top_group"]), str(row["material_family"]), str(row["current_name"])): row
        for row in exports.get("material_name_decisions", [])
    }
    attributes: dict[str, list[dict[str, Any]]] = {}
    for row in exports.get("material_attribute_templates", []):
        attributes.setdefault(str(row["type_id"]), []).append(row)
    issues: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    item_issues: dict[str, list[dict[str, Any]]] = {}
    for row in exports.get("material_governance_issues", []):
        item_code = str(row.get("item_code", ""))
        if item_code:
            item_issues.setdefault(item_code, []).append(row)
            continue
        key = (str(row["top_group"]), str(row["material_family"]), str(row["current_name"]))
        issues.setdefault(key, []).append(row)

    extra_fields = [
        "v05_original_item_name",
        "v05_type_id",
        "v05_standard_name",
        "v05_decision",
        "v05_review",
        "v05_validation",
        "v05_attribute_template",
        "v05_issues",
    ]
    preview_rows: list[dict[str, Any]] = []
    for source in source_rows:
        row: dict[str, Any] = dict(source)
        key = (source.get("top_group", ""), source.get("material_family", ""), source.get("item_name", ""))
        decision = decisions.get(key)
        mapping = mappings.get(source.get("item_code", ""))
        row["v05_original_item_name"] = source.get("item_name", "")
        row["v05_type_id"] = str(mapping.get("type_id", "")) if mapping else ""
        row["v05_standard_name"] = str(mapping.get("standard_name", "")) if mapping else ""
        row["v05_decision"] = (
            f"{decision.get('action', '')}：{decision.get('reason', '')}" if decision else "未治理"
        )
        row["v05_review"] = str(decision.get("review_summary", "")) if decision else ""
        row["v05_validation"] = str(decision.get("decision_status", "")) if decision else "not_processed"
        row["v05_attribute_template"] = "；".join(
            f"{attribute.get('display_name', '')}({attribute.get('requirement', '')})"
            for attribute in attributes.get(row["v05_type_id"], [])
        )
        row_issues = [
            *issues.get(key, []),
            *item_issues.get(source.get("item_code", ""), []),
        ]
        row["v05_issues"] = "；".join(str(item.get("detail", "")) for item in row_issues)
        if mapping and str(mapping.get("mapping_status")) == "frozen":
            row["item_name"] = str(mapping.get("standard_name") or row["item_name"])
            row["quality_level"] = "standard"
            note = f"v0.5标准类型：{row['v05_type_id']}；旧名称：{row['v05_original_item_name']}"
            row["governance_note"] = "；".join(
                value for value in (row.get("governance_note", ""), note) if value
            )
        else:
            row["quality_level"] = "needs_review"
        preview_rows.append(row)

    preview_path = output_dir / "material_master_type_governed_preview.tsv"
    write_tsv(preview_path, preview_rows, source_fields + extra_fields)
    payload = build_browser_payload(
        preview_rows,
        source=preview_path,
    )
    payload["v05_governance"] = {
        "type_count": len(exports.get("material_type_dictionary", [])),
        "mapped_sku_count": len(mappings),
        "decision_count": len(decisions),
        "open_issue_count": sum(
            1 for row in exports.get("material_governance_issues", []) if row.get("status") == "open"
        ),
        "prompt_version": PROMPT_VERSION,
    }
    browser_path = output_dir / "material_master_type_governed_browser_data.json"
    browser_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload["v05_governance"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the material type dictionary with two DeepSeek passes.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--all", action="store_true", help="Govern every family that has not been frozen.")
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Refresh TSV, browser data, and coverage summary without calling DeepSeek.",
    )
    parser.add_argument("--top-group", default="工具耗材")
    parser.add_argument("--material-family", default="钻头")
    parser.add_argument("--max-names", type=int, default=160)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--reuse-responses", action="store_true")
    parser.add_argument(
        "--defer-detailed",
        action="store_true",
        help="Persist reviewed family decisions while leaving detailed SKU mappings as explicit issues.",
    )
    parser.add_argument("--force", action="store_true", help="Ignore matching frozen source hashes.")
    parser.add_argument(
        "--batch-id",
        default="",
        help="Replay one saved batch without regrouping other families.",
    )
    return parser.parse_args()


def load_saved_batch(output_dir: Path, batch_id: str) -> GovernanceBatchInput:
    request_path = output_dir / "batches" / batch_id / "requests" / "generation.json"
    if not request_path.exists():
        raise RuntimeError(f"Saved batch request not found: {request_path}")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    messages = request.get("messages") or []
    if len(messages) < 2:
        raise RuntimeError(f"Saved batch request is incomplete: {request_path}")
    payload = json.loads(messages[1]["content"])
    batch = GovernanceBatchInput.model_validate(payload["batch"])
    if batch.batch_id != batch_id:
        raise RuntimeError(f"Saved batch id mismatch: expected {batch_id}, got {batch.batch_id}")
    return batch


def main() -> int:
    args = parse_args()
    load_dotenv(REPO_ROOT / ".env")
    dsn = os.getenv("MATERIAL_CATALOG_DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("MATERIAL_CATALOG_DATABASE_URL is required")
    source_fields, source_rows = read_tsv(args.input)
    catalog = PostgresTypeGovernanceCatalog(dsn)
    settings = replace(load_deepseek_settings(), timeout_seconds=240)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if args.export_only:
        families = build_family_evidence(source_rows)
        batches = []
    elif args.batch_id:
        batches = [load_saved_batch(args.output_dir, args.batch_id)]
        families = list(batches[0].families)
    else:
        families = build_family_evidence(source_rows)
        if not args.all:
            families = [
                family
                for family in families
                if family.top_group == args.top_group and family.material_family == args.material_family
            ]
        if not families:
            raise RuntimeError("No matching material families found")
        frozen_hashes = catalog.frozen_family_hashes(prompt_version=PROMPT_VERSION)
        if not args.force:
            families = [
                family
                for family in families
                if frozen_hashes.get((family.top_group, family.material_family)) != family.source_hash
            ]
        batches = pack_family_batches(families, max_names=args.max_names) if families else []

    failures: list[dict[str, str]] = []
    completed: list[dict[str, Any]] = []
    if batches:
        with ThreadPoolExecutor(max_workers=max(1, min(args.concurrency, len(batches)))) as executor:
            futures = {
                executor.submit(
                    run_batch,
                    batch,
                    source_rows=source_rows,
                    output_dir=args.output_dir,
                    settings=settings,
                    reuse_responses=args.reuse_responses,
                    defer_detailed=args.defer_detailed,
                ): batch
                for batch in batches
            }
            for future in as_completed(futures):
                batch = futures[future]
                try:
                    snapshot = future.result()
                    catalog.persist_snapshot(snapshot)
                    completed.append(snapshot.batch)
                    print(
                        f"{batch.batch_id}: {snapshot.batch['status']} "
                        f"({snapshot.batch['family_count']} families, {snapshot.batch['name_count']} names)",
                        flush=True,
                    )
                except Exception as exc:
                    failures.append({"batch_id": batch.batch_id, "error": str(exc)})
                    print(f"{batch.batch_id}: failed: {exc}", file=sys.stderr, flush=True)

    exports = export_database_snapshots(catalog, args.output_dir)
    preview_summary = build_preview(source_fields, source_rows, exports, args.output_dir)
    source_codes = {row.get("item_code", "") for row in source_rows if row.get("item_code")}
    mapped_codes = {
        str(row.get("item_code", ""))
        for row in exports.get("sku_type_mapping", [])
        if row.get("item_code")
    }
    issue_codes = {
        str(row.get("item_code", ""))
        for row in exports.get("material_governance_issues", [])
        if row.get("item_code") and row.get("status") == "open"
    }
    uncovered_codes = source_codes - mapped_codes - issue_codes
    run_summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(args.input),
        "prompt_version": PROMPT_VERSION,
        "model": settings.model,
        "selected_family_count": len(families),
        "batch_count": len(batches),
        "completed_batches": completed,
        "failures": failures,
        "preview": preview_summary,
        "coverage": {
            "source_sku_count": len(source_codes),
            "mapped_sku_count": len(source_codes & mapped_codes),
            "issue_covered_sku_count": len((source_codes - mapped_codes) & issue_codes),
            "uncovered_sku_count": len(uncovered_codes),
            "all_skus_accounted_for": not uncovered_codes,
        },
    }
    summary_name = (
        f"retry-summary-{args.batch_id}.json"
        if args.batch_id
        else "summary.json"
    )
    (args.output_dir / summary_name).write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(run_summary, ensure_ascii=False, indent=2), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
