"""Read-only discovery of high-frequency material types in a purchase list.

This module deliberately separates three ideas that are often incorrectly
collapsed into one:

* a purchase line (the source fact and its frequency);
* a shopping/type group (a safe place to aggregate aliases and variants); and
* an exact SKU (which is never changed by this analysis).

The first pass is deterministic and conservative.  Only a small set of
well-known construction material heads are grouped across specifications.
Other rows remain separate and are emitted as fuzzy review candidates rather
than being silently merged.  The output is local, audit-friendly, and never
writes ERPNext.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
import difflib
import hashlib
import json
import math
from pathlib import Path
import re
import unicodedata
from typing import Any, Iterable, Mapping

from .procurement_batch_pilot import _excel_date, _number, _xlsx_rows
from .source_identity import (
    DEFAULT_SOURCE_DATASET,
    DEFAULT_SOURCE_DOCUMENT,
    DEFAULT_SOURCE_SHEET,
    make_source_record,
    source_row_hash,
)


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SOURCE_PATH = Path.home() / "Downloads" / "龙华项目物料待导入清单.xlsx"
DEFAULT_OUTPUT_ROOT = ROOT / ".runtime" / "material-master" / "frequency-discovery"
SOURCE_SHEET = "实际采购清单"
EXPECTED_HEADERS = ("日期", "材料", "数量", "单位", "工序序号", "市场单价")
VERSION = "procurement-frequency-discovery-v0.1"

_PACK_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:只|个|支|把|套|盒|包|片|根|条|张|瓶|桶|付)\s*/\s*(?:包|盒|箱)", re.I)
_MEASURE_RE = re.compile(
    r"(?:φ|Φ|ø|Ø|dn)?\s*\d+(?:\.\d+)?(?:\s*[x×*/]\s*\d+(?:\.\d+)?){0,4}\s*"
    r"(?:mm|cm|m|kg|g|a|w|v|寸|米|毫米|平方|号|级)?",
    re.I,
)
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_PUNCT_RE = re.compile(r"[^0-9a-z\u4e00-\u9fffφ]+", re.I)
_SPACE_RE = re.compile(r"\s+")
_BRANDS = (
    "飞利浦", "飞利普", "公牛", "公元", "世达", "东成", "起帆", "海螺", "大西洋",
    "华凌", "凌月", "立邦", "沪工", "得力", "普赛达",
)
_SERVICE_MARKERS = ("修理", "维修", "安装费", "人工费", "运费", "快递", "闪送", "顺丰")
_BUNDLE_MARKERS = ("一批", "若干", "杂项")

# A type head is only used for cross-specification grouping when its pattern
# is explicit.  Generic fallbacks keep their dimensions, preventing false
# merges such as a pump hose and a garden hose.
_CORE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("灭火器箱", re.compile(r"灭火器\s*(?:箱|箱子)", re.I)),
    ("灭火器", re.compile(r"(?<!箱)灭火器", re.I)),
    ("开口铜接线端子", re.compile(r"(?:开口\s*)?(?:铜接线端子|铜鼻子|开口端子)", re.I)),
    ("公牛五孔面板底座", re.compile(r"(?:五孔)?(?:面板底座|插座底座)", re.I)),
    ("公牛五孔插座面板开关", re.compile(r"五孔.*插座面板开关", re.I)),
    ("公牛五孔插座面板", re.compile(r"(?:五孔)?插座面板", re.I)),
    ("PPR内丝直接", re.compile(r"ppr.*(?:内丝|内牙).*?(?:直接|直通)", re.I)),
    ("PPR截止阀", re.compile(r"ppr.*截止阀", re.I)),
    ("PPR异径三通", re.compile(r"ppr.*(?:变|异径).*?(?:三通|tee)", re.I)),
    ("PPR三通", re.compile(r"ppr.*三通", re.I)),
    ("PPR弯头", re.compile(r"ppr.*弯头", re.I)),
    ("PPR直接", re.compile(r"ppr.*(?:直接|直通)", re.I)),
    ("PPR管", re.compile(r"ppr.*(?:管|管材)", re.I)),
    ("内六角螺钉", re.compile(r"内六角.*(?:螺钉|螺丝)", re.I)),
    ("六角螺栓", re.compile(r"(?<!内)(?:六角|外六角).*?(?:螺栓|螺丝)", re.I)),
    ("双头螺栓", re.compile(r"双头[^\u4e00-\u9fff]*(?:螺栓|螺丝)", re.I)),
    ("预埋螺栓", re.compile(r"预埋[^\u4e00-\u9fff]*(?:螺栓|螺丝)", re.I)),
    ("膨胀锚栓", re.compile(r"膨胀[^\u4e00-\u9fff]*(?:锚栓|膨胀栓)", re.I)),
    ("钻尾螺钉", re.compile(r"钻尾[^\u4e00-\u9fff]*(?:螺钉|螺丝)", re.I)),
    ("自攻螺钉", re.compile(r"自攻[^\u4e00-\u9fff]*(?:螺钉|螺丝)", re.I)),
    ("弹簧垫圈与平垫圈组合", re.compile(r"(?:弹垫|弹簧垫)[^\u4e00-\u9fff]*(?:平垫|平垫圈)|(?:平垫|平垫圈)[^\u4e00-\u9fff]*(?:弹垫|弹簧垫)", re.I)),
    ("螺纹钢", re.compile(r"螺纹钢|带肋钢筋|抗震热轧带肋钢筋", re.I)),
    ("钢筋", re.compile(r"钢筋", re.I)),
    ("高压胶管", re.compile(r"高压.*胶管", re.I)),
    ("药芯焊丝", re.compile(r"药芯焊丝", re.I)),
    ("焊条", re.compile(r"焊条", re.I)),
    ("钢丝绳防锈剂", re.compile(r"钢丝绳.*(?:喷雾|防锈剂|除锈剂)", re.I)),
    ("钢丝绳扣", re.compile(r"钢丝绳扣", re.I)),
    ("扣压钢丝绳", re.compile(r"扣压钢丝绳", re.I)),
    ("钢丝绳", re.compile(r"钢丝绳", re.I)),
    ("吊带", re.compile(r"吊带", re.I)),
    ("手拉葫芦保险扣", re.compile(r"手拉葫芦.*保险扣", re.I)),
    ("手拉葫芦", re.compile(r"手拉葫芦", re.I)),
    ("铝合金快速接头", re.compile(r"铝合金.*快速接头", re.I)),
    ("防锈漆", re.compile(r"防锈漆", re.I)),
    ("聚氨酯密封胶", re.compile(r"聚氨酯.*密封胶", re.I)),
    ("平面密封胶", re.compile(r"平面密封胶", re.I)),
    ("双排插拖线板", re.compile(r"双排.*(?:插板|插拖线板)", re.I)),
    ("背胶草皮", re.compile(r"背胶草(?:皮|坪)", re.I)),
    ("建筑用天然砂", re.compile(r"黄沙|天然砂|中砂|河沙", re.I)),
    ("混凝土/水泥砖", re.compile(r"(?:水泥砖|混凝土[^\u4e00-\u9fff]*砖)", re.I)),
    ("水泥垫块", re.compile(r"水泥垫块", re.I)),
    ("白水泥", re.compile(r"白水泥", re.I)),
    ("普通硅酸盐水泥", re.compile(r"(?:普通)?硅酸盐水泥|海螺.*水泥|(?:42(?:\.5)?|425)水泥", re.I)),
    ("尼龙膨胀管", re.compile(r"膨胀管", re.I)),
    ("排水软管", re.compile(r"排水[^\u4e00-\u9fff]*(?:软管|水管)", re.I)),
    ("园林/浇水软管", re.compile(r"(?:草坪|浇水|花园)[^\u4e00-\u9fff]*(?:软管|水管)", re.I)),
)

_UOM_ALIASES = {
    "个": "件", "只": "件", "片": "件", "根": "支", "付": "套",
    "公斤": "千克", "kg": "千克", "KG": "千克", "米": "米", "m": "米",
}


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = text.replace("Ｘ", "x").replace("×", "x").replace("＊", "*")
    text = text.replace("Ø", "Φ").replace("ø", "φ")
    return _SPACE_RE.sub(" ", text)


def normalize_uom(value: Any) -> str:
    raw = normalize_text(value)
    return _UOM_ALIASES.get(raw, raw)


def _strip_brand_packaging(text: str) -> str:
    output = text
    for brand in _BRANDS:
        output = output.replace(brand, "")
    output = _PACK_RE.sub("", output)
    output = re.sub(r"\s+", "", output)
    return output


def _safe_core(text: str) -> tuple[str, bool]:
    clean = _strip_brand_packaging(text)
    for core, pattern in _CORE_PATTERNS:
        if pattern.search(clean):
            return core, True
    # Do not strip dimensions in the fallback.  Unknown items are therefore
    # not silently grouped merely because they share a vague noun.
    fallback = _PUNCT_RE.sub("", clean.casefold())
    return fallback or normalize_text(text), False


def _spec_signature(text: str, core: str) -> str:
    clean = _strip_brand_packaging(text)
    if core and core in clean:
        clean = clean.replace(core, "")
    clean = _PUNCT_RE.sub(" ", clean.casefold())
    clean = _SPACE_RE.sub(" ", clean).strip()
    return clean or "(无额外规格)"


def _json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DiscoveryRow:
    source_row: int
    purchase_date: str
    raw_name: str
    qty: float | None
    raw_uom: str
    normalized_uom: str
    procedure_sequence: str
    market_unit_price: float | None
    core_type: str
    safe_core: bool
    spec_signature: str
    flags: tuple[str, ...]
    source_dataset: str = DEFAULT_SOURCE_DATASET
    source_document: str = DEFAULT_SOURCE_DOCUMENT
    source_sheet: str = DEFAULT_SOURCE_SHEET
    source_row_hash: str = ""


def read_source_rows(path: Path) -> list[DiscoveryRow]:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file() or resolved.suffix.casefold() != ".xlsx":
        raise FileNotFoundError(f"采购清单不存在或不是 xlsx：{resolved}")
    rows = _xlsx_rows(resolved, SOURCE_SHEET)
    if not rows:
        raise ValueError("实际采购清单为空")
    headers = tuple(normalize_text(value) for value in rows[0][:6])
    if headers != EXPECTED_HEADERS:
        raise ValueError(f"实际采购清单表头不匹配：{headers}")
    selected: list[DiscoveryRow] = []
    for source_row, values in enumerate(rows[1:], start=2):
        padded = [*values, "", "", "", "", "", ""][:6]
        name = normalize_text(padded[1])
        if not name:
            continue
        qty = _number(padded[2])
        uom = normalize_text(padded[3])
        flags: list[str] = []
        if qty is None or qty <= 0:
            flags.append("missing_or_invalid_quantity")
        if not uom:
            flags.append("missing_uom")
        if any(marker in name for marker in _SERVICE_MARKERS):
            flags.append("service_or_logistics")
        if any(marker in name for marker in _BUNDLE_MARKERS):
            flags.append("bundled_or_vague")
        core, safe = _safe_core(name)
        selected.append(DiscoveryRow(
            source_row=source_row,
            purchase_date=_excel_date(padded[0]),
            raw_name=name,
            qty=qty,
            raw_uom=uom,
            normalized_uom=normalize_uom(uom),
            procedure_sequence=normalize_text(padded[4]),
            market_unit_price=_number(padded[5]),
            core_type=core,
            safe_core=safe,
            spec_signature=_spec_signature(name, core),
            flags=tuple(flags),
            source_dataset=DEFAULT_SOURCE_DATASET,
            source_document=DEFAULT_SOURCE_DOCUMENT,
            source_sheet=SOURCE_SHEET,
            source_row_hash=source_row_hash({
                "purchase_date": _excel_date(padded[0]),
                "raw_name": name,
                "qty": qty,
                "raw_uom": uom,
                "procedure_sequence": normalize_text(padded[4]),
                "market_unit_price": _number(padded[5]),
            }),
        ))
    if not selected:
        raise ValueError("实际采购清单没有可读取的物料行")
    return selected


def _event_key(row: DiscoveryRow) -> tuple[str, str, str, str]:
    # This is intentionally an approximate event count, not a replacement for
    # line_count.  It prevents duplicated exports on the same date/process
    # from dominating the ranking while leaving the raw count auditable.
    return (row.purchase_date, row.procedure_sequence, row.raw_name.casefold(), row.normalized_uom)


def _cluster_id(key: str, source_rows: Iterable[int]) -> str:
    first = min(source_rows)
    return f"PF-{first:04d}-{_json_hash(key)[:8].upper()}"


def _row_json(row: DiscoveryRow) -> dict[str, Any]:
    value = asdict(row)
    value["flags"] = list(row.flags)
    return value


def build_clusters(rows: list[DiscoveryRow]) -> list[dict[str, Any]]:
    grouped: dict[tuple[bool, str], list[DiscoveryRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.safe_core, row.core_type)].append(row)
    output: list[dict[str, Any]] = []
    for (safe, core), members in sorted(grouped.items(), key=lambda item: min(row.source_row for row in item[1])):
        raw_names = list(dict.fromkeys(row.raw_name for row in members))
        variants = list(dict.fromkeys(row.spec_signature for row in members))
        event_keys = {_event_key(row) for row in members}
        uoms = sorted({row.normalized_uom for row in members if row.normalized_uom})
        qty_by_uom: dict[str, float] = defaultdict(float)
        total_value = 0.0
        priced_rows = 0
        for row in members:
            if row.qty is not None:
                qty_by_uom[row.normalized_uom or "(缺失)"] += row.qty
            if row.qty is not None and row.market_unit_price is not None:
                total_value += row.qty * row.market_unit_price
                priced_rows += 1
        flags = sorted({flag for row in members for flag in row.flags})
        line_count = len(members)
        alias_count = len(raw_names)
        variant_count = len(variants)
        score = math.log1p(line_count) * (1.0 + math.log1p(max(0, variant_count - 1))) * (1.0 + 0.25 * math.log1p(max(0, alias_count - 1)))
        if not safe:
            queue = "保持独立/待复核"
        elif "service_or_logistics" in flags or "bundled_or_vague" in flags:
            queue = "非标准物料或待复核"
        elif len(uoms) > 1:
            queue = "单位冲突/待复核"
        elif variant_count > 1:
            queue = "多规格整合候选"
        elif alias_count > 1:
            queue = "别名归并候选"
        else:
            queue = "单规格标准类型"
        output.append({
            "cluster_id": _cluster_id(f"{safe}:{core}", [row.source_row for row in members]),
            "standard_type_candidate": core,
            "grouping_confidence": "high" if safe else "not_auto_grouped",
            "auto_grouped_across_specs": safe,
            "queue": queue,
            "source_rows": [row.source_row for row in members],
            "source_dataset": DEFAULT_SOURCE_DATASET,
            "source_document": DEFAULT_SOURCE_DOCUMENT,
            "source_sheet": SOURCE_SHEET,
            "source_records": [
                make_source_record(
                    row.source_row,
                    dataset=row.source_dataset,
                    document=row.source_document,
                    sheet=row.source_sheet,
                    row_hash=row.source_row_hash,
                )
                for row in members
            ],
            "raw_names": raw_names,
            "line_count": line_count,
            "distinct_event_count_approx": len(event_keys),
            "alias_count": alias_count,
            "variant_count": variant_count,
            "normalized_uoms": uoms,
            "quantity_by_uom": dict(sorted(qty_by_uom.items())),
            "priced_line_count": priced_rows,
            "market_value_sum": round(total_value, 6),
            "source_flags": flags,
            "integration_priority_score": round(score, 6),
            "frequency_metric_note": "line_count为原始行频次；distinct_event_count_approx为日期+工序+名称+单位去重后的近似采购事件数。",
        })
    ranked = sorted(output, key=lambda row: (-row["integration_priority_score"], -row["line_count"], row["cluster_id"]))
    frequency_ranked = sorted(
        ranked,
        key=lambda row: (-row["distinct_event_count_approx"], -row["line_count"], -row["variant_count"], row["cluster_id"]),
    )
    frequency_ranks = {row["cluster_id"]: rank for rank, row in enumerate(frequency_ranked, start=1)}
    for rank, row in enumerate(ranked, start=1):
        row["integration_rank"] = rank
        row["frequency_rank"] = frequency_ranks[row["cluster_id"]]
    return ranked


def build_fuzzy_review_candidates(clusters: list[dict[str, Any]], *, limit: int = 500) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    # Blocking by the first two Chinese characters keeps this bounded and
    # avoids an O(n^2) comparison over all source lines.
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for cluster in clusters:
        if cluster["grouping_confidence"] == "high":
            continue
        key = re.sub(r"[^\u4e00-\u9fff]", "", cluster["standard_type_candidate"])[:2] or cluster["standard_type_candidate"][:2]
        blocks[key].append(cluster)
    for block in blocks.values():
        for index, left in enumerate(block):
            for right in block[index + 1:]:
                if left["standard_type_candidate"] == right["standard_type_candidate"]:
                    continue
                score = difflib.SequenceMatcher(None, left["standard_type_candidate"], right["standard_type_candidate"]).ratio()
                if score < 0.76:
                    continue
                candidates.append({
                    "left_cluster_id": left["cluster_id"],
                    "right_cluster_id": right["cluster_id"],
                    "similarity": round(score, 6),
                    "left_type": left["standard_type_candidate"],
                    "right_type": right["standard_type_candidate"],
                    "left_rows": left["source_rows"],
                    "right_rows": right["source_rows"],
                    "decision": "人工复核，不自动合并",
                    "reason": "仅相似度不足以证明同一标准类型；需核对用途、结构、材质、单位和GPC范围。",
                })
    return sorted(candidates, key=lambda row: (-row["similarity"], row["left_cluster_id"], row["right_cluster_id"]))[:limit]


def discover(source_path: Path = DEFAULT_SOURCE_PATH, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    rows = read_source_rows(source_path)
    clusters = build_clusters(rows)
    fuzzy = build_fuzzy_review_candidates(clusters)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "source-rows.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(_row_json(row), ensure_ascii=False) + "\n")
    with (output_root / "clusters.jsonl").open("w", encoding="utf-8") as handle:
        for row in clusters:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (output_root / "fuzzy-review-candidates.jsonl").open("w", encoding="utf-8") as handle:
        for row in fuzzy:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "version": VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_path": str(Path(source_path).expanduser().resolve()),
        "source_sheet": SOURCE_SHEET,
        "source_row_count": len(rows),
        "unique_raw_name_count": len({row.raw_name for row in rows}),
        "cluster_count": len(clusters),
        "safe_cluster_count": sum(1 for row in clusters if row["grouping_confidence"] == "high"),
        "multi_attribute_candidate_count": sum(1 for row in clusters if row["grouping_confidence"] == "high" and row["variant_count"] > 1),
        "ready_multi_attribute_cluster_count": sum(1 for row in clusters if row["queue"] == "多规格整合候选"),
        "uom_conflict_candidate_count": sum(1 for row in clusters if row["queue"] == "单位冲突/待复核"),
        "alias_candidate_cluster_count": sum(1 for row in clusters if row["queue"] == "别名归并候选"),
        "review_cluster_count": sum(1 for row in clusters if row["grouping_confidence"] != "high" or "待复核" in row["queue"]),
        "fuzzy_review_candidate_count": len(fuzzy),
        "service_or_logistics_line_count": sum("service_or_logistics" in row.flags for row in rows),
        "bundled_or_vague_line_count": sum("bundled_or_vague" in row.flags for row in rows),
        "uom_conflict_cluster_count": sum(len(row["normalized_uoms"]) > 1 for row in clusters),
        "writes_erpnext": False,
        "notes": [
            "这是发现和排序结果，不是物料主数据发布结果。",
            "同一标准类型的不同规格仍然是不同SKU。",
            "非显式类型头的项目保持独立并进入复核，不以模糊相似度自动合并。",
        ],
    }
    (output_root / "discovery-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summary, "clusters": clusters, "fuzzy_review_candidates": fuzzy, "output_root": str(output_root)}
