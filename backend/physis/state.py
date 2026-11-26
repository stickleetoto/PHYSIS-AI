"""Persist experiment inputs only. Every run uses the current trusted registry."""
from contextlib import closing
from pathlib import Path
import sqlite3
from uuid import UUID

from .schema import Experiment, Level, ModelSpec, Patch


class RevisionConflict(Exception):
    pass


def build(spec: ModelSpec, experiment_id: UUID, patch: Patch, previous: Experiment | None = None) -> Experiment:
    values = dict(previous.values) if previous else {v.key: v.default for v in spec.variables}
    values.update(patch.values)
    settings = spec.model_dump()
    settings.update(
        id=experiment_id,
        values=values,
        method=previous.method if previous else spec.methods[0],
        duration=previous.duration if previous else spec.duration,
        dt=previous.dt if previous else spec.dt,
    )
    settings.update(patch.model_dump(exclude={"values"}, exclude_none=True))
    return Experiment.model_validate(settings)


class Experiments:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY, revision INTEGER NOT NULL, model TEXT NOT NULL,
                inputs TEXT NOT NULL, level TEXT NOT NULL)""")

    def read(self, experiment_id: UUID):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute(
                "SELECT revision, model, inputs, level FROM experiments WHERE id = ?", (str(experiment_id),)
            ).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        revision, model, inputs, level = row
        return revision, model, Patch.model_validate_json(inputs), level

    def save(self, experiment: Experiment, level: Level, prior: int) -> int:
        with closing(sqlite3.connect(self.path)) as db, db:
            self.write(db, experiment, level, prior)
        return prior + 1

    @staticmethod
    def write(db, experiment: Experiment, level: Level, prior: int):
        inputs = Patch(values=experiment.values, method=experiment.method,
                       duration=experiment.duration, dt=experiment.dt).model_dump_json()
        if prior == 0:
            db.execute("INSERT INTO experiments VALUES (?, 1, ?, ?, ?)",
                       (str(experiment.id), experiment.model, inputs, level))
        else:
            changed = db.execute(
                "UPDATE experiments SET inputs=?, level=?, revision=revision+1 WHERE id=? AND revision=?",
                (inputs, level, str(experiment.id), prior),
            ).rowcount
            if changed != 1:
                raise RevisionConflict()
