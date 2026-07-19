# Research: Prior Art — Similar Tools

Gathered 2026-07-15. What exists, what's worth borrowing, what to avoid.

## cleanvid (closest relative)

Python script: video + SRT in → muted video out. Same core idea as Censorr (subtitle-driven muting via FFmpeg volume filters).

Worth borrowing:
- **Auto-acquire subtitles when missing**: extracts from container, else downloads via `subliminal`. Censorr v1 fails if no embedded subs; a pluggable "subtitle source" chain (embedded → sidecar next to file → optional downloader) directly serves the minimal-input goal. Downloader = post-MVP seam, same pattern as MuteWindowProvider.
- **Word→replacement mappings** (e.g., "sh*t"→"poop") instead of asterisk-only masking — cheap to support in the profanity list schema (v1's schema is `{word, ...}` objects already; add optional `replacement`).
- **`--pad` seconds around windows** as a user-visible knob (v1 hard-codes 0.2 s).
- **Alternative outputs**: EDL files and PlexAutoSkip JSON instead of remuxing. Cheap to emit (it's just the mute-window list serialized) — a good optional output artifact since we compute windows anyway.

Differences/avoid: single-shot script, no service/queue/idempotency, no Plex naming awareness, re-encodes the *entire* audio track (no codec-preservation options like v1's transcode-to-original).

## monkeyplug (same author)

Audio-first variant: uses **Vosk or Whisper speech recognition** rather than subtitles to find profanity — validates the "transcription-based MuteWindowProvider" as a real, proven approach for the post-MVP seam (works when subs are missing/badly synced).

## adeel-raza/profanity-filter

AI-powered (Whisper tiny→large): defaults to audio-based detection, subtitle-based as fallback; mutes intervals rather than cutting. Confirms the same architecture split: detection provider (subtitle vs. ASR) is orthogonal to the muting mechanism.

## Takeaways for v2

1. Subtitle-driven detection is the standard baseline across tools; ASR is the standard upgrade path — our provider-interface seam matches the field.
2. Nobody else handles Plex naming/editions/sidecar conventions or Arr integration — that's Censorr's differentiator; keep it first-class.
3. Adopt: subtitle-source chain, optional replacement words, configurable padding, optional EDL/PlexAutoSkip export.

Sources: [cleanvid](https://github.com/mmguero/cleanvid), [monkeyplug](https://github.com/mmguero/monkeyplug), [profanity-filter](https://github.com/adeel-raza/profanity-filter)
