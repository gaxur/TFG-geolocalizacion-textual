# Auditoría del fallo E1 Qwen residente

## Sesión y alcance

Sesión auditada:
`freetext-application-5f0b0122-b141-4489-a0b5-385d342a16af`.

La auditoría fue exclusivamente de lectura. No se repitió E1, no se modificó la
sesión, D098, el runtime ni la evidencia científica.

Manifest saneado: [evidence/freetext-e1-qwen-failure-5f0b0122.json](evidence/freetext-e1-qwen-failure-5f0b0122.json).
Los artefactos completos permanecen en el volumen local no versionado.

## Hechos verificados

- La respuesta humana se persistió antes de inferencia:
  `No puedo comprobarlo, pero a mi izquierda veo una parada de metro`.
- SHA-256 de respuesta:
  `1c93ebddbbc54a880069a8e28fdc3ce9e9162974c205fea417effed21b14c8cc`.
- Evento `E1_qwen: running`: `2026-11-16T19:05:36.582Z`.
- Evento `E1_qwen: failed`: `2026-11-16T19:05:40.288Z`.
- Telemetría Qwen: `cache_hit=true`, `model_load_ms=0`,
  `inference_wall_ms=3677,003`, error `ValueError`.
- Error exacto en traceback:
  `ValueError: salida FreeText rechazada por validación`.
- CT2L E1 no se inició y no existe ranking E1.
- Qwen permaneció residente; ModelGate/RLock no mostraron espera o deadlock.
- Ollama estaba vacío, PSI 0 y no hubo OOM/preflight nuevo.

## Clasificación causal

| Clase | Resultado |
|---|---|
| Modelo/carga | No: Qwen residente produjo una salida en 3,677 s |
| Infraestructura/GPU | No: GPU y memoria estables, sin timeout ni OOM |
| Autorización/cuota | No: E1 reservado y respuesta persistida correctamente |
| Orquestación | Correcta hasta el validador; CT2L no debía arrancar tras rechazo |
| Validación post-Qwen | Sí: `validate_transformation` devolvió rechazo estructural |

El runtime anterior no persistió el `raw_output` rechazado ni
`validation.issues`. Por tanto, no puede determinarse honestamente qué regla
concreta falló sin repetir inferencia. El transcript observacional aplicable
contiene negación/incertidumbre, dirección izquierda y `parada de metro`; no
contiene números observacionales.

## Propuesta mínima no implementada

Antes de volver a probar E1, versionar un sidecar de fallo que persista, de forma
atómica y fuera del estado científico aceptado:

- output/raw output rechazado;
- SHA-256 del transcript y prompt;
- `validation.issues` completos;
- identidad del modelo/perfil;
- stage y timestamp;
- declaración `not_used_for_retrieval=true`.

El estado y ranking solo avanzarían si la validación pasa. Añadir tests CPU para
preservación de negación, incertidumbre, dirección y entidad, además de fallo de
sidecar. Esta propuesta modifica runtime/identidad y requiere aprobación antes de
implementarse o regenerar D098.
