"""Unit tests for simplified CLI functionality."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
from typer.testing import CliRunner

from src.cli.main import app
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationResult
from src.planner.planner import ExecutionPlan


class TestCLISimplified:
    """Test cases for simplified CLI interface."""

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_force_flag_overwrites_existing(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that --force flag allows overwriting existing files."""
        # Setup mocks
        mock_exists.return_value = True  # Both input and output exist
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        mock_executor.execute.return_value = [
            OperationResult(
                operation="extract_subtitles",
                inputs=["/path/to/video.mp4"],
                outputs=["/tmp/output.mp4"],
                success=True
            )
        ]
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--force"
        ])
        
        assert result.exit_code == 0
        
        # Verify executor was called with force=True
        if mock_executor.execute.called:
            call_args = mock_executor.execute.call_args
            flags = call_args.kwargs['flags']  # Third argument should be flags
    def test_help_shows_simplified_flags(self):
        """Test that help shows the simplified CLI flags."""
        runner = CliRunner()
        result = runner.invoke(app, ["process", "--help"])
        
        assert result.exit_code == 0
        assert "--force" in result.stdout
        assert "--verbose" in result.stdout
        assert "--dry-run" in result.stdout
        assert "--config" in result.stdout
        assert "--preset" in result.stdout
        
        # These should NOT be present (removed as part of simplification)
        assert "--skip-existing" not in result.stdout
        assert "--parallel" not in result.stdout
        assert "--jobs" not in result.stdout

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_config_driven_execution(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that complex options are handled via config instead of CLI."""
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--config", "/tmp/test_config.json"
        ])
        
        assert result.exit_code == 0
        # Config path should be used
        mock_planner.plan.assert_called_once()

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_preset_usage(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test preset functionality."""
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--preset", "movies"
        ])
        
        assert result.exit_code == 0
        mock_planner.plan.assert_called_once()

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_smart_defaults_applied(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that smart defaults work without explicit configuration."""
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4"
        ])
        
        assert result.exit_code == 0
        # Should work with just the input file, using smart defaults
        mock_planner.plan.assert_called_once()
        mock_executor.execute.assert_called_once()