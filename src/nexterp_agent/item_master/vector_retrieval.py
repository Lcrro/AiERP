"""Small, deterministic vector retrieval primitives for material candidates.

The project intentionally has no mandatory ML runtime.  This module therefore
provides a dependency-free hashing vectorizer that turns normalized Chinese
character n-grams and alphanumeric tokens into L2-normalized vectors.  It is a
lexical vector signal (not a semantic embedding) and is used as a recall lane;
business rules and exact attributes remain responsible for the final decision.

``TextEmbeddingProvider`` is kept as a protocol so a reviewed, local embedding
model can be added later without changing the resolver or its API contract.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
from typing import Any, Iterable, Protocol, Sequence


class TextEmbeddingProvider(Protocol):
    """Interface for an optional embedding backend."""

    def embed(self, texts: Sequence[str]) -> list[Sequence[float]]: ...


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.#/+_-][a-z0-9]+)*|[\u4e00-\u9fff]+", re.IGNORECASE)
_PUNCTUATION_RE = re.compile(r"[\s\u3000，。；：、（）()【】\[\]{}<>《》“”‘’'\"|,;:]+")


def normalize_vector_text(value: Any) -> str:
    """Normalize searchable text without discarding Chinese or model symbols."""

    text = str(value or "").casefold()
    text = _PUNCTUATION_RE.sub("", text)
    return text


def _features(value: Any) -> Iterable[tuple[str, float]]:
    text = normalize_vector_text(value)
    if not text:
        return ()

    features: list[tuple[str, float]] = []
    for token in _TOKEN_RE.findall(text):
        # Whole tokens retain useful model/brand/alias signals.
        features.append((f"t:{token}", 2.0))
        if len(token) >= 2:
            for size in (2, 3):
                features.extend((f"c:{token[index:index + size]}", 1.0) for index in range(len(token) - size + 1))
    # Include cross-token character windows for strings such as “六角螺栓M12”.
    if len(text) >= 2:
        for size in (2, 3):
            features.extend((f"w:{text[index:index + size]}", 0.75) for index in range(len(text) - size + 1))
    return features


class HashingTextVectorizer:
    """Stable sparse-feature hashing vectorizer with cosine-compatible output."""

    def __init__(self, dimension: int = 512) -> None:
        if int(dimension) < 32:
            raise ValueError("向量维度至少为 32")
        self.dimension = int(dimension)

    def embed_one(self, text: Any) -> tuple[float, ...]:
        vector = [0.0] * self.dimension
        for feature, weight in _features(text):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimension
            sign = -1.0 if digest[4] & 1 else 1.0
            vector[bucket] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm <= 0:
            return tuple(vector)
        return tuple(value / norm for value in vector)

    def embed(self, texts: Sequence[str]) -> list[Sequence[float]]:
        return [self.embed_one(text) for text in texts]


@dataclass(frozen=True)
class VectorMatch:
    document_id: str
    score: float


class TextVectorIndex:
    """In-memory cosine index for the small governed material catalog."""

    def __init__(self, vectorizer: HashingTextVectorizer | None = None) -> None:
        self.vectorizer = vectorizer or HashingTextVectorizer()
        self._vectors: dict[str, tuple[float, ...]] = {}

    def build(self, documents: Iterable[tuple[str, str]]) -> None:
        rows = [(str(document_id), str(text or "")) for document_id, text in documents if str(document_id)]
        vectors = self.vectorizer.embed([text for _document_id, text in rows])
        self._vectors = {
            document_id: tuple(float(value) for value in vector)
            for (document_id, _text), vector in zip(rows, vectors)
        }

    def score(self, query: str, document_id: str) -> float:
        return self.score_vector(self.vectorizer.embed_one(query), document_id)

    def score_vector(self, query_vector: Sequence[float], document_id: str) -> float:
        vector = self._vectors.get(str(document_id))
        if vector is None:
            return 0.0
        return round(_dot(query_vector, vector), 6)

    def query(self, query: str, *, limit: int = 10, min_score: float = 0.0) -> list[VectorMatch]:
        if not str(query or "").strip() or not self._vectors:
            return []
        query_vector = self.vectorizer.embed_one(query)
        matches = [
            VectorMatch(document_id=document_id, score=round(_dot(query_vector, vector), 6))
            for document_id, vector in self._vectors.items()
        ]
        matches = [match for match in matches if match.score >= float(min_score)]
        matches.sort(key=lambda match: (-match.score, match.document_id))
        return matches[: max(1, int(limit))]

    def __len__(self) -> int:
        return len(self._vectors)


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def material_vector_text(row: dict[str, Any]) -> str:
    """Build one governed search document from a release-catalog row."""

    fields = (
        "item_code",
        "item_name",
        "sku_name",
        "standard_name",
        "top_group",
        "sub_group",
        "material_family",
        "item_group",
        "required_specs",
        "optional_specs",
        "aliases",
        "search_keywords",
        "brand",
        "model",
        "stock_uom",
    )
    return " ".join(str(row.get(field) or "") for field in fields)


__all__ = [
    "HashingTextVectorizer",
    "TextEmbeddingProvider",
    "TextVectorIndex",
    "VectorMatch",
    "material_vector_text",
    "normalize_vector_text",
]
