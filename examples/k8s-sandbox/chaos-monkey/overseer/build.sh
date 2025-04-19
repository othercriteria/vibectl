#!/usr/bin/env bash
set -e

# Chaos Monkey Overseer Build Script
# This script builds the Docker image for the overseer component.

# Default to non-verbose mode
VERBOSE=false
DEBUG_TAG=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --verbose|-v)
      VERBOSE=true
      shift
      ;;
    --debug|-d)
      DEBUG_TAG=true
      shift
      ;;
    --help|-h)
      echo "Usage: $0 [options]"
      echo ""
      echo "Options:"
      echo "  --verbose, -v   Enable verbose output"
      echo "  --debug, -d     Use 'debug' tag instead of default tag"
      echo "  --help, -h      Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help to see available options"
      exit 1
      ;;
  esac
done

# Find the overseer directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
echo "📂 Script directory: $SCRIPT_DIR"

# Change to the overseer directory
cd "$SCRIPT_DIR"
echo "📍 Current directory: $(pwd)"

# Check if our core files exist
echo "🔍 Checking for core files..."
if [ ! -f "overseer.py" ]; then
  echo "❌ Error: overseer.py not found!"
  exit 1
fi

if [ ! -f "requirements.txt" ]; then
  echo "❌ Error: requirements.txt not found!"
  exit 1
fi

if [ ! -f "Dockerfile" ]; then
  echo "❌ Error: Dockerfile not found!"
  exit 1
fi

# Verify frontend directory exists
echo "🔍 Checking frontend directory..."
if [ ! -d "frontend" ]; then
  echo "❌ Error: frontend directory not found!"
  exit 1
fi

# Verify React app is available
if [ ! -f "frontend/package.json" ]; then
  echo "❌ Error: frontend/package.json not found! React app is required."
  exit 1
fi

# Check for Docker
if ! command -v docker &> /dev/null; then
  echo "❌ Error: Docker is not installed or not in PATH"
  exit 1
fi

# Show a summary of what will be built
echo ""
echo "🔄 Build summary:"
echo "   - Backend: Python-based overseer from overseer.py"
echo "   - Frontend: React app from frontend/"
if [ "$DEBUG_TAG" = true ]; then
  echo "   - Docker tag: chaos-monkey-overseer:debug"
else
  echo "   - Docker tag: chaos-monkey-overseer"
fi
if [ "$VERBOSE" = true ]; then
  echo "   - Verbose mode: enabled"
fi
echo ""

# List frontend files in verbose mode
if [ "$VERBOSE" = true ]; then
  echo "📋 Frontend directory structure:"
  find frontend -type d | sort
  echo ""
  
  echo "📋 Frontend files:"
  find frontend -type f | sort
  echo ""
fi

# Build the Docker image with appropriate verbosity
echo "🏭 Building Docker image for overseer..."
if [ "$DEBUG_TAG" = true ]; then
  # Use debug tag
  if [ "$VERBOSE" = true ]; then
    docker build --progress=plain -t chaos-monkey-overseer:debug .
  else
    docker build -t chaos-monkey-overseer:debug .
  fi
else
  # Use default tag
  if [ "$VERBOSE" = true ]; then
    docker build --progress=plain -t chaos-monkey-overseer .
  else
    docker build -t chaos-monkey-overseer .
  fi
fi

# Report success
echo ""
echo "✅ Build completed successfully!"
echo ""
echo "To run the image, use:"
if [ "$DEBUG_TAG" = true ]; then
  echo "   docker run -p 8080:8080 chaos-monkey-overseer:debug"
else
  echo "   docker run -p 8080:8080 chaos-monkey-overseer"
fi
echo ""
echo "The overseer will be available at:"
echo "   http://localhost:8080/" 