# Guía de actualización y validación del MVP en PGX

Esta guía actualiza el código sin sobrescribir cambios locales, reutiliza los
artefactos ya instalados en PGX y valida el despliegue sin descargar datasets ni
checkpoints. No ejecutes inferencias mientras otra persona o proyecto use la GPU.

## 1. Comprobar la copia de trabajo de PGX

Usa la ruta real del checkout existente; no des por supuesto el nombre del
directorio:

```bash
PROJECT_ROOT="$HOME/Projects/TFG-geolocalizacion-textual"
cd "$PROJECT_ROOT"
git remote -v
git status --short --branch
git rev-parse --show-toplevel
```

Si `git status` muestra cambios, **no** ejecutes `switch`, `pull`, `reset`,
`clean` ni `stash` automáticamente. Inspecciona y conserva primero los cambios
locales. Copia de seguridad opcional fuera del checkout:

```bash
BACKUP_DIR=$(mktemp -d "$HOME/tfg-worktree-backup.XXXXXX")
git diff --binary > "$BACKUP_DIR/unstaged.patch"
git diff --cached --binary > "$BACKUP_DIR/staged.patch"
git ls-files -z --others --exclude-standard \
  | tar --null -T - -czf "$BACKUP_DIR/untracked.tar.gz"
printf 'Copia local en %s\n' "$BACKUP_DIR"
```

Esta copia no incluye artefactos ignorados (`data/`, `checkpoints/`,
`external/`). Mantén el checkout como está hasta decidir cómo conservar sus
cambios y recursos locales.

## 2. Obtener la rama publicada sin sobrescribir el checkout

En un checkout limpio, o después de resolver conscientemente sus cambios:

```bash
git fetch origin
git ls-remote --heads origin feature/mvp-maplibre-progress-pgx
git switch --track -c feature/mvp-maplibre-progress-pgx \
  origin/feature/mvp-maplibre-progress-pgx
git status --short --branch
git rev-parse HEAD
```

Si la rama local ya existe, comprueba primero que el checkout esté limpio y usa:

```bash
git switch feature/mvp-maplibre-progress-pgx
git merge --ff-only origin/feature/mvp-maplibre-progress-pgx
```

La actualización normal de la rama conserva los archivos ignorados del mismo
checkout; no borres ni reemplaces `data/`, `external/`, `checkpoints/` o `.env`.

## 3. Inventariar dependencias y artefactos locales

El runtime necesita el clon CVG-Text fijado, el checkpoint CrossText2Loc, CLIP,
los dos manifests F1, las selecciones F4, los bundles visuales/embeddings de ambas
galerías y Qwen3-8B. El mapa usa GeoJSON F1 y, para el basemap/extrusión local,
PMTiles con provenance. El PBF F4 y el snapshot F2 solo hacen falta para
regenerar o auditar cartografía; no se requieren para la inferencia online.

Verifica identidades y rutas antes de copiar nada:

```bash
test "$(git -C external/CVG-Text rev-parse HEAD)" = \
  6910d2747a94fbe985309bde60cd4732bcbbf50f
test -f external/CVG-Text/utils.py
test -f checkpoints/CrossText2Loc/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
test "$(sha256sum checkpoints/CrossText2Loc/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth | cut -d' ' -f1)" = \
  d0c2f684ec838fa22dc7e607f0f1dc790468aef6df050cf472720756c26da47d
CLIP_WEIGHTS="${MVP_CLIP_CACHE_DIR:-$HOME/.cache/clip}/ViT-L-14-336px.pt"
test -f "$CLIP_WEIGHTS"
test "$(sha256sum "$CLIP_WEIGHTS" | cut -d' ' -f1)" = \
  3035c92b350959924f9f00213499208652fc7ea050643e8b385c2dac08641f02
test -f "${MVP_QWEN_MODEL_DIR:-$HOME/models/hf/Qwen3-8B-b968826d9c46}/config.json"
test -f "${MVP_QWEN_MODEL_DIR:-$HOME/models/hf/Qwen3-8B-b968826d9c46}/tokenizer.json"
test -f data/processed/catalog/manifest-25m.json
test -f data/processed/catalog/manifest-50m.json
test -f data/processed/map-assets/map-assets.json
test -f data/processed/map-assets/cells-25m.geojson
test -f data/processed/map-assets/cells-50m.geojson
test -f data/processed/map-assets/madrid.pmtiles
test -f data/processed/map-assets/madrid.pmtiles.provenance.json
```

