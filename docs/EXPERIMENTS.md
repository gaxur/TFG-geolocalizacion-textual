# Registro de experimentos

Conservar por separado el protocolo oficial de Nueva York, cuya galería de 100
vecinos se obtiene usando las coordenadas reales de cada consulta, y cualquier
evaluación sobre una galería que no utilice el ground truth para seleccionar
candidatos. Sus métricas no son directamente comparables si cambia la galería.

## Plantilla

Cada ejecución futura debe registrar objetivo, fecha, commits, hardware,
entorno, dataset, checkpoint y hash, configuración, comando, resultados,
métricas, tiempo, memoria, problemas y cambios realizados. Solo se sustituirán
valores pendientes por observaciones reales.

## F4.1b-B: galería visual OSM de Madrid

### Objetivo y resultado

Generar una galería pequeña de imágenes cartográficas reales para nueve
candidatos F1 de 50 m, sin cargar CrossText2Loc, calcular embeddings ni ejecutar
retrieval. La ejecución terminó el 15 de octubre de 2026 con nueve PNG válidos
y un bundle content-addressed:

```text
f4-madrid-visual-sha256-40ed367c74e29ab271308f1f2df0349b1fc423d8e64ba7dc19da60d7d40be915
```

### Entorno y entradas

- Equipo: Lenovo ThinkStation PGX, Linux ARM64.
- Imagen efectiva: `sha256:70e20b64458b562342c9c9534151e7a6bf7dceffba23326bbda87cbc42f4d5b7`.
- Mapnik 3.1.0; osm2pgsql 1.11.0; PostgreSQL 16.15; PostGIS 3.4.2.
- CartoCSS 1.2.0; Pillow 10.2.0.
- OpenStreetMap Carto v5.9.0, commit
  `491bd4a4675a94f3950ff45843d0c4696d8ae420`.
- Fuente: Geofabrik `madrid-261014.osm.pbf`, 85.306.514 bytes.
- Fuente SHA-256:
  `9ef85f5c728a26995712a835a68f0cb30e01a32af6d2a7facd6744f3a3840db8`.
- Datos OSM: ODbL 1.0; estilo OSM Carto: CC0 1.0.

El estilo aplica el parche versionado de fallback emoji porque las faces
monocromas históricas `Noto Emoji Regular/Bold` ya no estaban disponibles en el
endpoint upstream. La sustitución por Noto Symbols está registrada y mantiene
el perfil como `experimental_unconfirmed`.

### Parámetros y comandos

- EPSG:3857, norte arriba, zoom 18.
- Crop nativo 256 x 256 centrado con precisión subpíxel.
- Footprint: 152,87405657035252 m proyectados por lado.
- Resize bicúbico a PNG RGB 512 x 512.

```bash
bash scripts/acquire_f4_render_inputs.sh
docker build --platform linux/arm64 \
  -f docker/f4-osm-carto-arm64/Dockerfile \
  -t tfg-f4-osm-carto-arm64:ubuntu24.04 .
bash scripts/run_f4_osm_render.sh
./.venv-geo/bin/python scripts/validate_f4_visual_bundle.py \
  --bundle data/processed/visual/f4-madrid-visual-sha256-40ed367c74e29ab271308f1f2df0349b1fc423d8e64ba7dc19da60d7d40be915
```

### Validación y límites

- 9/9 candidatos con estado `generated`.
- Todos los ficheros son PNG RGB 512 x 512, completamente decodificables y no
  uniformes.
- SHA-256 central (`R0008_C0008`):
  `3043d9982aa62a80cc9aae99006b61d8693843f88eb26fd7a03c884196034667`.
- Una segunda ejecución completa produjo el mismo ID y el publicador comprobó
  igualdad byte a byte del árbol.
- No se usó GPU, checkpoint, descripción textual ni ground truth.
- No se obtuvieron métricas de recuperación.
- D007 continúa abierta: la escala, el estilo y la generación exactos del
  entrenamiento original no están confirmados.
- La base Ubuntu está fijada por digest, pero APT resuelve paquetes al construir;
  una reconstrucción con otro ID deberá validarse como otro entorno.

## F4.1c: embeddings y retrieval exhaustivo de nueve candidatos

### Objetivo y entorno

Comprobar el recorrido completo texto-imagen con el checkpoint congelado, sin
entrenamiento, fine-tuning, preselección geográfica ni ground truth. Se utilizó
la NVIDIA GB10 mediante la imagen ARM64:

```text
sha256:4306f8b8596461c3e08ca3b809e370e4de0dbc978715c95b4421ab37ab70a2c4
```

Checkpoint y pesos base:

