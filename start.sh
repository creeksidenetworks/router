#!/bin/bash

# Router Project - Python Environment Setup Script
# This script creates/prepares a Python virtual environment and activates it

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_NAME="router"
VENV_DIR="${SCRIPT_DIR}/venv"

echo "=========================================="
echo "Setting up Python environment for: $PROJECT_NAME"
echo "=========================================="
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Found Python version: $PYTHON_VERSION"
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment at: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created successfully."
    echo ""
else
    echo "Virtual environment already exists at: $VENV_DIR"
    echo ""
fi

# Upgrade pip, setuptools, and wheel
echo "Upgrading pip, setuptools, and wheel..."
"${VENV_DIR}/bin/pip" install --upgrade pip setuptools wheel > /dev/null 2>&1
echo "Done."
echo ""

# Install required packages
echo "Installing required Python packages..."
"${VENV_DIR}/bin/pip" install --upgrade \
    requests \
    paramiko \
    simple-term-menu \
    validators \
    pytz \
    cryptography \
    packaging \
    > /dev/null 2>&1
echo "Packages installed successfully."
echo ""

# Activation instructions
echo "=========================================="
echo "✓ Environment setup complete!"
echo "=========================================="
echo ""
echo "To activate the virtual environment, run:"
echo "  source ${VENV_DIR}/bin/activate"
echo ""
echo "To deactivate, run:"
echo "  deactivate"
echo ""
echo "To run the router script directly:"
echo "  ${VENV_DIR}/bin/python router.py <hostname> [options]"
echo ""

# Optionally activate the environment
echo "Activate the virtual environment by running the following command:"
echo ""
echo "source ${VENV_DIR}/bin/activate"

