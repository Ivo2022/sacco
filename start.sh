#!/bin/bash
# start.sh - Production-safe startup script

set -e

echo "Starting SACCO Management System..."

# Check environment
ENV=${ENVIRONMENT:-development}
echo "Environment: $ENV"

# Validate required environment variables in production
if [ "$ENV" = "production" ]; then
    echo "Validating production environment..."
    
    # Check required secrets
    if [ -z "$SECRET_KEY" ] || [ ${#SECRET_KEY} -lt 32 ]; then
        echo "ERROR: SECRET_KEY must be set to at least 32 characters in production"
        exit 1
    fi
    
    if [ -z "$SESSION_SECRET_KEY" ] || [ ${#SESSION_SECRET_KEY} -lt 32 ]; then
        echo "ERROR: SESSION_SECRET_KEY must be set to at least 32 characters in production"
        exit 1
    fi
    
    if [ -z "$DATABASE_URL" ]; then
        echo "ERROR: DATABASE_URL must be set in production"
        exit 1
    fi
    
    # Don't run with debug in production
    if [ "$DEBUG" = "True" ] || [ "$DEBUG" = "true" ]; then
        echo "WARNING: DEBUG is enabled in production!"
    fi
    
    echo "✅ Production validation passed"
fi

# Run database migrations (if using Alembic)
# alembic upgrade head

# Start the application - use gunicorn in production
if [ "$ENV" = "production" ]; then
    echo "Starting with gunicorn (production)..."
    exec gunicorn backend.main:app \
        --workers 4 \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind 0.0.0.0:8000 \
        --timeout 120 \
        --access-logfile - \
        --error-logfile -
else
    echo "Starting with uvicorn (development)..."
    exec uvicorn backend.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --reload \
        --log-level debug
fi