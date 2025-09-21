"""Tests for FFmpeg adapter."""
import pytest
from pathlib import Path
import tempfile
from unittest.mock import Mock, patch, MagicMock
from src.adapters.ffmpeg import FFmpegAdapter, FFmpegError, MediaInfo, TrackInfo
from src.models.artifacts import Artifact, ArtifactType
from src.models.common import MuteWindow


class TestFFmpegAdapter:
    """Test FFmpegAdapter."""
    
    def test_adapter_creation(self):
        """Test FFmpeg adapter creation."""
        adapter = FFmpegAdapter()
        assert adapter.ffmpeg_path == "ffmpeg"
    
    def test_adapter_custom_path(self):
        """Test FFmpeg adapter with custom path."""
        adapter = FFmpegAdapter(ffmpeg_path="/usr/local/bin/ffmpeg")
        assert adapter.ffmpeg_path == "/usr/local/bin/ffmpeg"
    
    @patch('subprocess.run')
    def test_probe_video_file(self, mock_run):
        """Test probing a video file."""
        # Mock ffprobe output
        mock_run.return_value = Mock(
            returncode=0,
            stdout='{"streams": [{"index": 0, "codec_type": "video", "codec_name": "h264"}, {"index": 1, "codec_type": "audio", "codec_name": "aac", "tags": {"language": "eng"}}], "format": {"format_name": "matroska,webm"}}'
        )
        
        adapter = FFmpegAdapter()
        
        with tempfile.NamedTemporaryFile(suffix=".mkv") as tmp:
            media_info = adapter.probe(tmp.name)
            
            assert media_info.format == "matroska,webm"
            assert len(media_info.tracks) == 2
            
            video_track = media_info.tracks[0]
            assert video_track.type == "video"
            assert video_track.codec == "h264"
            
            audio_track = media_info.tracks[1]
            assert audio_track.type == "audio"
            assert audio_track.codec == "aac"
            assert audio_track.language == "eng"
    
    @patch('subprocess.run')
    def test_probe_file_not_found(self, mock_run):
        """Test probing non-existent file."""
        mock_run.return_value = Mock(returncode=1, stderr="No such file")
        
        adapter = FFmpegAdapter()
        
        with pytest.raises(FFmpegError, match="Failed to probe"):
            adapter.probe("/nonexistent/file.mkv")
    
    @patch('subprocess.run')
    def test_extract_audio(self, mock_run):
        """Test extracting audio from video."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        adapter = FFmpegAdapter()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.mkv"
            output_path = Path(tmpdir) / "output.wav"
            
            # Create mock input file
            input_path.write_text("mock video")
            
            # Mock the output file creation by creating it when ffmpeg runs
            def mock_ffmpeg_run(*args, **kwargs):
                output_path.write_text("mock audio")
                return Mock(returncode=0, stdout="", stderr="")
            
            mock_run.side_effect = mock_ffmpeg_run
            
            result_path = adapter.extract_audio(str(input_path), str(output_path))
            
            assert result_path == str(output_path)
            # Verify ffmpeg was called with correct arguments
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "ffmpeg" in args[0]
            assert str(input_path) in args
            assert str(output_path) in args
    
    @patch('subprocess.run')
    def test_extract_audio_with_format(self, mock_run):
        """Test extracting audio with different formats."""
        adapter = FFmpegAdapter()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.mkv"
            output_path = Path(tmpdir) / "output.mp3"
            
            # Create mock input file
            input_path.write_text("mock video")
            
            # Mock the output file creation by creating it when ffmpeg runs
            def mock_ffmpeg_run(*args, **kwargs):
                output_path.write_text("mock audio")
                return Mock(returncode=0, stdout="", stderr="")
            
            mock_run.side_effect = mock_ffmpeg_run
            
            result_path = adapter.extract_audio(
                str(input_path), str(output_path), audio_format="mp3"
            )
            
            assert result_path == str(output_path)
            # Verify ffmpeg was called with MP3 codec
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert "ffmpeg" in args[0]
            assert "libmp3lame" in args  # MP3 codec
            assert str(input_path) in args
            assert str(output_path) in args
    
    @patch('subprocess.run')
    def test_extract_subtitles(self, mock_run):
        """Test extracting subtitles from video."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        adapter = FFmpegAdapter()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.mkv"
            output_path = Path(tmpdir) / "output.srt"
            
            input_path.write_text("mock video")
            
            # Mock the output file creation
            def mock_ffmpeg_run(*args, **kwargs):
                output_path.write_text("mock subtitles")
                return Mock(returncode=0, stdout="", stderr="")
            
            mock_run.side_effect = mock_ffmpeg_run
            
            result_path = adapter.extract_subtitles(str(input_path), str(output_path))
            
            assert result_path == str(output_path)
            mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_apply_mute_windows(self, mock_run):
        """Test applying mute windows to audio."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        adapter = FFmpegAdapter()
        
        mute_windows = [
            MuteWindow(start=10.0, end=15.0, reason="profanity", source="SUBTITLE"),
            MuteWindow(start=30.0, end=35.0, reason="profanity", source="SUBTITLE")
        ]
        
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.wav"
            output_path = Path(tmpdir) / "output.wav"
            
            input_path.write_text("mock audio")
            
            # Mock the output file creation
            def mock_ffmpeg_run(*args, **kwargs):
                output_path.write_text("mock audio processed")
                return Mock(returncode=0, stdout="", stderr="")
            
            mock_run.side_effect = mock_ffmpeg_run
            
            result_path = adapter.apply_mute_windows(
                str(input_path), 
                str(output_path), 
                mute_windows
            )
            
            assert result_path == str(output_path)
            mock_run.assert_called_once()
            
            # Check that volume filters were included
            args = mock_run.call_args[0][0]
            filter_arg = " ".join(args)
            assert "volume=enable" in filter_arg
    
    @patch('subprocess.run')
    def test_remux_media(self, mock_run):
        """Test remuxing video with new audio/subtitle tracks."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        
        adapter = FFmpegAdapter()
        
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = Path(tmpdir) / "video.mkv"
            audio_path = Path(tmpdir) / "audio.wav"
            subtitle_path = Path(tmpdir) / "subs.srt"
            output_path = Path(tmpdir) / "output.mkv"
            
            # Create mock files
            video_path.write_text("mock video")
            audio_path.write_text("mock audio")
            subtitle_path.write_text("mock subtitles")
            
            # Mock the output file creation
            def mock_ffmpeg_run(*args, **kwargs):
                output_path.write_text("mock remuxed video")
                return Mock(returncode=0, stdout="", stderr="")
            
            mock_run.side_effect = mock_ffmpeg_run
            
            result_path = adapter.remux(
                video_input=str(video_path),
                output=str(output_path),
                audio_tracks=[str(audio_path)],
                subtitle_tracks=[str(subtitle_path)]
            )
            
            assert result_path == str(output_path)
            mock_run.assert_called_once()
    
    @patch('subprocess.run')
    def test_ffmpeg_command_failure(self, mock_run):
        """Test handling FFmpeg command failure."""
        mock_run.return_value = Mock(
            returncode=1, 
            stdout="", 
            stderr="Error: Invalid format"
        )
        
        adapter = FFmpegAdapter()
        
        with pytest.raises(FFmpegError, match="FFmpeg command failed"):
            adapter.extract_audio("/fake/input.mkv", "/fake/output.wav")


