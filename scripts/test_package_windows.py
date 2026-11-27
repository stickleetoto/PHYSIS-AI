from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from package_windows import (
    PackageAuditError,
    audit_archive,
    audit_release_archive,
    build_release,
    build_deterministic_zip,
    load_allowlist,
    render_cyclonedx,
    render_internal_sha256s,
    verify_sidecars,
    validate_source_inventory,
)
import package_windows as packager


ROOT = "PHYSIS-AI/"


def test_portable_interpreter_checks_file_identity(tmp_path, monkeypatch):
    import serve

    lock = tmp_path / "runtime-lock.json"
    lock.write_text(json.dumps({
        "product": {"version": serve.VERSION},
        "runtime": {"architecture": "win-amd64", "version": ".".join(map(str, sys.version_info[:3]))},
        "installation": {"python_executable": "runtime/python.exe"},
    }), encoding="utf-8")
    expected = tmp_path / "python.exe"
    expected.write_bytes(b"test file")
    alias = tmp_path / "alias.exe"
    alias.hardlink_to(expected)
    monkeypatch.setattr(serve, "PACKAGE_LOCK", lock)
    monkeypatch.setattr(serve, "PORTABLE_RUNTIME", expected)
    monkeypatch.setattr(sys, "executable", str(alias))
    serve.validate_portable_runtime()

    other = tmp_path / "other.exe"
    other.write_bytes(expected.read_bytes())
    monkeypatch.setattr(sys, "executable", str(other))
    with pytest.raises(SystemExit, match="must be started with its runtime"):
        serve.validate_portable_runtime()


def _minimal_source_inventory(root: Path) -> dict[str, object]:
    (root / "backend" / "physis").mkdir(parents=True)
    (root / "backend" / "physis" / "module.py").write_text("value = 1\n", encoding="utf-8")
    (root / "frontend" / "dist" / "assets").mkdir(parents=True)
    (root / "frontend" / "dist" / "assets" / "app.js").write_text("const app = true;\n", encoding="utf-8")
    return {
        "fixed_files": [],
        "production_modules": ["module.py"],
        "frontend_dist": ["assets/app.js"],
    }


def _zip(path: Path, files: dict[str, bytes]) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def test_audit_accepts_the_exact_approved_inventory(tmp_path: Path) -> None:
    candidate = tmp_path / "valid.zip"
    files = {
        ROOT + "README.txt": b"PHYSIS AI user guide\n",
        ROOT + "Start-PHYSIS.cmd": b"@echo off\r\n",
    }
    _zip(candidate, files)

    result = audit_archive(candidate, expected_members=set(files))

    assert result.members == tuple(sorted(files))
    assert result.sha256


def test_audit_rejects_an_unapproved_member(tmp_path: Path) -> None:
    candidate = tmp_path / "extra.zip"
    files = {ROOT + "README.txt": b"guide", ROOT + "release/private.json": b"{}"}
    _zip(candidate, files)

    with pytest.raises(PackageAuditError, match="unexpected"):
        audit_archive(candidate, expected_members={ROOT + "README.txt"})


def test_audit_rejects_missing_approved_members(tmp_path: Path) -> None:
    candidate = tmp_path / "missing.zip"
    _zip(candidate, {ROOT + "README.txt": b"guide"})

    with pytest.raises(PackageAuditError, match="missing"):
        audit_archive(candidate, expected_members={ROOT + "README.txt", ROOT + "LICENSE"})


def test_audit_rejects_traversal_path(tmp_path: Path) -> None:
    candidate = tmp_path / "traversal.zip"
    member = ROOT + "../outside.txt"
    _zip(candidate, {member: b"escape"})

    with pytest.raises(PackageAuditError, match="invalid ZIP path"):
        audit_archive(candidate, expected_members={member})


@pytest.mark.parametrize("name", ["runtime/python.exe", "runtime/python313.dll", "backend/physis/native.pyd", "cache/dependency.whl"])
def test_audit_rejects_runtime_and_native_payloads_even_if_listed(tmp_path: Path, name: str) -> None:
    candidate = tmp_path / "forbidden.zip"
    member = ROOT + name
    _zip(candidate, {member: b"not a real binary"})

    with pytest.raises(PackageAuditError, match="prohibited"):
        audit_archive(candidate, expected_members={member})


