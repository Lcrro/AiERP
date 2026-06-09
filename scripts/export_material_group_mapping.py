from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - script can still run with explicit args
    load_dotenv = None


DEFAULT_DATA_DIR = Path("data/material_purchase_2024")
DEFAULT_OUTPUT = DEFAULT_DATA_DIR / "material_group_canonical_mapping.csv"


CSV_FILES = [
    "standard_item_catalog_from_review.csv",
    "item_aliases_from_review.csv",
    "manual_review_queue_from_review.csv",
    "non_stock_services_from_review.csv",
]


L1_ALIASES = {
    "安全标识": "安全防护",
    "安全防护": "安全防护",
    "安全设施": "安全防护",
    "劳保": "劳保用品",
    "劳保耗材": "劳保用品",
    "劳保用品": "劳保用品",
    "安全消防": "消防器材",
    "消防材料": "消防器材",
    "消防器材": "消防器材",
    "电气": "电气与自动化",
    "电气材料": "电气与自动化",
    "电气耗材": "电气与自动化",
    "自动化": "电气与自动化",
    "弱电安防": "弱电安防",
    "通讯设备": "弱电安防",
    "通信设备": "弱电安防",
    "工具": "工具器具",
    "工具器具": "工具器具",
    "工具耗材": "工具器具",
    "工具备件": "工具器具",
    "手动工具": "工具器具",
    "电动工具": "工具器具",
    "气动": "液压气动",
    "气动元件": "液压气动",
    "气动液压": "液压气动",
    "液压": "液压气动",
    "液压气动": "液压气动",
    "管材": "管道管件",
    "管道耗材": "管道管件",
    "管道紧固": "管道管件",
    "管件": "管道管件",
    "管夹": "管道管件",
    "PPR管件": "管道管件",
    "PPR管材": "管道管件",
    "工程材料": "工程建材",
    "工程器具": "工具器具",
    "建材": "工程建材",
    "建筑材料": "工程建材",
    "建筑施工耗材": "工程建材",
    "建筑周转材料": "工程建材",
    "建筑装饰材料": "工程建材",
    "装修材料": "工程建材",
    "装饰": "工程建材",
    "板材": "工程建材",
    "保温材料": "工程建材",
    "木材板材": "工程建材",
    "塑料板材": "工程建材",
    "水暖五金": "工程建材",
    "五金建材": "工程建材",
    "五金": "五金备件",
    "五金备件": "五金备件",
    "五金耗材": "五金备件",
    "紧固件": "紧固件",
    "密封件": "密封件",
    "吊装索具": "吊装索具",
    "绳索": "吊装索具",
    "阀门": "阀门",
    "焊割耗材": "焊接焊割",
    "焊割设备": "焊接焊割",
    "焊割工具": "焊接焊割",
    "焊接材料": "焊接焊割",
    "焊接防护": "焊接焊割",
    "焊接工具": "焊接焊割",
    "焊接耗材": "焊接焊割",
    "化工材料": "化工油漆胶粘",
    "化工耗材": "化工油漆胶粘",
    "化工辅料": "化工油漆胶粘",
    "化工原料": "化工油漆胶粘",
    "胶粘剂": "化工油漆胶粘",
    "清洁化学品": "化工油漆胶粘",
    "油漆涂料": "化工油漆胶粘",
    "油品": "化工油漆胶粘",
    "涂装工具": "工具器具",
    "润滑工具": "润滑系统",
    "润滑配件": "润滑系统",
    "润滑设备": "润滑系统",
    "润滑系统": "润滑系统",
    "设备润滑": "润滑系统",
    "备品备件": "设备备件与加工件",
    "定制件": "设备备件与加工件",
    "加工件": "设备备件与加工件",
    "设备": "设备备件与加工件",
    "设备备件": "设备备件与加工件",
    "原材料": "金属原材料",
    "钢材": "金属原材料",
    "金属材料": "金属原材料",
    "仪表": "仪器仪表",
    "检测耗材": "仪器仪表",
    "包装材料": "包装与标识",
    "标签耗材": "包装与标识",
    "标识耗材": "包装与标识",
    "胶带": "包装与标识",
    "办公": "行政办公与清洁",
    "办公低耗": "行政办公与清洁",
    "办公耗材": "行政办公与清洁",
    "办公生活用品": "行政办公与清洁",
    "办公用品": "行政办公与清洁",
    "行政后勤": "行政办公与清洁",
    "清洁工具": "行政办公与清洁",
    "清洁耗材": "行政办公与清洁",
    "清洁用品": "行政办公与清洁",
    "清洗设备": "行政办公与清洁",
    "容器": "行政办公与清洁",
    "搬运工具": "仓储物流",
    "仓储设备": "仓储物流",
    "物流搬运": "仓储物流",
    "输送设备": "仓储物流",
    "环保耗材": "环保",
    "环保设备": "环保",
    "堵漏注浆": "工程建材",
    "注浆设备": "工程建材",
    "施工工具": "工具器具",
    "施工设备": "设备备件与加工件",
    "覆盖材料": "工程建材",
    "辅料耗材": "生产辅料",
    "磨具磨料": "工具器具",
    "绝缘材料": "电气与自动化",
    "服务费用": "非库存服务",
}


