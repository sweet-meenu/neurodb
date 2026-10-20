# Proposed Work

NeuroDB is proposed as an AI Knowledge Lake — a managed, cloud-native Vector-Database-as-a-Service
that lets an application store raw documents and retrieve them by *meaning* rather than by exact
keyword match. Today, building semantic search over a document set means stitching together three
separate systems by hand: a place to store the documents, an NLP pipeline to turn them into
embeddings, and a vector database to search those embeddings. NeuroDB's proposed contribution is to
unify all three into a single managed product, provisioned the way a developer already expects from
services like Neon or Supabase — create a project, receive a connection string and an API key, and
start querying.

**[Insert: high-level architecture diagram — `neurodb-web` dashboard → FastAPI control-plane/data-plane
split → per-project NLP pipeline, storage engine, vector index, and NeuroQL query engine]**

The system is architected in two halves. `neurodb-web`, a Next.js dashboard, is the surface a user
signs into to create a project and browse or query their data. `neurodb-core` is the Python engine
behind it, split into a control plane (users, projects, API keys, sessions) and a data plane (the
actual ingest/query API), so that the dashboard and any external application talking to the same
project always go through identical business logic and never drift apart. Per the project's core
design constraint, every piece that would normally be pulled from an ML or database library is
instead implemented from scratch: a hand-written NLP pipeline (sentence-aware chunking, regex and
gazetteer-based named-entity recognition, TF-IDF keyphrase extraction, a hashing-trick embedding
encoder), a hand-written adaptive vector index (brute-force flat search that is automatically
promoted to a hand-written HNSW graph as a collection grows), and a hand-written, WAL-backed,
MVCC storage engine that versions every write so that data can be queried as it existed at an
earlier point in time.

**[Insert: screenshot of the dashboard's Data tab, showing a file being uploaded and ingested, and/or
the Files tab showing chunks grouped by source document]**

On ingestion, a document (plain text, Markdown, HTML, or PDF) is passed through the NLP pipeline,
split into overlapping, topic-bounded chunks, and each chunk is enriched with extracted entities and
keyphrases before being embedded into a dense vector. Every chunk is written to the storage engine as
an immutable, versioned object, added to the project's vector index, and made immediately queryable —
all without depending on any pretrained model or external API call. Retrieval is expressed through
NeuroQL, a SQL-like query language designed for this project, complete with its own lexer, parser,
cost-based optimizer, and executor: a query such as `SELECT * FROM docs SEMANTIC SIMILAR TO
'<natural-language question>' LIMIT 5` is planned against the collection's size and any metadata
filters present, and executed as either an exact scan, a filter-then-rank, or an index-first
approximate search, whichever the optimizer estimates is cheapest.

**[Insert: screenshot of the SQL Editor tab — a NeuroQL semantic query and its ranked results, ideally
with the "Why this match?" explanation panel expanded]**

A project's connection string is the credential an external application uses to talk to its data
without going through the dashboard's login session. It is shown exactly once, at project-creation
time, in the form `neurodb://<project_id>:<api_key>@<host>:<port>` — mirroring how a Postgres
connection string is presented by managed database providers. In practice an application does not
parse this string as a database driver would; it extracts the API key portion and sends it on every
request to NeuroDB's data-plane REST API, either as an `X-NeuroDB-Api-Key` header or as a standard
`Authorization: Bearer <api_key>` header, against endpoints such as `POST /api/data/v1/ingest/file`
to add documents or `POST /api/data/v1/query` to run a NeuroQL query — the same operations available
from the dashboard's SQL Editor, now callable from any backend service or SDK.

**[Insert: screenshot or code snippet showing the connection string / API key being copied from the
project-creation screen, and a short example request using it against the data-plane API]**

The work proposed and delivered for this MVP demonstrates a complete, working loop — provisioning,
ingestion through a real NLP pipeline, semantic querying with an explainable ranking, and version
history — running entirely locally with no paid cloud dependency, and validated by an automated test
suite covering the storage engine, index, NLP pipeline, and query language independently.