def _secret_markers() -> list[bytes]:
    return [
        b"-----BEGIN " + b"PRIVATE KEY" + b"-----",
        b"AKIA" + b"1234567890ABCDEF",
        b"sk-" + b"proj-" + b"abcdefghijklmnopqrstuvwxyz012345",
    ]


@pytest.mark.parametrize("secret", _secret_markers())
def test_audit_rejects_secret_markers_in_text_files(tmp_path: Path, secret: bytes) -> None:
    candidate = tmp_path / "secret.zip"
    member = ROOT + "README.txt"
    _zip(candidate, {member: b"safe intro\n" + secret})

    with pytest.raises(PackageAuditError, match="secret"):
        audit_archive(candidate, expected_members={member})


def test_deterministic_zip_writer_emits_identical_bytes(tmp_path: Path) -> None:
    files = {"PHYSIS-AI/LICENSE": b"license\n", "PHYSIS-AI/README.txt": b"readme\n"}
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"

    build_deterministic_zip(first, files)
    build_deterministic_zip(second, files)

    assert first.read_bytes() == second.read_bytes()


def test_internal_inventory_covers_every_member_except_itself(tmp_path: Path) -> None:
    candidate = tmp_path / "inventory.zip"
    files = {
        ROOT + "README.txt": b"guide\n",
        ROOT + "Start-PHYSIS.cmd": b"@echo off\n",
    }
    files[ROOT + "SHA256SUMS.txt"] = render_internal_sha256s(files)
    _zip(candidate, files)

    result = audit_archive(candidate, expected_members=set(files))

    assert set(result.members) == set(files)


def test_tampered_allowed_file_fails_even_with_a_forged_internal_inventory(tmp_path: Path) -> None:
    candidate = tmp_path / "forged-inventory.zip"
    member = ROOT + "README.txt"
    approved = b"reviewed source README\n"
    files = {member: b"tampered README\n", ROOT + "Start-PHYSIS.cmd": b"@echo off\n"}
    files[ROOT + "SHA256SUMS.txt"] = render_internal_sha256s(files)
    _zip(candidate, files)

    with pytest.raises(PackageAuditError, match="differs from approved local input"):
        audit_archive(
            candidate,
            expected_members=set(files),
            expected_content_sha256={member: hashlib.sha256(approved).hexdigest()},
        )


def test_audit_rejects_crc_tampering(tmp_path: Path) -> None:
    candidate = tmp_path / "bad-crc.zip"
    member = ROOT + "README.txt"
    with ZipFile(candidate, "w", ZIP_STORED) as archive:
        archive.writestr(member, b"guide")
    candidate.write_bytes(candidate.read_bytes().replace(b"guide", b"guida", 1))

    with pytest.raises(PackageAuditError, match="CRC"):
        audit_archive(candidate, expected_members={member})


@pytest.mark.parametrize("reparse_location", ["allowlisted-ancestor", "unlisted-nested-entry"])
def test_source_inventory_rejects_directory_reparse_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reparse_location: str
) -> None:
    root = tmp_path / "project"
    config = _minimal_source_inventory(root)
    if reparse_location == "allowlisted-ancestor":
        reparse_path = root / "backend" / "physis"
    else:
        reparse_path = root / "frontend" / "dist" / "private-cache"
        reparse_path.mkdir()

    original_lstat = Path.lstat

    def lstat_with_windows_reparse_attribute(path: Path):
        result = original_lstat(path)
        if path == reparse_path:
            return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400)
        return result

    monkeypatch.setattr(Path, "lstat", lstat_with_windows_reparse_attribute)

    with pytest.raises(PackageAuditError, match="reparse"):
        validate_source_inventory(root, config)


