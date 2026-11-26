"""Independent checks for retrievable text, registered formulas and a specific physics run."""
from bisect import bisect_right
from hashlib import sha256
import json
import math
import re
import unicodedata

from pydantic import Field

from .reasoning import _FACT_LABELS, _QUANTITIES
from .schema import Number, StrictModel


def format_value(value):
    """Four significant digits for evidence, with unrounded SI values retained for replay."""
    return format(value, ".4g") if value else "0"


def unit_spelling(unit):
    normalized = unicodedata.normalize("NFKC", unit).replace("⋅", "·").replace("*", "·").strip()
    return re.sub(r"(?<=[A-Za-z])\^(?=[23](?!\d))", "", normalized)


# Only synonyms for a named engine observation may be used to verify a numerical statement.
# Several labels can share a unit. A unit alone never identifies a particular observation.
FACT_ALIASES = {
    "arrival_time": ("낙하 시간", "바닥 도착 시간", "도착 시간", "fall time"),
    "impact_speed": ("충돌 직전 속력", "충돌 속력", "impact speed"),
    "acceleration": ("가속도", "acceleration"),
    "net_force": ("알짜힘", "합력", "net force"),
    "centripetal_acceleration": ("구심 가속도", "구심가속도", "centripetal acceleration"),
    "gauge_pressure": ("게이지압", "게이지 압력", "gauge pressure"),
    "pressure": ("절대 압력", "absolute pressure"),
    "equilibrium_temp": ("평형온도", "평형 온도", "equilibrium temperature"),
    "buoyancy": ("부력", "buoyant force"), "flow": ("유량", "flow rate"),
    "outlet_speed": ("출구 평균 속력", "출구 속도", "outlet speed"),
    "wave_speed": ("전파 속력", "파동 속력", "wave speed"),
    "energy_loss": ("운동 에너지 손실", "energy loss"),
    "stop_distance": ("정지 거리", "stopping distance"),
    "measured_period": ("측정 주기", "관측 주기"), "reference_period": ("이론 주기", "기준 주기"),
}


class NumberClaim(StrictModel):
    key: str = Field(min_length=1, max_length=72)
    value: Number
    unit: str = Field(max_length=32)
    experiment_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1, strict=True)
    run_id: str = Field(min_length=1, max_length=64)


def _fingerprint(snapshot, include_readouts):
    exp, run = snapshot.experiment, snapshot.run
    material = [str(exp.id), snapshot.revision, exp.model, exp.method, exp.duration, exp.dt,
                exp.values, run.status, run.facts, run.times[-1] if run.times else None]
    if include_readouts:
        material += [exp.measurements, {k:samples[-1] for k,samples in run.series.items() if samples}]
    return sha256(json.dumps(material, sort_keys=True, allow_nan=False).encode()).hexdigest()[:24]


def run_id(snapshot):
    return _fingerprint(snapshot, include_readouts=True)


def graph_observation_text(item, snapshot):
    index, _, quantity = item["reference"].partition(".")
    subject = snapshot.experiment.objects[int(index)]
    label = _QUANTITIES.get(quantity, quantity)
    display = ", ".join(f"{v['time']:.5g} s에서 {v['value']:.5g} {item['unit']}" for v in item["samples"])
    return f"강조한 구간에서 {subject}의 {label} 표본을 읽어 보세요. {display}입니다."


