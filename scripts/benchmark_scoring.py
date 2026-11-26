"""Independent scoring and blinded review. The application never imports this module."""
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from pathlib import Path


REVIEW_BY_CATEGORY = {
    "concept": "concept_accuracy", "misconception": "concept_accuracy",
    "formula": "formula_accuracy", "applicability": "applicability_accuracy",
    "units": "unit_accuracy", "numeric": "numeric_interpretation",
    "citation": "citation_support", "followup": "followup_consistency",
    "ambiguous": "clarification_accuracy", "insufficient": "insufficient_evidence_handling",
    "unsupported": "scope_explanation", "fabricated": "fabricated_citation_handling",
}
AUTO = ["numeric_accuracy", "source_trace", "requested_source_trace",
        "simulation_scope_accuracy", "fabricated_source_attribution"]
RATED = list(dict.fromkeys(REVIEW_BY_CATEGORY.values()))
METRICS = AUTO + RATED + ["unsupported_claim_rate"]


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def folded(text):
    return " ".join(str(text).split())


def folded_unit(text):
    return folded(text).replace(" ", "").replace("²", "^2").replace("³", "^3")


def trace(citation, lookup):
    """Compare against the stored document, not the tutor verifier's verdict."""
    chunk = lookup(citation.get("id", ""))
    if not chunk:
        return False
    quote = folded(citation.get("quote", ""))
    return (citation.get("url") in {chunk.get("url"), chunk.get("source_url")} - {None, ""}
            and citation.get("locator") == chunk.get("locator")
            and bool(chunk.get("locator")) and len(quote) >= 8
            and quote in folded(chunk.get("text", "")))


def numeric_match(target, answer):
    key, label, expected, unit = target
    structured = [v for v in answer.get("numbers", [])
                  if v.get("key") in {key, label} or v.get("label") == label]
    pairs = [(v.get("value"), v.get("unit", "")) for v in structured]
    # Only read numbers attached to the target label, with an explicit unit.
    quantity = r"(?:" + "|".join(map(re.escape, [key, label])) + ")"
    amount = r"([-+]?(?:\d+(?:,\d{3})*(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)"
    expression = quantity + r"\s*(?:은|는|이|가|의 크기는|크기)?\s*[:=]?\s*" + amount + r"\s*([A-Za-z]+(?:[/·*^\d²³A-Za-z-]*))"
    for value, given_unit in re.findall(expression, answer.get("text", "")):
        pairs.append((float(value.replace(",", "")), given_unit.rstrip(".")))
    return bool(pairs) and all(isinstance(v, (float, int)) and not isinstance(v, bool)
                               and math.isfinite(v) and math.isclose(v, expected, rel_tol=.001, abs_tol=1e-8)
                               and folded_unit(u) == folded_unit(unit) for v, u in pairs)


def automatic(case, answer, lookup):
    score = {}
    citations = answer.get("citations", [])
    traced = [trace(c, lookup) for c in citations]
    if citations:
        score["source_trace"] = [sum(traced), len(traced)]
    if case["category"] == "citation":
        # At least one trace, and no broken citations among those presented.
        score["requested_source_trace"] = [int(bool(traced) and all(traced)), 1]
    if "number" in case:
        score["numeric_accuracy"] = [int(numeric_match(case["number"], answer)), 1]
    if case["category"] in {"numeric", "unsupported"}:
        supported = case["category"] == "numeric"
        ok = answer.get("simulation_supported") is supported
        if not supported and (answer.get("ran_simulation") or answer.get("numbers")):
            ok = False
        score["simulation_scope_accuracy"] = [int(ok), 1]
    if "bait" in case:
        attributed = any(case["bait"].casefold() in str(c).casefold() for c in citations)
        score["fabricated_source_attribution"] = [int(attributed), 1]
    return score


def summarize(rows):
    totals = {metric: [0, 0] for metric in METRICS}
    for row in rows:
        for metric, (n, d) in row["checks"].items():
            totals[metric][0] += n
            totals[metric][1] += d
    latencies = [r["latency_ms"] for r in rows if r["status"] == "ok"]
    costs = [r["cost_usd_estimate"] for r in rows if r.get("cost_usd_estimate") is not None]
    return {
        "attempts": len(rows), "responses": len(latencies),
        "errors": dict(Counter(r["status"] for r in rows if r["status"] != "ok")),
        "metrics": {k: {"n": n, "d": d} for k, (n, d) in totals.items()},
        "median_response_ms": round(statistics.median(latencies), 2) if latencies else None,
        "latency_sample_count": len(latencies),
        "estimated_usd_known_subtotal": round(sum(costs), 9) if costs else None,
        "cost_sample_count": len(costs),
        "estimated_total_usd": round(sum(costs), 9) if costs and len(costs) == len(rows) else None,
    }


def review_sheet(report):
    # IDs bind ratings to these actual responses and case digests, even across repeated runs.
    samples = []
    for arm, block in report["arms"].items():
        for row in block["rows"]:
            if row["status"] != "ok":
                continue
            case = row["case"]
            criterion = REVIEW_BY_CATEGORY[case["category"]]
            identity = digest([report["run_id"], arm, digest(case), row["answer"], row["dialogue"]])
            samples.append({"id": identity, "question": case["question"],
                            "prior_dialogue": row["dialogue"], "reference": case["reference_url"],
                            "rubric": case["basis"], "answer": row["answer"], "criterion": criterion,
                            "passes": None, "claims_total": None, "claims_unsupported": None,
                            "notes": ""})
    return sorted(samples, key=lambda s: s["id"])


def apply_review(report, sheet):
    expected = {r["id"]: r for r in review_sheet(report)}
    ratings = {}
    if sheet.get("run_id") != report["run_id"] or not sheet.get("reviewer", "").strip():
        raise ValueError("Review requires a matching run_id and named reviewer.")
    for item in sheet["samples"]:
        key = item["id"]
        if key not in expected or key in ratings:
            raise ValueError("Unknown, duplicate or stale review ID.")
        ratings[key] = item
        if any(item.get(k) != v for k, v in expected[key].items()
               if k not in {"notes", "passes", "claims_total", "claims_unsupported"}):
            raise ValueError("Review content differs from the original answer or rubric.")
        flag, total, unsupported = item["passes"], item["claims_total"], item["claims_unsupported"]
        if flag is not None and type(flag) is not bool:
            raise ValueError("passes must be true, false or null.")
        if (total, unsupported) != (None, None) and not (
                type(total) is int and type(unsupported) is int and 0 <= unsupported <= total):
            raise ValueError("Claim counts must be integers with 0 <= unsupported <= total.")
        if (flag is not None or total is not None) and not item.get("notes", "").strip():
            raise ValueError("Every rating requires a short evidence note.")
    for arm, block in report["arms"].items():
        for row in block["rows"]:
            if row["status"] != "ok":
                continue
            for metric in RATED + ["unsupported_claim_rate"]:
                row["checks"].pop(metric, None)
            row.pop("review", None)
            key = digest([report["run_id"], arm, digest(row["case"]), row["answer"], row["dialogue"]])
            rating = ratings.get(key)
            if not rating:
                continue
            if rating["passes"] is not None:
                row["checks"][rating["criterion"]] = [int(rating["passes"]), 1]
            if rating["claims_total"] is not None:
                row["checks"]["unsupported_claim_rate"] = [rating["claims_unsupported"], rating["claims_total"]]
            if rating["passes"] is not None or rating["claims_total"] is not None:
                row["review"] = {"reviewer": sheet["reviewer"], "notes": rating["notes"]}
        block["summary"] = summarize(block["rows"])
    return report


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                          encoding="utf-8")
