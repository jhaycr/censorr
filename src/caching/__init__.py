"""Caching and manifest management for the censorr package."""
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from src.models.artifacts import Artifact
from src.models.common import ManifestEntry
from src.models.operations import OperationFlags


class CacheKey(BaseModel):
    """Represents a cache key for an operation."""
    
    operation_name: str = Field(..., description="Name of the operation")
    input_hashes: List[str] = Field(..., description="SHA256 hashes of input artifacts")
    params_hash: str = Field(..., description="SHA256 hash of operation parameters")
    
    def to_string(self) -> str:
        """Convert cache key to a deterministic string representation."""
        all_hashes = [self.operation_name] + self.input_hashes + [self.params_hash]
        combined = "|".join(all_hashes)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


class CacheManager:
    """Manages workdir layout and manifest recording for operations."""
    
    def __init__(self, workdir: Path):
        """Initialize the cache manager.
        
        Args:
            workdir: Root working directory for all operations
        """
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
    
    def get_operation_dir(self, operation_name: str, cache_key: CacheKey) -> Path:
        """Get the directory for a specific operation execution.
        
        The layout is: {workdir}/{operation_name}/{cache_key}/
        
        Args:
            operation_name: Name of the operation
            cache_key: Cache key for this execution
            
        Returns:
            Path to the operation directory
        """
        op_dir = self.workdir / operation_name / cache_key.to_string()
        op_dir.mkdir(parents=True, exist_ok=True)
        return op_dir
    
    def create_cache_key(
        self, 
        operation_name: str, 
        inputs: List[Artifact], 
        params: Dict[str, Any]
    ) -> CacheKey:
        """Create a cache key for an operation execution.
        
        Args:
            operation_name: Name of the operation
            inputs: Input artifacts
            params: Operation parameters (from flags)
            
        Returns:
            Cache key for this execution
        """
        # Hash input artifacts by their path and content
        input_hashes = []
        for artifact in inputs:
            artifact_path = Path(artifact.path)
            if artifact_path.exists():
                # Use file content hash for deterministic caching
                content_hash = self._hash_file(artifact_path)
                input_hashes.append(f"{artifact_path.name}:{content_hash}")
            else:
                # If file doesn't exist, use path as fallback
                input_hashes.append(f"{artifact_path.name}:missing")
        
        # Hash parameters for deterministic key
        params_str = json.dumps(params, sort_keys=True)
        params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]
        
        return CacheKey(
            operation_name=operation_name,
            input_hashes=input_hashes,
            params_hash=params_hash
        )
    
    def get_manifest_path(self, operation_dir: Path) -> Path:
        """Get the manifest file path for an operation directory.
        
        Args:
            operation_dir: Operation execution directory
            
        Returns:
            Path to the manifest.json file
        """
        return operation_dir / "manifest.json"
    
    def load_manifest(self, operation_dir: Path) -> Optional[ManifestEntry]:
        """Load the manifest for an operation execution.
        
        Args:
            operation_dir: Operation execution directory
            
        Returns:
            ManifestEntry if manifest exists and is valid, None otherwise
        """
        manifest_path = self.get_manifest_path(operation_dir)
        if not manifest_path.exists():
            return None
        
        try:
            with manifest_path.open('r') as f:
                data = json.load(f)
            return ManifestEntry.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            # Invalid manifest, treat as cache miss
            return None
    
    def save_manifest(
        self, 
        operation_dir: Path, 
        operation_name: str,
        inputs: List[Artifact], 
        outputs: List[Artifact], 
        params: Dict[str, Any]
    ) -> ManifestEntry:
        """Save the manifest for an operation execution.
        
        Args:
            operation_dir: Operation execution directory
            operation_name: Name of the operation
            inputs: Input artifacts
            outputs: Output artifacts  
            params: Operation parameters
            
        Returns:
            The saved manifest entry
        """
        # Create manifest entry
        input_entries = []
        for artifact in inputs:
            artifact_path = Path(artifact.path)
            if artifact_path.exists():
                checksum = self._hash_file(artifact_path)
            else:
                checksum = "missing"
            input_entries.append({
                "path": str(artifact_path),
                "checksum": checksum
            })
        
        output_entries = []
        for artifact in outputs:
            artifact_path = Path(artifact.path)
            if artifact_path.exists():
                checksum = self._hash_file(artifact_path)
            else:
                checksum = "missing"
            output_entries.append({
                "path": str(artifact_path),
                "checksum": checksum
            })
        
        manifest = ManifestEntry(
            op=operation_name,
            inputs=input_entries,
            outputs=output_entries,
            params=params
        )
        
        # Save to file
        manifest_path = self.get_manifest_path(operation_dir)
        with manifest_path.open('w') as f:
            json.dump(manifest.model_dump(), f, indent=2, default=str)
        
        return manifest
    
    def is_cached(
        self, 
        operation_name: str, 
        inputs: List[Artifact], 
        params: Dict[str, Any],
        flags: OperationFlags
    ) -> tuple[bool, Optional[Path]]:
        """Check if an operation execution is cached and valid.
        
        Args:
            operation_name: Name of the operation
            inputs: Input artifacts
            params: Operation parameters
            flags: Operation flags (force bypasses cache)
            
        Returns:
            Tuple of (is_cached, operation_dir)
        """
        # Force flag bypasses cache
        if flags.force:
            return False, None
        
        # Create cache key and get operation directory
        cache_key = self.create_cache_key(operation_name, inputs, params)
        operation_dir = self.get_operation_dir(operation_name, cache_key)
        
        # Load manifest
        manifest = self.load_manifest(operation_dir)
        if manifest is None:
            return False, operation_dir
        
        # Verify outputs still exist
        for output_entry in manifest.outputs:
            output_path = Path(output_entry["path"])
            if not output_path.exists():
                return False, operation_dir
            
            # Verify output hasn't changed
            current_checksum = self._hash_file(output_path)
            if current_checksum != output_entry["checksum"]:
                return False, operation_dir
        
        return True, operation_dir
    
    def _hash_file(self, filepath: Path) -> str:
        """Calculate a content hash or fast fingerprint for a file.
        
        This uses a fast path for large media files to avoid repeatedly hashing
        multi-GB inputs when computing cache keys and manifests. For files above
        a size threshold, we return a stable fingerprint based on file size and
        modification time, which is sufficient for cache invalidation while
        dramatically reducing I/O.
        
        Args:
            filepath: Path to the file
            
        Returns:
            Hex digest string representing the file identity.
        """
        try:
            st = filepath.stat()
            size_bytes = st.st_size
            mtime_ns = int(st.st_mtime_ns)
            
            # Fast path for large files (e.g., videos). Threshold: 500 MB.
            LARGE_FILE_THRESHOLD = 500 * 1024 * 1024
            if size_bytes >= LARGE_FILE_THRESHOLD:
                # Fingerprint: sha256 of size + mtime + name to remain stable across runs
                fp = f"fp:{filepath.name}:{size_bytes}:{mtime_ns}"
                return hashlib.sha256(fp.encode()).hexdigest()
        except OSError:
            # If we can't stat the file, fall back to a deterministic missing hash
            return hashlib.sha256(b"missing_file").hexdigest()
        
        # Small files: compute true content hash
        hash_obj = hashlib.sha256()
        try:
            with filepath.open('rb') as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    hash_obj.update(chunk)
            return hash_obj.hexdigest()
        except IOError:
            # Return a deterministic hash for missing files
            return hashlib.sha256(b"missing_file").hexdigest()