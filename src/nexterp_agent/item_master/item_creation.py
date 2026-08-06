from __future__ import annotations

from collections import Counter
from html import escape
import re
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict

from .coding import generate_next_item_code
from .type_classifier import MaterialClassificationResult, MaterialTypeClassifier


class ItemCreationDraft(BaseModel):
    """Frozen business draft used to create one ERPNext Item."""

    model_config = ConfigDict(extra="forbid")

    type_id: str
    top_group: str
    material_family: str
    standard_name: str
    item_code: str
    sku_name: str
    item_group: str
    stock_uom: str
    required_specs: str
    optional_specs: str = ""
    item_doc: dict[str, Any]


class ItemMasterCreationPlanner:
    """Compile a classified material into an ERPNext Item draft.

    The model may provide raw facts. Classification boundaries, code generation,
    unit selection and the final Item fields remain deterministic here.
    """

    def __init__(self, classifier: MaterialTypeClassifier | None = None) -> None:
        self.classifier = classifier or MaterialTypeClassifier()

    def classify(
        self,
        raw_text: str,
        *,
        attributes: dict[str, Any] | None = None,
        top_group_hint: str = "",
        material_family_hint: str = "",
        limit: int = 5,
    ) -> MaterialClassificationResult:
        return self.classifier.classify(
            raw_text,
            attributes=attributes,
            top_group_hint=top_group_hint,
            material_family_hint=material_family_hint,
            limit=limit,
        )

    def code_prefix(self, classification: MaterialClassificationResult) -> str:
        selected = classification.selected_type
        if selected is None:
            raise ValueError("物料标准类型尚未确定。")
        rows = self.classifier.release_rows_for_type(selected.type_id)
        prefixes = [_item_code_prefix(str(row.get("item_code") or "")) for row in rows]
        prefixes = [value for value in prefixes if value]
        if not prefixes:
            raise ValueError("标准类型没有可复用的企业物料编码前缀。")
        return Counter(prefixes).most_common(1)[0][0]

    def build_draft(
        self,
        classification: MaterialClassificationResult,
        *,
        existing_item_codes: Iterable[str] = (),
    ) -> ItemCreationDraft:
        if classification.status != "new_sku" or not classification.ready_to_create:
            raise ValueError("只有分类结果为 new_sku 且关键属性完整时才能准备建档。")
        selected = classification.selected_type
        if selected is None:
            raise ValueError("物料标准类型尚未确定。")

        rows = self.classifier.release_rows_for_type(selected.type_id)
        prefix = self.code_prefix(classification)
        release_codes = [str(row.get("item_code") or "") for row in rows]
        item_code = generate_next_item_code(prefix, sorted(set([*release_codes, *existing_item_codes])))
        stock_uom = _preferred_value(
            classification.normalized_attributes.get("uom"),
            (str(row.get("stock_uom") or "") for row in rows),
        )
        if not stock_uom:
            raise ValueError("无法从同类标准物料推导计量单位，请明确提供单位。")
        item_group = _preferred_value(
            "",
            (str(row.get("item_group") or "") for row in rows),
        ) or f"{selected.top_group}/{selected.material_family}"

        required_specs, optional_specs, identity_values = _render_specs(
            selected.attributes,
            classification.normalized_attributes,
        )
        sku_name = _sku_name(selected.standard_name, identity_values)
        description = _description(
            sku_name=sku_name,
            type_id=selected.type_id,
            standard_name=selected.standard_name,
            required_specs=required_specs,
            optional_specs=optional_specs,
        )
        item_doc = {
            "item_code": item_code,
            "item_name": sku_name,
            "item_group": item_group,
            "stock_uom": stock_uom,
            "description": description,
            "disabled": 0,
            "is_stock_item": 1,
            "is_purchase_item": 1,
            "is_sales_item": 0,
            "include_item_in_manufacturing": 0,
        }
        return ItemCreationDraft(
            type_id=selected.type_id,
            top_group=selected.top_group,
            material_family=selected.material_family,
            standard_name=selected.standard_name,
            item_code=item_code,
            sku_name=sku_name,
            item_group=item_group,
            stock_uom=stock_uom,
            required_specs=required_specs,
            optional_specs=optional_specs,
            item_doc=item_doc,
        )


def _item_code_prefix(item_code: str) -> str:
    match = re.match(r"^(.+?)-\d{6,}(?:-.+)?$", item_code.strip())
    return match.group(1) if match else ""


def _preferred_value(explicit: str, values: Iterable[str]) -> str:
    if str(explicit or "").strip():
        return str(explicit).strip()
    normalized = [str(value).strip() for value in values if str(value).strip()]
    return Counter(normalized).most_common(1)[0][0] if normalized else ""


def _render_specs(
    templates: list[dict[str, Any]],
    attributes: dict[str, str],
) -> tuple[str, str, list[str]]:
    by_key = {str(item.get("attribute_key") or ""): item for item in templates}
    required: list[str] = []
    optional: list[str] = []
    identity_values: list[str] = []
    consumed: set[str] = {"uom"}
    for item in templates:
        key = str(item.get("attribute_key") or "")
        value = str(attributes.get(key) or "").strip()
        if not key or not value:
            continue
        consumed.add(key)
        label = str(item.get("display_name") or key)
        rendered = f"{label}：{value}"
        target = required if item.get("requirement") == "required" else optional
        target.append(rendered)
        if item.get("affects_sku_identity"):
            identity_values.append(value)
    for key, value in attributes.items():
        if key in consumed or not str(value).strip():
            continue
        label = str(by_key.get(key, {}).get("display_name") or key)
        optional.append(f"{label}：{str(value).strip()}")
    return "；".join(required), "；".join(optional), identity_values


def _sku_name(standard_name: str, identity_values: list[str]) -> str:
    normalized_name = standard_name.lower()
    suffixes: list[str] = []
    for value in identity_values:
        clean = str(value).strip()
        if clean and clean.lower() not in normalized_name and clean not in suffixes:
            suffixes.append(clean)
    return " ".join([standard_name, *suffixes]).strip()[:140]


def _description(
    *,
    sku_name: str,
    type_id: str,
    standard_name: str,
    required_specs: str,
    optional_specs: str,
) -> str:
    fields = [
        ("标准物料名称", standard_name),
        ("必填规格", required_specs),
        ("辅助规格", optional_specs),
        ("标准类型编号", type_id),
    ]
    rows = "".join(
        f"<li><strong>{escape(label)}：</strong>{escape(value)}</li>"
        for label, value in fields
        if value
    )
    return f"<p><strong>{escape(sku_name)}</strong></p><ul>{rows}</ul>"
