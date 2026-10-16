#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE_TAG=crosstext2loc-gb10:ngc26.02

mkdir -p "$ROOT/results/generated/f4.5"
image_id=$(docker image inspect "$IMAGE_TAG" --format '{{.Id}}')
utils_sha256=$(sha256sum "$ROOT/external/CVG-Text/utils.py" | cut -d' ' -f1)
export F4_HOST_UID=$(id -u)
export F4_HOST_GID=$(id -g)

F4_CROSSTEXT2LOC_IMAGE_ID="$image_id" docker compose -f "$ROOT/compose.cross-text2loc.yaml" run --rm --entrypoint bash \
  crosstext2loc -lc 'set -euo pipefail; python /workspace/project/scripts/run_f4_linguistic_rankings.py "$@"; chown -R "$F4_HOST_UID:$F4_HOST_GID" /run-results; find /run-results -type d -exec chmod 755 {} +; find /run-results -type f -exec chmod 644 {} +' -- "$@" \
  --container-image-id "$image_id" --cvg-utils-sha256 "$utils_sha256"
