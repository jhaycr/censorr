# TODO

- [ ] Add audio energy QC: compute RMS over profanity windows on the muted audio artifact and assert sufficiently low energy vs control segments (similar to subtitle QC). Integrate into pipeline after `audio_mute` and before `video_remux`, with a `--continue-on-audio-qc-fail` flag.
