"""Shared context selection for the tutor and offline, non-mutating ablation runs."""
import re
from typing import Literal
from uuid import UUID, uuid4

from starlette.concurrency import run_in_threadpool

from . import clarification, evidence, grounded, reasoning
from .physics import SPECS, simulate
from .schema import Level, Patch, StrictModel
from .state import build

# Count UTF-8 bytes as a conservative upper bound for data-dependent token usage.
# The transport adds its short, fixed instructions and records actual model token counts.
CONTEXT_BYTES = 6000
_EXCLUDED = re.compile(r"무기|총기|총알|탄도|미사일|포탄|폭탄|살상|암살|병원체|바이러스|해킹|악성\s*코드|"
                       r"\b(?:weapon\w*|firearms?|gunshots?|bullets?|missiles?|bombs?|ballistics?|explosives?|"
                       r"pathogens?|malware|ransomware|shellcode)\b",re.I)


def excluded_reply(question,level):
    if not _EXCLUDED.search(question):
        return None
    text = "요청한 대상은 PHYSIS의 교실 물리 실험 범위 밖입니다. 수레의 운동이나 용수철 진동 같은 실험을 선택할 수 있습니다."
    dossier = {"core":text,"sources":[],"formula":None,"calculations":[],"claims":[],"checks":[],
               "assumptions":[],"uncertainty":[],"related_models":[],"prerequisite":None,
               "theory_status":"insufficient","simulation_supported":False}
    lesson = {"mode":"explain","title":"지원 범위","text":text,"prompt":"","actions":[],"evidence":dossier}
    return {"action":"unsupported","classification":"unsupported","status":"UNSUPPORTED","snapshot":None,"level":level,
            "answer_state":"UNSUPPORTED_SIMULATION","message":text,"evidence":dossier,"lesson":lesson,"dialogue":None}


class ExperimentAction(StrictModel):
    op: Literal["create","modify","compare"]
    target_experiment_id: UUID
    source_experiment_id: UUID | None
    source_revision: int | None
    patch: Patch


class ApplicationState(StrictModel):
    """Read-only projection. Learning history and settings stay with their existing owners."""
    experiment_id: UUID
    revision: int
    level: Level


def contract_receipt(action,snapshot,patch,source_id,source_revision,level):
    state = ApplicationState(experiment_id=snapshot.experiment.id,revision=snapshot.revision,level=level)
    change = None
    if action in {"create","modify","compare"}:
        change = ExperimentAction(op=action,target_experiment_id=state.experiment_id,patch=patch,
                                  source_experiment_id=source_id,source_revision=source_revision)
    return {"application_state":state.model_dump(mode="json"),
            "experiment_action":change.model_dump(mode="json",exclude_none=True) if change else None}

_MATH_VERBS = {"미분":"differentiate","적분":"integrate","differentiate":"differentiate","integrate":"integrate",
               "simplify":"simplify","간단히 정리":"simplify"}
_SYMBOLIC = r"(?P<expr>[+\-(\da-zA-Z][a-zA-Z0-9 .+*/^()\-]{0,160}?)"


def needs_readout(question,route):
    return (bool({"calculation","experiment_create","experiment_modify","comparison"}.intersection(route.intents))
            or bool(re.search(r"현재|이번|이\s*실험|관측값|측정값|그래프|실험\s*결과|this run|current|measured",question,re.I)))


