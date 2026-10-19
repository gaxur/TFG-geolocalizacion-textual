# MVP.2: frontend real y mapa Leaflet

## Resultado

El frontend Vite usa exclusivamente la API MVP.1. No contiene fixtures, rutas
alternativas ni candidatos ficticios; un fallo del backend se muestra como un
error de servicio.

Módulos:

- `frontend/src/api.js`: fetch, timeout, cancelación y errores;
- `frontend/src/retrieval.js`: contratos F4.6 y adaptación sin reordenar;
- `frontend/src/map.js`: Leaflet, marcadores WGS84 y cleanup;
- `frontend/src/main.js`: estado, navegación y sincronización UI/mapa.

## Ejecutar el MVP completo

Los comandos siguientes se ejecutan desde la raíz del repositorio:

```bash
cd /home/dataai/Projects/TFG_Marcos/TFG-geolocalizacion-textual
```

Se necesitan dos terminales: una para la API con CrossText2Loc y otra para el
frontend Vite. No hay que ejecutar scripts de entrenamiento ni regenerar las
imágenes o embeddings.

### 1. Comprobaciones previas

Confirmar que la GPU está disponible y que existen la imagen Docker, el
checkpoint y los pesos base CLIP:

```bash
nvidia-smi
docker image inspect crosstext2loc-gb10:ngc26.02 --format '{{.Id}}'
test -f checkpoints/CrossText2Loc/long_model_NewYork-mixed_1e-05_128_osm_epoch30_59.08.pth
test -f "$HOME/.cache/clip/ViT-L-14-336px.pt"
```

Si la imagen Docker no existe, construirla una vez:

```bash
docker build \
  -f docker/crosstext2loc-gb10/Dockerfile \
  -t crosstext2loc-gb10:ngc26.02 \
  docker/crosstext2loc-gb10
```

### 2. Terminal 1: arrancar la API

Si el puerto 8000 está libre:

```bash
scripts/run_mvp1_api_docker.sh
```

La API quedará disponible en `http://127.0.0.1:8000`. La primera carga tarda
aproximadamente 5–6 segundos porque carga el checkpoint en GPU y las dos galerías.

En la PGX actual el puerto 8000 puede estar ocupado por otro servicio. En ese
caso no se debe detener el servicio ajeno; se utiliza, por ejemplo, el 18000:

```bash
ATLAS_API_PORT=18000 scripts/run_mvp1_api_docker.sh
```

Comprobar readiness desde otra terminal:

```bash
curl http://127.0.0.1:8000/api/v1/health/ready
```

O, si se usa el puerto alternativo:

```bash
curl http://127.0.0.1:18000/api/v1/health/ready
```

La respuesta esperada es:

```json
{"status":"ready","runtime":"crosstext2loc","gallery_ids":["madrid-50m","madrid-25m"]}
```

### 3. Terminal 2: instalar y arrancar el frontend

La primera vez, o cuando cambie `package-lock.json`:

```bash
npm --prefix frontend ci
```

Si la API usa el puerto 8000:

```bash
npm --prefix frontend run dev
```

Si la API usa el puerto 18000:

```bash
VITE_PROXY_TARGET=http://127.0.0.1:18000 \
  npm --prefix frontend run dev
```

Abrir en el navegador:

```text
http://127.0.0.1:5173/
```

La ruta `/` es la única experiencia de la aplicación. Los parámetros de consulta
antiguos no activan ningún modo alternativo.

### 4. Utilizar la aplicación

1. Escribir una descripción del entorno.
2. Elegir `Madrid · cuadrícula 50 m` o `Madrid · cuadrícula 25 m`.
3. Elegir Top-3, Top-5 o Top-10.
4. Pulsar **Buscar candidatos**.
5. Seleccionar una tarjeta o un marcador para consultar ID, coordenadas y
   similitud coseno.

El Top-1 se resalta visualmente, pero no representa una ubicación confirmada. La
similitud coseno tampoco es una probabilidad de acierto.

### 5. Parar la aplicación

En la terminal de Vite, pulsar `Ctrl+C`. En la terminal de la API, pulsar
`Ctrl+C`. El contenedor ejecuta el cierre del runtime y libera el modelo GPU.

Comprobar que no queda el contenedor:

```bash
docker ps --filter name=atlas-mvp1-api
```

### 6. Comando único (backend + frontend)

```bash
ATLAS_API_PORT=18000 ./scripts/run_mvp1_api_docker.sh & API_PID=$!; trap 'kill "$API_PID" 2>/dev/null; wait "$API_PID" 2>/dev/null' EXIT; VITE_PROXY_TARGET=http://127.0.0.1:18000 npm --prefix frontend run dev
```

### 7. Compilar y previsualizar la build

Compilar:

```bash
npm --prefix frontend run build
```

Previsualizar con API en el puerto 8000:

```bash
npm --prefix frontend run preview
```

Previsualizar con API en el puerto 18000:

```bash
VITE_PROXY_TARGET=http://127.0.0.1:18000 \
  npm --prefix frontend run preview
```

La preview queda normalmente en `http://127.0.0.1:4173/`.

### Diagnóstico rápido

- **`Bind ... 8000 failed: port is already allocated`**: usar
  `ATLAS_API_PORT=18000` y el mismo puerto en `VITE_PROXY_TARGET`.
- **Frontend muestra “Backend no disponible”**: comprobar `/health/ready` y que
  el proxy de Vite apunta al puerto correcto.
- **No aparecen teselas**: CrossText2Loc y los marcadores pueden seguir
  funcionando; revisar conexión y `VITE_TILE_URL`.
- **`RUNTIME_BUSY`**: esperar a que termine la consulta anterior. Cancelar en el
  navegador no detiene necesariamente una inferencia CUDA que ya haya comenzado.
- **La API aborta durante el arranque**: revisar que existan checkpoint, pesos
  CLIP, clones externos y bundles locales con los hashes esperados.

## Controles reales

- descripción en español;
- galería obtenida de `/api/v1/capabilities`;
- Top-3, Top-5 o Top-10;
- cancelación del navegador;
- resultados agrupados por galería;
- ID, rank, WGS84 y similitud coseno;
- Top-1 visualmente diferenciado.

Cancelar `fetch()` no cancela necesariamente la inferencia CUDA ya iniciada.

## Mapa

Leaflet recibe directamente `[latitude, longitude]`. Los marcadores y tarjetas
comparten una clave `gallery_id:candidate_id`. Antes de cada rerender se destruye
la instancia anterior mediante `map.remove()`.

Variables:

```text
VITE_TILE_URL
VITE_TILE_ATTRIBUTION
```

Por defecto se usa el endpoint público de OpenStreetMap con atribución. Es solo
para desarrollo local y no debe utilizarse para precarga o descarga masiva. Si
no hay proveedor disponible, una URL vacía deja un fondo neutro con marcadores.

## Validación

- 8 tests Node: PASS.
- Build Vite: PASS.
- HTTP real Vite proxy → FastAPI → CrossText2Loc: PASS.
- Galerías 50 m y 25 m: PASS.
- Consultas consecutivas con ranking idéntico: PASS.
- API con un solo proceso Uvicorn: comprobado.
- Browser-check visual: no ejecutado; no hay Chrome/Chromium instalado en la
  PGX ni `CHROME_PATH` configurado.

Por tanto, la integración HTTP real está validada, mientras que la verificación
visual automatizada de Leaflet queda pendiente para MVP.3 o un entorno con
navegador compatible.
