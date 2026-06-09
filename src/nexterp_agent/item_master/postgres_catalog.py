from __future__ import annotations

from dataclasses import dataclass
import csv
from decimal import Decimal
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA_SQL = """
create extension if not exists pg_trgm;

create table if not exists material_groups (
    id bigserial primary key,
    path text not null unique,
    level1 text not null,
    level2 text,
    level3 text,
    parent_path text,
    source text not null default 'purchase_review',
    created_at timestamptz not null default now()
);

create table if not exists material_items (
    proposed_item_code text primary key,
    standard_name text not null,
    item_group_path text not null references material_groups(path),
    canonical_group_path text not null default '',
    canonical_level1 text not null default '',
    canonical_level2 text,
    canonical_level3 text,
    group_mapping_confidence numeric(4, 2),
    group_mapping_reason text not null default '',
    group_needs_human_review boolean not null default false,
    specs_text text not null default '',
    unit text not null default '',
    source_count integer not null default 0,
    source_statuses text not null default '',
    alias_names text not null default '',
    source_rows text not null default '',
    notes text not null default '',
    disabled boolean not null default false,
    normalized_search_text text not null default '',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists material_group_mappings (
    reviewed_group_path text primary key,
    canonical_group_path text not null,
    canonical_level1 text not null,
    canonical_level2 text,
    canonical_level3 text,
    confidence numeric(4, 2) not null,
    rule_reason text not null default '',
    needs_human_review boolean not null default false,
    updated_at timestamptz not null default now()
);

create table if not exists material_aliases (
    id bigserial primary key,
    raw_name text not null,
    normalized_raw_name text not null,
    proposed_item_code text not null references material_items(proposed_item_code) on delete cascade,
    standard_name text not null,
    item_group_path text not null,
    specs_text text not null default '',
    unit text not null default '',
    created_at timestamptz not null default now(),
    unique (normalized_raw_name, proposed_item_code)
);

create table if not exists material_manual_review_queue (
    id bigserial primary key,
    sequence integer,
    excel_row integer,
    raw_name text not null,
    standard_name text not null default '',
    item_group_path text not null default '',
    specs_text text not null default '',
    unit text not null default '',
    status text not null default '',
    question text not null default '',
    created_at timestamptz not null default now(),
    unique (excel_row, raw_name)
);

create table if not exists material_non_stock_services (
    id bigserial primary key,
    sequence integer,
    excel_row integer,
    raw_name text not null,
    standard_name text not null default '',
    item_group_path text not null default '',
    specs_text text not null default '',
    unit text not null default '',
    status text not null default '',
    question text not null default '',
    created_at timestamptz not null default now(),
    unique (excel_row, raw_name)
);

alter table material_items add column if not exists canonical_group_path text not null default '';
alter table material_items add column if not exists canonical_level1 text not null default '';
alter table material_items add column if not exists canonical_level2 text;
alter table material_items add column if not exists canonical_level3 text;
alter table material_items add column if not exists group_mapping_confidence numeric(4, 2);
alter table material_items add column if not exists group_mapping_reason text not null default '';
alter table material_items add column if not exists group_needs_human_review boolean not null default false;

create index if not exists idx_material_items_group on material_items(item_group_path);
create index if not exists idx_material_items_canonical_group on material_items(canonical_group_path);
create index if not exists idx_material_items_name_trgm on material_items using gin (standard_name gin_trgm_ops);
create index if not exists idx_material_items_specs_trgm on material_items using gin (specs_text gin_trgm_ops);
create index if not exists idx_material_items_alias_trgm on material_items using gin (alias_names gin_trgm_ops);
create index if not exists idx_material_items_search_trgm on material_items using gin (normalized_search_text gin_trgm_ops);
create index if not exists idx_material_alias_raw_trgm on material_aliases using gin (raw_name gin_trgm_ops);
create index if not exists idx_material_alias_normalized on material_aliases(normalized_raw_name);
create index if not exists idx_material_group_mappings_canonical on material_group_mappings(canonical_group_path);
"""


ITEM_SELECT_SQL = """
select
    proposed_item_code as name,
    proposed_item_code as item_code,
    standard_name as item_name,
    coalesce(nullif(canonical_group_path, ''), item_group_path) as item_group,
    unit as stock_uom,
    specs_text as specification,
    specs_text as material,
    specs_text as standard,
    specs_text as brand,
    specs_text as model,
    specs_text as package_spec,
    alias_names as raw_name,
    alias_names,
    disabled,
    item_group_path as reviewed_group_path,
    canonical_group_path,
    canonical_level1,
    canonical_level2,
    canonical_level3,
    group_mapping_confidence,
    group_mapping_reason,
    group_needs_human_review
from material_items
"""


