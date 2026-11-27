# Windows distribution audit · v0.4.1

## Scope and release artifacts

The Windows distribution is built from the v0.4 source baseline `dcdae00843472b88e97806cb988d4abcded5f3db`. It ships the built web interface and a user-initiated runtime setup. Physics, mathematics and tutor behavior retain the v0.4 coverage. The initial setup needs internet access and write permission to the extracted directory. [User guide](WINDOWS_DISTRIBUTION.md)

## Security and privacy

The historical packager included reports by filename patterns. Its v0.4 ZIP contained 61 files under `release/`, including a raw evaluation record containing dialogue and provider request data. That ZIP stays local. v0.4.1 selects production modules, static assets, educational data, setup and notice files through an explicit inventory. Evaluation reports, raw requests, user databases, settings, development tools, runtime binaries and wheels are outside the ZIP inventory. No historical archive is used as a packaging input.

The repository's four v0.4 commits and two tags were reviewed for its source publication. This release adds an automated check that reconciles only those exact 28 source-digest findings in the original import commit, by rule, path, line, field and value type. The Windows ZIP is scanned separately. [Original findings](SOURCE_PUBLICATION_AUDIT.md) · [CI checks](.github/workflows/windows-distribution.yml)

## Microsoft DLLs and third-party rights

The preserved v0.4 ZIP contained 12 DLLs. Three were Microsoft runtime libraries. All 163 PE executables, DLLs and extension modules in that archive were inspected for direct and delay-load imports. All three DLL hashes matched their corresponding files in the official CPython or NumPy archive. Windows Authenticode reported a valid Microsoft signature on each. The version and full hash, signer, certificate thumbprint, timestamp signer, original archive and importing binaries are recorded separately. [Per-file evidence](distribution/audit/v040-microsoft-dlls.json)

| Microsoft DLL in v0.4 | File version | Direct importers | Reason it was present |
|---|---|---:|---|
| vcruntime140.dll | 14.42.34438.0 | 49 | MSVC runtime for the interpreter and native extensions |
| vcruntime140_1.dll | 14.42.34438.0 | 4 | x64 exception-handling runtime required by native modules |
| msvcp140-a4c2229bdc2a2a630acdc095b4d86008.dll | 14.40.33810.0 | 2 | NumPy wheel’s renamed C++ library for its multiarray and FFT extensions |

Microsoft's terms govern its distributable code. A valid signature establishes provenance. No DevSeat right to ship those DLLs directly has been established, so the release omits all three. Setup obtains official archives directly from the publishers at the user’s request. The upstream DLLs may therefore appear in the installed runtime. Missing system prerequisites are directed to Microsoft’s official installer. [Microsoft redistribution guidance](https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files) · [Supported Microsoft downloads](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist/)

The app’s original work is Apache-2.0. Bundled frontend code, icons and fonts preserve MIT, ISC and OFL notices. The six frontend package tarballs matched the integrity values in the npm lockfile, and their license files matched upstream. The local corpus contains 116 OpenStax excerpts under CC BY 4.0 and three NASA metadata records. The user-provisioned Python interpreter, its binary wheels and their bundled dependencies retain upstream terms. [Third-party notices](THIRD_PARTY_NOTICES.md) · [Frontend package review](distribution/audit/frontend-licenses.json) · [OpenStax attribution and editions](SOURCE_MANIFEST.md)

