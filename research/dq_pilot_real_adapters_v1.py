"""Adapters reales preparados para DQ-PILOT.12; dependencias inyectadas, sin cargas implícitas."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from research.dialogue_visual_generative_v1 import build_cached_visual_context
from research.dq_pilot_iterative_controller_v1 import IterativeDialogueError, atomic_json, canonical, digest, digest_text, validate_ranking
from research.dq_pilot_zero_shot_v1 import build_native_messages, validate_native_question
from src.tfg_phase0.dialogue_freetext_v1 import build_freetext_prompt, render_literal_transcript, validate_full_ranking
from src.tfg_phase0.f5_text_transform import GenerationConfig, validate_transformation


QWEN_IDENTITY = {
    "model_id": "Qwen/Qwen3-8B",
    "revision": "b968826d9c46dd6066d109eabc6255188de91218",
    "artifact_manifest_sha256": "d95b2ee5a666c88adcb53094740c1002718f28e0dcabad56a508a9c66dce1570",
    "prompt_version": "dialogue-vpr-freetext-qwen-v1",
}
PROMPT_VERSION = "dialogue-vpr-freetext-qwen-v1"
CT2L_IDENTITY = {
    "gallery_id": "madrid-50m",
    "candidate_count": 253,
    "checkpoint_sha256": "d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d",
    "clip_sha256": "3035c92b350959924f9f00213499208652fc7ea050643e8b385c2dac08641f02",
    "cvg_commit": "6910d2747a94fbe985309bde60cd4732bcbbf50f",
    "ranking_method": "exhaustive_cosine",
    "tie_break": "candidate_id_ascending",
}


def _history_turns(history: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    turns = []
    for expected, row in enumerate(history, 1):
        if row.get("index") != expected or not row.get("question_es") or row.get("answer_literal") is None:
            raise IterativeDialogueError("historial pregunta-respuesta incompleto o desordenado")
        turns.append({
            "index": expected,
            "question": {"literal": row["question_es"]},
            "answer": {"literal": row["answer_literal"]},
        })
    return turns


class ResidentQwenFreetextPort:
    """Puente público; recibe un QwenTransformersAdapter ya cargado externamente."""

    def __init__(self, runtime):
        self.runtime = runtime

    def transform(self, *, stage: str, transcript: str, prompt: str) -> Mapping[str, Any]:
        started = time.perf_counter()
        result = self.runtime.generate_prompt(prompt, GenerationConfig())
        metadata = self.runtime.metadata.__dict__
        return {
            "schema_version": "1.0",
            "contract_version": "atlas-dialogue-freetext-en-v1",
            "stage": stage,
            "transcript_sha256": digest_text(transcript),
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": digest_text(prompt),
            "text": result.text,
            "raw_output": result.raw_output,
            "text_sha256": digest_text(result.text),
            "duration_ms": result.duration_ms,
            "port_wall_ms": (time.perf_counter() - started) * 1000,
            "model": dict(metadata),
        }


class ResidentCT2LPort:
    """Puente público; recibe un CrossText2LocRetriever ya cargado externamente."""

    def __init__(self, runtime):
        self.runtime = runtime

    def retrieve(self, *, stage: str, query_id: str, text: str) -> Mapping[str, Any]:
        return self.runtime.retrieve_many(gallery_ids=("madrid-50m",), query_id=query_id, text=text, language="en", k=253)


class RealTextInterpreterAdapter:
    """Proyecta InterpreterPort al Qwen port FreeText ya validado."""
    identity = {"adapter_id": "dq-pilot12-qwen-freetext-interpreter-v1", **QWEN_IDENTITY}

    def __init__(self, qwen_port):
        self.qwen_port = qwen_port

    def interpret(self, *, round_index: int, original_description: str, accumulated_description: str, dialogue_history: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        turns = _history_turns(dialogue_history)
        if round_index != len(turns):
            raise IterativeDialogueError("round LLM no coincide con respuestas disponibles")
        expected_accumulated = original_description + "".join(f"\nRespuesta {row['index']}: {row['answer_literal']}" for row in dialogue_history)
        if accumulated_description != expected_accumulated:
            raise IterativeDialogueError("descripción acumulada no corresponde al historial")
        transcript = render_literal_transcript(original_description, turns)
        prompt = build_freetext_prompt(transcript)
        stage = f"E{round_index}"
        output = dict(self.qwen_port.transform(stage=stage, transcript=transcript, prompt=prompt))
        if output.get("contract_version") != "atlas-dialogue-freetext-en-v1" or output.get("stage") != stage:
            raise IterativeDialogueError("output Qwen FreeText incompatible")
        if output.get("transcript_sha256") != digest_text(transcript) or output.get("prompt_sha256") != digest_text(prompt) or output.get("prompt_version") != PROMPT_VERSION:
            raise IterativeDialogueError("output Qwen no corresponde al transcript/prompt")
        model = output.get("model", {})
        required_model = {key: value for key, value in QWEN_IDENTITY.items() if key != "prompt_version"}
        if any(model.get(key) != value for key, value in required_model.items()) or model.get("real_model_inference") is not True:
            raise IterativeDialogueError("identidad Qwen FreeText incompatible")
        text = output.get("text")
        if not isinstance(text, str) or not text or hashlib.sha256(text.encode()).hexdigest() != output.get("text_sha256"):
            raise IterativeDialogueError("texto Qwen/hash inválido")
        validation = validate_transformation("\n".join([original_description, *[row["answer_literal"] for row in dialogue_history]]), text, "translate_en_cartographic", [], GenerationConfig())
        if validation["structurally_valid"] is not True:
            raise IterativeDialogueError("interpretación Qwen rechazada")
        return {
            "contract_version": "dq-pilot13-real-text-interpretation-v1",
            "round_index": round_index,
            "text": text,
            "text_sha256": output["text_sha256"],
            "raw_output_sha256": digest_text(str(output.get("raw_output", ""))),
            "transcript": transcript,
            "transcript_sha256": digest_text(transcript),
            "prompt_sha256": digest_text(prompt),
            "model": dict(model),
            "duration_ms": output.get("duration_ms"),
            "validation": validation,
            "dialogue_history_sha256": digest(list(dialogue_history)),
            "ground_truth_used": False,
        }


class RealCT2LRetrieverAdapter:
    """Proyecta RetrieverPort al CT2L port exhaustivo existente."""
    identity = {"adapter_id": "dq-pilot12-ct2l-exhaustive-madrid50-v1", **CT2L_IDENTITY}

    def __init__(self, retrieval_port, *, query_id: str, visual_dataset_id: str, embedding_dataset_id: str):
        self.retrieval_port = retrieval_port
        self.query_id = query_id
        self.visual_dataset_id = visual_dataset_id
        self.embedding_dataset_id = embedding_dataset_id
        self._candidate_universe: set[str] | None = None

    def retrieve(self, *, round_index: int, interpreted_text: str) -> Mapping[str, Any]:
        retrieval_query_id = f"{self.query_id}-E{round_index}"
        envelope = dict(self.retrieval_port.retrieve(stage=f"E{round_index}", query_id=retrieval_query_id, text=interpreted_text))
        if envelope.get("contract_version") != "crosstext2loc-retrieval-response-v1":
            raise IterativeDialogueError("envelope CT2L incompatible")
        if envelope.get("query") != {"query_id": retrieval_query_id, "text": interpreted_text, "language": "en"}:
            raise IterativeDialogueError("envelope CT2L no corresponde a la consulta")
        if envelope.get("model", {}).get("checkpoint_sha256") != CT2L_IDENTITY["checkpoint_sha256"] or len(envelope.get("retrievals", [])) != 1:
            raise IterativeDialogueError("identidad CT2L incompatible")
        ranking = dict(envelope["retrievals"][0])
        universe = validate_full_ranking(ranking, self._candidate_universe)
        self._candidate_universe = universe
        required = {"gallery_id": "madrid-50m", "gallery_count": 253, "requested_k": 253, "effective_k": 253, "ranking_method": "exhaustive_cosine", "tie_break": "candidate_id_ascending", "visual_dataset_id": self.visual_dataset_id, "embedding_dataset_id": self.embedding_dataset_id}
        if any(ranking.get(key) != value for key, value in required.items()):
            raise IterativeDialogueError("ranking CT2L no es exhaustivo/fijo")
        return {
            **ranking,
            "contract_version": "dq-pilot13-real-ct2l-ranking-v1",
            "source_contract_version": envelope["contract_version"],
            "round_index": round_index,
            "retrieval_query_id": retrieval_query_id,
            "interpreted_text_sha256": digest_text(interpreted_text),
            "model": dict(envelope["model"]),
            "timings_ms": dict(envelope.get("timings_ms", {})),
            "ground_truth_used": False,
        }


class MetadataOnlyMapillaryPanelAdapter:
    """Panel dinámico D109 metadata-only; exige 4/4 y conserva todas sus limitaciones."""
    identity = {"adapter_id": "dq-pilot12-mapillary-metadata-panel-v1", "policy": "top3_plus_spatial_farthest_first_without_gt", "quality_status": "metadata_geometry_only_not_representativeness_validated"}

    def __init__(self, *, catalog: Mapping[str, Any], inventory: Mapping[str, Any], cache_root: Path, original_description: str, session_id: str):
        self.catalog, self.inventory, self.cache_root = catalog, inventory, cache_root
        self.original_description, self.session_id = original_description, session_id

    def build(self, *, round_index: int, ranking: Mapping[str, Any], reserve: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        if len(reserve) != 20 or list(reserve) != list(ranking.get("results", []))[:20]:
            raise IterativeDialogueError("reserva Top-N no corresponde al ranking")
        context = build_cached_visual_context(session_id=self.session_id, iteration=round_index, description_original=self.original_description, description_effective="ranking-bound-panel-no-model-text", history=[], ranking=ranking, catalog=self.catalog, inventory=self.inventory, cache_root=self.cache_root, reserve_size=len(reserve), panel_candidates=4, protected_count=3, maximum_images=4, maximum_images_per_candidate=1, maximum_radius_m=100.0)
        ready = context["coverage_summary"] == {"requested_candidates": 4, "covered_candidates": 4, "selected_images": 4, "evidence_sufficient_for_vlm": True}
        candidates = []
        for index, row in enumerate(context["candidates"], 1):
            candidates.append({"candidate_ref": f"C{index}", "candidate_id": row["candidate_id"], "source_rank": row["ct2l_rank"], "coverage_status": row["coverage_status"]})
        candidate_ref = {row["candidate_id"]: row["candidate_ref"] for row in candidates}
        association_by_image = {row["image_id"]: row for row in context["associations"]}
        image_to_candidate = {image_id: candidate for candidate in context["candidates"] for image_id in candidate["selected_image_ids"]}
        images = []
        for index, image in enumerate(context["images"], 1):
            candidate = image_to_candidate[image["image_id"]]
            images.append({"candidate_ref": candidate_ref[candidate["candidate_id"]], "image_ref": f"I{index}", "image_id": image["image_id"], "logical_path": image["logical_path"], "sha256": image["sha256"], "size_bytes": image["size_bytes"], "association": association_by_image[image["image_id"]]})
        return {"contract_version": "dq-pilot13-mapillary-panel-v1", "status": "prepared_pending_review" if ready else "insufficient_visual_evidence", "review_required": ready, "round_index": round_index, "source_ranking_sha256": digest(ranking), "candidate_ids": [row["candidate_id"] for row in candidates], "candidates": candidates, "images": images, "selection_trace": context["selection"], "coverage": {**context["coverage_summary"], "meaning": "metadata_assignment_only_not_visual_sufficiency"}, "limitations": ["atlas_zero_shot_top3_plus_diversity_not_official_top4", "metadata_geometry_only", "quality_score_not_semantically_validated", "geometric_compatibility_not_visibility", "representativeness_not_validated", "orientation_and_panorama_require_review", "dynamic_panel_not_d112_strict"], "ground_truth_used": False}


def native_dialogue_history(original_description: str, history: Sequence[Mapping[str, Any]]) -> str:
    parts = [f"Witness: {original_description}"]
    for expected, row in enumerate(history, 1):
        if row.get("index") != expected or not row.get("question_original") or row.get("answer_literal") is None:
            raise IterativeDialogueError("historial nativo incompleto")
        parts.extend([f"You: {row['question_original']}", f"Witness: {row['answer_literal']}"])
    return "\n".join(parts)


def native_round_request(*, session_id, query_id, round_index, panel, blind_images, original_description, dialogue_history, expectation):
    """El mismo documento que consume el worker oficial; no carga modelos."""
    history = native_dialogue_history(original_description, dialogue_history)
    native = build_native_messages(image_refs=["I1", "I2", "I3", "I4"], dialogue_history=history, seed=42)
    request = {"schema_version":"1.0","contract_version":"dq-pilot13-native-round-request-v1","session_id":session_id,"query_id":query_id,"round_index":round_index,"source_ranking_sha256":panel["source_ranking_sha256"],"source_panel_sha256":digest(panel),"history":{"native_text":history,"sha256":digest_text(history),"turn_count":len(dialogue_history),"prior_questions":[row["question_original"] for row in dialogue_history]},"images":blind_images,"native_messages":native["messages"],"native_prompt_identity":{key:native[key] for key in ("instruction_index","instruction_sha256","system_prompt_sha256","seed")},"generation":{"do_sample":False,"num_beams":1,"max_new_tokens":1024,"repetition_penalty":1.05,"eos_token_ids":[151645,151643],"pad_token_id":151643,"use_cache":True,"automatic_retries":0,"fallbacks":0},"constraints":{"ground_truth_used":False,"coordinates_sent":False,"ranks_sent":False,"scores_sent":False,"answerer_used":False,"cmpl_used":False,"question_templates_used":False,"translation_performed":False},"processor_expectation":expectation}
    request["request_id"] = "dq-pilot13-round-request-sha256-" + digest(request)
    return request


class PreparedDQPilotQuestionerAdapter:
    """Prepara request DQ-Pilot dinámico; ejecutor externo opcional e idempotente."""
    identity = {"adapter_id": "dq-pilot12-official-questioner-four-image-v1", "model_id": "graysonggg/dlgpr", "revision": "cf5c7b8a79ce055a83706fcbe0b94edf31b1cb40", "native_stop_supported": False}

    def __init__(self, *, cache_root: Path, execution_port=None, processor_expectation_resolver=None):
        self.cache_root, self.execution_port, self.processor_expectation_resolver = cache_root.resolve(), execution_port, processor_expectation_resolver

    @staticmethod
    def _validate_projection(projection: Mapping[str, Any], *, request_sha256: str, panel: Mapping[str, Any]) -> None:
        if projection.get("contract_version") != "dq-pilot14-public-generation-v1" or projection.get("status") not in {"generated", "host_rejected"}:
            raise IterativeDialogueError("proyección DQ incompatible")
        if projection.get("request_sha256") != request_sha256 or projection.get("panel_sha256") != digest(panel) or projection.get("source_ranking_sha256") != panel["source_ranking_sha256"]:
            raise IterativeDialogueError("ejecución DQ no corresponde al request/panel/ranking")
        if projection.get("status") == "generated" and (not projection.get("question") or not projection.get("raw_output_sha256") or not projection.get("telemetry_sha256")):
            raise IterativeDialogueError("proyección DQ incompleta")
        if projection.get("status") == "host_rejected" and (projection.get("question") is not None or not projection.get("host_decision_sha256") or not projection.get("terminal_commit_sha256")):
            raise IterativeDialogueError("rechazo host incompleto")
        if projection.get("reasoning_public") is not False or projection.get("private_output_retained") is not True or "raw_output" in projection:
            raise IterativeDialogueError("frontera privada DQ violada")

    def generate(self, *, session_id: str, query_id: str, round_index: int, panel: Mapping[str, Any], original_description: str, dialogue_history: Sequence[Mapping[str, Any]], operation_root: Path) -> Mapping[str, Any]:
        operation_root.mkdir(parents=True, exist_ok=True)
        completion = operation_root / "generation-projection.json"
        runtime_completion = operation_root / "runtime" / "generation-projection.json"
        if completion.is_file():
            projection = json.loads(completion.read_text())
            request_path = operation_root / "request.json"
            if not request_path.is_file():
                raise IterativeDialogueError("request DQ ausente durante resume")
            self._validate_projection(projection, request_sha256=hashlib.sha256(request_path.read_bytes()).hexdigest(), panel=panel)
            return projection
        if runtime_completion.is_file():
            request_path = operation_root / "request.json"
            if not request_path.is_file(): raise IterativeDialogueError("request DQ ausente durante resume runtime")
            projection=json.loads(runtime_completion.read_text());self._validate_projection(projection,request_sha256=hashlib.sha256(request_path.read_bytes()).hexdigest(),panel=panel);atomic_json(completion,projection);return projection
        if panel.get("status") != "ready" or len(panel.get("candidates", [])) != 4 or len(panel.get("images", [])) != 4:
            raise IterativeDialogueError("DQ-Pilot requiere panel exacto 4/4")
        if panel.get("round_index") != round_index:
            raise IterativeDialogueError("panel pertenece a otra ronda")
        media = operation_root / "media";media.mkdir(exist_ok=True)
        blind_images=[];private=[]
        candidate_ids = [row.get("candidate_id") for row in panel["candidates"]]
        if panel.get("candidate_ids") != candidate_ids or len(set(candidate_ids)) != 4 or [row.get("candidate_ref") for row in panel["candidates"]] != ["C1", "C2", "C3", "C4"]:
            raise IterativeDialogueError("candidatos DQ no forman una biyección 4/4")
        image_ids = [row.get("image_id") for row in panel["images"]]
        image_hashes = [row.get("sha256") for row in panel["images"]]
        if len(set(image_ids)) != 4 or len(set(image_hashes)) != 4:
            raise IterativeDialogueError("imágenes DQ no son físicamente únicas")
        for index, image in enumerate(panel["images"], 1):
            if image.get("image_ref") != f"I{index}" or image.get("candidate_ref") != f"C{index}":
                raise IterativeDialogueError("orden candidato-imagen DQ divergente")
            source=(self.cache_root/str(image["logical_path"])).resolve()
            if self.cache_root not in source.parents or not source.is_file() or source.is_symlink() or hashlib.sha256(source.read_bytes()).hexdigest()!=image["sha256"] or source.stat().st_size!=image["size_bytes"]:
                raise IterativeDialogueError("bytes Mapillary divergentes")
            target=media/f"I{index}{source.suffix}"
            if target.exists():
                if target.is_symlink() or hashlib.sha256(target.read_bytes()).hexdigest() != image["sha256"]:
                    raise IterativeDialogueError("media DQ preexistente divergente")
            else:
                temporary=target.with_name(f".{target.name}.{os.getpid()}.tmp")
                try:
                    with source.open("rb") as input_stream, temporary.open("xb") as output_stream:
                        shutil.copyfileobj(input_stream,output_stream)
                        output_stream.flush();os.fsync(output_stream.fileno())
                    if hashlib.sha256(temporary.read_bytes()).hexdigest()!=image["sha256"] or temporary.stat().st_size!=image["size_bytes"]:
                        raise IterativeDialogueError("copia media DQ divergente")
                    os.replace(temporary,target)
                finally:
                    temporary.unlink(missing_ok=True)
            blind_images.append({"candidate_ref":f"C{index}","image_ref":f"I{index}","logical_path":f"media/{target.name}","sha256":image["sha256"],"size_bytes":image["size_bytes"]})
            private.append({"candidate_ref":f"C{index}","image_ref":f"I{index}","candidate_id":panel["candidates"][index-1]["candidate_id"],"image_id":image["image_id"]})
        expectation=self.processor_expectation_resolver(round_index=round_index,panel=panel,history=dialogue_history) if self.processor_expectation_resolver is not None else None
        request=native_round_request(session_id=session_id,query_id=query_id,round_index=round_index,panel=panel,blind_images=blind_images,original_description=original_description,dialogue_history=dialogue_history,expectation=expectation)
        atomic_json(operation_root/"request.json", request)
        atomic_json(operation_root/"private-lineage.json", {"records":private,"source_panel_sha256":digest(panel),"ground_truth_used":False})
        if self.execution_port is None:
            return {"contract_version":"dq-pilot13-round-generation-v1","status":"prepared_not_executed","question":None,"request_sha256":hashlib.sha256((operation_root/"request.json").read_bytes()).hexdigest(),"panel_sha256":digest(panel),"source_ranking_sha256":panel["source_ranking_sha256"],"operation_root":str(operation_root),"ground_truth_used":False,"automatic_approval":False}
        projection=dict(self.execution_port.execute(request_path=operation_root/"request.json",operation_root=operation_root))
        self._validate_projection(projection,request_sha256=hashlib.sha256((operation_root/"request.json").read_bytes()).hexdigest(),panel=panel)
        atomic_json(completion, projection);return projection


class DQPilotHostValidatorAdapter:
    """Validación automática; grounding real siempre requiere review panel-bound."""
    identity = {"adapter_id":"dq-pilot12-host-validator-v1","automatic_grounding_approval":False}

    def __init__(self, *, outcome_schema: Mapping[str, Any]): self.outcome_schema=outcome_schema
    def validate(self, *, session_id: str, query_id: str, round_index: int, panel: Mapping[str, Any], generation: Mapping[str, Any], accumulated_description: str, dialogue_history: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        if generation.get("status")=="host_rejected":
            return {"contract_version":"dq-pilot13-validation-v1","status":"invalid","question":None,"generation_sha256":digest(generation),"panel_sha256":digest(panel),"reason":"host_rejected:"+",".join(generation.get("host_validation",{}).get("reason_codes",[])),"automatic_approval":False,"ground_truth_used":False}
        if generation.get("status")!="generated":
            return {"contract_version":"dq-pilot13-validation-v1","status":"invalid","question":generation.get("question"),"generation_sha256":digest(generation),"panel_sha256":digest(panel),"reason":"generation_not_completed","automatic_approval":False}
        prior=[row["question_original"] for row in dialogue_history]
        if generation.get("raw_output"):
            try:checked=validate_native_question(generation["raw_output"],history_questions=prior,outcome_schema=self.outcome_schema)
            except Exception as error:return {"contract_version":"dq-pilot13-validation-v1","status":"invalid","question":generation.get("question"),"generation_sha256":digest(generation),"panel_sha256":digest(panel),"reason":type(error).__name__,"automatic_approval":False}
            question=checked["public_question"]
            if generation.get("question") != question:
                return {"contract_version":"dq-pilot13-validation-v1","status":"invalid","question":question,"generation_sha256":digest(generation),"panel_sha256":digest(panel),"reason":"projected_question_differs_from_native_output","automatic_approval":False,"ground_truth_used":False}
        else:
            checks=generation.get("host_validation",{})
            if checks != {"format":True,"text_safety":True,"exact_redundancy":True} or not generation.get("raw_output_sha256") or generation.get("reasoning_public") is not False or generation.get("private_output_retained") is not True:
                return {"contract_version":"dq-pilot13-validation-v1","status":"invalid","question":generation.get("question"),"generation_sha256":digest(generation),"panel_sha256":digest(panel),"reason":"private_worker_validation_missing","automatic_approval":False,"ground_truth_used":False}
            question=generation.get("question")
            if not isinstance(question,str) or not question:
                return {"contract_version":"dq-pilot13-validation-v1","status":"invalid","question":question,"generation_sha256":digest(generation),"panel_sha256":digest(panel),"reason":"public_question_missing","automatic_approval":False,"ground_truth_used":False}
        return {"contract_version":"dq-pilot13-validation-v1","status":"pending_review","question":question,"generation_sha256":digest(generation),"panel_sha256":digest(panel),"automatic_checks":{"format":True,"text_safety":True,"exact_redundancy":True},"perceptual_checks":{"grounded":"pending","discriminative":"pending","user_answerable":"pending","novel":"pending"},"automatic_approval":False,"ground_truth_used":False}


class PendingSpanishTranslatorAdapter:
    """No hay traductor EN-ES local validado; falla antes de presentar."""
    identity = {"translator_id":None,"version":None,"runtime":None,"status":"candidate_not_selected_no_validated_local_model","local":False,"candidate":"Helsinki-NLP/opus-mt-en-es"}
    def translate(self, *, round_index: int, question: str) -> Mapping[str, Any]:
        raise IterativeDialogueError("no existe un traductor EN-ES local, fijado y validado; traducción bloqueada")


PendingMarianTranslatorAdapter = PendingSpanishTranslatorAdapter
