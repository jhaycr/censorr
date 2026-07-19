# Research: Plex Behavior Verification (deeper dive)

Gathered 2026-07-15. Follow-up on the Q8 decision (keep `.censorr` sidecar token) and library access control.

## Sidecar naming: what's verifiable

- Official docs specify **strict `Name.lang.ext`** (or `Name.lang.flag.ext` with flags `forced`, `sdh`, `cc`) and warn that a missing/unparsed language code makes the track show as **"Unknown"** — and "Unknown"-language tracks are excluded from automatic subtitle selection logic (they never match a user's preferred language).
- Forum history shows external-sub language detection regressions across PMS versions (e.g. "Plex Agent — All External Subs now Unknown"); parsing of non-spec names is the fragile area.
- The official docs don't define behavior for **extra unknown tokens** (like `.censorr`) — it's undocumented territory that has changed across versions.

## Reconciling with Josh's decision (Q8)

Josh's deployment empirically resolves `Stem.en.censorr.srt` correctly today — his evidence wins for the default. Design mitigations so a PMS update can't silently break subtitles:
1. Sidecar token is **config-driven** (`naming.sidecar_token = "censorr"`), with `""` producing pure-spec names — one-line escape hatch.
2. Token placement fixed as `<stem>.<lang>.<token>.<ext>` (language adjacent to stem, matching what works today).
3. When a source track is SDH/forced, spec flags are appended in Plex's position and the QC/verification step logs the final names, so any breakage is visible in job output rather than discovered on the TV.

## Editions display

- `{edition-...}` requires PMS ≥ 1.28.1 with the new Plex Movie agent; **displaying** the edition chip requires Plex Pass on the server admin. Without it the file still plays fine and sorts as a separate version — naming is correct regardless. No action needed; document in README.

## Separate library access control (the TV clean-root strategy, Q7)

- Plex libraries are the unit of sharing: Home/managed users can be restricted per-library, and label-based restrictions exist for finer control. A `TV (Clean)` library pointed at the clean root gives kids-profile isolation with zero per-item management — confirms Q7's design.
- Same mechanism works for movies if desired later (clean movies live beside originals as editions in the same library by default, so movie isolation would need its own clean root — out of scope for now, noted as a config possibility).

Sources: [Plex: Adding local subtitles](https://support.plex.tv/articles/200471133-adding-local-subtitles-to-your-media/), [Plex: Configuring subtitle support](https://support.plex.tv/articles/200471113-configuring-subtitle-support/), [Plex forum: external subs become Unknown](https://forums.plex.tv/t/plex-agent-all-external-subs-now-unknown/636354), [Plex: Multiple editions](https://support.plex.tv/articles/multiple-editions/)