The setup uses CPython 3.14.10 x64. The final official 3.13 Windows embed predates the 3.13.18 security fixes, which were released as source only. The 3.14.10 Windows build includes the compromised-CA fix. The source setup remains compatible with Python 3.13. [Python security release](https://www.python.org/downloads/release/python-31410/) The embeddable ZIP hash `90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159` matches Python.org’s published SPDX checksum. This Python archive supplies two app-local VCRuntime DLLs; the NumPy wheel separately supplies its renamed MSVCP DLL. The PHYSIS release does not mirror those archives. [Python.org SPDX record](https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip.spdx.json)

The installed 3.14.10 runtime contained 12 DLLs, including three signed Microsoft DLLs. Each matched its upstream archive member. A scan of 165 installed PE files recorded direct and delay-load dependencies, with no parsing failures. [Per-DLL license, signature, origin and dependency records](distribution/audit/v041-provisioned-microsoft-dlls.json)

## Build and verification

Run `npm ci` and `npm run build` in `frontend/`. From the repository root run `python scripts/package_windows.py build`, then `python scripts/package_windows.py audit release/PHYSIS-AI-0.4.1-win-x64.zip`. The npm lockfile pins build dependencies. The runtime lock records official download filenames, URLs, versions and digests. The package checksum applies to the ZIP as downloaded. Setup verifies the separately obtained runtime files before installing them.

The CI workflow runs tests and inspections with read-only repository permissions. Publishing a release is a separate manual operation. The local development environment used Windows 11 x64 build 26200, Python 3.13.4, Node.js 24.18.0, npm 11.16.0 and Vite 7.3.8. The app’s provisioned interpreter version is independent of this build interpreter. Real LLM calls, training, GPU computation and model downloads were excluded throughout.

The final dependency lock was checked against the official CPython checksum and PyPI release records. All 23 wheels satisfy the Python 3.14 Windows dependency graph. All 23 corresponding versions were also present in the isolated backend test environment. The Python advisory feed and OSV’s npm query returned no active entries for the checked versions at the time of review. This is a dated check of published advisories. It follows updates to KaTeX, python-dotenv, pypdf and selected transitive packages. All 60 KaTeX font files matched the previous version. [Dependency verification record](distribution/audit/runtime-metadata.json) · [Executable check](scripts/verify_runtime_lock.py)

The local backend suite passed 571 tests (two upstream deprecation warnings); the frontend passed 32 tests in one worker. The TypeScript check and Vite production build passed with KaTeX 0.18.2. An initial red test for the previous health version passed after the launcher and health response adopted 0.4.1.

The provisioned ZIP also passed seven end-to-end tests in Microsoft Edge. They exercised all 27 formulas, symbolic calculations, mathematics exports, Physics Bridge, Mock conversation revisions and physics CSV export. The server ran with a Windows-only PATH and offline mode, and the browser ran headless with GPU and WebGL disabled. The report names each test and identifies the tested ZIP by its SHA-256. [Application verification](distribution/audit/application-verification.json)

## Windows execution and archive inspection

On Windows 11 x64 build 26200, a non-elevated account extracted the ZIP under a path containing Hangul and spaces. The first launch displayed setup instructions. Explicit setup provisioned CPython 3.14.10 and 23 wheels. With system Python and Node.js absent from PATH, NumPy and SciPy solved a linear system. The offline service returned a free-fall result, a symbolic derivative and a Mock Tutor response. Both a foreign port owner and an existing PHYSIS instance survived a second launch. Ctrl+C and Ctrl+Break produced a graceful server shutdown. After restarting on the same port, the stored experiment retained its ID, parameters and revision. Windows Command Prompt can ask for Y to finish the batch file after the server stops. [12 Windows checks and their results](distribution/audit/windows-smoke.json)

이 PC에는 시스템 VC 런타임이 설치되어 있었습니다. 실제 최초 실행에서 앱 전용 Python의 부재를 확인했고, VC 런타임 누락 안내는 빈 시스템·앱 폴더로 모의 시험했습니다. 새로 설치한 일반 사용자용 Windows에서의 동작과 기본 브라우저 연결을 직접 클릭하는 과정은 미검증입니다.

| Public ZIP | Verified value |
|---|---|
| Filename | `PHYSIS-AI-0.4.1-win-x64.zip` |
| Size | 1,443,851 bytes compressed, 2,954,839 bytes extracted |
| SHA-256 | `6ae18c6f6b8c6ece1d4b3d1909175a8e0c18386a1f5874e4be81ead2738572a1` |
| Contents | 154 approved files and 36 CycloneDX inventory components, including separately provisioned dependencies |
| Security inspection | Gitleaks 8.30.1 reported zero findings in the extracted ZIP. File inventory, sizes, internal hashes, source-content comparison and ZIP CRC checks passed. |
| Excluded material | Zero native binaries, wheel archives, raw evaluation records, conversations or user databases |

Rebuilding the release produced the same ZIP digest as the Windows and browser trials. The complete package regression suite passed 21 tests. A separate Windows check created an NTFS directory junction inside a disposable fixture and confirmed that the packager rejected its use as a source directory. The external CycloneDX SBOM passed the official 1.6 schema and matched the embedded SBOM byte for byte. All seven previous Windows archives still matched their recorded SHA-256 digests.
