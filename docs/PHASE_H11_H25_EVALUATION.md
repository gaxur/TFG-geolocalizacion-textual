# Evaluación independiente H11–H25

## Objetivo y procedencia

La campaña compara `es_original` y Qwen `en_cartographic` sobre 15 descripciones
humanas nuevas, dos galerías y Top-10. Las descripciones y referencias proceden
del responsable del TFG a partir de Google Street View. Las coordenadas son puntos
de enlace de incertidumbre desconocida, no posiciones verificadas al centímetro
ni Ground Truth oficial F5.4.

La asignación de categorías fue aleatoria y se conserva fija:

- sencilla: H12, H15, H19, H23, H24;
- intermedia: H11, H14, H18, H20, H25;
- compleja: H13, H16, H17, H21, H22.

Estas etiquetas describen longitud asignada, no dificultad geográfica medida.
H16 es una fotografía interior aportada por usuario y se informa por separado.

## Control de calidad

- 15/15 coordenadas dentro de D004.
- 15/15 `assigned` en 25 m y 50 m.
- 0 panoramas repetidos o referencias a ≤25 m de F5.7/H01–H10.
- 0 duplicados internos detectados.
- 0 coordenadas, panorama IDs o candidate IDs dentro de textos.
- Correspondencia visual y direcciones: `pending`, porque no se conservaron ni
  readquirieron capturas locales.
- URLs completas y pitch: no aportados; se registran como no disponibles.

H16 conserva la coordenada de la URL de fotografía, pero no se interpreta su
orientación como heading Street View exterior.

## Ejecución

Qwen3-8B generó 15/15 textos `en_cartographic`, una vez por consulta y sin
fallback. Cada original y cada salida se codificaron una sola vez en
CrossText2Loc y se reutilizaron para las dos galerías mediante `retrieve_many`.

```text
15 consultas × 2 variantes × 2 galerías = 60 rankings Top-10
30 codificaciones textuales CrossText2Loc
600 candidatas individuales
```

Evaluación:

```text
h11-h25-evaluation-sha256-952d33d7312f5e418bf43ccbdba4277800653b36a77f5bd026e22b85473502bf
```

## Resultados globales

| Galería | Variante | Geo@10 50 m | Geo@10 100 m | R@10 | Mín. Top-10 media/mediana | Geo@1 50/100 m | R@1 |
|---|---|---:|---:|---:|---:|---:|---:|
| 25 m | `es_original` | 4/15 | 7/15 | 0/15 | 168,19 / 135,52 m | 1/15 / 3/15 | 0/15 |
| 25 m | `en_cartographic` | **5/15** | 7/15 | **1/15** | 172,41 / 135,52 m | **2/15** / 3/15 | 0/15 |
| 50 m | `es_original` | 4/15 | 7/15 | 1/15 | 126,16 / 100,41 m | 0/15 / 2/15 | 0/15 |
| 50 m | `en_cartographic` | **8/15** | **8/15** | **3/15** | **96,40 / 47,33 m** | **2/15 / 2/15** | 0/15 |

## Exterior e interior

### Exteriores H11–H15 y H17–H25

| Galería | Variante | Geo@10 50 m | Geo@10 100 m | R@10 | Mín. Top-10 media/mediana |
|---|---|---:|---:|---:|---:|
| 25 m | `es_original` | 3/14 | 6/14 | 0/14 | 177,95 / 138,69 m |
| 25 m | `en_cartographic` | **5/14** | **7/14** | **1/14** | **172,26 / 114,12 m** |
| 50 m | `es_original` | 3/14 | 6/14 | 1/14 | 131,84 / 113,31 m |
| 50 m | `en_cartographic` | **8/14** | **8/14** | **3/14** | **92,07 / 45,92 m** |

### H16 interior

| Galería | Variante | Geo@10 50/100 m | Mín. Top-10 |
|---|---|---:|---:|
| 25 m | `es_original` | 1/1 / 1/1 | 31,62 m |
| 25 m | `en_cartographic` | 0/1 / 0/1 | 174,62 m |
| 50 m | `es_original` | 1/1 / 1/1 | 46,68 m |
| 50 m | `en_cartographic` | 0/1 / 0/1 | 156,96 m |

H16 empeora con Qwen en ambas galerías. Al ser un único interior, no se mezcla
silenciosamente con la conclusión exterior.

## Desglose por categoría aleatoria

### Sencillas

| Galería | Original Geo50/100 | Qwen Geo50/100 | Mínimo medio original/Qwen |
|---|---:|---:|---:|
| 25 m | 2/5 / 3/5 | 1/5 / 2/5 | 84,40 / 139,18 m |
| 50 m | 1/5 / 2/5 | 1/5 / 1/5 | 91,71 / 131,40 m |

