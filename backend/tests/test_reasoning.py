import asyncio
import math
from uuid import uuid4

import pytest

from physis.physics import SPECS, simulate
from physis.reasoning import explain, plan
from physis.schema import Check, Patch
from physis.state import build


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("PHYSIS_AI_PROVIDER", "mock")


def exp(model="free_fall", **patch):
    return build(SPECS[model], uuid4(), Patch(**patch))


def ask(text, current=None, level="school"):
    return asyncio.run(plan(text, current, level, SPECS))


def test_guided_free_fall_conversation():
    message = "무거운 물체가 가벼운 물체보다 빨리 떨어지는 거 아니야?"
    initial = ask(message)
    assert (initial.action, initial.model) == ("create", "free_fall")
    current = exp()
    assert ask(message, current).action == "explain"
    edit = ask("그러면 두 물체의 질량 차이를 더 크게 해봐.", current)
    assert edit.action == "modify" and set(edit.patch.values) == {"mass_b"}
    assert edit.patch.values["mass_b"] > current.values["mass_b"]
    changed = build(SPECS[initial.model], current.id, edit.patch, current)
    answer = ask("왜 결과가 같아?", changed)
    assert answer.action == "explain" and not answer.patch.values
    rendered = explain(changed, simulate(changed), answer.level)
    assert f"B {changed.values['mass_b']:g} kg" in rendered and "바닥 도착 시간" in rendered
    assert ask("새 실험으로 자유낙하를 해줘", changed).action == "create"


@pytest.mark.parametrize("text,model", [
    ("등속 운동 실험", "uniform"), ("등가속도 운동을 관찰해줘", "acceleration"),
    ("뉴턴의 제2법칙", "newton"), ("미끄럼 마찰", "friction"), ("두 수레의 충돌", "collision"),
    ("용수철 주기", "spring"), ("진자의 주기", "pendulum"), ("감쇠하는 용수철", "damped"),
    ("등속 원운동", "circular"), ("수심과 압력", "hydrostatic"), ("잠긴 물체의 부력", "buoyancy"),
    ("관의 단면과 유속의 관계", "continuity"),
])
def test_model_selection(text, model):
    assert (ask(text).action, ask(text).model) == ("create", model)


@pytest.mark.parametrize("model,text,key,expected", [
    ("free_fall", "높이를 250cm로 바꿔", "height", 2.5),
    ("free_fall", "물체 B의 질량을 750그램으로", "mass_b", .75),
    ("pendulum", "처음 각도를 30도로 변경", "angle", math.pi / 6),
    ("uniform", "초기 속도를 -10.8 km/h로 변경", "v0", -3),
    ("uniform", "질량을 2kg 늘려", "mass", 3),
    ("uniform", "질량을 2kg으로 늘려", "mass", 2),
    ("uniform", "질량을 2배로 바꿔", "mass", 2),
    ("uniform", "질량을 50% 줄여", "mass", .5),
    ("hydrostatic", "수면 압력을 101.3kPa로 변경", "p0", 101300),
    ("continuity", "입구 단면적을 100cm²로 바꿔", "area_in", .01),
])
def test_partial_si_edits(model, text, key, expected):
    result = ask(text, exp(model))
    assert result.action == "modify"
    assert result.patch.values == {key: pytest.approx(expected)}
    assert result.patch.method is result.patch.dt is result.patch.duration is None


def test_multiple_fields_and_grid_are_explicit():
    current = exp()
    p = ask("질량 A는 2kg, 질량 B는 8kg, 시간 간격은 10ms로 변경", current).patch
    assert p.values == {"mass_a": 2, "mass_b": 8} and p.dt == .01
    assert p.duration is p.method is None
    assert ask("용수철의 질량을 2kg, 용수철 상수를 32N/m로 바꿔", current).action == "create"
    assert ask("두 물체 1kg과 10kg의 자유낙하").patch.values == {"mass_a": 1, "mass_b": 10}


