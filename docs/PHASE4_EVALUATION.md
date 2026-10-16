# F4.3: consultas y protocolo de evaluación de Madrid

## Alcance y estado

F4.3 separa la inferencia de la evaluación:

```text
texto -> CrossText2Loc -> ranking exhaustivo inmutable
referencia validada -----------------------> evaluador independiente
```

El evaluador nunca recibe la referencia antes de que el ranking esté publicado.
No llama a CrossText2Loc, no reordena candidatos y no aplica el filtro de 100
vecinos del protocolo oficial de Nueva York.

Actualmente hay tres sondas técnicas de F4.2, todas en `development`, pero
ninguna procede de una observación independiente ni tiene referencia geográfica
validada. Por ello, la evaluación empírica de Madrid continúa pendiente. Los
fixtures sintéticos validan el software, no miden el rendimiento del modelo.

## Contratos

`schemas/f4_query_dataset.schema.json` define un dataset versionado con:

- `query_id`, `location_id` y `derivation_group_id`;
- partición `development` o `evaluation`;
- texto, idioma y prohibición explícita de coordenadas en la descripción;
- procedencia diferenciada: observación humana *in situ*, observación de mapa
  OSM, sintética, asistida por modelo, sonda técnica o dataset existente;
- referencia WGS84 pendiente, validada o rechazada;
- método de captura y validación, precisión reportada y asignación F1;
- estado de ambigüedad y validación.

`schemas/f4_evaluation_result.schema.json` define el informe agregado y sus
referencias a dataset, catálogo, galería, embeddings y checkpoint. El ranking
continúa usando `schemas/f4_retrieval_result.schema.json`; el ground truth no se
añade a ese documento.

El borrador `config/madrid_f43_query_dataset_draft.json` contiene únicamente las
tres sondas técnicas ya ejecutadas. Conserva referencias `pending` y `null`; no
es un conjunto de evaluación final.

## Incorporación de consultas

### Procedencias

1. `human_in_situ`: una persona describe el entorno sin ver OSM, la galería,
   candidate IDs ni rankings. Es la procedencia requerida para el futuro test.
2. `osm_map_observed`: descripción redactada observando un mapa o PNG OSM. Es
   útil para desarrollo, pero no representa observación humana independiente.
3. `synthetic` o `model_assisted`: datos artificiales o asistidos, identificando
   modelo, instrucciones y revisión. No se mezclan silenciosamente con humanos.
4. `technical_probe`: texto creado solo para probar el pipeline, como las tres
   consultas actuales.

Para incorporar una consulta real se debe:

1. asignar un `query_id` estable y un `location_id` independiente de F1;
2. registrar texto original, idioma, instrucciones y procedencia;
3. capturar la referencia antes de observar el ranking;
4. registrar método, precisión y método de validación de la coordenada;
5. anotar ambigüedad sin forzar una única interpretación;
6. ejecutar `scripts/validate_f4_query_dataset.py`;
7. revisar manualmente duplicados y pares marcados como paráfrasis;
8. congelar la partición `evaluation` antes de evaluar.

No se elimina una consulta porque CrossText2Loc falle ni se cambia su ubicación
después de observar el ranking.

## Particiones y contaminación

La política `location-and-derivation-group-v1` impide que un `location_id` o un
`derivation_group_id` aparezca en ambas particiones. Traducciones, paráfrasis y
versiones derivadas deben compartir grupo y partición.

El validador aplica normalización Unicode NFKC, minúsculas para auditoría,
eliminación de puntuación, compactación de espacios, rechazo de duplicados
exactos y Jaccard de tokens entre particiones con umbral registrado. Los pares
sospechosos requieren revisión manual antes de congelar test. Esta detección
léxica no garantiza reconocer toda paráfrasis semántica ni mueve muestras
automáticamente.

Compartir la galería visual y sus embeddings entre particiones no es leakage:
son el catálogo congelado de búsqueda, no descripciones ni pesos ajustados con
el test.

## Asignación geográfica

La referencia WGS84 se transforma a EPSG:25830 y se compara con las celdas F1.
La política `projected_cell_interior_boundary_ambiguous_v1` produce:

- `assigned`: punto inequívocamente dentro del interior de una celda;
- `boundary_ambiguous`: punto sobre un borde o vértice dentro de tolerancia;
- `outside_catalog_coverage`: dentro de D004 pero en una franja no cubierta por
  celdas completas;
- `outside_region`: fuera de la bbox D004.

No se sustituye un hueco por la celda más próxima. Esto es necesario porque
`full_cell_within_bbox` solo conserva celdas completas y no cubre necesariamente
toda la bbox. Los casos no asignados se contabilizan en cobertura, pero no
reciben un `ground_truth_candidate_id` inventado.

