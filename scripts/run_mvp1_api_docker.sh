#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE=${ATLAS_API_IMAGE:-crosstext2loc-gb10:ngc26.02}
PUBLISH_HOST=${ATLAS_API_HOST:-127.0.0.1}
PORT=${ATLAS_API_PORT:-8000}
NAME=${ATLAS_API_CONTAINER_NAME:-atlas-mvp1-api}

test -f "$ROOT/external/CVG-Text/utils.py"
test -f "$HOME/.cache/clip/ViT-L-14-336px.pt"
utils_sha256=$(sha256sum "$ROOT/external/CVG-Text/utils.py" | cut -d' ' -f1)

exec docker run --rm --name "$NAME" --gpus all --init --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=1g \
  -p "$PUBLISH_HOST:$PORT:8000" \
  -e CUDA_VISIBLE_DEVICES=0 \
  -e HOME=/root \
  -e HF_HOME=/tmp/huggingface \
  -e GIT_CONFIG_COUNT=1 \
  -e GIT_CONFIG_KEY_0=safe.directory \
  -e GIT_CONFIG_VALUE_0=/workspace/project/external/CVG-Text \
  -e CLIP_WEIGHTS_PATH=/root/.cache/clip/ViT-L-14-336px.pt \
  -e ATLAS_CVG_UTILS_SHA256="$utils_sha256" \
  -e ATLAS_API_HOST=0.0.0.0 \
  -e ATLAS_API_PORT=8000 \
  -v "$ROOT:/workspace/project:ro" \
  -v "$HOME/.cache/clip:/root/.cache/clip:ro" \
  -w /workspace/project \
  "$IMAGE" \
  /workspace/project/scripts/run_mvp1_api.sh
