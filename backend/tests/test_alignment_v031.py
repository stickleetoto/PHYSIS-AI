from physis.alignment import align_claim, split_claims
from physis.education import education_for
from physis.grounded import make_context, report
from physis.knowledge import KnowledgeStore
from physis.reviewed_claims import EDUCATION_CARDS, REVIEWED


FREE_FALL_ID = "college-m42102:import-auto-id2006874"
FREE_FALL_SOURCE = {
    "id": FREE_FALL_ID,
    "status": "source_verified",
    "quote": (
        "If air resistance and friction are negligible, then in a given location "
        "all objects fall toward the center of Earth with the same constant acceleration, "
        "independent of their mass."
    ),
}
NEWTON_SOURCE = {
    "id": "college-m42073:import-auto-id1355832",
    "status": "source_verified",
    "quote": "The acceleration of a system is directly proportional to and in the same direction as the net external force acting on the system, and inversely proportional to its mass.",
}


def test_claims_are_split_into_independent_sentences():
    assert split_claims("The masses do not change acceleration. Drag is outside this model.") == [
        "The masses do not change acceleration.",
        "Drag is outside this model.",
    ]


def test_exact_evidence_is_direct():
    result = align_claim(FREE_FALL_SOURCE["quote"], [FREE_FALL_SOURCE])
    assert result["state"] == "direct"
    assert result["references"] == [FREE_FALL_ID]


def test_exact_match_preserves_numeric_signs_and_inequalities():
    passage = {"id":"synthetic-math", "status":"source_verified", "quote":"The acceleration is −4 m/s²."}
    assert align_claim("The acceleration is -4 m/s²", [passage])["state"] == "direct"
    assert align_claim("The acceleration is +4 m/s²", [passage])["state"] != "direct"


def test_unsigned_passage_is_not_a_verified_source():
    unsigned = {key: value for key, value in FREE_FALL_SOURCE.items() if key != "status"}
    assert align_claim(unsigned["quote"], [unsigned])["state"] == "insufficient"


def test_opposed_verified_rows_are_undecidable():
    opposite = FREE_FALL_SOURCE | {
        "id": "synthetic-opposed-control",
        "quote": "When air resistance is negligible, the heavier object has greater acceleration than the lighter object as they fall.",
    }
    # Use the same reviewed fact identity for the synthetic opposing control so the
    # relation judge must reconcile the two independently labeled statements.
    opposite["id"] = FREE_FALL_ID
    result = align_claim(FREE_FALL_SOURCE["quote"], [FREE_FALL_SOURCE, opposite])
    assert result["state"] == "undecidable"
    assert set(result["references"]) == {FREE_FALL_ID}


def test_negated_newton_relation_is_never_certified_as_positive():
    english = align_claim("More net force does not produce greater acceleration.", [NEWTON_SOURCE])
    korean = align_claim("알짜힘이 더 커져도 가속도가 커지지 않는다.", [NEWTON_SOURCE])
    assert english["state"] == "contradiction"
    assert korean["state"] == "contradiction"


def test_unseen_free_fall_paraphrase_is_partial_only_under_the_source_condition():
    result = align_claim(
        "With drag negligible, a ten-kilogram object does not accelerate faster than a one-kilogram object as they fall.",
        [FREE_FALL_SOURCE],
    )
    assert result["state"] == "partial"
    assert result["references"] == [FREE_FALL_ID]


def test_opposite_free_fall_relation_is_a_contradiction():
    result = align_claim(
        "When air resistance is negligible, the heavier falling object accelerates faster.",
        [FREE_FALL_SOURCE],
    )
    assert result["state"] == "contradiction"


def test_related_vocabulary_does_not_count_as_support():
    result = align_claim("The mass changes the color of a falling object.", [FREE_FALL_SOURCE])
    assert result["state"] == "related"
    assert result["reason"]


def test_missing_or_mismatched_evidence_abstains():
    assert align_claim("A new claim.", [])["state"] == "insufficient"
    result = align_claim("With drag present, different masses have identical acceleration as they fall.", [FREE_FALL_SOURCE])
    assert result["state"] == "undecidable"


def test_education_cards_are_conditioned_on_a_vetted_source_and_cover_four_levels():
    supported = {"id": FREE_FALL_ID, "quote": FREE_FALL_SOURCE["quote"], "status": "source_verified"}
    result = education_for("school", [supported])
    assert set(result["levels"]) == {"intro", "school", "university", "research"}
    assert result["levels"]["school"]["core"]
    assert result["levels"]["school"]["conditions"]
    assert result["levels"]["research"]["core"] != result["levels"]["intro"]["core"]
    assert education_for("school", [])["status"] == "insufficient"


def test_report_aligns_each_claim_and_withholds_only_unsupported_sentences(tmp_path):
    store = KnowledgeStore(tmp_path / "knowledge.db")
    store.initialize()
    rows = store.search("falling objects same constant acceleration independent mass", model="free_fall", limit=8)
    source = next(row for row in rows if row["id"] == FREE_FALL_ID)
    rows = [source]
    context = make_context(store, rows, "free-fall acceleration and mass")
    supported = source["text"].split(". ")[0] + "."
    unsupported = "The mass changes the color of a falling object."
    dossier = report(store, rows, context, supported + " " + unsupported, level="school")
    explanations = [claim for claim in dossier["claims"] if claim["kind"] == "explanation"]
    assert [claim["status"] for claim in explanations] == ["direct", "related"]
    assert explanations[1]["withheld"] is True
    assert unsupported not in dossier["core"]
    assert dossier["education"]["status"] == "available"
    assert dossier["education"]["selected_level"] == "school"
    assert dossier["abstention"]["status"] == "partial"


