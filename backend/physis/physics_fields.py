"""Analytic classroom fields. Spatial views use these sampled mode amplitudes."""
from math import pi

import numpy as np

from .physics_common import Sample, grid, spec, variable
from .physics_fluids import DENSITY

R = 8.31446261815324  # exact SI product N_A k_B, J/(mol K)
AMPLITUDE = variable("amplitude", "파동 진폭", "m", .001, .04, .001, .03)
FREQUENCY = variable("frequency", "진동수", "Hz", .1, 3, .1, 1)
WAVELENGTH = variable("wavelength", "파장", "m", .5, 5, .05, 1)
PHASE = variable("phase", "두 파동의 위상차", "rad", -pi, pi, .05, pi/2)
TA = variable("temp_a", "물체 A 초기 온도", "K", 240, 400, 1, 350)
TB = variable("temp_b", "물체 B 초기 온도", "K", 240, 400, 1, 290)
BASE = variable("ambient", "주변 온도", "K", 250, 350, 1, 290)
PIPE = [variable("area_in", "입구 단면적", "m²", .02, .06, .001, .04),
        variable("area_out", "출구 단면적", "m²", .02, .06, .001, .02),
        variable("speed_in", "입구 유속", "m/s", 0, 2, .1, 1)]


def analytic(key, title, category, goal, formula, assumptions, variables, comparison, measurements, objects):
    return spec(key, title, category, goal, formula, assumptions, variables, comparison,
                methods=["analytic"], measurements=measurements, objects=objects)


def wave_spec(key, title, goal, formula, constraint, extra=()):
    return analytic(key, title, "파동", goal, formula, ["균일한 선형 매질", "분산·감쇠 없음", constraint],
                    [AMPLITUDE, FREQUENCY, WAVELENGTH, *extra],
                    "같은 매질 입자의 변위와 파형이 이동하는 방향을 구별합니다.",
                    {"displacement":"m", "quarter_displacement":"m"}, ["관측점"])


