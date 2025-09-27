"""Filename parsing utilities for sidecar naming and edition tagging."""
import re
from pathlib import Path
from typing import Optional, Tuple


def parse_title_and_edition(filename: str) -> Tuple[str, Optional[str]]:
    """Parse base title and detect existing edition tags from filename.
    
    Args:
        filename: Full filename or path
        
    Returns:
        Tuple of (base_title, existing_edition_tag)
        base_title excludes any existing edition tag
        existing_edition_tag is the content inside {edition-...} or None
    """
    # Get just the filename without path and extension
    path = Path(filename)
    name_no_ext = path.stem
    
    # Look for existing edition tag pattern: {edition-...}
    edition_pattern = r'\{edition-([^}]+)\}'
    edition_match = re.search(edition_pattern, name_no_ext, re.IGNORECASE)
    
    if edition_match:
        # Found existing edition tag
        existing_edition = edition_match.group(1)
        # Remove the edition tag to get base title
        base_title = re.sub(edition_pattern, '', name_no_ext, flags=re.IGNORECASE).strip()
        # Clean up any double spaces
        base_title = re.sub(r'\s+', ' ', base_title).strip()
        return base_title, existing_edition
    else:
        # No existing edition tag
        return name_no_ext.strip(), None


def ensure_movie_edition_tag(file_path: str, edition_tag: str = "Censorr") -> str:
    """Ensure movie file has edition tag, returning new path. Idempotent.
    
    Args:
        file_path: Path to the video file
        edition_tag: Edition tag to add (default: "Censorr")
        
    Returns:
        New file path with edition tag added (if not already present)
    """
    path = Path(file_path)
    base_title, existing_edition = parse_title_and_edition(path.name)
    
    if existing_edition:
        # Already has an edition tag - return unchanged (idempotent)
        return str(path)
    
    # Add the edition tag after the base title
    # Look for year pattern to insert before quality/other tokens
    year_pattern = r'(\([12]\d{3}\))'
    year_match = re.search(year_pattern, base_title)
    
    if year_match:
        # Insert edition tag after year
        year_end = year_match.end()
        new_name = (
            base_title[:year_end] + 
            f" {{edition-{edition_tag}}}" + 
            base_title[year_end:]
        )
    else:
        # No year found, append edition tag at the end
        new_name = f"{base_title} {{edition-{edition_tag}}}"
    
    # Clean up spacing and reconstruct full path
    new_name = re.sub(r'\s+', ' ', new_name).strip()
    new_path = path.parent / f"{new_name}{path.suffix}"
    
    return str(new_path)


def is_episode_filename(filename: str) -> bool:
    """Check if filename appears to be a TV episode based on pattern.
    
    Args:
        filename: Filename to check
        
    Returns:
        True if filename contains episode pattern (S##E##)
    """
    path = Path(filename)
    name = path.stem
    
    # Look for season/episode patterns like S01E03, S1E1, etc.
    episode_patterns = [
        r'S\d{1,2}E\d{1,2}',  # S01E02, S1E2
        r'Season\s*\d+.*Episode\s*\d+',  # Season 1 Episode 2
        r'\d{1,2}x\d{1,2}',  # 1x02
    ]
    
    for pattern in episode_patterns:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    
    return False


def build_sidecar_subtitle_path(
    video_path: str, 
    language: str, 
    tag: str = "censorr"
) -> str:
    """Build sidecar subtitle path following Plex naming convention.
    
    Args:
        video_path: Path to the source video file
        language: ISO 639-1 language code (will be lowercased)  
        tag: Censorship tag (default: "censorr", alternative: "clean")
        
    Returns:
        Path for sidecar subtitle file: <base>.<lang>.<tag>.srt
    """
    path = Path(video_path)
    base_title, _ = parse_title_and_edition(path.name)  # Strip edition tag from base
    
    # Normalize base title: collapse whitespace, trim
    normalized_base = re.sub(r'\s+', ' ', base_title).strip()
    
    # Build sidecar filename: base.lang.tag.srt
    lang_lower = language.lower()
    sidecar_name = f"{normalized_base}.{lang_lower}.{tag}.srt"
    
    # Place in same directory as video
    sidecar_path = path.parent / sidecar_name
    
    return str(sidecar_path)


def handle_sidecar_collision(target_path: str, content_checksum: str) -> str:
    """Handle sidecar file collision by checking content or finding new name.
    
    Args:
        target_path: Desired sidecar file path
        content_checksum: Checksum of content to be written
        
    Returns:
        Final path to use (may have numeric suffix if collision with different content)
    """
    import hashlib
    from pathlib import Path
    
    target = Path(target_path)
    
    if not target.exists():
        # No collision
        return target_path
    
    # File exists - check if content is identical
    try:
        with open(target, 'rb') as f:
            existing_content = f.read()
            existing_checksum = hashlib.md5(existing_content).hexdigest()
            
        if existing_checksum == content_checksum:
            # Identical content - reuse existing file
            return target_path
    except (IOError, OSError):
        # Can't read existing file - treat as collision
        pass
    
    # Different content - find new name with numeric suffix
    counter = 2
    while True:
        # Insert counter before .srt extension
        new_name = f"{target.stem}-{counter}{target.suffix}"
        new_path = target.parent / new_name
        
        if not new_path.exists():
            return str(new_path)
        
        # Check if this one matches content
        try:
            with open(new_path, 'rb') as f:
                existing_content = f.read()
                existing_checksum = hashlib.md5(existing_content).hexdigest()
                
            if existing_checksum == content_checksum:
                # Found matching content
                return str(new_path)
        except (IOError, OSError):
            # Can't read - continue searching
            pass
        
        counter += 1
        if counter > 100:  # Safety limit
            break
    
    # Fallback - use the numbered version even if we can't verify
    return str(new_path)