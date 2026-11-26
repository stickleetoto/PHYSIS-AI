"""Constrained experiment planning and interpretation of engine-owned observations."""
import math
import re
import unicodedata
from uuid import UUID

from pydantic import ValidationError

from .providers import Candidate, ProviderError, provider_name, request_candidate, request_reading
from .schema import Experiment, Level, ModelSpec, Patch, Run
from .state import build
from . import science_language


class Intent(Candidate):
    message: str = ""


_SCOPE = "현재 지원하는 교실 물리 실험에서 다루기 어려운 요청입니다. 실험 목록에서 모델을 선택해 주세요."
_CONDITIONS = "조건을 정확히 적용하기 어렵습니다. 바꿀 변수, 범위 안의 값, 단위를 지정해 주세요."


def _decline(level, reason=_SCOPE):
    return Intent(action="unsupported", model=None, patch=Patch(), level=level, message=reason)


_MODELS = {
    **science_language.MODELS,
    "damped": r"감쇠|감쇄|damped|damping",
    "free_fall": r"자유\s*낙하|떨어[지뜨질져졌]|낙하|진공.{0,80}(?:놓|놓았|낙하|바닥)|free[ -]?fall|falling|drop(?:ped)?\b",
    "collision": r"충돌|반발\s*계수|운동량\s*보존|collis(?:ion|ions)|collid(?:e|ing)",
    "friction": r"마찰|미끄러|friction",
    "pendulum": r"진자|pendulum",
    "spring": r"용수철|스프링|훅의?\s*법칙|단순\s*조화|spring|hooke",
    "circular": r"원\s*운동|원궤도|회전판|구심|원심|turntable|circular|centripetal",
    "buoyancy": r"부력|아르키메데스|물에\s*잠긴|buoyan",
    "continuity": r"연속\s*(?:방정식|법칙)|관의?\s*단면|유량|유속|(?:입구|출구)\s*(?:평균\s*)?(?:속력|속도|단면)|continuity|pipe\s*flow|outlet\s*(?:speed|velocity)",
    "hydrostatic": r"수압|정수압|정수\s*압력|수심|게이지압|hydrostatic|water\s*pressure|gauge\s*pressure",
    "newton": r"뉴[턴튼]|순힘|알짜힘|합력|힘을?\s*(?:가하|가해|주면|밀)|newton|net\s*force",
    "acceleration": r"등\s*가속|일정한\s*가속도|constant\s*acceleration",
    "uniform": r"등속|일정한\s*속[도력]|uniform\s*motion|constant\s*(?:speed|velocity)",
}
_OUTSIDE = re.compile(
    r"공기\s*저항|항력|풍속|지구\s*자전|포물선|투사체|발사체|빗면|경사면|난류|점성\s*(?:유체|유동)|CFD|"
    r"자기장|전기장|전자기|양자|상대성|블랙홀|상변화|복사열|열기관|카르노|실제\s*기체|화학\s*반응|날씨|주식|레시피|"
    r"폭발|폭탄|총알|탄도|무기|미사일|포탄|살상|암살|무력화|바이러스|병원체|해킹|악성\s*코드|"
    r"(?:시|소설|이야기|노래|메일)(?:를|을|로)\s*(?:써|쓰|지어|만들|작성)|"
    r"air\s*resistance|\bdrag\b|projectile|inclined\s*plane|quantum|relativity|explosiv|"
    r"ballistic|weapon|missile|firearm|gunshot|bullet|bomb\b", re.I)
_IDEAL_AIR = re.compile(r"(?:공기\s*저항|항력)(?:을|이|은|를)?\s*(?:무시(?:하고|한|하는)?|없[이는다]|제외(?:한|하고)?)|"
                        r"(?:without|ignore|ignoring|no)\s+(?:air\s*resistance|drag)", re.I)
_NO_FRICTION = re.compile(r"무\s*마찰|마찰(?:력)?(?:을|이|은)?\s*(?:무시(?:하고|한|하는)?|없(?:는|이|다고|도록|음)|제외(?:한|하고)?)|"
                          r"frictionless|(?:without|no|ignoring)\s+friction", re.I)
_NO_DAMPING = re.compile(r"무\s*감쇠|감쇠(?:력)?(?:가|를|는)?\s*(?:없(?:는|이|음)|무시(?:한|하고)?)|undamped|without\s+damping", re.I)
_MASS_GAP = re.compile(r"질량\s*(?:의\s*)?차이?|mass\s*(?:gap|difference)", re.I)
_INAPPLICABLE = {
    "collision": r"[23이삼]\s*차원|비스듬|충돌\s*각도|oblique|[23][ -]?d\b|two[ -]dimensional",
    "oscillation": r"강제\s*(?:감쇠\s*)?진동|구동\s*(?:진동|주파수|력)|주기적(?:인)?\s*외력|공명|forced\s*oscillat|driven|resonan",
    "buoyancy": r"떠\s*오르|떠\s*올|떠오[른를]|떠있|떠\s*있는|가라\s*앉|부분\s*잠|일부만\s*잠|부분\s*침수|부유|float(?:ing|s)?\b|sink(?:ing|s)?\b|rise\b",
    "free_fall": r"던[져지진질졌짐]|내던|위(?:쪽)?로\s*(?:쏘|발사)|초기\s*속[도력]|처음\s*속[도력]|throw|toss|launch|initial\s*(?:speed|velocity)",
}


