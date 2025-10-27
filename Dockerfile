# Dockerfile for Censorr - Plex/Arr Clean Censor Tool
# Multi-stage build for minimal, secure container image

# Build stage - Use specific tag for better reproducibility  
FROM python:3.12-slim AS builder

# Install build dependencies and clean up in single layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root build user
RUN groupadd -g 1000 censorr && useradd -u 1000 -g censorr -m censorr

WORKDIR /build

# Upgrade pip and install build tools
RUN python -m pip install --no-cache-dir --upgrade pip==24.3.1 setuptools==75.8.0 wheel==0.46.0

# Install Python dependencies with pinned versions for reproducibility
COPY pyproject.toml .
RUN python -m pip install --no-cache-dir \
    rapidfuzz==3.14.1 \
    pysubs2==1.8.0 \
    pydantic==2.11.9 \
    typer[all]==0.19.1 \
    PyYAML==6.0.2 \
    rich==14.1.0 \
    gunicorn==23.0.0

# Runtime stage - Use same base for consistency
FROM python:3.12-slim

# Install runtime dependencies and clean up in single layer
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    wget \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get autoremove -y \
    && rm -rf /tmp/* /var/tmp/*

# Create non-root user with specific UID/GID for security
RUN groupadd -g 1000 censorr && \
    useradd -u 1000 -g censorr -m -s /bin/bash censorr

# Copy Python packages from builder (minimal transfer)
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Set working directory
WORKDIR /app

# Copy application code with proper ownership
COPY --chown=censorr:censorr src/ ./src/
COPY --chown=censorr:censorr pyproject.toml ./
COPY --chown=censorr:censorr README.md ./

# Install the package and create directories as root, then fix permissions
RUN python -m pip install --no-cache-dir -e . && \
    mkdir -p /app/workdir /app/config && \
    chown -R censorr:censorr /app && \
    # Remove pip cache and temporary files
    rm -rf /root/.cache/pip /tmp/* /var/tmp/*

# Switch to non-root user early for security  
USER censorr

# Verify non-root user
RUN id && whoami

# Set environment variables for security and performance
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Expose expected volume mount points in labels
LABEL org.opencontainers.image.title="Censorr"
LABEL org.opencontainers.image.description="Plex/Arr Clean Censor Tool for media processing"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.source="https://github.com/user/censorr"
LABEL org.opencontainers.image.licenses="MIT"

# Document expected volumes
VOLUME ["/media", "/app/workdir", "/app/config"]

# Copy entrypoint script and set it
COPY --chown=censorr:censorr docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
# Default to daemon to stay running (can override with CLI args)
CMD ["daemon"]