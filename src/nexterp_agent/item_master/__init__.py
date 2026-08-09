"""Material master rules, coding, and search helpers."""

from .coding import generate_next_item_code, next_sequence
from .batch_intake import (
    BatchFactExtraction,
    BatchMaterialIntakeAnalyzer,
    ExtractedMaterialFacts,
    MaterialIntakeBatchResult,
    MaterialIntakeDecision,
    MaterialIntakeRow,
)
from .item_creation import ItemCreationDraft, ItemMasterCreationPlanner
from .postgres_catalog import CatalogPaths, PostgresCatalogSearchClient, PostgresMaterialCatalog
from .release_resolver import ReleaseMaterialCandidate, ReleaseMaterialResolver
from .high_recall import (
    BatchMaterialJudgement,
    CandidateGroup,
    HighRecallBatchMaterialIntakeAnalyzer,
    HighRecallBatchResult,
    HighRecallCandidate,
    HighRecallMaterialRetriever,
    MaterialBatchJudgement,
    RetrievalResult,
)
from .intake_drafts import MaterialDraftBatch, MaterialItemDraft, build_material_drafts
from .runtime_aliases import RuntimeAliasStore
from .rules import ItemIntent, MaterialRules, prepare_item_from_intent
from .search import MaterialSearch, SearchCandidate
from .type_classifier import (
    MaterialClassificationCandidate,
    MaterialClassificationResult,
    MaterialTypeClassifier,
)

__all__ = [
    "CatalogPaths",
    "BatchFactExtraction",
    "BatchMaterialIntakeAnalyzer",
    "ExtractedMaterialFacts",
    "ItemIntent",
    "MaterialRules",
    "MaterialSearch",
    "MaterialClassificationCandidate",
    "MaterialClassificationResult",
    "MaterialIntakeBatchResult",
    "MaterialIntakeDecision",
    "MaterialIntakeRow",
    "MaterialTypeClassifier",
    "PostgresCatalogSearchClient",
    "PostgresMaterialCatalog",
    "ReleaseMaterialCandidate",
    "ReleaseMaterialResolver",
    "BatchMaterialJudgement",
    "CandidateGroup",
    "HighRecallBatchMaterialIntakeAnalyzer",
    "HighRecallBatchResult",
    "HighRecallCandidate",
    "HighRecallMaterialRetriever",
    "MaterialBatchJudgement",
    "RetrievalResult",
    "RuntimeAliasStore",
    "MaterialDraftBatch",
    "MaterialItemDraft",
    "build_material_drafts",
    "SearchCandidate",
    "generate_next_item_code",
    "ItemCreationDraft",
    "ItemMasterCreationPlanner",
    "next_sequence",
    "prepare_item_from_intent",
]
