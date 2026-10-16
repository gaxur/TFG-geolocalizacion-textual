# Atlas API — MVP.1

API HTTP interna y de un solo worker para `CrossText2LocRetriever`. No sirve el
frontend, no implementa F5 y no carga CUDA al importar módulos.

Arranque reproducible en Docker sobre la PGX:

```bash
scripts/run_mvp1_api_docker.sh
```

`scripts/run_mvp1_api.sh` es el entrypoint interno del contenedor.

Si el puerto 8000 está ocupado: `ATLAS_API_PORT=18000 scripts/run_mvp1_api_docker.sh`.

Parada: `Ctrl+C`. El lifespan espera la consulta activa y llama a `close()` una
sola vez.

Smoke de pila real:

```bash
ATLAS_API_PORT=18000 scripts/smoke_mvp1_stack.sh
```

Un fallo al cargar modelo, checkpoint o galerías aborta el proceso para que el
supervisor pueda reiniciarlo; no queda un servidor permanentemente no listo.

Endpoints:

```text
GET  /api/v1/health/live
GET  /api/v1/health/ready
GET  /api/v1/capabilities
POST /api/v1/retrievals
```
