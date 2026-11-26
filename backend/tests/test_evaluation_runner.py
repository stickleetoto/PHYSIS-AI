import json
import asyncio
import sqlite3

import pytest

from scripts import evaluation_v032


def test_replay_refuses_mixed_or_remote_profiles_before_reading_fixtures(tmp_path):
    profiles = {"lab": {"provider": "ollama"}, "mock": {"provider": "mock"}}
    with pytest.raises(evaluation_v032.EvaluationError, match="exclusively Mock"):
        evaluation_v032._provider_context_for_mock_replay(profiles, tmp_path / "absent.jsonl")


def test_reserved_requests_survive_resume_and_consume_cumulative_cap(tmp_path):
    path = tmp_path / "progress.sqlite3"
    store = evaluation_v032.ProgressStore(path)
    store.create_run("run-1", "input-a", "config-a", "product-a", 2, 60)
    first = store.begin_invocation("invoke-1", 2, 60)
    store.begin_case("run-1", "model-a", "C", "c1", "question-hash")
    store.reserve_requests(first, "model_generation", 2, "model-a", "C", "c1")
    store.close()

    resumed = evaluation_v032.ProgressStore(path)
    resumed.create_run("run-1", "input-a", "config-a", "product-a", 2, 60)
    assert resumed.recover_interrupted("run-1") == 1
    assert resumed.latest_case("run-1", "model-a", "C", "c1")["status"] == "interrupted"
    with pytest.raises(evaluation_v032.BudgetExceeded):
        resumed.begin_invocation("invoke-2", 2, 60)
    assert resumed.request_usage() == 2
    resumed.close()


def test_resume_rejects_different_input_config_or_product(tmp_path):
    store = evaluation_v032.ProgressStore(tmp_path / "progress.sqlite3")
    store.create_run("run-1", "input-a", "config-a", "product-a", 4, 60)
    with pytest.raises(evaluation_v032.RunIdentityMismatch):
        store.create_run("run-1", "input-b", "config-a", "product-a", 4, 60)
    with pytest.raises(evaluation_v032.RunIdentityMismatch):
        store.create_run("run-1", "input-a", "config-b", "product-a", 4, 60)
    with pytest.raises(evaluation_v032.RunIdentityMismatch):
        store.create_run("run-1", "input-a", "config-a", "product-b", 4, 60)
    store.close()


def test_run_defaults_to_dry_run_without_creating_progress_or_calling_executor(tmp_path, monkeypatch, capsys):
    cases = tmp_path / "cases.jsonl"
    cases.write_text(json.dumps({"id": "c1", "question": "What is Newton's second law?", "model": "newton"}) + "\n",
                     encoding="utf-8")
    config = tmp_path / "providers.json"
    config.write_text(json.dumps({"provider_configs": {
        "mock": {"provider": "mock", "model": "local-rules"},
        "compatible": {"provider": "compatible", "model": "example-model",
                       "endpoint_env": "EVAL_COMPATIBLE_URL"},
    }}), encoding="utf-8")
    progress = tmp_path / "progress.sqlite3"

    def forbid_execute(*args, **kwargs):
        raise AssertionError("default run must not execute any arm")

    monkeypatch.setattr(evaluation_v032, "execute_run", forbid_execute)
    result = evaluation_v032.main([
        "run", "--cases", str(cases), "--config", str(config),
        "--progress", str(progress), "--arms", "A,C,D,E,F",
    ])
    assert result == 0
    output = capsys.readouterr().out
    assert "DRY RUN" in output
    assert '"planned_rows": 10' in output
    assert not progress.exists()


def test_comparison_joins_completed_outputs_by_provider_arm_and_case(tmp_path):
    paths = []
    for name, answer in (("model-a", "first"), ("model-b", "second")):
        path = tmp_path / f"{name}.sqlite3"
        store = evaluation_v032.ProgressStore(path)
        store.create_run(name, "input", name, "product", 10, 300)
        store.begin_invocation(f"{name}-inv", 10, 300)
        store.begin_case(name, name, "C", "c1", "question-hash")
        store.finish_case(name, name, "C", "c1", "ok",
                          {"text": answer, "trust_label": "UNTRUSTED"})
        store.close()
        paths.append(path)

    rows = evaluation_v032.compare_results(paths)
    assert [(row["provider_config"], row["case_id"], row["arm"], row["text"])
            for row in rows] == [
                ("model-a", "c1", "C", "first"),
                ("model-b", "c1", "C", "second"),
            ]
    assert {row["origin"] for row in rows} == {"no_provider_call"}


