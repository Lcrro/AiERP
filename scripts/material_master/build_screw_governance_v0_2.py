from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TSV_PATH = ROOT / "data/material_master/reclassification/material_master_reclassified.tsv"
BROWSER_JSON_PATH = ROOT / "data/material_master/reclassification/material_master_browser_data_reclassified.json"
FAMILY_RULES_PATH = ROOT / "data/material_master/reclassification/family_governance/material_family_rules.tsv"
ISSUE_INVENTORY_PATH = ROOT / "data/material_master/governance_v0_2/material_governance_issue_inventory.tsv"
GOVERNANCE_SUMMARY_PATH = ROOT / "data/material_master/governance_v0_2/material_governance_summary.json"

OUT_DIR = ROOT / "data/material_master/governance_v0_2/screw"
CANDIDATES_TSV = OUT_DIR / "screw_governance_candidates.tsv"
FAMILY_GOVERNED_TSV = OUT_DIR / "screw_family_governed.tsv"
BOUNDARY_REVIEW_TSV = OUT_DIR / "screw_boundary_review.tsv"
SPEC_TEMPLATE_JSON = OUT_DIR / "screw_spec_template.json"
RULE_PROPOSALS_TSV = OUT_DIR / "screw_rule_proposals.tsv"
MANUAL_REVIEW_TSV = OUT_DIR / "screw_manual_review_queue.tsv"
SUMMARY_JSON = OUT_DIR / "screw_governance_summary.json"
PLAN_MD = ROOT / "docs/reference/material-governance-screw-v0.2.md"


CANDIDATE_FIELDS = [
    "scope_type",
    "source_reason",
    "item_code",
    "current_item_name",
    "current_family",
    "recommended_family",
    "recommended_item_name",
    "required_specs_normalized",
    "optional_specs_normalized",
    "stock_uom",
    "action",
    "confidence",
    "reason",
    "needs_owner_decision",
]

RULE_FIELDS = [
    "rule_type",
    "priority",
    "automation_level",
    "match_terms",
    "exclude_terms",
    "recommended_action",
    "target_family",
    "explanation",
    "examples",
]

MANUAL_REVIEW_FIELDS = [
    "item_code",
    "current_item_name",
    "current_family",
    "recommended_family",
    "action",
    "confidence",
    "review_reason",
    "missing_or_ambiguous_fields",
    "owner_question",
    "source_required_specs",
]

BOUNDARY_TERMS = [
    "螺丝",
    "螺栓",
    "螺母",
    "垫片",
    "垫圈",
    "平垫",
    "弹垫",
    "膨胀",
    "花篮",
    "花兰",
    "螺丝刀",
    "取出器",
    "套件",
    "组件",
    "套装",
    "螺杆",
    "通丝",
]

LONGEST_MATCH_BOUNDARY_TERMS = [
    "膨胀螺丝",
    "膨胀钩",
    "花篮螺丝",
    "花兰螺丝",
    "花篮螺栓",
    "花兰扣",
    "螺丝刀",
    "螺丝取出器",
    "断丝取出器",
    "通丝螺杆",
    "螺杆泵",
    "防松螺母",
    "平垫片",
    "弹簧垫片",
    "法兰垫片",
    "四氟垫片",
    "橡胶垫片",
    "异形垫片",
    "螺丝套件",
    "螺丝组件",
    "螺栓组件",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_inputs() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], dict]:
    tsv_rows = read_tsv(TSV_PATH)
    browser_data = json.loads(BROWSER_JSON_PATH.read_text(encoding="utf-8"))
    rows = browser_data["rows"]
    rules = read_tsv(FAMILY_RULES_PATH)
    issues = read_tsv(ISSUE_INVENTORY_PATH)
    summary = json.loads(GOVERNANCE_SUMMARY_PATH.read_text(encoding="utf-8"))
    if len(tsv_rows) != len(rows):
        raise RuntimeError(f"TSV/JSON row count mismatch: {len(tsv_rows)} vs {len(rows)}")
    return tsv_rows, rows, rules, issues, summary


def has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def parse_specs(text: str) -> dict[str, str]:
    specs: dict[str, str] = {}
    for part in re.split(r"[；;]", text or ""):
        part = part.strip()
        if not part:
            continue
        if "：" in part:
            key, value = part.split("：", 1)
        elif ":" in part:
            key, value = part.split(":", 1)
        else:
            continue
        specs[key.strip()] = value.strip()
    return specs


def normalize_spec_value(value: str) -> str:
    value = value.strip()
    value = value.replace("＊", "*").replace("×", "*").replace("X", "*")
    value = value.replace("全芽", "全牙")
    return value


def set_if_absent(specs: dict[str, str], key: str, value: str) -> None:
    if value and not specs.get(key):
        specs[key] = value


def normalize_specs(row: dict[str, str], action: str) -> tuple[str, str, list[str], list[str]]:
    source = parse_specs(row.get("required_specs", ""))
    normalized: dict[str, str] = {}
    optional: dict[str, str] = {}
    text = f"{row.get('item_name', '')} {row.get('aliases', '')} {row.get('required_specs', '')}"

    key_map = {
        "规格": "规格",
        "螺丝规格": "规格",
        "尺寸": "规格",
        "型号/规格": "规格",
        "直径": "直径",
        "长度": "长度",
        "类型": "类型",
        "头型": "头型/驱动",
        "槽型": "头型/驱动",
        "材质": "材质",
        "强度等级": "强度等级",
        "表面": "表面处理",
        "表面处理": "表面处理",
        "螺纹": "螺纹形式",
        "螺纹形式": "螺纹形式",
        "成套": "成套",
        "套件组成": "套件组成",
        "包含": "套件组成",
        "包装": "包装",
        "特征": "特征",
        "定制": "定制",
        "加工": "加工",
    }
    for key, value in source.items():
        target_key = key_map.get(key, key)
        clean_value = normalize_spec_value(value)
        if target_key == "类型":
            if clean_value in {"内六角", "六角", "十字", "一字", "圆头"}:
                target_key = "头型/驱动"
            elif clean_value in {"全牙", "全螺纹"}:
                target_key = "螺纹形式"
        if target_key in {"包装", "特征", "定制", "加工"}:
            optional[target_key] = clean_value
        else:
            normalized[target_key] = clean_value

    if "内六角" in text:
        set_if_absent(normalized, "头型/驱动", "内六角")
    elif "六角" in text:
        set_if_absent(normalized, "头型/驱动", "六角")
    if "十字" in text:
        set_if_absent(normalized, "头型/驱动", "十字")
    if "圆头" in text:
        set_if_absent(normalized, "头型/驱动", "圆头")
    if "T型" in text or "T形" in text:
        set_if_absent(normalized, "类型", "T型")
    if "鱼尾" in text:
        set_if_absent(normalized, "类型", "鱼尾")
    if "骑马" in text:
        set_if_absent(normalized, "类型", "骑马")
    if "自攻" in text:
        set_if_absent(normalized, "类型", "自攻")
    if "钻尾" in text:
        set_if_absent(normalized, "类型", "钻尾")
    if "不锈钢" in text:
        set_if_absent(normalized, "材质", "不锈钢")
    if "镀锌" in text:
        set_if_absent(normalized, "表面处理", "镀锌")
    if "高强度" in text:
        optional.setdefault("强度描述", "高强度")
    if "全牙" in text or "全螺纹" in text:
        set_if_absent(normalized, "螺纹形式", "全牙")
    if action == "keep_as_kit_review":
        set_if_absent(normalized, "成套", "是")

    missing: list[str] = []
    if action in {"keep_screw", "keep_as_kit_review"}:
        for field in ["规格", "材质", "头型/驱动", "强度等级"]:
            if not normalized.get(field):
                missing.append(field)
        if row.get("stock_uom") == "套" and action != "keep_as_kit_review" and not normalized.get("套件组成"):
            missing.append("套/包装口径")
        if action == "keep_as_kit_review" and not normalized.get("套件组成"):
            missing.append("套件组成")
    elif action == "move_to_expansion_anchor":
        for field in ["规格", "材质", "表面处理"]:
            if not normalized.get(field):
                missing.append(field)
    elif action == "move_to_turnbuckle":
        for field in ["规格", "材质", "端部形式", "额定载荷"]:
            if not normalized.get(field):
                missing.append(field)
    elif action in {"move_to_nut", "move_to_washer", "move_to_screw_rod"}:
        for field in ["规格", "材质"]:
            if not normalized.get(field):
                missing.append(field)

    normalized_text = "；".join(f"{key}：{value}" for key, value in normalized.items())
    optional_text = "；".join(f"{key}：{value}" for key, value in optional.items())
    return normalized_text, optional_text, missing, list(normalized)


