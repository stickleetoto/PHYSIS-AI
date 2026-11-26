"""Independent references: characteristic waves, ODE IVP, finite-difference heat PDE."""
from math import pi

import numpy as np
import pytest
from scipy.integrate import solve_ivp
from scipy.linalg import eigh_tridiagonal

from physis.physics_fields import SPECS, field_sample


def sample(key, duration=2, dt=.025, **changes):
    values = {v.key:v.default for v in SPECS[key].variables} | changes
    result = field_sample(key, values, "analytic", duration, dt)
    assert result.checks and all(check.passed for check in result.checks)
    return result


@pytest.mark.parametrize("key", [key for key in SPECS if key.startswith("wave_")])
def test_full_space_time_wavefield_against_translated_profiles(key):
    params = dict(amplitude=.024,frequency=.8,wavelength=.7)
    if key == "wave_superposition":
        params["phase"] = .72
    r = sample(key,**params)
    a,length,speed = .024,.7,.56
    for x in [.0, .19, .35, .83]:
        u = r.series["0.displacement"]*np.cos(2*pi*x/length) + r.series["0.quarter_displacement"]*np.sin(2*pi*x/length)
        def profile(distance):
            return a*np.sin(2*pi*distance/length)
        expected = profile(x-speed*r.times)
        if key == "wave_standing":
            expected += profile(x+speed*r.times)
        if key == "wave_superposition":
            expected += profile(x-speed*r.times+.72*length/(2*pi))
        np.testing.assert_allclose(u,expected,atol=5e-15,rtol=0)
    assert r.facts["wave_speed"] == pytest.approx(speed)
    assert r.facts["wave_period"] == pytest.approx(1.25)


def test_interference_cancellation_and_quarter_period_motion():
    r = sample("wave_superposition",phase=pi)
    assert max(np.max(np.abs(s)) for s in r.series.values()) < 2e-16
    for key in ("wave_transverse","wave_longitudinal"):
        r = sample(key,dt=.25)
        assert r.series["0.displacement"][1] == pytest.approx(-.03)
        assert r.series["0.quarter_displacement"][1] == pytest.approx(0,abs=1e-14)


def test_gas_law_standard_reference_and_boyle_scaling():
    r = sample("ideal_gas",temperature=273.15,volume=.02241397)
    assert r.series["0.pressure"][0] == pytest.approx(101325,rel=1e-6)
    larger = sample("ideal_gas",temperature=273.15,volume=.04482794)
    assert larger.facts["pressure"] == pytest.approx(r.facts["pressure"]/2)


@pytest.mark.parametrize("pair", [(290,370),(330,330),(370,290)])
def test_heat_exchange_independent_ivp_and_energy_balance(pair):
    r = sample("heat_equilibrium",temp_a=pair[0],temp_b=pair[1],capacity_a=7,capacity_b=13,conductance=4)
    def rhs(_,z):
        q = 4*(z[1]-z[0])
        return q/7,-q/13
    ref = solve_ivp(rhs,[0,2],pair,t_eval=r.times,method="DOP853",rtol=1e-12,atol=1e-12)
    for i in (0,1):
        np.testing.assert_allclose(r.series[f"{i}.temperature"],ref.y[i],atol=1e-8,rtol=0)
    np.testing.assert_allclose(r.series["0.heat"]+r.series["1.heat"],0,atol=3e-12)


@pytest.mark.parametrize("initial",[260,290,360])
def test_cooling_and_warming_independent_ivp(initial):
    r = sample("cooling",initial_temp=initial)
    ref = solve_ivp(lambda t,z:.5*(290-z),[0,2],[initial],t_eval=r.times,method="DOP853",rtol=1e-12,atol=1e-12)
    np.testing.assert_allclose(r.series["0.temperature"],ref.y[0],atol=2e-8,rtol=0)


def test_heat_diffusion_independent_dirichlet_grid():
    # Diagonalize the centered spatial difference operator, then advance all modes.
    n,length,alpha = 99,.37,.0007
    x = np.linspace(0,length,n+2)[1:-1]
    scale = alpha/(length/(n+1))**2
    vals,vecs = eigh_tridiagonal(-2*scale*np.ones(n),scale*np.ones(n-1))
    initial = 37*np.sin(pi*x/length)
    r = sample("heat_diffusion",length=length,diffusivity=alpha,excess=37,boundary_temp=270)
    ref = vecs @ ((vecs.T @ initial)[:,None] * np.exp(vals[:,None]*r.times))
    projected = np.sin(pi*x[:,None]/length)*(r.series["0.temperature"]-270)
    np.testing.assert_allclose(projected,ref,atol=.0003,rtol=0)
    assert np.all(r.series["0.edge_temperature"] == 270)
    assert np.all(np.diff(r.series["0.temperature"]) <= 0)


def test_bernoulli_pressure_difference_and_stationary_limit():
    r = sample("bernoulli",inlet_pressure=100000,density=1000,area_in=.06,area_out=.02,speed_in=2)
    assert r.facts["outlet_pressure"] == pytest.approx(84000)
    assert r.series["1.flow"][0] == pytest.approx(.12)
    still = sample("bernoulli",speed_in=0)
    assert still.series["0.pressure"][-1] == still.series["1.pressure"][-1]


def test_tracer_advection_reference():
    r = sample("fluid_tracer",x0=.7,speed=1.25)
    # Time of passage at x=1.7 m is 0.8 s.
    assert np.interp(1.7,r.series["0.x"],r.times) == pytest.approx(.8)
    still = sample("fluid_tracer",speed=0)
    np.testing.assert_allclose(still.series["0.x"],.2)
