"""Integration-style tests for audio QC tuning via flags.

These tests exercise the AudioQualityCheckOperation using real WAV IO and
verify that threshold/control-window settings are honored and persisted
to the QC report.
"""
from pathlib import Path
import tempfile
import wave
import json

from src.ops.audio_quality_check import AudioQualityCheckOperation
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags


def _write_wav_mono_16bit(path: Path, samples: list[int], rate: int = 44100):
    with wave.open(str(path), 'w') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        frame_bytes = bytearray()
        for s in samples:
            s = max(-32768, min(32767, s))
            frame_bytes.append(s & 0xFF)
            frame_bytes.append((s >> 8) & 0xFF)
        wav_file.writeframes(bytes(frame_bytes))


def test_audio_qc_threshold_and_control_window_propagate_to_report():
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        audio_path = tmpdir / "test.wav"

        # 1 second half-volume tone (approx), then 1 second silence
        sr = 44100
        samples = []
        for i in range(sr * 2):
            if i < sr:
                samples.append(int(32767 * 0.5))
            else:
                samples.append(0)
        _write_wav_mono_16bit(audio_path, samples, rate=sr)

        # Mute window covering first second (tone region)
        mute_windows = [{"start": 0.0, "end": 1.0, "reason": "test", "source": "TEST"}]
        mute_path = tmpdir / "mute_windows.json"
        mute_path.write_text(json.dumps(mute_windows))

        artifact = Artifact(
            type=ArtifactType.AUDIO,
            path=str(audio_path),
            metadata={"mute_windows_file": str(mute_path)}
        )

        op = AudioQualityCheckOperation()
        # Provide custom threshold/control-window via flags
        flags = OperationFlags(
            verbose=False,
            continue_on_audio_qc_fail=True,
            audio_qc_threshold_db=-12.0,
            audio_qc_control_window=0.5,
        )

        results = op.run([artifact], tmpdir, flags)
        assert results and results[0].type == ArtifactType.AUDIO

        # Read the generated report and verify the parameters are recorded
        report_path = tmpdir / "audio_qc_report.json"
        assert report_path.exists()
        report = json.loads(report_path.read_text())
        assert report.get("energy_threshold_db") == -12.0
        assert report.get("control_window_duration") == 0.5
