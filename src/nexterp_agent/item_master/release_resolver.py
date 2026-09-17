from __future__ import annotations

from dataclasses import dataclass, replace
import csv
import json
from pathlib import Path
import re
from typing import Any, Iterable, Literal, Mapping

from .vector_retrieval import TextVectorIndex, material_vector_text
from .source_identity import normalize_source_records


DEFAULT_RELEASE_CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "material_master"
    / "release_v1_0"
    / "material_master_release_v1_0.tsv"
)

DEFAULT_GPC_PLACEMENTS_PATH = (
    Path(__file__).resolve().parents[3]
    / ".runtime"
    / "material-master"
    / "gpc-material-placements.jsonl"
)
DEFAULT_ITEM_CODE_MAP_PATH = (
    Path(__file__).resolve().parents[3]
    / ".runtime"
    / "erpnext-material-test"
    / "material-item-code-map.json"
)
DEFAULT_FREQUENCY_CLUSTERS_PATH = (
    Path(__file__).resolve().parents[3]
    / ".runtime"
    / "material-master"
    / "frequency-discovery"
    / "clusters.jsonl"
)
DEFAULT_APPROVED_ALIASES_PATH = (
    Path(__file__).resolve().parents[3]
    / "data"
    / "material_master"
    / "approved_material_aliases_v0_1.jsonl"
)

# Vector retrieval is deliberately kept in shadow mode during the evaluation
# round.  It may add a low-confidence review candidate, but it must not alter
# the lexical/specification ordering used by existing callers.
VECTOR_RECALL_MIN_SCORE = 0.42
VECTOR_MODES = frozenset({"off", "shadow"})
DEFAULT_VECTOR_MODE: Literal["off", "shadow"] = "off"


@dataclass(frozen=True)
class ReleaseMaterialCandidate:
    item_code: str
    item_name: str
    sku_name: str
    score: int
    match_reasons: tuple[str, ...]
    data: dict[str, str]
    vector_score: float = 0.0
    retrieval_sources: tuple[str, ...] = ()
    match_tier: int = 0
    exact_code_match: bool = False
    approved_alias_match: bool = False
    required_specs_match: bool = False

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
            "estimated_rate": self.data.get("estimated_rate"),
            "currency": self.data.get("currency"),
            "price_basis": self.data.get("price_basis"),
            "score": self.score,
            "vector_score": self.vector_score,
            "retrieval_sources": list(self.retrieval_sources),
            "match_tier": self.match_tier,
            "exact_code_match": self.exact_code_match,
            "approved_alias_match": self.approved_alias_match,
            "required_specs_match": self.required_specs_match,
            "auto_selectable": self.auto_selectable,
            "confidence": self.confidence,
            "match_reasons": list(self.match_reasons),
            "match_reason": "；".join(self.match_reasons),
            "data": self.data,
        }

    @property
    def auto_selectable(self) -> bool:
        """Only deterministic code/approved-alias matches may be selected."""

        # Current projections always carry the explicit ``approved_aliases``
        # column (even when it is empty), so they use the strict numeric-code
        # / audited-alias gate.  The immutable v1.0 compatibility release
        # predates that column; keep its historical deterministic behaviour
        # for legacy callers while it is being migrated, without allowing
        # that compatibility path into the current published catalog.
        strict_projection = "approved_aliases" in self.data or self.data.get("matching_policy") == "strict"
        if strict_projection:
            numeric_exact_code = self.exact_code_match and self.item_code.isdigit()
            return numeric_exact_code or (self.approved_alias_match and self.required_specs_match)
        return self.match_tier >= 2 or (self.approved_alias_match and self.required_specs_match)


