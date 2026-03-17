#!/bin/bash

APP_DIR="/var/www/ngo-system"

# Ensure we're in the app directory
cd "$APP_DIR" || {
  echo "App directory not found: $APP_DIR"
  exit 1
}

# Activate the virtual environment
source venv/bin/activate

# Optional: Pull latest changes (only if you want auto-updates)
# git pull origin main

# Start the FastAPI app using Gunicorn
exec gunicorn -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000 main:app
