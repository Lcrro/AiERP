from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_PATH = (
    REPO_ROOT / "data" / "material_master" / "reclassification" / "material_master_browser_data_reclassified.json"
)
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "material_master" / "reclassification" / "material_family_candidate_terms.tsv"
DEFAULT_SUMMARY_PATH = (
    REPO_ROOT / "data" / "material_master" / "reclassification" / "material_family_candidate_terms_summary.json"
)

OUTPUT_FIELDS = [
    "候选词",
    "建议物料族",
    "处理建议",
    "置信度",
    "覆盖SKU数",
    "覆盖标准名称数",
    "当前物料族数",
    "是否跨一级类目",
    "主要分类",
    "当前物料族",
    "样例标准名称",
    "样例SKU",
    "说明",
]

ATTRIBUTE_TERMS = {
    "不锈钢",
    "镀锌",
    "加厚",
    "高压",
    "低压",
    "公元",
    "博世",
    "方大同",
    "世达",
    "铜",
    "铝合金",
    "304",
    "12.9",
    "10.9",
    "8.8",
    "内牙",
    "外牙",
    "焊接",
    "热熔",
    "定制",
}

KNOWN_FAMILY_TERMS = {
    "钻头",
    "开孔器",
    "手套",
    "螺丝",
    "螺母",
    "螺杆",
    "垫片",
    "垫圈",
    "膨胀锚栓",
    "管卡",
    "管材",
    "弯头",
    "三通",
    "直通",
    "接头",
    "法兰",
    "阀门",
    "球阀",
    "止回阀",
    "水龙头",
    "软管",
    "油管",
    "气管",
    "吊带",
    "卸扣",
    "葫芦",
    "钢丝绳",
    "锁扣",
    "门锁",
    "挂锁",
    "合页",
    "插销",
    "扳手",
    "套筒",
    "卷尺",
    "刷",
    "钻尾丝",
    "切割片",
    "砂轮片",
    "自喷漆",
    "防锈漆",
    "密封胶",
    "胶水",
    "黄油嘴",
    "生料带",
    "垃圾袋",
    "油布",
    "篷布",
    "编织袋",
    "水泥",
    "水桶",
    "安全帽",
    "反光背心",
    "口罩",
    "护目镜",
    "电线",
    "电缆",
    "插座",
    "开关",
    "断路器",
    "灯管",
    "灯泡",
    "接线端子",
    "扎带",
    "泵",
    "轴承",
    "皮带",
    "焊条",
    "焊丝",
    "割嘴",
}

STOP_SUBSTRINGS = {
    "材料",
    "工具",
    "耗材",
    "用品",
    "配件",
    "标准",
    "通用",
    "规格",
    "型号",
    "加长",
    "双层",
    "专用",
    "普通",
}


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_tsv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, delimiter="\t")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: str(row.get(field, "")) for field in OUTPUT_FIELDS})


def chinese_substrings(name: str) -> set[str]:
    clean = re.sub(r"[A-Za-z0-9Φφ×*./\\-]+", "", name)
    pieces = re.findall(r"[\u4e00-\u9fff]+", clean)
    terms: set[str] = set()
    for piece in pieces:
        for size in (2, 3, 4):
            for start in range(0, max(0, len(piece) - size + 1)):
                terms.add(piece[start : start + size])
    return terms


def candidate_terms_for_row(row: dict[str, str]) -> set[str]:
    name = row["item_name"]
    terms = {term for term in KNOWN_FAMILY_TERMS if term in name}
    terms.update(chinese_substrings(name))
    family = row.get("material_family", "")
    if family and family != name:
        terms.add(family)

    filtered = {
        term
        for term in terms
        if term
        and term not in ATTRIBUTE_TERMS
        and term not in STOP_SUBSTRINGS
        and not any(attr in term for attr in ATTRIBUTE_TERMS if len(attr) >= 3)
    }
    if "手套" in filtered and not (row.get("item_group") == "劳保防护/手套" and name.endswith("手套")):
        filtered.remove("手套")
    return filtered


def first_values(values: list[str], limit: int = 10) -> str:
    seen: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.append(value)
        if len(seen) >= limit:
            break
    return "；".join(seen)


