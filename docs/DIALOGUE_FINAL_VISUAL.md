# Cierre supervisado de DialogueVPR con reranking visual

La sesión conserva descripción original y acumulada, diálogo, interpretación y
ranking exhaustivo por ronda. La reserva de 20 del panel DQ conserva su contrato;
no limita la reserva exhaustiva ni el reranking. El cierre congela el ranking
posterior a la última respuesta y su Top-10. El VLM recibe solo sus primeros
M candidatos (50 por defecto; `ATLAS_DQ_FINAL_VISUAL_DEPTH=10|50|100` en el
proceso FastAPI). Se conserva también el ranking combinado completo; la cola
fuera de M no cambia. `ATLAS_DQ_CELLS_GEOJSON` puede apuntar al GeoJSON canónico
F1 de la galería para persistir los polígonos con su hash; sin él se conservan los
centros WGS84 y MapLibre usa su catálogo habitual. No se fabrican polígonos.

Se reutiliza `minmax(CT2L) + 0,1 × soporte visual positivo` sobre Top-M, sin
penalización por falta de cobertura. No se presenta el score como probabilidad.
Ausencia de evidencia o veredicto no verificable implica `visual_score: null`.
Sin soporte positivo o sin resultado VLM, el ranking completo y el Top-10
permanecen idénticos. La API pública conserva el Top-10 CT2L en `results` y añade
`visual_postprocessing` solo a la última ronda cerrada. El resultado visual no
participa en la generación de preguntas. El mismo núcleo puede recibir un
ranking inicial CT2L directamente para la ablación sin diálogo.

## Límite del supervisor del host

Este repositorio publica el [contrato de recibo](../schemas/dq-stage-lease-receipt.schema.json),
no StageLease ni DQ56. El productor externo escribe `<sha-operación>.release.json`
en un directorio privado distinto del buzón y de las sesiones. FastAPI lo lee
en modo de solo lectura y contrasta la operación (incluidos sesión, etapa de
cómputo y modo), hashes de postflight y terminal, ejecución y estado del cgroup.
El esquema documenta la forma; **no sustituye esas verificaciones**. Sin un
recibo compatible no se admite el éxito de una operación supervisada real.

`compose.dq-supervised.yaml` solo monta el buzón y el directorio de recibos.
No instala ni ejecuta el supervisor. Su provisión, release inmutable y permisos
de uso han de confirmarse con el operador del host antes de cualquier ejecución
real. No hay descargador, sustituto automático ni modo de simular recibos en
producción. DQ-Pilot (`graysonggg/dlgpr`, `cf5c7b8a79ce055a83706fcbe0b94edf31b1cb40`)
y Qwen3-VL-8B (`Qwen/Qwen3-VL-8B-Instruct`, `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b`)
son dependencias de inferencia externas. CrossText2Loc mantiene su auditoría de
origen en [CROSSTEXT2LOC.md](CROSSTEXT2LOC.md).

## Validación CPU desde un checkout limpio

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-integrated-cpu.txt
.venv/bin/python -m pytest -q \
  tests/test_final_visual_ranking.py tests/test_dq_pilot52_supervised_visual.py \
  tests/test_dq_pilot46_supervised_sessions.py tests/test_dq_pilot23_iterative_integration.py \
  tests/test_dq_pilot24_session_api.py tests/test_dq_pilot45_session_flow.py \
  tests/test_visual_reranking.py tests/test_symmetric_visual_reranking.py
cd frontend
npm ci
npm test
npm run build
```

Las pruebas de admisión usan recibos sintéticos y comprueban rechazo ante
ausencia, identidad divergente o cgroup no liberado. No validan el supervisor
real. El caso de exclusión/reinicio/liberación de StageLease sigue en
`test_dq_pilot52_supervised_visual.py`: se habilita con
`ATLAS_TEST_EXTERNAL_STAGELEASE=1` y `-k exclusive_lease` solo si el operador
proporciona por separado la implementación autorizada con módulo
`research.dq_pilot_stage_lease_v1` en `PYTHONPATH`. Si se solicita la prueba
opcional y el módulo no existe, falla; no hay implementación de reserva.

## Operación posterior, con autorización independiente

1. Una vez cerrada la sesión, `GET /internal/dq-supervised/sessions/{id}/final-visual/context`
   devuelve descripción acumulada, Top-M, geometrías disponibles y ligaduras del
   ranking. Es un endpoint de operador local. No ejecuta modelos.
2. `scripts/final_visual_v4_bridge.py prepare` convierte ese contexto y un JSON
   de asociaciones Mapillary autorizadas o resultado D112 (selección geométrica
   OSM/Mapillary) en el plan de V4. Una asociación directa requiere `provider`,
   `candidate_id`, `image_id`, `image_sha256` y admite `sequence_id`. Usar solo
   activos compatibles con la ventana y el propósito autorizados; no adquiere
   fotografías. Revisar todos los claims (en especial negaciones y menciones
   de la propia pregunta) y omitir la ejecución si no quedan imágenes y claims.
3. Solo con permiso explícito y exclusión de cargas concurrentes, el runner
   existente [`run_visual_fixture_v4.py`](../scripts/run_visual_fixture_v4.py)
   admite `--model-key qwen3-vl-8b` y verifica los pesos locales. El VLM recibe
   la imagen y el claim, no las coordenadas, ranks, scores ni GT. El runner no
   se lanza desde FastAPI y este cambio no lo autoriza ni incorpora un nuevo
   supervisor GPU.
4. `scripts/final_visual_v4_bridge.py convert` verifica artefactos, modelo,
   revisión, claims, hashes y veredictos; publicar atómicamente su salida en
   `<buzón>/final-visual/{id}.json`. El operador local incorpora el resultado
   con `POST /internal/dq-supervised/sessions/{id}/final-visual`. Relectura
   desde el navegador actualiza el mapa sin repetir ninguna operación.

## Bloqueo GB10

Los dos intentos Q1 terminaron `STOPPED_MEMORY` por reclaim directo global.
El último registró 7,43 GiB de pico del cgroup, +69 páginas globales, +0 directas
y 0 ms de PSI acumulado del cgroup; FastAPI quedó en `FAILED (DQ_E0)` y
StageLease se liberó por reconciliación oficial. No hay atribución causal.

Solicitar al administrador franjas UTC y duración con exclusión acordada de
cargas CPU/E/S/GPU; inventario de usuarios, contenedores, servicios/timers y
cgroups concurrentes (incluidos usuarios fuera del cgroup DQ); estado y margen
de RAM, swap y zonas NUMA; y disponibilidad/permisos para correlacionar con
timestamps los contadores de reclaim, PSI, fallos y memoria por proceso/cgroup.
Pedir confirmación de quién puede pausar sus propias cargas y contacto para
abortar la ventana si aparece presión. No reemitir Q1 ni alterar sus guardas.
