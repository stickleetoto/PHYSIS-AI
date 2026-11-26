import pytest

from physis import evidence, reasoning
from physis.api import Snapshot
from test_studio import client, create, turn


def fingerprint(snapshot):
    return evidence.run_id(Snapshot.model_validate(snapshot))


def result_of(events):
    assert events[-1]["event"]=="result",events[-1]
    return events[-1]["result"]


def comparison_claims(answer):
    return [claim for claim in answer["evidence"]["claims"] if claim["kind"]=="comparison"]


def assert_period_comparison(answer, start, peer):
    claims = comparison_claims(answer)
    assert len(claims)==1
    claim = claims[0]
    assert claim["status"]=="calculation_verified"
    assert claim["references"]==[fingerprint(start),fingerprint(peer)]
    for ref, snapshot in zip(claim["runs"],[start,peer],strict=True):
        assert ref["experiment_id"]==snapshot["experiment"]["id"] and ref["revision"]==snapshot["revision"]
        assert ref["run_id"]==fingerprint(snapshot)
    left,right = (snap["run"]["facts"]["measured_period"] for snap in [start,peer])
    assert claim["measurement"]=={"key":"measured_period","unit":"s","baseline":left,"compared":right,"difference":right-left}
    assert left!=right
    assert "기준 실험" in claim["text"] and "측정 주기" in claim["text"] and f"{left:.5g} s" in claim["text"]
    assert f"비교 실험은 {right:.5g} s" in claim["text"]
    assert claim["text"] in answer["message"]==answer["lesson"]["text"]==answer["evidence"]["core"]


def test_created_and_saved_comparison_references_two_real_runs(client,monkeypatch):
    start = create(client,"pendulum")
    async def wrong_number(*args):
        return "측정 주기는 999 s입니다."
    monkeypatch.setattr(reasoning,"interpret",wrong_number)
    answer = result_of(turn(client,start,"줄 길이를 2 m로 바꿔 비교해 줘",mode="experiment"))
    peer = answer["snapshot"]
    assert_period_comparison(answer,start,peer)
    assert "999 s" not in answer["message"] and "999 s" not in peer["explanation"]
    failed = [check for check in answer["evidence"]["checks"] if check["status"]=="failed"]
    assert len(failed)==1 and failed[0]["value"]==999 and failed[0]["run_id"]==fingerprint(peer)
    for active in [start,peer]:
        analysis = result_of(turn(client,active,"두 실험의 결과 차이를 설명해 줘"))
        assert_period_comparison(analysis,start,peer)
        assert "999 s" not in analysis["snapshot"]["explanation"]


@pytest.mark.parametrize("mode",["discovery","review"])
def test_assessment_comparison_keeps_predicted_answers_hidden(client,mode):
    start = create(client,"pendulum")
    answer = result_of(turn(client,start,"줄 길이를 2 m로 바꿔 비교해 줘",mode=mode))
    assert answer["action"]=="compare"
    assert not comparison_claims(answer) and not answer["evidence"]["calculations"]
    assert "기준 실험의 측정 주기" not in answer["message"]
    assert answer["snapshot"]["explanation"]==""
