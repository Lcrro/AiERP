from __future__ import annotations

import argparse
import csv
import json
import sys
import time
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


DEFAULT_INPUT_TSV = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "release_v0_3"
    / "material_master_release_v0_3.tsv"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "master_data" / "price_ready_sku_trial"


SOURCE_FIELDS = [
    "item_code",
    "item_name",
    "sku_name",
    "required_specs",
    "stock_uom",
    "aliases",
    "brand",
    "model",
]


OUTPUT_FIELDS = [
    "source_item_code",
    "original_item_name",
    "original_sku_name",
    "original_required_specs",
    "original_unit",
    "item_code",
    "sku_name",
    "required_specs",
    "unit",
    "estimated_rate",
    "currency",
    "price_basis",
    "default_fill_basis",
    "aliases",
    "brand",
    "model",
]


PROBLEM_KEYWORDS = [
    "安全网",
    "玻璃纸",
    "花篮螺丝",
    "软连接",
    "创可贴",
    "泵头",
    "轴承",
    "接头",
    "空调",
    "输送带",
    "井盖",
    "阀",
    "套装",
    "皮带",
    "卷",
    "吨袋",
    "油布",
    "电缆",
    "扳手",
    "钻头",
]
PROBLEM_UOMS = {"套", "件", "张", "卷", "片", "盒", "桶", "台"}
FORBIDDEN_UNRESOLVED_WORDS = [
    "待补",
    "未知",
    "不详",
    "不确定",
    "无法",
    "缺失",
    "needs_review",
    "unresolved",
]


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


def compact_source(row: dict[str, str]) -> dict[str, str]:
    return {field: row.get(field, "") for field in SOURCE_FIELDS}


def challenge_score(row: dict[str, str]) -> int:
    haystack = " ".join(
        [
            row.get("item_name", ""),
            row.get("sku_name", ""),
            row.get("required_specs", ""),
            row.get("aliases", ""),
            row.get("top_group", ""),
            row.get("material_family", ""),
        ]
    )
    score = 0
    score += sum(3 for keyword in PROBLEM_KEYWORDS if keyword in haystack)
    if row.get("stock_uom") in PROBLEM_UOMS:
        score += 2
    if any(token in row.get("required_specs", "") for token in ["大号", "加厚", "普通", "整套"]):
        score += 1
    if len(row.get("required_specs", "")) < 12:
        score += 1
    return score


def select_rows(rows: list[dict[str, str]], *, limit: int) -> list[dict[str, str]]:
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
            -challenge_score(row),
            row.get("top_group", ""),
            row.get("material_family", ""),
            row.get("item_code", ""),
        )
    )
    selected: list[dict[str, str]] = []
    selected_codes: set[str] = set()
    for keyword in PROBLEM_KEYWORDS:
        for row in active_rows:
            haystack = " ".join(
                [
                    row.get("item_name", ""),
                    row.get("sku_name", ""),
                    row.get("required_specs", ""),
                    row.get("aliases", ""),
                ]
            )
            if keyword in haystack and row["item_code"] not in selected_codes:
                selected.append(row)
                selected_codes.add(row["item_code"])
                break
        if len(selected) >= limit:
            break

    for row in active_rows:
        if len(selected) >= limit:
            break
        if row["item_code"] not in selected_codes:
            selected.append(row)
            selected_codes.add(row["item_code"])
    return [compact_source(row) for row in selected[:limit]]


def select_all_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        compact_source(row)
        for row in rows
        if row.get("status") == "active"
        and row.get("item_code")
        and row.get("sku_name")
        and row.get("stock_uom")
    ]


