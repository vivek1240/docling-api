#!/bin/bash
# =============================================================================
# Lightning.AI Deployment Script
# =============================================================================
#
# Deploys the Docling service to Lightning.AI with GPU support.
#
# Prerequisites:
#   - Lightning CLI installed: pip install lightning
#   - Lightning.AI account and authentication
#
# Usage:
#   ./scripts/deploy_lightning.sh
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="$PROJECT_DIR/deployments/lightning/lightning.yaml"

echo "🚀 Deploying Docling to Lightning.AI..."
echo "   Config: $CONFIG_FILE"
echo ""

# Check if lightning CLI is installed
if ! command -v lightning &> /dev/null; then
    echo "❌ Error: Lightning CLI not found"
    echo "   Install with: pip install lightning"
    exit 1
fi

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "❌ Error: Config file not found: $CONFIG_FILE"
    exit 1
fi

# Check authentication
echo "🔐 Checking Lightning.AI authentication..."
if ! lightning whoami &> /dev/null; then
    echo "⚠️  Not authenticated. Running 'lightning login'..."
    lightning login
fi

# Deploy
echo ""
echo "📦 Deploying service..."
lightning deploy "$CONFIG_FILE"

# Get status
echo ""
echo "📊 Deployment status:"
lightning list

echo ""
echo "✅ Deployment complete!"
echo ""
echo "📝 Next steps:"
echo "   1. Note your service endpoint URL from the list above"
echo "   2. Test with: curl https://<your-endpoint>/health"
echo "   3. Access UI at: https://<your-endpoint>/ui"
echo ""
