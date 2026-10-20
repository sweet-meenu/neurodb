from __future__ import annotations

from dataclasses import dataclass

from neurodb_core.nlp.ner import extract_entities
from neurodb_core.nlp.tokenizer import normalize_tokens
from neurodb_core.storage.records import ObjectVersion


@dataclass
class Explanation:
    similarity: float
    confidence: float
    matched_terms: list[str]
    matched_entities: list[str]
    matched_keyphrases: list[str]
    contributing_field: str


def build_explanation(query_text: str, ov: ObjectVersion, similarity: float, field: str = "text") -> Explanation:
    """Explainable search: instead of a bare similarity score, report which
    terms/entities/keyphrases the query and the matched object share, and a
    confidence score blending vector similarity with lexical overlap.
    """
    query_terms = set(normalize_tokens(query_text))
    object_text = ov.modalities.get(field, "")
    object_text = object_text if isinstance(object_text, str) else ""
    object_terms = set(normalize_tokens(object_text))
    matched_terms = sorted(query_terms & object_terms)

    query_entities = {e.text.lower() for e in extract_entities(query_text)}
    object_entities = {e.text.lower() for e in extract_entities(object_text)} if object_text else set()
    stored_entities = {str(e).lower() for e in ov.metadata.get("entities", [])}
    matched_entities = sorted((query_entities & object_entities) | (query_entities & stored_entities))

    stored_keyphrases = {str(k).lower() for k in ov.metadata.get("keyphrases", [])}
    matched_keyphrases = sorted(query_terms & stored_keyphrases)

    term_overlap_ratio = len(matched_terms) / len(query_terms) if query_terms else 0.0
    confidence = max(0.0, min(1.0, 0.7 * similarity + 0.3 * term_overlap_ratio))

    return Explanation(
        similarity=similarity,
        confidence=confidence,
        matched_terms=matched_terms,
        matched_entities=matched_entities,
        matched_keyphrases=matched_keyphrases,
        contributing_field=field,
    )
