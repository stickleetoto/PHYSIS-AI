from concurrent.futures import ThreadPoolExecutor
from functools import partial
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from physis.api import create_app
from physis import reasoning


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "mock")
    with TestClient(create_app(tmp_path / "lab.sqlite3")) as client:
        yield client


def post(client, path, **values):
    response = client.post(path, json=values)
    assert response.status_code == 200, response.text
    return response.json()


def test_health_reports_distribution_version(client):
    health = client.get("/api/health").json()
    assert health["service"] == "PHYSIS AI"
    assert health["version"] == "0.4.1"


def test_lesson_with_persistent_identity_and_computed_evidence(client):
    created = post(client, "/api/chat", message="무거운 물체가 가벼운 물체보다 빨리 떨어지는 거 아니야?")
    first = created["snapshot"]
    assert created["action"] == "create"
    assert first["experiment"]["model"] == "free_fall"
    assert first["run"]["status"] in {"VERIFIED", "LIMITED"}
    assert first["run"]["status"] != "FAILED"
    eid = first["experiment"]["id"]
    updated = post(client, "/api/chat", message="그러면 두 물체의 질량 차이를 더 크게 해봐.",
                   experiment_id=eid, revision=1)
    second = updated["snapshot"]
    assert updated["action"] == "modify"
    assert second["experiment"]["id"] == eid and second["revision"] == 2
    assert second["experiment"]["values"]["mass_b"] > first["experiment"]["values"]["mass_b"]
    assert first["run"]["series"]["1.y"] == pytest.approx(second["run"]["series"]["1.y"])
    assert first["run"]["series"]["1.energy"][0] < second["run"]["series"]["1.energy"][0]
    explained = post(client, "/api/chat", message="왜 결과가 같아?", experiment_id=eid, revision=2)
    assert explained["action"] == "explain" and explained["snapshot"]["revision"] == 2
    assert explained["message"] == explained["snapshot"]["explanation"]
    assert client.get(f"/api/experiments/{eid}").json()["experiment"] == second["experiment"]


def test_unsupported_preserves_previous_state(client):
    first = post(client, "/api/experiments", model="spring")
    eid = first["experiment"]["id"]
    answer = post(client, "/api/chat", experiment_id=eid, revision=1, message="양자 얽힘을 시뮬레이션해줘")
    assert (answer["status"], answer["snapshot"]) == ("UNSUPPORTED", None)
    assert client.get(f"/api/experiments/{eid}").json()["revision"] == 1
    assert client.post("/api/experiments", json={"model": "unknown"}).status_code == 422


@pytest.mark.parametrize("invalid", [
    {"values": {"mass_a": -1}}, {"values": {"foo": 2}}, {"values": {"mass_a": "1 kg"}},
    {"unit": "pound"}, {"status": "VERIFIED"}, {"code": "print(123)"},
    {"method": "invented"}, {"duration": 30, "dt": .002}, {"dt": 0},
])
def test_invalid_patch_rolls_back(client, invalid):
    first = post(client, "/api/experiments", model="free_fall")
    url = "/api/experiments/" + first["experiment"]["id"]
    response = client.patch(url, json={"revision": 1, "patch": invalid})
    assert response.status_code == 422
    assert client.get(url).json()["experiment"] == first["experiment"]
    assert client.get(url).json()["revision"] == 1


def test_concurrent_updates_cannot_overwrite(client):
    first = post(client, "/api/experiments", model="free_fall")
    url = "/api/experiments/" + first["experiment"]["id"]

    def update(mass):
        return client.patch(url, json={"revision": 1, "patch": {"values": {"mass_a": mass}}}).status_code

    with ThreadPoolExecutor(2) as executor:
        assert sorted(executor.map(update, (2, 4))) == [200, 409]
    assert client.get(url).json()["revision"] == 2


