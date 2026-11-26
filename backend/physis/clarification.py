"""Deterministic clarification and abstention helpers for experiment dialogue."""
from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4
import re
from threading import Lock

from pydantic import Field

from .schema import Experiment, ModelSpec, Patch, StrictModel


Classification = Literal["sufficient", "assumptions", "needs_clarification", "unsupported"]
_TURN_LOCK = Lock()
_DIALOGUE_TURNS: dict[str, int | None] = {}


class MissingCondition(StrictModel):
    key: str | None = None
    label: str
    unit: str = ""
    reason: str = ""


class DialogueState(StrictModel):
    """Client-carried state, always rebound to an experiment revision and reparsed."""

    id: UUID = Field(default_factory=uuid4)
    original_message: str = Field(min_length=1, max_length=2000)
    experiment_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1, strict=True)
    target_experiment_id: UUID | None = None
    model: str | None = Field(default=None, max_length=64)
    model_hint: str = Field(default="", max_length=100)
    kind: Literal["conditions", "semantic"] = "conditions"
    force_new: bool = False
    turn: int = Field(default=0, ge=0, strict=True)
    missing_conditions: list[MissingCondition] = Field(min_length=1, max_length=8)
    followups: list[str] = Field(default_factory=list, max_length=4)


class Clarification(StrictModel):
    message: str
    missing_conditions: list[MissingCondition] = Field(default_factory=list)
    dialogue: DialogueState | None = None


_NUMERIC_ASK = re.compile(
    r"몇\s*(?:초|분|시간|미터|cm|mm|kg|그램|뉴턴|파스칼|도|주기|배)?|얼마(?:나|야|인가|일까)?|"
    r"(?:값|수치|시간|속력|속도|가속도|힘|압력|온도|부피|부력|마찰계수|계수|파장|주기|각속도|유량|유속)(?:을|를|이|가)?\s*(?:알려|구해|계산|측정|확정)|"
    r"계산(?:해|하면|하고)|정확(?:히|한\s*값)|how\s+(?:much|long|fast|many)|"
    r"what\s+is\s+the\s+(?:value|time|force|pressure|speed|coefficient|period|wavelength|temperature|volume)|calculate\b",
    re.I,
)
_NUMERIC_ACTION = re.compile(
    r"몇\s*(?:초|분|시간|미터|cm|mm|kg|그램|뉴턴|파스칼|도)|얼마(?:나|야|인가|일까)?|"
    r"계산(?:해|하면|하고)|구해|측정(?:해|하면)|수치|정확(?:히|한\s*값)|"
    r"how\s+(?:much|long|fast|many)|calculate\b|compute\b|what\s+is\s+the\s+value",
    re.I,
)
_META_QUESTION = re.compile(
    r"원리|개념|뜻|의미|정의|설명|무슨\s*뜻|what\s+does\s+.{0,60}\s+mean|"
    r"what\s+is\s+(?:newton(?:'s)?\s+(?:second|2nd)\s+law|the\s+(?:net\s+)?force)(?:\s*[?.!]|\s+mean(?:ing)?)",
    re.I,
)
_EXPLICIT_DEMO = re.compile(
    r"(?:새\s*실험|실험을?\s*(?:만들|생성|구성)|시뮬레이션|예시(?:를|로)?\s*(?:보여|만들)|"
    r"실험을?\s*(?:실행|돌리|구동)|(?:실행|돌리|구동).{0,16}(?:실험|시뮬레이션)|"
    r"create\s+(?:an?\s+)?experiment|simulate\b|(?:run|execute|perform|start|launch)\b[^.!?]{0,40}"
    r"(?:simulation|experiment|model|case)\b|demonstration\b)", re.I)
_CURRENT_REFERENCE = re.compile(
    r"현재\s*(?:실험|결과|화면)|이번\s*(?:실험|실행)|이\s*실험|위\s*실험|저장한\s*실험|"
    r"this\s+experiment|current\s+(?:experiment|run)|saved\s+experiment", re.I)
