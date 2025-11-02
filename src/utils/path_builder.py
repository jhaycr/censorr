"""Path building utilities for output modes and destination policies."""
import hashlib
import re
from pathlib import Path
from typing import Optional, Tuple

from src.models.config import OutputMode, DestinationPolicy


def build_same_folder_new_name(source_path: Path, edition_tag: str = "Censorr") -> Path:
    """
    Build a new filename in the same folder with edition tag.
    
    For movies: 'Movie Title (2024).mkv' -> 'Movie Title (2024) {edition-Censorr}.mkv'
    
    Args:
        source_path: Path to source video file
        edition_tag: Edition tag to add (default: "Censorr")
        
    Returns:
        Path to new file with edition tag
    """
    parent = source_path.parent
    stem = source_path.stem
    suffix = source_path.suffix
    
    # Check if edition tag already exists
    edition_pattern = r'\{edition-[^}]+\}'
    if re.search(edition_pattern, stem):
        # Edition tag already exists, return as-is
        return source_path
    
    # Find canonical "Title (Year)" segment to insert after
    # Match patterns like "Movie Title (2024)" or "Movie Title (2024) [Quality]"
    title_year_match = re.match(r'^(.+\(\d{4}\))', stem)
    if title_year_match:
        title_year = title_year_match.group(1)
        remainder = stem[len(title_year):]
        new_stem = f"{title_year} {{edition-{edition_tag}}}{remainder}"
    else:
        # No year pattern found, append to end
        new_stem = f"{stem} {{edition-{edition_tag}}}"
    
    return parent / f"{new_stem}{suffix}"


def build_destination_path(
    source_path: Path, 
    policy: str, 
    tag: str = "[Censorr]", 
    separate_root: str = "/data/media/TV/Censorr"
) -> Path:
    """
    Build destination path based on policy.
    
    Args:
        source_path: Path to source video file
        policy: "subfolder_tag" or "separate_root"
        tag: Tag to append for subfolder_tag policy
        separate_root: Root path for separate_root policy
        
    Returns:
        Path to destination file
    """
    if policy == "subfolder_tag":
        return _build_subfolder_tag_path(source_path, tag)
    elif policy == "separate_root":
        return _build_separate_root_path(source_path, separate_root)
    else:
        raise ValueError(f"Unknown destination policy: {policy}")


def _build_subfolder_tag_path(source_path: Path, tag: str) -> Path:
    """
    Build path with tagged subfolder.
    
    TV/General/Only Murders in the Building/Season 1/S01E01.mkv
    -> TV/General/Only Murders in the Building [Censorr]/Season 1/S01E01.mkv
    """
    parts = source_path.parts
    filename = source_path.name
    
    # Find the show folder (typically 3rd level in: TV/General/ShowName/Season/Episode)
    if len(parts) >= 4:
        # Assume structure: root/library/show/season/episode
        root_parts = parts[:-3]  # Everything before show/season/episode
        show_folder = parts[-3]  # Show name
        season_folder = parts[-2]  # Season folder
        
        # Add tag to show folder if not already present
        if tag not in show_folder:
            tagged_show = f"{show_folder} {tag}"
        else:
            tagged_show = show_folder
        
        return Path(*root_parts, tagged_show, season_folder, filename)
    else:
        # Fallback: just add tag to parent folder
        parent_parts = source_path.parent.parts
        if parent_parts:
            tagged_parent = f"{parent_parts[-1]} {tag}"
            return Path(*parent_parts[:-1], tagged_parent, filename)
        else:
            return source_path


def _build_separate_root_path(source_path: Path, separate_root: str) -> Path:
    """
    Build path under separate root.
    
    TV/General/Only Murders in the Building/Season 1/S01E01.mkv
    -> TV/Censorr/Only Murders in the Building/Season 1/S01E01.mkv
    """
    parts = source_path.parts
    filename = source_path.name
    
    # Extract show and season from original path
    if len(parts) >= 3:
        # Assume structure: root/library/show/season/episode
        show_folder = parts[-3]  # Show name
        season_folder = parts[-2]  # Season folder
        
        return Path(separate_root, show_folder, season_folder, filename)
    elif len(parts) >= 2:
        # Simpler structure: show/episode
        show_folder = parts[-2]
        return Path(separate_root, show_folder, filename)
    else:
        # Just filename
        return Path(separate_root, filename)


def resolve_output_conflict(
    target_path: Path, 
    policy: str = "reuse_if_identical"
) -> Tuple[Path, bool]:
    """
    Resolve output file conflicts.
    
    Args:
        target_path: Desired output path
        policy: Conflict resolution policy
            - "reuse_if_identical": Reuse if content matches (default)
            - "overwrite": Overwrite existing file
            - "fail": Fail if file exists
            - "suffix": Add numeric suffix
    
    Returns:
        Tuple of (final_path, should_write)
        should_write is False if file exists and should be reused
    """
    if not target_path.exists():
        return target_path, True
    
    if policy == "overwrite":
        return target_path, True
    elif policy == "fail":
        raise FileExistsError(f"Output file already exists: {target_path}")
    elif policy == "suffix":
        return _find_available_suffix_path(target_path), True
    elif policy == "reuse_if_identical":
        # For now, always reuse if exists (checksum comparison would need source)
        return target_path, False
    else:
        raise ValueError(f"Unknown conflict policy: {policy}")


def _find_available_suffix_path(target_path: Path) -> Path:
    """Find available path with numeric suffix."""
    parent = target_path.parent
    stem = target_path.stem
    suffix = target_path.suffix
    
    counter = 2
    while True:
        new_path = parent / f"{stem}-{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


def detect_media_type(file_path: Path) -> str:
    """
    Detect if file is likely a movie or TV episode.
    
    Returns:
        "movie" or "episode"
    """
    filename = file_path.name
    
    # Simple heuristic: look for episode patterns
    episode_patterns = [
        r'[Ss]\d{2}[Ee]\d{2}',  # S01E01
        r'[Ss]\d{1,2}\s*[Ee]\d{1,2}',  # S1 E1, S01 E01
        r'\d{1,2}x\d{1,2}',  # 1x01
    ]
    
    for pattern in episode_patterns:
        if re.search(pattern, filename):
            return "episode"
    
    return "movie"