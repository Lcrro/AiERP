from __future__ import annotations

import re


def next_sequence(prefix: str, existing_codes: list[str]) -> int:
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    numbers = []
    for code in existing_codes:
        match = pattern.match(code)
        if match:
            numbers.append(int(match.group(1)))
    return (max(numbers) + 1) if numbers else 1


def generate_next_item_code(prefix: str, existing_codes: list[str], *, width: int = 6) -> str:
    return f"{prefix}-{next_sequence(prefix, existing_codes):0{width}d}"
