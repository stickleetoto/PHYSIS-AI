"""Reviewed classroom sequence; visits never create progress or change the official graph."""

# id, title, prerequisites, linked physics models, searchable reading topic, misconception
NODES = {
    "units": ("단위와 차원", [], [], "unit conversion dimensions", "수치가 같아도 단위가 다르면 같은 물리량이 아닙니다."),
    "equations": ("방정식", ["units"], [], "equation units", "양변에 같은 연산을 해도 0으로 나누면 동치가 깨집니다."),
    "graphs": ("함수와 그래프", ["equations"], ["uniform"], "position time graph", "위치 그래프의 높이와 기울기는 다른 물리량입니다."),
    "trig": ("삼각함수", ["graphs"], ["pendulum"], "trigonometric functions angle", "호도법과 도 단위를 구분해야 합니다."),
    "vectors": ("벡터", ["units"], ["newton"], "scalars vectors direction", "크기가 같은 두 벡터도 방향이 다를 수 있습니다."),
    "calculus": ("미분과 적분 입문", ["graphs"], ["acceleration"], "instantaneous velocity derivative", "평균 변화율과 순간 변화율은 일반적으로 다릅니다."),
    "position": ("위치", ["units"], ["uniform"], "position coordinates", "위치의 원점은 좌표계를 선택할 때 정합니다."),
    "displacement": ("변위", ["position","vectors"], ["uniform"], "displacement distance", "왕복 경로의 이동 거리가 양수여도 변위는 0일 수 있습니다."),
    "velocity": ("속도", ["displacement","graphs"], ["uniform","acceleration"], "average velocity", "속도에는 방향이 있습니다."),
    "acceleration": ("가속도", ["velocity"], ["acceleration","free_fall"], "acceleration change velocity", "속력만 일정해도 방향이 바뀌면 가속도가 생깁니다."),
    "mass": ("질량", ["units"], ["newton","free_fall"], "mass inertia", "질량은 무게와 단위가 다릅니다."),
    "force": ("힘과 뉴턴 법칙", ["mass","acceleration"], ["newton","friction"], "Newton second law net force", "여러 힘이 작용할 때 가속도를 정하는 것은 알짜힘입니다."),
    "gravity": ("중력", ["force"], ["free_fall"], "gravity free fall", "진공에서 같은 위치의 두 물체는 질량과 관계없이 같은 중력 가속도를 받습니다."),
    "momentum": ("운동량", ["mass","velocity"], ["collision"], "conservation momentum", "비탄성 충돌에서도 외부 충격량이 없으면 계 전체 운동량이 보존됩니다."),
    "energy": ("에너지", ["force","displacement"], ["spring","friction"], "work kinetic energy", "운동 에너지의 보존 여부는 계와 상호작용에 따라 달라집니다."),
    "rotation": ("회전 운동 기초", ["acceleration","vectors"], ["circular"], "centripetal acceleration", "등속 원운동에서도 속도의 방향이 변합니다."),
    "oscillation": ("단순 조화 운동", ["energy","trig"], ["spring"], "simple harmonic motion", "선형 용수철의 주기는 진폭에 비례하지 않습니다."),
    "pendulum": ("진자", ["oscillation","gravity"], ["pendulum"], "simple pendulum small angles", "작은 각도 주기식을 큰 진폭에 그대로 적용하면 오차가 생깁니다."),
    "damping": ("감쇠", ["oscillation"], ["damped"], "damped oscillations", "감쇠하는 계의 역학적 에너지는 줄어들 수 있습니다."),
    "waves": ("파동", ["oscillation"], ["wave_transverse","wave_longitudinal"], "transverse longitudinal wave", "파형의 진행과 매질 입자 자체의 이동은 구분합니다."),
    "superposition": ("중첩과 정상파", ["waves"], ["wave_superposition","wave_standing"], "superposition standing waves", "서로 반대 위상인 변위는 상쇄될 수 있습니다."),
    "temperature": ("온도", ["units"], ["ideal_gas","heat_equilibrium"], "temperature thermal equilibrium", "온도와 에너지 전달량은 다른 물리량입니다."),
    "heat": ("열", ["temperature","energy"], ["heat_equilibrium"], "heat transfer temperature", "열은 온도 차이에 의해 전달되는 에너지입니다."),
    "gas": ("이상기체", ["temperature"], ["ideal_gas"], "ideal gas absolute temperature", "이상기체식의 온도에는 절대온도를 사용합니다."),
    "transfer": ("열전달", ["heat","calculus"], ["cooling","heat_diffusion"], "heat conduction", "평형에서도 물체마다 내부 에너지는 다를 수 있습니다."),
    "density": ("밀도", ["mass","units"], ["hydrostatic"], "density mass volume", "물질이 균일하면 시료 크기를 바꿔도 밀도가 같습니다."),
    "fluids": ("유체와 모델 가정", ["density"], ["fluid_tracer","bernoulli"], "fluid ideal steady flow", "이상 유동의 결과를 마찰 손실이 큰 실제 관에 그대로 적용할 수 없습니다."),
    "pressure": ("압력", ["force","density"], ["hydrostatic"], "pressure depth", "정수압은 용기 모양보다 깊이와 밀도에 좌우됩니다."),
    "buoyancy": ("부력", ["pressure"], ["buoyancy"], "Archimedes buoyant force", "주어진 유체에서 부력은 밀어낸 유체의 부피에 의존합니다."),
    "continuity": ("연속 방정식", ["fluids","velocity"], ["continuity","bernoulli"], "fluid continuity volume flow", "정상 비압축 흐름에서 단면이 좁아져도 체적 유량은 같습니다."),
    "integration": ("수치적분", ["calculus","oscillation"], ["spring"], "numerical integration oscillator", "한 스텝이 작아도 이산 계산의 오차가 정확히 0이 되는 것은 아닙니다."),
    "error": ("계산 오차", ["integration"], ["spring"], "numerical error reference", "기준해와의 차이와 실제 장치에서 생기는 모델 오차는 다릅니다."),
    "convergence": ("수렴성", ["error"], ["spring"], "time step convergence", "한 개의 시간 간격만으로 수렴 차수를 측정할 수 없습니다."),
    "validation": ("모델 검증", ["convergence"], ["spring","pendulum"], "validation reference model", "단위 일치만으로 공식이나 설명 전체의 정확성을 보장할 수 없습니다."),
    "comparison": ("실험 데이터 비교", ["validation"], ["spring","free_fall"], "comparison measurements", "서로 다른 단위의 시계열은 수치만으로 직접 비교할 수 없습니다."),
}
STAGES = [
    ("수학 기초", ["units","equations","graphs","trig","vectors","calculus"]),
    ("고전역학", ["position","displacement","velocity","acceleration","mass","force","gravity","momentum","energy","rotation"]),
    ("진동과 파동", ["oscillation","pendulum","damping","waves","superposition"]),
    ("열역학", ["temperature","heat","gas","transfer"]),
    ("유체역학 기초", ["density","fluids","pressure","buoyancy","continuity"]),
    ("계산 물리", ["integration","error","convergence","validation","comparison"]),
]
RELATED = [("velocity","momentum"),("energy","heat"),("pressure","gas"),("pendulum","waves"),
           ("mass","density"),("error","graphs"),("fluids","heat"),("gravity","buoyancy")]

