"""Build a local x64 ZIP from the tested CPython distribution and installed wheels."""
import argparse
import hashlib
from io import BytesIO
from importlib import metadata
from importlib.util import cache_from_source
from pathlib import Path
import platform
import py_compile
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
PREFIX = Path("PHYSIS-AI")
ZIP_SAFE = {
    "fastapi", "pydantic", "starlette", "uvicorn", "httpx", "httpcore", "anyio", "h11",
    "click", "idna", "typing-extensions", "typing-inspection", "annotated-doc",
    "annotated-types", "python-dotenv",
}


def distributions():
    pending = [Requirement(line.strip()) for line in (ROOT / "requirements.txt").read_text().splitlines()
               if line.strip() and not line.startswith("#")]
    seen = set()
    while pending:
        requirement = pending.pop()
        name = canonicalize_name(requirement.name)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        wheel = metadata.distribution(name)
        if not requirement.specifier.contains(wheel.version, prereleases=True):
            raise RuntimeError(f"Incompatible build dependency: {requirement} (installed {wheel.version})")
        if name in seen:
            continue
        seen.add(name)
        yield wheel
        pending.extend(Requirement(dep) for dep in (wheel.requires or []))


def add_runtime(archive):
    base = Path(sys.base_prefix)
    target = PREFIX / "runtime"
    for filename in ["python.exe", "python3.dll", "python313.dll", "vcruntime140.dll", "vcruntime140_1.dll", "LICENSE.txt"]:
        archive.write(base / filename, target / filename)
    for item in (base / "DLLs").iterdir():
        if item.suffix in {".pyd", ".dll"} and not item.name.startswith(("_test", "_tkinter", "tcl", "tk8")):
            archive.write(item, target / "DLLs" / item.name)
    wheel_paths = list(distributions())
    zipped = BytesIO()
    with ZipFile(zipped, "w", ZIP_STORED) as library:
        add_python_library(library, base, wheel_paths)
    # One indexed import path avoids thousands of file opens on removable
    # Windows drives. The outer release ZIP compresses this stored archive.
    archive.writestr((target / "python313.zip").as_posix(), zipped.getvalue())
    archive.writestr((target / "python313._pth").as_posix(), ".\nDLLs\npython313.zip\nLib/site-packages\n")
    written = set()
    versions = []
    for wheel in wheel_paths:
        versions.append(f"{wheel.metadata['Name']}=={wheel.version}")
        package = canonicalize_name(wheel.metadata["Name"])
        for relative, original in wheel_entries(wheel):
            if in_library(package, relative) or relative in written:
                continue
            archive.write(original, target / "Lib" / "site-packages" / relative)
            written.add(relative)
    archive.writestr((target / "VERSIONS.txt").as_posix(), "\n".join(sorted(versions)) + "\n")
    add_math_bytecode(archive, target, wheel_paths)


def add_math_bytecode(archive, target, wheels):
    # Each bounded worker starts a new interpreter with -B. Ship checked caches so
    # its first calculation does not spend the worker's time budget compiling SymPy.
    site = target / "Lib" / "site-packages"
    with TemporaryDirectory(prefix="physis-x64-build-") as scratch:
        compiled = Path(scratch) / "module.pyc"
        for wheel in wheels:
            name = canonicalize_name(wheel.metadata["Name"])
            if name not in {"sympy", "mpmath"}:
                continue
            for relative, source in wheel_entries(wheel):
                if relative.suffix != ".py" or relative.parts[0] != name:
                    continue
                py_compile.compile(str(source), cfile=str(compiled), dfile=(site / relative).as_posix(),
                                   doraise=True, invalidation_mode=py_compile.PycInvalidationMode.CHECKED_HASH)
                archive.write(compiled, site / cache_from_source(str(relative)))


def wheel_entries(wheel):
    for entry in wheel.files or []:
        relative = Path(entry)
        if relative.is_absolute() or ".." in relative.parts or "__pycache__" in relative.parts:
            continue
        if "tests" in relative.parts or relative.suffix == ".pyc":
            continue
        original = Path(wheel.locate_file(entry))
        if original.is_file():
            yield relative, original


def in_library(package, relative):
    # Native extension loaders, TLS certificate data and distribution metadata
    # need ordinary filesystem paths. The remaining pure-Python modules are zip-safe.
    return package in ZIP_SAFE and not relative.parts[0].endswith(".dist-info")