_ACTUAL_CONTEXT = re.compile(
    r"실제|실측|측정값|측정\s*결과|어제|우리\s*(?:반|조|수레|실험|교실)|집에서|책상|"
    r"사진|영상|센서|기록지|관측값|실험실의|실험실에서|without\s+(?:data|measurements|a\s+photo|the\s+video)|"
    r"didn't\s+(?:upload|measure)|no\s+(?:data|measurements|record)", re.I)
_NO_EVIDENCE = re.compile(
    r"(?:자료|데이터|기록|측정|사진|영상|원자료)(?:가|을|를|도|는)?(?:\s|.{0,8}){0,1}(?:없|부족|안\s*올|제공되지|주지|미제공)|"
    r"올리지\s*않|모르는데|기억이\s*없|without\s+(?:data|measurements|a\s+photo|the\s+video)|"
    r"no\s+(?:data|measurements|record)", re.I)
_META_CLARIFICATION = re.compile(
    r"무엇을\s*(?:물어|확인)|뭐(?:를|가)?\s*(?:빠졌|필요)|어떻게\s*질문|어떤\s*질문|"
    r"무엇(?:을|부터)\s*(?:확인|질문)|무엇이\s*(?:필요|빠져)|what\s+should\s+i\s+ask|"
    r"what\s+(?:is|do\s+i\s+need)\s+missing", re.I)
_NEW_TOPIC = re.compile(
    r"(?:^|[.!?\s])(?:왜|무엇|뭐|어떻게|설명해|알려줘|새\s*실험|만들어|시뮬레이션|"
    r"why|what|how|explain|tell\s+me|create|simulate)\b", re.I)
_HAS_VALUE = re.compile(r"(?<![A-Za-z가-힣])[-+]?\d+(?:\.\d+)?\s*(?:[A-Za-zµμ°가-힣/²³]+)?")
_WATER_MEDIUM = re.compile(r"(?:물(?:에|속|의|을|이|은|에서)|수돗물|담수|바닷물|\bwater\b|liquid\s+water)", re.I)


_AMBIGUITIES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"(?:파동|파형|매질).{0,35}속도|속도.{0,35}(?:파동|파형|매질)", re.I),
     "속도의 종류", "파형의 전파 속력인지, 매질 입자의 진동 속력인지와 각 값의 단위를 확인해 주세요."),
    (re.compile(r"(?:처음\s*위치|돌아왔|왕복|한\s*바퀴|반\s*바퀴).{0,35}주기|주기.{0,35}(?:처음\s*위치|왕복|한\s*바퀴)", re.I),
     "주기 측정 구간", "주기를 재려는 시작 상태와 끝 상태가 같은 위상인지 확인해 주세요."),
    (re.compile(r"열", re.I), "열의 물리량", "온도 변화(°C 또는 K)인지 전달 에너지(J)인지 먼저 구분해 주세요."),
    (re.compile(r"(?:반\s*바퀴|회전).{0,30}(?:각속도|속도)|(?:각속도|회전\s*속도).{0,30}(?:기록|값|측정|\d)", re.I),
     "시간 간격", "회전한 각도와 그에 걸린 시간, 시간 단위를 함께 확인해 주세요."),
    (re.compile(r"(?:힘|force).{0,28}(?:N|뉴턴|숫자|값)|(?:N|뉴턴).{0,28}힘", re.I),
     "힘의 종류", "기록한 값이 물체에 작용한 개별 힘인지 모든 힘을 합한 알짜힘인지 확인해 주세요."),
    (re.compile(r"(?:부피|volume).{0,35}(?:잠긴|잠긴\s*부분|침수|부력)|(?:잠긴|침수).{0,35}부피", re.I),
     "부피의 범위", "물체 전체 부피인지 실제로 잠겨 유체를 밀어낸 부피인지 확인해 주세요."),
)


