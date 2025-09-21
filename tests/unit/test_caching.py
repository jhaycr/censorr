"""Tests for the caching module."""
import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from src.caching import CacheKey, CacheManager
from src.models.artifacts import Artifact, ArtifactType
from src.models.common import ManifestEntry
from src.models.operations import OperationFlags


class TestCacheKey:
    """Test cache key generation and serialization."""
    
    def test_cache_key_creation(self):
        """Test creating a cache key with basic inputs."""
        key = CacheKey(
            operation_name="test_op",
            input_hashes=["hash1", "hash2"],
            params_hash="params_hash"
        )
        
        assert key.operation_name == "test_op"
        assert key.input_hashes == ["hash1", "hash2"]
        assert key.params_hash == "params_hash"
    
    def test_cache_key_to_string_deterministic(self):
        """Test that cache key string representation is deterministic."""
        key1 = CacheKey(
            operation_name="test_op",
            input_hashes=["hash1", "hash2"],
            params_hash="params_hash"
        )
        key2 = CacheKey(
            operation_name="test_op",
            input_hashes=["hash1", "hash2"],
            params_hash="params_hash"
        )
        
        assert key1.to_string() == key2.to_string()
    
    def test_cache_key_to_string_different_inputs(self):
        """Test that different inputs produce different cache keys."""
        key1 = CacheKey(
            operation_name="test_op",
            input_hashes=["hash1", "hash2"],
            params_hash="params_hash"
        )
        key2 = CacheKey(
            operation_name="test_op",
            input_hashes=["hash1", "hash3"],  # Different hash
            params_hash="params_hash"
        )
        
        assert key1.to_string() != key2.to_string()
    
    def test_cache_key_string_length(self):
        """Test that cache key string is reasonably short."""
        key = CacheKey(
            operation_name="very_long_operation_name_that_might_cause_issues",
            input_hashes=["very_long_hash_1", "very_long_hash_2"],
            params_hash="very_long_params_hash"
        )
        
        # Should be truncated to 16 characters
        assert len(key.to_string()) == 16


