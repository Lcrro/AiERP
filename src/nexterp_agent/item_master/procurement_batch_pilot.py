"""Auditable batch pilot for normalising field purchase lists against GPC.

The pilot is intentionally isolated from ERPNext.  It reads one allow-listed
workbook, preserves every source row, analyses duplicate/type clusters once,
constrains DeepSeek to imported GPC codes and the fixed procurement-template
catalog, then writes local review artefacts under ``.runtime``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence
import unicodedata
from uuid import uuid4
import zipfile
from xml.etree import ElementTree as ET

from pydantic import BaseModel, ConfigDict, Field

from .procurement_templates import ProcurementTemplateRegistry, ProcurementTypeProfile
from .procurement_batch_review import ProcurementReviewRuleCatalog
from .reference_catalog import GpcReferenceIndex


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LONGHUA_WORKBOOK_PATH = Path.home() / "Downloads" / "龙华项目物料待导入清单.xlsx"
DEFAULT_RUNTIME_ROOT = ROOT / ".runtime" / "material-master" / "batch-pilot"
DEFAULT_GPC_RUNTIME_ROOT = ROOT / ".runtime" / "gpc-reference"
DEFAULT_GPC_VERSION = "2026-05"
DEFAULT_PLACEMENTS_PATH = ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl"
DEFAULT_TYPE_PROFILES_PATH = ROOT / ".runtime" / "material-master" / "gpc-procurement-type-profiles.jsonl"
DEFAULT_TEMPLATE_CATALOG_PATH = ROOT / "data" / "material_master" / "procurement_template_catalog_v0_1.json"
DEFAULT_DEEPSEEK_PRICING_PATH = ROOT / "data" / "material_master" / "deepseek_pricing_v0_1.json"
SOURCE_SHEET = "实际采购清单"
EXPECTED_HEADERS = ("日期", "材料", "数量", "单位", "工序序号", "市场单价")
PROMPT_VERSION = "longhua-gpc-batch-v0.5"
MAX_PILOT_ROWS = 100
DEFAULT_LLM_CHUNK_SIZE = 50


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProcurementSourceRow(_StrictModel):
    source_row: int = Field(ge=2)
    purchase_date: str = ""
    raw_name: str = Field(min_length=1)
    qty: float | None = None
    raw_uom: str = ""
    procedure_sequence: str = ""
    market_unit_price: float | None = None
    exact_key: str = Field(min_length=1)
    cluster_key: str = Field(min_length=1)
    flags: list[str] = Field(default_factory=list)


class ProcurementWorkbookSnapshot(_StrictModel):
    source_path: str
    source_sha256: str
    source_sheet: str
    source_row_count: int
    selected_row_count: int
    selected_start_row: int
    selected_end_row: int
    rows: list[ProcurementSourceRow]


class ProcurementCluster(_StrictModel):
    cluster_id: str
    cluster_key: str
    representative_name: str
    source_rows: list[int]
    raw_names: list[str]
    exact_keys: list[str]
    row_count: int
    unique_variant_count: int
    flags: list[str] = Field(default_factory=list)
    golden_material_id: str = ""


class ClusterFact(_StrictModel):
    cluster_id: str
    standard_query: str
    standard_type: str
    explicit_facts: dict[str, str] = Field(default_factory=dict)
    search_synonyms: list[str] = Field(default_factory=list)
    is_service: bool = False
    is_bundled_line: bool = False
    ambiguity_note: str = ""


class ClusterFactBatch(_StrictModel):
    rows: list[ClusterFact]


class ClusterJudgement(_StrictModel):
    cluster_id: str
    selected_gpc_code: str = ""
    standard_type: str
    main_template_id: str = ""
    constraint_ids: list[str] = Field(default_factory=list)
    sku_identity_fact_keys: list[str] = Field(default_factory=list)
    transaction_fact_keys: list[str] = Field(default_factory=list)
    offer_fact_keys: list[str] = Field(default_factory=list)
    stock_uom: str = "件"
    confidence: Literal["high", "medium", "low"] = "low"
    reason: str
    questions: list[str] = Field(default_factory=list)


class ClusterJudgementBatch(_StrictModel):
    rows: list[ClusterJudgement]


@dataclass(frozen=True)
class LlmJsonResult:
    data: dict[str, Any] | list[Any]
    model: str
    usage: dict[str, int]
    request_id: str = ""


DeepSeekClient = Callable[[list[dict[str, str]], int], LlmJsonResult]
ProgressCallback = Callable[[str, int, str, Mapping[str, Any]], None]


_XML_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
_DOC_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")
_MEASURE_RE = re.compile(
    r"(?:φ|Φ|ø|Ø|dn|m)?\s*\d+(?:\.\d+)?(?:\s*[x×*/]\s*\d+(?:\.\d+)?){0,4}\s*"
    r"(?:mm|cm|m|kg|g|a|w|v|寸|米|毫米|平方|只|个|支|把|套|盒|包|片|根|条|张|瓶|桶|付)?",
    re.IGNORECASE,
)
_PACK_RE = re.compile(r"\d+\s*(?:只|个|支|把|套|盒|包|片|根|条|张|瓶|桶|付)\s*/\s*(?:包|盒|箱)", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^0-9a-z\u4e00-\u9fffφ]+", re.IGNORECASE)
_BRANDS = ("飞利浦", "公牛", "公元", "世达", "东成", "起帆", "海螺", "大西洋", "华凌", "凌月")
_SERVICE_MARKERS = ("修理", "维修", "安装费", "人工费", "运费")
_BUNDLE_MARKERS = ("一批", "若干", "杂项")
_UOM_ALIASES = {
    "米 ": "米", "kg": "千克", "KG": "千克", "公斤": "千克",
    "个": "件", "只": "件", "片": "件", "根": "支", "付": "套",
}
_ALLOWED_STOCK_UOMS = {
    "件", "套", "支", "米", "平方米", "千克", "吨", "包", "盒", "台", "把", "瓶", "桶", "张", "卷",
}
_TEMPLATE_DEFAULT_UOM = {
    "standard_component": "件",
    "linear_cut_material": "米",
    "sheet_roll_material": "平方米",
    "bulk_measured_material": "吨",
    "packaged_consumable": "包",
    "equipment_tool": "台",
    "model_specific_spare": "件",
    "custom_fabricated": "套",
    "kit_assembly": "套",
    "general_finished_good": "件",
}
_GPC_RETRIEVAL_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("扫把", ("Brooms/ Brushes",)),
    ("灰斗", ("Brooms/ Brushes", "Cleaning Aids Accessories")),
    ("大小头", ("Valves/Fittings - Water and Gas",)),
    ("弯头", ("Valves/Fittings - Water and Gas",)),
    ("三通", ("Valves/Fittings - Water and Gas",)),
    ("直接", ("Valves/Fittings - Water and Gas",)),
    ("活接头", ("Valves/Fittings - Water and Gas",)),
    ("截止阀", ("Valves/Fittings - Water and Gas",)),
    ("快速接头", ("Valves/Fittings - Water and Gas",)),
    ("法兰", ("Pipes/Tubing Flanges",)),
    ("钢卡", ("Hose Clamps",)),
    ("卡箍", ("Hose Clamps",)),
    ("水带", ("Hoses", "Fire Fighting Equipment")),
    ("软管", ("Hoses",)),
    ("ppr", ("Pipes/Tubing - Water, Gas, Central heating", "Valves/Fittings - Water and Gas")),
    ("管", ("Pipes/Tubing - Water, Gas, Central heating",)),
    ("麻绳", ("Ropes/Chains/Cables (Fixings/Fasteners)",)),
    ("尼龙绳", ("Ropes/Chains/Cables (Fixings/Fasteners)",)),
    ("变频", ("Inverters",)),
    ("抽油机", ("Pumps", "Industrial Fluid Pumps/Systems")),
    ("热熔器", ("Welding/Blow Torches (Powered)",)),
    ("灭火器", ("Fire Extinguishers - Pressurised", "Fire Fighting Equipment")),
    ("水泥砖", ("Brick/Block",)),
    ("水泥", ("Cement",)),
    ("黄沙", ("Sand (DIY)",)),
    ("铁板", ("Steel (Formed)",)),
    ("角铁", ("Steel (Formed)",)),
    ("焊管", ("Steel (Formed)", "Pipes/Tubing")),
    ("镀锌管", ("Steel (Formed)", "Pipes/Tubing")),
    ("铁丝", ("Wire", "Steel (Formed)")),
    ("角磨机", ("Angle Grinders (Powered)",)),
    ("切割片", ("Grinders/Sharpeners/Scrapers/Sanders - Consumables",)),
    ("接地线", ("Electrical Wires", "Bonding/Grounding Braid")),
    ("电缆", ("Electrical Wires",)),
    ("铜鼻子", ("Terminal Blocks/Strips",)),
    ("焊条", ("Welding/Blow Torches Rods/Wire/Solder - Consumables",)),
    ("弹垫", ("Washers (Fixings/Fasteners)",)),
    ("平垫", ("Washers (Fixings/Fasteners)",)),
    ("螺丝", ("Screws",)),
    ("螺栓", ("Bolts/Threaded Rods",)),
    ("扎带", ("Cable Clips/Grommets/Ties",)),
    ("草坪", ("Artificial Grass",)),
    ("排插", ("Extension/Power Supply Cords",)),
    ("插拖线板", ("Extension/Power Supply Cords",)),
    ("雨衣", ("Protective Wear Variety Packs",)),
    ("雨伞", ("Umbrellas - Personal",)),
    ("座椅", ("Chairs",)),
    ("凳子", ("Chairs",)),
    ("菜刀", ("Knives",)),
    ("手套", ("Gloves",)),
    ("靠尺", ("Rulers (DIY) (Non Powered)",)),
    ("括尺", ("Rulers (DIY) (Non Powered)",)),
    ("割枪", ("Welding/Blow Torches (Powered)",)),
    ("氧气管", ("Hoses",)),
    ("乙炔管", ("Hoses",)),
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _normalise_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = text.replace("×", "x").replace("Ｘ", "x").replace("Ø", "Φ").replace("ø", "φ")
    return re.sub(r"\s+", " ", text)


def _exact_key(value: Any) -> str:
    return _PUNCT_RE.sub("", _normalise_text(value).casefold())


def _cluster_key(value: Any) -> str:
    text = _normalise_text(value).casefold()
    for brand in _BRANDS:
        text = text.replace(brand.casefold(), "")
    text = _PACK_RE.sub("", text)
    text = _MEASURE_RE.sub("", text)
    text = re.sub(r"\b(?:型|号)\b", "", text)
    compact = _PUNCT_RE.sub("", text)
    return compact or _exact_key(value)


def _column_number(reference: str) -> int:
    match = _CELL_REF_RE.fullmatch(reference)
    if not match:
        raise ValueError(f"invalid XLSX cell reference: {reference}")
    number = 0
    for char in match.group(1):
        number = number * 26 + ord(char) - ord("A") + 1
    return number


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return ["".join(node.text or "" for node in item.findall(".//main:t", _XML_NS)) for item in root]


def _xlsx_sheet_target(archive: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relation_id = ""
    for sheet in workbook.findall(".//main:sheet", _XML_NS):
        if sheet.get("name") == sheet_name:
            relation_id = str(sheet.get(_DOC_REL_ID) or "")
            break
    if not relation_id:
        raise ValueError(f"workbook sheet not found: {sheet_name}")
    relations = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    for relation in relations.findall("rel:Relationship", _REL_NS):
        if relation.get("Id") != relation_id:
            continue
        target = str(relation.get("Target") or "").replace("\\", "/")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = "xl/" + target.lstrip("./")
        if ".." in Path(target).parts:
            raise ValueError("workbook sheet relationship escapes archive root")
        return target
    raise ValueError(f"workbook relationship missing for sheet: {sheet_name}")


def _xlsx_rows(path: Path, sheet_name: str) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        shared = _xlsx_shared_strings(archive)
        target = _xlsx_sheet_target(archive, sheet_name)
        root = ET.fromstring(archive.read(target))
    output: list[list[str]] = []
    for row in root.findall(".//main:sheetData/main:row", _XML_NS):
        values: dict[int, str] = {}
        for cell in row.findall("main:c", _XML_NS):
            reference = str(cell.get("r") or "")
            column = _column_number(reference)
            cell_type = str(cell.get("t") or "")
            if cell_type == "inlineStr":
                value = "".join(node.text or "" for node in cell.findall(".//main:t", _XML_NS))
            else:
                value_node = cell.find("main:v", _XML_NS)
                raw = value_node.text if value_node is not None and value_node.text is not None else ""
                if cell_type == "s" and raw:
                    index = int(raw)
                    value = shared[index] if 0 <= index < len(shared) else ""
                elif cell_type == "b":
                    value = "TRUE" if raw == "1" else "FALSE"
                else:
                    value = raw
            values[column] = value
        width = max(values, default=0)
        output.append([values.get(index, "") for index in range(1, width + 1)])
    return output


def _number(value: Any) -> float | None:
    text = _normalise_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _excel_date(value: Any) -> str:
    number = _number(value)
    if number is None:
        return _normalise_text(value)
    return (datetime(1899, 12, 30) + timedelta(days=number)).date().isoformat()


def load_purchase_workbook(path: Path, *, limit: int = MAX_PILOT_ROWS) -> ProcurementWorkbookSnapshot:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file() or resolved.suffix.casefold() != ".xlsx":
        raise FileNotFoundError(f"采购清单不存在或不是 xlsx：{resolved}")
    if limit < 1 or limit > MAX_PILOT_ROWS:
        raise ValueError(f"试运行行数必须在 1 到 {MAX_PILOT_ROWS} 之间")
    source_bytes = resolved.read_bytes()
    rows = _xlsx_rows(resolved, SOURCE_SHEET)
    if not rows:
        raise ValueError("实际采购清单为空")
    headers = tuple(_normalise_text(value) for value in rows[0][: len(EXPECTED_HEADERS)])
    if headers != EXPECTED_HEADERS:
        raise ValueError(f"实际采购清单表头不匹配：{headers}")
    selected: list[ProcurementSourceRow] = []
    for source_row, values in enumerate(rows[1:], start=2):
        padded = [*values, "", "", "", "", "", ""][:6]
        raw_name = _normalise_text(padded[1])
        if not raw_name:
            continue
        qty = _number(padded[2])
        uom = _normalise_text(padded[3])
        flags = []
        if qty is None or qty <= 0:
            flags.append("missing_or_invalid_quantity")
            qty = None
        if not uom:
            flags.append("missing_uom")
        if _number(padded[5]) is None:
            flags.append("missing_market_price")
        if any(marker in raw_name for marker in _SERVICE_MARKERS):
            flags.append("service_line")
        if any(marker in raw_name for marker in _BUNDLE_MARKERS):
            flags.append("bundled_line")
        selected.append(ProcurementSourceRow(
            source_row=source_row,
            purchase_date=_excel_date(padded[0]),
            raw_name=raw_name,
            qty=qty,
            raw_uom=uom,
            procedure_sequence=_normalise_text(padded[4]),
            market_unit_price=_number(padded[5]),
            exact_key=_exact_key(raw_name),
            cluster_key=_cluster_key(raw_name),
            flags=flags,
        ))
        if len(selected) >= limit:
            break
    if not selected:
        raise ValueError("实际采购清单没有可读取的物料行")
    return ProcurementWorkbookSnapshot(
        source_path=str(resolved),
        source_sha256=_sha256_bytes(source_bytes),
        source_sheet=SOURCE_SHEET,
        source_row_count=sum(1 for row in rows[1:] if len(row) > 1 and _normalise_text(row[1])),
        selected_row_count=len(selected),
        selected_start_row=selected[0].source_row,
        selected_end_row=selected[-1].source_row,
        rows=selected,
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def build_clusters(
    rows: Sequence[ProcurementSourceRow],
    *,
    golden_placements: Iterable[Mapping[str, Any]] = (),
) -> list[ProcurementCluster]:
    golden_by_row: dict[int, str] = {}
    for placement in golden_placements:
        material_id = _normalise_text(placement.get("material_id"))
        for source_row in placement.get("source_rows") or ():
            try:
                golden_by_row[int(source_row)] = material_id
            except (TypeError, ValueError):
                continue
    golden_by_exact: dict[str, str] = {}
    for row in rows:
        material_id = golden_by_row.get(row.source_row, "")
        if material_id:
            golden_by_exact[row.exact_key] = material_id
    grouped: dict[str, list[ProcurementSourceRow]] = defaultdict(list)
    for row in rows:
        golden_id = golden_by_row.get(row.source_row, "") or golden_by_exact.get(row.exact_key, "")
        grouped[f"golden:{golden_id}" if golden_id else row.cluster_key].append(row)
    clusters = []
    for cluster_key, members in sorted(grouped.items(), key=lambda item: min(row.source_row for row in item[1])):
        effective_cluster_key = members[0].cluster_key if cluster_key.startswith("golden:") else cluster_key
        source_rows = [row.source_row for row in members]
        raw_names = list(dict.fromkeys(row.raw_name for row in members))
        exact_keys = list(dict.fromkeys(row.exact_key for row in members))
        golden_ids = {
            golden_by_row.get(row.source_row, "") or golden_by_exact.get(row.exact_key, "")
            for row in members
            if golden_by_row.get(row.source_row, "") or golden_by_exact.get(row.exact_key, "")
        }
        flags = sorted({flag for row in members for flag in row.flags})
        clusters.append(ProcurementCluster(
            cluster_id=f"CL-{min(source_rows):04d}-{_json_hash(effective_cluster_key)[:8].upper()}",
            cluster_key=effective_cluster_key,
            representative_name=raw_names[0],
            source_rows=source_rows,
            raw_names=raw_names,
            exact_keys=exact_keys,
            row_count=len(members),
            unique_variant_count=len(exact_keys),
            flags=flags,
            golden_material_id=next(iter(golden_ids)) if len(golden_ids) == 1 else "",
        ))
    return clusters


class _ResultCache:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def read(self, phase: str, key: str) -> dict[str, Any] | None:
        path = self.root / phase / f"{key}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def write(self, phase: str, key: str, value: Mapping[str, Any]) -> None:
        directory = self.root / phase
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{key}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


class _TokenLedger:
    def __init__(self, pricing_path: Path = DEFAULT_DEEPSEEK_PRICING_PATH) -> None:
        self.calls: list[dict[str, Any]] = []
        self.pricing = json.loads(Path(pricing_path).read_text(encoding="utf-8")) if Path(pricing_path).is_file() else {}

    def record(self, phase: str, result: LlmJsonResult, *, item_count: int, request_hash: str) -> None:
        self.calls.append({
            "phase": phase,
            "model": result.model,
            "request_id": result.request_id,
            "request_hash": request_hash,
            "item_count": item_count,
            "usage": dict(result.usage),
        })

    def summary(self) -> dict[str, Any]:
        usage: Counter[str] = Counter()
        for call in self.calls:
            usage.update({key: int(value) for key, value in call.get("usage", {}).items()})
        configured_models = dict(self.pricing.get("models") or {})
        env_prices = {
            "cache_hit_input": _number(os.getenv("DEEPSEEK_CACHE_HIT_PRICE_PER_MILLION_CNY")),
            "cache_miss_input": _number(os.getenv("DEEPSEEK_CACHE_MISS_PRICE_PER_MILLION_CNY")),
            "output": _number(os.getenv("DEEPSEEK_OUTPUT_PRICE_PER_MILLION_CNY")),
        }
        has_env_prices = all(value is not None for value in env_prices.values())
        cost = 0.0
        priced_calls = 0
        for call in self.calls:
            call_usage = call.get("usage", {})
            prices = env_prices if has_env_prices else configured_models.get(str(call.get("model") or ""), {})
            if not prices or any(_number(prices.get(key)) is None for key in ("cache_hit_input", "cache_miss_input", "output")):
                continue
            hit = int(call_usage.get("prompt_cache_hit_tokens", 0))
            miss = int(call_usage.get("prompt_cache_miss_tokens", int(call_usage.get("prompt_tokens", 0)) - hit))
            output = int(call_usage.get("completion_tokens", 0))
            cost += (
                hit * float(prices["cache_hit_input"])
                + miss * float(prices["cache_miss_input"])
                + output * float(prices["output"])
            ) / 1_000_000
            priced_calls += 1
        return {
            "call_count": len(self.calls),
            "usage": dict(usage),
            "estimated_cost_cny": round(cost, 6) if priced_calls == len(self.calls) and self.calls else (0.0 if not self.calls else None),
            "pricing_configured": bool(not self.calls or priced_calls == len(self.calls)),
            "pricing_version": self.pricing.get("pricing_version", "environment_override" if has_env_prices else ""),
            "pricing_source_url": self.pricing.get("source_url", ""),
        }


def _default_deepseek_client(messages: list[dict[str, str]], max_tokens: int) -> LlmJsonResult:
    from nexterp_agent.agent_runtime.deepseek_material_request import call_deepseek_json_with_usage

    result = call_deepseek_json_with_usage(
        messages,
        max_tokens=max_tokens,
        thinking={"type": "disabled"},
    )
    return LlmJsonResult(
        data=result.data,
        model=result.model,
        usage=result.usage,
        request_id=result.request_id,
    )


def _local_fact(cluster: ProcurementCluster) -> ClusterFact:
    facts: dict[str, str] = {}
    source = "；".join(cluster.raw_names)
    dimension = re.search(r"(?:φ|Φ|dn|m)?\s*\d+(?:\.\d+)?(?:\s*[x×*/]\s*\d+(?:\.\d+)?){0,4}\s*(?:mm|cm|m|寸|平方)?", source, re.IGNORECASE)
    if dimension:
        facts["规格"] = _normalise_text(dimension.group(0))
    grade = re.search(r"(?:\d\.\d级|hrb\d+e?|q\d+|j\d+|t\d+)", source, re.IGNORECASE)
    if grade:
        facts["等级/型号"] = _normalise_text(grade.group(0)).upper()
    return ClusterFact(
        cluster_id=cluster.cluster_id,
        standard_query=cluster.cluster_key,
        standard_type=re.sub(r"[｜|].*$", "", cluster.representative_name),
        explicit_facts=facts,
        is_service="service_line" in cluster.flags,
        is_bundled_line="bundled_line" in cluster.flags,
    )


def _normalise_fact_row(raw: Any, cluster: ProcurementCluster) -> ClusterFact | None:
    if not isinstance(raw, Mapping) or str(raw.get("cluster_id") or "") != cluster.cluster_id:
        return None
    local = _local_fact(cluster)
    explicit = raw.get("explicit_facts")
    def fact_value(value: Any) -> str:
        if isinstance(value, list):
            return "/".join(dict.fromkeys(filter(None, (fact_value(item) for item in value))))
        normalised = _normalise_text(value)
        if normalised.casefold() in {"true", "yes"}:
            return "是"
        if normalised.casefold() in {"false", "no"}:
            return "否"
        return normalised

    facts = {
        _normalise_text(key): fact_value(value)
        for key, value in (explicit.items() if isinstance(explicit, Mapping) else ())
        if _normalise_text(key) and fact_value(value)
    }
    synonyms = raw.get("search_synonyms")
    return ClusterFact(
        cluster_id=cluster.cluster_id,
        standard_query=_normalise_text(raw.get("standard_query")) or local.standard_query,
        standard_type=_normalise_text(raw.get("standard_type")) or local.standard_type,
        explicit_facts=facts or local.explicit_facts,
        search_synonyms=[_normalise_text(value) for value in (synonyms if isinstance(synonyms, list) else []) if _normalise_text(value)][:5],
        # Service/bundle boundaries are deterministic safety decisions.  A
        # model must not turn a fabricated stock item (for example 加工角铁)
        # into a non-material service or bypass a bundled-line review.
        is_service=local.is_service,
        is_bundled_line=local.is_bundled_line,
        ambiguity_note=_normalise_text(raw.get("ambiguity_note")),
    )


def _normalise_judgement_row(raw: Any, cluster_id: str) -> ClusterJudgement | None:
    if not isinstance(raw, Mapping) or str(raw.get("cluster_id") or "") != cluster_id:
        return None
    list_fields = {}
    for field in (
        "constraint_ids", "sku_identity_fact_keys", "transaction_fact_keys", "offer_fact_keys", "questions",
    ):
        values = raw.get(field)
        list_fields[field] = [
            _normalise_text(value) for value in (values if isinstance(values, list) else []) if _normalise_text(value)
        ]
    confidence = _normalise_text(raw.get("confidence")).lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "low"
    return ClusterJudgement(
        cluster_id=cluster_id,
        selected_gpc_code=_normalise_text(raw.get("selected_gpc_code")),
        standard_type=_normalise_text(raw.get("standard_type")) or "未命名物料",
        main_template_id=_normalise_text(raw.get("main_template_id")),
        stock_uom=_normalise_text(raw.get("stock_uom")) or "件",
        confidence=confidence,
        reason=_normalise_text(raw.get("reason")) or "模型未返回判定依据",
        **list_fields,
    )


def _fact_messages(clusters: Sequence[ProcurementCluster]) -> list[dict[str, str]]:
    payload = [{
        "cluster_id": item.cluster_id,
        "representative_name": item.representative_name,
        "variants": item.raw_names,
        "source_rows": item.source_rows,
    } for item in clusters]
    return [
        {"role": "system", "content": (
            "你是土木施工采购清单事实整理员。逐个 cluster 规范现场叫法，只提取原文明确出现的事实。"
            "不得虚构品牌、型号、材质、强度、尺寸、性能或 GPC 编码；不得合并或遗漏 cluster。"
            "standard_query 是用于检索目录的简短品类词，standard_type 是不含品牌和纯尺寸的中文标准类型名。"
            "search_synonyms 可同时给出中文同义词和最可能的 GPC 英文官方类目词，但不能写 GPC 编码。"
            "同一 cluster 的不同尺寸是变体，不得展开笛卡尔积。维修/服务和‘一批’类笼统行必须明确标记。"
            "只输出 JSON object，不输出 Markdown。"
        )},
        {"role": "system", "content": json.dumps({
            "prompt_version": PROMPT_VERSION,
            "output_schema": {"rows": [{
                "cluster_id": "原样返回",
                "standard_query": "2-20字目录检索词",
                "standard_type": "中文标准类型名",
                "explicit_facts": {"原文明示属性": "规范值"},
                "search_synonyms": ["最多3个常见同义检索词"],
                "is_service": False,
                "is_bundled_line": False,
                "ambiguity_note": "无歧义则为空",
            }]},
            "clusters": payload,
        }, ensure_ascii=False)},
    ]


def _judgement_messages(
    items: Sequence[tuple[ProcurementCluster, ClusterFact, list[dict[str, Any]]]],
    registry: ProcurementTemplateRegistry,
) -> list[dict[str, str]]:
    templates = [{
        "template_id": item.template_id,
        "name": item.name,
        "description": item.description,
        "record_policy": item.record_policy,
        "max_identity_attributes": item.max_identity_attributes,
    } for item in registry.main_templates.values()]
    constraints = [{
        "constraint_id": item.constraint_id,
        "name": item.name,
        "description": item.description,
        "force_review": item.force_review,
    } for item in registry.constraints.values()]
    payload = []
    for cluster, facts, candidates in items:
        payload.append({
            "cluster_id": cluster.cluster_id,
            "raw_variants": cluster.raw_names,
            "facts": facts.model_dump(mode="json"),
            "allowed_gpc_candidates": [{
                "code": row["code"],
                "working_name": row.get("working_name", ""),
                "official_name": row.get("official_name", ""),
                "definition": row.get("definition_working") or row.get("definition") or "",
                "includes": row.get("includes_working") or row.get("includes") or "",
                "excludes": row.get("excludes_working") or row.get("excludes") or "",
            } for row in candidates],
        })
    return [
        {"role": "system", "content": (
            "你是 GPC 施工物料准入判定员。每个 cluster 只能从 allowed_gpc_candidates 选择一个真实 Brick 编码，"
            "只能从 provided_templates 选择一个主模板，只能从 provided_constraints 选择约束。"
            "候选不适合时 selected_gpc_code 留空并说明，绝对不得编造编码。"
            "属性角色只能引用 facts.explicit_facts 已有键：影响互换和独立库存的进 sku_identity；"
            "仅本次项目/采购行变化的进 transaction；品牌、包装和报价条件进 offer。"
            "不得生成未实际发生的 SKU 组合。只输出 JSON object，不输出 Markdown。"
        )},
        {"role": "system", "content": json.dumps({
            "prompt_version": PROMPT_VERSION,
            "provided_templates": templates,
            "provided_constraints": constraints,
            "allowed_stock_uoms": sorted(_ALLOWED_STOCK_UOMS),
            "output_schema": {"rows": [{
                "cluster_id": "原样返回",
                "selected_gpc_code": "只能取 allowed_gpc_candidates.code 或空",
                "standard_type": "标准类型名",
                "main_template_id": "只能取 provided_templates.template_id 或空",
                "constraint_ids": ["只能取 provided_constraints.constraint_id"],
                "sku_identity_fact_keys": ["只能取 explicit_facts 的键"],
                "transaction_fact_keys": ["只能取 explicit_facts 的键"],
                "offer_fact_keys": ["只能取 explicit_facts 的键"],
                "stock_uom": "只能取 allowed_stock_uoms",
                "confidence": "high | medium | low",
                "reason": "简短判定依据",
                "questions": ["仅真正阻塞的问题"],
            }]},
            "clusters": payload,
        }, ensure_ascii=False)},
    ]


class ProcurementBatchPilot:
    def __init__(
        self,
        *,
        source_path: Path = DEFAULT_LONGHUA_WORKBOOK_PATH,
        runtime_root: Path = DEFAULT_RUNTIME_ROOT,
        gpc_index: GpcReferenceIndex | None = None,
        registry: ProcurementTemplateRegistry | None = None,
        placements: Iterable[Mapping[str, Any]] | None = None,
        deepseek_client: DeepSeekClient | None = None,
        llm_chunk_size: int = DEFAULT_LLM_CHUNK_SIZE,
        review_rules: ProcurementReviewRuleCatalog | None = None,
    ) -> None:
        self.source_path = Path(source_path)
        self.runtime_root = Path(runtime_root)
        self.gpc_index = gpc_index or GpcReferenceIndex.from_runtime(DEFAULT_GPC_RUNTIME_ROOT, DEFAULT_GPC_VERSION)
        self.registry = registry or ProcurementTemplateRegistry.from_files(
            DEFAULT_TEMPLATE_CATALOG_PATH,
            DEFAULT_TYPE_PROFILES_PATH,
        )
        self.placements = list(placements) if placements is not None else _load_jsonl(DEFAULT_PLACEMENTS_PATH)
        self.deepseek_client = deepseek_client or _default_deepseek_client
        self.llm_chunk_size = max(1, min(MAX_PILOT_ROWS, int(llm_chunk_size)))
        self.review_rules = review_rules or ProcurementReviewRuleCatalog()
        self.cache = _ResultCache(self.runtime_root / "cache")
        self.ledger = _TokenLedger()
        self.call_records: list[dict[str, Any]] = []
        self.model_errors: list[dict[str, Any]] = []

    def _progress(self, callback: ProgressCallback | None, stage: str, percent: int, message: str, **metrics: Any) -> None:
        if callback:
            callback(stage, percent, message, metrics)

    def _call(self, phase: str, messages: list[dict[str, str]], item_count: int, max_tokens: int) -> LlmJsonResult:
        request_hash = _json_hash(messages)
        result = self.deepseek_client(messages, max_tokens)
        self.ledger.record(phase, result, item_count=item_count, request_hash=request_hash)
        self.call_records.append({
            "phase": phase,
            "prompt_version": PROMPT_VERSION,
            "request_hash": request_hash,
            "item_count": item_count,
            "messages": messages,
            "model": result.model,
            "usage": result.usage,
            "request_id": result.request_id,
        })
        return result

    def _facts(self, clusters: Sequence[ProcurementCluster], use_deepseek: bool) -> tuple[dict[str, ClusterFact], int]:
        output: dict[str, ClusterFact] = {}
        pending: list[tuple[ProcurementCluster, str]] = []
        cache_hits = 0
        for cluster in clusters:
            key = _json_hash({"phase": "facts", "version": PROMPT_VERSION, "cluster": cluster.model_dump(mode="json")})
            cached = self.cache.read("facts", key) if use_deepseek else None
            if cached:
                output[cluster.cluster_id] = _normalise_fact_row(cached, cluster) or _local_fact(cluster)
                cache_hits += 1
            else:
                pending.append((cluster, key))
        if not use_deepseek:
            return {cluster.cluster_id: _local_fact(cluster) for cluster in clusters}, 0
        def process(chunk: list[tuple[ProcurementCluster, str]]) -> None:
            if not chunk:
                return
            try:
                messages = _fact_messages([item[0] for item in chunk])
                result = self._call("facts", messages, len(chunk), max(2500, 220 * len(chunk)))
                raw_rows = result.data.get("rows") if isinstance(result.data, Mapping) else None
                indexed = {
                    str(row.get("cluster_id") or ""): row
                    for row in (raw_rows if isinstance(raw_rows, list) else [])
                    if isinstance(row, Mapping)
                }
                accepted: set[str] = set()
                for cluster, key in chunk:
                    try:
                        value = _normalise_fact_row(indexed.get(cluster.cluster_id), cluster)
                    except Exception:
                        value = None
                    if value is None:
                        continue
                    self.cache.write("facts", key, value.model_dump(mode="json"))
                    output[cluster.cluster_id] = value
                    accepted.add(cluster.cluster_id)
                missing = [item for item in chunk if item[0].cluster_id not in accepted]
                if missing:
                    if len(missing) == len(chunk):
                        raise ValueError("DeepSeek 事实阶段未返回任何可识别的 cluster")
                    process(missing)
            except Exception as exc:
                if len(chunk) > 1:
                    midpoint = len(chunk) // 2
                    process(chunk[:midpoint])
                    process(chunk[midpoint:])
                    return
                cluster, _key = chunk[0]
                value = _local_fact(cluster)
                value.ambiguity_note = f"DeepSeek 事实抽取失败，已降级到本地事实：{exc}"
                output[cluster.cluster_id] = value
                self.model_errors.append({"phase": "facts", "cluster_id": cluster.cluster_id, "error": str(exc)})

        for offset in range(0, len(pending), self.llm_chunk_size):
            process(pending[offset:offset + self.llm_chunk_size])
        return output, cache_hits

    def _candidates(self, cluster: ProcurementCluster, fact: ClusterFact) -> list[dict[str, Any]]:
        queries = [fact.standard_query, fact.standard_type, cluster.cluster_key, cluster.representative_name, *fact.search_synonyms]
        combined = " ".join(queries).casefold()
        for marker, values in _GPC_RETRIEVAL_ALIASES:
            if marker.casefold() in combined:
                queries.extend(values)
        matched_rules = self.review_rules.match(combined)
        preferred_codes = list(dict.fromkeys(
            str(rule["gpc_brick_code"])
            for rule in matched_rules
            if rule.get("gpc_brick_code")
        ))
        forbidden = {
            str(code)
            for rule in matched_rules
            for code in rule.get("forbidden_gpc_codes") or []
        }
        preferred = [
            row for code in preferred_codes
            if (row := self.gpc_index.candidate_brick(code)) is not None
        ]
        ordinary = self.gpc_index.candidate_bricks(queries, limit=8)
        output: list[dict[str, Any]] = []
        seen: set[str] = set()
        for row in [*preferred, *ordinary]:
            code = str(row.get("code") or "")
            if not code or code in forbidden or code in seen:
                continue
            output.append(row)
            seen.add(code)
        return output[:8]

    def _validate_judgement(
        self,
        judgement: ClusterJudgement,
        fact: ClusterFact,
        candidates: Sequence[Mapping[str, Any]],
    ) -> ClusterJudgement:
        allowed_codes = {str(item.get("code") or "") for item in candidates}
        if judgement.selected_gpc_code and judgement.selected_gpc_code not in allowed_codes:
            raise ValueError(f"DeepSeek 返回了候选集合外的 GPC 编码：{judgement.selected_gpc_code}")
        if judgement.main_template_id and judgement.main_template_id not in self.registry.main_templates:
            raise ValueError(f"DeepSeek 返回未知主模板：{judgement.main_template_id}")
        unknown_constraints = set(judgement.constraint_ids) - set(self.registry.constraints)
        if unknown_constraints:
            raise ValueError(f"DeepSeek 返回未知叠加约束：{sorted(unknown_constraints)[0]}")
        fact_keys = set(fact.explicit_facts)
        roles = [
            *judgement.sku_identity_fact_keys,
            *judgement.transaction_fact_keys,
            *judgement.offer_fact_keys,
        ]
        if len(roles) != len(set(roles)):
            raise ValueError(f"DeepSeek 重复分配属性角色：{judgement.cluster_id}")
        unknown_keys = set(roles) - fact_keys
        if unknown_keys:
            raise ValueError(f"DeepSeek 引用了不存在的事实键：{sorted(unknown_keys)[0]}")
        if judgement.stock_uom not in _ALLOWED_STOCK_UOMS:
            judgement.stock_uom = _TEMPLATE_DEFAULT_UOM.get(judgement.main_template_id, "件")
        return judgement

    def _judgements(
        self,
        clusters: Sequence[ProcurementCluster],
        facts: Mapping[str, ClusterFact],
        candidates: Mapping[str, list[dict[str, Any]]],
        use_deepseek: bool,
    ) -> tuple[dict[str, ClusterJudgement], int]:
        output: dict[str, ClusterJudgement] = {}
        pending: list[tuple[ProcurementCluster, ClusterFact, list[dict[str, Any]], str]] = []
        cache_hits = 0
        for cluster in clusters:
            fact = facts[cluster.cluster_id]
            rows = candidates[cluster.cluster_id]
            if fact.is_service or fact.is_bundled_line or cluster.golden_material_id or not rows:
                continue
            key = _json_hash({
                "phase": "judgement", "version": PROMPT_VERSION,
                "cluster": cluster.model_dump(mode="json"),
                "fact": fact.model_dump(mode="json"),
                "candidate_codes": [row["code"] for row in rows],
                "template_version": self.registry.catalog.catalog_version,
                "review_rules_version": self.review_rules.rules_version,
            })
            cached = self.cache.read("judgements", key) if use_deepseek else None
            if cached:
                value = ClusterJudgement.model_validate(cached)
                output[cluster.cluster_id] = self._validate_judgement(value, fact, rows)
                cache_hits += 1
            elif use_deepseek:
                pending.append((cluster, fact, rows, key))
            else:
                candidate = rows[0]
                output[cluster.cluster_id] = ClusterJudgement(
                    cluster_id=cluster.cluster_id,
                    selected_gpc_code=str(candidate["code"]),
                    standard_type=fact.standard_type,
                    main_template_id="general_finished_good",
                    stock_uom="件",
                    confidence="low",
                    reason="本地候选预览，尚未经过 DeepSeek 受限判定",
                    questions=["需要运行受限 DeepSeek 判定"],
                )
        def process(chunk: list[tuple[ProcurementCluster, ClusterFact, list[dict[str, Any]], str]]) -> None:
            if not chunk:
                return
            try:
                messages = _judgement_messages([(item[0], item[1], item[2]) for item in chunk], self.registry)
                result = self._call("judgement", messages, len(chunk), max(3000, 260 * len(chunk)))
                raw_rows = result.data.get("rows") if isinstance(result.data, Mapping) else None
                indexed = {
                    str(row.get("cluster_id") or ""): row
                    for row in (raw_rows if isinstance(raw_rows, list) else [])
                    if isinstance(row, Mapping)
                }
                accepted: set[str] = set()
                row_errors: dict[str, str] = {}
                for cluster, fact, rows, key in chunk:
                    try:
                        value = _normalise_judgement_row(indexed.get(cluster.cluster_id), cluster.cluster_id)
                        if value is not None:
                            value = self._validate_judgement(value, fact, rows)
                    except Exception as exc:
                        row_errors[cluster.cluster_id] = str(exc)
                        value = None
                    if value is None:
                        continue
                    self.cache.write("judgements", key, value.model_dump(mode="json"))
                    output[cluster.cluster_id] = value
                    accepted.add(cluster.cluster_id)
                missing = [item for item in chunk if item[0].cluster_id not in accepted]
                if missing:
                    if len(missing) == len(chunk):
                        if len(chunk) == 1 and row_errors.get(chunk[0][0].cluster_id):
                            raise ValueError(row_errors[chunk[0][0].cluster_id])
                        raise ValueError("DeepSeek 判定阶段未返回任何可识别的 cluster")
                    process(missing)
            except Exception as exc:
                if len(chunk) > 1:
                    midpoint = len(chunk) // 2
                    process(chunk[:midpoint])
                    process(chunk[midpoint:])
                    return
                cluster = chunk[0][0]
                self.model_errors.append({"phase": "judgement", "cluster_id": cluster.cluster_id, "error": str(exc)})

        for offset in range(0, len(pending), self.llm_chunk_size):
            process(pending[offset:offset + self.llm_chunk_size])
        return output, cache_hits

    def _golden_material(self, material_id: str) -> dict[str, Any] | None:
        return next((deepcopy(dict(row)) for row in self.placements if row.get("material_id") == material_id), None)

    def _matching_profile(self, standard_type: str, brick_code: str) -> ProcurementTypeProfile | None:
        key = (_normalise_text(standard_type).casefold(), brick_code)
        return self.registry.profile_by_type_and_brick.get(key)

    def _decision(
        self,
        cluster: ProcurementCluster,
        fact: ClusterFact,
        candidates: Sequence[Mapping[str, Any]],
        judgement: ClusterJudgement | None,
    ) -> dict[str, Any]:
        if cluster.golden_material_id:
            material = self._golden_material(cluster.golden_material_id)
            if material:
                return {
                    "cluster_id": cluster.cluster_id,
                    "queue": "existing_candidate",
                    "queue_label": "已整理候选",
                    "source_rows": cluster.source_rows,
                    "raw_names": cluster.raw_names,
                    "standard_type": material.get("standard_type", ""),
                    "standard_name": material.get("material_name", ""),
                    "gpc_brick_code": material.get("gpc_brick_code", ""),
                    "gpc_brick_name": next((row.get("working_name", "") for row in candidates if row.get("code") == material.get("gpc_brick_code")), ""),
                    "main_template_id": self.registry.profile(str(material.get("procurement_profile_id"))).main_template_id,
                    "constraint_ids": self.registry.profile(str(material.get("procurement_profile_id"))).constraint_ids,
                    "confidence": "golden",
                    "reason": "命中已人工确认的龙华黄金样本",
                    "questions": [],
                    "candidate_codes": [row.get("code", "") for row in candidates],
                    "material_candidate": material,
                }
        if fact.is_service:
            return self._review_decision(cluster, fact, candidates, "excluded_non_material", "非物料服务行，不进入库存物料库")
        if fact.is_bundled_line:
            return self._review_decision(cluster, fact, candidates, "needs_review", "‘一批/杂项’无法形成可复用的单一物料")
        if not judgement or not judgement.selected_gpc_code or not judgement.main_template_id:
            return self._review_decision(cluster, fact, candidates, "needs_review", "没有足够可靠的 GPC Brick 或采购模板判定")
        selected = next((row for row in candidates if row.get("code") == judgement.selected_gpc_code), {})
        selected_rank = next(
            (index for index, row in enumerate(candidates, start=1) if row.get("code") == judgement.selected_gpc_code),
            0,
        )
        force_review = any(self.registry.constraints[item].force_review for item in judgement.constraint_ids)
        profile = self._matching_profile(judgement.standard_type, judgement.selected_gpc_code)
        queue = "ready_new_sku" if profile else "ready_new_type"
        questions = list(judgement.questions)
        if judgement.confidence == "low" or force_review or (selected_rank > 3 and judgement.confidence != "high"):
            queue = "needs_review"
        facts = dict(fact.explicit_facts)
        identity_keys = [key for key in judgement.sku_identity_fact_keys if key in facts]
        transaction_keys = [key for key in judgement.transaction_fact_keys if key in facts]
        offer_keys = [key for key in judgement.offer_fact_keys if key in facts]
        if not identity_keys and self.registry.main_templates[judgement.main_template_id].record_policy == "actual_sku_only":
            facts.setdefault("类型/规格", judgement.standard_type)
            identity_keys = ["类型/规格"]
        procurement_attributes = {key: facts[key] for key in [*identity_keys, *transaction_keys][:4]}
        if not procurement_attributes:
            procurement_attributes = {"类型/规格": judgement.standard_type}
        price_drivers = {key: facts[key] for key in offer_keys[:2]}
        price_drivers.setdefault("质量要求", "符合国家/行业通用标准，质量可靠")
        supplier_offer_role_keys = list(dict.fromkeys([*offer_keys, "质量要求"]))
        type_key = _normalise_text(judgement.standard_type).casefold()
        identity_values = list(dict.fromkeys(
            facts[key]
            for key in identity_keys
            if facts.get(key) and _normalise_text(facts[key]).casefold() != type_key
        ))
        standard_name = "｜".join([judgement.standard_type, *identity_values]) if identity_values else judgement.standard_type
        material = {
            "material_id": f"LH-PILOT-{cluster.source_rows[0]:04d}",
            "project": "龙华项目",
            "source_reference": SOURCE_SHEET,
            "source_rows": cluster.source_rows,
            "standard_type": judgement.standard_type,
            "material_name": standard_name,
            "gpc_brick_code": judgement.selected_gpc_code,
            "confidence": judgement.confidence,
            "review_status": "批量候选待复核",
            "completeness_status": "候选完整",
            "specification_basis": "采购原文事实；缺失的通用质量要求按用户授权的施工采购默认策略补齐",
            "stock_uom": judgement.stock_uom,
            "procurement_attributes": procurement_attributes,
            "price_drivers": price_drivers,
            "gpc_notes": [
                f"按 GPC Brick {judgement.selected_gpc_code} {selected.get('working_name') or selected.get('official_name') or ''} 归类",
                "未生成未实际发生的属性组合；后续不同真实规格按需新增",
            ],
            "questions": questions,
        }
        return {
            "cluster_id": cluster.cluster_id,
            "queue": queue,
            "queue_label": {
                "ready_new_sku": "现有类型新增 SKU 候选",
                "ready_new_type": "新增标准类型候选",
                "needs_review": "需人工复核",
            }[queue],
            "source_rows": cluster.source_rows,
            "raw_names": cluster.raw_names,
            "standard_type": judgement.standard_type,
            "standard_name": standard_name,
            "gpc_brick_code": judgement.selected_gpc_code,
            "gpc_brick_name": selected.get("working_name") or selected.get("official_name") or "",
            "main_template_id": judgement.main_template_id,
            "constraint_ids": judgement.constraint_ids,
            "confidence": judgement.confidence,
            "reason": judgement.reason,
            "questions": questions,
            "attribute_roles": {
                "sku_identity": identity_keys,
                "transaction": transaction_keys,
                "supplier_offer": supplier_offer_role_keys,
            },
            "candidate_codes": [row.get("code", "") for row in candidates],
            "selected_candidate_rank": selected_rank,
            "material_candidate": material,
        }

    @staticmethod
    def _review_decision(
        cluster: ProcurementCluster,
        fact: ClusterFact,
        candidates: Sequence[Mapping[str, Any]],
        queue: str,
        reason: str,
    ) -> dict[str, Any]:
        return {
            "cluster_id": cluster.cluster_id,
            "queue": queue,
            "queue_label": "非物料服务" if queue == "excluded_non_material" else "需人工复核",
            "source_rows": cluster.source_rows,
            "raw_names": cluster.raw_names,
            "standard_type": fact.standard_type,
            "standard_name": "",
            "gpc_brick_code": "",
            "gpc_brick_name": "",
            "main_template_id": "",
            "constraint_ids": [],
            "confidence": "low",
            "reason": reason,
            "questions": [fact.ambiguity_note] if fact.ambiguity_note else [],
            "candidate_codes": [row.get("code", "") for row in candidates],
            "material_candidate": None,
        }

    def _generated_profiles(self, decisions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        seen: set[tuple[str, str]] = set()
        for decision in decisions:
            if decision.get("queue") not in {"ready_new_type", "ready_new_sku"}:
                continue
            code = str(decision.get("gpc_brick_code") or "")
            standard_type = str(decision.get("standard_type") or "")
            template_id = str(decision.get("main_template_id") or "")
            if not code or not standard_type or not template_id:
                continue
            key = (_normalise_text(standard_type).casefold(), code)
            if key in seen or self.registry.profile_by_type_and_brick.get(key):
                continue
            roles = decision.get("attribute_roles") or {}
            profile_id = f"LH-AUTO-{_json_hash(key)[:10].upper()}"
            rows.append({
                "profile_id": profile_id,
                "standard_type": standard_type,
                "gpc_brick_code": code,
                "main_template_id": template_id,
                "constraint_ids": list(decision.get("constraint_ids") or []),
                "sku_identity_fields": [f"procurement_attributes.{key}" for key in roles.get("sku_identity", [])],
                "transaction_fields": [f"procurement_attributes.{key}" for key in roles.get("transaction", [])],
                "offer_fields": [f"price_drivers.{key}" for key in roles.get("supplier_offer", [])],
                "status": "generated",
                "source_material_ids": [decision["material_candidate"]["material_id"]] if decision.get("material_candidate") else [],
                "review_status": "待人工确认后才能加入正式类型档案",
            })
            seen.add(key)
        return rows

    def run(
        self,
        *,
        limit: int = MAX_PILOT_ROWS,
        use_deepseek: bool = True,
        job_id: str | None = None,
        progress: ProgressCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        resolved_job_id = job_id or f"pilot-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
        job_dir = self.runtime_root / "jobs" / resolved_job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        self._progress(progress, "read", 5, "读取实际采购清单")
        snapshot = load_purchase_workbook(self.source_path, limit=limit)
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("批处理任务已取消")
        self._progress(progress, "cluster", 15, "规范原文并聚合重复/近似物料", source_rows=len(snapshot.rows))
        clusters = build_clusters(snapshot.rows, golden_placements=self.placements)
        facts, fact_cache_hits = self._facts(clusters, use_deepseek)
        self._progress(progress, "facts", 40, "事实抽取完成", clusters=len(clusters), cache_hits=fact_cache_hits)
        if cancel_event and cancel_event.is_set():
            raise InterruptedError("批处理任务已取消")
        candidate_map = {cluster.cluster_id: self._candidates(cluster, facts[cluster.cluster_id]) for cluster in clusters}
        self._progress(progress, "retrieve", 55, "已检索真实 GPC Brick 候选")
        judgements, judgement_cache_hits = self._judgements(clusters, facts, candidate_map, use_deepseek)
        self._progress(progress, "judge", 78, "受限 GPC 与模板判定完成", cache_hits=judgement_cache_hits)
        decisions = [
            self._decision(cluster, facts[cluster.cluster_id], candidate_map[cluster.cluster_id], judgements.get(cluster.cluster_id))
            for cluster in clusters
        ]
        profiles = self._generated_profiles(decisions)
        queue_counts = dict(Counter(str(row.get("queue") or "unknown") for row in decisions))
        token_summary = self.ledger.summary()
        exact_unique = len({row.exact_key for row in snapshot.rows})
        audit = {
            "schema_version": 1,
            "job_id": resolved_job_id,
            "status": "completed",
            "writes_erpnext": False,
            "created_at": _now_iso(),
            "prompt_version": PROMPT_VERSION,
            "source": snapshot.model_dump(mode="json", exclude={"rows"}),
            "row_count": len(snapshot.rows),
            "exact_unique_count": exact_unique,
            "cluster_count": len(clusters),
            "duplicate_source_row_count": len(snapshot.rows) - exact_unique,
            "cluster_compression_count": exact_unique - len(clusters),
            "golden_cluster_count": sum(bool(cluster.golden_material_id) for cluster in clusters),
            "queue_counts": queue_counts,
            "generated_type_profile_count": len(profiles),
            "fact_cache_hits": fact_cache_hits,
            "judgement_cache_hits": judgement_cache_hits,
            "model_error_count": len(self.model_errors),
            "model_errors": self.model_errors,
            "deepseek": token_summary,
            "llm_chunk_size": self.llm_chunk_size,
            "history_sheet_used": False,
        }
        self._write_jsonl(job_dir / "source-rows.jsonl", [row.model_dump(mode="json") for row in snapshot.rows])
        self._write_jsonl(job_dir / "clusters.jsonl", [row.model_dump(mode="json") for row in clusters])
        self._write_jsonl(job_dir / "facts.jsonl", [facts[row.cluster_id].model_dump(mode="json") for row in clusters])
        self._write_jsonl(job_dir / "decisions.jsonl", decisions)
        self._write_jsonl(job_dir / "generated-type-profiles.jsonl", profiles)
        self._write_jsonl(job_dir / "deepseek-calls.jsonl", self.call_records)
        (job_dir / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        (job_dir / "job.json").write_text(json.dumps({
            "job_id": resolved_job_id,
            "status": "completed",
            "stage": "complete",
            "percent": 100,
            "message": "批处理候选已生成",
            "writes_erpnext": False,
            "audit": audit,
            "updated_at": _now_iso(),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        (job_dir / "prompt-manifest.json").write_text(json.dumps({
            "prompt_version": PROMPT_VERSION,
            "facts_system_prompt": _fact_messages([])[0]["content"],
            "judgement_system_prompt": _judgement_messages([], self.registry)[0]["content"],
            "guardrails": [
                "GPC 编码只能从本地真实候选中选择",
                "模板与约束只能从固定 10+5 目录中选择",
                "属性角色只能引用原文事实",
                "禁止生成未实际发生的 SKU 组合",
                "任务不写入 ERPNext",
            ],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        latest = self.runtime_root / "latest.json"
        latest.parent.mkdir(parents=True, exist_ok=True)
        latest.write_text(json.dumps({"job_id": resolved_job_id, "job_dir": str(job_dir), "audit": audit}, ensure_ascii=False, indent=2), encoding="utf-8")
        self._progress(progress, "complete", 100, "前 100 行批处理候选已生成", **queue_counts)
        return {"audit": audit, "decisions": decisions, "generated_type_profiles": profiles, "job_dir": str(job_dir)}

    @staticmethod
    def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
        path.write_text("".join(json.dumps(dict(row), ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class ProcurementBatchPilotJobManager:
    def __init__(
        self,
        runtime_root: Path = DEFAULT_RUNTIME_ROOT,
        *,
        pipeline_factory: Callable[[], ProcurementBatchPilot] | None = None,
    ) -> None:
        self.runtime_root = Path(runtime_root)
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.pipeline_factory = pipeline_factory or (lambda: ProcurementBatchPilot(runtime_root=self.runtime_root))
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancellations: dict[str, threading.Event] = {}

    def start(self, *, limit: int = MAX_PILOT_ROWS, use_deepseek: bool = True) -> dict[str, Any]:
        if limit < 1 or limit > MAX_PILOT_ROWS:
            raise ValueError(f"试运行行数必须在 1 到 {MAX_PILOT_ROWS} 之间")
        job_id = f"pilot-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
        job = {
            "job_id": job_id,
            "status": "queued",
            "stage": "queued",
            "percent": 0,
            "message": "任务已排队",
            "limit": limit,
            "use_deepseek": bool(use_deepseek),
            "writes_erpnext": False,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "metrics": {},
        }
        with self._lock:
            self._jobs[job_id] = job
            self._cancellations[job_id] = threading.Event()
        self._persist_job(job)
        threading.Thread(target=self._run, args=(job_id,), daemon=True, name=f"procurement-{job_id}").start()
        return deepcopy(job)

    def _run(self, job_id: str) -> None:
        try:
            with self._lock:
                job = self._jobs[job_id]
                cancel_event = self._cancellations[job_id]
                job.update({"status": "running", "updated_at": _now_iso()})
                limit = int(job["limit"])
                use_deepseek = bool(job["use_deepseek"])
            pipeline = self.pipeline_factory()

            def progress(stage: str, percent: int, message: str, metrics: Mapping[str, Any]) -> None:
                with self._lock:
                    current = self._jobs[job_id]
                    current.update({
                        "stage": stage,
                        "percent": percent,
                        "message": message,
                        "metrics": {**current.get("metrics", {}), **dict(metrics)},
                        "updated_at": _now_iso(),
                    })
                    self._persist_job(current)

            result = pipeline.run(
                limit=limit,
                use_deepseek=use_deepseek,
                job_id=job_id,
                progress=progress,
                cancel_event=cancel_event,
            )
            with self._lock:
                job = self._jobs[job_id]
                job.update({
                    "status": "completed",
                    "stage": "complete",
                    "percent": 100,
                    "message": "批处理候选已生成",
                    "audit": result["audit"],
                    "updated_at": _now_iso(),
                })
                self._persist_job(job)
        except InterruptedError as exc:
            self._finish_error(job_id, "cancelled", str(exc))
        except Exception as exc:  # pragma: no cover - background boundary
            self._finish_error(job_id, "failed", str(exc))

    def _finish_error(self, job_id: str, status: str, error: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.update({"status": status, "message": error, "error": error, "updated_at": _now_iso()})
            self._persist_job(job)

    def status(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id in self._jobs:
                return deepcopy(self._jobs[job_id])
        path = self.runtime_root / "jobs" / job_id / "job.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        audit_path = self.runtime_root / "jobs" / job_id / "audit.json"
        if audit_path.is_file():
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            return {
                "job_id": job_id, "status": "completed", "stage": "complete", "percent": 100,
                "message": "批处理候选已生成", "writes_erpnext": False, "audit": audit,
                "updated_at": audit.get("created_at", ""),
            }
        raise ValueError(f"批处理任务不存在：{job_id}")

    def result(self, job_id: str) -> dict[str, Any]:
        job = self.status(job_id)
        if job.get("status") != "completed":
            return {"job": job, "decisions": [], "generated_type_profiles": []}
        directory = self.runtime_root / "jobs" / job_id
        return {
            "job": job,
            "audit": json.loads((directory / "audit.json").read_text(encoding="utf-8")),
            "decisions": _load_jsonl(directory / "decisions.jsonl"),
            "generated_type_profiles": _load_jsonl(directory / "generated-type-profiles.jsonl"),
            "prompt_manifest": json.loads((directory / "prompt-manifest.json").read_text(encoding="utf-8")),
        }

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self._jobs:
                raise ValueError(f"批处理任务不存在：{job_id}")
            self._cancellations[job_id].set()
            job = self._jobs[job_id]
            job["message"] = "已请求取消，将在当前阶段结束后停止"
            job["updated_at"] = _now_iso()
            self._persist_job(job)
            return deepcopy(job)

    def latest(self) -> dict[str, Any]:
        latest_path = self.runtime_root / "latest.json"
        if not latest_path.is_file():
            return {"available": False, "message": "尚未运行批处理试验"}
        payload = json.loads(latest_path.read_text(encoding="utf-8"))
        return {"available": True, **payload}

    def _persist_job(self, job: Mapping[str, Any]) -> None:
        directory = self.runtime_root / "jobs" / str(job["job_id"])
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "job.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(dict(job), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


__all__ = [
    "ClusterFact",
    "ClusterJudgement",
    "DEFAULT_LONGHUA_WORKBOOK_PATH",
    "MAX_PILOT_ROWS",
    "PROMPT_VERSION",
    "ProcurementBatchPilot",
    "ProcurementBatchPilotJobManager",
    "ProcurementCluster",
    "ProcurementSourceRow",
    "ProcurementWorkbookSnapshot",
    "build_clusters",
    "load_purchase_workbook",
]