@dataclass(frozen=True)
class CatalogPaths:
    catalog: Path
    aliases: Path
    manual_review: Path
    services: Path
    group_mapping: Path

    @classmethod
    def from_dir(cls, directory: str | Path) -> "CatalogPaths":
        base = Path(directory)
        return cls(
            catalog=base / "standard_item_catalog_from_review.csv",
            aliases=base / "item_aliases_from_review.csv",
            manual_review=base / "manual_review_queue_from_review.csv",
            services=base / "non_stock_services_from_review.csv",
            group_mapping=base / "material_group_canonical_mapping.csv",
        )


@dataclass(frozen=True)
class CatalogToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    error_type: str | None = None


class PostgresMaterialCatalog:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - exercised only without dependency installed
            raise RuntimeError("psycopg is required for PostgreSQL material catalog support") from exc
        self._psycopg = psycopg
        self.dsn = dsn

    def connect(self):
        return self._psycopg.connect(self.dsn)

    def setup_schema(self) -> None:
        with self.connect() as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()

    def import_review_catalog(self, paths: CatalogPaths) -> dict[str, int]:
        self.setup_schema()
        counts = {"groups": 0, "group_mappings": 0, "items": 0, "aliases": 0, "manual_review": 0, "services": 0}
        group_mappings = read_group_mappings(paths.group_mapping)

        with self.connect() as conn:
            groups = sorted({row["item_group"] for row in read_csv(paths.catalog)} | {row["item_group"] for row in read_csv(paths.aliases)})
            for group_path in groups:
                if not group_path:
                    continue
                levels = split_group_path(group_path)
                conn.execute(
                    """
                    insert into material_groups (path, level1, level2, level3, parent_path)
                    values (%s, %s, %s, %s, %s)
                    on conflict (path) do update set
                        level1 = excluded.level1,
                        level2 = excluded.level2,
                        level3 = excluded.level3,
                        parent_path = excluded.parent_path
                    """,
                    (group_path, levels[0], levels[1], levels[2], parent_group_path(group_path)),
                )
                counts["groups"] += 1

            for mapping in group_mappings.values():
                conn.execute(
                    """
                    insert into material_group_mappings (
                        reviewed_group_path, canonical_group_path, canonical_level1,
                        canonical_level2, canonical_level3, confidence, rule_reason,
                        needs_human_review, updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (reviewed_group_path) do update set
                        canonical_group_path = excluded.canonical_group_path,
                        canonical_level1 = excluded.canonical_level1,
                        canonical_level2 = excluded.canonical_level2,
                        canonical_level3 = excluded.canonical_level3,
                        confidence = excluded.confidence,
                        rule_reason = excluded.rule_reason,
                        needs_human_review = excluded.needs_human_review,
                        updated_at = now()
                    """,
                    (
                        mapping["reviewed_group_path"],
                        mapping["canonical_group_path"],
                        mapping["canonical_level1"],
                        mapping["canonical_level2"],
                        mapping["canonical_level3"],
                        float(mapping["confidence"] or 0),
                        mapping["rule_reason"],
                        parse_bool(mapping["needs_human_review"]),
                    ),
                )
                counts["group_mappings"] += 1

            for row in read_csv(paths.catalog):
                mapping = group_mappings.get(row["item_group"]) or fallback_group_mapping(row["item_group"])
                search_text = normalize_search_text(
                    " ".join(
                        [
                            row["proposed_item_code"],
                            row["standard_name"],
                            row["item_group"],
                            mapping["canonical_group_path"],
                            row["specs"],
                            row["unit"],
                            row["alias_names"],
                            row["notes"],
                        ]
                    )
                )
                conn.execute(
                    """
                    insert into material_items (
                        proposed_item_code, standard_name, item_group_path,
                        canonical_group_path, canonical_level1, canonical_level2,
                        canonical_level3, group_mapping_confidence, group_mapping_reason,
                        group_needs_human_review, specs_text, unit, source_count,
                        source_statuses, alias_names, source_rows, notes,
                        normalized_search_text, updated_at
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                    on conflict (proposed_item_code) do update set
                        standard_name = excluded.standard_name,
                        item_group_path = excluded.item_group_path,
                        canonical_group_path = excluded.canonical_group_path,
                        canonical_level1 = excluded.canonical_level1,
                        canonical_level2 = excluded.canonical_level2,
                        canonical_level3 = excluded.canonical_level3,
                        group_mapping_confidence = excluded.group_mapping_confidence,
                        group_mapping_reason = excluded.group_mapping_reason,
                        group_needs_human_review = excluded.group_needs_human_review,
                        specs_text = excluded.specs_text,
                        unit = excluded.unit,
                        source_count = excluded.source_count,
                        source_statuses = excluded.source_statuses,
                        alias_names = excluded.alias_names,
                        source_rows = excluded.source_rows,
                        notes = excluded.notes,
                        normalized_search_text = excluded.normalized_search_text,
                        updated_at = now()
                    """,
                    (
                        row["proposed_item_code"],
                        row["standard_name"],
                        row["item_group"],
                        mapping["canonical_group_path"],
                        mapping["canonical_level1"],
                        mapping["canonical_level2"],
                        mapping["canonical_level3"],
                        float(mapping["confidence"] or 0),
                        mapping["rule_reason"],
                        parse_bool(mapping["needs_human_review"]),
                        row["specs"],
                        row["unit"],
                        int(row.get("source_count") or 0),
                        row["source_statuses"],
                        row["alias_names"],
                        row["source_rows"],
                        row["notes"],
                        search_text,
                    ),
                )
                counts["items"] += 1

            for row in read_csv(paths.aliases):
                conn.execute(
                    """
                    insert into material_aliases (
                        raw_name, normalized_raw_name, proposed_item_code, standard_name,
                        item_group_path, specs_text, unit
                    )
                    values (%s, %s, %s, %s, %s, %s, %s)
                    on conflict (normalized_raw_name, proposed_item_code) do update set
                        raw_name = excluded.raw_name,
                        standard_name = excluded.standard_name,
                        item_group_path = excluded.item_group_path,
                        specs_text = excluded.specs_text,
                        unit = excluded.unit
                    """,
                    (
                        row["raw_name"],
                        normalize_search_text(row["raw_name"]),
                        row["proposed_item_code"],
                        row["standard_name"],
                        row["item_group"],
                        row["specs"],
                        row["unit"],
                    ),
                )
                counts["aliases"] += 1

            counts["manual_review"] = import_queue(conn, "material_manual_review_queue", paths.manual_review)
            counts["services"] = import_queue(conn, "material_non_stock_services", paths.services)
            conn.commit()

        return counts