### Intermedias

| Galería | Original Geo50/100 | Qwen Geo50/100 | Mínimo medio original/Qwen |
|---|---:|---:|---:|
| 25 m | 1/5 / 1/5 | 2/5 / 3/5 | 234,50 / 142,51 m |
| 50 m | 1/5 / 2/5 | 4/5 / 4/5 | 173,95 / 73,52 m |

### Complejas, incluido H16

| Galería | Original Geo50/100 | Qwen Geo50/100 | Mínimo medio original/Qwen |
|---|---:|---:|---:|
| 25 m | 1/5 / 3/5 | 2/5 / 2/5 | 185,67 / 235,55 m |
| 50 m | 2/5 / 3/5 | 3/5 / 3/5 | 112,83 / 84,27 m |

Los grupos tienen n=5 y no miden dificultad real; no se infiere tendencia
general a partir de estas diferencias.

## Comparación pareada

### Galería 25 m

- GeoRecall@10 50 m: 4 fallo→acierto, 3 acierto→fallo, 8 empates.
- GeoRecall@10 100 m: 4 mejoras, 4 empeoramientos.
- Distancia mínima: 7 mejoras y 7 empeoramientos.

Mejoras Geo50: H11, H13, H14 y H21. Regresiones: H12, H16 y H20.

### Galería 50 m

- GeoRecall@10 50 m: 5 fallo→acierto, 1 acierto→fallo, 9 empates.
- GeoRecall@10 100 m: 3 mejoras, 2 empeoramientos.
- Distancia mínima: 10 mejoras y 5 empeoramientos.

Mejoras Geo50: H11, H13, H14, H18 y H21. Regresión: H16.

No se confunden deltas Top-1 con la métrica principal. En varios casos Qwen
reduce el mínimo Top-10 y empeora Top-1, o viceversa.

## Casos destacados

- H11, H13 y H14 pasan de fallo a acierto a 50 m en ambas galerías.
- H18 pasa a acierto solo en 50 m.
- H21 mejora a 50 m en ambas galerías.
- H12 pierde GeoRecall en ambas galerías.
- H16 interior pierde proximidad en ambas galerías.
- H15 obtiene la celda exacta con Qwen en rangos 7/3.
- H20 mantiene proximidad en 50 m, pero pierde 50 m en 25 m.

## Latencia

Qwen, sin incluir carga:

```text
media: 5.793,77 ms
mediana: 5.872,60 ms
rango: 3.111,72–10.063,90 ms
```

Las latencias de retrieval por fila se conservan en `evaluation.json`; no se
mezclan con la transformación. La carga Qwen se registra en campañas previas y
no se atribuye a cada consulta de este batch residente.

## Limitaciones y conclusión

La muestra es pequeña, las referencias tienen incertidumbre desconocida y no se
revisó visualmente la orientación. Aun así, H11–H25 no solapa por panorama o
proximidad ≤25 m con F5.7/H01–H10 y aporta evidencia nueva.

`en_cartographic` mejora claramente el agregado exterior, especialmente en 50 m,
pero no domina todas las consultas: pierde H12 y H16, entre otras regresiones de
distancia. D076 permanece pendiente hasta revisar esta campaña y, si procede,
obtener referencias más verificadas.

## Reproducción

```bash
.venv-geo/bin/python scripts/prepare_h11_h25.py \
  --output results/generated/f5/h11-h25-independent/dataset.json

python scripts/transform_h11_h25.py \
  --dataset results/generated/f5/h11-h25-independent/dataset.json \
  --model-path "$HOME/models/hf/Qwen3-8B-b968826d9c46" \
  --output results/generated/f5/h11-h25-independent/qwen-run.json

.venv-cvgtext/bin/python scripts/rank_h11_h25.py \
  --dataset results/generated/f5/h11-h25-independent/dataset.json \
  --qwen-run results/generated/f5/h11-h25-independent/qwen-run.json \
  --clip-weights "$HOME/.cache/clip/ViT-L-14-336px.pt" \
  --cvg-utils-sha256 18dad4696c205dba5f934f9382ff5bd7d380c502680e462612bbdc49229ba597 \
  --plan-output results/generated/f5/h11-h25-independent/plan.json \
  --rankings-output results/generated/f5/h11-h25-independent/rankings.json

.venv-geo/bin/python scripts/evaluate_h11_h25.py \
  --dataset results/generated/f5/h11-h25-independent/dataset.json \
  --qwen-run results/generated/f5/h11-h25-independent/qwen-run.json \
  --plan results/generated/f5/h11-h25-independent/plan.json \
  --rankings results/generated/f5/h11-h25-independent/rankings.json \
  --output-root results/generated/f5/h11-h25-independent/final
```