def _outside_model(text, current):
    # Named environments require explicit conditions in this version of the catalog.
    if re.search(r"달(?:에서|의\s*(?:표면|중력)|\s*표면|\s*중력)|화성(?:에서|의\s*중력)|\b(?:moon|lunar|mars)\b", text, re.I):
        from .physics import SPECS
        spec = SPECS["free_fall"]
        try:
            given = _parse_patch(text, spec, None).values.get("g")
        except ValueError:
            return True
        gravity = next(v for v in spec.variables if v.key == "g")
        if given is None or not gravity.min <= given <= gravity.max:
            return True
    active = current.model if current else None
    named = {m for m, pattern in _MODELS.items() if re.search(pattern, text, re.I)}
    for family, pattern in _INAPPLICABLE.items():
        members = ("spring", "pendulum", "damped") if family == "oscillation" else (family,)
        matches_model = bool(named.intersection(members)) if named else active in members
        if matches_model and re.search(pattern, text, re.I):
            # The free-fall registry releases from rest. Stating that condition is supported.
            if family == "free_fall" and re.search(r"(?:처음|초기)\s*속[도력](?:은|는|이|가|를|을)?\s*(?:=\s*)?0(?:\.0+)?\s*m/s(?![A-Za-z\d/])", text) and not re.search(r"던[져지진질졌짐]|throw|toss|launch", text, re.I):
                continue
            return True
    return False

_AUDIENCE = {
    "research": r"연구자|연구\s*수준|전문가|research",
    "university": r"대학(?:생|교|원|\s*수준)?|전공자|university|undergraduate",
    "school": r"중학|고등학|중고등|중학생|고등학생|교과서|high\s*school",
    "intro": r"초등|입문|어린이|유치원|쉽게|아주\s*쉽|beginner|simply",
}
_EXPLAIN = re.compile(r"왜|이유|원리|해석|설명|결과|그래프|어떻게\s*(?:돼|되|나)|why|explain|interpret|result", re.I)
_REFERENCE = re.compile(r"결과|그래프|실험|물체|공식|이론|오차|에너지|힘|시간|속도|다르|같[아은지]|그[럴런렇래]|이[럴런렇래]|"
                        r"(?:^|\s)(?:왜|이유|설명|해석)(?:해\s*줘|해줘|해|지|야|요)?[?.!\s]*$|"
                        r"why\s+(?:is\s+that|are\s+they)|the\s+(?:result|graph|experiment)|^\s*(?:why|explain)[?!.\s]*$", re.I)
_CHANGE = re.compile(r"바꿔|바꾸|바꾼|변경|설정|늘[려리]|높여|높이(?:고|자|기|면|도록|세요|려)|올[려리]|크게|세게|더\s*무겁|줄[여이]|낮[춰추]|내[려리]|작게|짧게|길게|증가|감소|절반|반으로|[두세\d]\s*배|change|set\b|double|half|increase|decrease", re.I)
_FRESH = re.compile(r"새로|새\s*실험|처음부터|새로운|new\s*experiment", re.I)

_ALIASES = {
    **science_language.ALIASES,
    "mass_a": ["물체 A의 질량", "A의 질량", "A 질량", "질량 A", "물체 A", "첫 번째 물체", "첫 물체"],
    "mass_b": ["물체 B의 질량", "B의 질량", "B 질량", "질량 B", "물체 B", "두 번째 물체", "둘째 물체"],
    "mass": ["질량", "무게", "mass"], "height": ["높이", "낙하 거리", "height"],
    "g": ["중력 가속도", "중력가속도", "중력"], "x0": ["초기 위치", "초기 변위", "변위", "위치"],
    "v0": ["초기 속도", "초속", "처음 속력", "속도", "속력"], "a": ["가속도"],
    "force": ["알짜힘", "힘", "순힘"], "mu": ["운동 마찰 계수", "마찰 계수", "마찰계수"],
    "v_a": ["A의 속도", "A 속도", "속도 A"], "v_b": ["B의 속도", "B 속도", "속도 B"],
    "gap": ["두 물체 사이 거리", "초기 간격", "간격"], "restitution": ["반발 계수", "반발계수"],
    "k": ["용수철 상수", "스프링 상수", "탄성 계수"], "length": ["실의 길이", "줄 길이", "길이"],
    "angle": ["진폭각", "각도", "각"], "damping": ["감쇠 계수", "감쇠계수", "감쇠 상수"],
    "radius": ["반지름", "반경"], "omega": ["각속도"], "density": ["밀도"], "depth": ["깊이", "수심"],
    "p0": ["수면 압력", "표면 압력", "기준 압력", "대기압"], "volume": ["부피", "체적", "밀어낸 부피", "displaced volume"],
    "area_in": ["입구 단면적", "입구 면적"], "area_out": ["출구 단면적", "출구 면적"],
    "speed_in": ["입구 속력", "입구 속도", "입구 유속"], "duration": ["실험 시간", "측정 시간", "재생 시간", "관찰 시간", "총 시간", "시간"],
    "dt": ["시간 간격", "시간 스텝", "시간 간격폭", "시간 단계", "스텝 크기"],
}


def _norm(s):
    return unicodedata.normalize("NFKC", s).replace("−", "-").replace("^2", "2").replace("^3", "3")


# Unit dimensions are compared to the catalog variable's unit before applying a scale.
_SCALES = {
    **science_language.SCALES,
    "kg": {"kg": 1, "킬로그램": 1, "g": .001, "그램": .001},
    "m": {"m": 1, "미터": 1, "cm": .01, "센티미터": .01, "mm": .001, "밀리미터": .001, "km": 1000},
    "m/s": {"m/s": 1, "cm/s": .01, "km/h": 1 / 3.6}, "m/s2": {"m/s2": 1, "cm/s2": .01},
    "s": {"s": 1, "초": 1, "ms": .001, "밀리초": .001, "분": 60, "min": 60},
    "rad": {"rad": 1, "라디안": 1, "도": math.pi / 180, "°": math.pi / 180, "deg": math.pi / 180},
    "rad/s": {"rad/s": 1, "deg/s": math.pi / 180}, "N": {"N": 1, "뉴턴": 1},
    "N/m": {"N/m": 1}, "N·s/m": {"N·s/m": 1, "N*s/m": 1, "kg/s": 1},
    "kg/s": {"kg/s": 1, "N·s/m": 1, "N*s/m": 1}, "kg/m3": {"kg/m3": 1, "g/cm3": 1000},
    "Pa": {"Pa": 1, "kPa": 1000, "hPa": 100, "MPa": 1e6},
    "m2": {"m2": 1, "cm2": .0001, "mm2": .000001},
    "m3": {"m3": 1, "cm3": .000001, "L": .001, "리터": .001, "mL": .000001},
}
_UNITS = {unit for group in _SCALES.values() for unit in group} | {"%", "배"}
_UNIT = re.compile("(?:" + "|".join(map(re.escape, sorted(_UNITS, key=len, reverse=True))) + r")(?![a-zA-Z0-9/*^·])")
_NUMBER = re.compile(r"(?<![A-Za-z_0-9.])[+-]?(?:\d+(?:\.\d+)?|\.\d+)(?:[Ee][+-]?\d+)?")
_LINK = re.compile(r"(?:[\s=:]|을|를|은|는|이|가|의|값|약|만|으로|로|부터)*")
_METHODS = {"semi_implicit": r"반\s*암시적|심플렉틱|semi[_ -]implicit", "rk4": r"rk4|룽게\s*쿠타",
            "euler": r"오일러|euler", "analytic": r"해석해|해석적|analytic"}


