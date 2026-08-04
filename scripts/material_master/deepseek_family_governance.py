from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from nexterp_agent.agent_runtime.deepseek_material_request import (  # noqa: E402
    call_deepseek_json,
    load_deepseek_settings,
)


DEFAULT_INPUT = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "release_v1_0"
    / "material_master_release_v1_0.tsv"
)
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "material_master" / "governance_v0_4"

MODEL_FIELDS = [
    "item_code",
    "proposed_item_name",
    "proposed_sku_name",
    "proposed_required_specs",
    "proposed_optional_specs",
    "proposed_stock_uom",
    "proposed_aliases",
    "proposed_brand",
    "proposed_model",
    "duplicate_with_item_code",
    "change_reason",
]

REVIEW_SEVERITIES = {"high", "medium", "low"}
REVIEW_FIELDS = ["item_code", "severity", "issue_type", "issue", "suggestion"]

COMPARISON_FIELDS = [
    "item_code",
    "original_item_name",
    "proposed_item_name",
    "original_sku_name",
    "proposed_sku_name",
    "original_required_specs",
    "proposed_required_specs",
    "original_optional_specs",
    "proposed_optional_specs",
    "original_stock_uom",
    "proposed_stock_uom",
    "original_aliases",
    "proposed_aliases",
    "original_brand",
    "proposed_brand",
    "original_model",
    "proposed_model",
    "duplicate_with_item_code",
    "change_reason",
]

FAMILY_GUIDES = {
    "钻头": {
        "goal": "把笼统的钻头名称拆成采购员能理解的稳定商品类型，尺寸和品牌留在 SKU 层。",
        "preferred_item_names": [
            "高速钢麻花钻头",
            "不锈钢用高速钢麻花钻头",
            "硬质合金钻头",
            "混凝土冲击钻头",
            "SDS-Plus四坑冲击钻头",
            "SDS-Max五坑冲击钻头",
            "方柄冲击钻头",
            "铣刀钻头",
        ],
        "normalization_notes": [
            "二坑二槽通常是 SDS-Plus 四坑接口，五坑或五坑三槽通常是 SDS-Max 五坑接口。",
            "只有历史信息足以支持时才归入具体接口；仅写冲击钻头时不得凭空补四坑或五坑。",
            "高速钢且没有冲击结构信息的普通钻头，通常可整理为高速钢麻花钻头。",
            "本历史清单中的合金钻头和钨钢钻头按常用品口径统一为硬质合金钻头，原称保留为别名。",
            "不锈钢钻头描述的是用途，不应误写成钻头本体材质为不锈钢。",
            "方柄只表示柄型；原始资料未写冲击时，名称不得增加冲击用途。",
            "品牌放 brand；除非品牌决定设备兼容性，否则不进入三级名称或 SKU 名称。",
            "关键规格优先使用用途、接口/柄型、直径、总长、材质；没有证据的工作长度不要编造。",
            "库存单位统一为支。",
        ],
    }
}


def call_deepseek_json_with_retry(
    messages: list[dict[str, str]],
    *,
    settings: Any,
    attempts: int = 2,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            return call_deepseek_json(messages, settings=settings)
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                raise
            time.sleep(1)
    raise RuntimeError("DeepSeek call failed") from last_error


def read_tsv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader.fieldnames or []), [
            {key: (value or "").strip() for key, value in row.items()}
            for row in reader
        ]


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
            delimiter="\t",
            lineterminator="\n",
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def compact_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "item_code": row.get("item_code", ""),
        "item_name": row.get("item_name", ""),
        "sku_name": row.get("sku_name", ""),
        "required_specs": row.get("required_specs", ""),
        "optional_specs": row.get("optional_specs", ""),
        "stock_uom": row.get("stock_uom", ""),
        "aliases": row.get("aliases", ""),
        "brand": row.get("brand", ""),
        "model": row.get("model", ""),
    }


def select_family_rows(
    rows: list[dict[str, str]],
    *,
    top_group: str,
    material_family: str,
) -> list[dict[str, str]]:
    selected = [
        row
        for row in rows
        if row.get("top_group") == top_group
        and row.get("material_family") == material_family
    ]
    return sorted(selected, key=lambda row: row.get("item_code", ""))


