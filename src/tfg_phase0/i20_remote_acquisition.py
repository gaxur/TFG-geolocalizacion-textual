"""Selección metadata-only y auditoría remota I01-I20 sin señales de ranking."""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .crs import wgs84_to_epsg25830
from .i20_preparation import EXPECTED_IDS, canonical_bytes


class I20RemoteError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dhash(path: Path) -> str:
    try:
        from PIL import Image
    except ImportError as error:
        raise I20RemoteError("Pillow es obligatorio para calcular dHash") from error
    with Image.open(path) as image:
        image.load()
        pixels = list(image.convert("L").resize((9, 8)).getdata())
    value = 0
    for row in range(8):
        for column in range(8):
            value = (value << 1) | (pixels[row * 9 + column] > pixels[row * 9 + column + 1])
    return f"{value:016x}"


def hamming(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def block_id(latitude: float, longitude: float) -> str:
    x, y = wgs84_to_epsg25830(latitude, longitude)
    return f"B150-{math.floor(x / 150)}-{math.floor(y / 150)}"


def projected_distance(left: Mapping[str, Any], right: Mapping[str, Any]) -> float:
    lx,ly=wgs84_to_epsg25830(float(left["latitude"]),float(left["longitude"]));rx,ry=wgs84_to_epsg25830(float(right["latitude"]),float(right["longitude"]));return math.hypot(lx-rx,ly-ry)


def quality_key(row: Mapping[str, Any]) -> tuple:
    quality = row.get("quality_score")
    pixels = (row.get("width_px") or 0) * (row.get("height_px") or 0)
    captured = row.get("captured_at_epoch_ms") or 0
    return (-(quality if quality is not None else -1), -pixels, -captured, str(row["image_id"]))


def safe_prior_index(*, h01_h02: Mapping[str, Any], h03_h10: Mapping[str, Any], h11_h25: Mapping[str, Any], h26_h37_selection: Mapping[str, Any], h26_h37_assets: Mapping[str, Any]) -> dict[str, Any]:
    references=[]
    for document in (h01_h02,h03_h10):
        for row in document["observations"]:
            position=row["panorama_coordinate"];references.append({"query_id":row["observation_id"],"latitude":position["latitude"],"longitude":position["longitude"],"source_id":row["panorama"]["panorama_id"]})
    for row in h11_h25["observations"]:
        references.append({"query_id":row["query_id"],"latitude":row["latitude"],"longitude":row["longitude"],"source_id":row["panorama_id"]})
    used_ids=set(h26_h37_selection["asset_ids"]);used_sequences=set()
    for row in h26_h37_selection["references"]:
        ref=row["reference"];references.append({"query_id":row["query_id"],"latitude":ref["latitude"],"longitude":ref["longitude"],"source_id":ref["image_id"]});used_sequences.add(ref["sequence_id"]);used_sequences.update(item["sequence_id"] for item in row["verification_plan"])
    hashes={row["sha256"] for row in h26_h37_assets["assets"]};perceptual={row["perceptual_hash"] for row in h26_h37_assets["assets"]};used_ids.update(row["image_id"] for row in h26_h37_assets["assets"])
    return {"references":references,"used_provider_ids":sorted(used_ids),"used_sequences":sorted(used_sequences),"exact_hashes":sorted(hashes),"perceptual_hashes":sorted(perceptual)}


def select_shortlist(inventory: Mapping[str, Any], prior: Mapping[str, Any], *, target: int = 20, reserves: int = 2, exclusion_radius_m: float = 75.0) -> dict[str, Any]:
    if target!=20 or reserves!=2:raise I20RemoteError("v1 exige 20 slots y dos reservas")
    prior_ids=set(prior["used_provider_ids"]);prior_sequences=set(prior["used_sequences"]);refs=prior["references"]
    eligible=[];exclusions=defaultdict(int)
    for row in inventory["images"]:
        reason=None
        if row["image_id"] in prior_ids:reason="used_provider_id"
        elif not row.get("sequence_id"):reason="missing_sequence"
        elif row["sequence_id"] in prior_sequences:reason="used_sequence"
        elif not row.get("width_px") or not row.get("height_px"):reason="missing_dimensions"
        else:
            distance=min(projected_distance(row,ref) for ref in refs)
            if distance < exclusion_radius_m:reason="within_prior_reference_exclusion_radius"
        if reason:exclusions[reason]+=1;continue
        eligible.append({**row,"block_id":block_id(row["latitude"],row["longitude"])})
    by_block=defaultdict(list)
    for row in eligible:by_block[row["block_id"]].append(row)
    for rows in by_block.values():rows.sort(key=quality_key)
    block_order=sorted(by_block,key=lambda key:(quality_key(by_block[key][0]),key))
    slots=[];used_sequences=set();used_ids=set();selected_primary=[]
    def choose(block, *, second=False):
        rows=by_block[block];available=[r for r in rows if r["image_id"] not in used_ids]
        if not available:return None
        unused=[r for r in available if r["sequence_id"] not in used_sequences]
        pool=unused or available
        if selected_primary:
            compliant=[r for r in pool if all(projected_distance(r,other)>=75 for other in selected_primary)]
            if compliant:pool=compliant
            else:pool=sorted(pool,key=lambda r:(-min(projected_distance(r,o) for o in selected_primary),quality_key(r)))
        primary=pool[0];slot_rows=[primary];local_used={primary["image_id"]}
        reserve_pool=[r for r in rows if r["image_id"] not in used_ids and r["image_id"] not in local_used]
        reserve_pool.sort(key=lambda r:((r["sequence_id"]==primary["sequence_id"]),quality_key(r)))
        for row in reserve_pool:
            if len(slot_rows)>=3:break
            slot_rows.append(row);local_used.add(row["image_id"])
        if len(slot_rows)<3:return None
        for row in slot_rows:used_ids.add(row["image_id"])
        used_sequences.add(primary["sequence_id"]);selected_primary.append(primary)
        return slot_rows
    for block in block_order:
        if len(slots)>=target:break
        rows=choose(block)
        if rows:slots.append((block,rows))
    if len({block for block,_ in slots})<10:raise I20RemoteError("menos de diez bloques elegibles")
    for block in block_order:
        if len(slots)>=target:break
        if sum(item[0]==block for item in slots)>=2:continue
        rows=choose(block,second=True)
        if rows:slots.append((block,rows))
    if len(slots)<target:raise I20RemoteError(f"solo {len(slots)} slots cumplen el freeze")
    records=[]
    for observation_id,(block,rows) in zip(EXPECTED_IDS,slots,strict=True):
        records.append({"observation_id":observation_id,"block_id":block,"ordered_candidates":[{"order":index,"role":("primary" if index==0 else f"reserve_{index}"),**row} for index,row in enumerate(rows)]})
    doc={"schema_version":"1.0","contract_version":"i20-mapillary-metadata-shortlist-v1","selection_id":"","status":"frozen_before_download","provider":"mapillary","inputs":{"inventory_id":inventory["inventory_id"],"inventory_sha256":hashlib.sha256(canonical_bytes(inventory)).hexdigest()},"protocol":{"ground_truth_used":False,"rankings_used":False,"osm_used":False,"candidate_center_distance_used":False,"pixels_used":False,"quality_metadata_only":True,"block_size_m":150,"target_separation_m":75,"minimum_blocks":10,"maximum_per_block":2,"reserves_per_slot":2,"prior_reference_exclusion_radius_m":exclusion_radius_m,"radius_is_not_independence_proof":True},"preflight":{"inventory_records":len(inventory["images"]),"eligible_records":len(eligible),"eligible_blocks":len(by_block),"eligible_sequences":len({row["sequence_id"] for row in eligible}),"exclusions":dict(sorted(exclusions.items()))},"slots":records};doc["selection_id"]="i20-mapillary-selection-sha256-"+hashlib.sha256(canonical_bytes({k:v for k,v in doc.items() if k!="selection_id"})).hexdigest();return doc


def validate_shortlist(document: Mapping[str, Any]) -> None:
    if document.get("status")!="frozen_before_download" or document.get("protocol",{}).get("ground_truth_used") is not False or document.get("protocol",{}).get("rankings_used") is not False:raise I20RemoteError("shortlist no congelado sin señales prohibidas")
    slots=document.get("slots",[])
    if [row["observation_id"] for row in slots]!=list(EXPECTED_IDS):raise I20RemoteError("slots I01-I20 incompletos")
    if len({row["block_id"] for row in slots})<10 or any(sum(item["block_id"]==row["block_id"] for item in slots)>2 for row in slots):raise I20RemoteError("distribución de bloques inválida")
    ids=[]
    for row in slots:
        candidates=row["ordered_candidates"]
        if len(candidates)!=3 or [item["order"] for item in candidates]!=[0,1,2]:raise I20RemoteError("reservas incompletas")
        ids.extend(item["image_id"] for item in candidates)
    if len(ids)!=60 or len(set(ids))!=60:raise I20RemoteError("shortlist debe contener 60 IDs únicos")


def validate_observation_states(document: Mapping[str, Any]) -> dict[str, int]:
    allowed={"DISCOVERED","ACQUIRED","QUALITY_CHECKED","PENDING_BLIND_EXCLUSION","PENDING_HUMAN_ANNOTATION","PENDING_HUMAN_REVIEW","ELIGIBLE","EXCLUDED"}
    if set(document.get("allowed_states",()))!=allowed:raise I20RemoteError("vocabulario de estados incompatible")
    rows=document.get("observations",[])
    if [row.get("observation_id") for row in rows]!=list(EXPECTED_IDS):raise I20RemoteError("estados I01-I20 incompletos o desordenados")
    counts={state:0 for state in sorted(allowed)}
    for row in rows:
        state=row.get("state")
        if state not in allowed:raise I20RemoteError("estado desconocido")
        counts[state]+=1
        if row.get("eligible") is not (state=="ELIGIBLE"):raise I20RemoteError("flag eligible incoherente")
        if state=="ELIGIBLE" and (row.get("blind_exclusion")!="clear" or row.get("human_annotation")!="frozen" or row.get("human_review")!="approved" or row.get("technical_quality")!="pass"):
            raise I20RemoteError("observación elegible sin gates completos")
        if state=="PENDING_BLIND_EXCLUSION" and row.get("blind_exclusion")!="pending_custodian":raise I20RemoteError("pendiente ciego incoherente")
    return counts
