"""Combine and semantically score the pre-freeze local Ollama regression receipts.

This script makes no provider requests. The rubric judgments are an explicit,
single-evaluator desk review of the stored responses; it is not a teacher study.
"""
from __future__ import annotations

import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark_scoring import summarize

ARMS = ("raw", "retrieval", "retrieval_physics")
METRIC_CASES = {
    "concept_accuracy": ("f-concept-3", "f-misconception-3"),
    "numeric_answer": ("f-numeric-3",),
    "formula_choice": ("f-formula-3",),
    "citation_support": ("f-citation-3",),
    "ambiguous_question_handling": ("f-ambiguous-3",),
    "insufficient_evidence_handling": ("f-insufficient-3",),
    "fabricated_reference_handling": ("f-fabricated-3",),
    "unsupported_scope_handling": ("f-unsupported-3",),
    "followup_consistency": ("f-followup-3",),
    "applicability_accuracy": ("f-applicability-3",),
    "unit_accuracy": ("f-units-3",),
}
SCORES = {
    "f-concept-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-numeric-3": {"raw": True, "retrieval": False, "retrieval_physics": False},
    "f-ambiguous-3": {"raw": False, "retrieval": True, "retrieval_physics": True},
    "f-insufficient-3": {"raw": True, "retrieval": False, "retrieval_physics": False},
    "f-citation-3": {"raw": False, "retrieval": False, "retrieval_physics": True},
    "f-fabricated-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-unsupported-3": {"raw": True, "retrieval": False, "retrieval_physics": True},
    "f-followup-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-applicability-3": {"raw": False, "retrieval": True, "retrieval_physics": True},
    "f-units-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-formula-3": {"raw": True, "retrieval": True, "retrieval_physics": True},
    "f-misconception-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
}

# One or more materially false or ungrounded claims in a response. This is a
# response-incidence measure, not a claim-count rate. Provider errors are null.
UNSUPPORTED = {
    "f-concept-3": {"raw": None, "retrieval": True, "retrieval_physics": False},
    "f-numeric-3": {"raw": True, "retrieval": True, "retrieval_physics": False},
    "f-ambiguous-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-insufficient-3": {"raw": True, "retrieval": True, "retrieval_physics": True},
    "f-citation-3": {"raw": True, "retrieval": True, "retrieval_physics": False},
    "f-fabricated-3": {"raw": True, "retrieval": True, "retrieval_physics": True},
    "f-unsupported-3": {"raw": False, "retrieval": True, "retrieval_physics": False},
    "f-followup-3": {"raw": True, "retrieval": True, "retrieval_physics": True},
    "f-applicability-3": {"raw": True, "retrieval": False, "retrieval_physics": False},
    "f-units-3": {"raw": True, "retrieval": True, "retrieval_physics": True},
    "f-formula-3": {"raw": True, "retrieval": True, "retrieval_physics": False},
    "f-misconception-3": {"raw": True, "retrieval": True, "retrieval_physics": False},
}
NEEDLESS_CLARIFICATION = {
    "f-concept-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-numeric-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-citation-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-formula-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-misconception-3": {"raw": False, "retrieval": False, "retrieval_physics": True},
    "f-followup-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-applicability-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
    "f-units-3": {"raw": False, "retrieval": False, "retrieval_physics": False},
}
EXPLICIT_ABSTENTION = {case_id: {arm: False for arm in ARMS} for case_id in NEEDLESS_CLARIFICATION}
NOTES = {
    "f-concept-3": {
        "raw": "Provider timed out at 45 seconds; counted as an accuracy failure.",
        "retrieval": "Did not clearly state that one coil oscillates around equilibrium instead of traveling with the compression; its own explanation was inconsistent.",
        "retrieval_physics": "Echoed the question without answering it.",
    },
    "f-numeric-3": {
        "raw": "Structured numbers contain 12,000 Pa with the requested SI unit; the automatic checker missed it because the label/key differs from its exact expected label.",
        "retrieval": "Gave the formula but no pressure result.",
        "retrieval_physics": "Gave the formula but no pressure result.",
    },
    "f-ambiguous-3": {
        "raw": "Named both possible meanings but asked how to distinguish them instead of asking which quantity the learner intends.",
        "retrieval": "Identified wave propagation versus particle motion as the required measurement distinction.",
        "retrieval_physics": "Identified wave propagation versus particle motion as the required measurement distinction.",
    },
    "f-insufficient-3": {
        "raw": "Correctly withheld the real temperature and named missing inputs, but added a false formula, invented values, and an unverified source.",
        "retrieval": "Said the actual value was unknown, then invented example inputs, an incorrect formula, and a source.",
        "retrieval_physics": "Claimed a measured final temperature despite no measurements or run evidence in context.",
    },
    "f-citation-3": {
        "raw": "Citation did not trace to the corpus; the explanation also misattributed the result to Newton's first law.",
        "retrieval": "The passage is real and traceable, but the answer contradicts it by saying one ball lands sooner.",
        "retrieval_physics": "The answer and traceable passage support mass-independent gravitational acceleration.",
    },
    "f-fabricated-3": {
        "raw": "Did not repeat the fictional source, but answered an unrelated default uniform-motion task instead of refusing the false premise.",
        "retrieval": "Attributed invented content, URL, and page to the explicitly fictional title.",
        "retrieval_physics": "Returned a fabricated citation to the explicitly fictional title and unrelated default-run values.",
    },
    "f-unsupported-3": {
        "raw": "Correctly explained that the registered engine cannot simulate the requested white-dwarf model.",
        "retrieval": "Refused the run but added unsupported particle terminology, a formula, values, and an unrelated source.",
        "retrieval_physics": "Correctly described the model as outside the engine's scope.",
    },
    "f-followup-3": {
        "raw": "The prose says wavelength doubles while the formula and structured value say it halves; the citation is unverified.",
        "retrieval": "The prose says both that wavelength doubles and halves; numeric fields contain the correct doubled value.",
        "retrieval_physics": "The prose and number say wavelength doubles, but the formula conflicts with both and the citations do not support the relation.",
    },
    "f-applicability-3": {
        "raw": "Gives an incorrect infinite-speed explanation and an unverified citation.",
        "retrieval": "Identifies the small-angle linear-restoring-force assumption and gives a relevant source.",
        "retrieval_physics": "Identifies that the small-angle assumption fails; the extra default-run value is tangential but not treated as unsupported because it was present in the active-run context.",
    },
    "f-units-3": {
        "raw": "Did not answer the unit and supplied an unverified citation.",
        "retrieval": "Incorrectly gives s⁻¹ instead of m/s.",
        "retrieval_physics": "Incorrectly says the product is unitless.",
    },
    "f-formula-3": {
        "raw": "The requested small-angle pendulum formula is correct; the extra numeric value and citation are not supported by the answer context.",
        "retrieval": "Formula is correct; the extra 1.0 s value is inconsistent with the included 1 m and 9.81 m/s².",
        "retrieval_physics": "The formula is correct; the extra period value is consistent with the active run, although the cited passages do not state the equation.",
    },
    "f-misconception-3": {
        "raw": "Incorrectly says the objects fall more slowly.",
        "retrieval": "Incorrectly says soft objects fall more slowly, despite its own citation saying otherwise.",
        "retrieval_physics": "Asked whether times differ instead of directly correcting the misconception; this is one needless clarification on a clear item.",
    },
}


