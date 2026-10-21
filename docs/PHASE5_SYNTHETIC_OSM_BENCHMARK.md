# F5.5c: revisión Panoramax y benchmark sintético OSM

## Cierre de revisión Panoramax

La segunda cola fue revisada visualmente sin aprobar GT:

| Aptitud | Segunda cola | Total diez imágenes |
|---|---:|---:|
| `suitable` | 1 | 2 |
| `limited` | 3 | 5 |
| `unsuitable` | 1 | 3 |
| GT `approved` | 0 | 0 |

Artefacto final:

```text
results/generated/f5/f55c/panoramax-review/
  f55c-complementary-review-905cd76a33dab3f27f970ef20beaca37dba2bbb5561f9aabcb794253d21ce87c/
    complementary-visual-review.json
    complementary-visual-review.html
```

La imagen `608dca83-929b-49d6-be52-537ee91a2aaa` es visualmente apta y
conserva una descripción propuesta pendiente de revisión final. Sus asignaciones
25/50 m son `accuracy_insufficient`; no se convierte en GT exacto.

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

## Paso posterior

1. Revisar las 35 descripciones mediante `review.html`.
2. Congelar una cola de decisiones humanas sin modificar textos/evidencia.
3. Importar solo sintéticas aprobadas al adaptador separado.
4. Generar y revisar las cinco variantes con F5.2.
5. Ejecutar CrossText2Loc con pesos, galerías y embeddings congelados.
6. Publicar métricas sintéticas por separado y comparaciones pareadas.
7. No usar estos resultados para sustituir las cinco observaciones propias
   recomendadas por F5.5b.