def graph_observation(snapshot, actions):
    """Read a validated graph selection directly from this engine run."""
    exp, run = snapshot.experiment, snapshot.run
    interval = next((a for a in actions if a["op"] == "highlight_graph"), None)
    if run.status != "VERIFIED" or not interval or not run.times:
        return None
    obj = next((a["index"] for a in actions if a["op"] == "highlight_object"), 0)
    quantity = interval["quantity"]
    reference = f"{obj}.{quantity}"
    values = run.series.get(reference, [])
    if not (0 <= obj < len(exp.objects) and quantity in exp.measurements
            and len(values) == len(run.times)
            and run.times[0] <= interval["start"] <= interval["end"] <= run.times[-1] + 1e-10):
        return None
    samples = []
    for boundary in ("start", "end"):
        i = bisect_right(run.times, interval[boundary]) - 1
        if samples and samples[-1]["index"] == i:
            continue
        if not math.isfinite(values[i]):
            return None
        samples.append({"index":i, "time":run.times[i], "value":values[i]})
    unit = exp.measurements[quantity]
    label = _QUANTITIES.get(quantity, quantity)
    item = {"label":label, "unit":unit, "reference":reference, "samples":samples,
            "status":"calculation_verified", "run_id":run_id(snapshot),
            "experiment_id":str(exp.id), "revision":snapshot.revision}
    return {**item, "text":graph_observation_text(item, snapshot)}


def reference_values(snapshot):
    exp, run = snapshot.experiment, snapshot.run
    values = {k: (label, run.facts[k], unit) for k, (label, unit) in _FACT_LABELS.items()
              if k in run.facts}
    if exp.model == "newton" and "acceleration" in run.facts:
        values["net_force"] = ("알짜힘", exp.values["mass"] * run.facts["acceleration"], "N")
    for series, samples in run.series.items():
        index, _, q = series.partition(".")
        if samples and index.isdigit() and int(index) < len(exp.objects) and q in exp.measurements:
            values["last." + series] = (f"{exp.objects[int(index)]} · 마지막 {q}", samples[-1], exp.measurements[q])
    return values


def check_number(claim, snapshot):
    """Four significant digits may be displayed. A wrong quantity, unit or run cannot pass."""
    ref = reference_values(snapshot).get(claim.key)
    result = claim.model_dump() | {"status":"failed", "label":ref[0] if ref else claim.key}
    stamp = run_id(snapshot)
    # Saved v0.3 reports remain auditable when their original input/fact hash matches;
    # values and units are always rechecked against the current reconstruction.
    legacy = claim.run_id != stamp and claim.run_id == _fingerprint(snapshot, include_readouts=False)
    if (claim.experiment_id != str(snapshot.experiment.id) or claim.revision != snapshot.revision
            or (claim.run_id != stamp and not legacy)):
        return result | {"reason":"실험 ID, 버전 또는 실행 지문이 다릅니다."}
    result["fingerprint_version"] = "0.3" if legacy else "0.3.1"
    if not ref:
        return result | {"status":"unverifiable","reason":"이 실행에는 해당 측정값이 없습니다."}
    label, expected, unit = ref
    result.update(expected=expected, expected_unit=unit, display_value=format_value(claim.value),
                  expected_display=format_value(expected))
    if unit_spelling(claim.unit) != unit_spelling(unit):
        return result | {"reason":"양의 SI 단위가 다릅니다."}
    if not math.isclose(claim.value, expected, rel_tol=5e-4, abs_tol=1e-10):
        return result | {"reason":"실제 계산값과 표시 반올림 허용 오차 안에서 일치하지 않습니다."}
    if snapshot.run.status != "VERIFIED":
        return result | {"status":"unverifiable", "reason":f"실행 상태가 {snapshot.run.status}여서 이 수치를 물리 예측으로 확인할 수 없습니다."}
    return result | {"status":"calculation_verified", "reason":"이 버전의 엔진 결과와 단위·수치가 일치합니다."}


def check_quote(store, retrieved, candidate):
    """A real title alone is never sufficient for verification."""
    row = next((r for r in retrieved if r["id"] == candidate.get("id")), None)
    if not row:
        return {"status":"insufficient","reason":"이 질문에서 검색된 문단이 아닙니다."}
    original = store.chunk(row["id"])
    if not original or not original.get("citable", False):
        return {"status":"insufficient","reason":"인용할 수 있는 원문이 없습니다."}
    quote = candidate.get("quote", "")
    if (not quote.strip() or len(quote) > 900 or quote not in original["text"]
            or quote not in row["text"] or any(candidate.get(k) != original[k] for k in ("doc_id","locator"))
            or any(row[k] != original[k] for k in ("doc_id","locator","text","url"))):
        return {"status":"failed","reason":"인용문·위치 또는 검색 이후의 원문이 일치하지 않습니다."}
    return {k: original[k] for k in ("id","doc_id","title","publisher","url","locator","license")} | {
        "quote":quote, "status":"source_verified"}