```text
checkpoint sha256: d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d
OpenAI CLIP sha256: 3035c92b350959924f9f00213499208652fc7ea050643e8b385c2dac08641f02
```

Entorno observado: Python 3.12.3, PyTorch
`2.11.0a0+eb65b36914.nv26.02`, torchvision
`0.25.0a0+1e53952f.nv26.02.44259020`, CUDA 13.1 e inferencia FP32.

### Artefacto offline

```text
f4-madrid-embeddings-sha256-9d721b9893e004b39a238c1b1e40ece8f865964e4555c82d2732ba9b066709eb
```

- Matriz: `(9, 768)`, `float32`, C-contiguous, little-endian.
- Valores finitos; normas de fila entre `0,99999994` y `1,0`.
- SHA-256 NPY:
  `19284f67dac2e3efa6e4e4ca212592ccce6db5e4a1d8bb5a3a5634c0fe54a223`.
- SHA-256 JSONL de filas:
  `6cdc68c6d5d33574d267fac1d805bc5650b56d954b503b46fd3185aa47bd7b44`.
- SHA-256 del `utils.py` de CVG-Text realmente importado:
  `18dad4696c205dba5f934f9382ff5bd7d380c502680e462612bbdc49229ba597`.

### Consultas de desarrollo observadas

| Query | Top-1 | Score coseno |
|---|---|---:|
| `madrid-dev-es-001`: «Una plaza urbana rodeada de edificios y calles estrechas» | `...R0008_C0004` | 0,24788210 |
| `madrid-dev-en-001`: “A dense city block with narrow streets and many buildings” | `...R0008_C0004` | 0,18201816 |
| `madrid-dev-es-002`: «Veo una avenida amplia cerca de una zona verde» | `...R0004_C0008` | 0,23069473 |

Los JSON completos permanecen bajo `results/generated/f4/`, fuera de Git. La
consulta `madrid-dev-es-001` se repitió con los embeddings persistidos y produjo
el mismo ranking, scores y coordenadas; solo cambió la telemetría temporal.

Estos resultados demuestran ejecución y reutilización del índice exacto, no
acierto geográfico ni generalización. No existe ground truth para estas frases y
los scores no son probabilidades. D007, D013 y D016 permanecen abiertas.

## CrossText2Loc NewYork-mixed OSM en GB10

### Objetivo y resultado

Reproducir la evaluación oficial de CrossText2Loc con el checkpoint
NewYork-mixed OSM y los datos originales, exclusivamente en inferencia. La
secuencia D0-D5 terminó el 5 de octubre de 2026 con estado **REPRODUCIDO**.

| Etapa | Estado | Comprobación |
|---|---|---|
| D0 | PASS | Runtime NVIDIA, driver y GB10 visibles dentro del contenedor. |
| D1 | PASS | PyTorch NGC 26.02 ejecutó CUDA en GB10 `sm_121`. |
| D2 | PASS | Modelo, checkpoint y 1200 muestras validados en CPU. |
| D3 | PASS | Modelo FP32 completo transferido una vez a `cuda:0`. |
| D4 intento 1 | FAIL operacional | Git rechazó el mount por `dubious ownership`; no se construyó el modelo ni se ejecutó CUDA. |
| D4 retry | PASS | Una pareja real produjo embeddings finitos y normalizados. |
| D5 | PASS | Evaluación oficial completa, 1200/1200 muestras y exit code 0. |

El primer intento D4 se conserva localmente como evidencia de un fallo de
infraestructura, no de CUDA, modelo, checkpoint o preprocessing. El retry usó
una excepción `safe.directory` limitada al proceso Git del contenedor.

### Entorno de referencia v1

- Equipo: Lenovo ThinkStation PGX.
- GPU: NVIDIA GB10, compute capability 12.1.
- Imagen: `crosstext2loc-gb10:ngc26.02`.
- ID: `sha256:9df10d06a947b32d3c4f95601e9f1125073cbc067d76ee9da6f762d7eb254fc2`.
- Base: `nvcr.io/nvidia/pytorch@sha256:8014e4ffc674ae9cc9aecad04b64b29c3d311ed738e54ac3042d2d45690d19e9`.
- Python: 3.12.3.
- PyTorch: `2.11.0a0+eb65b36914.nv26.02`.
- torchvision: `0.25.0a0+1e53952f.nv26.02.44259020`.
- CUDA de PyTorch: 13.1; `CUDA_VERSION=13.1.1.006`.
- CVG-Text: `6910d2747a94fbe985309bde60cd4732bcbbf50f`.
- OpenAI CLIP: `dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1`.
- Modelo: CLIP ViT-L/14@336, FP32, contexto 300.
- Checkpoint: `long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth`.
- SHA-256: `d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d`.
- Parámetros: 428.115.457; `missing_keys=[]`; `unexpected_keys=[]`.

