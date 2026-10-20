"""Streamlit medical-knowledge chatbot — retrieval-augmented generation over
books ingested into a NeuroDB project, talked to purely through its
connection string and public data-plane API. See docs/rag-demo.md.
"""

from __future__ import annotations

import os

import streamlit as st
from dotenv import load_dotenv

from generator import build_generator
from neurodb_client import NeuroDBClient, NeuroDBError, RetrievedChunk

load_dotenv()

DISCLAIMER = (
    "This is a literature-search demo over documents the user chose to ingest. "
    "It is **not medical advice** and has not been reviewed by a clinician."
)

_BACKEND_KEY_ENV = {
    "gemini": ("GEMINI_API_KEY", "GEMINI_MODEL"),
    "claude": ("ANTHROPIC_API_KEY", "CLAUDE_MODEL"),
    "ollama": (None, "OLLAMA_MODEL"),
}

st.set_page_config(page_title="NeuroDB Medical Knowledge Chat", page_icon="🩺")


def _connect(connection_string: str) -> NeuroDBClient:
    client = NeuroDBClient(connection_string)
    client.list_collections()  # fail fast if the connection string / server is bad
    return client


def _make_generator():
    backend = os.environ.get("GENERATOR_BACKEND", "gemini")
    key_env, model_env = _BACKEND_KEY_ENV.get(backend, (None, None))
    return build_generator(
        backend,
        api_key=os.environ.get(key_env) if key_env else None,
        model=os.environ.get(model_env) if model_env else None,
    )


def _history_pairs(messages: list[dict]) -> list[tuple[str, str]]:
    return [(m["role"], m["content"]) for m in messages]


def _source_summary(chunks: list[RetrievedChunk]) -> str:
    seen: list[str] = []
    for chunk in chunks:
        if chunk.filename not in seen:
            seen.append(chunk.filename)
    return "📚 Grounded in: " + ", ".join(seen) if seen else "⚠️ No matching passages found in any ingested book."


def _render_sources(chunks: list[RetrievedChunk]) -> None:
    st.caption(_source_summary(chunks))
    if not chunks:
        return
    with st.expander(f"Show the {len(chunks)} retrieved passage(s) behind this answer"):
        for i, chunk in enumerate(chunks, start=1):
            score = f"{chunk.score:.3f}" if chunk.score is not None else "—"
            st.markdown(
                f"**[{i}] {chunk.filename}**"
                + (f" · chunk {chunk.chunk_index}" if chunk.chunk_index is not None else "")
                + f" · similarity {score}"
            )
            if chunk.matched_terms:
                st.caption("matched terms: " + ", ".join(chunk.matched_terms))
            st.text(chunk.text)


with st.sidebar:
    st.header("1. Connect")
    st.caption(DISCLAIMER)

    default_conn = os.environ.get("NEURODB_CONNECTION_STRING", "")
    connection_string = st.text_input(
        "Connection string", value=default_conn, type="password", placeholder="neurodb://<project_id>:<api_key>@host:port"
    )
    collection = st.text_input("Collection", value="medbooks")

    if st.button("Connect", type="primary", disabled=not connection_string):
        try:
            st.session_state["client"] = _connect(connection_string)
            st.session_state["generator"] = _make_generator()
            st.session_state["collection"] = collection
            st.session_state.setdefault("messages", [])
            st.success("Connected ✅")
        except (NeuroDBError, ValueError) as exc:
            st.error(f"Couldn't connect: {exc}")

    if "client" in st.session_state:
        st.divider()
        st.header("2. Add books")
        uploads = st.file_uploader(
            "Upload medical references — PDF, text, CSV, image, or audio (.wav/.mp3, needs the server-side "
            "Whisper backend)",
            type=["pdf", "txt", "md", "markdown", "html", "htm", "csv", "png", "jpg", "jpeg", "gif", "bmp", "webp", "wav", "mp3"],
            accept_multiple_files=True,
        )
        if uploads and st.button("Ingest into NeuroDB"):
            client: NeuroDBClient = st.session_state["client"]
            for f in uploads:
                with st.spinner(f"Ingesting {f.name}..."):
                    try:
                        result = client.ingest_bytes(f.getvalue(), filename=f.name, collection=st.session_state["collection"])
                        st.success(f"{f.name}: {result['chunks_created']} chunks ingested")
                    except NeuroDBError as exc:
                        st.error(f"{f.name}: {exc}")

        st.divider()
        if st.button("Clear chat"):
            st.session_state["messages"] = []

st.title("🩺 Medical Knowledge Chat")
st.caption(DISCLAIMER)

if "client" not in st.session_state:
    st.info("Paste a project connection string in the sidebar and click Connect to begin.")
    st.stop()

for message in st.session_state["messages"]:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message.get("sources") is not None:
            _render_sources(message["sources"])

question = st.chat_input("Ask a question about the ingested books...")
if question:
    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Searching and generating an answer..."):
            client: NeuroDBClient = st.session_state["client"]
            generator = st.session_state["generator"]
            history = _history_pairs(st.session_state["messages"][:-1])
            chunks: list[RetrievedChunk] = []
            try:
                condensed = generator.condense(history, question)
                chunks = client.semantic_search(st.session_state["collection"], condensed, limit=6)
                answer = generator.generate(question, chunks)
            except NeuroDBError as exc:
                answer = f"Retrieval failed: {exc}"
            except Exception as exc:  # noqa: BLE001 - surface generator/API errors to the user, don't crash the app
                answer = f"Generation failed: {exc}"

        st.write(answer)
        _render_sources(chunks)

    st.session_state["messages"].append({"role": "assistant", "content": answer, "sources": chunks})
