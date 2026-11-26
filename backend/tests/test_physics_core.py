from math import sqrt
from uuid import uuid4

import numpy as np
import pytest

from physis.physics import SPECS, simulate
from physis.schema import Experiment


def experiment(key, *, method=None, dt=None, duration=None, **overrides):
    s = SPECS[key]
    values = {v.key: v.default for v in s.variables}
    values.update(overrides)
    options = s.model_dump()
    options.update(method=method or s.methods[0], values=values, id=uuid4())
    if dt is not None:
        options["dt"] = dt
    if duration is not None:
        options["duration"] = duration
    return Experiment(**options)


def test_free_fall_20m_from_rest():
    run = simulate(experiment("free_fall"))
    assert run.status == "VERIFIED"
    arrival = sqrt(40/9.81)
    assert run.times[-1] == pytest.approx(arrival, abs=1e-12)
    assert run.facts["arrival_time"] == run.times[-1]
    assert run.series["0.y"] == run.series["1.y"]
    assert run.series["0.y"][-1] == 0
    assert min(run.series["0.y"]) >= 0
    assert run.series["1.fy"][0] / run.series["0.fy"][0] == pytest.approx(5)
    assert run.series["0.vy"][-1] == pytest.approx(-sqrt(2*9.81*20))
    np.testing.assert_allclose(run.series["1.energy"], 5*9.81*20)


def test_preimpact_horizon_and_partial_step():
    run = simulate(experiment("free_fall", duration=1.055, dt=.1))
    assert "arrival_time" not in run.facts
    assert run.times[-1] == 1.055
    assert run.series["0.y"][-1] == pytest.approx(20 - 9.81*1.055**2/2)
    assert np.all(np.diff(run.times) > 0)


@pytest.mark.parametrize("method", ["euler", "semi_implicit"])
def test_euler_convergence_and_impact_bracket(method):
    run = simulate(experiment("free_fall", method=method, dt=.1))
    ratio = run.convergence[0]["error"]/run.convergence[1]["error"]
    assert 1.8 < ratio < 2.2
    assert (run.times[-1] > sqrt(40/9.81)) == (method == "euler")
    assert run.status == "FAILED"


@pytest.mark.parametrize("method", ["analytic", "euler", "semi_implicit", "rk4"])
def test_uniform_signed_speed(method):
    run = simulate(experiment("uniform", method=method, x0=2, v0=-3, duration=2.51, dt=.2))
    assert run.series["0.x"][-1] == pytest.approx(2-3*2.51)
    assert run.status == "VERIFIED"


@pytest.mark.parametrize(("key","params","a"), [("acceleration", {"a": -2}, -2), ("newton", {"force": -4, "mass": .5}, -8)])
def test_accelerated_force_work_and_position(key, params, a):
    run = simulate(experiment(key, v0=3, x0=1, duration=2, **params))
    assert run.facts["acceleration"] == a
    assert run.series["0.x"][-1] == pytest.approx(1 + 6 + 2*a)
    assert run.series["0.vx"][-1] == pytest.approx(3 + 2*a)
    assert run.status == "VERIFIED"
