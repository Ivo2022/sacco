#!/usr/bin/env bash

# start.sh - run the FastAPI application for this repository
# Behavior:
# - default app location: backend.main:app
# - tries to activate a virtualenv if found at ./venv or ./backend/venv
# - prefers gunicorn+uvicorn worker when available, otherwise falls back to uvicorn

set -euo pipefail

# Allow overriding the app module and python env from environment
: ${APP_MODULE:=backend.main:app}
: ${APP_HOST:=0.0.0.0}
: ${APP_PORT:=8000}
: ${VENV_PATH:=}

# Resolve script directory (repo root where start.sh lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting app from $SCRIPT_DIR (module=$APP_MODULE host=$APP_HOST port=$APP_PORT)"

# Try to locate a virtualenv to activate
if [ -z "$VENV_PATH" ]; then
  if [ -f "$SCRIPT_DIR/env/bin/activate" ]; then
    VENV_PATH="$SCRIPT_DIR/venv"
  elif [ -f "$SCRIPT_DIR/backend/env/bin/activate" ]; then
    VENV_PATH="$SCRIPT_DIR/backend/env"
  fi
fi

if [ -n "$VENV_PATH" ] && [ -f "$VENV_PATH/bin/activate" ]; then
  echo "Activating virtualenv at $VENV_PATH"
  # shellcheck source=/dev/null
  . "$VENV_PATH/bin/activate"
fi

# If gunicorn with uvicorn worker is installed, prefer it for production
if command -v gunicorn >/dev/null 2>&1 && python -c "import uvicorn" >/dev/null 2>&1; then
  echo "Launching with gunicorn + uvicorn worker"
  exec gunicorn -k uvicorn.workers.UvicornWorker -b 127.0.0.1:$APP_PORT "$APP_MODULE"
fi

# Otherwise fall back to running uvicorn directly
if command -v uvicorn >/dev/null 2>&1; then
  echo "Launching with uvicorn"
  exec uvicorn "$APP_MODULE" --host $APP_HOST --port $APP_PORT --reload
fi

echo "Error: neither gunicorn nor uvicorn found. Install one of them (e.g. pip install 'uvicorn[standard]' or 'gunicorn uvicorn')"
exit 1
