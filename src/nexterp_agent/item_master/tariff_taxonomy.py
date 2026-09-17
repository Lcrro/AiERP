"""Read-only index for browsing the complete extracted tariff hierarchy."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


KIND_ORDER = {
    "section": 0,
    "chapter": 1,
    "heading": 2,
    "subheading": 3,
    "sku": 4,
}
KIND_LABELS = {
    "section": "类",
    "chapter": "章",
    "heading": "四位品目",
    "subheading": "六位子目",
    "sku": "八位税号",
}
_SPACE_RE = re.compile(r"\s+")


def _node_value(node: Mapping[str, Any], key: str, default: Any = "") -> Any:
    return node.get(key, default)


def resolve_tariff_taxonomy_source(
    review_summary_path: Path,
    runtime_root: Path,
) -> Path:
    """Resolve the reviewed hierarchy source without accepting arbitrary paths."""

    root = Path(runtime_root).resolve()
    summary_path = Path(review_summary_path)
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        configured = str(summary.get("source_path") or "").strip()
        if configured:
            candidate = Path(configured).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                candidate = Path()
            if candidate.is_file():
                return candidate

    candidates: list[tuple[int, Path]] = []
    for manifest_path in root.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        nodes_path = manifest_path.with_name("tariff-nodes.jsonl")
        if manifest.get("hierarchy_complete") is True and nodes_path.is_file():
            candidates.append((manifest_path.stat().st_mtime_ns, nodes_path))
    if not candidates:
        raise FileNotFoundError("尚未找到已校验的完整税则层级文件")
    return max(candidates, key=lambda item: item[0])[1]


class TariffTaxonomyIndex:
    """In-memory parent/child and search index for the 15,929-node tree."""

    def __init__(
        self,
        nodes: Iterable[Mapping[str, Any]],
        *,
        source_path: Path | None = None,
        source_meta: Mapping[str, Any] | None = None,
    ) -> None:
        self.source_path = Path(source_path).resolve() if source_path else None
        self.source_meta = dict(source_meta or {})
        self._nodes: dict[str, dict[str, Any]] = {}
        self._children: dict[str | None, list[str]] = defaultdict(list)
        for raw in nodes:
            code = str(_node_value(raw, "code")).strip()
            if not code:
                continue
            if code in self._nodes:
                raise ValueError(f"税则层级存在重复编码：{code}")
            kind = str(_node_value(raw, "kind")).strip()
            if kind not in KIND_ORDER:
                raise ValueError(f"税则层级类型无效：{code} ({kind})")
            raw_parent_code = _node_value(raw, "parent_code", None)
            parent_code = str(raw_parent_code).strip() if raw_parent_code is not None else None
            parent_code = parent_code or None
            node = {
                "code": code,
                "name": str(_node_value(raw, "name")).strip(),
                "kind": kind,
                "level": int(_node_value(raw, "level", KIND_ORDER[kind])),
                "parent_code": parent_code,
                "page": int(_node_value(raw, "page", 0) or 0),
            }
            self._nodes[code] = node
            self._children[parent_code].append(code)

        for child_codes in self._children.values():
            child_codes.sort(key=lambda code: (KIND_ORDER[self._nodes[code]["kind"]], code))

        missing_parents = [
            node["code"]
            for node in self._nodes.values()
            if node["parent_code"] and node["parent_code"] not in self._nodes
        ]
        if missing_parents:
            raise ValueError(f"税则层级存在缺失父级：{missing_parents[0]}")

    @classmethod
    def from_jsonl(cls, path: Path) -> "TariffTaxonomyIndex":
        source_path = Path(path).resolve()
        with source_path.open("r", encoding="utf-8") as handle:
            nodes = [json.loads(line) for line in handle if line.strip()]
        manifest_path = source_path.with_name("manifest.json")
        source_meta: dict[str, Any] = {}
        if manifest_path.is_file():
            source_meta = json.loads(manifest_path.read_text(encoding="utf-8"))
        return cls(nodes, source_path=source_path, source_meta=source_meta)

    def _payload(self, node: Mapping[str, Any]) -> dict[str, Any]:
        code = str(node["code"])
        child_count = len(self._children.get(code, ()))
        return {
            **node,
            "kind_label": KIND_LABELS[str(node["kind"])],
            "child_count": child_count,
            "has_children": child_count > 0,
        }

    def summary(self) -> dict[str, Any]:
        counts = Counter(node["kind"] for node in self._nodes.values())
        return {
            "total_nodes": len(self._nodes),
            "counts": {kind: counts.get(kind, 0) for kind in KIND_ORDER},
            "kind_labels": KIND_LABELS,
            "root_count": len(self._children.get(None, ())),
            "hierarchy_complete": bool(self.source_meta.get("hierarchy_complete", not self.validate())),
            "parent_missing_count": int(self.source_meta.get("parent_missing_count", 0) or 0),
            "source_version": str(self.source_meta.get("source_version") or "中华人民共和国进出口税则（2026）"),
            "generated_at": str(self.source_meta.get("generated_at") or ""),
        }

    def children(self, parent_code: str | None = None) -> list[dict[str, Any]]:
        normalized_parent = str(parent_code or "").strip() or None
        if normalized_parent is not None and normalized_parent not in self._nodes:
            raise ValueError(f"税则节点不存在：{normalized_parent}")
        return [self._payload(self._nodes[code]) for code in self._children.get(normalized_parent, ())]

    def path(self, code: str) -> list[dict[str, Any]]:
        normalized_code = str(code or "").strip()
        node = self._nodes.get(normalized_code)
        if node is None:
            raise ValueError(f"税则节点不存在：{normalized_code}")
        chain: list[dict[str, Any]] = []
        seen: set[str] = set()
        while node is not None:
            node_code = str(node["code"])
            if node_code in seen:
                raise ValueError(f"税则层级存在循环引用：{node_code}")
            seen.add(node_code)
            chain.append(self._payload(node))
            parent_code = node["parent_code"]
            node = self._nodes.get(str(parent_code)) if parent_code else None
        chain.reverse()
        return chain

    def search(self, query: str, *, kind: str = "", limit: int = 100) -> dict[str, Any]:
        needle = str(query or "").strip().casefold()
        if not needle:
            return {"rows": [], "total": 0, "truncated": False}
        normalized_kind = str(kind or "").strip()
        if normalized_kind and normalized_kind not in KIND_ORDER:
            raise ValueError(f"未知税则层级：{normalized_kind}")
        compact_needle = _SPACE_RE.sub("", needle)
        matches: list[tuple[tuple[int, int, str], dict[str, Any]]] = []
        for node in self._nodes.values():
            if normalized_kind and node["kind"] != normalized_kind:
                continue
            code = str(node["code"])
            name = str(node["name"])
            compact_name = _SPACE_RE.sub("", name.casefold())
            if needle not in code.casefold() and compact_needle not in compact_name:
                continue
            if code.casefold() == needle:
                rank = 0
            elif code.casefold().startswith(needle):
                rank = 1
            elif compact_name.startswith(compact_needle):
                rank = 2
            else:
                rank = 3
            matches.append(((rank, KIND_ORDER[str(node["kind"])], code), node))
        matches.sort(key=lambda item: item[0])
        bounded_limit = min(200, max(1, int(limit)))
        rows = []
        for _rank, node in matches[:bounded_limit]:
            payload = self._payload(node)
            payload["path"] = self.path(str(node["code"]))
            rows.append(payload)
        return {
            "rows": rows,
            "total": len(matches),
            "truncated": len(matches) > bounded_limit,
        }

    def validate(self) -> list[str]:
        issues: list[str] = []
        roots = self._children.get(None, ())
        if any(self._nodes[code]["kind"] != "section" for code in roots):
            issues.append("根节点必须全部为类")
        for node in self._nodes.values():
            expected_level = KIND_ORDER[str(node["kind"])]
            if node["level"] != expected_level:
                issues.append(f"层级不匹配：{node['code']}")
            parent_code = node["parent_code"]
            if parent_code:
                parent = self._nodes[str(parent_code)]
                if KIND_ORDER[str(parent["kind"])] != expected_level - 1:
                    issues.append(f"父级跨层：{node['code']} -> {parent_code}")
        return issues


__all__ = [
    "KIND_LABELS",
    "KIND_ORDER",
    "TariffTaxonomyIndex",
    "resolve_tariff_taxonomy_source",
]
