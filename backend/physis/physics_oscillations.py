"""Spring, dissipative spring, full-angle pendulum and circular reference orbit."""
from math import pi, sin, sqrt

import numpy as np

from .physics_common import GRAVITY, MASS, MECHANICS, Sample, grid, integrate, spec, step, variable
from .schema import Check


STIFFNESS = variable("k", "용수철 상수", "N/m", .5, 100, .5, 10)
DISPLACEMENT = variable("x0", "처음 변위", "m", -3, 3, .05, 1)
INITIAL_SPEED = variable("v0", "처음 속도", "m/s", -5, 5, .1, 0)
SPECS = {
    "spring": spec("spring", "용수철의 단순 조화 운동", "진동", "질량과 용수철 상수가 주기를 어떻게 바꾸는지 측정합니다.",
        "mẍ = −kx, T = 2π√(m/k)", ["선형 복원력", "수평 운동", "마찰 없음"],
        [MASS, STIFFNESS, DISPLACEMENT, INITIAL_SPEED], "주기와 운동·탄성 위치 에너지의 교환을 비교합니다.", duration=6),
    "damped": spec("damped", "점성 감쇠 진동", "진동", "감쇠 계수에 따른 진폭 감소와 에너지 소산을 측정합니다.",
        "mẍ + bẋ + kx = 0, dE/dt = −bv²", ["선형 용수철", "속도에 비례하는 감쇠력", "외부 구동 없음"],
        [MASS, STIFFNESS, variable("damping", "감쇠 계수", "N·s/m", 0, 6, .05, .6), DISPLACEMENT, INITIAL_SPEED],
        "감쇠로 잃은 역학적 에너지와 소산된 에너지를 비교합니다.",
        measurements=MECHANICS | {"dissipated":"J"}, duration=6),
    "pendulum": spec("pendulum", "단진자의 비선형 진동", "진동", "진폭에 따라 달라지는 주기를 측정합니다.",
        "θ̈ = −(g/L)sin θ, T = 4√(L/g)K(sin²(θ₀/2))",
        ["질량 없는 고정 길이 줄", "점질량", "마찰 없음", "정지 상태에서 놓음", "최저점의 높이 0"],
        [MASS, variable("length", "줄 길이", "m", .2, 5, .1, 1),
         variable("angle", "처음 각도", "rad", -1.55, 1.55, .05, .4), GRAVITY],
        "측정한 주기와 유한 진폭 이론 주기를 비교합니다.",
        measurements=MECHANICS | {"angle":"rad","angular_velocity":"rad/s"}, duration=6),
    "circular": spec("circular", "등속 원운동", "역학", "속도와 구심 가속도의 방향을 추적합니다.",
        "a⃗ = −ω²r⃗, |v| = |ω|R", ["평면 운동", "원점 방향의 선형 중심력", "초기 속도는 원의 접선 방향"],
        [MASS, variable("radius", "반지름", "m", .1, 5, .1, 1),
         variable("omega", "각속도", "rad/s", -8, 8, .1, 2)],
        "수치 궤도의 반지름과 이론에서 일정한 속력을 비교합니다.", duration=6),
}


def spring_solution(t, x0, v0, gamma, omega2):
    # The two fundamental responses C and S remain continuous at critical damping.
    discriminant = omega2 - gamma**2
    if discriminant >= 0:
        w = sqrt(discriminant)
        decay = np.exp(-gamma*t)
        c = decay*np.cos(w*t)
        s = decay*t*np.sinc(w*t/pi)
    else:
        w = sqrt(-discriminant)
        slow = np.exp(-omega2/(gamma+w)*t)
        fast = np.exp(-(gamma+w)*t)
        c = (slow+fast)/2
        s = slow * (-np.expm1(-2*w*t))/(2*w)
    return c*x0 + s*(v0+gamma*x0), c*v0 - s*(gamma*v0+omega2*x0)


def period_facts(sample, displacement, reference_period):
    sample.facts["reference_period"] = reference_period
    indices = np.flatnonzero((displacement[:-1] >= 0) & (displacement[1:] < 0))
    if len(indices) >= 2:
        i = indices
        t = sample.times
        roots = t[i] + (t[i+1]-t[i]) * displacement[i]/(displacement[i]-displacement[i+1])
        sample.facts["measured_period"] = float(np.mean(np.diff(roots)))
        sample.residual("측정 주기와 기준 주기", np.diff(roots)-reference_period, reference_period, "s")


def linear_stability(sample, acceleration, method, h):
    if method == "analytic":
        return
    # Advance the two basis vectors to obtain the exact discrete transition
    # matrix for one full numerical step of this homogeneous linear system.
    matrix = np.column_stack([step(1.,0.,h,acceleration,method), step(0.,1.,h,acceleration,method)])
    eigenvalues = np.linalg.eigvals(matrix)
    radius = float(np.max(np.abs(eigenvalues)))
    # A repeated multiplier on the unit circle also requires two independent
    # eigenvectors. The undamped semi-implicit method has a Jordan block at hω=2.
    defective = (method == "semi_implicit" and acceleration(0.,1.) == 0.
                 and abs(-h*h*acceleration(1.,0.)-4.) < 1e-12)
    passed = radius <= 1+1e-10 and not defective
    sample.checks.append(Check(label="선형 적분의 장시간 안정성", passed=passed,
        detail=f"한 스텝의 최대 고유값 크기 {radius:.10g} · 기준 1 이하"
               + (" · 중복 고유값에서 교란이 누적됩니다." if defective else "")))
    sample.facts["spectral_radius"] = radius


