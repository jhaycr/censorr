# Adversarial Review #1 — Findings & Disposition

2026-07-16. Subagent adversarial review of `design/detailed-design.md` (pre-revision), requested by Josh. Full report retained below the disposition table. Design revised in response the same day.

## Disposition

| # | Sev | Finding (short) | Disposition |
|---|---|---|---|
| C1 | CRIT | Q16 sidecar reversal not propagated (R4/R5/publish/tests) | **Fixed** — full design rewrite; sidecar conditional everywhere; default-path test asserts *no* sidecar |
| C2 | CRIT | PGS/VOBSUB bitmap subs unhandled | **Fixed** — text-codec filter in select_tracks; bitmap never passed to output; falls to source chain → skipped(`no_text_subtitles`) |
| C3 | CRIT | Zero-match behavior undefined | **Josh decided**: TV → publish stream-copy to clean root; movies → `skipped_clean`. Captions track omitted when empty |
| C4 | CRIT | Edition-tag idempotency → self-overwrite; reprocess re-ingests outputs | **Fixed + Josh decided**: hard invariant output≠source (`JobValidationError`); existing tag → **combine** `{edition-<orig> Censorr}`; outputs self-marked via `CENSORR_FINGERPRINT` MKV metadata and skipped on ingest |
| C5 | CRIT | tv-clean not mounted in compose | **False positive** — compose already mounts `MEDIA_PATH_TV_CLEAN`. Valid residue adopted: worker startup writability check on clean root; "validated" claim softened to config-syntax only |
| M1 | MAJ | Fingerprint store undefined; record growth | **Fixed** — fingerprint embedded in output MKV metadata (self-describing outputs, survives record GC); `source_path` dropped from hash; job-record TTL added |
| M2 | MAJ | No dedup / lease renewal / mid-job source replacement | **Fixed** — queued same-source dedup; lease renewal on progress ticks; pre-publish source re-stat |
| M3 | MAJ | Stale clean outputs never removed | **Fixed** — upgrade path deletes old outputs via `deletedFiles` → plan_names; new `censorr reconcile` command for rename/delete drift |
| M4 | MAJ | API existence-check impossible without mounts | **Fixed** — API = prefix-mapping only; worker checks existence |
| M5 | MAJ | Audio lang ≠ sub lang undefined | **Josh decided**: proceed **subtitles-only** (mask subs, stream-copy audio, no muting, no captions track; audio QC skipped) |
| M6 | MAJ | No-subtitles outcome unclassified | **Josh decided**: skip with visible reason + `fail_on_no_subtitles` escape; **subtitle downloader seam prioritized post-MVP** |
| M7 | MAJ | Allowlist has no home | **Fixed** — wordlist schema `{words:[], allowlist:[]}`; user allowlist extends bundled |
| M8 | MAJ | Stage contract / RemuxPlan / ResolvedConfig undefined; config keys missing; invalid TOML | **Fixed** — PipelineContext + stage I/O contract defined; missing keys added; TOML corrected |
| M9 | MAJ | Clean-root derivation rule unspecified | **Fixed** — explicit season-dir-walk algorithm + shallow-path refusal, in the naming golden table |
| M10 | MAJ | Arr may not send custom headers | **Fixed** — secret accepted via `?token=` query param (fits Q4 precedent) and header; header support to be verified during implementation |
| m1 | MIN | Control-audio ±3 dB false-fails lossy fallback | **Fixed** — control integrity measured within-output (distribution-relative); calibrated against eac3-fallback fixture |
| m2 | MIN | R2 guarantee conditional on subtitle sync | **Fixed** — assumption stated; duration-divergence warning added |
| m3 | MIN | ASS styling / captions format unspecified | **Fixed** — match on plaintext, masks re-injected; captions track always SRT |
| m4 | MIN | Assorted drift (no-Year fallback, --mute-windows, inspect wording, folder tag, reprocess extras) | **Fixed** — all items addressed; folder edition tag explicitly rejected (original shares the folder) |

## Reviewer's overall verdict (verbatim)

> This is a genuinely strong planning artifact by homelab standards — the research is real, decisions carry rationale, and the Q16 symmetric-QC amendment shows the process self-correcting. But it is **not yet handoff-ready for a fresh-context agent.** [...] Fix the 5 criticals and define the ~8 major decision gaps and this becomes an excellent build spec.

(Full finding details were delivered in-session; the substance of every finding is reflected in the disposition above and the revised design.)
