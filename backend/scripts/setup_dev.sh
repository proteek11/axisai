#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# axis-ai local development setup
# Run this once after cloning the repo
# Requires: Python 3.11.3, Docker Desktop
# ─────────────────────────────────────────────────────────────────────────────
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  axis-ai — local dev setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Check Python version
PYTHON_VERSION=$(python3.11 --version 2>&1 | cut -d' ' -f2)
echo "✓ Python: $PYTHON_VERSION"

# 2. Create virtual environment
if [ ! -d ".venv" ]; then
    echo "→ Creating virtual environment..."
    python3.11 -m venv .venv
fi
source .venv/bin/activate
echo "✓ Virtual environment active"

# 3. Install dependencies
echo "→ Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"
echo "✓ Dependencies installed"

# 4. Create .env from example (if not exists)
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✓ Created .env from .env.example"
    echo "  ⚠️  Edit .env and add your AI provider API keys before running"
else
    echo "✓ .env already exists"
fi

# 5. Start infrastructure
echo "→ Starting Docker services (postgres, redis, qdrant)..."
docker compose up -d postgres redis qdrant
echo "→ Waiting for services to be healthy..."
sleep 5

# 6. Run migrations
echo "→ Running database migrations..."
alembic upgrade head
echo "✓ Migrations complete"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete! To start developing:"
echo ""
echo "  source .venv/bin/activate"
echo ""
echo "  # Start the API server (auto-reload)"
echo "  uvicorn app.main:app --reload --port 8000"
echo ""
echo "  # In another terminal: start Celery worker"
echo "  celery -A app.tasks.celery_app worker --loglevel=info"
echo ""
echo "  # API docs:"
echo "  http://localhost:8000/docs"
echo "  http://localhost:8000/health/ready"
echo ""
echo "  # Qdrant dashboard:"
echo "  http://localhost:6333/dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
