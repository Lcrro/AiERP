from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts" / "material_master"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from build_third_layer_mapping_preview import read_mapping  # noqa: E402


DEFAULT_INPUT_JSON = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_2"
    / "manual_family_mapping"
    / "material_master_manual_family_preview.json"
)
DEFAULT_MAPPING_PATH = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_2"
    / "manual_third_layer_mapping"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "material_master" / "governance_v0_2"
DEFAULT_INPUT_DIR = DEFAULT_OUTPUT_DIR / "third_layer_work_inputs"
DEFAULT_QUEUE_PATH = DEFAULT_OUTPUT_DIR / "third_layer_work_queue.tsv"
DEFAULT_FAMILY_QUEUE_PATH = DEFAULT_OUTPUT_DIR / "third_layer_family_work_queue.tsv"
DEFAULT_PROMPT_PATH = DEFAULT_OUTPUT_DIR / "third_layer_work_prompt.md"


INPUT_FIELDS = [
    "batch_id",
    "top_group",
    "material_family",
    "item_code",
    "item_name",
    "required_specs",
    "optional_specs",
    "stock_uom",
    "aliases",
    "quality_level",
    "governance_note",
]

QUEUE_FIELDS = [
    "batch_id",
    "status",
    "priority",
    "sku_count",
    "family_count",
    "current_name_count",
    "top_groups",
    "material_families",
    "input_file",
    "output_file",
    "notes",
]

FAMILY_QUEUE_FIELDS = [
    "top_group",
    "material_family",
    "sku_count",
    "current_name_count",
    "quality_summary",
    "status",
    "batch_id",
    "input_file",
    "output_file",
]


def slug(value: str) -> str:
    mapping = {
        "管材管件阀门": "pipe",
        "电气电料": "electrical",
        "紧固件与连接件": "fastener",
        "工具量具": "tooling",
        "清洁办公后勤": "admin",
        "液压气动": "hydraulic",
        "化工胶粘涂料": "chemical",
        "定制加工件": "custom",
        "工具耗材": "tool_consumable",
        "吊装索具": "lifting",
        "劳保防护": "safety",
        "建筑材料": "building",
        "金属材料": "metal",
        "设备备件": "spare",
        "焊接切割": "welding",
        "包装覆盖周转": "packaging",
        "安全消防": "fire",
        "施工机具设备": "construction_equipment",
        "电动气动工具": "power_tool",
        "弱电安防": "security",
    }
    if value in mapping:
        return mapping[value]
    ascii_slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return ascii_slug or "material"


def read_rows(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [dict(row) for row in payload["rows"]]


def grouped_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(row["top_group"], row["material_family"])].append(row)
    return groups


def chunk_group(rows: list[dict[str, str]], max_rows: int) -> list[list[dict[str, str]]]:
    return [rows[index : index + max_rows] for index in range(0, len(rows), max_rows)]


def pack_groups(
    groups: dict[tuple[str, str], list[dict[str, str]]],
    target_rows: int,
    max_rows: int,
) -> list[list[dict[str, str]]]:
    large_chunks: list[list[dict[str, str]]] = []
    small_groups: list[list[dict[str, str]]] = []
    for _, rows in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0][0], item[0][1])):
        sorted_rows = sorted(rows, key=lambda row: row["item_code"])
        if len(sorted_rows) > max_rows:
            large_chunks.extend(chunk_group(sorted_rows, max_rows))
        else:
            small_groups.append(sorted_rows)

    batches: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    for rows in small_groups:
        if current and len(current) + len(rows) > max_rows:
            batches.append(current)
            current = []
        current.extend(rows)
        if len(current) >= target_rows:
            batches.append(current)
            current = []
    if current:
        batches.append(current)

    if len(batches) >= 2 and len(batches[-1]) < target_rows and len(batches[-2]) + len(batches[-1]) <= max_rows:
        batches[-2].extend(batches[-1])
        batches.pop()

    return large_chunks + batches


def relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def output_path_for(batch_id: str, batch_rows: list[dict[str, str]]) -> Path:
    top_groups = sorted({row["top_group"] for row in batch_rows})
    prefix = slug(top_groups[0]) if len(top_groups) == 1 else "mixed"
    return DEFAULT_MAPPING_PATH / f"{batch_id}_{prefix}_third_layer_mapping_v0_1.tsv"


def queue_row(batch_id: str, batch_rows: list[dict[str, str]], input_path: Path, output_path: Path) -> dict[str, str]:
    families = sorted({f"{row['top_group']}/{row['material_family']}" for row in batch_rows})
    top_groups = sorted({row["top_group"] for row in batch_rows})
    current_names = {row["item_name"] for row in batch_rows}
    priority = str(len(batch_rows) * max(1, len(current_names)))
    return {
        "batch_id": batch_id,
        "status": "pending",
        "priority": priority,
        "sku_count": str(len(batch_rows)),
        "family_count": str(len(families)),
        "current_name_count": str(len(current_names)),
        "top_groups": "；".join(top_groups),
        "material_families": "；".join(families),
        "input_file": relative(input_path),
        "output_file": relative(output_path),
        "notes": "每包 100-200 行；同一物料族尽量不拆散；输出必须覆盖 input_file 全部 item_code。",
    }


