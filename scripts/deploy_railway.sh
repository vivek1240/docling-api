#!/bin/bash
# =============================================================================
# Railway Deployment Script
# =============================================================================
#
# Deploys the DocProcess API to Railway with PostgreSQL database.
#
# Prerequisites:
#   - Railway CLI installed: brew install railway
#   - Railway authentication: railway login
#
# Usage:
#   ./scripts/deploy_railway.sh
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚂 Railway Deployment Script${NC}"
echo "=================================="
echo ""

cd "$PROJECT_DIR"

# Check if railway CLI is installed
if ! command -v railway &> /dev/null; then
    echo -e "${RED}❌ Error: Railway CLI not found${NC}"
    echo "   Install with: brew install railway"
    exit 1
fi

# Check if logged in
echo -e "${YELLOW}🔐 Checking Railway authentication...${NC}"
if ! railway whoami &> /dev/null; then
    echo -e "${YELLOW}⚠️  Not authenticated. Please run 'railway login' first${NC}"
    echo ""
    echo "Run this command in your terminal:"
    echo "  railway login"
    echo ""
    echo "Then run this script again."
    exit 1
fi

RAILWAY_USER=$(railway whoami 2>/dev/null)
echo -e "${GREEN}✓ Logged in as: $RAILWAY_USER${NC}"
echo ""

# Check if project already exists
if railway status &> /dev/null 2>&1; then
    echo -e "${YELLOW}📁 Found existing Railway project${NC}"
    read -p "   Use existing project? (y/n): " USE_EXISTING
    if [[ "$USE_EXISTING" != "y" ]]; then
        echo "   Please run 'railway unlink' first to start fresh"
        exit 1
    fi
else
    # Initialize new project
    echo -e "${BLUE}📦 Creating new Railway project...${NC}"
    railway init --name docprocess-api
    echo -e "${GREEN}✓ Project created${NC}"
fi

echo ""

# Add PostgreSQL database
echo -e "${BLUE}🗄️  Adding PostgreSQL database...${NC}"
if railway add --database postgres 2>/dev/null; then
    echo -e "${GREEN}✓ PostgreSQL added${NC}"
else
    echo -e "${YELLOW}⚠️  PostgreSQL may already exist (continuing...)${NC}"
fi

echo ""

# Set environment variables
echo -e "${BLUE}🔧 Setting environment variables...${NC}"

# Generate secret key
SECRET_KEY=$(openssl rand -hex 32)

# Modal endpoint (your deployed Modal service)
MODAL_ENDPOINT="https://vivek12345singh--docling-service-convert-endpoint.modal.run"

railway variables set \
    API_DEBUG=false \
    API_TITLE="DocProcess API" \
    API_VERSION="1.0.0" \
    API_SECRET_KEY="$SECRET_KEY" \
    DOCLING_USE_MODAL=true \
    DOCLING_MODAL_ENDPOINT="$MODAL_ENDPOINT" \
    DOCLING_TIMEOUT=300 \
    LOG_LEVEL=INFO \
    RATE_LIMIT_ENABLED=true \
    RATE_LIMIT_REQUESTS_PER_MINUTE=60

echo -e "${GREEN}✓ Environment variables set${NC}"
echo ""

# Deploy
echo -e "${BLUE}🚀 Deploying to Railway...${NC}"
echo "   (This may take 2-5 minutes)"
echo ""

railway up --detach

echo ""
echo -e "${GREEN}✓ Deployment initiated!${NC}"
echo ""

# Wait a moment for deployment to register
sleep 5

# Generate domain if not exists
echo -e "${BLUE}🌐 Setting up domain...${NC}"
DOMAIN=$(railway domain 2>/dev/null || echo "")

if [ -z "$DOMAIN" ]; then
    echo -e "${YELLOW}⚠️  Generating domain...${NC}"
    railway domain
    DOMAIN=$(railway domain 2>/dev/null)
fi

echo ""
echo "=================================="
echo -e "${GREEN}🎉 Deployment Complete!${NC}"
echo "=================================="
echo ""
echo -e "${BLUE}📍 Your API Endpoints:${NC}"
echo ""
echo "   Base URL:    https://$DOMAIN"
echo "   Health:      https://$DOMAIN/health"
echo "   API Docs:    https://$DOMAIN/docs"
echo ""
echo -e "${BLUE}🔧 Useful Commands:${NC}"
echo ""
echo "   View logs:     railway logs"
echo "   View status:   railway status"
echo "   Open dashboard: railway open"
echo "   View variables: railway variables"
echo ""
echo -e "${BLUE}📝 Quick Test:${NC}"
echo ""
echo "   # Create an API key"
echo "   curl -X POST https://$DOMAIN/v1/keys \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"name\": \"Test Key\", \"credits\": 1000}'"
echo ""
echo -e "${YELLOW}⏳ Note: First deployment may take 2-5 minutes to be fully ready.${NC}"
echo "   Check status with: railway logs -f"
echo ""
