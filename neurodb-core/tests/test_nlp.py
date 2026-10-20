import numpy as np

from neurodb_core.nlp.chunker import chunk_text, split_sentences
from neurodb_core.nlp.classifier import NaiveBayesClassifier
from neurodb_core.nlp.embedding import encode
from neurodb_core.nlp.extraction import extract_html
from neurodb_core.nlp.keyphrase import extract_keyphrases
from neurodb_core.nlp.ner import extract_entities
from neurodb_core.nlp.pipeline import DocumentPipeline
from neurodb_core.nlp.tokenizer import normalize_tokens, tokenize


def test_tokenize_and_normalize():
    tokens = tokenize("Running quickly, Dr. Smith jumped!")
    assert "Running" in tokens
    normalized = normalize_tokens("The runners are running quickly")
    assert "the" not in normalized
    assert "are" not in normalized


def test_split_sentences_respects_abbreviations():
    text = "Dr. Smith works at Acme Inc. He is a scientist. She left at 5 p.m. yesterday."
    sentences = split_sentences(text)
    assert len(sentences) >= 2
    assert any("Dr. Smith" in s for s in sentences)


def test_chunk_text_respects_token_budget():
    text = " ".join([f"This is sentence number {i} in a long document." for i in range(60)])
    chunks = chunk_text(text, target_tokens=50)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text.split()) <= 70  # budget + slack for overlap/last sentence


def test_extract_html_strips_tags_and_scripts():
    html = "<html><head><style>.a{}</style></head><body><script>evil()</script><p>Hello <b>World</b></p></body></html>"
    text = extract_html(html)
    assert "Hello" in text and "World" in text
    assert "evil" not in text
    assert "<p>" not in text


def test_extract_entities_finds_email_date_and_org():
    text = "Contact Dr. Jane Doe at jane@example.com. She joined Acme Inc. on Jan 5, 2024 in New York."
    entities = extract_entities(text)
    labels = {(e.text, e.label) for e in entities}
    assert ("jane@example.com", "EMAIL") in labels
    assert any(label == "ORG" for _, label in labels)
    assert any(label == "DATE" for _, label in labels)
    assert any(label == "GPE" and "New York" in text_ for text_, label in labels)


def test_extract_keyphrases_ranks_repeated_terms_higher():
    text = "database database database vector search index query optimizer"
    keyphrases = extract_keyphrases(text, top_n=3)
    assert keyphrases[0][0] == "database"  # most frequent term ranks first


def test_naive_bayes_classifier_learns_separable_classes():
    clf = NaiveBayesClassifier()
    clf.fit([
        ("the stock market rallied today on strong earnings", "finance"),
        ("investors watched interest rates and the economy", "finance"),
        ("the football team won the championship game", "sports"),
        ("the basketball player scored thirty points", "sports"),
    ])
    label, probs = clf.predict("the earnings report beat market expectations")
    assert label == "finance"
    assert probs["finance"] > probs["sports"]


def test_embedding_similar_texts_closer_than_unrelated():
    a = encode("The vector database stores embeddings efficiently.")
    b = encode("Embeddings are stored efficiently in the vector database.")
    c = encode("The chef prepared a delicious pasta dinner tonight.")

    va, vb, vc = np.array(a.vector), np.array(b.vector), np.array(c.vector)
    sim_ab = np.dot(va, vb)
    sim_ac = np.dot(va, vc)
    assert sim_ab > sim_ac
    assert a.dims == len(a.vector) == 256


def test_pipeline_process_text_end_to_end():
    pipeline = DocumentPipeline(target_tokens=40)
    text = (
        "NeuroDB is a vector database. It was built by Meenakshi Mishra. "
        "The database supports semantic search over documents. "
        "Contact support@neurodb.dev for help. It launched on Jan 1, 2026."
    )
    chunks = pipeline.process_text(text, source_metadata={"doc_id": "abc"})
    assert len(chunks) >= 1
    first = chunks[0]
    assert first.source_metadata["doc_id"] == "abc"
    assert len(first.embedding.vector) == 256
    assert isinstance(first.keyphrases, list)
