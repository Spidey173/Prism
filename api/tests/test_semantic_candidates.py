from uuid import uuid4

from app.services.semantic_candidates import (
    CandidateClaim,
    generate_candidate_pairs,
    rank_embedding_neighbors,
)


def _claim(text: str, *, page: int, index: int) -> CandidateClaim:
    return CandidateClaim(uuid4(), page, index, uuid4(), text)


def test_similarity_threshold_uses_synthetic_embeddings() -> None:
    a = _claim("The contract allows annual renewal after every completed service term.", page=1, index=1)
    b = _claim("The agreement allows yearly renewal after each full service period.", page=2, index=1)
    c = _claim("Unrelated short note that should not be considered a relevant claim.", page=3, index=1)
    claims = [a, b, c]
    vectors = {a.id: [1.0, 0.0], b.id: [0.8, 0.6], c.id: [0.0, 1.0]}
    nearest = rank_embedding_neighbors(claims, vectors, top_k=2)
    pairs = generate_candidate_pairs(nearest, {item.id: item for item in claims}, similarity_threshold=0.75, min_chunk_distance=8, max_pairs=10)
    assert len(pairs) == 1
    assert pairs[0].ids == frozenset((a.id, b.id))


def test_excludes_nearby_chunks_on_the_same_page() -> None:
    a = _claim("The contract allows annual renewal after every completed service term.", page=1, index=2)
    b = _claim("The agreement prohibits any renewal after the initial service term.", page=1, index=6)
    nearest = {a.id: [(b, 0.95)], b.id: [(a, 0.95)]}
    assert generate_candidate_pairs(nearest, {a.id: a, b.id: b}, similarity_threshold=0.7, min_chunk_distance=8, max_pairs=5) == []


def test_allows_same_page_claims_far_enough_apart() -> None:
    a = _claim("The contract allows annual renewal after every completed service term.", page=1, index=2)
    b = _claim("The agreement prohibits any renewal after the initial service term.", page=1, index=20)
    pairs = generate_candidate_pairs({a.id: [(b, 0.9)]}, {a.id: a, b.id: b}, similarity_threshold=0.7, min_chunk_distance=8, max_pairs=5)
    assert len(pairs) == 1


def test_deduplicates_symmetric_pairs_and_applies_ranked_cap() -> None:
    claims = [
        _claim("The contract allows annual renewal after every completed service term.", page=1, index=1),
        _claim("The agreement prohibits renewal after its initial service term.", page=2, index=1),
        _claim("The service contract provides annual maintenance for covered equipment.", page=3, index=1),
    ]
    nearest = {
        claims[0].id: [(claims[1], 0.82), (claims[2], 0.94)],
        claims[1].id: [(claims[0], 0.82)],
        claims[2].id: [(claims[0], 0.94)],
    }
    pairs = generate_candidate_pairs(nearest, {item.id: item for item in claims}, similarity_threshold=0.7, min_chunk_distance=8, max_pairs=1)
    assert len(pairs) == 1
    assert pairs[0].similarity == 0.94


def test_skips_deterministic_pairs() -> None:
    a = _claim("The contract allows annual renewal after every completed service term.", page=1, index=1)
    b = _claim("The agreement prohibits renewal after its initial service term.", page=2, index=1)
    covered = {frozenset((a.id, b.id))}
    assert generate_candidate_pairs({a.id: [(b, 0.9)]}, {a.id: a, b.id: b}, similarity_threshold=0.7, min_chunk_distance=8, max_pairs=5, covered_pairs=covered) == []
