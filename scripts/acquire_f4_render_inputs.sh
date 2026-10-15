#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
CARTO_DIR="$ROOT/external/openstreetmap-carto-v5.9.0"
SOURCE_DIR="$ROOT/data/raw/osm/f4_sources/madrid-geofabrik-20261014"
ASSET_DIR="$ROOT/data/raw/osm/f4_renderer/osm-carto-v5.9.0/downloads"

fetch() {
  local url=$1 destination=$2 expected=$3
  mkdir -p "$(dirname "$destination")"
  if [[ -f "$destination" ]] && [[ "$(sha256sum "$destination" | cut -d' ' -f1)" == "$expected" ]]; then
    return
  fi
  curl --fail --location --retry 3 --output "$destination.part" "$url"
  printf '%s  %s\n' "$expected" "$destination.part" | sha256sum --check --status
  mv "$destination.part" "$destination"
}

archive=/tmp/openstreetmap-carto-v5.9.0.tar.gz
fetch "https://codeload.github.com/openstreetmap-carto/openstreetmap-carto/tar.gz/refs/tags/v5.9.0" "$archive" "03b637652b13e3ed6bdb83979ff01cae2a26b33e60fdaca7ad3a8cd045ec4045"
carto_temp=$(mktemp -d -p "$ROOT/external" .openstreetmap-carto-v5.9.0-XXXXXX)
trap 'rm -rf "$carto_temp"' EXIT
tar --extract --gzip --strip-components=1 --file "$archive" --directory "$carto_temp"
patch -d "$carto_temp" -p1 < "$ROOT/docker/f4-osm-carto-arm64/osm-carto-v5.9.0-emoji-fallback.patch"
rm -rf "$CARTO_DIR"
mv "$carto_temp" "$CARTO_DIR"
trap - EXIT

fetch "https://download.geofabrik.de/europe/spain/madrid-261014.osm.pbf" "$SOURCE_DIR/source.osm.pbf" "9ef85f5c728a26995712a835a68f0cb30e01a32af6d2a7facd6744f3a3840db8"
cp "$ROOT/config/madrid_f4_osm_source_provenance.json" "$SOURCE_DIR/provenance.json"
fetch "https://osmdata.openstreetmap.de/download/simplified-water-polygons-split-3857.zip" "$ASSET_DIR/simplified-water-polygons-split-3857.zip" "e1b4afdf4045860169a72fb7464c3a6bddabdf5938ffcf3a03be189008ccb737"
fetch "https://osmdata.openstreetmap.de/download/water-polygons-split-3857.zip" "$ASSET_DIR/water-polygons-split-3857.zip" "83644dfb628a981ae367c27f13f23d31b1500691a18a73e9678bf4476a1f2db5"
fetch "https://osmdata.openstreetmap.de/download/antarctica-icesheet-polygons-3857.zip" "$ASSET_DIR/antarctica-icesheet-polygons-3857.zip" "7612a8b32318f40aecce507db44d69c3520e6b612f60569130009e8dd5cb2c29"
fetch "https://osmdata.openstreetmap.de/download/antarctica-icesheet-outlines-3857.zip" "$ASSET_DIR/antarctica-icesheet-outlines-3857.zip" "38c6394732074ec371a939f4abeaa96a5ff1b293a04fbd5e3820e689b4f3deaa"
fetch "https://naturalearth.s3.amazonaws.com/110m_cultural/ne_110m_admin_0_boundary_lines_land.zip" "$ASSET_DIR/ne_110m_admin_0_boundary_lines_land.zip" "bb2954981570498a4b4344f8e83fa54caa5858e15e800094112407d2bd2f940d"

echo "F4 render inputs verified"