def load_parts(paths: list[Path]) -> list[dict]:
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    if not reports or any(r.get("provider") != "ollama" or r.get("model") != "qwen2.5:3b" for r in reports):
        raise ValueError("Expected only the local qwen2.5:3b receipts.")
    if len({r["source_split_sha256"] for r in reports}) != 1:
        raise ValueError("Regression split hashes do not match.")
    return reports


def aggregate_calls(rows: list[dict]) -> dict:
    calls = [c for row in rows for c in row.get("provider_requests", [])]
    observed = [c for c in calls if type(c.get("input_tokens")) is int and type(c.get("output_tokens")) is int]
    latencies = [c["latency_ms"] for c in calls if type(c.get("latency_ms")) is int]
    return {
        "provider_request_count": len(calls),
        "token_observed_request_count": len(observed),
        "input_tokens": sum(c["input_tokens"] for c in observed),
        "output_tokens": sum(c["output_tokens"] for c in observed),
        "total_tokens": sum(c["input_tokens"] + c["output_tokens"] for c in observed),
        "median_provider_request_ms": round(statistics.median(latencies), 2) if latencies else None,
        "provider_request_latencies_ms": latencies,
        "failed_requests": sum(c.get("status") != "ok" for c in calls),
    }


def combine(paths: list[Path]) -> dict:
    parts = load_parts(paths)
    rows_by_arm = {arm: [] for arm in ARMS}
    for part in parts:
        for arm in ARMS:
            rows_by_arm[arm].extend(part["arms"][arm]["rows"])
    ids = [row["case"]["id"] for row in rows_by_arm[ARMS[0]]]
    if len(ids) != 12 or len(set(ids)) != 12:
        raise ValueError("The matched prior-regression cohort must contain 12 unique items per arm.")
    for arm in ARMS:
        arm_ids = [row["case"]["id"] for row in rows_by_arm[arm]]
        if set(arm_ids) != set(ids):
            raise ValueError(f"Matched item IDs differ for {arm}.")

    report = {
        "schema_version": 1,
        "snapshot": "PRE-FREEZE DEVELOPMENT-TIME MEASUREMENT; prior v0.3 regression only",
        "combined_utc": datetime.now(UTC).isoformat(),
        "design": "Same installed qwen2.5:3b model, same question/output contract and actual PHYSIS Ollama adapter. Arms: raw input; retrieval context; retrieval plus active physics run.",
        "source_split": "Existing v0.3 final regression fixture, stratified allowlist; this is not an independent heldout cohort.",
        "source_split_sha256": parts[0]["source_split_sha256"],
        "selected_ids": ids,
        "screening": "12/12 selected prompts were screened before generation; none matched the weapons/attack term screen. No prompt was sent to a cloud endpoint.",
        "endpoint": "http://127.0.0.1:11434",
        "provider": "ollama",
        "model": parts[0]["model"],
        "model_manifest": parts[0]["model_manifest"],
        "machine": parts[0]["machine"],
        "measurement_parts": [
            {"file": p.name, "run_id": part["run_id"], "started_utc": part["started_utc"],
             "finished_utc": part["finished_utc"], "code_sha256": part["code_sha256"]}
            for p, part in zip(paths, parts)
        ],
        "manual_review": {
            "reviewer": "Codex evaluator desk review; one reviewer, no independent teacher adjudication.",
            "pass_rule": "A response passes only when it directly answers the item's rubric without a material contradiction. Provider errors count as incorrect for the item's accuracy denominator.",
            "claim_incidence_rule": "Binary per response: at least one materially false, fabricated, or ungrounded physics, source, number, or simulation assertion. Provider errors are reported separately and excluded from the answered-response denominator.",
            "clear_answerable_ids": ["f-concept-3", "f-numeric-3", "f-citation-3", "f-formula-3", "f-misconception-3", "f-followup-3", "f-applicability-3", "f-units-3"],
            "scores": SCORES,
            "unsupported_assertion_present": UNSUPPORTED,
            "unnecessary_clarification": NEEDLESS_CLARIFICATION,
            "explicit_abstention_on_clear_item": EXPLICIT_ABSTENTION,
            "case_notes": NOTES,
        },
        "arms": {},
    }
    for arm in ARMS:
        rows = rows_by_arm[arm]
        status_counts = {"attempts": len(rows), "responses": sum(r["status"] == "ok" for r in rows),
                         "provider_errors": sum(r["status"] != "ok" for r in rows),
                         "provider_error_ids": [r["case"]["id"] for r in rows if r["status"] != "ok"]}
        auto = summarize(rows)
        manual = {}
        for metric, case_ids in METRIC_CASES.items():
            passed = sum(SCORES[cid][arm] is True for cid in case_ids)
            manual[metric] = {"correct": passed, "denominator": len(case_ids),
                              "items": {cid: SCORES[cid][arm] for cid in case_ids}}
        valid = sum(UNSUPPORTED[row["case"]["id"]][arm] is not None for row in rows)
        claim_hits = sum(UNSUPPORTED[row["case"]["id"]][arm] is True for row in rows)
        clear_ids = report["manual_review"]["clear_answerable_ids"]
        needless_hits = sum(NEEDLESS_CLARIFICATION[cid][arm] for cid in clear_ids)
        abstention_hits = sum(EXPLICIT_ABSTENTION[cid][arm] for cid in clear_ids)
        manual["unsupported_assertion_response_incidence"] = {
            "responses_with_unsupported_assertion": claim_hits,
            "answered_response_denominator": valid,
            "attempt_denominator_including_provider_errors": len(rows),
        }
        manual["excessive_abstention_on_clear_items"] = {
            "explicit_abstentions": abstention_hits, "attempt_denominator": len(clear_ids),
            "provider_errors_inside_denominator": sum(r["case"]["id"] in clear_ids and r["status"] != "ok" for r in rows),
        }
        manual["needless_clarification_on_clear_items"] = {
            "needless_clarifications": needless_hits, "attempt_denominator": len(clear_ids),
        }
        manual["missing_clarification_on_ambiguous_item"] = {
            "missing": int(SCORES["f-ambiguous-3"][arm] is False), "denominator": 1,
        }
        report["arms"][arm] = {
            "execution": status_counts,
            "telemetry": aggregate_calls(rows),
            "automatic_metrics": auto["metrics"],
            "manual_metrics": manual,
        }
    return report