def oscillator(key, p, method, duration, dt):
    t = grid(duration, dt)
    m, k, b = p["mass"], p["k"], p.get("damping", 0.)
    x0, v0 = p["x0"], p["v0"]
    omega2, gamma = k/m, b/(2*m)
    reference, ref_v = spring_solution(t, x0, v0, gamma, omega2)
    def acceleration(x, v):
        return -omega2*x - 2*gamma*v
    x, vx = (reference, ref_v) if method == "analytic" else integrate(t, x0, v0, acceleration, method)
    sample = Sample(t)
    sample.body(0, m, x=x, vx=vx, ax=acceleration(x,vx), pe=.5*k*x**2, error=np.abs(x-reference))
    e0 = .5*(m*v0**2+k*x0**2)
    sample.position_check(sqrt(2*e0/k))
    energy_change = sample.series["0.energy"]-e0
    if key == "damped":
        power = b*vx**2
        heat = np.r_[0., np.cumsum((power[:-1] + power[1:]) * .5 * np.diff(t))]
        sample.record(0, dissipated=heat)
        sample.residual("역학적 에너지와 누적 소산량의 합", energy_change+heat, e0, "J")
        sample.facts.update(damping_ratio=gamma/sqrt(omega2), dissipated_energy=heat[-1])
    else:
        sample.residual("역학적 에너지 보존", energy_change, e0, "J")
    if omega2 > gamma**2 and e0 > 0:
        period_facts(sample, x, 2*pi/sqrt(omega2-gamma**2))
    linear_stability(sample, acceleration, method, dt)
    return sample


def pendulum(p, method, duration, dt):
    from scipy.special import ellipj, ellipk

    t = grid(duration, dt)
    m, length, angle, g = (p[k] for k in ("mass", "length", "angle", "g"))
    w = sqrt(g/length)
    k = sin(angle/2)
    K = ellipk(k*k)
    sn, cn, _, _ = ellipj(K-w*t, k*k)
    ref_q = 2*np.arcsin(np.clip(k*sn, -1., 1.))
    ref_v = -2*k*w*cn
    ref_q[0], ref_v[0] = angle, 0.
    def accel(theta, angular_speed):
        return -(g/length)*sin(theta)
    q, v = (ref_q,ref_v) if method == "analytic" else integrate(t, angle, 0., accel, method)
    s, c = np.sin(q), np.cos(q)
    # 2 sin²(q/2) avoids cancellation for small angles.
    x, y = length*s, 2*length*np.sin(q/2)**2
    alpha = -(g/length)*s
    error = 2*length*np.abs(np.sin((q-ref_q)/2))
    sample = Sample(t)
    sample.body(0, m, x=x, y=y, vx=length*c*v, vy=length*s*v,
                ax=length*(c*alpha-s*v*v), ay=length*(s*alpha+c*v*v), pe=m*g*y, error=error)
    sample.record(0, angle=q, angular_velocity=v)
    sample.position_check(2*length*abs(k))
    e0 = 2*m*g*length*k*k
    sample.residual("역학적 에너지 보존", sample.series["0.energy"]-e0, e0, "J")
    sample.residual("줄 길이 제약", np.hypot(x,y-length)-length, length, "m", rtol=1e-10)
    if angle != 0:
        period_facts(sample, q, 4*K/w)
    return sample


def circular(p, method, duration, dt):
    t = grid(duration, dt)
    m, r, w = p["mass"], p["radius"], p["omega"]
    x_ref, y_ref = r*np.cos(w*t), r*np.sin(w*t)
    def accel(q, v):
        return -(w*w)*q
    if method == "analytic":
        x, y, vx, vy = x_ref, y_ref, -w*y_ref, w*x_ref
    else:
        x, vx = integrate(t, r, 0., accel, method)
        y, vy = integrate(t, 0., r*w, accel, method)
    sample = Sample(t)
    r2 = x*x+y*y
    sample.body(0, m, x=x,y=y,vx=vx,vy=vy,ax=-w*w*x,ay=-w*w*y,
                pe=.5*m*w*w*r2,error=np.hypot(x-x_ref,y-y_ref))
    sample.position_check(r)
    sample.residual("궤도 반지름", np.sqrt(r2)-r, r, "m")
    e0 = m*(w*r)**2
    sample.residual("역학적 에너지 보존", sample.series["0.energy"]-e0, e0, "J")
    sample.facts.update(centripetal_acceleration=w*w*r, reference_speed=abs(w)*r)
    if w != 0 and abs(w) >= 2*pi/np.finfo(float).max:
        sample.facts["reference_period"] = 2*pi/abs(w)
    if w != 0:
        linear_stability(sample, accel, method, dt)
    return sample
