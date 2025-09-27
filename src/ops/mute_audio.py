"""Audio muting operation for applying mute windows to audio tracks."""
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set

from src.adapters.ffmpeg import FFmpegAdapter
from src.error_handling import ExternalToolRunner
from src.models.artifacts import Artifact, ArtifactType
from src.models.common import MuteWindow
from src.models.operations import Operation, OperationFlags
from src.utils.subtitle_parser import SubtitleParser, SubtitleEntry
from src.utils.fuzzy_matcher import FuzzyMatcher
from src.utils.time_logging import tprint


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
    def consumes(self) -> Set[ArtifactType]:
        """Return the artifact types this operation consumes.
        
        Returns:
            Set containing AUDIO (required), and SUBTITLE/VIDEO for deriving windows
        """
        # Consume audio (to process), subtitles (to derive profanity windows), and video (to honor --mute-windows)
        return {ArtifactType.AUDIO, ArtifactType.SUBTITLE, ArtifactType.VIDEO}
    
    @property
    def produces(self) -> Set[ArtifactType]:
        """Return the artifact types this operation produces.
        
        Returns:
            Set containing AUDIO artifact type
        """
        return {ArtifactType.AUDIO}
    
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
            # Partition inputs by type
            audio_artifacts = [a for a in inputs if a.type == ArtifactType.AUDIO]
            subtitle_artifacts = [a for a in inputs if a.type == ArtifactType.SUBTITLE]
            video_artifacts = [a for a in inputs if a.type == ArtifactType.VIDEO]
            
            if not audio_artifacts:
                raise ValueError("No audio artifacts found for mute processing")
            
            # Set up error handling
            tool_runner = ExternalToolRunner(
                execution_logger=getattr(self, '_execution_logger', None),
                log_entry=getattr(self, '_log_entry', None)
            )
            
            results = []
            
            tprint(f"Begin processing {len(audio_artifacts)} audio artifact(s)", prefix="mute_audio")
            for idx, audio_artifact in enumerate(audio_artifacts, start=1):
                tprint(f"Audio {idx}/{len(audio_artifacts)}: collecting mute windows", prefix="mute_audio")
                # Collect mute windows from various sources
                external_file: Optional[str] = None
                if video_artifacts and "mute_windows_file" in video_artifacts[0].metadata:
                    external_file = video_artifacts[0].metadata.get("mute_windows_file")
                mute_windows = self._collect_mute_windows(
                    audio_artifact,
                    subtitle_artifacts=subtitle_artifacts,
                    external_file=external_file,
                    flags=flags,
                )
                # Maintain backward-compatible phrase for tests while adding richer context
                # New structured log
                tprint(f"Derived {len(mute_windows)} merged mute windows", prefix="mute_audio")
                # Legacy verbose line for backward compatibility with existing tests
                if flags.verbose:
                    print(f"Found {len(mute_windows)} mute windows for {audio_artifact.path}")

                # Persist mute windows to a sidecar JSON so downstream ops (QC) can consume them
                try:
                    windows_path = Path(workdir) / "mute_windows.json"
                    # Serialize MuteWindow models to plain dicts
                    windows_payload = [
                        {
                            "start": w.start,
                            "end": w.end,
                            "reason": w.reason,
                            "source": w.source,
                        }
                        for w in mute_windows
                    ]
                    windows_path.write_text(json.dumps(windows_payload, indent=2), encoding="utf-8")
                    tprint(f"Wrote mute windows sidecar: {windows_path}", prefix="mute_audio")
                except Exception as e:
                    tprint(f"Warning: failed to write mute windows sidecar: {e}", prefix="mute_audio")
                
                # Generate output path
                output_path = self._generate_output_path(audio_artifact.path, workdir)
                
                if not flags.dry_run:
                    tprint(f"Applying {len(mute_windows)} mute windows via ffmpeg to {audio_artifact.path}", prefix="mute_audio")
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
                        tprint(f"ffmpeg apply_mute_windows failed after {mute_result.duration_ms:.1f}ms: {mute_result.error}", prefix="mute_audio")
                    else:
                        tprint(f"ffmpeg apply_mute_windows succeeded in {mute_result.duration_ms:.1f}ms -> {mute_result.result}", prefix="mute_audio")
                    
                    if not mute_result.success:
                        raise RuntimeError(f"Failed to apply mute windows to {audio_artifact.path}: {mute_result.error}")
                    
                    processed_path = mute_result.result
                else:
                    processed_path = output_path
                
                # Create result artifact
                result_metadata = audio_artifact.metadata.copy()
                result_metadata["mute_windows_applied"] = len(mute_windows)
                result_metadata["original_path"] = audio_artifact.path
                # Reference the sidecar windows file for QC
                try:
                    result_metadata["mute_windows_file"] = str(windows_path)
                except Exception:
                    pass
                
                if not flags.dry_run and hasattr(mute_result, 'duration_ms'):
                    result_metadata["processing_duration_ms"] = mute_result.duration_ms
                
                result_artifact = Artifact(
                    type=ArtifactType.AUDIO,
                    path=processed_path,
                    metadata=result_metadata
                )
                tprint(f"Completed audio {idx}/{len(audio_artifacts)} -> {processed_path}", prefix="mute_audio")
                results.append(result_artifact)
            
            tprint("All audio artifacts processed", prefix="mute_audio")
            return results
            
        except Exception as e:
            tprint(f"Error in mute_audio operation: {e}", prefix="mute_audio")
            raise
    
    def _collect_mute_windows(self, artifact: Artifact, subtitle_artifacts: List[Artifact], external_file: Optional[str], flags: OperationFlags) -> List[MuteWindow]:
        """Collect mute windows from all available sources.
        
        Args:
            artifact: Audio artifact to process
            subtitle_artifacts: Subtitle artifacts to derive profanity windows from
            external_file: Optional path to external mute windows JSON file (via CLI)
            flags: Operation flags (for verbosity and profanity list path)
            
        Returns:
            List of MuteWindow objects from all sources
        """
        mute_windows: List[MuteWindow] = []
        
        # 1) Collect from artifact metadata (e.g., if carried through earlier steps)
        if "mute_windows" in artifact.metadata:
            metadata_windows = self._parse_mute_windows_from_metadata(
                artifact.metadata["mute_windows"]
            )
            mute_windows.extend(metadata_windows)
        
        # 2a) Collect from external file (CLI --mute-windows), pulled from input VIDEO metadata
        if external_file:
            try:
                file_windows = self._load_mute_windows_from_file(external_file)
                mute_windows.extend(file_windows)
            except Exception as e:
                if flags.verbose:
                    print(f"[mute_audio] Warning: Failed to load external mute windows '{external_file}': {e}")

        # 2b) Back-compat: if audio artifact itself declares a mute_windows_file, honor it too
        if "mute_windows_file" in artifact.metadata:
            try:
                file_windows = self._load_mute_windows_from_file(
                    artifact.metadata["mute_windows_file"]
                )
                mute_windows.extend(file_windows)
            except Exception as e:
                if flags.verbose:
                    print(f"[mute_audio] Warning: Failed to load per-audio mute windows '{artifact.metadata.get('mute_windows_file')}': {e}")

        # 3) Derive from subtitle artifacts using profanity detection
        if subtitle_artifacts:
            try:
                derived = self._derive_mute_windows_from_subtitles(subtitle_artifacts, flags)
                mute_windows.extend(derived)
            except Exception as e:
                if flags.verbose:
                    print(f"[mute_audio] Warning: Failed to derive mute windows from subtitles: {e}")
        
        # Sort and merge overlaps
        merged = self._merge_overlapping_windows(sorted(mute_windows, key=lambda w: (w.start, w.end)))
        return merged
    
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

    # ---- Helpers for deriving from subtitles ----
    def _derive_mute_windows_from_subtitles(self, subtitle_artifacts: List[Artifact], flags: OperationFlags) -> List[MuteWindow]:
        """Create mute windows for entries containing profanities using the matcher.
        
        Preference order for source subtitle: masked > merged > any extracted.
        Returns a list of windows with small padding.
        """
        if not subtitle_artifacts:
            return []

        chosen, reason = self._choose_best_subtitle_artifact(subtitle_artifacts)
        parser = SubtitleParser()

        # If chosen is masked and has original_file metadata, analyze the original for profanity
        source_path = chosen.path
        if (chosen.metadata.get('original_file') is not None) and Path(chosen.path).name == 'masked_subtitles.srt':
            try:
                orig = Path(chosen.metadata.get('original_file'))
                if orig.exists():
                    source_path = str(orig)
                    if flags.verbose:
                        print(f"[mute_audio] Using original subtitle for mute derivation: {source_path}")
            except Exception:
                # fallback silently
                pass

        # Load entries from the chosen source
        entries: List[SubtitleEntry] = parser.parse_file(source_path)

        # Prepare matcher with allow list
        profanity_path = self._resolve_default_profanity_file(flags.profanity_list_file)
        allow = []
        if profanity_path and Path(profanity_path).exists():
            try:
                allow = [w['word'] for w in json.loads(Path(profanity_path).read_text(encoding='utf-8'))]
            except Exception as e:
                if flags.verbose:
                    print(f"[mute_audio] Warning: failed to load profanity list from {profanity_path}: {e}")
        matcher = FuzzyMatcher(allow_list=allow, strategy='window')

        padding = 0.2  # seconds of padding around each window
        windows: List[MuteWindow] = []
        if flags.verbose:
            tprint(f"Scanning {len(entries)} subtitle entries for profanity windows", prefix="mute_audio")
        matched_entries = 0
        for entry in entries:
            matches = matcher.find_matches_in_text(entry.text)
            if matches:
                start_time = max(0.0, entry.start - padding)
                end_time = entry.end + padding
                windows.append(MuteWindow(start=start_time, end=end_time, reason='profanity', source='SUBTITLE'))
                matched_entries += 1

        if flags.verbose:
            tprint(f"Derived {len(windows)} raw windows from {matched_entries} matched subtitle entries", prefix="mute_audio")

        return windows

    def _choose_best_subtitle_artifact(self, subtitle_artifacts: List[Artifact]) -> Tuple[Artifact, str]:
        """Choose a single best subtitle artifact to analyze for profanity.
        
        Preference order: masked (metadata.original_file or filename masked_subtitles.srt)
        > merged (metadata.merged_from or filename merged_subtitles.srt) > first.
        """
        # Masked
        for a in subtitle_artifacts:
            if (a.metadata.get('original_file') is not None) or (Path(a.path).name == 'masked_subtitles.srt'):
                return a, 'masked subtitle'
        # Merged
        for a in subtitle_artifacts:
            if ('merged_from' in a.metadata) or (Path(a.path).name == 'merged_subtitles.srt'):
                return a, 'merged subtitle'
        # Fallback
        return subtitle_artifacts[0], 'extracted subtitle'

    def _merge_overlapping_windows(self, windows: List[MuteWindow]) -> List[MuteWindow]:
        """Merge overlapping or contiguous windows into minimal set."""
        if not windows:
            return []
        merged: List[MuteWindow] = []
        current = windows[0]
        for w in windows[1:]:
            if w.start <= current.end + 1e-3:  # allow tiny gap
                # extend
                current = MuteWindow(start=current.start, end=max(current.end, w.end), reason=current.reason, source=current.source)
            else:
                merged.append(current)
                current = w
        merged.append(current)
        return merged

    def _resolve_default_profanity_file(self, cli_path: Optional[str]) -> Optional[str]:
        """Resolve profanity list file path using CLI override or defaults."""
        if cli_path:
            return cli_path
        # 1) CWD/config/profanity_list.json
        cwd_candidate = Path.cwd() / 'config' / 'profanity_list.json'
        if cwd_candidate.exists():
            return str(cwd_candidate)
        # 2) Project root/config/profanity_list.json
        project_root = Path(__file__).resolve().parents[2]
        root_candidate = project_root / 'config' / 'profanity_list.json'
        if root_candidate.exists():
            return str(root_candidate)
        return None
    
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