#!/bin/bash
# Podman run examples for Censorr container
# Equivalent to Docker Compose examples but using podman run commands

set -e

# Configuration
MEDIA_DIR="/home/josh/Videos"
WORKDIR="./workdir"
CONFIG_DIR="./config"
FINAL_DIR="./final"
IMAGE_NAME="censorr:latest"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Censorr Podman Examples${NC}"
echo "=========================="

# Function to build image if it doesn't exist
build_image_if_needed() {
    if ! podman image exists $IMAGE_NAME; then
        echo -e "${YELLOW}Building Censorr image...${NC}"
        podman build -t $IMAGE_NAME ..
    else
        echo -e "${GREEN}Using existing image: $IMAGE_NAME${NC}"
    fi
}

# Function to create directories
setup_directories() {
    echo -e "${YELLOW}Setting up directories...${NC}"
    mkdir -p "$WORKDIR" "$CONFIG_DIR" "$FINAL_DIR"
    
    # Set proper permissions (matching container UID/GID 10001)
    # Note: This may require sudo depending on your system
    # sudo chown -R 10001:10001 "$WORKDIR" "$FINAL_DIR"
}

# Example 1: Dry-run with subtitle processing
dry_run_example() {
    echo -e "${GREEN}Example 1: Dry-run with subtitle processing${NC}"
    echo "=============================================="
    
    podman run --rm \
        --user 10001:10001 \
        --security-opt label=disable \
        -v "${MEDIA_DIR}:/media:ro,Z" \
        -v "$(pwd)/${WORKDIR}:/app/workdir:Z" \
        -v "$(pwd)/${CONFIG_DIR}:/app/config:ro,Z" \
        -e PYTHONUNBUFFERED=1 \
        -e CENSORR_VERBOSE=true \
        $IMAGE_NAME \
        process "/media/bullet_train_backup.mkv" \
        --output /app/workdir \
        --language en \
        --create-subtitle-sidecar \
        --continue-on-qc-fail \
        --dry-run \
        --verbose
}

# Example 2: Full processing pipeline
full_processing_example() {
    echo -e "${GREEN}Example 2: Full processing pipeline${NC}"
    echo "===================================="
    
    podman run --rm \
        --user 10001:10001 \
        --security-opt label=disable \
        -v "${MEDIA_DIR}:/media:ro,Z" \
        -v "$(pwd)/${WORKDIR}:/app/workdir:Z" \
        -v "$(pwd)/${CONFIG_DIR}:/app/config:ro,Z" \
        -v "$(pwd)/${FINAL_DIR}:/app/workdir/final:Z" \
        -e PYTHONUNBUFFERED=1 \
        -e PYTHONDONTWRITEBYTECODE=1 \
        $IMAGE_NAME \
        process "/media/bullet_train_backup.mkv" \
        --output /app/workdir \
        --language en \
        --exclude-sdh \
        --create-subtitle-sidecar \
        --sidecar-tag clean \
        --final-dest /app/workdir/final \
        --operations subtitle_extract,subtitle_merge,subtitle_mask,audio_extract,audio_mute,audio_qc,subtitle_qc,video_remux \
        --verbose
}

# Example 3: Subtitle-only processing
subtitle_only_example() {
    echo -e "${GREEN}Example 3: Subtitle-only processing${NC}"
    echo "==================================="
    
    podman run --rm \
        --user 10001:10001 \
        --security-opt label=disable \
        -v "${MEDIA_DIR}:/media:ro,Z" \
        -v "$(pwd)/${WORKDIR}:/app/workdir:Z" \
        -v "$(pwd)/${CONFIG_DIR}:/app/config:ro,Z" \
        -e PYTHONUNBUFFERED=1 \
        $IMAGE_NAME \
        process "/media/bullet_train_backup.mkv" \
        --output /app/workdir \
        --language en \
        --operations subtitle_extract,subtitle_mask,sidecar_export \
        --create-subtitle-sidecar \
        --sidecar-tag censorr \
        --verbose
}

# Example 4: Using custom configuration files
custom_config_example() {
    echo -e "${GREEN}Example 4: Using custom configuration files${NC}"
    echo "============================================="
    
    # Create sample config files if they don't exist
    if [ ! -f "$CONFIG_DIR/profanity.json" ]; then
        echo '{"terms": ["damn", "hell", "shit"], "allowlist": ["hell'\''s kitchen", "what the hell"]}' > "$CONFIG_DIR/profanity.json"
    fi
    
    if [ ! -f "$CONFIG_DIR/selectors.json" ]; then
        cat > "$CONFIG_DIR/selectors.json" << 'EOF'
[
    {
        "track_type": "SUBTITLE",
        "language": "en",
        "title_include": ["full", "forced"],
        "title_exclude": ["sdh", "hi", "cc"]
    }
]
EOF
    fi
    
    podman run --rm \
        --user 10001:10001 \
        --security-opt label=disable \
        -v "${MEDIA_DIR}:/media:ro,Z" \
        -v "$(pwd)/${WORKDIR}:/app/workdir:Z" \
        -v "$(pwd)/${CONFIG_DIR}:/app/config:ro,Z" \
        -e PYTHONUNBUFFERED=1 \
        $IMAGE_NAME \
        process "/media/bullet_train_backup.mkv" \
        --output /app/workdir \
        --profanity-list-file /app/config/profanity.json \
        --selectors-file /app/config/selectors.json \
        --dry-run \
        --verbose
}

# Example 5: Help and version information
help_example() {
    echo -e "${GREEN}Example 5: Help and version information${NC}"
    echo "======================================="
    
    echo -e "${YELLOW}Showing help:${NC}"
    podman run --rm $IMAGE_NAME --help
    
    echo -e "${YELLOW}Showing version:${NC}"
    podman run --rm $IMAGE_NAME --version
}

# Main execution
case "${1:-all}" in
    "build")
        build_image_if_needed
        ;;
    "setup")
        setup_directories
        ;;
    "dry-run")
        build_image_if_needed
        setup_directories
        dry_run_example
        ;;
    "full")
        build_image_if_needed
        setup_directories
        full_processing_example
        ;;
    "subtitles")
        build_image_if_needed
        setup_directories
        subtitle_only_example
        ;;
    "config")
        build_image_if_needed
        setup_directories
        custom_config_example
        ;;
    "help")
        build_image_if_needed
        help_example
        ;;
    "all")
        echo -e "${YELLOW}Running all examples...${NC}"
        build_image_if_needed
        setup_directories
        echo ""
        dry_run_example
        echo ""
        subtitle_only_example
        echo ""
        custom_config_example
        echo ""
        help_example
        ;;
    *)
        echo "Usage: $0 [build|setup|dry-run|full|subtitles|config|help|all]"
        echo ""
        echo "Examples:"
        echo "  $0 build      - Build the Censorr container image"
        echo "  $0 setup      - Create required directories"
        echo "  $0 dry-run    - Run dry-run example"
        echo "  $0 full       - Run full processing example"
        echo "  $0 subtitles  - Run subtitle-only example"
        echo "  $0 config     - Run example with custom config files"
        echo "  $0 help       - Show container help and version"
        echo "  $0 all        - Run all examples (default)"
        exit 1
        ;;
esac

echo -e "${GREEN}Done!${NC}"