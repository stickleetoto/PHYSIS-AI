from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import sqlite3

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from physis.knowledge import KnowledgeStore
from physis.knowledge_api import router
from physis.knowledge_processing import extract_document, MAX_BYTES
from physis.knowledge_sources import CORPUS, DownloadCache, atomic, sha
from physis.physics import SPECS


@pytest.fixture
def store(tmp_path):
    k = KnowledgeStore(tmp_path / "public.sqlite3")
    k.initialize()
    return k


def test_seed_integrity_and_rights(store):
    facts = store.stats()
    assert facts["documents"] == 49 and facts["chunks"] == 116
    docs = store.documents()
    assert set(SPECS) == {m for doc in docs for m in doc["models"]}
    for doc in docs:
        detail = store.document(doc["id"])
        assert len(detail["chunks"]) == doc["chunk_count"]
        if doc["citable"]:
            assert doc["license"] == "CC BY 4.0" and len(doc["version"]) == 40
            assert doc["collection_evidence"]["url"].endswith(".collection.xml")
            for c in detail["chunks"]:
                assert c == store.chunk(c["id"])
                assert c["text_sha256"] == sha(c["text"].encode())
                assert c["paragraph_id"] in c["locator"] and "#L" in c["url"]
        else:
            assert not detail["chunks"] and doc["source_id"] in {"glenn","ntrs"}


def test_filters_exact_symbols_and_unknowns(store):
    assert store.search("T = 2π√(L/g)", limit=1)[0]["doc_id"] == "college-m42243"
    assert store.search("F = ma", limit=1)[0]["paragraph_id"] == "import-auto-id1355832"
    assert store.search("ρ", limit=1)[0]["concepts"] == ["density"]
    assert store.search("λ", limit=1)[0]["concepts"] == ["wave"]
    assert store.search("진자", mode="lexical") == []
    cuts = store.search("진자", model="pendulum", source="university1", level="university")
    assert cuts and all(x["source_id"] == "university1" and x["level"] == "university" for x in cuts)
    assert not store.search("newton", source="ntrs")
    assert not store.search("양자색역학")
    assert not store.search('") OR *** NEAR()')
    with pytest.raises(ValueError):
        store.search("x", limit=3000)
    assert store.related("university1-m58364")[0]["id"] == "college-m42243"


def test_legacy_embedding_request_uses_filtered_text_index(store):
    cuts = store.search("standing waves", model="wave_standing", mode="hybrid", embeddings=True)
    assert cuts and all("wave_standing" in c["models"] for c in cuts)
    assert cuts == store.search("standing waves", model="wave_standing", mode="hybrid")
    assert store.search("zzqqxx", embeddings=True) == []


def test_source_removal_is_durable_and_reversible(store):
    original = store.stats()
    first = store.search("진자", source="college")[0]
    store.delete_source("college")
    new = KnowledgeStore(store.path)
    new.initialize()
    assert new.stats()["deleted_sources"] == ["college"] and new.chunk(first["id"]) is None
    assert not new.search("pendulum", source="college") and new.search("pendulum", source="university1")
    new.reindex_source("college")
    new.reindex_source("college")
    assert new.stats() == original and new.chunk(first["id"])["text"] == first["text"]
    with pytest.raises(KeyError):
        new.delete_source("unknown")


def test_concurrent_first_run_and_wrong_database(tmp_path):
    target = tmp_path / "public.sqlite3"
    with ThreadPoolExecutor(4) as pool:
        list(pool.map(lambda _: KnowledgeStore(target).initialize(), range(4)))
    assert KnowledgeStore(target).stats()["chunks"] == 116
    private = tmp_path / "experiments.sqlite3"
    with sqlite3.connect(private) as db:
        db.execute("CREATE TABLE experiments(id TEXT)")
    with pytest.raises(ValueError, match="공개 문헌 전용"):
        KnowledgeStore(private).initialize()
    with sqlite3.connect(private) as db:
        assert [row[0] for row in db.execute("SELECT name FROM sqlite_master")] == ["experiments"]


