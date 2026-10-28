# Evaluación parcial H16/H23 v2 y runner reanudable

## Estado recuperado

Los runs parciales Qwen3-VL-2B y 8B ya estaban completos. No se repitieron. Ambos
usan exactamente fixture v2, 41 imágenes históricas, 29 claims humanos aprobados
y el mismo conjunto de 1.566 jobs.

| Modelo | Generate | Abstenciones orientación | Inválidos | Supported | Contradicted | Unverifiable |
|---|---:|---:|---:|---:|---:|---:|
| 2B | 1.240 | 326 | 0 | 305 | 0 | 1.261 |
| 8B | 1.240 | 326 | 0 | 299 | 11 | 1.256 |

El acuerdo exacto es 1.415/1.566, 90,36 %. Sin etiquetas humanas claim-imagen,
esto mide concordancia, no accuracy ni superioridad.

## Cobertura parcial

- 41 imágenes físicas frente a 432 planificadas;
- 99 asociaciones frente a 766;
- 1.566 jobs frente a 11.080;
- H16: 26/50 candidatos con alguna evidencia;
- H23: 19/50;
- cobertura condicionada por disponibilidad histórica, no equilibrada.

## Promoción parcial contrafactual

Se aplicó sin GT la misma política numérica positiva congelada, pero se declara:

- `complete_block_requirement_satisfied=false`;
- `official_frozen_experiment_result=false`;
- `availability_conditioned_counterfactual=true`.

Ambos modelos:

- H16: ninguna promoción;
- H23: promueven rank 12 y desplazan rank 10.

La evaluación posterior con referencia muestra:

- ninguna mejora en Top-1;
- ningún cambio en GeoRecall@1/5/10 a 50 o 100 m;
- candidato desplazado H23: 289,90 m;
- candidato promovido: 690,34 m;
- reemplazo: +400,45 m, geográficamente más lejano.

No cuenta como falso descarte Geo50 porque ambos están fuera de 50 m, pero sí es
una sustitución geográficamente desfavorable. No demuestra que el experimento
Top-50 completo vaya a comportarse igual.

Artefactos:

- promoción sin GT SHA-256
  `7277cfb8631ab1892fe2c85234ee42be5d18eb49470e7bd2a4248557a3897097`;
- `partial-paired-promotions-v1.json`;
- `partial-paired-promotion-geography-v1.json`.

## Adquisición pendiente

No existe autorización v2. El plan exacto permanece bloqueado. Resumen por fases:

| Fase acumulada | Pendientes acumuladas | Nuevas en fase |
|---|---:|---:|
| Top-10 | 114 | 114 |
| Top-20 | 195 | 81 |
| Top-50 | 391 | 196 |

Top-50 continúa siendo profundidad primaria congelada. Las fases solo permiten
escalonar transferencia; sus resultados no deciden si continuar.

## Observabilidad y reanudación

`run_visual_fixture_v4.py` mantiene prompts, orden, batch 1 y generación, pero
añade:

- progreso periódico con query/candidato/imagen/claim, elapsed, media y ETA;
- checkpoint JSONL append-only;
- cabecera con hashes, modelo, generación y hash del plan ordenado;
- `flush` y `fsync` por resultado;
- resume estricto de un prefijo completo;
- rechazo de provenance o jobs distintos;
- reparación exclusiva de una cola truncada no confirmada;
- salida final temporal y `os.replace` atómico;
- hashing de pesos por chunks.

No se activan batching, resize, cuantización ni reutilización de features. Los
runs existentes no se reejecutaron para probar estas mejoras.

## Análisis de abstenciones y agregación

De los 1.566 jobs por modelo, 326 son abstenciones deterministas por orientación.
Sobre las 1.240 llamadas reales:

| Modelo | No verificables del modelo | Fracción |
|---|---:|---:|
| 2B | 935 | 75,40 % |
| 8B | 930 | 75,00 % |

El output V4 solo contiene el veredicto, por lo que no permite separar con rigor
oclusiones, fuera de campo, baja resolución, distancia o ambigüedad. Para estudiar
esas causas haría falta un protocolo nuevo con rationale separado, no reinterpretar
los outputs actuales.

H16 evidencia cambio de dominio interior/exterior. En 2B, altar, retablo,
escultura, hornacinas, pinturas, cúpula y púlpito son no verificables en todas las
vistas; 8B tampoco verifica nunca altar, retablo, escultura, hornacinas o púlpito.
En H23, 2B no verifica `plaza` en ninguna vista. Las seis relaciones egocéntricas
de ambas consultas son abstenciones de política, no decisiones del VLM.

La agregación real:

- deduplica por secuencia;
- asigna peso 0,5 a claims genéricos y 1,0 a distintivos;
- normaliza soporte por la suma total de pesos de claims;
- neutraliza conflicto y `unverifiable`;
- no usa evidencia negativa en promoción.

Más fotografías no suman score directamente una vez soportado un claim, aunque
sí incrementan oportunidades de observarlo y `valid_verdicts`. En el subconjunto,
la correlación Pearson entre número de imágenes y evidencia positiva es 0,305
para 2B y 0,067 para 8B; no implica causalidad por el sesgo de disponibilidad.

## Distancias EPSG:25830

La evaluación se regeneró en un artefacto separado usando EPSG:25830. Mantiene
la conclusión: cero cambios GeoRecall y Top-1. La media Top-1 baseline/experimental
es 302,11 m. La sustitución H23 sigue siendo claramente más lejana. El artefacto
Haversine anterior se conserva para trazabilidad y no se sobrescribe.
