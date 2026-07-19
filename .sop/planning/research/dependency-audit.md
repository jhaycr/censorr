# Research: Dependency Audit (v2 final slate)

Gathered 2026-07-16 at Josh's request: "Do I need uvicorn? Look at the others, are there any that should be replaced?"

## Is uvicorn needed? — Yes, if we serve HTTP

FastAPI is only a framework; it cannot listen on a port — an ASGI server is required. 2026 landscape:

| Server | Assessment |
|---|---|
| **uvicorn** | The FastAPI standard; battle-tested, best docs/community. Plain `uvicorn` (NOT `uvicorn[standard]`) skips uvloop/httptools/watchfiles extras we don't need — the lean install is a small, pure-Python dep set. **Chosen.** |
| granian | Rust, 20–50% faster on synthetic benchmarks — irrelevant here (the API does file I/O + JSON at webhook rates; FFmpeg is the bottleneck by ~1000×). Younger project risk for zero real gain. Rejected. |
| hypercorn | HTTP/2/3 support we don't need. Rejected. |
| gunicorn (v1 used) | WSGI-era; superseded by uvicorn for ASGI. **Dropped from v1's slate.** |

Also re-validated the framework itself: FastAPI remains the 2026 default recommendation for small typed APIs (Litestar is the credible challenger but with ~12% of the ecosystem — more risk, no benefit at our scale). FastAPI stands.

## Full slate audit

### Runtime — core (CLI-only install)

| Dep | Verdict | Notes |
|---|---|---|
| typer | ✅ keep | typed CLI signatures; the stdlib-argparse alternative saves one dep but costs readability — against the project's #1 priority |
| pydantic v2 | ✅ keep | config/API/records — the single modeling idiom |
| rapidfuzz | ✅ keep | irreplaceable for the matcher port |
| pysubs2 | ✅ keep | v1.8.x, actively maintained 2026; becomes the ONLY subtitle I/O |
| rich | ✅ keep | CLI presentation + typer help rendering; core-only (service logs are plain JSON) |

### Runtime — `[serve]` extra (**new structure**)

| Dep | Verdict |
|---|---|
| fastapi | ✅ (serve extra) |
| uvicorn (plain) | ✅ (serve extra) |

**Packaging consequence**: `pip install censorr` → full CLI with zero HTTP deps; `pip install censorr[serve]` → adds the service. The Docker image installs `[serve]`. Worker (`censorr work`) needs only core — it reads the queue and runs the pipeline.

### Dropped from v1's slate

- **gunicorn** (replaced by uvicorn) · **PyYAML** (TOML via stdlib `tomllib`) · hand-rolled SRT parsing (pysubs2) · black (ruff format)

### Dev-only

pytest, pytest-cov, **httpx** (required by FastAPI's TestClient — dev-only), ruff (lint + format), mypy.

## Final counts

Core runtime: **5** deps. Serve extra: **+2**. Dev: **5**. (v1 shipped 7 runtime deps and used gunicorn+PyYAML it didn't need; v2 core is leaner while adding the whole service layer.)

Sources: [DeployHQ: Python app servers 2026](https://www.deployhq.com/blog/python-application-servers-wsgi-vs-asgi-guide), [FastAPI discussion: choosing an ASGI server](https://github.com/fastapi/fastapi/discussions/7299), [BetterStack: Litestar vs FastAPI](https://betterstack.com/community/guides/scaling-python/litestar-vs-fastapi/), [ASGI implementations](https://asgi.readthedocs.io/en/latest/implementations.html)
