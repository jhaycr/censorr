# Research: Single-Pass Mute-During-Remux Validation

Gathered 2026-07-15. Validates the one-FFmpeg-invocation design from ffmpeg-techniques.md.

## The invocation

```
ffmpeg -i source.mkv -i masked.srt \
  -filter_complex "[0:a:IDX]volume=0:enable='between(t,12.3,15.1)+between(t,88.0,90.2)+...'[aout]" \
  -map 0:v:0 -c:v copy \
  -map "[aout]" -c:a eac3 -b:a 640k \
  -map 1:0 -c:s srt -metadata:s:s:0 language=eng -metadata:s:s:0 title="English (Censored)" \
  -disposition:a:0 default -metadata:s:a:0 language=eng -metadata:s:a:0 title="English (Censored)" \
  -map_metadata 0 -map_chapters 0 \
  output.mkv
```

Validated mechanics:
- `volume` supports **compound enable expressions**: `enable='between(t,a,b)+between(t,c,d)+…'` — `+` is logical OR in FFmpeg expression syntax. One filter handles all windows.
- A `filter_complex`-labeled stream **must be re-encoded** (that's inherent — filtered PCM can't be bit-copied), while unfiltered streams (`0:v:0`, chapters, metadata) are copied untouched. Video is never re-encoded.
- No seeking involved — full-stream single pass; window boundaries are sample-accurate enough (±one filter frame, ~10 ms) for this purpose.

## Filter-string length

Worst realistic case: ~300 windows × ~28 chars ≈ 8.5 KB. Linux `ARG_MAX` is ~2 MB — no practical risk in the Docker/Linux deployment. Belt-and-braces anyway: FFmpeg supports **`-filter_complex_script file`** (filtergraph read from a file); v2's adapter should write the filtergraph to `<workdir>/mute.filter` and always use the script form — also makes every job's filter inspectable/debuggable after the fact, which serves the auditability goal.

## When staged (multi-pass) processing is still needed

1. **Audio QC** needs to measure the muted output against the original. With single-pass remux the muted audio only exists inside the output container — QC probes the *output file's* audio stream directly (ffprobe/ffmpeg can read from the MKV; no extraction to WAV needed — decode windows on the fly with `-ss/-t` per window, which reads only small segments).
2. **Debugging** (`--keep-intermediates`): optional staged mode extracts audio first, mutes to a discrete file, then remuxes — same stages, two invocations, intermediate artifacts inspectable.
3. **Future word-alignment provider**: needs raw audio segments for the flagged windows — extracted on demand per segment (seconds of audio), not whole-track WAV.

So: single-pass is the default path; the *stage structure* in code (plan windows → build filter → remux → verify) stays identical in both modes — only the FFmpeg invocation strategy differs.

## Progress reporting

`-progress pipe:1` emits `out_time_us=...` key-value lines on stdout; divided by ffprobe-known duration → fraction complete, written into the job record for `/jobs/{id}`. Heartbeat log lines derive from the same reader (keep `CENSORR_NO_HEARTBEAT=1`-style suppression for tests).

Sources: [FFmpeg filters documentation](https://ffmpeg.org/ffmpeg-filters.html) (volume filter, timeline editing/enable, filter_complex_script), [FFmpeg filtering guide](https://trac.ffmpeg.org/wiki/FilteringGuide)