_MODEL_HINTS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("wave_longitudinal", re.compile(r"종파|압축.{0,10}파|코일|longitudinal", re.I), "종파"),
    ("wave_transverse", re.compile(r"횡파|진행파|파형|파동|wave|particle", re.I), "진행파"),
    ("free_fall", re.compile(r"자유\s*낙하|떨어[지뜨질져졌]|낙하|(?=.*(?:공|물체|ball))(?=.*(?:땅|바닥|ground|floor))(?=.*(?:초|시간|몇|time|long))", re.I), "자유 낙하"),
    ("pendulum", re.compile(r"진자|pendulum", re.I), "진자"),
    ("hydrostatic", re.compile(r"수압|정수압|수조.{0,15}압력|절대압", re.I), "정수압"),
    ("buoyancy", re.compile(r"부력|밀어낸\s*부피", re.I), "부력"),
    ("friction", re.compile(r"운동\s*마찰|마찰계수|friction", re.I), "운동 마찰"),
    ("spring", re.compile(r"용수철|스프링|spring", re.I), "용수철"),
    ("circular", re.compile(r"각속도|회전판|원\s*운동|angular\s+speed", re.I), "원 운동"),
    ("newton", re.compile(r"뉴[턴튼](?:의?\s*(?:제\s*2\s*법칙|제2법칙|운동\s*법칙|법칙))|"
                          r"Newton(?:'s)?(?:\s+(?:second|2nd))?\s+law|알짜힘|합력|"
                          r"net\s+(?:external\s+)?force|물체.{0,15}힘|힘.{0,15}물체|"
                          r"(?=.*(?:mass|질량))(?=.*(?:acceleration|가속도))|"
                          r"(?:how\s+much|what\s+is).{0,12}force|force.{0,15}(?:value|how\s+much|object|body)|"
                          r"(?:object|body).{0,15}force", re.I), "알짜힘"),
    ("heat_equilibrium", re.compile(r"열평형|열량|전달\s*에너지|heat\s+transfer|열\s*에너지", re.I), "열평형"),
    ("ideal_gas", re.compile(r"이상\s*기체|기체.{0,12}압력|ideal\s+gas|gas\s+pressure", re.I), "이상기체"),
    ("cooling", re.compile(r"냉각|식는|냉각\s*법칙|cooling", re.I), "냉각"),
    ("continuity", re.compile(r"유량|유속|단면적|관\s*흐름|flow\s+rate|pipe\s+flow", re.I), "관 유동"),
)


_FIELD_TEXT: dict[str, tuple[str, str]] = {
    "height": ("낙하 높이", "m"), "g": ("중력 가속도", "m/s²"),
    "length": ("진자 줄 길이", "m"), "angle": ("시작 각도", "rad"),
    "k": ("용수철 상수", "N/m"),
    "depth": ("수심", "m"), "p0": ("수면 기준 압력", "Pa"),
    "volume": ("밀어낸 유체 부피", "m³"), "density": ("유체 밀도", "kg/m³"),
    "mass": ("질량", "kg"), "force": ("알짜힘", "N"),
    "radius": ("회전 반지름", "m"), "omega": ("각속도", "rad/s"),
    "mu": ("운동 마찰 계수", "1"), "x0": ("초기 변위", "m"),
}


def _question_intent(text: str) -> bool:
    explicit_quantity = bool(_NUMERIC_ASK.search(text))
    value_context = bool(re.search(r"(?:net\s+(?:external\s+)?force|알짜힘|합력)", text, re.I)
                         and _HAS_VALUE.search(text))
    if not (explicit_quantity or value_context):
        return False
    if _META_QUESTION.search(text) and not _NUMERIC_ACTION.search(text) and not _HAS_VALUE.search(text):
        return False
    return True


def _infer_model(text: str, current: Experiment | None, catalog: dict[str, ModelSpec]):
    found = [(model, hint) for model, pattern, hint in _MODEL_HINTS
             if model in catalog and pattern.search(text)]
    if len(found) == 1:
        return found[0]
    if not found and current and _CURRENT_REFERENCE.search(text):
        return current.model, current.title
    return None, ""


def _explicit_values(text: str, model: str, current: Experiment | None) -> set[str]:
    """Use the existing parser as the authority for any user-supplied value."""
    from . import reasoning
    from .physics import SPECS

    try:
        patch = reasoning._parse_patch(text, SPECS[model], current if current and current.model == model else None)
    except (ValueError, KeyError):
        return set()
    return set(patch.values)