class PostgresCatalogSearchClient:
    """Adapter that lets MaterialSearch query the PostgreSQL review catalog."""

    def __init__(self, dsn: str) -> None:
        self.catalog = PostgresMaterialCatalog(dsn)

    def get_document(self, doctype: str, name: str) -> ToolResult:
        if doctype != "Item":
            return CatalogToolResult(ok=False, error_type="unsupported_tool", error=f"unsupported doctype: {doctype}")
        with self.catalog.connect() as conn:
            row = conn.execute(
                ITEM_SELECT_SQL + " where proposed_item_code = %s limit 1",
                (name,),
            ).fetchone()
        if not row:
            return CatalogToolResult(ok=False, error_type="not_found", error=f"material item not found: {name}")
        return CatalogToolResult(ok=True, data=dict_from_row(row))

    def search_documents(
        self,
        doctype: str,
        *,
        filters: dict[str, Any] | list[Any] | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
    ) -> ToolResult:
        if doctype != "Item":
            return CatalogToolResult(ok=False, error_type="unsupported_tool", error=f"unsupported doctype: {doctype}")

        where_sql, params = build_filter_sql(filters or [])
        sql = ITEM_SELECT_SQL
        if where_sql:
            sql += f" where {where_sql}"
        sql += " order by source_count desc, proposed_item_code asc limit %s offset %s"
        params.extend([limit, offset])

        with self.catalog.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return CatalogToolResult(ok=True, data=[dict_from_row(row) for row in rows])


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: value or "" for key, value in row.items()} for row in csv.DictReader(handle)]


