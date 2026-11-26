"""Trusted tutor turn preparation, streamed delivery and comparison transactions."""
import asyncio
from contextlib import suppress
import json
import re
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool

from . import clarification, cognitive, evidence, grounded, reasoning, tutor
from .cognitive_routing import route
from .physics import SPECS, simulate
from .portable import DisplayNames
from .providers import ProviderSelection, provider_context
from .schema import Level, Patch, StrictModel
from .state import RevisionConflict, build
from .workbenches import FACTS, comparison_text


class Member(StrictModel):
    revision: int = Field(ge=1, strict=True)
    model: str | None = None
    patch: Patch = Field(default_factory=Patch)
    level: Level = "school"


class Turn(StrictModel):
    experiment_id: UUID
    revision: int = Field(ge=1, strict=True)
    message: str = Field(min_length=1, max_length=2000)
    previous_question: str | None = Field(default=None,max_length=600)
    mode: Literal["explain", "experiment", "discovery", "equation", "review"] = "explain"
    level: Level = "school"
    selection: ProviderSelection | None = None
    dialogue: clarification.DialogueState | None = None


class ComparedRun(StrictModel):
    experiment_id: UUID
    revision: int
    run_id: str
    model: str


class ComparedMeasurement(StrictModel):
    key: str
    unit: str
    baseline: float
    compared: float
    difference: float


class ComparisonClaim(StrictModel):
    kind: Literal["comparison"] = "comparison"
    text: str
    status: Literal["calculation_verified","partial","failed","unverifiable"]
    references: tuple[str,str]
    runs: tuple[ComparedRun,ComparedRun]
    measurement: ComparedMeasurement | None


def comparison_claim(first, second):
    """Only snapshots calculated by the server may produce a two-run reading."""
    left = ComparedRun(experiment_id=first.experiment.id, revision=first.revision,
                       run_id=evidence.run_id(first), model=first.experiment.model)
    right = ComparedRun(experiment_id=second.experiment.id, revision=second.revision,
                        run_id=evidence.run_id(second), model=second.experiment.model)
    statuses = {first.run.status,second.run.status}
    measurement = None
    if "FAILED" in statuses:
        status = "failed"
    elif left.model != right.model:
        status = "unverifiable"
    else:
        status = "calculation_verified" if statuses=={"VERIFIED"} else "partial"
        for key, _, unit in FACTS:
            if key in first.run.facts and key in second.run.facts:
                a,b = first.run.facts[key],second.run.facts[key]
                measurement = ComparedMeasurement(key=key,unit=unit,baseline=a,compared=b,difference=b-a)
                break
    return ComparisonClaim(text=comparison_text(first,second),status=status,references=(left.run_id,right.run_id),
                           runs=(left,right),measurement=measurement).model_dump(mode="json")


def wire(event, **fields):
    return json.dumps({"event": event, **fields}, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":")) + "\n"


def view_channel(action):
    return "graph" if action["op"] in {"highlight_graph", "highlight_quantity"} else action["op"]


