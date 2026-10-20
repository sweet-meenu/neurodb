# Architecture

## Layers

```
neurodb-web (Next.js)
   │  fetch, CORS-enabled, browser → backend directly
   ▼
neurodb-core (FastAPI app.py)
   ├── controlplane/   users, projects, API keys, sessions (JWT) — sqlite3
   │     └── project_data.py   session-authenticated mirror of the data-plane,
   │                            used by the dashboard so it never has to hold
   │                            an API key
   ├── dataplane/      API-key-authenticated REST surface for external apps
   │     ├── router.py         thin FastAPI routes
   │     └── service.py        shared business logic (both routers call this)
   │
   │   Per project, lazily constructed and cached (dataplane/runtime.py):
   ├── nlp/            extraction → chunking → NER/keyphrases/classification → embedding
   ├── storage/         StorageEngine: WAL → MVCC → Parquet segments → catalog
   ├── index/            IndexManager: adaptive flat/HNSW per (collection, field)
   ├── lifecycle/        embedding version registry + background re-embedding
   ├── query/neuroql/   lexer → parser → planner → optimizer → executor → explain
   ├── connectors/       local data-lake connector (indexes files in place)
   └── cluster/          ClusterNode/ShardMap interfaces (single-node impl only)
```

Each **project** (created via the control plane) gets an isolated on-disk root
(`neurodb_data/projects/{project_id}/`) and its own `StorageEngine` + `IndexManager` +
`EmbeddingVersionRegistry`, cached in memory by `ProjectRuntimeCache` and rehydrated (index
rebuilt from durable storage) on first access after a process restart — the index itself
isn't persisted, only the data it's built from.

## Storage engine

- **WAL** (`storage/wal.py`): length-prefixed, `fsync`-on-write. `replay()` reconstructs
  every record written since the last checkpoint.
- **Transactions** (`storage/txn.py`): monotonic transaction ids, a commit watermark used for
  snapshot isolation — a reader's snapshot never sees a transaction with a higher id, even if
  it commits mid-scan.
- **MVCC** (`storage/mvcc.py`): every write is a new, immutable `ObjectVersion` (never an
  in-place update). The "hot" tier lives in memory; `get`/`scan` fall back to reading
  segments for anything already checkpointed out.
- **Segments** (`storage/segment.py`): committed versions are flushed into immutable Parquet
  files (pyarrow used purely as the columnar file format, the same role it plays in Delta
  Lake).
- **Catalog** (`storage/catalog.py`): a Delta-Lake-style append-only action log plus a
  materialized view of current segments/collections — this is what NeuroQL's `AS OF` queries
  and the dashboard's Versions tab read.

Time travel follows directly from this design: `AS OF VERSION n` / `AS OF TIMESTAMP '...'`
just changes which `ObjectVersion` is considered "visible" for a given object, whether it's
still in the hot tier or already in a segment.

## Vector index

- **Flat** (`index/flat.py`): brute-force cosine search, always exact. Used below a size
  threshold and as the ground-truth baseline HNSW recall is tested against.
- **HNSW** (`index/hnsw.py`): a hand-written multi-layer proximity graph (Malkov & Yashunin,
  2018) — greedy layer descent to find an entry point, then a bounded best-first search at
  layer 0. No hnswlib/faiss.
- **Adaptive manager** (`index/manager.py`): a `CollectionIndex` starts as flat and is
  transparently promoted to HNSW once it crosses `HNSW_PROMOTION_THRESHOLD` (5,000 vectors by
  default). `IndexManager` owns one `CollectionIndex` per `(collection, embedding field)`
  pair, so multiple embedding models/fields on the same collection index independently.

## Embedding

`nlp/embedding.py` implements NeuroDB's own encoder rather than wrapping a pretrained model:
a hashing-trick term vector (TF, optionally IDF-weighted) is reduced via a fixed-seed
Gaussian random projection to a dense 256-dim output. By the Johnson–Lindenstrauss lemma this
approximately preserves pairwise distances from the sparse term space, so cosine similarity
between outputs tracks term-overlap similarity — a legitimate, if lower-quality-than-a-
transformer, from-scratch semantic signal.

## Multimodal ingestion

`nlp/pipeline.py`'s `DocumentPipeline.process_bytes` dispatches on file extension into two
shapes:

- **Text-like** (`.txt/.md/.html/.pdf/.csv`) — extraction -> chunking -> NER/keyphrases/
  classification -> embedding, unchanged, returning `list[ProcessedChunk]`. `.csv` is rendered
  to "column: value." sentences per row (`nlp/extraction.py::extract_csv_bytes`) and flows
  through this exact same path — no separate tabular embedding field.
