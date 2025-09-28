"""Container smoke tests for Censorr.

Tests basic container functionality including help, version, and dry-run processing.
These tests are gated to run only when DOCKER_AVAILABLE=1 in environment.
"""
import os
import subprocess
import pytest
from pathlib import Path


def docker_available():
    """Check if Docker is available and accessible."""
    try:
        result = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def podman_available():
    """Check if Podman is available and accessible."""
    try:
        result = subprocess.run(
            ["podman", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_container_runtime():
    """Get available container runtime (docker or podman)."""
    if docker_available():
        return "docker"
    elif podman_available():
        return "podman"
    else:
        return None


@pytest.fixture(scope="session")
def container_runtime():
    """Fixture providing container runtime command."""
    runtime = get_container_runtime()
    if not runtime:
        pytest.skip("No container runtime (Docker/Podman) available")
    return runtime


@pytest.fixture(scope="session")
def container_image(container_runtime):
    """Fixture that ensures container image is built."""
    image_name = "censorr:test"
    
    # Check if image exists
    result = subprocess.run(
        [container_runtime, "image", "exists", image_name],
        capture_output=True
    )
    
    if result.returncode != 0:
        # Build image if it doesn't exist
        print(f"Building container image {image_name}...")
        build_result = subprocess.run(
            [container_runtime, "build", "-t", image_name, "."],
            cwd=Path(__file__).parent.parent.parent,  # Repository root
            capture_output=True,
            text=True
        )
        
        if build_result.returncode != 0:
            pytest.fail(f"Failed to build container image: {build_result.stderr}")
    
    return image_name


@pytest.mark.skipif(
    os.environ.get("DOCKER_AVAILABLE") != "1",
    reason="Container tests require DOCKER_AVAILABLE=1 environment variable"
)
class TestContainerSmoke:
    """Smoke tests for container functionality."""
    
    def test_container_help(self, container_runtime, container_image):
        """Test that container can display help message."""
        result = subprocess.run(
            [container_runtime, "run", "--rm", container_image, "--help"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"Help command failed: {result.stderr}"
        assert "CLI tool for censoring audio and subtitles" in result.stdout
        assert "Commands" in result.stdout
        assert "process" in result.stdout
    
    def test_container_version(self, container_runtime, container_image):
        """Test that container can display version information."""
        result = subprocess.run(
            [container_runtime, "run", "--rm", container_image, "--version"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"Version command failed: {result.stderr}"
        # Version output should contain version number
        assert result.stdout.strip(), "Version output should not be empty"
    
    def test_container_list_operations(self, container_runtime, container_image):
        """Test that container can list available operations."""
        result = subprocess.run(
            [container_runtime, "run", "--rm", container_image, "list-operations"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"List operations failed: {result.stderr}"
        assert "extract_subtitles" in result.stdout
        assert "mask_subtitles" in result.stdout
        assert "mute_audio" in result.stdout
        assert "remux" in result.stdout
    
    def test_container_explain(self, container_runtime, container_image):
        """Test that container can explain the pipeline."""
        result = subprocess.run(
            [container_runtime, "run", "--rm", container_image, "explain"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        assert result.returncode == 0, f"Explain command failed: {result.stderr}"
        assert "Pipeline Phases" in result.stdout or "pipeline" in result.stdout.lower()
    
    def test_container_invalid_file_dry_run(self, container_runtime, container_image):
        """Test container with invalid file path (should fail gracefully)."""
        result = subprocess.run([
            container_runtime, "run", "--rm",
            "-v", "/tmp:/app/workdir",  # Mount temp directory for workdir
            container_image,
            "process", "/nonexistent/file.mkv",
            "--output", "/app/workdir",
            "--dry-run"
        ], capture_output=True, text=True, timeout=60)
        
        # Should fail with non-zero exit code but not crash
        assert result.returncode != 0
        # Should have error message about missing file
        assert "not" in result.stderr.lower() or "error" in result.stderr.lower()
    
    def test_container_user_permissions(self, container_runtime, container_image):
        """Test that container runs as non-root user."""
        result = subprocess.run([
            container_runtime, "run", "--rm",
            container_image,
            "python", "-c", "import os; print(f'UID: {os.getuid()}, GID: {os.getgid()}')"
        ], capture_output=True, text=True, timeout=30)
        
        assert result.returncode == 0, f"User check failed: {result.stderr}"
        assert "UID: 10001, GID: 10001" in result.stdout
    
    def test_container_working_directory(self, container_runtime, container_image):
        """Test that container has correct working directory."""
        result = subprocess.run([
            container_runtime, "run", "--rm",
            container_image,
            "pwd"
        ], capture_output=True, text=True, timeout=30)
        
        assert result.returncode == 0, f"PWD command failed: {result.stderr}"
        assert result.stdout.strip() == "/app"
    
    def test_container_python_path(self, container_runtime, container_image):
        """Test that Python can import censorr modules."""
        result = subprocess.run([
            container_runtime, "run", "--rm",
            container_image,
            "python", "-c", "import src.cli.main; print('Import successful')"
        ], capture_output=True, text=True, timeout=30)
        
        assert result.returncode == 0, f"Python import failed: {result.stderr}"
        assert "Import successful" in result.stdout
    
    def test_container_ffmpeg_available(self, container_runtime, container_image):
        """Test that FFmpeg is available in the container."""
        result = subprocess.run([
            container_runtime, "run", "--rm",
            container_image,
            "ffmpeg", "-version"
        ], capture_output=True, text=True, timeout=30)
        
        assert result.returncode == 0, f"FFmpeg not available: {result.stderr}"
        assert "ffmpeg version" in result.stdout
    
    @pytest.mark.skipif(
        not Path("tests/fixtures").exists(),
        reason="Test fixtures directory not found"
    )
    def test_container_with_fixture_dry_run(self, container_runtime, container_image):
        """Test container dry-run with actual fixture file (if available)."""
        fixtures_dir = Path("tests/fixtures")
        if not fixtures_dir.exists():
            pytest.skip("No test fixtures available")
        
        # Look for a small test video file
        test_files = list(fixtures_dir.glob("*.mkv")) + list(fixtures_dir.glob("*.mp4"))
        if not test_files:
            pytest.skip("No test video files in fixtures")
        
        test_file = test_files[0]
        
        result = subprocess.run([
            container_runtime, "run", "--rm",
            "-v", f"{fixtures_dir.absolute()}:/media:ro",
            "-v", "/tmp:/app/workdir",
            container_image,
            "process", f"/media/{test_file.name}",
            "--output", "/app/workdir",
            "--language", "en",
            "--dry-run",
            "--verbose"
        ], capture_output=True, text=True, timeout=120)
        
        # Dry run should succeed or fail gracefully
        # (May fail due to missing tracks, but shouldn't crash)
        assert "dry-run" in result.stdout.lower() or result.returncode in [0, 1]


if __name__ == "__main__":
    # Allow running tests directly with environment variable check
    if os.environ.get("DOCKER_AVAILABLE") == "1":
        pytest.main([__file__, "-v"])
    else:
        print("Set DOCKER_AVAILABLE=1 to run container smoke tests")
        print("Example: DOCKER_AVAILABLE=1 python -m pytest tests/integration/test_container_smoke.py -v")