def studio_router(store, boards, load, get_spec, make_snapshot, snapshot_type, knowledge, names=None):
    router = APIRouter(prefix="/api")
    names = names or DisplayNames(store.path)

    @router.get("/workbenches/{eid}")
    def workbench(eid: UUID, level: Level = "school"):
        anchor, ids = boards.members(eid)
        members = []
        display_names = {}
        name_revisions = {}
        for member in ids:
            exp, rev, _ = load(member)
            members.append(make_snapshot(exp, rev, level))
            display_name, name_revision = names.get(member)
            display_names[str(member)] = display_name
            name_revisions[str(member)] = name_revision
        return {"anchor": str(anchor), "members": members,
                "display_names": display_names, "name_revisions": name_revisions,
                "analysis": [comparison_text(members[0], other) for other in members[1:]]}

    @router.post("/workbenches/{eid}/members")
    def add(eid: UUID, body: Member):
        source, rev, _ = load(eid, body.revision)
        spec = get_spec(body.model or source.model)
        exp = build(spec, uuid4(), body.patch, None if body.model else source)
        result = make_snapshot(exp, 1, body.level)
        boards.attach(eid, rev, exp, body.level)
        return result

    @router.delete("/workbenches/{eid}/members/{member}")
    def remove(eid: UUID, member: UUID):
        load(eid)
        boards.detach(eid, member)
        return {"removed": str(member)}

    @router.get("/usage")
    def usage():
        return {"items": boards.usage()}

    @router.get("/learning/export")
    def export_learning():
        return boards.export_learning()

    @router.delete("/learning")
    def erase():
        boards.erase_learning()
        return {"deleted": True}

    async def prepare(body, metrics, queue):
        message = body.message.strip()
        if not message:
            raise ValueError("질문을 입력하세요.")
        current, revision, _ = await run_in_threadpool(load, body.experiment_id, body.revision)
        if clarification.stale_dialogue(body.dialogue, message, current.id, revision):
            clarification.retire(body.dialogue)
            notice = clarification.MissingCondition(label="대화 상태", reason="이전 답변이 이미 처리되었거나 실험 조건이 바뀌었습니다.")
            prompt = "이전 답변이 이미 처리되었거나 실험 조건이 바뀌었습니다. 최신 질문을 확인한 뒤 다시 답해 주세요."
            return clarification.response(prompt, body.level, [notice]), None
        pending = clarification.merge_followup(body.dialogue, message, current.id, revision, SPECS)
        special = None
        pending_blocked = False
        if pending:
            message, dialogue = pending
            special = clarification.special_topic(message)
            pending_blocked = clarification.blocked_scope(message, current, special)
            if not pending_blocked:
                remaining = clarification.unresolved(dialogue, message, current, SPECS)
                if remaining:
                    dialogue = dialogue.model_copy(update={"missing_conditions": remaining})
                    prompt = clarification.question_for(dialogue.model or "", remaining)
                    return clarification.response(prompt, body.level, remaining, dialogue), None
        else:
            dialogue = None
            clarification.retire(body.dialogue)
            special = clarification.special_topic(message)
        excluded = cognitive.excluded_reply(message,body.level)
        if excluded:
            clarification.retire(dialogue)
            return excluded, None
        selected = route(message,current)
        domain_reason = getattr(selected,"unsupported_reason",None)
        if domain_reason or pending_blocked or clarification.blocked_scope(message, current, special):
            clarification.retire(dialogue)
            topic = "drag" if clarification.drag_only_request(message, current, special) else None
            response, _ = await run_in_threadpool(
                grounded.reading_only, knowledge, message, body.mode, body.level, topic,
                domain_reason or (None if topic else reasoning._SCOPE))
            response["classification"] = "unsupported"
            response["dialogue"] = None
            return response, None
        math_reply = await run_in_threadpool(cognitive.math_turn,message,body.level)
        if math_reply:
            clarification.retire(dialogue)
            return math_reply, None
        prompt = clarification.identify(message, current, revision, SPECS)
        if prompt:
            clarification.retire(dialogue)
            return clarification.response(prompt.message, body.level,
                                          prompt.missing_conditions, prompt.dialogue), None
        if special:
            response, _ = await run_in_threadpool(grounded.reading_only, knowledge, message, body.mode, body.level, special)
            response["classification"] = ("sufficient" if response.get("evidence", {}).get("theory_status") == "available"
                                           else "unsupported")
            response["dialogue"] = None
            clarification.retire(dialogue)
            return response, None
        default = reasoning.Intent(action="explain", model=current.model, patch=Patch(), level=body.level)
        compare = tutor.is_comparison_request(message)
        _, members = boards.members(current.id)
        inspect_comparison = not compare and len(members) > 1 and bool(re.search(
            r"(?:비교|두 실험|실험 간|실험들의?).*(?:결과|차이|어떻|설명|해석)|(?:결과|차이).*비교", message))
        # A visualization refers to actual sample times and recorded quantities.
        base = await run_in_threadpool(make_snapshot, current, revision, body.level)
        raw_view = tutor.visualization_request(message, current, base.run)
        if reasoning._DENY_CHANGE.search(message):
            compare = False
            raw_view = [v for v in raw_view or [] if v["op"] not in {"change_conditions","create_comparison"}]
        direct_ops = [a for a in (raw_view or []) if a["op"] in {"change_conditions", "create_comparison"}]
        if compare and len(members) >= 4:
            raise HTTPException(409, "비교 실험은 최대 4개입니다.")
        if dialogue and dialogue.force_new:
            intent = cognitive.local_plan(message, None, body.level, selected)
        elif direct_ops:
            if len(direct_ops) != 1:
                raise ValueError("한 번에 한 조건 변경을 요청하세요.")
            compare = direct_ops[0]["op"] == "create_comparison"
            intent = default.model_copy(update={"action": "modify", "patch": Patch.model_validate(direct_ops[0]["patch"])})
        elif inspect_comparison:
            # Retain the planner's domain guard even for questions about saved peers.
            guarded = cognitive.local_plan(message, current, body.level, selected)
            intent = guarded if guarded.action == "unsupported" else default
        elif raw_view and not compare:
            intent = default
        elif body.mode in {"review", "discovery", "equation"} and message in {
            "복습 문제를 내줘", "가설을 세워볼래", "공식을 단계별로 설명해 줘"}:
            intent = default
        else:
            question = tutor.comparison_message(message) if compare else message
            intent = cognitive.local_plan(question or "현재 실험 결과를 설명해 줘",current,body.level,selected)
        if intent.action == "unsupported":
            need = clarification.plan_failure(message, current, revision, intent, SPECS)
            if need:
                clarification.retire(dialogue)
                return clarification.response(need.message, body.level, need.missing_conditions, need.dialogue), None
            topic = "drag" if grounded.DRAG.search(message) and not re.search("무기|총알|발사체|탄도|missile|weapon|bullet",message,re.I) else None
            response, _ = await run_in_threadpool(grounded.reading_only, knowledge, message, body.mode, body.level, topic, intent.message)
            response["classification"] = "unsupported"
            response["dialogue"] = None
            clarification.retire(dialogue)
            return response, None
        action = "compare" if compare else intent.action
        level = intent.level
        model = intent.model or current.model
        if action == "compare":
            exp = build(get_spec(model), uuid4(), intent.patch, current if model == current.model else None)
        elif action == "create":
            exp = build(get_spec(model), uuid4(), intent.patch)
        elif action == "modify":
            exp = build(get_spec(current.model), current.id, intent.patch, current)
        else:
            exp = current
        rows = await run_in_threadpool(grounded.retrieved_for, knowledge, message, exp.model)
        run = base.run if action == "explain" else await run_in_threadpool(simulate, exp)
        new_revision = revision + 1 if action == "modify" else revision if action == "explain" else 1
        result = snapshot_type(experiment=exp, revision=new_revision, run=run, explanation="")
        context = await run_in_threadpool(grounded.make_context, knowledge, rows, message, result, question=message)
        metrics.research_context = {**context, "passages":context["passages"][:4]}
        explanation, trace = await cognitive.explain_turn(message,level,body.mode,selected,result,context,metrics,
                                                         body.previous_question)
        lesson = tutor.teach(message, body.mode, exp, run, level, explanation)
        view = list(lesson["actions"])
        if raw_view:
            view.extend(v for v in raw_view if v not in view)
        if metrics.visual_actions:
            requested_channels = {view_channel(v) for v in raw_view or []}
            provider_view = []
            for item in metrics.visual_actions:
                try:
                    directive, = tutor.validate_actions([item],exp,run)
                except (ValueError,ValidationError):
                    trace["warnings"].append("invalid_visual_action_removed")
                    continue
                if directive["op"] in {"create_comparison", "change_conditions"}:
                    matching = "compare" if directive["op"] == "create_comparison" else "modify"
                    if action != matching or Patch.model_validate(directive["patch"]) != intent.patch:
                        trace["warnings"].append("unrequested_state_change_removed")
                elif view_channel(directive) not in requested_channels:
                    provider_view.append(directive)
            provider_channels = {view_channel(v) for v in provider_view}
            view = provider_view + [v for v in view if view_channel(v) not in provider_channels]
        if action in {"modify", "compare"}:
            op = "change_conditions" if action == "modify" else "create_comparison"
            view = [v for v in view if v["op"] not in {"change_conditions","create_comparison"}]
            view.append({"op": op, "patch": intent.patch.model_dump(exclude_none=True)})
        lesson["actions"] = tutor.validate_actions(view, exp, run)
        if body.mode in {"explain", "experiment"}:
            reading = evidence.graph_observation(result, lesson["actions"])
            if reading:
                context["observations"] = [reading]
        hidden = body.mode in {"discovery","review"}
        # The inspector reads this field independently of the tutor's evidence
        # panel. Populate it with the same engine-only readout as GET /experiments.
        result = result.model_copy(update={"explanation":"" if hidden else reasoning.explain(exp,run,level)})
        formula = context["formula"]
        if formula and body.mode in {"equation","explain"} and re.search(r"적용|근사|소각|언제|성립|condition|approx",message,re.I):
            lesson["text"] += "\n\n" + " · ".join(formula["conditions"]) + "\n" + formula["applicability"]["reason"]
        dossier = await run_in_threadpool(grounded.report, knowledge, rows, context, lesson["text"],
                                          snapshot=result, mode=body.mode, metrics=metrics,
                                          level=level, question=message)
        cognitive.finish_trace(trace,dossier,explanation)
        comparisons = []
        if action == "compare" and not hidden:
            comparisons.append(comparison_claim(base,result))
        elif inspect_comparison and not hidden:
            anchor = base if current.id == members[0] else await run_in_threadpool(
                lambda: make_snapshot(*load(members[0])[:2], body.level))
            peers = members[1:] if current.id == members[0] else [current.id]
            for peer in peers:
                sample = base if peer == current.id else await run_in_threadpool(
                    lambda: make_snapshot(*load(peer)[:2], body.level))
                comparisons.append(comparison_claim(anchor,sample))
        for claim in comparisons:
            dossier["core"] += "\n\n" + claim["text"]
            dossier["claims"].append(claim)
        lesson["evidence"] = dossier
        lesson["text"] = dossier["core"]
        classification, assumed_values = clarification.result_classification(
            action, exp, intent.patch, run.status)
        assumptions = assumed_values
        def commit():
            if action == "compare":
                boards.attach(current.id, revision, exp, level)
            elif action == "create":
                boards.create_from(current.id, revision, exp, level)
            elif action == "modify":
                store.save(exp, level, revision)
            else:
                load(current.id, revision)
            clarification.retire(dialogue)
        return {"action": action, "status": run.status, "message": lesson["text"],
                "snapshot": result.model_dump(mode="json"), "level": level, "lesson": lesson,
                "evidence":dossier, "classification":classification, "assumptions":assumptions,
                "dialogue":None, "pipeline":trace,
                **cognitive.contract_receipt(action,result,intent.patch,current.id,revision,level)}, commit

    @router.post("/tutor/stream")
    async def stream(body: Turn, request: Request):
        # A missing default model must be reported before HTTP streaming begins.
        with provider_context(body.selection):
            pass
        generation = boards.generation()
        async def events():
            queue = asyncio.Queue(maxsize=32)
            def progress(info):
                if not queue.full():
                    queue.put_nowait({"stage": "공급자 응답 수신", **info})
            outcome = "cancelled"
            with provider_context(body.selection, stream=True, on_progress=progress) as metrics:
                task = asyncio.create_task(prepare(body, metrics, queue))
                try:
                    yield wire("stage", stage="질문 분석 · 문헌 조회 및 계산")
                    while not task.done():
                        if await request.is_disconnected():
                            return
                        try:
                            update = await asyncio.wait_for(queue.get(), timeout=.12)
                            yield wire("stage", **update)
                        except TimeoutError:
                            pass
                    result, commit = task.result()
                    result.setdefault("answer_state",cognitive.outcome(result))
                    result.setdefault("pipeline",{"generation":"deterministic","warnings":[]})
                    if result.get("evidence") is not None:
                        result["evidence"]["answer_state"] = result["answer_state"]
                        result["evidence"]["generation"] = result["pipeline"]["generation"]
                    # Only grounded Korean paragraphs cross the streaming boundary.
                    for paragraph in result["message"].split("\n\n"):
                        yield wire("text", text=paragraph)
                        await asyncio.sleep(0)
                    if await request.is_disconnected():
                        return
                    if commit:
                        commit()
                    outcome = "ok"
                    yield wire("result", result=result, metrics=metrics.as_dict())
                except (HTTPException, RevisionConflict, reasoning.ProviderError, ValueError) as error:
                    outcome = "error"
                    clarification.restore(body.dialogue)
                    detail = error.detail if isinstance(error, HTTPException) else str(error)
                    yield wire("error", detail=detail or "실험이 변경되었습니다. 새로 불러와 주세요.")
                finally:
                    if outcome == "cancelled":
                        clarification.restore(body.dialogue)
                    task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await task
                    boards.usage(metrics.as_dict(), outcome, generation)
        return StreamingResponse(events(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
    return router