def _mentions(text, spec):
    phrases = {}
    for key, label in [(v.key, v.label) for v in spec.variables] + [("dt", "dt"), ("duration", "duration")]:
        for phrase in [key, label, *_ALIASES.get(key, [])]:
            # Single-letter SI symbols inside a number-unit pair are not variable names.
            p = re.escape(_norm(phrase)).replace(r"\ ", r"\s*")
            if phrase.isascii():
                p = r"(?<![A-Za-z_0-9])" + p + r"(?![A-Za-z_0-9])"
                if len(phrase) == 1:
                    p += r"(?=\s*[=:])"
            phrases[p] = key
    ordered = sorted(phrases, key=len, reverse=True)
    pattern = "|".join(f"(?P<p{i}>{p})" for i, p in enumerate(ordered))
    return [(m.start(), m.end(), phrases[ordered[int(m.lastgroup[1:])]]) for m in re.finditer(pattern, text, re.I)]


def _near_key(start, end, mentions, text):
    for left, right, key in reversed(mentions):
        if right <= start and _LINK.fullmatch(text[right:start]):
            return key
    for left, right, key in mentions:
        if left >= end and _LINK.fullmatch(text[end:left]):
            return key
    return None


def _method(text):
    # Korean “해석해 줘” asks for an interpretation. “해석해로” selects an analytic solution.
    text = re.sub(r"해석해\s*(?:줘|주세요|봐|달라|줄래)|(?:결과|측정값|그래프)(?:를|을)?\s*해석해(?=[.!?\s]*$)", "", text)
    for name, pattern in _METHODS.items():
        if re.search(pattern, text, re.I):
            return name
    return None


class _Unclear(ValueError):
    pass


def _quantities(text):
    result = []
    consumed = 0
    for number in _NUMBER.finditer(text):
        if number.start() < consumed:
            continue
        tail = text[number.end():].lstrip()
        if re.match(r"(?:법칙|차원)", tail) or re.match(r"차\s*(?:룽게|런게|Runge)", tail, re.I):
            continue
        unit = _UNIT.match(tail)
        value = float(number[0])
        if not math.isfinite(value):
            raise _Unclear()
        if not unit:
            if re.match(r"[A-Za-z/%°^·]|(?:[.,]\d)", tail):
                raise _Unclear()
            if re.match(r"[가-힣]", tail) and not re.match(r"(?:으로|로|까지|에서|만큼|동안|씩|와|과|인|일\s*때|보다|또는|이고|이며|하고|설정|변경|늘려|줄여)", tail):
                raise _Unclear()
        end = number.end() if not unit else len(text) - len(tail) + unit.end()
        consumed = end
        result.append((number.start(), end, value, unit[0] if unit else ""))
    return result


def _scaled(value, unit, target):
    if not unit or unit == target:
        return value
    conversions = _SCALES.get(target, {})
    if unit not in conversions:
        raise _Unclear()
    return value * conversions[unit]


def _relative(text, initial, smallest_change):
    if re.search(r"절반|반으로|half", text, re.I):
        return initial / 2
    if re.search(r"(?:두|2)\s*배|double", text, re.I):
        return initial * 2
    if re.search(r"(?:세|3)\s*배", text):
        return initial * 3
    step = max(abs(initial) * .5, smallest_change)
    if re.search(r"크게|늘[려리]|높여|높이(?:고|자|기|면|도록|세요|려)|올[려리]|세게|무겁게|길게|증가|increase", text, re.I):
        return initial + step
    if re.search(r"작게|줄[여이]|낮[춰추]|내[려리]|가볍게|짧게|감소|decrease", text, re.I):
        return initial - step
    raise _Unclear()