def test_origin_is_persisted_and_exported_as_replay_mock_or_actual(tmp_path):
    path = tmp_path / "progress.sqlite3"
    store = evaluation_v032.ProgressStore(path)
    store.create_run("run-1", "input", "config", "product", 10, 300)
    store.begin_invocation("invoke-1", 10, 300)

    rows_to_save = [
        ("mock-replay", "A", "c1", "mock", 0,
         {"text": "replayed", "provider_metrics": {"provider": "mock", "model": "local-rules",
             "latency_ms": 4, "requests": [{"origin": "replay", "latency_ms": 3}]}}),
        ("mock-only", "A", "c1", "mock", 0,
         {"text": "mock answer", "provider_metrics": {"provider": "mock", "model": "local-rules",
             "latency_ms": 4, "requests": []}}),
        ("remote", "A", "c1", "compatible", 1,
         {"text": "provider answer", "provider_metrics": {"provider": "compatible",
             "model": "remote-model", "latency_ms": 40, "requests": [{"status": "ok"}]}}),
    ]
    for profile, arm, case_id, provider, request_count, output in rows_to_save:
        store.begin_case("run-1", profile, arm, case_id, "question-hash")
        if request_count:
            store.reserve_requests("invoke-1", "model_generation", request_count,
                                   profile, arm, case_id)
        origin = evaluation_v032.output_origin(output, provider, request_count)
        evaluation_v032.annotate_output_origin(output, origin)
        store.finish_case("run-1", profile, arm, case_id, "ok", output, origin=origin)
    store.close()

    rows = evaluation_v032.compare_results([path])
    assert {row["provider_config"]: row["origin"] for row in rows} == {
        "mock-replay": "replay", "mock-only": "mock", "remote": "actual_provider"
    }
    csv_path = tmp_path / "comparison.csv"
    json_path = tmp_path / "comparison.json"
    evaluation_v032._write_compare(rows, csv_path, "csv")
    evaluation_v032._write_compare(rows, json_path, "json")
    assert "actual_provider" in csv_path.read_text(encoding="utf-8")
    assert {row["origin"] for row in json.loads(json_path.read_text(encoding="utf-8"))} == {
        "replay", "mock", "actual_provider"
    }
    db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        outputs = {row[0]: json.loads(row[1]) for row in db.execute(
            "SELECT provider_config,output_json FROM case_results")}
    finally:
        db.close()
    assert outputs["mock-replay"]["provider_metrics"]["provider"] == "replay"
    assert outputs["mock-replay"]["provider_metrics"]["model"] is None
    assert outputs["mock-replay"]["provider_metrics"]["latency_ms"] is None
    assert outputs["mock-replay"]["provider_metrics"]["requests"][0]["latency_ms"] is None
    assert outputs["mock-only"]["provider_metrics"]["latency_ms"] is None


def test_compare_opens_progress_read_only_and_does_not_create_missing_path(tmp_path):
    missing = tmp_path / "typo.sqlite3"
    with pytest.raises(evaluation_v032.EvaluationError):
        evaluation_v032.compare_results([missing])
    assert not missing.exists()


def test_no_provider_call_does_not_keep_selected_remote_model_or_latency():
    output = {"provider_metrics": {"provider": "compatible", "model": "configured-model",
                                   "latency_ms": 12, "requests": []}}
    origin = evaluation_v032.output_origin(output, "compatible", 0)
    evaluation_v032.annotate_output_origin(output, origin)
    assert origin == "no_provider_call"
    assert output["provider_metrics"]["provider"] is None
    assert output["provider_metrics"]["model"] is None
    assert output["provider_metrics"]["latency_ms"] is None


def test_keyless_compatible_profile_clears_unrelated_global_credential(monkeypatch):
    monkeypatch.setenv("EVAL_COMPATIBLE_URL", "https://compatible.example.invalid/v1")
    monkeypatch.setenv("PHYSIS_COMPATIBLE_API_KEY", "unrelated-global-key")
    profile = {"provider": "compatible", "model": "remote-model",
               "endpoint_env": "EVAL_COMPATIBLE_URL"}
    with evaluation_v032.provider_environment(profile):
        assert "PHYSIS_COMPATIBLE_API_KEY" not in __import__("os").environ or not __import__("os").environ[
            "PHYSIS_COMPATIBLE_API_KEY"]
    assert __import__("os").environ["PHYSIS_COMPATIBLE_API_KEY"] == "unrelated-global-key"


def test_missing_named_compatible_secret_fails_before_endpoint_use(monkeypatch):
    monkeypatch.setenv("EVAL_COMPATIBLE_URL", "https://compatible.example.invalid/v1")
    monkeypatch.delenv("EVAL_COMPATIBLE_KEY", raising=False)
    profile = {"provider": "compatible", "model": "remote-model",
               "endpoint_env": "EVAL_COMPATIBLE_URL", "api_key_env": "EVAL_COMPATIBLE_KEY"}
    with pytest.raises(evaluation_v032.EvaluationError):
        with evaluation_v032.provider_environment(profile):
            raise AssertionError("missing secret must stop before the request body")


def test_replay_transport_is_offline_and_does_not_consume_generation_budget():
    from physis.evaluation_guard import generation_guard
    from physis.provider_config import ProviderSelection, provider_context
    from physis.providers import ReplayTransport, request_explanation

    reservations = []
    async def call():
        with provider_context(ProviderSelection(provider="mock", model="local-rules")) as metrics:
            with generation_guard(lambda operation: reservations.append(operation)):
                response = await request_explanation(
                    "mock", {"question": "What changes an object's velocity?", "level": "school"},
                    transport=ReplayTransport(content=json.dumps({
                        "text": "A net force changes velocity by producing acceleration."})))
        return response, metrics.as_dict()

    response, metrics = asyncio.run(call())
    assert "net force" in response.text
    assert reservations == []
    assert metrics["requests"][0]["origin"] == "replay"


def test_archived_b_import_is_labelled_and_never_runs_the_archived_app(tmp_path):
    archive = tmp_path / "saved-b.json"
    archive.write_text(json.dumps({"model_digest": "old-digest", "arms": {"B": {"rows": [
        {"case_id": "c1", "question": "safe question", "event": "error",
         "error": "saved failure", "events": [{"event": "error", "detail": "saved failure"}]}
    ]}}}), encoding="utf-8")
    progress = tmp_path / "progress.sqlite3"
    assert evaluation_v032.import_archived_b(progress, archive) == 0
    rows = evaluation_v032.compare_results([progress])
    assert rows[0]["arm"] == "B (ARCHIVED)"
    assert rows[0]["origin"] == "archived_baseline"
    assert rows[0]["text"] == "saved failure"
