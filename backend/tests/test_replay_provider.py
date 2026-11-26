import asyncio
import json
from pathlib import Path

import pytest

from physis import cognitive, grounded
from physis.provider_config import ProviderError, ProviderSelection, provider_context
from physis.providers import ReplayTransport, request_explanation
from physis.provider_stream import replay_context
from physis.cognitive_routing import route
from physis.knowledge import KnowledgeStore
from physis.physics import SPECS
from physis.schema import Patch
from physis.state import build
from physis.api import snapshot
from uuid import uuid4


FIXTURE = Path(__file__).parent / "fixtures" / "replay" / "ollama_saved_h_units_answer.txt"
CONTEXT = {
    "question": "힘을 SI 기본 단위로 나타내면 어떻게 되나요?",
    "level": "school",
    "intents": ["units"],
    "model": "newton",
    "passages": [{"id": "source-1", "quote": "A newton is one kilogram meter per second squared."}],
    "conditions": ["일정한 질량"],
}


def test_archived_content_replay_uses_runtime_answer_contract_and_marks_origin():
    content = FIXTURE.read_text(encoding="utf-8").strip()
    replay = ReplayTransport(content=content)

    async def run():
        with provider_context(ProviderSelection(provider="mock", model="local-rules")) as metrics:
            answer = await request_explanation("mock", CONTEXT, transport=replay)
        return answer, metrics

    answer, metrics = asyncio.run(run())

    assert answer.text == content
    assert answer.warnings == ["plain_text_salvaged_unverified"]
    assert metrics.requests[0]["origin"] == "replay"
    assert metrics.requests[0]["input_tokens"] is None
    assert metrics.requests[0]["output_tokens"] is None


def test_wire_message_replay_uses_same_metadata_filtering_as_runtime():
    wire_message = {
        "role": "assistant",
        "content": json.dumps({
            "text": "힘의 SI 단위는 뉴턴입니다.",
            "source_ids": ["source-1", "not-provided"],
            "assumptions": ["일정한 질량", "not-provided"],
            "level": "university",
            "actions": [{"op": "create"}],
        }, ensure_ascii=False),
    }

    async def run():
        with provider_context(ProviderSelection(provider="mock", model="local-rules")) as metrics:
            answer = await request_explanation(
                "mock", CONTEXT, transport=ReplayTransport(wire_message=wire_message)
            )
        return answer, metrics

    answer, metrics = asyncio.run(run())

    assert answer.text == "힘의 SI 단위는 뉴턴입니다."
    assert answer.source_ids == ["source-1"]
    assert answer.assumptions == ["일정한 질량"]
    assert set(answer.warnings) == {
        "state_action_metadata_dropped", "invalid_level_dropped",
        "invalid_source_ids_dropped", "invalid_assumptions_dropped",
    }
    assert metrics.proposed_sources == ["source-1"]
    assert metrics.requests[0]["origin"] == "replay"


def test_scoped_replay_fixture_is_mock_only_and_one_shot():
    replay = ReplayTransport(content='{"text":"검토할 설명입니다."}')

    async def run():
        with replay_context(replay):
            with provider_context(ProviderSelection(provider="mock", model="local-rules")) as metrics:
                answer = await request_explanation("mock", CONTEXT)
                with pytest.raises(ProviderError):
                    await request_explanation("mock", CONTEXT)
        return answer, metrics

    answer, metrics = asyncio.run(run())
    assert answer.text == "검토할 설명입니다."
    assert metrics.requests[0]["origin"] == "replay"
    with pytest.raises(ProviderError):
        asyncio.run(request_explanation("openai", CONTEXT, transport=ReplayTransport(content="{}")))


def test_saved_replay_flows_through_mock_tutor_screening_and_grounded_report(tmp_path):
    question = "뉴턴의 법칙에서 힘의 SI 단위는 무엇이야?"
    experiment = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    current = snapshot(experiment, 1, "school")
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.initialize()
    rows = grounded.retrieved_for(store, question, model="newton")
    material = grounded.make_context(store, rows, question, current)
    selected = route(question, experiment)

    async def run():
        with replay_context(ReplayTransport(content=FIXTURE.read_text(encoding="utf-8").strip())):
            with provider_context(ProviderSelection(provider="mock", model="local-rules")) as metrics:
                candidate, trace = await cognitive.explain_turn(
                    question, "school", "explain", selected, current, material, metrics
                )
        report = grounded.report(store, rows, material, candidate, snapshot=current,
                                metrics=metrics, level="school", question=question)
        cognitive.finish_trace(trace, report, candidate)
        return candidate, trace, report, metrics

    candidate, trace, report, metrics = asyncio.run(run())

    assert trace["generation"] in {"model_with_verified_tools", "verified_fallback"}
    assert metrics.requests[0]["origin"] == "replay"
    assert "5 Newton" not in candidate and "5 Newton" not in report["core"]
    assert "1 kg·m/s²" not in candidate and "1 kg·m/s²" not in report["core"]


def test_environment_provider_default_is_inert_without_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "ollama")
    monkeypatch.setenv("PHYSIS_OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.delenv("PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT", raising=False)

    with provider_context() as implicit:
        assert implicit.provider == "mock"
    with provider_context(ProviderSelection(provider="ollama", model="qwen2.5:3b")) as selected:
        assert selected.provider == "ollama"


def test_environment_provider_default_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "ollama")
    monkeypatch.setenv("PHYSIS_OLLAMA_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT", "1")

    with provider_context() as metrics:
        assert metrics.provider == "ollama"
        assert metrics.model == "qwen2.5:3b"
