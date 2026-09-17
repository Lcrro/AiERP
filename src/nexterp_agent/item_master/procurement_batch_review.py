"""Local, auditable review workflow for procurement batch boundary items.

The review store is deliberately downstream of the batch pilot and upstream of
any material publication.  It never calls ERPNext.  Every decision is bound to
the hash of the source candidate so a rerun cannot silently inherit a stale
human review.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from .procurement_templates import ProcurementTemplateRegistry


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES_PATH = ROOT / "data" / "material_master" / "procurement_review_rules_v0_1.json"
_JOB_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_ACTIONS = {"approved", "revised", "deferred", "excluded"}
_MATERIALIZATIONS = {"ready", "split_ready", "hold", "excluded"}


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _canonical_hash(value: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_decision_hash(decision: Mapping[str, Any]) -> str:
    """Return the immutable binding hash shown to and returned by the UI."""

    return _canonical_hash(decision)


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n")
    temporary.replace(path)


class ProcurementReviewRuleCatalog:
    """Versioned deterministic rules extracted from reviewed edge cases."""

    def __init__(self, path: Path = DEFAULT_RULES_PATH) -> None:
        self.path = Path(path).resolve()
        source_bytes = self.path.read_bytes()
        self.catalog_sha256 = hashlib.sha256(source_bytes).hexdigest()
        payload = json.loads(source_bytes.decode("utf-8"))
        self.schema_version = int(payload.get("schema_version") or 0)
        self.rules_version = str(payload.get("rules_version") or "").strip()
        self.principles = [str(value).strip() for value in payload.get("principles") or [] if str(value).strip()]
        rules: dict[str, dict[str, Any]] = {}
        for raw in payload.get("rules") or []:
            rule = dict(raw)
            rule_id = str(rule.get("rule_id") or "").strip()
            if not rule_id or rule_id in rules:
                raise ValueError(f"采购复核规则编号缺失或重复：{rule_id or '空'}")
            if not rule.get("title") or not rule.get("guidance"):
                raise ValueError(f"采购复核规则不完整：{rule_id}")
            rules[rule_id] = rule
        if self.schema_version != 1 or not self.rules_version or not rules:
            raise ValueError("采购复核规则目录无效")
        self.rules = rules

    def require(self, rule_ids: Iterable[str]) -> list[str]:
        values = list(dict.fromkeys(str(value).strip() for value in rule_ids if str(value).strip()))
        unknown = [value for value in values if value not in self.rules]
        if unknown:
            raise ValueError(f"未知采购复核规则：{unknown[0]}")
        return values

    def match(self, text: str) -> list[dict[str, Any]]:
        normalized = str(text or "").casefold()
        output = []
        for rule in self.rules.values():
            keywords = [str(value).casefold() for value in rule.get("keywords") or []]
            excludes = [str(value).casefold() for value in rule.get("excludes") or []]
            if keywords and any(value in normalized for value in keywords) and not any(value in normalized for value in excludes):
                output.append(dict(rule))
        return output

    def public_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rules_version": self.rules_version,
            "catalog_sha256": self.catalog_sha256,
            "principles": self.principles,
            "rules": list(self.rules.values()),
        }


class ProcurementBatchReviewStore:
    """Persist, summarize and freeze local reviews for one completed pilot job."""

    def __init__(
        self,
        runtime_root: Path,
        *,
        rules_path: Path = DEFAULT_RULES_PATH,
        template_registry: ProcurementTemplateRegistry | None = None,
        allowed_gpc_codes: Iterable[str] | None = None,
        max_source_row: int = 101,
    ) -> None:
        self.runtime_root = Path(runtime_root).resolve()
        self.jobs_root = (self.runtime_root / "jobs").resolve()
        self.rules = ProcurementReviewRuleCatalog(rules_path)
        self.template_registry = template_registry or ProcurementTemplateRegistry.from_files()
        self.allowed_gpc_codes = {str(value) for value in (allowed_gpc_codes or []) if str(value)}
        self.max_source_row = int(max_source_row)

    def _job_dir(self, job_id: str) -> Path:
        value = str(job_id or "").strip()
        if not _JOB_ID_RE.fullmatch(value):
            raise ValueError("批处理任务编号无效")
        path = (self.jobs_root / value).resolve()
        if self.jobs_root not in path.parents or not path.is_dir():
            raise ValueError("批处理任务不存在")
        return path

    def _source(self, job_id: str) -> tuple[Path, dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
        job_dir = self._job_dir(job_id)
        audit_path = job_dir / "audit.json"
        decisions_path = job_dir / "decisions.jsonl"
        if not audit_path.is_file() or not decisions_path.is_file():
            raise ValueError("批处理任务尚未完成")
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        if audit.get("status") != "completed" or audit.get("writes_erpnext") is not False:
            raise ValueError("只能审阅已完成且未写入 ERPNext 的本地任务")
        source = dict(audit.get("source") or {})
        selected_end = int(source.get("selected_end_row") or 0)
        if selected_end > self.max_source_row:
            raise ValueError(f"本轮审阅范围只允许到源表第 {self.max_source_row} 行")
        decisions = _load_jsonl(decisions_path)
        pending = {row["cluster_id"]: row for row in decisions if row.get("queue") == "needs_review"}
        if not pending:
            raise ValueError("当前任务没有待审边界项")
        for row in pending.values():
            if max([int(value) for value in row.get("source_rows") or [0]]) > self.max_source_row:
                raise ValueError("检测到超出本轮范围的源行")
        return job_dir, audit, decisions, pending

    @staticmethod
    def _review_index(path: Path) -> dict[str, dict[str, Any]]:
        return {str(row.get("cluster_id")): row for row in _load_jsonl(path) if row.get("cluster_id")}

    def status(self, job_id: str) -> dict[str, Any]:
        job_dir, audit, _decisions, pending = self._source(job_id)
        review_path = job_dir / "boundary-reviews.jsonl"
        reviews = self._review_index(review_path)
        action_counts = Counter(str(row.get("action") or "") for row in reviews.values())
        materialization_counts = Counter(str(row.get("materialization") or "") for row in reviews.values())
        items = []
        for cluster_id, source in pending.items():
            text = " ".join([*(source.get("raw_names") or []), str(source.get("standard_type") or "")])
            review = reviews.get(cluster_id)
            matched = {row["rule_id"]: row for row in self.rules.match(text)}
            for rule_id in (review or {}).get("rule_ids") or []:
                if rule_id in self.rules.rules:
                    matched[rule_id] = dict(self.rules.rules[rule_id])
            items.append({
                "cluster_id": cluster_id,
                "source_decision_sha256": source_decision_hash(source),
                "source_rows": list(source.get("source_rows") or []),
                "raw_names": list(source.get("raw_names") or []),
                "matched_rules": list(matched.values()),
                "review": review,
            })
        total = len(pending)
        reviewed = len(set(pending) & set(reviews))
        release_path = job_dir / "boundary-review-release.json"
        release = json.loads(release_path.read_text(encoding="utf-8")) if release_path.is_file() else None
        return {
            "job_id": job_id,
            "scope": {
                "source_sheet": (audit.get("source") or {}).get("source_sheet"),
                "selected_start_row": (audit.get("source") or {}).get("selected_start_row"),
                "selected_end_row": (audit.get("source") or {}).get("selected_end_row"),
                "selected_row_count": (audit.get("source") or {}).get("selected_row_count"),
                "next_rows_processed": False,
                "writes_erpnext": False,
            },
            "summary": {
                "total": total,
                "reviewed": reviewed,
                "remaining": total - reviewed,
                "complete": reviewed == total,
                "frozen": release is not None,
                "action_counts": dict(action_counts),
                "materialization_counts": dict(materialization_counts),
            },
            "rules": self.rules.public_payload(),
            "items": items,
            "release": release,
        }

    def save(self, job_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        job_dir, _audit, _decisions, pending = self._source(job_id)
        if (job_dir / "boundary-review-release.json").exists():
            raise ValueError("本轮审阅已冻结，不能直接覆盖")
        cluster_id = str(payload.get("cluster_id") or "").strip()
        source = pending.get(cluster_id)
        if source is None:
            raise ValueError("只能审阅当前任务的 needs_review 边界项")
        expected_hash = source_decision_hash(source)
        if str(payload.get("source_decision_sha256") or "") != expected_hash:
            raise ValueError("候选内容已变化，请刷新页面后重新审阅")
        action = str(payload.get("action") or "").strip()
        materialization = str(payload.get("materialization") or "").strip()
        if action not in _ACTIONS or materialization not in _MATERIALIZATIONS:
            raise ValueError("审阅动作或物料化状态无效")
        if action == "deferred" and materialization != "hold":
            raise ValueError("延期项必须保持 hold")
        if action == "excluded" and materialization != "excluded":
            raise ValueError("排除项必须标记为 excluded")
        if action in {"approved", "revised"} and materialization not in {"ready", "split_ready", "hold"}:
            raise ValueError("批准或修订项的物料化状态无效")
        rationale = str(payload.get("rationale") or "").strip()
        if len(rationale) < 8:
            raise ValueError("请记录不少于 8 个字的复核依据")
        rule_ids = self.rules.require(payload.get("rule_ids") or [])
        if not rule_ids:
            raise ValueError("边界项必须绑定至少一条可复用规则")
        final_material = dict(payload.get("final_material") or {})
        variants = [dict(row) for row in payload.get("variants") or []]
        if action in {"approved", "revised"}:
            required = ["standard_type", "gpc_brick_code", "main_template_id", "stock_uom"]
            missing = [key for key in required if not str(final_material.get(key) or "").strip()]
            if missing:
                raise ValueError(f"确认类型时缺少字段：{missing[0]}")
            template_id = str(final_material["main_template_id"])
            if template_id not in self.template_registry.main_templates:
                raise ValueError(f"未知采购主模板：{template_id}")
            constraint_ids = list(final_material.get("constraint_ids") or [])
            unknown_constraints = [value for value in constraint_ids if value not in self.template_registry.constraints]
            if unknown_constraints:
                raise ValueError(f"未知采购约束：{unknown_constraints[0]}")
            code = str(final_material["gpc_brick_code"])
            if self.allowed_gpc_codes and code not in self.allowed_gpc_codes:
                raise ValueError(f"GPC Brick 不存在于固定参考包：{code}")
            if materialization == "split_ready" and len(variants) < 2:
                raise ValueError("拆分完成项至少需要两个实际发生的 SKU 变体")
        review = {
            "schema_version": 1,
            "job_id": job_id,
            "cluster_id": cluster_id,
            "source_decision_sha256": expected_hash,
            "source_rows": list(source.get("source_rows") or []),
            "raw_names": list(source.get("raw_names") or []),
            "action": action,
            "materialization": materialization,
            "final_material": final_material,
            "variants": variants,
            "rule_ids": rule_ids,
            "rationale": rationale,
            "reviewer": str(payload.get("reviewer") or "codex-assisted").strip(),
            "reviewed_at": _now(),
            "writes_erpnext": False,
        }
        review_path = job_dir / "boundary-reviews.jsonl"
        reviews = self._review_index(review_path)
        reviews[cluster_id] = review
        order = {cluster_id: index for index, cluster_id in enumerate(pending)}
        _write_jsonl(review_path, sorted(reviews.values(), key=lambda row: order.get(row["cluster_id"], 10**9)))
        return {"review": review, "status": self.status(job_id)}

    def freeze(self, job_id: str) -> dict[str, Any]:
        job_dir, audit, _decisions, pending = self._source(job_id)
        release_path = job_dir / "boundary-review-release.json"
        if release_path.is_file():
            return json.loads(release_path.read_text(encoding="utf-8"))
        reviews = self._review_index(job_dir / "boundary-reviews.jsonl")
        missing = [cluster_id for cluster_id in pending if cluster_id not in reviews]
        if missing:
            raise ValueError(f"仍有 {len(missing)} 个边界项未审阅，不能冻结")
        applied_rule_ids = list(dict.fromkeys(
            rule_id for cluster_id in pending for rule_id in reviews[cluster_id].get("rule_ids") or []
        ))
        release = {
            "schema_version": 1,
            "release_type": "procurement_boundary_review",
            "job_id": job_id,
            "frozen_at": _now(),
            "source": dict(audit.get("source") or {}),
            "source_audit_sha256": _canonical_hash(audit),
            "decision_count": len(reviews),
            "rules_version": self.rules.rules_version,
            "rules_catalog_sha256": self.rules.catalog_sha256,
            "applied_rule_ids": applied_rule_ids,
            "action_counts": dict(Counter(reviews[item]["action"] for item in pending)),
            "materialization_counts": dict(Counter(reviews[item]["materialization"] for item in pending)),
            "next_rows_processed": False,
            "writes_erpnext": False,
            "reviews": [reviews[item] for item in pending],
        }
        release["release_sha256"] = _canonical_hash(release)
        temporary = release_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(release, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(release_path)
        return release