def classify_row(row: dict[str, str]) -> tuple[str, str, str, str, str, bool]:
    name = row.get("item_name", "")
    aliases = row.get("aliases", "")
    text = f"{name} {aliases}"
    current_family = row.get("material_family", "")

    if "膨胀止水条" in text:
        return ("needs_manual_review", current_family, name, "medium", "包含膨胀但为止水条，必须作为膨胀锚栓规则排除。", True)
    if "膨胀螺丝" in text or "膨胀钩" in text or (("膨胀" in text) and current_family == "膨胀锚栓"):
        return ("move_to_expansion_anchor", "膨胀锚栓", "膨胀锚栓", "high", "膨胀螺丝/膨胀钩是锚固件，长词优先于普通螺丝。", False)
    if has_any(text, ["花篮螺丝", "花兰螺丝", "花篮螺栓", "花兰扣"]):
        return ("move_to_turnbuckle", "花篮螺丝", "花篮螺丝", "high", "花篮/花兰类是索具拉紧器，不归普通螺丝。", False)
    if "螺丝刀" in text or "取出器" in text:
        target = "螺丝取出器" if "取出器" in text else "螺丝刀"
        return ("move_to_tool", target, target, "high", "螺丝刀/取出器是工具，必须排除出螺丝族。", False)
    if current_family == "螺丝" and has_any(text, ["套件", "组件"]) or (
        current_family == "螺丝" and has_any(row.get("required_specs", ""), ["套件组成", "成套", "包含"])
    ):
        return ("keep_as_kit_review", "螺丝", "螺丝套件", "medium", "成套/组件 SKU 可能包含螺母、平垫、弹垫，不应轻易拆成普通螺丝。", True)
    if "螺杆泵" in text:
        return ("needs_manual_review", current_family, name, "medium", "螺杆泵是设备/备件语义，不应按螺杆或螺丝自动归类。", True)
    if "螺杆" in text or "通丝" in text or "丝杆" in text:
        return ("move_to_screw_rod", "螺杆", "螺杆", "high", "螺杆/通丝是独立紧固件族，和普通螺丝分开。", False)
    if "气管接头螺母" in text:
        return ("needs_manual_review", current_family, name, "medium", "螺母是气动接头部件，不应自动转普通螺母。", True)
    if "螺母" in text:
        return ("move_to_nut", "螺母", "螺母", "high", "螺母独立成族，不归普通螺丝。", False)
    if has_any(text, ["法兰垫片", "四氟垫片", "橡胶垫片", "异形垫片"]) or ("垫片" in text and has_any(text, ["定制", "加工"])):
        return ("needs_manual_review", current_family, name, "medium", "垫片跨标准垫圈、密封垫、法兰垫和定制件，需要按用途人工确认。", True)
    if has_any(text, ["垫片", "垫圈", "平垫", "弹垫", "弹簧垫片"]):
        return ("move_to_washer", "垫圈", "垫圈", "high", "标准平垫/弹垫/垫圈应从普通螺丝分开。", False)
    if has_any(text, ["套件", "组件", "套装"]) and current_family != "螺丝":
        return ("needs_manual_review", current_family, name, "medium", "非螺丝套件/组件只作为边界排除样本，不能按螺丝套件处理。", True)
    if current_family == "螺丝" or "螺丝" in text or "螺栓" in text:
        return ("keep_screw", "螺丝", "螺丝", "high", "普通螺丝/螺栓统一保留在螺丝族，头型、强度、材质等进入规格。", False)
    return ("needs_manual_review", current_family, name, "low", "命中边界词但不属于螺丝治理可自动判断范围。", True)


def owner_decision_needed(action: str, missing: list[str], row: dict[str, str]) -> bool:
    if action in {"keep_as_kit_review", "needs_manual_review"}:
        return True
    if action == "keep_screw":
        critical = {"规格", "材质", "头型/驱动", "强度等级", "套/包装口径"}
        return bool(critical.intersection(missing))
    if action in {"move_to_expansion_anchor", "move_to_turnbuckle", "move_to_tool", "move_to_screw_rod", "move_to_nut", "move_to_washer"}:
        return False
    return True


def build_candidate_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    universe: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        text = f"{row.get('item_name', '')} {row.get('aliases', '')}"
        if row.get("material_family") == "螺丝" or has_any(text, BOUNDARY_TERMS):
            if row["item_code"] not in seen:
                universe.append(row)
                seen.add(row["item_code"])

    candidates: list[dict[str, str]] = []
    manual_rows: list[dict[str, str]] = []
    for row in universe:
        action, target_family, target_name, confidence, reason, inherent_owner_decision = classify_row(row)
        required_normalized, optional_normalized, missing, normalized_keys = normalize_specs(row, action)
        scope_type, source_reason = determine_scope(row)
        needs_owner = inherent_owner_decision or owner_decision_needed(action, missing, row)
        if action == "keep_screw" and needs_owner and confidence == "high":
            confidence = "medium"
        if action in {"keep_as_kit_review", "needs_manual_review"}:
            needs_owner = True

        candidate = {
            "scope_type": scope_type,
            "source_reason": source_reason,
            "item_code": row["item_code"],
            "current_item_name": row.get("item_name", ""),
            "current_family": row.get("material_family", ""),
            "recommended_family": target_family,
            "recommended_item_name": target_name,
            "required_specs_normalized": required_normalized,
            "optional_specs_normalized": optional_normalized,
            "stock_uom": row.get("stock_uom", ""),
            "action": action,
            "confidence": confidence,
            "reason": reason,
            "needs_owner_decision": "yes" if needs_owner else "no",
        }
        candidates.append(candidate)

        if needs_owner:
            review_reason = reason
            if missing:
                review_reason = f"{review_reason}；缺失/不明确字段：{'、'.join(missing)}"
            owner_question = build_owner_question(candidate, missing, row)
            manual_rows.append(
                {
                    "item_code": row["item_code"],
                    "current_item_name": row.get("item_name", ""),
                    "current_family": row.get("material_family", ""),
                    "recommended_family": target_family,
                    "action": action,
                    "confidence": confidence,
                    "review_reason": review_reason,
                    "missing_or_ambiguous_fields": "；".join(missing),
                    "owner_question": owner_question,
                    "source_required_specs": row.get("required_specs", ""),
                }
            )

    candidates.sort(key=lambda item: (item["current_family"] != "螺丝", item["action"], item["item_code"]))
    manual_rows.sort(key=lambda item: (item["current_family"] != "螺丝", item["action"], item["item_code"]))
    return candidates, manual_rows


