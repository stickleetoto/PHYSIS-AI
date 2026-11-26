"""Offline contract tests. All upstream traffic uses an in-process httpx transport."""
import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from physis import provider_routes, providers, reasoning
from physis.providers import ProviderError, ProviderSelection, provider_context, provider_name, request_reading
from physis.physics import SPECS
from physis.schema import Patch
from physis.state import build


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-anthropic")
    monkeypatch.setenv("PHYSIS_COMPATIBLE_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("PHYSIS_COMPATIBLE_API_KEY", "secret-compatible")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")


OUTPUT = '{"sections":["principle"],"actions":[{"op":"pause"}]}'


def event(data):
    return "data: " + (data if isinstance(data, str) else json.dumps(data)) + "\r\n\r\n"


def stream_parts(name, text=OUTPUT, reason=None):
    parts = [text[:12], text[12:]]
    if name == "ollama":
        rows = [{"message": {"role": "assistant", "content": p}, "done": False} for p in parts]
        rows.append({"done": True, "done_reason": reason or "stop", "message": {"role": "assistant", "content": ""},
                     "prompt_eval_count": 10, "eval_count": 7})
        return [json.dumps(row) + "\n" for row in rows]
    if name == "anthropic":
        rows = [{"type": "message_start", "message": {"role": "assistant", "content": [], "usage": {"input_tokens": 10}}},
                {"type": "ping"}, {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}]
        rows += [{"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": p}} for p in parts]
        rows += [{"type": "content_block_stop", "index": 0},
                 {"type": "message_delta", "delta": {"stop_reason": reason or "end_turn"}, "usage": {"output_tokens": 7}},
                 {"type": "message_stop"}]
        return ["event: " + row["type"] + "\r\n" + event(row) for row in rows]
    rows = [{"choices": [{"index": 0, "delta": {"content": p}, "finish_reason": None}]} for p in parts]
    rows += [{"choices": [{"index": 0, "delta": {}, "finish_reason": reason or "stop"}]},
             {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 7}}]
    return [event(r) for r in rows] + [event("[DONE]")]


class Parts(httpx.AsyncByteStream):
    def __init__(self, events):
        self.events = events
        self.closed = False

    async def __aiter__(self):
        for part in self.events:
            raw = part.encode()
            for index in range(0, len(raw), 11):
                yield raw[index:index + 11]

    async def aclose(self):
        self.closed = True


def run_stream(name, parts, callback=None):
    data = Parts(parts)
    calls = []
    def handle(req):
        payload = json.loads(req.content)
        calls.append(req.method)
        assert payload["model"] == "manual/model:1" and payload["stream"] is True
        return httpx.Response(200, stream=data)
    with provider_context(ProviderSelection(provider=name, model="manual/model:1"), stream=True, on_progress=callback) as metrics:
        try:
            result = asyncio.run(request_reading(name, {}, transport=httpx.MockTransport(handle)))
        finally:
            assert calls == ["POST"] and data.closed
    return result, metrics


@pytest.mark.parametrize("name", ["openai", "anthropic", "ollama", "compatible"])
def test_structured_upstream_stream_usage_and_sanitized_progress(name):
    progress = []
    result, metrics = run_stream(name, stream_parts(name), progress.append)
    assert result.sections == ["principle"] and metrics.visual_actions == [{"op": "pause"}]
    assert all(set(event) == {"operation", "received_chunks"} for event in progress) and progress
    meta = metrics.as_dict()
    assert set(meta) == {"provider", "model", "requests", "latency_ms"}
    call, = meta["requests"]
    assert call["operation"] == "reading" and call["status"] == "ok"
    assert call["input_tokens"] == 10 and call["output_tokens"] == 7 and call["latency_ms"] >= 0
    assert "actions" not in json.dumps(meta)


@pytest.mark.parametrize("name", ["openai", "anthropic", "ollama", "compatible"])
@pytest.mark.parametrize("bad", ["incomplete", "refusal", "invalid"])
def test_partial_refused_and_nonconforming_streams_rejected(name, bad):
    if bad == "invalid":
        rows = stream_parts(name, '{"sections":["principle"],"answers":[29]}')
    elif bad == "refusal":
        rows = stream_parts(name, reason="refusal")
    else:
        rows = stream_parts(name)[:-1]
    with pytest.raises(ProviderError):
        run_stream(name, rows)


