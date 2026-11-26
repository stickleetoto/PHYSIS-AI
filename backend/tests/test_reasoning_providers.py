import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from physis import reasoning
from physis.physics import SPECS, simulate
from physis.providers import Candidate, ProviderError, Reading, provider_name, request_candidate, request_reading
from physis.schema import Patch
from physis.state import build


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    # Exercise the old explicitly configured adapter contract against MockTransport.
    monkeypatch.setenv("PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT", "1")
    monkeypatch.setenv("PHYSIS_AI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("PHYSIS_COMPATIBLE_BASE_URL", "https://provider.test/v1/")
    monkeypatch.setenv("PHYSIS_COMPATIBLE_API_KEY", "test-compatible-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")


def candidate(**updates):
    return {"action": "create", "model": "free_fall", "level": "school", "patch": {}} | updates


def envelope(name, content):
    text = content if isinstance(content, str) else json.dumps(content)
    reply = {"role": "assistant", "content": text}
    if name == "anthropic":
        return {"role": "assistant", "content": [{"text": text, "type": "text"}], "stop_reason": "end_turn"}
    if name == "ollama":
        return {"message": reply, "done": True, "done_reason": "stop"}
    return {"choices": [{"message": reply, "finish_reason": "stop"}]}


def request(name, handler):
    return asyncio.run(request_candidate(name, "두 공의 자유낙하", None, "school", SPECS,
                                         transport=httpx.MockTransport(handler)))


@pytest.mark.parametrize("name,url", [
    ("openai", "https://api.openai.com/v1/chat/completions"),
    ("anthropic", "https://api.anthropic.com/v1/messages"),
    ("ollama", "http://127.0.0.1:11434/api/chat"),
    ("compatible", "https://provider.test/v1/chat/completions"),
])
def test_each_protocol_writes_and_reads_its_own_envelope(name, url):
    def handle(req):
        assert req.method == "POST" and str(req.url) == url
        data = json.loads(req.content)
        assert data["model"] == "test-model" and len(data["messages"]) == (1 if name == "anthropic" else 2)
        user = json.loads(data["messages"][-1]["content"])
        assert user["request"] == "두 공의 자유낙하" and user["current"] is None
        assert any(entry["id"] == "free_fall" for entry in user["catalog"])
        assert "test-openai-key" not in req.content.decode()
        if name == "anthropic":
            assert data["system"] and req.headers["x-api-key"] == "test-anthropic-key"
            assert req.headers["anthropic-version"] == "2023-06-01" and "authorization" not in req.headers
        elif name == "ollama":
            assert data["stream"] is False and data["format"]["additionalProperties"] is False
            assert "authorization" not in req.headers
        else:
            assert req.headers["authorization"] == f"Bearer test-{name}-key"
            assert data["response_format"]["type"] == "json_object"
        return httpx.Response(200, json=envelope(name, candidate()))
    assert request(name, handle).model == "free_fall"


@pytest.mark.parametrize("bad", [candidate(status="VERIFIED"), candidate(code="return 1"), candidate(results=[1]),
                                candidate(patch={"values": {"height": "4"}}), candidate(patch={"runtime": "python"}),
                                candidate(patch={"values": {"height": True}}), candidate(level="anything"),
                                candidate(message="provider prose"), "{}", "[1,2]", "not json", "```json\n{}\n```",
                                '{"action":"create","action":"modify","level":"school","model":null,"patch":{}}'])
def test_rejects_malformed_or_untrusted_generated_fields(bad):
    with pytest.raises(ProviderError):
        request("openai", lambda _: httpx.Response(200, json=envelope("openai", bad)))


@pytest.mark.parametrize("name,body", [
    ("anthropic", {"role": "assistant", "stop_reason": "max_tokens", "content": []}),
    ("ollama", {"done": False, "message": {"role": "assistant", "content": json.dumps(candidate())}}),
    ("openai", {"choices": [{"finish_reason": "length"}]}), ("compatible", {"choices": []}),
])
def test_incomplete_provider_output_is_not_used(name, body):
    with pytest.raises(ProviderError):
        request(name, lambda _: httpx.Response(200, json=body))


@pytest.mark.parametrize("proposal", [candidate(model="unregistered"), candidate(action="explain", model="pendulum"),
                                     candidate(action="modify"), candidate(action="unsupported"),
                                     candidate(action="explain", patch={"duration": 2}),
                                     candidate(patch={"values": {"electric_charge": 3}}),
                                     candidate(patch={"values": {"mass_a": 1e8}})])
def test_registry_validation_applies_after_provider_response(monkeypatch, proposal):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "openai")
    async def propose(*args):
        return Candidate.model_validate(proposal)
    monkeypatch.setattr(reasoning, "request_candidate", propose)
    current = build(SPECS["free_fall"], uuid4(), Patch())
    with pytest.raises(ProviderError):
        asyncio.run(reasoning.plan("자유낙하 실험", current, "school", SPECS))


