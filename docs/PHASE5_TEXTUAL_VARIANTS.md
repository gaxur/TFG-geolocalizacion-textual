# F5.1: observaciones madrileñas y variantes textuales

## Alcance y estado

F5.1 prepara contratos, validación y protocolo para recoger observaciones con
ground truth y comparar cuatro representaciones textuales:

- `es_original`;
- `es_cartographic`;
- `en_conventional`;
- `en_toponym_preserved`.

No genera traducciones, no ejecuta inferencia y no modifica el MVP. Tampoco
implementa LLM, extracción automática, preselección OSM, filtrado, reranking,
fusión de scores, fusión de coordenadas ni fine-tuning.

La preselección OSM permanece expresamente en
`standby_pending_tutor_decision` hasta hablarlo con el tutor.

## Arquitectura compatible con F4.3

F4.3 continúa siendo la única fuente de observaciones, particiones, procedencia y
ground truth. Su contrato `f4-query-dataset-v1` es content-addressed y no se
modifica. F5.1 añade un sidecar que lo referencia por `dataset_id`, SHA-256 y
`query_id`:

```text
F4.3 query dataset
  ├── descripción original
  ├── procedencia
  ├── location_id y derivation_group_id
  ├── partición
  └── ground truth y asignación F1
          │
          └── ID + SHA-256 + query_id
                    ↓
F5.1 textual variants sidecar
  ├── topónimos y spans
  ├── orientación opcional
  └── cuatro variantes relacionadas
```

Archivos:

| Recurso | Ruta |
|---|---|
| Schema | `schemas/f5_textual_variant_dataset.schema.json` |
| Identidad y validación | `src/tfg_phase0/f5_textual_variants.py` |
| Plantilla vacía | `config/madrid_f51_textual_variants_template.json` |
| CLI | `scripts/validate_f5_textual_variants.py` |
| Tests | `tests/test_phase5_textual_variants.py` |

La plantilla tiene cero observaciones porque el borrador F4.3 actual solo
contiene sondas técnicas inglesas. No se fabrican observaciones españolas,
traducciones ni coordenadas para aparentar un dataset completo.

## Recogida de una observación

### Preparación

1. Fijar instrucciones y versión antes de recoger evaluación.
2. Elegir una posición dentro de la bbox sin seleccionar el punto a partir del
   ranking del modelo.
3. Asignar un `location_id` independiente de los candidate IDs.
4. No mostrar OSM, imágenes de la galería, candidatos ni resultados al
   participante de una observación `human_in_situ`.
5. Obtener consentimiento y aplicar la política de datos aprobada.

### Descripción original

Registrar en F4.3:

- `query_id` estable;
- `location_id`;
- `derivation_group_id` compartido por todos los derivados;
- texto español íntegro, sin sustituirlo por una versión limpiada;
- `language: es`;
- `source_type` y si es observación independiente;
- instrucciones y fecha de recogida;
- ambigüedad y notas.

Procedencias permitidas por F4.3:

| Procedencia | Uso |
|---|---|
| `human_in_situ` | Requerida para una evaluación humana independiente |
| `osm_map_observed` | Desarrollo al observar cartografía; no mezclar con in situ |
| `synthetic` | Fixture o dato artificial identificado |
| `model_assisted` | Texto asistido, con modelo/instrucciones documentados |
| `technical_probe` | Comprobación técnica sin pretensión empírica |
| `existing_dataset` | Importación con procedencia y permisos |

## Ground truth

El ground truth es la posición del observador o el punto definido previamente
por el protocolo, nunca el centro de un objeto mencionado. Debe capturarse antes
de inspeccionar el ranking y registrar:

- latitud y longitud WGS84;
- `crs: EPSG:4326`;
- método de captura;
- precisión estimada en metros;
- método de validación;
- estado `pending`, `validated` o `rejected`;
- asignación recalculada al catálogo mediante F4.3.

No se completa parcialmente una referencia pendiente. Una referencia validada
debe incluir precisión, método y asignación. Los estados posibles de cobertura
son `assigned`, `boundary_ambiguous`, `accuracy_insufficient`,
`outside_catalog_coverage` y `outside_region`.

La asignación se calcula por separado para 25 m y 50 m. Una celda de 25 m no
garantiza error inferior a 25 m.

## Topónimos

F5.1 anota manualmente una mención sin buscarla todavía en OSM:

```json
{
  "mention": "Plaza Mayor",
  "span": {"start": 15, "end": 27},
  "entity_type": "square",
  "name_kind": "proper_name",
  "aliases": ["Plaza Mayor de Madrid"],
  "annotation_provenance": "manual",
  "review_status": "reviewed"
}
```

`span.start` es inclusivo y `span.end` exclusivo sobre el texto original. El
validador comprueba que `text[start:end]` sea exactamente `mention` y rechaza
spans duplicados o solapados.

