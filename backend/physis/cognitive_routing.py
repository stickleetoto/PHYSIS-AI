"""Deterministic, multi-intent routing for the local tutoring pipeline."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Route:
    """Stable route facts; this type never contains generated or mutable state."""

    intents: tuple[str, ...]
    model: str | None
    confidence: float
    unsupported_reason: str | None = None
    hypothetical: bool = False
    references_current: bool = False

    @property
    def primary(self) -> str:
        return self.intents[0] if self.intents else "unsupported"


_CURRENT = re.compile(
    r"현재\s*(?:실험|시뮬레이션|결과|화면)|이번\s*(?:실험|시뮬레이션|실행|결과)|이\s*(?:실험|시뮬레이션)|위\s*실험|"
    r"저장한\s*실험|this\s+experiment|current\s+(?:experiment|run)|saved\s+experiment",
    re.I,
)
_CURRENT_FOLLOWUP = re.compile(
    r"^\s*(?:(?:그럼|그렇다면|so)\s*)?(?:왜|이유(?:는|가)?|설명(?:해\s*줘)?|해석(?:해\s*줘)?|"
    r"결과(?:는|가)?|원리(?:는|가)?|what\??|why\??|how\??|explain\??|and\s+why\??)[?!.\s]*$",
    re.I,
)
_CREATE = re.compile(
    r"새\s*실험|실험을?\s*(?:만들|생성|구성)|시뮬레이션|예시(?:를|로)?\s*(?:보여|만들)|"
    r"create\s+(?:an?\s+)?experiment|simulate\b|(?:run|execute|perform|start|launch)\b[^.!?]{0,40}"
    r"(?:simulation|experiment|model|case)\b|"
    r"시뮬레이션.{0,12}(?:실행|돌리|구동)|(?:실행|돌리|구동).{0,12}시뮬레이션|"
    r"(?:시뮬레이터|수치\s*실험|물리\s*엔진)[^.!?]{0,100}(?:실행|돌려|구동|재현|추적|모의)|"
    r"실험(?:을|으로)?\s*(?:실행|돌리|구동)|demonstration",
    re.I,
)
_MODIFY = re.compile(
    r"바꿔|바꾸|변경|수정|조정|늘리|줄이|높이|낮추|설정해|change\b|modify\b|set\s+the|"
    r"increase\b|decrease\b|double\b|halve\b",
    re.I,
)
_HYPOTHETICAL = re.compile(
    r"what\s+if|suppose|assume\s+(?:that\s+)?|if\s+[^?.!]{0,90}\b(?:would|could|were|was)\b|"
    r"\bwould\s+[^?.!]{0,80}\bif\b|"
    r"만약|가정(?:하면|할\s*때|한\s*다면)|(?:라면|다면|일\s*경우)|\b가정해\s*보면",
    re.I,
)
_EXPLICIT_MODIFY = re.compile(
    r"^\s*(?:please\s+)?(?:change|modify|adjust|set|increase|decrease|raise|lower|double|halve)\b|"
    r"\b(?:change|modify|adjust|set)\s+(?:the\s+)?[\w-]+\s+(?:to|by)\s*[-+\d]|"
    r"(?:크게|작게|길게|짧게|빠르게|느리게|같게|다르게)\s*해\s*(?:봐|줘|주세요|라)|"
    r"(?:바꿔|바꾸|변경(?:해|하)|수정(?:해|하)|조정(?:해|하)|늘려|줄여|높여|낮춰|올려|내려|설정해|맞춰|키워)"
    r"\s*(?:줘|주세요|봐|봅시다|하자|해|비교해\s*(?:줘|봐|주세요)|[.!?]?$)",
    re.I,
)
_CAUSAL_QUESTION = re.compile(r"^\s*(?:why|how|what\s+does|왜|어떻게|무슨\s*뜻|무엇을\s*뜻)", re.I)
_COMPARE = re.compile(r"비교|차이(?:가|를|는)?|어느\s*(?:쪽|것)|대비|compare|versus|\bvs\.?\b|difference", re.I)
_FORMULA = re.compile(
    r"공식|수식|방정식|유도|증명|적용\s*조건|성립\s*조건|formula|equation|derive|proof|"
    r"applicability|conditions?",
    re.I,
)
_CALCULATION = re.compile(
    r"계산|얼마(?:나|야|인가|일까)?|몇\s*(?:초|분|시간|미터|cm|mm|kg|그램|뉴턴|파스칼|도|회)?|"
    r"값을?\s*(?:구해|알려)|수치(?:를|가)?\s*(?:구해|알려)|정확(?:히|한\s*값)|"
    r"calculate\b|compute\b|how\s+(?:much|long|fast|many)|what\s+is\s+the\s+(?:value|time|force|speed)",
    re.I,
)
_MATH = re.compile(
    r"수학|미분|적분|도함수|극한|행렬|벡터|방정식|대수|함수|기울기|derivative|integral|"
    r"calculus|algebra|matrix|vector|limit|slope|quadratic|polynomial|equation|math(?:ematics)?",
    re.I,
)
_CONCEPT = re.compile(
    r"왜|이유|원리|개념|뜻|설명|해석|어떻게|무엇|무슨|차이|관계|원인|"
    r"why|because|cause|mechanism|principle|concept|meaning|explain|interpret|how|what|relation",
    re.I,
)
_UNCLEAR_REFERENCE = re.compile(
    r"^\s*(?:그(?:것|거| 값| 결과| 실험)?|이(?:것|거| 값| 결과)?|저(?:것|거)?|it|that|this|those|they)"
    r"(?:\s|은|는|이|가|을|를|에|의|\?|$)", re.I,
)
_NONPHYSICS = re.compile(
    r"날씨|주식|레시피|요리|노래|메일|소설|이야기|영화|정치|주가|"
    r"weather|stock|recipe|cooking|song|email|story|novel|movie|politic",
    re.I,
)
_PHYSICS_TOPIC = re.compile(
    r"물리|힘|질량|속도|속력|가속도|운동|에너지|일\s*에너지|운동량|충돌|낙하|중력|"
    r"파동|파형|열|온도|압력|유체|밀도|부력|진자|용수철|마찰|항력|공기\s*저항|"
    r"전자기|자기장|전기장|양자|상대성|광자|빛|기체|원자|분자|"
    r"physics|force|mass|velocity|speed|acceleration|motion|energy|momentum|collision|fall|gravity|"
    r"wave|heat|temperature|pressure|fluid|density|buoyancy|pendulum|spring|friction|drag|"
    r"electromagnet|magnetic|electric|quantum|relativity|photon|light|gas|atom|molecule",
    re.I,
)
_UNSUPPORTED_DOMAINS = (
    ("gravitational_lensing",
     re.compile(r"gravitational\s+lens(?:ing)?|중력\s*렌즈", re.I),
     "일반상대론적 시공간 곡률과 빛의 전파를 함께 다루는 중력렌즈 모델",
     ()),
    ("astrophysics",
     re.compile(r"white\s*dwarf|neutron\s*star|stellar|astrophys|electron\s+degeneracy|degeneracy\s+pressure|black\s*hole|백색\s*왜성|중성자별|항성\s*(?:내부|구조)|축퇴\s*압력", re.I),
     "별 내부의 상태방정식과 항성 구조 모델",
     ("hydrostatic", "ideal_gas")),
    ("optics",
     re.compile(r"optics?|optical\s+(?:lens|system|bench)|ray\s+trac|focal\s+length|refraction|reflection|image\s+formation|렌즈|초점\s*거리|굴절|반사|상\s*만들기", re.I),
     "광선 추적과 렌즈·거울의 기하 및 굴절률을 처리하는 광학 모델",
     ("wave_transverse", "wave_superposition")),
    ("electromagnetism",
     re.compile(r"electromagnet|electric\s+field|magnetic\s+field|electric\s+circuit|circuit\s+current|capacitance|inductance|maxwell|electrostatic|전기장|자기장|전자기|회로\s*전류|축전기|정전기", re.I),
     "전기장·자기장 또는 회로의 장·경계 조건을 계산하는 모델",
     ()),
    ("projectile_motion",
     re.compile(r"projectile|ballistic|trajectory|launch\s+angle|포물선\s*운동|투사체|발사체|발사\s*각도", re.I),
     "2차원 발사체 궤적과 초기 속도·각도를 함께 처리하는 모델",
     ("free_fall", "uniform")),
    ("inclined_plane",
     re.compile(r"inclined\s+plane|ramp\s+motion|slope\s+plane|경사면|빗면", re.I),
     "경사면 방향 분해와 수직항력·마찰을 함께 처리하는 모델",
     ("newton", "friction")),
    ("drag_and_wind",
     re.compile(r"air\s*resistance|drag\s*(?:force|coefficient|law)?|wind\s+(?:field|speed|resistance)|공기\s*저항|항력|바람(?:까지|을|의)?\s*(?:포함|고려|속도)", re.I),
     "항력 법칙·항력 계수와 물체 기준의 바람장을 처리하는 모델",
     ("free_fall",)),
    ("complex_fluid_flow",
     re.compile(r"turbulen(?:t|ce)|computational\s+fluid|\bcfd\b|viscous\s+(?:flow|fluid)|난류|점성\s*(?:유체|유동|흐름)|전산\s*유체", re.I),
     "점성 응력과 난류를 다루는 유체 모델 또는 CFD 해석기",
     ("continuity", "bernoulli")),
    ("quantum_relativity",
     re.compile(r"quantum|relativit|spacetime|양자|상대성|시공간", re.I),
     "양자 상태 또는 상대론적 시공간을 다루는 물리 모델",
     ()),
    ("nuclear_process",
     re.compile(r"nuclear\s+(?:decay|reaction|fission|fusion)|radioactiv|핵\s*(?:붕괴|반응|분열|융합)|방사성\s*붕괴", re.I),
     "핵 반응·붕괴와 방사성 동위원소 자료를 다루는 모델",
     ()),
    ("thermal_process",
     re.compile(r"heat\s+engine|carnot|thermal\s+radiation|phase\s+change|phase\s+transition|열기관|카르노|열복사|상변화|상\s*전이", re.I),
     "열기관·상변화·복사를 계산하는 열역학 모델",
     ("heat_equilibrium", "heat_diffusion", "cooling")),
)


def _model_for(question: str, current) -> str | None:
    """Resolve model aliases against the full simulation registry, not only numeric cues."""
    from .clarification import _infer_model
    from .physics import SPECS
    from .reasoning import _MODELS
    from .science_language import resolve_field_terms

    model, _ = _infer_model(question, current, SPECS)
    if model in SPECS:
        return model
    named = {key for key, pattern in _MODELS.items() if key in SPECS and re.search(pattern, question, re.I)}
    named = set(resolve_field_terms(sorted(named), question))
    return next(iter(named)) if len(named) == 1 else None


def _unsupported_recovery(question: str, *, action_request: bool, model: str | None) -> tuple[str | None, str | None]:
    if not action_request:
        return None, None
    for topic, pattern, dependency, related in _UNSUPPORTED_DOMAINS:
        # A broad catalog model name in the same question does not make a specialized
        # phenomenon representable (for example, free fall is not a drag model).
        if pattern.search(question):
            from .physics import SPECS

            related_titles = [SPECS[key].title for key in related if key in SPECS]
            related_text = ", ".join(related_titles) if related_titles else "직접 대체할 등록 모델은 없습니다"
            phenomenon = {
                "astrophysics":"천체 내부 물리",
                "gravitational_lensing":"중력렌즈 현상",
                "optics":"기하광학",
                "electromagnetism":"전자기 현상",
                "projectile_motion":"2차원 발사체 운동",
                "inclined_plane":"경사면 운동",
                "drag_and_wind":"항력과 바람을 포함한 운동",
                "complex_fluid_flow":"점성·난류 유동",
                "quantum_relativity":"양자·상대론 현상",
                "nuclear_process":"핵 반응·붕괴",
                "thermal_process":"열기관·상변화·열복사",
            }[topic]
            reason = (f"요청한 {phenomenon} 계산은 현재 등록 모델에서 지원하지 않습니다. "
                      f"필요한 의존 기능은 {dependency}입니다. 관련해 사용할 수 있는 등록 기능: {related_text}. "
                      "관련 개념 자료는 확인할 수 있지만, 이를 요청한 계산의 대체 결과로 사용하지 않습니다.")
            return topic, reason
    return None, None


def route(question: str, current=None) -> Route:
    """Return all clear intents, a single catalog model when inferable, and a heuristic score.

    This is only a selector. Experiment-domain guards, patch validation, and numeric/source
    verification remain the responsibility of their existing deterministic owners.
    """
    text = question.strip() if isinstance(question, str) else ""
    if not text:
        return Route(("clarification",), None, 0.0)

    current_reference = bool(_CURRENT.search(text) or (current and _CURRENT_FOLLOWUP.search(text)))
    hypothetical = bool(_HYPOTHETICAL.search(text))
    model = _model_for(text, current)
    if current_reference and current and model is None:
        model = current.model
    create = bool(_CREATE.search(text))
    modify_request = bool(_EXPLICIT_MODIFY.search(text)) and not hypothetical and not _CAUSAL_QUESTION.search(text)
    modify = modify_request and (current is not None or current_reference)
    compare = bool(_COMPARE.search(text))
    formula = bool(_FORMULA.search(text))
    calculation = bool(_CALCULATION.search(text) or hypothetical)
    math = bool(_MATH.search(text))
    concept = bool(_CONCEPT.search(text) and (_PHYSICS_TOPIC.search(text) or model or current_reference))
    intents: list[str] = []

    if create:
        intents.append("experiment_create")
    if modify:
        intents.append("experiment_modify")
    if compare:
        intents.append("comparison")
    if formula:
        intents.append("formula")
    if calculation:
        intents.append("calculation")
    if math:
        intents.append("math")
    if concept:
        intents.append("concept")

    clarification_needed = bool(_UNCLEAR_REFERENCE.search(text))
    if calculation and model:
        from .clarification import _explicit_values, _required_fields

        required = _required_fields(text, model)
        referenced_current = current if current_reference and current and current.model == model else None
        explicit = _explicit_values(text, model, referenced_current)
        if model == "newton" and "a" in required:
            explicit |= _explicit_values(text, "acceleration", referenced_current)
        if current_reference and current and current.model == model:
            explicit |= set(current.values)
        clarification_needed = clarification_needed or any(key not in explicit for key in required)
    elif calculation and not model and not current_reference:
        clarification_needed = True

    if clarification_needed:
        intents.append("clarification")

    # Recognized non-physics requests and explicit unsupported simulation/edits stay out of
    # the read-only model fallback. A conceptual question about an out-of-catalog physics
    # topic may still proceed to the existing guarded literature path.
    from . import reasoning
    out_of_catalog = bool(reasoning._OUTSIDE.search(text))
    # A causal explanation such as "why does drag change motion?" contains the verb
    # "change" but is still read-only; do not turn it into a model-edit request.
    explicit_edit = modify_request and not concept
    action_request = create or modify or explicit_edit or calculation
    unsupported_topic, unsupported_reason = _unsupported_recovery(text, action_request=action_request, model=model)
    if _NONPHYSICS.search(text):
        intents.append("unsupported")
    elif unsupported_reason:
        intents.append("unsupported")
    elif out_of_catalog and action_request:
        intents.append("unsupported")
    elif not intents:
        intents.append("unsupported")

    # Fixed precedence lets consumers pick a primary path without discarding other intents.
    priority = ("experiment_create", "experiment_modify", "comparison", "formula",
                "calculation", "math", "concept", "clarification", "unsupported")
    ordered = tuple(kind for kind in priority if kind in intents)
    if "clarification" in ordered:
        confidence = 0.45 if len(ordered) == 1 else 0.6
    elif "unsupported" in ordered:
        confidence = 0.95
    elif model and set(ordered).issubset({"concept", "formula"}):
        confidence = 0.9
    elif ordered:
        confidence = 0.85
    else:
        confidence = 0.0
    if unsupported_topic:
        model = None
    return Route(ordered, model, confidence, unsupported_reason, hypothetical, current_reference)