def chunked(rows: list[dict[str, str]], size: int) -> list[list[dict[str, str]]]:
    if size <= 0:
        raise ValueError("chunk size must be positive")
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def build_family_guide_messages(
    *,
    top_group: str,
    material_family: str,
    family_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是土木工程企业的资深物料主数据架构师。"
                "请先为一个完整物料族制定可执行的治理说明书，不要改写具体SKU。"
                "说明书要区分稳定商品类型和SKU属性，并明确哪些行业默认允许补齐、"
                "哪些信息不得推断。只输出JSON object。"
            ),
        },
        {
            "role": "system",
            "content": json.dumps(
                {
                    "scope": {
                        "top_group": top_group,
                        "material_family": material_family,
                        "row_count": len(family_rows),
                    },
                    "requirements": [
                        "preferred_item_names只放稳定商品类型，不含尺寸、品牌、型号和包装数量。",
                        "normalization_notes说明允许采用的行业归一化口径。",
                        "prohibited_inferences说明没有原始证据时绝对不能补什么。",
                        "required_specs_by_item_name只列影响采购选择的最小字段。",
                        "同一说明书必须能覆盖输入中的全部SKU，不得逐条建立商品类型。",
                    ],
                    "output_schema": {
                        "material_family": material_family,
                        "goal": "本族治理目标",
                        "preferred_item_names": ["稳定三级物料名称"],
                        "normalization_notes": ["批准的归一化口径"],
                        "prohibited_inferences": ["禁止无依据推断的内容"],
                        "required_specs_by_item_name": [
                            {"item_name": "三级物料名称", "required_fields": ["规格字段"]}
                        ],
                        "uom_policy": "库存单位口径",
                    },
                    "family_rows": [compact_row(row) for row in family_rows],
                },
                ensure_ascii=False,
            ),
        },
    ]


def normalize_family_guide(result: dict[str, Any], material_family: str) -> dict[str, Any]:
    goal = str(result.get("goal") or "").strip()
    raw_names = result.get("preferred_item_names") or []
    raw_notes = result.get("normalization_notes") or []
    raw_prohibited = result.get("prohibited_inferences") or []
    if not goal or not isinstance(raw_names, list) or not raw_names:
        raise ValueError("DeepSeek family guide requires goal and preferred_item_names")
    names = list(dict.fromkeys(str(value).strip() for value in raw_names if str(value).strip()))
    invalid_names = [
        name
        for name in names
        if re.search(
            r"(?:DN|Φ)\s*\d|\d+(?:\.\d+)?\s*(?:mm|cm|m|寸|分|×|\*)",
            name,
            re.I,
        )
    ]
    if invalid_names:
        raise ValueError(f"family guide item names contain SKU dimensions: {invalid_names}")
    specs = result.get("required_specs_by_item_name") or []
    if not isinstance(specs, list):
        raise ValueError("required_specs_by_item_name must be an array")
    return {
        "material_family": material_family,
        "goal": goal,
        "preferred_item_names": names,
        "normalization_notes": [
            str(value).strip() for value in raw_notes if str(value).strip()
        ],
        "prohibited_inferences": [
            str(value).strip() for value in raw_prohibited if str(value).strip()
        ],
        "required_specs_by_item_name": specs,
        "uom_policy": str(result.get("uom_policy") or "").strip(),
    }


