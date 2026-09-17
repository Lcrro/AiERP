"""Extract source-backed SKU attribute candidates from tariff review rows."""

from __future__ import annotations

from collections import Counter
import csv
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping


ATTRIBUTE_REVIEW_VERSION = "tariff-attribute-review-v0.1"
ATTRIBUTE_DECISION_VERSION = "tariff-attribute-decision-v0.1"
ATTRIBUTE_FROZEN_RELEASE_VERSION = "tariff-attribute-release-v0.1"
ATTRIBUTE_DECISION_COLUMNS = (
    "code",
    "attribute_decision",
    "reviewer",
    "override_attributes",
    "comment",
    "source_name",
    "parent_name",
    "attribute_status",
    "attributes",
)


@dataclass(frozen=True)
class TariffAttributeRow:
    code: str
    source_name: str
    parent_name: str
    suggested_top_group: str
    suggested_material_family: str
    review_status: str
    attributes: dict[str, dict[str, str]]
    attribute_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "source_name": self.source_name,
            "parent_name": self.parent_name,
            "suggested_top_group": self.suggested_top_group,
            "suggested_material_family": self.suggested_material_family,
            "review_status": self.review_status,
            "attributes": self.attributes,
            "attribute_status": self.attribute_status,
        }


def _add_attribute(target: dict[str, dict[str, str]], key: str, value: str, evidence: str, confidence: str = "0.85") -> None:
    if value and key not in target:
        target[key] = {"value": value, "evidence": evidence, "confidence": confidence}


def extract_tariff_attributes(row: Mapping[str, Any]) -> TariffAttributeRow:
    code = str(row.get("code", ""))
    source_name = str(row.get("source_name", ""))
    parent_name = str(row.get("parent_name", ""))
    text = f"{source_name} {parent_name}"
    attributes: dict[str, dict[str, str]] = {}

    strength = re.search(r"抗拉强度\s*在\s*(\d+)\s*兆帕及以上", source_name)
    if strength:
        _add_attribute(attributes, "tensile_strength", f">={strength.group(1)} MPa", strength.group(0), "0.98")

    head_types = (("方头", "方头"), ("钩头", "钩头"), ("环头", "环头"), ("六角", "六角"), ("内六角", "内六角"), ("平头", "平头"))
    for token, value in head_types:
        if token in source_name:
            _add_attribute(attributes, "head_type", value, token, "0.90")
            break

    thread_types = (("木螺钉", "木螺钉"), ("自攻螺钉", "自攻螺钉"), ("无螺纹制品", "无螺纹"), ("螺纹制品", "螺纹"))
    for token, value in thread_types:
        if token in source_name:
            _add_attribute(attributes, "thread_form", value, token, "0.92")
            break

    kind_text = re.sub(r"不论是否带有.*", "", source_name)
    kind_hits = [(token, value) for token, value in (("螺钉", "螺钉"), ("螺栓", "螺栓"), ("螺母", "螺母"), ("垫圈", "垫圈"), ("铆钉", "铆钉"), ("销", "销")) if token in kind_text]
    if "钉" in kind_text and "螺钉" not in kind_text and "铆钉" not in kind_text:
        kind_hits.append(("钉", "钉类"))
    kind_values = list(dict.fromkeys(value for _token, value in kind_hits))
    if len(kind_values) == 1:
        _add_attribute(attributes, "fastener_kind", kind_values[0], kind_hits[0][0], "0.90")
    elif len(kind_values) > 1:
        attributes["fastener_kind"] = {"value": " | ".join(kind_values), "evidence": "、".join(token for token, _value in kind_hits), "confidence": "0.40"}

    if "钢铁制" in text:
        _add_attribute(attributes, "material", "钢铁制（来源父级证据）", "钢铁制", "0.78")
    elif "铜制" in text:
        _add_attribute(attributes, "material", "铜制或钢铁制带铜头（来源父级证据）", "铜制", "0.62")

    attribute_status = "candidate" if attributes else "unmapped"
    if any(item["confidence"] in {"0.40", "0.62", "0.78"} for item in attributes.values()):
        attribute_status = "review_required"
    return TariffAttributeRow(
        code=code,
        source_name=source_name,
        parent_name=parent_name,
        suggested_top_group=str(row.get("suggested_top_group", "")),
        suggested_material_family=str(row.get("suggested_material_family", "")),
        review_status=str(row.get("review_status", "")),
        attributes=attributes,
        attribute_status=attribute_status,
    )


