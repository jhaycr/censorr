"""Merge subtitles operation.

Merges multiple subtitle files into a single chronologically ordered file.
"""
from pathlib import Path
from typing import List, Set
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import Operation, OperationFlags
from src.utils.subtitle_parser import SubtitleParser, SubtitleEntry, SubtitleError


class MergeSubtitlesOperation(Operation):
    """Operation to merge multiple subtitle files into one."""
    
    def __init__(self):
        """Initialize the operation."""
        super().__init__("merge_subtitles")
        self.description = "Merge multiple subtitle files into chronologically ordered single file"
        self.parser = SubtitleParser()
    
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
            List with single merged subtitle artifact
        """
        try:
            # Find subtitle artifacts
            subtitle_artifacts = [
                artifact for artifact in inputs 
                if artifact.type == ArtifactType.SUBTITLE
            ]
            
            if not subtitle_artifacts:
                raise ValueError("No subtitle artifacts found for merging")
            
            if flags.dry_run:
                return self._handle_dry_run(subtitle_artifacts, workdir)
            
            # Parse all subtitle files
            all_entries = []
            combined_metadata = {}
            
            for artifact in subtitle_artifacts:
                try:
                    entries = self.parser.parse_file(artifact.path)
                    all_entries.append(entries)
                    
                    # Combine metadata (language should be consistent)
                    if not combined_metadata.get("language") and artifact.metadata.get("language"):
                        combined_metadata["language"] = artifact.metadata["language"]
                    
                    if flags.verbose:
                        print(f"Parsed {len(entries)} entries from {artifact.path}")
                        
                except SubtitleError as e:
                    raise RuntimeError(f"Failed to parse subtitle file {artifact.path}: {e}")
            
            # Merge entries in chronological order
            merged_entries = self._merge_entries(all_entries)
            
            if flags.verbose:
                print(f"Merged {len(merged_entries)} total subtitle entries")
            
            # Generate output path
            output_path = workdir / "merged_subtitles.srt"
            
            # Generate and write SRT content
            srt_content = self._generate_srt_content(merged_entries)
            output_path.write_text(srt_content, encoding='utf-8')
            
            # Create merged artifact
            merged_artifact = Artifact(
                type=ArtifactType.SUBTITLE,
                path=str(output_path),
                metadata={
                    **combined_metadata,
                    "merged_from": [artifact.path for artifact in subtitle_artifacts],
                    "entry_count": len(merged_entries)
                }
            )
            
            return [merged_artifact]
            
        except (ValueError, RuntimeError):
            # Re-raise expected exceptions
            raise
        except Exception as e:
            raise RuntimeError(f"Unexpected error during subtitle merging: {e}")
    
    def _merge_entries(self, entry_lists: List[List[SubtitleEntry]]) -> List[SubtitleEntry]:
        """Merge multiple lists of subtitle entries in chronological order.
        
        Args:
            entry_lists: List of lists of subtitle entries
            
        Returns:
            Single list of merged entries in chronological order
        """
        # Flatten all entries
        all_entries = []
        for entries in entry_lists:
            all_entries.extend(entries)
        
        # Sort by start time, then by end time for stability
        all_entries.sort(key=lambda entry: (entry.start, entry.end))
        
        # Renumber indices
        for i, entry in enumerate(all_entries):
            # Create new entry with updated index
            all_entries[i] = SubtitleEntry(
                index=i + 1,
                start=entry.start,
                end=entry.end,
                text=entry.text,
                normalized_text=entry.normalized_text
            )
        
        return all_entries
    
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
    
    def _handle_dry_run(self, subtitle_artifacts: List[Artifact], workdir: Path) -> List[Artifact]:
        """Handle dry run execution.
        
        Args:
            subtitle_artifacts: List of subtitle artifacts
            workdir: Working directory
            
        Returns:
            List with planned merged artifact
        """
        output_path = workdir / "merged_subtitles.srt"
        
        # Collect metadata
        combined_metadata = {}
        for artifact in subtitle_artifacts:
            if not combined_metadata.get("language") and artifact.metadata.get("language"):
                combined_metadata["language"] = artifact.metadata["language"]
        
        # Create planned artifact (not actually created)
        planned_artifact = Artifact(
            type=ArtifactType.SUBTITLE,
            path=str(output_path),
            metadata={
                **combined_metadata,
                "merged_from": [artifact.path for artifact in subtitle_artifacts],
                "planned": True
            }
        )
        
        return [planned_artifact]