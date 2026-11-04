# Diagnóstico de JSON inválido en I01-I20 assisted v2

## Evidencia disponible

La salida cruda de la primera llamada v2 no se conservó. No aparece en el
checkpoint, los artefactos del experimento, el repositorio ni el journal local.
Por ello no puede afirmarse qué carácter concreto ocupaba la posición 818 ni
reconstruirse esa salida como si fuera real.

Sí se ha demostrado en CPU una causa suficiente para producir exactamente el
error observado. LM Format Enforcer 0.11.3 evalúa un `enum` como numérico cuando
todos sus elementos son instancias de `int` o `float`. En Python, `bool` deriva
de `int`; por tanto, `enum: [true]` se transforma internamente en el literal
`True`. Ese literal no es JSON válido.

Con el tokenizer Qwen2 local de Qwen3-VL-8B y la integración Transformers real:

- el parser permite `T` después de `{"x":`;
- el parser no permite `t`;
- la secuencia tokenizada `{"x":true}` es rechazada;
- la secuencia `{"x":True}` es aceptada y habilita EOS;
- `json.loads('{"x":True}')` falla con `Expecting value`.

Esto explica el fallo sin necesitar una hipótesis sobre el contenido visual. La
coincidencia con línea y columna no puede confirmarse porque falta la salida.

## Integración auditada

El runner entrega a `json.loads` únicamente los tokens posteriores a la longitud
de `input_ids`. `skip_special_tokens=True` elimina los tokens terminales del chat,
pero no añade el prompt a la salida decodificada.

LMFE recibe la secuencia completa, incluido el prompt. Su `TokenEnforcer` trata
la primera secuencia desconocida como raíz y solo aplica al parser los tokens
generados posteriormente. Esto funciona para una generación greedy de batch uno,
pero no usa un offset explícito y conserva estado entre jobs.

Riesgos secundarios de LMFE 0.11.3:

- ante algunos fallos internos fuerza EOS en lugar de propagar el error;
- solo registra un EOS del tokenizer aunque Qwen configure dos;
- el decodificador incremental elimina `�` terminales y puede diferir de la
  decodificación final en casos Unicode fragmentados;
- no aplica por completo `minimum`, `uniqueItems` ni restricciones hermanas de
  tipos anulables.

Estos riesgos no son necesarios para explicar v2. El contrato Draft 2020-12 y
las reglas semánticas posteriores siguen siendo obligatorios.

## Corrección v3

La revisión v3 usa `type: boolean` únicamente para los tres booleanos constantes
del schema de generación. LMFE produce así `true` o `false` JSON válidos. No se
relaja el contrato publicado: la validación posterior conserva `const: true`, la
orientación conservadora y las reglas semánticas existentes.

Los prompts, fixtures, modelo, revisión, pesos, parámetros y orden permanecen
sin cambios. La identidad del schema y del plan sí cambia, por lo que v3 requiere
autorización propia.

## Observabilidad y fallo cerrado

El runner v3 prepara antes de cada inferencia un registro separado de intento.
Cuando la generación termina, registra:

- tokens generados;
- último token;
- terminación por EOS o por límite;
- hash de salida si es válida;
- excepción, traceback y salida cruda si falla;
- picos CUDA disponibles.

Una excepción se vuelve a propagar. No existe retry automático y una salida
fallida nunca entra en el checkpoint de propuestas válidas.

## Alternativas evaluadas

| Opción | Evaluación |
|---|---|
| Corregir LMFE actual | Recomendada. `type: boolean` resuelve la causa demostrada con cambio mínimo. |
| Simplificar más el schema guiado | No necesario. Aumentaría salidas inválidas sin resolver una causa adicional demostrada. |
| Generar texto y estructurarlo en otra llamada | No recomendado. Duplica coste, introduce otra transformación no independiente y complica spans literales. |
| Sustituir la librería | No justificado sin validar primero la corrección mínima; podría exigir dependencias o descargas. |

Si la sonda v3 fallara por otra causa, la alternativa operativa es completar las
20 anotaciones y 12 decisiones de escena mediante el workflow humano original,
sin VLM. También podría generarse texto libre para asistencia visual no
contractual, pero no debería materializarse automáticamente como anotación.

## Autorización futura

La autorización v3 preparada permite solicitar como máximo una sola llamada de
escena, con el flag `--probe-first-scene-only`. Está desactivada y no autoriza la
campaña completa. Una sonda válida demostraría la integración GPU para un caso,
pero una campaña posterior requeriría otra autorización explícita y un presupuesto
que contabilice las llamadas históricas v1 y v2.
