# Resultados de pruebas de la aplicación

- Backend/API/admisión/Compose/regresiones: `83 passed`.
- Frontend: `48 passed`, `1 skipped` por PMTiles unitario opcional.
- Vite build: PASS con warning de chunk MapLibre existente.
- `APP_DISABLED_BROWSER_PASS`: stack real, perfil pendiente, MapLibre y cero POST.
- `APP_FLOW_BROWSER_PASS`: API fake, creación, Q1-Q3, E0-E3, mapa estable y recarga.
- `FREETEXT_NGINX_INTEGRATION_PASS`: SSE incremental/replay/GET.
- `nginx -t`, Compose config, `py_compile` y `git diff --check`: PASS.

Los fakes validan integración y contratos, no inferencia real. No se cargaron
Qwen, CrossText2Loc ni VLM en esta integración.

## Prueba GPU autorizada

- Sesión: `freetext-application-7cf633c5-bf33-4acf-9aa7-a0841e0c8c19`.
- Resultado: `failed`, `runtime_error_no_retry`, antes de cargar Qwen.
- Reserva durable: E0, 1 Qwen, 1 CT2L y 1 pregunta; sin refund ni retry.
- Causa: resource gate no pudo consultar Ollama desde la red interna (`URLError`).
- Modelos residentes después del fallo: ninguno.
- Corrección posterior: sidecar allowlist `resource-monitor` para `/api/ps`.
- Repetición automatizada por el agente: no ejecutada; requiere autorización
  nueva. El uso interactivo iniciado por el operador sigue cubierto por D098.

Una sesión interactiva posterior iniciada por el operador verificó el fix del
resource monitor y completó E0: 134,813 s, 253 candidatos exhaustivos, Top-10 y
primera pregunta. Qwen ocupó 119,296 s por eventos (3,046 s de generación) y
CrossText2Loc 15,491 s. El agente no la respondió. Antes del runtime residente,
la sesión se archivó íntegramente (manifest `a06e6401…`) y quedó `unknown` con
motivo `runtime_identity_superseded_no_retry`; no es completed ni failed. E1-E3
no se revalidaron.

## Runtime residente v2

- Perfil: `freetext-application-pgx-20261116-v2`.
- Executor identity SHA-256: `6f7adaab8e667cc66fea0cbd1c43f5e019d478fb3da6faee74a95a0e507048d6`.
- Startup: readiness `resident-sequential-lazy-v1`, cero POST y cero modelos.
- CPU: cargas fake Qwen/CT2L únicas, cache hits E1, cierre, contratos CT2L,
  supersession e idempotencia.
- GPU: no ejecutada; no se afirma todavía reducción real ni convivencia en RAM.
