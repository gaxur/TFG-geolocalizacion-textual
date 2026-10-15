#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE_TAG=tfg-f4-osm-carto-arm64:ubuntu24.04

docker build --pull --platform linux/arm64 \
  -f "$ROOT/docker/f4-osm-carto-arm64/Dockerfile" \
  -t "$IMAGE_TAG" "$ROOT"

export F4_RENDER_IMAGE_ID
F4_RENDER_IMAGE_ID=$(docker image inspect "$IMAGE_TAG" --format '{{.Id}}')
export F4_HOST_UID=$(id -u)
export F4_HOST_GID=$(id -g)

docker compose -f "$ROOT/compose.f4-osm-render.yaml" run --rm f4-osm-render
