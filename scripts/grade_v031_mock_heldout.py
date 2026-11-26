"""Apply the preregistered single-rater education rubric to the frozen Mock cohort."""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from benchmark_scoring import apply_review, digest, review_sheet
from benchmark_v3 import write_json

SOURCE = ROOT / "release/benchmark-v031-mock-heldout-24.json"
REVIEW = ROOT / "release/benchmark-v031-mock-heldout-24-review.json"
GRADED = ROOT / "release/benchmark-v031-mock-heldout-24-graded.json"
SUMMARY = ROOT / "release/benchmark-v031-mock-heldout-24-scoring.md"
FIXTURE = ROOT / "release/education-v031-heldout.jsonl"

# Category judgment is per frozen rubric. Formula 2 accepts heat capacity as an
# equivalent to mass times common specific heat; formula 1 does not show v/r.
RATINGS = {
    "h-concept-01": (False, 0, 0, "Full abstention on an answerable force-cancellation question; no explanation of the existing equal and opposite forces."),
    "h-concept-02": (False, 11, 0, "States the correct fixed-volume Kelvin proportionality and p=nRT/V but omits the requested molecular kinetic-energy/collision mechanism, so it does not explain why pressure rises."),
    "h-misconception-01": (True, 11, 0, "Correctly says kinetic friction opposes motion and explains slowing; the stationary-floor context makes the direction correct, though it does not explicitly say relative surface motion."),
    "h-misconception-02": (False, 0, 0, "Full abstention; it does not distinguish zero instantaneous velocity from continuing downward gravitational acceleration."),
    "h-formula-01": (False, 11, 0, "Gives a_c=omega^2 R but does not express the requested variables v and r or connect omega=v/r."),
    "h-formula-02": (True, 11, 0, "Gives the equivalent heat-capacity weighted mean; for the same material C_i=m_i c, so the common c cancels. Extra simulation state is not needed for the formula."),
    "h-applicability-01": (False, 0, 0, "Full abstention; it does not identify constant acceleration as the formula's applicability condition."),
    "h-applicability-02": (False, 10, 1, "The prompt says viscous loss matters, yet the answer runs and reports an ideal no-loss Bernoulli result. It names an inviscid assumption but never states the formula is inapplicable or that a loss term/model is needed."),
    "h-units-01": (False, 4, 0, "Only states that equation dimensions must match; it omits J, N·m, and kg·m²/s²."),
    "h-units-02": (False, 0, 0, "Full abstention; it omits Pa=N/m²=kg/(m·s²)."),
    "h-numeric-01": (False, 2, 1, "Needlessly asks whether the explicitly supplied net force is net and refuses to calculate 18/6=3 m/s²."),
    "h-numeric-02": (True, 9, 0, "Correctly reports gauge pressure 29,792 Pa with the requested unit. The additional absolute-pressure value is clearly labeled separately."),
    "h-citation-01": (True, 11, 0, "Provides two traceable Newton's second-law passages whose original quotes directly support acceleration proportional to net force and inversely proportional to mass."),
    "h-citation-02": (False, 0, 0, "Full abstention; it provides no section or original quotation for the pressure-temperature claim."),
    "h-followup-01": (False, 0, 0, "Full abstention; it does not use the same spring and small-oscillation condition to give a threefold period."),
    "h-followup-02": (False, 0, 0, "Full abstention; it does not carry forward the 12 m/s speed to calculate a 2 m wavelength."),
    "h-ambiguous-01": (False, 4, 0, "Does not ask whether the graph is position-time or velocity-time; dimensional-analysis citations do not resolve the missing axes."),
    "h-ambiguous-02": (False, 12, 1, "Assumes 12 is a net force in newtons and uses a default mass to output acceleration; it should ask for unit, net-force status, and mass."),
    "h-insufficient-01": (True, 1, 0, "Correctly says a real classroom measurement cannot be inferred and asks for the measurement or raw data."),
    "h-insufficient-02": (False, 10, 0, "Returns a default friction simulation instead of saying the real coefficient is unknown and requesting measurements/material records."),
    "h-unsupported-01": (False, 0, 0, "Generic evidence abstention does not state that the registered engine has no quantum-tunneling model or explain scope."),
    "h-unsupported-02": (False, 0, 0, "Generic evidence abstention does not state that 3D turbulence/heat-transfer coupling is outside the registered simulation scope."),
    "h-fabricated-01": (True, 0, 0, "Does not invent the requested title, page, quote, or URL and says it could not verify a supporting passage."),
    "h-fabricated-02": (True, 0, 0, "Does not attribute a fabricated manual section or quote and says it could not verify a supporting passage."),
}


