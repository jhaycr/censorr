# Research: FFmpeg Muting & Remux Techniques

Gathered 2026-07-15. Validates/refines v1's approach for the v2 design.

## Muting mechanism

Standard technique (used by v1, cleanvid, and the FFmpeg docs):
```
-af "volume=enable='between(t,START,END)':volume=0"   # one clause per window
```
- Muting **requires re-encoding the audio stream** — a filtered stream cannot be `-c:a copy`. Video is always `-c:v copy` (never re-encode video).
- v1 extracts audio → WAV → applies windows → re-encodes at remux. A leaner v2 pipeline can apply the volume filter **during the remux itself** (single FFmpeg invocation: original container in, filtered+encoded audio and copied video out), eliminating the multi-GB WAV intermediates entirely — directly serving the disk-ballooning concern from Q9. Keep separate-step processing as debug fallback (`--keep-intermediates`).

## Codec preservation constraints (matters for surround)

| Source codec | Re-encode to same | Notes |
|---|---|---|
| AAC / AC3 / EAC3 5.1 | ✅ fine | FFmpeg native encoders good |
| EAC3 7.1 | ❌ encoder capped at 5.1 | error: "channel layout 7.1 not supported" |
| TrueHD / Atmos | ⚠️ impractical | encoder exists but Atmos metadata lost; community practice: don't re-encode TrueHD |
| DTS / DTS-HD MA | ⚠️ DTS encoder is lossy/mediocre | common practice: transcode to EAC3 640k |

**v2 default policy (needs to be explicit in design)**: mute → re-encode to the *original codec* when FFmpeg encodes it well (aac, ac3, eac3 ≤5.1, flac, opus); otherwise fall back to `eac3 640k` (≤5.1) with channel-count preservation where possible, and log the substitution clearly. Configurable per-preset (`audio.target_codec`, `audio.bitrate`). This formalizes what v1's `audio_transcode_to_original` gestured at, with the failure cases actually handled.

## Stream disposition & metadata (Plex resolution inside the container)

Beyond filenames, Plex/clients pick tracks by container flags — v1 ignores all of this:
```
-disposition:a:0 default          # muted track = default
-metadata:s:a:0 title="English (Censored)"
-metadata:s:a:0 language=eng      # ISO 639-2
-disposition:s:0 default          # masked subtitle = default (or 0 to unset)
-metadata:s:s:0 title="English (Censored)" -metadata:s:s:0 language=eng
```
With clean-only output (Q6) there's one audio track anyway, but disposition+title+language must still be set correctly — some clients show "Unknown" tracks otherwise.

## Remux invocation shape

```
ffmpeg -i original.mkv \
  -map 0:v:0 -c:v copy \
  -map 0:a:<selected> -af "<mute windows>" -c:a <target codec+bitrate> \
  -map 0:s:<masked>? OR -i masked.srt -map 1:0 -c:s srt/copy \
  <dispositions/metadata> output.mkv
```
- MKV accepts SRT/ASS/PGS subtitle codecs; MP4 needs `mov_text` conversion — v2 should default output container to **MKV always** (v1 keeps source extension; MP4 sources + SRT subs would fail or need conversion).
- Chapters and global metadata are preserved by default with `-map_metadata 0 -map_chapters 0` — include explicitly.

## Progress & heartbeat

Keep v1's heartbeat pattern but add `-progress pipe:1` parsing: FFmpeg emits `out_time_us` — combined with `ffprobe` duration this yields **percentage progress** for the job-status API (`/jobs/{id}` can report `progress: 0.62`), a genuine improvement over v1's bare elapsed-time heartbeats.

Sources: [FFmpeg filters docs](https://ffmpeg.org/ffmpeg-filters.html), [Tdarr issue #891 — EAC3 7.1 unsupported](https://github.com/HaveAGitGat/Tdarr/issues/891), [AVSForum TrueHD→EAC3 practice](https://www.avsforum.com/threads/audio-conversion-of-a-truehd-video-to-e-ac3-dd-using-ffmpeg-to-convert.3189351/), [OTTVerse audio transcode guide](https://ottverse.com/transcode-audio-codec-ffmpeg-without-changing-video/)
