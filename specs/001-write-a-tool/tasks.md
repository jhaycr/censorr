# Tasks (Phase 2+)

This checklist will guide the implementation using TDD. It maps to requirements and constitution gates.

## Contracts & Scaffolding (P)
1. Create Python project skeleton (src/, tests/) (P)
2. Define dataclasses/models for Artifact, Selector, Operation contracts (tests first) (P)
3. Implement registry and planner stubs with unit tests (P)
4. Add executor with dry-run and explain (tests) (P)

## Adapters & Utilities (P)
5. FFmpeg adapter: probe, extract audio/subs, mute windows, remux (tests with small fixtures) (P)
6. Subtitle parser utils using pysubs2; normalization helpers (tests) (P)
7. Fuzzy matcher using RapidFuzz with defaults and allow-list (tests) (P)

## Operations (serial where dependent)
8. extract_subtitles op (unit + contract tests)
9. merge_subtitles op (unit + contract tests)
10. mask_subtitles op (unit + contract + QC path)
11. export_sidecar op (unit)
12. extract_audio op (unit)
13. mute_audio op (unit + windows input variants)
14. remux op (unit + integration)

## CLI
15. CLI entry with typer: flags for inputs/targets, selectors, dry-run/explain (tests)
16. --list-ops and --help content (tests)
17. Skip/force controls and parallelism flag (tests)

## Caching & Observability
18. Workdir layout and manifest recording (tests)
19. Structured execution log per op (tests)
20. Error handling for external tools; preserve artifacts (tests)

## Integration Scenarios
21. Subtitle-only flow end-to-end (dry-run + outputs)
22. Audio-only with external windows (dry-run + outputs)
23. Full flow: extract→mask→mute→remux (small fixture)

## Documentation
24. Update quickstart with concrete CLI examples as implemented
25. Document selector schema and examples in contracts

Notes:
- (P) indicates tasks that can run in parallel.
- Keep tests minimal and fast; prefer tiny media samples.
- Ensure Constitution Gates are met before merging.