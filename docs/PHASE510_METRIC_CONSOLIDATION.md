# F5.10: consolidación y preparación de D076

## Alcance

F5.10 consolida post hoc los rankings F5.9 ya congelados. No ejecuta Qwen,
CrossText2Loc ni Street View, no modifica las evaluaciones históricas y no cambia
el MVP. Las galerías de 25 m y 50 m se informan por separado porque representan
las mismas consultas, no veinte observaciones independientes.

Fuentes verificadas por tamaño y SHA-256:

- manifiesto H01–H02: 7/7 artefactos;
- manifiesto H03–H10: 10/10;
- manifiesto F5.7: 8/8;
- manifiesto F5.5c: 9/9.

El resultado reproducible es:

```text
f510-consolidation-sha256-c4be6f6577be7403f419396a8f1953d25315a6afb3945a049c2d2ff9c4e81a22
```

## Métricas H01–H10

Cada celda indica `aciertos/denominador`. H01 participa en GeoRecall y Haversine,
pero no en Recall exacto porque está fuera de cobertura efectiva; el denominador
exacto es 9.

### Galería 25 m

| Variante | Geo@10 50 m | Geo@10 100 m | R@10 | Mín. Top-10 media/mediana | Geo@1 50 m | Geo@1 100 m | R@1 | Top-1 medio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `es_original` | **4/10** | **5/10** | **2/9** | 173,71 / **89,60 m** | 1/10 | 2/10 | 0/9 | 346,95 m |
| `es_cartographic` | **4/10** | **5/10** | 1/9 | 172,35 / **89,60 m** | 1/10 | 2/10 | 0/9 | 348,60 m |
| `en_conventional` | 3/10 | 3/10 | 1/9 | **170,45** / 188,12 m | 1/10 | **3/10** | 0/9 | 326,04 m |
| `en_toponym_preserved` | 3/10 | 3/10 | 1/9 | 183,24 / 194,51 m | 1/10 | 2/10 | 0/9 | 339,97 m |
| `en_cartographic` | 3/10 | 3/10 | 0/9 | 180,43 / 172,79 m | **3/10** | **3/10** | 0/9 | **318,63 m** |

### Galería 50 m

| Variante | Geo@10 50 m | Geo@10 100 m | R@10 | Mín. Top-10 media/mediana | Geo@1 50 m | Geo@1 100 m | R@1 | Top-1 medio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `es_original` | **4/10** | 5/10 | 2/9 | 132,60 / 122,11 m | 1/10 | 1/10 | 0/9 | 343,62 m |
| `es_cartographic` | 3/10 | 5/10 | 2/9 | 137,25 / 133,33 m | 1/10 | 1/10 | 0/9 | 350,70 m |
| `en_conventional` | 3/10 | **6/10** | 2/9 | **112,55** / 86,19 m | 1/10 | 1/10 | 0/9 | 351,69 m |
| `en_toponym_preserved` | 3/10 | 4/10 | 2/9 | 163,47 / 194,43 m | **2/10** | **3/10** | **1/9** | **265,50 m** |
| `en_cartographic` | **4/10** | **6/10** | **3/9** | 118,74 / **76,91 m** | 1/10 | 2/10 | 0/9 | 387,37 m |

Según D075, `es_original` lidera o empata la métrica primaria a 50 m en ambas
galerías. `en_cartographic` es la única variante Qwen que empata en 50 m y además
lidera GeoRecall@10 a 100 m y Recall@10 en la galería de 50 m. Sin embargo, en
25 m pierde un acierto a 50 m, dos a 100 m y dos aciertos exactos frente al
original.

## Resultados H03–H10

| Galería | Variante | Geo@10 50 m | Geo@10 100 m | R@10 | Mín. Top-10 media/mediana | Geo@1 50/100 m | R@1 |
|---|---|---:|---:|---:|---:|---:|---:|
| 25 m | `es_original` | 3/8 | **4/8** | 1/8 | 200,48 / 150,87 m | 0/8 / 1/8 | 0/8 |
| 25 m | `es_cartographic` | 3/8 | **4/8** | 0/8 | 198,78 / 149,14 m | 0/8 / 1/8 | 0/8 |
| 25 m | `en_conventional` | 3/8 | 3/8 | 1/8 | 166,03 / 192,65 m | 1/8 / 3/8 | 0/8 |
| 25 m | `en_toponym_preserved` | 3/8 | 3/8 | 1/8 | 160,47 / 185,12 m | 1/8 / 2/8 | 0/8 |
| 25 m | `en_cartographic` | 3/8 | 3/8 | 0/8 | **157,11 / 138,63 m** | **3/8 / 3/8** | 0/8 |
| 50 m | `es_original` | 3/8 | 4/8 | 1/8 | 132,60 / 122,11 m | 0/8 / 0/8 | 0/8 |
| 50 m | `es_cartographic` | 2/8 | 4/8 | 1/8 | 138,41 / 133,33 m | 0/8 / 0/8 | 0/8 |
| 50 m | `en_conventional` | 3/8 | 4/8 | **2/8** | 123,60 / 139,50 m | 1/8 / 1/8 | 0/8 |
| 50 m | `en_toponym_preserved` | 3/8 | 3/8 | **2/8** | 146,69 / 194,43 m | **2/8 / 3/8** | **1/8** |
| 50 m | `en_cartographic` | 3/8 | **5/8** | **2/8** | **115,27 / 76,91 m** | 1/8 / 2/8 | 0/8 |