`proper_name` identifica nombres como `Plaza Mayor`, `Gran Vía` o `Puerta del
Sol`. `generic_expression` identifica frases como `una plaza grande` o `una
avenida`. No se detectan topónimos solo por mayúsculas. Los alias pueden conservar
formas conocidas; una futura resolución deberá considerar `name`, `name:es`,
`name:en`, `alt_name` y otras variantes, pero F5.1 no consulta OSM.

## Orientación opcional

La orientación puede estar `absent`, `reported` o `verified`. Puede declarar:

- un cardinal: norte, noreste, este, sureste, sur, suroeste, oeste o noroeste;
- o un rumbo entre 0 y menos de 360 grados, medido en sentido horario desde el
  norte verdadero;
- método y procedencia;
- incertidumbre en grados;
- estado de verificación;
- presencia de relaciones relativas en el texto.

No se permiten a la vez cardinal y rumbo. Una orientación ausente no puede
contener valores. `derecha`, `izquierda`, `delante` o `detrás` se conservan como
relaciones egocéntricas y no se convierten a cardinales sin orientación adicional
justificada.

Ejemplo verificado:

```json
{
  "status": "verified",
  "cardinal": "north",
  "bearing_degrees": null,
  "bearing_convention": null,
  "method": "compass",
  "uncertainty_degrees": 5.0,
  "provenance": "observer_measurement",
  "verification_status": "verified",
  "relative_relations_present": true,
  "notes": "La relación derecha se conserva; no se reescribe automáticamente."
}
```

## Variantes textuales

Cada observación contiene exactamente cuatro slots en este orden. Excepto
`es_original`, pueden permanecer `pending`:

| Variante | Idioma | Regla |
|---|---|---|
| `es_original` | es | Copia exacta del texto F4.3; nunca se sobrescribe |
| `es_cartographic` | es | Reescritura manual centrada en elementos potencialmente cartográficos |
| `en_conventional` | en | Traducción convencional, registrando método/herramienta |
| `en_toponym_preserved` | en | Traducción que mantiene literalmente topónimos propios revisados |

Cada variante registra ID, estado, texto, método, herramienta/modelo, versión,
configuración o prompt, revisión, tiempo de transformación y elementos
conservados, eliminados, modificados o protegidos.

En F5.1 no se ejecuta ningún traductor. Los métodos automáticos existen en el
contrato para trazabilidad futura, no como funcionalidad implementada. Una
variante `pending` debe tener texto, ID, herramienta, tiempo y anotaciones nulos o
vacíos; el validador rechaza contenido fabricado.

La variante cartográfica puede conservar calles, intersecciones, plazas,
parques, edificios, formas y relaciones espaciales. Toda eliminación se registra.
No se asume que retirar colores, carteles o fachadas mejore el ranking.

### Plantilla de una observación

El siguiente fragmento es estructural y utiliza placeholders; no debe copiarse
como dato real. Primero se añade y valida la observación española en F4.3. Luego
se calcula `source_input_sha256` con la implementación F5.1 y se incorpora al
sidecar:

```json
{
  "source_query_id": "<query_id-f43>",
  "source_input_sha256": "<sha256-del-input-f43>",
  "partition": "development",
  "location_id": "<location_id-f43>",
  "derivation_group_id": "<derivation_group_id-f43>",
  "toponyms": [],
  "orientation": {
    "status": "absent",
    "cardinal": null,
    "bearing_degrees": null,
    "bearing_convention": null,
    "method": null,
    "uncertainty_degrees": null,
    "provenance": null,
    "verification_status": "not_applicable",
    "relative_relations_present": false,
    "notes": null
  },
  "variants": [
    {
      "variant_id": "<query_id-f43>-es-original-v1",
      "kind": "es_original",
      "status": "reviewed",
      "text": "<copia exacta del texto español F4.3>",
      "language": "es",
      "generation": {
        "method": "original",
        "tool_or_model": "manual",
        "version": "v1",
        "configuration_or_prompt": "copy-from-f43",
        "transformation_time_ms": null
      },
      "review_status": "reviewed",
      "transformations": ["preserve_original"],
      "preserved_elements": [],
      "removed_elements": [],
      "modified_elements": [],
      "protected_toponyms": []
    },
    {
      "variant_id": null,
      "kind": "es_cartographic",
      "status": "pending",
      "text": null,
      "language": "es",
      "generation": {
        "method": "pending",
        "tool_or_model": null,
        "version": null,
        "configuration_or_prompt": null,
        "transformation_time_ms": null
      },
      "review_status": "pending",
      "transformations": [],
      "preserved_elements": [],
      "removed_elements": [],
      "modified_elements": [],
      "protected_toponyms": []
    },
    {
      "variant_id": null,
      "kind": "en_conventional",
      "status": "pending",
      "text": null,
      "language": "en",
      "generation": {
        "method": "pending",
        "tool_or_model": null,
        "version": null,
        "configuration_or_prompt": null,
        "transformation_time_ms": null
      },
      "review_status": "pending",
      "transformations": [],
      "preserved_elements": [],
      "removed_elements": [],
      "modified_elements": [],
      "protected_toponyms": []
    },
    {
      "variant_id": null,
      "kind": "en_toponym_preserved",
      "status": "pending",
      "text": null,
      "language": "en",
      "generation": {
        "method": "pending",
        "tool_or_model": null,
        "version": null,
        "configuration_or_prompt": null,
        "transformation_time_ms": null
      },
      "review_status": "pending",
      "transformations": [],
      "preserved_elements": [],
      "removed_elements": [],
      "modified_elements": [],
      "protected_toponyms": []
    }
  ],
  "notes": null
}
```

