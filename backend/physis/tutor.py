"""Classroom modes sharing the same registry, engine readout, and visual protocol."""
from typing import Literal

from .schema import Experiment, Level, Run
from .tutor_protocol import comparison_message, is_comparison_request, primary_quantity, validate_actions, visualization_request

Mode = Literal["explain", "experiment", "discovery", "equation", "review"]

# Short derivations for the classroom fields outside the initial Formula Explorer library.
_FIELD_DERIVATIONS = {
    "wave_transverse": ["입자가 한 주기 T 동안 한 번 진동한다고 두면 각진동수는 ω=2π/T이다.",
                        "한 파장 λ 뒤에서 위상이 같으므로 k=2π/λ이다. 오른쪽으로 진행하는 파의 위상은 kx−ωt이다.",
                        "같은 위상을 따라가면 kΔx=ωΔt이므로 파형 속력은 c=ω/k=fλ이다. 변위는 진행 축에 수직이다."],
    "wave_longitudinal": ["입자의 평형 위치를 x라 둔다. 변위 ξ는 진행 축을 따라 잰다.",
                          "한 파장과 한 주기마다 위상이 2π씩 반복되므로 ξ=A sin(2πx/λ−2πt/T)로 쓴다.",
                          "일정한 위상은 한 주기에 한 파장만큼 이동하므로 전파 속력은 c=λ/T=fλ이다."],
    "wave_superposition": ["선형 매질에서 한 지점의 합성 변위는 두 변위의 합이다.",
                           "θ=kx−ωt로 두면 u=A[sin θ+sin(θ+φ)]이다.",
                           "삼각함수 덧셈식으로 정리하면 u=2A cos(φ/2) sin(θ+φ/2)이다. φ=π이면 상쇄된다."],
    "wave_standing": ["같은 진폭과 진동수를 가진 두 진행파를 반대 방향으로 보낸다.",
                      "A sin(kx−ωt)와 A sin(kx+ωt)를 더하면 2A sin(kx) cos(ωt)가 된다.",
                      "sin(kx)=0인 곳은 모든 시각에 변위가 0이므로 고정된 마디이다."],
    "ideal_gas": ["고정된 양의 이상기체는 절대온도가 일정할 때 pV가 일정하고, 부피가 일정할 때 p가 T에 비례한다.",
                  "두 비례 관계와 물질량 n에 대한 비례를 합하면 pV=nRT이다.",
                  "부피로 나누면 현재 상태의 압력 p=nRT/V를 얻는다. T에는 켈빈을 쓴다."],
    "heat_equilibrium": ["순간 열전달률을 G(T₁−T₂)로 두고 각 물체에 Q̇=CṪ를 적용한다.",
                         "두 에너지 수지를 더하면 C₁T₁+C₂T₂가 일정하다.",
                         "평형에서 T₁=T₂이므로 공통 온도는 (C₁T₁,₀+C₂T₂,₀)/(C₁+C₂)이다."],
    "cooling": ["환경과의 온도차를 ΔT=T−T환경으로 두고 변화율이 온도차에 비례한다고 가정한다.",
                "d(ΔT)/dt=−kΔT를 적분하면 ΔT(t)=ΔT(0)e^(−kt)이다.",
                "환경 온도를 더하면 물체의 시각별 온도를 얻는다."],
    "heat_diffusion": ["균일한 막대의 에너지 수지와 푸리에 열전도 법칙을 합하면 ∂T/∂t=α∂²T/∂x²이다.",
                       "고정된 양끝 온도를 기준으로 온도차를 B(t) sin(πx/L)로 놓는다.",
                       "대입하면 B′=−α(π/L)²B이므로 초기 사인 분포의 진폭은 지수적으로 감소한다."],
    "bernoulli": ["정상 비압축성 흐름에서 질량 보존을 적용하면 A₁v₁=A₂v₂이다.",
                  "손실이 없는 한 유선을 따라 에너지 보존을 쓰면 p+ρv²/2+ρgz가 일정하다.",
                  "두 단면 높이가 같으므로 p₂=p₁+ρ(v₁²−v₂²)/2이다."],
    "fluid_tracer": ["추적 입자가 평균 흐름과 같은 속도로 움직인다고 둔다.",
                     "균일한 일차원 흐름에서는 dx/dt=v가 일정하다.",
                     "시간에 대해 적분하고 초기 위치를 대입하면 x=x₀+vt이다."],
}

