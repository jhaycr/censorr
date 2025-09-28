"""
Final destination management utilities.

Handles moving completed pipeline outputs to their final destination with atomic operations.
"""
import logging
import os
import shutil
import hashlib 
from pathlib import Path
from typing import List, Dict, Any, Optional


class FinalDestinationManager:
    """Manages moving completed outputs to final destination."""
    
    def __init__(self):
        """Initialize the manager."""
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def move_to_final_destination(self, source_paths: List[str], final_dest: str, 
                                preserve_structure: bool = False) -> Dict[str, Any]:
        """Move files to final destination with atomic operations.
        
        Args:
            source_paths: List of source file paths to move
            final_dest: Final destination directory path
            preserve_structure: Whether to preserve source directory structure
            
        Returns:
            Dictionary with move results
        """
        if not final_dest:
            return {"status": "skipped", "reason": "No final destination specified"}
        
        final_dest_path = Path(final_dest)
        
        # Ensure destination exists
        try:
            final_dest_path.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Final destination ready: {final_dest_path}")
        except Exception as e:
            return {"status": "error", "message": f"Failed to create destination {final_dest_path}: {e}"}
        
        moved_files = []
        failed_moves = []
        
        for source_path in source_paths:
            try:
                source = Path(source_path)
                if not source.exists():
                    self.logger.warning(f"Source file not found, skipping: {source_path}")
                    continue
                
                # Determine target path
                if preserve_structure:
                    # Preserve relative path structure (future enhancement)
                    target = final_dest_path / source.name
                else:
                    target = final_dest_path / source.name
                
                # Attempt atomic move
                move_result = self._atomic_move(source, target)
                if move_result["status"] == "success":
                    moved_files.append({
                        "source": str(source),
                        "target": str(target),
                        "method": move_result["method"]
                    })
                    self.logger.info(f"✓ Moved to final destination: {source.name}")
                else:
                    failed_moves.append({
                        "source": str(source),
                        "target": str(target),
                        "error": move_result["error"]
                    })
                    self.logger.error(f"✗ Failed to move {source.name}: {move_result['error']}")
                    
            except Exception as e:
                failed_moves.append({
                    "source": source_path,
                    "target": "unknown",
                    "error": str(e)
                })
                self.logger.error(f"✗ Unexpected error moving {source_path}: {e}")
        
        result = {
            "status": "completed",
            "moved_count": len(moved_files),
            "failed_count": len(failed_moves),
            "moved_files": moved_files,
            "failed_moves": failed_moves,
            "final_destination": str(final_dest_path)
        }
        
        if moved_files:
            self.logger.info(f"Final destination move completed: {len(moved_files)} files moved, {len(failed_moves)} failed")
        
        return result
    
    def _atomic_move(self, source: Path, target: Path) -> Dict[str, Any]:
        """Attempt atomic move with fallback to copy+verify+remove.
        
        Args:
            source: Source file path
            target: Target file path
            
        Returns:
            Dictionary with move result
        """
        try:
            # Check if target exists
            if target.exists():
                return {"status": "error", "error": f"Target already exists: {target}"}
            
            # Try atomic rename first (same filesystem)
            try:
                os.rename(str(source), str(target))
                return {"status": "success", "method": "atomic_rename"}
            except OSError:
                # Cross-filesystem or other rename issue, fall back to copy
                self.logger.debug(f"Atomic rename failed for {source}, falling back to copy+verify")
                
                # Copy file
                shutil.copy2(str(source), str(target))
                
                # Verify checksums
                if self._verify_checksum(source, target):
                    # Remove original
                    os.remove(str(source))
                    return {"status": "success", "method": "copy_verify_remove"}
                else:
                    # Cleanup failed copy
                    if target.exists():
                        os.remove(str(target))
                    return {"status": "error", "error": "Checksum verification failed"}
                    
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def _verify_checksum(self, source: Path, target: Path) -> bool:
        """Verify that source and target files have identical checksums.
        
        Args:
            source: Source file path
            target: Target file path
            
        Returns:
            True if checksums match
        """
        try:
            source_checksum = self._calculate_checksum(source)
            target_checksum = self._calculate_checksum(target)
            return source_checksum == target_checksum
        except Exception as e:
            self.logger.error(f"Checksum verification failed: {e}")
            return False
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file.
        
        Args:
            file_path: Path to file
            
        Returns:
            SHA256 hexdigest
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()