def family_queue_rows(batches: list[tuple[str, list[dict[str, str]], Path, Path]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for batch_id, batch_rows, input_path, output_path in batches:
        for (top_group, family), family_rows in grouped_rows(batch_rows).items():
            quality_counts = Counter(row.get("quality_level", "") for row in family_rows)
            rows.append(
                {
                    "top_group": top_group,
                    "material_family": family,
                    "sku_count": str(len(family_rows)),
                    "current_name_count": str(len({row["item_name"] for row in family_rows})),
                    "quality_summary": "；".join(f"{key}:{value}" for key, value in sorted(quality_counts.items()) if key),
                    "status": "pending",
                    "batch_id": batch_id,
                    "input_file": relative(input_path),
                    "output_file": relative(output_path),
                }
            )
    return sorted(rows, key=lambda row: (row["batch_id"], row["top_group"], row["material_family"]))


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def input_row(batch_id: str, row: dict[str, str]) -> dict[str, str]:
    return {
        "batch_id": batch_id,
        "top_group": row.get("top_group", ""),
        "material_family": row.get("material_family", ""),
        "item_code": row.get("item_code", ""),
        "item_name": row.get("item_name", ""),
        "required_specs": row.get("required_specs", ""),
        "optional_specs": row.get("optional_specs", ""),
        "stock_uom": row.get("stock_uom", ""),
        "aliases": row.get("aliases", ""),
        "quality_level": row.get("quality_level", ""),
        "governance_note": row.get("governance_note", ""),
    }


def write_prompt(path: Path, generated_at: str) -> None:
    path.write_text(
        f"""# 三级物料名称治理批处理提示词

生成日期：{generated_at}

请先阅读：

```text
docs/reference/material-third-layer-governance-v0.1.md
```

你的输入是一个 `third_layer_work_inputs/batch_XXX.tsv` 文件。你只处理该文件中的行，不读取全量物料表，不写 ERPNext，不修改正式主表。

输出 TSV 字段固定为：

```text
item_code
current_item_name
current_required_specs
current_uom
target_top_category
target_second_layer_family
target_third_layer_name
decision
confidence
assumed_specs
manual_judgment
next_action
```

要求：

- 输出行数必须等于输入行数。
- 每个输入 `item_code` 必须且只能输出一次。
- `target_third_layer_name` 只保留核心商品类型/形态/稳定功能。
- 材质、品牌、规格、尺寸、连接方式、表面处理、用途、压力、型号等放进 `assumed_specs` 或保留在规格里。
- 不属于当前物料族时，使用 `decision=移出`，并填写正确的目标二级物料族。
- 信息不足但暂可归类时，使用 `decision=复核`，`confidence=low/medium`，并在 `next_action` 写清楚采购前要确认什么。
""",
        encoding="utf-8",
    )


def clear_old_inputs(input_dir: Path) -> None:
    input_dir.mkdir(parents=True, exist_ok=True)
    for path in input_dir.glob("batch_*.tsv"):
        path.unlink()


def build_work_batches(
    input_json: Path,
    mapping_path: Path,
    input_dir: Path,
    queue_path: Path,
    family_queue_path: Path,
    prompt_path: Path,
    target_rows: int,
    max_rows: int,
    generated_at: str,
) -> dict[str, object]:
    rows = read_rows(input_json)
    mapped_codes = set(read_mapping(mapping_path))
    remaining = [row for row in rows if row["item_code"] not in mapped_codes]
    groups = grouped_rows(remaining)
    batches = pack_groups(groups, target_rows=target_rows, max_rows=max_rows)

    clear_old_inputs(input_dir)
    batch_records: list[tuple[str, list[dict[str, str]], Path, Path]] = []
    queue_rows: list[dict[str, str]] = []
    for index, batch_rows in enumerate(batches, start=1):
        batch_id = f"batch_{index:03d}"
        input_path = input_dir / f"{batch_id}.tsv"
        output_path = output_path_for(batch_id, batch_rows)
        write_tsv(input_path, INPUT_FIELDS, [input_row(batch_id, row) for row in batch_rows])
        batch_records.append((batch_id, batch_rows, input_path, output_path))
        queue_rows.append(queue_row(batch_id, batch_rows, input_path, output_path))

    write_tsv(queue_path, QUEUE_FIELDS, queue_rows)
    write_tsv(family_queue_path, FAMILY_QUEUE_FIELDS, family_queue_rows(batch_records))
    write_prompt(prompt_path, generated_at)

    return {
        "input_json": relative(input_json),
        "existing_mapping_count": len(mapped_codes),
        "total_rows": len(rows),
        "remaining_rows": len(remaining),
        "remaining_families": len(groups),
        "batch_count": len(batches),
        "target_rows": target_rows,
        "max_rows": max_rows,
        "queue_path": relative(queue_path),
        "family_queue_path": relative(family_queue_path),
        "prompt_path": relative(prompt_path),
        "input_dir": relative(input_dir),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build lightweight work batches for third-layer material governance.")
    parser.add_argument("--input-json", type=Path, default=DEFAULT_INPUT_JSON)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--queue", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--family-queue", type=Path, default=DEFAULT_FAMILY_QUEUE_PATH)
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT_PATH)
    parser.add_argument("--target-rows", type=int, default=150)
    parser.add_argument("--max-rows", type=int, default=200)
    parser.add_argument("--generated-at", default=date.today().isoformat())
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_work_batches(
        input_json=args.input_json,
        mapping_path=args.mapping,
        input_dir=args.input_dir,
        queue_path=args.queue,
        family_queue_path=args.family_queue,
        prompt_path=args.prompt,
        target_rows=args.target_rows,
        max_rows=args.max_rows,
        generated_at=args.generated_at,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
