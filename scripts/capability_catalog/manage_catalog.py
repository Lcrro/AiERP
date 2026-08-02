from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from nexterp_agent.capability_service.catalog import CapabilityCatalogRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the Nexterp capability manual catalog")
    parser.add_argument("command", choices=("migrate", "export", "bind-identity"))
    parser.add_argument("--database-url", default="")
    parser.add_argument("--output", default="docs/generated/capability-manual.md")
    parser.add_argument("--external-subject", default="")
    parser.add_argument("--agent-id", default="")
    parser.add_argument("--employee-user", default="")
    parser.add_argument("--profile", default="material_clerk_agent")
    parser.add_argument("--project", default="")
    args = parser.parse_args()
    load_dotenv()
    repository = CapabilityCatalogRepository(
        args.database_url or os.getenv("MATERIAL_CATALOG_DATABASE_URL") or ""
    )
    revision = repository.migrate()
    if args.command == "migrate":
        print(revision)
    elif args.command == "export":
        output = Path(args.output)
        repository.export_markdown(output)
        print(output.resolve())
    else:
        if not args.external_subject or not args.employee_user:
            parser.error("bind-identity requires --external-subject and --employee-user")
        repository.upsert_identity(
            external_subject=args.external_subject,
            agent_id=args.agent_id,
            employee_user=args.employee_user,
            profile_name=args.profile,
            default_project=args.project,
            allowed_projects=[args.project] if args.project else [],
        )
        print("identity bound")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
