"""Reviewable retrieval vocabulary. Tags refer to topics and do not verify equations."""
import re
import unicodedata

# Preferred English indexing terms followed by Korean/English aliases and formula spellings.
VOCABULARY = {
    "units": "unit conversion|단위|단위 환산|단위 변환|단위변환|SI 단위|기본 단위|환산 계수|measurement units",
    "dimensions": "dimensional analysis|차원 분석|차원|dimensionally consistent",
    "vector": "vectors|벡터|스칼라|방향과 크기|scalar",
    "derivative": "instantaneous velocity|미분|도함수|순간 속도|순간속도|dx/dt|derivative|기울기",
    "displacement": "displacement|변위|이동 거리|이동거리|위치 변화",
    "velocity": "velocity|속력|속도|등속|average speed|평균속도",
    "acceleration": "acceleration|가속도|등가속|dv/dt|v=v0+at",
    "gravity": "free fall|자유 낙하|자유낙하|낙하|중력|gravitational acceleration",
    "inertia": "inertia|관성|제1법칙|제1 법칙|first law",
    "newton": "newton's second law|뉴턴|제2법칙|제2 법칙|알짜힘|합력|힘|힘과 질량|force|f=ma|a=f/m|ΣF=ma|net force|second law",
    "reaction": "newton's third law|작용 반작용|작용반작용|제3법칙|third law",
    "friction": "friction|마찰|마찰력|마찰계수|μ|μk|f=μn",
    "drag": "drag force|항력|공기 저항|공기저항|종단 속도|종단속도|air resistance|terminal velocity",
    "centripetal": "centripetal acceleration|구심|원운동|등속 원운동|v²/r|v^2/r",
    "energy": "kinetic energy|운동 에너지|운동에너지|일 에너지|work energy|½mv²",
    "momentum": "momentum|운동량|충격량|p=mv|impulse",
    "elastic": "elastic collision|충돌|탄성 충돌|탄성충돌|반발 계수|restitution",
    "density": "density|밀도|ρ|ρ=m/v|rho=m/v",
    "hydrostatic": "pressure|정수압|수압|수심|압력|hydrostatic|ρgh|rho*g*h",
    "buoyancy": "buoyancy|부력|아르키메데스|archimedes|floating",
    "continuity": "flow rate|연속 방정식|연속방정식|유량|유선|추적자|streamline|continuity|a1v1=a2v2",
    "bernoulli": "bernoulli|베르누이|정압과 동압",
    "gas": "ideal gas|이상기체|이상 기체|pv=nrt|절대 온도|기체 법칙",
    "equilibrium": "thermal equilibrium|열평형|열 평형|zeroth law",
    "heat": "specific heat|비열|열용량|열량|calorimetry|q=mcδt",
    "conduction": "conduction|열전도|열 전도|열확산|열 확산|온도 기울기|thermal diffusion|fourier",
    "convection": "convection|대류|냉각|cooling",
    "hooke": "simple harmonic motion|후크|훅의 법칙|용수철|스프링|f=-kx|hooke",
    "oscillation": "oscillator|단순 조화|조화 운동|단진동|진동수|harmonic",
    "pendulum": "pendulum|진자|소각도|작은 각|작은각|small angle|θ|2π√(l/g)|2πsqrt(l/g)|2*pi*sqrt(l/g)",
    "damping": "damping|감쇠|과감쇠|임계 감쇠|damped oscillation",
    "wave": "traveling waves|횡파|종파|파동|파속|파장|λ|longitudinal|transverse|v=fλ",
    "superposition": "superposition|중첩|간섭|보강|상쇄|interference",
    "standing": "standing waves|정상파|정재파|마디|배와 마디|공명|nodes|antinodes",
}

STOP = set("a an the to on is of or an and me it how does do with for this what in can why when about are was at as if be i tell please explain that law laws motion force".split())


def norm(text):
    return unicodedata.normalize("NFKC", text).casefold().replace("’", "'").replace("−", "-")


def tokens(text):
    return [word for word in re.findall(r"[^\W_]+", norm(text)) if len(word) > 1 and word not in STOP]


def concepts(query):
    folded = norm(query)
    compact = re.sub(r"\s+", "", folded)
    found = {}
    for concept, aliases in VOCABULARY.items():
        for alias in (concept, *aliases.split("|")):
            term = norm(alias)
            if re.fullmatch(r"[a-z]+(?:[ '][a-z]+)*", term):
                matched = re.search(r"(?<![a-z])" + re.escape(term) + r"s?(?![a-z])", folded)
            else:
                matched = re.sub(r"\s+", "", term) in compact
            if matched:
                found[concept] = max(found.get(concept, 0), 1 + min(len(term), 15) / 15)
    return found

