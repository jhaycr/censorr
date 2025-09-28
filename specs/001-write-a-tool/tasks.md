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
8. ✅ extract_subtitles op (unit + contract tests)
9. ✅ merge_subtitles op (unit + contract tests)
10. ✅ mask_subtitles op (unit + contract + QC path)
11. ✅ export_sidecar op (unit)
12. ✅ extract_audio op (unit)
13. ✅ mute_audio op (unit + windows input variants)
14. ✅ remux op (unit + integration)

## CLI
15. ✅ CLI entry with typer: flags for inputs/targets, selectors, dry-run/explain (tests)
16. ✅ --list-ops and --help content (tests)
17. ✅ Skip/force controls and parallelism flag (tests)

## Caching & Observability
18. ✅ Workdir layout and manifest recording (debug focus)
	- Implement manifest.json capturing per-op inputs (paths + checksum), outputs, params, timestamp.
	- Skip implementing automatic skip logic (future optional). Tests assert presence & schema.
19. ✅ Structured execution log per op (tests)
20. ✅ Error handling for external tools; preserve artifacts (tests)

## Integration Scenarios
21. ✅ Subtitle-only flow end-to-end (dry-run + outputs)
22. ✅ Audio-only with external windows (dry-run + outputs)
23. ✅ Full flow: extract→mask→mute→remux (small fixture)

## Documentation
24. Update quickstart with concrete CLI examples as implemented
25. Document selector schema and examples in contracts

Notes:
- (P) indicates tasks that can run in parallel.
- Keep tests minimal and fast; prefer tiny media samples.
- Ensure Constitution Gates are met before merging.

---

## New: Post-mask QC + CLI override (FR-045, FR-047)

26. ✅ Operation flags plumbing
	- Add `continue_on_qc_fail` to execution flags/context (default False); propagate from CLI to operations.
27. ✅ MaskSubtitlesOperation: QC step
	- After masking, run QC using same matcher and allow-list; generate `qc_report.json`, log summary; fail by default on residuals.
	- When `continue_on_qc_fail` is True, proceed; attach `qc` metadata to artifact with match count and report path.
28. ✅ CLI flag
	- Add `--continue-on-qc-fail` boolean flag; document in help; precedence over config.
29. Tests
	- Unit tests for QC failure vs override and allow-list handling.
	- Integration tests: subtitle-only and full pipeline with QC residuals; verify default abort and override continuation.
30. Docs
	- Update quickstart and CLI usage examples; describe QC behavior and report format.

---

## New: Containerization (Constitution XII)

31. Dockerfile (non-root, minimal image)
	- Create `Dockerfile` at repo root with a slim, pinned base (Python 3.11 slim by digest).
	- Install runtime deps minimally; ensure FFmpeg is available on PATH inside the container (pin package version).
	- Create non-root user (uid/gid 10001), set `WORKDIR /app`, copy project.
	- Set `ENTRYPOINT` to the CLI (e.g., `python -m src.cli.main`).
	- Emit logs to stdout/stderr only; no files under container image FS by default.

32. [P] Compose example and volumes
	- Add `examples/compose.yaml` showing:
		- Bind mounts for media input and `WORKDIR` output
		- Environment variables mapping to CLI flags (demonstrate both approaches)
		- A sample service using the built image and a dry-run command

33. [P] Podman run example
	- Add `examples/podman-run.sh` demonstrating an equivalent to the Compose example.
	- Include `--user` flag if needed and volume mappings for media and workdir.

34. ENTRYPOINT/console script alignment
	- Ensure `pyproject.toml` defines a console script entrypoint (e.g., `censorr=censorr.cli:main`) or confirm `python -m src.cli.main` works.
	- Update Dockerfile to use the chosen entrypoint consistently.

35. Container image hardening
	- Drop build tools in final stage (multi-stage build if needed).
	- Run as non-root by default; verify no root-owned writable paths.
	- Pin base image by digest; document update cadence.

36. Multi-arch build notes
	- Add `docs/container-build.md` with instructions for `docker buildx` to publish amd64/arm64 images.
	- Include example build commands and a note on QEMU requirements.

37. Healthcheck guidance (if applicable)
	- If a long-running mode is introduced later, document a `HEALTHCHECK` pattern.
	- For current short-lived CLI usage, document that no healthcheck is added.

38. [P] Container smoke tests
	- Add `tests/integration/test_container_smoke.py` to run the built image with `--help` and a `--dry-run` pipeline on tiny fixtures.
	- Gate tests to run only when `DOCKER_AVAILABLE=1` in env.

