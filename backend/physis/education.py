"""Level-specific teaching text backed by reviewed source rows and explicit conditions."""
from .reviewed_claims import EDUCATION_CARDS, REVIEWED


LEVELS = ("intro", "school", "university", "research")
_NO_CARD = "이 개념을 다룬 검토된 교육 자료를 현재 근거에서 확인하지 못했습니다."

_FOLLOW_UP = {
    "free_fall_mass_independence": {
        "intro": "공기 저항을 무시할 수 없다면 같은 설명을 그대로 쓸 수 있을까요?",
        "school": "공기 저항이 작용하는 경우에도 이 결론을 그대로 적용할 수 있을까요?",
        "university": "항력이 무시되지 않는 조건에서 질량 독립 가속도를 말하려면 어떤 추가 근거가 필요할까요?",
        "research": "이 문장의 두 조건 중 하나를 바꾸면 어떤 자료가 더 필요할까요?",
    },
    "newton_second_law": {
        "intro": "같은 힘으로 더 무거운 물체를 밀면 가속도는 어떻게 될까요?",
        "school": "알짜 외력을 고정하고 질량만 늘리면 가속도는 어떻게 변할까요?",
        "university": "알짜 외력 벡터를 고정한 채 계의 질량을 바꾸면 가속도 크기와 방향은 어떻게 될까요?",
        "research": "힘의 계와 계의 경계를 바꾸면 이 관계를 적용하기 위해 어떤 양을 다시 정의해야 할까요?",
    },
    "pendulum_small_angle": {
        "intro": "흔드는 각도가 커지면 작은 각도 설명을 그대로 써도 될까요?",
        "school": "약 15°보다 큰 각도에서도 같은 근사를 쓸 수 있는지 확인해 보세요.",
        "university": "각도 조건을 벗어날 때 선형 복원력 근사가 유효한지 어떻게 검토할까요?",
        "research": "약 15° 조건을 넘어선 범위에서 근사 오차를 정량화하려면 무엇을 비교해야 할까요?",
    },
}
_MODEL_CARD = {
    "free_fall": "free_fall_mass_independence",
    "newton": "newton_second_law",
    "pendulum": "pendulum_small_angle",
}


def _empty_level(level):
    return {"core": _NO_CARD, "conditions": [], "misconception": None,
            "follow_up": None, "source_ids": []}


def education_for(level, sources, *, claims=(), question="", model=None):
    """Build four level variants only when the corresponding reviewed evidence is present."""
    if level not in LEVELS:
        level = "school"
    verified = {}
    for source in sources:
        if source.get("status") != "source_verified" or not source.get("id"):
            continue
        reviewed = REVIEWED.get(source["id"])
        if reviewed and reviewed[0] in source.get("quote", ""):
            verified[source["id"]] = source

    if model in _MODEL_CARD:
        candidate = _MODEL_CARD[model]
        selected = candidate if any(source_id in verified for source_id in EDUCATION_CARDS[candidate]["source_ids"]) else None
    elif model:
        selected = None
    else:
        selected = next((key for key, card in EDUCATION_CARDS.items()
                         if any(source_id in verified for source_id in card["source_ids"])), None)
    if selected is None:
        reviewed_source = next((source_id for source_id in verified if source_id in REVIEWED), None) if not model else None
        if not reviewed_source:
            return {"status": "insufficient", "selected_level": level,
                    "levels": {name: _empty_level(name) for name in LEVELS}}
        paraphrase = REVIEWED[reviewed_source][1]
        source_quote = verified[reviewed_source]["quote"]
        levels = {
            "intro": {"core": paraphrase, "conditions": [], "misconception": None,
                      "follow_up": None, "source_ids": [reviewed_source]},
            "school": {"core": paraphrase + " 인용문과 함께 조건을 확인하세요.", "conditions": [],
                       "misconception": None, "follow_up": None, "source_ids": [reviewed_source]},
            "university": {"core": paraphrase + " 원문: " + source_quote, "conditions": [],
                           "misconception": None, "follow_up": None, "source_ids": [reviewed_source]},
            "research": {"core": paraphrase + " 이 문장만으로는 원문에 없는 조건까지 일반화하지 않습니다.",
                         "conditions": [], "misconception": None, "follow_up": None,
                         "source_ids": [reviewed_source]},
        }
        return {"status": "available", "selected_level": level, "levels": levels}

    card = EDUCATION_CARDS[selected]
    ids = [source_id for source_id in card["source_ids"] if source_id in verified]
    misconception = card["misconception"]
    # Show a misconception correction only if a claim was judged contrary to this source.
    contradiction = any(c.get("status") == "contradiction" and set(c.get("references", ())) & set(ids)
                        for c in claims)
    if question:
        from .alignment import align_claim
        question_result = align_claim(question.rstrip(" ?.!"), list(verified.values()))
        contradiction = contradiction or question_result["state"] in {"contradiction", "undecidable"}
    return {
        "status": "available",
        "selected_level": level,
        "levels": {
            name: {
                "core": card["levels"][name],
                "conditions": list(card["conditions"]),
                "misconception": misconception if contradiction else None,
                "follow_up": _FOLLOW_UP[selected][name],
                "source_ids": ids,
            }
            for name in LEVELS
        },
    }
