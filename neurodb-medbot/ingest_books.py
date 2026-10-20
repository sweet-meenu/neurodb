"""One-off bulk loader: walks a local folder of medical reference books and
ingests each supported file into a NeuroDB collection via the same
/ingest/file endpoint the dashboard's file upload uses.

Usage:
    python ingest_books.py --connection-string "neurodb://..." --folder ./books --collection medbooks
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from neurodb_client import NeuroDBClient, NeuroDBError

# Same set neurodb-core's extraction pipeline supports (nlp/extraction.py).
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown", ".html", ".htm"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connection-string", required=True, help="neurodb://<project_id>:<api_key>@<host>:<port>")
    parser.add_argument("--folder", required=True, type=Path, help="local folder of medical reference books")
    parser.add_argument("--collection", default="medbooks")
    args = parser.parse_args()

    if not args.folder.is_dir():
        print(f"error: {args.folder} is not a directory", file=sys.stderr)
        return 1

    client = NeuroDBClient(args.connection_string)
    files = sorted(p for p in args.folder.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS)
    if not files:
        print(f"no supported files ({', '.join(sorted(SUPPORTED_EXTENSIONS))}) found under {args.folder}")
        return 0

    print(f"ingesting {len(files)} file(s) into collection '{args.collection}'...")
    total_chunks = 0
    failures = 0
    for path in files:
        try:
            result = client.ingest_file(path, collection=args.collection)
        except NeuroDBError as exc:
            print(f"  FAILED {path.name}: {exc}")
            failures += 1
            continue
        chunks = result["chunks_created"]
        total_chunks += chunks
        print(f"  ok  {path.name} -> {chunks} chunks")

    print(f"\ndone: {len(files) - failures}/{len(files)} files ingested, {total_chunks} chunks total")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
