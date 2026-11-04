# Manifests pareados de selección visual H16/H23

## Identidades congeladas

Brazo A, adquisición adaptativa por cobertura:

`h16-h23-coverage_adaptive-manifest-sha256-0b458ee23eb5924671853f07c4c98e989ba1e0a528c4680faeb43db147ceab57`

Brazo B, prioridad geométrica:

`h16-h23-geometric_adaptive-manifest-sha256-532fa43ab7e16426063d0e51740a86a3f876e5d7a4ea1a5146811345e6d51e53`

Los manifests fijan los 100 slots, asociaciones, assets, secuencias, distancias,
criterios, FOV hipotético, inputs y estado de autorización. No contienen GT ni
outputs VLM para decidir selección.

## Reutilización física

| Brazo | Assets | Locales | Pendientes | Asociaciones | Asociaciones ya evaluadas |
|---|---:|---:|---:|---:|---:|
| A | 323 | 37 | 286 | 568 | 89 |
| B | 315 | 19 | 296 | 568 | 49 |

Entre brazos:

- 127 assets compartidos;
- 196 exclusivos de A;
- 188 exclusivos de B;
- unión 511;
- 37 disponibles en la unión;
- 474 pendientes.

La unión requiere una autorización propia. No equivale a las 391 imágenes del
protocolo Mapillary histórico.

## Identidad de inferencia

La reutilización de un output Qwen exige igualdad exacta de:

- modelo, revisión y hashes de pesos;
- SHA-256 de imagen;
- claim completo;
- prompt;
- output schema;
- `do_sample=false`, `max_new_tokens=24`, batch 1;
- modo modelo o abstención por orientación.

La proyección candidato-imagen no entra en el prompt V4. Un resultado físico puede
reutilizarse entre candidatos únicamente mientras ese contrato permanezca. Si se
añade crop, geometría o contexto de candidato, la identidad cambia.

## Jobs por modelo

| Brazo | Proyectados | Reutilizables | Nuevos | Generate total | Generate reutilizable | Generate nuevo |
|---|---:|---:|---:|---:|---:|---:|
| A | 8.227 | 1.421 | 6.806 | 6.525 | 1.125 | 5.400 |
| B | 8.227 | 874 | 7.353 | 6.525 | 692 | 5.833 |

Los jobs pendientes no se declaran reutilizables hasta conocer el hash real del
asset. Las abstenciones de orientación se registran pero no llaman al modelo.

Estimación de nuevas llamadas con tiempos observados:

- A: 2B 2.513 s, 8B 7.907 s;
- B: 2B 2.714 s, 8B 8.541 s.

## Discriminación sobre evidencia ya existente

Solo se comparan asociaciones exactas ya evaluadas, no se proyectan veredictos a
asociaciones nuevas.

| Brazo/modelo | Asociaciones | Supported | Exclusivos | Compartidos | Fracción exclusiva | Distintivos | Ambiguos |
|---|---:|---:|---:|---:|---:|---:|---:|
| A 2B | 89 | 271 | 108 | 163 | 39,9 % | 203 | 106 |
| A 8B | 89 | 261 | 117 | 144 | 44,8 % | 180 | 109 |
| B 2B | 49 | 147 | 41 | 106 | 27,9 % | 120 | 24 |
| B 8B | 49 | 135 | 42 | 93 | 31,1 % | 96 | 27 |

Los subconjuntos no son pareados: A reutiliza casi el doble de asociaciones. No
se concluye que A sea más discriminativo. Exclusivo no significa correcto;
compartido no significa erróneo.

## Presupuesto y autorización

La unión pendiente estima 57.670.476 B y máximo duro 3.792.000.000 B. La solicitud
específica está en
`config/h16_h23_selector_comparison_authorization.request.json` y permanece con
`approved=false`, `terms_reviewed=false`.

No se realizaron descargas ni inferencias nuevas.

## Dry-run y presupuesto físico

El dry-run offline valida hashes, IDs, presupuesto y autorización sin cargar
Torch, modelos o cliente Mapillary y sin abrir red.

Por modelo, la unión física A/B contiene 9.613 tareas: 2.453 compartidas entre
brazos, 845 reutilizables y 8.768 nuevas. De ellas, 7.625 requieren `generate()`,
669 son reutilizables y 6.956 son nuevas; 1.988 son abstenciones automáticas.

Estimación de nuevas inferencias: 2B 3.237 s (~54 min) y 8B 10.186 s (~170 min).
Checkpoint recomendado con margen 1,5×: 10,14 MB para 2B y 10,16 MB para 8B.

La identidad de tareas de assets pendientes es provisional por `image_id`. Solo
después de descargar y calcular SHA-256 puede declararse reutilización física
definitiva.