def test_unsupported_reading_only_surfaces_full_abstention_and_adjudicated_text():
    from physis.grounded import reading_only
    response, _ = reading_only(KnowledgeStore(":memory:"), "an unindexed topic", "explain", "school")
    assert response["message"] == response["lesson"]["text"] == response["evidence"]["core"]
    assert response["evidence"]["abstention"]["status"] == "full"


def test_report_keeps_verified_numeric_observations_without_literature():
    from uuid import uuid4
    from physis import evidence
    from physis.api import snapshot
    from physis.physics import SPECS
    from physis.schema import Patch
    from physis.state import build

    experiment = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    result = snapshot(experiment, 1, "school")
    values = evidence.readings(result, question="가속도")
    context = {"passages": [], "formula": None, "calculations": values}
    dossier = report(KnowledgeStore(":memory:"), [], context, "가속도 4 m/s²입니다.",
                     snapshot=result, level="school", question="가속도")
    assert "가속도 4 m/s²" in dossier["core"]
    assert any(claim["kind"] == "simulation_observation" and claim["status"] == "calculation_verified"
               for claim in dossier["claims"])


def test_report_preserves_only_the_exact_question_bound_registry_unit_note(monkeypatch):
    from uuid import uuid4
    from physis.api import snapshot
    from physis.physics import SPECS
    from physis.schema import Patch
    from physis.state import build
    from physis import classroom_units

    experiment = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    result = snapshot(experiment, 1, "school")
    question = "가속도 단위 질문"
    note = "가속도의 단위는 m/s²이며 차원은 LT⁻²입니다."
    monkeypatch.setattr(classroom_units, "unit_note", lambda q, model: note if q == question and model == "newton" else "")
    context = {"passages": [], "formula": None, "calculations": []}
    dossier = report(KnowledgeStore(":memory:"), [], context, note, snapshot=result,
                     level="school", question=question)
    assert dossier["core"] == note
    registry_claim, = [claim for claim in dossier["claims"] if claim["kind"] == "registry_unit"]
    assert registry_claim["status"] == "registry_verified"
    assert registry_claim["references"] == ["classroom_units.dimension_table"]


def test_report_rebuilds_graph_observation_from_current_run_samples():
    from uuid import uuid4
    from physis import evidence
    from physis.api import snapshot
    from physis.physics import SPECS
    from physis.schema import Patch
    from physis.state import build

    experiment = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    result = snapshot(experiment, 1, "school")
    key = next(iter(result.run.series))
    quantity = key.partition(".")[2]
    unit = experiment.measurements[quantity]
    indices = (0, len(result.run.times) - 1)
    item = {"status":"calculation_verified", "run_id":evidence.run_id(result),
            "experiment_id":str(experiment.id), "revision":result.revision, "reference":key,
            "label":"untrusted label", "unit":unit, "text":"This proves 999 m.",
            "samples":[{"index":i,"time":result.run.times[i],"value":result.run.series[key][i]} for i in indices]}
    context = {"passages":[], "formula":None, "calculations":[], "observations":[item]}
    dossier = report(KnowledgeStore(":memory:"), [], context, "Unverified prose.",
                     snapshot=result, level="school", question="graph values")
    observation, = [claim for claim in dossier["claims"] if claim["kind"] == "simulation_observation"
                    and "samples" in claim]
    assert "999" not in observation["text"]
    assert "untrusted label" not in observation["text"]
    assert "999" not in dossier["core"]
    assert observation["references"] == [evidence.run_id(result)]


def test_report_rejects_stale_graph_sample():
    from uuid import uuid4
    from physis import evidence
    from physis.api import snapshot
    from physis.physics import SPECS
    from physis.schema import Patch
    from physis.state import build

    experiment = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    result = snapshot(experiment, 1, "school")
    key = next(iter(result.run.series))
    quantity = key.partition(".")[2]
    item = {"status":"calculation_verified", "run_id":evidence.run_id(result),
            "experiment_id":str(experiment.id), "revision":result.revision, "reference":key,
            "unit":experiment.measurements[quantity], "text":"999", "samples":[
                {"index":0,"time":result.run.times[0],"value":999}]}
    context = {"passages":[], "formula":None, "calculations":[], "observations":[item]}
    dossier = report(KnowledgeStore(":memory:"), [], context, "Unverified prose.",
                     snapshot=result, level="school", question="graph values")
    assert not any(claim.get("samples") for claim in dossier["claims"])
    assert "999" not in dossier["core"]
    assert any(check["status"] == "failed" for check in dossier["checks"])


def test_equation_mode_keeps_only_the_recomputed_registered_derivation():
    from uuid import uuid4
    from physis.api import snapshot
    from physis.physics import SPECS
    from physis.schema import Patch
    from physis.state import build
    from physis.tutor import teach

    experiment = build(SPECS["newton"], uuid4(), Patch(values={"force": 12, "mass": 3}))
    result = snapshot(experiment, 1, "school")
    question = "공식을 단계별로 설명해 줘"
    text = teach(question, "equation", experiment, result.run, "school", "")["text"]
    context = {"passages":[], "formula":None, "calculations":[], "observations":[]}
    dossier = report(KnowledgeStore(":memory:"), [], context, text, snapshot=result,
                     mode="equation", level="school", question=question)
    assert text in dossier["core"]
    derivation, = [claim for claim in dossier["claims"] if claim["kind"] == "registry_derivation"]
    assert derivation["status"] == "registry_verified"
    altered = report(KnowledgeStore(":memory:"), [], context, text + " Unsupported.", snapshot=result,
                     mode="equation", level="school", question=question)
    assert "Unsupported." not in altered["core"]
