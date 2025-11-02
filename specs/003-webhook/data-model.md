# Data Model: Webhook-triggered processing via 'censorr_preset'

Date: 2025-10-26  
Branch: 003-webhook

## Entities

### WebhookEvent
- source: enum [radarr, sonarr]
- eventType: string (e.g., Download, Grab, Test)
- tags: map<string, string> (must include 'censorr_preset' for processing)
- mediaPaths: array<string> (absolute paths inside container)
- receivedAt: datetime (UTC)

Validation:
- If 'censorr_preset' tag missing → ignore.
- If 'censorr_preset' value not in presets → skip with warning.
- If paths missing/unavailable → fail gracefully and log.

### ProcessingJob
- id: string (uuid)
- preset: string (from 'censorr_preset')
- mediaPath: string
- enqueuedAt: datetime
- startedAt: datetime|null
- finishedAt: datetime|null
- status: enum [queued, running, succeeded, failed]
- error: string|null

### Counters (since process start)
- processed: int
- ignored: int
- failed: int
- queued: int

### Queue
- type: bounded FIFO
- capacity: int (default 100)
- depth: int (current)
- overflowPolicy: reject & log

## Relationships
- WebhookEvent with qualifying tag produces exactly one ProcessingJob per mediaPath.
- ProcessingJob transitions: queued → running → (succeeded|failed).