def _required_fields(text: str, model: str) -> list[str]:
    if model == "free_fall":
        required = ["height"]
        if re.search(r"달|moon|lunar", text, re.I) and not re.search(r"중력\s*(?:가속도)?\s*[-+]?\d|\bg\s*=", text, re.I):
            required.append("g")
        return required
    if model == "pendulum":
        return ["length", "angle"]
    if model == "hydrostatic":
        required = ["depth"]
        if re.search(r"액체|기름|fluid|liquid", text, re.I) and not _WATER_MEDIUM.search(text):
            required.append("density")
        return required
    if model == "buoyancy":
        required = ["volume"]
        if not _WATER_MEDIUM.search(text):
            required.append("density")
        if re.search(r"알짜힘|합력|무게를 뺀|net\s+force", text, re.I):
            required.append("mass")
        return required
    if model == "circular":
        if re.search(r"구심\s*가속도|centripetal\s+acceleration", text, re.I):
            return ["radius", "omega"]
        if re.search(r"각속도|angular\s+(?:speed|velocity)", text, re.I):
            return ["omega"]
        return ["radius", "omega"]
    if model == "spring":
        if re.search(r"주기|period", text, re.I):
            return ["mass", "k"]
        return ["mass", "k"]
    if model == "friction":
        if re.search(r"(?:정지|멈추|거리|stop|distance)", text, re.I):
            return ["v0", "mu"]
        return ["mass", "mu"]
    if model == "newton":
        if re.search(r"가속도(?:의|가|는|를)?\s*(?:크기|방향|얼마|값|구해|계산)|"
                     r"(?:magnitude|direction)\s+of\s+(?:the\s+)?acceleration", text, re.I):
            return ["mass", "force"]
        if re.search(r"(?:알짜힘|순힘|합력|힘|net\s+(?:external\s+)?force).{0,16}(?:얼마|값|수치|크기)|"
                     r"(?:얼마|how\s+much|what\s+is).{0,16}(?:알짜힘|합력|force)|"
                     r"force.{0,16}(?:value|how\s+much)", text, re.I):
            return ["mass", "a"]
        return ["mass", "force"]
    if model in {"wave_transverse", "wave_longitudinal"}:
        if re.search(r"(?:입자|매질).{0,12}속력|particle.{0,12}speed", text, re.I):
            return ["amplitude", "frequency"]
        return ["wavelength", "frequency"]
    if model == "heat_equilibrium":
        return ["temp_a", "temp_b", "capacity_a", "capacity_b"]
    if model == "ideal_gas":
        return ["moles", "temperature", "volume"]
    if model == "cooling":
        return ["initial_temp", "ambient", "rate"]
    if model == "continuity":
        return ["area_in", "area_out", "speed_in"]
    return []


def _condition(key: str, specs: dict[str, ModelSpec], reason: str = "") -> MissingCondition:
    label, unit = _FIELD_TEXT.get(key, (key.replace("_", " "), ""))
    for spec in specs.values():
        variable = next((item for item in spec.variables if item.key == key), None)
        if variable:
            label, unit = variable.label, variable.unit
            break
    return MissingCondition(key=key, label=label, unit=unit, reason=reason)


def _missing_prompt(model: str, missing: list[MissingCondition]) -> str:
    if model == "free_fall" and [item.key for item in missing] == ["height"]:
        return "낙하 시간을 계산하려면 낙하 높이(m)를 알려 주세요. 높이는 바닥 기준으로, 물체는 정지 상태에서 놓이고 지구 중력 가속도는 기본값을 쓰는 것으로 가정하겠습니다."
    if model == "free_fall" and any(item.key == "g" for item in missing):
        labels = "와 ".join(f"{item.label} ({item.unit})" for item in missing)
        return f"달 환경의 자유 낙하를 계산하려면 {labels}을(를) 알려 주세요. 환경 이름만으로는 중력 수치를 정하지 않겠습니다."
    labels = "와 ".join(f"{item.label} ({item.unit})" if item.unit else item.label for item in missing)
    return f"요청한 수치를 계산하려면 {labels}을(를) 알려 주세요."


