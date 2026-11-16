# Remediación de PR3 para cierre de Fase 1

## Estado

`PR3_REMEDIATED_PENDING_REAL_E1_E3_VALIDATION`

No se ejecutaron modelos, no se abrió H38-H61 y no se incorporó VLM.

## Cambios

- Autorización operacional fail-closed ligada a policy, executor, modelo,
  configuración, scope, budgets, execution ID y expiración.
- Receipt persistente de consumo único previo a sesión/idempotencia.
- Locks `fcntl` de consumo y transición; budgets durables E0-E3.
- Revalidación antes de reservar y antes de cada ejecución.
- `/retrievals` preservado mediante Qwen/CT2L efímeros y secuenciales.
- Un único `model_gate` compartido por retrieval y DialogueVPR.
- Nginx FreeText unbuffered, keepalive/replay y timeout 900 s.
- Descripción libre alineada a 2.400 caracteres; respuestas a 1.200.
- HTTP 410, estados `unknown`, rankings/transcript/eventos persistentes intactos.

## Prueba real E1-E3 pendiente

Se requiere una autorización nueva y no reutilizable para una sesión nueva:

- máximo 4 Qwen y 4 CT2L;
- máximo 3 preguntas y 3 respuestas humanas;
- cero retries;
- pausa en cada `waiting_user`;
- recarga/recovery después de E1;
- ningún dato GT, VLM, referencia o H38-H61.

La sesión E0 histórica no se modifica ni continúa.
