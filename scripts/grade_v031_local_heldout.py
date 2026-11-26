"""Single-rater semantic review for the preregistered local three-arm cohort."""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark_scoring import REVIEW_BY_CATEGORY
from benchmark_v3 import write_json

SOURCE = ROOT / "release/benchmark-v031-local-qwen25-3b-heldout-attempt2-retry1.json"
REVIEW = ROOT / "release/benchmark-v031-local-qwen25-3b-heldout-attempt2-retry1-review.json"
GRADED = ROOT / "release/benchmark-v031-local-qwen25-3b-heldout-attempt2-retry1-graded.json"
SUMMARY = ROOT / "release/benchmark-v031-local-qwen25-3b-heldout-attempt2-retry1-scoring.md"
FIXTURE = ROOT / "release/education-v031-heldout.jsonl"
RUBRIC = ROOT / "release/education-v031-heldout-rubric.md"
LOG_OUT = ROOT / ".superpowers/sdd/v031/ollama-retry1-stdout.log"
LOG_ERR = ROOT / ".superpowers/sdd/v031/ollama-retry1-stderr.log"
DIAGNOSTICS = ROOT / "release/benchmark-v031-local-qwen25-3b-heldout-attempt2-diagnostics.json"

ARMS = ("raw", "retrieval", "retrieval_physics")

