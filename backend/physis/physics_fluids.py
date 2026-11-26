"""Equilibrium pressure, submerged-body force balance and steady volume flow."""
from .physics_common import GRAVITY, MASS, Sample, grid, spec, variable


DENSITY = variable("density", "유체 밀도", "kg/m³", 400, 1500, 10, 1000)
SPECS = {
    "hydrostatic": spec("hydrostatic", "깊이에 따른 정수압", "유체", "수면 압력과 수심으로 절대압과 게이지압을 구합니다.",
        "p = p₀ + ρgh", ["정지 유체", "일정한 밀도와 중력", "고정 깊이의 압력계"],
        [DENSITY, variable("depth", "수면 아래 깊이", "m", 0, 20, .1, 2), GRAVITY,
         variable("p0", "수면 절대압", "Pa", 0, 200000, 25, 101325)],
        "깊이를 바꾼 두 측정의 압력 차이를 비교합니다.", methods=["analytic"],
        measurements={"pressure":"Pa","gauge_pressure":"Pa","depth":"m"}, objects=["압력계"]),
    "buoyancy": spec("buoyancy", "잠긴 물체의 부력", "유체", "물체를 완전히 잠긴 채 정지시키는 데 필요한 지지력을 구합니다.",
        "Fᵦ = ρgV,  F지지 = mg − Fᵦ", ["완전히 잠긴 단단한 물체", "유체 밀도 일정", "지지대가 물체의 위치 고정", "위쪽이 양의 방향"],
        [DENSITY, variable("volume", "잠긴 부피", "m³", .0005, .01, .0001, .002), MASS, GRAVITY],
        "부력과 무게의 크기, 필요한 지지력의 방향을 비교합니다.", methods=["analytic"],
        measurements={"buoyancy":"N","weight":"N","support":"N","fy":"N","volume":"m³"}),
    "continuity": spec("continuity", "관의 단면적과 유속", "유체", "서로 다른 두 단면을 통과하는 체적 유량을 비교합니다.",
        "Q = A₁v₁ = A₂v₂", ["정상 유동", "비압축성", "분기·누출 없음", "단면 평균 유속"],
        [variable("area_in", "입구 단면적", "m²", .01, .1, .001, .04),
         variable("area_out", "출구 단면적", "m²", .01, .1, .001, .02),
         variable("speed_in", "입구 유속", "m/s", 0, 3, .1, 1)],
        "단면적이 줄어들 때 유속과 유량이 각각 어떻게 변하는지 비교합니다.", methods=["analytic"],
        measurements={"flow":"m³/s","speed":"m/s","area":"m²"}, objects=["입구","출구"]),
}


def fluid(key, p, method, duration, dt):
    sample = Sample(grid(duration, dt))
    if key == "hydrostatic":
        rho, g, depth = p["density"], p["g"], p["depth"]
        gauge = rho*g*depth
        pressure = p["p0"]+gauge
        sample.record(0, pressure=pressure, gauge_pressure=gauge, depth=depth)
        sample.facts.update(pressure=pressure, gauge_pressure=gauge)
        sample.residual("압력으로 환산한 수두", (pressure-p["p0"])/(rho*g)-depth, depth, "m", rtol=1e-10)
    elif key == "buoyancy":
        volume, rho, g = p["volume"], p["density"], p["g"]
        buoyancy, weight = rho*g*volume, p["mass"]*g
        support = weight-buoyancy
        net = buoyancy-weight+support
        sample.record(0, buoyancy=buoyancy, weight=weight, support=support, fy=net, volume=volume)
        sample.facts.update(buoyancy=buoyancy, weight=weight, support=support)
        sample.residual("지지된 물체의 수직 평형", net, weight+buoyancy, "N", rtol=1e-10)
        sample.residual("배제된 유체의 질량", buoyancy/g-rho*volume, rho*volume, "kg", rtol=1e-10)
    else:
        a1, a2, v1 = p["area_in"], p["area_out"], p["speed_in"]
        q = a1*v1
        v2 = q/a2
        sample.record(0, flow=q, speed=v1, area=a1)
        sample.record(1, flow=a2*v2, speed=v2, area=a2)
        sample.facts.update(flow=q, outlet_speed=v2)
        sample.residual("두 단면의 체적 유량", a2*v2-q, q, "m³/s", rtol=1e-10)
    return sample
