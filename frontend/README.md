# Frontend del TFG

Interfaz web en español conectada a la API MVP.1. Está implementada con
JavaScript, CSS, Vite y Leaflet. Solo presenta recuperaciones reales de
CrossText2Loc; no contiene fixtures ni un modo de resultados sintéticos. Se
recomienda Node.js 22.12 o superior.

## Ejecutar

Arrancar primero MVP.1 en `127.0.0.1:8000` y, desde la raíz:

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
- Galerías de 25 m y 50 m obtenidas mediante `/api/v1/capabilities`.
- Selección de Top-3, Top-5 o Top-10.
- Candidatos con ID, coordenadas WGS84 y similitud coseno.
- Mapa Leaflet con tarjetas y marcadores sincronizados.
- Estados de carga, cancelación y errores del backend.
- Historial local de consultas sin resultados completos.
- Vista adaptada a escritorio y móvil.

CrossText2Loc no produce una ubicación confirmada y su similitud no es una
probabilidad. No se ejecutan LLM, GOTPR, VLM, diálogo ni TOLoc. Enviar la
descripción a la API interna y solicitar teselas al proveedor configurado puede
implicar tratamiento de datos; no se deben introducir datos sensibles.

## Estructura

- `src/api.js`: transporte HTTP, timeout, cancelación y errores.
- `src/retrieval.js`: construcción y validación de los contratos F4.6.
- `src/map.js`: mapa Leaflet y marcadores de candidatos.
- `src/main.js`: estado, navegación y sincronización de la interfaz.
- `src/minimal.css`: sistema visual responsive.

Las URLs de API y teselas se configuran mediante las variables descritas en
`.env.example`.

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
