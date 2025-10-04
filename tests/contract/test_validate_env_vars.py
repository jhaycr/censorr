"""Contract tests for environment variable validation."""
import json
import pytest
import yaml
from tests.contract.test_validate_deployment_config import TestValidateDeploymentConfig


class TestValidateEnvironmentVars(TestValidateDeploymentConfig):
    """Test environment variable validation rules."""

    def test_valid_env_vars_succeed(self, valid_config, script_path):
        """Valid environment variables should pass."""
        valid_config['censorr_env'] = {
            'CENSORR_VERBOSE': 'true',
            'CENSORR_JOBS': '4',
            'TZ': 'UTC',
            'CENSORR_SIDECAR_TAG': 'clean'
        }
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 0
        output = json.loads(stdout)
        assert output['valid'] is True

    def test_lowercase_env_key_fails(self, valid_config, script_path):
        """Lowercase environment keys should fail."""
        valid_config['censorr_env']['censorr_verbose'] = 'true'  # lowercase
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 1
        output = json.loads(stdout)
        assert output['valid'] is False
        assert any('censorr_verbose' in error and 'uppercase' in error.lower()
                  for error in output['errors'])

    def test_mixed_case_env_key_fails(self, valid_config, script_path):
        """Mixed case environment keys should fail."""
        valid_config['censorr_env']['Censorr_Verbose'] = 'true'  # mixed case
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 1
        output = json.loads(stdout)
        assert output['valid'] is False

    def test_spaces_in_env_key_fails(self, valid_config, script_path):
        """Spaces in environment keys should fail."""
        valid_config['censorr_env']['CENSORR VERBOSE'] = 'true'  # space
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 1
        output = json.loads(stdout)
        assert output['valid'] is False

    def test_non_string_env_values_warn(self, valid_config, script_path):
        """Non-string environment values should generate warnings."""
        valid_config['censorr_env']['CENSORR_JOBS'] = 4  # integer instead of string
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        # Should succeed but warn
        assert returncode == 0
        output = json.loads(stdout)
        assert output['valid'] is True
        assert any('string' in warning.lower() for warning in output['warnings'])

    def test_empty_env_section_succeeds(self, valid_config, script_path):
        """Empty environment section should be valid."""
        valid_config['censorr_env'] = {}
        
        returncode, stdout, stderr = self.run_validator(valid_config, script_path)
        
        assert returncode == 0
        output = json.loads(stdout)
        assert output['valid'] is True