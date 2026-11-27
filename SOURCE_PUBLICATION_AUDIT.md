# v0.4 source publication review

This review covers the Git history reachable from the public branches and tags. The archived Windows distribution is a separate artifact. Checks used local files, Git objects, Gitleaks 8.30.1 and the upstream rights records. No model inference was used.

## Investigated secret-scanner findings

The full-history scan used `gitleaks git --log-opts="--all --full-history" --redact=100 .` with the default rules. All 28 detections were introduced in commit `020fb63c6ddc2c24ee736b8debf24d128539617a`. Every finding used the `generic-api-key` rule. The table gives the line numbers in that commit.

| File under `release/` | Lines |
|---|---|
| benchmark-v031-mock-heldout-24-graded.json | 57, 66, 86, 91 |
| benchmark-v031-mock-heldout-24.json | 57, 66, 86, 91 |
| benchmark-v031-regression72.json | 9, 18, 38, 43 |
| benchmark-v3-final.json | 8, 14, 33, 38 |
| benchmark-v3-release-replay.json | 8, 14, 33, 38 |
| product-freeze-v031.json | 7, 21, 41, 46 |
| software-v032/product-freeze.json | 8, 26, 46, 51 |

Each file has four flagged values. The keys are source paths under `backend/physis/` for `api.py`, `knowledge_api.py`, `science_api.py` and `study_api.py`. Each value is a 64-digit hexadecimal digest in a `code_sha256` or `files` manifest. The benchmark writer hashes source bytes with SHA-256. The records were checked against archived source hashes or, for intermediate builds, the preserved report and its hash-producing code. No scan rule was disabled and no allowlist was introduced. [Benchmark writer](scripts/benchmark_v3.py)

## Privacy and artifact review

- Enumerated each commit tree, inspected distinct blob contents and paths, and checked commit and annotated-tag metadata. Checks covered API credentials, private key material, email addresses, home directories, identification and phone number patterns, private IPs, databases, binary packages, model files and unexpected large files.
- All commit contact addresses examined were GitHub noreply addresses. A historical Replay fixture receipt references a local evaluation directory. It contains a project path and record digest. Its companion fixture is a short, normalized benchmark answer about SI units. Neither contains an individual’s identity, authentication data or a raw request log. The tracked JSONL files contain educational evaluation cases or curated Replay examples.
- The seven tracked PNGs show the application running with example inputs. They were checked visually and inspected for embedded text and EXIF metadata. Historical verification reports may refer to local artifacts by name.
- The OpenStax license files and book metadata at the two pinned upstream revisions matched the recorded hashes. Each of the 116 excerpt hashes and the corpus digest were checked. The three NASA records are metadata-only. [Rights and attribution](SOURCE_MANIFEST.md)
- The public source tree excludes model weights, installed dependencies, bundled runtimes, personal learning data, raw provider logs and local distribution ZIPs. The Windows archive remains on hold. [Windows distribution review](THIRD_PARTY_NOTICES.md#windows-binaries)

These checks found no publication-blocking credential or private user record in the examined source history. They do not measure model accuracy or student learning.
