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


DEFAULT_INPUT_JSON = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "governance_v0_2"
    / "manual_third_layer_mapping"
    / "material_master_third_layer_preview.json"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs" / "material_master" / "sku_governance"


SKU_GOVERNANCE_PROBLEMS = [
    {
        "problem": "SKU名称太笼统",
        "symptom": "同一个三级物料名下只有代码和散乱规格，采购员无法一眼看懂差异。",
        "solution": "新增 standard_sku_name，按“物料名称 + 最关键规格”生成可读名称。",
    },
    {
        "problem": "规格字段混乱",
        "symptom": "规格、类型、形态、连接、别名等字段互相重复或错位。",
        "solution": "把规格拆成 required_specs 和 optional_specs；同义字段归一为标准字段名。",
    },
    {
        "problem": "关键规格缺失",
        "symptom": "缺少材质、口径、连接方式、额定参数等采购决策字段。",
        "solution": "不要补全百科式规格；只保留影响采购买错/买对的最小字段。行业默认且不会造成误解的字段直接删除，并记录到 removed_default_fields。",
    },
    {
        "problem": "别名混进规格",
        "symptom": "老虎钳、直通、接头等别名被写入必填规格。",
        "solution": "别名进入 aliases，不参与 required_specs，不作为唯一 SKU 判定字段。",
    },
    {
        "problem": "单位不统一",
        "symptom": "同类物料混用 个、只、把、支、套。",
        "solution": "按物料名称给出 standard_uom，并记录需要人工确认的单位换算。",
    },
    {
        "problem": "疑似重复 SKU",
        "symptom": "同一物料名称下，多条关键规格高度相似。",
        "solution": "输出 duplicate_group 和 duplicate_reason；只提示疑似合并，不直接删除。",
    },
    {
        "problem": "Agent 难以自动选择",
        "symptom": "搜索结果里缺少清晰商品标题，模型只能猜。",
        "solution": "为每条 SKU 输出 standard_sku_name 和 minimal_required_specs，让员工/Agent 能直接看懂并避免买错。",
    },
]


GENERAL_SKU_TEMPLATE = {
    "standard_sku_name_rule": "物料名称 + 最关键规格；示例：PPR直接 25、球阀 DN50、弯头 90度 DN25、螺丝 M8*45。",
    "minimal_required_specs": [
        "尺寸/口径/型号/容量等核心规格",
        "材质、接口、压力等级、电流、强度等级等会导致买错/买对的字段",
        "长度、角度、异径关系、内丝/外丝等结构差异",
    ],
    "delete_by_default": [
        "行业默认且不会造成误解的连接方式",
        "普通形态描述，例如普通直通、普通弯头",
        "不影响采购选择的泛化描述",
        "品牌，除非原始物料本身是指定品牌件、设备兼容件，或品牌会明显影响安装兼容性",
    ],
    "known_input_corrections": {
        "公元": "公称；本项目历史清单里“公元”通常是老员工把“公称”写错，不是品牌。",
    },
    "duplicate_rule": "标准 SKU 名、最小关键规格和标准单位一致时标记疑似合并；单位冲突不应拆成不同 SKU，应在治理依据中说明统一口径。",
    "minimal_sku_rule": {
        "keep": "只保留会导致买错/买对的字段，不做百科式规格堆砌。",
        "remove": "删除行业默认且不会造成误解的字段，但不得删除接口、口径、长度、角度、额定参数等关键差异。",
        "infer_reasonably": "老清单只是参考，目标是生成初始常用物料表；原始规格缺失时，按常见采购口径生成一个合理 SKU，不输出无法补齐。",
        "trace": "被删除或默认推断的字段写入 removed_default_fields/default_fill_basis，方便后续审计，但不进入正式最小规格。",
    },
}


def compact_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "item_code": row.get("item_code", ""),
        "current_item_name": row.get("item_name", ""),
        "required_specs": row.get("required_specs", ""),
        "optional_specs": row.get("optional_specs", ""),
        "item_group": row.get("item_group", ""),
        "top_group": row.get("top_group", ""),
        "material_family": row.get("material_family", ""),
        "stock_uom": row.get("stock_uom", ""),
        "purchase_uom": row.get("purchase_uom", ""),
        "aliases": row.get("aliases", ""),
        "governance_note": row.get("governance_note", ""),
    }


