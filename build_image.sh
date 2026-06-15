#!/usr/bin/env bash
# Helper script to build the Zalopay Issue Analytics Agent Docker image
# Automatically loads HF_TOKEN from .env and passes it as a build-arg
set -e

# Change directory to the script's directory (agent root)
cd "$(dirname "$0")"

# Load environment variables from .env if it exists
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    # Extract only valid key=value pairs, ignoring comments and empty lines
    export $(grep -E '^[^#].*=' .env | xargs)
fi

# Setup Repository details
REPO_NAME="111480-abp111948"
REGISTRY_URL="vcr.vngcloud.vn"
IMAGE_NAME="ai-chay-bang-com-agent"

# Generate a timestamp-based version tag
TAG="v$(date +%Y%m%d%H%M%S)"
FULL_IMAGE="${REGISTRY_URL}/${REPO_NAME}/${IMAGE_NAME}:${TAG}"

echo "======================================================="
echo "Building Image : ${FULL_IMAGE}"
echo "Platform       : linux/amd64"
echo "======================================================="

# Run docker build with HF_TOKEN build-arg if configured
if [ -z "$HF_TOKEN" ]; then
    echo "⚠️  HF_TOKEN is not set in .env. Building without token..."
    docker build --platform linux/amd64 -t "${FULL_IMAGE}" .
else
    echo "🔑 HF_TOKEN detected. Passing as build-arg..."
    docker build --platform linux/amd64 --build-arg HF_TOKEN="${HF_TOKEN}" -t "${FULL_IMAGE}" .
fi

echo "======================================================="
echo "✅ Build Complete: ${FULL_IMAGE}"
echo "======================================================="
echo "To push the built image to the registry, run:"
echo "  docker push ${FULL_IMAGE}"
echo "======================================================="
echo "To deploy/update the runtime with the new image tag:"
echo "  ./build_image.sh to build, then push, then update on AgentBase."