def math_turn(question, level):
    """Bind explicit single-variable math requests to the existing bounded parser."""
    from .math_router import mathematics, MathRequest

    verbs = "|".join(_MATH_VERBS)
    term = re.fullmatch(rf"\s*(?:(?P<prefix>{verbs})\s+{_SYMBOLIC}|(?P<left>[a-zA-Z0-9 .+*/^()\-]+?)"
                        rf"(?:을|를)?\s*(?:(?P<variable>[a-z])에\s*대해\s*)?(?P<suffix>{verbs}))"
                        r"(?:해\s*(?:줘|주세요)|해|하세요)?\s*[.?!]?\s*",question,re.I)
    if not term:
        return None
    expression = (term["expr"] or term["left"]).strip().replace("^","**")
    variables = set(re.findall(r"\b[a-z]\b",expression))
    if not term["variable"] and len(variables)>1:
        return clarification.response("어느 변수를 기준으로 계산할까요? 수식과 기준 변수를 함께 적어 주세요.",level)
    variable = term["variable"] or next(iter(sorted(variables)),"x")
    operation = _MATH_VERBS[(term["prefix"] or term["suffix"]).lower()]
    result = mathematics(MathRequest(operation=operation,expression=expression,variable=variable))
    ok = result.get("status") == "computed" and result.get("result") is not None
    verb = {"differentiate":"미분","integrate":"부정적분","simplify":"정리"}[operation]
    value = str(result.get("result",""))
    if ok and operation == "integrate":
        value += " + C (C는 적분 상수)"
    text = f"{expression}의 {verb} 결과는 {value}입니다." if ok else result.get("detail","주어진 식을 검산할 수 없습니다.")
    if ok and operation != "simplify":
        text += f" 기준 변수는 {variable}입니다."
    for key in ("domain","conditions"):
        if result.get(key):
            text += f" 적용 조건은 {result[key]}입니다."
    dossier = {"core":text,"sources":[],"formula":None,"calculations":[],"claims":[],"assumptions":[],
               "checks":[{"status":result.get("status"),"reason":text}],"uncertainty":[],"theory_status":"not_required",
               "simulation_supported":False,"related_models":[],"prerequisite":None,"math_result":result}
    lesson = {"mode":"explain","title":"기호 계산","text":text,"prompt":"","actions":[],"evidence":dossier}
    return {"action":"explain","status":"COMPUTED" if ok else "UNVERIFIED","message":text,"snapshot":None,"level":level,
            "lesson":lesson,"evidence":dossier,"classification":"sufficient" if ok else "unsupported","dialogue":None,
            "answer_state":"ANSWERED" if ok else "VERIFICATION_FAILED","pipeline":{"intents":["math"],"generation":"deterministic","warnings":[]}}


def compact_context(question, level, route, exp, material, *, history=(), rag=True, physics=True):
    import json

    def fits(data):
        return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf8")) <= CONTEXT_BYTES

    subject = route.model
    if not subject and (needs_readout(question,route) or re.search(r"이번|현재|the current",question,re.I)):
        if not {"unsupported","clarification"}.intersection(route.intents):
            subject = exp.model
    packet = {"question": question, "level": level, "intents": list(route.intents)}
    if subject:
        packet["model"] = subject
    # An unusually long UTF-8 question can consume the whole context. Do not truncate
    # a physical quantity to fit; the verified path can still answer without this call.
    if not fits(packet):
        raise ValueError("질문이 모델 문맥 예산을 넘었습니다.")
    show_run = needs_readout(question,route)
    if exp.model == subject and show_run:
        packet["inputs"] = dict(exp.values)
    def add(key, value):
        if value and fits({**packet, key:value}):
            packet[key] = value
    if rag:
        f = material.get("formula")
        if f and f["model"] == subject:
            add("formula", {k:f[k] for k in ("formula_id","latex","conditions","status")})
    if physics and exp.model == subject and show_run:
        numbers = []
        for n in material.get("calculations", ()):
            if n.get("status") == "calculation_verified":
                numbers.append({k:n[k] for k in ("key","label","value","unit","run_id","revision","experiment_id")})
        add("calculations", numbers[:4])
    if exp.model == subject:
        formula_limits = material.get("formula") or {}
        limits = list(formula_limits.get("conditions",[])) if rag else []
        add("conditions",list(dict.fromkeys([*limits,*exp.assumptions]))[:6])
    if rag:
        passages = []
        for row in material.get("passages", ()):
            item = {"id":row["id"], "quote":row["quote"]}
            if fits({**packet,"passages":[*passages,item]}):
                passages.append(item)
            if len(passages) == 3:
                break
        add("passages", passages)
    if history and re.search(r"그[럼렇때]|반대|아까|앞서|이전|다시|그중|같은|then|previous|instead|what if",question,re.I):
        # Prior assistant prose is untrusted. A previous user question resolves short follow-ups.
        for turn in reversed(history):
            if isinstance(turn, dict) and isinstance(turn.get("question"),str) and not _EXCLUDED.search(turn["question"]):
                add("history", [{"question":turn["question"][:280]}])
                break
    if not fits(packet):
        packet.pop("inputs", None)
    return packet


