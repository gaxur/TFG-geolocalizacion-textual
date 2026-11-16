# Resultados de pruebas de la aplicación

- Backend/API/admisión/Compose/regresiones: `72 passed`.
- Frontend: `45 passed`, `1 skipped` por PMTiles unitario opcional.
- Vite build: PASS con warning de chunk MapLibre existente.
- `APP_DISABLED_BROWSER_PASS`: stack real, perfil pendiente, MapLibre y cero POST.
- `APP_FLOW_BROWSER_PASS`: API fake, creación, Q1-Q3, E0-E3, mapa estable y recarga.
- `FREETEXT_NGINX_INTEGRATION_PASS`: SSE incremental/replay/GET.
- `nginx -t`, Compose config, `py_compile` y `git diff --check`: PASS.

Los fakes validan integración y contratos, no inferencia real. No se cargaron
Qwen, CrossText2Loc ni VLM en esta integración.
