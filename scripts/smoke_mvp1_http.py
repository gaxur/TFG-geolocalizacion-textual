#!/usr/bin/env python3
"""Smoke HTTP real MVP.1 contra una API FastAPI ya arrancada."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(base_url: str, method: str, path: str, body=None):
    raw = None if body is None else json.dumps(body).encode()
    request = Request(base_url + path, data=raw, method=method, headers={"Content-Type": "application/json", "X-Request-ID": "mvp1-smoke"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, dict(response.headers), json.loads(response.read())
    except HTTPError as error:
        return error.code, dict(error.headers), json.loads(error.read())


def stable_rows(retrieval):
    return [(row["rank"], row["candidate_id"], row["latitude"], row["longitude"], row["cosine_similarity"]) for row in retrieval["results"]]


def historical_rows(path: Path):
    document = json.loads(path.read_text())
    return [(row["rank"], row["candidate_id"], row["latitude"], row["longitude"], row["score"]) for row in document["results"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--expected-25m", required=True, type=Path)
    parser.add_argument("--expected-50m", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    live = call(args.base_url, "GET", "/api/v1/health/live")
    ready = call(args.base_url, "GET", "/api/v1/health/ready")
    capabilities = call(args.base_url, "GET", "/api/v1/capabilities")
    payload = {"schema_version": "1.0", "contract_version": "crosstext2loc-retrieval-request-v1", "query": {"query_id": "madrid-f42-final-en-001", "text": "A large urban square surrounded by buildings and narrow streets", "language": "en"}, "gallery_ids": ["madrid-25m", "madrid-50m"], "top_k": 10}
    started = time.perf_counter()
    first = call(args.base_url, "POST", "/api/v1/retrievals", payload)
    first_ms = (time.perf_counter() - started) * 1000
    repeated = call(args.base_url, "POST", "/api/v1/retrievals", payload)
    single_25 = call(args.base_url, "POST", "/api/v1/retrievals", dict(payload, gallery_ids=["madrid-25m"]))
    single_50 = call(args.base_url, "POST", "/api/v1/retrievals", dict(payload, gallery_ids=["madrid-50m"]))
    invalid = call(args.base_url, "POST", "/api/v1/retrievals", dict(payload, top_k=0))
    missing = call(args.base_url, "POST", "/api/v1/retrievals", dict(payload, gallery_ids=["missing"]))
    if any(response[0] != 200 for response in (live, ready, capabilities, first, repeated, single_25, single_50)) or invalid[0] != 422 or missing[0] != 404:
        raise RuntimeError("códigos HTTP inesperados")
    first_rows = {item["gallery_id"]: stable_rows(item) for item in first[2]["retrievals"]}
    repeated_rows = {item["gallery_id"]: stable_rows(item) for item in repeated[2]["retrievals"]}
    expected = {"madrid-25m": historical_rows(args.expected_25m), "madrid-50m": historical_rows(args.expected_50m)}
    if first_rows != expected or repeated_rows != first_rows:
        raise RuntimeError("ranking HTTP no coincide con F4.4 o no es determinista")
    response_headers = {key.lower(): value for key, value in first[1].items()}
    report = {
        "status": "pass", "live": live[2], "ready": ready[2], "capabilities": capabilities[2],
        "first_multigallery_http_ms": first_ms, "rankings_match_f44": True, "repeated_ranking_identical": True,
        "single_gallery_25m_ok": single_25[2]["retrievals"][0]["gallery_count"] == 1115,
        "single_gallery_50m_ok": single_50[2]["retrievals"][0]["gallery_count"] == 253,
        "invalid_request_status": invalid[0], "missing_gallery_status": missing[0],
        "request_id_propagated": response_headers.get("x-request-id") == "mvp1-smoke",
    }
    if not all((report["rankings_match_f44"], report["repeated_ranking_identical"], report["single_gallery_25m_ok"], report["single_gallery_50m_ok"], report["request_id_propagated"])):
        raise RuntimeError("el smoke HTTP no verificó todas las invariantes")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