class ReleaseMaterialResolver:
    """Resolve human material text against the governed material master release.

    This resolver is intentionally offline and deterministic. The language
    model can extract raw material text and specs, but concrete item_code/uom
    values should come from this resolver before the ToolCall is composed.
    """

    def __init__(
        self,
        catalog_path: str | Path = DEFAULT_RELEASE_CATALOG_PATH,
        *,
        vector_mode: Literal["off", "shadow"] = DEFAULT_VECTOR_MODE,
    ) -> None:
        if vector_mode not in VECTOR_MODES:
            raise ValueError(f"vector_mode 必须是 off 或 shadow，而不是 {vector_mode!r}")
        self.catalog_path = Path(catalog_path)
        self.vector_mode = vector_mode
        self.rows = load_release_catalog(self.catalog_path)
        self._vector_index: TextVectorIndex | None = None
        self._rebuild_vector_index()

    @classmethod
    def from_rows(
        cls,
        rows: list[dict[str, Any]],
        *,
        catalog_path: str | Path = "<in-memory-catalog>",
        vector_mode: Literal["off", "shadow"] = DEFAULT_VECTOR_MODE,
    ) -> "ReleaseMaterialResolver":
        """Build a resolver from a validated in-memory catalog projection."""

        if vector_mode not in VECTOR_MODES:
            raise ValueError(f"vector_mode 必须是 off 或 shadow，而不是 {vector_mode!r}")
        resolver = cls.__new__(cls)
        resolver.catalog_path = Path(catalog_path)
        resolver.vector_mode = vector_mode
        resolver.rows = [dict(row) for row in rows]
        resolver._vector_index = None
        resolver._rebuild_vector_index()
        return resolver

    def _rebuild_vector_index(self) -> None:
        if self.vector_mode != "shadow":
            self._vector_index = None
            return
        self._vector_index = TextVectorIndex()
        self._vector_index.build(
            (str(row.get("item_code") or ""), material_vector_text(row))
            for row in self.rows
        )

    @staticmethod
    def _vector_query(query: str, specs: dict[str, Any]) -> str:
        values = [str(query or "").strip()]
        values.extend(str(value).strip() for value in specs.values() if value not in (None, ""))
        return " ".join(value for value in values if value)

    def vector_similarity(self, query: str, row: dict[str, str], specs: dict[str, Any] | None = None) -> float:
        """Return the local vector signal for one release row.

        A vector match is recall assistance only.  The normal exact/spec
        gates still decide whether a material may be selected or written.
        """

        if self._vector_index is None:
            return 0.0
        return self._vector_index.score(
            self._vector_query(query, normalize_specs(specs or {})),
            str(row.get("item_code") or ""),
        )

    def vector_scores(self, query: str, specs: dict[str, Any] | None = None) -> dict[str, float]:
        """Score the whole release in one query-vector pass."""

        if self._vector_index is None:
            return {}
        query_text = self._vector_query(query, normalize_specs(specs or {}))
        matches = self._vector_index.query(query_text, limit=max(1, len(self.rows)), min_score=-1.0)
        return {match.document_id: match.score for match in matches}

    def resolve(
        self,
        query: str,
        *,
        specs: dict[str, Any] | None = None,
        limit: int = 10,
        _vector_scores: Mapping[str, float] | None = None,
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

        vector_scores = (
            dict(_vector_scores)
            if self.vector_mode == "shadow" and _vector_scores is not None
            else self.vector_scores(query, specs)
            if self.vector_mode == "shadow"
            else {}
        )
        ranked_candidates: list[ReleaseMaterialCandidate] = []
        for row in self.rows:
            lexical = score_release_row(row, query, specs)
            vector_score = vector_scores.get(str(row.get("item_code") or ""), 0.0)
            # Shadow mode must not change the existing candidate set. A
            # vector-only hit is measured by the offline evaluator, but is
            # not returned to production callers until a labelled review set
            # proves that the recall gain is safe.
            if lexical.score <= 0:
                continue
            # Keep the governed lexical score as the ranking score.  The
            # vector signal is recorded for offline comparison only; adding a
            # bonus here would make the new path silently change production
            # choices before it has a labelled evaluation set.
            combined_score = lexical.score
            reasons = list(lexical.match_reasons)
            sources = ["关键词/属性规则"] if lexical.score > 0 else []
            if vector_score >= VECTOR_RECALL_MIN_SCORE:
                reasons.append("向量相似信号（影子评估）")
                sources.append("local_char_ngram_vector")
            ranked_candidates.append(replace(
                lexical,
                score=combined_score,
                match_reasons=tuple(dict.fromkeys(reasons)),
                vector_score=vector_score,
                retrieval_sources=tuple(sources),
            ))
        ranked = sorted(
            ranked_candidates,
            # Deterministic retrieval order: code, approved alias, standard
            # type, exact specs, then ordinary lexical candidates.  Vector
            # scores are deliberately absent from this key.
            key=lambda candidate: (-candidate.match_tier, -candidate.score, candidate.item_code),
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


def load_current_published_catalog(
    placements_path: str | Path = DEFAULT_GPC_PLACEMENTS_PATH,
    item_code_map_path: str | Path = DEFAULT_ITEM_CODE_MAP_PATH,
    frequency_clusters_path: str | Path | None = None,
    *,
    approved_aliases_path: str | Path | None = DEFAULT_APPROVED_ALIASES_PATH,
    enabled_item_codes: Iterable[str] | None = None,
) -> list[dict[str, str]]:
    """Load the currently published GPC/ERPNext material surface.

    The historical release TSV is intentionally retained for compatibility
    with offline intake tests.  Runtime-facing evaluations must use the
    placement JSONL plus the ERPNext readback map instead: the former carries
    the governed names/specifications and the latter proves that each local
    material is mapped to the current numeric Item Code.  Unmapped or
    non-numeric entries are excluded rather than silently falling back to a
    legacy local ID.
    """

    placement_file = Path(placements_path)
    map_file = Path(item_code_map_path)
    if not placement_file.exists() or not map_file.exists():
        return []

    with map_file.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    code_map = payload.get("material_item_codes", payload)
    if not isinstance(code_map, dict):
        return []
    enabled_codes = (
        {str(value).strip() for value in enabled_item_codes}
        if enabled_item_codes is not None
        else None
    )

    placements: list[dict[str, Any]] = []
    with placement_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                placements.append(json.loads(line))

    # Frequency discovery is a prioritisation signal, not an approval.  Only
    # an explicit alias review file may add a searchable alias.  In particular,
    # the legacy ``frequency_clusters_path`` argument is intentionally ignored
    # for publication so a high-confidence cluster cannot silently poison a
    # SKU before a person confirms its target.
    approved_aliases_by_material_id: dict[str, list[str]] = {}
    if approved_aliases_path and Path(approved_aliases_path).is_file():
        with Path(approved_aliases_path).open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    alias_row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                approval = str(
                    alias_row.get("review_decision")
                    or alias_row.get("status")
                    or ""
                ).casefold()
                if approval not in {"approved", "已审核", "confirmed", "通过", "确认"}:
                    continue
                # A status flag without an accountable reviewer and review
                # timestamp is not an approved alias.  This prevents a
                # hand-edited experiment row from becoming an auto-select key.
                if not str(alias_row.get("reviewer") or "").strip() or not str(alias_row.get("reviewed_at") or "").strip():
                    continue
                alias = str(alias_row.get("alias") or alias_row.get("raw_name") or "").strip()
                target = str(
                    alias_row.get("source_material_id")
                    or alias_row.get("material_id")
                    or alias_row.get("target_id")
                    or ""
                ).strip()
                if not alias or not target:
                    continue
                if target not in code_map:
                    target = next((material_id for material_id, code in code_map.items() if str(code) == target), "")
                if target:
                    approved_aliases_by_material_id.setdefault(target, []).append(alias)

    rows: list[dict[str, str]] = []
    for placement in placements:
        material_id = str(placement.get("material_id") or "").strip()
        item_code = str(code_map.get(material_id) or "").strip()
        if not material_id or not re.fullmatch(r"\d+", item_code):
            continue
        if enabled_codes is not None and item_code not in enabled_codes:
            continue
        material_name = str(placement.get("material_name") or "").strip()
        standard_name = str(placement.get("standard_type") or material_name).strip()
        attributes = placement.get("procurement_attributes") or {}
        if not isinstance(attributes, dict):
            attributes = {}
        source_records = normalize_source_records(placement.get("source_records"))
        attribute_text = "；".join(
            f"{key}={value}" for key, value in attributes.items() if value not in (None, "")
        )
        price_drivers = placement.get("price_drivers") or ""
        if isinstance(price_drivers, dict):
            price_drivers = "；".join(
                f"{key}={value}" for key, value in price_drivers.items() if value not in (None, "")
            )
        rows.append(
            {
                    "item_code": item_code,
                    "item_name": standard_name,
                    "sku_name": material_name,
                    "standard_name": standard_name,
                    "top_group": "",
                    "sub_group": "",
                    "material_family": standard_name,
                    "item_group": str(placement.get("gpc_brick_code") or ""),
                    "required_specs": attribute_text,
                    "optional_specs": str(placement.get("specification_basis") or ""),
                    # Internal material IDs and standard names are lookup
                    # fields, not approved aliases.  Keep this legacy column
                    # empty on the current surface so experiment-generated
                    # names cannot leak into the alias channel.
                    "aliases": "",
                    "approved_aliases": "；".join(dict.fromkeys(
                        approved_aliases_by_material_id.get(material_id, [])
                    )),
                    "search_keywords": "；".join(
                        value
                        for value in (
                            str(placement.get("gpc_brick_code") or ""),
                            str(placement.get("internal_category_code") or ""),
                            str(placement.get("source_reference") or ""),
                        )
                        if value
                    ),
                    "brand": "",
                    "model": "",
                    "stock_uom": str(placement.get("stock_uom") or ""),
                    "status": "active" if enabled_codes is not None else "mapped_unverified",
                    "erpnext_status": "enabled" if enabled_codes is not None else "unverified",
                    "agent_use_policy": "auto_select_allowed" if enabled_codes is not None else "review_required",
                    "source_material_id": material_id,
                    "source_dataset": str(placement.get("source_dataset") or ""),
                    "source_document": str(placement.get("source_document") or ""),
                    "source_sheet": str(placement.get("source_sheet") or ""),
                    "source_records": json.dumps(source_records, ensure_ascii=False, sort_keys=True),
                    "source_catalog": "gpc-material-placements + erpnext-item-code-map",
                    "price_drivers": str(price_drivers),
            }
        )
    return rows


def score_release_row(row: dict[str, str], query: str, specs: dict[str, Any]) -> ReleaseMaterialCandidate:
    query_norm = normalize_text(query)
    query_spec = normalize_spec_text(query)
    spec_values = [str(value) for value in specs.values() if value not in (None, "")]
    spec_norms = {normalize_spec_text(value) for value in spec_values if normalize_spec_text(value)}

    item_code = row.get("item_code", "")
    item_name = row.get("item_name", "")
    sku_name = row.get("sku_name", "")
    required_specs = row.get("required_specs", "")
    code_norm = normalize_text(item_code)
    item_name_norm = normalize_text(item_name)
    sku_name_norm = normalize_text(sku_name)
    # Frozen release aliases are treated as approved.  Runtime/current
    # projections must opt in through the separate approved_aliases field;
    # source IDs and standard names are not aliases by themselves.
    if "approved_aliases" in row:
        aliases = split_terms(row.get("approved_aliases", ""))
    else:
        aliases = [
            alias for alias in split_terms(row.get("aliases", ""))
            if normalize_text(alias) not in {code_norm, item_name_norm, normalize_text(row.get("standard_name", ""))}
        ]
    search_keywords = row.get("search_keywords", "")

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
                row.get("approved_aliases", ""),
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

    exact_code_match = bool(query_norm and query_norm == code_norm)
    approved_alias_match = bool(query_norm and query_norm in aliases_norm)
    required_specs_match = _required_specs_match(row, query, specs)
    if exact_code_match:
        match_tier = 5
    elif approved_alias_match:
        match_tier = 4
    elif query_norm and query_norm == item_name_norm:
        match_tier = 3
    elif query_norm and query_norm == sku_name_norm:
        match_tier = 2
    elif _has_exact_spec_match(query, specs, sku_name, required_specs):
        match_tier = 1
    else:
        match_tier = 0

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
        match_tier=match_tier,
        exact_code_match=exact_code_match,
        approved_alias_match=approved_alias_match,
        required_specs_match=required_specs_match,
    )


def _has_exact_spec_match(
    query: str,
    specs: dict[str, Any],
    sku_name: str,
    required_specs: str,
) -> bool:
    query_spec = normalize_spec_text(query)
    if query_spec and (query_spec in normalize_spec_text(sku_name) or query_spec in normalize_spec_text(required_specs)):
        return True
    return any(
        normalize_spec_text(value)
        and (
            normalize_spec_text(value) in normalize_spec_text(sku_name)
            or normalize_spec_text(value) in normalize_spec_text(required_specs)
        )
        for value in specs.values()
        if value not in (None, "")
    )


def _required_specs_match(row: dict[str, str], query: str, specs: dict[str, Any]) -> bool:
    required = str(row.get("required_specs") or "").strip()
    if not required:
        return True
    query_text = normalize_spec_text(" ".join([query, *[str(value) for value in specs.values()]]))
    values: list[str] = []
    for part in re.split(r"[；;|]+", required):
        if "=" in part:
            value = part.split("=", 1)[1].strip()
        elif ":" in part:
            value = part.split(":", 1)[1].strip()
        else:
            value = part.strip()
        if value:
            values.append(normalize_spec_text(value))
    return bool(values) and all(value in query_text for value in values)


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

    if candidates[0].auto_selectable and is_exact_item_code(query, candidates[0]):
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

    # An explicitly approved alias is a deterministic lookup key.  Its
    # required attributes must already match, but the text score itself is
    # not a second (and arbitrary) approval gate.  This keeps the policy
    # aligned with the retrieval order: only a numeric code or an approved
    # alias plus complete required attributes may auto-select.
    if (
        candidates[0].auto_selectable
        and candidates[0].approved_alias_match
        and candidates[0].required_specs_match
    ):
        return {
            "status": "ready",
            "top_score": top_score,
            "second_score": second_score,
            "score_gap": score_gap,
            "why_status": "已审核别名与必选属性完整命中，可以直接使用。",
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
