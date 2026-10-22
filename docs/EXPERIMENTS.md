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

## F4.2: galería completa F1 de 50 m

### Artefactos y ejecución

- Selección: `f4-full-50m-gallery-v1`, 253 candidatos en orden del manifest F1.
- Cobertura Geofabrik previa: 253 cubiertos, 0 sin cobertura.
- Bundle visual:
  `f4-madrid-visual-sha256-15310268e0fed30180085c7ec1f14fce696c4ba94e83bf9727970451cc82f564`.
- Manifest visual SHA-256:
  `a31724ab8a5f8f9beb30f81fe50a36489214f898ec25ac8ad93f839871b90996`.
- Imágenes: 253 PNG válidos, 52.222.622 bytes en total.
- Render limpio: 253 renders, 0 hits, 355,39 s.
- Reanudación: 0 renders, 253 hits, mismo ID, 164,67 s.
- Bundle de embeddings:
  `f4-madrid-embeddings-sha256-199dae0e3eb38b206004557f20fae0ef98f620621458fc64c2dfa3f7ef7f84c1`.
- Matriz: `(253, 768)`, `float32`, normalizada L2, 777.344 bytes.
- Extracción GPU observada: 16,52 s.

Las tres consultas se redactaron como sondas cualitativas en inglés; no se
derivan de un dataset con coordenada verdadera y no constituyen evaluación.

| Query | Top-1 | Score coseno | Coordenada WGS84 |
|---|---|---:|---|
| `A large urban square surrounded by buildings and narrow streets` | `...R0013_C0012` | 0,21134724 | 40,4180647717; -3,7016966714 |
| `A broad avenue next to a green park` | `...R0012_C0013` | 0,20875248 | 40,4176179232; -3,7011026735 |
| `A dense block with a major road intersection and many buildings` | `...R0002_C0003` | 0,21027139 | 40,4130778027; -3,7069487074 |

Los JSON canónicos permanecen fuera de Git en
`results/generated/f4/madrid-f42-final-en-001.json`,
`madrid-f42-final-en-002.json` y `madrid-f42-final-en-003.json`. Todos
referencian el bundle final `199dae0e...`, declaran `gallery_count: 253`,
`ranking_method: exhaustive_cosine` y el mismo checkpoint. El archivo
`madrid-f42-final-en-001-repeat.json` repite la primera consulta y conserva el
mismo ranking y scores. Las puntuaciones no son probabilidades ni prueban que el
candidato sea geográficamente correcto. D007, D013 y D016 permanecen abiertas.

## F4.3: infraestructura de evaluación

El borrador `madrid-f43-draft-v1` contiene tres sondas técnicas de F4.2 en la
partición `development`. Ninguna tiene coordenada de referencia verificada:

```text
consultas: 3
rankings reales disponibles: 3
referencias validadas: 0
referencias evaluables: 0
metrics_available: false
```

El evaluador produjo localmente:

```text
f4-madrid-evaluation-sha256-627b2b29155d2762b096771f895aaaaa5af88f298353c3babfd75d271eca7b79
```

Los tres rankings Top-5 quedan fijados por SHA-256, pero ninguno está preparado
para Recall@10. Recall@1/5/10, errores y GeoRecall permanecen `null`; no se
transformó ausencia de datos en ceros. Las pruebas sintéticas cubren posiciones exactas 1, 5 y 10,
ausencia de Top-K, Haversine, huecos F1, bordes, referencias pendientes y
contaminación entre particiones. Sus resultados validan software y no son
rendimiento de CrossText2Loc.

## F4.4: galería 25 m y comparación con 50 m

### Galería y embeddings

```text
selección: f4-full-25m-gallery-v1
candidatos: 1.115
visual: f4-madrid-visual-sha256-ebe6c91b8ed5600d65c3021a53c768d6e65545777efda92d7b171f705a0d42e9
embeddings: f4-madrid-embeddings-sha256-2874609b95005b65823ce6efb5b7888b9d1500b7ec2f6ba301dfc3083cb56c2a
```

