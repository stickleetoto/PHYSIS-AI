"""Public simulation registry. Experiments are reconstructed server-side."""
import numpy as np

from . import physics_events as events, physics_fluids as fluids, physics_motion as motion
from . import physics_oscillations as oscillations
from . import physics_fields as fields
from .schema import Check, Experiment, ModelSpec, Run


SPECS: dict[str, ModelSpec] = motion.SPECS | events.SPECS | oscillations.SPECS | fluids.SPECS | fields.SPECS


def parse_dsl(payload: dict) -> Experiment:
    """Validate a full JSON design, including the registry's units and domains."""
    experiment = Experiment.model_validate(payload)
    spec = SPECS.get(experiment.model)
    if spec is None:
        raise ValueError("UNSUPPORTED · 등록되지 않은 물리 모델입니다.")
    # Duration and step size are experiment settings. Other metadata is the
    # trusted model definition, including units, available solvers and bounds.
    for name in ModelSpec.model_fields:
        if name not in {"dt", "duration"} and getattr(experiment, name) != getattr(spec, name):
            raise ValueError(f"등록된 모델 명세와 다른 DSL 필드입니다 ({name}).")
    return experiment


def _sample(exp, dt):
    args = (exp.values, exp.method, exp.duration, dt)
    if exp.model == "free_fall":
        return motion.fall(*args)
    if exp.model in ("uniform", "acceleration", "newton"):
        return motion.straight(exp.model, *args)
    if exp.model == "friction":
        return events.friction(*args)
    if exp.model == "collision":
        return events.collision(*args)
    if exp.model in ("spring", "damped"):
        return oscillations.oscillator(exp.model, *args)
    if exp.model == "pendulum":
        return oscillations.pendulum(*args)
    if exp.model == "circular":
        return oscillations.circular(*args)
    if exp.model in fluids.SPECS:
        return fluids.fluid(exp.model, *args)
    if exp.model in fields.SPECS:
        return fields.field_sample(exp.model, *args)
    raise ValueError("등록되지 않은 물리 모델입니다.")


def simulate(exp: Experiment) -> Run:
    exp = parse_dsl(exp.model_dump())
    result = _sample(exp, exp.dt)
    convergence = []
    finite = np.logical_and.reduce([np.isfinite(s) for s in [result.times, *result.series.values()]])
    bad = np.flatnonzero(~finite)
    if len(bad) or not all(np.isfinite(v) for v in result.facts.values()):
        stop = int(bad[0]) if len(bad) else len(result.times)
        return Run(times=result.times[:stop].tolist(), series={k:v[:stop].tolist() for k,v in result.series.items()},
                   facts={}, status="FAILED", checks=[Check(label="수치 유한성", passed=False,
                   detail="계산 결과가 유한한 범위를 벗어났습니다. 시간 간격을 줄여 다시 계산하세요.")])
    if exp.method != "analytic" and any(k.endswith(".error") for k in result.series):
        for factor in (1, 2, 4):
            h = exp.dt / factor
            error = result.max_error() if factor == 1 else _sample(exp, h).max_error()
            if np.isfinite(error):
                convergence.append({"dt": h, "error": error})
            else:
                result.checks.append(Check(label="격자 세분화", passed=False, detail="세분한 격자에서 유한한 오차를 얻지 못했습니다."))
                break
        if len(convergence) == 3:
            errors = [item["error"] for item in convergence]
            scale = max(float(np.max(np.abs(v))) for k,v in result.series.items() if k.endswith((".x", ".y")))
            floor = 1e-10 * max(1., scale)
            near_roundoff = max(errors) <= floor
            decreases = all(b <= a + floor for a,b in zip(errors, errors[1:])) and errors[-1] < errors[0]
            result.checks.append(Check(label="시간 간격을 절반으로 줄인 위치 오차", passed=near_roundoff or decreases,
                detail=" → ".join(f"{e:.4g}" for e in errors) + " m"
                       + (" · 수치 분해 한계 이내" if near_roundoff else "")))
    if not result.checks:
        status = "UNVERIFIED"
    elif any(not c.passed for c in result.checks):
        status = "FAILED"
    elif result.limitation:
        status = "LIMITED"
    else:
        status = "VERIFIED"
    if result.limitation:
        result.checks.append(Check(label="관찰 범위", passed=True, detail=result.limitation))
    return Run(times=result.times.tolist(), series={k: v.tolist() for k, v in result.series.items()},
               facts=result.facts, checks=result.checks, status=status, convergence=convergence)