def build_messages(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output_schema = {
        "rows": [
            {
                "source_item_code": "原输入 item_code",
                "item_code": "保留原 item_code",
                "sku_name": "物料名称 + 最关键规格，例如：密目安全网 1.8m*6m 加厚",
                "required_specs": "够采购、够报价的规格，格式：字段：值；字段：值",
                "unit": "标准单位。这个单位同时用于库存、采购和计价",
                "estimated_rate": "人民币测试单价，数字，必须大于0，对应该标准单位",
                "currency": "固定 CNY",
                "price_basis": "价格口径说明，例如：按1盒100片估价，单价对应单位=盒",
                "default_fill_basis": "哪些字段是按常见采购口径补齐的；无补齐也要写：无需补齐",
                "aliases": "别名/土名，中文分号分隔",
                "brand": "品牌/厂牌；无则空字符串",
                "model": "型号；无则空字符串",
            }
        ],
        "summary": {
            "completed_count": 0,
            "unit_changes": 0,
            "pricing_assumptions": ["string"],
        },
    }
    system_prompt = {
        "role": "system",
        "content": (
            "你是中国土木、市政工程公司的物料主数据编制员兼采购测试价估算员。"
            "目标不是评价旧清单是否可靠，而是借旧清单生成一份可用于 ERPNext 初始账套的标准物料清单。"
            "旧物料名称、规格和单位只是参考；如果旧信息不规则、命名不清、单位不适合报价，你必须按最常见、最合理的采购口径重新编制。"
            "每条都要输出一条能采购、能报价、能入库的标准 SKU。"
            "不要输出待补、未知、不确定、无法判断、needs_review、unresolved 等消极状态。"
            "如果旧数据缺少必要规格，请直接按常见工程采购规格补齐，并在 default_fill_basis 里说明补齐依据。"
            "required_specs 必须足够报价：尺寸/口径/型号/材质/等级/长度/包装数量/额定参数等会影响价格和买错买对的字段要补齐。"
            "单位只保留一个 unit。这个单位同时作为库存单位、采购单位和计价单位；estimated_rate 就是这个 unit 的测试单价。"
            "如果旧清单是小包装或盒装，请直接把标准单位定成更适合采购的包装单位，并把包装数量写入 required_specs。"
            "例如创可贴 100片/盒 应输出 unit=盒, required_specs=包装数量：100片/盒, estimated_rate=12。不要再输出片、盒之间的换算。"
            "例如安全网可按常见密目安全网 1.8m*6m 加厚，单位张估价。"
            "例如卷材、纸、油布等要明确宽度/长度或按米/平方米计价口径。"
            "例如接头、软连接、阀门必须明确口径、材质、连接方式、压力或长度等关键字段。"
            "安全网必填尺寸、类型、特征；若旧数据只有安全网/加厚/3000，按密目安全网 1.8m*6m 补齐，3000可解释为目数或密目规格，但不能缺尺寸。"
            "玻璃纸、保鲜膜、油布、输送带等卷材必须明确宽度、长度或按米/平方米计价，不允许只写宽度。"
            "创可贴、螺丝套装、批头套装、冲凿套装等包装件必须明确每盒/每套数量，并把 unit 定为盒或套。"
            "液压扳手套装、泵头、轴承、空调、卷扬机等设备/备件，required_specs 不能只写品牌，必须补核心型号/功率/载荷/适配设备/尺寸等够报价字段。"
            "快速接头、胶管接头、堵头、软接头等，数字口径必须补单位，例如 52 应写为 52mm 或 DN52；不允许只写口径：52。"
            "本项目历史清单里的“公元”通常是“公称”的误写，不是品牌；遇到时要改为公称口径/公称直径，不得放入 brand。"
            "真正品牌例如世达、黑猫、SKF、公牛等可以保留在 brand；但如品牌不是必须采购条件，不要让名称过长。"
            "价格只用于测试账套，不是真实报价，不代表供应商承诺；不要声称联网或查到了实时价格。"
            "只输出 JSON object，不要 Markdown。"
        ),
    }
    developer_prompt = {
        "role": "system",
        "content": json.dumps(
            {
                "output_schema": output_schema,
                "hard_requirements": [
                    f"rows 长度必须等于输入数量：{len(rows)}。",
                    "每个输入 item_code 必须输出且只输出一行，source_item_code 和 item_code 都必须等于输入 item_code。",
                    "不要输出 item_name、top_group、sub_group、material_family；这些层级字段由主数据发布表锁定，不由模型改写。",
                    "不得输出待补、未知、不详、不确定、无法、缺失、needs_review、unresolved。",
                    "sku_name、required_specs、unit、price_basis、default_fill_basis 都不能为空。",
                    "estimated_rate 必须是正数。",
                    "currency 固定 CNY。",
                    "required_specs 必须使用“字段：值；字段：值”格式。",
                    "required_specs 不能只有品牌；如果原始信息只有品牌，必须按常见采购口径补型号/规格/适配对象。",
                    "required_specs 里数字口径必须有单位或标准前缀，例如 DN50、50mm、M20、4寸。",
                    "安全网类 required_specs 必须同时包含尺寸和类型/特征。",
                    "套装类 required_specs 必须包含规格范围或件数。",
                    "包装类必须把包装数量写入 required_specs，并将 unit 定为盒、包、套等采购直觉单位。",
                    "sku_name 必须是人能看懂的商品标题，不要只重复 item_name。",
                    "不要新增或删除 item_code。",
                    "不要输出质量等级、放行等级、风险等级或不可估价标记。",
                ],
            },
            ensure_ascii=False,
        ),
    }
    user_prompt = {
        "role": "user",
        "content": json.dumps(
            {
                "task": "请将以下旧物料行重新编制成价格就绪版标准 SKU，并同步生成测试采购价。",
                "items": rows,
            },
            ensure_ascii=False,
        ),
    }
    return [system_prompt, developer_prompt, user_prompt]


def to_float(value: Any, *, field: str, item_code: str) -> float:
    try:
        number = float(str(value).strip())
    except ValueError as exc:
        raise ValueError(f"{item_code}: {field} must be numeric, got {value!r}") from exc
    if number <= 0:
        raise ValueError(f"{item_code}: {field} must be positive, got {value!r}")
    return number


def contains_forbidden_text(value: str) -> bool:
    return any(word in value for word in FORBIDDEN_UNRESOLVED_WORDS)


def validate_response(source_rows: list[dict[str, str]], response: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    response_rows = response.get("rows")
    if not isinstance(response_rows, list):
        raise ValueError("DeepSeek response must contain rows list")

    source_by_code = {row["item_code"]: row for row in source_rows}
    seen: set[str] = set()
    output_rows: list[dict[str, Any]] = []

    for response_row in response_rows:
        if not isinstance(response_row, dict):
            raise ValueError(f"Invalid response row: {response_row!r}")
        source_item_code = str(response_row.get("source_item_code", "")).strip()
        item_code = str(response_row.get("item_code", "")).strip()
        if not source_item_code:
            source_item_code = item_code
        if source_item_code != item_code:
            raise ValueError(f"{source_item_code}: source_item_code and item_code must match")
        if item_code not in source_by_code:
            raise ValueError(f"Unexpected item_code: {item_code}")
        if item_code in seen:
            raise ValueError(f"Duplicate item_code: {item_code}")
        seen.add(item_code)

        required_text_fields = [
            "sku_name",
            "required_specs",
            "unit",
            "price_basis",
            "default_fill_basis",
        ]
        for field in required_text_fields:
            value = str(response_row.get(field, "")).strip()
            if not value:
                raise ValueError(f"{item_code}: {field} must not be empty")
            if field != "default_fill_basis" and contains_forbidden_text(value):
                raise ValueError(f"{item_code}: {field} contains unresolved wording: {value!r}")

        estimated_rate = to_float(
            response_row.get("estimated_rate"),
            field="estimated_rate",
            item_code=item_code,
        )
        currency = str(response_row.get("currency", "")).strip().upper()
        if currency != "CNY":
            raise ValueError(f"{item_code}: currency must be CNY")

        source = source_by_code[item_code]
        output_rows.append(
            {
                "source_item_code": item_code,
                "original_item_name": source.get("item_name", ""),
                "original_sku_name": source.get("sku_name", ""),
                "original_required_specs": source.get("required_specs", ""),
                "original_unit": source.get("stock_uom", ""),
                "item_code": item_code,
                "sku_name": str(response_row.get("sku_name", "")).strip(),
                "required_specs": str(response_row.get("required_specs", "")).strip(),
                "unit": str(response_row.get("unit", "")).strip(),
                "estimated_rate": f"{estimated_rate:.2f}",
                "currency": currency,
                "price_basis": str(response_row.get("price_basis", "")).strip(),
                "default_fill_basis": str(response_row.get("default_fill_basis", "")).strip(),
                "aliases": str(response_row.get("aliases", "")).strip(),
                "brand": str(response_row.get("brand", "")).strip(),
                "model": str(response_row.get("model", "")).strip(),
            }
        )

    missing = sorted(set(source_by_code) - seen)
    if missing:
        raise ValueError(f"Missing item_code in response: {missing}")
    return output_rows, {"row_count": len(output_rows)}


def chunk_rows(rows: list[dict[str, str]], chunk_size: int) -> list[list[dict[str, str]]]:
    return [rows[index : index + chunk_size] for index in range(0, len(rows), chunk_size)]


def process_chunk(
    *,
    chunk_index: int,
    rows: list[dict[str, str]],
    output_dir: Path,
    timeout_seconds: int,
    retries: int,
    force: bool = False,
) -> list[dict[str, Any]]:
    chunk_dir = output_dir / f"chunk_{chunk_index:03d}"
    output_path = chunk_dir / "output.tsv"
    validation_path = chunk_dir / "validation.json"
    if output_path.exists() and validation_path.exists() and not force:
        return read_tsv(output_path)

    messages = build_messages(rows)
    write_tsv(chunk_dir / "input.tsv", rows, SOURCE_FIELDS)
    write_json(
        chunk_dir / "request.json",
        {
            "chunk_index": chunk_index,
            "row_count": len(rows),
            "rows": rows,
            "messages": messages,
        },
    )
    settings = replace(load_deepseek_settings(), timeout_seconds=timeout_seconds)
    last_error = ""
    for attempt in range(1, retries + 2):
        try:
            response = call_deepseek_json(messages, settings=settings)
            write_json(chunk_dir / "response.json", response)
            output_rows, validation = validate_response(rows, response)
            write_tsv(output_path, output_rows, OUTPUT_FIELDS)
            write_json(
                validation_path,
                {
                    **validation,
                    "chunk_index": chunk_index,
                    "attempt": attempt,
                },
            )
            return output_rows
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            write_json(
                chunk_dir / "error.json",
                {
                    "chunk_index": chunk_index,
                    "attempt": attempt,
                    "error": last_error,
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
            if attempt <= retries:
                time.sleep(3 * attempt)
    raise RuntimeError(f"chunk {chunk_index} failed: {last_error}")


def process_chunk_summary(
    *,
    chunk_index: int,
    rows: list[dict[str, str]],
    output_dir: Path,
    timeout_seconds: int,
    retries: int,
    force: bool,
) -> dict[str, Any]:
    try:
        output_rows = process_chunk(
            chunk_index=chunk_index,
            rows=rows,
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            retries=retries,
            force=force,
        )
        return {
            "chunk_index": chunk_index,
            "status": "ok",
            "row_count": len(output_rows),
            "output_tsv": str(output_dir / f"chunk_{chunk_index:03d}" / "output.tsv"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "chunk_index": chunk_index,
            "status": "failed",
            "row_count": len(rows),
            "error": f"{type(exc).__name__}: {exc}",
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run DeepSeek price-ready SKU compilation.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_TSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--all", action="store_true", help="Process all active material rows.")
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--retries", type=int, default=1)
    parser.add_argument("--resume-run", type=Path, default=None)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    all_rows = read_tsv(args.input)
    source_rows = select_all_rows(all_rows) if args.all else select_rows(all_rows, limit=args.limit)
    if not source_rows:
        raise SystemExit("No source rows selected")

    output_dir = args.resume_run or (args.output_dir / datetime.now().strftime("%Y%m%d%H%M%S"))
    write_tsv(output_dir / "price_ready_sku_trial_input.tsv", source_rows, SOURCE_FIELDS)
    write_json(
        output_dir / "price_ready_sku_trial_request.json",
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "input": str(args.input),
            "limit": "all" if args.all else args.limit,
            "rows": source_rows,
            "chunk_size": args.chunk_size,
            "concurrency": args.concurrency,
            "timeout_seconds": args.timeout_seconds,
            "retries": args.retries,
        },
    )
    chunks = chunk_rows(source_rows, args.chunk_size)
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "input_rows": len(source_rows),
                "chunk_count": len(chunks),
                "chunk_size": args.chunk_size,
                "concurrency": args.concurrency,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    results: list[dict[str, Any]] = []
    if args.concurrency == 1:
        for chunk_index, chunk in enumerate(chunks, start=1):
            result = process_chunk_summary(
                chunk_index=chunk_index,
                rows=chunk,
                output_dir=output_dir,
                timeout_seconds=args.timeout_seconds,
                retries=args.retries,
                force=args.force,
            )
            results.append(result)
            print(json.dumps(result, ensure_ascii=False), flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = [
                executor.submit(
                    process_chunk_summary,
                    chunk_index=chunk_index,
                    rows=chunk,
                    output_dir=output_dir,
                    timeout_seconds=args.timeout_seconds,
                    retries=args.retries,
                    force=args.force,
                )
                for chunk_index, chunk in enumerate(chunks, start=1)
            ]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                print(json.dumps(result, ensure_ascii=False), flush=True)

    results.sort(key=lambda result: result["chunk_index"])
    write_json(output_dir / "chunk_results.json", results)
    failures = [result for result in results if result["status"] != "ok"]
    output_rows: list[dict[str, Any]] = []
    for result in results:
        if result["status"] == "ok":
            output_rows.extend(read_tsv(Path(result["output_tsv"])))

    item_codes = [row["item_code"] for row in output_rows]
    duplicate_item_codes = sorted({code for code in item_codes if item_codes.count(code) > 1})
    validation = {
        "row_count": len(output_rows),
        "chunk_count": len(chunks),
        "failed_chunks": len(failures),
        "duplicate_item_codes": duplicate_item_codes,
    }
    write_tsv(output_dir / "price_ready_sku_trial_output.tsv", output_rows, OUTPUT_FIELDS)
    write_json(
        output_dir / "price_ready_sku_trial_validation.json",
        {
            **validation,
            "output_tsv": str(output_dir / "price_ready_sku_trial_output.tsv"),
        },
    )

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "input_rows": len(source_rows),
                "output_rows": len(output_rows),
                "failed_chunks": len(failures),
                "output_tsv": str(output_dir / "price_ready_sku_trial_output.tsv"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if failures:
        raise SystemExit(f"{len(failures)} chunk(s) failed; see {output_dir / 'chunk_results.json'}")


if __name__ == "__main__":
    main()