- 1.115/1.115 footprints cubiertos y PNG validados.
- 231.485.372 bytes de PNG.
- Render limpio: 989,67 s; 1.115 renders y 0 hits.
- Repetición: 170,58 s; 0 renders y 1.115 hits.
- Embeddings: `(1115, 768)`, `float32`, finitos y L2.
- Generación GPU: 46,88 s; repetición con el mismo ID.

### Top-10 comparativo

| Consulta | Top-1 25 m | Score | Top-1 50 m | Score | Distancia entre Top-1 |
|---|---|---:|---|---:|---:|
| Plaza urbana y calles estrechas | `...R0027_C0026` | 0,21502331 | `...R0013_C0012` | 0,21134724 | 39,46 m |
| Avenida amplia junto a parque | `...R0012_C0028` | 0,20504767 | `...R0012_C0013` | 0,20875248 | 315,27 m |
| Bloque denso e intersección principal | `...R0004_C0007` | 0,19638419 | `...R0002_C0003` | 0,21027139 | 17,67 m |

Los ranking sets son `e83d1f82...` para 25 m y `d803e6f3...` para 50 m. Las
ejecuciones F4.3 son `4d9b2494...` y `0c947675...`, respectivamente, ambas con
tres Top-10 listos y cero referencias validadas. La comparación técnica es
`1fc6e96d...`. Ambas ramas usan los mismos textos,
checkpoint, encoder y perfil visual, pero galerías de tamaños distintos. F4.3
acepta los dos Top-10 y registra cero referencias validadas; por tanto Recall,
GeoRecall y errores empíricos continúan no disponibles. No se infiere mejora o
empeoramiento a partir de estos tres ejemplos.

## F4.5: estabilidad lingüística controlada

El query set `0f202067...` contiene tres anchors y 24 variantes técnicas:
paráfrasis, sinónimos, expansión, acortamiento, eliminación, ambigüedad,
contradicción y traducción al español. Se ejecutaron 27 Top-10 sobre cada
galería, sin ground truth.

```text
ranking set 50 m: 2f400901...
ranking set 25 m: 6d3bd2f0...
informe 50 m: 2421b0fc...
informe 25 m: 923677b8...
```

| Galería | Relación | n | Top-1 igual | Jaccard@10 | Distancia de salida Top-1 |
|---|---|---:|---:|---:|---:|
| 50 m | Equivalencia aproximada | 12 | 0,167 | 0,184 | 314,9 m |
| 50 m | Pérdida de información | 9 | 0,000 | 0,067 | 387,6 m |
| 50 m | Cambio semántico | 3 | 0,333 | 0,578 | 192,5 m |
| 25 m | Equivalencia aproximada | 12 | 0,000 | 0,085 | 434,5 m |
| 25 m | Pérdida de información | 9 | 0,000 | 0,006 | 484,6 m |
| 25 m | Cambio semántico | 3 | 0,667 | 0,356 | 37,2 m |

Las tres traducciones ES no conservaron Top-1. Su Jaccard@10 medio fue 0,055 en
50 m y 0,000 en 25 m. Esto no mide precisión del español: son tres sondas
controladas, sin ubicación verdadera y con checkpoint de Nueva York.

Los batches tardaron 8,29 s en 50 m y 10,28 s en 25 m, incluida una carga de
modelo por galería. `geographic_accuracy_available` permanece `false`.

## F4.6: runtime residente para el MVP

La prueba real cargó una instancia FP32 del checkpoint y ambas galerías dentro
del mismo proceso. La primera petición Top-10 multigalería codificó el texto una
vez y produjo exactamente los mismos candidatos y scores que F4.4.

```text
inicialización: 5.571,25 ms
primera consulta multigalería: 154,19 ms
CUDA asignada tras carga: 1.712.462.336 B
CUDA reservada tras carga: 1.772.093.440 B
pico de primera consulta tras reset post-carga, asignado: 1.741.103.104 B
pico de primera consulta tras reset post-carga, reservado: 1.803.550.720 B
```

Se confirmó repetición idéntica, tres codificaciones para tres peticiones
multigalería, consulta en español, dos matrices residentes y rechazo después de
cerrar el runtime. El informe local `results/generated/f4/f46-smoke-final.json`
permanece fuera de Git. Estas medidas no son un SLA ni métricas de precisión.

