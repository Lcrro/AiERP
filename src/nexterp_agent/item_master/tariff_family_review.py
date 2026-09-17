"""Deterministic review mapping from tariff nodes to Nexterp material families.

The tariff is an external classification system, not an ERPNext Item Group.
This module therefore emits review candidates only.  Rules are deliberately
small, explainable, and constrained to families already present in the local
material-master release.  Ambiguous or unsupported rows remain review-required
instead of being silently published.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from .tariff_extraction import TariffNode


REVIEW_VERSION = "tariff-family-review-v0.1"
DECISION_VERSION = "tariff-family-decision-v0.1"
FROZEN_RELEASE_VERSION = "tariff-family-release-v0.1"


def normalize_tariff_name(value: str) -> str:
    """Collapse PDF whitespace without changing the source meaning."""

    text = re.sub(r"\s+", " ", str(value or "").replace("\u3000", " ")).strip()
    return text.rstrip("：:；;")


@dataclass(frozen=True)
class FamilyRule:
    rule_id: str
    top_group: str
    material_family: str
    keywords: tuple[str, ...] = ()
    code_prefixes: tuple[str, ...] = ()
    priority: int = 0
    confidence: float = 0.0


# Prefix rules are intentionally more specific than keyword rules.  The
# 7318 mappings cover the fastener examples that motivated this review step.
FAMILY_RULES: tuple[FamilyRule, ...] = (
    FamilyRule("hs731816-nut", "紧固件与连接件", "螺母", code_prefixes=("731816",), priority=120, confidence=0.99),
    FamilyRule("hs731821-washer", "紧固件与连接件", "垫圈/垫片", code_prefixes=("731821", "731822"), priority=120, confidence=0.99),
    FamilyRule("hs731823-rivet", "紧固件与连接件", "扣件/连接件", code_prefixes=("731823",), priority=120, confidence=0.88),
    FamilyRule("hs731824-pin", "紧固件与连接件", "销/卡簧", code_prefixes=("731824",), priority=120, confidence=0.96),
    FamilyRule("hs7318-fastener", "紧固件与连接件", "螺丝/螺栓", code_prefixes=("731811", "731812", "731813", "731814", "731815", "731829"), priority=120, confidence=0.96),
    FamilyRule("hs7317-nail", "紧固件与连接件", "钉类", code_prefixes=("7317",), priority=120, confidence=0.95),
    FamilyRule("hs741510-nail", "紧固件与连接件", "钉类", code_prefixes=("741510",), priority=120, confidence=0.92),
    FamilyRule("hs741521-washer", "紧固件与连接件", "垫圈/垫片", code_prefixes=("741521",), priority=120, confidence=0.94),
    FamilyRule("hs74153310-screw", "紧固件与连接件", "螺丝/螺栓", code_prefixes=("74153310",), priority=120, confidence=0.90),
    FamilyRule("fastener-nut", "紧固件与连接件", "螺母", keywords=("螺母", "螺帽"), priority=80, confidence=0.95),
    FamilyRule("fastener-washer", "紧固件与连接件", "垫圈/垫片", keywords=("垫圈", "垫片", "弹簧垫"), priority=80, confidence=0.95),
    FamilyRule("fastener-pin", "紧固件与连接件", "销/卡簧", keywords=("开尾销", "销", "卡簧"), priority=78, confidence=0.88),
    FamilyRule("fastener-rivet", "紧固件与连接件", "扣件/连接件", keywords=("铆钉",), priority=80, confidence=0.88),
    FamilyRule("fastener-rod", "紧固件与连接件", "螺杆/丝杆", keywords=("螺杆", "丝杆", "丝杠"), priority=80, confidence=0.94),
    FamilyRule("fastener-screw", "紧固件与连接件", "螺丝/螺栓", keywords=("螺钉", "螺栓", "螺丝"), priority=76, confidence=0.90),
    FamilyRule("pipe-valve", "管材管件阀门", "阀门", keywords=("阀",), priority=70, confidence=0.82),
    FamilyRule("pipe-flange", "管材管件阀门", "法兰", keywords=("法兰",), priority=72, confidence=0.90),
    FamilyRule("pipe-fitting", "管材管件阀门", "直接/接头", keywords=("接头", "管件", "弯头", "三通"), priority=60, confidence=0.72),
    # Do not use the single character ``管`` here: it occurs in unrelated
    # chapter text and would create a large false-positive bucket.
    FamilyRule("pipe-material", "管材管件阀门", "管材", keywords=("管材", "钢管", "塑料管", "无缝管", "焊管", "铜管", "铝管"), priority=55, confidence=0.72),
    FamilyRule("electrical-cable", "电气电料", "电线电缆", keywords=("电线", "电缆"), priority=70, confidence=0.92),
    FamilyRule("electrical-switch", "电气电料", "低压电器", keywords=("断路器", "开关", "继电器"), priority=68, confidence=0.84),
    FamilyRule("electrical-terminal", "电气电料", "接线端子/线鼻子", keywords=("端子", "线鼻子"), priority=68, confidence=0.88),
    FamilyRule("metal-steel-pipe", "金属材料", "钢管", keywords=("钢管",), priority=72, confidence=0.92),
    FamilyRule("metal-steel-plate", "金属材料", "钢板/板材", keywords=("钢板", "板材"), priority=72, confidence=0.92),
    FamilyRule("metal-section", "金属材料", "型钢", keywords=("型钢",), priority=72, confidence=0.92),
    FamilyRule("metal-rebar", "金属材料", "钢筋/线材", keywords=("钢筋", "线材"), priority=70, confidence=0.88),
    FamilyRule("tool-drill", "工具耗材", "钻头", keywords=("钻头", "钻具"), priority=68, confidence=0.90),
    FamilyRule("equipment-bearing", "设备备件", "传动件", keywords=("轴承",), priority=65, confidence=0.86),
    FamilyRule("chemical-rubber", "化工胶粘涂料", "橡胶材料", keywords=("橡胶",), priority=60, confidence=0.75),
)


@dataclass(frozen=True)
class FamilyCandidate:
    code: str
    source_name: str
    normalized_name: str
    parent_code: str
    parent_name: str
    chapter_code: str
    chapter_context: str
    page: int
    suggested_top_group: str
    suggested_material_family: str
    candidate_families: tuple[str, ...]
    matching_rule: str
    confidence: float
    review_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "source_name": self.source_name,
            "normalized_name": self.normalized_name,
            "parent_code": self.parent_code,
            "parent_name": self.parent_name,
            "chapter_code": self.chapter_code,
            "chapter_context": self.chapter_context,
            "page": self.page,
            "suggested_top_group": self.suggested_top_group,
            "suggested_material_family": self.suggested_material_family,
            "candidate_families": list(self.candidate_families),
            "matching_rule": self.matching_rule,
            "confidence": self.confidence,
            "review_status": self.review_status,
        }


def _node_value(node: TariffNode | Mapping[str, Any], key: str, default: Any = "") -> Any:
    if isinstance(node, TariffNode):
        return getattr(node, key, default)
    return node.get(key, default)


def _rule_matches(rule: FamilyRule, code: str, source_text: str) -> bool:
    if rule.code_prefixes and any(code.startswith(prefix) for prefix in rule.code_prefixes):
        return True
    # Keyword matches deliberately use the leaf name only.  Parent headings
    # are retained as evidence but are too broad to classify a leaf called
    # ``其他`` or a mixed heading such as 7318.
    return bool(rule.keywords and any(keyword in source_text for keyword in rule.keywords))


def map_tariff_nodes(nodes: Iterable[TariffNode | Mapping[str, Any]]) -> list[FamilyCandidate]:
    """Map SKU nodes to explainable internal-family candidates.

    A row is ``candidate`` only when one highest-priority rule wins.  Ties are
    ``ambiguous`` and no family is selected.  Rows without a rule are
    ``unmapped``.  Both statuses remain review-required by design.
    """

    source = list(nodes)
    parent_nodes = {
        str(_node_value(node, "code")): normalize_tariff_name(str(_node_value(node, "name")))
        for node in source
        if str(_node_value(node, "kind")) in {"heading", "subheading"}
    }
    results: list[FamilyCandidate] = []
    for node in source:
        if str(_node_value(node, "kind")) != "sku":
            continue
        code = str(_node_value(node, "code"))
        source_name = str(_node_value(node, "name"))
        normalized_name = normalize_tariff_name(source_name)
        parent_code = str(_node_value(node, "parent_code"))
        parent_name = parent_nodes.get(parent_code, "")
        chapter_code = code[:2]
        prefix_matches = [
            rule for rule in FAMILY_RULES
            if rule.code_prefixes and _rule_matches(rule, code, normalized_name)
        ]
        # A precise HS prefix is stronger than leaf keywords.  Without a
        # precise prefix, however, a mixed leaf such as “螺钉、螺栓及螺母”
        # must remain ambiguous even when one keyword has a higher priority.
        matches = prefix_matches or [rule for rule in FAMILY_RULES if _rule_matches(rule, code, normalized_name)]
        highest = max((rule.priority for rule in matches), default=-1)
        winners = [rule for rule in matches if rule.priority == highest]
        if not prefix_matches:
            keyword_keys = tuple(dict.fromkeys(f"{rule.top_group}/{rule.material_family}" for rule in matches))
            if len(keyword_keys) > 1:
                winners = matches
        winner_keys = tuple(dict.fromkeys(f"{rule.top_group}/{rule.material_family}" for rule in winners))
        if len(winner_keys) == 1:
            top_group, family = winner_keys[0].split("/", 1)
            matching_rule = winners[0].rule_id
            confidence = winners[0].confidence
            status = "candidate"
        elif len(winner_keys) > 1:
            top_group = family = ""
            matching_rule = "ambiguous:" + ",".join(rule.rule_id for rule in winners)
            confidence = max(rule.confidence for rule in winners)
            status = "ambiguous"
        else:
            top_group = family = ""
            matching_rule = "none"
            confidence = 0.0
            status = "unmapped"
        results.append(
            FamilyCandidate(
                code=code,
                source_name=source_name,
                normalized_name=normalized_name,
                parent_code=parent_code,
                parent_name=parent_name,
                chapter_code=chapter_code,
                chapter_context=f"HS第{int(chapter_code):02d}章",
                page=int(_node_value(node, "page", 0) or 0),
                suggested_top_group=top_group,
                suggested_material_family=family,
                candidate_families=winner_keys,
                matching_rule=matching_rule,
                confidence=confidence,
                review_status=status,
            )
        )
    return results


def load_tariff_nodes(path: Path) -> list[dict[str, Any]]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_internal_families(path: Path) -> set[tuple[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return {(row["top_group"], row["material_family"]) for row in csv.DictReader(handle, delimiter="\t")}


def build_review_package(input_path: Path, output_dir: Path, internal_release_path: Path | None = None) -> dict[str, Any]:
    """Build a TSV/JSON summary without mutating either source release."""

    nodes = load_tariff_nodes(input_path)
    rows = map_tariff_nodes(nodes)
    valid_families = load_internal_families(internal_release_path) if internal_release_path else set()
    if valid_families:
        for index, row in enumerate(rows):
            key = (row.suggested_top_group, row.suggested_material_family)
            if row.review_status == "candidate" and key not in valid_families:
                rows[index] = FamilyCandidate(**{**row.as_dict(), "candidate_families": list(row.candidate_families), "suggested_top_group": "", "suggested_material_family": "", "matching_rule": f"invalid-internal-family:{row.matching_rule}", "review_status": "unmapped"})
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    columns = list(rows[0].as_dict()) if rows else list(FamilyCandidate.__annotations__)
    with (output_dir / "tariff_family_candidates.tsv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        for row in rows:
            data = row.as_dict()
            data["candidate_families"] = " | ".join(data["candidate_families"])
            writer.writerow(data)
    summary = {
        "release": REVIEW_VERSION,
        "source_path": str(input_path),
        "row_count": len(rows),
        "status_counts": dict(Counter(row.review_status for row in rows)),
        "candidate_family_counts": dict(Counter(f"{row.suggested_top_group}/{row.suggested_material_family}" for row in rows if row.review_status == "candidate")),
        "chapter_counts": dict(Counter(row.chapter_code for row in rows)),
        "unmapped_sample": [row.as_dict() for row in rows if row.review_status == "unmapped"][:20],
        "ambiguous_sample": [row.as_dict() for row in rows if row.review_status == "ambiguous"][:20],
        "erpnext_written": False,
        "review_required": True,
    }
    (output_dir / "tariff_family_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "tariff_family_rules.json").write_text(json.dumps([rule.__dict__ for rule in FAMILY_RULES], ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


DECISION_COLUMNS = (
    "code",
    "decision",
    "top_group",
    "material_family",
    "reviewer",
    "comment",
    "source_name",
    "suggested_top_group",
    "suggested_material_family",
    "review_status",
    "confidence",
    "chapter_context",
    "parent_code",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_review_candidates(path: Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def build_review_slice(candidate_path: Path, output_dir: Path, code_prefixes: Sequence[str]) -> dict[str, Any]:
    """Create a reproducible, review-only subset such as HS 7317/7318."""

    prefixes = tuple(sorted({str(value).strip() for value in code_prefixes if str(value).strip()}))
    if not prefixes:
        raise ValueError("至少需要一个税号前缀")
    rows = load_review_candidates(candidate_path)
    selected = [row for row in rows if any(str(row.get("code", "")).startswith(prefix) for prefix in prefixes)]
    if len({row.get("code", "") for row in selected}) != len(selected):
        raise ValueError("切片候选包包含重复税号")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_output = output_dir / "tariff_family_candidates.tsv"
    columns = list(rows[0]) if rows else list(DECISION_COLUMNS)
    with candidate_output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(selected)
    decision_output = output_dir / "tariff_family_decisions.tsv"
    decision_meta = build_decision_template(candidate_output, decision_output)
    summary = {
        "release": f"{REVIEW_VERSION}-slice",
        "source_candidate_path": str(candidate_path),
        "source_candidate_sha256": sha256_file(candidate_path),
        "slice_candidate_sha256": sha256_file(candidate_output),
        "code_prefixes": list(prefixes),
        "row_count": len(selected),
        "status_counts": dict(Counter(row.get("review_status", "") for row in selected)),
        "decision_template": str(decision_output),
        "decision_template_sha256": decision_meta["candidate_sha256"],
        "erpnext_written": False,
        "review_required": True,
    }
    (output_dir / "tariff_family_slice_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def build_decision_template(candidate_path: Path, output_path: Path) -> dict[str, Any]:
    """Write an explicit blank decision sheet and bind it to the candidate hash."""

    candidates = load_review_candidates(candidate_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=DECISION_COLUMNS, delimiter="\t")
        writer.writeheader()
        for row in candidates:
            writer.writerow({
                "code": row.get("code", ""),
                "decision": "",
                "top_group": row.get("suggested_top_group", ""),
                "material_family": row.get("suggested_material_family", ""),
                "reviewer": "",
                "comment": "",
                "source_name": row.get("source_name", ""),
                "suggested_top_group": row.get("suggested_top_group", ""),
                "suggested_material_family": row.get("suggested_material_family", ""),
                "review_status": row.get("review_status", ""),
                "confidence": row.get("confidence", ""),
                "chapter_context": row.get("chapter_context", ""),
                "parent_code": row.get("parent_code", ""),
            })
    metadata = {
        "decision_version": DECISION_VERSION,
        "candidate_path": str(Path(candidate_path)),
        "candidate_sha256": sha256_file(candidate_path),
        "row_count": len(candidates),
        "decision_required": True,
        "erpnext_written": False,
    }
    meta_path = output_path.with_suffix(output_path.suffix + ".meta.json")
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return metadata


def freeze_review_package(
    candidate_path: Path,
    decision_path: Path,
    output_dir: Path,
    internal_release_path: Path,
) -> dict[str, Any]:
    """Freeze only explicitly approved mappings into a review-only release."""

    candidates = load_review_candidates(candidate_path)
    candidate_by_code = {str(row.get("code", "")): row for row in candidates}
    if len(candidate_by_code) != len(candidates):
        raise ValueError("候选包包含重复税号，不能冻结")
    candidate_hash = sha256_file(candidate_path)
    metadata_path = Path(decision_path).with_suffix(Path(decision_path).suffix + ".meta.json")
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("candidate_sha256") != candidate_hash:
            raise ValueError("决策模板绑定的候选包哈希已过期，请重新生成模板")

    valid_families = load_internal_families(internal_release_path)
    with Path(decision_path).open("r", encoding="utf-8-sig", newline="") as handle:
        decisions = list(csv.DictReader(handle, delimiter="\t"))
    decision_by_code: dict[str, dict[str, str]] = {}
    for row in decisions:
        code = str(row.get("code", "")).strip()
        if not code or code in decision_by_code:
            raise ValueError("决策表包含空税号或重复税号")
        if code not in candidate_by_code:
            raise ValueError(f"决策表包含候选包之外的税号：{code}")
        decision = str(row.get("decision", "")).strip().lower()
        if decision not in {"approve", "reject", "revise"}:
            raise ValueError(f"税号 {code} 的 decision 必须是 approve/reject/revise")
        decision_by_code[code] = row

    approved: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    for code, decision in decision_by_code.items():
        source = candidate_by_code[code]
        action = str(decision.get("decision", "")).strip().lower()
        top_group = str(decision.get("top_group", "")).strip()
        family = str(decision.get("material_family", "")).strip()
        reviewer = str(decision.get("reviewer", "")).strip()
        comment = str(decision.get("comment", "")).strip()
        issue = ""
        if action == "approve":
            if not reviewer:
                issue = "approve 必须填写 reviewer"
            elif not top_group or not family:
                issue = "approve 必须填写 top_group 和 material_family"
            elif (top_group, family) not in valid_families:
                issue = "approve 指向了不存在的内部物料族"
            else:
                approved.append({
                    "code": code,
                    "tariff_name": source.get("normalized_name", ""),
                    "parent_code": source.get("parent_code", ""),
                    "chapter_context": source.get("chapter_context", ""),
                    "page": source.get("page", ""),
                    "top_group": top_group,
                    "material_family": family,
                    "decision": action,
                    "reviewer": reviewer,
                    "comment": comment,
                    "source_candidate_status": source.get("review_status", ""),
                    "source_matching_rule": source.get("matching_rule", ""),
                    "source_confidence": source.get("confidence", ""),
                })
        elif action == "revise" and not comment:
            issue = "revise 必须填写 comment"
        audit_rows.append({"code": code, "decision": action, "reviewer": reviewer, "issue": issue, "comment": comment})
        if issue:
            raise ValueError(f"税号 {code} 无法冻结：{issue}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    release_path = output_dir / "tariff_family_release.tsv"
    release_columns = list(approved[0]) if approved else [
        "code", "tariff_name", "parent_code", "chapter_context", "page", "top_group", "material_family",
        "decision", "reviewer", "comment", "source_candidate_status", "source_matching_rule", "source_confidence",
    ]
    with release_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=release_columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(approved)
    audit_path = output_dir / "tariff_family_decision_audit.tsv"
    with audit_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["code", "decision", "reviewer", "issue", "comment"], delimiter="\t")
        writer.writeheader()
        writer.writerows(audit_rows)
    summary = {
        "release": FROZEN_RELEASE_VERSION,
        "candidate_sha256": candidate_hash,
        "decision_sha256": sha256_file(decision_path),
        "release_sha256": sha256_file(release_path),
        "candidate_row_count": len(candidates),
        "decision_row_count": len(decisions),
        "release_row_count": len(approved),
        "decision_counts": dict(Counter(row["decision"] for row in audit_rows)),
        "not_decided_count": len(candidates) - len(decisions),
        "publication_status": "review_only_frozen",
        "erpnext_written": False,
    }
    (output_dir / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary
