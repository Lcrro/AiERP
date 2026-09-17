"""Read-only reference catalog indexes used by the internal catalog browser.

The existing :mod:`tariff_taxonomy` module remains the compatibility adapter for
the HS catalog.  This module owns the GPC representation so that GPC's
attributes and values stay on Brick profiles rather than becoming fake tree
levels.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .procurement_templates import ProcurementTemplateRegistry
from .vector_retrieval import TextVectorIndex


GPC_KIND_ORDER = {"segment": 0, "family": 1, "class": 2, "brick": 3}
GPC_KIND_LABELS = {
    "segment": "Segment",
    "family": "Family",
    "class": "Class",
    "brick": "Brick",
}
GPC_KIND_LABELS_ZH = {
    "segment": "段",
    "family": "族",
    "class": "类",
    "brick": "砖块",
}
INTERNAL_BRICK_KIND = "internal_brick"
INTERNAL_FAMILY_KIND = "internal_family"
INTERNAL_TYPE_KIND = "internal_type"
# Backwards-compatible public name used by the first internal leaf feature.
INTERNAL_KIND = INTERNAL_TYPE_KIND
INTERNAL_KINDS = frozenset({INTERNAL_BRICK_KIND, INTERNAL_FAMILY_KIND, INTERNAL_TYPE_KIND})
INTERNAL_LEAF_KINDS = frozenset({INTERNAL_TYPE_KIND})
INTERNAL_KIND_LABELS = {
    INTERNAL_BRICK_KIND: "Brick",
    INTERNAL_FAMILY_KIND: "Material Family",
    INTERNAL_TYPE_KIND: "Standard Type",
}
INTERNAL_KIND_LABELS_ZH = {
    INTERNAL_BRICK_KIND: "砖块",
    INTERNAL_FAMILY_KIND: "物料族",
    INTERNAL_TYPE_KIND: "标准类型",
}
_NODE_KIND_ORDER = {
    **GPC_KIND_ORDER,
    INTERNAL_BRICK_KIND: 3,
    INTERNAL_FAMILY_KIND: 4,
    INTERNAL_TYPE_KIND: 5,
}
_SPACE_RE = re.compile(r"\s+")
_RETRIEVAL_PUNCTUATION_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+", re.IGNORECASE)
PROFILE_TERM_REFERENCE_LIMIT = 24


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_runtime_path(root: Path, relative: str) -> Path:
    """Resolve a generated file without allowing runtime path escape."""

    root = Path(root).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("参考目录运行期文件路径越界") from exc
    return candidate


def _source_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _retrieval_text(value: Any) -> str:
    return _RETRIEVAL_PUNCTUATION_RE.sub("", _as_text(value).casefold())


def _character_bigrams(value: str) -> set[str]:
    compact = _retrieval_text(value)
    if len(compact) < 2:
        return {compact} if compact else set()
    return {compact[index:index + 2] for index in range(len(compact) - 1)}


class ChatgptClassificationIndex:
    """Read-only hierarchy adapter for the ChatGPT classification release.

    The ChatGPT workbook is a material classification release rather than a
    GPC reference package.  This adapter deliberately exposes the same small
    read-only tree contract as :class:`GpcReferenceIndex`, so the current
    taxonomy browser can switch sources without creating a second UI or
    pretending that the preview is an ERPNext classification.
    """

    KIND_ORDER = {"segment": 0, "family": 1, "internal_type": 2}
    KIND_LABELS = {
        "segment": "分类组",
        "family": "物料分类",
        "internal_type": "物料族",
    }
    KIND_LABELS_ZH = {
        "segment": "一级分类",
        "family": "二级分类",
        "internal_type": "物料族",
    }

    def __init__(self, payload: Mapping[str, Any], *, source_path: Path | None = None) -> None:
        self.source_path = Path(source_path).resolve() if source_path else None
        self.source_meta = dict(payload)
        self._nodes: dict[str, dict[str, Any]] = {}
        self._children: dict[str | None, list[str]] = defaultdict(list)
        self._materials_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._rows: list[dict[str, Any]] = []
        type_codes: dict[tuple[str, str], str] = {}
        type_code_owners: dict[str, str] = {}
        for raw in payload.get("rows") or []:
            row = deepcopy(dict(raw))
            item_code = _as_text(row.get("item_code") or row.get("material_id"))
            family_code = _as_text(row.get("family_code"))
            top_group = _as_text(row.get("top_group") or row.get("segment_name")) or "未分组"
            sub_group = _as_text(row.get("sub_group")) or top_group
            standard_type = _as_text(row.get("standard_type") or row.get("material_family")) or "未命名物料族"
            if not item_code or not family_code:
                continue
            segment_code = _as_text(row.get("segment_code")) or f"CHATGPT-L1-{top_group}"
            category_code = _as_text(row.get("category_code")) or f"CHATGPT-L2-{top_group}|{sub_group}"
            self._ensure_node(segment_code, top_group, "segment", 0, None)
            self._ensure_node(category_code, sub_group, "family", 1, segment_code)
            type_key = (category_code, family_code)
            type_code = type_codes.get(type_key)
            if type_code is None:
                type_code = family_code
                owner = type_code_owners.get(type_code)
                if owner is not None and owner != category_code:
                    type_code = f"{family_code}-{hashlib.sha256(category_code.encode('utf-8')).hexdigest()[:6]}"
                type_codes[type_key] = type_code
                type_code_owners[type_code] = category_code
            material = self._material_payload(row, item_code, type_code)
            self._ensure_node(type_code, standard_type, "internal_type", 2, category_code)
            self._materials_by_type[type_code].append(material)
            self._rows.append(material)
        for children in self._children.values():
            children.sort(key=lambda code: (self._nodes[code]["level"], self._nodes[code]["name"], code))
        self._assign_display_codes()
        self._rows.sort(key=lambda row: (_as_text(row.get("material_name")), _as_text(row.get("item_code"))))

    @staticmethod
    def _material_payload(raw: Mapping[str, Any], item_code: str, family_code: str) -> dict[str, Any]:
        material = deepcopy(dict(raw))
        material["item_code"] = item_code
        material["material_id"] = item_code
        material["gpc_brick_code"] = family_code
        material["classification_source"] = "chatgpt_v4"
        material["review_status"] = "ChatGPT 分类待复核"
        material["completeness_status"] = "完整"
        material["stock_uom"] = _as_text(material.get("stock_uom")) or "—"
        material["material_name"] = _as_text(material.get("material_name") or material.get("item_name"))
        material["standard_type"] = _as_text(material.get("standard_type") or material.get("material_family"))
        material["source_rows"] = [material.get("source_row")] if material.get("source_row") is not None else []
        material.setdefault("gpc_notes", ["ChatGPT 分类 V4；来源于龙华项目公司第四轮附件治理工作簿。"])
        material.setdefault("questions", [])
        return material

    def _ensure_node(self, code: str, name: str, kind: str, level: int, parent_code: str | None) -> None:
        if code in self._nodes:
            return
        node = {
            "code": code,
            "official_name": "",
            "name": name,
            "working_name": name,
            "kind": kind,
            "level": level,
            "parent_code": parent_code,
            "source": "ChatGPT 分类（龙华 V4）",
            "is_gpc": False,
            "classification_source": "chatgpt_v4",
            "translation_status": "human_confirmed",
            "display_code": "",
        }
        self._nodes[code] = node
        self._children[parent_code].append(code)

    def _assign_display_codes(self) -> None:
        """Give the preview tree simple numeric labels without exposing source IDs."""

        for segment_index, segment_code in enumerate(self._children.get(None, ()), 1):
            segment = self._nodes[segment_code]
            segment["display_code"] = f"{segment_index:02d}"
            for family_index, family_code in enumerate(self._children.get(segment_code, ()), 1):
                family = self._nodes[family_code]
                family["display_code"] = f"{segment['display_code']}{family_index:02d}"
                for type_index, type_code in enumerate(self._children.get(family_code, ()), 1):
                    self._nodes[type_code]["display_code"] = f"{family['display_code']}{type_index:02d}"

    def _payload(self, node: Mapping[str, Any]) -> dict[str, Any]:
        code = _as_text(node["code"])
        descendants = self._descendant_material_count(code)
        children = len(self._children.get(code, ()))
        return {
            **node,
            "kind_label": self.KIND_LABELS[node["kind"]],
            "kind_label_zh": self.KIND_LABELS_ZH[node["kind"]],
            "classification_source": "chatgpt_v4",
            "is_gpc": False,
            "child_count": children,
            "catalog_child_count": children,
            "has_children": children > 0,
            "direct_material_count": len(self._materials_by_type.get(code, ())),
            "actual_material_count": descendants,
            "has_actual_materials": descendants > 0,
            "internal_child_count": 0,
        }

    def _descendant_material_count(self, code: str) -> int:
        direct = len(self._materials_by_type.get(code, ()))
        return direct + sum(self._descendant_material_count(child) for child in self._children.get(code, ()))

    def path(self, code: str) -> list[dict[str, Any]]:
        normalized = _as_text(code)
        if normalized not in self._nodes:
            raise ValueError(f"ChatGPT 分类节点不存在：{normalized}")
        chain = []
        seen: set[str] = set()
        current: dict[str, Any] | None = self._nodes[normalized]
        while current is not None:
            if current["code"] in seen:
                raise ValueError(f"ChatGPT 分类存在循环引用：{current['code']}")
            seen.add(current["code"])
            chain.append(self._payload(current))
            parent = _as_text(current.get("parent_code"))
            current = self._nodes.get(parent) if parent else None
        chain.reverse()
        return chain

    def summary(self) -> dict[str, Any]:
        counts = Counter(node["kind"] for node in self._nodes.values())
        return {
            "catalog": "gpc",
            "available": True,
            "source": "ChatGPT 分类（龙华 V4）",
            "source_url": "",
            "source_version": "chatgpt-classification-v4",
            "generated_at": _as_text(self.source_meta.get("generated_at")),
            "release_hash": _as_text(self.source_meta.get("release_hash")),
            "classification_source": "chatgpt_v4",
            "classification_label": _as_text(self.source_meta.get("classification_label")) or "ChatGPT 分类（龙华 V4）",
            "read_only": True,
            "total_nodes": len(self._nodes),
            "browsable_total_nodes": len(self._nodes),
            "internal_extension_count": 0,
            "counts": dict(counts),
            "kind_labels": self.KIND_LABELS,
            "kind_labels_zh": self.KIND_LABELS_ZH,
            "levels": [
                {"kind": kind, "label": self.KIND_LABELS[kind], "label_zh": self.KIND_LABELS_ZH[kind], "level": level, "count": counts.get(kind, 0)}
                for kind, level in self.KIND_ORDER.items()
            ],
            "root_count": len(self._children.get(None, ())),
            "hierarchy_complete": True,
            "parent_missing_count": 0,
            "duplicate_code_count": 0,
            "orphan_brick_count": 0,
            "attribute_count": 0,
            "attribute_value_count": 0,
            "actual_material_count": len(self._rows),
            "materialized_brick_count": counts.get("internal_type", 0),
            "materialized_node_count": len(self._nodes),
            "materialized_counts": {kind: counts.get(kind, 0) for kind in (*self.KIND_ORDER, "internal_brick", "internal_family", "internal_type")},
            "material_record_counts": {"sku_candidate": len(self._rows)},
        }

    def children(self, parent_code: str | None = None, *, materialized_only: bool = False) -> list[dict[str, Any]]:
        normalized = _as_text(parent_code) or None
        if normalized is not None and normalized not in self._nodes:
            raise ValueError(f"ChatGPT 分类节点不存在：{normalized}")
        rows = []
        for code in self._children.get(normalized, ()):
            node = self._nodes[code]
            if materialized_only and self._descendant_material_count(code) <= 0:
                continue
            payload = self._payload(node)
            payload["full_path"] = self.path(code)
            rows.append(payload)
        return rows

    def search(self, query: str, *, kind: str = "", limit: int = 100, materialized_only: bool = False) -> dict[str, Any]:
        needle = _as_text(query).casefold()
        if not needle:
            return {"rows": [], "total": 0, "truncated": False}
        if kind and kind not in self.KIND_ORDER:
            raise ValueError(f"未知 ChatGPT 分类层级：{kind}")
        compact = _SPACE_RE.sub("", needle)
        matches: list[tuple[tuple[int, int, str], dict[str, Any]]] = []
        for node in self._nodes.values():
            if kind and node["kind"] != kind:
                continue
            haystack = " ".join((node["code"], node.get("display_code", ""), node["name"], node.get("working_name", "")))
            materials = self._materials_by_type.get(node["code"], ())
            if materials:
                haystack += " " + " ".join(
                    " ".join((_as_text(row.get("item_code")), _as_text(row.get("material_name")), _as_text(row.get("aliases")), _as_text(row.get("search_text"))))
                    for row in materials
                )
            compact_haystack = _SPACE_RE.sub("", haystack).casefold()
            if needle not in haystack.casefold() and compact not in compact_haystack:
                continue
            code = _as_text(node["code"])
            rank = 0 if code.casefold() == needle else 1 if code.casefold().startswith(needle) else 2 if node["name"].casefold().startswith(needle) else 3
            payload = self._payload(node)
            payload["result_type"] = "node"
            payload["path"] = self.path(code)
            payload["full_path"] = payload["path"]
            matches.append(((rank, self.KIND_ORDER[node["kind"]], code), payload))
        matches.sort(key=lambda item: item[0])
        bounded = min(200, max(1, int(limit)))
        return {"rows": [row for _rank, row in matches[:bounded]], "total": len(matches), "truncated": len(matches) > bounded}

    def profile(self, code: str) -> dict[str, Any]:
        normalized = _as_text(code)
        node = self._nodes.get(normalized)
        if node is None:
            raise ValueError(f"ChatGPT 分类节点不存在：{normalized}")
        materials = deepcopy(self._materials_by_type.get(normalized, ()))
        attributes: dict[str, set[str]] = defaultdict(set)
        for material in materials:
            for field in ("procurement_attributes", "price_drivers"):
                for key, value in (material.get(field) or {}).items():
                    if _as_text(key) and _as_text(value):
                        attributes[_as_text(key)].add(_as_text(value))
        return {
            "code": normalized,
            "kind": node["kind"],
            "is_gpc": False,
            "classification_source": "chatgpt_v4",
            "working_name": node["name"],
            "official_name": "",
            "definition_working": "ChatGPT 分类 V4 物料族；仅用于分类预览，正式采购仍以 ERPNext 为准。",
            "includes_working": "",
            "excludes_working": "",
            "attributes": [
                {"code": f"CHATGPT-ATTR-{index:02d}", "name": key, "working_name": key, "values": [{"code": f"CHATGPT-VALUE-{index:02d}-{value_index:02d}", "name": value, "working_name": value} for value_index, value in enumerate(sorted(values), 1)]}
                for index, (key, values) in enumerate(sorted(attributes.items()), 1)
            ],
            "path": self.path(normalized),
            "actual_materials": materials,
            "direct_material_count": len(materials),
            "actual_material_count": self._descendant_material_count(normalized),
        }


class GpcReferenceIndex:
    """In-memory GPC Segment → Family → Class → Brick index."""

    def __init__(
        self,
        nodes: Iterable[Mapping[str, Any]],
        profiles: Iterable[Mapping[str, Any]] = (),
        translations: Iterable[Mapping[str, Any]] = (),
        profile_translations: Iterable[Mapping[str, Any]] = (),
        profile_text_translations: Iterable[Mapping[str, Any]] = (),
        material_placements: Iterable[Mapping[str, Any]] = (),
        procurement_registry: ProcurementTemplateRegistry | None = None,
        *,
        internal_extensions: Iterable[Mapping[str, Any]] = (),
        source_meta: Mapping[str, Any] | None = None,
        source_path: Path | None = None,
        vector_mode: str = "off",
    ) -> None:
        if vector_mode not in {"off", "shadow"}:
            raise ValueError(f"vector_mode 必须是 off 或 shadow，而不是 {vector_mode!r}")
        # Reference browsing and candidate generation stay cheap by default.
        # The local character vector lane is an explicit offline/shadow opt-in.
        self.vector_mode = vector_mode
        self.source_meta = dict(source_meta or {})
        self.source_path = Path(source_path).resolve() if source_path else None
        self._nodes: dict[str, dict[str, Any]] = {}
        self._children: dict[str | None, list[str]] = defaultdict(list)
        self._profiles: dict[str, dict[str, Any]] = {}
        self._translations: dict[str, dict[str, Any]] = {}
        self._profile_translations: dict[str, dict[str, Any]] = {}
        self._profile_text_translations: dict[str, dict[str, Any]] = {}
        self._profile_terms: dict[str, dict[str, Any]] = {}
        self._material_placements: list[dict[str, Any]] = []
        self._materials_by_brick: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._material_counts: Counter[str] = Counter()
        self._procurement_registry = procurement_registry

        for raw in nodes:
            code = _as_text(raw.get("code"))
            if not code:
                continue
            if code in self._nodes:
                raise ValueError(f"GPC 存在重复编码：{code}")
            kind = _as_text(raw.get("kind"))
            if kind not in GPC_KIND_ORDER:
                raise ValueError(f"GPC 层级类型无效：{code} ({kind})")
            parent = _as_text(raw.get("parent_code")) or None
            level = int(raw.get("level", GPC_KIND_ORDER[kind]))
            official_name = _as_text(raw.get("official_name") or raw.get("name"))
            node = {
                "code": code,
                "official_name": official_name,
                "name": _as_text(raw.get("name") or official_name),
                "kind": kind,
                "level": level,
                "parent_code": parent,
                "source": _as_text(raw.get("source") or "GS1 GPC 2026-05"),
                "is_gpc": True,
            }
            self._nodes[code] = node
            self._children[parent].append(code)

        internal_profiles: dict[str, dict[str, Any]] = {}
        pending_extensions = [dict(row) for row in internal_extensions]
        declared_codes: set[str] = set()
        for raw in pending_extensions:
            code = _as_text(raw.get("code"))
            if not re.fullmatch(r"\d{10}(?:\d{2})*", code):
                raise ValueError("内部扩展类目编码必须是在父级编码后追加两位数字")
            if code in self._nodes or code in declared_codes:
                raise ValueError(f"内部扩展类目编码重复：{code}")
            declared_codes.add(code)

        # Internal overlays may extend an official Brick by two sparse levels:
        # Brick -> internal material family -> internal standard type.  Resolve
        # them parent-first so the JSON file does not need a fragile row order.
        while pending_extensions:
            unresolved: list[dict[str, Any]] = []
            progressed = False
            for raw in pending_extensions:
                code = _as_text(raw.get("code"))
                parent = _as_text(raw.get("parent_code"))
                parent_node = self._nodes.get(parent)
                if parent_node is None:
                    unresolved.append(raw)
                    continue
                kind = _as_text(raw.get("kind")) or INTERNAL_TYPE_KIND
                if kind not in INTERNAL_KINDS:
                    raise ValueError(f"内部扩展类目类型无效：{code} ({kind})")
                if kind == INTERNAL_BRICK_KIND:
                    valid_parent = parent_node.get("kind") == "class" and parent_node.get("is_gpc", True)
                elif kind == INTERNAL_FAMILY_KIND:
                    valid_parent = parent_node.get("kind") in {"brick", INTERNAL_BRICK_KIND}
                else:
                    valid_parent = parent_node.get("kind") == INTERNAL_FAMILY_KIND
                if not valid_parent:
                    raise ValueError(f"内部扩展类目父级无效：{code} -> {parent}")
                if code[:-2] != parent or code[-2:] == "00":
                    raise ValueError(f"内部扩展类目编码必须等于父级编码追加 01–99：{code} -> {parent}")
                expected_level = int(parent_node.get("level", -1)) + 1
                level = int(raw.get("level", expected_level))
                if level != expected_level:
                    raise ValueError(f"内部扩展类目层级不匹配：{code}")
                working_name = _as_text(raw.get("working_name") or raw.get("name"))
                if not working_name:
                    raise ValueError(f"内部扩展类目缺少名称：{code}")
                node = {
                    "code": code,
                    "official_name": "",
                    "name": working_name,
                    "working_name": working_name,
                    "kind": kind,
                    "level": level,
                    "parent_code": parent,
                    "source": "物料分类工作台",
                    "is_gpc": False,
                    "translation_status": "human_confirmed",
                    "translation_source_hash": "",
                }
                self._nodes[code] = node
                self._children[parent].append(code)
                internal_profiles[code] = {
                    "code": code,
                    "kind": kind,
                    "is_gpc": False,
                    "classification_source": "nexterp_internal",
                    "definition_working": _as_text(raw.get("definition_working")),
                    "includes_working": _as_text(raw.get("includes_working")),
                    "excludes_working": _as_text(raw.get("excludes_working")),
                    "attributes": deepcopy(list(raw.get("attributes") or [])),
                }
                progressed = True
            if not progressed:
                raw = unresolved[0]
                raise ValueError(
                    f"内部扩展类目父级不存在或形成循环：{_as_text(raw.get('code'))} -> "
                    f"{_as_text(raw.get('parent_code'))}"
                )
            pending_extensions = unresolved

        for raw in profiles:
            code = _as_text(raw.get("code"))
            if code:
                self._profiles[code] = dict(raw)
        self._profiles.update(internal_profiles)
        for raw in translations:
            code = _as_text(raw.get("code"))
            if code:
                self._translations[code] = dict(raw)
        for raw in profile_translations:
            code = _as_text(raw.get("code"))
            if code:
                self._profile_translations[code] = dict(raw)
        for raw in profile_text_translations:
            source_hash = _as_text(raw.get("source_hash"))
            if source_hash:
                self._profile_text_translations[source_hash] = dict(raw)

        for code, node in self._nodes.items():
            if node.get("is_gpc") is False:
                continue
            translation = self._translations.get(code, {})
            working_name = _as_text(translation.get("working_name"))
            status = _as_text(translation.get("status")) or ("missing" if not working_name else "machine")
            node["working_name"] = working_name or node["official_name"]
            node["translation_status"] = status
            node["translation_source_hash"] = _as_text(translation.get("source_hash")) or _source_hash(node["official_name"])

        for child_codes in self._children.values():
            child_codes.sort(
                key=lambda code: (
                    int(self._nodes[code].get("level", 0)),
                    _NODE_KIND_ORDER.get(self._nodes[code]["kind"], 99),
                    code,
                )
            )

        missing = [node["code"] for node in self._nodes.values() if node["parent_code"] and node["parent_code"] not in self._nodes]
        if missing:
            raise ValueError(f"GPC 存在缺失父级：{missing[0]}")
        issues = self.validate()
        if issues:
            raise ValueError(f"GPC 目录校验失败：{issues[0]}")
        self._load_material_placements(material_placements)
        self._build_profile_terms()

    @classmethod
    def from_runtime(
        cls,
        runtime_root: Path,
        version: str = "2026-05",
        *,
        material_placements_path: Path | None = None,
        procurement_template_catalog_path: Path | None = None,
        procurement_type_profiles_path: Path | None = None,
        internal_extensions_path: Path | None = None,
    ) -> "GpcReferenceIndex":
        root = Path(runtime_root).resolve()
        if not re.fullmatch(r"\d{4}-\d{2}", str(version)):
            raise ValueError("GPC 版本格式必须为 YYYY-MM")
        version_root = _safe_runtime_path(root, version)
        manifest_path = _safe_runtime_path(version_root, "manifest.json")
        nodes_path = _safe_runtime_path(version_root, "nodes.jsonl")
        profiles_path = _safe_runtime_path(version_root, "brick-profiles.jsonl")
        translations_path = _safe_runtime_path(version_root, "translations.zh-CN.jsonl")
        profile_translations_path = _safe_runtime_path(version_root, "profile-translations.zh-CN.jsonl")
        profile_text_translations_path = _safe_runtime_path(version_root, "profile-text-translations.zh-CN.jsonl")
        if not manifest_path.is_file() or not nodes_path.is_file():
            raise FileNotFoundError(f"GPC {version} 尚未导入；请运行 import_gpc_reference.py --version {version}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if _as_text(manifest.get("version")) != version:
            raise ValueError("GPC 运行期包版本与请求版本不一致")

        def load_jsonl(path: Path) -> list[dict[str, Any]]:
            if not path.is_file():
                return []
            with path.open("r", encoding="utf-8") as handle:
                return [json.loads(line) for line in handle if line.strip()]

        material_placements: list[dict[str, Any]] = []
        if material_placements_path is not None:
            placements_path = Path(material_placements_path).resolve()
            if placements_path.is_file():
                material_placements = load_jsonl(placements_path)
        procurement_registry = None
        if procurement_template_catalog_path is not None:
            procurement_registry = ProcurementTemplateRegistry.from_files(
                procurement_template_catalog_path,
                procurement_type_profiles_path,
            )
        internal_extensions: list[dict[str, Any]] = []
        if internal_extensions_path is not None:
            extensions_path = Path(internal_extensions_path).resolve()
            if extensions_path.is_file():
                payload = json.loads(extensions_path.read_text(encoding="utf-8"))
                if int(payload.get("schema_version") or 0) != 1:
                    raise ValueError("Nexterp 内部扩展类目版本无效")
                internal_extensions = [dict(row) for row in payload.get("extensions") or []]

        node_rows = load_jsonl(nodes_path)
        known_codes = {_as_text(row.get("code")) for row in node_rows}
        # The internal overlay is optional.  A deliberately partial GPC test or
        # recovery package should still load its official nodes when the
        # extension parent is outside that package.
        available_extensions: list[dict[str, Any]] = []
        pending_extensions = list(internal_extensions)
        while pending_extensions:
            accepted = [
                row for row in pending_extensions
                if _as_text(row.get("parent_code")) in known_codes
            ]
            if not accepted:
                break
            available_extensions.extend(accepted)
            known_codes.update(_as_text(row.get("code")) for row in accepted)
            accepted_codes = {_as_text(row.get("code")) for row in accepted}
            pending_extensions = [
                row for row in pending_extensions
                if _as_text(row.get("code")) not in accepted_codes
            ]
        internal_extensions = available_extensions

        return cls(
            node_rows,
            load_jsonl(profiles_path),
            load_jsonl(translations_path),
            load_jsonl(profile_translations_path),
            load_jsonl(profile_text_translations_path),
            material_placements,
            procurement_registry,
            internal_extensions=internal_extensions,
            source_meta=manifest,
            source_path=nodes_path,
        )

    def _load_material_placements(self, rows: Iterable[Mapping[str, Any]]) -> None:
        """Attach display-safe runtime material candidates to GPC Bricks."""

        seen_ids: set[str] = set()
        seen_sku_fingerprints: dict[str, str] = {}
        seen_configuration_fingerprints: dict[str, str] = {}
        allowed_fields = (
            "material_id",
            "procurement_profile_id",
            "project",
            "source_reference",
            "source_rows",
            "source_dataset",
            "source_document",
            "source_sheet",
            "source_records",
            "standard_type",
            "material_name",
            "gpc_brick_code",
            "classification_source",
            "internal_category_code",
            "confidence",
            "review_status",
            "completeness_status",
            "specification_basis",
            "stock_uom",
            "purchase_package",
            "procurement_attributes",
            "price_drivers",
            "gpc_notes",
            "questions",
        )
        for raw in rows:
            if raw.get("enabled") is False:
                continue
            material_id = _as_text(raw.get("material_id"))
            brick_code = _as_text(raw.get("gpc_brick_code"))
            material_name = _as_text(raw.get("material_name"))
            standard_type = _as_text(raw.get("standard_type"))
            stock_uom = _as_text(raw.get("stock_uom"))
            completeness_status = _as_text(raw.get("completeness_status"))
            questions = [str(value).strip() for value in (raw.get("questions") or []) if str(value).strip()]
            procurement_attributes = {
                _as_text(key): _as_text(value)
                for key, value in dict(raw.get("procurement_attributes") or {}).items()
                if _as_text(key) and _as_text(value)
            }
            price_drivers = {
                _as_text(key): _as_text(value)
                for key, value in dict(raw.get("price_drivers") or {}).items()
                if _as_text(key) and _as_text(value)
            }
            gpc_notes = [str(value).strip() for value in (raw.get("gpc_notes") or []) if str(value).strip()]
            if not material_id or not material_name or not brick_code or not standard_type or not stock_uom:
                raise ValueError(
                    "GPC 实际物料缺少 material_id、material_name、gpc_brick_code、standard_type 或 stock_uom"
                )
            if completeness_status != "完整" or questions:
                raise ValueError(f"GPC 实际物料必须完整且不能保留待确认问题：{material_id}")
            if not procurement_attributes or not price_drivers or not gpc_notes:
                raise ValueError(
                    f"GPC 实际物料必须包含采购必选、价格/适配关键和 GPC 分类提示三组精简字段：{material_id}"
                )
            if len(procurement_attributes) > 4 or len(price_drivers) > 3 or len(gpc_notes) > 3:
                raise ValueError(f"GPC 实际物料属性超过施工采购精简上限：{material_id}")
            if material_id in seen_ids:
                raise ValueError(f"GPC 实际物料编号重复：{material_id}")
            node = self._nodes.get(brick_code)
            if node is None or node.get("kind") not in {"brick", *INTERNAL_LEAF_KINDS}:
                raise ValueError(f"实际物料必须挂到有效 Brick 或内部末级：{material_id} -> {brick_code}")
            if node.get("kind") in INTERNAL_LEAF_KINDS and _as_text(raw.get("classification_source")) != "nexterp_internal":
                raise ValueError(f"内部类目物料必须明确标注非 GPC 来源：{material_id}")
            placement = {field: deepcopy(raw.get(field)) for field in allowed_fields if field in raw}
            placement["material_id"] = material_id
            placement["material_name"] = material_name
            placement["gpc_brick_code"] = brick_code
            placement["classification_source"] = (
                "nexterp_internal" if node.get("kind") in INTERNAL_LEAF_KINDS else "gpc"
            )
            placement["internal_category_code"] = brick_code if node.get("kind") in INTERNAL_LEAF_KINDS else ""
            placement["standard_type"] = standard_type
            placement["review_status"] = _as_text(raw.get("review_status")) or "已完整录入"
            placement["completeness_status"] = completeness_status
            placement["specification_basis"] = _as_text(raw.get("specification_basis"))
            placement["confidence"] = _as_text(raw.get("confidence"))
            placement["stock_uom"] = stock_uom
            placement["source_rows"] = list(raw.get("source_rows") or [])
            placement["source_dataset"] = _as_text(raw.get("source_dataset"))
            placement["source_document"] = _as_text(raw.get("source_document"))
            placement["source_sheet"] = _as_text(raw.get("source_sheet"))
            placement["source_records"] = deepcopy(raw.get("source_records") or [])
            placement["procurement_attributes"] = procurement_attributes
            placement["price_drivers"] = price_drivers
            placement["gpc_notes"] = gpc_notes
            placement["questions"] = questions
            if self._procurement_registry is not None:
                placement = self._procurement_registry.enrich_material(placement)
                if placement["record_kind"] == "sku_candidate":
                    fingerprint = _as_text(placement.get("sku_identity_fingerprint"))
                    existing_id = seen_sku_fingerprints.get(fingerprint)
                    if existing_id:
                        raise ValueError(
                            f"GPC 实际物料存在重复 SKU 身份：{existing_id} / {material_id}"
                        )
                    seen_sku_fingerprints[fingerprint] = material_id
                else:
                    fingerprint = _as_text(placement.get("configuration_fingerprint"))
                    existing_id = seen_configuration_fingerprints.get(fingerprint)
                    if existing_id:
                        raise ValueError(
                            f"GPC 实际物料存在重复项目配置：{existing_id} / {material_id}"
                        )
                    seen_configuration_fingerprints[fingerprint] = material_id
            self._material_placements.append(placement)
            self._materials_by_brick[brick_code].append(placement)
            seen_ids.add(material_id)
            for ancestor in self.path(brick_code):
                self._material_counts[_as_text(ancestor.get("code"))] += 1

        self._material_placements.sort(key=lambda row: _as_text(row.get("material_id")))
        for materials in self._materials_by_brick.values():
            materials.sort(key=lambda row: _as_text(row.get("material_id")))

    def _payload(self, node: Mapping[str, Any], *, materialized_only: bool = False) -> dict[str, Any]:
        code = _as_text(node["code"])
        catalog_child_count = len(self._children.get(code, ()))
        child_count = sum(
            1
            for child_code in self._children.get(code, ())
            if not materialized_only or self._material_counts.get(child_code, 0) > 0
        )
        return {
            **node,
            "kind_label": GPC_KIND_LABELS.get(
                _as_text(node["kind"]),
                INTERNAL_KIND_LABELS.get(_as_text(node["kind"]), _as_text(node["kind"])),
            ),
            "kind_label_zh": GPC_KIND_LABELS_ZH.get(
                _as_text(node["kind"]),
                INTERNAL_KIND_LABELS_ZH.get(_as_text(node["kind"]), _as_text(node["kind"])),
            ),
            "is_gpc": node.get("is_gpc", True),
            "classification_source": "gpc" if node.get("is_gpc", True) else "nexterp_internal",
            "child_count": child_count,
            "catalog_child_count": catalog_child_count,
            "has_children": child_count > 0,
            "direct_material_count": len(self._materials_by_brick.get(code, ())),
            "actual_material_count": self._material_counts.get(code, 0),
            "has_actual_materials": self._material_counts.get(code, 0) > 0,
            "internal_child_count": sum(
                self._nodes[child_code].get("kind") in INTERNAL_KINDS
                for child_code in self._children.get(code, ())
            ),
        }

    def _profile_term_translation(self, code: str, official_name: str) -> tuple[str, str]:
        translation = self._profile_translations.get(code, {})
        valid = _as_text(translation.get("source_hash")) == _source_hash(official_name)
        working_name = _as_text(translation.get("working_name")) if valid else ""
        status = _as_text(translation.get("status")) if working_name else "missing"
        return working_name or official_name, status

    def _profile_text_translation(self, official_text: str) -> tuple[str, str]:
        if not official_text:
            return "", "empty"
        translation = self._profile_text_translations.get(_source_hash(official_text), {})
        valid = (
            _as_text(translation.get("source_hash")) == _source_hash(official_text)
            and _as_text(translation.get("official_text")) == official_text
        )
        working_text = _as_text(translation.get("working_text")) if valid else ""
        status = _as_text(translation.get("status")) if working_text else "missing"
        return working_text or official_text, status

    def _build_profile_terms(self) -> None:
        """Build one searchable term with reverse Brick references per GPC code."""

        seen_references: set[tuple[str, str, str]] = set()

        def register(
            *,
            code: str,
            kind: str,
            official_name: str,
            definition: str,
            reference: dict[str, Any],
        ) -> None:
            if not code or not official_name:
                return
            working_name, status = self._profile_term_translation(code, official_name)
            term = self._profile_terms.get(code)
            if term is None:
                term = {
                    "code": code,
                    "kind": kind,
                    "official_name": official_name,
                    "working_name": working_name,
                    "translation_status": status,
                    "definition": definition,
                    "references": [],
                }
                self._profile_terms[code] = term
            elif term["kind"] != kind or term["official_name"] != official_name:
                raise ValueError(f"GPC 属性术语编码冲突：{code}")
            reference_key = (code, _as_text(reference.get("brick_code")), _as_text(reference.get("attribute_code")))
            if reference_key not in seen_references:
                term["references"].append(reference)
                seen_references.add(reference_key)

        for brick_code in sorted(self._profiles):
            node = self._nodes.get(brick_code)
            if node is None or node.get("kind") not in {"brick", *INTERNAL_LEAF_KINDS}:
                continue
            profile = self._profiles[brick_code]
            for attribute in profile.get("attributes") or []:
                attribute_code = _as_text(attribute.get("code"))
                attribute_official = _as_text(attribute.get("name"))
                attribute_working, _status = self._profile_term_translation(attribute_code, attribute_official)
                reference = {
                    "brick_code": brick_code,
                    "brick_official_name": node["official_name"],
                    "brick_working_name": node["working_name"],
                    "attribute_code": attribute_code,
                    "attribute_official_name": attribute_official,
                    "attribute_working_name": attribute_working,
                }
                register(
                    code=attribute_code,
                    kind="attribute",
                    official_name=attribute_official,
                    definition=_as_text(attribute.get("definition")),
                    reference=reference,
                )
                for value in attribute.get("values") or []:
                    register(
                        code=_as_text(value.get("code")),
                        kind="attribute_value",
                        official_name=_as_text(value.get("name")),
                        definition=_as_text(value.get("definition")),
                        reference=reference,
                    )

        for term in self._profile_terms.values():
            term["references"].sort(key=lambda row: (row["brick_code"], row["attribute_code"]))

    def _profile_term_payload(self, term: Mapping[str, Any]) -> dict[str, Any]:
        references = list(term.get("references") or [])
        preview = []
        for reference in references[:PROFILE_TERM_REFERENCE_LIMIT]:
            row = dict(reference)
            row["path"] = self.path(_as_text(reference.get("brick_code")))
            preview.append(row)
        kind = _as_text(term.get("kind"))
        return {
            "result_type": "profile_term",
            "code": _as_text(term.get("code")),
            "kind": kind,
            "kind_label": "Attribute" if kind == "attribute" else "Attribute Value",
            "kind_label_zh": "属性" if kind == "attribute" else "属性值",
            "official_name": _as_text(term.get("official_name")),
            "working_name": _as_text(term.get("working_name")),
            "translation_status": _as_text(term.get("translation_status")),
            "definition": _as_text(term.get("definition")),
            "usage_count": len(references),
            "brick_count": len({_as_text(row.get("brick_code")) for row in references}),
            "references": preview,
            "references_truncated": len(references) > len(preview),
        }

    def contains(self, code: str, *, kind: str | None = None) -> bool:
        """Return whether the fixed imported reference contains this code."""

        node = self._nodes.get(_as_text(code))
        return bool(node and (kind is None or node.get("kind") == kind))

    def codes(self, *, kind: str | None = None) -> list[str]:
        """Return stable codes for validation boundaries, optionally by kind."""

        return sorted(
            code for code, node in self._nodes.items()
            if kind is None or node.get("kind") == kind
        )

    def material_catalog(
        self,
        *,
        query: str = "",
        segment_code: str = "",
        category_code: str = "",
        standard_type: str = "",
        stock_uom: str = "",
        sort: str = "name",
        offset: int = 0,
        limit: int = 24,
        allowed_material_ids: set[str] | None = None,
        group_standard_type_codes: set[str] | None = None,
        group_all_multi_sku_types: bool = False,
    ) -> dict[str, Any]:
        """Return the approved material projection used by the request shop.

        The GPC hierarchy remains reference data.  These rows are the compact,
        fully reviewed procurement records already attached to that hierarchy;
        no ERPNext stock or price is invented here.
        """

        normalized_query = _as_text(query).casefold()
        normalized_segment = _as_text(segment_code)
        normalized_category = _as_text(category_code)
        normalized_type = _as_text(standard_type)
        normalized_uom = _as_text(stock_uom)
        bounded_offset = max(0, int(offset))
        bounded_limit = min(100, max(1, int(limit)))

        rows: list[dict[str, Any]] = []
        for material in self._material_placements:
            row = deepcopy(material)
            if allowed_material_ids is not None and _as_text(row.get("material_id")) not in allowed_material_ids:
                continue
            path = self.path(_as_text(row.get("gpc_brick_code")))
            if not path:
                continue
            segment = path[0]
            row["segment_code"] = _as_text(segment.get("code"))
            row["segment_name"] = _as_text(segment.get("working_name") or segment.get("official_name"))
            row["classification_path"] = [
                {
                    "code": _as_text(node.get("code")),
                    "name": _as_text(node.get("working_name") or node.get("official_name")),
                    "kind": _as_text(node.get("kind")),
                }
                for node in path
            ]
            haystack = " ".join(
                [
                    _as_text(row.get("material_id")),
                    _as_text(row.get("material_name")),
                    _as_text(row.get("standard_type")),
                    _as_text(row.get("segment_name")),
                    *[_as_text(value) for value in dict(row.get("procurement_attributes") or {}).values()],
                    *[_as_text(value) for value in dict(row.get("price_drivers") or {}).values()],
                ]
            ).casefold()
            if normalized_query and normalized_query not in haystack:
                continue
            rows.append(row)

        category_tree: list[dict[str, Any]] = []
        category_lookup: dict[str, dict[str, Any]] = {}
        for row in rows:
            parent_children = category_tree
            for node in row.get("classification_path") or []:
                code = _as_text(node.get("code"))
                if not code:
                    continue
                current = category_lookup.get(code)
                if current is None:
                    current = {
                        "code": code,
                        "name": _as_text(node.get("name")),
                        "kind": _as_text(node.get("kind")),
                        "count": 0,
                        "children": [],
                    }
                    category_lookup[code] = current
                    parent_children.append(current)
                current["count"] += 1
                parent_children = current["children"]

        if normalized_category:
            rows = [
                row for row in rows
                if any(_as_text(node.get("code")) == normalized_category for node in row.get("classification_path") or [])
            ]

        segment_facets = Counter((row["segment_code"], row["segment_name"]) for row in rows)
        if normalized_segment:
            rows = [row for row in rows if row["segment_code"] == normalized_segment]
        type_facets = Counter(_as_text(row.get("standard_type")) for row in rows)
        if normalized_type:
            rows = [row for row in rows if _as_text(row.get("standard_type")) == normalized_type]
        uom_facets = Counter(_as_text(row.get("stock_uom")) for row in rows)
        if normalized_uom:
            rows = [row for row in rows if _as_text(row.get("stock_uom")) == normalized_uom]

        sku_total = len(rows)
        grouped_codes = {
            _as_text(code) for code in (group_standard_type_codes or set()) if _as_text(code)
        }
        if group_all_multi_sku_types:
            type_counts = Counter(_as_text(row.get("gpc_brick_code")) for row in rows)
            grouped_codes.update(code for code, count in type_counts.items() if code and count >= 2)
        if grouped_codes:
            grouped_rows: list[dict[str, Any]] = []
            groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
            first_positions: dict[str, int] = {}
            for position, row in enumerate(rows):
                type_code = _as_text(row.get("gpc_brick_code"))
                if type_code in grouped_codes:
                    groups[type_code].append(row)
                    first_positions.setdefault(type_code, position)
                else:
                    grouped_rows.append(row)
            for type_code, variants in groups.items():
                representative = deepcopy(variants[0])
                value_sets: dict[str, set[str]] = defaultdict(set)
                variant_stock_uoms = sorted({
                    _as_text(variant.get("stock_uom"))
                    for variant in variants
                    if _as_text(variant.get("stock_uom"))
                })
                for variant in variants:
                    for field in ("procurement_attributes", "price_drivers"):
                        for key, value in dict(variant.get(field) or {}).items():
                            if _as_text(key) and _as_text(value):
                                value_sets[_as_text(key)].add(_as_text(value))
                ordered_attributes = sorted(
                    value_sets.items(),
                    key=lambda item: (len(item[1]) == 1, len(item[1]), item[0]),
                )
                representative.update(
                    {
                        "material_id": f"TYPE-{type_code}",
                        "item_code": type_code,
                        "material_name": _as_text(representative.get("standard_type")),
                        "record_kind": "standard_type_group",
                        "variant_type_code": type_code,
                        "variant_count": len(variants),
                        "variant_stock_uoms": variant_stock_uoms,
                        "stock_uom": variant_stock_uoms[0] if len(variant_stock_uoms) == 1 else "",
                        "first_position": first_positions[type_code],
                        "variant_attributes": {
                            key: next(iter(values)) if len(values) == 1 else f"{len(values)} 种可选"
                            for key, values in ordered_attributes
                        },
                    }
                )
                grouped_rows.append(representative)
            rows = grouped_rows

        if sort == "type":
            rows.sort(key=lambda row: (_as_text(row.get("standard_type")), _as_text(row.get("material_name")), _as_text(row.get("material_id"))))
        elif sort == "code":
            rows.sort(key=lambda row: _as_text(row.get("material_id")))
        else:
            rows.sort(key=lambda row: (_as_text(row.get("material_name")), _as_text(row.get("material_id"))))

        total = len(rows)
        return {
            "rows": rows[bounded_offset : bounded_offset + bounded_limit],
            "total": total,
            "sku_total": sku_total,
            "grouped_type_count": len(groups) if grouped_codes else 0,
            "offset": bounded_offset,
            "limit": bounded_limit,
            "segments": [
                {"code": code, "name": name, "count": count}
                for (code, name), count in sorted(segment_facets.items(), key=lambda item: (-item[1], item[0][1]))
            ],
            "category_tree": category_tree,
            "standard_types": [
                {"name": name, "count": count}
                for name, count in sorted(type_facets.items(), key=lambda item: (-item[1], item[0]))
                if name
            ],
            "stock_uoms": [
                {"name": name, "count": count}
                for name, count in sorted(uom_facets.items(), key=lambda item: (-item[1], item[0]))
                if name
            ],
        }

    def summary(self) -> dict[str, Any]:
        counts = Counter(node["kind"] for node in self._nodes.values())
        official_node_count = sum(node.get("is_gpc", True) for node in self._nodes.values())
        levels = [
            {
                "kind": kind,
                "label": GPC_KIND_LABELS[kind],
                "label_zh": GPC_KIND_LABELS_ZH[kind],
                "level": level,
                "count": counts.get(kind, 0),
            }
            for kind, level in sorted(GPC_KIND_ORDER.items(), key=lambda item: item[1])
        ]
        levels[3]["count"] += counts.get(INTERNAL_BRICK_KIND, 0)
        levels.append({
            "kind": INTERNAL_FAMILY_KIND,
            "label": INTERNAL_KIND_LABELS[INTERNAL_FAMILY_KIND],
            "label_zh": INTERNAL_KIND_LABELS_ZH[INTERNAL_FAMILY_KIND],
            "level": 4,
            "count": counts.get(INTERNAL_FAMILY_KIND, 0),
        })
        levels.append({
            "kind": INTERNAL_TYPE_KIND,
            "label": INTERNAL_KIND_LABELS[INTERNAL_TYPE_KIND],
            "label_zh": INTERNAL_KIND_LABELS_ZH[INTERNAL_TYPE_KIND],
            "level": 5,
            "count": counts.get(INTERNAL_TYPE_KIND, 0),
        })
        return {
            "catalog": "gpc",
            "available": True,
            "source": "GS1 GPC",
            "source_url": _as_text(self.source_meta.get("source_url")),
            "source_version": _as_text(self.source_meta.get("version") or "2026-05"),
            "generated_at": _as_text(self.source_meta.get("generated_at")),
            "total_nodes": official_node_count,
            "browsable_total_nodes": len(self._nodes),
            "internal_extension_count": sum(counts.get(kind, 0) for kind in INTERNAL_KINDS),
            "internal_counts": {kind: counts.get(kind, 0) for kind in INTERNAL_KINDS},
            "counts": {kind: counts.get(kind, 0) for kind in GPC_KIND_ORDER},
            "kind_labels": GPC_KIND_LABELS,
            "kind_labels_zh": GPC_KIND_LABELS_ZH,
            "levels": levels,
            "root_count": len(self._children.get(None, ())),
            "hierarchy_complete": bool(self.source_meta.get("hierarchy_complete", not self.validate())),
            "parent_missing_count": int(self.source_meta.get("parent_missing_count", 0) or 0),
            "duplicate_code_count": int(self.source_meta.get("duplicate_code_count", 0) or 0),
            "orphan_brick_count": int(self.source_meta.get("orphan_brick_count", 0) or 0),
            "attribute_count": int(self.source_meta.get("attribute_count", 0) or 0),
            "attribute_value_count": int(self.source_meta.get("attribute_value_count", 0) or 0),
            "actual_material_count": len(self._material_placements),
            "procurement_templates": (
                self._procurement_registry.summary()
                if self._procurement_registry is not None
                else {"main_template_count": 0, "constraint_count": 0, "type_profile_count": 0}
            ),
            "material_record_counts": dict(Counter(
                _as_text(item.get("record_kind")) or "unprofiled"
                for item in self._material_placements
            )),
            "materialized_brick_count": len(self._materials_by_brick),
            "materialized_node_count": sum(1 for code in self._nodes if self._material_counts.get(code, 0) > 0),
            "materialized_internal_extension_count": sum(
                1
                for code, node in self._nodes.items()
                if node["kind"] in INTERNAL_KINDS and self._material_counts.get(code, 0) > 0
            ),
            "materialized_counts": {
                kind: sum(
                    1
                    for code, node in self._nodes.items()
                    if node["kind"] == kind and self._material_counts.get(code, 0) > 0
                )
                for kind in (*GPC_KIND_ORDER, INTERNAL_BRICK_KIND, INTERNAL_FAMILY_KIND, INTERNAL_TYPE_KIND)
            },
            "translation": self.source_meta.get("translation") or {},
            "profile_translation": self.source_meta.get("profile_translation") or {},
            "profile_text_translation": self.source_meta.get("profile_text_translation") or {},
        }

    def children(self, parent_code: str | None = None, *, materialized_only: bool = False) -> list[dict[str, Any]]:
        normalized = _as_text(parent_code) or None
        if normalized is not None and normalized not in self._nodes:
            raise ValueError(f"GPC 节点不存在：{normalized}")
        rows = []
        for code in self._children.get(normalized, ()):
            if materialized_only and self._material_counts.get(code, 0) <= 0:
                continue
            payload = self._payload(self._nodes[code], materialized_only=materialized_only)
            payload["full_path"] = self.path(code)
            rows.append(payload)
        return rows

    def path(self, code: str) -> list[dict[str, Any]]:
        normalized = _as_text(code)
        if normalized not in self._nodes:
            raise ValueError(f"GPC 节点不存在：{normalized}")
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        current: dict[str, Any] | None = self._nodes[normalized]
        while current is not None:
            current_code = _as_text(current["code"])
            if current_code in seen:
                raise ValueError(f"GPC 存在循环引用：{current_code}")
            seen.add(current_code)
            chain.append(self._payload(current))
            parent = _as_text(current.get("parent_code"))
            current = self._nodes.get(parent) if parent else None
        chain.reverse()
        return chain

    def search(
        self,
        query: str,
        *,
        kind: str = "",
        limit: int = 100,
        materialized_only: bool = False,
    ) -> dict[str, Any]:
        needle = _as_text(query).casefold()
        if not needle:
            return {"rows": [], "total": 0, "truncated": False}
        normalized_kind = _as_text(kind)
        if normalized_kind and normalized_kind not in _NODE_KIND_ORDER:
            raise ValueError(f"未知 GPC 层级：{normalized_kind}")
        compact = _SPACE_RE.sub("", needle)
        matches: list[tuple[tuple[int, int, int, str], str, dict[str, Any]]] = []
        for node in self._nodes.values():
            if materialized_only and self._material_counts.get(_as_text(node.get("code")), 0) <= 0:
                continue
            if normalized_kind and node["kind"] != normalized_kind and not (
                normalized_kind == "brick" and node["kind"] == INTERNAL_BRICK_KIND
            ):
                continue
            profile = self._profiles.get(node["code"], {})
            profile_texts = [
                _as_text(profile.get(field))
                for field in (
                    "definition", "includes", "excludes",
                    "definition_working", "includes_working", "excludes_working",
                )
            ]
            attrs = " ".join(
                [
                    *profile_texts,
                    *(self._profile_text_translation(text)[0] for text in profile_texts if text),
                ]
            )
            material_text = " ".join(
                " ".join(
                    (
                        _as_text(material.get("material_id")),
                        _as_text(material.get("standard_type")),
                        _as_text(material.get("material_name")),
                        " ".join(
                            f"{key} {_as_text(value)}"
                            for field in ("procurement_attributes", "price_drivers")
                            for key, value in (material.get(field) or {}).items()
                        ),
                        " ".join(material.get("gpc_notes") or ()),
                    )
                )
                for material in self._materials_by_brick.get(_as_text(node.get("code")), ())
            )
            haystack = " ".join(
                (
                    _as_text(node["code"]),
                    _as_text(node["official_name"]),
                    _as_text(node["working_name"]),
                    attrs,
                    material_text,
                )
            ).casefold()
            compact_haystack = _SPACE_RE.sub("", haystack)
            if needle not in haystack and compact not in compact_haystack:
                continue
            code = _as_text(node["code"])
            if code.casefold() == needle:
                rank = 0
            elif code.casefold().startswith(needle):
                rank = 1
            elif _as_text(node["working_name"]).casefold().startswith(needle):
                rank = 2
            else:
                rank = 3
            matches.append(((rank, 0, _NODE_KIND_ORDER[node["kind"]], code), "node", node))

        if not normalized_kind and not materialized_only:
            for term in self._profile_terms.values():
                code = _as_text(term.get("code"))
                official_name = _as_text(term.get("official_name"))
                working_name = _as_text(term.get("working_name"))
                haystack = " ".join((code, official_name, working_name, _as_text(term.get("definition")))).casefold()
                compact_haystack = _SPACE_RE.sub("", haystack)
                if needle not in haystack and compact not in compact_haystack:
                    continue
                if code.casefold() == needle or working_name.casefold() == needle or official_name.casefold() == needle:
                    rank = 0
                elif code.casefold().startswith(needle):
                    rank = 1
                elif working_name.casefold().startswith(needle) or official_name.casefold().startswith(needle):
                    rank = 2
                else:
                    rank = 3
                term_order = 0 if term.get("kind") == "attribute" else 1
                matches.append(((rank, 1, term_order, code), "profile_term", term))

        matches.sort(key=lambda item: item[0])
        bounded = min(200, max(1, int(limit)))
        rows: list[dict[str, Any]] = []
        for _rank, result_type, row in matches[:bounded]:
            if result_type == "profile_term":
                rows.append(self._profile_term_payload(row))
                continue
            payload = self._payload(row, materialized_only=materialized_only)
            payload["result_type"] = "node"
            payload["path"] = self.path(_as_text(row["code"]))
            payload["full_path"] = payload["path"]
            rows.append(payload)
        return {"rows": rows, "total": len(matches), "truncated": len(matches) > bounded}

    def candidate_bricks(self, queries: Iterable[str], *, limit: int = 8) -> list[dict[str, Any]]:
        """Return real Brick candidates for a constrained classifier.

        This is deliberately lexical rather than generative: a model may rank
        the returned codes, but it cannot introduce a code that is absent from
        the imported GS1 package.  Multiple normalized queries let an upstream
        fact extractor bridge construction-site jargon without changing GPC.
        """

        clean_queries = []
        for value in queries:
            clean = _as_text(value)
            if clean and clean not in clean_queries:
                clean_queries.append(clean)
        if not clean_queries:
            return []

        documents = getattr(self, "_brick_candidate_documents", None)
        if documents is None:
            documents = []
            for code, node in self._nodes.items():
                if node.get("kind") != "brick":
                    continue
                profile = self._profiles.get(code, {})
                profile_texts = [_as_text(profile.get(field)) for field in ("definition", "includes", "excludes")]
                working_profile_texts = [self._profile_text_translation(text)[0] if text else "" for text in profile_texts]
                names = (_as_text(node.get("working_name")), _as_text(node.get("official_name")))
                name_text = " ".join(names)
                document = " ".join((*names, *profile_texts, *working_profile_texts))
                documents.append((
                    code, node, profile_texts, working_profile_texts,
                    tuple(_retrieval_text(name) for name in names),
                    _retrieval_text(name_text), _retrieval_text(document), _character_bigrams(name_text),
                ))
            self._brick_candidate_documents = documents
            self._brick_vector_index: TextVectorIndex | None = None
            if self.vector_mode == "shadow":
                self._brick_vector_index = TextVectorIndex()
                self._brick_vector_index.build(
                    (document[0], document[6]) for document in documents
                )

        vector_scores_by_code: dict[str, float] = {}
        if self.vector_mode == "shadow" and self._brick_vector_index is not None:
            for query in clean_queries:
                for match in self._brick_vector_index.query(
                    query,
                    limit=max(1, len(documents)),
                    min_score=-1.0,
                ):
                    vector_scores_by_code[match.document_id] = max(
                        vector_scores_by_code.get(match.document_id, 0.0), match.score
                    )

        ranked: list[tuple[float, str, dict[str, Any]]] = []
        for code, node, profile_texts, working_profile_texts, compact_names, compact_name, compact_document, name_bigrams in documents:
            best = 0.0
            vector_best = vector_scores_by_code.get(code, 0.0)
            for query in clean_queries:
                compact_query = _retrieval_text(query)
                if not compact_query:
                    continue
                score = 0.0
                if compact_query in compact_names:
                    score = 1.0
                elif compact_query in compact_name:
                    score = 0.88 + min(0.08, len(compact_query) / 100)
                elif compact_query in compact_document:
                    score = 0.72 + min(0.08, len(compact_query) / 100)
                else:
                    query_bigrams = _character_bigrams(query)
                    if query_bigrams and name_bigrams:
                        overlap = len(query_bigrams & name_bigrams)
                        score = (2 * overlap) / (len(query_bigrams) + len(name_bigrams))
                best = max(best, score)
            # The lexical score remains the only candidate-generation signal
            # in the current shadow round.  We still compute and expose the
            # vector score for candidates that the explainable lane already
            # found, but a vector-only hit must not change the GPC candidate
            # set or its ordering before labelled evaluation is complete.
            if best < 0.18:
                continue
            payload = self._payload(node)
            payload.update({
                "score": round(best, 4),
                "definition": profile_texts[0],
                "definition_working": working_profile_texts[0] if working_profile_texts else profile_texts[0],
                "includes": profile_texts[1],
                "includes_working": working_profile_texts[1] if len(working_profile_texts) > 1 else profile_texts[1],
                "excludes": profile_texts[2],
                "excludes_working": working_profile_texts[2] if len(working_profile_texts) > 2 else profile_texts[2],
                "full_path": self.path(code),
                "vector_score": round(vector_best, 6),
                "retrieval_sources": [
                    "lexical_rules",
                    *(["local_char_ngram_vector"] if self.vector_mode == "shadow" and vector_best >= 0.42 else []),
                ],
                # This flag means that the already-lexical candidate also
                # received a material vector signal. Vector-only candidates
                # remain deliberately absent from production results.
                "vector_shadow_hit": bool(self.vector_mode == "shadow" and vector_best >= 0.42),
            })
            ranked.append((-best, code, payload))
        ranked.sort(key=lambda item: (item[0], item[1]))
        return [payload for _score, _code, payload in ranked[:max(1, min(20, int(limit)))]]

    def candidate_brick(self, code: str) -> dict[str, Any] | None:
        """Return one pinned official Brick or declared Nexterp internal leaf.

        Lexical candidate generation remains restricted to official GPC
        Bricks.  Internal leaves can only enter through deterministic rules or
        explicit post-freeze curation.
        """

        normalized = _as_text(code)
        node = self._nodes.get(normalized)
        if node is None or node.get("kind") not in {"brick", *INTERNAL_LEAF_KINDS}:
            return None
        profile = self._profiles.get(normalized, {})
        if node.get("kind") in INTERNAL_LEAF_KINDS:
            payload = self._payload(node)
            payload.update({
                "score": 1.0,
                "definition": "",
                "definition_working": _as_text(profile.get("definition_working")),
                "includes": "",
                "includes_working": _as_text(profile.get("includes_working")),
                "excludes": "",
                "excludes_working": _as_text(profile.get("excludes_working")),
                "full_path": self.path(normalized),
                "rule_pinned": True,
            })
            return payload
        profile_texts = [_as_text(profile.get(field)) for field in ("definition", "includes", "excludes")]
        working_profile_texts = [self._profile_text_translation(text)[0] if text else "" for text in profile_texts]
        payload = self._payload(node)
        payload.update({
            "score": 1.0,
            "definition": profile_texts[0],
            "definition_working": working_profile_texts[0] if working_profile_texts else profile_texts[0],
            "includes": profile_texts[1],
            "includes_working": working_profile_texts[1] if len(working_profile_texts) > 1 else profile_texts[1],
            "excludes": profile_texts[2],
            "excludes_working": working_profile_texts[2] if len(working_profile_texts) > 2 else profile_texts[2],
            "full_path": self.path(normalized),
            "rule_pinned": True,
        })
        return payload

    def profile(self, code: str) -> dict[str, Any]:
        normalized = _as_text(code)
        node = self._nodes.get(normalized)
        if node is None:
            raise ValueError(f"GPC 节点不存在：{normalized}")
        profile = deepcopy(self._profiles.get(normalized, {"code": normalized, "attributes": []}))
        if node.get("kind") in INTERNAL_KINDS:
            profile.setdefault("code", normalized)
            profile.setdefault("kind", node["kind"])
            profile["official_name"] = ""
            profile.setdefault("working_name", node["working_name"])
            profile["is_gpc"] = False
            profile["classification_source"] = "nexterp_internal"
            for field in ("definition", "includes", "excludes"):
                profile[f"{field}_official"] = ""
                profile.setdefault(f"{field}_working", "")
                profile[f"{field}_translation_status"] = "human_confirmed"
            for attribute in profile.get("attributes") or []:
                working_name = _as_text(attribute.get("working_name") or attribute.get("name"))
                attribute["official_name"] = ""
                attribute["working_name"] = working_name
                attribute["translation_status"] = "human_confirmed"
                for value in attribute.get("values") or []:
                    value["official_name"] = ""
                    value["working_name"] = _as_text(value.get("working_name") or value.get("name"))
                    value["translation_status"] = "human_confirmed"
            profile["path"] = self.path(normalized)
            profile["actual_materials"] = deepcopy(self._materials_by_brick.get(normalized, ()))
            profile["direct_material_count"] = len(profile["actual_materials"])
            profile["actual_material_count"] = self._material_counts.get(normalized, 0)
            return profile
        for field in ("definition", "includes", "excludes"):
            official_text = _as_text(profile.get(field))
            working_text, status = self._profile_text_translation(official_text)
            profile[f"{field}_official"] = official_text
            profile[f"{field}_working"] = working_text
            profile[f"{field}_translation_status"] = status
        for attribute in profile.get("attributes") or []:
            official_name = _as_text(attribute.get("name"))
            working_name, status = self._profile_term_translation(_as_text(attribute.get("code")), official_name)
            attribute["official_name"] = official_name
            attribute["working_name"] = working_name
            attribute["translation_status"] = status
            for value in attribute.get("values") or []:
                value_official = _as_text(value.get("name"))
                value_working, value_status = self._profile_term_translation(_as_text(value.get("code")), value_official)
                value["official_name"] = value_official
                value["working_name"] = value_working
                value["translation_status"] = value_status
        profile.setdefault("code", normalized)
        profile.setdefault("kind", node["kind"])
        profile.setdefault("official_name", node["official_name"])
        profile.setdefault("working_name", node["working_name"])
        profile["path"] = self.path(normalized)
        profile["actual_materials"] = deepcopy(self._materials_by_brick.get(normalized, ()))
        profile["direct_material_count"] = len(profile["actual_materials"])
        profile["actual_material_count"] = self._material_counts.get(normalized, 0)
        return profile

    def validate(self) -> list[str]:
        issues: list[str] = []
        # Check ancestry first so a malformed cyclic package is reported as a
        # cycle rather than being obscured by a secondary level mismatch.
        for code in self._nodes:
            try:
                self.path(code)
            except ValueError as exc:
                issues.append(str(exc))
                break
        if any(self._nodes[code]["kind"] != "segment" for code in self._children.get(None, ())):
            issues.append("根节点必须全部为 Segment")
        for node in self._nodes.values():
            if node["kind"] in INTERNAL_KINDS:
                parent = self._nodes.get(_as_text(node.get("parent_code")))
                if parent is None:
                    issues.append(f"内部扩展父级缺失：{node['code']}")
                    continue
                if int(node["level"]) != int(parent.get("level", -1)) + 1:
                    issues.append(f"内部扩展层级不匹配：{node['code']}")
                if node["kind"] == INTERNAL_BRICK_KIND:
                    if parent.get("kind") != "class" or not parent.get("is_gpc", True):
                        issues.append(f"内部砖块父级无效：{node['code']}")
                elif node["kind"] == INTERNAL_FAMILY_KIND:
                    if parent.get("kind") not in {"brick", INTERNAL_BRICK_KIND}:
                        issues.append(f"内部物料族父级无效：{node['code']}")
                elif parent.get("kind") != INTERNAL_FAMILY_KIND:
                    issues.append(f"内部标准类型父级无效：{node['code']}")
                continue
            expected = GPC_KIND_ORDER[node["kind"]]
            if int(node["level"]) != expected:
                issues.append(f"层级不匹配：{node['code']}")
            parent_code = node.get("parent_code")
            if parent_code:
                parent = self._nodes.get(_as_text(parent_code))
                if parent is None:
                    issues.append(f"父级缺失：{node['code']}")
                elif GPC_KIND_ORDER[parent["kind"]] != expected - 1:
                    issues.append(f"父级跨层：{node['code']} -> {parent_code}")
        return issues


__all__ = [
    "GPC_KIND_LABELS",
    "GPC_KIND_LABELS_ZH",
    "GPC_KIND_ORDER",
    "INTERNAL_BRICK_KIND",
    "INTERNAL_FAMILY_KIND",
    "INTERNAL_KIND",
    "INTERNAL_KINDS",
    "INTERNAL_LEAF_KINDS",
    "INTERNAL_TYPE_KIND",
    "GpcReferenceIndex",
]