def determine_scope(row: dict[str, str]) -> tuple[str, str]:
    if row.get("material_family") == "螺丝":
        return "in_family", "current_family_is_screw"
    text = f"{row.get('item_name', '')} {row.get('aliases', '')}"
    matched_long = [term for term in LONGEST_MATCH_BOUNDARY_TERMS if term in text]
    if matched_long:
        return "boundary_sample", f"longest_match_boundary_term:{'|'.join(matched_long[:3])}"
    matched = [term for term in BOUNDARY_TERMS if term in text]
    if matched:
        return "boundary_sample", f"name_contains_screw_keyword:{'|'.join(matched[:3])}"
    return "boundary_sample", "boundary_context"


def build_owner_question(candidate: dict[str, str], missing: list[str], row: dict[str, str]) -> str:
    action = candidate["action"]
    if action == "keep_as_kit_review":
        return "请确认该 SKU 是否作为成套采购；套件是否包含螺母、平垫、弹垫及各自数量。"
    if action == "keep_screw":
        if row.get("stock_uom") == "套":
            return "请确认单位“套”是包装单位还是包含螺母/垫片的成套 SKU，并补齐材质、强度等级、头型/驱动。"
        return "请补齐材质、强度等级、头型/驱动、表面处理等会影响采购替代的字段。"
    if action == "needs_manual_review":
        return "请确认该物料的实物本体和目标物料族，避免被螺丝关键字误归类。"
    if action == "move_to_washer":
        return "请确认是标准垫圈/平垫/弹垫，还是密封、法兰或定制垫片。"
    if missing:
        return f"目标族基本明确，请补齐 {'、'.join(missing)}。"
    return "目标族基本明确，请业务确认是否接受该规则。"


def write_tsv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build_spec_template(rows: list[dict[str, str]], rules: list[dict[str, str]]) -> dict:
    screw_rows = [row for row in rows if row.get("material_family") == "螺丝"]
    spec_key_counts: Counter[str] = Counter()
    for row in screw_rows:
        spec_key_counts.update(parse_specs(row.get("required_specs", "")).keys())

    related_rules = [
        {
            "candidate_term": rule["candidate_term"],
            "decision": rule["decision"],
            "suggested_family": rule["suggested_family"],
            "split_rule": rule["split_rule"],
            "family_attributes": rule["family_attributes"],
        }
        for rule in rules
        if rule["candidate_term"] in {"螺丝", "螺栓", "自攻螺丝", "钻尾丝", "套件", "六角", "十字"}
    ]

    return {
        "generated_at": "2026-07-03",
        "scope": "material_family == 螺丝 plus screw boundary samples",
        "standard_name_policy": {
            "family_name": "螺丝",
            "standard_item_name": "螺丝",
            "kit_item_name": "螺丝套件",
            "policy": "普通螺丝/螺栓统一用螺丝作为标准名称；自攻、钻尾、鱼尾、骑马、六角、内六角、十字、圆头、高强度、全牙等进入规格属性或别名。膨胀螺丝、花篮/花兰螺丝、螺丝刀、取出器、螺杆、螺母、垫片/垫圈不归普通螺丝。",
            "keep_original_name_as_alias": True,
        },
        "required_fields": [
            {"field": "规格", "description": "优先使用 M径*长度 或 直径*长度；原始 8*30 等需确认是否为 M8*30。", "current_key_examples": ["规格", "螺丝规格"]},
            {"field": "头型/驱动", "description": "如六角、内六角、十字、一字、圆头、T型；当前数据常写在名称或 类型/头型 字段。", "current_key_examples": ["类型", "头型"]},
            {"field": "材质", "description": "如碳钢、不锈钢、304不锈钢等；当前大量缺失。", "current_key_examples": ["材质"]},
            {"field": "强度等级", "description": "如 8.8、10.9、12.9；普通螺丝缺失时会影响替代判断。", "current_key_examples": ["强度等级"]},
            {"field": "表面处理", "description": "如镀锌、发黑、本色；高强度或户外使用场景建议必填。", "current_key_examples": ["表面", "表面处理"]},
        ],
        "conditional_required_fields": [
            {"field": "螺纹形式", "when": "全牙、半牙、全螺纹等在名称或采购描述中出现", "current_key_examples": ["螺纹", "螺纹形式"]},
            {"field": "套件组成", "when": "item_name/aliases/stock_uom/规格中出现套件、组件、成套、包含、单位=套", "current_key_examples": ["套件组成", "成套", "包含"]},
            {"field": "包装数量", "when": "stock_uom 为盒、包、套但不是成套实物", "current_key_examples": ["包装"]},
            {"field": "是否定制/图纸号", "when": "名称或规格含加长、定制、加工", "current_key_examples": ["定制", "加工", "特征"]},
        ],
        "optional_fields": [
            "类型",
            "螺纹形式",
            "包装数量",
            "执行标准",
            "品牌",
            "用途/适配场景",
            "是否定制",
            "图纸号",
            "备注",
        ],
        "field_synonym_map": {
            "规格": ["规格", "螺丝规格", "尺寸", "型号/规格"],
            "头型/驱动": ["类型", "头型", "槽型", "驱动", "六角", "内六角", "十字", "一字", "圆头", "T型"],
            "材质": ["材质", "不锈钢", "304不锈钢", "碳钢"],
            "强度等级": ["强度等级", "等级", "高强度", "8.8", "10.9", "12.9"],
            "表面处理": ["表面", "表面处理", "镀锌", "发黑", "本色"],
            "螺纹形式": ["螺纹", "螺纹形式", "全牙", "全螺纹", "半牙"],
            "套件组成": ["套件组成", "成套", "包含", "配置", "平垫", "弹垫", "螺母"],
            "包装数量": ["包装", "每盒数量", "每包数量"],
        },
        "standard_uom_recommendation": {
            "ordinary_screw": "个/只作为最小实物单位；现有“套”需确认是成套还是包装单位。",
            "screw_kit": "套，仅在明确包含螺母/平垫/弹垫等组合件时使用。",
            "boxed_screw": "盒可以保留为采购单位，但必须补包装数量或转换关系。",
        },
        "fields_not_safe_to_auto_decide": [
            "原始 8*30、10*40 是否等同 M8*30、M10*40",
            "单位“套”是包装单位还是包含垫片/螺母的成套 SKU",
            "套件是否包含螺母、平垫、弹垫及数量",
            "材质缺失时是否可默认为碳钢",
            "强度等级缺失时是否可按历史常用等级处理",
            "不锈钢是否需要细分 201/304/316",
            "加长、定制类是否需要图纸号或加工标准",
        ],
        "current_screw_spec_key_counts": dict(spec_key_counts.most_common()),
        "related_existing_family_rules": related_rules,
    }