RULES = [
    ("消防器材", "灭火器与水带", "灭火器", ("灭火器",)),
    ("消防器材", "灭火器与水带", "消防水带", ("消防水带", "水带")),
    ("消防器材", "消防管件与接头", "消防接头", ("消防接头", "消防管件")),
    ("消防器材", "消防工具", "消防工具", ("消防工具", "消防器材", "消防材料")),
    ("安全防护", "警示标识", "反光警示", ("反光", "警示", "标识", "标牌", "交通标识")),
    ("安全防护", "隔离防护", "防护网", ("防护网", "隔离", "防撞")),
    ("安全防护", "高处与水域防护", "高处防护", ("安全带", "安全绳", "登高", "高处")),
    ("安全防护", "高处与水域防护", "水域防护", ("水域",)),
    ("劳保用品", "手部防护", "手套", ("手套",)),
    ("劳保用品", "呼吸防护", "口罩", ("口罩", "防尘", "滤棉")),
    ("劳保用品", "眼面防护", "眼镜面罩", ("护目", "眼镜", "面罩")),
    ("劳保用品", "头足身防护", "安全帽", ("安全帽", "头盔")),
    ("劳保用品", "头足身防护", "劳保鞋", ("劳保鞋", "安全鞋", "雨靴")),
    ("劳保用品", "头足身防护", "防护服", ("防护服", "雨衣", "围裙")),
    ("电气与自动化", "低压电器", "断路器", ("断路器", "漏电", "空开")),
    ("电气与自动化", "低压电器", "继电器接触器", ("继电器", "接触器")),
    ("电气与自动化", "低压电器", "开关按钮", ("按钮", "开关", "指示元件")),
    ("电气与自动化", "电线电缆与敷设", "电线电缆", ("电线", "电缆", "线缆")),
    ("电气与自动化", "电线电缆与敷设", "电缆附件", ("电缆接头", "电缆支架", "桥架")),
    ("电气与自动化", "接线连接", "接线端子", ("接线端子", "端子")),
    ("电气与自动化", "插头插座", "插头插座", ("插头", "插座", "插排")),
    ("电气与自动化", "绝缘材料", "热缩绝缘", ("热缩", "绝缘")),
    ("电气与自动化", "照明与报警", "灯具", ("照明", "灯", "灯具")),
    ("电气与自动化", "照明与报警", "报警器", ("报警",)),
    ("电气与自动化", "电源电池", "电源电池", ("电池", "电源", "充电器")),
    ("弱电安防", "通信与监控", "通信设备", ("通讯", "通信", "网络")),
    ("弱电安防", "通信与监控", "安防监控", ("监控", "摄像", "门禁")),
    ("工具器具", "手动工具", "扳手", ("扳手",)),
    ("工具器具", "手动工具", "钳剪刀锤", ("钳", "剪", "刀", "锤", "锯", "铲", "撬")),
    ("工具器具", "电动工具", "电钻角磨机", ("电钻", "手电钻", "角磨机", "电动")),
    ("工具器具", "气动工具", "气动工具", ("气动扳手", "气动工具")),
    ("工具器具", "工具耗材", "钻头", ("钻头",)),
    ("工具器具", "工具耗材", "切磨耗材", ("切割片", "磨片", "砂轮", "磨具", "磨料")),
    ("工具器具", "量具测量", "量具测量", ("量具", "测量", "卷尺", "水平仪", "卡尺")),
    ("工具器具", "涂装工具", "刷辊喷涂", ("涂装", "刷", "滚筒", "喷壶")),
    ("工具器具", "工具配件", "工具配件", ("工具配件", "配件")),
    ("液压气动", "液压管路", "高压胶管", ("高压管", "胶管", "油管")),
    ("液压气动", "液压接头", "液压接头", ("液压接头", "接头")),
    ("液压气动", "液压密封", "液压密封", ("油封", "密封")),
    ("液压气动", "气动元件", "接头阀管", ("气动", "快插", "气管")),
    ("管道管件", "塑料管件", "PPR管件", ("PPR",)),
    ("管道管件", "塑料管件", "PVC管件", ("PVC",)),
    ("管道管件", "塑料管件", "PE管件", ("PE",)),
    ("管道管件", "金属管件", "镀锌管件", ("镀锌",)),
    ("管道管件", "金属管件", "钢制管件", ("钢管", "钢制")),
    ("管道管件", "管道紧固", "管夹卡箍", ("管夹", "卡箍", "管道紧固")),
    ("阀门", "通用阀门", "球阀", ("球阀",)),
    ("阀门", "通用阀门", "闸截止止回", ("闸阀", "截止阀", "止回阀")),
    ("阀门", "控制阀门", "电磁气动阀", ("电磁阀", "气动阀")),
    ("紧固件", "螺纹紧固件", "螺丝螺栓", ("螺丝", "螺栓", "螺钉")),
    ("紧固件", "螺纹紧固件", "螺母垫圈", ("螺母", "垫圈", "平垫", "弹垫")),
    ("紧固件", "锚固件", "膨胀锚栓", ("膨胀", "锚栓")),
    ("密封件", "橡胶密封", "O型圈油封", ("O型", "密封圈", "油封")),
    ("密封件", "垫片盘根", "垫片盘根", ("垫片", "盘根")),
    ("五金备件", "门锁锁具", "门锁锁具", ("锁", "门锁")),
    ("五金备件", "通用五金", "轴承滑轮", ("轴承", "滑轮")),
    ("五金备件", "通用五金", "弹簧链条", ("弹簧", "链条")),
    ("吊装索具", "吊带索具", "吊带", ("吊带",)),
    ("吊装索具", "吊带索具", "钢丝绳链条", ("钢丝绳", "链条", "绳索")),
    ("吊装索具", "吊装连接件", "卸扣吊钩", ("卸扣", "吊钩", "卡环")),
    ("焊接焊割", "焊接耗材", "焊条焊丝", ("焊条", "焊丝", "焊接材料")),
    ("焊接焊割", "焊割耗材", "割嘴焊嘴", ("割嘴", "焊嘴", "焊割耗材")),
    ("焊接焊割", "焊割设备工具", "焊机割炬", ("焊机", "割炬", "焊割设备", "焊接工具")),
    ("化工油漆胶粘", "油漆涂料", "涂料油漆", ("油漆", "涂料", "稀料")),
    ("化工油漆胶粘", "胶粘密封", "胶粘剂", ("胶", "胶粘", "结构胶", "密封胶")),
    ("化工油漆胶粘", "油品化学品", "润滑油脂", ("润滑油", "黄油", "油脂")),
    ("化工油漆胶粘", "油品化学品", "清洗化学品", ("清洗剂", "除锈", "清洁化学")),
    ("润滑系统", "润滑设备配件", "润滑泵管路", ("润滑", "油泵", "分配器")),
    ("工程建材", "水泥砂石", "水泥砂石", ("水泥", "砂", "石")),
    ("工程建材", "保温防水", "保温材料", ("保温", "挤塑板")),
    ("工程建材", "保温防水", "防水堵漏", ("防水", "堵漏", "注浆")),
    ("工程建材", "板材型材", "板材", ("板材", "木板", "塑料板", "硅晶板")),
    ("工程建材", "水暖建材", "水暖五金", ("水暖", "PPR管件", "PPR管材")),
    ("金属原材料", "钢材型材", "钢材型材", ("钢材", "钢板", "角钢", "槽钢", "圆钢", "扁钢", "型材")),
    ("金属原材料", "有色金属", "铜铝材料", ("铜", "铝")),
    ("设备备件与加工件", "金属加工件", "金属加工件", ("金属加工", "加工件", "定制件")),
    ("设备备件与加工件", "传动轴承", "传动轴承", ("传动", "轴承", "链轮", "齿轮")),
    ("设备备件与加工件", "过滤密封", "过滤件", ("过滤", "滤芯")),
    ("设备备件与加工件", "设备专用备件", "设备备件", ("设备备件", "电机配件", "泵", "输送")),
    ("仪器仪表", "压力温度仪表", "压力温度", ("压力表", "温度", "温控")),
    ("仪器仪表", "流量液位仪表", "流量液位", ("流量", "液位")),
    ("包装与标识", "袋箱膜包装", "袋箱膜", ("袋", "箱", "膜", "吨袋", "编织袋", "缠绕膜")),
    ("包装与标识", "胶带标签", "胶带", ("胶带",)),
    ("包装与标识", "胶带标签", "标签碳带", ("标签", "碳带", "不干胶")),
    ("行政办公与清洁", "办公用品", "文具书写", ("文具", "书写", "记录本", "办公用品")),
    ("行政办公与清洁", "生活后勤", "生活用品", ("生活", "家具", "小电器", "容器")),
    ("行政办公与清洁", "清洁用品", "清洁工具耗材", ("清洁", "扫", "拖", "垃圾")),
    ("仓储物流", "搬运设备", "手推车叉车", ("手推车", "搬运", "叉车")),
    ("仓储物流", "仓储设备", "货架容器", ("货架", "仓储", "托盘")),
    ("环保", "环保设备耗材", "环保设备耗材", ("环保",)),
    ("非库存服务", "维修服务", "维修服务", ("维修",)),
]


