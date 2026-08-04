from __future__ import annotations

import json
from typing import Any

from .type_governance import GovernanceSnapshot


GOVERNANCE_SCHEMA_SQL = """
create table if not exists material_governance_batch (
    batch_id text primary key,
    prompt_version text not null,
    generator_model text not null,
    reviewer_model text not null,
    input_hash text not null,
    family_count integer not null,
    name_count integer not null,
    status text not null check (status in ('frozen', 'review_required', 'failed')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists material_type_dictionary (
    type_id text primary key,
    top_group text not null,
    material_family text not null,
    standard_name text not null,
    normalized_name text not null,
    definition text not null,
    includes text not null default '',
    excludes text not null default '',
    governance_status text not null check (governance_status in ('frozen', 'review_required', 'superseded')),
    revision integer not null default 1 check (revision > 0),
    source_hash text not null,
    prompt_version text not null,
    generator_model text not null,
    reviewer_model text not null,
    frozen_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (top_group, material_family, normalized_name, revision)
);

create table if not exists material_type_alias (
    id bigserial primary key,
    type_id text not null references material_type_dictionary(type_id) on delete cascade,
    alias text not null,
    normalized_alias text not null,
    alias_kind text not null default 'governance',
    created_at timestamptz not null default now(),
    unique (type_id, normalized_alias)
);

create table if not exists material_attribute_definition (
    attribute_key text primary key,
    display_name text not null,
    value_type text not null check (value_type in ('text', 'number', 'enum', 'boolean')),
    unit text not null default '',
    enum_values jsonb not null default '[]'::jsonb,
    description text not null default '',
    updated_at timestamptz not null default now()
);

alter table material_attribute_definition
    drop constraint if exists material_attribute_definition_value_type_check;
alter table material_attribute_definition
    add constraint material_attribute_definition_value_type_check
    check (value_type in ('text', 'number', 'enum', 'boolean'));

create table if not exists material_type_attribute (
    type_id text not null references material_type_dictionary(type_id) on delete cascade,
    attribute_key text not null references material_attribute_definition(attribute_key),
    requirement text not null check (requirement in ('required', 'optional')),
    affects_sku_identity boolean not null default true,
    display_order integer not null default 0,
    primary key (type_id, attribute_key)
);

create table if not exists material_name_decision (
    top_group text not null,
    material_family text not null,
    current_name text not null,
    action text not null check (action in ('keep', 'rename', 'merge', 'split', 'needs_evidence')),
    target_type_ids jsonb not null default '[]'::jsonb,
    reason text not null,
    decision_status text not null check (decision_status in ('frozen', 'review_required', 'superseded')),
    source_hash text not null,
    review_summary text not null default '',
    revision integer not null default 1,
    updated_at timestamptz not null default now(),
    primary key (top_group, material_family, current_name, revision)
);

create table if not exists material_sku_mapping (
    item_code text primary key,
    type_id text references material_type_dictionary(type_id),
    standard_name text not null default '',
    mapping_method text not null,
    mapping_evidence text not null default '',
    mapping_status text not null check (mapping_status in ('frozen', 'review_required', 'superseded')),
    source_hash text not null,
    updated_at timestamptz not null default now()
);

create table if not exists material_governance_issue (
    issue_id text primary key,
    batch_id text not null references material_governance_batch(batch_id) on delete cascade,
    top_group text not null,
    material_family text not null,
    current_name text not null default '',
    item_code text not null default '',
    issue_type text not null,
    severity text not null check (severity in ('high', 'medium', 'low')),
    detail text not null,
    status text not null check (status in ('open', 'resolved')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_material_type_dictionary_family
    on material_type_dictionary(top_group, material_family, governance_status);
create index if not exists idx_material_name_decision_family
    on material_name_decision(top_group, material_family, decision_status);
create index if not exists idx_material_sku_mapping_type
    on material_sku_mapping(type_id, mapping_status);
create index if not exists idx_material_governance_issue_family
    on material_governance_issue(top_group, material_family, status);
"""


