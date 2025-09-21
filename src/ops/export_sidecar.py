"""Export sidecar operation.

Exports subtitles and metadata to external sidecar files in various formats.
"""
import json
import xml.etree.ElementTree as ET
from enum import Enum
from pathlib import Path
from typing import List, Set, Dict, Any, Optional
from src.models.artifacts import Artifact, ArtifactType
from src.models.operations import Operation, OperationFlags
from src.utils.subtitle_parser import SubtitleParser, SubtitleEntry, SubtitleError


class SidecarFormat(Enum):
    """Supported sidecar export formats."""
    SRT = "srt"
    JSON = "json"
    XML = "xml"


class ExportSidecarOperation(Operation):
    """Operation to export subtitles and metadata to external sidecar files."""
    
    def __init__(self, format: SidecarFormat = SidecarFormat.SRT):
        """Initialize the operation.
        
        Args:
            format: Export format for the sidecar file
        """
        super().__init__("export_sidecar")
        self.description = "Export subtitles and metadata to external sidecar files"
        self.format = format
        self.parser = SubtitleParser()
    
    @property
    def consumes(self) -> Set[ArtifactType]:
        """Return the set of artifact types this operation consumes."""
        return {ArtifactType.SUBTITLE, ArtifactType.VIDEO}
    
    @property
    def produces(self) -> Set[ArtifactType]:
        """Return the set of artifact types this operation produces."""
        return {ArtifactType.SIDECAR}
    
    def run(self, inputs: List[Artifact], workdir: Path, flags: OperationFlags) -> List[Artifact]:
        """Execute the operation.
        
        Args:
            inputs: List of input artifacts
            workdir: Working directory for outputs
            flags: Execution flags
            
        Returns:
            List with single sidecar artifact
        """
        try:
            # Find subtitle and video artifacts
            subtitle_artifacts = [
                artifact for artifact in inputs 
                if artifact.type == ArtifactType.SUBTITLE
            ]
            video_artifacts = [
                artifact for artifact in inputs 
                if artifact.type == ArtifactType.VIDEO
            ]
            
            if not subtitle_artifacts and not video_artifacts:
                raise ValueError("No subtitle or video artifacts found for sidecar export")
            
            if flags.dry_run:
                return self._handle_dry_run(workdir, subtitle_artifacts, video_artifacts)
            
            # Parse subtitle files
            all_subtitle_entries = []
            source_artifacts = []
            
            for artifact in subtitle_artifacts:
                try:
                    entries = self.parser.parse_file(artifact.path)
                    all_subtitle_entries.extend(entries)
                    source_artifacts.append(artifact.path)
                    
                    if flags.verbose:
                        print(f"Parsed {len(entries)} subtitle entries from {artifact.path}")
                        
                except SubtitleError as e:
                    raise RuntimeError(f"Failed to parse subtitle file {artifact.path}: {e}")
            
            # Sort subtitle entries chronologically and renumber
            all_subtitle_entries.sort(key=lambda entry: (entry.start, entry.end))
            for i, entry in enumerate(all_subtitle_entries):
                all_subtitle_entries[i] = SubtitleEntry(
                    index=i + 1,
                    start=entry.start,
                    end=entry.end,
                    text=entry.text,
                    normalized_text=entry.normalized_text
                )
            
            # Collect video metadata
            video_metadata = {}
            for artifact in video_artifacts:
                video_metadata.update(artifact.metadata)
                source_artifacts.append(artifact.path)
            
            if flags.verbose:
                print(f"Exporting sidecar in {self.format.value} format with {len(all_subtitle_entries)} subtitle entries")
            
            # Generate output path
            output_path = workdir / f"sidecar.{self.format.value}"
            
            # Export in specified format
            if self.format == SidecarFormat.SRT:
                content = self._export_srt_format(all_subtitle_entries)
            elif self.format == SidecarFormat.JSON:
                content = self._export_json_format(all_subtitle_entries, video_metadata, source_artifacts)
            elif self.format == SidecarFormat.XML:
                content = self._export_xml_format(all_subtitle_entries, video_metadata, source_artifacts)
            else:
                raise ValueError(f"Unsupported sidecar format: {self.format}")
            
            # Write sidecar file
            output_path.write_text(content, encoding='utf-8')
            
            # Create sidecar artifact
            sidecar_artifact = Artifact(
                type=ArtifactType.SIDECAR,
                path=str(output_path),
                metadata={
                    "format": self.format.value,
                    "source_artifacts": source_artifacts,
                    "subtitle_count": len(all_subtitle_entries),
                    "has_video_metadata": bool(video_metadata)
                }
            )
            
            return [sidecar_artifact]
            
        except (ValueError, RuntimeError):
            # Re-raise expected exceptions
            raise
        except Exception as e:
            raise RuntimeError(f"Unexpected error during sidecar export: {e}")
    
    def _export_srt_format(self, entries: List[SubtitleEntry]) -> str:
        """Export subtitle entries in SRT format.
        
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
    
    def _export_json_format(self, entries: List[SubtitleEntry], video_metadata: Dict[str, Any], source_artifacts: List[str]) -> str:
        """Export data in JSON format.
        
        Args:
            entries: List of subtitle entries
            video_metadata: Video metadata dictionary
            source_artifacts: List of source artifact paths
            
        Returns:
            JSON format content as string
        """
        data = {
            "metadata": {
                "format": "json",
                "source_artifacts": source_artifacts,
                "export_timestamp": "2025-09-20T00:00:00Z"  # Could use actual timestamp
            },
            "subtitles": [
                {
                    "index": entry.index,
                    "start": entry.start,
                    "end": entry.end,
                    "duration": entry.end - entry.start,
                    "text": entry.text,
                    "normalized_text": entry.normalized_text
                }
                for entry in entries
            ],
            "video": video_metadata
        }
        
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    def _export_xml_format(self, entries: List[SubtitleEntry], video_metadata: Dict[str, Any], source_artifacts: List[str]) -> str:
        """Export data in XML format.
        
        Args:
            entries: List of subtitle entries
            video_metadata: Video metadata dictionary
            source_artifacts: List of source artifact paths
            
        Returns:
            XML format content as string
        """
        root = ET.Element("sidecar")
        
        # Metadata section
        metadata_elem = ET.SubElement(root, "metadata")
        format_elem = ET.SubElement(metadata_elem, "format")
        format_elem.text = "xml"
        
        sources_elem = ET.SubElement(metadata_elem, "source_artifacts")
        for artifact_path in source_artifacts:
            source_elem = ET.SubElement(sources_elem, "artifact")
            source_elem.text = artifact_path
        
        # Subtitles section
        subtitles_elem = ET.SubElement(root, "subtitles")
        for entry in entries:
            subtitle_elem = ET.SubElement(subtitles_elem, "subtitle")
            subtitle_elem.set("index", str(entry.index))
            subtitle_elem.set("start", str(entry.start))
            subtitle_elem.set("end", str(entry.end))
            
            text_elem = ET.SubElement(subtitle_elem, "text")
            text_elem.text = entry.text
            
            normalized_elem = ET.SubElement(subtitle_elem, "normalized_text")
            normalized_elem.text = entry.normalized_text
        
        # Video section
        if video_metadata:
            video_elem = ET.SubElement(root, "video")
            for key, value in video_metadata.items():
                field_elem = ET.SubElement(video_elem, key)
                field_elem.text = str(value)
        
        # Convert to string with XML declaration
        rough_string = ET.tostring(root, encoding='unicode')
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{rough_string}'
    
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
    
    def _handle_dry_run(self, workdir: Path, subtitle_artifacts: List[Artifact], video_artifacts: List[Artifact]) -> List[Artifact]:
        """Handle dry run execution.
        
        Args:
            workdir: Working directory
            subtitle_artifacts: List of subtitle artifacts
            video_artifacts: List of video artifacts
            
        Returns:
            List with planned sidecar artifact
        """
        output_path = workdir / f"sidecar.{self.format.value}"
        
        # Collect source artifacts
        source_artifacts = []
        source_artifacts.extend([artifact.path for artifact in subtitle_artifacts])
        source_artifacts.extend([artifact.path for artifact in video_artifacts])
        
        # Create planned artifact (not actually created)
        planned_artifact = Artifact(
            type=ArtifactType.SIDECAR,
            path=str(output_path),
            metadata={
                "format": self.format.value,
                "source_artifacts": source_artifacts,
                "planned": True
            }
        )
        
        return [planned_artifact]