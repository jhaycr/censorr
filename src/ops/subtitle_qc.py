"""Subtitle quality check operation for verifying masking effectiveness."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Set, Dict, Any

from ..models.artifacts import Artifact, ArtifactType
from ..models.operations import Operation, OperationFlags
from ..utils.fuzzy_matcher import FuzzyMatcher
from ..utils.subtitle_parser import SubtitleParser, SubtitleEntry
from ..models.profanity import normalize_profanity_list


class SubtitleQualityCheckOperation(Operation):
    """Operation to verify subtitle masking effectiveness and detect residual profanity."""
    
    def __init__(self):
        """Initialize the subtitle quality check operation."""
        super().__init__("subtitle_qc")
        self.description = "Verify subtitle masking effectiveness and detect residual profanity"
        self.parser = SubtitleParser()
        self.matcher = None
    
    @property
    def consumes(self) -> Set[ArtifactType]:
        """Return the artifact types this operation consumes."""
        return {ArtifactType.SUBTITLE}
    
    @property 
    def produces(self) -> Set[ArtifactType]:
        """Return the artifact types this operation produces."""
        return {ArtifactType.SUBTITLE}  # Pass-through with QC metadata
    
    def run(self, inputs: List[Artifact], workdir: Path, flags: OperationFlags) -> List[Artifact]:
        """Execute the subtitle quality check operation.
        
        Args:
            inputs: List of subtitle artifacts to check
            workdir: Working directory for outputs
            flags: Execution flags
            
        Returns:
            List with the original subtitle artifact plus QC metadata
        """
        if not inputs:
            raise ValueError("No subtitle artifacts provided for quality check")
        
        # Prefer masked subtitle artifacts; fallback to first subtitle
        subtitle_artifact = None
        masked_candidates = [
            a for a in inputs
            if a.type == ArtifactType.SUBTITLE and ((a.metadata or {}).get("masked") is True or "masked_subtitles" in str(a.path))
        ]
        if masked_candidates:
            subtitle_artifact = masked_candidates[0]
        else:
            for artifact in inputs:
                if artifact.type == ArtifactType.SUBTITLE:
                    subtitle_artifact = artifact
                    break

        if not subtitle_artifact:
            raise ValueError("No subtitle artifact found in inputs")

        if not masked_candidates and (flags.verbose):
            print("[subtitle_qc] Warning: masked subtitle not found; QC will run on first available subtitle")
        
        # Parse the subtitle file
        subtitle_path = Path(subtitle_artifact.path)
        if not subtitle_path.exists():
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
        
        try:
            entries = self.parser.parse_file(subtitle_path)
        except Exception as e:
            raise ValueError(f"Failed to parse subtitle file {subtitle_path}: {e}")
        
        # Run quality check
        qc_results = self._run_quality_check(entries, workdir, flags)
        
        # Create output artifact with QC metadata
        output_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(subtitle_path),
            metadata={
                **subtitle_artifact.metadata,
                "subtitle_qc": qc_results
            }
        )
        
        return [output_artifact]
    
    def _run_quality_check(self, entries: List[SubtitleEntry], workdir: Path, flags: OperationFlags) -> Dict[str, Any]:
        """Run quality check on subtitle entries to detect residual profanity.
        
        Args:
            entries: List of subtitle entries to check
            workdir: Working directory for QC reports  
            flags: Operation flags
            
        Returns:
            Dictionary containing QC results
        """
        # Initialize matcher if not already done
        if self.matcher is None:
            profanity_path = getattr(flags, 'profanity_list_file', None)
            if profanity_path and Path(profanity_path).exists():
                profanity_data = json.loads(Path(profanity_path).read_text(encoding='utf-8'))
                loaded_terms = normalize_profanity_list(profanity_data)
                self.matcher = FuzzyMatcher(similarity_threshold=85, allow_list=loaded_terms)
                if flags.verbose:
                    print(f"[subtitle_qc] Loaded {len(loaded_terms)} profanity terms for QC")
            else:
                # No profanity list - skip QC
                if flags.verbose:
                    print("[subtitle_qc] No profanity list found - QC skipped")
                return {
                    "operation": "subtitle_qc",
                    "status": "SKIPPED",
                    "reason": "No profanity list found",
                    "timestamp": datetime.now().isoformat(),
                    "residual_terms": []
                }
        
        # Check for residual profanity
        residual_matches = []
        total_entries = len(entries)
        
        for i, entry in enumerate(entries):
            if entry.text:
                # Skip entries that contain masking (asterisks or partial tokens)
                text_lower = entry.text.lower()
                if (
                    '***' in text_lower
                    or any('*' in token and len(token.replace('*', '')) <= 2 for token in text_lower.split())
                ):
                    continue

                matches = self.matcher.extract_profanity_matches(entry.text)
                if matches:
                    for match in matches:
                        residual_matches.append({
                            "entry_index": i,
                            "start_time": entry.start,
                            "end_time": entry.end,
                            "text": entry.text,
                            "matched_term": match.target if hasattr(match, 'target') else match.query,
                            "matched_text": match.window_text if match.window_text else match.query,
                            "confidence": match.score
                        })
        
        # Generate QC report
        status = "FAIL" if residual_matches else "PASS"
        qc_report = {
            "operation": "subtitle_qc", 
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "total_entries": total_entries,
            "residual_terms": len(residual_matches),
            "matches": residual_matches
        }
        
        # Write detailed QC report
        qc_report_path = workdir / "subtitle_qc_report.json"
        qc_report_path.write_text(json.dumps(qc_report, indent=2), encoding='utf-8')
        qc_report["report_path"] = str(qc_report_path)
        
        if flags.verbose:
            if residual_matches:
                print(f"[subtitle_qc] QC FAILED: {len(residual_matches)} residual profanity terms found")
                for match in residual_matches[:5]:  # Show first 5
                    print(f"[subtitle_qc]   - '{match['matched_text']}' at {match['start_time']}-{match['end_time']}")
                if len(residual_matches) > 5:
                    print(f"[subtitle_qc]   ... and {len(residual_matches) - 5} more")
            else:
                print(f"[subtitle_qc] QC PASSED: No residual profanity detected in {total_entries} entries")
            print(f"[subtitle_qc] Report written to: {qc_report_path}")
        
        return qc_report