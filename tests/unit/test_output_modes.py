"""Tests for output mode configuration and path building utilities."""
import pytest
from pathlib import Path
import tempfile
import shutil

from src.models.config import Config, OutputMode, DestinationPolicy, PresetConfig
from src.utils.path_builder import (
    build_same_folder_new_name,
    build_destination_path,
    detect_media_type,
    resolve_output_conflict,
    _build_subfolder_tag_path,
    _build_separate_root_path
)


class TestOutputModeConfig:
    """Test output mode configuration functionality."""
    
    def test_output_mode_enum(self):
        """Test OutputMode enum values."""
        assert OutputMode.REMUX_ORIGINAL_VIDEO == "REMUX_ORIGINAL_VIDEO"
        assert OutputMode.REMUX_NEW_FILE == "REMUX_NEW_FILE"
    
    def test_destination_policy_creation(self):
        """Test DestinationPolicy model creation."""
        policy = DestinationPolicy()
        assert policy.policy == "subfolder_tag"
        assert policy.tag == "[Censorr]"
        assert policy.separate_root == "/data/media/TV/Censorr"
        assert policy.template is None
    
    def test_destination_policy_validation(self):
        """Test DestinationPolicy validation."""
        # Valid policies
        DestinationPolicy(policy="subfolder_tag")
        DestinationPolicy(policy="separate_root")
        
        # Invalid policy should raise validation error
        with pytest.raises(ValueError, match="policy must be one of"):
            DestinationPolicy(policy="invalid_policy")
    
    def test_preset_config_creation(self):
        """Test PresetConfig model creation."""
        preset = PresetConfig(
            operations=["extract_subtitles", "mask_subtitles"],
            flags={"create_subtitle_sidecar": True},
            output={"output_mode": "REMUX_NEW_FILE"},
            destination_policy=DestinationPolicy(policy="subfolder_tag"),
            backup_default=False
        )
        
        assert preset.operations == ["extract_subtitles", "mask_subtitles"]
        assert preset.flags["create_subtitle_sidecar"] is True
        assert preset.output["output_mode"] == "REMUX_NEW_FILE"
        assert preset.destination_policy.policy == "subfolder_tag"
        assert preset.backup_default is False
    
    def test_config_with_presets(self):
        """Test Config with presets configuration."""
        config = Config(
            output_mode=OutputMode.REMUX_NEW_FILE,
            destination_policy=DestinationPolicy(policy="separate_root"),
            presets={
                "movies": PresetConfig(
                    operations=["extract_subtitles", "remux"],
                    output={"output_mode": "REMUX_NEW_FILE"}
                ),
                "tv": PresetConfig(
                    operations=["extract_subtitles", "remux"],
                    destination_policy=DestinationPolicy(policy="subfolder_tag")
                )
            }
        )
        
        assert config.output_mode == OutputMode.REMUX_NEW_FILE
        assert config.destination_policy.policy == "separate_root"
        assert "movies" in config.presets
        assert "tv" in config.presets
        assert config.presets["movies"].operations == ["extract_subtitles", "remux"]