# Each question specifies the conditions under which exactly one choice is correct.
# The stable answer indexes also permit rechecking a saved learner response.
_REVIEW = {
    "free_fall": ("공기 저항을 무시하고 같은 높이에서 동시에 놓은 두 공 중 어느 것이 먼저 닿을까요?",
                  ["무거운 공", "두 공이 동시에", "가벼운 공"], 1, "중력 mg를 질량 m으로 나누면 두 공의 가속도가 모두 g입니다."),
    "uniform": ("속도가 일정한 수레의 위치–시간 그래프에서 기울기가 뜻하는 것은?",
                ["속도", "힘", "이동 시간"], 0, "기울기는 위치의 변화량을 걸린 시간으로 나눈 속도입니다."),
    "acceleration": ("일정한 양의 가속도로 움직일 때 같은 시간 간격마다 일정하게 늘어나는 것은?",
                     ["위치", "힘", "속도"], 2, "속도 변화량은 가속도와 시간 간격의 곱입니다."),
    "newton": ("알짜힘을 고정하고 수레 질량을 두 배로 하면 가속도는?",
               ["두 배가 된다", "절반이 된다", "그대로이다"], 1, "a = F/m이므로 같은 알짜힘에서는 질량이 클수록 가속도가 작습니다."),
    "friction": ("오른쪽으로 미끄러지는 지우개에 바닥이 가하는 운동 마찰력은 어느 방향일까요?",
                 ["왼쪽", "오른쪽", "위쪽"], 0, "운동 마찰력은 접촉면 사이의 상대 미끄럼을 방해합니다."),
    "collision": ("외력이 없는 두 수레가 비탄성 충돌할 때에도 보존되는 것은?",
                  ["각 수레의 속력", "총운동 에너지", "총운동량"], 2, "두 수레 사이의 충격량은 크기가 같고 방향이 반대여서 계의 운동량 합이 보존됩니다."),
    "spring": ("수평 용수철의 추를 평형점 오른쪽으로 당겼을 때 복원력은?",
               ["왼쪽으로 작용한다", "오른쪽으로 작용한다", "항상 0이다"], 0, "훅의 법칙 F = −kx의 음의 부호는 평형점으로 향하는 힘을 뜻합니다."),
    "pendulum": ("작은 각도로 흔들리는 진자의 줄 길이만 4배로 하면 주기는?",
                 ["4배", "2배", "절반"], 1, "작은 각도에서 T = 2π√(L/g)이므로 길이가 4배이면 주기는 2배입니다."),
    "damped": ("감쇠 계수가 양수이고 추가 움직일 때 점성 감쇠가 역학적 에너지에 미치는 영향은?",
               ["증가시킨다", "항상 보존한다", "감소시킨다"], 2, "점성 감쇠의 일률은 −bv²이므로 움직일 때 역학적 에너지가 줄어듭니다."),
    "circular": ("등속 원운동에서 중심을 향하는 물리량은?",
                 ["가속도", "속도", "각운동량"], 0, "속도의 방향이 바뀌면서 가속도가 원의 중심으로 향합니다."),
    "hydrostatic": ("수면 압력과 밀도가 일정한 물에서 깊이를 두 배로 하면 게이지압은?",
                    ["그대로", "두 배", "네 배"], 1, "수면을 기준으로 한 압력 차이는 ρgh이므로 깊이에 비례합니다."),
    "buoyancy": ("물에 완전히 잠긴 물체의 부피와 물의 밀도를 고정하고 물체의 질량만 늘리면 부력은?",
                 ["늘어난다", "줄어든다", "그대로이다"], 2, "부력은 밀어낸 물의 무게 ρgV와 같아서 잠긴 부피가 같으면 달라지지 않습니다."),
    "continuity": ("정상 비압축성 유동에서 관의 단면적이 절반이 되면 그 곳의 평균 속력은?",
                   ["두 배", "절반", "그대로"], 0, "유량 Q = Av가 일정하므로 단면적이 절반이면 속력은 두 배입니다."),
    "wave_transverse": ("횡파에서 매질 입자의 진동 방향과 파동의 진행 방향은?",
                        ["평행", "수직", "항상 반대"], 1, "횡파에서는 매질의 변위가 전파 방향에 수직입니다."),
    "wave_longitudinal": ("종파에서 매질 입자는 어느 방향으로 진동할까요?",
                          ["전파 방향과 나란히", "전파 방향과 수직으로", "항상 원형으로"], 0, "종파에서는 입자들이 전파 방향과 나란히 왕복하면서 밀집과 희박이 전달됩니다."),
    "wave_superposition": ("선형 매질의 같은 지점에서 두 파동의 변위가 서로 같은 크기이고 반대이면 합성 변위는?",
                           ["두 배", "절반", "0"], 2, "중첩 원리에 따라 그 순간의 변위를 부호까지 더합니다."),
    "wave_standing": ("이상적인 정상파에서 마디의 변위는?",
                      ["항상 최대", "항상 0", "항상 양수"], 1, "마디에서는 서로 반대로 진행하는 두 파동의 변위가 항상 상쇄됩니다."),
    "ideal_gas": ("이상기체의 양과 부피가 일정할 때 절대온도를 두 배로 하면 압력은?",
                  ["두 배", "절반", "그대로"], 0, "pV = nRT에서 양과 부피를 고정하면 압력은 절대온도에 비례합니다."),
    "heat_equilibrium": ("단열된 두 물체가 열평형에 도달하면 같아지는 것은?",
                         ["열용량", "질량", "온도"], 2, "열평형은 두 물체의 온도가 같아져 순열전달이 사라진 상태입니다."),
    "cooling": ("뉴턴 냉각에서 환경보다 뜨거운 물체가 환경 온도에 가까워지면 냉각 속력은?",
                ["커진다", "작아진다", "일정하다"], 1, "온도 변화율의 크기는 물체와 환경의 온도 차이에 비례합니다."),
    "heat_diffusion": ("열원이 없고 물성이 일정한 막대 내부에서 열은 어느 방향으로 전달될까요?",
                       ["높은 온도에서 낮은 온도로", "낮은 온도에서 높은 온도로", "온도 분포와 무관하게"], 0, "푸리에 법칙에서 열유속은 온도가 낮아지는 방향을 향합니다."),
    "bernoulli": ("정상·비압축·비점성 유동의 같은 유선에서 높이가 같을 때 유속이 큰 곳의 정압은?",
                  ["더 높다", "같다", "더 낮다"], 2, "같은 높이에서 p + ρv²/2가 일정하므로 속력이 크면 정압이 낮습니다."),
    "fluid_tracer": ("정상 유동에서 이상적인 추적 입자의 순간 속도는?",
                     ["유선에 수직이다", "그 위치의 유체 속도와 같다", "항상 0이다"], 1, "추적 입자는 그 위치의 유체 흐름을 따라 이동한다고 가정합니다."),
}


