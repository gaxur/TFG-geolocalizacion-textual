# Informe de integración de la aplicación

## Estado

`APP_INTEGRATED_D098_V2_RESIDENT_E0_VALIDATED_E1_VALIDATION_FAILED`

La aplicación integra en una interfaz descripción libre, FreeText-v1, SSE, chat,
rankings E0-E3 y MapLibre. La plantilla distribuida permanece `PENDING_APPROVAL`;
el perfil real aprobado se genera fuera de Git y está ligado al runtime.

## Arquitectura

- `compose.app.yaml`: API FastAPI y frontend Nginx.
- Solo Nginx publica `127.0.0.1:8080`; API en red interna.
- Imagen API propia derivada de `crosstext2loc-gb10:f511`, sin datos/modelos.
- Qwen/CT2L residentes lazy, estrictamente secuenciales y un único `ModelGate`;
  no se cargan al arrancar Compose.
- Policy core application separada sobre la implementación FreeText compartida;
  declara stop temprano sin modificar la policy científica.
- SQLite WAL/FULL para cuotas, idempotencia y admisión reutilizable.
- Volumen persistente `atlas-app-state`.
- FastAPI y Nginx exponen solo rutas application/health/capabilities.

## Frontend

- Build `VITE_ATLAS_UI_MODE=app`.
- Formulario principal inicia FreeText application.
- Chat, progreso, recovery y rankings E0-E3.
- MapLibre montado en la app principal y actualizado sin recrear instancia.
- PMTiles/celdas locales; 3D con `height` explícita y estimaciones visuales
  diferenciadas (`levels × 3 m` o 9 m), nunca usadas por retrieval.
- Controles científicos/raw ocultos.

## Seguridad y cuotas

- Perfil aprobado obligatorio, con expiry e identidad exacta.
- Cuotas globales derivadas y reserva 4 Qwen/4 CT2L/3 preguntas por sesión.
- Cero retries y cuotas inciertas no reembolsables.
- Loopback fijo y acceso recomendado por túnel SSH.
- GT, VLM, referencias y H38-H61 prohibidos.
- Recovery de respuesta perdida por operation ID sin repetir POST.

## Pendiente

- Solicitar autorización nueva solo si el agente debe repetir el smoke GPU. Las
  búsquedas iniciadas por el operador desde el frontend siguen autorizadas por
  D098 durante la vigencia del perfil.