def _parse_patch(text, spec, previous):
    text = _norm(text)
    text = re.sub(r"두\s*배", "2배", text)
    text = re.sub(r"세\s*배", "3배", text)
    text = re.sub(r"절반|반(?=으로)", "0.5배", text)
    units = {v.key: _norm(v.unit) for v in spec.variables} | {"duration": "s", "dt": "s"}
    initial = ({v.key: v.default for v in spec.variables} if previous is None else dict(previous.values))
    initial.update(duration=previous.duration if previous else spec.duration, dt=previous.dt if previous else spec.dt)
    steps = {v.key: v.step for v in spec.variables} | {"duration": .1, "dt": .002}
    mentions = _mentions(text, spec)
    if "mass_b" in units:
        units["mass_gap"] = "kg"
        initial["mass_gap"] = abs(initial["mass_b"] - initial["mass_a"])
        steps["mass_gap"] = steps["mass_b"]
        mentions.extend((m.start(), m.end(), "mass_gap") for m in _MASS_GAP.finditer(text))
        mentions.sort()
    numbers = _quantities(text)
    edits = {}
    observed_acceleration = None
    pairs = {("mass_a","mass_b"): [], ("temp_a","temp_b"): [], ("capacity_a","capacity_b"): []}
    for start, end, value, unit in numbers:
        if spec.model == "newton" and unit in _SCALES["m/s2"]:
            if observed_acceleration is not None:
                raise _Unclear()
            observed_acceleration = _scaled(value, unit, "m/s2")
            continue
        key = _near_key(start, end, mentions, text)
        if unit == "s" or unit == "초":
            if not key and re.match(r"\s*동안", text[end:]):
                key = "duration"
        if not key and {"area_in", "area_out"} <= units.keys():
            # Inlet and outlet qualify both an area and a speed. The unit fixes the role.
            site = re.search(r"(입구|출구|inlet|outlet)(?:에서|가|는|의|가진|면적)?\s*$", text[:start], re.I)
            if not site:
                site = re.match(r"\s*(?:인\s*)?(입구|출구|inlet|outlet)", text[end:], re.I)
            if site:
                inlet = site[1].lower() in {"입구","inlet"}
                if unit in _SCALES["m2"]:
                    key = "area_in" if inlet else "area_out"
                elif unit in _SCALES["m/s"] and inlet:
                    key = "speed_in"
        if not key and spec.model == "buoyancy" and unit in _SCALES["m3"] and re.search(
                r"밀어\s*(?:내|낸|냈)|잠[겨긴]|displac|submerg", text, re.I):
            key = "volume"
        if not key and spec.model == "newton":
            if unit in _SCALES["N"]:
                key = "force"
            elif unit in _SCALES["kg"]:
                key = "mass"
        pair = next((p for p in pairs if set(p) <= units.keys() and unit in _SCALES.get(units[p[0]], {})), None)
        if not key and pair:
            pairs[pair].append(_scaled(value, unit, units[pair[0]]))
            continue
        if not key and unit and not mentions:
            options = [k for k, u in units.items() if unit in _SCALES.get(u, {})]
            # A leading measurement can identify the single compatible model parameter,
            # including a named new experiment such as “4.905 m 자유낙하”.
            if len(options) == 1 and re.fullmatch(r"\s*(?:그러면|그럼|그걸)?\s*", text[:start]):
                key = options[0]
        if not key or key in edits:
            raise _Unclear()
        if unit == "배":
            edits[key] = initial[key] * value
        elif unit == "%":
            # Percentages here describe explicit relative changes to a parameter.
            direction = _relative(text[end:], 1, .1) - 1
            edits[key] = initial[key] * (1 + math.copysign(value / 100, direction))
        else:
            amount = _scaled(value, unit, units[key])
            delta = re.match(r"\s*(?:만큼\s*)?(?:더\s*)?(늘려|높여|올려|줄여|낮춰|내려|증가|감소)", text[end:])
            if delta:
                amount = initial[key] + (-amount if delta[1] in {"줄여", "낮춰", "내려", "감소"} else amount)
            edits[key] = amount
    for pair, loose in pairs.items():
        if not loose:
            continue
        remaining = [key for key in pair if key not in edits]
        if len(loose) != len(remaining):
            raise _Unclear()
        edits.update(zip(remaining, loose))
    if observed_acceleration is not None:
        if "mass" not in edits:
            raise _Unclear()
        required_force = edits["mass"] * observed_acceleration
        if "force" in edits and not math.isclose(edits["force"], required_force, rel_tol=1e-9, abs_tol=1e-12):
            raise _Unclear()
        edits["force"] = required_force
    method = _method(text)
    if not numbers and _CHANGE.search(text):
        keys = {m[2] for m in mentions}
        if len(keys) == 1:
            key, = keys
            edits[key] = _relative(text, initial[key], steps[key])
        elif keys and not method:
            raise _Unclear()
    if "mass_gap" in edits:
        gap = edits.pop("mass_gap")
        if "mass_b" in edits or "mass_a" in edits or gap < 0:
            raise _Unclear()
        sign = initial["mass_b"] - initial["mass_a"] or 1
        edits["mass_b"] = initial["mass_a"] + math.copysign(gap, sign)
    if spec.model == "collision":
        _collision_condition(text, edits)
    if spec.model == "friction" and _NO_FRICTION.search(text):
        if edits.get("mu", 0) != 0:
            raise _Unclear()
        edits["mu"] = 0
    if spec.model == "damped" and _NO_DAMPING.search(text):
        if edits.get("damping", 0) != 0:
            raise _Unclear()
        edits["damping"] = 0
    return Patch(method=method, duration=edits.pop("duration", None), dt=edits.pop("dt", None), values=edits)


def _collision_condition(text, edits):
    inelastic = re.search(r"비\s*탄성|inelastic", text, re.I)
    stuck = re.search(r"완전(?:히)?\s*비\s*탄성|perfectly\s+inelastic|붙(?:어(?:서|\s*움직|\s*가|\s*이동|\s*다니)|는|는다)|한\s*덩어리|stick\s+together", text, re.I)
    elastic = not inelastic and re.search(r"탄성\s*충돌|\belastic\s*collision", text, re.I)
    value = edits.get("restitution")
    if stuck and elastic or inelastic and not stuck and (value is None or value >= 1):
        raise _Unclear()
    if stuck or elastic:
        required = 0 if stuck else 1
        if value is not None and value != required:
            raise _Unclear()
        edits["restitution"] = required


def _has_patch(patch):
    return bool(patch.values or patch.method or patch.dt is not None or patch.duration is not None)


