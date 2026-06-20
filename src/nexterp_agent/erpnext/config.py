from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class ERPNextSettings:
    base_url: str
    api_key: str
    api_secret: str
    host_header: str | None = None


def load_erpnext_settings(profile: str = "remote") -> ERPNextSettings:
    """Load ERPNext connection settings from environment variables.

    Supported profiles are `remote` and `local`; custom profiles can be used by
    defining variables with the matching upper-case prefix.
    """

    load_dotenv()
    prefix = f"NEXTERP_{profile.upper()}"

    base_url = os.getenv(f"{prefix}_BASE_URL")
    api_key = os.getenv(f"{prefix}_API_KEY")
    api_secret = os.getenv(f"{prefix}_API_SECRET")
    host_header = os.getenv(f"{prefix}_HOST_HEADER") or os.getenv("NEXTERP_HOST_HEADER") or None

    missing = [
        name
        for name, value in {
            f"{prefix}_BASE_URL": base_url,
            f"{prefix}_API_KEY": api_key,
            f"{prefix}_API_SECRET": api_secret,
        }.items()
        if not value or value == "replace-me"
    ]

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing ERPNext configuration: {joined}")

    return ERPNextSettings(
        base_url=base_url or "",
        api_key=api_key or "",
        api_secret=api_secret or "",
        host_header=host_header,
    )
