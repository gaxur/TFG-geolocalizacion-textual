# Exploratory-v4: reranking geográfico estructurado OSM/F3

## Alcance

`h26-h37-exploratory-v4` estudia si las asociaciones OSM/F3 pueden reordenar el
Top-100 ya recuperado por CrossText2Loc. No incorpora imágenes, red, GPU, LLM ni
VLM. Mantiene las doce consultas, la galería Madrid 50 m y los mismos cien
candidatos por consulta.

Los rankings se generaron sin cargar referencias geográficas. El fichero de
referencias se abrió únicamente después de congelar
`structured-rankings.frozen.json`, en un evaluador separado. Los resultados son
de desarrollo y no demuestran generalización.

## Señales disponibles

F3 relaciona una celda candidata de 50 m con cada `node` o `way` cuya geometría
OSM la intersecta. El bundle contiene 29.777 objetos, 23.808 asociaciones y 253
candidatos con asociaciones. Conserva tags completos, `osm_ref`, rol geométrico,
predicados `within`, `crosses`, `overlaps`, `contains` y `touches`, además de la
distancia del centro de la celda a la geometría completa en EPSG:25830.

El bundle no conserva geometrías serializadas, bearing, orientación, visibilidad,
oclusión ni distancia a objetos que no intersectan la celda. Las relations son
contexto parcial sin geometría expandida. Por tanto:

- un objeto asociado existe cartográficamente en la celda, pero no se afirma que
  sea visible;
- la ausencia de un objeto no se usa como contradicción;
- izquierda, derecha, delante y fondo se registran como relaciones no puntuadas;
- varias representaciones OSM de una categoría no equivalen necesariamente a
  evidencias independientes.

## Evidencia textual

La extracción es determinista. Reconoce nombres entre comillas, categorías OSM
con reglas globales y relaciones egocéntricas explícitas. Distingue coincidencia
de nombre exacta, normalizada, compacta y de núcleo tras un descriptor comercial.
Las categorías genéricas, como edificio, comercio o árbol, nunca habilitan por sí
solas una promoción.

Se encontró señal moderada o fuerte en 8/12 consultas y se produjo fallback
exacto en H26, H29, H34 y H35. Las señales más discriminativas fueron nombres
como `Sportium`, `Starbucks Coffee` y `El Escarpín`, y categorías o conjunciones
raras como farmacia más paso, peluquería, torre, reloj, obra y museo más calle
peatonal.

El nombre exacto no garantiza unicidad geográfica. `Starbucks Coffee` es el
contraejemplo principal: una coincidencia literal promovida a Top-1 empeoró la
distancia de H31 en 281,30 m.

## Variantes

| Variante | Descripción |
|---|---|
| `baseline` | Orden CrossText2Loc Top-100 sin cambios |
| `atlas_v3` | Política visual histórica congelada |
| `historical_osm_gamma_0.35` | Prior OSM lineal histórico, solo como referencia |
| `structured_osm` | Orden por evidencia estructurada, con fallback si no es informativa |
| `rrf_k60` | Reciprocal Rank Fusion de CT2L y ranking estructurado |
| `conditional_top5` | Máximo una promoción a rank 5 con evidencia moderada o fuerte |
| `conditional_strong_top1` | Máximo una promoción a rank 1 solo con evidencia fuerte |

No se realizó una búsqueda masiva de parámetros. RRF usa únicamente `k=60`; las
dos posiciones de promoción responden a las funciones distintas que se querían
comparar, no a una optimización por GT.

## Resultados agregados

Las celdas muestran aciertos sobre 12 consultas.

| Variante | 50 m @1/@5/@10 | 100 m @1/@5/@10 | Top-1 media | Top-1 mediana | Mejoradas | Degradadas |
|---|---:|---:|---:|---:|---:|---:|
| CrossText2Loc | 0/0/3 | 1/4/5 | 382,76 m | 379,45 m | 0 | 0 |
| Atlas v3 | 0/0/3 | 1/4/5 | 382,39 m | 379,45 m | 1 | 0 |
| OSM histórico 0,35 | 0/1/2 | 2/4/6 | 342,59 m | 356,14 m | 2 | 0 |
| OSM estructurado | **1/2/6** | 1/4/**7** | 355,34 m | 379,45 m | 6 | 2 |
| RRF k=60 | **1/2/5** | **2**/4/6 | 359,33 m | 379,45 m | 6 | 1 |
| Promoción Top-5 | 0/**1**/3 | 1/4/5 | 382,76 m | 379,45 m | 0 | 0 |
| Promoción fuerte Top-1 | **1/1/3** | 1/4/5 | 393,40 m | 432,13 m | 2 | 1 |

