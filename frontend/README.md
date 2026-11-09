# Frontend del TFG

Interfaz web en español conectada a la API MVP.1. Está implementada con
JavaScript, CSS y Vite. MapLibre GL JS usa un PMTiles local generado desde la
fuente OSM F4 validada; Leaflet queda como fallback 2D si WebGL2 no está
disponible. La capa 3D solo extruye edificios con alturas numéricas explícitas
de OSM. Las geometrías de las celdas continúan siendo las celdas canónicas F1 de
25/50 m. Se recomienda Node.js 22.12 o superior.

## Despliegue integrado recomendado

Desde la raíz del repositorio:

```bash
scripts/run_mvp3_stack.sh -d
```

También se conserva el arranque directo solicitado:

```bash
docker compose -f compose.mvp.yaml up
```

`compose.mvp.yaml` compila el frontend con `npm ci` y `npm run build`, copia
`dist/` a una imagen Nginx y redirige `/api` al servicio FastAPI interno. Abrir:

```text
http://127.0.0.1:8080/
```

El wrapper escucha por defecto en la LAN. Desde otro dispositivo de la misma red
se abre `http://IP_LOCAL:8080/`. Para restringirlo a la propia PGX:

```bash
MVP_BIND_HOST=127.0.0.1 scripts/run_mvp3_stack.sh -d
```

Parar sin borrar datos:

```bash
docker compose -f compose.mvp.yaml down
```

El contenedor Nginx integrado utiliza el nombre estable `atlas-mvp-frontend`.

La API no publica un puerto y el navegador utiliza un único origen. Consultar
[`docs/MVP.md`](../docs/MVP.md) para variables, LAN,
healthchecks y diagnóstico.

## Desarrollo con Vite

Solo para desarrollo del frontend, arrancar MVP.1 en `127.0.0.1:8000` y ejecutar:

```bash
npm --prefix frontend ci
npm --prefix frontend run dev
```

Si la API escucha en otro puerto:

```bash
VITE_PROXY_TARGET=http://127.0.0.1:18000 npm --prefix frontend run dev
```

Abrir `http://127.0.0.1:5173/`.

## Funciones

- Descripción libre enviada al servicio interno.
- Selección exclusiva de galería 25 m o 50 m.
- Selección Sin LLM o Con LLM experimental (`en_cartographic`).
- Top-10 fijo para una sola combinación.
- Candidatos con ID, coordenadas WGS84 y similitud coseno.
- Mapa MapLibre 2D/3D con tarjetas/marcadores/celdas sincronizados; extrusión
  parcial solo para alturas OSM explícitas y numéricas.
- PMTiles locales servidos por el Nginx frontend existente; sin token ni API cartográfica externa.
- Fallback Leaflet 2D sin teselas externas cuando no hay WebGL2.
- Estados de carga, cancelación y errores del backend.
- Seguimiento por etapas con eventos SSE del backend, subfases medibles CT2L y
  fallback honesto al contrato síncrono cuando no llegan eventos.
- Historial local de consultas sin resultados completos.
- Vista adaptada a escritorio y móvil.

CrossText2Loc no produce una ubicación confirmada y su similitud no es una
probabilidad. El modo Con LLM no implica superioridad científica. No se ejecuta
Qwen3-VL en línea: si el postprocesador experimental opcional está habilitado, se
aplica evidencia visual precalculada. GOTPR, DialogueVPR en el endpoint HTTP y TOLoc no
están integrados en el MVP. La descripción se envía a la API interna; el mapa usa
recursos OSM locales y no solicita teselas a proveedores externos. No se deben
introducir datos sensibles en las consultas.

## Estructura

- `src/api.js`: transporte HTTP, timeout, cancelación y errores.
- `src/retrieval.js`: construcción y validación de los contratos F4.6.
- `src/pipeline.js`: estado por etapas, reductor de eventos y resultado terminal.
- `src/progress-stream.js`: conexión SSE por consulta y limpieza de listeners.
- `src/map.js`: MapLibre, PMTiles locales, celdas, edificios y fallback Leaflet.
- `src/map-data.js`: validación de metadatos/GeoJSON y unión por `candidate_id`.
- `src/main.js`: estado, navegación y sincronización de la interfaz.
- `src/minimal.css`: sistema visual responsive.

En Compose, `MVP_MAP_ASSETS_DIR` monta recursos locales de solo lectura en el
Nginx existente. La carpeta se prepara offline; no se generan teselas durante
`docker compose up`.

