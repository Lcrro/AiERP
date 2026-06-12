from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "material_purchase_2024"
DEFAULT_RULES_PATH = REPO_ROOT / "config" / "material_governance_rules.yaml"
DEFAULT_MERGED_CATALOG_PATH = DEFAULT_DATA_DIR / "merged_standard_item_catalog.csv"
DEFAULT_COMPOSITION_ITEMS_PATH = DEFAULT_DATA_DIR / "material_catalog_composition_items.csv"
DEFAULT_RESOLUTION_QUEUE_PATH = DEFAULT_DATA_DIR / "material_conflict_resolution_queue.csv"
DEFAULT_ALIAS_CONTEXT_PATH = DEFAULT_DATA_DIR / "material_alias_context_map.csv"
DEFAULT_GROUP_OVERRIDES_PATH = DEFAULT_DATA_DIR / "material_group_governance_overrides.csv"
DEFAULT_ITEM_OVERRIDES_PATH = DEFAULT_DATA_DIR / "material_item_governance_overrides.csv"
DEFAULT_ALIAS_OVERRIDES_PATH = DEFAULT_DATA_DIR / "material_alias_governance_overrides.csv"
DEFAULT_GOVERNED_CATALOG_PATH = DEFAULT_DATA_DIR / "governed_material_catalog.csv"
DEFAULT_RELEASE_CANDIDATES_PATH = DEFAULT_DATA_DIR / "governed_release_candidates.csv"
DEFAULT_GOVERNANCE_QUEUE_PATH = DEFAULT_DATA_DIR / "material_governance_queue.csv"
DEFAULT_BREAKDOWN_PATH = DEFAULT_DATA_DIR / "material_governance_breakdown.csv"
DEFAULT_SUMMARY_PATH = DEFAULT_DATA_DIR / "material_governance_summary.json"


GOVERNED_FIELDS = [
    "merged_item_code",
    "standard_name",
    "canonical_group_path",
    "specs",
    "unit",
    "source_count",
    "source_candidate_count",
    "alias_names",
    "source_rows",
    "governance_grade",
    "governance_status",
    "issue_type",
    "missing_specs",
    "governance_reason",
    "next_action",
    "matched_rule_key",
    "matched_rule_label",
    "rule_source",
    "override_source",
    "has_blocking_conflict",
    "has_alias_conflict",
    "has_unit_conflict",
    "has_low_precision",
    "needs_human_review",
    "note_has_open_question",
    "related_conflict_types",
    "resolution_issue_types",
    "original_composition_bucket",
    "merge_confidence",
    "merge_reason",
]

QUEUE_FIELDS = [
    "merged_item_code",
    "governance_grade",
    "priority",
    "issue_type",
    "standard_name",
    "canonical_group_path",
    "specs",
    "unit",
    "missing_specs",
    "governance_reason",
    "next_action",
    "source_rows",
    "alias_names",
]

BREAKDOWN_FIELDS = [
    "section",
    "key",
    "label",
    "count",
    "percent",
    "description",
]

GRADE_LABELS = {
    "A": "A-可发布候选",
    "B": "B-简单确认",
    "C": "C-补关键规格",
    "D": "D-阻塞冲突",
}

DEFAULT_NEXT_ACTION = {
    "A": "后续可进入导入前复核清单，本阶段不写入 ERPNext。",
    "B": "让业务人员确认备注中的轻微疑问后再升级为 A。",
    "C": "补齐缺失规格、型号、材质、包装或执行标准后再重新治理。",
    "D": "先解决别名、单位或分组冲突，不要自动创建物料。",
}


def normalize_for_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "").strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    return re.sub(r"\s+", "", text)


def parse_bool(value: str) -> bool:
    return normalize_for_key(value) in {"1", "true", "yes", "y", "是", "需要", "需复核"}


def parse_float(value: str, default: float = 0.0) -> float:
    try:
        return float((value or "").strip())
    except ValueError:
        return default


