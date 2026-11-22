# Auditoría científica de DialogueVPR FreeText-v1

## Conclusión

La aplicación no reproduce DQ-pilot. Implementa una política propia,
determinista e inspirada en DialogueVPR: usa el ranking actual, agrupa candidatos
próximos, consulta evidencia cartográfica F3 y elige una intención mediante reglas
y utilidad lexicográfica. La pregunta visible procede de una plantilla fija.
Qwen solo transforma el transcript a inglés cartográfico para CrossText2Loc.

Hay adaptatividad real, pero acotada: ranking y respuestas cambian hipótesis,
features elegibles y familias usadas. No hay policy aprendida, entropía calibrada,
ganancia de información probabilística ni evidencia de visibilidad.

## Flujo E0-E3

| Etapa | Entrada | Operaciones | Salida |
|---|---|---|---|
| E0 | Descripción española | Qwen, CT2L 253, Top-20, clusters/F3, selector | Ranking y pregunta 1 o stop |
| E1 | Descripción y respuesta 1 | Nuevo transcript, Qwen/CT2L global y selector | Ranking y pregunta 2 o stop |
| E2 | Historial hasta respuesta 2 | Igual, mismo universo 253 | Ranking y pregunta 3 o stop |
| E3 | Historial hasta respuesta 3 | Qwen/CT2L; sin cuarta pregunta | Ranking final completed |

El Top-10 es la proyección pública. La pregunta usa el Top-20; el ranking completo
de 253 se conserva y su universo debe ser idéntico entre etapas.

Referencias: `src/tfg_phase0/dialogue_freetext_v1.py`,
`src/tfg_phase0/interactive_dialogue.py`,
`backend/atlas_api/dialogue_freetext_executor.py` y
`config/interactive_dialogue_freetext_application_v1.json`.

## Respuestas A-J

**A. Origen.** `select_freetext_question()` crea opciones desde features F3 de
hipótesis espaciales del Top-20. Qwen no elige preguntas.

**B. Elección.** Filtra opciones y ordena una tupla de utilidad. Prioridades:
relación espacial 3.0; observabilidad 2.0; rasgo 1.5; proximidad 1.25; marco
egocéntrico 1.0.

**C. Candidatos.** Separa `supported_hypothesis_ids` de
`unknown_hypothesis_ids`. Las hipótesis son clusters conectados a 75 m, no
candidatos individuales.

**D. Evidencia.** Asociaciones F3 positivas candidato-objeto OSM. No acreditan
visibilidad y la ausencia no se interpreta como contradicción.

**E. Feature compartida.** Si no quedan hipótesis unknown, descarta por
`no_unknown_hypotheses`; si el soporte supera 75 %, por
`supported_fraction_exceeded`.

**F. No observable.** La respuesta literal consume turno y provoca Qwen+CT2L. No
hay parser especial para “No lo sé”. La familia queda marcada como usada.

**G. Repetición.** Bloquea familias usadas y preguntas cerradas sobre features ya
mencionadas. No detecta equivalencia entre familias distintas.

**H. Utilidad.** Exige dos hipótesis, una supported y una unknown, y registra
razones de descarte.

**I. Función.** Es heurística lexicográfica: prioridad, balance,
`sum(1/best_rank)`, especificidad fija y menos referencias. Los scores influyen
solo por el rank; no hay entropía/information gain calibrada.

**J. Generación.** La intención es dinámica/grounded, pero el literal usa cinco
familias de plantillas. No hay aleatoriedad ni LLM de preguntas.

## Modelos

| Componente | Papel | Decide preguntas |
|---|---|---|
| Qwen3-8B | Transcript español a descripción inglesa | No |
| CrossText2Loc | Ranking exhaustivo Madrid-50m | Aporta orden/candidatos |
| Selector propio | Clustering, F3, opciones, utilidad | Sí |
| DQ-pilot | Referencia metodológica | No implementado |
| VLM | Ninguno | Prohibido en D098 |

