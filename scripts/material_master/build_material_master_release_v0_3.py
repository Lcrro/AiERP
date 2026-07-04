from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "material_master" / "release_v0_3"
DEFAULT_INPUT_PATH = DEFAULT_OUTPUT_DIR / "sku_governance_unique_all.tsv"
DEFAULT_RELEASE_PATH = DEFAULT_OUTPUT_DIR / "material_master_release_v0_3.tsv"
DEFAULT_BROWSER_PATH = DEFAULT_OUTPUT_DIR / "material_master_release_v0_3_browser_data.json"
DEFAULT_SUMMARY_PATH = DEFAULT_OUTPUT_DIR / "material_master_release_v0_3_summary.json"


INPUT_FIELDS = [
    "canonical_item_code",
    "standard_item_name",
    "standard_sku_name",
    "minimal_required_specs",
    "standard_uom",
    "source_uoms",
    "unit_resolution",
    "brand",
    "aliases",
    "removed_default_fields",
    "default_fill_basis",
    "merged_from_item_codes",
    "merged_count",
    "merge_reasons",
    "governance_reasons",
    "target",
]

RELEASE_FIELDS = [
    "item_code",
    "item_name",
    "sku_name",
    "required_specs",
    "optional_specs",
    "item_group",
    "top_group",
    "sub_group",
    "material_family",
    "stock_uom",
    "purchase_uom",
    "conversion_factor",
    "aliases",
    "search_keywords",
    "brand",
    "model",
    "status",
    "quality_level",
    "agent_use_policy",
    "source_refs",
    "source_item_codes",
    "merged_count",
    "governance_note",
    "updated_at",
]


def read_tsv(path: Path, expected_fields: list[str]) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != expected_fields:
            raise ValueError(f"{path}: unexpected fields {reader.fieldnames}")
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def write_tsv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def split_terms(value: str) -> list[str]:
    result: list[str] = []
    for part in (value or "").replace(";", "；").split("；"):
        text = part.strip()
        if text and text not in result:
            result.append(text)
    return result


def join_unique(values: list[str]) -> str:
    result: list[str] = []
    for value in values:
        for part in split_terms(value):
            if part not in result:
                result.append(part)
    return "；".join(result)


def parse_target(target: str, fallback_name: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in (target or "").split("/") if part.strip()]
    fallback_parts = [part.strip() for part in (fallback_name or "").split("/") if part.strip()]
    if len(parts) >= 3:
        top_group = parts[0]
        rest = parts[1:]
        if fallback_parts and len(rest) > len(fallback_parts) and rest[-len(fallback_parts) :] == fallback_parts:
            return top_group, "/".join(rest[: -len(fallback_parts)]), fallback_name
        return top_group, "/".join(rest[:-1]), parts[-1]
    if len(parts) == 2:
        return parts[0], parts[1], fallback_name
    if len(parts) == 1:
        return parts[0], fallback_name, fallback_name
    return "未分组", fallback_name or "未命名", fallback_name or "未命名"


def build_search_keywords(row: dict[str, str], top_group: str, family: str, item_name: str) -> str:
    values = [
        row["canonical_item_code"],
        row["standard_sku_name"],
        row["standard_item_name"],
        item_name,
        family,
        top_group,
        row["minimal_required_specs"],
        row["standard_uom"],
        row["brand"],
        row["aliases"],
        row["merged_from_item_codes"],
    ]
    return " ".join(part for part in join_unique(values).split("；") if part)


def build_governance_note(row: dict[str, str]) -> str:
    parts = []
    if row.get("unit_resolution"):
        parts.append(row["unit_resolution"])
    if row.get("default_fill_basis"):
        parts.append(f"补齐依据：{row['default_fill_basis']}")
    if row.get("merge_reasons"):
        parts.append(f"合并依据：{row['merge_reasons']}")
    return join_unique(parts)


def build_release_row(row: dict[str, str], updated_at: str) -> dict[str, str]:
    top_group, material_family, item_name = parse_target(row["target"], row["standard_item_name"])
    item_group = f"{top_group}/{material_family}" if material_family else top_group
    source_item_codes = row["merged_from_item_codes"]
    source_refs = join_unique(
        [
            f"canonical={row['canonical_item_code']}",
            f"source_item_codes={source_item_codes}",
            f"merged_count={row['merged_count']}",
            "sku_governance=batch_all_sku_governance_20260703",
        ]
    )
    return {
        "item_code": row["canonical_item_code"],
        "item_name": item_name or row["standard_item_name"],
        "sku_name": row["standard_sku_name"],
        "required_specs": row["minimal_required_specs"],
        "optional_specs": "",
        "item_group": item_group,
        "top_group": top_group,
        "sub_group": material_family,
        "material_family": material_family,
        "stock_uom": row["standard_uom"],
        "purchase_uom": "",
        "conversion_factor": "",
        "aliases": row["aliases"],
        "search_keywords": build_search_keywords(row, top_group, material_family, item_name),
        "brand": row["brand"],
        "model": "",
        "status": "active",
        "quality_level": "standard",
        "agent_use_policy": "auto_select_allowed",
        "source_refs": source_refs,
        "source_item_codes": source_item_codes,
        "merged_count": row["merged_count"],
        "governance_note": build_governance_note(row),
        "updated_at": updated_at,
    }