## MVP.1: smoke HTTP interno

La API FastAPI se ejecutó en la imagen ARM64/CUDA con un único worker Uvicorn.
El puerto 8000 estaba ocupado por un servicio ajeno y se utilizó temporalmente
`127.0.0.1:18000`, sin detenerlo.

El smoke de pila automatizado verificó un único proceso Uvicorn, liveness,
readiness, capabilities, consultas Top-10 de ambas galerías, multigalería,
repetición, paridad con F4.4, request ID y errores 422/404. La primera consulta
multigalería tardó 149,43 ms. SIGTERM cerró el lifespan y no quedó contenedor
residual.

## MVP.2: integración frontend real

Se ejecutó Vite en `127.0.0.1:5173` con proxy hacia MVP.1 en el puerto temporal
18000. Una petición española enviada por `/api/v1/retrievals` devolvió cinco
candidatos reales de 50 m; otra devolvió Top-3 de 25 m y su repetición produjo
exactamente los mismos candidatos y scores. La API mantuvo un único proceso
Uvicorn y ambos servicios se detuvieron sin residuos.

Los tests Node y la build Vite pasaron. El browser-check con API fake y Leaflet
no pudo ejecutarse porque la PGX no dispone de Chrome/Chromium ni `CHROME_PATH`;
no se presenta como validación visual superada.

## MVP.3: despliegue integrado y browser-check ARM64

El 19 de octubre de 2026 se desplegó la aplicación mediante
`compose.mvp.yaml`. Nginx sirvió la build estática y redirigió `/api` a FastAPI
en la red Compose; solo el frontend se publicó en loopback. La imagen API
`crosstext2loc-gb10:ngc26.02` cargó un único runtime y Uvicorn ejecutó un worker.

```bash
MVP_HTTP_PORT=18080 scripts/smoke_mvp3_stack.sh
```

El smoke verificó healthchecks, mismo origen, errores 422/404, repetibilidad,
shutdown y ausencia de contenedores residuales. Chromium 155 se instaló dentro
de una imagen Debian ARM64 aislada, sin modificar el sistema operativo host.
Pasaron tanto la prueba visual con API simulada como el recorrido real:

```text
Chromium → Nginx → FastAPI → CrossText2Loc GB10 → Top-K → Leaflet
```

Resultados técnicos de la consulta española utilizada por el smoke:

| Galería | K | Top-1 | Score coseno |
|---|---:|---|---:|
| 50 m | 5 | `...S050_L050_R0013_C0009` | 0,2834689915 |
| 25 m | 3 | `...S025_L025_R0019_C0013` | 0,2912742496 |

La repetición conservó exactamente IDs, orden, scores y coordenadas. Esto
demuestra integración y determinismo, no precisión geográfica: la consulta no
dispone de una posición real validada. El informe local se conserva en
`results/generated/mvp3/stack-smoke.json`, fuera de Git. La operación completa
se documenta en [MVP.md](MVP.md).

El check HTTP bilingüe posterior reutilizó los tres pares inglés-español de
F4.5 sobre ambas galerías. Las 12 peticiones finalizaron y ninguna de las seis
comparaciones conservó Top-1. El solapamiento Top-10 fue 0 en cuatro casos, 1 en
parque/50 m y 2 en intersección/50 m. El informe local
`results/generated/mvp3/bilingual-check.json` registra estabilidad de salida,
no accuracy ni superioridad de un idioma. Procedimiento e interpretación:
[PRUEBAS_BILINGUES_MVP.md](PRUEBAS_BILINGUES_MVP.md).

## F5.1: contrato y plantilla de variantes textuales

F5.1 añadió un sidecar content-addressed ligado al dataset F4.3 para registrar
topónimos, orientación opcional y cuatro variantes textuales. La ejecución de
validación utilizó:

```bash
.venv-geo/bin/python scripts/validate_f5_textual_variants.py \
  --dataset config/madrid_f51_textual_variants_template.json \
  --source-query-dataset config/madrid_f43_query_dataset_draft.json
```