## Recursos cartográficos locales

Para regenerar GeoJSON directamente desde la cuadrícula F1 canónica, sin
atribuirla a un snapshot OSM, ejecutar desde la raíz:

```bash
python scripts/build_madrid_map_assets.py --regenerate-grid
```

El comando publica `cells-25m.geojson`, `cells-50m.geojson` y `map-assets.json`
en `data/processed/map-assets/`. Las coordenadas proceden del generador F1 en
EPSG:25830 y se publican en EPSG:4326. El manifest declara explícitamente
`osm_snapshot_id: null`; no reemplaza los manifests F4 del runtime.

Los manifests F1 y selecciones de las galerías están disponibles. Para repetir
esa validación sin tocar los GeoJSON F1 del directorio operativo, exporta a una
carpeta temporal:

```bash
python scripts/build_madrid_map_assets.py \
  --manifest-25m data/processed/catalog/manifest-25m.json \
  --manifest-50m data/processed/catalog/manifest-50m.json \
  --output-dir /tmp/madrid-map-assets-validation
```

MapLibre busca `data/processed/map-assets/madrid.pmtiles` y valida el encabezado,
la cobertura, las capas vectoriales, la provenance local y el tamaño servido
mediante HTTP Range. Si el archivo o su provenance no es válido, conserva la
vista de celdas/Top-10 y desactiva edificios 3D. No dibuja celdas aproximadas ni
asigna alturas por defecto.

El snapshot F2 está en `data/raw/osm/snapshots/<osm_snapshot_id>/`; su SHA-256
esperado se valida antes de la auditoría. La capa de mapa usa exclusivamente el
PBF F4 `data/raw/osm/f4_sources/madrid-geofabrik-20261014/source.osm.pbf`, no
mezcla ambos snapshots. Manifests F1 tienen `osm_snapshot_id: null`; se validan
contra las selecciones F4 y no se reemplazan.

Para reproducir la auditoría PBF y el build, instala las dependencias solo en un
entorno virtual externo al repositorio:

```bash
stamp=$(date -u +%Y%m%dT%H%M%SZ)
python -m venv "$HOME/.venvs/tfg-cartography"
"$HOME/.venvs/tfg-cartography/bin/python" -m pip install -r requirements-cartography.txt
"$HOME/.venvs/tfg-cartography/bin/python" scripts/audit_madrid_osm_pbf_buildings.py \
  --margin-m 250 --output "results/generated/madrid-osm-building-audit-f4-${stamp}.json"
"$HOME/.venvs/tfg-cartography/bin/python" scripts/build_madrid_pmtiles.py \
  --margin-m 250 --min-zoom 11 --max-zoom 17 \
  --output "${TMPDIR:-/tmp}/madrid-repro-${stamp}.pmtiles"
```

`requirements-cartography.txt` fija Osmium, Shapely, el encoder MVT y el writer
PMTiles. El build solo lee el PBF; genera las teselas fuera del arranque de
Compose y se niega a sobrescribir el archive o su provenance. El resumen real de
edificios, alturas, geometrías y área cubierta está en
[`docs/FRONTEND_MAPLIBRE.md`](../docs/FRONTEND_MAPLIBRE.md) y en los artefactos
`results/generated/madrid-osm-building-audit-f4-buffer250-final-v2-20261106.json` y
`data/processed/map-assets/madrid.pmtiles.provenance.json`.

## Verificación

```bash
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:browser
```

La prueba de navegador utiliza `CHROME_PATH` o busca Chrome/Chromium en rutas
habituales. Con el archive local presente, carga PMTiles real por HTTP Range,
GeoJSON F1 real, conmuta 2D/3D y sincroniza candidatos Top-10 de una API fake.
Valida software/cartografía local, no la API FastAPI real ni precisión científica.
También comprueba ausencia de solicitudes a proveedores cartográficos externos.
Si no existe un navegador compatible, las pruebas Node y la build siguen siendo
ejecutables.

En ARM64, `compose.mvp.yaml` proporciona Chromium aislado mediante el perfil
`test`; el smoke completo se ejecuta con `scripts/smoke_mvp3_stack.sh`.

La validación real de `docker compose -f compose.mvp.yaml up` y de Range en Nginx
se debe ejecutar en un host con Docker. No se declara validada en este checkout
Windows, que no tiene Docker CLI.
