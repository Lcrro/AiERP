"""Material master rules, coding, and search helpers."""

from .coding import generate_next_item_code, next_sequence
from .postgres_catalog import CatalogPaths, PostgresCatalogSearchClient, PostgresMaterialCatalog
from .rules import ItemIntent, MaterialRules, prepare_item_from_intent
from .search import MaterialSearch, SearchCandidate

__all__ = [
    "CatalogPaths",
    "ItemIntent",
    "MaterialRules",
    "MaterialSearch",
    "PostgresCatalogSearchClient",
    "PostgresMaterialCatalog",
    "SearchCandidate",
    "generate_next_item_code",
    "next_sequence",
    "prepare_item_from_intent",
]
