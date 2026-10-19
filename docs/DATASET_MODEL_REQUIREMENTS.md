# Requisitos de datos de CrossText2Loc y GOTPR

## Arquitectura auditada del catálogo

La arquitectura vigente separa una preparación offline de una inferencia
online. La preselección utiliza la consulta estructurada, la zona y datos
vectoriales OSM/Overpass —con Wikidata/Wikipedia solo si se habilita—; no usa
imágenes OSM, imágenes satelitales ni sus embeddings. Los candidatos
descartados no se borran: quedan fuera de esa consulta mediante sus
`candidate_id`.

CrossText2Loc y GOTPR son alternativas de recuperación. CrossText2Loc compara
texto con representaciones visuales; GOTPR compara un Text Scene Graph con OSM
Scene Graphs. Esta última ruta requiere un adaptador de construcción del grafo
textual y un generador OSM compatible que no están completos en el repositorio
oficial de GOTPR.

## Auditoría de viabilidad por componente

| Componente | Viabilidad | Evidencia | Qué falta | Riesgo |
| --- | --- | --- | --- | --- |
| LLM como intérprete geográfico | VIABLE CON ADAPTACIÓN | D017, D026 y `schemas/llm_geo_query.schema.json` | Proveedor e implementación del adaptador | El LLM puede introducir restricciones no justificadas |
| OpenStreetMap | CONFIRMADO | Snapshot raw D004 y bundles geométricos F3 validados: `osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141` | Preparar en F4 representaciones visuales sin modificar raw ni bundles F3 | Etiquetas incompletas o inconsistentes |
| Overpass API | CONFIRMADO | Cliente, caché, validación y adquisición real HTTP 200 en un intento | Revisar política y disponibilidad antes de cada nueva adquisición | Límites de carga o cobertura |
| Catálogo geográfico de Madrid | CONFIRMADO | F1, F3 y [`PHASE3_CLOSURE.md`](PHASE3_CLOSURE.md) | Elegir experimentalmente 25 m o 50 m mediante D003 | El catálogo puede no cubrir el lugar correcto |
| Generación de imágenes OSM | VIABLE CON ADAPTACIÓN | `external/CVG-Text/download_osm_street.py:17-74` | Wrapper corregido y validación del recorte/área | Incompatibilidad de escala o formato |
| Embeddings visuales | VIABLE CON ADAPTACIÓN | `external/CVG-Text/model_loader.py:27-215`; `evaluate.py:24-54` | Checkpoint fijado e índice persistente | Licencia o pesos no confirmados |
| Imágenes satelitales | EXPERIMENTAL | `external/CVG-Text/config.yaml:11-20`; `zeroshot.py:36-40` | Fuente con permisos de almacenamiento y embeddings | Restricciones del proveedor |
| CrossText2Loc para Madrid | VIABLE CON ADAPTACIÓN | `dataset.py`, `model_loader.py`, `evaluate.py` del commit auditado | Manifiesto, índice y adaptación a `candidate_id` | Transferencia no demostrada a Madrid |
| GOTPR sobre datos oficiales | CONFIRMADO | `scene_graph.py`, `models.py`, `eval_utils.py` | Entorno y artefactos oficiales | Dependencias y formatos serializados |
| GOTPR para una ciudad nueva | EXPERIMENTAL | `scene_graph.py:46-117`; `scene_graph_candidates_extraction.py:8-76` | Constructor OSM→Scene Graph, reglas espaciales y embeddings | El checkpoint puede no ser compatible |
| Indexación GOTPR/Milvus | CONFIRMADO | `scene_graph_candidates_extraction.py:8-36` | Escoger Milvus o comparación completa | Coste y dependencia de CUDA |
| Street View | BLOQUEADO/PENDIENTE | APIs y términos de Google Maps Platform | Confirmar descarga, procesamiento, caché y publicación | Restricciones contractuales |
| VLM | PENDIENTE | No hay proveedor fijado en el proyecto | Modelo, contrato, coste y retención | Privacidad y coste |
| DialogueVPR | EXPERIMENTAL | Referencia científica en `BASELINE.md` | Política de preguntas propia | No es necesario para el MVP |
| TOLoc | EXPERIMENTAL | Referencia científica en `BASELINE.md` | Compatibilidad, datos y licencia | Ampliación fuera del alcance inicial |
| Recall@K y Haversine | CONFIRMADO | `external/CVG-Text/evaluate.py:11-17,271-342`; `external/GOTPR/eval_utils.py:28-93`; D030–D031 | Umbrales y métrica principal pendientes de experimento | Las métricas oficiales no son idénticas |

