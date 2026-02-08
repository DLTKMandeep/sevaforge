#!/bin/bash
# ForgeFlow Mac Setup Script

set -e

echo "========================================"
echo "ForgeFlow Mac Setup"
echo "========================================"
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo "Detected Python: $PYTHON_VERSION"

# Check if we're in the right directory
if [ ! -f "mcp-config.yaml" ]; then
    echo "❌ Error: Please run this script from the forgeflow directory"
    exit 1
fi

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

# Run installation test
echo ""
echo "Running installation test..."
python3 scripts/test_installation.py

echo ""
echo "========================================"
echo "Setup Complete!"
echo "========================================"
echo ""
echo "To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "To test ForgeFlow, run:"
echo "  python3 cli/forgeflow.py --help"
echo ""
echo "To run discovery on current directory:"
echo "  python3 cli/forgeflow.py discover ."
echo ""