def _local(text, current, level, catalog):
    lookup = _NO_DAMPING.sub("", _NO_FRICTION.sub("", text))
    models = [m for m, pattern in _MODELS.items() if m in catalog and re.search(pattern, lookup, re.I)]
    if not models and re.search(r"가속도|acceleration", lookup, re.I) and re.search(r"\d\s*(?:N|뉴턴)\b|\d\s*N(?=[가-힣])", lookup):
        models.append("newton")
    models = science_language.resolve_field_terms(models, lookup)
    if "damped" in models and "spring" in models:
        models.remove("spring")
    if "circular" in models and "uniform" in models:
        models.remove("uniform")
    if len(models) > 1:
        return _decline(level)
    model = next(iter(models), None)
    if model is None:
        model = next((m for m, spec in catalog.items() if spec.title in text or re.search(r"\b" + re.escape(m) + r"\b", text, re.I)), None)
    chosen = model or (current.model if current else None)
    if chosen is None or chosen not in catalog:
        return _decline(level)
    new = current is None or chosen != current.model or _FRESH.search(text)
    level_only = re.fullmatch(r"(?:그럼\s*|그러면\s*)?(?:연구자|전문가|대학(?:생|원)?|고등학생?|중학생?|초등학생?|입문자?)"
                              r"(?:를?\s*위한|도\s*알\s*수\s*있는)?\s*(?:수준|모드|난이도)?(?:으?로|에게)?\s*"
                              r"(?:바꿔|변경|설명|해\s*줘|다시\s*설명)?(?:해\s*줘|해줘|줘)?[.!?\s]*", text)
    if not new and level_only:
        return Intent(action="explain", model=chosen, patch=Patch(), level=level)
    try:
        patch = _parse_patch(text, catalog[chosen], None if new else current)
        if new or _has_patch(patch):
            build(catalog[chosen], UUID(int=0), patch, None if new else current)
            return Intent(action="create" if new else "modify", model=chosen, patch=patch, level=level)
    except (ValueError, ValidationError):
        return _decline(level, _CONDITIONS)
    if model or (_EXPLAIN.search(text) and (_REFERENCE.search(text) or _mentions(text, current))):
        return Intent(action="explain", model=chosen, patch=Patch(), level=level)
    return _decline(level)


_CREATE_REQUEST = re.compile(r"새\s*실험|새로|만들어|만들자|생성해|생성하|시뮬레이션해|\b(?:create|build|simulate|set up)\b", re.I)
_DENY_CHANGE = re.compile(r"(?:바꾸|변경하|조정하|수정하|생성하|만들|늘리|줄이|높이)지\s*(?:말|마|않)|"
                         r"(?:그대로|유지(?:해|하)[^.!?]{0,12})\s*(?:두고|두세요|설명)|"
                         r"\b(?:do not|don't|never)\s+(?:change|modify|create|set|adjust)\b", re.I)


def _check_requested_patch(action, model, patch, known, current, catalog, text):
    """Require independent evidence for the operation and every field a provider wants to write."""
    if _DENY_CHANGE.search(text):
        raise ProviderError("AI가 사용자가 유지하라고 한 실험 조건을 바꾸려 했습니다.")
    if known.model:
        explicit_create = action == "create" and _CREATE_REQUEST.search(text)
        if action != known.action and not explicit_create:
            raise ProviderError("AI가 질문과 다른 실험 동작을 제안했습니다.")
    elif action == "create" and current and not _CREATE_REQUEST.search(text):
        raise ProviderError("새 실험을 만들려면 실험 이름과 생성 요청을 함께 적어 주세요.")

    previous = current if action == "modify" else None
    try:
        expected = _parse_patch(text, catalog[model], previous)
    except ValueError:
        raise ProviderError("질문에서 변경할 변수와 조건을 확인할 수 없습니다.") from None
    if patch.values.keys() != expected.values.keys() or patch.method != expected.method:
        raise ProviderError("AI가 요청에 없는 변수나 적분 방법을 변경하거나 요청한 변경을 누락했습니다.")
    initial = dict(previous.values) if previous else {v.key: v.default for v in catalog[model].variables}
    initial.update(dt=previous.dt if previous else catalog[model].dt,
                   duration=previous.duration if previous else catalog[model].duration)
    precise = bool(_NUMBER.search(text) or re.search(r"[두세]\s*배|절반|반으로|\b(?:double|half)\b", text, re.I))
    qualitative = not precise and _CHANGE.search(text)
    if qualitative and "mass_b" in expected.values and _MASS_GAP.search(text):
        old_gap = abs(initial["mass_a"] - initial["mass_b"])
        target_gap = abs(initial["mass_a"] - expected.values["mass_b"])
        new_gap = abs(initial["mass_a"] - patch.values["mass_b"])
        if (target_gap - old_gap) * (new_gap - old_gap) <= 0 and not math.isclose(new_gap, target_gap):
            raise ProviderError("AI가 요청과 다른 방향으로 질량 차이를 바꾸려 했습니다.")
    targets = {**expected.values, "duration": expected.duration, "dt": expected.dt}
    proposals = {**patch.values, "duration": patch.duration, "dt": patch.dt}
    for key, target in targets.items():
        value = proposals[key]
        if value is None and target is None:
            continue
        if value is not None and target is not None:
            if math.isclose(value, target, rel_tol=1e-9, abs_tol=1e-12):
                continue
            # A qualitative request, e.g. “make B heavier”, permits multiple magnitudes.
            if qualitative and (value - initial[key]) * (target - initial[key]) > 0:
                continue
        raise ProviderError("AI가 질문에 지정한 수치나 변화 방향과 다른 값을 제안했습니다.")