Resultado observado de la plantilla:

```text
observaciones F5.1: 0
ground truths validados: 0
comparaciones emparejadas listas: 0
precision_metrics_available: false
osm_preselection_status: standby_pending_tutor_decision
```

Esto valida contrato, identidad, referencia F4.3 y herramientas; no constituye
un dataset recogido, no ejecuta CrossText2Loc y no aporta métricas. No se
generaron traducciones ni descripciones cartográficas artificiales.

La suite específica F5.1 completó 14 tests y la regresión Python completa 308
tests. También pasaron el JSON Schema Draft 2020-12, el CLI de plantilla, los 8
tests Node y la build Vite. Checkpoint y manifests de embeddings conservaron sus
hashes. El MVP alcanzó readiness sin cambios de API, runtime o Compose.

## F5.2: transformación textual y comparación exploratoria

La inspección inicial no encontró un snapshot Hugging Face de `Qwen/Qwen3-8B`.
Se observaron modelos distintos (`Qwen3.8-27B`, Qwen2.5-7B-AWQ y un artefacto
Ollama `qwen3.8`), que no se usaron como sustitutos. En ese incremento inicial no
se descargaron pesos ni se ejecutó inferencia Qwen real; F5.2b, documentada a
continuación, resolvió posteriormente ese bloqueo con autorización expresa.

La ficha pública consultada declaró revisión
`b968826d9c46dd6066d109eabc6255188de91218`, 8,2B parámetros, licencia
Apache-2.0 y soporte non-thinking. Estos metadatos no sustituyen los hashes del
snapshot que finalmente se autorice.

El smoke técnico se ejecutó con dobles deterministas:

```bash
.venv-geo/bin/python scripts/smoke_f52_fake.py
```

Resultado:

```text
technical_fake_only: true
real_qwen_inference: false
rankings independientes: 8
comparaciones emparejadas: 6
geographic_accuracy_available: false
```

El smoke valida prompts, placeholders, artefactos, rankings inyectados y métricas
descriptivas. No valida Qwen, CrossText2Loc real ni precisión geográfica.

La suite F5.2 completó 11 tests específicos y la regresión Python completa 319
tests. También pasaron los tres JSON Schema F5, los 8 tests Node, la build Vite y
readiness del MVP. Checkpoint y manifests de embeddings conservaron sus hashes.

## F5.2b: Qwen3-8B real en PGX GB10

Se descargó exclusivamente `Qwen/Qwen3-8B` en la revisión
`b968826d9c46dd6066d109eabc6255188de91218` fuera de Git. Los cinco shards BF16
suman 16.381.470.720 bytes y sus SHA-256 coinciden con los OIDs publicados.

Dos ejecuciones completas en GB10 produjeron 18/18 textos y hashes idénticos. Los
tiempos de carga fueron 82,04 s y 89,28 s; la generación media fue 1,27 s por
variante y el pico CUDA asignado 16.425.854.976 B. Tras cerrar, la memoria CUDA
asignada quedó en 8.519.680 B y la reservada en 20.971.520 B.

Una revisión humana explícita aprobó las 18 variantes técnicas. CrossText2Loc
generó 48 rankings Top-10 y 36 comparaciones emparejadas sobre ambas galerías.
El informe declara `geographic_accuracy_available: false`; no se calculó Recall
ni error geográfico. Los artefactos completos permanecen en
`results/generated/f5/f52/`, fuera de Git. Véase
[PHASE5_TEXT_TRANSFORMATION.md](PHASE5_TEXT_TRANSFORMATION.md).

## F5.3: extracción geográfica estructurada real

Se implementaron schemas, extractor desacoplado, parser JSON, validación de
evidencia/semántica, provenance, identidad y comparación entre variantes. El
smoke fake cubrió diez casos y produjo 10/10 extracciones válidas.

Qwen3-8B real se ejecutó en tres campañas de diez sondas técnicas sin ground
truth. La campaña inicial produjo 1/10 válida; el reintento explícito 0/10; y el
prompt con mapa índice-caracter 0/10. Los errores principales fueron spans
incorrectos, formato de negaciones/ambigüedades, referencias inexistentes y
frames incompatibles. No se repararon salidas ni se relajó el contrato.

