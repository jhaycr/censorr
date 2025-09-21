"""Unit tests for enhanced CLI functionality (skip/force/parallel controls)."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
from typer.testing import CliRunner

from src.cli.main import app
from src.models.artifacts import Artifact, ArtifactType


class TestCLIEnhancedControls:
    """Test cases for enhanced CLI control flags."""

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_force_flag_overwrites_existing(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that --force flag allows overwriting existing files."""
        # Setup mocks
        mock_exists.return_value = True  # Both input and output exist
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = [("extract_subtitles", [])]
        mock_executor.execute.return_value = [
            Artifact(type=ArtifactType.VIDEO, path="/tmp/output.mp4", metadata={})
        ]
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--force"
        ])
        
        assert result.exit_code == 0
        
        # Verify executor was called with force=True
        if mock_executor.execute.called:
            call_args = mock_executor.execute.call_args
            flags = call_args[0][2]  # Third argument should be flags
            assert flags.force is True

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_skip_existing_flag(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that --skip-existing flag skips processing when output exists."""
        # Setup mocks
        mock_exists.return_value = True  # Both input and output exist
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        # Mock planner to return empty plan when skipping
        mock_planner.plan.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--skip-existing"
        ])
        
        assert result.exit_code == 0
        
        # Should check for existing outputs and potentially skip
        mock_planner.plan.assert_called_once()

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_parallel_flag(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that --parallel flag enables parallel execution."""
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = [
            ("extract_subtitles", []),
            ("extract_audio", [])
        ]
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--parallel"
        ])
        
        assert result.exit_code == 0
        
        # Verify executor was called with parallel=True
        if mock_executor.execute.called:
            call_args = mock_executor.execute.call_args
            flags = call_args[0][2]  # Third argument should be flags
            assert flags.parallel is True

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_parallel_jobs_flag(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that --jobs flag sets the number of parallel jobs."""
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = [("extract_subtitles", [])]
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--jobs", "4"
        ])
        
        assert result.exit_code == 0
        
        # Verify executor was called with jobs=4
        if mock_executor.execute.called:
            call_args = mock_executor.execute.call_args
            flags = call_args[0][2]  # Third argument should be flags
            assert flags.max_jobs == 4

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_force_and_skip_existing_conflict(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that --force and --skip-existing flags conflict."""
        mock_exists.return_value = True
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--force",
            "--skip-existing"
        ])
        
        assert result.exit_code != 0
        assert "cannot be used together" in result.stdout.lower() or "conflicting" in result.stdout.lower()

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_parallel_with_jobs_auto_enables_parallel(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that --jobs automatically enables parallel mode."""
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = [("extract_subtitles", [])]
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--jobs", "2"
        ])
        
        assert result.exit_code == 0
        
        # Verify both parallel and jobs are set
        if mock_executor.execute.called:
            call_args = mock_executor.execute.call_args
            flags = call_args[0][2]
            assert flags.parallel is True
            assert flags.max_jobs == 2

    def test_help_shows_new_flags(self):
        """Test that help shows the new control flags."""
        runner = CliRunner()
        result = runner.invoke(app, ["process", "--help"])
        
        assert result.exit_code == 0
        assert "--force" in result.stdout
        assert "--skip-existing" in result.stdout
        assert "--parallel" in result.stdout
        assert "--jobs" in result.stdout

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_verbose_mode_with_control_flags(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test verbose output includes information about control flags."""
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = [("extract_subtitles", [])]
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--verbose",
            "--parallel",
            "--jobs", "3"
        ])
        
        assert result.exit_code == 0
        # Verbose mode should mention parallel execution
        assert "parallel" in result.stdout.lower() or "jobs" in result.stdout.lower()

    @patch('src.cli.main.Path.exists')
    def test_invalid_jobs_number(self, mock_exists):
        """Test error handling for invalid jobs number."""
        mock_exists.return_value = True
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--jobs", "0"
        ])
        
        assert result.exit_code != 0
        assert "jobs" in result.stdout.lower() and ("positive" in result.stdout.lower() or "greater" in result.stdout.lower())

    @patch('src.cli.main.Path.exists')
    def test_negative_jobs_number(self, mock_exists):
        """Test error handling for negative jobs number."""
        mock_exists.return_value = True
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--jobs", "-1"
        ])
        
        assert result.exit_code != 0
        assert "jobs" in result.stdout.lower() and ("positive" in result.stdout.lower() or "greater" in result.stdout.lower())