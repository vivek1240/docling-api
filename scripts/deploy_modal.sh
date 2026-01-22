#!/bin/bash
# =============================================================================
# Modal Deployment Script
# =============================================================================
#
# Deploys the Docling service to Modal for serverless GPU processing.
#
# Prerequisites:
#   - Modal CLI installed: pip install modal
#   - Modal account and authentication: modal token new
#
# Usage:
#   ./scripts/deploy_modal.sh
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODAL_FILE="$PROJECT_DIR/deployments/modal/modal_docling.py"

echo "🚀 Deploying Docling to Modal..."
echo "   File: $MODAL_FILE"
echo ""

# Check if modal CLI is installed
if ! command -v modal &> /dev/null; then
    echo "❌ Error: Modal CLI not found"
    echo "   Install with: pip install modal"
    exit 1
fi

# Check if modal file exists
if [ ! -f "$MODAL_FILE" ]; then
    echo "❌ Error: Modal file not found: $MODAL_FILE"
    exit 1
fi

# Check authentication
echo "🔐 Checking Modal authentication..."
if ! modal token info &> /dev/null 2>&1; then
    echo "⚠️  Not authenticated. Running 'modal token new'..."
    modal token new
fi

# Create secrets if needed (optional)
echo ""
echo "📦 Checking Modal secrets..."
if ! modal secret list | grep -q "docling-secrets"; then
    echo "   Creating docling-secrets (empty placeholder)..."
    modal secret create docling-secrets || true
fi

# Deploy
echo ""
echo "📦 Deploying to Modal..."
modal deploy "$MODAL_FILE"

# Test
echo ""
echo "🧪 Testing deployment..."
modal run "$MODAL_FILE" --url "https://arxiv.org/pdf/2501.17887" || echo "   Test completed (check output above)"

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Get your endpoint URL from Modal dashboard: https://modal.com"
echo "   2. Use the web endpoint for HTTP access"
echo "   3. Or call functions directly from Python using Modal client"
echo ""
