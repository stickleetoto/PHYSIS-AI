"""Read-only formula lookup and isolated, bounded symbolic operations."""
import json
from pathlib import Path
import subprocess
import sys
from threading import BoundedSemaphore
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import Field, StringConstraints

from .formula_registry import UNITS, check_applicability, formula_by_id, search_formulas
from .schema import StrictModel

router = APIRouter(prefix="/api")
WORKER = Path(__file__).with_name("symbolic_worker.py")
WORKER_TIMEOUT = 8
_slots = BoundedSemaphore(2)
Name = Annotated[str,StringConstraints(pattern=r"^[A-Za-z][A-Za-z0-9_]{0,15}$")]
Unit = Annotated[str,StringConstraints(min_length=1,max_length=12)]
Value = Annotated[float,Field(strict=True,ge=-1_000_000,le=1_000_000)]
Domain = Literal["real","positive","nonnegative","nonzero"]


class MathRequest(StrictModel):
    operation: Literal["simplify","solve","differentiate","integrate","substitute","equivalent","dimension","graph","compare","compare_root"]
    expression: str = Field(min_length=1,max_length=180)
    other: str | None = Field(default=None,min_length=1,max_length=180)
    variable: Name = "x"
    domain: Domain = "real"
    other_domain: Domain | None = None
    values: dict[Name,Value] = Field(default_factory=dict,max_length=12)
    units: dict[Name,Unit] = Field(default_factory=dict,max_length=12)
    lower: Value = -2.0
    upper: Value = 2.0


@router.get("/formulas")
def library(q: str=Query("",max_length=120), model: str|None=Query(None,max_length=64)):
    return {"items":search_formulas(q,model),"units":list(UNITS)}


@router.get("/formulas/{formula_id}")
def detail(formula_id: str):
    result = formula_by_id(formula_id)
    if result is None: raise HTTPException(404,"등록된 공식이 없습니다.")
    return result


def bounded_calculate(data):
    if not _slots.acquire(blocking=False):
        return {"status":"unverifiable","detail":"두 계산 작업이 실행 중입니다. 잠시 후 다시 시도하세요."}
    try:
        child = subprocess.run([sys.executable,"-I","-B",str(WORKER)],
            input=json.dumps(data,allow_nan=False).encode("ascii"),capture_output=True,
            timeout=WORKER_TIMEOUT,check=False,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if child.returncode!=0 or len(child.stdout)>64_000:
            return {"status":"unverifiable","detail":"제한된 계산 프로세스가 결과를 반환하지 못했습니다."}
        return json.loads(child.stdout)
    except subprocess.TimeoutExpired:
        return {"status":"unverifiable","detail":"계산 시간 제한을 넘겨 작업을 종료했습니다."}
    except (OSError,ValueError):
        return {"status":"unverifiable","detail":"격리된 계산 도구를 시작하거나 결과를 읽을 수 없습니다."}
    finally:
        _slots.release()


@router.post("/math")
def mathematics(request: MathRequest):
    return bounded_calculate(request.model_dump())


def check_formula_claim(formula_id, experiment, expression=None, units=None):
    """Check independent parts of a claimed registered formula for an actual experiment."""
    record = formula_by_id(formula_id)
    if not record:
        return {"status":"failed","reason":"미등록 공식입니다."}
    applicability = check_applicability(formula_id,experiment)
    if expression is None and units is None:
        return applicability
    expected = {v["name"]:v["unit"] for v in record["variables"]}
    result = dict(applicability=applicability,**applicability)
    if units is not None:
        same = units==expected
        result["units_check"] = {"status":"verified" if same else "failed",
            "detail":"등록된 전체 변수와 SI 단위가 일치합니다." if same else "제출한 변수 이름 또는 SI 단위가 등록 명세와 다릅니다."}
    if expression is not None:
        if not isinstance(expression,str) or len(expression)>180:
            checked = {"status":"invalid","detail":"우변 수식은 180자 이내여야 합니다."}
        elif expression.strip()==record["expression"]:
            checked = {"status":"verified","detail":"등록된 우변의 기계 판독식과 일치합니다."}
        else:
            checked = bounded_calculate(dict(operation="registered_relation",expression=expression,
                other=record["expression"],units=expected,lhs=record["lhs"]))
        result["expression_check"] = checked
    checks = [result[k] for k in ("units_check","expression_check") if k in result]
    failed = next((c for c in checks if c["status"] in ("failed","invalid","domain_mismatch")),None)
    uncertain = next((c for c in checks if c["status"]=="unverifiable"),None)
    if failed:
        result.update(status="failed",reason=failed["detail"])
    elif uncertain and result["status"]=="applicable":
        result.update(status="unverifiable",reason=uncertain["detail"])
    return result
