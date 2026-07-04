from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_PATH = REPO_ROOT / "data" / "material_purchase_2024" / "standard_item_master_draft.tsv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "material_master"
DEFAULT_MASTER_PATH = DEFAULT_OUTPUT_DIR / "material_master.tsv"
DEFAULT_SUMMARY_PATH = DEFAULT_OUTPUT_DIR / "material_master_summary.json"


SOURCE_FIELDS = [
    "draft_sku_id",
    "draft_item_code",
    "code_prefix",
    "release_status",
    "放行等级",
    "标准名称",
    "必填规格",
    "辅助规格",
    "标准分组",
    "标准单位",
    "别名/土名",
    "candidate_count",
    "source_candidate_rows",
    "source_file_rows",
    "grade_counts",
    "matched_category",
    "import_decision",
    "missing_specs",
    "整理依据",
    "dedupe_key",
]

MASTER_FIELDS = [
    "item_code",
    "item_name",
    "required_specs",
    "optional_specs",
    "item_group",
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
    "governance_note",
    "updated_at",
]

GRADE_POLICY = {
    "A": ("active", "standard", "auto_select_allowed"),
    "B": ("candidate", "usable", "confirm_before_use"),
    "C": ("candidate", "needs_review", "clarify_specs_before_use"),
    "D": ("disabled", "blocked", "do_not_use"),
}

RELEASE_POLICY = {
    "ready": GRADE_POLICY["A"],
    "needs_confirmation": GRADE_POLICY["B"],
    "needs_missing_specs": GRADE_POLICY["C"],
    "blocked": GRADE_POLICY["D"],
}


