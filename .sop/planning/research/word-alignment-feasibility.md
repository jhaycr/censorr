# Research: Word-Level Alignment Feasibility (post-MVP seam)

Gathered 2026-07-15. Out of MVP scope (Q10), but the `MuteWindowProvider` interface must be designed against a real future implementation.

## Candidate stacks

| Tool | Approach | Word-timestamp accuracy | Notes |
|---|---|---|---|
| **faster-whisper** | CTranslate2 Whisper reimpl | ~±500 ms (whisper-native word ts) | 4× faster than openai-whisper, CPU-viable with int8; simplest dependency |
| **WhisperX** | faster-whisper + wav2vec2 forced alignment | **<100 ms (±50 ms)** | the accuracy needed for word-level muting; adds pyannote/wav2vec2 deps; alignment adds ~10–20% runtime |
| **stable-ts** | Whisper timestamp stabilization | intermediate | lighter than WhisperX, less precise |
| ASR-free forced alignment | align *known subtitle text* to audio (e.g., wav2vec2 CTC segmentation, easytranscriber-style) | <100 ms | **best fit**: we already know the words from subtitles — no full transcription needed, much cheaper than ASR |

## Key insight for the seam design

Two distinct future providers, both cheaper than "transcribe everything":

1. **AlignmentProvider** (most likely v2.1): input = subtitle entry text + audio segment (we already know *roughly where* the word is — the subtitle entry's time range); output = word-level timing within that segment. Forced alignment on a few-second clip is fast even on CPU. This narrows mute windows from sentence to word without any ASR.
2. **TranscriptionProvider** (later): full ASR (monkeyplug-style) for media with no/bad subtitles; produces both subtitle text *and* windows.

## Interface consequence

`MuteWindowProvider.windows(job) -> list[MuteWindow]` where the MVP implementation is `SubtitleEntryProvider` (entry span ± pad). The interface must receive: the selected subtitle entries **with match details (which word matched, where in the text)**, the source media path, and the resolved settings. MuteWindow keeps `source` ("subtitle" | "alignment" | "external" | "transcription") and `reason` fields (v1 already has these — keep).

**Design guardrails so the seam stays real**: providers must be pure "compute windows" components — no FFmpeg execution, no file writes into the pipeline's workdir; heavyweight deps (torch etc.) live behind an optional extra (`pip install censorr[align]`) and are imported lazily only when that provider is configured.

Sources: [WhisperX](https://github.com/m-bain/whisperX), [Modal: choosing Whisper variants](https://modal.com/blog/choosing-whisper-variants), [faster-whisper guide](https://localaimaster.com/blog/faster-whisper-guide), [KBLab easytranscriber (GPU forced alignment)](https://kb-labb.github.io/posts/2026-02-26-easytranscriber/)