class PostgresTypeGovernanceCatalog:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("psycopg is required for material type governance") from exc
        self._psycopg = psycopg
        self.dsn = dsn

    def connect(self):
        return self._psycopg.connect(self.dsn)

    def setup_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(GOVERNANCE_SCHEMA_SQL)
            conn.commit()

    def frozen_family_hashes(self, *, prompt_version: str) -> dict[tuple[str, str], str]:
        self.setup_schema()
        with self.connect() as conn:
            rows = conn.execute(
                """
                select mtd.top_group, mtd.material_family, mtd.source_hash
                from material_type_dictionary mtd
                where mtd.governance_status = 'frozen'
                  and mtd.prompt_version = %s
                  and not exists (
                      select 1 from material_name_decision mnd
                      where mnd.top_group = mtd.top_group
                        and mnd.material_family = mtd.material_family
                        and mnd.source_hash = mtd.source_hash
                        and mnd.decision_status <> 'frozen'
                  )
                  and not exists (
                      select 1 from material_governance_issue mgi
                      where mgi.top_group = mtd.top_group
                        and mgi.material_family = mtd.material_family
                        and mgi.status = 'open'
                  )
                group by mtd.top_group, mtd.material_family, mtd.source_hash
                """,
                (prompt_version,),
            ).fetchall()
        return {(str(row[0]), str(row[1])): str(row[2]) for row in rows}

    def persist_snapshot(self, snapshot: GovernanceSnapshot) -> None:
        self.setup_schema()
        batch = snapshot.batch
        with self.connect() as conn:
            conn.execute(
                """
                insert into material_governance_batch (
                    batch_id, prompt_version, generator_model, reviewer_model,
                    input_hash, family_count, name_count, status, updated_at
                ) values (%s, %s, %s, %s, %s, %s, %s, %s, now())
                on conflict (batch_id) do update set
                    prompt_version = excluded.prompt_version,
                    generator_model = excluded.generator_model,
                    reviewer_model = excluded.reviewer_model,
                    input_hash = excluded.input_hash,
                    family_count = excluded.family_count,
                    name_count = excluded.name_count,
                    status = excluded.status,
                    updated_at = now()
                """,
                (
                    batch["batch_id"],
                    batch["prompt_version"],
                    batch["generator_model"],
                    batch["reviewer_model"],
                    batch["input_hash"],
                    int(batch["family_count"]),
                    int(batch["name_count"]),
                    batch["status"],
                ),
            )

            family_keys = {
                (str(row["top_group"]), str(row["material_family"]))
                for row in [*snapshot.type_dictionary, *snapshot.name_decisions, *snapshot.issues]
                if row.get("top_group") and row.get("material_family")
            }
            for top_group, material_family in family_keys:
                conn.execute(
                    "delete from material_governance_issue where top_group = %s and material_family = %s",
                    (top_group, material_family),
                )
                conn.execute(
                    """
                    delete from material_sku_mapping msm
                    using material_type_dictionary mtd
                    where msm.type_id = mtd.type_id
                      and mtd.top_group = %s
                      and mtd.material_family = %s
                    """,
                    (top_group, material_family),
                )
                conn.execute(
                    "delete from material_name_decision where top_group = %s and material_family = %s",
                    (top_group, material_family),
                )
                conn.execute(
                    "delete from material_type_dictionary where top_group = %s and material_family = %s",
                    (top_group, material_family),
                )

            for row in snapshot.type_dictionary:
                normalized_name = _normalize_name(str(row["standard_name"]))
                conn.execute(
                    """
                    insert into material_type_dictionary (
                        type_id, top_group, material_family, standard_name,
                        normalized_name, definition, includes, excludes,
                        governance_status, revision, source_hash, prompt_version,
                        generator_model, reviewer_model, frozen_at, updated_at
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                              case when %s = 'frozen' then now() else null end, now())
                    on conflict (type_id) do update set
                        top_group = excluded.top_group,
                        material_family = excluded.material_family,
                        standard_name = excluded.standard_name,
                        normalized_name = excluded.normalized_name,
                        definition = excluded.definition,
                        includes = excluded.includes,
                        excludes = excluded.excludes,
                        governance_status = excluded.governance_status,
                        revision = excluded.revision,
                        source_hash = excluded.source_hash,
                        prompt_version = excluded.prompt_version,
                        generator_model = excluded.generator_model,
                        reviewer_model = excluded.reviewer_model,
                        frozen_at = case
                            when excluded.governance_status = 'frozen'
                            then coalesce(material_type_dictionary.frozen_at, now())
                            else null
                        end,
                        updated_at = now()
                    """,
                    (
                        row["type_id"],
                        row["top_group"],
                        row["material_family"],
                        row["standard_name"],
                        normalized_name,
                        row["definition"],
                        row["includes"],
                        row["excludes"],
                        row["governance_status"],
                        int(row["revision"]),
                        row["source_hash"],
                        row["prompt_version"],
                        row["generator_model"],
                        row["reviewer_model"],
                        row["governance_status"],
                    ),
                )

            for row in snapshot.type_aliases:
                conn.execute(
                    """
                    insert into material_type_alias (type_id, alias, normalized_alias, alias_kind)
                    values (%s, %s, %s, %s)
                    on conflict (type_id, normalized_alias) do update set
                        alias = excluded.alias,
                        alias_kind = excluded.alias_kind
                    """,
                    (row["type_id"], row["alias"], row["normalized_alias"], row["alias_kind"]),
                )

            for row in snapshot.attribute_templates:
                enum_values = [value for value in str(row["enum_values"]).split("；") if value]
                conn.execute(
                    """
                    insert into material_attribute_definition (
                        attribute_key, display_name, value_type, unit,
                        enum_values, description, updated_at
                    ) values (%s, %s, %s, %s, %s::jsonb, %s, now())
                    on conflict (attribute_key) do update set
                        display_name = excluded.display_name,
                        value_type = excluded.value_type,
                        unit = excluded.unit,
                        enum_values = excluded.enum_values,
                        description = excluded.description,
                        updated_at = now()
                    """,
                    (
                        row["attribute_key"],
                        row["display_name"],
                        row["value_type"],
                        row["unit"],
                        json.dumps(enum_values, ensure_ascii=False),
                        row["description"],
                    ),
                )
                conn.execute(
                    """
                    insert into material_type_attribute (
                        type_id, attribute_key, requirement,
                        affects_sku_identity, display_order
                    ) values (%s, %s, %s, %s, %s)
                    on conflict (type_id, attribute_key) do update set
                        requirement = excluded.requirement,
                        affects_sku_identity = excluded.affects_sku_identity,
                        display_order = excluded.display_order
                    """,
                    (
                        row["type_id"],
                        row["attribute_key"],
                        row["requirement"],
                        _as_bool(row["affects_sku_identity"]),
                        int(row["display_order"]),
                    ),
                )

            for row in snapshot.name_decisions:
                target_ids = [value for value in str(row["target_type_ids"]).split("；") if value]
                conn.execute(
                    """
                    insert into material_name_decision (
                        top_group, material_family, current_name, action,
                        target_type_ids, reason, decision_status, source_hash,
                        review_summary, revision, updated_at
                    ) values (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, 1, now())
                    on conflict (top_group, material_family, current_name, revision) do update set
                        action = excluded.action,
                        target_type_ids = excluded.target_type_ids,
                        reason = excluded.reason,
                        decision_status = excluded.decision_status,
                        source_hash = excluded.source_hash,
                        review_summary = excluded.review_summary,
                        updated_at = now()
                    """,
                    (
                        row["top_group"],
                        row["material_family"],
                        row["current_name"],
                        row["action"],
                        json.dumps(target_ids, ensure_ascii=False),
                        row["reason"],
                        row["decision_status"],
                        row["source_hash"],
                        row["review_summary"],
                    ),
                )

            for row in snapshot.sku_mappings:
                conn.execute(
                    """
                    insert into material_sku_mapping (
                        item_code, type_id, standard_name, mapping_method,
                        mapping_evidence, mapping_status, source_hash, updated_at
                    ) values (%s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (item_code) do update set
                        type_id = excluded.type_id,
                        standard_name = excluded.standard_name,
                        mapping_method = excluded.mapping_method,
                        mapping_evidence = excluded.mapping_evidence,
                        mapping_status = excluded.mapping_status,
                        source_hash = excluded.source_hash,
                        updated_at = now()
                    """,
                    (
                        row["item_code"],
                        row["type_id"],
                        row["standard_name"],
                        row["mapping_method"],
                        row["mapping_evidence"],
                        row["mapping_status"],
                        row["source_hash"],
                    ),
                )

            conn.execute("delete from material_governance_issue where batch_id = %s", (batch["batch_id"],))
            for row in snapshot.issues:
                conn.execute(
                    """
                    insert into material_governance_issue (
                        issue_id, batch_id, top_group, material_family,
                        current_name, item_code, issue_type, severity,
                        detail, status, updated_at
                    ) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (issue_id) do update set
                        detail = excluded.detail,
                        severity = excluded.severity,
                        status = excluded.status,
                        updated_at = now()
                    """,
                    (
                        row["issue_id"],
                        row["batch_id"],
                        row["top_group"],
                        row["material_family"],
                        row["current_name"],
                        row["item_code"],
                        row["issue_type"],
                        row["severity"],
                        row["detail"],
                        row["status"],
                    ),
                )
            conn.commit()

    def export_rows(self) -> dict[str, list[dict[str, Any]]]:
        self.setup_schema()
        queries = {
            "material_type_dictionary": """
                select type_id, top_group, material_family, standard_name, definition,
                       includes, excludes, governance_status, revision, source_hash,
                       prompt_version, generator_model, reviewer_model
                from material_type_dictionary
                where governance_status <> 'superseded'
                order by top_group, material_family, standard_name, type_id
            """,
            "material_type_aliases": """
                select type_id, alias, normalized_alias, alias_kind
                from material_type_alias order by type_id, normalized_alias
            """,
            "material_attribute_templates": """
                select mta.type_id, mad.attribute_key, mad.display_name,
                       mta.requirement, mad.value_type, mad.unit,
                       array_to_string(array(select jsonb_array_elements_text(mad.enum_values)), '；') as enum_values,
                       mta.affects_sku_identity, mta.display_order, mad.description
                from material_type_attribute mta
                join material_attribute_definition mad using (attribute_key)
                order by mta.type_id, mta.display_order, mad.attribute_key
            """,
            "material_name_decisions": """
                select top_group, material_family, current_name, action,
                       array_to_string(array(select jsonb_array_elements_text(target_type_ids)), '；') as target_type_ids,
                       reason, decision_status, source_hash, review_summary
                from material_name_decision
                where decision_status <> 'superseded'
                order by top_group, material_family, current_name
            """,
            "sku_type_mapping": """
                select item_code, type_id, standard_name, mapping_method,
                       mapping_evidence, mapping_status, source_hash
                from material_sku_mapping
                where mapping_status <> 'superseded'
                order by item_code
            """,
            "material_governance_issues": """
                select issue_id, batch_id, top_group, material_family, current_name,
                       item_code, issue_type, severity, detail, status
                from material_governance_issue
                order by top_group, material_family, current_name, issue_id
            """,
        }
        output: dict[str, list[dict[str, Any]]] = {}
        with self.connect() as conn:
            for name, query in queries.items():
                cursor = conn.execute(query)
                columns = [column.name for column in cursor.description]
                output[name] = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        return output


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _normalize_name(value: str) -> str:
    return "".join(character for character in value.casefold() if character not in " -_/（）()")
