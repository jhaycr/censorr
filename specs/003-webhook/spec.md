# Feature Specification: Webhook-triggered processing via 'censorr_preset'

**Feature Branch**: `003-webhook`  
**Created**: 2025-10-26  
**Status**: Draft  
**Input**: User description: "Add a container-embedded webhook server that listens for Radarr/Sonarr events and only processes items that include a fixed 'censorr_preset' tag whose value maps to a preset in censorr.json; then trigger the CLI with that preset; ignore all other events."

## Execution Flow (main)
```
1. Parse user description from Input
   → If empty: ERROR "No feature description provided"
2. Extract key concepts from description
   → Identify: actors, actions, data, constraints
3. For each unclear aspect:
   → Mark with [NEEDS CLARIFICATION: specific question]
4. Fill User Scenarios & Testing section
   → If no clear user flow: ERROR "Cannot determine user scenarios"
5. Generate Functional Requirements
   → Each requirement must be testable
   → Mark ambiguous requirements
6. Identify Key Entities (if data involved)
7. Run Review Checklist
   → If any [NEEDS CLARIFICATION]: WARN "Spec has uncertainties"
   → If implementation details found: ERROR "Remove tech details"
8. Return: SUCCESS (spec ready for planning)
```

---

## ⚡ Quick Guidelines
- ✅ Focus on WHAT users need and WHY
- ❌ Avoid HOW to implement (no tech stack, APIs, code structure)
- 👥 Written for business stakeholders, not developers

### Section Requirements
- **Mandatory sections**: Must be completed for every feature
- **Optional sections**: Include only when relevant to the feature
- When a section doesn't apply, remove it entirely (don't leave as "N/A")

### For AI Generation
When creating this spec from a user prompt:
1. **Mark all ambiguities**: Use [NEEDS CLARIFICATION: specific question] for any assumption you'd need to make
2. **Don't guess**: If the prompt doesn't specify something (e.g., "login system" without auth method), mark it
3. **Think like a tester**: Every vague requirement should fail the "testable and unambiguous" checklist item
4. **Common underspecified areas**:
   - User types and permissions
   - Data retention/deletion policies  
   - Performance targets and scale
   - Error handling behaviors
   - Integration requirements
   - Security/compliance needs

---

## User Scenarios & Testing (mandatory)

### Primary User Story
As a media automation user running Censorr in a container with Radarr/Sonarr, I want new downloads that carry a 'censorr_preset' tag to be automatically processed using the matching preset so that censored outputs are produced consistently without manual steps.

### Acceptance Scenarios
1. Given Censorr is running and a preset named "movies" exists in the configuration, when Radarr sends a webhook for a completed movie download that includes the tag key 'censorr_preset' with value 'movies', then the system acknowledges the webhook, schedules processing for the referenced media using the "movies" preset, and records the outcome in logs.
2. Given a webhook is received without the 'censorr_preset' tag, when the event is evaluated, then the system must ignore it, take no processing action, and record an informational log indicating the reason (missing tag).
3. Given a webhook is received with 'censorr_preset' set to a value that does not match any configured preset, when the event is evaluated, then the system must skip processing and record a warning stating the preset is unknown.
4. Given a qualifying webhook references a media file that is not yet available to the container (e.g., path not mounted or file still moving), when the system attempts to schedule processing, then it must fail gracefully and log the error.
5. Given a webhook is received that does not contain any allowlisted tags (default allowlist includes 'censor_profile'), when the server evaluates the event, then it must ignore it before invoking the CLI and record an informational log indicating the reason (allowlist miss).
6. Given a webhook contains at least one allowlisted tag (e.g., 'censor_profile'), when the server evaluates the event, then it passes the event through to the CLI for further processing according to 'censorr_preset' mapping and records the decision.

### Edge Cases
- Webhook source sends an event type that is not relevant to completed downloads; the system should ignore it and log why.  
- High-volume bursts of qualifying webhooks; the system should maintain responsiveness by enqueuing qualifying events and processing them asynchronously to avoid overwhelming resources.  
- Security validation fails (e.g., missing/invalid shared secret or disallowed source); the system must fail gracefully and log the error.  
- Malformed or oversized payloads: the system must fail gracefully and log the error.  
- Partial configuration (no presets defined); the system should start but treat all events as unprocessable and surface a clear configuration error to the operator.

