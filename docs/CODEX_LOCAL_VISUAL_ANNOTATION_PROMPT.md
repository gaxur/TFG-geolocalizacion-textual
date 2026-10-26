# Prompt para Codex local: propuestas de anotación visual

Trabaja exclusivamente dentro de este paquete. Tu función es **proponer**
anotaciones visuales para revisión humana; no eres la referencia final.

## Entradas

- `fixture.json`: queries, claims, asociaciones y los 72 registros esperados.
- `photo-manifest.json`: rutas portables, hashes, orientación y atribución.
- `images/`: las 12 fotografías.
- `schemas/visual_atomic_ai_proposals.schema.json`: contrato de salida.

No busques archivos fuera del paquete, no uses Internet y no intentes localizar
geográficamente las imágenes. No hay referencias de evaluación, scores o rankings
y no debes inferirlos.

## Tarea

Para cada registro esperado `(query_id, candidate_id, image_id, claim_id)`:

1. Abre la fotografía indicada.
2. Localiza el claim exacto en `claim_sets`.
3. Propón uno de estos veredictos:
   - `supported`: hay evidencia visual específica y suficiente a favor;
   - `contradicted`: hay evidencia visible inequívocamente incompatible;
   - `unverifiable`: la vista no permite decidir.
4. Escribe la evidencia que realmente observas, no una reformulación del claim.
5. Justifica brevemente la decisión.
6. Registra limitaciones de visibilidad y cualquier ambigüedad.

## Reglas obligatorias

- La mera ausencia de un objeto no es contradicción.
- Fuera de campo, vista parcial, oclusión, lejanía, baja resolución o duda son
  `unverifiable`.
- No inventes establecimientos, nombres, materiales, texto o relaciones.
- Un rótulo/nombre solo puede ser `supported` si es literalmente legible.
- No conviertas izquierda/derecha/enfrente de la cámara en relaciones del
  observador salvo que el paquete establezca orientación comparable; si no,
  marca `unverifiable` y `orientation_issue=true`.
- Una escena genérica parecida no basta para confirmar un lugar concreto.
- Si existen varias interpretaciones razonables, usa `unverifiable` y describe la
  ambigüedad.
- Conserva literalmente todos los identificadores.
- No añadas ni omitas registros; deben ser exactamente 72 y únicos.

## Salida

Escribe `ai-proposals.json` conforme al schema. Usa:

```json
{
  "schema_version": "1.0",
  "contract_version": "visual-atomic-ai-proposals-v1",
  "fixture_id": "<source_fixture_id>",
  "provenance": {
    "annotation_kind": "AI-proposed",
    "agent": "Codex local <versión si está disponible>",
    "generated_at_utc": "<ISO-8601>",
    "human_validated": false
  },
  "records": []
}
```

Cada record debe contener exactamente:

```text
query_id, candidate_id, image_id, claim_id,
proposed_verdict, observed_evidence, justification,
limitations, orientation_issue, ambiguity, proposal_status
```

`proposal_status` siempre será `AI-proposed`. No uses expresiones como
“anotación humana”, “validado” o “ground truth”.

Al finalizar:

1. comprueba que hay 72 registros;
2. comprueba unicidad del cuádruple de IDs;
3. valida el JSON con el schema;
4. no modifiques imágenes, fixture, manifest o checksums.
