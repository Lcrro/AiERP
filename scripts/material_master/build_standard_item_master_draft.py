from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "material_purchase_2024"
DEFAULT_INPUT_PATH = DEFAULT_DATA_DIR / "standard_material_candidates_curated.tsv"
DEFAULT_DRAFT_PATH = DEFAULT_DATA_DIR / "standard_item_master_draft.tsv"
DEFAULT_DEDUPE_QUEUE_PATH = DEFAULT_DATA_DIR / "material_dedupe_review_queue.tsv"
DEFAULT_MISSING_QUESTIONS_PATH = DEFAULT_DATA_DIR / "material_missing_spec_questions.tsv"
DEFAULT_IMPORT_READY_PATH = DEFAULT_DATA_DIR / "material_import_ready_items.tsv"
DEFAULT_SUMMARY_PATH = DEFAULT_DATA_DIR / "standard_item_master_draft_summary.json"


INPUT_FIELDS = [
    "标准名称",
    "必填规格",
    "辅助规格",
    "标准分组",
    "标准单位",
    "别名/土名",
    "放行等级",
    "整理依据",
]

DRAFT_FIELDS = [
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

DEDUPE_FIELDS = [
    "issue_id",
    "issue_type",
    "severity",
    "review_status",
    "standard_name",
    "standard_group",
    "required_specs",
    "unit_values",
    "draft_sku_ids",
    "draft_item_codes",
    "candidate_count",
    "source_candidate_rows",
    "reason",
    "suggested_action",
]

MISSING_QUESTION_FIELDS = [
    "question_id",
    "draft_sku_id",
    "draft_item_code",
    "priority",
    "放行等级",
    "标准名称",
    "标准分组",
    "标准单位",
    "当前必填规格",
    "missing_specs",
    "question",
    "recommended_next_action",
    "source_candidate_rows",
    "整理依据",
]

IMPORT_READY_FIELDS = [
    "draft_sku_id",
    "draft_item_code",
    "import_status",
    "放行等级",
    "标准名称",
    "必填规格",
    "辅助规格",
    "标准分组",
    "标准单位",
    "别名/土名",
    "candidate_count",
    "source_candidate_rows",
    "confirmation_required",
    "confirmation_reason",
]

ALLOWED_GRADES = {"A", "B", "C", "D"}
GRADE_ORDER = {"A": 1, "B": 2, "C": 3, "D": 4}

UNIT_SYNONYMS = {
    "只": "个",
    "件": "个",
    "pc": "个",
    "pcs": "个",
    "nos": "个",
    "set": "套",
    "m": "米",
    "meter": "米",
    "metre": "米",
    "kg": "kg",
    "公斤": "kg",
    "千克": "kg",
    "t": "吨",
}

MISSING_SPEC_TERMS = [
    "品牌",
    "型号",
    "规格",
    "材质",
    "强度等级",
    "表面处理",
    "执行标准",
    "图号",
    "适用设备",
    "压力等级",
    "连接方式",
    "接口形式",
    "接头形式",
    "口径",
    "壁厚",
    "尺寸",
    "长度",
    "宽度",
    "厚度",
    "直径",
    "头型",
    "型式",
    "套件内容",
    "包装规格",
    "包装重量",
    "每包数量",
    "容量",
    "颜色",
    "色号",
    "功率",
    "电压",
    "电流",
    "量程",
    "精度",
    "流量",
    "扬程",
    "开孔尺寸",
    "锁体型号",
    "开向",
    "安全系数",
]

MISSING_MARKERS = (
    "缺",
    "缺失",
    "不明",
    "未明确",
    "未说明",
    "待补",
    "待确认",
    "需确认",
    "需要确认",
    "疑问",
    "无法",
)


@dataclass(frozen=True)
class CategoryRule:
    key: str
    label: str
    code_prefix: str
    patterns: tuple[str, ...]
    recommended_missing: tuple[str, ...]
    next_action: str


CATEGORY_RULES: tuple[CategoryRule, ...] = (
    CategoryRule(
        key="cement",
        label="水泥砂石",
        code_prefix="MAT-CEM",
        patterns=("水泥", "砂石", "黄沙", "石子"),
        recommended_missing=("类型", "强度等级", "包装重量", "品牌"),
        next_action="确认水泥/砂石的类型、强度等级、包装重量和品牌。",
    ),
    CategoryRule(
        key="tie",
        label="扎带",
        code_prefix="ELEC-TIE",
        patterns=("扎带",),
        recommended_missing=("规格", "材质", "颜色", "每包数量"),
        next_action="确认扎带规格、材质、颜色和每包数量。",
    ),
    CategoryRule(
        key="lock",
        label="锁具",
        code_prefix="HW-LOCK",
        patterns=("门锁", "锁扣", "锁芯", "挂锁", "电箱门锁", "锁具"),
        recommended_missing=("用途", "锁体型号", "开孔尺寸", "开向"),
        next_action="确认适用对象、锁体型号、开孔尺寸和开向。",
    ),
    CategoryRule(
        key="fastener",
        label="紧固件",
        code_prefix="FAST",
        patterns=("螺丝", "螺栓", "螺母", "螺杆", "丝杆", "膨胀", "垫片", "平垫", "弹垫"),
        recommended_missing=("规格", "材质", "强度等级", "头型", "表面处理"),
        next_action="确认规格、材质、强度等级、头型和表面处理。",
    ),
    CategoryRule(
        key="pipe_and_fitting",
        label="管材管件",
        code_prefix="PIPE",
        patterns=("管", "管件", "阀", "接头", "弯头", "三通", "法兰", "水带", "胶管", "堵头"),
        recommended_missing=("材质", "口径", "压力等级", "连接方式", "壁厚"),
        next_action="确认材质、口径、压力等级、连接方式和壁厚。",
    ),
    CategoryRule(
        key="electrical",
        label="电气材料",
        code_prefix="ELEC",
        patterns=("电气", "电箱", "开关", "插座", "断路器", "接线", "电缆", "电线", "灯", "按钮", "电磁阀", "端子"),
        recommended_missing=("品牌", "型号", "电压", "电流", "安装方式"),
        next_action="确认品牌、型号、电压/电流和安装或连接方式。",
    ),
    CategoryRule(
        key="tool",
        label="工具器具",
        code_prefix="TOOL",
        patterns=("工具", "钻头", "卷尺", "钳", "刷", "刀片", "扳手", "梯", "角磨机", "锤"),
        recommended_missing=("品牌", "型号", "规格", "尺寸", "适用设备"),
        next_action="确认品牌、型号/规格、尺寸和适用设备。",
    ),
    CategoryRule(
        key="metal",
        label="金属材料",
        code_prefix="METAL",
        patterns=("钢", "铁", "角钢", "方管", "槽钢", "钢板", "不锈钢", "铝合金", "钢丝绳"),
        recommended_missing=("材质", "规格", "厚度", "长度", "执行标准"),
        next_action="确认材质、规格尺寸、厚度/长度和执行标准。",
    ),
    CategoryRule(
        key="construction",
        label="工程建材",
        code_prefix="CONST",
        patterns=("模板", "砖", "板", "土工", "草皮", "脚手架", "架子管", "踢脚板"),
        recommended_missing=("材质", "尺寸", "厚度", "强度等级", "包装规格"),
        next_action="确认材质、尺寸、厚度、强度等级和包装规格。",
    ),
    CategoryRule(
        key="chemical",
        label="化工油漆胶粘",
        code_prefix="CHEM",
        patterns=("胶", "油漆", "漆", "涂料", "除锈剂", "堵漏剂", "清洗剂", "润滑", "黄油", "机油"),
        recommended_missing=("品牌", "型号", "类型", "容量", "颜色"),
        next_action="确认品牌/型号、类型、容量或包装规格和颜色。",
    ),
    CategoryRule(
        key="welding",
        label="焊接焊割",
        code_prefix="WELD",
        patterns=("焊", "割", "氧气", "乙炔", "焊条", "焊丝"),
        recommended_missing=("型号", "规格", "材质", "包装重量", "适用工艺"),
        next_action="确认型号、规格、材质、包装重量和适用工艺。",
    ),
    CategoryRule(
        key="safety",
        label="安防劳保",
        code_prefix="SAFE",
        patterns=("安全", "劳保", "手套", "眼镜", "反光", "消防", "灭火器", "警示", "防护"),
        recommended_missing=("类型", "材质", "规格", "安全等级", "认证标准"),
        next_action="确认类型、材质、规格、安全等级或认证标准。",
    ),
    CategoryRule(
        key="admin",
        label="行政办公与清洁",
        code_prefix="ADMIN",
        patterns=("办公", "清洁", "垃圾袋", "铅笔", "记号笔", "牙刷", "牙膏", "拖鞋", "床垫"),
        recommended_missing=("品牌", "规格", "包装规格", "材质"),
        next_action="确认品牌、规格、包装规格和材质。",
    ),
    CategoryRule(
        key="spare_part",
        label="设备备件与加工件",
        code_prefix="SPARE",
        patterns=("备件", "加工件", "轴承", "密封", "活塞", "泵", "滤芯", "皮带", "油封"),
        recommended_missing=("型号", "图号", "适用设备", "材质", "关键尺寸"),
        next_action="确认型号、图号、适用设备、材质和关键尺寸。",
    ),
)

DEFAULT_CATEGORY = CategoryRule(
    key="general",
    label="通用物料",
    code_prefix="MAT",
    patterns=(),
    recommended_missing=("规格", "型号", "材质", "品牌"),
    next_action="确认规格、型号、材质和品牌等关键建档信息。",
)


def normalize_for_key(value: str) -> str:
    text = unicodedata.normalize("NFKC", value or "")
    text = text.strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    text = text.replace("×", "x").replace("*", "x")
    return re.sub(r"\s+", "", text)


def normalize_unit(value: str) -> str:
    normalized = normalize_for_key(value)
    return UNIT_SYNONYMS.get(normalized, normalized)


def split_multi(value: str) -> list[str]:
    text = unicodedata.normalize("NFKC", value or "").strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*(?:[;；|,\n])\s*", text) if part.strip()]


def dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = (value or "").strip()
        if not text:
            continue
        key = normalize_for_key(text)
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def join_values(values: Iterable[str], separator: str = "；") -> str:
    return separator.join(dedupe_keep_order(values))


def normalize_specs_signature(specs: str) -> str:
    parts = split_multi(specs)
    normalized_parts: list[tuple[str, str]] = []
    for part in parts:
        if "：" in part:
            key, value = part.split("：", 1)
        elif ":" in part:
            key, value = part.split(":", 1)
        else:
            key, value = "规格", part
        normalized_parts.append((normalize_for_key(key), normalize_spec_value(value)))
    normalized_parts.sort()
    return "|".join(f"{key}:{value}" for key, value in normalized_parts)


def normalize_spec_value(value: str) -> str:
    text = normalize_for_key(value)

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


def spec_keys(specs: str) -> set[str]:
    keys: set[str] = set()
    for part in split_multi(specs):
        if "：" in part:
            key = part.split("：", 1)[0]
        elif ":" in part:
            key = part.split(":", 1)[0]
        else:
            key = "规格"
        keys.add(normalize_for_key(key))
    return keys


def worst_grade(grades: Iterable[str]) -> str:
    return max((grade for grade in grades if grade in GRADE_ORDER), key=lambda grade: GRADE_ORDER[grade])


def release_status_for_grade(grade: str) -> str:
    return {
        "A": "ready",
        "B": "needs_confirmation",
        "C": "needs_missing_specs",
        "D": "blocked",
    }[grade]


def import_decision_for_grade(grade: str) -> str:
    return {
        "A": "import_ready",
        "B": "confirm_then_import",
        "C": "do_not_import_missing_specs",
        "D": "do_not_import_blocked",
    }[grade]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != INPUT_FIELDS:
            raise ValueError(f"{path.name}: unexpected fields {reader.fieldnames}")
        rows = list(reader)
    for index, row in enumerate(rows, start=2):
        grade = row.get("放行等级", "")
        if grade not in ALLOWED_GRADES:
            raise ValueError(f"{path.name}:{index}: invalid grade {grade!r}")
        for field in ["标准名称", "必填规格", "标准分组", "标准单位", "放行等级"]:
            if not (row.get(field) or "").strip():
                raise ValueError(f"{path.name}:{index}: missing required field {field}")
    return rows


def write_tsv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def dedupe_key_for_row(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (
        normalize_for_key(row["标准名称"]),
        normalize_specs_signature(row["必填规格"]),
        normalize_for_key(row["标准分组"]),
        normalize_unit(row["标准单位"]),
    )


def match_category(row: dict[str, str]) -> CategoryRule:
    name = row.get("标准名称", "")
    group = row.get("标准分组", "")
    specs = row.get("必填规格", "") + "|" + row.get("辅助规格", "")
    aliases = row.get("别名/土名", "")
    best_rule = DEFAULT_CATEGORY
    best_score = 0
    for rule in CATEGORY_RULES:
        score = 0
        for pattern in rule.patterns:
            if pattern in group:
                score += 8
            if pattern in name:
                score += 4
            if pattern in specs:
                score += 2
            if pattern in aliases:
                score += 1
        if score > best_score:
            best_rule = rule
            best_score = score
    return best_rule


def extract_missing_specs(row: dict[str, str], category: CategoryRule) -> list[str]:
    basis = row.get("整理依据", "")
    combined_basis = basis + " " + row.get("辅助规格", "")
    present_keys = spec_keys(row.get("必填规格", "")) | spec_keys(row.get("辅助规格", ""))
    missing: list[str] = []

    for term in MISSING_SPEC_TERMS:
        term_key = normalize_for_key(term)
        if term_key in present_keys:
            continue
        term_index = combined_basis.find(term)
        if term_index == -1:
            continue
        window = combined_basis[max(0, term_index - 8) : term_index + len(term) + 12]
        if any(marker in window for marker in MISSING_MARKERS):
            missing.append(term)

    if missing:
        return dedupe_keep_order(missing)

    grade = row.get("放行等级", "")
    if grade in {"C", "D"}:
        return [term for term in category.recommended_missing if normalize_for_key(term) not in present_keys]
    if grade == "B" and basis:
        return [term for term in category.recommended_missing[:2] if normalize_for_key(term) not in present_keys]
    return []


def build_drafts(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, list[int]]]:
    grouped: dict[tuple[str, str, str, str], list[tuple[int, dict[str, str]]]] = defaultdict(list)
    for source_index, row in enumerate(rows, start=1):
        grouped[dedupe_key_for_row(row)].append((source_index, row))

    drafts: list[dict[str, str]] = []
    prefix_counts: Counter[str] = Counter()
    key_to_source_indexes: dict[str, list[int]] = {}

    for draft_index, (key, group_rows) in enumerate(grouped.items(), start=1):
        first = group_rows[0][1]
        category = match_category(first)
        prefix_counts[category.code_prefix] += 1
        grades = [row["放行等级"] for _, row in group_rows]
        grade = worst_grade(grades)
        aliases = []
        bases = []
        aux_specs = []
        source_indexes = []
        file_rows = []
        for source_index, row in group_rows:
            source_indexes.append(source_index)
            file_rows.append(source_index + 1)
            aliases.extend(split_multi(row.get("别名/土名", "")))
            aux_specs.extend(split_multi(row.get("辅助规格", "")))
            if row.get("整理依据"):
                bases.append(row["整理依据"])

        merged_row = {
            "标准名称": first["标准名称"],
            "必填规格": first["必填规格"],
            "辅助规格": join_values(aux_specs),
            "标准分组": first["标准分组"],
            "标准单位": first["标准单位"],
            "别名/土名": join_values(aliases),
            "放行等级": grade,
            "整理依据": join_values(bases),
        }
        missing_specs = extract_missing_specs(merged_row, category)
        draft_sku_id = f"SKU-DRAFT-{draft_index:06d}"
        draft_item_code = f"{category.code_prefix}-{prefix_counts[category.code_prefix]:06d}"
        dedupe_key = "|".join(key)
        grade_counts = Counter(grades)
        source_candidate_rows = ";".join(str(index) for index in source_indexes)
        key_to_source_indexes[dedupe_key] = source_indexes

        drafts.append(
            {
                "draft_sku_id": draft_sku_id,
                "draft_item_code": draft_item_code,
                "code_prefix": category.code_prefix,
                "release_status": release_status_for_grade(grade),
                "放行等级": grade,
                "标准名称": merged_row["标准名称"],
                "必填规格": merged_row["必填规格"],
                "辅助规格": merged_row["辅助规格"],
                "标准分组": merged_row["标准分组"],
                "标准单位": merged_row["标准单位"],
                "别名/土名": merged_row["别名/土名"],
                "candidate_count": str(len(group_rows)),
                "source_candidate_rows": source_candidate_rows,
                "source_file_rows": ";".join(str(index) for index in file_rows),
                "grade_counts": ";".join(f"{grade_key}:{grade_counts[grade_key]}" for grade_key in sorted(grade_counts)),
                "matched_category": category.label,
                "import_decision": import_decision_for_grade(grade),
                "missing_specs": join_values(missing_specs),
                "整理依据": merged_row["整理依据"],
                "dedupe_key": dedupe_key,
            }
        )

    return drafts, key_to_source_indexes


def build_dedupe_queue(drafts: list[dict[str, str]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    issue_index = 1

    for draft in drafts:
        if int(draft["candidate_count"]) <= 1:
            continue
        issues.append(
            {
                "issue_id": f"DEDUPE-{issue_index:05d}",
                "issue_type": "exact_duplicate_auto_merged",
                "severity": "low",
                "review_status": "auto_merged",
                "standard_name": draft["标准名称"],
                "standard_group": draft["标准分组"],
                "required_specs": draft["必填规格"],
                "unit_values": draft["标准单位"],
                "draft_sku_ids": draft["draft_sku_id"],
                "draft_item_codes": draft["draft_item_code"],
                "candidate_count": draft["candidate_count"],
                "source_candidate_rows": draft["source_candidate_rows"],
                "reason": "标准名称、必填规格、标准分组、标准单位完全一致，已在 SKU 草案中自动合并为一条。",
                "suggested_action": "抽样确认别名和整理依据，无需重复建档。",
            }
        )
        issue_index += 1

    by_without_unit: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for draft in drafts:
        by_without_unit[
            (
                normalize_for_key(draft["标准名称"]),
                normalize_specs_signature(draft["必填规格"]),
                normalize_for_key(draft["标准分组"]),
            )
        ].append(draft)

    for group in by_without_unit.values():
        units = {normalize_unit(draft["标准单位"]) for draft in group}
        if len(units) <= 1:
            continue
        issues.append(
            {
                "issue_id": f"DEDUPE-{issue_index:05d}",
                "issue_type": "unit_conflict_review",
                "severity": "high",
                "review_status": "needs_review",
                "standard_name": group[0]["标准名称"],
                "standard_group": group[0]["标准分组"],
                "required_specs": group[0]["必填规格"],
                "unit_values": join_values(draft["标准单位"] for draft in group),
                "draft_sku_ids": join_values(draft["draft_sku_id"] for draft in group),
                "draft_item_codes": join_values(draft["draft_item_code"] for draft in group),
                "candidate_count": str(sum(int(draft["candidate_count"]) for draft in group)),
                "source_candidate_rows": join_values(draft["source_candidate_rows"] for draft in group),
                "reason": "标准名称和必填规格相同，但单位不同，不能自动判断是否同一 SKU。",
                "suggested_action": "确认采购、库存和领用的基础单位，再决定合并或保留独立 SKU。",
            }
        )
        issue_index += 1

    alias_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    for draft in drafts:
        for alias in split_multi(draft["别名/土名"]):
            if len(normalize_for_key(alias)) < 2:
                continue
            alias_map[normalize_for_key(alias)].append(draft)

    for alias_key, group in alias_map.items():
        distinct_keys = {draft["dedupe_key"] for draft in group}
        if len(distinct_keys) <= 1:
            continue
        display_alias = split_multi(group[0]["别名/土名"])[0] if split_multi(group[0]["别名/土名"]) else alias_key
        issues.append(
            {
                "issue_id": f"DEDUPE-{issue_index:05d}",
                "issue_type": "alias_conflict_review",
                "severity": "medium",
                "review_status": "needs_review",
                "standard_name": display_alias,
                "standard_group": join_values(draft["标准分组"] for draft in group),
                "required_specs": join_values(draft["必填规格"] for draft in group),
                "unit_values": join_values(draft["标准单位"] for draft in group),
                "draft_sku_ids": join_values(draft["draft_sku_id"] for draft in group),
                "draft_item_codes": join_values(draft["draft_item_code"] for draft in group),
                "candidate_count": str(sum(int(draft["candidate_count"]) for draft in group)),
                "source_candidate_rows": join_values(draft["source_candidate_rows"] for draft in group),
                "reason": f"同一别名/土名 {display_alias!r} 指向多个 SKU 候选。",
                "suggested_action": "确认该别名是否可唯一指向某个 SKU；若不能唯一，检索时必须让用户补充规格。",
            }
        )
        issue_index += 1

    return issues


def build_missing_questions(drafts: list[dict[str, str]]) -> list[dict[str, str]]:
    questions: list[dict[str, str]] = []
    for index, draft in enumerate(drafts, start=1):
        grade = draft["放行等级"]
        if grade == "A":
            continue
        missing = split_multi(draft.get("missing_specs", ""))
        if not missing and grade == "B":
            continue
        category = match_category(
            {
                "标准名称": draft["标准名称"],
                "标准分组": draft["标准分组"],
                "必填规格": draft["必填规格"],
                "辅助规格": draft["辅助规格"],
                "别名/土名": draft["别名/土名"],
            }
        )
        if not missing:
            missing = list(category.recommended_missing)
        priority = "high" if grade in {"C", "D"} else "medium"
        question = f"请补充“{draft['标准名称']}”的{join_values(missing, '、')}。"
        questions.append(
            {
                "question_id": f"MISS-{index:06d}",
                "draft_sku_id": draft["draft_sku_id"],
                "draft_item_code": draft["draft_item_code"],
                "priority": priority,
                "放行等级": grade,
                "标准名称": draft["标准名称"],
                "标准分组": draft["标准分组"],
                "标准单位": draft["标准单位"],
                "当前必填规格": draft["必填规格"],
                "missing_specs": join_values(missing),
                "question": question,
                "recommended_next_action": category.next_action,
                "source_candidate_rows": draft["source_candidate_rows"],
                "整理依据": draft["整理依据"],
            }
        )
    return questions


def build_import_ready_items(drafts: list[dict[str, str]], dedupe_issues: list[dict[str, str]]) -> list[dict[str, str]]:
    blocked_draft_ids: set[str] = set()
    for issue in dedupe_issues:
        if issue["issue_type"] not in {"unit_conflict_review", "alias_conflict_review"}:
            continue
        blocked_draft_ids.update(split_multi(issue["draft_sku_ids"]))

    ready_rows: list[dict[str, str]] = []
    for draft in drafts:
        if draft["放行等级"] not in {"A", "B"}:
            continue
        if draft["draft_sku_id"] in blocked_draft_ids:
            continue
        import_status = "ready_to_import" if draft["放行等级"] == "A" else "confirm_then_import"
        ready_rows.append(
            {
                "draft_sku_id": draft["draft_sku_id"],
                "draft_item_code": draft["draft_item_code"],
                "import_status": import_status,
                "放行等级": draft["放行等级"],
                "标准名称": draft["标准名称"],
                "必填规格": draft["必填规格"],
                "辅助规格": draft["辅助规格"],
                "标准分组": draft["标准分组"],
                "标准单位": draft["标准单位"],
                "别名/土名": draft["别名/土名"],
                "candidate_count": draft["candidate_count"],
                "source_candidate_rows": draft["source_candidate_rows"],
                "confirmation_required": "否" if draft["放行等级"] == "A" else "是",
                "confirmation_reason": "" if draft["放行等级"] == "A" else draft["整理依据"],
            }
        )
    return ready_rows


def build_summary(
    source_count: int,
    drafts: list[dict[str, str]],
    dedupe_issues: list[dict[str, str]],
    questions: list[dict[str, str]],
    import_ready: list[dict[str, str]],
) -> dict[str, object]:
    draft_grade_counts = Counter(draft["放行等级"] for draft in drafts)
    source_grade_counts: Counter[str] = Counter()
    for draft in drafts:
        for part in split_multi(draft["grade_counts"]):
            if ":" not in part:
                continue
            grade, count = part.split(":", 1)
            source_grade_counts[grade] += int(count)
    issue_counts = Counter(issue["issue_type"] for issue in dedupe_issues)
    import_counts = Counter(row["import_status"] for row in import_ready)
    prefix_counts = Counter(draft["code_prefix"] for draft in drafts)
    return {
        "source_candidate_rows": source_count,
        "draft_sku_count": len(drafts),
        "auto_merged_duplicate_source_rows": source_count - len(drafts),
        "source_grade_counts": dict(sorted(source_grade_counts.items())),
        "draft_grade_counts": dict(sorted(draft_grade_counts.items())),
        "dedupe_issue_counts": dict(sorted(issue_counts.items())),
        "missing_question_count": len(questions),
        "import_ready_count": len(import_ready),
        "import_ready_counts": dict(sorted(import_counts.items())),
        "code_prefix_counts": dict(sorted(prefix_counts.items())),
    }


def build_outputs(input_path: Path) -> tuple[
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    list[dict[str, str]],
    dict[str, object],
]:
    source_rows = read_tsv(input_path)
    drafts, _ = build_drafts(source_rows)
    dedupe_issues = build_dedupe_queue(drafts)
    missing_questions = build_missing_questions(drafts)
    import_ready = build_import_ready_items(drafts, dedupe_issues)
    summary = build_summary(len(source_rows), drafts, dedupe_issues, missing_questions, import_ready)
    return drafts, dedupe_issues, missing_questions, import_ready, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build standard item master draft tables from curated material candidates.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--draft-output", type=Path, default=DEFAULT_DRAFT_PATH)
    parser.add_argument("--dedupe-output", type=Path, default=DEFAULT_DEDUPE_QUEUE_PATH)
    parser.add_argument("--missing-output", type=Path, default=DEFAULT_MISSING_QUESTIONS_PATH)
    parser.add_argument("--import-ready-output", type=Path, default=DEFAULT_IMPORT_READY_PATH)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_PATH)
    args = parser.parse_args()

    drafts, dedupe_issues, missing_questions, import_ready, summary = build_outputs(args.input)
    write_tsv(args.draft_output, DRAFT_FIELDS, drafts)
    write_tsv(args.dedupe_output, DEDUPE_FIELDS, dedupe_issues)
    write_tsv(args.missing_output, MISSING_QUESTION_FIELDS, missing_questions)
    write_tsv(args.import_ready_output, IMPORT_READY_FIELDS, import_ready)
    write_json(args.summary_output, summary)

    print(f"source rows: {summary['source_candidate_rows']}")
    print(f"draft sku rows: {summary['draft_sku_count']}")
    print(f"import ready rows: {summary['import_ready_count']}")
    print(f"missing question rows: {summary['missing_question_count']}")
    print(f"dedupe issue rows: {len(dedupe_issues)}")


if __name__ == "__main__":
    main()
