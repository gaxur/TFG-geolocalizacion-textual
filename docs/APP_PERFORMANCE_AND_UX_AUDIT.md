# Auditoría de rendimiento y experiencia de la aplicación

## Alcance

La auditoría compara el MVP residente con la aplicación FreeText integrada sin
ejecutar una inferencia nueva. Se usó en lectura una sesión iniciada por el
operador y ya persistida en `atlas-app-state`. No se respondió esa sesión ni se
abrió GT, VLM o H38-H61.

## Medición E0 real

Sesión observada:
`freetext-application-599db399-b8d3-48bd-a172-0fd7628d342a`.

| Componente | Tiempo observado | Evidencia |
|---|---:|---|
| E0 completo | 134,813 s | `latency_ms.transitions` |
| Qwen, eventos running→completed | 119,296 s | eventos 3–4 |
| Generación Qwen interna | 3,046 s | `freetext-en-0.json` |
| Carga de pesos Qwen | ~93 s | supervisor, 399 pesos |
| CrossText2Loc, eventos running→completed | 15,491 s | eventos 5–6 |
| Resource gates mínimos | 16 s/E0 | dos gates, 5 muestras y 4 esperas de 2 s |
| Ranking | 253 candidatos; Top-10 público | `ranking-0.json` y sesión pública |

Los eventos demuestran que el Top-10 y la primera pregunta existían en backend
al terminar E0. La ausencia percibida procedía del recovery/frontend, que no
reabría SSE tras recargar una sesión `pending/running` y ocultaba errores.

## Diferencia con el MVP original

El MVP original mantenía CrossText2Loc y, si se habilitaba, Qwen residentes en el
lifespan de FastAPI. La aplicación integrada usa procesos efímeros por etapa para
garantizar liberación de GPU:

- hasta cuatro cargas Qwen;
- hasta cuatro cargas CrossText2Loc;
- dos resource gates por etapa;
- persistencia durable e idempotencia adicionales.

La búsqueda exhaustiva residente de CrossText2Loc está históricamente en
milisegundos; la mayor diferencia actual es la carga/descarga de modelos, no la
similitud coseno ni el catálogo.

## Decisión de optimización

No se cambió aún a modelos residentes. Ese cambio afecta memoria, ejecutor e
identidad hash-bound D098. Requiere instrumentación backend, regenerar el perfil
y una autorización explícita antes de otra prueba GPU. La opción prioritaria a
evaluar es un único worker secuencial que reutilice Qwen y CT2L sin concurrencia;
no se afirmará mejora hasta medirla.

## Correcciones funcionales

- Recovery reabre SSE para sesiones `pending/running`.
- Reconexiones quedan ligadas a generación y `session_id`.
- Errores FreeText son visibles.
- La operation ID se elimina tras creación confirmada.
- Una sesión terminal ofrece «Nueva búsqueda» sin borrar estado backend.
- E0 cambia a mapa/resultados en móvil y conserva el último ranking válido.
- El mapa es dominante; DialogueVPR queda en sidebar o panel móvil.

## Política 3D visual

La capa MapLibre usa, en orden:

1. `height` OSM numérica explícita;
2. `building:levels × 3 m` como estimación visual;
3. 9 m como fallback visual.

`min_height` se respeta cuando existe. Colores diferentes distinguen altura
explícita, niveles y fallback. La regla solo afecta al estilo MapLibre: no cambia
PMTiles, catálogo, asociaciones, embeddings ni rankings. Chromium observó 4.800
extrusiones visibles y 8.031 features fuente en la cámara del despliegue final.
El recuento varía con teselas, zoom y encuadre y no es un censo de edificios.

## Evidencia visual

- [Escritorio con MapLibre 3D](screenshots/integrated-app-desktop-3d.png).
- [Vista móvil responsive](screenshots/integrated-app-mobile.png).

Las capturas fueron producidas por Chromium sobre la sesión persistida, sin POST
ni inferencia. La comprobación automática validó dimensiones, ausencia de
overflow, Top-10, pregunta, canvas y extrusiones; este agente no dispone de
capacidad de inspección visual de píxeles, por lo que queda pendiente la revisión
humana estética desde Windows.