def load_target_skus(
    input_json: Path,
    *,
    top_group: str,
    material_family: str,
    material_name: str,
) -> list[dict[str, Any]]:
    payload = json.loads(input_json.read_text(encoding="utf-8"))
    rows = payload["rows"]
    target_rows = [
        compact_row(row)
        for row in rows
        if row.get("top_group") == top_group
        and row.get("material_family") == material_family
        and row.get("item_name") == material_name
    ]
    target_rows.sort(key=lambda row: row["item_code"])
    return target_rows


def build_messages(
    *,
    top_group: str,
    material_family: str,
    material_name: str,
    skus: list[dict[str, Any]],
) -> list[dict[str, str]]:
    output_schema = {
        "target": {
            "top_group": top_group,
            "material_family": material_family,
            "material_name": material_name,
            "sku_count": len(skus),
        },
        "rows": [
            {
                "item_code": "string",
                "standard_item_name": "三级物料名称，例如：直接/直通、球阀、弯头",
                "standard_sku_name": "物料名称 + 最关键规格，例如：PPR直接 25、球阀 DN50",
                "minimal_required_specs": "最小必填规格，必须使用“字段名：值；字段名：值”格式，只保留影响采购买错/买对的字段",
                "standard_uom": "标准单位",
                "brand": "品牌/厂牌，例如：埃美柯、世达；无则空字符串；默认不参与唯一 SKU 判断。注意：本项目里的“公元”不是品牌，是“公称”的误写。",
                "aliases": "别名，用中文分号分隔；没有则空字符串",
                "removed_default_fields": ["被删除的行业默认/低价值字段，例如：连接方式：热熔"],
                "default_fill_basis": "原始字段缺失时，生成常用SKU的依据；没有则空字符串",
                "merge_group": "疑似可合并组编号，例如 M001；没有则空字符串",
                "merge_reason": "疑似合并原因；没有则空字符串",
                "source_item_code": "原始 item_code",
                "governance_reason": "简短说明为什么保留/删除这些字段",
            }
        ],
        "summary": {
            "completed_count": 0,
            "manual_check_count": 0,
            "duplicate_groups": [
                {
                    "group_id": "D001",
                    "item_codes": ["string"],
                    "reason": "string",
                    "suggested_action": "merge | keep_separate | needs_human_review",
                }
            ],
            "observations": ["string"],
        },
    }
    system_prompt = {
        "role": "system",
        "content": (
            "你是制造业/土木工程物料主数据 SKU 治理员。"
            "你的任务是把同一三级物料名称下的脏 SKU 明细整理成初始物料清单的最小可用 SKU。"
            "不要执行任何系统操作，不要编造不存在的 item_code，不要删除行。"
            "每个输入 item_code 必须输出且只输出一行。"
            "标准 SKU 名称必须使用“物料名称 + 最关键规格”，让采购员一眼能判断买什么。"
            "只保留会影响买错/买对的字段，不要保留百科式技术参数。"
            "行业默认且不会造成误解的字段要直接删除，不进入 standard_sku_name，也不进入 minimal_required_specs。"
            "例如 PPR直接 25 不需要写热熔；PVC直接 75 不需要写胶粘/承插；普通弯头不需要写形态：弯头。"
            "但内丝、外丝、异径、大小头、材质、规格口径、长度、角度、压力等级、电流等级会影响买错/买对，必须保留。"
            "别名/土名必须放 aliases，不得塞进 required_specs。"
            "老清单只是初始库参考，不是要还原历史采购真相；原始信息缺失时，请生成一个最常见、最适合作为初始库的合理 SKU。"
            "本项目历史清单里的“公元”通常是“公称”的误写，不是品牌；遇到公元DN50、公元25、公元规格等，必须规范为公称直径/规格口径，不得放入 brand。"
            "真正的品牌/厂牌例如埃美柯、世达应放入 brand 字段。"
            "品牌默认不进入 standard_sku_name 或 minimal_required_specs，除非是指定品牌件、设备兼容件，或品牌会明显影响安装兼容性。"
            "不要输出 unresolved、manual_check、needs_review、quality、policy 或任何放行/未通过字段。"
            "如果是默认推断或删除默认字段，写到 removed_default_fields/default_fill_basis。"
            "只输出 JSON object，不要 Markdown，不要解释性正文。"
        ),
    }
    developer_prompt = {
        "role": "system",
        "content": json.dumps(
            {
                "sku_governance_problems_and_solutions": SKU_GOVERNANCE_PROBLEMS,
                "target_template": GENERAL_SKU_TEMPLATE,
                "output_schema": output_schema,
                "hard_requirements": [
                    f"rows 长度必须等于输入 sku_count：{len(skus)}",
                    "rows 中 item_code 必须完整覆盖输入 item_code，不能新增、遗漏、重复。",
                    "standard_sku_name 不要只写 item_code，不要只写三级名称。",
                    "minimal_required_specs 必须保留字段名，格式类似：材质：PPR；规格/口径：25。",
                    "行业默认字段不要放入 standard_sku_name 或 minimal_required_specs；但接口、口径、长度、角度、压力等级、电流等级必须保留。",
                    "本项目里的“公元”不是品牌，是“公称”的误写；必须规范为公称直径/规格口径，不得输出到 brand、aliases 或 removed_default_fields。",
                    "真正的品牌/厂牌必须放入 brand 字段；默认不得进入 minimal_required_specs；除非它是指定品牌件、设备兼容件，或兼容性依赖品牌。",
                    "removed_default_fields 用来记录被删除的行业默认/低价值规格，不要把正常识别出来的品牌写成被删除字段。",
                    "内丝/外丝/内螺纹/外螺纹必须保留，并统一成接口：内丝 或 接口：外丝。",
                    "异径、大小头、多规格组合、长度组合、角度组合必须保留。",
                    "如果原始核心字段缺失但名称/同组规律能合理推断，请生成合理初始 SKU，并记录 default_fill_basis。",
                    "如果多个历史 item_code 生成同一个 standard_sku_name 和 minimal_required_specs，标记 merge_group。",
                    "不得输出 unresolved、manual_check、quality_level、agent_use_policy 或任何放行等级字段。",
                ],
            },
            ensure_ascii=False,
        ),
    }
    user_prompt = {
        "role": "user",
        "content": json.dumps(
            {
                "task": "请治理以下 SKU，输出标准 SKU 名、最小关键规格、标准单位、别名、删除的默认字段、默认补齐依据和疑似重复组。",
                "target": {
                    "top_group": top_group,
                    "material_family": material_family,
                    "material_name": material_name,
                },
                "skus": skus,
            },
            ensure_ascii=False,
        ),
    }
    return [system_prompt, developer_prompt, user_prompt]


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "item_code",
        "standard_item_name",
        "standard_sku_name",
        "minimal_required_specs",
        "standard_uom",
        "brand",
        "aliases",
        "removed_default_fields",
        "default_fill_basis",
        "merge_group",
        "merge_reason",
        "source_item_code",
        "governance_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            for list_field in ("removed_default_fields",):
                values = normalized.get(list_field, [])
                if isinstance(values, list):
                    normalized[list_field] = "；".join(str(item) for item in values)
            writer.writerow({key: normalized.get(key, "") for key in fieldnames})


