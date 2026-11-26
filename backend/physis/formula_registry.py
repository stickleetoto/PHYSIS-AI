"""Read-only teaching relations. Each right-hand side is checked against a simulation."""
from copy import deepcopy
from math import isfinite

from .physics import SPECS


from .symbolic_units import UNITS, dimension


def book(section, volume=1):
    number = ".".join(section.split("-")[:2])
    return {"title": f"OpenStax · University Physics Volume {volume}", "section": number,
            "url": f"https://openstax.org/books/university-physics-volume-{volume}/pages/{section}"}


# The displayed symbols and parser names are distinct. Each occurrence of a
# name refers to exactly one physical quantity within a record.
SYMBOLS = {
    "t": ("t","s","경과 시간"), "x": ("x","m","위치"), "y": ("y","m","높이"),
    "x0": ("x_0","m","초기 위치"), "h": ("h","m","시작 높이"), "v0": ("v_0","m/s","초기 속도"),
    "v": ("v","m/s","속도"), "a": ("a","m/s²","가속도"), "g": ("g","m/s²","중력 가속도의 크기"),
    "F": ("F","N","알짜힘의 수평 성분"), "m": ("m","kg","질량"), "mu": (r"\mu_k","1","운동 마찰 계수"),
    "d": ("d","m","정지 거리"), "m1": ("m_1","kg","물체 1 질량"), "m2": ("m_2","kg","물체 2 질량"),
    "u1": ("u_1","m/s","충돌 전 물체 1 속도"), "u2": ("u_2","m/s","충돌 전 물체 2 속도"),
    "v1": ("v_1","m/s","입구 유속"), "v2": ("v_2","m/s","출구 유속"), "e": ("e","1","반발 계수"),
    "pnet": ("p","kg·m/s","계의 총운동량"), "rel": (r"\Delta v","m/s","충돌 직후 물체 2의 물체 1에 대한 상대속도"),
    "k": ("k","N/m","용수철 상수"), "b": ("b","N·s/m","점성 감쇠 계수"), "period": ("T","s","한 주기"),
    "L": ("L","m","길이"), "theta": (r"\theta","rad","수직 아래 방향으로부터의 각변위"),
    "theta0": (r"\theta_0","rad","정지 출발 각도"), "alpha": (r"\alpha","rad/s²","각가속도"),
    "radius": ("R","m","궤도 반지름"), "omega": (r"\omega","rad/s","각속도"),
    "ac": ("a_c","m/s²","중심을 향하는 가속도의 크기"), "rho": (r"\rho","kg/m³","유체 밀도"),
    "depth": ("h","m","수면 아래 깊이"), "p0": ("p_0","Pa","수면 절대압"), "p": ("p","Pa","절대압"),
    "Fb": ("F_B","N","부력의 크기"), "V": ("V","m³","부피"), "A1": ("A_1","m²","입구 단면적"),
    "A2": ("A_2","m²","출구 단면적"), "A": ("A","m","한 진행파의 변위 진폭"),
    "f": ("f","Hz","진동수"), "lam": (r"\lambda","m","파장"), "u": ("u","m","매질의 변위"),
    "phi": (r"\phi","rad","위상차"), "n": ("n","mol","물질량"), "temp": ("T","K","절대 온도"),
    "R": ("R","J/(mol·K)","몰 기체 상수 8.31446261815324"), "Te": ("T_e","K","주변 온도"),
    "T0": ("T_0","K","물체 초기 온도"), "rate": ("k","1/s","냉각 계수"),
    "Ta": ("T_{a0}","K","물체 A 초기 온도"), "Tb": ("T_{b0}","K","물체 B 초기 온도"),
    "Ca": ("C_a","J/K","물체 A 열용량"), "Cb": ("C_b","J/K","물체 B 열용량"),
    "G": ("G","W/K","두 물체 사이 열전도도"), "gap": (r"\Delta T","K","현재 온도차 Tₐ − Tᵦ"),
    "edge": ("T_b","K","양 끝의 고정 온도"), "amp": (r"\Delta T_0","K","초기 중심 온도와 끝 온도의 차"),
    "diff": (r"\alpha","m²/s","열확산율"), "p1": ("p_1","Pa","입구 절대압"), "p2": ("p_2","Pa","출구 절대압"),
    "flowv": ("u","m/s","균일한 흐름의 축방향 유속"),
}


