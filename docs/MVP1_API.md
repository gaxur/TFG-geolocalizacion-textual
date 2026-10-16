# MVP.1: API HTTP interna

## Alcance

MVP.1 añade una capa FastAPI fina sobre `CrossText2LocRetriever`. No modifica el
runtime, el checkpoint, las galerías ni el ranking; tampoco integra todavía el
frontend.

## Endpoints

```text
GET  /api/v1/health/live
GET  /api/v1/health/ready
GET  /api/v1/capabilities
POST /api/v1/retrievals
```

El POST consume y devuelve directamente los contratos F4.6. Las similitudes son
coseno, no probabilidades.

## Arranque en PGX

La imagen `crosstext2loc-gb10:ngc26.02` incluye FastAPI 0.115.14 y Uvicorn
0.34.3. El wrapper publica solo localhost y ejecuta un único worker:

```bash
scripts/run_mvp1_api_docker.sh
```

Para otro puerto: `ATLAS_API_PORT=18000 scripts/run_mvp1_api_docker.sh`.

El puerto 8000 estaba ocupado durante el smoke por un servicio ajeno, por lo que
la validación real se ejecutó en `127.0.0.1:18000` sin detener ese servicio.

Parada: `Ctrl+C` o señal SIGTERM. El lifespan espera la consulta activa y llama
a `close()` una sola vez.

## Petición

```bash
curl -X POST http://127.0.0.1:8000/api/v1/retrievals \
  -H 'Content-Type: application/json' \
  -d '{
    "schema_version":"1.0",
    "contract_version":"crosstext2loc-retrieval-request-v1",
    "query":{"query_id":"browser-001","text":"Una avenida amplia junto a un parque verde","language":"es"},
    "gallery_ids":["madrid-50m"],
    "top_k":5
  }'
```

## Ciclo de vida y concurrencia

- El lifespan carga una sola instancia del modelo y ambas galerías.
- Las peticiones ejecutan la inferencia síncrona en un thread de AnyIO.
- Un lock HTTP pequeño rechaza con `RUNTIME_BUSY` una segunda inferencia activa.
- Liveness sigue respondiendo durante una consulta.
- No deben usarse varios workers Uvicorn.
- Readiness no intenta reparar ni recargar el runtime.
- Un fallo de startup aborta Uvicorn; no se mantiene un proceso degradado.

## Errores

| Caso | HTTP | Código |
|---|---:|---|
| Body inválido | 422 | `INVALID_REQUEST` |
| Input de retrieval inválido | 422 | `INVALID_RETRIEVAL_INPUT` |
| Galería desconocida | 404 | `GALLERY_NOT_FOUND` |
| Runtime no listo | 503 | `RUNTIME_NOT_READY` |
| Runtime ocupado | 503 | `RUNTIME_BUSY` |
| Runtime cerrado | 503 | `RUNTIME_CLOSED` |
| Inferencia fallida | 503 | `INFERENCE_FAILED` |
| Error inesperado | 500 | `INTERNAL_ERROR` |

Las respuestas no contienen trazas, paths ni detalles CUDA. Cada respuesta
incluye `X-Request-ID`.

## Smoke real GB10

Artefacto local: `results/generated/mvp1/http-smoke.json`.

Se comprobó:

- liveness y readiness;
- capabilities reales;
- Top-10 en 25 m y 50 m;
- petición multigalería;
- dos consultas sucesivas sin recarga;
- igualdad exacta con rankings F4.4;
- errores 422 y 404;
- propagación del request ID;
- parada limpia y ausencia de contenedor residual.

El smoke de pila automatizado arrancó un único worker, esperó readiness, ejecutó
las peticiones y envió SIGTERM. Su primera consulta multigalería tardó 149,43 ms.
La carga del runtime medida en F4.6 fue aproximadamente 5,6 s. Son observaciones,
no SLA.

```bash
ATLAS_API_PORT=18000 scripts/smoke_mvp1_stack.sh
```

## Tests

Los tests HTTP usan `FakeRetriever`, no importan Torch ni necesitan GPU. Cubren
lifespan, endpoints, contratos, errores, reutilización, busy y cierre.

## Pendiente para MVP.2

- Cliente HTTP del frontend.
- Estados remotos y cancelación.
- Selector de galería/Top-K.
- Marcadores WGS84 sobre mapa real.
- Separación inequívoca entre demo y modo real.
