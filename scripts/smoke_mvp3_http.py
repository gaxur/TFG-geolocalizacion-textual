#!/usr/bin/env python3
"""Smoke del MVP integrado a través del único origen publicado por Nginx."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def call(base_url: str, method: str, path: str, body=None):
    raw = None if body is None else json.dumps(body).encode()
    request = Request(base_url + path, data=raw, method=method, headers={"Content-Type": "application/json", "X-Request-ID": "mvp3-smoke"})
    try:
        with urlopen(request, timeout=45) as response:
            return response.status, dict(response.headers), json.loads(response.read())
    except HTTPError as error:
        return error.code, dict(error.headers), json.loads(error.read())


def payload(query_id: str, gallery_id: str, mode: str = "no_llm"):
    return {
        "schema_version": "1.0",
        "contract_version": "atlas-experimental-retrieval-request-v2",
        "query": {"query_id": query_id, "text": "Estoy en una plaza urbana amplia rodeada de edificios y calles estrechas", "language": "es"},
        "gallery_id": gallery_id,
        "processing_mode": mode,
        "top_k": 10,
    }


def stable_rows(document):
    return [(row["candidate_id"], row["rank"], row["cosine_similarity"], row["latitude"], row["longitude"]) for row in document["retrievals"][0]["results"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    with urlopen(args.base_url + "/", timeout=10) as response:
        html_ok = response.status == 200 and b'id="app"' in response.read()
    live = call(args.base_url, "GET", "/api/v1/health/live")
    ready = call(args.base_url, "GET", "/api/v1/health/ready")
    capabilities = call(args.base_url, "GET", "/api/v1/capabilities")
    case_50 = call(args.base_url, "POST", "/api/v1/retrievals", payload("mvp3-50m", "madrid-50m"))
    case_25 = call(args.base_url, "POST", "/api/v1/retrievals", payload("mvp3-25m", "madrid-25m"))
    llm_50 = call(args.base_url, "POST", "/api/v1/retrievals", payload("mvp3-llm-50m", "madrid-50m", "with_llm"))
    llm_25 = call(args.base_url, "POST", "/api/v1/retrievals", payload("mvp3-llm-25m", "madrid-25m", "with_llm"))
    repeated_a = call(args.base_url, "POST", "/api/v1/retrievals", payload("mvp3-repeat-a", "madrid-50m"))
    repeated_b = call(args.base_url, "POST", "/api/v1/retrievals", payload("mvp3-repeat-b", "madrid-50m"))
    invalid = call(args.base_url, "POST", "/api/v1/retrievals", dict(payload("mvp3-invalid", "madrid-50m"), top_k=0))
    missing = call(args.base_url, "POST", "/api/v1/retrievals", payload("mvp3-missing", "missing"))

    expected_statuses = [live[0], ready[0], capabilities[0], case_50[0], case_25[0], llm_50[0], llm_25[0], repeated_a[0], repeated_b[0], invalid[0], missing[0]]
    if expected_statuses != [200, 200, 200, 200, 200, 200, 200, 200, 200, 422, 422]:
        raise RuntimeError(f"códigos HTTP inesperados: {expected_statuses}")
    rows_50 = stable_rows(case_50[2])
    rows_25 = stable_rows(case_25[2])
    deterministic = stable_rows(repeated_a[2]) == stable_rows(repeated_b[2])
    coordinates_valid = all(-90 <= row[3] <= 90 and -180 <= row[4] <= 180 for row in rows_50 + rows_25)
    galleries = {item["gallery_id"]: item["candidate_count"] for item in capabilities[2]["galleries"]}
    report = {
        "status": "pass",
        "same_origin_frontend": html_ok,
        "live": live[2],
        "ready": ready[2],
        "galleries": galleries,
        "case_50m_no_llm": {"requested_k": 10, "returned": len(rows_50), "rows": rows_50},
        "case_25m_no_llm": {"requested_k": 10, "returned": len(rows_25), "rows": rows_25},
        "case_50m_with_llm": {"returned": len(stable_rows(llm_50[2])), "processing": llm_50[2]["processing"]},
        "case_25m_with_llm": {"returned": len(stable_rows(llm_25[2])), "processing": llm_25[2]["processing"]},
        "repeated_ranking_identical": deterministic,
        "coordinates_valid": coordinates_valid,
        "invalid_request_status": invalid[0],
        "missing_gallery_status": missing[0],
    }
    if not all((html_ok, galleries == {"madrid-50m": 253, "madrid-25m": 1115}, len(rows_50) == 10, len(rows_25) == 10, len(stable_rows(llm_50[2])) == 10, len(stable_rows(llm_25[2])) == 10, deterministic, coordinates_valid)):
        raise RuntimeError("el smoke integrado no verificó todas las invariantes")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