def record(model, title, lhs, rhs, names, latex, concepts, derivation, source, *,
           key=None, conditions=(), applicability="exact", overrides=None):
    variables = []
    for name in [lhs, *names.split()]:
        symbol, unit, description = (overrides or {}).get(name, SYMBOLS[name])
        variables.append(dict(name=name, symbol=symbol, unit=unit, dimension=dimension(unit), description=description))
    key = key or model
    return dict(formula_id=key, title=title, latex=latex, model=model, related_models=[model],
                lhs=lhs, expression=rhs, variables=variables, conditions=[*SPECS[model].assumptions, *conditions],
                applicability=applicability, concepts=concepts.split(), derivation=derivation, source=source,
                test=f"backend/tests/test_formula_registry.py::test_registered_relation_against_engine[{key}]",
                review_status="source_and_engine_checked")


phase = "2*pi*(x/lam-f*t)"
wave_tex = r"2\pi(x/\lambda-ft)"
wave_ref = book("16-2-mathematics-of-waves")
pendulum_ref = book("15-4-pendulums")
heat_ref = book("1-4-heat-transfer-specific-heat-and-calorimetry", 2)

RECORDS = [
    record("free_fall","정지 출발 자유낙하의 높이","y","h-g*t**2/2","h g t",
           r"y=h-\tfrac12gt^2","위치 가속도 중력","위쪽을 양으로 잡고 수직 가속도 −g를 두 번 적분한 뒤 초기 속도 0과 높이 h를 대입합니다.",
           book("3-5-free-fall"), conditions=["0 ≤ t ≤ √(2h/g), h > 0, g > 0"]),
    record("uniform","등속 운동의 위치","x","x0+v0*t","x0 v0 t",r"x=x_0+v_0t","위치 속도 변위",
           "일정한 속도에 경과 시간을 곱한 변위를 초기 위치에 더합니다.",book("3-1-position-displacement-and-average-velocity")),
    record("acceleration","등가속도 운동의 위치","x","x0+v0*t+a*t**2/2","x0 v0 a t",r"x=x_0+v_0t+\tfrac12at^2",
           "위치 속도 가속도","시간에 대해 a를 적분해 v₀+at를 얻고 다시 적분해 위치를 구합니다.",book("3-4-motion-with-constant-acceleration")),
    record("newton","뉴턴 제2법칙","a","F/m","F m",r"a=\frac{F}{m}","힘 질량 가속도 운동량",
           "관성계에서 알짜힘은 운동량의 시간 변화율입니다. 질량이 일정하면 F = ma이므로 양변을 질량으로 나눕니다.",
           book("5-3-newtons-second-law"),conditions=["관성계, 일정한 양의 질량"]),
    record("friction","운동 마찰에 의한 정지 거리","d","v0**2/(2*mu*g)","v0 mu g",
           r"d=\frac{v_0^2}{2\mu_k g}","힘 에너지 속도","마찰력이 한 일 −μₖmgd를 운동 에너지 변화 −mv₀²/2와 같게 두어 질량을 약분합니다.",
           book("6-2-friction"),conditions=["μₖ > 0, g > 0. 이동 거리이므로 속도 방향과 무관합니다."]),
    record("collision","일차원 충돌의 총운동량","pnet","m1*u1+m2*u2","m1 u1 m2 u2",r"p=m_1u_1+m_2u_2",
           "운동량 질량 속도","두 물체의 운동량을 더합니다. 계가 받는 외부 충격량이 0이면 이 합은 충돌 전후에 같습니다.",book("9-3-conservation-of-linear-momentum")),
    record("collision","충돌 후 상대속도와 반발 계수","rel","e*(u1-u2)","e u1 u2",r"\Delta v=e(u_1-u_2)",
           "운동량 속도 충돌","반발 계수의 정의인 분리 속력/접근 속력을 충돌 직후 상대속도에 대해 정리합니다.",
           {"title":"University of Alabama · P. LeClair, Coefficient of Restitution",
            "section":"§1, Eq. (1), p. 1","url":"https://pleclair.ua.edu/ph105/Labs/coef_rest_lab.pdf"},
           key="collision_restitution",conditions=["물체 1이 뒤에서 접근하고 실제 충돌이 일어남, 0 ≤ e ≤ 1"]),
    record("spring","선형 용수철의 주기","period","2*pi*sqrt(m/k)","m k",r"T=2\pi\sqrt{m/k}",
           "진동 힘 질량","mẍ = −kx에 코사인 해를 대입하면 각진동수의 제곱은 k/m입니다. 한 주기 위상 변화는 2π입니다.",
           book("15-1-simple-harmonic-motion"),conditions=["m, k > 0. 정지 평형점에서는 주기를 관측할 수 없습니다."]),
    record("damped","선형 감쇠 진동의 가속도","a","-(k*x+b*v)/m","k x b v m",r"a=-\frac{kx+bv}{m}",
           "진동 힘 가속도 에너지","복원력 −kx와 점성 저항 −bv의 합을 질량으로 나눕니다.",book("15-5-damped-oscillations"),
           overrides={"x":("x","m","평형점에서의 변위")}),
    record("pendulum","정지 출발 진자의 유한 진폭 주기","period","4*sqrt(L/g)*elliptic_k(sin(theta0/2)**2)","L g theta0",
           r"T=4\sqrt{L/g}\,K\!\left(\sin^2(\theta_0/2)\right)","중력 진동 에너지",
           "에너지 보존식에서 각속도를 구해 최저점부터 되돌이점까지 걸리는 시간을 적분하고 4배 합니다. K(m)의 인자 m은 모듈러스의 제곱입니다.",
           {"title":"Carvalhaes & Suppes · American Journal of Physics 76 (2008)", "section":"II, pp. 1150–1151",
            "url":"https://suppescorpus.stanford.edu/sites/g/files/sbiybj32751/files/media/file/approximations_for_the_period_of_the_simple_pendulum_based_on_the_arithmetic-geometric_mean_431.pdf"},
           conditions=["0 < |θ₀| < π rad, L > 0, g > 0. θ₀ = 0에서는 실제 진동이 없습니다."]),
    record("pendulum","단진자의 소각도 근사 주기","period","2*pi*sqrt(L/g)","L g theta0",r"T\approx 2\pi\sqrt{\frac Lg}",
           "중력 진동 근사","라디안으로 작은 각도에서 sin θ ≈ θ를 적용하면 각진동수 √(g/L)의 선형 방정식이 됩니다.",
           pendulum_ref,key="pendulum_small_angle",applicability="approximation",
           conditions=["소각도 |θ₀| ≪ 1 rad. 이 도구는 0 < |θ₀| ≤ 0.20 rad를 사용하며 이 범위에서 유한 진폭 주기 대비 오차는 0.26% 미만입니다."]),
    record("pendulum","단진자의 비선형 각가속도","alpha","-g*sin(theta)/L","g theta L",r"\alpha=-\frac{g}{L}\sin\theta",
           "중력 진동 가속도","접선 방향의 중력 −mg sin θ를 mLα와 같게 두면 m이 약분됩니다.",pendulum_ref,key="pendulum_equation"),
    record("circular","등속 원운동의 구심 가속도","ac","omega**2*radius","omega radius",r"a_c=\omega^2R",
           "가속도 힘 속도","반지름이 고정된 원운동에서 가속도는 중심 쪽이고 크기는 v²/R입니다. 속력 |ω|R을 대입합니다.",book("6-3-centripetal-force")),
    record("hydrostatic","정지 유체의 절대압","p","p0+rho*g*depth","p0 rho g depth",r"p=p_0+\rho gh",
           "압력 밀도 중력","압력 차에 단면적을 곱한 힘은 같은 단면의 유체 기둥 무게와 같습니다. 단면적을 약분한 뒤 수면 압력을 더합니다.",book("14-1-fluids-density-and-pressure")),
    record("buoyancy","잠긴 물체의 부력","Fb","rho*g*V","rho g V",r"F_B=\rho gV","힘 밀도 중력 유체",
           "물체가 밀어낸 유체의 질량 ρV에 g를 곱하면 위로 작용하는 부력의 크기를 얻습니다.",book("14-4-archimedes-principle-and-buoyancy"),
           overrides={"V":("V","m³","배제한 유체의 부피")}),
    record("continuity","연속 방정식의 출구 유속","v2","A1*v1/A2","A1 v1 A2",r"v_2=A_1v_1/A_2",
           "속도 유체 질량","질량 보존과 일정한 밀도로부터 두 단면의 체적 유량이 같습니다. A₁v₁ = A₂v₂를 출구 유속에 대해 풉니다.",
           book("14-5-fluid-dynamics"),conditions=["A₁, A₂ > 0"]),
    record("wave_transverse","진행 횡파의 입자 변위","u",f"A*sin({phase})","A x lam f t",rf"u=A\sin\!\left({wave_tex}\right)",
           "파동 진동 변위","위상은 파장마다 2π 증가하고 한 지점에서 주기마다 2π 감소합니다. 위상의 사인에 진폭을 곱합니다.",wave_ref),
    record("wave_longitudinal","진행 종파의 입자 변위","u",f"A*sin({phase})","A x lam f t",rf"u=A\sin\!\left({wave_tex}\right)",
           "파동 진동 변위 밀도","평형 좌표 x에서 입자가 진행 방향으로 움직인 거리를 사인 모드로 씁니다. 압력과 변위는 다른 관측량입니다.",book("16-1-traveling-waves")),
    record("wave_superposition","같은 방향 진행파의 중첩","u",f"A*(sin({phase})+sin({phase}+phi))","A x lam f t phi",
           rf"u=A\sin\!\left({wave_tex}\right)+A\sin\!\left({wave_tex}+\phi\right)",
           "파동 중첩 변위","선형 매질에서 같은 점과 시각의 두 변위를 부호까지 더합니다.",book("16-5-interference-of-waves")),
    record("wave_standing","정상파의 변위","u","2*A*sin(2*pi*x/lam)*cos(2*pi*f*t)","A x lam f t",
           r"u=2A\sin(2\pi x/\lambda)\cos(2\pi ft)","파동 중첩 진동","반대 방향 두 진행파의 사인을 합차 공식으로 정리해 위치와 시간에 의존하는 인자로 나눕니다.",book("16-6-standing-waves-and-resonance")),
    record("ideal_gas","이상기체의 절대압","p","n*R*temp/V","n R temp V",r"p=nRT/V","압력 온도",
           "몰 수를 사용한 상태 방정식 pV = nRT를 압력에 대해 풉니다. 온도는 켈빈입니다.",book("2-1-molecular-model-of-an-ideal-gas",2),conditions=["V, T, n > 0"]),
    record("heat_equilibrium","단열된 두 물체의 평형 온도","temp","(Ca*Ta+Cb*Tb)/(Ca+Cb)","Ca Ta Cb Tb",
           r"T_\mathrm{eq}=\frac{C_aT_{a0}+C_bT_{b0}}{C_a+C_b}","열 온도 에너지",
           "두 물체가 주고받은 열 Ca(T−Ta₀)와 Cb(T−Tb₀)의 합이 0인 온도를 구합니다. 실험의 유한 시간 마지막 값과 평형 극한은 구분됩니다.",heat_ref),
    record("heat_equilibrium","접촉 열교환 중의 온도차","gap","(Ta-Tb)*exp(-G*(1/Ca+1/Cb)*t)","Ta Tb G Ca Cb t",
           r"\Delta T=(T_{a0}-T_{b0})e^{-G(1/C_a+1/C_b)t}","열 온도 에너지",
           "모델의 선형 열전달률 G(Tₐ−Tᵦ)를 두 에너지 수지에 반대 부호로 넣습니다. 두 온도 변화율의 차를 적분하면 온도차가 지수적으로 줄어듭니다.",
           book("1-6-mechanisms-of-heat-transfer",2),key="heat_exchange",conditions=["접촉 열류가 온도차에 비례하는 집중 열용량 모형"]),
    record("cooling","뉴턴 냉각 법칙의 온도","temp","Te+(T0-Te)*exp(-rate*t)","Te T0 rate t",
           r"T=T_e+(T_0-T_e)e^{-kt}","열 온도","온도차의 시간 변화율이 온도차에 비례하는 방정식을 풀어 초기 온도차를 곱합니다.",
           {"title":"OpenStax · Calculus Volume 1","section":"6.8, Newton’s Law of Cooling",
            "url":"https://openstax.org/books/calculus-volume-1/pages/6-8-exponential-growth-and-decay"}),
    record("heat_diffusion","막대의 열확산 단일 모드","temp","edge+amp*sin(pi*x/L)*exp(-diff*pi**2*t/L**2)",
           "edge amp x L diff t",r"T=T_b+\Delta T_0\sin(\pi x/L)e^{-\alpha\pi^2t/L^2}","열 온도",
           "양 끝에서 0인 첫 사인 모드를 열방정식에 대입하면 진폭의 감소율은 απ²/L²입니다. 경계 온도를 더해 절대 온도를 복원합니다.",
           {"title":"MIT OpenCourseWare · 18.03 The Heat Equation","section":"§5.2, limit of discrete modal solutions",
            "url":"https://ocw.mit.edu/courses/es-1803-differential-equations-spring-2024/mites_1803_s24_heat_equation.pdf"},
           conditions=["0 ≤ x ≤ L, t ≥ 0"]),
    record("bernoulli","수평 유선의 출구 정압","p2","p1+rho*(v1**2-v2**2)/2","p1 rho v1 v2",
           r"p_2=p_1+\tfrac12\rho(v_1^2-v_2^2)","압력 에너지 밀도 유체",
           "같은 유선 위에서 정압과 동압의 합이 일정합니다. 높이가 같아 중력 위치 항이 약분됩니다.",book("14-6-bernoullis-equation")),
    record("fluid_tracer","균일 유동을 따르는 입자의 위치","x","x0+flowv*t","x0 flowv t",r"x=x_0+ut","위치 속도 유체",
           "표지 입자의 속도를 유체 속도와 같게 두고 일정한 축방향 속도를 적분합니다.",book("14-5-fluid-dynamics")),
]

