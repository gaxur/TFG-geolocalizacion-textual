#!/usr/bin/env bash
set -euo pipefail

ROOT=/workspace/project
CARTO_ROOT="$ROOT/external/openstreetmap-carto-v5.9.0"
SOURCE_PBF="$ROOT/data/raw/osm/f4_sources/madrid-geofabrik-20261014/source.osm.pbf"
RENDER_ROOT="$ROOT/data/raw/osm/f4_renderer/osm-carto-v5.9.0"

test -f "$SOURCE_PBF"
test -f "$CARTO_ROOT/project.mml"

python3 "$ROOT/scripts/verify_f4_osm_pbf.py" \
  --pbf "$SOURCE_PBF" \
  --provenance "$ROOT/data/raw/osm/f4_sources/madrid-geofabrik-20261014/provenance.json"

if grep -q 'Noto Emoji Regular' "$CARTO_ROOT/style/fonts.mss"; then
  patch -d "$CARTO_ROOT" -p1 < "$ROOT/docker/f4-osm-carto-arm64/osm-carto-v5.9.0-emoji-fallback.patch"
fi

rm -rf /var/lib/postgresql/16/main
install -d -o postgres -g postgres /var/lib/postgresql/16/main /var/run/postgresql
runuser -u postgres -- /usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/16/main --encoding=UTF8 --locale=C.UTF-8
runuser -u postgres -- /usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/16/main -o "-c listen_addresses='' -c jit=off" -w start
runuser -u postgres -- createuser --username postgres --superuser root
createdb --username root gis
psql --username root -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION postgis; CREATE EXTENSION hstore;'

osm2pgsql --create --slim --drop --cache 2048 --number-processes 4 \
  --multi-geometry --hstore --style "$CARTO_ROOT/openstreetmap-carto.style" \
  --tag-transform-script "$CARTO_ROOT/openstreetmap-carto.lua" \
  --database gis "$SOURCE_PBF"

psql -v ON_ERROR_STOP=1 -f "$CARTO_ROOT/functions.sql"
psql -v ON_ERROR_STOP=1 -f "$CARTO_ROOT/indexes.sql"
python3 "$CARTO_ROOT/scripts/get-external-data.py" --config "$ROOT/docker/f4-osm-carto-arm64/external-data.local.yml" --force-import

mkdir -p "$CARTO_ROOT/fonts"
find /usr/share/fonts -type f \( -name '*.ttf' -o -name '*.otf' \) -exec cp -n {} "$CARTO_ROOT/fonts/" \;
carto -a 3.0.22 "$CARTO_ROOT/project.mml" > "$CARTO_ROOT/project.xml"
render_args=(
  --manifest data/processed/catalog/manifest-50m.json
  --selection config/madrid_f4_visual_fixture.json
  --source-dir data/raw/osm/f4_sources/madrid-geofabrik-20261014
  --carto-root external/openstreetmap-carto-v5.9.0
  --renderer-root data/raw/osm/f4_renderer/osm-carto-v5.9.0
  --container-image-digest "$F4_CONTAINER_IMAGE_DIGEST"
  --output-root data/processed/visual
)
if [[ -n "${F4_ONLY_CANDIDATE:-}" ]]; then
  render_args+=(--only-candidate "$F4_ONLY_CANDIDATE")
fi
python3 scripts/render_f4_osm_images.py "${render_args[@]}"

chown -R "$F4_HOST_UID:$F4_HOST_GID" \
  "$ROOT/data/processed/visual" \
  "$RENDER_ROOT" \
  "$CARTO_ROOT/fonts" \
  "$CARTO_ROOT/project.xml"

runuser -u postgres -- /usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/16/main -m fast -w stop
