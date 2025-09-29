"""Audio quality check operation using energy analysis.

Audio quality check operation for verifying mute effectiveness.

Analyzes muted audio to ensure profanity windows have sufficiently low energy
compared to control segments, similar to subtitle QC for residual profanities.
"""
import json
import wave
from pathlib import Path
from typing import List, Dict, Any, Set
from typing import List, Dict, Any, Optional, Tuple

from src.utils import audio_utils

from src.models.artifacts import Artifact, ArtifactType
from src.models.common import MuteWindow
from src.models.operations import Operation, OperationFlags


class AudioQualityCheckOperation(Operation):
    """Operation to verify audio muting effectiveness through energy analysis."""
    
    def __init__(self, energy_threshold_db: float = -20.0, control_window_duration: float = 1.0):
        """Initialize the audio QC operation.
        
        Args:
            energy_threshold_db: Minimum dB reduction required in muted windows
            control_window_duration: Duration of control segments for comparison (seconds)
        """
        super().__init__("audio_quality_check")
        self.description = "Verify audio muting effectiveness through energy analysis"
        self.energy_threshold_db = energy_threshold_db
        self.control_window_duration = control_window_duration
    
    @property
    def consumes(self) -> Set[ArtifactType]:
        """Return the artifact types this operation consumes."""
        return {ArtifactType.AUDIO}
    
    @property
    def produces(self) -> Set[ArtifactType]:
        """Return the artifact types this operation produces."""
        return {ArtifactType.AUDIO}  # Pass-through with QC metadata
    
    def run(self, inputs: List[Artifact], workdir: Path, flags: OperationFlags) -> List[Artifact]:
        """Execute the audio quality check.
        
        Args:
            inputs: List of input artifacts (muted audio)
            workdir: Working directory for QC reports
            flags: Execution flags
            
        Returns:
            List of audio artifacts with QC metadata
        """
        from datetime import datetime
        
        try:
            # Find audio artifacts
            audio_artifacts = [
                artifact for artifact in inputs
                if artifact.type == ArtifactType.AUDIO
            ]
            
            if not audio_artifacts:
                if flags.verbose:
                    print("[audio_qc] No audio artifacts found - skipping QC")
                return []
            
            results = []
            
            if flags.dry_run:
                if flags.verbose:
                    print("[audio_qc] Dry run - skipping audio energy analysis")
                for audio_artifact in audio_artifacts:
                    # Return artifact with dry run QC metadata
                    output_artifact = Artifact(
                        type=audio_artifact.type,
                        path=audio_artifact.path,
                        metadata={
                            **audio_artifact.metadata,
                            "quality_check": {
                                "operation": "audio_quality_check",
                                "status": "SKIPPED",
                                "reason": "Dry run mode",
                                "timestamp": datetime.now().isoformat()
                            }
                        }
                    )
                    results.append(output_artifact)
                return results

            for audio_artifact in audio_artifacts:
                if flags.verbose:
                    print(f"[audio_qc] Running energy analysis on: {audio_artifact.path}")
                
                # Run energy analysis
                qc_results = self._analyze_audio_energy(audio_artifact, workdir, flags)
                
                # Handle QC results
                if qc_results["failed_windows"] > 0:
                    if not getattr(flags, 'continue_on_audio_qc_fail', False):
                        # Fail the pipeline by default
                        qc_report_path = qc_results["report_path"]
                        raise RuntimeError(
                            f"Audio QC failed: {qc_results['failed_windows']} windows have insufficient muting. "
                            f"See QC report at {qc_report_path}. Use --continue-on-audio-qc-fail to proceed despite failures."
                        )
                    else:
                        # Log warning but continue
                        if flags.verbose:
                            print(f"[audio_qc] Warning: {qc_results['failed_windows']} windows failed QC, but continuing due to --continue-on-audio-qc-fail flag")
                
                # Create result artifact with QC metadata
                result_metadata = audio_artifact.metadata.copy()
                result_metadata["quality_check"] = qc_results
                
                result_artifact = Artifact(
                    type=ArtifactType.AUDIO,
                    path=audio_artifact.path,  # Pass-through
                    metadata=result_metadata
                )
                
                results.append(result_artifact)
            
            return results
            
        except Exception as e:
            if flags.verbose:
                print(f"[audio_qc] Error during audio quality check: {e}")
            raise
    
    def _analyze_audio_energy(self, audio_artifact: Artifact, workdir: Path, flags: OperationFlags) -> Dict[str, Any]:
        """Analyze energy levels in muted windows vs control segments.
        
        Args:
            audio_artifact: Audio artifact to analyze
            workdir: Working directory for reports
            flags: Execution flags
            
        Returns:
            QC results dictionary
        """
        from datetime import datetime
        
        audio_path = Path(audio_artifact.path)
        if not audio_path.exists():
            # Return SKIPPED status for missing files
            return {
                "operation": "audio_quality_check",
                "status": "SKIPPED",
                "reason": f"Audio file not found: {audio_path}",
                "timestamp": datetime.now().isoformat(),
                "failed_windows": 0
            }
        
        # Extract mute windows from metadata
        mute_windows = self._extract_mute_windows(audio_artifact)
        
        if not mute_windows:
            if flags.verbose:
                print("[audio_qc] No mute windows found - QC skipped")
            return {
                "operation": "audio_quality_check",
                "status": "SKIPPED", 
                "reason": "No mute windows file found",
                "timestamp": datetime.now().isoformat(),
                "failed_windows": 0
            }
        
        # Analyze audio file
        try:
            with wave.open(str(audio_path), 'rb') as wf:
                rate = wf.getframerate()
                width = wf.getsampwidth()
                nchannels = wf.getnchannels()
                duration = wf.getnframes() / rate
                
                if flags.verbose:
                    print(f"[audio_qc] Audio: {rate}Hz, {width}B, {nchannels}ch, {duration:.1f}s")
                
                # Analyze each mute window
                failed_windows = []
                window_results = []
                
                for i, window in enumerate(mute_windows):
                    if window.end > duration:
                        if flags.verbose:
                            print(f"[audio_qc] Window {i} extends beyond audio duration, skipping")
                        continue
                    
                    # Get RMS for muted window
                    muted_rms = self._get_rms(wf, window.start, window.end, width, nchannels)
                    
                    # Get RMS for control segment (after the window)
                    control_start = min(window.end + 0.5, duration - self.control_window_duration)
                    control_end = min(control_start + self.control_window_duration, duration)
                    
                    if control_end <= control_start:
                        # No space for control segment, use before the window
                        control_end = max(window.start - 0.5, 0)
                        control_start = max(control_end - self.control_window_duration, 0)
                    
                    if control_end <= control_start:
                        if flags.verbose:
                            print(f"[audio_qc] Cannot find control segment for window {i}, skipping")
                        continue
                    
                    control_rms = self._get_rms(wf, control_start, control_end, width, nchannels)
                    
                    # Calculate dB reduction
                    if control_rms > 0 and muted_rms > 0:
                        import math
                        db_reduction = 20 * math.log10(muted_rms / control_rms)
                    elif muted_rms == 0:
                        db_reduction = -60.0  # Assume perfect silence
                    else:
                        db_reduction = 0.0  # No reduction
                    
                    window_result = {
                        "window_index": i,
                        "start": window.start,
                        "end": window.end,
                        "muted_rms": muted_rms,
                        "control_rms": control_rms,
                        "db_reduction": db_reduction,
                        "passed": db_reduction <= self.energy_threshold_db  # More negative means better muting
                    }
                    
                    window_results.append(window_result)
                    
                    if not window_result["passed"]:
                        failed_windows.append(window_result)
                        if flags.verbose:
                            print(f"[audio_qc] Window {i} FAILED: {db_reduction:.1f}dB reduction (need ≤{self.energy_threshold_db}dB)")
                    elif flags.verbose:
                        print(f"[audio_qc] Window {i} passed: {db_reduction:.1f}dB reduction")
                
                # Generate QC report
                qc_report = {
                    "audio_file": str(audio_path),
                    "total_windows": len(window_results),
                    "failed_windows": len(failed_windows),
                    "passed_windows": len(window_results) - len(failed_windows),
                    "energy_threshold_db": self.energy_threshold_db,
                    "window_results": window_results,
                    "failed_details": failed_windows
                }
                
                # Write QC report
                qc_report_path = workdir / "audio_qc_report.json"
                qc_report_path.write_text(json.dumps(qc_report, indent=2), encoding='utf-8')
                
                if flags.verbose:
                    if failed_windows:
                        print(f"[audio_qc] QC FAILED: {len(failed_windows)}/{len(window_results)} windows insufficient muting")
                    else:
                        print(f"[audio_qc] QC PASSED: All {len(window_results)} windows properly muted")
                    print(f"[audio_qc] Report written to: {qc_report_path}")
                
                return {
                    "operation": "audio_quality_check",
                    "status": "PASS" if len(failed_windows) == 0 else "FAIL",
                    "failed_windows": len(failed_windows),
                    "total_windows": len(window_results),
                    "report_path": str(qc_report_path),
                    "energy_threshold_db": self.energy_threshold_db,
                    "energy_analysis": {
                        "muted_segments_analyzed": len(window_results),
                        "control_segments_analyzed": len(window_results),
                        "average_db_reduction": sum(r["db_reduction"] for r in window_results) / len(window_results) if window_results else 0,
                        "failed_windows": len(failed_windows)
                    },
                    "timestamp": datetime.now().isoformat()
                }
                
        except Exception as e:
            raise RuntimeError(f"Failed to analyze audio energy: {e}")
    
    def _extract_mute_windows(self, audio_artifact: Artifact) -> List[MuteWindow]:
        """Extract mute windows from audio artifact metadata."""
        import json
        
        windows = []
        
        # Look for mute windows in metadata
        if "mute_windows" in audio_artifact.metadata:
            window_data = audio_artifact.metadata["mute_windows"]
            if isinstance(window_data, list):
                for item in window_data:
                    if isinstance(item, dict):
                        try:
                            windows.append(MuteWindow(**item))
                        except Exception:
                            continue
        
        # Also check for mute windows file 
        elif "mute_windows_file" in audio_artifact.metadata:
            mute_file_path = Path(audio_artifact.metadata["mute_windows_file"])
            if mute_file_path.exists():
                try:
                    with open(mute_file_path, 'r') as f:
                        window_data = json.load(f)
                    if isinstance(window_data, list):
                        for item in window_data:
                            if isinstance(item, dict):
                                try:
                                    windows.append(MuteWindow(**item))
                                except Exception:
                                    continue
                except Exception as e:
                    if hasattr(self, '_verbose') and self._verbose:
                        print(f"[audio_qc] Warning: Failed to load mute windows from {mute_file_path}: {e}")
        
        # Also check for windows applied count as a hint
        windows_applied = audio_artifact.metadata.get("mute_windows_applied", 0)
        if windows_applied > 0 and not windows:
            # We know windows were applied but don't have the details
            # This is a limitation - we'd need the mute operation to preserve window details
            if hasattr(self, '_verbose') and self._verbose:
                print(f"[audio_qc] Warning: {windows_applied} windows were applied but details not available in metadata")
        
        return windows
    
    def _get_rms(self, wf: wave.Wave_read, start: float, end: float, width: int, nchannels: int) -> int:
        """Get RMS energy for a time segment."""
        rate = wf.getframerate()
        start_frame = max(0, int(start * rate))
        end_frame = max(start_frame, int(end * rate))
        frame_count = end_frame - start_frame
        
        if frame_count <= 0:
            return 0
        
        wf.setpos(start_frame)
        data = wf.readframes(frame_count)
        
        if not data:
            return 0
        
        # Convert to mono if stereo
        if nchannels == 2:
            data = audio_utils.tomono(data, width, 0.5, 0.5)
        
        return audio_utils.rms(data, width)