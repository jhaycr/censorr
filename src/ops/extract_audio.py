"""Extract audio operation.

Extracts audio tracks from video files using FFmpeg.
"""
from pathlib import Path
from typing import List, Set, Optional
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import Operation, OperationFlags
from src.adapters.ffmpeg import FFmpegAdapter, FFmpegError, TrackInfo
from src.error_handling import ExternalToolRunner


class ExtractAudioOperation(Operation):
    """Operation to extract audio tracks from video files."""
    
    def __init__(self, audio_format: str = "wav", language_filter: Optional[str] = None):
        """Initialize the operation.
        
        Args:
            audio_format: Output audio format (wav, mp3, flac, etc.)
            language_filter: Optional language filter for audio tracks
        """
        super().__init__("extract_audio")
        self.description = "Extract audio tracks from video files using FFmpeg"
        self.audio_format = audio_format
        self.language_filter = language_filter
        self.ffmpeg = FFmpegAdapter()
    
    @property
    def consumes(self) -> Set[ArtifactType]:
        """Return the set of artifact types this operation consumes."""
        return {ArtifactType.VIDEO}
    
    @property
    def produces(self) -> Set[ArtifactType]:
        """Return the set of artifact types this operation produces."""
        return {ArtifactType.AUDIO}
    
    def run(self, inputs: List[Artifact], workdir: Path, flags: OperationFlags) -> List[Artifact]:
        """Execute the operation.
        
        Args:
            inputs: List of input artifacts
            workdir: Working directory for outputs
            flags: Execution flags
            
        Returns:
            List of extracted audio artifacts
        """
        try:
            # Find video artifacts
            video_artifacts = [
                artifact for artifact in inputs 
                if artifact.type == ArtifactType.VIDEO
            ]
            
            if not video_artifacts:
                raise ValueError("No video artifacts found for audio extraction")
            
            # Process first video artifact (operation expects single video)
            video_artifact = video_artifacts[0]
            
            # Set up error handling
            tool_runner = ExternalToolRunner(
                execution_logger=getattr(self, '_execution_logger', None),
                log_entry=getattr(self, '_log_entry', None)
            )
            
            # Probe video file for audio tracks
            probe_result = tool_runner.run_ffmpeg_with_recovery(
                self.ffmpeg, 'probe', workdir, video_artifact.path
            )
            
            if not probe_result.success:
                raise RuntimeError(f"Failed to probe video file {video_artifact.path}: {probe_result.error}")
            
            media_info = probe_result.result
            # Store original audio codec info on the video artifact metadata for later use
            try:
                orig_audio_tracks = media_info.get_audio_tracks()
                if orig_audio_tracks:
                    # Use first audio track as baseline
                    first_track = orig_audio_tracks[0]
                    # codec
                    codec_val = getattr(first_track, "codec", None)
                    if isinstance(codec_val, str):
                        video_artifact.metadata["audio_codec"] = codec_val
                    # channels
                    channels_val = getattr(first_track, "channels", None)
                    if isinstance(channels_val, int):
                        video_artifact.metadata["audio_channels"] = channels_val
                    # sample_rate (string from ffprobe, keep as int if convertible)
                    sr_val = getattr(first_track, "sample_rate", None)
                    if isinstance(sr_val, str) and sr_val.isdigit():
                        video_artifact.metadata["audio_sample_rate"] = int(sr_val)
                    elif isinstance(sr_val, int):
                        video_artifact.metadata["audio_sample_rate"] = sr_val
                    # bitrate (string bits per second; store as e.g. '256k' if divisible)
                    br_val = getattr(first_track, "bitrate", None)
                    if isinstance(br_val, str) and br_val.isdigit():
                        try:
                            br_int = int(br_val)
                            # Convert to k suffix if clean multiple of 1000
                            if br_int % 1000 == 0:
                                video_artifact.metadata["audio_bitrate"] = f"{br_int // 1000}k"
                            else:
                                video_artifact.metadata["audio_bitrate_bps"] = br_int
                        except Exception:
                            pass
            except Exception:
                pass
            audio_tracks = media_info.get_audio_tracks()
            
            if flags.verbose:
                print(f"Found {len(audio_tracks)} audio tracks in {video_artifact.path}")
            
            # Filter audio tracks: prefer selectors (CLI --language) if provided; fallback to ctor filter
            filtered_tracks = self._filter_audio_tracks_by_selectors(audio_tracks, flags.selectors)
            if not filtered_tracks:
                filtered_tracks = self._filter_audio_tracks(audio_tracks)
            audio_tracks = filtered_tracks
            
            if not audio_tracks:
                if flags.verbose:
                    print("No audio tracks match the specified criteria")
                return []
            
            if flags.dry_run:
                return self._handle_dry_run(audio_tracks, workdir, video_artifact)
            
            # Extract audio tracks
            extracted_artifacts = []
            
            # Build mapping from ffprobe's global stream index -> audio-relative index for FFmpeg mapping
            all_audio_tracks = media_info.get_audio_tracks()
            audio_index_map = {t.index: idx for idx, t in enumerate(all_audio_tracks)}

            for track in audio_tracks:
                if flags.verbose:
                    print(f"Extracting audio track {track.index} ({track.codec}, {track.language or 'und'})")
                
                # Generate output filename
                output_filename = f"audio_track_{track.index}.{self.audio_format}"
                output_path = workdir / output_filename
                
                # Extract audio track using enhanced error handling
                ffmpeg_audio_idx = audio_index_map.get(track.index)
                if ffmpeg_audio_idx is None:
                    if flags.verbose:
                        print(f"Skipping track {track.index}: unable to map to audio-relative index")
                    continue

                extract_result = tool_runner.run_ffmpeg_with_recovery(
                    self.ffmpeg, 'extract_audio', workdir,
                    input_path=video_artifact.path,
                    output_path=str(output_path),
                    track_index=ffmpeg_audio_idx,
                    audio_format=self.audio_format,
                    channels=None,  # Preserve original channel layout
                    heartbeat_interval=8.0,
                    heartbeat_context=f"extracting audio track {track.index} ({track.codec}, {track.language or 'und'})"
                )
                
                if extract_result.success:
                    # Create audio artifact
                    audio_artifact = Artifact(
                        type=ArtifactType.AUDIO,
                        path=extract_result.result,
                        metadata={
                            "source_file": video_artifact.path,
                            "track": str(track.index),
                            "audio_stream_index": ffmpeg_audio_idx,
                            "codec": track.codec,
                            "language": track.language or "und",
                            "format": self.audio_format,
                            "duration_ms": extract_result.duration_ms
                        }
                    )
                    
                    extracted_artifacts.append(audio_artifact)
                else:
                    if flags.verbose:
                        print(f"Failed to extract audio track {track.index}: {extract_result.error}")
                        if extract_result.preserved_artifacts:
                            print(f"Preserved artifacts: {extract_result.preserved_artifacts}")
                    # Continue with other tracks
                    continue
            
            if flags.verbose:
                print(f"Successfully extracted {len(extracted_artifacts)} audio tracks")
            
            return extracted_artifacts
            
        except (ValueError, RuntimeError):
            # Re-raise expected exceptions
            raise
        except Exception as e:
            raise RuntimeError(f"Unexpected error during audio extraction: {e}")
    
    def _filter_audio_tracks(self, audio_tracks: List[TrackInfo]) -> List[TrackInfo]:
        """Filter audio tracks based on language and other criteria.
        
        Args:
            audio_tracks: List of available audio tracks
            
        Returns:
            Filtered list of audio tracks
        """
        if not self.language_filter:
            return audio_tracks
        
        filtered_tracks = []
        for track in audio_tracks:
            if track.language == self.language_filter:
                filtered_tracks.append(track)
        
        return filtered_tracks

    def _filter_audio_tracks_by_selectors(self, tracks: List[TrackInfo], selectors) -> List[TrackInfo]:
        """Filter audio tracks based on CLI selectors (language, etc.)."""
        if not selectors:
            return []

        # Find audio selectors
        audio_selectors = [s for s in selectors if s.type.value == "AUDIO"]
        if not audio_selectors:
            return []

        filtered = []
        for track in tracks:
            # language check (normalize eng -> en like subtitles do)
            for selector in audio_selectors:
                if selector.language:
                    track_lang = track.language
                    if track_lang == "eng":
                        track_lang = "en"
                    if track_lang != selector.language:
                        continue
                # other audio selector fields can be extended here
                filtered.append(track)
                break

        return filtered
    
    def _handle_dry_run(self, audio_tracks: List[TrackInfo], workdir: Path, video_artifact: Artifact) -> List[Artifact]:
        """Handle dry run execution.
        
        Args:
            audio_tracks: List of audio tracks to extract
            workdir: Working directory
            video_artifact: Source video artifact
            
        Returns:
            List with planned audio artifacts
        """
        planned_artifacts = []
        
        for track in audio_tracks:
            output_filename = f"audio_track_{track.index}.{self.audio_format}"
            output_path = workdir / output_filename
            
            # Create planned artifact (not actually created)
            planned_artifact = Artifact(
                type=ArtifactType.AUDIO,
                path=str(output_path),
                metadata={
                    "source_file": video_artifact.path,
                    "track": str(track.index),
                    "codec": track.codec,
                    "language": track.language or "und",
                    "format": self.audio_format,
                    "planned": True
                }
            )
            
            planned_artifacts.append(planned_artifact)
        
        return planned_artifacts