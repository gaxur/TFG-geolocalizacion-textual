# Catálogo y evaluación de Madrid

Este documento define la organización de los datos de Madrid. La infraestructura
determinista del catálogo geométrico está implementada en Fase 1 y se documenta
en [PHASE1_GEOGRAPHIC_CATALOG.md](PHASE1_GEOGRAPHIC_CATALOG.md). No se ha
adquirido OSM ni generado el catálogo visual. El piloto utiliza la bounding box
fijada en D004; la extensión definitiva de Madrid continúa pendiente.

## 1. Separación de recursos

### Catálogo offline de referencia

El catálogo contiene localizaciones candidatas sobre las que se ejecuta la
búsqueda. Cada entrada debe conservar, como mínimo:

```text
candidate_id
latitude
longitude
```

También conservará la procedencia, la versión/fecha de OSM, la región, las
transformaciones y las representaciones disponibles.

Para CrossText2Loc, una entrada puede asociar:

- imagen OSM y referencia a su embedding visual;
- imagen satelital y referencia a su embedding, únicamente si se incorpora y
  se confirma su fuente y licencia.

Para GOTPR, una entrada puede asociar un OSM Scene Graph y su representación o
índice. La creación de OSM Scene Graphs de Madrid compatibles con el checkpoint
publicado sigue **PENDIENTE DE VALIDAR**; el repositorio oficial no proporciona
todo ese conversor.

Como extensión futura, una entrada podría asociar una o varias imágenes de
calle, satélite o *drone* y embeddings GeoBridge por modalidad. GeoBridge
original no consume la imagen OSM del catálogo. Estos campos no se añaden al
manifest actual: primero deben resolverse D038 (permisos) y D039 (modalidad,
footprint, orientación y transferencia a Madrid).

### Dataset de evaluación

El dataset de evaluación es independiente del catálogo como artefacto lógico.
Contiene descripciones, posición real y metadatos de procedencia. La posición
real solo se utiliza después de la inferencia para calcular métricas.

Una descripción de evaluación no se usa para entrenar ni ajustar los pesos.
Puede corresponder a una localización que también exista en el catálogo: eso es
necesario para medir recuperación. Lo que no puede ocurrir es que el
`ground_truth` se use para preseleccionar candidatos.

## 2. Flujo offline

```text
OSM/Overpass
    ↓
datos vectoriales raw y metadatos
    ↓
normalización y candidatos
    ├── renderizado de teselas → imágenes OSM → embeddings CrossText2Loc
    ├── OSM Scene Graphs → representaciones GOTPR (si se valida el formato)
    └╌ imágenes visuales autorizadas → embeddings GeoBridge (extensión)
```

Overpass devuelve datos OSM, geometrías y etiquetas; no devuelve imágenes
cartográficas ni scene graphs GOTPR. Las imágenes OSM se obtienen mediante un
servicio de teselas/renderizado compatible con el modelo. El script oficial de
CVG-Text usa `contextily` y `tile.openstreetmap.org`, pero contiene una
discrepancia: calcula `img_crop` y guarda `img`. La corrección y la validación
del tamaño/área deben vivir en un wrapper propio.

Los datos raw, procesados, imágenes, embeddings, grafos e índices se mantienen
separados y no se incorporan al repositorio Git.

## 3. Flujo online

```text
descripción + zona
        ↓
LLM → consulta geográfica estructurada
        ↓
OSM/Overpass + consulta estructurada
        ↓
candidate_id preseleccionados
        ├── CrossText2Loc: texto → embedding → representaciones visuales
        ├── GOTPR: texto → Text Scene Graph → OSM Scene Graphs
        └╌ GeoBridge: texto → embedding → imágenes de calle/satélite/drone
        ↓
Top-N
```

La preselección no utiliza las imágenes OSM, las imágenes satelitales ni sus
embeddings. Tampoco elimina físicamente representaciones del catálogo: solo
limita las entradas participantes en esa consulta.

Se conservará un modo de evaluación sin preselección y se medirá la cobertura
del filtro antes de medir Recall@K del recuperador.

## 4. Estado de viabilidad

| Pipeline | Estado | Evidencia | Falta |
| --- | --- | --- | --- |
| Madrid → candidatos → imágenes OSM → embeddings CrossText2Loc → retrieval | VIABLE CON ADAPTACIÓN | `dataset.py`, `model_loader.py`, `evaluate.py` y `download_osm_street.py` del commit auditado de CVG-Text | Fijar checkpoint, validar renderizado y crear índice/manifiesto propios |
| Madrid → candidatos → OSM Scene Graphs → GOTPR → retrieval | EXPERIMENTAL | `scene_graph.py`, `models.py`, `scene_graph_candidates_extraction.py` y `eval_utils.py` de GOTPR | Constructor OSM→scene graph, reglas espaciales, embeddings y compatibilidad del checkpoint |
| Madrid → Street View → VLM | BLOQUEADO/PENDIENTE | APIs y términos oficiales de Google Maps Platform | Confirmar legalmente descarga/procesamiento/caché/uso con VLM |
| Madrid → imágenes satelitales Google → embeddings | BLOQUEADO/PENDIENTE | Términos de Google Maps Platform | Fuente alternativa o permiso específico; no usar como supuesto del MVP |
| Madrid → imágenes autorizadas → embeddings GeoBridge → retrieval/reranking | EXTENSIÓN CONDICIONADA | Encoders y scoring del commit auditado de GeoBridge | D038, carga reproducible del checkpoint y experimento zero-shot D039 |

## 5. Criterio de publicación

El repositorio puede contener código propio, manifiestos sin contenido
restringido, consultas, identificadores, hashes, métricas y documentación. No
deben publicarse claves, checkpoints, imágenes de Google, datasets de terceros
ni índices derivados cuya licencia no permita redistribución.
