"""Bounded text extraction. All extracted passages remain untrusted source data."""
from dataclasses import dataclass, field
from html.parser import HTMLParser
from io import BytesIO
import re
import xml.etree.ElementTree as ET

MAX_BYTES = 2 * 1024 * 1024
MAX_PAGES = 200
MAX_CHARS = 2_000_000


def clean(text):
    return " ".join(text.split())


@dataclass
class Passage:
    paragraph_id: str
    paragraph: int
    section: str
    text: str
    page: int | None = None


@dataclass
class Extraction:
    title: str = ""
    passages: list[Passage] = field(default_factory=list)
    quality: str = "text"
    formulas: str = "not detected"
    tables: str = "not detected"
    notes: list[str] = field(default_factory=list)

    def finish(self):
        if not self.passages:
            self.quality = "no_citable_text"
        return self


def tag(el):
    return el.tag.rsplit("}", 1)[-1]


def prose(el):
    """Keep exact prose and simple inline symbols. Never linearize a fraction or an exponent."""
    if tag(el) == "math":
        if any(tag(n) not in {"math", "mrow", "mi", "mn", "mo", "mtext"} for n in el.iter()):
            return "\ufffc"
        return "".join(clean(n.text or "") for n in el.iter() if not len(n))
    if tag(el) not in {"para", "term", "emphasis"}:
        return "\ufffc"
    return (el.text or "") + "".join(prose(c) + (c.tail or "") for c in el)


def uninterrupted_text(el):
    value = clean(prose(el))
    if "\ufffc" not in value:
        return value
    # A citation may be a sentence-level excerpt of a paragraph. Keep adjacent
    # sentences from one continuous span only and omit sentences touching markup.
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z(“])", value)
    runs = [""]
    for sentence in pieces:
        if "\ufffc" in sentence:
            runs.append("")
        else:
            runs[-1] = (runs[-1] + " " + sentence).strip()
    return max(runs, key=len)


def cnxml(raw):
    if re.search(br"<!\s*(DOCTYPE|ENTITY)", raw, re.I):
        raise ValueError("DTD is not permitted")
    root = ET.fromstring(raw)
    result = Extraction(clean(root.findtext("{*}title", "")))
    if root.find(".//{*}math") is not None:
        result.formulas = "MathML present; excluded from excerpts"
    if root.find(".//{*}table") is not None:
        result.tables = "structured tables present; excluded"
    ordinal = 0

    def walk(el, section):
        nonlocal ordinal
        kind = tag(el)
        if kind == "section":
            section = clean(el.findtext("{*}title", "")) or section
        if kind == "para":
            ordinal += 1
            # Publish only continuous, standalone prose. Figure identifiers,
            # external links, embedded equations and exercises require other context.
            if not el.get("id"):
                return
            text = uninterrupted_text(el)
            if 65 <= len(text) <= 1800:
                result.passages.append(Passage(el.get("id"), ordinal, section, text))
        elif kind in {"content", "section", "note"}:
            for child in el:
                walk(child, section)

    content = root.find("{*}content")
    if content is None:
        raise ValueError("CNXML has no content")
    walk(content, result.title)
    return result.finish()


class StructuredHTML(HTMLParser):
    """Capture paragraph/heading text and omit navigation, tables and active content."""
    SKIP = {"script", "style", "nav", "header", "footer", "aside", "form", "svg", "math", "table", "template", "noscript"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.result = Extraction()
        self.block = ""
        self.parts = []
        self.section = ""
        self.hidden = []
        self.paragraph = 0
        self.anchor = ""

    def handle_starttag(self, name, attrs):
        if name == "table":
            self.result.tables = "HTML table present; excluded"
        if name == "math":
            self.result.formulas = "MathML present; excluded"
            self.result.quality = "limited_layout"
            if self.block == "p" and not self.hidden:
                self.parts.append(" [omitted MathML] ")
        if name in self.SKIP:
            self.hidden.append(name)
        if self.hidden:
            return
        if name in {"title", "h1", "h2", "h3", "h4", "p"}:
            self.flush()
            self.block, self.anchor = name, dict(attrs).get("id") or ""
        elif name == "br":
            self.parts.append(" ")

    def handle_endtag(self, name):
        if self.hidden:
            if self.hidden[-1] == name:
                self.hidden.pop()
            return
        if name == self.block:
            self.flush()

    def handle_data(self, data):
        if self.block and not self.hidden:
            self.parts.append(data)

    def flush(self):
        text = clean("".join(self.parts))
        if self.block == "title" or (self.block == "h1" and not self.result.title):
            self.result.title = text
        if self.block.startswith("h"):
            self.section = text
        if self.block == "p" and text:
            self.paragraph += 1
            self.result.passages.append(Passage(self.anchor or f"p{self.paragraph}", self.paragraph, self.section, text))
        self.block, self.parts = "", []


def markdown(text):
    result = Extraction()
    if re.search(r"\$[^$\n]+\$|\\\(|\\\[", text):
        result.formulas = "inline mathematical notation retained as source text; unverified"
    section = ""
    buffer = []
    fenced = False

    def paragraph():
        if buffer:
            number = len(result.passages) + 1
            result.passages.append(Passage(f"p{number}", number, section, clean(" ".join(buffer))))
            buffer.clear()

    for line in text.splitlines():
        if re.match(r"^\s*(?:```|~~~)", line):
            paragraph()
            fenced = not fenced
        elif not fenced:
            heading = re.match(r"^#{1,6}\s+(.+)", line)
            if heading:
                paragraph()
                section = heading[1].strip()
                result.title = result.title or section
            elif "|" in line and line.count("|") >= 2:
                paragraph()
                result.tables = "Markdown table present; excluded"
            elif line.strip():
                buffer.append(line.strip())
            else:
                paragraph()
    paragraph()
    return result.finish()


def pdf(raw):
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(raw), strict=True)
    if reader.is_encrypted or len(reader.pages) > MAX_PAGES:
        raise ValueError("Encrypted or oversized PDF")
    result = Extraction(title=getattr(reader.metadata, "title", "") or "", quality="limited_layout",
                        formulas="unverified PDF glyph order", tables="unverified PDF layout")
    count = 0
    for number, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        count += len(text)
        if count > MAX_CHARS:
            raise ValueError("Extracted PDF text exceeds limit")
        if not text.strip():
            result.notes.append(f"p.{number}: no text layer; OCR unavailable")
        for i, block in enumerate(re.split(r"\n\s*\n", text), 1):
            if clean(block):
                result.passages.append(Passage(f"p{number}-{i}", i, "", clean(block), number))
    return result.finish()


def extract_document(raw: bytes, kind: str):
    if len(raw) > MAX_BYTES:
        raise ValueError("Document exceeds byte limit")
    if kind == "cnxml":
        return cnxml(raw)
    if kind == "pdf":
        return pdf(raw)
    text = raw.decode("utf-8-sig")
    if kind in {"md", "markdown"}:
        return markdown(text)
    if kind == "html":
        parser = StructuredHTML()
        parser.feed(text)
        parser.close()
        parser.flush()
        return parser.result.finish()
    raise ValueError("Unsupported document format")

