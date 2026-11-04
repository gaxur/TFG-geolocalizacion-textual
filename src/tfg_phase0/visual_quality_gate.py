"""Quality gate and bounded replacement before visual claim verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Protocol, Sequence

from .f4_evaluation import haversine_m
from .mapillary_visual_pilot import angular_difference, bearing_degrees, reject_ground_truth


DECISIONS = {"ACCEPT", "REVIEW", "REJECT"}
REASONS = {"USABLE_SCENE", "BLUR", "UNDEREXPOSED", "OVEREXPOSED", "LOW_CONTRAST", "OCCLUDED", "OBSTRUCTED_LENS", "SEVERE_ARTIFACTS", "SCENE_NOT_OBSERVABLE", "PARTIAL_SCENE", "AMBIGUOUS_QUALITY"}
REJECT_REASONS = REASONS - {"USABLE_SCENE", "PARTIAL_SCENE", "AMBIGUOUS_QUALITY"}


class VisualQualityError(ValueError):
    pass


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def quality_schema() -> dict[str, Any]:
    return {"type":"object","additionalProperties":False,"required":["decision","reason_codes"],"properties":{"decision":{"enum":["ACCEPT","REVIEW","REJECT"]},"reason_codes":{"type":"array","maxItems":4,"uniqueItems":True,"items":{"enum":sorted(REASONS)}}}}


def quality_prompt() -> str:
    return (
        "Evalúa únicamente la calidad técnica general de esta fotografía para una inspección visual posterior. "
        "No recibes descripción, claim, candidato, ranking, coordenadas ni ground truth. "
        "ACCEPT: escena suficientemente nítida, expuesta y observable. "
        "REVIEW: caso limítrofe o parcialmente útil. REJECT: desenfoque severo, oscuridad/sobreexposición severa, "
        "lente obstruida, artefactos severos u escena esencialmente no observable. "
        "No rechaces por ser una escena genérica ni por no mostrar un objeto concreto. "
        "Devuelve solo JSON estricto con decision y reason_codes."
    )


def parse_quality_decision(raw: str) -> dict[str, Any]:
    if raw != raw.strip() or raw.startswith("```") or len(raw) > 300:
        raise VisualQualityError("salida de calidad no es JSON estricto")
    try: value=json.loads(raw)
    except json.JSONDecodeError as error: raise VisualQualityError("salida de calidad no es JSON") from error
    if not isinstance(value,dict) or set(value)!={"decision","reason_codes"} or value["decision"] not in DECISIONS or not isinstance(value["reason_codes"],list) or len(value["reason_codes"])>4 or len(value["reason_codes"])!=len(set(value["reason_codes"])) or not set(value["reason_codes"])<=REASONS:
        raise VisualQualityError("decisión de calidad incompatible")
    reasons=set(value["reason_codes"])
    if value["decision"]=="ACCEPT" and reasons!={"USABLE_SCENE"}:raise VisualQualityError("ACCEPT exige USABLE_SCENE único")
    if value["decision"]=="REJECT" and not reasons.intersection(REJECT_REASONS):raise VisualQualityError("REJECT sin motivo técnico severo")
    if value["decision"]=="REVIEW" and not reasons.intersection({"PARTIAL_SCENE","AMBIGUOUS_QUALITY"}):raise VisualQualityError("REVIEW sin ambigüedad explícita")
    return {"decision":value["decision"],"reason_codes":sorted(reasons)}


def quality_task_id(*, image_sha256: str, model: Mapping[str,Any], prompt: str | None = None, schema: Mapping[str,Any] | None = None) -> str:
    if len(image_sha256)!=64:raise VisualQualityError("SHA-256 de imagen inválido")
    prompt=prompt or quality_prompt();schema=schema or quality_schema();payload={"contract_version":"visual-image-quality-task-v1","image_sha256":image_sha256,"model_id":model["model_id"],"revision":model["revision"],"weight_sha256":model["weight_sha256"],"dtype":model.get("dtype","bfloat16"),"attention":model.get("attention","sdpa"),"prompt_version":model.get("prompt_version","visual-image-quality-v1"),"prompt_sha256":hashlib.sha256(prompt.encode()).hexdigest(),"schema_sha256":hashlib.sha256(canonical_bytes(schema)).hexdigest(),"generation":model.get("generation",{"do_sample":False,"max_new_tokens":48,"batch_size":1}),"preprocessing_policy":model.get("preprocessing_policy","qwen3-vl-auto-processor-local-files-only-v1")};return "visual-quality-task-sha256-"+hashlib.sha256(canonical_bytes(payload)).hexdigest()


def refresh_run_id(document: Mapping[str,Any]) -> str:
    return "visual-quality-run-sha256-"+hashlib.sha256(canonical_bytes({key:value for key,value in document.items() if key!="run_id"})).hexdigest()


@dataclass(frozen=True)
class ResolvedAsset:
    image_id: str
    image_sha256: str
    path: Path
    source: str
    downloaded: bool = False
    size_bytes: int = 0


class AssetResolver(Protocol):
    def resolve(self, reserve: Mapping[str,Any], *, mode: str, maximum_bytes: int) -> ResolvedAsset | None: ...


class QualityVerifier(Protocol):
    @property
    def metadata(self) -> Mapping[str,Any]: ...
    def evaluate(self, *, image_path: Path) -> Mapping[str,Any]: ...
    def close(self) -> None: ...


class ClaimVerifier(Protocol):
    def verify(self, *, candidate_id: str, asset: ResolvedAsset, claims: Sequence[Mapping[str,Any]]) -> Sequence[Mapping[str,Any]]: ...


class ManifestAssetResolver:
    """Resolver offline/fixture por manifest inmutable; nunca abre red."""

    def __init__(self, assets: Mapping[str,Mapping[str,Any]], *, root: Path):
        self._assets={str(key):dict(value) for key,value in assets.items()};self._root=root.resolve()

    def is_cached(self, reserve: Mapping[str,Any]) -> bool:
        return str(reserve["image_id"]) in self._assets

    def resolve(self, reserve: Mapping[str,Any], *, mode: str, maximum_bytes: int) -> ResolvedAsset | None:
        if mode not in {"offline","fixture"}:raise VisualQualityError("resolver de manifest no admite red")
        row=self._assets.get(str(reserve["image_id"]))
        if row is None:return None
        logical=Path(str(row["logical_path"]))
        if logical.is_absolute() or ".." in logical.parts:raise VisualQualityError("ruta de asset insegura")
        path=(self._root/logical).resolve()
        if self._root not in path.parents or not path.is_file() or path.is_symlink():raise VisualQualityError("asset fuera de raíz o ausente")
        raw=path.read_bytes()
        if len(raw)>maximum_bytes:return None
        digest=hashlib.sha256(raw).hexdigest()
        if digest!=row.get("sha256") or len(raw)!=row.get("size_bytes"):raise VisualQualityError("asset cacheado sin integridad")
        return ResolvedAsset(str(reserve["image_id"]),digest,path,"cache",False,len(raw))


class MapillaryOnlineResolver:
    """Adapter online explícito; autorización y presupuesto se validan fuera y dentro del core."""

    def __init__(self, *, client, cache, authorization: Mapping[str,Any]):
        if not authorization.get("approved") or not authorization.get("terms_reviewed") or not authorization.get("quality_filtering_permitted"):
            raise VisualQualityError("adquisición/calidad Mapillary no autorizada")
        self._client=client;self._cache=cache;self._authorization=dict(authorization)

    def is_cached(self, reserve: Mapping[str,Any]) -> bool:
        return len(list(self._cache.images.glob(f"{reserve['image_id']}.*"))) == 1

    def resolve(self, reserve: Mapping[str,Any], *, mode: str, maximum_bytes: int) -> ResolvedAsset | None:
        if mode!="online":raise VisualQualityError("resolver Mapillary requiere modo online")
        image_id=str(reserve["image_id"]);matches=list(self._cache.images.glob(f"{image_id}.*"));cached=matches[0] if len(matches)==1 else None
        if len(matches)>1:raise VisualQualityError("múltiples assets cacheados para el mismo image_id")
        if cached and cached.is_file():
            metadata_path=self._cache.metadata/f"{image_id}.json"
            if not metadata_path.is_file():raise VisualQualityError("asset cacheado sin metadata")
            metadata=json.loads(metadata_path.read_text(encoding="utf-8"));raw=cached.read_bytes();digest=hashlib.sha256(raw).hexdigest()
            if len(raw)>maximum_bytes:return None
            if metadata.get("sha256")!=digest or metadata.get("size_bytes")!=len(raw) or (self._cache.root/metadata.get("logical_path","")).resolve()!=cached.resolve():raise VisualQualityError("integridad de caché Mapillary inválida")
            return ResolvedAsset(image_id,digest,cached.resolve(),"cache",False,len(raw))
        metadata=self._client.image_metadata(image_id,("id","creator","thumb_1024_url"))
        if str(metadata.get("id"))!=image_id or not metadata.get("thumb_1024_url"):return None
        raw,media=self._client.download_bytes(metadata["thumb_1024_url"],max_bytes=maximum_bytes)
        from .mapillary_visual_pilot import image_dimensions
        detected,width,height=image_dimensions(raw)
        if media and media not in {detected,"application/octet-stream"}:raise VisualQualityError("MIME Mapillary incompatible")
        suffix=".jpg" if detected=="image/jpeg" else ".png";record=self._cache.store(image_id,raw,{"status":"downloaded","media_type":detected,"downloaded_resolution":[width,height],"license":"CC-BY-SA-4.0","source_page_url":f"https://www.mapillary.com/app/?pKey={image_id}","authorization_id":self._authorization.get("authorization_id")},suffix=suffix);path=(self._cache.root/record["logical_path"]).resolve();return ResolvedAsset(image_id,record["sha256"],path,"downloaded",True,len(raw))


class ScriptedQualityVerifier:
    """Fake determinista exclusivo de fixtures; no debe usarse como resultado científico."""

    def __init__(self, decisions_by_sha256: Mapping[str,Mapping[str,Any]], model: Mapping[str,Any] | None = None):
        self._decisions={key:dict(value) for key,value in decisions_by_sha256.items()};self._metadata=dict(model or {"model_id":"fixture-quality-verifier","revision":"fixture-v1","weight_sha256":"0"*64,"dtype":"cpu","attention":"none","prompt_version":"visual-image-quality-v1","preprocessing_policy":"fixture-bytes-v1","generation":{"do_sample":False,"max_new_tokens":48,"batch_size":1}});self.calls=[]
    @property
    def metadata(self)->Mapping[str,Any]:return self._metadata
    def evaluate(self, *, image_path: Path)->Mapping[str,Any]:
        digest=hashlib.sha256(image_path.read_bytes()).hexdigest();self.calls.append(digest)
        if digest not in self._decisions:raise VisualQualityError("fixture sin decisión")
        return self._decisions[digest]
    def close(self)->None:return None


def validate_policy(policy: Mapping[str,Any]) -> None:
    if policy.get("contract_version")!="visual-quality-gate-policy-v1":raise VisualQualityError("política de calidad incompatible")
    limits=policy.get("limits",{});required=("target_accepted_images_per_candidate","maximum_images_inspected_per_candidate","maximum_images_downloaded_per_query","maximum_quality_vlm_calls","maximum_claim_vlm_calls","maximum_replacements_per_candidate","maximum_sequences_per_candidate","maximum_wall_seconds","maximum_asset_bytes","maximum_downloaded_bytes")
    if any(not isinstance(limits.get(key),int) or limits[key]<=0 for key in required):raise VisualQualityError("límites de calidad inválidos")
    if limits["target_accepted_images_per_candidate"]>limits["maximum_images_inspected_per_candidate"] or limits["maximum_replacements_per_candidate"]>=limits["maximum_images_inspected_per_candidate"]:raise VisualQualityError("presupuesto por candidato incoherente")
    selection=policy.get("selection",{});downstream=policy.get("downstream",{})
    if any(selection.get(key) is not False for key in ("rerank_feedback_allowed","ground_truth_allowed","query_text_allowed_in_quality_gate","claims_allowed_in_quality_gate")):raise VisualQualityError("calidad recibe señal científica prohibida")
    if any(downstream.get(key) is not True for key in ("claims_receive_accept_only","review_blocks_claims","reject_blocks_claims","missing_quality_blocks_claims","abstention_is_neutral","reranking_policy_unchanged")):raise VisualQualityError("política downstream no es conservadora")


def validate_reserves(reserves: Sequence[Mapping[str,Any]]) -> None:
    reject_ground_truth(reserves,path="quality_reserves")
    keys=[]
    for row in reserves:
        expected={"candidate_id","reserve_index","image_id","sequence_id"}
        if not expected<=set(row) or not isinstance(row["reserve_index"],int) or row["reserve_index"]<0:raise VisualQualityError("reserva visual inválida")
        keys.append((row["candidate_id"],row["reserve_index"]))
    if len(keys)!=len(set(keys)):raise VisualQualityError("índice de reserva duplicado")
    grouped={candidate:sorted(index for cid,index in keys if cid==candidate) for candidate in {cid for cid,_ in keys}}
    if any(indices!=list(range(len(indices))) for indices in grouped.values()):raise VisualQualityError("reservas no son prefijo contiguo")


def freeze_quality_reserves(candidates: Sequence[Mapping[str,Any]], images: Sequence[Mapping[str,Any]], *, maximum_radius_m: float = 100.0, reserve_depth: int = 8) -> dict[str,Any]:
    """Congela reservas por metadata; nunca observa píxeles, GT o outputs VLM."""
    reject_ground_truth(candidates,path="quality_candidates");reject_ground_truth(images,path="quality_images")
    if not 0 < maximum_radius_m <= 150 or not 1 <= reserve_depth <= 16:raise VisualQualityError("parámetros de reserva inválidos")
    rows=[]
    for candidate in sorted(candidates,key=lambda row:row["candidate_id"]):
        nearby=[]
        for image in images:
            distance=haversine_m(candidate["latitude"],candidate["longitude"],image["latitude"],image["longitude"])
            if distance>maximum_radius_m:continue
            bearing=bearing_degrees(image["latitude"],image["longitude"],candidate["latitude"],candidate["longitude"])
            difference=angular_difference(image["orientation_degrees"],bearing) if image.get("orientation_degrees") is not None else None
            panoramic=image.get("camera_type") in {"equirectangular","spherical","cylindrical"}
            band=0 if panoramic else 1 if difference is not None and difference<=45 else 2 if difference is not None and difference<=90 else 3
            group=image.get("sequence_id") or f"image:{image['image_id']}"
            nearby.append({"candidate_id":candidate["candidate_id"],"image_id":image["image_id"],"sequence_id":image.get("sequence_id"),"opportunity_group_id":f"mapillary:{group}","distance_m":distance,"orientation_band":band,"quality_score":image.get("quality_score"),"width_px":image.get("width_px"),"height_px":image.get("height_px"),"captured_at_epoch_ms":image.get("captured_at_epoch_ms")})
        nearby.sort(key=lambda row:(row["orientation_band"],row["distance_m"],-(row["quality_score"] if row["quality_score"] is not None else -1),-((row["width_px"] or 0)*(row["height_px"] or 0)),-(row["captured_at_epoch_ms"] or 0),row["image_id"]))
        groups={}
        for row in nearby:groups.setdefault(row["opportunity_group_id"],[]).append(row)
        group_order=sorted(groups,key=lambda key:(groups[key][0]["orientation_band"],groups[key][0]["distance_m"],key))
        ordered=[];wave=0
        while len(ordered)<reserve_depth:
            emitted=False
            for group in group_order:
                if wave<len(groups[group]):ordered.append(groups[group][wave]);emitted=True
                if len(ordered)==reserve_depth:break
            if not emitted:break
            wave+=1
        for index,row in enumerate(ordered):rows.append({**row,"reserve_index":index})
    document={"schema_version":"1.0","contract_version":"visual-quality-reserve-plan-v1","plan_id":"","protocol":{"ground_truth_used":False,"pixels_used":False,"vlm_outputs_used":False,"rerank_feedback_used":False,"sequence_diversity_first":True,"maximum_radius_m":maximum_radius_m,"reserve_depth":reserve_depth},"candidate_count":len(candidates),"reserves":rows};document["plan_id"]="visual-quality-reserve-plan-sha256-"+hashlib.sha256(canonical_bytes({key:value for key,value in document.items() if key!="plan_id"})).hexdigest();validate_reserves(rows);return document


def run_quality_replacement(*, reserves: Sequence[Mapping[str,Any]], claims_by_candidate: Mapping[str,Sequence[Mapping[str,Any]]], policy: Mapping[str,Any], resolver: AssetResolver, quality_verifier: QualityVerifier, claim_verifier: ClaimVerifier | None = None, quality_cache: Mapping[str,Mapping[str,Any]] | None = None, mode: str = "offline", clock: Callable[[],float] = time.monotonic) -> dict[str,Any]:
    validate_policy(policy);validate_reserves(reserves)
    if mode not in {"offline","online","fixture"}:raise VisualQualityError("modo de calidad inválido")
    if mode=="online" and policy.get("status")!="authorized_for_real_execution":raise VisualQualityError("modo online no autorizado")
    quality_cache=dict(quality_cache or {});model=dict(quality_verifier.metadata);limits=policy["limits"];by_candidate={};candidate_ids=sorted({row["candidate_id"] for row in reserves})
    for candidate_id in candidate_ids:by_candidate[candidate_id]=sorted((dict(row) for row in reserves if row["candidate_id"]==candidate_id),key=lambda row:(row["reserve_index"],row["image_id"]))
    state={cid:{"accepted":[],"sequences":set(),"attempted":[],"next":0,"replacements":0,"terminal":None} for cid in candidate_ids};attempts=[];started=clock();quality_calls=downloads=downloaded_bytes=claim_calls=cache_hits=0;stop_reason="targets_or_reserves_exhausted"
    while True:
        progress=False
        for candidate_id in candidate_ids:
            row=state[candidate_id]
            if row["terminal"] or len(row["accepted"])>=limits["target_accepted_images_per_candidate"]:continue
            if clock()-started>=limits["maximum_wall_seconds"]:stop_reason="wall_time_exhausted";break
            reserves_for_candidate=by_candidate[candidate_id]
            if row["next"]>=len(reserves_for_candidate) or len(row["attempted"])>=limits["maximum_images_inspected_per_candidate"]:
                row["terminal"]="partial" if row["accepted"] else "abstain_reserves_exhausted";continue
            reserve=reserves_for_candidate[row["next"]];row["next"]+=1
            if reserve["reserve_index"]>0:
                if row["replacements"]>=limits["maximum_replacements_per_candidate"]:
                    row["terminal"]="partial" if row["accepted"] else "abstain_replacement_budget_exhausted";continue
                row["replacements"]+=1
            if reserve.get("sequence_id") not in row["sequences"] and len(row["sequences"])>=limits["maximum_sequences_per_candidate"]:
                row["attempted"].append(reserve["image_id"]);attempts.append({"candidate_id":candidate_id,"reserve_index":reserve["reserve_index"],"image_id":reserve["image_id"],"sequence_id":reserve.get("sequence_id"),"asset_status":"not_resolved","quality_status":"policy_sequence_limit","quality_decision":"REVIEW","reason_codes":["AMBIGUOUS_QUALITY"],"claim_calls":0,"replacement_triggered":True});progress=True;continue
            cached_hint=bool(getattr(resolver,"is_cached",lambda _:False)(reserve))
            if mode=="online" and not cached_hint and downloads>=limits["maximum_images_downloaded_per_query"]:
                row["terminal"]="partial" if row["accepted"] else "abstain_download_budget_exhausted";stop_reason="download_budget_exhausted";continue
            remaining_bytes=limits["maximum_downloaded_bytes"]-downloaded_bytes
            if mode=="online" and not cached_hint and remaining_bytes<=0:
                row["terminal"]="partial" if row["accepted"] else "abstain_download_budget_exhausted";stop_reason="download_budget_exhausted";continue
            try:asset=resolver.resolve(reserve,mode=mode,maximum_bytes=min(limits["maximum_asset_bytes"],remaining_bytes) if mode=="online" and not cached_hint else limits["maximum_asset_bytes"])
            except VisualQualityError:raise
            except Exception:asset=None
            row["attempted"].append(reserve["image_id"])
            if asset is None:
                attempts.append({"candidate_id":candidate_id,"reserve_index":reserve["reserve_index"],"image_id":reserve["image_id"],"sequence_id":reserve.get("sequence_id"),"asset_status":"offline_cache_miss" if mode=="offline" else "acquisition_failed","quality_status":"not_run","quality_decision":"REVIEW","reason_codes":["AMBIGUOUS_QUALITY"],"claim_calls":0,"replacement_triggered":True});progress=True;continue
            if asset.downloaded:
                if downloads>=limits["maximum_images_downloaded_per_query"] or downloaded_bytes+asset.size_bytes>limits["maximum_downloaded_bytes"]:
                    row["terminal"]="partial" if row["accepted"] else "abstain_download_budget_exhausted";stop_reason="download_budget_exhausted";continue
                downloads+=1;downloaded_bytes+=asset.size_bytes
            task_id=quality_task_id(image_sha256=asset.image_sha256,model=model);cached=quality_cache.get(task_id)
            if cached is not None:
                try:quality=parse_quality_decision(json.dumps({"decision":cached["decision"],"reason_codes":cached["reason_codes"]},separators=(",",":")));quality_status="valid";source="cache";cache_hits+=1
                except Exception:cached=None
            if cached is None and quality_calls>=limits["maximum_quality_vlm_calls"]:
                quality={"decision":"REVIEW","reason_codes":["AMBIGUOUS_QUALITY"]};quality_status="quality_budget_exhausted";source="policy"
            elif cached is None:
                quality_calls+=1;before=clock()
                try:
                    raw=quality_verifier.evaluate(image_path=asset.path);quality=parse_quality_decision(raw if isinstance(raw,str) else json.dumps(raw,separators=(",",":")));quality_status="valid";source="executed"
                except Exception:
                    quality={"decision":"REVIEW","reason_codes":["AMBIGUOUS_QUALITY"]};quality_status="invalid_or_failed";source="executed"
                quality["inference_seconds"]=max(0.0,clock()-before)
            accepted=quality["decision"]=="ACCEPT" and quality_status=="valid";claim_records=[]
            if accepted:
                row["accepted"].append(asset);row["sequences"].add(reserve.get("sequence_id") or f"image:{reserve['image_id']}")
                claims=list(claims_by_candidate.get(candidate_id,()))
                if claim_verifier is not None and claims:
                    if claim_calls+len(claims)>limits["maximum_claim_vlm_calls"]:
                        row["terminal"]="partial_claim_budget_exhausted";stop_reason="claim_budget_exhausted"
                    else:
                        claim_records=list(claim_verifier.verify(candidate_id=candidate_id,asset=asset,claims=claims));claim_calls+=len(claims)
            attempts.append({"candidate_id":candidate_id,"reserve_index":reserve["reserve_index"],"image_id":reserve["image_id"],"image_sha256":asset.image_sha256,"sequence_id":reserve.get("sequence_id"),"asset_status":asset.source,"quality_task_id":task_id,"quality_status":quality_status,"quality_decision":quality["decision"],"reason_codes":quality["reason_codes"],"quality_source":source,"claim_calls":len(claim_records),"claim_records":claim_records,"replacement_triggered":not accepted});progress=True
        else:
            if not progress:break
            continue
        break
    candidates=[]
    for candidate_id in candidate_ids:
        row=state[candidate_id]
        if row["terminal"] is None:row["terminal"]="complete" if len(row["accepted"])>=limits["target_accepted_images_per_candidate"] else "partial" if row["accepted"] else "abstain_no_accepted_image"
        candidates.append({"candidate_id":candidate_id,"status":row["terminal"],"accepted_image_ids":[asset.image_id for asset in row["accepted"]],"accepted_image_sha256":[asset.image_sha256 for asset in row["accepted"]],"accepted_sequences":sorted(row["sequences"]),"attempted_image_ids":row["attempted"],"replacements":row["replacements"],"target_accepted_images":limits["target_accepted_images_per_candidate"],"unused_reserves":len(by_candidate[candidate_id])-row["next"],"abstention_is_neutral":True})
    summary={"candidates":len(candidates),"complete":sum(row["status"]=="complete" for row in candidates),"partial":sum(row["status"].startswith("partial") for row in candidates),"abstaining":sum(row["status"].startswith("abstain") for row in candidates),"images_inspected":len(attempts),"quality_accept":sum(row["quality_decision"]=="ACCEPT" for row in attempts),"quality_review":sum(row["quality_decision"]=="REVIEW" for row in attempts),"quality_reject":sum(row["quality_decision"]=="REJECT" for row in attempts),"successful_replacements":sum(row["reserve_index"]>0 and row["quality_decision"]=="ACCEPT" for row in attempts),"quality_cache_hits":cache_hits,"quality_vlm_calls":quality_calls,"claim_vlm_calls":claim_calls,"network_downloads":downloads,"downloaded_bytes":downloaded_bytes,"final_visual_coverage":sum(bool(row["accepted_image_ids"]) for row in candidates)}
    document={"schema_version":"1.0","contract_version":"visual-quality-replacement-result-v1","run_id":"","mode":mode,"policy":dict(policy),"protocol":{"ground_truth_used":False,"rerank_feedback_used":False,"query_text_used_for_quality":False,"claims_used_for_quality":False,"quality_is_not_relevance":True,"review_and_reject_neutral_for_candidate":True,"i01_i20_used":False},"candidates":candidates,"attempts":attempts,"summary":summary,"resources":{"wall_seconds":max(0.0,clock()-started),"stop_reason":stop_reason}};document["run_id"]=refresh_run_id(document);return document


def accepted_associations(result: Mapping[str,Any], associations: Sequence[Mapping[str,Any]]) -> list[dict[str,Any]]:
    """Proyecta ACCEPT hacia claims; REVIEW/REJECT/ausencia nunca pasan."""
    accepted={(row["candidate_id"],image_id,image_sha) for row in result.get("candidates",[]) for image_id,image_sha in zip(row.get("accepted_image_ids",[]),row.get("accepted_image_sha256",[]),strict=True)}
    attempts={(row["candidate_id"],str(row["image_id"]),row.get("image_sha256")):row for row in result.get("attempts",[]) if row.get("quality_decision")=="ACCEPT" and row.get("quality_status")=="valid"}
    output=[]
    for row in associations:
        key=(row["candidate_id"],str(row["image_id"]),row.get("image_sha256"))
        if key in accepted:
            attempt=attempts.get(key)
            if attempt is None:raise VisualQualityError("asociación ACCEPT sin intento físico")
            output.append({**dict(row),"quality_run_id":result["run_id"],"quality_task_id":attempt["quality_task_id"],"quality_decision":"ACCEPT"})
    return sorted(output,key=lambda row:(row["candidate_id"],row.get("reserve_index",999999),str(row["image_id"])))
