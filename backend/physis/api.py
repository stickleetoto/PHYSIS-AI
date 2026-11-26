"""Local HTTP boundary for experiment design, validation and calculation."""
from contextlib import asynccontextmanager, closing
import os
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import UUID, uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import clarification, reasoning
from .physics import SPECS, simulate
from .portable import DisplayNames, clean_display_name
from .portable_api import portable_router
from .schema import Experiment, Level, Patch, Run, StrictModel
from .state import Experiments, RevisionConflict, build
from .workbenches import Workbenches


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env", override=False)


class NewExperiment(StrictModel):
    model: str = Field(max_length=64)
    level: Level = "school"
    patch: Patch = Field(default_factory=Patch)
    display_name: str | None = Field(default=None, max_length=80)


class Edit(StrictModel):
    revision: int = Field(ge=1, strict=True)
    patch: Patch
    level: Level | None = None


class HistoryMove(StrictModel):
    revision: int = Field(ge=1, strict=True)
    level: Level | None = None


class Chat(StrictModel):
    message: str = Field(min_length=1, max_length=2000)
    experiment_id: UUID | None = None
    revision: int | None = Field(default=None, ge=1, strict=True)
    level: Level = "school"
    dialogue: clarification.DialogueState | None = None

    @model_validator(mode="after")
    def check_context(self):
        if not self.message.strip():
            raise ValueError("질문을 입력하세요.")
        if (self.revision is None) != (self.experiment_id is None):
            raise ValueError("기존 실험에는 ID와 버전이 함께 필요합니다.")
        return self


class Snapshot(StrictModel):
    experiment: Experiment
    revision: int
    run: Run
    explanation: str


def get_spec(model: str):
    if model not in SPECS:
        raise HTTPException(422, "UNSUPPORTED · 현재 등록되지 않은 물리 모델입니다.")
    return SPECS[model]


def snapshot(exp: Experiment, revision: int, level: Level) -> Snapshot:
    run = simulate(exp)
    return Snapshot(experiment=exp, revision=revision, run=run, explanation=reasoning.explain(exp, run, level))


