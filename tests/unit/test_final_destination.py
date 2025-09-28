"""
Unit tests for final destination manager.
"""
import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch

from src.utils.final_destination import FinalDestinationManager


class TestFinalDestinationManager:
    """Test cases for final destination management (Task 61)."""
    
    def test_move_to_final_destination_success(self):
        """Test successful move to final destination."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create source and destination directories
            source_dir = tmpdir_path / "source"
            dest_dir = tmpdir_path / "destination"
            source_dir.mkdir()
            dest_dir.mkdir()
            
            # Create test file
            source_file = source_dir / "test_movie.mkv"
            source_file.write_text("test content")
            
            manager = FinalDestinationManager()
            
            # Move to destination
            result = manager.move_to_final_destination(
                [str(source_file)], 
                str(dest_dir)
            )
            
            assert result["status"] == "completed"
            assert result["moved_count"] == 1
            assert result["failed_count"] == 0
            
            # Check file was moved
            dest_file = dest_dir / "test_movie.mkv"
            assert dest_file.exists()
            assert not source_file.exists()
            assert dest_file.read_text() == "test content"
    
    def test_move_cross_filesystem_copy_fallback(self):
        """Test fallback to copy+verify+remove for cross-filesystem moves."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create source and destination directories
            source_dir = tmpdir_path / "source"
            dest_dir = tmpdir_path / "destination"
            source_dir.mkdir()
            dest_dir.mkdir()
            
            # Create test file
            source_file = source_dir / "test_movie.mkv"
            source_file.write_text("test content")
            
            manager = FinalDestinationManager()
            
            # Mock os.rename to fail (simulate cross-filesystem)
            with patch('os.rename', side_effect=OSError("Cross-device link")):
                with patch('shutil.copy2') as mock_copy:
                    # Ensure the copy actually creates the target file for checksum verification
                    def copy_side_effect(src, dst):
                        Path(dst).write_text(Path(src).read_text())
                    mock_copy.side_effect = copy_side_effect
                    
                    result = manager.move_to_final_destination(
                        [str(source_file)],
                        str(dest_dir)
                    )
                    
                    assert result["status"] == "completed"
                    assert result["moved_count"] == 1
                    assert result["moved_files"][0]["method"] == "copy_verify_remove"
    
    def test_move_target_already_exists(self):
        """Test handling when target file already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create source and destination directories
            source_dir = tmpdir_path / "source"
            dest_dir = tmpdir_path / "destination"
            source_dir.mkdir()
            dest_dir.mkdir()
            
            # Create source file
            source_file = source_dir / "test_movie.mkv"
            source_file.write_text("source content")
            
            # Create existing target file
            target_file = dest_dir / "test_movie.mkv"
            target_file.write_text("existing content")
            
            manager = FinalDestinationManager()
            
            # Move should fail due to existing target
            result = manager.move_to_final_destination(
                [str(source_file)],
                str(dest_dir)
            )
            
            assert result["status"] == "completed"
            assert result["moved_count"] == 0
            assert result["failed_count"] == 1
            assert "Target already exists" in result["failed_moves"][0]["error"]
    
    def test_move_nonexistent_source(self):
        """Test handling of non-existent source files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dest_dir = tmpdir_path / "destination"
            dest_dir.mkdir()
            
            manager = FinalDestinationManager()
            
            # Try to move non-existent file
            result = manager.move_to_final_destination(
                ["/nonexistent/file.mkv"],
                str(dest_dir)
            )
            
            assert result["status"] == "completed"
            assert result["moved_count"] == 0
            assert result["failed_count"] == 0  # Non-existent files are just skipped
    
    def test_move_create_destination_directory(self):
        """Test that destination directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create source directory
            source_dir = tmpdir_path / "source"
            source_dir.mkdir()
            
            # Don't create destination directory
            dest_dir = tmpdir_path / "destination"
            
            # Create test file
            source_file = source_dir / "test_movie.mkv"
            source_file.write_text("test content")
            
            manager = FinalDestinationManager()
            
            # Move to non-existent destination
            result = manager.move_to_final_destination(
                [str(source_file)],
                str(dest_dir)
            )
            
            assert result["status"] == "completed"
            assert result["moved_count"] == 1
            assert dest_dir.exists()  # Should have been created
            assert (dest_dir / "test_movie.mkv").exists()
    
    def test_move_no_final_destination(self):
        """Test skipping when no final destination is specified."""
        manager = FinalDestinationManager()
        
        result = manager.move_to_final_destination(
            ["test.mkv"],
            ""  # Empty destination
        )
        
        assert result["status"] == "skipped"
        assert result["reason"] == "No final destination specified"
    
    def test_checksum_verification_failure(self):
        """Test handling of checksum verification failure during copy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create source and destination directories
            source_dir = tmpdir_path / "source"
            dest_dir = tmpdir_path / "destination"
            source_dir.mkdir()
            dest_dir.mkdir()
            
            # Create test file
            source_file = source_dir / "test_movie.mkv"
            source_file.write_text("test content")
            
            manager = FinalDestinationManager()
            
            # Mock os.rename to fail and checksum verification to fail
            with patch('os.rename', side_effect=OSError("Cross-device link")):
                with patch('shutil.copy2'), \
                     patch.object(manager, '_verify_checksum', return_value=False):
                    
                    result = manager.move_to_final_destination(
                        [str(source_file)],
                        str(dest_dir)
                    )
                    
                    assert result["status"] == "completed"
                    assert result["moved_count"] == 0
                    assert result["failed_count"] == 1
                    assert "Checksum verification failed" in result["failed_moves"][0]["error"]