El wrapper `scripts/run_mvp3_stack.sh` comprueba el checkpoint, CLIP, Qwen,
CVG-Text, manifests, bundles visuales y embeddings del runtime antes de arrancar.
Confirma también que la imagen `crosstext2loc-gb10:f511` existe. Si falta una
dependencia, detente y localiza la copia autorizada antes de descargar o
transferir artefactos. No crees directorios vacíos para superar el preflight.

Para transferir desde otro checkout de **la misma PGX**, haz primero un inventario
de origen y destino. Copia solo las rutas verificadas que falten y conserva las
existentes, por ejemplo:

```bash
rsync -a --ignore-existing --info=progress2 \
  "$SOURCE_PROJECT/data/processed/catalog/" \
  "$PROJECT_ROOT/data/processed/catalog/"
```

Repite únicamente para el bundle o directorio concreto que hayas confirmado como
ausente. Comprueba hashes/manifests después de copiar. No transfieras `data/raw`
si no vas a regenerar cartografía, ni pesos/modelos ya instalados. `rsync` de esta
guía no se ejecuta automáticamente.

## 4. Comprobar Docker, GPU y configuración

```bash
docker compose version
docker info --format '{{json .Runtimes}}'
nvidia-smi
docker image inspect crosstext2loc-gb10:f511 \
  --format '{{.Id}} {{.Architecture}} {{.Os}}'
docker compose -f compose.mvp.yaml config --quiet
docker compose -f compose.mvp.yaml ps
```

Comprueba primero los contenedores existentes. Si `atlas-mvp-api` o
`atlas-mvp-frontend` pertenecen a una sesión activa, no los recrees ni detengas;
consulta al responsable de esa sesión antes de actualizar. No ejecutes pruebas de
GPU mientras haya otro trabajo usando la GPU.

La imagen API debe ser compatible con la arquitectura Linux ARM64, el driver y
NVIDIA Container Toolkit de esa PGX. No reutilices una imagen de otra arquitectura
sin comprobarla. El servicio `api` solicita `gpus: all`; no se añaden servicios
auxiliares.

## 5. Arrancar el MVP

El arranque recomendado ejecuta el preflight y construye el frontend:

```bash
MVP_BIND_HOST=127.0.0.1 scripts/run_mvp3_stack.sh
```

Para Compose directo, después de completar las verificaciones anteriores:

```bash
MVP_BIND_HOST=127.0.0.1 docker compose -f compose.mvp.yaml up --build
```

El comando habitual también se conserva cuando las imágenes ya están construidas:

```bash
MVP_BIND_HOST=127.0.0.1 docker compose -f compose.mvp.yaml up
```

El bind local restringe el acceso a PGX. Para acceso desde una LAN de confianza,
configura `MVP_BIND_HOST=0.0.0.0` conscientemente y aplica las reglas de red del
responsable; no publiques el servicio directamente en Internet.

## 6. Healthcheck y PMTiles HTTP Range

En otra terminal de PGX:

```bash
curl -fsS http://127.0.0.1:8080/healthz
curl -fsS http://127.0.0.1:8080/api/v1/health/live
curl -fsS http://127.0.0.1:8080/api/v1/health/ready
curl -fsS http://127.0.0.1:8080/api/v1/capabilities
curl -sS -D - -H 'Range: bytes=0-126' -o /dev/null \
  http://127.0.0.1:8080/map-assets/madrid.pmtiles
```

La respuesta Range esperada es `206 Partial Content` y
`Content-Range: bytes 0-126/1961605` para el archive actualmente documentado.
Comprueba el hash local contra el sidecar antes de servirlo:

```bash
test "$(sha256sum data/processed/map-assets/madrid.pmtiles | cut -d' ' -f1)" = \
  b267ebc4bb8de10e0ec0c7e6ba024793cb5ce0bc11dfb951cd6d9fe25541e093
```

No descargues ni regeneres PMTiles si el archive existente pasa sus verificaciones.

## 7. Probar SSE y una consulta real CrossText2Loc

Ejecuta una consulta únicamente cuando el runtime indique readiness y no haya otra
inferencia activa. Este comando abre el SSE primero, espera su evento de conexión
real, y después envía un POST real. La espera breve solo permite establecer HTTP;
no simula etapas ni progreso.

