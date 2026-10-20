# Roadmap / explicitly out of scope for this MVP

These were deliberately descoped during planning rather than accidentally omitted — noted
here so the gap is visible rather than discovered later.

## Promoted: next two milestones

Two items below are being pulled out of "deferred" and scheduled next, because a concrete
consumer app needs them (see [`rag-demo.md`](rag-demo.md) for the full design of both):

- **Big-data / scale — S3-compatible data-lake connector.** The synopsis's stated target for
  ingesting corpora too large to hand-upload one file at a time; today `connectors/datalake.py`
  only walks a local filesystem. Needed to point NeuroDB at a real bucket of medical reference
  books instead of files copied onto the machine running the demo. Same interface as the
  existing connector (read in place, run through the NLP pipeline) — the gap is purely an
  S3-compatible client + credentials handling, not a design change.
- **Retrieval-Augmented Generation (RAG) / chat layer.** Genuinely new, not named in the
  original synopsis at all: today `SEMANTIC SIMILAR TO` returns ranked matching chunks and
  stops there. A real chatbot needs a generation step on top — an LLM that turns "here are the
  5 most relevant passages from these medical textbooks" into an actual conversational,
  cited answer. This is being built as a separate demo application (`neurodb-web` stays a
  pure database dashboard) that talks to NeuroDB exclusively through its public
  API-key-authenticated data-plane REST API — i.e. the same connection string any external
  application would use, which doubles as a real-world validation of that API surface.

## Implemented since the initial roadmap: multimodal ingestion

Image, audio, and CSV ingestion now ship (`.png/.jpg/.jpeg/.gif/.bmp/.webp`, `.wav`, `.csv`,
alongside the original `.txt/.md/.html/.pdf`) — closing part of the synopsis's "multimodal"
framing this doc used to list as entirely unimplemented. Honest about the tradeoff, matching
this project's existing encoder-quality pattern:

- **Images and audio get hand-written, pre-deep-learning feature vectors** — a color-
  histogram + spatial-grid descriptor for images (`nlp/image_features.py`), and a frame-based
  RMS/zero-crossing-rate/spectral-centroid descriptor for audio (`nlp/audio_features.py`), both
  reduced through the same random-projection trick as the text encoder. This gives real, working
  visual/acoustic *similarity* search — not object recognition or scene understanding. No
  pretrained weights, matching the project's constraint.
- **Real image description / audio transcription is opt-in, off by default** —
  `nlp/captioning.py` calls an external model (Gemini, reusing the credential precedent set by
  the RAG demo) only if `NEURODB_CAPTION_API_KEY` is configured; `google-genai` is a core
  dependency (always installed) but its client is only constructed once that path is actually
  exercised. When enabled, the generated caption/transcript is chunked and
  embedded through the ordinary text pipeline on the same object, so it becomes searchable via
  plain `SEMANTIC SIMILAR TO` like any other text — this is the only way to get "what's actually
  in the image/said in the audio" search without violating the project's from-scratch
  constraint. Left unconfigured, ingestion is 100% hand-written, zero external calls, same as
  everything else.
