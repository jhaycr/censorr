# Dockerfile for Censorr CLI/Worker image (with ffmpeg)

# ---------- Builder: build wheel ----------
FROM python:3.12-slim AS builder

WORKDIR /build

# Tools to build a wheel
RUN python -m pip install --no-cache-dir --upgrade pip==24.3.1 build==1.2.2

# Copy only what is needed to build the package
COPY pyproject.toml ./
COPY src ./src

# Build a wheel for the project (dependencies are resolved at install time)
RUN python -m build --wheel --outdir /dist

# ---------- Runtime: slim with ffmpeg ----------
FROM python:3.12-slim

# Install ffmpeg only; keep image minimal
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    && apt-get autoremove -y \
    && rm -rf /tmp/* /var/tmp/* /var/cache/apt/archives/*

# Create non-root user matching compose (UID:GID 1000:1000)
RUN groupadd -g 1000 censorr && useradd -u 1000 -g censorr -m -s /bin/bash censorr

WORKDIR /app

# Copy code (module entry points rely on src.*) and wheel artifact
COPY --chown=censorr:censorr src/ ./src/
COPY --from=builder /dist /tmp/dist

# Install the built package from wheel (non-editable) with no cache
RUN python -m pip install --no-cache-dir /tmp/dist/*.whl \
    && rm -rf /tmp/dist \
    && mkdir -p /app/workdir /app/config \
    && chown -R censorr:censorr /app

# Environment
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Entrypoint
COPY --chown=censorr:censorr docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as root to initialize queue volume; worker runs as root unless dropped in entrypoint
USER root

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["worker"]