def is_ordinary_88_bolt(row: dict[str, str]) -> bool:
    return (
        row["material_family"] == "螺丝/螺栓"
        and row["item_name"] == "普通螺栓"
        and "强度等级：8.8" in row["required_specs"]
    )


def strip_strength_prefix(value: str) -> str:
    text = value.strip()
    for prefix in ("6.8级", "8.8级", "10.9级", "12.9级"):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def clean_ordinary_bolt_text(value: str) -> str:
    return (value or "").replace("普通螺栓", "螺栓")


def with_grade_in_bolt_names(row: dict[str, str], grade: str) -> dict[str, str]:
    next_row = dict(row)
    next_row["item_name"] = f"{grade}级螺栓"
    sku_name = strip_strength_prefix(row["sku_name"])
    if sku_name.startswith("普通螺栓"):
        next_row["sku_name"] = sku_name.replace("普通螺栓", f"{grade}级螺栓", 1)
    elif sku_name.startswith("螺栓"):
        next_row["sku_name"] = sku_name.replace("螺栓", f"{grade}级螺栓", 1)
    elif "普通螺栓" in sku_name:
        next_row["sku_name"] = sku_name.replace("普通螺栓", f"{grade}级螺栓", 1)
    else:
        next_row["sku_name"] = f"{grade}级螺栓 {sku_name}"
    next_row["required_specs"] = row["required_specs"].replace("强度等级：8.8", f"强度等级：{grade}")
    next_row["aliases"] = join_unique([row["aliases"].replace("普通螺栓", "螺栓"), f"{grade}级螺栓", "螺栓"])
    next_row["search_keywords"] = " ".join(
        part
        for part in join_unique(
            [
                clean_ordinary_bolt_text(row["search_keywords"]),
                next_row["item_name"],
                next_row["sku_name"],
                next_row["required_specs"],
                next_row["aliases"],
            ]
        ).split("；")
        if part
    )
    for field in ("source_refs", "governance_note"):
        next_row[field] = clean_ordinary_bolt_text(next_row.get(field, ""))
    return next_row


def derive_ordinary_68_bolt(row: dict[str, str]) -> dict[str, str]:
    derived = with_grade_in_bolt_names(row, "6.8")
    derived["item_code"] = f"{row['item_code']}-68"
    derived["source_refs"] = join_unique(
        [
            row["source_refs"],
            f"derived_from={row['item_code']}",
            "derive_rule=ordinary_bolt_6.8_from_8.8_v0.1",
        ]
    )
    derived["governance_note"] = join_unique(
        [
            row["governance_note"],
            "派生：按工地常用 6.8级螺栓，从 8.8级螺栓规格复制生成",
        ]
    )
    return derived


