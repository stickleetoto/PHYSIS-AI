import asyncio
import json

import httpx
import pytest

from physis import providers
from physis.provider_config import ProviderSelection, provider_context


def _context():
    return {
        "question": "Why does acceleration change?",
        "level": "school",
        "intents": ["concept_explanation"],
        "model": "newton",
        "inputs": {"mass": 2, "force": 8},
        "history": [],
        "passages": [{"id": "source-1", "quote": "Acceleration is proportional to net force."}],
        "formula": {"title": "Newton's second law", "formula_id": "newton.second_law",
                    "status": "partial", "conditions": ["small-angle approximation"],
                    "applicability": {"status": "outside_conditions", "reason": "Angle is too large."},
                    "variables": [{"key": "angle", "min": 0, "max": 1}]},
        "calculations": [{"key": "acceleration", "label": "acceleration", "value": 4,
                          "unit": "m/s^2", "run_id": "run-1"}],
        "conditions": ["Friction is ignored."],
        "catalog": [{"model": "must-not-be-sent", "variables": ["all", "of", "them"]}],
    }


def _ollama_stream(answer, *, usage=True):
    final = {"model": "test", "message": {"role": "assistant", "content": json.dumps(answer)},
             "done": True, "done_reason": "stop"}
    if usage:
        final.update(prompt_eval_count=23, eval_count=41, load_duration=120_000_000,
                     eval_duration=900_000_000)
    return httpx.Response(200, content=(json.dumps(final) + "\n").encode())


def _resident_response():
    return httpx.Response(200, json={"models": [{"name": "qwen2.5:3b"}]})


def test_explanation_filters_optional_metadata_and_records_numeric_proposal():
    answer = {
        "text": "Increasing net force increases acceleration.",
        "source_ids": ["source-1", "forged-source"],
        "assumptions": ["Friction is ignored.", "Unverified condition"],
        "uncertainty": "This model does not include friction.",
        "numeric_claims": [{"key": "acceleration", "value": 4.1, "unit": "m/s^2",
                            "experiment_id": "exp-1", "revision": 1, "run_id": "run-1"}],
        "actions": [{"op": "change_conditions", "patch": {"values": {"mass": 100}}}],
        "application_state": {"learning_level": "research"},
        "level": "research",
        "unrecognized": "ignored",
    }
    requests = []
    paths = []

    def handle(request):
        paths.append(request.url.path)
        if request.method == "GET":
            return _resident_response()
        requests.append(json.loads(request.content))
        return _ollama_stream(answer)

    selection = ProviderSelection(provider="ollama", model="qwen2.5:3b")
    context = _context() | {"history": [{"question": "What did I ask before?", "answer": "A prior response."}]}
    with provider_context(selection) as metrics:
        result = asyncio.run(providers.request_explanation(
            "ollama", context, transport=httpx.MockTransport(handle)))

    assert result.text == answer["text"]
    assert result.source_ids == ["source-1"]
    assert result.assumptions == ["Friction is ignored."]
    assert result.uncertainty == answer["uncertainty"]
    assert result.warnings
    assert "forged-source" not in json.dumps(result.model_dump())
    assert "change_conditions" not in json.dumps(result.model_dump())
    assert metrics.proposed_numbers == answer["numeric_claims"]
    assert len(requests) == 1 and paths == ["/api/ps", "/api/chat"]
    user_context = json.loads(requests[0]["messages"][1]["content"])
    assert "catalog" not in user_context and "schema" not in user_context
    assert user_context["passages"] == _context()["passages"]
    assert user_context["history"] == context["history"]
    assert user_context["formula"]["status"] == "partial"
    assert user_context["formula"]["conditions"] == ["small-angle approximation"]
    assert user_context["formula"]["applicability"]["status"] == "outside_conditions"
    assert "variables" not in user_context["formula"]
    assert set(user_context) == {"question", "level", "intents", "model", "inputs", "history",
                                 "passages", "formula", "calculations", "conditions"}
    record = metrics.requests[-1]
    assert record["operation"] == "explanation" and record["status"] == "ok"
    assert record["input_tokens"] == 23 and record["output_tokens"] == 41
    assert record["ttft_ms"] is not None and record["latency_ms"] >= 0
    assert record["model_load_ms"] == 120 and record["generation_ms"] == 900
    assert "invalid_level_dropped" in result.warnings
    assert "unverified_numeric_claim_reported" in result.warnings


def test_invalid_optional_metadata_is_dropped_without_losing_text():
    answer = {"text": "The observed result and theory should be distinguished.", "source_ids": "not-a-list",
              "assumptions": [42], "uncertainty": ["invalid"], "numeric_claims": ["bad"]}

    def handle(_):
        if _.method == "GET":
            return _resident_response()
        return _ollama_stream(answer, usage=False)

    with provider_context(ProviderSelection(provider="ollama", model="qwen2.5:3b")):
        result = asyncio.run(providers.request_explanation(
            "ollama", _context(), transport=httpx.MockTransport(handle)))

    assert result.text == answer["text"]
    assert result.source_ids == [] and result.assumptions == [] and result.uncertainty is None
    assert result.warnings


def test_empty_explanation_is_rejected_without_retry():
    calls = []

    def handle(request):
        calls.append(request.url.path)
        if request.method == "GET":
            return _resident_response()
        return _ollama_stream({"text": "  ", "source_ids": [], "assumptions": [], "uncertainty": None})

    with provider_context(ProviderSelection(provider="ollama", model="qwen2.5:3b")):
        with pytest.raises(providers.ProviderError):
            asyncio.run(providers.request_explanation(
                "ollama", _context(), transport=httpx.MockTransport(handle)))
    assert calls == ["/api/ps", "/api/chat"]


