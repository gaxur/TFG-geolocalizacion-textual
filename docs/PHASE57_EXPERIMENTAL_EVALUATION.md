# F5.7: evaluación experimental con referencias aproximadas

## Alcance y separación

F5.7 ejecuta Qwen3-8B y CrossText2Loc sobre las cuatro descripciones documentales
de F5.6. Es una excepción provisional para explorar el recorrido completo antes
de la revisión humana. No modifica F5.6, no aprueba las descripciones y no produce
métricas oficiales F5.4.

La referencia es la coordenada incluida en cada enlace de Street View. Su
incertidumbre es desconocida y no constituye una posición de cámara verificada.
Las coordenadas se incorporan únicamente después del ranking para calcular
distancias y asignaciones aproximadas; no entran en prompts, variantes ni
retrieval.

## Entradas y ejecución

El dataset canónico de entrada es:

```text
f56-streetview-documentary-sha256-575695ca55793d6077f9a464cfb53b61366871c7e721d9b0a3fe60e3d253be9a
```

`prepare_f57_inputs.py` lo adapta sin coordenadas a `f4-query-dataset-v1` y al
sidecar `f5-textual-variant-dataset-v2`. Qwen genera cuatro derivados por
descripción con el snapshot local `Qwen/Qwen3-8B`, revisión
`b968826d9c46dd6066d109eabc6255188de91218`, non-thinking y sin muestreo.

La auditoría automática exige salida estructural válida, correspondencia de hash,
ausencia de coordenadas e identificadores internos y conservación heurística de
negaciones y relaciones egocéntricas. Superar estos controles no equivale a una
revisión semántica humana. Una variante fallida se excluye de forma individual y
su ausencia no se convierte en un cero.

CrossText2Loc usa el checkpoint NewYork-mixed OSM congelado, las galerías
exhaustivas de 1.115 candidatos a 25 m y 253 candidatos a 50 m, y Top-10 sin
preselección ni fusión. Se ejecutó en `crosstext2loc-gb10:ngc26.02`, sin red.

## Resultados observados

La campaña real produjo 16/16 derivados Qwen válidos en los controles
automáticos, 20/20 variantes elegibles y 40/40 rankings.

| Galería | Variante | Recall@10 aproximado | GeoRecall@10, 50 m | GeoRecall@10, 100 m | Error Top-1 medio |
|---|---|---:|---:|---:|---:|
| 25 m | `es_original` | 0,00 | 0,00 | 0,75 | 412,84 m |
| 25 m | `es_cartographic` | 0,00 | 0,00 | 0,75 | 416,35 m |
| 25 m | `en_conventional` | 0,00 | 0,00 | 0,50 | 420,02 m |
| 25 m | `en_toponym_preserved` | 0,00 | 0,00 | 0,50 | 305,47 m |
| 25 m | `en_cartographic` | 0,00 | 0,25 | 0,50 | 401,40 m |
| 50 m | `es_original` | 0,00 | 0,25 | 0,75 | 365,69 m |
| 50 m | `es_cartographic` | 0,00 | 0,50 | 0,75 | 365,69 m |
| 50 m | `en_conventional` | 0,00 | 0,50 | 0,75 | 276,43 m |
| 50 m | `en_toponym_preserved` | 0,00 | 0,25 | 0,50 | 276,43 m |
| 50 m | `en_cartographic` | 0,00 | 0,50 | 0,75 | 385,90 m |

Recall@1 y Recall@5 aproximados también fueron 0,00 en todas las combinaciones.
Cada acierto cambia la tasa en 0,25. El tamaño, la falta de independencia, la
incertidumbre de referencia y la revisión pendiente impiden inferir superioridad
de idioma, variante o granularidad.

No existe una variante ganadora en todas las métricas. En 25 m,
`en_toponym_preserved` tuvo el menor error Top-1 medio (305,47 m), mientras las
variantes españolas lograron GeoRecall@10 a 100 m de 0,75 y el menor error mínimo
Top-10 medio (84,53 m). En 50 m, `en_conventional` y
`en_toponym_preserved` empataron en menor Top-1 medio (276,43 m), pero
`es_cartographic` obtuvo el menor mínimo Top-10 medio (79,99 m) y GeoRecall@10 a
50 m de 0,50. Solo son diferencias exploratorias en cuatro casos.

La mediana de retrieval por variante estuvo entre 6,37 y 8,13 ms. La media de
`es_original` fue 79,19 ms porque incluye el primer calentamiento del runtime;
para las demás variantes las medias estuvieron entre 6,39 y 7,91 ms. Los Top-10
de dos ejecuciones CrossText2Loc fueron idénticos; solo cambió telemetría.

## Artefactos y comandos

Los artefactos base están bajo `results/generated/f5/f57-final/` y el informe
final con latencias bajo `results/generated/f5/f57-final-v3/`. El manifest v2
enlaza dataset F5.6, inputs, run Qwen, sidecar derivado, auditoría, rankings,
evaluación e HTML. No se versionan pesos, capturas ni resultados voluminosos.

El informe final declara `official_f54_metrics=false`, cero casos oficialmente
evaluables y `coordinates_used_for_retrieval=false`.

Evaluación final:

```text
f57-experimental-evaluation-sha256-087353796a88f17300f1cf8854ae26ff6c26f6b5ab135b1ee332a21b24356265
```
