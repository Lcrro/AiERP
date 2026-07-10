from __future__ import annotations

import argparse
import csv
import json
import sys
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


DEFAULT_INPUT_TSV = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "release_v0_3"
    / "material_master_release_v0_3.tsv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "master_data" / "test_price_trial"
DEFAULT_SUPPLIER_CODE = "SUP-TEST-GENERAL"
DEFAULT_PRICE_LIST = "PL-BUY-TEST"


INPUT_FIELDS = [
    "item_code",
    "item_name",
    "sku_name",
    "required_specs",
    "optional_specs",
    "top_group",
    "sub_group",
    "material_family",
    "stock_uom",
    "purchase_uom",
    "brand",
    "model",
    "aliases",
]


PRICE_TSV_FIELDS = [
    "supplier_code",
    "price_list",
    "item_code",
    "item_name",
    "sku_name",
    "top_group",
    "sub_group",
    "material_family",
    "required_specs",
    "stock_uom",
    "purchase_uom",
    "estimated_rate",
    "currency",
    "confidence",
    "pricing_basis",
    "risk_flags",
    "price_source",
    "note",
]


VOLATILE_PRICE_KEYWORDS = [
    "空调",
    "泵",
    "电机",
    "设备",
    "井盖",
    "钢材",
    "钢筋",
    "螺纹钢",
    "角钢",
    "槽钢",
    "阀",
    "流量计",
    "输送带",
    "变频器",
    "液压",
    "电缆",
    "电箱",
    "配电",
]

