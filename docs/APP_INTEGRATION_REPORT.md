# Informe de integración de la aplicación

## Estado

`APP_INTEGRATED_PENDING_D098_PROFILE_APPROVAL_AND_REAL_GPU_TEST`

La aplicación integra en una interfaz descripción libre, FreeText-v1, SSE, chat,
rankings E0-E3 y MapLibre. El perfil distribuido permanece `PENDING_APPROVAL`;
la infraestructura arranca, pero ninguna sesión ni inferencia puede iniciarse.

## Arquitectura

- `compose.app.yaml`: API FastAPI y frontend Nginx.
- Solo Nginx publica `127.0.0.1:18085`; API en red interna.
- Imagen API propia derivada de `crosstext2loc-gb10:f511`, sin datos/modelos.
- Qwen/CT2L efímeros secuenciales y un único `ModelGate`.
- SQLite WAL/FULL para cuotas, idempotencia y admisión reutilizable.
- Volumen persistente `atlas-app-state`.
- FastAPI y Nginx exponen solo rutas application/health/capabilities.

## Frontend

- Build `VITE_ATLAS_UI_MODE=app`.
- Formulario principal inicia FreeText application.
- Chat, progreso, recovery y rankings E0-E3.
- MapLibre montado en la app principal y actualizado sin recrear instancia.
- PMTiles/celdas locales; 3D solo con `height` numérica explícita.
- Controles científicos/raw ocultos.

## Seguridad y cuotas

- Perfil aprobado obligatorio, con expiry e identidad exacta.
- Cuotas globales derivadas y reserva 4 Qwen/4 CT2L/3 preguntas por sesión.
- Cero retries y cuotas inciertas no reembolsables.
- Loopback fijo y acceso recomendado por túnel SSH.
- GT, VLM, referencias y H38-H61 prohibidos.
- Recovery de respuesta perdida por operation ID sin repetir POST.

## Pendiente

- Aprobar D098 con profile ID, expiry, sesiones totales/abiertas y retención.
- Generar perfil hash-bound.
- Ejecutar una prueba GPU nueva explícitamente autorizada.