def local_plan(question, current, level, route):
    """Derive DSL solely from the request. Apply the same domain and model constraints as the planner."""
    text = reasoning._norm(question).strip()
    # A request for simpler wording changes this explanation, not the stored audience.
    audience_text = re.sub(r"쉽게|아주\s*쉽\w*|\bsimply\b","",text,flags=re.I)
    level = next((n for n,p in reasoning._AUDIENCE.items() if re.search(p,audience_text,re.I)),level)
    if getattr(route,"unsupported_reason",None):
        return reasoning._decline(level,route.unsupported_reason)
    if not text or clarification.blocked_scope(text,current,clarification.special_topic(text)):
        return reasoning._decline(level)
    if reasoning._DENY_CHANGE.search(text) and current is not None:
        return reasoning.Intent(action="explain",model=current.model,patch=Patch(),level=level)
    intent = reasoning._local(text,current,level,SPECS)
    explicit_write = "experiment_modify" in route.intents
    current_reference = bool(getattr(route,"references_current",False))
    hypothetical = bool(getattr(route,"hypothetical",False))

    # Some counterfactuals name enough variables to identify a registered model,
    # but the edit-oriented parser deliberately declines them as active changes.
    # Reparse only against that explicit route model and emit a new detached case.
    if intent.action == "unsupported" and hypothetical and route.model in SPECS:
        base = current if current and current.model == route.model else None
        try:
            candidate_patch = reasoning._parse_patch(text, SPECS[route.model], base)
            if reasoning._has_patch(candidate_patch):
                patch = Patch(
                    values={**(base.values if base else {}), **candidate_patch.values},
                    method=(candidate_patch.method if candidate_patch.method is not None
                            else base.method if base else None),
                    dt=(candidate_patch.dt if candidate_patch.dt is not None
                        else base.dt if base else None),
                    duration=(candidate_patch.duration if candidate_patch.duration is not None
                              else base.duration if base else None),
                )
                build(SPECS[route.model], UUID(int=0), patch)
                intent = reasoning.Intent(action="create", model=route.model, patch=patch, level=level)
        except (ValueError, ValidationError):
            pass

    def detached_copy(candidate):
        values = {**current.values, **candidate.patch.values}
        patch = Patch(values=values,
                      method=candidate.patch.method if candidate.patch.method is not None else current.method,
                      dt=candidate.patch.dt if candidate.patch.dt is not None else current.dt,
                      duration=candidate.patch.duration if candidate.patch.duration is not None else current.duration)
        return candidate.model_copy(update={"action":"create","model":current.model,"patch":patch})

    # A question about the open experiment is read-only unless the user gives a
    # direct imperative change command. Model aliases such as “acceleration” may
    # name a subtopic rather than the selected experiment; bind the query to the
    # selected model and never let parser guesses write into the active state.
    if current and current_reference and route.model == current.model and not explicit_write and not hypothetical:
        try:
            readout_patch = reasoning._parse_patch(text, SPECS[current.model], current)
        except (ValueError, ValidationError):
            return reasoning._decline(level, reasoning._CONDITIONS)
        if reasoning._has_patch(readout_patch):
            detached = intent.model_copy(update={"action":"modify","model":current.model,"patch":readout_patch})
            return detached_copy(detached)
        return reasoning.Intent(action="explain",model=current.model,patch=Patch(),level=level)

    if intent.action == "modify" and current and not explicit_write:
        # Hypotheticals, read-only numeric examples, and uncertain parser matches
        # run on a detached example. The active experiment is never the write target.
        values = {**current.values,**intent.patch.values}
        patch = Patch(values=values,method=intent.patch.method or current.method,
                      dt=intent.patch.dt or current.dt,duration=intent.patch.duration or current.duration)
        return intent.model_copy(update={"action":"create","model":current.model,"patch":patch})
    if intent.action == "unsupported" and intent.message == reasoning._SCOPE and route.model in SPECS:
        # A concept can be expressed without any imperative verb. An unrecognized
        # numeric or edit request must never inherit this read-only permission.
        if set(route.intents).issubset({"concept","formula"}) and route.confidence >= 0.65:
            action = "explain" if current and route.model == current.model else "create"
            return reasoning.Intent(action=action,model=route.model,patch=Patch(),level=level)
    return intent