Una muestra se repitió dos veces: raw JSON y SHA-256 idénticos, pero ambas salidas
fueron rechazadas. La inferencia es reproducible para esa muestra, aunque la
calidad contractual sigue siendo insuficiente. Accuracy permanece no disponible.
Detalles: [PHASE5_GEOGRAPHIC_EXTRACTION.md](PHASE5_GEOGRAPHIC_EXTRACTION.md).

## F5.3b: generación guiada y variante inglesa cartográfica

Se diagnosticaron de forma reproducible las tres campañas F5.3 históricas. Sus
30 records acumularon 16 issues estructurales y 42 semánticos; 39 fueron spans
incorrectos. Los artefactos históricos se conservaron sin cambios.

Se compararon tres estrategias reales con `Qwen/Qwen3-8B`, revisión
`b968826d9c46dd6066d109eabc6255188de91218`, un intento, 512 tokens, seed 0 y
non-thinking:

| Estrategia | JSON válido | Estructura válida | Contrato final | Media por caso |
|---|---:|---:|---:|---:|
| Baseline F5.3 | 10/10 | 6/10 | 1/10 | 15.881,92 ms |
| Evidencia literal y offset determinista | 10/10 | 5/10 | 4/10 | 11.575,19 ms |
| LM Format Enforcer 0.11.3 + evidencia literal | 8/10 | 6/10 | 5/10 | 18.493,57 ms |

Dos salidas guiadas quedaron truncadas al alcanzar 512 tokens. Persistieron
errores semánticos y de referencias; la integración automática continúa
bloqueada.

El contrato textual v2 añadió `en_cartographic` sin modificar v1. CrossText2Loc
produjo 60 rankings Top-10. `en_cartographic` obtuvo acuerdo Top-1 0,000,
Jaccard@10 0,079 y distancia Top-1 media 328,2 m frente a `es_original`. Son
métricas de estabilidad sin ground truth. La extracción guiada sobre las cinco
variantes produjo 15/30 records válidos, 3/6 para cada tipo; no se observó ventaja
de `en_cartographic`. El resumen permanece fuera de Git en
`results/generated/f5/f53b/`.

## F5.4: auditoría de Ground Truth y plantilla

La auditoría de F4.3/F5 no encontró observaciones `human_in_situ` ni referencias
geográficas `validated`. Los únicos textos disponibles son tres sondas técnicas
F4.3 y fixtures de desarrollo sin GT. No se ejecutó una evaluación de precisión
ni se publicaron Recall/error de Madrid.

Se materializó la plantilla F5.4 contra los catálogos reales:

```bash
.venv-geo/bin/python scripts/prepare_f54_ground_truth_template.py \
  --output results/generated/f5/f54/ground-truth-template.json
```

Resultado:

```text
observation_count: 0
validated_count: 0
pending_count: 0
geographic_evaluation_ready: false
```

El artefacto permanece fuera de Git. Los manifests auditados contienen 1.115
candidatos de 25 m y 253 de 50 m. La infraestructura y métricas se verificaron
con fixtures sintéticos identificados exclusivamente como tests de software.
Procedimiento: [PHASE5_GEOGRAPHIC_EVALUATION.md](PHASE5_GEOGRAPHIC_EVALUATION.md).

## F5.5: snapshot Panoramax y cola piloto — vía sustituida

Se consultó el catálogo federado Panoramax sobre D004 y se congelaron los bytes
reales de la respuesta:

> Registro histórico: F5.6 eliminó el script de adquisición y esta orden ya no
> forma parte del flujo activo reproducible desde `main`.

El procedimiento quedó fijado en el commit histórico `ec1f4ae`; F5.6 retiró el
script de adquisición del flujo activo.

Resultado:

```text
items: 10
colecciones: 2
thumbnails descargados: 5
pending: 5
approved: 0
rejected: 0
```

