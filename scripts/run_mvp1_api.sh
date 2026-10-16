#!/usr/bin/env bash
set -euo pipefail

: "${CLIP_WEIGHTS_PATH:?CLIP_WEIGHTS_PATH es obligatorio}"
: "${ATLAS_CVG_UTILS_SHA256:?ATLAS_CVG_UTILS_SHA256 es obligatorio}"

HOST=${ATLAS_API_HOST:-127.0.0.1}
PORT=${ATLAS_API_PORT:-8000}

exec uvicorn backend.atlas_api.main:create_app \
  --factory \
  --host "$HOST" \
  --port "$PORT" \
  --workers 1
