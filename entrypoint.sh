#!/bin/sh

set -e

mkdir -p /tmp/db

echo "Running database migrations..."

if ! timeout 30s alembic upgrade head 2>&1; then
    echo "⚠️  Migration failed or timed out. Creating tables directly..."

    python -c "
from app.db.database import Base, engine
try:
    Base.metadata.create_all(bind=engine)
    print('✅ Database tables created successfully')
except Exception as e:
    print(f'❌ Database initialization failed: {e}')
" || echo "Continuing without database initialization..."
fi

echo "Starting application on port ${PORT:-8080}..."
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}