# Runtime por fases de DialogueVPR v3

## Objetivo y aislamiento

El runtime por fases evita mantener CT2L y Qwen3-VL residentes a la vez. Cada
recuperación CT2L se ejecuta en un proceso hijo supervisado. El hijo carga CT2L,
produce una transición v2 validada, escribe un checkpoint y termina. El padre
comprueba que no queden procesos compute antes de publicar la fase `retrieved`.
No se utiliza `gc.collect()` ni `torch.cuda.empty_cache()` como sustituto de la
terminación del proceso.

La reanudación CPU convierte la sesión v2 persistida en v3 mediante
`VisualMultiTurnDialogueOrchestrator.from_base_session()` o fusiona una respuesta
mediante `from_base_answer_result()`. No vuelve a ejecutar CT2L. La evidencia
visual se aplica mediante `inspect_pending()`, una transición separada que nunca
ejecuta recuperación ni modifica ranking.

## CLI

```text
python scripts/run_dialogue_v3_phased.py prepare
python scripts/run_dialogue_v3_phased.py retrieve
python scripts/run_dialogue_v3_phased.py resume
python scripts/run_dialogue_v3_phased.py visual
python scripts/run_dialogue_v3_phased.py status
```

- `prepare`: valida configuración, `session_id` y manifest; crea el envelope.
- `retrieve`: reserva durablemente el intento y lanza CT2L en un hijo. Es GPU.
- `resume`: transición CPU desde checkpoint; con `--answer` registra una respuesta
  literal. Nunca abre GPU por sí sola.
- `visual`: exige `--authorize-gpu`, reserva el único presupuesto antes de llamar
  al worker y nunca reintenta automáticamente.
- `status`: valida y muestra estado, próxima acción, checkpoint, snapshot,
  presupuesto visual y lock activo; no carga modelos.

## Estados

```text
prepared -> retrieval_reserved -> retrieved -> awaiting_visual
                                      |             |
                                      |             -> visual_reserved
                                      |                    |-> awaiting_answer
                                      |                    |-> visual_failed
                                      |                    `-> visual_uncertain
                                      `-> awaiting_answer -> retrieved (respuesta con retrieval)
                                                           `-> completed
```

Errores conocidos terminan en `retrieval_failed` o `visual_failed`. Un timeout,
corte o falta de artefacto terminal produce `*_uncertain`. Ninguno se reintenta:
requiere revisión y una nueva autorización explícita. Un estado `*_reserved` sin
lock activo se muestra como `*_uncertain_after_interruption`.

## Checkpoints

El envelope contiene:

```text
run/
  configuration.json
  state.json
  run.lock
  attempts/retrieval-NNN/{supervisor.json,result.json}
  checkpoints/dialogue-retrieval-checkpoint-sha256-....json
  snapshots/NNN-sha256.json
```

Los checkpoints y snapshots son inmutables. El checkpoint enlaza sesión,
descripción por hash, intención realmente seleccionada, galería, CT2L, CLIP,
checkpoint, F3, política, ranking completo, candidate IDs, scores, tiempos,
configuración y procedencia. Se rechazan corrupción, otra sesión o divergencia
entre ranking, IDs y scores. `state.json` se actualiza atómicamente.

## Respuestas humanas

Una sesión en `awaiting_answer` no avanza sin una respuesta literal:

```bash
python scripts/run_dialogue_v3_phased.py resume \
  --run-root results/generated/dialogue-v3-madrid-prueba-visual-01-phased-v1 \
  --answer "<respuesta literal>"
```

Si la respuesta exige recuperación, `resume` persiste `pending_answer` y devuelve
`next_action=retrieve`; no construye un ranking falso. Si es desconocida,
ambigua, no observable o una orden de parada, la transición puede completarse en
CPU. Nunca se inventan respuestas y se mantiene `max_questions=3`.

## Evidencia visual y presupuesto

Antes de `visual` se verifica que la intención real seleccionada coincide con el
manifest (`square` para `madrid-prueba-visual-01`). Si no coincide, la fase pasa
directamente a `awaiting_answer` y Qwen3-VL no se ejecuta.

`visual --authorize-gpu` escribe primero un intento `reserved`. Después aplica el
worker existente, request v2, 192 tokens, Docker validado y `stable-swap-v1`. El
worker mantiene `query_update_allowed=false` y `ranking_update_allowed=false`.
Tras una interrupción no hay retry automático; el estado incierto requiere
revisión. Un intento `completed`, `failed` o `uncertain` consume el presupuesto.

## Ejemplo preparado, no ejecutado

```bash
RUN=results/generated/dialogue-v3-madrid-prueba-visual-01-phased-v1

python scripts/run_dialogue_v3_phased.py prepare \
  --config config/dialogue_v3_real_session_madrid_prueba_visual_01.json \
  --run-root "$RUN"

python scripts/run_dialogue_v3_phased.py status --run-root "$RUN"
```

Tras una autorización GPU separada para CT2L:

```bash
python scripts/run_dialogue_v3_phased.py retrieve \
  --run-root "$RUN" \
  --authorization <autorizacion-ct2l-aprobada.json> \
  --timeout 240