Esta combinación queda congelada como **REFERENCE ENVIRONMENT v1**. Un cambio
posterior de NGC, CUDA, PyTorch, torchvision o dependencias debe crear una nueva
versión del entorno y no sobrescribir silenciosamente esta referencia.

### Dataset y comando

- `annotation/NewYork/test.json`: 1000 muestras.
- `annotation/NewYork-photos/test.json`: 200 muestras.
- Total: 1200; imágenes ausentes: 0.
- No se utilizó `query.zip`.
- `batch_size=4`, `num_workers=4`, `shuffle=False`.

```bash
python zeroshot.py \
  --version NewYork-mixed \
  --img_type osm \
  --model CLIP-L/14@336 \
  --expand \
  --checkpoint long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
```

### Resultados D5

Duración total observada: 49,538392479 segundos. Código de salida: 0.

| Subconjunto | Muestras | R@1 | R@5 | R@10 | L@50 | L@100 | L@150 | Desviación media |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global | 1200 | 59,08 % | 82,75 % | 90,00 % | 62,00 % | 66,75 % | 69,67 % | 0,18 km |
| Panorama | 1000 | 59,30 % | 82,90 % | 90,10 % | 62,40 % | 67,80 % | 70,90 % | 0,17 km |
| Single-view | 200 | 58,00 % | 82,00 % | 89,50 % | 60,00 % | 61,50 % | 63,50 % | 0,23 km |

El R@1 global observado coincide con el 59,08 documentado para este checkpoint
en New York OSM. Los demás valores se registran como resultados observados de
esta ejecución y no se extrapolan a Madrid.

### Protocolo y limitación

`evaluate.py` extrae la coordenada ground truth de cada consulta, calcula las
distancias a la galería, selecciona los 100 candidatos más cercanos y solo
entonces los ordena mediante CrossText2Loc. Por tanto, esta reproducción oficial
no es una búsqueda global independiente del ground truth.

Los experimentos futuros se separarán en:

- A: reproducción oficial, GT → 100 vecinos → CrossText2Loc;
- B: baseline Madrid sobre un catálogo fijado, sin GT en consulta;
- C: propuesta con intención geográfica LLM, preselección OSM determinista,
  `candidate_id`, CrossText2Loc y Top-K, sin GT en consulta.

No se mezclarán las métricas de A, B y C. La documentación completa está en
[CROSSTEXT2LOC_REPRODUCTION.md](CROSSTEXT2LOC_REPRODUCTION.md) y el resumen
saneado en
[`results/reproductions/crosstext2loc-newyork-osm-gb10-v1/`](../results/reproductions/crosstext2loc-newyork-osm-gb10-v1/).

## Materialización F3 de Madrid

### Objetivo y entorno

El 14 de octubre de 2026 se materializaron los bundles geométricos F3 para los
manifests F1 de 50 m y 25 m, sin red, imágenes, embeddings ni datos de
evaluación. El código efectivo cubierto por D052 correspondía al commit
`425ac494cf50b26ca14037d4d238550a91ab42f7`, con Python 3.12.3, NumPy 2.5.4,
Shapely 2.1.2 y GEOS 3.13.1 sobre Linux/ext4. El entrypoint F3.8 todavía no
estaba versionado y el worktree contenía cambios locales; por tanto, ese commit
no identifica por sí solo el script operativo usado. No se conserva un hash
histórico verificable de aquellos bytes del entrypoint.

Inputs comunes:

- snapshot F2: `osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141`;
- raw F2: 8.420.815 B, 25.537 nodes, 4.240 ways y 498 relations;
- reglas D049: `way_is_area-v1`, SHA-256
  `cf81018ba820557c59c2c27de7ea6b314009abed040cd11249e94ed1a3a10583`.

### Comandos

Las primeras publicaciones se ejecutaron primero para 50 m y después para 25 m.
Cada comando se repitió después para verificar cache hit. Las rutas históricas
`madrid-*-first.json` fueron reutilizadas accidentalmente y ahora contienen
informes de cache hit, no la evidencia de publicación inicial. Los tiempos de
primera publicación de la tabla proceden de la salida JSON capturada durante
BUILD; esta limitación se conserva explícitamente y esos informes no se
reconstruyen de forma artificial.

El entrypoint corregido exige nombres independientes y publicación no-replace
bajo `results/generated/f3/`, por ejemplo `*-publish.json` y
`*-cache-hit.json`. La raíz operativa queda fijada mediante un descriptor abierto
sin seguir symlinks y debe existir previamente; cada informe se escribe en un
inode anónimo `O_TMPFILE` y
se enlaza sin reemplazo desde su descriptor. La trazabilidad se captura al
inicio. Un error posterior al hard link distingue un informe no publicado de
uno visible cuya durabilidad no ha podido confirmarse. Los comandos de
verificación conservados son:

