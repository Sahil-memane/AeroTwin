#!/bin/sh
set -e

echo "Running Alembic migrations..."
alembic upgrade head

# --reload is a development convenience (watches the bind-mounted source in
# docker-compose); never on in a deployed image. Opt in with UVICORN_RELOAD=1.
#
# Deliberately a single worker: prediction windows, alert cooldowns, aux wear
# state and the WebSocket connection manager are held in process memory, so
# more than one worker/replica would split that state (see docs/DEPLOYMENT.md).
RELOAD_FLAG=""
if [ -n "${UVICORN_RELOAD}" ]; then
  RELOAD_FLAG="--reload"
fi

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" ${RELOAD_FLAG}
