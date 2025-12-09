#!/bin/bash
# Quick start script for testing WrkTalk Agent

set -e

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}WrkTalk Agent Quick Start${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.11+"
    exit 1
fi
echo "✅ Python 3 found: $(python3 --version)"

if ! command -v helm &> /dev/null; then
    echo "⚠️  Helm not found. Install for Kubernetes testing."
else
    echo "✅ Helm found: $(helm version --short)"
fi

if ! command -v docker &> /dev/null; then
    echo "⚠️  Docker not found. Install for Docker Compose testing."
else
    echo "✅ Docker found: $(docker --version)"
fi

echo ""
echo -e "${YELLOW}Setting up Python environment...${NC}"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt
pip install -q fastapi uvicorn

echo "✅ Dependencies installed"
echo ""

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file...${NC}"
    cp .env.example .env
    echo "✅ Created .env file - please review and update if needed"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo ""
echo "1. Start the mock backend:"
echo -e "   ${YELLOW}python tests/mock_backend.py${NC}"
echo ""
echo "2. In another terminal, start the agent:"
echo -e "   ${YELLOW}source venv/bin/activate${NC}"
echo -e "   ${YELLOW}export \$(cat .env | xargs)${NC}"
echo -e "   ${YELLOW}python -m wrktalk_agent${NC}"
echo ""
echo "3. In a third terminal, create a test task:"
echo -e "   ${YELLOW}./tests/create_test_task.sh${NC}"
echo ""
echo "Or run all at once with tmux/screen!"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo -e "  View tasks: ${YELLOW}curl http://localhost:3000/test/tasks${NC}"
echo -e "  Clear all:  ${YELLOW}curl -X DELETE http://localhost:3000/test/clear${NC}"
echo ""
