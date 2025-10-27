# Container Build Guide

This document provides instructions for building, testing, and publishing Censorr container images with multi-architecture support.

## Prerequisites

- Docker with buildx support
- QEMU for multi-architecture emulation (if building non-native architectures)
- Access to container registry (if publishing)

### Installing QEMU for Multi-Arch Builds

**On Ubuntu/Debian:**
```bash
sudo apt-get update
sudo apt-get install qemu-user-static binfmt-support
```

**On RHEL/CentOS/Fedora:**
```bash
sudo dnf install qemu-user-static
```

**Verify QEMU Installation:**
```bash
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
```

## Basic Build Commands

### Single Architecture Build (Current Platform)
```bash
# Build for current platform
docker build -t censorr:latest .
```

### Multi-Architecture Build Setup

First, create and use a buildx builder instance:
```bash
# Create a new builder instance (Docker)
docker buildx create --name censorr-builder --use --bootstrap

# Verify builder supports multiple platforms
docker buildx inspect --bootstrap
```

### Multi-Architecture Build Commands

#### Build for AMD64 and ARM64
```bash
# Build for multiple architectures (Docker)
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag censorr:latest \
  --tag censorr:1.0.0 \
  .

# To build and push to registry in one step
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --tag your-registry.com/censorr:latest \
  --tag your-registry.com/censorr:1.0.0 \
  --push \
  .
```

## Supported Architectures

The Censorr container supports the following architectures:

- **linux/amd64** - Intel/AMD 64-bit (recommended)
- **linux/arm64** - ARM 64-bit (Apple Silicon, newer ARM servers)

### Architecture Notes

1. **FFmpeg Availability**: Both architectures have FFmpeg packages available in Debian repositories
2. **Python Dependencies**: All Python dependencies (rapidfuzz, pysubs2, etc.) have wheels for both architectures
3. **Performance**: ARM64 builds may have slightly different performance characteristics

## Build Scripts

### Automated Build Script

Create `scripts/build-multi-arch.sh`:
```bash
#!/bin/bash
set -e

VERSION=${1:-latest}
REGISTRY=${2:-localhost}
IMAGE_NAME="censorr"

echo "Building multi-architecture image: ${REGISTRY}/${IMAGE_NAME}:${VERSION}"

# Ensure buildx is available
docker buildx version || {
    echo "Error: docker buildx is required for multi-arch builds"
    exit 1
}

# Create builder if it doesn't exist
if ! docker buildx ls | grep -q censorr-builder; then
    echo "Creating buildx builder..."
    docker buildx create --name censorr-builder --use --bootstrap
else
    docker buildx use censorr-builder
fi

# Build and push
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag "${REGISTRY}/${IMAGE_NAME}:${VERSION}" \
    --tag "${REGISTRY}/${IMAGE_NAME}:latest" \
    ${PUSH:+--push} \
    .

echo "Build complete: ${REGISTRY}/${IMAGE_NAME}:${VERSION}"
```

Usage:
```bash
# Build locally (no push)
./scripts/build-multi-arch.sh v1.0.0 localhost

# Build and push to registry
PUSH=1 ./scripts/build-multi-arch.sh v1.0.0 your-registry.com
```

## Testing Multi-Arch Images

### Local Testing
```bash
# Test AMD64 image
docker run --rm --platform linux/amd64 censorr:latest --help

# Test ARM64 image (on ARM hardware or with QEMU emulation)
docker run --rm --platform linux/arm64 censorr:latest --help
```

### Architecture-Specific Smoke Tests
```bash
#!/bin/bash
# Test script for both architectures

for arch in linux/amd64 linux/arm64; do
    echo "Testing $arch..."
    
    # Basic functionality test
    docker run --rm --platform $arch \
        -v $(pwd)/tests/fixtures:/media:ro \
        -v $(pwd)/test-output:/app/workdir \
        censorr:latest \
        process /media/small-sample.mkv \
        --output /app/workdir \
        --dry-run --verbose
    
    echo "$arch test completed"
done
```

## Registry Publishing

### Docker Hub
```bash
# Login
docker login

# Build and push
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag your-dockerhub-username/censorr:latest \
    --tag your-dockerhub-username/censorr:1.0.0 \
    --push \
    .
```

### GitHub Container Registry
```bash
# Login
echo $GITHUB_TOKEN | docker login ghcr.io -u USERNAME --password-stdin

# Build and push
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag ghcr.io/your-username/censorr:latest \
    --tag ghcr.io/your-username/censorr:1.0.0 \
    --push \
    .
```

### Private Registry
```bash
# Build and push to private registry
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag your-registry.com/censorr:latest \
    --push \
    .
```

## Troubleshooting

### Common Issues

1. **QEMU Not Available**
   ```
   Error: failed to solve: process "/bin/sh" did not complete successfully
   ```
   Solution: Install QEMU user-static and restart Docker daemon

2. **Builder Instance Issues**
   ```bash
   # Remove and recreate builder
   docker buildx rm censorr-builder
   docker buildx create --name censorr-builder --use --bootstrap
   ```

3. **Platform-Specific Build Failures**
   - Check if all dependencies are available for the target architecture
   - Verify base image supports the target platform
   - Review FFmpeg package availability

### Build Performance Tips

1. **Use Docker Layer Caching**: 
   ```bash
   docker buildx build --cache-from type=registry,ref=your-registry.com/censorr:buildcache
   ```

2. **Parallel Builds**: Buildx automatically parallelizes builds across architectures

3. **Local Registry Cache**: Use a local registry for faster rebuilds during development

## CI/CD Integration

Example GitHub Actions workflow for automated multi-arch builds:

```yaml
name: Build Multi-Arch Container

on:
  push:
    tags: ['v*']
  pull_request:
    branches: ['main']

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3
        
      - name: Login to Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
          
      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          platforms: linux/amd64,linux/arm64
          push: true
          tags: |
            ghcr.io/${{ github.repository }}:latest
            ghcr.io/${{ github.repository }}:${{ github.ref_name }}
```

## Healthcheck Configuration

### Current Design: Short-Lived CLI

Censorr is designed as a **short-lived CLI tool** that processes media files and exits. It does not run as a long-running service, therefore **no HEALTHCHECK is configured** in the Dockerfile.

### Future Long-Running Mode Considerations

If a long-running mode is introduced later (e.g., file watcher, web API), consider adding a HEALTHCHECK:

```dockerfile
# Example HEALTHCHECK for future long-running mode
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD censorr --health-check || exit 1
```

### Container Health Validation

For the current CLI mode, validate container health by:

1. **Successful Help Command**:
   ```bash
   docker run --rm censorr:latest --help
   ```

2. **Dry-Run Processing**:
   ```bash
   docker run --rm \
     -v /path/to/test/media:/media:ro \
     -v $(pwd)/test-output:/app/workdir \
     censorr:latest \
     process /media/test-file.mkv --dry-run
   ```

3. **Version Check**:
   ```bash
   docker run --rm censorr:latest --version
   ```

## Update Cadence

- **Base Image**: Monitor python:3.12-slim for security updates monthly
- **Dependencies**: Update Python packages quarterly or when security issues are identified
- **Multi-arch**: Rebuild when base image updates or dependency changes occur

Run `docker scout cves censorr:latest` to check for security vulnerabilities.

## Software Bill of Materials (SBOM)

### Generating SBOM

An SBOM (Software Bill of Materials) provides a detailed inventory of all components in the container image.

#### Using Docker Scout (Recommended)
```bash
# Generate SBOM in SPDX format
docker scout sbom censorr:latest --format spdx --output sbom.spdx.json

# Generate SBOM in CycloneDX format  
docker scout sbom censorr:latest --format cyclonedx --output sbom.cyclonedx.json
```

#### Using Syft
```bash
# Install Syft
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin

# Generate SBOM
syft censorr:latest -o spdx-json=sbom.spdx.json
syft censorr:latest -o cyclonedx-json=sbom.cyclonedx.json
```

#### Using Trivy
```bash
# Install Trivy
sudo apt-get install wget apt-transport-https gnupg lsb-release
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee -a /etc/apt/sources.list.d/trivy.list
sudo apt-get update && sudo apt-get install trivy

# Generate SBOM
trivy image --format spdx-json --output sbom.spdx.json censorr:latest
```

### SBOM Storage

Store generated SBOMs in the `dist/` directory:
```bash
mkdir -p dist/sbom

# Generate all formats
docker scout sbom censorr:latest --format spdx --output dist/sbom/censorr-sbom.spdx.json
docker scout sbom censorr:latest --format cyclonedx --output dist/sbom/censorr-sbom.cyclonedx.json

# Generate for each architecture (if multi-arch)
docker scout sbom --platform linux/amd64 censorr:latest --format spdx --output dist/sbom/censorr-amd64-sbom.spdx.json
docker scout sbom --platform linux/arm64 censorr:latest --format spdx --output dist/sbom/censorr-arm64-sbom.spdx.json
```

### Build Provenance

Generate provenance information for supply chain security:

#### Using Docker Buildkit
```bash
# Build with provenance
docker buildx build \
    --platform linux/amd64,linux/arm64 \
    --tag censorr:latest \
    --provenance=true \
    --sbom=true \
    --metadata-file dist/metadata.json \
    .
```

#### Attestation with Cosign (Advanced)
```bash
# Install Cosign
go install github.com/sigstore/cosign/cmd/cosign@latest

# Generate key pair
cosign generate-key-pair

# Sign image
cosign sign --key cosign.key censorr:latest

# Attest SBOM
cosign attest --predicate sbom.spdx.json --key cosign.key censorr:latest
```

### Automated SBOM Generation Script

Create `scripts/generate-sbom.sh`:
```bash
#!/bin/bash
set -e

IMAGE_NAME=${1:-censorr:latest}
OUTPUT_DIR=${2:-dist/sbom}

echo "Generating SBOM for image: $IMAGE_NAME"

# Create output directory
mkdir -p "$OUTPUT_DIR"

# Generate SBOM using available tools
if command -v docker &> /dev/null && docker scout --help &> /dev/null; then
    echo "Using Docker Scout..."
    docker scout sbom "$IMAGE_NAME" --format spdx --output "$OUTPUT_DIR/sbom.spdx.json"
    docker scout sbom "$IMAGE_NAME" --format cyclonedx --output "$OUTPUT_DIR/sbom.cyclonedx.json"
elif command -v syft &> /dev/null; then
    echo "Using Syft..."
    syft "$IMAGE_NAME" -o spdx-json="$OUTPUT_DIR/sbom.spdx.json"
    syft "$IMAGE_NAME" -o cyclonedx-json="$OUTPUT_DIR/sbom.cyclonedx.json"
elif command -v trivy &> /dev/null; then
    echo "Using Trivy..."
    trivy image --format spdx-json --output "$OUTPUT_DIR/sbom.spdx.json" "$IMAGE_NAME"
else
    echo "Error: No SBOM generation tool available (docker scout, syft, or trivy)"
    exit 1
fi

echo "SBOM generated in: $OUTPUT_DIR"
ls -la "$OUTPUT_DIR"
```

### Security Scanning with SBOM

Use the generated SBOM for security analysis:
```bash
# Scan SBOM for vulnerabilities with Grype
grype sbom:dist/sbom/sbom.spdx.json

# Analyze with OSV Scanner
osv-scanner --sbom dist/sbom/sbom.spdx.json
```