PATH_OVERRIDES = {
    "劳保耗材/手套": ("劳保用品", "手部防护", "手套", 0.98, "人工示例：劳保耗材与劳保用品统一"),
    "劳保用品/手套": ("劳保用品", "手部防护", "手套", 0.98, "人工示例：劳保耗材与劳保用品统一"),
    "工具/手动工具": ("工具器具", "手动工具", "通用手动工具", 0.95, "人工示例：工具/手动工具并入工具器具体系"),
    "手动工具/扳手": ("工具器具", "手动工具", "扳手", 0.98, "人工示例：裸一级手动工具转为规范三级"),
    "电气材料/低压电器": ("电气与自动化", "低压电器", "低压电器", 0.95, "人工示例：电气材料与电气统一"),
    "电气/断路器": ("电气与自动化", "低压电器", "断路器", 0.98, "人工示例：断路器作为低压电器子类"),
}


HIGH_RISK_KEYWORDS = (
    "安全带",
    "安全绳",
    "高处",
    "登高",
    "吊带",
    "卸扣",
    "吊钩",
    "钢丝绳",
    "消防",
    "灭火器",
    "危化",
    "化学品",
    "气瓶",
    "压力容器",
    "防爆",
)


@dataclass(frozen=True)
class MappingRow:
    reviewed_group_path: str
    canonical_level1: str
    canonical_level2: str
    canonical_level3: str
    confidence: float
    rule_reason: str
    needs_human_review: bool

    @property
    def canonical_group_path(self) -> str:
        return "/".join(part for part in [self.canonical_level1, self.canonical_level2, self.canonical_level3] if part)


