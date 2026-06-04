#!/bin/bash
# SevaForge Quick Start
echo "Starting SevaForge stack..."

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "Docker not found. Running locally instead..."
    echo "Install dependencies: pip install -e ."
    echo "Start server: cd src && uvicorn sevaforge.api.app:create_app --factory --reload"
    exit 1
fi

# Start stack
docker compose up -d
echo ""
echo "SevaForge is starting up!"
echo "  API:        http://localhost:8000"
echo "  Dashboard:  http://localhost:3000"
echo "  API Docs:   http://localhost:8000/docs"
echo "  Jaeger:     http://localhost:16686"
echo ""
echo "Run 'docker compose logs -f api' to see API logs"