def apply_release_overrides(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    expanded: list[dict[str, str]] = []
    for row in rows:
        if is_ordinary_88_bolt(row):
            row_88 = with_grade_in_bolt_names(row, "8.8")
            expanded.append(row_88)
            expanded.append(derive_ordinary_68_bolt(row_88))
        else:
            expanded.append(row)
    return expanded


def group_counts(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    return dict(Counter(row[key] for row in rows).most_common())


def build_summary(rows: list[dict[str, str]], input_path: Path, release_path: Path) -> dict[str, object]:
    source_codes = []
    for row in rows:
        source_codes.extend(split_terms(row["source_item_codes"]))
    duplicate_key_counter = Counter((row["sku_name"], row["required_specs"]) for row in rows)
    duplicate_keys = [f"{name} | {spec}" for (name, spec), count in duplicate_key_counter.items() if count > 1]
    return {
        "input": str(input_path),
        "output": str(release_path),
        "sku_count": len(rows),
        "source_sku_count": len(set(source_codes)),
        "source_sku_refs": len(source_codes),
        "item_name_count": len({row["item_name"] for row in rows}),
        "material_family_count": len({row["material_family"] for row in rows}),
        "top_group_count": len({row["top_group"] for row in rows}),
        "item_group_count": len({row["item_group"] for row in rows}),
        "status_counts": group_counts(rows, "status"),
        "quality_counts": group_counts(rows, "quality_level"),
        "agent_use_policy_counts": group_counts(rows, "agent_use_policy"),
        "stock_uom_counts": group_counts(rows, "stock_uom"),
        "top_group_counts": group_counts(rows, "top_group"),
        "material_family_counts": group_counts(rows, "material_family"),
        "derived_sku_count": sum(1 for row in rows if "derived_from=" in row["source_refs"]),
        "duplicate_sku_name_spec_key_count": len(duplicate_keys),
        "duplicate_sku_name_spec_keys": duplicate_keys[:50],
        "empty_field_counts": {
            field: sum(1 for row in rows if not row[field])
            for field in RELEASE_FIELDS
        },
    }


def browser_row(row: dict[str, str]) -> dict[str, str]:
    search_text = " ".join(
        [
            row["item_code"],
            row["item_name"],
            row["sku_name"],
            row["required_specs"],
            row["item_group"],
            row["top_group"],
            row["material_family"],
            row["stock_uom"],
            row["aliases"],
            row["brand"],
            row["search_keywords"],
        ]
    ).lower()
    return {
        **row,
        "family_rule": "",
        "family_note": "发布版 v0.3：DeepSeek SKU 治理合并结果",
        "family_type": "",
        "family_material": "",
        "family_use": "",
        "family_connection": "",
        "family_surface": "",
        "family_attributes": "",
        "family_split_candidates": "",
        "family_attribute_terms": "",
        "drill_material": "",
        "drill_use_type": "",
        "drill_shank": "",
        "search_text": search_text,
        "is_likely_hand_glove": "yes" if "手套" in row["item_name"] or "手套" in row["sku_name"] else "no",
    }


def build_categories(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["top_group"]].append(row)
    categories: list[dict[str, object]] = []
    for top_group, group_rows in grouped.items():
        sub_groups = [
            {"name": name, "sku_count": count}
            for name, count in sorted(group_counts(group_rows, "sub_group").items(), key=lambda item: (-item[1], item[0]))
        ]
        categories.append(
            {
                "name": top_group,
                "sku_count": len(group_rows),
                "name_count": len({row["material_family"] for row in group_rows}),
                "status_counts": group_counts(group_rows, "status"),
                "quality_counts": group_counts(group_rows, "quality_level"),
                "sub_groups": sub_groups,
            }
        )
    return sorted(categories, key=lambda item: (-int(item["sku_count"]), str(item["name"])))


def build_browser_payload(
    rows: list[dict[str, str]],
    summary: dict[str, object],
    release_path: Path,
    generated_at: str,
) -> dict[str, object]:
    browser_rows = [browser_row(row) for row in rows]
    return {
        "generated_at": generated_at,
        "source": str(release_path),
        "family_rules_source": "",
        "family_rules_count": 0,
        "summary": summary,
        "categories": build_categories(browser_rows),
        "family_rule_impacts": [],
        "rows": browser_rows,
    }


def validate_release(rows: list[dict[str, str]], summary: dict[str, object]) -> None:
    required_fields = ["item_code", "item_name", "sku_name", "required_specs", "item_group", "stock_uom"]
    for index, row in enumerate(rows, start=2):
        for field in required_fields:
            if not row[field]:
                raise ValueError(f"release row {index}: missing {field}")
    item_codes = [row["item_code"] for row in rows]
    duplicate_codes = [code for code, count in Counter(item_codes).items() if count > 1]
    if duplicate_codes:
        raise ValueError(f"duplicate item_code in release table: {duplicate_codes[:20]}")
    if summary["duplicate_sku_name_spec_key_count"]:
        raise ValueError("duplicate sku_name + required_specs keys remain")
    if summary["source_sku_count"] != 2328:
        raise ValueError(f"expected 2328 covered source SKU codes, got {summary['source_sku_count']}")
    for row in rows:
        if "公元" in json.dumps(row, ensure_ascii=False):
            raise ValueError(f"release row still contains 公元: {row['item_code']}")


def build_release(
    input_path: Path,
    release_path: Path,
    browser_path: Path,
    summary_path: Path,
    generated_at: str,
) -> dict[str, object]:
    input_rows = read_tsv(input_path, INPUT_FIELDS)
    release_rows = apply_release_overrides([build_release_row(row, generated_at) for row in input_rows])
    release_rows.sort(key=lambda row: (row["top_group"], row["material_family"], row["item_name"], row["sku_name"], row["item_code"]))
    summary = build_summary(release_rows, input_path, release_path)
    validate_release(release_rows, summary)
    write_tsv(release_path, release_rows, RELEASE_FIELDS)
    write_json(summary_path, summary)
    write_json(browser_path, build_browser_payload(release_rows, summary, release_path, generated_at))
    return {
        "release_tsv": str(release_path),
        "browser_json": str(browser_path),
        "summary_json": str(summary_path),
        **summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build material master release v0.3 from governed unique SKU rows.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--release", type=Path, default=DEFAULT_RELEASE_PATH)
    parser.add_argument("--browser-json", type=Path, default=DEFAULT_BROWSER_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--generated-at", default=date.today().isoformat())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_release(args.input, args.release, args.browser_json, args.summary, args.generated_at)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