39. SBOM / provenance (optional)
	- Add a step in `docs/container-build.md` for generating an SBOM (e.g., `docker sbom` or `syft`), storing artifacts under `dist/`.

40. Docs: Quickstart container usage
	- Update `specs/001-write-a-tool/quickstart.md` with container run examples (Docker/Podman), volume mounts, and env→flag mapping.
	- Add troubleshooting notes (permissions, SELinux on host, ffmpeg availability).

41. CI build (optional enhancement)
	- Add a GitHub Actions workflow `.github/workflows/container.yml` to build and (optionally) push the image on tags; include `buildx` matrix for amd64/arm64 if feasible.

Dependencies & Ordering Notes
- 31 before 32–35 (Dockerfile precedes examples and hardening).
- 34 depends on console entrypoint availability in `pyproject.toml`.
- 36 and 41 are documentation/CI and can follow after 31.
- 38 can run after 31 (and local Docker availability); mark as optional in CI.

---

## New: Subtitle title & metadata filtering (FR-048)

42. ✅ Selector schema extension
	- Update `Selector` for SUBTITLE to support `title_include[]`, `title_exclude[]`, `title_regex[]`, and `exclude_sdh` (boolean). Add validation: these fields only valid for SUBTITLE.
	- Update `selector.schema.json` and `contracts/selectors.md` with examples and precedence rules (excludes win; regex opt-in).

43. ✅ Adapter metadata exposure
	- Ensure ffprobe adapter captures `title` and `forced` disposition (if available) into track metadata. Add tests with mocked ffprobe JSON covering null/empty titles and forced flags.

44. ✅ Planner/selection wiring
	- Implement title/metadata matching in selector `.matches()` for SUBTITLE: case-insensitive substring on normalized title; optional regex mode; apply excludes before includes; implement `exclude_sdh` convenience (pattern list: SDH/HI/CC variants).

45. ✅ CLI flags & JSON input
	- Add CLI flags to pass subtitle title filters (e.g., `--subtitle-title-include`, `--subtitle-title-exclude`, `--subtitle-title-regex`, `--exclude-sdh`).
	- Ensure flags integrate with existing `--language` behavior and selector construction.

46. ✅ Tests: selection behavior
	- Unit tests for selector matching covering: null/empty title considered as main/full; include forced + full; exclude SDH/HI synonyms; regex include; exclude precedence.
	- Integration test: a fixture with three English tracks (full, forced, SDH) → plan selects only full+forced → merge output contains only those cues.

47. ✅ Docs & examples
	- Update `quickstart.md` and `contracts/selectors.md` with examples for selecting English full + forced while excluding SDH.
	- Add CLI help examples and a sample command in quickstart.

48. ✅ Back-compat & defaults
	- Ensure existing usages continue to work with only `--language` specified. Title filters are optional and off by default. When both include and exclude match, exclude wins; document this behavior.

---

## New: Sidecar naming + Plex Edition tag (FR-054, FR-055)

49. ✅ Filename parsing utility
	- Implement helper to parse base title and detect existing edition tags `{edition-*}`.
	- Provide function `ensure_movie_edition_tag(path, tag="Censorr") -> new_path` that is idempotent.

50. ✅ Sidecar naming generator
	- Implement `build_sidecar_sub_path(video_path, lang, tag="censorr")` producing `<base>.<lang>.<tag>.srt`.
	- Normalize `<base>` by stripping edition tag, trimming whitespace, collapsing multiple spaces, preserving year segment.

51. ✅ Collision & reuse logic
	- If target exists: compare checksum; if identical, skip write; if different, append `-2`, `-3`, etc. before `.srt`.
	- Unit tests covering identical vs differing content, numeric suffix increment.

52. ✅ Episode vs movie handling
	- Add simple media type inference (parameter or heuristic: presence of `S\d{2}E\d{2}`) to suppress edition tag for episodes.
	- Tests verifying no edition tag added for episodes; sidecar naming still applied.

53. ✅ Integration into remux/export
	- Wire edition tagging into remux operation for movie outputs only (pre-write rename step).
	- Wire sidecar path generation into sidecar export/remux path logic; replace prior ad-hoc naming.

54. ✅ CLI/config options
	- Add config/CLI option to switch censorship tag between `censorr` (default) and `clean`.
	- Document in help text and quickstart.

55. ✅ Tests
	- Unit: edition tagging idempotency, existing edition pass-through, base normalization, sidecar naming variants.
	- Integration: full pipeline producing movie remux with edition tag, sidecar reuse, rerun idempotency (no duplicate tag or rewritten identical sidecar).

