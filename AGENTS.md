# Guía para agentes del TFG

## Lecturas y estructura antes de modificar

Leer [README.md](README.md), [BASELINE.md](BASELINE.md) completo y
[docs/PROJECT.md](docs/PROJECT.md) antes de modificar el alcance. Consultar
[docs/DECISIONS.md](docs/DECISIONS.md), los requisitos de datos y las licencias
aplicables. Conservar `BASELINE.md` sin cambios salvo petición expresa.

El monorepo contiene documentación en `docs/`, contratos y código propio de la
Fase 0 en `src/tfg_phase0/`, schemas en `schemas/`, configuración en `config/`,
tests en `tests/`, un prototipo previo en `frontend/` y la memoria en
`latex-memory/`. `ml/` y `backend/` podrán incorporarse cuando exista código
propio que lo requiera. No mover ni borrar material existente sin revisar sus
referencias y su procedencia.

## Modelo e integridad científica

- Priorizar inferencia de CrossText2Loc con los pesos preentrenados **congelados**.
  No entrenar, hacer fine-tuning, backpropagation ni modificar su arquitectura
  salvo petición expresa. No ejecutar scripts de entrenamiento como parte de una
  comprobación de inferencia.
- No inventar propiedades de datasets, checkpoints, rutas internas, licencias ni
  resultados. Separar hechos publicados, comprobaciones propias, hipótesis y
  extensiones opcionales. Los resultados ajenos no son resultados del TFG.
- El protocolo oficial de `evaluate.py` selecciona 100 vecinos usando la
  coordenada real de cada consulta. No atribuir sus métricas a una búsqueda
  sobre una galería completa sin ese dato. En Madrid, el ground truth no se
  utilizará para seleccionar candidatos.
- La arquitectura propuesta combina LLM, OSM con posible enriquecimiento,
  CrossText2Loc/GOTPR y, condicionalmente, fotografías/VLM, diálogo y
  refinamiento. Distinguir la reproducción de Nueva York de la futura
  transferencia zero-shot a Madrid.

## Procedencia, datos y seguridad del repositorio

- `external/` contiene clones de terceros **no versionados**. El código de
  CVG-Text pertenece a sus autores; obtenerlo con `scripts/setup_external.sh`
  en la revisión fijada. No modificar silenciosamente un clon externo ni copiar
  su código a módulos propios. Revisar licencias antes de redistribuir.
- No descargar datasets, checkpoints o imágenes automáticamente sin comprobar
  tamaño, necesidad y condiciones. Nunca versionar pesos, datasets, secretos,
  credenciales, cachés ni resultados voluminosos. Inspeccionar los archivos
  staged antes de cada commit.
- Usar rutas configurables relativas al proyecto o parámetros, no rutas
  absolutas de una máquina. Preparar scripts para Linux/DGX; no presumir GPU,
  driver, versión de CUDA o VRAM hasta medirlos allí.
- Conservar hashes, commits, versiones, parámetros y procedencia de cada
  experimento. Registrar experimentos en [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md)
  y las decisiones técnicas/metodológicas en [docs/DECISIONS.md](docs/DECISIONS.md).
  Respetar sus estados; una propuesta no es `ACEPTADA` sin aprobación expresa.

## Documentación y comprobaciones

Escribir documentación de proyecto en español UTF-8, con títulos descriptivos,
párrafos breves, tablas cuando aclaren comparaciones y enlaces relativos.
Usar bloques `mermaid` para nuevos diagramas. Conservar referencias originales y
no inventar URLs. Revisar enlaces, Markdown y Mermaid antes de entregar.

La Fase 0 tiene tests en `tests/test_phase0.py`; el prototipo frontal tiene
comandos en `frontend/package.json`. Ejecutar solo verificaciones pertinentes
al cambio. Antes de un commit revisar `git status`, `git diff`, el historial
disponible y el conjunto staged. Para PR, explicar cambios, fuentes y revisión;
añadir capturas únicamente si facilitan valorar elementos visuales.
