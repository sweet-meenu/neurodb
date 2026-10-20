import Link from "next/link";

const FEATURES = [
  {
    title: "Multimodal storage",
    body: "One object, many modalities and many embeddings. Text, PDFs, code, and more, versioned together.",
  },
  {
    title: "NLP-driven ingestion",
    body: "Extraction, semantic chunking, NER, keyphrases, and classification run on every document you ingest.",
  },
  {
    title: "Adaptive indexing",
    body: "Exact flat search for small collections, promoted transparently to a hand-built HNSW graph as they grow.",
  },
  {
    title: "NeuroQL",
    body: "A SQL-like language for metadata filters, semantic search, hybrid queries, and time travel.",
  },
  {
    title: "Time travel",
    body: "Every write is a new MVCC version. Query any collection AS OF a version or a timestamp.",
  },
  {
    title: "Explainable search",
    body: "Every match reports the terms, entities, and keyphrases it shares with your query, not just a score.",
  },
];

export default function Home() {
  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between px-6 py-5 sm:px-10">
        <span className="text-lg font-semibold tracking-tight">
          Neuro<span className="text-accent">DB</span>
        </span>
        <nav className="flex items-center gap-3 text-sm">
          <Link href="/login" className="rounded-md px-3 py-2 text-muted hover:text-foreground">
            Sign in
          </Link>
          <Link
            href="/register"
            className="rounded-md bg-accent px-4 py-2 font-medium text-black hover:bg-accent-strong"
          >
            Get started
          </Link>
        </nav>
      </header>

      <main className="flex flex-1 flex-col items-center px-6 py-16 sm:py-24">
        <div className="mx-auto max-w-3xl text-center">
          <p className="mb-4 inline-block rounded-full border border-border bg-surface px-3 py-1 text-xs text-muted">
            An AI Knowledge Lake, delivered as a managed database
          </p>
          <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">
            Semantic search, provisioned in seconds.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-lg text-muted">
            NeuroDB turns raw documents into a queryable knowledge base: NLP ingestion,
            adaptive vector indexing, and a SQL-like query language, all behind a database
            URL and an API key — no servers to run yourself.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link
              href="/register"
              className="rounded-md bg-accent px-6 py-3 font-medium text-black hover:bg-accent-strong"
            >
              Create a free project
            </Link>
            <Link
              href="/login"
              className="rounded-md border border-border px-6 py-3 font-medium text-foreground hover:bg-surface"
            >
              Sign in
            </Link>
          </div>
        </div>

        <div className="mt-16 w-full max-w-3xl overflow-hidden rounded-lg border border-border bg-surface">
          <div className="flex items-center gap-2 border-b border-border px-4 py-2">
            <span className="h-2.5 w-2.5 rounded-full bg-danger/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-yellow-500/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-accent/70" />
            <span className="ml-2 text-xs text-muted">NeuroQL</span>
          </div>
          <pre className="overflow-x-auto p-5 text-left font-mono text-sm leading-6 text-foreground">
{`SELECT *
FROM support_tickets
WHERE category = 'billing'
SEMANTIC SIMILAR TO 'customer asking for a refund'
ORDER BY score DESC
LIMIT 5;`}
          </pre>
        </div>

        <div className="mt-20 grid w-full max-w-5xl grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div key={f.title} className="rounded-lg border border-border bg-surface p-5">
              <h3 className="font-medium text-foreground">{f.title}</h3>
              <p className="mt-2 text-sm text-muted">{f.body}</p>
            </div>
          ))}
        </div>
      </main>

      <footer className="border-t border-border px-6 py-8 text-center text-xs text-muted">
        NeuroDB — an AI Knowledge Lake for multimodal data management and semantic retrieval.
      </footer>
    </div>
  );
}