_BY_ID = {r["formula_id"]: r for r in RECORDS}


def formula_by_id(formula_id):
    return deepcopy(_BY_ID.get(formula_id))


def formulas_for(model):
    return [deepcopy(r) for r in RECORDS if r["model"] == model]


def formula_for(model):
    return formula_by_id(model)


def search_formulas(query="", model=None):
    terms = query.strip().casefold().split()
    records = []
    for r in RECORDS:
        if model is not None and model != r["model"]:
            continue
        fields = [r["formula_id"], r["title"], r["latex"], r["expression"], *r["concepts"],
                  *r["conditions"], *(v["name"]+" "+v["description"] for v in r["variables"])]
        searchable = " ".join(fields).casefold()
        if all(term in searchable for term in terms):
            records.append(deepcopy(r))
    return records


def verify_registered_formula(formula_id, model, values, units=None):
    """Check the selected relation inside an engine-defined model and its parameter bounds.

    The caller supplies the complete engine parameter dictionary. Qualitative
    assumptions describe the idealized engine, not observations of a real setup.
    """
    r = _BY_ID.get(formula_id)
    if not r or r["model"] != model:
        return {"status":"failed","detail":"해당 모델에 등록된 공식 ID와 일치하지 않습니다."}
    spec = SPECS[model]
    if not isinstance(values, dict) or set(values) != {v.key for v in spec.variables}:
        return {"status":"unverifiable","detail":"실험의 전체 SI 매개변수가 필요합니다."}
    if any(type(values[v.key]) not in (int,float) or not v.min <= values[v.key] <= v.max
           or not isfinite(values[v.key]) for v in spec.variables):
        return {"status":"failed","detail":"물리 엔진이 지원하는 매개변수 범위를 벗어났습니다."}
    if units is not None and units != {v["name"]:v["unit"] for v in r["variables"]}:
        return {"status":"failed","detail":"공식 변수와 SI 단위가 등록된 명세와 다릅니다."}
    if ((formula_id == "pendulum_small_angle" and not 0 < abs(values["angle"]) <= .2)
        or (formula_id == "pendulum" and values["angle"] == 0)
        or (formula_id == "collision_restitution" and values["v_a"] <= values["v_b"])
        or (formula_id == "friction" and values["mu"] <= 0)
        or (formula_id == "spring" and values["x0"] == values["v0"] == 0)):
        return {"status":"failed","detail":"현재 실험값이 이 공식의 적용 조건을 벗어났습니다."}
    return {"status":"verified","detail":"등록 모델의 SI 매개변수와 공식 적용 조건을 확인했습니다."}


def check_applicability(formula_id, experiment):
    from .physics import parse_dsl
    try:
        payload = experiment if isinstance(experiment, dict) else experiment.model_dump()
        exp = parse_dsl(payload)
    except (TypeError, ValueError, AttributeError):
        return {"status":"unverifiable", "reason":"등록된 엔진 명세를 가진 실험이 필요합니다."}
    result = verify_registered_formula(formula_id, exp.model, exp.values)
    if result["status"] != "verified":
        status = "outside_conditions" if result["status"] == "failed" else "unverifiable"
        return {"status":status, "reason":result["detail"]}
    p = exp.values
    if formula_id == "collision_restitution" and (p["v_a"]-p["v_b"])*exp.duration < p["gap"]:
        return {"status":"outside_conditions", "reason":"관찰 시간 안에 두 물체가 만나지 않습니다."}
    detail = result["detail"]
    if formula_id == "pendulum_small_angle":
        detail = "소각도 근사 허용 범위 0 < |θ₀| ≤ 0.20 rad에서 유한 진폭 주기와의 차이가 0.26% 미만입니다."
    return {"status":"applicable", "reason":detail}
