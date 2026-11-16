# Plan de ejecución real E1-E3

Estado: `PREPARED_PENDING_SEPARATE_AUTHORIZATION`.

## Alcance

- Sesión nueva; no reutilizar E0 histórica.
- Descripción española libre de hasta 2.400 caracteres.
- Máximo 4 Qwen y 4 CT2L, E0-E3.
- Máximo 3 preguntas y 3 respuestas humanas.
- Cero retries.
- Workers secuenciales y un solo worker Uvicorn.
- GT, VLM, referencias y H38-H61 prohibidos.

## Autorización

Crear un archivo nuevo desde
`config/freetext_operational_authorization.template.json`. Debe fijar hashes
finales de la rama, execution ID único, expiry y presupuesto exacto. No se
versiona el documento aprobado. El receipt se consume antes de ejecutar E0.

## Interacción

1. Crear sesión desde navegador.
2. Esperar E0 y la primera pregunta.
3. Solicitar respuesta humana literal; no sugerir ni reutilizar respuestas.
4. Ejecutar E1 y detenerse en `waiting_user`.
5. Recargar el navegador y verificar recovery de transcript/ranking/pregunta.
6. Repetir intervención humana para E2 y E3.
7. Verificar estado terminal, cuatro rankings de 253 y tres respuestas.

Cada pregunta se presenta al usuario y la prueba se detiene hasta recibir su
respuesta explícita. Un timeout o outcome incierto produce `unknown`; no se
reenvía POST ni se libera presupuesto/autorización.

## Evidencia requerida

- Authorization hash y receipt de consumo.
- Idempotency records.
- Eventos SSE/replay y GET de recovery.
- Prompt/model/revisión/latencias por etapa.
- Ranking hash y 253 IDs/scores por etapa.
- Transcript literal y preguntas no repetidas.
- Supervisores/gates append-only o attempt ledger equivalente.

Éxito: `E1_E3_REAL_INTERACTIVE_PASS`. Hasta entonces Fase 1 permanece pendiente.
