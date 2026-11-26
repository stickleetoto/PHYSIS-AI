"""Collect only approved public sources. Network access is explicit and never occurs at app startup."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from physis.knowledge_sources import BOOKS, CORPUS, DownloadCache, OpenStax, atomic, nasa_metadata, serialize, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--delete-source", choices=[*BOOKS, "glenn", "ntrs"])
    operations.add_argument("--reindex-source", choices=[*BOOKS, "glenn", "ntrs"])
    operations.add_argument("--inspect", type=Path, help="Inspect local PDF, HTML or Markdown extraction; writes nothing to index")
    parser.add_argument("--db", type=Path, help="Path to the public knowledge SQLite database for source maintenance")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "physis-v03-public-downloads")
    parser.add_argument("--offline", action="store_true", help="Require verified cached downloads")
    parser.add_argument("--refresh", action="store_true", help="Revalidate by fetching sources even if cached")
    parser.add_argument("--preview", type=Path, help="Write eligible candidate paragraphs for editorial review")
    parser.add_argument("--output", type=Path, default=CORPUS / "units.json")
    args = parser.parse_args()
    if args.inspect:
        from physis.knowledge_processing import extract_document, MAX_BYTES
        from dataclasses import asdict
        with args.inspect.open("rb") as handle:
            doc = extract_document(handle.read(MAX_BYTES + 1), args.inspect.suffix.lower().lstrip("."))
        print(json.dumps(asdict(doc), ensure_ascii=False, indent=2))
        return 0
    if args.delete_source or args.reindex_source:
        from physis.knowledge import KnowledgeStore
        if not args.db:
            parser.error("--db is required for maintenance")
        store = KnowledgeStore(args.db)
        store.initialize()
        stats = (store.delete_source(args.delete_source) if args.delete_source else store.reindex_source(args.reindex_source))
        print(json.dumps(stats, ensure_ascii=False))
        return 0
    if args.refresh and args.offline:
        parser.error("Choose either --refresh or --offline")
    cache = DownloadCache(args.cache, args.refresh, args.offline)
    specs = json.loads((CORPUS / "selection.json").read_bytes())
    adapters, docs, failures = {}, [], []
    for spec in specs:
        key = spec["source"]
        try:
            if key in BOOKS:
                if key not in adapters:
                    adapters[key] = OpenStax(key, cache)
                doc = adapters[key].get(spec, bool(args.preview))
            else:
                doc = nasa_metadata(cache, spec)
            docs.append(doc)
        except Exception as error:
            failures.append(f"{key}-{spec['module']}: {type(error).__name__}: {error}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        if args.preview:
            atomic(args.preview, serialize(docs))
        return 1
    identifiers = {d["id"] for d in docs}
    if len(identifiers) != len(docs) or len({d["sha256"] for d in docs}) != len(docs):
        raise ValueError("Duplicate document ID or source payload")
    output = args.preview or args.output
    payload = serialize(docs)
    atomic(output, payload)
    if not args.preview:
        atomic(output.with_suffix(".sha256"), (sha(payload) + "\n").encode())
    print(f"{len(docs)} units, {sum(len(doc['chunks']) for doc in docs)} paragraphs, {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