El ranking estructurado mejora GeoRecall@10 a 50 y 100 m respecto a Atlas v3 y
reduce la distancia Top-1 media en 27,05 m respecto a Atlas. Sin embargo, degrada
H31 y H32 y sustituye de forma agresiva gran parte del Top-10. RRF contiene el
fallo de H31, pero degrada H32 en 524,12 m.

La aparente mejora media no es estable. H28 y H37 aportan las dos mayores
reducciones, aunque ninguna termina dentro de 100 m en Top-1. Si se retiran esas
dos consultas, el ranking estructurado empeora la media frente al baseline. El
leave-one-out se informa como sensibilidad, no como evaluación independiente ni
como mecanismo de selección.

## Casos principales

| Consulta | Evidencia | Movimiento relevante | Resultado |
|---|---|---|---|
| H27 | `Sportium` exacto | rank 45 a 1 estructurado | mejora 124,27 m, pero queda a 570,83 m |
| H28 | farmacia y pasos de peatones | rank 13 a 1; cercano rank 30 a 3 | mejora 333,84 m, sin hit Top-1 a 100 m |
| H30 | bolardos y elementos urbanos | rank 16 a 1; cercano rank 69 a 8 | mejora 31,72 m; evidencia correlacionada |
| H31 | `Starbucks Coffee` exacto | rank 53 a 1 estructurado | degrada 281,30 m |
| H32 | peluquería, bolardo y peatonal | rank 81 a 1 estructurado | degrada 233,30 m; RRF degrada 524,12 m |
| H33 | torre | rank 67 a 1 estructurado | mejora 99,80 m; Top-100 no contiene hit a 100 m |
| H36 | `El Escarpín` exacto | rank 10 a 1 | 62,17 a 32,79 m; nuevo hit @1 a 50 m |
| H37 | museo y peatonal | rank 30 a 1 | mejora 224,63 m, pero queda a 246,06 m |

La promoción Top-5 solo crea un nuevo acierto: H36 pasa a rank 5 a 50 m. Su
ventaja es conservar exactamente el Top-1 de todas las consultas; su beneficio
observado es demasiado pequeño para adoptarla como política validada.

## Diagnóstico

1. OSM sí ordena mejor algunos candidatos que CT2L infravalora.
2. Los nombres exactos y categorías raras son las señales más útiles.
3. Repetir numerosos objetos de la misma clase puede inflar artificialmente el
   score; bolardos y ways peatonales son ejemplos claros.
4. La frecuencia dentro del Top-100 no demuestra unicidad en Madrid. Las cadenas
   comerciales necesitan un control de unicidad o corroboración adicional.
5. Las conjunciones deben agrupar familias independientes y no sumar cada objeto
   cartográfico como una evidencia nueva.
6. La recuperación sigue limitando H33: ningún reranker Top-100 puede generar un
   candidato a menos de 100 m cuando no existe en la reserva.

## Decisión

No se sustituye Atlas v3. El ranking estructurado y RRF prueban que existe señal
cartográfica complementaria, pero sus degradaciones son demasiado grandes y sus
mejoras dependen de pocas consultas. La promoción directa a Top-1 por nombre se
descarta.

La dirección preferida para un experimento mínimo posterior es una promoción
Top-5 con evidencia fuerte, control de unicidad a escala del catálogo y
corroboración por dos familias independientes, agrupando objetos repetidos. Debe
conservar Top-1 CT2L y fallback exacto. No está justificado todavía implementar
un recuperador OSM independiente: primero debe comprobarse esa variante acotada
en desarrollo y, si se congela, evaluarse en un conjunto independiente.

## Reproducibilidad

Los artefactos están en
`results/generated/mapillary/h26-h37-exploratory-v4/`:

- `osm-f3-signal-audit.json`;
- `evidence-matrix.json`;
- `structured-rankings.frozen.json`;
- `evaluation.json`;
- `analysis.json`;
- `manifest.json`.

El manifiesto registra hashes, artefactos históricos, recursos y decisión final.
Atlas v3, exploratory-v2, exploratory-v3, `BASELINE.md` y el test sellado
permanecen sin modificar.
