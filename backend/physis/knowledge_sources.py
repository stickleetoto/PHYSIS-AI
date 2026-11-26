"""Fixed first-party download adapters. No externally supplied addresses or document directives."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler, Request
import xml.etree.ElementTree as ET

from .knowledge_processing import extract_document, MAX_BYTES


CORPUS = Path(__file__).with_name("corpus")
CACHE_LIMIT = 64 * 1024 * 1024
HOSTS = {"raw.githubusercontent.com", "www1.grc.nasa.gov", "ntrs.nasa.gov"}
BOOKS = {
    "college": ("osbooks-college-physics-bundle", "84147e8ddbb1a7d2689e235630b230e6b4f20480",
                "college-physics-2e", "Paul Peter Urone; Roger Hinrichs; OpenStax contributors", "school"),
    "university1": ("osbooks-university-physics-bundle", "9364cbc32511afea3d4695e70a88687ffc1a3696",
                    "university-physics-volume-1", "Samuel J. Ling; Jeff Sanny; William Moebs; OpenStax contributors", "university"),
    "university2": ("osbooks-university-physics-bundle", "9364cbc32511afea3d4695e70a88687ffc1a3696",
                    "university-physics-volume-2", "Samuel J. Ling; Jeff Sanny; William Moebs; OpenStax contributors", "university"),
}
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as tmp:
        name = Path(tmp.name)
        try:
            tmp.write(raw)
        except Exception:
            tmp.close()
            name.unlink(missing_ok=True)
            raise
    try:
        os.replace(name, path)
    finally:
        name.unlink(missing_ok=True)


def serialize(data):
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()


def allowed_url(url):
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.netloc in HOSTS


class ReviewedRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise ValueError("Redirect outside approved source hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class DownloadCache:
    def __init__(self, path, refresh=False, offline=False):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.refresh = refresh
        self.offline = offline
        self.next_request = 0.0
        # Use the CA bundle shipped with the existing httpx dependency.
        import certifi
        self.opener = build_opener(ReviewedRedirects(), HTTPSHandler(context=ssl.create_default_context(cafile=certifi.where())))

    def get(self, url):
        if not allowed_url(url):
            raise ValueError("Unapproved source host")
        key = sha(url.encode())
        entry = self.path / f"{key}.json"
        if entry.exists() and (not self.refresh or self.offline):
            info = json.loads(entry.read_bytes())
            digest = info.get("sha256", "")
            if info.get("url") != url or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("Invalid cache entry")
            blob = self.path / digest
            if blob.stat().st_size > MAX_BYTES:
                raise ValueError("Cached source exceeds limit")
            body = blob.read_bytes()
            if sha(body) != digest:
                raise ValueError("Cache checksum mismatch")
            return body, info
        if self.offline:
            raise ValueError("Missing offline cache entry")
        time.sleep(max(0, self.next_request - time.monotonic()))
        self.next_request = time.monotonic() + .35
        request = Request(url, headers={"User-Agent": "PHYSIS-Education-Corpus/0.3"})
        with self.opener.open(request, timeout=18) as res:
            if int(res.headers.get("Content-Length") or 0) > MAX_BYTES:
                raise ValueError("Source exceeds limit")
            body = res.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            raise ValueError("Source exceeds limit")
        digest = sha(body)
        info = {"url": url, "sha256": digest, "bytes": len(body),
                "downloaded": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        blob = self.path / digest
        receipt = self.path / f"{key}.{digest}.receipt"
        info_bytes = serialize(info)
        total = sum(p.stat().st_size for p in self.path.iterdir() if p.is_file())
        if total + (0 if blob.exists() else len(body)) + 2 * len(info_bytes) > CACHE_LIMIT:
            raise ValueError("Cache exceeds storage budget")
        if not blob.exists():
            atomic(blob, body)
        if not receipt.exists():
            atomic(receipt, info_bytes)
        atomic(entry, info_bytes)
        return body, info


class OpenStax:
    def __init__(self, source, cache):
        repo, self.version, slug, self.author, self.level = BOOKS[source]
        self.cache = cache
        self.source = source
        self.root = f"https://raw.githubusercontent.com/openstax/{repo}/{self.version}/"
        self.browse = f"https://github.com/openstax/{repo}/blob/{self.version}/"
        self.slug = slug
        license_body, self.license_record = cache.get(self.root + "LICENSE")
        if not license_body.startswith(b"Attribution 4.0 International"):
            raise ValueError("Repository license requires human review")
        collection, self.collection_record = cache.get(self.root + f"collections/{slug}.collection.xml")
        root = ET.fromstring(collection)
        metadata = root.find("{*}metadata")
        license_tag = metadata.find("{*}license")
        if license_tag is None or license_tag.get("url", "").replace("http://", "https://") != LICENSE_URL:
            raise ValueError("Book-level license requires human review")
        self.book = metadata.findtext("{*}title")
        self.members = {mod.get("document"): group.findtext("{*}title", "")
                        for group in root.findall(".//{*}subcollection")
                        for mod in group.findall("{*}content/{*}module")}

    def get(self, spec, preview=False):
        module = spec["module"]
        if module not in self.members:
            raise ValueError("Module not present in pinned book")
        rel = f"modules/{module}/index.cnxml"
        raw, info = self.cache.get(self.root + rel)
        if not preview and sha(raw) != spec.get("raw_sha256"):
            raise ValueError(f"Reviewed source checksum changed: {module}")
        parsed = extract_document(raw, "cnxml")
        identity = f"{self.source}-{module}"
        doc = dict(id=identity, source_id=self.source, title=parsed.title, book=self.book, chapter=self.members[module],
                   language="en", publisher="OpenStax, Rice University", author=self.author,
                   url=self.browse + rel, source_url=info["url"], version=self.version,
                   license="CC BY 4.0", license_url=LICENSE_URL, license_evidence=self.license_record,
                   collection_evidence=self.collection_record, license_scope="selected textbook prose",
                   sha256=info["sha256"], downloaded=info["downloaded"], bytes=info["bytes"],
                   level=self.level, models=spec["models"], concepts=spec["concepts"], kind="cnxml",
                   formulas=parsed.formulas, tables=parsed.tables, quality="selected_prose", citable=True)
        chosen = set(spec.get("paragraphs", []))
        chunks = []
        for part in parsed.passages:
            if not preview and part.paragraph_id not in chosen:
                continue
            marker = ('id="' + part.paragraph_id + '"').encode()
            pos = raw.index(marker)
            line = 1 + raw[:pos].count(b"\n")
            chunks.append(dict(**asdict(part), id=f"{identity}:{part.paragraph_id}", doc_id=identity,
                               url=doc["url"] + f"#L{line}", locator=f"{part.section} · ¶{part.paragraph} ({part.paragraph_id})",
                               text_sha256=sha(part.text.encode())))
        if not preview and (not chunks or {c["paragraph_id"] for c in chunks} != chosen):
            raise ValueError(f"Selection requires review: {identity}")
        if not preview:
            order = {key: i for i, key in enumerate(spec["paragraphs"])}
            chunks.sort(key=lambda c: order[c["paragraph_id"]])
        return dict(**doc, chunks=chunks)


def nasa_metadata(cache, spec):
    source = spec["source"]
    if source == "glenn":
        slug = spec["module"]
        url = f"https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/{slug}/"
        raw, info = cache.get(url)
        parsed = extract_document(raw, "html")
        title = parsed.title.split("|")[0].strip()
        if title.casefold() != spec["expected_title"].casefold():
            raise ValueError(f"NASA Glenn title changed: {title}")
        publisher = "NASA Glenn Research Center"
        author = publisher
        book = "Beginner’s Guide to Aeronautics"
        rights = "https://www.nasa.gov/nasa-brand-center/images-and-media/"
        determination = "Source-level reuse reviewed separately for each item"
    elif source == "ntrs":
        number = spec["module"]
        url = f"https://ntrs.nasa.gov/citations/{number}"
        raw, info = cache.get(f"https://ntrs.nasa.gov/api/citations/{number}")
        item = json.loads(raw)
        if str(item["id"]) != number or item.get("distribution") != "PUBLIC":
            raise ValueError("NTRS record not public or changed identity")
        title = item["title"]
        names = [a.get("meta", {}).get("author", {}).get("name") for a in item.get("authorAffiliations", [])]
        author = "; ".join(name for name in names if name) or "Not stated in public metadata"
        publisher = "NASA Technical Reports Server"
        book = "NTRS"
        rights = "https://sti.nasa.gov/disclaimers/"
        determination = item.get("copyright", {}).get("determinationType", "UNSPECIFIED")
    else:
        raise ValueError("Unknown adapter")
    return dict(id=f"{source}-{spec['module']}", source_id=source, title=title, book=book, chapter="",
                publisher=publisher, author=author, url=url, source_url=info["url"], version=info["sha256"],
                language="en", license="Bibliographic metadata only", license_url=rights, license_scope=determination,
                sha256=info["sha256"], bytes=info["bytes"], downloaded=info["downloaded"],
                level=spec["level"], models=spec["models"], concepts=spec["concepts"], kind="metadata",
                quality="metadata_only", formulas="not collected", tables="not collected", citable=False, chunks=[])

