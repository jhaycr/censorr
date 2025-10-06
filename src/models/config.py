"""Configuration model for censorr CLI defaults."""
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class OutputMode(str, Enum):
    """Output mode for remux operations."""
    REMUX_ORIGINAL_VIDEO = "REMUX_ORIGINAL_VIDEO"
    REMUX_NEW_FILE = "REMUX_NEW_FILE"


class DestinationPolicy(BaseModel):
    """Destination policy for REMUX_NEW_FILE output mode."""
    policy: str = Field("subfolder_tag", description="Destination policy: subfolder_tag or separate_root")
    tag: str = Field("[Censorr]", description="Tag to append for subfolder_tag policy")
    separate_root: str = Field("/data/media/TV/Censorr", description="Root path for separate_root policy")
    template: Optional[str] = Field(None, description="Optional path template with tokens")
    
    @field_validator('policy')
    @classmethod
    def validate_policy(cls, v):
        """Ensure policy is valid."""
        valid_policies = ['subfolder_tag', 'separate_root']
        if v not in valid_policies:
            raise ValueError(f'policy must be one of: {valid_policies}')
        return v


class PresetConfig(BaseModel):
    """Configuration for a preset."""
    operations: List[str] = Field(default_factory=list, description="Pipeline operations")
    flags: Dict[str, Any] = Field(default_factory=dict, description="Default flags")
    language_selector: Dict[str, Any] = Field(default_factory=dict, description="Language selection rules")
    output: Dict[str, Any] = Field(default_factory=dict, description="Output configuration")
    destination_policy: Optional[DestinationPolicy] = Field(None, description="Destination policy for new file output")
    backup_default: bool = Field(False, description="Default backup behavior")


class Config(BaseModel):
    """Configuration model with CLI defaults."""
    
    # General settings
    output: str = Field("./output", description="Default output directory")
    dry_run: bool = Field(False, description="Default dry-run mode")
    verbose: bool = Field(False, description="Default verbose output")
    force: bool = Field(False, description="Default force overwrite")
    skip_existing: bool = Field(False, description="Default skip existing files")
    parallel: bool = Field(False, description="Default parallel execution")
    jobs: int = Field(1, description="Default number of parallel jobs")
    
    # Subtitle filtering defaults
    subtitle_title_include: List[str] = Field(default_factory=list, description="Default subtitle title include patterns")
    subtitle_title_exclude: List[str] = Field(default_factory=lambda: ["sdh", "hi", "cc"], description="Default subtitle title exclude patterns")
    subtitle_title_regex: List[str] = Field(default_factory=list, description="Default subtitle title regex patterns")
    
    # Processing defaults
    language: Optional[str] = Field(None, description="Default language filter")
    fuzzy_threshold: Optional[float] = Field(None, description="Default fuzzy matching threshold")
    subtitle_mode: str = Field("masked_only", description="Default subtitle mode for remux")
    sidecar_tag: str = Field("censorr", description="Default sidecar tag")
    
    # Quality control defaults
    continue_on_qc_fail: bool = Field(False, description="Default continue on QC failure")
    continue_on_audio_qc_fail: bool = Field(False, description="Default continue on audio QC failure")
    strict_audio_parity: bool = Field(False, description="Default strict audio parity")
    
    # File paths
    profanity_list_file: Optional[str] = Field(None, description="Default profanity list file path")
    
    # Output mode and destination policy
    output_mode: OutputMode = Field(OutputMode.REMUX_ORIGINAL_VIDEO, description="Default output mode")
    destination_policy: Optional[DestinationPolicy] = Field(None, description="Default destination policy")
    
    # Presets
    presets: Dict[str, PresetConfig] = Field(default_factory=dict, description="Named presets")
    
    @field_validator('jobs')
    @classmethod
    def validate_jobs(cls, v):
        """Ensure jobs is positive."""
        if v <= 0:
            raise ValueError('jobs must be positive')
        return v
    
    @field_validator('fuzzy_threshold')
    @classmethod
    def validate_fuzzy_threshold(cls, v):
        """Ensure fuzzy threshold is in valid range."""
        if v is not None and (v < 0 or v > 100):
            raise ValueError('fuzzy_threshold must be between 0 and 100')
        return v
    
    @field_validator('subtitle_mode')
    @classmethod
    def validate_subtitle_mode(cls, v):
        """Ensure subtitle mode is valid."""
        valid_modes = ['all', 'masked_only', 'none']
        if v not in valid_modes:
            raise ValueError(f'subtitle_mode must be one of: {valid_modes}')
        return v
    
    @field_validator('sidecar_tag')
    @classmethod
    def validate_sidecar_tag(cls, v):
        """Ensure sidecar tag is valid."""
        valid_tags = ['censorr', 'clean']
        if v not in valid_tags:
            raise ValueError(f'sidecar_tag must be one of: {valid_tags}')
        return v
    
    @classmethod
    def load_from_file(cls, config_path: Path) -> 'Config':
        """Load configuration from JSON file."""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls(**data)
        except FileNotFoundError:
            raise FileNotFoundError(f"Config file not found: {config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file {config_path}: {e}")
        except Exception as e:
            raise ValueError(f"Error loading config from {config_path}: {e}")
    
    @classmethod
    def load_with_fallback(cls, custom_path: Optional[str] = None) -> 'Config':
        """Load configuration with fallback hierarchy."""
        # Priority order:
        # 1. Custom path (if provided)
        # 2. ./config/censorr.json (project-local)
        # 3. ~/.config/censorr/config.json (user-global)
        # 4. Default values
        
        config_paths = []
        
        if custom_path:
            config_paths.append(Path(custom_path))
        
        # Project-local config
        project_config = Path.cwd() / "config" / "censorr.json"
        config_paths.append(project_config)
        
        # User-global config
        user_config = Path.home() / ".config" / "censorr" / "config.json"
        config_paths.append(user_config)
        
        # Try each path in order
        for config_path in config_paths:
            if config_path.exists():
                try:
                    return cls.load_from_file(config_path)
                except Exception:
                    # Continue to next path if loading fails
                    continue
        
        # Return default config if no files found
        return cls()
    
    def merge_with_args(self, **kwargs) -> Dict[str, Any]:
        """Merge config with CLI arguments, giving priority to CLI args."""
        # Start with config values
        merged = self.model_dump()
        
        # Override with any non-None CLI arguments
        for key, value in kwargs.items():
            if value is not None:
                merged[key] = value
            # Special handling for lists - CLI args should extend/override config lists
            elif key in ['subtitle_title_include', 'subtitle_title_exclude', 'subtitle_title_regex']:
                # Keep config default if CLI arg is None/empty
                pass
        
        return merged
    
    def save_to_file(self, config_path: Path) -> None:
        """Save configuration to JSON file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(self.model_dump(), f, indent=2, ensure_ascii=False)