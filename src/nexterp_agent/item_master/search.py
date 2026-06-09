from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Protocol


class DocumentClientLike(Protocol):
    def get_document(self, doctype: str, name: str): ...

    def search_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
    ): ...


@dataclass(frozen=True)
class SearchCandidate:
    item_code: str
    item_name: str
    score: int
    match_reasons: tuple[str, ...]
    data: dict[str, Any]
    missing_specs: tuple[str, ...] = ()
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        match_reason = "；".join(self.match_reasons)
        return {
            "item_code": self.item_code,
            "item_name": self.item_name,
            "item_group": self.data.get("item_group"),
            "score": self.score,
            "confidence": confidence_for_score(self.score),
            "enabled": self.enabled,
            "match_reasons": list(self.match_reasons),
            "match_reason": match_reason,
            "missing_specs": list(self.missing_specs),
            "data": self.data,
        }


class MaterialSearch:
    def __init__(self, client: DocumentClientLike) -> None:
        self.client = client
        self.warnings: list[str] = []

    def search_items(
        self,
        query: str,
        *,
        specs: dict[str, Any] | None = None,
        item_group: str | None = None,
        enabled_only: bool = True,
        limit: int = 10,
    ) -> dict[str, Any]:
        self.warnings = []
        query = str(query or "").strip()
        specs = normalize_specs(specs or {})
        candidates: dict[str, SearchCandidate] = {}

        for result in [
            self._exact_code(query),
            self._like("item_name", query, enabled_only=enabled_only),
            self._like("alias_names", query, enabled_only=enabled_only),
            self._like("raw_name", query, enabled_only=enabled_only),
            self._like("specification", query, enabled_only=enabled_only),
            self._like("brand", query, enabled_only=enabled_only),
            self._like("model", query, enabled_only=enabled_only),
            self._like("material", query, enabled_only=enabled_only),
            self._like("standard", query, enabled_only=enabled_only),
            *self._spec_recall(specs, enabled_only=enabled_only),
        ]:
            for row, reason in result:
                candidate = score_row(row, query, specs, reason, item_group=item_group)
                current = candidates.get(candidate.item_code)
                if current is None or candidate.score > current.score:
                    candidates[candidate.item_code] = candidate

        ranked = sorted(candidates.values(), key=lambda item: item.score, reverse=True)[:limit]
        decision = decision_for_candidates(ranked, query=query, has_specs=bool(specs))
        return {
            "status": decision["status"],
            "query": query,
            "specs": specs,
            "item_group": item_group,
            "top_score": ranked[0].score if ranked else 0,
            "candidates": [candidate.to_dict() for candidate in ranked],
            "questions": questions_for_result(decision["status"], ranked, query=query, specs=specs),
            "decision_reason": decision["why_status"],
            "warnings": self.warnings,
            "debug": {**decision, "warnings": self.warnings},
        }

    def _exact_code(self, query: str) -> list[tuple[dict[str, Any], str]]:
        if not query:
            return []
        result = self.client.get_document("Item", query)
        if getattr(result, "ok", False) and isinstance(result.data, dict):
            return [(result.data, "物料编码精确匹配")]
        return []

    def _like(self, field: str, query: str, *, enabled_only: bool) -> list[tuple[dict[str, Any], str]]:
        if not query:
            return []
        filters: list[list[Any]] = [[field, "like", f"%{query}%"]]
        if enabled_only:
            filters.append(["disabled", "=", 0])
        result = self.client.search_documents(
            "Item",
            filters=filters,
            fields=ITEM_SEARCH_FIELDS,
            limit=50,
        )
        if not getattr(result, "ok", False) or not isinstance(result.data, list):
            self._warn_failed_field(field, result)
            return []
        return [(row, f"{field} 模糊匹配") for row in result.data]

    def _spec_recall(self, specs: dict[str, Any], *, enabled_only: bool) -> list[list[tuple[dict[str, Any], str]]]:
        recalls: list[list[tuple[dict[str, Any], str]]] = []
        for field in SPEC_RECALL_FIELDS:
            value = specs.get(field)
            if value:
                for variant in search_variants(value):
                    recalls.append(self._like(field, variant, enabled_only=enabled_only))
        return recalls

    def _warn_failed_field(self, field: str, result: Any) -> None:
        error_type = getattr(result, "error_type", None) or "unknown_error"
        error = getattr(result, "error", None) or getattr(result, "user_message", None) or "field query failed"
        self.warnings.append(f"跳过字段 {field}：{error_type}: {error}")