def split_path(path: str) -> list[str]:
    return [part.strip() for part in path.split("/") if part.strip()]


def normalize_l1(level1: str) -> tuple[str, str, float]:
    canonical = L1_ALIASES.get(level1)
    if canonical:
        if canonical == level1:
            return canonical, f"一级分类已规范：{level1}", 0.88
        return canonical, f"一级同义合并：{level1} -> {canonical}", 0.86
    return "待治理", f"未知一级分类：{level1}", 0.35


def match_rule(canonical_l1: str, text: str) -> tuple[str, str, float, str] | None:
    for rule_l1, level2, level3, keywords in RULES:
        if rule_l1 != canonical_l1:
            continue
        if any(keyword.lower() in text.lower() for keyword in keywords):
            return level2, level3, 0.92, f"关键词规则：{','.join(keywords)}"
    return None


def fallback_levels(canonical_l1: str, original_l2: str) -> tuple[str, str, float, str]:
    if canonical_l1 == "待治理":
        return "待治理", original_l2 or "未分组", 0.25, "未命中一级和关键词规则"
    if original_l2:
        return "其他", original_l2, 0.62, "仅完成一级合并，保留原二级作为三级待复核"
    return "其他", "未分组", 0.5, "缺少二级分类，需人工补充"


def should_review(path: str, confidence: float, canonical_l1: str) -> bool:
    if confidence < 0.7 or canonical_l1 == "待治理":
        return True
    return any(keyword in path for keyword in HIGH_RISK_KEYWORDS)


