# Research: Library Selection & Service Patterns

Gathered 2026-07-15. Per Josh: "Research the best underlying libraries to use. See what I used in v1."

## v1's dependency slate (baseline)

`typer` `pydantic>=2` `rapidfuzz` `pysubs2` `rich` `PyYAML` `gunicorn` — plus hand-rolled FFmpeg subprocess code, a hand-rolled SRT parser (despite pysubs2 being installed!), and a hand-rolled WSGI app.

## v2 recommendations

| Concern | v1 | v2 recommendation | Rationale |
|---|---|---|---|
| CLI | typer ✅ | **typer** (keep) | mature, typed, already known; rich integration for output |
| Data models | pydantic v2 ✅ | **pydantic v2** (keep) | config schema, API payloads, job records — one modeling idiom everywhere |
| Fuzzy matching | rapidfuzz ✅ | **rapidfuzz** (keep) | best-in-class; v1's FuzzyMatcher semantics port on top |
| Subtitle I/O | pysubs2 installed but bypassed ❌ | **pysubs2 as the ONLY subtitle I/O** | handles SRT/ASS/VTT + encoding quirks; delete the hand-rolled parser; `SSAFile`/`SSAEvent` wrapped in a thin domain type so pysubs2 doesn't leak everywhere |
| FFmpeg | hand-rolled subprocess ✅ (concept) | **keep hand-rolled, thin** — subprocess + args-as-list + `ffprobe -print_format json` parsed into pydantic models | wrapper libs evaluated and rejected: `ffmpeg-python` (filter-graph DSL, effectively unmaintained), `PyAV` (C bindings — power we don't need, deploy pain we do), `ffmpy` (adds nothing over stdlib). v1's adapter shape was right; v2 adds `-progress pipe:1` parsing |
| HTTP service | hand-rolled WSGI + gunicorn ❌ | **FastAPI + uvicorn** | decided in Q3; typed request models, OpenAPI docs for free; uvicorn replaces gunicorn (or uvicorn workers under gunicorn if multi-worker needed — start with plain uvicorn, 2 workers is a config change) |
| Config | JSON + PyYAML (unused?) ❌ | **TOML via stdlib `tomllib`** (read) | decided in Q11; drop PyYAML entirely; pydantic models validate |
| Console output | rich ✅ | **rich** (keep, CLI only) | tables/progress for humans; service logs stay structured JSON |
| Logging | stdlib + prints ❌ | **stdlib `logging` with a small JSON formatter** | avoid structlog dependency; one `logging.py` module in core; no bare `print()` outside CLI presentation layer |
| Queue | hand-rolled file queue ✅ | **keep hand-rolled** (~200 lines, proven) | evaluated Celery/RQ/Huey — all need Redis/broker; persistqueue unmaintained; v1's atomic-rename design is the right size |
| Subtitle download (post-MVP seam) | — | `subliminal` (what cleanvid uses) behind optional extra | only if/when the subtitle-source chain grows a downloader |
| Alignment (post-MVP seam) | — | WhisperX or wav2vec2 forced alignment behind `censorr[align]` extra | see word-alignment-feasibility.md |

Dev tooling: keep pytest + pytest-cov, **ruff (also as formatter — replaces black)**, mypy. One fewer tool, same coverage.

## Service pattern (FastAPI + file queue, two processes)

Validated pattern for the Q5 topology:
- API process: FastAPI + uvicorn. Webhook handlers validate → fingerprint-check → enqueue → return 202 with job id. NO FFmpeg work in-process — FastAPI's `BackgroundTasks` explicitly not used for processing (dies with the server; wrong failure domain).
- Worker process: plain synchronous Python loop (v1 shape): claim → run pipeline as library call → write job record. No async needed — FFmpeg is one long subprocess; concurrency knob is "N worker processes," not asyncio.
- Job status: the queue's job-record JSONs are the single source of truth; API reads them for `/jobs/{id}` (read-only across the shared volume). Worker updates progress by rewriting the job record (atomic replace), API just serves the latest.
- Lifespan: API uses FastAPI lifespan only for config load + queue-dir init; worker startup runs GC sweep (Q9 retention).

Sources: [FastAPI background tasks docs](https://fastapi.tiangolo.com/tutorial/background-tasks/), [OneUptime: background processing in FastAPI](https://oneuptime.com/blog/post/2026-01-25-background-task-processing-fastapi/view), [pysubs2](https://pysubs2.readthedocs.io/), [ffmpeg wrapper comparison](https://json2video.com/how-to/ffmpeg-course/ffmpeg-wrappers.html)
