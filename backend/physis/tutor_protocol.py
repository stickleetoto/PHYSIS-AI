"""Finite visual instructions addressing only an existing experiment and its run."""
import re
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from .physics import SPECS
from .schema import Experiment, Number, Patch, Run, StrictModel
from .state import build


class ObjectAction(StrictModel):
    op: Literal["highlight_object", "show_force", "show_velocity", "show_acceleration"]
    index: int = Field(strict=True, ge=0)


class QuantityAction(StrictModel):
    op: Literal["highlight_quantity"]
    quantity: str


class GraphAction(StrictModel):
    op: Literal["highlight_graph"]
    quantity: str
    start: Number
    end: Number


class Pause(StrictModel):
    op: Literal["pause"]


class Seek(StrictModel):
    op: Literal["seek"]
    time: Number


class Mutation(StrictModel):
    op: Literal["change_conditions", "create_comparison"]
    patch: Patch


class VariableAction(StrictModel):
    op: Literal["highlight_variable"]
    variable: str


Action = Annotated[ObjectAction | QuantityAction | GraphAction | Pause | Seek | Mutation | VariableAction,
                   Field(discriminator="op")]
_ACTIONS = TypeAdapter(Annotated[list[Action], Field(max_length=12)])
_VECTOR = {"show_force": ("fx", "fy"), "show_velocity": ("vx", "vy"), "show_acceleration": ("ax", "ay")}
_COMPARE = re.compile(r"비교(?:\s*실험)?|\bcompar(?:e|ison)\b", re.I)


def is_comparison_request(message: str) -> bool:
    if re.search(r"실험(?:을|을 하나 더)?\s*(?:복제|복사)(?:해|하|할|해\s*줘)|\b(?:clone|duplicate)\s+(?:this |the )?experiment", message, re.I):
        return True
    if not _COMPARE.search(message):
        return False
    if re.search(r"(?:바꿔|바꾸|변경|설정|복제|추가|늘려|줄여|반으로|절반|두\s*배|세\s*배|\d+\s*배|duplicate|clone|change|double|half)", message, re.I):
        return True
    if re.search(r"비교\s*실험.{0,8}(?:생성|만들|만드|시작)|새(?:로운)?\s*(?:비교|실험)|다른\s*조건(?:의|으로)|하나\s*더", message):
        return True
    if message.strip(" .!?") in {"비교 실험","비교 실험 생성","create comparison"}:
        return True
    return bool(re.search(r"\d+(?:\.\d+)?\s*(?:kg|g|cm|m|N|Pa|Hz|K|s|초|도)\s*(?:으?로|인)\s*(?:바로\s*)?(?:실험|조건|경우|비교)",message,re.I))


def comparison_message(message: str) -> str:
    """Keep all conditions, including units, for the normal contextual planner."""
    stripped = re.sub(r"(?:(?:이|현재|지금|기존)\s*)?실험(?:을|을 하나 더)?\s*(?:복제|복사)(?:해\s*(?:줘|주세요)?|하자)|\b(?:clone|duplicate)\s+(?:this |the )?experiment",
                      " ", message, flags=re.I)
    return re.sub(r"비교(?:\s*실험)?(?:을|를)?\s*(?:생성|만들어|해|하자|하고)?\s*(?:줘|주세요|보기)?|\bcompare\b",
                  " ", stripped, flags=re.I).strip(" .?!")


