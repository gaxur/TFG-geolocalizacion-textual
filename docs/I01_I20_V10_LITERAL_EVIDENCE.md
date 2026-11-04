# I01-I20 v10: evidencia literal y spans deterministas

## Problema

La anotación v9 produjo JSON y estructura válidos, pero asignó a `TIGER` el span
`[428,475)`, que correspondía a otro fragmento. Los offsets generados por el VLM
no son fiables.

El contrato canónico `i20-annotation-package-v1` no separa claim semántico y
evidencia: exige semánticamente que `description_es[start:end] == text_es`. Los
revisores y la adjudicación se enlazan por el `claim_id` derivado de ese texto y
span. Por ello v10 no modifica el contrato final.

## Schema guiado sidecar

Los claims generados contienen:

- `semantic_text_es`: interpretación atómica para revisión y trazabilidad;
- `evidence_quote`: cita exacta y no vacía copiada de `description_es`;
- tipo, certeza, observabilidad y requisitos existentes;
- ningún offset.

`visible_text` contiene transcripción, `evidence_quote`, legibilidad y certeza,
sin offsets.

La transformación final usa `evidence_quote` como `claim.text_es`, porque el
contrato canónico define el claim final como fragmento literal. El texto semántico
permanece en el raw sidecar y no se copia al contrato final. Esta pérdida es
explícita; cambiarla requeriría versionar contratos, revisiones y adjudicación.

No se admiten claims sin evidencia literal. Una afirmación observable que no
pueda citarse de forma única debe rechazarse o reescribirse en una generación
posterior autorizada, nunca materializarse automáticamente.

## Algoritmo

1. Validar el raw contra el schema guiado v10.
2. Buscar todas las apariciones exactas de `evidence_quote` en `description_es`.
3. Exigir exactamente una aparición, incluyendo coincidencias solapadas.
4. Calcular `start` y `end=start+len(evidence_quote)` con índices Python.
5. Comprobar nuevamente igualdad literal.
6. Materializar `text_es=evidence_quote` y el span.
7. Calcular `claim_id` sobre el claim final.
8. Validar contrato Draft 2020-12 y reglas semánticas existentes.

No se normaliza Unicode, espacios o puntuación; formas NFC/NFD distintas no son
iguales. No se usan fuzzy matching, embeddings o reparación del texto.

## Replay diagnóstico v9

El raw histórico no contiene `evidence_quote` y no es una generación v10. La
descripción contiene `TIGER` tres veces. La cita `TIGER` es ambigua y se rechaza.
Existen citas contextuales únicas como `el nombre 'TIGER'`, pero seleccionarlas
retroactivamente sería una reinterpretación no autorizada. No se crea ningún
resultado retroactivo.

## Concisión

V9 alcanzó exactamente 2.000 caracteres. Doce de 23 frases eran negativas,
incluyó 15 limitaciones y agotó 500 caracteres de notas, pero generó un claim.

V10 fija:

- descripción entre 80 y 900 caracteres;
- máximo 12 claims;
- máximo 6 limitaciones por bloque;
- notas de máximo 300 caracteres;
- instrucción explícita de priorizar indicios discriminativos y evitar listas
  exhaustivas de ausencias, repeticiones y detalles genéricos.

No se elimina información visual útil ni se introduce contexto geográfico.

## Estado

V10 es una revisión nueva y desautorizada. No modifica v1-v9, no materializa
anotaciones humanas y requiere revisión humana posterior aunque una propuesta
supere todos los validadores.
