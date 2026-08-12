#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

START_COMMAND="${START_COMMAND:-api}"

if [ "$START_COMMAND" = "worker" ]; then
    echo "Starting Worker (background collector)..."
    exec python -m app.worker
else
    echo "Starting API server..."
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000
fi