def read_group_mappings(path: Path) -> dict[str, dict[str, str]]:
    mappings: dict[str, dict[str, str]] = {}
    for row in read_csv(path):
        reviewed = row.get("reviewed_group_path") or ""
        if reviewed:
            mappings[reviewed] = {
                "reviewed_group_path": reviewed,
                "canonical_group_path": row.get("canonical_group_path") or reviewed,
                "canonical_level1": row.get("canonical_level1") or split_group_path(reviewed)[0],
                "canonical_level2": row.get("canonical_level2") or "",
                "canonical_level3": row.get("canonical_level3") or "",
                "confidence": row.get("confidence") or "0",
                "rule_reason": row.get("rule_reason") or "",
                "needs_human_review": row.get("needs_human_review") or "true",
            }
    return mappings


def fallback_group_mapping(group_path: str) -> dict[str, str]:
    level1, level2, level3 = split_group_path(group_path)
    return {
        "reviewed_group_path": group_path,
        "canonical_group_path": group_path,
        "canonical_level1": level1,
        "canonical_level2": level2 or "",
        "canonical_level3": level3 or "",
        "confidence": "0",
        "rule_reason": "未找到 canonical 映射，保留原始 reviewed group",
        "needs_human_review": "true",
    }


def parse_bool(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def split_group_path(path: str) -> tuple[str, str | None, str | None]:
    parts = [part.strip() for part in path.split("/") if part.strip()]
    parts = [*parts, None, None]
    return parts[0] or "未分类", parts[1], parts[2]


def parent_group_path(path: str) -> str | None:
    parts = [part.strip() for part in path.split("/") if part.strip()]
    if len(parts) <= 1:
        return None
    return "/".join(parts[:-1])


def normalize_search_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("×", "*").replace("＊", "*")
    return re.sub(r"\s+", "", text)


def import_queue(conn: Any, table: str, path: Path) -> int:
    count = 0
    for row in read_csv(path):
        conn.execute(
            f"""
            insert into {table} (
                sequence, excel_row, raw_name, standard_name, item_group_path,
                specs_text, unit, status, question
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (excel_row, raw_name) do update set
                standard_name = excluded.standard_name,
                item_group_path = excluded.item_group_path,
                specs_text = excluded.specs_text,
                unit = excluded.unit,
                status = excluded.status,
                question = excluded.question
            """,
            (
                as_int(row.get("sequence")),
                as_int(row.get("excel_row")),
                row.get("raw_name") or "",
                row.get("standard_name") or "",
                row.get("item_group") or "",
                row.get("specs") or "",
                row.get("unit") or "",
                row.get("status") or "",
                row.get("question") or "",
            ),
        )
        count += 1
    return count


def as_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def build_filter_sql(filters: Iterable[Any]) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    for filter_row in filters:
        if not isinstance(filter_row, list | tuple) or len(filter_row) < 3:
            continue
        field, operator, value = filter_row[:3]
        if field == "disabled" and operator == "=":
            clauses.append("disabled = %s")
            params.append(bool(value))
            continue

        column = column_for_search_field(str(field))
        if operator == "like":
            needle = str(value).replace("%", "")
            clauses.append(f"({column} ilike %s or normalized_search_text ilike %s)")
            params.extend([f"%{needle}%", f"%{normalize_search_text(needle)}%"])
        elif operator == "=":
            clauses.append(f"{column} = %s")
            params.append(value)

    return " and ".join(clauses), params


def column_for_search_field(field: str) -> str:
    return {
        "name": "proposed_item_code",
        "item_code": "proposed_item_code",
        "item_name": "standard_name",
        "item_group": "item_group_path",
        "stock_uom": "unit",
        "specification": "specs_text",
        "material": "specs_text",
        "standard": "specs_text",
        "brand": "specs_text",
        "model": "specs_text",
        "package_spec": "specs_text",
        "raw_name": "alias_names",
        "alias_names": "alias_names",
        "canonical_group_path": "canonical_group_path",
        "reviewed_group_path": "item_group_path",
    }.get(field, "normalized_search_text")


def dict_from_row(row: Any) -> dict[str, Any]:
    if hasattr(row, "_asdict"):
        return dict(row._asdict())
    if isinstance(row, dict):
        return {key: json_safe_value(value) for key, value in row.items()}
    keys = [
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
        "reviewed_group_path",
        "canonical_group_path",
        "canonical_level1",
        "canonical_level2",
        "canonical_level3",
        "group_mapping_confidence",
        "group_mapping_reason",
        "group_needs_human_review",
    ]
    return {key: json_safe_value(value) for key, value in zip(keys, row, strict=False)}


def json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value
