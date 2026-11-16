# Auditoría integral de fallos FreeText application

## Estado observado

El ledger local contiene sesiones v1/v2 `failed`, una supersedida `unknown`,
varias sesiones v2 `completed` E3 y una sesión en curso. El patrón no es un fallo
general de GPU: existen recorridos E0–E3 completos con el mismo runtime residente.

En el ledger local no versionado se observaron tres fallos v2 Qwen E1/E3:
`5f0b0122…`, `303bd662…` y `5f475b9b…`; y tres recorridos E3 completados:
`e6fcc120…`, `70f3c18e…` y `214fc110…`. Son observaciones locales, no artefactos
versionados. El caso `5f0b0122…` auditado en detalle está en
[FREETEXT_E1_QWEN_FAILURE_AUDIT.md](FREETEXT_E1_QWEN_FAILURE_AUDIT.md).

## Fronteras de fallo

| Frontera | Estado | Irreversible | Ranking conservado | Recuperación |
|---|---|---|---|---|
| Validación request/perfil | HTTP 4xx/503 | No | Todos | Corregir entrada/perfil |
| ModelGate ocupado | HTTP 409 | No | Todos | Reintento manual posterior seguro |
| Persistencia tras admisión | `unknown` | Admisión | Último durable | No retry automático |
| Reserva E0–E3 | `unknown/failed` | Cuota stage | Etapas anteriores | No refund/retry |
| Qwen gate/load/generate | `failed` | Stage reservado | Etapas anteriores | Nueva sesión |
| Qwen validación | `failed` | Qwen ejecutado | Etapas anteriores | Nueva sesión; CT2L no corre |
| CT2L load/retrieval/contrato | `failed` | Qwen+stage | Etapas anteriores | Nueva sesión |
| Crash/restart en running | `unknown` | Operación incierta | Último durable | No reanudación |
| SSE/red navegador | No cambia backend | No adicional | Todos | GET + cursor SSE |

## Defectos demostrados del validador general

- Mezcla incapacidad de comprobar con negación factual.
- No reconoce equivalencias como `unable to verify` o `can't confirm`.
- No protege `parada de metro` y otras entidades de diálogo.
- Comprueba direcciones solo contra pérdidas, no adiciones contradictorias.
- Trata invenciones geográficas como warning.
- Compara números/unidades con grafía demasiado estricta.
- No rechaza metacomentarios de forma completa.

## Propuesta no implementada

Se propone un validador separado del histórico F5:

- incapacidad/incertidumbre separada de negación factual;
- entidades y direcciones bidireccionales;
- números/unidades normalizados;
- formato sin metacomentarios;
- sidecar de rechazo con output, issues, hashes e identidad;
- `not_used_for_retrieval=true` y CT2L nunca llamado tras rechazo;
- mismo control en runtime residente y worker efímero;
- error público saneado `FREETEXT_TRANSFORMATION_REJECTED`.

La propuesta alteraría `src/` y `backend/`, por tanto cambiaría la identidad D098.
No está implementada ni desplegada: la revisión detectó que requiere antes un
contrato de alcance semántico, privacidad/retención y sanitización SSE.
