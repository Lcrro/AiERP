"""Publish a frozen local procurement batch into the internal GPC workbench.

This module only rewrites the two ignored runtime JSONL files consumed by the
read-only GPC browser.  It neither calls ERPNext nor promotes any ERPNext Item.
Publication is sparse: exact source variants become actual records, duplicate
purchases are merged, held/excluded reviews never become materials, and the
complete output is validated against the imported GPC package before replace.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .procurement_templates import ProcurementTemplateRegistry
from .material_catalog_normalization import canonical_material_name, canonical_standard_type
from .reference_catalog import GpcReferenceIndex
from .reference_catalog_database import (
    DEFAULT_REFERENCE_CATALOG_DATABASE_PATH,
    ReferenceCatalogDatabase,
)
from .source_identity import (
    DEFAULT_SOURCE_DATASET,
    DEFAULT_SOURCE_DOCUMENT,
    DEFAULT_SOURCE_SHEET,
    make_source_record,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNTIME_ROOT = ROOT / ".runtime" / "material-master" / "batch-pilot"
DEFAULT_PLACEMENTS_PATH = ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl"
DEFAULT_PROFILES_PATH = ROOT / ".runtime" / "material-master" / "gpc-procurement-type-profiles.jsonl"
DEFAULT_GPC_ROOT = ROOT / ".runtime" / "gpc-reference"
DEFAULT_GPC_VERSION = "2026-05"
DEFAULT_INTERNAL_EXTENSIONS_PATH = ROOT / "data" / "material_master" / "gpc_internal_extensions_v0_1.json"
_PROFILE_PREFIX = "LH-PUB-"
_MATERIAL_PREFIX = "LH-GPC-P"
_OFFER_ATTRIBUTE_KEYS = {"品牌", "供应商", "包装", "配置"}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not Path(path).is_file():
        return []
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with Path(path).open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def _profile_id(standard_type: str, gpc_code: str) -> str:
    return f"{_PROFILE_PREFIX}{_stable_hash([_normalized(standard_type), gpc_code])[:12].upper()}"


def _material_id(source_row: int, variant_index: int = 0) -> str:
    suffix = "" if variant_index == 0 else f"-{chr(ord('A') + variant_index - 1)}"
    return f"{_MATERIAL_PREFIX}{source_row:04d}{suffix}"


def _split_value(value: str, count: int) -> list[str] | None:
    parts = [part.strip() for part in str(value or "").split("/") if part.strip()]
    return parts if count > 1 and len(parts) == count else None


def _compact_groups(
    procurement_attributes: Mapping[str, Any],
    price_drivers: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    attributes: dict[str, str] = {}
    prices = {
        str(key).strip(): str(value).strip()
        for key, value in price_drivers.items()
        if str(key).strip() and str(value).strip()
    }
    for key, value in procurement_attributes.items():
        clean_key = str(key).strip()
        clean_value = str(value).strip()
        if not clean_key or not clean_value:
            continue
        if clean_key in _OFFER_ATTRIBUTE_KEYS:
            prices.setdefault("品牌/包装要求" if clean_key in {"品牌", "包装"} else clean_key, clean_value)
            continue
        if len(attributes) < 4:
            attributes[clean_key] = clean_value
    return attributes, dict(list(prices.items())[:3])


def _material_name(standard_type: str, attributes: Mapping[str, str]) -> str:
    values = []
    type_key = _normalized(standard_type)
    for value in attributes.values():
        if _normalized(value) == type_key or value in values:
            continue
        values.append(value)
    return "｜".join([standard_type, *values]) if values else standard_type


class ProcurementBatchGpcPublisher:
    def __init__(
        self,
        *,
        batch_runtime_root: Path = DEFAULT_RUNTIME_ROOT,
        placements_path: Path = DEFAULT_PLACEMENTS_PATH,
        profiles_path: Path = DEFAULT_PROFILES_PATH,
        gpc_runtime_root: Path = DEFAULT_GPC_ROOT,
        gpc_version: str = DEFAULT_GPC_VERSION,
        database_path: Path | None = None,
    ) -> None:
        self.batch_runtime_root = Path(batch_runtime_root).resolve()
        self.placements_path = Path(placements_path).resolve()
        self.profiles_path = Path(profiles_path).resolve()
        self.gpc_runtime_root = Path(gpc_runtime_root).resolve()
        self.gpc_version = str(gpc_version)
        use_default_database = (
            self.gpc_runtime_root == DEFAULT_GPC_ROOT.resolve()
            and self.placements_path == DEFAULT_PLACEMENTS_PATH.resolve()
            and self.profiles_path == DEFAULT_PROFILES_PATH.resolve()
        )
        self.database = ReferenceCatalogDatabase(
            Path(database_path).resolve()
            if database_path is not None
            else DEFAULT_REFERENCE_CATALOG_DATABASE_PATH
        ) if database_path is not None or use_default_database else None
        if self.database is not None and self.database.is_ready("gpc"):
            self.catalog = self.database.load_gpc_index()
        else:
            self.catalog = GpcReferenceIndex.from_runtime(
                self.gpc_runtime_root,
                self.gpc_version,
                internal_extensions_path=DEFAULT_INTERNAL_EXTENSIONS_PATH,
            )
        self.template_registry = ProcurementTemplateRegistry.from_files()

    def _job_dir(self, job_id: str) -> Path:
        root = (self.batch_runtime_root / "jobs").resolve()
        directory = (root / str(job_id or "").strip()).resolve()
        if root not in directory.parents or not directory.is_dir():
            raise ValueError("批处理任务不存在")
        return directory

    @staticmethod
    def _curations(path: Path | None) -> dict[str, dict[str, Any]]:
        if path is None:
            return {}
        return {str(row.get("cluster_id")): row for row in _load_jsonl(Path(path)) if row.get("cluster_id")}

    @staticmethod
    def _source_groups(source_rows: Iterable[int], source_index: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = {}
        for source_row in source_rows:
            row = source_index[int(source_row)]
            key = str(row.get("exact_key") or row.get("raw_name") or source_row)
            group = groups.setdefault(key, {"source_rows": [], "raw_name": str(row.get("raw_name") or "")})
            group["source_rows"].append(int(source_row))
        return list(groups.values())

    def _base_placement(
        self,
        *,
        job_id: str,
        material_id: str,
        source_rows: list[int],
        standard_type: str,
        material_name: str,
        gpc_code: str,
        stock_uom: str,
        attributes: Mapping[str, Any],
        prices: Mapping[str, Any],
        specification_basis: str,
        confidence: str,
        mapping_quality: str = "exact",
    ) -> dict[str, Any]:
        standard_type = canonical_standard_type(standard_type)
        compact_attributes, compact_prices = _compact_groups(attributes, prices)
        if not compact_attributes:
            compact_attributes = {"类型/规格": standard_type}
        if not compact_prices:
            compact_prices = {"质量要求": "符合国家/行业通用标准，质量可靠"}
        node = self.catalog.candidate_brick(gpc_code)
        if node is None:
            raise ValueError(f"发布候选未挂到有效目录末级：{material_id} -> {gpc_code}")
        is_internal = node.get("kind") == "internal_type"
        notes = [
            (
                f"归入“{node.get('working_name')}”标准类型"
                if is_internal
                else f"按 GPC Brick {gpc_code} {node.get('working_name') or node.get('official_name')} 归类"
            ),
            "只录入实际发生规格；未展开属性笛卡尔积",
        ]
        if mapping_quality == "broad_fallback":
            notes.insert(1, "GPC 仅作宽口径参考映射，内部标准类型保留施工语义")
        placement = {
            "material_id": material_id,
            "publication_job_id": job_id,
            "project": "龙华项目",
            "source_reference": f"实际采购清单｜{job_id}",
            "source_rows": sorted(set(int(value) for value in source_rows)),
            "standard_type": standard_type,
            "material_name": material_name or _material_name(standard_type, compact_attributes),
            "gpc_brick_code": gpc_code,
            "classification_source": "nexterp_internal" if is_internal else "gpc",
            "internal_category_code": gpc_code if is_internal else "",
            "confidence": confidence,
            "review_status": "首批候选已录入",
            "completeness_status": "完整",
            "specification_basis": specification_basis,
            "stock_uom": stock_uom,
            "procurement_attributes": compact_attributes,
            "price_drivers": compact_prices,
            "gpc_notes": notes[:3],
            "questions": [],
        }
        placement["material_name"] = canonical_material_name(placement)
        return placement

    def _direct_materials(
        self,
        job_id: str,
        decisions: Iterable[Mapping[str, Any]],
        source_index: Mapping[int, Mapping[str, Any]],
        curations: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]], list[dict[str, Any]]]:
        materials: list[dict[str, Any]] = []
        specs: dict[tuple[str, str], dict[str, Any]] = {}
        held: list[dict[str, Any]] = []
        for decision in decisions:
            if decision.get("queue") not in {"ready_new_type", "ready_new_sku"}:
                continue
            cluster_id = str(decision.get("cluster_id") or "")
            curation = dict(curations.get(cluster_id) or {})
            if curation.get("publish") is False:
                held.append({
                    "cluster_id": cluster_id,
                    "source_rows": list(decision.get("source_rows") or []),
                    "raw_names": list(decision.get("raw_names") or []),
                    "reason": str(curation.get("reason") or "发布门禁暂缓"),
                })
                continue
            candidate = deepcopy(dict(decision.get("material_candidate") or {}))
            standard_type = str(curation.get("standard_type") or candidate.get("standard_type") or decision.get("standard_type") or "").strip()
            gpc_code = str(curation.get("gpc_brick_code") or candidate.get("gpc_brick_code") or decision.get("gpc_brick_code") or "").strip()
            main_template_id = str(curation.get("main_template_id") or decision.get("main_template_id") or "").strip()
            constraint_ids = list(curation.get("constraint_ids") or decision.get("constraint_ids") or [])
            stock_uom = str(curation.get("stock_uom") or candidate.get("stock_uom") or "件").strip()
            groups = self._source_groups(decision.get("source_rows") or [], source_index)
            curated_variants = list(curation.get("variants") or [])
            variants: list[dict[str, Any]] = []
            if curated_variants:
                variants = [deepcopy(dict(row)) for row in curated_variants]
            else:
                count = len(groups)
                base_attributes = dict(candidate.get("procurement_attributes") or {})
                for index, group in enumerate(groups):
                    attributes = {}
                    for key, value in base_attributes.items():
                        split = _split_value(str(value), count)
                        attributes[key] = split[index] if split else value
                    variants.append({
                        "source_rows": list(group["source_rows"]),
                        "material_name": candidate.get("material_name") if count == 1 else "",
                        "procurement_attributes": attributes,
                        "price_drivers": dict(candidate.get("price_drivers") or {}),
                    })
            for index, variant in enumerate(variants, start=1):
                variant_type = str(variant.get("standard_type") or standard_type).strip()
                variant_code = str(variant.get("gpc_brick_code") or gpc_code).strip()
                attributes = dict(variant.get("procurement_attributes") or candidate.get("procurement_attributes") or {})
                prices = dict(variant.get("price_drivers") or candidate.get("price_drivers") or {})
                compact_attributes, compact_prices = _compact_groups(attributes, prices)
                first_row = min(int(value) for value in (variant.get("source_rows") or decision.get("source_rows") or [0]))
                placement = self._base_placement(
                    job_id=job_id,
                    material_id=_material_id(first_row, index if len(variants) > 1 else 0),
                    source_rows=list(variant.get("source_rows") or decision.get("source_rows") or []),
                    standard_type=variant_type,
                    material_name=str(variant.get("material_name") or _material_name(variant_type, compact_attributes)),
                    gpc_code=variant_code,
                    stock_uom=str(variant.get("stock_uom") or stock_uom),
                    attributes=compact_attributes,
                    prices=compact_prices,
                    specification_basis=str(curation.get("specification_basis") or candidate.get("specification_basis") or "采购原文与已授权的施工常用值"),
                    confidence=str(curation.get("confidence") or candidate.get("confidence") or decision.get("confidence") or "批处理候选"),
                    mapping_quality=str(curation.get("gpc_mapping_quality") or "exact"),
                )
                materials.append(placement)
                specs[(variant_type, variant_code)] = {
                    "main_template_id": str(variant.get("main_template_id") or main_template_id),
                    "constraint_ids": list(variant.get("constraint_ids") or constraint_ids),
                }
        return materials, specs, held

    def _reviewed_materials(
        self,
        job_id: str,
        release: Mapping[str, Any],
        curations: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        materials: list[dict[str, Any]] = []
        specs: dict[tuple[str, str], dict[str, Any]] = {}
        for review in release.get("reviews") or []:
            materialization = str(review.get("materialization") or "")
            if materialization not in {"ready", "split_ready"}:
                continue
            curation = dict(curations.get(str(review.get("cluster_id") or "")) or {})
            if curation.get("publish") is False:
                continue
            final = dict(review.get("final_material") or {})
            standard_type = str(curation.get("standard_type") or final.get("standard_type") or "").strip()
            gpc_code = str(curation.get("gpc_brick_code") or final.get("gpc_brick_code") or "").strip()
            main_template_id = str(curation.get("main_template_id") or final.get("main_template_id") or "").strip()
            constraint_ids = list(curation.get("constraint_ids") or final.get("constraint_ids") or [])
            curated_variants = list(curation.get("variants") or [])
            if curated_variants:
                variants = [deepcopy(dict(row)) for row in curated_variants]
            elif materialization == "split_ready":
                variants = list(review.get("variants") or [])
            else:
                variants = [{
                    "source_rows": list(review.get("source_rows") or []),
                    "procurement_attributes": dict(final.get("procurement_attributes") or {}),
                    "price_drivers": dict(final.get("price_drivers") or {}),
                }]
            for index, raw_variant in enumerate(variants, start=1):
                variant = dict(raw_variant)
                variant_type = str(variant.get("standard_type") or standard_type).strip()
                variant_code = str(variant.get("gpc_brick_code") or gpc_code).strip()
                attributes = dict(variant.get("attributes") or variant.get("procurement_attributes") or final.get("procurement_attributes") or {})
                prices = dict(variant.get("price_drivers") or final.get("price_drivers") or {})
                compact_attributes, compact_prices = _compact_groups(attributes, prices)
                source_rows = list(variant.get("source_rows") or ([variant["source_row"]] if variant.get("source_row") else review.get("source_rows") or []))
                first_row = min(int(value) for value in source_rows)
                placement = self._base_placement(
                    job_id=job_id,
                    material_id=_material_id(first_row, index if len(variants) > 1 else 0),
                    source_rows=source_rows,
                    standard_type=variant_type,
                    material_name=str(variant.get("material_name") or _material_name(variant_type, compact_attributes)),
                    gpc_code=variant_code,
                    stock_uom=str(variant.get("stock_uom") or curation.get("stock_uom") or final.get("stock_uom") or "件"),
                    attributes=compact_attributes,
                    prices=compact_prices,
                    specification_basis=str(curation.get("specification_basis") or review.get("rationale") or "首批边界项审阅确认"),
                    confidence=str(curation.get("confidence") or (
                        f"边界审阅{review.get('action')}+用途修正"
                        if curation else f"边界审阅{review.get('action')}"
                    )),
                    mapping_quality=str(variant.get("gpc_mapping_quality") or curation.get("gpc_mapping_quality") or final.get("gpc_mapping_quality") or "exact"),
                )
                materials.append(placement)
                specs[(variant_type, variant_code)] = {
                    "main_template_id": str(variant.get("main_template_id") or main_template_id),
                    "constraint_ids": list(variant.get("constraint_ids") or constraint_ids),
                }
        return materials, specs

    @staticmethod
    def _merge_duplicate_materials(materials: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for raw in materials:
            row = deepcopy(dict(raw))
            fingerprint = _stable_hash({
                "standard_type": _normalized(row.get("standard_type")),
                "gpc_brick_code": row.get("gpc_brick_code"),
                "procurement_attributes": {
                    key: _normalized(value) for key, value in dict(row.get("procurement_attributes") or {}).items()
                },
            })
            if fingerprint not in merged:
                merged[fingerprint] = row
                continue
            existing = merged[fingerprint]
            existing["source_rows"] = sorted(set([*existing.get("source_rows", []), *row.get("source_rows", [])]))
            existing["material_id"] = min(str(existing["material_id"]), str(row["material_id"]))
        return sorted(merged.values(), key=lambda row: (min(row.get("source_rows") or [10**9]), row["material_id"]))

    @staticmethod
    def _merge_existing_source_rows(
        materials: Iterable[Mapping[str, Any]],
        decisions: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Attach repeated purchase rows to an already curated workbench material."""
        source_rows_by_material: dict[str, set[int]] = defaultdict(set)
        for decision in decisions:
            if decision.get("queue") != "existing_candidate":
                continue
            material_id = str(dict(decision.get("material_candidate") or {}).get("material_id") or "")
            if material_id:
                source_rows_by_material[material_id].update(int(value) for value in decision.get("source_rows") or [])
        merged: list[dict[str, Any]] = []
        for raw in materials:
            row = deepcopy(dict(raw))
            repeated = source_rows_by_material.get(str(row.get("material_id") or ""))
            if repeated:
                row["source_rows"] = sorted({*map(int, row.get("source_rows") or []), *repeated})
            merged.append(row)
        return merged

    def _profiles(
        self,
        materials: list[dict[str, Any]],
        profile_specs: Mapping[tuple[str, str], Mapping[str, Any]],
        existing_profiles: Iterable[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        profiles = [deepcopy(dict(row)) for row in existing_profiles if not str(row.get("profile_id") or "").startswith(_PROFILE_PREFIX)]
        existing_by_key = {(_normalized(row.get("standard_type")), str(row.get("gpc_brick_code") or "")): row for row in profiles}
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for material in materials:
            groups[(_normalized(material["standard_type"]), material["gpc_brick_code"])].append(material)
        for normalized_key, group in groups.items():
            existing = existing_by_key.get(normalized_key)
            if existing:
                for material in group:
                    material["procurement_profile_id"] = existing["profile_id"]
                continue
            type_key = (group[0]["standard_type"], group[0]["gpc_brick_code"])
            spec = dict(profile_specs.get(type_key) or {})
            template_id = str(spec.get("main_template_id") or "general_finished_good")
            template = self.template_registry.main_templates.get(template_id)
            if template is None:
                raise ValueError(f"发布类型引用未知主模板：{type_key[0]} -> {template_id}")
            attribute_keys = list(dict.fromkeys(
                key for material in group for key in dict(material.get("procurement_attributes") or {})
            ))
            price_keys = list(dict.fromkeys(
                key for material in group for key in dict(material.get("price_drivers") or {})
            ))
            for material in group:
                missing = [key for key in attribute_keys if key not in material["procurement_attributes"]]
                if missing:
                    raise ValueError(f"同一标准类型属性结构不一致：{type_key[0]} -> {missing[0]}")
            if template.record_policy == "project_configuration_first":
                identity_fields: list[str] = []
                transaction_fields = [f"procurement_attributes.{key}" for key in attribute_keys]
            else:
                identity_fields = [f"procurement_attributes.{key}" for key in attribute_keys]
                transaction_fields = []
            profile_id = _profile_id(*type_key)
            profile = {
                "profile_id": profile_id,
                "standard_type": type_key[0],
                "gpc_brick_code": type_key[1],
                "main_template_id": template_id,
                "constraint_ids": list(spec.get("constraint_ids") or []),
                "sku_identity_fields": identity_fields,
                "transaction_fields": transaction_fields,
                "offer_fields": [f"price_drivers.{key}" for key in price_keys],
                "status": "confirmed",
                "source_material_ids": [material["material_id"] for material in group],
            }
            profiles.append(profile)
            for material in group:
                material["procurement_profile_id"] = profile_id
        return profiles

    def publish(self, job_id: str, *, curation_path: Path | None = None) -> dict[str, Any]:
        job_dir = self._job_dir(job_id)
        release_path = job_dir / "boundary-review-release.json"
        if not release_path.is_file():
            raise ValueError("34 个边界项尚未冻结，不能发布到 GPC 工作台")
        release = json.loads(release_path.read_text(encoding="utf-8"))
        source = dict(release.get("source") or {})
        if (
            int(source.get("selected_start_row") or 0) != 2
            or int(source.get("selected_end_row") or 0) != 101
            or release.get("next_rows_processed") is not False
            or release.get("writes_erpnext") is not False
        ):
            raise ValueError("发布范围必须严格绑定首批 100 条业务记录且不得包含 ERPNext 写入")
        decisions = _load_jsonl(job_dir / "decisions.jsonl")
        source_rows = _load_jsonl(job_dir / "source-rows.jsonl")
        source_index = {int(row["source_row"]): row for row in source_rows}
        curations = self._curations(curation_path)
        direct, direct_specs, held_direct = self._direct_materials(job_id, decisions, source_index, curations)
        reviewed, reviewed_specs = self._reviewed_materials(job_id, release, curations)
        new_materials = self._merge_duplicate_materials([*direct, *reviewed])
        existing_materials = self._merge_existing_source_rows([
            row for row in _load_jsonl(self.placements_path)
            if str(row.get("publication_job_id") or "") != job_id
        ], decisions)
        existing_profiles = _load_jsonl(self.profiles_path)
        profile_specs = {**direct_specs, **reviewed_specs}
        new_profiles = self._profiles(new_materials, profile_specs, existing_profiles)
        all_materials = [*existing_materials, *new_materials]

        # A bare source row number is not a provenance key: historical and
        # current source files can both contain row 47.  Attach the full
        # dataset/document/sheet/row identity (and a stable row fingerprint)
        # to newly published actual-purchase placements.  Historical rows are
        # intentionally left without this identity and therefore cannot absorb
        # frequency aliases during a later read.
        for material in all_materials:
            if str(material.get("publication_job_id") or "") != job_id:
                continue
            records = [
                make_source_record(
                    int(source_row),
                    row=source_index.get(int(source_row)),
                    dataset=DEFAULT_SOURCE_DATASET,
                    document=DEFAULT_SOURCE_DOCUMENT,
                    sheet=DEFAULT_SOURCE_SHEET,
                )
                for source_row in material.get("source_rows") or []
                if int(source_row) in source_index
            ]
            if not records:
                continue
            material["source_dataset"] = DEFAULT_SOURCE_DATASET
            material["source_document"] = DEFAULT_SOURCE_DOCUMENT
            material["source_sheet"] = DEFAULT_SOURCE_SHEET
            material["source_records"] = records

        self.placements_path.parent.mkdir(parents=True, exist_ok=True)
        temp_placements = self.placements_path.with_suffix(".publish.tmp.jsonl")
        temp_profiles = self.profiles_path.with_suffix(".publish.tmp.jsonl")
        _write_jsonl(temp_profiles, new_profiles)
        _write_jsonl(temp_placements, all_materials)
        # Full readback validation: GPC codes, completeness gate, type profiles,
        # sparse identity fingerprints and ancestor counts must all load.
        pending_materials = _load_jsonl(temp_placements)
        pending_profiles = _load_jsonl(temp_profiles)
        if self.database is not None and self.database.is_ready("gpc"):
            index = self.database.load_gpc_index(
                material_placements=pending_materials,
                procurement_type_profiles=pending_profiles,
            )
        else:
            index = GpcReferenceIndex.from_runtime(
                self.gpc_runtime_root,
                self.gpc_version,
                material_placements_path=temp_placements,
                procurement_template_catalog_path=ROOT / "data" / "material_master" / "procurement_template_catalog_v0_1.json",
                procurement_type_profiles_path=temp_profiles,
                internal_extensions_path=DEFAULT_INTERNAL_EXTENSIONS_PATH,
            )
        summary = index.summary()
        expected_count = len(all_materials)
        if int(summary.get("actual_material_count") or 0) != expected_count:
            raise ValueError("GPC 工作台回读物料数量与发布候选不一致")

        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_root = self.placements_path.parent / "publication-backups" / f"{job_id}-{stamp}"
        backup_root.mkdir(parents=True, exist_ok=True)
        if self.placements_path.is_file():
            (backup_root / self.placements_path.name).write_bytes(self.placements_path.read_bytes())
        if self.profiles_path.is_file():
            (backup_root / self.profiles_path.name).write_bytes(self.profiles_path.read_bytes())
        temp_profiles.replace(self.profiles_path)
        temp_placements.replace(self.placements_path)
        database_revision = None
        if self.database is not None and self.database.is_ready("gpc"):
            database_revision = self.database.replace_material_publication(
                pending_materials,
                pending_profiles,
            )
            database_summary = self.database.load_gpc_index().summary()
            if int(database_summary.get("actual_material_count") or 0) != expected_count:
                raise ValueError("目录数据库回读物料数量与发布候选不一致")

        manifest = {
            "schema_version": 1,
            "publication_type": "internal_gpc_workbench_materials",
            "job_id": job_id,
            "published_at": _now(),
            "source": source,
            "boundary_review_release_sha256": release.get("release_sha256"),
            "publication_curation_path": str(Path(curation_path).resolve()) if curation_path else "",
            "publication_curation_sha256": _hash_file(Path(curation_path)) if curation_path else "",
            "post_freeze_correction_count": sum(
                str(row.get("cluster_id") or "") in {str(review.get("cluster_id") or "") for review in release.get("reviews") or []}
                for row in curations.values()
            ),
            "existing_material_count": len(existing_materials),
            "new_material_count": len(new_materials),
            "total_material_count": expected_count,
            "new_type_profile_count": sum(str(row.get("profile_id") or "").startswith(_PROFILE_PREFIX) for row in new_profiles),
            "held_direct_count": len(held_direct),
            "held_direct": held_direct,
            "next_rows_processed": False,
            "writes_erpnext": False,
            "placements_sha256": _hash_file(self.placements_path),
            "profiles_sha256": _hash_file(self.profiles_path),
            "catalog_database": database_revision,
            "backup_path": str(backup_root),
            "workbench_readback": {
                "actual_material_count": summary.get("actual_material_count"),
                "materialized_counts": summary.get("materialized_counts"),
            },
        }
        manifest["manifest_sha256"] = _stable_hash(manifest)
        manifest_dir = self.placements_path.parent / "publications"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / f"{job_id}.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return manifest
