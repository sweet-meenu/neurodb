# neurodb-medbot

A Streamlit RAG chatbot over medical reference books, built as a plain external application on
top of NeuroDB — see [`../docs/rag-demo.md`](../docs/rag-demo.md) for the full design. This app
has no import-level dependency on `neurodb-core`; it only talks to a running NeuroDB server over
HTTP, using a project's connection string, exactly like any external application would.

## Setup

```bash
cd neurodb-medbot
python -m venv .venv && . .venv/Scripts/activate   # or source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:
- `NEURODB_CONNECTION_STRING` — from a NeuroDB project's Overview tab (shown once at creation;
  use "Rotate API key" to get a fresh one if you lost it).
- `ANTHROPIC_API_KEY` — required for the default `GENERATOR_BACKEND=claude`. Set
  `GENERATOR_BACKEND=ollama` instead to use a free, locally-hosted model via
  [Ollama](https://ollama.com) — no key needed, but answer quality (especially the
  question-condensing step) will vary a lot more by model.

## Ingest a few books

```bash
python ingest_books.py --connection-string "neurodb://..." --folder ./books --collection medbooks
```

Point `--folder` at a directory of medical reference PDFs (or `.txt`/`.md`/`.html`). Re-running
against the same folder just adds more chunks under the same filenames — delete a file's chunks
from the NeuroDB dashboard's Files tab first if you want to re-ingest a changed version cleanly.

## Run the chatbot

```bash
streamlit run app.py
```

Paste the connection string in the sidebar (or leave it — it's pre-filled from `.env`), hit
Connect, and ask a question. Every answer shows an expandable **Sources** panel citing which
book (and which chunk) it was grounded in.