def generate_family_guide(
    *,
    top_group: str,
    material_family: str,
    family_rows: list[dict[str, str]],
    output_dir: Path,
    reuse_guide: bool,
) -> dict[str, Any]:
    guide_path = output_dir / "family_guide.json"
    if reuse_guide and guide_path.exists():
        return normalize_family_guide(
            json.loads(guide_path.read_text(encoding="utf-8")),
            material_family,
        )
    messages = build_family_guide_messages(
        top_group=top_group,
        material_family=material_family,
        family_rows=family_rows,
    )
    request_path = output_dir / "requests" / "family_guide.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps({"messages": messages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    settings = replace(load_deepseek_settings(), timeout_seconds=180)
    guide = normalize_family_guide(
        call_deepseek_json_with_retry(messages, settings=settings),
        material_family,
    )
    guide.update(
        {
            "top_group": top_group,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "model": settings.model,
            "authoritative": False,
        }
    )
    guide_path.write_text(
        json.dumps(guide, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return guide


def build_messages(
    *,
    top_group: str,
    material_family: str,
    all_family_rows: list[dict[str, str]],
    target_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    family_guide = FAMILY_GUIDES.get(
        material_family,
        {
            "goal": "统一三级物料名称、SKU 名称、最小采购规格、单位和别名。",
            "preferred_item_names": [],
            "normalization_notes": [],
        },
    )
    output_schema = {
        "rows": [
            {
                "item_code": "必须原样返回的编码",
                "proposed_item_name": "稳定的三级商品类型，不含尺寸、品牌或型号",
                "proposed_sku_name": "三级物料名称 + 最关键规格",
                "proposed_required_specs": "字段：值；字段：值",
                "proposed_optional_specs": "辅助信息，没有则空字符串",
                "proposed_stock_uom": "一个标准库存单位",
                "proposed_aliases": "中文分号分隔，没有则空字符串",
                "proposed_brand": "品牌，没有则空字符串",
                "proposed_model": "型号，没有则空字符串",
                "duplicate_with_item_code": "疑似相同 SKU 的另一个编码，没有则空字符串",
                "change_reason": "一句话说明整理依据",
            }
        ],
        "family_observations": ["整族层面的简短发现"],
    }
    system = {
        "role": "system",
        "content": (
            "你是土木工程企业的物料主数据治理员。"
            "你会看到同一物料族的完整清单，并只整理本批指定编码。"
            "必须横向比较整族数据，建立稳定的三级物料名称；不得逐行孤立改写。"
            "一级类目、二级物料族、item_code 和价格由程序管理，你不得输出或修改。"
            "三级物料名称表示稳定商品类型，不能包含尺寸、长度、品牌、型号和包装数量。"
            "SKU 名称使用‘三级物料名称 + 最关键规格’，采购员应能一眼区分。"
            "规格只保留会影响买对或买错的字段；字段名和单位必须统一。"
            "可以根据行业常识修正明显误写，但不得凭空制造接口、性能等级或兼容型号。"
            "疑似重复只给出 duplicate_with_item_code，不删除、不合并行。"
            "每个目标 item_code 必须且只能输出一次。只输出 JSON object。"
        ),
    }
    developer = {
        "role": "system",
        "content": json.dumps(
            {
                "scope": {
                    "top_group": top_group,
                    "material_family": material_family,
                    "family_row_count": len(all_family_rows),
                    "target_row_count": len(target_rows),
                },
                "family_guide": family_guide,
                "hard_requirements": [
                    "输出 rows 数量必须等于 target_row_count。",
                    "输出编码集合必须与 target_item_codes 完全相同。",
                    "proposed_item_name、proposed_sku_name、proposed_required_specs、proposed_stock_uom 不能为空。",
                    "规格分隔符统一使用中文分号；尺寸乘号在名称中统一使用 ×。",
                    "直径写作 mm，长度写作 mm；不要在数值前重复 Φ 符号和‘直径’两个表达。",
                    "原始别名中有价值的土名和旧写法应保留，使用中文分号去重。",
                    "品牌与型号只能来自原始资料，不得猜测。",
                ],
                "output_schema": output_schema,
                "target_item_codes": [row["item_code"] for row in target_rows],
                "all_family_rows_for_comparison": [compact_row(row) for row in all_family_rows],
                "target_rows_to_output": [compact_row(row) for row in target_rows],
            },
            ensure_ascii=False,
        ),
    }
    return [system, developer]


def normalize_model_row(row: dict[str, Any]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for field in MODEL_FIELDS:
        value = row.get(field, "")
        if isinstance(value, list):
            value = "；".join(str(item).strip() for item in value if str(item).strip())
        normalized[field] = str(value or "").strip()
    normalized["proposed_sku_name"] = normalized["proposed_sku_name"].replace("*", "×")
    return normalized


def append_spec(specs: str, value: str) -> str:
    values = [item.strip() for item in specs.split("；") if item.strip()]
    if value not in values:
        values.append(value)
    return "；".join(values)


def normalize_family_output(
    row: dict[str, str],
    material_family: str,
    source: dict[str, str] | None = None,
) -> dict[str, str]:
    normalized = dict(row)
    source = source or {}
    if material_family == "胶管总成":
        source_spec_match = re.search(
            r"规格\s*[:：]\s*([^；]+)",
            source.get("required_specs", ""),
        )
        if source_spec_match:
            source_spec = source_spec_match.group(1).strip()
            normalized["proposed_required_specs"] = re.sub(
                r"规格\s*[:：]\s*[^；]+",
                f"规格：{source_spec}",
                normalized["proposed_required_specs"],
                count=1,
            )
            specs = normalized["proposed_required_specs"]
            layer = re.search(r"层数\s*[:：]\s*([^；]+)", specs)
            length = re.search(r"长度\s*[:：]\s*([^；]+)", specs)
            sku_parts = [normalized["proposed_item_name"], source_spec]
            if layer:
                sku_parts.append(layer.group(1).strip())
            if length:
                sku_parts.append(length.group(1).strip())
            normalized["proposed_sku_name"] = " ".join(
                part for part in sku_parts if part
            )
            normalized["change_reason"] = (
                "保留原始通径或螺纹标识，仅将长度、层数和接头形式结构化。"
            )
        normalized["proposed_stock_uom"] = "根"
        return normalized
    if material_family == "弯头":
        aliases = source.get("aliases", "")
        inner_thread = re.search(
            r"(\d+(?:\.\d+)?)\s*[*×]\s*(\d+(?:\.\d+)?)\s*(?:内牙|内丝)",
            aliases,
            re.I,
        )
        if inner_thread and "内丝" in source.get("required_specs", ""):
            pipe_size, thread_size = inner_thread.groups()
            normalized["proposed_required_specs"] = append_spec(
                normalized["proposed_required_specs"],
                f"内丝端口径：{thread_size}分",
            )
            material = re.search(
                r"材质\s*[:：]\s*([^；]+)",
                normalized["proposed_required_specs"],
            )
            material_prefix = material.group(1) if material else ""
            normalized["proposed_sku_name"] = (
                f"{material_prefix}{normalized['proposed_item_name']} "
                f"{pipe_size}mm×{thread_size}分"
            ).strip()
            normalized["change_reason"] = (
                "从原始别名保留管端口径和内丝端口径，避免不同接口规格混淆。"
            )
        return normalized
    if material_family != "钻头":
        return normalized
    specs = normalized["proposed_required_specs"]
    specs = re.sub(r"规格/直径\s*[:：]", "直径：", specs)
    specs = re.sub(r"(?<!总)长度\s*[:：]", "总长：", specs)
    specs = re.sub(r"柄型：(SDS-(?:Plus|Max)[^；]*)", r"接口：\1", specs)
    normalized["proposed_required_specs"] = specs
    normalized["proposed_stock_uom"] = "支"
    source_sku_name = source.get("sku_name", "")
    source_required_specs = source.get("required_specs", "")
    source_item_name = source.get("item_name", "")
    if "短型" in source_sku_name:
        normalized["proposed_optional_specs"] = append_spec(
            normalized["proposed_optional_specs"],
            "类型：短型",
        )
    if (
        normalized["proposed_item_name"] == "混凝土冲击钻头"
        and "冲击钻头" in f"{source_item_name} {source_sku_name}"
        and "混凝土" not in f"{source_item_name} {source_sku_name} {source_required_specs}"
    ):
        normalized["proposed_item_name"] = "冲击钻头"
        normalized["change_reason"] = (
            "原始资料只确认冲击结构，不推断混凝土用途；保留为通用冲击钻头。"
        )
    if "五坑三槽" in f"{source_item_name} {source_sku_name} {source_required_specs}":
        normalized["proposed_optional_specs"] = append_spec(
            normalized["proposed_optional_specs"],
            "接口特征：五坑三槽",
        )
    if (
        normalized["proposed_item_name"] == "方柄冲击钻头"
        and "冲击" not in f"{source_item_name} {source_sku_name} {source_required_specs}"
    ):
        normalized["proposed_item_name"] = "方柄钻头"
        normalized["change_reason"] = "原始资料只确认方柄柄型，不额外推断冲击用途。"
    if source_item_name == "钻头" and "用途：不锈钢" in source_required_specs:
        normalized["proposed_item_name"] = "不锈钢用钻头"
        normalized["proposed_required_specs"] = re.sub(
            r"(?<!总)长度\s*[:：]",
            "总长：",
            source_required_specs,
        )
        normalized["change_reason"] = (
            "原始资料只确认不锈钢用途，不推断高速钢材质或麻花结构；保留直径和总长。"
        )
    elif source_item_name == "铣刀钻头" and "不锈钢" in source_sku_name:
        normalized["proposed_item_name"] = "不锈钢用铣刀钻头"
        normalized["proposed_required_specs"] = re.sub(
            r"^材质\s*[:：]\s*不锈钢",
            "用途：不锈钢",
            source_required_specs,
        )
        normalized["proposed_required_specs"] = re.sub(
            r"(?<!总)长度\s*[:：]",
            "总长：",
            normalized["proposed_required_specs"],
        )
        normalized["change_reason"] = (
            "原SKU中的不锈钢作为加工用途保留在商品名称和规格中，不误写成钻头本体材质。"
        )
    specs = normalized["proposed_required_specs"]
    diameter = re.search(r"直径\s*[:：]\s*Φ?\s*(\d+(?:\.\d+)?)\s*mm", specs, re.I)
    length = re.search(r"总长\s*[:：]\s*(\d+(?:\.\d+)?)\s*mm", specs, re.I)
    if diameter and length:
        normalized["proposed_sku_name"] = (
            f"{normalized['proposed_item_name']} Φ{diameter.group(1)}×{length.group(1)}mm"
        )
    return normalized


def validate_chunk_result(
    result: dict[str, Any],
    expected_codes: list[str],
) -> tuple[list[dict[str, str]], list[str]]:
    raw_rows = result.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError("DeepSeek result.rows must be an array")
    rows = [normalize_model_row(row) for row in raw_rows if isinstance(row, dict)]
    actual_codes = [row["item_code"] for row in rows]
    missing = sorted(set(expected_codes) - set(actual_codes))
    extra = sorted(set(actual_codes) - set(expected_codes))
    duplicates = sorted({code for code in actual_codes if actual_codes.count(code) > 1})
    if missing or extra or duplicates or len(rows) != len(expected_codes):
        raise ValueError(
            f"item_code coverage mismatch: missing={missing}, extra={extra}, "
            f"duplicates={duplicates}, expected={len(expected_codes)}, actual={len(rows)}"
        )
    required_fields = (
        "proposed_item_name",
        "proposed_sku_name",
        "proposed_required_specs",
        "proposed_stock_uom",
        "change_reason",
    )
    empty = [
        f"{row['item_code']}:{field}"
        for row in rows
        for field in required_fields
        if not row[field]
    ]
    if empty:
        raise ValueError(f"required output fields are empty: {empty}")
    observations = result.get("family_observations") or []
    if not isinstance(observations, list):
        observations = [str(observations)]
    return rows, [str(item).strip() for item in observations if str(item).strip()]


def build_comparison_rows(
    source_rows: list[dict[str, str]],
    proposed_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    source_by_code = {row["item_code"]: row for row in source_rows}
    comparison: list[dict[str, str]] = []
    for proposed in sorted(proposed_rows, key=lambda row: row["item_code"]):
        source = source_by_code[proposed["item_code"]]
        comparison.append(
            {
                "item_code": proposed["item_code"],
                "original_item_name": source.get("item_name", ""),
                "proposed_item_name": proposed["proposed_item_name"],
                "original_sku_name": source.get("sku_name", ""),
                "proposed_sku_name": proposed["proposed_sku_name"],
                "original_required_specs": source.get("required_specs", ""),
                "proposed_required_specs": proposed["proposed_required_specs"],
                "original_optional_specs": source.get("optional_specs", ""),
                "proposed_optional_specs": proposed["proposed_optional_specs"],
                "original_stock_uom": source.get("stock_uom", ""),
                "proposed_stock_uom": proposed["proposed_stock_uom"],
                "original_aliases": source.get("aliases", ""),
                "proposed_aliases": proposed["proposed_aliases"],
                "original_brand": source.get("brand", ""),
                "proposed_brand": proposed["proposed_brand"],
                "original_model": source.get("model", ""),
                "proposed_model": proposed["proposed_model"],
                "duplicate_with_item_code": proposed["duplicate_with_item_code"],
                "change_reason": proposed["change_reason"],
            }
        )
    return comparison


def build_review_messages(
    *,
    top_group: str,
    material_family: str,
    comparison_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    family_guide = FAMILY_GUIDES.get(material_family, {})
    review_rows = [
        {
            "item_code": row["item_code"],
            "original_item_name": row["original_item_name"],
            "original_sku_name": row["original_sku_name"],
            "original_required_specs": row["original_required_specs"],
            "original_optional_specs": row["original_optional_specs"],
            "original_aliases": row["original_aliases"],
            "original_brand": row["original_brand"],
            "original_model": row["original_model"],
            "proposed_item_name": row["proposed_item_name"],
            "proposed_sku_name": row["proposed_sku_name"],
            "proposed_required_specs": row["proposed_required_specs"],
            "proposed_optional_specs": row["proposed_optional_specs"],
            "proposed_stock_uom": row["proposed_stock_uom"],
            "proposed_aliases": row["proposed_aliases"],
            "proposed_brand": row["proposed_brand"],
            "proposed_model": row["proposed_model"],
            "duplicate_with_item_code": row["duplicate_with_item_code"],
            "change_reason": row.get("change_reason", ""),
        }
        for row in comparison_rows
    ]
    return [
        {
            "role": "system",
            "content": (
                "你是独立的物料主数据质量审查员，不参与本批数据生成。"
                "只报告有实际依据的问题，不要为了凑数制造问题。"
                "重点检查：三级名称是否混入尺寸或品牌、原始信息是否丢失、"
                "是否无依据补充材质/接口/用途、规格字段是否自相矛盾、"
                "同一采购对象是否形成重复SKU。"
                "不要直接重写整张表，只输出JSON object。"
            ),
        },
        {
            "role": "system",
            "content": json.dumps(
                {
                    "scope": {
                        "top_group": top_group,
                        "material_family": material_family,
                        "row_count": len(comparison_rows),
                    },
                    "severity_definition": {
                        "high": "可能导致采购错误、错误合并或信息失真",
                        "medium": "分类或规格表达需要人工复核",
                        "low": "主要是命名、格式或可读性改进",
                    },
                    "approved_family_policy": family_guide,
                    "review_policy": [
                        "本项目在编制初始化标准物料表，允许依据 approved_family_policy 补齐常用品类。",
                        "已被 approved_family_policy 明确授权、且不与原始资料冲突的归一化，不应判为 unsupported_inference。",
                        "只报告违反已批准口径、丢失原始采购信息、自相矛盾或造成错误合并的问题。",
                    ],
                    "output_schema": {
                        "verdict": "pass或needs_revision",
                        "issues": [
                            {
                                "item_code": "必须来自输入",
                                "severity": "high|medium|low",
                                "issue_type": "classification|unsupported_inference|information_loss|spec_conflict|duplicate|naming|uom",
                                "issue": "明确说明问题",
                                "suggestion": "建议如何复核或修正",
                            }
                        ],
                        "family_summary": "不超过三句话的总体评价",
                    },
                    "rows": review_rows,
                },
                ensure_ascii=False,
            ),
        },
    ]


def normalize_review_result(
    result: dict[str, Any],
    valid_codes: set[str],
) -> dict[str, Any]:
    raw_issues = result.get("issues") or []
    if not isinstance(raw_issues, list):
        raise ValueError("DeepSeek review issues must be an array")
    issues: list[dict[str, str]] = []
    for raw_issue in raw_issues:
        if not isinstance(raw_issue, dict):
            raise ValueError("DeepSeek review issue must be an object")
        item_code = str(raw_issue.get("item_code") or "").strip()
        severity = str(raw_issue.get("severity") or "").strip().lower()
        issue = str(raw_issue.get("issue") or "").strip()
        if item_code not in valid_codes:
            raise ValueError(f"DeepSeek review referenced unknown item_code: {item_code}")
        if severity not in REVIEW_SEVERITIES:
            raise ValueError(f"DeepSeek review used invalid severity: {severity}")
        if not issue:
            raise ValueError(f"DeepSeek review issue text is empty for {item_code}")
        issues.append(
            {
                "item_code": item_code,
                "severity": severity,
                "issue_type": str(raw_issue.get("issue_type") or "other").strip(),
                "issue": issue,
                "suggestion": str(raw_issue.get("suggestion") or "").strip(),
            }
        )
    return {
        "verdict": "needs_revision" if issues else "pass",
        "issue_count": len(issues),
        "severity_counts": dict(Counter(issue["severity"] for issue in issues)),
        "issues": issues,
        "family_summary": str(result.get("family_summary") or "").strip(),
    }


def run_independent_review(
    *,
    top_group: str,
    material_family: str,
    comparison_rows: list[dict[str, str]],
    output_dir: Path,
    reuse_review: bool,
) -> dict[str, Any]:
    review_path = output_dir / "independent_review.json"
    if reuse_review and review_path.exists():
        return json.loads(review_path.read_text(encoding="utf-8"))
    messages = build_review_messages(
        top_group=top_group,
        material_family=material_family,
        comparison_rows=comparison_rows,
    )
    request_path = output_dir / "requests" / "independent_review.json"
    request_path.write_text(
        json.dumps({"messages": messages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    settings = replace(load_deepseek_settings(), timeout_seconds=180)
    result = call_deepseek_json_with_retry(messages, settings=settings)
    review = normalize_review_result(
        result,
        {row["item_code"] for row in comparison_rows},
    )
    review.update(
        {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "model": settings.model,
            "authoritative": False,
        }
    )
    review_path.write_text(
        json.dumps(review, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return review


def build_search_keywords(row: dict[str, str]) -> str:
    fields = (
        "item_code",
        "item_name",
        "sku_name",
        "required_specs",
        "optional_specs",
        "material_family",
        "aliases",
        "brand",
        "model",
    )
    return " ".join(row.get(field, "").strip() for field in fields if row.get(field, "").strip())


def apply_preview(
    all_rows: list[dict[str, str]],
    proposed_rows: list[dict[str, str]],
    review: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    proposed_by_code = {row["item_code"]: row for row in proposed_rows}
    review_by_code: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for issue in (review or {}).get("issues", []):
        review_by_code[str(issue.get("item_code", ""))].append(issue)
    preview: list[dict[str, str]] = []
    for source in all_rows:
        row = dict(source)
        proposed = proposed_by_code.get(row.get("item_code", ""))
        if proposed:
            row.update(
                {
                    "item_name": proposed["proposed_item_name"],
                    "sku_name": proposed["proposed_sku_name"],
                    "required_specs": proposed["proposed_required_specs"],
                    "optional_specs": proposed["proposed_optional_specs"],
                    "stock_uom": proposed["proposed_stock_uom"],
                    "purchase_uom": proposed["proposed_stock_uom"],
                    "aliases": proposed["proposed_aliases"],
                    "brand": proposed["proposed_brand"],
                    "model": proposed["proposed_model"],
                }
            )
            row["search_keywords"] = build_search_keywords(row)
            note = f"DeepSeek物料族治理预览：{proposed['change_reason']}"
            review_notes = [
                f"独立复核[{issue['severity']}]：{issue['issue']}"
                for issue in review_by_code.get(row.get("item_code", ""), [])
            ]
            row["governance_note"] = "；".join(
                value
                for value in (row.get("governance_note", ""), note, *review_notes)
                if value
            )
        preview.append(row)
    return preview


def count_values(rows: list[dict[str, str]], field: str) -> dict[str, int]:
    return dict(Counter(row.get(field, "") for row in rows if row.get(field, "")).most_common())


def build_browser_payload(
    rows: list[dict[str, str]],
    *,
    source: Path,
) -> dict[str, Any]:
    browser_rows: list[dict[str, str]] = []
    grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for source_row in rows:
        row = dict(source_row)
        row["search_text"] = build_search_keywords(row).lower()
        row["family_rule"] = ""
        row["family_note"] = "DeepSeek完整物料族治理预览"
        browser_rows.append(row)
        grouped[row.get("top_group", "未分组")].append(row)
    categories = []
    for top_group, group_rows in grouped.items():
        categories.append(
            {
                "name": top_group,
                "sku_count": len(group_rows),
                "name_count": len({row.get("material_family", "") for row in group_rows}),
                "status_counts": count_values(group_rows, "status"),
                "quality_counts": count_values(group_rows, "quality_level"),
                "sub_groups": [
                    {"name": name, "sku_count": count}
                    for name, count in count_values(group_rows, "material_family").items()
                ],
            }
        )
    categories.sort(key=lambda item: (-int(item["sku_count"]), str(item["name"])))
    summary = {
        "sku_count": len(rows),
        "item_name_count": len({row.get("item_name", "") for row in rows}),
        "material_family_count": len({row.get("material_family", "") for row in rows}),
        "top_group_count": len({row.get("top_group", "") for row in rows}),
        "item_group_count": len({row.get("item_group", "") for row in rows}),
        "quality_counts": count_values(rows, "quality_level"),
        "status_counts": count_values(rows, "status"),
    }
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source.relative_to(REPO_ROOT)),
        "family_rules_source": "",
        "family_rules_count": 0,
        "summary": summary,
        "categories": categories,
        "rows": browser_rows,
    }


def build_summary(
    source_rows: list[dict[str, str]],
    proposed_rows: list[dict[str, str]],
    observations: list[str],
) -> dict[str, Any]:
    item_names: dict[str, int] = {}
    duplicate_links: list[dict[str, str]] = []
    source_codes = {row["item_code"] for row in source_rows}
    warnings: list[str] = []
    for row in proposed_rows:
        item_names[row["proposed_item_name"]] = item_names.get(row["proposed_item_name"], 0) + 1
        duplicate_code = row["duplicate_with_item_code"]
        if duplicate_code:
            duplicate_links.append(
                {"item_code": row["item_code"], "duplicate_with_item_code": duplicate_code}
            )
            if duplicate_code not in source_codes:
                warnings.append(
                    f"{row['item_code']} references unknown duplicate code {duplicate_code}"
                )
        if re.search(r"\d+(?:\.\d+)?\s*(?:mm|毫米|×|\*)", row["proposed_item_name"], re.I):
            warnings.append(f"{row['item_code']} proposed_item_name may contain SKU dimensions")
    return {
        "source_rows": len(source_rows),
        "proposed_rows": len(proposed_rows),
        "item_code_coverage": len({row["item_code"] for row in proposed_rows}),
        "proposed_item_name_count": len(item_names),
        "proposed_item_names": dict(sorted(item_names.items())),
        "duplicate_link_count": len(duplicate_links),
        "duplicate_links": duplicate_links,
        "warnings": warnings,
        "family_observations": observations,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def run_chunk(
    *,
    index: int,
    top_group: str,
    material_family: str,
    all_family_rows: list[dict[str, str]],
    target_rows: list[dict[str, str]],
    output_dir: Path,
    dry_run: bool,
    reuse_responses: bool,
) -> dict[str, Any]:
    messages = build_messages(
        top_group=top_group,
        material_family=material_family,
        all_family_rows=all_family_rows,
        target_rows=target_rows,
    )
    request_path = output_dir / "requests" / f"chunk_{index:03d}.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(
        json.dumps({"messages": messages}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if dry_run:
        return {"index": index, "rows": [], "observations": [], "dry_run": True}
    response_path = output_dir / "responses" / f"chunk_{index:03d}.json"
    if reuse_responses and response_path.exists():
        result = json.loads(response_path.read_text(encoding="utf-8"))
    else:
        settings = replace(load_deepseek_settings(), timeout_seconds=180)
        result = call_deepseek_json_with_retry(messages, settings=settings)
    rows, observations = validate_chunk_result(
        result,
        [row["item_code"] for row in target_rows],
    )
    source_by_code = {row["item_code"]: row for row in all_family_rows}
    rows = [
        normalize_family_output(row, material_family, source_by_code.get(row["item_code"]))
        for row in rows
    ]
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"index": index, "rows": rows, "observations": observations, "dry_run": False}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Govern one complete material family with DeepSeek.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--top-group", default="工具耗材")
    parser.add_argument("--material-family", default="钻头")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--chunk-size", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--family-guide", type=Path, default=None)
    parser.add_argument(
        "--auto-guide",
        action="store_true",
        help="Generate a family-specific governance guide with DeepSeek before processing rows.",
    )
    parser.add_argument(
        "--reuse-guide",
        action="store_true",
        help="Reuse a saved family_guide.json instead of calling DeepSeek again.",
    )
    parser.add_argument(
        "--reuse-responses",
        action="store_true",
        help="Reuse saved DeepSeek JSON responses and rerun deterministic validation/post-processing.",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip the independent DeepSeek quality review.",
    )
    parser.add_argument(
        "--reuse-review",
        action="store_true",
        help="Reuse a saved independent_review.json instead of calling DeepSeek again.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_fields, all_rows = read_tsv(args.input)
    family_rows = select_family_rows(
        all_rows,
        top_group=args.top_group,
        material_family=args.material_family,
    )
    if not family_rows:
        raise SystemExit(
            f"No rows found for {args.top_group}/{args.material_family} in {args.input}"
        )
    output_dir = args.output_dir or (
        DEFAULT_OUTPUT_ROOT / f"{args.top_group}_{args.material_family}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.family_guide:
        FAMILY_GUIDES[args.material_family] = normalize_family_guide(
            json.loads(args.family_guide.read_text(encoding="utf-8")),
            args.material_family,
        )
    elif args.auto_guide and not args.dry_run and args.material_family not in FAMILY_GUIDES:
        FAMILY_GUIDES[args.material_family] = generate_family_guide(
            top_group=args.top_group,
            material_family=args.material_family,
            family_rows=family_rows,
            output_dir=output_dir,
            reuse_guide=args.reuse_guide,
        )
    chunks = chunked(family_rows, args.chunk_size)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as executor:
        futures = {
            executor.submit(
                run_chunk,
                index=index,
                top_group=args.top_group,
                material_family=args.material_family,
                all_family_rows=family_rows,
                target_rows=target_rows,
                output_dir=output_dir,
                dry_run=args.dry_run,
                reuse_responses=args.reuse_responses,
            ): index
            for index, target_rows in enumerate(chunks, start=1)
        }
        for future in as_completed(futures):
            results.append(future.result())
    if args.dry_run:
        print(json.dumps({"family_rows": len(family_rows), "chunks": len(chunks)}, ensure_ascii=False))
        return 0

    proposed_rows = [
        row
        for result in sorted(results, key=lambda item: item["index"])
        for row in result["rows"]
    ]
    proposed_rows, _ = validate_chunk_result(
        {"rows": proposed_rows},
        [row["item_code"] for row in family_rows],
    )
    source_by_code = {row["item_code"]: row for row in family_rows}
    proposed_rows = [
        normalize_family_output(
            row,
            args.material_family,
            source_by_code.get(row["item_code"]),
        )
        for row in proposed_rows
    ]
    observations = list(
        dict.fromkeys(
            observation
            for result in sorted(results, key=lambda item: item["index"])
            for observation in result["observations"]
        )
    )
    comparison_rows = build_comparison_rows(family_rows, proposed_rows)
    review = None
    if not args.skip_review:
        review = run_independent_review(
            top_group=args.top_group,
            material_family=args.material_family,
            comparison_rows=comparison_rows,
            output_dir=output_dir,
            reuse_review=args.reuse_review,
        )
    preview_rows = apply_preview(all_rows, proposed_rows, review)
    summary = build_summary(family_rows, proposed_rows, observations)
    summary.update(
        {
            "source": str(args.input.relative_to(REPO_ROOT)),
            "top_group": args.top_group,
            "material_family": args.material_family,
            "chunk_count": len(chunks),
            "model": load_deepseek_settings().model,
            "authoritative": False,
            "note": "Preview only. The authoritative release_v1_0 file was not modified.",
            "independent_review": (
                {
                    "verdict": review["verdict"],
                    "issue_count": review["issue_count"],
                    "severity_counts": review["severity_counts"],
                }
                if review
                else {"verdict": "skipped", "issue_count": 0, "severity_counts": {}}
            ),
        }
    )

    write_tsv(output_dir / "family_governed.tsv", proposed_rows, MODEL_FIELDS)
    write_tsv(output_dir / "before_after.tsv", comparison_rows, COMPARISON_FIELDS)
    if review:
        write_tsv(output_dir / "independent_review.tsv", review["issues"], REVIEW_FIELDS)
    preview_path = output_dir / "material_master_family_governed_preview.tsv"
    write_tsv(preview_path, preview_rows, input_fields)
    (output_dir / "material_master_family_governed_browser_data.json").write_text(
        json.dumps(build_browser_payload(preview_rows, source=preview_path), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
