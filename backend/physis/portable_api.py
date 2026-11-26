"""HTTP endpoints for versioned, JSON-only experiment set transfer."""
from contextlib import closing
import json
import sqlite3
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .portable import (MAX_PORTABLE_BYTES, DEFAULT_VIEW, DisplayNames, PortableBundle,
                       PortableComparison, PortableExperiment, PortableInputs, PortableView,
                       PORTABLE_FORMAT, PORTABLE_VERSION, clean_display_name)
from .physics import simulate
from .schema import Patch, StrictModel
from .state import RevisionConflict, build


class PortableExportRequest(StrictModel):
    experiment_id: UUID
    revision: int = Field(ge=1, strict=True)
    view: PortableView = Field(default_factory=lambda: DEFAULT_VIEW.model_copy(deep=True))


class DisplayNameUpdate(StrictModel):
    revision: int = Field(ge=1, strict=True)
    name_revision: int | None = Field(default=None, ge=0, strict=True)
    display_name: str | None = Field(default=None, max_length=80)


class DuplicateJSONKey(ValueError):
    pass


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKey("duplicate JSON key")
        result[key] = value
    return result


async def bounded_body(request: Request) -> bytes:
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_PORTABLE_BYTES:
            raise HTTPException(413, "실험 파일이 허용 크기(128 KiB)를 초과했습니다.")
        chunks.append(chunk)
    return b"".join(chunks)


def checked_view_unit(view, experiment, unit_so_far, run=None):
    if view.object_index >= len(experiment.objects):
        raise HTTPException(422, "저장된 비교 물체가 실험에 없습니다.")
    if view.quantity is None:
        return None
    unit = experiment.measurements.get(view.quantity)
    if unit is None or (unit_so_far is not None and unit != unit_so_far):
        raise HTTPException(422, "모든 실험에서 같은 단위로 비교 가능한 물리량이 필요합니다.")
    if run is None:
        run = simulate(experiment)
    if "0." + view.quantity not in run.series:
        raise HTTPException(422, "저장된 물리량의 측정값이 없습니다.")
    return unit


def preflight_and_import(bundle: PortableBundle, store, get_spec):
    keyed_experiments = {experiment.key: experiment for experiment in bundle.experiments}
    by_key = {}
    validated = {}
    view = bundle.comparison.view
    quantity_unit = None
    for key in bundle.comparison.order:
        incoming = keyed_experiments[key]
        spec = get_spec(incoming.model)
        expected_values = {variable.key for variable in spec.variables}
        if set(incoming.inputs.values) != expected_values:
            raise HTTPException(422, "등록된 모델의 입력 변수가 모두 정확히 필요합니다.")
        experiment_id = uuid4()
        patch = Patch(values=incoming.inputs.values, method=incoming.inputs.method,
                      duration=incoming.inputs.duration, dt=incoming.inputs.dt)
        experiment = build(spec, experiment_id, patch)
        run = simulate(experiment)
        quantity_unit = checked_view_unit(view, experiment, quantity_unit, run)
        by_key[key] = experiment_id
        validated[key] = (experiment, incoming.level, incoming.display_name)

    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        DisplayNames.ensure(db)
        for key in bundle.comparison.order:
            experiment, level, display_name = validated[key]
            store.write(db, experiment, level, 0)
            if display_name is not None:
                DisplayNames.write_in_transaction(db, experiment.id,
                                                  clean_display_name(display_name))
        for ordinal, key in enumerate(bundle.comparison.order):
            db.execute("INSERT INTO bench_members(member,anchor,ordinal) VALUES (?,?,?)",
                       (str(by_key[key]), str(by_key[bundle.comparison.anchor]), ordinal))

    active_key = bundle.comparison.active
    return {
        "active_id": str(by_key[active_key]),
        "level": validated[active_key][1],
        "experiment_ids": {key: str(experiment_id) for key, experiment_id in by_key.items()},
        "view": bundle.comparison.view.model_dump(mode="json"),
    }


