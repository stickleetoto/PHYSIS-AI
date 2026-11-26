import pytest
from fastapi.testclient import TestClient

from physis.api import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "mock")
    with TestClient(create_app(tmp_path / "clarification.sqlite3")) as api:
        yield api


def test_generic_prediction_asks_for_essential_height_then_runs_with_answer(client):
    first = client.post("/api/chat", json={"message": "공이 몇 초 만에 땅에 닿아?"}).json()

    assert first["classification"] == "needs_clarification"
    assert first["snapshot"] is None
    assert first["dialogue"]["missing_conditions"][0]["key"] == "height"
    assert "높이" in first["message"]

    recovered = client.post("/api/chat", json={
        "message": "4 m",
        "dialogue": first["dialogue"],
    }).json()

    assert recovered["action"] == "create"
    assert recovered["classification"] == "assumptions"
    assert recovered["snapshot"]["experiment"]["model"] == "free_fall"
    assert recovered["snapshot"]["experiment"]["values"]["height"] == 4
    assert recovered["status"] == recovered["snapshot"]["run"]["status"]
    assert recovered["dialogue"] is None


def test_partial_answers_keep_only_unresolved_conditions_and_recover(client):
    first = client.post("/api/chat", json={"message": "진자 주기를 계산해 줘."}).json()
    assert first["classification"] == "needs_clarification"
    assert {item["key"] for item in first["dialogue"]["missing_conditions"]} == {"length", "angle"}

    partial = client.post("/api/chat", json={"message": "길이 2 m", "dialogue": first["dialogue"]}).json()
    assert partial["classification"] == "needs_clarification"
    assert [item["key"] for item in partial["dialogue"]["missing_conditions"]] == ["angle"]
    assert partial["snapshot"] is None

    complete = client.post("/api/chat", json={"message": "진폭각 0.2 rad", "dialogue": partial["dialogue"]}).json()
    assert complete["action"] == "create"
    assert complete["snapshot"]["experiment"]["model"] == "pendulum"
    assert complete["snapshot"]["experiment"]["values"]["length"] == 2
    assert complete["snapshot"]["experiment"]["values"]["angle"] == pytest.approx(0.2)
    assert complete["dialogue"] is None


def test_newton_inverse_waits_for_both_mass_and_acceleration_then_uses_them(client):
    first = client.post("/api/chat", json={"message": "물체의 알짜힘이 얼마야?"}).json()
    assert first["classification"] == "needs_clarification"
    assert {item["key"] for item in first["dialogue"]["missing_conditions"]} == {"mass", "a"}

    partial = client.post("/api/chat", json={"message": "질량 2 kg", "dialogue": first["dialogue"]}).json()
    assert [item["key"] for item in partial["dialogue"]["missing_conditions"]] == ["a"]

    complete = client.post("/api/chat", json={"message": "가속도 3 m/s²", "dialogue": partial["dialogue"]}).json()
    assert complete["action"] == "create"
    assert complete["snapshot"]["experiment"]["model"] == "newton"
    assert complete["snapshot"]["experiment"]["values"]["mass"] == 2
    assert complete["snapshot"]["experiment"]["values"]["force"] == 6


def test_explicit_demo_uses_registry_defaults_and_discloses_assumptions(client):
    result = client.post("/api/chat", json={"message": "진자 실험을 만들어 줘."}).json()

    assert result["action"] == "create"
    assert result["classification"] == "assumptions"
    assert result["snapshot"]["experiment"]["model"] == "pendulum"
    assert result["assumptions"]
    assert result["dialogue"] is None


def test_real_measurement_without_data_never_uses_default_simulation(client):
    result = client.post("/api/chat", json={
        "message": "우리 책상의 실제 운동 마찰계수 측정값을 알려 줘."
    }).json()

    assert result["classification"] == "needs_clarification"
    assert result["snapshot"] is None
    assert "측정" in result["message"] or "자료" in result["message"]


def test_unrelated_followup_does_not_attach_to_pending_dialogue(client):
    first = client.post("/api/chat", json={"message": "공이 몇 초 만에 땅에 닿아?"}).json()
    unrelated = client.post("/api/chat", json={
        "message": "왜 하늘은 파랄까?",
        "dialogue": first["dialogue"],
    }).json()

    assert unrelated["classification"] == "unsupported"
    assert unrelated["dialogue"] is None


def test_tutor_stream_uses_same_recovery_without_changing_unrelated_current_experiment(client):
    current = client.post("/api/experiments", json={"model": "free_fall"}).json()
    first_response = client.post("/api/tutor/stream", json={
        "experiment_id": current["experiment"]["id"],
        "revision": current["revision"],
        "message": "공이 몇 초 만에 바닥에 닿아?",
    })
    first = [__import__("json").loads(line) for line in first_response.text.splitlines()][-1]["result"]
    assert first["classification"] == "needs_clarification"
    assert first["dialogue"]["experiment_id"] == current["experiment"]["id"]

    second_response = client.post("/api/tutor/stream", json={
        "experiment_id": current["experiment"]["id"],
        "revision": current["revision"],
        "message": "4 m",
        "dialogue": first["dialogue"],
    })
    second = [__import__("json").loads(line) for line in second_response.text.splitlines()][-1]["result"]
    assert second["action"] == "create"
    assert second["snapshot"]["experiment"]["values"]["height"] == 4
    assert second["snapshot"]["experiment"]["id"] != current["experiment"]["id"]
    assert client.get("/api/experiments/" + current["experiment"]["id"]).json() == current


def test_answer_from_another_experiment_is_stale_and_does_not_cross_conversations(client):
    first_exp = client.post("/api/experiments", json={"model": "free_fall"}).json()
    second_exp = client.post("/api/experiments", json={"model": "pendulum"}).json()
    ask = client.post("/api/chat", json={
        "experiment_id": first_exp["experiment"]["id"], "revision": 1,
        "message": "공이 몇 초 만에 바닥에 닿아?",
    }).json()

    stale = client.post("/api/chat", json={
        "experiment_id": second_exp["experiment"]["id"], "revision": 1,
        "message": "4 m", "dialogue": ask["dialogue"],
    }).json()

    assert stale["classification"] == "needs_clarification"
    assert stale["snapshot"] is None
    assert stale["dialogue"] is None
    assert client.get("/api/experiments/" + first_exp["experiment"]["id"]).json() == first_exp
    assert client.get("/api/experiments/" + second_exp["experiment"]["id"]).json() == second_exp

