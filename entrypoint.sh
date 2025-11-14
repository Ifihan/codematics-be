#!/bin/sh

set -e

echo "Running database migrations..."
uv run alembic upgrade head || echo "Migration failed, continuing anyway..."

echo "Starting application on port ${PORT:-8080}..."
exec uv run uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}