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
[prototipo frontend](frontend/README.md) **simulado**. El frontend no ejecuta
modelos. F1, F2 y F3 proporcionan el catálogo geométrico, el snapshot OSM y los
bundles de asociaciones de Madrid; su cierre está en
[PHASE3_CLOSURE.md](docs/PHASE3_CLOSURE.md). La reproducción oficial
NewYork-mixed OSM de CrossText2Loc se completó en la NVIDIA GB10. F4 ya dispone
de una fixture local de nueve imágenes OSM y de una galería completa para los
253 candidatos F1 de 50 m, ambas con embeddings visuales CrossText2Loc. La
recuperación textual exhaustiva sobre 253 candidatos ya tiene una prueba
técnica; la evaluación formal de Madrid sigue pendiente.

F4.3 ya dispone de contratos, control de particiones, asignación geográfica y
métricas reproducibles. No existen todavía consultas humanas con referencias
validadas suficientes, por lo que no se publican métricas empíricas de Madrid.

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
comandos, resultados y recursos sin inventar mediciones. Las instrucciones de
adquisición de los datos y pesos se concretarán después de verificar su formato,
tamaño y permisos.

La operación del entorno validado de CrossText2Loc se documenta en
[docs/CROSSTEXT2LOC_DOCKER.md](docs/CROSSTEXT2LOC_DOCKER.md) y utiliza
`compose.cross-text2loc.yaml`.
Los resultados y la limitación metodológica del protocolo oficial se resumen en
[docs/CROSSTEXT2LOC_REPRODUCTION.md](docs/CROSSTEXT2LOC_REPRODUCTION.md).
La implementación del modelo geográfico y manifest del piloto se documenta en
[docs/PHASE1_GEOGRAPHIC_CATALOG.md](docs/PHASE1_GEOGRAPHIC_CATALOG.md).
La infraestructura offline para adquirir y congelar un snapshot OSM se describe
en [docs/PHASE2_OSM_SNAPSHOT.md](docs/PHASE2_OSM_SNAPSHOT.md). La Fase 2 ya
produjo y validó el primer snapshot real de la bbox D004; el raw permanece fuera
de Git y las fases posteriores deberán referenciar su `osm_snapshot_id`.

## Organización y ejecución futura en DGX

| Ruta | Contenido |
|---|---|
| `docs/`, `BASELINE.md`, `TFG_COMPONENTS.md` | Alcance, decisiones, requisitos y contexto |
| `config/`, `schemas/`, `src/tfg_phase0/`, `tests/` | Configuración y contratos propios ya existentes |
| `scripts/` | Preparación reproducible sin instalación implícita |
| `data/`, `checkpoints/`, `results/` | Ubicaciones locales de artefactos; solo metadatos pequeños seleccionados en Git |
| `external/` | Clones de terceros excluidos de Git |
| `frontend/`, `latex-memory/` | Prototipo previo y memoria existentes |

Los experimentos de GPU se ejecutarán **posteriormente en una NVIDIA DGX**.
No se presupone su modelo de GPU, driver, CUDA ni VRAM. En la DGX, después de
clonar este monorepo, se podrán ejecutar `bash scripts/check_dgx.sh` y
`bash scripts/setup_external.sh`; ninguno instala Python, CUDA ni PyTorch. El
entorno de inferencia y las descargas se prepararán en una fase posterior.
