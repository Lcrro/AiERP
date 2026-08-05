from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .release_resolver import DEFAULT_RELEASE_CATALOG_PATH, ReleaseMaterialResolver, normalize_spec_text, normalize_text


DEFAULT_GOVERNANCE_DIR = (
    Path(__file__).resolve().parents[3] / "data" / "material_master" / "governance_v0_5"
)

_ATTRIBUTE_DESCRIPTIONS = {
    "material": "构成材质，例如碳钢、不锈钢、PPR、橡胶或硬质合金。",
    "length": "成品总长或有效长度，使用明确数值和单位。",
    "size": "决定采购选择的标准尺寸或规格。",
    "brand": "员工明确指定或来源资料已记录的品牌；未指定时不要猜测。",
    "feature": "会影响采购选择或互换性的结构、性能或工艺特征。",
    "capacity": "额定或实际容量，使用明确数值和单位。",
    "model": "制造商或行业使用的完整型号。",
    "specification": "决定采购选择的完整标准规格。",
    "nominal_size": "标准公称尺寸，例如 DN50。",
    "surface_treatment": "表面处理方式，例如镀锌、发黑或喷塑。",
    "spec": "决定采购选择的完整标准规格。",
    "color": "成品颜色；仅在影响识别、用途或采购选择时参与 SKU。",
    "dimensions": "长、宽、高、厚等完整外形尺寸。",
    "connection_type": "连接方式，例如法兰、螺纹、焊接、热熔或胶接。",
    "width": "成品宽度，使用明确数值和单位。",
    "thickness": "成品厚度或壁厚，使用明确数值和单位。",
    "voltage": "额定或工作电压。",
    "diameter": "成品、接口或加工直径，使用明确数值和单位。",
    "interface": "决定设备或部件兼容性的接口或柄型。",
    "structure": "决定产品类型或互换性的结构形式。",
    "strength_grade": "材料或紧固件的强度等级，例如 8.8、10.9 或 12.9。",
    "type": "稳定的产品类型或结构类型，不使用临时描述。",
    "power": "额定功率，使用明确数值和单位。",
    "rated_current_a": "额定电流，单位 A。",
    "rated_load": "设备或部件允许的额定载荷。",
    "rated_voltage_v": "额定电压，单位 V。",
    "thread_spec": "完整螺纹规格，包括直径、螺距或标准制式。",
    "pressure": "额定压力或压力等级。",
    "material_type": "材料类别或牌号，不使用模糊外观描述。",
    "nominal_diameter": "公称直径，例如 DN50。",
}


class MaterialClassificationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type_id: str
    top_group: str
    material_family: str
    standard_name: str
    definition: str
    includes: str = ""
    excludes: str = ""
    score: int = 0
    confidence: Literal["high", "medium", "low"] = "low"
    match_reasons: list[str] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)


class MaterialClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "existing_sku",
        "needs_choice",
        "needs_input",
        "new_sku",
        "new_type_review",
    ]
    raw_text: str
    normalized_attributes: dict[str, str] = Field(default_factory=dict)
    selected_type: MaterialClassificationCandidate | None = None
    type_candidates: list[MaterialClassificationCandidate] = Field(default_factory=list)
    sku_candidates: list[dict[str, Any]] = Field(default_factory=list)
    existing_sku: dict[str, Any] | None = None
    missing_attributes: list[dict[str, str]] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
    reason: str
    ready_to_create: bool = False


@dataclass(frozen=True)
class _TypeRow:
    type_id: str
    top_group: str
    material_family: str
    standard_name: str
    definition: str
    includes: str
    excludes: str
    aliases: tuple[str, ...]
    attributes: tuple[dict[str, Any], ...]