def test_interpretation_failure_does_not_commit_proposed_edit(client, monkeypatch):
    first = post(client, "/api/experiments", model="free_fall")
    eid = first["experiment"]["id"]

    async def unavailable(question, experiment, run, level):
        assert experiment.values["mass_b"] > first["experiment"]["values"]["mass_b"]
        assert run.facts["arrival_time"] > 0
        raise reasoning.ProviderError("결과 해석 응답을 확인할 수 없습니다.")

    monkeypatch.setattr(reasoning, "interpret", unavailable)
    response = client.post("/api/chat", json={"message": "질량 차이를 더 크게 해봐",
                           "experiment_id": eid, "revision": 1})
    assert response.status_code == 502
    assert client.get("/api/experiments/" + eid).json() == first


def test_explanation_provider_receives_calculated_evidence_after_local_plan(client, monkeypatch):
    from physis import providers
    monkeypatch.setenv("PHYSIS_ALLOW_ENV_PROVIDER_DEFAULT", "1")
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "compatible")
    monkeypatch.setenv("PHYSIS_AI_MODEL", "classroom-test")
    monkeypatch.setenv("PHYSIS_COMPATIBLE_BASE_URL", "http://provider.invalid/v1")
    stages = []

    def respond(request):
        prompt = json.loads(json.loads(request.content)["messages"][-1]["content"])
        stages.append("explain")
        assert "catalog" not in prompt and "schema" not in prompt
        arrival = next(n for n in prompt["calculations"] if n["key"]=="arrival_time")
        assert arrival["value"] == pytest.approx(1.) and arrival["unit"] == "s" and arrival["run_id"]
        answer = {"text":"공기 저항이 없는 같은 장소에서 두 물체는 같은 가속도로 떨어집니다."}
        event = {"choices":[{"index":0,"delta":{"content":json.dumps(answer)},"finish_reason":"stop"}]}
        return httpx.Response(200,content=("data: "+json.dumps(event)+"\n\ndata: [DONE]\n\n").encode())

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(providers,"request_explanation",partial(providers.request_explanation,transport=transport))
    answer = post(client, "/api/chat", message="4.905 m 자유낙하 실험을 만들어 줘")
    assert stages == ["explain"]
    assert answer["snapshot"]["experiment"]["values"]["height"] == 4.905
    assert "1 s" in answer["message"]


def test_failed_verification_is_exposed(client):
    response = post(client, "/api/experiments", model="spring",
                    patch={"method": "euler", "duration": 10, "dt": 0.2})
    assert response["run"]["status"] == "FAILED"
    assert any(not check["passed"] for check in response["run"]["checks"])


def test_restart_reloads_experiment_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "mock")
    path = tmp_path / "lab.db"
    with TestClient(create_app(path)) as first:
        created = post(first, "/api/experiments", model="spring")
    with TestClient(create_app(path)) as second:
        recovered = second.get("/api/experiments/" + created["experiment"]["id"]).json()
        assert recovered == created


def test_api_contract_rejects_incomplete_context_and_nonfinite(client):
    assert client.post("/api/chat", json={"message": " "}).status_code == 422
    assert client.post("/api/chat", json={"message": "왜?", "revision": 1}).status_code == 422
    malformed = '{"model":"free_fall","patch":{"values":{"height":NaN}}}'
    assert client.post("/api/experiments", content=malformed, headers={"Content-Type": "application/json"}).status_code == 422


def test_enabled_catalog_runs_with_finite_aligned_series(client):
    specs = client.get("/api/catalog").json()["models"]
    assert {"free_fall", "spring"} <= {spec["model"] for spec in specs}
    for spec in specs:
        run = post(client, "/api/experiments", model=spec["model"])["run"]
        assert run["status"] in {"VERIFIED", "LIMITED"}, (spec["model"], run["checks"])
        assert run["checks"] and run["times"] and run["series"]
        assert all(len(measure) == len(run["times"]) for measure in run["series"].values())