def validate_actions(raw, exp: Experiment, run: Run) -> list[dict]:
    actions = _ACTIONS.validate_python(raw)
    elapsed = run.times[-1] if run.times else 0
    quantities = {key.split(".", 1)[1] for key in run.series if "." in key} & exp.measurements.keys()
    mutations = 0
    for action in actions:
        if isinstance(action, ObjectAction):
            if action.index >= len(exp.objects):
                raise ValueError("이 실험에 없는 물체입니다.")
            axes = _VECTOR.get(action.op)
            if axes and not any(f"{action.index}.{axis}" in run.series for axis in axes):
                raise ValueError("이 실험에서는 해당 벡터를 측정하지 않습니다.")
        elif isinstance(action, QuantityAction | GraphAction):
            if action.quantity not in quantities:
                raise ValueError("계산 결과에 없는 물리량입니다.")
            if isinstance(action, GraphAction) and not 0 <= action.start < action.end <= elapsed:
                raise ValueError(f"그래프 구간은 0~{elapsed:g}초 안에서 시작 < 끝을 만족해야 합니다.")
        elif isinstance(action, Seek) and not 0 <= action.time <= elapsed:
            raise ValueError(f"이동할 시각은 0~{elapsed:g}초 안에서 선택하세요.")
        elif isinstance(action, VariableAction) and action.variable not in exp.values:
            raise ValueError("현재 실험에 등록되지 않은 공식 변수입니다.")
        elif isinstance(action, Mutation):
            mutations += 1
            if mutations > 1:
                raise ValueError("한 번에 한 가지 조건 변경이나 비교만 요청하세요.")
            if action.op == "change_conditions" and not (action.patch.values or action.patch.model_dump(exclude={"values"}, exclude_none=True)):
                raise ValueError("변경할 조건이 필요합니다.")
            build(SPECS[exp.model], exp.id, action.patch, exp)
    return [action.model_dump(exclude_none=True) for action in actions]


_LABELS = {
    "x": "수평 위치|변위|위치", "y": "높이|수직 위치", "vx": "수평 속도", "vy": "수직 속도",
    "ax": "수평 가속도", "ay": "수직 가속도", "fx": "수평 힘", "fy": "수직 힘",
    "ke": "운동 에너지", "pe": "위치 에너지", "energy": "역학적 에너지|에너지", "angle": "각도",
    "flow": "유량", "pressure": "압력", "depth": "깊이", "temperature": "온도", "speed": "속력",
    "buoyancy": "부력", "error": "오차", "momentum": "운동량",
    "displacement":"변위|관측점 변위", "quarter_displacement":"사분 파장 변위", "heat":"열량",
    "edge_temperature":"끝 온도|경계 온도", "temperature_rate":"온도 변화율",
    "gauge_pressure":"게이지압|게이지 압력","area":"단면적","volume":"부피",
    "weight":"무게","support":"지지력","dissipated":"소산 에너지","angular_velocity":"각속도",
}


def primary_quantity(exp: Experiment, run: Run):
    keys = [k[2:] for k in run.series if k.startswith("0.") and k[2:] in exp.measurements]
    for key in ("pressure", "flow", "buoyancy", "temperature", "displacement", "angle",
                "y" if exp.model == "free_fall" else "x", *keys):
        if key in keys:
            return key
    return None


def _quantity(text, exp, run):
    candidates = []
    for key in exp.measurements:
        if not any(k.endswith("." + key) for k in run.series):
            continue
        for label in [*_LABELS.get(key, "").split("|"), key]:
            if not label:
                continue
            pattern = re.escape(label)
            if label.isascii():
                pattern = r"(?<![A-Za-z0-9_])" + pattern + r"(?![A-Za-z0-9_])"
            if re.search(pattern, text, re.I):
                candidates.append((len(label), key))
    if candidates:
        return max(candidates)[1]
    # An unqualified velocity/acceleration graph uses the model's movement axis.
    for word, axis in (("가속도", "a"), ("속도", "v")):
        if word in text:
            key = axis + ("y" if exp.model == "free_fall" else "x")
            return key if key in exp.measurements else None
    return None