Asignación geométrica: 25 m produjo 6 `accuracy_insufficient` y 4
`accuracy_unavailable`; 50 m produjo 1 `assigned`, 3
`accuracy_insufficient`, 2 `outside_catalog_coverage` y 4
`accuracy_unavailable`. No se ejecutó CrossText2Loc ni se generaron descripciones
o variantes. El snapshot de 456 KiB y la galería HTML permanecen fuera de Git.
El snapshot válido es
`f55-panoramax-inventory-sha256-0664a7bdcb06c84d46dc81b03f8ea9f468da2bab7ac695b3f7b9ce523ca19e89`,
con raw SHA-256
`67882b891ac6a6523ea93ba1d8a3e99a047b4cbf7a4c6354a87483b7187b2d1a`.
Un intento anterior quedó invalidado por identidad tras detectar aliasing y no se
usa como resultado.
La migración y las limitaciones vigentes se documentan en
[PHASE56_STREETVIEW_DOCUMENTARY.md](PHASE56_STREETVIEW_DOCUMENTARY.md).

## F5.5b: revisión visual y cola complementaria — vía sustituida

La revisión manual comunicada por el responsable se materializó en un contrato
Panoramax v2 sin modificar la aprobación GT:

> Registro histórico: los contratos y scripts Panoramax fueron retirados del
> flujo activo por D073; no ejecutar esta vía en nuevas campañas.

```text
suitable: 1
limited: 2
unsuitable: 2
GT pending: 5
GT approved: 0
GT rejected: 0
```

La única imagen `suitable` conserva una descripción española propuesta pendiente
de revisión final y asignaciones `accuracy_insufficient` en 25 m/50 m. Una imagen
`unsuitable` tiene celda 50 m `assigned`, demostrando que calidad visual y
asignación geométrica son dimensiones independientes.

Los cinco items restantes se publicaron como segunda cola, con cinco thumbnails
y estado visual/GT `pending`. Ninguno mejora automáticamente la cobertura exacta:
tres tienen precisión declarada pero asignaciones insuficientes o fuera de
cobertura y dos no declaran precisión. Los artefactos permanecen fuera de Git en
`results/generated/f5/f55b/`. El procedimiento histórico está en `85fd35b`; la
vía vigente se documenta en
[PHASE56_STREETVIEW_DOCUMENTARY.md](PHASE56_STREETVIEW_DOCUMENTARY.md).

## F5.5c: benchmark `synthetic_osm`

La segunda cola Panoramax quedó revisada con 1 `suitable`, 3 `limited` y 1
`unsuitable`. El total de diez imágenes es 2/5/3 respectivamente; los diez GT
siguen `pending` y no se importaron a F5.4.

F5.6 retiró posteriormente Panoramax del flujo activo; estos resultados se
conservan solo como historial experimental.

Se materializó un benchmark OSM separado:

```bash
.venv-geo/bin/python scripts/build_f55c_synthetic_osm_benchmark.py \
  --count 40 --seed 55 --minimum-spacing-m 70 \
  --output-root results/generated/f5/f55c-final
```

Resultado:

```text
observaciones: 35
development: 24
evaluation: 11
bloques espaciales: 23
separación mínima: 70,69 m
media de entidades/relaciones: 3,77
review pending: 35
```

Las 35 posiciones están `assigned` en 25 m y 50 m por construcción sintética.
Las evidencias se revalidaron contra F3. Se solicitaron 40, pero con 80 m solo se
obtuvieron 25; se adoptó 70 m, el mayor umbral ensayado que superó el mínimo de
30. No se rellenó la muestra. Benchmark final:
`f55c-synthetic-osm-sha256-bf7aea13116cda8e027343535f0a6d2de3bd6582aa09c6a65d1f14e9b24873c2`.

