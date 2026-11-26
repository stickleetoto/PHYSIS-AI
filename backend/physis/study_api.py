"""Read-only evidence audit, classroom roadmap, and separately stored graph proposals."""
from contextlib import closing
from pathlib import Path
import sqlite3
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import Field

from . import curriculum, evidence
from .math_router import Name, Unit, check_formula_claim
from .schema import StrictModel


class Citation(StrictModel):
    id: str = Field(max_length=180)
    doc_id: str = Field(max_length=180)
    locator: str = Field(max_length=512)
    quote: str = Field(min_length=1,max_length=900)


class SourceValue(Citation):
    literal: str = Field(max_length=30)
    unit: str = Field(max_length=32)
    quantity: str = Field(max_length=60)
    scope: str = Field(max_length=120)


class Audit(StrictModel):
    experiment_id: UUID
    revision: int = Field(ge=1)
    query: str = Field(min_length=1,max_length=2000)
    citations: list[Citation] = Field(default_factory=list,max_length=6)
    numbers: list[evidence.NumberClaim] = Field(default_factory=list,max_length=6)
    formula_id: str | None = Field(default=None,max_length=80)
    formula_expression: str | None = Field(default=None,min_length=1,max_length=180)
    formula_units: dict[Name, Unit] | None = Field(default=None,max_length=16)
    source_values: list[SourceValue] = Field(default_factory=list,max_length=8)


class Answer(StrictModel):
    choice: int = Field(ge=0,le=12,strict=True)


class Candidate(StrictModel):
    source: str = Field(max_length=64)
    target: str = Field(max_length=64)
    type: Literal["prerequisite","related","broader","narrower"]


def study_router(knowledge, load, make_snapshot, folder: Path):
    router = APIRouter(prefix="/api")

    @router.post("/evidence/check")
    def audit(body: Audit):
        exp, revision, level = load(body.experiment_id, body.revision)
        result = make_snapshot(exp,revision,level)
        found = knowledge.search(body.query,model=exp.model,limit=8)
        formula = None
        if body.formula_id:
            formula = check_formula_claim(body.formula_id, exp, body.formula_expression, body.formula_units)
        elif body.formula_expression is not None or body.formula_units is not None:
            raise HTTPException(422,"비교할 등록 공식의 ID가 필요합니다.")
        return {"sources":[evidence.check_quote(knowledge,found,c.model_dump()) for c in body.citations],
                "calculations":[evidence.check_number(n,result) for n in body.numbers],
                "formula":formula,
                "conflicts":evidence.compare_source_values(knowledge,found,[v.model_dump() for v in body.source_values])}

    @router.get("/curriculum")
    def roadmap():
        return curriculum.graph()

    @router.get("/curriculum/{topic}/resources")
    def resources(topic: str):
        node = curriculum.NODES.get(topic)
        if not node:
            raise HTTPException(404,"개념을 찾을 수 없습니다.")
        rows = knowledge.search(node[3],limit=3)
        return {"readings":[{"title":r["title"],"locator":r["locator"],"id":r["id"],"url":r["url"]} for r in rows if r.get("citable")],
                "models":node[2]}

    @router.post("/curriculum/{topic}/answer")
    def grade(topic: str, body: Answer):
        quiz = curriculum.QUIZZES.get(topic)
        if not quiz or body.choice >= len(quiz[1]):
            raise HTTPException(422,"이 개념의 선택지를 확인하세요.")
        return {"topic":topic,"choice":body.choice,"correct":body.choice==quiz[2],"reason":quiz[3]}

    @router.post("/curriculum/candidates")
    def propose(body: Candidate):
        if body.source == body.target or not {body.source,body.target} <= curriculum.NODES.keys():
            raise HTTPException(422,"서로 다른 등록 개념을 선택하세요.")
        with closing(sqlite3.connect(folder / "concept-candidates.sqlite3")) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS candidates(source TEXT, target TEXT, relation TEXT, PRIMARY KEY(source,target,relation))")
            if not db.execute("SELECT 1 FROM candidates WHERE source=? AND target=? AND relation=?",
                              (body.source,body.target,body.type)).fetchone() and db.execute("SELECT count(*) FROM candidates").fetchone()[0] >= 2000:
                raise HTTPException(409,"후보 저장 한도에 도달했습니다.")
            db.execute("INSERT OR IGNORE INTO candidates VALUES(?,?,?)",(body.source,body.target,body.type))
        return {"status":"unreviewed",**body.model_dump()}
    return router