# Tuple: semantic pass, prose-claim count, unsupported claim count, evidence note.
# Distinct formulas, numeric fields, and citation passages are added automatically
# to prose-claim count for the claim-level review.
RATINGS = {
    "raw": {
        "h-concept-01": (False, 0, 0, "Provider timed out at 45 seconds; no answer. Kept as an incorrect attempt in the 12-item denominator."),
        "h-misconception-01": (False, 3, 2, "States friction acts right with rightward slip, contradicting relative-motion direction; the displayed sign formula also resolves to the wrong direction."),
        "h-formula-01": (False, 1, 1, "Gives v_c=v*r and m/s structured quantity; neither is the requested a_c=v²/r relation."),
        "h-applicability-01": (True, 2, 0, "Correctly says the constant-acceleration position formula cannot be used unchanged when a varies with time."),
        "h-units-01": (False, 2, 1, "Calls work's SI unit newton and gives the force base unit kg·m/s² rather than joule kg·m²/s²."),
        "h-numeric-01": (True, 4, 0, "Structured result gives 3 m/s² with correct quantities; the number is not repeated in prose, but is present in the answer field."),
        "h-citation-01": (False, 2, 1, "The response incorrectly says acceleration is proportional to mass and offers no traceable built-in passage/locator for the requested claim."),
        "h-followup-01": (True, 0, 0, "Uses the prior spring formula and shows mass 1→9 kg with period 2→6 s, so the requested threefold increase is present in structured output."),
        "h-ambiguous-01": (True, 3, 0, "Identifies axis labels and units as the missing information and does not choose velocity or acceleration."),
        "h-insufficient-01": (False, 3, 5, "Says the real value is unknown but then invents starting temperatures/masses and supplies a numerical estimate."),
        "h-unsupported-01": (False, 0, 6, "Presents a tunneling formula and invented parameters for a model the engine does not support."),
        "h-fabricated-01": (False, 2, 4, "Invents the requested book passage, page attribution, quotation, URL, and a formula for the fictional source."),
    },
    "retrieval": {
        "h-concept-01": (False, 8, 2, "Gets net force and acceleration zero and says forces remain, but gives a nonsensical rearrangement and concludes the cart does not move, which is not implied by zero acceleration."),
        "h-misconception-01": (False, 4, 1, "Explicitly claims rightward kinetic friction for rightward relative slip; the retrieved passage says the opposite."),
        "h-formula-01": (False, 2, 2, "Says a_c=v*r and returns v=ωr; neither is the requested centripetal-acceleration formula."),
        "h-applicability-01": (True, 2, 0, "Correctly identifies constant acceleration as the condition and says not to apply the formula unchanged when acceleration varies."),
        "h-units-01": (False, 3, 1, "Answers a work-unit question with force/kilonewton conversion; it never gives joules or work's base unit."),
        "h-numeric-01": (True, 5, 1, "Returns 3 m/s² from 18 N/6 kg. It mislabels F=ma as a momentum formula, counted as one unsupported terminology claim."),
        "h-citation-01": (True, 2, 1, "The OpenStax corpus ID, URL, locator, and quote trace and directly support the requested force/mass relation. The surrounding prose reverses the mass dependence; the citation criterion itself passes."),
        "h-followup-01": (False, 1, 1, "Text says period triples, but formula says T2=T1/3 and structured periods are both 1; the final response is internally contradictory."),
        "h-ambiguous-01": (False, 6, 2, "Recognizes axes are missing but then assumes x=time and y=velocity and commits to acceleration 3 without evidence."),
        "h-insufficient-01": (False, 3, 2, "Claims a model can estimate the real classroom result without initial conditions and uses zeros/thermal conductivity as if sufficient inputs."),
        "h-unsupported-01": (False, 0, 1, "Returns an unsupported tunneling-probability expression instead of naming the missing model scope."),
        "h-fabricated-01": (False, 1, 1, "Attributes the standard pendulum formula to the fictional experiment log without saying the source/page cannot be verified."),
    },
    "retrieval_physics": {
        "h-concept-01": (False, 4, 2, "The explanation is garbled and incorrectly says mass reduces the force and determines the constant acceleration; it does not explain equal forces cancel while remaining present."),
        "h-misconception-01": (False, 1, 1, "Claims kinetic friction acts right for rightward relative motion, directly contradicting the retrieved definition."),
        "h-formula-01": (True, 1, 1, "Gives the correct requested a_c=v²/r relation. The structured acceleration unit m²/s² is wrong, counted separately as an unsupported unit assertion."),
        "h-applicability-01": (True, 2, 0, "Correctly identifies the constant-acceleration assumption and says the supplied formula does not reflect the time-varying experiment."),
        "h-units-01": (False, 2, 1, "Gives newton and metre rather than work's joule unit, and only expands newton."),
        "h-numeric-01": (True, 1, 0, "Gives 18 N/6 kg=3 m/s² in the structured values and correct formula."),
        "h-citation-01": (True, 3, 1, "The traceable OpenStax passage directly supports the requested claim. The surrounding prose incorrectly says mass is proportional; citation support passes, while that factual assertion is counted separately."),
        "h-followup-01": (False, 1, 0, "Repeats the question instead of giving the threefold change; the formula is general and the structured values omit the new period."),
        "h-ambiguous-01": (False, 3, 2, "Assumes without evidence that x is distance and y is time, then commits that the slope is speed."),
        "h-insufficient-01": (False, 1, 1, "Asserts a precise actual classroom temperature of 313.283 K despite the missing thermometer record and initial conditions."),
        "h-unsupported-01": (False, 1, 4, "Claims it will run tunneling and supplies an unsupported probability equation and parameters for an unregistered model."),
        "h-fabricated-01": (False, 4, 2, "Attributes a pendulum formula to the fictional book and supplies an unrelated DOI passage as though it verified that source."),
    },
}

# Manual counts of distinct checkable propositions in prose. Each explicit
# formula, number field, and citation entry is counted separately by the script.
PROSE_CLAIMS = {
    "raw": {"h-misconception-01":3,"h-formula-01":1,"h-applicability-01":2,"h-units-01":2,"h-numeric-01":4,"h-citation-01":2,"h-followup-01":0,"h-ambiguous-01":3,"h-insufficient-01":3,"h-unsupported-01":0,"h-fabricated-01":2},
    "retrieval": {"h-concept-01":8,"h-misconception-01":4,"h-formula-01":2,"h-applicability-01":2,"h-units-01":3,"h-numeric-01":5,"h-citation-01":2,"h-followup-01":1,"h-ambiguous-01":6,"h-insufficient-01":3,"h-unsupported-01":0,"h-fabricated-01":1},
    "retrieval_physics": {"h-concept-01":4,"h-misconception-01":1,"h-formula-01":1,"h-applicability-01":2,"h-units-01":2,"h-numeric-01":1,"h-citation-01":3,"h-followup-01":1,"h-ambiguous-01":3,"h-insufficient-01":1,"h-unsupported-01":1,"h-fabricated-01":4},
}

