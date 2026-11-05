#!/usr/bin/env python3
"""CLI de un turno para el MVP interactivo; modo fake por defecto y sin GPU."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.tfg_phase0.crosstext2loc_runtime import CrossText2LocRetriever, load_runtime_config
from src.tfg_phase0.f5_text_transform import QwenTransformersAdapter
from src.tfg_phase0.interactive_dialogue import (
    DialoguePolicyConfig,
    F3EvidenceIndex,
    FakeTextDialogueAdapter,
    OneTurnDialogueOrchestrator,
    QWEN_MODEL_ID,
    QWEN_REVISION,
    QwenDialogueAdapter,
    ResidentCT2LAdapter,
    write_session,
)
from src.tfg_phase0.interactive_dialogue_multiturn import (
    MultiTurnConfig,
    MultiTurnDialogueOrchestrator,
    write_multiturn_session,
)
from src.tfg_phase0.dialogue_visual_evidence import FakeVisualEvidenceProvider, RealQwen3VLDialogueEvidenceProvider, VisualEvidencePolicy, VisualImageReference, file_sha256, load_observer_image_manifest
from src.tfg_phase0.interactive_dialogue_visual import VisualMultiTurnConfig, VisualMultiTurnDialogueOrchestrator, write_visual_session


class FakeRetriever:
    """Galería CPU pequeña para validar el flujo, no la calidad geográfica."""

    gallery_id = "fake-d004"

    def __init__(self):
        self.calls: list[str] = []
        self._rows = [
            ("fake-a", 40.41600, -3.70600),
            ("fake-b", 40.41605, -3.70595),
            ("fake-c", 40.41750, -3.70400),
            ("fake-d", 40.41900, -3.70200),
        ]

    @property
    def metadata(self) -> Mapping[str, Any]:
        ids = sorted(row[0] for row in self._rows)
        universe = hashlib.sha256(json.dumps(ids, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"adapter": "fake-ct2l-cpu-v1", "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "text_context_tokens": 300, "truncate": True, "truncation_side": "right", "real_model_inference": False, "expected_gallery_count": len(ids), "candidate_universe_sha256": universe, "catalog_manifest_id": "fake-catalog", "catalog_manifest_sha256": "0" * 64, "embedding_dataset_id": "fake-embeddings", "checkpoint_sha256": "0" * 64, "model_name": "fake-ct2l", "cvg_utils_sha256": "0" * 64}

    def retrieve_full(self, *, query_id: str, text: str, language: str) -> dict[str, Any]:
        self.calls.append(text)
        scores = {"fake-a": .92, "fake-b": .90, "fake-c": .81, "fake-d": .70}
        if "iglesia" in text.casefold():
            scores["fake-c"] = .97
        ordered = sorted(self._rows, key=lambda row: (-scores[row[0]], row[0]))
        return {
            "gallery_id": self.gallery_id,
            "visual_dataset_id": "fake-visual",
            "embedding_dataset_id": "fake-embeddings",
            "gallery_count": len(ordered),
            "requested_k": len(ordered),
            "effective_k": len(ordered),
            "ranking_method": "exhaustive_cosine",
            "tie_break": "candidate_id_ascending",
            "results": [
                {"rank": index, "candidate_id": candidate_id, "latitude": latitude, "longitude": longitude, "cosine_similarity": scores[candidate_id]}
                for index, (candidate_id, latitude, longitude) in enumerate(ordered, start=1)
            ],
        }


def fake_evidence() -> F3EvidenceIndex:
    objects = [
        {"osm_ref": "node/1", "osm_type": "node", "osm_id": 1, "geometry_status": "valid", "geometry_role": "point", "tags": {"amenity": "place_of_worship"}},
        {"osm_ref": "node/2", "osm_type": "node", "osm_id": 2, "geometry_status": "valid", "geometry_role": "point", "tags": {"historic": "monument"}},
    ]
    base = {"contains": False, "within": True, "crosses": False, "touches": False, "overlaps": False, "intersects": True, "boundary_contact_only": False, "center_distance_m": 5.0}
    associations = [
        {"candidate_id": "fake-c", "osm_ref": "node/1", **base},
        {"candidate_id": "fake-d", "osm_ref": "node/2", **base},
    ]
    return F3EvidenceIndex.from_documents(dataset_id="fake-f3-cpu", objects=objects, associations=associations)


def load_policy(path: Path) -> tuple[str, DialoguePolicyConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    common = {
        "schema_version", "contract_version", "gallery_id", "reserve_size",
        "cluster_radius_m", "minimum_hypotheses", "minimum_supported_hypotheses",
        "maximum_supported_fraction", "allow_qwen_question",
        "enable_controlled_rewrite", "absence_semantics", "vlm_enabled",
    }
    legacy = raw.get("contract_version") == "interactive-dialogue-policy-config-v1" and set(raw) == common | {"turn_limit"} and raw.get("turn_limit") == 1
    current = raw.get("contract_version") == "interactive-dialogue-policy-config-v2" and set(raw) == common | {"max_questions"} and raw.get("max_questions") in {1, 2, 3}
    if raw.get("schema_version") != "1.0" or not (legacy or current) or raw["vlm_enabled"] is not False or raw["absence_semantics"] != "unknown_not_contradicted":
        raise ValueError("configuración interactiva incompatible")
    return raw["gallery_id"], DialoguePolicyConfig(
        reserve_size=raw["reserve_size"],
        cluster_radius_m=raw["cluster_radius_m"],
        minimum_hypotheses=raw["minimum_hypotheses"],
        minimum_supported_hypotheses=raw["minimum_supported_hypotheses"],
        maximum_supported_fraction=raw["maximum_supported_fraction"],
        allow_qwen_question=raw["allow_qwen_question"],
        enable_controlled_rewrite=raw["enable_controlled_rewrite"],
    )


def load_multiturn_policy(path: Path, override: int | None = None) -> tuple[str, MultiTurnConfig]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    gallery_id, policy = load_policy(path)
    configured = raw.get("max_questions", raw.get("turn_limit", 1))
    return gallery_id, MultiTurnConfig(max_questions=override if override is not None else configured, policy=policy)


def build_real_components(args: argparse.Namespace, gallery_id: str):
    if args.f3_bundle is None or args.cvg_utils_sha256 is None or args.clip_weights is None:
        raise ValueError("modo real requiere --f3-bundle, --cvg-utils-sha256 y --clip-weights")
    model, galleries = load_runtime_config(args.ct2l_config, project_root=ROOT, cvg_utils_sha256=args.cvg_utils_sha256, clip_weights_path=args.clip_weights)
    selected = [value for value in galleries if value.gallery_id == gallery_id]
    if len(selected) != 1:
        raise ValueError(f"galería no configurada: {gallery_id}")
    runtime = CrossText2LocRetriever.load(model_config=model, gallery_configs=selected, region_config=ROOT / "config/madrid.yaml")
    evidence = F3EvidenceIndex.load_bundle(args.f3_bundle)
    runtime_catalog_id = json.loads(selected[0].catalog_manifest.read_text(encoding="utf-8"))["manifest_id"]
    runtime_catalog_sha256 = runtime._galleries[gallery_id].catalog.sha256
    catalog_candidate_ids = {candidate.candidate_id for candidate in runtime._galleries[gallery_id].catalog.candidates}
    if evidence.catalog_manifest_id != runtime_catalog_id or evidence.catalog_manifest_sha256 != runtime_catalog_sha256 or not set(evidence.features_by_candidate) <= catalog_candidate_ids:
        runtime.close()
        raise ValueError("el bundle F3 no corresponde al catálogo CT2L configurado")
    qwen_runtime = None
    text_adapter = None
    if args.qwen_model_dir is not None:
        qwen_runtime = QwenTransformersAdapter(args.qwen_model_dir, model_id=QWEN_MODEL_ID, revision=QWEN_REVISION)
        text_adapter = QwenDialogueAdapter(qwen_runtime)
    return ResidentCT2LAdapter(runtime, gallery_id), evidence, text_adapter, (runtime, qwen_runtime)


def print_summary(session: Mapping[str, Any]) -> None:
    initial = session["initial_ranking"]["results"][:5]
    print("\nTop-5 inicial:")
    for row in initial:
        print(f"  {row['rank']}. {row['candidate_id']} ({row['cosine_similarity']:.4f})")
    for value in session["updated_rankings"]:
        print(f"\nTop-5 posterior [{value['variant']}]:")
        for row in value["ranking"]["results"][:5]:
            print(f"  {row['rank']}. {row['candidate_id']} ({row['cosine_similarity']:.4f})")
    for comparison in session["comparisons"]:
        print(f"\nCambio técnico [{comparison['variant']}]: top1_changed={comparison['top1_changed']}, entradas Top-10={comparison['top10_entered']}, candidatos con cambio de rango={comparison['changed_candidate_count']}")
    print("No se ha evaluado mejora geográfica: el pipeline no recibe ground truth.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("fake", "real"), default="fake")
    parser.add_argument("--policy", type=Path, default=ROOT / "config/interactive_dialogue_multiturn.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--description")
    parser.add_argument("--answer")
    parser.add_argument("--answers", nargs="*", help="Respuestas técnicas en orden; si faltan se solicitan por terminal.")
    parser.add_argument("--max-questions", type=int, choices=(1, 2, 3))
    parser.add_argument("--legacy-one-turn", action="store_true", help="Escribe el contrato histórico v1.")
    parser.add_argument("--fake-visual-manifest", type=Path, help="Manifest local autorizado; solo modo fake CPU y contrato v3.")
    parser.add_argument("--visual-image-manifest", type=Path, help="Manifest observer_view autorizado; solo modo real.")
    parser.add_argument("--authorize-visual-gpu", action="store_true", help="Autoriza explícitamente una única inferencia visual aislada.")
    parser.add_argument("--visual-worker-output", type=Path, help="Directorio nuevo para preflight y artefactos del worker visual.")
    parser.add_argument("--visual-model-dir", type=Path, help="Snapshot local exacto de Qwen3-VL-8B.")
    parser.add_argument("--visual-docker-image", default="qwen3-vl-dialogue-worker:lmfe-0.11.3-tf5.9-v1")
    parser.add_argument("--fake-visual-state", choices=("supported", "contradicted", "unverifiable"), default="unverifiable")
    parser.add_argument("--session-label", default="interactive-cli")
    parser.add_argument("--ct2l-config", type=Path, default=ROOT / "config/madrid_f46_retriever.json")
    parser.add_argument("--f3-bundle", type=Path)
    parser.add_argument("--cvg-utils-sha256")
    parser.add_argument("--clip-weights", type=Path)
    parser.add_argument("--qwen-model-dir", type=Path, help="Snapshot local exacto; no se descarga nada.")
    args = parser.parse_args()
    if args.fake_visual_manifest is not None and (args.mode != "fake" or args.legacy_one_turn):
        parser.error("la evidencia visual fake solo está disponible en modo fake multivuelta")
    if args.fake_visual_manifest is not None and args.visual_image_manifest is not None:parser.error("los manifests visuales fake y real son mutuamente excluyentes")
    if args.visual_image_manifest is not None and (args.mode!="real" or args.legacy_one_turn):parser.error("el manifest observer_view real exige modo real multivuelta")
    if args.visual_image_manifest is not None and (not args.authorize_visual_gpu or args.visual_worker_output is None or args.visual_model_dir is None):parser.error("la evidencia visual real exige --authorize-visual-gpu, --visual-worker-output y --visual-model-dir")
    if args.authorize_visual_gpu and args.visual_image_manifest is None:parser.error("--authorize-visual-gpu exige --visual-image-manifest")

    if args.legacy_one_turn:
        gallery_id, config = load_policy(args.policy)
        multiturn_config = None
    else:
        gallery_id, multiturn_config = load_multiturn_policy(args.policy, args.max_questions)
        config = multiturn_config.policy
    resources = ()
    if args.mode == "fake":
        retriever, evidence = FakeRetriever(), fake_evidence()
        text_adapter = FakeTextDialogueAdapter()
    else:
        retriever, evidence, text_adapter, resources = build_real_components(args, gallery_id)
    try:
        description = args.description if args.description is not None else input("Descripción inicial: ")
        if args.legacy_one_turn:
            orchestrator = OneTurnDialogueOrchestrator(retriever=retriever, evidence=evidence, config=config, text_adapter=text_adapter)
            session = orchestrator.start(session_label=args.session_label, description=description)
            if session["status"] == "awaiting_answer":
                print(f"\nPregunta: {session['selected_question']['question']}")
                answer = args.answer if args.answer is not None else input("Respuesta: ")
                session = orchestrator.answer(session, answer)
            session_path, events_path = write_session(session, args.output_dir)
            print_summary(session)
        else:
            visual_mode = args.fake_visual_manifest is not None or args.visual_image_manifest is not None
            if args.fake_visual_manifest is not None:
                manifest=json.loads(args.fake_visual_manifest.read_text(encoding="utf-8"));required={"contract_version","image_id","logical_path","sha256","provenance","authorized","authorization_id","observer_relation"}
                if set(manifest)!=required or manifest["contract_version"]!="dialogue-fake-visual-image-v1" or manifest["authorized"] is not True or not manifest["authorization_id"]:raise ValueError("manifest visual fake no autorizado")
                image_path=(args.fake_visual_manifest.parent/manifest["logical_path"]).resolve()
                if not image_path.is_file() or file_sha256(image_path)!=manifest["sha256"]:raise ValueError("fixture visual fake ausente o alterado")
                reference=VisualImageReference(manifest["image_id"],image_path,manifest["sha256"],manifest["provenance"],True,manifest["authorization_id"],manifest["observer_relation"])
                features=("square","church","monument","intersection","park","commercial");scenario={"state":args.fake_visual_state,"observed_evidence":"evidencia visual fake" if args.fake_visual_state!="unverifiable" else None,"reason":"cli_scripted_unverifiable" if args.fake_visual_state=="unverifiable" else None};provider=FakeVisualEvidenceProvider(images={feature:reference for feature in features},scenarios={feature:scenario for feature in features})
                orchestrator = VisualMultiTurnDialogueOrchestrator(retriever=retriever,evidence=evidence,config=VisualMultiTurnConfig(multiturn_config,VisualEvidencePolicy(enabled=True)),text_adapter=text_adapter,visual_provider=provider)
            elif args.visual_image_manifest is not None:
                from scripts.run_dialogue_visual_worker import ExternalQwen3VLWorkerExecutor
                manifest,reference=load_observer_image_manifest(args.visual_image_manifest,ROOT/"schemas/dialogue_observer_image_manifest.schema.json")
                executor=ExternalQwen3VLWorkerExecutor(output_root=args.visual_worker_output,model_dir=args.visual_model_dir,docker_image=args.visual_docker_image)
                provider=RealQwen3VLDialogueEvidenceProvider(manifest=manifest,reference=reference,executor=executor)
                orchestrator=VisualMultiTurnDialogueOrchestrator(retriever=retriever,evidence=evidence,config=VisualMultiTurnConfig(multiturn_config,VisualEvidencePolicy(enabled=True)),text_adapter=text_adapter,visual_provider=provider)
            else:
                orchestrator = MultiTurnDialogueOrchestrator(retriever=retriever, evidence=evidence, config=multiturn_config, text_adapter=text_adapter)
            session = orchestrator.start(session_label=args.session_label, description=description)
            supplied = list(args.answers if args.answers is not None else ([args.answer] if args.answer is not None else []))
            while session["status"] == "awaiting_answer":
                turn = session["turns"][-1]
                print(f"\nPregunta {turn['index']}/{session['max_questions']}: {turn['question']['final_question']}")
                answer = supplied.pop(0) if supplied else input("Respuesta (o 'terminar'): ")
                session = orchestrator.answer(session, answer)
                ranking = session["current_ranking"]["results"][:5]
                print("Top-5 técnico actual:")
                for row in ranking:
                    print(f"  {row['rank']}. {row['candidate_id']} ({row['cosine_similarity']:.4f})")
            print(f"\nFin: {session['stop_reason']}. No se ha evaluado mejora geográfica.")
            session_path, events_path = (write_visual_session(session,args.output_dir) if visual_mode else write_multiturn_session(session, args.output_dir))
        print(f"\nSesión: {session_path}\nEventos: {events_path}")
    finally:
        for resource in reversed(resources):
            if resource is not None:
                resource.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
