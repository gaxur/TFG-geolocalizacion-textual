# I01–I20-assisted-annotation-v1

## Estado

El workflow semiautomático está preparado, sin propuestas válidas. La primera
llamada histórica falló por una incompatibilidad de LM Format Enforcer 0.11.3
con `const` booleano. La revisión v2 corrige únicamente la representación del
schema guiado y permanece sin autorización de GPU. El protocolo
humano original permanece intacto en `i01-i20-annotation-workflow-v1`.

La asistencia produce sidecars de propuestas IA. No modifica automáticamente
`i20-scene-review-v1` ni `i20-annotation-package-v1`. Solo una decisión humana
explícita puede materializar datos en esos contratos.

## Flujo

```text
fixtures ciegas congeladas
  -> plan de 12 pares + 20 imágenes
  -> Qwen3-VL local, JSON guiado
  -> propuestas IA inmutables
  -> interfaz: original read-only + revisión editable
  -> decisión humana explícita
  -> materialización en contratos humanos originales
  -> revisores A/B y adjudicación originales
```

Estados humanos:

- `pending`: valor inicial, bloqueante;
- `reviewed`: aceptación explícita sin cambios;
- `corrected`: revisión explícita distinta;
- `rejected`: se rechaza el borrador, no la observación;
- `unresolved`: duda no resuelta, bloqueante.

No cambiar nada nunca equivale a aceptar.

## Propuestas de escenas

El VLM recibe únicamente las dos imágenes opacas del par y propone:

- misma escena;
- objetos distintivos compartidos;
- solapamiento de FOV;
- vistas alternativas;
- decisión conservadora;
- justificación e incertidumbres.

No recibe coordenadas, distancias, GT, rankings, OSM, provider IDs o holdout.
`CLEAR` asistido es inválido si existe solapamiento o incertidumbre relevante.

## Propuestas de anotación

Cada borrador incluye:

- descripción española natural;
- claims atómicos;
- spans literales Unicode;
- texto visible y legibilidad;
- incertidumbre;
- relaciones en frame de cámara;
- orientación geográfica `unknown`;
- `human_review_required=true`.

Texto `unreadable/uncertain` no puede llevar transcripción. No se permiten nombres
o lugares inferidos mediante contexto externo.

## Interfaces

Tras generar propuestas:

- escenas: `results/generated/i01-i20-assisted-annotation-v1/interfaces/scene-review/review-assisted.html`;
- anotación: `results/generated/i01-i20-assisted-annotation-v1/interfaces/annotation/review-assisted.html`.

Ambas muestran:

1. propuesta original inmutable;
2. versión humana editable;
3. estado humano explícito;
4. razón cuando se rechaza o queda dudoso.

Las interfaces exportan borradores de decisiones. Python recalcula IDs y valida
antes de incorporarlos.

## Modelos locales

| Modelo | Estado local | Pico CUDA | Carga | Papel recomendado |
|---|---|---:|---:|---|
| Qwen3-VL-2B | completo, Apache-2.0 | 4,63 GB | ~25 s | desarrollo barato |
| Qwen3-VL-8B | completo, Apache-2.0 | 18,08 GB | ~98 s | borradores por mayor calidad potencial |

No existe otro VLM local completo. No se descargarán modelos adicionales.

El 8B también se usa como verificador de claims. Esto introduce dependencia
metodológica: un borrador y su posterior verificación por el mismo modelo no son
evidencia independiente. Se exige freeze humano antes de claims y nunca se usa la
imagen de referencia como evidencia candidata.

## Presupuesto

- 12 llamadas multiimagen de escena.
- 20 llamadas de anotación.
- Máximo: 32 llamadas.
- Qwen3-VL-8B BF16/SDPA.
- Estimación: 190–420 s incluyendo carga.
- Pico CUDA esperado: 18,08 GB.
- Red/descargas: 0.
- CT2L/reranking/GT: 0.

## Plan y autorización

La revisión original, su autorización, checkpoint e incidente se conservan sin
cambios en `i01-i20-assisted-annotation-v1`. La revisión v2 usa `enum: [true]` y
`enum: [false]` en los tres booleanos constantes del schema de generación. El
contrato publicado conserva `const`; cada artefacto se valida posteriormente con
JSON Schema Draft 2020-12 y con las reglas semánticas propias.

LM Format Enforcer 0.11.3 sí aplica objetos anidados, propiedades requeridas,
enumeraciones y límites de arrays usados aquí. No garantiza todas las
restricciones de JSON Schema: los mínimos numéricos, `uniqueItems` y límites de
strings en uniones anulables requieren la validación contractual posterior. El
texto español libre se puede emitir escapado como `\\uXXXX`; esta limitación del
alfabeto por defecto no cambia el valor Unicode después de `json.loads`.

Plan original:

`results/generated/i01-i20-assisted-annotation-v1/plan.json`

ID:

`i20-assist-plan-sha256-76b7c73513ee979ef723cc885696d166a307e442df7935e84fd36db37c9291c0`

Autorización pendiente:

`results/generated/i01-i20-assisted-annotation-v1/authorization.request.json`

Estado: `approved=false`, `gpu_authorized=false`.

Plan revisado y autorización sustitutiva pendiente:

```text
results/generated/i01-i20-assisted-annotation-v2/plan.json
results/generated/i01-i20-assisted-annotation-v2/retry-authorization.request.json
```

## Comando tras una autorización posterior expresa

```bash
python scripts/run_i20_assisted_annotation.py \
  --plan results/generated/i01-i20-assisted-annotation-v2/plan.json \
  --authorization results/generated/i01-i20-assisted-annotation-v2/retry-authorization.request.json \
  --annotation-fixture results/generated/i01-i20-annotation-workflow-v1/annotation/fixture.json \
  --scene-fixture results/generated/i01-i20-annotation-workflow-v1/scene-review/fixture.json \
  --instructions results/generated/i01-i20-annotation-workflow-v1/annotation/INSTRUCTIONS_ES.md \
  --model-path /home/dataai/models/hf/Qwen3-VL-8B-Instruct-0c351dd01ed8 \
  --output-root results/generated/i01-i20-assisted-annotation-v2
```

El runner usa checkpoints separados:

- `checkpoints/scene-proposals.jsonl`;
- `checkpoints/annotation-proposals.jsonl`.

## Revisión humana

1. Importar `scene-proposals.json` en la interfaz de escenas assisted.
2. Abrir cada par y elegir estado humano explícito.
3. Exportar decisiones y finalizarlas con
   `finalize_i20_assisted_human_decisions.py`.
4. Repetir con `annotation-proposals.json`.
5. Solo cuando existan 32 decisiones terminales `reviewed/corrected`, ejecutar
   `materialize_i20_assisted_outputs.py`.
6. Continuar con revisores A/B y adjudicación del protocolo original.

Rechazar una propuesta obliga a completar manualmente el formulario original; no
excluye automáticamente Ixx.

## Limitaciones

- La asistencia no produce anotaciones humanas independientes.
- El mismo VLM para borrador y claims crea correlación.
- OCR y nombres pueden alucinarse; siempre revisar.
- Multiimagen está soportado por arquitectura, pero no tiene evaluación local
  independiente suficiente.
- JSON guiado reduce, pero no elimina, errores semánticos.
- No se calibra ningún componente con I01–I20.
- Elegibilidad sigue en 0 hasta escenas, ledger, dos revisores, adjudicación y GT.
