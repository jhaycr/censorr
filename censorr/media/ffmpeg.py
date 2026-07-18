import subprocess
from pathlib import Path


def extract_subtitle_stream(source: Path, stream_index: int, workdir: Path) -> Path:
    """Dump one subtitle stream to a standalone SRT file for parsing.

    A minimal, single-purpose subprocess call -- the full remux/mute
    machinery (RemuxPlan, filtergraph, progress parsing) is Step 9.
    """
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
