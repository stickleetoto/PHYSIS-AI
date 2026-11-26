import json
import sqlite3
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from physis.api import create_app
from physis import reasoning


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER","mock")
    with TestClient(create_app(tmp_path/"local.db")) as client:
        yield client


def create(client, model="free_fall"):
    response = client.post("/api/experiments",json={"model":model})
    assert response.is_success, response.text
    return response.json()


def turn(client,s,message,mode="explain",**overrides):
    result=client.post("/api/tutor/stream",json={"message":message,"experiment_id":s["experiment"]["id"],
                 "revision":s["revision"],"mode":mode,**overrides})
    assert result.is_success,result.text
    return [json.loads(line) for line in result.text.splitlines()]


def test_clone_input_independence_limit_and_concurrent_capacity(client):
    start=create(client)
    eid=start["experiment"]["id"]
    route=f"/api/workbenches/{eid}"
    with ThreadPoolExecutor(4) as pool:
        responses=list(pool.map(lambda n:client.post(route+"/members",json={
            "revision":1,"patch":{"values":{"height":n}}}),[5,10,15,25]))
    assert sorted(x.status_code for x in responses)==[200,200,200,409]
    board=client.get(route).json()
    assert len({s["experiment"]["id"] for s in board["members"]})==4
    assert board["members"][0]["experiment"]["values"]["height"]==20
    child=board["members"][1]
    child_id=child["experiment"]["id"]
    client.patch("/api/experiments/"+child_id,json={"revision":1,"patch":{"values":{"height":12}}}).raise_for_status()
    assert client.get("/api/workbenches/"+child_id).json()["anchor"]==eid
    assert client.get(route).json()["members"][0]["experiment"]["values"]["height"]==20
    assert client.delete(route+"/members/"+eid).status_code==422
    assert client.delete(route+"/members/"+child_id).is_success
    assert len(client.get(route).json()["members"])==3
    assert client.get("/api/experiments/"+child_id).is_success


def test_lesson_highlights_computed_interval_and_seeks(client):
    start=create(client)
    events=turn(client,start,"높이 그래프 0.2초부터 0.8초까지 강조해 줘")
    assert events[0]["event"]=="stage" and any(e["event"]=="text" for e in events)
    last=events[-1]
    assert last["event"]=="result",last
    assert {"op":"highlight_graph","quantity":"y","start":.2,"end":.8} in last["result"]["lesson"]["actions"]
    assert "19.804 m" in last["result"]["message"] and "16.861 m" in last["result"]["message"]
    invalid=turn(client,start,"400초로 이동해 줘")
    assert invalid[-1]["event"]=="error"
    assert client.get("/api/experiments/"+start["experiment"]["id"]).json()["revision"]==1


def test_tutor_comparison_uses_engine_and_keeps_original(client):
    start=create(client,"pendulum")
    events=turn(client,start,"줄 길이를 2 m로 바꿔 비교해 줘",mode="experiment")
    assert events[-1]["event"]=="result",events[-1]
    answer=events[-1]["result"]
    assert answer["action"]=="compare",answer["message"]
    other=answer["snapshot"]
    assert other["experiment"]["id"]!=start["experiment"]["id"]
    assert other["experiment"]["values"]["length"]==2
    assert other["run"]["facts"]["measured_period"]>start["run"]["facts"]["measured_period"]
    assert "측정 주기" in answer["message"]
    assert {"op":"create_comparison","patch":{"values":{"length":2}}} in answer["lesson"]["actions"]
    assert len(client.get("/api/workbenches/"+start["experiment"]["id"]).json()["members"])==2
    analysis=turn(client,other,"두 실험의 결과 차이를 설명해 줘")[-1]["result"]
    assert analysis["action"]=="explain" and "측정 주기" in analysis["message"]
    assert len(client.get("/api/workbenches/"+start["experiment"]["id"]).json()["members"])==2


def test_rejected_provider_action_never_writes(client,monkeypatch):
    from physis.provider_config import current_context
    start=create(client)
    async def malicious(*args):
        current_context.get().metrics.visual_actions=[{"op":"change_conditions","patch":{"values":{"height":4}}}]
        return "모의 응답"
    monkeypatch.setattr(reasoning,"interpret",malicious)
    events=turn(client,start,"현재 결과를 설명해 줘")
    assert events[-1]["event"]=="result"
    assert "unrequested_state_change_removed" in events[-1]["result"]["pipeline"]["warnings"]
    assert client.get("/api/experiments/"+start["experiment"]["id"]).json()==start
    assert client.get("/api/usage").json()["items"][0]["outcome"]=="ok"


def test_explicit_graph_then_provider_graph_take_priority_over_default(client,monkeypatch):
    from physis.provider_config import current_context
    s = create(client)
    async def choose_graph(*args):
        current_context.get().metrics.visual_actions = [{"op":"highlight_graph","quantity":"vy","start":0,"end":1}]
        return "계산한 표본을 살펴보세요."
    monkeypatch.setattr(reasoning, "interpret", choose_graph)
    actions = turn(client, s, "현재 결과를 설명해 줘")[-1]["result"]["lesson"]["actions"]
    assert [(a["op"],a["quantity"]) for a in actions] == [("highlight_graph","vy")]
    actions = turn(client, s, "높이 그래프 0.2초부터 0.8초까지 강조해 줘")[-1]["result"]["lesson"]["actions"]
    assert [(a["op"],a["quantity"]) for a in actions] == [("highlight_graph","y")]


def test_learning_erase_clears_db_and_usage(client):
    s=create(client)
    turn(client,s,"왜 결과가 같아?")
    assert client.get("/api/usage").json()["items"]
    archive=client.get("/api/learning/export").json()
    assert archive["experiments"][0]["id"]==s["experiment"]["id"]
    assert archive["experiments"][0]["inputs"]["values"]==s["experiment"]["values"]
    assert archive["usage"] and archive["workbenches"]==[]
    client.delete("/api/learning").raise_for_status()
    assert client.get("/api/experiments/"+s["experiment"]["id"]).status_code==404
    assert client.get("/api/usage").json()=={"items":[]}
    assert client.get("/api/learning/export").json()=={"experiments":[], "workbenches":[], "usage":[]}


def test_existing_v01_sqlite_inputs_open_modify_and_compare(tmp_path,monkeypatch):
    path = tmp_path/"legacy.db"
    eid = str(uuid4())
    monkeypatch.setenv("PHYSIS_AI_PROVIDER","mock")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE experiments(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, model TEXT NOT NULL, inputs TEXT NOT NULL, level TEXT NOT NULL)")
        db.execute("INSERT INTO experiments VALUES(?,7,'free_fall',?,'intro')",
                   (eid, json.dumps({"values":{"mass_a":2,"mass_b":9,"height":12,"g":9.81},
                                     "duration":5,"dt":.02,"method":"analytic"})))
    with TestClient(create_app(path)) as client:
        original = client.get("/api/experiments/"+eid).json()
        assert original["revision"]==7 and original["experiment"]["values"]["mass_b"]==9
        changed = turn(client, original, "물체 B의 질량을 12 kg으로 바꿔 줘")[-1]["result"]["snapshot"]
        assert changed["revision"]==8 and changed["experiment"]["id"]==eid
        group = "/api/workbenches/"+eid
        assert client.post(group+"/members",json={"revision":8}).is_success
        assert len(client.get(group).json()["members"])==2
