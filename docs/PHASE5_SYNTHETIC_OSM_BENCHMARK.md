# F5.5c: benchmark sintético OSM

F5.5c se conserva como benchmark cartográfico independiente. La vía Panoramax
que coexistía durante su creación fue sustituida y retirada del flujo activo en
F5.6; su provenance histórica permanece en Git y en el registro de experimentos,
pero no forma parte de este benchmark ni de sus comandos actuales.

## Propósito del benchmark

El benchmark `synthetic_osm` permite una futura comprobación exploratoria de
CrossText2Loc sobre posiciones y evidencia cartográfica conocidas. No representa
personas in situ, observaciones fotográficas ni visibilidad. Sus resultados nunca
se mezclan con F5.4 real.

```text
benchmark_id:
f55c-synthetic-osm-sha256-bf7aea13116cda8e027343535f0a6d2de3bd6582aa09c6a65d1f14e9b24873c2
```

Artefactos fuera de Git:

```text
results/generated/f5/f55c-final/<benchmark_id>/
├── benchmark.json
├── evaluation-input.json
└── review.html
```

## Inputs congelados

- Catálogo F1 50 m: 253 celdas.
- Catálogo F1 25 m: 1.115 celdas.
- Snapshot OSM F2:
  `osm-madrid-pilot-osmxml-sha256-f2152555c742ab5fbe54b02fe7145c144757d00ed3941695856db9a52b983141`.
- Bundle F3 50 m:
  `f3-madrid-pilot-associations-sha256-5f4af89b9349de792d3a60752a15f227d49b96cdb688a671504e4cf30bf68453`.
- Objetos y asociaciones se enlazan mediante hashes efectivos de los JSONL.

F3 aporta predicados topológicos exactos y `center_distance_m` en EPSG:25830.
No se reconstruye visibilidad ni se consulta red.

## Selección de posiciones

1. Se consideran centros F1 de 50 m declarados explícitamente como puntos
   sintéticos por construcción.
2. Se exige que el mismo punto sea `assigned` inequívocamente en 50 m y 25 m con
   `reported_accuracy_m=None`; no se inventa GNSS.
3. Se exige al menos tres entidades útiles, dos tipos semánticos y descripción no
   trivial.
4. Se aplica *farthest-point sampling* en EPSG:25830 con seed 55.
5. Se descartan textos duplicados antes de seleccionar el siguiente punto.
6. Se solicitaban 40 casos con separación de 80 m; solo 25 cumplían. Se probó de
   forma controlada 70, 60 y 50 m. Se adoptó el mayor umbral que alcanzó el mínimo:
   70 m, que produjo 35 casos. No se rellenó artificialmente hasta 40.

Resultado:

| Métrica | Valor |
|---|---:|
| Observaciones | 35 |
| Development | 24 |
| Evaluation | 11 |
| Bloques espaciales de 150 m | 23 |
| Separación mínima real | 70,69 m |
| Celdas 25 m `assigned` | 35 |
| Celdas 50 m `assigned` | 35 |

Las particiones se asignan por bloque espacial, no por variante ni por fila. Un
bloque completo pertenece solo a development o evaluation.

## Descripciones y evidencia

Cada texto empieza por «En la cartografía de esta zona urbana» para no fingir una
observación visual. Las afirmaciones permitidas son:

- geometría OSM dentro, cruzando, conteniendo, solapando o tocando la celda;
- intersección con la celda;
- proximidad cualitativa al punto sintético basada en bandas de
  `center_distance_m`.

No se incluyen coordenadas, IDs internos, distancias exactas, izquierda/derecha,
cardinales, colores, alturas, materiales ni visibilidad. Los nombres OSM no se
insertan en el texto para evitar convertir topónimos únicos en respuesta directa;
sí se conservan en evidencia cuando existen.

Estadísticas:

| Entidades/relaciones por texto | Casos |
|---:|---:|
| 3 | 8 |
| 4 | 27 |

Media: 3,77 entidades y 3,77 relaciones. Longitud: 179–279 caracteres.

Tipos utilizados en las 35 observaciones:

