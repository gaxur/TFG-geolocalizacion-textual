# Despliegue local de la aplicación integrada

## Alcance y estado seguro

`compose.app.yaml` construye `atlas-app-api:local` desde la imagen base local
`crosstext2loc-gb10:f511`, construye el frontend Vite con su Dockerfile y lo
sirve mediante Nginx. Solo Nginx publica un puerto y, por defecto, queda limitado
a `127.0.0.1:18085`; la API solo existe en la red interna de Compose.

El perfil distribuido en
`config/freetext_application_profile.template.json` está deliberadamente en
`PENDING_APPROVAL`, con `approved: false` y fechas expiradas. El servicio de
aplicación arranca para servir health/UI, pero permanece no disponible para
sesiones. Este estado es fail-closed y no autoriza inferencias. Arrancar infraestructura no concede una
autorización científica ni operativa.

Este despliegue no monta cohortes, autorizaciones científicas, fotografías,
imágenes de diálogo, bundles VLM ni ground truth. La promoción visual y los modos
DialogueVPR/FreeText científicos están desactivados explícitamente.

## Requisitos

- Linux con Docker Engine, Docker Compose v2 y NVIDIA Container Toolkit.
- GPU compatible con la imagen API; la referencia validada del proyecto es la
  NVIDIA GB10 ARM64. Otra máquina debe verificar arquitectura, driver, CUDA y
  VRAM.
- Imagen local `crosstext2loc-gb10:f511`. Compose usa `pull_policy: never` y no
  descarga la imagen.
- Dependencias del build frontend disponibles para `npm ci`. El build puede
  requerir acceso al registro npm si la caché local no las contiene; esto es
  preparación de imagen, no tráfico del runtime.
- Checkpoint CrossText2Loc, CLIP, Qwen3-8B, galerías, embeddings, clon CVG-Text,
  assets cartográficos y contexto PMTiles ya presentes en el host.

El runtime usa una red Compose marcada `internal` y variables offline de
Hugging Face/Transformers. No descarga modelos, datos ni mapas al arrancar.

## Rutas de la PGX

`.env.app.example` contiene las rutas reales observadas en este host el
2026-11-16. Son configuración, no rutas portables; deben revisarse si cambia el
checkout o se copia el despliegue a otra máquina.

| Variable | Ruta actual del host | Montaje |
|---|---|---|
| `APP_PROCESSED_DATA_DIR` | `/home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual/data/processed` | Catálogos, visuales OSM y F3, solo lectura |
| `APP_EMBEDDINGS_DIR` | `/home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual/data/embeddings` | Embeddings, solo lectura |
| `APP_EXTERNAL_DIR` | `/home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual/external` | CVG-Text, solo lectura |
| `APP_CHECKPOINT_DIR` | `/home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual/checkpoints/CrossText2Loc` | Checkpoint, solo lectura |
| `APP_CLIP_CACHE_DIR` | `/home/dataai/.cache/clip` | Pesos CLIP, solo lectura |
| `APP_QWEN_MODEL_DIR` | `/home/dataai/models/hf/Qwen3-8B-b968826d9c46` | Snapshot Qwen, solo lectura |
| `APP_MAP_ASSETS_DIR` | `/home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual/data/processed/map-assets` | Mapa local, solo lectura |
| `APP_MAP_CONTEXT_DIR` | `/home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual-maplibre-pgx/results/generated/map-assets-context-2000m` | Contexto PMTiles, solo lectura |

La imagen API se construye localmente con `docker/app-api.Dockerfile`; solo
incorpora código propio, configuración y schemas. Modelos, datos, embeddings,
checkpoint y CVG-Text permanecen en mounts host de solo lectura.

La API escribe únicamente en el volumen nombrado `atlas-app-state`, montado en
`/application-state`. Las sesiones viven en `/application-state/sessions`. Para
usar un bind mount en vez de un volumen se debe cambiar de forma explícita el
último montaje de `api`; no se debe convertir ningún montaje de datos/modelos a
lectura-escritura.

## Preparación

Desde la raíz del checkout integrado:

```bash
cp .env.app.example .env.app
```

Revisar las rutas sin crear directorios vacíos para ocultar artefactos ausentes:

```bash
test -f /home/dataai/.cache/clip/ViT-L-14-336px.pt
test -f /home/dataai/models/hf/Qwen3-8B-b968826d9c46/config.json
test -f /home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual/checkpoints/CrossText2Loc/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
test -f /home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual/data/processed/map-assets/madrid.pmtiles
test -f /home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual-maplibre-pgx/results/generated/map-assets-context-2000m/madrid-context-2000m.pmtiles
```

