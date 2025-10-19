"""Mask subtitles operation.

Applies profanity filtering to subtitle content using fuzzy matching with
per-word threshold configuration and aggressive variant detection.
"""
import json
from pathlib import Path
from typing import List, Set, Dict, Any, Optional, Union
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import Operation, OperationFlags
from src.models.profanity import ProfanityTerm, normalize_profanity_list
from src.utils.subtitle_parser import SubtitleParser, SubtitleEntry, SubtitleError
from src.utils.fuzzy_matcher import FuzzyMatcher


class MaskSubtitlesOperation(Operation):
    """Operation to mask profanity in subtitle files."""
    
    def __init__(self, profanity_list: Union[List[str], List[ProfanityTerm]] = None):
        """Initialize the operation.
        
        Args:
            profanity_list: Optional list of profanity terms (strings or ProfanityTerm objects) to filter
        """
        super().__init__("subtitle_mask")
        self.description = "Apply profanity filtering to subtitle content using fuzzy matching"
        self.parser = SubtitleParser()

        # Track whether profanity_list was explicitly provided
        self._explicit_profanity_list = profanity_list is not None
        
        # Defer allow-list initialization; we'll read from file at run-time
        if profanity_list is None:
            profanity_list = []
        
        self.matcher = FuzzyMatcher(
            similarity_threshold=85.0,  # High threshold for profanity matching
            allow_list=profanity_list,
            normalization_enabled=True
        )
    
    @property
    def consumes(self) -> Set[ArtifactType]:
        """Return the set of artifact types this operation consumes."""
        return {ArtifactType.SUBTITLE}
    
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
            List with single masked subtitle artifact
        """
        try:
            # Find subtitle artifacts
            subtitle_artifacts = [
                artifact for artifact in inputs 
                if artifact.type == ArtifactType.SUBTITLE
            ]
            
            if not subtitle_artifacts:
                raise ValueError("No subtitle artifacts found for masking")
            
            # Prefer a merged subtitle artifact if available; otherwise use the first
            input_artifact = self._choose_best_input_subtitle(subtitle_artifacts)
            if flags.verbose:
                source_kind = (
                    "merged" if ('merged_from' in input_artifact.metadata or Path(input_artifact.path).name == 'merged_subtitles.srt')
                    else "extracted"
                )
                print(f"[subtitle_mask] Using {source_kind} subtitle: {input_artifact.path}")
            
            if flags.dry_run:
                return self._handle_dry_run(input_artifact, workdir)
            
            # Initialize profanity allow list: prefer explicit constructor list, then CLI flag, then default config
            if not self._explicit_profanity_list:
                profanity_path: Optional[Path] = None
                if flags.profanity_list_file:
                    profanity_path = Path(flags.profanity_list_file)
                else:
                    profanity_path = self._resolve_default_profanity_file()

                if profanity_path is not None:
                    loaded_terms = self._load_profanity_list(profanity_path)
                    self.matcher._initialize_profanity_terms(loaded_terms)
                    if flags.verbose:
                        print(f"[subtitle_mask] Loaded {len(loaded_terms)} profanity terms from {profanity_path}")
                        # Print effective configuration summary
                        aggressive_count = sum(1 for term in self.matcher.profanity_terms if term.is_aggressive_variant_enabled())
                        custom_threshold_count = sum(1 for term in self.matcher.profanity_terms if term.fuzzy_threshold is not None)
                        if aggressive_count > 0 or custom_threshold_count > 0:
                            print(f"[subtitle_mask] Per-word config: {custom_threshold_count} custom thresholds, {aggressive_count} aggressive variants")
                else:
                    if flags.verbose:
                        print("[subtitle_mask] No profanity list found; proceeding with empty allow_list")
            else:
                if flags.verbose:
                    print(f"[subtitle_mask] Using explicit profanity list with {len(self.matcher.allow_list)} terms")

            # Parse subtitle file
            try:
                entries = self.parser.parse_file(input_artifact.path)
                if flags.verbose:
                    print(f"Parsed {len(entries)} subtitle entries from {input_artifact.path}")
            except SubtitleError as e:
                raise RuntimeError(f"Failed to parse subtitle file {input_artifact.path}: {e}")
            
            # Filter profanity from entries
            masked_entries = []
            total_matches = 0
            entries_with_profanity = 0
            unique_terms: Set[str] = set()
            
            for entry in entries:
                # Use new window-based matching
                matches = self.matcher.find_matches_in_text(entry.text)
                if matches:
                    masked_text = self._mask_text_profanity(entry.text, matches)
                    
                    # Count unique terms found
                    for match in matches:
                        unique_terms.add(match.target)
                    
                    total_matches += len(matches)
                    entries_with_profanity += 1
                    
                    # Create new entry with masked text
                    masked_entry = SubtitleEntry(
                        index=entry.index,
                        start=entry.start,
                        end=entry.end,
                        text=masked_text,
                        normalized_text=self.parser.normalize_text(masked_text)
                    )
                    masked_entries.append(masked_entry)
                else:
                    # Keep original entry
                    masked_entries.append(entry)
            
            if flags.verbose:
                total_entries = len(entries)
                unchanged = total_entries - entries_with_profanity
                pct_masked = (entries_with_profanity / total_entries * 100.0) if total_entries else 0.0
                print(f"[subtitle_mask] Entries: {total_entries} | Masked: {entries_with_profanity} ({pct_masked:.1f}%) | Unchanged: {unchanged}")
                print(f"[subtitle_mask] Window-based matches: {total_matches} | Unique profane terms matched: {len(unique_terms)}")
            
            # Generate output path
            output_path = workdir / "masked_subtitles.srt"
            
            # Generate and write SRT content
            srt_content = self._generate_srt_content(masked_entries)
            output_path.write_text(srt_content, encoding='utf-8')
            if flags.verbose:
                print(f"[subtitle_mask] Wrote masked subtitles to: {output_path}")

            # Run quality check on masked content
            qc_results = self._run_quality_check(masked_entries, workdir, flags)
            
            # Handle QC results
            if qc_results["residual_matches"] > 0:
                if not flags.continue_on_qc_fail:
                    # Fail the pipeline by default
                    qc_report_path = qc_results["report_path"]
                    raise RuntimeError(
                        f"Quality check failed: Found {qc_results['residual_matches']} residual profane matches. "
                        f"See QC report at {qc_report_path}. Use --continue-on-qc-fail to proceed despite failures."
                    )
                else:
                    # Log warning but continue
                    if flags.verbose:
                        print(f"Warning: QC found {qc_results['residual_matches']} residual matches, but continuing due to --continue-on-qc-fail flag")
            
            # Create masked artifact
            masked_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(output_path),
                metadata={
                    **input_artifact.metadata,
                    "original_file": input_artifact.path,
                    "profanity_filtered": total_matches > 0,
                    "matches_found": total_matches,
                    "entries_modified": entries_with_profanity,
                    "qc": qc_results if qc_results["residual_matches"] > 0 else None
                }
            )
            
            return [masked_artifact]
            
        except (ValueError, RuntimeError):
            # Re-raise expected exceptions
            raise
        except Exception as e:
            raise RuntimeError(f"Unexpected error during subtitle masking: {e}")

    def _run_quality_check(self, masked_entries: List[SubtitleEntry], workdir: Path, flags: OperationFlags) -> Dict[str, Any]:
        """Run quality check to detect missed profanities in masked content.
        
        Since our masking operation uses the same matcher to detect profanities
        and then masks them completely, the QC should find zero residual matches
        if masking worked correctly. Any profanity still detectable after masking
        indicates a bug in the masking logic.
        
        Args:
            masked_entries: List of processed subtitle entries (after masking)
            workdir: Working directory for QC report
            flags: Execution flags
            
        Returns:
            QC results dictionary with residual matches and report path
        """
        residual_matches = []
        total_residual_count = 0
        sample_limit = 3
        
        # Scan for residual matches in the masked text using the same matcher
        for entry in masked_entries:
            matches = self.matcher.find_matches_in_text(entry.text)
            
            if matches:
                # This indicates a masking failure - profanity should have been masked
                for match in matches:
                    term_entry = next((rm for rm in residual_matches if rm["term"] == match.target), None)
                    if not term_entry:
                        term_entry = {"term": match.target, "count": 0, "samples": []}
                        residual_matches.append(term_entry)
                    
                    term_entry["count"] += 1
                    total_residual_count += 1
                    
                    if len(term_entry["samples"]) < sample_limit:
                        term_entry["samples"].append({
                            "cue_index": entry.index,
                            "start": entry.start,
                            "end": entry.end,
                            "excerpt": entry.text[:160] + ("..." if len(entry.text) > 160 else ""),
                            "matched_token": match.window_text or match.query,
                            "matched_term": match.target
                        })
        
        # Generate QC report
        qc_report = {
            "terms": residual_matches,
            "totals": {
                "matches": total_residual_count,
                "terms": len(residual_matches)
            },
            "language": "unknown",
            "policy": "partial", 
            "sample_limit": sample_limit
        }
        
        # Write QC report to file
        qc_report_path = workdir / "qc_report.json"
        qc_report_path.write_text(json.dumps(qc_report, indent=2), encoding='utf-8')
        
        # Log summary
        if flags.verbose:
            if total_residual_count > 0:
                print(f"QC: Found {total_residual_count} residual matches across {len(residual_matches)} terms")
                print(f"QC report written to: {qc_report_path}")
            else:
                print("QC: No residual matches found - quality check passed")
        
        return {
            "residual_matches": total_residual_count,
            "report_path": str(qc_report_path),
            "terms_with_matches": len(residual_matches),
            "continued": flags.continue_on_qc_fail if total_residual_count > 0 else False
        }
    
    def _mask_text_profanity(self, text: str, matches: List) -> str:
        """Mask profanity in text with asterisks using window matches.
        
        Args:
            text: Original text
            matches: List of MatchResult objects from find_matches_in_text
            
        Returns:
            Text with profanity masked
        """
        if not matches:
            return text

        # For each match, find and mask the corresponding text in the original
        result_text = text
        
        for match in matches:
            # Use the window_text to find the exact substring to mask
            target_phrase = match.window_text
            
            # Find all occurrences of this phrase in the original text (case-insensitive)
            import re
            
            # Escape special regex characters in the target phrase
            escaped_phrase = re.escape(target_phrase)
            
            # Create pattern that matches word boundaries to avoid partial matches
            pattern = r'\b' + escaped_phrase + r'\b'
            
            # Replace all occurrences with asterisks, preserving case
            def replacement(match_obj):
                matched_text = match_obj.group(0)
                return '*' * len(matched_text)
            
            result_text = re.sub(pattern, replacement, result_text, flags=re.IGNORECASE)
        
        return result_text
    
    def _generate_srt_content(self, entries: List[SubtitleEntry]) -> str:
        """Generate SRT format content from subtitle entries.
        
        Args:
            entries: List of subtitle entries
            
        Returns:
            SRT format content as string
        """
        lines = []
        
        for entry in entries:
            # Entry number
            lines.append(str(entry.index))
            
            # Timing line
            start_time = self._format_srt_timestamp(entry.start)
            end_time = self._format_srt_timestamp(entry.end)
            lines.append(f"{start_time} --> {end_time}")
            
            # Text content
            lines.append(entry.text)
            
            # Empty line separator
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_srt_timestamp(self, seconds: float) -> str:
        """Format timestamp for SRT format.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            SRT format timestamp (HH:MM:SS,mmm)
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        milliseconds = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
    
    def _handle_dry_run(self, input_artifact: Artifact, workdir: Path) -> List[Artifact]:
        """Handle dry run execution.
        
        Args:
            input_artifact: Input subtitle artifact
            workdir: Working directory
            
        Returns:
            List with planned masked artifact
        """
        output_path = workdir / "masked_subtitles.srt"
        
        # Create planned artifact (not actually created)
        planned_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(output_path),
            metadata={
                **input_artifact.metadata,
                "original_file": input_artifact.path,
                "planned": True
            }
        )
        
        return [planned_artifact]

    def _choose_best_input_subtitle(self, subtitle_artifacts: List[Artifact]) -> Artifact:
        """Choose the best subtitle to mask.

        Preference order: merged (by metadata or filename) > first extracted.

        This is resilient to cached artifacts where metadata may be missing.
        """
        if not subtitle_artifacts:
            raise ValueError("No subtitle artifacts available")

        # Prefer by explicit metadata
        for a in subtitle_artifacts:
            if 'merged_from' in a.metadata:
                return a

        # Prefer by filename heuristic
        for a in subtitle_artifacts:
            if Path(a.path).name == 'merged_subtitles.srt':
                return a

        # Fallback to the first available subtitle
        return subtitle_artifacts[0]
    
    def _load_profanity_list(self, file_path: Path) -> List[Union[str, Dict[str, Any]]]:
        """Load profanity terms from a JSON file.

        The file format supports both legacy string arrays and new structured format:
        Legacy: ["damn", "hell"]
        New: [{"word": "damn"}, {"word": "hell", "fuzzy_threshold": 90, "variant_strategy": "aggressive"}]
        Mixed: ["damn", {"word": "hell", "fuzzy_threshold": 90}]
        
        Args:
            file_path: Path to the JSON file
        
        Returns:
            List of profanity terms (strings or dicts) for normalization
        """
        if not file_path.exists():
            raise RuntimeError(f"Profanity list file not found: {file_path}")
        try:
            data = json.loads(file_path.read_text(encoding='utf-8'))
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON in profanity list file {file_path}: {e}")
        if not isinstance(data, list):
            raise RuntimeError(f"Profanity list file must be a JSON array, got {type(data).__name__}")
        
        # Validate entries but don't normalize here - let normalize_profanity_list handle it
        for i, item in enumerate(data):
            if isinstance(item, str):
                if not item:
                    raise RuntimeError(f"Entry {i} is an empty string")
            elif isinstance(item, dict):
                if "word" not in item:
                    raise RuntimeError(f"Entry {i} missing required 'word' field")
                if not isinstance(item["word"], str) or not item["word"]:
                    raise RuntimeError(f"Entry {i} has invalid 'word' field")
            else:
                raise RuntimeError(f"Entry {i} must be string or object, got {type(item).__name__}")
        
        return data

    def _resolve_default_profanity_file(self) -> Optional[Path]:
        """Resolve default profanity list path if available.

        Checks the following locations in order and returns the first that exists:
        1) Current working directory: ./config/profanity_list.json
        2) Project root (two levels above this file): <project>/config/profanity_list.json

        Returns:
            Path to the default file if found, else None.
        """
        # 1) CWD/config/profanity_list.json
        cwd_candidate = Path.cwd() / "config" / "profanity_list.json"
        if cwd_candidate.exists():
            return cwd_candidate

        # 2) Project root/config/profanity_list.json
        project_root = Path(__file__).resolve().parents[2]
        root_candidate = project_root / "config" / "profanity_list.json"
        if root_candidate.exists():
            return root_candidate

        return None