"""Benchmark contract tests use synthetic responses, never a real provider or final-case answer keys."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import sys
from uuid import uuid4

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import benchmark_v3 as bench
from benchmark_scoring import REVIEW_BY_CATEGORY, apply_review, automatic, numeric_match, review_sheet, summarize
from physis.physics import SPECS
from physis.provider_config import ProviderSelection
from physis.providers import _generate
from physis.schema import Patch
from physis.state import build


def test_split_structure_and_golds_are_separate_from_the_tutor():
    dev, final = bench.dataset("development"), bench.dataset("final")
    assert len(dev) + len(final) >= 80
    for rows in (dev, final):
        assert set(Counter(c["category"] for c in rows)) == set(REVIEW_BY_CATEGORY)
        assert all(c["basis"] and c["reference_url"] for c in rows)
    assert {c["id"] for c in dev}.isdisjoint(c["id"] for c in final)
    assert {c["question"] for c in dev}.isdisjoint(c["question"] for c in final)


def test_numeric_checks_the_named_quantity_unit_and_conflicting_prose():
    target = ["my_speed", "측정 속력", 1.5, "m/s"]
    ans = {"numbers": [{"key": "my_speed", "value": 1.5, "unit": "m/s"}], "text": ""}
    assert numeric_match(target, ans)
    assert not numeric_match(target, {**ans, "text": "측정 속력은 1.8 m/s"})
    assert not numeric_match(target, {"numbers": [], "text": "다른 속력은 1.5 m/s"})
    assert not numeric_match(target, {"text": "측정 속력은 1.5 m/s²"})
    assert numeric_match(target, {"text": "측정 속력은 1.500 m/s이다."})


def test_source_record_must_match_original_and_missing_citation_is_scored():
    chunk = {"id": "c", "url": "https://example.org/a", "locator": "§2 ¶3",
             "text": "At equilibrium the temperatures are equal."}
    citation = {"id": "c", "url": chunk["url"], "locator": chunk["locator"], "quote": "temperatures are equal"}
    source_case = {"category": "citation"}
    ok = automatic(source_case, {"citations": [citation]}, lambda key: chunk if key == "c" else None)
    assert ok["source_trace"] == ok["requested_source_trace"] == [1, 1]
    for field, value in {"id": "other", "url": "bad", "locator": "p4", "quote": "fabricated sentence"}.items():
        checks = automatic(source_case, {"citations": [{**citation, field: value}]}, lambda k: chunk if k == "c" else None)
        assert checks["source_trace"] == [0, 1]
    assert automatic(source_case, {}, lambda k: None)["requested_source_trace"] == [0, 1]
    assert automatic({"category": "fabricated", "bait": "GHOST"}, {"citations": [{"id": "book-GHOST"}]}, lambda _: None)["fabricated_source_attribution"] == [1, 1]


def test_three_real_arms_use_same_model_and_question_and_only_requested_context(monkeypatch):
    exp = build(SPECS["uniform"], uuid4(), Patch(values={"v0": 1.25}, duration=2))
    snap = {"experiment": exp.model_dump(mode="json"), "revision": 3}
    selected = ProviderSelection(provider="compatible", model="fixture/controlled")
    monkeypatch.setenv("PHYSIS_COMPATIBLE_BASE_URL", "http://127.0.0.1:19999/v1")
    monkeypatch.delenv("PHYSIS_COMPATIBLE_API_KEY", raising=False)
    requests = []
    result = {"text": "test", "formula": "", "numbers": [], "citations": [],
              "simulation_supported": True, "ran_simulation": False}

    def receive(request):
        body = json.loads(request.content)
        requests.append(body)
        message = {"role": "assistant", "content": json.dumps(result)}
        return httpx.Response(200, json={"choices": [{"message": message, "finish_reason": "stop"}],
                                         "usage": {"prompt_tokens": 11, "completion_tokens": 7}})

    async def local_generation(name, instructions, payload, schema, unused_transport):
        return await _generate(name, instructions, payload, schema, httpx.MockTransport(receive))

    class Store:
        def search(self, query, model, limit):
            return [{"id": "c", "title": "Book", "url": "https://example.org/a", "locator": "§1", "text": "example"}]

    contexts = []
    for arm in bench.ARMS[1:]:
        calls, receipts = [], []
        answer, _ = bench.real_turn(arm, "Fixture question?", snap, [], Store(), selected, calls, receipts, local_generation)
        assert answer == result and calls[0]["input_tokens"] == 11
        assert bench.cost(calls, (1, 2)) == pytest.approx(25e-6)
        contexts.append(json.loads(requests[-1]["messages"][1]["content"]))
    assert all(r["model"] == "fixture/controlled" and r["messages"][0] == requests[0]["messages"][0] for r in requests)
    assert all(ctx["question"] == "Fixture question?" and "basis" not in ctx for ctx in contexts)
    assert set(contexts[1]) == set(contexts[0]) | {"passages"}
    assert set(contexts[2]) == set(contexts[1]) | {"active_run"}
    assert contexts[1]["passages"] == contexts[2]["passages"]
    assert contexts[2]["active_run"]["facts"]["final_position"] == pytest.approx(2.5)
    assert bench.cost([], (1, 2)) is None
    assert bench.cost([{"input_tokens": None, "output_tokens": 4}], (1, 2)) is None


def test_partial_review_requires_matching_responses_and_preserves_missing_denominators():
    case = {"category": "formula", "question": "Generic?", "reference_url": "§1", "basis": "generic rubric"}
    row = {"case": case, "answer": {"text": "abc"}, "checks": {}, "dialogue": [],
           "status": "ok", "latency_ms": 3, "cost_usd_estimate": None}
    report = {"run_id": "r1", "arms": {"mock": {"rows": [row]}}}
    sheet = {"run_id": "r1", "reviewer": "fixture reviewer", "samples": review_sheet(report)}
    rating = sheet["samples"][0]
    assert "arm" not in rating
    assert summarize([row])["metrics"]["formula_accuracy"]["d"] == 0
    rating.update(passes=False, claims_total=2, claims_unsupported=1, notes="One false assertion.")
    result = apply_review(deepcopy(report), sheet)["arms"]["mock"]["summary"]
    assert result["metrics"]["formula_accuracy"] == {"n": 0, "d": 1}
    assert result["metrics"]["unsupported_claim_rate"] == {"n": 1, "d": 2}
    assert result["estimated_total_usd"] is None
    rating["answer"] = {"text": "tampered response"}
    with pytest.raises(ValueError):
        apply_review(report, sheet)


def test_real_call_cli_gate_fails_before_network(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["benchmark", "--provider", "openai"])
    with pytest.raises(SystemExit) as error:
        bench.main()
    assert error.value.code == 2


def test_no_provider_key_keeps_all_real_arms_unmeasured(monkeypatch):
    monkeypatch.setattr(bench, "endpoint", lambda _: ("https://example.invalid", {}))
    def accidental_call(*args):
        pytest.fail("Real transport was used without a configured credential.")
    monkeypatch.setattr(bench, "real_turn", accidental_call)
    selected = ProviderSelection(provider="compatible", model="classroom")
    report = bench.evaluate(limit=1, selection=selected)
    assert report["arms"]["mock"]["summary"]["responses"] == 1
    assert all(report["arms"][arm]["status"] == "unmeasured" for arm in bench.ARMS[1:])
