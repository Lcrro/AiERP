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
                "summary": row[4], "is_write": row[5], "aliases": list(row[6] or []),
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
                          prohibitions, examples_json, implementation_key, is_write
                     FROM nexterp_manual.capability_node WHERE node_id = ANY(%s) AND is_active = TRUE""",
                (node_ids,),
            ).fetchall()
            edges = conn.execute(
                """SELECT e.source_node_id, e.target_node_id, e.relation_type, e.position,
                          n.node_type, n.label, n.summary
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
                "is_write": row[10], "relations": [],
            }
        for row in edges:
            if row[0] in by_id:
                by_id[row[0]]["relations"].append({
                    "node_id": row[1], "relation_type": row[2], "position": row[3],
                    "node_type": row[4], "label": row[5], "summary": row[6],
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

    def export_markdown(self, path: Path) -> None:
        guides = self.load_guides(["module.buying", "cap.material_request", "op.material_request.create"])
        bundle = self.operation_bundle("op.material_request.create")
        lines = ["# Capability 说明书目录", "", f"目录版本：`{self.current_revision()}`", ""]
        for guide in guides:
            lines.extend([f"## {guide['label']}", "", guide["summary"], "", guide["guide"], ""])
        lines.extend(["## 字段槽位", "", "| 序号 | 字段 | 来源 | 控件 | 目标 |", "|---:|---|---|---|---|"])
        for slot in bundle["slots"]:
            lines.append(f"| {slot['position']} | {slot['label']} | {slot['source']} | {slot['control']} | `{slot['target_path']}` |")
        lines.extend(["", "## 业务规则", ""])
        for rule in bundle["rules"]:
            lines.append(f"- **{rule['label']}**：{rule['message']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

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

    def _write_revision(self, conn: Any) -> str:
        nodes = conn.execute(
            """SELECT node_id, node_type, module, label, summary, guide, usage_conditions, prohibitions,
                      examples_json, implementation_key, is_write, is_active, sort_order
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
        payload = json.dumps(
            {"nodes": nodes, "edges": edges, "aliases": aliases, "tools": tools, "slots": slots, "rules": rules},
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
                 VALUES (%s, %s, 1, TRUE) ON CONFLICT (revision_id) DO UPDATE SET is_current = TRUE""",
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
