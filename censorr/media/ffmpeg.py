import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from censorr.audio.windows import MuteWindow
from censorr.config.schema import AudioConfig
from censorr.media.probe import probe
from censorr.media.progress import run_with_progress

# R13: FFmpeg encodes these well; eac3 above 5.1 (6ch) can't round-trip.
GOOD_ENCODE_CODECS = {"aac", "ac3", "eac3", "flac", "opus"}
# Used only when the source bitrate is unknown -- a re-encode to the same codec
# preserves the source's actual bitrate (so the clean copy matches the original)
# and only falls back to these conservative defaults when ffprobe reports none.
_DEFAULT_BITRATES = {"aac": "192k", "ac3": "448k", "eac3": "448k", "opus": "128k"}

CENSORED_TITLE = "English (Censored)"
CAPTIONS_TITLE = "English (Muted Dialogue)"


def extract_subtitle_stream(source: Path, stream_index: int, workdir: Path) -> Path:
    """Dump one subtitle stream to a standalone SRT file for parsing."""
    out_path = workdir / f"subtitle_{stream_index}.srt"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(source),
            "-map", f"0:{stream_index}",
            "-c:s", "srt",
            str(out_path),
        ],
        check=True,
    )
    return out_path


def resolve_audio_codec(
    source_codec: str, channels: int, cfg: AudioConfig, source_bitrate: int | None = None
) -> tuple[str, str | None]:
    """R13 codec policy: reuse the source codec when FFmpeg encodes it well;
    otherwise fall back to the configured default (channel preservation is
    automatic -- we never force a downmix). A per-preset target_codec wins.
    Returns (codec, bitrate); bitrate is None for lossless codecs (flac).

    When reusing the source codec, the source's own bitrate is preserved so the
    clean copy matches the original instead of shrinking to the codec default.
    """
    if cfg.target_codec:
        return cfg.target_codec, _bitrate_for(cfg.target_codec, cfg)

    eac3_too_many_channels = source_codec == "eac3" and channels > 6
    if source_codec in GOOD_ENCODE_CODECS and not eac3_too_many_channels:
        return source_codec, _reencode_bitrate(source_codec, cfg, source_bitrate)

    return cfg.fallback_codec, cfg.fallback_bitrate


def _bitrate_for(codec: str, cfg: AudioConfig) -> str | None:
    if codec == "flac":
        return None
    return _DEFAULT_BITRATES.get(codec, cfg.fallback_bitrate)


def _reencode_bitrate(codec: str, cfg: AudioConfig, source_bitrate: int | None) -> str | None:
    """Preserve the source bitrate on a same-codec re-encode; fall back to the
    codec default when the container didn't report one. flac stays bitrate-less."""
    if codec == "flac":
        return None
    if source_bitrate and source_bitrate > 0:
        return str(source_bitrate)
    return _DEFAULT_BITRATES.get(codec, cfg.fallback_bitrate)


class RemuxPlan(BaseModel):
    source: Path
    temp_output: Path
    video_stream: int
    audio_stream: int
    audio_mode: Literal["mute_encode", "copy"]
    audio_codec: str | None = None
    audio_bitrate: str | None = None
    windows: list[MuteWindow] = []
    masked_sub: Path | None = None
    captions_sub: Path | None = None
    stream_titles: dict[str, str] = {}
    language: str = "en"
    fingerprint: str


def _mute_filter_script(windows: list[MuteWindow], audio_stream: int) -> str:
    stages = ",".join(
        f"volume=enable='between(t,{w.start_s},{w.end_s})':volume=0" for w in windows
    )
    return f"[0:{audio_stream}]{stages}[aout]"


def remux(plan: RemuxPlan, *, on_progress: Callable[[float], None] | None = None) -> Path:
    """The only place that builds the FFmpeg remux command (design's "only
    subprocess site" for media/). Args as a list, never a shell; the mute
    filtergraph goes to a script file, never the command line (N3).

    Single pass: video always stream-copied; audio muted+re-encoded per
    R13, or stream-copied verbatim in "copy" mode (clean/subtitles_only).
    Masked subtitle + mute-captions embedded, chapters/global metadata
    preserved, output tagged with CENSORR_FINGERPRINT (R10).
    """
    plan.temp_output.parent.mkdir(parents=True, exist_ok=True)

    inputs = ["-i", str(plan.source)]
    next_input_index = 1
    masked_input_index: int | None = None
    captions_input_index: int | None = None
    if plan.masked_sub is not None:
        inputs += ["-i", str(plan.masked_sub)]
        masked_input_index = next_input_index
        next_input_index += 1
    if plan.captions_sub is not None:
        inputs += ["-i", str(plan.captions_sub)]
        captions_input_index = next_input_index
        next_input_index += 1

    args = ["ffmpeg", "-y", "-loglevel", "error", *inputs]

    if plan.audio_mode == "mute_encode":
        filter_path = plan.temp_output.parent / "mute.filter"
        filter_path.write_text(_mute_filter_script(plan.windows, plan.audio_stream))
        args += ["-filter_complex_script", str(filter_path)]
        audio_map = ["-map", "[aout]", "-c:a", plan.audio_codec or "aac"]
        if plan.audio_bitrate:
            audio_map += ["-b:a", plan.audio_bitrate]
    else:
        audio_map = ["-map", f"0:{plan.audio_stream}", "-c:a", "copy"]

    args += ["-map", f"0:{plan.video_stream}", "-c:v", "copy"]
    args += audio_map
    args += ["-map_metadata", "0", "-map_chapters", "0"]
    args += [
        "-metadata:s:a:0", f"language={plan.language}",
        "-metadata:s:a:0", f"title={plan.stream_titles.get('audio', CENSORED_TITLE)}",
        "-disposition:a:0", "default",
    ]

    if masked_input_index is not None:
        args += ["-map", f"{masked_input_index}:0", "-c:s", "srt"]
        args += [
            "-metadata:s:s:0", f"language={plan.language}",
            "-metadata:s:s:0", f"title={plan.stream_titles.get('subtitle', CENSORED_TITLE)}",
        ]
    if captions_input_index is not None:
        captions_out_index = 1 if masked_input_index is not None else 0
        args += ["-map", f"{captions_input_index}:0", "-c:s", "srt"]
        args += [
            f"-metadata:s:s:{captions_out_index}", f"language={plan.language}",
            f"-metadata:s:s:{captions_out_index}",
            f"title={plan.stream_titles.get('captions', CAPTIONS_TITLE)}",
            f"-disposition:s:{captions_out_index}", "forced+default",
        ]

    args += ["-metadata", f"CENSORR_FINGERPRINT={plan.fingerprint}"]
    args += ["-progress", "pipe:1", str(plan.temp_output)]

    total_duration_s = probe(plan.source).duration_s
    run_with_progress(
        args,
        total_duration_s=total_duration_s,
        on_progress=on_progress,
        context=f"remuxing {plan.source.name}",
    )

    return plan.temp_output
