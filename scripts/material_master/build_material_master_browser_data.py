from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_PATH = REPO_ROOT / "data" / "material_master" / "material_master.tsv"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "data" / "material_master" / "material_master_browser_data.json"
DEFAULT_FAMILY_RULES_PATH = (
    REPO_ROOT
    / "data"
    / "material_master"
    / "reclassification"
    / "family_governance"
    / "material_family_rules.tsv"
)

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

FAMILY_RULE_FIELDS = [
    "domain",
    "candidate_term",
    "decision",
    "suggested_family",
    "split_rule",
    "family_attributes",
    "include_examples",
    "exclude_examples",
    "priority",
    "confidence",
    "reason",
]

DOMAIN_ALIASES = {
    "劳保防护": {"劳保防护", "劳保耗材", "劳保用品", "劳保", "安全防护", "安全设施"},
    "包装覆盖周转": {"包装覆盖周转", "包装材料", "覆盖材料", "建筑周转材料"},
    "化工胶粘涂料": {"化工胶粘涂料", "化工耗材", "化工材料", "化工辅料", "胶粘剂", "油漆涂料", "密封材料"},
    "吊装索具": {"吊装索具", "绳索", "物流搬运"},
    "安全消防": {"安全消防", "消防材料", "消防器材", "安全设施", "安全标识"},
    "工具耗材": {"工具耗材", "工具", "工具备件", "磨具磨料", "涂装工具"},
    "工具量具": {"工具量具", "工具器具", "手动工具", "量具", "施工工具", "工具"},
    "紧固件与连接件": {"紧固件与连接件", "紧固件", "五金", "五金耗材", "五金备件", "管道紧固"},
    "管材管件阀门": {"管材管件阀门", "管件", "管材", "阀门", "PPR管件", "PPR管材", "管道耗材", "水暖五金"},
    "液压气动": {"液压气动", "液压", "气动", "气动元件", "气动液压"},
    "定制加工件": {"定制加工件", "定制件", "加工件"},
    "电气电料": {"电气电料", "电气材料", "电气耗材", "电气", "绝缘材料"},
    "弱电安防": {"弱电安防", "通信设备", "通讯设备", "自动化"},
    "焊接切割": {"焊接切割", "焊接耗材", "焊割耗材", "焊接工具", "焊割工具", "焊割设备", "焊接材料"},
    "电动气动工具": {"电动气动工具", "电动工具", "气动工具"},
    "金属材料": {"金属材料", "钢材", "原材料", "板材"},
    "建筑材料": {"建筑材料", "建材", "工程材料", "建筑施工耗材", "建筑装饰材料", "装修材料"},
    "清洁办公后勤": {
        "清洁办公后勤",
        "行政后勤",
        "办公用品",
        "办公耗材",
        "办公生活用品",
        "清洁用品",
        "清洁耗材",
        "清洁工具",
        "清洁化学品",
    },
}


