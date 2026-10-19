#!/usr/bin/env python3
"""Comprueba pares ingles-espanol a traves del HTTP publico del MVP."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from urllib.request import Request, urlopen


def retrieve(base_url: str, query: dict, gallery_id: str, top_k: int) -> dict:
    payload = {
        "schema_version": "1.0",
        "contract_version": "crosstext2loc-retrieval-request-v1",
        "query": {
            "query_id": query["query_id"],
            "text": query["text"],
            "language": query["language"],
        },
        "gallery_ids": [gallery_id],
        "top_k": top_k,
    }
    request = Request(
        base_url.rstrip("/") + "/api/v1/retrievals",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={"Content-Type": "application/json", "X-Request-ID": query["query_id"]},
    )
    with urlopen(request, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"HTTP inesperado: {response.status}")
        document = json.loads(response.read())
    retrieval = document["retrievals"][0]
    if retrieval["gallery_id"] != gallery_id or retrieval["effective_k"] != top_k:
        raise RuntimeError("respuesta incompatible con la consulta bilingue")
    return retrieval


def haversine_m(first: dict, second: dict) -> float:
    radius = 6_371_008.8
    lat1, lat2 = math.radians(first["latitude"]), math.radians(second["latitude"])
    dlat = lat2 - lat1
    dlon = math.radians(second["longitude"] - first["longitude"])
    value = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def bilingual_pairs(query_set: dict) -> list[tuple[str, dict, dict]]:
    pairs = []
    for group in query_set["groups"]:
        variants = group["variants"]
        anchors = {variant["query_id"]: variant for variant in variants if variant["transformation"] == "anchor"}
        translations = [variant for variant in variants if variant["transformation"] == "translation" and variant["language"] == "es"]
        if len(anchors) != 1 or len(translations) != 1:
            raise ValueError(f"grupo bilingue invalido: {group['group_id']}")
        translation = translations[0]
        anchor = anchors.get(translation["parent_query_id"])
        if anchor is None or anchor["language"] != "en":
            raise ValueError(f"traduccion sin anchor ingles: {group['group_id']}")
        pairs.append((group["group_id"], anchor, translation))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--query-set", type=Path, default=Path("config/madrid_f45_linguistic_robustness.json"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.top_k < 1 or args.top_k > 10:
        raise ValueError("top-k debe estar entre 1 y 10")

    query_set = json.loads(args.query_set.read_text(encoding="utf-8"))
    rows = []
    for group_id, english, spanish in bilingual_pairs(query_set):
        for gallery_id in ("madrid-50m", "madrid-25m"):
            en_result = retrieve(args.base_url, english, gallery_id, args.top_k)
            es_result = retrieve(args.base_url, spanish, gallery_id, args.top_k)
            en_rows, es_rows = en_result["results"], es_result["results"]
            en_ids = [row["candidate_id"] for row in en_rows]
            es_ids = [row["candidate_id"] for row in es_rows]
            shared = len(set(en_ids) & set(es_ids))
            rows.append({
                "group_id": group_id,
                "gallery_id": gallery_id,
                "english_query_id": english["query_id"],
                "spanish_query_id": spanish["query_id"],
                "english_top1": en_ids[0],
                "spanish_top1": es_ids[0],
                "top1_equal": en_ids[0] == es_ids[0],
                "shared_top_k": shared,
                "jaccard_top_k": shared / len(set(en_ids) | set(es_ids)),
                "top1_distance_m": haversine_m(en_rows[0], es_rows[0]),
            })

    report = {
        "status": "pass",
        "scope": "technical_linguistic_stability_without_ground_truth",
        "base_url": args.base_url,
        "query_set_id": query_set["query_set_id"],
        "top_k": args.top_k,
        "comparisons": rows,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
