# Requirements Document: Docker Compose Deployment

## Introduction

This feature provides a simple, generic Docker Compose deployment configuration for Censorr, enabling users to run the tool as a long-running service without requiring Ansible or complex orchestration. The deployment supports local builds, environment-based configuration, and standard Docker Compose workflows.

## Glossary

- **System**: The Docker Compose deployment configuration and associated tooling
- **Service**: A containerized instance of Censorr running via Docker Compose
- **Compose File**: The docker-compose.yml configuration defining services, volumes, and networks
- **Environment Template**: The env.template file documenting available configuration options
- **Media Mount**: A bind-mounted directory providing read access to media files
- **Working Directory**: A bind-mounted directory for Censorr's output and temporary files
- **Health Check**: A container health verification mechanism using command execution
- **Restart Policy**: Docker's automatic container restart behavior configuration

## Requirements

### Requirement 1: Simple Deployment

**User Story:** As a homelab operator, I want to deploy Censorr using docker-compose.yml with minimal configuration, so that I can get started quickly without complex setup.

#### Acceptance Criteria

1. WHEN a user runs `docker compose up -d` with the provided configuration, THE System SHALL build and start the Censorr container
2. WHEN no .env file is present, THE System SHALL use documented default values for all configuration
3. WHEN the container starts successfully, THE System SHALL be ready to process media files
4. WHEN a user runs `docker compose down`, THE System SHALL stop and remove the container while preserving volume data
5. THE System SHALL provide a docker-compose.yml file in the repository root

### Requirement 2: Local Build by Default

**User Story:** As a developer, I want Docker Compose to build the image locally from the Dockerfile by default, so that I can test changes without pushing to a registry.

#### Acceptance Criteria

1. WHEN docker-compose.yml is used without modification, THE System SHALL build the image from the local Dockerfile
2. THE System SHALL not require IMAGE_REPO or IMAGE_TAG environment variables for basic usage
3. WHEN a user runs `docker compose build`, THE System SHALL rebuild the image with current code
4. WHEN a user wants to use a published image, THE System SHALL support overriding the build configuration
5. THE System SHALL document how to switch from local build to published image usage

### Requirement 3: Media Volume Configuration

**User Story:** As a user, I want to configure separate mount points for TV and movie media, so that I can organize my library according to my existing structure.

#### Acceptance Criteria

1. THE System SHALL mount TV media at `/data/media/tv` inside the container
2. THE System SHALL mount movie media at `/data/media/movies` inside the container
3. WHEN a user sets MEDIA_PATH_TV in .env, THE System SHALL use that host path for TV media
4. WHEN a user sets MEDIA_PATH_MOVIES in .env, THE System SHALL use that host path for movie media
5. THE System SHALL mount media directories as read-only by default

### Requirement 4: Working Directory and Output

**User Story:** As a user, I want to configure where Censorr writes its output and temporary files, so that I can control storage location and persistence.

#### Acceptance Criteria

1. THE System SHALL provide a configurable working directory mount for output files
2. WHEN WORKDIR_PATH is set in .env, THE System SHALL use that host path for the working directory
3. THE System SHALL mount the working directory as read-write
4. WHEN the container restarts, THE System SHALL preserve working directory contents
5. THE System SHALL document recommended permissions for the working directory

### Requirement 5: Environment-Based Configuration

**User Story:** As a user, I want to configure Censorr behavior through environment variables, so that I can customize operation without modifying code.

#### Acceptance Criteria

1. THE System SHALL provide an env.template file documenting all available options
2. WHEN environment variables are set, THE System SHALL pass them to the Censorr CLI
3. THE System SHALL support configuration for timezone, verbosity, and processing options
4. WHEN a user sets UID and GID, THE System SHALL run the container as that user
5. THE System SHALL document the mapping between environment variables and CLI flags

### Requirement 6: Container Naming and Identity

**User Story:** As a user, I want a predictable container name, so that I can easily reference it in commands and monitoring tools.

#### Acceptance Criteria

