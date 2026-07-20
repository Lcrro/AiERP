from __future__ import annotations

from pathlib import Path

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Keep test-layer markers consistent with the repository layout."""
    for item in items:
        path = Path(str(item.path))
        parts = {part.lower() for part in path.parts}
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        elif "integration" in parts:
            item.add_marker(pytest.mark.integration)
