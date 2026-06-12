from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from nexterp_agent.item_master.postgres_catalog import CatalogPaths, PostgresMaterialCatalog


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Import reviewed purchase material catalog into PostgreSQL.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("MATERIAL_CATALOG_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="PostgreSQL DSN. Defaults to MATERIAL_CATALOG_DATABASE_URL or DATABASE_URL.",
    )
    parser.add_argument(
        "--data-dir",
        default="data/material_purchase_2024",
        help="Directory containing *from_review.csv export files.",
    )
    args = parser.parse_args()

    if not args.database_url:
        raise SystemExit("Missing PostgreSQL DSN. Set MATERIAL_CATALOG_DATABASE_URL or pass --database-url.")

    paths = CatalogPaths.from_dir(Path(args.data_dir))
    catalog = PostgresMaterialCatalog(args.database_url)
    result = catalog.import_review_catalog(paths)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
