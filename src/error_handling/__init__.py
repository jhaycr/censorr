"""Enhanced error handling framework for external tools."""
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union
from dataclasses import dataclass, field

# Type variable for function return types
T = TypeVar('T')


@dataclass
class ExternalToolResult:
    """Result of external tool execution."""
    
    success: bool
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None
    preserved_artifacts: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)


class ExternalToolRunner:
    """Enhanced runner for external tools with error handling and artifact preservation."""
    
    def __init__(self, execution_logger=None, log_entry=None):
        """Initialize the tool runner.
        
        Args:
            execution_logger: ExecutionLogger instance for logging
            log_entry: Current operation log entry
        """
        self.execution_logger = execution_logger
        self.log_entry = log_entry
        self.preserved_artifacts: List[str] = []
    
    def run_with_error_handling(
        self,
        func: Callable[..., T],
        *args,
        preserve_artifacts_on_error: bool = True,
        artifact_patterns: Optional[List[str]] = None,
        workdir: Optional[Path] = None,
        operation_name: str = "external_tool",
        **kwargs
    ) -> ExternalToolResult:
        """Run a function with enhanced error handling.
        
        Args:
            func: Function to execute
            *args: Arguments to pass to the function
            preserve_artifacts_on_error: Whether to preserve artifacts on failure
            artifact_patterns: File patterns to preserve (glob patterns)
            workdir: Working directory to search for artifacts
            operation_name: Name of the operation for logging
            **kwargs: Keyword arguments to pass to the function
            
        Returns:
            ExternalToolResult with success status and details
        """
        start_time = time.time()
        result = ExternalToolResult(success=False)
        
        try:
            if self.execution_logger and self.log_entry:
                self.execution_logger.add_operation_log(
                    self.log_entry, f"Starting {operation_name}"
                )
            
            # Execute the function
            func_result = func(*args, **kwargs)
            
            duration_ms = (time.time() - start_time) * 1000
            result.success = True
            result.result = func_result
            result.duration_ms = duration_ms
            
            if self.execution_logger and self.log_entry:
                self.execution_logger.add_operation_log(
                    self.log_entry, f"Completed {operation_name} successfully ({duration_ms:.1f}ms)"
                )
            
            return result
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            error_msg = str(e)
            
            result.error = error_msg
            result.duration_ms = duration_ms
            
            # Log the error
            if self.execution_logger and self.log_entry:
                self.execution_logger.add_operation_log(
                    self.log_entry, f"Error in {operation_name}: {error_msg}"
                )
                self.execution_logger.add_operation_log(
                    self.log_entry, f"Full traceback: {traceback.format_exc()}"
                )
            
            # Preserve artifacts if requested
            if preserve_artifacts_on_error and workdir:
                preserved = self._preserve_artifacts(workdir, artifact_patterns or ["*"])
                result.preserved_artifacts = preserved
                
                if preserved and self.execution_logger and self.log_entry:
                    self.execution_logger.add_operation_log(
                        self.log_entry, f"Preserved {len(preserved)} artifacts: {preserved}"
                    )
            
            return result
    
    def _preserve_artifacts(self, workdir: Path, patterns: List[str]) -> List[str]:
        """Preserve artifacts matching patterns.
        
        Args:
            workdir: Directory to search for artifacts
            patterns: Glob patterns to match
            
        Returns:
            List of preserved artifact paths
        """
        preserved = []
        workdir = Path(workdir)
        
        if not workdir.exists():
            return preserved
        
        # Create preservation directory
        preserve_dir = workdir / "preserved_artifacts"
        preserve_dir.mkdir(exist_ok=True)
        
        # Find and copy artifacts
        for pattern in patterns:
            for artifact_path in workdir.glob(pattern):
                if artifact_path.is_file() and artifact_path != preserve_dir:
                    try:
                        # Copy to preservation directory
                        preserved_path = preserve_dir / artifact_path.name
                        preserved_path.write_bytes(artifact_path.read_bytes())
                        preserved.append(str(preserved_path))
                        
                        if self.execution_logger and self.log_entry:
                            self.execution_logger.add_operation_log(
                                self.log_entry, f"Preserved artifact: {artifact_path} -> {preserved_path}"
                            )
                    except Exception as e:
                        if self.execution_logger and self.log_entry:
                            self.execution_logger.add_operation_log(
                                self.log_entry, f"Failed to preserve {artifact_path}: {e}"
                            )
        
        return preserved
    
    def run_ffmpeg_with_recovery(
        self,
        ffmpeg_adapter,
        method_name: str,
        workdir: Path,
        *args,
        **kwargs
    ) -> ExternalToolResult:
        """Run FFmpeg adapter method with enhanced error handling.
        
        Args:
            ffmpeg_adapter: FFmpegAdapter instance
            method_name: Name of the method to call
            workdir: Working directory
            *args: Arguments to pass to the method
            **kwargs: Keyword arguments to pass to the method (including heartbeat_interval)
            
        Returns:
            ExternalToolResult with success status and details
        """
        # Set up logging for the adapter
        if hasattr(ffmpeg_adapter, 'set_execution_logger'):
            ffmpeg_adapter.set_execution_logger(self.execution_logger, self.log_entry)
        
        # Extract heartbeat parameters from kwargs if present
        heartbeat_interval = kwargs.pop('heartbeat_interval', 10.0)
        heartbeat_context = kwargs.pop('heartbeat_context', None)
        
        # Get the method to call
        method = getattr(ffmpeg_adapter, method_name)
        
        # Define artifact patterns based on method
        artifact_patterns = self._get_artifact_patterns_for_method(method_name)
        
        # Create a wrapper that passes heartbeat_interval to _run_ffmpeg_command
        def method_with_heartbeat(*method_args, **method_kwargs):
            # Store original _run_ffmpeg_command
            original_run_command = ffmpeg_adapter._run_ffmpeg_command
            
            # Create wrapper that injects heartbeat parameters
            def run_command_with_heartbeat(cmd, expected_output, heartbeat_interval=10.0, heartbeat_context=None):
                return original_run_command(cmd, expected_output, heartbeat_interval=heartbeat_interval, heartbeat_context=heartbeat_context)
            
            # Temporarily replace the method
            ffmpeg_adapter._run_ffmpeg_command = run_command_with_heartbeat
            
            try:
                return method(*method_args, **method_kwargs)
            finally:
                # Restore original method
                ffmpeg_adapter._run_ffmpeg_command = original_run_command
        
        return self.run_with_error_handling(
            method_with_heartbeat,
            *args,
            preserve_artifacts_on_error=True,
            artifact_patterns=artifact_patterns,
            workdir=workdir,
            operation_name=f"ffmpeg_{method_name}",
            **kwargs
        )
    
    def _get_artifact_patterns_for_method(self, method_name: str) -> List[str]:
        """Get artifact preservation patterns for FFmpeg methods.
        
        Args:
            method_name: Name of the FFmpeg method
            
        Returns:
            List of glob patterns for artifacts to preserve
        """
        patterns = {
            'extract_audio': ['*.wav', '*.mp3', '*.flac', '*.m4a', '*.aac'],
            'extract_subtitles': ['*.srt', '*.vtt', '*.ass', '*.sub'],
            'apply_mute_windows': ['*.wav', '*.mp3', '*.flac', '*.m4a'],
            'remux': ['*.mkv', '*.mp4', '*.avi', '*.mov'],
            'probe': []  # No artifacts to preserve for probe
        }
        
        return patterns.get(method_name, ['*'])