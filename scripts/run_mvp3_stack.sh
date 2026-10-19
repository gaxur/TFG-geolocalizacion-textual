#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
COMPOSE=(docker compose)
if [[ -n "${MVP_COMPOSE_PROJECT:-}" ]]; then COMPOSE+=(-p "$MVP_COMPOSE_PROJECT"); fi
COMPOSE+=(-f "$ROOT/compose.mvp.yaml")
CLIP_DIR=${MVP_CLIP_CACHE_DIR:-$HOME/.cache/clip}

test -f "$ROOT/external/CVG-Text/utils.py"
test -f "$CLIP_DIR/ViT-L-14-336px.pt"
python - "$ROOT" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
config = json.loads((root / "config/madrid_f46_retriever.json").read_text())
paths = [config["model"]["checkpoint"], config["model"]["cvg_text_root"]]
for gallery in config["galleries"].values():
    paths.extend(gallery[key] for key in ("catalog_manifest", "selection", "visual_bundle", "embedding_bundle"))
missing = [path for path in paths if not (root / path).exists()]
if missing:
    raise SystemExit("Faltan artefactos MVP.3:\n" + "\n".join(missing))
PY

export MVP_CLIP_CACHE_DIR=$CLIP_DIR
exec "${COMPOSE[@]}" up --build "$@"
