from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from nexterp_agent.agent_runtime.operation_catalog import (
    INFORMATION_SLOTS,
    MATERIAL_REQUEST_BINDINGS,
    MATERIAL_REQUEST_OPERATION,
    MATERIAL_REQUEST_RULES,
)

from .procurement_catalog import PROCUREMENT_CHAIN
from .role_catalog import CONTEXT_GUIDES, ROLE_CAPABILITY_LINKS, ROLE_PROFILES


ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = ROOT / "config" / "capability_catalog_migrations"


@dataclass(frozen=True)
class ExternalIdentity:
    external_subject: str
    agent_id: str
    employee_user: str
    profile_name: str
    default_project: str
    allowed_projects: tuple[str, ...]


class CapabilityCatalogRepository:
    """PostgreSQL-backed source of truth for manuals and frozen operations."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise RuntimeError("MATERIAL_CATALOG_DATABASE_URL is required")
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("psycopg is required for capability catalog support") from exc
        self._psycopg = psycopg
        self.dsn = dsn

    def connect(self):
        return self._psycopg.connect(self.dsn)

    def migrate(self) -> str:
        scripts = sorted(MIGRATIONS.glob("*.sql"))
        if not scripts:
            raise RuntimeError(f"No capability catalog migrations found in {MIGRATIONS}")
        with self.connect() as conn:
            for script in scripts:
                conn.execute(script.read_text(encoding="utf-8"))
            self._seed_material_request(conn)
            self._seed_procurement_chain(conn)
            self._seed_read_capabilities(conn)
            self._seed_role_context(conn)
            revision = self._write_revision(conn)
            conn.commit()
        return revision

    def search_nodes(self, query: str, *, module: str | None = None, limit: int = 5) -> list[dict[str, Any]]:
        normalized = normalize_text(query)
        terms = [part for part in re.split(r"\s+", normalized) if part]
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT n.node_id, n.node_type, n.module, n.label, n.summary, n.is_write,
                       n.operation_mode, n.business_object, n.intent_kind,
                       COALESCE(array_agg(a.normalized_text) FILTER (WHERE a.alias_id IS NOT NULL), '{}') AS aliases
                  FROM nexterp_manual.capability_node n
                  LEFT JOIN nexterp_manual.capability_alias a ON a.node_id = n.node_id
                 WHERE n.is_active = TRUE
                   AND n.node_type IN ('capability', 'operation')
                   AND (%s::text IS NULL OR n.module = %s::text)
                 GROUP BY n.node_id
                 ORDER BY n.sort_order, n.label
                """,
                (module, module),
            ).fetchall()
        scored = []
        for row in rows:
            payload = {
                "node_id": row[0], "node_type": row[1], "module": row[2], "label": row[3],
                "summary": row[4], "is_write": row[5], "operation_mode": row[6],
                "business_object": row[7], "intent_kind": row[8], "aliases": list(row[9] or []),
            }
            phrases = [
                normalize_text(value)
                for value in [payload["node_id"], payload["label"], *payload["aliases"]]
                if normalize_text(value)
            ]
            haystack = normalize_text(" ".join([*phrases, payload["summary"]]))
            score = 0
            if normalized:
                for phrase in phrases:
                    if normalized == phrase:
                        score = max(score, 200)
                    elif phrase in normalized:
                        score = max(score, 140 + min(len(phrase), 20))
                    elif normalized in phrase:
                        score = max(score, 120)
                score += sum(20 for term in terms if term in haystack)
            if score or not normalized:
                payload["score"] = score
                payload.pop("aliases", None)
                scored.append(payload)
        return sorted(scored, key=lambda item: (-item["score"], item["node_type"] != "operation", item["label"]))[:limit]

    def load_guides(self, node_ids: list[str]) -> list[dict[str, Any]]:
        if not node_ids or len(node_ids) > 3:
            raise ValueError("每次必须加载 1 到 3 个说明书节点")
        with self.connect() as conn:
            nodes = conn.execute(
                """SELECT node_id, node_type, module, label, summary, guide, usage_conditions,
                          prohibitions, examples_json, implementation_key, is_write,
                          operation_mode, business_object, intent_kind
                     FROM nexterp_manual.capability_node WHERE node_id = ANY(%s) AND is_active = TRUE""",
                (node_ids,),
            ).fetchall()
            edges = conn.execute(
                """SELECT e.source_node_id, e.target_node_id, e.relation_type, e.position,
                          n.node_type, n.label, n.summary, n.operation_mode, n.business_object, n.intent_kind
                     FROM nexterp_manual.capability_edge e
                     JOIN nexterp_manual.capability_node n ON n.node_id = e.target_node_id
                    WHERE e.source_node_id = ANY(%s)
                    ORDER BY e.source_node_id, e.position, n.label""",
                (node_ids,),
            ).fetchall()
        by_id: dict[str, dict[str, Any]] = {}
        for row in nodes:
            by_id[row[0]] = {
                "node_id": row[0], "node_type": row[1], "module": row[2], "label": row[3],
                "summary": row[4], "guide": row[5], "usage_conditions": row[6],
                "prohibitions": row[7], "examples": row[8], "implementation_key": row[9],
                "is_write": row[10], "operation_mode": row[11], "business_object": row[12],
                "intent_kind": row[13], "relations": [],
            }
        for row in edges:
            if row[0] in by_id:
                by_id[row[0]]["relations"].append({
                    "node_id": row[1], "relation_type": row[2], "position": row[3],
                    "node_type": row[4], "label": row[5], "summary": row[6],
                    "operation_mode": row[7], "business_object": row[8], "intent_kind": row[9],
                })
        missing = [node_id for node_id in node_ids if node_id not in by_id]
        if missing:
            raise KeyError(f"Unknown or inactive guide nodes: {', '.join(missing)}")
        return [by_id[node_id] for node_id in node_ids]

    def operation_bundle(self, operation_id: str) -> dict[str, Any]:
        with self.connect() as conn:
            operation = conn.execute(
                """SELECT n.node_id, n.module, n.label, n.summary, n.guide, n.implementation_key,
                          t.tool_name, t.compiler_key, t.resolver_key, t.preflight_key,
                          t.verifier_key, t.risk_level, t.requires_confirmation
                     FROM nexterp_manual.capability_node n
                     JOIN nexterp_manual.operation_tool t ON t.operation_id = n.node_id
                    WHERE n.node_id = %s AND n.node_type = 'operation' AND n.is_active = TRUE""",
                (operation_id,),
            ).fetchone()
            if not operation:
                raise KeyError(f"Unknown operation: {operation_id}")
            slots = conn.execute(
                """SELECT s.node_id, s.label, s.summary, os.position, os.scope, os.target_path,
                          os.source_type, os.control_type, os.is_user_editable, os.lookup_doctype,
                          os.format_hint, os.default_strategy, os.source_path, os.is_required,
                          os.resolver_key, os.fixed_value_json, os.derived_from_slot_id, os.constraint_text
                     FROM nexterp_manual.operation_slot os
                     JOIN nexterp_manual.capability_node s ON s.node_id = os.slot_id
                    WHERE os.operation_id = %s ORDER BY os.position""",
                (operation_id,),
            ).fetchall()
            rules = conn.execute(
                """SELECT rule_id, label, implementation_key, expression_text, user_message, position
                     FROM nexterp_manual.operation_rule WHERE operation_id = %s ORDER BY position""",
                (operation_id,),
            ).fetchall()
        return {
            "operation": {
                "operation_id": operation[0], "module": operation[1], "label": operation[2],
                "summary": operation[3], "guide": operation[4], "implementation_key": operation[5],
                "tool_name": operation[6], "compiler_key": operation[7], "resolver_key": operation[8],
                "preflight_key": operation[9], "verifier_key": operation[10], "risk_level": operation[11],
                "requires_confirmation": operation[12],
            },
            "slots": [
                dict(zip(
                    ("slot_id", "label", "description", "position", "scope", "target_path", "source", "control",
                     "editable", "lookup_doctype", "format_hint", "default_strategy", "source_path", "required",
                     "resolver", "fixed_value", "derived_from", "constraint"),
                    row,
                )) for row in slots
            ],
            "rules": [
                dict(zip(("rule_id", "label", "implementation_key", "expression", "message", "position"), row))
                for row in rules
            ],
        }

    def current_revision(self) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT revision_id FROM nexterp_manual.catalog_revision WHERE is_current = TRUE"
            ).fetchone()
        if not row:
            raise RuntimeError("Capability catalog has no current revision; run migration first")
        return str(row[0])

    def upsert_identity(
        self,
        *,
        external_subject: str,
        employee_user: str,
        profile_name: str,
        agent_id: str = "",
        default_project: str = "",
        allowed_projects: list[str] | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO nexterp_manual.external_identity
                       (provider, external_subject, agent_id, employee_user, profile_name, default_project, allowed_projects_json)
                     VALUES ('openclaw', %s, %s, %s, %s, NULLIF(%s, ''), %s)
                     ON CONFLICT (provider, external_subject, agent_id) DO UPDATE SET
                       employee_user = EXCLUDED.employee_user, profile_name = EXCLUDED.profile_name,
                       default_project = EXCLUDED.default_project, allowed_projects_json = EXCLUDED.allowed_projects_json,
                       is_active = TRUE, updated_at = NOW()""",
                (
                    external_subject,
                    agent_id,
                    employee_user,
                    profile_name,
                    default_project,
                    self._psycopg.types.json.Jsonb(allowed_projects or []),
                ),
            )
            conn.commit()

    def resolve_identity(self, external_subject: str, agent_id: str = "") -> ExternalIdentity:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT external_subject, agent_id, employee_user, profile_name,
                          COALESCE(default_project, ''), allowed_projects_json
                     FROM nexterp_manual.external_identity
                    WHERE provider = 'openclaw' AND external_subject = %s AND agent_id = %s AND is_active = TRUE""",
                (external_subject, agent_id),
            ).fetchone()
        if not row:
            raise PermissionError("OpenClaw 请求者尚未绑定 ERPNext 员工身份")
        return ExternalIdentity(row[0], row[1], row[2], row[3], row[4], tuple(row[5] or []))

    def resolve_identity_for_session(self, session_key: str, agent_id: str = "") -> ExternalIdentity:
        """Resolve a workbench identity from its server-registered trusted session."""
        with self.connect() as conn:
            row = conn.execute(
                """SELECT i.external_subject, i.agent_id, i.employee_user, i.profile_name,
                          COALESCE(i.default_project, ''), i.allowed_projects_json
                     FROM nexterp_manual.agent_session_context s
                     JOIN nexterp_manual.external_identity i
                       ON i.external_subject = s.external_subject AND i.agent_id = s.agent_id
                    WHERE s.session_key = %s AND s.agent_id = %s AND i.is_active = TRUE""",
                (session_key, agent_id),
            ).fetchone()
        if not row:
            raise PermissionError("工作台会话尚未绑定可信员工身份")
        return ExternalIdentity(row[0], row[1], row[2], row[3], row[4], tuple(row[5] or []))

    def create_pending(
        self,
        *,
        operation_id: str,
        identity: ExternalIdentity,
        project_code: str,
        session_key: str,
        request_id: str,
        tool_call: dict[str, Any],
        summary: dict[str, Any],
        ttl_minutes: int = 15,
    ) -> dict[str, Any]:
        canonical = json.dumps(tool_call, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        call_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        pending_id = str(uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
        revision = self.current_revision()
        with self.connect() as conn:
            row = conn.execute(
                """INSERT INTO nexterp_manual.prepared_operation
                       (pending_id, operation_id, employee_user, project_code, external_subject, agent_id,
                        session_key, request_id, catalog_revision_id, tool_call_json, tool_call_hash,
                        summary_json, status, expires_at)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                     ON CONFLICT (employee_user, request_id) DO UPDATE SET request_id = EXCLUDED.request_id
                     RETURNING pending_id, operation_id, employee_user, project_code, external_subject, agent_id,
                               session_key, request_id, catalog_revision_id, tool_call_json, tool_call_hash,
                               summary_json, status, expires_at, result_json""",
                (pending_id, operation_id, identity.employee_user, project_code, identity.external_subject,
                 identity.agent_id, session_key, request_id, revision, self._psycopg.types.json.Jsonb(tool_call),
                 call_hash, self._psycopg.types.json.Jsonb(summary), expires_at),
            ).fetchone()
            conn.commit()
        return pending_from_row(row)

    def get_pending(self, pending_id: str, *, for_update: bool = False) -> dict[str, Any]:
        suffix = " FOR UPDATE" if for_update else ""
        with self.connect() as conn:
            row = conn.execute(
                """SELECT pending_id, operation_id, employee_user, project_code, external_subject, agent_id,
                          session_key, request_id, catalog_revision_id, tool_call_json, tool_call_hash,
                          summary_json, status, expires_at, result_json
                     FROM nexterp_manual.prepared_operation WHERE pending_id = %s""" + suffix,
                (pending_id,),
            ).fetchone()
        if not row:
            raise KeyError(f"Unknown pending operation: {pending_id}")
        return pending_from_row(row)

    def claim_pending(self, pending_id: str, *, identity: ExternalIdentity, session_key: str) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        with self.connect() as conn:
            row = conn.execute(
                """SELECT pending_id, operation_id, employee_user, project_code, external_subject, agent_id,
                          session_key, request_id, catalog_revision_id, tool_call_json, tool_call_hash,
                          summary_json, status, expires_at, result_json
                     FROM nexterp_manual.prepared_operation WHERE pending_id = %s FOR UPDATE""",
                (pending_id,),
            ).fetchone()
            if not row:
                raise KeyError(f"Unknown pending operation: {pending_id}")
            pending = pending_from_row(row)
            if pending["employee_user"] != identity.employee_user or pending["external_subject"] != identity.external_subject:
                raise PermissionError("待确认动作不属于当前员工")
            if pending["agent_id"] != identity.agent_id or pending["session_key"] != session_key:
                raise PermissionError("待确认动作不属于当前 OpenClaw 会话")
            if pending["status"] == "completed":
                return pending
            if pending["status"] != "pending":
                raise RuntimeError(f"待确认动作当前状态不可执行：{pending['status']}")
            if pending["expires_at"] <= now:
                conn.execute("UPDATE nexterp_manual.prepared_operation SET status = 'expired' WHERE pending_id = %s", (pending_id,))
                conn.commit()
                raise RuntimeError("待确认动作已过期，请重新准备")
            canonical = json.dumps(pending["tool_call"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != pending["tool_call_hash"]:
                raise RuntimeError("待确认 ToolCall 完整性校验失败")
            conn.execute("UPDATE nexterp_manual.prepared_operation SET status = 'executing' WHERE pending_id = %s", (pending_id,))
            conn.commit()
        pending["status"] = "executing"
        return pending

    def finish_pending(self, pending_id: str, *, status: str, result: dict[str, Any]) -> dict[str, Any]:
        with self.connect() as conn:
            conn.execute(
                """UPDATE nexterp_manual.prepared_operation
                      SET status = %s, result_json = %s, executed_at = NOW() WHERE pending_id = %s""",
                (status, self._psycopg.types.json.Jsonb(result), pending_id),
            )
            conn.commit()
        return self.get_pending(pending_id)

    def role_context(self, role_code: str, topics: list[str]) -> dict[str, Any]:
        with self.connect() as conn:
            profile = conn.execute(
                """SELECT role_code, role_name, mission, boundaries, escalation_guidance
                     FROM nexterp_manual.agent_role_profile
                    WHERE role_code = %s AND is_active = TRUE""",
                (role_code,),
            ).fetchone()
            if not profile:
                raise KeyError(f"Unknown role profile: {role_code}")
            responsibilities = conn.execute(
                """SELECT responsibility_id, label, summary, responsibility_type, priority
                     FROM nexterp_manual.agent_role_responsibility
                    WHERE role_code = %s AND is_active = TRUE ORDER BY priority, label""",
                (role_code,),
            ).fetchall()
            guides = conn.execute(
                """SELECT g.guide_id, g.topic, g.label, g.summary, g.guide
                     FROM nexterp_manual.agent_context_guide g
                     JOIN nexterp_manual.agent_role_context rc ON rc.guide_id = g.guide_id
                    WHERE rc.role_code = %s AND g.topic = ANY(%s) AND g.is_active = TRUE
                    ORDER BY rc.relevance, g.topic""",
                (role_code, topics),
            ).fetchall()
        return {
            "profile": {"role_code": profile[0], "role_name": profile[1], "mission": profile[2],
                        "boundaries": profile[3], "escalation": profile[4]},
            "responsibilities": [
                {"responsibility_id": row[0], "label": row[1], "summary": row[2],
                 "type": row[3], "priority": row[4]} for row in responsibilities
            ],
            "guides": [
                {"guide_id": row[0], "topic": row[1], "label": row[2],
                 "summary": row[3], "guide": row[4]} for row in guides
            ],
        }

    def upsert_session_context(self, **values: Any) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO nexterp_manual.agent_session_context
                       (external_subject, agent_id, session_key, employee_user, project_code,
                        current_goal, intent_mode, confirmed_entities_json, unresolved_fields_json,
                        active_capability, loaded_context_json, recent_documents_json,
                        pending_operation, last_successful_progress, search_miss_count)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                     ON CONFLICT (external_subject, agent_id, session_key) DO UPDATE SET
                       employee_user = EXCLUDED.employee_user, project_code = EXCLUDED.project_code,
                       current_goal = EXCLUDED.current_goal, intent_mode = EXCLUDED.intent_mode,
                       confirmed_entities_json = EXCLUDED.confirmed_entities_json,
                       unresolved_fields_json = EXCLUDED.unresolved_fields_json,
                       active_capability = EXCLUDED.active_capability,
                       loaded_context_json = EXCLUDED.loaded_context_json,
                       recent_documents_json = EXCLUDED.recent_documents_json,
                       pending_operation = EXCLUDED.pending_operation,
                       last_successful_progress = EXCLUDED.last_successful_progress,
                       search_miss_count = EXCLUDED.search_miss_count, updated_at = NOW()""",
                (values["external_subject"], values.get("agent_id", ""), values["session_key"],
                 values["employee_user"], values["project_code"], values.get("current_goal", ""),
                 values.get("intent_mode", "read"), self._psycopg.types.json.Jsonb(values.get("confirmed_entities", {})),
                 self._psycopg.types.json.Jsonb(values.get("unresolved_fields", [])), values.get("active_capability"),
                 self._psycopg.types.json.Jsonb(values.get("loaded_context", [])),
                 self._psycopg.types.json.Jsonb(values.get("recent_documents", [])), values.get("pending_operation"),
                 values.get("last_successful_progress"), values.get("search_miss_count", 0)),
            )
            conn.commit()

    def session_context(self, identity: ExternalIdentity, session_key: str) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """SELECT employee_user, project_code, current_goal, intent_mode,
                          confirmed_entities_json, unresolved_fields_json, active_capability,
                          loaded_context_json, recent_documents_json, pending_operation,
                          last_successful_progress, search_miss_count
                     FROM nexterp_manual.agent_session_context
                    WHERE external_subject = %s AND agent_id = %s AND session_key = %s""",
                (identity.external_subject, identity.agent_id, session_key),
            ).fetchone()
        if not row:
            return {}
        if row[0] != identity.employee_user:
            raise PermissionError("会话工作情境不属于当前员工")
        keys = ("employee_user", "project_code", "current_goal", "intent_mode", "confirmed_entities",
                "unresolved_fields", "active_capability", "loaded_context", "recent_documents",
                "pending_operation", "last_successful_progress", "search_miss_count")
        return dict(zip(keys, row))

    def mark_context_loaded(self, identity: ExternalIdentity, session_key: str, topics: list[str]) -> None:
        current = self.session_context(identity, session_key)
        if not current:
            return
        current.update({"external_subject": identity.external_subject, "agent_id": identity.agent_id,
                        "session_key": session_key,
                        "loaded_context": list(dict.fromkeys([*(current.get("loaded_context") or []), *topics]))})
        self.upsert_session_context(**current)

    def record_search_result(self, identity: ExternalIdentity, session_key: str, *, found: bool) -> int:
        current = self.session_context(identity, session_key)
        if not current:
            return 0
        misses = 0 if found else int(current.get("search_miss_count") or 0) + 1
        current.update({"external_subject": identity.external_subject, "agent_id": identity.agent_id,
                        "session_key": session_key, "search_miss_count": misses})
        self.upsert_session_context(**current)
        return misses

    def export_markdown(self, path: Path) -> None:
        guide_ids = [
            "module.buying",
            "cap.material_request",
            "op.material_request.create",
            "cap.material_creation",
            "op.material.create_item",
        ]
        guide_ids.extend(seed.capability_id for seed in PROCUREMENT_CHAIN)
        lines = ["# Capability 说明书目录", "", f"目录版本：`{self.current_revision()}`", ""]
        for guide_id in guide_ids:
            guide = self.load_guides([guide_id])[0]
            lines.extend([f"## {guide['label']}", "", guide["summary"], "", guide["guide"], ""])
        operation_ids = [
            "op.material_request.create",
            *(seed.operation_id for seed in PROCUREMENT_CHAIN),
            "op.material.create_item",
        ]
        for operation_id in operation_ids:
            bundle = self.operation_bundle(operation_id)
            lines.extend([
                f"## {bundle['operation']['label']}字段槽位",
                "",
                "| 序号 | 字段 | 来源 | 控件 | 目标 |",
                "|---:|---|---|---|---|",
            ])
            for slot in bundle["slots"]:
                lines.append(f"| {slot['position']} | {slot['label']} | {slot['source']} | {slot['control']} | `{slot['target_path']}` |")
            lines.extend(["", "### 业务规则", ""])
            for rule in bundle["rules"]:
                lines.append(f"- **{rule['label']}**：{rule['message']}")
            lines.append("")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    def _seed_material_request(self, conn: Any) -> None:
        nodes = [
            ("module.buying", "module", "buying", "采购", "采购需求、询价、下单、收货与退货。", "先确定员工要处理的采购阶段，再沿 contains 关系加载具体能力。", "员工有采购或项目材料职责。", "不得绕过 ERPNext 权限和工作流。", [], None, False, 10),
            ("cap.material_request", "capability", "buying", "材料申请", "把项目用料需求整理为材料申请。", "用于提出项目用料需求。先加载创建操作，再提交项目、物料描述、数量和需求日期。", "员工需要为可访问项目提出用料需求。", "材料申请不是采购订单；不得编造物料编码。", ["帮我申请水泥", "明天需要 100 双帆布手套"], None, True, 20),
            ("op.material_request.create", "operation", "buying", "创建材料申请草稿", "解析真实项目、仓库和物料后创建采购类型材料申请草稿。", "提供项目、物料、数量和需求日期。公司、仓库、物料编码与单位由 Nexterp 解析；信息完整后 prepare 会返回不可修改的确认摘要。", "至少一个物料明细，数量大于 0，需求日期有效。", "不得自行拼 item_code、warehouse 或底层 ToolCall；不得跳过确认。", ["合流项目后天需要 20 包 42.5 袋装水泥"], "material_request.create.v1", True, 30),
        ]
        for slot in INFORMATION_SLOTS:
            nodes.append((slot.slot_id, "slot", "buying", slot.label, slot.description, slot.description, "", "", [], None, False, 100 + slot.serial))
        for node in nodes:
            conn.execute(
                """INSERT INTO nexterp_manual.capability_node
                       (node_id, node_type, module, label, summary, guide, usage_conditions, prohibitions,
                        examples_json, implementation_key, is_write, sort_order)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                     ON CONFLICT (node_id) DO UPDATE SET
                       node_type = EXCLUDED.node_type, module = EXCLUDED.module, label = EXCLUDED.label,
                       summary = EXCLUDED.summary, guide = EXCLUDED.guide,
                       usage_conditions = EXCLUDED.usage_conditions, prohibitions = EXCLUDED.prohibitions,
                       examples_json = EXCLUDED.examples_json, implementation_key = EXCLUDED.implementation_key,
                       is_write = EXCLUDED.is_write, is_active = TRUE, sort_order = EXCLUDED.sort_order,
                       updated_at = NOW()""",
                (*node[:8], self._psycopg.types.json.Jsonb(node[8]), *node[9:]),
            )
        edges = [("module.buying", "cap.material_request", "contains", 1), ("cap.material_request", "op.material_request.create", "contains", 1)]
        edges += [("op.material_request.create", binding.slot_id, "uses_slot", binding.position) for binding in MATERIAL_REQUEST_BINDINGS]
        for edge in edges:
            conn.execute(
                """INSERT INTO nexterp_manual.capability_edge(source_node_id, target_node_id, relation_type, position)
                     VALUES (%s, %s, %s, %s) ON CONFLICT (source_node_id, target_node_id, relation_type)
                     DO UPDATE SET position = EXCLUDED.position""", edge,
            )
        aliases = {
            "module.buying": ["采购", "买材料", "采购管理"],
            "cap.material_request": ["材料申请", "物料申请", "用料申请", "申请材料"],
            "op.material_request.create": ["创建材料申请", "新建材料申请", "提报材料需求", "要材料", "买材料"],
        }
        for node_id, values in aliases.items():
            for value in values:
                conn.execute(
                    """INSERT INTO nexterp_manual.capability_alias(node_id, alias_text, normalized_text)
                         VALUES (%s, %s, %s) ON CONFLICT (node_id, normalized_text)
                         DO UPDATE SET alias_text = EXCLUDED.alias_text""",
                    (node_id, value, normalize_text(value)),
                )
        conn.execute(
            """INSERT INTO nexterp_manual.operation_tool
                   (operation_id, tool_name, compiler_key, resolver_key, preflight_key, verifier_key, risk_level, requires_confirmation)
                 VALUES (%s, %s, 'material_request.create.v1', 'material_request.resolve.v1',
                         'material_request.preflight.v1', 'material_request.verify.v1', 'L3', TRUE)
                 ON CONFLICT (operation_id) DO UPDATE SET tool_name = EXCLUDED.tool_name,
                   compiler_key = EXCLUDED.compiler_key, resolver_key = EXCLUDED.resolver_key,
                   preflight_key = EXCLUDED.preflight_key, verifier_key = EXCLUDED.verifier_key,
                   risk_level = EXCLUDED.risk_level, requires_confirmation = EXCLUDED.requires_confirmation""",
            (MATERIAL_REQUEST_OPERATION.operation_id, MATERIAL_REQUEST_OPERATION.tool),
        )
        for binding in MATERIAL_REQUEST_BINDINGS:
            conn.execute(
                """INSERT INTO nexterp_manual.operation_slot
                       (operation_id, slot_id, position, scope, target_path, source_type, control_type,
                        is_user_editable, lookup_doctype, format_hint, default_strategy, source_path,
                        is_required, resolver_key, fixed_value_json, derived_from_slot_id, constraint_text)
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                     ON CONFLICT (operation_id, slot_id) DO UPDATE SET
                       position = EXCLUDED.position, scope = EXCLUDED.scope, target_path = EXCLUDED.target_path,
                       source_type = EXCLUDED.source_type, control_type = EXCLUDED.control_type,
                       is_user_editable = EXCLUDED.is_user_editable, lookup_doctype = EXCLUDED.lookup_doctype,
                       format_hint = EXCLUDED.format_hint, default_strategy = EXCLUDED.default_strategy,
                       source_path = EXCLUDED.source_path, is_required = EXCLUDED.is_required,
                       resolver_key = EXCLUDED.resolver_key, fixed_value_json = EXCLUDED.fixed_value_json,
                       derived_from_slot_id = EXCLUDED.derived_from_slot_id, constraint_text = EXCLUDED.constraint_text""",
                (binding.operation_id, binding.slot_id, binding.position, binding.scope.value, binding.target_path,
                 binding.source.value, binding.control.value, binding.editable, binding.lookup_doctype,
                 binding.format_hint, binding.default_strategy, binding.source_path, binding.required,
                 binding.resolver, self._psycopg.types.json.Jsonb(binding.fixed_value) if binding.fixed_value is not None else None,
                 binding.derived_from, binding.constraint),
            )
        for position, rule in enumerate(MATERIAL_REQUEST_RULES, start=1):
            conn.execute(
                """INSERT INTO nexterp_manual.operation_rule
                       (rule_id, operation_id, label, implementation_key, expression_text, user_message, position)
                     VALUES (%s, %s, %s, %s, %s, %s, %s)
                     ON CONFLICT (rule_id) DO UPDATE SET label = EXCLUDED.label,
                       implementation_key = EXCLUDED.implementation_key, expression_text = EXCLUDED.expression_text,
                       user_message = EXCLUDED.user_message, position = EXCLUDED.position""",
                (rule.rule_id, rule.operation_id, rule.label, rule.rule_id + ".v1", rule.expression, rule.message, position),
            )

    def _seed_procurement_chain(self, conn: Any) -> None:
        for capability_position, seed in enumerate(PROCUREMENT_CHAIN, start=1):
            nodes = (
                (
                    seed.capability_id,
                    "capability",
                    "buying",
                    seed.capability_label,
                    seed.capability_summary,
                    f"先加载 {seed.operation_label} 操作节点，再按说明提交业务事实。",
                    seed.usage_conditions,
                    seed.prohibitions,
                    seed.examples,
                    None,
                    True,
                    30 + capability_position * 10,
                ),
                (
                    seed.operation_id,
                    "operation",
                    "buying",
                    seed.operation_label,
                    seed.operation_summary,
                    seed.guide,
                    seed.usage_conditions,
                    seed.prohibitions,
                    seed.examples,
                    seed.compiler_key,
                    True,
                    31 + capability_position * 10,
                ),
            )
            for node in nodes:
                self._upsert_node(conn, node)
            for slot in seed.slots:
                self._upsert_node(conn, (
                    slot["slot_id"],
                    "slot",
                    "buying",
                    slot["label"],
                    slot["description"],
                    slot["description"],
                    "",
                    "",
                    (),
                    None,
                    False,
                    200 + int(slot["position"]),
                ))

            edges = [
                ("module.buying", seed.capability_id, "contains", capability_position + 1),
                (seed.capability_id, seed.operation_id, "contains", 1),
            ]
            edges.extend((seed.operation_id, slot["slot_id"], "uses_slot", slot["position"]) for slot in seed.slots)
            for edge in edges:
                conn.execute(
                    """INSERT INTO nexterp_manual.capability_edge(source_node_id, target_node_id, relation_type, position)
                         VALUES (%s, %s, %s, %s)
                         ON CONFLICT (source_node_id, target_node_id, relation_type)
                         DO UPDATE SET position = EXCLUDED.position""",
                    edge,
                )

            for alias in (*seed.aliases, seed.capability_label, seed.operation_label):
                for node_id in (seed.capability_id, seed.operation_id):
                    conn.execute(
                        """INSERT INTO nexterp_manual.capability_alias(node_id, alias_text, normalized_text)
                             VALUES (%s, %s, %s)
                             ON CONFLICT (node_id, normalized_text)
                             DO UPDATE SET alias_text = EXCLUDED.alias_text""",
                        (node_id, alias, normalize_text(alias)),
                    )

            conn.execute(
                """INSERT INTO nexterp_manual.operation_tool
                       (operation_id, tool_name, compiler_key, resolver_key, preflight_key, verifier_key,
                        risk_level, requires_confirmation)
                     VALUES (%s, %s, %s, 'procurement.resolve_source.v1',
                             'procurement.preflight.v1', 'procurement.verify.v1', 'L3', TRUE)
                     ON CONFLICT (operation_id) DO UPDATE SET
                       tool_name = EXCLUDED.tool_name, compiler_key = EXCLUDED.compiler_key,
                       resolver_key = EXCLUDED.resolver_key, preflight_key = EXCLUDED.preflight_key,
                       verifier_key = EXCLUDED.verifier_key, risk_level = EXCLUDED.risk_level,
                       requires_confirmation = EXCLUDED.requires_confirmation""",
                (seed.operation_id, seed.tool_name, seed.compiler_key),
            )
            for slot in seed.slots:
                conn.execute(
                    """INSERT INTO nexterp_manual.operation_slot
                           (operation_id, slot_id, position, scope, target_path, source_type, control_type,
                            is_user_editable, lookup_doctype, format_hint, default_strategy, source_path,
                            is_required, resolver_key, fixed_value_json, derived_from_slot_id, constraint_text)
                         VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL, NULL, %s)
                         ON CONFLICT (operation_id, slot_id) DO UPDATE SET
                           position = EXCLUDED.position, scope = EXCLUDED.scope,
                           target_path = EXCLUDED.target_path, source_type = EXCLUDED.source_type,
                           control_type = EXCLUDED.control_type, is_user_editable = EXCLUDED.is_user_editable,
                           lookup_doctype = EXCLUDED.lookup_doctype, format_hint = EXCLUDED.format_hint,
                           default_strategy = EXCLUDED.default_strategy, source_path = EXCLUDED.source_path,
                           is_required = EXCLUDED.is_required, resolver_key = EXCLUDED.resolver_key,
                           constraint_text = EXCLUDED.constraint_text""",
                    (
                        seed.operation_id,
                        slot["slot_id"],
                        slot["position"],
                        slot["scope"],
                        slot["target_path"],
                        slot["source"],
                        slot["control"],
                        slot["editable"],
                        slot["lookup_doctype"],
                        slot["format_hint"],
                        slot["default_strategy"],
                        slot["source_path"],
                        slot["required"],
                        slot["resolver"],
                        slot["constraint"],
                    ),
                )
            for position, (rule_id, label, message) in enumerate(seed.rules, start=1):
                conn.execute(
                    """INSERT INTO nexterp_manual.operation_rule
                           (rule_id, operation_id, label, implementation_key, expression_text, user_message, position)
                         VALUES (%s, %s, %s, %s, %s, %s, %s)
                         ON CONFLICT (rule_id) DO UPDATE SET
                           operation_id = EXCLUDED.operation_id, label = EXCLUDED.label,
                           implementation_key = EXCLUDED.implementation_key,
                           expression_text = EXCLUDED.expression_text,
                           user_message = EXCLUDED.user_message, position = EXCLUDED.position""",
                    (rule_id, seed.operation_id, label, rule_id + ".v1", rule_id, message, position),
                )

        chain = ["cap.material_request", *(seed.capability_id for seed in PROCUREMENT_CHAIN)]
        for position, (source, target) in enumerate(zip(chain, chain[1:]), start=1):
            conn.execute(
                """INSERT INTO nexterp_manual.capability_edge(source_node_id, target_node_id, relation_type, position)
                     VALUES (%s, %s, 'next', %s)
                     ON CONFLICT (source_node_id, target_node_id, relation_type)
                     DO UPDATE SET position = EXCLUDED.position""",
                (source, target, position),
            )

    def _upsert_node(self, conn: Any, node: tuple[Any, ...]) -> None:
        conn.execute(
            """INSERT INTO nexterp_manual.capability_node
                   (node_id, node_type, module, label, summary, guide, usage_conditions, prohibitions,
                    examples_json, implementation_key, is_write, sort_order)
                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                 ON CONFLICT (node_id) DO UPDATE SET
                   node_type = EXCLUDED.node_type, module = EXCLUDED.module, label = EXCLUDED.label,
                   summary = EXCLUDED.summary, guide = EXCLUDED.guide,
                   usage_conditions = EXCLUDED.usage_conditions, prohibitions = EXCLUDED.prohibitions,
                   examples_json = EXCLUDED.examples_json, implementation_key = EXCLUDED.implementation_key,
                   is_write = EXCLUDED.is_write, is_active = TRUE, sort_order = EXCLUDED.sort_order,
                   updated_at = NOW()""",
            (*node[:8], self._psycopg.types.json.Jsonb(node[8]), *node[9:]),
        )

    def _seed_role_context(self, conn: Any) -> None:
        for role in ROLE_PROFILES:
            conn.execute(
                """INSERT INTO nexterp_manual.agent_role_profile
                       (role_code, role_name, mission, boundaries, escalation_guidance)
                     VALUES (%s, %s, %s, %s, %s)
                     ON CONFLICT (role_code) DO UPDATE SET role_name = EXCLUDED.role_name,
                       mission = EXCLUDED.mission, boundaries = EXCLUDED.boundaries,
                       escalation_guidance = EXCLUDED.escalation_guidance,
                       is_active = TRUE, updated_at = NOW()""",
                (role.role_code, role.role_name, role.mission, role.boundaries, role.escalation),
            )
            for item in role.responsibilities:
                conn.execute(
                    """INSERT INTO nexterp_manual.agent_role_responsibility
                           (responsibility_id, role_code, label, summary, responsibility_type, priority)
                         VALUES (%s, %s, %s, %s, %s, %s)
                         ON CONFLICT (responsibility_id) DO UPDATE SET label = EXCLUDED.label,
                           summary = EXCLUDED.summary, responsibility_type = EXCLUDED.responsibility_type,
                           priority = EXCLUDED.priority, is_active = TRUE""",
                    (f"resp.{role.role_code.lower()}.{item.key}", role.role_code,
                     item.label, item.summary, item.kind, item.priority),
                )
        for topic, (label, guide) in CONTEXT_GUIDES.items():
            guide_id = f"context.{topic}"
            conn.execute(
                """INSERT INTO nexterp_manual.agent_context_guide(guide_id, topic, label, summary, guide)
                     VALUES (%s, %s, %s, %s, %s)
                     ON CONFLICT (guide_id) DO UPDATE SET label = EXCLUDED.label,
                       summary = EXCLUDED.summary, guide = EXCLUDED.guide,
                       is_active = TRUE, updated_at = NOW()""",
                (guide_id, topic, label, guide, guide),
            )
            for role in ROLE_PROFILES:
                conn.execute(
                    """INSERT INTO nexterp_manual.agent_role_context(role_code, guide_id, relevance)
                         VALUES (%s, %s, 100) ON CONFLICT (role_code, guide_id) DO NOTHING""",
                    (role.role_code, guide_id),
                )
        for role_code, node_ids in ROLE_CAPABILITY_LINKS.items():
            for relevance, node_id in enumerate(node_ids, start=1):
                conn.execute(
                    """INSERT INTO nexterp_manual.agent_role_capability(role_code, node_id, relevance)
                         VALUES (%s, %s, %s)
                         ON CONFLICT (role_code, node_id) DO UPDATE SET relevance = EXCLUDED.relevance""",
                    (role_code, node_id, relevance),
                )

    def _seed_read_capabilities(self, conn: Any) -> None:
        item_create_slots = (
            {
                "slot_id": "slot.item_create.raw_text",
                "label": "原始物料描述",
                "description": "员工提供的客观名称、用途、结构和规格描述。",
                "position": 1,
                "target_path": "facts.raw_text",
                "source": "user_input",
                "control": "read_only",
                "editable": True,
                "source_path": "request.query",
                "required": True,
                "resolver": None,
                "constraint": "不得补造员工未提供的品牌、型号或技术参数。",
            },
            {
                "slot_id": "slot.item_create.attributes",
                "label": "已确认规格属性",
                "description": "从员工描述中抽取并经确认的结构化规格属性。",
                "position": 2,
                "target_path": "facts.attributes",
                "source": "user_input",
                "control": "read_only",
                "editable": True,
                "source_path": "request.attributes",
                "required": True,
                "resolver": None,
                "constraint": "键必须来自标准类型属性模板；必填属性不能为空。",
            },
            {
                "slot_id": "slot.item_create.type_id",
                "label": "标准类型编号",
                "description": "冻结物料名称字典返回的稳定 type_id。",
                "position": 3,
                "target_path": "classification.type_id",
                "source": "resolver",
                "control": "derived",
                "editable": False,
                "source_path": "classification.selected_type.type_id",
                "required": True,
                "resolver": "material.classify.v1",
                "constraint": "分类状态必须为 new_sku；模型不得指定 type_id。",
            },
            {
                "slot_id": "slot.item_create.item_code",
                "label": "物料编码",
                "description": "按标准类型既有编码前缀和当前最大序号生成的唯一编码。",
                "position": 4,
                "target_path": "arguments.item_code",
                "source": "system_generated",
                "control": "derived",
                "editable": False,
                "source_path": "coding.next_code",
                "required": True,
                "resolver": "material.code.v1",
                "constraint": "必须同时避开发布目录和 ERPNext 已存在编码。",
            },
            {
                "slot_id": "slot.item_create.item_name",
                "label": "SKU 名称",
                "description": "标准物料名称加影响 SKU 唯一性的关键属性。",
                "position": 5,
                "target_path": "arguments.item_name",
                "source": "derived",
                "control": "derived",
                "editable": False,
                "source_path": "classification.standard_name+identity_attributes",
                "required": True,
                "resolver": None,
                "constraint": "不得把无关备注、价格或状态写入名称。",
            },
            {
                "slot_id": "slot.item_create.item_group",
                "label": "ERPNext 物料组",
                "description": "同一冻结标准类型已有 SKU 的稳定 ERPNext Item Group。",
                "position": 6,
                "target_path": "arguments.item_group",
                "source": "derived",
                "control": "derived",
                "editable": False,
                "source_path": "catalog.release_rows.item_group",
                "required": True,
                "resolver": "item_group.exists.v1",
                "constraint": "必须存在于 ERPNext Item Group，不允许模型临时改组。",
            },
            {
                "slot_id": "slot.item_create.stock_uom",
                "label": "库存单位",
                "description": "员工明确单位或同一标准类型的稳定库存单位。",
                "position": 7,
                "target_path": "arguments.stock_uom",
                "source": "derived",
                "control": "derived",
                "editable": False,
                "source_path": "request.stock_uom|catalog.release_rows.stock_uom",
                "required": True,
                "resolver": "uom.exists.v1",
                "constraint": "必须存在于 ERPNext UOM；与既有类型单位冲突时停止建档。",
            },
        )
        nodes = (
            ("cap.material_lookup", "capability", "stock", "物料查询", "查询标准物料、SKU 详情和相关仓库库存。", "read", "Item", "lookup_material", False),
            ("op.material.search", "operation", "stock", "查询标准物料与库存", "按名称、别名、规格或编码查询候选，并返回相关仓库库存。", "read", "Item", "lookup_material", False),
            ("cap.material_classification", "capability", "stock", "新物料分类", "依据冻结的类目、物料族、标准名称和属性模板判断新物料。", "analyze", "Item", "classify_material", False),
            ("op.material.classify", "operation", "stock", "分析新物料分类", "识别现有标准类型、必填属性和重复 SKU，或进入新类型审核。", "analyze", "Item", "classify_material", False),
            ("cap.material_creation", "capability", "stock", "标准物料建档", "把已分类且规格完整的新 SKU 建成 ERPNext Item。", "write", "Item", "create_material", True),
            ("op.material.create_item", "operation", "stock", "创建标准物料", "重新分类、查重并冻结编码后创建一个 Item。", "write", "Item", "create_material", True),
            ("cap.document_lookup", "capability", "generic", "业务单据查询", "查询当前员工可见的业务单据及状态。", "read", "Document", "lookup_document", False),
            ("op.document.search", "operation", "generic", "查询业务单据状态", "按单号、类型和项目查询当前员工可见单据。", "read", "Document", "lookup_document", False),
        )
        for node_id, node_type, module, label, summary, mode, business_object, intent, is_write in nodes:
            conn.execute(
                """INSERT INTO nexterp_manual.capability_node
                       (node_id, node_type, module, label, summary, guide, usage_conditions,
                        prohibitions, examples_json, implementation_key, is_write, sort_order,
                        operation_mode, business_object, intent_kind)
                     VALUES (%s, %s, %s, %s, %s, %s, '', %s, '[]'::jsonb, %s, %s, 5, %s, %s, %s)
                     ON CONFLICT (node_id) DO UPDATE SET label = EXCLUDED.label,
                       summary = EXCLUDED.summary, guide = EXCLUDED.guide,
                       prohibitions = EXCLUDED.prohibitions,
                       operation_mode = EXCLUDED.operation_mode,
                       business_object = EXCLUDED.business_object,
                       intent_kind = EXCLUDED.intent_kind, is_write = EXCLUDED.is_write,
                       is_active = TRUE""",
                (node_id, node_type, module, label, summary,
                 self._read_capability_guide(intent),
                 self._read_capability_prohibition(intent), f"catalog.{intent}.v1", is_write,
                 mode, business_object, intent),
            )
        conn.execute(
            """UPDATE nexterp_manual.capability_node
                  SET examples_json = %s::jsonb
                WHERE node_id IN ('cap.material_creation', 'op.material.create_item')""",
            (self._psycopg.types.json.Jsonb([{
                "operation_id": "op.material.create_item",
                "request_id": "create-item-example-1",
                "query": "内六角螺丝",
                "attributes": {
                    "规格": "M8×45",
                    "材质": "碳钢",
                    "强度等级": "8.8",
                    "表面处理": "镀锌",
                },
            }]),),
        )
        for source, target in (("cap.material_lookup", "op.material.search"),
                               ("cap.material_classification", "op.material.classify"),
                               ("cap.material_creation", "op.material.create_item"),
                               ("cap.document_lookup", "op.document.search")):
            conn.execute(
                """INSERT INTO nexterp_manual.capability_edge(source_node_id, target_node_id, relation_type, position)
                     VALUES (%s, %s, 'contains', 1) ON CONFLICT DO NOTHING""", (source, target),
            )
        for slot in item_create_slots:
            self._upsert_node(conn, (
                slot["slot_id"],
                "slot",
                "stock",
                slot["label"],
                slot["description"],
                slot["description"],
                "",
                "",
                (),
                None,
                False,
                300 + int(slot["position"]),
            ))
            conn.execute(
                """INSERT INTO nexterp_manual.capability_edge
                       (source_node_id, target_node_id, relation_type, position)
                     VALUES ('op.material.create_item', %s, 'uses_slot', %s)
                     ON CONFLICT (source_node_id, target_node_id, relation_type)
                     DO UPDATE SET position = EXCLUDED.position""",
                (slot["slot_id"], slot["position"]),
            )
        aliases = {
            "cap.material_lookup": ("查物料", "有没有物料", "物料表", "SKU查询", "查库存"),
            "op.material.search": ("物料查询", "规格查询", "候选物料", "库存查询", "有没有14的钻头"),
            "cap.material_classification": ("新物料分类", "物料怎么分类", "物料建档", "新增物料", "标准名称判断"),
            "op.material.classify": ("分析物料分类", "判断类目", "判断物料族", "匹配标准名称", "检查重复SKU"),
            "cap.material_creation": ("创建物料", "物料建档", "新增SKU", "新增标准物料"),
            "op.material.create_item": ("确认创建物料", "新建Item", "创建物料主数据"),
            "cap.document_lookup": ("查单据", "单据状态", "最近单据"),
            "op.document.search": ("查询材料申请", "查询采购订单", "单据进度"),
        }
        for node_id, values in aliases.items():
            for value in values:
                conn.execute(
                    """INSERT INTO nexterp_manual.capability_alias(node_id, alias_text, normalized_text)
                         VALUES (%s, %s, %s) ON CONFLICT (node_id, normalized_text)
                         DO UPDATE SET alias_text = EXCLUDED.alias_text""",
                    (node_id, value, normalize_text(value)),
                )
        conn.execute(
            """INSERT INTO nexterp_manual.operation_tool
                   (operation_id, tool_name, compiler_key, resolver_key, preflight_key, verifier_key,
                    risk_level, requires_confirmation)
                 VALUES ('op.material.create_item', 'erpnext.stock.create_item',
                         'material.create.v1', 'material.classify.v1',
                         'material.duplicate_and_dependency_check.v1', 'material.readback.v1', 'L3', TRUE)
                 ON CONFLICT (operation_id) DO UPDATE SET
                   tool_name = EXCLUDED.tool_name, compiler_key = EXCLUDED.compiler_key,
                   resolver_key = EXCLUDED.resolver_key, preflight_key = EXCLUDED.preflight_key,
                   verifier_key = EXCLUDED.verifier_key, risk_level = EXCLUDED.risk_level,
                   requires_confirmation = EXCLUDED.requires_confirmation"""
        )
        for slot in item_create_slots:
            conn.execute(
                """INSERT INTO nexterp_manual.operation_slot
                       (operation_id, slot_id, position, scope, target_path, source_type, control_type,
                        is_user_editable, source_path, is_required, resolver_key, constraint_text)
                     VALUES ('op.material.create_item', %s, %s, 'document', %s, %s, %s,
                             %s, %s, %s, %s, %s)
                     ON CONFLICT (operation_id, slot_id) DO UPDATE SET
                       position = EXCLUDED.position, scope = EXCLUDED.scope,
                       target_path = EXCLUDED.target_path, source_type = EXCLUDED.source_type,
                       control_type = EXCLUDED.control_type,
                       is_user_editable = EXCLUDED.is_user_editable,
                       source_path = EXCLUDED.source_path, is_required = EXCLUDED.is_required,
                       resolver_key = EXCLUDED.resolver_key,
                       constraint_text = EXCLUDED.constraint_text""",
                (
                    slot["slot_id"],
                    slot["position"],
                    slot["target_path"],
                    slot["source"],
                    slot["control"],
                    slot["editable"],
                    slot["source_path"],
                    slot["required"],
                    slot["resolver"],
                    slot["constraint"],
                ),
            )
        item_create_rules = (
            (
                "rule.item_create.classification",
                "分类允许建档",
                "classification.status == new_sku and ready_to_create",
                "只有规格完整且不重复的新 SKU 才能进入建档。",
            ),
            (
                "rule.item_create.dependencies",
                "主数据依赖存在",
                "item_group and stock_uom exist in ERPNext",
                "标准物料组和库存单位必须已存在。",
            ),
            (
                "rule.item_create.unique_code",
                "物料编码唯一",
                "item_code not in release catalog and ERPNext Item",
                "物料编码必须由系统生成且不能重复。",
            ),
            (
                "rule.item_create.confirmation",
                "确认后执行并回读",
                "frozen tool call confirmed and ERPNext Item readback matches",
                "员工确认后才能创建，创建成功必须回读核对。",
            ),
        )
        for position, (rule_id, label, expression, message) in enumerate(item_create_rules, start=1):
            conn.execute(
                """INSERT INTO nexterp_manual.operation_rule
                       (rule_id, operation_id, label, implementation_key,
                        expression_text, user_message, position)
                     VALUES (%s, 'op.material.create_item', %s, %s, %s, %s, %s)
                     ON CONFLICT (rule_id) DO UPDATE SET
                       label = EXCLUDED.label, implementation_key = EXCLUDED.implementation_key,
                       expression_text = EXCLUDED.expression_text,
                       user_message = EXCLUDED.user_message, position = EXCLUDED.position""",
                (rule_id, label, f"{rule_id}.v1", expression, message, position),
            )

    @staticmethod
    def _read_capability_guide(intent: str) -> str:
        if intent == "create_material":
            return (
                "这是写入型标准物料建档能力。调用 nexterp_prepare_operation 时，query 只放简洁物料名称或客观描述，"
                "从员工原话提取出的规格键值必须放入 attributes 对象；本操作不使用 items，禁止把物料名称和规格塞入 "
                "items[].raw_item_text。示例：operation_id=op.material.create_item，query=内六角螺丝，"
                "attributes={规格:M8×45, 材质:碳钢, 强度等级:8.8, 表面处理:镀锌}。不得遗漏员工已经明确提供的属性，"
                "也不得补造原话中没有的品牌、型号或技术参数。Nexterp 会重新执行冻结字典分类、必填属性检查和重复 SKU "
                "检查。只有分类结果为 new_sku 时才会生成编码和确认卡。编码、标准名称、物料组和单位由确定性程序生成；"
                "确认后以当前员工身份创建 ERPNext Item，并回读核对。"
            )
        if intent == "classify_material":
            return (
                "这是只分析、不写入的物料分类能力。先从员工原话提取客观事实：物料叫法、用途、结构、"
                "兼容接口、材质、尺寸和单位；不得补造原话中没有的品牌、型号或技术参数。调用时把原始描述放入 query，"
                "把已明确事实放入 attributes。若已知可提供 top_group_hint 和 material_family_hint，但它们只是提示，"
                "最终边界由冻结字典决定。结果 existing_sku 表示已有完全匹配 SKU；needs_choice 表示必须让员工选择；"
                "needs_input 表示标准类型已确定但关键属性不足；new_sku 表示可进入新 SKU 建档准备；"
                "new_type_review 表示现有字典没有可靠类型，必须交物料管理员审核。"
            )
        if intent == "lookup_material":
            return (
                "这是只读能力。返回真实候选以及当前员工相关项目仓库的实时库存，不创建、不修改任何 ERPNext 数据。"
                "候选中的 inventory 是已查询结果；inventory_status=available 且明细为空时表示相关仓库当前库存为 0，"
                "应直接告知员工，不要再次承诺以后查询库存。"
            )
        return "这是只读能力，只能解释实际返回的数据，不得创建或修改 ERPNext 数据。"

    @staticmethod
    def _read_capability_prohibition(intent: str) -> str:
        if intent == "create_material":
            return (
                "不得使用 items 字段，不得自行填写物料编码，不得跳过分类或查重，不得修改冻结确认卡，"
                "也不得在用户确认前写 ERPNext。"
            )
        if intent == "classify_material":
            return "不得猜测缺失属性，不得自行新增标准类型，不得创建 Item，也不得把分析升级成任何写操作。"
        return "不得把查询升级成申请或其他写操作。"

    def _write_revision(self, conn: Any) -> str:
        nodes = conn.execute(
            """SELECT node_id, node_type, module, label, summary, guide, usage_conditions, prohibitions,
                      examples_json, implementation_key, is_write, is_active, sort_order,
                      operation_mode, business_object, intent_kind
                 FROM nexterp_manual.capability_node ORDER BY node_id"""
        ).fetchall()
        edges = conn.execute(
            "SELECT source_node_id, target_node_id, relation_type, position, metadata_json FROM nexterp_manual.capability_edge ORDER BY 1,2,3"
        ).fetchall()
        aliases = conn.execute(
            "SELECT node_id, alias_text, alias_type, normalized_text FROM nexterp_manual.capability_alias ORDER BY 1,4"
        ).fetchall()
        tools = conn.execute(
            """SELECT operation_id, tool_name, compiler_key, resolver_key, preflight_key, verifier_key,
                      risk_level, requires_confirmation FROM nexterp_manual.operation_tool ORDER BY 1"""
        ).fetchall()
        slots = conn.execute(
            """SELECT operation_id, slot_id, position, scope, target_path, source_type, control_type,
                      is_user_editable, lookup_doctype, format_hint, default_strategy, source_path,
                      is_required, resolver_key, fixed_value_json, derived_from_slot_id, constraint_text
                 FROM nexterp_manual.operation_slot ORDER BY 1,3"""
        ).fetchall()
        rules = conn.execute(
            """SELECT rule_id, operation_id, label, implementation_key, expression_text, user_message, position
                 FROM nexterp_manual.operation_rule ORDER BY 2,7,1"""
        ).fetchall()
        role_profiles = conn.execute(
            "SELECT role_code, role_name, mission, boundaries, escalation_guidance FROM nexterp_manual.agent_role_profile ORDER BY 1"
        ).fetchall()
        responsibilities = conn.execute(
            """SELECT responsibility_id, role_code, label, summary, responsibility_type, priority
                 FROM nexterp_manual.agent_role_responsibility ORDER BY 2,6,1"""
        ).fetchall()
        role_capabilities = conn.execute(
            "SELECT role_code, node_id, relevance FROM nexterp_manual.agent_role_capability ORDER BY 1,3,2"
        ).fetchall()
        payload = json.dumps(
            {"nodes": nodes, "edges": edges, "aliases": aliases, "tools": tools, "slots": slots,
             "rules": rules, "role_profiles": role_profiles, "responsibilities": responsibilities,
             "role_capabilities": role_capabilities},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
            separators=(",", ":"),
        )
        checksum = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        revision = "manual-" + checksum[:16]
        conn.execute("UPDATE nexterp_manual.catalog_revision SET is_current = FALSE WHERE is_current = TRUE")
        conn.execute(
            """INSERT INTO nexterp_manual.catalog_revision(revision_id, content_checksum, schema_version, is_current)
                 VALUES (%s, %s, 2, TRUE) ON CONFLICT (revision_id) DO UPDATE SET is_current = TRUE""",
            (revision, checksum),
        )
        return revision


def pending_from_row(row: Any) -> dict[str, Any]:
    return {
        "pending_id": str(row[0]), "operation_id": row[1], "employee_user": row[2],
        "project_code": row[3], "external_subject": row[4], "agent_id": row[5],
        "session_key": row[6], "request_id": row[7], "catalog_revision": row[8],
        "tool_call": row[9], "tool_call_hash": row[10], "summary": row[11],
        "status": row[12], "expires_at": row[13], "result": row[14],
    }


def normalize_text(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().casefold())
