#!/usr/bin/env python3
from __future__ import annotations

import argparse
from html import escape
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
from src.tfg_phase0.visual_reranking import canonical_bytes  # noqa: E402


def main() -> int:
    p=argparse.ArgumentParser(description="Renderiza anotación humana atómica local")
    p.add_argument("--fixture",type=Path,required=True); p.add_argument("--photo-manifest",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    p.add_argument("--annotations",type=Path)
    a=p.parse_args(); fixture=json.loads(a.fixture.read_text()); photos_doc=json.loads(a.photo_manifest.read_text())
    annotations=json.loads(a.annotations.read_text()) if a.annotations else fixture["annotation_template"]; claims={row["claim_id"]:row for group in fixture["claim_sets"] for row in group["claims"]}; photos={row["image_id"]:row for row in photos_doc["photos"] if row["status"]=="downloaded"}
    groups={}
    for record in annotations["records"]: groups.setdefault((record["query_id"],record["candidate_id"],record["image_id"]),[]).append(record)
    articles=[]
    for (query_id,candidate_id,image_id),records in groups.items():
        photo=photos.get(image_id)
        if photo is None: raise ValueError(f"imagen ausente: {image_id}")
        source=(a.photo_manifest.parent/photo["logical_path"]).resolve().relative_to(a.output.parent.resolve()) if False else None
        image_path=Path(photo["logical_path"])
        if not image_path.is_absolute(): image_path=(a.photo_manifest.parent/image_path).resolve()
        import os
        image_source=Path(os.path.relpath(image_path,a.output.parent.resolve())).as_posix()
        cards=[]
        for record in records:
            claim=claims[record["claim_id"]]; value=escape(json.dumps(claim["value"],ensure_ascii=False)); cid=escape(record["claim_id"],quote=True)
            options=''.join(f'<option value="{verdict}"{" selected" if record.get("human_verdict")==verdict else ""}>{verdict}</option>' for verdict in ('supported','contradicted','unverifiable'))
            cards.append(f'<section class="claim" data-claim-id="{cid}"><p><strong>{escape(claim["kind"])}</strong>: {value}<br><small>Texto literal: {escape(claim["evidence"]["text"])}</small></p><label>Veredicto<select class="verdict"><option value="">pendiente</option>{options}</select></label><label>Explicación/evidencia breve<textarea class="evidence" maxlength="240">{escape(record.get("observed_evidence") or "")}</textarea></label><label>Motivo o limitación<textarea class="reason" maxlength="240">{escape(record.get("reason") or "")}</textarea></label><label><input class="reviewed" type="checkbox"{" checked" if record.get("review_status")=="reviewed" else ""}> Revisada</label></section>')
        articles.append(f'<article data-query-id="{escape(query_id,quote=True)}" data-candidate-id="{escape(candidate_id,quote=True)}" data-image-id="{escape(image_id,quote=True)}"><h2>{escape(query_id)} · {escape(image_id)}</h2><p><code>{escape(candidate_id)}</code></p><img src="{image_source}" alt="Mapillary {escape(image_id)}"><div class="claims">{"".join(cards)}</div></article>')
    data=json.dumps(annotations,ensure_ascii=False).replace('</','<\\/')
    schema=json.dumps(json.loads((ROOT/'schemas/visual_atomic_human_annotations.schema.json').read_text()),ensure_ascii=False).replace('</','<\\/')
    script=r'''<script id="data" type="application/json">DATA</script><script id="schema" type="application/json">SCHEMA</script><script>
const doc=JSON.parse(document.getElementById('data').textContent), schema=JSON.parse(document.getElementById('schema').textContent); const key=(c,i,q)=>q+'\0'+c+'\0'+i; const by=new Map(doc.records.map(r=>[key(r.candidate_id,r.image_id,r.claim_id),r]));
function collect(){const reviewer=document.getElementById('reviewer').value.trim(); document.querySelectorAll('article').forEach(a=>a.querySelectorAll('.claim').forEach(c=>{const r=by.get(key(a.dataset.candidateId,a.dataset.imageId,c.dataset.claimId)); const checked=c.querySelector('.reviewed').checked, verdict=c.querySelector('.verdict').value, evidence=c.querySelector('.evidence').value.trim(); if(checked&&(!reviewer||!verdict))throw Error('Cada fila revisada necesita revisor y veredicto.'); if(checked&&(verdict==='supported'||verdict==='contradicted')&&!evidence)throw Error('supported y contradicted necesitan evidencia observable breve.'); r.human_verdict=verdict||null;r.observed_evidence=evidence||null;r.reason=c.querySelector('.reason').value.trim()||null;r.review_status=checked?'reviewed':'pending';r.reviewer=checked?reviewer:null;r.reviewed_at_utc=checked?new Date().toISOString():null;})); return doc;}
function buildExport(){const d=collect(); if(d.records.some(r=>r.review_status!=='reviewed'))throw Error('Quedan anotaciones pendientes.'); return JSON.stringify(d,null,2)+'\n';}
document.getElementById('export').onclick=()=>{try{const blob=new Blob([buildExport()],{type:'application/json'}),u=URL.createObjectURL(blob),l=document.createElement('a');l.href=u;l.download='atomic-annotations.json';l.click();setTimeout(()=>URL.revokeObjectURL(u),1000);document.getElementById('status').textContent='JSON completo exportado.';}catch(e){document.getElementById('status').textContent=e.message;}};
window.annotationFormTest=()=>({records:doc.records.length,articles:document.querySelectorAll('article').length,claims:document.querySelectorAll('.claim').length,selects:document.querySelectorAll('select.verdict').length,checkboxes:document.querySelectorAll('input.reviewed').length,images:[...document.images].map(i=>({complete:i.complete,width:i.naturalWidth,src:i.getAttribute('src')})),collectType:typeof collect,exportType:typeof buildExport}); document.documentElement.dataset.ready='true'; document.getElementById('status').textContent='Formulario cargado: '+doc.records.length+' anotaciones.';
if(new URLSearchParams(location.search).get('autotest')==='1'){window.addEventListener('load',()=>{document.querySelectorAll('select.verdict').forEach(x=>x.value='unverifiable');document.querySelectorAll('input.reviewed').forEach(x=>x.checked=true);document.querySelectorAll('textarea.reason').forEach(x=>x.value='autotest');let result;try{const exported=JSON.parse(buildExport()),images=[...document.images];result={ok:true,records:exported.records.length,reviewed:exported.records.filter(x=>x.review_status==='reviewed').length,selects:document.querySelectorAll('select.verdict').length,checkboxes:document.querySelectorAll('input.reviewed').length,images:images.length,imagesLoaded:images.filter(x=>x.complete&&x.naturalWidth>0).length};}catch(e){result={ok:false,error:e.message};}document.getElementById('status').textContent='AUTOTEST '+JSON.stringify(result);fetch('/__form_autotest__?form=atomic&result='+encodeURIComponent(JSON.stringify(result))).catch(()=>{});},{once:true});}
</script>'''.replace('DATA',data).replace('SCHEMA',schema)
    html='<!doctype html><html lang="es" data-ready="false"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Anotación atómica</title><style>body{font:15px system-ui;max-width:1500px;margin:auto;padding:1.5rem;background:#f4f1e8;color:#17221b}.toolbar{position:sticky;top:0;background:#183b2d;color:#fff;padding:1rem;z-index:3}article{border-top:3px solid #1f6f54;padding:1rem 0}img{width:min(640px,100%);max-height:450px;object-fit:contain;background:#111}.claims{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:.7rem}.claim{background:#fff;border:1px solid #aaa;padding:.8rem}label{display:block;margin:.5rem 0;font-weight:600}select,textarea,input{font:inherit}select,textarea{width:100%;box-sizing:border-box}textarea{min-height:4rem}code{overflow-wrap:anywhere}</style></head><body><h1>Anotación humana por evidencia</h1><p>La ausencia en una vista parcial es <code>unverifiable</code>, no contradicción. Usa <code>contradicted</code> solo ante incompatibilidad visible.</p><div class="toolbar">Revisor <input id="reviewer" value="marcos"> <button id="export" type="button">Exportar JSON completo</button> <span id="status">Inicializando formulario…</span></div>'+''.join(articles)+script+'</body></html>'
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(html,encoding='utf-8'); print(json.dumps({'pairs':len(annotations['records']),'output':str(a.output)},sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
