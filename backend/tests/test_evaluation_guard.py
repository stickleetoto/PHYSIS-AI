import asyncio

import httpx
import pytest

from physis import providers
from physis.evaluation_guard import generation_guard
from physis.provider_config import ProviderSelection, provider_context


@pytest.mark.parametrize("phase", ["plan", "explanation", "preload"])
def test_denied_reservation_precedes_outgoing_generation_or_preload(phase, monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("PHYSIS_OFFLINE", "0")
    charged = []
    sent = []

    def reserve(operation):
        charged.append(operation)
        raise RuntimeError("test budget exhausted")

    def respond(request):
        if request.method == "GET" and request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": [{"name": "mock-test"}]})
        sent.append(request.method)
        raise AssertionError("budgeted request reached the transport")

    transport = httpx.MockTransport(respond)
    with provider_context(ProviderSelection(provider="ollama", model="mock-test")):
        with generation_guard(reserve), pytest.raises(RuntimeError, match="budget exhausted"):
            if phase == "preload":
                asyncio.run(providers.preload_ollama_model(transport=transport))
            elif phase == "plan":
                asyncio.run(providers._generate("ollama", "test", {}, providers.Candidate, transport))
            else:
                asyncio.run(providers._request_completion("ollama", "test", {}, transport=transport))
    assert charged == [phase] and sent == []