def _state(message: str, missing: list[MissingCondition], experiment_id: UUID | None,
           revision: int | None, model: str | None, hint: str,
           kind: Literal["conditions", "semantic"] = "conditions") -> DialogueState:
    force_new = bool(model and not _CURRENT_REFERENCE.search(message)
                     and not re.search(r"바꾸|변경|수정|조정|change|modify", message, re.I))
    state = DialogueState(original_message=message, experiment_id=experiment_id, revision=revision,
                          target_experiment_id=uuid4() if model and (experiment_id is None or force_new) else None,
                          model=model, model_hint=hint, kind=kind, force_new=force_new,
                          missing_conditions=missing)
    with _TURN_LOCK:
        _DIALOGUE_TURNS[str(state.id)] = state.turn
    return state


def identify(message: str, current: Experiment | None, revision: int | None,
             catalog: dict[str, ModelSpec]) -> Clarification | None:
    """Return a specific clarification when answering from a default run would mislead."""
    text = message.strip()
    if not text:
        return None

    # A request to interpret an ambiguous note should name the missing distinction, not
    # substitute a simulation from whichever experiment happens to be open.
    for pattern, label, answer in _AMBIGUITIES:
        if not pattern.search(text):
            continue
        resolved = _semantic_resolved(label, text)
        if _META_CLARIFICATION.search(text):
            return Clarification(message=answer,
                                 missing_conditions=[MissingCondition(label=label, reason=answer)])
        if not resolved and _question_intent(text):
            missing = [MissingCondition(label=label, reason=answer)]
            state = _state(text, missing, current.id if current else None,
                           revision if current else None, None, "", kind="semantic")
            return Clarification(message=answer, missing_conditions=missing, dialogue=state)

    # Real measurements require the user's record or sensor data; a catalog default is
    # never evidence about a physical object outside this application.
    if (_ACTUAL_CONTEXT.search(text) and _question_intent(text)
            and (_NO_EVIDENCE.search(text) or not _HAS_VALUE.search(text))):
        model, _ = _infer_model(text, current, catalog)
        needed = {
            "friction": "운동 마찰력(N)과 수직항력(N) 또는 직접 구한 계수",
            "spring": "하중과 늘어난 길이, 또는 질량과 측정 주기",
            "hydrostatic": "센서 깊이(m)와 수면 기준 압력(Pa)",
            "buoyancy": "실제로 밀어낸 유체 부피(m³)와 유체 밀도(kg/m³)",
            "pendulum": "직접 잰 주기와 줄 길이",
            "free_fall": "낙하 높이와 실제 관찰 기록",
        }.get(model, "질문 대상의 실제 측정값 또는 원자료")
        return Clarification(message=f"이 요청은 특정 실물의 측정값을 묻고 있어 기본 시뮬레이션으로 확정할 수 없습니다. {needed}를 제공해 주세요.",
                             missing_conditions=[MissingCondition(label="실제 측정 자료", reason=needed)])

    if (_EXPLICIT_DEMO.search(text) and not re.search(r"달|moon|lunar", text, re.I)) \
            or _CURRENT_REFERENCE.search(text) or not _question_intent(text):
        return None

    model, hint = _infer_model(text, current, catalog)
    if not model:
        # An explicit model cue may be detected by the main parser even if this small
        # target map does not know how to require its inputs. Do not infer from unrelated state.
        return None
    # An open experiment is context only when the user points to it. A new question
    # about another object must not inherit that experiment's default height or data.
    referenced_current = current if current and current.model == model and _CURRENT_REFERENCE.search(text) else None
    explicit = _explicit_values(text, model, referenced_current)
    if model == "newton" and "a" in _required_fields(text, model):
        explicit |= _explicit_values(text, "acceleration", referenced_current)
    missing_keys = [key for key in _required_fields(text, model) if key not in explicit]
    if not missing_keys:
        return None
    missing = [_condition(key, catalog) for key in missing_keys]
    state = _state(text, missing, current.id if current else None,
                   revision if current else None, model, hint)
    return Clarification(message=_missing_prompt(model, missing), missing_conditions=missing, dialogue=state)


