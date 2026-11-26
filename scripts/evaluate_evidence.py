"""Exercise the evidence API with predeclared positive, negative and indeterminate controls."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi.testclient import TestClient
from physis.api import Snapshot, create_app
from physis.evidence import run_id
from physis.knowledge import KnowledgeStore


def evaluate(directory):
    cases = []

    def record(group, name, actual, expected):
        cases.append(dict(group=group, case=name, expected=expected, observed=actual,
                          matched=actual == expected))

    with TestClient(create_app(directory / "lab.sqlite3")) as client:
        experiment = client.post("/api/experiments", json={"model":"newton", "patch":{"values":{"force":12,"mass":3}}})
        experiment.raise_for_status()
        snap = Snapshot.model_validate(experiment.json())
        header = {"experiment_id":str(snap.experiment.id), "revision":snap.revision,
                  "query":"Newton second law net force mass acceleration"}

        def audit(**fields):
            response = client.post("/api/evidence/check", json=header | fields)
            response.raise_for_status()
            return response.json()

        store = KnowledgeStore(directory / "knowledge-v3.sqlite3")
        rows = store.search(header["query"], model="newton", limit=8)
        primary = next(row for row in rows if "inversely proportional" in row["text"])
        citation = {k: primary[k] for k in ("id","doc_id","locator")}
        citation["quote"] = "inversely proportional"
        checks = [
            ("original passage", {}, "source_verified"),
            ("invented wording", {"quote":"always increases with mass squared"}, "failed"),
            ("wrong document", {"doc_id":"invented"}, "failed"),
            ("wrong page", {"locator":"page 4500"}, "failed"),
            ("unretrieved identifier", {"id":"not-retrieved"}, "insufficient"),
        ]
        for name, change, expected in checks:
            result = audit(citations=[citation | change])["sources"][0]
            record("citation", name, result["status"], expected)

        number = {"key":"acceleration", "value":4, "unit":"m/s²", "revision":snap.revision,
                  "experiment_id":str(snap.experiment.id), "run_id":run_id(snap)}
        checks = [
            ("12 N / 3 kg", {}, "calculation_verified"),
            ("ASCII power notation", {"unit":"m/s^2"}, "calculation_verified"),
            ("inside tolerance", {"value":4.001}, "calculation_verified"),
            ("outside tolerance", {"value":4.003}, "failed"),
            ("wrong unit", {"unit":"m/s"}, "failed"),
            ("malformed unit", {"unit":"m^/s2"}, "failed"),
            ("stale run fingerprint", {"run_id":"old"}, "failed"),
            ("other revision", {"revision":snap.revision+1}, "failed"),
            ("other experiment", {"experiment_id":str(UUID(int=1))}, "failed"),
            ("unmeasured quantity", {"key":"air_resistance"}, "unverifiable"),
        ]
        for name, change, expected in checks:
            result = audit(numbers=[number | change])["calculations"][0]
            record("number", name, result["status"], expected)

        si = {"a":"m/s²","F":"N","m":"kg"}
        checks = [
            ("registered Newton relation", {"formula_expression":"F/m","formula_units":si}, "applicable"),
            ("equivalent RHS", {"formula_expression":"F*m^(-1)"}, "applicable"),
            ("wrong relation", {"formula_expression":"F*m"}, "failed"),
            ("wrong SI units", {"formula_units":si | {"m":"g"}}, "failed"),
            ("misspelled variable", {"formula_expression":"z/m"}, "failed"),
            ("different model", {"formula_id":"pendulum"}, "outside_conditions"),
            ("unknown formula", {"formula_id":"invented"}, "failed"),
        ]
        for name, fields, expected in checks:
            result = audit(**({"formula_id":"newton"} | fields))["formula"]
            record("formula", name, result["status"], expected)

        bad = client.post("/api/experiments",json={"model":"spring","patch":{"duration":10,"dt":.2,"method":"euler"}})
        bad.raise_for_status()
        unstable = Snapshot.model_validate(bad.json())
        assert unstable.run.status == "FAILED"
        raw = {"experiment_id":str(unstable.experiment.id), "revision":unstable.revision,
               "key":"last.0.x", "unit":"m", "value":unstable.run.series["0.x"][-1], "run_id":run_id(unstable)}
        result = audit(experiment_id=raw["experiment_id"], revision=raw["revision"], numbers=[raw])
        record("number","exact readout from failed trajectory",result["calculations"][0]["status"],"unverifiable")

    summary = defaultdict(lambda: {"matched":0, "total":0})
    for row in cases:
        summary[row["group"]]["total"] += 1
        summary[row["group"]]["matched"] += int(row["matched"])
    return {"scope":"Deterministic controls on the public audit API. No free-text semantic accuracy estimate.",
            "summary":dict(summary), "cases":cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    with TemporaryDirectory() as folder:
        result = evaluate(Path(folder))
    if args.out:
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(result["summary"]))
    return 0 if all(row["matched"] for row in result["cases"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())

