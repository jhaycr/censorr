"""
Remux operation for combining video, audio, and subtitle streams.
"""
import logging
import re
import shutil
import hashlib
from pathlib import Path
from typing import List, Optional, Set

from ..adapters.ffmpeg import FFmpegAdapter
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import Operation, OperationFlags
from src.utils.filename_utils import (
    ensure_movie_edition_tag,
    is_episode_filename,
    build_sidecar_subtitle_path,
    handle_sidecar_collision
)


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
            original_audio_artifacts = [
                artifact for artifact in inputs
                if artifact.type == ArtifactType.AUDIO
            ]
            
            subtitle_artifacts = [
                artifact for artifact in inputs
                if artifact.type == ArtifactType.SUBTITLE
            ]
            
            # Prioritize muted audio over extracted audio (searches entire inputs list + output dir)
            audio_artifacts = self._prioritize_audio_artifacts(inputs, workdir)
            
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
            
            # Apply edition tagging for movies (not episodes)
            if not is_episode_filename(output_path):
                output_path = ensure_movie_edition_tag(output_path, "Censorr")
                if flags.verbose:
                    print(f"Applied Plex edition tag for movie: {Path(output_path).name}")
            elif flags.verbose:
                print(f"Skipped edition tag for episode: {Path(output_path).name}")
            
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
                    
                    # Verify audio parity if audio tracks were provided
                    if audio_tracks:
                        self._verify_audio_parity(audio_artifacts, remuxed_path, flags)
                        
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
    
    def _find_muted_audio_in_output_dir(self, workdir: Path, track_num: int) -> Optional[Artifact]:
        """Try to find muted audio files in the output directory."""
        logger = logging.getLogger(f"{self.__class__.__name__}")
        
        # Search in the parent directory (output base) for mute_audio folders
        logger.info(f"Remux workdir: {workdir}")
        output_base = workdir.parent.parent if 'remux' in str(workdir) else workdir
        logger.info(f"Searching for muted audio in: {output_base}")
        
        # Also try searching from workdir directly
        mute_audio_dirs = list(output_base.glob("mute_audio/*/"))
        if not mute_audio_dirs and output_base != workdir:
            logger.info(f"No mute_audio dirs in {output_base}, trying {workdir}")
            mute_audio_dirs = list(workdir.glob("mute_audio/*/"))
        
        logger.info(f"Found {len(mute_audio_dirs)} mute_audio directories")
        
        # Sort by modification time to get the most recent
        mute_audio_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
        
        for mute_dir in mute_audio_dirs:
            muted_file = mute_dir / f"muted_audio_track_{track_num}.wav"
            if muted_file.exists():
                logger.info(f"✓ Found muted audio in output directory: {muted_file}")
                import hashlib
                def calculate_checksum(file_path):
                    sha256_hash = hashlib.sha256()
                    with open(file_path, "rb") as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            sha256_hash.update(chunk)
                    return sha256_hash.hexdigest()
                return Artifact(
                    path=str(muted_file),
                    type=ArtifactType.AUDIO,
                    checksum=calculate_checksum(muted_file)
                )
        
        logger.warning(f"No muted audio found for track {track_num}")
        return None

    def _prioritize_audio_artifacts(self, artifacts: List[Artifact], workdir: Path) -> List[Artifact]:
        """Prioritize audio artifacts, preferring muted over extracted audio."""
        logger = logging.getLogger(f"{self.__class__.__name__}")
        
        audio_artifacts = [a for a in artifacts if a.type == ArtifactType.AUDIO]
        if not audio_artifacts:
            logger.warning("No audio artifacts available for remux")
            return []
        
        logger.info(f"Found {len(audio_artifacts)} audio artifacts:")
        for artifact in audio_artifacts:
            logger.info(f"  Audio: {artifact.path}")
        
        # Group by track number
        by_track = {}
        for artifact in audio_artifacts:
            # Extract track number from filename
            path_name = artifact.path.name if hasattr(artifact.path, 'name') else str(artifact.path).split('/')[-1]
            match = re.search(r'audio_track_(\d+)|muted_audio_track_(\d+)', path_name)
            if match:
                track_num = int(match.group(1) or match.group(2))
                if track_num not in by_track:
                    by_track[track_num] = []
                by_track[track_num].append(artifact)
        
        prioritized = []
        for track_num, track_artifacts in by_track.items():
            # Sort by priority: muted > extracted
            muted_artifacts = [a for a in track_artifacts if "muted_audio" in str(a.path)]
            extracted_artifacts = [a for a in track_artifacts if "extract_audio" in str(a.path)]
            
            if muted_artifacts:
                prioritized.extend(muted_artifacts)
                logger.info(f"✓ Using muted audio for track {track_num}: {muted_artifacts[0].path}")
            else:
                # Try to find muted audio in output directory
                logger.warning(f"⚠ Muted audio not provided as input for track {track_num}, searching output directory...")
                found_muted = self._find_muted_audio_in_output_dir(workdir, track_num)
                if found_muted:
                    prioritized.append(found_muted)
                    logger.info(f"✓ Found and using muted audio for track {track_num}: {found_muted.path}")
                elif extracted_artifacts:
                    prioritized.extend(extracted_artifacts)
                    logger.warning(f"⚠ Using extracted audio for track {track_num} (muted audio not found): {extracted_artifacts[0].path}")
                else:
                    logger.error(f"✗ No audio found for track {track_num}")
        
        return prioritized

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
                self._create_subtitle_sidecars(subtitle_artifacts, workdir, output_path, flags)        # Handle subtitle mode
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
    
    def _create_subtitle_sidecars(self, subtitle_artifacts: List[Artifact], workdir: Path, video_output_path: str, flags: OperationFlags):
        """Create sidecar subtitle files alongside the remuxed video.
        
        Args:
            subtitle_artifacts: List of subtitle artifacts
            workdir: Working directory
            video_output_path: Path to the remuxed video file
            flags: Operation flags
        """
        # Get masked subtitles for sidecar creation
        masked_subtitles = self._get_masked_subtitles_only(subtitle_artifacts)
        
        for artifact in masked_subtitles:
            language = artifact.metadata.get('language', 'und')
            
            # Use proper Plex-compatible sidecar naming
            sidecar_path = build_sidecar_subtitle_path(
                video_output_path, 
                language, 
                tag=flags.sidecar_tag
            )
            
            try:
                # Read subtitle content and calculate checksum
                with open(artifact.path, 'rb') as f:
                    content = f.read()
                    checksum = hashlib.md5(content).hexdigest()
                
                # Handle collision/reuse
                final_sidecar_path = handle_sidecar_collision(sidecar_path, checksum)
                
                if final_sidecar_path == sidecar_path:
                    # No collision or reusing existing
                    if Path(sidecar_path).exists():
                        if flags.verbose:
                            print(f"Reusing existing identical sidecar: {sidecar_path}")
                    else:
                        # Write new sidecar
                        with open(sidecar_path, 'wb') as f:
                            f.write(content)
                        if flags.verbose:
                            print(f"Created subtitle sidecar: {sidecar_path}")
                else:
                    # Using numbered collision path
                    with open(final_sidecar_path, 'wb') as f:
                        f.write(content)
                    if flags.verbose:
                        print(f"Created subtitle sidecar (collision handled): {final_sidecar_path}")
                        
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
    
    def _verify_audio_parity(self, audio_artifacts: List[Artifact], remuxed_path: str, flags: OperationFlags):
        """Verify audio parity between source and remuxed files.
        
        Args:
            audio_artifacts: List of audio artifacts used in remux
            remuxed_path: Path to remuxed video file
            flags: Operation flags
        """
        logger = logging.getLogger(f"{self.__class__.__name__}")
        
        for i, audio_artifact in enumerate(audio_artifacts):
            parity_result = self.ffmpeg.verify_audio_parity(audio_artifact.path, remuxed_path, i)
            
            if parity_result["status"] == "match":
                logger.info(f"✓ Audio parity verified for track {i}: {audio_artifact.path}")
                if flags.verbose:
                    print(f"✓ Audio parity verified for track {i}")
            elif parity_result["status"] == "mismatch":
                mismatches = ", ".join(parity_result["mismatches"])
                message = f"Audio parity mismatch for track {i}: {mismatches}"
                logger.warning(f"⚠ {message}")
                
                if flags.verbose:
                    print(f"⚠ {message}")
                    print(f"  Original: {parity_result['original']}")
                    print(f"  Remuxed:  {parity_result['remuxed']}")
                
                if flags.strict_audio_parity:
                    raise RuntimeError(f"Audio parity check failed in strict mode: {message}")
            else:
                error_message = f"Audio parity check error for track {i}: {parity_result['message']}"
                logger.error(f"✗ {error_message}")
                if flags.verbose:
                    print(f"✗ {error_message}")
                
                if flags.strict_audio_parity:
                    raise RuntimeError(f"Audio parity check failed: {error_message}")