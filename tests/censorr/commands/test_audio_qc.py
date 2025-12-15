import json
import subprocess
from pathlib import Path

import pytest

from censorr.commands.audio_qc import AudioQC


class FakeFFmpeg:
    def __init__(self):
        self.calls = []

    def run(self, cmd, capture_output=True, text=True, **kwargs):
        self.calls.append(cmd)
        if cmd[0] == "ffprobe":
            payload = {"format": {"duration": "60.0"}}
            return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")

        if cmd[0] == "ffmpeg":
            try:
                start = float(cmd[cmd.index("-ss") + 1])
                end = float(cmd[cmd.index("-to") + 1])
            except Exception as exc:  # pragma: no cover - defensive
                raise AssertionError(f"Malformed ffmpeg command: {cmd}") from exc

            # Treat windows roughly matching mute spans as muted regions
            if 10 <= start < 12 or 20 <= start < 22:
                mean = -50.0
            else:
                mean = -10.0

            stderr = f"[Parsed_volumedetect_0] mean_volume: {mean} dB\n"
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr=stderr)

        raise AssertionError(f"Unexpected command: {cmd}")


def write_windows(tmp_path: Path):
    windows_path = tmp_path / "mute_windows.json"
    windows = [
        {"start": 10.0, "end": 12.0},
        {"start": 20.0, "end": 22.0},
    ]
    windows_path.write_text(json.dumps(windows), encoding="utf-8")
    return windows_path


def test_audio_qc_passes_when_delta_large(tmp_path, monkeypatch):
    fake = FakeFFmpeg()
    monkeypatch.setattr(subprocess, "run", fake.run)

    windows_path = write_windows(tmp_path)
    qc = AudioQC()

    report_path = qc.do(
        muted_audio_path="/fake/audio.m4a",
        windows_path=str(windows_path),
        output_dir=str(tmp_path),
        threshold_db=20.0,
    )

    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["delta_db"] >= 20.0


def test_audio_qc_fails_when_delta_small(tmp_path, monkeypatch):
    fake = FakeFFmpeg()
    monkeypatch.setattr(subprocess, "run", fake.run)

    windows_path = write_windows(tmp_path)
    qc = AudioQC()

    report_path = qc.do(
        muted_audio_path="/fake/audio.m4a",
        windows_path=str(windows_path),
        output_dir=str(tmp_path),
        threshold_db=45.0,
    )

    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert report["delta_db"] < 45.0
