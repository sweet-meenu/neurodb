import io
import struct
import wave

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from neurodb_core.app import create_app
from neurodb_core.nlp.audio_features import encode_audio, encode_audio_samples
from neurodb_core.nlp.extraction import extract_csv_bytes
from neurodb_core.nlp.image_features import encode_image
from neurodb_core.nlp.pipeline import DocumentPipeline, ProcessedMedia


def _png_bytes(color: tuple[int, int, int], size: tuple[int, int] = (32, 32)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=color).save(buf, format="PNG")
    return buf.getvalue()


def _wav_bytes(freq: float | None, duration_s: float = 0.5, framerate: int = 8000) -> bytes:
    """freq=None renders silence (all-zero samples) instead of a tone."""
    n_samples = int(duration_s * framerate)
    if freq is None:
        samples = np.zeros(n_samples, dtype=np.int16)
    else:
        t = np.arange(n_samples) / framerate
        samples = (np.sin(2 * np.pi * freq * t) * 32767 * 0.8).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buf.getvalue()


# -- extraction / encoders -----------------------------------------------------


def test_extract_csv_bytes_renders_rows_as_readable_sentences():
    csv_data = b"name,age,city\nAda,36,London\nGrace,85,Arlington\n"
    text = extract_csv_bytes(csv_data)
    assert "name: Ada" in text
    assert "age: 36" in text
    assert "city: London" in text
    assert "name: Grace" in text


def test_extract_csv_bytes_skips_empty_values():
    csv_data = b"a,b,c\n1,,3\n"
    text = extract_csv_bytes(csv_data)
    assert "a: 1" in text
    assert "b:" not in text  # empty cell dropped, not rendered as "b: "
    assert "c: 3" in text


def test_encode_image_is_deterministic_and_correct_dims():
    data = _png_bytes((10, 20, 30))
    a = encode_image(data)
    b = encode_image(data)
    assert a.vector == b.vector
    assert a.dims == len(a.vector) == 256


def test_encode_image_similar_colors_closer_than_different():
    red = encode_image(_png_bytes((220, 20, 20)))
    red2 = encode_image(_png_bytes((200, 30, 30)))
    blue = encode_image(_png_bytes((10, 10, 220)))

    r, r2, b = np.array(red.vector), np.array(red2.vector), np.array(blue.vector)
    sim_red_red = np.dot(r, r2)
    sim_red_blue = np.dot(r, b)
    assert sim_red_red > sim_red_blue


def test_encode_audio_correct_dims_and_deterministic():
    data = _wav_bytes(440.0)
    a = encode_audio(data)
    b = encode_audio(data)
    assert a.vector == b.vector
    assert a.dims == len(a.vector) == 256


def test_encode_audio_similar_tones_closer_than_different():
    a = encode_audio(_wav_bytes(440.0))
    a2 = encode_audio(_wav_bytes(460.0))
    silence = encode_audio(_wav_bytes(None))

    va, va2, vs = np.array(a.vector), np.array(a2.vector), np.array(silence.vector)
    assert np.dot(va, va2) > np.dot(va, vs)


def test_encode_audio_samples_matches_encode_audio_on_equivalent_input():
    # encode_audio_samples() is what the MP3/Whisper path uses (decoded PCM
    # instead of WAV bytes) — it must be the exact same math as encode_audio().
    data = _wav_bytes(440.0)
    from_bytes = encode_audio(data)

    with wave.open(io.BytesIO(data), "rb") as wf:
        framerate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0
    from_samples = encode_audio_samples(samples, framerate)

    assert from_bytes.vector == from_samples.vector


# -- pipeline dispatch ----------------------------------------------------------


def test_pipeline_process_bytes_dispatches_image_to_media():
    pipeline = DocumentPipeline()
    result = pipeline.process_bytes(_png_bytes((5, 5, 5)), filename="photo.png")
    assert isinstance(result, ProcessedMedia)
    assert result.modality == "image"
    assert result.content_type == "image/png"
    assert len(result.embedding.vector) == 256
    assert result.caption is None  # no caption_fn configured
    assert result.caption_chunks == []


def test_pipeline_process_bytes_dispatches_audio_to_media():
    pipeline = DocumentPipeline()
    result = pipeline.process_bytes(_wav_bytes(300.0), filename="clip.wav")
    assert isinstance(result, ProcessedMedia)
    assert result.modality == "audio"
    assert result.content_type in ("audio/wav", "audio/x-wav")  # mimetypes DB varies by platform


def test_pipeline_mp3_without_transcribe_fn_raises_clear_error():
    pipeline = DocumentPipeline()
    with pytest.raises(ValueError, match="NEURODB_TRANSCRIBE_BACKEND"):
        pipeline.process_bytes(b"fake mp3 bytes", filename="clip.mp3")


def test_pipeline_mp3_with_transcribe_fn_produces_media_and_transcript_chunks():
    def fake_transcribe(data: bytes) -> tuple[np.ndarray, int, str]:
        samples = np.sin(2 * np.pi * 440 * np.arange(4000) / 8000)
        return samples, 8000, "This is a test transcript of the audio clip."

    pipeline = DocumentPipeline(transcribe_fn=fake_transcribe)
    result = pipeline.process_bytes(b"fake mp3 bytes", filename="clip.mp3")
    assert isinstance(result, ProcessedMedia)
    assert result.modality == "audio"
    assert len(result.embedding.vector) == 256
    assert result.caption == "This is a test transcript of the audio clip."
    assert len(result.caption_chunks) >= 1
    assert "test transcript" in result.caption_chunks[0].text


