from math import cos, exp, pi, sin, sqrt

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from physis.physics import SPECS, simulate
from test_physics_core import experiment


@pytest.mark.parametrize("key", list(SPECS))
def test_defaults_match_registry_and_pass(key):
    setup = experiment(key)
    run = simulate(setup)
    assert run.status == "VERIFIED", run.checks
    assert all(c.passed for c in run.checks)
    assert len(run.checks) > 0
    assert run.times[0] == 0 and np.all(np.diff(run.times) > 0)
    expected = {f"{i}.{k}" for i in range(len(setup.objects)) for k in setup.measurements}
    assert set(run.series) == expected
    for data in run.series.values():
        assert len(data) == len(run.times)
        assert np.isfinite(data).all()


def test_friction_negative_velocity_stop_and_force_sign():
    run = simulate(experiment("friction", v0=-3, mu=.4, g=10, mass=2))
    t = np.asarray(run.times)
    i = run.times.index(.75)
    assert run.series["0.fx"][0] == 8.
    assert run.series["0.fx"][i] == 0.
    assert run.facts["stop_distance"] == pytest.approx(1.125)
    np.testing.assert_allclose(np.asarray(run.series["0.x"])[t>=.75], -1.125)
    assert max(run.series["0.vx"]) == 0.
    assert run.status == "VERIFIED"


def test_no_friction_and_event_beyond_horizon():
    friction = simulate(experiment("friction", mu=0, v0=2))
    fall = simulate(experiment("free_fall", duration=.1))
    collision = simulate(experiment("collision", v_a=-1, v_b=1))
    assert all(r.status == "LIMITED" for r in [friction,fall,collision])
    assert "stop_time" not in friction.facts and friction.series["0.x"][-1] == 8.
    assert "arrival_time" not in fall.facts
    assert "collision_time" not in collision.facts
    assert collision.series["1.vx"][-1] == 1.


@pytest.mark.parametrize("e", [0., .25, 1.])
def test_collision_event_loss_momentum_and_restitution(e):
    m1,m2,u1,u2 = 2,3,4,-1
    run = simulate(experiment("collision", mass_a=m1,mass_b=m2,v_a=u1,v_b=u2,gap=1.125,restitution=e,dt=.1))
    arrival = .225
    i = run.times.index(arrival)
    assert run.facts["collision_time"] == arrival
    assert run.series["0.x"][i] == run.series["1.x"][i] == pytest.approx(.9)
    assert run.series["0.vx"][i-1] == u1
    assert run.series["0.vx"][i] == pytest.approx(1-3*e)
    assert run.series["1.vx"][i] == pytest.approx(1+2*e)
    assert run.facts["energy_loss"] == pytest.approx(15*(1-e**2))
    np.testing.assert_allclose(np.asarray(run.series["0.momentum"])+run.series["1.momentum"], 5.)
    assert run.status == "VERIFIED"


def test_elastic_equal_masses_exchange_velocity_at_final_horizon():
    run = simulate(experiment("collision", mass_a=1,mass_b=1,v_a=2,v_b=0,gap=2,duration=1,dt=.1))
    assert run.times.count(1.) == 1
    assert run.series["0.vx"][-1] == 0
    assert run.series["1.vx"][-1] == 2


@pytest.mark.parametrize(("method","min_ratio","max_ratio"), [
    ("rk4",14,18), ("euler",1.7,2.8), ("semi_implicit",1.7,2.4),
])
def test_spring_convergence_order(method,min_ratio,max_ratio):
    run = simulate(experiment("spring", method=method, dt=.05, duration=3, mass=1, k=4))
    errors = [row["error"] for row in run.convergence]
    assert min_ratio < errors[0]/errors[1] < max_ratio
    assert min_ratio < errors[1]/errors[2] < max_ratio


def test_coarse_euler_fails_and_resolved_rk4_passes():
    coarse = simulate(experiment("spring", method="euler", dt=.2, duration=10))
    refined = simulate(experiment("spring", method="rk4", dt=.02, duration=10))
    assert coarse.status == "FAILED"
    assert max(coarse.series["0.energy"])/coarse.series["0.energy"][0] > 100
    assert refined.status == "VERIFIED"
    assert max(refined.series["0.error"]) < 1e-5
    # The bounded, oscillating semi-implicit energy still differs from exact energy.
    symplectic = simulate(experiment("spring", method="semi_implicit", dt=.1, duration=30))
    e = symplectic.series["0.energy"]
    assert max(e)/min(e) < 1.5