## Comparación pareada H01–H10

Transiciones GeoRecall@10 frente a `es_original`:

| Galería | Variante | 50 m: fallo→acierto / acierto→fallo / igual | 100 m: fallo→acierto / acierto→fallo / igual |
|---|---|---:|---:|
| 25 m | `es_cartographic` | 0 / 0 / 10 | 0 / 0 / 10 |
| 25 m | `en_conventional` | 1 / 2 / 7 | 1 / 3 / 6 |
| 25 m | `en_toponym_preserved` | 1 / 2 / 7 | 1 / 3 / 6 |
| 25 m | `en_cartographic` | 1 / 2 / 7 | 1 / 3 / 6 |
| 50 m | `es_cartographic` | 0 / 1 / 9 | 0 / 0 / 10 |
| 50 m | `en_conventional` | 2 / 3 / 5 | 2 / 1 / 7 |
| 50 m | `en_toponym_preserved` | 2 / 3 / 5 | 1 / 2 / 7 |
| 50 m | `en_cartographic` | 2 / 2 / 6 | 2 / 1 / 7 |

Una variante no se considera superior si gana consultas pero pierde más aciertos
a 50 m. En 25 m, todas las variantes inglesas tienen saldo negativo. En 50 m,
`en_cartographic` queda neutral a 50 m y positivo a 100 m.

Comparaciones adicionales:

| Galería | Variante | R@10 mejora/empeora/igual, n exacto | Mín. Top-10 mejora/empeora/empata | Delta medio mínimo | Top-1 mejora/empeora/empata |
|---|---|---:|---:|---:|---:|
| 25 m | `es_cartographic` | 0/1/8, n=9 | 1/1/8 | −1,36 m | 0/1/9 |
| 25 m | `en_conventional` | 0/1/8, n=9 | 5/4/1 | −3,26 m | 6/3/1 |
| 25 m | `en_toponym_preserved` | 0/1/8, n=9 | 5/4/1 | +9,53 m | 6/3/1 |
| 25 m | `en_cartographic` | 0/2/7, n=9 | 5/5/0 | +6,72 m | 6/3/1 |
| 50 m | `es_cartographic` | 0/0/9, n=9 | 1/1/8 | +4,65 m | 0/1/9 |
| 50 m | `en_conventional` | 1/1/7, n=9 | 5/3/2 | −20,05 m | 6/4/0 |
| 50 m | `en_toponym_preserved` | 1/1/7, n=9 | 4/5/1 | +30,87 m | 7/2/1 |
| 50 m | `en_cartographic` | 1/0/8, n=9 | 4/3/3 | −13,86 m | 5/5/0 |

Las variantes inglesas cambian la identidad Top-1 en 9–10 de 10 consultas, pero
eso no equivale a mejora. `en_cartographic` mejora Top-1 en cinco y empeora en
cinco casos de 50 m.

## Rango de la candidata más próxima

El histograma completo se conserva en `consolidation.json`. La candidata más
próxima aparece con frecuencia al final del Top-10. Por ejemplo, en 50 m:

- `es_original`: rango 10 en 2/10 casos;
- `en_conventional`: rango 10 en 3/10;
- `en_toponym_preserved`: rango 1 en 3/10, pero rango 10 en 2/10;
- `en_cartographic`: nunca en rango 1; rangos 7–9 en 7/10 casos.

Esto explica que una variante pueda tener buen GeoRecall@10 y mal Top-1.

## Incertidumbre estadística

Con diez casos, un acierto cambia la tasa en 0,10. Los intervalos Wilson 95%
descriptivos de una tasa 4/10 son aproximadamente `[0,168; 0,687]`; para 3/10,
`[0,108; 0,603]`. Se solapan ampliamente y no demuestran superioridad general.