def read_master(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != MASTER_FIELDS:
            raise ValueError(f"{path}: unexpected fields {reader.fieldnames}")
        return list(reader)


def read_family_rules(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != FAMILY_RULE_FIELDS:
            raise ValueError(f"{path}: unexpected fields {reader.fieldnames}")
        return sorted(list(reader), key=family_rule_sort_key)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def split_group(item_group: str) -> tuple[str, str]:
    parts = [part.strip() for part in (item_group or "").split("/") if part.strip()]
    if not parts:
        return "未分组", "未分组"
    if len(parts) == 1:
        return parts[0], parts[0]
    return parts[0], parts[1]


def build_search_text(row: dict[str, str]) -> str:
    return " ".join(
        value
        for value in [
            row["item_code"],
            row["item_name"],
            row["required_specs"],
            row["optional_specs"],
            row["item_group"],
            row["stock_uom"],
            row["aliases"],
            row["search_keywords"],
            row["brand"],
            row["model"],
        ]
        if value
    ).lower()


def pick_first(text: str, candidates: list[str]) -> str:
    for candidate in candidates:
        if candidate in text:
            return candidate
    return ""


def split_terms(value: str) -> list[str]:
    return [term.strip() for term in (value or "").replace(";", "；").split("；") if term.strip()]


def build_rule_text(row: dict[str, str]) -> str:
    return " ".join(
        value
        for value in [
            row["item_name"],
            row["required_specs"],
            row["optional_specs"],
            row["item_group"],
            row["aliases"],
            row["search_keywords"],
            row["brand"],
            row["model"],
        ]
        if value
    )


def build_name_rule_text(row: dict[str, str]) -> str:
    return row["item_name"]


def field_append(existing: str, value: str) -> str:
    if not value:
        return existing
    values = split_terms(existing)
    for item in split_terms(value):
        if item not in values:
            values.append(item)
    return "；".join(values)


def domain_tokens(domain: str) -> set[str]:
    tokens: set[str] = set()
    for token in split_terms(domain):
        tokens.add(token)
        tokens.update(DOMAIN_ALIASES.get(token, set()))
    return tokens


def domain_matches(row: dict[str, str], domain: str) -> bool:
    tokens = domain_tokens(domain)
    if not tokens:
        return True
    top_group, _ = split_group(row["item_group"])
    return any(token == top_group or row["item_group"].startswith(f"{token}/") or token in row["item_group"] for token in tokens)


def rule_text_has_any(text: str, terms: list[str]) -> bool:
    return any(term and term in text for term in terms)


def rule_is_excluded(row: dict[str, str], rule: dict[str, str]) -> bool:
    text = build_rule_text(row)
    excludes = split_terms(rule["exclude_examples"])
    candidate_term = rule["candidate_term"].strip()
    exact_terms = {row["item_name"].strip(), *split_terms(row["aliases"])}
    for exclude in excludes:
        if exclude in exact_terms:
            return True
        if len(exclude) >= max(3, len(candidate_term)) and exclude in text:
            return True
    return False


def rule_matches(row: dict[str, str], rule: dict[str, str]) -> bool:
    if rule["decision"] == "reject":
        return False
    if rule_is_excluded(row, rule):
        return False
    if not domain_matches(row, rule["domain"]):
        return False

    text = build_name_rule_text(row)
    candidate_term = rule["candidate_term"].strip()
    include_examples = split_terms(rule["include_examples"])
    return bool(candidate_term and candidate_term in text) or rule_text_has_any(text, include_examples)


def family_rule_sort_key(rule: dict[str, str]) -> tuple[int, int, int, int, str]:
    priority_rank = {"P0": 0, "P1": 1, "P2": 2}.get(rule.get("priority", ""), 9)
    decision_rank = {"solidify": 0, "split": 1, "attribute_only": 2, "reject": 9}.get(rule.get("decision", ""), 9)
    confidence_rank = {"high": 0, "medium": 1, "low": 2}.get(rule.get("confidence", ""), 9)
    return (
        priority_rank,
        decision_rank,
        confidence_rank,
        -len(rule.get("candidate_term", "")),
        rule.get("candidate_term", ""),
    )


def base_family_fields(item_name: str) -> dict[str, str]:
    return {
        "material_family": item_name,
        "family_rule": "",
        "family_note": "",
        "family_type": "",
        "family_material": "",
        "family_use": "",
        "family_connection": "",
        "family_surface": "",
        "family_attributes": "",
        "family_split_candidates": "",
        "family_attribute_terms": "",
        "drill_material": "",
        "drill_use_type": "",
        "drill_shank": "",
    }


def derive_material_family_legacy(row: dict[str, str]) -> dict[str, str]:
    item_name = row["item_name"]
    item_group = row["item_group"]
    text = " ".join(
        value
        for value in [
            row["item_name"],
            row["required_specs"],
            row["optional_specs"],
            row["aliases"],
            row["search_keywords"],
        ]
        if value
    )
    base = base_family_fields(item_name)

    if item_group == "工具耗材/钻头" and ("钻头" in item_name or "开孔器" in item_name):
        drill_material = ""
        drill_use_type = ""
        drill_shank = ""

        if "合金" in text:
            drill_material = "合金"
        elif "钨钢" in text:
            drill_material = "钨钢"
        elif "高速钢" in text:
            drill_material = "高速钢"

        if "冲击" in text:
            drill_use_type = "冲击钻"
        elif "麻花" in text:
            drill_use_type = "麻花钻"
        elif "铣刀" in text:
            drill_use_type = "铣刀"
        elif "宝塔" in text or "开孔器" in text:
            drill_use_type = "宝塔钻/开孔器"

        if "五坑" in text or "五孔" in text:
            drill_shank = "五坑"
        elif "二坑二槽" in text:
            drill_shank = "二坑二槽"
        elif "二坑三槽" in text:
            drill_shank = "二坑三槽"
        elif "方柄" in text:
            drill_shank = "方柄"
        elif "圆柄" in text:
            drill_shank = "圆柄"

        if "宝塔" in text or "开孔器" in item_name:
            family = "开孔器"
            family_note = "钻头专项样板：宝塔钻/开孔器从普通钻头族拆出"
        elif "铣刀" in text:
            family = "铣刀钻头"
            family_note = "钻头专项样板：铣刀钻头暂独立成族，后续复核是否并入铣刀"
        else:
            family = "钻头"
            family_note = "钻头专项样板：冲击、合金、钨钢、五坑等进入物料族属性"

        return {
            **base,
            "material_family": family,
            "family_rule": "drill_family_v0.1",
            "family_note": family_note,
            "family_type": drill_use_type,
            "family_material": drill_material,
            "drill_material": drill_material,
            "drill_use_type": drill_use_type,
            "drill_shank": drill_shank,
        }

    if item_group.startswith("紧固件与连接件/"):
        fastener_material = pick_first(text, ["304不锈钢", "不锈钢", "镀锌", "高强度"])
        fastener_type = pick_first(
            text,
            ["内六角", "六角自攻", "六角", "鱼尾", "骑马", "自攻", "防松", "膨胀钩", "膨胀螺丝"],
        )
        strength = pick_first(text, ["12.9级", "10.9级", "8.8级"])
        family = item_name
        note = "紧固件专项样板：同族物料按头型、强度、材质、规格区分 SKU"

        if item_group == "紧固件与连接件/膨胀锚栓":
            family = "膨胀锚栓"
            note = "紧固件专项样板：膨胀螺丝、爆炸螺丝、膨胀钩统一为膨胀锚栓族"
        elif item_group == "紧固件与连接件/螺丝":
            family = "螺丝"
            note = "紧固件专项样板：内六角、六角、鱼尾、骑马等作为螺丝族属性"
        elif item_group == "紧固件与连接件/螺母":
            family = "螺母"
        elif item_group in {"紧固件与连接件/垫圈", "紧固件与连接件/垫片"}:
            family = "垫圈/垫片"
        elif item_group == "紧固件与连接件/螺杆":
            family = "螺杆"
        elif item_group == "紧固件与连接件/管卡":
            family = "管卡"

        return {
            **base,
            "material_family": family,
            "family_rule": "fastener_family_v0.1",
            "family_note": note,
            "family_type": fastener_type,
            "family_material": fastener_material,
            "family_surface": strength,
        }

    if item_group == "劳保防护/手套" and "手套" in item_name:
        glove_type = pick_first(
            text,
            ["帆布", "乳胶", "牛筋", "挂胶", "焊工", "电焊", "全胶", "橡胶", "浸胶", "浸塑", "胶手套", "布"],
        )
        glove_use = "焊接防护" if ("焊" in text or "电焊" in text) else ""
        return {
            **base,
            "material_family": "手套",
            "family_rule": "glove_family_v0.1",
            "family_note": "劳保专项样板：帆布、乳胶、牛筋、焊工等作为手套族属性",
            "family_type": glove_type,
            "family_material": glove_type if glove_type not in {"焊工", "电焊", "挂胶", "浸胶", "浸塑"} else "",
            "family_use": glove_use,
        }

    if item_group.startswith("管材管件阀门/"):
        pipe_material = pick_first(text, ["不锈钢", "镀锌", "UPVC", "PVC", "PPR", "PE", "铜", "金属"])
        pipe_connection = pick_first(text, ["内牙", "外牙", "焊接", "热熔", "法兰", "卡箍", "丝牙"])
        pipe_type = pick_first(
            text,
            ["过桥弯", "45度", "斜三通", "Y型三通", "异径", "补心", "直通", "弯头", "三通", "阀门", "堵头", "法兰"],
        )
        family = item_name
        note = "管材管件专项样板：材质、连接方式、角度、异径等作为族内属性"
        if item_group == "管材管件阀门/管材":
            family = "管材"
        elif item_group == "管材管件阀门/弯头":
            family = "弯头"
        elif item_group == "管材管件阀门/三通":
            family = "三通"
        elif item_group in {"管材管件阀门/直接", "管材管件阀门/异径接头"}:
            family = "直接/接头"
        elif item_group == "管材管件阀门/阀门":
            family = "阀门"
        elif item_group == "管材管件阀门/法兰":
            family = "法兰"
        elif item_group == "管材管件阀门/堵头":
            family = "堵头"

        return {
            **base,
            "material_family": family,
            "family_rule": "pipe_family_v0.1",
            "family_note": note,
            "family_type": pipe_type,
            "family_material": pipe_material,
            "family_connection": pipe_connection,
        }

    if item_group in {"液压气动/液压接头", "液压气动/气动接头", "定制加工件/管路接头"}:
        connection_type = pick_first(text, ["卡套", "卡扣", "自锁", "变径", "三通", "弯头", "外丝", "内外丝", "卡箍", "抱箍"])
        connection_material = pick_first(text, ["不锈钢", "镀锌", "铜"])
        if item_group == "液压气动/液压接头":
            family = "液压接头"
        elif item_group == "液压气动/气动接头":
            family = "气动接头"
        else:
            family = "定制管路接头"
        return {
            **base,
            "material_family": family,
            "family_rule": "pipe_connection_family_v0.1",
            "family_note": "管路接头专项样板：高压、液压、气动、定制接头按用途成族，形态作为属性",
            "family_type": connection_type,
            "family_material": connection_material,
            "family_connection": connection_type,
        }

    if "锁" in item_name and item_group in {"清洁办公后勤/门窗五金", "电气电料/电气辅材"}:
        lock_material = pick_first(text, ["不锈钢", "铝合金", "铜"])
        lock_use = pick_first(text, ["办公室门", "防盗门", "断桥铝门", "电箱门", "电箱", "大门", "外门"])
        if "电箱" in text:
            family = "电箱锁"
        elif "挂锁" in item_name or "挂锁" in text or "铜锁" in text:
            family = "挂锁"
        elif "锁扣" in item_name or "锁扣" in text:
            family = "锁扣"
        elif "插销" in item_name:
            family = "插销"
        elif "门锁" in item_name or "门锁" in text:
            family = "门锁"
        else:
            family = item_name
        return {
            **base,
            "material_family": family,
            "family_rule": "lock_family_v0.1",
            "family_note": "门窗五金专项样板：办公室门、防盗门、断桥铝门等作为适配用途",
            "family_material": lock_material,
            "family_use": lock_use,
        }

    return base


def note_from_rule(rule: dict[str, str], prefix: str) -> str:
    reason = rule["reason"].strip()
    split_rule = rule["split_rule"].strip()
    if split_rule:
        return f"{prefix}：{split_rule}；依据：{reason}" if reason else f"{prefix}：{split_rule}"
    return f"{prefix}：{reason}" if reason else prefix


def first_family(value: str) -> str:
    terms = split_terms(value)
    return terms[0] if terms else ""


def apply_solidify_rule(fields: dict[str, str], rule: dict[str, str]) -> dict[str, str]:
    family = first_family(rule["suggested_family"])
    if not family or family == "不单独建族":
        return fields
    return {
        **fields,
        "material_family": family,
        "family_rule": f"family_rule_v0.2:{rule['candidate_term']}",
        "family_note": note_from_rule(rule, "人工物料族规则"),
        "family_attributes": field_append(fields["family_attributes"], rule["family_attributes"]),
    }


def resolve_split_family(row: dict[str, str], rule: dict[str, str]) -> str:
    blocked = {"不单独建族", "按主物料族归属"}
    if rule["candidate_term"] == "螺丝" and (
        "螺丝套件" in row["item_name"]
        or "螺丝组件" in row["item_name"]
        or row["item_group"] == "紧固件与连接件/螺丝套件"
    ):
        return "螺丝套件"
    candidates = [candidate for candidate in split_terms(rule["suggested_family"]) if candidate not in blocked and not candidate.startswith("非")]
    for candidate in sorted(candidates, key=len, reverse=True):
        if candidate and candidate in row["item_name"]:
            return candidate
    return ""


def apply_split_rule(row: dict[str, str], fields: dict[str, str], rule: dict[str, str]) -> dict[str, str]:
    resolved_family = resolve_split_family(row, rule)
    next_fields = {
        **fields,
        "family_rule": field_append(fields["family_rule"], f"family_split_rule_v0.2:{rule['candidate_term']}"),
        "family_note": field_append(fields["family_note"], note_from_rule(rule, "需拆分复核")),
        "family_split_candidates": field_append(fields["family_split_candidates"], rule["suggested_family"]),
        "family_attributes": field_append(fields["family_attributes"], rule["family_attributes"]),
    }
    if resolved_family and fields["material_family"] == row["item_name"]:
        next_fields["material_family"] = resolved_family
    return next_fields


def apply_attribute_rule(fields: dict[str, str], rule: dict[str, str]) -> dict[str, str]:
    return {
        **fields,
        "family_attribute_terms": field_append(fields["family_attribute_terms"], rule["candidate_term"]),
        "family_attributes": field_append(fields["family_attributes"], rule["family_attributes"]),
    }


def derive_material_family(row: dict[str, str], family_rules: list[dict[str, str]] | None = None) -> dict[str, str]:
    fields = derive_material_family_legacy(row)
    if not family_rules:
        return fields

    matched_split_rules: list[dict[str, str]] = []
    matched_attribute_rules: list[dict[str, str]] = []

    for rule in family_rules:
        if not rule_matches(row, rule):
            continue
        if rule["decision"] == "solidify":
            fields = apply_solidify_rule(fields, rule)
            return fields
        if rule["decision"] == "split":
            matched_split_rules.append(rule)
        elif rule["decision"] == "attribute_only":
            matched_attribute_rules.append(rule)

    for rule in matched_split_rules[:2]:
        fields = apply_split_rule(row, fields, rule)
    for rule in matched_attribute_rules[:3]:
        fields = apply_attribute_rule(fields, rule)
    return fields


def is_likely_hand_glove(row: dict[str, str]) -> bool:
    if "手套" in row["item_group"]:
        return True
    if row["item_name"].endswith("手套"):
        return True
    if row["item_code"].startswith("SAFE-") and "手套" in row["aliases"]:
        return True
    return False


def enrich_rows(rows: list[dict[str, str]], family_rules: list[dict[str, str]] | None = None) -> list[dict[str, str]]:
    enriched: list[dict[str, str]] = []
    for row in rows:
        top_group, sub_group = split_group(row["item_group"])
        family_fields = derive_material_family(row, family_rules)
        row_with_family = {**row, **family_fields}
        enriched.append(
            {
                **row_with_family,
                "top_group": top_group,
                "sub_group": sub_group,
                "search_text": (
                    f"{build_search_text(row)} {family_fields['material_family']} "
                    f"{family_fields['family_split_candidates']} {family_fields['family_attribute_terms']}"
                ).lower(),
                "is_likely_hand_glove": "yes" if is_likely_hand_glove(row) else "no",
            }
        )
    return enriched


def group_counts(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    return dict(Counter(row[key] for row in rows).most_common())


def build_categories(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["top_group"]].append(row)

    categories: list[dict[str, object]] = []
    for top_group, group_rows in grouped.items():
        family_count = len({row["material_family"] for row in group_rows})
        sub_groups = [
            {"name": name, "sku_count": count}
            for name, count in sorted(group_counts(group_rows, "sub_group").items(), key=lambda item: (-item[1], item[0]))
        ]
        categories.append(
            {
                "name": top_group,
                "sku_count": len(group_rows),
                "name_count": family_count,
                "status_counts": group_counts(group_rows, "status"),
                "quality_counts": group_counts(group_rows, "quality_level"),
                "sub_groups": sub_groups,
            }
        )
    categories.sort(key=lambda item: (-int(item["sku_count"]), str(item["name"])))
    return categories


def build_summary(rows: list[dict[str, str]]) -> dict[str, object]:
    name_group_counter: Counter[str] = Counter()
    for row in rows:
        name_group_counter[f"{row['item_name']} | {row['item_group']}"] += 1
    return {
        "sku_count": len(rows),
        "item_name_count": len({row["item_name"] for row in rows}),
        "material_family_count": len({row["material_family"] for row in rows}),
        "top_group_count": len({row["top_group"] for row in rows}),
        "item_group_count": len({row["item_group"] for row in rows}),
        "status_counts": group_counts(rows, "status"),
        "quality_counts": group_counts(rows, "quality_level"),
        "agent_use_policy_counts": group_counts(rows, "agent_use_policy"),
        "top_repeated_names": dict(Counter(row["item_name"] for row in rows).most_common(30)),
        "top_repeated_name_groups": dict(name_group_counter.most_common(30)),
    }


def describe_family_rule_token(token: str) -> tuple[str, str]:
    if token.startswith("family_rule_v0.2:"):
        return "solidify", token.split(":", 1)[1]
    if token.startswith("family_split_rule_v0.2:"):
        return "split", token.split(":", 1)[1]
    if token.endswith("_family_v0.1"):
        return "legacy", token.replace("_family_v0.1", "")
    return "other", token


def build_family_rule_impacts(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    impacts: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        for token in split_terms(row["family_rule"]):
            impacts[token].append(row)

    result: list[dict[str, object]] = []
    for token, token_rows in impacts.items():
        decision, candidate = describe_family_rule_token(token)
        result.append(
            {
                "rule_key": token,
                "decision": decision,
                "candidate_term": candidate,
                "sku_count": len(token_rows),
                "family_count": len({row["material_family"] for row in token_rows}),
                "top_groups": group_counts(token_rows, "top_group"),
                "item_groups": group_counts(token_rows, "item_group"),
                "families": group_counts(token_rows, "material_family"),
                "quality_counts": group_counts(token_rows, "quality_level"),
                "sample_item_codes": [row["item_code"] for row in token_rows[:10]],
            }
        )
    result.sort(key=lambda item: (-int(item["sku_count"]), str(item["rule_key"])))
    return result


def build_browser_data(
    input_path: Path,
    output_path: Path,
    generated_at: str,
    family_rules_path: Path = DEFAULT_FAMILY_RULES_PATH,
) -> dict[str, object]:
    family_rules = read_family_rules(family_rules_path)
    rows = enrich_rows(read_master(input_path), family_rules)
    payload = {
        "generated_at": generated_at,
        "source": str(input_path),
        "family_rules_source": str(family_rules_path) if family_rules else "",
        "family_rules_count": len(family_rules),
        "summary": build_summary(rows),
        "categories": build_categories(rows),
        "family_rule_impacts": build_family_rule_impacts(rows),
        "rows": rows,
    }
    write_json(output_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build JSON data for the material master browser page.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--generated-at", default=date.today().isoformat())
    parser.add_argument("--family-rules", type=Path, default=DEFAULT_FAMILY_RULES_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_browser_data(args.input, args.output, args.generated_at, args.family_rules)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sku_count": payload["summary"]["sku_count"],
                "top_group_count": payload["summary"]["top_group_count"],
                "item_name_count": payload["summary"]["item_name_count"],
                "material_family_count": payload["summary"]["material_family_count"],
                "family_rules_count": payload["family_rules_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