def test_corrupt_payload_is_rejected_atomically(tmp_path, store):
    body = json.loads((CORPUS / "units.json").read_bytes())
    body[0]["chunks"][0]["text"] += " changed"
    data = json.dumps(body).encode()
    target = tmp_path / "modified.json"
    target.write_bytes(data)
    target.with_suffix(".sha256").write_text("0"*64)
    bad = KnowledgeStore(store.path, target)
    with pytest.raises(ValueError, match="SHA-256"):
        bad.initialize()
    target.with_suffix(".sha256").write_text(sha(data))
    with pytest.raises(ValueError, match="해시"):
        bad.initialize()
    assert store.stats()["documents"] == 49 and store.chunk(body[0]["chunks"][0]["id"])["text"] != body[0]["chunks"][0]["text"]


def test_download_cache_validates_bytes_hosts_and_missing_entries(tmp_path):
    cache = DownloadCache(tmp_path, offline=True)
    url = "https://ntrs.nasa.gov/api/citations/19970022278"
    data = b"sample record"
    info = {"url":url, "sha256":sha(data), "downloaded":"2025-01-01", "bytes":len(data)}
    atomic(tmp_path / (sha(url.encode()) + ".json"), json.dumps(info).encode())
    atomic(tmp_path / info["sha256"], data)
    assert cache.get(url) == (data, info)
    atomic(tmp_path / info["sha256"], b"modified")
    with pytest.raises(ValueError, match="checksum"):
        cache.get(url)
    with pytest.raises(ValueError, match="host"):
        cache.get("https://other.invalid/")
    with pytest.raises(ValueError, match="Missing"):
        cache.get("https://ntrs.nasa.gov/api/citations/2")


def test_html_markdown_structure_and_inert_text():
    source = b"<title>Units</title><nav><p>Navigation</p></nav><h2>SI</h2><p id='p1'>Length is <em>measured</em> in metres.</p><p>Data<script>not included()</script> only</p><table><tr><td>x</td></tr></table>"
    html = extract_document(source,"html")
    assert html.title == "Units" and [p.text for p in html.passages] == ["Length is measured in metres.","Data only"]
    assert (html.passages[0].section, html.passages[0].paragraph_id) == ("SI", "p1")
    assert "excluded" in html.tables
    md = extract_document(b"# Units\n\n## SI\n\nLength in metres.\n\n```\nignored()\n```\n\nA formula $x$\n\n|x|y|","md")
    assert [p.text for p in md.passages] == ["Length in metres.","A formula $x$"]
    assert md.passages[0].section == "SI" and md.title == "Units"
    assert "notation" in md.formulas and "excluded" in md.tables
    with pytest.raises(ValueError, match="byte"):
        extract_document(b"x"*(MAX_BYTES+1), "html")
    with pytest.raises(ValueError, match="DTD"):
        extract_document(b"<!DOCTYPE x><document/>", "cnxml")


def test_text_pdf_page_anchors_and_missing_layer():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(200,200)
    font = DictionaryObject({NameObject("/Type"):NameObject("/Font"), NameObject("/Subtype"):NameObject("/Type1"),
                             NameObject("/BaseFont"):NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):DictionaryObject({NameObject("/F1"):font})})
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 15 120 Td (Uniform motion) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    writer.add_blank_page(200,200)
    data = BytesIO()
    writer.write(data)
    result = extract_document(data.getvalue(),"pdf")
    assert result.quality == "limited_layout"
    assert [(p.text,p.page,p.paragraph) for p in result.passages] == [("Uniform motion",1,1)]
    assert any("p.2" in n for n in result.notes)


def test_api_uses_canonical_passage_and_does_not_expose_maintenance(store):
    app = FastAPI()
    app.state.knowledge = store
    app.include_router(router)
    with TestClient(app) as client:
        hit = client.get("/api/knowledge/search", params={"q":"부력","limit":1}).json()["items"][0]
        assert client.get("/api/knowledge/chunks/" + hit["id"]).json()["text"] == hit["text"]
        meta = client.get("/api/knowledge/documents", params={"q":"drag","source":"glenn"}).json()["items"]
        assert len(meta) == 1 and not meta[0]["citable"]
        assert client.get("/api/knowledge/documents/" + meta[0]["id"]).json()["chunks"] == []
        assert client.delete("/api/knowledge/documents/" + meta[0]["id"]).status_code == 405
        assert client.get("/api/knowledge/chunks/fake").status_code == 404
        assert client.get("/api/knowledge/search",params={"q":"x","mode":"invalid"}).status_code == 422

