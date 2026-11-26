import sqlite3
from uuid import uuid4

from fastapi.testclient import TestClient

from physis.api import create_app
from physis.physics import SPECS
from physis.schema import Patch
from physis.state import Experiments, build


def test_bounded_history_survives_existing_database_and_reopen(tmp_path):
    path = tmp_path / "old.db"
    eid = uuid4()
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE experiments(id TEXT PRIMARY KEY, revision INTEGER, model TEXT, inputs TEXT, level TEXT)")
        db.execute("INSERT INTO experiments VALUES(?,1,'free_fall',?,'school')",
                   (str(eid), Patch(values={"height": 20}).model_dump_json()))
    store = Experiments(path)
    store.initialize()
    assert store.history(eid) == {"revision": 1, "undo": 0, "redo": 0}
    for i in range(56):
        store.save(build(SPECS["free_fall"], eid, Patch(values={"height": 5+i})), "school", i+1)
    reopened = Experiments(path)
    assert reopened.history(eid) == {"revision": 57, "undo": 50, "redo": 0}
    for i in range(50):
        step, target = reopened.history_target(eid, "undo")
        assert target.values["height"] == 59-i
        reopened.move_history(eid, 57+i, "undo", step, "school")
    assert reopened.history(eid) == {"revision": 107, "undo": 0, "redo": 50}


def test_manual_and_mock_changes_share_revision_guarded_history(tmp_path, monkeypatch):
    monkeypatch.setenv("PHYSIS_OFFLINE","1")
    path = tmp_path / "lab.db"
    with TestClient(create_app(path)) as client:
        s = client.post("/api/experiments", json={"model":"free_fall"}).json()
        eid = s["experiment"]["id"]
        uri = "/api/experiments/" + eid
        def move(direction, revision):
            return client.post(uri+"/history/"+direction,json={"revision":revision})
        edited = client.patch(uri,json={"revision":1,"patch":{"values":{"height":9}}})
        assert edited.status_code == 200
        answer = client.post("/api/chat",json={"experiment_id":eid,"revision":2,"message":"물체 B의 질량을 10 kg으로 바꿔 줘"})
        assert answer.json()["action"] == "modify"
        original = s["experiment"]["values"]
        assert move("undo",2).status_code == 409
        restored = move("undo",3).json()
        assert restored["experiment"]["values"] == {**original,"height":9}
        assert move("undo",4).json()["experiment"]["values"] == original
        assert move("redo",5).json()["experiment"]["values"]["height"] == 9
        # An unchanged submission keeps redo available.
        assert client.patch(uri,json={"revision":6,"patch":{"values":{"height":9}}}).is_success
        assert client.get(uri+"/history").json()["redo"] == 1
        assert client.patch(uri,json={"revision":7,"patch":{"values":{"height":12}}}).is_success
        assert move("redo",8).status_code == 409
        other = client.post("/api/experiments",json={"model":"free_fall"}).json()["experiment"]["id"]
        assert client.get("/api/experiments/"+other+"/history").json()["undo"] == 0
        assert client.get(uri+"/history").json()["undo"] == 2
        client.delete("/api/learning").raise_for_status()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM input_history").fetchone()[0] == 0