ITEM_SEARCH_FIELDS = [
    "name",
    "item_code",
    "item_name",
    "item_group",
    "stock_uom",
    "specification",
    "material",
    "standard",
    "brand",
    "model",
    "package_spec",
    "raw_name",
    "alias_names",
    "disabled",
]

SPEC_RECALL_FIELDS = {"material", "brand", "model", "standard", "package_spec"}


def score_row(
    row: dict[str, Any],
    query: str,
    specs: dict[str, Any],
    reason: str,
    *,
    item_group: str | None = None,
) -> SearchCandidate:
    item_code = str(row.get("item_code") or row.get("name") or "")
    item_name = str(row.get("item_name") or item_code)
    searchable = searchable_text(row)
    query_lower = normalize_text(query)
    score = 0
    reasons: list[str] = [reason]
    missing_specs: list[str] = []
    enabled = not bool(row.get("disabled"))

    if normalize_text(item_code) == query_lower:
        score += 100
        reasons.append("物料编码精确命中")
    if query_lower and query_lower == normalize_text(item_name):
        score += 70
        reasons.append("标准名称精确命中")
    elif query_lower and query_lower in normalize_text(item_name):
        score += 45
        reasons.append("标准名称包含查询词")

    alias_hit = text_list_contains(row.get("alias_names"), query_lower)
    if alias_hit == "exact":
        score += 65
        reasons.append("别名/土名精确命中")
    elif alias_hit == "contains":
        score += 50
        reasons.append("别名/土名包含查询词")

    for field, label, points in [
        ("raw_name", "原始名称", 35),
        ("specification", "规格描述", 25),
        ("brand", "品牌", 20),
        ("model", "型号", 25),
        ("material", "材质", 20),
        ("standard", "执行标准", 20),
    ]:
        value = normalize_text(row.get(field))
        if query_lower and query_lower in value:
            score += points
            reasons.append(f"{label}命中")

    token_score = token_overlap_score(query_lower, searchable)
    if token_score:
        score += token_score
        reasons.append("关键词重合")

    for key, value in specs.items():
        normalized_value = normalize_text(value)
        normalized_spec_value = normalize_spec_text(value)
        if not normalized_value:
            continue
        field_value = normalize_text(row.get(key))
        field_spec_value = normalize_spec_text(row.get(key))
        searchable_spec = normalize_spec_text(searchable)
        if field_value and (field_value == normalized_value or field_spec_value == normalized_spec_value):
            score += 20
            reasons.append(f"规格字段精确命中 {key}={value}")
        elif normalized_value in searchable or (normalized_spec_value and normalized_spec_value in searchable_spec):
            score += 12
            reasons.append(f"规格命中 {key}={value}")
        else:
            missing_specs.append(key)

    if item_group and normalize_text(item_group) == normalize_text(row.get("item_group")):
        score += 12
        reasons.append(f"物料组匹配 {item_group}")

    if enabled:
        score += 5
    else:
        score -= 15
        reasons.append("物料已禁用")

    return SearchCandidate(
        item_code=item_code,
        item_name=item_name,
        score=score,
        match_reasons=tuple(dict.fromkeys(reasons)),
        data=row,
        missing_specs=tuple(missing_specs),
        enabled=enabled,
    )


def status_for_candidates(candidates: list[SearchCandidate], *, query: str = "", has_specs: bool = False) -> str:
    return decision_for_candidates(candidates, query=query, has_specs=has_specs)["status"]


