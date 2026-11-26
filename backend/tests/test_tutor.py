from uuid import uuid4

import pytest

from physis.physics import SPECS, simulate
from physis.schema import Patch
from physis.state import build
from physis.tutor import comparison_message, is_comparison_request, review_question, teach, validate_actions, visualization_request


@pytest.fixture(scope="module")
def fall():
    exp = build(SPECS["free_fall"], uuid4(), Patch())
    return exp, simulate(exp)


@pytest.mark.parametrize("action", [
    {"op":"highlight_object","index":1}, {"op":"highlight_quantity","quantity":"y"},
    {"op":"show_force","index":0},{"op":"show_velocity","index":1},{"op":"show_acceleration","index":1},
    {"op":"highlight_graph","quantity":"vy","start":0,"end":0.8},{"op":"pause"},{"op":"seek","time":0.4},
    {"op":"change_conditions","patch":{"values":{"mass_b":2}}},{"op":"create_comparison","patch":{"values":{"height":2}}},
    {"op":"highlight_variable","variable":"g"},
])
def test_closed_protocol(fall, action):
    assert validate_actions([action], *fall)[0]["op"] == action["op"]


@pytest.mark.parametrize("action", [
    {"op":"script","code":"arbitrary"}, {"op":"pause","html":"extra"}, {"op":"seek","time":float("nan")},
    {"op":"seek","time":True},{"op":"seek","time":3.9},{"op":"seek","time":-1},
    {"op":"highlight_graph","quantity":"y","start":1,"end":0.5},{"op":"show_velocity","index":2},
    {"op":"highlight_variable","variable":"y"},{"op":"highlight_quantity","quantity":"unmeasured"},
    {"op":"change_conditions","patch":{"values":{"g":-2}}},{"op":"change_conditions","patch":{"values":{"alien":0}}},
    {"op":"change_conditions","patch":{"status":"VERIFIED"}},{"op":"change_conditions","patch":{}},
    {"op":"create_comparison","patch":{"dt":0.002,"duration":30}},
])
def test_unavailable_or_invalid_operation_is_rejected(fall, action):
    with pytest.raises(ValueError):
        validate_actions([action], *fall)


def test_protocol_batches_are_validated_before_any_mutation(fall):
    exp,run=fall
    before = exp.model_dump()
    pair = [{"op":"create_comparison","patch":{}},{"op":"change_conditions","patch":{"values":{"mass_b":4}}}]
    with pytest.raises(ValueError):
        validate_actions(pair,exp,run)
    assert exp.model_dump() == before


def test_describing_a_number_on_a_graph_does_not_request_a_display_change(fall):
    assert visualization_request("높이 그래프에 3이라고 표시된 숫자의 단위가 뭐야?", *fall) is None


@pytest.mark.parametrize("prompt,action", [
    ("물체 B를 강조해 줘",{"op":"highlight_object","index":1}),
    ("물체 B의 가속도 벡터를 보여 줘",{"op":"show_acceleration","index":1}),
    ("0.6초로 이동해 줘",{"op":"seek","time":0.6}),
    ("높이 그래프 0.1초부터 1초까지 강조해 줘",{"op":"highlight_graph","quantity":"y","start":0.1,"end":1.0}),
    ("공식에서 g 변수를 강조해 줘",{"op":"highlight_variable","variable":"g"}),
    ("공식에서 높이를 강조해 줘",{"op":"highlight_variable","variable":"height"}),
    ("가속도를 강조해 줘",{"op":"highlight_quantity","quantity":"ay"}),
])
def test_visual_instruction_from_korean_question(fall,prompt,action):
    assert visualization_request(prompt,*fall) == [action]


def test_mismatched_model_or_scope_is_left_to_planner(fall):
    assert visualization_request("공기 저항을 넣고 힘 벡터를 보여 줘", *fall) is None
    assert visualization_request("진자의 공식에서 길이를 강조해 줘", *fall) is None
    assert visualization_request("높이를 10 m로 변경하고 벡터를 표시해 줘", *fall) is None


def test_no_vector_fabricated_for_static_sensor():
    exp=build(SPECS["hydrostatic"],uuid4(),Patch())
    with pytest.raises(ValueError):
        validate_actions([{"op":"show_velocity","index":0}],exp,simulate(exp))


def test_discovery_and_review_delay_revelation(fall):
    exp,run=fall
    measured="이번 실행에서 기록한 값은 두 물체의 바닥 도착 시간 2.019 s입니다."
    discovery=teach("가설을 세워볼래","discovery",exp,run,"school",measured)
    assert measured not in discovery["text"] and discovery["actions"]==[{"op":"pause"}]
    quiz=teach("복습 문제를 내줘","review",exp,run,"school",measured)
    assert quiz["review"]["options"][quiz["review"]["correct"]]=="두 공이 동시에"
    assert quiz["review"]["feedback"] not in quiz["text"] and measured not in quiz["text"]


def test_experiment_and_explain_grounded(fall):
    for mode in ["explain","experiment"]:
        lesson=teach("결과를 설명해 줘",mode,*fall,"school","검증된 현재 실행의 관측")
        assert "검증된 현재 실행의 관측" in lesson["text"]
        assert lesson["prompt"] and lesson["actions"]


def test_all_enabled_models_have_a_review_item():
    for spec in SPECS.values():
        quiz=review_question(spec)
        assert len(set(quiz["options"]))==len(quiz["options"])>=2
        assert quiz["options"][quiz["correct"]] and quiz["feedback"]


def test_comparison_conditions_survive_language_normalization():
    message="길이를 2 m로 바꿔 비교해줘"
    assert is_comparison_request(message)
    assert comparison_message(message)=="길이를 2 m로 바꿔"
    assert not is_comparison_request("두 물체의 낙하 시간을 비교해 줘")
    assert not is_comparison_request("비교 실험 결과를 설명해 줘")
    assert is_comparison_request("이 실험을 복제해 줘")
    assert comparison_message("이 실험을 복제해 줘")==""


def test_interpretation_request_is_read_only_while_analytic_method_is_selectable():
    from physis.reasoning import _method
    assert _method("측정 결과를 해석해 줘") is None
    assert _method("그래프를 해석해") is None
    assert _method("해석해로 변경해 줘") == "analytic"