RISKY_CONFIDENCE_FLAGS = {
    "brand_sensitive",
    "unit_may_need_conversion",
    "volatile_market_price",
    "spec_too_generic",
    "high_uncertainty",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_tsv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, delimiter="\t", fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def compact_row(row: dict[str, str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in INPUT_FIELDS}


def select_rows(rows: list[dict[str, str]], *, limit: int, sample: str) -> list[dict[str, str]]:
    active_rows = [
        row
        for row in rows
        if row.get("status") == "active"
        and row.get("item_code")
        and row.get("sku_name")
        and row.get("stock_uom")
    ]
    active_rows.sort(
        key=lambda row: (
            row.get("top_group", ""),
            row.get("sub_group", ""),
            row.get("material_family", ""),
            row.get("item_code", ""),
        )
    )
    if sample == "first":
        return [compact_row(row) for row in active_rows[:limit]]

    groups: dict[str, list[dict[str, str]]] = {}
    for row in active_rows:
        groups.setdefault(row.get("top_group", "") or "未分类", []).append(row)

    selected: list[dict[str, str]] = []
    group_names = sorted(groups)
    cursor = 0
    while len(selected) < limit and group_names:
        group_name = group_names[cursor % len(group_names)]
        group_rows = groups[group_name]
        if group_rows:
            selected.append(group_rows.pop(0))
        group_names = [name for name in group_names if groups[name]]
        cursor += 1
    return [compact_row(row) for row in selected[:limit]]


def build_messages(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    schema = {
        "rows": [
            {
                "item_code": "必须原样返回输入 item_code",
                "estimated_unit_price": "人民币测试单价，数字，保留最多2位小数，必须大于0",
                "currency": "固定 CNY",
                "price_uom": "必须等于输入 stock_uom",
                "confidence": "high | medium | low",
                "pricing_basis": "简短中文依据，说明按什么规格/材质/常见采购价估算",
                "risk_flags": [
                    "可为空数组；常见值：spec_too_generic, brand_sensitive, unit_may_need_conversion, volatile_market_price, high_uncertainty"
                ],
            }
        ],
        "summary": {
            "assumptions": ["估价口径"],
            "high_uncertainty_count": 0,
        },
    }
    system_prompt = {
        "role": "system",
        "content": (
            "你是中国土木、市政、工程施工场景的采购测试价估算员。"
            "你的任务是根据物料名称、SKU名称、规格、类别、单位，给 ERPNext 测试账套生成合理的人民币测试单价。"
            "这些价格只用于沙盘和测试，不是真实报价，不代表供应商承诺。"
            "不要联网，不要声称你查到了实时价格。"
            "不要更改 item_code、sku_name、规格或单位。"
            "如果信息不完整，也要按常见工程采购口径给一个合理测试价，并把 confidence 设为 low 或 medium。"
            "价格要符合采购直觉：普通耗材便宜，大规格钢材/阀门/电气元件/设备件更贵；同类中规格越大通常价格越高。"
            "大件设备、井盖、钢材、输送带、阀门、电气元件、品牌工具、专用配件价格波动较大，除非规格非常明确，否则 confidence 不得为 high。"
            "规格过泛、品牌/型号缺失、单位可能涉及包装换算、市场价格波动大的物料必须加入 risk_flags。"
            "如果单位是套、件、台且规格不完整，要特别保守，risk_flags 至少包含 high_uncertainty 或 spec_too_generic。"
            "只输出 JSON object，不要 Markdown。"
        ),
    }
    developer_prompt = {
        "role": "system",
        "content": json.dumps(
            {
                "output_schema": schema,
                "hard_requirements": [
                    f"rows 长度必须等于输入数量：{len(rows)}。",
                    "rows 必须完整覆盖输入 item_code，不能新增、遗漏、重复。",
                    "estimated_unit_price 必须是数字，不要带 ¥、元、人民币 等单位文本。",
                    "currency 固定为 CNY。",
                    "price_uom 必须等于输入 stock_uom；不要擅自把个、只、套、米、kg互相换算。",
                    "confidence 只能是 high、medium、low。",
                    "pricing_basis 控制在 50 个汉字以内。",
                    "risk_flags 只能是字符串数组。",
                    "不要输出真实供应商名称，不要输出采购建议动作，只做测试价估算。",
                    "价格波动类物料必须优先使用 medium 或 low：设备、井盖、钢材、输送带、阀门、电气元件、品牌工具、专用配件。",
                    "若 sku_name 或 required_specs 缺少关键型号/材质/尺寸/额定参数，confidence 不得为 high。",
                    "risk_flags 可用值优先从这些选择：spec_too_generic、brand_sensitive、unit_may_need_conversion、volatile_market_price、high_uncertainty。",
                ],
                "pricing_policy": {
                    "supplier_code": DEFAULT_SUPPLIER_CODE,
                    "price_list": DEFAULT_PRICE_LIST,
                    "tax": "不含税测试单价",
                    "currency": "CNY",
                    "rounding": "保留最多2位小数",
                },
            },
            ensure_ascii=False,
        ),
    }
    user_prompt = {
        "role": "user",
        "content": json.dumps(
            {
                "task": "请为以下物料生成测试采购单价。",
                "items": rows,
            },
            ensure_ascii=False,
        ),
    }
    return [system_prompt, developer_prompt, user_prompt]


def normalize_price(value: Any) -> float:
    if isinstance(value, (int, float)):
        price = float(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace("¥", "").replace("￥", "").replace("元", "")
        price = float(cleaned)
    else:
        raise ValueError(f"Unsupported price value: {value!r}")
    if price <= 0:
        raise ValueError(f"Price must be positive: {value!r}")
    return round(price, 2)


def normalize_risk_flags(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        raw_flags = value
    elif isinstance(value, str):
        raw_flags = value.replace(",", "；").split("；")
    else:
        raw_flags = [str(value)]

    flags: list[str] = []
    for raw_flag in raw_flags:
        flag = str(raw_flag).strip()
        if flag and flag not in flags:
            flags.append(flag)
    return flags


def append_risk_flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def has_volatile_price_hint(source: dict[str, str]) -> bool:
    haystack = " ".join(
        [
            source.get("item_name", ""),
            source.get("sku_name", ""),
            source.get("required_specs", ""),
            source.get("top_group", ""),
            source.get("sub_group", ""),
            source.get("material_family", ""),
        ]
    )
    return any(keyword in haystack for keyword in VOLATILE_PRICE_KEYWORDS)


def adjust_confidence(
    *,
    confidence: str,
    risk_flags: list[str],
    source: dict[str, str],
) -> str:
    if has_volatile_price_hint(source):
        append_risk_flag(risk_flags, "volatile_market_price")
    if source.get("brand") or "品牌：" in source.get("required_specs", ""):
        append_risk_flag(risk_flags, "brand_sensitive")

    if "high_uncertainty" in risk_flags:
        return "low"
    if confidence == "high" and any(flag in RISKY_CONFIDENCE_FLAGS for flag in risk_flags):
        return "medium"
    return confidence


def validate_response(input_rows: list[dict[str, str]], response: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = response.get("rows")
    if not isinstance(rows, list):
        raise ValueError("DeepSeek response must contain rows list")

    input_by_code = {row["item_code"]: row for row in input_rows}
    seen: set[str] = set()
    output_rows: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"Invalid output row: {row!r}")
        item_code = str(row.get("item_code", "")).strip()
        if item_code not in input_by_code:
            raise ValueError(f"Unexpected item_code in response: {item_code}")
        if item_code in seen:
            raise ValueError(f"Duplicate item_code in response: {item_code}")
        seen.add(item_code)

        source = input_by_code[item_code]
        price = normalize_price(row.get("estimated_unit_price"))
        currency = str(row.get("currency", "")).strip().upper()
        confidence = str(row.get("confidence", "")).strip().lower()
        price_uom = str(row.get("price_uom", "")).strip()
        risk_flags = normalize_risk_flags(row.get("risk_flags"))
        if currency != "CNY":
            raise ValueError(f"{item_code}: currency must be CNY, got {currency!r}")
        if confidence not in {"high", "medium", "low"}:
            raise ValueError(f"{item_code}: invalid confidence {confidence!r}")
        if price_uom != source.get("stock_uom", ""):
            warnings.append(
                f"{item_code}: price_uom {price_uom!r} differs from stock_uom {source.get('stock_uom', '')!r}"
            )
        confidence = adjust_confidence(
            confidence=confidence,
            risk_flags=risk_flags,
            source=source,
        )

        output_rows.append(
            {
                "supplier_code": DEFAULT_SUPPLIER_CODE,
                "price_list": DEFAULT_PRICE_LIST,
                "item_code": item_code,
                "item_name": source.get("item_name", ""),
                "sku_name": source.get("sku_name", ""),
                "top_group": source.get("top_group", ""),
                "sub_group": source.get("sub_group", ""),
                "material_family": source.get("material_family", ""),
                "required_specs": source.get("required_specs", ""),
                "stock_uom": source.get("stock_uom", ""),
                "purchase_uom": source.get("purchase_uom", ""),
                "estimated_rate": f"{price:.2f}",
                "currency": currency,
                "confidence": confidence,
                "pricing_basis": str(row.get("pricing_basis", "")).strip(),
                "risk_flags": "；".join(str(flag) for flag in risk_flags),
                "price_source": "deepseek_estimated_for_test",
                "note": "DeepSeek测试估价；非真实采购报价。",
            }
        )

    missing = sorted(set(input_by_code) - seen)
    if missing:
        raise ValueError(f"Missing item_code in response: {missing}")

    return output_rows, {"warnings": warnings, "row_count": len(output_rows)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a small DeepSeek trial for ERPNext test item prices.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_TSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--sample", choices=["stratified", "first"], default="stratified")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit <= 0:
        raise SystemExit("--limit must be positive")

    all_rows = read_tsv(args.input)
    selected_rows = select_rows(all_rows, limit=args.limit, sample=args.sample)
    if not selected_rows:
        raise SystemExit("No rows selected for price trial")

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    output_dir = args.output_dir / timestamp
    messages = build_messages(selected_rows)
    request_payload = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "input": str(args.input),
        "limit": args.limit,
        "sample": args.sample,
        "rows": selected_rows,
        "messages": messages,
    }
    write_json(output_dir / "deepseek_test_price_trial_request.json", request_payload)
    write_tsv(output_dir / "deepseek_test_price_trial_input.tsv", selected_rows, INPUT_FIELDS)

    settings = load_deepseek_settings()
    response = call_deepseek_json(messages, settings=settings)
    write_json(output_dir / "deepseek_test_price_trial_response.json", response)

    price_rows, validation = validate_response(selected_rows, response)
    write_tsv(output_dir / "deepseek_test_price_trial_prices.tsv", price_rows, PRICE_TSV_FIELDS)
    write_json(
        output_dir / "deepseek_test_price_trial_validation.json",
        {
            **validation,
            "output_tsv": str(output_dir / "deepseek_test_price_trial_prices.tsv"),
        },
    )

    summary = {
        "output_dir": str(output_dir),
        "input_rows": len(selected_rows),
        "price_rows": len(price_rows),
        "warnings": validation["warnings"],
        "price_tsv": str(output_dir / "deepseek_test_price_trial_prices.tsv"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
