"""Independent, local-only educational evaluation helper for PHYSIS v0.3.1.

It runs a fixed, safety-screened subset of the existing v0.3 final regression set
through the application's actual Ollama adapter in three matched conditions.
It never pulls a model and never reads credentials or a .env file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import statistics
import subprocess
import sys
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

# Set these before importing the app: backend/physis/api.py otherwise calls
# load_dotenv at import time. This process never reads the project .env file.
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
from physis.api import create_app
from physis.provider_config import ProviderSelection, endpoint

MODEL = "qwen2.5:3b"
LOCAL_BASE = "http://127.0.0.1:11434"
ARMS = ("raw", "retrieval", "retrieval_physics")
SUBSET_IDS = (
    "f-concept-3", "f-numeric-3", "f-ambiguous-3", "f-insufficient-3",
    "f-citation-3", "f-fabricated-3", "f-unsupported-3", "f-followup-3",
    "f-applicability-3", "f-units-3",
)

# Keep the allowlist strictly educational. A match aborts the run before any
# provider request, even though the selected provider is local-only. This is a
# conservative lexical screen, not a semantic safety classifier.
UNSAFE_PROMPT = re.compile(
    r"(?i)\b(?:weapon|firearm|gun|cannon|bullet|missile|bomb|explos(?:ive|ion)|"
    r"shoot(?:ing)?|warhead|ransomware|malware|phishing|credential theft|password theft|"
    r"keylogger|shellcode|exploit(?:ation)?|unauthorized access|privilege escalation|"
    r"data exfiltration|ddos|botnet|pathogen|biological weapon|gain[- ]of[- ]function|"
    r"increase transmissibility|toxin production|virus engineering|pathogen culture)\b|"
    r"무기|총기|총알|포탄|탄도|폭탄|폭발|사격|조준|탄환|총을|총으로|발사체|미사일|"
    r"랜섬웨어|악성코드|피싱|계정 탈취|비밀번호 탈취|키로거|쉘코드|취약점 악용|"
    r"무단 접근|권한 상승|정보 탈취|분산 서비스 거부|봇넷|병원체|생물무기|"
    r"기능 획득|전염력 증대|감염성 증대|독소 생산|병원체 배양|바이러스 조작"
)


def safety_screen(case: dict) -> None:
    material = "\n".join(str(case.get(k, "")) for k in ("question", "prior", "basis"))
    if UNSAFE_PROMPT.search(material):
        raise RuntimeError(f"Safety screen rejected evaluation item {case.get('id')} before generation.")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_models() -> dict:
    # Pin the only destination in-process; no .env or remote provider config is used.
    os.environ["OLLAMA_BASE_URL"] = LOCAL_BASE
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    os.environ["no_proxy"] = "127.0.0.1,localhost"
    os.environ.pop("PHYSIS_OFFLINE", None)
    base, headers = endpoint("ollama")
    if base != LOCAL_BASE or any(k.lower() in {"authorization", "x-api-key"} for k in headers):
        raise RuntimeError("Ollama endpoint is not the expected unauthenticated loopback URL.")
    with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
        response = client.get(f"{LOCAL_BASE}/api/tags")
        response.raise_for_status()
        models = response.json().get("models", [])
    by_name = {m.get("name"): m for m in models}
    if MODEL not in by_name:
        raise RuntimeError(f"{MODEL} is not installed locally; refusing to download a model.")
    return by_name


def machine_facts() -> dict:
    facts = {"platform": platform.platform(), "python": platform.python_version(),
             "processor": platform.processor(), "logical_cpus": os.cpu_count()}
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            check=True, capture_output=True, text=True, timeout=5, shell=False,
        )
        facts["gpu"] = result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        facts["gpu"] = None
    return facts


def arm_summary(rows: list[dict]) -> dict:
    calls = [call for row in rows for call in row.get("provider_requests", [])]
    observed = [c for c in calls if type(c.get("input_tokens")) is int and type(c.get("output_tokens")) is int]
    request_latencies = [c["latency_ms"] for c in calls if type(c.get("latency_ms")) is int]
    turn_latencies = [r["latency_ms"] for r in rows if r.get("status") == "ok"]
    dialogue_latencies = [r["dialogue_elapsed_ms"] for r in rows if type(r.get("dialogue_elapsed_ms")) is int]
    total_in = sum(c["input_tokens"] for c in observed)
    total_out = sum(c["output_tokens"] for c in observed)
    return {
        "attempts": len(rows),
        "responses": sum(r.get("status") == "ok" for r in rows),
        "errors": {k: sum(r.get("status") == k for r in rows)
                   for k in sorted({r.get("status", "unknown") for r in rows if r.get("status") != "ok"})},
        "provider_request_count": len(calls),
        "token_observed_request_count": len(observed),
        "input_tokens": total_in,
        "output_tokens": total_out,
        "total_tokens": total_in + total_out,
        "token_observation_fraction": f"{len(observed)}/{len(calls)}" if calls else "0/0",
        "median_provider_request_ms": round(statistics.median(request_latencies), 2) if request_latencies else None,
        "median_final_turn_ms": round(statistics.median(turn_latencies), 2) if turn_latencies else None,
        "median_full_dialogue_ms": round(statistics.median(dialogue_latencies), 2) if dialogue_latencies else None,
        "automatic_metrics": prior.summarize(rows)["metrics"],
    }


def run(out: Path, subset_ids: tuple[str, ...] = SUBSET_IDS) -> dict:
    all_cases = prior.dataset("final")
    by_id = {c["id"]: c for c in all_cases}
    if not set(subset_ids) <= by_id.keys() or len(subset_ids) != len(set(subset_ids)):
        raise RuntimeError("The fixed regression subset no longer matches the prior v0.3 fixture.")
    cases = [by_id[case_id] for case_id in subset_ids]
    for case in cases:
        safety_screen(case)

    models = local_models()
    manifest = models[MODEL]
    selection = ProviderSelection(provider="ollama", model=MODEL)
    report = {
        "schema_version": 1,
        "run_id": uuid4().hex,
        "started_utc": datetime.now(UTC).isoformat(),
        "scope": "local-only Ollama adapter; matched raw/retrieval/retrieval+physics arms",
        "source_split": "existing v0.3 final regression set; not a fresh heldout set",
        "source_split_sha256": prior.digest(all_cases),
        "safety_screen": {"checked_items": len(cases), "rejected_before_generation": 0,
                          "scope": "fixed allowlist plus weapon/attack term scan over prompt, prior turn, rubric"},
        "selected_ids": list(subset_ids),
        "provider": "ollama",
        "model": MODEL,
        "model_manifest": {k: manifest.get(k) for k in ("name", "digest", "size", "details")},
        "endpoint": LOCAL_BASE,
        "machine": machine_facts(),
        "arms": {arm: {"rows": []} for arm in ARMS},
    }

    files = [ROOT / "scripts" / name for name in ("benchmark_v3.py", "benchmark_scoring.py", "independent_v031.py")]
    files.extend(sorted((ROOT / "backend" / "physis").glob("*.py")))
    report["code_sha256"] = {p.relative_to(ROOT).as_posix(): sha256(p) for p in files}

    with ExitStack() as stack:
        temp = Path(stack.enter_context(TemporaryDirectory(prefix="physis-v031-eval-")))
        app = create_app(temp / "experiments.sqlite3")
        client = stack.enter_context(TestClient(app))
        store = app.state.knowledge
        report["knowledge_index"] = store.stats()
        for index, case in enumerate(cases):
            shift = index % len(ARMS)
            order = ARMS[shift:] + ARMS[:shift]
            for arm in order:
                # Re-check the destination immediately before each model call.
                base, _ = endpoint("ollama")
                if base != LOCAL_BASE:
                    raise RuntimeError("Ollama destination changed; stopping before generation.")
                row = prior.sample(client, store, case, arm, selection, rates=None)
                report["arms"][arm]["rows"].append(row)
                print(f"measured {case['id']} / {arm}: {row['status']}", flush=True)

    for arm in ARMS:
        block = report["arms"][arm]
        block["summary"] = arm_summary(block["rows"])
    report["finished_utc"] = datetime.now(UTC).isoformat()
    prior.write_json(out, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ids", nargs="+", choices=[c for c in SUBSET_IDS + ("f-formula-3", "f-misconception-3")])
    args = parser.parse_args()
    report = run(args.out, tuple(args.ids) if args.ids else SUBSET_IDS)
    for arm, block in report["arms"].items():
        summary = block["summary"]
        print(f"{arm}: {summary['responses']}/{summary['attempts']} responses, "
              f"{summary['total_tokens']} tokens, median provider request "
              f"{summary['median_provider_request_ms']} ms")


if __name__ == "__main__":
    raise SystemExit("보관된 v0.3.1 로컬 모델 평가입니다. 명시적 실행과 예산 제한은 scripts/evaluation_v032.py에서 제공합니다.")