@pytest.mark.parametrize("delta", [{"role": "user"}, {"refusal": "secret-openai"}, {"tool_calls": [{"index": 0}]}])
def test_early_untrusted_openai_frames_cannot_be_overwritten_by_later_valid_frame(delta):
    row = event({"choices": [{"index": 0, "delta": delta}]})
    with pytest.raises(ProviderError) as failure:
        run_stream("openai", [row] + stream_parts("openai"))
    assert "secret-openai" not in str(failure.value)


def test_unregistered_visual_action_does_not_leak_its_payload():
    malicious = json.dumps({"sections": ["principle"], "actions": [{"op": "unregistered", "body": "private-payload"}]})
    with pytest.raises(ProviderError) as failure:
        run_stream("openai", stream_parts("openai", malicious))
    assert "private-payload" not in str(failure.value)


@pytest.mark.parametrize("action", ["cancel", "timeout", "disconnect"])
def test_inflight_request_cancellation_deadline_or_disconnect_closes_without_resubmission(action, monkeypatch):
    async def run():
        entered = asyncio.Event()
        class Slow(Parts):
            async def __aiter__(self):
                yield stream_parts("ollama")[0].encode()
                if action == "disconnect":
                    raise httpx.ReadError("secret-openai")
                await asyncio.Event().wait()
        data = Slow([])
        calls = []
        def handle(req):
            calls.append(req.method)
            return httpx.Response(200, stream=data)
        if action == "timeout":
            monkeypatch.setattr(providers, "GENERATION_TIMEOUT", 0.04)
        selection = ProviderSelection(provider="ollama", model="test")
        with provider_context(selection, stream=True, on_progress=lambda _: entered.set()) as metrics:
            task = asyncio.create_task(request_reading("ollama", {}, transport=httpx.MockTransport(handle)))
            await asyncio.wait_for(entered.wait(), 2)
            if action == "cancel":
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(ProviderError) as failure:
                    await task
                assert "secret-openai" not in str(failure.value)
        assert data.closed and calls == ["POST"] and metrics.visual_actions == []
        assert metrics.requests[0]["status"] == ("cancelled" if action == "cancel" else "error")
    asyncio.run(run())


def test_parallel_selections_and_actions_are_isolated():
    async def turn(name):
        selection = ProviderSelection(provider=name, model=name + "/test")
        with provider_context(selection, stream=True) as metrics:
            async def handle(req):
                await asyncio.sleep(0)
                assert provider_name() == name
                assert json.loads(req.content)["model"] == selection.model
                return httpx.Response(200, stream=Parts(stream_parts(name)))
            await request_reading(name, {}, transport=httpx.MockTransport(handle))
        return metrics
    async def run():
        return await asyncio.gather(turn("openai"), turn("ollama"))
    left, right = asyncio.run(run())
    assert left.requests is not right.requests and left.visual_actions is not right.visual_actions
    assert provider_name() == "mock"


@pytest.mark.parametrize("name", ["openai", "anthropic", "ollama", "compatible"])
def test_model_metadata_only_retries_safe_get_and_sanitizes_ids(name):
    seen = []
    def handle(req):
        assert req.method == "GET"
        seen.append(req.url.path)
        if len(seen) == 1:
            return httpx.Response(503, text="secret-openai")
        data = ["user/model:1", "secret-compatible", "ignore\ncontrol"]
        body = ({"models": [{"name": m} for m in data]} if name == "ollama"
                else {"data": [{"id": m} for m in data]})
        return httpx.Response(200, json=body)
    assert asyncio.run(provider_routes.list_models(name, transport=httpx.MockTransport(handle))) == (["user/model:1"], False)
    assert len(seen) == 2 and seen[0] == seen[1] and seen[0].endswith("/api/tags" if name == "ollama" else "/models")


