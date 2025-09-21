"""FFmpeg adapter for media processing.

Provides FFmpeg integration for:
- Probing media files for track information
- Extracting audio and subtitle tracks
- Applying mute windows to audio
- Remuxing media files with new tracks
"""
import json
import subprocess
import time
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class FFmpegError(Exception):
    """Exception raised for FFmpeg-related errors."""
    pass


class TrackInfo(BaseModel):
    """Information about a media track."""
    index: int = Field(..., description="Track index")
    type: str = Field(..., description="Track type (video, audio, subtitle)")
    codec: str = Field(..., description="Codec name")
    language: Optional[str] = Field(None, description="Language code")
    title: Optional[str] = Field(None, description="Track title")


class MediaInfo(BaseModel):
    """Media file information from FFprobe."""
    format: str = Field(..., description="Container format")
    tracks: List[TrackInfo] = Field(default_factory=list, description="Media tracks")
    
    def get_audio_tracks(self) -> List[TrackInfo]:
        """Get all audio tracks."""
        return [track for track in self.tracks if track.type == "audio"]
    
    def get_subtitle_tracks(self) -> List[TrackInfo]:
        """Get all subtitle tracks."""
        return [track for track in self.tracks if track.type == "subtitle"]


class FFmpegAdapter:
    """FFmpeg adapter for media operations."""
    
    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        """Initialize FFmpeg adapter.
        
        Args:
            ffmpeg_path: Path to ffmpeg executable
            ffprobe_path: Path to ffprobe executable
        """
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self._execution_logger = None  # Will be set by operations if available
    def set_execution_logger(self, execution_logger, log_entry):
        """Set execution logger for enhanced error handling.
        
        Args:
            execution_logger: ExecutionLogger instance
            log_entry: Current operation log entry
        """
        self._execution_logger = execution_logger
        self._log_entry = log_entry
    
    def probe(self, input_path: str) -> MediaInfo:
        """Probe media file for track information.
        
        Args:
            input_path: Path to input media file
            
        Returns:
            MediaInfo with track details
            
        Raises:
            FFmpegError: If probing fails
        """
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            input_path
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            if result.returncode != 0:
                raise FFmpegError(f"Failed to probe {input_path}: {result.stderr}")
            
            data = json.loads(result.stdout)
            
            # Extract format info
            format_name = data.get("format", {}).get("format_name", "unknown")
            
            # Extract track info
            tracks = []
            for stream in data.get("streams", []):
                track = TrackInfo(
                    index=stream.get("index", 0),
                    type=stream.get("codec_type", "unknown"),
                    codec=stream.get("codec_name", "unknown"),
                    language=stream.get("tags", {}).get("language"),
                    title=stream.get("tags", {}).get("title")
                )
                tracks.append(track)
            
            return MediaInfo(format=format_name, tracks=tracks)
            
        except json.JSONDecodeError as e:
            raise FFmpegError(f"Failed to parse ffprobe output: {e}")
        except subprocess.SubprocessError as e:
            raise FFmpegError(f"FFprobe command failed: {e}")
    
    def extract_audio(self, input_path: str, output_path: str, track_index: int = 0, audio_format: str = "wav") -> str:
        """Extract audio track from media file.
        
        Args:
            input_path: Path to input media file
            output_path: Path for output audio file
            track_index: Audio track index to extract
            audio_format: Output audio format (wav, mp3, flac, etc.)
            
        Returns:
            Path to extracted audio file
            
        Raises:
            FFmpegError: If extraction fails
        """
        # Audio codec mapping
        codec_map = {
            "wav": "pcm_s16le",
            "mp3": "libmp3lame",
            "flac": "flac",
            "m4a": "aac",
            "aac": "aac"
        }
        
        codec = codec_map.get(audio_format.lower(), "pcm_s16le")
        
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-map", f"0:a:{track_index}",
            "-acodec", codec,
            "-ac", "2",  # Stereo
            "-ar", "48000",  # 48kHz sample rate
            "-y",  # Overwrite output
            output_path
        ]
        
        return self._run_ffmpeg_command(cmd, output_path)
    
    def extract_subtitles(self, input_path: str, output_path: str, track_index: int = 0) -> str:
        """Extract subtitle track from media file.
        
        Args:
            input_path: Path to input media file
            output_path: Path for output subtitle file
            track_index: Subtitle track index to extract
            
        Returns:
            Path to extracted subtitle file
            
        Raises:
            FFmpegError: If extraction fails
        """
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-map", f"0:s:{track_index}",
            "-c:s", "srt",  # Convert to SRT format
            "-y",  # Overwrite output
            output_path
        ]
        
        return self._run_ffmpeg_command(cmd, output_path)
    
    def apply_mute_windows(self, input_path: str, output_path: str, mute_windows: List) -> str:
        """Apply mute windows to audio file.
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output audio file
            mute_windows: List of MuteWindow objects
            
        Returns:
            Path to processed audio file
            
        Raises:
            FFmpegError: If processing fails
        """
        if not mute_windows:
            # No mute windows, just copy the file
            cmd = [
                self.ffmpeg_path,
                "-i", input_path,
                "-c", "copy",
                "-y",
                output_path
            ]
        else:
            # Build volume filter for mute windows
            volume_filters = []
            for window in mute_windows:
                # Volume filter: volume=enable='between(t,start,end)':volume=0
                filter_expr = f"volume=enable='between(t,{window.start},{window.end})':volume=0"
                volume_filters.append(filter_expr)
            
            # Combine filters
            filter_string = ",".join(volume_filters)
            
            cmd = [
                self.ffmpeg_path,
                "-i", input_path,
                "-af", filter_string,
                "-y",
                output_path
            ]
        
        return self._run_ffmpeg_command(cmd, output_path)
    
    def remux(self, video_input: str, output: str, 
              audio_tracks: Optional[List[str]] = None,
              subtitle_tracks: Optional[List[str]] = None) -> str:
        """Remux video with new audio and subtitle tracks.
        
        Args:
            video_input: Path to input video file
            output: Path for output file
            audio_tracks: List of audio file paths to include
            subtitle_tracks: List of subtitle file paths to include
            
        Returns:
            Path to remuxed file
            
        Raises:
            FFmpegError: If remuxing fails
        """
        cmd = [self.ffmpeg_path, "-i", video_input]
        
        # Add audio inputs
        if audio_tracks:
            for audio_path in audio_tracks:
                cmd.extend(["-i", audio_path])
        
        # Add subtitle inputs
        if subtitle_tracks:
            for sub_path in subtitle_tracks:
                cmd.extend(["-i", sub_path])
        
        # Map video from first input
        cmd.extend(["-map", "0:v"])
        
        # Map audio tracks
        input_index = 1
        if audio_tracks:
            for i in range(len(audio_tracks)):
                cmd.extend(["-map", f"{input_index}:a"])
                input_index += 1
        else:
            # Keep original audio if no new audio tracks
            cmd.extend(["-map", "0:a"])
        
        # Map subtitle tracks
        if subtitle_tracks:
            for i in range(len(subtitle_tracks)):
                cmd.extend(["-map", f"{input_index}:s"])
                input_index += 1
        
        # Copy codecs to avoid re-encoding
        cmd.extend(["-c", "copy"])
        cmd.extend(["-y", output])
        
        return self._run_ffmpeg_command(cmd, output)
    
    def _run_ffmpeg_command(self, cmd: List[str], expected_output: str) -> str:
        """Run FFmpeg command and handle errors.
        
        Args:
            cmd: FFmpeg command arguments
            expected_output: Expected output file path
            
        Returns:
            Path to output file
            
        Raises:
            FFmpegError: If command fails
        """
        start_time = time.time()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Log external command execution if logger is available
            if self._execution_logger and hasattr(self, '_log_entry'):
                self._execution_logger.log_external_command(
                    self._log_entry,
                    cmd,
                    result.returncode,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    duration_ms=duration_ms
                )
            
            if result.returncode != 0:
                # Preserve any partially created artifacts
                if Path(expected_output).exists():
                    if self._execution_logger and hasattr(self, '_log_entry'):
                        self._execution_logger.add_operation_log(
                            self._log_entry,
                            f"Partial artifact preserved at: {expected_output}"
                        )
                
                error_msg = f"FFmpeg command failed (exit code {result.returncode})"
                if result.stderr:
                    error_msg += f": {result.stderr}"
                
                raise FFmpegError(error_msg)
            
            # Verify output file was created
            if not Path(expected_output).exists():
                raise FFmpegError(f"Expected output file not created: {expected_output}")
            
            # Log successful creation
            if self._execution_logger and hasattr(self, '_log_entry'):
                file_size = Path(expected_output).stat().st_size
                self._execution_logger.add_operation_log(
                    self._log_entry,
                    f"Created output file: {expected_output} ({file_size} bytes)"
                )
            
            return expected_output
            
        except subprocess.SubprocessError as e:
            error_msg = f"Failed to run FFmpeg command: {e}"
            
            # Log the subprocess error if logger is available
            if self._execution_logger and hasattr(self, '_log_entry'):
                self._execution_logger.add_operation_log(self._log_entry, error_msg)
            
            raise FFmpegError(error_msg)