"""Re-run the two published education cohorts through the current offline tutor, retaining per-item evidence."""
import argparse
import json
from datetime import UTC,datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from benchmark_v3 import ROOT, TestClient, sample
from benchmark_scoring import summarize, write_json
from physis.api import create_app

BASES = {"72":"benchmark-v031-regression72.json","24":"benchmark-v031-mock-heldout-24-graded.json"}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cohort",choices=BASES)
    parser.add_argument("--out",type=Path,required=True)
    args = parser.parse_args()
    baseline = json.loads((ROOT/"release"/BASES[args.cohort]).read_text(encoding="utf8"))
    old = baseline["arms"]["mock"]["rows"]
    assert len(old)==int(args.cohort)
    rows = []
    with TemporaryDirectory(prefix="physis-v032-regression-") as tmp:
        with TestClient(create_app(Path(tmp)/"experiment.sqlite3")) as client:
            for entry in old:
                rows.append(sample(client,client.app.state.knowledge,entry["case"],"mock",None,None))
    report = {"version":"0.3.2","provider":"mock","baseline":BASES[args.cohort],"cohort_size":len(rows),
              "finished_utc":datetime.now(UTC).isoformat(),"rows":rows,"summary":summarize(rows)}
    write_json(args.out,report)
    print(args.out,report["summary"])

if __name__=="__main__":
    main()
