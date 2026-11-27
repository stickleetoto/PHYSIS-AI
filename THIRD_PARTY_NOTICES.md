# Third-party notices

Copyright 2026 DevSeat applies to DevSeat’s original PHYSIS AI work. The Apache-2.0 grant covers that work. The following materials retain their own authorship, license and distribution terms. [Project license](LICENSE) · [Attribution notice](NOTICE)

## Material in the source repository

| Material | Rights holder or attribution | Terms and scope |
|---|---|---|
| College Physics 2e | OpenStax, Rice University. Paul Peter Urone, Roger Hinrichs and contributors | CC BY 4.0 for the selected prose from the recorded edition. 29 sections. |
| University Physics Volumes 1 and 2 | OpenStax, Rice University. Samuel J. Ling, Jeff Sanny, William Moebs and contributors | CC BY 4.0 for the selected prose from the recorded editions. 13 sections in volume 1 and 4 in volume 2. |
| NASA Glenn and NASA Technical Reports Server | NASA Glenn and the authors credited in the manifest | Three bibliographic records with links. The repository includes no NASA article text, abstract, images, logo or PDF from these records. |
| KaTeX notices | Khan Academy and other contributors (code). Design Science, Inc. and Khan Academy (fonts) | KaTeX code uses MIT. Its fonts use SIL OFL 1.1, with reserved font names. The public source tree includes the original notices. The web build obtains the package through npm. |

The corpus contains 116 English excerpts. PHYSIS selected passages, normalized whitespace, converted simple inline notation to text and added search annotations. Each excerpt has a source locator and digest. External photos, figures and tables are excluded. The source manifest records attribution, modifications and the exact upstream revisions. [Source manifest](SOURCE_MANIFEST.md) · [CC BY 4.0 text](backend/physis/corpus/CC-BY-4.0.txt) · [College Physics license at the imported revision](https://github.com/openstax/osbooks-college-physics-bundle/blob/84147e8ddbb1a7d2689e235630b230e6b4f20480/LICENSE) · [University Physics license at the imported revision](https://github.com/openstax/osbooks-university-physics-bundle/blob/9364cbc32511afea3d4695e70a88687ffc1a3696/LICENSE)

The font notice includes the reserved names and the full OFL text. Both notices are copied into the frontend by the build. [KaTeX MIT notice](frontend/public/licenses/KaTeX-MIT.txt) · [KaTeX font notice](frontend/public/licenses/KaTeX-fonts-OFL-1.1.txt)

## Dependencies installed by the user

The source tag includes dependency declarations and the npm lockfile. The license review covered the npm lockfile and license metadata and notices of the 23 Python distributions used in the v0.4 Windows verification. Installed copies remain subject to their upstream terms. [Python requirements](requirements.txt) · [Frontend lockfile](frontend/package-lock.json)

| Components | Upstream licensing |
|---|---|
| React, React DOM, Scheduler, KaTeX code and Commander | MIT. React packages credit Meta Platforms, Inc. and affiliates. KaTeX credits Khan Academy and contributors. |
| Lucide React | ISC for Lucide contributors’ work. The upstream notice credits Cole Bemis for Feather-derived portions under MIT. |
| FastAPI, Pydantic, pydantic-core, annotated-doc, annotated-types, typing-inspection, anyio and h11 | MIT |
| Starlette, Uvicorn, HTTPX, httpcore, Click, idna, python-dotenv and pypdf | BSD-3-Clause |
| SymPy, mpmath, NumPy and SciPy | BSD-family project licenses. NumPy and SciPy wheels carry additional notices for bundled code. |
| typing_extensions | PSF-2.0 |
| OpenTelemetry API | Apache-2.0 |
| certifi | MPL-2.0 for the CA bundle and covered files |

Development dependencies in the npm lockfile declare MIT, ISC, Apache-2.0, BSD-3-Clause and CC-BY-4.0 (caniuse-lite data). Their notices travel with the installed packages. Using these dependencies in the source setup preserves their own terms.

## Windows binaries

The public v0.4 source release has no Windows binary attachment. The historical local ZIP contains a CPython runtime, including Microsoft C++ DLLs, and binary wheels. The PSF distribution has component-specific notices. The NumPy and SciPy wheels identify OpenBLAS, LAPACK and the GCC runtime with its runtime library exception. The Windows ZIP also contains raw inference evaluation logs. The original archive is retained locally.

Before distributing a replacement, remove the raw logs, verify redistribution rights and provenance for each Microsoft DLL, collect the actual runtime, wheel and frontend notices, and repeat the archive and offline launch checks. One alternative under consideration is to direct Windows users to Microsoft’s official x64 runtime installer and validate the resulting dependency loading on a clean system. That configuration has not been tested. [Microsoft redistribution terms](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files?view=msvc-170) · [Official supported runtime downloads](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170)
