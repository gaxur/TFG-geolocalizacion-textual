# Evaluación independiente H11–H25

## Objetivo y procedencia

La campaña compara `es_original` y Qwen `en_cartographic` sobre 15 descripciones
humanas nuevas, dos galerías y Top-10. Las descripciones y referencias proceden
del responsable del TFG a partir de Google Street View. Las coordenadas son puntos
de enlace de incertidumbre desconocida, no posiciones verificadas al centímetro
ni Ground Truth oficial F5.4.

Esta campaña se diseñó después de H01–H10 y se mantiene separada de aquella
muestra de desarrollo. H01–H10 comparó cinco variantes y sirvió para formular la
propuesta F5.10; H11–H25 compara de forma dirigida solo el baseline
`es_original` y la candidata `en_cartographic`. La auditoría no encontró
panoramas repetidos ni referencias a menos de 25 m respecto de F5.7/H01–H10.
No se suman sus denominadores ni se presentan ambos conjuntos como una única
muestra homogénea.

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

### Tendencia según el nivel de detalle textual

Al excluir H16 por ser una fotografía interior, el desglose exterior de la
galería de 50 m muestra una tendencia relevante:

| Grupo descriptivo | Casos exteriores | `es_original` Geo@10 50 m | `en_cartographic` Geo@10 50 m |
|---|---:|---:|---:|
| Sencilla | 5 | 1/5 (20 %) | 1/5 (20 %) |
| Intermedia | 5 | 1/5 (20 %) | 4/5 (80 %) |
| Compleja exterior | 4 | 1/4 (25 %) | 3/4 (75 %) |

Los resultados sugieren que `en_cartographic` puede resultar especialmente útil
para descripciones con mayor detalle textual. En las descripciones intermedias
alcanza un GeoRecall@10 a 50 m del 80 %, frente al 20 % de `es_original`; en las
complejas exteriores alcanza un 75 % frente al 25 %. En las sencillas ambas
variantes obtienen un 20 %.

Esta tendencia es exploratoria. Los grupos fueron asignados aleatoriamente y sus
etiquetas no constituyen una medida validada de dificultad ni una variable
continua de longitud. Además, los denominadores son cinco, cinco y cuatro casos,
por lo que uno solo modifica las tasas entre 20 y 25 puntos porcentuales. No se
presenta como superioridad general demostrada.

Por ello no se recomienda implementar todavía una selección automática entre
`es_original` y `en_cartographic` según la longitud o complejidad aparente de la
consulta. Antes habría que congelar esa regla y comprobarla en una muestra humana
independiente que incluya suficientes casos de cada nivel.

### Texto adaptable a la memoria del TFG

> Los resultados de la evaluación H11–H25 sugieren que la transformación
> `en_cartographic` resulta especialmente beneficiosa para descripciones con
> mayor detalle textual. En la galería de 50 m, alcanza un GeoRecall@10 a 50 m
> del 80 % en descripciones intermedias, frente al 20 % obtenido con
> `es_original`. En las descripciones complejas exteriores obtiene un 75 % frente
> al 25 %, mientras que en las sencillas ambas variantes alcanzan un 20 %. Estos
> resultados apuntan a una posible relación entre el nivel de detalle de las
> descripciones y la utilidad de la transformación lingüística. Sin embargo,
> debido al reducido tamaño de la muestra y al carácter no validado de las
> categorías, esta tendencia debe considerarse exploratoria y no una superioridad
> general demostrada. En consecuencia, no se adopta una selección automática de
> variante según la longitud de la descripción; dicha estrategia debería
> comprobarse previamente en una muestra independiente.

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

## Conclusión experimental: variante ganadora y justificación

Si fuese obligatorio seleccionar hoy una única configuración entre las cuatro
evaluadas, la elección provisional sería:

**Variante ganadora provisional: `en_cartographic` + galería `madrid-50m`.**

### Comparación de las cuatro configuraciones

| Configuración | Geo@10 50 m | Geo@10 100 m | Geo@1 50 m | Recall@10 | Mín. Top-10 media | Mediana | Geo@10 50 m exteriores |
|---|---:|---:|---:|---:|---:|---:|---:|
| `es_original` + 25 m | 4/15 | 7/15 | 1/15 | 0/15 | **168,19 m** | 135,52 m | 3/14 |
| `en_cartographic` + 25 m | 5/15 | 7/15 | 2/15 | 1/15 | 172,41 m | 135,52 m | 5/14 |
| `es_original` + 50 m | 4/15 | 7/15 | 0/15 | 1/15 | 126,16 m | 100,41 m | 3/14 |
| **`en_cartographic` + 50 m** | **8/15** | **8/15** | **2/15** | **3/15** | **96,40 m** | **47,33 m** | **8/14** |

