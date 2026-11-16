# Despliegue local de la aplicación integrada

## Alcance y estado seguro

`compose.app.yaml` construye `atlas-app-api:local` desde la imagen base local
`crosstext2loc-gb10:f511`, construye el frontend Vite con su Dockerfile y lo
sirve mediante Nginx. Solo Nginx publica un puerto y, por defecto, queda limitado
a `127.0.0.1:8080`; la API solo existe en la red interna de Compose.

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
Hugging Face/Transformers. No descarga modelos, datos ni mapas al arrancar. El
sidecar `resource-monitor` permite únicamente `/api/ps` hacia Ollama para el
resource gate; no publica puerto y la API permanece en la red interna.

## Rutas de la PGX

`.env.app.example` contiene rutas relativas portables. Los modelos o artefactos
que residan fuera del checkout deben configurarse en el `.env.app` local.

| Variable | Ruta actual del host | Montaje |
|---|---|---|
| `APP_PROCESSED_DATA_DIR` | `./data/processed` | Catálogos, visuales OSM y F3, solo lectura |
| `APP_EMBEDDINGS_DIR` | `./data/embeddings` | Embeddings, solo lectura |
| `APP_EXTERNAL_DIR` | `./external` | CVG-Text, solo lectura |
| `APP_CHECKPOINT_DIR` | `./checkpoints/CrossText2Loc` | Checkpoint, solo lectura |
| `APP_CLIP_CACHE_DIR` | `./models/clip` | Pesos CLIP, solo lectura |
| `APP_QWEN_MODEL_DIR` | `./models/Qwen3-8B` | Snapshot Qwen, solo lectura |
| `APP_MAP_ASSETS_DIR` | `./data/processed/map-assets` | Mapa local, solo lectura |
| `APP_MAP_CONTEXT_DIR` | `./results/generated/map-assets-context-2000m` | Contexto PMTiles, solo lectura |

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
set -a; . ./.env.app; set +a
test -f "$APP_CLIP_CACHE_DIR/ViT-L-14-336px.pt"
test -f "$APP_QWEN_MODEL_DIR/config.json"
test -f "$APP_CHECKPOINT_DIR/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth"
test -f "$APP_MAP_ASSETS_DIR/madrid.pmtiles"
test -f "$APP_MAP_CONTEXT_DIR/madrid-context-2000m.pmtiles"
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

Abrir `http://127.0.0.1:8080/` en la PGX. Comprobaciones sin inferencia:

```bash
curl --fail http://127.0.0.1:8080/healthz
curl --fail http://127.0.0.1:8080/api/v1/health/live
curl -i http://127.0.0.1:8080/api/v1/health/ready
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
ssh -N -L 8080:127.0.0.1:8080 dataai@192.168.12.219
```

Con el túnel activo, abrir `http://127.0.0.1:8080/` en Windows. El Compose fija
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

La plantilla no es una autorización. D098 aprobó para esta PGX sesiones
acumuladas ilimitadas, una abierta, máximos 4 Qwen/4 CT2L/3 preguntas, cero
retries y vigencia de 90 días. El perfil real se genera fuera de Git con la
expiración absoluta y referencia de aprobación registradas; volver a ejecutar el
generador no puede extender por sí solo esa vigencia.

Después se configura `APP_PROFILE_FILE` con la ruta de ese JSON aprobado. El
backend debe validar estado, vigencia, hashes,
identidad, cuotas y restricciones; editar solo el booleano o copiar la plantilla
no habilita inferencia. No se deben reutilizar autorizaciones científicas ni
montarlas en este stack.

### Perfil v2 residente

El perfil real se genera dentro de la imagen API final, con los mounts y el
volumen de estado efectivos:

```bash
docker compose -f compose.app.yaml build api
docker compose -f compose.app.yaml run --rm --no-deps \
  -v "$PWD/runtime/freetext-application:/profile-output" \
  api python scripts/generate_freetext_application_profile.py \
  --output /profile-output/freetext-application-pgx-20261116-v2.json
```

El arranque solo valida identidad y permanece lazy. Una prueba real iniciada por
el operador debe exigir:

- E0: `cache_hit=false` para Qwen y CT2L, una carga física por modelo y ranking
  exhaustivo de 253 candidatos 50 m;
- E1-E3, si se alcanzan: `cache_hit=true` y ninguna carga física adicional;
- sidecars `eN-qwen-runtime.json` y `eN-crosstext2loc-runtime.json` con latencias;
- cero retries, estado durable y cierre controlado de ambos modelos.

`/health/ready` confirma perfil/configuración, no que los dos modelos ya se hayan
cargado o que quepan simultáneamente en memoria.

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
- El perfil por defecto impide el modo aplicación. La prueba v1 y su supersession
  están registradas en `APP_TEST_RESULTS.md`. V2 residente tiene E0 real y un
  intento E1 rechazado por validación; no existe todavía recorrido E1-E3 completo
  ni métricas de mejora.
