# NeuroDB

**An AI Knowledge Lake for multimodal data management and semantic retrieval** — a
cloud-native Vector Database-as-a-Service, built from scratch as a monorepo.

NeuroDB turns raw documents into a queryable knowledge base: an NLP ingestion pipeline
(extraction, semantic chunking, NER, keyphrases, classification, embedding), an adaptive
vector index (exact search promoted to a hand-written HNSW graph as collections grow), an
ACID/MVCC storage engine with time travel, and **NeuroQL** — a SQL-like query language for
metadata filters, semantic search, and historical queries — all sitting behind a Neon-style
managed dashboard: sign in, create a project, get a connection string and API key.

See [`docs/`](docs/) for the full architecture, the NeuroQL grammar reference, and the
roadmap of what's intentionally out of scope for this MVP — including
[`docs/rag-demo.md`](docs/rag-demo.md), the finalized plan for a separate Streamlit
application that consumes NeuroDB purely through its connection string to build a
retrieval-augmented medical-knowledge chatbot on top of it.

## Monorepo layout

```
neurodb/
├── neurodb-core/     Python engine + control-plane/data-plane API (uv-managed)
├── neurodb-web/       Next.js dashboard (App Router, TypeScript, Tailwind)
└── docs/               Architecture notes, NeuroQL grammar, roadmap
```

## What's actually hand-written vs. what's a library

Per the project's design constraint, only *general-purpose plumbing* uses third-party
libraries (numpy, pyarrow/Parquet as a storage format, FastAPI, pypdf, Next.js/React). Every
piece that would normally come from an ML or vector-search library is implemented from
scratch in `neurodb-core`:

- **Storage engine**: write-ahead log, transaction manager, MVCC version chains, catalog/
  manifest, segment flush — all hand-written; Parquet is used only as the on-disk column
  format for flushed segments.
- **Vector index**: brute-force flat search and a hand-written HNSW graph (Malkov &
  Yashunin), with an adaptive manager that promotes a collection from one to the other. No
  faiss/hnswlib/annoy.
- **Embeddings**: a from-scratch encoder — hashing-trick term vectors, TF‑IDF weighted,
  reduced via a fixed-seed random projection. No pretrained weights, no transformers/
  sentence-transformers.
- **NLP pipeline**: rule-based sentence chunker, whitespace/stem tokenizer, regex +
  gazetteer NER, TF‑IDF keyphrase extraction, a hand-written multinomial Naive Bayes
  classifier. No spaCy/NLTK.
- **NeuroQL**: a hand-written lexer and recursive-descent parser, a cost-based query
  optimizer, and an executor. No parser-generator library.

## Quickstart

**Backend** (`neurodb-core`, requires [uv](https://docs.astral.sh/uv/)):

```bash
cd neurodb-core
uv sync
uv run pytest                                                  # 54 tests
uv run uvicorn neurodb_core.app:create_app --factory --reload  # http://localhost:8000
```

**Frontend** (`neurodb-web`, requires Node 20+):

```bash
cd neurodb-web
npm install
cp .env.example .env.local   # NEXT_PUBLIC_NEURODB_API_URL, defaults to localhost:8000
npm run dev                   # http://localhost:3000
```

Open `http://localhost:3000`, create an account, create a project, and you'll get a
connection string and API key back — the same flow an application would use, minus the
dashboard's "New Project" button. Everything runs locally with no paid cloud dependencies:
project data lives on disk under `neurodb-core/neurodb_data/` (configurable via
`NEURODB_DATA_ROOT`).

## Two ways to talk to a project

- **Dashboard (session-authenticated)** — `/api/control/projects/{id}/data/...`. The
  dashboard signs in as your user and never needs to hold on to a project's API key.
- **Applications/SDKs (API-key-authenticated)** — `/api/data/v1/...`, authenticated with the
  `X-NeuroDB-Api-Key` header (or `Authorization: Bearer <api_key>`). This is the connection
  string/API key shown once at project creation.

Both paths share the same underlying logic (`neurodb_core.dataplane.service`), so they never
drift apart.
