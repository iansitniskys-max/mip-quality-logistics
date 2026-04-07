#!/bin/sh

# Start uvicorn in background
cd /app/backend
/opt/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --log-level info &

# Wait for uvicorn to start
sleep 2

# Start nginx in foreground
nginx -g "daemon off;"
