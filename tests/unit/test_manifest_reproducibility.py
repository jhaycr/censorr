"""
Unit tests for manifest reproducibility.
"""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock

from src.caching import CacheManager
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationFlags
from src.models.common import ManifestEntry


class TestManifestReproducibility:
    """Test cases for manifest reproducibility (Task 66)."""
    
    def test_manifest_reproducibility_identical_inputs(self):
        """Test that running pipeline twice with identical inputs produces consistent manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            cache_manager = CacheManager(workdir)
            
            # Create test input artifact
            input_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(workdir / "input.mkv"),
                metadata={"format": "mkv"}
            )
            
            # Create fake input file
            (workdir / "input.mkv").write_text("test video content")
            
            # Create test output artifact
            output_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(workdir / "output.wav"),
                metadata={"track_index": 0}
            )
            
            # Create fake output file
            (workdir / "output.wav").write_text("test audio content")
            
            # Save manifest first time
            cache_key1 = cache_manager.create_cache_key("test_op", [input_artifact], {})
            op_dir1 = cache_manager.get_operation_dir("test_op", cache_key1)
            
            manifest1 = cache_manager.save_manifest(
                operation_dir=op_dir1,
                operation_name="test_op",
                inputs=[input_artifact],
                outputs=[output_artifact],
                params={}
            )
            
            # Save manifest second time with identical inputs
            cache_key2 = cache_manager.create_cache_key("test_op", [input_artifact], {})
            op_dir2 = cache_manager.get_operation_dir("test_op", cache_key2)
            
            manifest2 = cache_manager.save_manifest(
                operation_dir=op_dir2,
                operation_name="test_op",
                inputs=[input_artifact],
                outputs=[output_artifact],
                params={}
            )
            
            # Should create same operation directory due to identical hash
            assert str(op_dir1) == str(op_dir2)
            
            # Manifest content should be identical (except timestamps)
            assert manifest1.op == manifest2.op
            assert manifest1.inputs == manifest2.inputs
            assert manifest1.outputs == manifest2.outputs
            assert manifest1.params == manifest2.params
    
    def test_manifest_different_inputs_different_directories(self):
        """Test that different inputs produce different operation directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            cache_manager = CacheManager(workdir)
            
            # Create two different input artifacts
            input1 = Artifact(
                type=ArtifactType.VIDEO,
                path=str(workdir / "input1.mkv"),
                metadata={"format": "mkv"}
            )
            
            input2 = Artifact(
                type=ArtifactType.VIDEO,
                path=str(workdir / "input2.mkv"),
                metadata={"format": "mkv", "language": "en"}  # Different metadata
            )
            
            # Create fake input files with different content
            (workdir / "input1.mkv").write_text("test video content 1")
            (workdir / "input2.mkv").write_text("test video content 2")
            
            # Get operation directories
            cache_key1 = cache_manager.create_cache_key("test_op", [input1], {})
            cache_key2 = cache_manager.create_cache_key("test_op", [input2], {})
            op_dir1 = cache_manager.get_operation_dir("test_op", cache_key1)
            op_dir2 = cache_manager.get_operation_dir("test_op", cache_key2)
            
            # Should produce different directories due to different inputs
            assert str(op_dir1) != str(op_dir2)
    
    def test_manifest_load_after_save(self):
        """Test that saved manifest can be loaded and matches original."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            cache_manager = CacheManager(workdir)
            
            # Create test artifacts
            input_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(workdir / "input.mkv"),
                metadata={"format": "mkv"}
            )
            
            output_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(workdir / "output.wav"),
                metadata={"track_index": 0}
            )
            
            # Create fake files
            (workdir / "input.mkv").write_text("test video content")
            (workdir / "output.wav").write_text("test audio content")
            
            # Save manifest
            cache_key = cache_manager.create_cache_key("test_op", [input_artifact], {"verbose": True})
            op_dir = cache_manager.get_operation_dir("test_op", cache_key)
            
            original_manifest = cache_manager.save_manifest(
                operation_dir=op_dir,
                operation_name="test_op",
                inputs=[input_artifact],
                outputs=[output_artifact],
                params={"verbose": True}
            )
            
            # Load manifest
            loaded_manifest = cache_manager.load_manifest(op_dir)
            
            # Should match original
            assert loaded_manifest is not None
            assert loaded_manifest.op == original_manifest.op
            assert loaded_manifest.inputs == original_manifest.inputs
            assert loaded_manifest.outputs == original_manifest.outputs
            assert loaded_manifest.params == original_manifest.params
    
    def test_manifest_no_duplicate_edition_tags_on_rerun(self):
        """Test that re-running pipeline doesn't create duplicate edition tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            # Create test video file with edition tag
            video_file = workdir / "Movie Title (2024) {edition-Censorr}.mkv"
            video_file.write_text("test video content")
            
            from src.utils.filename_utils import ensure_movie_edition_tag
            
            # Apply edition tag first time
            result1 = ensure_movie_edition_tag(str(video_file), "Censorr")
            
            # Apply edition tag second time (should be idempotent)
            result2 = ensure_movie_edition_tag(result1, "Censorr")
            
            # Should not create duplicate tags
            assert result1 == result2
            assert result1.count("{edition-Censorr}") == 1
    
    def test_manifest_sidecar_reuse_identical_content(self):
        """Test that sidecar files with identical content are reused, not rewritten."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            from src.utils.filename_utils import build_sidecar_subtitle_path, handle_sidecar_collision
            import hashlib
            
            # Create video file
            video_file = workdir / "test_movie.mkv"
            video_file.write_text("test video")
            
            # Create identical subtitle content
            subtitle_content = b"1\n00:00:01,000 --> 00:00:02,000\nTest subtitle\n"
            checksum = hashlib.md5(subtitle_content).hexdigest()
            
            # Build sidecar path
            sidecar_path = build_sidecar_subtitle_path(str(video_file), "en", "censorr")
            
            # Create first sidecar
            with open(sidecar_path, 'wb') as f:
                f.write(subtitle_content)
            
            # Handle collision/reuse with identical content
            result_path = handle_sidecar_collision(sidecar_path, checksum)
            
            # Should reuse existing file (same path)
            assert result_path == sidecar_path
            
            # Create different content
            different_content = b"1\n00:00:01,000 --> 00:00:02,000\nDifferent subtitle\n"
            different_checksum = hashlib.md5(different_content).hexdigest()
            
            # Handle collision with different content
            collision_path = handle_sidecar_collision(sidecar_path, different_checksum)
            
            # Should create new numbered file
            assert collision_path != sidecar_path
            assert collision_path.endswith("-2.srt")
    
    def test_manifest_unchanged_inputs_deterministic_output(self):
        """Test that unchanged inputs produce deterministic operation directories and checksums."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            
            cache_manager = CacheManager(workdir)
            
            # Create test input with fixed content
            input_file = workdir / "input.mkv"
            input_file.write_text("consistent test content")
            
            input_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=str(input_file),
                metadata={"format": "mkv"}
            )
            
            flags = OperationFlags(verbose=True, dry_run=False)
            
            # Get operation directory multiple times
            params = {"verbose": True, "dry_run": False}
            cache_key_1 = cache_manager.create_cache_key("test_op", [input_artifact], params)
            cache_key_2 = cache_manager.create_cache_key("test_op", [input_artifact], params)
            cache_key_3 = cache_manager.create_cache_key("test_op", [input_artifact], params)
            op_dir_1 = cache_manager.get_operation_dir("test_op", cache_key_1)
            op_dir_2 = cache_manager.get_operation_dir("test_op", cache_key_2)  
            op_dir_3 = cache_manager.get_operation_dir("test_op", cache_key_3)
            
            # Should all be identical
            assert str(op_dir_1) == str(op_dir_2) == str(op_dir_3)
            
            # Directory path should be deterministic based on inputs
            assert "test_op" in str(op_dir_1)
            
            # Hash component should be consistent (directory contains some hash-like component)
            dir_name = str(op_dir_1)
            assert len(dir_name) > len(str(workdir / "test_op"))  # Should have additional hash component