def add_python_library(library, base, wheel_paths):
    ignored = {"site-packages", "__pycache__", "test", "tests", "idlelib", "ensurepip", "tkinter", "turtledemo"}
    # Path.walk prunes site-packages before descent, even on large development machines.
    for folder, dirs, files in (base / "Lib").walk():
        dirs[:] = [name for name in dirs if name not in ignored]
        for name in files:
            path = folder / name
            if path.suffix in {".py", ".txt", ".pem"}:
                library.write(path, path.relative_to(base / "Lib"))
    for wheel in wheel_paths:
        package = canonicalize_name(wheel.metadata["Name"])
        if package not in ZIP_SAFE:
            continue
        for relative, original in wheel_entries(wheel):
            if in_library(package, relative):
                library.write(original, relative)


def add_project(archive):
    files = [*ROOT.glob("*.md"), *ROOT.glob("*.cmd"), *ROOT.glob("requirements*.txt"),
             ROOT / ".env.example", ROOT / ".gitignore", ROOT / "pyproject.toml"]
    for folder in ["backend", "scripts", "frontend"]:
        for directory, dirs, names in (ROOT / folder).walk():
            dirs[:] = [name for name in dirs if name not in {"__pycache__", "node_modules", ".pytest_cache",
                                                             ".vite", "test-results", ".cache"} and not name.startswith(".tmp")]
            files.extend(directory / name for name in names if not name.startswith(".env") and
                         not name.endswith((".log", ".pyc", ".tsbuildinfo", ".sqlite3", ".local.json")))
    for path in sorted(set(files)):
        archive.write(path, PREFIX / path.relative_to(ROOT))
    reports = ["retrieval-v0.3.json", "evidence-v0.3.json", "benchmark-v3-final.json",
               "benchmark-v3-release-replay.json", "검증결과-v0.3.md", "검증결과-v0.3.3.md"]
    release = ROOT / "release"
    updates = [p for p in release.iterdir() if p.is_file() and any(v in p.name for v in ("0.3.1","v031"))
               and p.suffix in {".md", ".json", ".png", ".jsonl", ".sha256", ".csv"}]
    for path in [*release.glob("PHYSIS-0.3-*.png"), *(release / name for name in reports), *updates]:
        if path.is_file():
            archive.write(path, PREFIX / "release" / path.name)
    for path in sorted((release / "software-v032").rglob("*")):
        if path.is_file() and path.suffix in {".md",".json",".jsonl",".csv",".sha256",".png"}:
            archive.write(path, PREFIX / path.relative_to(ROOT))
    for package in ["react", "react-dom", "scheduler", "lucide-react", "katex"]:
        path = ROOT / "frontend" / "node_modules" / package / "LICENSE"
        archive.write(path, PREFIX / "third-party" / (package + "-LICENSE.txt"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "release" / "PHYSIS-AI-0.3.3-win-x64.zip")
    parser.add_argument("--reuse-runtime", action="store_true",
                        help="Copy the verified v0.3.2 runtime when requirements are identical.")
    args = parser.parse_args()
    if args.output.resolve() in {(ROOT / "release" / f"PHYSIS-AI-{v}-win-x64.zip").resolve() for v in ("0.1", "0.2", "0.3", "0.3.1", "0.3.2")}:
        sys.exit("Archived release. Choose a v0.3.3 output path.")
    if sys.platform != "win32" or platform.machine().upper() != "AMD64" or sys.version_info[:2] != (3, 13):
        sys.exit("Build using Windows x64 CPython 3.13.")
    if not (ROOT / "frontend" / "dist" / "index.html").exists():
        sys.exit("Build frontend first.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    candidate = args.output.with_suffix(".partial")
    with ZipFile(candidate, "w", ZIP_DEFLATED, compresslevel=5) as archive:
        if args.reuse_runtime:
            source = ROOT / "release" / "PHYSIS-AI-0.3.2-win-x64.zip"
            with source.open("rb") as content:
                if hashlib.file_digest(content, "sha256").hexdigest() != "219969d83e86c0ee231975f572382e53f5a8e763ff6b1b6e04d4d6e3b634d1cb":
                    raise ValueError("Unexpected baseline archive digest.")
            with ZipFile(source) as baseline:
                if baseline.read("PHYSIS-AI/requirements.txt") != (ROOT/"requirements.txt").read_bytes():
                    raise ValueError("Runtime requirements differ from the baseline.")
                for entry in baseline.infolist():
                    if entry.filename.startswith("PHYSIS-AI/runtime/"):
                        archive.writestr(entry.filename, baseline.read(entry))
        else:
            add_runtime(archive)
        add_project(archive)
    candidate.replace(args.output)
    print(args.output)


if __name__ == "__main__":
    main()