def decide(term: str, rows: list[dict[str, str]]) -> tuple[str, str, str, str]:
    item_names = {row["item_name"] for row in rows}
    families = {row.get("material_family") or row["item_name"] for row in rows}
    top_groups = {row.get("top_group", "") for row in rows}
    item_groups = {row.get("item_group", "") for row in rows}
    suffix_count = sum(1 for name in item_names if name.endswith(term))

    if term in ATTRIBUTE_TERMS:
        return term, "更像属性，不建议作为物料族", "low", "高频词更像材质/品牌/特征，应进入规格属性。"

    if term in KNOWN_FAMILY_TERMS and len(top_groups) <= 2 and len(families) <= 6:
        return term, "可优先固化为物料族", "high", "覆盖集中，且属于典型实物族名。"

    if term in KNOWN_FAMILY_TERMS and len(top_groups) > 2:
        return term, "可作为候选，但需按用途/系统拆分", "medium", "覆盖多个一级类目，可能同词不同物，需要先拆用途。"

    if len(item_names) >= 6 and suffix_count >= max(3, len(item_names) * 0.45):
        return term, "可人工复核为物料族", "medium", "多个标准名称以该词结尾，形态接近物料族。"

    if len(item_names) >= 8 and len(item_groups) <= 3:
        return term, "可人工复核为物料族", "medium", "覆盖数量较多且分类集中。"

    return term, "暂作为检索/属性候选", "low", "有重复但族边界不够清晰，先不固化。"


def build_candidates(payload: dict[str, object], min_names: int, min_skus: int) -> tuple[list[dict[str, object]], dict[str, object]]:
    all_rows = [dict(row) for row in payload["rows"]]  # type: ignore[index]
    by_term: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    seen_pairs: set[tuple[str, str]] = set()

    for row in all_rows:
        name = row["item_name"]
        for term in candidate_terms_for_row(row):
            key = (term, row["item_code"])
            if key in seen_pairs:
                continue
            by_term[term].append(row)
            seen_pairs.add(key)

    results: list[dict[str, object]] = []
    for term, rows in by_term.items():
        names = sorted({row["item_name"] for row in rows})
        if len(names) < min_names and len(rows) < min_skus:
            continue
        families = sorted({row.get("material_family") or row["item_name"] for row in rows})
        top_groups = sorted({row.get("top_group", "") for row in rows if row.get("top_group")})
        item_groups = [row["item_group"] for row in rows]
        suggested_family, action, confidence, note = decide(term, rows)
        sample_skus = [f"{row['item_code']} {row['item_name']} {row['required_specs']}" for row in rows[:8]]
        results.append(
            {
                "候选词": term,
                "建议物料族": suggested_family,
                "处理建议": action,
                "置信度": confidence,
                "覆盖SKU数": len(rows),
                "覆盖标准名称数": len(names),
                "当前物料族数": len(families),
                "是否跨一级类目": "是" if len(top_groups) > 1 else "否",
                "主要分类": "；".join(f"{name}:{count}" for name, count in Counter(item_groups).most_common(6)),
                "当前物料族": first_values(families, 12),
                "样例标准名称": first_values(names, 12),
                "样例SKU": first_values(sample_skus, 8),
                "说明": note,
            }
        )

    action_rank = {
        "可优先固化为物料族": 0,
        "可人工复核为物料族": 1,
        "可作为候选，但需按用途/系统拆分": 2,
        "暂作为检索/属性候选": 3,
        "更像属性，不建议作为物料族": 4,
    }
    confidence_rank = {"high": 0, "medium": 1, "low": 2}
    results.sort(
        key=lambda row: (
            action_rank.get(str(row["处理建议"]), 9),
            confidence_rank.get(str(row["置信度"]), 9),
            -int(row["覆盖SKU数"]),
            str(row["候选词"]),
        )
    )

    summary = {
        "generated_at": date.today().isoformat(),
        "source": str(DEFAULT_INPUT_PATH),
        "candidate_count": len(results),
        "action_counts": dict(Counter(str(row["处理建议"]) for row in results).most_common()),
        "confidence_counts": dict(Counter(str(row["置信度"]) for row in results).most_common()),
        "top_candidates": [
            {
                "候选词": row["候选词"],
                "处理建议": row["处理建议"],
                "覆盖SKU数": row["覆盖SKU数"],
                "覆盖标准名称数": row["覆盖标准名称数"],
            }
            for row in results[:30]
        ],
    }
    return results, summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build candidate material family terms from repeated item names.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument("--min-names", type=int, default=3)
    parser.add_argument("--min-skus", type=int, default=5)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows, summary = build_candidates(read_json(args.input), args.min_names, args.min_skus)
    write_tsv(args.output, rows)
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
