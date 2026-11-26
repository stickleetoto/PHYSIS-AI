"""Run a stand-alone, manually labeled control set for claim/evidence alignment.

These deterministic controls are separate from the education cards, education
held-out data, and all prior turn-level tutor regression outcomes. They measure
the local relation classifier against a small authored set; they are not a
blind or independently graded semantic-accuracy estimate.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from physis.alignment import STATES, align_claim, split_claims
from physis.knowledge import KnowledgeStore


CONTROL_SET = [
    {
        "id": "direct-freefall-source-sentence",
        "kind": "corpus-exact",
        "source_ids": ["college-m42102:import-auto-id2006874"],
        "claim_source": "exact source passage, loaded at run time",
        "expected": "direct",
        "rationale": "A complete verified source sentence should be directly supported.",
    },
    {
        "id": "freefall-ignored-drag-paraphrase",
        "kind": "unseen-paraphrase-control",
        "source_ids": ["college-m42102:import-auto-id2006874"],
        "claim": "When drag can be ignored, objects with different masses accelerate downward at the same rate in one place.",
        "expected": "partial",
        "rationale": "Restates mass-independent acceleration and preserves the source's drag/location conditions.",
    },
    {
        "id": "freefall-opposite-relation-under-condition",
        "kind": "contradiction-control",
        "source_ids": ["college-m42102:import-auto-id2006874"],
        "claim": "In a vacuum, the heavier object falls with greater acceleration than the lighter one.",
        "expected": "contradiction",
        "rationale": "The stated vacuum condition is compatible with negligible drag, while the acceleration relation is opposite.",
    },
    {
        "id": "freefall-unverified-drag-scope",
        "kind": "scope-control",
        "source_ids": ["college-m42102:import-auto-id2006874"],
        "claim": "When air resistance is significant, objects of unequal mass still share the same falling acceleration.",
        "expected": "undecidable",
        "rationale": "The source restricts its claim to negligible drag and does not settle significant-drag behavior.",
    },
    {
        "id": "freefall-topically-related-color",
        "kind": "related-only-control",
        "source_ids": ["college-m42102:import-auto-id2006874"],
        "claim": "Mass changes the color of a falling body.",
        "expected": "related",
        "rationale": "The topic overlaps, but the source says nothing about color.",
    },
    {
        "id": "freefall-unrelated-granite",
        "kind": "insufficient-control",
        "source_ids": ["college-m42102:import-auto-id2006874"],
        "claim": "Granite forms under cooling magma.",
        "expected": "insufficient",
        "rationale": "The verified passage provides no relevant information for this claim.",
    },
    {
        "id": "newton-force-acceleration-paraphrase",
        "kind": "unseen-paraphrase-control",
        "source_ids": ["college-m42073:import-auto-id1355832"],
        "claim": "More net force produces greater acceleration in the system.",
        "expected": "partial",
        "rationale": "Restates the positive force/acceleration relation from the verified Newton passage.",
    },
    {
        "id": "newton-inverse-force-contradiction",
        "kind": "contradiction-control",
        "source_ids": ["college-m42073:import-auto-id1355832"],
        "claim": "Acceleration is inversely proportional to net force.",
        "expected": "contradiction",
        "rationale": "The source states direct proportionality to net external force.",
    },
    {
        "id": "newton-relation-unspecified",
        "kind": "undecidable-control",
        "source_ids": ["college-m42073:import-auto-id1355832"],
        "claim": "Acceleration depends on net force and mass.",
        "expected": "undecidable",
        "rationale": "The terms are present but the direction or form of the relation is not stated.",
    },
    {
        "id": "pendulum-small-angle-paraphrase",
        "kind": "unseen-paraphrase-control",
        "source_ids": ["college-m42243:import-auto-id2672250"],
        "claim": "At small angles, a pendulum's restoring force grows in proportion to displacement.",
        "expected": "partial",
        "rationale": "Restates the supported small-angle restoring-force relation.",
    },
    {
        "id": "pendulum-large-angle-scope",
        "kind": "scope-control",
        "source_ids": ["college-m42243:import-auto-id2672250"],
        "claim": "For large angles, a pendulum's restoring force is proportional to displacement.",
        "expected": "undecidable",
        "rationale": "The source limits this approximation to angles below about 15 degrees.",
    },
    {
        "id": "pendulum-square-relation-contradiction",
        "kind": "contradiction-control",
        "source_ids": ["college-m42243:import-auto-id2672250"],
        "claim": "A pendulum's restoring force is proportional to the square of displacement.",
        "expected": "contradiction",
        "rationale": "The source's small-angle relation is linear in displacement, not quadratic.",
    },
    {
        "id": "velocity-vector-paraphrase",
        "kind": "unseen-paraphrase-control",
        "source_ids": ["college-m42100:import-auto-id3526102"],
        "claim": "Velocity includes a direction as well as a magnitude.",
        "expected": "partial",
        "rationale": "Restates both defining vector attributes in the verified source.",
    },
    {
        "id": "velocity-scalar-contradiction",
        "kind": "contradiction-control",
        "source_ids": ["college-m42100:import-auto-id3526102"],
        "claim": "Velocity is a scalar with only magnitude; direction is irrelevant.",
        "expected": "contradiction",
        "rationale": "The source explicitly states that velocity has both magnitude and direction.",
    },
    {
        "id": "momentum-product-paraphrase",
        "kind": "unseen-paraphrase-control",
        "source_ids": ["college-m42156:import-auto-id1120695"],
        "claim": "Momentum is mass times velocity.",
        "expected": "partial",
        "rationale": "Restates the source definition of momentum as the product of mass and velocity.",
    },
    {
        "id": "density-ratio-paraphrase",
        "kind": "unseen-paraphrase-control",
        "source_ids": ["college-m42187:import-auto-id3217118"],
        "claim": "Density is the amount of mass per unit volume.",
        "expected": "partial",
        "rationale": "Restates the verified mass-per-unit-volume definition.",
    },
    {
        "id": "average-velocity-paraphrase",
        "kind": "unseen-paraphrase-control",
        "source_ids": ["college-m42096:import-auto-id3538220"],
        "claim": "Average velocity is displacement divided by elapsed time.",
        "expected": "partial",
        "rationale": "Restates the verified displacement-over-time definition.",
    },
    {
        "id": "conflicting-verified-row-control",
        "kind": "synthetic-conflict-stress-control",
        "source_ids": ["college-m42102:import-auto-id2006874"],
        "claim_source": "exact source passage, loaded at run time",
        "expected": "undecidable",
        "rationale": "A synthetic opposing statement is paired with the real verified passage; the conflict should prevent certification.",
    },
    {
        "id": "signed-quantity-control",
        "kind": "synthetic-normalization-control",
        "source_ids": ["synthetic-numeric-control"],
        "claim": "The acceleration is +4 m/s².",
        "expected": "related",
        "rationale": "The shared quantity terms make this related-only, but the plus sign must not normalize to the negative source value or earn direct support.",
        "synthetic_quote": "The acceleration is −4 m/s².",
    },
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluate() -> dict:
    with TemporaryDirectory() as directory:
        store = KnowledgeStore(Path(directory) / "knowledge.sqlite3")
        store.initialize()
        corpus_sha = store.stats()["corpus_sha256"]

        cases = []
        for control in CONTROL_SET:
            passages = []
            for source_id in control["source_ids"]:
                if source_id == "synthetic-numeric-control":
                    passages.append({"id": source_id, "status": "source_verified", "quote": control["synthetic_quote"]})
                    continue
                row = store.chunk(source_id)
                if not row or not row.get("citable") or not row.get("text"):
                    raise RuntimeError(f"Expected verified citable corpus passage missing: {source_id}")
                passages.append({"id": source_id, "status": "source_verified", "quote": row["text"]})

            if control["id"] == "conflicting-verified-row-control":
                passages.append({
                    "id": control["source_ids"][0],
                    "status": "source_verified",
                    "quote": "When air resistance is negligible, the heavier object has greater acceleration than the lighter object as they fall.",
                })
            claim = split_claims(passages[0]["quote"])[0] if control.get("claim_source") else control["claim"]
            result = align_claim(claim, passages)
            cases.append({
                "id": control["id"],
                "kind": control["kind"],
                "claim": claim,
                "source_ids": control["source_ids"],
                "expected": control["expected"],
                "observed": result["state"],
                "matched": result["state"] == control["expected"],
                "rationale": control["rationale"],
                "observed_reason": result["reason"],
                "observed_references": result["references"],
            })

        confusion = {expected: {observed: 0 for observed in STATES} for expected in STATES}
        by_label = defaultdict(Counter)
        by_kind = defaultdict(Counter)
        for row in cases:
            confusion[row["expected"]][row["observed"]] += 1
            by_label[row["expected"]]["total"] += 1
            by_label[row["expected"]]["matched"] += int(row["matched"])
            by_kind[row["kind"]]["total"] += 1
            by_kind[row["kind"]]["matched"] += int(row["matched"])

        matched = sum(row["matched"] for row in cases)
        return {
            "schema_version": 1,
            "evaluation": "PHYSIS v0.3.1 claim-evidence alignment deterministic controls",
            "evaluated_utc": datetime.now(UTC).isoformat(),
            "scope": {
                "method": "Direct execution of physis.alignment.align_claim against actual bundled corpus passages plus explicitly labeled synthetic stress controls.",
                "labels": "Expected relations were manually assigned from the cited source text before running this script; labels were not blinded or independently graded.",
                "independence": "Control claims are authored in this script and do not import education cards, education held-out fixtures, or prior 72-turn regression outcomes.",
                "limits": [
                    "This small deterministic control set is not an estimate of open-domain semantic accuracy.",
                    "Most controls exercise curated relation patterns; unseen paraphrase coverage is bounded to the listed claims.",
                    "Synthetic controls test conflict aggregation and sign normalization, not citation authenticity.",
                    "No language model, network request, or provider inference was used.",
                ],
            },
            "inputs": {
                "corpus_sha256": corpus_sha,
                "alignment_module_sha256": sha256(ROOT / "backend" / "physis" / "alignment.py"),
                "control_script_sha256": sha256(Path(__file__)),
                "case_count": len(cases),
            },
            "summary": {
                "matched": matched,
                "total": len(cases),
                "accuracy_on_this_control_set": round(matched / len(cases), 4) if cases else None,
                "by_expected_label": {key: dict(value) for key, value in sorted(by_label.items())},
                "by_control_kind": {key: dict(value) for key, value in sorted(by_kind.items())},
                "confusion_matrix": confusion,
            },
            "cases": cases,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "release" / "alignment-v0.3.1.json")
    args = parser.parse_args()
    result = evaluate()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0 if result["summary"]["matched"] == result["summary"]["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