- **`.wav` decodes with zero extra dependency** (stdlib `wave`); **`.mp3` requires the opt-in
  local Whisper backend** (`nlp/transcription.py`, `NEURODB_TRANSCRIBE_BACKEND=whisper`) —
  `faster-whisper`/`av` are core dependencies (always installed), the env var just gates
  whether the model actually loads. There's no honest hand-written way to decode a
  compressed audio codec at all, so unlike image/audio captioning (an optional *enrichment* on
  top of ingestion that already works without it), MP3 *ingestion itself* doesn't work without
  this configured; attempting it without the backend returns a 400 explaining why. Backed by
  `faster-whisper` (CTranslate2, not PyTorch — lighter, and its PyAV-based decoding bundles its
  own audio codecs, so a separate system `ffmpeg` install usually isn't needed) at the "tiny"
  model size by default. Once decoded, the same PCM samples feed both a real transcript (→
  chunked and embedded as searchable text, same mechanism as image captions) and the ordinary
  hand-written audio feature vector — so an MP3 object gets both search modes, same as
  everything else. Other compressed formats (m4a, ogg, ...) aren't wired up, though PyAV can
  decode them — `nlp/extraction.py::COMPRESSED_AUDIO_EXTENSIONS` is the place to add them.
- **CSV is text, not a new modality** — rendered to "column: value." sentences and run through
  the existing chunk/embed/index path unchanged, no separate tabular embedding field.
- **Still not ingested**: DOCX, PPTX, video. The storage model (`modalities: dict[str, Any]`,
  arbitrary embedding fields per object) already generalizes to them; no extractor exists yet.
- **Cross-modal text search over images/audio isn't meaningful** — a `SEMANTIC SIMILAR TO
  '<text>' USING image` query would run without error (dimensions match), but the text encoder
  and the image encoder map to unrelated feature spaces, so the similarity score wouldn't mean
  anything. The correct primitive for genuine image/audio similarity search is "search by
  example" (compare a candidate file's own embedding against the index) — not implemented as a
  dedicated endpoint yet, tracked here rather than silently offered as if it worked.

## Vector indexing

- **IVF, Product Quantization, DiskANN** — the synopsis names all four alongside HNSW. This
  MVP ships flat (exact) search and a hand-written HNSW, with adaptive promotion between them.
  IVF/PQ/DiskANN are real, separate algorithms each worth their own implementation effort;
  building all five properly was traded for spending the time on the storage engine, NLP
  pipeline, and query optimizer instead.

## Distributed architecture

- **Real multi-node Raft consensus, sharding, replication** — `cluster/node.py` defines the
  `ClusterNode`/`ShardMap` interfaces a real implementation would plug into, but only
  `SingleNodeCluster` (trivially its own leader) is implemented. Leader election and log
  replication across processes is a multi-week distributed-systems project in its own right;
  building it properly would have consumed the time budget for everything else. This also
  matches the "one person owns a project, runs it locally for free" model — a distributed
  cluster isn't needed until you outgrow a single node.

## Data lake connector

- Only a **local filesystem** connector (`connectors/datalake.py`) is implemented, in
  keeping with the "run everything for free, no paid cloud dependencies" constraint. An
  S3/MinIO-compatible connector (the synopsis's stated target) would follow the same
  interface — read files in place, run them through the NLP pipeline — but needs an
  S3-compatible client and credentials handling not built here.

## Embeddings / NLP quality

- The embedding encoder (`nlp/embedding.py`) is a from-scratch hashing-trick + TF‑IDF +
  random-projection encoder, not a pretrained transformer. This was an explicit tradeoff: the
  project's constraint was "no ML/vector-search libraries," which rules out
  sentence-transformers/transformers; a hand-rolled inference engine over pretrained weights
  was considered and rejected as disproportionate effort for the quality gain.
- NER is regex + a small bundled gazetteer, not a statistical/learned model — it will
  mislabel unfamiliar multi-word capitalized phrases (a two-word capitalized sequence not in
  the gazetteer defaults to `PERSON`).
- Document ingestion supports `.txt`, `.md`, `.html`, `.pdf`, `.csv`, common image formats,
  `.wav`, and (with the opt-in Whisper backend) `.mp3` audio (see "Implemented since the
  initial roadmap" above). DOCX, PPTX, and video aren't ingested yet.

## NeuroQL

- No joins across collections, no aggregations (`COUNT`, `GROUP BY`, `SUM`), no multi-column
  `ORDER BY`. The grammar covers filtering, semantic search, and time travel only.
- `AS OF` time travel is per-object-version (via MVCC), not per-catalog-version; the catalog's
  version history log doesn't yet let you ask "what did collection X's *schema/segment set*
  look like as of version N," only "what did object O look like."

## Platform / access

- **No gRPC** — only REST is exposed, despite the synopsis naming gRPC alongside it. The
  REST API (control plane + data plane) covers the same functionality; a gRPC surface would
  be an additive layer over the same `dataplane/service.py` logic.
- **No language SDKs** (Python/JS/Go/Java/C++ client libraries) — applications call the REST
  API directly today.
- **No usage-based billing/metering, multi-region deployment, enterprise SSO/RBAC** — all
  named as "future enhancements" in the synopsis itself (§4.20), and out of scope here too.
- **No GPU/CUDA acceleration** — distance computation is numpy (CPU) only.

## Auth

- Dashboard sessions use a JWT in `localStorage` read by client components, not httpOnly
  cookies + Next.js middleware-gated routes. Fine for a local, single-user dev tool; would
  need hardening (httpOnly cookies, CSRF handling) before being exposed beyond localhost.
