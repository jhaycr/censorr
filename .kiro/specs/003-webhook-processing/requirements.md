# Requirements Document: Webhook-Triggered Processing

## Introduction

This feature adds webhook server capabilities to Censorr, enabling automatic processing of media files when Radarr or Sonarr import new content. The webhook service acts as a lightweight ingress layer that filters events and enqueues processing jobs for a worker container to execute.

## Glossary

- **Webhook Service**: A lightweight HTTP server that receives and filters webhook events
- **Worker Service**: A container that polls the queue and executes Censorr CLI processing jobs
- **Queue**: A file-based FIFO queue for passing jobs between webhook and worker services
- **Allowlist**: A configurable list of tags that must be present for an event to be processed
- **Preset Tag**: The `censorr_preset` tag value that maps to a processing preset configuration
- **Job**: A unit of work representing one media file to process with a specific preset
- **Counters**: In-memory statistics tracking processed, ignored, failed, and queued events
- **Health Endpoint**: An HTTP endpoint for container orchestration health checks
- **Status Endpoint**: An HTTP endpoint exposing operational counters and queue depth

## Requirements

### Requirement 1: Webhook Event Reception

**User Story:** As a Radarr/Sonarr user, I want Censorr to automatically process new media imports, so that clean versions are available without manual intervention.

#### Acceptance Criteria

1. WHEN Radarr or Sonarr sends a webhook, THE Webhook Service SHALL accept the HTTP POST request
2. WHEN a webhook is received, THE Webhook Service SHALL parse the JSON payload
3. WHEN the payload is malformed, THE Webhook Service SHALL respond with 400 Bad Request
4. WHEN the payload is oversized, THE Webhook Service SHALL respond with 413 Payload Too Large
5. THE Webhook Service SHALL support webhooks from both Radarr and Sonarr sources

### Requirement 2: Tag-Based Filtering

**User Story:** As a user, I want to control which media gets processed by applying tags in Radarr/Sonarr, so that I can selectively enable censoring for specific content.

#### Acceptance Criteria

1. WHEN a webhook event contains at least one allowlisted tag, THE Webhook Service SHALL forward it for processing
2. WHEN a webhook event contains no allowlisted tags, THE Webhook Service SHALL ignore it and respond with 200 Ignored
3. WHEN the allowlist is configured, THE Webhook Service SHALL check tags before invoking the CLI
4. WHEN the allowlist is empty, THE Webhook Service SHALL process all events
5. THE Webhook Service SHALL default to allowing events with the `censorr_profile` tag

### Requirement 3: Preset Mapping

**User Story:** As a user, I want to specify which processing preset to use via the `censorr_preset` tag, so that different media types can use appropriate configurations.

#### Acceptance Criteria

1. WHEN an event contains the `censorr_preset` tag, THE System SHALL use that value to select a preset
2. WHEN the preset value matches a configured preset, THE System SHALL enqueue a job with that preset
3. WHEN the preset value doesn't match any configured preset, THE System SHALL skip processing and log a warning
4. WHEN the `censorr_preset` tag is missing, THE System SHALL ignore the event
5. THE System SHALL treat `censorr_preset` as a reserved, non-configurable tag name

### Requirement 4: Job Queueing

**User Story:** As a system operator, I want webhook events to be queued for asynchronous processing, so that the webhook service remains responsive during bursts.

#### Acceptance Criteria

1. WHEN a qualifying event is received, THE Webhook Service SHALL enqueue a job to the file-based queue
2. WHEN the queue is full, THE Webhook Service SHALL respond with 503 Service Unavailable
3. WHEN a job is enqueued successfully, THE Webhook Service SHALL respond with 202 Accepted
4. WHEN the filesystem is full or unwritable, THE Webhook Service SHALL fail gracefully and log an error
5. THE System SHALL use atomic file operations to ensure queue concurrency safety

### Requirement 5: Worker Processing

**User Story:** As a system operator, I want a worker service to process queued jobs, so that media processing happens asynchronously without blocking webhook reception.

#### Acceptance Criteria

1. WHEN jobs are in the queue, THE Worker Service SHALL poll and process them in FIFO order
2. WHEN processing a job, THE Worker Service SHALL invoke the Censorr CLI with the specified preset
3. WHEN a job succeeds, THE Worker Service SHALL move it to the done directory
4. WHEN a job fails, THE Worker Service SHALL retry up to the configured maximum attempts
5. WHEN retries are exhausted, THE Worker Service SHALL move the job to the failed directory

### Requirement 6: Crash Recovery

**User Story:** As a system operator, I want the system to recover from crashes without losing jobs, so that processing continues reliably after failures.

#### Acceptance Criteria

