# Resultados de pruebas de la aplicación

- Backend/API/admisión/Compose/regresiones: `79 passed`.
- Frontend: `45 passed`, `1 skipped` por PMTiles unitario opcional.
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