def test_pipeline_process_bytes_csv_goes_through_text_path():
    pipeline = DocumentPipeline()
    result = pipeline.process_bytes(b"name,note\nAda,pioneer\n", filename="people.csv")
    assert isinstance(result, list)
    assert result[0].text
    assert "Ada" in result[0].text


def test_pipeline_caption_fn_produces_text_chunks_when_configured():
    def fake_caption(data: bytes, mime_type: str) -> str:
        return "A red square on a white background, with some visible text reading DEMO."

    pipeline = DocumentPipeline(caption_fn=fake_caption)
    result = pipeline.process_bytes(_png_bytes((200, 10, 10)), filename="photo.png")
    assert isinstance(result, ProcessedMedia)
    assert result.caption is not None and "red square" in result.caption
    assert len(result.caption_chunks) >= 1
    assert len(result.caption_chunks[0].embedding.vector) == 256


def test_pipeline_caption_fn_returning_empty_string_yields_no_chunks():
    pipeline = DocumentPipeline(caption_fn=lambda data, mime_type: "")
    result = pipeline.process_bytes(_png_bytes((1, 2, 3)), filename="photo.png")
    assert result.caption is None
    assert result.caption_chunks == []


# -- end-to-end through the API ---------------------------------------------------


@pytest.fixture()
def client(tmp_path):
    app = create_app(tmp_path / "neurodb_data")
    with TestClient(app) as c:
        yield c


def _auth_headers(client) -> dict:
    client.post("/api/control/auth/register", json={"email": "img@example.com", "password": "supersecret"})
    resp = client.post("/api/control/auth/login", json={"email": "img@example.com", "password": "supersecret"})
    token = resp.json()["access_token"]
    resp = client.post(
        "/api/control/projects", json={"name": "media-proj"}, headers={"Authorization": f"Bearer {token}"}
    )
    api_key = resp.json()["api_key"]
    return {"X-NeuroDB-Api-Key": api_key}


def test_ingest_image_creates_object_with_image_field_and_is_searchable(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/api/data/v1/ingest/file",
        headers=headers,
        data={"collection": "photos"},
        files={"file": ("cat.png", _png_bytes((30, 200, 30)), "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["chunks_created"] == 1

    resp = client.get("/api/data/v1/collections", headers=headers)
    collections = {c["name"]: c for c in resp.json()}
    assert collections["photos"]["object_count"] == 1
    assert "image" in collections["photos"]["modalities"]

    resp = client.get(
        "/api/data/v1/collections/photos/objects", headers=headers, params={"filename": "cat.png"}
    )
    objects = resp.json()
    assert len(objects) == 1
    assert objects[0]["modalities"]["image"] == "cat.png"
    assert objects[0]["metadata"]["modality"] == "image"

    # raw bytes round-trip (same mechanism as "View PDF")
    resp = client.get(
        "/api/data/v1/collections/photos/files/raw", headers=headers, params={"filename": "cat.png"}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


def test_ingest_audio_creates_object_with_audio_field(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/api/data/v1/ingest/file",
        headers=headers,
        data={"collection": "clips"},
        files={"file": ("tone.wav", _wav_bytes(500.0), "audio/wav")},
    )
    assert resp.status_code == 201

    resp = client.get("/api/data/v1/collections", headers=headers)
    collections = {c["name"]: c for c in resp.json()}
    assert "audio" in collections["clips"]["modalities"]


def test_ingest_mp3_without_whisper_backend_configured_returns_400(client):
    headers = _auth_headers(client)
    resp = client.post(
        "/api/data/v1/ingest/file",
        headers=headers,
        data={"collection": "clips"},
        files={"file": ("clip.mp3", b"fake mp3 bytes", "audio/mpeg")},
    )
    assert resp.status_code == 400
    assert "NEURODB_TRANSCRIBE_BACKEND" in resp.json()["detail"]


def test_ingest_csv_chunks_rows_as_text(client):
    headers = _auth_headers(client)
    csv_bytes = b"name,role\nAda Lovelace,mathematician\nGrace Hopper,computer scientist\n"
    resp = client.post(
        "/api/data/v1/ingest/file",
        headers=headers,
        data={"collection": "people"},
        files={"file": ("people.csv", csv_bytes, "text/csv")},
    )
    assert resp.status_code == 201
    assert resp.json()["chunks_created"] >= 1

    resp = client.post(
        "/api/data/v1/query",
        headers=headers,
        json={"query": "SELECT * FROM people SEMANTIC SIMILAR TO 'mathematician' LIMIT 3;"},
    )
    results = resp.json()["results"]
    assert any("Ada Lovelace" in r["modalities"]["text"] for r in results)


def test_delete_file_removes_media_object_and_raw_copy(client):
    headers = _auth_headers(client)
    client.post(
        "/api/data/v1/ingest/file",
        headers=headers,
        data={"collection": "photos"},
        files={"file": ("cat.png", _png_bytes((10, 10, 10)), "image/png")},
    )
    resp = client.delete(
        "/api/data/v1/collections/photos/files", headers=headers, params={"filename": "cat.png"}
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    resp = client.get(
        "/api/data/v1/collections/photos/files/raw", headers=headers, params={"filename": "cat.png"}
    )
    assert resp.status_code == 404
