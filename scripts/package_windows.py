"""Build and audit the allowlisted PHYSIS AI 0.4.1 Windows source distribution."""

from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid5
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile, ZipInfo


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "distribution" / "package-allowlist.json"
FRONTEND_LICENSE_AUDIT = ROOT / "distribution" / "audit" / "frontend-licenses.json"
RELEASE_DIR = ROOT / "release"
DEFAULT_ZIP = RELEASE_DIR / "PHYSIS-AI-0.4.1-win-x64.zip"
CHECKSUM_NAME = "SHA256SUMS.txt"
SBOM_NAME = "sbom.cdx.json"
ZIP_ROOT = "PHYSIS-AI"
ZIP_TIME = (1980, 1, 1, 0, 0, 0)
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 12 * 1024 * 1024
MAX_MEMBER_BYTES = 8 * 1024 * 1024
MAX_MEMBER_COUNT = 400
TEXT_SUFFIXES = {
    ".cmd", ".css", ".html", ".js", ".json", ".md", ".py", ".ps1", ".sha256", ".svg", ".txt",
}
PROHIBITED_SUFFIXES = {".dll", ".exe", ".pyd", ".pyc", ".so", ".dylib", ".whl"}


class PackageAuditError(RuntimeError):
    """Raised when a release archive fails a distribution policy check."""


@dataclass(frozen=True)
class ArchiveAudit:
    members: tuple[str, ...]
    sha256: str
    archive_bytes: int
    uncompressed_bytes: int


