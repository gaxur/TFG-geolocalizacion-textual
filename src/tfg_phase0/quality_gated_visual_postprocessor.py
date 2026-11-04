"""VisualPostprocessor composable with quality gate before unchanged reranking."""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from .visual_postprocessor import VisualPostprocessorError, query_identity
from .visual_quality_gate import run_quality_replacement


class QualityGatedVisualPostprocessor:
    """Orquesta reservas/calidad/claims; la política de ranking se inyecta sin alterarla."""

    def __init__(self, *, reserve_k: int, policy: Mapping[str,Any], reserve_source: Callable[...,Mapping[str,Any]], resolver, quality_verifier, claims_source: Callable[[str],Mapping[str,Sequence[Mapping[str,Any]]]], claim_verifier, ranking_policy: Callable[[Mapping[str,Any],Mapping[str,Any]],Mapping[str,Any]], quality_cache: Mapping[str,Mapping[str,Any]] | None = None, mode: str = "offline"):
        if reserve_k<10:raise VisualPostprocessorError("reserva de calidad menor que Top-10")
        self._reserve_k=reserve_k;self._policy=dict(policy);self._reserve_source=reserve_source;self._resolver=resolver;self._quality_verifier=quality_verifier;self._claims_source=claims_source;self._claim_verifier=claim_verifier;self._ranking_policy=ranking_policy;self._quality_cache=dict(quality_cache or {});self._mode=mode

    @property
    def reserve_k(self)->int:return self._reserve_k

    @property
    def metadata(self)->Mapping[str,Any]:
        return {"provider":"quality_gated_mapillary_qwen3_vl","reserve_k":self._reserve_k,"quality_enabled":bool(self._policy.get("enabled")),"quality_model":dict(self._quality_verifier.metadata),"mode":self._mode}

    def apply(self, *, query_text: str, processing_variant: str, retrieval: Mapping[str,Any])->Mapping[str,Any]:
        reserve=list(retrieval["results"]);baseline=reserve[:10];request_id=query_identity(query_text,processing_variant,retrieval)
        if not self._policy.get("enabled"):
            return {"status":"fallback_baseline","source":"quality_gated","request_id":request_id,"reason":"visual_quality_gate_disabled","model":None,"policy_id":None,"baseline_results":baseline,"final_results":baseline,"evidence":[],"quality_pipeline":None}
        plan=self._reserve_source(query_text=query_text,processing_variant=processing_variant,retrieval=retrieval)
        candidate_ids={row["candidate_id"] for row in reserve}
        if set(row["candidate_id"] for row in plan["reserves"])-candidate_ids:raise VisualPostprocessorError("plan visual contiene candidato fuera de reserva CT2L")
        claims=self._claims_source(query_text)
        pipeline=run_quality_replacement(reserves=plan["reserves"],claims_by_candidate=claims,policy=self._policy,resolver=self._resolver,quality_verifier=self._quality_verifier,claim_verifier=self._claim_verifier,quality_cache=self._quality_cache,mode=self._mode)
        accepted_candidates={row["candidate_id"] for row in pipeline["candidates"] if row["accepted_image_ids"]}
        if not accepted_candidates:
            return {"status":"fallback_baseline","source":"quality_gated","request_id":request_id,"reason":"no_accepted_visual_evidence","model":dict(self._quality_verifier.metadata),"policy_id":None,"baseline_results":baseline,"final_results":baseline,"evidence":[],"quality_pipeline":pipeline}
        ranked=self._ranking_policy(retrieval,pipeline)
        final=ranked.get("final_results")
        if not isinstance(final,list) or len(final)!=10 or len({row["candidate_id"] for row in final})!=10 or not {row["candidate_id"] for row in final}<=candidate_ids:raise VisualPostprocessorError("ranking visual de calidad incompatible")
        evidence_ids=set(ranked.get("evidence_candidate_ids",()))
        if not evidence_ids or not evidence_ids<=accepted_candidates:raise VisualPostprocessorError("ranking visual no declara evidencia ACCEPT válida")
        return {"status":"applied","source":"quality_gated","request_id":request_id,"reason":None,"model":dict(self._quality_verifier.metadata),"policy_id":ranked.get("policy_id"),"baseline_results":baseline,"final_results":final,"evidence":ranked.get("evidence",[]),"quality_pipeline":pipeline}

    def close(self)->None:
        self._quality_verifier.close()
