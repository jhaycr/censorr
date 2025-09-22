"""Audio muting operation for applying mute windows to audio tracks."""
import json
from pathlib import Path
from typing import List, Dict, Any

from src.adapters.ffmpeg import FFmpegAdapter
from src.error_handling import ExternalToolRunner
from src.models.artifacts import Artifact, ArtifactType
from src.models.common import MuteWindow
from src.models.operations import Operation, OperationFlags


class MuteAudioOperation(Operation):
    """Operation to apply mute windows to audio tracks.
    
    This operation processes audio artifacts and applies mute windows based on:
    - Mute windows stored in artifact metadata (from subtitle processing)
    - External mute windows files (JSON format)
    
    The operation supports combining multiple sources of mute windows and applies
    them using FFmpeg's volume filter.
    """
    
    def __init__(self):
        """Initialize the mute audio operation."""
        super().__init__("mute_audio")
        self.ffmpeg = FFmpegAdapter()
    
    @property
    def consumes(self) -> List[ArtifactType]:
        """Return the artifact types this operation consumes.
        
        Returns:
            List containing AUDIO artifact type and optionally SUBTITLE for mute windows
        """
        return [ArtifactType.AUDIO]
    
    @property
    def produces(self) -> List[ArtifactType]:
        """Return the artifact types this operation produces.
        
        Returns:
            List containing AUDIO artifact type
        """
        return [ArtifactType.AUDIO]
    
    def run(self, inputs: List[Artifact], workdir: Path, flags: OperationFlags) -> List[Artifact]:
        """Execute the operation.
        
        Args:
            inputs: List of input artifacts
            workdir: Working directory for outputs
            flags: Execution flags
            
        Returns:
            List of processed audio artifacts with mute windows applied
        """
        try:
            # Find audio artifacts
            audio_artifacts = [
                artifact for artifact in inputs
                if artifact.type == ArtifactType.AUDIO
            ]
            
            if not audio_artifacts:
                raise ValueError("No audio artifacts found for mute processing")
            
            # Set up error handling
            tool_runner = ExternalToolRunner(
                execution_logger=getattr(self, '_execution_logger', None),
                log_entry=getattr(self, '_log_entry', None)
            )
            
            results = []
            
            for audio_artifact in audio_artifacts:
                # Collect mute windows from various sources
                mute_windows = self._collect_mute_windows(audio_artifact)
                
                if flags.verbose:
                    print(f"Found {len(mute_windows)} mute windows for {audio_artifact.path}")
                
                # Generate output path
                output_path = self._generate_output_path(audio_artifact.path, workdir)
                
                if not flags.dry_run:
                    if flags.verbose:
                        print(f"Applying mute windows to {audio_artifact.path}")
                    
                    # Apply mute windows using enhanced error handling
                    mute_result = tool_runner.run_ffmpeg_with_recovery(
                        self.ffmpeg, 'apply_mute_windows', workdir,
                        input_path=audio_artifact.path,
                        output_path=output_path,
                        mute_windows=mute_windows
                    )
                    
                    if not mute_result.success:
                        raise RuntimeError(f"Failed to apply mute windows to {audio_artifact.path}: {mute_result.error}")
                    
                    processed_path = mute_result.result
                else:
                    processed_path = output_path
                
                # Create result artifact
                result_metadata = audio_artifact.metadata.copy()
                result_metadata["mute_windows_applied"] = len(mute_windows)
                result_metadata["original_path"] = audio_artifact.path
                
                if not flags.dry_run and hasattr(mute_result, 'duration_ms'):
                    result_metadata["processing_duration_ms"] = mute_result.duration_ms
                
                result_artifact = Artifact(
                    type=ArtifactType.AUDIO,
                    path=processed_path,
                    metadata=result_metadata
                )
                
                results.append(result_artifact)
            
            return results
            
        except Exception as e:
            if flags.verbose:
                print(f"Error in mute_audio operation: {e}")
            raise
    
    def _collect_mute_windows(self, artifact: Artifact) -> List[MuteWindow]:
        """Collect mute windows from all available sources.
        
        Args:
            artifact: Audio artifact to process
            
        Returns:
            List of MuteWindow objects from all sources
        """
        mute_windows = []
        
        # Collect from artifact metadata (e.g., from subtitle processing)
        if "mute_windows" in artifact.metadata:
            metadata_windows = self._parse_mute_windows_from_metadata(
                artifact.metadata["mute_windows"]
            )
            mute_windows.extend(metadata_windows)
        
        # Collect from external file
        if "mute_windows_file" in artifact.metadata:
            file_windows = self._load_mute_windows_from_file(
                artifact.metadata["mute_windows_file"]
            )
            mute_windows.extend(file_windows)
        
        # Sort by start time to ensure proper processing
        mute_windows.sort(key=lambda w: w.start)
        
        return mute_windows
    
    def _parse_mute_windows_from_metadata(self, metadata: List[Dict[str, Any]]) -> List[MuteWindow]:
        """Parse mute windows from artifact metadata.
        
        Args:
            metadata: List of mute window dictionaries
            
        Returns:
            List of MuteWindow objects
            
        Raises:
            ValueError: If mute window data is invalid
        """
        mute_windows = []
        
        for window_data in metadata:
            try:
                mute_window = MuteWindow(**window_data)
                mute_windows.append(mute_window)
            except Exception as e:
                raise ValueError(f"Invalid mute window data: {window_data}, error: {e}")
        
        return mute_windows
    
    def _load_mute_windows_from_file(self, file_path: str) -> List[MuteWindow]:
        """Load mute windows from external JSON file.
        
        Args:
            file_path: Path to JSON file containing mute windows
            
        Returns:
            List of MuteWindow objects
            
        Raises:
            ValueError: If file cannot be read or parsed
        """
        try:
            with open(file_path, 'r') as f:
                windows_data = json.load(f)
            
            return self._parse_mute_windows_from_metadata(windows_data)
            
        except Exception as e:
            raise ValueError(f"Failed to load mute windows from {file_path}: {e}")
    
    def _generate_output_path(self, input_path: str, workdir: Path) -> str:
        """Generate output path for processed audio.
        
        Args:
            input_path: Path to input audio file
            workdir: Working directory
            
        Returns:
            Generated output path
        """
        input_path_obj = Path(input_path)
        extension = input_path_obj.suffix
        
        output_filename = f"muted_{input_path_obj.stem}{extension}"
        output_path = workdir / output_filename
        
        return str(output_path)