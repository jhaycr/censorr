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
18. ✅ Workdir layout and manifest recording (tests)
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

26. Operation flags plumbing
	- Add `continue_on_qc_fail` to execution flags/context (default False); propagate from CLI to operations.
27. MaskSubtitlesOperation: QC step
	- After masking, run QC using same matcher and allow-list; generate `qc_report.json`, log summary; fail by default on residuals.
	- When `continue_on_qc_fail` is True, proceed; attach `qc` metadata to artifact with match count and report path.
28. CLI flag
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