def _is_answer(message: str, state: DialogueState) -> bool:
    text = message.strip()
    if not text:
        return False
    aliases = []
    from . import reasoning
    for missing in state.missing_conditions:
        if missing.key:
            aliases.extend(reasoning._ALIASES.get(missing.key, []))
            aliases.extend([missing.label])
    if _NEW_TOPIC.search(text):
        starts_with_requested_field = any(alias and re.match(r"\s*" + re.escape(alias), text, re.I) for alias in aliases)
        if not starts_with_requested_field:
            return False
    if _HAS_VALUE.search(text):
        return True
    return any(alias and re.search(re.escape(alias), text, re.I) for alias in aliases) or len(text) <= 35


def _normalize_answer(message: str, state: DialogueState) -> str:
    text = message.strip()
    if len(state.missing_conditions) == 1 and state.missing_conditions[0].key:
        key = state.missing_conditions[0].key
        from . import reasoning
        aliases = [state.missing_conditions[0].label, *reasoning._ALIASES.get(key, [])]
        if not any(re.search(re.escape(alias), text, re.I) for alias in aliases if alias):
            return f"{state.missing_conditions[0].label} {text}"
    return text


def merge_followup(state: DialogueState | None, message: str, experiment_id: UUID | None,
                   revision: int | None, catalog: dict[str, ModelSpec]) -> tuple[str, DialogueState] | None:
    """Merge only a plausible answer for the same experiment revision."""
    if not state or state.experiment_id != experiment_id or state.revision != revision or not _is_answer(message, state):
        return None
    key = str(state.id)
    with _TURN_LOCK:
        latest = _DIALOGUE_TURNS.get(key, state.turn)
        if latest is None or latest != state.turn:
            return None
        _DIALOGUE_TURNS[key] = state.turn + 1
    followups = [*state.followups, _normalize_answer(message, state)]
    if len(followups) > 4 or sum(map(len, followups)) > 4000:
        restore(state)
        return None
    state = state.model_copy(update={"followups": followups, "turn": state.turn + 1})
    prefix = state.model_hint.strip()
    parts = [state.original_message]
    if prefix:
        parts.append(prefix)
    parts.extend(followups)
    return "\n".join(parts), state


def stale_dialogue(state: DialogueState | None, message: str, experiment_id: UUID | None,
                   revision: int | None) -> bool:
    """Identify answer-like turns that target an older or different dialogue state."""
    if not state or not _is_answer(message, state):
        return False
    if state.experiment_id != experiment_id or state.revision != revision:
        return True
    with _TURN_LOCK:
        latest = _DIALOGUE_TURNS.get(str(state.id), state.turn)
    return latest is None or latest != state.turn


def retire(state: DialogueState | None) -> None:
    if not state:
        return
    key = str(state.id)
    with _TURN_LOCK:
        latest = _DIALOGUE_TURNS.get(key, state.turn)
        if latest == state.turn:
            _DIALOGUE_TURNS[key] = None


def restore(state: DialogueState | None) -> None:
    """Release a just-claimed turn after a failed request so it can be retried."""
    if not state:
        return
    key = str(state.id)
    with _TURN_LOCK:
        if _DIALOGUE_TURNS.get(key) == state.turn + 1:
            _DIALOGUE_TURNS[key] = state.turn


def question_for(model: str, missing: list[MissingCondition]) -> str:
    return _missing_prompt(model, missing)


def plan_failure(message: str, current: Experiment | None, revision: int | None,
                 intent, catalog: dict[str, ModelSpec]) -> Clarification | None:
    """Promote only a genuinely omitted target value to a precise question."""
    from . import reasoning

    if "조건을 정확히 적용하기 어렵습니다" not in getattr(intent, "message", ""):
        return None
    model, hint = _infer_model(message, current, catalog)
    if not model and current:
        model, hint = current.model, current.title
    if not model or model not in catalog or _HAS_VALUE.search(message):
        return None
    mentioned = []
    for variable in catalog[model].variables:
        aliases = [variable.label, *reasoning._ALIASES.get(variable.key, [])]
        if any(alias and re.search(re.escape(alias), message, re.I) for alias in aliases):
            mentioned.append(variable.key)
    if len(mentioned) != 1 or not re.search(
            r"바꾸|수정|변경|늘리|줄이|높이|낮추|set\b|change\b|increase|decrease", message, re.I):
        return None
    missing = [_condition(mentioned[0], catalog, "변경할 값이 필요합니다.")]
    state = _state(message, missing, current.id if current else None,
                   revision if current else None, model, hint)
    condition = missing[0]
    question = f"{condition.label}을(를) 얼마로 설정할까요? 값과 단위를 알려 주세요 ({condition.unit})."
    return Clarification(message=question, missing_conditions=missing, dialogue=state)