1. THE System SHALL set the container name to `censorr` in docker-compose.yml
2. THE System SHALL not allow the container name to be configured via .env
3. WHEN the container is running, THE System SHALL be accessible via the name `censorr`
4. WHEN multiple instances are needed, THE System SHALL document how to use Compose project names
5. THE System SHALL fail clearly if a container with the same name already exists

### Requirement 7: Health Checks

**User Story:** As a user, I want Docker to monitor container health, so that I can detect and respond to failures automatically.

#### Acceptance Criteria

1. THE System SHALL provide an optional health check configuration in docker-compose.yml
2. WHEN health checks are enabled, THE System SHALL verify the container is functional
3. THE System SHALL use a simple command-based health check (e.g., `censorr --version`)
4. WHEN the health check fails, THE System SHALL mark the container as unhealthy
5. THE System SHALL document health check configuration options (interval, timeout, retries)

### Requirement 8: Restart Policy

**User Story:** As a user, I want the container to restart automatically after failures or host reboots, so that the service remains available without manual intervention.

#### Acceptance Criteria

1. THE System SHALL set the restart policy to `unless-stopped` by default
2. WHEN the container exits with an error, THE System SHALL restart it automatically
3. WHEN the host reboots, THE System SHALL start the container automatically
4. WHEN a user explicitly stops the container, THE System SHALL not restart it
5. THE System SHALL document how to change the restart policy if needed

### Requirement 9: Resource Constraints

**User Story:** As a user, I want to optionally limit container resource usage, so that Censorr doesn't overwhelm my system during processing.

#### Acceptance Criteria

1. THE System SHALL support optional memory limits via environment configuration
2. THE System SHALL support optional CPU share limits via environment configuration
3. WHEN resource limits are not set, THE System SHALL use all available resources
4. WHEN resource limits are exceeded, THE System SHALL handle the constraint gracefully
5. THE System SHALL document recommended resource limits for typical workloads

### Requirement 10: Logging Strategy

**User Story:** As a user, I want to control how container logs are managed, so that I can balance observability with disk usage.

#### Acceptance Criteria

1. THE System SHALL log to stdout/stderr by default for Docker log driver compatibility
2. THE System SHALL support optional bind-mounted log directory configuration
3. WHEN using Docker's default logging, THE System SHALL respect Docker's log rotation settings
4. WHEN using a bind-mounted log directory, THE System SHALL write structured logs to files
5. THE System SHALL document logging configuration options and trade-offs

### Requirement 11: Idempotent Deployment

**User Story:** As a user, I want to safely re-run `docker compose up` without side effects, so that I can update configuration or verify state without risk.

#### Acceptance Criteria

1. WHEN running `docker compose up` with unchanged configuration, THE System SHALL complete quickly with no changes
2. WHEN configuration changes, THE System SHALL recreate only affected resources
3. WHEN volumes already exist, THE System SHALL reuse them without data loss
4. WHEN the image is already built, THE System SHALL not rebuild unless forced
5. THE System SHALL complete idempotent runs in under 10 seconds

### Requirement 12: Documentation and Examples

**User Story:** As a new user, I want clear documentation and examples, so that I can deploy Censorr successfully on my first attempt.

#### Acceptance Criteria

1. THE System SHALL provide a README section with Docker Compose quickstart instructions
2. THE System SHALL document all environment variables in env.template with descriptions
3. THE System SHALL provide example commands for common operations (build, start, stop, logs)
4. THE System SHALL document integration with Radarr/Sonarr webhook configuration
5. THE System SHALL include troubleshooting guidance for common issues (permissions, paths, FFmpeg)

### Requirement 13: Validation and Error Handling

**User Story:** As a user, I want clear error messages when configuration is invalid, so that I can quickly identify and fix problems.

#### Acceptance Criteria

1. WHEN required host paths don't exist, THE System SHALL fail with a clear error message
2. WHEN volume permissions are incorrect, THE System SHALL fail with guidance on fixing them
3. WHEN the container fails to start, THE System SHALL preserve logs for debugging
4. WHEN environment variables have invalid values, THE System SHALL fail with validation errors
5. THE System SHALL provide a validation script to check configuration before deployment