def _checked(candidate, current, catalog, text, level=None):
    action, model, patch = candidate.action, candidate.model, candidate.patch
    if level is not None and candidate.level != level:
        raise ProviderError("AI가 요청에 없는 학습 수준 변경을 제안했습니다.")
    if action == "unsupported" and model is None and not _has_patch(patch):
        return _decline(candidate.level)
    valid = model in catalog and (action == "create" or (current and model == current.model))
    if (not valid or action == "unsupported" or action == "modify" and not _has_patch(patch)
            or action == "explain" and _has_patch(patch)):
        raise ProviderError("AI가 현재 실험에 적용할 수 없는 변경을 제안했습니다.")
    try:
        resulting = build(catalog[model], UUID(int=0), patch, current if action != "create" else None)
        # Named classroom conditions must hold even if the model omitted an input.
        constraints = dict(resulting.values)
        if model == "collision":
            _collision_condition(text, constraints)
        if model == "friction" and _NO_FRICTION.search(text) and constraints["mu"] != 0:
            raise _Unclear()
        if model == "damped" and _NO_DAMPING.search(text) and constraints["damping"] != 0:
            raise _Unclear()
        # Check explicit variable/unit pairs independently of the provider's conversion.
        mentions = _mentions(text, catalog[model])
        units = {v.key: _norm(v.unit) for v in catalog[model].variables} | {"dt": "s", "duration": "s"}
        if mentions:
            for start, end, value, unit in _quantities(text):
                key = _near_key(start, end, mentions, text)
                if key and unit not in {"", "%", "배"}:
                    _scaled(value, unit, units[key])
    except ValueError:
        raise ProviderError("AI가 허용된 변수, 단위 또는 범위를 벗어나는 변경을 제안했습니다.") from None
    known = _local(text, current, candidate.level, catalog)
    if known.model and known.model != model:
        raise ProviderError("AI가 질문에 지정된 실험과 다른 모델을 선택했습니다.")
    if action in {"modify", "create"}:
        _check_requested_patch(action, model, patch, known, current, catalog, text)
    return Intent(**candidate.model_dump())


async def plan(message: str, current: Experiment | None, level: Level, catalog: dict[str, ModelSpec]) -> Intent:
    text = _norm(message).strip()
    level = next((name for name, pattern in _AUDIENCE.items() if re.search(pattern, text, re.I)), level)
    if not text or _OUTSIDE.search(_IDEAL_AIR.sub("", text)) or _outside_model(text, current):
        return _decline(level)
    name = provider_name()
    if name == "mock":
        return _local(text, current, level, catalog)
    candidate = await request_candidate(name, message, current, level, catalog)
    return _checked(candidate, current, catalog, text, level)


_CONCEPT = {
    **science_language.CONCEPTS,
    "free_fall": "공기 저항이 없을 때 물체를 아래로 끌어당기는 힘은 질량에 비례합니다. 그 힘을 질량으로 나눈 가속도는 두 물체에서 같아요.",
    "uniform": "속도가 일정하면 같은 시간마다 같은 거리만큼 이동합니다. 위치 그래프의 기울기가 속도입니다.",
    "acceleration": "가속도는 매초 속도가 얼마나 변하는지를 나타냅니다. 위치 그래프의 기울기는 순간 속도를 보여 줍니다.",
    "newton": "같은 힘을 가하면 질량이 클수록 가속도가 작아집니다. 힘의 방향은 가속도의 부호로 확인할 수 있습니다.",
    "friction": "움직이는 물체에 작용하는 운동 마찰력은 속도와 반대 방향입니다. 마찰 계수가 클수록 물체의 속력이 빠르게 줄어듭니다.",
    "collision": "수평 외력이 없는 두 물체 사이의 충돌에서는 운동량의 합이 보존됩니다. 반발 계수는 충돌 뒤 두 물체가 벌어지는 상대 속력을 정합니다.",
    "spring": "용수철은 늘어나거나 줄어든 길이에 비례하는 힘으로 물체를 평형 위치 쪽으로 당기거나 밉니다.",
    "pendulum": "추를 옆으로 당겼다 놓으면 줄의 접선 방향으로 작용하는 중력 성분이 추를 최저점 쪽으로 움직입니다. 줄의 길이와 출발 각도가 주기에 영향을 줍니다.",
    "damped": "점성 감쇠력은 속도와 반대 방향으로 작용합니다. 감쇠 계수가 양수이면 움직이는 물체의 역학적 에너지가 줄어듭니다.",
    "circular": "원의 접선 방향으로 움직이는 물체에 중심을 향한 가속도가 작용하면 속도의 방향이 계속 바뀝니다.",
    "hydrostatic": "가만히 있는 액체에서는 위쪽 액체의 무게 때문에 깊은 곳의 압력이 높습니다.",
    "buoyancy": "완전히 잠긴 물체에는 밀어낸 유체의 무게만큼 위쪽으로 부력이 작용합니다. 물체를 정지시킨 지지력까지 합하면 알짜힘은 0입니다. 지지력의 양수는 위쪽을 뜻합니다.",
    "continuity": "새거나 쌓이는 유체가 없으면 입구와 출구를 매초 통과하는 부피가 같습니다. 단면적이 좁은 곳에서는 유속이 커집니다.",
}
# These labels distinguish measurements from reference predictions; only present keys are rendered.
_FACT_LABELS = {
    **science_language.FACTS,
    "arrival_time": ("두 물체의 바닥 도착 시간", "s"), "impact_speed": ("도착 순간 속력", "m/s"),
    "collision_time": ("충돌 시각", "s"), "final_velocity_a": ("A의 마지막 속도", "m/s"),
    "final_velocity_b": ("B의 마지막 속도", "m/s"), "energy_loss": ("운동 에너지 감소량", "J"),
    "stop_time": ("정지 시각", "s"), "stop_distance": ("정지할 때까지 이동한 거리", "m"),
    "measured_period": ("측정 주기", "s"), "reference_period": ("이론 주기", "s"),
    "dissipated_energy": ("누적 소산 에너지", "J"), "centripetal_acceleration": ("이론 구심 가속도", "m/s²"),
    "reference_speed": ("이론 속력", "m/s"), "acceleration": ("가속도", "m/s²"),
    "final_velocity": ("마지막 속도", "m/s"), "final_position": ("마지막 위치", "m"),
    "pressure": ("절대압", "Pa"), "gauge_pressure": ("게이지압", "Pa"),
    "buoyancy": ("부력의 크기", "N"), "weight": ("무게의 크기", "N"), "support": ("위쪽 기준 지지력", "N"),
    "flow": ("체적 유량", "m³/s"), "outlet_speed": ("출구 유속", "m/s"),
    "reference_arrival_time": ("이론 도착 시간", "s"), "total_momentum": ("총운동량", "kg·m/s"),
    "impulse": ("충돌 충격량 크기", "N·s"), "damping_ratio": ("감쇠비", "1"),
    "spectral_radius": ("증폭 행렬 스펙트럼 반경", "1"),
}
_QUANTITIES = {"x": "수평 위치", "y": "높이", "angle": "각도", "pressure": "압력", "buoyancy": "부력",
               "flow": "체적 유량", "speed": "유속", "net_force": "알짜힘", "vx": "수평 속도"}
