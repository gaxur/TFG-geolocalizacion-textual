#!/usr/bin/env python3
"""Congela una revisión assisted I01-I20 sin abrir imágenes ni cargar modelos."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.i20_assisted_annotation import annotation_evidence_draft_schema_v10, annotation_prompt_v10, content_id, scene_draft_schema, scene_prompt, validate_plan
from src.tfg_phase0.i20_preparation import canonical_bytes
from src.tfg_phase0.visual_verifier import SUPPORTED_LOCAL_MODELS
from src.tfg_phase0.xgrammar_guidance import EXPECTED_QWEN3_VL_EOS_TOKEN_IDS, EXPECTED_QWEN3_VL_TEXT_VOCAB_SIZE


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, document: dict) -> None:
    path.write_bytes(canonical_bytes(document) + b"\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--annotation-fixture", type=Path, required=True)
    parser.add_argument("--scene-fixture", type=Path, required=True)
    parser.add_argument("--instructions", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--supersedes-plan", type=Path)
    parser.add_argument("--incident", type=Path)
    parser.add_argument("--probe-kind", choices=("scene", "annotation"), default="scene")
    args = parser.parse_args()
    annotation = json.loads(args.annotation_fixture.read_text())
    scene = json.loads(args.scene_fixture.read_text())
    root = args.output_root
    root.mkdir(parents=True, exist_ok=True)
    model = {
        **SUPPORTED_LOCAL_MODELS["qwen3-vl-8b"],
        "processor_policy": "qwen3-vl-auto-processor-local-files-only-v1",
        "decoding": {"do_sample": False, "temperature": 0, "top_p": 1, "max_new_tokens": 2048},
    }
    scene_schema = scene_draft_schema()
    annotation_schema = annotation_evidence_draft_schema_v10()
    (root / "scene-generation.schema.json").write_bytes(canonical_bytes(scene_schema))
    (root / "annotation-generation.schema.json").write_bytes(canonical_bytes(annotation_schema))
    predecessor = json.loads(args.supersedes_plan.read_text()) if args.supersedes_plan else None
    incident = json.loads(args.incident.read_text()) if args.incident else None
    runner_sha256 = digest(ROOT / "scripts" / "run_i20_assisted_annotation.py")
    validation_code_sha256 = digest(ROOT / "src" / "tfg_phase0" / "i20_assisted_annotation.py")
    materializer_code_sha256 = validation_code_sha256
    ledger_code_sha256 = digest(ROOT / "src" / "tfg_phase0" / "immutable_attempt_ledger.py")
    guidance_code_sha256 = digest(ROOT / "src" / "tfg_phase0" / "xgrammar_guidance.py")
    xgrammar_spec = importlib.util.find_spec("xgrammar")
    if xgrammar_spec is None or not xgrammar_spec.submodule_search_locations:
        raise RuntimeError("XGrammar local no disponible")
    xgrammar_root = Path(next(iter(xgrammar_spec.submodule_search_locations)))
    xgrammar_version = importlib.metadata.version("xgrammar")
    xgrammar_bindings_sha256 = digest(xgrammar_root / "libxgrammar_bindings.so")
    xgrammar_hf_adapter_sha256 = digest(xgrammar_root / "contrib" / "hf.py")
    plan = {
        "schema_version": "1.0",
        "contract_version": "i20-assisted-annotation-plan-v1",
        "plan_id": "",
        "status": "prepared_not_authorized",
        "revision": {
            "revision": 10 if args.probe_kind == "annotation" else 5,
            "supersedes_plan_id": predecessor["plan_id"] if predecessor else None,
            "reason": "Schema guiado sin offsets: semantic_text_es y evidence_quote; spans finales materializados por coincidencia literal única en CPU" if args.probe_kind == "annotation" else "Revisión operativa: validadores individuales conservan $defs Draft 2020-12 y replay CPU verifica result, checkpoint e informe; inputs científicos v3 sin cambios",
        },
        "source": {
            "annotation_fixture_id": annotation["fixture_id"],
            "annotation_fixture_sha256": digest(args.annotation_fixture),
            "scene_fixture_sha256": scene["fixture_sha256"],
            "instructions_sha256": digest(args.instructions),
            "expected_observation_ids": annotation["expected_observation_ids"],
            "expected_scene_pair_ids": [row["pair_id"] for row in scene["records"]],
        },
        "generator": {
            "adapter": "local-qwen3-vl-assisted-annotation-v1",
            "adapter_version": "1.8-xgrammar-literal-evidence" if args.probe_kind == "annotation" else "1.4-defs-aware-record-validation",
            "runner_sha256": runner_sha256,
            "validation_code_sha256": validation_code_sha256,
            "materializer_code_sha256": materializer_code_sha256,
            "ledger_code_sha256": ledger_code_sha256,
            "guidance_code_sha256": guidance_code_sha256,
            "lm_format_enforcer_version": "0.11.3",
            "structured_engine": "xgrammar-0.2.1" if args.probe_kind == "annotation" else "lm-format-enforcer-0.11.3",
            "xgrammar_version": xgrammar_version,
            "xgrammar_bindings_sha256": xgrammar_bindings_sha256,
            "xgrammar_hf_adapter_sha256": xgrammar_hf_adapter_sha256,
            "text_vocab_size": EXPECTED_QWEN3_VL_TEXT_VOCAB_SIZE,
            "eos_token_ids": list(EXPECTED_QWEN3_VL_EOS_TOKEN_IDS),
            "model_id": model["model_id"],
            "model_revision": model["revision"],
            "weight_sha256": model["weight_sha256"],
            "processor_policy": model["processor_policy"],
            "scene_prompt_sha256": hashlib.sha256(scene_prompt().encode()).hexdigest(),
            "annotation_prompt_sha256": hashlib.sha256(annotation_prompt_v10().encode()).hexdigest(),
            "scene_schema_sha256": hashlib.sha256(canonical_bytes(scene_schema)).hexdigest(),
            "annotation_schema_sha256": hashlib.sha256(canonical_bytes(annotation_schema)).hexdigest(),
            "decoding": model["decoding"],
        },
        "jobs": {
            "scene_job_count": 12,
            "annotation_job_count": 20,
            "scene_order": [row["pair_id"] for row in scene["records"]],
            "annotation_order": annotation["expected_observation_ids"],
        },
        "policy": {
            "language": "es",
            "external_context_allowed": False,
            "human_acceptance_required": True,
            "original_ai_payload_immutable": True,
            "human_revision_stored_separately": True,
            "automatic_materialization_allowed": False,
        },
        "blinding": {
            "ground_truth_present": False,
            "rankings_present": False,
            "predictions_present": False,
            "candidate_information_present": False,
            "osm_present": False,
            "holdout_present": False,
            "geography_present": False,
            "provider_ids_present": False,
            "external_links_present": False,
        },
    }
    plan["plan_id"] = content_id("i20-assist-plan-sha256-", plan, "plan_id")
    validate_plan(plan, annotation_fixture=annotation, scene_fixture=scene)
    write(root / "plan.json", plan)
    authorization = {
        "schema_version": "1.0",
        "contract_version": "i20-assisted-retry-authorization-v10" if args.probe_kind == "annotation" else "i20-assisted-retry-authorization-v5",
        "authorization_id": "i20-assisted-annotation-v10-literal-evidence-probe" if args.probe_kind == "annotation" else "i20-assisted-annotation-v5-defs-aware-probe",
        "approved": False,
        "gpu_authorized": False,
        "approved_by": None,
        "approved_at_utc": None,
        "incident_id": (incident.get("incident_id") or incident.get("attempt_id")) if incident else None,
        "original_plan_id": predecessor["plan_id"] if predecessor else None,
        "plan_id": plan["plan_id"],
        "plan_sha256": digest(root / "plan.json"),
        "runner_sha256": runner_sha256,
        "validation_code_sha256": validation_code_sha256,
        "materializer_code_sha256": materializer_code_sha256,
        "ledger_code_sha256": ledger_code_sha256,
        "guidance_code_sha256": guidance_code_sha256,
        "structured_engine": "xgrammar-0.2.1" if args.probe_kind == "annotation" else "lm-format-enforcer-0.11.3",
        "xgrammar_version": xgrammar_version,
        "xgrammar_bindings_sha256": xgrammar_bindings_sha256,
        "xgrammar_hf_adapter_sha256": xgrammar_hf_adapter_sha256,
        "text_vocab_size": EXPECTED_QWEN3_VL_TEXT_VOCAB_SIZE,
        "eos_token_ids": list(EXPECTED_QWEN3_VL_EOS_TOKEN_IDS),
        "annotation_fixture_sha256": digest(args.annotation_fixture),
        "scene_fixture_sha256": digest(args.scene_fixture),
        "instructions_sha256": digest(args.instructions),
        "scene_prompt_sha256": plan["generator"]["scene_prompt_sha256"],
        "annotation_prompt_sha256": plan["generator"]["annotation_prompt_sha256"],
        "scene_schema_sha256": plan["generator"]["scene_schema_sha256"],
        "annotation_schema_sha256": plan["generator"]["annotation_schema_sha256"],
        "model_id": model["model_id"],
        "model_revision": model["revision"],
        "weight_sha256": model["weight_sha256"],
        "historical_v1_calls_attempted": 1,
        "historical_v2_calls_attempted": 1,
        "historical_proposals_completed": 0,
        "requested_probe_calls": 1,
        "probe_kind": args.probe_kind,
        "probe_target_id": plan["jobs"]["annotation_order"][0] if args.probe_kind == "annotation" else plan["jobs"]["scene_order"][0],
        "maximum_scene_calls": 0 if args.probe_kind == "annotation" else 1,
        "maximum_annotation_calls": 1 if args.probe_kind == "annotation" else 0,
        "maximum_total_future_calls": 1,
        "network_permitted": False,
        "downloads_permitted": False,
        "gt_permitted": False,
        "rankings_permitted": False,
        "osm_permitted": False,
        "h38_h61_permitted": False,
        "ct2l_permitted": False,
        "claims_permitted": False,
        "reranking_permitted": False,
        "training_permitted": False,
        "fine_tuning_permitted": False,
        "human_review_required": True,
    }
    write(root / "probe-authorization.request.json", authorization)
    print(json.dumps({"plan_id": plan["plan_id"], "probe_calls": 1, "approved": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