La sensibilidad leave-one-out de 4/10 está entre 3/9 y 4/9; la de 3/10 entre
2/9 y 3/9. Uno o dos casos pueden cambiar el orden de variantes. Estos intervalos
no corrigen selección previa, incertidumbre de referencia ni dependencia entre
galerías.

## Análisis Qwen

`es_cartographic` fue idéntica al original en siete de diez casos y cambió H05,
H06 y H07. Su comportamiento agregado es casi el original y no justifica por sí
solo cargar Qwen.

Las relaciones izquierda, derecha, delante/frente y detrás se conservaron en la
auditoría automática. Los nombres protegidos también, mientras
`en_conventional` tradujo `Pisco Sour Cocina Peruana`. Esto no demuestra que
CrossText2Loc comprenda orientación: heading no entra como input independiente y
las mejoras pueden proceder de idioma, nombres, longitud o eliminación de pistas
visuales no representadas en OSM Carto.

Qwen observó cargas cercanas a 87–90 s. La generación media fue 3,47 s por salida
en H01/H02; las campañas anteriores observaron aproximadamente 4,47–7,05 s según
longitud. CrossText2Loc residente opera en milisegundos. Estas son mediciones
locales, no estimaciones de producción.

## Protocolo de validación independiente

Se propone validar **una sola variante Qwen frente a `es_original`** sobre
**20–30 observaciones humanas nuevas**, con objetivo práctico de 24 casos
completos. Este tamaño permite observar estabilidad pareada y diversidad, pero no
promete significación estadística ni generalización fuera de D004.

Requisitos:

1. Localizaciones no usadas en F5.7/F5.9, separadas de sus panoramas y, cuando
   sea posible, de sus bloques espaciales.
2. Coordenada de cámara/observador e incertidumbre verificadas; orientación
   revisada cuando el texto use relaciones egocéntricas.
3. Descripción española redactada y congelada antes de rankings.
4. Detección de duplicados por panorama ID, distancia espacial y similitud
   textual antes de asignar la partición.
5. Prompts, Qwen, checkpoint, embeddings, galerías y Top-10 congelados.
6. Registro explícito de cobertura 25/50 m; casos fuera de cobertura permanecen
   en GeoRecall y fuera del denominador exacto.
7. Métrica principal pareada: GeoRecall@10 a 50 m por galería, informando
   fallo→acierto y acierto→fallo.
8. Métricas secundarias: 100 m, Recall exacto, mínimo Top-10, Top-1, latencia y
   auditoría semántica humana.

Un criterio de aprobación conservador para D076 sería que la variante Qwen:

- no reduzca los aciertos GeoRecall@10 a 50 m en ninguna galería;
- produzca más transiciones fallo→acierto que acierto→fallo en 50 m;
- no introduzca pérdidas de relaciones o nombres tras revisión humana;
- mantenga cobertura exacta y no dependa de uno o dos casos;
- justifique operativamente su latencia y memoria.

Se rechazaría si pierde aciertos a 50 m, requiere fallback/fusión no autorizados,
altera semántica o solo mejora métricas secundarias a 100 m.

## Propuesta provisional para D076

**Modo Sin LLM:** `es_original` directo a CrossText2Loc. Es el baseline más
simple y el mejor respaldado por GeoRecall@10 a 50 m humano.

**Modo Con LLM:** `en_cartographic` es la candidata Qwen más prometedora para una
validación independiente, porque empata 4/10 a 50 m en 50 m y lidera 6/10 a
100 m y 3/9 en Recall@10. No queda aprobada: pierde en la galería de 25 m y sus
mejoras/regresiones pareadas son inestables. `en_conventional` tiene el menor
error mínimo medio en 50 m, pero pierde un acierto a 50 m frente al original.

D076 debe permanecer `PENDIENTE DE EXPERIMENTO`. La próxima decisión del
responsable es elegir qué variante Qwen, si alguna, pasa a la validación ciega;
la recomendación F5.10 es `en_cartographic` como candidata, no como default.

## Artefactos

```text
results/generated/f5/f510-consolidation/
├── consolidation.json
├── report.html
└── manifest.json
```

El informe enlaza por SHA-256 las evaluaciones y manifiestos originales y no
sobrescribe resultados F5.9.

Reproducción local desde los artefactos F5.9 verificados:

```bash
.venv-geo/bin/python scripts/consolidate_f510_metrics.py \
  --output-root results/generated/f5/f510-consolidation
```

Los rankings y evaluaciones fuente permanecen fuera de Git por tamaño/política;
sus rutas lógicas, tamaños y SHA-256 se validan antes de consolidar.
