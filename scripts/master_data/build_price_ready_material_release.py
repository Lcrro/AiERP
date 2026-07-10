from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable


DEFAULT_SOURCE_ROOT = Path("outputs/master_data/price_ready_sku_trial")
DEFAULT_AUTHORITY_TSV = Path("data/material_master/release_v0_3/material_master_release_v0_3.tsv")
DEFAULT_RELEASE_DIR = Path("data/material_master/price_ready_release_v0_1")
DEFAULT_RELEASE_TSV = DEFAULT_RELEASE_DIR / "material_master_price_ready_release_v0_1.tsv"
DEFAULT_BROWSER_JSON = DEFAULT_RELEASE_DIR / "material_master_price_ready_browser_data.json"
DEFAULT_DUPLICATES_TSV = DEFAULT_RELEASE_DIR / "material_master_price_ready_duplicates.tsv"
DEFAULT_SUMMARY_JSON = DEFAULT_RELEASE_DIR / "material_master_price_ready_summary.json"


RELEASE_FIELDS = [
    "item_code",
    "source_item_codes",
    "merged_count",
    "item_name",
    "sku_name",
    "required_specs",
    "item_group",
    "top_group",
    "sub_group",
    "material_family",
    "unit",
    "estimated_rate",
    "currency",
    "price_basis",
    "default_fill_basis",
    "aliases",
    "brand",
    "model",
    "original_item_name",
    "original_sku_name",
    "original_required_specs",
    "original_unit",
    "updated_at",
]


def latest_price_ready_source(root: Path) -> Path:
    candidates = sorted(root.glob("*/price_ready_sku_trial_output.tsv"))
    if not candidates:
        raise FileNotFoundError(f"No price-ready output found under {root}")
    return candidates[-1]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return [dict(row) for row in csv.DictReader(f, delimiter="\t")]


