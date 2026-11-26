from uuid import uuid4

import pytest

from physis import evidence, reasoning
from physis.api import snapshot
from physis.physics import SPECS
from physis.schema import Patch
from physis.state import build


def run_question(question, model):
    plan = reasoning._local(reasoning._norm(question), None, "school", SPECS)
    assert plan.model == model and plan.action == "create"
    return snapshot(build(SPECS[model], uuid4(), plan.patch), 1, "school")


@pytest.mark.parametrize("question,model,key,expected", [
    ("질량 4 kg 수레에 18 N을 가할 때 가속도는?", "newton", "acceleration", 4.5),
    ("수레 질량 2.5 kg, 가속도 -1.4 m/s²일 때 알짜힘은?", "newton", "net_force", -3.5),
    ("밀도 750 kg/m³에서 2 L를 밀어낸 블록의 부력, g=9 m/s²", "buoyancy", "buoyancy", 13.5),
    ("평형 온도는? 처음 두 온도가 300 K와 330 K, 열용량은 4 J/K와 8 J/K입니다.", "heat_equilibrium", "equilibrium_temp", 320),
    ("관의 입구 유속 3 m/s, 입구 단면적 200 cm², 출구 단면적 500 cm²일 때 출구 속도는?", "continuity", "outlet_speed", 1.2),
])
def test_different_inputs_bind_to_the_actual_run(question, model, key, expected):
    s = run_question(question,model)
    record = next(n for n in evidence.readings(s, question=question) if n["key"] == key)
    assert record["value"] == pytest.approx(expected)
    assert record["status"] == "calculation_verified"
    assert record["experiment_id"] == str(s.experiment.id) and record["run_id"] == evidence.run_id(s)


def test_failed_run_is_diagnostic_and_rejects_mislabelled_units():
    s = run_question("질량 4 kg 수레에 18 N을 가할 때 가속도는?", "newton")
    n = evidence.NumberClaim(key="acceleration", value=4.5, unit="m/s^2", experiment_id=str(s.experiment.id),
                             revision=1, run_id=evidence.run_id(s))
    assert evidence.check_number(n, s)["status"] == "calculation_verified"
    assert evidence.check_number(n.model_copy(update={"unit":"m^/s2"}), s)["status"] == "failed"
    unstable = snapshot(build(SPECS["spring"], uuid4(), Patch(method="euler",dt=.2,duration=10)), 1, "school")
    assert unstable.run.status == "FAILED"
    assert all(v["status"] == "unverifiable" for v in evidence.readings(unstable))
    assert [c["status"] for c in evidence.check_reported_numbers("acceleration is 94 m/s²",s)] == ["failed"]


def test_numerical_spelling_preserves_small_and_large_values():
    assert [evidence.format_value(x) for x in [0,1.234567,1e-9,40210000]] == ["0","1.235","1e-09","4.021e+07"]


def test_highlight_is_bound_to_the_requested_series_and_execution():
    s = run_question("높이 12 m에서 자유낙하", "free_fall")
    selection = {"op":"highlight_graph","quantity":"y","start":.12,"end":.46}
    reading = evidence.graph_observation(s, [selection, {"op":"highlight_object","index":1}])
    assert reading["reference"] == "1.y" and reading["run_id"] == evidence.run_id(s)
    for sample in reading["samples"]:
        assert sample["value"] == s.run.series["1.y"][sample["index"]]
        assert sample["time"] == s.run.times[sample["index"]]
    assert evidence.graph_observation(s,[{**selection,"quantity":"unknown"}]) is None
    assert evidence.graph_observation(s,[{**selection,"end":200}]) is None


def test_measured_acceleration_cannot_silently_override_a_conflicting_force():
    with pytest.raises(ValueError):
        reasoning._parse_patch("질량 2 kg, 힘 3 N에 가속도 5 m/s²", SPECS["newton"], None)


def test_unit_guidance_uses_registry_and_dimension_arithmetic():
    from physis.classroom_units import unit_note
    assert "m³/s" in unit_note("m²와 m/s를 곱하면 단위가 어떻게 될까?", "continuity")
    assert "N/m" in unit_note("용수철 상수 k의 단위가 뭐야?", "spring")
    assert not unit_note("F=ma에서 힘을 바꿔줘","newton")


def test_saved_v03_reports_recheck_units_and_values_against_reconstructed_run():
    s = run_question("질량 4 kg 수레에 18 N을 가할 때 가속도는?", "newton")
    old = evidence._fingerprint(s, include_readouts=False)
    claim = evidence.NumberClaim(key="acceleration",value=4.5,unit="m/s²",experiment_id=str(s.experiment.id),
                                 revision=s.revision,run_id=old)
    assert evidence.check_number(claim,s)["fingerprint_version"] == "0.3"
    assert evidence.check_number(claim.model_copy(update={"value":45}),s)["status"] == "failed"
    stamp = evidence.run_id(s)
    s.run.series["0.x"][-1] += 1
    assert stamp != evidence.run_id(s)