1. WHEN the worker crashes during processing, THE System SHALL detect stale jobs after a lease timeout
2. WHEN a stale job is detected, THE System SHALL re-queue it for processing
3. WHEN a job has been re-queued multiple times, THE System SHALL respect the retry limit
4. WHEN the queue directory is corrupted, THE System SHALL log errors and continue with valid jobs
5. THE System SHALL use file-based locking to prevent concurrent processing of the same job

### Requirement 7: Observability

**User Story:** As a system operator, I want to monitor webhook service health and processing statistics, so that I can detect issues and track usage.

#### Acceptance Criteria

1. WHEN the /healthz endpoint is called, THE Webhook Service SHALL respond with 200 OK if alive
2. WHEN the /readyz endpoint is called, THE Webhook Service SHALL respond with 200 OK if the worker is running and config is loaded
3. WHEN the /status endpoint is called, THE Webhook Service SHALL return counters for processed, ignored, failed, and queued events
4. WHEN events are processed, THE System SHALL emit structured logs with request_id, source, decision, and status
5. THE System SHALL maintain counters in memory since process start

### Requirement 8: Security

**User Story:** As a security-conscious user, I want to protect the webhook endpoint with authentication, so that only authorized sources can trigger processing.

#### Acceptance Criteria

1. WHEN a shared secret is configured, THE Webhook Service SHALL require the X-Webhook-Secret header
2. WHEN the secret header is missing or invalid, THE Webhook Service SHALL respond with 401 Unauthorized
3. WHEN no secret is configured, THE Webhook Service SHALL accept all requests (suitable for internal networks)
4. WHEN a payload exceeds the size limit, THE Webhook Service SHALL reject it before processing
5. THE System SHALL default to a 1MB payload size limit

### Requirement 9: Separate Container Images

**User Story:** As a system operator, I want separate container images for webhook and worker services, so that I can optimize each for its specific role.

#### Acceptance Criteria

1. THE System SHALL provide a minimal webhook image without FFmpeg
2. THE System SHALL provide a worker image that includes FFmpeg for media processing
3. WHEN deploying via Compose, THE System SHALL build both images from separate Dockerfiles
4. WHEN the webhook service starts, THE System SHALL not require FFmpeg to be present
5. THE System SHALL name services `censorr-webhook` and `censorr-cli` to reflect their roles

### Requirement 10: Configuration

**User Story:** As a user, I want to configure webhook behavior through environment variables, so that I can customize filtering and processing without code changes.

#### Acceptance Criteria

1. WHEN CENSORR_WEBHOOK_ALLOWLIST is set, THE System SHALL use those tags for filtering
2. WHEN CENSORR_WEBHOOK_SECRET is set, THE System SHALL require authentication
3. WHEN CENSORR_WEBHOOK_MAX_SIZE is set, THE System SHALL enforce that payload size limit
4. WHEN CENSORR_QUEUE_PATH is set, THE System SHALL use that directory for the queue
5. THE System SHALL document all configuration options in the deployment guide

### Requirement 11: No Idempotency Guarantee

**User Story:** As a system architect, I want to keep the webhook service simple by not implementing deduplication, so that complexity is minimized and upstream systems handle duplicates.

#### Acceptance Criteria

1. WHEN duplicate webhook events are received, THE System SHALL process each one independently
2. WHEN the same media file is processed multiple times, THE System SHALL execute the full pipeline each time
3. THE System SHALL document that duplicate detection is the responsibility of upstream systems
4. WHEN idempotency is needed, THE System SHALL recommend implementing it in Radarr/Sonarr configuration
5. THE System SHALL log all received events regardless of duplication

### Requirement 12: Error Handling

**User Story:** As a system operator, I want clear error messages and graceful degradation, so that I can diagnose and resolve issues quickly.

#### Acceptance Criteria

1. WHEN the CLI invocation fails, THE Webhook Service SHALL map exit codes to HTTP status codes
2. WHEN a validation error occurs (exit code 3), THE System SHALL respond with 400 Bad Request
3. WHEN an unexpected error occurs (exit code 1), THE System SHALL respond with 500 Internal Server Error
4. WHEN the CLI ignores an event (exit code 2), THE System SHALL respond with 200 Ignored
5. THE System SHALL log all errors with sufficient context for debugging

### Requirement 13: Integration Testing

**User Story:** As a developer, I want integration tests using representative webhook payloads, so that I can verify the system works with real Radarr/Sonarr events.

#### Acceptance Criteria

1. THE System SHALL include unit tests with example Radarr media import payloads
2. THE System SHALL include unit tests with example Sonarr completed download payloads
3. WHEN tests run, THE System SHALL verify allowlist filtering behavior
4. WHEN tests run, THE System SHALL verify response categorization (accepted, ignored, failed)
5. THE System SHALL verify that the CLI is invoked correctly for qualifying events
