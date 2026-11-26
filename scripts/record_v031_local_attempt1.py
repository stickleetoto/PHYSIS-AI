"""Preserve the interrupted first heldout Ollama attempt as a package artifact."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT = ROOT / ".superpowers/sdd/v031/local-heldout-three-arm.progress.jsonl"
SEAL = ROOT / "release/education-v031-heldout-seal.json"
FIXTURE = ROOT / "release/education-v031-heldout.jsonl"
RUBRIC = ROOT / "release/education-v031-heldout-rubric.md"
RAW = ROOT / "release/benchmark-v031-local-qwen25-3b-heldout-attempt1-failure-raw.jsonl"
REPORT = ROOT / "release/benchmark-v031-local-qwen25-3b-heldout-attempt1-failure.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    seal = json.loads(SEAL.read_text(encoding="utf-8"))
    checkpoint_bytes = CHECKPOINT.read_bytes()
    rows = [json.loads(line) for line in checkpoint_bytes.decode("utf-8").splitlines() if line.strip()]
    if len(rows) != 5:
        raise RuntimeError(f"Expected the preserved first-attempt checkpoint to have 5 rows, found {len(rows)}")
    if any(row.get("status") != "provider_error" for row in rows):
        raise RuntimeError("The interrupted attempt contains a non-error row; review manually before reporting.")
    calls = [call for row in rows for call in row.get("provider_requests", [])]
    if len(calls) != 5 or any(call.get("input_tokens") is not None or call.get("output_tokens") is not None for call in calls):
        raise RuntimeError("Observed request count or token-coverage check differs from the registered failure summary.")

    # Copy the original checkpoint bytes verbatim for packaging; never reconstruct receipts.
    if RAW.exists() or REPORT.exists():
        raise FileExistsError("Refusing to overwrite an attempt-1 package artifact.")
    RAW.write_bytes(checkpoint_bytes)

    expected_order = []
    ids = seal["local_plan"]["item_ids"]
    arms = seal["local_plan"]["arms"]
    for index, case_id in enumerate(ids):
        shift = index % len(arms)
        expected_order.extend((case_id, arm) for arm in (arms[shift:] + arms[:shift]))
    row_ids = [row.get("case", {}).get("id") for row in rows]
    # The frozen runner's legacy receipt omitted the arm and the saved row order is
    # inconsistent with its expected case-major rotation. Preserve this limitation.
    arm_attribution = "unrecoverable-from-receipt"

    report = {
        "schema_version": 1,
        "status": "interrupted-failed-attempt-preserved",
        "attempt_number": 1,
        "observed_utc": datetime.now(UTC).isoformat(),
        "cohort": "heldout-local-three-arm",
        "pre_generation_seal": {
            "file": SEAL.relative_to(ROOT).as_posix(),
            "sha256": sha(SEAL),
            "fixture_sha256": sha(FIXTURE),
            "rubric_sha256": sha(RUBRIC),
            "registered_model_digest": seal["local_plan"]["model_digest"],
            "registered_items": ids,
            "registered_arms": arms,
        },
        "product_freeze_sha256": seal["product_freeze"]["snapshot_sha256"],
        "previous_runner_sha256_at_freeze": seal["evaluation_script_sha256"]["scripts/independent_v031_fresh.py"],
        "provider": "ollama",
        "endpoint": "http://127.0.0.1:11434",
        "model": "qwen2.5:3b",
        "server_state_during_recovery_check": {
            "pid": 13860,
            "executable": "E:\\Apps\\Ollama\\ollama.exe",
            "loopback_listener": "127.0.0.1:11434",
            "api_version": "0.34.2",
            "loaded_models": [],
            "installed_model_digest": seal["local_plan"]["model_digest"],
        },
        "results": {
            "saved_request_receipts": len(rows),
            "provider_errors": len(rows),
            "successful_responses": 0,
            "token_observed_requests": 0,
            "input_tokens_observed": 0,
            "output_tokens_observed": 0,
            "reported_latency_ms": [call.get("latency_ms") for call in calls],
            "all_errors_reported_as_timeout": all("초과" in str(row.get("error", "")) for row in rows),
            "saved_row_case_counts": dict(Counter(row_ids)),
            "saved_row_case_order": row_ids,
            "arm_attribution": arm_attribution,
            "expected_preregistered_case_order_prefix": [case_id for case_id, _ in expected_order[:len(rows)]],
            "row_order_matches_expected_prefix": row_ids == [case_id for case_id, _ in expected_order[:len(rows)]],
            "interrupted_or_unrecorded_invocation": "No receipt was saved for a call in progress at interruption; no result is inferred or counted.",
        },
        "diagnosis": {
            "cause": "undetermined",
            "evidence": "The loopback API version endpoint responded, the model was installed, and /api/ps reported no loaded model. Previously discovered server logs predate this server process; no current stderr was captured for attempt 1.",
            "raw_receipts_file": RAW.relative_to(ROOT).as_posix(),
            "raw_checkpoint_sha256": sha(RAW),
            "source_checkpoint": CHECKPOINT.relative_to(ROOT).as_posix(),
            "source_checkpoint_sha256": sha(CHECKPOINT),
        },
        "retry_plan": {
            "same_fixture_rubric_items_arms_and_rotation": True,
            "separate_attempt": True,
            "no_prompt_or_selection_changes": True,
        },
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": REPORT.name, "raw": RAW.name, "saved_receipts": len(rows),
                      "errors": len(rows), "token_observed": 0,
                      "case_order_matches_expected_prefix": report["results"]["row_order_matches_expected_prefix"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