Validar la interpolación de Compose sin arrancar contenedores:

```bash
docker compose --env-file .env.app -f compose.app.yaml config --quiet
```

## Arranque, estado, logs y parada

El comando es autónomo y no depende de wrappers ni de `--env-file`. Los defaults
corresponden a esta PGX y pueden sobreescribirse mediante `.env` o variables de
entorno:

```bash
docker compose -f compose.app.yaml up -d --build
docker compose --env-file .env.app -f compose.app.yaml up -d --build
docker compose --env-file .env.app -f compose.app.yaml ps
docker compose --env-file .env.app -f compose.app.yaml logs -f api frontend
```

Abrir `http://127.0.0.1:18085/` en la PGX. Comprobaciones sin inferencia:

```bash
curl --fail http://127.0.0.1:18085/healthz
curl --fail http://127.0.0.1:18085/api/v1/health/live
curl -i http://127.0.0.1:18085/api/v1/health/ready
```

Parar sin borrar el estado persistente:

```bash
docker compose --env-file .env.app -f compose.app.yaml down
```

Con el perfil pendiente, readiness devuelve de forma esperada
`503 APPLICATION_PROFILE_NOT_APPROVED`; liveness y `/healthz` confirman que la
infraestructura está disponible. No usar `down --volumes` salvo que se haya aprobado borrar todas las sesiones,
recibos y estado de aplicación. `restart: unless-stopped` reinicia ambos servicios
tras fallos o reinicios del daemon, excepto cuando se hayan detenido manualmente.

## Acceso desde Windows por SSH

Mantener Nginx ligado a loopback. Desde PowerShell o Windows Terminal:

```powershell
ssh -N -L 18085:127.0.0.1:18085 dataai@192.168.12.219
```

Con el túnel activo, abrir `http://127.0.0.1:18085/` en Windows. El Compose fija
el bind a loopback y no ofrece una variable para ampliarlo a LAN.

## Memoria y GPU

La API solicita GPU mediante `gpus: all`, pero fija
`CUDA_VISIBLE_DEVICES=${APP_CUDA_VISIBLE_DEVICES:-0}`. Uvicorn arranca con un
solo worker mediante `scripts/run_mvp1_api.sh`; no aumentar workers porque cada
proceso puede duplicar modelos y agotar VRAM/RAM.

Antes de habilitar ejecución, comprobar que no existen cargas ajenas y observar
el consumo durante una ventana autorizada:

```bash
nvidia-smi
free -h
docker compose --env-file .env.app -f compose.app.yaml stats
```

El `tmpfs` API es de 2 GiB por defecto y se ajusta con
`APP_API_TMPFS_SIZE`; no sustituye la RAM necesaria para cargas secuenciales de
Qwen y CrossText2Loc.

## Aprobación y activación

La plantilla no es una autorización. Antes de poner `APP_MODE_ENABLED=true`, el
responsable debe crear un perfil separado y completar, como mínimo:

- `[PENDIENTE: responsable que aprueba y fundamento]`;
- `[PENDIENTE: profile_id, ventana temporal y límites de sesiones]`;
- `[PENDIENTE: hashes exactos de las políticas y del ejecutor]`;
- `[PENDIENTE: revisión de rutas, artefactos, GPU/RAM y política offline]`;
- `[PENDIENTE: aceptación expresa de limitaciones y procedimiento de revocación]`.

Después se configura `APP_PROFILE_FILE` con la ruta de ese JSON aprobado. El
backend debe validar estado, vigencia, hashes,
identidad, cuotas y restricciones; editar solo el booleano o copiar la plantilla
no habilita inferencia. No se deben reutilizar autorizaciones científicas ni
montarlas en este stack.

## Limitaciones

- El sistema recupera candidatos de una galería de Madrid; no es GPS, no estima
  una coordenada continua y la similitud coseno no es una probabilidad.
- Los pesos fueron entrenados fuera de Madrid. La transferencia zero-shot y la
  precisión con descripciones humanas no están validadas de forma general.
- La ausencia de evidencia OSM no demuestra que un elemento no exista.
- El mapa y su contexto son artefactos locales congelados; no se actualizan ni
  consultan servicios externos en runtime.
- La imagen API y los artefactos pesados no se construyen ni descargan con este
  procedimiento. Sus licencias, hashes y compatibilidad siguen siendo requisitos
  independientes.
- El healthcheck demuestra disponibilidad técnica, no autorización para ejecutar
  ni validez científica de resultados.
- El perfil por defecto impide el modo aplicación. No se realizó una ejecución de
  contenedores, modelos o inferencias al preparar esta guía.