SPECS = {s.model:s for s in [
    wave_spec("wave_transverse", "진행하는 사인 횡파", "매질의 수직 변위와 파형의 전파를 관찰합니다.",
              "u = A sin(kx − ωt), c = fλ", "변위는 진행 방향에 수직"),
    wave_spec("wave_longitudinal", "압축과 팽창의 종파", "매질 입자가 앞뒤로 진동할 때 생기는 밀집 구간을 관찰합니다.",
              "ξ = A sin(kx − ωt), c = fλ", "변위는 진행 방향과 평행, 입자 교차 없음"),
    wave_spec("wave_superposition", "두 사인파의 중첩", "같은 방향으로 진행하는 두 파동의 위상차를 바꿉니다.",
              "u = A sin(kx − ωt) + A sin(kx − ωt + φ)", "같은 진폭·파장·진동수·진행 방향", [PHASE]),
    wave_spec("wave_standing", "마디와 배가 있는 정상파", "서로 반대로 진행하는 두 파동의 마디와 배를 관찰합니다.",
              "u = 2A sin(kx) cos(ωt)", "크기가 같고 반대 방향인 두 진행파"),
    analytic("ideal_gas", "이상기체의 상태 방정식", "열", "온도·부피·몰수를 바꾸고 평형 압력을 읽습니다.",
             "pV = nRT", ["기체가 열평형에 도달", "분자 부피·상호작용 무시", "상태량 고정"],
             [variable("moles","물질량","mol",.1,2,.1,1),variable("temperature","기체 온도","K",250,400,1,300),
              variable("volume","기체 부피","m³",.01,.1,.001,.025)], "부피를 두 배로 바꾸고 압력을 비교합니다.",
             {"pressure":"Pa","temperature":"K","volume":"m³"}, ["기체"]),
    analytic("heat_equilibrium", "두 물체의 열평형", "열", "접촉한 두 물체의 온도차가 줄어드는 과정을 관찰합니다.",
             "C₁Ṫ₁ = −G(T₁−T₂), C₂Ṫ₂ = G(T₁−T₂)", ["외부와 단열", "각 물체 내부 온도 균일",
              "열용량·접촉 열전도도 일정", "상변화 없음"], [TA,TB,variable("capacity_a","물체 A 열용량","J/K",1,100,1,12),
              variable("capacity_b","물체 B 열용량","J/K",1,100,1,24),
              variable("conductance","접촉 열전도도","W/K",.1,20,.1,5)],
             "각 물체의 온도 변화와 교환한 열의 합을 비교합니다.", {"temperature":"K","heat":"J"}, ["물체 A","물체 B"]),
    analytic("cooling","뉴턴의 냉각 법칙","열","물체와 주변의 온도차가 지수적으로 변하는 과정을 측정합니다.",
             "T = Tₑ + (T₀−Tₑ) exp(−kt)",["주변 온도 일정", "물체 내부 온도 균일","열전달 계수·열용량 일정"],
             [variable("initial_temp","물체 초기 온도","K",230,420,1,360),BASE,
              variable("rate","냉각 계수","1/s",.05,2,.05,.5)],"초기 온도가 주변보다 낮을 때도 시험합니다.",
             {"temperature":"K","temperature_rate":"K/s"},["물체"]),
    analytic("heat_diffusion","막대의 일차원 열확산","열","양 끝 온도가 일정할 때 내부의 온도 분포를 관찰합니다.",
             "T = Tᵦ + ΔT sin(πx/L) exp(−απ²t/L²)",["균일한 가느다란 막대", "양 끝은 같은 고정 온도",
             "초기 온도는 단일 사인 모드","일정한 열확산율, 내부 열원 없음"],
             [variable("length","막대 길이","m",.1,1,.01,.2),variable("diffusivity","열확산율","m²/s",.00001,.002,.00001,.001),
              variable("boundary_temp","양 끝 온도","K",250,350,1,290),variable("excess","초기 중심 온도차","K",0,70,1,50)],
             "길이와 열확산율을 바꾸어 중심 온도가 내려가는 속도를 비교합니다.",
             {"temperature":"K","edge_temperature":"K"},["막대 중심"]),
    analytic("bernoulli","수평 관의 베르누이 원리","유체","단면적이 변하는 관에서 유속과 정압을 비교합니다.",
             "A₁v₁ = A₂v₂, p₁ + ρv₁²/2 = p₂ + ρv₂²/2", ["정상·비압축성·비점성 흐름", "수평 유선", "손실·펌프 없음"],
             [DENSITY,*PIPE,variable("inlet_pressure","입구 절대압","Pa",80000,200000,100,101325)],
             "각 단면의 정압과 동압을 합쳐 비교합니다.", {"pressure":"Pa","speed":"m/s","flow":"m³/s"},["입구","출구"]),
    analytic("fluid_tracer","균일한 흐름의 추적 입자","유체","직선 관에서 표지 입자가 유속을 따라 이동하는 거리를 관찰합니다.",
             "dx/dt = u, x = x₀ + ut",["단면과 축방향 유속 일정", "질량·크기 없는 추적자", "점성·난류·확산 없음"],
             [variable("speed","축방향 유속","m/s",0,2,.05,.4),variable("x0","추적자 시작 위치","m",0,2,.05,.2)],
             "같은 시간 동안 이동한 거리와 유속의 비례 관계를 확인합니다.",
             {"x":"m","speed":"m/s"},["표지 입자"]),
]}