def validate_result(result: dict[str, Any], input_item_codes: list[str]) -> dict[str, Any]:
    rows = result.get("rows")
    if not isinstance(rows, list):
        raise ValueError("DeepSeek result must include rows list")
    output_codes = [row.get("item_code") for row in rows if isinstance(row, dict)]
    input_set = set(input_item_codes)
    output_set = set(output_codes)
    duplicates = sorted(code for code in output_set if output_codes.count(code) > 1)
    merged_count = 0
    warnings: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        item_code = str(row.get("item_code") or "")
        forbidden_fields = {
            "quality_level",
            "agent_use_policy",
            "unresolved_specs",
            "manual_check_reason",
            "needs_review",
            "policy",
        }
        leaked_fields = sorted(field for field in forbidden_fields if field in row)
        if leaked_fields:
            warnings.append({"item_code": item_code, "warning": "result contains forbidden fields", "fields": "；".join(leaked_fields)})
        if row.get("merge_group"):
            merged_count += 1
        if not row.get("standard_sku_name"):
            warnings.append({"item_code": item_code, "warning": "missing standard_sku_name"})
        if not row.get("minimal_required_specs"):
            warnings.append({"item_code": item_code, "warning": "missing minimal_required_specs"})
        required_text = str(row.get("minimal_required_specs") or "")
        if required_text and "：" not in required_text:
            warnings.append(
                {
                    "item_code": item_code,
                    "warning": "minimal_required_specs should use 字段名：值 format",
                    "minimal_required_specs": required_text,
                }
            )
        if any(default_term in required_text for default_term in ("形态：直通", "形态：弯头", "普通直通", "普通弯头")):
            warnings.append(
                {
                    "item_code": item_code,
                    "warning": "minimal_required_specs may still contain default/low-value fields",
                    "minimal_required_specs": required_text,
                }
            )
        if "品牌：" in required_text:
            warnings.append(
                {
                    "item_code": item_code,
                    "warning": "minimal_required_specs contains brand; verify brand is truly required",
                    "minimal_required_specs": required_text,
                }
            )
        if "公元" in required_text:
            warnings.append(
                {
                    "item_code": item_code,
                    "warning": "minimal_required_specs contains 公元; normalize it as 公称/口径, not brand",
                    "minimal_required_specs": required_text,
                }
            )
        if str(row.get("brand") or "").strip() == "公元":
            warnings.append(
                {
                    "item_code": item_code,
                    "warning": "brand contains 公元; in this project 公元 means 公称, not brand",
                    "brand": str(row.get("brand") or ""),
                }
            )
        if any(default_term in str(row.get("standard_sku_name") or "") for default_term in ("普通直通", "普通弯头")):
            warnings.append(
                {
                    "item_code": item_code,
                    "warning": "standard_sku_name may still contain default wording",
                    "standard_sku_name": str(row.get("standard_sku_name") or ""),
                }
            )
    return {
        "input_count": len(input_item_codes),
        "output_count": len(output_codes),
        "missing": sorted(input_set - output_set),
        "extra": sorted(output_set - input_set),
        "duplicates": duplicates,
        "merge_marked_count": merged_count,
        "consistency_warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ask DeepSeek to trial SKU governance for one material name.")
    parser.add_argument("--input-json", type=Path, default=DEFAULT_INPUT_JSON)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--top-group", default="管材管件阀门")
    parser.add_argument("--material-family", default="直接/接头")
    parser.add_argument("--material-name", default="直接/直通")
    parser.add_argument("--dry-run", action="store_true", help="Only write the DeepSeek request payload, do not call API.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    skus = load_target_skus(
        args.input_json,
        top_group=args.top_group,
        material_family=args.material_family,
        material_name=args.material_name,
    )
    if not skus:
        raise SystemExit("No matching SKU rows found.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    request_path = args.output_dir / f"deepseek_sku_governance_request_{timestamp}.json"
    response_path = args.output_dir / f"deepseek_sku_governance_response_{timestamp}.json"
    tsv_path = args.output_dir / f"deepseek_sku_governance_rows_{timestamp}.tsv"

    messages = build_messages(
        top_group=args.top_group,
        material_family=args.material_family,
        material_name=args.material_name,
        skus=skus,
    )
    request_payload = {
        "input_json": str(args.input_json),
        "target": {
            "top_group": args.top_group,
            "material_family": args.material_family,
            "material_name": args.material_name,
            "sku_count": len(skus),
        },
        "messages": messages,
    }
    request_path.write_text(json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.dry_run:
        print(json.dumps({"dry_run": True, "sku_count": len(skus), "request": str(request_path)}, ensure_ascii=False, indent=2))
        return

    settings = load_deepseek_settings()
    result = call_deepseek_json(messages, settings=settings)
    validation = validate_result(result, [row["item_code"] for row in skus])
    result_with_meta = {
        "generated_at": timestamp,
        "model": settings.model,
        "target": request_payload["target"],
        "validation": validation,
        "result": result,
    }
    response_path.write_text(json.dumps(result_with_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    write_tsv(tsv_path, result.get("rows", []))

    print(
        json.dumps(
            {
                "sku_count": len(skus),
                "request": str(request_path),
                "response": str(response_path),
                "rows_tsv": str(tsv_path),
                "validation": validation,
                "summary": result.get("summary", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
