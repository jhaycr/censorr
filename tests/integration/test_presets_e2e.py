"""End-to-end tests for output modes and presets functionality."""
import pytest
import tempfile
import shutil
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.models.config import Config, OutputMode, DestinationPolicy, PresetConfig
from src.models.operations import OperationFlags
from src.models.artifacts import Artifact, ArtifactType
from src.ops.remux import RemuxOperation


class TestOutputModesE2E:
    """End-to-end tests for output modes and presets."""
    
    def test_movies_preset_new_file_mode(self):
        """Test movies preset with REMUX_NEW_FILE mode creates edition file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create test input file
            input_file = tmpdir_path / "Movie Title (2024).mkv"
            input_file.touch()
            
            # Create flags with movies preset settings
            flags = OperationFlags(
                output_mode="REMUX_NEW_FILE",
                dest_policy="subfolder_tag",
                dest_policy_tag="[Censorr]",
                dry_run=True  # Don't actually run FFmpeg
            )
            
            # Create test artifacts
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(input_file),
                metadata={"codec": "h264"}
            )
            
            # Run remux operation
            remux_op = RemuxOperation()
            with patch.object(remux_op, 'ffmpeg') as mock_ffmpeg:
                mock_ffmpeg.remux.return_value = str(tmpdir_path / "output.mkv")
                
                results = remux_op.run([video_artifact], tmpdir_path, flags)
                
                # Verify output path includes edition tag
                assert len(results) == 1
                result_path = Path(results[0].path)
                assert "{edition-Censorr}" in result_path.name
                assert result_path.parent == input_file.parent  # Same folder
    
    def test_tv_preset_subfolder_tag_mode(self):
        """Test TV preset with subfolder_tag destination policy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create test TV structure
            show_dir = tmpdir_path / "TV" / "General" / "Only Murders in the Building" / "Season 1"
            show_dir.mkdir(parents=True)
            input_file = show_dir / "S01E01.mkv"
            input_file.touch()
            
            # Create flags with TV preset settings
            flags = OperationFlags(
                output_mode="REMUX_NEW_FILE",
                dest_policy="subfolder_tag",
                dest_policy_tag="[Censorr]",
                dry_run=True
            )
            
            # Create test artifacts
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(input_file),
                metadata={"codec": "h264"}
            )
            
            # Run remux operation
            remux_op = RemuxOperation()
            with patch.object(remux_op, 'ffmpeg') as mock_ffmpeg:
                mock_ffmpeg.remux.return_value = str(tmpdir_path / "output.mkv")
                
                results = remux_op.run([video_artifact], tmpdir_path, flags)
                
                # Verify output path uses tagged subfolder
                assert len(results) == 1
                result_path = Path(results[0].path)
                assert "[Censorr]" in str(result_path)
                assert "Only Murders in the Building [Censorr]" in str(result_path)
    
    def test_tv_preset_separate_root_mode(self):
        """Test TV preset with separate_root destination policy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create test TV structure
            show_dir = tmpdir_path / "TV" / "General" / "Show Name" / "Season 1"
            show_dir.mkdir(parents=True)
            input_file = show_dir / "S01E01.mkv"
            input_file.touch()
            
            # Create flags with separate root settings
            separate_root = str(tmpdir_path / "TV" / "Censorr")
            flags = OperationFlags(
                output_mode="REMUX_NEW_FILE",
                dest_policy="separate_root",
                dest_separate_root=separate_root,
                dry_run=True
            )
            
            # Create test artifacts
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(input_file),
                metadata={"codec": "h264"}
            )
            
            # Run remux operation
            remux_op = RemuxOperation()
            with patch.object(remux_op, 'ffmpeg') as mock_ffmpeg:
                mock_ffmpeg.remux.return_value = str(tmpdir_path / "output.mkv")
                
                results = remux_op.run([video_artifact], tmpdir_path, flags)
                
                # Verify output path uses separate root
                assert len(results) == 1
                result_path = Path(results[0].path)
                assert separate_root in str(result_path)
                assert "Show Name" in str(result_path)
    
    def test_config_preset_loading(self):
        """Test loading and resolving preset configuration."""
        # Create test config with presets
        config_data = {
            "output_mode": "REMUX_ORIGINAL_VIDEO",
            "presets": {
                "movies": {
                    "operations": ["extract_subtitles", "remux"],
                    "flags": {"create_subtitle_sidecar": True},
                    "output": {"output_mode": "REMUX_NEW_FILE"},
                    "backup_default": False
                },
                "tv": {
                    "operations": ["extract_subtitles", "remux"],
                    "destination_policy": {
                        "policy": "subfolder_tag",
                        "tag": "[Censorr]"
                    },
                    "output": {"output_mode": "REMUX_NEW_FILE"}
                }
            }
        }
        
        # Create config from data
        config = Config(**config_data)
        
        # Verify config structure
        assert config.output_mode == OutputMode.REMUX_ORIGINAL_VIDEO
        assert "movies" in config.presets
        assert "tv" in config.presets
        
        # Verify movies preset
        movies_preset = config.presets["movies"]
        assert movies_preset.operations == ["extract_subtitles", "remux"]
        assert movies_preset.flags["create_subtitle_sidecar"] is True
        assert movies_preset.output["output_mode"] == "REMUX_NEW_FILE"
        assert movies_preset.backup_default is False
        
        # Verify TV preset with destination policy
        tv_preset = config.presets["tv"]
        assert tv_preset.destination_policy is not None
        assert tv_preset.destination_policy.policy == "subfolder_tag"
        assert tv_preset.destination_policy.tag == "[Censorr]"
    
    def test_conflict_resolution_reuse(self):
        """Test conflict resolution with reuse_if_identical policy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create existing output file
            input_file = tmpdir_path / "Movie (2024).mkv"
            input_file.touch()
            existing_output = tmpdir_path / "Movie (2024) {edition-Censorr}.mkv"
            existing_output.touch()
            
            # Create flags with reuse policy
            flags = OperationFlags(
                output_mode="REMUX_NEW_FILE",
                conflict_policy="reuse_if_identical",
                dry_run=False,
                verbose=True
            )
            
            # Create test artifacts
            video_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(input_file),
                metadata={"codec": "h264"}
            )
            
            # Run remux operation
            remux_op = RemuxOperation()
            with patch.object(remux_op, 'ffmpeg') as mock_ffmpeg:
                # Should not call FFmpeg due to reuse
                results = remux_op.run([video_artifact], tmpdir_path, flags)
                
                # Verify no FFmpeg call was made (reused existing)
                mock_ffmpeg.remux.assert_not_called()
                
                # Verify result points to existing file
                assert len(results) == 1
                assert results[0].path == str(existing_output)