def main() -> None:
    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    if report.get("case_count") != 24 or report.get("arms", {}).get("mock", {}).get("summary", {}).get("responses") != 24:
        raise RuntimeError("Frozen Mock heldout report is incomplete or has changed.")
    cases = [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines() if line.strip()]
    id_by_question = {case["question"]: case["id"] for case in cases}
    sheet = {"run_id": report["run_id"], "reviewer": "Codex independent single-rater desk review", "samples": review_sheet(report)}
    for sample in sheet["samples"]:
        case_id = id_by_question[sample["question"]]
        if case_id not in RATINGS:
            raise RuntimeError(f"No frozen rating for {case_id}")
        passes, total, unsupported, notes = RATINGS[case_id]
        sample.update({"case_id": case_id, "passes": passes, "claims_total": total,
                       "claims_unsupported": unsupported, "notes": notes})
    if {sample["case_id"] for sample in sheet["samples"]} != set(RATINGS):
        raise RuntimeError("Review does not cover every heldout case exactly once.")

    graded = json.loads(json.dumps(report))
    apply_review(graded, sheet)
    write_json(REVIEW, sheet)
    write_json(GRADED, graded)

    category_counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for sample in sheet["samples"]:
        category = next(case["category"] for case in cases if case["id"] == sample["case_id"])
        category_counts[category][0] += int(sample["passes"])
        category_counts[category][1] += 1
    clear_ids = {case["id"] for case in cases if case["category"] in {
        "concept", "misconception", "formula", "applicability", "units", "numeric", "citation", "followup"}}
    answers = {row["case"]["id"]: row["answer"] for row in report["arms"]["mock"]["rows"]}
    full_abstentions = [case_id for case_id in clear_ids if (answers[case_id].get("abstention") or {}).get("status") == "full"]
    needless = [case_id for case_id in clear_ids if answers[case_id].get("action") == "needs_clarification"]
    ambiguous = [case["id"] for case in cases if case["category"] == "ambiguous"]
    missed_clarifications = [case_id for case_id in ambiguous if answers[case_id].get("action") != "needs_clarification"]
    totals = [sample["claims_total"] for sample in sheet["samples"]]
    uns = [sample["claims_unsupported"] for sample in sheet["samples"]]
    total_claims, unsupported_claims = sum(totals), sum(uns)
    responses_with_unsupported = sum(v > 0 for v in uns)

    lines = [
        "# v0.3.1 heldout Mock semantic review",
        "",
        "Frozen 24-item education cohort; actual `/api/tutor/stream` Mock responses. One independent desk reviewer. All 24 responses completed; Mock provider tokens are not applicable and recorded provider-token counters are zero.",
        "",
        f"- Product snapshot: `{report['product_freeze']['snapshot_sha256']}` (freeze manifest verified by runner).",
        f"- Pre-generation seal: `{report['pre_generation_seal']['sha256']}`; fixture SHA-256 `{report['pre_generation_seal']['heldout_sha256']}`; rubric SHA-256 `{report['pre_generation_seal']['rubric_sha256']}`.",
        f"- Review file: `{REVIEW.relative_to(ROOT).as_posix()}`; graded copy: `{GRADED.relative_to(ROOT).as_posix()}`.",
        "",
        "## Category results",
        "",
        "| Category | Correct | n |",
        "|---|---:|---:|",
    ]
    for category in ("concept", "misconception", "formula", "applicability", "units", "numeric", "citation", "followup", "ambiguous", "insufficient", "unsupported", "fabricated"):
        yes, n = category_counts[category]
        lines.append(f"| {category} | {yes} | {n} |")
    lines.extend([
        "",
        "## Cross-cutting results",
        "",
        f"- Clearly answerable set explicit full abstention: {len(full_abstentions)}/16 (`{', '.join(sorted(full_abstentions))}`).",
        f"- Needless clarification on clearly answerable set: {len(needless)}/16 (`{', '.join(sorted(needless)) or 'none'}`).",
        f"- Missed necessary clarification on ambiguous items: {len(missed_clarifications)}/2 (`{', '.join(sorted(missed_clarifications))}`).",
        f"- Unsupported factual/formula/numeric/simulation assertions after excluding generic refusal boilerplate: {unsupported_claims}/{total_claims} claims; responses with at least one such assertion: {responses_with_unsupported}/{len(sheet['samples'])}.",
        f"- Requested citation items: {category_counts['citation'][0]}/{category_counts['citation'][1]} semantic support; automated quote/source trace was {report['arms']['mock']['summary']['metrics']['source_trace']['n']}/{report['arms']['mock']['summary']['metrics']['source_trace']['d']} overall and requested source trace {report['arms']['mock']['summary']['metrics']['requested_source_trace']['n']}/{report['arms']['mock']['summary']['metrics']['requested_source_trace']['d']}.",
        "- Generic abstention text is not counted as a factual claim. Claim totals count distinct answer assertions, formulas, numeric fields, assumptions, and model/simulation-result statements; evidence notes bind each judgment to the response.",
        "",
        "This is a desk review of generated responses, not a classroom outcome or teacher adjudication. The independent second review is maintained separately.",
        "",
    ])
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"review": REVIEW.name, "graded": GRADED.name, "summary": SUMMARY.name,
                      "category_counts": dict(category_counts), "full_abstentions": len(full_abstentions),
                      "needless_clarification": len(needless), "missed_ambiguity_clarification": len(missed_clarifications),
                      "claims": [unsupported_claims, total_claims], "responses_with_unsupported": responses_with_unsupported}, ensure_ascii=False))


if __name__ == "__main__":
    main()