def response(prompt: str, level: str, missing: list[MissingCondition] | None = None,
             dialogue: DialogueState | None = None) -> dict:
    missing = missing or []
    evidence = {
        "core": prompt, "sources": [], "formula": None, "calculations": [],
        "assumptions": [], "claims": [], "checks": [],
        "uncertainty": ["필요한 물리 조건이 확인될 때까지 계산하지 않았습니다."],
        "theory_status": "insufficient", "simulation_supported": False,
        "related_models": [], "prerequisite": None, "awaiting_conditions": True,
        "answer_state": "CLARIFICATION_REQUIRED",
    }
    lesson = {"mode": "explain", "title": "조건 확인이 필요합니다", "text": prompt,
              "prompt": "", "actions": [], "evidence": evidence}
    return {
        "action": "needs_clarification", "status": "UNSUPPORTED", "message": prompt,
        "snapshot": None, "level": level, "lesson": lesson, "evidence": evidence,
        "classification": "needs_clarification", "answer_state": "CLARIFICATION_REQUIRED",
        "missing_conditions": [item.model_dump(mode="json") for item in missing],
        "dialogue": dialogue.model_dump(mode="json") if dialogue else None,
    }


def unresolved(state: DialogueState, effective_message: str, current: Experiment | None,
               catalog: dict[str, ModelSpec]) -> list[MissingCondition]:
    if state.kind == "semantic":
        return state.missing_conditions if not _semantic_resolved(
            state.missing_conditions[0].label, effective_message) else []
    if not state.model or state.model not in catalog:
        return state.missing_conditions
    from . import reasoning
    try:
        patch = reasoning._parse_patch(effective_message, catalog[state.model],
                                       current if current and current.model == state.model else None)
    except (ValueError, KeyError):
        patch = Patch()
    supplied = set(patch.values)
    acceleration_values = {}
    if any(item.key == "a" for item in state.missing_conditions) and "acceleration" in catalog:
        try:
            acceleration_values = reasoning._parse_patch(effective_message, catalog["acceleration"], None).values
        except (ValueError, KeyError):
            pass
    remaining = []
    for item in state.missing_conditions:
        available = acceleration_values if item.key == "a" else patch.values
        if item.key not in available:
            remaining.append(item)
            continue
        variable_specs = [catalog[state.model], catalog.get("acceleration")] if item.key == "a" else [catalog[state.model]]
        variable = next((v for spec in variable_specs if spec for v in spec.variables if v.key == item.key), None)
        value = available[item.key]
        if variable and not variable.min <= value <= variable.max:
            remaining.append(item.model_copy(update={"reason": f"허용 범위는 {variable.min:g}~{variable.max:g} {variable.unit}입니다."}))
    return remaining


def result_classification(action: str, experiment: Experiment | None, intent_patch: Patch | None,
                          run_status: str | None) -> tuple[Classification, list[str]]:
    if experiment is None:
        return ("unsupported", []) if action in {"unsupported", "needs_clarification"} else ("sufficient", [])
    assumed_values = []
    if action in {"create", "compare"}:
        patch = intent_patch or Patch()
        explicit = set(patch.values)
        omitted = [v for v in experiment.variables if v.key not in explicit]
        if omitted:
            values = ", ".join(f"{v.label} {experiment.values[v.key]:g} {v.unit}" for v in omitted)
            assumed_values.append(f"질문에서 정하지 않은 입력은 등록 기본값을 사용했습니다: {values}.")
        if patch.duration is None:
            assumed_values.append(f"관찰 시간 {experiment.duration:g} s는 등록 기본값입니다.")
        if patch.dt is None:
            assumed_values.append(f"시간 간격 {experiment.dt:g} s는 등록 기본값입니다.")
        if patch.method is None:
            method = {"analytic": "해석해", "euler": "오일러", "semi_implicit": "반암시적 오일러", "rk4": "룽게–쿠타 4차"}.get(experiment.method, experiment.method)
            assumed_values.append(f"계산 방법은 등록 기본값인 {method}를 사용했습니다.")
    if action in {"unsupported", "needs_clarification"} or run_status in {"FAILED", "UNSUPPORTED", "UNVERIFIED"}:
        return "unsupported", assumed_values
    if assumed_values:
        return "assumptions", assumed_values
    if run_status == "LIMITED":
        return "assumptions", ["물리 엔진 결과는 제한된 조건에서만 해석할 수 있습니다."]
    return "sufficient", []


