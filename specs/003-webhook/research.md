# Research Decisions: Webhook-triggered processing via 'censorr_preset'

Date: 2025-10-26  
Branch: 003-webhook  
Spec: /home/josh/Code/Censorr2/specs/003-webhook/spec.md

## Decisions

1) Framework and Serving
- Decision: Use Flask for the HTTP service; serve via Gunicorn in Docker for robustness.
- Rationale: Minimal dependencies, easy to integrate with existing Python CLI and logging; Gunicorn handles signals and concurrency better than Flask dev server.
- Alternatives: FastAPI (more features, higher overhead); aiohttp (async-first but unnecessary complexity here).

2) Endpoint Surface
- Decision: Single POST `/webhook` endpoint; detect source (Radarr/Sonarr) via payload fields; GET `/healthz`, `/readyz`, `/status` for ops.
- Rationale: Simpler routing; avoids maintaining two nearly identical endpoints.
- Alternatives: Separate `/webhook/radarr` and `/webhook/sonarr` (more explicit but redundant).

3) Security Posture
- Decision: Optional shared secret header validation; on failure, respond as failed and log; no IP allowlist in this feature.
- Rationale: Keeps setup simple; meets spec to fail gracefully and log without blocking deployment.
- Alternatives: Mandatory HMAC signature, IP allowlists; deferred as future hardening.

4) Queue Strategy
- Decision: In-process bounded FIFO using `queue.Queue`; default capacity 100; on overflow → reject and log (do not block request).
- Rationale: Keeps service responsive under bursts; avoids external broker complexity.
- Alternatives: External Redis/RabbitMQ; overkill for homelab scale.

5) Counters & Status
- Decision: In-memory counters since process start; `/status` returns {processed, ignored, failed, queued, queue_depth}.
- Rationale: Lightweight, meets observability need without extra stores.
- Alternatives: Export Prometheus metrics; can be added later.

6) Integration with Existing CLI
- Decision: Worker threads invoke the existing CLI/library with the selected preset and media path(s); stdout/stderr are logged.
- Rationale: Respects CLI-first principle; reuses proven pipeline behavior.
- Alternatives: Reimplement processing logic in service; violates library-first and increases risk.

7) Health/Readiness
- Decision: `/healthz` always 200 when process alive; `/readyz` 200 when config loaded and worker thread running.
- Rationale: Matches container health expectations; simple, testable signals.
- Alternatives: Complex self-diagnostics; unnecessary.

## Open Items (deferred)
- Metrics exposition beyond counters (Prometheus).
- Stronger auth (HMAC, IP allowlists).
- Persistent job queue or dedupe cache.

## Alternatives to Flask for minimal webhook ingress

Goal: a tiny HTTP listener that only accepts webhooks and invokes the CLI; no business logic in the server.

1) Python stdlib WSGI (wsgiref.simple_server) behind Gunicorn
- What: Write a 20–40 line WSGI app using only stdlib; run under Gunicorn in Docker for concurrency/signal handling.
- Pros: Zero framework dependency; smallest Python footprint; easy health/status routes; logs to stdout.
- Cons: You still need Gunicorn (or similar) for production serving; mapping CLI exit codes to HTTP statuses must be defined.
- Fit to “no business logic”: Excellent — server reads JSON and execs CLI; all decisions in CLI. Use exit codes to set HTTP status (e.g., 0=202 accepted, 2=200 ignored, 3=400 failed, 1=500 error).

2) Bottle (single-file microframework)
- What: Minimal WSGI microframework in one file.
- Pros: Tiny, simple routing; minimal cognitive overhead.
- Cons: Extra dependency; not materially simpler than stdlib + Gunicorn.
- Fit: Good — still keep logic in CLI; Bottle only handles routing.

3) Falcon (WSGI microframework)
- Pros: Lightweight, performant, explicit.
- Cons: Adds dependency; overkill for a single POST + 3 GET endpoints.
- Fit: Good but heavier than needed.

4) Starlette/Uvicorn (ASGI)
- Pros: Modern, fast; clean middleware; easy to grow later.
- Cons: Heavier stack (ASGI), more moving parts than required.
- Fit: Acceptable but not the simplest path.

5) aiohttp (async HTTP server)
- Pros: No external ASGI server needed; simple to wire.
- Cons: Async complexity not needed; adds dependency.
- Fit: Acceptable but not simplest.

6) External binary “webhook” (adnanh/webhook)
- What: A standalone binary that maps HTTP hooks to shell commands via a JSON config.
- Pros: Perfectly matches “receive webhook → run command”; no app code; mature and widely used.
- Cons: Non-Python dependency; embed extra binary in the image; mapping/templating limited to tool features; integrate logs and health separately.
- Fit: Excellent for zero-code ingress; pair with a tiny status/health shim or rely on container healthcheck hitting a static endpoint.

7) BusyBox httpd or Nginx + CGI/FastCGI
- Pros: Very small; classic pattern to execute scripts on HTTP.
- Cons: Operationally fiddly; CGI environment and security hardening; awkward logging/health wiring.
- Fit: Works, but higher ops overhead than necessary.

Recommendation
- Primary: stdlib WSGI app under Gunicorn (Option 1). It keeps Python-only, zero framework deps, minimal code, and cleanly shifts all logic to the CLI via a small exit-code contract.
- Secondary (even simpler app code): external “webhook” binary (Option 6). If acceptable to introduce a non-Python binary, this yields the thinnest ingress. The CLI (or a small wrapper) still owns all business rules.

Proposed CLI exit code contract for server mapping
- 0 → 202 Accepted (processed/enqueued)
- 2 → 200 Ignored (missing/unknown tag)
- 3 → 400 Failed (malformed/oversized/security validation)
- 1 → 500 Error (unexpected internal error)
