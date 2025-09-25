"""Video remuxing operation for combining processed tracks into final video."""
from pathlib import Path
from typing import List, Set

from src.adapters.ffmpeg import FFmpegAdapter
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import Operation, OperationFlags


class RemuxOperation(Operation):
    """Operation to remux video with processed audio and subtitle tracks.
    
    This operation combines:
    - Original or processed video track
    - Processed audio tracks (potentially muted)
    - Processed subtitle tracks (potentially masked)
    
    The operation produces a final video file with all tracks properly integrated.
    """
    
    def __init__(self):
        """Initialize the remux operation."""
        super().__init__("remux")
        self.ffmpeg = FFmpegAdapter()
    
    @property
    def consumes(self) -> Set[ArtifactType]:
        """Return the artifact types this operation consumes.
        
        Returns:
            Set containing VIDEO, AUDIO, and SUBTITLE artifact types
        """
        return {ArtifactType.VIDEO, ArtifactType.AUDIO, ArtifactType.SUBTITLE}
    
    @property
    def produces(self) -> Set[ArtifactType]:
        """Return the artifact types this operation produces.
        
        Returns:
            Set containing VIDEO artifact type
        """
        return {ArtifactType.VIDEO}
    
    def run(self, inputs: List[Artifact], workdir: Path, flags: OperationFlags) -> List[Artifact]:
        """Execute the operation.
        
        Args:
            inputs: List of input artifacts (video, audio, subtitle)
            workdir: Working directory for outputs
            flags: Execution flags
            
        Returns:
            List containing the remuxed video artifact
        """
        try:
            # Find video artifacts
            video_artifacts = [
                artifact for artifact in inputs
                if artifact.type == ArtifactType.VIDEO
            ]
            
            if not video_artifacts:
                raise ValueError("No video artifacts found for remuxing")
            
            if len(video_artifacts) > 1:
                raise ValueError("Multiple video artifacts found - remux expects exactly one video input")
            
            video_artifact = video_artifacts[0]
            
            # Find audio and subtitle artifacts
            audio_artifacts = [
                artifact for artifact in inputs
                if artifact.type == ArtifactType.AUDIO
            ]
            
            subtitle_artifacts = [
                artifact for artifact in inputs
                if artifact.type == ArtifactType.SUBTITLE
            ]
            
            # Prioritize muted audio over extracted audio
            audio_artifacts = self._prioritize_audio_artifacts(audio_artifacts)
            
            # Process subtitle artifacts based on mode
            subtitle_artifacts = self._process_subtitle_artifacts(subtitle_artifacts, workdir, flags)
            
            if flags.verbose:
                print(f"Found {len(audio_artifacts)} audio tracks for remuxing")
                for i, artifact in enumerate(audio_artifacts):
                    artifact_type = "muted" if "muted_audio" in artifact.path else "extracted"
                    print(f"  Audio track {i}: {artifact.path} ({artifact_type})")
                print(f"Using {len(subtitle_artifacts)} subtitle tracks for remuxing (mode: {flags.subtitle_mode})")
                for i, artifact in enumerate(subtitle_artifacts):
                    subtitle_type = self._get_subtitle_type(artifact)
                    print(f"  Subtitle track {i}: {artifact.path} ({subtitle_type})")
            
            # Prepare track lists
            audio_tracks = [artifact.path for artifact in audio_artifacts]
            subtitle_tracks = [artifact.path for artifact in subtitle_artifacts]
            
            # Generate output path
            output_path = self._generate_output_path(video_artifact.path, workdir)
            
            if not flags.dry_run:
                if flags.verbose:
                    print(f"Remuxing video: {video_artifact.path}")
                    if audio_tracks:
                        print(f"  Audio tracks: {audio_tracks}")
                    if subtitle_tracks:
                        print(f"  Subtitle tracks: {subtitle_tracks}")
                
                # Perform remuxing using FFmpeg
                try:
                    remuxed_path = self.ffmpeg.remux(
                        video_input=video_artifact.path,
                        output=output_path,
                        audio_tracks=audio_tracks,
                        subtitle_tracks=subtitle_tracks
                    )
                except Exception as e:
                    raise RuntimeError(f"Failed to remux video {video_artifact.path}: {e}")
            else:
                remuxed_path = output_path
            
            # Create result artifact with combined metadata
            result_metadata = video_artifact.metadata.copy()
            result_metadata.update({
                "input_video": video_artifact.path,
                "audio_tracks": len(audio_tracks),
                "subtitle_tracks": len(subtitle_tracks),
                "remuxed": True
            })
            
            # Preserve metadata from processed tracks
            if audio_artifacts:
                result_metadata["audio_metadata"] = [
                    artifact.metadata for artifact in audio_artifacts
                ]
            
            if subtitle_artifacts:
                result_metadata["subtitle_metadata"] = [
                    artifact.metadata for artifact in subtitle_artifacts
                ]
            
            result_artifact = Artifact(
                type=ArtifactType.VIDEO,
                path=remuxed_path,
                metadata=result_metadata
            )
            
            return [result_artifact]
            
        except Exception as e:
            if flags.verbose:
                print(f"Error in remux operation: {e}")
            raise
    
    def _prioritize_audio_artifacts(self, audio_artifacts: List[Artifact]) -> List[Artifact]:
        """Prioritize audio artifacts, preferring muted over extracted audio.
        
        Args:
            audio_artifacts: List of audio artifacts
            
        Returns:
            Prioritized list of audio artifacts
        """
        if not audio_artifacts:
            return audio_artifacts
        
        # Separate muted and extracted audio artifacts
        muted_artifacts = []
        extracted_artifacts = []
        
        for artifact in audio_artifacts:
            if "muted_audio" in artifact.path:
                muted_artifacts.append(artifact)
            else:
                extracted_artifacts.append(artifact)
        
        # If we have muted audio, use only muted audio (don't mix with extracted)
        # This prevents using both muted and extracted versions of the same track
        if muted_artifacts:
            return muted_artifacts
        else:
            return extracted_artifacts
    
    def _process_subtitle_artifacts(self, subtitle_artifacts: List[Artifact], workdir: Path, flags: OperationFlags) -> List[Artifact]:
        """Process subtitle artifacts based on the subtitle mode.
        
        Args:
            subtitle_artifacts: List of subtitle artifacts
            workdir: Working directory for sidecar files
            flags: Operation flags
            
        Returns:
            Processed list of subtitle artifacts for remuxing
        """
        if not subtitle_artifacts:
            return subtitle_artifacts
        
        # Create sidecar files if requested
        if flags.create_subtitle_sidecar:
            self._create_subtitle_sidecars(subtitle_artifacts, workdir, flags)
        
        # Handle subtitle mode
        if flags.subtitle_mode == "none":
            return []
        elif flags.subtitle_mode == "all":
            return subtitle_artifacts
        elif flags.subtitle_mode == "masked_only":
            return self._get_masked_subtitles_only(subtitle_artifacts)
        else:
            # Default to masked_only for unknown modes
            return self._get_masked_subtitles_only(subtitle_artifacts)
    
    def _get_masked_subtitles_only(self, subtitle_artifacts: List[Artifact]) -> List[Artifact]:
        """Filter subtitle artifacts to include only masked subtitles.
        
        Args:
            subtitle_artifacts: List of subtitle artifacts
            
        Returns:
            List containing only masked subtitle artifacts
        """
        masked_subtitles = []
        
        for artifact in subtitle_artifacts:
            # Check if this is a masked subtitle
            if "masked_subtitles" in artifact.path or artifact.metadata.get("profanity_filtered"):
                masked_subtitles.append(artifact)
        
        # If no masked subtitles found, fall back to merged or latest processed subtitles
        if not masked_subtitles:
            # Look for merged subtitles as fallback
            for artifact in subtitle_artifacts:
                if "merged_subtitles" in artifact.path or artifact.metadata.get("merged_from"):
                    masked_subtitles.append(artifact)
                    break
        
        return masked_subtitles
    
    def _create_subtitle_sidecars(self, subtitle_artifacts: List[Artifact], workdir: Path, flags: OperationFlags):
        """Create sidecar subtitle files alongside the remuxed video.
        
        Args:
            subtitle_artifacts: List of subtitle artifacts
            workdir: Working directory
            flags: Operation flags
        """
        # Get masked subtitles for sidecar creation
        masked_subtitles = self._get_masked_subtitles_only(subtitle_artifacts)
        
        for artifact in masked_subtitles:
            # Create sidecar filename based on video output
            sidecar_path = workdir / f"remuxed_subtitles_{artifact.metadata.get('language', 'und')}.srt"
            
            try:
                # Copy the masked subtitle to sidecar location
                import shutil
                shutil.copy2(artifact.path, sidecar_path)
                
                if flags.verbose:
                    print(f"Created subtitle sidecar: {sidecar_path}")
                    
            except Exception as e:
                if flags.verbose:
                    print(f"Failed to create subtitle sidecar {sidecar_path}: {e}")
    
    def _get_subtitle_type(self, artifact: Artifact) -> str:
        """Get a descriptive name for the subtitle type.
        
        Args:
            artifact: Subtitle artifact
            
        Returns:
            Description of subtitle type
        """
        if "masked_subtitles" in artifact.path or artifact.metadata.get("profanity_filtered"):
            return "masked"
        elif "merged_subtitles" in artifact.path or artifact.metadata.get("merged_from"):
            return "merged"
        elif artifact.metadata.get("forced"):
            return "forced"
        else:
            return "extracted"
    
    def _generate_output_path(self, input_path: str, workdir: Path) -> str:
        """Generate output path for remuxed video.
        
        Args:
            input_path: Path to input video file
            workdir: Working directory
            
        Returns:
            Generated output path
        """
        input_path_obj = Path(input_path)
        extension = input_path_obj.suffix
        
        output_filename = f"remuxed_{input_path_obj.stem}{extension}"
        output_path = workdir / output_filename
        
        return str(output_path)