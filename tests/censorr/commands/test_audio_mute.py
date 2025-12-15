import json
from pathlib import Path

import pytest

from censorr.commands.audio_mute import AudioMute


class FakePopen:
    """Minimal Popen fake to simulate ffmpeg call.

    - Immediately appears finished (poll() != None)
    - Creates the output file at the last argument path
    - Captures the command for assertions via a shared list
    """

    calls = []

    def __init__(self, cmd, stdout=None, stderr=None, text=False, **kwargs):
        self.cmd = cmd
        FakePopen.calls.append(cmd)
        self.returncode = 0
        # Create the output file (last arg in our ffmpeg command)
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")

    def poll(self):
        return 0

    def communicate(self):
        return ("", "")


class FakePopenFailure(FakePopen):
    """Fails with non-zero return code to exercise error handling."""

    def __init__(self, cmd, stdout=None, stderr=None, text=False, **kwargs):
        super().__init__(cmd, stdout=stdout, stderr=stderr, text=text, **kwargs)
        self.returncode = 1

    def communicate(self):
        return ("", "boom")


def write_csv(path: Path, rows: list[tuple[float, float]]):
    header = "start_ms,end_ms\n"
    lines = [header]
    for s, e in rows:
        lines.append(f"{s},{e}\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def test_applies_mutes_and_writes_sidecar(tmp_path, monkeypatch):
    # Prepare input paths
    audio_in = tmp_path / "audio_eng_Main.wav"
    audio_in.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    matches_csv = tmp_path / "matches.csv"
    # Two non-overlapping windows in milliseconds
    write_csv(matches_csv, [(1000, 2000), (2500, 3000)])

    # Patch Popen to avoid real ffmpeg
    FakePopen.calls = []
    monkeypatch.setattr("subprocess.Popen", FakePopen)

    out_dir = tmp_path / "out"
    op = AudioMute()
    muted_path, windows_path = op.do(
        audio_file_path=str(audio_in),
        matches_csv_path=str(matches_csv),
        output_dir=str(out_dir),
    )

    # Output files exist
    assert Path(muted_path).exists()
    assert Path(windows_path).exists()

    # Sidecar JSON has the expected windows in seconds
    windows = json.loads(Path(windows_path).read_text(encoding="utf-8"))
    assert windows == [{"start": 1.0, "end": 2.0}, {"start": 2.5, "end": 3.0}]

    # Validate ffmpeg command and filter
    cmd = FakePopen.calls[-1]
    assert cmd[0] == "ffmpeg"
    assert "-af" in cmd
    af = cmd[cmd.index("-af") + 1]
    # Combined OR via '+' and formatted to 3 decimals
    assert "volume=enable='between(t,1.000,2.000)+between(t,2.500,3.000)':volume=0" == af
    assert "-c:a" in cmd and cmd[cmd.index("-c:a") + 1] == "pcm_s16le"


def test_merges_overlapping_windows(tmp_path, monkeypatch):
    audio_in = tmp_path / "a.wav"
    audio_in.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    matches_csv = tmp_path / "matches.csv"
    # Overlapping windows (1000-2000) and (1900-2100) should merge to (1.0-2.1)
    # plus a separate window (3000-3200)
    write_csv(matches_csv, [(1000, 2000), (1900, 2100), (3000, 3200)])

    FakePopen.calls = []
    monkeypatch.setattr("subprocess.Popen", FakePopen)

    out_dir = tmp_path / "out"
    op = AudioMute()
    _, windows_path = op.do(
        audio_file_path=str(audio_in),
        matches_csv_path=str(matches_csv),
        output_dir=str(out_dir),
    )

    windows = json.loads(Path(windows_path).read_text(encoding="utf-8"))
    assert windows == [{"start": 1.0, "end": 2.1}, {"start": 3.0, "end": 3.2}]

    # Filter should include exactly two between(...) clauses after merge
    cmd = FakePopen.calls[-1]
    af = cmd[cmd.index("-af") + 1]
    assert af.count("between(") == 2


def test_raises_when_no_mute_windows(tmp_path, monkeypatch):
    audio_in = tmp_path / "a.wav"
    audio_in.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    matches_csv = tmp_path / "matches.csv"
    # Only header, no rows
    matches_csv.write_text("start_ms,end_ms\n", encoding="utf-8")

    FakePopen.calls = []
    monkeypatch.setattr("subprocess.Popen", FakePopen)

    op = AudioMute()
    with pytest.raises(RuntimeError):
        op.do(
            audio_file_path=str(audio_in),
            matches_csv_path=str(matches_csv),
            output_dir=str(tmp_path / "out"),
        )


def test_unsorted_and_adjacent_windows_merge(tmp_path, monkeypatch):
    audio_in = tmp_path / "a.wav"
    audio_in.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    matches_csv = tmp_path / "matches.csv"
    # Unsorted input with tiny gap (1ms) should merge into single window per tolerance (1e-3)
    write_csv(matches_csv, [(3000, 3100), (1000, 1500), (1501, 1800)])

    FakePopen.calls = []
    monkeypatch.setattr("subprocess.Popen", FakePopen)

    out_dir = tmp_path / "out"
    op = AudioMute()
    _, windows_path = op.do(
        audio_file_path=str(audio_in),
        matches_csv_path=str(matches_csv),
        output_dir=str(out_dir),
    )

    windows = json.loads(Path(windows_path).read_text(encoding="utf-8"))
    # (1000-1500) and (1501-1800) merge due to 1ms gap tolerance
    assert windows == [{"start": 1.0, "end": 1.8}, {"start": 3.0, "end": 3.1}]

    cmd = FakePopen.calls[-1]
    af = cmd[cmd.index("-af") + 1]
    # Only two between clauses after merge
    assert af.count("between(") == 2


def test_malformed_rows_are_skipped(tmp_path, monkeypatch):
    audio_in = tmp_path / "a.wav"
    audio_in.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    matches_csv = tmp_path / "matches.csv"
    matches_csv.write_text(
        "start_ms,end_ms\n"  # header
        "1000,2000\n"       # valid
        "oops,3000\n"       # malformed
        "4000,5000\n",      # valid
        encoding="utf-8",
    )

    FakePopen.calls = []
    monkeypatch.setattr("subprocess.Popen", FakePopen)

    out_dir = tmp_path / "out"
    op = AudioMute()
    _, windows_path = op.do(
        audio_file_path=str(audio_in),
        matches_csv_path=str(matches_csv),
        output_dir=str(out_dir),
    )

    windows = json.loads(Path(windows_path).read_text(encoding="utf-8"))
    assert windows == [{"start": 1.0, "end": 2.0}, {"start": 4.0, "end": 5.0}]


def test_ffmpeg_failure_raises(tmp_path, monkeypatch):
    audio_in = tmp_path / "a.wav"
    audio_in.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    matches_csv = tmp_path / "matches.csv"
    write_csv(matches_csv, [(1000, 2000)])

    FakePopenFailure.calls = []
    monkeypatch.setattr("subprocess.Popen", FakePopenFailure)

    op = AudioMute()
    with pytest.raises(RuntimeError):
        op.do(
            audio_file_path=str(audio_in),
            matches_csv_path=str(matches_csv),
            output_dir=str(tmp_path / "out"),
        )