def split_multi(value: str) -> list[str]:
    text = unicodedata.normalize("NFKC", value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*(?:[;；|])\s*", text) if part.strip()]


def split_override_list(value: str) -> list[str]:
    text = unicodedata.normalize("NFKC", value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*(?:[;；|,\n])\s*", text) if part.strip()]


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = (value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def join_values(values: Iterable[str], separator: str = "；") -> str:
    return separator.join(dedupe_keep_order(values))


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_rules(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def active_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if not parse_bool(row.get("disabled", ""))]


def composition_by_code(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("merged_item_code", ""): row for row in rows if row.get("merged_item_code")}


def queue_issue_types_by_code(rows: list[dict[str, str]]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        issue_type = row.get("issue_type", "")
        for code in split_multi(row.get("candidate_codes", "")):
            result[code].add(issue_type)
    return result


def item_overrides_by_code(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("merged_item_code", ""): row for row in active_rows(rows) if row.get("merged_item_code")}


def alias_overrides_by_name(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in active_rows(rows):
        raw_name = row.get("normalized_raw_name") or normalize_for_key(row.get("raw_name", ""))
        if raw_name:
            result[raw_name] = row
    return result


def alias_issue_types_by_code(
    alias_context_rows: list[dict[str, str]],
    alias_overrides: dict[str, dict[str, str]],
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = defaultdict(set)
    for row in alias_context_rows:
        if row.get("requires_confirmation") != "true":
            continue
        if parse_float(row.get("candidate_count", "0")) <= 1:
            continue
        raw_key = row.get("normalized_raw_name") or normalize_for_key(row.get("raw_name", ""))
        override = alias_overrides.get(raw_key)
        for code in split_multi(row.get("candidate_codes", "")):
            if alias_override_resolves_candidate(override, code):
                continue
            result[code].add("alias_conflict")
    return result


def alias_override_resolves_candidate(override: dict[str, str] | None, code: str) -> bool:
    if not override:
        return False
    if parse_bool(override.get("requires_confirmation", "")):
        return False
    policy = normalize_for_key(override.get("alias_policy", ""))
    recommended = override.get("recommended_candidate_code", "").strip()
    if policy not in {"unique", "唯一", "resolved", "已确认"}:
        return False
    return not recommended or recommended == code


def merge_issue_maps(*maps: dict[str, set[str]]) -> dict[str, set[str]]:
    merged: dict[str, set[str]] = defaultdict(set)
    for mapping in maps:
        for code, issue_types in mapping.items():
            merged[code].update(issue_types)
    return merged


def has_open_question(value: str, rules: dict[str, object]) -> bool:
    markers = rules.get("open_question_markers") or []
    return any(str(marker) in (value or "") for marker in markers)


def matched_group_rule(
    row: dict[str, str],
    rules: dict[str, object],
    group_overrides: list[dict[str, str]],
) -> dict[str, object]:
    path = row.get("canonical_group_path", "")
    default_rule = {
        "key": "default",
        "label": "默认规则",
        "required_all": [],
        "required_any": list((rules.get("defaults") or {}).get("required_any") or []),
        "recommended_next_action": "按默认规则补齐至少一个关键规格字段。",
        "source": "default",
    }

    selected = dict(default_rule)
    for rule in rules.get("group_rules") or []:
        patterns = [str(pattern) for pattern in rule.get("canonical_group_patterns") or []]
        if any(pattern and pattern in path for pattern in patterns):
            selected.update(rule)
            selected["source"] = "rules_yaml"
            break

    for override in active_rows(group_overrides):
        pattern = override.get("canonical_group_pattern", "")
        if not pattern or pattern not in path:
            continue
        selected["key"] = override.get("group_rule_key") or selected.get("key") or "group_override"
        selected["label"] = override.get("group_rule_key") or selected.get("label") or "分组覆盖规则"
        if override.get("required_all"):
            selected["required_all"] = split_override_list(override["required_all"])
        if override.get("required_any"):
            selected["required_any"] = split_override_list(override["required_any"])
        if override.get("default_uom"):
            selected["default_uom"] = override["default_uom"]
        if override.get("unit_policy"):
            selected["unit_policy"] = override["unit_policy"]
        if override.get("alias_policy"):
            selected["alias_policy"] = override["alias_policy"]
        if override.get("release_grade"):
            selected["release_grade"] = override["release_grade"]
        if override.get("governance_reason"):
            selected["governance_reason"] = override["governance_reason"]
        selected["source"] = "group_override"

    return selected


def missing_specs_for_rule(row: dict[str, str], rule: dict[str, object]) -> list[str]:
    haystack = normalize_for_key(" ".join([row.get("standard_name", ""), row.get("specs", "")]))
    missing: list[str] = []
    for marker in rule.get("required_all") or []:
        if normalize_for_key(str(marker)) not in haystack:
            missing.append(str(marker))

    required_any = [str(marker) for marker in rule.get("required_any") or []]
    if required_any and not any(normalize_for_key(marker) in haystack for marker in required_any):
        missing.append(f"至少一个: {join_values(required_any)}")
    return missing


def classify_row(
    row: dict[str, str],
    composition: dict[str, str],
    issue_types: set[str],
    rule: dict[str, object],
    item_override: dict[str, str] | None,
    rules: dict[str, object],
) -> dict[str, str]:
    code = row["merged_item_code"]
    missing_specs = missing_specs_for_rule(row, rule)
    needs_human_review = parse_bool(row.get("needs_human_review", ""))
    note_question = has_open_question(row.get("notes", ""), rules)
    blocking_types = set(rules.get("blocking_issue_types") or [])
    low_precision_types = set(rules.get("low_precision_issue_types") or [])
    has_blocking = bool(issue_types & blocking_types)
    has_low_precision = bool(issue_types & low_precision_types)

    override_source = ""
    if item_override and item_override.get("governance_grade"):
        grade = item_override["governance_grade"].strip().upper()
        issue_type = item_override.get("issue_type") or "item_override"
        reason = item_override.get("governance_reason") or "按单物料覆盖表指定治理等级。"
        next_action = item_override.get("next_action") or DEFAULT_NEXT_ACTION.get(grade, "")
        override_missing = split_override_list(item_override.get("missing_specs", ""))
        if override_missing:
            missing_specs = override_missing
        override_source = "item_override"
    elif has_blocking:
        grade = "D"
        issue_type = first_issue(issue_types, ["alias_conflict", "unit_conflict"]) or "blocking_conflict"
        reason = "存在阻塞冲突，不能自动放行。"
        next_action = DEFAULT_NEXT_ACTION["D"]
    elif missing_specs:
        grade = "C"
        issue_type = "missing_specs"
        reason = "未满足当前分组的关键规格模板。"
        next_action = str(rule.get("recommended_next_action") or DEFAULT_NEXT_ACTION["C"])
    elif has_low_precision or needs_human_review:
        grade = "C"
        issue_type = first_issue(issue_types, sorted(low_precision_types)) or "needs_human_review"
        reason = "存在低精度或人工复核标记，需要补齐信息。"
        next_action = str(rule.get("recommended_next_action") or DEFAULT_NEXT_ACTION["C"])
    elif note_question:
        grade = "B"
        issue_type = "note_question"
        reason = "备注中仍有轻微待确认问题。"
        next_action = DEFAULT_NEXT_ACTION["B"]
    else:
        grade = str(rule.get("release_grade") or "A").strip().upper()
        issue_type = ""
        reason = "规则完整，规格满足模板，单位明确，未发现阻塞冲突。"
        next_action = DEFAULT_NEXT_ACTION.get(grade, DEFAULT_NEXT_ACTION["A"])

    return {
        "merged_item_code": code,
        "standard_name": row.get("standard_name", ""),
        "canonical_group_path": row.get("canonical_group_path", ""),
        "specs": row.get("specs", ""),
        "unit": row.get("unit", ""),
        "source_count": row.get("source_count", ""),
        "source_candidate_count": composition.get("source_candidate_count", "1"),
        "alias_names": row.get("alias_names", ""),
        "source_rows": row.get("source_rows", ""),
        "governance_grade": grade,
        "governance_status": GRADE_LABELS.get(grade, grade),
        "issue_type": issue_type,
        "missing_specs": join_values(missing_specs),
        "governance_reason": reason,
        "next_action": next_action,
        "matched_rule_key": str(rule.get("key") or ""),
        "matched_rule_label": str(rule.get("label") or ""),
        "rule_source": str(rule.get("source") or ""),
        "override_source": override_source,
        "has_blocking_conflict": "true" if has_blocking else "false",
        "has_alias_conflict": "true" if "alias_conflict" in issue_types else "false",
        "has_unit_conflict": "true" if "unit_conflict" in issue_types else "false",
        "has_low_precision": "true" if has_low_precision else "false",
        "needs_human_review": row.get("needs_human_review", ""),
        "note_has_open_question": "true" if note_question else "false",
        "related_conflict_types": composition.get("related_conflict_types", ""),
        "resolution_issue_types": join_values(sorted(issue_types)),
        "original_composition_bucket": composition.get("composition_bucket", ""),
        "merge_confidence": row.get("merge_confidence", ""),
        "merge_reason": row.get("merge_reason", ""),
    }


def first_issue(issue_types: set[str], preference: Iterable[str]) -> str:
    for issue_type in preference:
        if issue_type in issue_types:
            return issue_type
    return sorted(issue_types)[0] if issue_types else ""


def queue_priority(grade: str, issue_type: str) -> str:
    if grade == "D" or issue_type in {"alias_conflict", "unit_conflict"}:
        return "high"
    if grade == "C":
        return "medium"
    return "low"


def build_queue_rows(governed_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for row in governed_rows:
        if row["governance_grade"] == "A":
            continue
        rows.append(
            {
                "merged_item_code": row["merged_item_code"],
                "governance_grade": row["governance_grade"],
                "priority": queue_priority(row["governance_grade"], row["issue_type"]),
                "issue_type": row["issue_type"],
                "standard_name": row["standard_name"],
                "canonical_group_path": row["canonical_group_path"],
                "specs": row["specs"],
                "unit": row["unit"],
                "missing_specs": row["missing_specs"],
                "governance_reason": row["governance_reason"],
                "next_action": row["next_action"],
                "source_rows": row["source_rows"],
                "alias_names": row["alias_names"],
            }
        )
    return rows


def add_breakdown(
    rows: list[dict[str, str]],
    section: str,
    counter: Counter[str],
    total: int,
    descriptions: dict[str, str] | None = None,
) -> None:
    descriptions = descriptions or {}
    for key, count in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
        rows.append(
            {
                "section": section,
                "key": key,
                "label": key,
                "count": str(count),
                "percent": f"{(count / total * 100):.2f}%" if total else "0.00%",
                "description": descriptions.get(key, ""),
            }
        )


def top_group(path: str) -> str:
    return (path or "未分组").split("/", 1)[0] or "未分组"


def build_breakdown_rows(governed_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    total = len(governed_rows)
    rows: list[dict[str, str]] = []
    add_breakdown(rows, "治理等级", Counter(row["governance_grade"] for row in governed_rows), total, GRADE_LABELS)
    add_breakdown(rows, "问题类型", Counter(row["issue_type"] or "none" for row in governed_rows), total)
    add_breakdown(rows, "匹配规则", Counter(row["matched_rule_key"] for row in governed_rows), total)
    add_breakdown(rows, "规则来源", Counter(row["rule_source"] for row in governed_rows), total)
    add_breakdown(rows, "一级分组", Counter(top_group(row["canonical_group_path"]) for row in governed_rows), total)
    add_breakdown(
        rows,
        "缺失规格",
        Counter(spec for row in governed_rows for spec in (split_multi(row["missing_specs"]) or ["none"])),
        total,
    )
    return rows


def govern_material_catalog(
    rules_path: Path = DEFAULT_RULES_PATH,
    merged_catalog_path: Path = DEFAULT_MERGED_CATALOG_PATH,
    composition_items_path: Path = DEFAULT_COMPOSITION_ITEMS_PATH,
    resolution_queue_path: Path = DEFAULT_RESOLUTION_QUEUE_PATH,
    alias_context_path: Path = DEFAULT_ALIAS_CONTEXT_PATH,
    group_overrides_path: Path = DEFAULT_GROUP_OVERRIDES_PATH,
    item_overrides_path: Path = DEFAULT_ITEM_OVERRIDES_PATH,
    alias_overrides_path: Path = DEFAULT_ALIAS_OVERRIDES_PATH,
    governed_catalog_path: Path = DEFAULT_GOVERNED_CATALOG_PATH,
    release_candidates_path: Path = DEFAULT_RELEASE_CANDIDATES_PATH,
    governance_queue_path: Path = DEFAULT_GOVERNANCE_QUEUE_PATH,
    breakdown_path: Path = DEFAULT_BREAKDOWN_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
) -> dict[str, object]:
    rules = load_rules(rules_path)
    merged_rows = read_csv(merged_catalog_path)
    composition = composition_by_code(read_csv(composition_items_path))
    resolution_issue_map = queue_issue_types_by_code(read_csv(resolution_queue_path))
    item_overrides = item_overrides_by_code(read_csv(item_overrides_path))
    alias_overrides = alias_overrides_by_name(read_csv(alias_overrides_path))
    alias_issue_map = alias_issue_types_by_code(read_csv(alias_context_path), alias_overrides)
    issue_map = merge_issue_maps(resolution_issue_map, alias_issue_map)
    group_overrides = read_csv(group_overrides_path)

    governed_rows: list[dict[str, str]] = []
    for row in merged_rows:
        code = row["merged_item_code"]
        rule = matched_group_rule(row, rules, group_overrides)
        governed_rows.append(
            classify_row(
                row=row,
                composition=composition.get(code, {}),
                issue_types=issue_map.get(code, set()),
                rule=rule,
                item_override=item_overrides.get(code),
                rules=rules,
            )
        )

    release_rows = [row for row in governed_rows if row["governance_grade"] == "A"]
    queue_rows = build_queue_rows(governed_rows)
    breakdown_rows = build_breakdown_rows(governed_rows)

    write_csv(governed_catalog_path, GOVERNED_FIELDS, governed_rows)
    write_csv(release_candidates_path, GOVERNED_FIELDS, release_rows)
    write_csv(governance_queue_path, QUEUE_FIELDS, queue_rows)
    write_csv(breakdown_path, BREAKDOWN_FIELDS, breakdown_rows)

    grade_counts = Counter(row["governance_grade"] for row in governed_rows)
    summary = {
        "merged_rows": len(merged_rows),
        "governed_rows": len(governed_rows),
        "release_candidate_rows": len(release_rows),
        "governance_queue_rows": len(queue_rows),
        "grade_counts": dict(grade_counts),
        "grade_total": sum(grade_counts.values()),
        "issue_type_counts": dict(Counter(row["issue_type"] or "none" for row in governed_rows)),
        "rule_source_counts": dict(Counter(row["rule_source"] for row in governed_rows)),
        "override_counts": dict(Counter(row["override_source"] or "none" for row in governed_rows)),
        "outputs": {
            "governed_catalog": str(governed_catalog_path),
            "release_candidates": str(release_candidates_path),
            "governance_queue": str(governance_queue_path),
            "breakdown": str(breakdown_path),
            "summary": str(summary_path),
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply A/B/C/D governance rules to merged material catalog candidates.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES_PATH)
    parser.add_argument("--merged-catalog", type=Path, default=None)
    parser.add_argument("--composition-items", type=Path, default=None)
    parser.add_argument("--resolution-queue", type=Path, default=None)
    parser.add_argument("--alias-context", type=Path, default=None)
    parser.add_argument("--group-overrides", type=Path, default=None)
    parser.add_argument("--item-overrides", type=Path, default=None)
    parser.add_argument("--alias-overrides", type=Path, default=None)
    parser.add_argument("--governed-catalog", type=Path, default=None)
    parser.add_argument("--release-candidates", type=Path, default=None)
    parser.add_argument("--governance-queue", type=Path, default=None)
    parser.add_argument("--breakdown", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir
    summary = govern_material_catalog(
        rules_path=args.rules,
        merged_catalog_path=args.merged_catalog or data_dir / "merged_standard_item_catalog.csv",
        composition_items_path=args.composition_items or data_dir / "material_catalog_composition_items.csv",
        resolution_queue_path=args.resolution_queue or data_dir / "material_conflict_resolution_queue.csv",
        alias_context_path=args.alias_context or data_dir / "material_alias_context_map.csv",
        group_overrides_path=args.group_overrides or data_dir / "material_group_governance_overrides.csv",
        item_overrides_path=args.item_overrides or data_dir / "material_item_governance_overrides.csv",
        alias_overrides_path=args.alias_overrides or data_dir / "material_alias_governance_overrides.csv",
        governed_catalog_path=args.governed_catalog or data_dir / "governed_material_catalog.csv",
        release_candidates_path=args.release_candidates or data_dir / "governed_release_candidates.csv",
        governance_queue_path=args.governance_queue or data_dir / "material_governance_queue.csv",
        breakdown_path=args.breakdown or data_dir / "material_governance_breakdown.csv",
        summary_path=args.summary or data_dir / "material_governance_summary.json",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
