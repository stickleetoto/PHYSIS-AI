"""Local formula library and controlled harmonic-oscillator method comparison."""
from time import perf_counter_ns
from uuid import UUID

from fastapi import APIRouter, HTTPException
import numpy as np

from .physics import SPECS
from .physics_common import grid, integrate
from .schema import Patch
from .science_formulas import FORMULAS
from .state import build

router = APIRouter(prefix="/api/science")


@router.get("/formulas")
def get_formulas():
    return FORMULAS


def solve(method, times, x0, v0, omega):
    if method == "analytic":
        phase = omega * times
        return (x0*np.cos(phase)+(v0/omega)*np.sin(phase),
                v0*np.cos(phase)-x0*omega*np.sin(phase))
    omega_squared = omega**2
    return integrate(times, x0, v0, lambda x,v:-omega_squared*x, method)


@router.post("/numerical")
def numerical_lab(settings: Patch):
    if settings.method is not None:
        raise HTTPException(422, "이 실험은 네 계산법을 모두 비교합니다.")
    try:
        experiment = build(SPECS["spring"],UUID(int=0),settings)
    except ValueError:
        raise HTTPException(422, "용수철 입력 범위와 시간 격자(최대 4,000 스텝)를 확인하세요.") from None
    p = experiment.values
    m,k,x0,v0 = (p[key] for key in ("mass","k","x0","v0"))
    omega = np.sqrt(k/m)
    times = grid(experiment.duration,experiment.dt)
    e0 = .5*(k*x0*x0+m*v0*v0)
    amplitude = np.hypot(x0,v0/omega)
    reference = solve("analytic",times,x0,v0,omega)[0]
    rows = []
    for method in ["analytic","euler","semi_implicit","rk4"]:
        # Only trajectory calculation is timed, uniformly across methods.
        started = perf_counter_ns()
        x,v = solve(method,times,x0,v0,omega)
        elapsed_ms = (perf_counter_ns()-started)/1_000_000
        absolute = float(np.max(np.abs(x-reference)))
        energy = .5*(k*x*x+m*v*v)
        drift = float(np.max(np.abs(energy-e0)))
        curve = []
        if method != "analytic":
            curve.append(dict(dt=experiment.dt,error=absolute))
            for factor in (2,4):
                h = experiment.dt/factor
                refined = grid(experiment.duration,h)
                solved = solve(method,refined,x0,v0,omega)[0]
                exact = solve("analytic",refined,x0,v0,omega)[0]
                curve.append(dict(dt=h,error=float(np.max(np.abs(solved-exact)))))
        rows.append(dict(method=method, position=x.tolist(), elapsed_ms=elapsed_ms,
                         absolute_error=absolute, relative_error=absolute/amplitude if amplitude else None,
                         energy_drift=drift, convergence=curve))
    return dict(model="spring", times=times.tolist(), amplitude=amplitude, initial_energy=e0,
                values=p, duration=experiment.duration, dt=experiment.dt, rows=rows)
