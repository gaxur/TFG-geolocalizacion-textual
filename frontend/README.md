# Atlas — prototipo frontend del TFG

Prototipo navegable, en español, del sistema descrito en [PROJECT.md](../docs/PROJECT.md). Implementado con JavaScript, CSS y Vite; no necesita backend ni claves de API. Node.js 22.12 o superior recomendado.

El frontend es una demostración independiente de la implementación por fases.
La Fase 0 del backend ya define schemas, configuración y contratos, pero todavía
no existe una conexión HTTP ni se ejecuta recuperación real. El roadmap vigente
se resume en [TFG_COMPONENTS.md](../TFG_COMPONENTS.md) y las decisiones en
[DECISIONS.md](../docs/DECISIONS.md).

## Ejecutar

Desde esta carpeta:

```powershell
npm install
npm run dev
```

Abrir la dirección local que indique Vite (normalmente `http://127.0.0.1:5173`). Para compilar y revisar la versión de producción:

```powershell
npm run build
npm run preview
```

Si Windows/OneDrive bloquea el vaciado de `dist` con `EPERM`, puede compilarse con `npm run build -- --emptyOutDir false`. Esta opción conserva posibles assets antiguos; para una publicación final conviene generar una build limpia en una carpeta sin bloqueos de sincronización.

## Funciones del prototipo

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

## Qué no hace

No se ejecutan LLM, CrossText2Loc, GOTPR, VLM ni TOLoc. No se consulta OSM ni se descargan imágenes de Street View. Las ilustraciones de edificios son SVG originales y no constituyen evidencia visual. Las coordenadas de los ejemplos representan lugares, no posiciones estimadas del observador. El mapa es un esquema sin precisión cartográfica; no sirve para navegación. Las puntuaciones son sintéticas y no son probabilidades ni resultados del TFG.

La simulación usa seis lugares fijos y reglas de palabras clave para hacer recorribles los estados de interfaz. Su limitación a esos lugares no describe la capacidad esperada del sistema final. La comparación muestra la consulta inicial, sin aplicar las respuestas del diálogo. La latencia no se mide ni se inventan métricas experimentales. El selector visual solo cambia la presentación del estado previsto; no ejecuta reranking real.

La tipografía utiliza fuentes del sistema, sin descargar fuentes externas. Todo el contenido funcional de la demo está disponible sin APIs externas una vez servido. No introducir información sensible: las consultas permanecen en el navegador hasta borrarlas. No se envían descripciones a servidores. El enlace de cada ficha abre OpenStreetMap en una pestaña nueva.

## Estructura y futura conexión con Python

`src/demo.js` contiene los datos y la simulación. `src/main.js` coordina vistas y estado; `src/visuals.js` genera los SVG; `src/minimal.css` define el diseño.

## Ver la interfaz en móvil

En Chrome o Edge, abrir la aplicación, pulsar **F12** y después **Ctrl + Mayús + M**. Elegir un dispositivo o un ancho de **390 px**. Las vistas móviles se activan a partir de 720 px o menos. Para volver a escritorio, desactivar la barra de dispositivos.

Para probar desde un teléfono conectado a la misma red, ejecutar `npm run dev -- --host 0.0.0.0 --port 5175` y abrir `http://IP_LOCAL_DEL_PC:5175` desde el móvil. Puede ser necesario permitir el acceso en el cortafuegos. El servidor de desarrollo debe exponerse únicamente en una red de confianza; la URL `127.0.0.1` del PC no sirve desde el teléfono.

Para integrar el backend, sustituir la simulación de `runSearch` por un servicio HTTP compatible con los contratos versionados de `schemas/`: consulta, ámbito, recuperador, candidatos georreferenciados, puntuaciones con su significado, evidencias y estado de ejecución. Añadir cancelación de solicitudes, errores de red y streaming/polling si procede. El backend utilizará el proveedor LLM que se seleccione posteriormente detrás de una interfaz independiente; las claves nunca deben incluirse en el navegador.

Sustituir el esquema por una biblioteca cartográfica y una fuente autorizada con atribución. El diseño de fichas admite imágenes reales cuando se disponga de proveedor y evidencia trazable. El diálogo deberá usar preguntas y respuestas reales y no las reglas de esta demo. TOLoc se mantiene como extensión futura sin control que simule que ya funciona.

## Verificación

```powershell
npm test
npm run build
npm run test:browser
```

Los tests comprueban aislamiento geográfico, escenarios, ausencia de resultados y tratamiento de orientación. Para revisión manual: ejecutar cada ejemplo, cambiar método y ámbito, cancelar una búsqueda, responder al diálogo, abrir una ficha, exportar desde Comparar y recuperar/borrar el historial. Revisar también una ventana móvil de 390 px y navegación con Tab/Escape.

La prueba de navegador utiliza Chrome instalado en su ruta habitual de Windows (o la variable `CHROME_PATH`), abre un navegador invisible y sirve temporalmente la build en localhost. Comprueba los flujos principales y guarda capturas en `test-results/`. Debe ejecutarse después de compilar. Cierra sus procesos al terminar; deja un perfil temporal de prueba en la carpeta temporal del sistema.
