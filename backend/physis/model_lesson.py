"""Teach from the existing classroom model and label its provenance separately from literature."""
import re

from . import reasoning
from .formula_registry import check_applicability, formula_by_id, formula_for


# Concept contrasts follow the observables and assumptions of the existing models.
# This table contains no measured values, document rankings or assessment IDs.
CONCEPTS = {
    "wave_longitudinal": "압축된 구간은 옆으로 전파됩니다. 코일 하나를 표시하고 따라가면 그 코일은 평형 위치 주위를 전파 방향과 나란히 왕복합니다.",
    "wave_standing": "마디에서는 두 진행파의 변위가 모든 시각에 상쇄되어 계속 0입니다. 배에서는 진동 진폭이 가장 큽니다.",
    "fluid_tracer": "정상 흐름에서는 고정된 한 지점의 유속이 시간에 따라 일정합니다. 그 지점을 지나가는 입자는 흐름을 따라 계속 이동할 수 있습니다.",
    "heat_equilibrium": "단열된 두 물체가 열평형에 이르면 온도가 같아지고 두 물체 사이의 순열전달이 사라집니다. 에너지 보존과 각 물체의 열용량이 그 온도를 결정합니다.",
    "ideal_gas": "같은 양의 이상기체를 단단한 밀폐 용기에서 데우면 분자들의 평균 병진 운동에너지가 커집니다. 벽에 부딪히는 분자들이 단위 시간에 단위 면적으로 전달하는 운동량이 커져 압력이 오릅니다. 양과 부피가 고정된 조건에서 절대압은 켈빈 온도에 비례합니다. 이 실험의 압력계는 상태 방정식으로 계산하며 개별 충돌을 측정하지 않습니다.",
    "damped": "점성 저항력은 속도와 반대 방향으로 일을 합니다. 진폭과 역학적 에너지가 줄며 그만큼 계와 주변의 내부 에너지로 전환됩니다.",
    "hydrostatic": "유체가 정지해 있을 때 깊이에 따른 압력 증가는 밀도·중력 가속도·깊이의 곱입니다. 열린 수조의 게이지압은 절대압에서 주변 대기압을 뺀 값입니다.",
    "buoyancy": "부력은 밀어낸 유체의 무게입니다. 유체 밀도와 중력 가속도, 잠긴 부피가 일정하면 내부 질량을 바꿔도 부력은 같습니다. 물체의 무게와 알짜힘은 변할 수 있습니다.",
    "circular": "등속 원운동에서는 속력의 크기는 일정해도 접선 방향이 계속 바뀝니다. 속도 벡터의 이 변화 때문에 가속도가 생기며 방향은 원의 중심을 향합니다.",
    "collision": "두 물체가 달라붙는 비탄성 충돌에서는 운동 에너지 일부가 변형이나 열에 쓰입니다.",
}
EASY = re.compile(r"쉽게|직관|비유|헷갈|이해가?.{0,4}안|모르겠|intuit|analogy", re.I)
DETAILED = re.compile(r"유도|증명|미분|적분|자세|derive|proof|in detail", re.I)
ANALOGY_LIMITS = {
    "pendulum":"실제 그네에서는 공기 저항과 축 마찰도 작용합니다.",
    "friction":"실제 접촉면의 마찰계수는 표면과 속도에 따라 달라질 수 있습니다.",
    "newton":"실제 수레에서는 바퀴의 저항도 알짜힘에 포함됩니다.",
    "damped":"이 모델은 저항력이 속도에 비례하는 범위만 다룹니다.",
    "continuity":"호스 비유에서는 누수와 유체의 압축을 무시합니다.",
}

ALTERNATE_FORMULAS = {
    "pendulum": (
        ("pendulum_equation", r"각가속도|운동\s*방정식|토크|angular acceleration|equation of motion|torque"),
        ("pendulum_small_angle", r"소각|작은\s*(?:각|진폭)|(?:각도|진폭).{0,8}작|근사|언제|성립|적용\s*조건|small.{0,8}(?:angle|amplitude)|approxim"),
    ),
    "collision": (("collision_restitution", r"반발\s*계수|상대\s*(?:속도|속력)|restitution|relative velocity"),),
    "heat_equilibrium": (("heat_exchange", r"열류|열전달률|접촉\s*열전도|heat\s*(?:current|transfer rate)"),),
}


def select_formula(question, experiment):
    for key, pattern in ALTERNATE_FORMULAS.get(experiment.model, ()):
        if re.search(pattern, question, re.I):
            return formula_by_id(key)
    return formula_for(experiment.model)


def explain_model(question, snapshot, level):
    if not question or snapshot is None:
        return None
    exp = snapshot.experiment
    if snapshot.run.status == "LIMITED":
        missing = reasoning._ABSENT.get(exp.model)
        if missing and missing[0] not in snapshot.run.facts:
            return {"kind":"model_explanation", "status":"model_explanation", "text":missing[1],
                    "references":[exp.model], "limits":list(exp.assumptions)}
    if snapshot.run.status != "VERIFIED":
        return None
    record = formula_for(exp.model)
    if not record or check_applicability(record["formula_id"], exp)["status"] != "applicable":
        return None
    concept = CONCEPTS.get(exp.model) or reasoning._CONCEPT.get(exp.model, exp.goal)
    if exp.model == "ideal_gas" and re.search(r"섭씨|°C|celsius",question,re.I):
        concept += " 섭씨 온도를 두 배로 한 경우에는 켈빈으로 환산한 두 온도의 비를 써야 합니다."
    if exp.model == "collision":
        concept = reasoning._CONCEPT[exp.model] + " " + concept
    easy = level == "intro" or EASY.search(question)
    if easy:
        introduction = reasoning._INTRO.get(exp.model)
        if introduction and introduction != concept:
            concept = introduction + " " + concept
        limit = ANALOGY_LIMITS.get(exp.model)
        if introduction and limit:
            concept += " " + limit
    elif level in {"university", "research"} or DETAILED.search(question):
        derivation = reasoning._DERIVE.get(exp.model)
        if derivation and derivation != concept:
            concept += " " + derivation
    if level == "research":
        limits = list(dict.fromkeys([*record.get("conditions", []), *exp.assumptions]))
        if limits:
            concept += " 적용 조건은 " + ", ".join(limits) + "입니다."
    limits = list(dict.fromkeys([*record.get("conditions", []), *exp.assumptions]))
    return {"kind":"model_explanation", "status":"model_explanation", "text":concept,
            "references":[record["formula_id"]], "limits":limits,
            "provenance":"registered_model", "scope_model":exp.model}

