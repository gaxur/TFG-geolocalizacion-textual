# TFG — Geolocalización desde descripciones en lenguaje natural

Proyecto de Trabajo de Fin de Grado para estudiar la recuperación de ubicaciones
geográficas a partir de descripciones libres. El recorrido previsto es:

```text
Descripción textual → generación/preselección de candidatos
                    → recuperación cross-modal → ranking → Top-K de coordenadas
```

La propuesta completa y sus decisiones abiertas están en
[docs/PROJECT.md](docs/PROJECT.md) y [docs/DECISIONS.md](docs/DECISIONS.md). El
contexto original se conserva sin cambios en [BASELINE.md](BASELINE.md).

## Estado actual y siguiente experimento

Ya existen contratos propios de Fase 0 (`src/tfg_phase0/`, `schemas/`,
`config/madrid.yaml`), documentación, una memoria LaTeX y un
[frontend Vite](frontend/README.md) conectado a la API interna. La interfaz
ejecuta CrossText2Loc y admite postprocesamiento Qwen3-VL precalculado con
identidad verificable; cuando no existe evidencia compatible declara el fallback
y conserva exactamente el ranking CrossText2Loc.
F1, F2 y F3 proporcionan el catálogo geométrico, el snapshot OSM y los
bundles de asociaciones de Madrid; su cierre está en
[PHASE3_CLOSURE.md](docs/PHASE3_CLOSURE.md). La reproducción oficial
NewYork-mixed OSM de CrossText2Loc se completó en la NVIDIA GB10. F4 ya dispone
de una fixture local de nueve imágenes OSM y de una galería completa para los
253 candidatos F1 de 50 m y de 1.115 candidatos F1 de 25 m, ambas con embeddings
visuales CrossText2Loc. La recuperación textual exhaustiva y la comparación
técnica 25 m/50 m ya están operativas; la evaluación formal de Madrid sigue
pendiente.

F4.3 ya dispone de contratos, control de particiones, asignación geográfica y
métricas reproducibles. No existen todavía consultas humanas con referencias
validadas suficientes, por lo que no se publican métricas empíricas de Madrid.

F4.5 añade un experimento técnico de robustez lingüística con 27 variantes
controladas en inglés y español sobre ambas galerías. Sus métricas describen
estabilidad de ranking, no precisión geográfica.

F4.6 cierra técnicamente CrossText2Loc con una interfaz Python residente: una
carga de modelo, galerías 25 m/50 m reutilizables y consultas Top-K individuales
o multigalería.

MVP.1 añade una API FastAPI interna con health, capabilities y retrieval real,
manteniendo una sola instancia GPU.

MVP.2 conecta el frontend Vite con esa API y muestra candidatos reales en un
mapa interactivo. La interfaz sintética anterior se retiró de forma definitiva.

MVP.3 cierra el despliegue integrado mediante `compose.mvp.yaml`: Nginx sirve el
frontend estático y redirige `/api` a FastAPI dentro de la red Compose. Se
publica únicamente el frontend en el puerto 8080 de la PGX y CrossText2Loc se
carga una vez en GPU.

La modernización mantiene ese despliegue y utiliza MapLibre, GeoJSON F1 y el
PMTiles local `data/processed/map-assets/madrid.pmtiles`, servido por el mismo
Nginx. F2/F4 se verificaron por hash/provenance; el mapa vectorial local se
construyó desde el PBF F4 con un buffer cartográfico de 250 m. Las extrusiones
solo usan alturas OSM numéricas explícitas; la cobertura es parcial y los niveles
no se convierten a metros. La auditoría, el esquema y la validación están en
[FRONTEND_MAPLIBRE.md](docs/FRONTEND_MAPLIBRE.md).

## Ejecutar el MVP

La guía completa de despliegue, configuración, parada y diagnóstico está en
[MVP.md](docs/MVP.md). Para actualizar una rama en PGX, conservar su worktree y
validar artefactos, SSE, HTTP Range y consultas reales, consulta
[MVP_PGX_DEPLOYMENT.md](docs/MVP_PGX_DEPLOYMENT.md). Desde la raíz:

