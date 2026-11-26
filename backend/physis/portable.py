"""Versioned portable experiment sets and display-only experiment names."""
from contextlib import closing
import json
import sqlite3
import unicodedata
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .schema import Level, Method, Number, StrictModel


PORTABLE_FORMAT = "physis-ai/experiment-set"
PORTABLE_VERSION = 1
MAX_PORTABLE_BYTES = 128 * 1024
MAX_EXPERIMENTS = 4
MAX_DISPLAY_NAME = 80


def clean_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    if any(unicodedata.category(character) == "Cc" for character in value):
        raise ValueError("표시 이름에 제어 문자를 사용할 수 없습니다.")
    value = value.strip()
    if not value:
        raise ValueError("표시 이름을 비우려면 null을 사용하세요.")
    if len(value) > MAX_DISPLAY_NAME:
        raise ValueError(f"표시 이름은 {MAX_DISPLAY_NAME}자 이하여야 합니다.")
    return value


class PortableInputs(StrictModel):
    values: dict[str, Number] = Field(min_length=1, max_length=32)
    method: Method
    duration: Number
    dt: Number


class PortableExperiment(StrictModel):
    key: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=64)
    level: Level
    inputs: PortableInputs
    source_revision: int = Field(ge=1, strict=True)
    display_name: str | None = Field(default=None, max_length=MAX_DISPLAY_NAME)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value):
        return clean_display_name(value)


class PortableView(StrictModel):
    elapsed: Number = Field(ge=0, le=30)
    speed: Literal[0.25, 0.5, 1.0, 2.0, 4.0]
    quantity: str | None = Field(default=None, max_length=64)
    object_index: int = Field(ge=0, le=31, strict=True)

    @field_validator("speed", mode="before")
    @classmethod
    def validate_speed(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value not in {0.25, 0.5, 1, 2, 4}:
            raise ValueError("재생 속도는 0.25, 0.5, 1, 2, 4 중 하나여야 합니다.")
        return float(value)

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value):
        if value is not None and any(unicodedata.category(character) == "Cc" for character in value):
            raise ValueError("물리량 키에 제어 문자를 사용할 수 없습니다.")
        return value


DEFAULT_VIEW = PortableView(elapsed=0, speed=1.0, quantity=None, object_index=0)


class PortableComparison(StrictModel):
    anchor: str = Field(min_length=1, max_length=32)
    order: list[str] = Field(min_length=1, max_length=MAX_EXPERIMENTS)
    active: str = Field(min_length=1, max_length=32)
    view: PortableView = Field(default_factory=lambda: DEFAULT_VIEW.model_copy(deep=True))


class PortableBundle(StrictModel):
    format: Literal["physis-ai/experiment-set"]
    format_version: int = Field(ge=1, le=1, strict=True)
    experiments: list[PortableExperiment] = Field(min_length=1, max_length=MAX_EXPERIMENTS)
    comparison: PortableComparison

    @model_validator(mode="after")
    def check_members(self):
        keys = [experiment.key for experiment in self.experiments]
        if len(set(keys)) != len(keys):
            raise ValueError("실험 키가 중복되었습니다.")
        if len(set(self.comparison.order)) != len(self.comparison.order):
            raise ValueError("비교 순서에 중복된 실험 키가 있습니다.")
        if set(keys) != set(self.comparison.order):
            raise ValueError("비교 순서와 실험 목록이 일치하지 않습니다.")
        if self.comparison.anchor != self.comparison.order[0]:
            raise ValueError("기준 실험은 비교 순서의 첫 번째여야 합니다.")
        if self.comparison.active not in keys:
            raise ValueError("현재 실험이 비교 목록에 없습니다.")
        return self

    def encoded(self) -> bytes:
        return json.dumps(self.model_dump(mode="json"), ensure_ascii=False,
                          allow_nan=False, separators=(",", ":")).encode("utf-8")


class DisplayNames:
    """Display labels are independent of immutable physics model titles."""

    def __init__(self, database: str | None = None):
        self.database = database

    def _connect(self, path=None):
        return sqlite3.connect(path or self.database)

    @staticmethod
    def ensure(db):
        db.execute("""CREATE TABLE IF NOT EXISTS experiment_display_names (
            experiment_id TEXT PRIMARY KEY,
            display_name TEXT,
            name_revision INTEGER NOT NULL DEFAULT 0)""")
        db.execute("""CREATE TRIGGER IF NOT EXISTS erase_experiment_display_name AFTER DELETE ON experiments
            BEGIN DELETE FROM experiment_display_names WHERE experiment_id=OLD.id; END;""")

    def get(self, experiment_id: UUID, path=None):
        with closing(self._connect(path)) as db, db:
            self.ensure(db)
            row = db.execute(
                "SELECT display_name, name_revision FROM experiment_display_names WHERE experiment_id=?",
                (str(experiment_id),),
            ).fetchone()
        return (row[0], row[1]) if row else (None, 0)

    @classmethod
    def write_in_transaction(cls, db, experiment_id: UUID, display_name: str | None,
                             expected_name_revision: int | None = None):
        cls.ensure(db)
        row = db.execute(
            "SELECT name_revision FROM experiment_display_names WHERE experiment_id=?",
            (str(experiment_id),),
        ).fetchone()
        current_name_revision = row[0] if row else 0
        if expected_name_revision is not None and expected_name_revision != current_name_revision:
            from .state import RevisionConflict
            raise RevisionConflict()
        new_revision = current_name_revision + 1
        db.execute(
            "INSERT INTO experiment_display_names VALUES (?, ?, ?) "
            "ON CONFLICT(experiment_id) DO UPDATE SET display_name=excluded.display_name, "
            "name_revision=excluded.name_revision",
            (str(experiment_id), display_name, new_revision),
        )
        return new_revision

    def set(self, experiment_id: UUID, display_name: str | None, expected_revision: int,
            expected_name_revision: int | None = None):
        from .state import RevisionConflict
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT revision FROM experiments WHERE id=?", (str(experiment_id),)).fetchone()
            if current is None:
                raise KeyError(experiment_id)
            if current[0] != expected_revision:
                raise RevisionConflict()
            name_revision = self.write_in_transaction(
                db, experiment_id, clean_display_name(display_name), expected_name_revision)
            return name_revision