def blocked_scope(message: str, current: Experiment | None, special: str | None = None) -> bool:
    """Apply the planner's domain guard before clarification, visual parsing or retrieval."""
    from . import reasoning

    if special == "drag":
        from . import grounded
        # Remove only the aerodynamic terms that selected the reviewed reading route;
        # unrelated out-of-scope requests still hit the planner's complete guard.
        cleaned = reasoning._IDEAL_AIR.sub("", grounded.DRAG.sub("", message))
        if reasoning._OUTSIDE.search(cleaned) or reasoning._outside_model(message, current):
            return True
        # Descriptive drag questions may use literature. Numeric/model requests must
        # not be converted into ideal free-fall output.
        return bool(_question_intent(message) or _EXPLICIT_DEMO.search(message)
                    or re.search(r"시뮬레이션|계산해|계산하면|바꿔|만들어|simulate|calculate", message, re.I))
    cleaned = reasoning._IDEAL_AIR.sub("", message)
    if reasoning._OUTSIDE.search(cleaned):
        return True
    if reasoning._outside_model(message, current):
        from .physics import SPECS
        model, _ = _infer_model(message, current, SPECS)
        # A named planetary environment is a missing numeric condition for an otherwise
        # supported vertical drop, not permission to replace that value with Earth gravity.
        if model == "free_fall" and re.search(r"달|moon|lunar", message, re.I):
            return False
        return True
    return False


def special_topic(message: str) -> str | None:
    """Resolve supported reading routes, including drag theory without drag simulation."""
    from . import grounded, reasoning
    topic = grounded.specialty(message)
    if topic:
        return topic
    # “Ignoring air resistance” explicitly selects the ideal model, so remove that
    # qualifier before looking for a request to explain aerodynamic drag.
    if grounded.DRAG.search(reasoning._IDEAL_AIR.sub("", message)):
        return "drag"
    return None


def drag_only_request(message: str, current: Experiment | None, special: str | None = None) -> bool:
    """Keep reviewed aerodynamic theory available when its calculation is unsupported."""
    from . import grounded, reasoning
    if special != "drag":
        return False
    cleaned = reasoning._IDEAL_AIR.sub("", grounded.DRAG.sub("", message))
    return not reasoning._OUTSIDE.search(cleaned) and not reasoning._outside_model(message, current)


def _semantic_resolved(label: str, text: str) -> bool:
    patterns = {
        "속도의 종류": r"파형.{0,12}(?:전파|이동)|전파\s*속력|매질.{0,12}(?:입자|진동)|입자\s*(?:속도|속력)|particle|propagation",
        "주기 측정 구간": r"같은\s*위상|왕복|평형점|처음(?:과|에서).{0,12}끝|same\s+phase|one\s+full\s+cycle",
        "열의 물리량": r"온도|열량|전달\s*에너지|\b(?:J|kJ|°C|K)\b|temperature|energy",
        "시간 간격": r"(?:초|분|시간|\bs\b|\bsec\b|\bmin\b)\s*(?:동안|걸려|소요|elapsed)?|\d+(?:\.\d+)?\s*(?:초|분|s|sec|min)",
        "힘의 종류": r"알짜힘|순힘|합력|개별\s*힘|작용한\s*힘|net\s+force|applied\s+force",
        "부피의 범위": r"전체\s*부피|잠긴\s*(?:부분|부피)|밀어낸\s*(?:유체\s*)?부피|total\s+volume|displaced\s+volume",
    }
    pattern = patterns.get(label)
    return bool(pattern and re.search(pattern, text, re.I))