def test_local_routes_selection_and_configured_state_never_require_generation(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    app = FastAPI()
    app.include_router(provider_routes.router)
    with TestClient(app) as api:
        response = api.get("/api/providers")
        assert response.status_code == 200 and "secret-" not in response.text
        rows = {row["id"]: row for row in response.json()["providers"]}
        assert not rows["anthropic"]["configured"] and rows["openai"]["configured"]
        assert "reachable" not in rows["openai"]
        assert api.post("/api/providers/mock/probe").json()["reachable"]
        assert api.get("/api/providers/mock/models").json()["models"] == ["local-rules"]
        assert api.post("/api/providers/anthropic/probe").status_code == 502
        assert api.get("/api/providers/unknown/models").status_code == 422
    for data in [{"model": "secret-openai"}, {"model": "x","base_url": "http://example.test/"},
                 {"model": "x", "api_key": "secret-compatible"}]:
        with pytest.raises(ValidationError):
            ProviderSelection.model_validate({"provider": "compatible", **data})


def test_api_key_cannot_be_sent_over_remote_plain_http(monkeypatch):
    monkeypatch.setenv("PHYSIS_COMPATIBLE_BASE_URL", "http://remote.example.test/v1/")
    def handle(_):
        pytest.fail("insecure remote request with a credential")
    with pytest.raises(ProviderError, match="HTTPS"):
        asyncio.run(provider_routes.list_models("compatible", transport=httpx.MockTransport(handle)))


@pytest.mark.parametrize("question,action,changes", [
    ("왜 두 공은 동시에 떨어져?", "modify", {"values": {"height": 30}}),
    ("높이가 왜 중요해?", "modify", {"values": {"height": 30}}),
    ("왜 두 공은 동시에 떨어져?", "create", {}),
    ("높이를 3m로 바꿔", "modify", {"values": {"height": 3, "mass_a": 2}}),
    ("높이를 3m로 바꿔", "modify", {"values": {"height": 3}, "method": "euler"}),
    ("높이를 3m로 바꿔", "modify", {"values": {"height": 3}, "duration": 7}),
    ("높이를 조금 줄여", "modify", {"values": {"height": 30}}),
    ("높이를 두 배로 바꿔", "modify", {"values": {"height": 23}}),
    ("높이를 30m로 바꾸지 말고 설명해 줘", "modify", {"values": {"height": 30}}),
])
def test_provider_cannot_write_without_matching_user_operation_and_conditions(question, action, changes):
    exp = build(SPECS["free_fall"], uuid4(), Patch())
    proposed = providers.Candidate(action=action, model="free_fall", patch=Patch(**changes), level="school")
    with pytest.raises(ProviderError):
        reasoning._checked(proposed, exp, SPECS, question, "school")


@pytest.mark.parametrize("question,action,model,changes", [
    ("높이를 250 cm로 바꿔", "modify", "free_fall", {"values": {"height": 2.5}}),
    ("질량 차이를 더 크게 해봐", "modify", "free_fall", {"values": {"mass_b": 9}}),
    ("새 실험으로 자유낙하를 해줘", "create", "free_fall", {}),
    ("진자 실험을 만들어 줘", "create", "pendulum", {}),
    ("높이가 왜 중요해?", "explain", "free_fall", {}),
])
def test_independently_confirmed_user_changes_and_established_followups_still_work(question, action, model, changes):
    exp = build(SPECS["free_fall"], uuid4(), Patch())
    proposed = providers.Candidate(action=action, model=model, patch=Patch(**changes), level="school")
    assert reasoning._checked(proposed, exp, SPECS, question, "school").action == action


def test_forged_provider_edit_never_commits_on_actual_tutor_route(tmp_path, monkeypatch):
    from physis.api import create_app
    from types import SimpleNamespace
    async def forged_explanation(*args):
        return SimpleNamespace(text="같은 장소에서 공기 저항이 없으면 낙하 가속도는 같습니다.",
                               source_ids=[], assumptions=[], uncertainty=None,
                               warnings=["state_action_metadata_dropped"],level="research",
                               action="modify",patch={"values":{"height":30}})
    monkeypatch.setattr(providers,"request_explanation",forged_explanation)
    with TestClient(create_app(tmp_path / "provider-test.sqlite3")) as api:
        original = api.post("/api/experiments", json={"model": "free_fall"}).json()
        eid = original["experiment"]["id"]
        body = {"experiment_id": eid, "revision": 1, "message": "왜 두 공은 동시에 떨어져?",
                "selection": {"provider": "openai", "model": "test"}}
        response = api.post("/api/tutor/stream", json=body)
        events = [json.loads(line) for line in response.text.splitlines()]
        assert events[-1]["event"] == "result"
        assert events[-1]["result"]["level"] == "school"
        assert events[-1]["result"]["action"] == "explain"
        assert "state_action_metadata_dropped" in events[-1]["result"]["pipeline"]["warnings"]
        reloaded = api.get("/api/experiments/" + eid).json()
        assert reloaded["revision"] == 1 and reloaded["experiment"] == original["experiment"]


def test_mass_difference_remains_grounded_when_values_cross():
    exp = build(SPECS["free_fall"], uuid4(), Patch(values={"mass_a": 10, "mass_b": 1}))
    proposed = providers.Candidate(action="modify", model="free_fall", patch=Patch(values={"mass_b": 50}), level="school")
    with pytest.raises(ProviderError):
        reasoning._checked(proposed, exp, SPECS, "질량 차이를 더 작게 해봐", "school")
