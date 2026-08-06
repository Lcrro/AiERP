"""Material master rules, coding, and search helpers."""

from .coding import generate_next_item_code, next_sequence
from .item_creation import ItemCreationDraft, ItemMasterCreationPlanner
from .postgres_catalog import CatalogPaths, PostgresCatalogSearchClient, PostgresMaterialCatalog
from .release_resolver import ReleaseMaterialCandidate, ReleaseMaterialResolver
from .rules import ItemIntent, MaterialRules, prepare_item_from_intent
from .search import MaterialSearch, SearchCandidate
from .type_classifier import (
    MaterialClassificationCandidate,
    MaterialClassificationResult,
    MaterialTypeClassifier,
)

__all__ = [
    "CatalogPaths",
    "ItemIntent",
    "MaterialRules",
    "MaterialSearch",
    "MaterialClassificationCandidate",
    "MaterialClassificationResult",
    "MaterialTypeClassifier",
    "PostgresCatalogSearchClient",
    "PostgresMaterialCatalog",
    "ReleaseMaterialCandidate",
    "ReleaseMaterialResolver",
    "SearchCandidate",
    "generate_next_item_code",
    "ItemCreationDraft",
    "ItemMasterCreationPlanner",
    "next_sequence",
    "prepare_item_from_intent",
]
