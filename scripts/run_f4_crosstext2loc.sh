#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE_TAG=crosstext2loc-gb10:ngc26.02

mkdir -p "$ROOT/data/embeddings" "$ROOT/results/generated/f4" \
  "$ROOT/results/cross_text2loc_docker/manual"

if ! docker image inspect "$IMAGE_TAG" >/dev/null 2>&1; then
  docker build \
    -f "$ROOT/docker/crosstext2loc-gb10/Dockerfile" \
    -t "$IMAGE_TAG" "$ROOT/docker/crosstext2loc-gb10"
fi

image_id=$(docker image inspect "$IMAGE_TAG" --format '{{.Id}}')
utils_sha256=$(sha256sum "$ROOT/external/CVG-Text/utils.py" | cut -d' ' -f1)
export F4_HOST_UID=$(id -u)
export F4_HOST_GID=$(id -g)

F4_CROSSTEXT2LOC_IMAGE_ID="$image_id" docker compose -f "$ROOT/compose.cross-text2loc.yaml" run --rm --entrypoint bash \
  crosstext2loc /workspace/project/scripts/run_f4_crosstext2loc_container.sh "$@" \
  --container-image-id "$image_id" --cvg-utils-sha256 "$utils_sha256"
