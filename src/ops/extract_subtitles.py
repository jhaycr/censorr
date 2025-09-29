"""Extract subtitles operation.

Extracts subtitle tracks from video files using FFmpeg.
"""
from pathlib import Path
from typing import List, Optional, Set
from src.models.artifacts import Artifact, ArtifactType
from src.models.selectors import Selector
from src.models.operations import Operation, OperationResult, OperationFlags
from src.adapters.ffmpeg import FFmpegAdapter, FFmpegError, TrackInfo


class ExtractSubtitlesOperation(Operation):
    """Operation to extract subtitle tracks from video files."""
    
    def __init__(self):
        """Initialize the operation."""
        super().__init__("extract_subtitles")
        self.description = "Extract subtitle tracks from video files"
        self.ffmpeg = FFmpegAdapter()
    
    @property
    def consumes(self) -> Set[ArtifactType]:
        """Return the set of artifact types this operation consumes."""
        return {ArtifactType.VIDEO}
    
    @property
    def produces(self) -> Set[ArtifactType]:
        """Return the set of artifact types this operation produces."""
        return {ArtifactType.SUBTITLE}
    
    def run(self, inputs: List[Artifact], workdir: Path, flags: OperationFlags) -> List[Artifact]:
        """Execute the operation.
        
        Args:
            inputs: List of input artifacts
            workdir: Working directory for outputs
            flags: Execution flags
            
        Returns:
            List of produced artifacts
        """
        try:
            # Find video artifact
            video_artifact = None
            for artifact in inputs:
                if artifact.type == ArtifactType.VIDEO:
                    video_artifact = artifact
                    break
            
            if not video_artifact:
                raise ValueError("No video artifact found for subtitle extraction")
            
            # Probe video file for subtitle tracks
            try:
                media_info = self.ffmpeg.probe(video_artifact.path)
            except FFmpegError as e:
                raise RuntimeError(f"Failed to probe video file: {e}")
            
            # Get subtitle tracks
            subtitle_tracks = media_info.get_subtitle_tracks()
            
            if not subtitle_tracks:
                return []  # No subtitle tracks found
            
            # Apply selector filtering
            filtered_tracks = self._filter_tracks_by_selectors(subtitle_tracks, flags.selectors)
            
            if flags.dry_run:
                return self._handle_dry_run(video_artifact, filtered_tracks, workdir)
            
            # Build mapping from ffprobe's global stream index -> subtitle-relative index
            # FFmpeg -map 0:s:<n> expects <n> to be the index among ONLY subtitle streams.
            sub_index_map = {t.index: idx for idx, t in enumerate(subtitle_tracks)}

            # Extract subtitle tracks
            extracted_artifacts = []
            for i, track in enumerate(filtered_tracks):
                try:
                    output_path = self._generate_output_path(
                        video_artifact.path, 
                        track, 
                        i, 
                        str(workdir)
                    )
                    
                    # Extract subtitle track
                    # Map to the correct subtitle-relative index for FFmpeg
                    ffmpeg_sub_idx = sub_index_map.get(track.index)
                    if ffmpeg_sub_idx is None:
                        raise RuntimeError(f"Unable to map track index {track.index} to subtitle-relative index")

                    self.ffmpeg.extract_subtitles(
                        video_artifact.path,
                        output_path,
                        track_index=ffmpeg_sub_idx  # Correct subtitle-relative index for FFmpeg mapping
                    )
                    
                    # Create subtitle artifact
                    subtitle_artifact = Artifact(
                        type=ArtifactType.SUBTITLE,
                        path=output_path,
                        metadata={
                            "language": track.language,
                            "codec": track.codec,
                            "title": track.title,
                            "forced": track.forced,
                            "source_file": video_artifact.path,
                            # ffprobe global stream index and ffmpeg subtitle-relative index
                            "track_index": track.index,
                            "subtitle_stream_index": ffmpeg_sub_idx
                        }
                    )
                    
                    extracted_artifacts.append(subtitle_artifact)
                    
                except FFmpegError as e:
                    # Continue with other tracks if one fails
                    if flags.verbose:
                        print(f"Failed to extract track {track.index}: {e}")
                    continue
            
            return extracted_artifacts
            
        except (ValueError, RuntimeError):
            # Re-raise expected exceptions
            raise
        except Exception as e:
            raise RuntimeError(f"Unexpected error during subtitle extraction: {e}")
    
    def _generate_output_path(self, video_path: str, track: TrackInfo, index: int, workdir: str) -> str:
        """Generate output path for extracted subtitle.
        
        Args:
            video_path: Path to source video file
            track: Subtitle track info
            index: Track index for naming
            workdir: Working directory
            
        Returns:
            Output path for subtitle file
        """
        video_file = Path(video_path)
        workdir_path = Path(workdir)
        
        # Create base filename
        base_name = video_file.stem
        
        # Add language and index to filename
        language = track.language or "unknown"
        filename = f"{base_name}.{language}.{index}.srt"
        
        return str(workdir_path / filename)
    
    def _handle_dry_run(self, video_artifact: Artifact, tracks: List[TrackInfo], workdir: Path) -> List[Artifact]:
        """Handle dry run execution.
        
        Args:
            video_artifact: Source video artifact
            tracks: Subtitle tracks
            workdir: Working directory
            
        Returns:
            List of planned artifacts for dry run
        """
        planned_artifacts = []
        
        for i, track in enumerate(tracks):
            output_path = self._generate_output_path(
                video_artifact.path,
                track,
                i,
                str(workdir)
            )
            
            # Create planned artifact (not actually created)
            subtitle_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=output_path,
                metadata={
                    "language": track.language,
                    "codec": track.codec,
                    "title": track.title,
                    "forced": track.forced,
                    "source_file": video_artifact.path,
                    "track_index": track.index
                }
            )
            
            planned_artifacts.append(subtitle_artifact)
        
        return planned_artifacts
    
    def _filter_tracks_by_selectors(self, tracks, selectors):
        """Filter tracks based on selector criteria.
        
        Args:
            tracks: List of TrackInfo objects
            selectors: List of Selector objects
            
        Returns:
            List of filtered TrackInfo objects
        """
        if not selectors:
            return tracks  # No filtering if no selectors
        
        # Find subtitle selectors
        subtitle_selectors = [s for s in selectors if s.type.value == "SUBTITLE"]
        
        if not subtitle_selectors:
            return tracks  # No subtitle selectors, return all
        
        filtered_tracks = []
        for track in tracks:
            # Check if track matches any selector
            for selector in subtitle_selectors:
                if self._track_matches_selector(track, selector):
                    filtered_tracks.append(track)
                    break  # Stop checking other selectors for this track
        
        return filtered_tracks
    
    def _track_matches_selector(self, track, selector):
        """Check if a track matches a selector.
        
        Args:
            track: TrackInfo object
            selector: Selector object
            
        Returns:
            bool: True if track matches selector criteria
        """
        # Check language match (convert eng to en for compatibility)
        if selector.language:
            track_lang = track.language
            if track_lang == "eng":
                track_lang = "en"
            if track_lang != selector.language:
                return False
        
        # Check forced flag
        if selector.forced is not None:
            if track.forced != selector.forced:
                return False
        
        # Check title filtering for subtitles
        if hasattr(selector, 'title_include') or hasattr(selector, 'title_exclude') or hasattr(selector, 'title_regex'):
            if not selector._matches_title_filters(track.title):
                return False
        
        return True