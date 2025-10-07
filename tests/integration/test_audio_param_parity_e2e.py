"""E2E test: When preset enables transcode-to-original, remuxed audio matches original parameters.

This test simulates a full pipeline around remux, ensuring that when
`audio_transcode_to_original` is active (via preset flags), the remux
step encodes processed audio to match the original codec, channels,
sample rate, and bitrate unless overridden.
"""
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

import pytest

from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.ops.remux import RemuxOperation


class TestAudioParamParityE2E:
    def test_transcode_to_original_params_from_preset(self):
        """When transcode-to-original is enabled, use original audio params by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            video_path = workdir / "Movie (2024).mkv"
            video_path.write_text("mock video")

            # Input video artifact with original audio metadata captured earlier in pipeline
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={
                    "audio_codec": "eac3",
                    "audio_channels": 6,
                    "audio_sample_rate": 48000,
                    "audio_bitrate": "256k",
                },
            )

            # Simulate presence of a muted audio artifact (content not used; adapter patched)
            muted_audio = Artifact(
                type=ArtifactType.AUDIO,
                path=str(workdir / "muted_audio_track_0.wav"),
                metadata={"track": "0"},
            )

            # Flags emulate preset behavior: transcode to original
            flags = OperationFlags(
                audio_transcode_to_original=True,
                output_mode="REMUX_NEW_FILE",
                dry_run=False,
                verbose=True,
            )

            remux = RemuxOperation()
            with patch.object(remux.ffmpeg, "remux", return_value=str(workdir / "Movie (2024) {edition-Censorr}.mkv")) as mock_remux:
                results = remux.run([video_artifact, muted_audio], workdir, flags)

                assert len(results) == 1
                # Verify we passed through the original params to adapter
                called_args, called_kwargs = mock_remux.call_args
                # kwargs contains audio_encode
                audio_encode = called_kwargs.get("audio_encode")
                assert audio_encode is not None
                assert audio_encode["codec"] == "eac3"
                assert audio_encode["channels"] == 6
                assert audio_encode["sample_rate"] == 48000
                assert audio_encode["bitrate"] == "256k"

    def test_cli_overrides_original_params(self):
        """CLI/flags should override specific original params when provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            video_path = workdir / "Movie (2024).mkv"
            video_path.write_text("mock video")

            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(video_path),
                metadata={
                    "audio_codec": "eac3",
                    "audio_channels": 6,
                    "audio_sample_rate": 48000,
                    "audio_bitrate": "256k",
                },
            )
            muted_audio = Artifact(
                type=ArtifactType.AUDIO,
                path=str(workdir / "muted_audio_track_0.wav"),
                metadata={"track": "0"},
            )

            flags = OperationFlags(
                audio_transcode_to_original=True,
                audio_target_codec="ac3",
                audio_bitrate="384k",
                audio_channels=2,
                output_mode="REMUX_NEW_FILE",
                dry_run=False,
                verbose=True,
            )

            remux = RemuxOperation()
            with patch.object(remux.ffmpeg, "remux", return_value=str(workdir / "Movie (2024) {edition-Censorr}.mkv")) as mock_remux:
                results = remux.run([video_artifact, muted_audio], workdir, flags)

                assert len(results) == 1
                audio_encode = mock_remux.call_args.kwargs.get("audio_encode")
                # Overrides applied
                assert audio_encode["codec"] == "ac3"
                assert audio_encode["channels"] == 2
                assert audio_encode["bitrate"] == "384k"
                # Since no override for sample_rate, original should remain
                assert audio_encode["sample_rate"] == 48000