def portable_router(store, boards, load, get_spec, names: DisplayNames):
    router = APIRouter(prefix="/api")

    @router.post("/portable/experiments/export")
    def export_experiments(body: PortableExportRequest):
        with closing(sqlite3.connect(store.path)) as db, db:
            db.row_factory = sqlite3.Row
            DisplayNames.ensure(db)
            db.commit()
            db.execute("BEGIN")
            requested = db.execute("SELECT revision FROM experiments WHERE id=?",
                                   (str(body.experiment_id),)).fetchone()
            if requested is None:
                raise HTTPException(404, "저장된 실험을 찾을 수 없습니다.")
            if requested["revision"] != body.revision:
                raise RevisionConflict()
            membership = db.execute("SELECT anchor FROM bench_members WHERE member=?",
                                    (str(body.experiment_id),)).fetchone()
            anchor_id = UUID(membership["anchor"]) if membership else body.experiment_id
            if membership:
                member_ids = [UUID(row["member"]) for row in db.execute(
                    "SELECT member FROM bench_members WHERE anchor=? ORDER BY ordinal",
                    (membership["anchor"],),
                )]
            else:
                member_ids = [body.experiment_id]
            if len(member_ids) > 4 or body.experiment_id not in member_ids:
                raise HTTPException(409, "비교 실험 구성을 불러올 수 없습니다.")
            key_by_id = {member_id: f"experiment-{index + 1}" for index, member_id in enumerate(member_ids)}
            experiments = []
            quantity_unit = None
            for member_id in member_ids:
                row = db.execute("SELECT revision,model,inputs,level FROM experiments WHERE id=?",
                                 (str(member_id),)).fetchone()
                if row is None:
                    raise HTTPException(409, "비교 실험 구성을 불러올 수 없습니다.")
                experiment = build(get_spec(row["model"]), member_id, Patch.model_validate_json(row["inputs"]))
                quantity_unit = checked_view_unit(body.view, experiment, quantity_unit)
                name = db.execute("SELECT display_name FROM experiment_display_names WHERE experiment_id=?",
                                  (str(member_id),)).fetchone()
                experiments.append(PortableExperiment(
                    key=key_by_id[member_id], model=experiment.model, level=row["level"],
                    inputs=PortableInputs(values=experiment.values, method=experiment.method,
                                          duration=experiment.duration, dt=experiment.dt),
                    source_revision=row["revision"], display_name=name["display_name"] if name else None,
                ))
        bundle = PortableBundle(
            format=PORTABLE_FORMAT, format_version=PORTABLE_VERSION,
            experiments=experiments,
            comparison=PortableComparison(
                anchor=key_by_id[anchor_id],
                order=[key_by_id[member_id] for member_id in member_ids],
                active=key_by_id[body.experiment_id], view=body.view,
            ),
        )
        encoded = bundle.encoded()
        if len(encoded) > MAX_PORTABLE_BYTES:
            raise HTTPException(413, "실험 파일이 허용 크기(128 KiB)를 초과했습니다.")
        return JSONResponse(
            content=bundle.model_dump(mode="json"),
            headers={"Content-Disposition": 'attachment; filename="physis-ai-experiments-v1.json"'},
        )

    @router.post("/portable/experiments/import")
    async def import_experiments(request: Request):
        raw = await bounded_body(request)
        try:
            payload = json.loads(raw, object_pairs_hook=unique_json_object)
        except (json.JSONDecodeError, UnicodeDecodeError, DuplicateJSONKey, RecursionError, ValueError) as exc:
            raise HTTPException(422, "실험 JSON 파일을 확인하세요.") from exc
        try:
            bundle = PortableBundle.model_validate(payload)
        except (ValidationError, RecursionError) as exc:
            raise HTTPException(422, "실험 파일의 형식이나 입력값을 확인하세요.") from exc
        return await run_in_threadpool(preflight_and_import, bundle, store, get_spec)

    @router.patch("/experiments/{experiment_id}/display-name")
    def update_display_name(experiment_id: UUID, body: DisplayNameUpdate):
        try:
            name_revision = names.set(experiment_id, body.display_name, body.revision,
                                      body.name_revision)
        except KeyError:
            raise HTTPException(404, "저장된 실험을 찾을 수 없습니다.") from None
        except RevisionConflict:
            raise HTTPException(409, "실험 또는 표시 이름이 이미 변경되었습니다. 최신 상태를 불러와 다시 시도하세요.") from None
        return {"id": str(experiment_id), "revision": body.revision,
                "display_name": clean_display_name(body.display_name),
                "name_revision": name_revision}

    @router.get("/experiments/{experiment_id}/display-name")
    def get_display_name(experiment_id: UUID):
        _, revision, _ = load(experiment_id)
        display_name, name_revision = names.get(experiment_id)
        return {"id": str(experiment_id), "revision": revision,
                "display_name": display_name, "name_revision": name_revision}

    return router
