# Decision: Base Image — python:3.12-alpine vs python:3.12-slim

2026-07-16. Requested by Josh: decide, then adversarially review the choice. Criteria: minimal memory usage, secure for general (LAN-only, no-auth) usage.

## Measured facts (this host, this week)

| | python:3.12-alpine | python:3.12-slim |
|---|---|---|
| All 7 v2 deps install from wheels, no compiler | ✅ verified (musllinux) | ✅ (manylinux, by definition) |
| ffmpeg via package manager | **8.1.2** (apk) | 7.1.5 (Debian trixie) |
| `/usr` after ffmpeg install | **179 MB** | 543 MB (3×) |
| libc | musl | glibc |

Both FFmpeg versions satisfy the design's ≥6 requirement; Alpine's is a full major version newer.

## THE DECISION: Alpine

Rationale in one paragraph: on Josh's two stated criteria the images tie — runtime memory is dominated by CPython + FFmpeg (musl's allocator is marginally leaner, glibc marginally hungrier; noise either way), and for a LAN-only service both distros are patched actively and the real security posture comes from the design (non-root, API container without media mounts, one published port). With the stated criteria tied, tiebreakers decide: Alpine ships a **newer FFmpeg** (8.x vs Debian's older stable), is **~half the disk**, and — decisively — the choice is **cheaply reversible**: because the Dockerfile needs no compiler stage on either base (verified), switching later is a two-line change (`FROM` + package-install line).

## Adversarial review

Each attack stated as strongly as I can make it, then the verdict.

**Attack 1 — "The savings are trivial; the risk is not."** 250 MB of disk is invisible on a media server holding terabytes; meanwhile *any* future dependency that lacks musllinux wheels breaks the build. You're trading nothing for unbounded forward risk. That's exactly backwards for a solo-maintained homelab tool where a burned evening on a `gcc: not found` pip failure is the most realistic annoyance.
*Verdict: strongest attack, partially lands.* Mitigations that keep it survivable: (a) v2's dep set is deliberately curated — 5 core + 2 serve, only two compiled (pydantic-core, rapidfuzz), both with strong musllinux track records; (b) new-dep additions are rare, and the failure is loud and instantly diagnosable, with a documented 2-line escape hatch in this file; (c) the implementation plan pins deps, so nothing changes under us. Accepted risk, documented.

**Attack 2 — "The [align] extra can never run on Alpine."** ctranslate2 and pytorch publish glibc-only wheels (verified on PyPI, 2026-07). Your own roadmap contains a feature the base image cannot host.
*Verdict: true but misdirected.* Torch-class dependencies don't belong in the webhook/worker image on *either* base — a Debian- or CUDA-based sidecar image for the alignment provider is the right architecture regardless (heavyweight optional deps behind an optional container, matching the `censorr[align]` extra design). Alpine forces the good architecture; slim would merely permit a worse one.

**Attack 3 — "musl performance/compat gremlins."** CPython on musl benchmarks slower in allocator-heavy workloads; musl DNS had TCP-fallback bugs; obscure libc differences bite at 2 a.m.
*Verdict: mostly obsolete or irrelevant here.* The pipeline's hot path is FFmpeg (a subprocess, apk-built against musl by Alpine, not us); Python does orchestration, subtitle parsing, and rapidfuzz calls (C++, compiled for musl by its maintainers). musl's DNS TCP fallback landed in musl 1.2.4/Alpine 3.18 (2023). No threading-heavy Python in the design (worker is a sequential loop).

**Attack 4 — "Debian's security team > Alpine's."** Debian has deeper CVE auditing, faster backports for libc-level issues, and slim is the ecosystem-default 'boring' choice; boring wins for infrastructure.
*Verdict: a wash on the facts.* Alpine's smaller package count means fewer *installed* CVEs to begin with; both distros patch FFmpeg and OpenSSL promptly; for a LAN-only, no-auth service behind a home firewall, neither distro's delta is the weak link — the payload parser and path mapping are, and those are ours either way. "Boring" legitimately favors slim, but boring-ness is not worth 2× image size when the exotic parts (musl wheels) are *verified*, not hoped.

**Attack 5 — "Debugging ergonomics."** Alpine's busybox userland lacks bash, GNU coreutils, and familiar flags; when a job wedges at 2 a.m. you'll miss them.
*Verdict: real but minor.* `apk add bash` in a live container takes two seconds when needed; the design's observability (structured job records, retained failed workdirs, filtergraph files on disk) is deliberately built so debugging happens by reading files, not by shelling into containers.

## Flip conditions (what would reverse this decision)

Switch to `python:3.12-slim` if any of these become true:
1. A **core** (non-optional) dependency with glibc-only wheels enters the design.
2. The alignment provider is promoted into the main image rather than a sidecar.
3. Hardware-accelerated **video** encoding enters scope (it's out: video is always stream-copied) — vendor driver stacks assume glibc.
4. Two or more musl-specific bugs consume real debugging time — empirical evidence beats analysis.

The escape hatch, verified buildable today:
```dockerfile
FROM python:3.12-slim            # was: python:3.12-alpine
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg gosu \
    && rm -rf /var/lib/apt/lists/*   # was: apk add --no-cache ffmpeg su-exec
# (entrypoint: s/su-exec/gosu/)
```

Sources: [PEP 656 (musllinux)](https://peps.python.org/pep-0656/), [ctranslate2 wheel tags on PyPI](https://pypi.org/project/ctranslate2/), [PyTorch manylinux-2.28 build platform](https://dev-discuss.pytorch.org/t/pytorch-linux-wheels-switching-to-new-wheel-build-platform-manylinux-2-28-on-november-12-2024/2581), local measurements 2026-07-16.