class TestMediaInfo:
    """Test MediaInfo model."""
    
    def test_media_info_creation(self):
        """Test MediaInfo creation."""
        tracks = [
            TrackInfo(index=0, type="video", codec="h264"),
            TrackInfo(index=1, type="audio", codec="aac", language="en")
        ]
        
        info = MediaInfo(format="matroska", tracks=tracks)
        
        assert info.format == "matroska"
        assert len(info.tracks) == 2
    
    def test_get_audio_tracks(self):
        """Test getting audio tracks."""
        tracks = [
            TrackInfo(index=0, type="video", codec="h264"),
            TrackInfo(index=1, type="audio", codec="aac", language="en"),
            TrackInfo(index=2, type="audio", codec="ac3", language="es"),
            TrackInfo(index=3, type="subtitle", codec="subrip", language="en")
        ]
        
        info = MediaInfo(format="matroska", tracks=tracks)
        audio_tracks = info.get_audio_tracks()
        
        assert len(audio_tracks) == 2
        assert all(track.type == "audio" for track in audio_tracks)
    
    def test_get_subtitle_tracks(self):
        """Test getting subtitle tracks."""
        tracks = [
            TrackInfo(index=0, type="video", codec="h264"),
            TrackInfo(index=1, type="audio", codec="aac", language="en"),
            TrackInfo(index=2, type="subtitle", codec="subrip", language="en"),
            TrackInfo(index=3, type="subtitle", codec="subrip", language="es")
        ]
        
        info = MediaInfo(format="matroska", tracks=tracks)
        subtitle_tracks = info.get_subtitle_tracks()
        
        assert len(subtitle_tracks) == 2
        assert all(track.type == "subtitle" for track in subtitle_tracks)


class TestTrackInfo:
    """Test TrackInfo model."""
    
    def test_track_info_creation(self):
        """Test TrackInfo creation."""
        track = TrackInfo(
            index=1,
            type="audio",
            codec="aac",
            language="en",
            title="English Audio"
        )
        
        assert track.index == 1
        assert track.type == "audio"
        assert track.codec == "aac"
        assert track.language == "en"
        assert track.title == "English Audio"