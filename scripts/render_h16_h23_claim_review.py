#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from html import escape
import json
from pathlib import Path


EXPORT_FILENAME_V1 = "h16-h23-top50-claims-review.json"
EXPORT_FILENAME_V2 = "h16-h23-top50-claims-review-v2.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    review = json.loads(args.review.read_text(encoding="utf-8"))
    export_filename = EXPORT_FILENAME_V2 if fixture.get("contract_version") == "h16-h23-multicandidate-fixture-v2" else EXPORT_FILENAME_V1
    records = {row["claim"]["claim_id"]: row for row in review["records"]}
    rows = []
    claims = []
    for query in fixture["queries"]:
        corrected = fixture.get("contract_version") == "h16-h23-multicandidate-fixture-v2"
        warning = ('<aside><b>Variante corregida y versionada:</b> “retablo oscuro” se representa como “dark altarpiece”. Revisa el claim nuevo; no hereda una aprobación anterior.</aside>' if corrected else '<aside><b>Revisión semántica obligatoria:</b> “retablo oscuro” no equivale automáticamente a “dark choir”. No apruebes esa equivalencia sin una decisión consciente.</aside>') if query["query_id"] == "H16" else ""
        rows.append(f"<h2>{escape(query['query_id'])}</h2><p>{escape(query['text'])}</p>{warning}")
        for claim in query["claims"]["claims"]:
            claims.append({"query_id": query["query_id"], "claim": claim})
            current = records[claim["claim_id"]]
            selected = current["decision"]
            rows.append(f'''<section data-id="{escape(claim['claim_id'])}"><code>{escape(claim['kind'])}</code> <b>{escape(claim['evidence']['text'])}</b><small>{escape(claim['claim_id'])}</small><pre>{escape(json.dumps(claim['value'], ensure_ascii=False))}</pre><label>Decisión <select><option value="pending"{' selected' if selected == 'pending' else ''}>Pendiente</option><option value="approved"{' selected' if selected == 'approved' else ''}>Aprobar</option><option value="rejected"{' selected' if selected == 'rejected' else ''}>Rechazar</option></select></label><label>Motivo <input value="{escape(current.get('reason') or '')}"></label></section>''')
    payload = {"claims": claims, "contract_version": review["contract_version"], "protocol_id": protocol["protocol_id"], "protocol_sha256": digest(args.protocol), "fixture_id": fixture["fixture_id"], "fixture_sha256": digest(args.fixture), "variant": review["variant"], "semantic_warnings": review["semantic_warnings"]}
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    script = r'''<script id="payload" type="application/json">DATA</script><script>
const payload=JSON.parse(document.getElementById('payload').textContent),by=new Map(payload.claims.map(x=>[x.claim.claim_id,x]));
function collect(){const reviewer=document.getElementById('reviewer').value.trim(),now=new Date().toISOString(),records=[];document.querySelectorAll('section').forEach(s=>{const decision=s.querySelector('select').value,x=by.get(s.dataset.id),decided=decision!=='pending';if(decided&&!reviewer)throw Error('Las decisiones necesitan revisor');records.push({query_id:x.query_id,claim:x.claim,decision,reason:s.querySelector('input').value.trim()||null,reviewer:decided?reviewer:null,reviewed_at_utc:decided?now:null})});const pending=records.filter(x=>x.decision==='pending').length;return {schema_version:'1.0',contract_version:payload.contract_version,protocol_id:payload.protocol_id,protocol_sha256:payload.protocol_sha256,fixture_id:payload.fixture_id,fixture_sha256:payload.fixture_sha256,variant:payload.variant,gallery_id:'madrid-50m',candidate_depth:50,review_status:pending?'pending':'complete',provenance:{kind:'human_review',imported_at_utc:null,source_export_sha256:null,previous_canonical_sha256:null},semantic_warnings:payload.semantic_warnings,records}}
function download(){try{const doc=collect(),u=URL.createObjectURL(new Blob([JSON.stringify(doc,null,2)+'\n'],{type:'application/json'})),a=document.createElement('a');a.href=u;a.download='EXPORT';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);status.textContent=doc.review_status==='complete'?'Exportación completa lista para importar':'Borrador exportado; el importador lo rechazará hasta completar todos los claims';}catch(e){status.textContent=e.message}}
function load(doc){if(doc.fixture_id!==payload.fixture_id||doc.protocol_id!==payload.protocol_id)throw Error('JSON de otro fixture/protocolo');const rows=new Map(doc.records.map(x=>[x.claim.claim_id,x]));if(rows.size!==payload.claims.length)throw Error('JSON incompleto');document.querySelectorAll('section').forEach(s=>{const row=rows.get(s.dataset.id);if(!row||JSON.stringify(row.claim)!==JSON.stringify(by.get(s.dataset.id).claim))throw Error('Claim manipulado o incompatible');s.querySelector('select').value=row.decision;s.querySelector('input').value=row.reason||'';if(row.reviewer)document.getElementById('reviewer').value=row.reviewer});status.textContent='Revisión cargada';}
document.getElementById('export').onclick=download;document.getElementById('load').onchange=async e=>{try{load(JSON.parse(await e.target.files[0].text()))}catch(error){status.textContent=error.message}};
</script>'''.replace("DATA", data).replace("EXPORT", export_filename)
    html = f'''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Claims H16/H23 Top-50</title><style>body{{font:16px system-ui;max-width:1100px;margin:auto;padding:1rem;background:#f4f1e8;color:#17211c}}.bar{{position:sticky;top:0;background:#183b2d;color:white;padding:1rem;z-index:2;display:flex;gap:1rem;flex-wrap:wrap}}section{{background:white;border-left:5px solid #bc8b32;margin:1rem 0;padding:1rem}}label,small{{display:block;margin-top:.7rem}}input[type=text],section input{{width:min(90%,50rem)}}pre{{white-space:pre-wrap}}aside{{background:#ffe8b2;border:2px solid #a86500;padding:1rem}}button,input,select{{font:inherit}}</style><div class="bar"><label>Revisor <input id="reviewer" type="text" value="marcos"></label><button id="export">Exportar {export_filename}</button><label>Cargar borrador <input id="load" type="file" accept="application/json"></label><span id="status"></span></div><h1>Claims exactos {escape(review['variant'])}, Top-50</h1><p>Revisa literalidad y utilidad como claim. Aprobar un claim no es afirmar que aparezca en todas las fotografías. Las relaciones egocéntricas quedarán no verificables sin orientación comparable.</p>{''.join(rows)}{script}</html>'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(json.dumps({"fixture_id": fixture["fixture_id"], "claims": len(claims), "export_filename": export_filename, "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