def build_attribute_review(input_path: Path, output_dir: Path) -> dict[str, Any]:
    with Path(input_path).open("r", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle, delimiter="\t"))
    rows = [extract_tariff_attributes(row) for row in source_rows]
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "tariff_attribute_candidates.tsv"
    columns = ["code", "source_name", "parent_name", "suggested_top_group", "suggested_material_family", "review_status", "attributes", "attribute_status"]
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        for row in rows:
            data = row.as_dict()
            data["attributes"] = json.dumps(data["attributes"], ensure_ascii=False, sort_keys=True)
            writer.writerow(data)
    summary = {
        "release": ATTRIBUTE_REVIEW_VERSION,
        "input_path": str(input_path),
        "row_count": len(rows),
        "attribute_status_counts": dict(Counter(row.attribute_status for row in rows)),
        "attribute_key_counts": dict(Counter(key for row in rows for key in row.attributes)),
        "erpnext_written": False,
        "review_required": True,
    }
    (output_dir / "tariff_attribute_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_attribute_candidates(path: Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _parse_attribute_json(value: str, *, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} 不是合法 JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"{label} 必须是 JSON 对象")
    return parsed


def _normalize_override_attributes(value: str) -> dict[str, dict[str, str]]:
    if not str(value or "").strip():
        return {}
    parsed = _parse_attribute_json(value, label="override_attributes")
    normalized: dict[str, dict[str, str]] = {}
    for key, raw in parsed.items():
        name = str(key).strip()
        if not name:
            raise ValueError("override_attributes 包含空属性名")
        if isinstance(raw, Mapping):
            if not str(raw.get("value") or "").strip():
                raise ValueError(f"属性 {name} 缺少 value")
            item = {str(field): str(item_value) for field, item_value in raw.items()}
            item["evidence"] = "manual_review"
            item["confidence"] = "1.00"
        elif isinstance(raw, (str, int, float, bool)):
            item = {"value": str(raw), "evidence": "manual_review", "confidence": "1.00"}
        else:
            raise ValueError(f"属性 {name} 的值必须是标量或对象")
        normalized[name] = item
    return normalized


def build_attribute_decision_template(candidate_path: Path, output_path: Path) -> dict[str, Any]:
    """Write a blank, hash-bound attribute decision sheet."""

    candidates = _load_attribute_candidates(candidate_path)
    codes = [str(row.get("code") or "").strip() for row in candidates]
    if not all(codes) or len(set(codes)) != len(codes):
        raise ValueError("属性候选包包含空税号或重复税号")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ATTRIBUTE_DECISION_COLUMNS, delimiter="\t")
        writer.writeheader()
        for row in candidates:
            writer.writerow({
                "code": row.get("code", ""),
                "attribute_decision": "",
                "reviewer": "",
                "override_attributes": "",
                "comment": "",
                "source_name": row.get("source_name", ""),
                "parent_name": row.get("parent_name", ""),
                "attribute_status": row.get("attribute_status", ""),
                "attributes": row.get("attributes", "{}"),
            })
    metadata = {
        "decision_version": ATTRIBUTE_DECISION_VERSION,
        "candidate_path": str(Path(candidate_path)),
        "candidate_sha256": _sha256_file(candidate_path),
        "row_count": len(candidates),
        "decision_required": True,
        "erpnext_written": False,
    }
    output_path.with_suffix(output_path.suffix + ".meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metadata


def freeze_attribute_review_package(candidate_path: Path, decision_path: Path, output_dir: Path) -> dict[str, Any]:
    """Validate explicit attribute decisions and emit a review-only release."""

    candidates = _load_attribute_candidates(candidate_path)
    candidate_by_code = {str(row.get("code") or "").strip(): row for row in candidates}
    if not all(candidate_by_code) or len(candidate_by_code) != len(candidates):
        raise ValueError("属性候选包包含空税号或重复税号")
    metadata_path = Path(decision_path).with_suffix(Path(decision_path).suffix + ".meta.json")
    if not metadata_path.exists():
        raise ValueError("属性决策缺少哈希绑定 .meta.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    candidate_hash = _sha256_file(candidate_path)
    if metadata.get("candidate_sha256") != candidate_hash:
        raise ValueError("属性决策模板绑定的候选包哈希已过期，请重新生成模板")
    with Path(decision_path).open("r", encoding="utf-8-sig", newline="") as handle:
        decisions = list(csv.DictReader(handle, delimiter="\t"))
    decision_by_code: dict[str, dict[str, str]] = {}
    for row in decisions:
        code = str(row.get("code") or "").strip()
        if not code or code in decision_by_code:
            raise ValueError("属性决策表包含空税号或重复税号")
        if code not in candidate_by_code:
            raise ValueError(f"属性决策表包含候选包之外的税号：{code}")
        action = str(row.get("attribute_decision") or "").strip().lower()
        if action not in {"approve", "reject", "revise"}:
            raise ValueError(f"税号 {code} 的 attribute_decision 必须是 approve/reject/revise")
        decision_by_code[code] = row

    release_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    for code, decision in decision_by_code.items():
        source = candidate_by_code[code]
        action = str(decision.get("attribute_decision") or "").strip().lower()
        reviewer = str(decision.get("reviewer") or "").strip()
        comment = str(decision.get("comment") or "").strip()
        if not reviewer:
            raise ValueError(f"税号 {code} 的属性决定必须填写 reviewer")
        source_attributes = _parse_attribute_json(source.get("attributes", "{}"), label=f"税号 {code} 的 source attributes")
        override = _normalize_override_attributes(decision.get("override_attributes", ""))
        if action == "reject" and not comment:
            raise ValueError(f"税号 {code} 的 reject 必须填写 comment")
        if action == "revise" and (not comment or not override):
            raise ValueError(f"税号 {code} 的 revise 必须填写 comment 和合法 override_attributes")
        effective = override or source_attributes
        if action == "approve" and not effective:
            raise ValueError(f"税号 {code} 的 approve 没有可确认属性")
        if action == "approve":
            release_rows.append({
                "code": code,
                "source_name": source.get("source_name", ""),
                "parent_name": source.get("parent_name", ""),
                "attribute_decision": action,
                "reviewer": reviewer,
                "comment": comment,
                "source_attribute_status": source.get("attribute_status", ""),
                "source_attributes": json.dumps(source_attributes, ensure_ascii=False, sort_keys=True),
                "effective_attributes": json.dumps(effective, ensure_ascii=False, sort_keys=True),
            })
        audit_rows.append({"code": code, "attribute_decision": action, "reviewer": reviewer, "issue": "", "comment": comment})

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    release_path = output_dir / "tariff_attribute_release.tsv"
    release_columns = list(release_rows[0]) if release_rows else [
        "code", "source_name", "parent_name", "attribute_decision", "reviewer", "comment",
        "source_attribute_status", "source_attributes", "effective_attributes",
    ]
    with release_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=release_columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(release_rows)
    audit_path = output_dir / "tariff_attribute_decision_audit.tsv"
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["code", "attribute_decision", "reviewer", "issue", "comment"], delimiter="\t")
        writer.writeheader()
        writer.writerows(audit_rows)
    summary = {
        "release": ATTRIBUTE_FROZEN_RELEASE_VERSION,
        "status": "review_only_frozen",
        "candidate_sha256": candidate_hash,
        "decision_sha256": _sha256_file(decision_path),
        "release_sha256": _sha256_file(release_path),
        "candidate_row_count": len(candidates),
        "decision_row_count": len(decisions),
        "release_row_count": len(release_rows),
        "decision_counts": dict(Counter(row["attribute_decision"] for row in audit_rows)),
        "erpnext_written": False,
        "review_required": True,
    }
    (output_dir / "tariff_attribute_release_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def compile_standard_type_sku_candidates(
    family_release_path: Path, attribute_release_path: Path, output_dir: Path
) -> dict[str, Any]:
    """Join two review-only releases into standard type/SKU candidates."""

    with Path(family_release_path).open("r", encoding="utf-8-sig", newline="") as handle:
        family_rows = list(csv.DictReader(handle, delimiter="\t"))
    with Path(attribute_release_path).open("r", encoding="utf-8-sig", newline="") as handle:
        attribute_rows = list(csv.DictReader(handle, delimiter="\t"))
    family_by_code = {str(row.get("code") or "").strip(): row for row in family_rows}
    attr_by_code = {str(row.get("code") or "").strip(): row for row in attribute_rows}
    if len(family_by_code) != len(family_rows) or len(attr_by_code) != len(attribute_rows):
        raise ValueError("物料族或属性冻结包包含重复/空税号")
    candidates: list[dict[str, str]] = []
    audit: list[dict[str, str]] = []
    for code, family in family_by_code.items():
        attribute = attr_by_code.get(code)
        if attribute is None:
            audit.append({"code": code, "status": "missing_attributes", "detail": "缺少已批准属性"})
            continue
        effective = _parse_attribute_json(attribute.get("effective_attributes", "{}"), label=f"税号 {code} 的 effective_attributes")
        if not effective:
            audit.append({"code": code, "status": "empty_attributes", "detail": "已批准属性为空"})
            continue
        candidates.append({
            "code": code,
            "proposed_standard_name": family.get("tariff_name", ""),
            "top_group": family.get("top_group", ""),
            "material_family": family.get("material_family", ""),
            "sku_attributes": json.dumps(effective, ensure_ascii=False, sort_keys=True),
            "candidate_status": "ready_for_manual_confirmation",
            "source_family_release": str(Path(family_release_path)),
            "source_attribute_release": str(Path(attribute_release_path)),
        })
        audit.append({"code": code, "status": "ready_for_manual_confirmation", "detail": "物料族与属性均已明确决定"})
    for code in sorted(set(attr_by_code) - set(family_by_code)):
        audit.append({"code": code, "status": "missing_family", "detail": "缺少已批准物料族"})
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = output_dir / "standard_type_sku_candidates.tsv"
    candidate_columns = list(candidates[0]) if candidates else [
        "code", "proposed_standard_name", "top_group", "material_family", "sku_attributes",
        "candidate_status", "source_family_release", "source_attribute_release",
    ]
    with candidate_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate_columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(candidates)
    audit_path = output_dir / "standard_type_sku_candidate_audit.tsv"
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["code", "status", "detail"], delimiter="\t")
        writer.writeheader()
        writer.writerows(audit)
    summary = {
        "release": "standard-type-sku-candidate-v0.1",
        "status": "review_only_candidate",
        "family_release_path": str(Path(family_release_path)),
        "attribute_release_path": str(Path(attribute_release_path)),
        "candidate_row_count": len(candidates),
        "audit_status_counts": dict(Counter(row["status"] for row in audit)),
        "erpnext_written": False,
        "explicit_confirmation_required": True,
    }
    (output_dir / "standard_type_sku_candidate_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
