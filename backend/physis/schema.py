"""Server-owned experiment format and fixed, finite SI inputs."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Method = Literal["analytic", "euler", "semi_implicit", "rk4"]
Level = Literal["intro", "school", "university", "research"]
Status = Literal["VERIFIED", "LIMITED", "FAILED", "UNSUPPORTED", "UNVERIFIED"]
Number = Annotated[FiniteFloat, Field(strict=True)]


class Variable(StrictModel):
    key: str
    label: str
    unit: str
    min: Number
    max: Number
    step: Annotated[Number, Field(gt=0)]
    default: Number

    @model_validator(mode="after")
    def check_bounds(self):
        if not self.min < self.max or not self.min <= self.default <= self.max:
            raise ValueError("변수 범위와 기본값을 확인하세요.")
        return self


class ModelSpec(StrictModel):
    model: str
    title: str
    category: str
    goal: str
    formula: str
    assumptions: list[str]
    variables: list[Variable]
    methods: list[Method]
    measurements: dict[str, str]  # quantity key -> SI unit
    visualization: str
    comparison: str
    objects: list[str]
    duration: Number = 4.0
    dt: Number = 0.02


class Experiment(ModelSpec):
    id: UUID
    values: dict[str, Number]
    method: Method
    duration: Annotated[Number, Field(ge=0.1, le=30)]
    dt: Annotated[Number, Field(ge=0.002, le=0.2)]

    @model_validator(mode="after")
    def validate_state(self):
        if self.method not in self.methods or self.dt > self.duration or self.duration / self.dt > 4000:
            raise ValueError("적분 방법 또는 시간 격자를 확인하세요 (최대 4,000 스텝).")
        if set(self.values) != {v.key for v in self.variables}:
            raise ValueError("모델에 등록된 변수가 모두 필요합니다.")
        for v in self.variables:
            if not v.min <= self.values[v.key] <= v.max:
                raise ValueError(f"{v.label}의 허용 범위는 {v.min:g}~{v.max:g} {v.unit}입니다.")
        return self


class Patch(StrictModel):
    values: dict[str, Number] = Field(default_factory=dict, max_length=32)
    method: Method | None = None
    duration: Number | None = None
    dt: Number | None = None


class Check(StrictModel):
    label: str
    passed: bool
    detail: str


class Run(StrictModel):
    times: list[FiniteFloat]
    series: dict[str, list[FiniteFloat]]  # object index + "." + quantity, e.g. "0.y"
    status: Status
    checks: list[Check]
    facts: dict[str, FiniteFloat]  # server-supplied fact names and units
    convergence: list[dict[str, FiniteFloat]] = []  # dt, error
