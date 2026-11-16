#!/usr/bin/env python3
"""Generate an approved, hash-bound application profile without inference."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.atlas_api.dialogue_freetext_executor import FreeTextRuntimeExecutor
from backend.atlas_api.dialogue_sessions import canonical, sha256_file


def utc(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    approval_path = ROOT / "config/freetext_application_approval_d098.json"
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    expected_approval = {
        "schema_version": "1.0", "contract_version": "atlas-dialogue-freetext-application-approval-v1", "decision_id": "D098",
        "profile_id": "freetext-application-pgx-20261116-v1", "status": "OPERATOR_APPROVED", "approved": True,
        "max_sessions_total": None, "max_open_sessions": 1, "retention": "until_tfg_review",
        "per_session_maximums": {"qwen": 4, "crosstext2loc": 4, "questions": 3, "automatic_retries": 0},
        "constraints": {"access_mode": "loopback_ssh", "gpu_sequential": True, "ground_truth_permitted": False, "references_permitted": False, "vlm_permitted": False, "h38_h61_permitted": False},
    }
    if {key: approval.get(key) for key in expected_approval} != expected_approval or set(approval) != set(expected_approval) | {"approved_at", "valid_from", "expires_at"}:
        parser.error("documento D098 ausente o incompatible")
    approved_at = datetime.fromisoformat(approval["approved_at"].replace("Z", "+00:00"))
    valid_from = datetime.fromisoformat(approval["valid_from"].replace("Z", "+00:00"))
    expires_at = datetime.fromisoformat(approval["expires_at"].replace("Z", "+00:00"))
    if not all(approval[key].endswith("Z") for key in ("approved_at", "valid_from", "expires_at")) or any(value.tzinfo is None for value in (approved_at, valid_from, expires_at)):
        parser.error("timestamps de aprobación deben estar en UTC y terminar en Z")
    approved_at = approved_at.astimezone(timezone.utc)
    valid_from = valid_from.astimezone(timezone.utc)
    expires_at = expires_at.astimezone(timezone.utc)
    if approved_at > valid_from or expires_at <= valid_from or expires_at - valid_from > timedelta(days=90):
        parser.error("la ventana aprobada debe ser positiva y no superar 90 días")

    executor = FreeTextRuntimeExecutor(
        qwen_model=Path(os.environ["ATLAS_QWEN_MODEL_PATH"]),
        runtime_config=Path(os.environ["ATLAS_RUNTIME_CONFIG"]),
        region_config=Path(os.environ["ATLAS_REGION_CONFIG"]),
        f3_bundle=Path(os.environ["ATLAS_DIALOGUE_F3_BUNDLE"]),
        clip_weights=Path(os.environ["CLIP_WEIGHTS_PATH"]),
        cvg_utils_sha256=os.environ.get("ATLAS_CVG_UTILS_SHA256") or file_sha256(ROOT / "external/CVG-Text/utils.py"),
        ollama_ps_url=os.environ["ATLAS_OLLAMA_PS_URL"],
        policy_config=ROOT / "config/interactive_dialogue_freetext_application_v1.json",
        ollama_status_config=Path(os.environ["ATLAS_OLLAMA_STATUS_CONFIG"]),
    )
    identity = executor.identity
    document = {
        "schema_version": "1.0",
        "contract_version": "atlas-dialogue-freetext-application-profile-v1",
        "profile_id": approval["profile_id"],
        "profile_version": "1.0.0",
        "approval_reference": f"D098:{sha256_file(approval_path)}",
        "status": "APPROVED",
        "approved": True,
        "approved_at": utc(approved_at),
        "valid_from": utc(valid_from),
        "expires_at": utc(expires_at),
        "application_policy_id": "dialogue-vpr-freetext-v1-application",
        "application_policy_version": "1.0.0",
        "application_policy_sha256": sha256_file(ROOT / "config/dialogue_freetext_application_v1.json"),
        "core_policy_id": "dialogue-vpr-freetext-v1-application-core",
        "core_policy_version": "1.0.0",
        "core_policy_sha256": sha256_file(ROOT / "config/interactive_dialogue_freetext_application_v1.json"),
        "executor_identity": identity,
        "executor_identity_sha256": hashlib.sha256(canonical(identity)).hexdigest(),
        "max_sessions_total": None,
        "max_open_sessions": 1,
        "global_quotas": {"maximum_qwen_units": None, "maximum_ct2l_units": None, "maximum_questions": None},
        "per_session_quotas": {"maximum_qwen_loads": 4, "maximum_qwen_calls": 4, "maximum_ct2l_loads": 4, "maximum_ct2l_calls": 4, "maximum_questions": 3, "automatic_retries": 0},
        "constraints": {"access_mode": "loopback", "network_permitted": False, "ground_truth_permitted": False, "references_permitted": False, "vlm_permitted": False, "h38_h61_permitted": False},
    }
    schema = json.loads((ROOT / "schemas/atlas-dialogue-freetext-application-profile-v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({"profile_id": document["profile_id"], "expires_at": document["expires_at"], "executor_identity_sha256": document["executor_identity_sha256"], "application_policy_sha256": document["application_policy_sha256"], "core_policy_sha256": document["core_policy_sha256"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