def test_explanatory_request_can_change_a_stated_condition():
    current = exp()
    result = ask("높이를 5m로 했을 때 결과를 설명해 줘", current)
    assert result.action == "modify" and result.patch.values == {"height": 5}
    compound = ask("높이를 두 배, 물체 A의 질량을 3kg으로 변경", current)
    assert compound.patch.values == {"height": current.values['height']*2, "mass_a": 3}
    assert ask("두 물체의 질량 차이를 2배로", current).patch.values == {"mass_b": 9}


@pytest.mark.parametrize("text,action,coefficient", [
    ("완전비탄성 충돌로 바꿔", "modify", 0), ("충돌한 후 두 수레가 붙어서 움직이면?", "modify", 0),
    ("완전 탄성 충돌로 변경", "modify", 1), ("비탄성 충돌", "unsupported", None),
    ("비탄성 충돌에서 반발 계수를 0.4로 설정", "modify", .4),
    ("완전비탄성 충돌에서 반발 계수를 0.5로", "unsupported", None),
])
def test_collision_qualifiers(text, action, coefficient):
    result = ask(text, exp("collision"))
    assert result.action == action
    assert result.patch.values.get("restitution") == coefficient


@pytest.mark.parametrize("text,model", [("마찰 없는 용수철 진동", "spring"), ("마찰 없는 등속 운동", "uniform"),
                                        ("감쇠가 없는 용수철", "spring"), ("공기 저항을 무시한 자유낙하", "free_fall")])
def test_negation_selects_the_intended_model(text, model):
    assert ask(text).model == model


@pytest.mark.parametrize("text", ["이차원 충돌", "강제 진동하는 용수철", "수면에서 떠오르는 물체의 부력",
                                "자유낙하에서 위로 던짐", "달에서의 자유낙하", "충돌과 마찰을 함께 계산"])
def test_incompatible_idealizations_are_declined(text):
    assert ask(text).action == "unsupported"


@pytest.mark.parametrize("text", ["높이를 4kg로 바꿔", "높이를 7km/h로", "높이를 2m/s로", "높이를 2000m로",
                                "높이를 1,000m로", "높이를 3.2.1미터로", "높이를 1e90광년으로", "질량을 4kg으로",
                                "양자 터널링 실험", "야구공에 공기 저항을 추가해줘", "날씨 결과가 어때?",
                                "왜 강아지는 귀여워?", "자유낙하에 관한 시를 써 줘", "탄도 계산을 위한 자유낙하", "포물선 운동"])
def test_unsupported_and_ambiguous_inputs_do_not_mutate_current(text):
    current = exp()
    outcome = ask(text, current)
    assert outcome.action == "unsupported" and outcome.model is None
    assert outcome.message and not outcome.patch.values


def test_explanations_use_observed_numbers_and_honor_missing_arrival():
    current = exp(duration=.1)
    run = simulate(current)
    assert "arrival_time" not in run.facts
    texts = [explain(current, run, level) for level in ("intro", "school", "university", "research")]
    assert len(set(texts)) == len(texts)
    for text in texts:
        assert current.formula in text and "도착 시각은 측정되지" in text
        assert f"{run.series['0.y'][-1]:.4g} m" in text
    assert "적분" in texts[2] and "Δt" in texts[3]
    assert ask("연구자 수준으로 설명해 줘", current).level == "research"
    assert ask("초등학생 수준으로 바꿔", current).action == "explain"


def test_failed_check_is_reported_without_asserting_a_successful_comparison():
    current = exp()
    run = simulate(current).model_copy(update={"status": "FAILED", "checks": [Check(label="위치", passed=False, detail="큰 편차")]})
    text = explain(current, run, "research")
    assert "큰 편차" in text and "위치" in text and "이 결과로는" in text
    assert "두 물체의 바닥 도착 시간" not in text