56. ✅ Docs
	- Update spec traceability (already appended FR-054/FR-055), quickstart examples, and contracts/naming section if present.
	- Note episode exclusion from edition tagging.

57. ✅ Logging & audit
	- Add structured log entries for: edition tag added, edition tag skipped (pre-existing), sidecar reused, sidecar collision new name.

58. ✅ Acceptance alignment
	- Ensure Acceptance Scenario #16 passes with new logic; add fixture-based test naming accordingly.

---

## New: Audio parity, cleanup, final destination, selector precedence (FR-056..FR-059)

59. ✅ Audio codec parity enforcement
	- Extend remux op to probe source audio (codec, channels, sample rate) and verify post-remux track matches.
	- Add strict mode option to fail on mismatch; default warn.
	- Tests: mutated fixture forcing mismatch (simulate) → warning/failure.

60. ✅ Intermediate cleanup utility
	- Implement cleanup manager recording produced intermediate artifacts and dependencies.
	- After downstream success, delete unless `persist_intermediate` flag set.
	- Tests: ensure deletion vs persistence path.

61. ✅ Final destination move
	- Add CLI/config `--final-dest` path.
	- Implement atomic rename or copy+checksum fallback; log actions.
	- Tests: same filesystem (rename) and simulated cross-filesystem (force copy path via monkeypatch).

62. ✅ Move ordering & failure behavior
	- Ensure move happens after QC steps and edition/sidecar naming.
	- Simulate move failure (permission denied) → retain originals, error surfaced.

63. ✅ Selector precedence enforcement
	- Remove/avoid CLI SDH exclusion flag; map any legacy input to deprecation warning if present.
	- Precedence rule: if selectors config provided, ignore individual CLI language/forced toggles except for base language; log decision.
	- Tests: config vs CLI conflict scenario logs precedence.

64. ✅ Docs & spec alignment
	- Update quickstart and contracts docs to reflect: no `--exclude-sdh`; use selectors JSON.
	- Document `--persist-intermediate`, `--final-dest`, strict parity mode flag.

65. ✅ Logging & audit entries
	- Add entries: audio_parity_validated, audio_parity_mismatch, intermediate_cleaned, intermediate_retained, final_move_success, final_move_failure, selector_cli_overridden.

66. ✅ Manifest reproducibility tests
	- Re-run pipeline; verify manifest entries append (or overwrite deterministically) with consistent checksums for unchanged inputs.
	- Assert no duplicate edition tags or sidecar rewrite when unchanged; skipping not required.

---

## New: Runtime Observability - FFmpeg Heartbeat & Timestamped Progress (FR-064)

67. ✅ Timestamp logging utility
	- Add centralized helper emitting ISO-8601 UTC timestamps (e.g., `tprint()`), used by operations.
	- Tests: simple unit asserting format and monotonic non-decreasing behavior.
68. ✅ Heartbeat implementation (mute audio)
	- Wrap long-running mute FFmpeg invocation with background thread emitting heartbeat lines at adaptive interval (5s if >50 windows else 8s).
	- Include context string: `muting audio track <n> (<lang>)`.
69. ✅ Heartbeat extension (all FFmpeg ops)
	- Extend adapter to support heartbeat for extraction (audio/subtitles) and remux with operation-specific intervals (audio=8s, subs=12s, remux=6s).
	- Heuristic trigger: presence of `-af`, `-vf`, `-map`, `-acodec`, mute filter graph, or explicit context parameter.
70. ✅ Legacy verbose phrase preservation
	- Ensure pre-existing verbose log lines required by tests (e.g., "Applying mute windows") still appear in addition to heartbeats.
71. ✅ Structured execution log integration
	- Record heartbeat events (timestamp, elapsed, context) in execution log (FR-034) without excessive volume (interval-based only).
72. ✅ Test adaptation & bypass toggle
	- Provide environment variable (e.g., `CENSORR_NO_HEARTBEAT`) or flag hook to disable heartbeat during specific deterministic unit tests.
	- Adapt affected FFmpeg adapter and remux tests to either mock heartbeat path or disable it.
73. ✅ Documentation & spec update
	- Append FR-064 to spec; document intervals, markers (`HEARTBEAT`), and disable toggle guidance.
74. ✅ Commit convention reinforcement
	- Git commit messages for features include: summary line, bullet list of key changes, rationale/observability improvements section when relevant.

Status: 67–73 implemented; 72 partially pending (existing tests currently being refactored to align with heartbeat path). Marking feature baseline as complete; remaining minor test refactors tracked separately.