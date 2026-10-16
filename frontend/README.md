# Atlas — prototipo frontend del TFG

Interfaz web, en español, del sistema descrito en [PROJECT.md](../docs/PROJECT.md). Implementada con JavaScript, CSS, Vite y Leaflet. El modo real consume la API MVP.1; la demo histórica permanece aislada mediante `?mode=demo`. Node.js 22.12 o superior recomendado.

El frontend es una demostración independiente de la implementación por fases.
MVP.2 conecta el frontend con FastAPI y CrossText2Loc. El roadmap vigente
se resume en [TFG_COMPONENTS.md](../TFG_COMPONENTS.md) y las decisiones en
[DECISIONS.md](../docs/DECISIONS.md).

## Ejecutar

Desde esta carpeta:

```powershell
npm install
npm run dev
```

Arrancar primero MVP.1 en `127.0.0.1:8000`. Vite redirige `/api` al backend. Abrir la dirección local que indique Vite (normalmente `http://127.0.0.1:5173`). Para compilar y revisar la versión de producción:

```powershell
npm run build
npm run preview
```

Si Windows/OneDrive bloquea el vaciado de `dist` con `EPERM`, puede compilarse con `npm run build -- --emptyOutDir false`. Esta opción conserva posibles assets antiguos; para una publicación final conviene generar una build limpia en una carpeta sin bloqueos de sincronización.

## Funciones del modo real

- Descripción libre enviada al servicio interno.
- Galerías de 25 m y 50 m obtenidas mediante `/capabilities`.
- Top-3, Top-5 o Top-10.
- Candidatos reales con ID, WGS84 y similitud coseno.
- Mapa Leaflet con selección sincronizada y Top-1 diferenciado.
- Estados de carga, cancelación y errores del backend.
- Historial local de consultas, sin almacenar resultados completos.

## Demo explícita

- Descripción libre, ejemplos, zona aproximada y selección de CrossText2Loc/GOTPR.
- Estados de búsqueda, cancelación, validación y ausencia de candidatos.
- Mapa SVG ilustrativo con selección sincronizada de tarjetas y marcadores, zoom y capa de ámbito.
- Fichas de candidatos con coordenadas, pistas, evidencias, incertidumbre y enlace a OpenStreetMap.
- Comparación de variantes con consulta y ámbito comunes; puntuaciones sintéticas explícitas.
- Diálogo simulado con respuesta y reordenamiento de ejemplo.
- Ajustes de Top-K, diálogo y presentación del estado de verificación visual.
- Historial de las últimas doce consultas en `localStorage`, recuperación y borrado con confirmación.
- Exportación JSON de una sesión y su comparación, marcada como simulación.
- Diseño minimalista con navegación única, opciones técnicas plegables, navegación por teclado y ventanas modales nativas.
- En móvil, vistas separadas de descripción y mapa/resultados; al finalizar una búsqueda se muestran sus resultados automáticamente.

La demo antigua se abre con `/?mode=demo` y nunca se activa automáticamente por un fallo del backend.

## Qué no hace

No se ejecutan LLM, GOTPR, VLM ni TOLoc. CrossText2Loc no produce una ubicación confirmada y la similitud no es una probabilidad. No hay ground truth, preselección OSM, diálogo real ni verificación visual.

La simulación usa seis lugares fijos y reglas de palabras clave exclusivamente en
`?mode=demo`. Su comparación, diálogo y evidencias siguen siendo ilustrativos.

La tipografía utiliza fuentes del sistema. En modo real, la descripción se envía a la API interna; no introducir datos sensibles. Leaflet puede solicitar teselas al proveedor configurado y muestra su atribución.

## Estructura y futura conexión con Python

`src/api.js` implementa HTTP, `src/retrieval.js` adapta contratos, `src/map.js` gestiona Leaflet, `src/demo.js` conserva fixtures y `src/main.js` coordina vistas/estado.

## Ver la interfaz en móvil

En Chrome o Edge, abrir la aplicación, pulsar **F12** y después **Ctrl + Mayús + M**. Elegir un dispositivo o un ancho de **390 px**. Las vistas móviles se activan a partir de 720 px o menos. Para volver a escritorio, desactivar la barra de dispositivos.

Para probar desde un teléfono conectado a la misma red, ejecutar `npm run dev -- --host 0.0.0.0 --port 5175` y abrir `http://IP_LOCAL_DEL_PC:5175` desde el móvil. Puede ser necesario permitir el acceso en el cortafuegos. El servidor de desarrollo debe exponerse únicamente en una red de confianza; la URL `127.0.0.1` del PC no sirve desde el teléfono.

El modo real usa los contratos F4.6, errores HTTP, cancelación de espera y un mapa
Leaflet. La URL de API y la fuente de teselas se configuran en `.env.example`.
Diálogo, LLM, evidencias visuales y TOLoc permanecen fuera del modo real.

## Verificación

```powershell
npm test
npm run build
npm run test:browser
```

Los tests comprueban aislamiento geográfico, escenarios, ausencia de resultados y tratamiento de orientación. Para revisión manual: ejecutar cada ejemplo, cambiar método y ámbito, cancelar una búsqueda, responder al diálogo, abrir una ficha, exportar desde Comparar y recuperar/borrar el historial. Revisar también una ventana móvil de 390 px y navegación con Tab/Escape.

La prueba de navegador usa `CHROME_PATH` o busca Chrome/Chromium en rutas
habituales. Sirve una API fake same-origin y teselas offline para comprobar modo
real, contrato, Leaflet, móvil y separación de la demo. En la PGX actual no se
encontró un navegador compatible, por lo que esta prueba quedó bloqueada.