No hace falta otro modelo generativo para seleccionar. La opción recomendable es
selección determinista y, si se aprueba, formulación controlada separada.

## Adaptatividad comprobada por CPU

`tests/test_dialogue_question_adaptivity_audit.py` demuestra:

- mismo texto y distinto Top-20/F3 produce `church` frente a `monument`;
- mismo orden con scores reescalados produce la misma pregunta;
- cualquier turno completado, incluida una respuesta “No lo sé”, bloquea la
  familia usada y permite otra; no existe tratamiento semántico especial;
- una feature común a todas las hipótesis produce abstención.

Sesiones locales no versionadas muestran secuencias diferentes: plaza/reloj/calle
elige comercio; monumento+plaza elige relación espacial; mencionar comercio puede
habilitar `commercial|monument`; un ranking posterior puede elegir `park`. Esto
demuestra adaptatividad del contenido, no mejora geográfica.

## Limitaciones

- Las features se unen dentro de cada cluster; basta un candidato para soportar
  la feature a nivel de hipótesis.
- Solo Top-20 influye en preguntas.
- Scores no se calibran ni entran directamente en utilidad.
- Ausencia F3 es unknown, no evidencia negativa.
- No hay línea de visión, heading, VLM ni atributos visuales.
- `open_spatial` puede dominar siempre por prioridad fija.
- Respuestas no tienen interpretación estructurada.
- No hay parada por convergencia, margen Top-1, estabilidad o utilidad mínima.

## Parada anticipada

No obliga siempre a tres preguntas: termina con `no_valid_question` tras E0/E1/E2
o `max_questions_reached_after_e3`. No se detiene específicamente por “No lo sé”
ni por ranking estable.

Una parada por utilidad mínima/estabilidad sería reproducible y sin GT, pero debe
evaluarse y versionarse antes de activarse. No se recomienda cambiarla ahora.

## Separación selección-formulación

Contrato recomendado:

```text
question_id, semantic_intent, target_attribute,
candidate_evidence, supported_hypothesis_ids, unknown_hypothesis_ids,
selection_reason, utility, canonical_question,
display_question, paraphrase_id, generation_method, history_context
```

La pregunta canónica sigue ligada a policy. Las variantes están diseñadas para
preservar intención/evidencia, pero su equivalencia semántica permanece
`pending_human_review`; no se presupone ni se activa.

## Estudio lingüístico no activo

`research/dialogue_question_formulation_v1.py` implementa variantes controladas:

- selección por SHA-256 de intención+historial;
- cero aleatoriedad;
- intención, evidencia, hipótesis y utilidad transportadas sin mutación;
- posibilidad explícita de no saber/no observar;
- `paraphrase_id` y método auditables.

`tests/test_dialogue_question_formulation_study.py` verifica determinismo,
trazabilidad, transporte de grounding, incertidumbre y diversidad; no demuestra
equivalencia lingüística. No está importado por `src/`/backend ni
copiado a la imagen; no cambia D098.

## Plan

1. Versionar schema/audit de selección sin cambiar decisiones.
2. Revisión humana de equivalencia de variantes.
3. Comparar claridad/no presuposición de plantilla actual y variantes.
4. Ampliar fixture F3 multihipótesis.
5. Solo entonces proponer activar wording versionado bajo nueva policy/hash.
6. Evaluar diálogo frente a consulta única antes de afirmar mejora Recall.

Activar formulaciones, utilidad o parada cambia policy/transcript y posiblemente
outputs Qwen; requiere nueva decisión y perfil D098. Esta auditoría no activa
ningún cambio operacional.

Comando ejecutado:

```bash
PYTHONPATH=. pytest -q tests/test_dialogue_question_adaptivity_audit.py \
  tests/test_dialogue_question_formulation_study.py \
  tests/test_dialogue_freetext_v1.py tests/test_interactive_dialogue.py \
  tests/test_interactive_dialogue_multiturn.py
```

Resultado: 50 PASS, incluidos 7 tests nuevos y 43 regresiones existentes.
