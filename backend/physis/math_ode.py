"""Fixed educational initial-value problems using the existing Euler/RK4 integrator."""
from math import hypot
from typing import Literal

from fastapi import APIRouter
import numpy as np
from pydantic import Field

from .physics_common import integrate
from .physics_oscillations import spring_solution
from .schema import StrictModel

router = APIRouter(prefix="/api/math-lab")


class InitialValue(StrictModel):
    model: Literal["exponential", "spring", "damped"]
    coefficient: float = Field(strict=True, ge=-2, le=2, default=-0.5)
    mass: float = Field(strict=True, ge=0.5, le=20, default=1)
    k: float = Field(strict=True, ge=0.5, le=100, default=4)
    damping: float = Field(strict=True, ge=0, le=6, default=0.5)
    x0: float = Field(strict=True, ge=-3, le=3, default=1)
    v0: float = Field(strict=True, ge=-5, le=5, default=0)
    duration: float = Field(strict=True, ge=0.1, le=6, default=3)
    steps: int = Field(strict=True, ge=6, le=240, default=60)


@router.post("/ode")
def solve_ivp(s: InitialValue):
    t = np.linspace(0,s.duration,s.steps+1)
    initial_speed = s.v0
    if s.model == "exponential":
        r = s.coefficient
        reference = s.x0*np.exp(r*t)
        # v = r*x makes (x', v') = (v, r*v) exactly the scalar linear IVP.
        initial_speed = r*s.x0
        def accel(x,v):
            return r*v
        def direction(x,y):
            return 1,r*y
    else:
        drag = s.damping if s.model=="damped" else 0
        omega2 = s.k/s.mass
        def accel(x,v):
            return -omega2*x-drag*v/s.mass
        reference,_ = spring_solution(t,s.x0,s.v0,drag/(2*s.mass),omega2)
        def direction(x,y):
            return y,accel(x,y)

    def curve(label,series):
        return dict(label=label, segments=[[[float(a),float(b)] for a,b in zip(t,series)]])
    curves=[curve("해석해",reference)]
    rows=[]
    for method in ("euler","rk4"):
        q,_=integrate(t,s.x0,initial_speed,accel,method)
        curves.append(curve(method.upper(),q))
        rows.append(dict(label=method.upper()+" 최대 절대 오차",value=f"{max(abs(q-reference)):.8g}",kind="numeric"))
    field=[]
    for x in np.linspace(-2,2,9):
        for y in np.linspace(-2,2,9):
            dx,dy=direction(x,y)
            length=hypot(dx,dy)
            if length:
                field.append([float(x),float(y),dx/length,dy/length])
    return dict(status="ok",rows=rows,curves=curves,field=field)