```bash
BASE=http://127.0.0.1:8080
QUERY_ID="pgx-$(date +%s)-$$"
SSE_FILE=$(mktemp)
RESULT_FILE=$(mktemp)
curl --no-buffer --silent --show-error \
  --max-time 600 \
  "$BASE/api/v1/progress/$QUERY_ID" > "$SSE_FILE" &
SSE_PID=$!
trap 'kill "$SSE_PID" 2>/dev/null || true; rm -f "$SSE_FILE" "$RESULT_FILE"' EXIT
for attempt in $(seq 1 50); do
  if grep -q '"event_type":"connected"' "$SSE_FILE"; then break; fi
  sleep 0.1
done
grep -q '"event_type":"connected"' "$SSE_FILE" || {
  echo 'No se estableció el SSE; no se enviará el POST de prueba.' >&2
  exit 1
}
curl -fsS -X POST "$BASE/api/v1/retrievals" \
  -H 'Content-Type: application/json' \
  --data-binary "{\"schema_version\":\"1.0\",\"contract_version\":\"atlas-experimental-retrieval-request-v2\",\"query\":{\"query_id\":\"$QUERY_ID\",\"text\":\"Estoy en una plaza amplia rodeada de edificios.\",\"language\":\"es\"},\"gallery_id\":\"madrid-50m\",\"processing_mode\":\"no_llm\",\"top_k\":10}" \
  > "$RESULT_FILE"
wait "$SSE_PID" || true
cat "$SSE_FILE"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); r=d["retrievals"][0]; assert len(r["results"]) == 10; print("Top-10 válido:",r["gallery_id"],len(r["results"]))' "$RESULT_FILE"
rm -f "$SSE_FILE" "$RESULT_FILE"
trap - EXIT
```

Los eventos deben llevar el `query_id` de esa consulta y secuencias crecientes.
CT2L informa codificación textual/ranking cuando el canal SSE se conecta a
tiempo; sin eventos, el POST aún debe devolver su contrato normal. Los tiempos no
son porcentajes. Cancelar `curl` solo cierra el cliente; no demuestra que la
inferencia haya sido detenida en FastAPI.

## 8. Probar Qwen opcional y revisar el mapa

Comprueba antes que Con LLM esté disponible:

```bash
curl -fsS http://127.0.0.1:8080/api/v1/capabilities \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(x for x in d["processing_modes"] if x["id"]=="with_llm"))'
```

Solo si está disponible y la GPU está libre, realiza **una** consulta de prueba
usando `processing_mode: "with_llm"`; la transformación Qwen corre antes de
CrossText2Loc. No hay fallback silencioso. El estado SSE debe mostrar Qwen
únicamente cuando el backend confirma su inicio y fin/error.

```bash
QWEN_QUERY_ID="pgx-llm-$(date +%s)-$$"
curl -fsS -X POST http://127.0.0.1:8080/api/v1/retrievals \
  -H 'Content-Type: application/json' \
  --data-binary "{\"schema_version\":\"1.0\",\"contract_version\":\"atlas-experimental-retrieval-request-v2\",\"query\":{\"query_id\":\"$QWEN_QUERY_ID\",\"text\":\"Estoy en una plaza amplia rodeada de edificios.\",\"language\":\"es\"},\"gallery_id\":\"madrid-50m\",\"processing_mode\":\"with_llm\",\"top_k\":10}"
```

Abre `http://127.0.0.1:8080/` en un navegador de PGX. Comprueba que se muestran
10 tarjetas, 10 marcadores, la celda seleccionada sincronizada y el Top-1
destacado. Prueba 3D solo si `capabilities`/mapa declara edificios 3D disponibles:
la extrusión es parcial y usa alturas OSM explícitas, no `building:levels`.
La similitud coseno no es una probabilidad y las celdas no confirman la posición
del observador.

El test completo opcional
`docker compose -f compose.mvp.yaml --profile test run --rm browser-check npm run test:browser:real`
ejecuta varias consultas con los modelos reales y consume GPU. Úsalo solo después
de confirmar que no hay otro proceso activo y con autorización para esa prueba.

## 9. Logs y parada

```bash
docker compose -f compose.mvp.yaml ps
docker compose -f compose.mvp.yaml logs --tail=100 api frontend
```

Cuando la consulta haya terminado y confirmes que estos servicios pertenecen a
esta sesión del MVP, detén únicamente este Compose project:

```bash
docker compose -f compose.mvp.yaml down
```

No uses `down -v`, `docker stop`, `docker rm` ni detengas contenedores por nombre
si no has verificado que son de esta ejecución.

## Estado conocido desde el checkout de desarrollo

La última auditoría local encontró F2, PBF F4, manifests F1, GeoJSON/PMTiles y el
clon CVG-Text fijado. En ese checkout faltaban checkpoint CrossText2Loc, CLIP,
Qwen3-8B y bundles visuales/embeddings; por tanto, no pudo ejecutarse allí una
consulta real. No fue posible autenticar por SSH al host PGX y no se conoce desde
esta sesión si sus artefactos o contenedores están presentes. Verifica esas rutas
en PGX antes de cualquier transferencia; esta guía no inicia descargas.