def read_authority_map(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    return {row["item_code"]: row for row in read_tsv(path) if row.get("item_code")}


def write_tsv(path: Path, rows: Iterable[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def split_terms(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[；;]", value or "") if part.strip()]


def append_note(value: str, note: str) -> str:
    parts = split_terms(value)
    if note not in parts:
        parts.append(note)
    return "；".join(parts)


def clean_formal_text(value: str, *, is_spec: bool = False) -> tuple[str, bool]:
    original = value or ""
    cleaned = original.replace("；", ";")
    cleaned = re.sub(r"不锈钢[（(]\s*默认\s*(201|304|316)\s*[）)]", r"\1不锈钢", cleaned)
    cleaned = re.sub(r"([0-9.*×xX]+)\s*[（(]\s*单位\s*([a-zA-Z\u4e00-\u9fff]+)\s*默认\s*[）)]", r"\1\2", cleaned)
    cleaned = re.sub(r"约(?=\d)", "", cleaned)
    cleaned = re.sub(r"[（(]\s*(?:默认|常见|推定|约|约为|按常用|按常见)\s*[）)]", "", cleaned)

    if is_spec:
        parts: list[str] = []
        for part in split_terms(cleaned):
            part = re.sub(r"^\s*(?:默认|常见|推定|约为|约)\s*[:：]?\s*", "", part)
            part = re.sub(r"([:：]\s*)(?:默认|常见|推定|约为|约)\s*", r"\1", part)
            part = re.sub(r"\s+", " ", part).strip(" ;；")
            if part:
                parts.append(part)
        cleaned = "；".join(parts)
    else:
        cleaned = re.sub(r"\b(?:默认|常见|推定)\b", "", cleaned)
        cleaned = re.sub(r"(?:默认|常见|推定|约为|约)\s*", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ;；")

    cleaned = cleaned.replace(";", "；")
    return cleaned, cleaned != original


def normalize_key(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("；", ";").replace("＊", "*").replace("×", "*").replace("x", "*")
    text = re.sub(r"\s+", "", text)
    return text


def duplicate_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        normalize_key(row["item_name"]),
        normalize_key(row["sku_name"]),
        normalize_key(row["required_specs"]),
        normalize_key(row["unit"]),
    )


def normalize_unit(value: str) -> str:
    text = (value or "").strip()
    unit_map = {
        "kg": "千克",
        "KG": "千克",
        "Kg": "千克",
        "公斤": "千克",
        "平方": "平方米",
    }
    return unit_map.get(text, text)


def search_text(row: dict[str, str]) -> str:
    fields = [
        "item_code",
        "item_name",
        "sku_name",
        "required_specs",
        "item_group",
        "top_group",
        "sub_group",
        "material_family",
        "unit",
        "aliases",
        "brand",
        "model",
        "original_item_name",
        "original_sku_name",
        "original_required_specs",
    ]
    return " ".join(row.get(field, "") for field in fields if row.get(field, "")).lower()


def build_search_keywords(row: dict[str, str]) -> str:
    parts: list[str] = []
    for field in [
        "item_code",
        "sku_name",
        "item_name",
        "material_family",
        "sub_group",
        "top_group",
        "required_specs",
        "unit",
        "aliases",
        "brand",
        "model",
    ]:
        value = row.get(field, "")
        if value and value not in parts:
            parts.append(value)
    return " ".join(parts)


def group_counts(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    return dict(Counter(row.get(key, "") for row in rows).most_common())


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
    categories.sort(key=lambda item: (-int(item["sku_count"]), str(item["name"])))
    return categories


def build_summary(rows: list[dict[str, str]], duplicates: list[dict[str, str]], source_path: Path) -> dict[str, object]:
    rates = [float(row["estimated_rate"]) for row in rows if row.get("estimated_rate")]
    return {
        "input": str(source_path),
        "sku_count": len(rows),
        "item_name_count": len({row["item_name"] for row in rows}),
        "material_family_count": len({row["material_family"] for row in rows}),
        "top_group_count": len({row["top_group"] for row in rows}),
        "item_group_count": len({row["item_group"] for row in rows}),
        "status_counts": group_counts(rows, "status"),
        "quality_counts": group_counts(rows, "quality_level"),
        "agent_use_policy_counts": group_counts(rows, "agent_use_policy"),
        "stock_uom_counts": group_counts(rows, "stock_uom"),
        "unit_counts": group_counts(rows, "unit"),
        "top_group_counts": group_counts(rows, "top_group"),
        "material_family_counts": dict(Counter(row["material_family"] for row in rows).most_common(50)),
        "duplicate_group_count": len({row["duplicate_group_id"] for row in duplicates}),
        "duplicate_row_count": len(duplicates),
        "min_estimated_rate": min(rates) if rates else None,
        "max_estimated_rate": max(rates) if rates else None,
        "generated_at": date.today().isoformat(),
    }


def build_release_rows(
    source_rows: list[dict[str, str]],
    authority_rows: dict[str, dict[str, str]],
) -> tuple[list[dict[str, str]], dict[str, int]]:
    stats = Counter()
    release_rows: list[dict[str, str]] = []
    for source in source_rows:
        item_code = source.get("item_code", "").strip() or source.get("source_item_code", "").strip()
        authority = authority_rows.get(item_code) or authority_rows.get(source.get("source_item_code", "").strip()) or {}
        sku_name, sku_changed = clean_formal_text(source.get("sku_name", ""))
        required_specs, specs_changed = clean_formal_text(source.get("required_specs", ""), is_spec=True)

        default_fill_basis = source.get("default_fill_basis", "").strip()
        if sku_changed or specs_changed:
            default_fill_basis = append_note(default_fill_basis, "正式字段清理：将默认、常见、推定、约等口径词移出SKU名称/必填规格。")
        if sku_changed:
            stats["cleaned_sku_name_rows"] += 1
        if specs_changed:
            stats["cleaned_required_specs_rows"] += 1

        item_name = (authority.get("item_name") or source.get("item_name") or source.get("original_item_name", "")).strip()
        top_group = (authority.get("top_group") or source.get("top_group", "")).strip()
        sub_group = (authority.get("sub_group") or source.get("sub_group", "")).strip()
        material_family = (authority.get("material_family") or source.get("material_family", "")).strip()
        item_group = (authority.get("item_group") or (f"{top_group}/{sub_group}" if sub_group else top_group)).strip()
        unit = normalize_unit(source.get("unit", "").strip() or source.get("original_unit", "").strip())
        locked_fields_changed = any(
            source.get(field, "").strip() and authority.get(field, "").strip() and source.get(field, "").strip() != authority.get(field, "").strip()
            for field in ["item_name", "top_group", "sub_group", "material_family", "item_group"]
        )
        if authority and locked_fields_changed:
            stats["locked_hierarchy_rows"] += 1
            default_fill_basis = append_note(
                default_fill_basis,
                "层级字段锁定：物料名称/分组取自 release_v0_3，DeepSeek 仅补SKU、规格、单位和测试价。",
            )

        release_rows.append(
            {
                "item_code": item_code,
                "source_item_codes": item_code,
                "merged_count": "1",
                "item_name": item_name,
                "sku_name": sku_name,
                "required_specs": required_specs,
                "item_group": item_group,
                "top_group": top_group,
                "sub_group": sub_group,
                "material_family": material_family,
                "unit": unit,
                "estimated_rate": source.get("estimated_rate", "").strip(),
                "currency": source.get("currency", "CNY").strip() or "CNY",
                "price_basis": source.get("price_basis", "").strip(),
                "default_fill_basis": default_fill_basis,
                "aliases": source.get("aliases", "").strip() or authority.get("aliases", "").strip(),
                "brand": source.get("brand", "").strip() or authority.get("brand", "").strip(),
                "model": source.get("model", "").strip() or authority.get("model", "").strip(),
                "original_item_name": source.get("original_item_name", "").strip(),
                "original_sku_name": source.get("original_sku_name", "").strip(),
                "original_required_specs": source.get("original_required_specs", "").strip(),
                "original_unit": source.get("original_unit", "").strip(),
                "updated_at": date.today().isoformat(),
            }
        )
    return release_rows, dict(stats)


def duplicate_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: defaultdict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[duplicate_key(row)].append(row)

    duplicates: list[dict[str, str]] = []
    group_index = 1
    for _, group_rows in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[1][0]["item_code"])):
        if len(group_rows) < 2:
            continue
        group_id = f"DUP-{group_index:04d}"
        keep = sorted(group_rows, key=lambda row: row["item_code"])[0]["item_code"]
        for row in sorted(group_rows, key=lambda row: row["item_code"]):
            duplicates.append(
                {
                    "duplicate_group_id": group_id,
                    "duplicate_count": str(len(group_rows)),
                    "keep_candidate_item_code": keep,
                    "action": "keep" if row["item_code"] == keep else "merge_into_keep",
                    "item_code": row["item_code"],
                    "item_name": row["item_name"],
                    "sku_name": row["sku_name"],
                    "required_specs": row["required_specs"],
                    "unit": row["unit"],
                    "estimated_rate": row["estimated_rate"],
                    "original_sku_name": row["original_sku_name"],
                    "default_fill_basis": row["default_fill_basis"],
                }
            )
        group_index += 1
    return duplicates


def merge_unique_terms(values: Iterable[str]) -> str:
    merged: list[str] = []
    for value in values:
        for term in split_terms(value):
            if term and term not in merged:
                merged.append(term)
    return "；".join(merged)


def average_rate(rows: list[dict[str, str]]) -> str:
    rates: list[float] = []
    for row in rows:
        try:
            rates.append(float(row.get("estimated_rate", "")))
        except ValueError:
            continue
    if not rates:
        return ""
    return f"{sum(rates) / len(rates):.2f}"


def collapse_duplicate_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    grouped: defaultdict[tuple[str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[duplicate_key(row)].append(row)

    collapsed: list[dict[str, str]] = []
    actions: list[dict[str, str]] = []
    for _, group_rows in sorted(grouped.items(), key=lambda item: item[1][0]["item_code"]):
        sorted_rows = sorted(group_rows, key=lambda row: row["item_code"])
        keep = dict(sorted_rows[0])
        if len(sorted_rows) == 1:
            collapsed.append(keep)
            continue

        source_codes = [row["item_code"] for row in sorted_rows]
        keep["source_item_codes"] = "；".join(source_codes)
        keep["merged_count"] = str(len(sorted_rows))
        keep["aliases"] = merge_unique_terms(row.get("aliases", "") for row in sorted_rows)
        keep["original_sku_name"] = merge_unique_terms(row.get("original_sku_name", "") for row in sorted_rows)
        keep["default_fill_basis"] = append_note(
            merge_unique_terms(row.get("default_fill_basis", "") for row in sorted_rows),
            f"重复合并：合并来源编码 {keep['source_item_codes']}，保留编码 {keep['item_code']}。",
        )

        distinct_rates = {row.get("estimated_rate", "") for row in sorted_rows}
        if len(distinct_rates) > 1:
            keep["estimated_rate"] = average_rate(sorted_rows)
            keep["price_basis"] = append_note(keep.get("price_basis", ""), "重复合并：测试单价取来源估价均值。")

        action_group_id = f"DEDUP-{len({action['duplicate_group_id'] for action in actions}) + 1:04d}"
        for row in sorted_rows:
            actions.append(
                {
                    "duplicate_group_id": action_group_id,
                    "duplicate_count": str(len(sorted_rows)),
                    "keep_candidate_item_code": keep["item_code"],
                    "action": "keep" if row["item_code"] == keep["item_code"] else "merge_into_keep",
                    "item_code": row["item_code"],
                    "item_name": row["item_name"],
                    "sku_name": row["sku_name"],
                    "required_specs": row["required_specs"],
                    "unit": row["unit"],
                    "estimated_rate": row["estimated_rate"],
                    "original_sku_name": row["original_sku_name"],
                    "default_fill_basis": row["default_fill_basis"],
                }
            )
        collapsed.append(keep)
    return collapsed, actions


def browser_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for row in rows:
        browser_row = {
            **row,
            "stock_uom": row["unit"],
            "purchase_uom": row["unit"],
            "conversion_factor": "1",
            "status": "active",
            "quality_level": "standard",
            "agent_use_policy": "confirm_before_use",
            "optional_specs": "",
            "source_refs": f"price_ready_v0.1_source={row.get('source_item_codes') or row['item_code']}",
            "source_item_codes": row.get("source_item_codes", row["item_code"]),
            "merged_count": row.get("merged_count", "1"),
            "governance_note": row["default_fill_basis"],
            "family_rule": "price_ready_release_v0.1",
            "family_note": "价格就绪版：SKU名称、核心规格、单位和测试单价已补齐。",
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
            "search_keywords": build_search_keywords(row),
        }
        browser_row["search_text"] = search_text(browser_row)
        browser_row["is_likely_hand_glove"] = "yes" if "手套" in browser_row["search_text"] else "no"
        result.append(browser_row)
    return result


def build_release(
    source_path: Path,
    release_tsv: Path,
    browser_json: Path,
    duplicates_tsv: Path,
    summary_json: Path,
    authority_tsv: Path = DEFAULT_AUTHORITY_TSV,
) -> dict[str, object]:
    source_rows = read_tsv(source_path)
    authority_rows = read_authority_map(authority_tsv)
    rows, clean_stats = build_release_rows(source_rows, authority_rows)
    duplicate_candidates = duplicate_rows(rows)
    rows, dedup_actions = collapse_duplicate_rows(rows)
    remaining_duplicates = duplicate_rows(rows)

    write_tsv(release_tsv, rows, RELEASE_FIELDS)
    write_tsv(
        duplicates_tsv,
        dedup_actions,
        [
            "duplicate_group_id",
            "duplicate_count",
            "keep_candidate_item_code",
            "action",
            "item_code",
            "item_name",
            "sku_name",
            "required_specs",
            "unit",
            "estimated_rate",
            "original_sku_name",
            "default_fill_basis",
        ],
    )

    browser_ready_rows = browser_rows(rows)
    summary = build_summary(browser_ready_rows, remaining_duplicates, source_path)
    summary.update(clean_stats)
    summary.update(
        {
            "duplicate_candidate_group_count": len({row["duplicate_group_id"] for row in duplicate_candidates}),
            "duplicate_candidate_row_count": len(duplicate_candidates),
            "resolved_duplicate_group_count": len({row["keep_candidate_item_code"] for row in dedup_actions}),
            "resolved_duplicate_row_count": len(dedup_actions),
            "resolved_duplicate_removed_rows": len(dedup_actions) - len({row["keep_candidate_item_code"] for row in dedup_actions}),
        }
    )
    payload = {
        "generated_at": date.today().isoformat(),
        "source": str(release_tsv),
        "price_ready_source": str(source_path),
        "authority_source": str(authority_tsv) if authority_rows else "",
        "family_rules_source": "",
        "family_rules_count": 0,
        "summary": summary,
        "categories": build_categories(browser_ready_rows),
        "family_rule_impacts": [],
        "rows": browser_ready_rows,
    }
    write_json(browser_json, payload)
    write_json(summary_json, summary)
    return {
        "source": str(source_path),
        "authority_source": str(authority_tsv) if authority_rows else "",
        "release_tsv": str(release_tsv),
        "browser_json": str(browser_json),
        "duplicates_tsv": str(duplicates_tsv),
        "summary_json": str(summary_json),
        **summary,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a price-ready material master release from DeepSeek SKU output.")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--authority-tsv", type=Path, default=DEFAULT_AUTHORITY_TSV)
    parser.add_argument("--release-tsv", type=Path, default=DEFAULT_RELEASE_TSV)
    parser.add_argument("--browser-json", type=Path, default=DEFAULT_BROWSER_JSON)
    parser.add_argument("--duplicates-tsv", type=Path, default=DEFAULT_DUPLICATES_TSV)
    parser.add_argument("--summary-json", type=Path, default=DEFAULT_SUMMARY_JSON)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    source_path = args.source or latest_price_ready_source(args.source_root)
    result = build_release(
        source_path,
        args.release_tsv,
        args.browser_json,
        args.duplicates_tsv,
        args.summary_json,
        args.authority_tsv,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