def read_source(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != SOURCE_FIELDS:
            raise ValueError(f"{path}: unexpected fields {reader.fieldnames}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"{path}: no rows")
    validate_source_rows(rows, path)
    return rows


def validate_source_rows(rows: list[dict[str, str]], path: Path) -> None:
    seen_codes: set[str] = set()
    required = ["draft_item_code", "标准名称", "必填规格", "标准分组", "标准单位", "别名/土名", "放行等级"]
    for index, row in enumerate(rows, start=2):
        for field in required:
            if not (row.get(field) or "").strip():
                raise ValueError(f"{path}:{index}: missing {field}")
        code = row["draft_item_code"].strip()
        if code in seen_codes:
            raise ValueError(f"{path}:{index}: duplicate draft_item_code {code}")
        seen_codes.add(code)


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def split_multi(value: str) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*[;；|,\n]\s*", text) if part.strip()]


def dedupe_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = (value or "").strip()
        if not text:
            continue
        key = normalize_key(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def normalize_key(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("：", ":").replace("（", "(").replace("）", ")")
    text = text.replace("×", "*").replace("x", "*")
    return re.sub(r"\s+", "", text)


def extract_spec_value(specs: str, key: str) -> str:
    for part in split_multi(specs):
        if "：" in part:
            part_key, value = part.split("：", 1)
        elif ":" in part:
            part_key, value = part.split(":", 1)
        else:
            continue
        if normalize_key(part_key) == normalize_key(key):
            return value.strip()
    return ""


def search_keywords(row: dict[str, str]) -> str:
    values: list[str] = [
        row["draft_item_code"],
        row["标准名称"],
        row["标准分组"],
        row["标准单位"],
    ]
    values.extend(split_multi(row["必填规格"]))
    values.extend(split_multi(row["辅助规格"]))
    values.extend(split_multi(row["别名/土名"]))

    extra: list[str] = []
    for value in values:
        if "：" in value:
            _, spec_value = value.split("：", 1)
            extra.append(spec_value)
        elif ":" in value:
            _, spec_value = value.split(":", 1)
            extra.append(spec_value)
    values.extend(extra)
    return " ".join(dedupe_keep_order(values))


def source_refs(row: dict[str, str]) -> str:
    parts = []
    if row.get("source_candidate_rows"):
        parts.append(f"purchase_2024_candidate_rows={row['source_candidate_rows']}")
    if row.get("source_file_rows"):
        parts.append(f"purchase_2024_source_rows={row['source_file_rows']}")
    if row.get("draft_sku_id"):
        parts.append(f"draft_sku_id={row['draft_sku_id']}")
    return "；".join(parts)


def governance_note(row: dict[str, str]) -> str:
    parts = []
    if row.get("missing_specs"):
        parts.append(f"缺失规格：{row['missing_specs']}")
    if row.get("整理依据"):
        parts.append(f"整理依据：{row['整理依据']}")
    if row.get("import_decision"):
        parts.append(f"导入口径：{row['import_decision']}")
    return "；".join(parts)


def status_policy(row: dict[str, str]) -> tuple[str, str, str]:
    release_status = (row.get("release_status") or "").strip()
    if release_status in RELEASE_POLICY:
        return RELEASE_POLICY[release_status]
    grade = (row.get("放行等级") or "").strip()
    return GRADE_POLICY.get(grade, ("candidate", "needs_review", "confirm_before_use"))


def build_master_row(row: dict[str, str], updated_at: str) -> dict[str, str]:
    status, quality_level, agent_use_policy = status_policy(row)
    specs = row.get("必填规格", "")
    return {
        "item_code": row["draft_item_code"].strip(),
        "item_name": row["标准名称"].strip(),
        "required_specs": specs.strip(),
        "optional_specs": (row.get("辅助规格") or "").strip(),
        "item_group": row["标准分组"].strip(),
        "stock_uom": row["标准单位"].strip(),
        "purchase_uom": "",
        "conversion_factor": "",
        "aliases": row["别名/土名"].strip(),
        "search_keywords": search_keywords(row),
        "brand": extract_spec_value(specs, "品牌"),
        "model": extract_spec_value(specs, "型号"),
        "status": status,
        "quality_level": quality_level,
        "agent_use_policy": agent_use_policy,
        "source_refs": source_refs(row),
        "governance_note": governance_note(row),
        "updated_at": updated_at,
    }


def build_summary(source_rows: list[dict[str, str]], master_rows: list[dict[str, str]], input_path: Path, master_path: Path) -> dict[str, object]:
    item_name_groups = group_counts(master_rows, ["item_name"])
    same_name_group_counts = group_counts(master_rows, ["item_name", "item_group"])
    same_name_specs_counts = group_counts(master_rows, ["item_name", "required_specs"])
    possible_duplicate_clusters = [key for key, count in same_name_specs_counts.items() if count > 1]

    return {
        "input": str(input_path),
        "output": str(master_path),
        "source_rows": len(source_rows),
        "master_rows": len(master_rows),
        "unique_item_codes": len({row["item_code"] for row in master_rows}),
        "field_count": len(MASTER_FIELDS),
        "fields": MASTER_FIELDS,
        "status_counts": dict(Counter(row["status"] for row in master_rows)),
        "quality_level_counts": dict(Counter(row["quality_level"] for row in master_rows)),
        "agent_use_policy_counts": dict(Counter(row["agent_use_policy"] for row in master_rows)),
        "stock_uom_counts": dict(Counter(row["stock_uom"] for row in master_rows).most_common()),
        "top_item_groups": dict(Counter(row["item_group"] for row in master_rows).most_common(30)),
        "top_repeated_item_names": top_counts(item_name_groups, minimum=8, limit=30),
        "top_repeated_item_name_groups": top_counts(same_name_group_counts, minimum=5, limit=30),
        "possible_duplicate_cluster_count": len(possible_duplicate_clusters),
        "possible_duplicate_clusters_sample": top_counts(same_name_specs_counts, minimum=2, limit=30),
        "empty_field_counts": empty_field_counts(master_rows),
    }


def group_counts(rows: list[dict[str, str]], fields: list[str]) -> dict[str, int]:
    counts: defaultdict[str, int] = defaultdict(int)
    for row in rows:
        key = " | ".join(row[field] for field in fields)
        counts[key] += 1
    return dict(counts)


def top_counts(counts: dict[str, int], minimum: int, limit: int) -> dict[str, int]:
    return dict(sorted(((key, count) for key, count in counts.items() if count >= minimum), key=lambda item: (-item[1], item[0]))[:limit])


def empty_field_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for field in MASTER_FIELDS:
        result[field] = sum(1 for row in rows if not (row.get(field) or "").strip())
    return result


def build_material_master(input_path: Path, master_path: Path, summary_path: Path, updated_at: str) -> dict[str, object]:
    source_rows = read_source(input_path)
    master_rows = [build_master_row(row, updated_at=updated_at) for row in source_rows]
    write_tsv(master_path, MASTER_FIELDS, master_rows)
    summary = build_summary(source_rows, master_rows, input_path=input_path, master_path=master_path)
    write_json(summary_path, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the canonical material_master.tsv from the current SKU draft.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH, help="Input standard_item_master_draft.tsv path.")
    parser.add_argument("--output", type=Path, default=DEFAULT_MASTER_PATH, help="Output material_master.tsv path.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH, help="Output material_master_summary.json path.")
    parser.add_argument("--updated-at", default=date.today().isoformat(), help="Value for updated_at, default today.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_material_master(
        input_path=args.input,
        master_path=args.output,
        summary_path=args.summary,
        updated_at=args.updated_at,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
