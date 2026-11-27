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

The historical v0.4 runtime ZIP remains local. Its three Microsoft DLLs matched the official CPython 3.13.4 embed archive or the official NumPy 2.3.5 CPython 3.13 x64 wheel, byte for byte. Their Windows Authenticode signatures validated. DevSeat’s entitlement to redistribute those DLLs directly was not established. The v0.4.1 PHYSIS ZIP contains zero DLLs. [DLL versions, signatures, hashes, upstream files and direct importers](https://github.com/stickleetoto/PHYSIS-AI/blob/v0.4.1/distribution/audit/v040-microsoft-dlls.json) · [Microsoft redistribution terms](https://learn.microsoft.com/cpp/windows/redistributing-visual-cpp-files)

The release includes compiled React and React DOM, Scheduler, Lucide icons (including Feather portions), KaTeX code and unmodified KaTeX fonts, and Vite’s client-side preload code. The ZIP preserves their notices in `third-party-notices/` and `frontend/dist/licenses/`. Permissions include MIT for React, React DOM, Scheduler, Feather, KaTeX code and Vite, ISC for the Lucide portions, and OFL-1.1 for the fonts. The upstream npm tarballs for six packages were compared with their lockfile integrity values and installed license files. [Upstream package evidence](https://github.com/stickleetoto/PHYSIS-AI/blob/v0.4.1/distribution/audit/frontend-licenses.json) · [Feather license](https://github.com/feathericons/feather/blob/1b002399e8758fb2bccea4d07312dc9e0f43dcb8/LICENSE)

At the user’s request, setup downloads CPython directly from Python.org and the pinned wheels from PyPI’s distribution host. The upstream archives supply their own licenses and DLLs. The Python Software Foundation license and CPython’s component notices travel with the interpreter. NumPy and SciPy carry additional notices for their binary components, including OpenBLAS, LAPACK and the GCC runtime exception. Certifi’s CA bundle retains MPL-2.0. A recipient making a new distribution containing those installed files must review those upstream terms. The ZIP’s component inventory distinguishes shipped files from downloads initiated during setup. [Source manifest](SOURCE_MANIFEST.md) · [Windows instructions](WINDOWS_DISTRIBUTION.md) · [Official Microsoft runtime downloads](https://learn.microsoft.com/cpp/windows/latest-supported-vc-redist/)