SECRET_PATTERNS = (
    (re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"), "private-key block"),
    (re.compile(r"\bAKIA[A-Z0-9]{16}\b"), "AWS access key"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "GitHub token"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{24,}\b"), "API key"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google API key"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{24,}"), "bearer token"),
    (re.compile(r"(?im)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{24,}"), "credential assignment"),
)
PII_PATTERNS = (
    (re.compile(r"(?i)\b[A-Z]:\\(?:Users|Documents and Settings)\\[A-Za-z0-9._-]+"), "local user profile path"),
    (re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"), "email address"),
    (re.compile(r"\b\d{6}-[1-4]\d{6}\b"), "Korean resident registration number"),
)


NOTICE_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "LICENSE": (b"Apache License", b"Version 2.0"),
    "NOTICE": (b"Copyright 2026 DevSeat",),
    "THIRD_PARTY_NOTICES.md": (b"Third-party notices", b"CC BY 4.0"),
    "SOURCE_MANIFEST.md": (b"OpenStax", b"CC BY 4.0"),
    "WINDOWS_DISTRIBUTION.md": (b"runtime", b"0.4.1"),
    "backend/physis/corpus/CC-BY-4.0.txt": (b"Creative Commons Attribution 4.0",),
    "frontend/dist/licenses/KaTeX-MIT.txt": (b"The MIT License", b"Khan Academy"),
    "frontend/dist/licenses/KaTeX-fonts-OFL-1.1.txt": (b"SIL OPEN FONT LICENSE", b"Reserved Font Names"),
    "third-party-notices/React-MIT.txt": (b"MIT License", b"Meta Platforms, Inc."),
    "third-party-notices/React-DOM-MIT.txt": (b"MIT License", b"Meta Platforms, Inc."),
    "third-party-notices/Scheduler-MIT.txt": (b"MIT License", b"Meta Platforms, Inc."),
    "third-party-notices/Lucide-ISC.txt": (b"ISC License", b"Lucide Contributors"),
    "third-party-notices/Feather-MIT.txt": (b"MIT License", b"Cole Bemis"),
    "third-party-notices/Vite-MIT.txt": (b"MIT License", b"VoidZero Inc.", b"SOFTWARE."),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def render_sha256_sums(archive_path: Path) -> str:
    return f"{sha256_file(archive_path)}  {archive_path.name}\n"


def render_internal_sha256s(files: dict[str, bytes]) -> bytes:
    inventory_member = f"{ZIP_ROOT}/{CHECKSUM_NAME}"
    lines = [
        f"{hashlib.sha256(data).hexdigest()}  {member}"
        for member, data in sorted(files.items())
        if member != inventory_member
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def build_deterministic_zip(output_path: Path, files: dict[str, bytes]) -> None:
    """Write stable ZIP metadata, sorted member order, and fixed timestamps."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for member in sorted(files):
            info = ZipInfo(member, date_time=ZIP_TIME)
            info.compress_type = ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 0
            info.extra = b""
            info.comment = b""
            archive.writestr(info, files[member], compress_type=ZIP_DEFLATED, compresslevel=9)


def _text_content(member: str, data: bytes) -> str | None:
    if PurePosixPath(member).suffix.lower() not in TEXT_SUFFIXES:
        return None
    return data.decode("utf-8", errors="replace")


def _check_member_path(member: str) -> str | None:
    if not member or member.startswith(("/", "\\")) or "\\" in member:
        return "invalid ZIP path"
    path = PurePosixPath(member)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return "invalid ZIP path"
    if not path.parts or path.parts[0] != ZIP_ROOT:
        return "member is outside the approved archive root"
    if path.suffix.lower() in PROHIBITED_SUFFIXES:
        return "prohibited binary, bytecode, wheel, or runtime payload"
    lowered = member.casefold()
    if lowered.startswith(f"{ZIP_ROOT.casefold()}/runtime/") or "/site-packages/" in lowered:
        return "prohibited runtime payload"
    if any(term in lowered for term in ("/node_modules/", "/.git/", "/tests/", "/test-results/", "/__pycache__/")):
        return "prohibited development or test path"
    return None


def audit_archive(
    archive_path: Path,
    *,
    expected_members: set[str],
    required_members: Iterable[str] = (),
    max_archive_bytes: int = MAX_ARCHIVE_BYTES,
    max_uncompressed_bytes: int = MAX_UNCOMPRESSED_BYTES,
    expected_content_sha256: dict[str, str] | None = None,
    scan_content: bool = True,
) -> ArchiveAudit:
    """Validate archive path safety, exact membership, payload policy, and CRC."""
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise PackageAuditError(f"archive does not exist: {archive_path}")
    archive_bytes = archive_path.stat().st_size
    if archive_bytes <= 0 or archive_bytes > max_archive_bytes:
        raise PackageAuditError(f"archive size {archive_bytes} is outside 1..{max_archive_bytes} bytes")

    try:
        with ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_MEMBER_COUNT:
                raise PackageAuditError(f"archive has {len(entries)} entries; maximum is {MAX_MEMBER_COUNT}")
            names = [entry.filename for entry in entries]
            if len(names) != len(set(names)):
                raise PackageAuditError("archive contains duplicate member names")
            folded = [name.casefold() for name in names]
            if len(folded) != len(set(folded)):
                raise PackageAuditError("archive contains member names that collide on Windows")
            actual = set(names)
            missing = set(expected_members) - actual
            extra = actual - set(expected_members)
            if missing or extra:
                issues = []
                if missing:
                    issues.append("missing approved members: " + ", ".join(sorted(missing)))
                if extra:
                    issues.append("unexpected members: " + ", ".join(sorted(extra)))
                raise PackageAuditError("; ".join(issues))

            total_size = 0
            for entry in entries:
                if entry.is_dir():
                    raise PackageAuditError(f"unexpected directory entry: {entry.filename}")
                unix_mode = entry.external_attr >> 16
                if stat.S_ISLNK(unix_mode):
                    raise PackageAuditError(f"symbolic links are prohibited in the ZIP: {entry.filename}")
                if entry.flag_bits & 0x1:
                    raise PackageAuditError(f"encrypted ZIP member: {entry.filename}")
                if entry.file_size > MAX_MEMBER_BYTES:
                    raise PackageAuditError(f"member exceeds size limit: {entry.filename}")
                total_size += entry.file_size
                path_issue = _check_member_path(entry.filename)
                if path_issue:
                    raise PackageAuditError(f"{path_issue}: {entry.filename}")
            if total_size > max_uncompressed_bytes:
                raise PackageAuditError(f"uncompressed size {total_size} exceeds {max_uncompressed_bytes} bytes")

            for required in required_members:
                if required not in actual:
                    raise PackageAuditError(f"required legal or runtime file is missing: {required}")

            broken = archive.testzip()
            if broken is not None:
                raise PackageAuditError(f"ZIP CRC failure in member: {broken}")

            for member, expected_hash in (expected_content_sha256 or {}).items():
                if member not in actual:
                    raise PackageAuditError(f"approved source member is missing: {member}")
                actual_hash = hashlib.sha256(archive.read(member)).hexdigest()
                if actual_hash != expected_hash:
                    raise PackageAuditError(f"member content differs from approved local input: {member}")

            inventory_member = f"{ZIP_ROOT}/{CHECKSUM_NAME}"
            if inventory_member in actual:
                archive_files = {
                    member: archive.read(member)
                    for member in names
                    if member != inventory_member
                }
                expected_inventory = render_internal_sha256s(archive_files)
                if archive.read(inventory_member) != expected_inventory:
                    raise PackageAuditError("internal SHA256SUMS.txt does not match all ZIP members")

            if scan_content:
                for entry in entries:
                    text = _text_content(entry.filename, archive.read(entry))
                    if text is None:
                        continue
                    for pattern, label in SECRET_PATTERNS:
                        if pattern.search(text):
                            raise PackageAuditError(f"secret marker ({label}) found in {entry.filename}")
                    for pattern, label in PII_PATTERNS:
                        if pattern.search(text):
                            raise PackageAuditError(f"possible PII ({label}) found in {entry.filename}")
    except BadZipFile as exc:
        raise PackageAuditError(f"invalid ZIP archive: {exc}") from exc

    digest = sha256_file(archive_path)
    return ArchiveAudit(tuple(sorted(names)), digest, archive_bytes, total_size)


def _entry_table(config: dict[str, Any]) -> list[dict[str, str]]:
    entries = list(config["fixed_files"])
    entries.extend(
        {"source": f"backend/physis/{name}", "path": f"backend/physis/{name}"}
        for name in config["production_modules"]
    )
    entries.extend(
        {"source": f"frontend/dist/{name}", "path": f"frontend/dist/{name}"}
        for name in config["frontend_dist"]
    )
    return entries


def expected_archive_members(config: dict[str, Any]) -> set[str]:
    root = config["archive_root"]
    fixed = {f"{root}/{entry['path']}" for entry in _entry_table(config)}
    fixed.update(f"{root}/{member}" for member in config.get("generated_files", []))
    return fixed


def load_allowlist(path: Path = ALLOWLIST) -> dict[str, Any]:
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageAuditError(f"cannot read package allowlist {path}: {exc}") from exc
    if config.get("schema_version") != 1 or config.get("archive_root") != ZIP_ROOT:
        raise PackageAuditError("unsupported package allowlist schema or root")
    return config


def _is_reparse_point(path: Path) -> bool:
    metadata = path.lstat()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)


def _assert_no_reparse_components(root: Path, path: Path, description: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise PackageAuditError(f"{description} resolves outside the package source root: {path}") from exc

    current = root
    for part in relative.parts:
        current = current / part
        try:
            if _is_reparse_point(current):
                raise PackageAuditError(f"{description} contains a symbolic link or reparse point: {current}")
        except FileNotFoundError:
            return
        except OSError as exc:
            raise PackageAuditError(f"cannot inspect {description} for reparse points: {current}") from exc


def _assert_no_reparse_tree(root: Path, directory: Path, description: str) -> None:
    _assert_no_reparse_components(root, directory, description)
    pending = [directory]
    while pending:
        current = pending.pop()
        try:
            children = list(current.iterdir())
        except FileNotFoundError:
            return
        except OSError as exc:
            raise PackageAuditError(f"cannot inspect {description}: {current}") from exc
        for child in children:
            _assert_no_reparse_components(root, child, description)
            try:
                if child.is_dir():
                    pending.append(child)
            except OSError as exc:
                raise PackageAuditError(f"cannot inspect {description}: {child}") from exc


def validate_source_inventory(root: Path, config: dict[str, Any]) -> list[tuple[Path, str]]:
    """Resolve every allowlisted source and reject unreviewed production/data/build files."""
    entries = _entry_table(config)
    sources = [entry["source"] for entry in entries]
    members = [entry["path"] for entry in entries]
    if len(sources) != len(set(sources)) or len(members) != len(set(members)):
        raise PackageAuditError("allowlist has duplicate source or ZIP destination paths")

    resolved: list[tuple[Path, str]] = []
    for entry in entries:
        source = Path(entry["source"])
        member = PurePosixPath(entry["path"])
        if source.is_absolute() or ".." in source.parts or member.is_absolute() or ".." in member.parts:
            raise PackageAuditError(f"unsafe allowlist entry: {entry}")
        path = root / source
        _assert_no_reparse_components(root, path, f"allowlisted source {source.as_posix()}")
        if not path.is_file() or path.is_symlink():
            raise PackageAuditError(f"allowlisted file is missing or a symlink: {source.as_posix()}")
        if _check_member_path(f"{ZIP_ROOT}/{member.as_posix()}"):
            raise PackageAuditError(f"allowlist contains prohibited member path: {member.as_posix()}")
        resolved.append((path, f"{ZIP_ROOT}/{member.as_posix()}"))

    _assert_no_reparse_tree(root, root / "backend" / "physis", "backend production inventory")
    _assert_no_reparse_tree(root, root / "frontend" / "dist", "compiled frontend inventory")

    expected_modules = {f"backend/physis/{name}" for name in config["production_modules"]}
    actual_modules = {
        path.relative_to(root).as_posix()
        for path in (root / "backend" / "physis").glob("*.py")
        if path.is_file()
    }
    if actual_modules != expected_modules:
        raise PackageAuditError(
            "production Python module inventory changed; review the allowlist. "
            f"missing={sorted(expected_modules - actual_modules)} extra={sorted(actual_modules - expected_modules)}"
        )

    expected_backend_files = {source for source in sources if source.startswith("backend/physis/")}
    actual_backend_files = {
        path.relative_to(root).as_posix()
        for path in (root / "backend" / "physis").rglob("*")
        if path.is_file() and path.suffix.lower() != ".pyc" and "__pycache__" not in path.parts
    }
    if actual_backend_files != expected_backend_files:
        raise PackageAuditError(
            "backend data/code inventory changed; review the allowlist. "
            f"missing={sorted(expected_backend_files - actual_backend_files)} extra={sorted(actual_backend_files - expected_backend_files)}"
        )

    expected_frontend_files = {f"frontend/dist/{name}" for name in config["frontend_dist"]}
    actual_frontend_files = {
        path.relative_to(root).as_posix()
        for path in (root / "frontend" / "dist").rglob("*")
        if path.is_file()
    }
    if actual_frontend_files != expected_frontend_files:
        raise PackageAuditError(
            "compiled frontend inventory changed; rebuild and review the allowlist. "
            f"missing={sorted(expected_frontend_files - actual_frontend_files)} extra={sorted(actual_frontend_files - expected_frontend_files)}"
        )
    return resolved


def _required_notice_members(config: dict[str, Any]) -> set[str]:
    root = config["archive_root"]
    return {f"{root}/{path}" for path in NOTICE_SIGNATURES}


def audit_licensing(archive_path: Path, config: dict[str, Any]) -> None:
    with ZipFile(archive_path) as archive:
        files = set(archive.namelist())
        for relative, markers in NOTICE_SIGNATURES.items():
            member = f"{config['archive_root']}/{relative}"
            if member not in files:
                raise PackageAuditError(f"required notice is missing: {member}")
            content = archive.read(member)
            if not all(marker in content for marker in markers):
                raise PackageAuditError(f"required license/attribution text is incomplete: {member}")

        if f"{config['archive_root']}/README.txt" not in files:
            raise PackageAuditError("end-user README.txt is missing from ZIP root")
        if f"{config['archive_root']}/scripts/serve.py" not in files:
            raise PackageAuditError("scripts/serve.py is missing from ZIP")
        if f"{config['archive_root']}/Start-PHYSIS.cmd" not in files:
            raise PackageAuditError("root Start-PHYSIS.cmd is missing from ZIP")


def _normalize_license(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else value


SPDX_LICENSE_IDS = {
    "0BSD", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "CC-BY-4.0", "ISC",
    "MIT", "MPL-2.0", "OFL-1.1", "PSF-2.0", "Unlicense",
}
SPDX_EXCEPTIONS = {"Autoconf-exception-3.0", "Classpath-exception-2.0", "GCC-exception-3.1"}


def _validate_spdx_expression(expression: str) -> None:
    tokens = re.findall(r"\(|\)|AND|OR|WITH|[A-Za-z0-9][A-Za-z0-9.+-]*", expression)
    if not tokens or re.sub(r"\s+", "", "".join(tokens)) != re.sub(r"\s+", "", expression):
        raise PackageAuditError(f"invalid SPDX license expression: {expression}")

    position = 0

    def primary() -> None:
        nonlocal position
        if position >= len(tokens):
            raise PackageAuditError(f"incomplete SPDX license expression: {expression}")
        token = tokens[position]
        if token == "(":
            position += 1
            disjunction()
            if position >= len(tokens) or tokens[position] != ")":
                raise PackageAuditError(f"unclosed SPDX license expression: {expression}")
            position += 1
            return
        if token in {"AND", "OR", "WITH", ")"} or (token not in SPDX_LICENSE_IDS and not token.startswith("LicenseRef-")):
            raise PackageAuditError(f"unknown SPDX license identifier in expression: {token}")
        position += 1
        if position < len(tokens) and tokens[position] == "WITH":
            position += 1
            if position >= len(tokens) or tokens[position] not in SPDX_EXCEPTIONS:
                raise PackageAuditError(f"unknown SPDX exception in expression: {expression}")
            position += 1

    def conjunction() -> None:
        nonlocal position
        primary()
        while position < len(tokens) and tokens[position] == "AND":
            position += 1
            primary()

    def disjunction() -> None:
        nonlocal position
        conjunction()
        while position < len(tokens) and tokens[position] == "OR":
            position += 1
            conjunction()

    disjunction()
    if position != len(tokens):
        raise PackageAuditError(f"invalid SPDX license expression: {expression}")


def _spdx_license_object(value: str) -> dict[str, str]:
    if value in SPDX_LICENSE_IDS:
        return {"id": value}
    _validate_spdx_expression(value)
    return {"expression": value}


def _component(
    *,
    name: str,
    version: str,
    purl: str,
    licenses: str | list[str],
    origin: str,
    paths: Iterable[str],
    scope: str = "required",
    hashes: list[dict[str, str]] | None = None,
    role: str = "runtime",
    extra_properties: Iterable[tuple[str, str]] = (),
) -> dict[str, Any]:
    license_values = [_spdx_license_object(value) for value in _normalize_license(licenses)]
    expressions = [value for value in license_values if "expression" in value]
    if expressions and len(license_values) != 1:
        raise PackageAuditError("a CycloneDX SPDX expression cannot be combined with separate license entries")
    license_entries = ([{"expression": expressions[0]["expression"]}] if expressions else
                       [{"license": value} for value in license_values])
    properties = [
        {"name": "origin", "value": origin},
        {"name": "role", "value": role},
    ]
    path_property = "provisioned:target" if scope == "optional" else "distribution:path"
    properties.extend({"name": path_property, "value": path} for path in sorted(set(paths)))
    properties.extend({"name": key, "value": value} for key, value in extra_properties)
    if scope == "optional":
        properties.append({"name": "delivery", "value": "provisioned-after-extraction"})
    component: dict[str, Any] = {
        "type": "library",
        "bom-ref": purl,
        "name": name,
        "version": version,
        "scope": scope,
        "purl": purl,
        "licenses": license_entries,
        "properties": properties,
        "externalReferences": [{
            "type": "website" if "pypi.org/pypi/" in origin else "distribution",
            "url": origin,
        }],
    }
    if hashes:
        component["hashes"] = hashes
    return component


def render_cyclonedx(
    *,
    source_inventory_sha256: str,
    components: list[dict[str, Any]],
    optional_components: list[dict[str, Any]],
    archive_paths: Iterable[str] = (),
) -> str:
    """Render a deterministic CycloneDX 1.6 BOM with runtime provisioning separated."""
    if not re.fullmatch(r"[0-9a-f]{64}", source_inventory_sha256):
        raise PackageAuditError("SBOM source inventory digest must be a lowercase SHA-256 value")
    root_purl = "pkg:generic/devseat/physis-ai@0.4.1"
    all_components = []
    for item in components:
        all_components.append(_component(**item))
    for item in optional_components:
        values = dict(item)
        values["scope"] = "optional"
        all_components.append(_component(**values))
    all_components.sort(key=lambda item: (item["purl"], item["name"]))
    if len({component["bom-ref"] for component in all_components}) != len(all_components):
        raise PackageAuditError("SBOM contains duplicate PURLs")

    serial = uuid5(NAMESPACE_URL, f"urn:physis-ai-0.4.1:source-inventory:{source_inventory_sha256}")
    sbom = {
        "$schema": "https://cyclonedx.org/schema/bom-1.6.schema.json",
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "tools": {
                "components": [{
                    "type": "application",
                    "name": "PHYSIS Windows package audit",
                    "version": "1.0.0",
                }]
            },
            "component": {
                "type": "application",
                "bom-ref": root_purl,
                "name": "PHYSIS AI Windows x64 Distribution",
                "version": "0.4.1",
                "scope": "required",
                "purl": root_purl,
                "licenses": [{"license": _spdx_license_object("Apache-2.0")}],
                "properties": [
                    {"name": "distribution:source-inventory-sha256", "value": source_inventory_sha256},
                    {"name": "distribution:runtime", "value": "installed by explicit user-run setup after extraction"},
                    *({"name": "distribution:path", "value": path} for path in sorted(set(archive_paths))),
                ],
                "externalReferences": [{
                    "type": "vcs",
                    "url": "https://github.com/stickleetoto/PHYSIS-AI",
                }],
            },
        },
        "components": all_components,
        "dependencies": [{
            "ref": root_purl,
            "dependsOn": [component["bom-ref"] for component in all_components],
        }],
    }
    return json.dumps(sbom, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _npm_components(root: Path, archive_members: set[str]) -> list[dict[str, Any]]:
    try:
        npm_entries = json.loads(FRONTEND_LICENSE_AUDIT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageAuditError(f"cannot read verified frontend license inventory: {exc}") from exc

    main_js = sorted(
        member for member in archive_members
        if member.startswith(f"{ZIP_ROOT}/frontend/dist/assets/index-") and member.endswith(".js")
    )
    if len(main_js) != 1:
        raise PackageAuditError(f"expected one main bundled JS asset for SBOM mapping, found {main_js}")

    components: list[dict[str, Any]] = []
    for record in npm_entries:
        name = record["component"]
        version = record["version"]
        if name == "katex":
            paths = [
                member for member in archive_members
                if "/frontend/dist/assets/" in member and (
                    "/katex" in member.casefold() or "/katex_" in member.casefold()
                )
            ]
            paths.extend([
                f"{ZIP_ROOT}/frontend/dist/licenses/KaTeX-MIT.txt",
                f"{ZIP_ROOT}/frontend/dist/licenses/KaTeX-fonts-OFL-1.1.txt",
            ])
            licenses: str | list[str] = ["MIT", "OFL-1.1"]
            role = "bundled-frontend-runtime-and-fonts"
        else:
            paths = [main_js[0]]
            notice = {
                "react": "React-MIT.txt",
                "react-dom": "React-DOM-MIT.txt",
                "scheduler": "Scheduler-MIT.txt",
                "lucide-react": "Lucide-ISC.txt",
                "vite": "Vite-MIT.txt",
            }.get(name)
            if notice:
                paths.append(f"{ZIP_ROOT}/third-party-notices/{notice}")
            licenses = record["license"]
            role = "embedded-modulepreload-polyfill" if name == "vite" else "bundled-frontend-runtime"
        if record.get("notice_file") and record.get("notice_sha256"):
            if name == "katex":
                actual_notice = root / "frontend" / "dist" / "licenses" / "KaTeX-MIT.txt"
            else:
                target = {
                    "react": "React-MIT.txt",
                    "react-dom": "React-DOM-MIT.txt",
                    "scheduler": "Scheduler-MIT.txt",
                    "lucide-react": "Lucide-ISC.txt",
                }.get(name)
                actual_notice = root / "distribution" / "notices" / target if target else None
            if actual_notice and actual_notice.is_file() and sha256_file(actual_notice) != record["notice_sha256"]:
                raise PackageAuditError(f"frontend notice hash differs from reviewed metadata: {name}")

        integrity = record.get("tarball_integrity", "")
        hashes = []
        if integrity.startswith("sha512-"):
            raw_hash = base64.b64decode(integrity[7:]).hex()
            hashes.append({"alg": "SHA-512", "content": raw_hash})
        purl = f"pkg:npm/{name}@{version}"
        components.append({
            "name": name,
            "version": version,
            "purl": purl,
            "licenses": licenses,
            "origin": record["url"],
            "paths": paths,
            "scope": "required",
            "hashes": hashes,
            "role": role,
            "extra_properties": [("npm:integrity", integrity)],
        })

    lucide = next((item for item in npm_entries if item["component"] == "lucide-react"), None)
    if lucide:
        components.append({
            "name": "Feather-derived icon shapes embedded by Lucide React",
            "version": f"snapshot carried by lucide-react {lucide['version']}",
            "purl": "pkg:generic/feather-derived-icon-shapes",
            "licenses": "MIT",
            "origin": "https://github.com/feathericons/feather",
            "paths": [main_js[0], f"{ZIP_ROOT}/third-party-notices/Feather-MIT.txt"],
            "scope": "required",
            "role": "Feather-derived icon artwork embedded through Lucide React",
            "extra_properties": [("provenance", f"Lucide React {lucide['version']} license attribution; no separate Feather package version is shipped")],
        })

    component_paths = {path for component in components for path in component["paths"]}
    if any(path not in archive_members for path in component_paths):
        missing = sorted(component_paths - archive_members)
        raise PackageAuditError(f"SBOM path mapping references missing archive paths: {missing}")
    return components


def _runtime_components(archive: ZipFile, root: Path) -> list[dict[str, Any]]:
    lock_path = f"{ZIP_ROOT}/runtime-lock.json"
    try:
        lock = json.loads(archive.read(lock_path).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageAuditError(f"runtime-lock.json is missing or invalid: {exc}") from exc
    runtime = lock.get("runtime")
    wheels = lock.get("wheels")
    if not isinstance(runtime, dict) or not isinstance(wheels, list):
        raise PackageAuditError("runtime-lock.json lacks runtime/wheels arrays for SBOM generation")

    def lock_component(record: dict[str, Any], *, package_type: str, name: str, version: str) -> dict[str, Any]:
        url = record.get("url") or record.get("pypi_json_url") or record.get("origin")
        license_id = record.get("license")
        digest = str(record.get("sha256", "")).lower()
        digest_source = record.get("sha256_source_url") or record.get("sha256_source")
        install_target = record.get("install_target", "")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise PackageAuditError(f"runtime component has no HTTPS origin: {name}")
        if not isinstance(license_id, str) or not license_id:
            raise PackageAuditError(f"runtime component has no license identifier: {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise PackageAuditError(f"runtime component has invalid SHA-256: {name}")
        if not isinstance(digest_source, str) or not digest_source.startswith("https://"):
            raise PackageAuditError(f"runtime component has no digest evidence URL: {name}")
        if package_type == "pypi":
            normalized = re.sub(r"[-_.]+", "-", name).lower()
            purl = f"pkg:pypi/{normalized}@{version}"
        else:
            purl = f"pkg:generic/{name.lower()}@{version}"
        return {
            "name": name,
            "version": version,
            "purl": purl,
            "licenses": license_id,
            "origin": url,
            "paths": [install_target] if install_target else [],
            "scope": "optional",
            "hashes": [{"alg": "SHA-256", "content": digest}],
            "role": record.get("role", "user-provisioned-runtime"),
            "extra_properties": [
                ("provisioned:target", install_target or "runtime/"),
                ("provisioned:format", str(record.get("format", ""))),
                ("provisioned:filename", str(record.get("filename", ""))),
                ("provisioned:sha256-source", digest_source),
                ("provisioned:pypi-json-origin", str(record.get("pypi_json_url", ""))),
            ],
        }

    runtime_version = str(runtime.get("version", ""))
    if not runtime_version:
        raise PackageAuditError("runtime-lock.json has no runtime version")
    result = [lock_component(runtime, package_type="generic", name="CPython", version=runtime_version)]
    for wheel in wheels:
        result.append(lock_component(
            wheel,
            package_type="pypi",
            name=str(wheel.get("name", "")),
            version=str(wheel.get("version", "")),
        ))
    if any(not component["name"] or not component["version"] for component in result):
        raise PackageAuditError("runtime-lock.json includes a wheel with missing name or version")
    return result


def source_inventory_digest(root: Path, config: dict[str, Any]) -> str:
    rows = []
    for source, member in validate_source_inventory(root, config):
        rows.append(f"{member}  {sha256_file(source)}")
    canonical = ("\n".join(sorted(rows)) + "\n").encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def generate_sbom(archive_path: Path, config: dict[str, Any], root: Path = ROOT) -> str:
    with ZipFile(archive_path) as archive:
        members = {info.filename for info in archive.infolist()}
        # Use policy paths, including generated BOM/inventory entries, so base and final ZIPs render identically.
        product_paths = sorted(expected_archive_members(config))
        components = _npm_components(root, members)
        backend_paths = [
            path for path in product_paths
            if path.startswith(f"{ZIP_ROOT}/backend/physis/")
            and "/corpus/" not in path
            and path.endswith(".py")
        ]
        backend_paths.extend([
            f"{ZIP_ROOT}/scripts/serve.py",
            f"{ZIP_ROOT}/scripts/windows_prerequisites.py",
        ])
        components.append({
            "name": "PHYSIS AI Python backend and local server",
            "version": config["release_version"],
            "purl": "pkg:generic/devseat/physis-ai-backend@0.4.1",
            "licenses": "Apache-2.0",
            "origin": "https://github.com/stickleetoto/PHYSIS-AI",
            "paths": backend_paths,
            "scope": "required",
            "role": "first-party production Python modules and local HTTP server",
        })
        components.append({
            "name": "PHYSIS AI frontend",
            "version": config["release_version"],
            "purl": "pkg:generic/devseat/physis-ai-frontend@0.4.1",
            "licenses": "Apache-2.0",
            "origin": "https://github.com/stickleetoto/PHYSIS-AI",
            "paths": [path for path in product_paths if path.startswith(f"{ZIP_ROOT}/frontend/dist/")],
            "scope": "required",
            "role": "first-party compiled browser application",
        })
        components.append({
            "name": "PHYSIS AI Windows distribution support",
            "version": config["release_version"],
            "purl": "pkg:generic/devseat/physis-ai-windows-support@0.4.1",
            "licenses": "Apache-2.0",
            "origin": "https://github.com/stickleetoto/PHYSIS-AI",
            "paths": [
                path for path in product_paths
                if not path.startswith(f"{ZIP_ROOT}/frontend/dist/")
                and not path.startswith(f"{ZIP_ROOT}/backend/physis/")
                and path not in backend_paths
            ],
            "scope": "required",
            "role": "launchers, setup, documentation, and original license notices",
        })
        corpus_paths = [
            f"{ZIP_ROOT}/backend/physis/corpus/{name}"
            for name in ("CC-BY-4.0.txt", "retrieval_queries.json", "selection.json", "units.json", "units.sha256")
        ]
        components.extend([
            {
                "name": "OpenStax College Physics 2e excerpts",
                "version": "84147e8ddbb1a7d2689e235630b230e6b4f20480",
                "purl": "pkg:generic/openstax-college-physics-2e@84147e8ddbb1a7d2689e235630b230e6b4f20480",
                "licenses": "CC-BY-4.0",
                "origin": "https://github.com/openstax/osbooks-college-physics-bundle/tree/84147e8ddbb1a7d2689e235630b230e6b4f20480",
                "paths": corpus_paths + [f"{ZIP_ROOT}/SOURCE_MANIFEST.md"],
                "scope": "required",
                "role": "selected, attributed excerpt source data",
            },
            {
                "name": "OpenStax University Physics volumes 1 and 2 excerpts",
                "version": "9364cbc32511afea3d4695e70a88687ffc1a3696",
                "purl": "pkg:generic/openstax-university-physics@9364cbc32511afea3d4695e70a88687ffc1a3696",
                "licenses": "CC-BY-4.0",
                "origin": "https://github.com/openstax/osbooks-university-physics-bundle/tree/9364cbc32511afea3d4695e70a88687ffc1a3696",
                "paths": corpus_paths + [f"{ZIP_ROOT}/SOURCE_MANIFEST.md"],
                "scope": "required",
                "role": "selected, attributed excerpt source data",
            },
        ])

        # Metadata hashes approved source inputs only; this avoids a ZIP/SBOM checksum cycle.
        source_digest = source_inventory_digest(root, config)
        optional = _runtime_components(archive, root)
    return render_cyclonedx(
        source_inventory_sha256=source_digest,
        components=components,
        optional_components=optional,
        archive_paths=product_paths,
    )


def _validate_frontend_license_provenance(root: Path) -> None:
    try:
        records = json.loads(FRONTEND_LICENSE_AUDIT.read_text(encoding="utf-8"))
        lock = json.loads((root / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PackageAuditError(f"cannot load frontend lock or verified notice metadata: {exc}") from exc
    notice_names = {
        "react": "React-MIT.txt",
        "react-dom": "React-DOM-MIT.txt",
        "scheduler": "Scheduler-MIT.txt",
        "lucide-react": "Lucide-ISC.txt",
    }
    for record in records:
        name = record["component"]
        locked = lock.get("packages", {}).get(f"node_modules/{name}")
        if not isinstance(locked, dict):
            raise PackageAuditError(f"frontend SBOM package is absent from package-lock.json: {name}")
        for field in ("version", "resolved", "integrity", "license"):
            expected = record.get({"resolved": "url", "integrity": "tarball_integrity"}.get(field, field))
            if not expected or locked.get(field) != expected:
                raise PackageAuditError(f"reviewed frontend metadata differs from package-lock.json: {name}.{field}")
        if name in notice_names:
            path = root / "distribution" / "notices" / notice_names[name]
            if not path.is_file() or sha256_file(path) != record["notice_sha256"]:
                raise PackageAuditError(f"reviewed notice does not match npm package metadata: {name}")
        elif name == "katex":
            path = root / "frontend" / "dist" / "licenses" / "KaTeX-MIT.txt"
            if not path.is_file() or sha256_file(path) != record["notice_sha256"]:
                raise PackageAuditError("KaTeX MIT notice differs from reviewed npm package metadata")
        elif name == "vite":
            source = root / "frontend" / "node_modules" / "vite" / "LICENSE.md"
            shipped = root / "distribution" / "notices" / "Vite-MIT.txt"
            if not source.is_file() or not shipped.is_file():
                raise PackageAuditError("Vite modulepreload notice source or copy is missing")
            if sha256_file(source) != record["notice_sha256"]:
                raise PackageAuditError("Vite original license digest differs from reviewed metadata")
            original = source.read_text(encoding="utf-8").split("# Licenses of bundled dependencies", 1)[0].rstrip() + "\n"
            actual = shipped.read_text(encoding="utf-8").replace("\r\n", "\n")
            if actual != original.replace("\r\n", "\n"):
                raise PackageAuditError("Vite core MIT notice is not an exact copy of its original license section")


def audit_release_archive(archive_path: Path, config: dict[str, Any], root: Path = ROOT) -> ArchiveAudit:
    source_inventory = validate_source_inventory(root, config)
    expected_content_sha256 = {member: sha256_file(source) for source, member in source_inventory}
    audit = audit_archive(
        archive_path,
        expected_members=expected_archive_members(config),
        required_members=_required_notice_members(config),
        max_archive_bytes=int(config.get("max_archive_bytes", MAX_ARCHIVE_BYTES)),
        max_uncompressed_bytes=int(config.get("max_uncompressed_bytes", MAX_UNCOMPRESSED_BYTES)),
        expected_content_sha256=expected_content_sha256,
    )
    audit_licensing(archive_path, config)
    _validate_frontend_license_provenance(root)
    # Regeneration from the allowlisted local inputs rejects a rewritten SBOM and forged member hashes.
    expected_sbom = generate_sbom(archive_path, config, root)
    with ZipFile(archive_path) as archive:
        embedded_sbom = archive.read(f"{config['archive_root']}/{SBOM_NAME}").decode("utf-8")
    if embedded_sbom != expected_sbom:
        raise PackageAuditError("embedded CycloneDX SBOM differs from regenerated approved-input SBOM")
    generated = json.loads(embedded_sbom)
    if generated.get("bomFormat") != "CycloneDX" or generated.get("specVersion") != "1.6":
        raise PackageAuditError("generated SBOM is not CycloneDX 1.6")
    return audit


def _write_new(path: Path, content: bytes) -> None:
    try:
        stream = path.open("xb")
    except FileExistsError as exc:
        raise PackageAuditError(f"refusing to replace existing release artifact: {path}") from exc
    try:
        with stream:
            written = stream.write(content)
            if written != len(content):
                raise OSError(f"short write while creating release artifact: {path}")
    except BaseException as exc:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as cleanup_exc:
            if isinstance(exc, Exception):
                raise PackageAuditError(f"could not remove incomplete release artifact: {path}") from cleanup_exc
        raise


def _remove_published_artifacts(paths: Iterable[Path]) -> list[str]:
    failures = []
    for path in reversed(list(paths)):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            failures.append(f"{path}: {exc}")
    return failures


def _publish_artifact_set(artifacts: Iterable[tuple[Path, Path]]) -> list[Path]:
    """Publish staged files without overwriting; remove this operation's outputs on failure."""
    entries = list(artifacts)
    for _staged, destination in entries:
        if destination.exists() or destination.is_symlink():
            raise PackageAuditError(f"refusing to replace existing release artifact: {destination}")

    published: list[Path] = []
    try:
        for staged, destination in entries:
            _write_new(destination, staged.read_bytes())
            published.append(destination)
    except BaseException as exc:
        rollback_failures = _remove_published_artifacts(published)
        if not isinstance(exc, Exception):
            raise
        details = "newly published files were removed" if not rollback_failures else (
            "rollback was incomplete: " + "; ".join(rollback_failures)
        )
        raise PackageAuditError(f"release artifact set publication failed; {details}") from exc
    return published


def build_release(output_dir: Path | None = None, root: Path = ROOT) -> ArchiveAudit:
    config = load_allowlist()
    qa_output = output_dir is not None
    output_dir = Path(output_dir).resolve() if output_dir is not None else RELEASE_DIR.resolve()
    release_dir = RELEASE_DIR.resolve()
    if qa_output and (
        output_dir == release_dir
        or output_dir.is_relative_to(release_dir)
        or release_dir.is_relative_to(output_dir)
    ):
        raise PackageAuditError("QA output directory must be separate from release/ and its parent")
    output_path = output_dir / "PHYSIS-AI-0.4.1-win-x64.zip"
    checksum_path = output_path.parent / CHECKSUM_NAME
    sbom_path = output_path.parent / SBOM_NAME
    for path in (output_path, checksum_path, sbom_path):
        if path.exists() or path.is_symlink():
            raise PackageAuditError(f"refusing to replace existing release artifact: {path}")
    inventory = validate_source_inventory(root, config)
    _validate_frontend_license_provenance(root)
    payload: dict[str, bytes] = {}
    for source, member in inventory:
        payload[member] = source.read_bytes()

    output_dir.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    try:
        with tempfile.TemporaryDirectory(prefix="physis-package-work-", dir=output_dir) as scratch:
            scratch_dir = Path(scratch)
            base_archive = scratch_dir / "approved-inputs.zip"
            candidate = scratch_dir / output_path.name
            build_deterministic_zip(base_archive, payload)
            sbom_text = generate_sbom(base_archive, config, root)
            payload[f"{ZIP_ROOT}/{SBOM_NAME}"] = sbom_text.encode("utf-8")
            payload[f"{ZIP_ROOT}/{CHECKSUM_NAME}"] = render_internal_sha256s(payload)
            build_deterministic_zip(candidate, payload)
            result = audit_release_archive(candidate, config, root)

            checksum_stage = scratch_dir / CHECKSUM_NAME
            sbom_stage = scratch_dir / SBOM_NAME
            checksum_stage.write_bytes(render_sha256_sums(candidate).encode("utf-8"))
            sbom_stage.write_bytes(sbom_text.encode("utf-8"))
            verify_sidecars(candidate, config, root)

            # The ZIP is published last as the completion marker for the staged sidecar set.
            published = _publish_artifact_set([
                (checksum_stage, checksum_path),
                (sbom_stage, sbom_path),
                (candidate, output_path),
            ])

        final_audit = audit_release_archive(output_path, config, root)
        verify_sidecars(output_path, config, root)
        if final_audit.sha256 != result.sha256:
            raise PackageAuditError("published ZIP hash changed during finalization")
        return final_audit
    except BaseException as exc:
        if published:
            rollback_failures = _remove_published_artifacts(published)
            if rollback_failures and isinstance(exc, Exception):
                raise PackageAuditError(
                    "post-publish verification failed and rollback was incomplete: " + "; ".join(rollback_failures)
                ) from exc
        raise


def verify_sidecars(archive_path: Path, config: dict[str, Any], root: Path = ROOT) -> tuple[Path, Path]:
    checksum_path = archive_path.parent / CHECKSUM_NAME
    sbom_path = archive_path.parent / SBOM_NAME
    checksum = render_sha256_sums(archive_path)
    sbom = generate_sbom(archive_path, config, root)
    if not checksum_path.is_file() or not sbom_path.is_file():
        raise PackageAuditError("release sidecars SHA256SUMS.txt and sbom.cdx.json are both required")
    if checksum_path.read_text(encoding="utf-8") != checksum:
        raise PackageAuditError(f"SHA256SUMS.txt does not match {archive_path.name}")
    if sbom_path.read_text(encoding="utf-8") != sbom:
        raise PackageAuditError("sbom.cdx.json does not match the embedded BOM and runtime lock")
    with ZipFile(archive_path) as archive:
        if archive.read(f"{ZIP_ROOT}/{SBOM_NAME}") != sbom_path.read_bytes():
            raise PackageAuditError("sidecar SBOM is not byte-identical to the BOM embedded in the ZIP")
    return checksum_path, sbom_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and independently audit PHYSIS AI 0.4.1 Windows ZIPs.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build", help="build the exact release ZIP, checksum, and CycloneDX SBOM")
    build_parser.add_argument("--output-dir", type=Path, help="separate directory for a local QA candidate")
    audit_parser = subparsers.add_parser("audit", help="audit a final ZIP and verify its internal and external manifests")
    audit_parser.add_argument("archive", type=Path)
    args = parser.parse_args(argv)

    try:
        if args.command == "build":
            result = build_release(args.output_dir)
            zip_path = (args.output_dir.resolve() if args.output_dir else RELEASE_DIR.resolve()) / "PHYSIS-AI-0.4.1-win-x64.zip"
            print(f"PASS ZIP: {zip_path}")
            print(f"PASS SHA-256: {result.sha256}")
            print(f"PASS inventory: {len(result.members)} approved files; {result.archive_bytes} compressed bytes")
            print(f"PASS sidecars: {zip_path.parent / CHECKSUM_NAME}; {zip_path.parent / SBOM_NAME}")
            return 0

        config = load_allowlist()
        archive_path = args.archive.resolve()
        result = audit_release_archive(archive_path, config)
        checksum_path, sbom_path = verify_sidecars(archive_path, config)
        print(f"PASS ZIP audit: {archive_path}")
        print(f"PASS CRC and allowlist: {len(result.members)} approved files; {result.archive_bytes} compressed bytes")
        print(f"PASS SHA-256: {result.sha256} ({checksum_path.name})")
        print(f"PASS CycloneDX 1.6 SBOM: {sbom_path}")
        return 0
    except (PackageAuditError, OSError, ValueError, KeyError, TypeError, BadZipFile) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
