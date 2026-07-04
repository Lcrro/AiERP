from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_PATH = REPO_ROOT / "data" / "material_master" / "material_master.tsv"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "material_master" / "governance"
DEFAULT_GOVERNANCE_PATH = DEFAULT_OUTPUT_DIR / "glove_governance.tsv"
DEFAULT_SAMPLE_PATH = DEFAULT_OUTPUT_DIR / "glove_material_master_sample.tsv"
DEFAULT_SUMMARY_PATH = DEFAULT_OUTPUT_DIR / "glove_governance_summary.json"

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

GOVERNANCE_FIELDS = [
    "source_item_code",
    "source_item_name",
    "source_required_specs",
    "source_item_group",
    "source_stock_uom",
    "source_aliases",
    "decision",
    "canonical_item_code",
    "canonical_item_name",
    "canonical_required_specs",
    "canonical_item_group",
    "canonical_stock_uom",
    "canonical_aliases",
    "reason",
]

GLOVE_GROUP = "劳保用品/手套"
GLOVE_UOM = "双"

CANONICALS = {
    "SAFE-000096": {
        "item_name": "帆布手套",
        "required_specs": "材质：帆布；结构：普通",
        "aliases": "帆布手套；普通帆布手套",
        "status": "candidate",
        "quality_level": "usable",
        "agent_use_policy": "confirm_before_use",
        "note": "普通帆布手套口径；原始数据缺结构，按常用品候选保留，采购前确认即可。",
    },
    "SAFE-000001": {
        "item_name": "帆布手套",
        "required_specs": "材质：帆布；结构：双层",
        "aliases": "双重帆布手套；双层帆布手套；帆布双层手套",
        "status": "active",
        "quality_level": "standard",
        "agent_use_policy": "auto_select_allowed",
        "note": "双层帆布手套，合并同义表达。",
    },
    "SAFE-000005": {
        "item_name": "帆布手套",
        "required_specs": "材质：帆布；结构：双层；特征：加厚",
        "aliases": "加厚双层帆布手套；帆布加厚双层手套；加厚双层布手套；布加厚双层手套",
        "status": "active",
        "quality_level": "standard",
        "agent_use_policy": "auto_select_allowed",
        "note": "常用加厚双层帆布/布手套，归为同一采购 SKU。",
    },
    "SAFE-000091": {
        "item_name": "布手套",
        "required_specs": "材质：布；特征：加厚",
        "aliases": "加厚布手套",
        "status": "candidate",
        "quality_level": "usable",
        "agent_use_policy": "confirm_before_use",
        "note": "布手套但未说明双层，保留为加厚普通布手套候选。",
    },
    "SAFE-000006": {
        "item_name": "乳胶手套",
        "required_specs": "材质：乳胶；特征：加厚",
        "aliases": "加厚乳胶手套",
        "status": "active",
        "quality_level": "standard",
        "agent_use_policy": "auto_select_allowed",
        "note": "材质明确，保留。",
    },
    "SAFE-000100": {
        "item_name": "牛筋手套",
        "required_specs": "材质/俗称：牛筋；结构：普通",
        "aliases": "牛筋手套",
        "status": "candidate",
        "quality_level": "usable",
        "agent_use_policy": "confirm_before_use",
        "note": "牛筋为现场俗称，普通款保留为候选。",
    },
    "SAFE-000007": {
        "item_name": "牛筋手套",
        "required_specs": "材质/俗称：牛筋；特征：加厚",
        "aliases": "牛筋加厚手套；加厚牛筋手套",
        "status": "active",
        "quality_level": "standard",
        "agent_use_policy": "auto_select_allowed",
        "note": "加厚牛筋手套，和普通牛筋手套区分。",
    },
    "SAFE-000016": {
        "item_name": "挂胶手套",
        "required_specs": "工艺：挂胶；特征：厚",
        "aliases": "厚挂胶手套；挂胶手套",
        "status": "candidate",
        "quality_level": "usable",
        "agent_use_policy": "confirm_before_use",
        "note": "挂胶和浸胶/浸塑不强行合并，先保留。",
    },
    "SAFE-000055": {
        "item_name": "全胶手套",
        "required_specs": "结构：全胶",
        "aliases": "全胶手套",
        "status": "candidate",
        "quality_level": "needs_review",
        "agent_use_policy": "clarify_specs_before_use",
        "note": "全胶材质/厚度不清，保留但采购前需确认。",
    },
    "SAFE-000062": {
        "item_name": "胶手套",
        "required_specs": "类型：胶手套",
        "aliases": "胶手套",
        "status": "candidate",
        "quality_level": "needs_review",
        "agent_use_policy": "clarify_specs_before_use",
        "note": "胶手套过于泛化，不能自动并入乳胶或橡胶。",
    },
    "SAFE-000097": {
        "item_name": "橡胶手套",
        "required_specs": "材质：橡胶",
        "aliases": "橡胶手套",
        "status": "candidate",
        "quality_level": "usable",
        "agent_use_policy": "confirm_before_use",
        "note": "橡胶手套，缺厚度/长度，确认后使用。",
    },
    "SAFE-000113": {
        "item_name": "浸胶手套",
        "required_specs": "工艺：浸胶",
        "aliases": "浸胶手套",
        "status": "candidate",
        "quality_level": "needs_review",
        "agent_use_policy": "clarify_specs_before_use",
        "note": "浸胶手套缺材质/涂层/尺码，保留但需追问。",
    },
    "SAFE-000141": {
        "item_name": "浸塑手套",
        "required_specs": "工艺：浸塑",
        "aliases": "浸塑手套",
        "status": "candidate",
        "quality_level": "needs_review",
        "agent_use_policy": "clarify_specs_before_use",
        "note": "浸塑手套缺材质/防护等级，保留但需追问。",
    },
    "SAFE-000022": {
        "item_name": "焊工手套",
        "required_specs": "用途：电焊防护",
        "aliases": "焊工手套；电焊手套",
        "status": "candidate",
        "quality_level": "usable",
        "agent_use_policy": "confirm_before_use",
        "note": "普通焊工/电焊手套，缺材质长度，确认后使用。",
    },
    "SAFE-000054": {
        "item_name": "焊工手套",
        "required_specs": "用途：焊工防护；特征：加长",
        "aliases": "加长焊工手套；加长电焊手套",
        "status": "candidate",
        "quality_level": "usable",
        "agent_use_policy": "confirm_before_use",
        "note": "加长焊工手套，与普通焊工手套区分。",
    },
    "SAFE-000059": {
        "item_name": "焊工手套",
        "required_specs": "用途：电焊防护；结构：双层；特征：加厚",
        "aliases": "双层电焊手套；加厚电焊手套；双层加厚电焊手套",
        "status": "candidate",
        "quality_level": "usable",
        "agent_use_policy": "confirm_before_use",
        "note": "双层加厚电焊手套，与普通和加长焊工手套区分。",
    },
}

