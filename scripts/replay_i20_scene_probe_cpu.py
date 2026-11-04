#!/usr/bin/env python3
"""Reproduce en CPU el procesamiento posterior de un raw de escena ya existente."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.append_jsonl_checkpoint import PlannedJob, finalize_json_atomic, run_resumable
from src.tfg_phase0.i20_assisted_annotation import cache_entry_id, canonical_bytes, content_id, task_identity, validate_scene_proposal_record
from src.tfg_phase0.immutable_attempt_ledger import ImmutableAttemptLedger, execute_immutable_attempt


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay(*, plan_path: Path, annotation_fixture_path: Path, scene_fixture_path: Path, attempt_path: Path, raw_path: Path) -> dict:
    plan = json.loads(plan_path.read_text())
    annotation = json.loads(annotation_fixture_path.read_text())
    scene = json.loads(scene_fixture_path.read_text())
    source_attempt = json.loads(attempt_path.read_text())
    source_raw = json.loads(raw_path.read_text())
    if hashlib.sha256(source_raw["raw_output"].encode()).hexdigest() != source_raw["raw_output_sha256"]:
        raise ValueError("hash de raw v4 inválido")
    pair = scene["records"][0]
    if pair["pair_id"] != source_attempt["target_id"] or source_attempt["attempt_id"] != f"scene:{pair['pair_id']}:1":
        raise ValueError("identidad del intento v4 incompatible")
    by_observation = {row["observation_id"]: row for row in annotation["observations"]}
    assets = {key: value["reference_asset_sha256"] for key, value in by_observation.items()}
    model = {
        "model_id": plan["generator"]["model_id"],
        "revision": plan["generator"]["model_revision"],
        "weight_sha256": plan["generator"]["weight_sha256"],
        "processor_policy": plan["generator"]["processor_policy"],
        "decoding": plan["generator"]["decoding"],
    }
    identity = task_identity(
        kind="scene_pair",
        target_id=pair["pair_id"],
        image_sha256=[assets[pair["left_observation_id"]], assets[pair["right_observation_id"]]],
        model=model,
        prompt_sha256=plan["generator"]["scene_prompt_sha256"],
        schema_sha256=plan["generator"]["scene_schema_sha256"],
        instructions_sha256=plan["source"]["instructions_sha256"],
    )
    expected_cache_id = cache_entry_id(identity)
    if expected_cache_id != source_attempt["cache_entry_id"]:
        raise ValueError("cache_entry_id v4 incompatible")

    def build(raw_output, metadata):
        draft = json.loads(raw_output)
        record = {
            "proposal_id": "",
            "pair_id": pair["pair_id"],
            "left_observation_id": pair["left_observation_id"],
            "right_observation_id": pair["right_observation_id"],
            "left_reference_asset_sha256": assets[pair["left_observation_id"]],
            "right_reference_asset_sha256": assets[pair["right_observation_id"]],
            "proposal_status": "proposed",
            "ai_draft": draft,
            "generation": {
                "input_identity_sha256": hashlib.sha256(canonical_bytes(identity)).hexdigest(),
                "cache_entry_id": expected_cache_id,
                "raw_output_sha256": source_raw["raw_output_sha256"],
                "generated_at_utc": source_attempt["started_at_utc"],
                "model_id": model["model_id"],
                "model_revision": model["revision"],
            },
        }
        record["proposal_id"] = content_id("i20-assist-scene-proposal-sha256-", record, "proposal_id")
        validate_scene_proposal_record(record, fixture_row=pair, asset_sha256=assets)
        return {"query_id": None, "candidate_id": "scene", "image_id": pair["pair_id"], "claim_id": expected_cache_id, "proposal": record}

    with tempfile.TemporaryDirectory(prefix="i20-v4-replay-", dir="/tmp/opencode") as temporary:
        root = Path(temporary)
        ledger = ImmutableAttemptLedger(root / "diagnostics", plan_id=plan["plan_id"], maximum_attempts=1)
        paths = ledger.begin(kind="scene", target_id=pair["pair_id"], cache_entry_id=expected_cache_id, started_at_utc=source_attempt["started_at_utc"])
        ledger.preserve_raw(paths, raw_output=source_raw["raw_output"], metadata=source_raw["generation"])
        generated = []
        record = execute_immutable_attempt(
            ledger=ledger,
            kind="scene",
            target_id=pair["pair_id"],
            cache_entry_id=expected_cache_id,
            now=lambda: "2026-11-03T16:00:00Z",
            generate_raw=lambda: (generated.append(True) or ("", {})),
            parse_and_build=build,
        )
        if generated:
            raise RuntimeError("el replay CPU invocó generación")
        job = PlannedJob((None, "scene", pair["pair_id"], expected_cache_id), identity, None, True)
        checkpoint = root / "checkpoints" / "scene-proposals.jsonl"
        records = run_resumable(
            checkpoint_path=checkpoint,
            provenance={"plan_id": plan["plan_id"], "kind": "scene"},
            jobs=[job],
            execute=lambda unused: execute_immutable_attempt(ledger=ledger, kind="scene", target_id=pair["pair_id"], cache_entry_id=expected_cache_id, now=lambda: "never", generate_raw=lambda: (_ for _ in ()).throw(RuntimeError("generation forbidden")), parse_and_build=build),
            policy_result=lambda unused: record,
        )
        recovered_calls = []
        recovered = run_resumable(
            checkpoint_path=checkpoint,
            provenance={"plan_id": plan["plan_id"], "kind": "scene"},
            jobs=[job],
            execute=lambda unused: (recovered_calls.append(True) or record),
            policy_result=lambda unused: record,
        )
        if recovered_calls or recovered != records:
            raise RuntimeError("recuperación de checkpoint ejecutó callback")
        report_path = root / "probe-report.json"
        report = {
            "schema_version": "1.0",
            "contract_version": "i20-assisted-cpu-replay-report-v1",
            "source_plan_id": plan["plan_id"],
            "source_raw_sha256": source_raw["raw_output_sha256"],
            "calls": ledger.summary(),
            "valid_scene_proposals": len(records),
            "checkpoint_result_frames": 1,
            "gpu_inference_performed": False,
        }
        finalize_json_atomic(output_path=report_path, document=report)
        result = {
            "source": {
                "attempt_file_sha256": digest(attempt_path),
                "raw_file_sha256": digest(raw_path),
                "raw_output_sha256": source_raw["raw_output_sha256"],
                "target_id": pair["pair_id"],
                "cache_entry_id": expected_cache_id,
            },
            "simulation": {
                "result_json_sha256": digest(paths.result),
                "checkpoint_sha256": digest(checkpoint),
                "probe_report_sha256": digest(report_path),
                "result_exists": paths.result.exists(),
                "failure_exists": paths.failure.exists(),
                "checkpoint_result_frames": 1,
                "recovered_without_callback": not recovered_calls,
                "generation_calls": 0,
            },
            "proposal_id": record["proposal"]["proposal_id"],
            "ledger": ledger.summary(),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--annotation-fixture", type=Path, required=True)
    parser.add_argument("--scene-fixture", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(replay(plan_path=args.plan, annotation_fixture_path=args.annotation_fixture, scene_fixture_path=args.scene_fixture, attempt_path=args.attempt, raw_path=args.raw), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