def screened_text(response, snapshot):
    """Exclude unbound numeric assertions and inline invented references before claim/evidence alignment."""
    text = response.text
    safe, warnings = [], list(response.warnings)
    for sentence in grounded.split_claims(text):
        if re.search(r"https?://|\[[^\]]+\]|(?:doi|isbn)\s*[:=]",sentence,re.I):
            warnings.append("inline_reference_removed")
            continue
        if re.search(r"(?<![a-zA-Z])[+-]?\d",sentence):
            # Every numeric assertion must bind to its own quantity and unit. Use the
            # server's canonical measurement paragraph for all quantitative sentences.
            warnings.append("numeric_prose_replaced_by_run")
            continue
        safe.append(sentence)
    return "\n\n".join(safe), list(dict.fromkeys(warnings))


async def explain_turn(question, level, mode, route, snapshot, material, metrics, previous_question=None):
    """Generate optional prose. Always let the caller reverify it against the actual run and citations."""
    from . import providers
    from .classroom_units import unit_note

    exp, run = snapshot.experiment, snapshot.run
    trace = {"intents":list(route.intents),"model":route.model,"confidence":route.confidence,
             "readout_requested":needs_readout(question,route),
             "generation":"deterministic","warnings":[],"context_bytes":0}
    if mode in {"discovery","review","equation"}:
        return "", trace
    from .provider_stream import current_replay_transport
    if metrics.provider == "mock" and current_replay_transport() is None:
        return await reasoning.interpret(question,exp,run,level), trace
    fallback = unit_note(question, exp.model) or reasoning.explain(exp,run,level)
    try:
        history = [{"question":previous_question}] if previous_question else []
        packet = compact_context(question,level,route,exp,material,history=history)
        import json
        trace["context_bytes"] = len(json.dumps(packet,ensure_ascii=False,separators=(",",":")).encode("utf8"))
        metrics.research_context = {"passages":packet.get("passages",[])}
        response = await providers.request_explanation(metrics.provider,packet)
        text, warnings = screened_text(response,snapshot)
        trace.update(generation="model_candidate",warnings=warnings)
        # Keep the source list on the server; only retrieved sources may be proposed by the model.
        metrics.proposed_sources = list(response.source_ids) or metrics.proposed_sources
        if "invalid_source_ids_dropped" in warnings and not response.source_ids:
            text = ""
            material["passages"] = []
        if text:
            trace["candidate_clauses"] = len(grounded.split_claims(text))
            note = unit_note(question, exp.model)
            return "\n\n".join(v for v in (note,text) if v), trace
        trace["generation"] = "verified_fallback"
    except (providers.ProviderError,ValueError) as exc:
        rejected = metrics.requests[-1].get("warnings",[]) if metrics.requests else []
        trace.update(generation="verified_fallback",warnings=["provider_or_contract_error",*rejected],
                     detail=str(exc))
    return fallback, trace


