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
import threading
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from src.utils.time_logging import tprint


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
    forced: Optional[bool] = Field(None, description="Forced flag (subtitle disposition)")
    channels: Optional[int] = Field(None, description="Number of audio channels")
    sample_rate: Optional[str] = Field(None, description="Audio sample rate")
    bitrate: Optional[str] = Field(None, description="Audio bit rate in bits per second (string from ffprobe)")


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
                # Get disposition info for forced flag
                disposition = stream.get("disposition", {})
                forced = disposition.get("forced", 0) == 1 if disposition else None
                
                track = TrackInfo(
                    index=stream.get("index", 0),
                    type=stream.get("codec_type", "unknown"),
                    codec=stream.get("codec_name", "unknown"),
                    language=stream.get("tags", {}).get("language"),
                    title=stream.get("tags", {}).get("title"),
                    forced=forced,
                    channels=stream.get("channels") if stream.get("codec_type") == "audio" else None,
                    sample_rate=stream.get("sample_rate") if stream.get("codec_type") == "audio" else None,
                    bitrate=stream.get("bit_rate") if stream.get("codec_type") == "audio" else None
                )
                tracks.append(track)
            
            return MediaInfo(format=format_name, tracks=tracks)
            
        except json.JSONDecodeError as e:
            raise FFmpegError(f"Failed to parse ffprobe output: {e}")
        except subprocess.SubprocessError as e:
            raise FFmpegError(f"FFprobe command failed: {e}")
    
    def extract_audio(self, input_path: str, output_path: str, track_index: int = 0, audio_format: str = "wav", channels: Optional[int] = None) -> str:
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
        ]
        # Preserve original channel layout if channels is None; otherwise enforce
        if channels is not None:
            cmd.extend(["-ac", str(channels)])
        # Keep 48kHz sample rate for consistency
        cmd.extend(["-ar", "48000"])
        cmd.extend(["-y", output_path])
        
        # Use heartbeat for audio extraction (can be slow for large files)
        heartbeat_context = f"extracting audio track {track_index} to {audio_format}"
        return self._run_ffmpeg_command(cmd, output_path, heartbeat_interval=8.0, heartbeat_context=heartbeat_context)
    
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
        
        # Use heartbeat for subtitle extraction (usually quick, but good for large files)
        heartbeat_context = f"extracting subtitle track {track_index}"
        return self._run_ffmpeg_command(cmd, output_path, heartbeat_interval=12.0, heartbeat_context=heartbeat_context)
    
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
            # Build single volume filter with multiple enable conditions
            # Using a single filter prevents interference between overlapping windows
            enable_conditions = []
            for window in mute_windows:
                # Add condition for this window: between(t,start,end)
                enable_conditions.append(f"between(t,{window.start},{window.end})")
            
            # Combine all conditions with OR logic: enable='cond1+cond2+...'
            combined_enable = "+".join(enable_conditions)
            filter_string = f"volume=enable='{combined_enable}':volume=0"
            
            cmd = [
                self.ffmpeg_path,
                "-i", input_path,
                "-af", filter_string,
                "-y",
                output_path
            ]
        
        return self._run_ffmpeg_command(cmd, output_path)
    
    def verify_audio_parity(self, original_audio_path: str, remuxed_video_path: str, track_index: int = 0) -> Dict[str, Any]:
        """Verify audio track parity between original and remuxed files.
        
        Args:
            original_audio_path: Path to original audio file
            remuxed_video_path: Path to remuxed video file
            track_index: Audio track index in remuxed file to verify
            
        Returns:
            Dictionary with parity check results
        """
        try:
            # Probe original audio
            original_info = self.probe(original_audio_path)
            original_tracks = original_info.get_audio_tracks()
            if not original_tracks:
                return {"status": "error", "message": "No audio tracks found in original file"}
            
            original_track = original_tracks[0]  # Use first track from extracted audio
            
            # Probe remuxed video
            remuxed_info = self.probe(remuxed_video_path)
            remuxed_tracks = remuxed_info.get_audio_tracks()
            if len(remuxed_tracks) <= track_index:
                return {"status": "error", "message": f"Track index {track_index} not found in remuxed file"}
            
            remuxed_track = remuxed_tracks[track_index]
            
            # Compare codec, channels, sample rate
            mismatches = []
            if original_track.codec != remuxed_track.codec:
                mismatches.append(f"codec: {original_track.codec} != {remuxed_track.codec}")
            if original_track.channels != remuxed_track.channels:
                mismatches.append(f"channels: {original_track.channels} != {remuxed_track.channels}")
            if original_track.sample_rate != remuxed_track.sample_rate:
                mismatches.append(f"sample_rate: {original_track.sample_rate} != {remuxed_track.sample_rate}")
            
            if mismatches:
                return {
                    "status": "mismatch", 
                    "mismatches": mismatches,
                    "original": {"codec": original_track.codec, "channels": original_track.channels, "sample_rate": original_track.sample_rate},
                    "remuxed": {"codec": remuxed_track.codec, "channels": remuxed_track.channels, "sample_rate": remuxed_track.sample_rate}
                }
            else:
                return {"status": "match", "message": "Audio parity verified"}
                
        except Exception as e:
            return {"status": "error", "message": f"Parity check failed: {e}"}

    def remux(self, video_input: str, output: str, 
              audio_tracks: Optional[List[str]] = None,
              subtitle_tracks: Optional[List[str]] = None,
              audio_encode: Optional[Dict[str, Any]] = None) -> str:
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
        else:
            # Keep original subtitle streams if no new subtitles are being embedded
            cmd.extend(["-map", "0:s?"])
        
        # Codec strategy
        if audio_encode:
            # Copy video, encode audio to requested codec/bitrate/channels
            cmd.extend(["-c:v", "copy"])
            # Apply per-stream audio settings
            target_codec = audio_encode.get("codec", "eac3")
            bitrate = audio_encode.get("bitrate")
            channels = audio_encode.get("channels")
            sample_rate = audio_encode.get("sample_rate")
            # If we added N audio inputs, map them in order and set -c:a accordingly
            cmd.extend(["-c:a", target_codec])
            if bitrate:
                cmd.extend(["-b:a", str(bitrate)])
            if channels:
                cmd.extend(["-ac", str(channels)])
            if sample_rate:
                cmd.extend(["-ar", str(sample_rate)])
        else:
            # Copy everything to avoid re-encoding
            cmd.extend(["-c", "copy"])
        cmd.extend(["-y", output])
        
        # Use heartbeat for remuxing (can be slow for large files with multiple tracks)
        track_count = len(audio_tracks or []) + len(subtitle_tracks or []) + 1  # +1 for video
        heartbeat_context = f"remuxing {track_count} tracks"
        return self._run_ffmpeg_command(cmd, output, heartbeat_interval=6.0, heartbeat_context=heartbeat_context)
    
    def _run_ffmpeg_command(self, cmd: List[str], expected_output: str, heartbeat_interval: float = 10.0, heartbeat_context: Optional[str] = None) -> str:
        """Run FFmpeg command and handle errors with periodic heartbeat logging.
        
        Args:
            cmd: FFmpeg command arguments
            expected_output: Expected output file path
            heartbeat_interval: Seconds between heartbeat messages (0 to disable)
            
        Returns:
            Path to output file
            
        Raises:
            FFmpegError: If command fails
        """
        start_time = time.time()
        
        try:
            # For long-running operations, use Popen with heartbeat monitoring
            # Detect operations that might be slow: filters, remuxing, audio/video processing
            is_long_operation = (
                heartbeat_interval > 0 and (
                    any(flag in ' '.join(cmd) for flag in ['-af', '-vf', 'volume=', '-acodec', '-map']) or
                    heartbeat_context is not None  # Explicit heartbeat request
                )
            )
            
            if is_long_operation:
                result = self._run_with_heartbeat(cmd, heartbeat_interval, start_time, heartbeat_context)
            else:
                # Standard run for quick operations
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
    
    def _run_with_heartbeat(self, cmd: List[str], heartbeat_interval: float, start_time: float, heartbeat_context: Optional[str] = None):
        """Run FFmpeg with periodic heartbeat logging for long operations.
        
        Args:
            cmd: FFmpeg command arguments
            heartbeat_interval: Seconds between heartbeat messages
            start_time: Start time for duration calculation
            heartbeat_context: Optional context description for heartbeat messages
            
        Returns:
            CompletedProcess-like object with returncode, stdout, stderr
        """
        class HeartbeatResult:
            def __init__(self):
                self.returncode = None
                self.stdout = ""
                self.stderr = ""
        
        result = HeartbeatResult()
        
        # Start the process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Heartbeat monitoring thread
        def heartbeat_monitor():
            last_heartbeat = time.time()
            while process.poll() is None:  # Process still running
                current_time = time.time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    elapsed = current_time - start_time
                    context_msg = f" ({heartbeat_context})" if heartbeat_context else ""
                    tprint(f"FFmpeg still running... {elapsed:.1f}s elapsed{context_msg} (cmd: {cmd[0]} {cmd[1] if len(cmd) > 1 else ''})", prefix="ffmpeg")
                    last_heartbeat = current_time
                time.sleep(1.0)  # Check every second
        
        # Start heartbeat thread
        heartbeat_thread = threading.Thread(target=heartbeat_monitor, daemon=True)
        heartbeat_thread.start()
        
        try:
            # Wait for process completion and capture output
            stdout, stderr = process.communicate()
            result.returncode = process.returncode
            result.stdout = stdout
            result.stderr = stderr
            
            # Log completion
            elapsed = time.time() - start_time
            if elapsed > heartbeat_interval:  # Only log if it was actually a long operation
                tprint(f"FFmpeg completed after {elapsed:.1f}s", prefix="ffmpeg")
            
            return result
            
        except Exception as e:
            # Ensure process is terminated
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5.0)
                except subprocess.TimeoutExpired:
                    process.kill()
            raise FFmpegError(f"FFmpeg execution failed: {e}")
        
        finally:
            # Ensure heartbeat thread completes
            if heartbeat_thread.is_alive():
                heartbeat_thread.join(timeout=1.0)