DECISIONS = {
    "SAFE-000001": ("keep_update", "SAFE-000001", "作为双层帆布手套标准 SKU 保留。"),
    "SAFE-000005": ("keep_update", "SAFE-000005", "作为加厚双层帆布手套标准 SKU 保留。"),
    "SAFE-000006": ("keep_update", "SAFE-000006", "材质明确，保留。"),
    "SAFE-000007": ("keep_update", "SAFE-000007", "作为加厚牛筋手套保留。"),
    "SAFE-000016": ("keep_update", "SAFE-000016", "挂胶工艺明确，保留候选。"),
    "SAFE-000020": ("merge_to", "SAFE-000005", "加厚双层布手套按常用口径并入加厚双层帆布手套。"),
    "SAFE-000022": ("keep_update", "SAFE-000022", "普通焊工/电焊防护手套保留候选。"),
    "SAFE-000054": ("keep_update", "SAFE-000054", "加长焊工手套与普通焊工手套区分。"),
    "SAFE-000055": ("keep_update", "SAFE-000055", "全胶手套过于泛化但可保留待复核。"),
    "SAFE-000059": ("keep_update", "SAFE-000059", "双层加厚电焊手套单独保留。"),
    "SAFE-000062": ("keep_update", "SAFE-000062", "胶手套含义泛化，保留但需追问。"),
    "SAFE-000066": ("merge_to", "SAFE-000001", "双层帆布手套同义表达，合并。"),
    "SAFE-000070": ("merge_to", "SAFE-000005", "加厚双层帆布手套重复，合并。"),
    "SAFE-000085": ("merge_to", "SAFE-000005", "布加厚双层手套按常用口径并入加厚双层帆布手套。"),
    "SAFE-000091": ("keep_update", "SAFE-000091", "加厚布手套未说明双层，暂不并入加厚双层帆布手套。"),
    "SAFE-000096": ("keep_update", "SAFE-000096", "普通帆布手套保留为候选。"),
    "SAFE-000097": ("keep_update", "SAFE-000097", "橡胶手套保留为候选。"),
    "SAFE-000100": ("keep_update", "SAFE-000100", "普通牛筋手套保留，和加厚牛筋手套区分。"),
    "SAFE-000108": ("merge_to", "SAFE-000022", "焊工防护手套并入普通焊工手套。"),
    "SAFE-000113": ("keep_update", "SAFE-000113", "浸胶工艺明确，保留但需追问材质/涂层。"),
    "SAFE-000133": ("merge_to", "SAFE-000096", "普通帆布手套重复，合并。"),
    "SAFE-000141": ("keep_update", "SAFE-000141", "浸塑工艺明确，保留但需追问。"),
    "SAFE-000142": ("merge_to", "SAFE-000097", "橡胶手套重复，合并。"),
}