class TestPathBuilder:
    """Test path building utilities."""
    
    def test_detect_media_type_movie(self):
        """Test movie detection."""
        assert detect_media_type(Path("Movie Title (2024).mkv")) == "movie"
        assert detect_media_type(Path("Another Movie.mp4")) == "movie"
        assert detect_media_type(Path("Film [1080p].mkv")) == "movie"
    
    def test_detect_media_type_episode(self):
        """Test episode detection."""
        assert detect_media_type(Path("Show S01E01.mkv")) == "episode"
        assert detect_media_type(Path("Series S1E1.mp4")) == "episode"
        assert detect_media_type(Path("Show 1x01.mkv")) == "episode"
        assert detect_media_type(Path("Show S02 E05.mkv")) == "episode"
    
    def test_build_same_folder_new_name_movie(self):
        """Test building movie edition filename."""
        source = Path("/movies/Movie Title (2024).mkv")
        result = build_same_folder_new_name(source)
        expected = Path("/movies/Movie Title (2024) {edition-Censorr}.mkv")
        assert result == expected
    
    def test_build_same_folder_new_name_no_year(self):
        """Test building edition filename without year pattern."""
        source = Path("/movies/Simple Movie.mkv")
        result = build_same_folder_new_name(source)
        expected = Path("/movies/Simple Movie {edition-Censorr}.mkv")
        assert result == expected
    
    def test_build_same_folder_new_name_existing_edition(self):
        """Test building filename when edition already exists."""
        source = Path("/movies/Movie (2024) {edition-Directors}.mkv")
        result = build_same_folder_new_name(source)
        # Should not add another edition tag
        assert result == source
    
    def test_build_same_folder_new_name_custom_tag(self):
        """Test building filename with custom edition tag."""
        source = Path("/movies/Movie (2024).mkv")
        result = build_same_folder_new_name(source, "Clean")
        expected = Path("/movies/Movie (2024) {edition-Clean}.mkv")
        assert result == expected
    
    def test_build_subfolder_tag_path(self):
        """Test building path with subfolder tag."""
        source = Path("/TV/General/Only Murders in the Building/Season 1/S01E01.mkv")
        result = _build_subfolder_tag_path(source, "[Censorr]")
        expected = Path("/TV/General/Only Murders in the Building [Censorr]/Season 1/S01E01.mkv")
        assert result == expected
    
    def test_build_subfolder_tag_path_existing_tag(self):
        """Test building path when tag already exists."""
        source = Path("/TV/General/Show [Censorr]/Season 1/S01E01.mkv")
        result = _build_subfolder_tag_path(source, "[Censorr]")
        # Should not duplicate tag
        assert result == source
    
    def test_build_separate_root_path(self):
        """Test building path under separate root."""
        source = Path("/TV/General/Only Murders in the Building/Season 1/S01E01.mkv")
        result = _build_separate_root_path(source, "/data/media/TV/Censorr")
        expected = Path("/data/media/TV/Censorr/Only Murders in the Building/Season 1/S01E01.mkv")
        assert result == expected
    
    def test_build_destination_path_subfolder_tag(self):
        """Test destination path building with subfolder_tag policy."""
        source = Path("/TV/General/Show Name/Season 1/S01E01.mkv")
        result = build_destination_path(source, "subfolder_tag", "[Clean]")
        expected = Path("/TV/General/Show Name [Clean]/Season 1/S01E01.mkv")
        assert result == expected
    
    def test_build_destination_path_separate_root(self):
        """Test destination path building with separate_root policy."""
        source = Path("/TV/General/Show Name/Season 1/S01E01.mkv")
        result = build_destination_path(source, "separate_root", tag="[Censorr]", separate_root="/censored/TV")
        expected = Path("/censored/TV/Show Name/Season 1/S01E01.mkv")
        assert result == expected
    
    def test_build_destination_path_invalid_policy(self):
        """Test destination path building with invalid policy."""
        source = Path("/TV/Show/S01E01.mkv")
        with pytest.raises(ValueError, match="Unknown destination policy"):
            build_destination_path(source, "invalid_policy")


class TestConflictResolution:
    """Test conflict resolution functionality."""
    
    def test_resolve_output_conflict_nonexistent(self):
        """Test conflict resolution for non-existent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "output.mkv"
            result_path, should_write = resolve_output_conflict(target)
            assert result_path == target
            assert should_write is True
    
    def test_resolve_output_conflict_overwrite(self):
        """Test conflict resolution with overwrite policy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "output.mkv"
            target.touch()  # Create existing file
            
            result_path, should_write = resolve_output_conflict(target, "overwrite")
            assert result_path == target
            assert should_write is True
    
    def test_resolve_output_conflict_fail(self):
        """Test conflict resolution with fail policy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "output.mkv"
            target.touch()  # Create existing file
            
            with pytest.raises(FileExistsError, match="Output file already exists"):
                resolve_output_conflict(target, "fail")
    
    def test_resolve_output_conflict_reuse(self):
        """Test conflict resolution with reuse policy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "output.mkv"
            target.touch()  # Create existing file
            
            result_path, should_write = resolve_output_conflict(target, "reuse_if_identical")
            assert result_path == target
            assert should_write is False  # Should not write, reuse existing
    
    def test_resolve_output_conflict_suffix(self):
        """Test conflict resolution with suffix policy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "output.mkv"
            target.touch()  # Create existing file
            
            result_path, should_write = resolve_output_conflict(target, "suffix")
            expected = Path(tmpdir) / "output-2.mkv"
            assert result_path == expected
            assert should_write is True
    
    def test_resolve_output_conflict_multiple_suffix(self):
        """Test conflict resolution with multiple existing suffixes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "output.mkv"
            target.touch()
            (Path(tmpdir) / "output-2.mkv").touch()
            (Path(tmpdir) / "output-3.mkv").touch()
            
            result_path, should_write = resolve_output_conflict(target, "suffix")
            expected = Path(tmpdir) / "output-4.mkv"
            assert result_path == expected
            assert should_write is True
    
    def test_resolve_output_conflict_invalid_policy(self):
        """Test conflict resolution with invalid policy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "output.mkv"
            target.touch()  # Need existing file to trigger policy check
            with pytest.raises(ValueError, match="Unknown conflict policy"):
                resolve_output_conflict(target, "invalid_policy")