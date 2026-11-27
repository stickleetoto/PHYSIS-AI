"""Reconcile only individually reviewed Gitleaks findings in the immutable v0.3.2 commit."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess


IMPORT = "020fb63c6ddc2c24ee736b8debf24d128539617a"
RECORDS = {
    "release/benchmark-v031-mock-heldout-24-graded.json": (57, 66, 86, 91),
    "release/benchmark-v031-mock-heldout-24.json": (57, 66, 86, 91),
    "release/benchmark-v031-regression72.json": (9, 18, 38, 43),
    "release/benchmark-v3-final.json": (8, 14, 33, 38),
    "release/benchmark-v3-release-replay.json": (8, 14, 33, 38),
    "release/product-freeze-v031.json": (7, 21, 41, 46),
    "release/software-v032/product-freeze.json": (8, 26, 46, 51),
}


def verify(report):
    expected = Counter((path, line) for path, lines in RECORDS.items() for line in lines)
    actual = Counter()
    for finding in report:
        path, line = finding["File"], finding["StartLine"]
        if (finding["Commit"] != IMPORT or finding["RuleID"] != "generic-api-key"
                or (path, line) not in expected):
            raise ValueError(f"Unreviewed finding: {finding['RuleID']} in {path} at line {line}")
        blob = subprocess.check_output(["git", "show", f"{IMPORT}:{path}"]).decode()
        field = blob.splitlines()[line - 1].strip().rstrip(",")
        key, value = next(iter(json.loads("{" + field + "}").items()))
        record = json.loads(blob)
        if (not re.fullmatch(r"backend/physis/(api|knowledge_api|science_api|study_api)\.py", key)
                or not re.fullmatch("[a-f0-9]{64}", value)
                or record.get("code_sha256", record.get("files", {})).get(key) != value):
            raise ValueError(f"Expected a historical source digest at {path}:{line}")
        actual[path, line] += 1
    if actual != expected:
        raise ValueError("The full-history finding set differs from the reviewed import.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    verify(json.loads(parser.parse_args().report.read_bytes()))
    print("Reconciled 28 historical source digests. No unreviewed findings.")