def test_missing_credentials_unknown_provider_and_transport_error_are_safe(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(ProviderError, match="OPENAI_API_KEY"):
        request("openai", lambda _: pytest.fail("network access with missing key"))
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "unrecognized")
    with pytest.raises(ProviderError):
        provider_name()
    with pytest.raises(ProviderError) as error:
        request("compatible", lambda _: httpx.Response(401, text="test-compatible-key should stay private"))
    assert "test-compatible-key" not in str(error.value)


@pytest.mark.parametrize("name", ["openai", "anthropic", "ollama", "compatible"])
def test_after_computation_each_protocol_receives_evidence_and_only_renders_allowed_text(name, monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", name)
    exp = build(SPECS["free_fall"], uuid4(), Patch(duration=.1))
    run = simulate(exp)
    def reply(req):
        body = json.loads(req.content)
        evidence = json.loads(body["messages"][-1]["content"])
        assert evidence["model"] == "free_fall" and evidence["status"] == run.status
        assert evidence["checks"] == [c.model_dump() for c in run.checks]
        assert evidence["facts"] == run.facts and evidence["sample_count"] == len(run.times)
        assert "관찰 구간" in "".join(evidence["required_readout"])
        assert 'next_question' in evidence['available_sections'] and 'series' not in evidence
        return httpx.Response(200, json=envelope(name, {"sections": ["next_question", "assumptions"]}))
    async def read(provider, evidence):
        return await request_reading(provider, evidence, transport=httpx.MockTransport(reply))
    monkeypatch.setattr(reasoning, "request_reading", read)
    text = asyncio.run(reasoning.interpret("이번엔 무엇을 바꿔볼까?", exp, run, "research"))
    assert "관찰 구간" in text and "어떤 측정값이" in text and "적분" in text and "Δt" in text
    assert f"{run.series['0.y'][-1]:.4g} m" in text and exp.formula in text


@pytest.mark.parametrize("output", [{"sections": ["comparison"], "value": 5}, {"sections": ["comparison"], "status": "VERIFIED"},
                                    {"sections": ["injected"]}, {"sections": ["assumptions", "assumptions"]},
                                    {"sections": []}, {"explanation": "fabricated output"}, {"sections": [6.5]}])
def test_interpretation_rejects_untrusted_numbers_prose_or_unknown_selection(output):
    def reply(_):
        return httpx.Response(200, json=envelope("openai", output))
    with pytest.raises(ProviderError):
        asyncio.run(request_reading("openai", {}, transport=httpx.MockTransport(reply)))


def test_interpretation_cannot_reintroduce_success_narrative_after_failed_check(monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "openai")
    exp = build(SPECS['free_fall'], uuid4(), Patch())
    run = simulate(exp).model_copy(update={"status": "FAILED"})
    async def read(provider, evidence):
        assert "principle" not in evidence["available_sections"]
        return Reading(sections=["principle"])
    monkeypatch.setattr(reasoning, "request_reading", read)
    with pytest.raises(ProviderError):
        asyncio.run(reasoning.interpret("왜 그래?", exp, run, "school"))


@pytest.mark.parametrize("text,model,patch", [
    ("높이를 5kg로", "free_fall", {"values": {"height": 5}}),
    ("높이를 500cm로", "free_fall", {"values": {"height": 50}}),
    ("완전 비탄성 충돌", "collision", {}), ("마찰 없는 용수철", "friction", {}),
])
def test_actual_conditions_checked_even_if_provider_outputs_well_formed_json(text, model, patch, monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "openai")
    async def propose(*args):
        return Candidate.model_validate(candidate(model=model, patch=patch))
    monkeypatch.setattr(reasoning, "request_candidate", propose)
    exp = build(SPECS['free_fall'], uuid4(), Patch())
    with pytest.raises(ProviderError):
        asyncio.run(reasoning.plan(text, exp, 'school', SPECS))


def test_explicit_outside_idealization_is_handled_before_provider(monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "openai")
    monkeypatch.setattr(reasoning, "request_candidate", lambda *args: pytest.fail("should have declined"))
    assert asyncio.run(reasoning.plan("이차원 충돌", None, "school", SPECS)).action == "unsupported"
