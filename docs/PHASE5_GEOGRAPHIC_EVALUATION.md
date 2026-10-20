# F5.4: Ground Truth de Madrid y evaluación geográfica

## Estado y resultado de la auditoría

F5.4 prepara una evaluación geográfica reproducible de las cinco variantes
textuales sobre las galerías completas de 25 m y 50 m. No implementa prefiltrado,
reranking OSM, GOTPR, Street View ni VLM.

La auditoría local no encontró observaciones madrileñas aptas para calcular
precisión:

| Recurso | Observaciones | GT validado | Uso permitido |
|---|---:|---:|---|
| Borrador F4.3 | 3 sondas inglesas | 0 | Pruebas técnicas |
| Fixtures F5.2/F5.3b | Sondas sintéticas/development | 0 | Pruebas de software y estabilidad |
| Observaciones `human_in_situ` | 0 | 0 | Ninguna disponible |

Por tanto no se publican Recall@K, GeoRecall ni errores geográficos de Madrid. La
plantilla materializada informa `geographic_evaluation_ready: false`. No se
inventaron textos, coordenadas ni evidencias para alcanzar 20-30 observaciones.

## Contrato de recopilación

F4.3 continúa siendo la fuente de texto, procedencia, partición y referencia. El
sidecar `f5-ground-truth-dataset-v1` añade evidencia revisada, orientación y
asignación independiente a ambos catálogos. La plantilla está en
[`config/madrid_f54_ground_truth_template.json`](../config/madrid_f54_ground_truth_template.json)
y el schema en
[`schemas/f5_ground_truth_dataset.schema.json`](../schemas/f5_ground_truth_dataset.schema.json).

Una observación validada debe cumplir:

- procedencia `human_in_situ` o `existing_dataset` y observación independiente;
- descripción original española sin coordenadas;
- posición WGS84 del observador, no de un objeto mencionado;
- método de captura, precisión reportada y validación independiente;
- al menos una evidencia con referencia lógica, SHA-256 y revisión humana;
- `location_id` y `derivation_group_id` estables;
- asignaciones recalculadas para 25 m y 50 m;
- orientación respaldada por evidencia cuando se declara;
- descripción y ambigüedad revisadas.

Los ficheros de evidencia pueden permanecer fuera de Git. `logical_reference` y
SHA-256 permiten verificar los bytes usados sin publicar fotografías, registros
GNSS ni datos sensibles.

### Formulario de observación

El siguiente bloque contiene marcadores y **no es una observación real**:

```json
{
  "source_query_id": "<query-id-f43>",
  "location_id": "<location-id>",
  "derivation_group_id": "<grupo-común-a-derivados>",
  "partition": "development",
  "description_profile": "complete_observation",
  "comparison_parent_query_id": null,
  "observer_reference": {
    "status": "pending",
    "latitude": null,
    "longitude": null,
    "crs": null,
    "capture_method": null,
    "reported_accuracy_m": null,
    "validation_method": null,
    "evidence": [],
    "review_notes": null
  },
  "orientation": {
    "status": "absent",
    "cardinal": null,
    "bearing_degrees": null,
    "uncertainty_degrees": null,
    "verification_method": null,
    "evidence_ids": [],
    "egocentric_relations_present": false,
    "notes": null
  },
  "catalog_assignments": {"madrid-25m": null, "madrid-50m": null},
  "description_review_status": "pending",
  "limitations": []
}
```

Las referencias pendientes no pueden contener coordenadas parciales, evidencia o
asignaciones. Tras verificar F4.3, las asignaciones se calculan con
`assign_reference()`; no se escriben a mano.

## Posición, celda y candidato

F5.4 distingue cuatro conceptos:

1. **Posición GT:** latitud/longitud real del observador.
2. **Celda GT:** celda F1 cuyo interior contiene el punto con precisión suficiente.
3. **Centro de celda:** coordenada representativa del candidato; puede diferir del observador.
4. **Candidato recuperado:** celda ordenada por CrossText2Loc.

La asignación transforma WGS84 a EPSG:25830. Un punto interior produce
`assigned`; bordes, precisión que alcanza un borde, huecos y puntos exteriores
producen estados distintos. No se sustituye un hueco por la celda más próxima.
25 m y 50 m se calculan por separado y normalmente tienen IDs distintos.

Cobertura del piloto auditada:

| Galería | Candidatos | Celda | Manifest SHA-256 |
|---|---:|---:|---|
| `madrid-25m` | 1.115 | 25 m | `a23d3f3b54958661db76914dff9ff40a3f01a133ee86499fb9e4ddf706a49f11` |
| `madrid-50m` | 253 | 50 m | `ad35d5cb3b602a9ce313e06e10f913f169430d62a948c0f5e77b396bc810f2aa` |

