#!/bin/bash

# BackStudio Startup Script
# Starts both backend and frontend servers
# Supports uv, pip, and conda

set -e

echo "🚀 BackStudio Startup Script"
echo "============================"
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

# Function to check if a port is in use
port_in_use() {
    lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1
}

# Detect package manager from setup
PACKAGE_MANAGER="uv"  # Default
if [ -f ".package_manager" ]; then
    PACKAGE_MANAGER=$(cat .package_manager)
fi

echo -e "${BLUE}[1/4]${NC} Checking environment..."
echo "Package manager: $PACKAGE_MANAGER"

# Check for Node.js
if ! command_exists node; then
    echo -e "${RED}Error: Node.js is not installed${NC}"
    echo "Please run ./setup.sh first"
    exit 1
fi
echo -e "${GREEN}✓ Node.js is installed${NC}"
echo ""

# Check for ports
echo -e "${BLUE}[2/4]${NC} Checking ports..."
if port_in_use 8000; then
    echo -e "${YELLOW}⚠ Warning: Port 8000 is already in use (backend)${NC}"
    echo "Kill the process or the backend won't start"
fi
if port_in_use 5173; then
    echo -e "${YELLOW}⚠ Warning: Port 5173 is already in use (frontend)${NC}"
    echo "Kill the process or the frontend won't start"
fi
echo ""

# Create logs directory
mkdir -p "$SCRIPT_DIR/logs"

# Determine how to start the backend based on package manager
echo -e "${BLUE}[3/4]${NC} Starting backend server..."
cd "$SCRIPT_DIR"

if [ "$PACKAGE_MANAGER" = "uv" ]; then
    # Start with uv
    uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 > "$SCRIPT_DIR/logs/backend.log" 2>&1 &
    BACKEND_PID=$!
    
elif [ "$PACKAGE_MANAGER" = "pip" ]; then
    # Activate venv and start
    source venv/bin/activate
    python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 > "$SCRIPT_DIR/logs/backend.log" 2>&1 &
    BACKEND_PID=$!
    
elif [ "$PACKAGE_MANAGER" = "conda" ]; then
    # Use conda environment
    echo -e "${YELLOW}Note: Ensure conda environment 'backstudio' is activated${NC}"
    eval "$(conda shell.bash hook)" 2>/dev/null || true
    conda activate backstudio 2>/dev/null || true
    python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 > "$SCRIPT_DIR/logs/backend.log" 2>&1 &
    BACKEND_PID=$!
fi

echo -e "${GREEN}✓ Backend started (PID: $BACKEND_PID)${NC}"

# Wait a moment for backend to start
sleep 2

# Start frontend
echo -e "${BLUE}[4/4]${NC} Starting frontend server..."
cd "$FRONTEND_DIR"
npm run dev -- --host 0.0.0.0 > "$SCRIPT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}✓ Frontend started (PID: $FRONTEND_PID)${NC}"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down servers...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo -e "${GREEN}✓ Servers stopped${NC}"
    exit 0
}

# Set trap to cleanup on Ctrl+C
trap cleanup SIGINT SIGTERM

echo ""
echo -e "${GREEN}╔════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   BackStudio is Running! 🎉           ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════╝${NC}"
echo ""
echo "📊 Access points:"
echo "   Frontend:     http://localhost:5173"
echo "   Backend API:  http://localhost:8000"
echo "   API Docs:     http://localhost:8000/docs"
echo ""
echo "📝 Logs:"
echo "   Backend:  tail -f $SCRIPT_DIR/logs/backend.log"
echo "   Frontend: tail -f $SCRIPT_DIR/logs/frontend.log"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Tail logs from both servers
tail -f "$SCRIPT_DIR/logs/backend.log" "$SCRIPT_DIR/logs/frontend.log"
