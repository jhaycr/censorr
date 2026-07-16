# Research: Plex Naming Rules (External Validation)

Ground truth for how outputs must be named/placed so Plex resolves them. Gathered 2026-07-15 via web research.

## Movies — editions

- Format: `Movie Name (Year) {edition-EditionName}.ext`, e.g. `Blade Runner (1982) {edition-Director's Cut}.mkv`.
- Requires the non-legacy **Plex Movie agent** (PMS ≥ 1.28.1); *displaying* the edition label requires **Plex Pass** on the server admin account. Without Plex Pass the file still plays but the edition chip may not render — the tag remains the correct convention regardless.
- Plex recommends the edition tag in **both folder name and filename**. v1 only tags the filename — v2 should consider tagging the movie folder too when the movie lives in its own folder. Quality/version tokens can coexist: `Movie (1982).1080p.h264 {edition-Director's Cut}.mkv`.
- Multiple files with the same title/year but different editions appear as separate selectable editions of one movie entry.

Sources: [Plex: Multiple Editions](https://support.plex.tv/articles/multiple-editions/), [Plex: Naming movie files](https://support.plex.tv/articles/naming-and-organizing-your-movie-media-files/), [Plex: Multi-Version Movies](https://support.plex.tv/articles/200381043-multi-version-movies/)

## TV episodes

- Editions are **not supported for TV**. Standard layout: `Show Name/Season 01/Show Name - s01e01 - Title.ext`.
- Distinguishing a censored copy therefore requires either a separate library root, a differently named show folder, or Plex "versions" (same folder, extra file — but Plex versions give the *player* a choice, not a restriction, so for family-filtering purposes a **separate library with its own access controls** is the meaningful mechanism).

Source: [Plex: Naming TV Show files](https://support.plex.tv/articles/naming-and-organizing-your-tv-show-files/)

## Subtitle sidecars

- Format: `<video_stem>.<lang>.<flags>.<ext>` where `<lang>` is ISO-639-1 or ISO-639-2/B and recognized flags are `forced`, `sdh`, `cc` (sdh/cc need PMS ≥ 1.20.3 + new agent). Examples: `Avatar (2009).en.srt`, `Avatar (2009).en.forced.ass`, `Avatar (2009).en.sdh.srt`.
- **The stem must match the video filename exactly** — including any `{edition-...}` tag.
- Extra unrecognized tokens (like v1's `.censorr.`) are not part of the spec; behavior varies by PMS version (may surface as a stream title or break flag parsing). Safest: stick to spec tokens.

Sources: [Plex: Adding local subtitles](https://support.plex.tv/articles/200471133-adding-local-subtitles-to-your-media/), [Plex forum: subtitle naming for forced/HI](https://forums.plex.tv/t/subtitle-naming-conventions-for-forced-and-hearing-impaired/78124)

## External audio: NOT supported

- Plex has **no official sidecar audio support** (long-standing feature request; only unofficial community hacks with `.mka` files exist and they don't work across clients).
- **Consequence: muted audio MUST be remuxed into the container.** The clean audio track should be the default/first audio stream, and (for a family-safe file) the original unmuted track should be pruned or clearly deprioritized — pruning is the only way to *guarantee* clients don't pick the profane track.
- In-container stream disposition matters: set the muted track as `default`, give tracks meaningful titles (e.g. "English (Censored)"), correct `language` tags.

Sources: [Plex forum: External Audio track/file support (feature request)](https://forums.plex.tv/t/external-audio-track-file-support/384059), [Plex forum: unofficial external audio tool](https://forums.plex.tv/t/release-external-audio-track-support/390714)

## Practical v2 naming targets

| Case | Target |
|---|---|
| Movie video | `Movie (2024) {edition-Censorr}.mkv` (same folder as original, or own folder also tagged) |
| Movie subtitle | `Movie (2024) {edition-Censorr}.en.srt` (+ `.sdh` variant only if source was SDH) |
| Episode video | `<clean-root or tagged show folder>/Show/Season 01/Show - s01e01 - Title.mkv` (filename unchanged) |
| Episode subtitle | same stem + `.en.srt`, next to the episode |
| Audio | embedded in container; muted track first + default, titled e.g. `English (Censored)`; original track pruned by default |
