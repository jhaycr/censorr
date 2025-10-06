"""Contract tests for deployment configuration validation script."""
import json
import os
import subprocess
import tempfile
import pytest
import yaml


class TestValidateDeploymentConfig:
    """Test validation script contract compliance."""

    @pytest.fixture
    def valid_config(self):
        """Valid configuration example for docker-compose deployment."""
        return {
            'censorr_enabled': True,
            'censorr_volumes': [
                {'host': '/mnt/media/tv', 'container': '/data/media/tv', 'mode': 'ro'},
                {'host': '/mnt/media/movies', 'container': '/data/media/movies', 'mode': 'ro'},
                {'host': '/srv/censorr/work', 'container': '/app/workdir', 'mode': 'rw'}
            ],
            'censorr_env': {
                'CENSORR_VERBOSE': 'true',
                'TZ': 'UTC'
            }
        }

    @pytest.fixture
    def script_path(self):
        """Path to validation script."""
        return "scripts/validate_deployment.py"

    def run_validator(self, config_data, script_path, extra_args=None):
        """Run validation script with given config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump(config_data, f)
            config_file = f.name

        try:
            cmd = ['python', script_path, '--config', config_file]
            if extra_args:
                cmd.extend(extra_args)
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True,
                cwd=os.getcwd()  # Use current working directory (repo root)
            )
            
            return result.returncode, result.stdout, result.stderr
        finally:
            os.unlink(config_file)

    def test_valid_config_succeeds(self, valid_config, script_path):
        """Valid configuration should return exit code 0."""
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 0, f"Expected success, got {returncode}: {stderr}"
        
        # Parse JSON output
        output = json.loads(stdout)
        assert output['valid'] is True
        assert len(output['errors']) == 0

    def test_missing_required_volume_fails(self, valid_config, script_path):
        """Missing required work volume should fail validation."""
        # Remove work volume (keep only media volumes)
        valid_config['censorr_volumes'] = [
            {'host': '/mnt/media/tv', 'container': '/data/media/tv', 'mode': 'ro'},
            {'host': '/mnt/media/movies', 'container': '/data/media/movies', 'mode': 'ro'}
        ]
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 1, f"Expected validation failure, got {returncode}"
        
        output = json.loads(stdout)
        assert output['valid'] is False
        assert any('work' in error.lower() and 'rw' in error for error in output['errors'])

    def test_invalid_env_key_fails(self, valid_config, script_path):
        """Environment keys must be uppercase."""
        valid_config['censorr_env']['censorr_verbose'] = 'true'  # lowercase - invalid
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 1
        
        output = json.loads(stdout)
        assert output['valid'] is False
        assert any('censorr_verbose' in error and 'uppercase' in error.lower() 
                  for error in output['errors'])

    def test_invalid_health_spec_fails(self, valid_config, script_path):
        """Invalid health specification should fail."""
        # Set both command and http endpoint (mutually exclusive)
        valid_config['censorr_health'] = {
            'command': ['censorr', '--version'],
            'http_endpoint': 'http://localhost:8080/health'  # hypothetical conflict
        }
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 1
        
        output = json.loads(stdout)
        assert output['valid'] is False
        # Should detect mutually exclusive health configurations

    def test_missing_config_file_fails(self, script_path):
        """Non-existent config file should return exit code 3."""
        cmd = ['python', script_path, '--config', '/nonexistent/file.yml']
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        assert result.returncode == 3
        assert 'not found' in result.stderr.lower() or 'file' in result.stderr.lower()

    def test_malformed_yaml_fails(self, script_path):
        """Malformed YAML should return exit code 3."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            config_file = f.name

        try:
            cmd = ['python', script_path, '--config', config_file]
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            assert result.returncode == 3
        finally:
            os.unlink(config_file)

    def test_json_output_format(self, valid_config, script_path):
        """Output should be valid JSON with required fields."""
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        # Should be parseable JSON
        output = json.loads(stdout)
        
        # Required fields
        assert 'valid' in output
        assert 'errors' in output
        assert isinstance(output['errors'], list)
        
        # Optional fields should exist
        assert 'warnings' in output
        assert isinstance(output['warnings'], list)

    def test_script_exists(self, script_path):
        """Validation script file should exist."""
        # This test will initially fail - that's expected for TDD
        assert os.path.exists(script_path), f"Validation script not found at {script_path}"