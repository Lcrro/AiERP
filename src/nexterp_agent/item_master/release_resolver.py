from __future__ import annotations

from dataclasses import dataclass
import csv
from pathlib import Path
import re
from typing import Any


DEFAULT_RELEASE_CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "material_master"
    / "release_v1_0"
    / "material_master_release_v1_0.tsv"
)


@dataclass(frozen=True)
class ReleaseMaterialCandidate:
    item_code: str
    item_name: str
    sku_name: str
    score: int
    match_reasons: tuple[str, ...]
    data: dict[str, str]

    @property
    def confidence(self) -> str:
        if self.score >= 135:
            return "high"
        if self.score >= 80:
            return "medium"
        return "low"

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_code": self.item_code,
            "item_name": self.item_name,
            "sku_name": self.sku_name,
            "item_group": self.data.get("item_group"),
            "top_group": self.data.get("top_group"),
            "material_family": self.data.get("material_family"),
            "stock_uom": self.data.get("stock_uom"),
            "required_specs": self.data.get("required_specs"),
            "score": self.score,
            "confidence": self.confidence,
            "match_reasons": list(self.match_reasons),
            "match_reason": "；".join(self.match_reasons),
            "data": self.data,
        }


class ReleaseMaterialResolver:
    """Resolve human material text against the governed material master release.

    This resolver is intentionally offline and deterministic. The language
    model can extract raw material text and specs, but concrete item_code/uom
    values should come from this resolver before the ToolCall is composed.
    """

    def __init__(self, catalog_path: str | Path = DEFAULT_RELEASE_CATALOG_PATH) -> None:
        self.catalog_path = Path(catalog_path)
        self.rows = load_release_catalog(self.catalog_path)

    def resolve(
        self,
        query: str,
        *,
        specs: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        query = str(query or "").strip()
        specs = normalize_specs(specs or {})
        if not query and not specs:
            return {
                "status": "needs_clarification",
                "query": query,
                "specs": specs,
                "top_score": 0,
                "resolved": None,
                "candidates": [],
                "questions": ["请说明要查找的物料名称、规格或编码。"],
                "decision_reason": "查询文本和结构化规格都为空。",
            }

        ranked = sorted(
            (score_release_row(row, query, specs) for row in self.rows),
            key=lambda candidate: candidate.score,
            reverse=True,
        )
        ranked = [candidate for candidate in ranked if candidate.score > 0][:limit]
        decision = decision_for_release_candidates(ranked, query=query, specs=specs)
        resolved = ranked[0].to_dict() if decision["status"] == "ready" and ranked else None
        return {
            "status": decision["status"],
            "query": query,
            "specs": specs,
            "top_score": ranked[0].score if ranked else 0,
            "resolved": resolved,
            "candidates": [candidate.to_dict() for candidate in ranked],
            "questions": questions_for_release_result(decision["status"], ranked, query=query),
            "decision_reason": decision["why_status"],
            "debug": decision,
        }


def load_release_catalog(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def score_release_row(row: dict[str, str], query: str, specs: dict[str, Any]) -> ReleaseMaterialCandidate:
    query_norm = normalize_text(query)
    query_spec = normalize_spec_text(query)
    spec_values = [str(value) for value in specs.values() if value not in (None, "")]
    spec_norms = {normalize_spec_text(value) for value in spec_values if normalize_spec_text(value)}

    item_code = row.get("item_code", "")
    item_name = row.get("item_name", "")
    sku_name = row.get("sku_name", "")
    required_specs = row.get("required_specs", "")
    aliases = split_terms(row.get("aliases", ""))
    search_keywords = row.get("search_keywords", "")

    code_norm = normalize_text(item_code)
    item_name_norm = normalize_text(item_name)
    sku_name_norm = normalize_text(sku_name)
    aliases_norm = {normalize_text(alias) for alias in aliases}
    searchable = normalize_text(
        " ".join(
            [
                item_code,
                item_name,
                sku_name,
                required_specs,
                row.get("item_group", ""),
                row.get("top_group", ""),
                row.get("sub_group", ""),
                row.get("material_family", ""),
                row.get("stock_uom", ""),
                row.get("aliases", ""),
                search_keywords,
                row.get("brand", ""),
            ]
        )
    )
    searchable_spec = normalize_spec_text(searchable)

    score = 0
    reasons: list[str] = []

    if query_norm and query_norm == code_norm:
        score += 220
        reasons.append("物料编码精确匹配")

    if query_norm:
        if query_norm == sku_name_norm:
            score += 145
            reasons.append("SKU名称精确匹配")
        elif query_norm in sku_name_norm:
            score += 80
            reasons.append("SKU名称包含查询词")
        elif sku_name_norm and sku_name_norm in query_norm:
            score += 70
            reasons.append("查询词包含完整SKU名称")

        if query_norm == item_name_norm:
            score += 85
            reasons.append("物料名称精确匹配")
        elif query_norm in item_name_norm:
            score += 45
            reasons.append("物料名称包含查询词")
        elif item_name_norm and item_name_norm in query_norm:
            score += 35
            reasons.append("查询词包含物料名称")

        if query_norm in aliases_norm:
            score += 95
            reasons.append("别名精确匹配")
        elif any(query_norm in alias for alias in aliases_norm):
            score += 55
            reasons.append("别名包含查询词")
        elif any(alias in query_norm for alias in aliases_norm):
            score += 25
            reasons.append("查询词包含别名")

        if query_spec and query_spec in normalize_spec_text(sku_name):
            score += 35
            reasons.append("SKU名称规格命中")
        if query_spec and query_spec in normalize_spec_text(required_specs):
            score += 45
            reasons.append("必填规格命中")

    for spec_norm in spec_norms:
        if spec_norm in normalize_spec_text(sku_name):
            score += 35
            reasons.append("结构化规格命中SKU名称")
        if spec_norm in normalize_spec_text(required_specs):
            score += 45
            reasons.append("结构化规格命中必填规格")

    token_score, token_reasons = token_match_score(query, searchable, searchable_spec)
    score += token_score
    reasons.extend(token_reasons)

    if score > 0:
        if row.get("status") == "active":
            score += 3
        if row.get("agent_use_policy") == "auto_select_allowed":
            score += 2

    return ReleaseMaterialCandidate(
        item_code=item_code,
        item_name=item_name,
        sku_name=sku_name,
        score=score,
        match_reasons=tuple(dict.fromkeys(reasons)),
        data=row,
    )


def decision_for_release_candidates(
    candidates: list[ReleaseMaterialCandidate],
    *,
    query: str,
    specs: dict[str, Any],
) -> dict[str, Any]:
    top_score = candidates[0].score if candidates else 0
    second_score = candidates[1].score if len(candidates) > 1 else 0
    score_gap = top_score - second_score if candidates else 0
    if not candidates:
        return {
            "status": "not_found",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "没有召回任何发布版物料候选。",
        }

    if is_exact_item_code(query, candidates[0]):
        return {
            "status": "ready",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "物料编码精确命中，可以直接使用。",
        }

    if is_generic_material_query(query) and not specs:
        return {
            "status": "needs_clarification",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "查询词是物料族或宽泛名称，需要补充关键规格。",
        }

    if top_score >= 165 and score_gap >= 25:
        return {
            "status": "ready",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "最高分候选达到高置信阈值且明显领先。",
        }

    if top_score < 55:
        return {
            "status": "not_found",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "最高分低于发布版物料匹配阈值。",
        }

    return {
        "status": "needs_confirmation",
        "top_score": top_score,
        "second_score": second_score,
        "score_gap": score_gap,
        "why_status": "已找到候选，但需要用户确认后才能写入单据。",
    }


def questions_for_release_result(
    status: str,
    candidates: list[ReleaseMaterialCandidate],
    *,
    query: str,
) -> list[str]:
    if status == "ready":
        return []
    if status == "not_found":
        return ["没有找到可信物料。请补充名称、规格、材质、品牌，或进入新增物料流程。"]
    if not candidates:
        return ["请补充物料名称或关键规格。"]
    if is_generic_material_query(query):
        return [f"“{query}”还不够具体，请补充规格、材质、型号、口径、长度或用途。"]
    return ["找到多个候选，请选择一个，或补充关键规格后再检索。"]


def normalize_specs(specs: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in specs.items() if value not in (None, "")}


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    return re.sub(r"\s+", "", text)


def normalize_spec_text(value: Any) -> str:
    text = normalize_text(value)
    text = (
        text.replace("×", "*")
        .replace("x", "*")
        .replace("＊", "*")
        .replace("毫米", "mm")
        .replace("公分", "cm")
        .replace("厘米", "cm")
        .replace("厘", "mm")
    )
    text = re.sub(r"(?<=\d)\.0(?=\D|$)", "", text)
    text = re.sub(r"\b[mφΦ](?=\d)", "", text)
    text = re.sub(r"(?<=\d)mm\b", "", text)
    return text


def split_terms(value: str) -> list[str]:
    terms = []
    for part in re.split(r"[,，|/；;]+", value or ""):
        term = part.strip()
        if term and len(normalize_text(term)) >= 2:
            terms.append(term)
    return terms


def token_match_score(query: str, searchable: str, searchable_spec: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    tokens = extract_query_tokens(query)
    if not tokens:
        return score, reasons
    for token in tokens:
        token_norm = normalize_text(token)
        token_spec = normalize_spec_text(token)
        if token_spec and is_spec_like(token) and token_spec in searchable_spec:
            score += 25
            reasons.append(f"规格片段命中 {token}")
        elif token_norm and token_norm in searchable:
            score += 10
            reasons.append(f"关键词命中 {token}")
    return min(score, 90), reasons


def extract_query_tokens(query: str) -> list[str]:
    raw = str(query or "")
    tokens: list[str] = []
    patterns = [
        r"\d+(?:\.\d+)?\s*级",
        r"[mM]?\d+(?:\.\d+)?\s*[*×x]\s*\d+(?:\.\d+)?",
        r"\d+(?:\.\d+)?\s*(?:mm|cm|米|寸|分|A|V|W)",
        r"[A-Za-z]+[-\w]*",
        r"[\u4e00-\u9fff]{2,}",
    ]
    for pattern in patterns:
        tokens.extend(match.group(0) for match in re.finditer(pattern, raw))
    return list(dict.fromkeys(token.strip() for token in tokens if token.strip()))


def is_spec_like(token: str) -> bool:
    return bool(re.search(r"\d", token))


def is_exact_item_code(query: str, candidate: ReleaseMaterialCandidate) -> bool:
    return bool(query) and normalize_text(query) == normalize_text(candidate.item_code)


def is_generic_material_query(query: str) -> bool:
    return normalize_text(query) in {
        "接头",
        "直接",
        "管",
        "线",
        "阀",
        "阀门",
        "螺丝",
        "螺栓",
        "螺丝螺栓",
        "手套",
        "钻头",
        "扳手",
        "开关",
        "插座",
        "电线",
        "电缆",
        "油漆",
    }
