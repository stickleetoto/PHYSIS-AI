from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from physis import evidence
from physis.api import create_app, snapshot
from physis.grounded import make_context, report
from physis.knowledge import KnowledgeStore
from physis.physics import SPECS
from physis.schema import Patch
from physis.state import build


@pytest.fixture
def reading(tmp_path):
    store = KnowledgeStore(tmp_path / "research.db")
    store.initialize()
    rows = store.search("Newton second law net force mass acceleration",model="newton",limit=8)
    return store, rows


def one_run():
    exp = build(SPECS["newton"],uuid4(),Patch(values={"force":12,"mass":3}))
    return snapshot(exp,2,"school")


def test_independent_quote_checks(reading):
    store, rows = reading
    row = next(r for r in rows if "inversely proportional" in r["text"])
    c = dict(id=row["id"],doc_id=row["doc_id"],locator=row["locator"],quote="inversely proportional")
    assert evidence.check_quote(store,rows,c)["status"] == "source_verified"
    for changes in ({"quote":"increases as the square of mass"},{"doc_id":"invented"},{"locator":"p. 3498"}):
        assert evidence.check_quote(store,rows,c | changes)["status"] == "failed"
    assert evidence.check_quote(store,[],c)["status"] == "insufficient"


def test_measurements_checked_independently():
    s = one_run()
    n = evidence.NumberClaim(key="acceleration",value=4,unit="m/s²",experiment_id=str(s.experiment.id),
                             revision=2,run_id=evidence.run_id(s))
    assert evidence.check_number(n,s)["status"]=="calculation_verified"
    for changes in ({"value":99},{"unit":"m/s"},{"revision":1},{"run_id":"stale"},{"experiment_id":str(uuid4())}):
        assert evidence.check_number(n.model_copy(update=changes),s)["status"]=="failed"
    assert evidence.check_number(n.model_copy(update={"key":"unobserved"}),s)["status"]=="unverifiable"
    wrong = evidence.check_reported_numbers("가속도 99 m/s², 마지막 위치 10 kg입니다.",s)
    assert len(wrong)==2 and all(r["status"]=="failed" for r in wrong)


def test_provider_mismatch_surfaces_end_to_end(tmp_path,monkeypatch):
    import json
    from physis import reasoning
    from physis.provider_config import current_context
    monkeypatch.setenv("PHYSIS_AI_PROVIDER","mock")
    async def erroneous_reading(*args):
        metrics = current_context.get().metrics
        real = metrics.research_context["calculations"][0]
        metrics.proposed_numbers = [{k:real[k] for k in ("key","unit","experiment_id","revision","run_id")} | {"value":99}]
        metrics.proposed_sources = ["a-paper-the-search-never-returned"]
        return "가속도 99 m/s²"
    monkeypatch.setattr(reasoning,"interpret",erroneous_reading)
    with TestClient(create_app(tmp_path/"lab.db")) as client:
        s=client.post("/api/experiments",json={"model":"newton"}).json()
        question={"experiment_id":s["experiment"]["id"],"revision":1,"message":"현재 실험을 설명해 줘"}
        response=client.post("/api/tutor/stream",json=question)
        r=json.loads(response.text.splitlines()[-1])["result"]
        e=r["lesson"]["evidence"]
        assert e["sources"]==[]
        assert any(row.get("value")==99 and row["status"]=="failed" for row in e["checks"])
        assert e["calculations"][0]["value"]==s["run"]["facts"]["acceleration"]
        assert e["calculations"][0]["value"] != 99 and r["snapshot"]["revision"]==1
        assert "가속도 99 m/s²" not in r["message"] and "검산값" in r["message"]


def test_reviewed_paraphrases_require_the_actual_passage(reading):
    store, rows = reading
    s = one_run()
    context = make_context(store,rows,"Newton second law",s)
    dossier = report(store,rows,context,"이번 실행에서 가속도 4 m/s²입니다.",snapshot=s)
    sources = {v["id"]:v["quote"] for v in dossier["sources"]}
    assert any(c["kind"]=="reviewed_paraphrase" and c["references"][0] in sources for c in dossier["claims"])
    assert all(claim["status"]!="source_verified" for claim in dossier["claims"] if claim["kind"]=="explanation")


def test_explicit_source_conflict_needs_distinct_supported_comparable_statements():
    class Corpus:
        def chunk(self, key):
            return next(r for r in rows if r["id"]==key)
    rows = [dict(id=k,doc_id=k,title=k,locator="§ 2 ¶1",license="test",url="https://example.org/"+k,
                 publisher="synthetic unit fixture",citable=True,text=f"At temperature T, speed is {v} m/s.") for k,v in (("a",1),("b",2))]
    claims=[dict(id=r["id"],doc_id=r["doc_id"],locator=r["locator"],quote=r["text"],literal=str(i+1),
                 unit="m/s",scope="temperature T",quantity="speed") for i,r in enumerate(rows)]
    assert evidence.compare_source_values(Corpus(),rows,claims)[0]["status"]=="conflict"
    assert not evidence.compare_source_values(Corpus(),rows,[claims[0],claims[1]|{"scope":"another experiment"}])
    assert not evidence.compare_source_values(Corpus(),rows,[claims[0],claims[1]|{"literal":"8"}])
    rows[1]["text"] = "At temperature T, speed is -2 m/s and a different speed is 2 m/s²."
    claims[1]["quote"] = rows[1]["text"]
    assert not evidence.compare_source_values(Corpus(),rows,claims)


def test_lab_chat_delivers_the_checked_explanation_in_every_view(tmp_path, monkeypatch):
    from physis import reasoning
    async def bad_reading(*args):
        return "가속도 99 m/s²"
    monkeypatch.setenv("PHYSIS_AI_PROVIDER","mock")
    monkeypatch.setattr(reasoning,"interpret",bad_reading)
    with TestClient(create_app(tmp_path/"lab.db")) as client:
        exp = client.post("/api/experiments",json={"model":"newton"}).json()
        request = {"experiment_id":exp["experiment"]["id"], "revision":1, "message":"현재 실험 설명해 줘"}
        r = client.post("/api/chat",json=request).json()
        assert r["message"] == r["lesson"]["evidence"]["core"] == r["lesson"]["text"] == r["snapshot"]["explanation"]
        assert "검산값" in r["message"] and "99" not in r["message"]


def test_roadmap_and_candidate_separation(tmp_path):
    from physis.curriculum import NODES
    from physis.grounded import FOUNDATIONS
    assert FOUNDATIONS.keys() <= NODES.keys()
    with TestClient(create_app(tmp_path/"lab.db")) as c:
        graph=c.get("/api/curriculum").json()
        assert len(graph["levels"])==6 and len(graph["nodes"])>=16
        original=graph["edges"]
        c.post("/api/curriculum/candidates",json={"source":"units","target":"mass","type":"related"}).raise_for_status()
        assert c.get("/api/curriculum").json()["edges"]==original
        assert not c.post("/api/curriculum/vectors/answer",json={"choice":0}).json()["correct"]
        assert c.post("/api/curriculum/vectors/answer",json={"choice":2}).json()["correct"]
        before=c.get("/api/knowledge/stats").json()
        c.delete("/api/learning").raise_for_status()
        assert c.get("/api/knowledge/stats").json()==before

