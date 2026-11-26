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
            db.executescript("""
                CREATE TABLE IF NOT EXISTS input_history(
                    step INTEGER PRIMARY KEY, experiment TEXT NOT NULL,
                    side TEXT NOT NULL CHECK(side IN ('undo','redo')), inputs TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS history_by_experiment ON input_history(experiment,side,step);
                CREATE TRIGGER IF NOT EXISTS erase_input_history AFTER DELETE ON experiments
                BEGIN DELETE FROM input_history WHERE experiment=OLD.id; END;
            """)

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
            db.execute("BEGIN IMMEDIATE")
            self.write(db, experiment, level, prior)
        return prior + 1

    def history(self, experiment_id: UUID):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("""SELECT e.revision, COUNT(CASE h.side WHEN 'undo' THEN 1 END),
                COUNT(CASE h.side WHEN 'redo' THEN 1 END) FROM experiments e
                LEFT JOIN input_history h ON h.experiment=e.id WHERE e.id=? GROUP BY e.id""",
                (str(experiment_id),)).fetchone()
        if row is None:
            raise KeyError(experiment_id)
        return dict(revision=row[0], undo=row[1], redo=row[2])

    def history_target(self, experiment_id: UUID, side: str):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute("""SELECT step, inputs FROM input_history WHERE experiment=? AND side=?
                ORDER BY step DESC LIMIT 1""", (str(experiment_id), side)).fetchone()
        return (row[0], Patch.model_validate_json(row[1])) if row else None

    def move_history(self, experiment_id: UUID, prior: int, side: str, step: int, level: Level):
        eid = str(experiment_id)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT inputs FROM experiments WHERE id=? AND revision=?", (eid, prior)).fetchone()
            target = db.execute("SELECT inputs FROM input_history WHERE experiment=? AND side=? AND step=?",
                                (eid, side, step)).fetchone()
            if not current or not target:
                raise RevisionConflict()
            db.execute("DELETE FROM input_history WHERE step=?", (step,))
            db.execute("INSERT INTO input_history(experiment,side,inputs) VALUES(?,?,?)",
                       (eid, "redo" if side == "undo" else "undo", current[0]))
            db.execute("UPDATE experiments SET inputs=?,level=?,revision=revision+1 WHERE id=?", (target[0], level, eid))

    @staticmethod
    def write(db, experiment: Experiment, level: Level, prior: int):
        inputs = Patch(values=experiment.values, method=experiment.method,
                       duration=experiment.duration, dt=experiment.dt).model_dump_json()
        if prior == 0:
            db.execute("INSERT INTO experiments VALUES (?, 1, ?, ?, ?)",
                       (str(experiment.id), experiment.model, inputs, level))
        else:
            eid = str(experiment.id)
            previous = db.execute("SELECT inputs FROM experiments WHERE id=? AND revision=?", (eid, prior)).fetchone()
            if not previous:
                raise RevisionConflict()
            changed = db.execute(
                "UPDATE experiments SET inputs=?, level=?, revision=revision+1 WHERE id=? AND revision=?",
                (inputs, level, str(experiment.id), prior),
            ).rowcount
            if changed != 1:
                raise RevisionConflict()
            if Patch.model_validate_json(previous[0]) != Patch.model_validate_json(inputs):
                db.execute("DELETE FROM input_history WHERE experiment=? AND side='redo'", (eid,))
                db.execute("INSERT INTO input_history(experiment,side,inputs) VALUES(?,'undo',?)", (eid, previous[0]))
                db.execute("""DELETE FROM input_history WHERE step IN (SELECT step FROM input_history
                    WHERE experiment=? ORDER BY step DESC LIMIT -1 OFFSET 50)""", (eid,))