Esta era la situación al congelar el benchmark. Posteriormente se ejecutó una
campaña exploratoria separada, sin aprobar las 35 observaciones: Qwen3-8B generó
140/140 derivados, la auditoría admitió 175/175 textos y CrossText2Loc produjo
350/350 rankings exhaustivos. El resultado
`f55c-exploratory-evaluation-sha256-ad492e0d6d33e1edd1db092303470aff59685de600d71fb6eb8f2bf2e22b2fe8`
declara `synthetic_osm`, `real_ground_truth=false`, cero casos oficiales y no se
agrega con F5.4 o F5.7. Detalles y métricas:
[PHASE5_SYNTHETIC_OSM_BENCHMARK.md](PHASE5_SYNTHETIC_OSM_BENCHMARK.md#evaluación-exploratoria-provisional-posterior).

## F5.6: Street View documental local

Se verificaron inicialmente cinco PNG locales. SV-02 se confirmó fuera de D004 y
de ambas coberturas, por lo que se retiró del dataset activo y se eliminó su PNG;
URL, panorama y coordenadas permanecen como `SV-EXCLUDED-01`. Las antiguas
SV-03/04/05 se renumeraron de forma continua a SV-02/03/04 conservando IDs
históricos. Se materializó:

```text
f56-streetview-documentary-sha256-575695ca55793d6077f9a464cfb53b61366871c7e721d9b0a3fe60e3d253be9a
```

Resultado:

```text
observaciones: 4
dentro de D004 por coordenada de enlace: 4
excluidas antes del dataset: 1 (SV-02)
descripciones formalmente revisadas: 0
Recall exacto elegible: 0
variantes generadas: 0
rankings: 0
```

SV-01/03/04/05 tienen asignación puntual `assigned` en ambas galerías, pero la
incertidumbre posicional es desconocida; no se presenta como celda GT validada.
SV-02 excedía D004 en 16,22 m, la cobertura 25 m en 29,29 m y la cobertura
50 m en 54,33 m. No se ejecutaron Qwen ni CrossText2Loc. Procedimiento:
[PHASE56_STREETVIEW_DOCUMENTARY.md](PHASE56_STREETVIEW_DOCUMENTARY.md).

Tras completar F5.9 H01–H10 se retiraron las cuatro capturas PNG locales y el
HTML de revisión que dependía de ellas. No participan en H01–H10 ni eran
necesarias para reproducir los rankings ya congelados. Se conservan el dataset
F5.6, hashes, URLs, panorama IDs, asignaciones y artefactos F5.7 para interpretar
los resultados históricos sin afirmar que las imágenes continúan disponibles.

## F5.7: Qwen y evaluación aproximada Street View

Se adaptó el dataset F5.6 canónico `575695ca...` a F4.3/F5 v2 sin incluir
coordenadas en las entradas. Qwen3-8B real, revisión `b968826d...`, produjo 16/16
derivados; los controles automáticos admitieron las 20 variantes. CrossText2Loc
con pesos congelados generó 40/40 Top-10 sobre las galerías 25 m y 50 m.

El Recall@1/5/10 de celda aproximada fue 0 en todas las combinaciones. El
GeoRecall@10 a 100 m estuvo entre 0,50 y 0,75, y el error Top-1 medio entre
276,43 m y 420,02 m. Son cuatro coordenadas de enlace con incertidumbre
desconocida, no métricas oficiales F5.4 ni evidencia de superioridad. Detalles:
[PHASE57_EXPERIMENTAL_EVALUATION.md](PHASE57_EXPERIMENTAL_EVALUATION.md).

Una segunda ejecución CrossText2Loc conservó Top-10 y scores idénticos y añadió
latencias por fila. La mediana de retrieval quedó entre 6,37 y 8,13 ms; la media
de `es_original` incluye calentamiento inicial. El informe final con manifest v2
está en `results/generated/f5/f57-final-v3/`.

## F5.9: H01/H02 con referencias Street View

Se materializaron dos descripciones humanas, sus traducciones inglesas aportadas
por el responsable y ocho transformaciones Qwen3-8B reales. Marcador y panorama
se conservaron por separado; el panorama se utilizó como referencia experimental
de incertidumbre desconocida y nunca entró en Qwen o retrieval.

Ambas coordenadas están dentro de D004. H01 queda fuera de la cobertura efectiva
de las celdas completas en ambas galerías, por lo que solo admite Haversine y
GeoRecall. H02 queda `assigned` en 25 m y 50 m. CrossText2Loc produjo 24/24
rankings para seis controles por caso y dos galerías.

El inglés humano mejoró H01, pero empeoró H02 frente al español. Qwen reprodujo
solo parte de esas tendencias y no mostró una mejora inglesa consistente. La
evaluación se identifica como
`f59-exploratory-evaluation-sha256-3dabf819cfa2ba78e3b8b859683c4e70d060a462f888addf3178261d15a5e8ac`.
Detalles: [PHASE59_HUMAN_STREETVIEW_EXPERIMENT.md](PHASE59_HUMAN_STREETVIEW_EXPERIMENT.md).

La ampliación H03–H10 añadió ocho descripciones orientadas, 32 transformaciones
Qwen y 80 rankings. Todas las relaciones y los nombres protegidos superaron la
auditoría; la traducción convencional modificó un nombre, registrado aparte. En
el agregado común H01–H10, `es_original` lideró o empató GeoRecall@10 a 50 m en
ambas galerías. Las variantes inglesas alcanzaron 0,60 a 100 m solo en la galería
de 50 m y empeoraron en 25 m. No se seleccionó variante definitiva.

## F5.10: consolidación post hoc

Sin ejecutar modelos se recalcularon métricas H03–H10 y H01–H10 desde candidatas
individuales, incluyendo numeradores, denominadores, GeoRecall@1, Recall@1,
rangos y transiciones pareadas. La auditoría detectó que SV-02/H10 reutilizan el
mismo panorama y que SV-03/H03 pertenecen al mismo entorno inmediato; F5.7 no se
trata como muestra independiente.

`es_original` lideró o empató GeoRecall@10 a 50 m. `en_cartographic` quedó como
candidata Qwen para una futura validación, no como default aprobado. Resultado:
`f510-consolidation-sha256-c4be6f6577be7403f419396a8f1953d25315a6afb3945a049c2d2ff9c4e81a22`.
Detalles: [PHASE510_METRIC_CONSOLIDATION.md](PHASE510_METRIC_CONSOLIDATION.md).

## Evaluación independiente H11–H25

Se congelaron 15 descripciones humanas nuevas con reparto aleatorio 5/5/5 en
sencilla, intermedia y compleja. H16 se identificó como fotografía interior. Las
15 referencias están dentro de D004 y asignadas en ambas galerías, sin
solapamientos ≤25 m ni panoramas repetidos respecto de F5.7/H01–H10.

Qwen produjo 15/15 `en_cartographic` y CrossText2Loc generó 60/60 rankings. En
exteriores, GeoRecall@10 a 50 m pasó de 3/14 a 5/14 en 25 m y de 3/14 a 8/14 en
50 m. H16 empeoró con Qwen en ambas galerías. El resultado
`h11-h25-evaluation-sha256-952d33d7312f5e418bf43ccbdba4277800653b36a77f5bd026e22b85473502bf`
aporta evidencia favorable pero no resuelve D076 por incertidumbre de referencia,
revisión visual pendiente y regresiones individuales. Detalles:
[PHASE_H11_H25_EVALUATION.md](PHASE_H11_H25_EVALUATION.md).

## F5.11: MVP experimental 2 × 2

Se implementó un contrato Atlas v2 que exige exactamente una galería 25/50 m y
un modo Sin LLM/Con LLM. Sin LLM no invoca Qwen; Con LLM ejecuta una única
transformación `en_cartographic`, valida su salida y realiza un único ranking
Top-10. No existe fallback, fusión ni ejecución multigalería.

Los cuatro caminos pasan tests con dobles y el frontend Vite compila. El smoke
host inicial no pudo arrancar por entornos separados, por lo que se construyó la
imagen unificada `crosstext2loc-gb10:f511` con Transformers 5.9.0. El smoke
conjunto cargó ambos modelos y alcanzó un pico CUDA asignado de 18.141.917.696 B.
Después, el smoke integrado real validó las cuatro combinaciones mediante
Nginx/FastAPI/GPU/Leaflet y Chromium ARM64. D076 permanece pendiente porque esta
validación es funcional, no evidencia de superioridad científica.

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
[CROSSTEXT2LOC.md](CROSSTEXT2LOC.md#resultado-de-la-reproducción-oficial) y el resumen
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
