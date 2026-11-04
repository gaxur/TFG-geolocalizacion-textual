#!/usr/bin/env python3
"""Orquestador fail-closed A/B. Solo el modo dry-run está habilitado sin autorización."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "coverage": "e02ca2f33772f70dee602d8c58628a8712490f7a3aa2056b956e1bda81003f1d",
    "geometric": "831c2bc52df35e4cf0bc6401aeef4e5ac2557b1cee7711b42dd57860269b90af",
    "paired": "036f23821f4333eb62846f6a019bb2e61e79305fa92004d51f7be34138639abb",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_authorization(document: dict, coverage: dict, geometric: dict, paired: dict) -> None:
    if document.get("contract_version") != "h16-h23-selector-comparison-authorization-request-v1":
        raise ValueError("contrato de autorización incompatible")
    expected_ids = {coverage["manifest_id"], geometric["manifest_id"]}
    scope = document.get("scope", {})
    if set(scope.get("frozen_manifest_ids", [])) != expected_ids:
        raise ValueError("autorización ligada a otros manifests")
    hashes = scope.get("frozen_manifest_sha256", {})
    if hashes != {"coverage_adaptive": EXPECTED["coverage"], "geometric_adaptive": EXPECTED["geometric"], "paired_reuse_plan": EXPECTED["paired"]}:
        raise ValueError("autorización sin hashes congelados exactos")
    if scope.get("new_unique_images_maximum") != paired["download_plan"]["pending_union"] or scope.get("hard_maximum_bytes") != paired["download_plan"]["hard_maximum_bytes"]:
        raise ValueError("presupuesto autorizado no coincide")
    basis = document.get("documentary_basis", {})
    if basis.get("basis_type") not in {"public_license_and_platform_terms", "individual_provider_authorization"}:
        raise ValueError("fundamento documental ausente o incompatible")
    source_urls = {source.get("url") for source in basis.get("sources", [])}
    required_sources = {
        "https://help.mapillary.com/hc/en-us/articles/115001770409-CC-BY-SA-license-for-open-data",
        "https://creativecommons.org/licenses/by-sa/4.0/legalcode.en",
        "https://www.mapillary.com/developer/api-documentation/",
        "https://www.mapillary.com/terms",
    }
    if not required_sources <= source_urls:
        raise ValueError("fuentes documentales públicas incompletas")
    if basis["basis_type"] == "individual_provider_authorization" and not basis.get("individual_provider_authorization_reference"):
        raise ValueError("referencia de autorización individual ausente")
    required = {"reviewed_terms_for_exact_application_and_manifests", "individual_download_and_private_storage_permitted", "fixed_model_inference_permitted", "retention_period_accepted", "attribution_privacy_and_quotas_recorded"}
    if set(document.get("operator_confirmations", {})) != required:
        raise ValueError("confirmaciones de operador incompletas")
    if not document.get("approved") or not document.get("terms_reviewed") or not all(document["operator_confirmations"].values()) or not document.get("approved_by") or not document.get("approved_at_utc") or not document.get("retention_deadline_utc"):
        raise PermissionError("autorización todavía no aprobada")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--geometric-manifest", type=Path, required=True)
    parser.add_argument("--paired-plan", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--dry-run-report", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    paths = {"coverage": args.coverage_manifest, "geometric": args.geometric_manifest, "paired": args.paired_plan}
    actual = {key: digest(path) for key, path in paths.items()}
    if actual != EXPECTED:
        raise ValueError(f"hashes de manifests incompatibles: {actual}")
    coverage = json.loads(args.coverage_manifest.read_text())
    geometric = json.loads(args.geometric_manifest.read_text())
    paired = json.loads(args.paired_plan.read_text())
    authorization = json.loads(args.authorization.read_text())
    if not args.execute:
        command = [str(ROOT / ".venv-geo/bin/python"), str(ROOT / "scripts/prepare_h16_h23_selector_execution.py"), "--dry-run", "--coverage-manifest", str(args.coverage_manifest), "--geometric-manifest", str(args.geometric_manifest), "--paired-plan", str(args.paired_plan), "--fixture", str(ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v2/fixture.json"), "--partial-assets", str(ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v2/partial-existing-assets.json"), "--run-2b", str(ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v2/partial-qwen3-vl-2b-run-v4.json"), "--run-8b", str(ROOT / "results/generated/mapillary/h16-h23-multicandidate-top50-v2/partial-qwen3-vl-8b-run-v4.json"), "--authorization", str(args.authorization), "--output", str(args.dry_run_report)]
        subprocess.run(command, cwd=ROOT, check=True)
        print(json.dumps({"mode": "dry_run_offline", "network_opened": False, "model_loaded": False, "report": str(args.dry_run_report)}, sort_keys=True))
        return 0
    validate_authorization(authorization, coverage, geometric, paired)
    raise RuntimeError("autorización válida, pero la ejecución online debe iniciarse con el comando documentado tras configurar MAPILLARY_ACCESS_TOKEN; este orquestador no descarga implícitamente")


if __name__ == "__main__":
    raise SystemExit(main())
