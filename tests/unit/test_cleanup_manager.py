"""
Unit tests for intermediate cleanup manager.
"""
import pytest
import tempfile
from pathlib import Path

from src.utils.cleanup_manager import CleanupManager


class TestCleanupManager:
    """Test cases for intermediate artifact cleanup (Task 60)."""
    
    def test_register_and_cleanup_intermediates(self):
        """Test basic registration and cleanup of intermediate files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create test files
            intermediate1 = tmpdir_path / "intermediate1.wav"
            intermediate2 = tmpdir_path / "intermediate2.srt"
            final_output = tmpdir_path / "final.mkv"
            
            intermediate1.touch()
            intermediate2.touch()
            final_output.touch()
            
            cleanup_manager = CleanupManager()
            
            # Register files
            cleanup_manager.register_intermediate(str(intermediate1))
            cleanup_manager.register_intermediate(str(intermediate2))
            cleanup_manager.register_preserved(str(final_output))
            
            # Perform cleanup
            result = cleanup_manager.cleanup_intermediates(persist_intermediate=False)
            
            assert result["status"] == "completed"
            assert result["cleaned_count"] == 2
            assert result["failed_count"] == 0
            assert not intermediate1.exists()
            assert not intermediate2.exists()
            assert final_output.exists()  # Preserved
    
    def test_skip_cleanup_when_persist_intermediate(self):
        """Test cleanup is skipped when persist_intermediate is True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create test file
            intermediate = tmpdir_path / "intermediate.wav"
            intermediate.touch()
            
            cleanup_manager = CleanupManager()
            cleanup_manager.register_intermediate(str(intermediate))
            
            # Skip cleanup
            result = cleanup_manager.cleanup_intermediates(persist_intermediate=True)
            
            assert result["status"] == "skipped"
            assert result["reason"] == "persist_intermediate flag set"
            assert intermediate.exists()  # Should still exist
    
    def test_preserve_dependencies(self):
        """Test that dependencies of preserved artifacts are not cleaned up."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Create test files
            dependency = tmpdir_path / "dependency.wav"
            intermediate = tmpdir_path / "intermediate.srt" 
            final_output = tmpdir_path / "final.mkv"
            
            dependency.touch()
            intermediate.touch()
            final_output.touch()
            
            cleanup_manager = CleanupManager()
            
            # Register files with dependencies
            cleanup_manager.register_intermediate(str(dependency))
            cleanup_manager.register_intermediate(str(intermediate))
            cleanup_manager.register_preserved(str(final_output))
            
            # Set up dependency relationship: final_output depends on dependency
            cleanup_manager.dependencies[str(final_output)] = {str(dependency)}
            
            # Perform cleanup
            result = cleanup_manager.cleanup_intermediates(persist_intermediate=False)
            
            assert result["status"] == "completed"
            assert result["cleaned_count"] == 1  # Only intermediate should be cleaned
            assert dependency.exists()      # Preserved as dependency
            assert not intermediate.exists() # Cleaned up
            assert final_output.exists()    # Preserved
    
    def test_cleanup_missing_files(self):
        """Test cleanup handles missing files gracefully."""
        cleanup_manager = CleanupManager()
        
        # Register non-existent file
        cleanup_manager.register_intermediate("/nonexistent/file.wav")
        
        # Should not fail
        result = cleanup_manager.cleanup_intermediates(persist_intermediate=False)
        
        assert result["status"] == "completed"
        assert result["cleaned_count"] == 0
        assert result["failed_count"] == 0
    
    def test_get_summary(self):
        """Test getting cleanup manager summary."""
        cleanup_manager = CleanupManager()
        
        cleanup_manager.register_intermediate("file1.wav")
        cleanup_manager.register_intermediate("file2.srt")
        cleanup_manager.register_preserved("final.mkv")
        
        summary = cleanup_manager.get_summary()
        
        assert summary["intermediate_count"] == 2
        assert summary["preserved_count"] == 1
        assert "file1.wav" in summary["intermediate_artifacts"]
        assert "final.mkv" in summary["preserved_artifacts"]