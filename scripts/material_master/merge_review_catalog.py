from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "material_purchase_2024"
DEFAULT_CATALOG_PATH = DEFAULT_DATA_DIR / "standard_item_catalog_from_review.csv"
DEFAULT_ALIASES_PATH = DEFAULT_DATA_DIR / "item_aliases_from_review.csv"
DEFAULT_MAPPING_PATH = DEFAULT_DATA_DIR / "material_group_canonical_mapping.csv"
DEFAULT_MERGED_CATALOG_PATH = DEFAULT_DATA_DIR / "merged_standard_item_catalog.csv"
DEFAULT_MERGED_ALIASES_PATH = DEFAULT_DATA_DIR / "merged_item_aliases.csv"
DEFAULT_CONFLICTS_PATH = DEFAULT_DATA_DIR / "merge_conflicts.csv"
DEFAULT_SUMMARY_PATH = DEFAULT_DATA_DIR / "merge_summary.json"


MERGED_CATALOG_FIELDS = [
    "merged_item_code",
    "standard_name",
    "reviewed_group_paths",
    "canonical_group_path",
    "specs",
    "unit",
    "source_count",
    "source_statuses",
    "alias_names",
    "source_rows",
    "notes",
    "merged_from_codes",
    "merge_reason",
    "merge_confidence",
    "needs_human_review",
]

MERGED_ALIAS_FIELDS = [
    "raw_name",
    "merged_item_code",
    "standard_name",
    "canonical_group_path",
    "specs",
    "unit",
    "source_proposed_item_codes",
    "alias_source",
]

CONFLICT_FIELDS = [
    "conflict_type",
    "standard_name",
    "canonical_group_path",
    "unit_values",
    "specs_values",
    "candidate_codes",
    "source_rows",
    "reason",
]

LOW_PRECISION_MARKERS = (
    "低精度",
    "缺失",
    "待补充",
    "待确认",
    "不详",
    "未明确",
    "规格型号缺失",
)

UNIT_SYNONYMS = {
    "m": "米",
    "meter": "米",
    "metre": "米",
    "米": "米",
    "个": "个",
    "件": "个",
    "只": "个",
    "set": "套",
    "套": "套",
}

BOOL_TRUE = {"1", "true", "yes", "y", "是", "需要", "需复核"}


@dataclass(frozen=True)
class GroupMapping:
    canonical_group_path: str
    needs_human_review: bool = False


@dataclass
class CatalogRecord:
    index: int
    proposed_item_code: str
    standard_name: str
    item_group: str
    canonical_group_path: str
    specs: str
    unit: str
    normalized_name: str
    normalized_unit: str
    specs_signature: str
    source_count: int
    source_statuses: set[str] = field(default_factory=set)
    alias_names: set[str] = field(default_factory=set)
    source_rows: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    low_precision: bool = False
    group_needs_human_review: bool = False

    @property
    def merge_key(self) -> tuple[str, str, str, str]:
        return (
            self.normalized_name,
            self.canonical_group_path,
            self.normalized_unit,
            self.specs_signature,
        )

    @property
    def review_key(self) -> tuple[str, str]:
        return (self.normalized_name, self.canonical_group_path)

    @property
    def needs_human_review(self) -> bool:
        return self.low_precision or self.group_needs_human_review

    @property
    def status_is_mergeable(self) -> bool:
        return any("可合并" in status for status in self.source_statuses)


def normalize_for_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.strip().lower()
    text = re.sub(r"\s+", "", text)
    text = text.replace("（", "(").replace("）", ")")
    return text


def normalize_unit(unit: str) -> str:
    normalized = normalize_for_key(unit)
    return UNIT_SYNONYMS.get(normalized, normalized)


def normalize_specs_signature(specs: str) -> str:
    text = unicodedata.normalize("NFKC", specs or "").strip()
    if not text:
        return ""

    parts = [part.strip() for part in re.split(r"[;；\n]+", text) if part.strip()]
    normalized_parts: list[tuple[str, str]] = []
    for part in parts:
        if ":" in part:
            key, value = part.split(":", 1)
        elif "：" in part:
            key, value = part.split("：", 1)
        else:
            key, value = "规格", part
        normalized_parts.append((normalize_for_key(key), normalize_spec_value(value)))

    normalized_parts.sort()
    return "|".join(f"{key}:{value}" for key, value in normalized_parts)