Ambas cubren la bbox D004 `40.412..40.420`, `-3.709..-3.699` mediante celdas
completas. Las franjas residuales de la bbox pueden quedar fuera de cobertura.

## Orientación y descripciones

Izquierda, derecha, delante y detrás permanecen egocéntricas. Solo se almacena
cardinal o rumbo cuando está reportado/verificado y enlazado a evidencia. Una
orientación `verified` exige método y precisión angular.

El protocolo solicita descripciones completas con varios objetos y relaciones
cuando sean observables. Los atributos visuales solo se anotan si existe
evidencia. Una simplificación controlada se registra como otra consulta F4.3 con
`description_profile: controlled_simplification`, el mismo grupo/partición y
`comparison_parent_query_id`; nunca se genera automáticamente ni se eliminan
pistas sin revisión.

## Cinco variantes y prevención de fuga

La evaluación requiere sidecar v2 y exactamente:

```text
es_original, es_cartographic, en_conventional,
en_toponym_preserved, en_cartographic
```

Todas deben estar `reviewed`. El runner verifica que GT y variantes referencien el
mismo dataset F4.3 y que el ranking corresponda por ID y SHA-256 al sidecar
revisado. CrossText2Loc recibe solo texto, idioma, galería y K. La posición,
asignación y evidencia no entran en prompts, retrieval o selección de candidatos.

Para evaluación final, la partición y las variantes se congelan antes de abrir el
GT reservado. El reporte exige ranking exhaustivo Top-10, sin scores o coordenadas
fusionados.

## Métricas

Por variante y galería:

- Recall@1, Recall@5 y Recall@10 de la celda GT;
- error Haversine Top-1 respecto al observador;
- error mínimo Top-1/5/10 respecto al observador;
- GeoRecall@K con umbrales positivos configurables;
- media y mediana;
- p90 y p95 únicamente con al menos 20 valores;
- latencia de retrieval;
- observaciones válidas/excluidas y motivos.

Un ranking ausente es fallo en Recall y GeoRecall, pero no inventa una distancia:
los resúmenes de error indican cuántos rankings fueron observados. Los bordes o
precisión insuficiente conservan métricas geográficas, pero no Recall exacto.
Los huecos del catálogo son fallos exactos.

`variant_comparisons` compara cada variante con `es_original` por consulta y
registra mejora, empeoramiento o empate en error Top-1. No confunde estas
comparaciones con Jaccard o acuerdo de rankings. Cada fila conserva además
`description_profile` y `comparison_parent_query_id` para analizar completas
frente a simplificaciones únicamente cuando haya pares revisados suficientes.

## Comandos

Materializar la plantilla actual:

```bash
.venv-geo/bin/python scripts/prepare_f54_ground_truth_template.py \
  --output results/generated/f5/f54/ground-truth-template.json
```

Validar tras incorporar observaciones reales en F4.3 y F5.4:

```bash
.venv-geo/bin/python scripts/validate_f54_ground_truth.py \
  --dataset <ground-truth-f54.json> \
  --source-query-dataset <query-dataset-f43.json>
```

Evaluar después de generar y revisar variantes y rankings:

```bash
.venv-geo/bin/python scripts/evaluate_f54_variants.py \
  --ground-truth <ground-truth-f54.json> \
  --source-query-dataset <query-dataset-f43.json> \
  --variants <sidecar-v2-revisado.json> \
  --ranking-report <report-f52-top10.json> \
  --distance-threshold-m 25 \
  --distance-threshold-m 50 \
  --distance-threshold-m 100 \
  --distance-threshold-m 500 \
  --output-root results/generated/f5/f54
```

No se ejecutó este último comando con datos reales porque el denominador actual
es cero.

## Preparación de comparaciones OSM futuras

El reporte conserva el baseline A y campos nulos para B/C:

| Configuración | Estado |
|---|---|
| A. CrossText2Loc exhaustivo | Implementado por F5.4 |
| B. Qwen → prefiltrado OSM → CrossText2Loc | No implementado; stand-by |
| C. CrossText2Loc → Top-N → reranking OSM | No implementado; stand-by |

Una fase posterior medirá cobertura GT tras prefiltrado, tasa de eliminación de
la celda correcta, Recall/error tras reranking, latencia Qwen/OSM y comparación
pareada con A. La ausencia de una etiqueta OSM no se tratará automáticamente como
contradicción.

## Limitaciones y siguiente paso

La infraestructura está lista, pero no existe evaluación empírica F5.4. El
siguiente paso es recoger 20-30 observaciones reales dentro de D004, con
consentimiento y política de datos, coordenada del observador capturada antes de
ver rankings, evidencia revisada y localizaciones distribuidas. Hasta entonces,
cualquier porcentaje de precisión de Madrid permanece no disponible.
