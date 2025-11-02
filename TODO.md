# TODO

- [ ] Add audio energy QC: compute RMS over profanity windows on the muted audio artifact and assert sufficiently low energy vs control segments (similar to subtitle QC). Integrate into pipeline after `audio_mute` and before `video_remux`, with a `--continue-on-audio-qc-fail` flag.
- [ ] Slim ffmpeg in Dockerfile.tool: explore pinned static builds or codec-pruned packages, document size diffs, and ensure CI smoke tests still pass.
- [ ] Record image sizes automatically: add a lightweight script or CI step that reports current webhook/worker image footprints and fails when size deltas exceed agreed thresholds.