Antes de arrancar deben existir localmente:

- `external/CVG-Text/` en el commit fijado por `scripts/setup_external.sh`;
- el checkpoint en `checkpoints/CrossText2Loc/`;
- CLIP en `$HOME/.cache/clip/ViT-L-14-336px.pt`;
- manifests, bundles visuales y embeddings indicados por
  `config/madrid_f46_retriever.json`.

Los nombres y ubicaciones exactos están en
[MVP.md](docs/MVP.md#archivos-locales-obligatorios-fuera-de-git).
No es obligatorio crear `.env`; `.env.mvp.example` es una plantilla opcional que
el wrapper y Docker Compose leen desde la raíz cuando se copia como `.env`.

```bash
scripts/run_mvp3_stack.sh
```

La interfaz experimental permite elegir galería 25/50 m y procesamiento Sin
LLM/Con LLM. Sin LLM usa el texto original; Con LLM aplica provisionalmente Qwen
`en_cartographic`. Cada consulta ejecuta una sola combinación y devuelve Top-10,
sin fusión ni fallback. El modo Qwen requiere definir `MVP_QWEN_MODEL_DIR` y una
imagen API reconstruida con las dependencias F5.11; véase [MVP.md](docs/MVP.md).
La imagen validada es `crosstext2loc-gb10:f511`; el smoke integrado real completó
las cuatro combinaciones en la GB10.

Este wrapper comprueba los artefactos externos y ejecuta el equivalente a
`docker compose -f compose.mvp.yaml up --build`. Abrir
`http://127.0.0.1:8080/` desde la PGX o `http://IP_LOCAL:8080/` desde un
dispositivo de la misma LAN. El wrapper publica en `0.0.0.0` por defecto. Para
segundo plano y parada:

```bash
scripts/run_mvp3_stack.sh -d
docker compose -f compose.mvp.yaml down
```

Para impedir el acceso LAN:

```bash
MVP_BIND_HOST=127.0.0.1 scripts/run_mvp3_stack.sh -d
```

Los contenedores se crean con nombres estables `atlas-mvp-api` y
`atlas-mvp-frontend`, sin el sufijo automático `-1` de Docker Compose.

La configuración, acceso LAN opcional, healthchecks, pruebas y diagnóstico se
documentan en [MVP.md](docs/MVP.md), junto con la API, el frontend, la validación
y las limitaciones del MVP funcional.

El cuadro de métricas está en
[MVP.md](docs/MVP.md#estado-de-evaluación-y-métricas). Recall@K y error
geográfico de Madrid figuran como no disponibles porque todavía no existen
referencias evaluables validadas; no se presentan los tests técnicos como
precisión del modelo.

F5.1 prepara la recogida de observaciones, topónimos, orientación y variantes
textuales sin ejecutar traducción ni modificar el MVP. Contrato, plantilla y
procedimiento: [PHASE5_TEXTUAL_VARIANTS.md](docs/PHASE5_TEXTUAL_VARIANTS.md).

F5.2 implementa el adaptador de transformación textual, protección de topónimos,
validación y comparación independiente de rankings. `Qwen/Qwen3-8B` fue validado
realmente en la GB10 y comparado con CrossText2Loc sobre sondas técnicas sin
ground truth:
[PHASE5_TEXT_TRANSFORMATION.md](docs/PHASE5_TEXT_TRANSFORMATION.md).

La guía práctica exclusiva del modelo, traducción, topónimos, ejecución, memoria
y limitaciones está en [QWEN.md](docs/QWEN.md).

F5.3 implementa extracción geográfica estructurada con evidencia textual. La
infraestructura y Qwen real se validaron, pero la tasa de cumplimiento del
contrato fue insuficiente para integrarla automáticamente:
[PHASE5_GEOGRAPHIC_EXTRACTION.md](docs/PHASE5_GEOGRAPHIC_EXTRACTION.md).

F5.4 implementa el contrato, recopilación y evaluador geográfico de las cinco
variantes sobre galerías 25 m/50 m. La auditoría actual encontró cero
observaciones humanas con GT validado, por lo que no publica precisión todavía:
[PHASE5_GEOGRAPHIC_EVALUATION.md](docs/PHASE5_GEOGRAPHIC_EVALUATION.md).

F5.5c materializa 35 consultas
`synthetic_osm` trazables y pendientes de revisión, separadas del GT real:
[PHASE5_SYNTHETIC_OSM_BENCHMARK.md](docs/PHASE5_SYNTHETIC_OSM_BENCHMARK.md).

F5.6 conserva el antecedente histórico de cinco referencias Street View
documentales usado por F5.7. Sus capturas locales se retiraron tras F5.9; quedan
metadatos, hashes y resultados para trazabilidad, no un flujo visual activo:
[PHASE56_STREETVIEW_DOCUMENTARY.md](docs/PHASE56_STREETVIEW_DOCUMENTARY.md).

F5.7 ejecuta provisionalmente 16 variantes Qwen y 40 rankings CrossText2Loc sobre
los cuatro casos activos. Sus métricas usan coordenadas de enlace con
incertidumbre desconocida y son exclusivamente experimentales, separadas de
F5.4: [PHASE57_EXPERIMENTAL_EVALUATION.md](docs/PHASE57_EXPERIMENTAL_EVALUATION.md).

F5.8 cambia el objetivo funcional para priorizar una ubicación próxima dentro del
Top-10. La auditoría de F5.7 y F5.5c no permite todavía elegir definitivamente
variante o uso de Qwen; propone una muestra humana dirigida:
[PHASE58_GEORECALL_DECISION.md](docs/PHASE58_GEORECALL_DECISION.md).

F5.9 incorpora H01–H10 como referencias Street View exploratorias, compara cinco
variantes y conserva candidatos Top-10 individuales. Es el conjunto humano
experimental vigente: [PHASE59_HUMAN_STREETVIEW_EXPERIMENT.md](docs/PHASE59_HUMAN_STREETVIEW_EXPERIMENT.md).

F5.10 consolida numeradores, denominadores, métricas Top-1/Top-10 y comparaciones
pareadas, detecta solapamientos con F5.7 y prepara una validación independiente
para D076: [PHASE510_METRIC_CONSOLIDATION.md](docs/PHASE510_METRIC_CONSOLIDATION.md).

H11–H25 añade una evaluación humana independiente de `es_original` frente a
`en_cartographic`, con H16 interior separado y 60 rankings reales:
[PHASE_H11_H25_EVALUATION.md](docs/PHASE_H11_H25_EVALUATION.md).

La siguiente fase propuesta estudia evidencia fotográfica autorizada y un VLM
como verificador/reranker del Top-10, comenzando por contratos y una fixture
propia antes de integrar modelos:
[PHASE_VLM_VISUAL_RERANKING_PLAN.md](docs/PHASE_VLM_VISUAL_RERANKING_PLAN.md).

El check bilingüe F4.5/F5.2 pertenece al contrato HTTP histórico anterior. La API
experimental F5.11 acepta descripciones originales españolas y compara Sin LLM
frente a Qwen; no reutiliza ese script como prueba operativa.

El primer experimento, completado **sin entrenamiento ni fine-tuning**, fue:

```text
Texto New York → CrossText2Loc → checkpoint NewYork-mixed OSM
              → candidatos OSM New York → ranking y Top-K
```

Posteriormente se estudiará, en un experimento distinto, texto de Madrid frente
a candidatos preparados para Madrid **con el mismo modelo y los mismos pesos
congelados**. La transferencia zero-shot es una hipótesis pendiente de evaluar,
no un resultado. Los perfiles de imágenes y los permisos pendientes se registran
en [docs/DATASET_MODEL_REQUIREMENTS.md](docs/DATASET_MODEL_REQUIREMENTS.md) y
[docs/LICENSES_AND_PERMISSIONS.md](docs/LICENSES_AND_PERMISSIONS.md).

La evaluación oficial de Nueva York utiliza los **100 candidatos más próximos a
la coordenada real** de cada texto (`evaluate.py` del repositorio original). Una
búsqueda sobre una galería fijada sin usar el ground truth constituye otro
protocolo y se documentará por separado; en Madrid la respuesta correcta no
reducirá el espacio de búsqueda.

## Código externo y reproducibilidad

[CVG-Text / CrossText2Loc](https://github.com/yejy53/CVG-Text) pertenece a sus
autores. La revisión auditada es
`6910d2747a94fbe985309bde60cd4732bcbbf50f`. No forma parte de este
repositorio: `external/` se ignora y [scripts/setup_external.sh](scripts/setup_external.sh)
permite clonar y fijar esa revisión localmente, tras revisar las condiciones
aplicables. La licencia del código externo y la de los pesos no se consideran
resueltas por el hecho de estar disponibles públicamente.

Los checkpoints, datasets, imágenes y resultados voluminosos **no se almacenan
en Git**. [data/README.md](data/README.md),
[checkpoints/README.md](checkpoints/README.md) y
[results/README.md](results/README.md) describen las ubicaciones locales;
`docs/EXPERIMENTS.md` proporciona la plantilla para registrar versiones,
comandos, resultados y recursos sin inventar mediciones. La preparación de los
artefactos locales y las condiciones pendientes se documentan en las guías de
datos, modelos, licencias y despliegue; el repositorio no los descarga al
arrancar el MVP.

El entorno validado, la reproducción oficial, la interfaz residente y las
limitaciones de CrossText2Loc se documentan en
[docs/CROSSTEXT2LOC.md](docs/CROSSTEXT2LOC.md). El shell científico utiliza
`compose.cross-text2loc.yaml`; el despliegue de la aplicación usa
`compose.mvp.yaml`.
La implementación del modelo geográfico y manifest del piloto se documenta en
[docs/PHASE1_GEOGRAPHIC_CATALOG.md](docs/PHASE1_GEOGRAPHIC_CATALOG.md).
La infraestructura offline para adquirir y congelar un snapshot OSM se describe
en [docs/PHASE2_OSM_SNAPSHOT.md](docs/PHASE2_OSM_SNAPSHOT.md). La Fase 2 ya
produjo y validó el primer snapshot real de la bbox D004; el raw permanece fuera
de Git y las fases posteriores deberán referenciar su `osm_snapshot_id`.

## Organización y ejecución en PGX/DGX

| Ruta | Contenido |
|---|---|
| `docs/`, `BASELINE.md` | Alcance, decisiones, requisitos, operación y contexto |
| `config/`, `schemas/`, `src/tfg_phase0/`, `tests/` | Configuración y contratos propios ya existentes |
| `scripts/` | Preparación reproducible sin instalación implícita |
| `data/`, `checkpoints/`, `results/` | Ubicaciones locales de artefactos; solo metadatos pequeños seleccionados en Git |
| `external/` | Clones de terceros excluidos de Git |
| `frontend/`, `backend/`, `compose.mvp.yaml` | Aplicación MVP y despliegue integrado |
| `latex-memory/` | Memoria del TFG |

El entorno principal validado actualmente es una PGX ARM64 con NVIDIA GB10. Una
ejecución posterior en otra DGX debe volver a comprobar GPU, driver, CUDA, VRAM,
arquitectura de las imágenes y rutas locales; no se extrapola automáticamente la
compatibilidad. `bash scripts/check_dgx.sh` y `bash scripts/setup_external.sh`
ayudan a inspeccionar y preparar el clon externo, pero no instalan Python, CUDA,
PyTorch ni los artefactos pesados del MVP.