python scripts/run_dialogue_v3_phased.py resume --run-root "$RUN"
python scripts/run_dialogue_v3_phased.py status --run-root "$RUN"
```

Solo si `status` indica `awaiting_visual`, intención `square`, CT2L terminado y
existe una nueva autorización visual GPU:

```bash
python scripts/run_dialogue_v3_phased.py visual \
  --run-root "$RUN" \
  --authorize-gpu
```

Estos comandos GPU no se ejecutaron en este BUILD.

## Continuación de un run terminal

`fork-recovery` crea una continuación versionada desde un run
`retrieval_failed` sin editarlo ni reutilizar autorizaciones:

```bash
python scripts/run_dialogue_v3_phased.py fork-recovery \
  --source-run results/generated/dialogue-v3-madrid-prueba-visual-01-phased-v3 \
  --target-run results/generated/dialogue-v3-madrid-prueba-visual-01-phased-v4 \
  --reason second_turn_child_import_failure_fixed
```

La operación exige checkpoint, snapshot y `pending_answer` válidos, lock libre y
artefactos del intento fallido. Publica el destino mediante `renameat2` con
`RENAME_NOREPLACE`, registra `dialogue-v3-fork-recovery-v1`, no copia intentos o
autorizaciones y deja `phase=retrieved`, `next_action=retrieve`. Repetir el mismo
comando es idempotente; un lineage diferente se rechaza.

`retrieve` rechaza la plantilla pendiente
`config/dialogue_v3_phased_ct2l_gpu_authorization.template.json`. El operador
debe materializar un archivo separado con `status=OPERATOR_AUTHORIZED`, conservar
el `session_id`, `stable_swap_required=true`, `automatic_retries=0` y declarar
exactamente `isolated CT2L retrieval on NVIDIA GB10`. Antes de reservar el
intento, el padre comprueba Ollama y aplica cinco muestras de `stable-swap-v1`.

## Entorno aislado CT2L

La fase `retrieve` no usa `sys.executable`. El padre valida primero
`config/ct2l_isolated_runtime_cvgtext.json` y lanza el hijo mediante:

```text
.venv-cvgtext/bin/python
```

Este es el entorno histórico previsto por `scripts/wait_and_run_cross_text2loc.py`.
El preflight se ejecuta con `python -I` y consulta exclusivamente metadatos de
distribución y `find_spec`; no importa Torch o CLIP, no inicializa CUDA y no carga
modelos. Verifica:

- CPython 3.12.3 y `sys.prefix` del virtualenv;
- `clip==1.0` con PEP 610 `direct_url.json` y commit OpenAI CLIP
  `dcba3cb2e2827b402d2701e7e1c7d9fed8a20ef1`;
- Torch `2.11.0+cu130`, torchvision `0.26.0+cu130`, NumPy `1.26.4`, Pillow
  `12.3.0` y dependencias auxiliares fijadas;
- CVG-Text `6910d2747a94fbe985309bde60cd4732bcbbf50f` y hash de `utils.py`;
- pesos CLIP y checkpoint CT2L por nombre, tamaño y SHA-256;
- identidad del manifest de embeddings `madrid-50m`;
- lock `config/ct2l_isolated_runtime_requirements.lock.txt`.

Un fallo de entorno ocurre antes de `stable-swap-v1`, antes de reservar el
intento y antes de consumir una autorización GPU. El padre y `status` continúan
sin importar Torch ni CLIP.

El run histórico `dialogue-v3-madrid-prueba-visual-01-phased-v1` conserva
`retrieval_failed` y nunca se migra o reactiva. Una ejecución futura debe crear
`dialogue-v3-madrid-prueba-visual-01-phased-v2`, obtener una autorización CT2L
nueva y repetir `prepare` antes de `retrieve`.

### Entry point hijo mínimo

El hijo GPU no ejecuta el CLI padre. Usa:

```text
.venv-cvgtext/bin/python -I scripts/run_ct2l_isolated_child.py
```

El módulo importa únicamente runtime CT2L, evidencia F3 y orquestador v2. No
importa `jsonschema`, schemas visuales, supervisor, ledger por fases o proveedor
Qwen3-VL. Reutiliza `CrossText2LocRetriever`, `ResidentCT2LAdapter`,
`F3EvidenceIndex` y `MultiTurnDialogueOrchestrator`; no duplica recuperación ni
política científica.

Antes de reservar GPU, el padre ejecuta el mismo entrypoint con:

```bash
.venv-cvgtext/bin/python -I scripts/run_ct2l_isolated_child.py \
  --check-child-startup \
  --config config/dialogue_v3_real_session_madrid_prueba_visual_01.json
```

El check carga configuración, galería/matriz NumPy y F3, valida sus identidades y
termina inmediatamente antes de `CrossText2LocRetriever.load()`. Exige
`torch_imported=false`, `clip_imported=false`, `cuda_initialized=false` y
`models_loaded=false`. Un fallo ocurre antes de `retrieval_reserved` y no consume
autorización.

## Comparación de variantes pendiente

La sesión funcional actual mantiene exclusivamente `literal_concatenation` como
variante canónica. Una comparación futura de `literal_concatenation`,
`en_cartographic` y `es_cartographic` debe definirse como experimento separado,
con protocolo, consultas, autorización GPU y outputs congelados. No debe
introducirse retrospectivamente en este run ni fusionar rankings o scores. Esta
comparación está documentada, pero no implementada ni ejecutada.
