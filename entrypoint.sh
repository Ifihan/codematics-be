#!/bin/sh

set -e

# Set Python path to include the app directory
export PYTHONPATH=/app:$PYTHONPATH

echo "Running database migrations..."
alembic upgrade head || echo "Migration failed, continuing anyway..."

echo "Starting application on port ${PORT:-8080}..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}