La precisión reportada también participa en la asignación. Si su radio alcanza
el borde de la celda, el estado es `accuracy_insufficient` y no se calcula
Recall exacto. Toda referencia validada debe almacenar la asignación recalculada,
declarar `location_id`, método de captura y validación, precisión y revisión de
ambigüedad.

## Métricas

Para referencias `assigned`:

```text
Recall@K = consultas cuyo ground_truth_candidate_id aparece en Top-K
           / referencias evaluables
```

Se calculan `Recall@1`, `Recall@5` y `Recall@10`. Una celda vecina es un fallo de
Recall exacto aunque esté geográficamente cerca.

La distancia Top-1 utiliza Haversine con radio terrestre medio de
6.371.008,8 m. No se restan grados como si fueran metros. También se calcula la
distancia mínima a la referencia entre Top-1, Top-5 y Top-10 y GeoRecall para
umbrales propios de 25, 50, 100 y 500 m. Recall exacto y GeoRecall se presentan
por separado.

Media y mediana se calculan cuando hay errores disponibles. Los percentiles 90 y
95 solo se publican con al menos 20 observaciones; con menos muestra quedan en
`null`. Consultas evaluables sin ranking permanecen en el denominador como
fallos. Referencias pendientes, rechazadas o fuera de región se informan aparte.
Bordes e incertidumbre impiden Recall exacto, pero conservan métricas
geográficas; los huecos del catálogo son fallos exactos y también conservan
Haversine.

Los huecos de cobertura dentro de D004 cuentan como fallos en el denominador de
Recall exacto porque el catálogo no contiene una celda correcta. Bordes e
incertidumbre insuficiente se excluyen de Recall exacto porque no existe una
etiqueta discreta inequívoca, pero conservan evaluación geográfica por Haversine.
Las estadísticas de error se etiquetan como condicionadas a que exista ranking y
publican también sus conteos ausentes. Cada ranking consumido queda fijado por
ruta lógica y SHA-256 en el `evaluation_id`.

El hash identifica los bytes consumidos, pero no demuestra por sí solo que se
generaran antes de conocer el ground truth. Para la evaluación final se congelará
y registrará el manifest de rankings antes de abrir las referencias reservadas;
la separación temporal y de responsables formará parte del acta de congelación.
El borrador actual no contiene referencias y sus hashes solo acreditan la
reproducibilidad de las sondas técnicas.

## Comandos

Validar el borrador:

```bash
./.venv-geo/bin/python scripts/validate_f4_query_dataset.py \
  --dataset config/madrid_f43_query_dataset_draft.json
```

Evaluar rankings Top-10 ya generados:

```bash
./.venv-geo/bin/python scripts/freeze_f4_rankings.py \
  --dataset config/madrid_f43_query_dataset_draft.json \
  --results-dir results/generated/f4 \
  --partition development \
  --embedding-dataset-id f4-madrid-embeddings-sha256-199dae0e3eb38b206004557f20fae0ef98f620621458fc64c2dfa3f7ef7f84c1 \
  --checkpoint-sha256 d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d \
  --output results/generated/f4.3/madrid-f43-development-ranking-set.json

./.venv-geo/bin/python scripts/evaluate_f4_madrid.py \
  --dataset config/madrid_f43_query_dataset_draft.json \
  --results-dir results/generated/f4 \
  --ranking-set results/generated/f4.3/madrid-f43-development-ranking-set.json \
  --partition development \
  --catalog-manifest data/processed/catalog/manifest-50m.json \
  --visual-bundle data/processed/visual/f4-madrid-visual-sha256-15310268e0fed30180085c7ec1f14fce696c4ba94e83bf9727970451cc82f564 \
  --embedding-bundle data/embeddings/f4-madrid-embeddings-sha256-199dae0e3eb38b206004557f20fae0ef98f620621458fc64c2dfa3f7ef7f84c1 \
  --selection config/madrid_f4_visual_gallery_50m.json \
  --output-root results/generated/f4.3
```

Una evaluación formal requiere rankings con al menos Top-10. Los JSON Top-5 de
las sondas actuales se registran, pero no permitirían calcular Recall@10 aunque
tuvieran referencia.

La partición `evaluation` solo puede procesarse cuando
`partition_policy.evaluation_frozen` sea `true`. Esta marca se activa después de
cerrar las revisiones de procedencia, referencia, duplicados y paráfrasis, y no
se revierte para ajustar el sistema.

## Pendientes

- Recoger y autorizar descripciones humanas *in situ* con referencias y
  precisión documentadas.
- Aprobar el tamaño final y split por localizaciones de D029.
- Congelar la política exacta de captura y revisión de referencias de D030.
- Mantener D007, D013 y D016 abiertas.
- Ejecutar una evaluación final solo después de congelar dataset, galería,
  checkpoint, código y protocolo.
