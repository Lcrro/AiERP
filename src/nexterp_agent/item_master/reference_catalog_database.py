"""SQLite-backed runtime store for the internal reference-catalog workbench.

The imported JSON/JSONL artifacts remain reproducible source packages and
compatibility exports.  The workbench reads this database once it has been
initialized, so taxonomy and material edits are data changes rather than page
code changes.  Official GPC rows remain distinguishable from explicit
Nexterp-only extensions through ``is_gpc`` and ``classification_source``.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from .procurement_templates import ProcurementTemplateCatalog, ProcurementTemplateRegistry
from .reference_catalog import GPC_KIND_ORDER, GpcReferenceIndex


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REFERENCE_CATALOG_DATABASE_PATH = (
    ROOT / ".runtime" / "material-master" / "reference-catalog.sqlite3"
)
DEFAULT_TEMPLATE_CATALOG_PATH = (
    ROOT / "data" / "material_master" / "procurement_template_catalog_v0_1.json"
)
DATABASE_SCHEMA_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not Path(path).is_file():
        return []
    with Path(path).open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class ReferenceCatalogDatabase:
    """Own the local SQLite representation of the GPC workbench."""

    def __init__(self, path: Path = DEFAULT_REFERENCE_CATALOG_DATABASE_PATH) -> None:
        self.path = Path(path).resolve()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS catalog_state (
                    catalog TEXT PRIMARY KEY,
                    schema_version INTEGER NOT NULL,
                    source_version TEXT NOT NULL,
                    revision INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    source_meta_json TEXT NOT NULL DEFAULT '{}',
                    bulk_mode INTEGER NOT NULL DEFAULT 0 CHECK (bulk_mode IN (0, 1))
                );

                CREATE TABLE IF NOT EXISTS catalog_nodes (
                    catalog TEXT NOT NULL,
                    code TEXT NOT NULL,
                    parent_code TEXT,
                    kind TEXT NOT NULL,
                    level INTEGER NOT NULL,
                    official_name TEXT NOT NULL DEFAULT '',
                    working_name TEXT NOT NULL,
                    source TEXT NOT NULL,
                    is_gpc INTEGER NOT NULL CHECK (is_gpc IN (0, 1)),
                    translation_status TEXT NOT NULL DEFAULT 'missing',
                    translation_source_hash TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (catalog, code),
                    FOREIGN KEY (catalog, parent_code)
                        REFERENCES catalog_nodes(catalog, code)
                        ON UPDATE CASCADE ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS catalog_nodes_parent_idx
                    ON catalog_nodes(catalog, parent_code, level, code);

                CREATE TABLE IF NOT EXISTS catalog_profiles (
                    catalog TEXT NOT NULL,
                    node_code TEXT NOT NULL,
                    definition_official TEXT NOT NULL DEFAULT '',
                    definition_working TEXT NOT NULL DEFAULT '',
                    definition_status TEXT NOT NULL DEFAULT 'missing',
                    includes_official TEXT NOT NULL DEFAULT '',
                    includes_working TEXT NOT NULL DEFAULT '',
                    includes_status TEXT NOT NULL DEFAULT 'missing',
                    excludes_official TEXT NOT NULL DEFAULT '',
                    excludes_working TEXT NOT NULL DEFAULT '',
                    excludes_status TEXT NOT NULL DEFAULT 'missing',
                    classification_source TEXT NOT NULL,
                    PRIMARY KEY (catalog, node_code),
                    FOREIGN KEY (catalog, node_code)
                        REFERENCES catalog_nodes(catalog, code)
                        ON UPDATE CASCADE ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS catalog_attributes (
                    catalog TEXT NOT NULL,
                    node_code TEXT NOT NULL,
                    code TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    official_name TEXT NOT NULL DEFAULT '',
                    working_name TEXT NOT NULL,
                    definition_official TEXT NOT NULL DEFAULT '',
                    definition_working TEXT NOT NULL DEFAULT '',
                    translation_status TEXT NOT NULL DEFAULT 'missing',
                    PRIMARY KEY (catalog, node_code, code),
                    FOREIGN KEY (catalog, node_code)
                        REFERENCES catalog_nodes(catalog, code)
                        ON UPDATE CASCADE ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS catalog_attributes_code_idx
                    ON catalog_attributes(catalog, code);

                CREATE TABLE IF NOT EXISTS catalog_attribute_values (
                    catalog TEXT NOT NULL,
                    node_code TEXT NOT NULL,
                    attribute_code TEXT NOT NULL,
                    code TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    official_name TEXT NOT NULL DEFAULT '',
                    working_name TEXT NOT NULL,
                    definition_official TEXT NOT NULL DEFAULT '',
                    definition_working TEXT NOT NULL DEFAULT '',
                    translation_status TEXT NOT NULL DEFAULT 'missing',
                    PRIMARY KEY (catalog, node_code, attribute_code, code),
                    FOREIGN KEY (catalog, node_code, attribute_code)
                        REFERENCES catalog_attributes(catalog, node_code, code)
                        ON UPDATE CASCADE ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS catalog_attribute_values_code_idx
                    ON catalog_attribute_values(catalog, code);

                CREATE TABLE IF NOT EXISTS material_placements (
                    material_id TEXT PRIMARY KEY,
                    catalog TEXT NOT NULL,
                    node_code TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (catalog, node_code)
                        REFERENCES catalog_nodes(catalog, code)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS material_placements_node_idx
                    ON material_placements(catalog, node_code, material_id);

                CREATE TABLE IF NOT EXISTS procurement_type_profiles (
                    profile_id TEXT PRIMARY KEY,
                    catalog TEXT NOT NULL,
                    node_code TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (catalog, node_code)
                        REFERENCES catalog_nodes(catalog, code)
                        ON UPDATE CASCADE ON DELETE RESTRICT
                );
                CREATE INDEX IF NOT EXISTS procurement_type_profiles_node_idx
                    ON procurement_type_profiles(catalog, node_code, profile_id);

                CREATE TABLE IF NOT EXISTS catalog_change_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    catalog TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    changed_at TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    detail_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS catalog_change_log_revision_idx
                    ON catalog_change_log(catalog, revision);
                """
            )
            tracked_tables = (
                "catalog_nodes",
                "catalog_profiles",
                "catalog_attributes",
                "catalog_attribute_values",
                "material_placements",
                "procurement_type_profiles",
            )
            for table in tracked_tables:
                for operation, row_alias in (("insert", "NEW"), ("update", "NEW"), ("delete", "OLD")):
                    connection.executescript(
                        f"""
                        CREATE TRIGGER IF NOT EXISTS {table}_{operation}_revision
                        AFTER {operation.upper()} ON {table}
                        WHEN COALESCE((
                            SELECT bulk_mode FROM catalog_state
                            WHERE catalog = {row_alias}.catalog
                        ), 0) = 0
                        BEGIN
                            UPDATE catalog_state
                            SET revision = revision + 1,
                                updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                            WHERE catalog = {row_alias}.catalog;
                        END;
                        """
                    )

    def is_ready(self, catalog: str = "gpc") -> bool:
        if not self.path.is_file():
            return False
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM catalog_state WHERE catalog = ? AND bulk_mode = 0",
                (_text(catalog).lower(),),
            ).fetchone()
        return row is not None

    def revision(self, catalog: str = "gpc") -> dict[str, Any]:
        normalized = _text(catalog).lower()
        if not self.path.is_file():
            return {"catalog": normalized, "available": False, "storage": "sqlite"}
        self.initialize()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT schema_version, source_version, revision, updated_at
                FROM catalog_state WHERE catalog = ? AND bulk_mode = 0
                """,
                (normalized,),
            ).fetchone()
        if row is None:
            return {"catalog": normalized, "available": False, "storage": "sqlite"}
        return {
            "catalog": normalized,
            "available": True,
            "storage": "sqlite",
            "schema_version": int(row["schema_version"]),
            "source_version": row["source_version"],
            "revision": int(row["revision"]),
            "updated_at": row["updated_at"],
            "database_path": str(self.path),
        }

    def sync_from_runtime(
        self,
        runtime_root: Path,
        version: str,
        *,
        material_placements_path: Path | None = None,
        procurement_template_catalog_path: Path = DEFAULT_TEMPLATE_CATALOG_PATH,
        procurement_type_profiles_path: Path | None = None,
        internal_extensions_path: Path | None = None,
    ) -> dict[str, Any]:
        """Validate the file package, then replace one catalog atomically."""

        index = GpcReferenceIndex.from_runtime(
            runtime_root,
            version,
            material_placements_path=material_placements_path,
            procurement_template_catalog_path=procurement_template_catalog_path,
            procurement_type_profiles_path=procurement_type_profiles_path,
            internal_extensions_path=internal_extensions_path,
        )
        issues = index.validate()
        if issues:
            raise ValueError(f"GPC 目录数据库导入前校验失败：{issues[0]}")
        type_profiles = _load_jsonl(procurement_type_profiles_path)
        stamp = _now()
        self.initialize()
        with self._connect() as connection:
            current = connection.execute(
                "SELECT revision FROM catalog_state WHERE catalog = 'gpc'"
            ).fetchone()
            next_revision = int(current["revision"] if current else 0) + 1
            connection.execute(
                """
                INSERT INTO catalog_state(
                    catalog, schema_version, source_version, revision,
                    updated_at, source_meta_json, bulk_mode
                ) VALUES ('gpc', ?, ?, ?, ?, ?, 1)
                ON CONFLICT(catalog) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    source_version = excluded.source_version,
                    updated_at = excluded.updated_at,
                    source_meta_json = excluded.source_meta_json,
                    bulk_mode = 1
                """,
                (
                    DATABASE_SCHEMA_VERSION,
                    version,
                    next_revision,
                    stamp,
                    json.dumps(index.source_meta, ensure_ascii=False, sort_keys=True),
                ),
            )
            for table in (
                "material_placements",
                "procurement_type_profiles",
                "catalog_attribute_values",
                "catalog_attributes",
                "catalog_profiles",
                "catalog_nodes",
            ):
                connection.execute(f"DELETE FROM {table} WHERE catalog = 'gpc'")

            nodes = sorted(
                index._nodes.values(),  # noqa: SLF001 - owned in-package validated projection
                key=lambda row: (int(row.get("level", 0)), _text(row.get("code"))),
            )
            connection.executemany(
                """
                INSERT INTO catalog_nodes(
                    catalog, code, parent_code, kind, level, official_name,
                    working_name, source, is_gpc, translation_status,
                    translation_source_hash
                ) VALUES ('gpc', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        _text(node.get("code")),
                        _text(node.get("parent_code")) or None,
                        _text(node.get("kind")),
                        int(node.get("level", 0)),
                        _text(node.get("official_name")),
                        _text(node.get("working_name") or node.get("name")),
                        _text(node.get("source")),
                        1 if node.get("is_gpc", True) else 0,
                        _text(node.get("translation_status")),
                        _text(node.get("translation_source_hash")),
                    )
                    for node in nodes
                ],
            )

            for code, profile in sorted(index._profiles.items()):  # noqa: SLF001
                node = index._nodes.get(code, {})  # noqa: SLF001
                is_gpc = bool(node.get("is_gpc", True))
                profile_fields: dict[str, tuple[str, str, str]] = {}
                for field in ("definition", "includes", "excludes"):
                    if is_gpc:
                        official = _text(profile.get(field))
                        working, status = index._profile_text_translation(official)  # noqa: SLF001
                    else:
                        official = ""
                        working = _text(profile.get(f"{field}_working"))
                        status = "human_confirmed"
                    profile_fields[field] = (official, working, status)
                connection.execute(
                    """
                    INSERT INTO catalog_profiles(
                        catalog, node_code,
                        definition_official, definition_working, definition_status,
                        includes_official, includes_working, includes_status,
                        excludes_official, excludes_working, excludes_status,
                        classification_source
                    ) VALUES ('gpc', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code,
                        *profile_fields["definition"],
                        *profile_fields["includes"],
                        *profile_fields["excludes"],
                        "gpc" if is_gpc else "nexterp_internal",
                    ),
                )
                for attribute_position, attribute in enumerate(profile.get("attributes") or []):
                    attribute_code = _text(attribute.get("code"))
                    official_name = _text(attribute.get("name")) if is_gpc else ""
                    if is_gpc:
                        working_name, status = index._profile_term_translation(  # noqa: SLF001
                            attribute_code, official_name
                        )
                    else:
                        working_name = _text(attribute.get("working_name") or attribute.get("name"))
                        status = "human_confirmed"
                    definition = _text(attribute.get("definition"))
                    connection.execute(
                        """
                        INSERT INTO catalog_attributes(
                            catalog, node_code, code, position, official_name,
                            working_name, definition_official, definition_working,
                            translation_status
                        ) VALUES ('gpc', ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            code,
                            attribute_code,
                            attribute_position,
                            official_name,
                            working_name,
                            definition if is_gpc else "",
                            "" if is_gpc else definition,
                            status,
                        ),
                    )
                    for value_position, value in enumerate(attribute.get("values") or []):
                        value_code = _text(value.get("code"))
                        value_official = _text(value.get("name")) if is_gpc else ""
                        if is_gpc:
                            value_working, value_status = index._profile_term_translation(  # noqa: SLF001
                                value_code, value_official
                            )
                        else:
                            value_working = _text(value.get("working_name") or value.get("name"))
                            value_status = "human_confirmed"
                        value_definition = _text(value.get("definition"))
                        connection.execute(
                            """
                            INSERT INTO catalog_attribute_values(
                                catalog, node_code, attribute_code, code, position,
                                official_name, working_name, definition_official,
                                definition_working, translation_status
                            ) VALUES ('gpc', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                code,
                                attribute_code,
                                value_code,
                                value_position,
                                value_official,
                                value_working,
                                value_definition if is_gpc else "",
                                "" if is_gpc else value_definition,
                                value_status,
                            ),
                        )

            self._replace_material_rows(
                connection,
                index._material_placements,  # noqa: SLF001
                type_profiles,
                stamp,
            )
            connection.execute(
                """
                UPDATE catalog_state SET revision = ?, updated_at = ?, bulk_mode = 0
                WHERE catalog = 'gpc'
                """,
                (next_revision, stamp),
            )
            connection.execute(
                """
                INSERT INTO catalog_change_log(catalog, revision, changed_at, operation, detail_json)
                VALUES ('gpc', ?, ?, 'full_sync', ?)
                """,
                (
                    next_revision,
                    stamp,
                    json.dumps(
                        {
                            "node_count": len(nodes),
                            "material_count": len(index._material_placements),  # noqa: SLF001
                            "type_profile_count": len(type_profiles),
                            "version": version,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
            )
        loaded = self.load_gpc_index(procurement_template_catalog_path)
        summary = loaded.summary()
        if summary["browsable_total_nodes"] != len(index._nodes):  # noqa: SLF001
            raise ValueError("目录数据库回读节点数不一致")
        if summary["actual_material_count"] != len(index._material_placements):  # noqa: SLF001
            raise ValueError("目录数据库回读物料数不一致")
        return {**self.revision("gpc"), "summary": summary}

    @staticmethod
    def _replace_material_rows(
        connection: sqlite3.Connection,
        materials: Iterable[Mapping[str, Any]],
        type_profiles: Iterable[Mapping[str, Any]],
        stamp: str,
    ) -> None:
        connection.execute("DELETE FROM material_placements WHERE catalog = 'gpc'")
        connection.execute("DELETE FROM procurement_type_profiles WHERE catalog = 'gpc'")
        for material in materials:
            row = dict(material)
            connection.execute(
                """
                INSERT INTO material_placements(material_id, catalog, node_code, payload_json, updated_at)
                VALUES (?, 'gpc', ?, ?, ?)
                """,
                (
                    _text(row.get("material_id")),
                    _text(row.get("gpc_brick_code")),
                    json.dumps(row, ensure_ascii=False, sort_keys=True),
                    stamp,
                ),
            )
        for profile in type_profiles:
            row = dict(profile)
            connection.execute(
                """
                INSERT INTO procurement_type_profiles(profile_id, catalog, node_code, payload_json, updated_at)
                VALUES (?, 'gpc', ?, ?, ?)
                """,
                (
                    _text(row.get("profile_id")),
                    _text(row.get("gpc_brick_code")),
                    json.dumps(row, ensure_ascii=False, sort_keys=True),
                    stamp,
                ),
            )

    def replace_material_publication(
        self,
        materials: Iterable[Mapping[str, Any]],
        type_profiles: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Atomically replace published material rows and advance revision once."""

        material_rows = [dict(row) for row in materials]
        profile_rows = [dict(row) for row in type_profiles]
        if not self.is_ready("gpc"):
            raise FileNotFoundError("参考目录数据库尚未初始化")
        stamp = _now()
        with self._connect() as connection:
            state = connection.execute(
                "SELECT revision FROM catalog_state WHERE catalog = 'gpc'"
            ).fetchone()
            next_revision = int(state["revision"]) + 1
            connection.execute("UPDATE catalog_state SET bulk_mode = 1 WHERE catalog = 'gpc'")
            self._replace_material_rows(connection, material_rows, profile_rows, stamp)
            connection.execute(
                """
                UPDATE catalog_state SET revision = ?, updated_at = ?, bulk_mode = 0
                WHERE catalog = 'gpc'
                """,
                (next_revision, stamp),
            )
            connection.execute(
                """
                INSERT INTO catalog_change_log(catalog, revision, changed_at, operation, detail_json)
                VALUES ('gpc', ?, ?, 'material_publication', ?)
                """,
                (
                    next_revision,
                    stamp,
                    json.dumps(
                        {
                            "material_count": len(material_rows),
                            "type_profile_count": len(profile_rows),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                ),
            )
        return self.revision("gpc")

    def load_gpc_index(
        self,
        procurement_template_catalog_path: Path = DEFAULT_TEMPLATE_CATALOG_PATH,
        *,
        material_placements: Iterable[Mapping[str, Any]] | None = None,
        procurement_type_profiles: Iterable[Mapping[str, Any]] | None = None,
    ) -> GpcReferenceIndex:
        """Reconstruct the established read-only index from normalized rows."""

        if not self.is_ready("gpc"):
            raise FileNotFoundError("参考目录数据库尚未初始化")
        with self._connect() as connection:
            state = connection.execute(
                "SELECT source_meta_json FROM catalog_state WHERE catalog = 'gpc'"
            ).fetchone()
            node_rows = connection.execute(
                "SELECT * FROM catalog_nodes WHERE catalog = 'gpc' ORDER BY level, code"
            ).fetchall()
            profile_rows = {
                row["node_code"]: row
                for row in connection.execute(
                    "SELECT * FROM catalog_profiles WHERE catalog = 'gpc'"
                ).fetchall()
            }
            attribute_rows: dict[str, list[sqlite3.Row]] = {}
            for row in connection.execute(
                "SELECT * FROM catalog_attributes WHERE catalog = 'gpc' ORDER BY node_code, position, code"
            ).fetchall():
                attribute_rows.setdefault(row["node_code"], []).append(row)
            value_rows: dict[tuple[str, str], list[sqlite3.Row]] = {}
            for row in connection.execute(
                """
                SELECT * FROM catalog_attribute_values WHERE catalog = 'gpc'
                ORDER BY node_code, attribute_code, position, code
                """
            ).fetchall():
                value_rows.setdefault((row["node_code"], row["attribute_code"]), []).append(row)
            stored_materials = [
                json.loads(row["payload_json"])
                for row in connection.execute(
                    "SELECT payload_json FROM material_placements WHERE catalog = 'gpc' ORDER BY material_id"
                ).fetchall()
            ]
            stored_type_profiles = [
                json.loads(row["payload_json"])
                for row in connection.execute(
                    "SELECT payload_json FROM procurement_type_profiles WHERE catalog = 'gpc' ORDER BY profile_id"
                ).fetchall()
            ]

        nodes: list[dict[str, Any]] = []
        translations: list[dict[str, Any]] = []
        profiles: list[dict[str, Any]] = []
        profile_translations: dict[tuple[str, str], dict[str, Any]] = {}
        profile_text_translations: dict[str, dict[str, Any]] = {}
        internal_extensions: list[dict[str, Any]] = []

        for row in node_rows:
            code = row["code"]
            if row["is_gpc"]:
                nodes.append(
                    {
                        "code": code,
                        "kind": row["kind"],
                        "level": int(row["level"]),
                        "name": row["official_name"],
                        "official_name": row["official_name"],
                        "parent_code": row["parent_code"],
                        "source": row["source"],
                    }
                )
                translations.append(
                    {
                        "code": code,
                        "working_name": row["working_name"],
                        "status": row["translation_status"],
                        "source_hash": row["translation_source_hash"] or _source_hash(row["official_name"]),
                    }
                )

        for row in node_rows:
            code = row["code"]
            profile = profile_rows.get(code)
            attributes: list[dict[str, Any]] = []
            for attribute in attribute_rows.get(code, []):
                values: list[dict[str, Any]] = []
                for value in value_rows.get((code, attribute["code"]), []):
                    if row["is_gpc"]:
                        value_name = value["official_name"]
                        profile_translations[(value["code"], value_name)] = {
                            "code": value["code"],
                            "kind": "attribute_value",
                            "official_name": value_name,
                            "working_name": value["working_name"],
                            "source_hash": _source_hash(value_name),
                            "status": value["translation_status"],
                        }
                    else:
                        value_name = value["working_name"]
                    values.append(
                        {
                            "code": value["code"],
                            "name": value_name,
                            "working_name": value["working_name"],
                            "definition": value["definition_official"] or value["definition_working"],
                        }
                    )
                if row["is_gpc"]:
                    attribute_name = attribute["official_name"]
                    profile_translations[(attribute["code"], attribute_name)] = {
                        "code": attribute["code"],
                        "kind": "attribute",
                        "official_name": attribute_name,
                        "working_name": attribute["working_name"],
                        "source_hash": _source_hash(attribute_name),
                        "status": attribute["translation_status"],
                    }
                else:
                    attribute_name = attribute["working_name"]
                attributes.append(
                    {
                        "code": attribute["code"],
                        "name": attribute_name,
                        "working_name": attribute["working_name"],
                        "definition": attribute["definition_official"] or attribute["definition_working"],
                        "values": values,
                    }
                )
            if row["is_gpc"]:
                profile_payload = {
                    "code": code,
                    "kind": row["kind"],
                    "official_name": row["official_name"],
                    "definition": profile["definition_official"] if profile else "",
                    "includes": profile["includes_official"] if profile else "",
                    "excludes": profile["excludes_official"] if profile else "",
                    "attributes": attributes,
                }
                profiles.append(profile_payload)
                if profile:
                    for field in ("definition", "includes", "excludes"):
                        official = profile[f"{field}_official"]
                        if not official:
                            continue
                        source_hash = _source_hash(official)
                        profile_text_translations[source_hash] = {
                            "id": f"T{source_hash[:24]}",
                            "official_text": official,
                            "working_text": profile[f"{field}_working"],
                            "source_hash": source_hash,
                            "status": profile[f"{field}_status"],
                        }
            else:
                internal_extensions.append(
                    {
                        "code": code,
                        "parent_code": row["parent_code"],
                        "kind": row["kind"],
                        "level": int(row["level"]),
                        "working_name": row["working_name"],
                        "definition_working": profile["definition_working"] if profile else "",
                        "includes_working": profile["includes_working"] if profile else "",
                        "excludes_working": profile["excludes_working"] if profile else "",
                        "attributes": attributes,
                    }
                )

        selected_materials = stored_materials if material_placements is None else [dict(row) for row in material_placements]
        selected_profiles = stored_type_profiles if procurement_type_profiles is None else [dict(row) for row in procurement_type_profiles]
        catalog = ProcurementTemplateCatalog.model_validate(
            json.loads(Path(procurement_template_catalog_path).read_text(encoding="utf-8"))
        )
        registry = ProcurementTemplateRegistry(catalog, selected_profiles)
        source_meta = json.loads(state["source_meta_json"] or "{}")
        source_meta["database"] = self.revision("gpc")
        return GpcReferenceIndex(
            nodes,
            profiles,
            translations,
            profile_translations.values(),
            profile_text_translations.values(),
            selected_materials,
            registry,
            internal_extensions=internal_extensions,
            source_meta=source_meta,
            source_path=self.path,
        )


__all__ = [
    "DATABASE_SCHEMA_VERSION",
    "DEFAULT_REFERENCE_CATALOG_DATABASE_PATH",
    "ReferenceCatalogDatabase",
]
