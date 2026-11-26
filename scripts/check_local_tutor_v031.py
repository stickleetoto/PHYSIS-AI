"""Exercise the actual student endpoint with the installed, loopback-only Ollama model."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

import httpx
from independent_v031 import LOCAL_BASE, MODEL, ROOT, local_models, sha256
from fastapi.testclient import TestClient
from physis.api import create_app

# Predeclared release smoke questions; these are not the fresh educational assessment.
CASES = [
    ("newton", "질량 2 kg인 수레에 알짜힘 14 N이 작용합니다. 가속도를 계산해 줘.", "7 m/s²"),
    ("wave_transverse", "횡파에서 매질의 진동 방향과 파동의 진행 방향은 어떤 관계야?", "서로 수직"),
]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    out = parser.parse_args().out
    manifest = local_models()[MODEL]
    report = {"model":MODEL, "digest":manifest["digest"], "endpoint":LOCAL_BASE, "route":"/api/tutor/stream",
              "source_sha256":sha256(ROOT/"backend/physis/studio.py"),
              "started_utc":datetime.now(UTC).isoformat(), "items":[]}
    try:
        with httpx.Client(base_url=LOCAL_BASE,timeout=5,trust_env=False) as local:
            resident = local.get("/api/ps")
            resident.raise_for_status()
            report["resident_before_call"] = [model.get("name") for model in resident.json().get("models", [])]
    except (httpx.HTTPError, ValueError) as exc:
        report["residency_check_error"] = type(exc).__name__
    with TemporaryDirectory() as folder, TestClient(create_app(Path(folder)/"smoke.sqlite3")) as client:
        for model, question, target in CASES:
            initial = client.post("/api/experiments",json={"model":model})
            initial.raise_for_status()
            snapshot = initial.json()
            start = perf_counter()
            res = client.post(report["route"],json={"experiment_id":snapshot["experiment"]["id"],
                              "revision":snapshot["revision"],"message":question,"mode":"explain","level":"school",
                              "selection":{"provider":"ollama","model":MODEL}})
            res.raise_for_status()
            events = [json.loads(line) for line in res.iter_lines() if line]
            final = events[-1]
            row = {"starting_model":model, "question":question, "rubric":target,
                   "elapsed_ms":round(1000*(perf_counter()-start),2), "event":final["event"],
                   "usage":client.get("/api/usage").json()["items"][0]}
            if final["event"] == "result":
                result = final["result"]
                row.update({k:result.get(k) for k in ("action","classification","status","message","assumptions","evidence")})
                if result["snapshot"]:
                    row["engine"] = {k:result["snapshot"]["experiment"][k] for k in ("id","model","values")}
            else:
                row["detail"] = final.get("detail")
            report["items"].append(row)
            print(f"{model}: {row['event']} ({row['elapsed_ms']} ms)",flush=True)
    report["finished_utc"] = datetime.now(UTC).isoformat()
    out.write_text(json.dumps(report, ensure_ascii=False,indent=2)+"\n",encoding="utf8")

if __name__ == "__main__":
    raise SystemExit("v0.3.1 실모델 실행 경로는 보관용입니다. 제한을 적용한 scripts/evaluation_v032.py를 사용하세요.")

