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

El check HTTP bilingüe histórico reutilizó los tres pares inglés-español de
F4.5 sobre ambas galerías. Las 12 peticiones finalizaron y ninguna de las seis
comparaciones conservó Top-1. El solapamiento Top-10 fue 0 en cuatro casos, 1 en
parque/50 m y 2 en intersección/50 m. El informe local
`results/generated/mvp3/bilingual-check.json` registra estabilidad de salida,
no accuracy ni superioridad de un idioma. Procedimiento e interpretación:
[PHASE4_LINGUISTIC_ROBUSTNESS.md](PHASE4_LINGUISTIC_ROBUSTNESS.md#check-http-histórico-del-mvp).

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

## Smoke aislado Qwen3-VL-2B con Mapillary

El 23 de octubre de 2026 se ejecutó un smoke local, sin servidor, GT, reranking
ni CrossText2Loc residente. Se usó `Qwen/Qwen3-VL-2B-Instruct` en la revisión
autorizada `89644892e4d85e24eaac8bacfd4f463576704203`; no se descargó el 4B. El
peso `model.safetensors` mide 4.255.140.312 B y tiene SHA-256
`7de1838c87a5349b016c26a1c3f7d2bc400a3d485f95ef39a7059ffd734977a0`.

La muestra se fijó antes de inferencia con tres fotografías ya anotadas: una
`useful`, una `partially_useful` y una `not_useful`. El request recibió solo la
descripción española, un `candidate_id` opaco y la imagen. Las anotaciones
humanas se unieron después para la comparación.

| Medida | Resultado |
|---|---:|
| JSON contractuales | 3/3 |
| Acuerdo ordinal con utilidad humana | 1/3 |
| Carga del modelo | 26,57 s |
| Ejecución total | 34,83 s |
| Inferencia por imagen | 3,99 / 2,63 / 1,51 s |
| Pico CUDA asignado | 4.479.027.712 B |
| Pico CUDA reservado | 4.513.071.104 B |
| Pico RSS | 5.357.838.336 B |
| Espacio libre posterior | 9.297.989.632 B |

El contrato técnico fue viable, pero la revisión cualitativa detectó
sobreafirmaciones. El modelo declaró visibles una inmobiliaria y una tienda que
la anotación humana marcó como no verificables, y clasificó como
`partial_match` una fotografía humana `not_useful`. Por tanto, el smoke no
autoriza Fase 3, reranking ni integración. El resultado local está en
`results/generated/mapillary/qwen3-vl-2b-isolated-smoke/result.json`, SHA-256
`7d1d12b9cc3e0556cd8d834c4c0dd4b9fa781fa1616677260f41aa2f7b0e1bdb`.

La evaluación de desarrollo posterior aplicó un prompt conservador distinto a
las 24 imágenes. Obtuvo 19/24 JSON válidos, 14/24 acuerdos con un proxy ordinal
explícito, 11/24 imágenes con coincidencias sobreafirmadas y 11/24 con
contradicciones injustificadas. Cinco salidas se truncaron por repetición. Se
adopta la categoría B: apoyo exploratorio con revisión humana, sin integración ni
reranking. Detalles:
[PHASE_QWEN3_VL_2B_CONSERVATIVE_EVALUATION.md](PHASE_QWEN3_VL_2B_CONSERVATIVE_EVALUATION.md).

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

## Comparación real A/B H16–H23

El 29 de octubre de 2026 se completó la adquisición e inferencia de la
comparación pareada entre selección adaptativa por cobertura y selección
adaptativa geométrica. Se conservaron los manifests, claims, prompts, pesos,
generación determinista y reranking simétrico congelados. El ground truth se
cargó únicamente después de publicar el ranking final.

- Se descargaron 474 miniaturas Mapillary nuevas y se reutilizaron 37 assets
  históricos: 511 assets físicos, 65.479.795 B y hashes SHA-256 verificados.
- La identidad definitiva por bytes detectó alias entre `image_id`: el plan pasó
  de 9.613 identidades provisionales a 9.594 tareas físicas por modelo. Las
  llamadas nuevas permanecieron en 6.956 por modelo.
- Por modelo se reutilizaron 826 tareas históricas, se ejecutaron 6.956 y 1.812
  se resolvieron como abstenciones de política; no hubo outputs inválidos.
- 2B registró 3.230,96 s de ejecución del plan y 8B 6.108,42 s en su sesión de
  cierre. Estos tiempos no representan todo el tiempo de pared acumulado de 8B,
  porque hubo una sesión anterior interrumpida.
- El ranking congelado tiene ID
  `h16-h23-selector-ranking-set-sha256-5c153de633ed8338c9026d7702991e90bd55fcc50a0dc6551fe9b98845d36eb9`
  y SHA-256
  `598df3d8a62fc7ee3f6f07c8fa0281bebd3ec9f4b9543ef1ec30bf0573275b3f`.
- Ninguna combinación modelo/selector cambió Top-1 ni cruzó la frontera Top-10.
  GeoRecall@1/5/10 fue 0/2 tanto a 50 m como a 100 m antes y después. La
  distancia Top-1 fue 407,42 m para H16 y 196,80 m para H23; media 302,11 m.

La primera sesión 8B fue terminada por el límite temporal de la herramienta, no
por un error del modelo. Durante una reanudación posterior coexistieron dos
procesos sobre el mismo JSONL: el checkpoint conserva 2.616 índices duplicados.
No existen conflictos semánticos: 708 duplicados son idénticos y 1.908 conservan
la misma identidad, estado y veredicto con tiempos distintos. El resultado final
atómico contiene exactamente 9.594 identidades únicas y coincide con la última
versión de cada índice. El JSONL se conserva sin modificar como evidencia, pero
no debe reutilizarse para otra reanudación; el pipeline necesita exclusión mutua
antes de una campaña futura.

Artefactos principales:

| Archivo | SHA-256 |
|---|---|
| `physical-assets.json` | `96abfe5582cb261e6b5bc3e424bfdaaa62c44fb55b2add970da10f924a4940ff` |
| `physical-task-plan.json` | `577f7b5f94e19ea71fa80634fa1d72586a219e8d2da7370441a0d3263202c399` |
| `qwen3-vl-2b-physical-results.json` | `c3f506ccce757d4e1838d583eac9748bfe86a603ca76d5eb010f94b40f5ff209` |
| `qwen3-vl-8b-physical-results.json` | `10bbbe9b07b7a0f5f94899876674a8e3c232ea393169f63e39f6b2a53bae9ff4` |
| `frozen-rankings.json` | `598df3d8a62fc7ee3f6f07c8fa0281bebd3ec9f4b9543ef1ec30bf0573275b3f` |
| `geographic-evaluation.json` | `1c15c6110a873049d8378cdfac98d98dfe414827477a2edf41a03f8b2f7fd7de` |
| `final-report.json` | `7c88871e63c52770253f58536049d5a450384eaaf7c41ec15aeecde7e5f964ed` |

El resultado no apoya promover ninguno de los dos selectores como mejora
geográfica. Solo cubre dos consultas development seleccionadas
retrospectivamente, con referencias de incertidumbre desconocida y desajuste
interior/exterior en H16; no permite una conclusión de generalización.

## Diagnóstico causal y piloto sin nuevas inferencias

El 30 de octubre de 2026 se reutilizaron los outputs congelados H16–H23 para
auditar la fórmula y ejecutar un barrido predefinido de peso positivo
`0/0,1/0,2/0,5/1/2`, sin ground truth. Los pesos altos producen cruces Top-10 y
cambios Top-1, pero su comportamiento varía por consulta, modelo y selector; no se
elige ningún peso con estas consultas development.

Se implementó una variante discriminativa experimental que descuenta soporte
imagen-claim compartido, pondera compatibilidad espacial y combina secuencias
independientes. Con peso 0,2 no cambia Top-1; solo H23 geométrico produce una
entrada Top-10 para 2B y 8B. No se evalúa ese cruce como mejora geográfica ni se
acepta la política hasta calibrarla en H26–H37.

Artefacto:

- `results/generated/mapillary/h16-h23-reranking-diagnostics-v1/diagnostic.json`;
- SHA-256: `27f6487090e1d63c9d70baa7a6d53cd59c6f5ec291ac6d6cc9d7f6a3dcf5608e`;
- inferencias nuevas: 0.

También se añadió exclusión mutua de escritor a los checkpoints JSONL y pruebas
de concurrencia/recuperación. Los checkpoints históricos no se modificaron.

## Fase C H26–H37: preparación y bloqueo previo a VLM

El 30 de octubre de 2026 se aisló H26–H37 sin deserializar registros H38–H61. El
contenedor compartido reservado quedó sellado por SHA-256. Se adquirieron 24
activos de referencia/verificación (13 nuevos, 11 reutilizados), y posteriormente
105 vistas candidate-neutral Top-50 (56 nuevas, 49 reutilizadas). Las imágenes y
secuencias de referencia se excluyeron globalmente del plan VLM.

Las 12 anotaciones proporcionadas por `marcos` se importaron sin rankings ni
salidas VLM: 12 aprobadas y 194 claims aceptados. La fecha humana de revisión se
conserva `null` porque no fue proporcionada. El freeze técnico posterior tiene
SHA-256 `da6ffbd65297fe36812fcd4d9826c836124a5d6998ece2f29e2a7091fdb351ed`.

CrossText2Loc Top-100 `es_original` se congeló antes de abrir referencias:

- ranking ID `h26-h37-top100-sha256-36234fdb3ebc533207bfe89d8da4ad62dc4b1398ce7daac51276306c0f7642b5`;
- SHA-256 `f4afafec2e1820da0d6bb3ba4cb695de9be86802252eeeda4f2cf433f9f771c9`.

Techo de recuperabilidad sobre 12 consultas development:

| Profundidad | Oracle <50 m | Oracle <100 m | Distancia mínima media |
|---|---:|---:|---:|
| Top-50 | 6/12 | 10/12 | 60,77 m |
| Top-100 | 10/12 | 11/12 | 37,35 m |

Top-100 mejora claramente el techo, pero se conserva como variante de
recuperación separada. H33 no tiene candidato <100 m ni siquiera en Top-100.

El piloto Top-50 candidate-neutral contiene 105 assets y 582/600 slots cubiertos.
Su presupuesto provisional 2B es 8.151 tareas físicas, 7.073 llamadas reales y
1.078 abstenciones, unos 3.263 s según la latencia H16–H23. La auditoría IA de
494 pares referencia-candidato produjo 176 escenas diferentes, 318 ambiguas y
cero iguales bajo umbrales conservadores. Su SHA-256 es
`707abd1ffb022db15ce55686c1be4cd6469c26dc66561837720615f6cf07a868`.

El protocolo exige revisión humana de solapamiento. La auditoría IA no la
sustituye y deja `pilot_2b_unblocked=false`; por ello se ejecutaron cero
inferencias VLM, no se calibraron pesos, no se seleccionó política y no se abrió
H38–H61.

## Fase D H26–H37: Qwen3-VL-8B y calibración final

Una directriz posterior fijó Qwen3-VL-8B como único VLM del sistema. La campaña
2B de solapamiento se detuvo tras 276 frames y no se reutilizó. La auditoría
automática alternativa `automated_conservative_overlap_gate_v1` se declaró
explícitamente experimental y no equivalente a revisión humana.

La auditoría de solapamiento Top-50 combinó CLIP, histogramas RGB, dHash y una
comparación pareada Qwen3-VL-8B cerrada. Sobre 494 pares, el 8B clasificó 493
como escenas diferentes y uno como la misma escena. El consenso final retuvo 491
y excluyó tres: una misma escena y dos casos con elementos distintivos
coincidentes. La cobertura pasó de 582/600 a 579/600 slots.

El piloto Top-50 8B completó 8.103 tareas físicas:

- 7.034 inferencias reales;
- 1.069 abstenciones de orientación;
- 0 outputs inválidos;
- 2.413 `supported`, 332 `contradicted` y 5.358 `unverifiable`;
- 10.168,32 s y 18.523.566.080 B de pico RSS.

Antes de abrir referencias se congelaron baseline y ocho políticas, combinando
fórmula original/discriminativa con β `0,1/0,2/0,35/0,5`. La regla global
predefinida seleccionó `original_beta_0.1`: no perdió ninguna consulta, mejoró
Top-1 en H26 por 4,49 m y redujo la media de 382,76 m a 382,39 m. No ganó ningún
hit GeoRecall; la mejora media de 0,37 m es real pero pequeña y solo development.

La variante Top-100 se ejecutó separadamente por su mayor techo oracle. Tras
adquirir 29 imágenes adicionales y reutilizar 105, la auditoría automática
retuvo 931/934 pares. El plan físico tuvo 15.420 tareas: 5.479 reutilizadas del
Top-50, 8.600 inferencias nuevas y 1.341 abstenciones. La ejecución incremental
duró 12.485,37 s y alcanzó 18.554.589.184 B de pico RSS.

Top-100 seleccionó igualmente β=0,1 original y reprodujo exactamente las métricas
Top-50. Ningún candidato cuyo rank CT2L inicial fuera mayor que 50 entró en el
Top-10. Por igual rendimiento y coste superior, Top-100 se descarta como política
final, aunque permanece como ablación reproducible.

La política congelada es Top-50 `original_beta_0.1`, Qwen3-VL-8B, reserva
interna Top-50, salida Top-10 y fallback CT2L exacto. ID:
`h26-h37-selected-policy-sha256-7e533420de0f4629296b3f88e0edeeac483d2904dac52bac0c7066939ebae9b4`.
El bundle Atlas v3 contiene solo las 12 consultas exactas H26–H37; cualquier
consulta incompatible activa fallback. H38–H61 continúa sellado y no abierto.
## Linaje exploratorio posterior a Atlas v3

Se abrió un linaje development nuevo sin modificar la política Atlas v3
congelada. El diagnóstico Top-100 mostró que el candidato más próximo tiene rank
medio 50,3 y que el problema no es cobertura nominal, sino evidencia poco
discriminativa: 66,7 % de veredictos físicos son `unverifiable`, 44,6 % de vistas
son espacialmente ambiguas, solo existe una vista por candidato, todos los claims
pesan como distintivos y no hay OCR literal.

Una reponderación offline por rareza IDF, tipo semántico y contradicción no añadió
GeoRecall y reprodujo la mejora mínima de 0,37 m. Se descartó por criterio de
parada.

El piloto pairwise Qwen3-VL-8B comparó 355 pares lógicos mediante 294 llamadas
físicas. El contrato compacto registró 58 salidas válidas y 236 inválidas,
tratadas como `unverifiable` sin reparación JSON: 27 challengers, 2 incumbentes y
265 abstenciones. Ninguna política pairwise superó el baseline.

El prior OSM/F3 aislado con γ=0,35 redujo la distancia Top-1 media en 40,17 m y
mejoró dos consultas sin degradar Top-1, pero perdió un hit GeoRecall@10 a 50 m.
Una fusión visual-OSM correctamente escalada volvió a seleccionar γ=0,01 y
reprodujo exactamente la mejora visual histórica, sin ganancias adicionales.

La siguiente hipótesis propuesta es multivista + claims atómicos + OCR sobre
ranks 1–20. El plan content-neutral requiere hasta 103 descargas nuevas, 7.112
llamadas estructuradas 8B y unas 3,8 horas. Permanece no autorizado y no se ha
ejecutado. H38–H61 sigue sellado.
## H26-H37 exploratory-v4: reranking OSM/F3 estructurado

- **Estado:** completado sin sustitución de política.
- **Lineage:** `results/generated/mapillary/h26-h37-exploratory-v4/`.
- **Objetivo:** reordenar el Top-100 CrossText2Loc mediante nombres, categorías,
  rareza, topología y distancia F3, sin GT durante inferencia.
- **Recursos:** CPU local; sin GPU, red, descargas, APIs ni nuevas imágenes.
- **Resultado:** el ranking estructurado mejoró GeoRecall@10 de 3/12 a 6/12 a
  50 m y de 5/12 a 7/12 a 100 m, pero degradó dos Top-1. RRF degradó una
  consulta. La promoción Top-5 conservó Top-1 y añadió un hit @5 a 50 m, pero no
  justifica reemplazar Atlas v3.
- **Decisión:** conservar Atlas v3; siguiente experimento mínimo propuesto:
  promoción Top-5 con unicidad global, agrupación de evidencia correlacionada y
  dos familias independientes.
- **Informe:** [H26_H37_EXPLORATORY_V4_STRUCTURED_OSM.md](H26_H37_EXPLORATORY_V4_STRUCTURED_OSM.md).

## H26-H37 exploratory-v5: reranking fiable OSM/F3 y visual

- **Estado:** completado sin sustitución de política.
- **Lineage:** `results/generated/mapillary/h26-h37-exploratory-v5/`.
- **Objetivo:** explicar las degradaciones v4 y limitar promociones mediante
  unicidad global, independencia de objetos/familias, coherencia nominal, acuerdo
  CT2L y evidencia visual existente.
- **Recursos:** CPU local; sin GPU, red, descargas, imágenes o inferencia nueva.
- **Resultado:** Top-1 protegido añade un hit @5 a 50 m; Top-1 condicionado añade
  un hit @1 a 50 m; ninguna política v5 degrada Top-1 frente a Atlas. Todo el
  beneficio procede de H36 y se pierde la mejora @10 de v4.
- **Decisión:** conservar Atlas v3, no abrir evaluación independiente y detener
  nuevas iteraciones de reglas sobre las mismas doce consultas.
- **Informe:** [H26_H37_EXPLORATORY_V5_RELIABLE_RERANKING.md](H26_H37_EXPLORATORY_V5_RELIABLE_RERANKING.md).

## Auditoría post-v5 de complementariedad y validación independiente

- **Estado:** auditoría completada; experimentos bloqueados pendientes de
  autorización y datos elegibles.
- **Lineage:** `results/generated/post-v5-complementarity-audit/`.
- **Resultado:** F3 y F4 usan snapshots distintos; no puede atribuirse
  causalmente la señal F3 al formato estructurado. El inventario local contiene
  cero observaciones humanas confirmadas como independientes y elegibles.
- **Prioridad:** construir un conjunto `I01–I20` y ejecutar una validación
  one-shot de políticas congeladas. La ablación cartográfica alineada de 50 m es
  secundaria y requiere 1.012 renders y embeddings nuevos.
- **Recursos consumidos:** CPU de auditoría; sin red, GPU, renders, embeddings,
  descargas o inferencias.
- **Informe:** [POST_V5_COMPLEMENTARITY_AND_INDEPENDENT_VALIDATION.md](POST_V5_COMPLEMENTARITY_AND_INDEPENDENT_VALIDATION.md).

## Preparación I01–I20

- **Estado:** preparada técnicamente, sin recogida ni evaluación.
- **Lineage:** `results/generated/i01-i20-preparation-v1/`.
- **Freeze:** `i20-policy-freeze-sha256-d3d255310369a00d30669216a7d26bad46ca44ca3632946a10d3e26f009dc55b`.
- **Fuente recomendada:** campaña manual en Madrid con múltiples lecturas GNSS;
  Mapillary queda como fallback remoto separado.
- **Ledger:** frontera tri-state por lotes (`CLEAR/EXCLUDE/REVIEW`) operada por
  custodio independiente, sin razones, scores, distancias o IDs del holdout.
- **Transferibilidad:** CT2L es ejecutable; Atlas requiere evidencia visual
  I-específica y su fallback no cuenta como Atlas; v4/v5 son diagnósticos.
- **Ejecución:** 0 observaciones, 0 adquisiciones, 0 anotaciones, 0 modelos,
  0 GPU, 0 red y 0 evaluaciones.
- **Informe:** [I01_I20_INDEPENDENT_PREPARATION.md](I01_I20_INDEPENDENT_PREPARATION.md).

## Adquisición remota I01–I20

- **Estado:** 20 referencias adquiridas y técnicamente válidas; 0 elegibles.
- **Lineage:** `results/generated/i01-i20-remote-acquisition-v1/`.
- **Fuente:** Mapillary API v4, miniaturas 1.024 px, CC BY-SA 4.0.
- **Selección:** 60 IDs congelados, 20 slots, 12 bloques, dos reservas por slot,
  sin rankings, OSM, GT o píxeles durante selección.
- **Adquisición:** 60/60, 53 nuevas, 7 cacheadas, 7.704.672 bytes, 0 fallos.
- **Independencia accesible:** 3 assets exactos y 8 assets near-duplicate en el
  shortlist; reservas dejan 0 duplicados marcados entre las 20 referencias.
- **Bloqueos:** 20 `PENDING_BLIND_EXCLUSION`, 20 pendientes de anotación y
  revisión humana, 9 pares a menos de 75 m, 15 secuencias, GT de precisión
  desconocida.
- **Recursos:** red limitada autorizada; 0 GPU, modelos, embeddings o evaluación.
- **Informe:** [I01_I20_REMOTE_ACQUISITION.md](I01_I20_REMOTE_ACQUISITION.md).

## Interfaces humanas I01–I20

- **Estado:** interfaces listas; 0 outputs humanos y freeze bloqueado.
- **Lineage:** `results/generated/i01-i20-annotation-workflow-v1/`.
- **Interfaces:** anotación, auditoría de 12 pares de escena, revisores A/B y
  adjudicación, en carpetas físicamente separadas.
- **Privacidad:** archivos opacos, sin coordenadas, IDs de proveedor, OSM,
  rankings, GT o predicciones.
- **Gate:** escena, dos revisiones, adjudicación, ledger Ed25519 auténtico y
  geografía congelada son obligatorios; el navegador no puede marcar elegible.
- **Estado real:** `ready=false`, 0 anotaciones/revisiones/adjudicaciones.
- **Informe:** [I01_I20_ANNOTATION_WORKFLOW.md](I01_I20_ANNOTATION_WORKFLOW.md).

## I01–I20-assisted-annotation-v1

- **Estado:** workflow semiautomático preparado; 0 propuestas VLM reales.
- **Lineage:** `results/generated/i01-i20-assisted-annotation-v1/`.
- **Plan:** 12 comparaciones y 20 borradores, Qwen3-VL-8B local, JSON guiado,
  dos checkpoints reanudables.
- **Interfaces:** original IA read-only y versión humana editable; estado inicial
  `pending`; ausencia de cambios no equivale a aceptación.
- **Modelos:** 8B recomendado por calidad; 2B disponible para desarrollo; no hay
  otro VLM local completo y no se descargan modelos.
- **Trazabilidad:** propuestas y decisiones humanas en sidecars; contratos humanos
  originales no cambian.
- **Ejecución:** 0 GPU, modelos, VLM, red, descargas, CT2L o reranking.
- **Informe:** [I01_I20_ASSISTED_ANNOTATION.md](I01_I20_ASSISTED_ANNOTATION.md).

## Quality gate visual Mapillary

- **Estado:** implementación técnica completada; ejecución real bloqueada.
- **Lineage:** `results/generated/visual-quality-gate-v1/`.
- **Objetivo:** filtrar calidad técnica `ACCEPT/REVIEW/REJECT` antes de claims y
  sustituir mediante reservas metadata-only precongeladas.
- **Integración:** nueva implementación de `VisualPostprocessor`; CT2L y la
  fórmula de reranking permanecen inalterados.
- **Fixture:** 3 candidatos, 6 imágenes, 3 rechazos, 1 review, 2 accepts,
  2 sustituciones, 1 abstención; solo ACCEPT llegó a claims.
- **Ejecución real:** 0 imágenes, 0 red, 0 GPU, 0 modelos, 0 VLM, 0 claims,
  0 rerankings y 0 evaluación.
- **Autorización recomendada siguiente:** smoke de 5 candidatos, máximo 15
  llamadas 8B de calidad, sin claims ni reranking.
- **Informe:** [VISUAL_QUALITY_GATE_PIPELINE.md](VISUAL_QUALITY_GATE_PIPELINE.md).

## Preparación de validación multimodal posterior

- **Estado:** smoke 8B y diagnóstico preparados; GPU no autorizada.
- **Smoke:** 5 candidatos H11 de desarrollo, 15 assets locales, 1,95 MB,
  15 llamadas máximas, 0 red/claims/reranking/GT/evaluación.
- **Plan:** `visual-quality-reserve-plan-sha256-fd21be1e129012d135eb13416f4a7b0634ad421dc7499890bcaa41a89b958967`.
- **Quality gate:** runner real disponible offline, pero no conectado aún al
  backend HTTP por incompatibilidad de factory/contrato/timings.
- **I01–I20:** 20/20 referencias decodifican; 0 avisos CPU extremos; 0 elegibles
  y revisión humana todavía obligatoria.
- **Ejecución:** 0 GPU, red, modelos, VLM, descargas, claims, rerankings o
  evaluación.
- **Informe:** [NEXT_MULTIMODAL_VALIDATION_PLAN.md](NEXT_MULTIMODAL_VALIDATION_PLAN.md).
# Validación CPU del diálogo adaptativo v2

**Fecha:** 2026-11-04
**Tipo:** comprobación técnica con dobles CPU, sin modelos reales ni GT.

- Se implementó `interactive-dialogue-session-v2` con hasta tres preguntas.
- La selección de cada turno consume el ranking canónico posterior anterior.
- Las recuperaciones fake cubren siempre el universo completo.
- Se comprobaron desconocimiento, ambigüedad, negación, corrección, conflicto,
  finalización voluntaria, familias repetidas, fallos Qwen y 300 tokens.
- Qwen real, CT2L real y Qwen3-VL no se cargaron; no hubo acceso a GPU, red,
  fotografías, H26–H37 ni H38–H61.
- Comando focal: `python -m pytest tests/test_interactive_dialogue.py
  tests/test_interactive_dialogue_multiturn.py tests/test_crosstext2loc_runtime.py
  tests/test_phase5_text_transform.py`.
- El resultado describe integridad de software, no precisión geográfica.

## Smoke real del diálogo adaptativo v2

**Fecha:** 2026-11-04
**Tipo:** integración técnica real, sin GT, VLM, red, descargas o reintentos.

### Protocolo congelado

- Descripción técnica: «Estoy en una calle urbana con varios edificios y
  comercios».
- Respuestas ordinales prefijadas: `Sí`, `No`, `No puedo comprobarlo`.
- Configuración: `interactive_dialogue_multiturn.json`, máximo tres preguntas.
- Galería exhaustiva `madrid-50m`, 253 candidatos; F3 físico compatible.
- Una carga compartida CT2L y una carga compartida Qwen3-8B.
- Qwen3-VL-8B no se cargó.

El preflight encontró una NVIDIA GB10 sin procesos compute. Ollama estaba activo
como servicio, pero no existía `llama-server` ni modelo residente. La RAM
disponible era 101.467.189.248 B; NVML no expuso memoria total/libre de la memoria
unificada. Se ejecutó un único intento en `crosstext2loc-gb10:f511`, imagen
`sha256:0775ff6757f13f28c9950eff2d2ee6a2bf9f8f6bb465e2946453dce8f1caff72`.

### Resultado

- Estado: `PASS`; tres preguntas; parada `max_questions_reached`.
- Familias adaptativas: `monument`, `church`, `square`, sin repetición.
- Recuperaciones CT2L: tres, todas exhaustivas con 253 candidatos. La respuesta
  desconocida del tercer turno no produjo recuperación.
- Los hashes prueban que el ranking posterior del turno 1 alimentó el turno 2 y
  el posterior del turno 2 alimentó el turno 3.
- Llamadas Qwen: tres redacciones y dos reescrituras; cero llamadas VLM.
- Las tres redacciones fallaron cerradas: `intent_changed` una vez y
  `missing_abstention_option` dos veces. Se mostraron plantillas deterministas.
- Reescrituras: primera rechazada por `clarification_lost`; segunda aceptada,
  pero ninguna alimentó la política adaptativa.
- Tokenizer CT2L real verificado post hoc sobre las consultas exactas: 25, 51 y
  75 tokens. No hubo omisiones ni truncamiento. El registro de sesión conserva el
  conteo fallback 14/27/43 debido a una limitación de instrumentación corregida
  después del único intento; la sesión no se reescribió.
- Carga CT2L: 5.743 ms; F3: 266 ms; Qwen: 91.551 ms; sesión: 11.026 ms; total:
  108.643 ms.
- CUDA tras CT2L: 1.712.462.336 B asignados; tras Qwen: 18.093.952.512 B;
  pico propio: 18.140.423.680 B asignados y 18.196.987.904 B reservados.
- Tras cerrar, CUDA asignada bajó a 9.568.256 B; el allocator seguía informando
  16.324.231.168 B reservados dentro del proceso justo antes de terminar el
  contenedor. Fuera del contenedor no quedaron procesos compute.
- Schema v2, validador Python, eventos, hashes, rankings, consultas, ausencia de
  GT y VLM: `PASS`.

Los rankings cambiaron técnicamente, incluido Top-1, pero no se evaluó ni se
afirma mejora geográfica. Los artefactos locales están en
`results/generated/interactive-dialogue-multiturn-real-smoke-v1/` y permanecen
fuera de Git conforme a la política de resultados generados.

## Caracterización aislada Qwen3-VL-8B: intento v1

**Fecha:** 2026-11-04
**Estado:** `PARTIAL_PERSISTENCE_FAILURE_NO_RETRY`

Se fijó antes de cargar el modelo una imagen sintética RGB de 384×384, generada
localmente con Pillow, con un rectángulo rojo, un círculo azul, un triángulo verde
y el texto «FORMAS Y COLORES». El prompt fue: «Describe brevemente los elementos
visuales que aparecen en la imagen. No inventes información que no puedas
observar». La configuración fue BF16, SDPA, `do_sample=false` y máximo 64 tokens.

El snapshot local `Qwen/Qwen3-VL-8B-Instruct`, revisión
`0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`, coincidió con los cuatro hashes
documentados. El preflight encontró una GB10 sin procesos compute y Ollama sin
modelo residente. Se ejecutó un único intento aislado, sin CT2L, Qwen textual,
DialogueVPR, red, GT o conjuntos reservados.

La salida de consola acredita que la carga alcanzó 750/750 tensores. El proceso
falló al serializar el informe final porque `processor.image_processor.size` era
un `SizeDict` de Transformers y no un tipo JSON nativo. El fallo ocurrió en el
`finally`; por ello no es científicamente seguro recuperar de memoria la salida
ni afirmar qué etapas posteriores a la carga concluyeron. M0–M3, latencias y
salida se clasifican `NOT VERIFIED`. Tras terminar el contenedor no quedaron
procesos compute propios; la RAM disponible observada fue 100.033.617.920 B y el
swap usado 15.104.573.440 B.

No se realizó un segundo intento, no se cambió precisión, imagen, modelo ni
configuración. Se corrigió únicamente la serialización de objetos de configuración
Transformers y se añadieron tests CPU. Los artefactos persistidos locales son:

- `protocol.json`, SHA-256
  `0b01e96f978be06ca3330d3d177148e08969e2f40b912ee8d87b38062f4025fc`;
- `synthetic-visual-fixture.png`, SHA-256
  `b9468994d5ce0a1ae6a6c7ecd37430926064d6088dfc123b2e2388fb22a033fb`.

La medición histórica de 17,83 GB de pico CUDA asignado en otro smoke 8B se
mantiene como antecedente y no se presenta como medición nueva. Este intento no
permite decidir coexistencia triple.

## Caracterización aislada Qwen3-VL-8B: repetición v2

**Fecha:** 2026-11-04
**Estado:** `VLM_ISOLATED_SMOKE_PASS`

Se reutilizaron byte a byte la imagen sintética v1, SHA-256
`b9468994d5ce0a1ae6a6c7ecd37430926064d6088dfc123b2e2388fb22a033fb`,
el prompt, BF16, SDPA, `do_sample=false` y el límite de 64 tokens. Antes de cargar
pesos se validaron en CPU `SizeDict`, NumPy, escalares/vectores PyTorch, tuplas,
listas, diccionarios y opcionales mediante escritura atómica y relectura.

El preflight encontró cero procesos compute, Ollama sin `llama-server`,
98.061.754.368 B de RAM disponible y 15.104.557.056 B de swap usada. NVML no
expuso memoria total/libre en la GB10. No se ejecutaron CT2L, Qwen textual,
DialogueVPR, red, GT ni conjuntos reservados.

### Inferencia y recursos

- Salida real: descripción de tres formas geométricas, fondo blanco y título
  «FORMAS Y COLORES»; terminó truncada al alcanzar exactamente 64 tokens.
- Entrada: 180 tokens totales, 144 tokens visuales, grid `[1, 24, 24]` y tensor
  visual `[576, 1536]`.
- M0 CUDA: 0 B asignados/reservados.
- M1 tras carga: 17.534.319.104 B asignados y 17.536.385.024 B reservados.
- M2 tras preprocessing: 17.537.863.168 B asignados y 17.557.356.544 B
  reservados.
- M3: 17.547.433.984 B asignados; pico 17.601.585.664 B asignados y
  17.632.854.016 B reservados.
- M4 tras eliminar referencias y vaciar caché: 9.568.768 B asignados y
  16.777.216 B reservados. Tras terminar el contenedor, el host observó cero
  procesos compute.
- Pico RSS: 18.498.625.536 B.

Latencias monotónicas con sincronización CUDA: processor 250 ms; carga y
transferencia 93.999 ms; preprocessing 24,8 ms; generación 6.651 ms;
decodificación 0,17 ms; liberación 308 ms; runtime total 101.757 ms. No incluyen
la inicialización externa del contenedor.

Los checkpoints `m0.json`–`m4.json`, salida, métricas y manifiesto se escribieron
atómicamente y se releyeron antes de avanzar. El manifiesto validó hashes y
tamaños de todos los artefactos. Los resultados locales están en
`results/generated/qwen3-vl-8b-memory-smoke-v2/`, fuera de Git.

La suma orientativa del pico histórico CT2L + Qwen textual (18.140.423.680 B) y
el pico aislado VLM (17.601.585.664 B) es 35.742.009.344 B y se etiqueta
`ESTIMATE_NOT_VALIDATED`: no mide coexistencia, activaciones simultáneas,
fragmentación ni presión de memoria unificada. La siguiente fase puede preparar
una prueba específica de coexistencia, pero todavía no autoriza residencia triple.

## Coexistencia real CT2L + Qwen3-8B + Qwen3-VL-8B

**Fecha:** 2026-11-04
**Estado:** `TRIPLE_COEXISTENCE_PASS`

Se cargaron en un único proceso, sin cuantización u *offloading*, CT2L float32,
Qwen3-8B BF16 y Qwen3-VL-8B BF16/SDPA. El preflight registró cero procesos
compute ajenos, Ollama sin `llama-server`, 98.512.576.512 B de RAM disponible y
15.104.536.576 B de swap usada. NVML no expuso memoria total/libre de la GB10.

Un gate fijado antes del experimento exigió al menos 40 GiB de RAM disponible,
crecimiento de swap no superior a 1 GiB entre C0 y C2 y ausencia de procesos
compute ajenos. Pasó con 78.368.870.400 B disponibles y crecimiento de swap 0 B.

### Carga conjunta

| Etapa | CUDA asignada | CUDA reservada | RAM disponible | Swap usada | Carga |
|---|---:|---:|---:|---:|---:|
| C0 | 0 B | 0 B | 97.673.990.144 B | 15.104.532.480 B | — |
| C1 CT2L | 1.712.462.336 B | 1.772.093.440 B | 94.444.007.424 B | 15.104.532.480 B | 5.069 ms |
| C2 + Qwen texto | 18.093.952.512 B | 18.161.336.320 B | 78.368.870.400 B | 15.104.528.384 B | 84.259 ms |
| C3 + Qwen VL | 35.629.484.032 B | 35.689.332.736 B | 63.599.046.656 B | 17.179.426.816 B | 94.992 ms |

Los tres objetos de modelo seguían referenciados en C3. La carga VLM produjo
presión PSI baja pero observable (`avg10=0,05`) y ocupó prácticamente toda la
swap disponible. No hubo OOM.

### Inferencias secuenciales

- CT2L: ranking exhaustivo de 253 candidatos en 291 ms.
- Qwen3-8B: 26 tokens de entrada y 24 de salida en 2.745 ms; salida truncada por
  el límite técnico fijado.
- Qwen3-VL-8B: misma imagen sintética y prompt del smoke aislado, 180 tokens de
  entrada y 64 de salida en 6.653 ms; salida idéntica y truncada al límite.
- Pico conjunto observado durante VLM: 35.707.285.504 B CUDA asignados y
  35.758.538.752 B reservados.

Tras liberar VLM, Qwen textual y CT2L en ese orden, quedaron 9.568.256 B CUDA
asignados y 23.068.672 B reservados dentro del proceso. Tras terminar el
contenedor, el host confirmó cero procesos compute y 101.333.602.304 B de RAM
disponible. La swap permaneció casi llena; este hecho puede reflejar páginas
inactivas persistentes y no se interpreta como memoria CUDA asignada.

Los 14 artefactos del manifiesto pasaron hashes y tamaños. Los resultados están
en `results/generated/triple-model-coexistence-smoke-v1/`, fuera de Git. La
coexistencia técnica queda demostrada para una única secuencia mínima, pero la
swap agotada y la presión de memoria desaconsejan residencia triple como política
operativa inicial. Se recomienda mantener CT2L + Qwen textual residentes y cargar
el VLM bajo demanda con reserva exclusiva de recursos, hasta evaluar sesiones
prolongadas y concurrencia en un protocolo separado.

## Integración CPU-first de evidencia visual en DialogueVPR

**Fecha:** 2026-11-04
**Estado:** `VISUAL_INTEGRATION_CPU_PASS`

Se añadió el contrato `dialogue-visual-evidence-v1` y la sesión aditiva
`interactive-dialogue-session-v3`. La configuración v2 continúa desactivando VLM
por defecto. El orquestador v3 consulta como máximo una imagen para una intención
ya seleccionada por CT2L/F3, verifica autorización, procedencia, SHA-256 y relación
`observer_view`, y registra `supported`, `contradicted` o `unverifiable`.

Las evidencias visuales permanecen separadas de claims humanos y asociaciones
F3. No se incorporan a `literal_concatenation`, no ejecutan retrieval, no alteran
scores/rankings y no eliminan candidatos. Los conflictos humano–VLM conservan
ambas fuentes y declaran `query_changed=false` y `ranking_changed=false`.

La ruta real Qwen3-VL solo prepara identidad, prompt, schema, imagen y presupuesto
de una futura petición. No carga modelos ni ejecuta callables en proceso; sin
runtime aislado se abstiene. La salida futura exige evidencia observada explícita,
límites y vocabulario acotados; la mera ausencia nunca produce contradicción.

La validación CPU cubrió proveedor desactivado, estados, autorización, fichero,
hash, procedencia, relación observador, salida inválida, timeout/excepción fake,
conflictos, manipulación de claim/productor, eventos, schemas, hashes,
compatibilidad v1/v2, máximo de tres preguntas, retrieval exhaustivo e
invariancia de consulta/ranking. El smoke CLI v3 con manifiesto local autorizado
produjo una evidencia, un conflicto trazable y no importó `torch`.

La integración valida software y seguridad fail-closed, no calidad visual,
Recall@K o precisión geográfica. No se cargó ningún modelo ni GPU y no se accedió
a conjuntos reservados.

## Primer intento de worker real y sesión visual v3

**Fecha:** 2026-11-04
**Estado:** `BLOCKED_BY_GPU` y `BLOCKED_BY_IMAGE_ELIGIBILITY`

Se implementó un worker Qwen3-VL aislado con petición cerrada, allowlist de mount,
doble comprobación SHA-256, BF16/SDPA, JSON guiado, una sola inferencia, alarmas de
carga/inferencia y supervisor con timeout total efectivo sobre un grupo de
proceso propio. Las pruebas CPU cubrieron schema, permisos, hashes, traversal,
request ID, timeout, terminación y error CUDA simulado. El supervisor
`--validate-only` completó correctamente sin importar modelos.

El gate prefijado exigía cero procesos compute ajenos, al menos 40 GiB de RAM y
PSI `some/full avg10 < 0,10`. El preflight encontró un `llama-server` de Ollama
ajeno, PID 3.640.702, con 18.523 MiB, y 17.172.344.832 B de swap usada de
17.179.865.088 B. Aunque había 81.874.685.952 B de RAM disponible y PSI actual
era cero, la competencia GPU/material de memoria bloqueó el worker. No se detuvo
Ollama, no se cargó ningún modelo y no hubo reintento.

Además, el único fixture autorizado disponible para este smoke es sintético y se
clasifica `synthetic_transport_only`: no es una fotografía desde el observador y
no puede declararse `observer_view`. No se buscaron imágenes en conjuntos
reservados ni se relajó el schema. Por ello no se creó una sesión v3 real. Los
diagnósticos locales están en
`results/generated/dialogue-v3-real-visual-smoke-v1/`, fuera de Git.

## Desbloqueo del worker visual: segundo preflight

**Fecha:** 2026-11-04
**Estado:** `BLOCKED_BY_GPU`

El worker y supervisor se ampliaron con allowlist de mount, doble hash, petición
content-addressed, alarmas separadas de carga/inferencia y timeout total efectivo
que termina únicamente el grupo de proceso propio. La validación CPU y el modo
`--validate-only` pasaron. Se añadió una plantilla de fotografía `observer_view`
que permanece explícitamente incompleta y no autorizada.

Los umbrales se fijaron antes del preflight: cero procesos compute ajenos, al
menos 40 GiB de RAM, swap usada como máximo al 95 % y PSI `some/full avg10 <
0,10`. El host tenía 81.746.046.976 B de RAM disponible y PSI cero, pero mantenía
el `llama-server` de Ollama PID 3.640.702 con 18.523 MiB y 17.172.221.952 B de
swap usada de 17.179.865.088 B. El supervisor devolvió
`foreign_compute_process_present` y `swap_fraction_above_limit` antes de crear el
worker. No hubo carga, inferencia, reintento, modificación de procesos ajenos ni
sesión v3.

El fixture sintético conservó el rol `synthetic_transport_only`; no se falsificó
`observer_view`. El diagnóstico local está en
`results/generated/qwen3-vl-dialogue-worker-real-smoke-v1/`, fuera de Git.
## Revalidación del desbloqueo del worker visual

**Fecha:** 2026-11-04
**Estado:** `BLOCKED_BY_GPU`

La infraestructura del worker se completó con schema de petición cerrado,
request ID content-addressed, allowlist `/authorized-images/<nombre>`, doble
verificación SHA-256, ejecución Docker sin red, alarmas de carga/inferencia y
timeout total efectivo del supervisor. Los tests CPU y `--validate-only`
finalizaron correctamente.

El preflight fijó antes de observar recursos: cero procesos compute ajenos, RAM
disponible ≥40 GiB, swap usada ≤95 % y PSI `some/full avg10 <0,10`. Se observaron
62.946.177.024 B de RAM disponible y PSI cero, pero Ollama mantenía el
`llama-server` PID 3.640.702 con 36.267 MiB y la swap estaba usada al 99,96 %
(17.172.221.952 de 17.179.865.088 B). El supervisor persistió
`foreign_compute_process_present` y `swap_fraction_above_limit`, no creó el
worker y realizó cero inferencias o reintentos.

La imagen sintética conservó `synthetic_transport_only`; no existe aún una
imagen real autorizada con relación `observer_view`. La plantilla
`dialogue_observer_image_manifest.template.json` permanece incompleta y no
autorizada, sin inventar fuente, autor, licencia, perspectiva, sesión o intención.

## Reanudación del worker visual pendiente

**Fecha:** 2026-11-04
**Estado:** `BLOCKED_BY_MEMORY_POLICY`

Se reanudó únicamente desde el preflight. `ollama ps` estaba vacío, `nvidia-smi`
no mostraba procesos compute y no existía `llama-server`. Había
105.100.926.976 B de RAM disponible y PSI `some/full avg10=0`, pero la swap seguía
usada al 99,97 %: 17.175.097.344 de 17.179.865.088 B. El gate fijo del 95 %
bloqueó antes de crear el worker.

El supervisor persistió petición, preflight y reporte en
`results/generated/qwen3-vl-dialogue-worker-real-smoke-v2/`. No cargó pesos, no
ejecutó inferencia, no creó procesos propios y no reintentó. La clasificación se
ajustó a `BLOCKED_BY_MEMORY_POLICY`, ya que la GPU estaba libre y el único fallo
era el umbral de swap. El gate no se modificó.

La plantilla `config/dialogue_observer_image_manifest.template.json` permanece
`template_incomplete`, `authorized=false` y sin datos inventados; la preparación
de una fotografía real `observer_view` continúa pendiente e independiente.
