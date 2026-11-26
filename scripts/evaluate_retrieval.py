"""Closed, local document-retrieval comparison using manually assigned section relevance."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from physis.knowledge import KnowledgeStore
from physis.knowledge_sources import CORPUS


def evaluate(store, items, use_embeddings=False):
    results = {}
    modes = [("lexical", False), ("rrf", False), ("weighted", False), ("hybrid", False)]
    if use_embeddings:
        raise ValueError("이 버전의 검색 평가는 텍스트 색인만 사용합니다.")
    for mode, embeddings in modes:
        records = []
        for item in items:
            started = time.perf_counter_ns()
            cuts = store.search(item["query"], mode=mode, embeddings=embeddings, limit=50, unique_documents=True)
            elapsed = (time.perf_counter_ns() - started) / 1e6
            docs = [c["doc_id"] for c in cuts]
            target = set(item["relevant_docs"])
            ranks = [i for i, doc in enumerate(docs, 1) if doc in target]
            top_five = [rank for rank in ranks if rank <= 5]
            records.append({"query": item["query"], "group": item["group"], "docs": docs[:5], "ms": round(elapsed,3),
                            "hit1": int(1 in ranks), "hit5": int(bool(top_five)),
                            "precision1": int(1 in ranks), "recall5": len(top_five)/len(target),
                            "mrr": 1/min(ranks) if ranks else 0, "rr5": 1/min(top_five) if top_five else 0})
        grouped = defaultdict(list)
        for record in records:
            grouped[record["group"]].append(record)
            grouped["all"].append(record)
        summary = {}
        for group, rows in grouped.items():
            summary[group] = {"n": len(rows), **{k: round(sum(r[k] for r in rows) / len(rows), 4)
                              for k in ("precision1","recall5","mrr","hit1", "hit5", "rr5", "ms")}}
        results[mode + ("+lsa" if embeddings else "")] = {"summary": summary, "queries": records}
    return {"corpus": store.stats(), "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--embeddings", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as folder:
        store = KnowledgeStore(Path(folder) / "public.sqlite3")
        store.initialize()
        report = evaluate(store, json.loads((CORPUS / "retrieval_queries.json").read_bytes()), args.embeddings)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k:v["summary"] for k,v in report["results"].items()}, indent=2))