def markdown(report: dict, json_name: str) -> str:
    arms = report["arms"]
    lines = [
        "# PHYSIS v0.3.1 local model evaluation (pre-freeze)", "",
        f"**Snapshot:** {report['snapshot']}. Combined {report['combined_utc']}. This is development-time evidence on the existing v0.3 regression set, not release acceptance or an independent heldout test.", "",
        "## Setup", "",
        f"- Provider/model: `{report['provider']}` / `{report['model']}`; installed digest `{report['model_manifest'].get('digest')}`; local endpoint `{report['endpoint']}` only.",
        "- Hardware inventory: Intel Core i7-13620H, about 15.7 GiB RAM, RTX 4050 Laptop GPU (6,141 MiB VRAM, driver 621.01).",
        "- Conditions: same model, questions and output schema in all arms; raw context, retrieval passages, and retrieval plus the active physics run. Arm order was rotated by case within each run.",
        "- Cases: 12 prior-regression items (10-item main run plus formula and misconception extension); one prior multi-turn case creates 13 provider requests per arm.",
        "- Safety and routing: all 12 allowlisted prompts were screened before generation. All generations went to Ollama on `127.0.0.1`; no cloud endpoint, paid service, or model download was used.",
        "- The first 10-item process imported the app before setting python-dotenv's disable flag; however, it pinned `OLLAMA_BASE_URL` to loopback before the first generation and used an explicit Ollama selection throughout. The two-item extension additionally set `PYTHON_DOTENV_DISABLED=1` before importing the app. No cloud calls were made.",
        "", "## Execution, tokens and speed", "",
        "| Arm | Responses / attempts | Provider requests | Token coverage | Input tokens | Output tokens | Median request latency | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for arm, block in arms.items():
        e, t = block["execution"], block["telemetry"]
        lines.append(f"| `{arm}` | {e['responses']}/{e['attempts']} | {t['provider_request_count']} | {t['token_observed_request_count']}/{t['provider_request_count']} | {t['input_tokens']:,} | {t['output_tokens']:,} | {t['median_provider_request_ms']:.0f} ms | {e['provider_errors']} |")
    lines += [
        "", "Latency is the adapter's per-request timer; the raw arm includes its 45,003 ms timeout in the median. Token counts are Ollama's prompt/evaluation counters. Local electricity cost was not measured.",
        "", "## Manual semantic review", "",
        "Each category is reported on its own denominator; no composite accuracy score is used. Failed responses count as incorrect in their category denominator. Scores are a single evaluator's semantic desk review, without a second teacher or inter-rater measurement.",
        "", "| Criterion | Raw | Retrieval | Retrieval + physics |",
        "|---|---:|---:|---:|",
    ]
    metric_labels = {
        "concept_accuracy": "Concept / misconception accuracy",
        "numeric_answer": "Numeric answer",
        "formula_choice": "Formula choice",
        "citation_support": "Citation supports target claim",
        "ambiguous_question_handling": "Clarifies ambiguous target",
        "insufficient_evidence_handling": "Insufficient evidence handling",
        "fabricated_reference_handling": "Rejects fabricated reference",
        "unsupported_scope_handling": "Unsupported simulation scope",
        "followup_consistency": "Follow-up consistency",
        "applicability_accuracy": "Applicability condition",
        "unit_accuracy": "Unit accuracy",
    }
    for metric, label in metric_labels.items():
        vals=[]
        for arm in ARMS:
            x=arms[arm]["manual_metrics"][metric]
            vals.append(f"{x['correct']}/{x['denominator']}")
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines += ["", "## Automatic checks", "",
              "| Check | Raw | Retrieval | Retrieval + physics |",
              "|---|---:|---:|---:|"]
    auto_labels = {
        "numeric_accuracy": "Numeric accuracy (strict label/key matcher)",
        "source_trace": "All returned citations trace to corpus",
        "requested_source_trace": "At least one traceable citation on citation request",
        "simulation_scope_accuracy": "Simulation support/status fields",
        "fabricated_source_attribution": "Invented source bait appears in citation field (lower is better)",
    }
    for metric, label in auto_labels.items():
        vals=[]
        for arm in ARMS:
            x=arms[arm]["automatic_metrics"][metric]
            vals.append(f"{x['n']}/{x['d']}")
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines += ["", "## Over-asking and unsupported assertions", "",
              "| Measure | Raw | Retrieval | Retrieval + physics |",
              "|---|---:|---:|---:|"]
    for metric, label, formatter in (
        ("unsupported_assertion_response_incidence", "Unsupported-assertion incidence", lambda x: f"{x['responses_with_unsupported_assertion']}/{x['answered_response_denominator']} answered; {x['responses_with_unsupported_assertion']}/{x['attempt_denominator_including_provider_errors']} attempts"),
        ("excessive_abstention_on_clear_items", "Explicit abstention on 8 clear items", lambda x: f"{x['explicit_abstentions']}/{x['attempt_denominator']} (errors: {x['provider_errors_inside_denominator']})"),
        ("needless_clarification_on_clear_items", "Needless clarification on 8 clear items", lambda x: f"{x['needless_clarifications']}/{x['attempt_denominator']}"),
    ):
        values = [formatter(arms[arm]["manual_metrics"][metric]) for arm in ARMS]
        lines.append(f"| {label} | {values[0]} | {values[1]} | {values[2]} |")
    missing = [f"{arms[arm]['manual_metrics']['missing_clarification_on_ambiguous_item']['missing']}/1" for arm in ARMS]
    lines.append(f"| Missing clarification on ambiguous item | {missing[0]} | {missing[1]} | {missing[2]} |")
    lines += [
        "", "The direct rates above are arm-specific, with each measure's denominator stated. Explicit over-abstention was 0/8 in every arm. One retrieval+physics response to a fully specified vacuum-fall question returned a question instead of the answer (1/8 needless clarification). The raw ambiguity response named the alternatives but did not ask the learner to choose; retrieval and retrieval+physics identified the wave-speed versus particle-speed distinction.",
        "", "## Main failures and comparison with v0.3", "",
        "The earlier v0.3 Mock report recorded concept accuracy 3/12, formula choice 1/6, ambiguity handling 0/6, insufficient-evidence handling 0/6, citation support 3/6, and follow-up consistency 2/6. The recorded failure notes repeatedly identify answers that miss the requested distinction, omit the requested formula, proceed without asking for missing measurements, lose earlier conditions, or return a traceable passage that does not support the target claim.",
        "", "This local subset reproduces those failure modes in new outputs: all arms missed the longitudinal-wave concept item; only one of three numeric outputs included the requested pressure value; all three chose the small-angle pendulum formula; all three failed the fabricated-reference item (raw answered an unrelated task, while the other two invented source content); and all three follow-up outputs contained a material problem (prose/formula disagreement or an unsupported formula). The physics-context arm gave the supported fall explanation and scope refusal, but still missed the concept, numeric, unit, misconception and evidence-absence items.",
        "", "## Limits", "",
        "- This is a fixed 12-item subset from the old final regression fixture, not new heldout material. The main and two-item extension were separate runs; the extension used the same model and method but a hardened dotenv boundary.",
        "- Small sample: most category denominators are one item per arm; only concept accuracy has two. This does not support broad claims about Korean tutoring quality or learning outcomes.",
        "- Manual scoring is a single desk review. No teacher panel, independent adjudication, student study, or inter-rater agreement was measured.",
        "- Traceability is not semantic support: retrieval and retrieval+physics each passed the automatic source-trace check on the citation request, but the retrieval answer contradicted the cited statement. The output schema's automatic numeric checker marked the raw 12,000 Pa structured value wrong because its exact target label/key did not match; manual review counted the correctly labeled SI result. Automatic and manual scores are kept distinct.",
        "- This benchmark calls the real Ollama generation adapter directly through the evaluation harness. It is not a post-freeze end-to-end tutor UI/endpoint measurement.",
        "", "## Artifacts", "",
        f"- Combined metrics and manual review: `{json_name}`",
        "- Main raw responses: `benchmark-v031-local-qwen25-3b.json`",
        "- Formula/misconception extension raw responses: `benchmark-v031-local-qwen25-3b-extension-2.json`",
        "- Evaluator runner: `scripts/independent_v031.py`; combiner/scoring record: `scripts/independent_v031_combine.py`",
        "",
    ]
    # Keep the table valid Markdown while retaining separate arm-specific measures.
    return "\n".join(lines)


def main() -> None:
    first = ROOT / "release" / "benchmark-v031-local-qwen25-3b.json"
    extension = ROOT / "release" / "benchmark-v031-local-qwen25-3b-extension-2.json"
    out_json = ROOT / "release" / "benchmark-v031-local-qwen25-3b-pre-freeze-12case-graded.json"
    out_md = ROOT / "release" / "benchmark-v031-local-qwen25-3b-pre-freeze-12case-graded.md"
    report = combine([first, extension])
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out_md.write_text(markdown(report, out_json.name), encoding="utf-8")
    print(out_json.name, out_md.name)
    for arm, block in report["arms"].items():
        print(arm, block["execution"], block["telemetry"])


if __name__ == "__main__":
    main()
