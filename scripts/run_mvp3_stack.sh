#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -f "$ROOT/.env" ]]; then
  declare -A ENV_OVERRIDES=()
  for name in \
    MVP_BIND_HOST MVP_HTTP_PORT MVP_COMPOSE_PROJECT \
    MVP_API_CONTAINER_NAME MVP_FRONTEND_CONTAINER_NAME \
    MVP_API_IMAGE MVP_FRONTEND_IMAGE MVP_BROWSER_IMAGE \
    MVP_CLIP_CACHE_DIR MVP_QWEN_MODEL_DIR MVP_MAP_ASSETS_DIR \
    MVP_DIALOGUE_COHORT_FILE MVP_DIALOGUE_AUTHORIZATION_FILE MVP_DIALOGUE_SESSION_DIR MVP_DIALOGUE_IMAGE_DIR \
    ATLAS_DIALOGUE_ENABLED ATLAS_DIALOGUE_COMPLETED_QUERY_IDS \
    MVP_VISUAL_BUNDLE_DIR ATLAS_VISUAL_PROMOTION_ENABLED \
    ATLAS_VISUAL_PRECOMPUTED_BUNDLE_CONTAINER \
    VITE_TILE_URL VITE_TILE_ATTRIBUTION; do
    if [[ -v "$name" ]]; then ENV_OVERRIDES["$name"]=${!name}; fi
  done
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
  for name in "${!ENV_OVERRIDES[@]}"; do
    printf -v "$name" '%s' "${ENV_OVERRIDES[$name]}"
    export "$name"
  done
fi
COMPOSE=(docker compose)
if [[ -n "${MVP_COMPOSE_PROJECT:-}" ]]; then COMPOSE+=(-p "$MVP_COMPOSE_PROJECT"); fi
COMPOSE+=(-f "$ROOT/compose.mvp.yaml")
CLIP_DIR=${MVP_CLIP_CACHE_DIR:-$HOME/.cache/clip}
QWEN_DIR=${MVP_QWEN_MODEL_DIR:-$HOME/models/hf/Qwen3-8B-b968826d9c46}
EXTERNAL_DIR=${MVP_EXTERNAL_DIR:-$ROOT/external}
CHECKPOINT_DIR=${MVP_CHECKPOINT_DIR:-$ROOT/checkpoints/CrossText2Loc}

test -f "$EXTERNAL_DIR/CVG-Text/utils.py"
test -f "$CHECKPOINT_DIR/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth"
test -f "$CLIP_DIR/ViT-L-14-336px.pt"
test -f "$QWEN_DIR/config.json"
test -f "$QWEN_DIR/tokenizer.json"
python - "$ROOT" "$EXTERNAL_DIR" "$CHECKPOINT_DIR" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1]); external = Path(sys.argv[2]); checkpoint = Path(sys.argv[3])
config = json.loads((root / "config/madrid_f46_retriever.json").read_text())
paths = []
for gallery in config["galleries"].values():
    paths.extend(gallery[key] for key in ("catalog_manifest", "selection", "visual_bundle", "embedding_bundle"))
missing = [path for path in paths if not (root / path).exists()]
if not (external / "CVG-Text").is_dir(): missing.append(str(external / "CVG-Text"))
if not (checkpoint / "long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth").is_file(): missing.append(str(checkpoint))
if missing:
    raise SystemExit("Faltan artefactos MVP.3:\n" + "\n".join(missing))
PY

export MVP_CLIP_CACHE_DIR=$CLIP_DIR
export MVP_QWEN_MODEL_DIR=$QWEN_DIR
export MVP_BIND_HOST=${MVP_BIND_HOST:-0.0.0.0}
exec "${COMPOSE[@]}" up --build "$@"