def review_question(exp):
    item = _REVIEW.get(exp.model)
    if not item:
        raise ValueError("이 모델의 복습 문항이 등록되지 않았습니다.")
    question, options, correct, feedback = item
    return dict(question=question, options=options, correct=correct, feedback=feedback)


def teach(message: str, mode: Mode, exp: Experiment, run: Run, level: Level, explanation: str) -> dict:
    quantity = primary_quantity(exp, run)
    actions = []
    extra = {}
    variable = next((v for v in exp.variables if v.key in {"mass_b", "length", "force", "mu", "k", "depth", "area_out"}), exp.variables[0])
    if mode == "discovery":
        title = "먼저 결과를 예측해 보세요"
        text = f"{exp.title}에서 {variable.label}만 바꾼다면 어떤 변화가 보일까요? 다른 조건은 고정하고, 예상과 그 이유를 적어 보세요."
        prompt = "가설을 기록한 뒤 실험 장면과 측정값을 관찰하세요."
        actions = [{"op": "pause"}]
    elif mode == "review":
        title = "개념 확인"
        extra["review"] = review_question(exp)
        text = extra["review"]["question"]
        prompt = "한 가지 답을 골라 근거를 확인하세요."
    elif mode == "equation":
        from .science_formulas import FORMULAS
        title = f"{exp.title}의 공식"
        formula = FORMULAS.get(exp.model)
        sections = [exp.formula, "변수와 단위\n" + "\n".join(
            f"{v.label} ({v.key}) = {exp.values[v.key]:g} {v.unit}" for v in exp.variables)]
        steps = formula["steps"] if formula else _FIELD_DERIVATIONS.get(exp.model, [])
        if steps:
            sections.append("유도 과정\n" + "\n".join(f"{i}. {step}" for i, step in enumerate(steps, 1)))
        if formula:
            sections.append("차원 확인\n" + formula["dimensions"])
        sections.append("적용 조건\n" + " · ".join(exp.assumptions))
        text = "\n\n".join(sections)
        prompt = f"{variable.label}을 바꾸면 식의 어느 항이 달라질까요?"
        actions = [{"op": "highlight_variable", "variable": variable.key}]
    elif mode == "experiment":
        title = "변수 하나를 바꾸는 실험"
        text = f"{exp.goal}\n\n{variable.label}의 현재 설정은 {exp.values[variable.key]:g} {variable.unit}입니다. 허용 범위는 {variable.min:g}~{variable.max:g} {variable.unit}입니다. 바꿀 값을 정한 뒤 나머지 조건을 고정하세요.\n\n{explanation}"
        prompt = f"‘{variable.label}을 … {variable.unit}로 바꿔 줘’처럼 조건을 지정해 보세요."
        if quantity:
            actions = [{"op": "highlight_quantity", "quantity": quantity}]
    elif mode == "explain":
        title = exp.title
        text = explanation
        prompt = exp.comparison
        if quantity:
            actions = [{"op": "highlight_quantity", "quantity": quantity}]
    else:
        raise ValueError("알 수 없는 튜터 모드입니다.")
    selected = visualization_request(message, exp, run)
    if selected:
        actions = selected
    return dict(mode=mode, title=title, text=text, prompt=prompt,
                actions=validate_actions(actions, exp, run), **extra)
