"""Reusable construction-procurement archetypes and sparse-SKU validation.

The catalog intentionally contains a small number of procurement behaviours,
not one hand-written template per material type.  Lightweight type profiles
bind a GPC Brick to one behaviour and describe how that type projects observed
fields into SKU identity, transaction configuration, or supplier-offer data.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, model_validator


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_TEMPLATE_CATALOG_PATH = ROOT / "data" / "material_master" / "procurement_template_catalog_v0_1.json"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcurementMainTemplate(_StrictModel):
    template_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    stock_behavior: Literal[
        "discrete", "linear", "sheet_roll", "bulk", "packaged",
        "equipment", "compatibility", "configuration", "kit", "general",
    ]
    record_policy: Literal["actual_sku_only", "project_configuration_first"]
    naming_pattern: str = Field(min_length=1)
    max_identity_attributes: int = Field(ge=0, le=8)
    identity_principles: list[str] = Field(min_length=1)
    transaction_principles: list[str] = Field(min_length=1)
    examples: list[str] = Field(min_length=1)
    negative_examples: list[str] = Field(min_length=1)


class ProcurementConstraint(_StrictModel):
    constraint_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    required_checks: list[str] = Field(min_length=1)
    force_review: bool = False


class ProcurementTemplateCatalog(_StrictModel):
    schema_version: int = 1
    catalog_version: str = Field(pattern=r"^v\d+\.\d+$")
    sku_generation_policy: Literal["actual_combinations_only"]
    offer_fields: list[str] = Field(min_length=1)
    main_templates: list[ProcurementMainTemplate]
    constraints: list[ProcurementConstraint]

    @model_validator(mode="after")
    def validate_catalog_shape(self) -> "ProcurementTemplateCatalog":
        template_ids = [item.template_id for item in self.main_templates]
        constraint_ids = [item.constraint_id for item in self.constraints]
        if len(self.main_templates) != 10 or len(set(template_ids)) != 10:
            raise ValueError("采购形态目录必须恰好包含 10 份唯一主模板")
        if len(self.constraints) != 5 or len(set(constraint_ids)) != 5:
            raise ValueError("采购形态目录必须恰好包含 5 份唯一叠加约束")
        return self


class ProcurementTypeProfile(_StrictModel):
    profile_id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]+$")
    standard_type: str = Field(min_length=1)
    # The legacy field name is retained for compatibility with existing local
    # publications. Official GPC nodes are eight digits; each Nexterp-added
    # business hierarchy level appends exactly two digits.
    gpc_brick_code: str = Field(pattern=r"^\d{8}(?:\d{2})*$")
    main_template_id: str = Field(min_length=1)
    constraint_ids: list[str] = Field(default_factory=list)
    sku_identity_fields: list[str] = Field(default_factory=list)
    transaction_fields: list[str] = Field(default_factory=list)
    offer_fields: list[str] = Field(default_factory=list)
    status: Literal["golden", "generated", "confirmed"] = "generated"
    source_material_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_role_references(self) -> "ProcurementTypeProfile":
        all_refs = [*self.sku_identity_fields, *self.transaction_fields, *self.offer_fields]
        if len(all_refs) != len(set(all_refs)):
            raise ValueError(f"类型档案属性角色重复：{self.profile_id}")
        for reference in all_refs:
            if not re.fullmatch(r"(?:procurement_attributes|price_drivers)\.[^.]+", reference):
                raise ValueError(f"类型档案属性引用无效：{self.profile_id} -> {reference}")
        return self


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    return re.sub(r"\s+", " ", text)


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class ProcurementTemplateRegistry:
    """Validate type profiles and enrich actual material records deterministically."""

    def __init__(
        self,
        catalog: ProcurementTemplateCatalog,
        profiles: Iterable[Mapping[str, Any]] = (),
    ) -> None:
        self.catalog = catalog
        self.main_templates = {item.template_id: item for item in catalog.main_templates}
        self.constraints = {item.constraint_id: item for item in catalog.constraints}
        self.profiles: dict[str, ProcurementTypeProfile] = {}
        self.profile_by_type_and_brick: dict[tuple[str, str], ProcurementTypeProfile] = {}
        for raw in profiles:
            profile = ProcurementTypeProfile.model_validate(raw)
            if profile.profile_id in self.profiles:
                raise ValueError(f"采购类型档案编号重复：{profile.profile_id}")
            if profile.main_template_id not in self.main_templates:
                raise ValueError(f"采购类型档案引用未知主模板：{profile.profile_id} -> {profile.main_template_id}")
            missing_constraints = [item for item in profile.constraint_ids if item not in self.constraints]
            if missing_constraints:
                raise ValueError(f"采购类型档案引用未知叠加约束：{profile.profile_id} -> {missing_constraints[0]}")
            template = self.main_templates[profile.main_template_id]
            if len(profile.sku_identity_fields) > template.max_identity_attributes:
                raise ValueError(f"采购类型档案SKU身份字段超过主模板上限：{profile.profile_id}")
            if template.record_policy == "actual_sku_only" and not profile.sku_identity_fields:
                raise ValueError(f"按需SKU类型档案必须定义身份字段：{profile.profile_id}")
            key = (_normalized(profile.standard_type), profile.gpc_brick_code)
            if key in self.profile_by_type_and_brick:
                raise ValueError(f"同一标准类型和 Brick 存在重复类型档案：{profile.standard_type}")
            self.profiles[profile.profile_id] = profile
            self.profile_by_type_and_brick[key] = profile

    @classmethod
    def from_files(
        cls,
        catalog_path: Path = DEFAULT_TEMPLATE_CATALOG_PATH,
        profiles_path: Path | None = None,
    ) -> "ProcurementTemplateRegistry":
        catalog = ProcurementTemplateCatalog.model_validate(
            json.loads(Path(catalog_path).read_text(encoding="utf-8"))
        )
        profiles = load_jsonl(profiles_path) if profiles_path and Path(profiles_path).is_file() else []
        return cls(catalog, profiles)

    def profile(self, profile_id: str) -> ProcurementTypeProfile:
        profile = self.profiles.get(str(profile_id or "").strip())
        if profile is None:
            raise ValueError(f"实际物料引用未知采购类型档案：{profile_id}")
        return profile

    @staticmethod
    def _field_map(material: Mapping[str, Any]) -> dict[str, str]:
        output: dict[str, str] = {}
        for group in ("procurement_attributes", "price_drivers"):
            for key, value in dict(material.get(group) or {}).items():
                clean_key = str(key or "").strip()
                clean_value = str(value or "").strip()
                if clean_key and clean_value:
                    output[f"{group}.{clean_key}"] = clean_value
        return output

    def enrich_material(self, material: Mapping[str, Any]) -> dict[str, Any]:
        profile = self.profile(str(material.get("procurement_profile_id") or ""))
        standard_type = str(material.get("standard_type") or "").strip()
        brick_code = str(material.get("gpc_brick_code") or "").strip()
        if _normalized(standard_type) != _normalized(profile.standard_type) or brick_code != profile.gpc_brick_code:
            raise ValueError(
                f"实际物料与采购类型档案不一致：{material.get('material_id')} -> {profile.profile_id}"
            )
        fields = self._field_map(material)
        role_refs = {
            "sku_identity": profile.sku_identity_fields,
            "transaction": profile.transaction_fields,
            "supplier_offer": profile.offer_fields,
        }
        expected = {reference for references in role_refs.values() for reference in references}
        missing = sorted(expected - set(fields))
        uncovered = sorted(set(fields) - expected)
        if missing:
            raise ValueError(f"采购类型档案要求的属性缺失：{material.get('material_id')} -> {missing[0]}")
        if uncovered:
            raise ValueError(f"实际物料存在未分配属性角色的字段：{material.get('material_id')} -> {uncovered[0]}")
        template = self.main_templates[profile.main_template_id]
        role_values = {
            role: {reference: fields[reference] for reference in references}
            for role, references in role_refs.items()
        }
        base_identity = {
            "gpc_brick_code": brick_code,
            "standard_type": _normalized(standard_type),
            "identity": {key: _normalized(value) for key, value in role_values["sku_identity"].items()},
        }
        all_configuration = {
            **base_identity,
            "transaction": {key: _normalized(value) for key, value in role_values["transaction"].items()},
        }
        is_sku_candidate = template.record_policy == "actual_sku_only"
        constraints = [self.constraints[item] for item in profile.constraint_ids]
        output = deepcopy(dict(material))
        output.update({
            "procurement_profile": {
                "profile_id": profile.profile_id,
                "status": profile.status,
                "main_template_id": template.template_id,
                "main_template_name": template.name,
                "constraint_ids": list(profile.constraint_ids),
                "constraint_names": [item.name for item in constraints],
                "force_review": any(item.force_review for item in constraints),
                "record_policy": template.record_policy,
                "record_policy_label": "真实组合按需建SKU" if is_sku_candidate else "项目配置优先，不默认建库存SKU",
                "sku_generation_policy": self.catalog.sku_generation_policy,
            },
            "attribute_roles": role_values,
            "record_kind": "sku_candidate" if is_sku_candidate else "project_configuration",
            "sku_identity_fingerprint": _fingerprint(base_identity) if is_sku_candidate else "",
            "configuration_fingerprint": _fingerprint(all_configuration),
        })
        return output

    def summary(self) -> dict[str, Any]:
        return {
            "catalog_version": self.catalog.catalog_version,
            "main_template_count": len(self.main_templates),
            "constraint_count": len(self.constraints),
            "type_profile_count": len(self.profiles),
            "sku_generation_policy": self.catalog.sku_generation_policy,
        }


__all__ = [
    "DEFAULT_TEMPLATE_CATALOG_PATH",
    "ProcurementConstraint",
    "ProcurementMainTemplate",
    "ProcurementTemplateCatalog",
    "ProcurementTemplateRegistry",
    "ProcurementTypeProfile",
]
