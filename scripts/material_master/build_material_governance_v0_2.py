from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TSV_PATH = ROOT / "data/material_master/reclassification/material_master_reclassified.tsv"
JSON_PATH = ROOT / "data/material_master/reclassification/material_master_browser_data_reclassified.json"
RULES_PATH = ROOT / "data/material_master/reclassification/family_governance/material_family_rules.tsv"
OUT_DIR = ROOT / "data/material_master/governance_v0_2"
ISSUE_TSV = OUT_DIR / "material_governance_issue_inventory.tsv"
SUMMARY_JSON = OUT_DIR / "material_governance_summary.json"
PLAN_MD = ROOT / "docs/reference/material-governance-v0.2-plan.md"


ISSUE_FIELDS = [
    "issue_id",
    "issue_type",
    "severity",
    "scope",
    "affected_count",
    "sample_item_codes",
    "sample_names",
    "recommended_action",
    "owner_decision_needed",
]


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def load_rows() -> tuple[list[dict[str, str]], list[dict[str, str]], dict]:
    tsv_rows = read_tsv(TSV_PATH)
    browser_data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    browser_rows = browser_data["rows"]
    if len(tsv_rows) != len(browser_rows):
        raise RuntimeError(f"TSV/JSON row count mismatch: {len(tsv_rows)} vs {len(browser_rows)}")
    return tsv_rows, browser_rows, browser_data


def spec_keys(text: str) -> list[str]:
    keys: list[str] = []
    for part in re.split(r"[；;]", text or ""):
        if "：" in part:
            keys.append(part.split("：", 1)[0].strip())
        elif ":" in part:
            keys.append(part.split(":", 1)[0].strip())
    return [key for key in keys if key]


def sample_values(rows: list[dict[str, str]], field: str, limit: int = 8) -> str:
    values: list[str] = []
    seen: set[str] = set()
    for row in rows:
        value = row.get(field, "")
        if value and value not in seen:
            values.append(value)
            seen.add(value)
        if len(values) >= limit:
            break
    return "；".join(values)


def add_issue(
    issues: list[dict[str, str]],
    issue_type: str,
    severity: str,
    scope: str,
    affected_rows: list[dict[str, str]],
    recommended_action: str,
    owner_decision_needed: str,
) -> None:
    issue_id = f"GOV-{len(issues) + 1:04d}"
    issues.append(
        {
            "issue_id": issue_id,
            "issue_type": issue_type,
            "severity": severity,
            "scope": scope,
            "affected_count": str(len(affected_rows)),
            "sample_item_codes": sample_values(affected_rows, "item_code"),
            "sample_names": sample_values(affected_rows, "item_name"),
            "recommended_action": recommended_action,
            "owner_decision_needed": owner_decision_needed,
        }
    )


def contains_any(row: dict[str, str], terms: list[str], fields: tuple[str, ...] = ("item_name", "aliases", "required_specs")) -> bool:
    text = " ".join(row.get(field, "") for field in fields)
    return any(term in text for term in terms)


