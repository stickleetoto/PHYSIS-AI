"""A period, paragraph or book title does not authenticate additional bibliographic claims."""
import pytest
from physis.grounded import reading_only, specialty
from physis.knowledge import KnowledgeStore


@pytest.fixture(scope="module")
def literature(tmp_path_factory):
    store = KnowledgeStore(tmp_path_factory.mktemp("library") / "public.sqlite3")
    store.initialize()
    return store


def response(store, question):
    assert specialty(question) == "literature"
    result, _ = reading_only(store, question, "explain", "school", "literature")
    return result["evidence"]


@pytest.mark.parametrize("request_text", [
    "Cite “Pendulums” by An Invented Author.",
    "Cite “Pendulums”, 45th edition.",
    "Cite “Pendulums” (1872).",
    "Cite “Pendulums”, DOI 10.0000/unknown.",
    "《Pendulums》를 인용해줘. 저자 가짜이름, 2021년 출판.",
    "Cite “Pendulums”, section “The Simple Pendulum”, page 999.",
    "Cite “Pendulums”, section “The Simple Pendulum”, paragraph 1.",
    "Cite “Pendulums”, section “Samuel J. Ling”.",
    "《Pendulums》 절 “Samuel J. Ling” 인용해 주세요.",
    "Cite “Pendulums” by The Simple Pendulum.",
    "Cite “Pendulums”, section “Nonexistent Heading”.",
])
def test_unverified_qualifiers_never_confirm_a_real_title(literature, request_text):
    report = response(literature, request_text)
    assert not report["sources"] and report["theory_status"] == "insufficient"
    assert all(c["status"] != "source_verified" for c in report["claims"])


@pytest.mark.parametrize("request_text", [
    "《Pendulums》의 원문을 인용해 주세요.",
    "Please cite “Pendulums”.",
    "Cite the section titled “Pendulums”.",
    "Cite “Pendulums” by Samuel J. Ling.",
    'Quote "Newton\'s Second Law".',
])
def test_exact_unqualified_title_and_recorded_author(literature, request_text):
    report = response(literature, request_text)
    assert report["sources"] and report["theory_status"] == "available"


def test_section_and_paragraph_must_belong_to_same_record(literature):
    report = response(literature, "Cite “Pendulums”, section “The Simple Pendulum”, paragraph 2.")
    assert len(report["sources"]) == 1
    source = report["sources"][0]
    assert source["doc_id"] == "university1-m58364"
    assert "The Simple Pendulum · ¶2" in source["locator"]
    assert source["quote"] in literature.chunk(source["id"])["text"]

