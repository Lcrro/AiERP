from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


STATUS_READY = "ready"
STATUS_NEEDS_CLARIFICATION = "needs_clarification"
STATUS_NEEDS_CONFIRMATION = "needs_confirmation"


@dataclass(frozen=True)
class ItemIntent:
    raw_text: str = ""
    raw_name: str = ""
    item_name: str = ""
    item_group_key: str | None = None
    item_group_hint: str = ""
    stock_uom: str | None = None
    specs: dict[str, Any] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ItemIntent":
        return cls(
            raw_text=str(payload.get("raw_text") or ""),
            raw_name=str(payload.get("raw_name") or ""),
            item_name=str(payload.get("item_name") or payload.get("raw_name") or ""),
            item_group_key=payload.get("item_group_key"),
            item_group_hint=str(payload.get("item_group_hint") or ""),
            stock_uom=payload.get("stock_uom"),
            specs=payload.get("specs") or {},
            aliases=list(payload.get("aliases") or []),
        )


class MaterialRules:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.groups: dict[str, dict[str, Any]] = payload.get("groups") or {}
        self.custom_fields: dict[str, dict[str, Any]] = payload.get("custom_fields") or {}
        self._validate()

    @classmethod
    def load(cls, path: str | Path | None = None) -> "MaterialRules":
        rule_path = Path(path) if path else default_rules_path()
        with rule_path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle) or {}
        return cls(payload)

    def _validate(self) -> None:
        required = {
            "label",
            "erpnext_item_group",
            "code_prefix",
            "default_uom",
            "defaults",
            "required_specs",
            "aliases",
            "batch_policy",
            "serial_policy",
        }
        if not self.groups:
            raise ValueError("item master rules must define groups")
        for key, group in self.groups.items():
            missing = sorted(required - set(group))
            if missing:
                raise ValueError(f"group {key} is missing rule fields: {', '.join(missing)}")

    def match_group(self, intent: ItemIntent) -> tuple[str | None, list[str]]:
        if intent.item_group_key:
            return (intent.item_group_key, []) if intent.item_group_key in self.groups else (None, [])

        haystack = " ".join(
            [
                intent.raw_text,
                intent.raw_name,
                intent.item_name,
                intent.item_group_hint,
                " ".join(str(value) for value in intent.specs.values()),
            ]
        ).lower()
        matches: list[tuple[str, int]] = []
        for key, group in self.groups.items():
            score = 0
            if group.get("label") and str(group["label"]).lower() in haystack:
                score += 8
            if group.get("erpnext_item_group") and str(group["erpnext_item_group"]).lower() in haystack:
                score += 4
            for alias in group.get("aliases") or []:
                if str(alias).lower() in haystack:
                    score += 10
            if key.replace("_", " ") in haystack:
                score += 5
            if score:
                matches.append((key, score))

        matches.sort(key=lambda row: row[1], reverse=True)
        if not matches:
            return None, []
        top_score = matches[0][1]
        top = [key for key, score in matches if score == top_score]
        return (top[0], top)

    def prepare(self, intent: ItemIntent, *, item_code: str | None = None) -> dict[str, Any]:
        matched_group, candidates = self.match_group(intent)
        if not matched_group:
            return {
                "status": STATUS_NEEDS_CONFIRMATION,
                "matched_group": None,
                "candidate_groups": [],
                "questions": ["请确认物料属于哪个物料组。"],
            }
        if len(candidates) > 1:
            return {
                "status": STATUS_NEEDS_CONFIRMATION,
                "matched_group": matched_group,
                "candidate_groups": candidates,
                "questions": ["这个叫法可能对应多个物料组，请先确认物料分类。"],
            }

        group = self.groups[matched_group]
        specs = normalize_specs(intent.specs)
        missing_specs = [spec for spec in group["required_specs"] if not specs.get(spec)]
        if missing_specs:
            return {
                "status": STATUS_NEEDS_CLARIFICATION,
                "matched_group": matched_group,
                "missing_specs": missing_specs,
                "questions": [question_for_spec(intent.item_name or intent.raw_name, spec) for spec in missing_specs],
            }

        doc = build_item_doc(intent, matched_group, group, specs, item_code=item_code)
        return {
            "status": STATUS_READY,
            "matched_group": matched_group,
            "missing_specs": [],
            "questions": [],
            "item_code": doc.get("item_code"),
            "item_doc": doc,
        }


def default_rules_path() -> Path:
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "config" / "item_master_rules.yaml"
        if candidate.exists():
            return candidate
    return Path.cwd() / "config" / "item_master_rules.yaml"


def prepare_item_from_intent(
    intent: ItemIntent | dict[str, Any],
    *,
    rules: MaterialRules | None = None,
    item_code: str | None = None,
) -> dict[str, Any]:
    rule_set = rules or MaterialRules.load()
    item_intent = ItemIntent.from_dict(intent) if isinstance(intent, dict) else intent
    return rule_set.prepare(item_intent, item_code=item_code)


def normalize_specs(specs: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in specs.items() if value not in (None, "")}


def build_item_doc(
    intent: ItemIntent,
    group_key: str,
    group: dict[str, Any],
    specs: dict[str, Any],
    *,
    item_code: str | None,
) -> dict[str, Any]:
    item_name = intent.item_name or intent.raw_name
    specification = specs.get("specification") or compose_specification(specs)
    aliases = sorted(set([*intent.aliases, intent.raw_name] + list(group.get("aliases") or [])))
    doc: dict[str, Any] = {
        "doctype": "Item",
        "item_code": item_code,
        "item_name": item_name,
        "item_group": group["erpnext_item_group"],
        "stock_uom": intent.stock_uom or group["default_uom"],
        "description": f"{item_name} {specification}".strip(),
        "specification": specification,
        "raw_name": intent.raw_name,
        "alias_names": ", ".join(alias for alias in aliases if alias),
    }
    doc.update(group.get("defaults") or {})
    for field in ["material", "drawing_no", "standard", "brand", "model", "package_spec"]:
        if specs.get(field):
            doc[field] = specs[field]
    return {key: value for key, value in doc.items() if value not in (None, "")}


def compose_specification(specs: dict[str, Any]) -> str:
    ordered = [
        "material",
        "grade",
        "model",
        "brand",
        "thickness",
        "width",
        "size",
        "form",
        "color",
        "standard",
        "package_spec",
    ]
    values = [str(specs[key]) for key in ordered if specs.get(key)]
    remaining = [str(value) for key, value in specs.items() if key not in ordered and value]
    return " ".join([*values, *remaining])


def question_for_spec(item_name: str, spec: str) -> str:
    labels = {
        "material": "材质",
        "thickness": "厚度",
        "width": "宽度",
        "form": "形态",
        "standard": "执行标准",
        "grade": "牌号/等级",
        "color": "颜色",
        "melt_index": "熔指",
        "package_spec": "包装规格",
        "model": "型号",
        "brand": "品牌",
        "package": "封装",
        "key_parameter": "关键参数",
        "size": "尺寸",
        "specification": "规格型号",
        "equipment": "适用设备",
        "version": "版本",
        "process_stage": "工序阶段",
        "service_scope": "服务范围",
        "billing_unit": "计价单位",
    }
    target = f"{item_name}的" if item_name else ""
    return f"请补充{target}{labels.get(spec, spec)}。"
