# Atlas API — MVP.1

API HTTP interna y de un solo worker para `CrossText2LocRetriever`. No implementa
F5 y no carga CUDA al importar módulos. En el despliegue integrado la sirve
indirectamente Nginx mediante `/api`; su puerto no se publica en el host.

## Despliegue integrado recomendado

Desde la raíz:

```bash
scripts/run_mvp3_stack.sh -d
```

Esto utiliza `compose.mvp.yaml`, espera el healthcheck
`/api/v1/health/ready` y expone únicamente Nginx en el puerto 8080. Desde la PGX
se usa `http://127.0.0.1:8080/`; desde la LAN, `http://IP_LOCAL:8080/`. Estado,
logs y parada:

```bash
docker compose -f compose.mvp.yaml ps
docker compose -f compose.mvp.yaml logs api
docker compose -f compose.mvp.yaml down
```

El contenedor integrado utiliza el nombre estable `atlas-mvp-api`.

La guía completa está en
[`docs/MVP.md`](../docs/MVP.md).

## Ejecución aislada de MVP.1

Para desarrollar o diagnosticar solo la API:

```bash
scripts/run_mvp1_api_docker.sh
```

`scripts/run_mvp1_api.sh` es el entrypoint interno del contenedor.

Si el puerto 8000 está ocupado:
`ATLAS_API_PORT=18000 scripts/run_mvp1_api_docker.sh`. Este puerto alternativo
no es necesario en `compose.mvp.yaml`, porque FastAPI solo usa la red interna.

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