| Tipo | Presencias |
|---|---:|
| vía | 33 |
| edificio | 31 |
| actividad/equipamiento | 20 |
| plaza | 16 |
| monumento/histórico | 14 |
| lugar de culto | 10 |
| parque/jardín | 8 |

Predicados persistidos:

| Predicado | Presencias |
|---|---:|
| `inside_cell` | 56 |
| `overlaps_cell` | 50 |
| `crosses_cell` | 26 |

Cada evidencia conserva `osm_ref`, tipo/ID OSM, rol geométrico, tipo semántico,
tags usados, predicado y distancia. El validador vuelve a abrir los JSONL F3 y
exige igualdad exacta; modificar distancia, tags o predicado invalida el
benchmark.

## Calidad y revisión humana

Todos los records empiezan:

```text
review.status: pending
```

El HTML local muestra posición, descripción, evidencia, asignaciones y estado:

```text
results/generated/f5/f55c-final/<benchmark_id>/review.html
```

Un revisor puede aprobar únicamente coherencia con OSM, naturalidad y ausencia de
fugas. Nunca convierte el caso en observación real. Debe rechazar:

- afirmaciones no respaldadas por el objeto/predicado F3;
- lenguaje de visibilidad u orientación;
- descripciones triviales, ambiguas o antinaturales;
- IDs, coordenadas o distancia exacta en el texto;
- duplicados semánticos excesivos;
- evidencia OSM mal tipada o irrelevante.

Estado actual: 35 pendientes, 0 aprobadas y 0 rechazadas.

Las decisiones se aplicarán sin editar texto o evidencia:

```bash
.venv-geo/bin/python scripts/review_f55c_synthetic_benchmark.py \
  --benchmark <benchmark.json> \
  --decisions <decisiones-humanas.json> \
  --output-root results/generated/f5/f55c-reviewed
```

El manifiesto debe cubrir exactamente las 35 observaciones una vez y justificar
cada `approve` o `reject`.

## Compatibilidad con métricas F5.4

`evaluation-input.json` reutiliza las definiciones de Recall@1/5/10, Haversine,
error mínimo@K y GeoRecall, pero declara:

```text
ground_truth_kind: synthetic_osm
real_ground_truth: false
```

Solo exporta observaciones sintéticas `approved`; actualmente exporta cero. No
pasa por el sidecar de GT real ni se agrega junto a métricas humanas.

## Contaminación experimental

OSM genera tanto los textos sintéticos como las imágenes OSM candidatas. Esto
crea solapamiento de fuente y favorece conceptos cartográficos. Por tanto:

- el benchmark no estima rendimiento con lenguaje humano independiente;
- no puede ser la única base para elegir prefiltrado/reranking OSM;
- no permite atribuir mejoras a comprensión visual;
- no se ajustan textos después de observar rankings;
- evaluation está congelada antes de ejecutar CrossText2Loc;
- los resultados deberán etiquetarse siempre como sintéticos.

## Ejecución

```bash
.venv-geo/bin/python scripts/build_f55c_synthetic_osm_benchmark.py \
  --count 40 \
  --seed 55 \
  --minimum-spacing-m 70 \
  --output-root results/generated/f5/f55c-final
```

No se ejecutaron Qwen, CrossText2Loc, prefiltrado ni reranking.

## Evaluación exploratoria provisional posterior

El 21 de octubre de 2026 se ejecutó una campaña excepcional separada sin cambiar
los 35 estados `pending`. La auditoría automática reconstruyó cada texto desde su
evidencia, revalidó F3 y no encontró fugas, duplicados exactos o de firma
semántica, afirmaciones visuales ni orientaciones. Esto no constituye revisión
humana.

Qwen3-8B produjo 140/140 derivados reales. Junto con los 35 originales se
auditaron 175 textos. Todos superaron los controles reforzados, incluida la
prohibición de introducir nombres OSM conservados solo en evidencia. Se aceptaron
como equivalencias controladas `atraviesa`/`cruza`,
`se superpone`/`se solapa` y el término cartográfico inglés `way`/`vía`; no se
regeneraron textos ni se modificaron prompts tras consultar rankings.

