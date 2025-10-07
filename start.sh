#!/bin/bash
# Railway startup script - handles PORT environment variable

# Get port from environment or default to 8000
PORT=${PORT:-8000}

echo "Starting Uvicorn on port $PORT..."

# Start uvicorn with the PORT variable
exec uvicorn main:app --host 0.0.0.0 --port "$PORT"