Después de sustituir los placeholders angulares hay que recalcular `dataset_id`.
No se editan a mano ni el hash del input ni el ID content-addressed.

## Particiones y fugas

- F5.1 no asigna particiones nuevas: debe coincidir con F4.3.
- Todas las variantes heredan `location_id`, `derivation_group_id` y partición.
- Una ubicación o grupo derivado no puede cruzar desarrollo/evaluación.
- Duplicados textuales entre observaciones de particiones distintas se rechazan.
- Traductores, prompts y reglas se seleccionan solo con desarrollo.
- La partición final se congela antes de generar rankings de evaluación.
- El ground truth no se utiliza para generar, seleccionar o reordenar rankings.

## Comparación emparejada posterior

`paired_variant_plan()` devuelve los pares de variantes revisadas de cada
observación. Solo prepara IDs; no ejecuta inferencia ni fusiona resultados.

Al ejecutar F5.2 deben permanecer constantes checkpoint, encoder, galería,
embeddings, ranking exhaustivo, desempate, K, observaciones y ground truth. Cada
variante genera un ranking independiente. Se compararán 25 m y 50 m por separado.

Métricas de precisión cuando exista ground truth:

- Recall@1/5/10;
- error Haversine Top-1;
- distancia mínima Top-K;
- GeoRecall@K a umbrales fijados;
- media, mediana y percentiles con muestra suficiente;
- mejoras, empeoramientos, empates y latencia adicional por observación.

Métricas de estabilidad:

- coincidencia Top-1;
- solapamiento y Jaccard Top-K;
- distancia entre Top-1 de variantes;
- cambio de rango de candidatos compartidos;
- margen `score_top1 - score_top2`.

La dispersión espacial queda definida como la **media de distancias Haversine de
los candidatos Top-K al medoide Top-K**, donde el medoide es el candidato que
minimiza la suma de distancias al resto. Se expresa en metros, depende de K y no
es error geográfico ni confianza.

Entre galerías no se comparan candidate IDs. El acuerdo 25 m/50 m se estudia
mediante distancias WGS84 o una correspondencia geométrica definida. No se
fusionan scores ni coordenadas. Reciprocal Rank Fusion y consenso quedan como
experimentos futuros sin autorización para modificar la predicción.

## Validación

Plantilla actual:

```bash
.venv-geo/bin/python scripts/validate_f5_textual_variants.py \
  --dataset config/madrid_f51_textual_variants_template.json \
  --source-query-dataset config/madrid_f43_query_dataset_draft.json
```

Para imprimir comparaciones disponibles:

```bash
.venv-geo/bin/python scripts/validate_f5_textual_variants.py \
  --dataset <sidecar-f51.json> \
  --source-query-dataset <dataset-f43.json> \
  --manifest <manifest-f1.json> \
  --print-paired-plan
```

El resumen informa observaciones, particiones, estados de referencia, cobertura,
topónimos propios, variantes pendientes/revisadas, completitud y disponibilidad
de métricas. La plantilla actual devuelve cero observaciones y
`precision_metrics_available: false`; no es un resultado empírico.

## Continuación en F5.2 y F5.3

F5.2 implementa la infraestructura de transformación y rankings independientes,
documentada en [PHASE5_TEXT_TRANSFORMATION.md](PHASE5_TEXT_TRANSFORMATION.md).
La inferencia real Qwen y los rankings derivados siguen pendientes de disponer
de pesos autorizados y observaciones revisadas. No debe elegirse traductor o
prompt con la evaluación final.

F5.3 podrá estudiar extracción automática de topónimos, categorías, objetos,
relaciones, atributos, negaciones y orientación explícita. Debe preservar texto
original y revisión. No está implementada en F5.1.

La preselección, filtrado o reranking OSM sigue en stand-by hasta decisión del
tutor. F3 puede utilizarse posteriormente para análisis de objetos alrededor de
candidatos, pero F5.1 no lo ejecuta ni modifica el ranking CrossText2Loc.