def compare_source_values(store, retrieved, claims):
    """Compare explicit source measurements only for the same quantity, unit and conditions."""
    groups = {}
    for c in claims:
        checked = check_quote(store, retrieved, c)
        if checked["status"] != "source_verified":
            continue
        # A value can only be attributed when the literal, quantity and scope occur in its quote.
        literal = str(c.get("literal",""))
        unit, quantity, scope = (c.get(k) for k in ("unit","quantity","scope"))
        if not all(isinstance(x, str) and x.strip() for x in (quantity, scope, unit)):
            continue
        quote = checked["quote"]
        if scope not in quote or quantity not in quote or not re.fullmatch(r"[-+]?\d+(?:\.\d+)?", literal):
            continue
        # Adjacency prevents assigning another quantity's number in the same passage.
        quantity_value = (re.escape(quantity) + r"\s*(?:is|was|equals|=|:|은|는|이|가)?\s*"
                          + re.escape(literal) + r"\s*" + re.escape(unit) + r"(?![\w/·^⁻])")
        if not re.search(quantity_value, quote, re.I):
            continue
        groups.setdefault((quantity, unit, scope), []).append((float(literal), checked["doc_id"]))
    return [{"status":"conflict", "quantity":key[0], "unit":key[1], "scope":key[2], "documents":sorted({d for _,d in items})}
            for key, items in groups.items()
            if any(d1 != d2 and not math.isclose(v1,v2,rel_tol=5e-4,abs_tol=1e-10)
                   for v1,d1 in items for v2,d2 in items)]


def check_reported_numbers(text, snapshot):
    """Check explicit named run quantities in prose; unparsed prose receives no numeric certification."""
    results = []
    ref = reference_values(snapshot)
    stamp = run_id(snapshot)
    for key, (label, _, unit) in ref.items():
        if key.startswith("last."):
            continue
        names = sorted({label,*FACT_ALIASES.get(key,())}, key=len, reverse=True)
        quantity = "(?:" + "|".join(re.escape(name) for name in names) + ")"
        pattern = (r"(?<![A-Za-z가-힣])" + quantity + r"(?:의?\s*크기)?(?:은|는|이|가)?\s*(?:=|:|약|is|equals)?\s*"
                   r"([-+]?(?:\d+(?:\.\d+)?|\.\d+)(?:[eE][-+]?\d+)?)\s*"
                   r"(1(?!\d)|[A-Za-z°µΩ][A-Za-z0-9°µΩ·⋅*⁻²³/^]*)")
        for m in re.finditer(pattern, text, re.I):
            value = float(m[1])
            if not math.isfinite(value):
                results.append({"status":"failed", "label":label, "expected":ref[key][1], "expected_unit":unit,
                                "reason":"유한한 수치가 아닙니다."})
                continue
            claim = NumberClaim(key=key,value=value,unit=m[2],experiment_id=str(snapshot.experiment.id),
                                revision=snapshot.revision,run_id=stamp)
            results.append(check_number(claim,snapshot))
    return results


def readings(snapshot, maximum=4, question=""):
    values = reference_values(snapshot)
    stamp = run_id(snapshot)
    result = []
    folded = "".join(question.casefold().split())
    def relevance(key):
        label = values[key][0]
        return max((len(alias) for alias in (label, *FACT_ALIASES.get(key, ()))
                    if "".join(alias.casefold().split()) in folded), default=0)
    for key in sorted(values, key=relevance, reverse=True)[:maximum]:
        _, value, unit = values[key]
        c = NumberClaim(key=key, value=value, unit=unit, experiment_id=str(snapshot.experiment.id),
                        revision=snapshot.revision, run_id=stamp)
        result.append(check_number(c,snapshot))
    return result

