"""SI series and scalar second-order fixed-step integrators shared by the models."""
from dataclasses import dataclass, field
from math import ceil

import numpy as np

from .schema import Check, ModelSpec, Variable


METHODS = ["rk4", "analytic", "euler", "semi_implicit"]
MECHANICS = {
    "x": "m", "y": "m", "vx": "m/s", "vy": "m/s", "ax": "m/s²", "ay": "m/s²",
    "fx": "N", "fy": "N", "ke": "J", "pe": "J", "energy": "J", "error": "m",
}


def variable(key, label, unit, low, high, step, default):
    return Variable(key=key, label=label, unit=unit, min=low, max=high, step=step, default=default)


MASS = variable("mass", "질량", "kg", 0.5, 20, 0.1, 1)
MASS_A = variable("mass_a", "물체 A 질량", "kg", 0.5, 20, 0.1, 1)
MASS_B = variable("mass_b", "물체 B 질량", "kg", 0.5, 20, 0.1, 5)
GRAVITY = variable("g", "중력 가속도 크기", "m/s²", 0.5, 25, 0.01, 9.81)
X0 = variable("x0", "처음 위치", "m", -10, 10, 0.1, 0)
V0 = variable("v0", "처음 속도", "m/s", -10, 10, 0.1, 2)


def spec(key, title, category, goal, formula, assumptions, variables, comparison,
         *, methods=None, measurements=None, objects=None, duration=4):
    return ModelSpec(
        model=key, title=title, category=category, goal=goal, formula=formula,
        assumptions=assumptions, variables=variables, methods=methods or METHODS,
        measurements=measurements or MECHANICS, visualization=key, comparison=comparison,
        objects=objects or ["물체"], duration=duration,
    )


def grid(duration, dt, event=None):
    # Preserve full steps. Replace a near-coincident final grid point and insert
    # interior event times without generating tiny duplicate time intervals.
    margin = 1e-12 * max(1., duration, dt)
    points = np.arange(ceil(duration / dt), dtype=float) * dt
    points = np.append(points[points < duration - margin], duration)
    if event is not None and 0 < event < duration:
        keep = (np.abs(points - event) > margin) | (points == 0) | (points == duration)
        points = np.sort(np.append(points[keep], event))
    return points


def step(q, v, h, acceleration, method):
    a = acceleration(q, v)
    if method == "euler":
        return q + h*v, v + h*a
    if method == "semi_implicit":
        v_next = v + h*a
        return q + h*v_next, v_next
    if method != "rk4":
        raise ValueError(f"지원하지 않는 수치 적분 방법: {method}")
    v2 = v + h*a/2
    a2 = acceleration(q + h*v/2, v2)
    v3 = v + h*a2/2
    a3 = acceleration(q + h*v2/2, v3)
    v4 = v + h*a3
    a4 = acceleration(q + h*v3, v4)
    return q + h*(v + 2*v2 + 2*v3 + v4)/6, v + h*(a + 2*a2 + 2*a3 + a4)/6


def integrate(times, q0, v0, accel, method):
    q = np.empty(len(times))
    v = np.empty(len(times))
    q[0], v[0] = q0, v0
    for i, h in enumerate(np.diff(times), 1):
        q[i], v[i] = step(q[i-1], v[i-1], h, accel, method)
    return q, v


@dataclass
class Sample:
    times: np.ndarray
    series: dict = field(default_factory=dict)
    facts: dict = field(default_factory=dict)
    checks: list = field(default_factory=list)
    limitation: str = ""

    def record(self, index, **quantities):
        for key, values in quantities.items():
            self.series[f"{index}.{key}"] = np.broadcast_to(values, self.times.shape)

    def body(self, index, mass, *, x=0., y=0., vx=0., vy=0., ax=0., ay=0., pe=0., error=0.):
        ke = mass * (vx**2 + vy**2) / 2
        self.record(index, x=x, y=y, vx=vx, vy=vy, ax=ax, ay=ay, fx=mass*ax, fy=mass*ay,
                    ke=ke, pe=pe, energy=ke+pe, error=error)

    def residual(self, label, difference, scale, unit, *, rtol=.01, atol=1e-8):
        peak = float(np.max(np.abs(difference)))
        limit = atol + rtol*abs(scale)
        self.checks.append(Check(label=label, passed=peak <= limit,
                                 detail=f"최대 편차 {peak:.4g} {unit} · 허용 {limit:.4g} {unit}"))

    def position_check(self, scale):
        self.residual("기준해와 위치 비교", self.max_error(), scale, "m")

    def max_error(self):
        return max((float(np.max(v)) for k, v in self.series.items() if k.endswith(".error")), default=0.)