def outcome(result):
    e = result.get("evidence") or {}
    a = (e.get("abstention") or {}).get("status")
    if result.get("classification") == "needs_clarification":
        return "CLARIFICATION_REQUIRED"
    if result.get("status") == "FAILED":
        return "VERIFICATION_FAILED"
    if result.get("classification") == "assumptions":
        return "ASSUMPTION_REQUIRED"
    if result.get("action") == "unsupported":
        if e.get("scope_reason") or e.get("theory_status") == "available":
            return "UNSUPPORTED_SIMULATION" if result.get("classification") == "unsupported" else "ANSWERED"
        return "INSUFFICIENT_EVIDENCE"
    if a == "full":
        return "INSUFFICIENT_EVIDENCE"
    if a == "partial" or result.get("status") == "LIMITED":
        return "PARTIALLY_ANSWERED"
    return "ANSWERED"


def finish_trace(trace, dossier, candidate):
    if not trace.get("readout_requested",True) and {"concept","formula"}.intersection(trace.get("intents",())):
        paragraphs = dossier["core"].split("\n\n")
        explanatory = [p for p in paragraphs if not p.startswith("이 실행에서 확인한 값:")]
        if explanatory:
            dossier["core"] = "\n\n".join(explanatory)
    if "invalid_source_ids_dropped" in trace.get("warnings",[]):
        dossier["checks"].append({"status":"failed","reason":"이번 질문에 제시되지 않은 인용 참조를 제거했습니다."})
    if trace.get("generation") != "model_candidate":
        return
    # Count only clauses that also survived into the actual user-visible answer.
    visible = {c["text"] for c in dossier.get("claims",[]) if c.get("kind")=="explanation"
               and not c.get("withheld") and c["text"] in dossier["core"]}
    accepted = set(grounded.split_claims(candidate)).intersection(visible)
    trace["accepted_clauses"] = len(accepted)
    trace["generation"] = "model_with_verified_tools" if accepted else "verified_fallback"


async def ablation_turn(condition, question, snapshot, store, level="school", history=(), *,
                        provider="ollama", transport=None):
    """Evaluation-only C, D, E path through the shared configured provider adapter."""
    from .api import Snapshot
    from .cognitive_routing import route
    from .providers import provider_name, request_explanation

    if condition not in {"C","D","E"} or provider_name() != provider:
        raise ValueError("평가 조건 또는 로컬 공급자를 확인하세요.")
    if excluded_reply(question,level):
        raise ValueError("학교 물리 평가 범위를 벗어났습니다.")
    state = Snapshot.model_validate(snapshot)
    exp = state.experiment
    selected = route(question,exp)
    material = {}
    rag, physics = condition in {"D","E"}, condition == "E"
    if not clarification.blocked_scope(question,exp,clarification.special_topic(question)):
        plan = local_plan(question, exp, level, selected)
        if plan.action in {"create","modify"} and plan.model in SPECS:
            exp = build(SPECS[plan.model],uuid4(),plan.patch,exp if plan.action=="modify" else None)
            if physics:
                state = Snapshot(experiment=exp,revision=1,run=await run_in_threadpool(simulate,exp),explanation="")
        if rag:
            rows = await run_in_threadpool(grounded.retrieved_for,store,question,selected.model or exp.model)
            material = await run_in_threadpool(grounded.make_context,store,rows,question,state if physics else None)
            if not physics:
                material["formula"] = grounded.chosen_formula(question,exp)
    packet = compact_context(question,level,selected,exp,material,history=history,rag=rag,physics=physics)
    reply = await request_explanation(provider,packet,transport=transport)
    return {"text":reply.text,"source_ids":reply.source_ids,"assumptions":reply.assumptions,
            "uncertainty":reply.uncertainty,"context":packet,"route":list(selected.intents)}
