# Preparación de la primera sesión visual real

## Estado

La infraestructura queda preparada, pero la sesión permanece
`SESSION_PREPARATION_PENDING`. No se ha ejecutado CT2L, Qwen textual, Qwen3-VL ni
una sesión geográfica. La plantilla operativa es
`config/dialogue_v3_real_session.template.json`; debe copiarse a un archivo local
separado antes de completar datos del operador.

## Configuración técnica congelada

| Campo | Valor |
|---|---|
| Región | `madrid_pilot`, `config/madrid.yaml` |
| Galería | `madrid-50m` |
| CT2L | `config/madrid_f46_retriever.json` |
| F3 | bundle `f3-madrid-pilot-associations-sha256-5f4af8...` declarado en la plantilla |
| Política | reserva 20, radio 75 m, máximo 3 preguntas |
| Consulta | literal, presupuesto 300 tokens |
| VLM | Qwen3-VL-8B revisión `0c351d...`, worker v2, 192 tokens |
| Docker | `qwen3-vl-dialogue-worker:lmfe-0.11.3-tf5.9-v1`, ID `sha256:4ed137...` |

No están congelados todavía `session_label`, descripción humana,
`intent_family`, ruta CLIP ni fotografía/manifiesto. Qwen3-8B textual es opcional:
si no se aporta `--qwen-model-dir`, la política usa la redacción determinista de
fallback sin cambiar la intención.

## Directorio de incorporación

Colocar la fotografía, sin copiar activos históricos, directamente en:

```text
data/madrid/observer_view_authorized/
```

Formatos admitidos: JPEG, PNG o WebP válidos. Se recomienda conservar los bytes
originales y un nombre sin espacios. No incluir coordenadas ni GT. La fotografía
debe ser propia/controlada, representar la vista desde el observador y no
proceder de H26-H37, H38-H61 u otro conjunto reservado.

## Orden de preparación

1. Copiar `config/dialogue_v3_real_session.template.json` a una configuración
   local separada.
2. Completar `session_label`, `initial_description` y `clip_weights` con valores
   reales. No parafrasear la descripción humana.
3. Derivar el identificador sin ejecutar modelos:

```bash
python scripts/validate_dialogue_v3_real_session.py \
  --config <configuracion-local.json>
```

El resultado aún será `SESSION_PREPARATION_PENDING`, pero incluirá
`derived_session_id`. Copiar exactamente ese valor al campo `session_id` de la
configuración.

4. El operador debe elegir una `intent_family` que realmente pretenda comprobar:
   `square`, `church`, `monument`, `intersection`, `park` o `commercial`. La
   ejecución posterior volverá a exigir que coincida con el turno seleccionado;
   si no coincide, no abre el worker.
5. Colocar la fotografía en el directorio autorizado y crear el manifiesto con
   todos los metadatos explícitos:

```bash
python scripts/prepare_observer_view_manifest.py \
  --image data/madrid/observer_view_authorized/<foto.jpg> \
  --output data/madrid/observer_view_authorized/manifest.json \
  --image-id <id-estable> \
  --source <fuente> \
  --author <autor> \
  --license-or-authorization <autorizacion> \
  --acquired-at-utc <fecha-ISO-8601> \
  --observer-relation-evidence <evidencia-de-perspectiva> \
  --usage-restriction <restriccion> \
  --session-id <derived_session_id> \
  --intent-family <familia> \
  --authorization-id <id-autorizacion>
```

6. Registrar en la configuración `intent_family`, `observer_manifest` y el mismo
   `session_id`. Validar en CPU, opcionalmente verificando todos los shards:

```bash
python scripts/validate_dialogue_v3_real_session.py \
  --config <configuracion-local.json> \
  --deep-model-identity \
  --output results/generated/dialogue-v3-real-session-preflight-v1.json
```

Solo `SESSION_CPU_VALIDATION_PASS` permite solicitar autorización de ejecución.

## Ejecución futura no autorizada en este BUILD

```bash
python scripts/run_interactive_dialogue.py \
  --mode real \
  --policy config/interactive_dialogue_multiturn.json \
  --max-questions 3 \
  --session-label <session_label> \
  --description "<initial_description literal>" \
  --output-dir results/generated/dialogue-v3-real-session-v1 \
  --ct2l-config config/madrid_f46_retriever.json \
  --f3-bundle <f3_bundle congelado> \
  --cvg-utils-sha256 18dad4696c205dba5f934f9382ff5bd7d380c502680e462612bbdc49229ba597 \
  --clip-weights <clip-local> \
  --visual-image-manifest data/madrid/observer_view_authorized/manifest.json \
  --authorize-visual-gpu \
  --visual-worker-output results/generated/dialogue-v3-real-worker-v1 \
  --visual-model-dir <snapshot-local-qwen3-vl-8b>
```

No ejecutar este comando hasta recibir una autorización posterior de GPU y
confirmar que el primer turno tiene la familia del manifiesto.
