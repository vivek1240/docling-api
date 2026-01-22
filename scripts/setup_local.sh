#!/bin/bash
# =============================================================================
# Local Development Setup Script
# =============================================================================
#
# Sets up the local development environment with Docker.
#
# Prerequisites:
#   - Docker and Docker Compose installed
#   - NVIDIA Container Toolkit (for GPU support)
#
# Usage:
#   ./scripts/setup_local.sh [--cpu]
#
# Options:
#   --cpu   Use CPU-only configuration (no GPU required)
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$PROJECT_DIR/deployments/docker"

# Parse arguments
USE_CPU=false
if [ "$1" == "--cpu" ]; then
    USE_CPU=true
fi

echo "🚀 Setting up local development environment..."
echo "   Project: $PROJECT_DIR"
echo "   Mode: $([ "$USE_CPU" == true ] && echo 'CPU' || echo 'GPU')"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Error: Docker not found"
    echo "   Install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    echo "❌ Error: Docker Compose not found"
    exit 1
fi

# Check GPU (if not using CPU mode)
if [ "$USE_CPU" == false ]; then
    echo "🔍 Checking GPU availability..."
    if ! docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi &> /dev/null; then
        echo "⚠️  Warning: GPU not available or NVIDIA Container Toolkit not installed"
        echo "   Switching to CPU mode..."
        USE_CPU=true
    else
        echo "   GPU detected ✓"
    fi
fi

# Create .env if not exists
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo ""
    echo "📝 Creating .env file from template..."
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
    
    # Generate a random secret key
    SECRET_KEY=$(openssl rand -hex 32)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/your-secret-key-change-in-production/$SECRET_KEY/" "$PROJECT_DIR/.env"
    else
        sed -i "s/your-secret-key-change-in-production/$SECRET_KEY/" "$PROJECT_DIR/.env"
    fi
    echo "   Generated secret key"
fi

# Set compose file
if [ "$USE_CPU" == true ]; then
    COMPOSE_FILE="$DOCKER_DIR/docker-compose.cpu.yml"
else
    COMPOSE_FILE="$DOCKER_DIR/docker-compose.yml"
fi

echo ""
echo "📦 Pulling Docker images..."
docker compose -f "$COMPOSE_FILE" pull

echo ""
echo "🏗️  Building API service..."
docker compose -f "$COMPOSE_FILE" build api 2>/dev/null || echo "   (API service will be built on first start)"

echo ""
echo "🚀 Starting services..."
docker compose -f "$COMPOSE_FILE" up -d

echo ""
echo "⏳ Waiting for services to be healthy..."
sleep 10

# Check health
echo ""
echo "🔍 Checking service health..."

# Check Docling
if curl -s http://localhost:5001/health | grep -q "healthy\|ok"; then
    echo "   ✓ Docling backend is healthy"
else
    echo "   ⚠ Docling backend may still be starting..."
fi

# Check API
if curl -s http://localhost:8000/health | grep -q "healthy\|ok"; then
    echo "   ✓ API service is healthy"
else
    echo "   ⚠ API service may still be starting..."
fi

echo ""
echo "✅ Local setup complete!"
echo ""
echo "📝 Services running:"
echo "   • Docling Backend: http://localhost:5001"
echo "   • Docling UI:      http://localhost:5001/ui"
echo "   • API Service:     http://localhost:8000"
echo "   • API Docs:        http://localhost:8000/docs"
echo ""
echo "📝 Quick start:"
echo "   1. Create an API key:"
echo "      curl -X POST http://localhost:8000/v1/keys \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{\"name\": \"Test Key\", \"credits\": 1000}'"
echo ""
echo "   2. Convert a document:"
echo "      curl -X POST http://localhost:8000/v1/convert/source \\"
echo "        -H 'Authorization: Bearer YOUR_API_KEY' \\"
echo "        -H 'Content-Type: application/json' \\"
echo "        -d '{\"sources\": [{\"kind\": \"http\", \"url\": \"https://arxiv.org/pdf/2501.17887\"}]}'"
echo ""
echo "📝 Useful commands:"
echo "   • View logs:  docker compose -f $COMPOSE_FILE logs -f"
echo "   • Stop:       docker compose -f $COMPOSE_FILE down"
echo "   • Restart:    docker compose -f $COMPOSE_FILE restart"
echo ""
