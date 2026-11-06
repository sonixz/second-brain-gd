# Third-party notices

Second Brain GD is built on the work of others. This file lists what the app and its packages contain or download,
and under which licences. Every package carries the full licence texts: `LICENSES/godot.txt` (Godot and the
components it bundles), `python/LICENSE.txt` (CPython), and each Python package's `*.dist-info` folder.

## In the app
| Component | Version | Licence | Notes |
|---|---|---|---|
| Godot Engine | 4.7.2 | MIT | With its own third-party components (FreeType, HarfBuzz, ICU, libpng, mbedTLS, zstd…), listed in `LICENSES/godot.txt`. |

## In the package's Python (`python/`)
| Component | Version | Licence |
|---|---|---|
| CPython (python-build-standalone build) | 3.12.15 | PSF License 2.0, with the licences of the libraries it is built with (OpenSSL, SQLite, zlib, bzip2, xz, libffi…) in `python/LICENSE.txt` |
| fastapi | 0.115.12 | MIT |
| starlette | 0.46.2 | BSD-3-Clause |
| uvicorn | 0.34.2 | BSD-3-Clause |
| click | 8.5.0 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| anyio | 4.16.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| pydantic | 2.14.2 | MIT |
| pydantic-core | 2.50.2 | MIT |
| annotated-types | 0.8.0 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| psutil | 7.0.0 | BSD-3-Clause |
| websockets | 15.0.1 | BSD-3-Clause |
| pypdfium2 (with PDFium) | 4.30.0 | Apache-2.0 or BSD-3-Clause, and PDFium's third-party licences |

## Downloaded only when you ask
| Component | Licence | When |
|---|---|---|
| OpenAI Codex app-server | Apache-2.0 | The first time the agent room is opened and you click Install (fingerprint checked). |

## Content
| Content | Origin |
|---|---|
| Music, ambience and sound effects (`assets/audio`) | Generated with ElevenLabs from this project's own prompts (`tools/audio-prompts.txt`). |
| Icons | This project's own. |
| Fonts | None shipped: the app uses the system's fonts. |
| Website and How-to screenshots | Captured from the app. Some show third-party web pages as browsed in the guides: Wikipedia articles (CC BY-SA 4.0) and Government of Canada pages. |