def normalize_spec_value(value: str) -> str:
    text = normalize_for_key(value)
    text = text.replace("×", "x").replace("*", "x")

    def replace_dimension(match: re.Match[str]) -> str:
        number = float(match.group("number"))
        unit = match.group("unit").lower()
        if unit in {"cm", "厘米"}:
            number *= 10
        return f"{format_number(number)}mm"

    return re.sub(
        r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>mm|毫米|cm|厘米)",
        replace_dimension,
        text,
        flags=re.IGNORECASE,
    )


def format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.6f}".rstrip("0").rstrip(".")


def is_low_precision(specs: str, statuses: Iterable[str], notes: Iterable[str]) -> bool:
    combined = " ".join([specs or "", *statuses, *notes])
    return not normalize_specs_signature(specs) or any(marker in combined for marker in LOW_PRECISION_MARKERS)


def split_multi(value: str) -> list[str]:
    text = unicodedata.normalize("NFKC", value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*(?:[;；|])\s*", text) if part.strip()]


def parse_int(value: str, default: int = 1) -> int:
    try:
        return int(float((value or "").strip()))
    except ValueError:
        return default


def parse_bool(value: str) -> bool:
    return normalize_for_key(value) in BOOL_TRUE


def sorted_codes(codes: Iterable[str]) -> list[str]:
    def code_key(code: str) -> tuple[str, int, str]:
        match = re.search(r"(\d+)$", code)
        if match:
            return (code[: match.start()], int(match.group(1)), code)
        return (code, -1, code)

    return sorted({code for code in codes if code}, key=code_key)


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


def load_group_mapping(path: Path) -> dict[str, GroupMapping]:
    if not path.exists():
        return {}

    mapping: dict[str, GroupMapping] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            reviewed_group = row.get("reviewed_group_path") or ""
            if not reviewed_group:
                continue
            mapping[reviewed_group] = GroupMapping(
                canonical_group_path=row.get("canonical_group_path") or reviewed_group,
                needs_human_review=parse_bool(row.get("needs_human_review") or ""),
            )
    return mapping


def load_catalog(path: Path, group_mapping: dict[str, GroupMapping]) -> list[CatalogRecord]:
    records: list[CatalogRecord] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for index, row in enumerate(csv.DictReader(handle), start=1):
            item_group = row.get("item_group") or ""
            group = group_mapping.get(item_group, GroupMapping(item_group, False))
            statuses = set(split_multi(row.get("source_statuses") or ""))
            notes = dedupe_keep_order([row.get("notes") or ""])
            specs = row.get("specs") or ""
            aliases = set(split_multi(row.get("alias_names") or ""))
            source_rows = set(split_multi(row.get("source_rows") or ""))
            record = CatalogRecord(
                index=index,
                proposed_item_code=row.get("proposed_item_code") or f"REVIEW-MAT-{index:05d}",
                standard_name=row.get("standard_name") or "",
                item_group=item_group,
                canonical_group_path=group.canonical_group_path,
                specs=specs,
                unit=row.get("unit") or "",
                normalized_name=normalize_for_key(row.get("standard_name") or ""),
                normalized_unit=normalize_unit(row.get("unit") or ""),
                specs_signature=normalize_specs_signature(specs),
                source_count=parse_int(row.get("source_count") or "1"),
                source_statuses=statuses,
                alias_names=aliases,
                source_rows=source_rows,
                notes=notes,
                group_needs_human_review=group.needs_human_review,
            )
            record.low_precision = is_low_precision(record.specs, record.source_statuses, record.notes)
            records.append(record)
    return records


def attach_aliases(records: list[CatalogRecord], aliases_path: Path | None) -> None:
    if not aliases_path or not aliases_path.exists():
        return

    by_code = {record.proposed_item_code: record for record in records}
    with aliases_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = row.get("proposed_item_code") or ""
            raw_name = (row.get("raw_name") or "").strip()
            if code in by_code and raw_name:
                by_code[code].alias_names.add(raw_name)


def merge_records(records: list[CatalogRecord]) -> tuple[list[dict[str, str]], dict[str, str], list[list[CatalogRecord]]]:
    buckets: dict[tuple[str, str, str, str], list[CatalogRecord]] = defaultdict(list)
    for record in records:
        buckets[record.merge_key].append(record)

    merged_rows: list[dict[str, str]] = []
    code_to_merged: dict[str, str] = {}
    clusters: list[list[CatalogRecord]] = []
    for cluster in sorted(buckets.values(), key=cluster_sort_key):
        row = merged_row_from_cluster(cluster)
        merged_rows.append(row)
        clusters.append(cluster)
        for code in row["merged_from_codes"].split("；"):
            if code:
                code_to_merged[code] = row["merged_item_code"]

    return merged_rows, code_to_merged, clusters


def cluster_sort_key(cluster: list[CatalogRecord]) -> tuple[int, str]:
    codes = sorted_codes(record.proposed_item_code for record in cluster)
    first_code = codes[0] if codes else ""
    match = re.search(r"(\d+)$", first_code)
    return (int(match.group(1)) if match else 10**9, first_code)


def merged_row_from_cluster(cluster: list[CatalogRecord]) -> dict[str, str]:
    codes = sorted_codes(record.proposed_item_code for record in cluster)
    merged_item_code = codes[0]
    needs_human_review = any(record.needs_human_review for record in cluster)
    mergeable_status = any(record.status_is_mergeable for record in cluster)
    low_precision = any(record.low_precision for record in cluster)
    human_group = any(record.group_needs_human_review for record in cluster)

    reason_parts = ["single_candidate" if len(codes) == 1 else "exact_name_group_unit_specs"]
    if mergeable_status:
        reason_parts.append("source_status_contains_merge")
    if low_precision:
        reason_parts.append("low_precision")
    if human_group:
        reason_parts.append("human_review_group")

    confidence = "1.00"
    if len(codes) > 1:
        confidence = "0.98"
    if low_precision:
        confidence = "0.70"
    if human_group:
        confidence = "0.65"

    source_statuses = sorted({status for record in cluster for status in record.source_statuses})
    aliases = sorted({alias for record in cluster for alias in record.alias_names})
    source_rows = sorted({source for record in cluster for source in record.source_rows})
    notes = dedupe_keep_order(note for record in cluster for note in record.notes)
    specs_values = dedupe_keep_order(record.specs for record in cluster)
    reviewed_groups = dedupe_keep_order(record.item_group for record in cluster)

    return {
        "merged_item_code": merged_item_code,
        "standard_name": cluster[0].standard_name,
        "reviewed_group_paths": join_values(reviewed_groups),
        "canonical_group_path": cluster[0].canonical_group_path,
        "specs": join_values(specs_values, " || "),
        "unit": cluster[0].normalized_unit or cluster[0].unit,
        "source_count": str(sum(record.source_count for record in cluster)),
        "source_statuses": " | ".join(source_statuses),
        "alias_names": join_values(aliases),
        "source_rows": join_values(source_rows),
        "notes": " || ".join(notes),
        "merged_from_codes": join_values(codes),
        "merge_reason": ";".join(reason_parts),
        "merge_confidence": confidence,
        "needs_human_review": "true" if needs_human_review else "false",
    }


def build_alias_rows(records: list[CatalogRecord], code_to_merged: dict[str, str], merged_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    merged_by_code = {row["merged_item_code"]: row for row in merged_rows}
    alias_map: dict[tuple[str, str], dict[str, set[str] | str]] = {}
    for record in records:
        merged_code = code_to_merged[record.proposed_item_code]
        aliases = set(record.alias_names)
        if not aliases and record.standard_name:
            aliases.add(record.standard_name)
        for alias in aliases:
            if not alias:
                continue
            key = (alias, merged_code)
            item = alias_map.setdefault(
                key,
                {
                    "raw_name": alias,
                    "merged_item_code": merged_code,
                    "source_proposed_item_codes": set(),
                    "alias_sources": set(),
                },
            )
            assert isinstance(item["source_proposed_item_codes"], set)
            assert isinstance(item["alias_sources"], set)
            item["source_proposed_item_codes"].add(record.proposed_item_code)
            item["alias_sources"].add("alias_names" if alias in record.alias_names else "standard_name_fallback")

    rows: list[dict[str, str]] = []
    for _, item in sorted(alias_map.items(), key=lambda pair: (pair[0][1], normalize_for_key(pair[0][0]))):
        merged = merged_by_code[str(item["merged_item_code"])]
        codes = item["source_proposed_item_codes"]
        sources = item["alias_sources"]
        assert isinstance(codes, set)
        assert isinstance(sources, set)
        rows.append(
            {
                "raw_name": str(item["raw_name"]),
                "merged_item_code": str(item["merged_item_code"]),
                "standard_name": merged["standard_name"],
                "canonical_group_path": merged["canonical_group_path"],
                "specs": merged["specs"],
                "unit": merged["unit"],
                "source_proposed_item_codes": join_values(sorted_codes(codes)),
                "alias_source": " | ".join(sorted(sources)),
            }
        )
    return rows


def generate_conflicts(records: list[CatalogRecord], alias_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    conflicts: list[dict[str, str]] = []
    by_review_key: dict[tuple[str, str], list[CatalogRecord]] = defaultdict(list)
    for record in records:
        by_review_key[record.review_key].append(record)

    for (_, canonical_group), bucket in sorted(by_review_key.items(), key=lambda item: (item[0][1], item[0][0])):
        if len(bucket) < 2:
            continue
        standard_name = bucket[0].standard_name
        spec_signatures = {record.specs_signature for record in bucket}
        if len(spec_signatures) > 1:
            conflicts.append(
                conflict_row(
                    "specs_conflict",
                    standard_name,
                    canonical_group,
                    bucket,
                    "同一标准名称和规范分组下存在多个规格签名；已保守拆开，需人工确认是否为不同物料。",
                )
            )

        by_spec: dict[str, list[CatalogRecord]] = defaultdict(list)
        for record in bucket:
            by_spec[record.specs_signature].append(record)
        for spec_bucket in by_spec.values():
            units = {record.normalized_unit for record in spec_bucket}
            if len(units) > 1:
                conflicts.append(
                    conflict_row(
                        "unit_conflict",
                        standard_name,
                        canonical_group,
                        spec_bucket,
                        "同一标准名称、规范分组和规格下存在非同义单位；未自动合并。",
                    )
                )

        has_low_precision = any(record.low_precision for record in bucket)
        has_precise = any(not record.low_precision for record in bucket)
        if has_low_precision and has_precise:
            conflicts.append(
                conflict_row(
                    "low_precision_conflict",
                    standard_name,
                    canonical_group,
                    bucket,
                    "低精度/缺规格项与高精度项同时存在；低精度项已保留 needs_human_review。",
                )
            )

    alias_to_codes: dict[str, set[str]] = defaultdict(set)
    alias_to_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in alias_rows:
        alias_to_codes[row["raw_name"]].add(row["merged_item_code"])
        alias_to_rows[row["raw_name"]].append(row)
    for raw_name, merged_codes in sorted(alias_to_codes.items(), key=lambda item: normalize_for_key(item[0])):
        if len(merged_codes) <= 1:
            continue
        rows = alias_to_rows[raw_name]
        conflicts.append(
            {
                "conflict_type": "alias_conflict",
                "standard_name": raw_name,
                "canonical_group_path": join_values(row["canonical_group_path"] for row in rows),
                "unit_values": join_values(row["unit"] for row in rows),
                "specs_values": join_values((row["specs"] for row in rows), " || "),
                "candidate_codes": join_values(sorted_codes(merged_codes)),
                "source_rows": "",
                "reason": "同一原始别名映射到多个合并后物料；检索时必须让用户确认。",
            }
        )

    return conflicts


def conflict_row(
    conflict_type: str,
    standard_name: str,
    canonical_group: str,
    records: list[CatalogRecord],
    reason: str,
) -> dict[str, str]:
    return {
        "conflict_type": conflict_type,
        "standard_name": standard_name,
        "canonical_group_path": canonical_group,
        "unit_values": join_values(record.unit for record in records),
        "specs_values": join_values(((record.specs or "<blank>") for record in records), " || "),
        "candidate_codes": join_values(sorted_codes(record.proposed_item_code for record in records)),
        "source_rows": join_values(sorted({source for record in records for source in record.source_rows})),
        "reason": reason,
    }


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def merge_files(
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    aliases_path: Path = DEFAULT_ALIASES_PATH,
    mapping_path: Path = DEFAULT_MAPPING_PATH,
    merged_catalog_path: Path = DEFAULT_MERGED_CATALOG_PATH,
    merged_aliases_path: Path = DEFAULT_MERGED_ALIASES_PATH,
    conflicts_path: Path = DEFAULT_CONFLICTS_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
) -> dict[str, object]:
    mapping = load_group_mapping(mapping_path)
    records = load_catalog(catalog_path, mapping)
    attach_aliases(records, aliases_path)

    merged_rows, code_to_merged, _clusters = merge_records(records)
    alias_rows = build_alias_rows(records, code_to_merged, merged_rows)
    conflicts = generate_conflicts(records, alias_rows)

    write_csv(merged_catalog_path, MERGED_CATALOG_FIELDS, merged_rows)
    write_csv(merged_aliases_path, MERGED_ALIAS_FIELDS, alias_rows)
    write_csv(conflicts_path, CONFLICT_FIELDS, conflicts)

    summary = {
        "source_rows": len(records),
        "merged_rows": len(merged_rows),
        "alias_rows": len(alias_rows),
        "conflicts": len(conflicts),
        "auto_merged_clusters": sum(1 for row in merged_rows if "exact_name_group_unit_specs" in row["merge_reason"]),
        "needs_human_review_rows": sum(1 for row in merged_rows if row["needs_human_review"] == "true"),
        "conflict_types": dict(Counter(row["conflict_type"] for row in conflicts)),
        "outputs": {
            "merged_catalog": str(merged_catalog_path),
            "merged_aliases": str(merged_aliases_path),
            "conflicts": str(conflicts_path),
            "summary": str(summary_path),
        },
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def merge_review_catalog(
    catalog_path: Path = DEFAULT_CATALOG_PATH,
    aliases_path: Path | None = DEFAULT_ALIASES_PATH,
    mapping_path: Path = DEFAULT_MAPPING_PATH,
    merged_catalog_path: Path = DEFAULT_MERGED_CATALOG_PATH,
    merged_aliases_path: Path = DEFAULT_MERGED_ALIASES_PATH,
    conflicts_path: Path = DEFAULT_CONFLICTS_PATH,
    summary_path: Path = DEFAULT_SUMMARY_PATH,
) -> dict[str, object]:
    resolved_aliases_path = aliases_path
    if catalog_path != DEFAULT_CATALOG_PATH and aliases_path == DEFAULT_ALIASES_PATH:
        sibling_aliases = catalog_path.parent / "item_aliases_from_review.csv"
        resolved_aliases_path = sibling_aliases if sibling_aliases.exists() else None
    return merge_files(
        catalog_path=catalog_path,
        aliases_path=resolved_aliases_path,
        mapping_path=mapping_path,
        merged_catalog_path=merged_catalog_path,
        merged_aliases_path=merged_aliases_path,
        conflicts_path=conflicts_path,
        summary_path=summary_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge high-confidence reviewed material catalog candidates.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--catalog", type=Path, default=None)
    parser.add_argument("--aliases", type=Path, default=None)
    parser.add_argument("--mapping", type=Path, default=None)
    parser.add_argument("--merged-catalog", type=Path, default=None)
    parser.add_argument("--merged-aliases", type=Path, default=None)
    parser.add_argument("--conflicts", type=Path, default=None)
    parser.add_argument("--summary", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    data_dir = args.data_dir
    summary = merge_files(
        catalog_path=args.catalog or data_dir / "standard_item_catalog_from_review.csv",
        aliases_path=args.aliases or data_dir / "item_aliases_from_review.csv",
        mapping_path=args.mapping or data_dir / "material_group_canonical_mapping.csv",
        merged_catalog_path=args.merged_catalog or data_dir / "merged_standard_item_catalog.csv",
        merged_aliases_path=args.merged_aliases or data_dir / "merged_item_aliases.csv",
        conflicts_path=args.conflicts or data_dir / "merge_conflicts.csv",
        summary_path=args.summary or data_dir / "merge_summary.json",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
