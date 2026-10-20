import pytest


@pytest.fixture(autouse=True)
def _no_external_api_calls_in_tests(monkeypatch):
    """The test suite must stay deterministic and network-independent
    regardless of what's in a developer's local neurodb-core/.env — clear
    the opt-in captioning/transcription config so build_caption_fn() and
    build_transcribe_fn() (nlp/captioning.py, nlp/transcription.py) stay
    disabled for every test. Tests that want to exercise either inject their
    own fake caption_fn/transcribe_fn instead (see test_multimodal.py).
    """
    monkeypatch.delenv("NEURODB_CAPTION_API_KEY", raising=False)
    monkeypatch.delenv("NEURODB_TRANSCRIBE_BACKEND", raising=False)