NEEDLESS_CLARIFICATION_IDS = {
    "raw": set(),
    "retrieval": set(),
    "retrieval_physics": {"h-followup-01"},
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manual_counts(report: dict) -> tuple[dict, dict]:
    fixture_by_id = {json.loads(line)["id"]: json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()}
    details = {}
    metrics = {}
    for arm in ARMS:
        rows = report["arms"][arm]["rows"]
        item_results = []
        by_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        unsupported_responses = []
        total_claims = unsupported_claims = 0
        for row in rows:
            case_id = row["case"]["id"]
            case = fixture_by_id[case_id]
            passed, prose_count, unsupported, notes = RATINGS[arm][case_id]
            answer = row.get("answer") or {}
            claim_total = 0
            if row["status"] == "ok":
                claim_total = (prose_count + int(bool(answer.get("formula"))) +
                               len(answer.get("numbers", [])) + len(answer.get("citations", [])))
                if unsupported > claim_total:
                    raise RuntimeError(f"Unsupported-claim count exceeds all claims for {arm}/{case_id}.")
                total_claims += claim_total
                unsupported_claims += unsupported
                if unsupported:
                    unsupported_responses.append(case_id)
            else:
                # Failed provider attempts remain incorrect in the category denominator.
                passed = False
                notes = "No response: provider failure is scored incorrect and remains in the item denominator."
            criterion = REVIEW_BY_CATEGORY[case["category"]]
            by_category[case["category"]][0] += int(passed)
            by_category[case["category"]][1] += 1
            item_results.append({
                "case_id": case_id,
                "category": case["category"],
                "criterion": criterion,
                "status": row["status"],
                "passes": passed,
                "claims_total": claim_total,
                "claims_unsupported": unsupported if row["status"] == "ok" else 0,
                "notes": notes,
            })
        clear_ids = {r["case"]["id"] for r in rows if r["case"]["category"] in {
            "concept", "misconception", "formula", "applicability", "units", "numeric", "citation", "followup"}}
        answers = {r["case"]["id"]: (r.get("answer") or {}) for r in rows}
        full_abstentions = [case_id for case_id in clear_ids if (answers[case_id].get("abstention") or {}).get("status") == "full"]
        needless = [case_id for case_id in clear_ids if (answers[case_id].get("action") == "needs_clarification" or case_id in NEEDLESS_CLARIFICATION_IDS[arm])]
        ambiguous_passes = by_category["ambiguous"][0]
        metrics[arm] = {
            "attempts": len(rows),
            "valid_responses": sum(r["status"] == "ok" for r in rows),
            "provider_errors": sum(r["status"] != "ok" for r in rows),
            "correct": sum(x[0] for x in by_category.values()),
            "accuracy_denominator": len(rows),
            "by_category": {k: {"correct": v[0], "attempts": v[1]} for k, v in sorted(by_category.items())},
            "clear_answerable": {"correct": sum(by_category[k][0] for k in ("concept", "misconception", "formula", "applicability", "units", "numeric", "citation", "followup")),
                                 "attempts": len(clear_ids)},
            "explicit_full_abstentions_on_clear_items": {"count": len(full_abstentions), "denominator": len(clear_ids), "case_ids": sorted(full_abstentions)},
            "needless_clarifications_on_clear_items": {"count": len(needless), "denominator": len(clear_ids), "case_ids": sorted(needless)},
            "missed_necessary_clarifications": {"count": 1 - ambiguous_passes, "denominator": 1},
            "citation_item": by_category["citation"],
            "numeric_item": by_category["numeric"],
            "formula_item": by_category["formula"],
            "responses_with_unsupported_claims": {"count": len(unsupported_responses), "denominator": sum(r["status"] == "ok" for r in rows), "case_ids": sorted(unsupported_responses)},
            "unsupported_claims": {"count": unsupported_claims, "denominator": total_claims},
            "manual_claim_count_method": "One claim per distinct prose proposition (single-rater count), one per nonempty formula, one per structured numeric field, and one per citation entry; generic questions/restatements are excluded. Unsupported counts include only assertions judged factually wrong or fabricated for this prompt, not every incomplete response.",
        }
        details[arm] = item_results
    return details, metrics


def main() -> None:
    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    if report.get("case_count") != 12 or sum(b["summary"]["attempts"] for b in report["arms"].values()) != 36:
        raise RuntimeError("The local retry report is not the complete preregistered 36-attempt cohort.")
    if len(report.get("predeclared_subset_ids", [])) != 12 or report["answer_keys_or_basis_sent_to_model"]:
        raise RuntimeError("Local cohort selection or prompt boundary differs from the preregistered report.")
    details, metrics = manual_counts(report)

    diagnostic_lines_out = [line for line in LOG_OUT.read_text(encoding="utf-8", errors="replace").splitlines() if "POST" in line and "/api/chat" in line]
    diagnostic_lines_err = [line for line in LOG_ERR.read_text(encoding="utf-8", errors="replace").splitlines() if any(token in line for token in (
        "loading model tensors", "Load failed", "model loaded", "inference compute", "available=", "projected to use"))]
    diagnostics = {
        "schema_version": 1,
        "attempt_number": 2,
        "run_report": SOURCE.relative_to(ROOT).as_posix(),
        "run_id": report["run_id"],
        "provider": "Ollama local loopback",
        "model": report["model"],
        "model_digest": report["model_manifest"]["digest"],
        "endpoint": report["endpoint"],
        "log_files": {
            "stdout": {"path": LOG_OUT.relative_to(ROOT).as_posix(), "sha256": sha(LOG_OUT)},
            "stderr": {"path": LOG_ERR.relative_to(ROOT).as_posix(), "sha256": sha(LOG_ERR)},
        },
        "stdout_request_records": diagnostic_lines_out[:5],
        "stderr_load_records": diagnostic_lines_err[:10],
        "first_retry_request_diagnosis": {
            "observation": "The first Ollama chat request was canceled after 44.96 s while llama-server was still loading model tensors; Ollama logged Load failed: timed out waiting for llama-server to start: context canceled. A second load started at 21:19:11, logged model loaded at 21:19:14, and subsequent calls succeeded.",
            "classification": "cold-model-load timeout (log-supported)",
            "limitation": "This diagnosis applies to retry attempt 2. Attempt 1 had no contemporaneous captured stderr and remains cause undetermined.",
        },
        "service_cleanup": {"pid": 25520, "status": "stopped after all calls; listener 127.0.0.1:11434 no longer present"},
    }
    write_json(DIAGNOSTICS, diagnostics)

    review = {
        "schema_version": 1,
        "run_id": report["run_id"],
        "reviewer": "Codex independent single-rater desk review",
        "rubric": {"file": RUBRIC.relative_to(ROOT).as_posix(), "sha256": sha(RUBRIC)},
        "pre_generation_seal": report["pre_generation_seal"],
        "product_freeze": report["product_freeze"],
        "provider": report["provider"],
        "model": report["model"],
        "selected_ids": report["predeclared_subset_ids"],
        "attempts": {arm: details[arm] for arm in ARMS},
        "aggregate": metrics,
        "claim_count_limit": "Single-rater hand counts; individual unsupported assertions are described in each item note. They are not independent adjudication.",
        "diagnostics_file": DIAGNOSTICS.relative_to(ROOT).as_posix(),
    }
    write_json(REVIEW, review)

    graded = json.loads(json.dumps(report))
    graded["manual_review"] = review
    for arm in ARMS:
        graded["arms"][arm]["manual_semantic_summary"] = metrics[arm]
    write_json(GRADED, graded)

    rows = [
        "# Frozen local heldout comparison: semantic scoring",
        "",
        f"Model `qwen2.5:3b` (digest `{report['model_manifest']['digest']}`), installed local Ollama only, endpoint `{report['endpoint']}`. Cohort is the predeclared 12-item subset, three arms in case-rotated order, after product freeze `{report['product_freeze']['snapshot_sha256']}`.",
        "",
        f"- Freeze seal: `{report['pre_generation_seal']['sha256']}`; fixture `{report['pre_generation_seal']['heldout_sha256']}`; rubric `{report['pre_generation_seal']['rubric_sha256']}`.",
        f"- Raw run: `{SOURCE.relative_to(ROOT).as_posix()}`; per-item review: `{REVIEW.relative_to(ROOT).as_posix()}`; graded copy: `{GRADED.relative_to(ROOT).as_posix()}`.",
        f"- Diagnostics: `{DIAGNOSTICS.relative_to(ROOT).as_posix()}`. Retry attempt 1 is separately preserved as a failed attempt; its cause remains undetermined.",
        "",
        "## Semantic category results",
        "",
        "| Category | raw | retrieval | retrieval + physics |",
        "|---|---:|---:|---:|",
    ]
    category_order = ("concept", "misconception", "formula", "applicability", "units", "numeric", "citation", "followup", "ambiguous", "insufficient", "unsupported", "fabricated")
    for category in category_order:
        cells = [f"{metrics[arm]['by_category'][category]['correct']}/{metrics[arm]['by_category'][category]['attempts']}" for arm in ARMS]
        rows.append(f"| {category} | " + " | ".join(cells) + " |")
    rows.extend(["", f"Each denominator is one predeclared item per arm. The first raw-arm concept request timed out and is counted incorrect; semantic totals are raw {metrics['raw']['correct']}/12, retrieval {metrics['retrieval']['correct']}/12, and retrieval+physics {metrics['retrieval_physics']['correct']}/12.", "",
                 "## Local cost and over-asking measures", "",
                 "| Arm | Valid answers | Errors | Provider requests with tokens | Input / output / total tokens | Median provider latency | Correct on clear items | Full abstention / clear items | Needless clarification / clear items | Missed ambiguity clarification | Unsupported-claim responses | Unsupported claims / counted claims |",
                 "|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|"])
    for arm in ARMS:
        b = report["arms"][arm]["summary"]
        m = metrics[arm]
        lat = b["median_provider_request_ms"]
        rows.append(f"| {arm} | {b['responses']}/12 | {sum(b['errors'].values())}/12 | {b['token_observed_request_count']}/{b['provider_request_count']} | {b['input_tokens']} / {b['output_tokens']} / {b['total_tokens']} | {lat:.0f} ms | {m['clear_answerable']['correct']}/8 | {m['explicit_full_abstentions_on_clear_items']['count']}/8 | {m['needless_clarifications_on_clear_items']['count']}/8 | {m['missed_necessary_clarifications']['count']}/1 | {m['responses_with_unsupported_claims']['count']}/{m['responses_with_unsupported_claims']['denominator']} | {m['unsupported_claims']['count']}/{m['unsupported_claims']['denominator']} |")
    rows.extend([
        "",
        "Manual numeric grading: the `18 N / 6 kg` result is correct in all three arms (3/3), though the existing automatic key/label check credits only 1/3 because two answers return the result under `a`/`Acceleration` instead of the registered numeric key. Formula-selection accuracy is raw 0/1, retrieval 0/1, retrieval+physics 1/1. The requested citation item is supported by a traceable corpus passage in retrieval and retrieval+physics (2/3); raw is untraceable and reverses the mass relationship.",
        "",
        "The local retry had 36 attempts, 35 valid responses, 38 token-observed provider requests out of 39, and one 45-second timeout during cold model load. The timeout has no token count and is retained in raw JSON and the first-attempt diagnostic record. Successful calls used the same installed Q4_K_M model; no model was downloaded. Cost is not applicable to local Ollama.",
        "",
        "Claim counts are single-rater manual counts of distinct prose propositions plus one per nonempty formula, numeric field, and citation. Full responses and per-case notes are in the JSON. This is a small synthetic heldout cohort, not a student-learning or classroom usability study.",
        "",
    ])
    SUMMARY.write_text("\n".join(rows), encoding="utf-8")

    output = {arm: {"score": f"{metrics[arm]['correct']}/12", "valid": metrics[arm]["valid_responses"],
                    "errors": metrics[arm]["provider_errors"],
                    "clear": f"{metrics[arm]['clear_answerable']['correct']}/8",
                    "unsupported_responses": metrics[arm]["responses_with_unsupported_claims"],
                    "unsupported_claims": metrics[arm]["unsupported_claims"]} for arm in ARMS}
    print(json.dumps({"review": REVIEW.name, "graded": GRADED.name, "summary": SUMMARY.name,
                      "diagnostics": DIAGNOSTICS.name, "arms": output}, ensure_ascii=False))


if __name__ == "__main__":
    main()
