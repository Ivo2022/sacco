#!/usr/bin/env bash

set -euo pipefail

: ${APP_MODULE:=backend.main:app}
: ${APP_HOST:=0.0.0.0}
: ${APP_PORT:=${PORT:-10000}}
: ${VENV_PATH:=}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Starting app from $SCRIPT_DIR (module=$APP_MODULE host=$APP_HOST port=$APP_PORT)"

if [ -z "$VENV_PATH" ]; then
  if [ -f "$SCRIPT_DIR/venv/bin/activate" ]; then
    VENV_PATH="$SCRIPT_DIR/venv"
  elif [ -f "$SCRIPT_DIR/backend/venv/bin/activate" ]; then
    VENV_PATH="$SCRIPT_DIR/backend/venv"
  fi
fi

if [ -n "$VENV_PATH" ] && [ -f "$VENV_PATH/bin/activate" ]; then
  echo "Activating virtualenv at $VENV_PATH"
  . "$VENV_PATH/bin/activate"
fi

if command -v gunicorn >/dev/null 2>&1 && python -c "import uvicorn" >/dev/null 2>&1; then
  echo "Launching with gunicorn + uvicorn worker"
  exec gunicorn -k uvicorn.workers.UvicornWorker -b 0.0.0.0:$APP_PORT "$APP_MODULE"
fi

if command -v uvicorn >/dev/null 2>&1; then
  echo "Launching with uvicorn"
  exec uvicorn "$APP_MODULE" --host $APP_HOST --port $APP_PORT
fi

echo "Error: neither gunicorn nor uvicorn found."
exit 1