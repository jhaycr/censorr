"""Contract tests for deployment validation script health check scenarios."""
import json
import tempfile
import pytest
import yaml
from tests.contract.test_validate_deployment_config import TestValidateDeploymentConfig


class TestValidateHealthSpecs(TestValidateDeploymentConfig):
    """Test health check validation scenarios."""

    def test_valid_health_command_succeeds(self, valid_config, script_path):
        """Valid health command configuration should pass."""
        valid_config['censorr_health'] = {
            'command': ['censorr', '--version'],
            'interval_seconds': 30,
            'timeout_seconds': 5,
            'retries': 3,
            'start_period_seconds': 10
        }
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 0
        output = json.loads(stdout)
        assert output['valid'] is True

    def test_empty_health_command_fails(self, valid_config, script_path):
        """Empty health command should fail validation."""
        valid_config['censorr_health'] = {
            'command': [],  # Empty command array
            'interval_seconds': 30
        }
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 1
        output = json.loads(stdout)
        assert output['valid'] is False
        assert any('command' in error and 'empty' in error.lower() 
                  for error in output['errors'])

    def test_negative_health_intervals_fail(self, valid_config, script_path):
        """Negative health check intervals should fail."""
        valid_config['censorr_health'] = {
            'command': ['censorr', '--version'],
            'interval_seconds': -1,  # Invalid
            'timeout_seconds': 5
        }
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 1
        output = json.loads(stdout)
        assert output['valid'] is False
        assert any('interval' in error and ('negative' in error.lower() or 'positive' in error.lower())
                  for error in output['errors'])

    def test_timeout_greater_than_interval_warns(self, valid_config, script_path):
        """Timeout greater than interval should generate warning."""
        valid_config['censorr_health'] = {
            'command': ['censorr', '--version'],
            'interval_seconds': 10,
            'timeout_seconds': 15  # Greater than interval
        }
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        # Should succeed but warn
        assert returncode == 0
        output = json.loads(stdout)
        assert output['valid'] is True
        assert any('timeout' in warning.lower() and 'interval' in warning.lower()
                  for warning in output['warnings'])