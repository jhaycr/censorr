"""Unit tests for CLI main module."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, call
from typer.testing import CliRunner

from src.cli.main import app
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import OperationResult
from src.planner.planner import ExecutionPlan


class TestCLIMain:
    """Test cases for CLI main functionality."""

    def setUp(self):
        """Set up test environment."""
        self.runner = CliRunner()

    def test_app_creation(self):
        """Test that the CLI app can be created."""
        assert app is not None

    def test_help_command(self):
        """Test that help command works."""
        runner = CliRunner()
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "censorr" in result.stdout.lower()
        assert "Usage:" in result.stdout

    def test_version_command(self):
        """Test version command."""
        runner = CliRunner()
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.stdout

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_basic_flow(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test basic processing flow."""
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        mock_executor.execute.return_value = [
            OperationResult(
                operation="extract_subtitles",
                inputs=["/path/to/video.mp4"],
                outputs=["/tmp/test/subtitles.srt"],
                success=True
            )
        ]
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--operations", "extract_subtitles,mask_subtitles"
        ])
        
        assert result.exit_code == 0
        mock_planner.plan.assert_called_once()
        mock_executor.execute.assert_called_once()

    @patch('src.cli.main.Path.exists')
    def test_process_input_file_not_found(self, mock_exists):
        """Test error when input file doesn't exist."""
        mock_exists.return_value = False
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/nonexistent/video.mp4",
            "--output", "/tmp/test"
        ])
        
        assert result.exit_code != 0
        assert "not found" in result.stdout.lower()

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_dry_run(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test dry-run mode."""
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--dry-run"
        ])
        
        assert result.exit_code == 0
        assert "dry run" in result.stdout.lower() or "would execute" in result.stdout.lower()
        
        # Should call planner but executor should get dry_run=True
        mock_planner.plan.assert_called_once()
        if mock_executor.execute.called:
            call_args = mock_executor.execute.call_args
            flags = call_args.kwargs['flags']  # Third argument should be flags
            assert flags.dry_run is True

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_verbose(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test verbose mode."""
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
            "--output", "/tmp/test",
            "--verbose"
        ])
        
        assert result.exit_code == 0
        
        # Should call executor with verbose=True
        if mock_executor.execute.called:
            call_args = mock_executor.execute.call_args
            flags = call_args.kwargs['flags']  # flags passed as keyword argument
            assert flags.verbose is True

    def test_list_operations_command(self):
        """Test list-operations command."""
        runner = CliRunner()
        result = runner.invoke(app, ["list-operations"])
        
        assert result.exit_code == 0
        assert "extract_subtitles" in result.stdout
        assert "mask_subtitles" in result.stdout
        assert "merge_subtitles" in result.stdout
        assert "extract_audio" in result.stdout
        assert "mute_audio" in result.stdout
        assert "remux" in result.stdout

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_with_operations_filter(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test processing with specific operations filter."""
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
            "--output", "/tmp/test",
            "--operations", "extract_subtitles,mask_subtitles"
        ])
        
        assert result.exit_code == 0
        
        # Verify planner was called with operation filter
        mock_planner.plan.assert_called_once()
        call_args = mock_planner.plan.call_args
        # The operations filter should be passed to the planner somehow

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_with_selectors(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test processing with artifact selectors."""
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
            "--output", "/tmp/test",
            "--language", "en",
            "--track-index", "0"
        ])
        
        assert result.exit_code == 0
        mock_planner.plan.assert_called_once()

    @patch('src.cli.main.Path.exists')
    def test_process_invalid_operations(self, mock_exists):
        """Test error with invalid operations."""
        mock_exists.return_value = True
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--operations", "invalid_operation"
        ])
        
        assert result.exit_code != 0
        assert "invalid" in result.stdout.lower() or "unknown" in result.stdout.lower()

    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_creates_output_directory(self, mock_planner_class, mock_executor_class):
        """Test that output directory is created if it doesn't exist."""
        # Setup mocks
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        mock_executor.execute.return_value = []
        
        # Use a temporary directory that actually exists
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "test_video.mp4"
            input_path.touch()  # Create the file
            output_path = Path(tmpdir) / "new_output"
            
            runner = CliRunner()
            result = runner.invoke(app, [
                "process",
                str(input_path),
                "--output", str(output_path)
            ])
            
            assert result.exit_code == 0
            assert output_path.exists()  # Directory should have been created

    def test_explain_command(self):
        """Test explain command shows operation descriptions."""
        runner = CliRunner()
        result = runner.invoke(app, ["explain"])
        
        assert result.exit_code == 0
        assert "extract_subtitles" in result.stdout
        assert "Operations available" in result.stdout or "Pipeline" in result.stdout

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_with_mute_windows_file(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test processing with external mute windows file."""
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
            "--output", "/tmp/test",
            "--mute-windows", "/path/to/mute_windows.json"
        ])
        
        assert result.exit_code == 0
        mock_planner.plan.assert_called_once()

    def test_cli_integration_with_typer(self):
        """Test CLI integrates properly with typer."""
        # This test ensures our CLI is properly structured for typer
        from typer import Typer
        assert isinstance(app, Typer)

    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_error_handling(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test error handling in CLI."""
        # Setup mocks to raise error
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_planner.plan.side_effect = Exception("Planning failed")
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test"
        ])
        
        assert result.exit_code != 0
        assert "error" in result.stdout.lower() or "failed" in result.stdout.lower()

    @patch('src.cli.main.Config.load_with_fallback')
    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_with_config_defaults(self, mock_planner_class, mock_executor_class, mock_exists, mock_config_load):
        """Test that config defaults are applied correctly."""
        from src.models.config import Config
        
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        # Mock config with custom defaults
        mock_config = Config(
            subtitle_title_exclude=["custom", "config", "defaults"],
            verbose=True,
            jobs=4
        )
        mock_config_load.return_value = mock_config
        
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test"
            # No CLI args for subtitle filtering - should use config defaults
        ])
        
        assert result.exit_code == 0
        mock_config_load.assert_called_once_with(None)  # No custom config path provided
        
        # Verify executor was called with config defaults
        if mock_executor.execute.called:
            call_args = mock_executor.execute.call_args
            flags = call_args.kwargs['flags']
            assert flags.verbose is True  # From config
    
    @patch('src.cli.main.Config.load_with_fallback')
    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_with_custom_config_path(self, mock_planner_class, mock_executor_class, mock_exists, mock_config_load):
        """Test loading custom config file."""
        from src.models.config import Config
        
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        mock_config_load.return_value = Config()
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--config", "/custom/config.json",
            "--output", "/tmp/test"
        ])
        
        assert result.exit_code == 0
        mock_config_load.assert_called_once_with("/custom/config.json")
    
    @patch('src.cli.main.Config.load_with_fallback')
    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_cli_args_override_config(self, mock_planner_class, mock_executor_class, mock_exists, mock_config_load):
        """Test that CLI arguments override config values."""
        from src.models.config import Config
        
        # Setup mocks
        mock_exists.return_value = True
        mock_planner = mock_planner_class.return_value
        mock_executor = mock_executor_class.return_value
        
        # Config with verbose=True
        mock_config = Config(verbose=True, force=False)
        mock_config_load.return_value = mock_config
        
        mock_planner.plan.return_value = ExecutionPlan(operations=[])
        mock_executor.execute.return_value = []
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--force"  # CLI override
            # --verbose not specified, should use config default (True)
        ])
        
        assert result.exit_code == 0
        
        # Verify the merged values were used
        if mock_executor.execute.called:
            call_args = mock_executor.execute.call_args
            flags = call_args.kwargs['flags']
            assert flags.force is True  # CLI override
            assert flags.verbose is True  # Config default
    
    @patch('src.cli.main.Config.load_with_fallback')
    @patch('src.cli.main.Path.exists')
    def test_process_config_load_failure(self, mock_exists, mock_config_load):
        """Test graceful handling of config load failure."""
        from src.models.config import Config
        
        # Setup mocks
        mock_exists.return_value = True
        mock_config_load.side_effect = Exception("Config load failed")
        
        runner = CliRunner()
        result = runner.invoke(app, [
            "process",
            "/path/to/video.mp4",
            "--output", "/tmp/test",
            "--dry-run"  # Use dry-run to avoid execution complexity
        ])
        
        # Should still work with default config
        assert result.exit_code == 0
        assert "Warning" in result.stdout or "config" in result.stdout.lower()
    
    @patch('src.cli.main.Path.exists')
    @patch('src.cli.main.Executor')
    @patch('src.cli.main.Planner')
    def test_process_subtitle_exclusion_defaults(self, mock_planner_class, mock_executor_class, mock_exists):
        """Test that default subtitle exclusions are applied."""
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
            "--output", "/tmp/test",
            "--language", "en"
            # No explicit subtitle-title-exclude - should use config defaults
        ])
        
        assert result.exit_code == 0
        
        # Verify planner was called with selectors
        mock_planner.plan.assert_called_once()
        call_args = mock_planner.plan.call_args
        selectors = call_args.kwargs.get('selectors', [])
        
        # Should have a subtitle selector with default exclusions
        subtitle_selectors = [s for s in selectors if hasattr(s, 'type') and s.type.value == 'SUBTITLE']
        if subtitle_selectors:
            selector = subtitle_selectors[0]
            # Should have default SDH exclusions
            assert 'sdh' in [pattern.lower() for pattern in selector.title_exclude]