_ABSENT = {
    "free_fall": ("arrival_time", "관찰 구간에서 바닥 도착 시각은 측정되지 않았습니다."),
    "collision": ("collision_time", "관찰 구간에서 두 물체의 충돌은 기록되지 않았습니다."),
    "friction": ("stop_time", "관찰 구간에서 물체의 정지는 기록되지 않았습니다."),
    "pendulum": ("measured_period", "이 관찰 구간의 측정값으로는 주기를 확인할 수 없습니다."),
    "spring": ("measured_period", "이 관찰 구간의 측정값으로는 주기를 확인할 수 없습니다."),
    "damped": ("measured_period", "이 관찰 구간의 측정값으로는 주기를 확인할 수 없습니다."),
}

_INTRO = {
    **science_language.CONCEPTS,
    "free_fall": "두 공을 나란히 들고 손을 동시에 펴 보세요. 공기를 빼면 매초 두 공의 빠르기가 똑같이 늘어요. 무거운 공도 먼저 출발하지 않아요.",
    "uniform": "장난감 기차가 같은 빠르기로 달려요. 1초마다 바닥에 점을 찍으면 점 사이의 간격이 모두 같아요.",
    "acceleration": "구르는 장난감에 1초마다 표시를 해 보세요. 앞으로 가면서 점점 빨라진다면 표시 사이가 넓어져요.",
    "newton": "빈 수레와 짐을 실은 수레를 같은 힘으로 밀어 보세요. 가벼운 수레의 빠르기가 더 많이 바뀌어요.",
    "friction": "바닥을 따라 미끄러지는 지우개를 떠올려 보세요. 마찰은 지우개가 가는 쪽과 반대쪽으로 밀어요.",
    "collision": "한 줄로 달리는 두 장난감 수레가 부딪혀요. 두 수레가 서로 얼마나 튀어 나가는지 속도를 살펴보세요.",
    "spring": "늘였던 용수철 끝을 놓으면 가운데로 끌려와요. 가운데를 지나쳐 반대쪽으로 가면 힘의 방향도 바뀌어요.",
    "pendulum": "그네를 옆에서 살짝 놓으면 가장 낮은 곳을 향해 내려와요. 한 번 갔다가 처음 자리로 돌아오는 데 걸린 시간이 주기예요.",
    "damped": "용수철에 매단 추를 끈적한 액체 속에서 흔든다고 생각해 보세요. 움직임을 방해하는 힘이 있으면 흔들림이 점차 잦아들어요.",
    "circular": "실 끝에 달린 구슬을 원을 그리며 돌려요. 구슬이 지나가는 방향은 계속 바뀌고, 실이 당기는 방향은 가운데를 향해요.",
    "hydrostatic": "수영장에서 물속으로 내려갈수록 위에 있는 물기둥이 길어져요. 같은 넓이를 누르는 힘도 커져요.",
    "buoyancy": "물속에 공을 완전히 잠기게 하고 손으로 붙잡고 있어요. 물이 위로 미는 힘과 무게가 다르면 손도 힘을 주어야 해요.",
    "continuity": "호스의 넓은 부분과 좁은 부분을 지나가는 물을 떠올려 보세요. 같은 양의 물이 좁은 곳을 통과하려면 더 빨라야 해요.",
}
_DERIVE = {
    **science_language.CONCEPTS,
    "free_fall": "수직 아래 방향으로 ma = mg를 쓰면 a = g입니다. 정지 상태에서 시간에 대해 두 번 적분하면 낙하 거리 h = gt²/2, 이론 도착 시간 t = √(2h/g)를 얻습니다.",
    "uniform": "ΣF = 0을 m으로 나누면 dv/dt = 0입니다. 일정한 v₀를 적분해 x(t) − x₀ = v₀t를 얻습니다.",
    "acceleration": "dv/dt = a를 적분해 v = v₀ + at를 얻고, v를 적분해 x − x₀ = v₀t + at²/2를 얻습니다.",
    "newton": "ΣF = ma로부터 a = F/m입니다. F dx를 궤적을 따라 적분하면 m v dv의 적분과 같아 FΔx = ΔK를 얻습니다.",
    "friction": "수평면에서 N = mg이고 운동 마찰력의 크기는 μmg입니다. μ > 0일 때 초기 운동 에너지를 마찰의 일로 소모하므로 μmgd = mv₀²/2입니다.",
    "collision": "외부 충격량이 0이므로 ΔpA + ΔpB = 0입니다. 여기에 충돌 뒤 상대 속력을 정하는 반발 계수 식을 연립하면 두 최종 속도를 구합니다.",
    "spring": "뉴턴 법칙과 복원력을 결합하면 ẍ + (k/m)x = 0입니다. 각진동수 ω = √(k/m)에서 T = 2π/ω를 얻습니다.",
    "pendulum": "회전축 주위 토크 −mgL sin θ와 관성 모멘트 mL²를 쓰면 θ̈ = −(g/L)sin θ입니다. 유한 진폭에서는 에너지 적분으로 주기를 구합니다.",
    "damped": "mẍ + bẋ + kx = 0에 속도 ẋ를 곱하면 d(mẋ²/2 + kx²/2)/dt = −bẋ²입니다. 이를 적분하면 초기 에너지와 누적 소산량을 비교할 수 있습니다.",
    "circular": "r⃗ = R(cos ωt, sin ωt)를 한 번 미분하면 접선 속도, 두 번 미분하면 중심을 향한 a⃗ = −ω²r⃗를 얻습니다.",
    "hydrostatic": "아래쪽 깊이 h를 양으로 두면 얇은 유체층의 힘 평형에서 dp/dh = ρg입니다. 수면부터 적분하면 p = p₀ + ρgh입니다.",
    "buoyancy": "물체 표면의 정수압을 적분하면 위쪽 부력 B = ρgV가 됩니다. 정지 조건 B + F지지 − mg = 0으로부터 F지지 = mg − B입니다.",
    "continuity": "정상 유동에서 단위 시간에 통과하는 질량은 ρAv입니다. 비압축성 유체의 일정한 ρ를 양변에서 소거하면 A₁v₁ = A₂v₂입니다.",
}


