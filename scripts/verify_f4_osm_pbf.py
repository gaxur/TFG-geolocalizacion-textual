#!/usr/bin/env python3
"""Comprueba íntegramente un PBF F4 con PyOsmium, sin binarios globales."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", required=True, type=Path)
    parser.add_argument("--provenance", required=True, type=Path)
    args = parser.parse_args()
    provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
    try:
        import osmium
    except ImportError as error:
        raise RuntimeError(
            "Instala requirements-cartography.txt en un entorno virtual local; "
            "no hace falta instalar osmium-tool globalmente."
        ) from error

    digest = hashlib.sha256()
    size = 0
    with args.pbf.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
    if digest.hexdigest() != provenance["raw_sha256"] or size != provenance["raw_size_bytes"]:
        raise ValueError("SHA-256/tamaño local no coincide con provenance F4")
    if provenance.get("license") != "ODbL-1.0" or provenance.get("raw_format") != "osmpbf":
        raise ValueError("Provenance F4 no declara osmpbf/ODbL-1.0")
    if not provenance.get("source_id", "").endswith(digest.hexdigest()):
        raise ValueError("source_id F4 no corresponde al hash del PBF")

    reader = osmium.io.Reader(str(args.pbf))
    try:
        header = reader.header()
        header_box = header.box()
        bbox = [
            float(header_box.bottom_left.lon),
            float(header_box.bottom_left.lat),
            float(header_box.top_right.lon),
            float(header_box.top_right.lat),
        ]
        timestamp = header.get("osmosis_replication_timestamp")
    finally:
        reader.close()
    expected_bbox = provenance["bbox"]
    expected_values = [expected_bbox["west"], expected_bbox["south"], expected_bbox["east"], expected_bbox["north"]]
    if any(not math.isclose(a, b, abs_tol=1e-7) for a, b in zip(bbox, expected_values)):
        raise ValueError("bbox de cabecera PBF no coincide con provenance")
    if timestamp != provenance["data_timestamp_utc"]:
        raise ValueError("timestamp de cabecera PBF no coincide con provenance")

    counts = {"node": 0, "way": 0, "relation": 0}
    last_ids = {"node": 0, "way": 0, "relation": 0}
    order_violations = 0

    class OrderAndParseCheck(osmium.SimpleHandler):
        def _record(self, kind: str, osm_id: int) -> None:
            nonlocal order_violations
            counts[kind] += 1
            if osm_id < last_ids[kind]:
                order_violations += 1
            last_ids[kind] = osm_id

        def node(self, obj: Any) -> None:
            self._record("node", int(obj.id))

        def way(self, obj: Any) -> None:
            self._record("way", int(obj.id))

        def relation(self, obj: Any) -> None:
            self._record("relation", int(obj.id))

    OrderAndParseCheck().apply_file(str(args.pbf))
    if order_violations:
        raise ValueError(f"PBF contiene {order_violations} violaciones de orden por tipo")
    if counts["node"] + counts["way"] + counts["relation"] == 0:
        raise ValueError("PyOsmium no encontró objetos OSM legibles")

    print(json.dumps({
        "bbox": bbox,
        "data_timestamp_utc": timestamp,
        "license": provenance["license"],
        "objects": counts,
        "objects_ordered_by_type": True,
        "pbf_sha256": digest.hexdigest(),
        "pbf_size_bytes": size,
        "reader": f"pyosmium {osmium.__version__ if hasattr(osmium, '__version__') else '4.3.2'}",
        "status": "valid",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
