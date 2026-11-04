# Comparación de selectores y reutilización de evidencia H16/H23

## Manifests congelados

Brazo A, cobertura adaptativa:

`h16-h23-coverage_adaptive-manifest-sha256-0b458ee23eb5924671853f07c4c98e989ba1e0a528c4680faeb43db147ceab57`

Brazo B, prioridad geométrica:

`h16-h23-geometric_adaptive-manifest-sha256-532fa43ab7e16426063d0e51740a86a3f876e5d7a4ea1a5146811345e6d51e53`

Ambos usan Top-50, inventario, claims, modelos, rondas 25/50/100, límites y
reranking simétrico comunes. B declara FOV hipotético 90° y sensibilidad 60/120°.

## Assets y asociaciones

| Brazo | Assets | Disponibles | Pendientes | Asociaciones | Asociaciones existentes exactas |
|---|---:|---:|---:|---:|---:|
| A | 323 | 37 | 286 | 568 | 89 |
| B | 315 | 19 | 296 | 568 | 49 |

Intersección física:

- 127 assets comunes;
- 196 exclusivos A;
- 188 exclusivos B;
- unión 511;
- 37 disponibles en la unión;
- 474 descargas pendientes.

Las 391 pendientes del protocolo histórico no equivalen a esta unión.

## Reutilización de jobs

Identidad física de inferencia:

```text
modelo/revisión/pesos + SHA-256 imagen + claim + prompt + schema + generación +
estado de orientación
```

La asociación candidato-imagen no entra en el prompt V4. Una tarea física puede
proyectarse sobre varios candidatos solo bajo este contrato exacto. Si se añade
contexto de candidato, crop o geometría, ya no es reutilizable.

Por modelo:

| Brazo | Jobs proyectados | Reutilizables | Nuevos | Generate total | Generate reutilizable | Generate nuevo |
|---|---:|---:|---:|---:|---:|---:|
| A | 8.227 | 1.421 | 6.806 | 6.525 | 1.125 | 5.400 |
| B | 8.227 | 874 | 7.353 | 6.525 | 692 | 5.833 |

Estimación con tiempos observados:

- A 2B: 2.513 s; A 8B: 7.907 s;
- B 2B: 2.714 s; B 8B: 8.541 s.

Los jobs de assets pendientes no se consideran reutilizables hasta conocer el
SHA-256 real descargado.

## Evidencia discriminativa sobre el subconjunto existente

| Brazo/modelo | Asociaciones evaluables | Supported | Exclusivos | Compartidos | Fracción exclusiva | Distintivos | Ambiguos |
|---|---:|---:|---:|---:|---:|---:|---:|
| A 2B | 89 | 271 | 108 | 163 | 0,399 | 203 | 106 |
| A 8B | 89 | 261 | 117 | 144 | 0,448 | 180 | 109 |
| B 2B | 49 | 147 | 41 | 106 | 0,279 | 120 | 24 |
| B 8B | 49 | 135 | 42 | 93 | 0,311 | 96 | 27 |

Estos subconjuntos no son iguales. B tiene menos asociaciones históricas
reutilizables. Las fracciones no prueban superioridad. Exclusivo no significa
correcto y compartido no significa incorrecto.

## Unidades y doble conteo

Se distinguen:

1. asset físico;
2. asociación candidato-imagen;
3. slot consulta-candidato-imagen;
4. job proyectado;
5. tarea física Qwen;
6. veredicto y proyecciones.

Un mismo par imagen-claim puede aparecer en varios candidatos. Se ejecuta una vez
si su identidad física es idéntica, pero cada proyección permanece auditable. No
se cuenta como evidencia independiente.

## H16/H23

H16 conserva la limitación interior/exterior. Ningún selector Mapillary resuelve
retablo, altar o púlpito mediante más proximidad. Un futuro Commons debe ser un
protocolo separado.

En H23, los candidates rank 10/12 del experimento histórico no deben orientar la
selección nueva. Los manifests se congelaron sin GT. La evidencia compartida y
ambigüedad deben evaluarse después, no usarse para escoger retrospectivamente.

## Autorización

La unión requiere hasta 474 nuevas miniaturas, estimación 57,67 MB y máximo duro
3,792 GB. La solicitud específica permanece `approved=false` y
`terms_reviewed=false`.
