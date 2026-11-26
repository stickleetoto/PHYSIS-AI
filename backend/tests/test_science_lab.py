import json
from uuid import uuid4

import numpy as np
import pytest
from fastapi import HTTPException

from physis.physics import SPECS, simulate
from physis.physics_fields import SPECS as FIELD_SPECS
from physis.reasoning import _local, explain
from physis.schema import Patch
from physis.science_api import get_formulas, numerical_lab
from physis.state import build


def test_formula_catalog_keys_symbols_units_and_real_graphs():
    # Independently listed SI dimensions for all tunable inputs in the original registry.
    units = {"mass":"kg","mass_a":"kg","mass_b":"kg","height":"m","g":"m/s²","x0":"m","v0":"m/s",
             "a":"m/s²","force":"N","mu":"1","v_a":"m/s","v_b":"m/s","gap":"m","restitution":"1",
             "k":"N/m","length":"m","angle":"rad","damping":"N·s/m","radius":"m","omega":"rad/s",
             "density":"kg/m³","depth":"m","p0":"Pa","volume":"m³","area_in":"m²","area_out":"m²","speed_in":"m/s"}
    expected_outputs = {"free_fall":"m","uniform":"m","acceleration":"m","newton":"m/s²","friction":"m/s",
                        "collision":"kg·m/s","spring":"m","damped":"J","pendulum":"rad","circular":"m/s²",
                        "hydrostatic":"Pa","buoyancy":"N","continuity":"m/s"}
    formulas = get_formulas()
    assert formulas.keys() == expected_outputs.keys()
    for key,c in formulas.items():
        spec = SPECS[key]
        assert c["steps"] and len(c["steps"]) >= 2 and c["dimensions"] and c["related"] in formulas
        assert c["source"].startswith("https://openstax.org/") and c["latex"] and c["outputs"]
        assert set(c["symbols"]) == {v.key for v in spec.variables}
        assert all(units[v.key] == v.unit for v in spec.variables)
        assert spec.measurements[c["quantity"]] == expected_outputs[key]
        run = simulate(build(spec,uuid4(),Patch()))
        assert "0."+c["quantity"] in run.series


def test_numerical_lab_closed_form_metrics_timing_and_order():
    result = numerical_lab(Patch(values={"mass":2,"k":8,"x0":.75,"v0":1},dt=.04,duration=3.013))
    t = np.array(result["times"])
    expected = .75*np.cos(2*t)+.5*np.sin(2*t)
    amplitude = np.sqrt(.75**2+.5**2)
    assert result["amplitude"] == pytest.approx(amplitude)
    assert result["initial_energy"] == pytest.approx(3.25)
    assert t[-1] == 3.013
    rows = {r["method"]:r for r in result["rows"]}
    assert rows.keys() == {"analytic","rk4","euler","semi_implicit"}
    for method,r in rows.items():
        assert r["elapsed_ms"] > 0
        error = max(abs(r["position"]-expected))
        assert r["absolute_error"] == pytest.approx(error,abs=1e-14)
        assert r["relative_error"] == pytest.approx(error/amplitude,abs=1e-14)
        if method == "analytic":
            np.testing.assert_allclose(r["position"],expected,atol=1e-15)
            assert r["convergence"] == []
            assert r["energy_drift"] < 1e-13
        else:
            a,b,c = [point["error"] for point in r["convergence"]]
            assert r["absolute_error"] == a
            ratio = 16 if method == "rk4" else 2
            assert b/c == pytest.approx(ratio,rel=.2)
    assert rows["euler"]["energy_drift"] > rows["semi_implicit"]["energy_drift"] > rows["rk4"]["energy_drift"]


def test_zero_reference_and_invalid_input():
    result = numerical_lab(Patch(values={"x0":0,"v0":0},dt=.1))
    assert all(r["relative_error"] is None and r["absolute_error"] == r["energy_drift"] == 0 for r in result["rows"])
    for p in [Patch(method="rk4"),Patch(dt=0),Patch(duration=30,dt=.002),Patch(values={"mass":-1})]:
        with pytest.raises(HTTPException) as error:
            numerical_lab(p)
        assert error.value.status_code == 422


@pytest.mark.parametrize("dt", [.2, 30/214, .14142])
def test_stiff_spring_unstable_methods_remain_finite_across_accepted_grid(dt):
    result = numerical_lab(Patch(values={"mass":.5,"k":100,"x0":3,"v0":5},duration=30,dt=dt))
    json.dumps(result,allow_nan=False)
    rows = {row["method"]:row for row in result["rows"]}
    assert all(len(row["position"]) == len(result["times"]) for row in rows.values())
    assert rows["euler"]["energy_drift"] > 1e140
    assert rows["semi_implicit"]["energy_drift"] > (1e230 if dt == .2 else 1e4)
    assert rows["analytic"]["energy_drift"] < 1e-10


def test_sampled_wave_aliasing_report_and_solver_error_explanation():
    aliased = build(SPECS["wave_transverse"],uuid4(),Patch(values={"frequency":3},dt=.2))
    assert simulate(aliased).status == "LIMITED"
    bad = build(SPECS["spring"],uuid4(),Patch(method="euler",dt=.2,duration=10))
    run = simulate(bad)
    assert run.status == "FAILED"
    explanation = explain(bad,run,"school")
    assert "같은 방정식의 기준해" in explanation and "실제 장치" in explanation
    assert "선형 복원력" in explanation


@pytest.mark.parametrize("key,question",[
    ("wave_transverse","주파수가 2 Hz인 사인파 실험"),
    ("wave_longitudinal","종파를 관찰할래"),("wave_standing","정상파를 보여 줘"),
    ("wave_superposition","파동의 중첩 실험"),("cooling","뉴턴의 냉각 법칙"),
    ("bernoulli","베르누이 원리로 유속을 비교해줘"),("fluid_tracer","유체 입자 이동"),
    ("ideal_gas","온도 320 K인 이상기체"),("heat_equilibrium","두 물체의 열평형 실험"),
    ("heat_diffusion","막대의 열확산 실험")])
def test_new_models_create_in_mock_and_report_a_calculated_observation(key, question):
    intent = _local(question,None,"school",SPECS)
    assert (intent.action,intent.model) == ("create",key), intent
    exp = build(FIELD_SPECS[key],uuid4(),intent.patch)
    if key == "wave_transverse":
        assert exp.values["frequency"] == 2
    if key == "ideal_gas":
        assert exp.values["temperature"] == 320
    run = simulate(exp)
    assert run.status == "VERIFIED"
    assert "이번 실행에서 기록한 값" in explain(exp,run,"school")