def read_master(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != MASTER_FIELDS:
            raise ValueError(f"{path}: unexpected fields {reader.fieldnames}")
        return list(reader)


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_source_glove(row: dict[str, str]) -> bool:
    return row["item_code"].startswith("SAFE-") and (
        "手套" in row["item_name"] or "手套" in row["item_group"] or "手套" in row["aliases"]
    )


def search_keywords(row: dict[str, str]) -> str:
    parts = [
        row["item_code"],
        row["item_name"],
        row["required_specs"],
        row["item_group"],
        row["stock_uom"],
        row["aliases"],
    ]
    return " ".join(part for part in parts if part)


def canonical_row(item_code: str, source_rows: list[dict[str, str]], updated_at: str) -> dict[str, str]:
    spec = CANONICALS[item_code]
    merged_codes = [row["item_code"] for row in source_rows if DECISIONS[row["item_code"]][1] == item_code]
    aliases = spec["aliases"]
    note = f"{spec['note']}；来源物料：{';'.join(merged_codes)}"
    row = {
        "item_code": item_code,
        "item_name": spec["item_name"],
        "required_specs": spec["required_specs"],
        "optional_specs": "",
        "item_group": GLOVE_GROUP,
        "stock_uom": GLOVE_UOM,
        "purchase_uom": "",
        "conversion_factor": "",
        "aliases": aliases,
        "search_keywords": "",
        "brand": "",
        "model": "",
        "status": spec["status"],
        "quality_level": spec["quality_level"],
        "agent_use_policy": spec["agent_use_policy"],
        "source_refs": "merged_source_item_codes=" + ";".join(merged_codes),
        "governance_note": note,
        "updated_at": updated_at,
    }
    row["search_keywords"] = search_keywords(row)
    return row


def governance_row(source: dict[str, str]) -> dict[str, str]:
    decision, canonical_code, reason = DECISIONS[source["item_code"]]
    canonical = CANONICALS[canonical_code]
    return {
        "source_item_code": source["item_code"],
        "source_item_name": source["item_name"],
        "source_required_specs": source["required_specs"],
        "source_item_group": source["item_group"],
        "source_stock_uom": source["stock_uom"],
        "source_aliases": source["aliases"],
        "decision": decision,
        "canonical_item_code": canonical_code,
        "canonical_item_name": canonical["item_name"],
        "canonical_required_specs": canonical["required_specs"],
        "canonical_item_group": GLOVE_GROUP,
        "canonical_stock_uom": GLOVE_UOM,
        "canonical_aliases": canonical["aliases"],
        "reason": reason,
    }


def build_glove_governance(input_path: Path, governance_path: Path, sample_path: Path, summary_path: Path, updated_at: str) -> dict[str, object]:
    master_rows = read_master(input_path)
    source_rows = [row for row in master_rows if is_source_glove(row)]
    source_codes = {row["item_code"] for row in source_rows}
    missing = sorted(set(DECISIONS) - source_codes)
    extra = sorted(source_codes - set(DECISIONS))
    if missing or extra:
        raise ValueError(f"Glove decision coverage mismatch: missing={missing}, extra={extra}")

    governance_rows = [governance_row(row) for row in source_rows]
    canonical_codes = sorted({decision[1] for decision in DECISIONS.values()})
    sample_rows = [canonical_row(code, source_rows, updated_at) for code in canonical_codes]

    write_tsv(governance_path, GOVERNANCE_FIELDS, governance_rows)
    write_tsv(sample_path, MASTER_FIELDS, sample_rows)

    summary = {
        "input": str(input_path),
        "governance_output": str(governance_path),
        "sample_output": str(sample_path),
        "source_glove_rows": len(source_rows),
        "canonical_glove_rows": len(sample_rows),
        "merged_rows": sum(1 for row in governance_rows if row["decision"] == "merge_to"),
        "kept_or_updated_rows": sum(1 for row in governance_rows if row["decision"] == "keep_update"),
        "decision_counts": dict(Counter(row["decision"] for row in governance_rows)),
        "quality_level_counts": dict(Counter(row["quality_level"] for row in sample_rows)),
        "agent_use_policy_counts": dict(Counter(row["agent_use_policy"] for row in sample_rows)),
        "canonical_codes": canonical_codes,
    }
    write_json(summary_path, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a glove-category governance sample from material_master.tsv.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--governance-output", type=Path, default=DEFAULT_GOVERNANCE_PATH)
    parser.add_argument("--sample-output", type=Path, default=DEFAULT_SAMPLE_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--updated-at", default=date.today().isoformat())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = build_glove_governance(
        input_path=args.input,
        governance_path=args.governance_output,
        sample_path=args.sample_output,
        summary_path=args.summary,
        updated_at=args.updated_at,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