def create_app(db_path: Path | None = None) -> FastAPI:
    data = Path(os.getenv("PHYSIS_DATA_DIR") or (Path(os.getenv("LOCALAPPDATA") or Path.home()) / "PHYSIS-AI"))
    store = Experiments(db_path or data / "experiments.sqlite3")
    boards = Workbenches(store)
    names = DisplayNames(store.path)
    from .knowledge import KnowledgeStore
    knowledge = KnowledgeStore(store.path.parent / "knowledge-v3.sqlite3")

    @asynccontextmanager
    async def lifespan(app):
        store.initialize()
        boards.initialize()
        knowledge.initialize()
        app.state.knowledge = knowledge
        yield

    app = FastAPI(title="PHYSIS AI", version="0.3.3", lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"])

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        # Do not echo arbitrary submitted values (including JSON NaN).
        first = exc.errors()[0]
        location = ".".join(str(part) for part in first["loc"])
        return JSONResponse({"detail": f"입력값을 확인하세요 ({location}): {first['msg']}"}, status_code=422)

    @app.exception_handler(ValidationError)
    async def invalid_state(request: Request, exc: ValidationError):
        return JSONResponse({"detail": exc.errors()[0]["msg"]}, status_code=422)

    @app.exception_handler(ValueError)
    async def invalid_conditions(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(RevisionConflict)
    async def conflict(request: Request, exc):
        try:
            submitted = await request.json()
            clarification.restore(clarification.DialogueState.model_validate(submitted["dialogue"]))
        except (KeyError, TypeError, ValueError):
            pass
        return JSONResponse({"detail": "이미 변경된 실험입니다. 최신 상태를 불러온 후 다시 시도하세요."}, status_code=409)

    @app.exception_handler(reasoning.ProviderError)
    async def provider_error(request: Request, exc):
        try:
            submitted = await request.json()
            clarification.restore(clarification.DialogueState.model_validate(submitted["dialogue"]))
        except (KeyError, TypeError, ValueError):
            pass
        return JSONResponse({"detail": str(exc)}, status_code=502)

    def load(experiment_id: UUID, expected: int | None = None):
        try:
            revision, model, patch, level = store.read(experiment_id)
        except KeyError:
            raise HTTPException(404, "저장된 실험을 찾을 수 없습니다.") from None
        if expected is not None and expected != revision:
            raise RevisionConflict()
        return build(get_spec(model), experiment_id, patch), revision, level

    def calculate_and_save(exp: Experiment, prior: int, level: Level):
        result = snapshot(exp, prior + 1, level)
        store.save(exp, level, prior)
        return result

    @app.get("/api/health")
    def health():
        return {"service": "PHYSIS AI", "version": app.version, "provider": reasoning.provider_name(), "offline":os.getenv("PHYSIS_OFFLINE")=="1"}

    @app.get("/api/catalog")
    def catalog():
        return {"models": list(SPECS.values()), "provider": reasoning.provider_name()}

    @app.get("/api/schema")
    def schema():
        return Experiment.model_json_schema()

    @app.post("/api/experiments", response_model=Snapshot)
    def create(body: NewExperiment):
        display_name = clean_display_name(body.display_name)
        exp = build(get_spec(body.model), uuid4(), body.patch)
        if display_name is None:
            return calculate_and_save(exp, 0, body.level)
        result = snapshot(exp, 1, body.level)
        with closing(sqlite3.connect(store.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            store.write(db, exp, body.level, 0)
            DisplayNames.write_in_transaction(db, exp.id, display_name)
        return result

    @app.get("/api/experiments/{experiment_id}", response_model=Snapshot)
    def get(experiment_id: UUID, level: Level | None = None):
        exp, revision, previous_level = load(experiment_id)
        return snapshot(exp, revision, level or previous_level)

    @app.patch("/api/experiments/{experiment_id}", response_model=Snapshot)
    def edit(experiment_id: UUID, body: Edit):
        exp, revision, previous_level = load(experiment_id, body.revision)
        updated = build(get_spec(exp.model), experiment_id, body.patch, exp)
        return calculate_and_save(updated, revision, body.level or previous_level)

    @app.get("/api/experiments/{experiment_id}/history")
    def input_history(experiment_id: UUID):
        try:
            return store.history(experiment_id)
        except KeyError:
            raise HTTPException(404, "저장된 실험을 찾을 수 없습니다.") from None

    @app.post("/api/experiments/{experiment_id}/history/{direction}", response_model=Snapshot)
    def restore_inputs(experiment_id: UUID, direction: Literal["undo", "redo"], body: HistoryMove):
        exp, revision, old_level = load(experiment_id, body.revision)
        target = store.history_target(experiment_id, direction)
        if target is None:
            raise HTTPException(409, "이 방향으로 복원할 조건이 없습니다.")
        step, patch = target
        level = body.level or old_level
        result = snapshot(build(get_spec(exp.model), experiment_id, patch), revision + 1, level)
        store.move_history(experiment_id, revision, direction, step, level)
        return result

    @app.post("/api/chat")
    async def chat(body: Chat):
        from . import cognitive, grounded
        from .cognitive_routing import route
        from .provider_config import provider_context
        current, revision = None, 0
        if body.experiment_id is not None:
            current, revision, _ = await run_in_threadpool(load, body.experiment_id, body.revision)
        message = body.message.strip()
        if clarification.stale_dialogue(body.dialogue, message, current.id if current else None,
                                        revision if current else None):
            clarification.retire(body.dialogue)
            notice = clarification.MissingCondition(label="대화 상태", reason="이전 답변이 이미 처리되었거나 실험 조건이 바뀌었습니다.")
            return clarification.response("이전 답변이 이미 처리되었거나 실험 조건이 바뀌었습니다. 최신 질문을 확인한 뒤 다시 답해 주세요.",
                                          body.level, [notice])
        pending = clarification.merge_followup(body.dialogue, message,
                                               current.id if current else None,
                                               revision if current else None, SPECS)
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
                    return clarification.response(clarification.question_for(dialogue.model or "", remaining),
                                                  body.level, remaining, dialogue)
        else:
            dialogue = None
            clarification.retire(body.dialogue)
            special = clarification.special_topic(message)
        excluded = cognitive.excluded_reply(message,body.level)
        if excluded:
            clarification.retire(dialogue)
            return excluded
        selected = route(message,current)
        domain_reason = getattr(selected,"unsupported_reason",None)
        if domain_reason or pending_blocked or clarification.blocked_scope(message, current, special):
            clarification.retire(dialogue)
            topic = "drag" if clarification.drag_only_request(message, current, special) else None
            response, _ = await run_in_threadpool(
                grounded.reading_only, knowledge, message, "explain", body.level, topic,
                domain_reason or (None if topic else reasoning._SCOPE))
            response["classification"] = "unsupported"
            response["dialogue"] = None
            return response
        math_reply = await run_in_threadpool(cognitive.math_turn,message,body.level)
        if math_reply:
            clarification.retire(dialogue)
            return math_reply
        prompt = clarification.identify(message, current, revision if current else None, SPECS)
        if prompt:
            clarification.retire(dialogue)
            return clarification.response(prompt.message, body.level, prompt.missing_conditions, prompt.dialogue)
        if special:
            response, _ = await run_in_threadpool(grounded.reading_only, knowledge, message, "explain", body.level, special)
            response["classification"] = ("sufficient" if response.get("evidence", {}).get("theory_status") == "available"
                                           else "unsupported")
            response["dialogue"] = None
            clarification.retire(dialogue)
            return response
        intent = cognitive.local_plan(message,None if dialogue and dialogue.force_new else current,body.level,selected)
        level = intent.level
        if intent.action == "unsupported":
            need = clarification.plan_failure(message, current, revision if current else None, intent, SPECS)
            if need:
                clarification.retire(dialogue)
                return clarification.response(need.message, level, need.missing_conditions, need.dialogue)
            clarification.retire(dialogue)
            reply, _ = await run_in_threadpool(grounded.reading_only,knowledge,message,"explain",level,None,intent.message)
            reply.update(classification="unsupported",dialogue=None)
            reply.setdefault("answer_state",cognitive.outcome(reply))
            return reply
        if intent.action == "create":
            exp = build(get_spec(intent.model), dialogue.target_experiment_id if dialogue else uuid4(), intent.patch)
            prior = 0
        else:
            if current is None:
                raise HTTPException(422, "먼저 실험을 선택하세요.")
            exp = build(get_spec(current.model), current.id, intent.patch, current) if intent.action == "modify" else current
            prior = revision
        changed = intent.action != "explain"
        run = await run_in_threadpool(simulate, exp)
        result = Snapshot(experiment=exp, revision=prior + int(changed), run=run, explanation="")
        rows = await run_in_threadpool(grounded.retrieved_for, knowledge, message, exp.model)
        context = await run_in_threadpool(grounded.make_context, knowledge, rows, message, result)
        with provider_context() as metrics:
            metrics.research_context = {**context, "passages":context["passages"][:4]}
            explanation, trace = await cognitive.explain_turn(message,level,"explain",selected,result,context,metrics)
            dossier = await run_in_threadpool(grounded.report, knowledge, rows, context, explanation,
                                              snapshot=result, metrics=metrics, level=level, question=message)
            cognitive.finish_trace(trace,dossier,explanation)
        result = result.model_copy(update={"explanation":dossier["core"]})
        lesson = dict(mode="explain",title=exp.title,text=dossier["core"],prompt="",actions=[],evidence=dossier)
        if changed:
            await run_in_threadpool(store.save, exp, level, prior)
        else:
            await run_in_threadpool(load, exp.id, prior)
        clarification.retire(dialogue)
        classification, assumed_values = clarification.result_classification(
            intent.action, exp, intent.patch, result.run.status)
        assumptions = assumed_values
        reply = {"action": intent.action, "status": result.run.status, "message": result.explanation,
                "snapshot": result, "level": level,"lesson":lesson, "classification":classification,
                "assumptions":assumptions, "dialogue":None,"evidence":dossier,"pipeline":trace,
                **cognitive.contract_receipt(intent.action,result,intent.patch,current.id if current else None,
                                            revision if current else None,level)}
        reply["answer_state"] = cognitive.outcome(reply)
        return reply

    from .studio import studio_router
    from .provider_routes import router as provider_router
    from .science_api import router as science_router
    from .knowledge_api import router as knowledge_router
    from .math_router import router as math_router
    from .study_api import study_router
    app.include_router(studio_router(store, boards, load, get_spec, snapshot, Snapshot, knowledge, names))
    app.include_router(portable_router(store, boards, load, get_spec, names))
    app.include_router(knowledge_router)
    app.include_router(math_router)
    app.include_router(study_router(knowledge, load, snapshot, store.path.parent))
    app.include_router(provider_router)
    app.include_router(science_router)
    dist = ROOT / "frontend" / "dist"
    if dist.joinpath("index.html").is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="laboratory")
    return app


app = create_app()