def test_ollama_preload_is_a_separate_non_streaming_request():
    seen = []

    def handle(request):
        body = json.loads(request.content)
        seen.append((request.url.path, body))
        return httpx.Response(200, json={"done": True, "load_duration": 500_000_000,
                                         "total_duration": 700_000_000})

    with provider_context(ProviderSelection(provider="ollama", model="qwen2.5:3b")) as metrics:
        result = asyncio.run(providers.preload_ollama_model(transport=httpx.MockTransport(handle)))

    assert result["model_load_ms"] == 500
    assert len(seen) == 1 and seen[0][0] == "/api/generate"
    assert "messages" not in seen[0][1] and not seen[0][1].get("prompt")
    record, = metrics.requests
    assert record["operation"] == "preload" and record["status"] == "ok"


def test_cold_ollama_is_preloaded_before_inference_with_distinct_metrics():
    seen = []

    def handle(request):
        seen.append(request.url.path)
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        if request.url.path == "/api/generate":
            return httpx.Response(200, json={"done": True, "load_duration": 800_000_000,
                                             "total_duration": 900_000_000})
        return _ollama_stream({"text": "The explanation follows the supplied evidence."})

    with provider_context(ProviderSelection(provider="ollama", model="qwen2.5:3b")) as metrics:
        result = asyncio.run(providers.request_explanation(
            "ollama", _context(), transport=httpx.MockTransport(handle)))

    assert result.text == "The explanation follows the supplied evidence."
    assert seen == ["/api/ps", "/api/generate", "/api/chat"]
    assert [row["operation"] for row in metrics.requests] == ["resident_check", "preload", "explanation"]
    assert metrics.requests[1]["model_load_ms"] == 800


def test_plain_prose_is_salvaged_only_as_unreferenced_text():
    plain = "The acceleration depends on the net force and the mass of the object."

    def handle(request):
        if request.method == "GET":
            return _resident_response()
        body = {"model": "test", "message": {"role": "assistant", "content": plain},
                "done": True, "done_reason": "stop"}
        return httpx.Response(200, content=(json.dumps(body) + "\n").encode())

    with provider_context(ProviderSelection(provider="ollama", model="qwen2.5:3b")):
        result = asyncio.run(providers.request_explanation(
            "ollama", _context(), transport=httpx.MockTransport(handle)))

    assert result.text == plain
    assert result.source_ids == [] and result.assumptions == [] and result.uncertainty is None
    assert result.warnings == ["plain_text_salvaged_unverified"]


def test_truncated_json_is_not_salvaged_as_prose():
    def handle(request):
        if request.method == "GET":
            return _resident_response()
        partial = '{"text":"partial'
        body = {"model": "test", "message": {"role": "assistant", "content": partial},
                "done": True, "done_reason": "stop"}
        return httpx.Response(200, content=(json.dumps(body) + "\n").encode())

    with provider_context(ProviderSelection(provider="ollama", model="qwen2.5:3b")) as metrics:
        with pytest.raises(providers.ProviderError):
            asyncio.run(providers.request_explanation(
                "ollama", _context(), transport=httpx.MockTransport(handle)))

    assert metrics.requests[-1]["status"] == "error"
    assert metrics.requests[-1]["warnings"] == ["invalid_explanation_dropped"]


def test_legacy_section_only_output_keeps_well_formed_number_diagnostics():
    proposal = {"key": "acceleration", "value": 99, "unit": "m/s^2",
                "experiment_id": "wrong-experiment", "revision": 999, "run_id": "wrong-run"}

    def handle(request):
        if request.method == "GET":
            return _resident_response()
        return _ollama_stream({"sections": ["principle"], "numeric_claims": [proposal],
                               "actions": [{"op": "change_conditions"}]})

    with provider_context(ProviderSelection(provider="ollama", model="qwen2.5:3b")) as metrics:
        with pytest.raises(providers.ProviderError):
            asyncio.run(providers.request_explanation(
                "ollama", _context(), transport=httpx.MockTransport(handle)))

    assert metrics.proposed_numbers == [proposal]
    assert "legacy_sections_only_dropped" in metrics.requests[-1]["warnings"]
    assert "state_action_metadata_dropped" in metrics.requests[-1]["warnings"]


def test_explanation_cancellation_propagates_and_does_not_retry():
    class SlowStream(httpx.AsyncByteStream):
        def __init__(self):
            self.closed = False

        async def __aiter__(self):
            event = {"model": "test", "message": {"role": "assistant", "content": "partial"}, "done": False}
            yield (json.dumps(event) + "\n").encode()
            await asyncio.Event().wait()

        async def aclose(self):
            self.closed = True

    async def run():
        progress = asyncio.Event()
        paths = []
        stream = SlowStream()

        def handle(request):
            paths.append(request.url.path)
            if request.method == "GET":
                return _resident_response()
            return httpx.Response(200, stream=stream)

        with provider_context(ProviderSelection(provider="ollama", model="qwen2.5:3b"),
                              on_progress=lambda _: progress.set()) as metrics:
            task = asyncio.create_task(providers.request_explanation(
                "ollama", _context(), transport=httpx.MockTransport(handle)))
            await asyncio.wait_for(progress.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        return paths, stream, metrics

    paths, stream, metrics = asyncio.run(run())
    assert paths == ["/api/ps", "/api/chat"]
    assert stream.closed and metrics.requests[-1]["status"] == "cancelled"