## Estado de la auditoría

La auditoría inicial se realizó sobre código local clonado, sin descargar
datasets, imágenes masivas ni checkpoints. Posteriormente se completó una
reproducción separada de NewYork-mixed OSM con los artefactos oficiales; véase
[`CROSSTEXT2LOC.md`](CROSSTEXT2LOC.md#resultado-de-la-reproducción-oficial). Esa reproducción
no resuelve la generación de una galería compatible ni la transferencia a
Madrid.

La Fase 2 adquirió el primer snapshot vectorial OSM de D004 el
`2026-10-06T08:52:43.930134Z`, con 8.420.815 bytes y SHA-256
`f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141`.
Contiene 23.019 nodes seleccionados por bbox y 2.518 nodes adicionales para
completar 4.240 ways, además de 498 relations contextuales. Sus members no
resueltos son consecuencia prevista de no expandir relations, no un fallo de
integridad; todos los `nd ref` de ways sí están resueltos. Véase
[`PHASE2_OSM_SNAPSHOT.md`](PHASE2_OSM_SNAPSHOT.md).

La política geométrica D049 fija `way_is_area-v1` junto con una copia exacta y
versionada de `osm-polygon-features` v0.9.2. F3 la aplicó al snapshot real y
materializó asociaciones `candidate_id`–OSM para 25 m y 50 m. El cierre se
documenta en [`PHASE3_CLOSURE.md`](PHASE3_CLOSURE.md).

D050 acepta el contrato global del dataset derivado F3. Sus inputs, outputs,
identidad, predicados, serialización, provenance y publicación se detallan en
[`PHASE3_GEOMETRIC_ASSOCIATIONS.md`](PHASE3_GEOMETRIC_ASSOCIATIONS.md). El
entorno efectivo quedó fijado en NumPy 2.5.4, Shapely 2.1.2 y GEOS 3.13.1.

| Repositorio | URL | Commit auditado |
| --- | --- | --- |
| CVG-Text / CrossText2Loc | <https://github.com/yejy53/CVG-Text> | `6910d2747a94fbe985309bde60cd4732bcbbf50f` |
| GOTPR | <https://github.com/donghwijung/GOTPR> | `4d6d12582ec51228d0a78438deaa4b1e2b349e52` |

Como referencias auxiliares declaradas por GOTPR también se clonaron
`whereami-text2sgm` y `Text2Pos-CVPR2022`. No se utilizaron sus datos ni sus
checkpoints. El entorno local no tiene instalados `numpy` ni `Pillow`, por lo
que las fixtures de ejecución quedaron bloqueadas; las conclusiones de esta
versión proceden de la inspección del código.

## 1. CrossText2Loc / CVG-Text

### Dataset y asociación con coordenadas

`external/CVG-Text/dataset.py:7-39` define `OSMTextImageDataset`. Cada JSON se
carga como un diccionario cuyos pares son:

```json
{
  "nombre_de_imagen.jpg": "descripción textual"
}
```

El loader concatena el directorio de imágenes con la clave del JSON
(`dataset.py:33-39`). En el flujo activo no existe un campo independiente para
`candidate_id`, latitud, longitud o polígono.

`external/CVG-Text/evaluate.py:18-22` extrae la latitud y longitud del inicio
del nombre del archivo con el patrón:

```text
<latitude>,<longitude>_...
```

Para Madrid se debe conservar, además del formato compatible del modelo, un
manifiesto propio que relacione de forma estable `candidate_id`, `latitude`,
`longitude`, imagen y metadatos de generación.

### Imágenes OSM

`external/CVG-Text/download_osm_street.py:17-23` define:

```text
pixel_size = 0.2627
img_size = 256
final_size = 512
dis = pixel_size * img_size / 2
```

`download_osm_street.py:57-65` solicita teselas de
`https://tile.openstreetmap.org/{z}/{x}/{y}.png` con `zoom=18`, usando una
ventana en EPSG:3857 alrededor del punto central.

`download_osm_street.py:67-73` convierte la imagen a RGB, calcula un recorte
central de `256 × 256` y lo redimensiona a `512 × 512`. Sin embargo, la línea
74 guarda `img`, no `img_crop`:

```python
img.save(out_file_path)
```

Por tanto, el script publicado no guarda actualmente el recorte redimensionado
que calcula. La salida efectiva depende del tamaño que devuelva `contextily` y
no debe describirse como `512 × 512` sin corregir o verificar ese script.

La corrección mínima técnicamente evidente sería guardar `img_crop`, pero no se
ha aplicado en el repositorio oficial ni se ha validado contra un checkpoint.
Antes de usarla hay que comprobar una imagen real del dataset oficial o ejecutar
el procedimiento con una muestra pequeña.

**TODO / NEEDS VERIFICATION:** el área geográfica efectiva de una imagen. El
código define una ventana matemática en Web Mercator, pero no documenta aquí su
extensión final en metros ni una geometría de cobertura por candidato.

### Preprocesamiento y modelos

`external/CVG-Text/model_loader.py:21-25` declara los modelos soportados y
`model_loader.py:27-105` selecciona el modelo y sus pesos base.

Para CLIP, `model_loader.py:110-123` utiliza el `preprocess` del modelo y
tokeniza el texto con CLIP. Con `expand_text=True`, modifica la longitud
posicional hasta `MAX_TEXT_LEN = 300` (`model_loader.py:21` y `110-119`).

Para OSM no se activa el ajuste panorámico reservado a `is_stv`; ese camino se
usa en `model_loader.py:121-125` y `150-157` para Street View. La configuración
de rutas está en `config.yaml:11-25`, con directorios separados para OSM,
Street View, satélite, fotos, anotaciones y resultados.

El README oficial muestra como ejemplo:

```text
python zeroshot.py --version NewYork-mixed --img_type sat \
  --model CLIP-L/14@336 --expand
```

(`external/CVG-Text/README.md:72-78`). El checkpoint concreto de Madrid aún no
está seleccionado.

### Embeddings y retrieval

`external/CVG-Text/evaluate.py:26-54` calcula `encode_image` y `encode_text`,
concatena los vectores, los normaliza y calcula la similitud mediante producto
matricial (`evaluate.py:51-54`).

El evaluator oficial trabaja con una matriz de textos frente a imágenes del
dataset. No proporciona un índice persistente de una ciudad nueva.

El adapter de Madrid puede reutilizar el loader y el preprocesador oficiales y
debe realizar offline:

1. cargar el modelo y checkpoint seleccionado;
2. procesar cada imagen OSM de referencia;
3. ejecutar `model.encode_image` sin gradientes;
4. normalizar y guardar el vector junto con `candidate_id` y coordenadas;
5. cargar esos vectores en inferencia;
6. procesar la descripción con el mismo tokenizer;
7. ejecutar `model.encode_text`, normalizar y comparar por producto escalar.

Este paso es una adaptación de indexación; no cambia los pesos.

### Métricas oficiales observadas

`evaluate.py:271-272` implementa la pertenencia del índice correcto a los
primeros `K`. En el evaluator CLIP se calculan R@1, R@5 y R@10
(`evaluate.py:315-322`). También se calcula Haversine y distancia Top-1 en
`evaluate.py:283-304`.

El bloque de evaluación usa umbrales de 50, 100 y 150 metros
(`evaluate.py:306-332`). Estos umbrales y el protocolo de vecino correcto son
los del código observado, no deben sustituirse silenciosamente por 25, 50,
100 o 500 metros. Los umbrales adicionales del TFG deberán marcarse como
métricas propias.

## 2. GOTPR

### Datos publicados y límites de reproducibilidad

El README oficial (`external/GOTPR/README.md:29-32`) indica que los scene
graphs y checkpoints descargables se generaron con coordenadas GPS derivadas
de ENU del dataset KITTI360Pose. El repositorio no contiene el generador
Overpass/OSM→scene graph para una ciudad nueva.

También declara como bases `whereami-text2sgm`, Milvus y Text2Pos
(`GOTPR/README.md:61`). La auditoría de `whereami-text2sgm` encontró cargadores
de grafos ya preparados, no un conversor de OSM para Madrid.

### Estructura interna de una scene

`external/GOTPR/scene_graph.py:18-44` define `Node`, `Edge` y la estructura
`SceneGraph`. Un grafo contiene, al menos:

```text
scene_id
nodes
edge_idx
edge_relations
edge_features
```

Cada nodo contiene índice, características de etiqueta, características de
atributos, etiqueta y atributos (`scene_graph.py:18-35`). Puede incluir
`centroid` en ciertos grafos (`scene_graph.py:78-89`).

Para grafos `human` o `scanscribe`, el constructor espera en cada nodo:

```text
id
label
attributes
label_<embedding_type>
attributes_<embedding_type>
```

y en cada arista:

```text
source
target
relationship
relation_<embedding_type>
```

Esto se observa en `scene_graph.py:54-59`, `78-90` y `109-117`.

El repositorio acepta también `3dssg`, pero ese formato usa objetos y listas de
aristas distintas (`scene_graph.py:46-53` y `67-76`). No se debe elegir uno
para Madrid sin determinar qué formato corresponde al checkpoint descargado.

### Embeddings de 300 dimensiones

`external/GOTPR/config.py:12` fija `word2vec_dim = 300`. El modelo define
características de entrada de nodos y aristas de 300 dimensiones en
`external/GOTPR/models.py:17-25`.

La referencia auxiliar `whereami-text2sgm` aporta información sobre el origen
de parte de esas características:

- `external/whereami-text2sgm/playground/graph_models/data_processing/graph_loader_utils.py:94-108`
  usa `create_embedding` para Ada y `nlp(desc)[0].vector` para spaCy/word2vec;
- `graph_loader_utils.py:101-108` devuelve un vector de 300 dimensiones para
  cada descripción con `en_core_web_lg`;
- `graph_loader_human.py:27-53` genera `relation_ada`,
  `relation_word2vec`, `label_ada`, `label_word2vec` y embeddings de atributos;
- `create_text_embeddings.py:68-73` comprueba explícitamente que el vector
  spaCy tenga longitud 300.

No obstante, GOTPR usa por defecto `embedding_type='ada'` en
`GOTPR/scene_graph.py:47`; el origen y checkpoint exactos de los vectores Ada
del paquete distribuido no están incluidos como un pipeline reproducible para
OSM.

### Relaciones y espacialidad

Para `scanscribe`/`human`, GOTPR conserva literalmente la relación de cada
arista y su embedding (`scene_graph.py:109-117`). No genera relaciones a partir
de coordenadas OSM.

Para `3dssg`, filtra las aristas por `distance <= max_dist`
(`scene_graph.py:92-107`), pero el repositorio no define un `max_dist` ni una
conversión geográfica para escenas OSM de Madrid.

La visualización usa el `centroid` del nodo como posición (`visualize_scene_retrieval_results.py:16-50`). Esto permite visualizar grafos que ya
contienen centroides; no especifica cómo calcular el centro o los límites de
una scene nueva.

**TODO / NEEDS VERIFICATION:** tamaño espacial de una scene, regla de teselado,
unidad de coordenadas, cobertura y asociación oficial scene→lat/lon.

### Candidate extraction y reranking

`external/GOTPR/scene_graph_candidates_extraction.py:8-36`:

1. convierte cada scene graph a PyG;
2. aplica `model.TSALayers[0]`;
3. calcula la media de los embeddings de nodos;
4. crea una colección Milvus de dimensión inferida;
5. inserta cada vector con un entero como ID.

`scene_graph_candidates_extraction.py:38-76` procesa el grafo textual del
mismo modo, busca con métrica COSINE y después reordena los candidatos con el
modelo GOTPR completo.

El mapeo de Milvus se basa en el orden de `list(cell_graphs.keys())`
(`scene_graph_candidates_extraction.py:13`, `58-63`), por lo que Madrid deberá
guardar explícitamente ese orden y su correspondencia con `scene_id` y
coordenadas.

`external/GOTPR/eval_utils.py:28-93` confirma el flujo completo. Si
`config.use_candidates_extraction` es falso, compara con todas las escenas; el
README (`GOTPR/README.md:19-22`, `39-42`) documenta esa alternativa.

La evaluación oficial usa `top_ks_list = [1, 3, 5]` (`GOTPR/config.py:11-12`) y
comprueba coincidencia de `scene_id`, no distancia geográfica
(`eval_utils.py:59-83`).

## 3. Resultado de las fixtures

Se intentó construir una fixture mínima con:

- un JSON y una imagen sintética para `OSMTextImageDataset`;
- un `SceneGraph` `human` con dos nodos, una arista y vectores de 300
  dimensiones.

En la auditoría inicial no pudieron ejecutarse porque aquel entorno de modelos
no tenía `Pillow` ni `numpy`. Esta observación histórica no describe el entorno
geométrico `.venv-geo` de F3, que sí ejecuta NumPy 2.5.4, Shapely 2.1.2 y GEOS
3.13.1. Las fixtures de los repositorios externos deben repetirse en sus propios
entornos antes de integrar los modelos.

## 4. Conclusiones para Madrid

### A. CrossText2Loc

Sí, podemos generar un reference dataset nuevo de Madrid compatible en la rama
OSM, con estas condiciones:

- escoger y fijar un modelo/checkpoint concreto;
- reproducir el formato de imagen del checkpoint;
- corregir mediante wrapper la discrepancia de `img_crop` frente a `img`;
- validar la dimensión final con una fixture real pequeña;
- conservar un manifiesto propio de candidatos y coordenadas;
- calcular los embeddings offline con `encode_image` y el preprocesador oficial;
- usar el mismo modelo para el embedding textual durante retrieval.

La compatibilidad no debe declararse cerrada hasta validar el tamaño/área de
imagen contra un ejemplo oficial y el checkpoint seleccionado.

### B. GOTPR

No podemos afirmar todavía que sea posible generar un reference dataset nuevo
de Madrid compatible de forma reproducible.

El código de GOTPR sí permite cargar una scene compatible, convertirla a PyG,
crear embeddings de candidate extraction y ejecutar Milvus/reranking. Pero no
proporciona suficientemente:

- el teselado espacial OSM;
- la definición de una scene OSM;
- el inventario de etiquetas y atributos;
- la generación exacta de relaciones;
- el pipeline oficial de embeddings Ada;
- la correspondencia scene→coordenadas para una ciudad nueva.

Crear un conversor propio sería una nueva hipótesis experimental, no una
reproducción oficial de GOTPR.

### C. Información que falta

1. Checkpoint CrossText2Loc exacto y su configuración de entrenamiento.
2. Ejemplo oficial descargado para comprobar dimensiones y área efectiva.
3. Procedimiento oficial OSM→imagen para el checkpoint elegido.
4. Dataset o scripts privados/no publicados de generación OSM de GOTPR.
5. Definición espacial y sistema de coordenadas de las scenes GOTPR.
6. Origen exacto de los embeddings Ada incluidos en los artefactos GOTPR.
7. Criterio de acierto geográfico común entre ambos métodos.

### D. Partes disponibles y siguiente adaptación

- manifests F1 de 25 m y 50 m con `candidate_id`, latitud y longitud;
- snapshot F2 y bundles F3 geométricos verificados;
- almacenamiento separado de raw, processed, embeddings e índices;
- configuración con la bbox piloto D004 y granularidad todavía experimental;
- caché local y metadatos de procedencia e integridad;
- wrapper de `OSMTextImageDataset`;
- generación de imágenes CrossText2Loc mediante un script corregido y versionado;
- cálculo offline de embeddings CrossText2Loc una vez fijado el checkpoint;
- loader/validador de scene graphs con el formato que ya exige GOTPR;
- evaluación genérica de Haversine y Recall@K, etiquetando las métricas propias
  del TFG frente a las oficiales.

### E. Decisión recomendada

El modelo geográfico, manifests, snapshot OSM y catálogo geométrico F3 ya están
disponibles. F4 puede comenzar con contratos, loaders, fixtures y el diseño del
renderizado. La generación definitiva de imágenes, embeddings y evaluación de
CrossText2Loc debe esperar a D007, D013 y D016; no se debe construir todavía un
generador OSM→GOTPR.

Para GOTPR, la decisión debería ser una de estas:

1. obtener de los autores o de un artefacto oficial el pipeline de generación
   de scenes y reproducirlo;
2. declarar explícitamente un adapter experimental propio, separado de la
   reproducción oficial y con una validación independiente;
3. mantener GOTPR como comparación sobre sus datos oficiales y no presentarlo
   como reference dataset nuevo de Madrid si no se puede justificar la
   compatibilidad.

Hasta resolver esa elección no debe comenzar una generación masiva de scene
graphs GOTPR para Madrid.

### F. Frontera entre F3 y F4

F1 aporta `candidate_id`, coordenadas y celdas. F3 aporta objetos OSM
normalizados, asociaciones, contexto parcial de relations, provenance e
integridad. F4 deberá producir un manifest visual derivado con imágenes,
embeddings y su correspondencia con candidatos, sin modificar F1 ni F3.

Los bundles F3 no contienen geometrías completas suficientes para renderizar un
mapa por sí solos. F4 deberá usar una fuente de teselas permitida o reconstruir
el render desde F2 mediante infraestructura propia. El servidor estándar
`tile.openstreetmap.org` no debe utilizarse para descarga masiva u offline; se
requiere un proveedor compatible o renderizado propio, además de atribución OSM.

## 5. Estado actual de implementación y contratos

La auditoría de los modelos está separada de la infraestructura propia del TFG.
La Fase 0 ha creado contratos independientes de los repositorios externos en
`schemas/`, `config/madrid.yaml` y `src/tfg_phase0/`. Estos contratos no alteran
el formato interno de CrossText2Loc ni GOTPR.

Actualmente están definidos:

- configuración versionada de la región `madrid_pilot` con la bbox D004;
- manifest común con `candidate_id`, coordenadas y referencias opcionales a
  imágenes, embeddings y scenes;
- JSON Schema del contrato geográfico del LLM;
- JSON Schema del ejemplo de evaluación;
- representación nullable de parámetros experimentales;
- validadores básicos y hashes de provenance.

Los valores de granularidad, separación, número de candidatos, radios, pesos,
thresholds, idioma y métricas no se han convertido en constantes definitivas.

## 6. Roadmap condicionado

El orden aprobado es un grafo de dependencias, no una secuencia rígida:

```text
Fase 0: contratos y alcance
       ↓
Fase 1: modelo geográfico y manifest
       ↓
Fase 2: adquisición/cache OSM
       ↓
Fase 3: catálogo geométrico
       ├── Fase 5: LLM + preselección
       └── Fase 6: infraestructura de evaluación

Fase 4: CrossText2Loc ──┐
                        ├── Fase 7: evaluación baseline/propuesta
Fase 5 + Fase 6 ────────┘

Fase 8: GOTPR, si se resuelve D011
Fase 9: VLM/Street View/diálogo, si se resuelven permisos y diseño
Extensiones posteriores: GeoBridge, si se resuelven D038–D039;
                       TOLoc como refinamiento opcional
```

La Fase 4 no puede cerrarse hasta resolver D007, D013 y D016. Esto no impide
desarrollar contratos, geometría, preselección, loaders y métricas con fixtures.

## 7. GeoBridge como extensión opcional

Esta sección concentra los requisitos técnicos auditados de GeoBridge. Su
posición arquitectónica se resume en [PROJECT.md](PROJECT.md#47-estado-de-geobridge-en-este-proyecto),
los permisos en [LICENSES_AND_PERMISSIONS.md](LICENSES_AND_PERMISSIONS.md#auditoría-específica-de-geobridge-y-geoloc)
y las decisiones D036–D039 en [DECISIONS.md](DECISIONS.md).

### Fuente y versión auditada

| Recurso oficial | Versión consultada | Contenido relevante |
|---|---|---|
| [Repositorio GeoBridge](https://github.com/MiliLab/GeoBridge) | commit `636c413c58615669bb8b95c3eecedf161d3e523f` | `README.md`, `code/GeoBridge.py`, `code/test.py` y figuras; sin licencia, entorno ni código de entrenamiento. |
| [Checkpoint](https://huggingface.co/Son12s/GeoBridge) | snapshot `959a40cebc49cb821606cc581e366d7c56aff20d` | `best_net.pth`, `opts.yaml` y `.gitattributes`. |
| [GeoLoc](https://huggingface.co/datasets/Son12s/GeoLoc) | snapshot `cb3de0ca43ea1ea6c3b68ca2abca1a05aa33451e` | Solo `train_drone.rar` y `test_drone.rar`, además de `.gitattributes`. |
| [Paper CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/html/Song_GeoBridge_A_Semantic-Anchored_Multi-View_Foundation_Model_Bridging_Images_and_Text_CVPR_2026_paper.html) | publicación oficial | Método GeoBridge y dataset GeoLoc. |
| [GeoBridge++](https://arxiv.org/html/2512.02697v4) | arXiv v4 | Extensión con mapas estáticos y hechos OSM; no se encontró un release de código/checkpoint específico. |

El clon de referencia permanece en `external/GeoBridge/` sin modificaciones.
Los dos scripts pasan análisis sintáctico, pero no se ejecutó inferencia ni se
descargaron artefactos grandes.

### Representación, entradas y salidas

GeoBridge original dispone de cuatro ramas CLIP-L/14: texto y encoders visuales
independientes para *drone*, satélite y calle. El `forward` de
[`GeoBridge.py`](../external/GeoBridge/code/GeoBridge.py#L31) devuelve cuatro
matrices de embeddings normalizados y una escala aprendida. El paper representa
su dimensión común como `D`, pero las fuentes auditadas no la fijan
numéricamente; debe comprobarse al cargar el checkpoint.

Entrada visual publicada:

1. imagen `jpg`, `jpeg`, `png`, `bmp`, `tif` o `tiff`, convertida a RGB;
2. `Resize((224, 224), interpolation=3)`, según `opts.yaml`;
3. tensor normalizado con media `[0.485, 0.456, 0.406]` y desviación
   `[0.229, 0.224, 0.225]`;
4. promedio de features de la imagen original y su reflejo horizontal, activo
   por defecto;
5. normalización L2.

La entrada textual es un CSV con columna obligatoria `text` y un `id` explícito
o deducido de la primera columna restante. `CLIPTokenizer` aplica padding y
truncado sin `max_length` explícito. El identificador publicado para modelo y
tokenizer es `clip-vit-large-patch14`, sin organización de Hugging Face; debe
validarse en el entorno de los autores.

La salida de evaluación es una matriz de scores y un CSV Top-5 con IDs, rutas,
rangos y puntuaciones. El evaluador informa Top-1, Top-5, mAP y R@1 %. El paper
usa R@k y AP, además de métricas específicas según el benchmark.

### Retrieval real

El flujo texto→imagen confirmado es:

```text
texto → tokenizer → encoder textual → normalización L2
imagen → encoder de su vista → test-time flip → normalización L2
       ↓
producto matricial por bloques × temperatura
       ↓
orden descendente → Top-K por ID
```

[`compute_similarity_matrix`](../external/GeoBridge/code/test.py#L196) calcula
`Q @ G.T * logit_scale`. El script ejecuta explícitamente satélite→calle y
texto→satélite. El paper/README soportan además texto→*drone*, texto→calle y
comparaciones bidireccionales entre las tres vistas, pero el script no ofrece
una CLI parametrizada para todas ellas.

GeoBridge original **no consume imágenes OSM ni Scene Graphs**. Los mapas
estáticos y hechos de OSM pertenecen a GeoBridge++, no al checkpoint auditado.

### Checkpoint y límites de reproducibilidad

| Archivo | Tamaño | Uso observado |
|---|---:|---|
| `best_net.pth` | 6.866.335.661 bytes | Se carga como objeto PyTorch completo con `torch.load(..., weights_only=False)`. |
| `opts.yaml` | 384 bytes | Incluye `h = w = 224`, batch size y opciones de entrenamiento/evaluación. |
| `train_drone.rar` | 38.226.341.148 bytes | Subconjunto público *drone* de GeoLoc. |
| `test_drone.rar` | 4.928.851.311 bytes | Subconjunto público *drone* de test. |

La carga como pickle completo requiere confiar en el origen y reproducir las
clases/versiones esperadas. El repositorio no fija dependencias; los imports
exigen al menos PyTorch, torchvision, Transformers, NumPy, Pillow, pandas,
PyYAML y tqdm. El reflejo horizontal usa `.cuda()` directamente, por lo que el
camino CPU publicado no es completo.

Inconsistencias confirmadas del código:

- `make_model` llama a `load_params`, método no definido en la clase publicada
  ([`GeoBridge.py`](../external/GeoBridge/code/GeoBridge.py#L59));
- el bucle sobre `named_parameters()` intenta asignar `requires_grad` a la
  tupla devuelta, no al parámetro
  ([`GeoBridge.py`](../external/GeoBridge/code/GeoBridge.py#L12));
- `test.py` deserializa el objeto sin importar explícitamente la clase;
- el modelo define `logit_scale`, mientras el evaluador busca
  `model_logit_scale` y usa `1.0` si no existe
  ([`test.py`](../external/GeoBridge/code/test.py#L224));
- `_LON_LAT_4F`, usado para las métricas geográficas, no está definido
  ([`test.py`](../external/GeoBridge/code/test.py#L345));
- el nombre de salida `top5_text2drone_byid.csv` no coincide con la galería
  satelital pasada a la llamada final.

Por ello, el checkpoint está destinado a inferencia, pero la interfaz publicada
no es directamente reproducible sin un wrapper y aclaraciones. El paper no
exige fine-tuning para inferencia en GeoLoc; sí describe ajuste de las últimas
capas en benchmarks públicos, que no debe extrapolarse automáticamente a
Madrid.

### Relación posible con Madrid

La relación técnicamente derivable es:

```text
candidate_id
  → imagen autorizada de calle, satélite o drone
  → encoder GeoBridge de la modalidad
  → embedding normalizado precalculado
  → embedding_ref
```

El evaluador devuelve las features necesarias, pero no implementa su
persistencia. Guardarlas offline sería un adaptador propio. Tampoco define la
política para varias imágenes por candidato, orientación, FOV, fecha o
agregación.

La transferencia zero-shot a Madrid es **PENDIENTE DE EXPERIMENTO**: no está
demostrado el rendimiento con descripciones humanas, español, nuevas fuentes
visuales ni la cuadrícula del TFG. Footprint, modalidad y política por candidato
permanecen configurables por D039. Código, pesos y fuente de imágenes dependen
de D038. GeoBridge no forma parte del MVP por D036.
