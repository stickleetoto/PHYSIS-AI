"""Kinetic friction with stopping and one frictionless 1-D impact."""
import numpy as np

from .physics_common import GRAVITY, MASS, MASS_A, MASS_B, MECHANICS, V0, Sample, grid, spec, variable
from .physics_motion import kinematics


SPECS = {
    "friction": spec("friction", "미끄럼 마찰과 정지", "역학", "수평면에서 정지 거리와 마찰의 일을 측정합니다.",
        "a = −sgn(v) μg,  d = v₀²/(2μg)", ["수평면", "운동 마찰 계수 일정", "외부 수평 힘 없음", "정지한 뒤 계속 정지"],
        [MASS, V0, variable("mu", "운동 마찰 계수", "1", 0, 1.5, .01, .25), GRAVITY],
        "마찰로 잃은 운동 에너지와 이동 거리를 비교합니다."),
    "collision": spec("collision", "두 물체의 일차원 충돌", "충돌", "반발 계수가 충돌 후 속도와 운동 에너지에 미치는 영향을 측정합니다.",
        "Σp전 = Σp후,  v′B − v′A = e(vA − vB)",
        ["수평 직선 위 점질량", "외력 없음", "접촉 시간 0", "충돌 시각의 속도는 충돌 직후 값"],
        [MASS_A, MASS_B, variable("v_a", "A 처음 속도", "m/s", -10, 10, .1, 3),
         variable("v_b", "B 처음 속도", "m/s", -10, 10, .1, -.5),
         variable("gap", "처음 간격", "m", .1, 10, .1, 3),
         variable("restitution", "반발 계수", "1", 0, 1, .05, 1)],
        "두 물체의 운동량 합과 충돌 전후 운동 에너지를 비교합니다.", methods=["analytic"],
        objects=["물체 A", "물체 B"],
        measurements={k:v for k,v in MECHANICS.items() if k not in ("ax","ay","fx","fy","error")} | {"momentum":"kg·m/s"}),
}


def friction(p, method, duration, dt):
    mass, v0 = p["mass"], p["v0"]
    decel = p["mu"]*p["g"]
    a = -np.sign(v0)*decel
    # Compare velocity loss over the finite horizon before dividing, including
    # for nearly zero coefficients. No stopping event exists for uniform motion.
    stop = None
    if v0 == 0:
        stop = 0.
    elif abs(v0) <= decel*duration:
        stop = abs(v0)/decel
    t = grid(duration, dt, stop)
    moving_t = np.minimum(t, stop) if stop is not None else t
    x, vx = kinematics(moving_t, 0., v0, a, method)
    acceleration = np.full_like(t, a)
    if stop is not None:
        vx[t >= stop] = 0.
        acceleration[t >= stop] = 0.
    exact = v0*moving_t + .5*a*moving_t**2
    sample = Sample(t)
    sample.body(0, mass, x=x, vx=vx, ax=acceleration, error=np.abs(x-exact))
    sample.position_check(abs(exact[-1]))
    sample.residual("마찰의 일과 운동 에너지 변화", .5*mass*(vx**2-v0**2)-mass*a*x,
                    .5*mass*v0**2, "J")
    sample.facts["final_position"] = x[-1]
    if stop is not None:
        sample.facts.update(stop_time=stop, stop_distance=abs(x[-1]))
    else:
        sample.limitation = "관찰 중 물체가 계속 움직여 정지 거리와 시간을 측정하지 못했습니다."
    return sample


def collision(p, method, duration, dt):
    m1, m2, u1, u2, e = (p[k] for k in ("mass_a","mass_b","v_a","v_b","restitution"))
    gap, closing = p["gap"], u1-u2
    impact = gap/closing if closing*duration >= gap else None
    t = grid(duration, dt, impact)
    sample = Sample(t)
    v1, v2 = u1, u2
    if impact is not None:
        impulse = (1+e)*closing*(m1*m2/(m1+m2))
        v1, v2 = u1 - impulse/m1, u2 + impulse/m2
        sample.facts.update(collision_time=impact, impulse=impulse)
    for i, (mass, x0, u, v) in enumerate([(m1,0.,u1,v1), (m2,gap,u2,v2)]):
        velocity = np.full_like(t, u)
        x = x0 + u*t
        if impact is not None:
            after = t >= impact
            x[after] = u1*impact + v*(t[after]-impact)
            velocity[after] = v
        ke = .5*mass*velocity**2
        sample.record(i, x=x, y=0., vx=velocity, vy=0., ke=ke, pe=0., energy=ke, momentum=mass*velocity)
    momentum = sample.series["0.momentum"]+sample.series["1.momentum"]
    energy = sample.series["0.energy"]+sample.series["1.energy"]
    expected_loss = .5*m1*m2/(m1+m2)*(1-e**2)*closing**2 if impact is not None else 0.
    sample.residual("계의 총운동량 보존", momentum-momentum[0], abs(m1*u1)+abs(m2*u2), "kg·m/s", rtol=1e-10)
    sample.residual("반발 계수와 운동 에너지 손실", energy[0]-energy[-1]-expected_loss, energy[0], "J", rtol=1e-10)
    if impact is not None:
        sample.residual("충돌 직후 상대 속도", (v2-v1)-e*closing, abs(closing), "m/s", rtol=1e-10)
    else:
        sample.limitation = "선택한 속도와 관찰 시간에서는 두 물체가 만나지 않았습니다."
    energy_loss = energy[0] - energy[-1]
    if abs(energy_loss) <= 16*np.finfo(float).eps*energy[0]:
        energy_loss = 0.
    sample.facts.update(total_momentum=momentum[-1], energy_loss=energy_loss,
                        final_velocity_a=v1, final_velocity_b=v2)
    return sample
