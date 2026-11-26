from uuid import uuid4

from physis.api import snapshot
from physis.cognitive_routing import route
from physis.grounded import make_context, reading_only, report, retrieved_for
from physis.knowledge import KnowledgeStore
from physis.physics import SPECS
from physis.schema import Patch
from physis.state import build


def test_router_keeps_multiple_intents_and_model_for_calculation_plus_concept():
    result = route("진자 주기가 왜 달라지는지 설명하고 계산해 줘")

    assert result.model == "pendulum"
    assert "concept" in result.intents
    assert "calculation" in result.intents
    assert "clarification" in result.intents
    assert 0 <= result.confidence <= 1


def test_router_uses_registered_law_aliases_for_concept_and_formula_intents():
    result = route("뉴턴 법칙의 공식과 원리를 설명해 줘")

    assert result.model == "newton"
    assert {"formula", "concept"}.issubset(result.intents)
    assert result.confidence >= 0.65


def test_hypothetical_numerical_question_is_a_detached_calculation_not_an_edit():
    from physis.cognitive import local_plan

    current = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    question = "What if the mass were 2 kg? What acceleration would result?"
    selected = route(question, current)
    intent = local_plan(question, current, "school", selected)

    assert "calculation" in selected.intents
    assert "experiment_modify" not in selected.intents
    assert intent.action == "create"
    assert intent.patch.values["mass"] == 2
    assert current.values["mass"] == 3


def test_nonimperative_numeric_condition_creates_a_detached_case_for_the_active_model():
    from physis.cognitive import local_plan

    current = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    question = "질량이 5 kg일 때 가속도는 어떻게 돼?"
    selected = route(question, current)
    intent = local_plan(question, current, "school", selected)

    assert "experiment_modify" not in selected.intents
    assert intent.action == "create"
    assert intent.patch.values["mass"] == 5
    assert intent.patch.values["force"] == 12
    assert current.values["mass"] == 3


def test_explicit_imperative_change_remains_a_current_experiment_edit():
    from physis.cognitive import local_plan

    current = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    question = "질량을 2 kg으로 바꿔 줘."
    selected = route(question, current)
    intent = local_plan(question, current, "school", selected)

    assert "experiment_modify" in selected.intents
    assert intent.action == "modify"
    assert intent.patch.values["mass"] == 2


def test_read_only_current_numeric_question_does_not_request_an_edit():
    from physis.cognitive import local_plan

    current = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    question = "이번 실험의 가속도는 얼마야?"
    selected = route(question, current)
    intent = local_plan(question, current, "school", selected)

    assert "calculation" in selected.intents
    assert "experiment_modify" not in selected.intents
    assert intent.action == "explain"
    assert not intent.patch.values


def test_execute_simulation_variants_are_detected_as_explicit_runs():
    selected = route("Run the free-fall simulation to find the arrival time.")

    assert selected.model == "free_fall"
    assert "experiment_create" in selected.intents


def test_newton_law_meta_question_does_not_ask_for_numeric_conditions():
    from physis.clarification import identify

    meta = identify("What is Newton's second law, and what does net force mean?", None, None, SPECS)
    numeric = identify("How much net force is acting? Calculate it.", None, None, SPECS)

    assert meta is None
    assert numeric is not None
    assert {item.key for item in numeric.missing_conditions} == {"mass", "a"}


def test_router_uses_active_model_only_for_an_explicit_current_experiment_reference():
    current = build(SPECS["newton"], uuid4(), Patch())

    result = route("이번 실험 결과를 설명해 줘", current)

    assert result.model == "newton"
    assert result.primary == "concept"


def test_router_reuses_registered_values_for_a_current_experiment_calculation():
    current = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))

    result = route("이번 실험에서 가속도 값은 얼마야?", current)

    assert "calculation" in result.intents
    assert "clarification" not in result.intents


def test_router_separates_supported_theory_from_an_unsupported_simulation_request():
    theory = route("공기 저항은 물체의 운동을 왜 바꿔?")
    simulation = route("공기 저항을 포함해 자유 낙하를 시뮬레이션해 줘")

    assert "concept" in theory.intents
    assert "unsupported" not in theory.intents
    assert {"experiment_create", "unsupported"}.issubset(simulation.intents)


def test_router_returns_domain_specific_recovery_for_simulations_without_registered_models():
    examples = (
        ("Simulate the electron degeneracy pressure inside a white dwarf.", "천체 내부 물리", "상태방정식"),
        ("Calculate the image formation of a compound optical lens.", "기하광학", "광선 추적"),
        ("Simulate the electromagnetic field around a circuit.", "전자기 현상", "전기장"),
        ("Simulate gravitational lensing around a galaxy.", "중력렌즈", "시공간 곡률"),
    )
    for question, phenomenon, dependency in examples:
        result = route(question)
        assert "unsupported" in result.intents
        assert result.model is None
        assert phenomenon in result.unsupported_reason
        assert dependency in result.unsupported_reason


