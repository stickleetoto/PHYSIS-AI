"""Record or check the exact product files used for a fixed educational evaluation."""
import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def inventory(include_evaluation=False):
    files = [*ROOT.joinpath("backend/physis").rglob("*.py"),
             *[p for p in ROOT.joinpath("backend/physis/corpus").rglob("*") if p.is_file()],
             *[p for p in ROOT.joinpath("frontend/src").rglob("*") if p.is_file()],
             *[p for p in ROOT.joinpath("frontend/dist").rglob("*") if p.is_file()],
             *(ROOT/name for name in ("Start-PHYSIS.cmd","requirements.txt","scripts/serve.py",
                                      "frontend/package.json","frontend/package-lock.json"))]
    if include_evaluation:
        files.extend([ROOT/"scripts/evaluation_v032.py", ROOT/"scripts/recovery_v032.py",
                      ROOT/"scripts/package_windows.py", ROOT/"scripts/fingerprint_product.py"])
        files.extend(path for path in (ROOT/"backend/tests/fixtures").rglob("*") if path.is_file())
    result = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
              for p in sorted(files)}
    digest = hashlib.sha256(json.dumps(result,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {"sha256":digest, "files":result}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", type=Path)
    group.add_argument("--check", type=Path)
    parser.add_argument("--include-evaluation", action="store_true", help="Include the v0.3.2 runner and replay fixtures.")
    args = parser.parse_args()
    saved = json.loads(args.check.read_text(encoding="utf8")) if args.check else {}
    with_evaluation = args.include_evaluation or saved.get("include_evaluation", False)
    current = inventory(with_evaluation)
    if args.record:
        with args.record.open("x",encoding="utf8") as output:
            json.dump({"recorded_utc":datetime.now(UTC).isoformat(),"include_evaluation":with_evaluation,**current},output,indent=2)
            output.write("\n")
    else:
        if current["files"] != saved["files"] or current["sha256"] != saved["sha256"]:
            changed = sorted(k for k in current["files"].keys() | saved["files"].keys()
                             if current["files"].get(k)!=saved["files"].get(k))
            raise SystemExit("Product differs: " + ", ".join(changed))
    print(current["sha256"], len(current["files"]), "files")

if __name__ == "__main__":
    main()