def top_family_stats(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    family_rows: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        family_rows[row.get("material_family") or "(未识别物料族)"].append(row)

    stats: list[dict[str, object]] = []
    for family, items in family_rows.items():
        total = len(items)
        needs_review = sum(1 for row in items if row.get("quality_level") == "needs_review")
        clarify = sum(1 for row in items if row.get("agent_use_policy") == "clarify_specs_before_use")
        split_candidates = sum(1 for row in items if row.get("family_split_candidates"))
        missing_specs = sum(1 for row in items if "缺失规格" in row.get("governance_note", ""))
        attr_blank = sum(1 for row in items if not row.get("family_attributes"))
        unique_names = len({row.get("item_name", "") for row in items})
        score = needs_review * 3 + split_candidates * 2 + missing_specs + attr_blank + max(0, unique_names - 5)
        stats.append(
            {
                "material_family": family,
                "sku_count": total,
                "needs_review_count": needs_review,
                "clarify_specs_before_use_count": clarify,
                "split_candidate_count": split_candidates,
                "missing_specs_note_count": missing_specs,
                "family_attributes_blank_count": attr_blank,
                "unique_item_name_count": unique_names,
                "priority_score": score,
            }
        )
    stats.sort(key=lambda item: (item["priority_score"], item["needs_review_count"], item["sku_count"]), reverse=True)
    return stats


def build_issues(rows: list[dict[str, str]], priority_families: list[dict[str, object]]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []

    needs_review_rows = [row for row in rows if row.get("quality_level") == "needs_review"]
    clarify_rows = [row for row in rows if row.get("agent_use_policy") == "clarify_specs_before_use"]
    add_issue(
        issues,
        "quality_review_concentration",
        "P0",
        "all_skus",
        needs_review_rows,
        "先按物料族分批治理，不直接批量导入；每批输出名称规则、规格模板、单位归一建议和人工复核清单。",
        "yes",
    )
    add_issue(
        issues,
        "clarify_specs_policy_concentration",
        "P0",
        "all_skus",
        clarify_rows,
        "将 clarify_specs_before_use 作为冻结口径：未补齐关键规格前仅允许检索和询问，不允许自动选型。",
        "yes",
    )

    for family_stat in priority_families[:10]:
        family = str(family_stat["material_family"])
        affected = [row for row in rows if row.get("material_family") == family and row.get("quality_level") == "needs_review"]
        if not affected:
            continue
        add_issue(
            issues,
            "review_concentration_by_family",
            "P0" if len(affected) >= 40 else "P1",
            f"material_family:{family}",
            affected,
            "建立该族规格模板与拆分/归并规则，先抽样人工确认边界，再由脚本生成候选修正表。",
            "yes",
        )

    unit_groups = [
        ("uom_weight_alias", "P1", "unit:weight", ["KG", "kg", "公斤", "斤"], "重量单位需统一 ERPNext UOM 口径；建议 KG/kg/公斤归一为 kg 或千克，斤需人工确认是否按 0.5kg 换算。"),
        ("uom_area_alias", "P1", "unit:area", ["平方", "㎡", "平米"], "面积单位需统一为平方米口径；平方/㎡/平米可脚本归一，但电线截面积中的“平方”不能当 stock_uom 改。"),
        ("uom_pair_alias", "P1", "unit:pair", ["付", "副", "双"], "成对单位需要定义业务口径；手套多用双，合页/眼镜/吊带的付/副是否等价需业主确认。"),
    ]
    for issue_type, severity, scope, units, action in unit_groups:
        affected = [row for row in rows if row.get("stock_uom") in units]
        add_issue(issues, issue_type, severity, scope, affected, action, "yes")

    synonym_groups = [
        ("synonym_cable", "P1", "synonym:电缆/电缆线/电线", ["电缆线", "电缆", "电线"], "长词优先：电缆防水接头/电缆支架先排除；电缆线归电缆，BV 等导线归电线。"),
        ("synonym_spray_paint", "P2", "synonym:自喷漆/自动喷漆/喷漆", ["自喷漆", "自动喷漆", "喷漆"], "自喷漆/自动喷漆可规则归并；泛称喷漆需人工确认是自喷漆、桶装油漆还是施工服务描述。"),
        ("synonym_screw", "P0", "synonym:螺丝/螺丝组件/螺丝套件", ["螺丝组件", "螺丝套件", "螺丝"], "先排除螺丝刀、膨胀螺丝、花篮螺丝；普通螺丝统一族名，组件/套件作为成套属性或单独套件口径待确认。"),
        ("synonym_connector", "P0", "synonym:接头/直接/直通", ["接头", "直接", "直通"], "按系统拆分：水暖/PPR/PVC/镀锌归标准管件，液压/气动/消防/电缆接头归各自专族。"),
        ("synonym_lifting_sling", "P2", "synonym:吊带/吊装带/扁平吊装带", ["吊带", "吊装带", "扁平吊装带"], "吊带、吊装带可归并；扁平/环形作为型式属性，保留额定载荷和长度为必填。"),
    ]
    for issue_type, severity, scope, terms, action in synonym_groups:
        affected = [row for row in rows if contains_any(row, terms, ("item_name", "aliases"))]
        add_issue(issues, issue_type, severity, scope, affected, action, "yes" if severity in {"P0", "P1"} else "no")

    attribute_terms = [
        ("name_embeds_material", "P1", "name_attribute:不锈钢/PPR/镀锌", ["不锈钢", "PPR", "镀锌"], "材质/表面处理从标准名称迁移到规格属性；保留对搜索别名的兼容。"),
        ("name_embeds_pressure_or_strength", "P1", "name_attribute:高压/高强度/防爆/耐磨", ["高压", "高强度", "防爆", "耐磨"], "压力等级、强度或防护特征进入规格模板；高压同时用于液压边界判定，需人工确认。"),
        ("name_embeds_form_factor", "P2", "name_attribute:加厚/内六角/五坑/扁平", ["加厚", "内六角", "五坑", "扁平"], "型式、柄型、厚度等属性不建议固化在族名；可脚本抽取候选属性后人工复核。"),
    ]
    for issue_type, severity, scope, terms, action in attribute_terms:
        affected = [row for row in rows if contains_any(row, terms, ("item_name",))]
        add_issue(issues, issue_type, severity, scope, affected, action, "yes")

    broad_families = [
        ("family_scope_screw", "P0", "螺丝", "螺丝族混入膨胀锚栓、花篮螺丝、螺丝刀和套件语义；需要长词优先规则和成套口径。"),
        ("family_scope_hydraulic_connector", "P0", "液压接头", "液压接头与高压弯头、对丝、油管快接、铜接头边界重叠；需先定义液压系统判定词。"),
        ("family_scope_pipe_connector", "P0", "直接/接头", "直接/接头是宽族，PPR/PVC/UPVC/镀锌和内外丝应作为系统、材质、连接属性；液压/气动/消防需排除。"),
        ("family_scope_hose_assembly", "P1", "胶管总成", "胶管总成规格高度依赖长度、层数和两端螺纹，缺一项就不能唯一选型。"),
        ("family_scope_drill_bit", "P1", "钻头", "钻头按柄型、直径、长度、适用材质区分；五坑/冲击/麻花等不应拆成杂乱族名。"),
        ("family_scope_cable", "P1", "电缆", "电缆、电缆线、电线、电缆防水接头和支架需要本体/附件边界。"),
    ]
    for issue_type, severity, family, action in broad_families:
        affected = [row for row in rows if row.get("material_family") == family or family in row.get("item_name", "")]
        add_issue(issues, issue_type, severity, f"material_family:{family}", affected, action, "yes")

    blank_attr_rows = [row for row in rows if not row.get("family_attributes")]
    add_issue(
        issues,
        "required_template_missing",
        "P0",
        "family_attributes_blank",
        blank_attr_rows,
        "补齐物料族必填规格模板；优先处理高频族和所有 needs_review 的空模板族。",
        "yes",
    )

    family_key_counter: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        family_key_counter[row.get("material_family") or "(未识别物料族)"].update(spec_keys(row.get("required_specs", "")))
    for family in ["螺丝", "液压接头", "直接/接头", "钻头", "胶管总成", "电缆"]:
        affected = [row for row in rows if row.get("material_family") == family]
        if not affected:
            continue
        keys = "、".join(key for key, _ in family_key_counter[family].most_common(8))
        add_issue(
            issues,
            "required_template_inconsistent",
            "P1",
            f"material_family:{family}",
            affected,
            f"该族现有规格键不统一（高频键：{keys}）；需收敛为必填/选填模板并映射旧字段同义词。",
            "yes",
        )

    return issues


def write_issue_tsv(issues: list[dict[str, str]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with ISSUE_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ISSUE_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(issues)


def build_summary(
    rows: list[dict[str, str]],
    tsv_rows: list[dict[str, str]],
    browser_data: dict,
    issues: list[dict[str, str]],
    priority_families: list[dict[str, object]],
) -> dict:
    quality_counts = Counter(row.get("quality_level", "") for row in tsv_rows)
    policy_counts = Counter(row.get("agent_use_policy", "") for row in tsv_rows)
    issue_type_rows = Counter(issue["issue_type"] for issue in issues)
    issue_type_affected = defaultdict(int)
    for issue in issues:
        issue_type_affected[issue["issue_type"]] += int(issue["affected_count"])

    next_sequence = [
        {
            "order": 1,
            "material_family": "螺丝",
            "why": "84 条中 83 条 needs_review，且螺丝/组件/套件/膨胀/花篮/螺丝刀语义交叉，先治理能显著降低紧固件误选风险。",
            "target_outputs": ["长词优先拆分规则", "螺丝规格模板", "成套/套件人工判定清单"],
        },
        {
            "order": 2,
            "material_family": "液压接头",
            "why": "73 条中 59 条 needs_review，和高压、油管、对丝、铜接头、弯头/三通边界重叠，错误选型风险高。",
            "target_outputs": ["液压系统判定词表", "接头规格模板", "疑似非液压接头复核清单"],
        },
        {
            "order": 3,
            "material_family": "直接/接头",
            "why": "63 条且 45 条带 family_split_candidates，是水暖、管件、液压、气动、消防、电缆接头交叉的核心宽族。",
            "target_outputs": ["标准管件归并规则", "材质/连接/口径模板", "需转出到液压/气动/消防/电缆的候选表"],
        },
        {
            "order": 4,
            "material_family": "定制管路接头",
            "why": "60 条全部偏人工判定，需在标准接头边界明确后再治理，避免把标准件误留在定制族。",
            "target_outputs": ["定制判定标准", "图纸/加工/非标规格模板", "可回流标准族候选"],
        },
        {
            "order": 5,
            "material_family": "胶管总成",
            "why": "34 条全部 needs_review，规格唯一性依赖长度、层数、两端螺纹，适合做专门模板治理。",
            "target_outputs": ["胶管总成必填模板", "两端接头字段规范", "缺失端口规格复核清单"],
        },
    ]

    return {
        "generated_at": "2026-07-03",
        "source_files": {
            "tsv": str(TSV_PATH.relative_to(ROOT)),
            "browser_json": str(JSON_PATH.relative_to(ROOT)),
            "family_rules": str(RULES_PATH.relative_to(ROOT)),
        },
        "total_sku_count": len(tsv_rows),
        "browser_row_count": len(rows),
        "quality_level_counts": dict(quality_counts),
        "agent_use_policy_counts": dict(policy_counts),
        "issue_type_counts": {
            issue_type: {
                "issue_row_count": issue_type_rows[issue_type],
                "affected_sku_mentions": issue_type_affected[issue_type],
            }
            for issue_type in sorted(issue_type_rows)
        },
        "top_10_priority_material_families": priority_families[:10],
        "recommended_next_governance_sequence": next_sequence,
        "source_summary": browser_data.get("summary", {}),
    }


def write_summary(summary: dict) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_plan(summary: dict) -> None:
    q = summary["quality_level_counts"]
    issue_counts = summary["issue_type_counts"]
    top = summary["top_10_priority_material_families"]
    sequence = summary["recommended_next_governance_sequence"]

    lines: list[str] = []
    lines.append("# 物料主数据治理 v0.2 计划")
    lines.append("")
    lines.append("## 1. 本轮目标")
    lines.append("")
    lines.append("本轮不写 ERPNext，不改原始重分类 TSV 和浏览器 JSON，只建立治理问题台账与下一批分批治理计划。后续每批治理都应先输出候选规则、候选修正表和人工判定清单，再由负责人确认是否进入正式主数据。")
    lines.append("")
    lines.append("## 2. 当前总体状态")
    lines.append("")
    lines.append(f"- 总 SKU 数：{summary['total_sku_count']}。")
    lines.append(f"- 质量等级：standard {q.get('standard', 0)}，usable {q.get('usable', 0)}，needs_review {q.get('needs_review', 0)}。")
    lines.append(f"- 使用策略：auto_select_allowed {summary['agent_use_policy_counts'].get('auto_select_allowed', 0)}，confirm_before_use {summary['agent_use_policy_counts'].get('confirm_before_use', 0)}，clarify_specs_before_use {summary['agent_use_policy_counts'].get('clarify_specs_before_use', 0)}。")
    lines.append("- 问题台账文件：`data/material_master/governance_v0_2/material_governance_issue_inventory.tsv`。")
    lines.append("")
    lines.append("## 3. 主要问题")
    lines.append("")
    lines.append("### 3.1 needs_review / clarify_specs_before_use 集中")
    lines.append("")
    lines.append(f"`needs_review` 与 `clarify_specs_before_use` 均为 {q.get('needs_review', 0)} 条，说明大多数 SKU 还不能自动选型。问题主要集中在螺丝、液压接头、定制管路接头、直接/接头、胶管总成等高风险族。")
    lines.append("")
    lines.append("### 3.2 单位口径不统一")
    lines.append("")
    lines.append("重量单位存在 KG、kg、公斤、斤；面积单位存在 平方、㎡、平米；成对单位存在 付、副、双。KG/kg/公斤、平方/㎡ 等可先做候选归一，但“斤”的换算口径、合页/眼镜/吊带的“付/副/双”是否等价必须由业务确认。")
    lines.append("")
    lines.append("### 3.3 同义和近义名称")
    lines.append("")
    lines.append("电缆/电缆线/电线、自喷漆/喷漆、螺丝/螺丝组件/螺丝套件、接头/直接/直通等名称混用。适合采用长词优先和排除词规则，但套件、泛称喷漆、接头系统边界需要人工判定。")
    lines.append("")
    lines.append("### 3.4 标准名称夹带属性")
    lines.append("")
    lines.append("不锈钢、PPR、高压、加厚、内六角、五坑、镀锌、扁平等经常写进 `item_name`。这些词多数应迁移为材质、压力等级、型式、柄型或表面处理属性，标准名称保留稳定族名，别名/搜索词保留原始说法。")
    lines.append("")
    lines.append("### 3.5 物料族过宽或边界过细")
    lines.append("")
    lines.append("螺丝、液压接头、直接/接头、电缆等宽族容易吞掉附件或其他系统物料；胶管总成、钻头则需要更精细的规格模板避免同名不同物。治理时应先定义族边界，再补规格模板。")
    lines.append("")
    lines.append("### 3.6 必填规格模板缺失或不统一")
    lines.append("")
    lines.append("浏览 JSON 中仍有大量行缺少 `family_attributes`，且同一族的规格键存在“规格/型号规格/螺纹规格/载荷/额定载荷”等同义字段。后续应为每个治理族输出必填字段、选填字段、字段同义词映射和缺失字段复核表。")
    lines.append("")
    lines.append("## 4. 哪些可以规则/脚本修")
    lines.append("")
    lines.append("- 单位候选归一：KG/kg/公斤、平方/㎡、部分“付/副/双”可由脚本生成候选表，但不直接覆盖源 TSV。")
    lines.append("- 长词优先归并：电缆防水接头先于电缆，花篮螺丝先于普通螺丝，螺丝刀排除出螺丝族。")
    lines.append("- 属性抽取：不锈钢、PPR、镀锌、高压、内六角、五坑等可抽为候选属性。")
    lines.append("- 字段同义词：载荷/额定载荷、型号/型号规格、螺纹/螺纹规格等可映射到模板字段。")
    lines.append("")
    lines.append("## 5. 哪些必须人工判定")
    lines.append("")
    lines.append("- `斤` 是否换算为 kg，以及历史采购单位是否需要保留。")
    lines.append("- “螺丝组件/螺丝套件”是普通螺丝的成套属性，还是应建套件类 SKU。")
    lines.append("- 接头类按系统归属：液压、气动、消防、水暖、电缆密封、定制加工之间的边界。")
    lines.append("- 高压、加厚、防爆、耐磨等词是属性、工况要求，还是会改变采购族。")
    lines.append("- 定制管路接头是否有图纸、加工要求或不可替代性；没有证据时不应自动合并到标准接头。")
    lines.append("")
    lines.append("## 6. Top 10 优先治理物料族")
    lines.append("")
    lines.append("| 排名 | 物料族 | SKU | needs_review | 拆分候选 | 缺规格提示 | 优先分 |")
    lines.append("|---:|---|---:|---:|---:|---:|---:|")
    for index, item in enumerate(top, start=1):
        lines.append(
            f"| {index} | {item['material_family']} | {item['sku_count']} | {item['needs_review_count']} | "
            f"{item['split_candidate_count']} | {item['missing_specs_note_count']} | {item['priority_score']} |"
        )
    lines.append("")
    lines.append("## 7. 下一批治理顺序")
    lines.append("")
    for item in sequence[:5]:
        targets = "；".join(item["target_outputs"])
        lines.append(f"{item['order']}. **{item['material_family']}**：{item['why']}目标输出：{targets}。")
    lines.append("")
    lines.append("## 8. 第一批建议聚焦 3 个族")
    lines.append("")
    lines.append("第一批建议治理 **螺丝、液压接头、直接/接头**。这三个族数量大、`needs_review` 集中、边界重叠明显，并且会影响紧固件和管路连接件两个高频采购区域。先把它们的族边界和模板定下来，后面的定制管路接头、胶管总成、电缆治理会更稳。")
    lines.append("")
    lines.append("每个族的目标输出：")
    lines.append("")
    lines.append("- 螺丝：长词优先拆分规则；螺丝标准名称；规格、头型、强度等级、材质、表面处理、长度/直径模板；组件/套件人工判定清单。")
    lines.append("- 液压接头：液压系统判定词；规格、螺纹、连接形式、材质、压力等级、适配油管模板；疑似气动/水暖/定制接头转出清单。")
    lines.append("- 直接/接头：PPR/PVC/UPVC/镀锌/不锈钢等标准管件规则；口径、材质、连接方式、内外丝、压力等级模板；应转出到液压、气动、消防、电缆接头的候选清单。")
    lines.append("")
    lines.append("## 9. 本轮产物")
    lines.append("")
    lines.append("- `data/material_master/governance_v0_2/material_governance_issue_inventory.tsv`：问题台账。")
    lines.append("- `data/material_master/governance_v0_2/material_governance_summary.json`：机器可读汇总与优先顺序。")
    lines.append("- `docs/reference/material-governance-v0.2-plan.md`：中文治理计划。")

    PLAN_MD.parent.mkdir(parents=True, exist_ok=True)
    PLAN_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    tsv_rows, rows, browser_data = load_rows()
    priority_families = top_family_stats(rows)
    issues = build_issues(rows, priority_families)
    write_issue_tsv(issues)
    summary = build_summary(rows, tsv_rows, browser_data, issues, priority_families)
    write_summary(summary)
    write_plan(summary)
    print(f"wrote {ISSUE_TSV}")
    print(f"wrote {SUMMARY_JSON}")
    print(f"wrote {PLAN_MD}")


if __name__ == "__main__":
    main()
