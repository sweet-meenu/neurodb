from __future__ import annotations

import math
from collections import Counter

from neurodb_core.nlp.tokenizer import normalize_tokens


def term_frequencies(text: str) -> Counter:
    return Counter(normalize_tokens(text))


def extract_keyphrases(
    text: str,
    *,
    corpus_doc_freq: dict[str, int] | None = None,
    corpus_size: int = 1,
    top_n: int = 8,
) -> list[tuple[str, float]]:
    """TF-IDF keyphrase scoring: term frequency within this chunk weighted
    by inverse document frequency across the corpus (falls back to
    chunk-local frequency alone when no corpus stats are supplied).
    """
    tf = term_frequencies(text)
    if not tf:
        return []
    total_terms = sum(tf.values())
    doc_freq = corpus_doc_freq or {}

    scores: dict[str, float] = {}
    for term, count in tf.items():
        tf_norm = count / total_terms
        df = doc_freq.get(term, 0) + 1  # +1 smoothing: avoid div-by-zero / log(0)
        idf = math.log((corpus_size + 1) / df) + 1
        scores[term] = tf_norm * idf

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:top_n]
