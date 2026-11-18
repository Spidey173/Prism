from __future__ import annotations

import math
import re
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class CandidateClaim:
    id: UUID
    page_number: int
    chunk_index: int
    sentence_id: UUID
    text: str


@dataclass(frozen=True)
class CandidatePair:
    left: CandidateClaim
    right: CandidateClaim
    similarity: float

    @property
    def ids(self) -> frozenset[UUID]:
        return frozenset((self.left.id, self.right.id))


_CAPTION_START = re.compile(r"^(?:fig(?:ure)?\.?|table|exhibit|chart|appendix)\s*\d*\b", re.IGNORECASE)


def is_claim_like(text: str) -> bool:
    clean = " ".join(text.split())
    if len(clean) < 55 or len(clean.split()) < 8:
        return False
    if _CAPTION_START.match(clean) or clean.endswith(":"):
        return False
    letters = [character for character in clean if character.isalpha()]
    if letters and sum(character.isupper() for character in letters) / len(letters) > 0.8:
        return False
    return True


def rank_embedding_neighbors(
    claims: list[CandidateClaim], embeddings: dict[UUID, list[float]], top_k: int
) -> dict[UUID, list[tuple[CandidateClaim, float]]]:
    """Small pure cosine helper used by candidate tests; production retrieval uses pgvector."""
    ranked: dict[UUID, list[tuple[CandidateClaim, float]]] = {}
    for query in claims:
        query_vector = embeddings.get(query.id)
        if not query_vector:
            ranked[query.id] = []
            continue
        neighbors = []
        for candidate in claims:
            vector = embeddings.get(candidate.id)
            if candidate.id == query.id or not vector or len(vector) != len(query_vector):
                continue
            dot = sum(left * right for left, right in zip(query_vector, vector, strict=True))
            left_norm = math.sqrt(sum(value * value for value in query_vector))
            right_norm = math.sqrt(sum(value * value for value in vector))
            similarity = dot / (left_norm * right_norm) if left_norm and right_norm else 0.0
            neighbors.append((candidate, similarity))
        ranked[query.id] = sorted(neighbors, key=lambda pair: pair[1], reverse=True)[:max(0, top_k)]
    return ranked


def generate_candidate_pairs(
    nearest: dict[UUID, list[tuple[CandidateClaim, float]]],
    claims: dict[UUID, CandidateClaim],
    *,
    similarity_threshold: float,
    min_chunk_distance: int,
    max_pairs: int,
    covered_pairs: set[frozenset[UUID]] | None = None,
) -> list[CandidatePair]:
    covered = covered_pairs or set()
    candidates: dict[frozenset[UUID], CandidatePair] = {}
    for query_id, neighbors in nearest.items():
        for neighbor, similarity in neighbors:
            if similarity < similarity_threshold or query_id == neighbor.id:
                continue
            if not is_claim_like(neighbor.text):
                continue
            query = claims.get(query_id)
            if query is None or not is_claim_like(query.text):
                continue
            if query.sentence_id == neighbor.sentence_id:
                continue
            if query.page_number == neighbor.page_number and abs(query.chunk_index - neighbor.chunk_index) < min_chunk_distance:
                continue
            pair_ids = frozenset((query.id, neighbor.id))
            if pair_ids in covered:
                continue
            left, right = sorted(
                (query, neighbor),
                key=lambda claim: (" ".join(claim.text.split()).casefold(), str(claim.id)),
            )
            current = candidates.get(pair_ids)
            if current is None or similarity > current.similarity:
                candidates[pair_ids] = CandidatePair(left, right, similarity)
    ranked = sorted(candidates.values(), key=lambda pair: pair.similarity, reverse=True)
    return ranked[:max(0, max_pairs)]
