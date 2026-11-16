# Pruebas de remediación PR3

## Backend

```text
58 passed
1 warning: deprecación TestClient/httpx existente
```

Incluye autorización negativa, consumo único, concurrencia, crash/restart,
budgets E0-E3, expiry/tamper, idempotencia, HTTP 410, retrieval independiente,
gate compartido y workers efímeros.

## Frontend

```text
41 passed
1 skipped: PMTiles real externo ausente en worktree temporal
```

## Integración

- Vite build: PASS.
- Chromium operacional fake: `FREETEXT_OPERATIONAL_BROWSER_PASS`.
- Nginx+Chromium real sin GPU: `FREETEXT_NGINX_INTEGRATION_PASS`.
- `nginx -t`: PASS.
- `nginx -T`: PASS.
- Compose config MVP/test: PASS.
- `py_compile`: PASS.
- `git diff --check`: PASS.

No se ejecutaron Qwen, CT2L, VLM ni campañas de evaluación.
