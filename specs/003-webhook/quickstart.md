# Quickstart: Censorr Webhook Service (WSGI + Gunicorn)

This quickstart shows how to run the standard-library WSGI webhook service (served by Gunicorn) inside a separate Docker container alongside the main censorr daemon.

## Prerequisites
- Docker and Docker Compose
- Media directories bind-mounted into the container (as per spec‑002):
  - /data/media/tv
  - /data/media/movies
- A `censorr.json` with presets (e.g., `movies`, `tv`) accessible inside the container

## Run the services

The `docker-compose.yml` defines two services that share a queue volume and are built from separate Dockerfiles:
- `censorr-listener` (Dockerfile.web): Webhook service on port 8000 (produces jobs). Minimal image; does NOT include ffmpeg.
- `censorr-cli` (Dockerfile.tool): Worker service (consumes jobs and runs the CLI). Includes ffmpeg for media processing.

1) Build and start via Compose (from repo root):

```bash
"# Build and start both containers (webhook + worker)
docker compose up -d --build

# Or build specific images
docker compose build censorr-listener
docker compose build censorr-cli

# Start services
docker compose up -d censorr-listener censorr-cli
```

The webhook service will be available at `http://localhost:8000` (configurable via `WEBHOOK_PORT` env var).
Jobs are written to `/app/queue/incoming` and processed by the worker.

2) Verify liveness and readiness:

```bash
curl -fsS http://localhost:8000/healthz
curl -fsS http://localhost:8000/readyz
```

3) Check status counters:

```bash
curl -fsS http://localhost:8000/status | jq .
```

## Send a qualifying webhook

Example Radarr/Sonarr-style payload (note the `censorr_profile` tag):

```bash
curl -fsS -X POST http://localhost:8000/webhook \
  -H 'Content-Type: application/json' \
  -d '{
    "source": "radarr",
    "eventType": "Download",
    "tags": {"censorr_profile": "movies"},
    "mediaPaths": ["/data/media/movies/Inception (2010)/Inception (2010).mkv"]
  }'
```

Expected response:
- **202 Accepted** when the tag is present and CLI accepts the job (exit code 0)
- **200 Ignored** when the tag is missing (filtered by allowlist) or CLI ignores it (exit code 2)
- **400 Failed** when payload malformed or CLI validation fails (exit code 3)
- **500 Error** when CLI encounters an unexpected error (exit code 1)

## Configure the allowlist

The webhook service filters events based on tags. By default, only events with the `censorr_profile` tag are processed.

Configure the allowlist via environment variable in `.env`:

```bash
# Default: only allow events with censorr_profile tag
CENSORR_WEBHOOK_ALLOWLIST=censorr_profile

# Allow multiple tags (comma-separated)
CENSORR_WEBHOOK_ALLOWLIST=censorr_profile,another_tag

# Disable filtering (process all events)
CENSORR_WEBHOOK_ALLOWLIST=
```

After changing the allowlist, restart the webhook container:

```bash
docker compose restart censorr-webhook
```

## Security features (optional)

### Shared secret authentication

Protect your webhook endpoint with a shared secret that must be included in the `X-Webhook-Secret` header:

```bash
# In .env file
CENSORR_WEBHOOK_SECRET=your-secret-token-here
```

Then configure Radarr/Sonarr to include the secret in webhook requests. Without the correct secret, requests will receive `401 Unauthorized`.

**Note**: If `CENSORR_WEBHOOK_SECRET` is not set, no authentication is required (suitable for internal homelab networks).

### Payload size limit

Protect against oversized payloads by setting a maximum size (default: 1MB):

```bash
# In .env file (size in bytes)
CENSORR_WEBHOOK_MAX_SIZE=2097152  # 2MB

# Or use default 1MB (1048576 bytes)
# CENSORR_WEBHOOK_MAX_SIZE=1048576
```

Requests exceeding this limit will receive `413 Payload Too Large`.

Example webhook request with authentication:

```bash
curl -fsS -X POST http://localhost:8000/webhook \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Secret: your-secret-token-here' \
  -d '{
    "source": "radarr",
    "eventType": "Download",
    "tags": {"censorr_profile": "movies"},
    "mediaPaths": ["/data/media/movies/Inception (2010)/Inception (2010).mkv"]
  }'
```

## Run webhook service standalone (development)

For development, you can run the webhook service directly with Gunicorn:

```bash
# Install dependencies
pip install -e .

# Set environment variables
export CENSORR_WEBHOOK_ALLOWLIST=censorr_profile

# Run with Gunicorn
gunicorn \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  src.webhook.runner:app
```

Or use the Docker entrypoint directly:

```bash
docker run -p 8000:8000 \
  -e CENSORR_WEBHOOK_ALLOWLIST=censorr_profile \
  -e CENSORR_QUEUE_PATH=/app/queue \
  -v /path/to/media:/data/media \
  -v /path/to/config:/app/config \
  -v /path/to/queue:/app/queue \
  censorr:latest webhook

## Worker configuration

The worker service polls the queue and processes jobs:

- CENSORR_QUEUE_PATH=/app/queue (shared with webhook)
- CENSORR_QUEUE_MAX_RETRIES=3 (default)
- CENSORR_QUEUE_LEASE_SECONDS=1800 (default)
- CENSORR_WORKER_POLL_INTERVAL=2 (default)

Check worker logs:

```bash
docker compose logs -f censorr-cli
```
```

## Notes
- **No idempotency**: duplicate deliveries are not deduplicated by this service.
- **Bounded queue**: capacity is finite; on overflow the service fails gracefully and logs an overload message.
- **Logs**: structured JSON logs to stdout/stderr with request_id, source, decision, status fields; counters are in-memory since process start.
- **Security**: Optional shared secret via `CENSORR_WEBHOOK_SECRET` env var and payload size limit via `CENSORR_WEBHOOK_MAX_SIZE` (default 1MB). Designed for internal homelab use; for external exposure, consider using a reverse proxy with authentication.
- **CLI invocation**: The webhook service invokes the CLI via subprocess. All business logic (preset mapping, queue management) is handled by the CLI.
