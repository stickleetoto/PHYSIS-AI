"""Score a fixed, source-annotated Korean classroom dataset through the real tutor API."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from physis.api import create_app

DATA = ROOT / "backend/tests/fixtures/education-v2.json"


def ground_truth(turn, result):
    """Score each applicable dimension separately, including explanation quantity + SI unit."""
    snapshot = result.get("snapshot") or {}
    run = snapshot.get("run", {})
    exp = snapshot.get("experiment", {})
    lesson = result.get("lesson") or {}
    text = lesson.get("text", "")
    yield "intent", result.get("action") == turn["action"]
    if turn["action"] == "unsupported":
        yield "unsupported", result.get("status") == "UNSUPPORTED" and not snapshot and bool(result.get("message"))
        return
    yield "model", exp.get("model") == turn["model"]
    if "values" in turn or "settings" in turn:
        yield "variables", (all(math.isclose(exp.get("values", {}).get(k, math.inf),v) for k,v in turn.get("values",{}).items())
                            and all(exp.get(k)==v for k,v in turn.get("settings",{}).items()))
    phrases = all(s in text for s in turn.get("phrases", [])) and all(s not in text for s in turn.get("exclude", []))
    evidence = True
    for key, label, expected, unit in turn.get("numbers", []):
        ref = run.get("facts", {}).get(key)
        match = re.search(re.escape(label) + r"\s+([-+\d.eE]+)\s+" + re.escape(unit) + r"(?![A-Za-z/²³])", text)
        evidence &= (ref is not None and math.isclose(ref, expected, rel_tol=1e-8, abs_tol=1e-9)
                     and match is not None and math.isclose(float(match[1]), expected, rel_tol=5e-4, abs_tol=1e-9))
    if any(k in turn for k in ("phrases","exclude","numbers","absent","quiz_answer","status")):
        quiz = lesson.get("review", {})
        options = quiz.get("options", [])
        correct = quiz.get("correct")
        selected = options[correct] if type(correct) is int and 0 <= correct < len(options) else None
        yield "consistency", (phrases and evidence and all(k not in run.get("facts", {}) for k in turn.get("absent", []))
                              and ("quiz_answer" not in turn or selected == turn["quiz_answer"])
                              and ("status" not in turn or run.get("status") == turn["status"]))


def evaluate(dataset=DATA):
    dataset = json.loads(Path(dataset).read_text(encoding="utf8"))
    attempted, passed = Counter(), Counter()
    rows = []
    with TemporaryDirectory() as folder, TestClient(create_app(Path(folder)/"eval.sqlite3")) as client:
        for scenario in dataset["scenarios"]:
            current = client.post("/api/experiments",json={"model":scenario["initial"]}).json()
            for i, turn in enumerate(scenario["turns"]):
                body = dict(experiment_id=current["experiment"]["id"], revision=current["revision"],
                            level="school", mode=turn.get("mode","explain"), message=turn["ask"],
                            selection={"provider":"mock","model":"local-rules"})
                response = client.post("/api/tutor/stream",json=body)
                response.raise_for_status()
                events = [json.loads(line) for line in response.iter_lines() if line]
                result = next((e["result"] for e in events if e["event"]=="result"),{})
                checks = dict(ground_truth(turn,result))
                returned = result.get("snapshot")
                if turn["action"] != "create":
                    persisted = client.get("/api/experiments/"+body["experiment_id"]).json()
                    expected_revision = current["revision"] + int(turn["action"] == "modify")
                    same = persisted["revision"] == expected_revision
                    same &= returned is None if turn["action"] == "unsupported" else (
                        bool(returned) and returned["experiment"]["id"] == body["experiment_id"] and returned["revision"] == expected_revision)
                    if turn["action"] in {"unsupported","explain"}:
                        same &= persisted["experiment"] == current["experiment"]
                    same &= all(math.isclose(persisted["experiment"]["values"].get(k,math.inf),v)
                                for k,v in turn.get("retain",{}).items())
                    checks["context"] = bool(same)
                for metric, ok in checks.items():
                    attempted[metric] += 1
                    passed[metric] += bool(ok)
                errors = [e.get("detail") for e in events if e["event"]=="error"]
                rows.append(dict(id=f"{scenario['id']}/{i+1}", category=turn["type"], passed=all(checks.values()),
                                 checks=checks, action=result.get("action"), errors=errors))
                if returned:
                    current = returned
    return {"provider":"mock/local-rules","scenarios":len(dataset["scenarios"]),"turns":len(rows),
            "metrics":{k:{"passed":passed[k],"total":v} for k,v in attempted.items()},"rows":rows}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Include each turn and its checks")
    args=parser.parse_args()
    result=evaluate()
    if args.json:
        print(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        print(f"{result['provider']}: {result['scenarios']} scenarios, {result['turns']} turns")
        for k,v in result["metrics"].items():
            print(f"{k}: {v['passed']}/{v['total']}")
        for row in result["rows"]:
            if not row["passed"]:
                print(row["id"],row["action"],[k for k,v in row["checks"].items() if not v],row["errors"])
    sys.exit(0 if all(r["passed"] for r in result["rows"]) else 1)
