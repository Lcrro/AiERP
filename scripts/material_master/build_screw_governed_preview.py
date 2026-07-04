from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = ROOT / "data/material_master/reclassification/material_master_reclassified.tsv"
GOVERNANCE_PATH = ROOT / "data/material_master/governance_v0_2/screw/screw_governance_candidates.tsv"
OUTPUT_PATH = ROOT / "data/material_master/governance_v0_2/screw/material_master_screw_governed_preview.tsv"

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

TARGET_GROUP_BY_ACTION = {
    "keep_screw": "紧固件与连接件/螺丝",
    "keep_as_kit_review": "紧固件与连接件/螺丝套件",
    "move_to_expansion_anchor": "紧固件与连接件/膨胀锚栓",
    "move_to_nut": "紧固件与连接件/螺母",
    "move_to_screw_rod": "紧固件与连接件/螺杆",
    "move_to_turnbuckle": "吊装索具/花篮螺丝",
    "move_to_washer": "紧固件与连接件/垫圈",
    "move_to_tool": "工具量具/螺丝刀",
}

REVIEW_ACTIONS = {"keep_as_kit_review", "needs_manual_review"}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MASTER_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def append_semicolon(value: str, addition: str) -> str:
    value = (value or "").strip()
    addition = (addition or "").strip()
    if not addition:
        return value
    parts = [part.strip() for part in value.split("；") if part.strip()]
    if addition in parts:
        return value
    parts.append(addition)
    return "；".join(parts)


def append_space_terms(value: str, *terms: str) -> str:
    existing = [part for part in (value or "").split() if part]
    seen = set(existing)
    for term in terms:
        term = (term or "").strip()
        if term and term not in seen:
            existing.append(term)
            seen.add(term)
    return " ".join(existing)


def governance_note(row: dict[str, str], gov: dict[str, str]) -> str:
    reason = gov.get("reason", "").strip()
    action = gov.get("action", "").strip()
    scope = gov.get("scope_type", "").strip()
    confidence = gov.get("confidence", "").strip()
    decision = "需人工确认" if action in REVIEW_ACTIONS or gov.get("needs_owner_decision") == "yes" else "可规则预处理"
    note = f"螺丝治理预览：{decision}；action={action}；scope={scope}；confidence={confidence}"
    if reason:
        note = f"{note}；依据：{reason}"
    return append_semicolon(row.get("governance_note", ""), note)


def apply_governance(row: dict[str, str], gov: dict[str, str]) -> dict[str, str]:
    action = gov.get("action", "")
    if action == "needs_manual_review":
        return {
            **row,
            "source_refs": append_semicolon(row.get("source_refs", ""), "screw_governance_v0.2_preview"),
            "governance_note": governance_note(row, gov),
            "updated_at": "2026-07-03",
        }

    recommended_name = gov.get("recommended_item_name", "").strip()
    required_specs = gov.get("required_specs_normalized", "").strip()
    optional_specs = gov.get("optional_specs_normalized", "").strip()
    target_group = TARGET_GROUP_BY_ACTION.get(action, row.get("item_group", ""))
    original_name = row.get("item_name", "").strip()

    next_quality = row.get("quality_level", "")
    next_policy = row.get("agent_use_policy", "")
    if action in REVIEW_ACTIONS:
        next_quality = "needs_review"
        next_policy = "clarify_specs_before_use"

    return {
        **row,
        "item_name": recommended_name or row.get("item_name", ""),
        "required_specs": required_specs or row.get("required_specs", ""),
        "optional_specs": optional_specs or row.get("optional_specs", ""),
        "item_group": target_group or row.get("item_group", ""),
        "aliases": append_semicolon(row.get("aliases", ""), original_name),
        "search_keywords": append_space_terms(
            row.get("search_keywords", ""),
            recommended_name,
            gov.get("recommended_family", ""),
            original_name,
            gov.get("action", ""),
        ),
        "quality_level": next_quality,
        "agent_use_policy": next_policy,
        "source_refs": append_semicolon(row.get("source_refs", ""), "screw_governance_v0.2_preview"),
        "governance_note": governance_note(row, gov),
        "updated_at": "2026-07-03",
    }


def build_preview() -> list[dict[str, str]]:
    rows = read_tsv(SOURCE_PATH)
    governance_rows = {row["item_code"]: row for row in read_tsv(GOVERNANCE_PATH)}
    preview_rows: list[dict[str, str]] = []
    for row in rows:
        gov = governance_rows.get(row["item_code"])
        preview_rows.append(apply_governance(row, gov) if gov else row)
    return preview_rows


def main() -> None:
    rows = build_preview()
    write_tsv(OUTPUT_PATH, rows)
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