def build_rule_proposals(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    examples_by_action: dict[str, list[str]] = defaultdict(list)
    for item in candidates:
        label = f"{item['item_code']} {item['current_item_name']}"
        if label not in examples_by_action[item["action"]] and len(examples_by_action[item["action"]]) < 6:
            examples_by_action[item["action"]].append(label)

    rules = [
        {
            "rule_type": "longest_match_first",
            "priority": "P0",
            "automation_level": "auto_safe",
            "match_terms": "膨胀螺丝；膨胀钩",
            "exclude_terms": "膨胀止水条；膨胀剂；膨胀管材",
            "recommended_action": "move_to_expansion_anchor",
            "target_family": "膨胀锚栓",
            "explanation": "膨胀螺丝是锚固件，必须先于普通螺丝命中。",
            "examples": "；".join(examples_by_action["move_to_expansion_anchor"]),
        },
        {
            "rule_type": "longest_match_first",
            "priority": "P0",
            "automation_level": "auto_safe",
            "match_terms": "花篮螺丝；花兰螺丝；花篮螺栓；花兰扣",
            "exclude_terms": "普通螺丝；普通螺栓",
            "recommended_action": "move_to_turnbuckle",
            "target_family": "花篮螺丝",
            "explanation": "花篮/花兰类用于索具拉紧，归吊装索具，不归普通紧固螺丝。",
            "examples": "；".join(examples_by_action["move_to_turnbuckle"]),
        },
        {
            "rule_type": "exclude_tool",
            "priority": "P0",
            "automation_level": "auto_safe",
            "match_terms": "螺丝刀；十字螺丝刀；一字螺丝刀；绝缘螺丝刀；螺丝取出器；断丝取出器",
            "exclude_terms": "螺丝；螺栓；螺丝套件",
            "recommended_action": "move_to_tool",
            "target_family": "工具",
            "explanation": "螺丝刀和取出器是工具，不能被螺丝关键词吞掉。",
            "examples": "；".join(examples_by_action["move_to_tool"]),
        },
        {
            "rule_type": "sibling_family",
            "priority": "P0",
            "automation_level": "auto_safe",
            "match_terms": "螺杆；通丝螺杆；丝杆",
            "exclude_terms": "螺杆泵；泵水封；泵电机套装",
            "recommended_action": "move_to_screw_rod",
            "target_family": "螺杆",
            "explanation": "紧固用螺杆/通丝归螺杆族，螺杆泵语义必须排除。",
            "examples": "；".join(examples_by_action["move_to_screw_rod"]),
        },
        {
            "rule_type": "sibling_family",
            "priority": "P0",
            "automation_level": "auto_safe",
            "match_terms": "螺母；防松螺母；不锈钢螺母；高强度螺母",
            "exclude_terms": "气管接头螺母；接头螺母",
            "recommended_action": "move_to_nut",
            "target_family": "螺母",
            "explanation": "螺母独立成族；接头部件螺母按对应接头族复核。",
            "examples": "；".join(examples_by_action["move_to_nut"]),
        },
        {
            "rule_type": "sibling_family",
            "priority": "P0",
            "automation_level": "review_required",
            "match_terms": "平垫片；弹簧垫片；垫圈；垫片；平垫；弹垫",
            "exclude_terms": "法兰垫片；四氟垫片；橡胶垫片；异形垫片；定制垫片",
            "recommended_action": "move_to_washer",
            "target_family": "垫圈",
            "explanation": "标准平垫/弹垫归垫圈；密封、法兰、定制垫片进入人工确认。",
            "examples": "；".join(examples_by_action["move_to_washer"]),
        },
        {
            "rule_type": "kit_review",
            "priority": "P0",
            "automation_level": "owner_policy_required",
            "match_terms": "螺丝套件；螺丝组件；螺栓组件；成套；包含；平垫+弹垫；螺母",
            "exclude_terms": "电钻套装；劳动车轮胎套件；螺杆泵电机套装；接地桩套件",
            "recommended_action": "keep_as_kit_review",
            "target_family": "螺丝",
            "explanation": "成套 SKU 先保留成套属性并进入人工确认，不轻易拆成普通螺丝。",
            "examples": "；".join(examples_by_action["keep_as_kit_review"]),
        },
        {
            "rule_type": "base_screw",
            "priority": "P1",
            "automation_level": "review_required",
            "match_terms": "螺丝；螺栓；自攻螺丝；钻尾螺丝；鱼尾螺丝；骑马螺丝；内六角螺丝；六角螺丝；十字螺丝",
            "exclude_terms": "膨胀螺丝；花篮螺丝；花兰螺丝；螺丝刀；取出器；螺杆；螺母；垫片；垫圈；套件；组件",
            "recommended_action": "keep_screw",
            "target_family": "螺丝",
            "explanation": "排除 P0 长词后，普通螺丝/螺栓统一到螺丝族；头型、强度、材质和表面处理进入规格。",
            "examples": "；".join(examples_by_action["keep_screw"]),
        },
        {
            "rule_type": "attribute_extract",
            "priority": "P1",
            "automation_level": "review_required",
            "match_terms": "内六角；六角；十字；圆头；T型；自攻；钻尾；全牙；高强度；不锈钢；镀锌",
            "exclude_terms": "扳手；套筒；批头；直接；接头",
            "recommended_action": "keep_screw",
            "target_family": "螺丝",
            "explanation": "这些词在螺丝族内作为头型/驱动、类型、螺纹形式、材质或表面处理属性，不单独建族。",
            "examples": "FAST-000075 内六角螺栓；FAST-000104 钻尾螺丝；FAST-000108 高强度全牙螺丝",
        },
    ]
    return rules


def build_summary(candidates: list[dict[str, str]], manual_rows: list[dict[str, str]], rows: list[dict[str, str]]) -> dict:
    screw_rows = [row for row in rows if row.get("material_family") == "螺丝"]
    boundary_rows = [
        row
        for row in rows
        if row.get("material_family") == "螺丝" or has_any(f"{row.get('item_name', '')} {row.get('aliases', '')}", BOUNDARY_TERMS)
    ]
    action_counts = Counter(item["action"] for item in candidates)
    scope_counts = Counter(item["scope_type"] for item in candidates)
    confidence_counts = Counter(item["confidence"] for item in candidates)
    owner_count = sum(1 for item in candidates if item["needs_owner_decision"] == "yes")
    focus_candidates = [item for item in candidates if item["current_family"] == "螺丝"]
    focus_owner = sum(1 for item in focus_candidates if item["needs_owner_decision"] == "yes")
    safe_rule_candidates = [
        item
        for item in candidates
        if item["confidence"] == "high"
        and item["action"]
        in {
            "move_to_expansion_anchor",
            "move_to_turnbuckle",
            "move_to_tool",
            "move_to_screw_rod",
            "move_to_nut",
            "move_to_washer",
        }
    ]
    focus_safe_keep = [
        item
        for item in focus_candidates
        if item["action"] == "keep_screw" and item["confidence"] in {"high", "medium"}
    ]
    standard_ready = [
        item
        for item in focus_candidates
        if item["action"] == "keep_screw"
        and item["needs_owner_decision"] == "no"
        and all(field in item["required_specs_normalized"] for field in ["规格：", "材质：", "头型/驱动：", "强度等级："])
    ]

    return {
        "generated_at": "2026-07-03",
        "source_files": {
            "material_master_reclassified": str(TSV_PATH.relative_to(ROOT)),
            "browser_json": str(BROWSER_JSON_PATH.relative_to(ROOT)),
            "family_rules": str(FAMILY_RULES_PATH.relative_to(ROOT)),
            "issue_inventory": str(ISSUE_INVENTORY_PATH.relative_to(ROOT)),
            "governance_summary": str(GOVERNANCE_SUMMARY_PATH.relative_to(ROOT)),
        },
        "input_sku_count": len(screw_rows),
        "input_screw_family_rows": len(screw_rows),
        "boundary_sample_count": len(boundary_rows),
        "boundary_sample_rows": scope_counts.get("boundary_sample", 0),
        "candidate_row_count": len(candidates),
        "total_candidate_rows": len(candidates),
        "manual_review_row_count": len(manual_rows),
        "manual_review_rows": len(manual_rows),
        "action_counts": dict(action_counts),
        "scope_counts": dict(scope_counts),
        "confidence_distribution": dict(confidence_counts),
        "needs_owner_decision_count": owner_count,
        "owner_decision_rows": owner_count,
        "focus_screw_needs_owner_decision_count": focus_owner,
        "safe_auto_rule_candidate_count": len(safe_rule_candidates),
        "safe_auto_rule_count": len(safe_rule_candidates),
        "safe_auto_rule_candidate_ratio": round(len(safe_rule_candidates) / len(candidates), 4) if candidates else 0,
        "safe_auto_rule_ratio": round(len(safe_rule_candidates) / len(candidates), 4) if candidates else 0,
        "estimated_can_promote_to_usable_after_rule_and_owner_confirmation": len(focus_safe_keep),
        "estimated_can_promote_to_standard_without_more_specs": len(standard_ready),
        "remaining_manual_review_count": len(manual_rows),
        "top_manual_review_actions": dict(Counter(item["action"] for item in manual_rows).most_common()),
        "recommended_first_application_sequence": [
            "先把 P0 长词排除规则固化为候选规则：膨胀螺丝、花篮/花兰螺丝、螺丝刀/取出器、螺杆、螺母、垫片/垫圈。",
            "再处理普通螺丝/螺栓的标准名称统一：标准名称=螺丝，头型/强度/材质/表面处理进入规格。",
            "最后由业务确认所有套件/组件和单位为套的记录，决定是保留成套 SKU 还是拆分/换单位。",
        ],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown(summary: dict) -> None:
    action_counts = summary["action_counts"]
    lines = [
        "# 螺丝族治理样板 v0.2",
        "",
        "## 1. 范围和边界",
        "",
        f"本样板只生成治理候选，不改正式主表、不写 ERPNext、不改浏览器 HTML/JSON。它不是最终导入表。候选表共 {summary['total_candidate_rows']} 行，其中 `scope_type=in_family` 是当前物料族本来就是“螺丝”的 {summary['input_screw_family_rows']} 条，`scope_type=boundary_sample` 是被螺丝、螺栓、螺母、垫片、膨胀、花篮/花兰、螺丝刀、取出器、套件/组件等关键词带入的边界样本 {summary['boundary_sample_rows']} 条。",
        "",
        "螺丝族的边界原则：普通螺丝/螺栓可以统一到“螺丝”族；膨胀螺丝归膨胀锚栓；花篮/花兰螺丝归索具拉紧器；螺丝刀和取出器归工具；螺母、垫片/垫圈、螺杆分开；套件/组件先保留成套属性并进入人工确认。",
        "",
        "## 2. action 统计",
        "",
        "| action | 数量 |",
        "|---|---:|",
    ]
    for action, count in sorted(action_counts.items(), key=lambda item: item[0]):
        lines.append(f"| {action} | {count} |")

    lines.extend(
        [
            "",
            "## 3. 标准名称规则",
            "",
            "- 普通螺丝、普通螺栓、自攻螺丝、钻尾螺丝、鱼尾螺丝、骑马螺丝：标准名称建议统一为“螺丝”。",
            "- 内六角、六角、十字、圆头、T型、自攻、钻尾、全牙、高强度、不锈钢、镀锌：不作为族名，进入规格属性或搜索别名。",
            "- 螺丝套件、螺丝组件、螺栓组件：标准名称建议为“螺丝套件”，但必须确认套件组成。",
            "- 原始 item_name 保留在别名/搜索词中，便于历史采购检索。",
            "",
            "## 4. 规格模板",
            "",
            "螺丝族建议必填字段：规格、头型/驱动、材质、强度等级、表面处理。条件必填字段包括螺纹形式、套件组成、包装数量、是否定制/图纸号。字段映射详见 `data/material_master/governance_v0_2/screw/screw_spec_template.json`。",
            "",
            "当前数据最常见的问题是：规格有但未确认是否为 M 制；材质、强度等级、头型/驱动、表面处理缺失；单位“套”与真正的套件/组件混在一起。",
            "",
            "## 5. 可以规则/脚本处理",
            "",
            "- P0 长词优先：膨胀螺丝、花篮/花兰螺丝、螺丝刀/取出器、螺杆、螺母、垫片/垫圈先于普通螺丝命中。",
            "- 属性抽取：内六角、六角、十字、圆头、自攻、钻尾、全牙、不锈钢、镀锌可抽成候选属性。",
            "- 字段同义词：螺丝规格/规格、头型/类型、表面/表面处理、包含/套件组成可规则归一。",
            "- 标准名称候选：普通螺丝/螺栓统一成“螺丝”，套件/组件统一成“螺丝套件”候选。",
            "",
            "## 6. 必须人工确认",
            "",
            "- 单位“套”是包装单位，还是包含螺母、平垫、弹垫的成套 SKU。",
            "- 螺丝组件/套件是否作为独立成套 SKU 管理，是否允许拆分为螺丝、螺母、垫片。",
            "- 原始 8*30、10*40、14*50 等规格是否等同 M8*30、M10*40、M14*50。",
            "- 材质缺失时是否可默认碳钢，强度等级缺失时是否可默认历史常用等级。",
            "- 不锈钢是否需要细分 201/304/316；高强度、加长、定制类是否需要图纸号。",
            "",
            "## 7. 下一步如何应用到正式主表",
            "",
            "1. 先由负责人验收 `screw_rule_proposals.tsv` 中 P0 规则，确认边界词和排除词。",
            "2. 对 `screw_manual_review_queue.tsv` 逐行补齐人工答案，特别是套件组成、单位口径、材质和强度等级。",
            "3. 生成下一版候选修正表，包含标准名称、目标物料族、规格字段、单位建议和质量等级建议。",
            "4. 经业务确认后，再由正式导入流程更新主表；本样板本身不直接写 ERPNext。",
            "",
            "## 8. 如何复用到其他物料族",
            "",
            "这套样板可以复用于后续高优先级物料族，但每个族都必须保留 `scope_type` 和拆分表，避免把边界样本误当成族内物料。",
            "",
            "- 液压接头：`in_family` 为当前液压接头；`boundary_sample` 应纳入高压接头、油管接头、对丝、铜接头、气动接头、消防接头、直接/接头。规则重点是液压/气动/水暖/消防/定制加工边界，owner policy 重点是高压是否足以判定液压。",
            "- 钻头：`in_family` 为当前钻头；`boundary_sample` 应纳入冲击钻、钻夹头、钻尾螺丝、批头、开孔器。规则重点是钻头本体与工具整机/附件边界，模板重点是直径、长度、柄型、适用材质。",
            "- 管件：`in_family` 可按直接/接头、弯头、三通等分别治理；`boundary_sample` 应纳入液压接头、气动接头、消防接头、法兰、卡箍、定制管路接头。规则重点是系统归属、材质、连接方式和口径。",
            "- 手套：`in_family` 为当前手套；`boundary_sample` 应纳入扳手套筒、手套箱、手套机等误命中词。规则重点是劳保手套本体与设备/工具词排除，模板重点是材质、工艺、防护用途、尺码、厚度和长度。",
            "",
            "复用流程建议：先定义族内样本和边界关键词，再产出候选全集、族内治理表、边界复核表、规格模板、规则提案、人工队列和 summary；最后再进入业务确认。",
            "",
            "## 9. 本轮产物",
            "",
            "- `data/material_master/governance_v0_2/screw/screw_governance_candidates.tsv`",
            "- `data/material_master/governance_v0_2/screw/screw_family_governed.tsv`",
            "- `data/material_master/governance_v0_2/screw/screw_boundary_review.tsv`",
            "- `data/material_master/governance_v0_2/screw/screw_spec_template.json`",
            "- `data/material_master/governance_v0_2/screw/screw_rule_proposals.tsv`",
            "- `data/material_master/governance_v0_2/screw/screw_manual_review_queue.tsv`",
            "- `data/material_master/governance_v0_2/screw/screw_governance_summary.json`",
        ]
    )
    PLAN_MD.parent.mkdir(parents=True, exist_ok=True)
    PLAN_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    _tsv_rows, rows, rules, _issues, _summary = load_inputs()
    candidates, manual_rows = build_candidate_rows(rows)
    family_candidates = [item for item in candidates if item["scope_type"] == "in_family"]
    boundary_candidates = [item for item in candidates if item["scope_type"] == "boundary_sample"]
    rule_proposals = build_rule_proposals(candidates)
    spec_template = build_spec_template(rows, rules)
    screw_summary = build_summary(candidates, manual_rows, rows)

    write_tsv(CANDIDATES_TSV, CANDIDATE_FIELDS, candidates)
    write_tsv(FAMILY_GOVERNED_TSV, CANDIDATE_FIELDS, family_candidates)
    write_tsv(BOUNDARY_REVIEW_TSV, CANDIDATE_FIELDS, boundary_candidates)
    write_json(SPEC_TEMPLATE_JSON, spec_template)
    write_tsv(RULE_PROPOSALS_TSV, RULE_FIELDS, rule_proposals)
    write_tsv(MANUAL_REVIEW_TSV, MANUAL_REVIEW_FIELDS, manual_rows)
    write_json(SUMMARY_JSON, screw_summary)
    write_markdown(screw_summary)

    print(f"wrote {CANDIDATES_TSV}")
    print(f"wrote {FAMILY_GOVERNED_TSV}")
    print(f"wrote {BOUNDARY_REVIEW_TSV}")
    print(f"wrote {SPEC_TEMPLATE_JSON}")
    print(f"wrote {RULE_PROPOSALS_TSV}")
    print(f"wrote {MANUAL_REVIEW_TSV}")
    print(f"wrote {SUMMARY_JSON}")
    print(f"wrote {PLAN_MD}")


if __name__ == "__main__":
    main()