def test_build_release_rolls_back_new_artifacts_when_a_sidecar_write_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "source"
    source = root / "README.md"
    root.mkdir()
    source.write_text("reviewed input\n", encoding="utf-8")
    output_dir = tmp_path / "qa-output"
    config = {
        "schema_version": 1,
        "release_version": "0.4.1",
        "archive_root": "PHYSIS-AI",
        "fixed_files": [{"source": "README.md", "path": "README.txt"}],
        "production_modules": [],
        "frontend_dist": [],
        "generated_files": ["SHA256SUMS.txt", "sbom.cdx.json"],
    }

    monkeypatch.setattr(packager, "load_allowlist", lambda: config)
    monkeypatch.setattr(packager, "validate_source_inventory", lambda *_args: [(source, "PHYSIS-AI/README.txt")])
    monkeypatch.setattr(packager, "_validate_frontend_license_provenance", lambda *_args: None)
    monkeypatch.setattr(packager, "generate_sbom", lambda *_args: "{}\n")
    monkeypatch.setattr(packager, "audit_release_archive", lambda *_args: None)
    monkeypatch.setattr(packager, "verify_sidecars", lambda *_args: (None, None))

    def write_small_candidate(path: Path, _files: dict[str, bytes]) -> None:
        path.write_bytes(b"candidate archive bytes")

    monkeypatch.setattr(packager, "build_deterministic_zip", write_small_candidate)
    original_write_new = packager._write_new

    def fail_sbom_sidecar(path: Path, content: bytes) -> None:
        if path == output_dir / "sbom.cdx.json":
            raise OSError("simulated disk full")
        original_write_new(path, content)

    monkeypatch.setattr(packager, "_write_new", fail_sbom_sidecar)

    with pytest.raises(PackageAuditError):
        packager.build_release(output_dir, root=root)

    assert not (output_dir / "PHYSIS-AI-0.4.1-win-x64.zip").exists()
    assert not (output_dir / "SHA256SUMS.txt").exists()
    assert not (output_dir / "sbom.cdx.json").exists()


def test_sbom_lists_optional_installed_runtime_separately_from_archive_components() -> None:
    sbom = render_cyclonedx(
        source_inventory_sha256="a" * 64,
        components=[{
            "name": "React", "version": "19.3.1", "purl": "pkg:npm/react@19.3.1",
            "licenses": "MIT", "origin": "https://registry.npmjs.org/react/-/react-19.3.1.tgz",
            "paths": ["PHYSIS-AI/frontend/dist/assets/index-abc.js"], "scope": "required",
        }],
        optional_components=[{
            "name": "CPython", "version": "3.13.17", "purl": "pkg:generic/cpython@3.13.17",
            "licenses": "PSF-2.0", "origin": "https://www.python.org/ftp/python/3.13.17/",
            "paths": ["runtime/python.exe"], "scope": "optional",
        }],
    )

    parsed = json.loads(sbom)
    assert parsed["bomFormat"] == "CycloneDX"
    assert parsed["specVersion"] == "1.6"
    assert {component["name"] for component in parsed["components"]} == {"React", "CPython"}
    runtime = next(component for component in parsed["components"] if component["name"] == "CPython")
    assert runtime["scope"] == "optional"
    assert runtime["properties"][-1]["value"] == "provisioned-after-extraction"


def test_sbom_uses_cyclonedx_spdx_expression_shape_and_rejects_unknown_license_ids() -> None:
    sbom = json.loads(render_cyclonedx(
        source_inventory_sha256="b" * 64,
        components=[{
            "name": "Example", "version": "1.0", "purl": "pkg:generic/example@1.0",
            "licenses": "MIT OR BSD-3-Clause", "origin": "https://example.invalid/source",
            "paths": [],
        }],
        optional_components=[],
    ))

    assert sbom["components"][0]["licenses"] == [{"expression": "MIT OR BSD-3-Clause"}]
    with pytest.raises(PackageAuditError, match="unknown SPDX"):
        render_cyclonedx(
            source_inventory_sha256="b" * 64,
            components=[{
                "name": "Example", "version": "1.0", "purl": "pkg:generic/example@1.0",
                "licenses": "Made-Up-License", "origin": "https://example.invalid/source",
                "paths": [],
            }],
            optional_components=[],
        )


def test_local_qa_build_self_audits_and_rejects_tampered_allowed_bytes_with_forged_inventory(tmp_path: Path) -> None:
    qa_dir = tmp_path / "physis-qa"
    result = build_release(qa_dir)
    candidate = qa_dir / "PHYSIS-AI-0.4.1-win-x64.zip"
    config = load_allowlist()

    assert result.archive_bytes == candidate.stat().st_size
    verify_sidecars(candidate, config)
    with ZipFile(candidate) as archive:
        files = {entry.filename: archive.read(entry) for entry in archive.infolist()}

    readme = ROOT + "README.txt"
    files[readme] += b"tampered\n"
    files[ROOT + "SHA256SUMS.txt"] = render_internal_sha256s(files)
    build_deterministic_zip(candidate, files)

    with pytest.raises(PackageAuditError, match="differs from approved local input"):
        audit_release_archive(candidate, config)
