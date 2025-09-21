"""Mask subtitles operation.

Applies profanity filtering to subtitle content using fuzzy matching.
"""
from pathlib import Path
from typing import List, Set
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import Operation, OperationFlags
from src.utils.subtitle_parser import SubtitleParser, SubtitleEntry, SubtitleError
from src.utils.fuzzy_matcher import FuzzyMatcher


class MaskSubtitlesOperation(Operation):
    """Operation to mask profanity in subtitle files."""
    
    def __init__(self, profanity_list: List[str] = None):
        """Initialize the operation.
        
        Args:
            profanity_list: Optional list of profanity terms to filter
        """
        super().__init__("mask_subtitles")
        self.description = "Apply profanity filtering to subtitle content using fuzzy matching"
        self.parser = SubtitleParser()
        
        # Use default profanity list if none provided
        if profanity_list is None:
            profanity_list = self._get_default_profanity_list()
        
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
            
            # Process first subtitle artifact (operation expects single subtitle)
            input_artifact = subtitle_artifacts[0]
            
            if flags.dry_run:
                return self._handle_dry_run(input_artifact, workdir)
            
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
            
            for entry in entries:
                if self.matcher.contains_profanity(entry.text):
                    masked_text = self._mask_text_profanity(entry.text)
                    # Count matches by checking individual words
                    words = entry.text.split()
                    word_matches = 0
                    for word in words:
                        clean_word = ''.join(c for c in word if c.isalnum())
                        if clean_word:
                            matches = self.matcher.match_against_allow_list(clean_word)
                            if matches and any(match.is_match for match in matches):
                                word_matches += 1
                    
                    total_matches += word_matches
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
                print(f"Found {total_matches} profanity matches in {entries_with_profanity} entries")
            
            # Generate output path
            output_path = workdir / "masked_subtitles.srt"
            
            # Generate and write SRT content
            srt_content = self._generate_srt_content(masked_entries)
            output_path.write_text(srt_content, encoding='utf-8')
            
            # Create masked artifact
            masked_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(output_path),
                metadata={
                    **input_artifact.metadata,
                    "original_file": input_artifact.path,
                    "profanity_filtered": total_matches > 0,
                    "matches_found": total_matches,
                    "entries_modified": entries_with_profanity
                }
            )
            
            return [masked_artifact]
            
        except (ValueError, RuntimeError):
            # Re-raise expected exceptions
            raise
        except Exception as e:
            raise RuntimeError(f"Unexpected error during subtitle masking: {e}")
    
    def _mask_text_profanity(self, text: str) -> str:
        """Mask profanity in text with asterisks.
        
        Args:
            text: Original text
            
        Returns:
            Text with profanity masked
        """
        if not self.matcher.allow_list:
            return text
        
        masked_text = text
        words = text.split()
        
        for i, word in enumerate(words):
            # Clean word of punctuation for matching
            clean_word = ''.join(c for c in word if c.isalnum())
            if not clean_word:
                continue
                
            # Check if word matches any profanity
            matches = self.matcher.match_against_allow_list(clean_word)
            if matches and any(match.is_match for match in matches):
                # Replace word with asterisks, preserving punctuation
                mask_length = len(clean_word)
                mask = "*" * mask_length
                
                # Replace the clean part with asterisks, keeping punctuation
                masked_word = ""
                for char in word:
                    if char.isalnum():
                        if mask:
                            masked_word += mask[0]
                            mask = mask[1:]
                        else:
                            masked_word += "*"
                    else:
                        masked_word += char
                
                words[i] = masked_word
        
        return " ".join(words)
    
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
    
    def _get_default_profanity_list(self) -> List[str]:
        """Get default profanity list for filtering.
        
        Returns:
            List of profanity terms
        """
        # Basic profanity list - in production this might be loaded from a file
        return [
            "damn", "hell", "shit", "fuck", "bitch", "ass", "crap",
            "piss", "bastard", "bloody", "goddamn", "dammit"
        ]