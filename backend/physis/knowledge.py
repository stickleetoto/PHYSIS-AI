"""Offline public-literature index with independent, addressable citation records."""
from collections import Counter
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3

from .knowledge_sources import CORPUS, sha
from .knowledge_terms import concepts, tokens


SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppressed(source TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY,source TEXT NOT NULL,level TEXT NOT NULL,
 models TEXT NOT NULL, metadata TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cuts(id TEXT PRIMARY KEY,doc TEXT NOT NULL REFERENCES docs(id) ON DELETE CASCADE,
 passage TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS cuts_doc ON cuts(doc);
CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(id UNINDEXED,doc UNINDEXED,title,section,text,
 tokenize='unicode61 remove_diacritics 2');
"""




class KnowledgeStore:
    def __init__(self, path, corpus_path=None):
        self.path = Path(path)
        self.corpus_path = Path(corpus_path or CORPUS / "units.json")

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=20)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _bundle(self):
        body = self.corpus_path.read_bytes()
        digest = sha(body)
        if self.corpus_path.with_suffix(".sha256").read_text().strip() != digest:
            raise ValueError("공개 문헌 묶음의 SHA-256이 일치하지 않습니다.")
        return digest, json.loads(body)

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        digest, docs = self._bundle()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if names and not {"settings", "docs", "cuts", "passages", "suppressed"}.issubset(names):
                raise ValueError("공개 문헌 전용 SQLite 파일을 선택하세요.")
            for statement in SCHEMA.split(";"):
                if statement.strip():
                    db.execute(statement)
            prev = db.execute("SELECT value FROM settings WHERE key='corpus'").fetchone()
            if prev and prev[0] == digest:
                return
            db.execute("DELETE FROM passages")
            db.execute("DELETE FROM docs")
            disabled = {r[0] for r in db.execute("SELECT source FROM suppressed")}
            self._insert(db, [d for d in docs if d["source_id"] not in disabled])
            db.execute("INSERT OR REPLACE INTO settings VALUES ('corpus',?)", (digest,))

    def _insert(self, db, docs):
        for doc in docs:
            meta = {k: v for k, v in doc.items() if k != "chunks"}
            meta["chunk_count"] = len(doc["chunks"])
            db.execute("INSERT INTO docs VALUES (?,?,?,?,?)", (doc["id"], doc["source_id"], doc["level"],
                       json.dumps(doc["models"]), json.dumps(meta, ensure_ascii=False)))
            if doc["chunks"] and (not doc["citable"] or doc["license"] != "CC BY 4.0"):
                raise ValueError("본문 재배포 범위를 확인하세요.")
            for c in doc["chunks"]:
                if c["doc_id"] != doc["id"] or sha(c["text"].encode()) != c["text_sha256"]:
                    raise ValueError("문단 ID 또는 원문 해시가 일치하지 않습니다.")
                db.execute("INSERT INTO cuts VALUES (?,?,?)", (c["id"], doc["id"], json.dumps(c, ensure_ascii=False)))
                db.execute("INSERT INTO passages VALUES (?,?,?,?,?)", (c["id"], doc["id"], doc["title"], c["section"], c["text"]))

    def _source(self, source, restore):
        _, all_docs = self._bundle()
        docs = [d for d in all_docs if d["source_id"] == source]
        if not docs:
            raise KeyError(source)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM passages WHERE doc IN (SELECT id FROM docs WHERE source=?)", (source,))
            db.execute("DELETE FROM docs WHERE source=?", (source,))
            if restore:
                self._insert(db, docs)
                db.execute("DELETE FROM suppressed WHERE source=?", (source,))
            else:
                db.execute("INSERT OR IGNORE INTO suppressed VALUES (?)", (source,))
        return self.stats()

    def delete_source(self, source):
        return self._source(source, False)

    def reindex_source(self, source):
        return self._source(source, True)

    def stats(self):
        with self.connect() as db:
            return {"documents": db.execute("SELECT count(*) FROM docs").fetchone()[0],
                    "chunks": db.execute("SELECT count(*) FROM cuts").fetchone()[0],
                    "sources": dict(db.execute("SELECT source,count(*) FROM docs GROUP BY source").fetchall()),
                    "deleted_sources": [r[0] for r in db.execute("SELECT source FROM suppressed ORDER BY source")],
                    "corpus_sha256": db.execute("SELECT value FROM settings WHERE key='corpus'").fetchone()[0]}

    @staticmethod
    def _filter(model=None, source=None, level=None):
        terms, values = [], []
        for col, value in (("d.source", source), ("d.level", level)):
            if value:
                terms.append(col + "=?")
                values.append(value)
        if model:
            terms.append("EXISTS (SELECT 1 FROM json_each(d.models) WHERE value=?)")
            values.append(model)
        return (" AND " + " AND ".join(terms) if terms else ""), values

    def documents(self, model=None, source=None, level=None):
        clause, values = self._filter(model, source, level)
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute("SELECT d.metadata FROM docs d WHERE 1" + clause +
                                                        " ORDER BY d.source,d.id", values)]

    @staticmethod
    def _cut(row):
        return {**json.loads(row["metadata"]), **json.loads(row["passage"])}

    def chunk(self, key):
        with self.connect() as db:
            row = db.execute("SELECT metadata,passage FROM cuts c JOIN docs d ON c.doc=d.id WHERE c.id=?", (key,)).fetchone()
            return self._cut(row) if row else None

    def document(self, key):
        with self.connect() as db:
            rows = db.execute("SELECT metadata,passage FROM docs d LEFT JOIN cuts c ON c.doc=d.id WHERE d.id=? ORDER BY c.rowid", (key,)).fetchall()
            if not rows:
                return None
            return {**json.loads(rows[0]["metadata"]), "chunks": [self._cut(r) for r in rows if r["passage"]]}

    def related(self, key, limit=4):
        target = self.document(key)
        if not target:
            return []
        def overlap(item):
            return (3 * len(set(target["concepts"]) & set(item["concepts"]))
                    + len(set(target["models"]) & set(item["models"])))
        choices = [(overlap(item), item) for item in self.documents() if item["id"] != key]
        return [item for score, item in sorted(choices, key=lambda x: (-x[0], x[1]["id"])) if score > 0][:limit]

    def search(self, query, model=None, source=None, level=None, mode="hybrid", limit=6, embeddings=False,
               unique_documents=False):
        if mode not in {"lexical", "rrf", "weighted", "hybrid"} or not 1 <= limit <= 50 or len(query) > 2000:
            raise ValueError("검색 모드·길이·결과 수를 확인하세요.")
        words = list(dict.fromkeys(tokens(query)))[:32]
        # Remove quotes and operators by tokenizing before constructing the FTS MATCH expression.
        match = " OR ".join('"' + w + '"' for w in words)
        matches = concepts(query) if mode != "lexical" else {}
        clause, values = self._filter(model, source, level)
        with self.connect() as db:
            db.execute("BEGIN")
            lexical = [r[0] for r in db.execute(
                "SELECT passages.id FROM passages JOIN docs d ON d.id=passages.doc WHERE passages MATCH ?" + clause +
                " ORDER BY bm25(passages,0,0,7,2,1),passages.id", [match, *values])] if match else []
            rows = db.execute("SELECT metadata,passage FROM cuts c JOIN docs d ON d.id=c.doc WHERE 1" + clause + " ORDER BY c.rowid", values)
            available = {item["id"]: item for item in map(self._cut, rows)}
        lists = [lexical]
        if matches:
            weights = set(words)
            def score(item):
                tagged = sum(matches.get(c, 0) for c in item["concepts"])
                if not tagged:
                    return 0
                overlap = len(weights & set(tokens(item["text"])))
                return tagged + min(overlap, 4) * .04
            ranked = [(score(x), x["id"]) for x in available.values()]
            lists.append([key for weight, key in sorted(ranked, key=lambda x: -x[0]) if weight])
        # Legacy clients can still send embeddings=True. This release uses only the
        # text index and deterministic topic ranks, including on that compatibility path.
        # The index text is English. In a prose query, direct word matches carry more
        # information than a broad chapter tag. Korean and symbolic queries need the tags.
        english_prose = not re.search(r"[가-힣ㄱ-ㅎㅏ-ㅣ=^λθρπωΣ]",query) and len(re.findall(r"\b[a-zA-Z]{2,}\b",query)) >= 2
        fused = Counter()
        for i, ranking in enumerate(lists):
            weight = 4 if i == 0 and mode in {"weighted", "hybrid"} and english_prose else 1
            for rank, key in enumerate(ranking, 1):
                fused[key] += weight / (60 + rank)
        ordered = [key for key,_ in fused.most_common()]
        if mode == "hybrid" and english_prose and lexical:
            # Preserve the best direct match before combining lower ranked candidates.
            ordered.remove(lexical[0])
            ordered.insert(0, lexical[0])
        if unique_documents:
            first = {}
            for key in ordered:
                first.setdefault(available[key]["doc_id"],key)
            ordered = list(first.values())
        return [{**available[key], "rank":rank} for rank,key in enumerate(ordered[:limit],1)]

