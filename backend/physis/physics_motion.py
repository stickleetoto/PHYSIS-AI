"""Constant accelerations, analytic reference paths and ground event localization."""
from math import sqrt

import numpy as np

from .physics_common import GRAVITY, MASS, MASS_A, MASS_B, V0, X0, Sample, grid, spec, variable


SPECS = {
    "free_fall": spec("free_fall", "두 물체의 자유낙하", "운동학", "질량이 다른 물체의 낙하 시간을 비교합니다.",
        "y = h − gt²/2, vᵧ = −gt", ["공기 저항 없음", "균일한 중력", "정지 상태에서 동시 낙하", "바닥에 처음 닿는 순간까지"],
        [MASS_A, MASS_B, variable("height", "출발 높이", "m", .2, 100, .1, 20), GRAVITY],
        "같은 높이에서 두 질량의 궤적과 도착 시간을 비교합니다.", objects=["물체 A", "물체 B"]),
    "uniform": spec("uniform", "등속 직선 운동", "운동학", "일정한 속도와 위치 변화의 관계를 관찰합니다.",
        "x = x₀ + v₀t", ["수평 직선 운동", "알짜힘 0"], [MASS, X0, V0], "속도의 부호와 위치 그래프의 기울기를 비교합니다."),
    "acceleration": spec("acceleration", "등가속도 직선 운동", "운동학", "시간에 따른 위치와 속도 변화를 측정합니다.",
        "x = x₀ + v₀t + at²/2", ["수평 직선 운동", "일정한 가속도", "위치 에너지 기준값 0"],
        [MASS, X0, V0, variable("a", "가속도", "m/s²", -10, 10, .1, 2)], "수치 위치와 등가속도 해를 비교합니다."),
    "newton": spec("newton", "뉴턴의 운동 제2법칙", "역학", "같은 힘에서 질량에 따른 가속도를 측정합니다.",
        "a = F/m, ΔK = FΔx", ["수평면", "일정한 수평 외력", "마찰 없음"],
        [MASS, X0, V0, variable("force", "수평 힘", "N", -30, 30, .1, 3)], "외력이 한 일과 운동 에너지 변화를 비교합니다."),
}


def kinematics(t, q0, v0, a, method):
    if method == "analytic":
        return q0 + v0*t + .5*a*t**2, v0 + a*t
    h = np.diff(t)
    fraction = {"euler": 0., "semi_implicit": 1., "rk4": .5}[method]
    # Component-wise cumulative updates preserve each method's recurrence.
    # RK4's four weighted stage velocities reduce to the midpoint velocity
    # when acceleration is constant. The closed-form reference is independent.
    v = v0 + np.r_[0., np.cumsum(a*h)]
    delta_q = h*(v[:-1] + fraction*a*h)
    return q0 + np.r_[0., np.cumsum(delta_q)], v


def fall(p, method, duration, dt):
    height, g = p["height"], p["g"]
    exact_time = sqrt(2*height/g)
    t = grid(duration, dt)
    y, vy = kinematics(t, height, 0., -g, method)
    crosses = np.flatnonzero(y <= 0)
    if not len(crosses) and method == "rk4" and duration == exact_time:
        crosses = [len(t)-1]
    arrived = len(crosses) > 0
    if method == "analytic":
        arrived = exact_time <= duration
        if arrived:
            t = grid(exact_time, dt)
            y, vy = kinematics(t, height, 0., -g, method)
            y[-1] = 0.
    elif arrived:
        i = crosses[0]
        begin = t[i-1]
        fraction = {"analytic": .5, "rk4": .5, "euler": 0., "semi_implicit": 1.}[method]
        h = t[i] - begin
        # Solve y₀ = downward_speed*s + fraction*g*s² on this last step.
        # Rationalizing the positive root also covers the linear Euler step.
        down = -vy[i-1]
        root = min(h, 2*y[i-1] / (down + sqrt(down**2 + 4*fraction*g*y[i-1])))
        impact = begin + root
        t = grid(impact, dt)
        y, vy = kinematics(t, height, 0., -g, method)
        y[-1] = 0.
    exact_y = np.maximum(0., height - .5*g*t**2)
    sample = Sample(t)
    for index, mass in enumerate([p["mass_a"], p["mass_b"]]):
        sample.body(index, mass, y=y, vy=vy, ay=-g, pe=mass*g*y, error=np.abs(y-exact_y))
        e0 = mass*g*height
        sample.residual(f"물체 {'AB'[index]} 역학적 에너지 보존", sample.series[f"{index}.energy"]-e0, e0, "J")
    sample.position_check(height)
    if arrived:
        sample.facts.update(arrival_time=t[-1], reference_arrival_time=exact_time, impact_speed=abs(vy[-1]))
        sample.residual("첫 도착 시간", t[-1]-exact_time, exact_time, "s")
    else:
        sample.limitation = "관찰이 끝날 때까지 바닥에 닿지 않아 도착 시간은 측정하지 못했습니다."
    return sample


def straight(key, p, method, duration, dt):
    mass = p["mass"]
    a = p["force"]/mass if key == "newton" else p.get("a", 0.)
    t = grid(duration, dt)
    x, vx = kinematics(t, p["x0"], p["v0"], a, method)
    exact = p["x0"] + p["v0"]*t + .5*a*t**2
    sample = Sample(t)
    sample.body(0, mass, x=x, vx=vx, ax=a, error=np.abs(x-exact))
    sample.position_check(max(np.max(np.abs(exact-p["x0"])), 1e-8))
    work = mass*a*(x-x[0])
    ke = sample.series["0.ke"]
    sample.residual("일과 운동 에너지 변화", ke-ke[0]-work, max(np.max(ke), np.max(np.abs(work))), "J")
    sample.facts.update(acceleration=a, final_position=x[-1], final_velocity=vx[-1])
    return sample
