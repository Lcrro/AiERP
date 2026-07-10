from __future__ import annotations

import csv
from pathlib import Path


BASE_RELEASE = Path("data/material_master/price_ready_release_v0_1/material_master_price_ready_release_v0_1.tsv")
FACTOR_FILE = Path("data/material_master/price_review_samples/price_review_family_adjustment_factors.tsv")

GOVERNANCE_NOTE = "润滑防锈人工治理：区分润滑油、润滑脂、防锈除锈和干性润滑剂，避免使用泛称“润滑剂”。"

ROW_UPDATES: dict[str, dict[str, str]] = {
    "CHEM-000006": {
        "material_family": "防锈除锈",
        "item_name": "防锈润滑剂",
        "sku_name": "防锈润滑剂 WD-40 500ml/瓶",
        "required_specs": "型号：WD-40；容量：500ml/瓶；功能：防锈润滑",
    },
    "CHEM-000037": {
        "material_family": "润滑油",
        "item_name": "齿轮油",
        "sku_name": "齿轮油 HL-20 20L/桶",
        "required_specs": "型号：HL-20；包装：20L/桶",
    },
    "CHEM-000054": {
        "material_family": "防锈除锈",
        "item_name": "防锈润滑剂",
        "sku_name": "防锈润滑剂 WD-40 350ml/瓶",
        "required_specs": "型号：WD-40；容量：350ml/瓶；功能：防锈润滑",
    },
    "CHEM-000058": {
        "material_family": "干性润滑剂",
        "item_name": "干性润滑剂",
        "sku_name": "干性润滑剂 D321R 摩力克 400mL/瓶",
        "required_specs": "品牌：摩力克；型号：D321R；容量：400mL/瓶；类型：干性润滑剂",
    },
    "CHEM-000060": {
        "material_family": "润滑脂",
        "item_name": "通用润滑脂",
        "sku_name": "通用润滑脂 15kg/桶",
        "required_specs": "类型：通用润滑脂；包装：15kg/桶",
    },
    "CHEM-000065": {
        "material_family": "润滑油",
        "item_name": "气动油",
        "sku_name": "气动油 250mL/瓶 油雾器用",
        "required_specs": "用途：油雾器；容量：250mL/瓶",
    },
    "CHEM-000067": {
        "material_family": "润滑油",
        "item_name": "齿轮油",
        "sku_name": "齿轮油 20L/桶",
        "required_specs": "包装：20L/桶",
    },
    "CHEM-000081": {
        "material_family": "润滑油",
        "item_name": "机油",
        "sku_name": "机油 46# 道达尔 20L/桶",
        "required_specs": "品牌：道达尔；牌号：46#；容量：20L/桶",
    },
    "CHEM-000085": {
        "material_family": "防锈除锈",
        "item_name": "防锈润滑剂",
        "sku_name": "防锈润滑剂 DM40 350ml/瓶",
        "required_specs": "型号：DM40；容量：350ml/瓶；功能：防锈润滑",
    },
    "CHEM-000090": {
        "material_family": "润滑油",
        "item_name": "清洗机专用油",
        "sku_name": "清洗机专用油 500mL/瓶",
        "required_specs": "适用设备：清洗机；容量：500mL/瓶",
    },
    "CHEM-000092": {
        "material_family": "润滑脂",
        "item_name": "润滑脂",
        "sku_name": "润滑脂 克虏伯 NB52 1kg/罐",
        "required_specs": "品牌：克虏伯；型号：NB52；包装：1kg/罐",
    },
    "CHEM-000095": {
        "material_family": "润滑油",
        "item_name": "齿轮油",
        "sku_name": "齿轮油 长城 18L/桶",
        "required_specs": "品牌：长城；包装：18L/桶",
    },
    "CHEM-000134": {
        "material_family": "防锈除锈",
        "item_name": "除锈剂",
        "sku_name": "除锈剂 WD40 500mL/瓶",
        "required_specs": "品牌：WD40；容量：500mL/瓶；功能：除锈",
    },
    "CHEM-000136": {
        "material_family": "润滑脂",
        "item_name": "高温润滑脂",
        "sku_name": "高温润滑脂 16kg/桶",
        "required_specs": "特性：高温；包装：16kg/桶",
    },
    "CHEM-000137": {
        "material_family": "防锈除锈",
        "item_name": "除锈剂",
        "sku_name": "除锈剂 陶喜 450mL/瓶",
        "required_specs": "品牌：陶喜；容量：450mL/瓶；功能：除锈",
    },
    "CHEM-000146": {
        "material_family": "防锈除锈",
        "item_name": "除锈剂",
        "sku_name": "除锈剂 WD40 350mL/瓶",
        "required_specs": "品牌：WD40；容量：350mL/瓶；功能：除锈",
    },
    "CHEM-000148": {
        "material_family": "润滑油",
        "item_name": "气动油",
        "sku_name": "气动油 卡仕顿 250mL/瓶",
        "required_specs": "品牌：卡仕顿；容量：250mL/瓶",
    },
    "MAT-000149": {
        "material_family": "润滑油",
        "item_name": "液压油",
        "sku_name": "液压油 进口 10L/桶",
        "required_specs": "容量：10L/桶；来源：进口",
    },
    "METAL-000096": {
        "material_family": "润滑脂",
        "item_name": "钢丝绳润滑脂",
        "sku_name": "钢丝绳润滑脂 5kg/桶",
        "required_specs": "用途：钢丝绳；包装：5kg/桶；剂型：润滑脂",
        "aliases": "进口5KG钢丝绳专用剂；钢丝绳专用剂；钢丝绳润滑剂",
    },
    "METAL-000103": {
        "material_family": "润滑脂",
        "item_name": "钢丝绳润滑脂",
        "sku_name": "钢丝绳润滑脂 伍尔特 500mL/瓶",
        "required_specs": "品牌：伍尔特；用途：钢丝绳；容量：500mL/瓶；剂型：润滑脂",
    },
}


def read_tsv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return list(reader), list(reader.fieldnames or [])


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def append_note(value: str, note: str) -> str:
    value = (value or "").strip()
    if note in value:
        return value
    if not value:
        return note
    return f"{value}；{note}"


def apply_release_updates() -> int:
    rows, fields = read_tsv(BASE_RELEASE)
    updated = 0
    for row in rows:
        updates = ROW_UPDATES.get(row.get("item_code", ""))
        if not updates:
            continue
        row.update(updates)
        row["default_fill_basis"] = append_note(row.get("default_fill_basis", ""), GOVERNANCE_NOTE)
        updated += 1
    write_tsv(BASE_RELEASE, rows, fields)
    return updated


def ensure_factor_rows() -> list[str]:
    rows, fields = read_tsv(FACTOR_FILE)
    existing = {row["material_family"] for row in rows}
    source = next(row for row in rows if row["material_family"] == "润滑防锈")
    added: list[str] = []
    for family in sorted({updates["material_family"] for updates in ROW_UPDATES.values()}):
        if family in existing:
            continue
        new_row = dict(source)
        new_row["material_family"] = family
        rows.append(new_row)
        added.append(family)
    if added:
        write_tsv(FACTOR_FILE, rows, fields)
    return added


def main() -> None:
    updated = apply_release_updates()
    added_factors = ensure_factor_rows()
    print(f"updated_rows={updated}")
    print("added_factor_rows=" + ",".join(added_factors))


if __name__ == "__main__":
    main()
