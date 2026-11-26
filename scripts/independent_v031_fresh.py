"""Seal and run the frozen PHYSIS v0.3.1 independent education cohort.

The script has no provider path other than an explicit local Ollama selection.
Mock jobs use the app's /api/tutor/stream endpoint through TestClient.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

# Prevent the app import-time load_dotenv side effect before importing it.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:11434"
os.environ["NO_PROXY"] = "127.0.0.1,localhost"
os.environ["no_proxy"] = "127.0.0.1,localhost"

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
import benchmark_v3 as prior
from benchmark_scoring import REVIEW_BY_CATEGORY, digest, review_sheet, summarize
from independent_v031 import ARMS as LEGACY_ARMS, MODEL, LOCAL_BASE, safety_screen
from physis.api import create_app
from physis.physics import SPECS
from physis.provider_config import ProviderSelection, endpoint

HELDOUT = ROOT / "release" / "education-v031-heldout.jsonl"
RUBRIC = ROOT / "release" / "education-v031-heldout-rubric.md"
SEAL = ROOT / "release" / "education-v031-heldout-seal.json"
SEAL_HASH = ROOT / "release" / "education-v031-heldout-seal.sha256"
FREEZE = ROOT / "release" / "product-freeze-v031.json"
MOCK_OLD_OUT = ROOT / "release" / "benchmark-v031-mock-v0.3-final-72.json"
MOCK_HELDOUT_OUT = ROOT / "release" / "benchmark-v031-mock-heldout-24.json"
LOCAL_HELDOUT_OUT = ROOT / "release" / "benchmark-v031-local-qwen25-3b-heldout-12.json"
LOCAL_HELDOUT_RETRY1_OUT = ROOT / "release" / "benchmark-v031-local-qwen25-3b-heldout-attempt2-retry1.json"
ARMS = ("raw", "retrieval", "retrieval_physics")
LOCAL_IDS = (
    "h-concept-01", "h-misconception-01", "h-formula-01", "h-applicability-01",
    "h-units-01", "h-numeric-01", "h-citation-01", "h-followup-01",
    "h-ambiguous-01", "h-insufficient-01", "h-unsupported-01", "h-fabricated-01",
)
TEMP_EVIDENCE = ROOT / ".superpowers" / "sdd" / "v031"


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_heldout(path: Path = HELDOUT) -> list[dict]:
    references = json.loads((ROOT / "backend/tests/fixtures/benchmark-v3/references.json").read_text(encoding="utf-8"))["sources"]
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(cases) != 24 or len({c.get("id") for c in cases}) != len(cases):
        raise ValueError("Heldout must contain exactly 24 unique records.")
    if len({c.get("question") for c in cases}) != len(cases):
        raise ValueError("Heldout questions must be unique.")
    for case in cases:
        if case.get("category") not in REVIEW_BY_CATEGORY or case.get("model") not in SPECS or not case.get("basis"):
            raise ValueError(f"Invalid heldout case metadata: {case.get('id')}")
        if case.get("reference") not in references:
            raise ValueError(f"Unknown reference key: {case.get('id')}")
        patch = case.get("patch", {})
        variables = {v.key: v for v in SPECS[case["model"]].variables}
        changed = patch.get("values", {})
        if set(changed) - variables.keys():
            raise ValueError(f"Unknown experiment variable in {case.get('id')}.")
        if any(not variables[k].min <= value <= variables[k].max for k, value in changed.items()):
            raise ValueError(f"Experiment patch is outside registered bounds in {case.get('id')}.")
        if "number" in case and (len(case["number"]) != 4 or case["number"][3] == ""):
            raise ValueError(f"Invalid numeric target metadata in {case.get('id')}.")
        case["reference_url"] = references[case["reference"]]
        safety_screen(case)
    counts = {category: sum(c["category"] == category for c in cases) for category in REVIEW_BY_CATEGORY}
    if any(counts[k] != 2 for k in REVIEW_BY_CATEGORY):
        raise ValueError(f"Expected two cases per scoring category, got {counts}.")
    if not set(LOCAL_IDS) <= {c["id"] for c in cases}:
        raise ValueError("The predeclared local subset does not match heldout IDs.")
    return cases


def verify_product_freeze() -> dict:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    actual_manifest_hash = file_sha(FREEZE)
    files = freeze.get("files")
    if not isinstance(files, dict) or len(files) != 157:
        raise RuntimeError("Product freeze manifest file count is unexpected.")
    mismatches = []
    for relative, expected in files.items():
        path = ROOT / Path(relative)
        if not path.is_file() or file_sha(path) != expected:
            mismatches.append(relative)
    if mismatches:
        raise RuntimeError("Product freeze verification failed: " + ", ".join(mismatches[:8]))
    expected_snapshot = "86a18410440acb8f5f83d6afeb78bfc9504241d67d745c7a681b99a17b35edb2"
    if freeze.get("sha256") != expected_snapshot:
        raise RuntimeError("The freeze fingerprint differs from the parent-declared snapshot.")
    return {"snapshot_sha256": freeze["sha256"], "manifest_file_sha256": actual_manifest_hash,
            "recorded_utc": freeze.get("recorded_utc"), "file_count": len(files), "verified_files": len(files)}


def seal() -> dict:
    cases = load_heldout()
    old = prior.dataset("final")
    old_questions = {c["question"] for c in old}
    duplicated = [c["id"] for c in cases if c["question"] in old_questions]
    if duplicated:
        raise RuntimeError("Heldout contains exact prior final-set duplicates: " + ", ".join(duplicated))
    freeze_state = verify_product_freeze()
    sources = ROOT / "backend/tests/fixtures/benchmark-v3/references.json"
    script_paths = [ROOT / "scripts" / name for name in (
        "benchmark_v3.py", "benchmark_scoring.py", "independent_v031.py", "independent_v031_combine.py",
        "independent_v031_fresh.py")]
    manifest = {
        "schema_version": 1,
        "sealed_utc": datetime.now(UTC).isoformat(),
        "status": "sealed-before-generation",
        "heldout_file": HELDOUT.relative_to(ROOT).as_posix(),
        "heldout_sha256": file_sha(HELDOUT),
        "heldout_canonical_sha256": digest(cases),
        "heldout_count": len(cases),
        "category_counts": {k: sum(c["category"] == k for c in cases) for k in REVIEW_BY_CATEGORY},
        "heldout_ids": [c["id"] for c in cases],
        "rubric_file": RUBRIC.relative_to(ROOT).as_posix(),
        "rubric_sha256": file_sha(RUBRIC),
        "reference_map_sha256": file_sha(sources),
        "prior_v0_3_final_fixture_sha256": file_sha(ROOT / "backend/tests/fixtures/benchmark-v3/final.jsonl"),
        "product_freeze": freeze_state,
        "mock_plan": {"regression": "all 72 existing v0.3 final items", "heldout": "all 24 sealed items", "provider": "mock/local-rules", "endpoint": "in-process TestClient POST /api/tutor/stream", "answer_keys_or_basis_sent": False},
        "local_plan": {"provider": "ollama", "model": MODEL, "model_digest": "357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b", "endpoint": LOCAL_BASE, "arms": list(ARMS), "item_ids": list(LOCAL_IDS), "items_per_arm": len(LOCAL_IDS), "one_item_per_category": True, "rotation": "arm order rotated by case index", "answer_keys_or_basis_sent": False},
        "safety_screen": {"method": "fixed allowlist, lexical weapons/cyber/operational-biology screen applied to question, prior turn, and basis before any generation", "checked_heldout": len(cases), "matches": 0, "rejected": 0},
        "evaluation_script_sha256": {p.relative_to(ROOT).as_posix(): file_sha(p) for p in script_paths},
    }
    if SEAL.exists() or SEAL_HASH.exists():
        raise FileExistsError("A seal already exists; refusing to replace frozen evidence.")
    SEAL.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SEAL_HASH.write_text(f"{file_sha(SEAL)}  {SEAL.name}\n", encoding="ascii")
    print(json.dumps({"heldout_count": len(cases), "category_counts": manifest["category_counts"],
                      "heldout_sha256": manifest["heldout_sha256"], "rubric_sha256": manifest["rubric_sha256"],
                      "seal_sha256": file_sha(SEAL), "product_snapshot_sha256": freeze_state["snapshot_sha256"]}, ensure_ascii=False))
    return manifest


def checkpoint_path(name: str) -> Path:
    TEMP_EVIDENCE.mkdir(parents=True, exist_ok=True)
    return TEMP_EVIDENCE / f"{name}.progress.jsonl"


def write_jsonl_checkpoint(path: Path, rows: list[dict]) -> None:
    data = "".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in rows)
    path.write_text(data, encoding="utf-8")


def code_hashes() -> dict:
    names = ("benchmark_v3.py", "benchmark_scoring.py", "independent_v031.py", "independent_v031_fresh.py")
    files = [ROOT / "scripts" / n for n in names]
    files.extend(sorted((ROOT / "backend" / "physis").glob("*.py")))
    return {p.relative_to(ROOT).as_posix(): file_sha(p) for p in files}


def create_common_report(name: str, fixture_path: Path, cases: list[dict]) -> dict:
    seal_manifest = json.loads(SEAL.read_text(encoding="utf-8"))
    if file_sha(HELDOUT) != seal_manifest["heldout_sha256"] or file_sha(RUBRIC) != seal_manifest["rubric_sha256"]:
        raise RuntimeError("Sealed heldout or rubric changed after registration.")
    freeze = verify_product_freeze()
    return {
        "schema_version": 1,
        "run_id": uuid4().hex,
        "started_utc": datetime.now(UTC).isoformat(),
        "cohort": name,
        "pre_generation_seal": {"file": SEAL.relative_to(ROOT).as_posix(), "sha256": file_sha(SEAL),
                                "heldout_sha256": seal_manifest["heldout_sha256"], "rubric_sha256": seal_manifest["rubric_sha256"]},
        "product_freeze": freeze,
        "fixture_file": fixture_path.relative_to(ROOT).as_posix(),
        "fixture_sha256": file_sha(fixture_path),
        "canonical_split_sha256": digest(cases),
        "selected_ids": [c["id"] for c in cases],
        "case_count": len(cases),
        "answer_keys_or_basis_sent_to_model": False,
        "code_sha256": code_hashes(),
    }


def finalize_arm(rows: list[dict]) -> dict:
    summary = summarize(rows)
    calls = [c for row in rows for c in row.get("provider_requests", [])]
    observed = [c for c in calls if type(c.get("input_tokens")) is int and type(c.get("output_tokens")) is int]
    call_latencies = [c["latency_ms"] for c in calls if type(c.get("latency_ms")) is int]
    summary.update({
        "provider_request_count": len(calls),
        "token_observed_request_count": len(observed),
        "input_tokens": sum(c["input_tokens"] for c in observed),
        "output_tokens": sum(c["output_tokens"] for c in observed),
        "total_tokens": sum(c["input_tokens"] + c["output_tokens"] for c in observed),
        "median_provider_request_ms": round(statistics.median(call_latencies), 2) if call_latencies else None,
    })
    return summary


def run_mock(cohort: str) -> dict:
    if cohort == "v0.3-final":
        cases = prior.dataset("final")
        fixture = ROOT / "backend/tests/fixtures/benchmark-v3/final.jsonl"
        out = MOCK_OLD_OUT
        count_expected = 72
    elif cohort == "heldout":
        cases = load_heldout()
        fixture = HELDOUT
        out = MOCK_HELDOUT_OUT
        count_expected = 24
    else:
        raise ValueError(cohort)
    for case in cases:
        safety_screen(case)
    report = create_common_report(cohort, fixture, cases)
    report["provider"] = "mock"
    report["model"] = "local-rules"
    report["execution_path"] = "POST /api/tutor/stream through TestClient"
    report["arms"] = {"mock": {"provider": "mock", "model": "local-rules", "rows": []}}
    checkpoint = checkpoint_path("mock-" + cohort.replace(".", "-"))
    if checkpoint.exists():
        raise FileExistsError(f"Progress checkpoint already exists: {checkpoint}")
    with ExitStack() as stack:
        temp = Path(stack.enter_context(TemporaryDirectory(prefix="physis-v031-mock-")))
        app = create_app(temp / "experiments.sqlite3")
        client = stack.enter_context(TestClient(app))
        store = app.state.knowledge
        report["knowledge_index"] = store.stats()
        rows = report["arms"]["mock"]["rows"]
        for i, case in enumerate(cases, 1):
            row = prior.sample(client, store, case, "mock", None, rates=None)
            rows.append(row)
            write_jsonl_checkpoint(checkpoint, rows)
            print(f"mock {cohort} {i}/{count_expected} {case['id']} {row['status']}", flush=True)
    if len(report["arms"]["mock"]["rows"]) != count_expected:
        raise RuntimeError("Mock report row count does not match the cohort.")
    report["arms"]["mock"]["status"] = "measured"
    report["arms"]["mock"]["summary"] = finalize_arm(report["arms"]["mock"]["rows"])
    report["finished_utc"] = datetime.now(UTC).isoformat()
    report["arms"]["mock"]["review_template"] = out.with_name(out.stem + "-review.json").name
    if out.exists():
        raise FileExistsError(f"Output already exists: {out}")
    prior.write_json(out, report)
    review_path = out.with_name(out.stem + "-review.json")
    prior.write_json(review_path, {"run_id": report["run_id"], "reviewer": "", "samples": review_sheet(report)})
    print(f"saved {out.name} {len(report['arms']['mock']['rows'])} rows")
    return report


def ollama_manifest() -> dict:
    os.environ["OLLAMA_BASE_URL"] = LOCAL_BASE
    base, headers = endpoint("ollama")
    if base != LOCAL_BASE or any(k.lower() in {"authorization", "x-api-key"} for k in headers):
        raise RuntimeError("Refusing non-loopback or authenticated Ollama endpoint.")
    with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
        response = client.get(f"{LOCAL_BASE}/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
    found = next((m for m in models if m.get("name") == MODEL), None)
    if not found or found.get("digest") != "357c53fb659c5076de1d65ccb0b397446227b71a42be9d1603d46168015c9e4b":
        raise RuntimeError("Installed Ollama model is missing or its digest changed; no model will be downloaded.")
    return found


def machine_facts() -> dict:
    facts = {"platform": platform.platform(), "python": platform.python_version(), "processor": platform.processor(), "logical_cpus": os.cpu_count()}
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
                                check=True, capture_output=True, text=True, timeout=5, shell=False)
        facts["gpu"] = result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        facts["gpu"] = None
    return facts


def run_local_heldout(attempt: str = "initial") -> dict:
    cases_by_id = {c["id"]: c for c in load_heldout()}
    cases = [cases_by_id[item_id] for item_id in LOCAL_IDS]
    models = ollama_manifest()
    report = create_common_report("heldout-local-three-arm", HELDOUT, cases)
    report.update({"provider": "ollama", "model": MODEL, "endpoint": LOCAL_BASE,
                   "model_manifest": {k: models.get(k) for k in ("name", "digest", "size", "details")},
                   "machine": machine_facts(), "predeclared_subset_ids": list(LOCAL_IDS),
                   "arms": {arm: {"rows": []} for arm in ARMS}})
    selection = ProviderSelection(provider="ollama", model=MODEL)
    if attempt == "initial":
        checkpoint = checkpoint_path("local-heldout-three-arm")
        out = LOCAL_HELDOUT_OUT
    elif attempt == "retry1":
        checkpoint = checkpoint_path("local-heldout-three-arm-retry1")
        out = LOCAL_HELDOUT_RETRY1_OUT
        report["retry_context"] = {
            "attempt_number": 2,
            "previous_attempt_record": "release/benchmark-v031-local-qwen25-3b-heldout-attempt1-failure.json",
            "previous_attempt_checkpoint": ".superpowers/sdd/v031/local-heldout-three-arm.progress.jsonl",
            "same_predeclared_items_arms_and_rotation": True,
            "fixture_and_rubric_unchanged": True,
        }
    else:
        raise ValueError(f"Unknown attempt: {attempt}")
    if checkpoint.exists():
        raise FileExistsError(f"Progress checkpoint already exists: {checkpoint}")
    with ExitStack() as stack:
        temp = Path(stack.enter_context(TemporaryDirectory(prefix="physis-v031-local-")))
        app = create_app(temp / "experiments.sqlite3")
        client = stack.enter_context(TestClient(app))
        store = app.state.knowledge
        report["knowledge_index"] = store.stats()
        for index, case in enumerate(cases):
            shift = index % len(ARMS)
            order = ARMS[shift:] + ARMS[:shift]
            for arm in order:
                base, _ = endpoint("ollama")
                if base != LOCAL_BASE:
                    raise RuntimeError("Local Ollama destination changed; stopping before generation.")
                row = prior.sample(client, store, case, arm, selection, rates=None)
                # Persist the condition explicitly in the raw receipt; the legacy
                # sample schema did not carry arm identity in the row itself.
                row["evaluation_arm"] = arm
                row["case_order_index"] = index + 1
                row["condition_position"] = order.index(arm) + 1
                report["arms"][arm]["rows"].append(row)
                all_rows = [r for block in report["arms"].values() for r in block["rows"]]
                write_jsonl_checkpoint(checkpoint, all_rows)
                print(f"local {case['id']} / {arm}: {row['status']}", flush=True)
    for arm in ARMS:
        block = report["arms"][arm]
        block["status"] = "measured" if any(r["status"] == "ok" for r in block["rows"]) else "no_responses"
        block["summary"] = finalize_arm(block["rows"])
    report["finished_utc"] = datetime.now(UTC).isoformat()
    if out.exists():
        raise FileExistsError(f"Output already exists: {out}")
    prior.write_json(out, report)
    review_path = out.with_name(out.stem + "-review.json")
    prior.write_json(review_path, {"run_id": report["run_id"], "reviewer": "", "samples": review_sheet(report)})
    print(f"saved {out.name} selected={len(LOCAL_IDS)} per arm")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["seal", "mock-final", "mock-heldout", "local-heldout", "local-heldout-retry1"])
    args = parser.parse_args()
    if args.action.startswith("local-"):
        parser.error("이 버전의 실모델 평가는 scripts/evaluation_v032.py에서 명시적으로 실행하세요.")
    if args.action == "seal":
        seal()
    elif args.action == "mock-final":
        run_mock("v0.3-final")
    elif args.action == "mock-heldout":
        run_mock("heldout")
    elif args.action == "local-heldout":
        run_local_heldout()
    else:
        run_local_heldout("retry1")


if __name__ == "__main__":
    main()
