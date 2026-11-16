# Informe de remediación de PR3

## Estado

`PR3_REMEDIATED_PENDING_REAL_E1_E3_VALIDATION`

No se ejecutaron modelos reales, no se abrió H38-H61 y no se incorporó VLM ni
verificador OSM.

## Autorización operacional

- `ATLAS_FREETEXT_OPERATIONAL_ENABLED=true` ya no autoriza inferencias.
- Son obligatorios authorization root y execution ID server-side.
- El archivo exacto debe estar aprobado, vigente y ligado a hashes de policy,
  executor, árboles de código, Python, Qwen snapshot, CLIP, F3 y configuración.
- Scope fijo: una sesión E0-E3, cuatro loads/calls Qwen, cuatro CT2L, tres
  preguntas y cero retries.
- Receipt persistente de consumo único con estados `reserved` y `bound`.
- Crash antes de sesión reconstruye únicamente la misma reserva exacta.
- Receipt ligado con sesión ausente queda `unknown/uncertain`, sin reutilización.
- Revalidación antes de reservar y ejecutar cada etapa.
- Locks `fcntl` de consumo y transición; gate de modelo reservado antes del
  consumo de autorización.
- Authorization, receipt, budgets, executor identity y execution ID no se
  exponen en respuestas públicas.

## API unificada

`/retrievals` permanece disponible en la misma aplicación. En modo operacional
usa proveedores efímeros:

- `no_llm`: CT2L en proceso hijo.
- `with_llm`: Qwen termina y sale antes de iniciar CT2L.
- Retrieval y FreeText comparten un único `model_gate`.
- Todos los workers configuran `PDEATHSIG` para no sobrevivir al API padre.
- Se conserva el contrato de ranking exhaustivo; Top-K solo afecta presentación.

## Nginx y SSE

La ruta `/api/v1/dialogue-freetext/` usa HTTP/1.1, `Connection ""`, buffering y
cache deshabilitados y timeouts de 900 s. El harness Nginx+Chromium real verificó:

- primera entrega SSE incremental;
- keepalive;
- desconexión forzada;
- replay `after=2`;
- reconciliación GET;
- una sola creación POST;
- descripción de 2.400 caracteres.

Resultado: `FREETEXT_NGINX_INTEGRATION_PASS`.

## Contrato de longitud

Descripción operacional: 3-2.400 caracteres en FastAPI, JavaScript y UI.
Respuestas: 1-1.200 caracteres. Una entrada 2.401 se rechaza antes de receipt,
idempotencia, sesión o executor.

## Persistencia

Se mantienen escritura atómica, `Idempotency-Key`, reserva previa, HTTP 410,
estado `unknown`, rankings E0-E3, transcript literal y eventos persistentes.
La sesión E0 histórica no se modificó y no se continúa.

## Validación

- Backend/API/autorización/concurrencia/retrieval/dialogue: 60 PASS.
- Frontend: 41 PASS, 1 skip por PMTiles externo ausente.
- Vite build: PASS con warning de chunk existente.
- Chromium operacional: PASS.
- Nginx+Chromium integrado: PASS.
- `nginx -t`/`nginx -T`: PASS en red con fixture API.
- Compose MVP y Compose test: PASS.
- `py_compile`: PASS.
- `git diff --check`: PASS.

## Pendiente

Solo falta una validación real nueva E1-E3 con autorización separada, preguntas
reales y tres respuestas humanas. PR3 no debe fusionarse como Fase 1 completa
antes de esa prueba.