def canonicalize(path: str) -> MappingRow:
    parts = split_path(path)
    original_l1 = parts[0] if parts else "未分类"
    original_l2 = parts[1] if len(parts) > 1 else ""

    if path in PATH_OVERRIDES:
        l1, l2, l3, confidence, reason = PATH_OVERRIDES[path]
        return MappingRow(path, l1, l2, l3, confidence, reason, should_review(path, confidence, l1))

    canonical_l1, l1_reason, l1_confidence = normalize_l1(original_l1)
    text = "/".join(parts)
    matched = match_rule(canonical_l1, text)
    if matched:
        l2, l3, rule_confidence, rule_reason = matched
        confidence = min(0.98, (l1_confidence + rule_confidence) / 2 + 0.05)
        reason = f"{l1_reason}；{rule_reason}"
    else:
        l2, l3, fallback_confidence, fallback_reason = fallback_levels(canonical_l1, original_l2)
        confidence = min(l1_confidence, fallback_confidence)
        reason = f"{l1_reason}；{fallback_reason}"

    return MappingRow(path, canonical_l1, l2, l3, confidence, reason, should_review(path, confidence, canonical_l1))


def read_csv_groups(data_dir: Path) -> set[str]:
    groups: set[str] = set()
    for filename in CSV_FILES:
        path = data_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                group = (row.get("item_group") or "").strip()
                if group:
                    groups.add(group)
    return groups


def read_postgres_groups(database_url: str) -> set[str]:
    import psycopg

    with psycopg.connect(database_url) as conn:
        rows = conn.execute("select path from material_groups order by path").fetchall()
    return {row[0] for row in rows if row and row[0]}


def collect_groups(source: str, data_dir: Path, database_url: str | None) -> tuple[set[str], str]:
    if source in {"auto", "postgres"} and database_url:
        try:
            return read_postgres_groups(database_url), "postgres"
        except Exception:
            if source == "postgres":
                raise
    return read_csv_groups(data_dir), "csv"


def write_mapping(rows: Iterable[MappingRow], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "reviewed_group_path",
        "canonical_group_path",
        "canonical_level1",
        "canonical_level2",
        "canonical_level3",
        "confidence",
        "rule_reason",
        "needs_human_review",
    ]
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: item.reviewed_group_path):
            writer.writerow(
                {
                    "reviewed_group_path": row.reviewed_group_path,
                    "canonical_group_path": row.canonical_group_path,
                    "canonical_level1": row.canonical_level1,
                    "canonical_level2": row.canonical_level2,
                    "canonical_level3": row.canonical_level3,
                    "confidence": f"{row.confidence:.2f}",
                    "rule_reason": row.rule_reason,
                    "needs_human_review": "true" if row.needs_human_review else "false",
                }
            )


def build_summary(rows: list[MappingRow], source_used: str) -> dict[str, int | str]:
    canonical_paths = {row.canonical_group_path for row in rows}
    review_count = sum(1 for row in rows if row.needs_human_review)
    return {
        "source": source_used,
        "reviewed_groups": len(rows),
        "canonical_groups": len(canonical_paths),
        "needs_human_review": review_count,
        "auto_mapped": len(rows) - review_count,
    }


def main() -> None:
    if load_dotenv:
        load_dotenv()

    parser = argparse.ArgumentParser(description="Export canonical material group mapping for reviewed purchase groups.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--source", choices=["auto", "postgres", "csv"], default="auto")
    parser.add_argument(
        "--database-url",
        default=os.getenv("MATERIAL_CATALOG_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="PostgreSQL DSN. Used when --source is auto/postgres.",
    )
    args = parser.parse_args()

    groups, source_used = collect_groups(args.source, args.data_dir, args.database_url)
    rows = [canonicalize(group) for group in groups]
    write_mapping(rows, args.output)
    summary = build_summary(rows, source_used)
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"output: {args.output}")


if __name__ == "__main__":
    main()
