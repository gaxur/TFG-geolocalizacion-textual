# Frontend del TFG

Interfaz web en español conectada a la API MVP.1. Está implementada con
JavaScript, CSS, Vite y Leaflet. Solo presenta recuperaciones reales de
CrossText2Loc; no contiene fixtures ni un modo de resultados sintéticos. Se
recomienda Node.js 22.12 o superior.

## Despliegue integrado recomendado

Desde la raíz del repositorio:

```bash
scripts/run_mvp3_stack.sh -d
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
- Mapa Leaflet con tarjetas y marcadores sincronizados.
- Estados de carga, cancelación y errores del backend.
- Historial local de consultas sin resultados completos.
- Vista adaptada a escritorio y móvil.

CrossText2Loc no produce una ubicación confirmada y su similitud no es una
probabilidad. El modo Con LLM no implica superioridad científica. No se ejecutan
GOTPR, VLM, diálogo ni TOLoc. Enviar la
descripción a la API interna y solicitar teselas al proveedor configurado puede
implicar tratamiento de datos; no se deben introducir datos sensibles.

## Estructura

- `src/api.js`: transporte HTTP, timeout, cancelación y errores.
- `src/retrieval.js`: construcción y validación de los contratos F4.6.
- `src/map.js`: mapa Leaflet y marcadores de candidatos.
- `src/main.js`: estado, navegación y sincronización de la interfaz.
- `src/minimal.css`: sistema visual responsive.

En Vite, las URLs se configuran mediante `frontend/.env.example`. En Compose,
las variables operativas y de teselas se documentan en `.env.mvp.example`; las
variables `VITE_TILE_*` se aplican al construir la imagen estática.

## Verificación

```bash
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:browser
```

La prueba de navegador utiliza `CHROME_PATH` o busca Chrome/Chromium en rutas
habituales. Comprueba el contrato HTTP, Leaflet, selección sincronizada y vista
móvil. Si no existe un navegador compatible, las pruebas Node y la build siguen
siendo ejecutables.

En ARM64, `compose.mvp.yaml` proporciona Chromium aislado mediante el perfil
`test`; el smoke completo se ejecuta con `scripts/smoke_mvp3_stack.sh`.