# An answer submitted for a checkpoint is the only action that marks that checkpoint as passed.
QUIZZES = {
 "units":("다음 중 길이와 같은 차원을 가진 식은?",["속도 × 시간","힘 × 시간","질량 × 가속도"],0,"(m/s) × s = m입니다."),
 "graphs":("위치–시간 그래프의 한 점에서 접선의 기울기는?",["위치","순간 속도","경과 시간"],1,"위치의 시간 변화율이 속도입니다."),
 "vectors":("두 속도 벡터가 같으려면 무엇이 같아야 할까요?",["크기만","방향만","크기와 방향"],2,"벡터의 일치는 크기와 방향을 모두 요구합니다."),
 "force":("질량 2 kg인 수레에 알짜힘 6 N이 작용하면 가속도는?",["12 m/s²","3 m/s²","8 m/s²"],1,"a = F/m = 6/2 = 3 m/s²입니다."),
 "momentum":("외부 충격량이 0인 충돌에서 항상 보존되는 양은?",["계 전체의 운동량","각 물체의 운동량","각 물체의 운동 에너지"],0,"두 물체 사이의 내부 충격량은 합하면 0입니다."),
 "pendulum":("이상적인 진자에서 T ≈ 2π√(L/g)를 쓸 수 있는 조건은?",["모든 각도","큰 감쇠","작은 진폭각"],2,"라디안에서 sin θ ≈ θ인 범위의 근사입니다."),
 "waves":("횡파의 매질 입자는 파동의 진행 방향에 대해 어떻게 진동하나요?",["수직","항상 평행","진동하지 않음"],0,"횡파의 변위 방향은 진행 방향에 수직입니다."),
 "heat":("두 물체가 열평형에 이르면 어떤 양이 같은가요?",["질량","온도","열용량"],1,"물체의 온도가 같으면 두 물체 사이의 순열전달이 없습니다."),
 "pressure":("정지한 일정 밀도의 유체에서 깊이가 두 배가 되면 게이지압은?",["절반","그대로","두 배"],2,"게이지압 ρgh는 깊이에 비례합니다."),
 "convergence":("같은 문제에서 시간 간격을 줄인 계산을 반복하는 목적은?",["오차 변화 추정","공기 저항 제거","질량 측정"],0,"여러 격자의 오차를 기준해와 대조해 수렴성을 살펴봅니다."),
}


def graph():
    nodes, edges = [], []
    for stage, (name, topics) in enumerate(STAGES):
        for topic in topics:
            title, prerequisites, models, search, misconception = NODES[topic]
            quiz = QUIZZES.get(topic)
            nodes.append(dict(id=topic,title=title,stage=stage,prerequisites=prerequisites,models=models,
                              search=search,misconception=misconception,
                              checkpoint={"question":quiz[0],"options":quiz[1]} if quiz else None))
            edges.extend(dict(source=p,target=topic,type="prerequisite") for p in prerequisites)
            edges.extend(dict(source=topic,target=m,type="experiment") for m in models)
            edges.extend(dict(source=topic,target=m,type="formula") for m in models)
            edges.append(dict(source=topic,target=f"level-{stage}",type="broader"))
            edges.append(dict(source=f"level-{stage}",target=topic,type="narrower"))
            edges.append(dict(source=topic,target=misconception,type="misconception"))
    edges.extend(dict(source=a,target=b,type="related") for a,b in RELATED)
    return {"nodes":nodes,"edges":edges,"levels":[{"id":n,"title":s[0]} for n,s in enumerate(STAGES)]}

