# Censorr Kiro Specifications

This directory contains Kiro-format specifications for the Censorr project, transformed from the original `specs/` directory structure.

## Transformation Summary

The original specifications followed a custom format with multiple documents per feature:
- `spec.md` - Feature specification with user scenarios
- `plan.md` - Implementation plan with technical context
- `research.md` - Research decisions and alternatives
- `data-model.md` - Entity and relationship definitions
- `quickstart.md` - Usage examples and getting started guide
- `tasks.md` - Detailed implementation task list
- `contracts/` - API contracts and schemas

The Kiro format consolidates these into a structured workflow:
- `requirements.md` - EARS-compliant requirements with user stories and acceptance criteria
- `design.md` - Architecture, components, and correctness properties (to be created)
- `tasks.md` - Implementation task list (to be generated)

## Feature Specifications

### 001-censorr-core-tool
**Status:** Requirements complete, design pending

Core media processing functionality including:
- Pipeline composition and operation orchestration
- Track selection with language and metadata filtering
- Subtitle processing (merge, mask, QC)
- Audio muting with fuzzy profanity matching
- Output packaging with Plex-compatible naming
- Configuration system with presets
- Container deployment support

**Original Location:** `specs/001-write-a-tool/`

### 002-docker-compose-deployment
**Status:** Requirements complete, design pending

Docker Compose deployment configuration including:
- Simple deployment with local builds
- Media volume configuration (TV/movies)
- Environment-based configuration
- Health checks and restart policies
- Resource constraints
- Validation and error handling

**Original Location:** `specs/002-integrate-existing-docker/`

### 003-webhook-processing
**Status:** Requirements complete, design pending

Webhook-triggered processing system including:
- Webhook event reception from Radarr/Sonarr
- Tag-based filtering with allowlist
- Preset mapping via `censorr_preset` tag
- File-based job queueing
- Separate webhook and worker containers
- Crash recovery and observability
- Security with optional authentication

**Original Location:** `specs/003-webhook/`

## Key Differences from Original Format

### Requirements Document
- Uses EARS (Easy Approach to Requirements Syntax) patterns
- Every requirement follows one of six EARS patterns (Ubiquitous, Event-driven, State-driven, etc.)
- Includes glossary defining all technical terms
- Structured as user stories with 2-5 acceptance criteria each
- Focuses on WHAT and WHY, not HOW

### Design Document (To Be Created)
Will include:
- Overview and architecture
- Components and interfaces
- Data models
- **Correctness Properties** - Formal properties for property-based testing
- Error handling strategy
- Testing strategy

### Tasks Document (To Be Generated)
Will be generated from the design document following TDD principles:
- Tests before implementation
- Parallel execution markers
- Clear dependencies
- FR requirement traceability

## Next Steps

1. **Review Requirements**: Ensure all requirements are complete and EARS-compliant
2. **Create Design Documents**: Transform data models and architecture into design.md
3. **Generate Tasks**: Use the Kiro workflow to generate implementation tasks
4. **Execute Tasks**: Follow TDD approach with property-based testing

## Workflow Commands

```bash
# Review requirements (when ready)
# The agent will ask: "Do the requirements look good?"

# Create design document (after requirements approved)
# The agent will generate design.md with correctness properties

# Generate tasks (after design approved)
# The agent will create tasks.md with TDD ordering

# Execute tasks (after tasks approved)
# Work through tasks one at a time with agent assistance
```

## Notes

- The original specs contain extensive implementation details that will be preserved in design documents
- Property-based testing approach is new and will be integrated into the design phase
- The Kiro workflow emphasizes iterative refinement with explicit user approval at each stage
- Original research decisions and technical context will inform the design documents