def _observations(exp, run):
    entries = [f"{label} {run.facts[key]:.4g} {unit}" for key, (label, unit) in _FACT_LABELS.items() if key in run.facts]
    if exp.model == "free_fall":
        entries.insert(0, f"질량 A {exp.values['mass_a']:g} kg, B {exp.values['mass_b']:g} kg")
        if "arrival_time" not in run.facts:
            for i, obj in enumerate(exp.objects):
                ys = run.series.get(f"{i}.y")
                if ys:
                    entries.append(f"{obj}의 마지막 높이 {ys[-1]:.4g} m")
    if not entries:
        for key, values in run.series.items():
            index, _, quantity = key.partition(".")
            if values and quantity in _QUANTITIES and quantity in exp.measurements and index.isdigit() and int(index) < len(exp.objects):
                entries.append(f"{exp.objects[int(index)]}의 마지막 {_QUANTITIES[quantity]} {values[-1]:.4g} {exp.measurements[quantity]}")
                if len(entries) >= 2:
                    break
    return ", ".join(entries[:4])


def _teaching_sections(exp, run, level):
    failed = [check for check in run.checks if not check.passed]
    required = []
    options = {}
    if failed:
        required.append("검산에서 허용 범위를 벗어났습니다. " + " / ".join(f"{c.label} ({c.detail})" for c in failed) + ".")
    if run.status != "VERIFIED":
        required.append(f"이 실행의 검증 상태는 {run.status}입니다.")
    options["assumptions"] = "적용 조건은 " + ", ".join(exp.assumptions[:2] if level in {"intro", "school"} else exp.assumptions) + "입니다."
    numerical_note = ""
    if exp.method != "analytic" and any(key.endswith(".error") for key in run.series):
        numerical_note = ("수치 오차는 같은 초기 조건과 같은 방정식의 기준해에서 얼마나 벗어났는지 나타냅니다. "
                          "시간 간격을 줄여 비교할 수 있습니다. 실제 장치에 대한 모델의 정확도는 "
                          + ", ".join(exp.assumptions[:2]) + " 등의 가정이 성립하는지에 달려 있습니다.")
    if run.status in {"FAILED", "UNSUPPORTED", "UNVERIFIED"}:
        if numerical_note:
            required.append(numerical_note)
        required.append(f"이 결과로는 실험의 결론을 확인할 수 없습니다. 모델의 기준식은 {exp.formula}입니다.")
        if run.times:
            required.append(f"마지막 유한 표본의 시각은 {run.times[-1]:.4g} s입니다.")
        else:
            required.append("유한한 측정 표본이 없습니다.")
        return required, options
    obs = _observations(exp, run)
    if obs:
        required.append(f"이번 실행에서 기록한 값은 {obs}입니다.")
    absent = _ABSENT.get(exp.model)
    if absent and absent[0] not in run.facts:
        required.append(absent[1])
    teaching = _INTRO if level == "intro" else _DERIVE if level in {"university", "research"} else _CONCEPT
    options["principle"] = teaching.get(exp.model, exp.goal) + f" 모델식은 {exp.formula}입니다."
    options["comparison"] = exp.comparison
    if run.checks:
        summary = f"계산 방법 {exp.method}, 설정 Δt {exp.dt:g} s, 출력 표본 {len(run.times)}개."
        errors = [row for row in run.convergence if {'dt', 'error'} <= row.keys()]
        if errors:
            summary += " 시간 간격별 최대 위치 편차는 " + ", ".join(f"Δt {row['dt']:.4g} s에서 {row['error']:.3g} m" for row in errors) + "입니다."
        else:
            summary += " " + run.checks[0].label + " 검산값은 " + run.checks[0].detail + "입니다."
        options["verification"] = " ".join(item for item in [summary,numerical_note] if item)
    if exp.variables:
        options["next_question"] = f"다른 조건을 고정하고 ‘{exp.variables[0].label}’만 바꾸면 어떤 측정값이 달라질까요?"
    return required, options


def _render(required, options, selection, level):
    if any(key not in options for key in selection):
        raise ProviderError("AI가 이번 계산에서 사용할 수 없는 해설 항목을 선택했습니다.")
    order = list(selection)
    if "principle" in options and "principle" not in order:
        order.append("principle")
    if level == "research" and "verification" in options and "verification" not in order:
        order.append("verification")
    return "\n\n".join([*required, *(options[k] for k in order)])


def explain(exp: Experiment, run: Run, level: Level) -> str:
    required, options = _teaching_sections(exp, run, level)
    selection = [k for k in ("principle", "assumptions", "comparison") if k in options]
    if level == "intro":
        selection = selection[:1]
    return _render(required, options, selection, level)


async def interpret(message: str, exp: Experiment, run: Run, level: Level) -> str:
    from .classroom_units import unit_note
    unit_answer = unit_note(message, exp.model)
    name = provider_name()
    if name == "mock":
        return unit_answer or explain(exp, run, level)
    required, options = _teaching_sections(exp, run, level)
    evidence = dict(question=message[:2000], level=level, model=exp.model, inputs=exp.values,
                    status=run.status, facts=dict(list(run.facts.items())[:24]),
                    checks=[c.model_dump() for c in run.checks[:16]], convergence=run.convergence[:3],
                    sample_count=len(run.times), observation_end_s=run.times[-1] if run.times else None,
                    required_readout=required, available_sections=options)
    selection = await request_reading(name, evidence)
    rendered = _render(required, options, selection.sections, level)
    return (unit_answer + "\n\n" + rendered) if unit_answer else rendered