def visualization_request(message: str, exp: Experiment, run: Run) -> list[dict] | None:
    """Match only display requests. Simulation planning retains compound change requests."""
    text = message.strip().lower()
    if not text or re.search(r"변경|바꿔|바꾸|비교|생성|실험 만들|새 실험|조건을|줄여|늘려|두 배", text):
        return None
    from . import reasoning
    if reasoning._OUTSIDE.search(reasoning._IDEAL_AIR.sub("", text)) or reasoning._outside_model(text, exp):
        return None
    if any(k != exp.model and re.search(pattern, text, re.I) for k, pattern in reasoning._MODELS.items() if k in SPECS):
        return None
    actions = []
    # A graph described as "표시된" or "showing" is part of the question. Only
    # imperative display requests should enter the graph-action validator.
    display = bool(re.search(
        r"(?:보여|띄워|켜|(?:표시|강조)해)\s*(?:줘|주세|주실|줄래|달라|봐|라|요|[.!?]?$)"
        r"|(?:표시|강조)\s*[.!?]?$|^(?:please\s+|can you\s+|could you\s+)?(?:highlight|show)\b",
        text,
    ))
    obj = re.search(r"(?:물체|공|수레)\s*([a-z]|\d+)|([첫두세네])\s*번째\s*(?:물체|공|수레)", text)
    index = 0
    if obj:
        token = obj[1] or obj[2]
        if token.isdigit():
            index = int(token) - 1
        elif token.isascii():
            index = ord(token) - ord("a")
        else:
            index = "첫두세네".index(token)
    if display and "벡터" in text:
        for word, op in (("가속도", "show_acceleration"), ("속도", "show_velocity"), ("힘", "show_force")):
            if re.search("(?<!가)" + word if word == "속도" else word, text):
                actions.append({"op": op, "index": index})
        if not actions:
            raise ValueError("힘, 속도, 가속도 중 표시할 벡터를 골라 주세요.")
    if display and ("공식" in text or "수식" in text) and ("강조" in text or "변수" in text):
        named = {key for _,_,key in reasoning._mentions(text, exp)}
        matches = [v for v in exp.variables if v.key in named or v.label in text or re.search(
            r"(?<![a-z0-9_])" + re.escape(v.key) + r"(?![a-z0-9_])", text)]
        if len(matches) != 1:
            raise ValueError("강조할 공식 변수 하나를 골라 주세요. " + ", ".join(v.label for v in exp.variables))
        actions.append({"op": "highlight_variable", "variable": matches[0].key})
    number = r"(-?(?:\d+(?:\.\d*)?|\.\d+))"
    if display and "그래프" in text:
        interval = re.search(number + r"\s*(?:초|s)?\s*(?:부터|에서|~|～|–|-)\s*" + number, text)
        quantity = _quantity(text, exp, run)
        if not quantity and re.match(r"^(?:이 |현재 |시간 )?그래프", text):
            quantity = primary_quantity(exp, run)
        if not quantity:
            raise ValueError("그래프에서 볼 측정량을 지정하세요.")
        # A whole graph can be selected even if no interval was specified.
        if interval:
            actions.append({"op": "highlight_graph", "quantity": quantity, "start": float(interval[1]), "end": float(interval[2])})
        elif re.search(r"구간|\d", text):
            raise ValueError("그래프의 시작 시각과 끝 시각을 초 단위로 지정하세요.")
        else:
            actions.append({"op": "highlight_quantity", "quantity": quantity})
    if re.search(r"(?:초|\bs\b).*?(?:이동|가줘|맞춰|옮겨)|\bseek\b", text):
        when = re.search(number + r"\s*(?:초|s\b)", text)
        if not when:
            raise ValueError("이동할 시각을 초 단위로 입력하세요.")
        actions.append({"op": "seek", "time": float(when[1])})
    if re.search(r"일시\s*정지|멈춰|\bpause\b", text):
        actions.append({"op": "pause"})
    if display and not actions:
        key = _quantity(text, exp, run)
        if key:
            actions.append({"op": "highlight_quantity", "quantity": key})
        elif obj:
            actions.append({"op": "highlight_object", "index": index})
        elif "강조" in text:
            raise ValueError("현재 실험에서 강조할 물체나 측정량을 지정하세요.")
    return validate_actions(actions, exp, run) if actions else None
