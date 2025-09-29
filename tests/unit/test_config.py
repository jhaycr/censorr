"""Unit tests for configuration system."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, mock_open
from src.models.config import Config


class TestConfig:
    """Test configuration model and loading."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = Config()
        
        assert config.output == "./output"
        assert config.dry_run is False
        assert config.verbose is False
        assert config.subtitle_title_exclude == ["sdh", "hi", "cc"]
        assert config.subtitle_title_include == []
        assert config.subtitle_mode == "masked_only"
        assert config.sidecar_tag == "censorr"
        assert config.jobs == 1
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Valid config
        config = Config(jobs=4, fuzzy_threshold=85.0, subtitle_mode="all")
        assert config.jobs == 4
        assert config.fuzzy_threshold == 85.0
        assert config.subtitle_mode == "all"
        
        # Invalid jobs
        with pytest.raises(ValueError, match="jobs must be positive"):
            Config(jobs=0)
        
        with pytest.raises(ValueError, match="jobs must be positive"):
            Config(jobs=-1)
        
        # Invalid fuzzy threshold
        with pytest.raises(ValueError, match="fuzzy_threshold must be between 0 and 100"):
            Config(fuzzy_threshold=-1)
        
        with pytest.raises(ValueError, match="fuzzy_threshold must be between 0 and 100"):
            Config(fuzzy_threshold=101)
        
        # Invalid subtitle mode
        with pytest.raises(ValueError, match="subtitle_mode must be one of"):
            Config(subtitle_mode="invalid")
        
        # Invalid sidecar tag
        with pytest.raises(ValueError, match="sidecar_tag must be one of"):
            Config(sidecar_tag="invalid")
    
    def test_load_from_file(self, tmp_path):
        """Test loading configuration from file."""
        config_data = {
            "output": "./custom-output",
            "verbose": True,
            "subtitle_title_exclude": ["custom", "patterns"],
            "jobs": 8
        }
        
        config_file = tmp_path / "config.json"
        with open(config_file, 'w') as f:
            json.dump(config_data, f)
        
        config = Config.load_from_file(config_file)
        
        assert config.output == "./custom-output"
        assert config.verbose is True
        assert config.subtitle_title_exclude == ["custom", "patterns"]
        assert config.jobs == 8
        # Defaults should still apply for unspecified fields
        assert config.dry_run is False
        assert config.subtitle_mode == "masked_only"
    
    def test_load_from_file_not_found(self, tmp_path):
        """Test loading from non-existent file."""
        config_file = tmp_path / "nonexistent.json"
        
        with pytest.raises(FileNotFoundError, match="Config file not found"):
            Config.load_from_file(config_file)
    
    def test_load_from_file_invalid_json(self, tmp_path):
        """Test loading from invalid JSON file."""
        config_file = tmp_path / "invalid.json"
        with open(config_file, 'w') as f:
            f.write("{ invalid json }")
        
        with pytest.raises(ValueError, match="Invalid JSON"):
            Config.load_from_file(config_file)
    
    def test_load_with_fallback_custom_path(self, tmp_path):
        """Test loading with custom path."""
        config_data = {"output": "./custom", "verbose": True}
        
        custom_config = tmp_path / "custom.json"
        with open(custom_config, 'w') as f:
            json.dump(config_data, f)
        
        config = Config.load_with_fallback(str(custom_config))
        
        assert config.output == "./custom"
        assert config.verbose is True
    
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.home')
    def test_load_with_fallback_hierarchy(self, mock_home, mock_cwd, tmp_path):
        """Test configuration loading fallback hierarchy."""
        # Setup mock paths
        mock_cwd.return_value = tmp_path / "project"
        mock_home.return_value = tmp_path / "home"
        
        # Create directories
        (tmp_path / "project" / "config").mkdir(parents=True)
        (tmp_path / "home" / ".config" / "censorr").mkdir(parents=True)
        
        # Create project-local config
        project_config = tmp_path / "project" / "config" / "censorr.json"
        with open(project_config, 'w') as f:
            json.dump({"output": "./project-output"}, f)
        
        # Create user-global config
        user_config = tmp_path / "home" / ".config" / "censorr" / "config.json"
        with open(user_config, 'w') as f:
            json.dump({"output": "./user-output", "verbose": True}, f)
        
        # Should load project config (higher priority)
        config = Config.load_with_fallback()
        assert config.output == "./project-output"
        # Should use defaults for fields not in project config
        assert config.verbose is False  # Default, not from user config
    
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.home')
    def test_load_with_fallback_user_config(self, mock_home, mock_cwd, tmp_path):
        """Test loading user config when no project config exists."""
        # Setup mock paths
        mock_cwd.return_value = tmp_path / "project"
        mock_home.return_value = tmp_path / "home"
        
        # Create user config directory and file
        (tmp_path / "home" / ".config" / "censorr").mkdir(parents=True)
        user_config = tmp_path / "home" / ".config" / "censorr" / "config.json"
        with open(user_config, 'w') as f:
            json.dump({"output": "./user-output", "verbose": True}, f)
        
        # Should load user config (project config doesn't exist)
        config = Config.load_with_fallback()
        assert config.output == "./user-output"
        assert config.verbose is True
    
    @patch('pathlib.Path.cwd')
    @patch('pathlib.Path.home')
    def test_load_with_fallback_defaults(self, mock_home, mock_cwd, tmp_path):
        """Test loading defaults when no config files exist."""
        # Setup mock paths to non-existent directories
        mock_cwd.return_value = tmp_path / "project"
        mock_home.return_value = tmp_path / "home"
        
        # Should return default config
        config = Config.load_with_fallback()
        assert config.output == "./output"
        assert config.verbose is False
        assert config.subtitle_title_exclude == ["sdh", "hi", "cc"]
    
    def test_merge_with_args(self):
        """Test merging config with CLI arguments."""
        config = Config(
            output="./config-output",
            verbose=True,
            subtitle_title_exclude=["config", "exclude"]
        )
        
        # CLI args should override config
        merged = config.merge_with_args(
            output="./cli-output",
            force=True,  # Not in config
            verbose=None  # Should keep config value
        )
        
        assert merged['output'] == "./cli-output"  # CLI override
        assert merged['verbose'] is True  # Config value (CLI was None)
        assert merged['force'] is True  # CLI addition
        assert merged['subtitle_title_exclude'] == ["config", "exclude"]  # Config value
    
    def test_merge_with_args_list_handling(self):
        """Test list field handling in merge."""
        config = Config(subtitle_title_exclude=["config", "patterns"])
        
        # None CLI args should preserve config lists
        merged = config.merge_with_args(subtitle_title_exclude=None)
        assert merged['subtitle_title_exclude'] == ["config", "patterns"]
        
        # Non-None CLI args should override
        merged = config.merge_with_args(subtitle_title_exclude=["cli", "patterns"])
        assert merged['subtitle_title_exclude'] == ["cli", "patterns"]
    
    def test_save_to_file(self, tmp_path):
        """Test saving configuration to file."""
        config = Config(
            output="./test-output",
            verbose=True,
            subtitle_title_exclude=["test", "save"]
        )
        
        config_file = tmp_path / "saved_config.json"
        config.save_to_file(config_file)
        
        # Verify file was created and contains correct data
        assert config_file.exists()
        
        with open(config_file, 'r') as f:
            saved_data = json.load(f)
        
        assert saved_data['output'] == "./test-output"
        assert saved_data['verbose'] is True
        assert saved_data['subtitle_title_exclude'] == ["test", "save"]
    
    def test_save_creates_directory(self, tmp_path):
        """Test that save creates parent directories."""
        config = Config()
        config_file = tmp_path / "nested" / "path" / "config.json"
        
        config.save_to_file(config_file)
        
        assert config_file.exists()
        assert config_file.parent.exists()