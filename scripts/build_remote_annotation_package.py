#!/usr/bin/env python3
"""Construye una interfaz estática portable; no adquiere ni copia fotografías."""

from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
import os
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.tfg_phase0.remote_mapillary_campaign import EXPECTED_DEVELOPMENT_IDS, EXPECTED_TEST_IDS


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render_html(fixture: dict, *, blind: bool) -> str:
    payload = json.dumps(fixture, ensure_ascii=False).replace("</", "<\\/")
    cards = []
    for row in fixture["observations"]:
        reference = row["reference"]
        image = (
            f'<img src="{escape(reference["logical_path"])}" alt="Referencia {escape(reference["image_id"])}">'
            if reference.get("logical_path")
            else '<div class="pending">Fotografía no disponible: adquisición no autorizada o pendiente.</div>'
        )
        cards.append(
            f'''<article data-query="{escape(row['query_id'])}">
<header><h2>{escape(row['query_id'])} <small>{escape(row['partition'])}</small></h2><span>{escape(row['spatial_block_id'])}</span></header>
<div class="columns"><section>{image}<p><b>image_id:</b> <code>{escape(reference['image_id'])}</code><br><b>sequence_id:</b> <code>{escape(reference['sequence_id'])}</code><br><b>captura:</b> {escape(str(reference.get('captured_at') or 'desconocida'))}<br><b>heading proveedor:</b> {escape(str(reference.get('orientation_degrees') if reference.get('orientation_degrees') is not None else 'desconocido'))}; fiabilidad desconocida</p></section>
<section><div class="map" data-lat="{reference['latitude']}" data-lon="{reference['longitude']}"></div><p>Coordenada reportada por Mapillary: {reference['latitude']:.7f}, {reference['longitude']:.7f}. No es GT centimétrico.</p><a href="https://www.openstreetmap.org/?mlat={reference['latitude']}&mlon={reference['longitude']}#map=19/{reference['latitude']}/{reference['longitude']}" target="_blank" rel="noreferrer">Abrir OSM</a></section></div>
<fieldset><legend>Anotación humana</legend><label>Descripción española<textarea class="description" minlength="40"></textarea></label><label>Claims, uno por línea<textarea class="claims" placeholder="object|fachada de ladrillo"></textarea></label><label>Orientación<select class="orientation"><option value="unknown">Desconocida</option><option value="provider_camera_heading">Heading de cámara, fiabilidad desconocida</option></select></label><label>Incertidumbres<textarea class="uncertainties"></textarea></label><label>Decisión<select class="decision"><option value="pending">Pendiente</option><option value="approved">Aprobar</option><option value="rejected">Rechazar</option></select></label><label><input type="checkbox" class="reviewed"> Confirmo revisión humana sin rankings ni salidas 2B/8B</label></fieldset>
</article>'''
        )
    ai_label = "No se muestran propuestas IA en este paquete ciego." if blind else "Las propuestas IA, si se importan, son auxiliares y nunca etiquetas humanas."
    script = r'''
<script id="fixture" type="application/json">PAYLOAD</script><script>
const fixture=JSON.parse(document.getElementById('fixture').textContent),D004={n:40.420,s:40.412,e:-3.699,w:-3.709};
document.querySelectorAll('.map').forEach(m=>{const lat=+m.dataset.lat,lon=+m.dataset.lon,x=(lon-D004.w)/(D004.e-D004.w)*100,y=(D004.n-lat)/(D004.n-D004.s)*100;m.innerHTML=`<svg viewBox="0 0 100 100" role="img" aria-label="Posición aproximada en D004"><rect width="100" height="100"/><path d="M0 25H100M0 50H100M0 75H100M25 0V100M50 0V100M75 0V100"/><circle cx="${x}" cy="${y}" r="3"/><text x="3" y="8">D004</text></svg>`});
function output(){const reviewer=document.getElementById('reviewer').value.trim();if(!reviewer)throw Error('Indica el revisor');const observations=fixture.observations.map(base=>{const a=document.querySelector(`[data-query="${base.query_id}"]`),description=a.querySelector('.description').value.trim(),decision=a.querySelector('.decision').value,reviewed=a.querySelector('.reviewed').checked,orientation=a.querySelector('.orientation').value;if(decision==='approved'&&(!reviewed||description.length<40))throw Error(`${base.query_id}: aprobación incompleta`);const claims=a.querySelector('.claims').value.split('\n').map(x=>x.trim()).filter(Boolean).map((x,i)=>{const p=x.split('|');return {claim_id:`claim-${i+1}`,text_es:(p[1]||p[0]).trim(),kind:(p[1]?p[0]:'scene').trim(),source:'reference_images_only',ai_proposed:false,human_reviewed:reviewed,reviewer:reviewed?reviewer:null,review_status:reviewed?'accepted':'pending'}});return {...base.canonical_stub,lifecycle_status:decision==='approved'?'approved':decision,description:{text_es:description||null,creation_method:description?'human_from_reference':'pending',ai_proposal:{used:false,model:null,model_revision:null,prompt_sha256:null,proposal_sha256:null},human_reviewed:reviewed,author_pseudonym:reviewed?reviewer:null,reviewed_at_utc:reviewed?new Date().toISOString():null},orientation:orientation==='unknown'?{status:'unknown',heading_degrees:null,uncertainty_degrees:null,meaning:'unknown',reliability:'unknown'}:{status:'provider_camera_heading',heading_degrees:base.reference.orientation_degrees,uncertainty_degrees:null,meaning:'camera_heading_not_body_heading',reliability:'unknown'},claims,uncertainties:a.querySelector('.uncertainties').value.split('\n').map(x=>x.trim()).filter(Boolean),human_review:{status:decision,primary_reviewer:reviewed?reviewer:null,secondary_reviewer:null,reviewed_at_utc:reviewed?new Date().toISOString():null,rankings_seen:false,vlm_outputs_seen:false,ai_proposals_visible:false}}});return {schema_version:'2.0',contract_version:'remote-mapillary-campaign-v2',campaign_id:fixture.campaign_id,selection_id:fixture.selection_id,observations}}
document.getElementById('export').onclick=()=>{try{const blob=new Blob([JSON.stringify(output(),null,2)+'\n'],{type:'application/json'}),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='remote-campaign-annotations.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);status.textContent='Exportado';}catch(error){status.textContent=error.message}};
</script>'''.replace("PAYLOAD", payload)
    return f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Anotación remota H26-H61</title><style>
