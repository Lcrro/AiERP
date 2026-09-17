"""Build or inspect the local SQLite reference-catalog database."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.item_master.reference_catalog_database import (  # noqa: E402
    DEFAULT_REFERENCE_CATALOG_DATABASE_PATH,
    ReferenceCatalogDatabase,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="2026-05", help="GPC fixed version (YYYY-MM)")
    parser.add_argument(
        "--database",
        type=Path,
        default=DEFAULT_REFERENCE_CATALOG_DATABASE_PATH,
        help="Local SQLite database path",
    )
    parser.add_argument("--status", action="store_true", help="Only print database revision/status")
    args = parser.parse_args()

    database = ReferenceCatalogDatabase(args.database)
    if args.status:
        payload = database.revision("gpc")
    else:
        payload = database.sync_from_runtime(
            ROOT / ".runtime" / "gpc-reference",
            args.version,
            material_placements_path=(
                ROOT / ".runtime" / "material-master" / "gpc-material-placements.jsonl"
            ),
            procurement_template_catalog_path=(
                ROOT / "data" / "material_master" / "procurement_template_catalog_v0_1.json"
            ),
            procurement_type_profiles_path=(
                ROOT / ".runtime" / "material-master" / "gpc-procurement-type-profiles.jsonl"
            ),
            internal_extensions_path=(
                ROOT / "data" / "material_master" / "gpc_internal_extensions_v0_1.json"
            ),
        )
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
