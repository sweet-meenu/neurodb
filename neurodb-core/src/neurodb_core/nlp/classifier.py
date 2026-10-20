from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from neurodb_core.nlp.tokenizer import normalize_tokens


@dataclass
class NaiveBayesClassifier:
    """Hand-written multinomial Naive Bayes text classifier, trained purely
    from labeled examples the caller supplies — no pretrained weights.
    """

    alpha: float = 1.0
    class_doc_counts: Counter = field(default_factory=Counter)
    class_term_counts: dict = field(default_factory=lambda: defaultdict(Counter))
    class_total_terms: Counter = field(default_factory=Counter)
    vocabulary: set = field(default_factory=set)
    fitted: bool = False

    def fit(self, examples: list[tuple[str, str]]) -> None:
        for text, label in examples:
            tokens = normalize_tokens(text)
            self.class_doc_counts[label] += 1
            counts = Counter(tokens)
            self.class_term_counts[label].update(counts)
            self.class_total_terms[label] += sum(counts.values())
            self.vocabulary.update(tokens)
        self.fitted = True

    def predict(self, text: str) -> tuple[str | None, dict[str, float]]:
        if not self.fitted or not self.class_doc_counts:
            return None, {}
        tokens = normalize_tokens(text)
        total_docs = sum(self.class_doc_counts.values())
        vocab_size = max(len(self.vocabulary), 1)

        log_scores: dict[str, float] = {}
        for label, doc_count in self.class_doc_counts.items():
            log_prob = math.log(doc_count / total_docs)
            term_counts = self.class_term_counts[label]
            total_terms = self.class_total_terms[label]
            for token in tokens:
                count = term_counts.get(token, 0)
                log_prob += math.log((count + self.alpha) / (total_terms + self.alpha * vocab_size))
            log_scores[label] = log_prob

        max_log = max(log_scores.values())
        exp_scores = {label: math.exp(score - max_log) for label, score in log_scores.items()}
        total = sum(exp_scores.values())
        probs = {label: value / total for label, value in exp_scores.items()}
        best_label = max(probs, key=probs.get)
        return best_label, probs
