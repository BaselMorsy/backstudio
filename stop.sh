#!/bin/bash

# BackStudio Stop Script
# Stops both backend and frontend servers

echo "🛑 Stopping BackStudio servers..."
echo ""

# Stop backend (port 8000)
if lsof -ti:8000 > /dev/null 2>&1; then
    echo "Stopping backend (port 8000)..."
    lsof -ti:8000 | xargs kill -9 2>/dev/null
    echo "✓ Backend stopped"
else
    echo "✓ Backend not running"
fi

# Stop frontend (port 5173)
if lsof -ti:5173 > /dev/null 2>&1; then
    echo "Stopping frontend (port 5173)..."
    lsof -ti:5173 | xargs kill -9 2>/dev/null
    echo "✓ Frontend stopped"
else
    echo "✓ Frontend not running"
fi

echo ""
echo "✅ All servers stopped"
