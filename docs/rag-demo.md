# RAG Demo — Medical Knowledge Chatbot

A finalized build plan for a second, separate application in this monorepo: a Streamlit
chatbot that answers questions grounded in a set of ingested medical reference books, using
NeuroDB purely as an external consumer would — through its connection string and REST API,
nothing internal. This is the concrete "does the product actually work as pitched" proof: a
real application, talking to NeuroDB the way any customer's application would.

## Goal

> "Ask a question in plain English, get a conversational answer that's actually grounded in
> our ingested medical textbooks, with the source book and passage cited — not just a list of
> matching sentences."

## Non-goals (what does *not* change)

- **`neurodb-core` stays exactly as scoped** — no pretrained weights, no external ML
  libraries, hand-written storage/index/NLP/query engine. This demo adds nothing to
  `neurodb-core`; it is a client of it.
- **`neurodb-web` is untouched** — it remains the pure database dashboard. The chatbot is a
  new, separate app, not a tab bolted onto the existing dashboard.
- **Not multimodal.** Medical reference books are text/PDF; image/audio ingestion is still
  out of scope (see `roadmap.md`).
- **Not a diagnostic tool.** See "Medical disclaimer" below — this is a literature-search
  assistant over books the user chose to ingest, not a source of medical advice.

## Why this needs a new layer, and the decision on how to build it

`SEMANTIC SIMILAR TO` already does real semantic retrieval — hand-written encoder, hand-written
index, working today. What it cannot do is turn "here are the 5 most relevant passages" into a
conversational, synthesized answer — that step is fundamentally generative, which is a
different problem than retrieval and isn't something the project's from-scratch constraint was
ever meant to cover (the constraint is specifically "no ML/vector-search *library*" for the
database engine itself).

**Decision: use an LLM API (Anthropic Claude, Messages API) as the generation step, inside the
demo app only.** Rationale:

- It's the only realistic way to get genuinely good conversational answers without standing up
  GPU infrastructure for a self-hosted model — disproportionate effort for a demo app.
- It's cleanly scoped: the *retrieval* stays 100% hand-written NeuroDB; only the *generation*
  step, in a separate application, calls out. That line is exactly where "our own vector
  database" ends and "an application built on top of it" begins.
- This is the project's first paid-API dependency anywhere — worth stating plainly rather than
  quietly. It lives entirely in the demo app's `.env`, never in `neurodb-core`.

To avoid hard-coupling to one provider, the generation step is written behind a small interface
(`Generator.generate(question, chunks) -> answer`) with the Claude backend as the default
implementation and a local-model backend (e.g. Ollama) as a documented, swappable alternative
for a zero-API-cost variant — same interface, different `.env` setting.

## Architecture

```
                         ┌─────────────────────────────┐
  medical PDFs  ───────► │   ingest_books.py            │
  (local folder)         │   (bulk loader, one-time)     │
                         └──────────────┬────────────────┘
                                        │  POST /api/data/v1/ingest/file
                                        │  (X-NeuroDB-Api-Key)
                                        ▼
┌───────────────────────────────────────────────────────────┐
│                     neurodb-core (unchanged)                │
│   NLP pipeline → StorageEngine (WAL/MVCC/Parquet) → index   │
│   NeuroQL: SEMANTIC SIMILAR TO ...                           │
└───────────────────────────────────────────────────────────┘
                                        ▲
                                        │  POST /api/data/v1/query
                                        │  (X-NeuroDB-Api-Key)
                         ┌──────────────┴────────────────┐
  user question  ──────► │   Streamlit app (new)           │
                         │   1. retrieve top-k chunks       │
                         │   2. build a grounded prompt      │
                         │   3. call Claude for the answer   │
                         │   4. render answer + citations    │
                         └──────────────┬────────────────┘
                                        │
                                        ▼
                              Anthropic Messages API
                              (generation only — new)
```

**[Insert: this diagram as a clean image for the report]**

## Where it lives in the monorepo

A new top-level directory, sibling to `neurodb-core` and `neurodb-web`:

```
neurodb/
├── neurodb-core/
├── neurodb-web/
├── neurodb-medbot/            # new
│   ├── app.py                  # Streamlit chat UI
│   ├── neurodb_client.py       # thin REST client (connection-string aware)
│   ├── generator.py            # Generator interface + Claude/Ollama backends
│   ├── ingest_books.py         # one-off bulk loader for a folder of PDFs
│   ├── requirements.txt
│   └── .env.example
└── docs/
```

Kept separate from `neurodb-web` deliberately: it's a *consumer application*, not part of the
managed product's own dashboard — mixing them would blur exactly the line this demo exists to
prove.

## Connecting via the connection string

The connection string shown once at project creation —
`neurodb://<project_id>:<api_key>@<host>:<port>` — is parsed once at app startup into the two
things the data-plane REST API actually needs: the API key (sent as `X-NeuroDB-Api-Key`) and
the base URL.

