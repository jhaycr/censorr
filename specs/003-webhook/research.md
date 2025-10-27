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