def field_sample(key, p, method, duration, dt):
    t = grid(duration, dt)
    s = Sample(t)
    if key.startswith("wave_"):
        a, f, length = p["amplitude"], p["frequency"], p["wavelength"]
        w = 2*pi*f*t
        # Displacements at x=0 and λ/4 determine the entire single spatial harmonic.
        origin, quarter = -a*np.sin(w), a*np.cos(w)
        if key == "wave_superposition":
            origin = origin + a*np.sin(p["phase"]-w)
            quarter = quarter + a*np.cos(p["phase"]-w)
            envelope = 2*a*abs(np.cos(p["phase"]/2))
        elif key == "wave_standing":
            origin, quarter = np.zeros_like(t), 2*quarter
            s.residual("원점 마디",origin,2*a,"m",rtol=1e-10)
            envelope = None
        else:
            envelope = a
        if envelope is not None:
            s.residual("공간 모드 진폭",np.hypot(origin,quarter)-envelope,a,"m",rtol=1e-10)
        else:
            s.residual("배와 두 진행파의 합",quarter-(a*np.sin(pi/2-w)+a*np.sin(pi/2+w)),2*a,"m",rtol=1e-10)
        s.record(0, displacement=origin, quarter_displacement=quarter)
        s.facts.update(wave_speed=f*length, wave_period=1/f)
        if 2*f*dt >= 1:
            s.limitation = "한 주기당 시간 표본이 두 개 이하입니다. 진행 방향이나 진동을 판독하려면 시간 간격을 줄이세요."
    elif key == "ideal_gas":
        pressure = p["moles"]*R*p["temperature"]/p["volume"]
        s.record(0,pressure=pressure,temperature=p["temperature"],volume=p["volume"])
        s.facts["pressure"] = pressure
        s.residual("상태식으로 복원한 절대온도",pressure*p["volume"]/(p["moles"]*R)-p["temperature"],p["temperature"],"K",rtol=1e-10)
    elif key == "heat_equilibrium":
        a,b = p["capacity_a"],p["capacity_b"]
        t1,t2 = p["temp_a"],p["temp_b"]
        eq = (a*t1+b*t2)/(a+b)
        gap = (t1-t2)*np.exp(-p["conductance"]*(1/a+1/b)*t)
        first,second = eq+b/(a+b)*gap,eq-a/(a+b)*gap
        for i,(temp,initial,capacity) in enumerate([(first,t1,a),(second,t2,b)]):
            s.record(i,temperature=temp,heat=capacity*(temp-initial))
        s.facts.update(equilibrium_temp=eq, final_temp=first[-1])
        s.residual("두 물체의 열 교환 합",s.series["0.heat"]+s.series["1.heat"],max(a,b)*abs(t1-t2),"J",rtol=1e-10)
    elif key == "cooling":
        ambient,k = p["ambient"],p["rate"]
        delta = (p["initial_temp"]-ambient)*np.exp(-k*t)
        s.record(0,temperature=ambient+delta,temperature_rate=-k*delta)
        s.facts["final_temp"] = ambient+delta[-1]
        s.residual("반감기 전이",delta[1:]-delta[:-1]*np.power(.5,k*np.diff(t)/np.log(2)),abs(delta[0]),"K",rtol=1e-10)
    elif key == "heat_diffusion":
        rate = p["diffusivity"]*(pi/p["length"])**2
        delta = p["excess"]*np.exp(-rate*t)
        center = p["boundary_temp"]+delta
        s.record(0,temperature=center,edge_temperature=p["boundary_temp"])
        s.facts.update(final_temp=center[-1], diffusion_time=1/rate)
        s.residual("초기 중심 온도차",delta[0]-p["excess"],p["excess"],"K",rtol=1e-10)
        s.residual("단일 모드의 온도차 전이",np.diff(delta)-delta[:-1]*np.expm1(-rate*np.diff(t)),p["excess"],"K",rtol=1e-10)
    elif key == "bernoulli":
        rho, inlet, v1 = p["density"],p["inlet_pressure"],p["speed_in"]
        flow = p["area_in"]*v1
        v2 = flow/p["area_out"]
        outlet = inlet + .5*rho*(v1**2-v2**2)
        for i,(v,pressure,area) in enumerate([(v1,inlet,p["area_in"]),(v2,outlet,p["area_out"])]):
            s.record(i,pressure=pressure,speed=v,flow=area*v)
        s.facts.update(outlet_pressure=outlet,outlet_speed=v2,flow=flow)
        s.residual("두 단면의 총압",inlet+.5*rho*v1*v1-outlet-.5*rho*v2*v2,inlet,"Pa",rtol=1e-10)
        s.residual("체적 유량 보존",v2*p["area_out"]-flow,flow,"m³/s",rtol=1e-10)
    elif key == "fluid_tracer":
        x = p["x0"]+p["speed"]*t
        s.record(0,x=x,speed=p["speed"])
        s.facts["final_position"] = x[-1]
        s.residual("입자 이동 거리",np.diff(x)-p["speed"]*np.diff(t),abs(x[-1]-x[0]),"m",rtol=1e-10)
    else:
        raise ValueError("등록되지 않은 장 모델입니다.")
    return s