:root{{--ink:#17211c;--paper:#f3efe4;--green:#174f3b;--gold:#bc8b32}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px Georgia,serif}}main{{max-width:1300px;margin:auto;padding:1.5rem}}.bar{{position:sticky;top:0;z-index:3;background:var(--green);color:white;padding:1rem;display:flex;gap:1rem;align-items:center;flex-wrap:wrap}}article{{background:#fffdf7;margin:1.5rem 0;padding:1.2rem;border-left:6px solid var(--gold);box-shadow:0 5px 20px #27352c18}}header,.columns{{display:flex;justify-content:space-between;gap:1rem}}.columns>section{{flex:1}}img{{width:100%;max-height:430px;object-fit:contain;background:#111}}.pending{{min-height:230px;display:grid;place-items:center;background:#ded8c9;padding:2rem}}.map svg{{width:100%;max-height:330px;background:#dce5d9}}.map rect{{fill:#dce5d9;stroke:#174f3b}}.map path{{stroke:#a6b2a7;stroke-width:.4}}.map circle{{fill:#b23a2e;stroke:white;stroke-width:1}}textarea,select,input{{font:inherit}}textarea,select{{width:100%;margin:.3rem 0 1rem;padding:.6rem}}textarea{{min-height:6rem}}fieldset{{border:1px solid #8a927e;margin-top:1rem}}small{{font-weight:normal}}code{{overflow-wrap:anywhere}}@media(max-width:750px){{.columns{{display:block}}}}
</style><div class="bar"><b>Campaña remota H26-H61</b><label>Revisor <input id="reviewer"></label><button id="export">Exportar JSON canónico</button><span id="status"></span></div><main><p>{escape(ai_label)} La referencia es la cámara Mapillary con precisión desconocida; las imágenes de verificación no se muestran aquí.</p>{''.join(cards)}</main>{script}</html>'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--photo-manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("human", "codex", "blind-test"), default="human")
    parser.add_argument("--partition", choices=("development", "test_sealed"), required=True)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    photos = {}
    if args.photo_manifest:
        manifest = json.loads(args.photo_manifest.read_text(encoding="utf-8"))
        photo_rows = manifest.get("photos", manifest.get("assets", []))
        photos = {row["image_id"]: row for row in photo_rows if row.get("status") == "downloaded"}
    expected_ids = EXPECTED_DEVELOPMENT_IDS if args.partition == "development" else EXPECTED_TEST_IDS
    selected_rows = [row for row in selection["references"] if row.get("partition") == args.partition]
    if tuple(row.get("query_id") for row in selected_rows) != expected_ids:
        raise ValueError(f"partición {args.partition} incompleta o desordenada")
    observations = []
    for row in selected_rows:
        reference = row["reference"]
        photo = photos.get(reference["image_id"], {})
        if photo:
            source_path = (args.photo_manifest.parent / photo["logical_path"]).resolve()
            photo = {**photo, "logical_path": os.path.relpath(source_path, args.output.resolve())}
        source = {"provider": "Mapillary", "inventory_id": selection["inputs"]["inventory_id"], "inventory_sha256": selection["inputs"]["inventory_sha256"], "license": "CC-BY-SA-4.0", "source_page_url": photo.get("source_page_url"), "creator": (photo.get("creator") or {}).get("username"), "attribution": photo.get("attribution"), "conditions_review_status": "authorized_for_campaign" if photo else "pending_new_authorization"}
        download = {"status": "downloaded", "logical_path": photo["logical_path"], "sha256": photo["sha256"], "perceptual_hash": photo.get("perceptual_hash")} if photo and photo.get("perceptual_hash") else {"status": "not_authorized", "logical_path": None, "sha256": None, "perceptual_hash": None}
        verification_assets = [{"image_id": asset["image_id"], "sequence_id": asset["sequence_id"], "distance_to_reference_m": asset["distance_to_reference_m"], "source": source, "download": {"status": "not_authorized", "logical_path": None, "sha256": None, "perceptual_hash": None}, "role": "vlm_verification_only", "independence_status": "metadata_distinct_pending_pixel_checks"} for asset in row["verification_plan"]]
        stub = {"query_id": row["query_id"], "partition": row["partition"], "location_id": f"MAPILLARY-{reference['image_id']}", "spatial_block_id": row["spatial_block_id"], "reference_asset": {"image_id": reference["image_id"], "sequence_id": reference["sequence_id"], "captured_at": None, "camera_type": reference["camera_type"], "position": {"reported_latitude": reference["latitude"], "reported_longitude": reference["longitude"], "crs": "EPSG:4326", "coordinate_source": reference["coordinate_source"], "reported_accuracy_m": None, "accuracy_status": "unknown", "observer_position_estimate": "reference_camera_coordinate", "evaluation_policy": "approximate_reference_with_sensitivity_analysis"}, "provider_heading_degrees": reference["orientation_degrees"], "heading_reliability": "unknown", "source": source, "download": download, "role": "reference_only_not_vlm_input"}, "verification_assets": verification_assets, "freeze": {"selected_at_utc": "2026-10-27T00:00:00Z", "frozen_at_utc": None, "canonical_sha256": None, "rankings_executed_at_utc": None, "edited_after_freeze": False}, "independence": {"same_image_excluded": True, "same_reference_sequence_excluded": True, "exact_hash_checked": False, "perceptual_similarity_checked": False, "human_overlap_reviewed": False, "status": "metadata_only_pending_pixel_checks"}, "limitations": ["remote_provider_image", "not_human_in_situ", "camera_coordinate_unknown_accuracy", "heading_reliability_unknown", "not_centimetric_ground_truth", "mapillary_coverage_bias", "verification_views_pending", "independence_pending"]}
        observations.append({"query_id": row["query_id"], "partition": row["partition"], "spatial_block_id": row["spatial_block_id"], "reference": {**reference, "logical_path": photo.get("logical_path")}, "canonical_stub": stub})
    fixture = {"contract_version": "remote-annotation-fixture-v1", "campaign_id": "madrid-d004-remote-mapillary-h26-h61-v2", "selection_id": selection["selection_id"], "partition": args.partition, "query_ids": list(expected_ids), "mode": args.mode, "forbidden_content": ["other_partition_records", "ct2l_rankings", "2b_outputs", "8b_outputs", "evaluation_metrics", "candidate_distances"], "observations": observations}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "fixture.json").write_bytes(canonical_bytes(fixture) + b"\n")
    (args.output / "annotate.html").write_text(render_html(fixture, blind=args.mode == "blind-test"), encoding="utf-8")
    schema_source = Path(__file__).resolve().parents[1] / "schemas" / "remote_mapillary_observation.schema.json"
    shutil.copy2(schema_source, args.output / "remote_mapillary_observation.schema.json")
    readme = "# Paquete de anotación remota\n\nAbrir `annotate.html` o servir la carpeta con `py -m http.server 8765 --bind 127.0.0.1`. No contiene rankings, resultados VLM ni credenciales. Verificar manualmente el JSON exportado antes de congelarlo.\n"
    (args.output / "README.md").write_text(readme, encoding="utf-8")
    if args.mode == "codex":
        prompt = """# Instrucciones para Codex local\n\nAnaliza solo `fixture.json` y las imágenes de referencia disponibles. Propón, sin aceptar automáticamente: descripción española, objetos visibles, atributos, relaciones, texto literal, ambigüedades y problemas de orientación. No uses web, rankings, resultados 2B/8B ni imágenes de verificación. Marca toda salida como `AI-proposed` y `human_validated: false`. No inventes precisión, orientación, objetos ocultos ni coordenadas. La persona revisora debe aceptar o corregir cada campo en `annotate.html`.\n"""
        (args.output / "CODEX_PROMPT.md").write_text(prompt, encoding="utf-8")
    checksums = []
    for path in sorted(args.output.iterdir()):
        if path.is_file() and path.name != "CHECKSUMS.sha256":
            checksums.append(f"{file_sha256(path)}  {path.name}")
    (args.output / "CHECKSUMS.sha256").write_text("\n".join(checksums) + "\n", encoding="ascii")
    print(json.dumps({"output": str(args.output), "mode": args.mode, "observations": len(observations)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