- **Image/audio** — a single `ProcessedMedia`: one hand-written feature-vector embedding for
  the whole file, no chunking (`nlp/image_features.py::encode_image`,
  `nlp/audio_features.py::encode_audio`). Both project a raw hand-crafted descriptor through
  the same fixed-seed random-projection trick `nlp/embedding.py` uses for text, landing in the
  same 256-dim output space/storage schema:
  - *Image*: an 8x8 spatial grid of average cell color (layout) concatenated with a 32-bin
    per-channel global color histogram (palette) — 288 raw dims. Image decoding uses Pillow
    (general-purpose plumbing, same exception category as pypdf).
  - *Audio*: 20 time frames of (RMS energy, zero-crossing rate, spectral centroid via a plain
    `numpy.fft.rfft`) plus an 8-bin whole-clip spectral-energy histogram
    (`nlp/audio_features.py::_raw_audio_features`, exposed as `encode_audio_samples` for
    already-decoded PCM and `encode_audio` for raw WAV bytes). `.wav` decodes via stdlib `wave`
    with zero extra dependency; `.mp3` is decoded by the opt-in Whisper backend below instead
    (there's no hand-written path for a compressed codec), feeding the same
    `encode_audio_samples`.

  Both are genuine visual/acoustic *similarity* signals — not object recognition or scene/
  speech understanding, an explicit, documented tradeoff matching the text encoder's own
  (see "Embedding" below and `docs/roadmap.md`).

`dataplane/service.py::store_media` (mirrored in `connectors/datalake.py::_ingest_media`)
stores the media object as `modalities={<"image"|"audio">: filename}` — a pointer, not inlined
bytes — with the actual file written to `raw_files/<collection>/<filename>` on disk (the same
mechanism the dashboard's "View PDF" uses), served back via
`GET /collections/{collection}/files/raw`. The embedding is indexed under its own field name
(`"image"` or `"audio"`) via the existing per-`(collection, field)` `IndexManager` — no changes
needed there, multiple embedding fields per collection already worked.

### Optional captioning/transcription

`nlp/captioning.py` is an opt-in enrichment hook, off by default. If `NEURODB_CAPTION_API_KEY`
is set, `DocumentPipeline` is constructed with a `caption_fn` (wired once in
`dataplane/runtime.py::ProjectRuntimeCache.__init__`) that asks an external model (Gemini) to
describe the image or transcribe the audio. When it returns non-empty text, that text is run
through the *ordinary* text pipeline (`process_text`) and stored as additional chunk objects
under the same filename — meaning a captioned image becomes searchable by
`SEMANTIC SIMILAR TO '<what's actually in the image>'` through the same machinery as any PDF,
without the encoder itself ever touching pretrained weights. Left unconfigured, `caption_fn` is
`None`, `google-genai` is never imported, and ingestion is identical to the hand-written-only
path. This is the same "hand-written core, optional external layer explicitly kept outside it"
pattern as the RAG demo's generation step (`docs/rag-demo.md`) — never silently blurred into a
default.

`nlp/transcription.py` is the audio-specific counterpart, and the reason `.mp3` ingestion works
at all: `build_transcribe_fn()` returns `None` (MP3 ingestion disabled, `.wav` unaffected)
unless `NEURODB_TRANSCRIBE_BACKEND=whisper` is set, in which case it lazily loads a local
`faster-whisper` model (`NEURODB_WHISPER_MODEL`, default `"tiny"`) and decodes via PyAV. Unlike
`caption_fn`, which only *enriches* an ingestion that already succeeds without it,
`transcribe_fn` is load-bearing for `.mp3` specifically — `DocumentPipeline._process_media_bytes`
raises a `ValueError` (surfaced as a 400) naming the missing env var/extra if a `.mp3` is
ingested with no `transcribe_fn` configured, rather than failing with an opaque decode error.

## Re-embedding / model migration

`lifecycle/reembed.py`'s `ReembedJob` detects objects whose embedding for a
`(collection, field)` is on an outdated model/version and regenerates them in batches. Because
a new model's output dimensionality generally differs from the old one's, migrated vectors
can't simply be added into the live index — instead each migration backfills a **shadow**
`CollectionIndex` at the new dimensionality while the live index keeps serving queries
unchanged, then atomically swaps in via `IndexManager.replace()` once every object is
migrated. Storage itself is updated incrementally the whole time (each batch is a normal
MVCC-versioned write), so `AS OF` queries against the pre-migration state keep working
throughout. This is the "no downtime, no application changes" rollout the design calls for —
via a shadow-index cutover rather than a per-query traffic-split, since mixing two
dimensionalities in one index isn't meaningful.

## NeuroQL

See [`neuroql.md`](neuroql.md) for the grammar. The query engine is a standard four-stage
pipeline: `lexer.py` → `parser.py` (hand-written recursive descent, no parser-generator
library) → `planner.py` (AST → `LogicalPlan`) → `optimizer.py` (cost-based strategy choice) →
`executor.py`. The optimizer estimates `WHERE`-clause selectivity from the predicate shape
(equality ≈ selective, range ≈ moderate, AND multiplies, OR unions, NOT inverts) and picks
between three physical strategies:

- `scan_filter` — no semantic clause, just scan + filter.
- `filter_first` — filter is selective enough that scanning the whole collection and doing
  exact brute-force cosine search among the small surviving candidate set is both correct and
  cheap.
- `semantic_first` — ANN-search the whole index (≈ log N) and filter the (small) result set
  after, when the filter isn't selective enough to make `filter_first` worthwhile.

`explain.py` builds a per-result `Explanation`: which terms/entities/keyphrases the query and
the matched object share, plus a confidence score blending vector similarity with lexical
overlap — this is what backs the dashboard's "Why this match?" panel.

## Cluster interfaces

`cluster/node.py` defines `ClusterNode`/`ShardMap` as the extension point a real multi-node,
Raft-based implementation would plug into. The only shipped implementation,
`SingleNodeCluster`, is trivially its own leader for every shard it's given. See
[`roadmap.md`](roadmap.md) for why real distributed consensus isn't implemented in this MVP.

## Control plane vs. data plane authentication

Two authenticated entry points share one `dataplane/service.py`:

- `controlplane/project_data.py` — session-authenticated (JWT from login), ownership-checked
  against the requesting user. This is what the dashboard itself calls.
- `dataplane/router.py` — API-key-authenticated (`X-NeuroDB-Api-Key`), for external
  applications/SDKs using the connection string shown once at project creation.