def decision_for_candidates(candidates: list[SearchCandidate], *, query: str = "", has_specs: bool = False) -> dict[str, Any]:
    top_score = candidates[0].score if candidates else 0
    second_score = candidates[1].score if len(candidates) > 1 else 0
    score_gap = top_score - second_score if candidates else 0
    if not candidates:
        return {
            "status": "not_found",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "没有召回任何候选物料。",
        }
    top = candidates[0]
    if not top.enabled:
        return {
            "status": "needs_confirmation",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "最高分候选已禁用，不能自动选择。",
        }
    if is_generic_query(query) and not has_specs:
        return {
            "status": "needs_clarification",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "查询词过于宽泛且没有结构化规格。",
        }
    if has_specs and top.score >= 35 and (len(candidates) == 1 or score_gap >= 20):
        return {
            "status": "ready" if top.score >= 90 else "needs_confirmation",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "规格召回后最高分候选明显领先。",
        }
    if top.score < 35:
        return {
            "status": "needs_clarification",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "最高分低于可信阈值。",
        }
    if len(candidates) == 1 and top.score >= 90:
        return {
            "status": "ready",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "唯一候选达到高置信阈值。",
        }
    if top.score >= 90 and len(candidates) > 1 and score_gap >= 15:
        return {
            "status": "ready",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "最高分候选达到高置信阈值，且领先第二候选。",
        }
    if len(candidates) > 1 and score_gap < 20:
        return {
            "status": "needs_confirmation",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "存在多个相近候选，分差不足以自动选择。",
        }
    return {
        "status": "needs_confirmation",
        "top_score": top_score,
        "second_score": second_score,
        "score_gap": score_gap,
        "why_status": "已找到候选，但未达到自动选择阈值。",
    }


def questions_for_result(
    status: str,
    candidates: list[SearchCandidate],
    *,
    query: str,
    specs: dict[str, Any],
) -> list[str]:
    if status == "ready":
        return []
    if status == "not_found":
        return ["没有找到可信候选，请补充标准名称、规格型号、材质、品牌或物料编码。"]
    if not candidates:
        return ["请补充更多可检索信息。"]
    if not candidates[0].enabled:
        return ["精确命中的物料已禁用，请确认是否需要启用、替换为其他物料，或新建标准物料。"]
    if is_generic_query(query) and specs:
        return ["已按型号/规格找到候选，请确认是否选择该物料。"]
    if is_generic_query(query):
        return [f"“{query}”过于宽泛，请补充规格、材质、型号、口径、长度或适用设备。"]
    if len(candidates) > 1:
        return ["找到多个相近物料，请让用户确认选择哪一个，或补充规格后再检索。"]
    if specs and candidates[0].missing_specs:
        missing = "、".join(candidates[0].missing_specs)
        return [f"候选物料未命中这些规格：{missing}，请确认是否仍为同一物料。"]
    return ["匹配置信度偏低，请补充规格、品牌、型号或物料组。"]


def normalize_specs(specs: dict[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in specs.items() if value not in (None, "")}


def searchable_text(row: dict[str, Any]) -> str:
    return normalize_text(" ".join(str(row.get(field) or "") for field in row))


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
        .replace("厘", "mm")
    )
    text = re.sub(r"(?<=\d)\.0(?=\D|$)", "", text)
    text = re.sub(r"\b[mφΦ](?=\d)", "", text)
    text = re.sub(r"(?<=\d)mm\b", "", text)
    return text


def search_variants(value: Any) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []

    variants = [raw]
    normalized = normalize_text(raw)
    spec = normalize_spec_text(raw)
    for candidate in {normalized, spec}:
        if candidate:
            variants.append(candidate)
            variants.append(candidate.replace("*", "×"))
            variants.append(candidate.replace("*", "x"))
            if re.fullmatch(r"\d+(?:\.\d+)?", candidate):
                variants.append(f"{candidate}mm")
            if re.fullmatch(r"\d+(?:\.\d+)?\*\d+(?:\.\d+)?", candidate):
                variants.append(f"M{candidate}")
                variants.append(f"m{candidate}")

    return list(dict.fromkeys(variant for variant in variants if variant))


def text_list_contains(value: Any, needle: str) -> str | None:
    if not needle:
        return None
    parts = [normalize_text(part) for part in re.split(r"[,，|/；;]+", str(value or "")) if part.strip()]
    if needle in parts:
        return "exact"
    if any(needle in part or part in needle for part in parts):
        return "contains"
    return None


def token_overlap_score(query: str, searchable: str) -> int:
    tokens = re.findall(r"[a-z0-9]+(?:[.#/-][a-z0-9]+)*|[\u4e00-\u9fff]{2,}", query)
    if not tokens:
        return 0
    hits = sum(1 for token in tokens if token in searchable)
    return min(20, hits * 5)


def confidence_for_score(score: int) -> str:
    if score >= 90:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def is_generic_query(query: str) -> bool:
    return normalize_text(query) in {
        "接头",
        "管",
        "线",
        "板",
        "阀",
        "螺丝",
        "螺母",
        "弯头",
        "三通",
        "油漆",
        "电缆",
        "电线",
        "开关",
    }