## Requirements (mandatory)

### Functional Requirements
- FR-001: The system MUST accept webhook requests from Radarr and Sonarr and evaluate them for processing eligibility.
- FR-002: The system MUST only consider events that include a tag whose key is exactly 'censorr_preset'. This key is fixed and not user-configurable.
- FR-003: The system MUST treat the 'censorr_preset' tag value as the name of a preset defined in the product's configuration and use it to determine the processing policy.
- FR-004: If the tag is missing, the system MUST ignore the event without side effects and write an informational log indicating the reason.
- FR-005: If the tag value does not match any configured preset, the system MUST skip processing and write a warning log that includes the unknown value.
- FR-006: For qualifying events, the system MUST initiate exactly one processing job applying the identified preset to the referenced media item.
- FR-007: The system MUST NOT implement idempotency guarantees for duplicate webhook deliveries.
- FR-008: The system MUST record structured logs for each webhook: receipt time, decision (ignored/skipped/accepted), preset selected (if any), and final processing outcome.
- FR-009: The system MUST expose a simple means to observe operational status suitable for container orchestration and uptime monitoring (e.g., readiness/health signals) without prescribing specific technology.
- FR-010: The system MUST fail gracefully and log a clear error when media is unavailable. There is no automatic retry.
- FR-011: The system MUST support both movie and TV use cases consistently with existing processing capabilities and MUST NOT alter established core behaviors (e.g., profanity detection, masking, muting, audio parity policies).
- FR-012: The system MUST provide a configuration switch (e.g., webhooks.enabled) that disables all webhook-triggered processing when set to false. Default is true. When disabled, the system MUST respond to webhook requests with a clear ‘processing disabled’ status and log the reason.
- FR-013: The system MUST provide basic counters (processed, ignored, failed, queued) since process start via a simple read-only status output suitable for container health/observability, and MUST emit structured per-event logs including decision and outcome.
- FR-014: The system MUST respond to webhook requests with a clear status categorized as one of: accepted, ignored, or failed; the response MUST NOT disclose sensitive internal details.
- FR-015: The system MUST treat the 'censorr_preset' key name as reserved by the product and MUST NOT allow end-users to remap or rename this key.
- FR-016: Qualifying webhooks MUST be enqueued and processed asynchronously using best-effort FIFO ordering. The queue MUST be bounded; when capacity is reached, the system MUST fail gracefully (do not enqueue) and log a clear overload message.
- FR-017: The server MUST implement a minimal tag allowlist filter: only events containing at least one allowlisted tag are forwarded to the CLI; all others are ignored and logged. Filtering occurs before any CLI invocation.
- FR-018: The allowlist of tags MUST be configurable via configuration or environment and MUST default to including 'censor_profile'. When the allowlist is empty, filtering is disabled and all events are eligible to pass through (subject to other rules).

### Key Entities (data)
- Webhook Event: Represents a notification from an external automation tool; includes source, event type, media identifiers/paths, and tag set (including optional 'censorr_preset').
- Preset: Named policy defined in configuration; determines how the product processes a media item.
- Processing Job: A unit of work created when a qualifying webhook is accepted; tracks status, timestamps, and outcome linked to the originating event.
- Audit Log Entry: A structured record capturing receipt, evaluation, decision, and completion details for each webhook.

---

## Review & Acceptance Checklist

### Content Quality
- [ ] No implementation details (languages, frameworks, APIs)
- [ ] Focused on user value and business needs
- [ ] Written for non-technical stakeholders
- [ ] All mandatory sections completed

### Requirement Completeness
- [ ] No [NEEDS CLARIFICATION] markers remain
- [ ] Requirements are testable and unambiguous  
- [ ] Success criteria are measurable
- [ ] Scope is clearly bounded
- [ ] Dependencies and assumptions identified

---

## Execution Status

- [x] User description parsed
- [x] Key concepts extracted
- [x] Ambiguities marked
- [x] User scenarios defined
- [x] Requirements generated
- [x] Entities identified
- [ ] Review checklist passed
