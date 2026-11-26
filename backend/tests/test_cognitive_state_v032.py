import json
from uuid import uuid4

from fastapi.testclient import TestClient
import pytest

from physis import cognitive
from physis.api import create_app
from physis.cognitive_routing import route
from physis.physics import SPECS
from physis.schema import Patch
from physis.state import build


def test_simple_wording_is_local_to_the_explanation():
    exp = build(SPECS["newton"],uuid4(),Patch())
    assert cognitive.local_plan("뉴턴의 법칙을 쉽게 설명해줘",exp,"research",route("뉴턴의 법칙을 쉽게 설명해줘",exp)).level=="research"


@pytest.mark.parametrize("question,expected", [
    ("질량 2 kg인 수레에 알짜힘 14 N이 작용합니다. 가속도를 계산해 줘.", "7 m/s²"),
    ("질량 3 kg인 카트에 오른쪽으로 15 N의 알짜힘이 작용해. 가속도 크기와 방향을 알려 줘.", "5 m/s²"),
])
def test_numeric_hypothesis_preserves_source_and_has_a_resolvable_run(tmp_path,monkeypatch,question,expected):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER","mock")
    with TestClient(create_app(tmp_path/"run.sqlite3")) as app:
        first = app.post("/api/experiments",json={"model":"newton"}).json()
        res=app.post("/api/tutor/stream",json={"experiment_id":first["experiment"]["id"],"revision":1,"message":question})
        end=json.loads(res.text.splitlines()[-1])["result"]
        assert end["experiment_action"]["op"]=="create"
        assert end["application_state"]["experiment_id"]==end["snapshot"]["experiment"]["id"]
        assert end["application_state"]["experiment_id"]!=first["experiment"]["id"]
        assert app.get("/api/experiments/"+end["application_state"]["experiment_id"]).status_code==200
        assert app.get("/api/experiments/"+first["experiment"]["id"]).json()==first
        assert expected in end["message"]


def test_concept_packet_has_no_sample_values_and_keeps_compound_intents():
    exp=build(SPECS["newton"],uuid4(),Patch())
    q="뉴턴 법칙의 공식과 원리를 설명해 줘"
    selected=route(q,exp)
    packet=cognitive.compact_context(q,"school",selected,exp,{"calculations":[{"status":"unused"}]})
    assert {"formula","concept"}.issubset(selected.intents)
    assert "inputs" not in packet and "calculations" not in packet

def test_one_variable_math_uses_existing_sandboxed_tool():
    answer=cognitive.math_turn("x^2를 x에 대해 미분해 줘","school")
    assert answer["answer_state"]=="ANSWERED" and "2*x" in answer["message"]
    assert answer["snapshot"] is None and answer["evidence"]["math_result"]["status"]=="computed"


def test_simulator_specific_requests_return_the_missing_physics_dependency():
    selected = route("시뮬레이터에서 망원경 렌즈를 지나는 광선을 추적해 줘", None)
    assert "unsupported" in selected.intents and "굴절률" in selected.unsupported_reason


def test_gas_lesson_separates_the_molecular_explanation_from_the_pressure_readout():
    from physis.api import snapshot
    from physis.model_lesson import explain_model

    exp = build(SPECS["ideal_gas"], uuid4(), Patch())
    lesson = explain_model("용기를 데우면 압력이 왜 높아지나요?", snapshot(exp, 1, "school"), "school")
    assert "운동량" in lesson["text"] and "켈빈" in lesson["text"]
    assert "개별 충돌을 측정하지 않습니다" in lesson["text"]
