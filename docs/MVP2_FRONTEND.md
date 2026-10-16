# MVP.2: frontend real y mapa Leaflet

## Resultado

El frontend Vite usa por defecto la API MVP.1 y conserva la simulación solo en
`?mode=demo`. El modo real no publica candidatos ficticios ni activa la demo si
falla el backend.

Módulos:

- `frontend/src/api.js`: fetch, timeout, cancelación y errores;
- `frontend/src/retrieval.js`: contratos F4.6 y adaptación sin reordenar;
- `frontend/src/map.js`: Leaflet, marcadores WGS84 y cleanup;
- `frontend/src/main.js`: estado, navegación y sincronización UI/mapa.

## Ejecución de desarrollo

Arrancar MVP.1:

```bash
scripts/run_mvp1_api_docker.sh
```

Arrancar Vite:

```bash
cd frontend
npm ci
npm run dev
```

El proxy `/api` apunta por defecto a `http://127.0.0.1:8000`. Puede cambiarse
mediante `VITE_PROXY_TARGET`.

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

- 12 tests Node: PASS.
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
