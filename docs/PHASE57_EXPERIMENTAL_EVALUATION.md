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

## Decisión provisional de variante para el MVP

Se selecciona **provisionalmente** `en_toponym_preserved` como variante textual
preferente para el MVP cuando el criterio principal del producto sea minimizar
el error geográfico medio de la primera ubicación propuesta, es decir, el error
Top-1. Esta es una decisión documentada para una configuración futura: el
frontend y el backend del MVP **no se han modificado todavía** para aplicar esta
variante por defecto.

La comparación que sustenta la decisión es:

| Variante | Error Top-1 medio, 25 m | Error Top-1 medio, 50 m | Media descriptiva entre galerías |
|---|---:|---:|---:|
| `es_original` | 412,84 m | 365,69 m | 389,26 m |
| `es_cartographic` | 416,35 m | 365,69 m | 391,02 m |
| `en_conventional` | 420,02 m | 276,43 m | 348,22 m |
| `en_toponym_preserved` | **305,47 m** | **276,43 m** | **290,95 m** |
| `en_cartographic` | 401,40 m | 385,90 m | 393,65 m |

`en_toponym_preserved` obtuvo el menor error Top-1 medio en la galería de 25 m
y empató con `en_conventional` en la de 50 m. El valor 290,95 m es únicamente la
media aritmética descriptiva de esos dos errores agregados; no constituye una
métrica oficial adicional, una combinación de galerías ni una evaluación
estadística independiente.

La elección no convierte a `en_toponym_preserved` en ganadora absoluta. Todas
las variantes obtuvieron Recall@1, Recall@5 y Recall@10 exacto aproximado de
0,00. Además, `en_toponym_preserved` alcanzó GeoRecall@10 a 100 m de 0,50 en
ambas galerías, por debajo del 0,75 de `es_cartographic`. En 50 m,
`es_cartographic`, `en_conventional` y `en_cartographic` alcanzaron
GeoRecall@10 a 50 m de 0,50, frente al 0,25 de `en_toponym_preserved`.
Por tanto, si el objetivo del producto pasa a priorizar que alguna ubicación
cercana aparezca dentro del Top-10, en lugar de minimizar el error de la primera
propuesta, deberá reconsiderarse esta preferencia.

La referencia contractual real de F5.7 es
`experimental_approximate_reference`. Las cuatro coordenadas proceden de enlaces
Street View, tienen incertidumbre desconocida y no son posiciones de cámara
verificadas de forma independiente. No constituyen Ground Truth validado F5.4;
de hecho, `officially_evaluable=0` y el informe declara
`official_f54_evaluation=false`. Las 16 transformaciones generadas por Qwen
siguen pendientes de revisión semántica humana, aunque superaron los controles
automáticos empleados para permitir esta ejecución provisional.

La muestra de cuatro observaciones es demasiado pequeña para establecer
superioridad estadística o generalizar el resultado a Madrid. Al utilizarse para
seleccionar provisionalmente una variante, estas cuatro observaciones pasan a
desempeñar una función de desarrollo y selección experimental. No deben
reutilizarse después como evaluación independiente final de la misma decisión.

## Reevaluación pendiente con F5.5c

La preferencia deberá revisarse tras completar la revisión humana y ejecutar el
benchmark `synthetic_osm` F5.5c. Ese benchmark contiene 35 observaciones
sintéticas: 24 de desarrollo y 11 de evaluación, inicialmente todas pendientes
de revisión humana.

Sus métricas deberán publicarse separadas de las cuatro referencias Street View.
Las observaciones `synthetic_osm` proceden de OSM y no son equivalentes a Ground
Truth humano independiente ni demuestran por sí solas qué variante funciona
mejor con descripciones visuales humanas. También debe preservarse la partición
de evaluación: no se puede usar iterativamente para ajustar prompts o seleccionar
variantes y presentarla después como evaluación intacta.

F5.5c podrá aportar evidencia complementaria sobre recuperación cartográfica. La
decisión provisional solo debería confirmarse si `en_toponym_preserved` mantiene
un compromiso favorable después de: revisar manualmente las transformaciones
Qwen, congelar los criterios de comparación y evaluar sin reutilizar como test
independiente los datos empleados para seleccionar la variante.

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
