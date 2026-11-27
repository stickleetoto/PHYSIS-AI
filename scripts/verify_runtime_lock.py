"""Verify the release lock against upstream metadata without downloading or executing packages."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

ROOT = Path(__file__).resolve().parents[1]


def get_json(url, payload=None):
    headers = {"User-Agent": "PHYSIS-distribution-audit", "Content-Type": "application/json"}
    data = None if payload is None else json.dumps(payload).encode()
    with urlopen(Request(url, data=data, headers=headers), timeout=25) as response:
        return json.load(response)


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate field in runtime lock: {key}")
        result[key] = value
    return result


def verify():
    lock_path = ROOT / "distribution/runtime-lock.json"
    lock = json.loads(lock_path.read_bytes(), object_pairs_hook=unique_keys)
    runtime = lock["runtime"]
    major, minor, _patch = map(int, runtime["version"].split("."))
    abi = f"cp{major}{minor}"
    archive_name = f"python-{runtime['version']}-embed-amd64.zip"
    python_url = f"https://www.python.org/ftp/python/{runtime['version']}/{archive_name}"
    if runtime["url"] != python_url or runtime["sha256_source_url"] != python_url + ".spdx.json":
        raise ValueError("Unexpected Python archive or checksum origin")
    spdx = get_json(python_url + ".spdx.json")
    described = {r["relatedSpdxElement"] for r in spdx["relationships"]
                 if r["spdxElementId"] == spdx["SPDXID"] and r["relationshipType"] == "DESCRIBES"}
    python_archives = [p for p in spdx["packages"] if p["SPDXID"] in described and
                       p["name"] == "CPython" and p.get("versionInfo") == runtime["version"] and
                       p.get("downloadLocation") == python_url]
    if len(python_archives) != 1 or not any(c["algorithm"] == "SHA256" and c["checksumValue"].lower() == runtime["sha256"]
                                            for c in python_archives[0].get("checksums", [])):
        raise ValueError("CPython archive digest differs from the official SPDX record")

    wheels = {canonicalize_name(r["name"]): r for r in lock["wheels"]}
    if len(wheels) != len(lock["wheels"]):
        raise ValueError("Duplicate normalized wheel name")
    env = {**default_environment(), "python_version": f"{major}.{minor}", "python_full_version": runtime["version"],
           "implementation_name": "cpython", "os_name": "nt", "platform_system": "Windows",
           "platform_machine": "AMD64", "sys_platform": "win32", "extra": ""}
    deps = {}
    advisories = {}
    target_tags = set(cpython_tags((major, minor), abis=[abi], platforms=["win_amd64"]))
    target_tags.update(compatible_tags((major, minor), interpreter=abi, platforms=["win_amd64"]))
    for name, wheel in wheels.items():
        version = wheel["version"]
        metadata_url = f"https://pypi.org/pypi/{name}/{version}/json"
        if wheel.get("pypi_json_url") != metadata_url:
            raise ValueError(f"Unexpected release metadata origin for {name}")
        pkg = get_json(metadata_url)
        artifact = next((x for x in pkg["urls"] if x["filename"] == wheel["filename"]), None)
        if (not artifact or artifact["digests"]["sha256"] != wheel["sha256"] or artifact["yanked"]
                or not artifact["url"].startswith("https://files.pythonhosted.org/")):
            raise ValueError(f"Unverified or withdrawn wheel for {name}")
        declared = wheel.get("download_url", wheel.get("url"))
        if declared and declared != artifact["url"]:
            raise ValueError(f"Wheel URL differs from PyPI for {name}")
        file_name, file_version, _, tags = parse_wheel_filename(artifact["filename"])
        requires_python = artifact.get("requires_python") or pkg["info"].get("requires_python") or ""
        if (file_name != name or str(file_version) != version or not wheel.get("license")
                or not SpecifierSet(requires_python).contains(runtime["version"])
                or not tags.intersection(target_tags)):
            raise ValueError(f"Wheel identity, license or platform mismatch: {name}")
        deps[name] = [Requirement(s) for s in pkg["info"].get("requires_dist") or []]
        active = [v["id"] for v in pkg.get("vulnerabilities", []) if not v.get("withdrawn")]
        if active:
            advisories[name] = sorted(active)

    roots = [Requirement(line) for line in (ROOT / "requirements.txt").read_text().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    seen = set()
    pending = roots.copy()
    while pending:
        req = pending.pop()
        if req.marker and not req.marker.evaluate(env):
            continue
        name = canonicalize_name(req.name)
        if name not in wheels or not req.specifier.contains(wheels[name]["version"], prereleases=True):
            raise ValueError(f"Missing or incompatible Windows dependency: {req}")
        if name not in seen:
            seen.add(name)
            pending.extend(deps[name])
    if seen != set(wheels):
        raise ValueError("Unreachable wheel entries: " + ", ".join(sorted(set(wheels) - seen)))

    npm = json.loads((ROOT / "frontend/package-lock.json").read_bytes())["packages"]
    queries = [{"package": {"ecosystem": "npm", "name": k.removeprefix("node_modules/")},
                "version": data["version"]} for k, data in npm.items() if k and not data.get("dev")]
    results = get_json("https://api.osv.dev/v1/querybatch", {"queries": queries})["results"]
    for q, row in zip(queries, results, strict=True):
        if row.get("vulns"):
            advisories["npm/" + q["package"]["name"]] = sorted(v["id"] for v in row["vulns"])
    if advisories:
        raise ValueError("Published advisories require review: " + json.dumps(advisories))
    return {"python": runtime["version"], "runtime_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
            "pypi_wheels_verified": len(wheels), "windows_dependency_closure": "pass",
            "npm_runtime_entries_checked": len(queries), "pypi_and_osv_reported_advisories": advisories}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        result = json.dumps(verify(), indent=2)
    except (OSError, KeyError, ValueError) as exc:
        sys.exit(str(exc))
    if args.report:
        args.report.write_text(result + "\n", encoding="utf8")
    print(result)