CrossText2Loc ejecutó 350/350 rankings Top-10 exhaustivos sobre 1.115 candidatos
de 25 m y 253 de 50 m. Las referencias sintéticas se incorporaron únicamente al
evaluador posterior. El resultado se identifica como:

```text
f55c-exploratory-evaluation-sha256-ad492e0d6d33e1edd1db092303470aff59685de600d71fb6eb8f2bf2e22b2fe8
```

Resultados globales provisionales:

| Galería | Variante | R@1 | R@5 | R@10 | Geo@10 50 m | Geo@10 100 m | Top-1 medio | Mín. Top-10 medio |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 25 m | `es_original` | 0,000 | 0,000 | 0,029 | 0,229 | 0,400 | 333,86 m | 186,20 m |
| 25 m | `es_cartographic` | 0,000 | 0,000 | 0,029 | 0,171 | 0,343 | 353,38 m | 190,65 m |
| 25 m | `en_conventional` | 0,000 | 0,029 | 0,029 | 0,114 | 0,143 | 412,87 m | 201,24 m |
| 25 m | `en_toponym_preserved` | 0,000 | 0,029 | 0,029 | 0,114 | 0,171 | 456,40 m | 235,35 m |
| 25 m | `en_cartographic` | 0,000 | 0,029 | 0,029 | 0,114 | 0,171 | 462,37 m | 245,32 m |
| 50 m | `es_original` | 0,000 | 0,000 | 0,086 | 0,257 | 0,429 | 444,55 m | 156,09 m |
| 50 m | `es_cartographic` | 0,000 | 0,000 | 0,057 | 0,257 | 0,486 | 435,05 m | 143,14 m |
| 50 m | `en_conventional` | 0,029 | 0,057 | 0,086 | 0,114 | 0,286 | 456,38 m | 157,32 m |
| 50 m | `en_toponym_preserved` | 0,029 | 0,029 | 0,086 | 0,114 | 0,257 | 420,05 m | 159,97 m |
| 50 m | `en_cartographic` | 0,029 | 0,057 | 0,086 | 0,086 | 0,257 | 457,27 m | 179,23 m |

La partición evaluation de 11 casos no se utilizó para cambiar prompts,
parámetros o textos. En ella, `es_original` y `es_cartographic` empataron en 25 m
con Top-1 medio de 338,14 m; `en_toponym_preserved` obtuvo 467,36 m. En 50 m,
`es_original` obtuvo 409,21 m y `en_toponym_preserved` 415,59 m. El Recall@1/5/10
de evaluation fue cero para todas las combinaciones.

F5.7 favorecía provisionalmente `en_toponym_preserved` por Top-1 medio en cuatro
referencias Street View aproximadas. F5.5c no reproduce esa tendencia de forma
consistente: la variante mejora el Top-1 global de 50 m frente al original, pero
lo empeora en 25 m y no mejora GeoRecall@10. Además, no conserva topónimos porque
los originales sintéticos no contienen ninguno. Sigue siendo una candidata
razonable para contrastar, no una ganadora confirmada. No se cambia el frontend,
el backend ni la decisión multilingüe pendiente.

Artefactos locales ignorados por Git:

```text
results/generated/f5/f55c-exploratory-real/
├── inputs/benchmark-audit.json
├── inputs/human-review-decisions-template.json
├── inputs/query-dataset.json
├── inputs/variant-template.json
├── qwen/<run_id>/derived-sidecar.json
├── qwen/<run_id>/run.json
├── variant-audit.json
├── rankings-complete.json
└── final-complete/{evaluation.json,report.html,manifest.json}
```

## Paso posterior

1. Abrir `review.html` y revisar las 35 fichas contra descripción, evidencia,
   asignaciones y estado.
2. Copiar la plantilla local de decisiones, sustituir todos los marcadores,
   identificar al revisor y justificar cada `approve` o `reject`.
3. Aplicar el manifiesto con `review_f55c_synthetic_benchmark.py`; nunca editar
   `review.status` directamente.
4. Revisar también las 140 transformaciones Qwen antes de tratarlas como
   variantes semánticamente aprobadas.
5. Recalcular el subconjunto validado sin mezclarlo con estas métricas
   provisionales, F5.4 real o F5.7.