La métrica principal GeoRecall@10 a 50 m favorece `en_cartographic` + 50 m con
8/15 aciertos. La diferencia es de tres aciertos frente a Qwen 25 m y cuatro
frente a cualquiera de las dos configuraciones con texto original. En el
subconjunto exterior alcanza 8/14 frente a 3/14 del español original de 50 m.

Los criterios secundarios también favorecen esa combinación: 8/15 a 100 m,
3/15 celdas exactas en Top-10 y un mínimo Top-10 de 96,40 m de media y 47,33 m
de mediana. No lidera el error Top-1, que no es la prioridad D075, y su
GeoRecall@1 continúa bajo: 2/15 a 50 m.

### Ventajas frente a las alternativas

- Duplica GeoRecall@10 a 50 m respecto de `es_original` + 50 m: 8/15 frente a
  4/15.
- Mejora también respecto de `en_cartographic` + 25 m: 8/15 frente a 5/15.
- En la comparación pareada con `es_original` + 50 m produce cinco transiciones
  fallo→acierto, una acierto→fallo y nueve empates.
- Mejora la distancia mínima Top-10 en 10 de 15 consultas y la empeora en cinco.
- La galería 50 m ofrece el mejor agregado con menos candidatos y menor mínimo
  Top-10 que la variante Qwen de 25 m.

### Inconvenientes y regresiones

- H16 interior pasa de acierto a fallo en ambas galerías; en 50 m el mínimo
  empeora de 46,68 m a 156,96 m.
- H12 pierde el acierto a 100 m y empeora de 50,20 m a 288,86 m de mínimo
  Top-10 en 50 m.
- Hay consultas con menor distancia mínima pero peor Top-1, y viceversa; no se
  interpreta un cambio de ranking como comprensión de orientación.
- Las salidas Qwen pasaron controles automáticos, pero la revisión semántica
  humana sigue pendiente.

### Coste de Qwen y efecto de la galería

Qwen añade 5.793,77 ms de transformación media y 5.872,60 ms de mediana por
consulta en esta campaña, sin contar la carga inicial del modelo. También exige
residencia GPU y aumenta la complejidad respecto de `es_original`.

La elección depende de la galería. En 25 m la mejora de Qwen es modesta, de 4/15
a 5/15 a 50 m, y la distancia mínima media empeora ligeramente. La galería de
50 m concentra la evidencia favorable: 8/15 a 50 m y 8/15 a 100 m.

### Contraste con F5.9/F5.10

H01–H10 no mostró superioridad consistente de Qwen: `es_original` lideraba o
empataba GeoRecall@10 a 50 m y las ventajas inglesas dependían de galería y
radio. H11–H25 cambia la tendencia, especialmente en 50 m, con una muestra nueva
sin panoramas repetidos ni referencias a menos de 25 m respecto de F5.7/H01–H10.

La diferencia puede deberse a variabilidad muestral, mayor presencia de nombres
comerciales, longitud y tipo de pistas, o al filtrado cartográfico de detalles
visuales. Los datos no permiten atribuir causalidad a uno de estos factores. H16
demuestra además que la transformación no es robusta para cualquier dominio.

### Nivel de confianza y condiciones de revisión

La confianza de esta recomendación es **baja-media**. La muestra tiene 15 casos,
las coordenadas de enlace tienen incertidumbre desconocida, no se revisaron las
capturas localmente y existe una fotografía interior. La recomendación podría
cambiar si:

- una revisión visual invalida descripciones, orientación o referencias;
- una muestra exterior adicional no reproduce el saldo pareado favorable;
- el coste de 5–10 s por transformación resulta inaceptable;
- se prioriza Top-1, latencia o la galería de 25 m en lugar de GeoRecall@10 a
  50 m;
- las regresiones H12/H16 representan casos frecuentes del uso real.

### Recomendación para el MVP e implicación para D076

Conviene mantener ambos modos seleccionables en el MVP para conservar el baseline
y observar regresiones. Si fuese obligatorio fijar una recomendación visible por
defecto, sería `en_cartographic` + `madrid-50m`, claramente etiquetada como
experimental. Esta elección práctica no exige cambiar automáticamente D076:
D076 puede permanecer pendiente hasta revisión humana y nueva validación.

### Veredicto final

Con la evidencia disponible, `en_cartographic` sobre la galería de 50 m es la
configuración provisional más defendible para el TFG porque obtiene el mayor
GeoRecall@10 a 50 m, mejora el resultado exterior y ofrece el menor error mínimo
Top-10 entre las cuatro alternativas. La recomendación es operativa y de
confianza baja-media, no una demostración de superioridad general de Qwen.

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
