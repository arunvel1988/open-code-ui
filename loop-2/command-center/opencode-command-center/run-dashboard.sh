#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"
set -a
source "$APP_DIR/.env"
set +a
exec "$APP_DIR/.venv/bin/gunicorn" --bind "${BIND_IP:-0.0.0.0}:${PORT:-5000}" --workers 1 --threads 8 --timeout 240 app:app
