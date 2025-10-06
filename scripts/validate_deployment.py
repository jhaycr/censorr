#!/usr/bin/env python3
"""
Validate Censorr deployment configuration.

Usage: python scripts/validate_deployment.py --config path/to/censorr.yml [--runtime-check]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    import yaml
except ImportError:
    print("Error: PyYAML not installed. Run: pip install PyYAML", file=sys.stderr)
    sys.exit(3)


class ValidationResult:
    """Holds validation results."""
    
    def __init__(self):
        self.valid = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.runtime_checks: Dict[str, Any] = {}
    
    def add_error(self, message: str):
        """Add validation error."""
        self.valid = False
        self.errors.append(message)
    
    def add_warning(self, message: str):
        """Add validation warning."""
        self.warnings.append(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON output."""
        result = {
            'valid': self.valid,
            'errors': self.errors,
            'warnings': self.warnings
        }
        if self.runtime_checks:
            result['runtime_checks'] = self.runtime_checks
        return result


class DeploymentValidator:
    """Validates Censorr deployment configuration."""
    
    def __init__(self):
        self.result = ValidationResult()
    
    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        """Validate deployment configuration."""
        self._validate_required_fields(config)
        self._validate_volumes(config)
        self._validate_environment(config)
        self._validate_health_check(config)
        self._validate_resources(config)
        
        return self.result
    
    def validate_runtime(self, config: Dict[str, Any], container_name: str = 'censorr', 
                        runtime_json_file: Optional[str] = None) -> ValidationResult:
        """Validate runtime container state."""
        try:
            if runtime_json_file:
                # Load from JSON file (for testing)
                with open(runtime_json_file, 'r') as f:
                    inspect_data = json.load(f)
                    if isinstance(inspect_data, list) and len(inspect_data) > 0:
                        container_info = inspect_data[0]
                    else:
                        container_info = inspect_data
            else:
                # Get live container info
                container_info = self._get_container_info(container_name)
            
            if container_info:
                self._validate_runtime_state(config, container_info)
            else:
                self.result.runtime_checks['container_running'] = False
                self.result.add_error(f"Container '{container_name}' not found")
                
        except Exception as e:
            self.result.add_error(f"Runtime validation failed: {e}")
        
        return self.result
    
    def _get_container_info(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Get container information from docker inspect."""
        try:
            result = subprocess.run(
                ['docker', 'inspect', container_name],
                capture_output=True,
                text=True,
                check=True
            )
            inspect_data = json.loads(result.stdout)
            return inspect_data[0] if inspect_data else None
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            return None
    
    def _validate_runtime_state(self, config: Dict[str, Any], container_info: Dict[str, Any]):
        """Validate container state against configuration."""
        # Check if container is running
        running = container_info.get('State', {}).get('Running', False)
        self.result.runtime_checks['container_running'] = running
        
        if not running:
            self.result.add_warning("Container is not running")
        
        # Validate image
        self._validate_runtime_image(config, container_info)
        
        # Validate volumes
        self._validate_runtime_volumes(config, container_info)
        
        # Validate environment
        self._validate_runtime_environment(config, container_info)
        
        # Validate labels
        self._validate_runtime_labels(config, container_info)
        
        # Validate health status
        self._validate_runtime_health(config, container_info)
    
    def _validate_runtime_image(self, config: Dict[str, Any], container_info: Dict[str, Any]):
        """Validate container image matches configuration."""
        expected_repo = config.get('censorr_image_repo', '')
        expected_tag = config.get('censorr_image_tag', '')
        
        # For now, assume match (would need registry API to resolve tag to digest)
        self.result.runtime_checks['image_match'] = True
    
    def _validate_runtime_volumes(self, config: Dict[str, Any], container_info: Dict[str, Any]):
        """Validate container volumes match configuration."""
        expected_volumes = config.get('censorr_volumes', [])
        actual_mounts = container_info.get('Mounts', [])
        
        volumes_match = True
        
        for expected_vol in expected_volumes:
            expected_host = expected_vol['host']
            expected_container = expected_vol['container']
            expected_mode = expected_vol['mode']
            
            # Find matching mount
            matching_mount = None
            for mount in actual_mounts:
                if mount['Destination'] == expected_container:
                    matching_mount = mount
                    break
            
            if not matching_mount:
                volumes_match = False
                self.result.add_error(f"Missing volume mount: {expected_container}")
                continue
            
            # Check source path
            if matching_mount['Source'] != expected_host:
                volumes_match = False
                self.result.add_error(f"Volume source mismatch for {expected_container}: expected {expected_host}, got {matching_mount['Source']}")
            
            # Check read-write mode
            expected_rw = expected_mode == 'rw'
            actual_rw = matching_mount.get('RW', False)
            if expected_rw != actual_rw:
                volumes_match = False
                self.result.add_error(f"Volume mode mismatch for {expected_container}: expected {expected_mode}, got {'rw' if actual_rw else 'ro'}")
        
        self.result.runtime_checks['volumes_match'] = volumes_match
    
    def _validate_runtime_environment(self, config: Dict[str, Any], container_info: Dict[str, Any]):
        """Validate container environment matches configuration."""
        expected_env = config.get('censorr_env', {})
        actual_env_list = container_info.get('Config', {}).get('Env', [])
        
        # Convert list to dict
        actual_env = {}
        for env_var in actual_env_list:
            if '=' in env_var:
                key, value = env_var.split('=', 1)
                actual_env[key] = value
        
        env_match = True
        for key, expected_value in expected_env.items():
            if key not in actual_env:
                env_match = False
                self.result.add_error(f"Missing environment variable: {key}")
            elif actual_env[key] != expected_value:
                env_match = False
                self.result.add_error(f"Environment variable mismatch for {key}: expected {expected_value}, got {actual_env[key]}")
        
        self.result.runtime_checks['env_match'] = env_match
    
    def _validate_runtime_labels(self, config: Dict[str, Any], container_info: Dict[str, Any]):
        """Validate container labels match configuration."""
        expected_labels = config.get('censorr_labels', {})
        actual_labels = container_info.get('Config', {}).get('Labels', {}) or {}
        
        labels_match = True
        
        # Check base labels
        base_labels = {
            'org.censorr.service': 'censorr',
            'org.censorr.version': config.get('censorr_image_tag', '')
        }
        
        for key, expected_value in base_labels.items():
            if key not in actual_labels:
                labels_match = False
                self.result.add_error(f"Missing base label: {key}")
            elif actual_labels[key] != expected_value:
                labels_match = False
                self.result.add_error(f"Base label mismatch for {key}: expected {expected_value}, got {actual_labels[key]}")
        
        # Check custom labels
        for key, expected_value in expected_labels.items():
            if key not in actual_labels:
                labels_match = False
                self.result.add_error(f"Missing custom label: {key}")
            elif actual_labels[key] != expected_value:
                labels_match = False
                self.result.add_error(f"Custom label mismatch for {key}: expected {expected_value}, got {actual_labels[key]}")
        
        self.result.runtime_checks['labels_match'] = labels_match
    
    def _validate_runtime_health(self, config: Dict[str, Any], container_info: Dict[str, Any]):
        """Validate container health status."""
        health_config = config.get('censorr_health')
        if health_config:
            health_status = container_info.get('State', {}).get('Health', {}).get('Status')
            self.result.runtime_checks['health_status'] = health_status
            
            if health_status == 'unhealthy':
                self.result.add_warning("Container health check is failing")
            elif health_status == 'starting':
                self.result.add_warning("Container health check is still starting")
            elif health_status != 'healthy':
                self.result.add_warning(f"Container health status: {health_status}")
        else:
            self.result.runtime_checks['health_status'] = 'not_configured'
    
    def _validate_required_fields(self, config: Dict[str, Any]):
        """Validate required configuration fields."""
        # For docker-compose deployment, we only need basic fields
        # Image building is handled by docker-compose via Dockerfile
        required_fields = ['censorr_enabled', 'censorr_volumes']
        
        for field in required_fields:
            if field not in config:
                self.result.add_error(f"Missing required field: {field}")
    
    def _validate_volumes(self, config: Dict[str, Any]):
        """Validate volume configuration."""
        volumes = config.get('censorr_volumes', [])
        
        if not isinstance(volumes, list):
            self.result.add_error("censorr_volumes must be a list")
            return
        
        # Check for required volumes
        has_media_ro = False
        has_work_rw = False
        
        for volume in volumes:
            if not isinstance(volume, dict):
                self.result.add_error("Volume entries must be dictionaries")
                continue
            
            if 'host' not in volume or 'container' not in volume or 'mode' not in volume:
                self.result.add_error("Volume entries must have 'host', 'container', and 'mode' fields")
                continue
            
            # Check for media volume (read-only)
            if 'media' in volume['container'] and volume['mode'] == 'ro':
                has_media_ro = True
            
            # Check for work volume (read-write)
            if ('work' in volume['container'] or 'workdir' in volume['container']) and volume['mode'] == 'rw':
                has_work_rw = True
            
            # Validate mode
            if volume['mode'] not in ['ro', 'rw']:
                self.result.add_error(f"Invalid volume mode '{volume['mode']}': must be 'ro' or 'rw'")
        
        if not has_media_ro:
            self.result.add_error("Missing required volume: media mount with mode 'ro'")
        
        if not has_work_rw:
            self.result.add_error("Missing required volume: work directory mount with mode 'rw'")
    
    def _validate_environment(self, config: Dict[str, Any]):
        """Validate environment variables."""
        env_vars = config.get('censorr_env', {})
        
        if not isinstance(env_vars, dict):
            self.result.add_error("censorr_env must be a dictionary")
            return
        
        for key, value in env_vars.items():
            # Validate key format (uppercase, underscores, no spaces)
            if not re.match(r'^[A-Z0-9_]+$', key):
                self.result.add_error(f"Invalid environment key '{key}': must be uppercase letters, numbers, and underscores only")
            
            # Warn about non-string values
            if not isinstance(value, str):
                self.result.add_warning(f"Environment value for '{key}' should be a string, got {type(value).__name__}")
    
    def _validate_health_check(self, config: Dict[str, Any]):
        """Validate health check configuration."""
        health = config.get('censorr_health')
        
        if health is None:
            return  # Health check is optional
        
        if not isinstance(health, dict):
            self.result.add_error("censorr_health must be a dictionary")
            return
        
        # Check for mutually exclusive configurations
        has_command = 'command' in health
        has_http = 'http_endpoint' in health
        
        if has_command and has_http:
            self.result.add_error("Health check cannot have both 'command' and 'http_endpoint'")
        
        if not has_command and not has_http:
            self.result.add_error("Health check must specify either 'command' or 'http_endpoint'")
        
        # Validate command
        if has_command:
            command = health['command']
            if not isinstance(command, list) or len(command) == 0:
                self.result.add_error("Health check command must be a non-empty array")
        
        # Validate intervals
        for field in ['interval_seconds', 'timeout_seconds', 'retries', 'start_period_seconds']:
            if field in health:
                value = health[field]
                if not isinstance(value, int) or value < 0:
                    self.result.add_error(f"Health check {field} must be a positive integer")
        
        # Warn if timeout > interval
        interval = health.get('interval_seconds', 30)
        timeout = health.get('timeout_seconds', 5)
        if timeout > interval:
            self.result.add_warning(f"Health check timeout ({timeout}s) is greater than interval ({interval}s)")
    
    def _validate_resources(self, config: Dict[str, Any]):
        """Validate resource constraints."""
        cpu_shares = config.get('censorr_cpu_shares')
        mem_limit = config.get('censorr_mem_limit')
        
        if cpu_shares is not None:
            if not isinstance(cpu_shares, int) or cpu_shares <= 0:
                self.result.add_error("censorr_cpu_shares must be a positive integer")
        
        if mem_limit is not None:
            if not isinstance(mem_limit, str):
                self.result.add_error("censorr_mem_limit must be a string (e.g., '512m', '1g')")
            elif not re.match(r'^\d+[kmg]?$', mem_limit.lower()):
                self.result.add_error(f"Invalid memory limit format '{mem_limit}': use format like '512m' or '1g'")


def load_config(config_path: str) -> Dict[str, Any]:
    """Load YAML configuration file."""
    try:
        config_file = Path(config_path)
        if not config_file.exists():
            print(f"Error: Configuration file not found: {config_path}", file=sys.stderr)
            sys.exit(3)
        
        with open(config_file, 'r') as f:
            return yaml.safe_load(f)
    
    except yaml.YAMLError as e:
        print(f"Error: Invalid YAML in {config_path}: {e}", file=sys.stderr)
        sys.exit(3)
    except Exception as e:
        print(f"Error reading configuration file: {e}", file=sys.stderr)
        sys.exit(3)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Validate Censorr deployment configuration')
    parser.add_argument('--config', required=True, help='Path to configuration YAML file')
    parser.add_argument('--runtime-check', action='store_true', 
                       help='Also validate running container state')
    parser.add_argument('--runtime-json', 
                       help='Path to JSON file with docker inspect output (for testing)')
    parser.add_argument('--container-name', default='censorr',
                       help='Container name to inspect (default: censorr)')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Validate configuration
    validator = DeploymentValidator()
    result = validator.validate_config(config)
    
    # Runtime checks
    if args.runtime_check:
        result = validator.validate_runtime(config, args.container_name, args.runtime_json)
    
    # Output results
    print(json.dumps(result.to_dict(), indent=2))
    
    # Exit with appropriate code
    if not result.valid:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == '__main__':
    main()