def test_marginal_symplectic_euler_jordan_block():
    run = simulate(experiment("spring", method="semi_implicit", mass=1, k=100,
                              dt=.2, duration=.2, x0=0, v0=0))
    check = next(c for c in run.checks if "장시간 안정성" in c.label)
    assert not check.passed
    assert "중복 고유값" in check.detail
    assert run.status == "FAILED"


def test_nonfinite_state_only_returns_finite_prefix(monkeypatch):
    from physis import physics
    from physis.physics_common import Sample
    def broken_sample(exp, dt):
        sample = Sample(np.array([0., .02, .04]))
        sample.record(0, x=np.array([1., 2., float("inf")]))
        return sample
    monkeypatch.setattr(physics, "_sample", broken_sample)
    run = physics.simulate(experiment("spring"))
    assert run.status == "FAILED" and not run.checks[0].passed
    assert run.series["0.x"] == [1., 2.] and run.times == [0., .02]


@pytest.mark.parametrize("b", [0., 1., 4., 4.0000000001, 6.])
def test_damped_all_regimes_independent_ivp(b):
    run = simulate(experiment("damped", method="analytic", mass=1,k=4,damping=b,x0=.8,v0=-.1,dt=.01))
    t = np.asarray(run.times)
    independent = solve_ivp(lambda _,s:[s[1],-4*s[0]-b*s[1]], [0,t[-1]],[.8,-.1],
                            method="DOP853", t_eval=t, rtol=1e-11, atol=1e-12)
    np.testing.assert_allclose(run.series["0.x"],independent.y[0],atol=2e-10)
    np.testing.assert_allclose(run.series["0.vx"],independent.y[1],atol=2e-10)
    assert np.all(np.diff(run.series["0.energy"]) < 1e-12)
    assert run.status == "VERIFIED"


def test_critical_damping_textbook_value():
    run=simulate(experiment("damped",mass=1,k=4,damping=4,x0=1,v0=0,duration=1))
    assert run.series["0.x"][-1] == pytest.approx(3*exp(-2), abs=2e-7)
    assert "reference_period" not in run.facts


@pytest.mark.parametrize("angle", [-1.45, .1, 1.45])
def test_full_angle_pendulum_reference_vs_independent_ivp(angle):
    run = simulate(experiment("pendulum", angle=angle, method="analytic", duration=6))
    t = np.asarray(run.times)
    independent = solve_ivp(lambda _,s:[s[1],-9.81*sin(s[0])],[0,6],[angle,0],
                            t_eval=t, method="DOP853",rtol=1e-12,atol=1e-12)
    np.testing.assert_allclose(run.series["0.angle"],independent.y[0],atol=2e-10)
    np.testing.assert_allclose(run.series["0.angular_velocity"],independent.y[1],atol=2e-10)
    assert run.facts["reference_period"] > 2*pi/sqrt(9.81)
    assert run.facts["measured_period"] == pytest.approx(run.facts["reference_period"], rel=1e-4)


def test_circular_negative_direction():
    run = simulate(experiment("circular", mass=2,radius=3,omega=-2,duration=1))
    assert run.series["0.x"][-1] == pytest.approx(3*cos(2), abs=3e-7)
    assert run.series["0.y"][-1] == pytest.approx(-3*sin(2), abs=3e-7)
    assert run.series["0.fx"][0] == -24
    assert run.series["0.vy"][0] == -6


def test_stationary_equilibria():
    for key, params in [("pendulum",{"angle":0}), ("spring",{"x0":0,"v0":0}),
                        ("circular",{"omega":0}), ("friction",{"v0":0})]:
        run = simulate(experiment(key, **params))
        assert run.status == "VERIFIED"
        assert np.max(run.series["0.ke"]) == 0
        assert "reference_period" not in run.facts


def test_static_fluids_textbook_values():
    water = simulate(experiment("hydrostatic",density=1000,depth=2,g=10,p0=100000))
    assert water.facts == {"pressure":120000.,"gauge_pressure":20000.}
    body = simulate(experiment("buoyancy",density=1000,volume=.002,g=10,mass=1))
    assert body.facts == {"buoyancy":20., "weight":10., "support":-10.}
    assert body.series["0.fy"][0] == 0
    pipe = simulate(experiment("continuity",area_in=.06,area_out=.02,speed_in=2))
    assert pipe.facts["outlet_speed"] == pytest.approx(6.)
    assert pipe.facts["flow"] == pytest.approx(.12)
    for run in [water,body,pipe]:
        assert run.convergence == []
        assert all(np.all(np.diff(s) == 0.) for s in run.series.values())
