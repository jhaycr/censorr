"""Contract tests for build mode validation in deployment config validator."""

import os
import tempfile
import subprocess
import json
import pytest
from pathlib import Path


class TestValidateBuildMode:
    """Test build mode validation scenarios."""
    
    def test_valid_config_succeeds(self):
        """Valid build config should pass validation."""
        config = {
            'censorr_enabled': True,
            'censorr_build_enabled': True,
            'censorr_git_repo': 'https://github.com/jhaycr/censorr_private.git',
            'censorr_git_ref': 'main',
            'censorr_volumes': [
                {'host': '/mnt/media/tv', 'container': '/data/media/tv', 'mode': 'ro'},
                {'host': '/srv/censorr/work', 'container': '/app/workdir', 'mode': 'rw'}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            result = subprocess.run([
                'python3', 'scripts/validate_deployment.py',
                '--config', config_path
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
            
            assert result.returncode == 0
            output = json.loads(result.stdout)
            assert output['valid'] is True
            assert len(output['errors']) == 0
        finally:
            os.unlink(config_path)
    
    def test_missing_required_volume_fails(self):
        """Config missing required work volume should fail."""
        config = {
            'censorr_enabled': True,
            'censorr_build_enabled': True,
            'censorr_git_repo': 'https://github.com/jhaycr/censorr_private.git',
            'censorr_git_ref': 'main',
            'censorr_volumes': [
                {'host': '/mnt/media/tv', 'container': '/data/media/tv', 'mode': 'ro'}
                # Missing work volume
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            result = subprocess.run([
                'python3', 'scripts/validate_deployment.py',
                '--config', config_path
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
            
            assert result.returncode == 1
            output = json.loads(result.stdout)
            assert output['valid'] is False
            assert any('work' in error.lower() for error in output['errors'])
        finally:
            os.unlink(config_path)

    def test_both_image_and_build_enabled_fails(self):
        """Config with both image and build mode should fail (T029.1)."""
        config = {
            'censorr_enabled': True,
            'censorr_build_enabled': True,
            'censorr_image_repo': 'ghcr.io/jhaycr/censorr',
            'censorr_image_tag': 'v0.1.0',
            'censorr_git_repo': 'https://github.com/jhaycr/censorr_private.git',
            'censorr_git_ref': 'main',
            'censorr_volumes': [
                {'host': '/mnt/media/tv', 'container': '/data/media/tv', 'mode': 'ro'},
                {'host': '/srv/censorr/work', 'container': '/app/workdir', 'mode': 'rw'}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            result = subprocess.run([
                'python3', 'scripts/validate_deployment.py',
                '--config', config_path
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
            
            assert result.returncode == 1
            output = json.loads(result.stdout)
            assert output['valid'] is False
            assert any('both image configuration' in error for error in output['errors'])
        finally:
            os.unlink(config_path)

    def test_build_enabled_but_missing_git_repo_fails(self):
        """Config with build enabled but missing git repo should fail (T029.2)."""
        config = {
            'censorr_enabled': True,
            'censorr_build_enabled': True,
            # Missing censorr_git_repo
            'censorr_git_ref': 'main',
            'censorr_volumes': [
                {'host': '/mnt/media/tv', 'container': '/data/media/tv', 'mode': 'ro'},
                {'host': '/srv/censorr/work', 'container': '/app/workdir', 'mode': 'rw'}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            result = subprocess.run([
                'python3', 'scripts/validate_deployment.py',
                '--config', config_path
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
            
            assert result.returncode == 1
            output = json.loads(result.stdout)
            assert output['valid'] is False
            assert any('censorr_git_repo not specified' in error for error in output['errors'])
        finally:
            os.unlink(config_path)

    def test_build_enabled_but_missing_git_ref_fails(self):
        """Config with build enabled but missing git ref should fail (T029.2)."""
        config = {
            'censorr_enabled': True,
            'censorr_build_enabled': True,
            'censorr_git_repo': 'https://github.com/jhaycr/censorr_private.git',
            # Missing censorr_git_ref
            'censorr_volumes': [
                {'host': '/mnt/media/tv', 'container': '/data/media/tv', 'mode': 'ro'},
                {'host': '/srv/censorr/work', 'container': '/app/workdir', 'mode': 'rw'}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            result = subprocess.run([
                'python3', 'scripts/validate_deployment.py',
                '--config', config_path
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
            
            assert result.returncode == 1
            output = json.loads(result.stdout)
            assert output['valid'] is False
            assert any('censorr_git_ref not specified' in error for error in output['errors'])
        finally:
            os.unlink(config_path)

    def test_malformed_yaml_fails(self):
        """Malformed YAML should fail gracefully."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            config_path = f.name
        
        try:
            result = subprocess.run([
                'python3', 'scripts/validate_deployment.py',
                '--config', config_path
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
            
            assert result.returncode == 3
        finally:
            os.unlink(config_path)

    def test_json_output_format(self):
        """Output should be valid JSON with expected structure."""
        config = {
            'censorr_enabled': True,
            'censorr_build_enabled': True,
            'censorr_git_repo': 'https://github.com/jhaycr/censorr_private.git',
            'censorr_git_ref': 'main',
            'censorr_volumes': [
                {'host': '/mnt/media/tv', 'container': '/data/media/tv', 'mode': 'ro'},
                {'host': '/srv/censorr/work', 'container': '/app/workdir', 'mode': 'rw'}
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            import yaml
            yaml.dump(config, f)
            config_path = f.name
        
        try:
            result = subprocess.run([
                'python3', 'scripts/validate_deployment.py',
                '--config', config_path
            ], capture_output=True, text=True, cwd=Path(__file__).parent.parent.parent)
            
            output = json.loads(result.stdout)
            assert 'valid' in output
            assert 'errors' in output
            assert 'warnings' in output
            assert isinstance(output['valid'], bool)
            assert isinstance(output['errors'], list)
            assert isinstance(output['warnings'], list)
        finally:
            os.unlink(config_path)

    def test_script_exists(self):
        """Validation script should exist at expected path."""
        script_path = Path(__file__).parent.parent.parent / 'scripts' / 'validate_deployment.py'
        assert script_path.exists()
        assert script_path.is_file()