class MaterialTypeClassifier:
    """Classify new material facts against the frozen v0.5 type dictionary.

    The language model may extract facts, but this class owns dictionary
    boundaries, required attributes, existing-SKU checks, and final status.
    It never writes the release catalog or ERPNext.
    """

    def __init__(
        self,
        governance_dir: str | Path = DEFAULT_GOVERNANCE_DIR,
        release_catalog_path: str | Path = DEFAULT_RELEASE_CATALOG_PATH,
    ) -> None:
        self.governance_dir = Path(governance_dir)
        self.release_catalog_path = Path(release_catalog_path)
        self.release_resolver = ReleaseMaterialResolver(self.release_catalog_path)
        self.release_rows = {row.get("item_code", ""): row for row in self.release_resolver.rows}
        self.sku_type_ids = {
            row.get("item_code", ""): row.get("type_id", "")
            for row in _read_tsv(self.governance_dir / "sku_type_mapping.tsv")
            if row.get("mapping_status") == "frozen"
        }
        self.types = self._load_types()

    def classify(
        self,
        raw_text: str,
        *,
        attributes: dict[str, Any] | None = None,
        top_group_hint: str = "",
        material_family_hint: str = "",
        limit: int = 5,
    ) -> MaterialClassificationResult:
        raw_text = str(raw_text or "").strip()
        normalized_attributes = _normalize_attributes(attributes or {})
        if not raw_text:
            return MaterialClassificationResult(
                status="needs_input",
                raw_text="",
                normalized_attributes=normalized_attributes,
                questions=["请说明新物料的名称、用途或关键结构。"],
                reason="物料描述为空。",
            )

        ranked = sorted(
            (
                self._score_type(
                    item,
                    raw_text,
                    top_group_hint=top_group_hint,
                    material_family_hint=material_family_hint,
                )
                for item in self.types
            ),
            key=lambda item: (-item.score, item.standard_name),
        )
        candidates = [item for item in ranked if item.score > 0][: max(1, min(limit, 10))]
        if not candidates or candidates[0].score < 80:
            return MaterialClassificationResult(
                status="new_type_review",
                raw_text=raw_text,
                normalized_attributes=normalized_attributes,
                type_candidates=candidates,
                questions=["现有标准名称字典没有可靠匹配，需要由物料管理员确认是否新增标准物料类型。"],
                reason="没有候选达到现有标准类型匹配阈值。",
            )

        top = candidates[0]
        second_score = candidates[1].score if len(candidates) > 1 else 0
        family_is_generic = normalize_text(raw_text) == normalize_text(top.material_family)
        if family_is_generic or top.score - second_score < 25:
            return MaterialClassificationResult(
                status="needs_choice",
                raw_text=raw_text,
                normalized_attributes=normalized_attributes,
                type_candidates=candidates,
                questions=["找到了多个可能的标准物料类型，请选择一个，或补充结构、接口和用途。"],
                reason="物料族描述过宽或最高候选没有明显领先。",
            )

        matching_skus = self._matching_skus(top.type_id, raw_text, normalized_attributes, limit=limit)
        exact_skus = [item for item in matching_skus if item.get("all_supplied_attributes_match")]
        selected_type = top
        missing = _missing_required_attributes(top.attributes, normalized_attributes, raw_text)

        direct = self.release_resolver.resolve(raw_text, specs=normalized_attributes, limit=limit)
        direct_code = str((direct.get("resolved") or {}).get("item_code") or "")
        if direct_code and self.sku_type_ids.get(direct_code) == top.type_id:
            existing = direct["resolved"]
            return MaterialClassificationResult(
                status="existing_sku",
                raw_text=raw_text,
                normalized_attributes=normalized_attributes,
                selected_type=selected_type,
                type_candidates=candidates,
                sku_candidates=matching_skus,
                existing_sku=existing,
                reason="物料类型与现有 SKU 均达到唯一高置信匹配。",
            )
        if len(exact_skus) == 1 and not missing:
            return MaterialClassificationResult(
                status="existing_sku",
                raw_text=raw_text,
                normalized_attributes=normalized_attributes,
                selected_type=selected_type,
                type_candidates=candidates,
                sku_candidates=matching_skus,
                existing_sku=exact_skus[0],
                reason="所有已提供的唯一性属性与一个现有 SKU 一致。",
            )
        if len(exact_skus) > 1:
            return MaterialClassificationResult(
                status="needs_choice",
                raw_text=raw_text,
                normalized_attributes=normalized_attributes,
                selected_type=selected_type,
                type_candidates=candidates,
                sku_candidates=exact_skus,
                questions=["多个现有 SKU 与当前信息一致，请选择一个或继续补充规格。"],
                reason="现有信息不能唯一确定 SKU。",
            )
        if missing:
            labels = [item["display_name"] for item in missing]
            return MaterialClassificationResult(
                status="needs_input",
                raw_text=raw_text,
                normalized_attributes=normalized_attributes,
                selected_type=selected_type,
                type_candidates=candidates,
                sku_candidates=matching_skus,
                missing_attributes=missing,
                questions=[f"已归入“{top.standard_name}”，请补充影响采购选择的必填属性：{'、'.join(labels)}。"],
                reason="标准类型已确定，但创建 SKU 所需的关键属性不完整。",
            )
        return MaterialClassificationResult(
            status="new_sku",
            raw_text=raw_text,
            normalized_attributes=normalized_attributes,
            selected_type=selected_type,
            type_candidates=candidates,
            sku_candidates=matching_skus,
            reason="标准类型已确定，关键属性完整，未发现相同现有 SKU。",
            ready_to_create=True,
        )

    def _load_types(self) -> list[_TypeRow]:
        aliases: dict[str, list[str]] = {}
        for row in _read_tsv(self.governance_dir / "material_type_aliases.tsv"):
            aliases.setdefault(row.get("type_id", ""), []).append(row.get("alias", ""))
        attributes: dict[str, list[dict[str, Any]]] = {}
        for row in _read_tsv(self.governance_dir / "material_attribute_templates.tsv"):
            attribute_key = row.get("attribute_key", "")
            attributes.setdefault(row.get("type_id", ""), []).append(
                {
                    "attribute_key": attribute_key,
                    "display_name": row.get("display_name", ""),
                    "requirement": row.get("requirement", "optional"),
                    "value_type": row.get("value_type", "text"),
                    "unit": row.get("unit", ""),
                    "enum_values": [value for value in row.get("enum_values", "").split("；") if value],
                    "affects_sku_identity": row.get("affects_sku_identity", "").lower() == "true",
                    "description": _ATTRIBUTE_DESCRIPTIONS.get(attribute_key, row.get("description", "")),
                }
            )
        return [
            _TypeRow(
                type_id=row["type_id"],
                top_group=row["top_group"],
                material_family=row["material_family"],
                standard_name=row["standard_name"],
                definition=row.get("definition", ""),
                includes=row.get("includes", ""),
                excludes=row.get("excludes", ""),
                aliases=tuple(value for value in aliases.get(row["type_id"], []) if value),
                attributes=tuple(attributes.get(row["type_id"], [])),
            )
            for row in _read_tsv(self.governance_dir / "material_type_dictionary.tsv")
            if row.get("governance_status") == "frozen"
        ]

    def _score_type(
        self,
        item: _TypeRow,
        raw_text: str,
        *,
        top_group_hint: str,
        material_family_hint: str,
    ) -> MaterialClassificationCandidate:
        query = normalize_text(raw_text)
        standard = normalize_text(item.standard_name)
        reasons: list[str] = []
        score = 0
        if query == standard:
            score += 220
            reasons.append("标准名称精确匹配")
        elif standard and standard in query:
            score += 145
            reasons.append("描述包含完整标准名称")
        aliases = [normalize_text(value) for value in item.aliases if normalize_text(value)]
        if query in aliases:
            score += 205
            reasons.append("标准别名精确匹配")
        else:
            best_alias = max((len(value) for value in aliases if value in query), default=0)
            if best_alias:
                score += (165 if best_alias >= 4 else 115) + min(best_alias, 20)
                reasons.append("描述命中标准别名")
        if top_group_hint and normalize_text(top_group_hint) == normalize_text(item.top_group):
            score += 35
            reasons.append("一级类目提示匹配")
        if material_family_hint and normalize_text(material_family_hint) == normalize_text(item.material_family):
            score += 65
            reasons.append("物料族提示匹配")
        elif normalize_text(item.material_family) in query:
            score += 25
            reasons.append("描述包含物料族")
        evidence_terms = _boundary_terms(item.includes)
        matched_terms = [term for term in evidence_terms if normalize_text(term) in query]
        if matched_terms:
            score += min(36, 12 * len(matched_terms))
            reasons.append("包含范围证据匹配")
        confidence: Literal["high", "medium", "low"] = (
            "high" if score >= 180 else "medium" if score >= 100 else "low"
        )
        return MaterialClassificationCandidate(
            type_id=item.type_id,
            top_group=item.top_group,
            material_family=item.material_family,
            standard_name=item.standard_name,
            definition=item.definition,
            includes=item.includes,
            excludes=item.excludes,
            score=score,
            confidence=confidence,
            match_reasons=reasons,
            attributes=list(item.attributes),
        )

    def _matching_skus(
        self,
        type_id: str,
        raw_text: str,
        attributes: dict[str, str],
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        resolver_result = self.release_resolver.resolve(raw_text, specs=attributes, limit=max(limit * 3, 10))
        output: list[dict[str, Any]] = []
        for candidate in resolver_result.get("candidates") or []:
            code = str(candidate.get("item_code") or "")
            if self.sku_type_ids.get(code) != type_id:
                continue
            row = self.release_rows.get(code, {})
            haystack = normalize_spec_text(
                " ".join([row.get("sku_name", ""), row.get("required_specs", ""), row.get("optional_specs", "")])
            )
            identity_values = [normalize_spec_text(value) for value in attributes.values() if value]
            payload = dict(candidate)
            payload["all_supplied_attributes_match"] = bool(identity_values) and all(
                value in haystack for value in identity_values
            )
            output.append(payload)
            if len(output) >= limit:
                break
        return output


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def _normalize_attributes(attributes: dict[str, Any]) -> dict[str, str]:
    aliases = {
        "overalllength": "length",
        "totallength": "length",
        "总长": "length",
        "长度": "length",
        "直径": "diameter",
        "口径": "diameter",
        "材质": "material",
        "规格口径": "spec",
        "规格": "spec",
        "接口": "interface",
        "柄型": "interface",
        "单位": "uom",
    }
    output: dict[str, str] = {}
    for key, value in attributes.items():
        raw_key = str(key).strip()
        raw_value = str(value or "").strip()
        if not raw_key or not raw_value:
            continue
        normalized_key = normalize_text(raw_key).replace("_", "").replace("-", "")
        canonical_key = aliases.get(normalized_key, raw_key)
        output[canonical_key] = raw_value
    return output


def _missing_required_attributes(
    templates: list[dict[str, Any]],
    attributes: dict[str, str],
    raw_text: str,
) -> list[dict[str, str]]:
    provided_keys = {normalize_text(key) for key in attributes}
    searchable = normalize_spec_text(" ".join([raw_text, *attributes.values()]))
    missing: list[dict[str, str]] = []
    for item in templates:
        if item.get("requirement") != "required":
            continue
        keys = {
            normalize_text(item.get("attribute_key")),
            normalize_text(item.get("display_name")),
        }
        if keys & provided_keys:
            continue
        enum_values = [normalize_spec_text(value) for value in item.get("enum_values") or [] if value]
        if enum_values and any(value in searchable for value in enum_values):
            continue
        missing.append(
            {
                "attribute_key": str(item.get("attribute_key") or ""),
                "display_name": str(item.get("display_name") or item.get("attribute_key") or ""),
                "description": str(item.get("description") or ""),
            }
        )
    return missing


def _boundary_terms(value: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[、，,；;。或及等/]+", value or "")
        if len(normalize_text(part)) >= 2
    ]
