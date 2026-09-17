"""Normalize the local GPC workbench hierarchy and material naming."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.material_catalog_normalization import (  # noqa: E402
    normalize_workbench_catalog,
)
from nexterp_agent.item_master.reference_catalog_database import (  # noqa: E402
    DEFAULT_REFERENCE_CATALOG_DATABASE_PATH,
    ReferenceCatalogDatabase,
)


DEFAULT_MATERIALS = ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl"
DEFAULT_PROFILES = ROOT / ".runtime" / "material-master" / "gpc-procurement-type-profiles.jsonl"
DEFAULT_EXTENSIONS = ROOT / "data" / "material_master" / "gpc_internal_extensions_v0_1.json"
DEFAULT_REPORT = ROOT / ".runtime" / "material-master" / "gpc-workbench-normalization-report.json"


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(dict(row), ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(path)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materials", type=Path, default=DEFAULT_MATERIALS)
    parser.add_argument("--profiles", type=Path, default=DEFAULT_PROFILES)
    parser.add_argument("--extensions", type=Path, default=DEFAULT_EXTENSIONS)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--database", type=Path, default=DEFAULT_REFERENCE_CATALOG_DATABASE_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    extension_payload = json.loads(args.extensions.read_text(encoding="utf-8"))
    materials, profiles, extensions, report = normalize_workbench_catalog(
        _load_jsonl(args.materials),
        _load_jsonl(args.profiles),
        list(extension_payload.get("extensions") or []),
    )
    report["erpnext_written"] = False
    if not args.dry_run:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        temporary_materials = args.materials.with_suffix(".normalize.tmp.jsonl")
        temporary_profiles = args.profiles.with_suffix(".normalize.tmp.jsonl")
        temporary_extensions = args.extensions.with_suffix(".normalize.tmp.json")
        _write_jsonl(temporary_materials, materials)
        _write_jsonl(temporary_profiles, profiles)
        _write_json(temporary_extensions, {**extension_payload, "extensions": extensions})
        database = ReferenceCatalogDatabase(args.database)
        database_result = database.sync_from_runtime(
            ROOT / ".runtime" / "gpc-reference",
            "2026-05",
            material_placements_path=temporary_materials,
            procurement_template_catalog_path=(
                ROOT / "data" / "material_master" / "procurement_template_catalog_v0_1.json"
            ),
            procurement_type_profiles_path=temporary_profiles,
            internal_extensions_path=temporary_extensions,
        )
        backup = args.materials.parent / "publication-backups" / f"normalize-{stamp}"
        backup.mkdir(parents=True, exist_ok=True)
        for path in (args.materials, args.profiles, args.extensions):
            if path.is_file():
                shutil.copy2(path, backup / path.name)
        temporary_materials.replace(args.materials)
        temporary_profiles.replace(args.profiles)
        temporary_extensions.replace(args.extensions)
        report["database_revision"] = database_result.get("revision")
        report["backup_path"] = str(backup)
    _write_json(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