class TestCacheManager:
    """Test cache manager functionality."""
    
    @pytest.fixture
    def temp_workdir(self):
        """Create a temporary working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    @pytest.fixture
    def cache_manager(self, temp_workdir):
        """Create a cache manager with temp workdir."""
        return CacheManager(temp_workdir)
    
    @pytest.fixture
    def sample_artifact(self, temp_workdir):
        """Create a sample artifact with content."""
        artifact_path = temp_workdir / "sample.txt"
        artifact_path.write_text("sample content")
        return Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(artifact_path),
            metadata={"language": "en"}
        )
    
    def test_cache_manager_initialization(self, temp_workdir):
        """Test cache manager initialization creates workdir."""
        workdir = temp_workdir / "new_workdir"
        assert not workdir.exists()
        
        cache_manager = CacheManager(workdir)
        assert workdir.exists()
        assert cache_manager.workdir == workdir
    
    def test_get_operation_dir(self, cache_manager, temp_workdir):
        """Test getting operation directory creates proper layout."""
        cache_key = CacheKey(
            operation_name="test_op",
            input_hashes=["hash1"],
            params_hash="params"
        )
        
        op_dir = cache_manager.get_operation_dir("test_op", cache_key)
        
        expected_path = temp_workdir / "test_op" / cache_key.to_string()
        assert op_dir == expected_path
        assert op_dir.exists()
    
    def test_create_cache_key(self, cache_manager, sample_artifact):
        """Test creating cache key from operation inputs."""
        inputs = [sample_artifact]
        params = {"verbose": True, "strategy": "default"}
        
        cache_key = cache_manager.create_cache_key("test_op", inputs, params)
        
        assert cache_key.operation_name == "test_op"
        assert len(cache_key.input_hashes) == 1
        assert "sample.txt:" in cache_key.input_hashes[0]
        assert cache_key.params_hash is not None
    
    def test_create_cache_key_missing_file(self, cache_manager, temp_workdir):
        """Test creating cache key with missing input file."""
        missing_path = temp_workdir / "missing.txt"
        artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(missing_path),
            metadata={"language": "en"}
        )
        
        cache_key = cache_manager.create_cache_key("test_op", [artifact], {})
        
        assert len(cache_key.input_hashes) == 1
        assert cache_key.input_hashes[0] == "missing.txt:missing"
    
    def test_manifest_path(self, cache_manager, temp_workdir):
        """Test getting manifest path."""
        op_dir = temp_workdir / "test_op" / "cache_key"
        manifest_path = cache_manager.get_manifest_path(op_dir)
        
        assert manifest_path == op_dir / "manifest.json"
    
    def test_load_manifest_missing(self, cache_manager, temp_workdir):
        """Test loading manifest when file doesn't exist."""
        op_dir = temp_workdir / "test_op" / "cache_key"
        op_dir.mkdir(parents=True)
        
        manifest = cache_manager.load_manifest(op_dir)
        assert manifest is None
    
    def test_load_manifest_invalid_json(self, cache_manager, temp_workdir):
        """Test loading manifest with invalid JSON."""
        op_dir = temp_workdir / "test_op" / "cache_key"
        op_dir.mkdir(parents=True)
        
        manifest_path = cache_manager.get_manifest_path(op_dir)
        manifest_path.write_text("invalid json")
        
        manifest = cache_manager.load_manifest(op_dir)
        assert manifest is None
    
    def test_save_and_load_manifest(self, cache_manager, sample_artifact, temp_workdir):
        """Test saving and loading a valid manifest."""
        op_dir = temp_workdir / "test_op" / "cache_key"
        op_dir.mkdir(parents=True)
        
        # Create output artifact
        output_path = op_dir / "output.txt"
        output_path.write_text("output content")
        output_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(output_path),
            metadata={"language": "en"}
        )
        
        # Save manifest
        params = {"verbose": True}
        manifest = cache_manager.save_manifest(
            op_dir, "test_op", [sample_artifact], [output_artifact], params
        )
        
        # Verify manifest structure
        assert manifest.op == "test_op"
        assert len(manifest.inputs) == 1
        assert len(manifest.outputs) == 1
        assert manifest.params == params
        
        # Load manifest and verify
        loaded_manifest = cache_manager.load_manifest(op_dir)
        assert loaded_manifest is not None
        assert loaded_manifest.op == manifest.op
        assert loaded_manifest.inputs == manifest.inputs
        assert loaded_manifest.outputs == manifest.outputs
    
    def test_is_cached_no_manifest(self, cache_manager, sample_artifact):
        """Test cache check when no manifest exists."""
        is_cached, op_dir = cache_manager.is_cached(
            "test_op", [sample_artifact], {}, OperationFlags()
        )
        
        assert not is_cached
        assert op_dir is not None
    
    def test_is_cached_force_flag(self, cache_manager, sample_artifact, temp_workdir):
        """Test that force flag bypasses cache."""
        # Create a valid cache first
        cache_key = cache_manager.create_cache_key("test_op", [sample_artifact], {})
        op_dir = cache_manager.get_operation_dir("test_op", cache_key)
        
        output_path = op_dir / "output.txt"
        output_path.write_text("cached output")
        output_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(output_path),
            metadata={"language": "en"}
        )
        
        cache_manager.save_manifest(op_dir, "test_op", [sample_artifact], [output_artifact], {})
        
        # Check cache with force flag
        flags = OperationFlags(force=True)
        is_cached, _ = cache_manager.is_cached("test_op", [sample_artifact], {}, flags)
        
        assert not is_cached
    
    def test_is_cached_missing_output(self, cache_manager, sample_artifact, temp_workdir):
        """Test cache check when output files are missing."""
        cache_key = cache_manager.create_cache_key("test_op", [sample_artifact], {})
        op_dir = cache_manager.get_operation_dir("test_op", cache_key)
        
        # Create manifest with missing output
        missing_output_path = op_dir / "missing_output.txt"
        output_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(missing_output_path),
            metadata={"language": "en"}
        )
        
        cache_manager.save_manifest(op_dir, "test_op", [sample_artifact], [output_artifact], {})
        
        # Check cache
        is_cached, _ = cache_manager.is_cached("test_op", [sample_artifact], {}, OperationFlags())
        
        assert not is_cached
    
    def test_is_cached_valid(self, cache_manager, sample_artifact, temp_workdir):
        """Test cache check with valid cached result."""
        cache_key = cache_manager.create_cache_key("test_op", [sample_artifact], {})
        op_dir = cache_manager.get_operation_dir("test_op", cache_key)
        
        # Create valid output
        output_path = op_dir / "output.txt"
        output_path.write_text("cached output")
        output_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(output_path),
            metadata={"language": "en"}
        )
        
        cache_manager.save_manifest(op_dir, "test_op", [sample_artifact], [output_artifact], {})
        
        # Check cache
        is_cached, returned_op_dir = cache_manager.is_cached(
            "test_op", [sample_artifact], {}, OperationFlags()
        )
        
        assert is_cached
        assert returned_op_dir == op_dir
    
    def test_is_cached_modified_output(self, cache_manager, sample_artifact, temp_workdir):
        """Test cache check when output has been modified."""
        cache_key = cache_manager.create_cache_key("test_op", [sample_artifact], {})
        op_dir = cache_manager.get_operation_dir("test_op", cache_key)
        
        # Create output and save manifest
        output_path = op_dir / "output.txt"
        output_path.write_text("original content")
        output_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(output_path),
            metadata={"language": "en"}
        )
        
        cache_manager.save_manifest(op_dir, "test_op", [sample_artifact], [output_artifact], {})
        
        # Modify output file
        output_path.write_text("modified content")
        
        # Check cache
        is_cached, _ = cache_manager.is_cached("test_op", [sample_artifact], {}, OperationFlags())
        
        assert not is_cached
    
    def test_hash_file_consistency(self, cache_manager, temp_workdir):
        """Test that file hashing is consistent."""
        test_file = temp_workdir / "test.txt"
        test_file.write_text("test content")
        
        hash1 = cache_manager._hash_file(test_file)
        hash2 = cache_manager._hash_file(test_file)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length
    
    def test_hash_file_missing(self, cache_manager, temp_workdir):
        """Test hashing missing file returns deterministic value."""
        missing_file = temp_workdir / "missing.txt"
        
        hash_value = cache_manager._hash_file(missing_file)
        
        assert hash_value is not None
        assert len(hash_value) == 64
    
    def test_params_hash_deterministic(self, cache_manager, sample_artifact):
        """Test that parameters hash deterministically."""
        params1 = {"verbose": True, "strategy": "default"}
        params2 = {"strategy": "default", "verbose": True}  # Different order
        
        key1 = cache_manager.create_cache_key("test_op", [sample_artifact], params1)
        key2 = cache_manager.create_cache_key("test_op", [sample_artifact], params2)
        
        # Should be the same due to sorted JSON serialization
        assert key1.params_hash == key2.params_hash