```python
from urllib.parse import urlsplit

def parse_connection_string(conn: str) -> tuple[str, str]:
    """neurodb://<project_id>:<api_key>@<host>:<port> -> (base_url, api_key)"""
    parts = urlsplit(conn)
    api_key = parts.password
    base_url = f"http://{parts.hostname}:{parts.port}"
    return base_url, api_key

# Streamlit sidebar: paste the connection string once, store in st.session_state.
base_url, api_key = parse_connection_string(st.session_state["connection_string"])
headers = {"X-NeuroDB-Api-Key": api_key}
```

Every request from the demo app after that goes to `{base_url}/api/data/v1/...` — the same
API-key-authenticated surface any external SDK would use (see
[`architecture.md`](architecture.md), "Control plane vs. data plane authentication").

## Data: the medical knowledge books

A local folder of medical reference PDFs the user supplies (e.g. a pharmacology reference, a
first-aid/clinical-procedures manual, a drug-interaction guide — anything the user has rights
to use). `ingest_books.py` walks the folder and, for each file, calls
`POST /api/data/v1/ingest/file` against a dedicated collection (e.g. `medbooks`) — reusing the
exact endpoint already built and tested for the dashboard's file upload, no new backend work
required for v1.

**Phase 2 (the "big data" milestone from `roadmap.md`):** once the book corpus is too large to
keep as local files (e.g. sourced from a shared bucket instead of copied onto the demo
machine), swap `ingest_books.py`'s local-folder walk for the planned S3-compatible data-lake
connector — same NeuroDB-facing call, different source. Not a blocker for v1.

## Retrieval flow

One NeuroQL query per user turn:

```sql
SELECT * FROM medbooks
SEMANTIC SIMILAR TO '<condensed question — see below>'
LIMIT 6
```

`POST /api/data/v1/query` returns each match's `modalities.text`, `metadata.filename` (which
book), `metadata.chunk_index`, `score`, and the existing `explanation` (matched terms/entities)
— all of it is reused directly as the grounding context and as citation metadata, with zero new
fields needed from `neurodb-core`.

## Handling multi-turn conversation (NeuroQL is stateless per query)

NeuroQL has no notion of conversation history — each `SEMANTIC SIMILAR TO` is a single,
self-contained query. A follow-up like "how is it dosed?" has no retrievable meaning on its
own. Standard RAG fix, no new NeuroDB capability required: before retrieval, ask the same LLM
to **condense** the chat history + latest question into one standalone query string, then run
*that* through NeuroQL. Two Claude calls per turn (condense, then answer) — an accepted,
well-understood cost for correct multi-turn retrieval.

## Generation step

```python
class Generator(Protocol):
    def generate(self, question: str, chunks: list[RetrievedChunk]) -> str: ...

class ClaudeGenerator:
    """Default backend — Anthropic Messages API."""
    ...

class OllamaGenerator:
    """Optional zero-API-cost backend for a locally-hosted open model."""
    ...
```

System prompt (fixed, not user-editable in v1):

> "Answer the user's question using ONLY the passages below, each tagged with its source book.
> If the passages don't contain the answer, say so explicitly — do not use outside knowledge.
> Cite the source book (and chunk) for every claim you make."

## Streamlit UI plan

- **Sidebar**: connection string input (stored in `st.session_state`, never logged), collection
  picker (`GET /api/data/v1/collections`), and a persistent medical disclaimer.
- **Main pane**: standard `st.chat_message` history; each assistant turn renders the answer plus
  an expandable **Sources** block (`st.expander`) listing the retrieved chunks — book name,
  chunk index, similarity score, and matched terms — reusing the same `explanation` payload the
  dashboard's "Why this match?" panel already renders, so citations aren't just claimed, they're
  inspectable.

## Medical disclaimer (non-negotiable, low effort)

A fixed, always-visible banner: *"This is a literature-search demo over documents the user
chose to ingest. It is not medical advice and has not been reviewed by a clinician."* Shown in
the sidebar and repeated above the first message of every session.

## Build order (next session's work)

1. `neurodb_client.py` — connection-string parsing + thin wrappers around `/ingest/file` and
   `/query`.
2. `ingest_books.py` — bulk-load a folder of PDFs into a `medbooks` collection; run it once
   against 2-3 real reference books.
3. `generator.py` — `Generator` protocol + `ClaudeGenerator` (env var `ANTHROPIC_API_KEY`).
4. `app.py` — Streamlit chat loop: condense → retrieve → generate → render with citations.
5. Manual pass: ask questions with answers that ARE in the books, questions that are NOT (should
   say so, not hallucinate), and a multi-turn follow-up (tests the condense step).
6. `OllamaGenerator` as the documented free alternative, swapped in via `.env`.

## Config (`.env.example`)

```
NEURODB_CONNECTION_STRING=neurodb://<project_id>:<api_key>@localhost:8000
GENERATOR_BACKEND=claude          # or "ollama"
ANTHROPIC_API_KEY=
OLLAMA_MODEL=llama3               # only used if GENERATOR_BACKEND=ollama
```

**[Insert: screenshot of the finished Streamlit chat UI — a question, the generated answer, and
the expanded Sources panel showing the cited book/chunk]**
