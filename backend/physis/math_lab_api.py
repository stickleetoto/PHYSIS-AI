"""Offline, finite Mathematics Laboratory jobs. Closing a request stops its worker."""
import asyncio
import json
import subprocess
import sys
from threading import BoundedSemaphore, Event
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import Field, model_validator

from .math_router import WORKER
from .schema import StrictModel

router = APIRouter(prefix="/api/math-lab")
_slots = BoundedSemaphore(1)
TIME_LIMIT = 8.0
STARTUP_LIMIT = 18.0
MAX_OUTPUT = 512_000
Coordinate = Annotated[float, Field(strict=True, ge=-1000, le=1000)]


class LabRequest(StrictModel):
    mode: Literal["function", "limit", "derivative", "integral"]
    expression: str = Field(min_length=1, max_length=180)
    other: str | None = Field(default=None, min_length=1, max_length=180)
    params: dict[Literal["a", "b", "c"], Coordinate] = Field(default_factory=dict)
    lo: Coordinate = -5
    hi: Coordinate = 5
    point: Coordinate = 1
    step: Coordinate = 0.5
    lower: Coordinate | None = 0
    upper: Coordinate | None = 2
    divisions: int = Field(strict=True, ge=2, le=64, default=8)

    @model_validator(mode="after")
    def check_window(self):
        if self.hi <= self.lo or self.hi - self.lo < 1e-5:
            raise ValueError("표시 범위는 왼쪽에서 오른쪽으로 최소 0.00001이어야 합니다.")
        if self.step <= 0:
            raise ValueError("접근 간격은 0보다 커야 합니다.")
        if (self.lower is None) != (self.upper is None):
            raise ValueError("정적분의 양 끝점을 함께 입력하세요.")
        return self


Row = Annotated[list[Coordinate], Field(min_length=1, max_length=5)]
Matrix = Annotated[list[Row], Field(min_length=1, max_length=5)]


class MatrixRequest(StrictModel):
    a: Matrix
    b: Matrix
    rhs: Row

    @model_validator(mode="after")
    def rectangular(self):
        if any(len(r) != len(matrix[0]) for matrix in (self.a, self.b) for r in matrix):
            raise ValueError("각 행렬의 행 길이를 같게 입력하세요.")
        if len(self.rhs) != len(self.a):
            raise ValueError("우변의 길이는 A의 행 수와 같아야 합니다.")
        return self


def unavailable(detail):
    return {"status": "unverifiable", "detail": detail}


@router.post("/calculate")
async def calculate_lab(request: Request, settings: LabRequest):
    return await run_worker(request, {"laboratory": settings.model_dump()})


@router.post("/matrix")
async def calculate_matrix(request: Request, settings: MatrixRequest):
    return await run_worker(request, {"matrix": settings.model_dump()})


class NumericRequest(StrictModel):
    expression: str = Field(min_length=1, max_length=180)
    lo: Coordinate = 1
    hi: Coordinate = 2
    tolerance: float = Field(strict=True, ge=1e-12, le=0.1, default=1e-7)
    iterations: int = Field(strict=True, ge=1, le=48, default=32)
    h: float = Field(strict=True, ge=1e-8, le=100, default=0.1)
    reference: Coordinate | None = None
    divisions: int = Field(strict=True, ge=4, le=64, default=16)

    @model_validator(mode="after")
    def bounds(self):
        if self.lo >= self.hi:
            raise ValueError("두 초깃값을 작은 값부터 입력하세요.")
        if self.divisions % 2:
            raise ValueError("Simpson 비교에는 짝수 분할 수가 필요합니다.")
        return self


@router.post("/numeric")
async def calculate_numeric(request: Request, settings: NumericRequest):
    return await run_worker(request, {"numeric": settings.model_dump()})


async def run_worker(request: Request, data):
    clock = asyncio.get_running_loop().time
    admission_deadline = clock() + 0.6
    while not _slots.acquire(blocking=False):
        if await request.is_disconnected() or clock() >= admission_deadline:
            return unavailable("다른 수학 실험이 계산 중입니다. 잠시 후 다시 계산하세요.")
        await asyncio.sleep(0.04)
    child = None
    task = None
    try:
        payload = json.dumps(data, allow_nan=False).encode("ascii")
        child = subprocess.Popen([sys.executable, "-I", "-B", str(WORKER), "--notify-ready"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        ready = Event()
        task = asyncio.create_task(asyncio.to_thread(exchange, child, payload, ready))
        deadline = clock() + STARTUP_LIMIT
        computing = False
        while not task.done():
            if await request.is_disconnected():
                return unavailable("요청이 취소되어 계산을 종료했습니다.")
            if not computing and ready.is_set():
                computing = True
                deadline = clock() + TIME_LIMIT
            if clock() >= deadline:
                return unavailable("계산 시간 제한을 넘겨 작업을 종료했습니다." if computing else
                                   "계산 도구의 시작 시간 제한을 넘겨 작업을 종료했습니다.")
            await asyncio.wait({task}, timeout=0.05)
        output = task.result()
        if child.returncode or len(output) > MAX_OUTPUT:
            return unavailable("격리된 계산 결과가 허용 범위를 벗어났습니다.")
        return json.loads(output)
    except (OSError, ValueError):
        return unavailable("격리된 계산 도구의 응답을 읽을 수 없습니다.")
    finally:
        try:
            if child is not None and child.poll() is None:
                child.kill()
            if task is not None:
                try:
                    await asyncio.shield(task)
                except OSError:
                    pass  # Killing a cancelled worker can close its input pipe.
        finally:
            _slots.release()


def exchange(child, payload, ready):
    """Separate fixed-library startup from the time budget for user mathematics."""
    with child.stdin, child.stdout:
        child.stdin.write(payload)
        child.stdin.close()
        line = child.stdout.readline(MAX_OUTPUT + 1)
        if line.rstrip(b"\r\n") == b"READY":
            ready.set()
            output = child.stdout.read(MAX_OUTPUT + 1)
        else:
            output = line  # A startup error can return JSON before readiness.
        if len(output) > MAX_OUTPUT:
            child.kill()
        child.wait()
        return output