def test_router_marks_an_unanchored_followup_for_clarification():
    result = route("그 값은 얼마야?")

    assert "clarification" in result.intents
    assert result.model is None


def test_new_object_numeric_question_does_not_inherit_active_experiment_defaults():
    from physis.clarification import identify

    current = build(SPECS["free_fall"], uuid4(), Patch())
    prompt = identify("서로 다른 두 물체를 떨어뜨렸는데, 도착 시간이 몇 초인가요?",
                      current, 1, SPECS)

    assert prompt is not None
    assert [item.key for item in prompt.missing_conditions] == ["height"]


def test_current_experiment_question_reuses_its_existing_conditions():
    from physis.clarification import identify

    current = build(SPECS["free_fall"], uuid4(), Patch(values={"height": 4}))
    prompt = identify("이번 실험에서 바닥에 닿는 시간은 몇 초야?", current, 1, SPECS)

    assert prompt is None


def test_why_retrieval_prefers_a_causal_source_for_the_requested_concept(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.initialize()

    rows = retrieved_for(store, "Why does acceleration increase as the net force increases?")

    assert rows
    assert "directly proportional" in rows[0]["text"]


def test_reading_only_answers_a_grounded_basic_science_question_and_lists_related_features(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.initialize()

    result, _ = reading_only(store, "속도의 단위와 차원을 알려 줘", "explain", "school", "units")

    assert result["answer_state"] == "ANSWERED"
    assert result["evidence"]["sources"]
    assert result["evidence"]["related_features"]
    assert result["message"] == result["evidence"]["core"]


def test_reading_only_preserves_scope_reason_with_a_supported_related_explanation(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.initialize()
    reason = "현재 자유 낙하 모델은 공기 저항을 포함한 시뮬레이션을 지원하지 않습니다."

    result, _ = reading_only(store, "공기 저항을 포함한 낙하 시간을 계산해 줘", "explain", "school",
                             "drag", reason)

    assert reason in result["message"]
    assert result["answer_state"] == "UNSUPPORTED_SIMULATION"
    assert result["evidence"]["related_features"]


def test_reading_only_fails_closed_when_local_index_is_not_initialized():
    store = KnowledgeStore(":memory:")

    result, _ = reading_only(store, "속도의 단위를 설명해 줘", "explain", "school")

    assert result["status"] == "UNSUPPORTED"
    assert result["evidence"]["sources"] == []


def test_unsupported_drag_simulation_is_explicitly_labeled_while_theory_remains_available(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.initialize()

    result, _ = reading_only(store, "공기 저항과 바람까지 포함해서 낙하 시간을 시뮬레이션해 줘.",
                             "explain", "school", "drag")

    assert result["answer_state"] == "UNSUPPORTED_SIMULATION"
    assert result["evidence"]["scope_recovery"]["supported_part"] is True
    assert result["evidence"]["related_features"]


def test_verified_model_mechanism_survives_while_contradictory_provider_prose_is_withheld(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.initialize()
    experiment = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    current = snapshot(experiment, 1, "school")
    question = "알짜힘과 가속도의 관계를 설명해 줘"
    rows = store.search("net force acceleration mass", model="newton", limit=8)
    context = make_context(store, rows, question, current)

    dossier = report(store, rows, context, "알짜힘이 커져도 가속도는 커지지 않습니다.", snapshot=current,
                     level="school", question=question)

    local, = [claim for claim in dossier["claims"] if claim["kind"] == "model_explanation"]
    explanation, = [claim for claim in dossier["claims"]
                    if claim["kind"] == "explanation" and "알짜힘이 커져도" in claim["text"]]
    assert local["provenance"] == "registered_model"
    assert local["scope_model"] == "newton"
    assert explanation["withheld"] is True
    assert "알짜힘이 커져도 가속도는 커지지 않습니다." not in dossier["core"]
    assert local["text"] in dossier["core"]


def test_wave_orientation_question_includes_the_registered_mechanism_and_rejects_wrong_relation(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.initialize()
    experiment = build(SPECS["wave_transverse"], uuid4(), Patch())
    current = snapshot(experiment, 1, "school")
    question = "횡파에서 매질의 진동 방향과 파동의 진행 방향은 어떤 관계야?"
    rows = retrieved_for(store, question, model="wave_transverse")
    context = make_context(store, rows, question, current)

    dossier = report(store, rows, context, "매질 입자는 파동의 진행 방향과 나란히 진동합니다.",
                     snapshot=current, level="school", question=question)

    local, = [claim for claim in dossier["claims"] if claim["kind"] == "model_explanation"]
    assert local["scope_model"] == "wave_transverse"
    assert local["provenance"] == "registered_model"
    assert "위아래로 진동" in dossier["core"]
    assert "나란히 진동합니다" not in dossier["core"]
