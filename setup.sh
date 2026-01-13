#!/bin/bash

# BackStudio Setup Script
# Supports uv, pip, and conda for Python dependency management

set -e

echo "🎨 BackStudio Setup Script"
echo "==========================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

echo -e "${BLUE}[1/5]${NC} Checking prerequisites..."
echo ""

# Check for Node.js
if ! command_exists node; then
    echo -e "${RED}Error: Node.js is not installed${NC}"
    echo "Please install Node.js 16+ from https://nodejs.org/"
    exit 1
fi
echo -e "${GREEN}✓ Node.js is installed ($(node --version))${NC}"

# Check for Python
if ! command_exists python3 && ! command_exists python; then
    echo -e "${RED}Error: Python is not installed${NC}"
    echo "Please install Python 3.11+ from https://www.python.org/"
    exit 1
fi

PYTHON_CMD=$(command_exists python3 && echo "python3" || echo "python")
PYTHON_VERSION=$($PYTHON_CMD --version | cut -d' ' -f2)
echo -e "${GREEN}✓ Python is installed ($PYTHON_VERSION)${NC}"
echo ""

# Ask user which package manager to use
echo -e "${BLUE}[2/5]${NC} Choose Python package manager:"
echo "  1) uv (recommended - fastest)"
echo "  2) pip (standard)"
echo "  3) conda (if using Anaconda/Miniconda)"
echo ""
read -p "Enter choice [1-3]: " pm_choice

case $pm_choice in
    1)
        PACKAGE_MANAGER="uv"
        ;;
    2)
        PACKAGE_MANAGER="pip"
        ;;
    3)
        PACKAGE_MANAGER="conda"
        ;;
    *)
        echo -e "${YELLOW}Invalid choice. Defaulting to pip.${NC}"
        PACKAGE_MANAGER="pip"
        ;;
esac

echo ""
echo -e "${BLUE}[3/5]${NC} Setting up Python environment with $PACKAGE_MANAGER..."
cd "$SCRIPT_DIR"

if [ "$PACKAGE_MANAGER" = "uv" ]; then
    # Check if uv is installed
    if ! command_exists uv; then
        echo -e "${YELLOW}uv not found. Installing uv...${NC}"
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
    
    # Create .python-version file
    echo "3.11" > .python-version
    
    # Sync dependencies
    echo "Syncing dependencies with uv..."
    uv sync
    
    echo -e "${GREEN}✓ Python environment ready (uv)${NC}"
    
elif [ "$PACKAGE_MANAGER" = "pip" ]; then
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        echo "Creating virtual environment..."
        $PYTHON_CMD -m venv venv
    fi
    
    # Activate virtual environment
    source venv/bin/activate
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install dependencies
    echo "Installing dependencies..."
    pip install -r backend/requirements.txt
    
    echo -e "${GREEN}✓ Python environment ready (pip)${NC}"
    
elif [ "$PACKAGE_MANAGER" = "conda" ]; then
    # Check if conda is installed
    if ! command_exists conda; then
        echo -e "${RED}Error: conda is not installed${NC}"
        echo "Please install Anaconda or Miniconda from https://docs.conda.io/"
        exit 1
    fi
    
    # Check if environment exists
    if conda env list | grep -q "backstudio"; then
        echo "backstudio environment already exists. Activating..."
        eval "$(conda shell.bash hook)"
        conda activate backstudio
    else
        echo "Creating conda environment..."
        conda create -n backstudio python=3.11 -y
        eval "$(conda shell.bash hook)"
        conda activate backstudio
    fi
    
    # Install dependencies
    echo "Installing dependencies..."
    pip install -r backend/requirements.txt
    
    echo -e "${GREEN}✓ Python environment ready (conda)${NC}"
fi

# Save the package manager choice for start script
echo "$PACKAGE_MANAGER" > .package_manager

echo ""
echo -e "${BLUE}[4/5]${NC} Installing frontend dependencies..."
cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
    echo "Running npm install..."
    npm install
else
    echo "Dependencies already installed"
fi

echo -e "${GREEN}✓ Frontend dependencies ready${NC}"
echo ""

# Create necessary directories
echo -e "${BLUE}[5/5]${NC} Creating project directories..."
cd "$SCRIPT_DIR"
mkdir -p workspace logs

echo -e "${GREEN}✓ Directories created${NC}"
echo ""

echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Setup Complete! 🎉                  ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo "Package manager: $PACKAGE_MANAGER"
echo ""
echo "Next steps:"
echo "  1. Run ./start.sh to start BackStudio"
echo "  2. Open http://localhost:5173 in your browser"
echo "  3. Check http://localhost:8000/docs for API documentation"
echo ""

if [ "$PACKAGE_MANAGER" = "conda" ]; then
    echo -e "${YELLOW}Note: For conda, you'll need to activate the environment:${NC}"
    echo "  conda activate backstudio"
    echo ""
fi