```bash
.venv-geo/bin/python -B scripts/materialize_f3_bundle.py \
  --manifest data/processed/catalog/manifest-50m.json \
  --snapshot-dir data/raw/osm/snapshots/osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141 \
  --report-json results/generated/f3/madrid-50m-cache-hit.json

.venv-geo/bin/python -B scripts/materialize_f3_bundle.py \
  --manifest data/processed/catalog/manifest-25m.json \
  --snapshot-dir data/raw/osm/snapshots/osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141 \
  --report-json results/generated/f3/madrid-25m-cache-hit.json
```

### Resultados observados

| Medida | 50 m | 25 m |
|---|---:|---:|
| Manifest SHA-256 | `ad35d5cb3b602a9ce313e06e10f913f169430d62a948c0f5e77b396bc810f2aa` | `a23d3f3b54958661db76914dff9ff40a3f01a133ee86499fb9e4ddf706a49f11` |
| Candidatos | 253 | 1.115 |
| Objetos indexados | 26.546 | 26.546 |
| Asociaciones | 23.808 | 30.118 |
| Objetos multi-cell | 1.349 | 2.235 |
| Relations emitidas | 196 | 210 |
| Members asociados | 945 | 1.058 |
| Apariciones de `candidate_id` en relations | 2.122 | 3.918 |
| Tamaño total | 18.744.138 B | 20.917.604 B |
| Tiempo total, primera publicación | 8,362 s | 10,980 s |
| Pico RSS del proceso | 1.385.760 KiB | 1.385.760 KiB |
| Segunda ejecución | cache hit | cache hit |

IDs publicados:

- 50 m: `f3-madrid-pilot-associations-sha256-5f4af89b9349de792d3a60752a15f227d49b96cdb688a671504e4cf30bf68453`;
- 25 m: `f3-madrid-pilot-associations-sha256-902e8edcd7892c4b9f6a686a6573fb5c15bf19858ecf2ce14d09fb687e9e0ffa`.

Hashes de outputs 50 m:

| Archivo | SHA-256 | Bytes |
|---|---|---:|
| `osm_objects.jsonl` | `c928a1b9a1b43d89d3376395043aca6fe37803f17941823af966ac0049a3e94f` | 10.583.015 |
| `candidate_osm_associations.jsonl` | `6a43797300c40628c55c64e0fd72bde6a86ccebc6614a7883dfcfea637144b20` | 7.810.063 |
| `relation_context.jsonl` | `2e91a080b6da1be95913ad1a630bf14be7194d10fb4225ea348c0ecbb5618897` | 346.556 |
| `provenance.json` | `d637f6ef3f2168f7cdcf52412cd04c94bd0adb199e584f65b34841a4e9fbc7ea` | 4.150 |
| `sha256.txt` | `99982cd5d0357f83ad6c02cec24745fd69e8b93e01eefe1215b53c8e94029f0f` | 354 |

Hashes de outputs 25 m:

| Archivo | SHA-256 | Bytes |
|---|---|---:|
| `osm_objects.jsonl` | `c928a1b9a1b43d89d3376395043aca6fe37803f17941823af966ac0049a3e94f` | 10.583.015 |
| `candidate_osm_associations.jsonl` | `e6073f04ec36e565b972c1bb687273547c855b08c3a26c135f1dcbe2068ae4d3` | 9.852.406 |
| `relation_context.jsonl` | `463061b5273632354a846c0ff053fe940c00a5c67a3be6db9298254dc120fee2` | 477.679 |
| `provenance.json` | `528e2cee3388e6e1f889dd2ab19387ffe5b1e6c5a3e4f4ebc4f3d5c31d5a2da8` | 4.150 |
| `sha256.txt` | `0a898420116658d9983222ac94f823db2a688487e859c1fbd49299f5f51d6ba9` | 354 |

Los cinco archivos de cada bundle superaron la validación integral posterior.
La repetición conservó hashes, tamaños y mtimes. Los informes operativos están
bajo `results/generated/f3/`, fuera del bundle canónico e ignorados por Git. Los
informes históricos conservados registran `git_commit`, pero no el estado sucio
ni el hash del entrypoint; el formato corregido añade ambos campos y su propia
versión, capturados antes de cargar los inputs. El pico RSS es acumulado para el
proceso y no una medición independiente por etapa. Las verificaciones de cache
hit de 50 m y 25 m realizadas después de la publicación se solaparon
temporalmente; esto no alteró los bundles ni sus locks independientes por ID.
