# Quickstart: Censorr Webhook Service (WSGI + Gunicorn)

This quickstart shows how to run the standard-library WSGI webhook service (served by Gunicorn) inside the Docker Compose stack defined by spec‑002 and verify basic behavior.

## Prerequisites
- Docker and Docker Compose
- Media directories bind-mounted into the container (as per spec‑002):
  - /data/media/tv
  - /data/media/movies
- A `censorr.json` with presets (e.g., `movies`, `tv`) accessible inside the container

## Run the service

1) Build and start via Compose (from repo root):

```bash
# Build and start (spec‑002 compose file)
docker compose up -d --build
```

2) Verify liveness and readiness:

```bash
curl -fsS http://localhost:8080/healthz
curl -fsS http://localhost:8080/readyz
```

3) Check status counters:

```bash
curl -fsS http://localhost:8080/status | jq .
```

## Send a qualifying webhook

Example Radarr/Sonarr-style payload (note the fixed 'censorr_preset' tag value):

```bash
curl -fsS -X POST http://localhost:8080/webhook \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "radarr",
    "eventType": "Download",
    "tags": {"censorr_preset": "movies"},
    "mediaPaths": ["/data/media/movies/Inception (2010)/Inception (2010).mkv"]
  }'
```

Expected response:
- 202 Accepted when the tag is present and matches a configured preset
- 200 Ignored when the tag is missing or preset unknown
- 400 Failed when payload malformed/oversized or security validation fails

## Notes
- No idempotency: duplicate deliveries are not deduplicated by this service.
- Bounded queue: capacity is finite; on overflow the service fails gracefully and logs an overload message.
- Logs: structured logs to stdout/stderr; counters are in-memory since process start.
